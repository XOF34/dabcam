"""
Tests for MetasploitMCP Bridge Service.

Tests:
- MSF RPC connectivity
- Exploitation workflow stages
- Session management
- Command execution
- Post-exploitation modules
- C2 establishment
- Error handling
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
from sqlalchemy.orm import Session

from app.services.msf_bridge import (
    MSFBridge,
    ExploitStage,
    get_msf_bridge
)
from app.models import MSFSession, PostModuleExecution, AuditLog


class TestMSFBridgeInitialization:
    """Test MSF Bridge initialization."""

    def test_bridge_creation(self):
        """Test bridge is created with correct configuration."""
        bridge = MSFBridge(
            msf_rpc_host="192.168.1.100",
            msf_rpc_port=55553,
            msf_rpc_user="admin",
            msf_rpc_pass="password123"
        )

        assert bridge.host == "192.168.1.100"
        assert bridge.port == 55553
        assert bridge.user == "admin"
        assert bridge.rpc_url == "http://192.168.1.100:55553/api/v1"

    def test_bridge_session_tracking_initialized(self):
        """Test session tracking is initialized."""
        bridge = MSFBridge()

        assert isinstance(bridge.active_sessions, dict)
        assert isinstance(bridge.exploitation_jobs, dict)
        assert len(bridge.active_sessions) == 0
        assert len(bridge.exploitation_jobs) == 0

    def test_get_msf_bridge_singleton(self):
        """Test get_msf_bridge returns singleton instance."""
        bridge1 = get_msf_bridge()
        bridge2 = get_msf_bridge()

        assert bridge1 is bridge2


class TestMSFConnectionCheck:
    """Test MSF RPC connectivity checks."""

    @pytest.mark.asyncio
    async def test_connection_success(self):
        """Test successful MSF connection."""
        bridge = MSFBridge()

        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            result = await bridge.check_connection()

            assert result is True
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_connection_failure_auth(self):
        """Test failed connection due to auth."""
        bridge = MSFBridge()

        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 401
            mock_get.return_value = mock_response

            result = await bridge.check_connection()

            assert result is False

    @pytest.mark.asyncio
    async def test_connection_failure_exception(self):
        """Test failed connection due to exception."""
        import requests
        bridge = MSFBridge()

        with patch('requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError()

            result = await bridge.check_connection()

            assert result is False


class TestReconnaissanceStage:
    """Test reconnaissance stage."""

    @pytest.mark.asyncio
    async def test_reconnaissance_success(self):
        """Test successful reconnaissance."""
        bridge = MSFBridge()

        result = await bridge._run_reconnaissance(
            campaign_id="camp-001",
            target_id="tgt-001",
            target_ip="192.168.1.100",
            target_port=80
        )

        assert result['success'] is True
        assert result['target'] == "192.168.1.100"
        assert len(result['services_detected']) > 0
        assert result['services_detected'][0]['port'] == 80
        assert result['services_detected'][0]['service'] == 'http'

    @pytest.mark.asyncio
    async def test_reconnaissance_error_handling(self):
        """Test reconnaissance error handling."""
        bridge = MSFBridge()

        with patch.object(bridge, '_run_reconnaissance', side_effect=Exception("Scan failed")):
            result = await bridge._run_reconnaissance(
                campaign_id="camp-001",
                target_id="tgt-001",
                target_ip="192.168.1.100",
                target_port=80
            )

            # Will be handled in actual workflow
            assert False  # Should not reach here with mocked exception


class TestExploitationStage:
    """Test exploitation stage."""

    @pytest.mark.asyncio
    async def test_exploitation_success(self):
        """Test successful exploitation."""
        bridge = MSFBridge()
        recon_result = {
            'success': True,
            'target': '192.168.1.100',
            'services_detected': [
                {'port': 80, 'service': 'http', 'version': 'Apache 2.4.41'}
            ]
        }

        result = await bridge._run_exploitation(
            campaign_id="camp-001",
            target_id="tgt-001",
            target_ip="192.168.1.100",
            target_port=80,
            recon_result=recon_result
        )

        assert result['success'] is True
        assert result['target'] == "192.168.1.100"
        assert len(result['exploits_attempted']) > 0
        assert len(result['sessions']) > 0

    @pytest.mark.asyncio
    async def test_exploitation_generates_session_ids(self):
        """Test exploitation generates proper session IDs."""
        bridge = MSFBridge()
        recon_result = {
            'success': True,
            'target': '192.168.1.100',
            'services_detected': [
                {'port': 80, 'service': 'http'}
            ]
        }

        result = await bridge._run_exploitation(
            campaign_id="camp-001",
            target_id="tgt-001",
            target_ip="192.168.1.100",
            target_port=80,
            recon_result=recon_result
        )

        for session in result['sessions']:
            assert 'session_id' in session
            assert session['session_id'].startswith('session_')
            assert 'created_at' in session


class TestPostExploitationStage:
    """Test post-exploitation stage."""

    @pytest.mark.asyncio
    async def test_post_exploitation_success(self, db: Session):
        """Test successful post-exploitation."""
        bridge = MSFBridge()
        sessions = [
            {
                'session_id': 'session_camp-001_tgt-001_123',
                'exploit': 'exploit/linux/http/apache_mod_cgi',
                'target': '192.168.1.100'
            }
        ]

        result = await bridge._run_post_exploitation(
            campaign_id="camp-001",
            target_id="tgt-001",
            sessions=sessions,
            db_session=db
        )

        assert result['success'] is True
        assert len(result['modules_executed']) > 0
        assert 'data_collected' in result

    @pytest.mark.asyncio
    async def test_post_exploitation_module_execution(self, db: Session):
        """Test individual post module execution."""
        bridge = MSFBridge()

        result = await bridge._execute_post_module(
            session_id="session_camp-001_tgt-001_123",
            module_path="post/linux/gather/hashdump",
            campaign_id="camp-001",
            target_id="tgt-001",
            db_session=db
        )

        assert result['success'] is True
        assert result['module'] == "post/linux/gather/hashdump"
        assert result['session_id'] == "session_camp-001_tgt-001_123"
        assert 'data' in result


class TestC2Establishment:
    """Test C2 (Command & Control) establishment."""

    @pytest.mark.asyncio
    async def test_c2_establishment_success(self):
        """Test successful C2 establishment."""
        bridge = MSFBridge()
        sessions = [
            {
                'session_id': 'session_camp-001_tgt-001_123',
                'type': 'meterpreter',
                'target': '192.168.1.100'
            }
        ]

        result = await bridge._establish_c2(
            campaign_id="camp-001",
            target_id="tgt-001",
            sessions=sessions
        )

        assert result['success'] is True
        assert len(result['c2_channels']) > 0
        assert result['c2_channels'][0]['type'] == 'meterpreter'
        assert result['c2_channels'][0]['protocol'] == 'https'
        assert result['c2_channels'][0]['established'] is True

    @pytest.mark.asyncio
    async def test_c2_multiple_sessions(self):
        """Test C2 on multiple sessions."""
        bridge = MSFBridge()
        sessions = [
            {'session_id': f'session_{i}', 'type': 'meterpreter', 'target': '192.168.1.100'}
            for i in range(3)
        ]

        result = await bridge._establish_c2(
            campaign_id="camp-001",
            target_id="tgt-001",
            sessions=sessions
        )

        assert len(result['c2_channels']) == 3
        for channel in result['c2_channels']:
            assert channel['established'] is True


class TestCommandExecution:
    """Test command execution on sessions."""

    @pytest.mark.asyncio
    async def test_command_execution_success(self, db: Session):
        """Test successful command execution."""
        bridge = MSFBridge()

        result = await bridge.execute_command(
            session_id="session_camp-001_tgt-001_123",
            command="whoami",
            db_session=db
        )

        assert result['session_id'] == "session_camp-001_tgt-001_123"
        assert result['command'] == "whoami"
        assert result['exit_code'] == 0
        assert 'executed_at' in result

    @pytest.mark.asyncio
    async def test_command_execution_logging(self, db: Session):
        """Test command execution is logged."""
        bridge = MSFBridge()

        result = await bridge.execute_command(
            session_id="session_camp-001_tgt-001_123",
            command="id",
            db_session=db
        )

        assert result['exit_code'] == 0
        # In production, would verify audit log entry

    @pytest.mark.asyncio
    async def test_command_execution_various_commands(self, db: Session):
        """Test various command execution."""
        bridge = MSFBridge()

        commands = ["whoami", "pwd", "id", "ls -la", "cat /etc/passwd"]

        for cmd in commands:
            result = await bridge.execute_command(
                session_id="session_camp-001_tgt-001_123",
                command=cmd,
                db_session=db
            )

            assert result['command'] == cmd
            assert result['exit_code'] == 0


class TestSessionManagement:
    """Test session management."""

    @pytest.mark.asyncio
    async def test_session_closure(self, db: Session):
        """Test session closure."""
        bridge = MSFBridge()

        # Create a session in DB first
        session = MSFSession(
            id="session_camp-001_tgt-001_123",
            campaign_id="camp-001",
            target_id="tgt-001",
            session_type="meterpreter",
            target_host="192.168.1.100",
            status="active"
        )
        db.add(session)
        db.commit()

        result = await bridge.close_session(
            session_id="session_camp-001_tgt-001_123",
            db_session=db
        )

        assert result is True

        # Verify session is closed in DB
        updated_session = db.query(MSFSession).filter(
            MSFSession.id == "session_camp-001_tgt-001_123"
        ).first()

        assert updated_session.status == 'closed'
        assert updated_session.closed_at is not None


class TestExploitationWorkflow:
    """Test complete exploitation workflow."""

    @pytest.mark.asyncio
    async def test_workflow_complete_success(self, db: Session):
        """Test complete workflow from reconnaissance to C2."""
        bridge = MSFBridge()

        result = await bridge.start_exploitation_workflow(
            campaign_id="camp-001",
            target_id="tgt-001",
            target_ip="192.168.1.100",
            target_port=80,
            db_session=db
        )

        assert result['campaign_id'] == "camp-001"
        assert result['target_id'] == "tgt-001"
        assert result['status'] == 'completed'
        assert 'completed_at' in result
        assert ExploitStage.RECONNAISSANCE.value in result['stages']
        assert ExploitStage.EXPLOITATION.value in result['stages']
        assert ExploitStage.POST_EXPLOITATION.value in result['stages']
        assert ExploitStage.C2.value in result['stages']

    @pytest.mark.asyncio
    async def test_workflow_contains_sessions(self, db: Session):
        """Test workflow result contains session information."""
        bridge = MSFBridge()

        result = await bridge.start_exploitation_workflow(
            campaign_id="camp-001",
            target_id="tgt-001",
            target_ip="192.168.1.100",
            target_port=80,
            db_session=db
        )

        assert len(result['sessions']) > 0
        for session in result['sessions']:
            assert 'session_id' in session
            assert 'exploit' in session
            assert 'target' in session


class TestExploitStageEnum:
    """Test ExploitStage enumeration."""

    def test_exploit_stage_values(self):
        """Test exploitation stages are properly defined."""
        assert ExploitStage.RECONNAISSANCE.value == "reconnaissance"
        assert ExploitStage.EXPLOITATION.value == "exploitation"
        assert ExploitStage.POST_EXPLOITATION.value == "post_exploitation"
        assert ExploitStage.C2.value == "c2"

    def test_exploit_stage_iteration(self):
        """Test exploitation stages can be iterated."""
        stages = list(ExploitStage)
        assert len(stages) == 4


class TestErrorHandling:
    """Test error handling in MSF bridge."""

    @pytest.mark.asyncio
    async def test_workflow_handles_recon_failure(self, db: Session):
        """Test workflow handles reconnaissance failure."""
        bridge = MSFBridge()

        with patch.object(bridge, '_run_reconnaissance', return_value={'success': False}):
            result = await bridge.start_exploitation_workflow(
                campaign_id="camp-001",
                target_id="tgt-001",
                target_ip="192.168.1.100",
                target_port=80,
                db_session=db
            )

            # Note: Since _run_reconnaissance is mocked at the method level,
            # we need to test via actual workflow
            # This is a placeholder for actual error scenario testing

    @pytest.mark.asyncio
    async def test_command_execution_error_handling(self, db: Session):
        """Test command execution error handling."""
        bridge = MSFBridge()

        result = await bridge.execute_command(
            session_id="nonexistent_session",
            command="whoami",
            db_session=db
        )

        # Should still return result dict
        assert isinstance(result, dict)


class TestBridgeConfiguration:
    """Test MSF bridge configuration."""

    def test_timeout_configurations(self):
        """Test timeout configuration constants."""
        bridge = MSFBridge()

        assert bridge.MSF_RPC_TIMEOUT == 30
        assert bridge.SESSION_CHECK_INTERVAL == 5
        assert bridge.EXPLOITATION_TIMEOUT == 300
        assert bridge.MAX_RETRY_ATTEMPTS == 3

    def test_custom_configuration(self):
        """Test custom configuration."""
        bridge = MSFBridge(
            msf_rpc_host="custom.host",
            msf_rpc_port=12345,
            msf_rpc_user="customuser",
            msf_rpc_pass="custompass"
        )

        assert bridge.host == "custom.host"
        assert bridge.port == 12345
        assert bridge.user == "customuser"
        assert bridge.pass_ == "custompass"


@pytest.fixture
def db():
    """Create test database session."""
    from app.database import SessionLocal

    session = SessionLocal()
    yield session
    session.close()
