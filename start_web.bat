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
rem Wait 1 second (ping is more reliable than timeout in mixed environments)
ping -n 2 127.0.0.1 >nul

rem ==================================================
rem Full repository synchronization (two-way)
rem ==================================================
echo ==================================================
echo Synchronizing repository...
echo ==================================================

rem 1. Reset runtime files that should not be committed
git checkout -- games/.auto_update.pid >nul 2>&1

rem 2. Check for local changes (staged + unstaged + untracked)
git status --porcelain | findstr "." >nul
if errorlevel 1 (
    echo No local changes.
) else (
    echo Local changes detected, committing...
    git add -A >nul 2>&1
    git commit -m "Auto-sync: local changes from %COMPUTERNAME% at %DATE% %TIME%" >nul 2>&1
    if errorlevel 1 (
        echo Warning: commit failed (maybe nothing to commit)
    ) else (
        echo Local commit created.
    )
)

rem 3. Fetch remote
echo Fetching remote...
git fetch origin >nul 2>&1

rem 4. Check if remote has new commits (count > 0)
git rev-list HEAD..origin/master --count | findstr /r "^[1-9]" >nul
if errorlevel 1 (
    echo Local is up to date with remote.
) else (
    echo Remote has new commits, pulling...
    git pull --ff-only origin master >nul 2>&1
    if errorlevel 1 (
        echo Warning: pull failed
    ) else (
        echo Pull complete.
    )
)

rem 5. Push local commits if any (count > 0)
git rev-list origin/master..HEAD --count | findstr /r "^[1-9]" >nul
if errorlevel 1 (
    echo No local commits to push.
) else (
    echo Pushing local commits to remote...
    git push origin master >nul 2>&1
    if errorlevel 1 (
        echo Warning: push failed (maybe authentication needed)
    ) else (
        echo Push complete.
    )
)

echo ==================================================
echo Sync complete.
echo ==================================================
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
