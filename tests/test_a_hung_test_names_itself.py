"""A test that hangs prints a stack trace naming itself, rather than a slow run.

`docs/PHASES.md` carried this as a debt and stated it precisely:

    "A hanging test presents as a slow suite. There is no per-test bound, and
     2,848 tests at ~4.5 minutes under a 600-second timeout means *hung* and
     *slow* differ by a factor nobody has had to think about.
     `faulthandler.dump_traceback_later()` turns it into a stack trace that
     names the test."

That is the whole fix and it is in `tests/support.py`. This file is the proof
that it works, because a bound nobody has seen fire is a bound nobody knows the
shape of - and this one has three properties worth pinning down:

* it FIRES, on a test that really does stop;
* it does NOT fire on the ordinary case, which is every other test in this
  suite and is where a wrong bound would cost the most;
* it does not KILL the run. `exit=True` would turn one hung test into no
  results at all, which is exactly the state this exists to get out of.

**Why the hang is a subprocess and not a `while True` here.** The bound prints a
traceback and lets the run continue, so a test that hung on purpose in THIS
process would hang this process on purpose - the suite would be down a thread
for a minute to prove a point. A child interpreter with a short budget proves
the same three properties in a second and leaves nothing behind.
"""

import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

import support

ROOT = Path(__file__).resolve().parents[1]


#: The child suite. `{sleep}` is how long the hanging test stops for - four
#: seconds in the cases about the bound firing, zero in the negative control, so
#: that "an ordinary test does not trip it" is a statement about ORDINARY tests
#: rather than about a shorter hang.
#:
#: FOUR AND NOT THIRTY. The timer fires at the budget, but the sleeping test
#: keeps sleeping, so the child's wall-clock is the SLEEP and not the bound.
#: Thirty put a minute on a four-and-a-half-minute suite to prove something four
#: seconds proves: this file is about a bound on time and should not spend it.
THE_CHILD_SUITE = '''
import sys, time, unittest
sys.path.insert(0, {tests!r})
import support  # arms the bound at import


class ItStops(unittest.TestCase):
    def test_the_one_that_hangs(self):
        time.sleep({sleep})

    def test_the_one_that_does_not(self):
        self.assertTrue(True)


unittest.main(verbosity=0)
'''


class TheBoundFiresAndNamesTheTestTest(unittest.TestCase):
    def _run_child(self, budget: str, sleep: int = 4):
        script = THE_CHILD_SUITE.format(tests=str(ROOT / "tests"), sleep=sleep)
        environment = dict(os.environ, MLH_TEST_TIMEOUT=budget)
        return subprocess.run(
            [sys.executable, "-c", textwrap.dedent(script)],
            capture_output=True,
            text=True,
            timeout=90,
            cwd=str(ROOT),
            env=environment,
        )

    def test_a_hung_test_prints_a_stack_that_names_it(self):
        finished = self._run_child("1")
        output = finished.stdout + finished.stderr

        self.assertIn("Timeout (0:00:01)!", output, output[-800:])
        # The name of the test, in the trace, which is the entire point: the
        # symptom this replaces is a run that took nine minutes and said
        # nothing about which of three thousand tests took eight of them.
        self.assertIn("test_the_one_that_hangs", output, output[-800:])

    def test_it_does_not_kill_the_run_and_the_other_test_still_reports(self):
        """`exit=False`. One hung test must not cost the results of the rest."""
        finished = self._run_child("1")
        output = finished.stdout + finished.stderr
        self.assertIn("Ran 2 tests", output, output[-800:])

    def test_an_ordinary_test_never_trips_it(self):
        """The negative, and it is the half that would cost the most if it were
        wrong: a bound that fires on healthy tests is noise, and noise in a
        suite is how a real trace gets scrolled past."""
        finished = self._run_child("5", sleep=0)
        output = finished.stdout + finished.stderr
        self.assertNotIn("Timeout (", output, output[-800:])
        self.assertIn("Ran 2 tests", output, output[-800:])


class TheBoundIsArmedForThisRunTest(unittest.TestCase):
    def test_importing_support_bounds_every_test_in_the_process(self):
        """The mechanism, asserted rather than described. The patch is on
        `unittest.TestCase.run`, so the first module to import `support` arms
        the bound for every test that runs after it in the same process -
        including the forty-odd modules in this suite that never import it."""
        self.assertTrue(getattr(unittest.TestCase, "_mlh_time_bounded", False))
        self.assertGreater(support.TEST_TIME_BUDGET_SECONDS, 0)

    def test_arming_twice_does_not_stack_the_patch(self):
        """`discover` imports 134 modules that import this one. Wrapping the
        wrapper 134 times would put 134 timer calls around every test."""
        before = unittest.TestCase.run
        support._bound_every_test()
        self.assertIs(before, unittest.TestCase.run)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
