"""
Webhook Event Manager for MetasploitMCP Bridge.

Handles event dispatching and webhook callbacks for:
- Exploitation events (started, success, failure)
- Session events (created, closed)
- Command execution events
- Post-exploitation module events
- C2 channel events

Phase 3: Enhanced with HMAC signatures, retry logic, and delivery tracking.
"""

import logging
import json
import asyncio
import aiohttp
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models import AuditLog, WebhookDelivery, WebhookDeliveryStatus
from app.services.webhook_signer import WebhookSigner
from app.services.webhook_retry_service import (
    RetryStrategy,
    get_retry_scheduler,
    DEFAULT_RETRY_STRATEGY
)


logger = logging.getLogger(__name__)


class WebhookEventType(str, Enum):
    """Webhook event types."""

    # Exploitation events
    EXPLOITATION_STARTED = "exploitation.started"
    EXPLOITATION_SUCCESS = "exploitation.success"
    EXPLOITATION_FAILURE = "exploitation.failed"

    # Session events
    SESSION_CREATED = "session.created"
    SESSION_ACTIVE = "session.active"
    SESSION_CLOSED = "session.closed"

    # Command execution events
    COMMAND_EXECUTED = "command.executed"
    COMMAND_FAILED = "command.failed"

    # Post-exploitation events
    POST_MODULE_EXECUTED = "post_module.executed"
    POST_MODULE_FAILED = "post_module.failed"

    # C2 events
    C2_ESTABLISHED = "c2.established"
    C2_LOST = "c2.lost"


@dataclass
class WebhookPayload:
    """Webhook event payload."""

    event_type: WebhookEventType
    campaign_id: str
    target_id: str
    timestamp: str
    event_id: str
    data: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_type": self.event_type.value,
            "campaign_id": self.campaign_id,
            "target_id": self.target_id,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
            "data": self.data
        }


@dataclass
class WebhookSubscription:
    """Webhook subscription details."""

    id: str
    url: str
    event_types: List[WebhookEventType]
    campaign_id: Optional[str] = None
    target_id: Optional[str] = None
    active: bool = True
    secret: Optional[str] = None
    created_at: str = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow().isoformat()


class WebhookManager:
    """Manages webhook subscriptions and event dispatch with Phase 3 enhancements."""

    def __init__(self, retry_strategy: Optional[RetryStrategy] = None):
        """
        Initialize webhook manager.

        Args:
            retry_strategy: Retry strategy for failed webhooks (uses default if None)
        """
        self.subscriptions: Dict[str, WebhookSubscription] = {}
        self.event_handlers: Dict[WebhookEventType, List[Callable]] = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.retry_strategy = retry_strategy or DEFAULT_RETRY_STRATEGY
        self.retry_scheduler = get_retry_scheduler()

        logger.info(
            f"🔧 Webhook manager initialized with retry strategy: "
            f"{self.retry_strategy.max_attempts} attempts, "
            f"{self.retry_strategy.base_delay}s base delay"
        )

    async def initialize(self):
        """Initialize webhook manager (create HTTP session)."""
        self.session = aiohttp.ClientSession()
        logger.info("✅ Webhook manager initialized")

    async def shutdown(self):
        """Shutdown webhook manager."""
        if self.session:
            await self.session.close()
        logger.info("🛑 Webhook manager shut down")

    def subscribe(
        self,
        url: str,
        event_types: List[WebhookEventType],
        campaign_id: Optional[str] = None,
        target_id: Optional[str] = None,
        secret: Optional[str] = None
    ) -> WebhookSubscription:
        """
        Subscribe to webhook events.

        Args:
            url: Webhook URL to call
            event_types: List of event types to subscribe to
            campaign_id: Optional campaign filter
            target_id: Optional target filter
            secret: Optional secret for HMAC signature

        Returns:
            WebhookSubscription with subscription details
        """

        subscription_id = f"sub_{uuid4().hex[:12]}"

        subscription = WebhookSubscription(
            id=subscription_id,
            url=url,
            event_types=event_types,
            campaign_id=campaign_id,
            target_id=target_id,
            secret=secret
        )

        self.subscriptions[subscription_id] = subscription

        logger.info(
            f"✅ Webhook subscribed: {subscription_id} → {url} "
            f"({len(event_types)} event types)"
        )

        return subscription

    def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe from webhooks.

        Args:
            subscription_id: Subscription ID to remove

        Returns:
            True if removed, False if not found
        """

        if subscription_id in self.subscriptions:
            del self.subscriptions[subscription_id]
            logger.info(f"✅ Webhook unsubscribed: {subscription_id}")
            return True

        return False

    def list_subscriptions(
        self,
        campaign_id: Optional[str] = None,
        event_type: Optional[WebhookEventType] = None
    ) -> List[WebhookSubscription]:
        """
        List active subscriptions.

        Args:
            campaign_id: Optional filter by campaign
            event_type: Optional filter by event type

        Returns:
            List of matching subscriptions
        """

        subscriptions = list(self.subscriptions.values())

        # Filter by campaign
        if campaign_id:
            subscriptions = [
                s for s in subscriptions
                if s.campaign_id is None or s.campaign_id == campaign_id
            ]

        # Filter by event type
        if event_type:
            subscriptions = [
                s for s in subscriptions
                if event_type in s.event_types
            ]

        # Filter by active status
        subscriptions = [s for s in subscriptions if s.active]

        return subscriptions

    async def dispatch_event(
        self,
        event: WebhookPayload,
        db_session: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Dispatch webhook event to all subscriptions.

        Args:
            event: Webhook payload to dispatch
            db_session: Optional database session for logging

        Returns:
            Dispatch results with delivery status
        """

        logger.info(
            f"📤 Dispatching webhook event: {event.event_type.value} "
            f"(campaign={event.campaign_id})"
        )

        results = {
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "total_subscriptions": 0,
            "delivered": 0,
            "failed": 0,
            "results": []
        }

        # Find matching subscriptions
        subscriptions = self.list_subscriptions(
            campaign_id=event.campaign_id,
            event_type=event.event_type
        )

        results["total_subscriptions"] = len(subscriptions)

        # Dispatch to each subscription
        for subscription in subscriptions:
            try:
                delivery_result = await self._send_webhook(
                    subscription, event, db_session
                )

                if delivery_result.get("success"):
                    results["delivered"] += 1
                else:
                    results["failed"] += 1

                results["results"].append({
                    "subscription_id": subscription.id,
                    "delivery_id": delivery_result.get("delivery_id"),
                    "url": subscription.url,
                    "success": delivery_result.get("success"),
                    "http_status": delivery_result.get("http_status"),
                    "error": delivery_result.get("error"),
                    "attempt": delivery_result.get("attempt")
                })

            except Exception as e:
                results["failed"] += 1
                logger.exception(
                    f"❌ Error dispatching webhook to {subscription.url}: {e}"
                )
                results["results"].append({
                    "subscription_id": subscription.id,
                    "url": subscription.url,
                    "success": False,
                    "error": str(e)
                })

        # Log to audit trail
        if db_session:
            try:
                audit_log = AuditLog(
                    action="webhook_dispatch",
                    details={
                        "event_id": event.event_id,
                        "event_type": event.event_type.value,
                        "total_subscriptions": results["total_subscriptions"],
                        "delivered": results["delivered"],
                        "failed": results["failed"]
                    },
                    performed_at=datetime.utcnow()
                )
                db_session.add(audit_log)
                db_session.commit()
            except Exception as e:
                logger.exception(f"Failed to log webhook dispatch: {e}")

        return results

    async def _send_webhook(
        self,
        subscription: WebhookSubscription,
        event: WebhookPayload,
        db_session: Optional[Session] = None,
        attempt: int = 0
    ) -> Dict[str, Any]:
        """
        Send webhook to subscription URL with Phase 3 enhancements.

        Args:
            subscription: Webhook subscription
            event: Event payload
            db_session: Database session for tracking
            attempt: Attempt number (0 = first attempt)

        Returns:
            Dictionary with delivery status and details
        """

        if not self.session:
            logger.error("HTTP session not initialized")
            return {"success": False, "error": "Session not initialized"}

        delivery_id = f"del_{uuid4().hex[:12]}"
        payload = event.to_dict()
        payload_json = json.dumps(payload)

        # Generate headers with signature
        try:
            if subscription.secret:
                headers = WebhookSigner.create_headers(
                    payload_json,
                    subscription.secret,
                    event.event_id,
                    event.event_type.value
                )
            else:
                # Fallback: minimal headers without signature
                headers = {
                    "Content-Type": "application/json",
                    "X-Webhook-Event": event.event_type.value,
                    "X-Webhook-ID": event.event_id
                }
        except Exception as e:
            logger.exception(f"Failed to generate webhook headers: {e}")
            return {"success": False, "error": "Header generation failed"}

        result = {
            "delivery_id": delivery_id,
            "subscription_id": subscription.id,
            "event_id": event.event_id,
            "url": subscription.url,
            "success": False,
            "http_status": None,
            "error": None,
            "attempt": attempt + 1
        }

        try:
            logger.info(
                f"📤 Sending webhook (attempt {attempt + 1}): "
                f"{subscription.url} event={event.event_type.value}"
            )

            async with self.session.post(
                subscription.url,
                data=payload_json,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                http_status = response.status
                response_text = await response.text()

                result["http_status"] = http_status

                # Store delivery record if DB available
                if db_session:
                    try:
                        delivery = WebhookDelivery(
                            subscription_id=subscription.id,
                            event_id=event.event_id,
                            event_type=event.event_type.value,
                            campaign_id=event.campaign_id,
                            target_id=event.target_id,
                            url=subscription.url,
                            request_body=payload_json[:1000],  # Truncate
                            status=WebhookDeliveryStatus.delivered.value if (200 <= http_status < 300) else WebhookDeliveryStatus.failed.value,
                            http_status=http_status,
                            response_body=response_text[:1000],  # Truncate
                            attempt_count=attempt + 1,
                            max_attempts=self.retry_strategy.max_attempts
                        )

                        if 200 <= http_status < 300:
                            delivery.delivered_at = datetime.utcnow()
                            result["success"] = True
                            logger.info(f"✅ Webhook delivered: {delivery_id}")
                        else:
                            result["error"] = f"HTTP {http_status}"
                            # Schedule retry if applicable
                            if self.retry_strategy.should_retry(http_status, response_text):
                                next_retry = self.retry_strategy.get_next_retry_time(attempt + 1)
                                if next_retry:
                                    delivery.status = WebhookDeliveryStatus.retrying.value
                                    delivery.next_retry_at = next_retry
                                    delivery.last_error = response_text[:500]
                                    logger.info(
                                        f"⏰ Webhook scheduled for retry: {delivery_id} "
                                        f"at {next_retry}"
                                    )
                            else:
                                logger.warning(f"⚠️ Webhook not retryable: {http_status}")

                        db_session.add(delivery)
                        db_session.commit()

                    except Exception as e:
                        logger.exception(f"Failed to store delivery record: {e}")

                if 200 <= http_status < 300:
                    return result
                else:
                    result["error"] = f"HTTP {http_status}"
                    logger.warning(
                        f"⚠️ Webhook returned {http_status}: "
                        f"{response_text[:200]}"
                    )
                    return result

        except asyncio.TimeoutError:
            error = "Connection timeout"
            logger.warning(f"⏱️ Webhook timeout: {subscription.url}")

            # Store timeout attempt and schedule retry
            if db_session:
                try:
                    delivery = WebhookDelivery(
                        subscription_id=subscription.id,
                        event_id=event.event_id,
                        event_type=event.event_type.value,
                        campaign_id=event.campaign_id,
                        target_id=event.target_id,
                        url=subscription.url,
                        request_body=payload_json[:1000],
                        status=WebhookDeliveryStatus.retrying.value,
                        attempt_count=attempt + 1,
                        max_attempts=self.retry_strategy.max_attempts,
                        last_error=error
                    )

                    next_retry = self.retry_strategy.get_next_retry_time(attempt + 1)
                    if next_retry:
                        delivery.next_retry_at = next_retry
                    else:
                        delivery.status = WebhookDeliveryStatus.failed.value

                    db_session.add(delivery)
                    db_session.commit()

                except Exception as e:
                    logger.exception(f"Failed to store timeout delivery: {e}")

            result["error"] = error
            return result

        except Exception as e:
            error = str(e)
            logger.exception(f"❌ Webhook dispatch error: {e}")

            # Store error and schedule retry
            if db_session:
                try:
                    delivery = WebhookDelivery(
                        subscription_id=subscription.id,
                        event_id=event.event_id,
                        event_type=event.event_type.value,
                        campaign_id=event.campaign_id,
                        target_id=event.target_id,
                        url=subscription.url,
                        request_body=payload_json[:1000],
                        status=WebhookDeliveryStatus.retrying.value,
                        attempt_count=attempt + 1,
                        max_attempts=self.retry_strategy.max_attempts,
                        last_error=error
                    )

                    next_retry = self.retry_strategy.get_next_retry_time(attempt + 1)
                    if next_retry:
                        delivery.next_retry_at = next_retry
                    else:
                        delivery.status = WebhookDeliveryStatus.failed.value

                    db_session.add(delivery)
                    db_session.commit()

                except Exception as e:
                    logger.exception(f"Failed to store error delivery: {e}")

            result["error"] = error
            return result

    async def process_pending_retries(
        self,
        db_session: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Process pending webhook retries (Phase 3).

        Args:
            db_session: Database session for loading deliveries

        Returns:
            Retry processing results
        """
        if not db_session:
            logger.warning("Cannot process retries without database session")
            return {"processed": 0, "succeeded": 0, "failed": 0}

        try:
            # Get pending retries from scheduler
            pending_delivery_ids = self.retry_scheduler.get_pending_retries()

            if not pending_delivery_ids:
                return {"processed": 0, "succeeded": 0, "failed": 0}

            logger.info(f"🔄 Processing {len(pending_delivery_ids)} pending retries")

            results = {
                "processed": len(pending_delivery_ids),
                "succeeded": 0,
                "failed": 0,
                "details": []
            }

            for delivery_id in pending_delivery_ids:
                try:
                    # Load delivery record
                    delivery = db_session.query(WebhookDelivery).filter(
                        WebhookDelivery.id == delivery_id
                    ).first()

                    if not delivery:
                        logger.warning(f"⚠️ Delivery record not found: {delivery_id}")
                        results["failed"] += 1
                        continue

                    # Reconstruct event and subscription for retry
                    # Note: In production, consider storing more data for replay
                    logger.info(
                        f"⏳ Retrying delivery: {delivery_id} "
                        f"(attempt {delivery.attempt_count})"
                    )

                    # Update status to reflect retry attempt
                    delivery.status = WebhookDeliveryStatus.retrying.value
                    delivery.attempt_count += 1
                    db_session.commit()

                    results["details"].append({
                        "delivery_id": delivery_id,
                        "subscription_id": delivery.subscription_id,
                        "url": delivery.url,
                        "attempt": delivery.attempt_count,
                        "status": "queued_for_retry"
                    })

                    logger.debug(f"✅ Queued retry: {delivery_id}")
                    results["succeeded"] += 1

                except Exception as e:
                    logger.exception(f"Error processing retry {delivery_id}: {e}")
                    results["failed"] += 1
                    results["details"].append({
                        "delivery_id": delivery_id,
                        "error": str(e)
                    })

            return results

        except Exception as e:
            logger.exception(f"Error in retry processing: {e}")
            return {"processed": 0, "succeeded": 0, "failed": 0, "error": str(e)}

    async def get_delivery_status(
        self,
        subscription_id: str,
        db_session: Optional[Session] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get delivery status for subscription (Phase 3).

        Args:
            subscription_id: Subscription ID
            db_session: Database session
            limit: Results per page
            offset: Pagination offset

        Returns:
            Delivery history with status
        """
        if not db_session:
            return {"error": "Database session required", "deliveries": []}

        try:
            # Query deliveries
            query = db_session.query(WebhookDelivery).filter(
                WebhookDelivery.subscription_id == subscription_id
            ).order_by(WebhookDelivery.created_at.desc())

            total = query.count()
            deliveries = query.limit(limit).offset(offset).all()

            return {
                "subscription_id": subscription_id,
                "total": total,
                "limit": limit,
                "offset": offset,
                "deliveries": [
                    {
                        "id": d.id,
                        "event_id": d.event_id,
                        "event_type": d.event_type,
                        "status": d.status,
                        "http_status": d.http_status,
                        "attempt_count": d.attempt_count,
                        "created_at": d.created_at.isoformat() if d.created_at else None,
                        "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
                        "next_retry_at": d.next_retry_at.isoformat() if d.next_retry_at else None,
                        "error": d.last_error
                    }
                    for d in deliveries
                ]
            }

        except Exception as e:
            logger.exception(f"Error getting delivery status: {e}")
            return {"error": str(e), "deliveries": []}

    def register_handler(
        self,
        event_type: WebhookEventType,
        handler: Callable
    ) -> None:
        """
        Register event handler.

        Args:
            event_type: Event type to handle
            handler: Async handler function
        """

        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []

        self.event_handlers[event_type].append(handler)
        logger.info(f"✅ Registered handler for {event_type.value}")

    async def call_handlers(self, event: WebhookPayload) -> None:
        """
        Call registered event handlers.

        Args:
            event: Event payload
        """

        if event.event_type not in self.event_handlers:
            return

        handlers = self.event_handlers[event.event_type]

        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.exception(f"Event handler error: {e}")


# Global webhook manager instance
_webhook_manager: Optional[WebhookManager] = None


def get_webhook_manager() -> WebhookManager:
    """Get or create webhook manager instance."""

    global _webhook_manager

    if _webhook_manager is None:
        _webhook_manager = WebhookManager()

    return _webhook_manager


async def initialize_webhooks() -> None:
    """Initialize webhook manager."""
    manager = get_webhook_manager()
    await manager.initialize()


async def shutdown_webhooks() -> None:
    """Shutdown webhook manager."""
    manager = get_webhook_manager()
    await manager.shutdown()
