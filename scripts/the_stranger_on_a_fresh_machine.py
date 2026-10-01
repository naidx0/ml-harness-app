"""What a stranger gets from the public four-asserts, on a machine with nothing.

    python scripts/the_stranger_on_a_fresh_machine.py

Windows Sandbox again, and two differences from the one-click run that are worth
stating because they change what the answer means.

**Networking is ON here, and it was off there.** The one-click check had to work
with no network, so proving that was part of the point. Installing from GitHub
cannot, so this run has a network and says so.

**The repository is NOT mapped in.** The whole question is what somebody gets
who has never had a checkout, so the only things on that machine are a Python
interpreter, one script, and a connection.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
IN = REPO / "scripts" / "fresh-machine-in"
OUT = REPO / "scripts" / "fresh-machine-out"
DESKTOP = Path("C:/Users/WDAGUtilityAccount/Desktop")
INTERPRETER = (
    Path(os.environ.get("LOCALAPPDATA", "")).parent
    / "Roaming" / "uv" / "python" / "cpython-3.11-windows-x86_64-none"
)

WSB = """<Configuration>
  <VGpu>Disable</VGpu>
  <Networking>Default</Networking>
  <MappedFolders>
    <MappedFolder><HostFolder>{scripts}</HostFolder><SandboxFolder>{desk_in}</SandboxFolder><ReadOnly>true</ReadOnly></MappedFolder>
    <MappedFolder><HostFolder>{python}</HostFolder><SandboxFolder>{desk_python}</SandboxFolder><ReadOnly>true</ReadOnly></MappedFolder>
    <MappedFolder><HostFolder>{out}</HostFolder><SandboxFolder>{desk_out}</SandboxFolder><ReadOnly>false</ReadOnly></MappedFolder>
  </MappedFolders>
  <LogonCommand><Command>powershell -NoProfile -ExecutionPolicy Bypass -File {desk_in}\\stranger.ps1</Command></LogonCommand>
</Configuration>
"""


def a_sandbox_is_open() -> bool:
    running = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-Process -Name 'WindowsSandboxServer' -ErrorAction SilentlyContinue | Measure-Object).Count"],
        capture_output=True, text=True, timeout=120,
    ).stdout.strip()
    return running.isdigit() and int(running) > 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wait", type=int, default=600)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    exe = Path(os.environ.get("WINDIR", "C:/Windows")) / "System32" / "WindowsSandbox.exe"
    if not exe.exists() or not INTERPRETER.exists():
        print("NOT RUN: no sandbox or no interpreter to map", file=sys.stderr)
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    for stale in list(OUT.glob("stranger.txt")) + list(OUT.glob("finished")):
        stale.unlink()

    config = OUT / "stranger.wsb"
    config.write_text(
        WSB.format(scripts=IN, python=INTERPRETER, out=OUT,
                   desk_in=DESKTOP / "in", desk_python=DESKTOP / "python",
                   desk_out=DESKTOP / "out"),
        encoding="utf-8",
    )
    print(f"wrote {config}")
    if a_sandbox_is_open():
        print("NOT RUN: a Windows Sandbox is already open; close it first", file=sys.stderr)
        return 2

    # PARSED BEFORE IT IS LAUNCHED. A script with a syntax error produces no
    # output at all inside the sandbox, and the caller then waits out its whole
    # timeout for a page that was never going to be written - measured: nine
    # minutes for a statement list inside a cast on line 29. A wait that cannot
    # succeed should say why.
    checked = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "$e=$null; $null=[System.Management.Automation.Language.Parser]::ParseFile("
         f"'{IN / 'stranger.ps1'}',[ref]$null,[ref]$e); "
         "if($e){ $e | ForEach-Object { 'LINE ' + $_.Extent.StartLineNumber + ': ' + $_.Message } }"],
        capture_output=True, text=True, timeout=180,
    ).stdout.strip()
    if checked:
        print("NOT RUN: the sandbox script does not parse:", file=sys.stderr)
        print(checked, file=sys.stderr)
        return 2

    subprocess.Popen([str(exe), str(config)])
    print("sandbox starting; waiting for the page", flush=True)
    finished = OUT / "finished"
    began = time.time()
    while time.time() - began < args.wait:
        if finished.exists():
            page = (OUT / "stranger.txt").read_text(encoding="utf-8-sig", errors="replace")
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            print(f"the sandbox answered after {time.time() - began:.0f}s")
            print()
            print(page)
            return 0
        time.sleep(5)
    print(f"no page after {args.wait}s", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
