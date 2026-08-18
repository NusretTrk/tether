@echo off
REM Builds dist\tether.exe - a standalone background executable.
REM Optional: pythonw.exe already runs tether without a console window.
REM Only worth doing if you need to run on a machine without Python.

where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo PyInstaller is not installed. Run:
    echo     pip install pyinstaller
    pause
    exit /b 1
)

pyinstaller ^
    --onefile ^
    --noconsole ^
    --name tether ^
    --paths src ^
    --hidden-import uiautomation ^
    --hidden-import comtypes ^
    --hidden-import win32timezone ^
    --collect-all telegram ^
    run.py

echo.
echo Built dist\tether.exe
echo Keep .env and config.yaml in the same folder as the exe.
pause
