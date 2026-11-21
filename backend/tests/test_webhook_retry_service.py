"""
Tests for Webhook Retry Service.

Tests exponential backoff, retry scheduling, and retry strategy logic.
"""

import pytest
from datetime import datetime, timedelta
from app.services.webhook_retry_service import (
    RetryStrategy,
    RetryScheduler,
    get_retry_scheduler,
    DEFAULT_RETRY_STRATEGY
)


class TestRetryStrategy:
    """Test retry strategy configuration and calculations."""

    def test_strategy_initialization(self):
        """Test retry strategy initialization."""
        strategy = RetryStrategy(
            max_attempts=5,
            base_delay=60,
            max_delay=3600,
            backoff_factor=2.0,
            jitter=True
        )

        assert strategy.max_attempts == 5
        assert strategy.base_delay == 60
        assert strategy.max_delay == 3600
        assert strategy.backoff_factor == 2.0
        assert strategy.jitter is True

    def test_default_strategy_values(self):
        """Test default retry strategy values."""
        strategy = RetryStrategy()

        assert strategy.max_attempts == 5
        assert strategy.base_delay == 60
        assert strategy.max_delay == 3600
        assert strategy.backoff_factor == 2.0
        assert strategy.jitter is True


class TestExponentialBackoff:
    """Test exponential backoff calculation."""

    def test_delay_calculation_first_attempt(self):
        """Test delay for first attempt."""
        strategy = RetryStrategy(
            base_delay=60, backoff_factor=2.0, jitter=False
        )

        # First attempt should return 0 delay
        delay = strategy.calculate_delay(0)
        assert delay == 0

    def test_delay_calculation_exponential(self):
        """Test exponential delay calculation."""
        strategy = RetryStrategy(
            base_delay=60, backoff_factor=2.0, jitter=False
        )

        # Attempt 1: 60s
        delay1 = strategy.calculate_delay(1)
        assert delay1 == 60

        # Attempt 2: 60 * 2^(2-1) = 120s
        delay2 = strategy.calculate_delay(2)
        assert delay2 == 120

        # Attempt 3: 60 * 2^(3-1) = 240s
        delay3 = strategy.calculate_delay(3)
        assert delay3 == 240

        # Attempt 4: 60 * 2^(4-1) = 480s
        delay4 = strategy.calculate_delay(4)
        assert delay4 == 480

        # Attempt 5: 60 * 2^(5-1) = 960s
        delay5 = strategy.calculate_delay(5)
        assert delay5 == 960

    def test_delay_capped_at_max(self):
        """Test that delay is capped at max_delay."""
        strategy = RetryStrategy(
            base_delay=60, backoff_factor=2.0, max_delay=300, jitter=False
        )

        # Attempt 5 would be 960s, but capped at 300s
        delay = strategy.calculate_delay(5)
        assert delay == 300

    def test_delay_with_jitter(self):
        """Test that jitter adds variance to delay."""
        strategy = RetryStrategy(
            base_delay=60, backoff_factor=2.0, jitter=True
        )

        # Get multiple delays for same attempt
        delays = [strategy.calculate_delay(3) for _ in range(10)]

        # All should be around 240s (±10%)
        assert min(delays) > 200  # At least 240 * 0.9
        assert max(delays) < 280  # At most 240 * 1.1

        # Should have variance
        assert len(set(delays)) > 1

    def test_delay_without_jitter(self):
        """Test that delay without jitter is deterministic."""
        strategy = RetryStrategy(
            base_delay=60, backoff_factor=2.0, jitter=False
        )

        delays = [strategy.calculate_delay(3) for _ in range(5)]

        # All should be exactly 240s
        assert all(d == 240 for d in delays)


class TestRetryTiming:
    """Test retry timing calculations."""

    def test_get_next_retry_time_success(self):
        """Test calculating next retry time."""
        strategy = RetryStrategy(base_delay=60, jitter=False)
        base_time = datetime(2026, 11, 21, 10, 0, 0)

        # After 1 attempt, should retry in 60s
        next_retry = strategy.get_next_retry_time(1, base_time)
        expected = base_time + timedelta(seconds=60)

        assert next_retry == expected

    def test_get_next_retry_time_max_attempts(self):
        """Test that None is returned when max attempts reached."""
        strategy = RetryStrategy(max_attempts=3, jitter=False)

        # After max attempts, should return None
        next_retry = strategy.get_next_retry_time(3)

        assert next_retry is None

    def test_get_next_retry_time_uses_current_time(self):
        """Test that current time is used if not provided."""
        strategy = RetryStrategy(base_delay=60, jitter=False)

        # Should use current time
        next_retry = strategy.get_next_retry_time(1)

        assert next_retry is not None
        assert next_retry > datetime.utcnow()


class TestRetryableErrors:
    """Test classification of retryable vs permanent errors."""

    def test_network_error_is_retryable(self):
        """Test that network errors are retryable."""
        strategy = RetryStrategy()

        # None status indicates network error
        is_retryable = strategy.should_retry(None, "Connection timeout")

        assert is_retryable is True

    def test_5xx_error_is_retryable(self):
        """Test that 5xx errors are retryable."""
        strategy = RetryStrategy()

        for status in [500, 502, 503, 504]:
            is_retryable = strategy.should_retry(status)
            assert is_retryable is True

    def test_408_timeout_is_retryable(self):
        """Test that 408 Timeout is retryable."""
        strategy = RetryStrategy()

        is_retryable = strategy.should_retry(408)

        assert is_retryable is True

    def test_429_rate_limit_is_retryable(self):
        """Test that 429 Rate Limit is retryable."""
        strategy = RetryStrategy()

        is_retryable = strategy.should_retry(429)

        assert is_retryable is True

    def test_4xx_error_not_retryable(self):
        """Test that 4xx errors (except 408, 429) are not retryable."""
        strategy = RetryStrategy()

        for status in [400, 401, 403, 404, 418, 422]:
            is_retryable = strategy.should_retry(status)
            assert is_retryable is False

    def test_2xx_success_not_retryable(self):
        """Test that 2xx responses don't need retry."""
        strategy = RetryStrategy()

        for status in [200, 201, 202, 204]:
            is_retryable = strategy.should_retry(status)
            assert is_retryable is False

    def test_3xx_redirect_not_retryable(self):
        """Test that 3xx redirects don't need retry."""
        strategy = RetryStrategy()

        for status in [300, 301, 302, 304]:
            is_retryable = strategy.should_retry(status)
            assert is_retryable is False


class TestRetryScheduler:
    """Test retry scheduler functionality."""

    def test_scheduler_initialization(self):
        """Test retry scheduler initialization."""
        scheduler = RetryScheduler()

        assert scheduler.strategy is not None
        assert scheduler.pending_retries == {}

    def test_schedule_retry_success(self):
        """Test scheduling a retry."""
        scheduler = RetryScheduler(
            RetryStrategy(base_delay=60, jitter=False)
        )

        success = scheduler.schedule_retry("delivery_1", 1, "Connection timeout")

        assert success is True
        assert "delivery_1" in scheduler.pending_retries

    def test_schedule_retry_max_attempts_exceeded(self):
        """Test that retry is not scheduled after max attempts."""
        scheduler = RetryScheduler(
            RetryStrategy(max_attempts=3, jitter=False)
        )

        # Try to schedule after max attempts
        success = scheduler.schedule_retry("delivery_1", 3, "Failed")

        assert success is False
        assert "delivery_1" not in scheduler.pending_retries

    def test_get_pending_retries(self):
        """Test getting retries ready to execute."""
        strategy = RetryStrategy(base_delay=1, jitter=False)
        scheduler = RetryScheduler(strategy)

        # Schedule retry in past (should be ready)
        base_time = datetime.utcnow() - timedelta(seconds=10)
        scheduler.pending_retries["delivery_1"] = {
            "next_retry": base_time,
            "attempt_count": 1,
            "last_error": "timeout"
        }

        # Schedule retry in future (should not be ready)
        scheduler.pending_retries["delivery_2"] = {
            "next_retry": datetime.utcnow() + timedelta(seconds=100),
            "attempt_count": 1,
            "last_error": "timeout"
        }

        ready = scheduler.get_pending_retries()

        assert len(ready) == 1
        assert "delivery_1" in ready
        assert "delivery_2" not in ready

    def test_cancel_retry(self):
        """Test cancelling a pending retry."""
        scheduler = RetryScheduler()
        scheduler.pending_retries["delivery_1"] = {
            "next_retry": datetime.utcnow(),
            "attempt_count": 1,
            "last_error": "timeout"
        }

        success = scheduler.cancel_retry("delivery_1")

        assert success is True
        assert "delivery_1" not in scheduler.pending_retries

    def test_cancel_nonexistent_retry(self):
        """Test cancelling nonexistent retry returns False."""
        scheduler = RetryScheduler()

        success = scheduler.cancel_retry("nonexistent")

        assert success is False

    def test_get_pending_count(self):
        """Test getting count of pending retries."""
        scheduler = RetryScheduler()

        scheduler.pending_retries["delivery_1"] = {
            "next_retry": datetime.utcnow(),
            "attempt_count": 1,
            "last_error": "timeout"
        }
        scheduler.pending_retries["delivery_2"] = {
            "next_retry": datetime.utcnow(),
            "attempt_count": 1,
            "last_error": "timeout"
        }

        assert scheduler.get_pending_count() == 2


class TestRetryGlobalScheduler:
    """Test global retry scheduler singleton."""

    def test_get_retry_scheduler_returns_instance(self):
        """Test that get_retry_scheduler returns a scheduler instance."""
        scheduler = get_retry_scheduler()

        assert scheduler is not None
        assert isinstance(scheduler, RetryScheduler)

    def test_get_retry_scheduler_singleton(self):
        """Test that scheduler is singleton."""
        scheduler1 = get_retry_scheduler()
        scheduler2 = get_retry_scheduler()

        assert scheduler1 is scheduler2


class TestRetryStrategySummary:
    """Test retry summary generation."""

    def test_get_retry_summary(self):
        """Test generating retry summary."""
        strategy = RetryStrategy(max_attempts=5)

        summary = strategy.get_retry_summary(2, "Connection timeout")

        assert "2/5" in summary
        assert "40%" in summary
        assert "3 remaining" in summary
        assert "Connection timeout" in summary
