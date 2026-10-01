"""G-types for the Solid frontend: this product's code is clean, and the vendored
tree has no errors beyond a recorded baseline.

    python scripts/check_web_types.py            # check
    python scripts/check_web_types.py --record   # rewrite the baseline (review the diff!)

WHY A BASELINE AND NOT ZERO. The type checker follows imports into OpenCode's
vendored source, and fourteen errors there cannot be fixed from this side:

  - twelve are callback parameters on surfaces this product never mounts - the
    Electron browser pane and the terminal - whose packages are deliberately
    not installed. Their shims are loosely typed, so the callbacks have no
    contextual type. Modelling a never-mounted API faithfully would be
    precision with nothing to protect.
  - two are upstream calling `onExpansionChange` on @pierre/trees, a property
    that exists in NO published release (beta.4, .5 and .6 all checked). That
    is their code ahead of their dependency, not drift introduced here.

Editing their files would break byte-identity with the pinned commit, which is
the property that makes an upstream diff possible. So the rule is the one the
plan states for G-types: no regressions.

  1. ZERO errors under web/src. That is this product's code and it has no
     baseline - one error there fails the check.
  2. No vendored error outside the baseline. A new one fails.
  3. A baseline entry that no longer occurs ALSO fails, loudly. Otherwise the
     baseline only ever grows in tolerance, and a fixed error leaves a slot a
     future regression can hide in.

Entries are keyed by file, error code and message - not line number - so a
re-vendor that shifts lines does not churn the baseline, while a genuinely new
error still shows up as new.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WEB = REPO / "web"
BASELINE = WEB / "tsc-baseline.txt"

ERROR = re.compile(r"^(?P<file>[^(]+)\(\d+,\d+\): error (?P<code>TS\d+): (?P<message>.*)$")


def run_tsc() -> tuple[int, list[str]]:
    npx = "npx.cmd" if sys.platform == "win32" else "npx"
    done = subprocess.run(
        [npx, "tsc", "-p", "tsconfig.json", "--noEmit"],
        cwd=WEB, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return done.returncode, (done.stdout + done.stderr).splitlines()


def key(line: str) -> str | None:
    match = ERROR.match(line.strip())
    if not match:
        return None
    file = match["file"].replace("\\", "/")
    return f"{file} {match['code']} {match['message'].strip()}"


def main() -> int:
    code, lines = run_tsc()
    keys = [k for k in (key(line) for line in lines) if k]
    unparsed = [line for line in lines if "error TS" in line and not key(line)]

    ours = [k for k in keys if k.startswith("src/")]
    theirs = Counter(k for k in keys if not k.startswith("src/"))

    if "--record" in sys.argv:
        if ours:
            print("REFUSING TO RECORD: this product's own code has errors, and they are")
            print("never baselined. Fix them first:")
            for k in ours:
                print("  " + k)
            return 1
        BASELINE.write_text(
            "".join(f"{count} {k}\n" for k, count in sorted(theirs.items())),
            encoding="utf-8",
            newline=chr(10),
        )
        print(f"recorded {sum(theirs.values())} vendored errors in {BASELINE.name}")
        return 0

    baseline: Counter[str] = Counter()
    if BASELINE.exists():
        for raw in BASELINE.read_text(encoding="utf-8").splitlines():
            if raw.strip():
                count, _, k = raw.partition(" ")
                baseline[k] = int(count)

    failures: list[str] = []
    if unparsed:
        # An error line this script cannot read is an error it cannot judge -
        # e.g. a config error with no file prefix. It fails rather than passes.
        failures += [f"UNREADABLE: {line.strip()}" for line in unparsed]
    failures += [f"OURS: {k}" for k in ours]
    for k, count in (theirs - baseline).items():
        failures.append(f"NEW VENDORED ({count}): {k}")
    for k, count in (baseline - theirs).items():
        failures.append(f"GONE FROM BASELINE ({count}) - re-record so the slot cannot hide a regression: {k}")

    if code != 0 and not keys and not unparsed:
        failures.append("tsc exited non-zero and printed no errors - the checker did not run")

    if failures:
        print("G-types FAILED")
        for line in failures:
            print("  " + line)
        return 1
    print(f"G-types ok: 0 errors in web/src, {sum(theirs.values())} vendored errors, all in the baseline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
