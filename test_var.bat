@echo off
echo test1
git commit -m "Auto-sync: local changes from %COMPUTERNAME% at %DATE% %TIME%" >nul 2>&1
echo test2
