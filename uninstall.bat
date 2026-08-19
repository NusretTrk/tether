@echo off
REM Double-click this to stop tether and remove it from startup, with an
REM option to also delete your .env/config/logs.
powershell -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1"
pause
