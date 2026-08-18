# Adds tether to Windows startup for the current user.
# No administrator rights needed - this writes a shortcut into your own
# Startup folder rather than registering a scheduled task (which requires
# elevation on most machines).
#
#   Install:    powershell -ExecutionPolicy Bypass -File install_autostart.ps1
#   Uninstall:  powershell -ExecutionPolicy Bypass -File install_autostart.ps1 -Remove

param([switch]$Remove)

$ErrorActionPreference = "Stop"

$startup      = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "tether.lnk"
$projectDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$runScript    = Join-Path $projectDir "run.py"

if ($Remove) {
    if (Test-Path $shortcutPath) {
        Remove-Item $shortcutPath -Force
        Write-Host "Removed tether from startup."
    } else {
        Write-Host "tether was not in startup - nothing to remove."
    }
    exit 0
}

if (-not (Test-Path $runScript)) {
    Write-Error "Can't find run.py next to this script (looked in $projectDir)."
}

# pythonw.exe runs without opening a console window.
$pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $pythonw) {
    $python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if (-not $python) { Write-Error "Python isn't on PATH. Install it, or edit this script with a full path." }
    $pythonw = Join-Path (Split-Path -Parent $python) "pythonw.exe"
    if (-not (Test-Path $pythonw)) { Write-Error "Found python.exe but not pythonw.exe next to it." }
}

$shell    = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath       = $pythonw
$shortcut.Arguments        = "`"$runScript`""
$shortcut.WorkingDirectory = $projectDir
$shortcut.Description      = "tether - Telegram remote control"
$shortcut.Save()

Write-Host "Installed. tether will start automatically when you log in."
Write-Host "Shortcut: $shortcutPath"
Write-Host ""
Write-Host "To start it right now without rebooting:"
Write-Host "  python run.py"
