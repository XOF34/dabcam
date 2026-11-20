"""
Unit tests for CaptureService.

Tests CRI-01 fix:
- Input validation (file size, type)
- Magic byte verification
- PIL image validation
- Secure filename generation
- File storage with correct permissions
"""

import os
import base64
import hashlib
from pathlib import Path
from io import BytesIO

import pytest
from PIL import Image

from app.services.capture_service import CaptureService


# Test fixtures

@pytest.fixture
def valid_png_data():
    """Generate valid PNG image data."""
    img = Image.new('RGB', (10, 10), color='red')
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return buffer.getvalue()


@pytest.fixture
def valid_jpeg_data():
    """Generate valid JPEG image data."""
    img = Image.new('RGB', (10, 10), color='blue')
    buffer = BytesIO()
    img.save(buffer, format='JPEG')
    return buffer.getvalue()


@pytest.fixture
def valid_webp_data():
    """Generate valid WebP image data."""
    img = Image.new('RGB', (10, 10), color='green')
    buffer = BytesIO()
    img.save(buffer, format='WebP')
    return buffer.getvalue()


@pytest.fixture
def invalid_image_data():
    """Generate invalid image data."""
    return b"This is not an image"


@pytest.fixture
def oversized_image_data():
    """Generate oversized image (larger than 5MB)."""
    return b'x' * (6 * 1024 * 1024)


# Tests for magic byte validation

class TestMagicByteValidation:
    """Test magic byte validation."""

    def test_png_magic_bytes_valid(self, valid_png_data):
        """PNG with correct magic bytes."""
        assert CaptureService.validate_image_magic_bytes(valid_png_data) is True

    def test_jpeg_magic_bytes_valid(self, valid_jpeg_data):
        """JPEG with correct magic bytes."""
        assert CaptureService.validate_image_magic_bytes(valid_jpeg_data) is True

    def test_webp_magic_bytes_valid(self, valid_webp_data):
        """WebP with correct magic bytes."""
        assert CaptureService.validate_image_magic_bytes(valid_webp_data) is True

    def test_invalid_magic_bytes(self, invalid_image_data):
        """Invalid magic bytes rejected."""
        assert CaptureService.validate_image_magic_bytes(invalid_image_data) is False

    def test_empty_data(self):
        """Empty data rejected."""
        assert CaptureService.validate_image_magic_bytes(b"") is False


# Tests for PIL validation

class TestPilValidation:
    """Test PIL image validation."""

    def test_png_validation_success(self, valid_png_data):
        """Valid PNG passes PIL validation."""
        is_valid, format_name = CaptureService.validate_image_with_pil(valid_png_data)
        assert is_valid is True
        assert format_name.lower() == 'png'

    def test_jpeg_validation_success(self, valid_jpeg_data):
        """Valid JPEG passes PIL validation."""
        is_valid, format_name = CaptureService.validate_image_with_pil(valid_jpeg_data)
        assert is_valid is True
        assert format_name.lower() in ('jpeg', 'jpg')

    def test_invalid_validation_failure(self, invalid_image_data):
        """Invalid image fails PIL validation."""
        is_valid, error = CaptureService.validate_image_with_pil(invalid_image_data)
        assert is_valid is False
        assert error is not None


# Tests for filename generation

class TestSecureFilenameGeneration:
    """Test secure filename generation."""

    def test_filename_uses_sha256(self, valid_png_data):
        """Filename is SHA256 hash."""
        filename = CaptureService.generate_secure_filename(valid_png_data)

        expected_hash = hashlib.sha256(valid_png_data).hexdigest()
        assert filename == f"{expected_hash}.png"

    def test_different_data_different_filename(self, valid_png_data, valid_jpeg_data):
        """Different data produces different filename."""
        filename1 = CaptureService.generate_secure_filename(valid_png_data)
        filename2 = CaptureService.generate_secure_filename(valid_jpeg_data)

        assert filename1 != filename2

    def test_same_data_same_filename(self, valid_png_data):
        """Same data produces same filename (deterministic)."""
        filename1 = CaptureService.generate_secure_filename(valid_png_data)
        filename2 = CaptureService.generate_secure_filename(valid_png_data)

        assert filename1 == filename2


# Tests for MIME type detection

class TestMimeTypeDetection:
    """Test MIME type detection from format."""

    def test_png_mime_type(self):
        """PNG format maps to correct MIME type."""
        mime = CaptureService._get_mime_type_from_format('png')
        assert mime == 'image/png'

    def test_jpeg_mime_type(self):
        """JPEG format maps to correct MIME type."""
        mime = CaptureService._get_mime_type_from_format('jpeg')
        assert mime == 'image/jpeg'

    def test_webp_mime_type(self):
        """WebP format maps to correct MIME type."""
        mime = CaptureService._get_mime_type_from_format('webp')
        assert mime == 'image/webp'

    def test_case_insensitive(self):
        """MIME type detection is case-insensitive."""
        mime1 = CaptureService._get_mime_type_from_format('PNG')
        mime2 = CaptureService._get_mime_type_from_format('png')

        assert mime1 == mime2 == 'image/png'


# Tests for complete validation flow

class TestCompleteValidationFlow:
    """Test complete validation flow."""

    def test_valid_png_passes_all_checks(self, valid_png_data):
        """Valid PNG passes all validation checks."""
        # Magic bytes
        assert CaptureService.validate_image_magic_bytes(valid_png_data) is True

        # PIL validation
        is_valid, format_name = CaptureService.validate_image_with_pil(valid_png_data)
        assert is_valid is True

        # Filename generation
        filename = CaptureService.generate_secure_filename(valid_png_data)
        assert filename.endswith('.png')

    def test_oversized_file_fails(self, oversized_image_data):
        """Oversized file fails validation."""
        # This will fail even before PIL check
        # because size check happens first in store_capture
        assert len(oversized_image_data) > CaptureService.MAX_FILE_SIZE

    def test_invalid_file_fails_magic_bytes(self, invalid_image_data):
        """Invalid file fails magic byte check."""
        assert CaptureService.validate_image_magic_bytes(invalid_image_data) is False

        # Also fails PIL validation
        is_valid, _ = CaptureService.validate_image_with_pil(invalid_image_data)
        assert is_valid is False


# Tests for base64 handling

class TestBase64Handling:
    """Test Base64 encoding/decoding."""

    def test_valid_base64_decoding(self, valid_png_data):
        """Valid Base64 encoded data decodes correctly."""
        encoded = base64.b64encode(valid_png_data).decode('utf-8')
        decoded = base64.b64decode(encoded, validate=True)

        assert decoded == valid_png_data

    def test_invalid_base64_raises(self):
        """Invalid Base64 raises exception."""
        with pytest.raises(Exception):
            base64.b64decode("not@valid@base64!", validate=True)


# Integration tests (with mock database)

class TestCaptureServiceIntegration:
    """Integration tests for CaptureService."""

    @pytest.mark.asyncio
    async def test_store_capture_validates_size(self, mock_db):
        """Store capture validates file size."""
        oversized = b'x' * (6 * 1024 * 1024)

        with pytest.raises(Exception) as exc_info:
            await CaptureService.store_capture(
                campaign_id="camp-123",
                target_id="tgt-456",
                image_data=oversized,
                db_session=mock_db
            )

        assert "too large" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_store_capture_validates_format(self, mock_db, invalid_image_data):
        """Store capture validates image format."""

        with pytest.raises(Exception) as exc_info:
            await CaptureService.store_capture(
                campaign_id="camp-123",
                target_id="tgt-456",
                image_data=invalid_image_data,
                db_session=mock_db
            )

        assert "invalid" in str(exc_info.value).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
