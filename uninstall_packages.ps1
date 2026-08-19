# Removes tether's pip dependencies (from requirements.txt), separately
# from uninstall.ps1 - these packages might be shared with other projects,
# so this is opt-in and per-package, not part of the main uninstall.
#
# There's no reliable way to know which of these were already on your
# machine before tether, installed for something else - a Python
# environment doesn't record "who asked for this" once it's in there. This
# just lists what tether depends on and asks before removing each one, so
# say no to anything you actually use elsewhere.
#
#   powershell -ExecutionPolicy Bypass -File uninstall_packages.ps1

$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$reqFile    = Join-Path $projectDir "requirements.txt"

if (-not (Test-Path $reqFile)) {
    Write-Error "requirements.txt not found next to this script (looked in $projectDir)."
}

$packages = Get-Content $reqFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq "" -or $line.StartsWith("#")) { return }
    # Strip version pins (==, >=, etc) and environment markers (; sys_platform == "win32")
    ($line -split "[=<>!;]")[0].Trim()
} | Where-Object { $_ } | Select-Object -Unique

Write-Host "tether depends on these packages:"
$packages | ForEach-Object { Write-Host "  - $_" }
Write-Host ""
Write-Host "This can't tell which of these you already had installed for"
Write-Host "something else before tether - answer 'n' for any of those."
Write-Host ""

$removed = @()
foreach ($pkg in $packages) {
    $installed = pip show $pkg 2>$null
    if (-not $installed) {
        Write-Host "$pkg - not currently installed, skipping"
        continue
    }
    $answer = Read-Host "Remove $pkg? [y/N]"
    if ($answer -eq "y") {
        pip uninstall -y $pkg
        $removed += $pkg
    }
}

Write-Host ""
if ($removed) {
    Write-Host "Removed: $($removed -join ', ')"
} else {
    Write-Host "Nothing removed."
}
