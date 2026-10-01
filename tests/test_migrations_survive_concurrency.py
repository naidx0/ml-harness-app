"""Two processes migrating at once must not kill one of them.

`app/migrations/__init__.py` says `migrate()` "is safe to call on every
request". Until the change this file was written for, that sentence was true
for one process at a time and false for the number this product actually runs:
the engine, the job runner and a test suite each call `db.init_db()` at
startup, and on a fresh database they can be inside it together.

## What went wrong

The version was read outside any write lock and `_apply` opened its
transaction with a bare `BEGIN`, which is `BEGIN DEFERRED`. Two processes both
read "version 0", both concluded migration 1 was owed, and the loser re-ran it.
Measured on this machine before the fix, four processes calling `init_db()` on
a fresh database killed at least one of themselves in **13 of 40 trials**; with
the time-of-check-to-time-of-use window widened to 300 ms so the outcome stops
depending on the scheduler, **30 of 40 processes** died. Three shapes of death:

- `UNIQUE constraint failed: schema_version.version` - the loser tried to
  record a version the winner had already recorded.
- `duplicate column name: project_id` - migration 4 contains
  `ALTER TABLE threads ADD COLUMN project_id`, the one statement in the tree
  that cannot be written `IF NOT EXISTS`, so a second application is an error
  rather than a no-op.
- `database is locked` - a deferred transaction's first write has to upgrade
  `SHARED` to `RESERVED`, and that is the one contention case SQLite reports
  immediately without calling the busy handler.

The data was never wrong: every trial ended at version 4 with fourteen tables,
one identity row and `PRAGMA integrity_check = ok`. What was wrong was that a
process died at startup, and that it died saying **"the database is still at
version 0"** about a file that was at 4, because the message computed
`version - 1` instead of reading the database.

## Why these tests and not a fuzzer

Random concurrency does not find this. The window is a few milliseconds wide
and the natural rate is roughly one process in twelve; a test that fails 8% of
the time teaches nobody anything. So the two tests that matter here **widen the
window on purpose** - `_apply` is wrapped in a sleep, which changes when things
happen and nothing about what they do - so that before the fix they fail every
time and after it they pass every time. `test_migration_four_is_not_idempotent`
is here to stop the next reader concluding the lock is belt-and-braces: it is
load-bearing, and that test names the statement that makes it load-bearing.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

from app import db, migrations

import support


REPO_ROOT = Path(__file__).resolve().parents[1]

#: How many processes race, and over how many trials. Both are raisable from
#: the environment so the same test is the harness: `MLH_RACE_TRIALS=40` is the
#: run the numbers in the docstring above came from. The defaults are what the
#: suite pays for on every run, and they are small because the window is
#: widened below - three deterministic trials prove more than forty flaky ones.
RACE_PROCESSES = int(os.environ.get("MLH_RACE_PROCESSES", "4"))
RACE_TRIALS = int(os.environ.get("MLH_RACE_TRIALS", "3"))

#: Seconds of sleep injected between the unlocked version read and the apply.
#: That gap *is* the time-of-check-to-time-of-use window. 0.15 s is two orders
#: of magnitude wider than the ~7 ms a full migration takes, so every racer
#: lands inside it and the result stops being a coin flip.
WINDOW = float(os.environ.get("MLH_RACE_WINDOW", "0.15"))

#: The child of the multi-process test. It widens the window the same way the
#: in-process tests do, then calls the real entry point - `db.init_db()`, not
#: `migrate()` - because `init_db` is what every process in this product
#: actually calls and it does two more things afterwards.
CHILD = "\n".join(
    [
        "import os, sys, time",
        "sys.path.insert(0, os.environ['MLH_REPO'])",
        "from app import db, migrations",
        "real = migrations._apply",
        "def widened(connection, version, sql):",
        "    time.sleep(float(os.environ['MLH_WINDOW']))",
        "    return real(connection, version, sql)",
        "migrations._apply = widened",
        "start = float(os.environ['MLH_START_AT'])",
        "while time.time() < start:",
        "    pass",
        "db.init_db()",
    ]
)


def widen_the_window(test, seconds: float = WINDOW) -> None:
    """Sleep between the unlocked read and the apply, for this test only.

    A timing injection, not a stub: `_apply` still does everything it does,
    with the arguments it would have had. All this changes is *when* the second
    caller arrives, which is the variable the defect was hiding behind.
    """
    real = migrations._apply

    def widened(connection, version, sql):
        time.sleep(seconds)
        return real(connection, version, sql)

    migrations._apply = widened
    test.addCleanup(setattr, migrations, "_apply", real)


class ConcurrentMigrationTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)

    def fresh(self) -> Path:
        """A database path nothing has migrated yet."""
        db.DB_PATH = self.root / "race.db"
        return db.DB_PATH

    def highest(self) -> int:
        return migrations.MIGRATIONS[-1][0]

    def state(self, path: Path | None = None) -> dict:
        """What the database ended up as, read with a connection of our own."""
        connection = sqlite3.connect(path or db.DB_PATH)
        try:
            versions = [
                row[0]
                for row in connection.execute(
                    "SELECT version FROM schema_version ORDER BY version"
                )
            ]
            tables = sorted(
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            )
            columns = [
                row[1] for row in connection.execute("PRAGMA table_info(threads)")
            ]
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            connection.close()
        return {
            "versions": versions,
            "tables": tables,
            "thread_columns": columns,
            "integrity": integrity,
        }

    # -- the defect, reproduced across processes ---------------------------

    def test_concurrent_processes_on_a_fresh_database_all_survive(self):
        """The adversary's repro: N processes, one fresh database, T trials.

        Subprocesses rather than threads, because that is the reported shape
        and because a thread shares this process's `db.DB_PATH` rebinding while
        a real engine does not - the child resolves `ML_HARNESS_DB` for itself,
        which is also what keeps it off the user's real database.

        Every process must exit 0. Before the fix, with this window, roughly
        three in four did not.
        """
        deaths: list[str] = []
        for trial in range(RACE_TRIALS):
            path = self.root / f"trial{trial}.db"
            environment = dict(os.environ)
            environment["MLH_REPO"] = str(REPO_ROOT)
            environment["ML_HARNESS_DB"] = str(path)
            environment["MLH_WINDOW"] = str(WINDOW)
            # A wall-clock start line, so the processes collide instead of
            # queueing behind each other's interpreter startup.
            environment["MLH_START_AT"] = str(time.time() + 2.0)

            processes = [
                subprocess.Popen(
                    [sys.executable, "-c", CHILD],
                    env=environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for _ in range(RACE_PROCESSES)
            ]
            results = [process.communicate() for process in processes]
            for process, (_, errors) in zip(processes, results):
                if process.returncode != 0:
                    deaths.append(f"trial {trial}: {errors.strip()}")

            state = self.state(path)
            self.assertEqual(
                state["versions"],
                [version for version, _ in migrations.MIGRATIONS],
                f"trial {trial} left the schema_version table wrong",
            )
            self.assertEqual(state["integrity"], "ok")
            self.assertEqual(
                state["thread_columns"].count("project_id"),
                1,
                f"trial {trial}: migration 4 ran more than once",
            )

        self.assertEqual(
            deaths,
            [],
            f"{len(deaths)} of {RACE_PROCESSES * RACE_TRIALS} processes died "
            "calling init_db() on a fresh database:\n\n" + "\n\n".join(deaths),
        )

    # -- the defect, reproduced deterministically in one process -----------

    def test_the_loser_of_the_race_no_ops_instead_of_reapplying(self):
        """Four threads, one fresh database, the window held open.

        Every one of them reads "version 0" before any of them holds the lock,
        which is the exact state the defect needed. What has to happen now is
        that the three that lose re-read under the lock and find there is
        nothing left to do.

        The assertions are about the database, not about the absence of an
        exception, because "nobody raised" would also be satisfied by a runner
        that applied migration 4 four times and swallowed the error.
        """
        self.fresh()
        widen_the_window(self)

        started = threading.Barrier(4)
        failures: list[BaseException] = []
        answers: list[int] = []
        guard = threading.Lock()

        def racer():
            started.wait()
            try:
                answer = migrations.migrate()
            except BaseException as error:  # noqa: BLE001 - reported below
                with guard:
                    failures.append(error)
            else:
                with guard:
                    answers.append(answer)

        threads = [threading.Thread(target=racer) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        self.assertEqual(
            [f"{type(e).__name__}: {e}" for e in failures],
            [],
            "a thread died migrating a database another thread was migrating",
        )
        self.assertEqual(
            answers,
            [self.highest()] * 4,
            "every caller must be told the version the database is at",
        )

        state = self.state()
        self.assertEqual(
            state["versions"], [version for version, _ in migrations.MIGRATIONS]
        )
        self.assertEqual(
            state["thread_columns"].count("project_id"),
            1,
            "migration 4's ALTER TABLE ran twice",
        )
        self.assertEqual(state["integrity"], "ok")

    def test_every_migration_transaction_is_begun_immediate(self):
        """The mechanism, watched rather than inferred.

        `BEGIN` is `BEGIN DEFERRED`: it takes no lock, so the transaction's
        first write has to upgrade `SHARED` to `RESERVED` while holding a read
        lock - and that is the contention case SQLite is entitled to report as
        `SQLITE_BUSY` without ever calling the busy handler, because two
        processes both waiting to upgrade would deadlock. `BEGIN IMMEDIATE`
        asks for `RESERVED` before it holds anything, so the handler runs and
        the second process queues.

        The difference between the two is one word in one string and no test
        of outcomes distinguishes them quickly - a deferred writer usually gets
        the lock anyway, just not reliably. So this watches the statements the
        runner actually sends, through `sqlite3`'s own trace callback, and the
        assertion is on the word.
        """
        self.fresh()

        seen: list[str] = []
        real = migrations._apply

        def watched(connection, version, sql):
            connection.set_trace_callback(seen.append)
            try:
                return real(connection, version, sql)
            finally:
                connection.set_trace_callback(None)

        migrations._apply = watched
        self.addCleanup(setattr, migrations, "_apply", real)

        self.assertEqual(migrations.migrate(), self.highest())

        begins = [
            statement.strip()
            for statement in seen
            if statement.strip().upper().startswith("BEGIN")
        ]
        self.assertEqual(
            len(begins),
            len(migrations.MIGRATIONS),
            "one transaction per migration is the property this module is "
            f"built on; saw {begins}",
        )
        for statement in begins:
            self.assertEqual(
                statement.upper(),
                "BEGIN IMMEDIATE",
                "a deferred transaction does not queue for the write lock, "
                "it dies on it",
            )

    def test_a_process_behind_a_held_lock_waits_instead_of_dying(self):
        """The behaviour that mechanism buys, at the level a caller sees it.

        A connection holds the write lock for 0.4 s while `migrate()` runs on a
        fresh database. The elapsed-time assertion is the one that stops this
        being vacuous - without it the test would pass if `migrate()` finished
        before the lock was ever taken.

        This one is a pin, not a discriminator: the code before the fix also
        survived a lock held for 0.4 s, because `sqlite3`'s own five-second
        default caught it. It died when the hold ran past five seconds, and it
        died on the wrong statement with the wrong version in the message. The
        discriminating tests are the two above and the two below; this is here
        so that a future change which drops the busy timeout to zero, or takes
        no lock at all, goes red on a behaviour rather than on an internal.
        """
        self.fresh()
        # Bring the file into existence so the holder has something to lock;
        # `migrate()` still has all four migrations to apply afterwards.
        sqlite3.connect(db.DB_PATH).close()

        holding = threading.Event()
        hold_for = 0.4

        def holder():
            connection = sqlite3.connect(db.DB_PATH)
            try:
                connection.execute("BEGIN IMMEDIATE")
                holding.set()
                time.sleep(hold_for)
                connection.rollback()
            finally:
                connection.close()

        thread = threading.Thread(target=holder)
        thread.start()
        self.addCleanup(thread.join)
        self.assertTrue(holding.wait(timeout=10), "the holder never got the lock")

        start = time.perf_counter()
        version = migrations.migrate()
        waited = time.perf_counter() - start

        self.assertEqual(version, self.highest())
        self.assertGreaterEqual(
            waited,
            hold_for * 0.8,
            "migrate() returned without ever waiting for the lock, so this "
            "test proved nothing about what happens when it is held",
        )
        self.assertEqual(self.state()["integrity"], "ok")

    # -- the message, which was the more expensive half --------------------

    def test_a_lock_timeout_reports_the_version_it_read(self):
        """The failure message must name a version it looked up, not `n - 1`.

        This is the case where the arithmetic lied. A process reads "version 0",
        another process takes the database to 4 and is still holding the lock
        when the first one wakes up: the old message announced "the database is
        still at version 0", and whoever read it went looking for an unmigrated
        database that did not exist.

        The stale read is injected rather than raced for, because racing for it
        is exactly the coin flip this file refuses to build a test on. What is
        injected is a *reading taken a moment too early* - which is the defect
        itself, not a stand-in for it. Everything after it is the real code.
        """
        self.fresh()
        self.assertEqual(migrations.migrate(), self.highest())

        holder = sqlite3.connect(db.DB_PATH)
        self.addCleanup(holder.close)
        holder.execute("BEGIN IMMEDIATE")

        self.addCleanup(
            setattr, migrations, "BUSY_TIMEOUT_MS", migrations.BUSY_TIMEOUT_MS
        )
        migrations.BUSY_TIMEOUT_MS = 250

        real = migrations._applied
        self.addCleanup(setattr, migrations, "_applied", real)
        calls = {"count": 0}

        def stale_the_first_time(connection):
            calls["count"] += 1
            return [] if calls["count"] == 1 else real(connection)

        migrations._applied = stale_the_first_time

        with self.assertRaises(migrations.MigrationError) as raised:
            migrations.migrate()

        message = str(raised.exception)
        self.assertIn(
            f"at version {self.highest()}",
            message,
            f"the message does not name the version the database is at: {message}",
        )
        self.assertNotIn(
            "still at version 0",
            message,
            "the message is computing the version again instead of reading it",
        )
        self.assertIn("migration 1", message, "it should say what it was doing")

    def test_a_failed_migration_still_says_what_it_rolled_back_to(self):
        """The honest message on the ordinary, uncontended failure path.

        Mutation check, and a companion to the one in
        `tests/test_migration_runner.py`: migration 2's second statement is
        nonsense, so the runner must roll back and report version 1 - which
        here it reads out of `schema_version` rather than deducing.
        """
        self.fresh()
        good = migrations.MIGRATIONS
        migrations.MIGRATIONS = [
            good[0],
            (
                2,
                "CREATE TABLE half_applied (id INTEGER PRIMARY KEY);\n"
                "CREATE TABLE nonsense (id INTEGER PRIMARY KEY) SYNTAX ERROR;\n",
            ),
        ]
        self.addCleanup(setattr, migrations, "MIGRATIONS", good)

        with self.assertRaises(migrations.MigrationError) as raised:
            migrations.migrate()

        message = str(raised.exception)
        self.assertIn("migration 2 failed", message)
        self.assertIn("the database is at version 1", message)
        self.assertEqual(self.state()["versions"], [1])

    # -- the two properties the fix rests on -------------------------------

    def test_an_up_to_date_database_never_asks_for_the_write_lock(self):
        """Why the unlocked read at the top of `migrate()` is allowed to stay.

        `migrate()` has seven call sites - `db.init_db`, five `ensure_*`
        helpers in `app/db.py` and `events.ensure_tables` - which run at the
        top of nearly every request. If it took a write lock to discover it
        had nothing to do, the whole engine would serialise behind the
        migration runner. So: hold the lock, shorten the timeout to a
        second, and call `migrate()` on a database that is already current. It
        must answer immediately. If it ever starts asking for the lock first,
        this raises instead.
        """
        self.fresh()
        self.assertEqual(migrations.migrate(), self.highest())

        holder = sqlite3.connect(db.DB_PATH)
        self.addCleanup(holder.close)
        holder.execute("BEGIN IMMEDIATE")

        self.addCleanup(
            setattr, migrations, "BUSY_TIMEOUT_MS", migrations.BUSY_TIMEOUT_MS
        )
        migrations.BUSY_TIMEOUT_MS = 250

        # The assertion that carries the weight is the one above: the lock is
        # held for the whole test, so a `migrate()` that asked for it would
        # raise after 250 ms rather than return. The clock below is a second
        # opinion and its bound is loose on purpose - a tight one would turn a
        # busy machine into a red suite, and it would be measuring the machine.
        start = time.perf_counter()
        self.assertEqual(migrations.migrate(), self.highest())
        elapsed = time.perf_counter() - start
        self.assertLess(
            elapsed,
            2.0,
            "migrate() waited for the write lock on a database that was "
            "already up to date",
        )

    def test_migration_four_is_not_idempotent(self):
        """The statement that makes the lock load-bearing, named.

        Every other migration in the tree is `CREATE TABLE IF NOT EXISTS` and
        would survive being applied twice. Migration 4 is not: SQLite has no
        `ADD COLUMN IF NOT EXISTS`, so `ALTER TABLE threads ADD COLUMN
        project_id` is an error the second time. Anyone tempted to conclude the
        write lock is defensive tidying should fail this test first.
        """
        self.fresh()
        self.assertEqual(migrations.migrate(), self.highest())

        sql = dict(migrations.MIGRATIONS)[4]
        self.assertIn("ALTER TABLE threads ADD COLUMN project_id", sql)

        connection = sqlite3.connect(db.DB_PATH)
        self.addCleanup(connection.close)
        with self.assertRaises(sqlite3.OperationalError) as raised:
            for statement in migrations._statements(sql):
                connection.execute(statement)
        self.assertIn("duplicate column name: project_id", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
