"""
Metasploit Framework (MSF) Bridge API endpoints.

Integrates camera exploitation with Metasploit through RPC interface.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.msf_bridge import get_msf_bridge
from app.schemas.metasploit import (
    MSFExploitationRequest,
    ExploitationWorkflow,
    CommandExecutionRequest,
    CommandExecutionResult,
    SessionCloseRequest,
    MSFConnectionStatus,
    MSFError
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/metasploit", tags=["metasploit"])


@router.get(
    "/status",
    response_model=MSFConnectionStatus,
    responses={
        200: {"model": MSFConnectionStatus, "description": "MSF connection status"}
    }
)
async def get_msf_status() -> MSFConnectionStatus:
    """
    Get Metasploit RPC connection status.

    **Response**:
    - Connected: Whether RPC endpoint is reachable
    - Authenticated: Whether credentials are valid
    - Host/Port: RPC server location
    - Timestamp: Status check time
    """

    try:
        bridge = get_msf_bridge()
        is_connected = await bridge.check_connection()

        return MSFConnectionStatus(
            connected=is_connected,
            host=bridge.host,
            port=bridge.port,
            authenticated=is_connected,
            timestamp=__import__('datetime').datetime.utcnow().isoformat()
        )

    except Exception as e:
        logger.exception(f"Failed to get MSF status: {e}")
        raise HTTPException(status_code=500, detail="Failed to check MSF status")


@router.post(
    "/exploit",
    response_model=ExploitationWorkflow,
    responses={
        400: {"model": MSFError, "description": "Invalid request"},
        500: {"model": MSFError, "description": "Exploitation failed"}
    }
)
async def start_exploitation(
    request: MSFExploitationRequest,
    db: Session = Depends(get_db)
) -> ExploitationWorkflow:
    """
    Start complete exploitation workflow.

    **Workflow Stages**:
    1. **Reconnaissance**: Scan target, detect services
    2. **Exploitation**: Execute appropriate exploits
    3. **Post-Exploitation**: Run post modules (hashdump, enum, persistence)
    4. **C2**: Establish Command & Control channel

    **Request Body**:
    - `campaign_id`: Campaign identifier
    - `target_id`: Target identifier
    - `target_ip`: Target IP address
    - `target_port`: Target port (usually 80 for HTTP)

    **Response**:
    - Workflow status and results for each stage
    - Session IDs for established sessions
    - Collected data from post-exploitation

    **Security**:
    - All operations logged to audit trail
    - Sessions tracked in database
    - Comprehensive error handling
    """

    try:
        logger.info(
            f"Starting exploitation: "
            f"campaign={request.campaign_id}, target={request.target_id}"
        )

        bridge = get_msf_bridge()

        # Check MSF connectivity
        is_connected = await bridge.check_connection()
        if not is_connected:
            logger.warning("Metasploit RPC not available")
            raise HTTPException(
                status_code=503,
                detail="Metasploit RPC server not available"
            )

        # Run exploitation workflow
        workflow_result = await bridge.start_exploitation_workflow(
            campaign_id=request.campaign_id,
            target_id=request.target_id,
            target_ip=request.target_ip,
            target_port=request.target_port,
            db_session=db
        )

        return ExploitationWorkflow(**workflow_result)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Exploitation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Exploitation failed: {str(e)}"
        )


@router.post(
    "/session/{session_id}/execute",
    response_model=CommandExecutionResult,
    responses={
        404: {"model": MSFError, "description": "Session not found"},
        500: {"model": MSFError, "description": "Command execution failed"}
    }
)
async def execute_command_on_session(
    session_id: str,
    request: CommandExecutionRequest,
    db: Session = Depends(get_db)
) -> CommandExecutionResult:
    """
    Execute command on established Metasploit session.

    **Request Body**:
    - `session_id`: Target session ID
    - `command`: Command to execute

    **Response**:
    - Command output
    - Exit code
    - Execution timestamp

    **Example Commands**:
    - `whoami` - Get current user
    - `id` - Get user/group info
    - `pwd` - Get current directory
    - `ls -la` - List files
    - `cat /etc/passwd` - Read files
    """

    try:
        logger.info(f"Executing command on session {session_id}: {request.command}")

        bridge = get_msf_bridge()

        # Execute command
        result = await bridge.execute_command(
            session_id=session_id,
            command=request.command,
            db_session=db
        )

        if 'error' in result:
            raise HTTPException(
                status_code=500,
                detail=result['error']
            )

        return CommandExecutionResult(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Command execution failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Command execution failed"
        )


@router.post(
    "/session/{session_id}/close",
    responses={
        200: {"model": dict, "description": "Session closed"},
        404: {"model": MSFError, "description": "Session not found"}
    }
)
async def close_session(
    session_id: str,
    db: Session = Depends(get_db)
) -> dict:
    """
    Close a Metasploit session.

    Cleans up:
    - Session connection
    - Associated resources
    - Database records

    **Response**:
    - Confirmation of closure
    """

    try:
        logger.info(f"Closing session: {session_id}")

        bridge = get_msf_bridge()

        # Close session
        success = await bridge.close_session(
            session_id=session_id,
            db_session=db
        )

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found"
            )

        logger.info(f"Session closed: {session_id}")

        return {
            "message": "Session closed successfully",
            "session_id": session_id,
            "closed": True
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Session closure failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to close session"
        )


@router.get(
    "/session/{session_id}",
    responses={
        200: {"model": dict, "description": "Session details"},
        404: {"model": MSFError, "description": "Session not found"}
    }
)
async def get_session_info(
    session_id: str,
    db: Session = Depends(get_db)
) -> dict:
    """
    Get information about a Metasploit session.

    **Response**:
    - Session type (meterpreter, shell, etc.)
    - Target information
    - Exploit used
    - Creation and activity timestamps
    - Current status
    """

    try:
        from app.models import MSFSession

        session = db.query(MSFSession).filter(
            MSFSession.id == session_id
        ).first()

        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found"
            )

        return {
            "session_id": str(session.id),
            "type": session.session_type or "meterpreter",
            "target": session.target_host or "unknown",
            "exploit": session.exploit_used or "unknown",
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "status": session.status or "active",
            "last_activity": session.updated_at.isoformat() if session.updated_at else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get session info: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve session information"
        )


@router.get(
    "/campaigns/{campaign_id}/sessions",
    responses={
        200: {"model": list, "description": "List of sessions"}
    }
)
async def list_campaign_sessions(
    campaign_id: str,
    db: Session = Depends(get_db)
) -> list:
    """
    List all Metasploit sessions for a campaign.

    **Response**:
    - Array of session information
    - Session IDs, types, targets, status
    """

    try:
        from app.models import MSFSession

        sessions = db.query(MSFSession).filter(
            MSFSession.campaign_id == campaign_id
        ).all()

        return [
            {
                "session_id": str(s.id),
                "type": s.session_type or "meterpreter",
                "target": s.target_host or "unknown",
                "status": s.status or "active",
                "created_at": s.created_at.isoformat() if s.created_at else None
            }
            for s in sessions
        ]

    except Exception as e:
        logger.exception(f"Failed to list sessions: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to list sessions"
        )
