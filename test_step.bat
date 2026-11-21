@echo off
echo step1
git checkout -- games/.auto_update.pid >nul 2>&1
echo step2
git status --porcelain | findstr "." >nul
echo step3 errorlevel=%errorlevel%
if errorlevel 1 (
    echo No local changes.
) else (
    echo Local changes detected, committing...
    git add -A >nul 2>&1
    git commit -m "Auto-sync: local changes from %COMPUTERNAME% at %DATE% %TIME%" >nul 2>&1
    if errorlevel 1 (
        echo Warning: commit failed
    ) else (
        echo Local commit created.
    )
)
echo step4
