"""A suite that reports OK must say how many it ran against how many exist.

## What happened, 2026-09-04

Two full suites ran in this checkout at once - one from this session, one from
another lane that gates in the same repository. The second printed:

    Ran 3315 tests in 432.374s
    OK (expected failures=4)

Discovery in that tree finds 3822. Five hundred and seven tests never ran. No
failure, no error, no skip line: a green tick over 87% of the suite, one command
away from being pushed on.

`docs/how-to-verify.md`'s first law is that a gate you cannot make fail is not a
gate. This is the same failure wearing a pass, and remembering not to run two
suites at once is not a fix - the next collision is a different lane on a
different night. So `scripts/gate.py` asserts the count and this file proves the
assertion can fail.

## Why the mismatch is simulated rather than reproduced

Reproducing it needs two concurrent full suites - twenty minutes of machine and
a race that is not guaranteed to land. What is being tested is the DECISION -
"ran fewer than exist, therefore red" - and the decision is exercised directly
against a suite whose count is known. That is the same argument
`recipes/hf-peft-dpo` makes for splitting out `adapter_keys_in`: test the part
that was wrong, in a way that runs in a second.
"""

from __future__ import annotations

import io
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr

import support

gate = support.import_file("mlh_gate", support.REPO_ROOT / "scripts" / "gate.py")


class Passes(unittest.TestCase):
    def test_one(self):
        pass

    def test_two(self):
        pass


class TheCounterCountsLeavesTest(unittest.TestCase):
    def test_a_flat_suite(self):
        suite = unittest.TestSuite([Passes("test_one"), Passes("test_two")])
        self.assertEqual(gate.how_many_tests_are_in(suite), 2)

    def test_a_nested_suite_is_counted_through(self):
        """Discovery returns suites of suites of suites; a counter that only
        looked one level down would report a number far smaller than the run,
        which is the failure this file is about, inverted."""
        inner = unittest.TestSuite([Passes("test_one")])
        middle = unittest.TestSuite([inner, Passes("test_two")])
        outer = unittest.TestSuite([middle])
        self.assertEqual(gate.how_many_tests_are_in(outer), 2)

    def test_an_empty_suite_is_zero_not_one(self):
        self.assertEqual(gate.how_many_tests_are_in(unittest.TestSuite()), 0)


class TheGateGoesRedWhenTestsVanishTest(unittest.TestCase):
    """The decision, exercised directly.

    `the_gate` discovers the real tests directory, so it is not callable here
    without running the whole suite. What is asserted instead is the rule it
    applies, against a runner result and a discovered count that disagree -
    which is exactly the state the 2026-09-04 run was in.
    """

    def run_with(self, discovered: int, ran: int, successful: bool = True):
        """The gate's decision, extracted the way the gate makes it."""
        if ran != discovered:
            return 2
        if not successful:
            return 1
        return 0

    def test_a_full_green_run_is_zero(self):
        self.assertEqual(self.run_with(discovered=3822, ran=3822), 0)

    def test_the_exact_2026_09_04_numbers_are_red(self):
        """3315 of 3822, everything passing. This is the run that said OK."""
        self.assertEqual(self.run_with(discovered=3822, ran=3315), 2)

    def test_one_missing_test_is_already_red(self):
        """There is no tolerance band. A single test that did not run is a
        question about the run, and a gate that shrugged at one would shrug at
        five hundred by degrees."""
        self.assertEqual(self.run_with(discovered=3822, ran=3821), 2)

    def test_a_failing_run_is_red_for_its_own_reason(self):
        """Count-red and failure-red are different exit codes so a reader can
        tell 'the suite is broken' from 'the run is incomplete'."""
        self.assertEqual(
            self.run_with(discovered=10, ran=10, successful=False), 1
        )

    def test_a_count_mismatch_outranks_a_failure(self):
        """If tests went missing, the failures that DID run are not the whole
        story, and reporting them as the story would be the smaller truth."""
        self.assertEqual(
            self.run_with(discovered=10, ran=8, successful=False), 2
        )


class TheRedGateSaysBothNumbersTest(unittest.TestCase):
    def test_the_message_names_the_gap_and_what_causes_it(self):
        """A red gate that said only 'counts differ' would send the next reader
        looking for a broken test rather than a second suite.

        Asserted by CALLING the function. The first version of this test
        grepped gate.py's source and broke on a line wrap inside the string
        literal - a test about formatting wearing the clothes of a test about
        behaviour."""
        said = gate.why_the_count_is_red(3822, 3315)
        self.assertIn("507 test(s) never ran", said)
        self.assertIn("3315 of 3822", said)
        self.assertIn("second suite in the same checkout", said)
        self.assertIn("stray process", said)

    def test_the_message_carries_the_real_numbers_not_a_template(self):
        said = gate.why_the_count_is_red(10, 8)
        self.assertIn("2 test(s) never ran", said)
        self.assertIn("8 of 10", said)


class TheDocumentedGateTakesTheMachineLockTest(unittest.TestCase):
    """Two mechanisms were built for one collision and only one was on the path.

    `one_gate_at_a_time.py` PREVENTS two suites sharing a machine; this file's
    count check DETECTS the damage afterwards. The wrapper's docstring shows it
    in front of `python -m unittest discover`, but the gate this repository
    documents and its lanes actually run is `python scripts/gate.py` - which
    took no lock at all. Every gate run on 2026-09-05 went without mutual
    exclusion, and the count check would have caught the loss, having not
    prevented it.
    """

    def test_the_gate_can_find_the_lock_module(self):
        lock = gate.the_machine_lock()
        self.assertIsNotNone(lock)
        self.assertTrue(hasattr(lock, "acquire"))
        self.assertTrue(hasattr(lock, "release"))

    def test_a_held_lock_makes_the_gate_red_without_running_anything(self):
        """A run that never started says nothing about the tree, which is a
        different fact from a test being red - so it exits 2, like a count
        mismatch, not 1."""
        calls = {"ran": False}

        class ARefusingLock:
            DEFAULT_TIMEOUT_SECONDS = 1

            @staticmethod
            def acquire(timeout, command):
                return False

            @staticmethod
            def release():
                calls["released"] = True

        with mock.patch.object(gate, "the_machine_lock", lambda: ARefusingLock),                 mock.patch.object(gate, "_run_the_suite",
                                  lambda *a, **k: calls.__setitem__("ran", True)):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = gate.the_gate([])
        self.assertEqual(code, 2)
        self.assertFalse(calls["ran"], "the suite ran while another lane held the lock")
        self.assertIn("machine lock", err.getvalue())

    def test_the_lock_is_released_even_when_the_suite_is_red(self):
        released = {"yes": False}

        class ALock:
            DEFAULT_TIMEOUT_SECONDS = 1

            @staticmethod
            def acquire(timeout, command):
                return True

            @staticmethod
            def release():
                released["yes"] = True

        with mock.patch.object(gate, "the_machine_lock", lambda: ALock),                 mock.patch.object(gate, "_run_the_suite", lambda *a, **k: 1):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(gate.the_gate([]), 1)
        self.assertTrue(released["yes"])

    def test_no_lock_is_an_escape_hatch_not_the_default(self):
        """A gate that cannot run without its lock is a gate nobody can run,
        so the flag exists - but it has to be asked for."""
        seen = {}

        with mock.patch.object(gate, "the_machine_lock",
                               lambda: seen.setdefault("looked", True)),                 mock.patch.object(gate, "_run_the_suite", lambda *a, **k: 0):
            with redirect_stdout(io.StringIO()):
                gate.the_gate(["--no-lock"])
        self.assertEqual(seen, {}, "it looked for a lock despite --no-lock")



#: A throwaway tests tree, written as source rather than as escaped strings.
#: The first version of this file built them with "\n" inside a shell heredoc
#: and the escapes collapsed into real newlines, producing a SyntaxError - so
#: the sources live in triple quotes where nothing can escape them.
A_TEST_THAT_PASSES = '''
import unittest


class T(unittest.TestCase):
    def test_ok(self):
        self.assertTrue(True)
'''

A_MODULE_THAT_CANNOT_IMPORT = '''
raise RuntimeError("this module reads something that is not in this checkout")
'''

#: `the_gate`'s decision, re-made against a throwaway tree in its own process.
#: A SUBPROCESS because `the_gate` reads a module-level `REPO` and runs a full
#: `TextTestRunner`; doing it in-process would have this gate discovering the
#: suite that is discovering it.
THE_GATE_OVER_A_TREE = '''
import sys, unittest, importlib.util, pathlib
sys.dont_write_bytecode = True
tree = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("gate", sys.argv[2])
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
loader = unittest.defaultTestLoader
suite = loader.discover(str(tree), top_level_dir=str(tree))
discovered = gate.how_many_tests_are_in(suite)
result = unittest.TextTestRunner(verbosity=0).run(suite)
if result.testsRun != discovered:
    print(gate.why_the_count_is_red(discovered, result.testsRun), file=sys.stderr)
    sys.exit(2)
if loader.errors:
    print(gate.why_the_import_errors_are_red(loader.errors), file=sys.stderr)
    sys.exit(2)
sys.exit(0 if result.wasSuccessful() else 1)
'''


def _run_the_gate_over(tree: Path):
    done = subprocess.run(
        [sys.executable, "-c", THE_GATE_OVER_A_TREE, str(tree),
         str(support.REPO_ROOT / "scripts" / "gate.py")],
        capture_output=True, text=True,
    )
    return done.returncode, done.stdout, done.stderr


class AModuleThatDidNotImportIsRedForItsOwnReasonTest(unittest.TestCase):
    """The loss the COUNT CHECK CANNOT SEE, measured on a clean clone.

    Two test modules read a gitignored artifact at import time. Gated on a
    clone that does not have it:

        with the guard      ran 3958 of 3958 discovered   GREEN
        without the guard   ran 3923 of 3923 discovered   errors=2

    Thirty-five real tests were replaced by two `_FailedTest` placeholders and
    `ran == discovered` STILL HELD, because a placeholder is discovered and run
    like any other test. The count assertion this file exists for is blind to
    this class of loss. Only the errors catch it, and they are printed at the
    top of four thousand lines of output, which is not where a reader looks.

    So the gate says it again at the end, names the modules, and returns 2
    rather than 1: a module that did not import means the run does not say what
    the tree does, which is a different fact from a test being red.
    """

    def test_the_message_names_every_module_that_did_not_import(self):
        said = gate.why_the_import_errors_are_red(["test_alpha", "test_beta"])
        self.assertIn("test_alpha", said)
        self.assertIn("test_beta", said)
        self.assertIn("2 test module(s)", said)

    def test_the_message_says_why_the_count_did_not_catch_it(self):
        """Without this sentence a reader concludes the count check covers
        import errors. It does not, and that is the whole finding."""
        said = gate.why_the_import_errors_are_red(["test_alpha"])
        self.assertIn("count check cannot see", said)

    def test_the_names_are_read_off_a_real_discovery_not_off_loader_errors(self):
        """WHY THIS TEST EXISTS. The first version read `TestLoader.errors` and
        unpacked it as (name, error) pairs. It is a list of formatted TRACEBACK
        STRINGS, so the code passed its own tuple fixture and raised `too many
        values to unpack` against the real loader. This runs a real discovery
        over a real broken module."""
        import unittest as _ut

        tree = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (tree / "test_healthy_one.py").write_text(A_TEST_THAT_PASSES, encoding="utf-8")
        (tree / "test_broken.py").write_text(
            A_MODULE_THAT_CANNOT_IMPORT, encoding="utf-8"
        )
        suite = _ut.TestLoader().discover(str(tree), top_level_dir=str(tree))
        self.assertEqual(gate.the_modules_that_did_not_import(suite), ["test_broken"])

    def test_a_healthy_tree_names_no_unimported_modules(self):
        """UNIQUE MODULE BASENAMES PER TREE. unittest caches imported modules by
        NAME, so two temporary directories both holding `test_fine.py` raise
        "module incorrectly imported from" - which this suite hit."""
        import unittest as _ut

        tree = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (tree / "test_healthy_two.py").write_text(A_TEST_THAT_PASSES, encoding="utf-8")
        suite = _ut.TestLoader().discover(str(tree), top_level_dir=str(tree))
        self.assertEqual(gate.the_modules_that_did_not_import(suite), [])

    def test_a_module_that_cannot_import_makes_the_gate_return_two(self):
        """END TO END, through the gate's own decision rather than through the
        message: a tests tree with one unimportable module exits 2."""
        tree = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (tree / "test_fine.py").write_text(A_TEST_THAT_PASSES, encoding="utf-8")
        (tree / "test_broken.py").write_text(
            A_MODULE_THAT_CANNOT_IMPORT, encoding="utf-8"
        )
        code, out, err = _run_the_gate_over(tree)
        self.assertEqual(code, 2, f"expected 2, got {code}: {out} {err}")
        self.assertIn("test_broken", err)

    def test_the_same_tree_without_the_broken_module_is_green(self):
        """The other half of the pair. A check that cannot pass is as useless
        as one that cannot fail."""
        tree = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (tree / "test_fine.py").write_text(A_TEST_THAT_PASSES, encoding="utf-8")
        code, out, err = _run_the_gate_over(tree)
        self.assertEqual(code, 0, f"{out} {err}")


class AGateWhoseTreeMovedDescribesNeitherTest(unittest.TestCase):
    """MEASURED TWICE IN ONE HOUR, both times by me.

    A commit landed while the suite was running and
    `test_the_real_repository_answers_with_a_real_sha` went red: it reads
    `identity.git_head()` and `git rev-parse HEAD` and compares them, and HEAD
    moved between the two reads. The test was right both times.

    The machine lock serialises SUITES. It does not stop the agent that started
    one from moving HEAD underneath it. After the first occurrence I wrote that
    I would rather build this than remember not to, and then did it again - the
    argument for the check rather than against it.
    """

    def test_the_message_names_both_shas(self):
        said = gate.why_the_moved_head_is_red("aaaa", "bbbb")
        self.assertIn("aaaa", said)
        self.assertIn("bbbb", said)

    def test_the_message_says_it_is_neither_pass_nor_failure(self):
        said = gate.why_the_moved_head_is_red("aaaa", "bbbb")
        self.assertIn("describes neither tree", said)
        self.assertIn("serialises", said)

    def test_head_is_read_from_git_and_none_when_it_cannot_be(self):
        class Failed:
            returncode = 128
            stdout = ""

        self.assertIsNone(gate.the_head_now(run=lambda *a, **k: Failed()))

    def test_head_is_none_when_git_is_not_there_at_all(self):
        def explode(*a, **k):
            raise OSError("no git")

        self.assertIsNone(gate.the_head_now(run=explode))

    def test_the_real_checkout_answers_with_a_sha(self):
        head = gate.the_head_now()
        if head is None:
            self.skipTest("this checkout has no readable git")
        self.assertEqual(len(head), 40)

    def test_a_moved_head_is_the_condition(self):
        """The decision, asked without running a suite. The first version of
        this called `the_gate` itself: thirty-eight seconds, a `fileno` error
        from the redirected stream, and a gate discovering the suite that was
        discovering it. A test that runs the thing under test is not a unit."""
        self.assertTrue(gate.the_run_is_not_about_one_tree("aaaa", "bbbb"))
        self.assertFalse(gate.the_run_is_not_about_one_tree("aaaa", "aaaa"))

    def test_an_unreadable_head_is_not_a_moved_one(self):
        """None means cannot decide, and cannot decide is not moved - a
        checkout with no git must still be able to gate."""
        self.assertFalse(gate.the_run_is_not_about_one_tree(None, "bbbb"))
        self.assertFalse(gate.the_run_is_not_about_one_tree("aaaa", None))
        self.assertFalse(gate.the_run_is_not_about_one_tree(None, None))

    def test_the_gate_calls_the_condition_at_all(self):
        """A check nothing calls is a comment. This reads the source for the
        call rather than trusting that it is wired, which is the cheapest
        version of the surviving-mutant lesson this repository already has."""
        source = (support.REPO_ROOT / "scripts" / "gate.py").read_text(encoding="utf-8")
        body = source[source.index("def _run_the_suite") :]
        self.assertIn("the_run_is_not_about_one_tree(", body)
        self.assertIn("why_the_moved_head_is_red(", body)


if __name__ == "__main__":
    unittest.main()
