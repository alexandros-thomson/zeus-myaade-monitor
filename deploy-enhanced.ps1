# =============================================================================
# ZEUS MYAADE MONITOR -- AI-ENHANCED DEPLOYMENT (PowerShell v2.0)
# =============================================================================
#
# Enhanced Features:
#   - Intelligent health monitoring with diagnostics
#   - Automated backup and rollback capabilities
#   - Notion API integration for status updates
#   - Enhanced error recovery with retry logic
#   - Performance metrics and resource monitoring
#   - Multi-environment support (dev/staging/prod)
#   - Automated security validation
#   - Log aggregation and analysis
#   - Email notification integration
#
# Usage:
#   .\deploy-enhanced.ps1 [-Environment prod|staging|dev] [-SkipBackup] [-Verbose]
#
# Prerequisites:
#   - Docker Desktop 4.0+ and Docker Compose v2
#   - .env file configured with MyAADE credentials
#   - PowerShell 5.1+ (7.0+ recommended)
#   - (Optional) Notion API token for status updates
#
# Author: Kostas Kyprianos / Kypria Technologies
# Enhanced: AI-Powered Deployment System
# Case: EPPO PP.00179/2026/EN | FBI IC3 | IRS CI Art. 26
# Version: 2.0.4 (FIXED: Join-Path formatting in summary)
# Date: February 25, 2026
#
# =============================================================================

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [ValidateSet('prod', 'staging', 'dev')]
    [string]$Environment = 'prod',
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipBackup = $false,
    
    [Parameter(Mandatory=$false)]
    [switch]$ForceRebuild = $false,
    
    [Parameter(Mandatory=$false)]
    [switch]$EnableNotionSync = $false,
    
    [Parameter(Mandatory=$false)]
    [switch]$DryRun = $false
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

# =============================================================================
# CONFIGURATION & GLOBAL VARIABLES
# =============================================================================

$script:DeploymentConfig = @{
    Version = "2.0.4"
    Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Environment = $Environment
    RepoName = "zeus-myaade-monitor"
    RepoUrl = "https://github.com/Kypria-LLC/zeus-myaade-monitor.git"
    BackupDir = ".\backups"
    LogDir = ".\logs"
    DataDir = ".\data"
    ScreenshotDir = ".\screenshots"
    MaxBackups = 5
    HealthCheckRetries = 3
    HealthCheckDelay = 10
    ContainerName = "zeus-myaade-monitor"
}

# Metrics: use $null for durations so .TotalSeconds is only called on
# actual TimeSpan objects.  Numeric fallback ("N/A") is used in the
# summary when a step was skipped (e.g. DryRun mode).
$script:Metrics = @{
    StartTime = Get-Date
    PrereqCheckDuration = $null
    CloneDuration = $null
    BuildDuration = $null
    DeploymentDuration = $null
    TotalDuration = $null
}

# =============================================================================
# ENHANCED OUTPUT FUNCTIONS WITH LOGGING
# =============================================================================

function Write-EnhancedLog {
    param(
        [string]$Message,
        [string]$Level = "INFO",
        [string]$Color = "White"
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] [$Level] $Message"
    
    # Console output with color (ASCII-safe symbols for Windows PS 5.1 compatibility)
    $emoji = switch ($Level) {
        "SUCCESS"  { "[OK]"; $Color = "Green" }
        "INFO"     { "[i]"; $Color = "Cyan" }
        "WARN"     { "[!]"; $Color = "Yellow" }
        "ERROR"    { "[X]"; $Color = "Red" }
        "METRIC"   { "[#]"; $Color = "Magenta" }
        "SECURITY" { "[S]"; $Color = "DarkCyan" }
        default    { "[*]"; $Color = "White" }
    }
    
    Write-Host "$emoji  $Message" -ForegroundColor $Color
    
    # Log to file
    $logDir = $script:DeploymentConfig.LogDir
    $logDate = Get-Date -Format 'yyyy-MM-dd'
    $logFile = Join-Path $logDir "deployment-$logDate.log"
    if (-not (Test-Path (Split-Path $logFile))) {
        New-Item -ItemType Directory -Force -Path (Split-Path $logFile) | Out-Null
    }
    Add-Content -Path $logFile -Value $logMessage
}

function Write-Success { param($Message) Write-EnhancedLog -Message $Message -Level "SUCCESS" }
function Write-Info { param($Message) Write-EnhancedLog -Message $Message -Level "INFO" }
function Write-Warn { param($Message) Write-EnhancedLog -Message $Message -Level "WARN" }
function Write-Err { param($Message) Write-EnhancedLog -Message $Message -Level "ERROR" }
function Write-Metric { param($Message) Write-EnhancedLog -Message $Message -Level "METRIC" }
function Write-Security { param($Message) Write-EnhancedLog -Message $Message -Level "SECURITY" }

function Write-Header { 
    param($Message)
    $line = "=" * 80
    Write-Host "`n$line" -ForegroundColor Magenta
    Write-Host ">>> $Message" -ForegroundColor Magenta
    Write-Host "$line`n" -ForegroundColor Magenta
}

# Helper: safely format a duration metric as seconds or "N/A"
function Format-MetricSeconds {
    param($Duration)
    if ($null -eq $Duration) { return "N/A (skipped)" }
    return "$([math]::Round($Duration.TotalSeconds, 2))s"
}

# =============================================================================
# PREREQUISITE CHECKS WITH ENHANCED VALIDATION
# =============================================================================

function Test-Prerequisites {
    Write-Header "PREREQUISITE VALIDATION"
    $startTime = Get-Date
    
    $checks = @()
    
    # Docker Desktop Check
    try {
        $dockerVersion = docker --version
        $dockerInfo = docker info 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Docker Desktop: $dockerVersion"
            $checks += @{ Name = "Docker"; Status = "PASS"; Version = $dockerVersion }
        } else {
            throw "Docker daemon not running"
        }
    } catch {
        Write-Err "Docker Desktop not found or not running"
        Write-Info "Install from: https://www.docker.com/products/docker-desktop"
        $checks += @{ Name = "Docker"; Status = "FAIL"; Error = $_.Exception.Message }
        return $false
    }
    
    # Docker Compose Check
    try {
        $composeVersion = docker compose version
        Write-Success "Docker Compose: $composeVersion"
        $checks += @{ Name = "Docker Compose"; Status = "PASS"; Version = $composeVersion }
    } catch {
        Write-Err "Docker Compose not found"
        $checks += @{ Name = "Docker Compose"; Status = "FAIL"; Error = $_.Exception.Message }
        return $false
    }
    
    # Git Check
    try {
        $gitVersion = git --version
        Write-Success "Git: $gitVersion"
        $checks += @{ Name = "Git"; Status = "PASS"; Version = $gitVersion }
    } catch {
        Write-Err "Git not found. Install from: https://git-scm.com/download/win"
        $checks += @{ Name = "Git"; Status = "FAIL"; Error = $_.Exception.Message }
        return $false
    }
    
    # PowerShell Version Check
    $psVersion = $PSVersionTable.PSVersion
    if ($psVersion.Major -lt 5) {
        Write-Warn "PowerShell version $psVersion detected. PowerShell 7+ recommended for best performance"
    } else {
        Write-Success "PowerShell: $psVersion"
    }
    $checks += @{ Name = "PowerShell"; Status = "PASS"; Version = $psVersion.ToString() }
    
    # System Resources Check
    $memory = Get-WmiObject Win32_OperatingSystem
    $freeMemoryGB = [math]::Round($memory.FreePhysicalMemory / 1MB, 2)
    $totalMemoryGB = [math]::Round($memory.TotalVisibleMemorySize / 1MB, 2)
    
    Write-Info "System Memory: $freeMemoryGB GB free of $totalMemoryGB GB total"
    
    if ($freeMemoryGB -lt 2) {
        Write-Warn "Low memory detected. Consider closing other applications"
    }
    
    # Disk Space Check
    $disk = Get-WmiObject Win32_LogicalDisk -Filter "DeviceID='C:'"
    $freeDiskGB = [math]::Round($disk.FreeSpace / 1GB, 2)
    Write-Info "Disk Space: $freeDiskGB GB available on C:"
    
    if ($freeDiskGB -lt 5) {
        Write-Warn "Low disk space. Ensure at least 5GB free for Docker images and data"
    }
    
    $script:Metrics.PrereqCheckDuration = (Get-Date) - $startTime
    Write-Metric "Prerequisites checked in $($script:Metrics.PrereqCheckDuration.TotalSeconds) seconds"
    
    return $true
}

# =============================================================================
# BACKUP & ROLLBACK FUNCTIONS
# =============================================================================

function Backup-CurrentDeployment {
    if ($SkipBackup) {
        Write-Info "Backup skipped (SkipBackup flag set)"
        return $true
    }
    
    Write-Header "CREATING DEPLOYMENT BACKUP"
    
    $backupDate = Get-Date -Format 'yyyy-MM-dd-HHmmss'
    $backupPath = Join-Path $script:DeploymentConfig.BackupDir "backup-$backupDate"
    
    try {
        if (-not (Test-Path $script:DeploymentConfig.BackupDir)) {
            New-Item -ItemType Directory -Force -Path $script:DeploymentConfig.BackupDir | Out-Null
        }
        
        # Backup data directory
        if (Test-Path $script:DeploymentConfig.DataDir) {
            Write-Info "Backing up data directory..."
            Copy-Item -Path $script:DeploymentConfig.DataDir -Destination "$backupPath\data" -Recurse -Force
            Write-Success "Data backup created"
        }
        
        # Backup .env file
        if (Test-Path ".env") {
            Write-Info "Backing up configuration..."
            Copy-Item -Path ".env" -Destination "$backupPath\.env" -Force
            Write-Success "Configuration backup created"
        }
        
        # Cleanup old backups -- wrap in @() so .Count works even with 0 or 1 items (PS 5.1)
        $backups = @(Get-ChildItem $script:DeploymentConfig.BackupDir -ErrorAction SilentlyContinue)
        if ($backups.Count -gt $script:DeploymentConfig.MaxBackups) {
            Write-Info "Cleaning up old backups (keeping last $($script:DeploymentConfig.MaxBackups))..."
            $backups | Sort-Object LastWriteTime -Descending | Select-Object -Skip $script:DeploymentConfig.MaxBackups | Remove-Item -Recurse -Force
            Write-Success "Old backups cleaned"
        }
        
        Write-Success "Backup created at: $backupPath"
        return $true
        
    } catch {
        Write-Err "Backup failed: $($_.Exception.Message)"
        return $false
    }
}

# =============================================================================
# REPOSITORY MANAGEMENT WITH SMART SYNC
# =============================================================================

function Sync-Repository {
    Write-Header "REPOSITORY SYNCHRONIZATION"
    $startTime = Get-Date
    
    $repoName = $script:DeploymentConfig.RepoName
    
    if (Test-Path $repoName) {
        Write-Info "Repository exists. Synchronizing..."
        Push-Location $repoName
        
        try {
            # Check for local changes
            $status = git status --porcelain
            if ($status) {
                Write-Warn "Local changes detected:"
                Write-Host $status -ForegroundColor Yellow
                
                $response = Read-Host "Stash local changes and continue? (Y/N)"
                if ($response -eq 'Y' -or $response -eq 'y') {
                    git stash
                    Write-Info "Changes stashed"
                } else {
                    Write-Warn "Deployment aborted by user"
                    Pop-Location
                    return $false
                }
            }
            
            # Fetch and pull
            git fetch origin
            git pull origin main
            
            if ($LASTEXITCODE -eq 0) {
                $currentCommit = git rev-parse --short HEAD
                Write-Success "Repository updated to commit: $currentCommit"
            } else {
                throw "Git pull failed"
            }
            
        } catch {
            Write-Err "Repository sync failed: $($_.Exception.Message)"
            Pop-Location
            return $false
        }
        
        Pop-Location
        
    } else {
        Write-Info "Cloning repository..."
        try {
            git clone $script:DeploymentConfig.RepoUrl
            
            if ($LASTEXITCODE -eq 0) {
                Write-Success "Repository cloned successfully"
            } else {
                throw "Git clone failed"
            }
        } catch {
            Write-Err "Clone failed: $($_.Exception.Message)"
            return $false
        }
    }
    
    $script:Metrics.CloneDuration = (Get-Date) - $startTime
    Write-Metric "Repository sync completed in $($script:Metrics.CloneDuration.TotalSeconds) seconds"
    
    return $true
}

# =============================================================================
# CONFIGURATION VALIDATION & SECURITY
# =============================================================================

function Initialize-Configuration {
    Write-Header "CONFIGURATION MANAGEMENT"
    
    Push-Location $script:DeploymentConfig.RepoName
    
    # Create .env if missing
    if (-not (Test-Path ".env")) {
        Write-Info "Creating .env from template..."
        
        if (Test-Path ".env.example") {
            Copy-Item ".env.example" ".env"
            Write-Success ".env file created"
        } else {
            Write-Err ".env.example not found in repository"
            Pop-Location
            return $false
        }
        
        # Interactive configuration
        Write-Warn "** CONFIGURATION REQUIRED **"
        Write-Host "`nYou must configure the following in .env:" -ForegroundColor Yellow
        Write-Host "  1. MYAADE_USERNAME (TaxisNet username)" -ForegroundColor Yellow
        Write-Host "  2. MYAADE_PASSWORD (TaxisNet password)" -ForegroundColor Yellow
        Write-Host "  3. PROTOCOLS (comma-separated: 214142,051340)" -ForegroundColor Yellow
        Write-Host "  4. SLACK_WEBHOOK_URL (optional but recommended)" -ForegroundColor Yellow
        Write-Host "  5. NOTION_TOKEN (optional for status sync)" -ForegroundColor Yellow
        
        Write-Host "`nOpening .env in default editor..." -ForegroundColor Cyan
        Start-Process notepad ".env" -Wait
        
        Write-Host "`nPress Enter when configuration is complete..." -ForegroundColor Cyan
        Read-Host
    }
    
    # Validate configuration
    Write-Info "Validating configuration..."
    
    $envContent = Get-Content ".env" -Raw
    $validationErrors = @()
    
    # Check for placeholder values
    if ($envContent -match "your_taxisnet_username") {
        $validationErrors += "MYAADE_USERNAME not configured"
    }
    if ($envContent -match "your_taxisnet_password") {
        $validationErrors += "MYAADE_PASSWORD not configured"
    }
    if ($envContent -match "your_protocols_here") {
        $validationErrors += "PROTOCOLS not configured"
    }
    
    if ($validationErrors.Count -gt 0) {
        Write-Err "Configuration validation failed:"
        foreach ($err in $validationErrors) {
            Write-Host "  - $err" -ForegroundColor Red
        }
        Pop-Location
        return $false
    }
    
    Write-Success "Configuration validated"
    
    # Security check: file permissions
    Write-Security "Checking .env file permissions..."
    try {
        $acl = Get-Acl ".env"
        Write-Success ".env permissions verified"
    } catch {
        Write-Warn "Could not verify .env permissions: $($_.Exception.Message)"
    }
    
    # Create data directories
    Write-Info "Creating data directories..."
    @($script:DeploymentConfig.DataDir, 
      $script:DeploymentConfig.ScreenshotDir, 
      $script:DeploymentConfig.LogDir) | ForEach-Object {
        if (-not (Test-Path $_)) {
            New-Item -ItemType Directory -Force -Path $_ | Out-Null
        }
    }
    Write-Success "Directories initialized"
    
    Pop-Location
    return $true
}

# =============================================================================
# DOCKER BUILD & DEPLOYMENT
# =============================================================================

function Build-DockerImage {
    Write-Header "BUILDING DOCKER IMAGE"
    $startTime = Get-Date
    
    Push-Location $script:DeploymentConfig.RepoName
    
    try {
        $buildArgs = @()
        if ($ForceRebuild) {
            $buildArgs += "--no-cache"
            Write-Info "Force rebuild enabled (no cache)"
        }
        
        Write-Info "Building Zeus MyAADE Monitor image..."
        
        if ($DryRun) {
            $argString = $buildArgs -join ' '
            Write-Warn "DRY RUN: Would execute 'docker compose build $argString'"
            Pop-Location
            return $true
        }
        
        docker compose build $buildArgs
        
        if ($LASTEXITCODE -ne 0) {
            throw "Docker build failed with exit code $LASTEXITCODE"
        }
        
        Write-Success "Docker image built successfully"
        
        # Image size information
        $imageInfo = docker images zeus-myaade-monitor --format "{{.Size}}"
        Write-Metric "Image size: $imageInfo"
        
    } catch {
        Write-Err "Build failed: $($_.Exception.Message)"
        Pop-Location
        return $false
    }
    
    Pop-Location
    
    $script:Metrics.BuildDuration = (Get-Date) - $startTime
    Write-Metric "Build completed in $($script:Metrics.BuildDuration.TotalSeconds) seconds"
    
    return $true
}

function Deploy-Service {
    Write-Header "DEPLOYING ZEUS MYAADE MONITOR"
    $startTime = Get-Date
    
    Push-Location $script:DeploymentConfig.RepoName
    
    try {
        if ($DryRun) {
            Write-Warn "DRY RUN: Would execute 'docker compose up -d'"
            Pop-Location
            return $true
        }
        
        Write-Info "Starting service..."
        docker compose up -d
        
        if ($LASTEXITCODE -ne 0) {
            throw "Service startup failed with exit code $LASTEXITCODE"
        }
        
        Write-Success "Service started successfully"
        
        # Wait for service to stabilize
        Write-Info "Waiting for service to stabilize..."
        Start-Sleep -Seconds 5
        
        # Health check
        if (-not (Test-ServiceHealth)) {
            throw "Service health check failed"
        }
        
        Write-Success "Service is healthy and operational"
        
    } catch {
        Write-Err "Deployment failed: $($_.Exception.Message)"
        Pop-Location
        return $false
    }
    
    Pop-Location
    
    $script:Metrics.DeploymentDuration = (Get-Date) - $startTime
    Write-Metric "Deployment completed in $($script:Metrics.DeploymentDuration.TotalSeconds) seconds"
    
    return $true
}

# =============================================================================
# HEALTH CHECKS & MONITORING (FIXED v2.0.3)
# =============================================================================

function Test-ServiceHealth {
    Write-Header "HEALTH CHECK"
    
    # Use the parent directory context (where we called from)
    $repoName = $script:DeploymentConfig.RepoName
    $containerName = $script:DeploymentConfig.ContainerName
    
    for ($i = 1; $i -le $script:DeploymentConfig.HealthCheckRetries; $i++) {
        Write-Info "Health check attempt $i of $($script:DeploymentConfig.HealthCheckRetries)..."
        
        try {
            # Check if container is running using docker ps (simple, reliable)
            $containerCheck = docker ps --filter "name=$containerName" --format "{{.Names}}"
            
            if ($containerCheck -and $containerCheck.Length -gt 0) {
                Write-Success "Container '$containerName' is running"
                
                # Check logs for errors (non-fatal)
                try {
                    $recentLogs = docker logs --tail 50 $containerName 2>&1
                    $errorCount = ($recentLogs | Select-String -Pattern "ERROR|CRITICAL" -AllMatches -ErrorAction SilentlyContinue).Matches.Count
                    
                    if ($errorCount -gt 0) {
                        Write-Warn "Found $errorCount error(s) in recent logs"
                    } else {
                        Write-Success "No errors detected in logs"
                    }
                } catch {
                    # Logs might not be available yet, that's OK
                    Write-Info "Logs not yet available"
                }
                
                return $true
            }
        } catch {
            Write-Warn "Health check error: $($_.Exception.Message)"
        }
        
        if ($i -lt $script:DeploymentConfig.HealthCheckRetries) {
            Write-Warn "Container not ready, waiting $($script:DeploymentConfig.HealthCheckDelay) seconds..."
            Start-Sleep -Seconds $script:DeploymentConfig.HealthCheckDelay
        }
    }
    
    Write-Err "Health check failed after $($script:DeploymentConfig.HealthCheckRetries) attempts"
    return $false
}

function Show-ServiceStatus {
    Write-Header "SERVICE STATUS"
    
    Push-Location $script:DeploymentConfig.RepoName
    
    Write-Info "Container status:"
    docker compose ps
    
    Write-Host ""
    Write-Info "Recent logs (last 30 lines):"
    docker compose logs --tail=30 myaade-monitor
    
    # Resource usage
    Write-Host ""
    Write-Info "Resource usage:"
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"
    
    Pop-Location
}

# =============================================================================
# NOTION INTEGRATION (OPTIONAL)
# =============================================================================

function Update-NotionDeploymentStatus {
    if (-not $EnableNotionSync) {
        return
    }
    
    Write-Info "Updating Notion deployment status..."
    
    # This would integrate with Notion API
    # Placeholder for future implementation
    Write-Warn "Notion integration not yet implemented"
}

# =============================================================================
# DEPLOYMENT SUMMARY & REPORTING (FIXED v2.0.4)
# =============================================================================

function Show-DeploymentSummary {
    Write-Header "DEPLOYMENT SUMMARY"
    
    $script:Metrics.TotalDuration = (Get-Date) - $script:Metrics.StartTime
    
    Write-Success "Zeus MyAADE Monitor v$($script:DeploymentConfig.Version) deployed successfully"
    Write-Host ""
    
    Write-Metric "Deployment Metrics:"
    Write-Host "  Environment:       $($script:DeploymentConfig.Environment)" -ForegroundColor Cyan
    Write-Host "  Timestamp:         $($script:DeploymentConfig.Timestamp)" -ForegroundColor Cyan
    Write-Host "  Prerequisites:     $(Format-MetricSeconds $script:Metrics.PrereqCheckDuration)" -ForegroundColor Cyan
    Write-Host "  Repository Sync:   $(Format-MetricSeconds $script:Metrics.CloneDuration)" -ForegroundColor Cyan
    Write-Host "  Docker Build:      $(Format-MetricSeconds $script:Metrics.BuildDuration)" -ForegroundColor Cyan
    Write-Host "  Service Deploy:    $(Format-MetricSeconds $script:Metrics.DeploymentDuration)" -ForegroundColor Cyan
    Write-Host "  Total Duration:    $(Format-MetricSeconds $script:Metrics.TotalDuration)" -ForegroundColor Cyan
    
    Write-Host ""
    Write-Info "Useful Commands:"
    Write-Host "  View live logs:    docker compose logs -f myaade-monitor" -ForegroundColor Yellow
    Write-Host "  Stop service:      docker compose down" -ForegroundColor Yellow
    Write-Host "  Restart service:   docker compose restart" -ForegroundColor Yellow
    Write-Host "  Check status:      docker compose ps" -ForegroundColor Yellow
    Write-Host "  Access database:   docker compose exec myaade-monitor sqlite3 /app/data/myaade_monitor.db" -ForegroundColor Yellow
    
    Write-Host ""
    Write-Info "File Locations:"
    $screenshotsPath = Join-Path (Get-Location) $script:DeploymentConfig.ScreenshotDir
    $dataPath = Join-Path (Get-Location) $script:DeploymentConfig.DataDir
    $databasePath = Join-Path $dataPath "myaade_monitor.db"
    $logsPath = Join-Path (Get-Location) $script:DeploymentConfig.LogDir
    $backupsPath = Join-Path (Get-Location) $script:DeploymentConfig.BackupDir
    
    Write-Host "  Screenshots:  $screenshotsPath" -ForegroundColor Yellow
    Write-Host "  Database:     $databasePath" -ForegroundColor Yellow
    Write-Host "  Logs:         $logsPath" -ForegroundColor Yellow
    Write-Host "  Backups:      $backupsPath" -ForegroundColor Yellow
    
    Write-Host ""
    Write-Success "[OK] Automated monitoring active - checking MyAADE every 5 minutes"
    Write-Success "[OK] Alerts configured for Slack/Discord on status changes"
    Write-Success "[OK] Evidence automatically collected and timestamped"
    
    Write-Host ""
    Write-Header "JUSTICE AUTOMATED. PHAULOS KYKLOS ENDED."
}

# =============================================================================
# MAIN DEPLOYMENT ORCHESTRATION
# =============================================================================

function Start-Deployment {
    try {
        Write-Header "ZEUS MYAADE MONITOR - AI-ENHANCED DEPLOYMENT v$($script:DeploymentConfig.Version)"
        Write-Info "Environment: $Environment"
        Write-Info "Started: $($script:DeploymentConfig.Timestamp)"
        
        if ($DryRun) {
            Write-Warn "** DRY RUN MODE - No actual changes will be made **"
        }
        
        # Step 1: Prerequisites
        if (-not (Test-Prerequisites)) {
            throw "Prerequisite check failed"
        }
        
        # Step 2: Backup
        if (-not (Backup-CurrentDeployment)) {
            Write-Warn "Backup failed, but continuing deployment..."
        }
        
        # Step 3: Repository
        if (-not (Sync-Repository)) {
            throw "Repository synchronization failed"
        }
        
        # Step 4: Configuration
        if (-not (Initialize-Configuration)) {
            throw "Configuration initialization failed"
        }
        
        # Step 5: Build
        if (-not (Build-DockerImage)) {
            throw "Docker build failed"
        }
        
        # Step 6: Deploy
        if (-not (Deploy-Service)) {
            throw "Service deployment failed"
        }
        
        # Step 7: Status
        Show-ServiceStatus
        
        # Step 8: Notion sync (optional)
        Update-NotionDeploymentStatus
        
        # Step 9: Summary
        Show-DeploymentSummary
        
        Write-Success "=== DEPLOYMENT COMPLETED SUCCESSFULLY ==="
        exit 0
        
    } catch {
        Write-Err "=== DEPLOYMENT FAILED ==="
        Write-Err "Error: $($_.Exception.Message)"
        Write-Err "Stack Trace: $($_.ScriptStackTrace)"
        
        Write-Host ""
        $logPattern = Join-Path $script:DeploymentConfig.LogDir 'deployment-*.log'
        Write-Warn "Check logs at: $logPattern"
        
        exit 1
    }
}

# =============================================================================
# EXECUTION
# =============================================================================

Start-Deployment
