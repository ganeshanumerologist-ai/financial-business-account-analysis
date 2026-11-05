@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\remove_startup_shortcut.ps1"
echo.
pause
