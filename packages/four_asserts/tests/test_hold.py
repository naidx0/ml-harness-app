"""The hold: a named holder, checked, and a wait that keys on it."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

from four_asserts import Hold, started_at, still_running


class HoldTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "resource.hold"

    def a_hold(self, holder="lane-a", purpose="a suite") -> Hold:
        return Hold(self.path, holder=holder, purpose=purpose)

    def held_by(self, pid: int, born: str = "") -> None:
        self.path.write_text(
            json.dumps(
                {
                    "holder": "somebody",
                    "purpose": "a run",
                    "pid": pid,
                    "pid_started_at": born,
                    "since": "2026-01-01T00:00:00",
                }
            ),
            encoding="utf-8",
        )

    def test_a_free_resource_is_taken_at_once(self):
        held = self.a_hold()
        began = time.time()
        self.assertTrue(held.take())
        self.addCleanup(held.let_go)
        self.assertLess(time.time() - began, 5)
        self.assertEqual(held.whose()["holder"], "lane-a")
        self.assertEqual(held.whose()["purpose"], "a suite")

    def test_a_second_caller_cannot_take_a_live_hold(self):
        first = self.a_hold("lane-a")
        self.assertTrue(first.take())
        self.addCleanup(first.let_go)
        second = self.a_hold("lane-b")
        began = time.time()
        self.assertFalse(second.take(timeout=1))
        self.assertGreaterEqual(time.time() - began, 1)

    def test_a_dead_holder_does_not_need_a_clock_to_be_let_go_of(self):
        """The whole reason a deadline felt necessary. Without one, a holder
        that died without releasing must be detected by its ABSENCE."""
        self.held_by(999_999)
        began = time.time()
        self.assertTrue(self.a_hold().take())
        self.addCleanup(self.a_hold().let_go)
        self.assertLess(time.time() - began, 10)

    def test_a_recycled_pid_is_not_the_holder(self):
        """A pid is not an identity. The number is alive; the process behind it
        is not the one that took the hold."""
        self.held_by(os.getpid(), born="1")
        self.assertTrue(self.a_hold().take())
        self.a_hold().let_go()

    def test_a_missing_start_time_is_no_evidence_rather_than_a_mismatch(self):
        """Treating 'cannot tell' as 'gone' would start a second run beside a
        live one, which is the collision being prevented."""
        self.assertTrue(still_running(os.getpid(), born=""))
        self.held_by(os.getpid(), born="")
        self.assertFalse(self.a_hold().take(timeout=1))

    def test_the_wait_ends_when_the_holder_lets_go_and_not_before(self):
        first = self.a_hold("lane-a")
        self.assertTrue(first.take())
        freed = []

        def finish_soon():
            time.sleep(3)
            freed.append(time.time())
            first.let_go()

        threading.Thread(target=finish_soon, daemon=True).start()
        second = self.a_hold("lane-b")
        began = time.time()
        self.assertTrue(second.take())
        self.addCleanup(second.let_go)
        took = time.time() - began
        self.assertTrue(freed, "the holder never let go, so nothing was measured")
        self.assertGreaterEqual(took, 2.5)
        self.assertLess(took, 30)

    def test_the_wait_is_totalled_rather_than_estimated(self):
        held = self.a_hold()
        self.assertTrue(held.take())
        self.addCleanup(held.let_go)
        self.assertGreaterEqual(held.waited_seconds(), 0)

    def test_letting_go_does_not_remove_somebody_elses_hold(self):
        held = self.a_hold()
        self.assertTrue(held.take())
        stolen = held.whose()
        stolen["pid"] = os.getpid() + 1
        self.path.write_text(json.dumps(stolen), encoding="utf-8")
        held.let_go()
        self.assertTrue(self.path.exists(), "it removed another process's hold")
        self.path.unlink()

    def test_the_wait_says_who_it_is_waiting_for(self):
        """'Waiting' with no subject is why the first collision went unnoticed
        for as long as it did."""
        first = self.a_hold("lane-a", "a full suite")
        self.assertTrue(first.take())
        self.addCleanup(first.let_go)
        said = []
        self.a_hold("lane-b").take(timeout=1, say=said.append)
        self.assertTrue(any("lane-a" in line for line in said))
        self.assertTrue(any("a full suite" in line for line in said))

    def test_this_process_has_a_start_time_and_a_dead_one_does_not(self):
        self.assertTrue(started_at(os.getpid()))
        self.assertEqual(started_at(999_999), "")
        self.assertEqual(started_at(0), "")

    def test_it_works_as_a_context_manager(self):
        with self.a_hold() as held:
            self.assertTrue(self.path.exists())
            self.assertEqual(held.whose()["holder"], "lane-a")
        self.assertFalse(self.path.exists())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
