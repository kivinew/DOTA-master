@echo off
setlocal enabledelayedexpansion
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"
echo test1
ping -n 2 127.0.0.1 >nul
echo test2
