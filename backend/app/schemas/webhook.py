"""
Pydantic schemas for webhook API.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, HttpUrl


class WebhookSubscriptionCreate(BaseModel):
    """Request to create webhook subscription."""

    url: HttpUrl = Field(..., description="Webhook URL")
    event_types: List[str] = Field(..., description="Event types to subscribe to")
    campaign_id: Optional[str] = Field(None, description="Optional campaign filter")
    target_id: Optional[str] = Field(None, description="Optional target filter")
    secret: Optional[str] = Field(None, description="Optional HMAC secret")

    class Config:
        schema_extra = {
            "example": {
                "url": "https://example.com/webhook",
                "event_types": ["exploitation.success", "session.created"],
                "campaign_id": "camp-001",
                "secret": "my-secret-key"
            }
        }


class WebhookSubscriptionResponse(BaseModel):
    """Webhook subscription response."""

    id: str
    url: str
    event_types: List[str]
    campaign_id: Optional[str] = None
    target_id: Optional[str] = None
    active: bool
    created_at: str


class WebhookSubscriptionList(BaseModel):
    """List of webhook subscriptions."""

    subscriptions: List[WebhookSubscriptionResponse]
    total: int


class WebhookEventPayload(BaseModel):
    """Webhook event payload."""

    event_type: str
    campaign_id: str
    target_id: str
    timestamp: str
    event_id: str
    data: Dict[str, Any]


class WebhookDispatchResult(BaseModel):
    """Webhook dispatch result."""

    subscription_id: str
    url: str
    success: bool
    error: Optional[str] = None


class WebhookDispatchResponse(BaseModel):
    """Webhook event dispatch response."""

    event_id: str
    event_type: str
    total_subscriptions: int
    delivered: int
    failed: int
    results: List[WebhookDispatchResult]


class WebhookUnsubscribeResponse(BaseModel):
    """Webhook unsubscribe response."""

    message: str
    subscription_id: str
    removed: bool


class WebhookError(BaseModel):
    """Webhook error response."""

    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Error details")
    subscription_id: Optional[str] = Field(None, description="Related subscription if applicable")
