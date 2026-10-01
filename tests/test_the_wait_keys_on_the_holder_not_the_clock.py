"""A gate waits while the holder is alive, and not for a fixed number of seconds.

THE STANDING LAW is that a gate keys on the actor, never on the clock, and this
file's subject was the one place the lock still broke it. `acquire` took a
1,800-second deadline and gave up on it.

MEASURED AGAINST THAT CLOCK, 2026-09-05: two consecutive gates queued about 18
and about 19 minutes behind holders that ran about 28 and about 30 minutes.
Neither expired, so nothing failed - but the second holder took essentially the
whole timeout, and a third lane arriving behind it would have waited half an
hour and been told nothing at all. Thirty minutes spent to learn NOTHING is a
worse outcome than thirty-one spent to learn whether the tree is green, and the
clock was deciding that on a quantity unrelated to the question.

WHY IT WAS ONLY SAFE TO REMOVE THE CLOCK NOW. An unbounded wait on "is there a
process with that number" would wedge this machine the first time a pid was
recycled, which was measured happening in `ceede9d`: `_alive(8932)` said yes
and 8932 was `explorer.exe`. The lock records each process's creation instant,
so "the holder is alive" means that process rather than that number, and the
unbounded wait rests on a check that can actually tell.

NOTHING HERE WAITS ON A LIVE HOLDER WITHOUT RELEASING IT. A test that called
the unbounded path against a holder it never freed would hang the suite
forever, so the one test that exercises a real wait frees the lock from a
thread and asserts the wait ended because of that.
"""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "one_gate_wait", REPO / "scripts" / "one_gate_at_a_time.py"
)
gate = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(gate)


class TheWaitKeysOnTheHolderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        real = gate.LOCK
        gate.LOCK = Path(self.tmp.name) / "gate.lock"
        self.addCleanup(lambda: setattr(gate, "LOCK", real))

    def held_by(self, pid: int, born: str = "") -> None:
        gate.LOCK.write_text(
            json.dumps(
                {
                    "pid": pid,
                    "pid_born": born,
                    "cwd": "somewhere",
                    "command": "a suite",
                    "started": "2026-09-05 12:00:00",
                }
            ),
            encoding="utf-8",
        )

    def test_a_free_lock_is_taken_at_once_with_no_deadline(self):
        began = time.time()
        self.assertTrue(gate.acquire(None, "ours"))
        self.addCleanup(gate.release)
        self.assertLess(time.time() - began, 5)

    def test_a_dead_holder_does_not_need_a_clock_to_be_let_go_of(self):
        """The whole reason a deadline felt necessary. Without one, a holder
        that died without releasing must still be detected and taken - by its
        absence, not by waiting it out."""
        self.held_by(999_999)
        began = time.time()
        self.assertTrue(gate.acquire(None, "after the dead one"))
        self.addCleanup(gate.release)
        self.assertLess(
            time.time() - began, 10, "an unbounded wait sat on a lock whose holder is gone"
        )

    def test_a_recycled_holder_is_gone_even_though_the_number_is_alive(self):
        """The check the unbounded wait rests on. If this ever regresses, the
        wait above becomes forever."""
        self.held_by(os.getpid(), born="1")
        self.assertTrue(gate.acquire(None, "after the recycle"))
        gate.release()

    def test_the_wait_ends_when_the_holder_releases_and_not_before(self):
        """THE REAL WAIT, bounded by the thread that frees it rather than by a
        deadline inside the code under test."""
        self.assertTrue(gate.acquire(None, "the first suite"))
        freed_at = []

        def finish_after_a_moment():
            time.sleep(3)
            freed_at.append(time.time())
            gate.release()

        threading.Thread(target=finish_after_a_moment, daemon=True).start()
        began = time.time()
        self.assertTrue(gate.acquire(None, "the second suite"))
        self.addCleanup(gate.release)
        took = time.time() - began
        self.assertTrue(freed_at, "the holder never released, so nothing was measured")
        self.assertGreaterEqual(took, 2.5, "it did not wait for the holder at all")
        self.assertLess(took, 30, "it waited well past the holder going away")

    def test_a_caller_that_asks_for_a_limit_still_gets_one(self):
        """Removing the file's opinion about how long a suite takes is not the
        same as removing a caller's right to say how long IT will wait."""
        self.assertTrue(gate.acquire(1, "ours"))
        self.addCleanup(gate.release)
        began = time.time()
        self.assertFalse(gate.acquire(1, "a caller with a limit"))
        self.assertGreaterEqual(time.time() - began, 1)

    def test_a_long_wait_says_it_is_a_wait_and_not_a_hang(self):
        """An unbounded wait with no output is indistinguishable from a wedged
        process, which is the pair of look-alike states this whole file is
        about."""
        holder = {"pid": 4242, "cwd": "elsewhere", "command": "a suite", "started": "x"}
        long_ago = time.time() - 3600
        said = gate._still_waiting(holder, began=long_ago, last_said=long_ago)
        self.assertGreater(said, long_ago, "it stayed silent through an hour of waiting")
        # And it does not chatter every five seconds.
        again = gate._still_waiting(holder, began=long_ago, last_said=said)
        self.assertEqual(again, said)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
