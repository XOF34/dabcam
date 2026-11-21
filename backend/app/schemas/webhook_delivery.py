"""
Webhook Delivery Status Schemas (Phase 3.4).

Pydantic models for delivery tracking API responses.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class WebhookDeliveryDetail(BaseModel):
    """Single webhook delivery record."""

    id: str = Field(..., description="Delivery ID")
    subscription_id: str = Field(..., description="Subscription ID")
    event_id: str = Field(..., description="Event ID")
    event_type: str = Field(..., description="Event type (e.g., exploitation.success)")
    campaign_id: Optional[str] = Field(None, description="Campaign ID")
    target_id: Optional[str] = Field(None, description="Target ID")
    url: str = Field(..., description="Webhook URL")
    status: str = Field(..., description="Delivery status (pending, delivered, retrying, failed)")
    http_status: Optional[int] = Field(None, description="HTTP response status code")
    attempt_count: int = Field(..., description="Number of delivery attempts")
    max_attempts: int = Field(..., description="Maximum retry attempts")
    created_at: datetime = Field(..., description="When delivery was first attempted")
    delivered_at: Optional[datetime] = Field(None, description="When delivery succeeded")
    next_retry_at: Optional[datetime] = Field(None, description="When next retry is scheduled")
    last_error: Optional[str] = Field(None, description="Last error message")
    response_body: Optional[str] = Field(None, description="Response body (truncated)")

    class Config:
        from_attributes = True


class WebhookDeliveryListRequest(BaseModel):
    """Request parameters for delivery listing."""

    status: Optional[str] = Field(
        None,
        description="Filter by status (pending, delivered, retrying, failed)"
    )
    event_type: Optional[str] = Field(
        None,
        description="Filter by event type (e.g., exploitation.success)"
    )
    subscription_id: Optional[str] = Field(
        None,
        description="Filter by subscription ID"
    )
    event_id: Optional[str] = Field(
        None,
        description="Filter by event ID"
    )
    campaign_id: Optional[str] = Field(
        None,
        description="Filter by campaign ID"
    )
    from_date: Optional[datetime] = Field(
        None,
        description="Only deliveries after this date"
    )
    to_date: Optional[datetime] = Field(
        None,
        description="Only deliveries before this date"
    )
    limit: int = Field(50, ge=1, le=500, description="Results per page")
    offset: int = Field(0, ge=0, description="Pagination offset")
    sort_by: str = Field(
        "created_at",
        description="Sort field (created_at, status, http_status)"
    )
    sort_order: str = Field(
        "desc",
        description="Sort order (asc, desc)"
    )


class WebhookDeliveryListResponse(BaseModel):
    """Response for delivery listing."""

    total: int = Field(..., description="Total deliveries matching filter")
    limit: int = Field(..., description="Results per page")
    offset: int = Field(..., description="Current offset")
    has_more: bool = Field(..., description="Whether more results available")
    deliveries: List[WebhookDeliveryDetail] = Field(..., description="Delivery records")

    class Config:
        from_attributes = True


class WebhookDeliveryStatsResponse(BaseModel):
    """Delivery statistics summary."""

    subscription_id: Optional[str] = Field(None, description="Subscription ID (if filtered)")
    event_id: Optional[str] = Field(None, description="Event ID (if filtered)")
    total_deliveries: int = Field(..., description="Total deliveries")
    successful: int = Field(..., description="Successfully delivered")
    pending: int = Field(..., description="Pending delivery")
    retrying: int = Field(..., description="Scheduled for retry")
    failed: int = Field(..., description="Failed permanently")
    success_rate: float = Field(..., description="Percentage successful (0-100)")
    average_attempts: float = Field(..., description="Average attempts per delivery")
    latest_delivery: Optional[datetime] = Field(None, description="Most recent delivery")
    earliest_delivery: Optional[datetime] = Field(None, description="Oldest delivery")

    class Config:
        from_attributes = True


class WebhookDeliveryRetryResponse(BaseModel):
    """Response for retry scheduling."""

    delivery_id: str = Field(..., description="Delivery ID")
    scheduled_for: datetime = Field(..., description="When retry is scheduled")
    attempt_number: int = Field(..., description="Next attempt number")
    message: str = Field(..., description="Status message")


class WebhookDeliveryBatchRetryRequest(BaseModel):
    """Request to retry multiple deliveries."""

    filters: Dict[str, Any] = Field(
        ...,
        description="Filters to identify deliveries to retry"
    )
    max_retries: int = Field(
        5,
        ge=1,
        le=10,
        description="Maximum retry attempts to allow"
    )


class WebhookDeliveryBatchRetryResponse(BaseModel):
    """Response for batch retry operation."""

    queued_for_retry: int = Field(..., description="Deliveries queued for retry")
    already_delivered: int = Field(..., description="Deliveries already successful")
    max_retries_exceeded: int = Field(..., description="Deliveries that exceeded max retries")
    total_processed: int = Field(..., description="Total deliveries processed")
    message: str = Field(..., description="Summary message")


class WebhookDeliveryError(BaseModel):
    """Error response."""

    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
    status_code: int = Field(..., description="HTTP status code")
