"""Make the machine lock serialise git too, not only suites.

    python scripts/install_hooks.py            # install into this checkout
    python scripts/install_hooks.py --check    # say what is installed, change nothing
    python scripts/install_hooks.py --remove   # take them out again

## The defect this closes, measured

`scripts/gate.py` ends a run that started on one commit and finished on another
with this, and it is the gate's own sentence:

    GATE IS RED: HEAD moved while the suite was running.
    ... Do not commit, rebase or checkout in this working copy while a gate is
    running; the machine lock serialises suites, not git.

MEASURED 2026-09-10, twice in one hour in the shared checkout:

    03:47:59  a gate takes the lock and starts on 2531252
    03:52:00  another lane commits b7cc2af into the same working copy
    04:09     the gate exits 2 - the run describes neither tree

Forty-two minutes of machine time produced no verdict, and the second one
happened AFTER a freeze had been broadcast in words. A rule that lives in a
message holds nothing: the lane that breaks it is the lane that did not read it
yet. So the rule moves to where the commit happens.

## What it does, and the one thing it deliberately does not

`pre-commit` and `pre-rebase` read the SAME lock `one_gate_at_a_time` writes,
through that module's own `_alive(pid, pid_born)`, and refuse while a LIVE gate
holds this checkout's lock. A stale lock - a holder that was killed, which does
happen and left a dead pid in the file at 03:16 tonight - does not refuse, and
says so rather than passing silently.

`pre-push` runs `scripts/viewport_smoke.py`: load the composer specimen at
820 / 1024 / 1280 / 1600 and refuse if any width scrolls the document
horizontally. Fail-open when no Chrome/Edge is installed.

IT IS A GUARD AND NOT AN ENFORCEMENT, AND THE DIFFERENCE IS WORTH STATING.
`git commit --no-verify` / `git push --no-verify` skips every hook and nothing
here can prevent that; git offers no way to make a hook mandatory. So this
stops the lane that forgot, which is the whole population it needs to stop -
both of tonight's collisions were somebody working normally, neither was
anybody insisting.

## Fail-open, on purpose

Every failure path in the hook ALLOWS the commit: an unreadable lock, a broken
import, an exception nobody predicted. A guard that refuses when it cannot tell
would block every commit in every checkout the first time it met a machine it
did not understand, and it would do it at the moment somebody is trying to fix
something. The cost of failing open is one lost gate, which is the cost we
already pay; the cost of failing closed is a repository nobody can commit to.

## Why a tracked script rather than a committed hook

`.git/hooks/` is not tracked and cannot be - it is per-checkout by design, and a
worktree has its own. So the hook's TEXT is here, in the tree, reviewable, and
installing it is a command each checkout runs. `--check` exists so a lane can
answer "is it actually installed here?" with a reading rather than a memory.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

LOCK_HOOKS = ("pre-commit", "pre-rebase")
VIEWPORT_HOOK = "pre-push"

#: Written into every installed hook so `--check` can tell OURS from a hook
#: somebody else put there. Without it, `--remove` would be free to delete
#: another tool's hook, and `--check` would report a stranger's file as ours.
MARKER = "ml-harness:one_gate_at_a_time"
VIEWPORT_MARKER = "ml-harness:viewport_smoke"

HOOK_SOURCE = '''#!/usr/bin/env python
"""Refuse to move HEAD while a live gate holds this checkout's lock.

{marker}

Installed by `scripts/install_hooks.py`. Not tracked - the tracked text is in
that file. FAIL-OPEN: every error path allows the operation.
"""
import subprocess
import sys
from pathlib import Path


def the_tree_being_committed_to():
    """The working tree THIS commit is in - asked of git, not read off my path.

    EVERY WORKTREE SHARES ONE `.git/hooks`, so this same file runs for the main
    checkout and for every worktree of it. Resolving the repository from
    `__file__` gave the MAIN checkout every time, which meant a commit in a
    worktree was refused because a gate was running somewhere else - and the
    refusal it printed said "commit in a worktree of your own instead". A guard
    that forbids the thing it advises is worse than no guard.

    During a hook, git runs us with the working tree as cwd, so it can say.
    """
    try:
        said = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=30,
        )
    except OSError:
        return None
    if said.returncode != 0 or not said.stdout.strip():
        return None
    return Path(said.stdout.strip())


def main() -> int:
    try:
        import importlib.util

        tree = the_tree_being_committed_to()
        if tree is None:
            return 0
        path = tree / "scripts" / "one_gate_at_a_time.py"
        if not path.is_file():
            return 0
        spec = importlib.util.spec_from_file_location("one_gate_at_a_time", path)
        if spec is None or spec.loader is None:
            return 0
        lock = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lock)

        holder = lock._holder()
        if not holder:
            return 0
        #: THE HOLDER'S OWN RECOVERY IS NOT AN INTRUSION. Measured 2026-09-10:
        #: push_if_green held this lock, its push was rejected, it ran
        #: `git rebase origin/main` to recover - and this hook refused it,
        #: because a live holder was holding the lock. The holder WAS the
        #: rebasing process. The retry died with "the rebase did not succeed".
        if getattr(lock, "this_process_holds_the_lock", None) and lock.this_process_holds_the_lock(holder):
            return 0
        pid = int(holder.get("pid") or 0)
        if not lock._alive(pid, str(holder.get("pid_born") or "")):
            print(
                "one_gate_at_a_time: the lock names pid %s, which is not "
                "running - stale, so this is allowed." % pid,
                file=sys.stderr,
            )
            return 0
    except Exception:  # noqa: BLE001 - a guard that cannot tell must not block
        return 0

    print(
        "REFUSED: a gate is running in this working copy and moving HEAD "
        "would void it.\\n"
        "  holder: %s\\n"
        "  the gate's own words: a run that starts on one commit and ends on "
        "another describes neither tree, and exits 2.\\n"
        "\\n"
        "Commit in a worktree of your own instead:\\n"
        "  git worktree add ../ml-harness-<lane> -b <lane>/night\\n"
        "\\n"
        "There is no flag here. `--no-verify` skips every git hook and this "
        "one cannot stop it - if you use it, the gate you void is somebody's."
        % lock._describe(holder),
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
'''

PRE_PUSH_SOURCE = '''#!/usr/bin/env python
"""Refuse a push when the composer specimen overflows at a known viewport.

{marker}

Installed by `scripts/install_hooks.py`. Runs `scripts/viewport_smoke.py`.
Fail-open when no Chrome/Edge is installed (that script exits 0 with SKIP).
"""
import subprocess
import sys
from pathlib import Path


def the_tree() -> Path | None:
    try:
        said = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=30,
        )
    except OSError:
        return None
    if said.returncode != 0 or not said.stdout.strip():
        return None
    return Path(said.stdout.strip())


def main() -> int:
    try:
        tree = the_tree()
        if tree is None:
            return 0
        script = tree / "scripts" / "viewport_smoke.py"
        if not script.is_file():
            return 0
        ran = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(tree),
        )
        return int(ran.returncode)
    except Exception:  # noqa: BLE001 - a guard that cannot tell must not block
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def hooks_dir(repo: Path = REPO) -> Path | None:
    """Where git keeps THIS checkout's hooks.

    ASKED, NOT ASSUMED. `<repo>/.git/hooks` is wrong for a worktree, where
    `.git` is a file pointing elsewhere - and worktrees are exactly what this
    change is asking every lane to start using, so guessing here would break on
    the first checkout that took the advice.
    """
    try:
        said = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--git-path", "hooks"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except OSError:
        return None
    if said.returncode != 0:
        return None
    where = Path(said.stdout.strip())
    return where if where.is_absolute() else (repo / where)


def _lock_text() -> str:
    return HOOK_SOURCE.format(marker=MARKER)


def _push_text() -> str:
    return PRE_PUSH_SOURCE.format(marker=VIEWPORT_MARKER)


def is_ours(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return MARKER in text or VIEWPORT_MARKER in text


def is_current(path: Path, *, kind: str) -> bool:
    """Is the INSTALLED text the text this file would install today?

    MEASURED 2026-09-10, and it cost a gate. The hook was fixed at 10:0x so a
    lock's own holder could rebase under it - and `push_if_green`'s retry was
    refused by that same hook at 11:19, because the fix was in the TRACKED
    source and the copy in `.git/hooks` was the one installed at 04:07.
    `--check` said `installed` both before and after the fix.
    """
    want = _lock_text() if kind == "lock" else _push_text()
    try:
        return path.read_text(encoding="utf-8", errors="replace") == want
    except OSError:
        return False


def _install_one(where: Path, name: str, text: str) -> str:
    path = where / name
    #: A HOOK SOMEBODY ELSE WROTE IS NOT OURS TO OVERWRITE. Refusing one
    #: file and installing the rest is better than an all-or-nothing that
    #: leaves a lane guessing which half happened.
    if path.exists() and not is_ours(path):
        return f"{name}: NOT INSTALLED - a hook is already there and it is not ours"
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return f"{name}: installed at {path}"


def install(repo: Path = REPO) -> tuple[int, list[str]]:
    where = hooks_dir(repo)
    if where is None:
        return 1, ["git could not say where this checkout keeps its hooks"]
    where.mkdir(parents=True, exist_ok=True)
    said = []
    for name in LOCK_HOOKS:
        said.append(_install_one(where, name, _lock_text()))
    said.append(_install_one(where, VIEWPORT_HOOK, _push_text()))
    return 0, said


def check(repo: Path = REPO) -> tuple[int, list[str]]:
    where = hooks_dir(repo)
    if where is None:
        return 1, ["git could not say where this checkout keeps its hooks"]
    said = []
    missing = 0
    expected = [(name, "lock") for name in LOCK_HOOKS] + [(VIEWPORT_HOOK, "push")]
    for name, kind in expected:
        path = where / name
        if not path.exists():
            said.append(f"{name}: absent")
            missing += 1
        elif is_ours(path) and is_current(path, kind=kind):
            said.append(f"{name}: installed")
        elif is_ours(path):
            #: OURS BUT NOT TODAY'S. "installed" for a version that predates
            #: the fix somebody is relying on is the same defect as a skip
            #: reading as a pass, which is what this whole file is about.
            said.append(
                f"{name}: STALE - ours, but not the text this repository would "
                "install now. Run `python scripts/install_hooks.py` again."
            )
            missing += 1
        else:
            said.append(f"{name}: present but NOT ours")
            missing += 1
    return (1 if missing else 0), said


def remove(repo: Path = REPO) -> tuple[int, list[str]]:
    where = hooks_dir(repo)
    if where is None:
        return 1, ["git could not say where this checkout keeps its hooks"]
    said = []
    for name in (*LOCK_HOOKS, VIEWPORT_HOOK):
        path = where / name
        if not path.exists():
            said.append(f"{name}: absent")
        elif not is_ours(path):
            said.append(f"{name}: LEFT ALONE - not ours")
        else:
            path.unlink()
            said.append(f"{name}: removed")
    return 0, said


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report, change nothing")
    parser.add_argument("--remove", action="store_true", help="take the hooks out")
    arguments = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if arguments.check and arguments.remove:
        print("--check and --remove ask for different things.", file=sys.stderr)
        return 2

    code, said = (
        check() if arguments.check else remove() if arguments.remove else install()
    )
    for line in said:
        print(line)
    return code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
