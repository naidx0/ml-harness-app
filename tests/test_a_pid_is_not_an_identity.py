"""A lock is held by a process, not by a number.

MEASURED 2026-09-05. `one_gate_at_a_time._alive(8932)` returned True, and pid
8932 was `explorer.exe`. Every operating system reuses process ids. So a lock
left behind by a gate whose number was later handed to some long-lived
program - a desktop shell, a service - read as HELD, and would have gone on
reading as HELD for as long as that program ran: every gate on this machine
waiting out the full 1800-second timeout for a holder that never took the lock.

That is the failure this file's own docstring calls worse than the collision it
prevents, reached by the mechanism that prevents it.

WHAT SEPARATES THEM. Two processes can share a number over a machine's life,
but not a number AND a creation instant. The lock records when each process
started, and a recorded start time that disagrees with the live one means the
holder is gone however alive the number looks.

THE DIRECTION OF THE DOUBT MATTERS. A missing or unreadable start time is not a
mismatch: it is no evidence, and falls back to the pid alone. Treating "cannot
tell" as "gone" would start a second suite beside a live one, which is the
collision itself.
"""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "one_gate_pid_identity", REPO / "scripts" / "one_gate_at_a_time.py"
)
gate = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(gate)


class APidIsNotAnIdentityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        real = gate.LOCK
        gate.LOCK = Path(self.tmp.name) / "gate.lock"
        self.addCleanup(lambda: setattr(gate, "LOCK", real))

    def test_a_live_process_has_a_start_time(self):
        self.assertTrue(gate.born_when(os.getpid()))

    def test_a_dead_pid_has_no_start_time_rather_than_a_wrong_one(self):
        self.assertEqual(gate.born_when(999_999), "")
        self.assertEqual(gate.born_when(0), "")

    def test_the_same_process_is_still_itself(self):
        me = os.getpid()
        self.assertTrue(gate._alive(me, gate.born_when(me)))

    def test_a_recycled_pid_is_not_the_holder(self):
        """THE PLANTED CASE. The number is alive; the process behind it is not
        the one that took the lock."""
        self.assertFalse(gate._alive(os.getpid(), born="1"))

    def test_a_lock_with_no_start_time_still_works(self):
        """Locks written before this change, and machines whose process times
        cannot be read, must not become unreadable."""
        self.assertTrue(gate._alive(os.getpid(), born=""))

    def test_a_gate_arriving_after_a_recycle_is_not_wedged(self):
        """THE WHOLE POINT: 1800 seconds of waiting, or a run."""
        self.assertTrue(gate.acquire(timeout=1, command="ours"))
        held = json.loads(gate.LOCK.read_text(encoding="utf-8"))
        held["pid_born"] = "1"  # our number, somebody else's process
        gate.LOCK.write_text(json.dumps(held), encoding="utf-8")
        self.assertTrue(
            gate.acquire(timeout=3, command="after the recycle"),
            "a recycled pid wedged the gate for the full timeout",
        )
        gate.release()

    def test_the_lock_records_the_start_time_it_will_be_checked_against(self):
        self.assertTrue(gate.acquire(timeout=1, command="ours"))
        self.addCleanup(gate.release)
        held = json.loads(gate.LOCK.read_text(encoding="utf-8"))
        self.assertEqual(held["pid_born"], gate.born_when(os.getpid()))

    def test_the_child_start_time_is_recorded_too(self):
        """The orphan check reads the child, so the child needs the same
        identity the wrapper has."""
        self.assertTrue(gate.acquire(timeout=1, command="ours"))
        self.addCleanup(gate.release)
        gate.note_the_child(os.getpid())
        held = json.loads(gate.LOCK.read_text(encoding="utf-8"))
        self.assertEqual(held["child_born"], gate.born_when(os.getpid()))

    def test_an_orphan_check_is_not_fooled_by_a_recycled_child(self):
        """A recycled CHILD is the dangerous direction: it makes a finished run
        look like it is still going, and every later gate waits for it."""
        gate.LOCK.write_text(
            json.dumps(
                {
                    "pid": 999_999,
                    "pid_born": "",
                    "child": os.getpid(),
                    "child_born": "1",
                    "cwd": "somewhere",
                    "command": "a run that finished long ago",
                    "started": "2026-09-05 04:00:00",
                }
            ),
            encoding="utf-8",
        )
        self.assertTrue(
            gate.acquire(timeout=3, command="after the child was recycled"),
            "a recycled child pid held the lock against a finished run",
        )
        gate.release()


class TheStartTimeIsAStringAndComparedAsOneTest(unittest.TestCase):
    """MEASURED 2026-09-05, on myself, against the live sentinel-N lane.

    I checked whether the lock's holder was still the process that took it with

        born_when(4264) == 134331322491779160

    and got False on a lane that was alive, correct, and mid-run. The lock file
    says `born=134331322491779160`; `born_when` hands back that same value AS A
    STRING, and a string never equals an int in Python however identical they
    read. One `==` against an unquoted literal and a live holder reads as a
    stranger.

    Nothing in the suite pinned the type, so the same slip is available to the
    next caller - and its consequence is the one this file exists to prevent,
    reached from the other side: not a dead lock read as held, but a LIVE lock
    read as recycled, which clears it and starts a second run beside the first.
    """

    def test_born_when_hands_back_a_string(self):
        said = gate.born_when(os.getpid())
        self.assertIsInstance(
            said,
            str,
            "born_when returned a non-string; every caller compares it against "
            "a field parsed out of the lock file, which is always a string",
        )

    def test_the_digits_from_the_lock_file_match_what_born_when_says(self):
        """The round trip a caller actually makes: write it, read it back as
        text, compare. This is the comparison that must hold."""
        mine = os.getpid()
        written = f"born={gate.born_when(mine)}"
        read_back = written.split("=", 1)[1]
        self.assertTrue(gate._alive(mine, read_back), "a live process read as gone")

    def test_a_start_time_handed_over_as_a_number_is_not_treated_as_a_mismatch(self):
        """THE SLIP ITSELF. A caller that int()s the field - or writes the
        literal without quotes - must not thereby clear a live lock.

        `_alive` may answer True (it normalised) or fall back to the pid alone;
        what it must never do is answer False, because False here means "the
        holder is gone, take the card"."""
        mine = os.getpid()
        digits = gate.born_when(mine)
        if not digits.isdigit():  # a platform that reports ISO, not FILETIME
            self.skipTest(f"born_when is not numeric here: {digits!r}")
        self.assertTrue(
            gate._alive(mine, int(digits)),
            "a live holder whose start time arrived as an int read as recycled; "
            "that clears the lock and starts a second run beside a live one",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
