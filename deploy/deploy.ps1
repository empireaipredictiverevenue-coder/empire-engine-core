# ═══════════════════════════════════════════════════════════════════════════
# EMPIRE V49 · MASTER DEPLOYMENT SCRIPT
# ═══════════════════════════════════════════════════════════════════════════
# Run from Windows PowerShell to deploy Empire AI to a Hetzner server.
#
# Prerequisites:
#   1. Hetzner box provisioned (CCX13 Ubuntu 24.04 minimum, root access)
#   2. Domain DNS pointing to the Hetzner IP (A record for empire-ai.co.uk)
#   3. Your Anthropic, Supabase, Vonage, Resend, OpenAI API keys ready
#   4. Git installed locally · OpenSSH client enabled
#   5. This script in your Empire repo root
#
# Usage:
#   .\deploy.ps1 -ServerIP "1.2.3.4" -Domain "empire-ai.co.uk" -Email "you@your.email"
#
# Or interactive mode (will prompt):
#   .\deploy.ps1
# ═══════════════════════════════════════════════════════════════════════════

param(
    [string]$ServerIP    = "",
    [string]$Domain      = "",
    [string]$Email       = "",
    [string]$AppName     = "empire-ai-uk",
    [string]$SshKeyPath  = "$env:USERPROFILE\.ssh\id_ed25519",
    [switch]$SkipBootstrap,
    [switch]$SkipSchema,
    [switch]$EnvOnly,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# ─────────────────────────────────────────────────────────────────────
# COLOR HELPERS
# ─────────────────────────────────────────────────────────────────────
function Write-Step    { param($msg) Write-Host "`n▸ $msg" -ForegroundColor Cyan }
function Write-Success { param($msg) Write-Host "  ✓ $msg" -ForegroundColor Green }
function Write-Warn    { param($msg) Write-Host "  ⚠ $msg" -ForegroundColor Yellow }
function Write-Err     { param($msg) Write-Host "  ✗ $msg" -ForegroundColor Red }
function Write-Info    { param($msg) Write-Host "    $msg" -ForegroundColor DarkGray }
function Write-Banner {
    param($msg)
    Write-Host ""
    Write-Host "═══════════════════════════════════════════════════════════════════════" -ForegroundColor DarkCyan
    Write-Host "  $msg" -ForegroundColor White
    Write-Host "═══════════════════════════════════════════════════════════════════════" -ForegroundColor DarkCyan
}

# ─────────────────────────────────────────────────────────────────────
# PROMPT FOR MISSING PARAMS
# ─────────────────────────────────────────────────────────────────────
Write-Banner "EMPIRE AI · V49 DEPLOYMENT"

if (-not $ServerIP) {
    $ServerIP = Read-Host "Hetzner server IP"
}
if (-not $Domain) {
    $Domain = Read-Host "Primary domain (e.g. empire-ai.co.uk)"
}
if (-not $Email) {
    $Email = Read-Host "Your email (for Let's Encrypt SSL)"
}

Write-Host ""
Write-Info "Server IP   : $ServerIP"
Write-Info "Domain      : $Domain"
Write-Info "Email       : $Email"
Write-Info "App name    : $AppName"
Write-Info "SSH key     : $SshKeyPath"
if ($DryRun) { Write-Warn "DRY-RUN MODE · no changes will be made" }
Write-Host ""

$confirm = Read-Host "Proceed? (y/N)"
if ($confirm -ne "y") {
    Write-Err "Aborted by user"
    exit 1
}

# ─────────────────────────────────────────────────────────────────────
# STEP 1 · LOCAL PREREQUISITES CHECK
# ─────────────────────────────────────────────────────────────────────
Write-Step "Checking local prerequisites..."

# Check git
try {
    $null = git --version
    Write-Success "git installed"
} catch {
    Write-Err "git is not installed or not in PATH"
    Write-Info "Install from https://git-scm.com/download/win"
    exit 1
}

# Check OpenSSH client
try {
    $null = Get-Command ssh -ErrorAction Stop
    Write-Success "OpenSSH client available"
} catch {
    Write-Err "OpenSSH client not available"
    Write-Info "Enable: Settings > Apps > Optional Features > OpenSSH Client"
    exit 1
}

# Check we're in a git repo with the empire modules
if (-not (Test-Path "hub.py")) {
    Write-Warn "hub.py not found in current directory."
    Write-Info "Make sure you're running this from the Empire repo root."
    $confirm = Read-Host "Continue anyway? (y/N)"
    if ($confirm -ne "y") { exit 1 }
}

# Check for SSH key, generate if missing
if (-not (Test-Path $SshKeyPath)) {
    Write-Warn "SSH key not found at $SshKeyPath"
    Write-Info "Generating ed25519 keypair..."
    if (-not $DryRun) {
        $sshDir = Split-Path $SshKeyPath
        if (-not (Test-Path $sshDir)) {
            New-Item -ItemType Directory -Path $sshDir -Force | Out-Null
        }
        ssh-keygen -t ed25519 -f $SshKeyPath -N '""' -C "empire-deploy@$env:USERNAME" 2>&1 | Out-Null
        Write-Success "Keypair generated at $SshKeyPath"
        Write-Warn "PUBLIC KEY (copy this to your Hetzner box via Hetzner cloud console first if not already):"
        Get-Content "$SshKeyPath.pub"
        Write-Host ""
        Read-Host "Press Enter once the public key is on the Hetzner box"
    }
} else {
    Write-Success "SSH key found"
}

# ─────────────────────────────────────────────────────────────────────
# STEP 2 · TEST SSH CONNECTION
# ─────────────────────────────────────────────────────────────────────
Write-Step "Testing SSH to $ServerIP..."

if (-not $DryRun) {
    $sshTest = ssh -i $SshKeyPath -o StrictHostKeyChecking=no -o ConnectTimeout=10 root@$ServerIP "echo OK" 2>&1
    if ($LASTEXITCODE -ne 0 -or $sshTest -notlike "*OK*") {
        Write-Err "SSH connection failed"
        Write-Info "Make sure your public key ($SshKeyPath.pub) is in /root/.ssh/authorized_keys on the server"
        Write-Info "On Hetzner cloud console, you can paste the key during server creation."
        exit 1
    }
    Write-Success "SSH OK"
}

# ─────────────────────────────────────────────────────────────────────
# STEP 3 · BOOTSTRAP DOKKU (server-side)
# ─────────────────────────────────────────────────────────────────────
if (-not $SkipBootstrap -and -not $EnvOnly) {
    Write-Step "Bootstrapping Dokku on the server (this takes ~5 minutes)..."

    if (Test-Path "deploy\hetzner-bootstrap.sh") {
        if (-not $DryRun) {
            Write-Info "Uploading bootstrap script..."
            scp -i $SshKeyPath -o StrictHostKeyChecking=no `
                "deploy\hetzner-bootstrap.sh" `
                "root@${ServerIP}:/root/hetzner-bootstrap.sh" 2>&1 | Out-Null

            Write-Info "Running bootstrap (verbose output below)..."
            ssh -i $SshKeyPath -o StrictHostKeyChecking=no root@$ServerIP `
                "chmod +x /root/hetzner-bootstrap.sh && /root/hetzner-bootstrap.sh"

            if ($LASTEXITCODE -ne 0) {
                Write-Err "Bootstrap failed"
                exit 1
            }
            Write-Success "Dokku bootstrap complete"
        }
    } else {
        Write-Warn "deploy\hetzner-bootstrap.sh not found · skipping"
    }
} else {
    Write-Info "Skipping bootstrap (--SkipBootstrap or --EnvOnly)"
}

# ─────────────────────────────────────────────────────────────────────
# STEP 4 · CREATE THE DOKKU APP
# ─────────────────────────────────────────────────────────────────────
if (-not $EnvOnly) {
    Write-Step "Creating Dokku app · $AppName..."

    if (Test-Path "deploy\empire-app-setup.sh") {
        if (-not $DryRun) {
            scp -i $SshKeyPath -o StrictHostKeyChecking=no `
                "deploy\empire-app-setup.sh" `
                "root@${ServerIP}:/root/empire-app-setup.sh" 2>&1 | Out-Null

            ssh -i $SshKeyPath -o StrictHostKeyChecking=no root@$ServerIP `
                "chmod +x /root/empire-app-setup.sh && APP_NAME='$AppName' DOMAIN='$Domain' LETSENCRYPT_EMAIL='$Email' /root/empire-app-setup.sh"

            if ($LASTEXITCODE -ne 0) {
                Write-Err "App setup failed"
                exit 1
            }
            Write-Success "App created and configured"
        }
    } else {
        Write-Warn "deploy\empire-app-setup.sh not found · skipping"
    }
}

# ─────────────────────────────────────────────────────────────────────
# STEP 5 · CONFIGURE ENVIRONMENT VARIABLES
# ─────────────────────────────────────────────────────────────────────
Write-Step "Configuring environment variables..."

if (-not (Test-Path ".env")) {
    Write-Err ".env file not found in current directory"
    Write-Info "Copy .env.example to .env and fill in your real values first."
    exit 1
}

Write-Info "Reading .env..."
$envVars = @{}
Get-Content ".env" | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $idx = $line.IndexOf("=")
        $k = $line.Substring(0, $idx).Trim()
        $v = $line.Substring($idx + 1).Trim()
        # Strip surrounding quotes if present
        if ($v.StartsWith('"') -and $v.EndsWith('"')) {
            $v = $v.Substring(1, $v.Length - 2)
        }
        $envVars[$k] = $v
    }
}

Write-Info "Found $($envVars.Count) variables · uploading to Dokku..."

if (-not $DryRun) {
    # Build a single config:set command for atomic update
    $configArgs = @()
    foreach ($k in $envVars.Keys) {
        $v = $envVars[$k] -replace '"', '\"'
        $configArgs += "${k}=`"${v}`""
    }
    $configCmd = "dokku config:set --no-restart $AppName " + ($configArgs -join " ")

    # Write the command to a tempfile because it can get long
    $tmpScript = [System.IO.Path]::GetTempFileName()
    "#!/bin/bash`nset -e`n$configCmd" | Out-File -FilePath $tmpScript -Encoding ascii

    scp -i $SshKeyPath -o StrictHostKeyChecking=no `
        $tmpScript `
        "root@${ServerIP}:/tmp/empire-config.sh" 2>&1 | Out-Null

    ssh -i $SshKeyPath -o StrictHostKeyChecking=no root@$ServerIP `
        "chmod +x /tmp/empire-config.sh && /tmp/empire-config.sh && rm /tmp/empire-config.sh" | Out-Null

    if ($LASTEXITCODE -ne 0) {
        Write-Err "Config upload failed"
        exit 1
    }
    Write-Success "$($envVars.Count) environment variables set"

    Remove-Item $tmpScript
}

if ($EnvOnly) {
    Write-Success "Env-only mode · skipping git push and SSL"
    Write-Banner "ENV UPDATE COMPLETE"
    exit 0
}

# ─────────────────────────────────────────────────────────────────────
# STEP 6 · UPLOAD VONAGE PRIVATE KEY (if it exists locally)
# ─────────────────────────────────────────────────────────────────────
if (Test-Path "vonage_private.key") {
    Write-Step "Uploading Vonage private key..."
    if (-not $DryRun) {
        $storageDir = "/var/lib/dokku/data/storage/$AppName"
        ssh -i $SshKeyPath -o StrictHostKeyChecking=no root@$ServerIP `
            "mkdir -p $storageDir" | Out-Null

        scp -i $SshKeyPath -o StrictHostKeyChecking=no `
            "vonage_private.key" `
            "root@${ServerIP}:${storageDir}/vonage_private.key" 2>&1 | Out-Null

        ssh -i $SshKeyPath -o StrictHostKeyChecking=no root@$ServerIP `
            "chmod 600 ${storageDir}/vonage_private.key" | Out-Null

        # Mount it into the app
        ssh -i $SshKeyPath -o StrictHostKeyChecking=no root@$ServerIP `
            "dokku storage:mount $AppName ${storageDir}/vonage_private.key:/app/vonage_private.key 2>/dev/null || true" | Out-Null

        ssh -i $SshKeyPath -o StrictHostKeyChecking=no root@$ServerIP `
            "dokku config:set --no-restart $AppName VONAGE_PRIVATE_KEY_PATH=/app/vonage_private.key" | Out-Null

        Write-Success "Vonage private key mounted at /app/vonage_private.key"
    }
} else {
    Write-Info "(No vonage_private.key found locally · skip)"
}

# ─────────────────────────────────────────────────────────────────────
# STEP 7 · ADD DOKKU GIT REMOTE
# ─────────────────────────────────────────────────────────────────────
Write-Step "Wiring git remote..."

$remoteUrl = "dokku@${ServerIP}:${AppName}"

if (-not $DryRun) {
    $existingRemotes = git remote 2>&1
    if ($existingRemotes -contains "dokku") {
        $currentDokkuUrl = git remote get-url dokku 2>&1
        if ($currentDokkuUrl -ne $remoteUrl) {
            git remote set-url dokku $remoteUrl
            Write-Success "Updated dokku remote → $remoteUrl"
        } else {
            Write-Success "dokku remote already set"
        }
    } else {
        git remote add dokku $remoteUrl
        Write-Success "Added dokku remote → $remoteUrl"
    }

    # Make sure SSH knows to use our key for dokku@server
    $sshConfig = "$env:USERPROFILE\.ssh\config"
    $hostBlock = "Host ${ServerIP}`n    User dokku`n    IdentityFile $SshKeyPath`n    StrictHostKeyChecking no"
    if (Test-Path $sshConfig) {
        $existing = Get-Content $sshConfig -Raw
        if (-not $existing.Contains("Host $ServerIP")) {
            Add-Content $sshConfig "`n$hostBlock`n"
            Write-Success "Updated ~/.ssh/config"
        }
    } else {
        $hostBlock | Out-File -FilePath $sshConfig -Encoding ascii
        Write-Success "Created ~/.ssh/config"
    }
}

# ─────────────────────────────────────────────────────────────────────
# STEP 8 · PUSH THE CODE
# ─────────────────────────────────────────────────────────────────────
Write-Step "Pushing code to Dokku (this takes 2-5 min on first push)..."

if (-not $DryRun) {
    # Determine current branch
    $branch = git rev-parse --abbrev-ref HEAD 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Could not determine current branch"
        exit 1
    }
    Write-Info "Pushing branch '$branch' → dokku/main"

    git push dokku "${branch}:main"

    if ($LASTEXITCODE -ne 0) {
        Write-Err "Git push failed"
        Write-Info "Check the deploy log: ssh root@$ServerIP 'dokku logs $AppName -t'"
        exit 1
    }
    Write-Success "Code deployed"
}

# ─────────────────────────────────────────────────────────────────────
# STEP 9 · ENABLE SSL (LET'S ENCRYPT)
# ─────────────────────────────────────────────────────────────────────
Write-Step "Enabling Let's Encrypt SSL..."

if (-not $DryRun) {
    ssh -i $SshKeyPath -o StrictHostKeyChecking=no root@$ServerIP `
        "dokku letsencrypt:enable $AppName 2>&1 || echo SSL_ALREADY_ENABLED"

    if ($LASTEXITCODE -eq 0) {
        Write-Success "SSL enabled · https://$Domain"
    } else {
        Write-Warn "SSL enable returned non-zero · may already be enabled"
    }
}

# ─────────────────────────────────────────────────────────────────────
# STEP 10 · POST-DEPLOY VERIFICATION
# ─────────────────────────────────────────────────────────────────────
Write-Step "Running post-deploy checks..."

if (-not $DryRun) {
    Start-Sleep -Seconds 5  # let the app finish starting

    try {
        $health = Invoke-WebRequest -Uri "https://$Domain/api/market-pulse" -TimeoutSec 15 -UseBasicParsing
        if ($health.StatusCode -eq 200 -or $health.StatusCode -eq 401) {
            Write-Success "App responding at https://$Domain"
        } else {
            Write-Warn "App returned HTTP $($health.StatusCode)"
        }
    } catch {
        Write-Warn "Could not reach https://$Domain yet · check logs"
    }
}

# ─────────────────────────────────────────────────────────────────────
# DONE
# ─────────────────────────────────────────────────────────────────────
Write-Banner "DEPLOY COMPLETE"
Write-Host ""
Write-Host "  🌐 URL:        https://$Domain" -ForegroundColor White
Write-Host "  📊 Logs:       ssh root@$ServerIP 'dokku logs $AppName -t'" -ForegroundColor DarkGray
Write-Host "  ⚙ Config:      ssh root@$ServerIP 'dokku config $AppName'" -ForegroundColor DarkGray
Write-Host "  🔐 Login:      https://$Domain/auth/login" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Yellow
Write-Host "    1. Visit https://$Domain · cinematic splash should load" -ForegroundColor DarkGray
Write-Host "    2. Run schema.sql in your Supabase SQL editor (if not done)" -ForegroundColor DarkGray
Write-Host "    3. Bootstrap your owner account: INSERT into operators table" -ForegroundColor DarkGray
Write-Host "    4. Sign in at https://$Domain/auth/login" -ForegroundColor DarkGray
Write-Host "    5. Configure Vonage webhooks (see DEPLOY.md)" -ForegroundColor DarkGray
Write-Host ""
