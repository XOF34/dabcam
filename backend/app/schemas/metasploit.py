"""
Pydantic schemas for MetasploitMCP bridge API.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class MSFExploitationRequest(BaseModel):
    """Request to start exploitation workflow."""

    campaign_id: str = Field(..., description="Campaign ID")
    target_id: str = Field(..., description="Target ID")
    target_ip: str = Field(..., description="Target IP address")
    target_port: int = Field(..., description="Target port")

    class Config:
        schema_extra = {
            "example": {
                "campaign_id": "camp-123",
                "target_id": "tgt-456",
                "target_ip": "192.168.1.100",
                "target_port": 80
            }
        }


class ServiceDetected(BaseModel):
    """Detected service information."""

    port: int
    service: str
    version: Optional[str] = None


class ReconnaissanceResult(BaseModel):
    """Reconnaissance stage result."""

    success: bool
    target: str
    services_detected: List[ServiceDetected] = []
    vulnerabilities: List[str] = []


class ExploitAttempt(BaseModel):
    """Individual exploit attempt."""

    exploit_name: str
    target: str
    port: int
    success: bool
    session_id: Optional[str] = None
    error: Optional[str] = None


class ExploitationResult(BaseModel):
    """Exploitation stage result."""

    success: bool
    target: str
    exploits_attempted: List[ExploitAttempt]
    sessions: List[Dict[str, Any]] = []


class PostModuleExecution(BaseModel):
    """Post-exploitation module execution."""

    module: str
    session: str
    success: bool
    output: Optional[Dict] = None


class PostExploitationResult(BaseModel):
    """Post-exploitation stage result."""

    success: bool
    modules_executed: List[PostModuleExecution]
    data_collected: Dict[str, Any]


class C2Channel(BaseModel):
    """Command & Control channel."""

    session_id: str
    type: str  # meterpreter, shell, etc.
    protocol: str  # https, http, tcp, etc.
    established: bool
    created_at: str


class C2Result(BaseModel):
    """C2 establishment result."""

    success: bool
    c2_channels: List[C2Channel]


class ExploitationStage(BaseModel):
    """Single stage of exploitation."""

    stage_name: str
    success: bool
    result: Optional[Dict] = None


class ExploitationWorkflow(BaseModel):
    """Complete exploitation workflow result."""

    campaign_id: str
    target_id: str
    stages: Dict[str, Any]
    sessions: List[Dict[str, Any]]
    status: str  # in_progress, completed, failed
    started_at: str
    completed_at: Optional[str] = None
    error: Optional[str] = None


class CommandExecutionRequest(BaseModel):
    """Request to execute command on session."""

    session_id: str = Field(..., description="Metasploit session ID")
    command: str = Field(..., description="Command to execute")

    class Config:
        schema_extra = {
            "example": {
                "session_id": "session_123",
                "command": "whoami"
            }
        }


class CommandExecutionResult(BaseModel):
    """Command execution result."""

    session_id: str
    command: str
    output: str
    exit_code: int
    executed_at: str


class SessionCloseRequest(BaseModel):
    """Request to close session."""

    session_id: str = Field(..., description="Session ID to close")


class SessionCloseResult(BaseModel):
    """Session closure result."""

    session_id: str
    closed: bool
    message: str


class MSFConnectionStatus(BaseModel):
    """MSF RPC connection status."""

    connected: bool
    host: str
    port: int
    authenticated: bool
    timestamp: str


class MSFSessionInfo(BaseModel):
    """Metasploit session information."""

    session_id: str
    type: str
    target: str
    exploit: str
    created_at: str
    last_activity: Optional[str] = None
    status: str  # active, inactive, closed


class MSFError(BaseModel):
    """MSF error response."""

    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Error detail")
    session_id: Optional[str] = Field(None, description="Related session if applicable")
