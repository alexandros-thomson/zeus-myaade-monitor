# =============================================================================
# ZEUS MYAADE MONITOR -- WINDOWS DEPLOYMENT (PowerShell)
# =============================================================================
#
# Usage:
#   .\deploy.ps1
#
# Prerequisites:
#   - Docker Desktop and Docker Compose installed
#   - .env file configured with MyAADE credentials
#
# Author: Kostas Kyprianos / Kypria Technologies
# Case: EPPO PP.00179/2026/EN | FBI IC3 | IRS CI Art. 26
#
# =============================================================================

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

# Color output functions
function Write-Success { param($Message) Write-Host $Message -ForegroundColor Green }
function Write-Info { param($Message) Write-Host $Message -ForegroundColor Cyan }
function Write-Warn { param($Message) Write-Host $Message -ForegroundColor Yellow }
function Write-Err { param($Message) Write-Host $Message -ForegroundColor Red }
function Write-Header { param($Message) Write-Host "`n$Message`n" -ForegroundColor Magenta }

Write-Header "ZEUS MYAADE MONITOR - WINDOWS DEPLOYMENT"
Write-Info "Checking prerequisites..."

# Check Docker Desktop
try {
    $dockerVersion = docker --version
    Write-Success "Docker Desktop: $dockerVersion"
} catch {
    Write-Err "Docker Desktop not found. Install from https://www.docker.com/products/docker-desktop"
    exit 1
}

# Check Docker Compose
try {
    $composeVersion = docker-compose --version
    Write-Success "Docker Compose: $composeVersion"
} catch {
    Write-Err "Docker Compose not found. Install Docker Desktop."
    exit 1
}

# Check Git
try {
    $gitVersion = git --version
    Write-Success "Git: $gitVersion"
} catch {
    Write-Err "Git not found. Install from https://git-scm.com/download/win"
    exit 1
}

# Clone repository if not already present
$repoName = "zeus-myaade-monitor"
if (Test-Path $repoName) {
    Write-Info "Repository exists. Pulling latest changes..."
    Set-Location $repoName
    git pull origin main
} else {
    Write-Info "Cloning repository..."
    git clone https://github.com/alexandros-thomson/zeus-myaade-monitor.git
    Set-Location $repoName
}
Write-Success "Repository ready"

# Create .env file if it doesn't exist
if (-not (Test-Path ".env")) {
    Write-Info "Creating .env configuration file..."
    Copy-Item .env.example .env
    Write-Warn ".env file created. You MUST edit it with your credentials:"
    Write-Host "  1. Open .env in Notepad" -ForegroundColor Yellow
    Write-Host "  2. Set MYAADE_USERNAME (TaxisNet username)" -ForegroundColor Yellow
    Write-Host "  3. Set MYAADE_PASSWORD (TaxisNet password)" -ForegroundColor Yellow
    Write-Host "  4. Set PROTOCOLS (comma-separated: 214142,051340)" -ForegroundColor Yellow
    Write-Host "  5. Set SLACK_WEBHOOK_URL (optional)" -ForegroundColor Yellow
    Write-Host "  6. Save and close" -ForegroundColor Yellow
    notepad .env
    Write-Host "`nPress Enter when you've edited the .env file..." -ForegroundColor Cyan
    Read-Host
}

# Validate .env has required variables
Write-Info "Validating .env configuration..."
$envContent = Get-Content .env -Raw
if ($envContent -match "MYAADE_USERNAME=your_taxisnet_username") {
    Write-Err ".env file not configured! Edit it with your actual credentials."
    exit 1
}
Write-Success "Configuration validated"

# Create required directories
Write-Info "Creating data directories..."
New-Item -ItemType Directory -Force -Path "data" | Out-Null
New-Item -ItemType Directory -Force -Path "screenshots" | Out-Null
Write-Success "Directories created"

# Build Docker image
Write-Header "BUILDING DOCKER IMAGE"
docker-compose build
if ($LASTEXITCODE -ne 0) {
    Write-Err "Docker build failed"
    exit 1
}
Write-Success "Docker image built successfully"

# Start monitoring service
Write-Header "STARTING ZEUS MYAADE MONITOR"
docker-compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Err "Failed to start monitoring service"
    exit 1
}
Write-Success "Zeus MyAADE Monitor is now running!"

# Show status
Write-Info "Checking service status..."
Start-Sleep -Seconds 3
docker-compose ps

# Show initial logs
Write-Header "INITIAL LOGS (Last 20 lines)"
docker-compose logs --tail=20 myaade-monitor

# Deployment complete
Write-Header "DEPLOYMENT COMPLETE"
Write-Success "Zeus MyAADE Monitor is running in the background"
Write-Host ""
Write-Info "Useful Commands:"
Write-Host "  View logs:       docker-compose logs -f myaade-monitor" -ForegroundColor Cyan
Write-Host "  Stop service:    docker-compose down" -ForegroundColor Cyan
Write-Host "  Restart service: docker-compose restart" -ForegroundColor Cyan
Write-Host "  Check status:    docker-compose ps" -ForegroundColor Cyan
Write-Host ""
Write-Info "Files:"
Write-Host "  Screenshots: .\screenshots\" -ForegroundColor Cyan
Write-Host "  Database:    .\data\myaade_monitor.db" -ForegroundColor Cyan
Write-Host ""
Write-Success "The system will check MyAADE every 5 minutes automatically"
Write-Success "You will receive Slack/Discord alerts on status changes"
Write-Host ""
Write-Header "PHAYLOS KYKLOS ENDED. JUSTICE AUTOMATED."
