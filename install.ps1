<#
ML Harness for Windows, installed with one line in PowerShell:

    irm https://raw.githubusercontent.com/naidx0/ml-harness-app/main/install.ps1 | iex

What it does, in order. It is safe to run again: anything already done is skipped.

  1. Downloads the latest ML Harness release and checks its SHA-256 against the
     release's SHA256SUMS.txt. A mismatch stops everything. Skipped when that
     version is already installed.
  2. Installs it for your user only (no admin rights).
  3. Installs Ollama with Ollama's own installer (ollama.com/install.ps1) when no
     Ollama is found. That download is about 1.6 GB and runs alongside step 1.
  4. Pulls one local model when it is not pulled yet (qwen3.5:4b, about 3.4 GB).
  5. Opens ML Harness and connects that model, so the first screen is ready for a
     question.

Options, set before the line, for example:

    $env:MLH_MODEL = "qwen3.5:2b"; irm https://raw.githubusercontent.com/naidx0/ml-harness-app/main/install.ps1 | iex

    MLH_MODEL       which Ollama model to pull and connect (default qwen3.5:4b)
    MLH_NO_OLLAMA   1 = install only the app; you will connect an API key instead
    MLH_NO_LAUNCH   1 = do not open the app at the end
    MLH_VERSION     a release tag such as v0.1.0 (default: the latest release)
#>

function Install-MLHarness {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $repo      = 'naidx0/ml-harness-app'
    $model     = if ($env:MLH_MODEL) { $env:MLH_MODEL } else { 'qwen3.5:4b' }
    $noOllama  = $env:MLH_NO_OLLAMA -eq '1'
    $noLaunch  = $env:MLH_NO_LAUNCH -eq '1'
    $version   = $env:MLH_VERSION
    $ollamaUrl = 'http://127.0.0.1:11434'
    $work      = Join-Path $env:TEMP 'ml-harness-install'
    $started   = Get-Date

    if (-not [Environment]::Is64BitOperatingSystem) { Fail 'ML Harness needs 64-bit Windows 10 or 11.' }
    New-Item -ItemType Directory -Force -Path $work | Out-Null

    # ---- 1. which release ----------------------------------------------------
    Say 'Finding the latest ML Harness release'
    $api = if ($version) { "https://api.github.com/repos/$repo/releases/tags/$version" } else { "https://api.github.com/repos/$repo/releases/latest" }
    try {
        $release = Invoke-RestMethod -Uri $api -Headers @{ 'User-Agent' = 'ml-harness-install' } -UseBasicParsing
    } catch {
        Fail "could not read $api ($($_.Exception.Message)). Check the internet connection, or download the installer from https://github.com/$repo/releases/latest"
    }
    $setup = $release.assets | Where-Object { $_.name -like 'ML-Harness-Setup-*-x64.exe' } | Select-Object -First 1
    $sums  = $release.assets | Where-Object { $_.name -eq 'SHA256SUMS.txt' } | Select-Object -First 1
    if (-not $setup) { Fail "release $($release.tag_name) has no Windows installer." }
    if (-not $sums)  { Fail "release $($release.tag_name) has no SHA256SUMS.txt, so the download cannot be checked." }
    $wantVersion = $release.tag_name.TrimStart('v')

    # ---- 3a. Ollama's installer, started first because it is the big one ----
    # It runs in the background while the app downloads and installs. Its own
    # script checks the installer's signature.
    $ollamaExe = $null
    $ollamaProc = $null
    $ollamaLog = Join-Path $work 'ollama-install.log'
    if (-not $noOllama) {
        $ollamaExe = Find-Ollama
        if ($ollamaExe) {
            Say "Ollama is already installed: $ollamaExe"
        } else {
            Say 'Ollama was not found. Installing it with ollama.com/install.ps1 (about 1.6 GB), in the background'
            $ollamaProc = Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -PassThru -ArgumentList @(
                '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command',
                "& { irm https://ollama.com/install.ps1 | iex } *> '$ollamaLog'"
            )
        }
    }

    # ---- 1b and 2. the app, unless this version is already installed ---------
    # Skipping it is what lets the app's own first-run screen offer this same
    # line while the app is open: then only Ollama and the model are added.
    $entry = Find-AppEntry
    $app = Find-App
    if ($entry -and $app -and $entry.DisplayVersion -eq $wantVersion) {
        Say "ML Harness $wantVersion is already installed"
    } else {
        if (Test-AppOpen) { Fail 'an older ML Harness is open. Close it, then run the line again.' }
        Install-App $setup $sums $work
        $app = Find-App
        if (-not $app) { Fail 'the installer finished but the app was not found in the Windows uninstall list.' }
        Note "Installed: $app"
    }

    if (-not $noOllama) {
        # ---- 3b. Ollama finished and answering ------------------------------
        if ($ollamaProc) {
            Say 'Waiting for the Ollama install to finish'
            $ollamaProc.WaitForExit()
            $ollamaExe = Find-Ollama
            if (-not $ollamaExe) {
                Get-Content $ollamaLog -ErrorAction SilentlyContinue | Select-Object -Last 15 | ForEach-Object { Note $_ }
                Fail "Ollama did not install (its log: $ollamaLog). ML Harness is installed; connect an API key in the app, or install Ollama from https://ollama.com/download and run this line again."
            }
            Note "Ollama installed: $ollamaExe"
        }
        if (-not (Test-Ollama $ollamaUrl)) {
            Say 'Starting Ollama'
            $tray = Join-Path (Split-Path $ollamaExe) 'ollama app.exe'
            if (Test-Path $tray) { Start-Process -FilePath $tray } else { Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WindowStyle Hidden }
            $deadline = (Get-Date).AddSeconds(90)
            while (-not (Test-Ollama $ollamaUrl) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 2 }
            if (-not (Test-Ollama $ollamaUrl)) { Fail "Ollama is installed but did not answer on $ollamaUrl within 90 s. Open Ollama from the Start menu and run this line again." }
        }

        # ---- 4. the model ---------------------------------------------------
        $have = @()
        try { $have = @((Invoke-RestMethod -Uri "$ollamaUrl/api/tags" -UseBasicParsing).models | ForEach-Object { $_.name }) } catch { }
        $wanted = if ($model -match ':') { $model } else { "$model`:latest" }
        if ($have -contains $wanted) {
            Say "The model $model is already pulled"
        } else {
            Say "Pulling the model $model (a few GB; Ollama shows its progress)"
            & $ollamaExe pull $model
            if ($LASTEXITCODE -ne 0) { Fail "ollama pull $model exited with code $LASTEXITCODE. ML Harness and Ollama are installed; run the line again to retry the pull." }
        }
    }

    if ($noLaunch) {
        Say ('Done in {0:N0} s. Open ML Harness from the Start menu.' -f ((Get-Date) - $started).TotalSeconds)
        return
    }

    # ---- 5. open it and connect the model ------------------------------------
    if (Test-AppOpen) {
        Say 'ML Harness is already open'
    } else {
        Say 'Opening ML Harness (the first launch sets up its own Python, so it needs internet)'
        Start-Process -FilePath $app
    }
    $engine = Wait-Engine 600
    if (-not $engine) {
        Say 'ML Harness is open, but its engine did not answer within 10 minutes, so the model was not connected for you.'
        Note 'In the app, click the model under "Pick a model to start".'
        return
    }
    if (-not $noOllama) {
        try {
            $row = Connect-Model $engine $model $ollamaUrl
            Note "Connected $($row.model) (tool calling: $($row.tool_calling))"
        } catch {
            Note "The model is pulled, but connecting it failed: $($_.Exception.Message)"
            Note 'In the app, click the model under "Pick a model to start".'
        }
    }
    Write-Host ''
    Say ('Done in {0:N0} s. ML Harness is open. Type what you want in the box, for example:' -f ((Get-Date) - $started).TotalSeconds)
    Note "Train a logistic regression on scikit-learn's iris dataset with an 80/20 split and tell me the test accuracy."
    if ($noOllama) { Note 'No local model was set up. Click "Use an API key instead" in the app to connect one.' }
}

function Say([string]$text) { Write-Host ">>> $text" }
function Note([string]$text) { Write-Host "    $text" }
function Fail([string]$text) {
    Write-Host ''
    Write-Host "Stopped: $text" -ForegroundColor Red
    $script:MLHarnessSaid = $true
    throw $text
}

function Install-App($setup, $sums, [string]$work) {
    Say "Downloading $($setup.name) ($([math]::Round($setup.size / 1MB)) MB)"
    $exe = Join-Path $work $setup.name
    Invoke-WebRequest -Uri $setup.browser_download_url -OutFile $exe -UseBasicParsing
    $sumsText = (Invoke-WebRequest -Uri $sums.browser_download_url -UseBasicParsing).Content
    if ($sumsText -is [byte[]]) { $sumsText = [Text.Encoding]::UTF8.GetString($sumsText) }
    $line = ($sumsText -split "`n") | Where-Object { $_ -match [regex]::Escape($setup.name) } | Select-Object -First 1
    if (-not $line) { Fail "SHA256SUMS.txt does not list $($setup.name)." }
    $expected = ($line.Trim() -split '\s+')[0].ToLower()
    $actual = (Get-FileHash -Path $exe -Algorithm SHA256).Hash.ToLower()
    if ($expected -ne $actual) {
        Remove-Item $exe -Force -ErrorAction SilentlyContinue
        Fail "the download's SHA-256 is $actual but the release says $expected. Nothing was installed."
    }
    Note "SHA-256 matches the release: $actual"
    Say 'Installing ML Harness for this user'
    $run = Start-Process -FilePath $exe -ArgumentList '/S' -Wait -PassThru
    if ($run.ExitCode -ne 0) { Fail "the installer exited with code $($run.ExitCode)." }
}

function Test-AppOpen {
    return [bool](Get-Process -Name 'ML Harness', 'ml-harness-shell' -ErrorAction SilentlyContinue)
}

function Find-Ollama {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($candidate in @("$env:LOCALAPPDATA\Programs\Ollama\ollama.exe", "$env:ProgramFiles\Ollama\ollama.exe")) {
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

function Test-Ollama([string]$url) {
    try { Invoke-RestMethod -Uri "$url/api/version" -TimeoutSec 3 -UseBasicParsing | Out-Null; return $true } catch { return $false }
}

# The uninstall entry the NSIS installer wrote: where it put the app, and which
# version it is.
function Find-AppEntry {
    foreach ($hive in 'HKCU:', 'HKLM:') {
        $entry = Get-ChildItem "$hive\Software\Microsoft\Windows\CurrentVersion\Uninstall" -ErrorAction SilentlyContinue |
            ForEach-Object { Get-ItemProperty $_.PSPath } |
            Where-Object { $_.DisplayName -like 'ML Harness*' -and $_.InstallLocation } |
            Select-Object -First 1
        if ($entry) { return $entry }
    }
    return $null
}

# The exe in the install folder that is neither the uninstaller nor a sidecar.
function Find-App {
    $entry = Find-AppEntry
    if ($entry) {
        $exe = Get-ChildItem -Path $entry.InstallLocation.Trim('"') -Filter '*.exe' -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notmatch 'uninstall|^uv' } | Select-Object -First 1
        if ($exe) { return $exe.FullName }
    }
    $fallback = "$env:LOCALAPPDATA\ML Harness\ml-harness-shell.exe"
    if (Test-Path $fallback) { return $fallback }
    return $null
}

# The app writes its address and token here once its engine is up.
function Wait-Engine([int]$seconds) {
    $file = "$env:LOCALAPPDATA\ml-harness\engine.json"
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $cfg = Get-Content $file -Raw -ErrorAction Stop | ConvertFrom-Json
            if ((Invoke-WebRequest -Uri "$($cfg.base_url)/health" -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200) { return $cfg }
        } catch { }
        Start-Sleep -Seconds 2
    }
    return $null
}

# The same three calls the app's one-click "connect" makes: reuse the row for
# this model if there is one, otherwise create it; then make it active and probe it.
function Connect-Model($cfg, [string]$model, [string]$ollamaUrl) {
    $headers = @{ Authorization = "Bearer $($cfg.token)" }
    $base = $cfg.base_url
    $rows = @(Invoke-RestMethod -Uri "$base/api/providers" -Headers $headers -UseBasicParsing)
    $row = $rows | Where-Object { $_.adapter -eq 'ollama' -and $_.model -eq $model } | Select-Object -First 1
    if (-not $row) {
        $body = @{ name = $model; base_url = $ollamaUrl; model = $model; adapter = 'ollama' } | ConvertTo-Json -Compress
        $row = Invoke-RestMethod -Uri "$base/api/providers" -Method Post -Headers $headers -ContentType 'application/json' -Body $body -UseBasicParsing
    }
    Invoke-RestMethod -Uri "$base/api/providers/$($row.id)/activate" -Method Post -Headers $headers -UseBasicParsing | Out-Null
    return Invoke-RestMethod -Uri "$base/api/providers/$($row.id)/probe" -Method Post -Headers $headers -UseBasicParsing -TimeoutSec 300
}

# Errors are printed, never thrown out of `iex`: a throw there can close the
# window the person is reading, and `exit` would close it for certain.
$script:MLHarnessSaid = $false
try { Install-MLHarness } catch {
    if (-not $script:MLHarnessSaid) {
        Write-Host ''
        Write-Host "Stopped: $($_.Exception.Message)" -ForegroundColor Red
    }
    Write-Host 'Run the line again after fixing that, or download the installer from https://github.com/naidx0/ml-harness-app/releases/latest'
}
