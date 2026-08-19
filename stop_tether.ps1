# Stops tether - and the watchdog, so it actually stays stopped instead
# of being relaunched on the watchdog's next check.
#
#   powershell -ExecutionPolicy Bypass -File stop_tether.ps1

$ErrorActionPreference = "Stop"

$procs = Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -eq "python.exe" -or $_.Name -eq "pythonw.exe") -and
    ($_.CommandLine -like "*run.py*" -or $_.CommandLine -like "*watchdog.py*")
}

if (-not $procs) {
    Write-Host "tether isn't running."
    exit 0
}

foreach ($p in $procs) {
    Stop-Process -Id $p.ProcessId -Force
    Write-Host "Stopped $($p.Name) (PID $($p.ProcessId))"
}

Write-Host "tether stopped. It will not come back on its own - run start_tether.ps1"
Write-Host "(or log out/in, if autostart is installed) to bring it back."
