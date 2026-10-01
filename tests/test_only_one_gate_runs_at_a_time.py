"""Two full-suite gates cannot run on this machine at once.

WHY THIS EXISTS. Two lanes work this repository from two worktrees on one
machine. The agreed rule was "before a gate, check for another test process and
wait if one is running", and that is a check-then-act race: both lanes look,
both see a clear machine, both start. It failed twice in twenty minutes on
2026-09-04, the second time within minutes of being agreed.

The collision does not present as a crash, which is what makes it dangerous.
One gate discovered 3,822 tests, ran 3,315, and reported OK - a gate that
cannot fail, which is the first law in `docs/how-to-verify.md`.

These hold the two properties that make the lock worth having, and the second
one is the property that makes it safe to adopt: a lock that could wedge every
future gate on this machine would be a worse defect than the collision it
prevents.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "one_gate_at_a_time", REPO / "scripts" / "one_gate_at_a_time.py"
)
gate = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(gate)


class TheGateLockTest(unittest.TestCase):
    def setUp(self):
        # Never touch the real machine-wide lock from a test - a suite that
        # stole it would cause exactly the collision this prevents.
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._real = gate.LOCK
        gate.LOCK = Path(self.tmp.name) / "gate.lock"
        self.addCleanup(lambda: setattr(gate, "LOCK", self._real))

    def test_the_second_caller_cannot_take_a_held_lock(self):
        self.assertTrue(gate.acquire(timeout=1, command="first"))
        self.addCleanup(gate.release)
        started = time.time()
        self.assertFalse(
            gate.acquire(timeout=1, command="second"),
            "two gates took the lock at once, which is the collision itself",
        )
        # It waited rather than failing instantly, so a real gate queues.
        self.assertGreaterEqual(time.time() - started, 1)

    def test_a_lock_whose_wrapper_died_but_whose_run_lives_is_not_stale(self):
        """FOUND BY KILLING THE WRAPPER, 2026-09-05. `Stop-Process -Force` on the
        wrapper does not touch the suite it started. The wrapper died, the run
        kept going, and the lock said STALE because it knew only the wrapper's
        pid - so the next lane would have taken it and started a second suite
        beside a live one, which is the collision this file exists to prevent,
        arriving through the file itself.

        A holder is gone only when BOTH are gone.
        """
        gate.LOCK.write_text(
            json.dumps(
                {
                    "pid": 999_999,          # the wrapper, gone
                    "child": os.getpid(),    # its run, still here
                    "cwd": "somewhere",
                    "command": "a suite that is still going",
                    "started": "2026-09-05 10:36:11",
                }
            ),
            encoding="utf-8",
        )
        self.assertFalse(gate._alive(999_999))
        self.assertTrue(gate._alive(os.getpid()))
        self.assertFalse(
            gate.acquire(timeout=1, command="a second suite"),
            "took a lock whose run is still going",
        )
        gate.LOCK.unlink()

    def test_the_child_is_recorded_on_the_lock_so_that_can_be_known(self):
        self.assertTrue(gate.acquire(timeout=1, command="ours"))
        self.addCleanup(gate.release)
        gate.note_the_child(4242)
        self.assertEqual(json.loads(gate.LOCK.read_text(encoding="utf-8"))["child"], 4242)

    def test_a_lock_left_by_a_dead_process_is_taken_rather_than_obeyed(self):
        """A gate wedged forever would be worse than the collision."""
        gate.LOCK.write_text(
            json.dumps(
                {
                    "pid": 999_999,
                    "cwd": "nowhere",
                    "command": "a run that died",
                    "started": "2026-09-04 20:00:00",
                }
            ),
            encoding="utf-8",
        )
        self.assertFalse(gate._alive(999_999))
        self.assertTrue(
            gate.acquire(timeout=5, command="after the dead one"),
            "a stale lock blocked a gate, which would wedge this machine",
        )
        gate.release()

    def test_releasing_does_not_take_a_lock_somebody_else_now_holds(self):
        """If we were declared dead and the lock was stolen, our own release
        must not remove the new holder's lock."""
        self.assertTrue(gate.acquire(timeout=1, command="ours"))
        stolen = json.loads(gate.LOCK.read_text(encoding="utf-8"))
        stolen["pid"] = os.getpid() + 1
        gate.LOCK.write_text(json.dumps(stolen), encoding="utf-8")
        gate.release()
        self.assertTrue(gate.LOCK.exists(), "release removed another process's lock")
        gate.LOCK.unlink()

    def test_this_process_is_reported_alive(self):
        """The liveness check decides whether a lock is stale, so a wrong
        answer here either wedges the machine or lets the collision through."""
        self.assertTrue(gate._alive(os.getpid()))
        self.assertFalse(gate._alive(0))
        self.assertFalse(gate._alive(-1))

    def test_the_wait_message_names_who_it_is_waiting_for(self):
        """"Waiting" with no subject is why the first collision went unnoticed
        for as long as it did."""
        gate.acquire(timeout=1, command="python -m unittest discover -s tests")
        self.addCleanup(gate.release)
        described = gate._describe(gate._holder())
        self.assertIn(str(os.getpid()), described)
        self.assertIn("unittest", described)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
