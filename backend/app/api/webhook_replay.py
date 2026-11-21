"""
Webhook Replay API (Phase 3.5).

REST endpoints for replaying historical webhook events on demand.
"""

import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuditLog
from app.services.webhook_replay_service import get_replay_service
from app.schemas.webhook_delivery import WebhookDeliveryError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks/replay", tags=["webhook-replay"])


@router.post("/events/{event_id}")
async def replay_event(
    event_id: str,
    subscription_ids: Optional[List[str]] = Query(None, description="Specific subscriptions to target"),
    db: Session = Depends(get_db)
) -> dict:
    """
    Replay a single event to specified subscriptions.

    **Path Parameters:**
    - `event_id`: The event ID to replay

    **Query Parameters:**
    - `subscription_ids`: Optional list of subscription IDs to target.
                         If not provided, event is sent to all subscriptions
                         that have received this event type.

    **Returns:**
    - `replay_id`: Unique ID for this replay operation
    - `events_queued`: Number of deliveries queued
    - `subscriptions_targeted`: Number of subscriptions affected
    - `status`: Current status of replay

    **Example:**
    ```
    POST /api/webhooks/replay/events/evt_abc123?subscription_ids=sub_1&subscription_ids=sub_2
    ```
    """

    try:
        replay_service = get_replay_service()

        result = await replay_service.replay_event(
            event_id=event_id,
            subscription_ids=subscription_ids,
            db_session=db
        )

        # Log the action
        audit_log = AuditLog(
            action="webhook_event_replay",
            details={
                "event_id": event_id,
                "subscription_ids": subscription_ids,
                "replay_id": result.get("replay_id")
            }
        )
        db.add(audit_log)
        db.commit()

        logger.info(
            f"Replayed event {event_id}",
            extra={"replay_id": result.get("replay_id")}
        )

        return result

    except ValueError as e:
        logger.warning(f"Invalid replay request: {e}")
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        logger.exception(f"Error replaying event: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to replay event"
        )


@router.post("/subscriptions/{subscription_id}")
async def replay_subscription(
    subscription_id: str,
    event_types: Optional[List[str]] = Query(None, description="Filter by event types"),
    from_date: Optional[datetime] = Query(None, description="Start date for filtering"),
    to_date: Optional[datetime] = Query(None, description="End date for filtering"),
    db: Session = Depends(get_db)
) -> dict:
    """
    Replay events for a specific subscription with optional filtering.

    **Path Parameters:**
    - `subscription_id`: The subscription to replay events for

    **Query Parameters:**
    - `event_types`: Optional event types to filter (e.g., exploitation.success)
    - `from_date`: Optional start date to replay from
    - `to_date`: Optional end date to replay until

    **Returns:**
    - `replay_id`: Unique ID for this replay operation
    - `events_queued`: Number of events queued for delivery
    - `status`: Current status of replay

    **Example:**
    ```
    POST /api/webhooks/replay/subscriptions/sub_xyz789?event_types=exploitation.success&from_date=2026-11-01
    ```
    """

    try:
        replay_service = get_replay_service()

        result = await replay_service.replay_subscription(
            subscription_id=subscription_id,
            event_types=event_types,
            from_date=from_date,
            to_date=to_date,
            db_session=db
        )

        # Log the action
        audit_log = AuditLog(
            action="webhook_subscription_replay",
            details={
                "subscription_id": subscription_id,
                "event_types": event_types,
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
                "replay_id": result.get("replay_id")
            }
        )
        db.add(audit_log)
        db.commit()

        logger.info(
            f"Replayed subscription {subscription_id}",
            extra={"replay_id": result.get("replay_id")}
        )

        return result

    except ValueError as e:
        logger.warning(f"Invalid replay request: {e}")
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        logger.exception(f"Error replaying subscription: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to replay subscription events"
        )


@router.post("/batch")
async def batch_replay(
    event_types: Optional[List[str]] = Query(None, description="Filter by event types"),
    subscription_ids: Optional[List[str]] = Query(None, description="Filter by subscriptions"),
    campaign_ids: Optional[List[str]] = Query(None, description="Filter by campaigns"),
    from_date: Optional[datetime] = Query(None, description="Start date for filtering"),
    to_date: Optional[datetime] = Query(None, description="End date for filtering"),
    dry_run: bool = Query(False, description="If true, count only without queueing"),
    db: Session = Depends(get_db)
) -> dict:
    """
    Batch replay with complex filtering criteria.

    **Query Parameters:**
    - `event_types`: Event types to replay (optional)
    - `subscription_ids`: Subscriptions to target (optional)
    - `campaign_ids`: Campaigns to filter (optional)
    - `from_date`: Start date for filtering (optional)
    - `to_date`: End date for filtering (optional)
    - `dry_run`: If true, only count matching events without queueing (default: false)

    **Returns:**
    - `replay_id`: Unique ID for this replay operation (null for dry_run)
    - `events_queued`: Number of events queued for delivery
    - `total_events`: Total events matching criteria
    - `status`: Current status of replay

    **Example - Dry Run:**
    ```
    POST /api/webhooks/replay/batch?event_types=exploitation.success&dry_run=true
    ```

    **Example - Batch Replay:**
    ```
    POST /api/webhooks/replay/batch?campaign_ids=camp_1&campaign_ids=camp_2&from_date=2026-11-01
    ```
    """

    try:
        replay_service = get_replay_service()

        filters = {
            "event_types": event_types,
            "subscription_ids": subscription_ids,
            "campaign_ids": campaign_ids,
            "from_date": from_date,
            "to_date": to_date
        }

        result = await replay_service.batch_replay(
            filters=filters,
            dry_run=dry_run,
            db_session=db
        )

        # Log the action
        audit_log = AuditLog(
            action="webhook_batch_replay",
            details={
                "filters": {
                    k: (v.isoformat() if isinstance(v, datetime) else v)
                    for k, v in filters.items()
                },
                "dry_run": dry_run,
                "replay_id": result.get("replay_id")
            }
        )
        db.add(audit_log)
        db.commit()

        logger.info(
            f"Batch replay completed",
            extra={"replay_id": result.get("replay_id"), "dry_run": dry_run}
        )

        return result

    except ValueError as e:
        logger.warning(f"Invalid batch replay request: {e}")
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        logger.exception(f"Error in batch replay: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to process batch replay"
        )


@router.get("/{replay_id}/status")
async def get_replay_status(
    replay_id: str,
    db: Session = Depends(get_db)
) -> dict:
    """
    Get status of a replay operation.

    **Path Parameters:**
    - `replay_id`: The replay operation ID to check status for

    **Returns:**
    - `status`: Current status (pending, in_progress, completed, failed)
    - `events_queued`: Number of events queued
    - `events_delivered`: Number successfully delivered
    - `events_failed`: Number that failed
    - `progress`: Progress summary with breakdown

    **Example:**
    ```
    GET /api/webhooks/replay/rpl_abc123/status
    ```
    """

    try:
        replay_service = get_replay_service()

        result = replay_service.get_replay_status(
            replay_id=replay_id,
            db_session=db
        )

        logger.info(f"Retrieved replay status: {replay_id}")

        return result

    except ValueError as e:
        logger.warning(f"Replay not found: {e}")
        raise HTTPException(
            status_code=404,
            detail=str(e)
        )
    except Exception as e:
        logger.exception(f"Error getting replay status: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get replay status"
        )
