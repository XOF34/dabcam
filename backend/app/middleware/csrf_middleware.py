"""
CSRF protection middleware for FastAPI.

Automatically validates CSRF tokens on unsafe HTTP methods.
Handles token generation for safe methods.
"""

import logging
from typing import Callable, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
import redis

from app.services.csrf_service import CSRFService


logger = logging.getLogger(__name__)


class CSRFMiddleware:
    """
    CSRF protection middleware.

    Features:
    - Generate token on GET requests
    - Validate token on POST/PUT/DELETE/PATCH
    - SameSite cookie policy
    - Rate limiting on failed attempts
    - Constant-time token comparison
    """

    def __init__(
        self,
        app,
        redis_client: Optional[redis.Redis] = None,
        exclude_paths: Optional[list] = None
    ):
        """
        Initialize CSRF middleware.

        Args:
            app: FastAPI application
            redis_client: Redis client for token storage
            exclude_paths: Paths to exclude from CSRF protection
        """
        self.app = app
        self.csrf_service = CSRFService(redis_client)

        # Paths that bypass CSRF protection (health checks, etc.)
        self.exclude_paths = exclude_paths or [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/api/health",
            "/api/health/database",
            "/api/health/redis",
            "/api/health/metasploit",
            "/"
        ]

    async def __call__(self, request: Request, call_next: Callable):
        """
        Process request through CSRF middleware.

        Flow:
        1. Skip CSRF check for safe methods and excluded paths
        2. For GET requests: Generate token and store
        3. For unsafe methods: Extract and validate token
        4. Return error on validation failure
        """

        method = request.method
        path = request.url.path

        # 1. Skip CSRF protection for safe methods
        if method in CSRFService.SAFE_METHODS:
            # Generate token for safe method
            token = CSRFService.generate_token()
            session_id = self.csrf_service.get_session_id(request)

            # Store token
            self.csrf_service.store_token(session_id, token)

            logger.debug(f"CSRF token generated for {method} {path}")

            # Proceed to route
            response = await call_next(request)

            # Add token to response headers
            response.headers["X-CSRF-Token"] = token

            # Set CSRF token cookie (double-submit pattern)
            response.set_cookie(
                CSRFService.COOKIE_NAME,
                token,
                max_age=CSRFService.TOKEN_EXPIRY,
                secure=True,
                httponly=False,  # Needed for JS to read
                samesite="Strict"
            )

            return response

        # 2. Skip for excluded paths
        if path in self.exclude_paths or path.startswith("/docs") or path.startswith("/redoc"):
            response = await call_next(request)
            return response

        # 3. For unsafe methods: validate CSRF token
        if method in CSRFService.UNSAFE_METHODS:
            # Get session ID
            session_id = self.csrf_service.get_session_id(request)

            # Extract token from request
            token = self.csrf_service.get_token_from_request(request)

            if not token:
                logger.warning(f"CSRF token missing for {method} {path}")
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "CSRF validation failed",
                        "detail": "CSRF token missing"
                    }
                )

            # Validate token
            is_valid, error_msg = self.csrf_service.validate_token(session_id, token)

            if not is_valid:
                logger.warning(
                    f"CSRF token invalid for {method} {path}: {error_msg}"
                )
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "CSRF validation failed",
                        "detail": error_msg or "CSRF token invalid"
                    }
                )

            logger.debug(f"CSRF token validated for {method} {path}")

        # Proceed to route
        response = await call_next(request)
        return response


class CSRFProtectDecorator:
    """
    Decorator for route-level CSRF protection.

    Usage:
        @app.post("/api/endpoint")
        @csrf_protect()
        async def my_endpoint(request: Request):
            pass
    """

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """Initialize decorator with Redis client."""
        self.csrf_service = CSRFService(redis_client)

    def __call__(self, func: Callable) -> Callable:
        """Wrap route function with CSRF protection."""

        async def wrapper(request: Request, *args, **kwargs):
            # Get session ID
            session_id = self.csrf_service.get_session_id(request)

            # Extract and validate token
            token = self.csrf_service.get_token_from_request(request)

            if not token:
                return JSONResponse(
                    status_code=403,
                    content={"error": "CSRF token missing"}
                )

            is_valid, error_msg = self.csrf_service.validate_token(session_id, token)

            if not is_valid:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "CSRF validation failed",
                        "detail": error_msg
                    }
                )

            # Call original function
            return await func(request, *args, **kwargs)

        return wrapper
