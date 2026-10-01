"""The machine lock serialises git too, and this is the proof it does.

## What went wrong twice in one hour

`scripts/gate.py` ends a run that began on one commit and finished on another
with `GATE IS RED: HEAD moved while the suite was running`, and its own remedy
sentence says *the machine lock serialises suites, not git*. Measured in the
shared checkout on 2026-09-10: a gate took the lock at 03:47:59 on `2531252`,
another lane committed `b7cc2af` at 03:52:00, and the run exited 2 describing
neither tree. It was the second such loss in an hour, and the second happened
AFTER a freeze had been broadcast in words.

A rule that lives in a message holds nothing, because the lane that breaks it is
the lane that has not read it yet. `scripts/install_hooks.py` moves it to where
the commit happens.

## The states, and the fourth one is the one that matters

A live lock refuses; a stale lock allows; no lock allows. The fourth is
FAIL-OPEN: anything the hook cannot read, parse, import or understand allows the
commit and says nothing. A guard that refuses when it cannot tell would block
every commit in the first checkout whose machine it did not understand, at the
moment somebody is trying to fix something - and unlike a lost gate, which costs
one run, that costs the repository.

## What is asserted about the hook TEXT and why

The hook is not tracked - `.git/hooks` cannot be, and a worktree has its own -
so these tests exercise the installed file by running it, rather than importing
a module. `run_hook` executes it exactly as git would.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import support

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import install_hooks  # noqa: E402 - after the path is set


def a_repo(where: Path) -> Path:
    """A real git repository, because the hook asks git where its hooks live."""
    subprocess.run(["git", "init", "-q", str(where)], check=True, capture_output=True)
    (where / "scripts").mkdir(parents=True, exist_ok=True)
    #: The hook resolves the lock module relative to itself, so the fixture
    #: needs the real one at the real path.
    (where / "scripts" / "one_gate_at_a_time.py").write_text(
        (REPO / "scripts" / "one_gate_at_a_time.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return where


class TheHookRefusesOnlyWhileAGateIsLive(unittest.TestCase):
    def setUp(self):
        self.tree = a_repo(Path(support.sandbox(self)) / "checkout")
        code, said = install_hooks.install(self.tree)
        self.assertEqual(0, code, said)
        self.hook = install_hooks.hooks_dir(self.tree) / "pre-commit"
        self.assertTrue(self.hook.is_file(), "the hook did not install")
        #: This fixture's own lock, named the way the module names it for THIS
        #: tree - read from the module rather than recomputed, so the test
        #: cannot drift from the implementation it is checking.
        self.lock = self._lock_path()

    def _lock_path(self) -> Path:
        said = subprocess.run(
            [sys.executable, "-c",
             "import importlib.util,sys;"
             f"s=importlib.util.spec_from_file_location('l', r'{self.tree}/scripts/one_gate_at_a_time.py');"
             "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);print(m.LOCK)"],
            capture_output=True, text=True, check=True,
        )
        return Path(said.stdout.strip())

    def run_hook(self, *, env: dict | None = None) -> subprocess.CompletedProcess:
        """Exactly as git runs it: the file, by the interpreter, in the tree.

        Drop `MLH_HOLDS_THE_GATE_LOCK` unless the caller sets it. A parent
        `scripts/gate.py` leaves that variable set to its own pid; if the
        sandbox lock is written with the same pid (this process), the hook
        would wave the commit through and the refusal cases would lie green
        only when the suite is NOT run under the gate.
        """
        import os

        cleaned = dict(os.environ if env is None else env)
        if env is None or "MLH_HOLDS_THE_GATE_LOCK" not in env:
            cleaned.pop("MLH_HOLDS_THE_GATE_LOCK", None)
        return subprocess.run(
            [sys.executable, str(self.hook)],
            cwd=self.tree, capture_output=True, text=True, env=cleaned,
        )

    def _write_lock(self, pid: int, born: str, command: str = "scripts/gate.py"):
        self.lock.parent.mkdir(parents=True, exist_ok=True)
        self.lock.write_text(json.dumps({
            "pid": pid, "pid_born": born, "cwd": str(self.tree),
            "command": command, "started": "2026-09-10 03:47:59",
        }), encoding="utf-8")
        self.addCleanup(lambda: self.lock.unlink(missing_ok=True))

    # -- the three states -------------------------------------------------

    def test_no_lock_allows_the_commit(self):
        self.lock.unlink(missing_ok=True)
        self.assertEqual(0, self.run_hook().returncode)

    def test_a_live_lock_refuses_the_commit(self):
        """THE CASE. A live holder is a suite whose verdict a commit would void."""
        import os

        me = os.getpid()
        born = self._born(me)
        self._write_lock(me, born)
        done = self.run_hook()
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn("REFUSED", done.stderr)

    def test_a_stale_lock_allows_and_says_so(self):
        """A KILLED HOLDER LEAVES ITS PID IN THE FILE. Measured tonight: after
        a gate was stopped at 03:16 the lock still named it. Refusing on that
        would block every commit until somebody deleted a file by hand."""
        self._write_lock(self._a_dead_pid(), "")
        done = self.run_hook()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("stale", done.stderr.lower())

    # -- the fourth state, which is the one that protects everybody ---------

    def test_an_unreadable_lock_allows_the_commit(self):
        """Not JSON, so nothing can be decided from it.

        NOTE WHICH PATH THIS TAKES: `_holder()` catches the parse error itself
        and returns None, so this exercises the "no holder" branch. It is NOT
        the fail-open test, which is below - and believing it was is exactly
        what the mutation below caught.
        """
        self.lock.parent.mkdir(parents=True, exist_ok=True)
        self.lock.write_text("{not json at all", encoding="utf-8")
        self.addCleanup(lambda: self.lock.unlink(missing_ok=True))
        self.assertEqual(0, self.run_hook().returncode)

    def test_a_lock_that_raises_inside_the_guard_allows_the_commit(self):
        """FAIL-OPEN, AND THIS IS THE TEST THAT REACHES IT.

        MEASURED: mutating `except Exception: return 0` to `return 1` left the
        suite GREEN, because every other case here returns before the guard can
        throw. A fail-open branch nobody has seen fail is a fail-open branch
        nobody knows is wired - and this one is the difference between a lost
        gate and a repository nobody can commit to.

        Valid JSON, so `_holder()` hands it back; a pid that is not a number,
        so `int(...)` raises inside the try.
        """
        self.lock.parent.mkdir(parents=True, exist_ok=True)
        self.lock.write_text(
            json.dumps({"pid": "not-a-number", "pid_born": "", "cwd": str(self.tree),
                        "command": "scripts/gate.py", "started": "now"}),
            encoding="utf-8",
        )
        self.addCleanup(lambda: self.lock.unlink(missing_ok=True))
        done = self.run_hook()
        self.assertEqual(0, done.returncode, done.stderr)

    def test_a_missing_lock_module_allows_the_commit(self):
        """The hook is in `.git/`, which survives a tree the module is not in."""
        import os

        me = os.getpid()
        self._write_lock(me, self._born(me))
        module = self.tree / "scripts" / "one_gate_at_a_time.py"
        module.rename(module.with_suffix(".py.away"))
        self.assertEqual(0, self.run_hook().returncode)

    # -- the refusal has to be actionable ----------------------------------

    def test_the_refusal_names_the_holder_and_the_way_out(self):
        """A refusal without a subject is a message nobody can act on."""
        import os

        me = os.getpid()
        self._write_lock(me, self._born(me))
        said = self.run_hook().stderr
        self.assertIn(str(me), said)
        self.assertIn("worktree", said)
        #: AND IT ADMITS ITS OWN LIMIT. `--no-verify` skips every git hook and
        #: nothing here can prevent it; a guard that implied otherwise would be
        #: claiming an enforcement it does not have.
        self.assertIn("--no-verify", said)

    # -- installation is a reading, not a memory ---------------------------

    def test_check_reports_installed_after_install(self):
        code, said = install_hooks.check(self.tree)
        self.assertEqual(0, code, said)
        self.assertTrue(all("installed" in line for line in said), said)

    def test_check_reports_a_stale_hook_rather_than_calling_it_installed(self):
        """THE ONE THAT COST A GATE, and `--check` said `installed` throughout.

        MEASURED 2026-09-10: the hook was fixed at 10:0x so a lock's own holder
        could rebase under it, and `push_if_green`'s retry was refused by that
        same hook at 11:19 - because the fix was in the TRACKED source while
        the copy in `.git/hooks` was the one installed at 04:07. Hook text is
        not tracked and cannot be, so updating the source does not update the
        installation, and a check that reads only the marker cannot tell.

        "Installed" that means "some version of ours" is the same defect as a
        skip reading as a pass, in the tool built to stop exactly that.
        """
        where = install_hooks.hooks_dir(self.tree)
        path = where / "pre-commit"
        stale = path.read_text(encoding="utf-8").replace(
            "def main() -> int:", "def main() -> int:  # an older text", 1
        )
        path.write_text(stale, encoding="utf-8")

        self.assertTrue(install_hooks.is_ours(path), "still ours, just older")
        self.assertFalse(install_hooks.is_current(path, kind="lock"))
        code, said = install_hooks.check(self.tree)
        self.assertEqual(1, code, said)
        self.assertTrue(any("STALE" in line for line in said), said)

    def test_check_reports_installed_for_the_text_it_would_install_now(self):
        """THE CONTROL. If this went red every checkout would be told to
        reinstall forever, which is how a real warning gets ignored."""
        where = install_hooks.hooks_dir(self.tree)
        self.assertTrue(install_hooks.is_current(where / "pre-commit", kind="lock"))

    def test_check_reports_absent_before_install(self):
        fresh = a_repo(Path(support.sandbox(self)) / "fresh")
        code, said = install_hooks.check(fresh)
        self.assertEqual(1, code)
        self.assertTrue(any("absent" in line for line in said), said)

    def test_a_stranger_s_hook_is_not_overwritten(self):
        """Somebody else's pre-commit is not ours to replace, and a lane that
        had one would otherwise lose it without being told."""
        fresh = a_repo(Path(support.sandbox(self)) / "stranger")
        where = install_hooks.hooks_dir(fresh)
        where.mkdir(parents=True, exist_ok=True)
        (where / "pre-commit").write_text("#!/bin/sh\necho theirs\n", encoding="utf-8")
        install_hooks.install(fresh)
        self.assertIn("theirs", (where / "pre-commit").read_text(encoding="utf-8"))

    def test_remove_leaves_a_stranger_s_hook_alone(self):
        fresh = a_repo(Path(support.sandbox(self)) / "stranger2")
        where = install_hooks.hooks_dir(fresh)
        where.mkdir(parents=True, exist_ok=True)
        (where / "pre-commit").write_text("#!/bin/sh\necho theirs\n", encoding="utf-8")
        install_hooks.remove(fresh)
        self.assertTrue((where / "pre-commit").is_file())

    def test_both_hooks_are_installed(self):
        """A pre-commit alone leaves `git rebase` free to move HEAD, and a
        rebase moves it further than a commit does. Lock hooks + viewport
        pre-push (LOCK_HOOKS / VIEWPORT_HOOK — THE_HOOKS was retired)."""
        where = install_hooks.hooks_dir(self.tree)
        expected = list(install_hooks.LOCK_HOOKS) + [install_hooks.VIEWPORT_HOOK]
        for name in expected:
            with self.subTest(hook=name):
                self.assertTrue((where / name).is_file())

    def test_a_worktree_is_judged_by_its_own_lock_and_not_the_main_checkouts(self):
        """THE CONTRADICTION THIS CAUGHT, and it was live for four minutes.

        Every worktree shares ONE `.git/hooks`, so this hook runs for the main
        checkout and for every worktree of it. The first version resolved the
        repository from its own `__file__`, which is always under the MAIN
        checkout - so a commit in a worktree was refused because a gate was
        running somewhere else, while the refusal it printed said "commit in a
        worktree of your own instead". Measured against a real live gate at
        04:07: refused, exit 1.

        A guard that forbids the thing it advises is worse than no guard. The
        tree is asked of git at hook time now, and each tree has its own lock
        because `_this_checkout()` keys on the module's own location.
        """
        import os

        worktree = Path(support.sandbox(self)) / "wt"
        done = subprocess.run(
            ["git", "-C", str(self.tree), "worktree", "add", "-q",
             str(worktree), "-b", "probe"],
            capture_output=True, text=True,
        )
        if done.returncode != 0:  # pragma: no cover - git too old to have worktrees
            self.skipTest(f"git could not add a worktree: {done.stderr.strip()[:120]}")

        #: A LIVE gate on the MAIN checkout's lock. The worktree's own lock is
        #: a different file and nobody holds it.
        me = os.getpid()
        self._write_lock(me, self._born(me))

        done = subprocess.run(
            [sys.executable, str(self.hook)],
            cwd=worktree, capture_output=True, text=True,
        )
        self.assertEqual(
            0, done.returncode,
            "a commit in a worktree was refused for a gate running in the main "
            "checkout, which is the route the refusal text recommends:\n"
            + done.stderr,
        )

    def test_the_lock_holder_may_move_its_own_head(self):
        """THE RETRY THIS HOOK KILLED, and it killed it the day it shipped.

        MEASURED 2026-09-10 05:20: `push_if_green` took this lock, gated green,
        pushed, was rejected because another lane had landed first, and ran
        `git rebase origin/main` to recover exactly as designed. This hook read
        the lock, found a LIVE holder, and refused - and the holder was the
        rebasing process itself. `PUSH REFUSED: the rebase did not succeed, so
        there is no tree to gate.` The guard blocked its own recovery.

        The lock now exports its holder's pid, so a process git spawns UNDER
        the holder can tell "somebody is gating here" from "I am the one
        gating here". Inheritance is the relation being asked about, which is
        why it is an environment variable rather than a walk up the process
        tree.
        """
        import os

        me = os.getpid()
        self._write_lock(me, self._born(me), command="push_if_green")
        refused = self.run_hook()
        self.assertEqual(1, refused.returncode, "the control: a stranger is refused")

        allowed = self.run_hook(env={**os.environ, "MLH_HOLDS_THE_GATE_LOCK": str(me)})
        self.assertEqual(
            0, allowed.returncode,
                "the lock owner was refused its own recovery: " + allowed.stderr,
        )

    def test_a_lock_held_by_somebody_else_is_not_waved_through(self):
        """The pid is compared, not the variable's presence. A lane holding
        ANOTHER checkout's lock must not wave itself through this one."""
        import os

        me = os.getpid()
        self._write_lock(me, self._born(me))
        done = subprocess.run(
            [sys.executable, str(self.hook)],
            cwd=self.tree, capture_output=True, text=True,
            env={**os.environ, "MLH_HOLDS_THE_GATE_LOCK": "999999"},
        )
        self.assertEqual(1, done.returncode, "a mismatched pid was accepted")

    def test_it_asks_git_where_the_hooks_go(self):
        """NOT `<repo>/.git/hooks`, which is wrong in a worktree - and worktrees
        are what this whole change asks every lane to start using."""
        where = install_hooks.hooks_dir(self.tree)
        self.assertTrue(where.is_absolute())
        self.assertEqual("hooks", where.name)

    # -- helpers ------------------------------------------------------------

    def _born(self, pid: int) -> str:
        said = subprocess.run(
            [sys.executable, "-c",
             "import importlib.util,sys;"
             f"s=importlib.util.spec_from_file_location('l', r'{self.tree}/scripts/one_gate_at_a_time.py');"
             "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
             f"print(m.born_when({pid}))"],
            capture_output=True, text=True, check=True,
        )
        return said.stdout.strip()

    def _a_dead_pid(self) -> int:
        """A pid that has CERTAINLY exited, because we started it and waited.

        The first version of this reached for `subprocess.run(...).pid`, which
        does not exist on `CompletedProcess`, and fell through to a hardcoded
        999999 - a number nobody had checked was free. A stale-lock test whose
        pid might be live is a test that could pass for the wrong reason.
        """
        process = subprocess.Popen([sys.executable, "-c", "pass"])
        process.wait()
        return process.pid


if __name__ == "__main__":
    unittest.main()
