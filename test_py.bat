@echo off
setlocal enabledelayedexpansion
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"
set "PYTHON=C:/Users/kivin/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe"
%PYTHON% --version >nul 2>nul || (echo Python not found. & pause & exit /b 1)
%PYTHON% -c "import flask" >nul 2>nul || (echo Flask not installed. & pause & exit /b 1)
echo Python OK
ping -n 2 127.0.0.1 >nul
echo after ping
