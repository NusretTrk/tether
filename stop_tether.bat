@echo off
REM Double-click this to stop tether (and its watchdog, so it stays stopped).
powershell -ExecutionPolicy Bypass -File "%~dp0stop_tether.ps1"
pause
