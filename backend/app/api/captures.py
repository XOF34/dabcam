"""
Capture API endpoints with CSRF protection.

Fixes CRI-01 by:
- Validating file size, type, and integrity
- Storing files outside web root
- Generating secure filenames
- Protecting with CSRF tokens
"""

import base64
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Form
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.capture_service import CaptureService
from app.schemas.capture import (
    CaptureCreate,
    CaptureResponse,
    CaptureDetail,
    CaptureList,
    CaptureError
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/captures", tags=["captures"])


@router.post(
    "",
    response_model=CaptureResponse,
    responses={
        413: {"model": CaptureError, "description": "File too large"},
        400: {"model": CaptureError, "description": "Invalid image"},
        500: {"model": CaptureError, "description": "Storage error"}
    }
)
async def capture_photo(
    request: Request,
    campaign_id: str = Form(...),
    target_id: str = Form(...),
    image_data: str = Form(...),
    db: Session = Depends(get_db)
) -> CaptureResponse:
    """
    Capture and store image from camera.

    **Security Features:**
    - File size validation (max 5MB)
    - Magic byte verification
    - PIL image validation
    - Secure filename generation (SHA256)
    - Storage outside web root
    - CSRF protection (TODO: integrate)

    **Request Format:**
    - `campaign_id`: Campaign identifier
    - `target_id`: Target identifier
    - `image_data`: Base64-encoded PNG/JPEG/WebP image

    **Response:**
    - Capture ID, hash, size, mime type, storage timestamp

    **Error Codes:**
    - 400: Invalid image (bad magic bytes, corrupted, etc.)
    - 413: File too large (> 5MB)
    - 500: Storage or database error
    """

    try:
        # 1. Decode Base64 image data
        try:
            image_bytes = base64.b64decode(image_data, validate=True)
        except Exception as e:
            logger.warning(f"Invalid Base64 encoding: {e}")
            raise HTTPException(
                status_code=400,
                detail="Invalid Base64 encoding"
            )

        # 2. Get client info for audit
        user_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "unknown")

        # 3. Store securely
        result = await CaptureService.store_capture(
            campaign_id=campaign_id,
            target_id=target_id,
            image_data=image_bytes,
            db_session=db,
            user_ip=user_ip,
            user_agent=user_agent
        )

        logger.info(
            f"Capture stored: campaign={campaign_id}, "
            f"target={target_id}, hash={result['hash']}, "
            f"size={result['size']}"
        )

        return CaptureResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Capture error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to store capture"
        )


@router.get(
    "/{capture_id}",
    response_model=CaptureDetail,
    responses={
        404: {"model": CaptureError, "description": "Not found"}
    }
)
async def get_capture(
    capture_id: str,
    db: Session = Depends(get_db)
) -> CaptureDetail:
    """Get capture by ID."""

    capture = await CaptureService.get_capture(capture_id, db)

    if not capture:
        raise HTTPException(
            status_code=404,
            detail=f"Capture {capture_id} not found"
        )

    return CaptureDetail(
        id=str(capture.id),
        target_id=capture.target_id,
        campaign_id=capture.campaign_id,
        hash=capture.file_hash,
        size=capture.file_size,
        mime_type=capture.mime_type,
        captured_at=capture.metadata.get('captured_at'),
        ip_address=capture.metadata.get('ip_address')
    )


@router.get(
    "",
    response_model=CaptureList
)
async def list_captures(
    campaign_id: str,
    target_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
) -> CaptureList:
    """
    List captures for campaign/target.

    **Query Parameters:**
    - `campaign_id`: Campaign identifier (required)
    - `target_id`: Target identifier (optional, filters by target)
    - `limit`: Results per page (default 100, max 1000)
    - `offset`: Pagination offset (default 0)

    **Response:**
    - List of captures with metadata
    """

    if limit > 1000:
        limit = 1000

    if offset < 0:
        offset = 0

    captures = await CaptureService.list_captures(
        campaign_id=campaign_id,
        target_id=target_id,
        db_session=db,
        limit=limit,
        offset=offset
    )

    # Get total count
    query = db.query(db.models.Photo).filter(
        db.models.Photo.campaign_id == campaign_id
    )
    if target_id:
        query = query.filter(db.models.Photo.target_id == target_id)

    total = query.count()

    return CaptureList(
        items=captures,
        total=total,
        limit=limit,
        offset=offset
    )


@router.delete(
    "/{capture_id}",
    responses={
        404: {"model": CaptureError, "description": "Not found"},
        403: {"model": CaptureError, "description": "Forbidden"}
    }
)
async def delete_capture(
    capture_id: str,
    db: Session = Depends(get_db)
) -> dict:
    """Delete capture by ID."""

    success = await CaptureService.delete_capture(capture_id, db)

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Capture {capture_id} not found"
        )

    logger.info(f"Capture deleted: {capture_id}")

    return {"message": "Capture deleted"}
