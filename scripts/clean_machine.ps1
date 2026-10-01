# THE CLEAN-MACHINE TEST, run from inside Windows Sandbox.
#
# `.github/workflows/gate.yml` says what this is and why a runner is not it:
# *"the clean-machine test is a person installing a wheel on a computer that has
# never seen this repository and reaching a diagnosed problem without asking a
# question. A runner is a fresh machine, which is most of it, and it is not a
# person."* THE_PLAN Phase C recorded it BLOCKED for wanting a second computer.
#
# Windows Sandbox is a second computer. It boots clean every time, has no
# Python, no WebView2, no repository and no %LOCALAPPDATA% belonging to this
# product, and it is thrown away on close. What it is NOT is a person - so this
# script measures the mechanical half honestly and says so, and the half about
# whether somebody UNDERSTANDS what they see stays a thing a human does.
#
# Run by `scripts/clean_machine_test.py`, which writes the .wsb that starts it.

$ErrorActionPreference = "Stop"
$root    = "C:\Users\WDAGUtilityAccount\Desktop"
$results = Join-Path $root "results"
$log     = Join-Path $results "clean-machine.log"
$facts   = [ordered]@{}

function Say($text) {
    $stamp = (Get-Date).ToString("HH:mm:ss")
    "$stamp  $text" | Tee-Object -FilePath $log -Append | Write-Host
}

New-Item -ItemType Directory -Force -Path $results | Out-Null
Say "=== the clean-machine test ==="

# ── 1. PROVE THE MACHINE IS ACTUALLY CLEAN ───────────────────────────────────
# Asserted first, because every measurement after this is worthless if it is
# not true. A test that ran on a machine with Python already on it would be
# testing the developer's machine wearing a sandbox's clothes.
$python = Get-Command python -ErrorAction SilentlyContinue
$facts["python_before"] = if ($python) { $python.Source } else { $null }
$facts["data_root_before"] = Test-Path "$env:LOCALAPPDATA\ml-harness"
$facts["webview2_before"] = [bool](Get-ItemProperty `
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" `
    -ErrorAction SilentlyContinue)
Say "python on PATH before install: $($facts['python_before'])"
Say "%LOCALAPPDATA%\ml-harness exists before install: $($facts['data_root_before'])"
Say "WebView2 runtime registered before install: $($facts['webview2_before'])"

if ($facts["python_before"]) {
    Say "REFUSING: this machine already has Python, so it is not the machine this test is about."
    $facts | ConvertTo-Json | Set-Content (Join-Path $results "result.json")
    exit 2
}

# ── 2. INSTALL, THE WAY A PERSON WOULD ───────────────────────────────────────
$installer = Get-ChildItem (Join-Path $root "installer") -Recurse -Include *.exe |
             Where-Object Name -notlike "*uv*" | Select-Object -First 1
if (-not $installer) { Say "no installer found"; exit 3 }
Say "installing $($installer.Name) ($([math]::Round($installer.Length/1MB,1)) MB)"

$started = Get-Date
# /S is NSIS's silent switch. A person would click through; the clicking is not
# what this measures, and an unattended run is what makes the timing a number.
$run = Start-Process -FilePath $installer.FullName -ArgumentList "/S" -Wait -PassThru
$facts["installer_exit"] = $run.ExitCode
$facts["install_seconds"] = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
Say "installer exited $($run.ExitCode) after $($facts['install_seconds'])s"

# ── 3. FIND WHAT IT INSTALLED ────────────────────────────────────────────────
# TWO NAMES, BECAUSE THE BUNDLER RENAMES. `cargo` builds ml-harness-shell.exe;
# Tauri's NSIS/MSI bundlers install it as "<productName>.exe" - "ML Harness.exe".
# The first run that could report (2026-09-02) searched for the cargo name
# only, found nothing, and called a successful install a failure.
# WHERE THE INSTALLER SAID IT PUT THINGS, READ BACK FROM THE REGISTRY. Measured
# 2026-09-02: the NSIS install lands in %LOCALAPPDATA%\ML Harness (not under
# Programs\), the MSI under Program Files, and neither is named the way the
# first search assumed. So: the registered InstallLocation first, then the
# conventional folders, and whatever exe is inside that is not the
# uninstaller or the uv sidecar IS the app - its name is then on record.
$candidates = @()
foreach ($hive in "HKCU:", "HKLM:") {
    Get-ChildItem "$hive\Software\Microsoft\Windows\CurrentVersion\Uninstall" -ErrorAction SilentlyContinue |
        ForEach-Object { $_ | Get-ItemProperty } |
        Where-Object { $_.DisplayName -like "*ML Harness*" -and $_.InstallLocation } |
        ForEach-Object { $candidates += ($_.InstallLocation -replace '"', '') }
}
$candidates += "$env:LOCALAPPDATA\ML Harness", "$env:LOCALAPPDATA\Programs\ML Harness",
               "$env:ProgramFiles\ML Harness", "${env:ProgramFiles(x86)}\ML Harness"
$app = $null
foreach ($dir in $candidates | Select-Object -Unique) {
    if (-not (Test-Path $dir)) { continue }
    $inside = Get-ChildItem $dir -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name
    Say "install folder $dir holds: $($inside -join ', ')"
    $app = Get-ChildItem $dir -Filter *.exe -ErrorAction SilentlyContinue |
           Where-Object { $_.Name -notlike "uninstall*" -and $_.Name -notlike "uv*" } |
           Select-Object -First 1
    if ($app) { break }
}
if (-not $app) {
    Say "the setup.exe ran (/S, exit $($run.ExitCode)) and left neither ml-harness-shell.exe nor 'ML Harness.exe'"
    # MEASURED ON 2026-09-02: exit 0 after 66 s, and %LOCALAPPDATA%\Programs was
    # EMPTY. A silent NSIS install that writes nothing and reports success is
    # the defect; the lines below exist so the next run says why instead of
    # only that. Registry first: an installer that got as far as registering
    # itself says where it thought it installed.
    foreach ($hive in "HKCU:", "HKLM:") {
        $keys = Get-ChildItem "$hive\Software\Microsoft\Windows\CurrentVersion\Uninstall" -ErrorAction SilentlyContinue |
                Where-Object { ($_ | Get-ItemProperty).DisplayName -like "*ML Harness*" }
        foreach ($key in $keys) {
            $p = $key | Get-ItemProperty
            Say "$hive uninstall entry: $($p.DisplayName) at '$($p.InstallLocation)' ($($p.UninstallString))"
        }
    }
    $facts["webview2_after_setup_exe"] = [bool](Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" -ErrorAction SilentlyContinue)
    Say "WebView2 runtime registered after setup.exe: $($facts['webview2_after_setup_exe'])"
    $programs = Get-ChildItem "$env:LOCALAPPDATA\Programs" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name
    Say "%LOCALAPPDATA%\Programs holds: $($programs -join ', ')"
    $anywhere = Get-ChildItem $env:USERPROFILE, "C:\Program Files", "C:\Program Files (x86)" -Recurse -Include "ML Harness.exe", "ml-harness-shell.exe" -ErrorAction SilentlyContinue | Select-Object -First 3
    Say "exe anywhere in the profile or Program Files: $(($anywhere | ForEach-Object FullName) -join '; ')"

    # THE MSI IS THE SECOND WITNESS, and the one that keeps a diary: msiexec's
    # verbose log names every action and the first one that failed.
    $msi = Get-ChildItem (Join-Path $root "installer") -Recurse -Include *.msi | Select-Object -First 1
    if ($msi) {
        $msilog = Join-Path $results "msi-install.log"
        Say "trying the MSI instead: $($msi.Name) with a verbose log"
        $started = Get-Date
        $m = Start-Process msiexec.exe -ArgumentList "/i", "`"$($msi.FullName)`"", "/qn", "/l*v", "`"$msilog`"" -Wait -PassThru
        $facts["msi_exit"] = $m.ExitCode
        $facts["msi_seconds"] = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
        Say "msiexec exited $($m.ExitCode) after $($facts['msi_seconds'])s; log at results\msi-install.log"
        $app = Get-ChildItem "$env:LOCALAPPDATA\Programs", "$env:ProgramFiles", "${env:ProgramFiles(x86)}", $env:USERPROFILE `
                -Recurse -Include "ml-harness-shell.exe", "ML Harness.exe" -ErrorAction SilentlyContinue |
               Select-Object -First 1
        if ($app) { Say "the MSI installed it at $($app.FullName)" }
    }
    if (-not $app) {
        $facts | ConvertTo-Json | Set-Content (Join-Path $results "result.json")
        exit 4
    }
}
$facts["installed_at"] = $app.FullName
Say "installed at $($app.FullName)"

$sidecar = Get-ChildItem $app.DirectoryName -Filter "uv*.exe" | Select-Object -First 1
$wheel = Get-ChildItem $app.DirectoryName -Recurse -Filter "ml_harness-*.whl" -ErrorAction SilentlyContinue |
         Select-Object -First 1
$facts["sidecar_shipped"] = if ($sidecar) { $sidecar.Name } else { $null }
$facts["wheel_shipped"] = if ($wheel) { $wheel.Name } else { $null }
Say "sidecar beside it: $($facts['sidecar_shipped'])"
Say "wheel beside it:   $($facts['wheel_shipped'])"

# ── 4. THE FIRST RUN ─────────────────────────────────────────────────────────
# The window opens, `config.ts` finds no engine, asks the shell to start one,
# and `engine.rs` finds no interpreter and has uv build one. On a machine with
# no Python that is a CPython download plus a dependency tree, so the wait is
# generous - and the thing being measured is whether it ends at all without
# somebody opening a terminal.
Say "launching the app; nobody will type anything from here on"
$launched = Get-Date
Start-Process -FilePath $app.FullName | Out-Null

$portfile = "$env:LOCALAPPDATA\ml-harness\engine.json"
$deadline = (Get-Date).AddMinutes(12)
while ((Get-Date) -lt $deadline -and -not (Test-Path $portfile)) {
    Start-Sleep -Seconds 5
}
$facts["portfile_appeared"] = Test-Path $portfile
$facts["first_run_seconds"] = [math]::Round(((Get-Date) - $launched).TotalSeconds, 1)

if (-not $facts["portfile_appeared"]) {
    Say "NO ENGINE. Nothing published $portfile within 12 minutes."
    $facts["verdict"] = "the first run did not reach an engine"
    $facts | ConvertTo-Json | Set-Content (Join-Path $results "result.json")
    exit 5
}
Say "engine.json appeared after $($facts['first_run_seconds'])s"

# ── 5. IS IT REALLY OURS, AND REALLY FROM AN INTERPRETER UV MADE? ────────────
$published = Get-Content $portfile -Raw | ConvertFrom-Json
$facts["port"] = $published.port
$facts["interpreter"] = $published.engine.executable
if (-not $facts["interpreter"]) { $facts["interpreter"] = $published.build.executable }

$health = $null
for ($try = 0; $try -lt 12 -and -not $health; $try++) {
    try {
        $health = Invoke-RestMethod -Uri "$($published.base_url)/health" -TimeoutSec 5
    } catch { Start-Sleep -Seconds 5 }
}
$facts["health_service"] = $health.service
$facts["health_status"]  = $health.status
$facts["schema_agrees"]  = $health.schema.agrees
$facts["python_version"] = $health.build.python
$facts["sha_source"]     = $health.build.sha_source
Say "health: service=$($health.service) status=$($health.status) python=$($health.build.python)"
Say "interpreter: $($facts['interpreter'])"

# ── 6. THE PRODUCT'S OWN ANSWER ABOUT ITSELF ─────────────────────────────────
# `mlh doctor` is what THE_PLAN V.0 built for exactly this moment: the first
# thing an installed copy can be asked to do, on the machine somebody installed
# onto, which is the only place the answer counts.
$interpreter = $facts["interpreter"]
if ($interpreter -and (Test-Path $interpreter)) {
    $doctor = & $interpreter -m app.cli doctor 2>&1 | Out-String
    $facts["doctor_exit"] = $LASTEXITCODE
    $doctor | Set-Content (Join-Path $results "doctor.txt")
    Say "mlh doctor exited $LASTEXITCODE"
    Say $doctor
}

$facts["verdict"] = if (
    $facts["health_service"] -eq "ml-harness-engine" -and $facts["doctor_exit"] -eq 0
) { "a clean machine reached a working engine with nothing typed" }
  else { "the first run got somewhere and not all the way - read the log" }

Say "VERDICT: $($facts['verdict'])"
$facts | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $results "result.json")
Say "=== done; results are on the host ==="
