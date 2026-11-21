"""
CSRF token management API endpoints.

Fixes CRI-03 by:
- Generating secure CSRF tokens
- Validating tokens on requests
- Managing token lifecycle
- Rate limiting failed attempts
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
import redis

from app.database import get_db
from app.services.csrf_service import CSRFService
from app.schemas.csrf import (
    CSRFTokenRequest,
    CSRFTokenResponse,
    CSRFValidationRequest,
    CSRFValidationResponse,
    CSRFInvalidationRequest,
    CSRFInvalidationResponse,
    CSRFError
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/csrf", tags=["csrf"])

# Global CSRF service instance (should be injected via dependency)
_csrf_service: CSRFService = None


def get_csrf_service() -> CSRFService:
    """Get CSRF service instance."""
    global _csrf_service
    if _csrf_service is None:
        # Initialize with Redis
        try:
            redis_client = redis.from_url("redis://:redis123@localhost:6379/0")
            redis_client.ping()
            _csrf_service = CSRFService(redis_client)
        except Exception as e:
            logger.warning(f"Redis not available for CSRF service: {e}")
            _csrf_service = CSRFService(None)

    return _csrf_service


@router.get(
    "/token",
    response_model=CSRFTokenResponse,
    responses={
        200: {"model": CSRFTokenResponse, "description": "CSRF token generated"}
    }
)
async def get_csrf_token(
    request: Request,
    db: Session = Depends(get_db)
) -> CSRFTokenResponse:
    """
    Generate or retrieve CSRF token.

    **Endpoint Flow**:
    1. Extract session ID from request
    2. Generate cryptographically secure token (secrets.token_urlsafe)
    3. Store in Redis with 1-hour expiry
    4. Return token to client

    **Security Features**:
    - 32-byte random token (43+ characters when base64 encoded)
    - Redis storage with automatic expiry
    - Rate limiting on validation
    - Constant-time comparison

    **Response**:
    - CSRF token (URL-safe base64)
    - Expiry time in seconds (3600 = 1 hour)
    - Creation timestamp (ISO 8601)

    **Usage**:
    ```
    // 1. Get token
    const response = await fetch('/api/csrf/token');
    const { token, expires_in } = await response.json();

    // 2. Store token in variable or hidden input

    // 3. Send with POST request in header
    fetch('/api/endpoint', {
        method: 'POST',
        headers: {
            'X-CSRF-Token': token
        },
        body: JSON.stringify(data)
    });
    ```
    """

    try:
        csrf_service = get_csrf_service()

        # Generate token
        token = CSRFService.generate_token()

        # Get session ID
        session_id = csrf_service.get_session_id(request)

        # Store token
        success = csrf_service.store_token(session_id, token)

        if not success:
            logger.warning("Failed to store CSRF token")
            raise HTTPException(
                status_code=500,
                detail="Failed to store CSRF token"
            )

        logger.info(f"CSRF token generated for session: {session_id}")

        return CSRFTokenResponse(
            token=token,
            expires_in=CSRFService.TOKEN_EXPIRY,
            created_at=datetime.utcnow().isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error generating CSRF token: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate CSRF token"
        )


@router.post(
    "/validate",
    response_model=CSRFValidationResponse,
    responses={
        200: {"model": CSRFValidationResponse, "description": "Token validation result"},
        400: {"model": CSRFError, "description": "Missing token"}
    }
)
async def validate_csrf_token(
    request: Request,
    payload: CSRFValidationRequest,
    db: Session = Depends(get_db)
) -> CSRFValidationResponse:
    """
    Validate CSRF token.

    **Validation Process**:
    1. Check rate limiting (max 10 failed attempts per token)
    2. Retrieve stored token from Redis
    3. Compare using constant-time comparison (prevents timing attacks)
    4. Reset rate limit on success
    5. Increment rate limit on failure

    **Security Features**:
    - Rate limiting (10 attempts / 5 minutes)
    - Constant-time comparison
    - Timing attack prevention
    - Automatic expiry via Redis

    **Request Body**:
    - `session_id`: User session identifier
    - `token`: Token from client (from header or hidden input)

    **Response**:
    - `valid`: Boolean indicating if token is valid
    - `message`: Validation status message

    **Error Codes**:
    - 400: Missing session ID or token
    - 500: Validation error

    **Rate Limiting**:
    - 10 failed attempts allowed per token
    - 5-minute window
    - Counter resets on successful validation
    """

    try:
        csrf_service = get_csrf_service()

        # Validate token
        is_valid, error_msg = csrf_service.validate_token(
            session_id=payload.session_id,
            token=payload.token
        )

        if is_valid:
            logger.info(f"CSRF token validated for session: {payload.session_id}")
            message = "CSRF token is valid"
        else:
            logger.warning(
                f"CSRF token validation failed: {error_msg}"
            )
            message = error_msg or "CSRF token invalid"

        return CSRFValidationResponse(
            valid=is_valid,
            message=message
        )

    except Exception as e:
        logger.exception(f"Error validating CSRF token: {e}")
        raise HTTPException(
            status_code=500,
            detail="CSRF validation error"
        )


@router.post(
    "/invalidate",
    response_model=CSRFInvalidationResponse,
    responses={
        200: {"model": CSRFInvalidationResponse, "description": "Tokens invalidated"}
    }
)
async def invalidate_csrf_tokens(
    payload: CSRFInvalidationRequest,
    db: Session = Depends(get_db)
) -> CSRFInvalidationResponse:
    """
    Invalidate all CSRF tokens for a session.

    Called on:
    - User logout
    - Session termination
    - Security events (password change, etc.)

    **Request Body**:
    - `session_id`: Session to invalidate tokens for

    **Response**:
    - Confirmation message
    - Whether invalidation succeeded

    **Security**:
    - Clears all tokens from Redis for session
    - Requires valid session ID
    - Logged for audit trail
    """

    try:
        csrf_service = get_csrf_service()

        # Invalidate all tokens for session
        success = csrf_service.invalidate_token(payload.session_id)

        logger.info(
            f"CSRF tokens invalidated for session: {payload.session_id}"
        )

        return CSRFInvalidationResponse(
            message="CSRF tokens invalidated for session",
            invalidated=success
        )

    except Exception as e:
        logger.exception(f"Error invalidating CSRF tokens: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to invalidate CSRF tokens"
        )


@router.get(
    "/status",
    responses={
        200: {"model": dict, "description": "CSRF protection status"}
    }
)
async def get_csrf_status() -> dict:
    """
    Get CSRF protection status.

    Returns information about:
    - Whether CSRF protection is enabled
    - Redis availability
    - Configuration details

    **Response**:
    - Enabled: Boolean
    - Redis available: Boolean
    - Token expiry: Seconds
    - Rate limit attempts: Max attempts
    """

    try:
        csrf_service = get_csrf_service()

        return {
            "enabled": True,
            "redis_available": csrf_service.use_redis,
            "token_expiry_seconds": CSRFService.TOKEN_EXPIRY,
            "rate_limit_attempts": CSRFService.RATE_LIMIT_ATTEMPTS,
            "rate_limit_window_seconds": CSRFService.RATE_LIMIT_WINDOW,
            "safe_methods": list(CSRFService.SAFE_METHODS),
            "unsafe_methods": list(CSRFService.UNSAFE_METHODS),
            "header_name": CSRFService.HEADER_NAME,
            "cookie_name": CSRFService.COOKIE_NAME,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.exception(f"Error getting CSRF status: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get CSRF status"
        )
