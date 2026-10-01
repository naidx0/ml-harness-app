"""What we vendored, what we changed, and whether either has moved since.

    python scripts/the_vendored_copy.py                  # check the tree against the record
    python scripts/the_vendored_copy.py --upstream       # compare with the published repo
    python scripts/the_vendored_copy.py --record <sha>   # write the record (a person does this)

## The problem, measured rather than feared

`packages/four_asserts` is a **copy**. No submodule, no subtree, no nested
`.git` - plain vendored files whose `pyproject.toml` names
`Source = https://github.com/naidx0/four-asserts`. Cloning that repository and
diffing it against this tree as it stood at `18fc9dc`:

* **11 files identical**, including every module the harness imports
* **README.md 84 lines apart**
* **`tools/run_readme.py` absent from the copy entirely**

The code agreed. The documentation and the tooling did not, and **nothing
compared them**. That is *call the function; a copy is a fork that agrees for
now*, arriving as a directory rather than as a function.

**And the drift ran opposite to the risk everybody named.** The worry was that
editing the copy would diverge from the package. What had happened is the
package moved AHEAD and the copy never followed: upstream found two of its four
README usage lines did not work - **found by a person on a fresh machine typing
them in** - rewrote the block so it runs, and built a runner that executes every
fenced block verbatim on every push.

## Why this and not a submodule, a subtree, or a dependency

**Not a submodule.** We carry DELIBERATE local modifications - the named-span
rule, the gerunds, the reason-aware `holds`. A submodule pins upstream, so those
would live as detached commits in a nested repository, and the gate would test
upstream's code rather than the code this harness actually imports.

**Not a declared dependency.** It loses the 62 package tests the gate gained,
and loses our improvements until upstream takes them. The package is not on
PyPI, so it would be a git URL regardless.

**A subtree is the right long-term shape** for two-way sync, and converting
retroactively is history surgery on a shared repository. It is also not the
thing that stops silent drift: **a subtree nobody pulls is today's situation
with extra ceremony.**

**What stops silent drift is a comparison, and it splits on the network.**

* **In the gate, no network** - the tree matches this record, so nobody can
  edit the copy without the edit being recorded. Catches OUR drift.
* **Person-run, network** - the record matches upstream. Catches THEIRS. It is
  deliberately not a gate test: a gate that fails when GitHub is slow is a gate
  people learn to ignore, and then it is not a gate.

The record is not a lock. It does not stop anybody changing the copy - it stops
them changing it *quietly*, which is the whole of the complaint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
THE_COPY = REPO / "packages" / "four_asserts"
THE_RECORD = THE_COPY / "VENDOR.json"

#: Never vendored and never compared: build noise and the upstream's own CI,
#: which is theirs to run and not ours to carry.
#: BUILD OUTPUT IS NOT PART OF THE COPY. The pycache entry was here from
#: the start for that reason; an egg-info directory is the same category
#: and was not
#: anticipated. An editable install of the package leaves one behind, and the
#: scan then reports four files the record cannot know about - red in whichever
#: checkout happened to run the install, green everywhere else.
NOT_OURS = ("__pycache__", ".git", ".github", ".gitignore", "VENDOR.json",
            "four_asserts.egg-info")


def digest(data: bytes) -> str:
    """sha256 of the content, with line endings normalised to LF first.

    THE CHECK WAS REPORTING THE CHECKOUT RATHER THAN THE COPY. Measured
    2026-09-09: this file reported

        tests/test_the_readme_still_describes_the_code.py: changed since it was
        recorded (f8a6384d0790 -> f6368f022367)

    in one working tree and nothing in another, on the same commit. The record
    holds f8a6384d0790, which is exactly the sha of the bytes GIT STORES; the
    working tree on Windows renders them with CRLF under `core.autocrlf=true`,
    and this hashed the rendering. Two checkouts of one commit, two answers,
    neither of them about the vendored copy.

    WHAT IT GIVES UP, said plainly: an upstream change that ONLY altered line
    endings would no longer be reported. That is the right trade for a check
    whose subject is the content of a vendored copy - a line ending here is a
    property of whoever checked the file out, not of the copy - and it is a
    smaller loss than a check that is red in one tree and green in another for
    a reason nobody can act on.
    """
    return hashlib.sha256(data.replace(bytes([13, 10]), bytes([10]))).hexdigest()

def ours() -> dict[str, str]:
    """Every vendored file and its digest, from the tree."""
    found = {}
    for path in sorted(THE_COPY.rglob("*")):
        if not path.is_file() or any(part in NOT_OURS for part in path.parts):
            continue
        name = path.relative_to(THE_COPY).as_posix()
        found[name] = digest(path.read_bytes())
    return found


def the_record() -> dict:
    try:
        return json.loads(THE_RECORD.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def why_the_tree_does_not_match_the_record() -> list[str]:
    """Every disagreement between the vendored files and what was recorded.

    NO NETWORK. This is the half that belongs in a gate: it asks whether
    somebody changed the copy without saying so, which is answerable from two
    files on this disk and is the failure the gate can actually prevent.
    """
    recorded = the_record().get("files") or {}
    if not recorded:
        return ["no vendor record exists - run --record to write one"]
    here = ours()
    said = []
    for name in sorted(set(recorded) | set(here)):
        was, now = recorded.get(name), here.get(name)
        if was is None:
            said.append(f"{name}: in the tree and not in the record - vendored without being recorded")
        elif now is None:
            said.append(f"{name}: in the record and not in the tree - removed without being recorded")
        elif was != now:
            said.append(f"{name}: changed since it was recorded ({was[:12]} -> {now[:12]})")
    return said


def upstream_now(url: str) -> tuple[str, dict[str, str]] | None:
    """Clone the published repository shallowly and digest it. NETWORK."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        done = subprocess.run(
            ["git", "clone", "--depth", "1", "-q", url, tmp + "/up"],
            capture_output=True, text=True, timeout=300,
        )
        if done.returncode != 0:
            print(f"could not reach {url}: {done.stderr.strip()[:200]}", file=sys.stderr)
            return None
        root = Path(tmp) / "up"
        sha = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
        found = {}
        for path in sorted(root.rglob("*")):
            if not path.is_file() or any(part in NOT_OURS for part in path.parts):
                continue
            found[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
        return sha, found


def compare_with_upstream() -> int:
    record = the_record()
    url = record.get("source") or "https://github.com/naidx0/four-asserts"
    got = upstream_now(url)
    if got is None:
        #: UNREACHABLE IS NOT UNCHANGED. Saying "no drift" because the network
        #: failed is the same error as a suite reporting OK over tests that
        #: never ran.
        print("UNKNOWN: upstream could not be read, so nothing is established.")
        return 2
    sha, theirs = got
    here = ours()
    print(f"upstream {url}")
    print(f"  recorded at {record.get('upstream') or '(never recorded)'}")
    print(f"  now at      {sha}")
    print()
    #: A DICT, not a set. `set(...)` over it kept only the keys and then `.get`
    #: raised - which is what happens when a container is converted for no
    #: reason on the way to being read.
    deliberate = dict(record.get("diverged") or {})
    moved, gone, new, ok = [], [], [], 0
    for name in sorted(set(here) | set(theirs)):
        mine, up = here.get(name), theirs.get(name)
        if up is None:
            new.append(name)
        elif mine is None:
            gone.append(name)
        elif mine != up:
            moved.append(name)
        else:
            ok += 1
    print(f"  {ok} file(s) identical")
    for name in moved:
        why = deliberate.get(name)
        print(f"  DIFFERS  {name}" + (f"  (recorded as ours: {why})" if why else
                                      "  ** NOT RECORDED AS A DELIBERATE CHANGE **"))
    for name in new:
        print(f"  OURS ONLY      {name}")
    for name in gone:
        print(f"  UPSTREAM ONLY  {name}  <- they have it and we do not")
    unexplained = [n for n in moved if n not in deliberate]
    print()
    if sha != record.get("upstream"):
        print("UPSTREAM HAS MOVED since this copy was recorded. That is not an "
              "error - it is the thing this command exists to tell you.")
    if unexplained:
        print(f"UNEXPLAINED: {len(unexplained)} file(s) differ from upstream and "
              "are not recorded as deliberate.")
        return 1
    return 0


def record_it(sha: str) -> int:
    """Write the record. A PERSON DOES THIS, and that is the point.

    A script that recorded its own drift would make the record agree with the
    tree by construction, which is a check that cannot fail.
    """
    existing = the_record()
    THE_RECORD.write_text(
        json.dumps(
            {
                "source": existing.get("source") or "https://github.com/naidx0/four-asserts",
                "upstream": sha,
                "diverged": existing.get("diverged") or {},
                "files": ours(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"recorded {len(ours())} file(s) against upstream {sha}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--upstream", action="store_true",
                        help="compare with the published repository (needs the network)")
    parser.add_argument("--record", metavar="SHA",
                        help="write the vendor record against this upstream sha")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if args.record:
        return record_it(args.record)
    if args.upstream:
        return compare_with_upstream()

    said = why_the_tree_does_not_match_the_record()
    if not said:
        print(f"the vendored copy matches its record: {len(ours())} file(s), "
              f"upstream {the_record().get('upstream', '(unrecorded)')}")
        return 0
    print("THE VENDORED COPY HAS CHANGED WITHOUT THE RECORD CHANGING:", file=sys.stderr)
    for line in said:
        print(f"  {line}", file=sys.stderr)
    print("\nIf the change is intended, run --record <sha> and say why in the "
          "commit. The record does not stop anybody changing the copy; it stops "
          "them changing it quietly.", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
