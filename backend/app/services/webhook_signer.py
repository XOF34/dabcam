"""
Webhook Signature Verification Service.

HMAC-SHA256 signing for webhook security and replay protection.
"""

import logging
import hmac
import hashlib
import secrets
import time
from typing import Tuple

logger = logging.getLogger(__name__)

SIGNATURE_ALGORITHM = "sha256"
SIGNATURE_VERSION = "v1"
TIMESTAMP_TOLERANCE = 300  # 5 minutes


class WebhookSigner:
    """HMAC-SHA256 signing for webhook security."""

    @staticmethod
    def generate_secret(length: int = 32) -> str:
        """
        Generate a random webhook secret.

        Args:
            length: Length of secret in bytes (default: 32)

        Returns:
            Random hex-encoded secret string
        """
        return secrets.token_hex(length)

    @staticmethod
    def sign(payload: str, secret: str, timestamp: int = None) -> Tuple[str, int]:
        """
        Generate HMAC-SHA256 signature for webhook payload.

        Args:
            payload: JSON payload to sign
            secret: Webhook secret for HMAC
            timestamp: Unix timestamp (uses current time if None)

        Returns:
            Tuple of (signature_header, timestamp)
        """
        if timestamp is None:
            timestamp = int(time.time())

        # Create signing string: timestamp.payload
        signing_string = f"{timestamp}.{payload}"

        # Generate HMAC-SHA256
        signature = hmac.new(
            secret.encode('utf-8'),
            signing_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        # Format: v1,sha256=<hex>
        signature_header = f"{SIGNATURE_VERSION},{SIGNATURE_ALGORITHM}={signature}"

        logger.debug(
            f"Generated webhook signature for payload ({len(payload)} bytes) "
            f"with timestamp {timestamp}"
        )

        return signature_header, timestamp

    @staticmethod
    def verify(
        payload: str,
        signature_header: str,
        secret: str,
        timestamp_header: int,
        tolerance: int = TIMESTAMP_TOLERANCE
    ) -> bool:
        """
        Verify HMAC-SHA256 signature and timestamp.

        Args:
            payload: JSON payload (must match exactly what was signed)
            signature_header: Signature from X-Webhook-Signature header
            secret: Webhook secret for HMAC
            timestamp_header: Timestamp from X-Webhook-Timestamp header
            tolerance: Allowed time skew in seconds (default: 300)

        Returns:
            True if signature is valid and timestamp is recent, False otherwise
        """
        try:
            # Verify timestamp is recent (prevent replay attacks)
            current_time = int(time.time())
            time_diff = abs(current_time - timestamp_header)

            if time_diff > tolerance:
                logger.warning(
                    f"Webhook timestamp outside tolerance: "
                    f"received {timestamp_header}, current {current_time}, "
                    f"diff {time_diff}s (tolerance {tolerance}s)"
                )
                return False

            # Recreate signing string
            signing_string = f"{timestamp_header}.{payload}"

            # Generate expected signature
            expected_signature = hmac.new(
                secret.encode('utf-8'),
                signing_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            # Parse signature header: v1,sha256=<hex>
            if not signature_header.startswith(f"{SIGNATURE_VERSION},"):
                logger.warning(
                    f"Webhook signature version mismatch: {signature_header}"
                )
                return False

            parts = signature_header.split("=", 1)
            if len(parts) != 2:
                logger.warning(f"Invalid signature format: {signature_header}")
                return False

            algo_part, received_signature = parts[0].split(","), parts[1]
            algorithm = algo_part[1] if len(algo_part) > 1 else None

            if algorithm != SIGNATURE_ALGORITHM:
                logger.warning(
                    f"Webhook signature algorithm mismatch: "
                    f"expected {SIGNATURE_ALGORITHM}, got {algorithm}"
                )
                return False

            # Constant-time comparison to prevent timing attacks
            is_valid = hmac.compare_digest(expected_signature, received_signature)

            if is_valid:
                logger.debug("Webhook signature verified successfully")
            else:
                logger.warning(
                    f"Webhook signature verification failed: "
                    f"expected {expected_signature[:16]}..., "
                    f"got {received_signature[:16]}..."
                )

            return is_valid

        except Exception as e:
            logger.exception(f"Error verifying webhook signature: {e}")
            return False

    @staticmethod
    def create_headers(
        payload: str,
        secret: str,
        event_id: str,
        event_type: str
    ) -> dict:
        """
        Create all webhook headers for HTTP request.

        Args:
            payload: JSON payload
            secret: Webhook secret
            event_id: Event identifier
            event_type: Type of event

        Returns:
            Dictionary of HTTP headers
        """
        signature, timestamp = WebhookSigner.sign(payload, secret)

        return {
            "Content-Type": "application/json",
            "X-Webhook-Event": event_type,
            "X-Webhook-ID": event_id,
            "X-Webhook-Signature": signature,
            "X-Webhook-Timestamp": str(timestamp),
            "User-Agent": "Dabcam/2.0 (+https://github.com/XOF34/dabcam)"
        }
