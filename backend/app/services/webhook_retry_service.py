"""
Webhook Retry Service with Exponential Backoff.

Handles retry scheduling and exponential backoff for failed webhook deliveries.
"""

import logging
import random
import math
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class RetryStrategy:
    """Exponential backoff retry configuration."""

    def __init__(
        self,
        max_attempts: int = 5,
        base_delay: int = 60,
        max_delay: int = 3600,
        backoff_factor: float = 2.0,
        jitter: bool = True
    ):
        """
        Initialize retry strategy.

        Args:
            max_attempts: Maximum number of retry attempts (default: 5)
            base_delay: Initial delay in seconds (default: 60)
            max_delay: Maximum delay in seconds (default: 3600)
            backoff_factor: Exponential multiplier (default: 2.0)
            jitter: Add randomness to delay (default: True)
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter

        logger.info(
            f"🔄 Retry strategy configured: "
            f"max_attempts={max_attempts}, base_delay={base_delay}s, "
            f"max_delay={max_delay}s, backoff_factor={backoff_factor}"
        )

    def calculate_delay(self, attempt: int) -> int:
        """
        Calculate delay for given attempt number.

        Args:
            attempt: Attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        if attempt <= 0:
            return 0

        # Calculate exponential delay: base_delay * (backoff_factor ^ attempt)
        delay = self.base_delay * (self.backoff_factor ** (attempt - 1))

        # Cap at max_delay
        delay = min(delay, self.max_delay)

        # Add jitter (random ±10%)
        if self.jitter:
            jitter_amount = delay * 0.1
            jitter = random.uniform(-jitter_amount, jitter_amount)
            delay = max(0, delay + jitter)

        return int(delay)

    def get_next_retry_time(
        self,
        attempt_count: int,
        base_time: Optional[datetime] = None
    ) -> Optional[datetime]:
        """
        Calculate next retry time based on attempt count.

        Args:
            attempt_count: Number of attempts already made
            base_time: Time to calculate from (uses current time if None)

        Returns:
            Datetime for next retry, or None if max attempts reached
        """
        if attempt_count >= self.max_attempts:
            logger.warning(
                f"❌ Max retry attempts reached: {attempt_count}/{self.max_attempts}"
            )
            return None

        if base_time is None:
            base_time = datetime.utcnow()

        delay = self.calculate_delay(attempt_count)
        next_retry = base_time + timedelta(seconds=delay)

        logger.debug(
            f"⏰ Next retry scheduled: {delay}s from now "
            f"(attempt {attempt_count + 1}/{self.max_attempts})"
        )

        return next_retry

    def should_retry(
        self,
        http_status: Optional[int],
        error: Optional[str] = None
    ) -> bool:
        """
        Determine if error is retryable.

        Args:
            http_status: HTTP status code (None for network errors)
            error: Error message (for context)

        Returns:
            True if should retry, False if permanent failure
        """
        # Network errors are retryable
        if http_status is None:
            logger.info(f"🔄 Network error is retryable: {error}")
            return True

        # 5xx errors are retryable
        if 500 <= http_status < 600:
            logger.info(f"🔄 Server error {http_status} is retryable")
            return True

        # 408 (Request Timeout) and 429 (Too Many Requests) are retryable
        if http_status in [408, 429]:
            logger.info(f"🔄 Status {http_status} is retryable")
            return True

        # 4xx (except above) are not retryable
        if 400 <= http_status < 500:
            logger.warning(
                f"❌ Client error {http_status} is not retryable"
            )
            return False

        # 2xx and 3xx are not retryable (should not reach here)
        logger.info(f"✅ Status {http_status} is successful, no retry needed")
        return False

    def get_retry_summary(
        self,
        attempt_count: int,
        last_error: Optional[str] = None
    ) -> str:
        """
        Generate human-readable retry summary.

        Args:
            attempt_count: Number of attempts made
            last_error: Last error message

        Returns:
            Summary string
        """
        remaining = max(0, self.max_attempts - attempt_count)
        percent = (attempt_count / self.max_attempts) * 100

        summary = (
            f"Retry attempt {attempt_count}/{self.max_attempts} "
            f"({percent:.0f}%) - {remaining} remaining"
        )

        if last_error:
            summary += f"\nLast error: {last_error}"

        return summary


# Default retry strategy
DEFAULT_RETRY_STRATEGY = RetryStrategy(
    max_attempts=5,
    base_delay=60,
    max_delay=3600,
    backoff_factor=2.0,
    jitter=True
)


class RetryScheduler:
    """Manages retry scheduling for failed webhooks."""

    def __init__(self, strategy: Optional[RetryStrategy] = None):
        """
        Initialize retry scheduler.

        Args:
            strategy: RetryStrategy instance (uses default if None)
        """
        self.strategy = strategy or DEFAULT_RETRY_STRATEGY
        self.pending_retries = {}

    def schedule_retry(
        self,
        delivery_id: str,
        attempt_count: int,
        error: str = None
    ) -> bool:
        """
        Schedule retry for failed delivery.

        Args:
            delivery_id: ID of webhook delivery
            attempt_count: Number of attempts already made
            error: Error message from last attempt

        Returns:
            True if retry scheduled, False if max attempts exceeded
        """
        next_retry = self.strategy.get_next_retry_time(attempt_count)

        if next_retry is None:
            logger.error(
                f"❌ Webhook {delivery_id} exceeded max retries: {error}"
            )
            return False

        self.pending_retries[delivery_id] = {
            "next_retry": next_retry,
            "attempt_count": attempt_count + 1,
            "last_error": error
        }

        delay = (next_retry - datetime.utcnow()).total_seconds()
        logger.info(
            f"⏰ Webhook {delivery_id} scheduled for retry "
            f"in {delay:.0f}s (attempt {attempt_count + 1})"
        )

        return True

    def get_pending_retries(self) -> list:
        """
        Get list of deliveries ready for retry.

        Returns:
            List of delivery IDs ready to retry
        """
        now = datetime.utcnow()
        ready = []

        for delivery_id, retry_info in list(self.pending_retries.items()):
            if retry_info["next_retry"] <= now:
                ready.append(delivery_id)
                del self.pending_retries[delivery_id]

        if ready:
            logger.info(f"📤 {len(ready)} webhooks ready for retry")

        return ready

    def cancel_retry(self, delivery_id: str) -> bool:
        """
        Cancel pending retry for delivery.

        Args:
            delivery_id: ID of webhook delivery

        Returns:
            True if cancelled, False if not pending
        """
        if delivery_id in self.pending_retries:
            del self.pending_retries[delivery_id]
            logger.info(f"🚫 Webhook retry cancelled: {delivery_id}")
            return True

        return False

    def get_pending_count(self) -> int:
        """Get count of pending retries."""
        return len(self.pending_retries)


# Global retry scheduler instance
_retry_scheduler = None


def get_retry_scheduler() -> RetryScheduler:
    """Get or create global retry scheduler."""
    global _retry_scheduler
    if _retry_scheduler is None:
        _retry_scheduler = RetryScheduler()
    return _retry_scheduler
