"""
Dabcam + MetasploitMCP Backend
Secure camera exploitation framework with Metasploit integration
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import logging
from datetime import datetime
from contextlib import asynccontextmanager
import os

# Configuration
from dotenv import load_dotenv
load_dotenv()

# Structured logging
from pythonjsonlogger import jsonlogger
import structlog

# Security
from fastapi.security import HTTPBearer

# Database
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Initialize logger
logger = logging.getLogger()
handler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Configuration
class Settings:
    """Application settings from environment variables"""
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dabcam_user:changeme123@localhost:5432/dabcam")
    REDIS_URL = os.getenv("REDIS_URL", "redis://:redis123@localhost:6379/0")
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    MSF_RPC_HOST = os.getenv("MSF_RPC_HOST", "localhost")
    MSF_RPC_PORT = int(os.getenv("MSF_RPC_PORT", 55553))
    MSF_RPC_USER = os.getenv("MSF_RPC_USER", "msf")
    MSF_RPC_PASS = os.getenv("MSF_RPC_PASS", "changeme123")
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # Security
    CORS_ORIGINS = ["http://localhost:3000", "http://localhost:80"]
    ALLOWED_HOSTS = ["localhost", "127.0.0.1", "dabcam.local"]

    # Upload limits
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
    MAX_STORAGE = 10 * 1024 * 1024 * 1024  # 10GB
    STORAGE_DIR = "/secure/storage"

settings = Settings()

# ============================================
# Lifespan Events
# ============================================

async def startup_event():
    """Initialize application"""
    logger.info("🚀 Starting Dabcam Backend", extra={
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.utcnow().isoformat()
    })

    # Test database connection
    try:
        from app.database import engine
        with engine.connect() as conn:
            result = conn.execute("SELECT 1")
            logger.info("✅ Database connection successful")
    except Exception as e:
        logger.error("❌ Database connection failed", extra={"error": str(e)})

async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("🛑 Shutting down Dabcam Backend")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan"""
    await startup_event()
    # Initialize webhook manager
    from app.services.webhook_manager import initialize_webhooks, shutdown_webhooks
    await initialize_webhooks()
    yield
    await shutdown_webhooks()
    await shutdown_event()

# ============================================
# FastAPI Application
# ============================================

app = FastAPI(
    title="Dabcam API",
    description="Secure camera exploitation framework with MetasploitMCP integration",
    version="2.0.0",
    lifespan=lifespan
)

# ============================================
# Security Middleware
# ============================================

# 1. Trusted Host Middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.ALLOWED_HOSTS
)

# 2. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-CSRF-Token"],
    max_age=3600
)

# 3. Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses"""
    response = await call_next(request)

    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"

    # XSS Protection
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # HTTPS enforcement
    response.headers["Strict-Transport-Security"] = (
        "max-age=63072000; includeSubDomains; preload"
    )

    # Content Security Policy
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self'; "
        "connect-src 'self' http://localhost:* http://127.0.0.1:*; "
        "frame-ancestors 'none'"
    )

    # Referrer Policy
    response.headers["Referrer-Policy"] = "no-referrer"

    # Permissions Policy
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), "
        "usb=(), payment=(), magnetometer=()"
    )

    # Remove server header
    response.headers.pop("Server", None)

    return response

# 4. CSRF Protection Middleware
from app.middleware.csrf_middleware import CSRFMiddleware
import redis

# Try to initialize Redis for CSRF service
try:
    csrf_redis = redis.from_url(settings.REDIS_URL)
    csrf_redis.ping()
    logger.info("✅ CSRF Redis connection established")
except Exception as e:
    csrf_redis = None
    logger.warning(f"⚠️  CSRF Redis connection failed: {e}")

app.add_middleware(CSRFMiddleware, redis_client=csrf_redis)

# ============================================
# Error Handlers
# ============================================

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors"""
    logger.error("Unhandled exception", extra={
        "error": str(exc),
        "path": request.url.path,
        "method": request.method
    })

    if settings.ENVIRONMENT == "development":
        return JSONResponse(
            status_code=500,
            content={"error": str(exc), "type": type(exc).__name__}
        )
    else:
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"}
        )

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle validation errors"""
    return JSONResponse(
        status_code=400,
        content={"error": str(exc)}
    )

# ============================================
# Health Check Endpoints
# ============================================

@app.get("/")
async def root():
    """API root"""
    return {
        "name": "Dabcam API",
        "version": "2.0.0",
        "status": "healthy"
    }

@app.get("/api/health")
async def health_check():
    """General health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/health/database")
async def check_database():
    """Check database connectivity"""
    try:
        from app.database import engine
        with engine.connect() as conn:
            result = conn.execute("SELECT 1")
            return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error("Database health check failed", extra={"error": str(e)})
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}

@app.get("/api/health/redis")
async def check_redis():
    """Check Redis connectivity"""
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL)
        r.ping()
        return {"status": "healthy", "redis": "connected"}
    except Exception as e:
        logger.error("Redis health check failed", extra={"error": str(e)})
        return {"status": "unhealthy", "redis": "disconnected", "error": str(e)}

@app.get("/api/health/metasploit")
async def check_metasploit():
    """Check MetasploitMCP bridge connectivity"""
    try:
        from app.services.msf_bridge import msf_bridge
        is_connected = await msf_bridge.check_connection()
        return {
            "status": "healthy" if is_connected else "unhealthy",
            "metasploit": "connected" if is_connected else "disconnected"
        }
    except Exception as e:
        logger.error("MSF health check failed", extra={"error": str(e)})
        return {"status": "unhealthy", "metasploit": "error", "error": str(e)}

# ============================================
# API Routes
# ============================================

# Campaign Management (TODO: will be created in next phase)
# from app.api import campaigns
# app.include_router(campaigns.router, prefix="/api/campaigns", tags=["campaigns"])

# Target Management (TODO: will be created in next phase)
# from app.api import targets
# app.include_router(targets.router, prefix="/api/targets", tags=["targets"])

# Session Management (TODO: will be created in next phase)
# from app.api import sessions
# app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])

# Photo Capture
from app.api import captures
app.include_router(captures.router, prefix="/api/captures", tags=["captures"])

# Binary Dependencies
from app.api import binaries
app.include_router(binaries.router, prefix="/api/binaries", tags=["binaries"])

# CSRF Token Management
from app.api import csrf_tokens
app.include_router(csrf_tokens.router, prefix="/api/csrf", tags=["csrf"])

# Metasploit Bridge
from app.api import metasploit
app.include_router(metasploit.router, prefix="/api/metasploit", tags=["metasploit"])

# Webhook Management
from app.api import webhooks
app.include_router(webhooks.router, tags=["webhooks"])

# Webhook Delivery Status (Phase 3.4)
from app.api import webhook_delivery_status
app.include_router(webhook_delivery_status.router)

# Webhook Replay Service (Phase 3.5)
from app.api import webhook_replay
app.include_router(webhook_replay.router)

# Webhook Logs API (Phase 3.6)
from app.api import webhook_logs
app.include_router(webhook_logs.router)

# Event Webhooks (TODO: will be created in next phase)
# from app.webhooks import capture_webhook, session_webhook
# app.include_router(capture_webhook.router, prefix="/webhook", tags=["webhooks"])
# app.include_router(session_webhook.router, prefix="/webhook", tags=["webhooks"])

# ============================================
# Request Logging Middleware
# ============================================

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests"""
    request_id = request.headers.get("x-request-id", "unknown")

    logger.info("Incoming request", extra={
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "client": request.client.host if request.client else "unknown"
    })

    response = await call_next(request)

    logger.info("Outgoing response", extra={
        "request_id": request_id,
        "status_code": response.status_code
    })

    return response

# ============================================
# Startup
# ============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.ENVIRONMENT == "development",
        log_level=settings.LOG_LEVEL.lower()
    )
