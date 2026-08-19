@echo off
REM Double-click this to remove tether's pip dependencies, one at a time
REM with a confirmation each - it cannot tell which you already had
REM installed for another project, so read each prompt.
powershell -ExecutionPolicy Bypass -File "%~dp0uninstall_packages.ps1"
pause
