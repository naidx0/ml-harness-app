# What a stranger gets from the INSTALLER, on a machine that has never seen
# this repository.
#
# `docs/PHASES.md` Phase 5: "somebody who has never seen the repository gets
# from zero to a diagnosed problem without asking a question." The install half
# was measured in THE_PLAN.md C.d.4 - silent install, engine in 16 seconds,
# clean uninstall - on the machine that BUILT it, which has the checkout, the
# model cache and a developer's PATH. This runs it where none of that is true.
#
# NO CHECKOUT IS MAPPED IN. The only things on this machine are Windows, the
# installer, and this script.

$ErrorActionPreference = "Continue"
$out  = "C:\Users\WDAGUtilityAccount\Desktop\out"
$page = Join-Path $out "harness-stranger.txt"
$inst = "C:\Users\WDAGUtilityAccount\Desktop\in\ML-Harness-setup.exe"

function Say($text) {
    $text | Out-File -Append -Encoding utf8 $page
}

function Run($label, $block) {
    Say ""
    Say "`$ $label"
    $result = & $block 2>&1 | Out-String
    Say $result.TrimEnd()
}

"=== what this machine has ===" | Out-File -Encoding utf8 $page
Say ("python on PATH:  " + [bool](Get-Command python -ErrorAction SilentlyContinue))
Say ("git on PATH:     " + [bool](Get-Command git -ErrorAction SilentlyContinue))
Say ("uv on PATH:      " + [bool](Get-Command uv -ErrorAction SilentlyContinue))
Say ("installer bytes: " + (Get-Item $inst).Length)

# ---------------------------------------------------------------------------
# 1. Install it the way a person would: double-click, or /S for a script.

Run "install silently" {
    $p = Start-Process -FilePath $inst -ArgumentList "/S" -PassThru -Wait
    "installer exit: " + $p.ExitCode
}

$home_dir = "C:\Users\WDAGUtilityAccount\AppData\Local\ML Harness"
Run "what landed" {
    if (Test-Path $home_dir) {
        Get-ChildItem -Recurse $home_dir | ForEach-Object {
            "{0,12}  {1}" -f $_.Length, $_.FullName.Replace($home_dir, "")
        }
    } else {
        "NOTHING AT $home_dir - the install did not put files where the first run looks"
    }
}

# ---------------------------------------------------------------------------
# 2. Start it. The shell binary is what a person launches; it bootstraps the
#    Python side on first run, which is the slow part and the one that needs
#    the network.

$shell = Join-Path $home_dir "ml-harness-shell.exe"
if (Test-Path $shell) {
    Run "launch the shell" {
        Start-Process -FilePath $shell -PassThru | Select-Object -ExpandProperty Id |
            ForEach-Object { "started pid $_" }
    }
} else {
    Say ""
    Say "NO SHELL BINARY AT $shell - a stranger has nothing to launch."
}

# ---------------------------------------------------------------------------
# 3. Wait for the engine to publish itself, and say how long it took.
#
# `app/security.py` writes engine.json into the data root, which for an
# installed copy with no checkout is under %LOCALAPPDATA%. Searched rather than
# assumed, because the exact directory name is the product's decision and a
# stranger test that hard-codes it is testing this script's memory.

$deadline = (Get-Date).AddSeconds(420)
$engine = $null
while ((Get-Date) -lt $deadline -and -not $engine) {
    $engine = Get-ChildItem "C:\Users\WDAGUtilityAccount\AppData\Local" -Recurse `
        -Filter "engine.json" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $engine) { Start-Sleep -Seconds 5 }
}

Say ""
if ($engine) {
    Say "engine.json appeared at $($engine.FullName)"
    $cfg = Get-Content $engine.FullName -Raw | ConvertFrom-Json
    Say ("base_url: " + $cfg.base_url)
    Say ("token present: " + [bool]$cfg.token)

    # 4. Ask it the one question every client asks first.
    Run "GET /health" {
        try {
            $headers = @{}
            if ($cfg.token) { $headers["Authorization"] = "Bearer " + $cfg.token }
            $r = Invoke-WebRequest -Uri ($cfg.base_url + "/health") -Headers $headers `
                 -UseBasicParsing -TimeoutSec 30
            "HTTP " + $r.StatusCode + "`n" + $r.Content
        } catch {
            "FAILED: " + $_.Exception.Message
        }
    }

    # 5. AND THE QUESTION PHASE 5 ACTUALLY ASKS: can this person reach a
    #    diagnosis? A diagnosis needs a model, and this machine has none - no
    #    Ollama, no key, no cache. Reported rather than worked around, because
    #    "the stranger installs it and then cannot do anything" is the finding
    #    if it is the finding.
    Run "what can it be asked without a model" {
        try {
            $headers = @{}
            if ($cfg.token) { $headers["Authorization"] = "Bearer " + $cfg.token }
            $r = Invoke-WebRequest -Uri ($cfg.base_url + "/api/providers") -Headers $headers `
                 -UseBasicParsing -TimeoutSec 30
            "providers: HTTP " + $r.StatusCode + "`n" + $r.Content
        } catch {
            "providers FAILED: " + $_.Exception.Message
        }
    }
} else {
    Say "NO engine.json ANYWHERE UNDER %LOCALAPPDATA% AFTER 7 MINUTES."
    Say "That is the wall a stranger hits, and it is the result."
    Run "is anything listening on 8078" {
        try { (Test-NetConnection -ComputerName 127.0.0.1 -Port 8078 -WarningAction SilentlyContinue).TcpTestSucceeded }
        catch { "could not test" }
    }
}

Say ""
Say "=== done ==="
"done" | Out-File -Encoding utf8 (Join-Path $out "finished")
