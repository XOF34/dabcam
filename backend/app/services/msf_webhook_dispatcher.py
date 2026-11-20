"""
MSF Bridge Webhook Event Dispatcher.

Integrates with MSF Bridge to emit webhook events for:
- Exploitation lifecycle (started, success, failure)
- Session management (created, activity, closed)
- Command execution
- Post-exploitation modules
- C2 channels
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.services.webhook_manager import (
    get_webhook_manager,
    WebhookEventType,
    WebhookPayload
)


logger = logging.getLogger(__name__)


class MSFWebhookDispatcher:
    """Dispatches webhook events from MSF bridge operations."""

    @staticmethod
    async def emit_exploitation_started(
        campaign_id: str,
        target_id: str,
        target_ip: str,
        target_port: int,
        db_session: Optional[Session] = None
    ) -> None:
        """
        Emit exploitation started event.

        Args:
            campaign_id: Campaign ID
            target_id: Target ID
            target_ip: Target IP address
            target_port: Target port
            db_session: Optional database session
        """

        event = WebhookPayload(
            event_type=WebhookEventType.EXPLOITATION_STARTED,
            campaign_id=campaign_id,
            target_id=target_id,
            timestamp=datetime.utcnow().isoformat(),
            event_id=f"evt_{uuid4().hex[:12]}",
            data={
                "target": target_ip,
                "port": target_port,
                "phase": "reconnaissance"
            }
        )

        manager = get_webhook_manager()
        await manager.dispatch_event(event, db_session)
        await manager.call_handlers(event)

    @staticmethod
    async def emit_exploitation_success(
        campaign_id: str,
        target_id: str,
        target_ip: str,
        exploit_name: str,
        session_id: str,
        db_session: Optional[Session] = None
    ) -> None:
        """
        Emit exploitation success event.

        Args:
            campaign_id: Campaign ID
            target_id: Target ID
            target_ip: Target IP
            exploit_name: Exploit path
            session_id: Created session ID
            db_session: Optional database session
        """

        event = WebhookPayload(
            event_type=WebhookEventType.EXPLOITATION_SUCCESS,
            campaign_id=campaign_id,
            target_id=target_id,
            timestamp=datetime.utcnow().isoformat(),
            event_id=f"evt_{uuid4().hex[:12]}",
            data={
                "target": target_ip,
                "exploit": exploit_name,
                "session_id": session_id,
                "status": "success"
            }
        )

        manager = get_webhook_manager()
        await manager.dispatch_event(event, db_session)
        await manager.call_handlers(event)

    @staticmethod
    async def emit_exploitation_failure(
        campaign_id: str,
        target_id: str,
        target_ip: str,
        reason: str,
        db_session: Optional[Session] = None
    ) -> None:
        """
        Emit exploitation failure event.

        Args:
            campaign_id: Campaign ID
            target_id: Target ID
            target_ip: Target IP
            reason: Failure reason
            db_session: Optional database session
        """

        event = WebhookPayload(
            event_type=WebhookEventType.EXPLOITATION_FAILURE,
            campaign_id=campaign_id,
            target_id=target_id,
            timestamp=datetime.utcnow().isoformat(),
            event_id=f"evt_{uuid4().hex[:12]}",
            data={
                "target": target_ip,
                "status": "failed",
                "reason": reason
            }
        )

        manager = get_webhook_manager()
        await manager.dispatch_event(event, db_session)
        await manager.call_handlers(event)

    @staticmethod
    async def emit_session_created(
        campaign_id: str,
        target_id: str,
        session_id: str,
        session_type: str,
        target_host: str,
        exploit_used: str,
        db_session: Optional[Session] = None
    ) -> None:
        """
        Emit session created event.

        Args:
            campaign_id: Campaign ID
            target_id: Target ID
            session_id: Session ID
            session_type: Type of session (meterpreter, shell, etc.)
            target_host: Target host
            exploit_used: Exploit path
            db_session: Optional database session
        """

        event = WebhookPayload(
            event_type=WebhookEventType.SESSION_CREATED,
            campaign_id=campaign_id,
            target_id=target_id,
            timestamp=datetime.utcnow().isoformat(),
            event_id=f"evt_{uuid4().hex[:12]}",
            data={
                "session_id": session_id,
                "type": session_type,
                "target": target_host,
                "exploit": exploit_used
            }
        )

        manager = get_webhook_manager()
        await manager.dispatch_event(event, db_session)
        await manager.call_handlers(event)

    @staticmethod
    async def emit_session_closed(
        campaign_id: str,
        target_id: str,
        session_id: str,
        db_session: Optional[Session] = None
    ) -> None:
        """
        Emit session closed event.

        Args:
            campaign_id: Campaign ID
            target_id: Target ID
            session_id: Session ID
            db_session: Optional database session
        """

        event = WebhookPayload(
            event_type=WebhookEventType.SESSION_CLOSED,
            campaign_id=campaign_id,
            target_id=target_id,
            timestamp=datetime.utcnow().isoformat(),
            event_id=f"evt_{uuid4().hex[:12]}",
            data={
                "session_id": session_id,
                "status": "closed"
            }
        )

        manager = get_webhook_manager()
        await manager.dispatch_event(event, db_session)
        await manager.call_handlers(event)

    @staticmethod
    async def emit_command_executed(
        campaign_id: str,
        target_id: str,
        session_id: str,
        command: str,
        output: str,
        exit_code: int,
        db_session: Optional[Session] = None
    ) -> None:
        """
        Emit command executed event.

        Args:
            campaign_id: Campaign ID
            target_id: Target ID
            session_id: Session ID
            command: Executed command
            output: Command output
            exit_code: Command exit code
            db_session: Optional database session
        """

        event = WebhookPayload(
            event_type=WebhookEventType.COMMAND_EXECUTED,
            campaign_id=campaign_id,
            target_id=target_id,
            timestamp=datetime.utcnow().isoformat(),
            event_id=f"evt_{uuid4().hex[:12]}",
            data={
                "session_id": session_id,
                "command": command,
                "output": output,
                "exit_code": exit_code
            }
        )

        manager = get_webhook_manager()
        await manager.dispatch_event(event, db_session)
        await manager.call_handlers(event)

    @staticmethod
    async def emit_post_module_executed(
        campaign_id: str,
        target_id: str,
        session_id: str,
        module_path: str,
        data: Dict[str, Any],
        db_session: Optional[Session] = None
    ) -> None:
        """
        Emit post-exploitation module executed event.

        Args:
            campaign_id: Campaign ID
            target_id: Target ID
            session_id: Session ID
            module_path: Module path
            data: Module output data
            db_session: Optional database session
        """

        event = WebhookPayload(
            event_type=WebhookEventType.POST_MODULE_EXECUTED,
            campaign_id=campaign_id,
            target_id=target_id,
            timestamp=datetime.utcnow().isoformat(),
            event_id=f"evt_{uuid4().hex[:12]}",
            data={
                "session_id": session_id,
                "module": module_path,
                "data": data
            }
        )

        manager = get_webhook_manager()
        await manager.dispatch_event(event, db_session)
        await manager.call_handlers(event)

    @staticmethod
    async def emit_c2_established(
        campaign_id: str,
        target_id: str,
        session_id: str,
        channel_type: str,
        protocol: str,
        db_session: Optional[Session] = None
    ) -> None:
        """
        Emit C2 channel established event.

        Args:
            campaign_id: Campaign ID
            target_id: Target ID
            session_id: Session ID
            channel_type: C2 channel type
            protocol: Protocol used
            db_session: Optional database session
        """

        event = WebhookPayload(
            event_type=WebhookEventType.C2_ESTABLISHED,
            campaign_id=campaign_id,
            target_id=target_id,
            timestamp=datetime.utcnow().isoformat(),
            event_id=f"evt_{uuid4().hex[:12]}",
            data={
                "session_id": session_id,
                "type": channel_type,
                "protocol": protocol,
                "status": "established"
            }
        )

        manager = get_webhook_manager()
        await manager.dispatch_event(event, db_session)
        await manager.call_handlers(event)

    @staticmethod
    async def emit_c2_lost(
        campaign_id: str,
        target_id: str,
        session_id: str,
        db_session: Optional[Session] = None
    ) -> None:
        """
        Emit C2 channel lost event.

        Args:
            campaign_id: Campaign ID
            target_id: Target ID
            session_id: Session ID
            db_session: Optional database session
        """

        event = WebhookPayload(
            event_type=WebhookEventType.C2_LOST,
            campaign_id=campaign_id,
            target_id=target_id,
            timestamp=datetime.utcnow().isoformat(),
            event_id=f"evt_{uuid4().hex[:12]}",
            data={
                "session_id": session_id,
                "status": "lost"
            }
        )

        manager = get_webhook_manager()
        await manager.dispatch_event(event, db_session)
        await manager.call_handlers(event)
