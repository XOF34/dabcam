"""
Binary download API endpoints with security verification.

Fixes CRI-02 by:
- Whitelist of trusted binary sources
- SHA256 checksum verification
- GPG signature verification (optional)
- SSL certificate validation
- Secure storage with minimal permissions
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.dependency_service import DependencyService
from app.schemas.dependency import (
    BinaryListResponse,
    BinaryInfo,
    BinaryDownloadResponse,
    BinaryDownloadedList,
    BinaryDownloadedItem,
    BinaryVerifyResponse,
    BinaryDeleteResponse,
    BinaryError
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/binaries", tags=["binaries"])


@router.get(
    "/trusted",
    response_model=BinaryListResponse,
    responses={
        200: {"model": BinaryListResponse, "description": "List of trusted binaries"}
    }
)
async def get_trusted_binaries() -> BinaryListResponse:
    """
    Get list of available trusted binaries.

    **Trusted Binaries**:
    Only binaries in this whitelist can be downloaded.
    Each has a verified SHA256 checksum.

    **Response**:
    - List of available binaries with descriptions
    - Total count of trusted binaries
    """

    trusted = DependencyService.get_trusted_binaries()

    binaries = [
        BinaryInfo(
            name=data['name'],
            description=data['description'],
            available=data['available']
        )
        for data in trusted.values()
    ]

    logger.info(f"Listed {len(binaries)} trusted binaries")

    return BinaryListResponse(
        binaries=binaries,
        total=len(binaries)
    )


@router.post(
    "/download/{binary_name}",
    response_model=BinaryDownloadResponse,
    responses={
        400: {"model": BinaryError, "description": "Binary not in trusted list"},
        413: {"model": BinaryError, "description": "Download too large"},
        502: {"model": BinaryError, "description": "Download or verification failed"},
        504: {"model": BinaryError, "description": "Download timeout"}
    }
)
async def download_binary(
    binary_name: str,
    force: bool = Query(False, description="Force re-download"),
    db: Session = Depends(get_db)
) -> BinaryDownloadResponse:
    """
    Download and verify binary.

    **Security Features**:
    - Whitelist verification (only trusted binaries)
    - SHA256 checksum verification
    - GPG signature verification (if available)
    - SSL certificate verification
    - Timeout protection (30 seconds)
    - Size limits (500MB max)
    - Secure storage with 0o500 permissions

    **Process**:
    1. Verify binary is in trusted whitelist
    2. Check if already cached (use cache unless force=true)
    3. Download with SSL verification and timeout
    4. Verify SHA256 checksum
    5. Verify GPG signature (optional)
    6. Store with minimal permissions
    7. Log audit trail

    **Query Parameters**:
    - `force`: Force re-download (default: false)

    **Response**:
    - Binary name, path, size, hash
    - File permissions, status, download timestamp

    **Error Codes**:
    - 400: Binary not in trusted list
    - 413: Download exceeds 500MB limit
    - 502: Download or verification failed
    - 504: Download timeout (>30s)
    """

    try:
        logger.info(f"Download request: {binary_name} (force={force})")

        result = await DependencyService.download_verified_binary(
            binary_name=binary_name,
            force_download=force,
            db_session=db
        )

        logger.info(f"Download successful: {binary_name}")
        logger.info(f"  Status: {result['status']}")
        logger.info(f"  Size: {result['size']} bytes")
        logger.info(f"  Hash: {result['hash']}")

        return BinaryDownloadResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Download error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to download {binary_name}"
        )


@router.get(
    "/downloaded",
    response_model=BinaryDownloadedList
)
async def list_downloaded_binaries() -> BinaryDownloadedList:
    """
    List all downloaded binaries.

    **Response**:
    - List of downloaded binaries with metadata
    - File size, permissions, download timestamp
    """

    binaries = await DependencyService.list_downloaded_binaries()

    items = [
        BinaryDownloadedItem(**binary)
        for binary in binaries
    ]

    logger.info(f"Listed {len(items)} downloaded binaries")

    return BinaryDownloadedList(
        binaries=items,
        total=len(items)
    )


@router.get(
    "/verify/{binary_name}",
    response_model=BinaryVerifyResponse,
    responses={
        404: {"model": BinaryError, "description": "Binary not found"}
    }
)
async def verify_binary_integrity(binary_name: str) -> BinaryVerifyResponse:
    """
    Verify integrity of downloaded binary.

    Recalculates SHA256 hash and compares with trusted value.

    **Response**:
    - Valid: boolean indicating if hash matches
    - Hash: calculated SHA256 hash (if valid)
    """

    try:
        from app.services.dependency_service import DependencyService

        is_valid = await DependencyService.verify_binary_integrity(binary_name)

        if is_valid:
            logger.info(f"Binary verified: {binary_name}")
        else:
            logger.warning(f"Binary verification failed: {binary_name}")

        binary_path = DependencyService.SECURE_STORAGE_DIR / binary_name

        return BinaryVerifyResponse(
            name=binary_name,
            path=str(binary_path),
            valid=is_valid,
            hash=DependencyService.TRUSTED_BINARIES.get(binary_name, {}).get('sha256')
        )

    except Exception as e:
        logger.exception(f"Verification error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to verify {binary_name}"
        )


@router.delete(
    "/{binary_name}",
    response_model=BinaryDeleteResponse,
    responses={
        404: {"model": BinaryError, "description": "Binary not found"}
    }
)
async def delete_binary(binary_name: str) -> BinaryDeleteResponse:
    """
    Delete downloaded binary.

    **Response**:
    - Confirmation of deletion
    """

    try:
        success = await DependencyService.delete_binary(binary_name)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Binary {binary_name} not found"
            )

        logger.info(f"Binary deleted: {binary_name}")

        return BinaryDeleteResponse(
            name=binary_name,
            deleted=True,
            message="Binary deleted successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Deletion error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete {binary_name}"
        )


@router.get(
    "/{binary_name}",
    response_model=dict,
    responses={
        200: {"description": "Binary download stream"},
        404: {"model": BinaryError, "description": "Binary not found"}
    }
)
async def get_binary_info(binary_name: str) -> dict:
    """
    Get binary information.

    Returns metadata about downloaded binary.

    **Response**:
    - Name, path, size, permissions, download date
    """

    try:
        from pathlib import Path
        import os

        binary_path = DependencyService.SECURE_STORAGE_DIR / binary_name

        if not binary_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Binary {binary_name} not found"
            )

        stat = binary_path.stat()

        return {
            'name': binary_name,
            'path': str(binary_path),
            'size': stat.st_size,
            'permissions': oct(stat.st_mode)[-3:],
            'downloaded_at': datetime.fromtimestamp(stat.st_mtime).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting binary info: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get info for {binary_name}"
        )


from datetime import datetime
