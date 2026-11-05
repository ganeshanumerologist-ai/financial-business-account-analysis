@echo off
setlocal
cd /d "%~dp0"
if not exist "data" mkdir "data"
if not exist "backups" mkdir "backups"
if not exist "logs" mkdir "logs"
title ARTHIVIO - single user
echo Starting ARTHIVIO...
echo.
runtime\python.exe scripts\run_offline.py %*
if errorlevel 1 (
  echo.
  echo ARTHIVIO stopped with an error. The message above and logs\arthivio.log
  echo contain the details. Press any key to close.
  pause >nul
)
