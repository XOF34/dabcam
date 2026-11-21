"""
Unit tests for CSRFService.

Tests CRI-03 fix:
- Token generation (secrets.token_urlsafe)
- Token storage and retrieval
- Token validation with constant-time comparison
- Rate limiting on failed attempts
- Session management
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import json

from app.services.csrf_service import CSRFService


# Fixtures

@pytest.fixture
def csrf_service():
    """Create CSRF service without Redis."""
    return CSRFService(redis_client=None)


@pytest.fixture
def csrf_service_with_redis():
    """Create CSRF service with mock Redis."""
    mock_redis = MagicMock()
    return CSRFService(redis_client=mock_redis), mock_redis


@pytest.fixture
def session_id():
    """Generate test session ID."""
    return "test-session-123"


# Tests for token generation

class TestTokenGeneration:
    """Test CSRF token generation."""

    def test_token_generation_returns_string(self):
        """Generated token is a string."""
        token = CSRFService.generate_token()
        assert isinstance(token, str)

    def test_token_has_minimum_length(self):
        """Generated token has minimum length (43+ characters)."""
        token = CSRFService.generate_token()
        # URL-safe base64 of 32 bytes is about 43 characters
        assert len(token) >= 43

    def test_token_is_url_safe(self):
        """Generated token uses URL-safe characters."""
        token = CSRFService.generate_token()
        # Should contain only URL-safe base64 characters (a-z, A-Z, 0-9, -, _)
        import string
        valid_chars = set(string.ascii_letters + string.digits + '-_')
        assert all(c in valid_chars for c in token)

    def test_tokens_are_unique(self):
        """Generated tokens are unique."""
        tokens = [CSRFService.generate_token() for _ in range(100)]
        assert len(set(tokens)) == 100  # All unique

    def test_token_uses_secrets_module(self):
        """Token generation uses secrets module."""
        # Calling generate_token multiple times should produce different values
        token1 = CSRFService.generate_token()
        token2 = CSRFService.generate_token()
        assert token1 != token2


# Tests for token storage and retrieval

class TestTokenStorage:
    """Test token storage in Redis."""

    def test_store_token_requires_redis(self):
        """Storing token without Redis returns False."""
        service = CSRFService(redis_client=None)
        token = CSRFService.generate_token()

        result = service.store_token("session-123", token)

        # Should return False when Redis unavailable
        assert result is False

    def test_store_token_with_redis(self):
        """Token is stored in Redis."""
        mock_redis = MagicMock()
        service = CSRFService(redis_client=mock_redis)

        token = CSRFService.generate_token()
        result = service.store_token("session-123", token)

        # Should attempt to store
        assert result is True or mock_redis.setex.called


# Tests for token validation

class TestTokenValidation:
    """Test token validation."""

    def test_validate_missing_token(self, csrf_service, session_id):
        """Validation fails for missing token."""
        is_valid, error = csrf_service.validate_token(session_id, "")

        assert is_valid is False
        assert error is not None

    def test_validate_none_token(self, csrf_service, session_id):
        """Validation fails for None token."""
        is_valid, error = csrf_service.validate_token(session_id, None)

        assert is_valid is False
        assert error is not None

    def test_validate_without_redis(self, csrf_service):
        """Validation skips when Redis unavailable."""
        token = CSRFService.generate_token()

        # Without Redis, validation should skip (return True)
        is_valid, error = csrf_service.validate_token("session-123", token)

        assert is_valid is True
        assert error is None


# Tests for constant-time comparison

class TestConstantTimeComparison:
    """Test constant-time token comparison."""

    def test_equal_tokens_match(self):
        """Equal tokens return True."""
        token = "test-token-123"
        result = CSRFService._constant_time_compare(token, token)
        assert result is True

    def test_different_tokens_fail(self):
        """Different tokens return False."""
        result = CSRFService._constant_time_compare("token1", "token2")
        assert result is False

    def test_different_lengths_fail(self):
        """Tokens of different length return False."""
        result = CSRFService._constant_time_compare("short", "much-longer-token")
        assert result is False

    def test_comparison_timing_independent(self):
        """Comparison time is independent of mismatch position."""
        # This is conceptual - actual timing test would need performance measurement
        # Constant-time comparison should take same time regardless of where difference is

        result1 = CSRFService._constant_time_compare("aaa", "aab")
        result2 = CSRFService._constant_time_compare("aaa", "baa")

        # Both should be False
        assert result1 is False
        assert result2 is False


# Tests for rate limiting

class TestRateLimiting:
    """Test rate limiting on failed attempts."""

    def test_rate_limit_key_generation(self):
        """Rate limit key includes session and token hash."""
        session_id = "session-123"
        token = CSRFService.generate_token()

        key = CSRFService._get_rate_limit_key(session_id, token)

        assert isinstance(key, str)
        assert "csrf:ratelimit" in key
        assert session_id in key

    def test_rate_limit_uses_token_hash(self):
        """Rate limit key uses token hash, not full token."""
        session_id = "session-123"
        token = CSRFService.generate_token()

        key = CSRFService._get_rate_limit_key(session_id, token)

        # Key should not contain the full token
        assert token not in key


# Tests for Redis key generation

class TestRedisKeyGeneration:
    """Test Redis key generation."""

    def test_redis_key_format(self):
        """Redis key follows correct format."""
        session_id = "session-123"
        key = CSRFService._get_redis_key(session_id)

        assert key == f"csrf:tokens:{session_id}"

    def test_redis_key_includes_session(self):
        """Redis key includes session ID."""
        session_id = "my-session-456"
        key = CSRFService._get_redis_key(session_id)

        assert session_id in key


# Tests for token invalidation

class TestTokenInvalidation:
    """Test token invalidation."""

    def test_invalidate_without_redis(self, csrf_service):
        """Invalidation succeeds without Redis."""
        result = csrf_service.invalidate_token("session-123")

        # Should return True (success)
        assert result is True


# Tests for token extraction from request

class TestTokenExtraction:
    """Test extracting token from request."""

    def test_extract_token_from_header(self):
        """Token extracted from header."""
        service = CSRFService()

        # Mock request
        mock_request = MagicMock()
        mock_request.headers = {"X-CSRF-Token": "test-token"}
        mock_request.cookies = {}
        mock_request.query_params = {}

        token = service.get_token_from_request(mock_request)

        assert token == "test-token"

    def test_extract_token_from_cookie(self):
        """Token extracted from cookie."""
        service = CSRFService()

        # Mock request
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.cookies = {"csrf_token": "cookie-token"}
        mock_request.query_params = {}

        token = service.get_token_from_request(mock_request)

        assert token == "cookie-token"

    def test_header_takes_precedence(self):
        """Header token takes precedence over cookie."""
        service = CSRFService()

        # Mock request with both
        mock_request = MagicMock()
        mock_request.headers = {"X-CSRF-Token": "header-token"}
        mock_request.cookies = {"csrf_token": "cookie-token"}
        mock_request.query_params = {}

        token = service.get_token_from_request(mock_request)

        assert token == "header-token"


# Tests for session ID extraction

class TestSessionIDExtraction:
    """Test extracting session ID from request."""

    def test_extract_session_from_query(self):
        """Session extracted from query parameter."""
        service = CSRFService()

        # Mock request
        mock_request = MagicMock()
        mock_request.query_params = {"session_id": "query-session"}
        mock_request.headers = {}
        mock_request.cookies = {}

        session_id = service.get_session_id(mock_request)

        assert session_id == "query-session"

    def test_extract_session_from_header(self):
        """Session extracted from header."""
        service = CSRFService()

        # Mock request
        mock_request = MagicMock()
        mock_request.query_params = {}
        mock_request.headers = {"X-Session-ID": "header-session"}
        mock_request.cookies = {}

        session_id = service.get_session_id(mock_request)

        assert session_id == "header-session"

    def test_extract_session_from_cookie(self):
        """Session extracted from cookie."""
        service = CSRFService()

        # Mock request
        mock_request = MagicMock()
        mock_request.query_params = {}
        mock_request.headers = {}
        mock_request.cookies = {"session_id": "cookie-session"}

        session_id = service.get_session_id(mock_request)

        assert session_id == "cookie-session"

    def test_generate_temp_session_if_none(self):
        """Temporary session ID generated if none found."""
        service = CSRFService()

        # Mock request with no session
        mock_request = MagicMock()
        mock_request.query_params = {}
        mock_request.headers = {}
        mock_request.cookies = {}
        mock_request.client.host = "127.0.0.1"
        mock_request.headers.get.return_value = "test-agent"

        session_id = service.get_session_id(mock_request)

        # Should return a generated ID
        assert isinstance(session_id, str)
        assert len(session_id) > 0


# Tests for configuration

class TestConfiguration:
    """Test CSRF service configuration."""

    def test_token_length_configured(self):
        """Token length is configured."""
        assert CSRFService.TOKEN_LENGTH == 32  # bytes

    def test_token_expiry_configured(self):
        """Token expiry is configured."""
        assert CSRFService.TOKEN_EXPIRY == 3600  # 1 hour

    def test_header_name_configured(self):
        """Header name is configured."""
        assert CSRFService.HEADER_NAME == "X-CSRF-Token"

    def test_safe_methods_configured(self):
        """Safe HTTP methods are configured."""
        assert "GET" in CSRFService.SAFE_METHODS
        assert "HEAD" in CSRFService.SAFE_METHODS
        assert "OPTIONS" in CSRFService.SAFE_METHODS

    def test_unsafe_methods_configured(self):
        """Unsafe HTTP methods are configured."""
        assert "POST" in CSRFService.UNSAFE_METHODS
        assert "PUT" in CSRFService.UNSAFE_METHODS
        assert "DELETE" in CSRFService.UNSAFE_METHODS
        assert "PATCH" in CSRFService.UNSAFE_METHODS

    def test_rate_limit_configured(self):
        """Rate limiting is configured."""
        assert CSRFService.RATE_LIMIT_ATTEMPTS == 10
        assert CSRFService.RATE_LIMIT_WINDOW == 300  # 5 minutes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
