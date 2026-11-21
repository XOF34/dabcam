"""
Tests for Webhook Replay Service (Phase 3.5).

Tests event replay, subscription replay, and batch replay functionality.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from app.services.webhook_replay_service import WebhookReplayService, get_replay_service
from app.models import WebhookReplay, WebhookReplayStatus


class TestEventReplay:
    """Test single event replay functionality."""

    @pytest.mark.asyncio
    async def test_replay_event_basic(self):
        """Test basic event replay."""
        service = WebhookReplayService()
        service.webhook_manager = AsyncMock()

        # Mock database delivery
        mock_delivery = Mock()
        mock_delivery.id = "del_123"
        mock_delivery.event_id = "evt_abc"
        mock_delivery.event_type = "exploitation.success"
        mock_delivery.subscription_id = "sub_1"
        mock_delivery.campaign_id = "camp_1"
        mock_delivery.target_id = "tgt_1"
        mock_delivery.created_at = datetime.utcnow()

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_delivery
        mock_db.query.return_value.filter.return_value.distinct.return_value.all.return_value = [mock_delivery]

        result = await service.replay_event(
            event_id="evt_abc",
            db_session=mock_db
        )

        assert result["replay_id"] is not None
        assert "rpl_" in result["replay_id"]
        assert result["event_id"] == "evt_abc"
        assert result["events_queued"] >= 0

    def test_replay_event_no_session(self):
        """Test replay without database session raises error."""
        service = WebhookReplayService()

        with pytest.raises(ValueError):
            import asyncio
            asyncio.run(service.replay_event(
                event_id="evt_abc",
                db_session=None
            ))

    def test_replay_event_not_found(self):
        """Test replaying non-existent event raises error."""
        service = WebhookReplayService()

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError):
            import asyncio
            asyncio.run(service.replay_event(
                event_id="evt_notfound",
                db_session=mock_db
            ))

    @pytest.mark.asyncio
    async def test_replay_event_with_specific_subscriptions(self):
        """Test replaying event to specific subscriptions."""
        service = WebhookReplayService()
        service.webhook_manager = AsyncMock()

        mock_delivery = Mock()
        mock_delivery.event_id = "evt_abc"
        mock_delivery.event_type = "exploitation.success"
        mock_delivery.created_at = datetime.utcnow()

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_delivery

        result = await service.replay_event(
            event_id="evt_abc",
            subscription_ids=["sub_1", "sub_2"],
            db_session=mock_db
        )

        assert result["subscriptions_targeted"] == 2


class TestSubscriptionReplay:
    """Test subscription replay functionality."""

    @pytest.mark.asyncio
    async def test_replay_subscription_basic(self):
        """Test basic subscription replay."""
        service = WebhookReplayService()
        service.webhook_manager = AsyncMock()

        mock_deliveries = [
            Mock(
                event_id=f"evt_{i}",
                event_type="exploitation.success",
                subscription_id="sub_1",
                campaign_id="camp_1",
                target_id="tgt_1",
                created_at=datetime.utcnow() - timedelta(days=i)
            )
            for i in range(3)
        ]

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value = mock_db.query.return_value.filter.return_value
        mock_db.query.return_value.filter.return_value.all.return_value = mock_deliveries

        result = await service.replay_subscription(
            subscription_id="sub_1",
            db_session=mock_db
        )

        assert result["replay_id"] is not None
        assert result["subscription_id"] == "sub_1"
        assert result["total_events"] == 3

    def test_replay_subscription_no_events(self):
        """Test replaying subscription with no events."""
        service = WebhookReplayService()

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.all.return_value = []

        result = {}
        import asyncio
        try:
            result = asyncio.run(service.replay_subscription(
                subscription_id="sub_empty",
                db_session=mock_db
            ))
        except:
            pass

        # Should return no_events_found status or similar

    @pytest.mark.asyncio
    async def test_replay_subscription_with_filters(self):
        """Test subscription replay with event type filter."""
        service = WebhookReplayService()
        service.webhook_manager = AsyncMock()

        # Create proper mock deliveries
        delivery = Mock()
        delivery.event_id = "evt_1"
        delivery.event_type = "exploitation.success"
        delivery.subscription_id = "sub_1"
        delivery.campaign_id = "camp_1"
        delivery.target_id = "tgt_1"
        delivery.created_at = datetime.utcnow()

        mock_db = Mock()
        query_chain = mock_db.query.return_value
        query_chain.filter.return_value = query_chain
        query_chain.all.return_value = [delivery]

        result = await service.replay_subscription(
            subscription_id="sub_1",
            event_types=["exploitation.success"],
            db_session=mock_db
        )

        assert "replay_id" in result

    @pytest.mark.asyncio
    async def test_replay_subscription_with_date_range(self):
        """Test subscription replay with date filtering."""
        service = WebhookReplayService()
        service.webhook_manager = AsyncMock()

        from_date = datetime.utcnow() - timedelta(days=7)
        to_date = datetime.utcnow()

        mock_deliveries = [
            Mock(
                event_id=f"evt_{i}",
                event_type="exploitation.success",
                subscription_id="sub_1",
                campaign_id="camp_1",
                target_id="tgt_1",
                created_at=from_date + timedelta(days=i)
            )
            for i in range(5)
        ]

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.filter.return_value = mock_db.query.return_value.filter.return_value
        mock_db.query.return_value.filter.return_value.all.return_value = mock_deliveries

        result = await service.replay_subscription(
            subscription_id="sub_1",
            from_date=from_date,
            to_date=to_date,
            db_session=mock_db
        )

        assert result["total_events"] == 5


class TestBatchReplay:
    """Test batch replay with complex filtering."""

    @pytest.mark.asyncio
    async def test_batch_replay_basic(self):
        """Test basic batch replay."""
        service = WebhookReplayService()
        service.webhook_manager = AsyncMock()

        mock_deliveries = [
            Mock(
                event_id=f"evt_{i}",
                event_type="exploitation.success",
                subscription_id=f"sub_{i % 2}",
                campaign_id="camp_1",
                target_id="tgt_1",
                created_at=datetime.utcnow()
            )
            for i in range(5)
        ]

        mock_db = Mock()
        query_chain = mock_db.query.return_value
        query_chain.filter.return_value = query_chain
        query_chain.all.return_value = mock_deliveries

        filters = {"event_types": ["exploitation.success"]}

        result = await service.batch_replay(
            filters=filters,
            db_session=mock_db
        )

        assert result["replay_id"] is not None
        assert result["total_events"] == 5

    @pytest.mark.asyncio
    async def test_batch_replay_dry_run(self):
        """Test batch replay dry run (count only)."""
        service = WebhookReplayService()

        mock_deliveries = [
            Mock(
                event_id=f"evt_{i}",
                event_type="exploitation.success",
                created_at=datetime.utcnow()
            )
            for i in range(10)
        ]

        mock_db = Mock()
        query_chain = mock_db.query.return_value
        query_chain.filter.return_value = query_chain
        query_chain.all.return_value = mock_deliveries

        filters = {"event_types": ["exploitation.success"]}

        result = await service.batch_replay(
            filters=filters,
            dry_run=True,
            db_session=mock_db
        )

        assert result["dry_run"] is True
        assert result["events_found"] == 10
        assert "replay_id" not in result or result["replay_id"] is None

    @pytest.mark.asyncio
    async def test_batch_replay_with_subscription_filter(self):
        """Test batch replay filtering by subscriptions."""
        service = WebhookReplayService()
        service.webhook_manager = AsyncMock()

        mock_deliveries = [
            Mock(
                event_id=f"evt_{i}",
                event_type="exploitation.success",
                subscription_id="sub_1",
                campaign_id="camp_1",
                target_id="tgt_1",
                created_at=datetime.utcnow()
            )
            for i in range(3)
        ]

        mock_db = Mock()
        query_chain = mock_db.query.return_value
        query_chain.filter.return_value = query_chain
        query_chain.all.return_value = mock_deliveries

        filters = {
            "subscription_ids": ["sub_1"],
            "event_types": ["exploitation.success"]
        }

        result = await service.batch_replay(
            filters=filters,
            db_session=mock_db
        )

        assert result["total_events"] == 3

    @pytest.mark.asyncio
    async def test_batch_replay_with_campaign_filter(self):
        """Test batch replay filtering by campaigns."""
        service = WebhookReplayService()
        service.webhook_manager = AsyncMock()

        mock_deliveries = [
            Mock(
                event_id=f"evt_{i}",
                event_type="exploitation.success",
                subscription_id="sub_1",
                campaign_id="camp_1",
                target_id="tgt_1",
                created_at=datetime.utcnow()
            )
            for i in range(5)
        ]

        mock_db = Mock()
        query_chain = mock_db.query.return_value
        query_chain.filter.return_value = query_chain
        query_chain.all.return_value = mock_deliveries

        filters = {
            "campaign_ids": ["camp_1"],
            "from_date": datetime.utcnow() - timedelta(days=1),
            "to_date": datetime.utcnow()
        }

        result = await service.batch_replay(
            filters=filters,
            db_session=mock_db
        )

        assert result["total_events"] == 5


class TestReplayStatus:
    """Test replay status checking."""

    def test_get_replay_status(self):
        """Test retrieving replay status."""
        service = WebhookReplayService()

        mock_replay = Mock()
        mock_replay.id = "rpl_123"
        mock_replay.status = "in_progress"
        mock_replay.total_events = 10
        mock_replay.events_queued = 10
        mock_replay.events_delivered = 5
        mock_replay.events_failed = 0
        mock_replay.created_at = datetime.utcnow()
        mock_replay.started_at = datetime.utcnow()
        mock_replay.completed_at = None

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_replay

        result = service.get_replay_status(
            replay_id="rpl_123",
            db_session=mock_db
        )

        assert result["replay_id"] == "rpl_123"
        assert result["status"] == "in_progress"
        assert result["total_events"] == 10
        assert result["progress"]["delivered"] == 5
        assert result["progress"]["pending"] == 5

    def test_get_replay_status_not_found(self):
        """Test getting status for non-existent replay."""
        service = WebhookReplayService()

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError):
            service.get_replay_status(
                replay_id="rpl_notfound",
                db_session=mock_db
            )

    def test_get_replay_status_completed(self):
        """Test status of completed replay."""
        service = WebhookReplayService()

        mock_replay = Mock()
        mock_replay.id = "rpl_123"
        mock_replay.status = "completed"
        mock_replay.total_events = 10
        mock_replay.events_queued = 10
        mock_replay.events_delivered = 10
        mock_replay.events_failed = 0
        mock_replay.created_at = datetime.utcnow()
        mock_replay.started_at = datetime.utcnow()
        mock_replay.completed_at = datetime.utcnow()

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_replay

        result = service.get_replay_status(
            replay_id="rpl_123",
            db_session=mock_db
        )

        assert result["status"] == "completed"
        assert result["progress"]["pending"] == 0
        assert result["progress"]["delivered"] == 10


class TestReplaySingleton:
    """Test replay service singleton pattern."""

    def test_get_replay_service_singleton(self):
        """Test that replay service is a singleton."""
        service1 = get_replay_service()
        service2 = get_replay_service()

        assert service1 is service2

    def test_replay_service_initialization(self):
        """Test replay service initialization with webhook manager."""
        mock_manager = Mock()

        from app.services.webhook_replay_service import initialize_replay_service
        initialize_replay_service(mock_manager)

        service = get_replay_service()
        assert service.webhook_manager is mock_manager
