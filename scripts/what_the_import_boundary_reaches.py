"""What a bare `import app` actually reaches, enumerated rather than sampled.

## What this is and is not

Two checkouts on this machine share one virtualenv whose editable install maps
`app` to ONE of them. A process in either tree that does not put its own
repository first on `sys.path` imports that tree's package - and because
`ENGINE_FILE` is `data_root()/engine.json` and `data_root()` prefers the checkout
of whichever `app` was imported, the mis-resolution reaches the engine file, the
token and the data root as well.

**THIS MEASURES. IT DOES NOT FIX.** It writes nothing, publishes nothing, and
changes no shared state. The fix - rewiring how `app` resolves - is surgery on
infrastructure both lanes run every process through, and it cannot be scoped
until somebody has established the blast radius. This is that.

## Built against the way I get things wrong

Three habits, each one a mistake made on this machine tonight:

* **It resolves by RUNNING, not by reasoning.** Each probe is a subprocess with a
  real working directory that imports `app` and prints what it got. A key
  derivation reimplemented rather than called was wrong the first time it was
  used tonight; asking Python what it resolves cannot be wrong in that way.
* **It enumerates rather than samples.** Every executable entry point in both
  trees, not a plausible subset. "0 lost tests" and "0 paths written by both"
  were both true and both narrow.
* **It prints its evidence, not a summary.** Every row, every path, so a reader
  disagreeing with the conclusion can check the rows. `OK (skipped=1)` was a
  summary over a warning that said NOT a clean bill.

## The three questions

1. which entry points already put their own repository first, as a ratio
2. what a bare import resolves to from each place people start things
3. what each unguarded entry point could touch if it resolved wrongly
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: The other working trees on this machine, found rather than assumed.
def the_other_checkouts() -> list[Path]:
    out = subprocess.run(["git", "worktree", "list"], cwd=REPO,
                         capture_output=True, text=True, encoding="utf-8").stdout
    trees = []
    for line in out.splitlines():
        first = line.split()[0] if line.split() else ""
        if first:
            path = Path(first)
            if path.exists() and path.resolve() != REPO:
                trees.append(path)
    return trees


IMPORTS_APP = re.compile(r"^\s*(?:from\s+app\b|import\s+app\b)", re.M)
PUTS_ITS_REPO_FIRST = re.compile(r"sys\.path\.insert\(\s*0\s*,")

#: What a wrongly-resolved `app` would let a script touch. Ordered by how much
#: it would matter, worst first - reading another tree's config is not the same
#: as publishing a token into it.
THE_BLAST_RADIUS = (
    ("publishes a token", re.compile(r"write_portfile|publish_portfile|current_token")),
    ("writes the data root", re.compile(r"in_data_root|data_root\(")),
    ("writes runs/", re.compile(r"runs\s*/|RUNS_ROOT|/ \"runs\"")),
    ("reads the engine file", re.compile(r"ENGINE_FILE|read_portfile")),
    ("touches the database", re.compile(r"ml_harness\.db|from app import db|app\.db")),
)

#: THE INTERPRETER IS THE MEASUREMENT. The first run of this script probed with
#: `sys.executable`, which under an agent harness is the AGENT's virtualenv - one
#: with no editable install at all. Every probe returned ModuleNotFoundError and
#: the two that worked did so only because the working directory happened to
#: contain `app/`. I read that as "the hazard does not exist" and was one step
#: from reporting it.
#:
#: The venv that matters is the project's, and there is exactly one on this
#: machine: `<this checkout>/.venv`. The other tree HAS NO `.venv` OF ITS OWN,
#: which is what "shared virtualenv" means here and is why the editable install
#: reaches across trees at all.
THE_VENV = REPO / ".venv" / "Scripts" / "python.exe"


def the_interpreter() -> str:
    """The project's venv if it exists, else this one - said out loud either way."""
    return str(THE_VENV) if THE_VENV.exists() else sys.executable


THE_PROBE = (
    "import json, sys; "
    "import app, app.paths as p; "
    "print(json.dumps({"
    "'app': str(__import__('pathlib').Path(app.__file__).resolve().parents[0]), "
    "'data_root': str(p.data_root())}))"
)


def entry_points(tree: Path) -> list[Path]:
    """Every runnable .py under scripts/ - the things a person starts."""
    return sorted(p for p in (tree / "scripts").rglob("*.py") if p.name != "__init__.py")


def question_one() -> None:
    print("=" * 72)
    print("1. ENTRY POINTS THAT ALREADY PUT THEIR OWN REPOSITORY FIRST")
    print("   (of those that import `app` at all - the rest cannot be hurt this way)")
    for tree in [REPO, *the_other_checkouts()]:
        importing, guarded, unguarded = 0, 0, []
        for path in entry_points(tree):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if not IMPORTS_APP.search(text):
                continue
            importing += 1
            if PUTS_ITS_REPO_FIRST.search(text):
                guarded += 1
            else:
                unguarded.append(path.relative_to(tree))
        print(f"{NEWLINE}  {tree.name}: {guarded} of {importing} guarded")
        for path in unguarded:
            print(f"      UNGUARDED  {path}")
        if not unguarded and importing:
            print("      none unguarded")


def question_two() -> None:
    print()
    print("=" * 72)
    print("2. WHAT A BARE `import app` RESOLVES TO, BY WORKING DIRECTORY")
    print("   Resolved by RUNNING a subprocess from each directory, not by reasoning.")
    #: The subdirectory cases are the point: from a tree's ROOT, the cwd holds
    #: `app/` and wins regardless of the editable install, which hides the
    #: hazard. From a subdirectory it does not.
    wheres = [REPO, REPO / "scripts", Path.home()]
    for other in the_other_checkouts():
        wheres += [other, other / "scripts"]
    for where in wheres:
        if not where.exists():
            continue
        try:
            done = subprocess.run(
                [the_interpreter(), "-c", THE_PROBE], cwd=where,
                capture_output=True, text=True, encoding="utf-8", timeout=90,
            )
            got = json.loads(done.stdout.strip().splitlines()[-1]) if done.stdout.strip() else None
        except (json.JSONDecodeError, IndexError, subprocess.TimeoutExpired, OSError) as error:
            print(f"{NEWLINE}  cwd={where}{NEWLINE}      probe failed: {error}")
            continue
        if got is None:
            print(f"{NEWLINE}  cwd={where}{NEWLINE}      probe produced nothing: "
                  f"{done.stderr.strip()[:120]}")
            continue
        app_tree = Path(got["app"]).parents[0]
        #: THE TREE THAT OWNS THE CWD, not the cwd itself. The first version
        #: compared against `where` and so labelled `<repo>/scripts` as
        #: "ANOTHER TREE (ml-harness)" - which is this tree, reached from its
        #: own subdirectory. The data was right and the label was wrong, which
        #: is the more dangerous of the two.
        owner = next((up for up in [where.resolve(), *where.resolve().parents]
                      if (up / "app").is_dir() or (up / ".git").exists()), None)
        verdict = ("its own tree" if owner and app_tree == owner
                   else f"NOT ITS OWN -> {app_tree.name}")
        print(f"{NEWLINE}  cwd={where}")
        print(f"      app package -> {got['app']}   [{verdict}]")
        print(f"      data root   -> {got['data_root']}")


def question_three() -> None:
    print()
    print("=" * 72)
    print("3. BLAST RADIUS PER UNGUARDED ENTRY POINT")
    print("   What it could touch in ANOTHER tree if `app` resolved wrongly.")
    any_found = False
    for tree in [REPO, *the_other_checkouts()]:
        for path in entry_points(tree):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if not IMPORTS_APP.search(text) or PUTS_ITS_REPO_FIRST.search(text):
                continue
            any_found = True
            reach = [name for name, pattern in THE_BLAST_RADIUS if pattern.search(text)]
            print(f"{NEWLINE}  {tree.name}/{path.relative_to(tree)}")
            for name in reach or ["(imports app but touches none of the ranked shapes)"]:
                print(f"      {name}")
    if not any_found:
        print(f"{NEWLINE}  No unguarded entry point in any tree. The blast radius of the")
        print("  CURRENT code is empty; the hazard is what gets written next.")


NEWLINE = chr(10)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    print(f"trees on this machine: {[REPO.name] + [t.name for t in the_other_checkouts()]}")
    print(f"probing with: {the_interpreter()}")
    print(f"  (this script was started by: {sys.executable})")
    if the_interpreter() != sys.executable:
        print("  THESE DIFFER - the project venv carries the editable install and")
        print("  the starting interpreter may not. Probing with the wrong one")
        print("  answers a different question and looks like a clean result.")
    question_one()
    question_two()
    question_three()
    print()
    print("=" * 72)
    print("WHAT THIS DOES NOT ESTABLISH: anything about processes that are not")
    print("entry points under scripts/ - a test helper, an editor plugin or a")
    print("notebook importing `app` has the same exposure and is not counted here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
