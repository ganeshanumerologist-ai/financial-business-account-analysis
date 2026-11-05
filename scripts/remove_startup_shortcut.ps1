# Remove the ARTHIVIO desktop and login-startup shortcuts.
$ErrorActionPreference = "Stop"

$desktop = [Environment]::GetFolderPath("Desktop")
$startup = [Environment]::GetFolderPath("Startup")
foreach ($path in @(
    (Join-Path $desktop "ARTHIVIO.lnk"),
    (Join-Path $startup "ARTHIVIO.lnk")
)) {
    if (Test-Path $path) {
        Remove-Item $path -Force
        Write-Host "Removed $path"
    } else {
        Write-Host "Not present: $path"
    }
}
