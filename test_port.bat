@echo off
setlocal enabledelayedexpansion
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"
set "PYTHON=C:/Users/kivin/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe"
%PYTHON% --version >nul 2>nul || (echo Python not found. & pause & exit /b 1)
echo Checking port 9999...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :9999') do (
    taskkill /F /PID %%a >nul 2>nul
)
echo after port check
ping -n 2 127.0.0.1 >nul
echo after ping
