# ⚖️ Zeus MyAADE Monitor

**Automated monitoring system that ENDS THE ΦΑΥΛΟΣ ΚΥΚΛΟΣ (vicious circle) of Greek bureaucracy.**

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

Automatically detects three main deflection tactics:

1. **Forwarding** - "Not our jurisdiction, try another agency"
2. **Vague Response** - "Απαντήθηκε" without actually solving anything
3. **Delay Tactic** - Requesting "supplementary documents" endlessly

When deflection is detected, you get:
- 🚨 High-priority alert
- 📋 Specific recommendations
- 📊 Deflection count (escalate if ≥2)
- 🎯 Suggested next actions

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

## Security

- ✅ Credentials stored in `.env` (never committed)
- ✅ `.gitignore` prevents accidental exposure
- ✅ Container runs without new privileges
- ✅ Read-only filesystem where possible
- ✅ Resource limits enforced

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