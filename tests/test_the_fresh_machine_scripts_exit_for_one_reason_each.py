"""Each fresh-machine exit has a case producing only it - and each CAUSE does.

## The rule, and the extra half these two scripts needed

*A probe that trips two branches at once proves neither in isolation.* Applied to
`rent_an_hour.py` it found a run that could not count its workload returning the
same codes as a fully priced one.

**These two needed the rule at one more level down.** `one_click_on_a_fresh_machine.py`
and `the_stranger_on_a_fresh_machine.py` each return `2` for **three unrelated
causes** - no interpreter or no sandbox binary, a sandbox already open, and (in
the stranger) a script that does not parse - and `one_click` returns `0` for two,
`--write-only` and a real answered page.

A test asserting *exit 2* proves whichever cause it happened to trigger. So each
CAUSE gets a case here, not each code.

**Whether one code for three causes is a defect is not settled here**, and this
file deliberately does not force that. It is defensible: all three mean *this
machine cannot run it now*, and a caller's response to each is the same - stop.
What is not defensible is nobody having checked which one fires. `rent_an_hour`
was different because its collapsed states wanted DIFFERENT responses: *your
budget is short* and *I cannot count the workload* are not the same instruction.

## Nothing here launches a sandbox

Every case patches the world at the boundary - `Path.exists`, `subprocess.run`,
`subprocess.Popen`. A test that started Windows Sandbox would take minutes, need
a feature not every machine has, and be skipped everywhere it mattered.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest import mock

import support

one_click = support.import_file(
    "one_click_on_a_fresh_machine",
    support.REPO_ROOT / "scripts" / "one_click_on_a_fresh_machine.py",
)
stranger = support.import_file(
    "the_stranger_on_a_fresh_machine",
    support.REPO_ROOT / "scripts" / "the_stranger_on_a_fresh_machine.py",
)


#: THE REAL ONE, captured before anything is patched.
#:
#: PATCHING `Path.exists` WHOLESALE BREAKS `Path.glob`. In CPython 3.11 a glob
#: with a LITERAL segment resolves it through `exists()`, so a patch returning
#: True for everything made `OUT.glob("finished")` yield a file that was not
#: there and the script died unlinking it. The fake now answers only for the
#: paths a case is deliberately faking and delegates everything else.
REALLY_EXISTS = Path.exists


class Answered:
    """`subprocess.run`'s reply, with only the field these scripts read."""

    def __init__(self, stdout=""):
        self.stdout = stdout
        self.returncode = 0


def no_sandbox_running(*a, **k):
    return Answered("0")


def a_sandbox_running(*a, **k):
    return Answered("1")


def parses_cleanly(*a, **k):
    return Answered("")


class OneClickExitsForOneReasonEachTest(unittest.TestCase):
    """Five causes, three codes."""

    def run_it(self, argv, *, interpreter=True, exe=True, running="0", answers=False, tmp=None):
        #: THE FAKE SANDBOX WRITES THE PAGE, and it has to be done here rather
        #: than before the call: the script CLEARS `OUT` of stale files before
        #: it launches, so a page created in advance is deleted and the case
        #: then sits out its whole wait. Modelling the launch is both correct
        #: and the difference between a 30-second case and an instant one.
        def launch(*a, **k):
            if answers and tmp is not None:
                (tmp / "page.txt").write_text("the page" + chr(10), encoding="utf-8")
                (tmp / "finished").write_text("", encoding="utf-8")
            return None

        def exists(self):
            name = str(self)
            if "WindowsSandbox.exe" in name:
                return exe
            if name == str(one_click.INTERPRETER):
                return interpreter
            return REALLY_EXISTS(self)

        with mock.patch.object(one_click, "OUT", tmp or one_click.OUT), \
             mock.patch.object(Path, "exists", exists), \
             mock.patch.object(subprocess, "run", lambda *a, **k: Answered(running)), \
             mock.patch.object(subprocess, "Popen", launch):
            return one_click.main(argv)

    def setUp(self):
        import tempfile

        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: None)

    def test_no_interpreter_is_exit_2(self):
        code = self.run_it(["--write-only"], interpreter=False, tmp=self.tmp)
        self.assertEqual(code, 2)

    def test_write_only_with_an_interpreter_is_exit_0(self):
        """A DIFFERENT CAUSE OF THE SAME CODE as the answered page below - it
        writes the config and stops, having launched nothing."""
        code = self.run_it(["--write-only"], tmp=self.tmp)
        self.assertEqual(code, 0)
        self.assertTrue((self.tmp / "one-click.wsb").is_file(), "it did not write the config")

    def test_no_sandbox_binary_is_exit_2(self):
        code = self.run_it([], exe=False, tmp=self.tmp)
        self.assertEqual(code, 2)

    def test_a_sandbox_already_open_is_exit_2(self):
        """The third cause of 2, and the one with a measured incident behind it:
        a run waited the full 420 seconds for a page that could never be
        written, because the previous sandbox was still open."""
        code = self.run_it([], running="1", tmp=self.tmp)
        self.assertEqual(code, 2)

    def test_no_page_within_the_wait_is_exit_1(self):
        code = self.run_it(["--wait", "0"], tmp=self.tmp)
        self.assertEqual(code, 1)

    def test_a_page_that_arrives_is_exit_0(self):
        """`answers=True` makes the fake launch write the page. Creating it
        BEFORE the call does not work - the script clears `OUT` of stale files
        first, which is what it should do, and the case then waits out its whole
        timeout for a page it deleted itself."""
        code = self.run_it(["--wait", "30"], answers=True, tmp=self.tmp)
        self.assertEqual(code, 0)

    def test_the_three_codes_are_reachable_and_distinct(self):
        """THE POINT. If two of these collapsed, one code would have no case
        that produces only it."""
        got = {
            self.run_it(["--write-only"], interpreter=False, tmp=self.tmp),
            self.run_it(["--wait", "0"], tmp=self.tmp),
            self.run_it(["--wait", "30"], answers=True, tmp=self.tmp),
        }
        self.assertEqual(got, {0, 1, 2})


class TheStrangerExitsForOneReasonEachTest(unittest.TestCase):
    """Five causes, three codes - and one cause `one_click` does not have."""

    def setUp(self):
        import tempfile

        self.tmp = Path(tempfile.mkdtemp())

    def run_it(self, argv, *, have=True, already_open=False, parse_errors="",
               answers=False, tmp=None):
        def launch(*a, **k):
            if answers and tmp is not None:
                (tmp / "stranger.txt").write_text("the page" + chr(10), encoding="utf-8")
                (tmp / "finished").write_text("", encoding="utf-8")
            return None

        def exists(self):
            name = str(self)
            if "WindowsSandbox.exe" in name or name == str(stranger.INTERPRETER):
                return have
            return REALLY_EXISTS(self)

        with mock.patch.object(stranger, "OUT", tmp or stranger.OUT), \
             mock.patch.object(Path, "exists", exists), \
             mock.patch.object(stranger, "a_sandbox_is_open", lambda: already_open), \
             mock.patch.object(stranger.subprocess, "run",
                               lambda *a, **k: Answered(parse_errors)), \
             mock.patch.object(stranger.subprocess, "Popen", launch):
            return stranger.main(argv)

    def test_no_sandbox_or_no_interpreter_is_exit_2(self):
        self.assertEqual(self.run_it([], have=False, tmp=self.tmp), 2)

    def test_a_sandbox_already_open_is_exit_2(self):
        self.assertEqual(self.run_it([], already_open=True, tmp=self.tmp), 2)

    def test_a_script_that_does_not_parse_is_exit_2(self):
        """THE CAUSE WITH THE SHARPEST INCIDENT: nine minutes waited for a page
        that was never going to be written, because of a statement list inside
        a cast on line 29. A wait that cannot succeed should say why."""
        code = self.run_it([], parse_errors="LINE 29: unexpected token", tmp=self.tmp)
        self.assertEqual(code, 2)

    def test_no_page_within_the_wait_is_exit_1(self):
        self.assertEqual(self.run_it(["--wait", "0"], tmp=self.tmp), 1)

    def test_a_page_that_arrives_is_exit_0(self):
        self.assertEqual(self.run_it(["--wait", "30"], answers=True, tmp=self.tmp), 0)

    def test_the_three_codes_are_reachable_and_distinct(self):
        got = {
            self.run_it([], have=False, tmp=self.tmp),
            self.run_it(["--wait", "0"], tmp=self.tmp),
            self.run_it(["--wait", "30"], answers=True, tmp=self.tmp),
        }
        self.assertEqual(got, {0, 1, 2})


class OneCodeCoversSeveralCausesAndThatIsRecordedTest(unittest.TestCase):
    """Saying so, because a reader counting codes would count three states."""

    def test_exit_two_has_three_causes_in_each_script(self):
        for module, name in ((one_click, "one_click_on_a_fresh_machine.py"),
                             (stranger, "the_stranger_on_a_fresh_machine.py")):
            with self.subTest(name=name):
                source = (support.REPO_ROOT / "scripts" / name).read_text(encoding="utf-8")
                self.assertGreaterEqual(
                    source.count("return 2"), 3,
                    f"{name} no longer returns 2 for three causes; update this file",
                )

    def test_this_file_says_whether_that_is_a_defect(self):
        """It is not settled here, and the reason is stated rather than left
        for a reader to infer - unlike `rent_an_hour`, whose collapsed states
        wanted DIFFERENT responses."""
        said = Path(__file__).read_text(encoding="utf-8")
        self.assertIn("is not settled here", said)


if __name__ == "__main__":
    unittest.main()
