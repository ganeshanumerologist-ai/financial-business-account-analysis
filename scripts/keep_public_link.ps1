# Keep the ARTHIVIO demo reachable through a stable Firebase landing link.
#
# The app runs on this PC and is exposed through a Cloudflare quick tunnel.
# A quick tunnel gets a new hostname when it restarts, so this watchdog:
#   1. starts the local app if it is not healthy or is not Build 0.21,
#   2. starts cloudflared if it is not running,
#   3. reads the current public URL from the cloudflared log,
#   4. updates firebase-public/index.html and redeploys Firebase when the URL changed.
#
# The link to share is always https://financial-business-accounting.web.app
# It survives a tunnel restart because the landing page is updated automatically.

$ErrorActionPreference = 'SilentlyContinue'

$root = 'D:\financial business account data analysis'
$port = 8010
$healthUrl = "http://127.0.0.1:$port/health"
$python = Join-Path $root '.venv\Scripts\python.exe'
$cloudflared = Join-Path $env:TEMP 'opencode\cloudflared.exe'
$tunnelLog = Join-Path $env:TEMP 'opencode\cloudflared-public.log'
$watchLog = Join-Path $env:TEMP 'opencode\arthivio-public-watchdog.log'
$stateFile = Join-Path $env:TEMP 'opencode\arthivio-public-state.json'
$indexFile = Join-Path $root 'firebase-public\index.html'
$redirectFile = Join-Path $root 'firebase-public\app\index.html'
$nodeExe = 'C:\Users\vicky\AppData\Local\Temp\opencode\node-v24.22.2-win-x64\node.exe'
$firebaseCli = 'C:\Users\vicky\AppData\Local\Temp\opencode\firebase-tools-24\node_modules\firebase-tools\lib\bin\firebase.js'
$project = 'financial-business-accounting'
$version = 'ARTHIVIO/0.21'

function Write-WatchLog([string]$message) {
    $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $message
    Add-Content -Path $watchLog -Value $line -Encoding UTF8
}

function Test-LocalHealth {
    try {
        $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 8
        $server = [string]$response.Headers['Server']
        return ($response.StatusCode -eq 200 -and
                $response.Content.Trim() -eq 'ok' -and
                $server -like "$version*")
    } catch {
        return $false
    }
}

function Start-App {
    $env:ARTHIVIO_DB = Join-Path $root 'data\arthivio-trial.db'
    $env:ARTHIVIO_HOST = '127.0.0.1'
    $env:PORT = [string]$port
    Start-Process -FilePath $python -ArgumentList '-m', 'app.server' `
        -WorkingDirectory $root -WindowStyle Hidden
    Write-WatchLog 'started local app'
}

function Get-TunnelProcess {
    Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" |
        Where-Object { $_.CommandLine -like "*--url http://127.0.0.1:$port*" } |
        Select-Object -First 1
}

function Start-Tunnel {
    Start-Process -FilePath $cloudflared `
        -ArgumentList 'tunnel', '--url', "http://127.0.0.1:$port", '--no-autoupdate', '--logfile', $tunnelLog `
        -WindowStyle Hidden
    Write-WatchLog 'started cloudflared'
}

function Stop-Tunnel {
    $proc = Get-TunnelProcess
    if ($proc) {
        Stop-Process -Id $proc.ProcessId -Force
        Write-WatchLog "stopped cloudflared pid $($proc.ProcessId)"
        Start-Sleep -Seconds 2
    }
}

function Get-PublicUrl {
    if (-not (Test-Path $tunnelLog)) { return $null }
    $match = Get-Content $tunnelLog -Tail 800 |
        Select-String -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' |
        Select-Object -Last 1
    if ($match) { return $match.Matches[0].Value }
    return $null
}

function Test-PublicUrl([string]$url) {
    if (-not $url) { return $false }
    try {
        $response = Invoke-WebRequest -Uri "$url/health" -UseBasicParsing -TimeoutSec 15
        return ($response.StatusCode -eq 200 -and $response.Content.Trim() -eq 'ok')
    } catch {
        return $false
    }
}

function Get-State {
    if (Test-Path $stateFile) {
        try { return Get-Content $stateFile -Raw | ConvertFrom-Json } catch { }
    }
    return [pscustomobject]@{ url = ''; failures = 0 }
}

function Save-State([string]$url, [int]$failures) {
    [pscustomobject]@{ url = $url; failures = $failures } |
        ConvertTo-Json -Compress | Set-Content -Path $stateFile -Encoding UTF8
}

function Update-Firebase([string]$oldUrl, [string]$newUrl) {
    $files = @($indexFile, $redirectFile)
    $changed = $false
    foreach ($file in $files) {
        if (-not (Test-Path $file)) {
            Write-WatchLog "missing $file"
            continue
        }
        $content = Get-Content $file -Raw -Encoding UTF8
        $updated = [regex]::Replace($content, 'https://[a-z0-9-]+\.trycloudflare\.com', $newUrl)
        if ($updated -ne $content) {
            [System.IO.File]::WriteAllText($file, $updated, [System.Text.UTF8Encoding]::new($false))
            $changed = $true
        }
    }
    if (-not $changed) {
        Write-WatchLog 'public files already contain the current URL'
        return
    }

    $env:PATH = (Split-Path $nodeExe) + ';' + $env:PATH
    Push-Location $root
    $output = & $nodeExe $firebaseCli deploy --only hosting --project $project --non-interactive 2>&1
    $code = $LASTEXITCODE
    Pop-Location
    $output | Add-Content -Path $watchLog -Encoding UTF8
    if ($code -eq 0) {
        Write-WatchLog "Firebase updated: $oldUrl -> $newUrl"
    } else {
        Write-WatchLog "Firebase deploy failed with exit code $code"
    }
}

# 1. Local app
if (-not (Test-LocalHealth)) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        if ($proc -and $proc.CommandLine -like '*app.server*') {
            Stop-Process -Id $proc.ProcessId -Force
            Write-WatchLog "stopped unhealthy app pid $($proc.ProcessId)"
            Start-Sleep -Seconds 2
        }
    }
    Start-App
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 1
        if (Test-LocalHealth) { break }
    }
    if (-not (Test-LocalHealth)) {
        Write-WatchLog 'app did not become healthy; will retry on next run'
        exit 1
    }
    Write-WatchLog 'local app is healthy'
}

# 2. Tunnel process
$tunnel = Get-TunnelProcess
if ($tunnel) {
    $logMatch = [regex]::Match($tunnel.CommandLine, '--logfile\s+"?([^"]+)"?')
    if ($logMatch.Success) { $tunnelLog = $logMatch.Groups[1].Value.Trim() }
}
if (-not $tunnel) {
    Start-Tunnel
    Start-Sleep -Seconds 8
    $tunnel = Get-TunnelProcess
}
if (-not $tunnel) {
    Write-WatchLog 'cloudflared is not running; will retry on next run'
    exit 1
}

# 3. Public URL
$url = $null
for ($i = 0; $i -lt 10; $i++) {
    $url = Get-PublicUrl
    if ($url -and (Test-PublicUrl $url)) { break }
    $url = $null
    Start-Sleep -Seconds 3
}

$state = Get-State
if (-not $url) {
    $failures = [int]$state.failures + 1
    Save-State '' $failures
    Write-WatchLog "public URL is not reachable (failure $failures)"
    if ($failures -ge 2) {
        Stop-Tunnel
        Start-Tunnel
        Start-Sleep -Seconds 10
        $url = Get-PublicUrl
        if ($url -and (Test-PublicUrl $url)) {
            Save-State $url 0
            Write-WatchLog "new tunnel is reachable: $url"
        } else {
            Write-WatchLog 'new tunnel did not become reachable; will retry on next run'
            exit 1
        }
    } else {
        exit 1
    }
} else {
    Save-State $url 0
}

# 4. Landing page
$content = Get-Content $indexFile -Raw -Encoding UTF8
$current = ([regex]::Matches($content, 'https://[a-z0-9-]+\.trycloudflare\.com') |
    Select-Object -First 1).Value
if (-not $current) {
    Write-WatchLog 'landing page has no tunnel URL to replace'
    exit 1
}
$redirectContent = Get-Content $redirectFile -Raw -Encoding UTF8
$redirectCurrent = ([regex]::Matches($redirectContent, 'https://[a-z0-9-]+\.trycloudflare\.com') |
    Select-Object -First 1).Value
if ($current -ne $url -or $redirectCurrent -ne $url) {
    Update-Firebase $current $url
} else {
    Write-WatchLog "public URL unchanged: $url"
}
