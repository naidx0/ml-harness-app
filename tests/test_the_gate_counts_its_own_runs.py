"""The concurrency denominator is counted, not typed.

WHY. "N concurrent runs, 0 lost tests" has been carried by hand in
`docs/walks.md` since the machine lock was built. It was written as 3,
corrected to 5 an hour later, and was already 6 before that correction's own
gate had finished - the number moves faster than the run that verifies it. A
figure that goes stale inside the gate that checks it wants counting.

WHAT IS RECORDED, and it is the whole claim rather than a tally: how many tests
ran, how many were discovered, and how many other suites were live at the
verdict. `--history` turns those into the sentence that was being typed.

WHERE. Beside the machine lock in the system temp directory, for the lock's own
reason: this is a fact about the MACHINE and its lanes, and a file inside one
worktree would count only that worktree's runs.

BEST EFFORT, ALWAYS. A gate that went green must never go red because a log
could not be written, so every failure here is swallowed. That is the one place
in this file where silence is correct.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

NEWLINE = chr(10)
REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("gate_history", REPO / "scripts" / "gate.py")
gate = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(gate)


class TheGateCountsItsOwnRunsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        real = gate.HISTORY
        gate.HISTORY = Path(self.tmp.name) / "history.jsonl"
        self.addCleanup(lambda: setattr(gate, "HISTORY", real))

    def test_a_run_records_what_it_saw(self):
        gate.remember(ran=4107, discovered=4107, beside=3)
        row = json.loads(gate.HISTORY.read_text(encoding="utf-8").strip())
        self.assertEqual(row["ran"], 4107)
        self.assertEqual(row["discovered"], 4107)
        self.assertEqual(row["beside"], 3)
        self.assertIn("T", row["at"])

    def test_runs_accumulate_rather_than_replace(self):
        """One line per run. A file that held only the last run could not
        answer the question the number is for."""
        for n in range(3):
            gate.remember(ran=100 + n, discovered=100 + n, beside=n)
        self.assertEqual(len(gate.HISTORY.read_text(encoding="utf-8").splitlines()), 3)

    def test_a_log_that_cannot_be_written_does_not_fail_the_gate(self):
        """THE ONE THING THIS MUST NEVER DO. A green run that goes red because
        of its own bookkeeping would be the gate failing for a reason that has
        nothing to do with the tree."""
        gate.HISTORY = Path(self.tmp.name) / "no-such-directory" / "history.jsonl"
        gate.remember(ran=1, discovered=1, beside=0)  # must not raise

    def test_the_history_reports_the_denominator_it_was_built_for(self):
        gate.remember(ran=10, discovered=10, beside=0)
        gate.remember(ran=10, discovered=10, beside=2)
        gate.remember(ran=8, discovered=10, beside=1)
        import io
        from contextlib import redirect_stdout

        said = io.StringIO()
        with redirect_stdout(said):
            gate.the_history()
        text = said.getvalue()
        self.assertIn("gate runs recorded on this machine: 3", text)
        self.assertIn("concurrent suite: 2 of 3", text)
        self.assertIn("runs that lost tests:           1 of 2", text)

    def test_an_empty_history_says_so_rather_than_claiming_zero(self):
        """No runs recorded is not the same as no losses, and reporting the
        second from the first is how a denominator becomes a lie."""
        import io
        from contextlib import redirect_stdout

        said = io.StringIO()
        with redirect_stdout(said):
            gate.the_history()
        self.assertIn("nothing recorded yet", said.getvalue())


    def _run_the_gate_over_one_test(self, lock):
        """Run the real `_run_the_suite` over a one-test suite.

        THE STREAMS ARE REAL FILES, NOT StringIO. `tests/support.py` arms
        `faulthandler.dump_traceback_later` against stderr, and faulthandler
        needs a file descriptor - a StringIO raises `io.UnsupportedOperation:
        fileno`. Both cases below passed alone and errored in the full suite,
        because alone nothing had installed that runner yet. A test that only
        passes when it runs by itself is not passing.
        """
        import tempfile as _tempfile
        from contextlib import redirect_stdout, redirect_stderr

        tiny = unittest.TestSuite([_APassingTest("test_it_passes")])
        real_discover = unittest.defaultTestLoader.discover
        unittest.defaultTestLoader.discover = lambda *a, **k: tiny
        try:
            with _tempfile.TemporaryFile("w+", encoding="utf-8") as out,                  _tempfile.TemporaryFile("w+", encoding="utf-8") as err:
                with redirect_stdout(out), redirect_stderr(err):
                    code = gate._run_the_suite([], 0, lock)
                out.seek(0), err.seek(0)
                return code, out.read(), err.read()
        finally:
            unittest.defaultTestLoader.discover = real_discover

    def test_the_green_path_runs_to_the_end_with_a_lock(self):
        """THE CASE NOTHING COVERED, AND IT COST A FULL SUITE. Every test above
        calls `remember` directly. Nothing called the thing that calls it, so a
        name that did not exist in `_run_the_suite` - `lock` was the caller's
        local - survived review, printed GATE IS GREEN after 4,397 of 4,397
        passed, and then exited 1. `push_if_green` refused on the exit code,
        which is the only reason it was a wasted 12 minutes and not a green lie."""

        class ALockThatWaited:
            def waited_seconds(self):
                return 71.5

        code, said, grumbled = self._run_the_gate_over_one_test(ALockThatWaited())
        self.assertEqual(code, 0, f"stdout={said!r} stderr={grumbled!r}")
        self.assertIn("GATE IS GREEN", said)
        row = json.loads(gate.HISTORY.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(row["waited_seconds"], 71.5,
                         "the lock queued and the history did not say so")

    def test_a_broken_recorder_cannot_turn_a_green_gate_red(self):
        """The same failure from the other side: whatever the bookkeeping does,
        the verdict already printed is the verdict. The recorder itself is what
        breaks here - a lock whose `waited_seconds` explodes no longer reaches
        it, because reading the wait is now guarded at the source."""
        real = gate.remember

        def a_recorder_that_explodes(**_):
            raise RuntimeError("the history could not be written")

        gate.remember = a_recorder_that_explodes
        self.addCleanup(lambda: setattr(gate, "remember", real))

        code, said, grumbled = self._run_the_gate_over_one_test(None)
        self.assertEqual(code, 0)
        self.assertIn("GATE IS GREEN", said)
        self.assertIn("was not recorded", grumbled,
                      "it swallowed the failure without saying the row was lost")

    def test_a_lock_that_cannot_say_how_long_it_waited_still_records_the_run(self):
        """Losing the figure loses the figure, not the row."""

        class ALockThatExplodes:
            def waited_seconds(self):
                raise RuntimeError("the wait could not be read")

        code, said, _ = self._run_the_gate_over_one_test(ALockThatExplodes())
        self.assertEqual(code, 0)
        self.assertIn("GATE IS GREEN", said)
        row = json.loads(gate.HISTORY.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(row["waited_seconds"], 0.0)

    def test_the_wait_survives_the_process_that_did_not_do_the_waiting(self):
        """THE NUMBER THIS WHOLE CHANGE IS JUDGED BY WAS BLIND ON THE MAIN PATH.
        `push_if_green` holds the lock and passes `--no-lock` to the gate, so
        the process that queues and the process that records are different
        ones. Two runs queued 13.6 and 6.1 minutes behind the other lane and
        both went into the history as 0.0, while the parent's own stderr said
        how long it had waited. The parent hands the figure over instead."""
        import os

        was = os.environ.get("MLH_WAITED_SECONDS")
        self.addCleanup(lambda: os.environ.__setitem__("MLH_WAITED_SECONDS", was)
                        if was is not None else os.environ.pop("MLH_WAITED_SECONDS", None))

        os.environ["MLH_WAITED_SECONDS"] = "816.0"
        self.assertEqual(gate.the_wait_this_run_paid(None), 816.0)

        # A lock of our own outranks the environment: it did the waiting.
        class ALockThatWaited:
            def waited_seconds(self):
                return 12.0

        self.assertEqual(gate.the_wait_this_run_paid(ALockThatWaited()), 12.0)

        # And nonsense in the environment must not turn a green gate red.
        os.environ["MLH_WAITED_SECONDS"] = "not a number"
        self.assertEqual(gate.the_wait_this_run_paid(None), 0.0)

    def test_the_history_says_how_long_the_queue_was(self):
        """The success metric in words: queued runs, total minutes, median."""
        import io
        from contextlib import redirect_stdout

        gate.remember(ran=1, discovered=1, beside=0, waited=0.0)
        gate.remember(ran=1, discovered=1, beside=1, waited=816.0)
        gate.remember(ran=1, discovered=1, beside=1, waited=366.0)
        said = io.StringIO()
        with redirect_stdout(said):
            gate.the_history()
        text = said.getvalue()
        self.assertIn("runs that queued for the lock:            2 of 3", text)
        self.assertIn("19.7 minutes", text)  # 816 + 366 seconds


    def test_the_history_says_how_much_each_checkout_could_run(self):
        """THE SAME COMMIT SKIPPED 56 IN ONE CHECKOUT AND 0 IN THE OTHER, on
        the same machine, measured 2026-09-07. 55 of those need artefacts
        under `runs/`, which is gitignored and does not travel between
        checkouts. The tests are not hollow; the checkout is unfurnished, and
        neither fact is visible from `ran 4420 of 4420`.

        So the number is recorded per run and reported per tree. A suite that
        skips more is not a suite that passed more."""
        import io
        from contextlib import redirect_stdout

        real = gate.HISTORY
        rows = [
            {'at': 'x', 'ran': 4420, 'discovered': 4420, 'beside': 0,
             'skipped': 56, 'cwd': 'C:/trees/unfurnished'},
            {'at': 'x', 'ran': 4420, 'discovered': 4420, 'beside': 0,
             'skipped': 0, 'cwd': 'C:/trees/furnished'},
        ]
        gate.HISTORY.write_text(NEWLINE.join(json.dumps(r) for r in rows), encoding='utf-8')
        said = io.StringIO()
        with redirect_stdout(said):
            gate.the_history()
        text = said.getvalue()
        self.assertIn('unfurnished', text)
        self.assertIn('furnished', text)
        self.assertIn('56', text)
        self.assertIn('not a suite that passed more', text)
        self.assertEqual(gate.HISTORY, real)

    def test_a_run_records_how_many_it_skipped(self):
        gate.remember(ran=10, discovered=10, beside=0, skipped=7)
        row = json.loads(gate.HISTORY.read_text(encoding='utf-8').strip().splitlines()[-1])
        self.assertEqual(row['skipped'], 7)

    def test_rows_written_before_skips_were_recorded_are_not_counted_as_zero(self):
        """An absent field is "not recorded", never "skipped nothing" - the
        rule every other number in this file follows."""
        import io
        from contextlib import redirect_stdout

        gate.HISTORY.write_text(json.dumps(
            {'at': 'x', 'ran': 1, 'discovered': 1, 'beside': 0, 'cwd': 'C:/trees/old'}
        ), encoding='utf-8')
        said = io.StringIO()
        with redirect_stdout(said):
            gate.the_history()
        self.assertNotIn('old', said.getvalue())


class _APassingTest(unittest.TestCase):
    """A one-test suite for the two cases above. Not a check of anything."""

    def test_it_passes(self):
        self.assertTrue(True)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
