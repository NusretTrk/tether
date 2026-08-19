@echo off
REM Double-click this to start tether if it isn't already running.
powershell -ExecutionPolicy Bypass -File "%~dp0start_tether.ps1"
pause
