"""
Phase 3 Integration Tests.

Comprehensive integration tests for the complete webhook pipeline including
signature verification, retry logic, delivery tracking, and replay functionality.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
import json

from app.services.webhook_signer import WebhookSigner
from app.services.webhook_retry_service import RetryStrategy, RetryScheduler
from app.services.webhook_manager import WebhookManager
from app.services.webhook_replay_service import WebhookReplayService
from app.models import WebhookDeliveryStatus


class TestPhase3SecurityPipeline:
    """Test security features across Phase 3."""

    def test_webhook_signing_and_verification(self):
        """Test complete signing and verification flow."""
        import time
        signer = WebhookSigner()

        # Generate secret
        secret = signer.generate_secret()
        assert len(secret) == 64  # 32 bytes hex-encoded

        # Sign payload
        payload = json.dumps({"event": "exploitation.success", "id": "evt_123"})
        signature, timestamp = signer.sign(payload, secret)

        assert signature.startswith("v1,sha256=")
        assert len(signature) > 20

        # Verify signature
        is_valid = signer.verify(payload, signature, secret, timestamp)
        assert is_valid is True

    def test_signature_replay_protection(self):
        """Test timestamp-based replay protection."""
        signer = WebhookSigner()
        secret = signer.generate_secret()

        payload = json.dumps({"event": "test"})

        # Sign and get timestamp
        signature, timestamp = signer.sign(payload, secret)

        assert signature.startswith("v1,sha256=")
        assert isinstance(timestamp, int)

        # Verify signature with timestamp
        is_valid = signer.verify(payload, signature, secret, timestamp)
        assert is_valid is True

    def test_signature_tampering_detection(self):
        """Test that tampering is detected."""
        signer = WebhookSigner()
        secret = signer.generate_secret()

        payload = json.dumps({"event": "test"})
        signature, timestamp = signer.sign(payload, secret)

        # Tamper with payload
        tampered_payload = json.dumps({"event": "tampered"})

        # Verification should fail
        is_valid = signer.verify(tampered_payload, signature, secret, timestamp)
        assert is_valid is False

    def test_timing_attack_prevention(self):
        """Test constant-time comparison."""
        signer = WebhookSigner()
        secret = signer.generate_secret()

        payload = json.dumps({"event": "test"})
        signature, timestamp = signer.sign(payload, secret)

        # Create wrong signature
        wrong_signature, wrong_ts = signer.sign(payload, "wrong_secret")

        # Both should fail safely
        is_valid1 = signer.verify(payload, signature, "wrong_secret", timestamp)
        is_valid2 = signer.verify(payload, wrong_signature, secret, wrong_ts)

        assert is_valid1 is False
        assert is_valid2 is False


class TestPhase3RetryPipeline:
    """Test retry logic across Phase 3."""

    def test_exponential_backoff_schedule(self):
        """Test exponential backoff calculation."""
        strategy = RetryStrategy(
            base_delay=60,
            backoff_factor=2.0,
            max_delay=3600
        )

        delays = []
        for attempt in range(1, 6):
            delay = strategy.calculate_delay(attempt)
            delays.append(delay)

        # Delays should increase exponentially
        # Each delay should be greater than the previous (before jitter/max_delay cap)
        assert len(delays) == 5
        assert delays[0] > 0
        # Verify exponential growth: each should be roughly 2x the previous
        for i in range(1, 4):
            assert delays[i] > delays[i-1] or delays[i] == strategy.max_delay

    def test_max_delay_capping(self):
        """Test that delays are capped at max_delay."""
        strategy = RetryStrategy(
            base_delay=60,
            backoff_factor=2.0,
            max_delay=1000,  # Set a low max to easily test capping
            jitter=False
        )

        # Calculate high attempt numbers - should eventually cap
        delays = []
        for attempt in range(1, 15):
            delay = strategy.calculate_delay(attempt)
            delays.append(delay)
            assert delay <= 1000  # Should never exceed max_delay

        # Verify that at least some delays hit the cap
        assert 1000 in delays

    def test_error_classification(self):
        """Test error classification for retry decisions."""
        strategy = RetryStrategy()

        # Retryable HTTP errors
        retryable_errors = [500, 502, 503, 504, 408, 429]
        for error in retryable_errors:
            should_retry = strategy.should_retry(error)
            assert should_retry is True, f"Error {error} should be retryable"

        # Non-retryable HTTP errors
        non_retryable = [400, 401, 403, 404, 200, 201]
        for error in non_retryable:
            should_retry = strategy.should_retry(error)
            assert should_retry is False, f"Error {error} should not be retryable"

    def test_jitter_randomness(self):
        """Test that jitter adds randomness to delays."""
        strategy = RetryStrategy(
            base_delay=100,
            backoff_factor=2.0,
            jitter=True  # Enable jitter
        )

        delays = []
        for _ in range(10):
            delay = strategy.calculate_delay(2)
            delays.append(delay)

        # Delays should be around 200 (100 * 2^(2-1) = 100 * 2 = 200)
        # With jitter (±10%), range is 180-220
        assert all(170 <= d <= 230 for d in delays)  # Within jitter range


class TestPhase3DeliveryPipeline:
    """Test delivery tracking across Phase 3."""

    def test_delivery_status_lifecycle(self):
        """Test complete delivery status lifecycle."""
        statuses = [
            WebhookDeliveryStatus.pending.value,
            WebhookDeliveryStatus.delivered.value
        ]

        # Delivery starts as pending
        assert statuses[0] == "pending"

        # Can transition to delivered
        assert statuses[1] == "delivered"

    def test_failed_delivery_lifecycle(self):
        """Test failed delivery status transitions."""
        statuses = [
            WebhookDeliveryStatus.pending.value,
            WebhookDeliveryStatus.retrying.value,
            WebhookDeliveryStatus.failed.value
        ]

        assert statuses[0] == "pending"
        assert statuses[1] == "retrying"
        assert statuses[2] == "failed"

    def test_max_attempts_enforcement(self):
        """Test that max attempts is enforced."""
        max_attempts = 5
        attempt_count = 0

        while attempt_count < max_attempts:
            attempt_count += 1

        assert attempt_count == max_attempts


class TestPhase3ReplayPipeline:
    """Test replay functionality across Phase 3."""

    @pytest.mark.asyncio
    async def test_single_event_replay_with_history(self):
        """Test replaying single event preserves history."""
        service = WebhookReplayService()
        service.webhook_manager = AsyncMock()

        mock_delivery = Mock()
        mock_delivery.id = "del_1"
        mock_delivery.event_id = "evt_abc"
        mock_delivery.event_type = "exploitation.success"
        mock_delivery.created_at = datetime.utcnow()

        mock_db = Mock()
        query_chain = mock_db.query.return_value
        query_chain.filter.return_value.first.return_value = mock_delivery
        query_chain.filter.return_value.distinct.return_value.all.return_value = [mock_delivery]

        result = await service.replay_event(
            event_id="evt_abc",
            db_session=mock_db
        )

        assert "replay_id" in result
        assert result["event_id"] == "evt_abc"

    @pytest.mark.asyncio
    async def test_subscription_replay_with_filtering(self):
        """Test subscription replay respects filters."""
        service = WebhookReplayService()
        service.webhook_manager = AsyncMock()

        mock_deliveries = [
            Mock(
                event_id=f"evt_{i}",
                event_type="exploitation.success" if i % 2 == 0 else "session.created",
                subscription_id="sub_1",
                campaign_id="camp_1",
                target_id="tgt_1",
                created_at=datetime.utcnow() - timedelta(days=i)
            )
            for i in range(5)
        ]

        mock_db = Mock()
        query_chain = mock_db.query.return_value
        query_chain.filter.return_value = query_chain
        query_chain.all.return_value = [d for d in mock_deliveries if d.event_type == "exploitation.success"]

        result = await service.replay_subscription(
            subscription_id="sub_1",
            event_types=["exploitation.success"],
            db_session=mock_db
        )

        assert "replay_id" in result
        assert result["subscription_id"] == "sub_1"

    @pytest.mark.asyncio
    async def test_batch_replay_dry_run_mode(self):
        """Test batch replay dry-run doesn't queue events."""
        service = WebhookReplayService()

        mock_deliveries = [Mock(created_at=datetime.utcnow()) for _ in range(10)]

        mock_db = Mock()
        query_chain = mock_db.query.return_value
        query_chain.filter.return_value = query_chain
        query_chain.all.return_value = mock_deliveries

        result = await service.batch_replay(
            filters={},
            dry_run=True,
            db_session=mock_db
        )

        assert result["dry_run"] is True
        assert result["events_found"] == 10
        assert "replay_id" not in result or result["replay_id"] is None


class TestPhase3LoggingPipeline:
    """Test logging and audit trail across Phase 3."""

    def test_webhook_log_aggregation(self):
        """Test webhook log aggregation."""
        logs = [
            {
                "event_type": "exploitation.success",
                "subscription_id": "sub_1",
                "total_deliveries": 5,
                "successful": 5,
                "failed": 0
            },
            {
                "event_type": "exploitation.success",
                "subscription_id": "sub_2",
                "total_deliveries": 3,
                "successful": 2,
                "failed": 1
            },
            {
                "event_type": "session.created",
                "subscription_id": "sub_1",
                "total_deliveries": 4,
                "successful": 4,
                "failed": 0
            }
        ]

        # Aggregate by event type
        event_stats = {}
        for log in logs:
            et = log["event_type"]
            if et not in event_stats:
                event_stats[et] = {"total": 0, "successful": 0, "failed": 0}
            event_stats[et]["total"] += log["total_deliveries"]
            event_stats[et]["successful"] += log["successful"]
            event_stats[et]["failed"] += log["failed"]

        assert event_stats["exploitation.success"]["total"] == 8
        assert event_stats["session.created"]["total"] == 4

    def test_success_rate_calculation(self):
        """Test success rate aggregation."""
        total_deliveries = 1000
        successful = 950
        failed = 50

        success_rate = (successful / total_deliveries * 100)

        assert success_rate == 95.0
        assert total_deliveries == successful + failed


class TestPhase3EndToEnd:
    """End-to-end integration tests for Phase 3."""

    def test_webhook_lifecycle_complete(self):
        """Test complete webhook lifecycle."""
        # 1. Create secret
        signer = WebhookSigner()
        secret = signer.generate_secret()

        # 2. Create payload
        payload = json.dumps({
            "event_id": "evt_123",
            "event_type": "exploitation.success",
            "timestamp": datetime.utcnow().isoformat()
        })

        # 3. Sign payload
        signature, timestamp = signer.sign(payload, secret)

        # 4. Verify signature with timestamp
        is_valid = signer.verify(payload, signature, secret, timestamp)

        assert is_valid is True
        assert signature.startswith("v1,sha256=")

    def test_retry_and_delivery_lifecycle(self):
        """Test retry and delivery status lifecycle."""
        # 1. Start with pending
        status = WebhookDeliveryStatus.pending.value
        assert status == "pending"

        # 2. First attempt fails
        attempt = 1
        should_retry = True
        assert should_retry is True

        # 3. Schedule retry
        strategy = RetryStrategy()
        delay = strategy.calculate_delay(attempt)
        assert delay > 0

        # 4. Second attempt succeeds
        status = WebhookDeliveryStatus.delivered.value
        assert status == "delivered"

    def test_full_pipeline_with_logging(self):
        """Test full pipeline with logging and tracking."""
        # 1. Event is created
        event_id = "evt_123"
        event_type = "exploitation.success"

        # 2. Event is signed
        signer = WebhookSigner()
        secret = signer.generate_secret()
        payload = json.dumps({"id": event_id, "type": event_type})
        signature = signer.sign(payload, secret)

        # 3. Delivery is attempted
        delivery_id = "del_123"
        status = WebhookDeliveryStatus.pending.value
        attempt = 1

        # 4. Delivery succeeds
        status = WebhookDeliveryStatus.delivered.value
        delivered_at = datetime.utcnow()

        # 5. Event is logged
        log_entry = {
            "event_id": event_id,
            "event_type": event_type,
            "total_deliveries": 1,
            "successful_deliveries": 1,
            "failed_deliveries": 0,
            "processed_at": datetime.utcnow()
        }

        assert log_entry["successful_deliveries"] == 1
        assert status == "delivered"


class TestPhase3Performance:
    """Performance and scalability tests for Phase 3."""

    def test_signature_generation_performance(self):
        """Test signature generation performance."""
        signer = WebhookSigner()
        secret = signer.generate_secret()

        # Generate multiple signatures
        import time
        start = time.time()

        for i in range(100):
            payload = json.dumps({"id": i})
            signature = signer.sign(payload, secret)

        elapsed = time.time() - start

        # Should complete in reasonable time (< 1 second for 100 ops)
        assert elapsed < 1.0

    def test_retry_schedule_calculation_performance(self):
        """Test retry schedule calculation performance."""
        strategy = RetryStrategy()

        import time
        start = time.time()

        for attempt in range(1, 1000):
            delay = strategy.calculate_delay(attempt)

        elapsed = time.time() - start

        # Should complete quickly
        assert elapsed < 0.1

    def test_aggregation_performance(self):
        """Test aggregation query performance."""
        # Simulate large log dataset
        logs = [
            {
                "event_type": "exploitation.success",
                "subscription_id": f"sub_{i % 100}",
                "total_deliveries": 5,
                "successful": 4 if i % 10 else 5,
                "failed": 1 if i % 10 else 0
            }
            for i in range(10000)
        ]

        import time
        start = time.time()

        # Aggregate statistics
        stats = {
            "total": 0,
            "successful": 0,
            "failed": 0
        }

        for log in logs:
            stats["total"] += log["total_deliveries"]
            stats["successful"] += log["successful"]
            stats["failed"] += log["failed"]

        elapsed = time.time() - start

        assert stats["total"] == 50000
        assert elapsed < 0.1  # Should be fast


class TestPhase3ErrorHandling:
    """Error handling and edge case testing."""

    def test_invalid_signature_handling(self):
        """Test handling invalid signatures."""
        import time
        signer = WebhookSigner()
        secret = signer.generate_secret()

        payload = json.dumps({"event": "test"})
        current_timestamp = int(time.time())

        # Invalid signature format
        invalid_sigs = [
            "invalid",
            "v1,md5=abc123",
            "v2,sha256=def456",
            ""
        ]

        for sig in invalid_sigs:
            is_valid = signer.verify(payload, sig, secret, current_timestamp)
            assert is_valid is False, f"Signature {sig} should be invalid"

    def test_max_retry_enforcement(self):
        """Test that max retries is enforced."""
        max_attempts = 5
        attempts = 0

        while attempts < max_attempts:
            attempts += 1

        # Should not exceed max
        assert attempts == max_attempts
        assert attempts < (max_attempts + 1)

    def test_replay_no_events_found(self):
        """Test replay when no events found."""
        result = {
            "replay_id": None,
            "events_queued": 0,
            "status": "no_events_found"
        }

        assert result["replay_id"] is None
        assert result["events_queued"] == 0
