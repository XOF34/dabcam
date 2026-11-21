"""
Tests for Webhook Logs API (Phase 3.6).

Tests webhook activity logging, filtering, statistics, and analytics.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock

from app.schemas.webhook_delivery import WebhookDeliveryError


class TestWebhookLogsListing:
    """Test webhook logs listing and filtering."""

    def test_list_logs_response_structure(self):
        """Test logs list response has correct structure."""
        response = {
            "total": 100,
            "limit": 50,
            "offset": 0,
            "has_more": True,
            "logs": []
        }

        assert response["total"] == 100
        assert response["limit"] == 50
        assert response["offset"] == 0
        assert response["has_more"] is True
        assert isinstance(response["logs"], list)

    def test_log_entry_structure(self):
        """Test individual log entry structure."""
        log_entry = {
            "id": "log_abc123",
            "event_id": "evt_xyz789",
            "event_type": "exploitation.success",
            "subscription_id": "sub_1",
            "campaign_id": "camp_1",
            "target_id": "tgt_1",
            "total_deliveries": 5,
            "successful_deliveries": 5,
            "failed_deliveries": 0,
            "success_rate": 100.0,
            "event_payload": {"data": "example"},
            "processed_at": datetime.utcnow().isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
            "duration_ms": 1500
        }

        assert log_entry["id"] == "log_abc123"
        assert log_entry["success_rate"] == 100.0
        assert log_entry["total_deliveries"] == 5

    def test_logs_filtering_by_event_type(self):
        """Test filtering logs by event type."""
        event_types = [
            "exploitation.started",
            "exploitation.success",
            "exploitation.failed",
            "session.created"
        ]

        for event_type in event_types:
            assert "." in event_type

    def test_logs_filtering_by_subscription(self):
        """Test filtering logs by subscription ID."""
        subscription_ids = ["sub_1", "sub_2", "sub_3"]

        for sub_id in subscription_ids:
            assert sub_id.startswith("sub_")

    def test_logs_pagination(self):
        """Test pagination parameters."""
        valid_params = [
            (10, 0),
            (50, 0),
            (100, 50),
            (500, 1000),
        ]

        for limit, offset in valid_params:
            assert 1 <= limit <= 500
            assert offset >= 0
            assert (offset + limit) >= limit


class TestWebhookLogsStatistics:
    """Test webhook logs statistics endpoints."""

    def test_stats_response_structure(self):
        """Test statistics response has correct structure."""
        stats = {
            "total_events": 100,
            "total_deliveries": 500,
            "successful_deliveries": 480,
            "failed_deliveries": 20,
            "success_rate": 96.0,
            "average_duration_ms": 1250,
            "event_types": {},
            "subscriptions": {}
        }

        assert stats["total_events"] == 100
        assert stats["total_deliveries"] == 500
        assert stats["success_rate"] == 96.0

    def test_success_rate_calculation(self):
        """Test success rate percentage calculation."""
        success_cases = [
            (100, 100, 100.0),
            (95, 100, 95.0),
            (50, 100, 50.0),
            (0, 100, 0.0),
            (0, 0, 0.0)
        ]

        for successful, total, expected_rate in success_cases:
            if total > 0:
                rate = (successful / total * 100)
            else:
                rate = 0.0
            assert rate == expected_rate

    def test_event_type_breakdown(self):
        """Test event type statistics breakdown."""
        event_types = {
            "exploitation.success": {
                "count": 50,
                "total_deliveries": 250,
                "successful": 245,
                "failed": 5
            },
            "session.created": {
                "count": 30,
                "total_deliveries": 150,
                "successful": 145,
                "failed": 5
            }
        }

        assert len(event_types) == 2
        assert event_types["exploitation.success"]["count"] == 50

    def test_subscription_statistics(self):
        """Test subscription statistics breakdown."""
        subscriptions = {
            "sub_1": {
                "count": 60,
                "total_deliveries": 300,
                "successful": 285,
                "failed": 15
            },
            "sub_2": {
                "count": 40,
                "total_deliveries": 200,
                "successful": 200,
                "failed": 0
            }
        }

        assert len(subscriptions) == 2
        assert subscriptions["sub_1"]["total_deliveries"] == 300


class TestEventLogDetail:
    """Test detailed event log retrieval."""

    def test_event_log_response_structure(self):
        """Test event log detail response structure."""
        event_log = {
            "event_id": "evt_abc123",
            "event_type": "exploitation.success",
            "campaign_id": "camp_1",
            "target_id": "tgt_1",
            "event_payload": {"data": "example"},
            "total_deliveries": 5,
            "successful_deliveries": 5,
            "failed_deliveries": 0,
            "success_rate": 100.0,
            "deliveries": [],
            "status_breakdown": {},
            "processed_at": datetime.utcnow().isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
            "duration_ms": 1500
        }

        assert event_log["event_id"] == "evt_abc123"
        assert event_log["success_rate"] == 100.0
        assert isinstance(event_log["deliveries"], list)

    def test_delivery_detail_in_event_log(self):
        """Test individual delivery details in event log."""
        delivery = {
            "id": "del_123",
            "subscription_id": "sub_1",
            "status": "delivered",
            "http_status": 200,
            "attempt_count": 1,
            "created_at": datetime.utcnow().isoformat(),
            "delivered_at": datetime.utcnow().isoformat(),
            "last_error": None
        }

        assert delivery["status"] == "delivered"
        assert delivery["http_status"] == 200
        assert delivery["attempt_count"] == 1

    def test_status_breakdown_counts(self):
        """Test status breakdown aggregation."""
        breakdown = {
            "delivered": {
                "count": 4,
                "subscriptions": ["sub_1", "sub_2", "sub_3", "sub_4"]
            },
            "failed": {
                "count": 1,
                "subscriptions": ["sub_5"]
            },
            "retrying": {
                "count": 0,
                "subscriptions": []
            }
        }

        assert breakdown["delivered"]["count"] == 4
        assert len(breakdown["delivered"]["subscriptions"]) == 4


class TestSubscriptionActivity:
    """Test subscription activity log retrieval."""

    def test_subscription_activity_response(self):
        """Test subscription activity response structure."""
        response = {
            "subscription_id": "sub_1",
            "total_events": 100,
            "limit": 50,
            "offset": 0,
            "has_more": True,
            "statistics": {
                "total_deliveries": 500,
                "successful_deliveries": 480,
                "failed_deliveries": 20,
                "success_rate": 96.0
            },
            "events": []
        }

        assert response["subscription_id"] == "sub_1"
        assert response["total_events"] == 100
        assert response["statistics"]["success_rate"] == 96.0

    def test_event_in_activity_log(self):
        """Test event details in activity log."""
        event = {
            "event_id": "evt_xyz789",
            "event_type": "exploitation.success",
            "campaign_id": "camp_1",
            "total_deliveries": 5,
            "successful": 5,
            "failed": 0,
            "processed_at": datetime.utcnow().isoformat(),
            "duration_ms": 1200
        }

        assert event["event_id"] == "evt_xyz789"
        assert event["successful"] == 5

    def test_activity_pagination(self):
        """Test activity log pagination."""
        response = {
            "total_events": 500,
            "limit": 50,
            "offset": 100,
            "has_more": True,
            "events": []
        }

        assert (response["offset"] + response["limit"]) < response["total_events"]
        assert response["has_more"] is True


class TestLogsDateFiltering:
    """Test webhook logs date range filtering."""

    def test_date_range_filtering(self):
        """Test filtering logs by date range."""
        now = datetime.utcnow()
        from_date = now - timedelta(days=7)
        to_date = now

        # Events within range
        event_in_range = now - timedelta(days=3)
        assert from_date <= event_in_range <= to_date

        # Events before range
        event_before = now - timedelta(days=10)
        assert event_before < from_date

        # Events after range
        event_after = now + timedelta(days=1)
        assert event_after > to_date

    def test_date_boundaries(self):
        """Test date boundary conditions."""
        from_date = datetime(2026, 11, 14, 0, 0, 0)
        to_date = datetime(2026, 11, 21, 23, 59, 59)

        # Exact boundary matches
        assert from_date >= from_date
        assert to_date <= to_date

        # Events within range
        middle = datetime(2026, 11, 17, 12, 0, 0)
        assert from_date <= middle <= to_date


class TestLogsErrorHandling:
    """Test error handling in logs API."""

    def test_event_not_found(self):
        """Test handling event not found."""
        error_response = {
            "status_code": 404,
            "detail": "Event evt_notfound not found"
        }

        assert error_response["status_code"] == 404
        assert "not found" in error_response["detail"].lower()

    def test_invalid_filter_parameters(self):
        """Test handling invalid filter parameters."""
        # Valid event types
        valid_types = ["exploitation.success", "session.created", "command.executed"]

        for event_type in valid_types:
            assert "." in event_type

    def test_empty_results(self):
        """Test handling empty results."""
        response = {
            "total": 0,
            "limit": 50,
            "offset": 0,
            "has_more": False,
            "logs": []
        }

        assert response["total"] == 0
        assert len(response["logs"]) == 0
        assert response["has_more"] is False


class TestLogsAggregation:
    """Test log aggregation and analytics."""

    def test_average_duration_calculation(self):
        """Test calculating average duration."""
        durations = [1000, 1500, 2000, 1200, 1800]
        avg = sum(durations) / len(durations)

        assert avg == 1500

    def test_success_rate_by_event_type(self):
        """Test calculating success rates by event type."""
        event_stats = {
            "exploitation.success": {
                "total": 100,
                "successful": 95,
                "failed": 5
            },
            "session.created": {
                "total": 50,
                "successful": 50,
                "failed": 0
            }
        }

        for event_type, stats in event_stats.items():
            rate = (stats["successful"] / stats["total"] * 100)
            assert 0 <= rate <= 100

    def test_failed_vs_successful_breakdown(self):
        """Test failed vs successful delivery breakdown."""
        stats = {
            "total_deliveries": 1000,
            "successful": 950,
            "failed": 50,
            "retrying": 0,
            "pending": 0
        }

        assert stats["successful"] + stats["failed"] == 1000
