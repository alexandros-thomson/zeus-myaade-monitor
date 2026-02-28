<div align="center">
  <img src="https://raw.githubusercontent.com/alexandros-thomson/zeus-myaade-monitor/main/assets/zeus-myaade-crest.png" width="120" height="120" alt="Zeus MYAADE Monitor Crest" style="border-radius:50%; border:3px solid #DAA520;" />
  <br />
</div>

# ⚖️ Zeus MyAADE Monitor

![Security Status](https://img.shields.io/badge/security-production--ready-brightgreen)
![Dependencies](https://img.shields.io/badge/dependencies-0%20vulnerabilities-success)
![Branch Protection](https://img.shields.io/badge/branch%20protection-active-success)
![CodeQL](https://img.shields.io/badge/CodeQL-passing-success)
![Tests](https://github.com/alexandros-thomson/zeus-myaade-monitor/actions/workflows/tests.yml/badge.svg)
![Zeus MYAADE Monitor](https://img.shields.io/badge/Zeus_MYAADE_Monitor-v1.0-gold?style=flat-square&logo=data:image/png;base64,iVBORw0KGgo=&logoColor=gold)
![Case](https://img.shields.io/badge/Case-Kyprianos_v_AADE-crimson?style=flat-square)
![Justice](https://img.shields.io/badge/Justice_for_Ioannis-%E2%9A%96%EF%B8%8F-blue?style=flat-square)

**Automated monitoring system that ENDS THE ΦΑΥΛΟΣ ΚΥΚΛΟΣ (vicious circle) of Greek bureaucracy.**

> **🎯 PRODUCTION-READY**: All security measures verified. Zero vulnerabilities. Ready for deployment (Feb 22, 2026).

## Mission

Monitor MyAADE protocol statuses 24/7, detect bureaucratic deflection tactics, and alert you immediately when status changes occur.

## Features

- ✅ **Real-time monitoring** of MyAADE protocols
- 🎯 **Deflection detection** - Identifies when AADE forwards, delays, or gives vague responses
- 🚨 **Instant alerts** via Slack/Discord/Webhook
- 📸 **Automatic screenshots** of every status check
- 📊 **Complete audit trail** in SQLite database
- 🔄 **Auto-recovery** with retry logic
- 🐳 **Docker deployment** for easy setup

## Quick Start

### Prerequisites

- Docker & Docker Compose
- MyAADE/TaxisNet credentials
- (Optional) Slack/Discord webhook for notifications

### 1-Minute Deployment

```bash
# Clone repository
git clone https://github.com/alexandros-thomson/zeus-myaade-monitor.git
cd zeus-myaade-monitor

# Run deployment script
chmod +x deploy.sh
./deploy.sh
```

The script will:
1. Check dependencies
2. Create `.env` file (you'll need to edit it with credentials)
3. Build Docker image
4. Start monitoring service

### Manual Setup

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Edit .env with your credentials
nano .env

# 3. Build and start
docker-compose up -d

# 4. View logs
docker-compose logs -f
```

## Configuration

Edit `.env` file:

```bash
# Required
MYAADE_USERNAME=your_username
MYAADE_PASSWORD=your_password

# Recommended
SLACK_WEBHOOK_URL=https://hooks.slack.com/...

# Optional
CHECK_INTERVAL_SECONDS=300  # Check every 5 minutes
TRACKED_PROTOCOLS=214142,051340  # Specific protocols
```

## How It Works

### Status Classification

The monitor understands Greek bureaucracy patterns:

| Greek Status | English | Meaning | Action Required |
|--------------|---------|---------|-----------------||
| Απαντήθηκε | Answered | They replied (≠ solved!) | ✅ Review response immediately |
| Διαβιβάστηκε | Forwarded | Deflection tactic | 🎯 Submit rebuttal |
| Ολοκληρώθηκε | Completed | Actually done | ✅ Download results |
| Εκκρεμεί | Pending | Still waiting | ⏳ Continue monitoring |

### Deflection Detection

Automatically detects four main deflection tactics:

1. **Forwarding** - "Not our jurisdiction, try another agency"
2. **Vague Response** - "Απαντήθηκε" without actually solving anything
3. **Delay Tactic** - Requesting "supplementary documents" endlessly
4. **ΔΟΥ A' Peiraia Redirect** - Forwarding Δ210 submissions to ΔΟΥ Κατοίκων Εξωτερικού (illegal jurisdiction dodge)

When deflection is detected, you get:
- 🚨 High-priority alert
- 📋 Specific recommendations
- 📊 Deflection count (escalate if ≥2)
- 🎯 Suggested next actions

## Δ210 Monitoring

### Overview

The monitor includes dedicated tracking for **Δ210 submissions** — formal requests for the complete ENFIA history of a taxpayer (AFM). This is critical for exposing fraudulent ENFIA billing on third-party properties (e.g., KAEK 050681726008).

### Configuration

Add to `.env`:

```bash
# Δ210 protocol tracking
D210_PROTOCOL_ID=your_d210_protocol_number   # Protocol number assigned by AADE
D210_DB_PATH=/app/data/d210_tracker.db       # Shared SQLite path (dual-repo)
```

### ΔΟΥ A' Peiraia Deflection Detection

The monitor automatically detects when ΔΟΥ A' Peiraia attempts to redirect Δ210 submissions to **ΔΟΥ Κατοίκων Εξωτερικού** — a known deflection tactic used against overseas taxpayers.

**Trigger keywords (Greek):** `δου κατοίκων εξωτερικού`, `αρμόδια δου εξωτερικού`, `κατοίκων εξωτερικού`

When this pattern is detected:
- Alert severity is set to **CRITICAL**
- A dedicated Slack alert fires with the cover letter excerpt embedded
- The deflection is recorded in `d210_submissions` table with `deflection_type = 'doy_peiraia_redirect'`

### Slack Alerts for Δ210 Status Changes

Δ210 status changes fire a rich Slack message that includes:
- Protocol number and current status
- Deflection type (if any)
- ΔΟΥ response excerpt
- Embedded **cover letter excerpt** (Δ210 filing summary for EPPO/ΣΔΟΕ/FBI cross-reference)

### Database: Δ210 Submissions Table

The `d210_submissions` table in the **shared SQLite database** enables dual-repo coordination between `zeus-myaade-monitor` and `justice-for-john-automation`:

```sql
SELECT * FROM d210_submissions ORDER BY updated_at DESC;
```

| Column | Description |
|--------|-------------|
| `submission_id` | Unique Δ210 submission identifier |
| `protocol_number` | AADE protocol number |
| `submitting_doy` | ΔΟΥ that received the submission |
| `status` | Current status (`pending`, `deflected`, `answered`, `escalated`) |
| `doy_response` | Raw response text from ΔΟΥ |
| `deflection_type` | Detected deflection pattern (e.g., `doy_peiraia_redirect`) |
| `cover_letter_excerpt` | Cover letter summary embedded in Slack alerts |
| `slack_alerted` | Whether a Slack alert was sent |

### Dual-Repo Deployment

To coordinate with `justice-for-john-automation`, point both repos at the **same SQLite file**:

```bash
# zeus-myaade-monitor .env
D210_DB_PATH=/shared/data/d210_tracker.db

# justice-for-john-automation .env
D210_DB_PATH=/shared/data/d210_tracker.db
```

With Docker, mount a shared volume:

```yaml
# docker-compose.yml (both repos)
volumes:
  - /host/shared/data:/app/data
```

## Commands

```bash
# View status
docker-compose ps

# View logs (live)
docker-compose logs -f

# View recent logs
docker-compose logs --tail=50

# Restart monitor
docker-compose restart

# Stop monitor
docker-compose down

# Check database
sqlite3 ./data/myaade_monitor.db "SELECT * FROM protocol_status;"

# View deflections
sqlite3 ./data/myaade_monitor.db "SELECT * FROM deflection_tracking ORDER BY detected_at DESC;"
```

## File Structure

```
zeus-myaade-monitor/
├── myaade_monitor_zeus.py    # Main monitoring script
├── docker-compose.yml         # Docker stack configuration
├── Dockerfile                 # Container image definition
├── requirements.txt           # Python dependencies
├── deploy.sh                  # One-command deployment
├── .env.example               # Environment template
├── .env                       # Your credentials (NOT committed)
├── data/                      # Database (persistent)
│   └── myaade_monitor.db     # SQLite database
├── screenshots/               # Protocol screenshots
└── logs/                      # Application logs
```

## Database Schema

### `protocol_status`
Current status of all tracked protocols.

### `protocol_status_history`
Complete audit trail of all status changes.

### `deflection_tracking`
Records of detected bureaucratic deflection tactics.

## Notifications

### Slack
Set `SLACK_WEBHOOK_URL` in `.env`:
```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### Discord
Set `DISCORD_WEBHOOK_URL` in `.env`:
```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR/WEBHOOK
```

## Documentation

- [Complete Deployment Guide](DEPLOYMENT-GUIDE.md)
- [Production Setup](docs/production-setup.md)
- [Troubleshooting](docs/troubleshooting.md)


## Testing

Zeus uses **pytest** for automated testing. The test suite covers the core monitor engine and the email integration system.

### Run Tests Locally

```bash
# Install test dependencies
pip install pytest pytest-cov selenium requests python-dotenv colorama

# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ -v --cov=. --cov-report=term-missing

# Run specific test file
python -m pytest tests/test_email_integration.py -v
```

### CI/CD

Tests run automatically on every push and pull request via GitHub Actions across Python 3.10, 3.11, and 3.12.
## Security

### Production Security Status (Verified Feb 22, 2026)

✅ **Zero Vulnerabilities** - All Dependabot alerts resolved  
✅ **Branch Protection** - Force push and deletion blocked on main  
✅ **CodeQL Scanning** - Active with AI-powered Copilot Autofix  
✅ **Container Hardening** - Non-root user, resource limits, read-only filesystem  
✅ **Credentials Protected** - Never committed, .gitignore enforced  

**Security Metrics:**
- Dependabot Alerts: 0 open, 3 closed (100% resolved)
- CodeQL Status: Passing (1m 2s scan time)
- Branch Protection: Active (Ruleset #13115832)

## System Requirements

- **CPU**: 0.5-2 cores
- **RAM**: 512MB-2GB
- **Disk**: 1GB minimum (for database, screenshots, logs)
- **OS**: Linux (Ubuntu 20.04+), macOS, Windows with WSL2

## License

MIT License - Use freely, END THE ΦΑΥΛΟΣ ΚΥΚΛΟΣ everywhere.

## Author

**Kostas Kyprianos** / Kypria Technologies
- Website: [kypriatechnologies.org](https://kypriatechnologies.org)
- GitHub: [@alexandros-thomson](https://github.com/alexandros-thomson)

## Acknowledgments

Built with frustration, determination, and the unwavering belief that:

> **"Απαντήθηκε ≠ Solved. The deflection ends TODAY."**

⚖️ **ΦΑΥΛΟΣ ΚΥΚΛΟΣ ENDS NOW. JUSTICE IS AUTOMATED.**
