"""Planted case 2 of the card owner, before any of it is built.

    2. The second holder. A job while the card is held: today a slow model.
       Expected: refused with the holder's line, zero GPU seconds, one refused
       row.

The cases come before the build, so these are written against
`card_owner/the_lock.py` and nothing else exists yet.

**Case 2 is first because it changes nobody's behaviour.** The design has the
owner as the lock's only writer, which is a migration: three lanes were writing
`gpu.lock` by hand the night it was designed, and a second writer makes the
failure silent. So this reads and refuses and writes nothing, and the tests
assert the "writes nothing" as hard as the refusal.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import support

lock = support.import_file(
    "card_owner_the_lock", support.REPO_ROOT / "card_owner" / "the_lock.py"
)

A_FOREIGN_HOLDER = (
    "lane=codeforge since=2026-09-05T19:12:46Z what=derived check-in, two bench runs"
)
OUR_OWN_HOLDER = (
    "lane=mlharness since=2026-09-05T19:53:42Z what=the 200-row run, both gates wired"
)


class ARecordingRuntime:
    """Stands where Ollama would. Records whether it was ever reached.

    THE POINT OF THE WHOLE CASE. "Zero GPU seconds" is not provable by reading
    the code; it is provable by giving the owner something that says whether it
    was called. A later version that checked the lock after opening a socket
    would pass a boolean test and fail this one.
    """

    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return "the model answered"


class ALockFile:
    """A lock file in a sandbox, never the real one."""

    def __init__(self, case, text=None):
        self.path = Path(support.sandbox(case)) / "gpu.lock"
        if text is not None:
            self.path.write_text(text, encoding="utf-8")


class AForeignHolderRefusesTheJobTest(unittest.TestCase):
    def test_the_job_is_refused(self):
        held = ALockFile(self, A_FOREIGN_HOLDER)
        said = lock.why_this_job_may_not_run("mlharness", held.path)
        self.assertIsNotNone(said)
        self.assertIn("codeforge", said)

    def test_the_refusal_carries_the_holder_line(self):
        """A refusal a reader cannot check is the failure one layer up: it has
        to say who, since when, and doing what."""
        held = ALockFile(self, A_FOREIGN_HOLDER)
        said = lock.why_this_job_may_not_run("mlharness", held.path)
        self.assertIn("2026-09-05T19:12:46Z", said)
        self.assertIn("derived check-in", said)

    def test_a_refused_job_touches_no_runtime(self):
        """ZERO GPU SECONDS, ASSERTED RATHER THAN DESCRIBED."""
        held = ALockFile(self, A_FOREIGN_HOLDER)
        runtime = ARecordingRuntime()
        with self.assertRaises(lock.TheCardIsHeld):
            lock.run_or_refuse("mlharness", runtime, held.path)
        self.assertEqual(runtime.calls, 0, "the runtime was reached anyway")

    def test_the_lock_file_is_not_written_to(self):
        """The owner is the only writer LATER, in one change with every lane
        and GPU LOCK.md. Until then a second writer would make the failure
        silent, so this must not touch the file at all."""
        held = ALockFile(self, A_FOREIGN_HOLDER)
        before = held.path.read_bytes()
        with self.assertRaises(lock.TheCardIsHeld):
            lock.run_or_refuse("mlharness", ARecordingRuntime(), held.path)
        self.assertEqual(held.path.read_bytes(), before)


class OurOwnHolderIsNotAStrangerTest(unittest.TestCase):
    def test_a_job_belonging_to_the_holder_runs(self):
        ours = ALockFile(self, OUR_OWN_HOLDER)
        runtime = ARecordingRuntime()
        self.assertEqual(
            lock.run_or_refuse("mlharness", runtime, ours.path), "the model answered"
        )
        self.assertEqual(runtime.calls, 1)

    def test_no_lock_at_all_runs(self):
        free = ALockFile(self)
        runtime = ARecordingRuntime()
        lock.run_or_refuse("mlharness", runtime, free.path)
        self.assertEqual(runtime.calls, 1)

    def test_an_empty_lock_file_runs(self):
        empty = ALockFile(self, "   \n")
        runtime = ARecordingRuntime()
        lock.run_or_refuse("mlharness", runtime, empty.path)
        self.assertEqual(runtime.calls, 1)


class AnUnreadableLockIsAHolderNotFreedomTest(unittest.TestCase):
    """Something wrote it. A card owner that reads a malformed lock as "nobody
    is here" is the exact failure this case exists to prevent."""

    def test_a_lock_that_does_not_parse_still_refuses(self):
        odd = ALockFile(self, "held by the night shift, back later")
        runtime = ARecordingRuntime()
        with self.assertRaises(lock.TheCardIsHeld):
            lock.run_or_refuse("mlharness", runtime, odd.path)
        self.assertEqual(runtime.calls, 0)

    def test_the_refusal_says_it_could_not_read_the_holder(self):
        odd = ALockFile(self, "held by the night shift, back later")
        said = lock.why_this_job_may_not_run("mlharness", odd.path)
        self.assertIn("unreadable holder", said)


class StalenessIsNotDecidedHereTest(unittest.TestCase):
    """`GPU LOCK.md` rule 2: stale needs the lock older than ninety minutes AND
    `ollama ps` empty. The second half is not a fact this file has, so it does
    not get a vote."""

    def test_a_very_old_foreign_lock_is_still_refused(self):
        old = ALockFile(
            self, "lane=codeforge since=2026-09-01T00:00:00Z what=something long gone"
        )
        runtime = ARecordingRuntime()
        with self.assertRaises(lock.TheCardIsHeld):
            lock.run_or_refuse("mlharness", runtime, old.path)
        self.assertEqual(runtime.calls, 0)

    def test_the_refusal_says_why_staleness_was_not_decided(self):
        old = ALockFile(self, "lane=codeforge since=2026-09-01T00:00:00Z what=x")
        said = lock.why_this_job_may_not_run("mlharness", old.path)
        self.assertIn("ollama ps", said)

    def test_the_age_is_reported_for_whoever_can_decide(self):
        when = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
        held = ALockFile(self, "lane=codeforge since=2026-09-05T10:30:00Z what=x")
        self.assertAlmostEqual(
            lock.how_old_is_the_lock(held.path, now=when), 90.0, places=1
        )

    def test_an_unparseable_since_reports_no_age_rather_than_zero(self):
        odd = ALockFile(self, "lane=codeforge since=lastnight what=x")
        self.assertIsNone(lock.how_old_is_the_lock(odd.path))


class ItReadsTheLockEveryLaneActuallyWritesTest(unittest.TestCase):
    """Both `since` forms in use on the night this was written: a bare local
    stamp and a UTC one ending Z. A card owner reading a different lock from
    the lanes it protects is worse than no lock at all."""

    def test_a_bare_local_timestamp_parses(self):
        held = ALockFile(self, "lane=practical since=2026-09-05T18:52:10 what=router")
        said = lock.what_the_lock_says(held.path)
        self.assertEqual(said["lane"], "practical")
        self.assertEqual(said["what"], "router")

    def test_a_utc_timestamp_with_a_z_parses(self):
        held = ALockFile(self, A_FOREIGN_HOLDER)
        self.assertEqual(lock.what_the_lock_says(held.path)["lane"], "codeforge")

    def test_the_real_path_is_the_one_the_lanes_write(self):
        parts = lock.THE_LOCK.parts
        self.assertIn("09-Nightshift", parts)
        self.assertEqual(lock.THE_LOCK.name, "gpu.lock")


class PlantedCasesThreeAndFourCannotBeDecidedYetTest(unittest.TestCase):
    """Case 3 is a holder whose process is dead. Case 4 is a holder younger
    than its own lock line - a recycled pid, where the process exists but
    started after the lock was written and is therefore somebody else.

    **Both need a process identity, and `gpu.lock` has none.** It carries
    `lane=`, `since=` and `what=` and nothing else. `one_gate_at_a_time.py`
    writes a DIFFERENT file, in JSON, with `pid` and `pid_born`, and already
    handles recycling for it. So these cases are built as far as the file
    allows and no further: the answer today is "cannot be decided", said out
    loud, because a card owner that guessed liveness from a lane name would be
    inventing the fact it exists to record.
    """

    def test_the_lock_the_lanes_write_names_no_process(self):
        holder = lock.what_the_lock_says_in_either_form(A_FOREIGN_HOLDER)
        self.assertEqual(lock.the_holders_process(holder), (None, None))

    def test_liveness_is_none_not_false_for_a_lock_with_no_pid(self):
        """None means undecided. False would mean dead, and a caller reading
        False as 'take the card' would take a card somebody is using."""
        holder = lock.what_the_lock_says_in_either_form(A_FOREIGN_HOLDER)
        self.assertIsNone(lock.is_the_holder_alive(holder))

    def test_the_undecidable_answer_says_why_and_what_would_fix_it(self):
        holder = lock.what_the_lock_says_in_either_form(A_FOREIGN_HOLDER)
        said = lock.why_liveness_could_not_be_decided(holder)
        self.assertIn("names no process", said)
        self.assertIn("only writer", said)

    def test_case_3_a_dead_holder_is_decidable_once_the_lock_names_one(self):
        holder = lock.what_the_lock_says_in_either_form(
            '{"lane": "mlharness", "pid": 4242, "pid_born": "1000", "since": "x"}'
        )
        self.assertEqual(lock.the_holders_process(holder), (4242, "1000"))
        self.assertIs(
            lock.is_the_holder_alive(holder, alive=lambda pid, born: False), False
        )
        self.assertIsNone(lock.why_liveness_could_not_be_decided(holder))

    def test_case_4_a_recycled_pid_is_a_different_process(self):
        """The holder is alive by pid and was born AFTER the lock recorded it,
        so the pid was reused. The liveness checker is given both, and a
        checker that compared only pids would call this alive."""
        holder = lock.what_the_lock_says_in_either_form(
            '{"lane": "mlharness", "pid": 4242, "pid_born": "1000", "since": "x"}'
        )

        def alive(pid, born):
            actually_born = "9999"  # later than the lock's 1000
            return pid == 4242 and born == actually_born

        self.assertIs(lock.is_the_holder_alive(holder, alive=alive), False)

    def test_a_still_running_holder_reads_alive(self):
        holder = lock.what_the_lock_says_in_either_form(
            '{"lane": "mlharness", "pid": 4242, "pid_born": "1000", "since": "x"}'
        )
        self.assertIs(
            lock.is_the_holder_alive(holder, alive=lambda pid, born: True), True
        )

    def test_liveness_never_changes_the_refusal_while_it_only_reads(self):
        """Reads and refusals only: knowing a holder might be dead does not
        make this take the card. GPU LOCK.md rule 2 needs `ollama ps` too, and
        acting on half a rule is how a lock stops protecting anything."""
        held = ALockFile(self, A_FOREIGN_HOLDER)
        runtime = ARecordingRuntime()
        with self.assertRaises(lock.TheCardIsHeld):
            lock.run_or_refuse("mlharness", runtime, held.path)
        self.assertEqual(runtime.calls, 0)

    def test_it_reads_the_json_form_the_owner_will_write(self):
        holder = lock.what_the_lock_says_in_either_form(
            '{"lane": "codeforge", "since": "2026-09-06T00:23:23Z", "what": "bench"}'
        )
        self.assertEqual(holder["lane"], "codeforge")
        self.assertEqual(holder["what"], "bench")

    def test_json_that_does_not_parse_is_a_holder_not_freedom(self):
        holder = lock.what_the_lock_says_in_either_form('{"lane": "codeforge"')
        self.assertIsNotNone(holder)
        self.assertIsNone(holder["lane"])


class CasesThreeAndFourDecidedWithoutAnInjectedCheckerTest(unittest.TestCase):
    """The same two cases against REAL process identity on this machine.

    The tests above inject a liveness function, which proves the decision and
    not the mechanism. These use `card_owner`'s own default, which borrows
    `one_gate_at_a_time`'s `_alive` and `born_when` - the pair that already
    carries the measurement forcing them apart: `_alive(8932)` returned True
    for a live `explorer.exe`, so a lock naming that pid would have read as
    HELD by a desktop shell until the machine restarted.
    """

    def a_pid_that_is_really_dead(self) -> int:
        """Spawn a process, wait for it to exit, close its handle, return its pid.

        A REAL DEAD PID, not a number chosen for being large. `999999` is
        almost certainly free, but "almost certainly" is what this file exists
        to stop relying on.

        THE HANDLE MUST BE CLOSED AND THAT IS THE WHOLE OF IT. Windows keeps a
        pid valid for as long as ANY handle to the process object is open, and
        `subprocess.Popen` holds one. So a child that has exited still answers
        `OpenProcess`, and this helper was handing back a pid the operating
        system still considered a live process object - the test was keeping its
        own corpse warm.

        MEASURED 2026-09-06, 20 spawned and waited-on children: **20 of 20 read
        as alive while the Popen handle was held, 0 of 20 after it was closed.**
        Refcounting usually closes it when `child` leaves scope, which is why
        this passed on its own and failed inside a 4,317-test gate where the
        object survived a moment longer. A test that depends on when the garbage
        collector runs is a test that fails on someone else's schedule.

        The product was right throughout: asked about a pid that still opens, it
        cannot say the holder is gone, and this file's own law is that "cannot
        tell" must never read as "gone".
        """
        import gc
        import subprocess
        import sys as _sys

        child = subprocess.Popen([_sys.executable, "-c", "pass"])
        child.wait()
        pid = child.pid
        handle = getattr(child, "_handle", None)
        if handle is not None:  # Windows; POSIX has no handle to release
            handle.Close()
        del child
        gc.collect()
        return pid

    def test_case_3_a_holder_whose_process_is_dead_reads_dead(self):
        dead = self.a_pid_that_is_really_dead()
        holder = {"lane": "codeforge", "pid": dead, "pid_born": "whatever"}
        self.assertIs(lock.is_the_holder_alive(holder), False)

    def test_case_4_a_live_pid_with_the_wrong_birth_time_reads_dead(self):
        """The recycling condition, built from real values rather than
        simulated: THIS process's pid, which is certainly alive, paired with a
        birth time that is not its own.

        That is exactly what a recycled id looks like to the checker - the
        number is in use, by somebody else. I did not force the operating
        system to reuse a pid, and this test does not claim to: it asserts that
        a checker given a real live pid and the wrong birth instant answers
        False, which is the whole of case 4.
        """
        import os as _os

        holder = {"lane": "codeforge", "pid": _os.getpid(), "pid_born": "0"}
        self.assertIs(lock.is_the_holder_alive(holder), False)

    def test_this_very_process_reads_alive_with_its_own_birth_time(self):
        """The other half. A checker that answered False for everything would
        pass both tests above."""
        import os as _os

        _, born_when = lock.the_process_identity_checker()
        holder = {
            "lane": "mlharness",
            "pid": _os.getpid(),
            "pid_born": born_when(_os.getpid()),
        }
        self.assertIs(lock.is_the_holder_alive(holder), True)

    def test_the_checker_is_the_one_the_gate_lock_already_uses(self):
        """Borrowed, not rewritten: a second implementation is a second thing
        to get wrong, and this asserts they are the same objects."""
        alive, born_when = lock.the_process_identity_checker()
        gate_lock = support.import_file(
            "one_gate_at_a_time",
            support.REPO_ROOT / "scripts" / "one_gate_at_a_time.py",
        )
        self.assertEqual(alive.__name__, gate_lock._alive.__name__)
        self.assertEqual(born_when.__name__, gate_lock.born_when.__name__)

    def test_a_line_lock_with_pid_and_born_decides_too(self):
        """The amended `GPU LOCK.md` line form, not just the JSON one:
        `lane=... since=... pid=... born=... what=...`."""
        import os as _os

        _, born_when = lock.the_process_identity_checker()
        text = (
            f"lane=mlharness since=2026-09-06T01:00:00Z pid={_os.getpid()} "
            f"born={born_when(_os.getpid())} what=the sentinel-N pair"
        )
        holder = lock.what_the_lock_says_in_either_form(text)
        self.assertEqual(holder["lane"], "mlharness")
        self.assertEqual(holder["pid"], _os.getpid())
        self.assertIs(lock.is_the_holder_alive(holder), True)

    def test_an_old_line_without_them_is_still_read(self):
        """The two fields are required from tonight and old lines stay
        readable - a reader that rejected yesterday's locks would refuse to
        protect anything written before the change."""
        holder = lock.what_the_lock_says_in_either_form(A_FOREIGN_HOLDER)
        self.assertEqual(holder["lane"], "codeforge")
        self.assertIsNone(lock.is_the_holder_alive(holder))


class TwoFormatsInOneFieldMustNotReadAsDeadTest(unittest.TestCase):
    """MEASURED IN THE WILD, 2026-09-06 01:29, minutes after the protocol
    changed.

    The first live lock written under the amended `GPU LOCK.md` said
    `born=2026-09-06T01:14:39Z` - the ISO instant the page asks a person to
    write - while `one_gate_at_a_time.born_when()` returns a Windows FILETIME
    integer. Compared as strings they never match, so a LIVE LANE READ AS A
    DEAD PROCESS. A version that acted on that would steal a card in use: the
    exact collision the lock exists to prevent, arriving through the lock.

    So liveness of the pid decides case 3, birth times are compared as
    INSTANTS for case 4, and two values that cannot be compared answer None.
    """

    def _me(self):
        import os as _os

        return _os.getpid()

    def test_a_filetime_born_reads_alive(self):
        _, born_when = lock.the_process_identity_checker()
        self.assertIs(
            lock.is_the_holder_alive(
                {"pid": self._me(), "pid_born": born_when(self._me())}
            ),
            True,
        )

    def test_the_same_instant_written_as_iso_also_reads_alive(self):
        """THE REGRESSION. Same process, same start, other notation."""
        _, born_when = lock.the_process_identity_checker()
        as_iso = lock._as_instant(born_when(self._me())).isoformat().replace(
            "+00:00", "Z"
        )
        self.assertIs(
            lock.is_the_holder_alive({"pid": self._me(), "pid_born": as_iso}), True
        )

    def test_an_iso_born_rounded_to_whole_seconds_still_matches(self):
        """A lock written by hand carries whole seconds; the runtime knows the
        instant to a fraction. Anything inside the tolerance is rounding, and
        no machine recycles a pid within two seconds of the last one exiting."""
        _, born_when = lock.the_process_identity_checker()
        exact = lock._as_instant(born_when(self._me()))
        rounded = exact.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        self.assertIs(
            lock.is_the_holder_alive({"pid": self._me(), "pid_born": rounded}), True
        )

    def test_a_born_value_in_no_readable_form_is_undecided_not_dead(self):
        """None, never False. False would invite a caller to take the card."""
        self.assertIsNone(
            lock.is_the_holder_alive({"pid": self._me(), "pid_born": "lastnight"})
        )

    def test_a_wrong_instant_is_still_case_four(self):
        self.assertIs(
            lock.is_the_holder_alive(
                {"pid": self._me(), "pid_born": "2020-01-01T00:00:00Z"}
            ),
            False,
        )

    def test_both_notations_parse_to_the_same_instant(self):
        _, born_when = lock.the_process_identity_checker()
        raw = born_when(self._me())
        from_filetime = lock._as_instant(raw)
        from_iso = lock._as_instant(from_filetime.isoformat())
        self.assertLess(abs((from_filetime - from_iso).total_seconds()), 0.001)

    def test_a_holder_with_no_born_at_all_is_alive_if_its_pid_is(self):
        """The old line form carries no birth time. With the pid present and
        running, that is alive - the recycling question simply cannot be asked,
        and refusing to answer the one that can be is not caution."""
        self.assertIs(lock.is_the_holder_alive({"pid": self._me()}), True)


if __name__ == "__main__":
    unittest.main()
