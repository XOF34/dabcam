"""
Webhook Management API endpoints.

Manages webhook subscriptions for MSF bridge events.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.webhook_manager import (
    get_webhook_manager,
    WebhookEventType,
    WebhookPayload
)
from app.schemas.webhook import (
    WebhookSubscriptionCreate,
    WebhookSubscriptionResponse,
    WebhookSubscriptionList,
    WebhookUnsubscribeResponse,
    WebhookError
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post(
    "/subscribe",
    response_model=WebhookSubscriptionResponse,
    responses={
        400: {"model": WebhookError, "description": "Invalid request"},
        500: {"model": WebhookError, "description": "Failed to create subscription"}
    }
)
async def subscribe_to_webhooks(
    request: WebhookSubscriptionCreate,
    db: Session = Depends(get_db)
) -> WebhookSubscriptionResponse:
    """
    Subscribe to webhook events.

    **Event Types**:
    - `exploitation.started` - Exploitation workflow started
    - `exploitation.success` - Exploitation successful
    - `exploitation.failed` - Exploitation failed
    - `session.created` - New session established
    - `session.active` - Session activity detected
    - `session.closed` - Session closed
    - `command.executed` - Command executed successfully
    - `command.failed` - Command execution failed
    - `post_module.executed` - Post-exploitation module executed
    - `post_module.failed` - Post-exploitation module failed
    - `c2.established` - C2 channel established
    - `c2.lost` - C2 channel lost

    **Webhook Delivery**:
    - Webhooks are POST requests to the provided URL
    - Each webhook includes event type and details in JSON
    - Headers include X-Webhook-Event and X-Webhook-ID
    - Timeout: 10 seconds per request
    """

    try:
        # Validate event types
        valid_event_types = [e.value for e in WebhookEventType]
        for event_type in request.event_types:
            if event_type not in valid_event_types:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid event type: {event_type}"
                )

        # Convert event type strings to enums
        events = [WebhookEventType(et) for et in request.event_types]

        # Subscribe
        manager = get_webhook_manager()
        subscription = manager.subscribe(
            url=str(request.url),
            event_types=events,
            campaign_id=request.campaign_id,
            target_id=request.target_id,
            secret=request.secret
        )

        logger.info(
            f"✅ Webhook subscription created: {subscription.id} → {subscription.url}"
        )

        return WebhookSubscriptionResponse(
            id=subscription.id,
            url=subscription.url,
            event_types=[e.value for e in subscription.event_types],
            campaign_id=subscription.campaign_id,
            target_id=subscription.target_id,
            active=subscription.active,
            created_at=subscription.created_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Webhook subscription failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create subscription"
        )


@router.get(
    "/subscriptions",
    response_model=WebhookSubscriptionList,
    responses={
        500: {"model": WebhookError, "description": "Failed to list subscriptions"}
    }
)
async def list_webhooks(
    campaign_id: str = None,
    event_type: str = None,
    db: Session = Depends(get_db)
) -> WebhookSubscriptionList:
    """
    List webhook subscriptions.

    **Filters**:
    - `campaign_id`: Filter by campaign
    - `event_type`: Filter by event type (e.g., "exploitation.success")
    """

    try:
        manager = get_webhook_manager()

        # Convert event type filter
        event_enum = None
        if event_type:
            try:
                event_enum = WebhookEventType(event_type)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid event type: {event_type}"
                )

        # List subscriptions
        subscriptions = manager.list_subscriptions(
            campaign_id=campaign_id,
            event_type=event_enum
        )

        return WebhookSubscriptionList(
            subscriptions=[
                WebhookSubscriptionResponse(
                    id=s.id,
                    url=s.url,
                    event_types=[e.value for e in s.event_types],
                    campaign_id=s.campaign_id,
                    target_id=s.target_id,
                    active=s.active,
                    created_at=s.created_at
                )
                for s in subscriptions
            ],
            total=len(subscriptions)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to list subscriptions: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to list subscriptions"
        )


@router.delete(
    "/subscriptions/{subscription_id}",
    response_model=WebhookUnsubscribeResponse,
    responses={
        404: {"model": WebhookError, "description": "Subscription not found"},
        500: {"model": WebhookError, "description": "Failed to unsubscribe"}
    }
)
async def unsubscribe_from_webhooks(
    subscription_id: str,
    db: Session = Depends(get_db)
) -> WebhookUnsubscribeResponse:
    """
    Unsubscribe from webhooks.

    Removes the webhook subscription and stops event delivery.
    """

    try:
        manager = get_webhook_manager()

        success = manager.unsubscribe(subscription_id)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Subscription {subscription_id} not found"
            )

        logger.info(f"✅ Webhook subscription removed: {subscription_id}")

        return WebhookUnsubscribeResponse(
            message="Subscription removed successfully",
            subscription_id=subscription_id,
            removed=True
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unsubscribe failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to unsubscribe"
        )


@router.get(
    "/subscriptions/{subscription_id}",
    response_model=WebhookSubscriptionResponse,
    responses={
        404: {"model": WebhookError, "description": "Subscription not found"}
    }
)
async def get_webhook_subscription(
    subscription_id: str,
    db: Session = Depends(get_db)
) -> WebhookSubscriptionResponse:
    """
    Get webhook subscription details.

    Retrieves information about a specific webhook subscription.
    """

    try:
        manager = get_webhook_manager()

        # Find subscription
        if subscription_id not in manager.subscriptions:
            raise HTTPException(
                status_code=404,
                detail=f"Subscription {subscription_id} not found"
            )

        subscription = manager.subscriptions[subscription_id]

        return WebhookSubscriptionResponse(
            id=subscription.id,
            url=subscription.url,
            event_types=[e.value for e in subscription.event_types],
            campaign_id=subscription.campaign_id,
            target_id=subscription.target_id,
            active=subscription.active,
            created_at=subscription.created_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get subscription: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve subscription"
        )


@router.post(
    "/subscriptions/{subscription_id}/toggle",
    response_model=WebhookSubscriptionResponse,
    responses={
        404: {"model": WebhookError, "description": "Subscription not found"}
    }
)
async def toggle_webhook_subscription(
    subscription_id: str,
    db: Session = Depends(get_db)
) -> WebhookSubscriptionResponse:
    """
    Enable or disable webhook subscription.

    Toggles the active state of a subscription without deleting it.
    """

    try:
        manager = get_webhook_manager()

        # Find subscription
        if subscription_id not in manager.subscriptions:
            raise HTTPException(
                status_code=404,
                detail=f"Subscription {subscription_id} not found"
            )

        subscription = manager.subscriptions[subscription_id]
        subscription.active = not subscription.active

        logger.info(
            f"✅ Webhook subscription toggled: {subscription_id} "
            f"(active={subscription.active})"
        )

        return WebhookSubscriptionResponse(
            id=subscription.id,
            url=subscription.url,
            event_types=[e.value for e in subscription.event_types],
            campaign_id=subscription.campaign_id,
            target_id=subscription.target_id,
            active=subscription.active,
            created_at=subscription.created_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to toggle subscription: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to toggle subscription"
        )
