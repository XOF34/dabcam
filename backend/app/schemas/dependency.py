"""
Pydantic schemas for binary dependency API.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class BinaryInfo(BaseModel):
    """Binary information from trusted list."""

    name: str = Field(..., description="Binary name")
    description: str = Field(..., description="Binary description")
    available: bool = Field(..., description="Is available for download")

    class Config:
        schema_extra = {
            "example": {
                "name": "ngrok",
                "description": "Secure introspectable tunnels",
                "available": True
            }
        }


class BinaryListResponse(BaseModel):
    """List of trusted binaries."""

    binaries: List[BinaryInfo]
    total: int

    class Config:
        schema_extra = {
            "example": {
                "binaries": [
                    {
                        "name": "ngrok",
                        "description": "Secure introspectable tunnels",
                        "available": True
                    }
                ],
                "total": 1
            }
        }


class BinaryDownloadResponse(BaseModel):
    """Binary download response."""

    name: str = Field(..., description="Binary name")
    path: str = Field(..., description="Absolute storage path")
    size: int = Field(..., description="File size in bytes")
    hash: str = Field(..., description="SHA256 file hash")
    permissions: str = Field(..., description="File permissions (octal)")
    status: str = Field(..., description="Status: downloaded or cached")
    downloaded_at: datetime = Field(..., description="Download timestamp")

    class Config:
        schema_extra = {
            "example": {
                "name": "ngrok",
                "path": "/secure/binaries/ngrok",
                "size": 50000000,
                "hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "permissions": "500",
                "status": "downloaded",
                "downloaded_at": "2026-11-20T12:00:00Z"
            }
        }


class BinaryDownloadedItem(BaseModel):
    """Downloaded binary item."""

    name: str
    path: str
    size: int
    permissions: str
    downloaded_at: str

    class Config:
        schema_extra = {
            "example": {
                "name": "ngrok",
                "path": "/secure/binaries/ngrok",
                "size": 50000000,
                "permissions": "500",
                "downloaded_at": "2026-11-20T12:00:00Z"
            }
        }


class BinaryDownloadedList(BaseModel):
    """List of downloaded binaries."""

    binaries: List[BinaryDownloadedItem]
    total: int

    class Config:
        schema_extra = {
            "example": {
                "binaries": [],
                "total": 0
            }
        }


class BinaryVerifyResponse(BaseModel):
    """Binary integrity verification response."""

    name: str = Field(..., description="Binary name")
    path: str = Field(..., description="Binary path")
    valid: bool = Field(..., description="Is binary valid (hash matches)")
    hash: Optional[str] = Field(None, description="Calculated hash (if valid)")

    class Config:
        schema_extra = {
            "example": {
                "name": "ngrok",
                "path": "/secure/binaries/ngrok",
                "valid": True,
                "hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            }
        }


class BinaryDeleteResponse(BaseModel):
    """Binary deletion response."""

    name: str
    deleted: bool
    message: str

    class Config:
        schema_extra = {
            "example": {
                "name": "ngrok",
                "deleted": True,
                "message": "Binary deleted successfully"
            }
        }


class BinaryError(BaseModel):
    """Binary error response."""

    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Error detail")

    class Config:
        schema_extra = {
            "example": {
                "error": "Checksum verification failed",
                "detail": "Downloaded binary does not match trusted hash"
            }
        }
