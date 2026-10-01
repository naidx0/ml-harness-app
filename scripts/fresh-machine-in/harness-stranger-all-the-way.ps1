# THE WHOLE PHASE 5 SENTENCE, on a machine that has never seen this repository.
#
# `docs/PHASES.md` Phase 5: "somebody who has never seen the repository gets
# from zero to a diagnosed problem without asking a question."
#
# The install half was driven on 2026-09-10 and stopped exactly where the
# done-condition points: `/api/providers` answered HTTP 200 with an EMPTY LIST.
# That run reported the wall and stopped, and this lane then wrote that the
# remaining link was unbuildable - "a sandbox has no Ollama and no key, so both
# roads out of that banner leave it."
#
# THAT WAS WRONG, AND THE PRODUCT'S OWN BANNER SAYS WHY. It reads "Pick one on
# this machine, or connect an API key." A stranger with no local model does the
# obvious thing: they install one. Doing that inside a throwaway VM is not
# blocked on anybody - it is what the product just told them to do.
#
# So this script IS the stranger, and it does not stop at the wall:
#
#   1. install the harness            (as before)
#   2. see the wall                   /api/providers -> []
#   3. INSTALL OLLAMA                 the thing the banner asks for
#   4. PULL A MODEL                   the smallest one that can hold a turn
#   5. ASK THE PRODUCT WHAT IT SEES   list_local_models, through the engine
#   6. CONNECT IT                     exactly what the one-click button calls:
#                                     create -> activate -> probe
#   7. START A THREAD                 and record where the walk arrives
#
# NOTHING IS MAPPED IN BUT THE INSTALLER. Every download happens inside the
# sandbox and dies with it.
#
# WHAT THIS CAN AND CANNOT SAY. It drives the ENGINE's own API - the same calls
# `useProviders.connectLocal` makes, in the same order. It does not click the
# button, because there is no UI automation inside a sandbox. The rendering half
# is pinned separately by `AStrangerIsToldToConnectAModel.test.tsx`, eight cases
# proved able to fail, and photographed against a scratch engine on the build
# machine. So: the WALK is measured here, the SCREEN is measured there, and
# neither claims to be the other.

$ErrorActionPreference = "Continue"

# THE PROGRESS BAR IS WHY THE DOWNLOAD NEVER FINISHED.
#
# Measured three times, 2026-09-10: this script stalled at exactly the same
# line - Invoke-WebRequest for Ollama's ~700 MB installer - for 18, 25 and 25
# minutes, writing nothing. The third stall had 2.2 GB free on the host and a
# quiet machine, so memory pressure was NOT the cause, which is what made it
# diagnosable rather than unlucky.
#
# In Windows PowerShell 5.1, Invoke-WebRequest re-renders its progress bar on
# every chunk, and on a large file that dominates the transfer - a documented
# slowdown of one to two orders of magnitude. Turning it off is the fix, and
# curl.exe (shipped in Windows 10 1803 and later) avoids the code path
# entirely, so it is tried first and Invoke-WebRequest is the fallback.
$ProgressPreference = "SilentlyContinue"
$out  = "C:\Users\WDAGUtilityAccount\Desktop\out"
$page = Join-Path $out "harness-stranger.txt"
$inst = "C:\Users\WDAGUtilityAccount\Desktop\in\ML-Harness-setup.exe"

function Say($text) { $text | Out-File -Append -Encoding utf8 $page }

function Run($label, $block) {
    Say ""
    Say "`$ $label"
    $result = & $block 2>&1 | Out-String
    Say $result.TrimEnd()
}

"=== what this machine has ===" | Out-File -Encoding utf8 $page

# WHICH BUILD THIS WALK IS TESTING, FIRST, BEFORE ANYTHING ELSE ON THE PAGE.
#
# The previous walk stopped at `map_the_ask` with empty arguments, and the
# conductor now fills that argument from the thread. So a re-driven walk that
# stops the same way has TWO possible readings - the fix does not work, or this
# installer predates it - and the installer BUNDLES A WHEEL AT BUILD TIME, so
# the second one is not hypothetical. A page that cannot tell them apart would
# report the first, which is the defect class this whole night has been about.
$arm_file = "C:\Users\WDAGUtilityAccount\Desktop\in\arm.txt"
$fill_off = $false
# NO DEFAULT MODEL. A model quietly falling back to a constant is how this walk
# came to answer a question nobody asked: the driver was told 3B, the script
# pulled the 7B its own source named, and nothing on the page disagreed. The
# model now arrives with the arm and the page always says which one it was.
$model = $null
if (Test-Path $arm_file) {
    Say "--- the build under test, written by the host driver ---"
    foreach ($line in Get-Content $arm_file) {
        Say ("  " + $line)
        if ($line -match "^fill=off") { $fill_off = $true }
        if ($line -match "^model=(.+)$") { $model = $Matches[1].Trim() }
    }
    Say "--- end ---"
    if (-not $model) {
        Say ""
        Say "NO model= IN arm.txt. Refusing to pull a default: a walk that picks"
        Say "its own model reports a fact about the script rather than about the"
        Say "arm that was asked for. This page is void."
        exit 2
    }
} else {
    Say "NO arm.txt WAS MAPPED IN. This page cannot say which build it tested"
    Say "or which arm it is, so it is not a reading. Treat it as void."
}

Say ("python on PATH:  " + [bool](Get-Command python -ErrorAction SilentlyContinue))
Say ("ollama on PATH:  " + [bool](Get-Command ollama -ErrorAction SilentlyContinue))
Say ("installer bytes: " + (Get-Item $inst).Length)

# ---------------------------------------------------------------------------
# 1. Install it the way a person would.

# THE STRANGER ARRIVES WITH DATA. The previous walk arrived empty-handed and
# then reported that the diagnosis stopped for want of a file - which was a fact
# about MY script, not about the product or the person. A person asking "answer
# my support tickets like our team does" HAS support tickets. 24 rows, four
# categories, obviously synthetic and labelled so in the file, copied to the
# desktop where somebody's own folder would sit.
Copy-Item "C:/Users/WDAGUtilityAccount/Desktop/in/support-tickets.jsonl" `
          "C:/Users/WDAGUtilityAccount/Desktop/support-tickets.jsonl" -Force
Say ""
Say ("tickets on the desktop: " + (Test-Path "C:/Users/WDAGUtilityAccount/Desktop/support-tickets.jsonl"))

Run "install the harness silently" {
    $p = Start-Process -FilePath $inst -ArgumentList "/S" -PassThru -Wait
    "installer exit: " + $p.ExitCode
}

$home_dir = "C:\Users\WDAGUtilityAccount\AppData\Local\ML Harness"
$shell = Join-Path $home_dir "ml-harness-shell.exe"
if (Test-Path $shell) {
    # THE ARM IS SET HERE AND NOWHERE ELSE. The engine is a child of this
    # shell, so it inherits this environment; setting it any later would set it
    # for a process that had already read it.
    if ($fill_off) {
        $env:MLH_FILL_BLANKS_FROM_THREAD = "0"
        Say ""
        Say "ARM: fill OFF - MLH_FILL_BLANKS_FROM_THREAD=0 set before the shell."
        Say "The harness will NOT complete a dropped argument from the thread."
    } else {
        Say ""
        Say "ARM: fill ON - the default. A required argument the thread already"
        Say "holds will be supplied, and the turn says so when it is."
    }
    Run "launch the shell" {
        Start-Process -FilePath $shell -PassThru | Select-Object -ExpandProperty Id |
            ForEach-Object { "started pid $_" }
    }
} else {
    Say ""
    Say "NO SHELL BINARY AT $shell - a stranger has nothing to launch."
}

# ---------------------------------------------------------------------------
# 2. Wait for the engine, then see the wall.

$deadline = (Get-Date).AddSeconds(600)
$engine = $null
while ((Get-Date) -lt $deadline -and -not $engine) {
    $engine = Get-ChildItem "C:\Users\WDAGUtilityAccount\AppData\Local" -Recurse `
        -Filter "engine.json" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $engine) { Start-Sleep -Seconds 5 }
}

if (-not $engine) {
    Say ""
    Say "NO engine.json AFTER TEN MINUTES. That is the wall and it is the result."
    Say ""
    Say "=== done ==="
    "done" | Out-File -Encoding utf8 (Join-Path $out "finished")
    exit
}

Say ""
Say "engine.json at $($engine.FullName)"
$cfg = Get-Content $engine.FullName -Raw | ConvertFrom-Json
$base = $cfg.base_url
$headers = @{}
if ($cfg.token) { $headers["Authorization"] = "Bearer " + $cfg.token }

function Ask($path) {
    try {
        $r = Invoke-WebRequest -Uri ($base + $path) -Headers $headers -UseBasicParsing -TimeoutSec 60
        "HTTP " + $r.StatusCode + "`n" + $r.Content
    } catch { "FAILED: " + $_.Exception.Message }
}

function Post($path, $body) {
    try {
        $h = $headers.Clone(); $h["Content-Type"] = "application/json"
        $r = Invoke-WebRequest -Uri ($base + $path) -Headers $h -Method POST `
             -Body ($body | ConvertTo-Json -Depth 8 -Compress) -UseBasicParsing -TimeoutSec 300
        "HTTP " + $r.StatusCode + "`n" + $r.Content
    } catch { "FAILED: " + $_.Exception.Message }
}

Run "GET /health" { Ask "/health" }
Run "GET /api/providers - THE WALL" { Ask "/api/providers" }

# ---------------------------------------------------------------------------
# 3. Do what the banner says. "Pick one on this machine" - so get one.

Run "get Ollama - the ZIP, not the installer" {
    # THE INSTALLER CANNOT BE DRIVEN AND THE ZIP NEEDS NO DRIVING.
    #
    # Measured 2026-09-10: OllamaSetup.exe ignored BOTH standard silent flag
    # families - /S (NSIS) and /VERYSILENT /NORESTART (Inno) - and each sat
    # alive past 240 seconds until killed, with ollama.exe never appearing. An
    # unattended installer with an unrecognised silent flag is a dialog nobody
    # will ever click, and from that I concluded "no automated walk on this
    # machine can pass it".
    #
    # THAT WAS THE FOURTH TIME IN A DAY I CALLED SOMETHING UNREACHABLE AND WAS
    # WRONG. Ollama publishes a standalone archive - no installer, no GUI, no
    # flag: unzip it and run ollama.exe. HTTP 200, checked before this was
    # written. A person on Windows would use the installer and click once; an
    # unattended walk uses this, and the thing being measured on the other side
    # - does the PRODUCT see and connect a local model - is identical either way.
    $url = "https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.zip"
    $zip = "C:/Users/WDAGUtilityAccount/Desktop/ollama.zip"
    $dir = "C:/Users/WDAGUtilityAccount/Desktop/ollama"
    $t0 = Get-Date
    try {
        & curl.exe -L --silent --show-error --max-time 1800 -o $zip $url 2>&1 | Out-Null
    } catch { "download FAILED: " + $_.Exception.Message }
    if (-not (Test-Path $zip)) {
        "NO ZIP after {0:N0}s - the download did not land" -f ((Get-Date)-$t0).TotalSeconds
    } else {
        "{0:N0} bytes in {1:N0}s" -f (Get-Item $zip).Length, ((Get-Date)-$t0).TotalSeconds
        try {
            Expand-Archive -Path $zip -DestinationPath $dir -Force
            $exe = Get-ChildItem -Path $dir -Recurse -Filter "ollama.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($exe) { "unzipped; ollama.exe at " + $exe.FullName }
            else { "UNZIPPED BUT THE ARCHIVE HAS NO ollama.exe" }
        } catch { "unzip FAILED: " + $_.Exception.Message }
    }
}

$found = Get-ChildItem -Path "C:/Users/WDAGUtilityAccount/Desktop/ollama" -Recurse -Filter "ollama.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
$ollama = if ($found) { $found.FullName } else { "C:/none/ollama.exe" }
Say ""
Say ("ollama.exe present: " + (Test-Path $ollama))

if (Test-Path $ollama) {
    Run "start the ollama server" {
        Start-Process -FilePath $ollama -ArgumentList "serve" -PassThru -WindowStyle Hidden |
            Select-Object -ExpandProperty Id | ForEach-Object { "serve pid $_" }
    }
    Start-Sleep -Seconds 10

    # THE SMALLEST MODEL THAT CAN HOLD A TURN. A stranger would pull something
    # bigger; this is a sandbox with no GPU, and the question being measured is
    # whether the product SEES and CONNECTS what the machine has - not how well
    # that model reasons.
    Run "pull a model" {
        $t0 = Get-Date
        & $ollama pull $model 2>&1 | Select-Object -Last 3
        "pull took {0:N0}s" -f ((Get-Date)-$t0).TotalSeconds
    }
    Run "ollama list" { & $ollama list 2>&1 }
}

# ---------------------------------------------------------------------------
# 4. Ask the PRODUCT what it can see now. This is the tool the connect dialog
#    calls to draw its list, so its answer is what a stranger would be shown.

Run "the product's own view: list_local_models" {
    Post "/api/tools/list_local_models" @{ args = @{} }
}

# ---------------------------------------------------------------------------
# 5. Connect it - create, activate, probe, which is what one click does.

# ---------------------------------------------------------------------------
# 5. Connect it the way ONE CLICK does: create, activate, probe. The earlier
#    version of this walk stopped after create and I wrote that it had "not
#    shown what a stranger sees when the probe fails". This shows it.

Run "POST /api/providers (create)" {
    Post "/api/providers" @{
        name = "Ollama"; base_url = "http://127.0.0.1:11434"
        model = $model; adapter = "ollama"
    }
}
Run "POST /api/providers/1/activate" { Post "/api/providers/1/activate" @{} }
Run "POST /api/providers/1/probe - does it call tools" { Post "/api/providers/1/probe" @{} }
Run "GET /api/providers (after connect)" { Ask "/api/providers" }

# ---------------------------------------------------------------------------
# 6. AND THE SENTENCE'S LAST CLAUSE: can this person be diagnosed?
#
#    The previous walk sent {goal=...} to POST /api/threads and got a 422. That
#    was MY request body, not the product: ThreadCreate takes `title`. The goal
#    is a separate door - POST /api/threads/{id}/goal - and the model is asked
#    through POST /api/threads/{id}/messages, whose role is always `user` and
#    is never read from the body.

Run "POST /api/threads (title)" {
    Post "/api/threads" @{ title = "Support tickets, answered like our team does" }
}
Run "POST /api/threads/1/goal - the person's own words" {
    Post "/api/threads/1/goal" @{ goal = "I have support tickets at C:/Users/WDAGUtilityAccount/Desktop/support-tickets.jsonl and I want the model to route them the way our team does." }
}
Run "POST /api/threads/1/messages - ask it" {
    Post "/api/threads/1/messages" @{ content = "I have support tickets at C:/Users/WDAGUtilityAccount/Desktop/support-tickets.jsonl and I want the model to route them the way our team does. Please look at the file." }
}

Run "POST /api/threads/1/turn - RUN THE DIAGNOSIS" {
    # THE MESSAGE DOOR RECORDS; THE TURN DOOR RUNS.
    #
    # The previous walk posted the question and waited 240 seconds for an answer
    # that was never going to come: POST /messages stores the person's words and
    # nothing else. `POST /api/threads/{id}/turn` is what asks the model, and
    # the UI calls it separately - client.ts's own comment names it.
    #
    # Its own timeout, not the shared 300s: a 0.5B model on a sandbox CPU with
    # tool calls is slow, and a walk that times out its own turn would report
    # "no answer" for a product that was mid-sentence.
    try {
        $h = $headers.Clone(); $h["Content-Type"] = "application/json"
        $t0 = Get-Date
        $r = Invoke-WebRequest -Uri ($base + "/api/threads/1/turn") -Headers $h `
             -Method POST -Body "{}" -UseBasicParsing -TimeoutSec 1500
        "HTTP " + $r.StatusCode + " after {0:N0}s`n" -f ((Get-Date)-$t0).TotalSeconds + $r.Content
    } catch {
        "FAILED after {0:N0}s: " -f ((Get-Date)-$t0).TotalSeconds + $_.Exception.Message
    }
}

# The turn is asynchronous. Give a 0.5B model on a sandbox CPU a fair while,
# and report what the thread holds whether or not it finished - a partial
# transcript is a result and a silent timeout is not.
Start-Sleep -Seconds 5
Run "keep turning until it stops or arrives" {
    # ONE TURN IS ONE TURN, NOT ONE CONVERSATION.
    #
    # The 7B walk ended with the model saying "let me proceed with proposing a
    # build" - a sentence that means the turn's budget ran out, not that the
    # thread was finished. I wrote that I would not claim a verdict I had not
    # read, and the way to read one is to keep turning.
    #
    # Bounded at four more turns: a walk that turns forever cannot distinguish
    # "still working" from "going in circles", and four is enough for the
    # remaining rungs if they are going to happen at all.
    for ($t = 1; $t -le 4; $t++) {
        try {
            $h = $headers.Clone(); $h["Content-Type"] = "application/json"
            $t0 = Get-Date
            $r = Invoke-WebRequest -Uri ($base + "/api/threads/1/turn") -Headers $h `
                 -Method POST -Body "{}" -UseBasicParsing -TimeoutSec 1500
            Say ("  turn {0}: HTTP {1} after {2:N0}s" -f $t, $r.StatusCode, ((Get-Date)-$t0).TotalSeconds)
        } catch {
            Say ("  turn {0}: FAILED after {1:N0}s - {2}" -f $t, ((Get-Date)-$t0).TotalSeconds, $_.Exception.Message)
            break
        }
    }
    "four more turns attempted"
}

Run "GET /api/threads/1/journey - the gates and the verdict" { Ask "/api/threads/1/journey" }

Run "did any tool actually run - from the thread, not the stream" {
    # THE CHECK THAT SAID NO WAS ASKING AN ENDPOINT THAT COULD NOT ANSWER.
    #
    # The previous version called GET /api/events?after=0 and printed "NO tool
    # events in the stream". That route REQUIRES a `scope` parameter, names its
    # cursor `since` and not `after`, and returns server-sent events rather
    # than JSON - so the request 422d, the regex found nothing in the error
    # body, and the absence was reported as a finding. The thread record
    # contradicted it in the very next block: tool_calls_json carried a real
    # call to read_context_file.
    #
    # A check that cannot tell "no tools ran" from "my request was malformed"
    # reports the first. So this one reads the THREAD - plain JSON, no scope,
    # no stream - and REFUSES TO CONCLUDE unless it got an HTTP 200 first.
    $r = Ask "/api/threads/1"
    if ($r -notmatch "^HTTP 200") { "CANNOT SAY: the thread did not answer 200, so absence proves nothing`n" + $r }
    else {
        $calls = [regex]::Matches($r, '\\"name\\": \\"([a-z_]+)\\"') | ForEach-Object { $_.Groups[1].Value }
        if ($calls) { "TOOLS CALLED: " + (($calls | Group-Object | ForEach-Object { $_.Name + " x" + $_.Count }) -join ", ") }
        elseif ($r -match 'tool_calls_json\\":null') { "no tool calls recorded on any message (thread answered 200)" }
        else { "CANNOT SAY: no tool_calls_json field found at all" }
    }
}

Run "GET /api/threads/1 - what the walk reached" { Ask "/api/threads/1" }
Run "GET /api/threads" { Ask "/api/threads" }
Say ""
Say "=== done ==="
"done" | Out-File -Encoding utf8 (Join-Path $out "finished")
