@echo off
rem DOTA_MASTER - Web Server launcher (port 9999)
rem ==================================================
rem Run by DOUBLE-CLICK or from cmd.exe (not PowerShell)
rem The server runs in THIS window. Only one console.
rem

setlocal enabledelayedexpansion
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

rem Force Python UTF-8
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "PYTHON=C:/Users/kivin/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe"

%PYTHON% --version >nul 2>nul || (echo Python not found. & pause & exit /b 1)
%PYTHON% -c "import flask" >nul 2>nul || (echo Flask not installed. & pause & exit /b 1)

rem Free port 9999 (only processes bound to this port)
echo Checking port 9999...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :9999') do (
    taskkill /F /PID %%a >nul 2>nul
)
timeout /t 1 /nobreak >nul

rem ==================================================
rem Synchronize with remote repository
rem ==================================================
echo Syncing with remote repository...
git fetch origin >nul 2>&1
git checkout -- games/.auto_update.pid >nul 2>&1
git pull --ff-only origin master 2>&1 | findstr /v /c:"Already up to date" /c:"Fast-forward" /c:"create mode" || echo Sync complete.
echo.

rem Run server in this window
chcp 65001 >nul
mode con: cols=120 lines=30 >nul

echo Starting DOTA_MASTER...
echo Port: 9999
"%PYTHON%" -u app.py

echo.
echo Server stopped. Press any key to exit.
pause >nul
