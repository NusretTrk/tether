@echo off
REM Double-click this to make tether start automatically at login.
powershell -ExecutionPolicy Bypass -File "%~dp0install_autostart.ps1"
pause
