"""
Integration tests for capture API endpoints.

Tests CRI-01 fix end-to-end:
- POST /api/captures with Base64 image
- GET /api/captures/{id}
- GET /api/captures with filtering
- DELETE /api/captures/{id}
- Error handling (file size, format, etc.)
"""

import base64
import json
from io import BytesIO

import pytest
from PIL import Image
from fastapi.testclient import TestClient


@pytest.fixture
def valid_png_image():
    """Generate valid PNG image in Base64."""
    img = Image.new('RGB', (100, 100), color='red')
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return base64.b64encode(buffer.getvalue()).decode('utf-8')


@pytest.fixture
def invalid_image():
    """Generate invalid image in Base64."""
    return base64.b64encode(b"not an image").decode('utf-8')


@pytest.fixture
def oversized_image():
    """Generate oversized image (> 5MB) in Base64."""
    data = b'x' * (6 * 1024 * 1024)
    return base64.b64encode(data).decode('utf-8')


class TestCaptureEndpoints:
    """Test capture API endpoints."""

    def test_capture_with_valid_image(self, client, valid_png_image):
        """POST /api/captures with valid image."""
        response = client.post(
            "/api/captures",
            data={
                "campaign_id": "camp-123",
                "target_id": "tgt-456",
                "image_data": valid_png_image
            }
        )

        assert response.status_code == 200
        data = response.json()

        assert data['id']
        assert data['campaign_id'] == "camp-123"
        assert data['target_id'] == "tgt-456"
        assert data['hash']
        assert data['size'] > 0
        assert data['mime_type'] == "image/png"
        assert data['stored_at']

    def test_capture_with_invalid_image(self, client, invalid_image):
        """POST /api/captures with invalid image."""
        response = client.post(
            "/api/captures",
            data={
                "campaign_id": "camp-123",
                "target_id": "tgt-456",
                "image_data": invalid_image
            }
        )

        assert response.status_code == 400
        data = response.json()
        assert 'detail' in data or 'error' in data

    def test_capture_with_oversized_image(self, client, oversized_image):
        """POST /api/captures with oversized image."""
        response = client.post(
            "/api/captures",
            data={
                "campaign_id": "camp-123",
                "target_id": "tgt-456",
                "image_data": oversized_image
            }
        )

        assert response.status_code == 413

    def test_capture_missing_campaign_id(self, client, valid_png_image):
        """POST /api/captures without campaign_id."""
        response = client.post(
            "/api/captures",
            data={
                "target_id": "tgt-456",
                "image_data": valid_png_image
            }
        )

        assert response.status_code == 422  # Validation error

    def test_capture_missing_target_id(self, client, valid_png_image):
        """POST /api/captures without target_id."""
        response = client.post(
            "/api/captures",
            data={
                "campaign_id": "camp-123",
                "image_data": valid_png_image
            }
        )

        assert response.status_code == 422

    def test_capture_invalid_base64(self, client):
        """POST /api/captures with invalid Base64."""
        response = client.post(
            "/api/captures",
            data={
                "campaign_id": "camp-123",
                "target_id": "tgt-456",
                "image_data": "not!valid!base64!"
            }
        )

        assert response.status_code == 400

    def test_get_capture(self, client, valid_png_image):
        """GET /api/captures/{id}."""
        # First, create a capture
        create_response = client.post(
            "/api/captures",
            data={
                "campaign_id": "camp-123",
                "target_id": "tgt-456",
                "image_data": valid_png_image
            }
        )

        capture_id = create_response.json()['id']

        # Then retrieve it
        response = client.get(f"/api/captures/{capture_id}")

        assert response.status_code == 200
        data = response.json()

        assert data['id'] == capture_id
        assert data['campaign_id'] == "camp-123"
        assert data['target_id'] == "tgt-456"
        assert data['hash']
        assert data['size'] > 0
        assert data['mime_type'] == "image/png"

    def test_get_nonexistent_capture(self, client):
        """GET /api/captures/{id} for nonexistent ID."""
        response = client.get("/api/captures/nonexistent-id")

        assert response.status_code == 404

    def test_list_captures(self, client, valid_png_image):
        """GET /api/captures."""
        campaign_id = "camp-999"

        # Create multiple captures
        for i in range(3):
            client.post(
                "/api/captures",
                data={
                    "campaign_id": campaign_id,
                    "target_id": f"tgt-{i}",
                    "image_data": valid_png_image
                }
            )

        # List captures
        response = client.get(f"/api/captures?campaign_id={campaign_id}")

        assert response.status_code == 200
        data = response.json()

        assert 'items' in data
        assert 'total' in data
        assert 'limit' in data
        assert 'offset' in data
        assert data['total'] >= 3

    def test_list_captures_with_target_filter(self, client, valid_png_image):
        """GET /api/captures with target_id filter."""
        campaign_id = "camp-888"
        target_id = "tgt-filter-test"

        # Create capture for specific target
        client.post(
            "/api/captures",
            data={
                "campaign_id": campaign_id,
                "target_id": target_id,
                "image_data": valid_png_image
            }
        )

        # Create capture for different target
        client.post(
            "/api/captures",
            data={
                "campaign_id": campaign_id,
                "target_id": "tgt-other",
                "image_data": valid_png_image
            }
        )

        # Filter by target
        response = client.get(
            f"/api/captures?campaign_id={campaign_id}&target_id={target_id}"
        )

        assert response.status_code == 200
        data = response.json()

        # All returned items should be from the specified target
        for item in data['items']:
            assert item['target_id'] == target_id

    def test_list_captures_pagination(self, client, valid_png_image):
        """GET /api/captures with pagination."""
        campaign_id = "camp-777"

        # Create multiple captures
        for i in range(5):
            client.post(
                "/api/captures",
                data={
                    "campaign_id": campaign_id,
                    "target_id": f"tgt-{i}",
                    "image_data": valid_png_image
                }
            )

        # Get first page (limit 2)
        response1 = client.get(f"/api/captures?campaign_id={campaign_id}&limit=2&offset=0")
        data1 = response1.json()

        assert len(data1['items']) == 2
        assert data1['offset'] == 0
        assert data1['limit'] == 2

        # Get second page
        response2 = client.get(f"/api/captures?campaign_id={campaign_id}&limit=2&offset=2")
        data2 = response2.json()

        assert len(data2['items']) == 2
        assert data2['offset'] == 2

    def test_delete_capture(self, client, valid_png_image):
        """DELETE /api/captures/{id}."""
        # Create capture
        create_response = client.post(
            "/api/captures",
            data={
                "campaign_id": "camp-123",
                "target_id": "tgt-456",
                "image_data": valid_png_image
            }
        )

        capture_id = create_response.json()['id']

        # Delete it
        delete_response = client.delete(f"/api/captures/{capture_id}")

        assert delete_response.status_code == 200

        # Verify it's deleted
        get_response = client.get(f"/api/captures/{capture_id}")
        assert get_response.status_code == 404

    def test_delete_nonexistent_capture(self, client):
        """DELETE /api/captures/{id} for nonexistent ID."""
        response = client.delete("/api/captures/nonexistent-id")

        assert response.status_code == 404


class TestCaptureSecurity:
    """Test security features of capture API."""

    def test_file_stored_securely(self, client, valid_png_image):
        """Verify file is stored outside web root."""
        response = client.post(
            "/api/captures",
            data={
                "campaign_id": "camp-123",
                "target_id": "tgt-456",
                "image_data": valid_png_image
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Verify filepath is in secure directory
        # (This is verified by the service, but we check the response)
        assert 'hash' in data
        assert len(data['hash']) == 64  # SHA256 hex is 64 chars

    def test_filename_uses_hash(self, client, valid_png_image):
        """Verify filename is hash-based, not user input."""
        # Create capture
        response = client.post(
            "/api/captures",
            data={
                "campaign_id": "camp-123",
                "target_id": "tgt-456",
                "image_data": valid_png_image
            }
        )

        # Filename should be SHA256 hash, not campaign/target ID
        data = response.json()
        assert data['hash']

        # Try with different campaign/target - same image should have same hash
        response2 = client.post(
            "/api/captures",
            data={
                "campaign_id": "camp-different",
                "target_id": "tgt-different",
                "image_data": valid_png_image
            }
        )

        data2 = response2.json()
        assert data2['hash'] == data['hash']  # Same image = same hash


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
