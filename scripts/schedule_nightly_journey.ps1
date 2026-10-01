<#
.SYNOPSIS
    Register (or remove) the 03:30 nightly journey as a Windows scheduled task.

.DESCRIPTION
    `scripts/nightly_journey.py` drives one live journey and writes one score
    row. This registers it to run at 03:30 every day from THIS checkout, with
    THIS checkout's interpreter, appending its output to
    `docs/score_rows/nightly.log`.

    NOTHING IN THIS REPOSITORY RUNS THIS FILE. A scheduled task that appeared
    as a side effect of a checkout - or of a test run, or of an agent doing
    something else - would be a scheduled task nobody chose, on a machine whose
    owner did not know it was there. Registering is one command, typed once, by
    a person. `docs/score_rows/README.md` is where that command is written down.

    The task runs as the logged-on user and only while that user is logged on.
    That is deliberate rather than a limitation worked around: the journey
    drives a live model on the local card, and a task running in session 0 with
    no desktop would be measuring a machine nobody is using.

.PARAMETER Remove
    Unregister the task instead of registering it. Silent when it is not there.

.PARAMETER TaskName
    The name in Task Scheduler. Default: "ML Harness nightly journey".

.PARAMETER Time
    When it runs, as HH:mm. Default: 03:30.

.PARAMETER Python
    The interpreter. Default: this checkout's `.venv` python when there is one,
    otherwise whatever `python` resolves to on PATH.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/schedule_nightly_journey.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/schedule_nightly_journey.ps1 -Remove
#>

[CmdletBinding()]
param(
    [switch]$Remove,
    [string]$TaskName = 'ML Harness nightly journey',
    [string]$Time = '03:30',
    [string]$Python = ''
)

$ErrorActionPreference = 'Stop'

# THE CHECKOUT THIS FILE IS IN, not the current directory. A task registered
# with a relative path is a task that runs wherever Task Scheduler happens to
# start it, which is `C:\Windows\System32`.
$scriptRoot = $PSScriptRoot
$repo = Split-Path -Parent $scriptRoot
$journey = Join-Path $scriptRoot 'nightly_journey.py'
$rows = Join-Path (Join-Path $repo 'docs') 'score_rows'
$log = Join-Path $rows 'nightly.log'

if ($Remove) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $existing) {
        Write-Output "There is no scheduled task called '$TaskName'. Nothing removed."
        exit 0
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output "Removed the scheduled task '$TaskName'."
    Write-Output "The rows already written are left alone: $rows"
    exit 0
}

if (-not (Test-Path $journey)) {
    Write-Error "$journey is not there. This script registers the journey in its own checkout."
    exit 2
}

if ([string]::IsNullOrWhiteSpace($Python)) {
    $venv = Join-Path (Join-Path (Join-Path $repo '.venv') 'Scripts') 'python.exe'
    if (Test-Path $venv) {
        $Python = $venv
    }
    else {
        $found = Get-Command python -ErrorAction SilentlyContinue
        if ($null -eq $found) {
            Write-Error "No python found. Pass -Python with the interpreter to use."
            exit 2
        }
        $Python = $found.Source
    }
}

if (-not (Test-Path $rows)) {
    New-Item -ItemType Directory -Path $rows -Force | Out-Null
}

# `cmd.exe` because a scheduled action cannot redirect on its own, and the log
# is the whole point of running this unattended: a night that failed before it
# reached the row has to leave something behind to read. Appended (`1>>`), never
# truncated - a fortnight of nights in one file is the record.
$inner = 'set "PYTHONIOENCODING=utf-8" & "{0}" "{1}" 1>> "{2}" 2>&1' -f $Python, $journey, $log
$arguments = '/c "{0}"' -f $inner

$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument $arguments -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
# THREE HOURS, against a sixty minute cap. The cap bounds the RUN; the engine
# start, the model probe and the last turn the run was in when it was asked to
# stop all sit outside it, and a limit that killed the process mid-write would
# leave a half-written row - the one outcome worse than a bad one.
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
    -MultipleInstances IgnoreNew

$description = @"
Drives one live ML Harness journey against the local model and writes one score
row to docs/score_rows/. Registered by scripts/schedule_nightly_journey.ps1 from
$repo. Remove it with that same script and -Remove.
"@

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description $description `
    -Force | Out-Null

Write-Output "Registered '$TaskName' at $Time daily."
Write-Output "  python : $Python"
Write-Output "  script : $journey"
Write-Output "  log    : $log"
Write-Output "  rows   : $(Join-Path $rows 'rows.csv')"
Write-Output ""
Write-Output "It runs as the logged-on user, only while that user is logged on."
Write-Output "Remove it with: powershell -ExecutionPolicy Bypass -File scripts/schedule_nightly_journey.ps1 -Remove"
