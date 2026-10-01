"""What a stranger gets from the INSTALLER, on a machine with nothing.

    python scripts/the_stranger_installs_the_harness.py

`docs/PHASES.md` Phase 5 is done when *"somebody who has never seen the
repository gets from zero to a diagnosed problem without asking a question."*
The install half was measured in `THE_PLAN.md` C.d.4 — silent install, an engine
in 16 seconds, a clean uninstall — **on the machine that built it**, which has
the checkout, the model cache and a developer's PATH. This runs it where none of
that is true.

The sibling `the_stranger_on_a_fresh_machine.py` does the same thing for
`four-asserts`, the library lifted out of this repository. This is the harness's
own, and the difference is what is mapped in: **the installer and nothing else.**

## What this can and cannot answer

It can answer *does the installer work on a machine that has never seen this
project* — files land where the first run looks, the shell starts, the engine
publishes itself, `/health` answers.

**It cannot answer the whole Phase 5 sentence**, and that is deliberate rather
than a gap in the script. A diagnosis needs a connected model; a fresh sandbox
has no Ollama, no key and no cache. So the run reports exactly where a stranger
stops, and *"they install it and then cannot do anything"* is the finding if it
is the finding.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
IN = REPO / "scripts" / "fresh-machine-in"
OUT = REPO / "scripts" / "fresh-machine-out"
DESKTOP = Path("C:/Users/WDAGUtilityAccount/Desktop")

#: Built by `cargo tauri build`. Named here rather than globbed so a missing
#: installer is a refusal with a path in it rather than a confusing empty run.
INSTALLER = (
    REPO / "src-tauri" / "target" / "release" / "bundle" / "nsis"
    / "ML Harness_0.1.0_x64-setup.exe"
)

#: NETWORKING IS ON. The installed copy's first run has `uv` build a Python
#: environment and install the product wheel into it, which needs the network.
#: Turning it off would measure a different product.
WSB = """<Configuration>
  <Networking>Default</Networking>
  <MappedFolders>
    <MappedFolder><HostFolder>{inbox}</HostFolder><SandboxFolder>{desk_in}</SandboxFolder><ReadOnly>true</ReadOnly></MappedFolder>
    <MappedFolder><HostFolder>{out}</HostFolder><SandboxFolder>{desk_out}</SandboxFolder><ReadOnly>false</ReadOnly></MappedFolder>
  </MappedFolders>
  <LogonCommand><Command>powershell -NoProfile -ExecutionPolicy Bypass -File {desk_in}\\{script}</Command></LogonCommand>
</Configuration>
"""


#: The lab's shared sandbox lock, ruled 2026-09-10 after two of this lane's runs
#: died mid-download. THE CAUSE WAS NOT THE DOWNLOAD OR THE VM: another lane hit
#: a launch collision and cleared it with `Stop-Process` on
#: `WindowsSandboxServer` - a MACHINE-WIDE service - which killed a sandbox it
#: could not see. Neither lane could see the other, which is the whole argument
#: for a lock rather than for either lane being more careful.
NEWLINE = chr(10)

def _sandbox_lock() -> Path:
    """`sandbox.lock`, beside `gpu.lock`, wherever that turns out to be.

    ASKED FOR, NOT SPELLED OUT. The first version of this pasted a real home
    directory and the name of a private note vault into a file that ships, and
    `test_no_shipped_file_names_a_person` refused the commit - correctly, and it
    was a lock line meant to stop lanes colliding that would have published
    where somebody's notes live.

    `card_owner/the_lock.py` already resolves that directory for `gpu.lock`, and
    the ruling puts this one beside it, so this asks that module rather than
    restating what it knows. Two definitions of one directory is how they drift;
    one of them being in a shipped file is how a private path escapes.

    `MLH_SANDBOX_LOCK` overrides, for a machine arranged differently and for the
    tests.
    """
    named = os.environ.get("MLH_SANDBOX_LOCK")
    if named:
        return Path(named)
    sys.path.insert(0, str(REPO))
    from card_owner.the_lock import THE_LOCK

    return THE_LOCK.parent / "sandbox.lock"


SANDBOX_LOCK = _sandbox_lock()


def a_sandbox_is_open() -> bool:
    """Is a sandbox VM resident on this machine?

    `vmmemWindowsSandbox` AND NOT `WindowsSandbox.exe`, because the two answer
    different questions and the second lies at exactly the wrong moment: the
    window process exits while the VM is still shutting down, so a run launched
    on its absence lands on a machine that still has one. Measured today - 0
    windows, 1 vmmem, and a dead run."""
    for image in ("vmmemWindowsSandbox.exe", "WindowsSandbox.exe"):
        try:
            done = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {image}"],
                capture_output=True, text=True, timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if image.split(".")[0].lower() in done.stdout.lower():
            return True
    return False


def clients_older_than_now() -> list[str]:
    """Sandbox CLIENTS already running, named with their start times.

    A KILLED RUN HAUNTS THE NEXT ONE, measured 2026-09-10. A
    `WindowsSandboxRemoteSession.exe` whose VM is ended under it RE-CREATES the
    VM when it reconnects, so a client orphaned by a collided run keeps
    launching sandboxes every few minutes with nobody at a keyboard. Hyper-V's
    worker log showed EIGHT VMs in thirty minutes and this lane read them as
    other lanes colliding, asked another lane to change its behaviour, and was
    wrong: the launcher was its own debris. The cadence stopped by itself when
    the orphans exited.

    So a run that starts while clients already exist refuses and NAMES them,
    rather than adding a ninth VM to a machine that is already relaunching. The
    server process is never touched - it is machine-wide, and stopping it is
    what ended two runs it could not see.
    """
    script = (
        "Get-Process -Name WindowsSandboxRemoteSession -ErrorAction SilentlyContinue | "
        "ForEach-Object { $_.Id.ToString() + ' started ' + $_.StartTime.ToString('HH:mm:ss') }"
    )
    try:
        done = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.strip() for line in done.stdout.splitlines() if line.strip()]


def take_the_sandbox(what: str) -> str:
    """Write the lock line, in the shape `gpu.lock` uses. Returns the line."""
    import datetime
    import socket

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = (f"lane=mlbuild host={socket.gethostname()} since={now} "
            f"pid={os.getpid()} born={now} what={what}")
    SANDBOX_LOCK.parent.mkdir(parents=True, exist_ok=True)
    SANDBOX_LOCK.write_text(line + NEWLINE, encoding="utf-8")
    with open(SANDBOX_LOCK.parent / "sandbox.lock.log", "a", encoding="utf-8") as log:
        log.write("TAKE     " + line + NEWLINE)
    return line


def release_the_sandbox() -> None:
    """Remove the lock and append the release line. Never raises.

    In a `finally`, because a lock a crash leaves behind stops every other lane
    and the next one cannot tell a held lock from an abandoned one."""
    try:
        line = (SANDBOX_LOCK.read_text(encoding="utf-8").strip()
                if SANDBOX_LOCK.exists() else "")
        SANDBOX_LOCK.unlink(missing_ok=True)
        with open(SANDBOX_LOCK.parent / "sandbox.lock.log", "a", encoding="utf-8") as log:
            log.write("RELEASE  " + line + NEWLINE)
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wait", type=int, default=900)
    # WHICH STRANGER. `harness-stranger.ps1` stops at the wall and reports it,
    # which was the right script while the wall was the finding. `--all-the-way`
    # runs the one that does what the banner tells the person to do - install a
    # model - because "a sandbox has no Ollama" is a fact about the sandbox at
    # boot, not a fact about what a stranger can reach from it.
    parser.add_argument(
        "--all-the-way", action="store_true",
        help="install Ollama and a model inside the sandbox and drive the whole "
             "Phase 5 sentence, rather than stopping at the empty provider list",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    exe = Path(os.environ.get("WINDIR", "C:/Windows")) / "System32" / "WindowsSandbox.exe"
    if not exe.exists():
        print("NOT RUN: Windows Sandbox is not installed on this machine.", file=sys.stderr)
        return 2
    if not INSTALLER.exists():
        print(f"NOT RUN: no installer at {INSTALLER}.", file=sys.stderr)
        print("Build it with `cargo tauri build` in src-tauri/ first.", file=sys.stderr)
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    for stale in ("harness-stranger.txt", "finished"):
        target = OUT / stale
        if target.exists():
            target.unlink()

    # THE INSTALLER IS COPIED IN UNDER A NAME WITH NO SPACES. A mapped path with
    # a space in it is a quoting problem waiting to happen inside a sandbox
    # script nobody can debug interactively.
    staged = IN / "ML-Harness-setup.exe"
    shutil.copy2(INSTALLER, staged)
    print(f"staged {INSTALLER.name} ({staged.stat().st_size:,} bytes) as {staged.name}")

    config = OUT / "harness-stranger.wsb"
    script = ("harness-stranger-all-the-way.ps1" if args.all_the_way
              else "harness-stranger.ps1")
    config.write_text(
        WSB.format(inbox=IN, out=OUT, desk_in=DESKTOP / "in",
                   desk_out=DESKTOP / "out", script=script),
        encoding="utf-8",
    )
    print(f"driving {script}")
    print(f"wrote {config}")

    # BUSY AND OWNER ARE DIFFERENT QUESTIONS AND BOTH GET ASKED. A resident VM
    # says the machine is busy; the lock says WHOSE it is. Refusing on the first
    # without reporting the second is what left another lane with nothing to do
    # but kill a machine-wide service, which ended two of this lane's runs.
    if a_sandbox_is_open():
        held = (SANDBOX_LOCK.read_text(encoding="utf-8").strip()
                if SANDBOX_LOCK.exists() else "no lock file - owner unknown")
        print("NOT RUN: a Windows Sandbox VM is resident on this machine.", file=sys.stderr)
        print(f"  held by: {held}", file=sys.stderr)
        print("  DO NOT Stop-Process WindowsSandboxServer - it is machine-wide "
              "and ends every lane's sandbox.", file=sys.stderr)
        return 2
    stale = clients_older_than_now()
    if stale:
        print("NOT RUN: a Windows Sandbox client is already running, and a client "
              "whose VM was ended under it RE-LAUNCHES one every few minutes:",
              file=sys.stderr)
        for line in stale:
            print(f"  WindowsSandboxRemoteSession {line}", file=sys.stderr)
        print("  End those clients before running. Do NOT stop "
              "WindowsSandboxServer - it is machine-wide.", file=sys.stderr)
        return 2
    if SANDBOX_LOCK.exists():
        print("NOT RUN: no VM is resident but the lock is held:", file=sys.stderr)
        print(f"  {SANDBOX_LOCK.read_text(encoding='utf-8').strip()}", file=sys.stderr)
        print("  A stale lock is its owner's decision, not this lane's.", file=sys.stderr)
        return 2

    # PARSED BEFORE IT IS LAUNCHED, which the sibling script learned the hard
    # way: a PowerShell syntax error produces no output at all inside the
    # sandbox, and the caller then waits out its entire timeout for a page that
    # was never going to be written.
    checked = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "$e=$null; $null=[System.Management.Automation.Language.Parser]::ParseFile("
         f"'{IN / script}',[ref]$null,[ref]$e); "
         "if($e){ $e | ForEach-Object { 'LINE ' + $_.Extent.StartLineNumber + ': ' + $_.Message } }"],
        capture_output=True, text=True, timeout=180,
    ).stdout.strip()
    if checked:
        print("NOT RUN: the sandbox script does not parse:", file=sys.stderr)
        print(checked, file=sys.stderr)
        return 2

    lock_line = take_the_sandbox(f"phase 5 stranger walk, {script}, wait {args.wait}s")
    print(f"sandbox.lock: {lock_line}")
    print("launching Windows Sandbox - a window will open and close itself")

    page, marker = OUT / "harness-stranger.txt", OUT / "finished"
    try:
        subprocess.Popen([str(exe), str(config)])
        deadline = time.monotonic() + args.wait
        while time.monotonic() < deadline and not marker.exists():
            time.sleep(5)
    finally:
        # REAP WHAT THIS RUN STARTED, then release. A finished walk leaves its
        # `WindowsSandboxRemoteSession.exe` alive, and that client is exactly
        # what `clients_older_than_now()` refuses on - so a SUCCESSFUL run used
        # to block the next one, and the guard looked like a bug in itself.
        # Measured 2026-09-10: the walk completed at 16:36, its client was still
        # there at 16:45, and the next launch was refused naming it.
        #
        # The client is ended and not the server: the server is machine-wide,
        # and stopping it is what killed two runs it could not see.
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-Process -Name WindowsSandboxRemoteSession "
                 "-ErrorAction SilentlyContinue | Stop-Process -Force"],
                capture_output=True, timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            pass
        release_the_sandbox()

    # THE VERDICT BEFORE THE DUMP, AND THE DUMP MADE UNKILLABLE.
    #
    # This printed the page first and said whether the run finished second.
    # Measured 2026-09-10: PowerShell writes the page as UTF-8 WITH A BOM,
    # `print` encodes it to the console's cp1252, and `﻿` is not in cp1252 -
    # so the process died with a UnicodeEncodeError on the FIRST character, one
    # line before the sentence saying the run did not finish. The caller got a
    # traceback and no verdict, and a sandbox that stopped halfway looked exactly
    # like one that completed.
    #
    # That is this project's recurring defect wearing the tooling's clothes: a
    # report whose failure branch sits behind an unrelated crash cannot
    # distinguish "did not finish" from "finished". So the verdict goes first,
    # and the page is written through a byte path that cannot raise on any
    # console encoding.
    finished = marker.exists()
    if not finished:
        print(f"NOT FINISHED within {args.wait}s - the page below is PARTIAL, "
              "and its last line is where the sandbox stopped.", file=sys.stderr)
    if page.exists():
        text = page.read_text(encoding="utf-8-sig", errors="replace")
        sys.stdout.buffer.write(text.encode("utf-8", "replace") + b"\n")
        sys.stdout.flush()
    return 0 if finished else 1


if __name__ == "__main__":
    raise SystemExit(main())
