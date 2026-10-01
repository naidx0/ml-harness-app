<#
ML Harness - one command to run the whole thing, from PowerShell.

    .\start.ps1                 engine + UI, reusing whatever is already correct
    .\start.ps1 --no-ui         engine only
    .\start.ps1 --status        say what is running, change nothing
    .\start.ps1 --rotate-token  new bearer token (open tabs will need a reload)

The bash twin is ./start.sh and this is deliberately the same twelve lines:
find a Python, hand over to scripts/launch.py. Nothing decides anything here.
Every rule about what to reuse, what to replace and what to refuse to touch
lives in scripts/launch.py, in one implementation that a test can drive.
#>

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

# A candidate is only accepted if it actually runs. `python3` on Windows is
# very often the App Execution Alias stub that opens the Microsoft Store: it is
# on PATH, Get-Command finds it, and it is not a Python.
function Test-Python([string]$exe) {
    if ([string]::IsNullOrWhiteSpace($exe)) { return $false }
    try {
        & $exe -c 'import sys' 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

$candidates = @(
    $env:MLH_PYTHON,
    (Join-Path $here '.venv\Scripts\python.exe'),
    (Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Source),
    (Get-Command py -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Source)
)

$python = $null
foreach ($candidate in $candidates) {
    if (Test-Python $candidate) { $python = $candidate; break }
}

if (-not $python) {
    Write-Host ''
    Write-Host 'ML HARNESS DID NOT START'
    Write-Host ''
    Write-Host 'No usable Python was found. Tried $env:MLH_PYTHON, .\.venv, python and py.'
    Write-Host ''
    Write-Host 'Install Python 3.11 or newer, then from this directory:'
    Write-Host ''
    Write-Host '    python -m pip install -e .'
    Write-Host '    .\start.ps1'
    Write-Host ''
    exit 127
}

& $python (Join-Path $here 'scripts\launch.py') @args
exit $LASTEXITCODE
