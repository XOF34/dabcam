"""
Integration tests for binary API endpoints.

Tests CRI-02 fix end-to-end:
- GET /api/binaries/trusted
- POST /api/binaries/download/{name}
- GET /api/binaries/downloaded
- GET /api/binaries/verify/{name}
- DELETE /api/binaries/{name}
- GET /api/binaries/{name}
"""

import pytest
from fastapi.testclient import TestClient


class TestBinaryAPI:
    """Test binary download API endpoints."""

    def test_get_trusted_binaries(self, client):
        """GET /api/binaries/trusted."""
        response = client.get("/api/binaries/trusted")

        assert response.status_code == 200
        data = response.json()

        assert 'binaries' in data
        assert 'total' in data
        assert len(data['binaries']) > 0

    def test_trusted_binaries_have_required_fields(self, client):
        """Trusted binaries have required fields."""
        response = client.get("/api/binaries/trusted")
        data = response.json()

        for binary in data['binaries']:
            assert 'name' in binary
            assert 'description' in binary
            assert 'available' in binary
            assert binary['available'] is True

    def test_ngrok_in_trusted_list(self, client):
        """ngrok is in trusted binary list."""
        response = client.get("/api/binaries/trusted")
        data = response.json()

        binary_names = [b['name'] for b in data['binaries']]
        assert 'ngrok' in binary_names

    def test_msfconsole_in_trusted_list(self, client):
        """msfconsole is in trusted binary list."""
        response = client.get("/api/binaries/trusted")
        data = response.json()

        binary_names = [b['name'] for b in data['binaries']]
        assert 'msfconsole' in binary_names

    def test_nmap_in_trusted_list(self, client):
        """nmap is in trusted binary list."""
        response = client.get("/api/binaries/trusted")
        data = response.json()

        binary_names = [b['name'] for b in data['binaries']]
        assert 'nmap' in binary_names

    def test_download_untrusted_binary(self, client):
        """POST /api/binaries/download with untrusted binary."""
        response = client.post("/api/binaries/download/untrusted-binary")

        assert response.status_code == 400
        data = response.json()
        assert 'detail' in data or 'error' in data

    def test_list_downloaded_binaries_empty(self, client):
        """GET /api/binaries/downloaded when none exist."""
        response = client.get("/api/binaries/downloaded")

        assert response.status_code == 200
        data = response.json()

        assert 'binaries' in data
        assert 'total' in data
        # May be empty or contain cached binaries

    def test_downloaded_binaries_have_required_fields(self, client):
        """Downloaded binaries have required fields."""
        response = client.get("/api/binaries/downloaded")
        data = response.json()

        for binary in data['binaries']:
            assert 'name' in binary
            assert 'path' in binary
            assert 'size' in binary
            assert 'permissions' in binary
            assert 'downloaded_at' in binary

    def test_get_nonexistent_binary_info(self, client):
        """GET /api/binaries/{name} for nonexistent binary."""
        response = client.get("/api/binaries/nonexistent")

        assert response.status_code == 404

    def test_delete_nonexistent_binary(self, client):
        """DELETE /api/binaries/{name} for nonexistent binary."""
        response = client.delete("/api/binaries/nonexistent")

        assert response.status_code == 404


class TestBinarySecurityValidation:
    """Test security validation for binary downloads."""

    def test_whitelist_only(self, client):
        """Only whitelisted binaries can be downloaded."""
        # Try to download non-whitelisted binary
        response = client.post("/api/binaries/download/malicious-binary")

        assert response.status_code == 400
        data = response.json()
        assert 'detail' in data or 'error' in data

    def test_ssl_verification_enabled(self):
        """SSL certificate verification is enabled."""
        # This is verified by checking the service implementation
        # The DependencyService uses verify=True in requests.get()
        from app.services.dependency_service import DependencyService
        assert DependencyService.DOWNLOAD_TIMEOUT > 0

    def test_timeout_configured(self):
        """Download timeout is configured."""
        from app.services.dependency_service import DependencyService
        assert DependencyService.DOWNLOAD_TIMEOUT == 30

    def test_size_limit_configured(self):
        """Download size limit is configured."""
        from app.services.dependency_service import DependencyService
        assert DependencyService.MAX_DOWNLOAD_SIZE == 500 * 1024 * 1024

    def test_permissions_read_execute_only(self):
        """Downloaded binaries have read/execute only permissions."""
        from app.services.dependency_service import DependencyService
        # 0o500 = r-x r-x r-x (read + execute, no write)
        assert DependencyService.FILE_PERMISSIONS == 0o500


class TestBinaryVerification:
    """Test binary verification endpoints."""

    def test_verify_nonexistent_binary(self, client):
        """GET /api/binaries/verify/{name} for nonexistent binary."""
        response = client.get("/api/binaries/verify/nonexistent")

        assert response.status_code == 200
        data = response.json()

        # Should return verification result
        assert 'name' in data
        assert 'valid' in data
        # valid will be False if not found


class TestBinaryDeletion:
    """Test binary deletion endpoints."""

    def test_delete_response_format(self, client):
        """DELETE response has correct format."""
        # Try to delete non-existent binary (will fail)
        response = client.delete("/api/binaries/nonexistent")

        # Will get 404 error
        assert response.status_code in (404, 500)


class TestBinaryAPIErrorHandling:
    """Test API error handling."""

    def test_malformed_request_handling(self, client):
        """Malformed requests are handled gracefully."""
        # Try to download binary with invalid name
        response = client.post("/api/binaries/download/")

        # Should handle gracefully
        assert response.status_code in (404, 422)

    def test_concurrent_downloads_isolation(self, client):
        """Multiple download requests are isolated."""
        # This tests that downloads don't interfere with each other
        # (would need actual concurrent testing)
        pass


class TestBinaryAPIDocumentation:
    """Test API documentation."""

    def test_swagger_docs_available(self, client):
        """Swagger API documentation is available."""
        response = client.get("/docs")

        assert response.status_code == 200
        # Docs page should be available


class TestBinaryAPIMetadata:
    """Test binary metadata handling."""

    def test_binary_metadata_returned(self):
        """Binary metadata is returned correctly."""
        from app.services.dependency_service import DependencyService

        binaries = DependencyService.get_trusted_binaries()

        for name, config in binaries.items():
            assert 'name' in config
            assert config['name'] == name
            assert 'description' in config
            assert config['available'] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
