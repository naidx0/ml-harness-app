# THE SMALL ML TASK ON A MACHINE WITH NOTHING (Windows Sandbox).
#
# finish-plan.md slice 3. A stranger installs today's build, connects a local
# model, and asks for the iris task; the page records whether it finished,
# scored by scripts/smoke_small_task.py (the H-shell scorer), run with the
# Python the installer itself built.
#
# What is mapped in, read-only: the installer, this script, the smoke script,
# arm.txt (commit, installer sha256, model) and a copy of ONE model's Ollama
# files, so the walk measures the product rather than a 2 GB download. Ollama
# itself is downloaded inside the sandbox, as a stranger would.
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
$desk = Join-Path $env:USERPROFILE "Desktop"
$in = Join-Path $desk "in"
$out = Join-Path $desk "out"
$page = Join-Path $out "small-task-stranger.txt"
function Say($text) { $text | Out-File -Append -Encoding utf8 $page }
function Run($label, $block) { Say ""; Say "`$ $label"; Say ((& $block 2>&1 | Out-String).TrimEnd()) }

"=== the build under test ===" | Out-File -Encoding utf8 $page
Get-Content (Join-Path $in "arm.txt") | ForEach-Object { Say ("  " + $_) }
$model = (Get-Content (Join-Path $in "arm.txt") | Where-Object { $_ -match "^model=" }) -replace "^model=", ""
Say ("python on PATH: " + [bool](Get-Command python -ErrorAction SilentlyContinue))
Say ("git on PATH:    " + [bool](Get-Command git -ErrorAction SilentlyContinue))
Say ("ollama on PATH: " + [bool](Get-Command ollama -ErrorAction SilentlyContinue))

Run "install silently" {
    $p = Start-Process -FilePath (Join-Path $in "ML-Harness-setup.exe") -ArgumentList "/S" -PassThru -Wait
    "installer exit: " + $p.ExitCode
}
$lnk = Get-ChildItem "$desk\*.lnk", "$env:PUBLIC\Desktop\*.lnk" -ErrorAction SilentlyContinue | Where-Object Name -match "ML Harness" | Select-Object -First 1
Say ("desktop shortcut: " + ($(if ($lnk) { $lnk.FullName } else { "NONE" })))

Run "launch from the desktop shortcut" {
    $t0 = Get-Date
    if ($lnk) { Start-Process $lnk.FullName } else { Start-Process "$env:LOCALAPPDATA\ML Harness\ml-harness-shell.exe" }
    $ok = $false
    while (((Get-Date) - $t0).TotalSeconds -lt 900 -and -not $ok) {
        try { $ok = (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8078/health -TimeoutSec 3).StatusCode -eq 200 } catch { Start-Sleep 3 }
    }
    "health 200: $ok after {0:N0}s" -f ((Get-Date) - $t0).TotalSeconds
}

$cfgPath = "$env:LOCALAPPDATA\ml-harness\engine.json"
$cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
$base = $cfg.base_url
$H = @{ Authorization = "Bearer " + $cfg.token; "Content-Type" = "application/json" }
function Post($path, $body) {
    try { $r = Invoke-WebRequest -Uri ($base + $path) -Headers $H -Method POST -Body ($body | ConvertTo-Json -Depth 8 -Compress) -UseBasicParsing -TimeoutSec 300; "HTTP " + $r.StatusCode + "`n" + $r.Content }
    catch { "FAILED: " + $_.Exception.Message }
}

Run "get Ollama (the zip)" {
    $zip = "$desk\ollama.zip"; $t0 = Get-Date
    & curl.exe -L --silent --show-error --max-time 1800 -o $zip "https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.zip" 2>&1 | Out-Null
    Expand-Archive -Path $zip -DestinationPath "$desk\ollama" -Force
    "{0:N0} bytes in {1:N0}s" -f (Get-Item $zip).Length, ((Get-Date) - $t0).TotalSeconds
}
$ollama = (Get-ChildItem "$desk\ollama" -Recurse -Filter ollama.exe | Select-Object -First 1).FullName
# The model's files, copied from the read-only map so Ollama may write beside them.
Copy-Item -Recurse -Force (Join-Path $in "models") "$desk\models"
$env:OLLAMA_MODELS = "$desk\models"
Run "start ollama" { (Start-Process -FilePath $ollama -ArgumentList "serve" -PassThru -WindowStyle Hidden).Id; Start-Sleep 10; & $ollama list }

Run "connect it the way one click does" {
    Post "/api/providers" @{ name = "Ollama"; base_url = "http://127.0.0.1:11434"; model = $model; adapter = "ollama" }
    Post "/api/providers/1/activate" @{}
    Post "/api/providers/1/probe" @{}
}

$py = "$env:LOCALAPPDATA\ml-harness\python\Scripts\python.exe"
Run "the small ML task, scored (iris)" {
    & $py (Join-Path $in "smoke_small_task.py") --task iris --budget 2400 --out (Join-Path $out "small-task-iris.json")
    "smoke exit: $LASTEXITCODE"
}
Run "what Python the machine has now" { Get-Command python, python3, py -ErrorAction SilentlyContinue | Select-Object Source | Out-String }
Say ""
Say "=== done ==="
"done" | Out-File -Encoding utf8 (Join-Path $out "finished")
