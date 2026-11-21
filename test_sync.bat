@echo off
echo ==================================================
echo Synchronizing repository...
echo ==================================================
git checkout -- games/.auto_update.pid >nul 2>&1
git status --porcelain | findstr "." >nul
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
echo Fetching remote...
git fetch origin >nul 2>&1
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
git rev-list origin/master..HEAD --count | findstr /r "^[1-9]" >nul
if errorlevel 1 (
    echo No local commits to push.
) else (
    echo Pushing local commits to remote...
    git push origin master >nul 2>&1
    if errorlevel 1 (
        echo Warning: push failed
    ) else (
        echo Push complete.
    )
)
echo ==================================================
echo Sync complete.
echo ==================================================
