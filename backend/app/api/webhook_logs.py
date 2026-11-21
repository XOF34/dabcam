"""
Webhook Logs API (Phase 3.6).

REST endpoints for viewing webhook activity logs with detailed filtering and analytics.
"""

import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc

from app.database import get_db
from app.models import WebhookLog, WebhookDelivery, AuditLog
from app.schemas.webhook_delivery import WebhookDeliveryError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks/logs", tags=["webhook-logs"])


@router.get("")
async def list_webhook_logs(
    event_id: Optional[str] = Query(None, description="Filter by event ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    subscription_id: Optional[str] = Query(None, description="Filter by subscription"),
    campaign_id: Optional[str] = Query(None, description="Filter by campaign"),
    target_id: Optional[str] = Query(None, description="Filter by target"),
    from_date: Optional[datetime] = Query(None, description="Start date filter"),
    to_date: Optional[datetime] = Query(None, description="End date filter"),
    status: Optional[str] = Query(None, description="Filter by delivery status"),
    limit: int = Query(50, ge=1, le=500, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    sort_by: str = Query("processed_at", regex="^(processed_at|event_type|subscription_id)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: Session = Depends(get_db)
) -> dict:
    """
    List webhook activity logs with comprehensive filtering.

    **Query Parameters:**
    - `event_id`: Filter by specific event
    - `event_type`: Filter by event type (e.g., exploitation.success)
    - `subscription_id`: Filter by webhook subscription
    - `campaign_id`: Filter by campaign ID
    - `target_id`: Filter by target ID
    - `from_date`: Start date for filtering
    - `to_date`: End date for filtering
    - `status`: Filter by delivery status (pending, delivered, failed, retrying)
    - `limit`: Results per page (1-500, default 50)
    - `offset`: Pagination offset (default 0)
    - `sort_by`: Sort field (processed_at, event_type, subscription_id)
    - `sort_order`: Sort order (asc, desc)

    **Returns:**
    - Paginated list of webhook logs with comprehensive details
    - Timestamps for all events
    - Delivery statistics for each log entry

    **Example:**
    ```
    GET /api/webhooks/logs?event_type=exploitation.success&campaign_id=camp_1&limit=25
    ```
    """

    try:
        # Build base query
        query = db.query(WebhookLog)

        # Apply filters
        if event_id:
            query = query.filter(WebhookLog.event_id == event_id)

        if event_type:
            query = query.filter(WebhookLog.event_type == event_type)

        if subscription_id:
            query = query.filter(WebhookLog.subscription_id == subscription_id)

        if campaign_id:
            query = query.filter(WebhookLog.campaign_id == campaign_id)

        if target_id:
            query = query.filter(WebhookLog.target_id == target_id)

        if from_date and to_date:
            query = query.filter(
                and_(
                    WebhookLog.processed_at >= from_date,
                    WebhookLog.processed_at <= to_date
                )
            )
        elif from_date:
            query = query.filter(WebhookLog.processed_at >= from_date)
        elif to_date:
            query = query.filter(WebhookLog.processed_at <= to_date)

        # Get total count
        total = query.count()

        # Apply sorting
        sort_column = getattr(WebhookLog, sort_by)
        if sort_order == "desc":
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(sort_column)

        # Apply pagination
        logs = query.limit(limit).offset(offset).all()

        # Format response
        log_entries = [
            {
                "id": log.id,
                "event_id": log.event_id,
                "event_type": log.event_type,
                "subscription_id": log.subscription_id,
                "campaign_id": log.campaign_id,
                "target_id": log.target_id,
                "total_deliveries": log.total_deliveries,
                "successful_deliveries": log.successful_deliveries,
                "failed_deliveries": log.failed_deliveries,
                "success_rate": (
                    (log.successful_deliveries / log.total_deliveries * 100)
                    if log.total_deliveries > 0
                    else 0.0
                ),
                "event_payload": log.event_payload,
                "processed_at": log.processed_at.isoformat() if log.processed_at else None,
                "completed_at": log.completed_at.isoformat() if log.completed_at else None,
                "duration_ms": log.duration_ms
            }
            for log in logs
        ]

        logger.info(f"Retrieved {len(logs)} webhook logs")

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total,
            "logs": log_entries
        }

    except Exception as e:
        logger.exception(f"Error listing webhook logs: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to list webhook logs"
        )


@router.get("/stats")
async def get_webhook_logs_stats(
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    subscription_id: Optional[str] = Query(None, description="Filter by subscription"),
    campaign_id: Optional[str] = Query(None, description="Filter by campaign"),
    from_date: Optional[datetime] = Query(None, description="Start date filter"),
    to_date: Optional[datetime] = Query(None, description="End date filter"),
    db: Session = Depends(get_db)
) -> dict:
    """
    Get webhook logs statistics and aggregated metrics.

    **Query Parameters:**
    - `event_type`: Filter statistics by event type
    - `subscription_id`: Filter statistics by subscription
    - `campaign_id`: Filter statistics by campaign
    - `from_date`: Start date for filtering
    - `to_date`: End date for filtering

    **Returns:**
    - Total events processed
    - Delivery success metrics
    - Event type breakdown
    - Subscription statistics
    - Performance metrics (avg duration)

    **Example:**
    ```
    GET /api/webhooks/logs/stats?event_type=exploitation.success
    ```
    """

    try:
        # Build query for logs
        query = db.query(WebhookLog)

        # Apply filters
        if event_type:
            query = query.filter(WebhookLog.event_type == event_type)

        if subscription_id:
            query = query.filter(WebhookLog.subscription_id == subscription_id)

        if campaign_id:
            query = query.filter(WebhookLog.campaign_id == campaign_id)

        if from_date and to_date:
            query = query.filter(
                and_(
                    WebhookLog.processed_at >= from_date,
                    WebhookLog.processed_at <= to_date
                )
            )
        elif from_date:
            query = query.filter(WebhookLog.processed_at >= from_date)
        elif to_date:
            query = query.filter(WebhookLog.processed_at <= to_date)

        logs = query.all()

        if not logs:
            return {
                "total_events": 0,
                "total_deliveries": 0,
                "successful_deliveries": 0,
                "failed_deliveries": 0,
                "success_rate": 0.0,
                "average_duration_ms": 0,
                "event_types": {},
                "subscriptions": {}
            }

        # Calculate aggregates
        total_events = len(logs)
        total_deliveries = sum(log.total_deliveries for log in logs)
        successful_deliveries = sum(log.successful_deliveries for log in logs)
        failed_deliveries = sum(log.failed_deliveries for log in logs)
        success_rate = (
            (successful_deliveries / total_deliveries * 100)
            if total_deliveries > 0
            else 0.0
        )

        # Calculate average duration
        durations = [log.duration_ms for log in logs if log.duration_ms]
        avg_duration = sum(durations) / len(durations) if durations else 0

        # Build event type breakdown
        event_type_stats = {}
        for log in logs:
            if log.event_type not in event_type_stats:
                event_type_stats[log.event_type] = {
                    "count": 0,
                    "total_deliveries": 0,
                    "successful": 0,
                    "failed": 0
                }
            event_type_stats[log.event_type]["count"] += 1
            event_type_stats[log.event_type]["total_deliveries"] += log.total_deliveries
            event_type_stats[log.event_type]["successful"] += log.successful_deliveries
            event_type_stats[log.event_type]["failed"] += log.failed_deliveries

        # Build subscription breakdown
        subscription_stats = {}
        for log in logs:
            if log.subscription_id not in subscription_stats:
                subscription_stats[log.subscription_id] = {
                    "count": 0,
                    "total_deliveries": 0,
                    "successful": 0,
                    "failed": 0
                }
            subscription_stats[log.subscription_id]["count"] += 1
            subscription_stats[log.subscription_id]["total_deliveries"] += log.total_deliveries
            subscription_stats[log.subscription_id]["successful"] += log.successful_deliveries
            subscription_stats[log.subscription_id]["failed"] += log.failed_deliveries

        logger.info("Retrieved webhook logs statistics")

        return {
            "total_events": total_events,
            "total_deliveries": total_deliveries,
            "successful_deliveries": successful_deliveries,
            "failed_deliveries": failed_deliveries,
            "success_rate": success_rate,
            "average_duration_ms": avg_duration,
            "event_types": event_type_stats,
            "subscriptions": subscription_stats
        }

    except Exception as e:
        logger.exception(f"Error getting webhook logs stats: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get webhook logs statistics"
        )


@router.get("/events/{event_id}")
async def get_event_log(
    event_id: str,
    db: Session = Depends(get_db)
) -> dict:
    """
    Get detailed log for a specific event including all delivery attempts.

    **Path Parameters:**
    - `event_id`: The event ID to get logs for

    **Returns:**
    - Event details and type
    - All subscription deliveries for this event
    - Delivery statistics and status breakdown
    - Original event payload

    **Example:**
    ```
    GET /api/webhooks/logs/events/evt_abc123
    ```
    """

    try:
        # Get the main log
        log = db.query(WebhookLog).filter(
            WebhookLog.event_id == event_id
        ).first()

        if not log:
            raise HTTPException(
                status_code=404,
                detail=f"Event {event_id} not found"
            )

        # Get all deliveries for this event
        deliveries = db.query(WebhookDelivery).filter(
            WebhookDelivery.event_id == event_id
        ).all()

        # Group deliveries by status
        status_breakdown = {}
        for delivery in deliveries:
            if delivery.status not in status_breakdown:
                status_breakdown[delivery.status] = {
                    "count": 0,
                    "subscriptions": []
                }
            status_breakdown[delivery.status]["count"] += 1
            if delivery.subscription_id not in status_breakdown[delivery.status]["subscriptions"]:
                status_breakdown[delivery.status]["subscriptions"].append(
                    delivery.subscription_id
                )

        logger.info(f"Retrieved event log: {event_id}")

        return {
            "event_id": event_id,
            "event_type": log.event_type,
            "campaign_id": log.campaign_id,
            "target_id": log.target_id,
            "event_payload": log.event_payload,
            "total_deliveries": log.total_deliveries,
            "successful_deliveries": log.successful_deliveries,
            "failed_deliveries": log.failed_deliveries,
            "success_rate": (
                (log.successful_deliveries / log.total_deliveries * 100)
                if log.total_deliveries > 0
                else 0.0
            ),
            "deliveries": [
                {
                    "id": d.id,
                    "subscription_id": d.subscription_id,
                    "status": d.status,
                    "http_status": d.http_status,
                    "attempt_count": d.attempt_count,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                    "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
                    "last_error": d.last_error
                }
                for d in deliveries
            ],
            "status_breakdown": status_breakdown,
            "processed_at": log.processed_at.isoformat() if log.processed_at else None,
            "completed_at": log.completed_at.isoformat() if log.completed_at else None,
            "duration_ms": log.duration_ms
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting event log: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get event log"
        )


@router.get("/subscriptions/{subscription_id}/activity")
async def get_subscription_activity(
    subscription_id: str,
    from_date: Optional[datetime] = Query(None, description="Start date filter"),
    to_date: Optional[datetime] = Query(None, description="End date filter"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
) -> dict:
    """
    Get detailed activity log for a specific subscription.

    **Path Parameters:**
    - `subscription_id`: The subscription to get activity for

    **Query Parameters:**
    - `from_date`: Start date for filtering
    - `to_date`: End date for filtering
    - `limit`: Results per page (1-500)
    - `offset`: Pagination offset

    **Returns:**
    - Chronological list of all events sent to subscription
    - Delivery status and attempt counts
    - Event types received
    - Performance metrics

    **Example:**
    ```
    GET /api/webhooks/logs/subscriptions/sub_xyz789/activity
    ```
    """

    try:
        # Get logs for subscription
        query = db.query(WebhookLog).filter(
            WebhookLog.subscription_id == subscription_id
        )

        if from_date and to_date:
            query = query.filter(
                and_(
                    WebhookLog.processed_at >= from_date,
                    WebhookLog.processed_at <= to_date
                )
            )
        elif from_date:
            query = query.filter(WebhookLog.processed_at >= from_date)
        elif to_date:
            query = query.filter(WebhookLog.processed_at <= to_date)

        total = query.count()

        logs = query.order_by(
            desc(WebhookLog.processed_at)
        ).limit(limit).offset(offset).all()

        # Get delivery statistics for period
        all_logs = db.query(WebhookLog).filter(
            WebhookLog.subscription_id == subscription_id
        ).all()

        total_deliveries = sum(log.total_deliveries for log in all_logs)
        successful_deliveries = sum(log.successful_deliveries for log in all_logs)
        failed_deliveries = sum(log.failed_deliveries for log in all_logs)

        logger.info(f"Retrieved subscription activity: {subscription_id}")

        return {
            "subscription_id": subscription_id,
            "total_events": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total,
            "statistics": {
                "total_deliveries": total_deliveries,
                "successful_deliveries": successful_deliveries,
                "failed_deliveries": failed_deliveries,
                "success_rate": (
                    (successful_deliveries / total_deliveries * 100)
                    if total_deliveries > 0
                    else 0.0
                )
            },
            "events": [
                {
                    "event_id": log.event_id,
                    "event_type": log.event_type,
                    "campaign_id": log.campaign_id,
                    "total_deliveries": log.total_deliveries,
                    "successful": log.successful_deliveries,
                    "failed": log.failed_deliveries,
                    "processed_at": log.processed_at.isoformat() if log.processed_at else None,
                    "duration_ms": log.duration_ms
                }
                for log in logs
            ]
        }

    except Exception as e:
        logger.exception(f"Error getting subscription activity: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get subscription activity"
        )
