"""A push runs the frontend's own tests and its typed build, or it refuses.

Max, in the ask this file answers: *"scripts/push_if_green.py gates via
scripts/gate.py, which runs unittest discovery only. Add a frontend step."*

## What was measured

`scripts/gate.py` is unittest discovery. It never opens a `.ts` file, never
runs `tsc`, and never runs vitest. The record already carries the shorter
sentence for what that costs - THE GATE DOES NOT READ CSS - written after a
stray brace in `whiteboard.css` passed 5,393 tests and failed in `vite build`,
and after `encode before you open for write` truncated a stylesheet to zero
lines and the build shipped it. Both are green-gate, broken-product.

A green gate is a statement about the Python. A push is an act of publication,
and what is published is the whole product. So the two frontend commands run
between the green gate and the push, and each is judged by its EXIT CODE - the
same rule this whole script exists to hold, from the day a `grep` succeeded and
pushed a red gate to main.

## The four laws held here

1. **Both commands are invoked**, in order, after a green gate.
2. **Either non-zero refuses the push**, and the code it returns is the one the
   command gave, not a code this step invented.
3. **A missing `frontend/node_modules` skips, LOUDLY.** Nothing can run without
   it. A silent skip is how a check stops existing without anybody deciding to
   remove it, so the skip prints and names the directory.
4. **npm failing to START is a refusal, not a skip.** A broken machine and a
   checkout with no frontend installed must not produce the same silence, which
   is the entire shape of law 3.

Nothing here runs npm. The commands are asserted against a recorder, exactly as
the gate and the push already are in
`tests/test_a_push_reads_the_gates_exit_code.py`; a test that really built the
frontend would take a minute per case and would be measuring node.
"""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import support

pusher = support.import_file(
    "push_if_green", support.REPO_ROOT / "scripts" / "push_if_green.py"
)

A_GATED_SHA = "d5326599ee8662465acfce4cb4c51a0d323d8b0a"


class ARunThatRecordsNpm:
    """Answers git, and hands npm whichever codes the case is about.

    `git status` and `git rev-parse` are answered rather than counted, for the
    reason the sibling file states at length: they are questions the step asks
    about its own checkout, not outcomes a case is setting up.
    """

    def __init__(self, gate=0, push=0, frontend=(0, 0)):
        self.gate = int(gate)
        self.push = int(push)
        self.frontend = list(frontend)
        self.npm: list[list[str]] = []
        self.pushes: list[list[str]] = []
        self.gated = 0

    def __call__(self, command, *args, **kwargs):
        command = list(command)
        if command[:2] == ["git", "rev-parse"]:
            class Resolved:
                returncode = 0
                stdout = A_GATED_SHA + chr(10)

            return Resolved()
        if command[0] == "git" and "status" in command:
            class Clean:
                returncode = 0
                stdout = ""

            return Clean()
        if any("gate.py" in str(part) for part in command):
            self.gated += 1
            code = self.gate

            class Gated:
                returncode = code

            return Gated()
        head = str(command[0]).replace(chr(92), "/").rsplit("/", 1)[-1].lower()
        if head.startswith("npm"):
            self.npm.append(command)
            code = self.frontend.pop(0) if self.frontend else 0

            class Checked:
                returncode = code

            return Checked()
        if command[:2] == ["git", "push"]:
            self.pushes.append(command)
            code = self.push

            class Pushed:
                returncode = code

            return Pushed()

        class Done:
            returncode = 0

        return Done()


class AFakeLock:
    """The machine lock, never the real one.

    The sibling file paid for this twice: a case that reached for the real lock
    from inside a suite its own gate was holding waited an hour on its parent.
    Every case here passes one, and `push_lock=False` for the same reason.
    """

    DEFAULT_TIMEOUT_SECONDS = 1

    def __init__(self):
        self.taken = 0
        self.released = 0

    def acquire(self, timeout, command):
        self.taken += 1
        return True

    def release(self):
        self.released += 1

    def waited_seconds(self):
        return 0.0


def _certifiable(test) -> None:
    """Give the step a release-rules file of this test's own.

    `scripts/release/identifiers.json` is GITIGNORED AND PER-CHECKOUT, and
    `push_if_green` refuses before the gate when it is absent. Every case in
    this file is about what happens AFTER a green gate, so a case that read
    whichever file happens to be on disk would assert the frontend laws on the
    owner's machine and assert nothing at all in a fresh worktree or on CI -
    where the refusal fires first and every case goes green for the wrong
    reason. A test must own its specimen, so this one makes it.
    """
    import tempfile

    temp = tempfile.TemporaryDirectory()
    test.addCleanup(temp.cleanup)
    rules = Path(temp.name) / "identifiers.json"
    rules.write_bytes(b"{}")
    was = pusher.THE_RELEASE_RULES
    pusher.THE_RELEASE_RULES = rules
    test.addCleanup(lambda: setattr(pusher, "THE_RELEASE_RULES", was))


def _installed(test) -> None:
    """Point the step at a `node_modules` that exists, in this test's own temp.

    NOT AT THE REPOSITORY'S. Whether this developer has run `npm ci` is not a
    property of the law - a case that read the real directory would assert the
    frontend is checked on a machine with node and assert nothing at all on a
    machine without, and the second machine is CI. A probe must own its
    specimen.
    """
    import tempfile

    temp = tempfile.TemporaryDirectory()
    test.addCleanup(temp.cleanup)
    modules = Path(temp.name) / "node_modules"
    modules.mkdir(parents=True)
    was = pusher.FRONTEND_MODULES
    pusher.FRONTEND_MODULES = modules
    test.addCleanup(lambda: setattr(pusher, "FRONTEND_MODULES", was))


def _absent(test) -> None:
    """Point it at a directory that is not there. The same ownership rule."""
    import tempfile

    temp = tempfile.TemporaryDirectory()
    test.addCleanup(temp.cleanup)
    was = pusher.FRONTEND_MODULES
    pusher.FRONTEND_MODULES = Path(temp.name) / "never_installed"
    test.addCleanup(lambda: setattr(pusher, "FRONTEND_MODULES", was))


def _drive(run, lock=None):
    said, err = io.StringIO(), io.StringIO()
    with redirect_stdout(said), redirect_stderr(err):
        code = pusher.push_if_green(
            ["origin", "main"],
            run=run,
            lock=lock or AFakeLock(),
            push_lock=False,
        )
    return code, said.getvalue(), err.getvalue()


class BothCommandsAreInvokedTest(unittest.TestCase):
    """Law 1. The two commands Max named, in that order, after a green gate."""

    def setUp(self):
        _certifiable(self)
        _installed(self)

    def test_the_two_commands_run_in_order(self):
        run = ARunThatRecordsNpm()
        code, _said, err = _drive(run)
        self.assertEqual(0, code, err)
        self.assertEqual(
            [
                ["--prefix", "frontend", "run", "test", "--", "--run"],
                ["--prefix", "frontend", "run", "build"],
            ],
            [c[1:] for c in run.npm],
        )

    def test_the_separator_is_there_so_vitest_does_not_watch(self):
        """`--` is npm's, not vitest's. Without it npm eats `--run`, vitest
        starts its WATCHER, and the push waits behind a file watcher for ever -
        which is a hang, not a failure, and hangs do not report themselves."""
        tests = dict(pusher.THE_FRONTEND_CHECKS)["the frontend tests"]
        self.assertEqual(("--", "--run"), tests[-2:])

    def test_they_run_after_the_gate_and_before_the_push(self):
        """The order is the point. Spending a minute of vite on a tree whose
        Python is red buys nothing, and checking after the push checks nothing.
        """
        run = ARunThatRecordsNpm()
        _drive(run)
        self.assertEqual(1, run.gated)
        self.assertEqual(2, len(run.npm))
        self.assertEqual(1, len(run.pushes))

    def test_a_red_gate_never_reaches_them(self):
        run = ARunThatRecordsNpm(gate=1)
        code, _said, _err = _drive(run)
        self.assertEqual(1, code)
        self.assertEqual([], run.npm, "it spent a frontend build on a red tree")
        self.assertEqual([], run.pushes)


class EitherRedRefusesThePushTest(unittest.TestCase):
    """Law 2. The decision is the exit code, and it is the command's own."""

    def setUp(self):
        _certifiable(self)
        _installed(self)

    def test_failing_tests_refuse_the_push(self):
        run = ARunThatRecordsNpm(frontend=(1, 0))
        code, _said, err = _drive(run)
        self.assertEqual(1, code)
        self.assertEqual([], run.pushes, "it pushed on red frontend tests")
        self.assertIn("PUSH REFUSED", err)
        self.assertIn("the frontend tests", err)

    def test_a_failing_build_refuses_the_push(self):
        """The `whiteboard.css` case: every test green, `vite build` red."""
        run = ARunThatRecordsNpm(frontend=(0, 2))
        code, _said, err = _drive(run)
        self.assertEqual(2, code)
        self.assertEqual([], run.pushes, "it published a tree that does not build")
        self.assertIn("the frontend build", err)

    def test_the_tests_failing_stops_before_the_build(self):
        """Nothing is learned by building a tree whose tests just failed, and a
        minute of vite is a minute nobody gets back."""
        run = ARunThatRecordsNpm(frontend=(1, 0))
        _drive(run)
        self.assertEqual(1, len(run.npm))

    def test_the_code_returned_is_the_commands_own(self):
        """Not a code this step invented. A caller reading 3 and being handed 1
        cannot tell a failed suite from a refusal, which is the confusion the
        gate's own `WHAT_THE_GATE_MEANT` table exists to prevent."""
        run = ARunThatRecordsNpm(frontend=(3, 0))
        code, _said, _err = _drive(run)
        self.assertEqual(3, code)

    def test_both_green_still_pushes(self):
        """THE CONTROL. Without it this change would have stopped every push on
        the machine rather than the wrong ones."""
        run = ARunThatRecordsNpm(frontend=(0, 0))
        code, _said, err = _drive(run)
        self.assertEqual(0, code, err)
        self.assertEqual(1, len(run.pushes))


class AMissingInstallSkipsOutLoudTest(unittest.TestCase):
    """Law 3. Nothing can run without `node_modules`, and the skip is said."""

    def setUp(self):
        _certifiable(self)
        _absent(self)

    def test_nothing_is_run_and_the_push_goes_ahead(self):
        run = ARunThatRecordsNpm()
        code, _said, err = _drive(run)
        self.assertEqual(0, code, err)
        self.assertEqual([], run.npm)
        self.assertEqual(1, len(run.pushes))

    def test_the_skip_is_printed_and_names_the_directory(self):
        """A silent skip is how a check stops existing without anybody deciding
        to remove it. It prints, it says FRONTEND NOT CHECKED, and it names the
        path so the reader can see why."""
        run = ARunThatRecordsNpm()
        _code, said, _err = _drive(run)
        self.assertIn("FRONTEND NOT CHECKED", said)
        self.assertIn("node_modules", said)
        self.assertIn("npm ci", said)

    def test_it_does_not_install_anything(self):
        """A step that installed a dependency tree in order to certify a push
        would be changing the thing it is certifying."""
        run = ARunThatRecordsNpm()
        _drive(run)
        self.assertEqual([], [c for c in run.npm if "ci" in c])


class NpmThatWillNotStartIsARefusalTest(unittest.TestCase):
    """Law 4. A broken machine is not a checkout without a frontend."""

    def setUp(self):
        _certifiable(self)
        _installed(self)

    def test_an_os_error_refuses_rather_than_skipping(self):
        class NpmIsGone(ARunThatRecordsNpm):
            def __call__(self, command, *args, **kwargs):
                head = (
                    str(command[0]).replace(chr(92), "/").rsplit("/", 1)[-1].lower()
                )
                if head.startswith("npm"):
                    raise OSError(2, "No such file or directory")
                return super().__call__(command, *args, **kwargs)

        run = NpmIsGone()
        code, _said, err = _drive(run)
        self.assertEqual(2, code)
        self.assertEqual([], run.pushes)
        self.assertIn("could not be run at all", err)

    def test_the_two_silences_are_different(self):
        """The skip is on stdout under a push that HAPPENED; the refusal is on
        stderr under a push that did not. Read the sentences rather than the
        mechanism: if these two ever converged, law 3 would have eaten law 4.
        """
        self.assertNotIn(
            "could not be run", pusher.THE_FRONTEND_WAS_NOT_CHECKED
        )
        self.assertNotIn(
            "NOT CHECKED", pusher.why_the_frontend_could_not_run("x", "y")
        )


class TheResolvedNpmIsTheOneThatStartsTest(unittest.TestCase):
    """On Windows the thing on PATH is `npm.cmd`, and the bare name raises."""

    def test_it_is_resolved_through_which(self):
        found = pusher.the_npm_command()
        head = str(found).replace(chr(92), "/").rsplit("/", 1)[-1].lower()
        self.assertTrue(head.startswith("npm"), found)

    def test_the_fallback_names_npm_rather_than_none(self):
        """A machine with no npm must produce a refusal that says `npm`, not
        one that says `None` and sends the reader looking for a bug here."""
        import shutil

        was = shutil.which
        shutil.which = lambda name, *a, **k: None
        try:
            self.assertEqual("npm", pusher.the_npm_command())
        finally:
            shutil.which = was


if __name__ == "__main__":
    unittest.main()
