# Starts tether via the watchdog (watchdog.py launches run.py itself and
# keeps it running). Safe to run even if tether is already up - it checks
# first rather than spawning a duplicate.
#
#   powershell -ExecutionPolicy Bypass -File start_tether.ps1

$ErrorActionPreference = "Stop"

$projectDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$watchdogPy  = Join-Path $projectDir "watchdog.py"

if (-not (Test-Path $watchdogPy)) {
    Write-Error "Can't find watchdog.py next to this script (looked in $projectDir)."
}

$alreadyUp = Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -eq "python.exe" -or $_.Name -eq "pythonw.exe") -and
    ($_.CommandLine -like "*run.py*" -or $_.CommandLine -like "*watchdog.py*")
}
if ($alreadyUp) {
    Write-Host "tether is already running."
    exit 0
}

$pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $pythonw) {
    $python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if (-not $python) { Write-Error "Python isn't on PATH." }
    $pythonw = Join-Path (Split-Path -Parent $python) "pythonw.exe"
    if (-not (Test-Path $pythonw)) { Write-Error "Found python.exe but not pythonw.exe next to it." }
}

Start-Process -FilePath $pythonw -ArgumentList "`"$watchdogPy`"" -WorkingDirectory $projectDir -WindowStyle Hidden

Write-Host "tether starting (via watchdog, so it'll relaunch itself if it ever dies)."
