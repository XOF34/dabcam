# Dabcam Phase 2 Quick Start Guide

Get the development environment running in 5 minutes.

## 1. Prerequisites

```bash
# Check Docker
docker --version
docker-compose --version

# Should output Docker 20.10+ and Docker Compose 2.0+
```

## 2. Clone & Setup

```bash
# Navigate to project
cd dabcam-phase2

# Copy environment file
cp .env.example .env

# Review environment variables (defaults work for development)
cat .env
```

## 3. Start Services

```bash
# Start all services (11 containers)
docker-compose up -d

# Wait for services to initialize
sleep 10

# Check status
docker-compose ps
```

## 4. Verify Services

```bash
# Check all services are healthy
curl http://localhost:8001/api/health

# Expected output:
# {"status":"healthy","timestamp":"2026-11-20T..."}

# Check database
curl http://localhost:8001/api/health/database

# Check Redis
curl http://localhost:8001/api/health/redis

# Check Metasploit bridge
curl http://localhost:8001/api/health/metasploit
```

## 5. Access Services

| Service | URL | Credentials |
|---------|-----|-------------|
| **Frontend** | http://localhost:3000 | No login yet |
| **Backend Docs** | http://localhost:8001/docs | Interactive Swagger UI |
| **pgAdmin** | http://localhost:5050 | admin@example.com / admin123 |
| **Redis Commander** | http://localhost:8081 | No login |

## 6. First API Call

```bash
# Get API documentation
curl http://localhost:8001/docs

# Create a campaign (example)
curl -X POST http://localhost:8001/api/campaigns \
  -H "Content-Type: application/json" \
  -d '{
    "name": "test-campaign",
    "description": "Test campaign",
    "payload_type": "camera_msf",
    "created_by": "user@example.com"
  }'
```

## 7. View Logs

```bash
# Backend logs
docker-compose logs -f backend

# Database logs
docker-compose logs -f postgres

# All services
docker-compose logs -f

# Press Ctrl+C to stop viewing logs
```

## 8. Stop Services

```bash
# Stop all services (keeps data)
docker-compose down

# Stop and remove data (clean slate)
docker-compose down -v
```

## Common Tasks

### Run Tests
```bash
docker-compose exec backend pytest -v
```

### Access Backend Shell
```bash
docker-compose exec backend bash
```

### Access Database
```bash
docker-compose exec postgres psql -U dabcam_user -d dabcam
```

### View Real-time Metrics
```bash
# In separate terminal
watch -n 1 'docker-compose stats --no-stream'
```

### Reset Everything
```bash
docker-compose down -v
docker system prune -f
docker-compose up -d
```

## Next Steps

1. **Review Implementation Plan**
   ```bash
   cat docs/PHASE2_IMPLEMENTATION_PLAN.md
   ```

2. **Start Phase 2 Work**
   - Follow day-by-day breakdown in `docs/PHASE2_IMPLEMENTATION_PLAN.md`
   - Start with Day 1-2: Environment Setup verification

3. **Create Feature Branch**
   ```bash
   git checkout -b feature/fix-cri-01
   ```

4. **Begin Implementation**
   - Fix CRI-01: Arbitrary File Write (see docs for details)
   - Write tests
   - Commit changes

## Troubleshooting

### Services won't start
```bash
# Check Docker daemon
docker ps

# View full logs
docker-compose logs

# Reset
docker-compose down -v
docker-compose up -d
```

### Port already in use
```bash
# Find what's using port 8001
lsof -i :8001

# Kill process or change port in docker-compose.yml
```

### Database won't initialize
```bash
# Check PostgreSQL logs
docker-compose logs postgres

# Reset database
docker-compose down -v postgres
docker-compose up -d postgres
sleep 5
docker-compose up -d
```

### Can't connect to Redis
```bash
# Check Redis is running
docker-compose ps redis

# Try to ping Redis
docker-compose exec redis redis-cli ping

# Should output: PONG
```

## Support

For issues, see the full README:
```bash
cat README.md
```

For security vulnerabilities, see:
```bash
cat docs/SECURITY_VULNERABILITIES.md
```

For integration details, see:
```bash
cat docs/METASPLOIT_INTEGRATION.md
```

---

**You're ready to start Phase 2 implementation!** 🚀

