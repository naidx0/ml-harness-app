"""A lock file that cannot be read is a lock that is HELD, not a lock that is absent.

## What happened, in three reads six minutes apart

Measured 2026-09-10 in the shared checkout, `ml-harness-gate.392f8026.lock`:

    05:23:43  {pid 23932, command verify_build.py, started 05:21:32}
              and 23932's child (3816) running `unittest discover`
    05:25:38  {pid 6268, command verify_build.py, started 05:25:38}
    05:29:58  the file does not exist
    05:30:54  23932 and 3816 are STILL RUNNING the suite

A second process took a lock whose holder was alive, and then a release deleted
a file it had not written - leaving a live gate holding nothing. That last state
is the one every reader in this module is built on never occurring.

## Neither liveness check failed. Neither ran.

`_holder()` answered `None` both for "there is no lock file" and for "there is a
lock file and I could not read it", and its two most important callers read the
second as the first:

  * `acquire` took `pid` from `(holder or {})`, got `0`, and `_alive(0, ...)` is
    False by its own first line - so it reached "the holder died without
    releasing" and stole a live lock.
  * `release` guarded with `if holder and int(...) != os.getpid()`, and `None`
    walked straight past it into `unlink(missing_ok=True)`.

A partial write, or a Windows sharing violation while another process rewrites
the file, produces exactly that `None`. The module's own law - three functions
below `_holder`, in `born_when` - is that empty means "could not tell", which
callers must treat as no evidence rather than as a mismatch. The two callers
that mattered most were the two that broke it.

## What is asserted here

Three states, three answers, and the unreadable one is read as a live foreign
holder: **wait, do not take; refuse, do not delete.** That is the same safe
direction `_alive` already takes when it cannot query a pid - the cost of
waiting for a lock nobody holds is a wait, and the cost of taking one somebody
holds is the collision this module exists to prevent.

NOT ASSERTED: that `born_when` differs between interpreters. It was the first
suspicion and it is wrong - `born_when` is a Win32 `GetProcessTimes` FILETIME
rendered `str((high << 32) | low)`, which is identical under any Python on this
machine. Written down so it is not chased again.
"""

from __future__ import annotations

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path

import support

lock = support.import_file(
    "one_gate_at_a_time", support.REPO_ROOT / "scripts" / "one_gate_at_a_time.py"
)


class TheThreeStatesGetThreeAnswersTest(unittest.TestCase):
    """`_holder` is where the conflation lived, so it is asserted directly."""

    def setUp(self):
        self.lock_path = Path(support.sandbox(self)) / "gate.lock"
        self._real = lock.LOCK
        lock.LOCK = self.lock_path
        self.addCleanup(lambda: setattr(lock, "LOCK", self._real))

    def test_an_absent_file_reads_as_no_holder(self):
        self.assertIsNone(lock._holder())

    def test_a_readable_file_reads_as_its_contents(self):
        self.lock_path.write_text(json.dumps({"pid": 4242}), encoding="utf-8")
        self.assertEqual(4242, lock._holder()["pid"])

    def test_a_file_that_is_not_json_reads_as_unreadable_and_not_as_absent(self):
        """THE CASE. A holder mid-write looks exactly like this."""
        self.lock_path.write_text("{partially writ", encoding="utf-8")
        holder = lock._holder()
        self.assertIsNotNone(holder, "an unreadable lock read as no lock at all")
        self.assertTrue(lock.is_unreadable(holder))

    def test_a_file_that_cannot_be_OPENED_reads_as_unreadable(self):
        """THE PRIMARY SUSPECT, AND MY FIRST THREE TESTS ALL MISSED IT.

        Mutation found this: collapsing the `OSError` arm back into `return
        None` left the suite green, because every case here wrote a file that
        opened fine and only failed to PARSE. The Windows sharing violation -
        another process holding the file open mid-write, which is the reading
        that actually explains 05:25:38 - takes the other arm entirely.

        A directory at the lock's path raises `OSError` on read while very much
        existing, which is that arm without needing to race a real writer.
        """
        self.lock_path.mkdir()
        holder = lock._holder()
        self.assertIsNotNone(holder, "an unopenable lock read as no lock at all")
        self.assertTrue(lock.is_unreadable(holder))

    def test_json_that_is_not_an_object_reads_as_unreadable(self):
        """`json.loads("null")` succeeds and returns None, which would have
        arrived at every caller as "no holder" through a different door."""
        for text in ("null", "[]", '"a string"', "7"):
            with self.subTest(text=text):
                self.lock_path.write_text(text, encoding="utf-8")
                self.assertTrue(lock.is_unreadable(lock._holder()))

    def test_the_two_absent_and_unreadable_answers_are_told_apart_in_words(self):
        """Both used to print the same sentence, which is how a reader could
        not have noticed either."""
        self.assertNotEqual(lock._describe(None), lock._describe(lock.UNREADABLE))
        self.assertIn("could not be read", lock._describe(lock.UNREADABLE))


class AcquireWaitsForALockItCannotRead(unittest.TestCase):
    def setUp(self):
        self.lock_path = Path(support.sandbox(self)) / "gate.lock"
        self._real = lock.LOCK
        lock.LOCK = self.lock_path
        self.addCleanup(lambda: setattr(lock, "LOCK", self._real))

    def test_it_refuses_rather_than_taking_an_unreadable_lock(self):
        """THE 05:25:38 EVENT. `timeout=0` so this asserts the DECISION and
        does not spend a wait proving it."""
        self.lock_path.write_text("{partially writ", encoding="utf-8")
        err = io.StringIO()
        with redirect_stderr(err):
            got = lock.acquire(0, "a test")
        self.assertFalse(got, "it took a lock whose file it could not read")
        self.assertIn("could not be read", err.getvalue())

    def test_the_file_is_left_exactly_as_it_was(self):
        """A refusal that rewrites the thing it refused is not a refusal."""
        self.lock_path.write_text("{partially writ", encoding="utf-8")
        with redirect_stderr(io.StringIO()):
            lock.acquire(0, "a test")
        self.assertEqual("{partially writ", self.lock_path.read_text(encoding="utf-8"))

    def test_an_absent_lock_is_still_acquirable(self):
        """THE CONTROL, and it is what stops the fix being a wedge. If this
        went red the module would refuse every gate on this machine."""
        with redirect_stderr(io.StringIO()):
            self.assertTrue(lock.acquire(5, "a test"))
        self.addCleanup(lock.release)
        self.assertEqual(os.getpid(), json.loads(
            self.lock_path.read_text(encoding="utf-8"))["pid"])


class ReleaseDeletesOnlyAFileItCanShowIsItsOwn(unittest.TestCase):
    def setUp(self):
        self.lock_path = Path(support.sandbox(self)) / "gate.lock"
        self._real = lock.LOCK
        lock.LOCK = self.lock_path
        self.addCleanup(lambda: setattr(lock, "LOCK", self._real))

    def test_an_unreadable_lock_is_left_on_disk(self):
        """THE 05:29:58 EVENT, and it is the worse half: `acquire` taking a
        held lock makes two suites collide, but `release` deleting one leaves a
        LIVE gate with no lock at all - the state every reader here assumes
        cannot happen."""
        self.lock_path.write_text("{partially writ", encoding="utf-8")
        err = io.StringIO()
        with redirect_stderr(err):
            lock.release()
        self.assertTrue(self.lock_path.is_file(), "it deleted a lock it could not read")
        self.assertIn("could not be read", err.getvalue())

    def test_another_process_s_lock_is_left_on_disk(self):
        """The guard that was already right, kept red so the rewrite above
        cannot quietly drop it."""
        self.lock_path.write_text(
            json.dumps({"pid": os.getpid() + 100000}), encoding="utf-8"
        )
        with redirect_stderr(io.StringIO()):
            lock.release()
        self.assertTrue(self.lock_path.is_file())

    def test_our_own_lock_is_released(self):
        """THE CONTROL. A release that never releases wedges the machine."""
        self.lock_path.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
        with redirect_stderr(io.StringIO()):
            lock.release()
        self.assertFalse(self.lock_path.exists())

    def test_an_absent_lock_is_not_an_error(self):
        with redirect_stderr(io.StringIO()):
            lock.release()
        self.assertFalse(self.lock_path.exists())


class TheSuspicionThatWasWrongTest(unittest.TestCase):
    """`born_when` was the first explanation offered and it is not available.

    It reads a Win32 FILETIME through `GetProcessTimes` and renders it
    `str((high << 32) | low)`. There is no formatting either interpreter could
    do differently, so a `pid_born` that disagreed across two Python builds was
    never the cause. Asserted rather than only written down, because a wrong
    explanation in a docstring is one somebody re-derives.
    """

    def test_a_pids_birth_reads_the_same_twice(self):
        me = os.getpid()
        self.assertEqual(lock.born_when(me), lock.born_when(me))

    def test_it_is_digits_and_not_a_formatted_time(self):
        said = lock.born_when(os.getpid())
        if not said:  # pragma: no cover - a platform that cannot tell
            self.skipTest("this machine cannot read process start times")
        self.assertTrue(said.isdigit(), f"born_when returned {said!r}")


if __name__ == "__main__":
    unittest.main()
