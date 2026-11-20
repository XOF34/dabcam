"""
Tests for Webhook Event Manager.

Tests:
- Webhook subscription management
- Event dispatching
- Handler registration and execution
- Webhook delivery
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import aiohttp

from app.services.webhook_manager import (
    WebhookManager,
    WebhookEventType,
    WebhookPayload,
    get_webhook_manager
)
from app.services.msf_webhook_dispatcher import MSFWebhookDispatcher


class TestWebhookSubscription:
    """Test webhook subscription management."""

    def test_subscribe_to_webhooks(self):
        """Test subscribing to webhooks."""
        manager = WebhookManager()

        subscription = manager.subscribe(
            url="https://example.com/webhook",
            event_types=[WebhookEventType.EXPLOITATION_SUCCESS]
        )

        assert subscription is not None
        assert subscription.url == "https://example.com/webhook"
        assert WebhookEventType.EXPLOITATION_SUCCESS in subscription.event_types
        assert subscription.active is True

    def test_subscribe_multiple_event_types(self):
        """Test subscribing to multiple event types."""
        manager = WebhookManager()

        event_types = [
            WebhookEventType.EXPLOITATION_SUCCESS,
            WebhookEventType.SESSION_CREATED,
            WebhookEventType.COMMAND_EXECUTED
        ]

        subscription = manager.subscribe(
            url="https://example.com/webhook",
            event_types=event_types
        )

        assert len(subscription.event_types) == 3
        for et in event_types:
            assert et in subscription.event_types

    def test_subscribe_with_filters(self):
        """Test subscribing with campaign/target filters."""
        manager = WebhookManager()

        subscription = manager.subscribe(
            url="https://example.com/webhook",
            event_types=[WebhookEventType.EXPLOITATION_SUCCESS],
            campaign_id="camp-001",
            target_id="tgt-001"
        )

        assert subscription.campaign_id == "camp-001"
        assert subscription.target_id == "tgt-001"

    def test_unsubscribe_from_webhooks(self):
        """Test unsubscribing from webhooks."""
        manager = WebhookManager()

        subscription = manager.subscribe(
            url="https://example.com/webhook",
            event_types=[WebhookEventType.EXPLOITATION_SUCCESS]
        )

        success = manager.unsubscribe(subscription.id)
        assert success is True

        # Verify unsubscribed
        success = manager.unsubscribe(subscription.id)
        assert success is False

    def test_unsubscribe_nonexistent(self):
        """Test unsubscribing non-existent subscription."""
        manager = WebhookManager()

        success = manager.unsubscribe("nonexistent")
        assert success is False


class TestWebhookListing:
    """Test webhook subscription listing."""

    def test_list_all_subscriptions(self):
        """Test listing all subscriptions."""
        manager = WebhookManager()

        # Create multiple subscriptions
        for i in range(3):
            manager.subscribe(
                url=f"https://example.com/webhook{i}",
                event_types=[WebhookEventType.EXPLOITATION_SUCCESS]
            )

        subscriptions = manager.list_subscriptions()
        assert len(subscriptions) == 3

    def test_list_by_campaign(self):
        """Test filtering subscriptions by campaign."""
        manager = WebhookManager()

        # Create subscriptions with different campaigns
        manager.subscribe(
            url="https://example.com/webhook1",
            event_types=[WebhookEventType.EXPLOITATION_SUCCESS],
            campaign_id="camp-001"
        )
        manager.subscribe(
            url="https://example.com/webhook2",
            event_types=[WebhookEventType.EXPLOITATION_SUCCESS],
            campaign_id="camp-002"
        )
        manager.subscribe(
            url="https://example.com/webhook3",
            event_types=[WebhookEventType.EXPLOITATION_SUCCESS]
        )

        # Filter by campaign
        subscriptions = manager.list_subscriptions(campaign_id="camp-001")
        assert len(subscriptions) == 2  # camp-001 + None (matches all)

    def test_list_by_event_type(self):
        """Test filtering subscriptions by event type."""
        manager = WebhookManager()

        manager.subscribe(
            url="https://example.com/webhook1",
            event_types=[WebhookEventType.EXPLOITATION_SUCCESS]
        )
        manager.subscribe(
            url="https://example.com/webhook2",
            event_types=[
                WebhookEventType.EXPLOITATION_SUCCESS,
                WebhookEventType.SESSION_CREATED
            ]
        )
        manager.subscribe(
            url="https://example.com/webhook3",
            event_types=[WebhookEventType.COMMAND_EXECUTED]
        )

        # Filter by event type
        subscriptions = manager.list_subscriptions(
            event_type=WebhookEventType.EXPLOITATION_SUCCESS
        )
        assert len(subscriptions) == 2


class TestWebhookDispatching:
    """Test webhook event dispatching."""

    @pytest.mark.asyncio
    async def test_dispatch_event(self):
        """Test dispatching webhook event."""
        manager = WebhookManager()
        await manager.initialize()

        try:
            # Create subscription
            manager.subscribe(
                url="https://example.com/webhook",
                event_types=[WebhookEventType.EXPLOITATION_SUCCESS]
            )

            # Create event
            event = WebhookPayload(
                event_type=WebhookEventType.EXPLOITATION_SUCCESS,
                campaign_id="camp-001",
                target_id="tgt-001",
                timestamp="2026-01-15T10:00:00Z",
                event_id="evt-123",
                data={"status": "success"}
            )

            # Mock HTTP request
            with patch.object(manager.session, 'post') as mock_post:
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_post.return_value.__aenter__.return_value = mock_response

                result = await manager.dispatch_event(event)

                assert result["total_subscriptions"] == 1
                assert result["delivered"] == 1
                assert result["failed"] == 0

        finally:
            await manager.shutdown()

    @pytest.mark.asyncio
    async def test_dispatch_event_no_subscriptions(self):
        """Test dispatching event with no subscriptions."""
        manager = WebhookManager()
        await manager.initialize()

        try:
            event = WebhookPayload(
                event_type=WebhookEventType.EXPLOITATION_SUCCESS,
                campaign_id="camp-001",
                target_id="tgt-001",
                timestamp="2026-01-15T10:00:00Z",
                event_id="evt-123",
                data={"status": "success"}
            )

            result = await manager.dispatch_event(event)

            assert result["total_subscriptions"] == 0
            assert result["delivered"] == 0
            assert result["failed"] == 0

        finally:
            await manager.shutdown()

    @pytest.mark.asyncio
    async def test_dispatch_event_delivery_failure(self):
        """Test webhook delivery failure."""
        manager = WebhookManager()
        await manager.initialize()

        try:
            # Create subscription
            manager.subscribe(
                url="https://example.com/webhook",
                event_types=[WebhookEventType.EXPLOITATION_SUCCESS]
            )

            # Create event
            event = WebhookPayload(
                event_type=WebhookEventType.EXPLOITATION_SUCCESS,
                campaign_id="camp-001",
                target_id="tgt-001",
                timestamp="2026-01-15T10:00:00Z",
                event_id="evt-123",
                data={"status": "success"}
            )

            # Mock failed HTTP request
            with patch.object(manager.session, 'post') as mock_post:
                mock_response = AsyncMock()
                mock_response.status = 500
                mock_response.text = AsyncMock(return_value="Server error")
                mock_post.return_value.__aenter__.return_value = mock_response

                result = await manager.dispatch_event(event)

                assert result["total_subscriptions"] == 1
                assert result["delivered"] == 0
                assert result["failed"] == 1

        finally:
            await manager.shutdown()


class TestWebhookHandlers:
    """Test webhook event handlers."""

    def test_register_handler(self):
        """Test registering event handler."""
        manager = WebhookManager()

        handler = Mock()
        manager.register_handler(WebhookEventType.EXPLOITATION_SUCCESS, handler)

        assert WebhookEventType.EXPLOITATION_SUCCESS in manager.event_handlers
        assert handler in manager.event_handlers[WebhookEventType.EXPLOITATION_SUCCESS]

    @pytest.mark.asyncio
    async def test_call_handlers(self):
        """Test calling event handlers."""
        manager = WebhookManager()

        handler = AsyncMock()
        manager.register_handler(WebhookEventType.EXPLOITATION_SUCCESS, handler)

        event = WebhookPayload(
            event_type=WebhookEventType.EXPLOITATION_SUCCESS,
            campaign_id="camp-001",
            target_id="tgt-001",
            timestamp="2026-01-15T10:00:00Z",
            event_id="evt-123",
            data={"status": "success"}
        )

        await manager.call_handlers(event)

        handler.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_call_handlers_no_handlers(self):
        """Test calling handlers when none registered."""
        manager = WebhookManager()

        event = WebhookPayload(
            event_type=WebhookEventType.EXPLOITATION_SUCCESS,
            campaign_id="camp-001",
            target_id="tgt-001",
            timestamp="2026-01-15T10:00:00Z",
            event_id="evt-123",
            data={"status": "success"}
        )

        # Should not raise
        await manager.call_handlers(event)


class TestWebhookDispatcher:
    """Test MSF webhook dispatcher."""

    @pytest.mark.asyncio
    async def test_emit_exploitation_started(self):
        """Test emitting exploitation started event."""
        manager = WebhookManager()
        await manager.initialize()

        try:
            manager.subscribe(
                url="https://example.com/webhook",
                event_types=[WebhookEventType.EXPLOITATION_STARTED]
            )

            with patch.object(manager.session, 'post') as mock_post:
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_post.return_value.__aenter__.return_value = mock_response

                await MSFWebhookDispatcher.emit_exploitation_started(
                    campaign_id="camp-001",
                    target_id="tgt-001",
                    target_ip="192.168.1.100",
                    target_port=80
                )

                # Verify webhook was sent
                mock_post.assert_called_once()

        finally:
            await manager.shutdown()

    @pytest.mark.asyncio
    async def test_emit_session_created(self):
        """Test emitting session created event."""
        manager = WebhookManager()
        await manager.initialize()

        try:
            manager.subscribe(
                url="https://example.com/webhook",
                event_types=[WebhookEventType.SESSION_CREATED]
            )

            with patch.object(manager.session, 'post') as mock_post:
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_post.return_value.__aenter__.return_value = mock_response

                await MSFWebhookDispatcher.emit_session_created(
                    campaign_id="camp-001",
                    target_id="tgt-001",
                    session_id="session_123",
                    session_type="meterpreter",
                    target_host="192.168.1.100",
                    exploit_used="exploit/linux/http/apache_mod_cgi"
                )

                # Verify webhook was sent
                mock_post.assert_called_once()

        finally:
            await manager.shutdown()

    @pytest.mark.asyncio
    async def test_emit_command_executed(self):
        """Test emitting command executed event."""
        manager = WebhookManager()
        await manager.initialize()

        try:
            manager.subscribe(
                url="https://example.com/webhook",
                event_types=[WebhookEventType.COMMAND_EXECUTED]
            )

            with patch.object(manager.session, 'post') as mock_post:
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_post.return_value.__aenter__.return_value = mock_response

                await MSFWebhookDispatcher.emit_command_executed(
                    campaign_id="camp-001",
                    target_id="tgt-001",
                    session_id="session_123",
                    command="whoami",
                    output="root",
                    exit_code=0
                )

                # Verify webhook was sent
                mock_post.assert_called_once()

        finally:
            await manager.shutdown()


class TestWebhookEventTypes:
    """Test webhook event types."""

    def test_event_type_values(self):
        """Test event type enum values."""
        assert WebhookEventType.EXPLOITATION_STARTED.value == "exploitation.started"
        assert WebhookEventType.EXPLOITATION_SUCCESS.value == "exploitation.success"
        assert WebhookEventType.SESSION_CREATED.value == "session.created"
        assert WebhookEventType.COMMAND_EXECUTED.value == "command.executed"

    def test_event_type_iteration(self):
        """Test iterating over event types."""
        event_types = list(WebhookEventType)
        assert len(event_types) >= 8  # At least 8 event types


class TestWebhookSingleton:
    """Test webhook manager singleton."""

    def test_get_webhook_manager_singleton(self):
        """Test that get_webhook_manager returns singleton."""
        manager1 = get_webhook_manager()
        manager2 = get_webhook_manager()

        assert manager1 is manager2
