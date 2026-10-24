#Requires -Version 5.1
<#
  ARTHIVIO local dev runner (no external dependencies).
  Usage:
    .\dev.ps1            # seed if needed, run tests, start server on :8000
    .\dev.ps1 -Port 8010
    .\dev.ps1 -SeedOnly
#>
param(
    [int]$Port = 8000,
    [switch]$SeedOnly,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

if (-not $SkipTests) {
    Write-Host "Running test suite..." -ForegroundColor Cyan
    & $python -m unittest discover -s tests -q
    if ($LASTEXITCODE -ne 0) { throw "Tests failed - not starting the server." }
}

Write-Host "Seeding demo data (idempotent)..." -ForegroundColor Cyan
& $python scripts\seed_demo.py
if ($LASTEXITCODE -ne 0) { throw "Seeding failed." }

if ($SeedOnly) { return }

$env:PORT = "$Port"
Write-Host "Starting ARTHIVIO on http://127.0.0.1:$Port" -ForegroundColor Green
& $python -m app.server
