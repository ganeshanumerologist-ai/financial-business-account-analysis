@echo off
setlocal
cd /d "%~dp0"
title ARTHIVIO - backup to external drive
echo ARTHIVIO backup
echo.
echo Enter the backup folder on your external drive.
echo Example: E:\ARTHIVIO-Backups
echo.
set /p DEST=Folder: 
if "%DEST%"=="" (
  echo No folder entered. Nothing was copied.
  pause
  exit /b 1
)
runtime\python.exe scripts\backup_to_drive.py --dest "%DEST%"
echo.
pause
