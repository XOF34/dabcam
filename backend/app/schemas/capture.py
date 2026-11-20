"""
Pydantic schemas for image capture API.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class CaptureCreate(BaseModel):
    """Create capture request."""

    campaign_id: str = Field(..., description="Campaign ID")
    target_id: str = Field(..., description="Target ID")
    image_data: str = Field(..., description="Base64-encoded image data")

    class Config:
        schema_extra = {
            "example": {
                "campaign_id": "camp-123",
                "target_id": "tgt-456",
                "image_data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
            }
        }


class CaptureResponse(BaseModel):
    """Capture response."""

    id: str = Field(..., description="Capture ID")
    campaign_id: str = Field(..., description="Campaign ID")
    target_id: str = Field(..., description="Target ID")
    hash: str = Field(..., description="SHA256 file hash")
    size: int = Field(..., description="File size in bytes")
    mime_type: str = Field(..., description="MIME type (image/png, etc.)")
    stored_at: datetime = Field(..., description="Storage timestamp")

    class Config:
        schema_extra = {
            "example": {
                "id": "cap-123",
                "campaign_id": "camp-123",
                "target_id": "tgt-456",
                "hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "size": 1024,
                "mime_type": "image/png",
                "stored_at": "2026-11-20T12:00:00Z"
            }
        }


class CaptureDetail(BaseModel):
    """Detailed capture information."""

    id: str
    target_id: str
    campaign_id: str
    hash: str
    size: int
    mime_type: str
    captured_at: Optional[str]
    ip_address: Optional[str]

    class Config:
        schema_extra = {
            "example": {
                "id": "cap-123",
                "target_id": "tgt-456",
                "campaign_id": "camp-123",
                "hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "size": 1024,
                "mime_type": "image/png",
                "captured_at": "2026-11-20T12:00:00Z",
                "ip_address": "192.168.1.100"
            }
        }


class CaptureList(BaseModel):
    """List of captures."""

    items: list[CaptureDetail]
    total: int
    limit: int
    offset: int

    class Config:
        schema_extra = {
            "example": {
                "items": [],
                "total": 1,
                "limit": 100,
                "offset": 0
            }
        }


class CaptureError(BaseModel):
    """Capture error response."""

    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Error detail")

    class Config:
        schema_extra = {
            "example": {
                "error": "Invalid image file",
                "detail": "File format not supported"
            }
        }
