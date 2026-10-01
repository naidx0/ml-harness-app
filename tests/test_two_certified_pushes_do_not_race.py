"""Two gates that target one remote ref never run at the same time.

## Six races in eight hours, all the same shape

2026-09-10. Two lanes gate siblings of one commit in two checkouts; both go
green; the second to reach the push is refused as a non-fast-forward, having
spent a full suite - about sixteen minutes - certifying a tree that no longer
describes `main`. Then it rebases and spends another.

`one_gate_at_a_time` cannot prevent this and is not wrong to. It is keyed by
CHECKOUT, and two lanes in two worktrees are correctly not contending for one
tree. What they contend for is `refs/heads/main` on the remote, and no
per-checkout lock can name that.

## Why the lock is taken before the gate rather than before the push

A lock taken after a green gate would serialise the pushes and nothing else -
the loser has already spent the suite. Taken first, the second lane WAITS, and
when it starts its tree already contains the winner's object. One wait replaces
one wasted suite plus one rebase.

## And why it is taken after the machine lock

`test_the_machine_lock_is_taken_first_so_one_checkout_cannot_deadlock` is the
case for the order. Two invocations in ONE checkout, taking them the other way
round, deadlock: each holds one and waits for the other.

## What this does not claim

It serialises the lanes that take it. A push from a clone nobody here knows
about still moves the ref, and `push_if_green` still checks the fast-forward
and still rebases on a rejected ref. This removes the common case, not the
possibility - and the refusal says so rather than implying it owns the ref.
"""

from __future__ import annotations

import io
import json
import os
import os
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path

import support

push_lock = support.import_file(
    "one_push_at_a_time", support.REPO_ROOT / "scripts" / "one_push_at_a_time.py"
)
pusher = support.import_file(
    "push_if_green", support.REPO_ROOT / "scripts" / "push_if_green.py"
)

MAIN = "refs/heads/main"


class OneRefOneHolderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(support.sandbox(self))
        self._real = push_lock.tempfile.gettempdir
        push_lock.tempfile.gettempdir = lambda: str(self.tmp)
        self.addCleanup(setattr, push_lock.tempfile, "gettempdir", self._real)
        self.addCleanup(push_lock.release)

    def test_two_gates_targeting_one_ref_do_not_both_hold_it(self):
        """THE CASE, and `timeout=0` asserts the DECISION rather than spending
        a wait to prove it."""
        with redirect_stderr(io.StringIO()):
            self.assertTrue(push_lock.acquire("origin", MAIN, 5, "first"))
        #: A SECOND HOLDER HAS TO BE A LIVE FOREIGN PROCESS, and the first
        #: version of this used `os.getpid() + 100000` - a number nobody had
        #: checked was running. `_alive` said no, the lock read as stale, and
        #: it was correctly reclaimed: the case passed for the wrong reason
        #: right up until it did not.
        path = push_lock.lock_path("origin", MAIN)
        said = json.loads(path.read_text(encoding="utf-8"))
        said["pid"] = self.a_live_stranger()
        said["pid_born"] = push_lock._gate.born_when(said["pid"])
        path.write_text(json.dumps(said), encoding="utf-8")
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertFalse(push_lock.acquire("origin", MAIN, 0, "second"))

    def test_a_different_ref_is_not_blocked(self):
        """THE CONTROL, and it is what stops this being a machine-wide push
        freeze. A lane pushing `refs/heads/experiment` has no reason to wait
        for one pushing `main`."""
        with redirect_stderr(io.StringIO()):
            self.assertTrue(push_lock.acquire("origin", MAIN, 5, "first"))
            self.assertTrue(
                push_lock.acquire("origin", "refs/heads/experiment", 0, "other")
            )

    def test_a_different_remote_is_not_blocked(self):
        """Two remotes with a branch of the same name are two different refs."""
        self.assertNotEqual(
            push_lock.lock_path("origin", MAIN),
            push_lock.lock_path("upstream", MAIN),
        )

    def test_a_stale_holder_is_reclaimed_and_says_so(self):
        """WIRED FROM THE START rather than after somebody waits out a timeout
        behind a corpse. This lock is held across a whole gate, which is
        exactly where a crash leaves one."""
        path = push_lock.lock_path("origin", MAIN)
        path.write_text(
            json.dumps({"pid": self._a_dead_pid(), "pid_born": "", "ref": MAIN}),
            encoding="utf-8",
        )
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertTrue(push_lock.acquire("origin", MAIN, 0, "after a crash"))
        self.assertIn("stale", err.getvalue().lower())

    def test_an_unreadable_lock_is_treated_as_held(self):
        """The rule `one_gate_at_a_time` took on the same day: a read that
        failed is not evidence that nobody is here."""
        path = push_lock.lock_path("origin", MAIN)
        path.write_text("{partially writ", encoding="utf-8")
        with redirect_stderr(io.StringIO()):
            self.assertFalse(push_lock.acquire("origin", MAIN, 0, "cautious"))
        self.assertEqual("{partially writ", path.read_text(encoding="utf-8"))

    def test_release_leaves_a_lock_that_is_not_ours(self):
        with redirect_stderr(io.StringIO()):
            push_lock.acquire("origin", MAIN, 5, "first")
        path = push_lock.lock_path("origin", MAIN)
        said = json.loads(path.read_text(encoding="utf-8"))
        said["pid"] = os.getpid() + 100000
        path.write_text(json.dumps(said), encoding="utf-8")
        with redirect_stderr(io.StringIO()):
            push_lock.release()
        #: release compares the PID and does not need the holder to be alive -
        #: a dead stranger's lock is still not ours to delete.
        self.assertTrue(path.is_file())

    def test_the_refusal_admits_what_it_does_not_cover(self):
        """A lock that implied it owned the ref would invite somebody to skip
        the fast-forward check that still has to be there."""
        said = pusher.why_the_push_lock_refused("origin", MAIN)
        self.assertIn("another lane", said)
        self.assertIn("Nothing was gated", said)

    def a_live_stranger(self) -> int:
        """A process that is running and is not us, cleaned up after."""
        import subprocess

        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(120)"]
        )
        self.addCleanup(process.wait)
        self.addCleanup(process.terminate)
        return process.pid

    def _a_dead_pid(self) -> int:
        """A pid whose process is gone AND whose handle nobody holds.

        THE SECOND HALF IS NOT PEDANTRY, IT IS WHY THIS WENT RED. On Windows
        `OpenProcess` succeeds for a process that has EXITED as long as any
        handle to it remains open - the kernel object outlives the process -
        and `subprocess.Popen` holds exactly such a handle until the object is
        released. So the old version, which returned `process.pid` with the
        `Popen` still referenced, handed back a pid that `_alive` reported as
        LIVING, the lock read as held, `acquire` refused, and this test failed
        for a reason with nothing to do with staleness.

        MEASURED 2026-09-11, six trials each way: handle held, `_alive` True
        6 of 6; handle released, 0 of 6. It reached the gate as one failure in
        six isolated runs on an unchanged tree - a flake, which is worse than
        a break, because a gate that goes red on unrelated commits is one
        people learn to re-run until it is green.

        AND THE NUMBER CAN BE TAKEN AGAIN. Windows hands a freed pid to the
        next process that asks, and inside a 5,000-test suite that spawns as
        it goes the next process asks within milliseconds. MEASURED 2026-09-11,
        push30: handle released, `_alive` still True - the second time this
        helper reddened a gate on a commit that touched nothing near it. A
        pid that is dead now is not a property one spawn can guarantee, so
        this tries a fresh spawn while the number reads alive, a bounded
        number of times, and asserts only after that. The assertion stays,
        because the case under test is "a holder that is gone" and a live
        number would test something else.
        """
        import subprocess

        pid = 0
        for _ in range(5):
            process = subprocess.Popen([sys.executable, "-c", "pass"])
            process.wait()
            pid = process.pid
            # Close the handle, then drop the last reference to it.
            process.__exit__(None, None, None)
            del process
            if not push_lock._gate._alive(pid, ""):
                break
        # ASSERTED, NOT ASSUMED. If this ever fails the test says so here,
        # where the reason is one line away, rather than three assertions
        # later as "stale holder was not reclaimed".
        self.assertFalse(
            push_lock._gate._alive(pid, ""),
            "the helper handed back a pid that still reads as alive after five "
            "spawns, so the case under test was never set up",
        )
        return pid


class NoTestReachesForTheRealLocksTest(unittest.TestCase):
    """A suite that takes the locks its own runner holds waits for itself.

    MEASURED 2026-09-10 and it cost two races. `one_push_at_a_time` arrived
    taken BEFORE the gate and keyed on the remote ref; the existing push tests
    passed a fake MACHINE lock and said nothing about the new one, so they
    reached for the real push lock from inside a suite whose runner was holding
    it. The gate did not fail - it WAITED, printing "still waiting for pid
    21908", which was its own parent, until it was killed an hour later.

    `test_a_push_reads_the_gates_exit_code`'s own docstring had already written
    the warning, about the other lock. Adding a second one without extending it
    is how a documented hazard gets committed twice, so this asserts the shape
    rather than trusting the next person to remember.
    """

    def test_every_push_if_green_call_in_the_suite_names_both_locks(self):
        import re

        for name in (
            "test_a_push_reads_the_gates_exit_code.py",
            "test_two_certified_pushes_do_not_race.py",
        ):
            text = (support.REPO_ROOT / "tests" / name).read_text(encoding="utf-8")
            for call in re.findall(r"push_if_green\((?:[^()]|\([^()]*\))*\)", text):
                if "run=" not in call:
                    continue  # a reference to the name, not a call with a runner
                with self.subTest(where=name, call=call[:60]):
                    self.assertIn("push_lock=", call,
                                  "this call would take the REAL push lock")
                    self.assertIn("lock=", call,
                                  "this call would take the REAL machine lock")


class ItIsTakenBeforeTheGateTest(unittest.TestCase):
    """The order is the whole value of the thing."""

    class ARecordingLock:
        DEFAULT_TIMEOUT_SECONDS = 1

        def __init__(self, log, name, grant=True):
            self.log, self.name, self.grant = log, name, grant
            self.released = 0

        def acquire(self, *args, **kwargs):
            self.log.append(f"take {self.name}")
            return self.grant

        def release(self):
            self.released += 1
            self.log.append(f"drop {self.name}")

    class ARecordingRun:
        def __init__(self, log, *codes):
            self.log, self.codes = log, list(codes)

        def __call__(self, command, *args, **kwargs):
            head = list(command[:2])
            if command[0] == "git" and "status" in command:
                #: A CLEAN TREE. `push_if_green` asks before it spends a suite,
                #: because the gate reads the working tree and the push
                #: publishes HEAD - and these cases are all about what happens
                #: after that check passes.
                class Clean:
                    returncode = 0
                    stdout = ""

                return Clean()
            if head == ["git", "rev-parse"]:
                class Resolved:
                    returncode = 0
                    stdout = "d5326599ee8662465acfce4cb4c51a0d323d8b0a\n"
                return Resolved()
            self.log.append("gate" if "gate.py" in " ".join(command) else " ".join(head))

            class Done:
                returncode = self.codes.pop(0) if self.codes else 0
            return Done()

    def test_the_ref_lock_is_taken_before_the_suite_runs(self):
        log = []
        machine = self.ARecordingLock(log, "machine")
        ref = self.ARecordingLock(log, "ref")
        run = self.ARecordingRun(log, 0, 0)
        with redirect_stderr(io.StringIO()):
            pusher.push_if_green(
                ["origin", "main"], run=run, lock=machine, push_lock=ref
            )
        self.assertLess(
            log.index("take ref"), log.index("gate"),
            "the lock was taken after the suite, which serialises the pushes "
            "and lets the loser spend a gate anyway:\n" + repr(log),
        )

    def test_the_machine_lock_is_taken_first_so_one_checkout_cannot_deadlock(self):
        """TWO INVOCATIONS IN ONE CHECKOUT, THE OTHER WAY ROUND, DEADLOCK: one
        holds the push lock and waits for the machine lock, the other the
        reverse. Machine first makes the cycle impossible - a lane only waits
        for the ref lock while holding a lock nobody outside its checkout
        wants."""
        log = []
        with redirect_stderr(io.StringIO()):
            pusher.push_if_green(
                ["origin", "main"],
                run=self.ARecordingRun(log, 0, 0),
                lock=self.ARecordingLock(log, "machine"),
                push_lock=self.ARecordingLock(log, "ref"),
            )
        self.assertLess(log.index("take machine"), log.index("take ref"), repr(log))

    def test_a_refused_ref_lock_does_not_gate_at_all(self):
        """The point of taking it first: a lane that cannot push must not spend
        a suite finding that out."""
        log = []
        with redirect_stderr(io.StringIO()):
            code = pusher.push_if_green(
                ["origin", "main"],
                run=self.ARecordingRun(log, 0, 0),
                lock=self.ARecordingLock(log, "machine"),
                push_lock=self.ARecordingLock(log, "ref", grant=False),
            )
        self.assertEqual(2, code)
        self.assertNotIn("gate", log, repr(log))

    def test_the_machine_lock_is_released_when_the_ref_lock_refuses(self):
        """Otherwise a lane that cannot push wedges its own checkout."""
        log = []
        machine = self.ARecordingLock(log, "machine")
        with redirect_stderr(io.StringIO()):
            pusher.push_if_green(
                ["origin", "main"],
                run=self.ARecordingRun(log, 0, 0),
                lock=machine,
                push_lock=self.ARecordingLock(log, "ref", grant=False),
            )
        self.assertEqual(1, machine.released)

    def test_both_are_released_after_a_push(self):
        log = []
        machine = self.ARecordingLock(log, "machine")
        ref = self.ARecordingLock(log, "ref")
        with redirect_stderr(io.StringIO()):
            pusher.push_if_green(
                ["origin", "main"],
                run=self.ARecordingRun(log, 0, 0),
                lock=machine, push_lock=ref,
            )
        self.assertEqual(1, machine.released)
        self.assertEqual(1, ref.released)


if __name__ == "__main__":
    unittest.main()
