"""
Webhook Event Manager for MetasploitMCP Bridge.

Handles event dispatching and webhook callbacks for:
- Exploitation events (started, success, failure)
- Session events (created, closed)
- Command execution events
- Post-exploitation module events
- C2 channel events
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

from app.models import AuditLog


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
    """Manages webhook subscriptions and event dispatch."""

    def __init__(self):
        """Initialize webhook manager."""
        self.subscriptions: Dict[str, WebhookSubscription] = {}
        self.event_handlers: Dict[WebhookEventType, List[Callable]] = {}
        self.session: Optional[aiohttp.ClientSession] = None

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
                success = await self._send_webhook(subscription, event)

                if success:
                    results["delivered"] += 1
                    logger.info(
                        f"✅ Webhook delivered to {subscription.url} "
                        f"({subscription.id})"
                    )
                else:
                    results["failed"] += 1
                    logger.warning(
                        f"⚠️ Webhook delivery failed to {subscription.url}"
                    )

                results["results"].append({
                    "subscription_id": subscription.id,
                    "url": subscription.url,
                    "success": success
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
        event: WebhookPayload
    ) -> bool:
        """
        Send webhook to subscription URL.

        Args:
            subscription: Webhook subscription
            event: Event payload

        Returns:
            True if successful, False otherwise
        """

        if not self.session:
            logger.error("HTTP session not initialized")
            return False

        payload = event.to_dict()

        try:
            async with self.session.post(
                subscription.url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Event": event.event_type.value,
                    "X-Webhook-ID": event.event_id
                },
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if 200 <= response.status < 300:
                    return True
                else:
                    logger.warning(
                        f"Webhook returned status {response.status}: "
                        f"{await response.text()}"
                    )
                    return False

        except asyncio.TimeoutError:
            logger.warning(f"Webhook timeout for {subscription.url}")
            return False
        except Exception as e:
            logger.exception(f"Webhook dispatch error: {e}")
            return False

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
