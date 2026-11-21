"""
Tests for Webhook Signer Service.

Tests HMAC-SHA256 signature generation, verification, and replay protection.
"""

import pytest
import time
import json
from app.services.webhook_signer import WebhookSigner


class TestWebhookSecretGeneration:
    """Test webhook secret generation."""

    def test_generate_secret_default_length(self):
        """Test generating secret with default length."""
        secret = WebhookSigner.generate_secret()
        assert secret is not None
        assert len(secret) == 64  # 32 bytes in hex = 64 chars
        assert isinstance(secret, str)

    def test_generate_secret_custom_length(self):
        """Test generating secret with custom length."""
        secret = WebhookSigner.generate_secret(length=16)
        assert len(secret) == 32  # 16 bytes in hex = 32 chars

    def test_generate_secret_uniqueness(self):
        """Test that generated secrets are unique."""
        secrets = [WebhookSigner.generate_secret() for _ in range(10)]
        assert len(set(secrets)) == 10  # All unique

    def test_secret_is_hex_encoded(self):
        """Test that secret is valid hex string."""
        secret = WebhookSigner.generate_secret()
        try:
            int(secret, 16)
        except ValueError:
            pytest.fail(f"Secret is not valid hex: {secret}")


class TestWebhookSignature:
    """Test webhook signature generation."""

    def test_sign_generates_signature(self):
        """Test that signing generates valid signature."""
        payload = json.dumps({"event": "test"})
        secret = "test-secret-12345"

        signature, timestamp = WebhookSigner.sign(payload, secret)

        assert signature is not None
        assert timestamp is not None
        assert isinstance(signature, str)
        assert isinstance(timestamp, int)
        assert signature.startswith("v1,sha256=")

    def test_sign_includes_version_and_algorithm(self):
        """Test that signature includes version and algorithm."""
        payload = json.dumps({"event": "test"})
        secret = "test-secret-12345"

        signature, _ = WebhookSigner.sign(payload, secret)

        assert "v1" in signature
        assert "sha256" in signature

    def test_sign_deterministic(self):
        """Test that signing same payload produces same signature."""
        payload = json.dumps({"event": "test"})
        secret = "test-secret-12345"
        fixed_timestamp = 1700000000

        sig1, _ = WebhookSigner.sign(payload, secret, fixed_timestamp)
        sig2, _ = WebhookSigner.sign(payload, secret, fixed_timestamp)

        assert sig1 == sig2

    def test_sign_different_payloads_different_signatures(self):
        """Test that different payloads produce different signatures."""
        secret = "test-secret-12345"
        fixed_timestamp = 1700000000

        sig1, _ = WebhookSigner.sign(
            json.dumps({"event": "test1"}), secret, fixed_timestamp
        )
        sig2, _ = WebhookSigner.sign(
            json.dumps({"event": "test2"}), secret, fixed_timestamp
        )

        assert sig1 != sig2

    def test_sign_different_secrets_different_signatures(self):
        """Test that different secrets produce different signatures."""
        payload = json.dumps({"event": "test"})
        fixed_timestamp = 1700000000

        sig1, _ = WebhookSigner.sign(payload, "secret1", fixed_timestamp)
        sig2, _ = WebhookSigner.sign(payload, "secret2", fixed_timestamp)

        assert sig1 != sig2


class TestWebhookVerification:
    """Test webhook signature verification."""

    def test_verify_valid_signature(self):
        """Test verifying valid signature."""
        payload = json.dumps({"event": "test"})
        secret = "test-secret-12345"

        signature, timestamp = WebhookSigner.sign(payload, secret)

        is_valid = WebhookSigner.verify(payload, signature, secret, timestamp)
        assert is_valid is True

    def test_verify_invalid_signature(self):
        """Test verifying tampered signature."""
        payload = json.dumps({"event": "test"})
        secret = "test-secret-12345"

        signature, timestamp = WebhookSigner.sign(payload, secret)
        tampered_signature = "v1,sha256=0000000000000000"

        is_valid = WebhookSigner.verify(
            payload, tampered_signature, secret, timestamp
        )
        assert is_valid is False

    def test_verify_tampered_payload(self):
        """Test that tampered payload fails verification."""
        payload = json.dumps({"event": "test"})
        secret = "test-secret-12345"

        signature, timestamp = WebhookSigner.sign(payload, secret)
        tampered_payload = json.dumps({"event": "tampered"})

        is_valid = WebhookSigner.verify(
            tampered_payload, signature, secret, timestamp
        )
        assert is_valid is False

    def test_verify_wrong_secret(self):
        """Test that wrong secret fails verification."""
        payload = json.dumps({"event": "test"})
        secret1 = "secret1"
        secret2 = "secret2"

        signature, timestamp = WebhookSigner.sign(payload, secret1)

        is_valid = WebhookSigner.verify(payload, signature, secret2, timestamp)
        assert is_valid is False

    def test_verify_old_timestamp_rejected(self):
        """Test that old timestamps are rejected."""
        payload = json.dumps({"event": "test"})
        secret = "test-secret-12345"

        # Use timestamp from 10 minutes ago
        old_timestamp = int(time.time()) - 600

        signature, _ = WebhookSigner.sign(payload, secret, old_timestamp)

        is_valid = WebhookSigner.verify(
            payload, signature, secret, old_timestamp, tolerance=300
        )
        assert is_valid is False

    def test_verify_future_timestamp_rejected(self):
        """Test that future timestamps are rejected."""
        payload = json.dumps({"event": "test"})
        secret = "test-secret-12345"

        # Use timestamp from 10 minutes in future
        future_timestamp = int(time.time()) + 600

        signature, _ = WebhookSigner.sign(payload, secret, future_timestamp)

        is_valid = WebhookSigner.verify(
            payload, signature, secret, future_timestamp, tolerance=300
        )
        assert is_valid is False

    def test_verify_timestamp_tolerance(self):
        """Test that timestamps within tolerance are accepted."""
        payload = json.dumps({"event": "test"})
        secret = "test-secret-12345"

        # Use timestamp from 4 minutes ago (within 5 minute tolerance)
        recent_timestamp = int(time.time()) - 240

        signature, _ = WebhookSigner.sign(payload, secret, recent_timestamp)

        is_valid = WebhookSigner.verify(
            payload, signature, secret, recent_timestamp, tolerance=300
        )
        assert is_valid is True

    def test_verify_invalid_signature_format(self):
        """Test that invalid signature format is rejected."""
        payload = json.dumps({"event": "test"})
        secret = "test-secret-12345"
        timestamp = int(time.time())

        # Test various invalid formats
        invalid_signatures = [
            "invalid",
            "v2,sha256=abc",  # Wrong version
            "v1,md5=abc",  # Wrong algorithm
            "v1=abc",  # Wrong format
        ]

        for invalid_sig in invalid_signatures:
            is_valid = WebhookSigner.verify(
                payload, invalid_sig, secret, timestamp
            )
            assert is_valid is False


class TestWebhookHeaders:
    """Test webhook header generation."""

    def test_create_headers_generates_all_required_headers(self):
        """Test that all required headers are generated."""
        payload = json.dumps({"event": "test"})
        secret = "test-secret-12345"
        event_id = "evt_12345"
        event_type = "exploitation.success"

        headers = WebhookSigner.create_headers(payload, secret, event_id, event_type)

        assert "Content-Type" in headers
        assert "X-Webhook-Event" in headers
        assert "X-Webhook-ID" in headers
        assert "X-Webhook-Signature" in headers
        assert "X-Webhook-Timestamp" in headers
        assert "User-Agent" in headers

    def test_create_headers_correct_values(self):
        """Test that headers have correct values."""
        payload = json.dumps({"event": "test"})
        secret = "test-secret-12345"
        event_id = "evt_12345"
        event_type = "exploitation.success"

        headers = WebhookSigner.create_headers(payload, secret, event_id, event_type)

        assert headers["Content-Type"] == "application/json"
        assert headers["X-Webhook-Event"] == event_type
        assert headers["X-Webhook-ID"] == event_id
        assert headers["X-Webhook-Signature"].startswith("v1,sha256=")
        assert headers["User-Agent"].startswith("Dabcam/")

    def test_create_headers_signature_is_verifiable(self):
        """Test that generated signature can be verified."""
        payload = json.dumps({"event": "test"})
        secret = "test-secret-12345"
        event_id = "evt_12345"
        event_type = "exploitation.success"

        headers = WebhookSigner.create_headers(payload, secret, event_id, event_type)

        # Verify the signature
        is_valid = WebhookSigner.verify(
            payload,
            headers["X-Webhook-Signature"],
            secret,
            int(headers["X-Webhook-Timestamp"])
        )
        assert is_valid is True


class TestReplayProtection:
    """Test replay attack protection."""

    def test_replay_attack_prevented(self):
        """Test that replay attack with old timestamp is rejected."""
        payload = json.dumps({"event": "test"})
        secret = "test-secret-12345"

        # Sign with timestamp from past
        past_timestamp = int(time.time()) - 1000
        signature, _ = WebhookSigner.sign(payload, secret, past_timestamp)

        # Try to replay
        is_valid = WebhookSigner.verify(
            payload, signature, secret, past_timestamp, tolerance=300
        )
        assert is_valid is False

    def test_signature_includes_timestamp_in_signing(self):
        """Test that timestamps are included in signature calculation."""
        payload = json.dumps({"event": "test"})
        secret = "test-secret-12345"

        # Sign same payload with different timestamps
        ts1 = 1700000000
        ts2 = 1700000001

        sig1, _ = WebhookSigner.sign(payload, secret, ts1)
        sig2, _ = WebhookSigner.sign(payload, secret, ts2)

        # Signatures should be different due to timestamp
        assert sig1 != sig2
