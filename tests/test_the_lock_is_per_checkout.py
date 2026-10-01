"""The suite lock covers a checkout, not the machine, and why that is safe.

THE COLLISION IT WAS BUILT FOR WAS TWO SUITES IN ONE CHECKOUT - `docs/how-to-
verify.md` says so in those words. A machine-wide scope also serialised two
lanes working two different checkouts, and that cost was measured: **22 queued
gate runs over two days, 194 minutes, median 8.3, against a suite that takes
13.7 minutes and uses no GPU at all** - 39% of every gate spent waiting for a
lock over work that never touched the card.

WHAT LICENSES THE NARROWING IS A COUNT, NOT AN ARGUMENT. The gate's own history:
**26 of 64 recorded runs had at least one concurrent suite, and 0 of the 26 lost
a test.** And what is actually shared between two checkouts was measured rather
than assumed - the suite asks the OS for a port rather than taking 8078, the
portfile is bound to a per-test root, and the data root resolves to the
checkout. What stays machine-wide is this lock and an append-only history.

THE TRANSITION IS THE DANGEROUS PART, not the new scope. A lane still on the old
name writes the machine-wide lock and cannot see a per-checkout one, so an
upgraded lane waits for a live legacy holder and never writes that name itself -
writing it would re-impose the scope being removed.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "one_gate_per_checkout", REPO / "scripts" / "one_gate_at_a_time.py"
)
gate = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules[_spec.name] = gate
_spec.loader.exec_module(gate)


class TheLockIsPerCheckoutTest(unittest.TestCase):
    def test_the_lock_name_carries_the_checkout(self):
        self.assertRegex(gate.LOCK.name, r"^ml-harness-gate\.[0-9a-f]{8}\.lock$")

    def test_two_checkouts_do_not_share_a_lock(self):
        """THE WHOLE POINT. Two lanes in two trees stop queueing behind each
        other; two suites in ONE tree still cannot run at once.

        LOADED FROM A SECOND TREE, NOT MEASURED BY CHANGING DIRECTORY. The first
        version of this test chdir'd and asserted the key moved - which passed
        only because the key hashed the working directory, the very defect the
        designed collision run exposed. It was a test of the bug, and it went
        green every time. Now it copies the module into a second tree and asks
        that tree.
        """
        here = gate._this_checkout()
        with tempfile.TemporaryDirectory() as elsewhere:
            second = Path(elsewhere) / "another-checkout" / "scripts"
            second.mkdir(parents=True)
            source = REPO / "scripts" / "one_gate_at_a_time.py"
            (second / source.name).write_bytes(source.read_bytes())

            spec = importlib.util.spec_from_file_location(
                "one_gate_over_there", second / source.name)
            other = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = other
            spec.loader.exec_module(other)

            self.assertNotEqual(here, other._this_checkout(),
                                "two different trees hashed the same")
            self.assertNotEqual(gate.LOCK, other.LOCK,
                                "two trees computed the same lock file")
        self.assertEqual(here, gate._this_checkout(), "this tree hashed differently twice")

    def test_the_legacy_name_is_known_and_never_written(self):
        """Writing it would put the machine-wide scope back on every lane."""
        self.assertEqual(gate.LEGACY_LOCK.name, "ml-harness-gate.lock")
        source = (REPO / "scripts" / "one_gate_at_a_time.py").read_text(encoding="utf-8")
        self.assertNotIn("LEGACY_LOCK.write_text", source)
        self.assertNotIn("os.open(str(LEGACY_LOCK)", source)

    def test_a_dead_legacy_holder_does_not_block(self):
        """An un-upgraded lane that died must not wedge every upgraded one."""
        with tempfile.TemporaryDirectory() as tmp:
            legacy, real = gate.LEGACY_LOCK, gate.LOCK
            gate.LEGACY_LOCK = Path(tmp) / "ml-harness-gate.lock"
            gate.LOCK = Path(tmp) / "mine.lock"
            try:
                gate.LEGACY_LOCK.write_text(
                    json.dumps({"pid": 999_999, "pid_born": "", "cwd": "gone",
                                "command": "a lane that died", "started": "x"}),
                    encoding="utf-8",
                )
                self.assertTrue(gate.acquire(timeout=5, command="ours"))
                gate.release()
            finally:
                gate.LEGACY_LOCK, gate.LOCK = legacy, real

    def test_a_checkout_lock_still_excludes_a_second_suite_in_that_checkout(self):
        """The failure this file exists for is unchanged."""
        with tempfile.TemporaryDirectory() as tmp:
            legacy, real = gate.LEGACY_LOCK, gate.LOCK
            gate.LEGACY_LOCK = Path(tmp) / "absent.lock"
            gate.LOCK = Path(tmp) / "mine.lock"
            try:
                self.assertTrue(gate.acquire(timeout=1, command="first"))
                self.assertFalse(gate.acquire(timeout=1, command="second"))
                gate.release()
            finally:
                gate.LEGACY_LOCK, gate.LOCK = legacy, real


    def test_the_lock_totals_the_wait_it_used_to_only_announce(self):
        """194 minutes had to be reconstructed by hand from scattered stderr
        lines, because the wait was announced while it happened and never
        totalled when it ended. Now it is a number a caller can record."""
        import time

        with tempfile.TemporaryDirectory() as tmp:
            legacy, real = gate.LEGACY_LOCK, gate.LOCK
            gate.LEGACY_LOCK = Path(tmp) / "absent.lock"
            gate.LOCK = Path(tmp) / "mine.lock"
            try:
                before = time.time()
                self.assertTrue(gate.acquire(timeout=5, command="ours"))
                self.assertGreaterEqual(gate.waited_seconds(), 0.0)
                self.assertLessEqual(gate.waited_seconds(), time.time() - before + 1)
                gate.release()
            finally:
                gate.LEGACY_LOCK, gate.LOCK = legacy, real


    def test_a_bounded_caller_stays_bounded_while_a_legacy_lane_runs(self):
        """THE DEFECT THIS CHANGE SHIPPED AND THEN CAUGHT. The legacy wait sat
        BEFORE the timeout loop, so a caller asking for one second waited as
        long as the other checkout's gate took - unbounded, from a bounded
        call. It was found by this file's own suite hanging eight minutes while
        the other lane ran, with a live machine-wide lock in the temp
        directory. A caller that names a limit must get an answer inside it,
        and 'I could not get in' is an answer."""
        import time

        with tempfile.TemporaryDirectory() as tmp:
            legacy, real = gate.LEGACY_LOCK, gate.LOCK
            gate.LEGACY_LOCK = Path(tmp) / "ml-harness-gate.lock"
            gate.LOCK = Path(tmp) / "mine.lock"
            try:
                gate.LEGACY_LOCK.write_text(
                    json.dumps({"pid": os.getpid(), "pid_born": gate.born_when(os.getpid()),
                                "cwd": "another checkout", "command": "an un-upgraded lane",
                                "started": "now"}),
                    encoding="utf-8",
                )
                began = time.time()
                got = gate.acquire(timeout=2, command="a bounded caller")
                took = time.time() - began
                self.assertFalse(got, "it took the lock while a live legacy lane held one")
                self.assertLess(took, 6, f"a 2s call waited {took:.1f}s")
                self.assertFalse(gate.LOCK.exists(), "it left a lock behind after failing")
                self.assertFalse(
                    (Path(tmp) / "ml-harness-gate.lock").read_text(encoding="utf-8").count("bounded"),
                    "it wrote the legacy lock, re-imposing the scope being removed",
                )
            finally:
                gate.LEGACY_LOCK, gate.LOCK = legacy, real


    def test_a_test_that_redirects_the_lock_cannot_see_the_real_one(self):
        """THE HARNESS MUST NOT REACH OUTSIDE ITSELF. Every lock test here
        points LOCK at a temp file; none of them pointed LEGACY_LOCK anywhere,
        so once the legacy wait existed they all queued on whatever the OTHER
        checkout was doing. Nine failed at once the first time the neighbouring
        lane ran a gate, and the failure was the harness, not the code.

        The rule: waiting out a legacy holder is this caller's business only in
        production, or in a test that redirected the legacy lock too and is
        therefore asking about the transition on purpose."""
        real_lock, real_legacy = gate.LOCK, gate.LEGACY_LOCK
        try:
            # Production.
            gate.LOCK, gate.LEGACY_LOCK = gate.THE_REAL_LOCK, gate.THE_REAL_LEGACY_LOCK
            self.assertTrue(gate._the_legacy_wait_is_ours_to_make())

            # A test about locking, which redirected only LOCK.
            gate.LOCK = Path("somewhere-else.lock")
            self.assertFalse(gate._the_legacy_wait_is_ours_to_make(),
                             "a redirected test can still see the machine's real lock")

            # A test about the transition, which redirected both.
            gate.LEGACY_LOCK = Path("its-own-legacy.lock")
            self.assertTrue(gate._the_legacy_wait_is_ours_to_make(),
                            "a transition test cannot exercise its own fixture")
        finally:
            gate.LOCK, gate.LEGACY_LOCK = real_lock, real_legacy


    def test_the_key_is_the_tree_not_the_working_directory(self):
        """FOUND BY THE DESIGNED COLLISION RUN, as an instrument artefact and a
        real defect wearing the same face. Both arms reported checkout key
        549c5cae because the key hashed `Path.cwd()` and the second arm was
        launched from the first arm's working directory.

        Keyed on the working directory the lock names wherever the caller was
        standing: two lanes in two trees that both run the gate from a common
        directory get the SAME lock and serialise for nothing, and one lane
        running it from a subdirectory of its own tree gets a DIFFERENT lock
        than from the root - losing mutual exclusion inside its own checkout,
        which is the one collision this file exists to prevent."""
        here = gate._this_checkout()
        was = Path.cwd()
        for elsewhere in (Path(tempfile.gettempdir()), REPO / "tests", REPO / "scripts"):
            if not elsewhere.is_dir():
                continue
            try:
                os.chdir(elsewhere)
                self.assertEqual(
                    gate._this_checkout(), here,
                    f"the key moved when the caller stood in {elsewhere}",
                )
            finally:
                os.chdir(was)

    def test_the_key_did_not_move_when_it_was_corrected(self):
        """The fix must not rename a live lock. Both lanes are mid-transition,
        and a key that changed would leave an upgraded lane holding a name no
        other upgraded lane looks at - the machine-wide problem again, with
        extra steps. The gate is normally run from the repository root, so the
        corrected key is the same value the cwd version produced there."""
        import hashlib

        from_the_root = hashlib.sha256(str(REPO).lower().encode()).hexdigest()[:8]
        self.assertEqual(gate._this_checkout(), from_the_root)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
