@echo off
git status --porcelain | findstr "." >nul
if errorlevel 1 (
    echo no changes
) else (
    echo has changes
)
