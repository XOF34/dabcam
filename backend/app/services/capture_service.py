"""
Secure image capture service with validation & integrity checks.

Fixes CRI-01: Arbitrary File Write vulnerability
- Input validation (file size, type)
- Magic byte verification
- PIL image validation
- Secure filename generation (SHA256)
- Storage outside web root
- Database record with metadata
"""

import hashlib
import os
from io import BytesIO
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

from fastapi import HTTPException, UploadFile
from PIL import Image
import sqlalchemy as sa

from app.models import Photo, Target


class CaptureService:
    """Securely handle image capture and storage."""

    # Security configuration
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
    ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}
    ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

    # Storage configuration
    SECURE_STORAGE_DIR = Path("/secure/storage/captures")
    FILE_PERMISSIONS = 0o600  # Owner read/write only

    @staticmethod
    def validate_image_magic_bytes(data: bytes) -> bool:
        """Validate image file integrity using magic bytes."""

        # PNG: 89 50 4E 47 0D 0A 1A 0A
        if data.startswith(b'\x89PNG\r\n\x1a\n'):
            return True

        # JPEG: FF D8 FF
        if data.startswith(b'\xff\xd8\xff'):
            return True

        # WebP: RIFF ... WEBP
        if data.startswith(b'RIFF') and b'WEBP' in data[:12]:
            return True

        return False

    @staticmethod
    def validate_image_with_pil(data: bytes) -> tuple[bool, Optional[str]]:
        """Validate image using PIL and extract format."""

        try:
            img = Image.open(BytesIO(data))
            img.verify()  # Verify image integrity

            # Get actual format
            format_name = img.format.lower() if img.format else None
            return True, format_name

        except Exception as e:
            return False, str(e)

    @staticmethod
    def _get_mime_type_from_format(format_name: str) -> str:
        """Map PIL format to MIME type."""

        format_to_mime = {
            'png': 'image/png',
            'jpeg': 'image/jpeg',
            'jpg': 'image/jpeg',
            'webp': 'image/webp',
        }

        return format_to_mime.get(format_name.lower(), 'image/unknown')

    @staticmethod
    def generate_secure_filename(data: bytes) -> str:
        """Generate secure filename using SHA256 hash."""

        file_hash = hashlib.sha256(data).hexdigest()
        return f"{file_hash}.png"

    @staticmethod
    async def store_capture(
        campaign_id: str,
        target_id: str,
        image_data: bytes,
        db_session: sa.orm.Session,
        user_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict:
        """
        Securely store captured image.

        Args:
            campaign_id: Campaign identifier
            target_id: Target identifier
            image_data: Raw image bytes
            db_session: Database session
            user_ip: Client IP address (optional)
            user_agent: User-Agent header (optional)

        Returns:
            Dictionary with capture metadata

        Raises:
            HTTPException: On validation or storage failure
        """

        # 1. Validate file size
        if len(image_data) > CaptureService.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large (max {CaptureService.MAX_FILE_SIZE} bytes)"
            )

        if len(image_data) == 0:
            raise HTTPException(
                status_code=400,
                detail="Empty file"
            )

        # 2. Validate magic bytes
        if not CaptureService.validate_image_magic_bytes(image_data):
            raise HTTPException(
                status_code=400,
                detail="Invalid image file format"
            )

        # 3. Validate with PIL
        is_valid, format_name = CaptureService.validate_image_with_pil(image_data)
        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail=f"Image validation failed: {format_name}"
            )

        # 4. Generate secure filename with hash
        file_hash = hashlib.sha256(image_data).hexdigest()
        filename = f"{file_hash}.png"
        filepath = CaptureService.SECURE_STORAGE_DIR / filename

        # 5. Create storage directory if needed
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create storage directory: {e}"
            )

        # 6. Check if file already exists (deduplication)
        if filepath.exists():
            # File already stored, just create new DB record
            pass
        else:
            # 7. Store file outside web root
            try:
                with open(filepath, 'wb') as f:
                    f.write(image_data)

                # 8. Set minimal permissions (owner read/write only)
                os.chmod(filepath, CaptureService.FILE_PERMISSIONS)

            except IOError as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Storage error: {e}"
                )

        # 9. Get MIME type
        mime_type = CaptureService._get_mime_type_from_format(format_name)

        # 10. Create database record
        capture = Photo(
            campaign_id=campaign_id,
            target_id=target_id,
            filepath=str(filepath),
            file_hash=file_hash,
            file_size=len(image_data),
            mime_type=mime_type,
            metadata={
                'captured_at': datetime.utcnow().isoformat(),
                'ip_address': user_ip or 'unknown',
                'user_agent': user_agent or 'unknown',
                'format': format_name or 'unknown'
            }
        )

        try:
            db_session.add(capture)
            db_session.commit()
            db_session.refresh(capture)
        except Exception as e:
            db_session.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Database error: {e}"
            )

        return {
            'id': str(capture.id),
            'campaign_id': campaign_id,
            'target_id': target_id,
            'hash': file_hash,
            'size': len(image_data),
            'mime_type': mime_type,
            'stored_at': datetime.utcnow().isoformat()
        }

    @staticmethod
    async def get_capture(
        capture_id: str,
        db_session: sa.orm.Session
    ) -> Optional[Photo]:
        """Get capture by ID."""

        return db_session.query(Photo).filter(
            Photo.id == capture_id
        ).first()

    @staticmethod
    async def list_captures(
        campaign_id: str,
        target_id: Optional[str] = None,
        db_session: Optional[sa.orm.Session] = None,
        limit: int = 100,
        offset: int = 0
    ) -> list:
        """List captures for campaign/target."""

        query = db_session.query(Photo).filter(
            Photo.campaign_id == campaign_id
        )

        if target_id:
            query = query.filter(Photo.target_id == target_id)

        captures = query.order_by(
            Photo.metadata['captured_at'].desc()
        ).offset(offset).limit(limit).all()

        return [
            {
                'id': str(c.id),
                'target_id': c.target_id,
                'hash': c.file_hash,
                'size': c.file_size,
                'mime_type': c.mime_type,
                'captured_at': c.metadata.get('captured_at'),
                'ip_address': c.metadata.get('ip_address')
            }
            for c in captures
        ]

    @staticmethod
    async def delete_capture(
        capture_id: str,
        db_session: sa.orm.Session
    ) -> bool:
        """Delete capture and file."""

        capture = await CaptureService.get_capture(capture_id, db_session)
        if not capture:
            return False

        # Delete file
        try:
            filepath = Path(capture.filepath)
            if filepath.exists():
                os.chmod(filepath, 0o600)  # Ensure writable
                filepath.unlink()
        except OSError:
            pass  # File may already be deleted

        # Delete database record
        db_session.delete(capture)
        db_session.commit()

        return True
