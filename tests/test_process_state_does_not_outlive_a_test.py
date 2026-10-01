"""A fresh database is not a fresh process, and the suite only ever asked for one.

## The class

`support.sandbox()` gives every test a new temporary directory and a new SQLite
file. It cannot give it a new interpreter. So every module-level dict, set and
list in `app/` carries whatever the previous test put there, and every
background thread a previous test started is still running - reading the same
module-level globals the new test has just rebound.

That matters more than it sounds, because of what the surviving state is KEYED
ON. `db.get_instance` exists because the repository already learned this once:

> A job id is not an identity. It is a counter, and `AUTOINCREMENT` restarts it
> at 1 for every fresh database - so "job 1" names a different job in every
> database that has ever existed on this machine.

Every test in this suite starts from a database whose first storm is storm 1,
whose first run is run 1 and whose first job is job 1. Under that shape,
process-level state keyed on those numbers is indistinguishable from state keyed
on an identity, exactly as one conversation makes a scoped record
indistinguishable from a global one. The suite could not tell, and cannot be
asked to notice.

## The two that are real, constructed below

**`storm._LIVE` / `storm._CANCELLED` hold storm ids.** `storm.run()` is a
generator that clears its id in a `finally`; a test that abandons the generator
without exhausting or closing it leaves the id behind. The next test gets a
brand-new database whose first storm is also number 1 - and finds it already
running, or already cancelled, in a conversation that has never seen it.

**`training._SUPERVISORS` holds live threads.** A supervisor resolves
`db.DB_PATH` when it next reads it, not when it started. One still running while
the next test rebinds the global writes its job row, its exit code and its
events into an unrelated test's database. That is the `logs/job_1.log`
collision of b024da4 with a thread in place of a filename, and it is a worse
version: the log collision was visible as a wrong file, this one is visible as a
row in the right table of the wrong database.

## What this file does

**1. It derives the roster.** `support.process_state_snapshot()` reports the
size of every module-level container under `app`. A test runs, and anything that
grew is state that outlives it. A container that grows for a good reason is
named in `RESIDENT_CACHES` with the reason; anything else fails, which is how
the next one of these gets caught rather than discovered.

**2. It constructs both failures.** Not by reading the code: by leaving the
state behind and watching the next sandbox trip over it.

**3. It asserts `sandbox()` now clears them,** by running a throwaway test case
through a real `TestResult` so the cleanup actually fires.

## The control

`test_the_snapshot_sees_something_left_behind` puts one entry in a module-level
dict and asserts the derived comparison names it. A drift detector that reports
nothing because it is looking at nothing is the failure mode this repository has
retracted a report over before.
"""

from __future__ import annotations

import threading
import unittest

from app import db, storm
from app.tools import training

import support


#: Module-level containers that legitimately grow and stay grown, with why.
#: Anything not here that grows during a test is state leaking into the next one.
RESIDENT_CACHES: dict[tuple[str, str], str] = {
    ("app.diagnosis", "_SPEC_CACHE"): (
        "the diagnosis spec, keyed on SPEC_PATH. The file is source and does not "
        "change during a run, so a hit is the same object a miss would build."
    ),
    ("app.diagnosis", "ACTION_HANDLERS"): "filled by decorators at import",
    ("app.diagnosis", "CONDITION_HANDLERS"): "filled by decorators at import",
    # ROUTE_KEYS was here and is gone. It held two functions keyed by the FIRST
    # ledger's node ids, which is why no second ledger could have a fork; forks
    # are executed from the declared `fork:` block now and there is no registry
    # to leak. A whitelist entry for a symbol that no longer exists is the kind
    # of stale list this file exists to argue against, so it goes with it.
}


class TheSnapshotIsDerivedTest(unittest.TestCase):
    """Layer 1. What grew, found by looking rather than by remembering."""

    def setUp(self):
        self.root = support.sandbox(self)

    def grown(self, before, after):
        return {
            key: (before.get(key, 0), size)
            for key, size in after.items()
            if size > before.get(key, 0) and key not in RESIDENT_CACHES
        }

    def test_a_full_tool_call_leaves_no_module_level_container_larger(self):
        from app.tools import REGISTRY

        alice, _ = support.conversations(2)
        before = support.process_state_snapshot()

        REGISTRY.call("list_context", {}, actor="user", thread_id=alice["id"])
        REGISTRY.call("list_runs", {}, actor="user", thread_id=alice["id"])

        grown = self.grown(before, support.process_state_snapshot())
        self.assertEqual(
            grown,
            {},
            "a tool call left something in a module-level container. If it is a "
            "cache that is safe to keep, add it to RESIDENT_CACHES with the "
            "reason; if it is keyed on a run, job, storm or thread id, it is "
            "keyed on a counter that restarts at 1 in the next test's database "
            f"and in the user's next install.\n\nGrew: {grown}",
        )

    def test_the_snapshot_sees_something_left_behind(self):
        """THE POSITIVE CONTROL. An empty diff must mean 'looked and found none'."""
        before = support.process_state_snapshot()
        storm._LIVE[424242] = 1.0
        self.addCleanup(storm._LIVE.pop, 424242, None)

        grown = self.grown(before, support.process_state_snapshot())

        self.assertIn(
            ("app.storm", "_LIVE"),
            grown,
            "the snapshot did not notice an entry appearing in a module-level "
            "dict, so its silence above means nothing",
        )


class AStormIdIsACounterNotAnIdentityTest(unittest.TestCase):
    """The first construction. Process state keyed on a per-database counter."""

    def setUp(self):
        self.root = support.sandbox(self)

    def test_a_leftover_live_id_makes_an_unrelated_storm_look_alive(self):
        """Storm 1 in a database that has never had a storm.

        `storm._is_live` is what `attach()` uses to tell a step that is running
        from one that was running when the engine died. With the id left behind,
        a brand-new storm 1 is reported as running before anything has started
        it, and `run()` refuses it as already running in this process.
        """
        self.assertFalse(
            storm._is_live(1), "this sandbox started with storm 1 already live"
        )

        storm._LIVE[1] = 1.0
        self.addCleanup(storm._LIVE.pop, 1, None)

        self.assertTrue(
            storm._is_live(1),
            "the id is the whole key - there is nothing else in _LIVE that "
            "could tell this database's storm 1 from another database's",
        )

    def test_a_leftover_cancellation_cancels_a_storm_nobody_cancelled(self):
        storm._CANCELLED.add(1)
        self.addCleanup(storm._CANCELLED.discard, 1)

        self.assertTrue(
            storm._stop_requested(1),
            "a cancellation left behind by an earlier storm 1 applies to this "
            "database's storm 1, which nobody has asked to stop",
        )

    def test_the_sandbox_clears_both_before_the_next_test(self):
        """The fix, watched rather than read.

        A throwaway case is run through a real `TestResult` so its `addCleanup`
        actually fires, and the state it left must be gone afterwards.
        """
        outer = self

        class Messy(unittest.TestCase):
            def runTest(self):
                support.sandbox(self)
                storm._LIVE[1] = 1.0
                storm._CANCELLED.add(1)
                outer.assertTrue(storm._is_live(1))

        result = unittest.TestResult()
        Messy().run(result)
        self.assertEqual(result.errors + result.failures, [])

        self.assertFalse(
            storm._is_live(1),
            "sandbox() cleanup left a storm id in _LIVE, so the next test's "
            "storm 1 is already running before it starts",
        )
        self.assertFalse(storm._stop_requested(1))


class ACounterIsNotAnIdentityTest(unittest.TestCase):
    """The rule the two constructions above are both instances of, pinned.

    `db.get_instance` exists because job ids repeat across databases, and
    `jobspec` keys artifact paths on the instance rather than on the id. That
    fix is only visible from a database with history: with one job in a fresh
    database, "keyed on the id" and "keyed on the identity" produce the same
    path, which is the shape every test in this suite had.

    `support.with_history()` is what makes the other shape cheap, and this is the
    test that could not have been written without it.
    """

    def test_the_same_job_id_in_two_databases_gets_two_run_directories(self):
        from app import jobspec

        support.sandbox(self)
        support.with_history(jobs=3)
        first_instance = jobspec.current_instance()
        first_dir = jobspec.run_dir_for(1)

        support.sandbox(self)
        support.with_history(jobs=3)
        second_instance = jobspec.current_instance()
        second_dir = jobspec.run_dir_for(1)

        self.assertNotEqual(
            first_instance,
            second_instance,
            "two databases minted the same identity, which would make every "
            "artifact path collide again",
        )
        self.assertNotEqual(
            first_dir,
            second_dir,
            "job 1 in two different databases resolved to one directory. That "
            "is the b024da4 collision: 'job 1' names a different job in every "
            "database that has ever existed on this machine.",
        )
        self.assertEqual(first_dir.name, second_dir.name, "both are job_1")

    def test_history_actually_moves_the_counter(self):
        """The control. If `with_history` made nothing, the test above is empty."""
        support.sandbox(self)
        made = support.with_history(jobs=2, runs=2, threads=2, projects=1)

        self.assertEqual([job["id"] for job in made["jobs"]], [1, 2])
        self.assertEqual([run["id"] for run in made["runs"]], [1, 2])
        self.assertEqual(len(made["threads"]), 2)

        next_job = db.create_job("intake-next", support.spec("printer"))
        self.assertEqual(
            next_job["id"],
            3,
            "a test starting after history still got id 1, so nothing here is "
            "measuring a database that has been used",
        )


class ABackgroundThreadReadsTheGlobalWhenItGetsThereTest(unittest.TestCase):
    """The second construction, deterministic rather than timed.

    `training.start_supervisor` runs `runner.run_next_job` on a daemon thread,
    and everything in that path reaches the database through `db.DB_PATH` - a
    module-level global, read at the moment of the call. The dangerous property
    is not the supervisor specifically, it is that a thread outliving a test
    writes wherever the global points WHEN IT ARRIVES, which is the next test's
    database. That is shown here with an event instead of a job, so the proof
    does not depend on how long a subprocess happens to take.
    """

    def test_a_thread_started_in_one_sandbox_writes_into_the_next_one(self):
        first = support.sandbox(self)
        first_db = db.DB_PATH
        db.create_run("run-in-the-first-database", "{}")

        released = threading.Event()
        landed: dict[str, object] = {}

        def late_writer():
            released.wait(timeout=10)
            landed["row"] = db.create_run("written-by-a-thread-from-before", "{}")
            landed["db"] = db.DB_PATH

        worker = threading.Thread(target=late_writer, daemon=True)
        worker.start()

        # The next test begins: a new sandbox rebinds the global.
        second = support.sandbox(self)
        second_db = db.DB_PATH
        self.assertNotEqual(first_db, second_db)

        released.set()
        worker.join(timeout=10)
        self.assertFalse(worker.is_alive())

        self.assertEqual(
            landed["db"],
            second_db,
            "the thread resolved db.DB_PATH at start rather than at use - if "
            "that is ever true, this whole class is measuring nothing",
        )
        names = [row["name"] for row in db.list_runs()]
        self.assertIn(
            "written-by-a-thread-from-before",
            names,
            "the row from the earlier test's thread landed in this sandbox's "
            "database. A supervisor left running by one test writes its job "
            "row, exit code and events into the next test's database, and "
            "nothing in the suite would report it as anything but a strange "
            "extra row.",
        )
        self.assertNotIn("run-in-the-first-database", names)
        self.assertTrue(first.is_dir() and second.is_dir())

    def test_the_sandbox_joins_supervisors_before_the_next_test_starts(self):
        """The fix for the family: no supervisor survives a test's cleanup.

        `start_supervisor` with nothing queued returns almost at once, so this
        asserts the joining rather than the waiting. The point is that cleanup
        does it at all: before this, `wait_for_supervisors` was called by
        exactly one test file and by nothing else in 1057 tests.
        """
        outer = self

        class StartsASupervisor(unittest.TestCase):
            def runTest(self):
                support.sandbox(self)
                training.start_supervisor(timeout=5)
                outer.assertTrue(training._SUPERVISORS)

        result = unittest.TestResult()
        StartsASupervisor().run(result)
        self.assertEqual(result.errors + result.failures, [])

        self.assertEqual(
            [thread for thread in training._SUPERVISORS if thread.is_alive()],
            [],
            "a supervisor thread outlived the test that started it. It will "
            "write into whichever database db.DB_PATH names when it next "
            "reads it, which is the next test's.",
        )


if __name__ == "__main__":
    unittest.main()
