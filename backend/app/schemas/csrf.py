"""
Pydantic schemas for CSRF protection API.
"""

from pydantic import BaseModel, Field
from typing import Optional


class CSRFTokenRequest(BaseModel):
    """CSRF token request."""

    session_id: str = Field(..., description="User session ID")

    class Config:
        schema_extra = {
            "example": {
                "session_id": "sess-abc123def456"
            }
        }


class CSRFTokenResponse(BaseModel):
    """CSRF token response."""

    token: str = Field(..., description="CSRF token (43+ characters)")
    expires_in: int = Field(..., description="Token expiry time in seconds")
    created_at: str = Field(..., description="Token creation timestamp")

    class Config:
        schema_extra = {
            "example": {
                "token": "xK9pL2mQ5nR8sT1uV4wX7yZ0aB3cD6eF9gH2jK5lM8nO",
                "expires_in": 3600,
                "created_at": "2026-11-20T12:00:00Z"
            }
        }


class CSRFValidationRequest(BaseModel):
    """CSRF validation request."""

    session_id: str = Field(..., description="User session ID")
    token: str = Field(..., description="CSRF token to validate")

    class Config:
        schema_extra = {
            "example": {
                "session_id": "sess-abc123def456",
                "token": "xK9pL2mQ5nR8sT1uV4wX7yZ0aB3cD6eF9gH2jK5lM8nO"
            }
        }


class CSRFValidationResponse(BaseModel):
    """CSRF validation response."""

    valid: bool = Field(..., description="Is token valid")
    message: str = Field(..., description="Validation message")

    class Config:
        schema_extra = {
            "example": {
                "valid": True,
                "message": "CSRF token is valid"
            }
        }


class CSRFInvalidationRequest(BaseModel):
    """CSRF token invalidation request."""

    session_id: str = Field(..., description="User session ID")

    class Config:
        schema_extra = {
            "example": {
                "session_id": "sess-abc123def456"
            }
        }


class CSRFInvalidationResponse(BaseModel):
    """CSRF token invalidation response."""

    message: str = Field(..., description="Invalidation message")
    invalidated: bool = Field(..., description="Was token invalidated")

    class Config:
        schema_extra = {
            "example": {
                "message": "CSRF tokens invalidated for session",
                "invalidated": True
            }
        }


class CSRFError(BaseModel):
    """CSRF error response."""

    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Error detail")

    class Config:
        schema_extra = {
            "example": {
                "error": "CSRF validation failed",
                "detail": "CSRF token missing"
            }
        }
