"""
Webhook Metrics Schemas (Phase 4.1).

Pydantic models for metrics dashboard and analytics responses.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class MetricsOverview(BaseModel):
    """System-wide webhook metrics overview."""

    total_events: int = Field(..., description="Total events processed")
    total_deliveries: int = Field(..., description="Total delivery attempts")
    success_rate: float = Field(..., description="Success rate percentage (0-100)")
    average_delivery_time_ms: float = Field(..., description="Average delivery time in ms")
    current_pending: int = Field(..., description="Currently pending deliveries")
    current_retrying: int = Field(..., description="Currently retrying deliveries")
    failed_today: int = Field(..., description="Failed deliveries today")


class HealthStatus(BaseModel):
    """Webhook system health status."""

    status: str = Field(..., description="Health status (healthy, degraded, unhealthy)")
    success_rate: float = Field(..., description="Success rate percentage")
    average_response_time_ms: float = Field(..., description="Average response time")
    p95_response_time_ms: float = Field(..., description="95th percentile response time")
    p99_response_time_ms: float = Field(..., description="99th percentile response time")
    failure_rate_1h: float = Field(..., description="Failure rate in last hour")
    uptime_percentage: float = Field(..., description="System uptime percentage")
    last_check: datetime = Field(..., description="Last health check timestamp")


class TrendPoint(BaseModel):
    """Single point in a metrics trend."""

    timestamp: datetime = Field(..., description="Timestamp of data point")
    success_rate: float = Field(..., description="Success rate at this point")
    throughput: int = Field(..., description="Events processed at this point")
    average_response_time_ms: float = Field(..., description="Average response time")
    failure_count: int = Field(..., description="Number of failures")


class PerformanceTrends(BaseModel):
    """Performance trends over time."""

    period: str = Field(..., description="Time period (1h, 6h, 24h, 7d)")
    data_points: List[TrendPoint] = Field(..., description="Trend data points")
    overall_success_rate: float = Field(..., description="Success rate for period")
    peak_throughput: int = Field(..., description="Peak throughput during period")
    lowest_success_rate: float = Field(..., description="Lowest success rate during period")


class FailureAnalysis(BaseModel):
    """Analysis of delivery failures."""

    total_failures: int = Field(..., description="Total failures in period")
    failure_rate: float = Field(..., description="Failure rate percentage")
    top_error_types: Dict[str, int] = Field(..., description="Most common error types")
    subscriptions_with_failures: int = Field(..., description="Number of subscriptions with failures")
    critical_failures: int = Field(..., description="Critical failures requiring attention")
    recoverable_failures: int = Field(..., description="Failures that recovered on retry")


class SubscriptionMetrics(BaseModel):
    """Metrics for a specific subscription."""

    subscription_id: str = Field(..., description="Subscription ID")
    total_events: int = Field(..., description="Total events sent to this subscription")
    successful_deliveries: int = Field(..., description="Successful deliveries")
    failed_deliveries: int = Field(..., description="Failed deliveries")
    success_rate: float = Field(..., description="Success rate percentage")
    average_response_time_ms: float = Field(..., description="Average response time")
    p95_response_time_ms: float = Field(..., description="95th percentile response time")
    retry_success_rate: float = Field(..., description="Success rate of retries")
    last_delivery_at: Optional[datetime] = Field(None, description="Last successful delivery")
    status: str = Field(..., description="Current status (healthy, degraded, failing)")


class EventTypeMetrics(BaseModel):
    """Metrics breakdown by event type."""

    event_type: str = Field(..., description="Event type")
    total_events: int = Field(..., description="Total events of this type")
    success_rate: float = Field(..., description="Success rate for this type")
    average_response_time_ms: float = Field(..., description="Average response time")
    failure_count: int = Field(..., description="Number of failures")
    subscriptions_using: int = Field(..., description="Number of subscriptions using this type")


class MetricsDashboard(BaseModel):
    """Complete metrics dashboard response."""

    overview: MetricsOverview = Field(..., description="System-wide overview")
    health_status: HealthStatus = Field(..., description="Current health status")
    performance_trends: PerformanceTrends = Field(..., description="Performance trends")
    failure_analysis: FailureAnalysis = Field(..., description="Failure analysis")
    top_subscriptions: List[SubscriptionMetrics] = Field(
        ..., description="Top subscriptions by activity"
    )
    event_types: List[EventTypeMetrics] = Field(
        ..., description="Metrics by event type"
    )
    generated_at: datetime = Field(..., description="When metrics were generated")


class SubscriptionMetricsResponse(BaseModel):
    """Subscription-specific metrics response."""

    subscription_id: str = Field(..., description="Subscription ID")
    metrics: SubscriptionMetrics = Field(..., description="Detailed metrics")
    recent_failures: List[Dict[str, Any]] = Field(..., description="Recent failures")
    trend_data: List[TrendPoint] = Field(..., description="Trend data for this subscription")


class AnalyticsResponse(BaseModel):
    """Analytics query response."""

    period: str = Field(..., description="Analysis period")
    event_types: Dict[str, EventTypeMetrics] = Field(..., description="Per-event-type metrics")
    subscriptions: Dict[str, SubscriptionMetrics] = Field(..., description="Per-subscription metrics")
    top_performers: List[str] = Field(..., description="Best performing subscriptions")
    struggling_subscribers: List[str] = Field(..., description="Subscriptions with high failure rates")
    recommendations: List[str] = Field(..., description="Improvement recommendations")
