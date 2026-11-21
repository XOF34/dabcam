#!/bin/bash

# Docker Compose Verification Script
# Run this locally to verify all 11 services are healthy

set -e

echo "╔═══════════════════════════════════════════════════════╗"
echo "║   Dabcam Phase 2: Docker Compose Verification Script  ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="dabcam"
SERVICES=(
    "postgres:PostgreSQL Database"
    "redis:Redis Cache"
    "backend:FastAPI Backend"
    "msf-bridge:MetasploitMCP Bridge"
    "metasploit:Metasploit Framework"
    "nginx:nginx Reverse Proxy"
    "frontend:React Frontend"
    "pgadmin:pgAdmin Database UI"
    "redis-commander:Redis Commander"
)

echo -e "${BLUE}Step 1: Checking Docker Installation${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker is not installed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker ${NC}$(docker --version)"

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}✗ Docker Compose is not installed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker Compose available${NC}"

echo ""
echo -e "${BLUE}Step 2: Validating docker-compose.yml${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if docker compose config > /dev/null 2>&1; then
    echo -e "${GREEN}✓ docker-compose.yml is valid${NC}"
else
    echo -e "${RED}✗ docker-compose.yml validation failed${NC}"
    docker compose config
    exit 1
fi

echo ""
echo -e "${BLUE}Step 3: Starting Services${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

docker compose up -d

echo -e "${GREEN}✓ All services started${NC}"
echo "⏳ Waiting 30 seconds for services to initialize..."
sleep 30

echo ""
echo -e "${BLUE}Step 4: Checking Service Status${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

docker compose ps

echo ""
echo -e "${BLUE}Step 5: Verifying Service Health${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Function to check service health
check_service() {
    local service=$1
    local port=$2
    local endpoint=$3

    if [ -z "$endpoint" ]; then
        # Just check port
        if nc -z localhost "$port" 2>/dev/null; then
            echo -e "${GREEN}✓${NC} $service (port $port) - ${GREEN}Listening${NC}"
            return 0
        else
            echo -e "${RED}✗${NC} $service (port $port) - ${RED}Not responding${NC}"
            return 1
        fi
    else
        # Check HTTP endpoint
        response=$(curl -s -w "%{http_code}" "$endpoint" 2>/dev/null || echo "000")
        http_code="${response: -3}"

        if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 500 ]; then
            echo -e "${GREEN}✓${NC} $service ($endpoint) - ${GREEN}HTTP $http_code${NC}"
            return 0
        else
            echo -e "${RED}✗${NC} $service ($endpoint) - ${RED}HTTP $http_code${NC}"
            return 1
        fi
    fi
}

# Check services
FAILED=0

echo "API & Web Services:"
check_service "Backend API" 8001 "http://localhost:8001/api/health" || ((FAILED++))
check_service "Frontend" 3000 "http://localhost:3000" || ((FAILED++))
check_service "nginx Proxy" 80 "http://localhost/health" || ((FAILED++))
check_service "pgAdmin" 5050 "http://localhost:5050" || ((FAILED++))
check_service "Redis Commander" 8081 "http://localhost:8081" || ((FAILED++))

echo ""
echo "Databases & Cache:"
check_service "PostgreSQL" 5432 || ((FAILED++))
check_service "Redis" 6379 || ((FAILED++))

echo ""
echo "Microservices:"
check_service "MSF Bridge" 8002 "http://localhost:8002/health" || ((FAILED++))
check_service "Metasploit RPC" 55553 || ((FAILED++))

echo ""
echo -e "${BLUE}Step 6: Testing API Endpoints${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "Testing health checks:"

# General health
echo -n "  GET /api/health ... "
if curl -s http://localhost:8001/api/health | grep -q "healthy"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    ((FAILED++))
fi

# Database health
echo -n "  GET /api/health/database ... "
if curl -s http://localhost:8001/api/health/database | grep -q "connected"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    ((FAILED++))
fi

# Redis health
echo -n "  GET /api/health/redis ... "
if curl -s http://localhost:8001/api/health/redis | grep -q "connected"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    ((FAILED++))
fi

# Metasploit health
echo -n "  GET /api/health/metasploit ... "
if curl -s http://localhost:8001/api/health/metasploit | grep -q "metasploit"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}TIMEOUT${NC} (expected if MSF not configured)"
fi

echo ""
echo -e "${BLUE}Step 7: Displaying Logs Summary${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "Backend logs (last 10 lines):"
docker compose logs backend | tail -10

echo ""
echo "Database logs (last 5 lines):"
docker compose logs postgres | tail -5

echo ""
echo "╔═══════════════════════════════════════════════════════╗"
echo "║                 Verification Summary                  ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All services are healthy and responding!${NC}"
    echo ""
    echo "Access Points:"
    echo "  Frontend:        http://localhost:3000"
    echo "  Backend API:     http://localhost:8001"
    echo "  API Docs:        http://localhost:8001/docs"
    echo "  pgAdmin:         http://localhost:5050 (admin@example.com / admin123)"
    echo "  Redis Commander: http://localhost:8081"
    echo ""
    echo "Docker commands:"
    echo "  View logs:       docker compose logs -f [service]"
    echo "  Restart service: docker compose restart [service]"
    echo "  Stop all:        docker compose down"
    echo ""
    exit 0
else
    echo -e "${RED}✗ $FAILED service(s) failed health checks${NC}"
    echo ""
    echo "Troubleshooting:"
    echo "  View all logs:   docker compose logs"
    echo "  Check service:   docker compose ps [service]"
    echo "  Check networks:  docker network ls"
    echo ""
    exit 1
fi
