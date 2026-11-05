# Create desktop and login-startup shortcuts for the portable ARTHIVIO package.
# Run from "Install autostart.bat" or:
#   powershell -ExecutionPolicy Bypass -File scripts\install_startup_shortcut.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$startBat = Join-Path $root "Start ARTHIVIO.bat"
if (-not (Test-Path $startBat)) {
    throw "Start ARTHIVIO.bat was not found next to this package."
}

$shell = New-Object -ComObject WScript.Shell

$desktop = [Environment]::GetFolderPath("Desktop")
$desktopLink = Join-Path $desktop "ARTHIVIO.lnk"
$sc = $shell.CreateShortcut($desktopLink)
$sc.TargetPath = $startBat
$sc.WorkingDirectory = $root
$sc.WindowStyle = 1
$sc.Description = "Start ARTHIVIO offline accounting"
$sc.Save()

$startup = [Environment]::GetFolderPath("Startup")
$startupLink = Join-Path $startup "ARTHIVIO.lnk"
$sc = $shell.CreateShortcut($startupLink)
$sc.TargetPath = $startBat
$sc.Arguments = "--no-browser"
$sc.WorkingDirectory = $root
$sc.WindowStyle = 7
$sc.Description = "Start ARTHIVIO at login (minimized, no browser)"
$sc.Save()

Write-Host "Created:"
Write-Host "  $desktopLink"
Write-Host "  $startupLink"
Write-Host ""
Write-Host "ARTHIVIO will start minimized at your next Windows login."
Write-Host "Use the desktop shortcut to open it, or browse to http://127.0.0.1:8000/"
