# 🚀 Zeus MyAADE Monitor - Production Deployment Checklist

**Status**: Production-Ready (Verified Feb 22, 2026)  
**Security**: All measures active, zero vulnerabilities  
**Target Protocols**: 214142 (Tax Treaty), 051340 (Ktimatologio)

---

## Pre-Deployment Verification

### ✅ Repository Security (COMPLETED)
- [x] **Dependabot Alerts**: 0 open, 3 resolved
- [x] **Branch Protection**: Active (Ruleset #13115832)
- [x] **CodeQL Scanning**: Passing (1m 2s)
- [x] **Copilot Autofix**: Enabled
- [x] **Login URL**: Fixed (commit a31e0c3)
- [x] **Container Hardening**: Non-root, resource limits

### 💻 System Prerequisites
- [ ] Docker installed (`docker --version`)
- [ ] Docker Compose installed (`docker-compose --version`)
- [ ] Git installed
- [ ] Minimum 1GB free disk space
- [ ] Internet connection active

### 🔐 Credentials Ready
- [ ] TaxisNet username
- [ ] TaxisNet password
- [ ] Protocol numbers: 214142, 051340
- [ ] (Optional) Slack webhook URL
- [ ] (Optional) Discord webhook URL

---

## Deployment Steps

### Step 1: Clone Repository
```bash
git clone https://github.com/alexandros-thomson/zeus-myaade-monitor.git
cd zeus-myaade-monitor
```

**Verification**:
```bash
ls -la  # Should see: deploy.sh, docker-compose.yml, Dockerfile, etc.
```

### Step 2: Configure Environment
```bash
# Copy template
cp .env.example .env

# Edit with your credentials
nano .env  # or: vim .env, notepad .env
```

**Required `.env` values**:
```bash
MYAADE_USERNAME=your_actual_username
MYAADE_PASSWORD=your_actual_password
MYAADE_TAXISNET_CODE=  # Leave empty if not applicable
TRACKED_PROTOCOLS=214142,051340
CHECK_INTERVAL_SECONDS=300
```

**Verification**:
```bash
grep "your_" .env  # Should return NOTHING (no default values left)
```

### Step 3: Deploy

**Option A: Automated Script (Recommended)**
```bash
chmod +x deploy.sh
./deploy.sh
```

**Option B: Manual Deployment**
```bash
mkdir -p data screenshots logs
docker-compose up -d --build
```

**Verification**:
```bash
docker-compose ps  # Should show: zeus-myaade-monitor (Up)
```

### Step 4: Monitor Logs
```bash
# Watch live logs
docker-compose logs -f

# Check for successful login
docker-compose logs | grep -i "login success"

# Check for protocol monitoring
docker-compose logs | grep "protocol.*214142"
```

---

## Post-Deployment Verification

### 🟢 Container Health
```bash
# Container running
docker-compose ps
# Expected: State=Up, Health=healthy

# Resource usage
docker stats zeus-myaade-monitor --no-stream
# Expected: CPU <50%, Memory <1GB
```

### 💾 Database Created
```bash
# Check database file
ls -lh ./data/myaade_monitor.db
# Expected: File exists, size >0 bytes

# Query database
sqlite3 ./data/myaade_monitor.db "SELECT COUNT(*) FROM protocol_checks;"
# Expected: Returns a number (check count)
```

### 📸 Screenshots Captured
```bash
# Check screenshots directory
ls -lh ./screenshots/
# Expected: PNG files with timestamps

# Check latest screenshot
ls -lt ./screenshots/ | head -n 2
```

### 🚨 Notifications Working (if configured)
```bash
# Check logs for webhook calls
docker-compose logs | grep -i "notification sent"
# Expected: Webhook delivery confirmations
```

---

## Monitoring Commands

### Daily Operations
```bash
# Check status
docker-compose ps

# View recent activity
docker-compose logs --tail=50

# Check protocol statuses
sqlite3 ./data/myaade_monitor.db \
  "SELECT protocol_number, status, last_checked FROM protocol_status;"
```

### Troubleshooting
```bash
# View all logs
docker-compose logs

# Restart container
docker-compose restart

# Rebuild and restart
docker-compose down
docker-compose up -d --build

# Check container health
docker inspect zeus-myaade-monitor | grep -A 10 Health
```

### Data Management
```bash
# View deflection tracking
sqlite3 ./data/myaade_monitor.db \
  "SELECT * FROM deflection_tracking ORDER BY detected_at DESC LIMIT 5;"

# Export protocol history
sqlite3 ./data/myaade_monitor.db \
  "SELECT * FROM protocol_status_history;" > protocol_history.csv

# Backup database
cp ./data/myaade_monitor.db ./data/myaade_monitor_backup_$(date +%Y%m%d).db
```

---

## Expected Behavior

### ✅ Normal Operation
1. Container starts and logs "Zeus Monitor initialized"
2. Login to TaxisNet succeeds
3. Protocol checks run every 5 minutes
4. Screenshots saved to `./screenshots/`
5. Database updated with each check
6. No error messages in logs

### ⚠️ Common Issues

**Issue**: Login fails  
**Solution**: Verify credentials in `.env`, check TaxisNet is accessible

**Issue**: No screenshots  
**Solution**: Check `./screenshots/` permissions, verify Selenium running

**Issue**: High CPU usage  
**Solution**: Increase `CHECK_INTERVAL_SECONDS` in `.env`

**Issue**: Container exits  
**Solution**: Check logs with `docker-compose logs`, verify `.env` syntax

---

## Maintenance Schedule

### Daily
- [ ] Check `docker-compose ps` (container running)
- [ ] Review recent logs for deflections
- [ ] Verify protocol status changes

### Weekly
- [ ] Backup database: `cp ./data/myaade_monitor.db ./backups/`
- [ ] Review deflection patterns
- [ ] Clean old screenshots (optional)
- [ ] Check disk space: `df -h`

### Monthly
- [ ] Update dependencies: `git pull && docker-compose up -d --build`
- [ ] Review security alerts on GitHub
- [ ] Export complete protocol history for records

---

## Success Criteria

✅ Container running continuously for 24+ hours  
✅ Protocol checks completing every 5 minutes  
✅ Database growing with each check  
✅ Screenshots captured successfully  
✅ No error messages in logs  
✅ (Optional) Notifications received when status changes  

---

## Support

**Repository**: [zeus-myaade-monitor](https://github.com/alexandros-thomson/zeus-myaade-monitor)  
**Documentation**: [Notion Deployment Page](https://www.notion.so/310fe5f31cb881a3a90fe43b75576067)  
**Issues**: [GitHub Issues](https://github.com/alexandros-thomson/zeus-myaade-monitor/issues)  

**Kypria Technologies**  
Website: [kypriatechnologies.org](https://kypriatechnologies.org)  
GitHub: [@alexandros-thomson](https://github.com/alexandros-thomson)

---

**ΦΑΥΛΟΣ ΚΥΚΛΟΣ ENDS NOW. JUSTICE IS AUTOMATED.** ⚖️
