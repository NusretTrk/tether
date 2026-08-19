# Uninstalls tether: stops the running process (and its watchdog), removes
# the autostart shortcut, and optionally clears your secrets/config/logs.
# Does NOT delete this project folder, your Python packages, or your
# BotFather bot - see uninstall_packages.ps1 for the packages, and revoke
# the bot yourself via @BotFather -> /revoke if you want the token dead.
#
#   powershell -ExecutionPolicy Bypass -File uninstall.ps1

$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "This will:"
Write-Host "  1. Stop tether and its watchdog, if running"
Write-Host "  2. Remove the Startup shortcut (autostart)"
Write-Host "  3. Optionally delete .env, config.yaml, logs, and state/"
Write-Host ""
$confirm = Read-Host "Continue? [y/N]"
if ($confirm -ne "y") { Write-Host "Cancelled."; exit 0 }

$procs = Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -eq "python.exe" -or $_.Name -eq "pythonw.exe") -and
    ($_.CommandLine -like "*run.py*" -or $_.CommandLine -like "*watchdog.py*")
}
foreach ($p in $procs) {
    Stop-Process -Id $p.ProcessId -Force
    Write-Host "Stopped $($p.Name) (PID $($p.ProcessId))"
}
if (-not $procs) { Write-Host "tether wasn't running." }

$startup      = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "tether.lnk"
if (Test-Path $shortcutPath) {
    Remove-Item $shortcutPath -Force
    Write-Host "Removed autostart shortcut."
} else {
    Write-Host "No autostart shortcut was installed."
}

Write-Host ""
$clearData = Read-Host "Also delete .env, config.yaml, tether.log, cmd_audit.log, and state/ - your bot token and settings? [y/N]"
if ($clearData -eq "y") {
    foreach ($f in @(".env", "config.yaml", "tether.log", "cmd_audit.log")) {
        $path = Join-Path $projectDir $f
        if (Test-Path $path) {
            Remove-Item $path -Force
            Write-Host "Deleted $f"
        }
    }
    $stateDir = Join-Path $projectDir "state"
    if (Test-Path $stateDir) {
        Remove-Item $stateDir -Recurse -Force
        Write-Host "Deleted state/"
    }
}

Write-Host ""
Write-Host "Done. tether is stopped and will not start at login again."
Write-Host "The project folder itself, your Python packages, and your"
Write-Host "BotFather bot are all untouched - see uninstall_packages.ps1"
Write-Host "for the packages, or delete this folder yourself for the rest."
