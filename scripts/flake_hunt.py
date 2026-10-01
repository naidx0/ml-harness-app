#!/usr/bin/env python3
"""Run the suite repeatedly and capture the output of any run that fails.

Written after a single unreproducible failure. The mistake that made it
unreproducible was re-running the suite to "see the error" - which started a
fresh run that passed, discarding the only evidence there was. This runs the
suite N times and writes the FULL output of the first failing run to a file, so
the next occurrence is evidence rather than a memory.

Usage:
    python scripts/flake_hunt.py            # 10 runs, warm bytecode
    python scripts/flake_hunt.py -n 30      # 30 runs
    python scripts/flake_hunt.py --cold     # clear __pycache__ before each run
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REPORT = REPO / "flake-report.txt"


def clear_bytecode() -> None:
    for cache in REPO.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def run_once() -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests"],
        cwd=REPO, capture_output=True, text=True, timeout=600, check=False,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-n", "--runs", type=int, default=10)
    parser.add_argument("--cold", action="store_true",
                        help="clear __pycache__ before every run")
    args = parser.parse_args()

    for attempt in range(1, args.runs + 1):
        if args.cold:
            clear_bytecode()
        ok, output = run_once()
        print(f"  run {attempt:>3}/{args.runs}  {'ok' if ok else 'FAILED'}", flush=True)
        if not ok:
            REPORT.write_text(
                f"flake caught {datetime.now():%Y-%m-%d %H:%M:%S} "
                f"on run {attempt} of {args.runs} "
                f"({'cold' if args.cold else 'warm'})\n\n{output}",
                encoding="utf-8",
            )
            print(f"\n  captured to {REPORT.name}")
            # Print the useful lines immediately - the whole point is not
            # needing a second run to find out what broke.
            for line in output.splitlines():
                if line.startswith(("FAIL:", "ERROR:", "AssertionError",
                                    "Ran ", "FAILED")):
                    print(f"    {line}")
            return 1

    print(f"\n  {args.runs} clean runs, no flake reproduced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
