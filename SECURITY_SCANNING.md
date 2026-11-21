# Dabcam Phase 2: Comprehensive Security Scanning Guide

**Security Scanning Infrastructure** for SAST, DAST, dependency analysis, and secret detection.

---

## 🛡️ Security Scanning Tools Overview

### 1. Static Application Security Testing (SAST)

#### Semgrep - Fast SAST with Rules Registry
```bash
# Install
pip install semgrep

# Scan
semgrep --config=p/security-audit --config=p/owasp-top-ten --json backend/

# Docker
docker run returntocorp/semgrep semgrep --config=p/security-audit .
```

#### GitHub CodeQL - Semantic Code Analysis
```bash
# GitHub Actions integration (automatic)
# Scans Python and JavaScript
# Results in Security → Code scanning
```

#### OWASP Dependency-Check
```bash
# Docker scan
docker run --rm -v $(pwd):/src owasp/dependency-check:latest \
  --project 'Dabcam' --scan /src --format JSON

# Install locally
brew install dependency-check  # macOS
```

---

### 2. Dependency Vulnerability Scanning

#### Trivy - Multi-scanner
```bash
# Filesystem scan
docker run aquasec/trivy fs /path/to/code

# Generate SBOM
docker run aquasec/trivy fs --format sbom --output sbom.json .

# Scan dependencies
docker run aquasec/trivy fs --severity CRITICAL,HIGH .
```

#### Anchore Grype
```bash
# Install
curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh

# Scan
grype dir:.
grype sbom:sbom.json

# Docker
docker run anchore/grype dir:.
```

#### Google OSV-Scanner
```bash
# Install
go install github.com/google/osv-scanner/cmd/osv-scanner@latest

# Scan lockfiles
osv-scanner --lockfile=backend/requirements.txt
osv-scanner --lockfile=frontend/package-lock.json

# Git repository scan
osv-scanner --repo=.
```

#### Anchore Syft - SBOM Generation
```bash
# Install
curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh

# Generate SBOM
syft -o json backend/ > sbom.json
syft -o spdx-json backend/ > sbom-spdx.json
syft -o cyclonedx-json backend/ > sbom-cyclonedx.json
```

---

### 3. Secret Detection

#### GitLeaks
```bash
# Install
brew install gitleaks  # macOS

# Detect secrets in current directory
gitleaks detect --source .

# Scan git history
gitleaks detect --source . --verbose

# Docker
docker run zricethezav/gitleaks detect --source /repo
```

#### TruffleHog
```bash
# Install
pip install truffleHog

# Scan filesystem
trufflehog filesystem /path/to/scan

# Scan git history
trufflehog git https://github.com/owner/repo

# Docker
docker run ghcr.io/trufflesecurity/trufflehog filesystem /repo
```

#### Trivy Secret Scanning
```bash
# Included in Trivy
trivy secret .
trivy secret backend/app/main.py
```

---

### 4. Dynamic Application Security Testing (DAST)

#### OWASP ZAP
```bash
# Install
brew install zaproxy  # macOS

# Baseline scan
zap.sh -t http://localhost:8001 -r zap-report.html

# Full scan
zap.sh -t http://localhost:8001 -a -r zap-report.html

# Docker API scan
docker run -t owasp/zap2docker-stable \
  zap-api-scan.py -t http://localhost:8001/docs \
  -f openapi -r zap-api-report.html
```

#### ProjectDiscovery Nuclei
```bash
# Install
go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest

# Vulnerability scanning
nuclei -u http://localhost:8001 -t cves,vulnerabilities

# Template-based scanning
nuclei -u http://localhost:8001 -tl  # List templates

# Generate report
nuclei -u http://localhost:8001 -t cves -json > nuclei-report.json
```

#### SQLMap - SQL Injection Testing
```bash
# Install
pip install sqlmap

# Test API endpoint
sqlmap -u "http://localhost:8001/api/campaigns" \
  --dbs --batch --level=5 --risk=3

# Test with POST data
sqlmap -u "http://localhost:8001/api/campaigns" \
  --data="name=test" --dbs --batch
```

---

## 🚀 Quick Start: Run All Scans

### Local Development

```bash
# 1. SAST Scans
semgrep --config=p/security-audit --config=p/owasp-top-ten --json backend/

# 2. Dependency Scans
trivy fs .
osv-scanner --lockfile=backend/requirements.txt

# 3. Secret Scans
gitleaks detect --source .
trufflehog filesystem .

# 4. Backend Unit Tests
pytest backend/

# 5. DAST (after services started)
nuclei -u http://localhost:8001 -t cves,vulnerabilities
zap.sh -t http://localhost:8001 -r zap-report.html
```

### Docker - Combined Scan

```bash
# Create scan network
docker network create scan-net

# Start backend
docker run -d --name backend --network scan-net -p 8001:8000 dabcam-backend

# Run all scans
docker run --rm -v $(pwd):/scan --network scan-net returntocorp/semgrep semgrep --config=p/security-audit /scan
docker run --rm -v $(pwd):/scan aquasec/trivy fs /scan
docker run --rm -v $(pwd):/scan zricethezav/gitleaks detect --source /scan

# Cleanup
docker stop backend
docker rm backend
docker network rm scan-net
```

---

## 🔄 CI/CD Integration

### GitHub Actions Workflow

Located at `.github/workflows/security-scan.yml`

Runs on:
- Every push to master/develop
- Every pull request
- Daily schedule (2 AM UTC)

Includes:
- ✓ Semgrep SAST
- ✓ CodeQL Analysis
- ✓ Dependency-Check
- ✓ Trivy FS Scan
- ✓ GitLeaks Secrets
- ✓ OSV-Scanner
- ✓ Bandit Python Security
- ✓ Safety Dependency Check
- ✓ Container Image Scan

### Pre-commit Hooks

Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash
set -e

echo "Running pre-commit security checks..."

# Run gitleaks
gitleaks detect --source . --exit-code 1

# Run semgrep
semgrep --config=p/security-audit --config=p/owasp-top-ten --json .

# Run bandit
bandit -r backend/app -f json

echo "✓ Pre-commit security checks passed"
```

Make executable:
```bash
chmod +x .git/hooks/pre-commit
```

---

## 📊 Scan Results & Reporting

### Result Formats

**JSON**:
```bash
semgrep --json
trivy fs --format json
grype -o json
osv-scanner --json
```

**SARIF** (GitHub Code Scanning):
```bash
trivy fs --format sarif --output results.sarif
```

**HTML Reports**:
```bash
zap.sh -r report.html
nuclei -json > report.json  # Custom HTML generation
```

### Aggregating Results

Create unified report:
```python
# reports/aggregate.py
import json
from pathlib import Path

reports = {
    'semgrep': Path('semgrep-results.json').read_text(),
    'trivy': Path('trivy-results.json').read_text(),
    'osv': Path('osv-results.json').read_text(),
    'gitleaks': Path('gitleaks-results.json').read_text(),
}

summary = {tool: len(json.loads(data).get('results', [])) 
           for tool, data in reports.items()}

print(json.dumps(summary, indent=2))
```

---

## ⚠️ Vulnerability Severity & Response

### Severity Levels

| Level | CVSS | Action | SLA |
|-------|------|--------|-----|
| **Critical** | 9.0-10.0 | Fix immediately | 4 hours |
| **High** | 7.0-8.9 | Fix within sprint | 24 hours |
| **Medium** | 4.0-6.9 | Schedule fix | 7 days |
| **Low** | 0.1-3.9 | Backlog | 30 days |

### Remediation Workflow

1. **Detection** → Scan finds vulnerability
2. **Verification** → Confirm it's exploitable
3. **Assignment** → Developer assigned
4. **Fixing** → Implement patch
5. **Testing** → Run test suite
6. **Re-scanning** → Verify fix
7. **Deployment** → Push to production
8. **Monitoring** → Watch for regression

---

## 📋 Configuration Files

### Semgrep
Create `.semgrep.yml`:
```yaml
rules:
  - id: custom-sql-injection
    pattern: sql(...)
    message: Potential SQL injection
    severity: HIGH
  
  - id: hardcoded-secrets
    pattern: password = "..."
    message: Hardcoded password
    severity: CRITICAL
```

### Gitleaks
Create `.gitleaks.toml`:
```toml
title = "Gitleaks config"

[[rules]]
id = "aws-access-key"
description = "AWS Access Key"
regex = "AKIA[0-9A-Z]{16}"
entropy = 3.5
keywords = ["aws", "access", "key"]
```

### Trivy
Create `trivy.yaml`:
```yaml
severity:
  - CRITICAL
  - HIGH
  - MEDIUM

skip-dirs:
  - node_modules
  - venv
  - __pycache__

offline-db: false
```

---

## 🔍 Manual Scanning Examples

### Scan a Specific File

```bash
# Semgrep
semgrep --config=p/security-audit backend/app/main.py

# Bandit
bandit backend/app/main.py

# Trivy
trivy fs backend/app/main.py
```

### Scan for Specific Vulnerabilities

```bash
# SQL Injection
sqlmap -u "http://localhost:8001/api/campaigns" --dbs

# XSS
nuclei -u http://localhost:8001 -t xss

# CSRF
nuclei -u http://localhost:8001 -t csrf
```

### Generate SBOM

```bash
# Software Bill of Materials
syft -o json backend/ > sbom.json

# SPDX format
syft -o spdx-json backend/ > sbom.spdx.json

# View SBOM
cat sbom.json | jq '.artifacts[]'
```

---

## 📈 Metrics & Dashboards

### Track Vulnerabilities Over Time

```python
# metrics/vulnerability_tracker.py
import json
from datetime import datetime

scan_results = {
    'timestamp': datetime.now().isoformat(),
    'critical': 2,
    'high': 15,
    'medium': 42,
    'low': 128,
}

# Store in time-series DB
# Graph trends
# Alert on regressions
```

### Quality Gates

Fail CI if:
- ❌ Any CRITICAL vulnerabilities found
- ❌ CVSS score > 8.9 without exception
- ❌ Known vulnerable dependency
- ❌ Secrets detected
- ❌ Code coverage < 60%

---

## 🧰 Installation & Setup

### Local Setup (macOS)

```bash
# Install all tools
brew install semgrep
brew install gitleaks
brew install trivy
brew install zaproxy

# Python tools
pip install bandit safety sqlmap

# Go tools
go install github.com/google/osv-scanner/cmd/osv-scanner@latest
go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
```

### Docker Setup

All tools available via Docker - no installation needed.

---

## 📚 Integration with Phase 2

### Add to Implementation Plan

**Day 5-6: Security Scanning Infrastructure**
- [ ] Install all scanning tools
- [ ] Create GitHub Actions workflows
- [ ] Set up pre-commit hooks
- [ ] Configure severity thresholds
- [ ] Run baseline scans
- [ ] Document findings

### Add to Requirements

Backend requirements already include:
- bandit (Python security)
- safety (dependency checker)

---

## 🎯 Success Criteria

✓ All scans run in CI/CD  
✓ No CRITICAL vulnerabilities  
✓ <5 HIGH severity issues  
✓ All secrets detected and removed  
✓ SBOM generated for releases  
✓ <30 day remediation SLA for all issues  
✓ Zero secrets in git history  
✓ 100% dependency vulnerability coverage  

---

## 📞 Support & References

| Tool | Docs | GitHub |
|------|------|--------|
| Semgrep | https://semgrep.dev/docs | returntocorp/semgrep |
| CodeQL | https://codeql.github.com | github/codeql |
| Trivy | https://trivy.dev | aquasecurity/trivy |
| Grype | https://anchore.com/grype | anchore/grype |
| GitLeaks | https://gitleaks.io | gitleaks/gitleaks |
| TruffleHog | https://www.trufflesecurity.com | trufflesecurity/trufflehog |
| Nuclei | https://nuclei.projectdiscovery.io | projectdiscovery/nuclei |
| ZAP | https://www.zaproxy.org | zaproxy/zaproxy |
| SQLMap | http://sqlmap.org | sqlmapproject/sqlmap |

---

**Security Scanning Ready for Phase 2** 🔐

