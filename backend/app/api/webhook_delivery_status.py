"""
Webhook Delivery Status API (Phase 3.4).

REST endpoints for querying webhook delivery history with filtering and pagination.
"""

import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, asc

from app.database import get_db
from app.models import WebhookDelivery, WebhookDeliveryStatus, AuditLog
from app.schemas.webhook_delivery import (
    WebhookDeliveryDetail,
    WebhookDeliveryListResponse,
    WebhookDeliveryStatsResponse,
    WebhookDeliveryRetryResponse,
    WebhookDeliveryBatchRetryRequest,
    WebhookDeliveryBatchRetryResponse,
    WebhookDeliveryError
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks/deliveries", tags=["webhook-deliveries"])


@router.get(
    "",
    response_model=WebhookDeliveryListResponse,
    responses={
        400: {"model": WebhookDeliveryError},
        500: {"model": WebhookDeliveryError}
    }
)
async def list_deliveries(
    status: Optional[str] = Query(None, description="Filter by status"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    subscription_id: Optional[str] = Query(None, description="Filter by subscription"),
    event_id: Optional[str] = Query(None, description="Filter by event"),
    campaign_id: Optional[str] = Query(None, description="Filter by campaign"),
    from_date: Optional[datetime] = Query(None, description="Start date filter"),
    to_date: Optional[datetime] = Query(None, description="End date filter"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("created_at", regex="^(created_at|status|http_status)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: Session = Depends(get_db)
) -> WebhookDeliveryListResponse:
    """
    List webhook deliveries with filtering and pagination.

    **Query Parameters:**
    - `status`: Filter by delivery status (pending, delivered, retrying, failed)
    - `event_type`: Filter by event type (e.g., exploitation.success)
    - `subscription_id`: Filter by subscription ID
    - `event_id`: Filter by event ID
    - `campaign_id`: Filter by campaign ID
    - `from_date`: Only include deliveries after this date
    - `to_date`: Only include deliveries before this date
    - `limit`: Results per page (1-500, default 50)
    - `offset`: Pagination offset (default 0)
    - `sort_by`: Sort field (created_at, status, http_status)
    - `sort_order`: Sort order (asc, desc)

    **Example:**
    ```
    GET /api/webhooks/deliveries?status=failed&limit=10&offset=0
    ```
    """

    try:
        # Build query
        query = db.query(WebhookDelivery)

        # Apply filters
        if status:
            if status not in [s.value for s in WebhookDeliveryStatus]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status: {status}"
                )
            query = query.filter(WebhookDelivery.status == status)

        if event_type:
            query = query.filter(WebhookDelivery.event_type == event_type)

        if subscription_id:
            query = query.filter(WebhookDelivery.subscription_id == subscription_id)

        if event_id:
            query = query.filter(WebhookDelivery.event_id == event_id)

        if campaign_id:
            query = query.filter(WebhookDelivery.campaign_id == campaign_id)

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

        # Get total count
        total = query.count()

        # Apply sorting
        sort_column = getattr(WebhookDelivery, sort_by)
        if sort_order == "desc":
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(asc(sort_column))

        # Apply pagination
        deliveries = query.limit(limit).offset(offset).all()

        # Convert to schema
        delivery_details = [
            WebhookDeliveryDetail.from_orm(d) for d in deliveries
        ]

        return WebhookDeliveryListResponse(
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total,
            deliveries=delivery_details
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error listing deliveries: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to list deliveries"
        )


@router.get(
    "/stats",
    response_model=WebhookDeliveryStatsResponse,
    responses={
        500: {"model": WebhookDeliveryError}
    }
)
async def get_delivery_stats(
    subscription_id: Optional[str] = Query(None),
    event_id: Optional[str] = Query(None),
    campaign_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
) -> WebhookDeliveryStatsResponse:
    """
    Get delivery statistics summary.

    **Query Parameters:**
    - `subscription_id`: Stats for specific subscription
    - `event_id`: Stats for specific event
    - `campaign_id`: Stats for specific campaign

    **Returns:**
    - Delivery counts by status
    - Success rate percentage
    - Average attempts per delivery
    - Date range of deliveries
    """

    try:
        # Build query
        query = db.query(WebhookDelivery)

        if subscription_id:
            query = query.filter(WebhookDelivery.subscription_id == subscription_id)
        if event_id:
            query = query.filter(WebhookDelivery.event_id == event_id)
        if campaign_id:
            query = query.filter(WebhookDelivery.campaign_id == campaign_id)

        deliveries = query.all()

        if not deliveries:
            return WebhookDeliveryStatsResponse(
                subscription_id=subscription_id,
                event_id=event_id,
                total_deliveries=0,
                successful=0,
                pending=0,
                retrying=0,
                failed=0,
                success_rate=0.0,
                average_attempts=0.0
            )

        # Calculate stats
        total = len(deliveries)
        successful = sum(1 for d in deliveries if d.status == WebhookDeliveryStatus.delivered.value)
        pending = sum(1 for d in deliveries if d.status == WebhookDeliveryStatus.pending.value)
        retrying = sum(1 for d in deliveries if d.status == WebhookDeliveryStatus.retrying.value)
        failed = sum(1 for d in deliveries if d.status == WebhookDeliveryStatus.failed.value)

        success_rate = (successful / total * 100) if total > 0 else 0.0
        average_attempts = sum(d.attempt_count for d in deliveries) / total if total > 0 else 0.0

        dates = [d.created_at for d in deliveries if d.created_at]
        latest = max(dates) if dates else None
        earliest = min(dates) if dates else None

        return WebhookDeliveryStatsResponse(
            subscription_id=subscription_id,
            event_id=event_id,
            total_deliveries=total,
            successful=successful,
            pending=pending,
            retrying=retrying,
            failed=failed,
            success_rate=success_rate,
            average_attempts=average_attempts,
            latest_delivery=latest,
            earliest_delivery=earliest
        )

    except Exception as e:
        logger.exception(f"Error getting delivery stats: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get delivery statistics"
        )


@router.get(
    "/{delivery_id}",
    response_model=WebhookDeliveryDetail,
    responses={
        404: {"model": WebhookDeliveryError},
        500: {"model": WebhookDeliveryError}
    }
)
async def get_delivery_detail(
    delivery_id: str,
    db: Session = Depends(get_db)
) -> WebhookDeliveryDetail:
    """
    Get detailed delivery record.

    **Path Parameters:**
    - `delivery_id`: The delivery ID to retrieve

    **Returns:**
    - Complete delivery record with all details
    """

    try:
        delivery = db.query(WebhookDelivery).filter(
            WebhookDelivery.id == delivery_id
        ).first()

        if not delivery:
            raise HTTPException(
                status_code=404,
                detail=f"Delivery {delivery_id} not found"
            )

        logger.info(f"Retrieved delivery details: {delivery_id}")

        return WebhookDeliveryDetail.from_orm(delivery)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting delivery detail: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get delivery details"
        )


@router.get(
    "/subscriptions/{subscription_id}/deliveries",
    response_model=WebhookDeliveryListResponse
)
async def get_subscription_deliveries(
    subscription_id: str,
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
) -> WebhookDeliveryListResponse:
    """
    Get delivery history for a specific subscription.

    **Path Parameters:**
    - `subscription_id`: The subscription to query

    **Query Parameters:**
    - `status`: Filter by status
    - `limit`: Results per page
    - `offset`: Pagination offset

    **Returns:**
    - Paginated delivery history for subscription
    """

    try:
        query = db.query(WebhookDelivery).filter(
            WebhookDelivery.subscription_id == subscription_id
        )

        if status:
            query = query.filter(WebhookDelivery.status == status)

        total = query.count()

        deliveries = query.order_by(
            desc(WebhookDelivery.created_at)
        ).limit(limit).offset(offset).all()

        delivery_details = [
            WebhookDeliveryDetail.from_orm(d) for d in deliveries
        ]

        logger.info(
            f"Retrieved {len(deliveries)} deliveries for subscription {subscription_id}"
        )

        return WebhookDeliveryListResponse(
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total,
            deliveries=delivery_details
        )

    except Exception as e:
        logger.exception(f"Error getting subscription deliveries: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get subscription deliveries"
        )


@router.post(
    "/{delivery_id}/retry",
    response_model=WebhookDeliveryRetryResponse
)
async def retry_delivery(
    delivery_id: str,
    db: Session = Depends(get_db)
) -> WebhookDeliveryRetryResponse:
    """
    Manually retry a failed delivery.

    **Path Parameters:**
    - `delivery_id`: The delivery to retry

    **Returns:**
    - Retry scheduling confirmation
    """

    try:
        delivery = db.query(WebhookDelivery).filter(
            WebhookDelivery.id == delivery_id
        ).first()

        if not delivery:
            raise HTTPException(
                status_code=404,
                detail=f"Delivery {delivery_id} not found"
            )

        # Check if max retries exceeded
        if delivery.attempt_count >= delivery.max_attempts:
            raise HTTPException(
                status_code=400,
                detail=f"Delivery has exceeded max retries ({delivery.max_attempts})"
            )

        # Reset to pending for retry
        delivery.status = WebhookDeliveryStatus.pending.value
        delivery.next_retry_at = None
        db.commit()

        # Log the action
        audit_log = AuditLog(
            action="webhook_delivery_retry",
            details={
                "delivery_id": delivery_id,
                "subscription_id": delivery.subscription_id,
                "event_id": delivery.event_id
            }
        )
        db.add(audit_log)
        db.commit()

        logger.info(f"Scheduled retry for delivery: {delivery_id}")

        return WebhookDeliveryRetryResponse(
            delivery_id=delivery_id,
            scheduled_for=datetime.utcnow(),
            attempt_number=delivery.attempt_count + 1,
            message=f"Delivery queued for immediate retry (attempt {delivery.attempt_count + 1})"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrying delivery: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retry delivery"
        )
