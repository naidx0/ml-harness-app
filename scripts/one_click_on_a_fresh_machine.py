"""Run the one-click check inside Windows Sandbox, which is a fresh machine.

    python scripts/one_click_on_a_fresh_machine.py

WHY A SANDBOX AND NOT A RUNNER. A CI runner is a fresh machine, which is most of
it, and it has a curated toolchain: Python, a driver stack, sometimes a GPU.
Windows Sandbox boots clean every time - no Python, no runtime, no models, no
`%LOCALAPPDATA%` belonging to this product, no repository - and is thrown away
on close. That is the machine the check's audience is actually sitting at.

WHAT IS MAPPED IN, AND IT IS THE HONEST PART OF THE ANSWER. Three folders, all
read-only: the repository, a Python interpreter, and a place to write the page.
**A fresh Windows machine has no Python, and the check is a Python program**, so
the check cannot be the literal first thing anybody runs. Mapping the
interpreter says that out loud rather than hiding it behind an installer that
would also have to be built. What is NOT mapped is anything the check reports
on: no models, no runtime, no lock, no card.

WHAT IT CANNOT SHOW. Whether a person UNDERSTANDS the page. That stays a thing a
human does, and this measures the mechanical half.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "scripts" / "fresh-machine-out"
SANDBOX_DESKTOP = Path("C:/Users/WDAGUtilityAccount/Desktop")

#: A CPython that runs from a folder, mapped rather than installed. Chosen over
#: downloading one inside the sandbox because a download makes the run depend on
#: a network and on whatever the latest release happens to be, and neither is
#: part of the question being asked.
INTERPRETER = Path(
    os.environ.get("LOCALAPPDATA", "")
).parent / "Roaming" / "uv" / "python" / "cpython-3.11-windows-x86_64-none"

WSB = """<Configuration>
  <VGpu>Disable</VGpu>
  <Networking>Disable</Networking>
  <MappedFolders>
    <MappedFolder><HostFolder>{repo}</HostFolder><SandboxFolder>{desk_repo}</SandboxFolder><ReadOnly>true</ReadOnly></MappedFolder>
    <MappedFolder><HostFolder>{python}</HostFolder><SandboxFolder>{desk_python}</SandboxFolder><ReadOnly>true</ReadOnly></MappedFolder>
    <MappedFolder><HostFolder>{out}</HostFolder><SandboxFolder>{desk_out}</SandboxFolder><ReadOnly>false</ReadOnly></MappedFolder>
  </MappedFolders>
  <LogonCommand><Command>{command}</Command></LogonCommand>
</Configuration>
"""


def the_command(desk_repo: Path, desk_python: Path, desk_out: Path) -> str:
    """What runs at logon: the check, and a note of what the machine had."""
    page = desk_out / "page.txt"
    interpreter = desk_python / "python.exe"
    # One line, because a LogonCommand is one command. Semicolons rather than
    # a script file so that what ran is visible in the .wsb itself.
    return (
        "powershell -NoProfile -Command "
        f"\"cd '{desk_repo}'; "
        f"'--- what this machine has ---' | Out-File -Encoding utf8 '{page}'; "
        f"('python on PATH: ' + [bool](Get-Command python -ErrorAction SilentlyContinue)) | Out-File -Append -Encoding utf8 '{page}'; "
        f"('ollama on PATH: ' + [bool](Get-Command ollama -ErrorAction SilentlyContinue)) | Out-File -Append -Encoding utf8 '{page}'; "
        f"('nvidia-smi on PATH: ' + [bool](Get-Command nvidia-smi -ErrorAction SilentlyContinue)) | Out-File -Append -Encoding utf8 '{page}'; "
        f"'' | Out-File -Append -Encoding utf8 '{page}'; "
        f"'--- the page ---' | Out-File -Append -Encoding utf8 '{page}'; "
        f"& '{interpreter}' scripts/one_click_check.py 2>&1 | Out-File -Append -Encoding utf8 '{page}'; "
        f"('EXIT ' + $LASTEXITCODE) | Out-File -Append -Encoding utf8 '{page}'; "
        f"'done' | Out-File -Encoding utf8 '{desk_out / 'finished'}'\""
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write-only", action="store_true")
    parser.add_argument("--wait", type=int, default=300, help="seconds to wait for the page")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    exe = Path(os.environ.get("WINDIR", "C:/Windows")) / "System32" / "WindowsSandbox.exe"
    if not INTERPRETER.exists():
        print(f"no interpreter to map at {INTERPRETER}", file=sys.stderr)
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*"):
        # A previous run's page sitting beside a failed one is how somebody
        # reads last week's answer as this one's.
        if stale.is_file():
            stale.unlink()

    desk_repo = SANDBOX_DESKTOP / "repo"
    desk_python = SANDBOX_DESKTOP / "python"
    desk_out = SANDBOX_DESKTOP / "out"
    config = OUT / "one-click.wsb"
    config.write_text(
        WSB.format(
            repo=REPO,
            python=INTERPRETER,
            out=OUT,
            desk_repo=desk_repo,
            desk_python=desk_python,
            desk_out=desk_out,
            command=the_command(desk_repo, desk_python, desk_out).replace("&", "&amp;"),
        ),
        encoding="utf-8",
    )
    print(f"wrote {config}")
    if args.write_only:
        return 0
    if not exe.exists():
        print(f"NOT RUN: {exe} is not on this machine", file=sys.stderr)
        return 2

    # ONE SANDBOX AT A TIME, and a second launch against a running one does
    # nothing at all. Measured: a run waited the full 420 seconds for a page
    # that could never be written, because the previous sandbox was still open.
    # A wait that cannot succeed should say why rather than time out.
    running = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-Process -Name 'WindowsSandboxServer' -ErrorAction SilentlyContinue "
         "| Measure-Object).Count"],
        capture_output=True, text=True, timeout=120,
    ).stdout.strip()
    if running.isdigit() and int(running) > 0:
        print(
            "NOT RUN: a Windows Sandbox is already open, and a second one cannot "
            "start beside it. Close it and run this again.",
            file=sys.stderr,
        )
        return 2

    subprocess.Popen([str(exe), str(config)])
    print("sandbox starting; waiting for the page", flush=True)
    finished = OUT / "finished"
    began = time.time()
    while time.time() - began < args.wait:
        if finished.exists():
            print(f"the sandbox answered after {time.time() - began:.0f}s")
            print()
            # `utf-8-sig`, and printed through a writer that cannot fail on
            # what the sandbox wrote. PowerShell's -Encoding utf8 emits a BOM,
            # and printing it to a cp1252 console raises - which made a run
            # that had SUCCEEDED look like a crash, twice, before anyone read
            # the file it had just written.
            page = (OUT / "page.txt").read_text(encoding="utf-8-sig", errors="replace")
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            print(page)
            return 0
        time.sleep(5)
    print(f"no page after {args.wait}s; the sandbox may still be booting", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
