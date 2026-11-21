"""
Webhook Metrics API (Phase 4.1).

REST endpoints for webhook metrics dashboard and analytics.
"""

import logging
from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.database import get_db
from app.models import WebhookDelivery, WebhookLog, WebhookDeliveryStatus
from app.schemas.webhook_metrics import (
    MetricsDashboard,
    MetricsOverview,
    HealthStatus,
    PerformanceTrends,
    TrendPoint,
    FailureAnalysis,
    SubscriptionMetrics,
    EventTypeMetrics,
    SubscriptionMetricsResponse,
    AnalyticsResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks/metrics", tags=["webhook-metrics"])


@router.get("/overview")
async def get_metrics_overview(db: Session = Depends(get_db)) -> MetricsOverview:
    """
    Get system-wide webhook metrics overview.

    **Returns:**
    - Total events and deliveries
    - Success rate
    - Average delivery time
    - Current pending and retrying counts

    **Example:**
    ```
    GET /api/webhooks/metrics/overview
    ```
    """

    try:
        # Get aggregate metrics
        deliveries = db.query(WebhookDelivery).all()

        if not deliveries:
            return MetricsOverview(
                total_events=0,
                total_deliveries=0,
                success_rate=0.0,
                average_delivery_time_ms=0,
                current_pending=0,
                current_retrying=0,
                failed_today=0
            )

        total_deliveries = len(deliveries)
        successful = sum(1 for d in deliveries if d.status == WebhookDeliveryStatus.delivered.value)
        pending = sum(1 for d in deliveries if d.status == WebhookDeliveryStatus.pending.value)
        retrying = sum(1 for d in deliveries if d.status == WebhookDeliveryStatus.retrying.value)

        # Calculate average delivery time
        delivered = [d for d in deliveries if d.delivered_at and d.created_at]
        if delivered:
            avg_time = sum(
                (d.delivered_at - d.created_at).total_seconds() * 1000
                for d in delivered
            ) / len(delivered)
        else:
            avg_time = 0

        # Count failures today
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        failed_today = sum(
            1 for d in deliveries
            if d.status == WebhookDeliveryStatus.failed.value and d.created_at >= today
        )

        success_rate = (successful / total_deliveries * 100) if total_deliveries > 0 else 0

        logger.info("Retrieved metrics overview")

        return MetricsOverview(
            total_events=len(set(d.event_id for d in deliveries)),
            total_deliveries=total_deliveries,
            success_rate=success_rate,
            average_delivery_time_ms=avg_time,
            current_pending=pending,
            current_retrying=retrying,
            failed_today=failed_today
        )

    except Exception as e:
        logger.exception(f"Error getting metrics overview: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get metrics overview"
        )


@router.get("/health")
async def get_health_metrics(db: Session = Depends(get_db)) -> HealthStatus:
    """
    Get webhook system health status.

    **Returns:**
    - Health status (healthy, degraded, unhealthy)
    - Success rate and response times
    - Uptime percentage

    **Example:**
    ```
    GET /api/webhooks/metrics/health
    ```
    """

    try:
        deliveries = db.query(WebhookDelivery).all()

        if not deliveries:
            return HealthStatus(
                status="healthy",
                success_rate=100.0,
                average_response_time_ms=0,
                p95_response_time_ms=0,
                p99_response_time_ms=0,
                failure_rate_1h=0.0,
                uptime_percentage=100.0,
                last_check=datetime.utcnow()
            )

        # Calculate success rate
        successful = sum(1 for d in deliveries if d.status == WebhookDeliveryStatus.delivered.value)
        success_rate = (successful / len(deliveries) * 100) if deliveries else 0

        # Calculate response times
        delivered = [d for d in deliveries if d.delivered_at and d.created_at]
        if delivered:
            times = sorted(
                [(d.delivered_at - d.created_at).total_seconds() * 1000 for d in delivered]
            )
            avg_time = sum(times) / len(times)
            p95_idx = int(len(times) * 0.95)
            p99_idx = int(len(times) * 0.99)
            p95_time = times[p95_idx] if p95_idx < len(times) else times[-1]
            p99_time = times[p99_idx] if p99_idx < len(times) else times[-1]
        else:
            avg_time = p95_time = p99_time = 0

        # Failure rate in last hour
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        recent_deliveries = [d for d in deliveries if d.created_at >= one_hour_ago]
        recent_failures = sum(
            1 for d in recent_deliveries if d.status == WebhookDeliveryStatus.failed.value
        )
        failure_rate_1h = (
            (recent_failures / len(recent_deliveries) * 100)
            if recent_deliveries
            else 0
        )

        # Determine health status
        if success_rate >= 95:
            status = "healthy"
        elif success_rate >= 85:
            status = "degraded"
        else:
            status = "unhealthy"

        logger.info(f"Health check: {status} (success_rate={success_rate}%)")

        return HealthStatus(
            status=status,
            success_rate=success_rate,
            average_response_time_ms=avg_time,
            p95_response_time_ms=p95_time,
            p99_response_time_ms=p99_time,
            failure_rate_1h=failure_rate_1h,
            uptime_percentage=success_rate,
            last_check=datetime.utcnow()
        )

    except Exception as e:
        logger.exception(f"Error getting health metrics: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get health metrics"
        )


@router.get("/subscriptions/{subscription_id}")
async def get_subscription_metrics(
    subscription_id: str,
    db: Session = Depends(get_db)
) -> SubscriptionMetricsResponse:
    """
    Get detailed metrics for a specific subscription.

    **Path Parameters:**
    - `subscription_id`: The subscription to get metrics for

    **Returns:**
    - Subscription metrics and status
    - Recent failures
    - Trend data

    **Example:**
    ```
    GET /api/webhooks/metrics/subscriptions/sub_xyz789
    ```
    """

    try:
        # Get deliveries for this subscription
        deliveries = db.query(WebhookDelivery).filter(
            WebhookDelivery.subscription_id == subscription_id
        ).all()

        if not deliveries:
            raise HTTPException(
                status_code=404,
                detail=f"Subscription {subscription_id} not found"
            )

        # Calculate metrics
        total = len(deliveries)
        successful = sum(1 for d in deliveries if d.status == WebhookDeliveryStatus.delivered.value)
        failed = sum(1 for d in deliveries if d.status == WebhookDeliveryStatus.failed.value)
        success_rate = (successful / total * 100) if total > 0 else 0

        # Calculate response times
        delivered = [d for d in deliveries if d.delivered_at and d.created_at]
        if delivered:
            times = sorted(
                [(d.delivered_at - d.created_at).total_seconds() * 1000 for d in delivered]
            )
            avg_time = sum(times) / len(times)
            p95_idx = int(len(times) * 0.95)
            p95_time = times[p95_idx] if p95_idx < len(times) else times[-1]
        else:
            avg_time = p95_time = 0

        # Determine status
        if success_rate >= 95:
            status = "healthy"
        elif success_rate >= 80:
            status = "degraded"
        else:
            status = "failing"

        # Get recent failures
        recent_failures = [
            {
                "event_id": d.event_id,
                "status": d.status,
                "error": d.last_error,
                "attempts": d.attempt_count,
                "timestamp": d.created_at.isoformat() if d.created_at else None
            }
            for d in sorted(deliveries, key=lambda x: x.created_at or datetime.min)[-10:]
            if d.status == WebhookDeliveryStatus.failed.value
        ]

        # Create trend data
        trend_data = []
        for delivery in sorted(deliveries, key=lambda x: x.created_at or datetime.min)[-24:]:
            if delivery.created_at:
                trend_data.append(
                    TrendPoint(
                        timestamp=delivery.created_at,
                        success_rate=success_rate,
                        throughput=len(deliveries),
                        average_response_time_ms=avg_time,
                        failure_count=failed
                    )
                )

        metrics = SubscriptionMetrics(
            subscription_id=subscription_id,
            total_events=len(set(d.event_id for d in deliveries)),
            successful_deliveries=successful,
            failed_deliveries=failed,
            success_rate=success_rate,
            average_response_time_ms=avg_time,
            p95_response_time_ms=p95_time,
            retry_success_rate=0.0,  # TODO: Calculate from retry logs
            last_delivery_at=max(
                (d.delivered_at for d in deliveries if d.delivered_at),
                default=None
            ),
            status=status
        )

        logger.info(f"Retrieved metrics for subscription {subscription_id}")

        return SubscriptionMetricsResponse(
            subscription_id=subscription_id,
            metrics=metrics,
            recent_failures=recent_failures,
            trend_data=trend_data
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting subscription metrics: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get subscription metrics"
        )
