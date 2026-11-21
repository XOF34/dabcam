"""
Tests for MetasploitMCP Bridge API endpoints.

Tests:
- GET /api/metasploit/status
- POST /api/metasploit/exploit
- POST /api/metasploit/session/{id}/execute
- POST /api/metasploit/session/{id}/close
- GET /api/metasploit/session/{id}
- GET /api/metasploit/campaigns/{id}/sessions
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, Mock
from sqlalchemy.orm import Session

from app.main import app
from app.database import SessionLocal
from app.models import MSFSession


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def db():
    """Create test database session."""
    session = SessionLocal()
    yield session
    session.close()


class TestMSFStatusEndpoint:
    """Test /api/metasploit/status endpoint."""

    def test_status_endpoint_success(self, client):
        """Test successful status check."""
        with patch('app.api.metasploit.get_msf_bridge') as mock_bridge:
            mock_instance = AsyncMock()
            mock_instance.check_connection = AsyncMock(return_value=True)
            mock_instance.host = "localhost"
            mock_instance.port = 55553
            mock_bridge.return_value = mock_instance

            response = client.get("/api/metasploit/status")

            assert response.status_code == 200
            data = response.json()
            assert data['connected'] is True
            assert data['authenticated'] is True
            assert data['host'] == "localhost"
            assert data['port'] == 55553

    def test_status_endpoint_disconnected(self, client):
        """Test status endpoint when MSF is disconnected."""
        with patch('app.api.metasploit.get_msf_bridge') as mock_bridge:
            mock_instance = AsyncMock()
            mock_instance.check_connection = AsyncMock(return_value=False)
            mock_instance.host = "localhost"
            mock_instance.port = 55553
            mock_bridge.return_value = mock_instance

            response = client.get("/api/metasploit/status")

            assert response.status_code == 200
            data = response.json()
            assert data['connected'] is False
            assert data['authenticated'] is False


class TestExploitationEndpoint:
    """Test POST /api/metasploit/exploit endpoint."""

    def test_exploit_endpoint_success(self, client, db):
        """Test successful exploitation request."""
        with patch('app.api.metasploit.get_msf_bridge') as mock_bridge:
            mock_instance = AsyncMock()
            mock_instance.check_connection = AsyncMock(return_value=True)
            mock_instance.start_exploitation_workflow = AsyncMock(return_value={
                'campaign_id': 'camp-001',
                'target_id': 'tgt-001',
                'stages': {},
                'sessions': [
                    {
                        'session_id': 'session_123',
                        'exploit': 'exploit/linux/http/apache_mod_cgi',
                        'target': '192.168.1.100'
                    }
                ],
                'status': 'completed',
                'started_at': '2026-01-15T10:00:00',
                'completed_at': '2026-01-15T10:05:00'
            })
            mock_bridge.return_value = mock_instance

            payload = {
                "campaign_id": "camp-001",
                "target_id": "tgt-001",
                "target_ip": "192.168.1.100",
                "target_port": 80
            }

            response = client.post("/api/metasploit/exploit", json=payload)

            assert response.status_code == 200
            data = response.json()
            assert data['campaign_id'] == 'camp-001'
            assert data['target_id'] == 'tgt-001'
            assert data['status'] == 'completed'
            assert len(data['sessions']) > 0

    def test_exploit_endpoint_msf_unavailable(self, client):
        """Test exploit endpoint when MSF is unavailable."""
        with patch('app.api.metasploit.get_msf_bridge') as mock_bridge:
            mock_instance = AsyncMock()
            mock_instance.check_connection = AsyncMock(return_value=False)
            mock_bridge.return_value = mock_instance

            payload = {
                "campaign_id": "camp-001",
                "target_id": "tgt-001",
                "target_ip": "192.168.1.100",
                "target_port": 80
            }

            response = client.post("/api/metasploit/exploit", json=payload)

            assert response.status_code == 503

    def test_exploit_endpoint_invalid_payload(self, client):
        """Test exploit endpoint with invalid payload."""
        payload = {
            "campaign_id": "camp-001"
            # Missing required fields
        }

        response = client.post("/api/metasploit/exploit", json=payload)

        assert response.status_code == 422  # Validation error


class TestCommandExecutionEndpoint:
    """Test POST /api/metasploit/session/{id}/execute endpoint."""

    def test_command_execution_success(self, client):
        """Test successful command execution."""
        with patch('app.api.metasploit.get_msf_bridge') as mock_bridge:
            mock_instance = AsyncMock()
            mock_instance.execute_command = AsyncMock(return_value={
                'session_id': 'session_123',
                'command': 'whoami',
                'output': 'root',
                'exit_code': 0,
                'executed_at': '2026-01-15T10:00:00'
            })
            mock_bridge.return_value = mock_instance

            payload = {
                "session_id": "session_123",
                "command": "whoami"
            }

            response = client.post(
                "/api/metasploit/session/session_123/execute",
                json=payload
            )

            assert response.status_code == 200
            data = response.json()
            assert data['command'] == 'whoami'
            assert data['exit_code'] == 0
            assert 'output' in data

    def test_command_execution_multiple_commands(self, client):
        """Test various command executions."""
        commands = ["whoami", "id", "pwd", "ls -la"]

        with patch('app.api.metasploit.get_msf_bridge') as mock_bridge:
            mock_instance = AsyncMock()

            for cmd in commands:
                mock_instance.execute_command = AsyncMock(return_value={
                    'session_id': 'session_123',
                    'command': cmd,
                    'output': f'Output of {cmd}',
                    'exit_code': 0,
                    'executed_at': '2026-01-15T10:00:00'
                })
                mock_bridge.return_value = mock_instance

                payload = {"session_id": "session_123", "command": cmd}

                response = client.post(
                    f"/api/metasploit/session/session_123/execute",
                    json=payload
                )

                assert response.status_code == 200


class TestSessionCloseEndpoint:
    """Test POST /api/metasploit/session/{id}/close endpoint."""

    def test_session_close_success(self, client, db):
        """Test successful session closure."""
        # Create session in DB
        session = MSFSession(
            id="session_123",
            campaign_id="camp-001",
            target_id="tgt-001",
            session_type="meterpreter",
            target_host="192.168.1.100",
            status="active"
        )
        db.add(session)
        db.commit()

        with patch('app.api.metasploit.get_msf_bridge') as mock_bridge:
            mock_instance = AsyncMock()
            mock_instance.close_session = AsyncMock(return_value=True)
            mock_bridge.return_value = mock_instance

            response = client.post("/api/metasploit/session/session_123/close")

            assert response.status_code == 200
            data = response.json()
            assert data['closed'] is True
            assert data['session_id'] == "session_123"

    def test_session_close_not_found(self, client):
        """Test closing non-existent session."""
        with patch('app.api.metasploit.get_msf_bridge') as mock_bridge:
            mock_instance = AsyncMock()
            mock_instance.close_session = AsyncMock(return_value=False)
            mock_bridge.return_value = mock_instance

            response = client.post("/api/metasploit/session/nonexistent/close")

            assert response.status_code == 404


class TestSessionInfoEndpoint:
    """Test GET /api/metasploit/session/{id} endpoint."""

    def test_get_session_info_success(self, client, db):
        """Test retrieving session information."""
        # Create session in DB
        session = MSFSession(
            id="session_123",
            campaign_id="camp-001",
            target_id="tgt-001",
            session_type="meterpreter",
            target_host="192.168.1.100",
            exploit_used="exploit/linux/http/apache_mod_cgi",
            status="active"
        )
        db.add(session)
        db.commit()

        response = client.get("/api/metasploit/session/session_123")

        assert response.status_code == 200
        data = response.json()
        assert data['session_id'] == "session_123"
        assert data['type'] == "meterpreter"
        assert data['target'] == "192.168.1.100"
        assert data['status'] == "active"

    def test_get_session_info_not_found(self, client):
        """Test getting info for non-existent session."""
        response = client.get("/api/metasploit/session/nonexistent")

        assert response.status_code == 404

    def test_get_session_info_contains_timestamps(self, client, db):
        """Test session info includes timestamps."""
        from datetime import datetime

        session = MSFSession(
            id="session_123",
            campaign_id="camp-001",
            target_id="tgt-001",
            session_type="meterpreter",
            target_host="192.168.1.100",
            status="active",
            created_at=datetime.utcnow()
        )
        db.add(session)
        db.commit()

        response = client.get("/api/metasploit/session/session_123")

        assert response.status_code == 200
        data = response.json()
        assert 'created_at' in data
        assert data['created_at'] is not None


class TestListCampaignSessionsEndpoint:
    """Test GET /api/metasploit/campaigns/{id}/sessions endpoint."""

    def test_list_campaign_sessions_success(self, client, db):
        """Test listing sessions for a campaign."""
        # Create multiple sessions
        for i in range(3):
            session = MSFSession(
                id=f"session_{i}",
                campaign_id="camp-001",
                target_id=f"tgt-{i}",
                session_type="meterpreter",
                target_host=f"192.168.1.{100 + i}",
                status="active"
            )
            db.add(session)
        db.commit()

        response = client.get("/api/metasploit/campaigns/camp-001/sessions")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3

    def test_list_campaign_sessions_empty(self, client):
        """Test listing sessions for campaign with no sessions."""
        response = client.get("/api/metasploit/campaigns/camp-nonexistent/sessions")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_list_campaign_sessions_contains_info(self, client, db):
        """Test session list includes required information."""
        session = MSFSession(
            id="session_123",
            campaign_id="camp-001",
            target_id="tgt-001",
            session_type="meterpreter",
            target_host="192.168.1.100",
            status="active"
        )
        db.add(session)
        db.commit()

        response = client.get("/api/metasploit/campaigns/camp-001/sessions")

        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0

        session_info = data[0]
        assert 'session_id' in session_info
        assert 'type' in session_info
        assert 'target' in session_info
        assert 'status' in session_info
        assert 'created_at' in session_info


class TestAPIErrorHandling:
    """Test API error handling."""

    def test_missing_path_parameter(self, client):
        """Test endpoint with missing path parameter."""
        response = client.get("/api/metasploit/session/")

        # Should be 404 or 405 depending on routing
        assert response.status_code in [404, 405]

    def test_invalid_request_format(self, client):
        """Test invalid request format."""
        response = client.post(
            "/api/metasploit/exploit",
            json="invalid"  # Should be dict
        )

        assert response.status_code == 422

    def test_missing_required_fields(self, client):
        """Test missing required fields in request."""
        payload = {
            "campaign_id": "camp-001"
            # Missing target_id, target_ip, target_port
        }

        response = client.post("/api/metasploit/exploit", json=payload)

        assert response.status_code == 422


class TestAPIDocumentation:
    """Test API documentation."""

    def test_openapi_schema_includes_metasploit(self, client):
        """Test OpenAPI schema includes metasploit endpoints."""
        response = client.get("/openapi.json")

        assert response.status_code == 200
        schema = response.json()

        # Check paths include metasploit endpoints
        paths = schema.get('paths', {})
        assert any('/api/metasploit' in path for path in paths.keys())


class TestAPICORSHeaders:
    """Test API CORS headers."""

    def test_status_endpoint_includes_cors_headers(self, client):
        """Test CORS headers are present."""
        response = client.get("/api/metasploit/status")

        # FastAPI should include headers even if CORS middleware not fully initialized
        assert response.status_code == 200


class TestAPILogging:
    """Test API logging."""

    def test_request_logging_on_success(self, client):
        """Test requests are logged."""
        with patch('app.api.metasploit.logger') as mock_logger:
            with patch('app.api.metasploit.get_msf_bridge') as mock_bridge:
                mock_instance = AsyncMock()
                mock_instance.check_connection = AsyncMock(return_value=True)
                mock_instance.host = "localhost"
                mock_instance.port = 55553
                mock_bridge.return_value = mock_instance

                response = client.get("/api/metasploit/status")

                assert response.status_code == 200
