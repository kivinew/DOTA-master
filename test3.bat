@echo off
echo test1
git status --porcelain | findstr "." >nul
if errorlevel 1 (
    echo no changes
) else (
    echo has changes
    git add -A >nul 2>&1
    git commit -m "test" >nul 2>&1
    if errorlevel 1 (
        echo commit failed
    ) else (
        echo commit ok
    )
)
echo test2
