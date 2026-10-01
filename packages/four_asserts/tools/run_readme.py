"""Run every ```python block in the README, verbatim, and fail on any of them.

    python tools/run_readme.py README.md
    python tools/run_readme.py README.md --plant   # prove it can go red

WHY THIS EXISTS. Two of the four usages in this README did not work. One passed
an absolute POSIX path on a package with Windows-specific code in the very
module it was demonstrating, and one read a file that was not there. Both were
found by a person on a fresh machine typing them in, which is the worst way to
learn it and the only way that was available.

A README is documentation until something runs it; after that it is a test that
happens to be readable. So these blocks run on every push, on both the oldest
Python this package claims and the newest, and a non-zero exit from any of them
fails the build.

VERBATIM MEANS VERBATIM. No preamble is added, no names are injected, nothing is
wrapped. If a block needs a file to exist, the block has to make it exist - and
the discipline that forces is the point: an example that cannot run on its own
is an example a reader cannot run either.

WHAT IT DOES NOT DO. It does not check that the prose around a block is true.
Only the blocks are executable, and the sentences remain a thing a person reads.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

FENCE = re.compile(r"```python\n(.*?)```", re.S)

#: A usage line that is wrong in the way the real ones were wrong: it names a
#: path that is not there. Appended to a COPY of the README by `--plant`, never
#: to the README itself.
A_WRONG_BLOCK = """
```python
from four_asserts import witness
witness("a-file-that-is-not-here.jsonl")
```
"""


def blocks(text: str) -> list[str]:
    return [b for b in FENCE.findall(text) if b.strip()]


def run(block: str, where: Path, number: int) -> int:
    script = where / f"block_{number}.py"
    script.write_text(block, encoding="utf-8")
    print(f"--- block {number} ---", flush=True)
    print(block.rstrip(), flush=True)
    done = subprocess.run([sys.executable, str(script)], cwd=where)
    print(f"  -> exit {done.returncode}", flush=True)
    return done.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("readme", nargs="?", default="README.md")
    parser.add_argument(
        "--plant",
        action="store_true",
        help="append a deliberately wrong block to a COPY and require a failure",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    text = Path(args.readme).read_text(encoding="utf-8")
    if args.plant:
        text += A_WRONG_BLOCK

    found = blocks(text)
    if not found:
        # A runner that finds nothing passes, and a passing check that ran
        # nothing is the failure this whole package is about.
        print("no ```python blocks found - the README changed shape", file=sys.stderr)
        return 2
    print(f"{len(found)} python block(s) in {args.readme}", flush=True)

    with tempfile.TemporaryDirectory() as tmp:
        where = Path(tmp)
        # Copied in so a block may read a file that ships with the package
        # without reaching outside the directory it runs in.
        for name in ("pyproject.toml", "README.md"):
            source = Path(name)
            if source.exists():
                (where / name).write_bytes(source.read_bytes())
        bad = [n for n, block in enumerate(found, 1) if run(block, where, n) != 0]

    if args.plant:
        if bad:
            print(f"\nPLANTED BLOCK CAUGHT: block(s) {bad} failed, as they must.")
            return 0
        print("\nTHE PLANTED BLOCK PASSED. This runner cannot go red, so a green "
              "result from it means nothing.", file=sys.stderr)
        return 1

    if bad:
        print(f"\nRED: block(s) {bad} of {len(found)} exited non-zero.", file=sys.stderr)
        return 1
    print(f"\nGREEN: {len(found)} of {len(found)} blocks ran.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
