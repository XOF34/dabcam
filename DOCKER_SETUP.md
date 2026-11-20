# Docker Compose Setup & Verification Guide

## Overview

This guide provides step-by-step instructions to start the Dabcam Phase 2 Docker Compose stack locally and verify all 11 services are running correctly.

**Note**: Docker daemon is not available in cloud environments. Run these commands on your local machine.

---

## Prerequisites

### Required
- **Docker**: 20.10+ ([Install Docker](https://docs.docker.com/get-docker/))
- **Docker Compose**: 2.0+ (included with Docker Desktop)
- **System Resources**: 
  - 4GB RAM minimum
  - 10GB free disk space
  - Ports 80, 443, 3000, 5050, 6379, 5432, 8001, 8002, 8081, 55553 available

### Optional
- `netcat` (nc) - for port checking
- `curl` - for API testing

---

## 11 Services Overview

| # | Service | Port | Purpose | Status |
|---|---------|------|---------|--------|
| 1 | PostgreSQL | 5432 | Database | Core |
| 2 | Redis | 6379 | Cache & Sessions | Core |
| 3 | FastAPI Backend | 8001 | REST API | Core |
| 4 | MetasploitMCP Bridge | 8002 | MSF Integration | Core |
| 5 | Metasploit RPC | 55553 | Exploitation Engine | Core |
| 6 | nginx | 80, 443 | Reverse Proxy | Core |
| 7 | React Frontend | 3000 | Web Dashboard | UI |
| 8 | pgAdmin | 5050 | Database UI | Optional |
| 9 | Redis Commander | 8081 | Cache UI | Optional |
| 10 | (Reserved) | - | - | - |
| 11 | (Reserved) | - | - | - |

---

## Quick Start (5 Minutes)

### 1. Clone Repository (if not already done)
```bash
cd /path/to/dabcam-phase2
```

### 2. Configure Environment
```bash
# Copy environment template
cp .env.example .env

# Review and edit if needed (defaults work for development)
cat .env
```

### 3. Start Services
```bash
# Start all services
docker compose up -d

# Wait for initialization
sleep 30

# Check status
docker compose ps
```

### 4. Verify Setup
```bash
# Run verification script
bash DOCKER_VERIFY.sh
```

### 5. Access Services
```
Frontend:        http://localhost:3000
Backend API:     http://localhost:8001
API Docs:        http://localhost:8001/docs
pgAdmin:         http://localhost:5050
Redis Commander: http://localhost:8081
```

---

## Detailed Setup Process

### Step 1: Environment Setup

```bash
# Navigate to project
cd /home/user/dabcam-phase2

# Copy environment file
cp .env.example .env

# Edit if needed (optional - defaults work)
nano .env

# Key environment variables:
# - SECRET_KEY: Change for production (use: openssl rand -hex 32)
# - DATABASE_URL: PostgreSQL connection string
# - MSF_RPC_PASS: Metasploit RPC password
# - NGROK_AUTHTOKEN: Your ngrok token (optional)
```

### Step 2: Start Services

```bash
# Start all services in background
docker compose up -d

# Check if services are starting
docker compose ps

# Expected output:
# STATUS              Ports
# Up (health: starting)   Various
```

### Step 3: Wait for Initialization

Services take time to initialize:
- PostgreSQL: 5-10 seconds
- Redis: 2-3 seconds  
- FastAPI: 10-15 seconds
- Metasploit: 20-30 seconds
- Others: 5-10 seconds

```bash
# Wait 30 seconds for all services to initialize
sleep 30

# Check status again
docker compose ps

# Expected: All services should show "Up"
```

### Step 4: Verify Health

```bash
# Test API endpoints
curl http://localhost:8001/api/health

# Expected response:
# {"status":"healthy","timestamp":"2026-11-20T..."}

# Test database
curl http://localhost:8001/api/health/database
# Expected: {"status":"healthy","database":"connected"}

# Test Redis
curl http://localhost:8001/api/health/redis
# Expected: {"status":"healthy","redis":"connected"}
```

### Step 5: Access Services

| Service | URL | Credentials |
|---------|-----|-------------|
| Frontend | http://localhost:3000 | No login yet |
| Backend Swagger UI | http://localhost:8001/docs | Interactive |
| pgAdmin | http://localhost:5050 | admin@example.com / admin123 |
| Redis Commander | http://localhost:8081 | No login |

---

## Automated Verification Script

We've created `DOCKER_VERIFY.sh` to automate all checks:

```bash
# Run verification script
bash DOCKER_VERIFY.sh

# This script will:
# 1. Check Docker installation
# 2. Validate docker-compose.yml
# 3. Start services
# 4. Wait for initialization
# 5. Check all service status
# 6. Test API endpoints
# 7. Display logs summary
# 8. Report health status
```

### Expected Output

```
╔═══════════════════════════════════════════════════════╗
║   Dabcam Phase 2: Docker Compose Verification Script  ║
╚═══════════════════════════════════════════════════════╝

Step 1: Checking Docker Installation
✓ Docker version 20.10.0
✓ Docker Compose version 2.0+

Step 2: Validating docker-compose.yml
✓ docker-compose.yml is valid

Step 3: Starting Services
✓ All services started

Step 4: Checking Service Status
postgres         Up (health: starting)
redis            Up (health: starting)
backend          Up (health: starting)
...

Step 5: Verifying Service Health
✓ Backend API (port 8001) - Listening
✓ Frontend (port 3000) - Listening
✓ PostgreSQL (port 5432) - Listening
✓ Redis (port 6379) - Listening
...

Step 6: Testing API Endpoints
  GET /api/health ... OK
  GET /api/health/database ... OK
  GET /api/health/redis ... OK
...

╔═══════════════════════════════════════════════════════╗
║                 Verification Summary                  ║
╚═══════════════════════════════════════════════════════╝

✓ All services are healthy and responding!
```

---

## Common Operations

### View Logs

```bash
# View all logs (follow mode)
docker compose logs -f

# View specific service logs
docker compose logs -f backend
docker compose logs -f postgres
docker compose logs -f redis

# View last 50 lines
docker compose logs --tail=50 backend
```

### Access Services

```bash
# PostgreSQL shell
docker compose exec postgres psql -U dabcam_user -d dabcam

# Redis shell
docker compose exec redis redis-cli

# Backend shell
docker compose exec backend bash

# Run Python script
docker compose exec backend python -c "print('Hello')"
```

### Database Operations

```bash
# Initialize database
docker compose exec backend python -c "from app.database import init_db; init_db()"

# Drop all tables (TESTING ONLY)
docker compose exec backend python -c "from app.database import drop_db; drop_db()"

# Reset database completely
docker compose down -v postgres
docker compose up -d postgres
sleep 10
docker compose up -d
```

### Service Management

```bash
# Restart a service
docker compose restart backend

# Stop all services
docker compose stop

# Start stopped services
docker compose start

# Stop and remove containers (keep data)
docker compose down

# Stop and remove everything (clean slate)
docker compose down -v

# Remove unused images
docker image prune -f

# Remove dangling containers
docker container prune -f
```

---

## Troubleshooting

### Services won't start

**Problem**: `Error response from daemon`

**Solution**:
```bash
# Check Docker daemon
docker ps

# Restart Docker daemon
sudo systemctl restart docker

# Try again
docker compose up -d
```

### Port already in use

**Problem**: `Bind for 0.0.0.0:8001 failed: port is already allocated`

**Solution**:
```bash
# Find process using port
lsof -i :8001

# Change port in docker-compose.yml or:
docker compose down
sleep 5
docker compose up -d
```

### Database connection fails

**Problem**: Backend can't connect to PostgreSQL

**Solution**:
```bash
# Check PostgreSQL is running
docker compose ps postgres

# Check logs
docker compose logs postgres

# Reset PostgreSQL
docker compose down -v postgres
docker compose up -d postgres
sleep 10
docker compose up -d

# Verify connection
docker compose exec postgres psql -U dabcam_user -d dabcam -c "SELECT 1"
```

### High memory/disk usage

**Problem**: Docker using too much resources

**Solution**:
```bash
# Check resource usage
docker stats

# Remove old data
docker system prune -f

# Remove images not in use
docker image prune -af

# Stop and remove all
docker compose down -v
```

### Service health check failing

**Problem**: Service stuck in "health: starting"

**Solution**:
```bash
# Check logs
docker compose logs backend

# Wait longer
sleep 60

# Check again
docker compose ps

# Restart service
docker compose restart backend
```

---

## Performance Tips

### Increase Docker Resource Limits

**Docker Desktop (macOS/Windows)**:
1. Open Docker Desktop
2. Settings → Resources
3. Increase CPUs and Memory
4. Restart Docker

**Linux**:
```bash
# Edit /etc/docker/daemon.json
{
  "storage-driver": "overlay2",
  "storage-opts": [
    "overlay2.override_kernel_check=true"
  ]
}

# Restart Docker
sudo systemctl restart docker
```

### Optimize Networks

```bash
# Prune unused networks
docker network prune -f

# Check network health
docker network ls
docker network inspect dabcam-phase2_dabcam-net
```

### Volume Performance

```bash
# Check volume usage
docker volume ls
docker volume inspect <volume_name>

# Prune unused volumes
docker volume prune -f
```

---

## Health Checks

### Manual Health Checks

```bash
# API Health
curl -v http://localhost:8001/api/health

# Database Health
curl http://localhost:8001/api/health/database

# Redis Health
curl http://localhost:8001/api/health/redis

# Metasploit Health
curl http://localhost:8001/api/health/metasploit

# Frontend
curl http://localhost:3000

# nginx Proxy
curl -v http://localhost/health
```

### Automatic Health Monitoring

```bash
# Watch container health in real-time
watch -n 2 'docker compose ps'

# Monitor resource usage
docker stats

# Monitor logs
docker compose logs -f --tail=20
```

---

## Next Steps

Once all services are verified as healthy:

1. **Access API Documentation**
   - Open http://localhost:8001/docs
   - Explore available endpoints

2. **Test Database Connection**
   - Use pgAdmin at http://localhost:5050
   - Login: admin@example.com / admin123
   - Verify tables exist

3. **Begin Phase 2 Implementation**
   - Follow `docs/PHASE2_IMPLEMENTATION_PLAN.md`
   - Create feature branch
   - Start fixing vulnerabilities

4. **Monitor Development**
   - Watch logs: `docker compose logs -f backend`
   - Run tests: `docker compose exec backend pytest`
   - Commit changes: `git commit -m "..."`

---

## Support & References

| Resource | Location |
|----------|----------|
| **Quick Start** | QUICKSTART.md |
| **Implementation Plan** | docs/PHASE2_IMPLEMENTATION_PLAN.md |
| **Git Workflow** | GIT_STATUS.md |
| **Verification Script** | DOCKER_VERIFY.sh |
| **Docker Docs** | https://docs.docker.com/ |
| **Docker Compose Docs** | https://docs.docker.com/compose/ |

---

## Commands Quick Reference

```bash
# Start
docker compose up -d
sleep 30

# Verify
bash DOCKER_VERIFY.sh

# Monitor
docker compose logs -f

# Stop
docker compose down

# Clean
docker compose down -v
docker system prune -f
```

---

**Setup Date**: 2026-11-20  
**Services**: 11  
**Status**: Ready for Phase 2 Implementation 🚀
