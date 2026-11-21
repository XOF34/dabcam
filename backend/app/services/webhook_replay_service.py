"""
Webhook Replay Service (Phase 3.5).

Functionality for replaying historical webhook events on demand.
Supports single event replay, subscription replay, and batch replay with filtering.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.models import WebhookDelivery, WebhookReplay, WebhookReplayStatus
from app.services.webhook_manager import WebhookManager
import uuid

logger = logging.getLogger(__name__)


class WebhookReplayService:
    """Replay webhook events on demand."""

    def __init__(self, webhook_manager: Optional[WebhookManager] = None):
        """Initialize replay service with webhook manager."""
        self.webhook_manager = webhook_manager
        self._pending_replays: Dict[str, Dict] = {}

    async def replay_event(
        self,
        event_id: str,
        subscription_ids: Optional[List[str]] = None,
        db_session: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Replay a single event to specified subscriptions.

        Args:
            event_id: ID of event to replay
            subscription_ids: Subscriptions to send to (all if None)
            db_session: Database session

        Returns:
            Replay operation details with ID, count, status
        """
        if not db_session:
            raise ValueError("Database session required")

        try:
            # Find the original event
            original_delivery = db_session.query(WebhookDelivery).filter(
                WebhookDelivery.event_id == event_id
            ).first()

            if not original_delivery:
                raise ValueError(f"Event {event_id} not found")

            # Get all subscriptions to target
            if subscription_ids:
                target_subscriptions = subscription_ids
            else:
                # Get all subscriptions that have received this event type
                subscriptions = db_session.query(WebhookDelivery).filter(
                    WebhookDelivery.event_type == original_delivery.event_type
                ).distinct(WebhookDelivery.subscription_id).all()

                target_subscriptions = [s.subscription_id for s in subscriptions]

            # Create replay record
            replay_id = f"rpl_{uuid.uuid4().hex[:12]}"
            replay = WebhookReplay(
                id=replay_id,
                event_id=event_id,
                event_type=original_delivery.event_type,
                status=WebhookReplayStatus.pending.value,
                total_events=1,
                created_by="system"
            )
            db_session.add(replay)
            db_session.commit()

            # Queue delivery to each subscription
            events_queued = 0
            for subscription_id in target_subscriptions:
                if self.webhook_manager:
                    # Queue the event through webhook manager
                    await self.webhook_manager.dispatch_event(
                        event_id=event_id,
                        event_type=original_delivery.event_type,
                        subscription_id=subscription_id,
                        payload={
                            "replayed": True,
                            "original_event_id": event_id,
                            "replay_id": replay_id,
                            "original_timestamp": original_delivery.created_at.isoformat()
                        },
                        campaign_id=original_delivery.campaign_id,
                        target_id=original_delivery.target_id
                    )
                    events_queued += 1

            # Update replay record
            replay.events_queued = events_queued
            replay.status = WebhookReplayStatus.in_progress.value
            db_session.commit()

            logger.info(
                f"Replayed event {event_id} to {events_queued} subscriptions",
                extra={"replay_id": replay_id}
            )

            return {
                "replay_id": replay_id,
                "event_id": event_id,
                "event_type": original_delivery.event_type,
                "events_queued": events_queued,
                "subscriptions_targeted": len(target_subscriptions),
                "status": WebhookReplayStatus.in_progress.value,
                "created_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.exception(f"Error replaying event {event_id}: {e}")
            raise

    async def replay_subscription(
        self,
        subscription_id: str,
        event_types: Optional[List[str]] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        db_session: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Replay events for a specific subscription with filters.

        Args:
            subscription_id: Subscription to replay events for
            event_types: Filter by event types (all if None)
            from_date: Start date filter
            to_date: End date filter
            db_session: Database session

        Returns:
            Replay operation details with ID, count, status
        """
        if not db_session:
            raise ValueError("Database session required")

        try:
            # Build query for events to replay
            query = db_session.query(WebhookDelivery).filter(
                WebhookDelivery.subscription_id == subscription_id,
                WebhookDelivery.status == "delivered"
            )

            if event_types:
                query = query.filter(WebhookDelivery.event_type.in_(event_types))

            if from_date and to_date:
                query = query.filter(
                    and_(
                        WebhookDelivery.created_at >= from_date,
                        WebhookDelivery.created_at <= to_date
                    )
                )
            elif from_date:
                query = query.filter(WebhookDelivery.created_at >= from_date)
            elif to_date:
                query = query.filter(WebhookDelivery.created_at <= to_date)

            deliveries_to_replay = query.all()

            if not deliveries_to_replay:
                return {
                    "replay_id": None,
                    "subscription_id": subscription_id,
                    "events_queued": 0,
                    "status": "no_events_found",
                    "message": "No events found matching criteria"
                }

            # Create replay record
            replay_id = f"rpl_{uuid.uuid4().hex[:12]}"
            replay = WebhookReplay(
                id=replay_id,
                subscription_id=subscription_id,
                status=WebhookReplayStatus.pending.value,
                total_events=len(deliveries_to_replay),
                filter_params={
                    "event_types": event_types,
                    "from_date": from_date.isoformat() if from_date else None,
                    "to_date": to_date.isoformat() if to_date else None
                },
                created_by="system"
            )
            db_session.add(replay)
            db_session.commit()

            # Queue events for replay
            events_queued = 0
            for delivery in deliveries_to_replay:
                if self.webhook_manager:
                    await self.webhook_manager.dispatch_event(
                        event_id=delivery.event_id,
                        event_type=delivery.event_type,
                        subscription_id=subscription_id,
                        payload={
                            "replayed": True,
                            "original_event_id": delivery.event_id,
                            "replay_id": replay_id,
                            "original_timestamp": delivery.created_at.isoformat()
                        },
                        campaign_id=delivery.campaign_id,
                        target_id=delivery.target_id
                    )
                    events_queued += 1

            # Update replay record
            replay.events_queued = events_queued
            replay.status = WebhookReplayStatus.in_progress.value
            db_session.commit()

            logger.info(
                f"Replayed {events_queued} events for subscription {subscription_id}",
                extra={"replay_id": replay_id}
            )

            return {
                "replay_id": replay_id,
                "subscription_id": subscription_id,
                "total_events": len(deliveries_to_replay),
                "events_queued": events_queued,
                "status": WebhookReplayStatus.in_progress.value,
                "created_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.exception(f"Error replaying subscription {subscription_id}: {e}")
            raise

    async def batch_replay(
        self,
        filters: Dict[str, Any],
        dry_run: bool = False,
        db_session: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Batch replay with complex filters.

        Args:
            filters: Complex filter criteria
            dry_run: If True, count only without queuing
            db_session: Database session

        Returns:
            Replay operation details
        """
        if not db_session:
            raise ValueError("Database session required")

        try:
            # Build query from filters
            query = db_session.query(WebhookDelivery).filter(
                WebhookDelivery.status == "delivered"
            )

            # Apply filters
            if "event_types" in filters and filters["event_types"]:
                query = query.filter(
                    WebhookDelivery.event_type.in_(filters["event_types"])
                )

            if "subscription_ids" in filters and filters["subscription_ids"]:
                query = query.filter(
                    WebhookDelivery.subscription_id.in_(filters["subscription_ids"])
                )

            if "campaign_ids" in filters and filters["campaign_ids"]:
                query = query.filter(
                    WebhookDelivery.campaign_id.in_(filters["campaign_ids"])
                )

            if "from_date" in filters and filters["from_date"]:
                from_date = filters["from_date"]
                if isinstance(from_date, str):
                    from_date = datetime.fromisoformat(from_date)
                query = query.filter(WebhookDelivery.created_at >= from_date)

            if "to_date" in filters and filters["to_date"]:
                to_date = filters["to_date"]
                if isinstance(to_date, str):
                    to_date = datetime.fromisoformat(to_date)
                query = query.filter(WebhookDelivery.created_at <= to_date)

            matching_deliveries = query.all()

            if dry_run:
                return {
                    "dry_run": True,
                    "events_found": len(matching_deliveries),
                    "message": "Dry run completed - no events queued"
                }

            if not matching_deliveries:
                return {
                    "replay_id": None,
                    "events_queued": 0,
                    "status": "no_events_found",
                    "message": "No events found matching filter criteria"
                }

            # Create replay record
            replay_id = f"rpl_{uuid.uuid4().hex[:12]}"
            replay = WebhookReplay(
                id=replay_id,
                status=WebhookReplayStatus.pending.value,
                total_events=len(matching_deliveries),
                filter_params=filters,
                created_by="system"
            )
            db_session.add(replay)
            db_session.commit()

            # Queue events for replay
            events_queued = 0
            for delivery in matching_deliveries:
                if self.webhook_manager:
                    await self.webhook_manager.dispatch_event(
                        event_id=delivery.event_id,
                        event_type=delivery.event_type,
                        subscription_id=delivery.subscription_id,
                        payload={
                            "replayed": True,
                            "original_event_id": delivery.event_id,
                            "replay_id": replay_id,
                            "original_timestamp": delivery.created_at.isoformat()
                        },
                        campaign_id=delivery.campaign_id,
                        target_id=delivery.target_id
                    )
                    events_queued += 1

            # Update replay record
            replay.events_queued = events_queued
            replay.status = WebhookReplayStatus.in_progress.value
            db_session.commit()

            logger.info(
                f"Batch replay queued {events_queued} events",
                extra={"replay_id": replay_id}
            )

            return {
                "replay_id": replay_id,
                "total_events": len(matching_deliveries),
                "events_queued": events_queued,
                "status": WebhookReplayStatus.in_progress.value,
                "created_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.exception(f"Error in batch replay: {e}")
            raise

    def get_replay_status(
        self,
        replay_id: str,
        db_session: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Get status of a replay operation.

        Args:
            replay_id: ID of replay to check
            db_session: Database session

        Returns:
            Replay status and progress
        """
        if not db_session:
            raise ValueError("Database session required")

        try:
            replay = db_session.query(WebhookReplay).filter(
                WebhookReplay.id == replay_id
            ).first()

            if not replay:
                raise ValueError(f"Replay {replay_id} not found")

            return {
                "replay_id": replay_id,
                "status": replay.status,
                "total_events": replay.total_events,
                "events_queued": replay.events_queued,
                "events_delivered": replay.events_delivered,
                "events_failed": replay.events_failed,
                "created_at": replay.created_at.isoformat(),
                "started_at": replay.started_at.isoformat() if replay.started_at else None,
                "completed_at": replay.completed_at.isoformat() if replay.completed_at else None,
                "progress": {
                    "total": replay.total_events,
                    "delivered": replay.events_delivered,
                    "failed": replay.events_failed,
                    "pending": replay.total_events - (replay.events_delivered + replay.events_failed)
                }
            }

        except Exception as e:
            logger.exception(f"Error getting replay status: {e}")
            raise


# Global singleton instance
_replay_service: Optional[WebhookReplayService] = None


def get_replay_service() -> WebhookReplayService:
    """Get global replay service instance."""
    global _replay_service
    if _replay_service is None:
        _replay_service = WebhookReplayService()
    return _replay_service


def initialize_replay_service(webhook_manager: WebhookManager) -> None:
    """Initialize replay service with webhook manager."""
    global _replay_service
    _replay_service = WebhookReplayService(webhook_manager)
