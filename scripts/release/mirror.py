"""Stage what a public mirror of this repository would contain. DRY RUN ONLY.

    python scripts/release/mirror.py            # stage into scripts/release/out
    python scripts/release/mirror.py --report   # counts and reasons, stage nothing

THERE IS NO `--push` IN THIS FILE, AND THAT IS DELIBERATE. Sequence's equivalent
has one because Sequence has a public mirror to push to. This repository has no
public mirror and nobody has asked for one, so the tool that would create it does
not exist yet. Adding the flag is a decision for whoever owns the repository, not
a convenience for whoever runs the script.

WHAT IT CHECKS BEYOND THE POLICY. `policy.py` decides by path. This scans the
CONTENT of everything the policy kept, for identifiers and for shapes that should
never leave a private tree, and refuses on a hit. The two are separate because
they fail differently: a path rule is wrong about a file you can name, and a
content rule catches the file you did not think to name.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE / "out"
STAGE = OUT / "tree"

sys.path.insert(0, str(HERE))
import policy  # noqa: E402

#: Text files worth scanning for content. A `.png` cannot leak a home directory
#: in a way this scan would catch, and reading every binary would make the run
#: slow enough that people stop doing it.
TEXT = re.compile(r"\.(py|md|ya?ml|json|toml|txt|cfg|ini|ts|tsx|js|jsx|css|html|sh|ps1)$", re.I)


def identifiers() -> list[tuple[str, str]]:
    """Personal strings to refuse on, from an untracked local file.

    Loud when absent, because running fewer checks than you think you are
    running is the failure this whole script exists to prevent.
    """
    #: A "paths" RULE NEED NOT LOOK LIKE A PATH, and that is the trap. Every
    #: rule in both lists is a lowercase SUBSTRING match, so a rule listed
    #: under "paths" that is a bare directory NAME with no separator in it
    #: matches like a word, anywhere in a line. Measured 2026-09-06: the
    #: other lane sanitised a pasted terminal transcript by replacing
    #: everything before a checkout name with an ellipsis, cleared the
    #: home-directory rule, and shipped a commit that the bare name rule
    #: still caught. The word "paths" does not warn anybody about that.
    #:
    #: AND THIS FILE LIVES IN A WORKING TREE, not on a machine. It is
    #: gitignored, and gitignored files do not travel between git worktrees -
    #: so one checkout can have the rules and another can be blind to them,
    #: on the same machine, on the same commit. That is how the same commit
    #: was green in one tree and red in another with no difference in the
    #: code, and why "this machine" in the warning below is imprecise: it is
    #: this CHECKOUT.
    where = HERE / "identifiers.json"
    if not where.exists():
        print(
            f"WARNING: no {where.name} - identifier checks are NOT active, only "
            "shape checks. Create it (it is gitignored) with "
            '{"identifiers": [...], "paths": [...]}.',
            file=sys.stderr,
        )
        return []
    config = json.loads(where.read_text(encoding="utf-8"))
    found = [(t.lower(), "a personal identifier") for t in config.get("identifiers", [])]
    found += [(t.lower(), "a private directory path") for t in config.get("paths", [])]
    return found


#: Shapes, checked whether or not an identifier list exists. The placeholders are
#: NAMED rather than guessed at: a check that cries wolf on documentation gets
#: widened until it stops working, and this tree documents Windows paths in
#: several places on purpose.
#:
#: THREE OF THEM ARE REAL ACCOUNTS AND NONE OF THEM IS A PERSON. `runneradmin`
#: and `RUNNER~1` are GitHub Actions' hosted runner, so a test documenting the
#: path a run takes on CI is documenting CI. `WDAGUtilityAccount` is Windows
#: Sandbox's fixed account, which is the entire point of the clean-machine
#: script that names it. `x` is a one-letter placeholder in a frontend test.
#: Scrubbing those four would have deleted true statements about where this
#: software runs, so they are named here instead - which is the same lesson the
#: rest of this list already carries.
SHAPES = [
    (
        re.compile(r"C:[/\\]{1,2}Users[/\\]{1,2}(?!dev\b|you\b|user\b|username\b|example\b|test\b|x\b|runneradmin\b|RUNNER~1|WDAGUtilityAccount\b|\.\.\.)[A-Za-z0-9_.-]+", re.I),
        "a real Windows home directory",
    ),
    (
        re.compile(r"/Users/(?!dev\b|you\b|user\b|example\b)[A-Za-z0-9_.-]+/(Documents|Projects)", re.I),
        "a real macOS home directory",
    ),
    # The label deliberately does not repeat the phrase it matches: this file is
    # itself scanned, and a rule that spells out its own trigger fails its own
    # check.
    (re.compile(r"obsidian[\s-]*vault|vault[\s-]*obsidian", re.I), "a personal note vault"),
    (
        # KEY MATERIAL, not the word "key". The pattern is length: a real token
        # is long, and a test fixture saying a key must NOT reach the model is
        # the opposite of a leak.
        re.compile(r"\b(sk|ghp|gho|github_pat|xox[baprs])-[A-Za-z0-9_-]*[A-Za-z0-9]{20,}"),
        "something shaped like a live API token",
    ),
]


def tracked() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def identifiers_are_available() -> bool:
    """Is the private denylist on this machine?

    IT IS GITIGNORED, WHICH MEANS IT IS ABSENT EVERYWHERE BUT HERE. Measured
    2026-09-06: with it missing, the scan runs 4 of its 11 rules and reports a
    clean tree, and the gate's own guard passes - so on CI and in every other
    lane's checkout this check has been running a third of itself and saying OK.
    That is the shape of defect this whole repository exists to refuse, arriving
    inside the thing that refuses it.
    """
    return (HERE / "identifiers.json").exists()


def scan(paths: list[str], *, include_identifiers: bool = True) -> list[str]:
    """Content hits in the files that would ship. Empty is the only pass.

    `include_identifiers=False` runs the SHAPE rules only - the ones that need
    no private data and can therefore run anywhere. Splitting them is what lets
    a machine without the denylist check what it can and say what it could not,
    rather than reporting a pass for a scan it only partly ran.
    """
    rules = (
        [(re.compile(re.escape(needle), re.I), why) for needle, why in identifiers()]
        if include_identifiers
        else []
    )
    hits = []
    for relative in paths:
        if not TEXT.search(relative):
            continue
        try:
            text = (REPO / relative).read_text(encoding="utf-8", errors="replace")
        except OSError:  # pragma: no cover
            continue
        for pattern, why in rules + SHAPES:
            found = pattern.search(text)
            if found:
                line = text[: found.start()].count("\n") + 1
                hits.append(f"{relative}:{line} contains {why}")
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true", help="counts and reasons; stage nothing")
    args = parser.parse_args(argv)

    files = tracked()
    kept, dropped = [], []
    for relative in files:
        keep, why = policy.decide(relative)
        (kept if keep else dropped).append((relative, why))

    print(f"tracked files: {len(files)}")
    print(f"  would ship:  {len(kept)}")
    print(f"  held back:   {len(dropped)}")
    print()
    print("held back, by reason:")
    for why, count in Counter(why for _, why in dropped).most_common():
        print(f"  {count:5d}  {why}")
    print()
    print("shipped, by reason:")
    for why, count in Counter(why for _, why in kept).most_common():
        print(f"  {count:5d}  {why}")

    # A README that links to a doc the policy denies would publish a broken
    # link. Checked here rather than left to a reader of the mirror.
    print()
    broken = []
    for linked in policy.README_LINKED:
        keep, why = policy.decide(linked)
        if not keep:
            broken.append(f"{linked} ({why})")
    if broken:
        print("README LINKS THE MIRROR WOULD BREAK:")
        for line in broken:
            print(f"  {line}")
    else:
        print(f"README-linked docs that survive the policy: {len(policy.README_LINKED)} of "
              f"{len(policy.README_LINKED)}")

    hits = scan([relative for relative, _ in kept])
    covered = len(identifiers()) + len(SHAPES) if identifiers_are_available() else len(SHAPES)
    total_rules = "?" if not identifiers_are_available() else covered
    print()
    if hits:
        # MATCHES AND PLACES ARE DIFFERENT NUMBERS, and reporting only the
        # first overstates the problem. Measured on the pre-scrub tree: 50 rule
        # matches over 27 distinct file:line places, because 21 of them tripped
        # two rules at once - a path like C:/Users/<name> is both a personal
        # identifier and a real home directory, one string counted twice. The
        # by-class breakdown double-counts for the same reason, so it is
        # labelled as matches rather than findings.
        places = {hit.split(" contains ")[0] for hit in hits}
        print(
            f"CONTENT CHECK FAILED: {len(places)} place(s) in "
            f"{len({h.split(':')[0] for h in hits})} file(s) that would ship "
            f"({len(hits)} rule matches; one string can trip two rules)"
        )
        for line in hits[:20]:
            print(f"  {line}")
        return 2
    # THE COVERAGE TRAVELS WITH THE RESULT. "0 hits" from a scan running a
    # third of its rules is not the same sentence as "0 hits" from a whole one,
    # and nothing in the old line distinguished them.
    if identifiers_are_available():
        print(f"content check: 0 hits across {len(kept)} shipped files, {covered} rules")
    else:
        print(
            f"content check: 0 hits across {len(kept)} shipped files - but only "
            f"{len(SHAPES)} SHAPE rules ran. The identifier list is not on this "
            "machine, so the personal-identifier rules did not run and this is "
            "not a clean bill."
        )

    if args.report:
        return 0 if not broken else 2

    if STAGE.exists():
        shutil.rmtree(STAGE)
    for relative, _ in kept:
        target = STAGE / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / relative, target)
    print(f"staged {len(kept)} files into {STAGE}")
    print("DRY RUN. Nothing was pushed and this tool has no way to push.")
    return 0 if not broken else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
