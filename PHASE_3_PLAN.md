# Phase 3 Implementation Plan - Webhook Enhancements

**Status:** Starting Phase 3  
**Branch:** `claude/phase-3-enhancements-*`  
**Date:** November 21, 2026  
**Target Completion:** This session  

---

## Overview

Phase 3 extends the webhook system with production-grade reliability, security, and observability features:

1. **Webhook Signature Verification** - HMAC-SHA256 signing for security
2. **Delivery Retry Logic** - Exponential backoff for resilience
3. **Delivery Status Tracking** - Database persistence of all webhook deliveries
4. **Webhook Delivery Logs** - Historical view of all webhook activity
5. **Replay Functionality** - Re-send historical webhook events on demand

---

## Implementation Roadmap

### 1. Database Models for Webhook Tracking
**Files to Create/Modify:**
- `backend/app/models.py` - Add `WebhookDelivery` and `WebhookLog` models

**Specification:**
```python
class WebhookDelivery(Base):
    """Track webhook delivery attempts and status."""
    __tablename__ = "webhook_deliveries"
    
    id: UUID - Primary key
    subscription_id: str - FK to subscription
    event_id: str - FK to webhook event
    event_type: str - Event type (exploitation.started, etc.)
    url: str - Destination URL
    status: str - pending, delivered, failed, retrying
    http_status: int - Response status code
    response_body: str - Response content (first 1000 chars)
    attempt_count: int - Number of delivery attempts
    max_attempts: int - Maximum retry attempts
    next_retry_at: datetime - When to retry next
    last_error: str - Error message from last attempt
    created_at: datetime - Initial attempt time
    updated_at: datetime - Last update time
    delivered_at: datetime - Successfully delivered time
```

**Key Indices:**
- `(subscription_id, created_at)` - For listing subscriber history
- `(event_id, status)` - For finding events needing retry
- `(status, next_retry_at)` - For scheduled retry queries
- `created_at DESC` - For recent deliveries listing

### 2. Webhook Signature Verification
**Files to Create:**
- `backend/app/services/webhook_signer.py` - New HMAC signing service

**Specification:**
```python
class WebhookSigner:
    """HMAC-SHA256 signing for webhook security."""
    
    @staticmethod
    def sign(payload: str, secret: str) -> str:
        """Generate HMAC-SHA256 signature."""
        
    @staticmethod
    def verify(payload: str, signature: str, secret: str) -> bool:
        """Verify HMAC-SHA256 signature."""
        
    @staticmethod
    def generate_secret() -> str:
        """Generate random 32-byte secret."""
```

**Integration Points:**
- Add signature to webhook headers:
  - `X-Webhook-Signature: sha256=<hex_digest>`
  - `X-Webhook-Timestamp: <unix_timestamp>`
- Include timestamp in signature for replay protection
- Verify timestamp within 5-minute window

**Headers Sent:**
```
X-Webhook-Event: exploitation.success
X-Webhook-ID: evt_abc123def456
X-Webhook-Signature: sha256=abcdef123456...
X-Webhook-Timestamp: 1700000000
Content-Type: application/json
```

### 3. Delivery Retry Logic with Exponential Backoff
**Files to Modify:**
- `backend/app/services/webhook_manager.py` - Add retry queue

**Specification:**
```python
class RetryStrategy:
    """Exponential backoff retry configuration."""
    
    max_attempts: int = 5  # Total retry attempts
    base_delay: int = 60   # 60 seconds
    max_delay: int = 3600  # 1 hour
    backoff_factor: float = 2.0  # Exponential multiplier
    jitter: bool = True    # Add randomness
    
    def calculate_delay(attempt: int) -> int:
        """Calculate delay for attempt N."""
        # delay = base_delay * (backoff_factor ^ attempt)
        # capped at max_delay, with optional jitter
```

**Retry Schedule:**
- Attempt 1: Immediate (0s)
- Attempt 2: 60s later
- Attempt 3: 180s later (60 * 2)
- Attempt 4: 540s later (180 * 2)
- Attempt 5: 1800s later (540 * 2, capped at 3600)

**Failure Scenarios Handled:**
- Connection timeout → Retry
- 5xx server errors → Retry
- 4xx client errors → Log and don't retry
- Network unreachable → Retry with backoff
- DNS resolution failure → Retry

### 4. Delivery Status Tracking
**Files to Modify:**
- `backend/app/services/webhook_manager.py` - Store delivery status
- `backend/app/api/webhooks.py` - Add delivery status endpoints

**New API Endpoints:**
```
GET /api/webhooks/deliveries                    - List all deliveries (paginated)
GET /api/webhooks/subscriptions/{id}/deliveries - List subscription deliveries
GET /api/webhooks/deliveries/{id}               - Get delivery details
GET /api/webhooks/events/{event_id}/deliveries  - List event deliveries
```

**Query Filters:**
- `?status=pending|delivered|failed|retrying`
- `?subscription_id=<id>`
- `?event_id=<id>`
- `?from=<datetime>&to=<datetime>`
- `?limit=50&offset=100` - Pagination
- `?order_by=created_at|status` - Sorting

**Response Format:**
```json
{
  "deliveries": [
    {
      "id": "del_abc123",
      "subscription_id": "sub_xyz789",
      "event_id": "evt_abc123",
      "event_type": "exploitation.success",
      "url": "https://example.com/webhook",
      "status": "delivered",
      "http_status": 200,
      "attempt_count": 1,
      "max_attempts": 5,
      "created_at": "2026-11-21T10:00:00Z",
      "delivered_at": "2026-11-21T10:00:01Z",
      "next_retry_at": null
    }
  ],
  "total": 1234,
  "has_more": true,
  "cursor": "..."
}
```

### 5. Webhook Delivery Logs & Replay
**Files to Create:**
- `backend/app/services/webhook_replay_service.py` - Replay functionality
- `backend/app/api/webhook_logs.py` - Log viewing API

**New Endpoints:**
```
GET  /api/webhooks/logs                         - View delivery logs
POST /api/webhooks/events/{id}/replay           - Replay single event
POST /api/webhooks/subscriptions/{id}/replay    - Replay for subscription
POST /api/webhooks/replay/batch                 - Batch replay
```

**Replay Service Specification:**
```python
class WebhookReplayService:
    """Replay webhook events on demand."""
    
    async def replay_event(
        event_id: str,
        subscription_ids: List[str] = None,
        db_session: Session = None
    ) -> Dict:
        """Replay single event to subscriptions."""
        
    async def replay_subscription(
        subscription_id: str,
        event_types: List[str] = None,
        from_date: datetime = None,
        to_date: datetime = None,
        db_session: Session = None
    ) -> Dict:
        """Replay events for subscription."""
        
    async def batch_replay(
        filters: Dict,
        dry_run: bool = False
    ) -> Dict:
        """Batch replay with complex filters."""
```

**Replay Response:**
```json
{
  "replay_id": "rpl_abc123",
  "events_queued": 42,
  "subscriptions_targeted": 3,
  "status": "pending",
  "created_at": "2026-11-21T10:00:00Z"
}
```

---

## Implementation Schedule

| Component | Priority | Est. LOC | Status |
|-----------|----------|---------|--------|
| 1. Database Models | Critical | 100 | 🔵 TODO |
| 2. Webhook Signer | Critical | 150 | 🔵 TODO |
| 3. Retry Logic | Critical | 200 | 🔵 TODO |
| 4. Delivery Tracking | High | 300 | 🔵 TODO |
| 5. Delivery Status API | High | 250 | 🔵 TODO |
| 6. Replay Service | High | 300 | 🔵 TODO |
| 7. Logs API | Medium | 200 | 🔵 TODO |
| 8. Tests | Critical | 400 | 🔵 TODO |
| 9. Documentation | Medium | 300 | 🔵 TODO |

**Total Phase 3: ~2,200 LOC**

---

## Success Criteria

✅ **Functionality**
- Webhook signatures verified on all deliveries
- Failed webhooks retry with exponential backoff
- All delivery attempts stored in database
- Delivery status visible via API
- Historical events can be replayed to subscriptions

✅ **Reliability**
- 100% of delivery attempts logged
- Retry queue survives application restart
- Subscription filters work correctly with replay
- No duplicate deliveries on replay

✅ **Security**
- HMAC-SHA256 signatures verified
- Timestamp validation prevents replay attacks
- Secrets stored securely (hashed if stored)
- No sensitive data in delivery logs

✅ **Testing**
- Unit tests for signer, retry logic, replay
- Integration tests for full delivery pipeline
- Load tests for retry queue under high volume
- 85%+ code coverage

---

## Commits Planned

1. `PHASE_3_1_DATABASE_MODELS` - WebhookDelivery and WebhookLog models
2. `PHASE_3_2_WEBHOOK_SIGNER` - HMAC-SHA256 signing service
3. `PHASE_3_3_RETRY_LOGIC` - Exponential backoff and retry queue
4. `PHASE_3_4_DELIVERY_TRACKING` - Persistent storage of deliveries
5. `PHASE_3_5_REPLAY_SERVICE` - Event replay functionality
6. `PHASE_3_6_API_ENDPOINTS` - Delivery status and logs APIs
7. `PHASE_3_7_TESTS` - Comprehensive test suite
8. `PHASE_3_COMPLETE` - Documentation and final validation

---

## Phase 4 Preview (Future)

- Webhook delivery metrics dashboard
- Alerting on delivery failures
- Webhook performance analytics
- Custom retry policies per subscription
- Webhook templates for common integrations (Slack, Teams, etc.)

---

## Notes

- All retry operations must be idempotent
- Delivery logs must support 5+ years of historical data
- Replay operations should respect subscription filters
- All timestamps in UTC ISO format
- Database migrations required for existing deployments

