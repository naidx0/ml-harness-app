"""Numbered migrations, applied in order, once, inside a transaction.

Before this package there was no schema layer - there was a habit. `init_db`
created four tables; `ensure_intake_table`, `ensure_jobs_table`,
`ensure_models_table` and `ensure_datasets_table` created four more on first
use; `app/events.py` and `app/providers/store.py` created four more the same
way. Twelve tables, no version, no order, and existence decided by whichever
reader happened to run first.

That is not a tidiness complaint. Two defects in this repository were that
shape and both are in the git log: `list_jobs` shipped without its
`ensure_jobs_table()` call and returned "no such table" the first time a page
listed an empty queue, and `harness_instance` did not exist until something
happened to ask for an identity. A table whose existence is a race can be
missing; a schema with no version cannot be *changed* at all, because there is
nowhere to record that the change happened.

## The rules this runner enforces, and why each one is here

**Ordered, contiguous, starting at 1.** `MIGRATIONS` is checked before the
database is even opened. A gap (`1, 2, 4`), a repeat, or a list out of order is
a `MigrationError` and *nothing is applied* - not the migrations before the
gap, not the ones after it. Half-applying a schema and recording that you did
is the failure this whole file exists to make impossible.

**Idempotent.** `migrate()` is safe to call on every request if you like. It
applies what is missing and returns the version it left the database at. The
test that matters is the one that calls it twice and asserts the second call
adds no row: a runner that re-applies is worse than none, because it will run
somebody's data migration a second time.

**Safe when two processes call it at the same moment.** That sentence above
used to be true only for one process at a time, which on this product is the
wrong number: the engine, the runner and a test can all open the database
inside the same second, and `init_db()` is the first thing each of them does.
Measured before the fix, four processes calling `init_db()` on a fresh
database killed at least one of themselves in 13 of 40 trials - and the
survivor's database was always correct, so the only symptom was a process
that died at startup quoting a version the database was not at. See "The
race, and why the write lock is taken before the version is read" below.

**Transactional, per migration.** Each migration's statements and the
`schema_version` row that records it are committed together or not at all. This
is why the statements are executed one at a time rather than with
`executescript`: `sqlite3.Connection.executescript` issues an implicit `COMMIT`
before it runs, which would commit the DDL and leave the version row outside
the transaction - exactly the window in which a crash produces a database that
has the tables and does not know it.

**Loud on a mismatch.** A database at version 7 opened by a build that only
knows 4 was written by a newer version of this program; downgrading it silently
would corrupt it. A `schema_version` table with a hole in it (1, 2, 4 recorded)
means an earlier run half-applied something before this rule existed. Both
raise rather than guess.

## The race, and why the write lock is taken before the version is read

The version read and the decision it feeds used to sit outside any write
lock, and `_apply` opened its transaction with a bare `BEGIN`, which is
`BEGIN DEFERRED`. Two processes therefore both read "the database is at 0",
both concluded migration 1 was owed, and the loser re-ran it: `INSERT INTO
schema_version (version) VALUES (1)` against a row another process had just
committed is `UNIQUE constraint failed`, and migration 4's `ALTER TABLE
threads ADD COLUMN project_id` - the one statement here that cannot be
written `IF NOT EXISTS` - is `duplicate column name: project_id`. The data
was never damaged, because each migration was still atomic. A process died
at startup, and it died quoting `version - 1`, which is arithmetic rather
than a reading: the process that lost the race for migration 1 announced
"the database is still at version 0" about a file that was at 4.

Three fixes were available and the chosen one is both of the sound two:

*The lock is taken up front, with `BEGIN IMMEDIATE`.* `BEGIN DEFERRED` takes
no lock at all, so the transaction's first write has to upgrade a `SHARED`
lock to `RESERVED` - and that upgrade is the one case where SQLite returns
`SQLITE_BUSY` **without** calling the busy handler, because waiting could
deadlock two processes each trying to upgrade. A deferred writer therefore
does not queue, it dies. `BEGIN IMMEDIATE` asks for `RESERVED` before it
holds anything, so the busy handler runs and the second process waits its
turn.

*The version is then read again, inside that lock, and a migration another
process already applied is a no-op.* `BEGIN IMMEDIATE` on its own would not
have been enough: both processes had already decided what was owed before
either asked for the lock, so the loser would still have re-applied
migration 4 and still have died on `duplicate column name`. A decision made
outside the lock is a guess. `_apply` therefore re-reads `schema_version`
after it holds the write lock and returns the version it actually found,
which is why it returns an `int` rather than `None` - the caller's loop uses
it to skip everything the winner ran ahead and did.

*An advisory lock - a lock file, or `PRAGMA locking_mode = EXCLUSIVE` - was
rejected.* It is a second mutual-exclusion mechanism standing beside the one
SQLite already has and gets right, and its failure mode is the bad one: a
process killed while holding a lock file leaves a file a later process
cannot tell from a live claim, so the recovery is a human deleting something.
SQLite's locks are held by an open file handle, and the operating system
drops them when the process dies. That is the whole reason `kill -9` in the
middle of a migration is a recoverable event here: the journal rolls back and
the next process re-applies. A lock file would have taken that away.

The unlocked read at the top of `migrate()` stays, and it is not the bug
coming back. `migrate()` has seven call sites - `db.init_db`, five `ensure_*`
helpers in `app/db.py` and `events.ensure_tables` - which between them run at
the top of nearly every request, against a database that is already up to date
essentially always. Taking a write lock to discover that would serialise the
whole engine behind the migration runner. That read decides only *whether there
is anything to do*; it never decides *what to apply*. Every apply re-decides
under the lock.

**A failure message reports a version it read, never one it computed.** The
old message said `version - 1`. `_where_the_database_is` runs a `SELECT`
after the rollback and reports what is there, and when even that read fails
it says so rather than naming a number. A message that misreports the
version sends whoever reads it hunting the wrong thing, which is the more
expensive half of this defect: the crash costs a restart, the wrong number
costs an afternoon.

**A migration that has shipped is never edited.** That is why each one is its
own file with its version in its name: an edit to a shipped migration is a
visible change to a file whose name says it is frozen, rather than a line
inside a list. A correction is a new file with a new number. The first person
to "just fix" a shipped migration in place will corrupt every database that has
already applied it, and will not find out for a week.

## Deviations from `docs/ROADMAP.md` step 1.1, stated rather than hidden

The step says `app/migrations.py` with EXACTLY TWO module-level names. This is
a package (the brief that commissioned the work asked for one), so the
per-migration modules are also names on it, and there is a third public name:
`MigrationError`. A runner asked to be "loud on a gap or a mismatch" needs
something to be loud *with*, and a named error is the house style here -
`conductor.ConductorError`, `security.Denied`. It subclasses `RuntimeError` so
nothing that already catches broadly changes behaviour.

`schema_version` carries `applied_at` as well as `version`, because
`docs/ARCHITECTURE.md` §5.1 specifies the table as
`schema_version(version INTEGER PRIMARY KEY, applied_at)`. It has a default, so
the insert is still the bare `INSERT INTO schema_version(version) VALUES (?)`
the step names.
"""

from __future__ import annotations

import sqlite3
from typing import Iterator

from . import v001_initial
from . import v002_lazy_tables
from . import v003_projects
from . import v004_threads_belong_to_a_project
from . import v005_storms
from . import v006_machine_scope_is_declared_not_assumed
from . import v007_a_thread_id_names_a_conversation
from . import v008_an_eval_keeps_its_rows
from . import v009_a_prompt_is_a_version
from . import v010_a_retriever_can_be_scored_alone
from . import v011_a_thread_names_its_ledger
from . import v012_an_agent_run_keeps_its_cases
from . import v013_a_thread_keeps_its_goal
from . import v014_a_person_s_reading_of_a_row_is_kept
from . import v015_a_thread_may_run_unattended
from . import v016_a_thread_plans_before_it_builds
from . import v017_a_thread_has_a_permission_ladder
from . import v018_remote_control_links
from . import v019_a_thread_has_a_secondary_todo
from . import v020_thread_baseline_provider
from . import v021_a_thread_names_its_baseline_target


class MigrationError(RuntimeError):
    """The schema is not in a state this build is willing to guess about."""


_MODULES = (
    v001_initial,
    v002_lazy_tables,
    v003_projects,
    v004_threads_belong_to_a_project,
    v005_storms,
    v006_machine_scope_is_declared_not_assumed,
    v007_a_thread_id_names_a_conversation,
    v008_an_eval_keeps_its_rows,
    v009_a_prompt_is_a_version,
    v010_a_retriever_can_be_scored_alone,
    v011_a_thread_names_its_ledger,
    v012_an_agent_run_keeps_its_cases,
    v013_a_thread_keeps_its_goal,
    v014_a_person_s_reading_of_a_row_is_kept,
    v015_a_thread_may_run_unattended,
    v016_a_thread_plans_before_it_builds,
    v017_a_thread_has_a_permission_ladder,
    v018_remote_control_links,
    v019_a_thread_has_a_secondary_todo,
    v020_thread_baseline_provider,
    v021_a_thread_names_its_baseline_target,
)

#: `(version, sql)` in ascending order. One entry per shipped migration.
MIGRATIONS: list[tuple[int, str]] = [
    (module.VERSION, module.SQL) for module in _MODULES
]


#: The table this runner keeps its own state in. Created inside the same
#: transaction as the first migration, so a database either has the table and
#: the row that says migration 1 ran, or neither.
_SCHEMA_VERSION = (
    "CREATE TABLE IF NOT EXISTS schema_version ("
    "version INTEGER PRIMARY KEY, "
    "applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
)

#: How long a process waits for another process's migration before it gives up,
#: in milliseconds.
#:
#: The number has to be larger than the longest a migration can hold the write
#: lock, times the number of processes that can queue behind it. Applying all
#: four migrations to a fresh database is 7.1-7.7 ms measured over five runs on
#: the machine this was written on, and a `migrate()` that finds nothing to do
#: - the case on every request after the first - takes 0.37-0.46 ms and never
#: asks for the lock at all. The queue this has to survive is therefore
#: milliseconds long. 30 seconds is not a tuned figure; it is three orders of
#: magnitude of headroom for a filesystem that stalls, which on this repository
#: is a real possibility, because it lives inside a OneDrive folder.
#:
#: It is not infinite on purpose. A process that waits forever for a lock a
#: dead process will never release looks exactly like a hang, and the timeout
#: is what turns that into a sentence naming the database and the version.
#:
#: SQLite's default is 0 - fail on first contention. Python's `sqlite3` sets
#: 5000 ms from its own `timeout` argument; this overrides it explicitly rather
#: than inheriting a default from two layers down, because the correct value
#: here is a property of the migrations, not of the driver.
BUSY_TIMEOUT_MS = 30_000


def migrate() -> int:
    """Bring the database at `db.DB_PATH` up to date. Returns its version.

    Safe to call concurrently from as many processes as you like, which on this
    product is the operating condition rather than an edge case: the engine,
    the job runner and a test suite can each call `db.init_db()` within the
    same second. See the module docstring for what that costs and why the write
    lock is taken before the version is read.

    Imported inside the function on purpose: `db.init_db()` calls `migrate()`,
    so a module-level `from app import db` here is a circular import.
    """
    from app.db import session

    _check_the_list(MIGRATIONS)
    with session() as connection:
        connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        # Unlocked, and only ever used to answer "is there anything to do".
        # Nothing is applied on the strength of it; `_apply` reads the version
        # again under the write lock and that reading is the one that decides.
        current = _check_the_database(_applied(connection))
        for version, sql in MIGRATIONS:
            if version <= current:
                continue
            current = _apply(connection, version, sql)
    return current


def _applied(connection: sqlite3.Connection) -> list[int]:
    """The versions recorded in `schema_version`, ascending. `[]` if there is no
    such table yet - which is the same answer as an empty one, and asking
    `sqlite_master` first keeps the read side free of writes so a database that
    is already up to date never takes a lock to find that out.
    """
    present = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' "
        "AND name = 'schema_version'"
    ).fetchone()
    if present is None:
        return []
    return [
        int(row[0])
        for row in connection.execute(
            "SELECT version FROM schema_version ORDER BY version"
        )
    ]


def _check_the_list(migrations: list[tuple[int, str]]) -> None:
    """`MIGRATIONS` must be `1..N`, ascending, no gaps, no repeats.

    Runs before the database is opened, so a bad list applies nothing at all.
    """
    versions = [version for version, _ in migrations]
    expected = list(range(1, len(versions) + 1))
    if versions != expected:
        raise MigrationError(
            "MIGRATIONS must be consecutive integers starting at 1, in "
            f"ascending order; got {versions} and expected {expected}. "
            "Nothing has been applied - fix the list, do not renumber a "
            "migration that has already shipped."
        )


def _check_the_database(applied: list[int]) -> int:
    """The version the database is at, or a `MigrationError` saying why not."""
    if not applied:
        return 0
    highest = applied[-1]
    known = MIGRATIONS[-1][0] if MIGRATIONS else 0
    # Checked before the contiguity rule below, and the order matters: a
    # database written by a newer build is contiguous *by that build's list*,
    # so measuring it against this one's would report a hole and name the wrong
    # problem. "You are older than this file" is the useful answer.
    if highest > known:
        raise MigrationError(
            f"the database is at schema version {highest} and this build only "
            f"knows {known}. It was written by a newer version of ML Harness. "
            "Refusing to open it rather than writing an older shape into it."
        )
    if applied != list(range(1, highest + 1)):
        missing = sorted(set(range(1, highest + 1)) - set(applied))
        raise MigrationError(
            f"schema_version records {applied} - {missing} never ran. This "
            "database was half-migrated by something that is not this runner; "
            "it is not safe to continue on top of it."
        )
    return highest


def _apply(connection: sqlite3.Connection, version: int, sql: str) -> int:
    """One migration and its version row, committed together or not at all.

    Returns the version the database is at afterwards, which is not always
    `version`. Everything inside the transaction below happens while this
    process holds the write lock, including the read that decides whether there
    is anything to do - so if another process applied this migration, and
    perhaps the three after it, while this one was queueing for the lock, the
    honest answer is that number and not `version`. `migrate()`'s loop uses the
    return value to skip what the winner already did.

    `BEGIN IMMEDIATE`, not `BEGIN`. A deferred transaction takes no lock until
    its first write, and that write has to upgrade `SHARED` to `RESERVED` -
    the one contention case SQLite reports as `SQLITE_BUSY` immediately,
    without consulting the busy handler, because two processes both waiting to
    upgrade would deadlock. Deferred writers do not queue; they die.
    """
    _take_the_write_lock(connection, version)

    # Deciding, under the lock. Separate from the applying below so that
    # `_check_the_database` refusing a database from the future, or one with a
    # hole in `schema_version`, comes out saying exactly that. Those sentences
    # are about the database, not about this migration, and wrapping them in
    # "migration N failed and was rolled back" would bury the useful half.
    try:
        connection.execute(_SCHEMA_VERSION)
        current = _check_the_database(_applied(connection))
    except BaseException:
        _rollback(connection)
        raise

    if version <= current:
        # Another process applied this while we waited for the lock. Nothing
        # has been written in this transaction - the `CREATE TABLE IF NOT
        # EXISTS` above found the table already there, because a version was
        # read out of it - so there is nothing to commit.
        connection.execute("ROLLBACK")
        return current

    # Applying.
    try:
        for statement in _statements(sql):
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_version (version) VALUES (?)", (version,)
        )
    except Exception as error:  # noqa: BLE001 - re-raised, never swallowed
        _rollback(connection)
        raise MigrationError(
            f"migration {version} failed and was rolled back; the database is "
            f"{_where_the_database_is(connection)}: {error}"
        ) from error
    connection.execute("COMMIT")
    return version


def _take_the_write_lock(connection: sqlite3.Connection, version: int) -> None:
    """`BEGIN IMMEDIATE`, or a `MigrationError` that says who is holding it."""
    try:
        connection.execute("BEGIN IMMEDIATE")
    except sqlite3.Error as error:
        raise MigrationError(
            f"waited {BUSY_TIMEOUT_MS} ms for the write lock to apply "
            f"migration {version} and did not get it; another process is "
            f"migrating this database and has not finished, or died holding "
            f"the lock. Nothing was applied by this process and the database "
            f"is {_where_the_database_is(connection)}: {error}"
        ) from error


def _rollback(connection: sqlite3.Connection) -> None:
    """Undo the transaction if one is still open.

    Guarded, because some failures - a full disk, an I/O error - roll the
    transaction back themselves, and an unguarded `ROLLBACK` would then raise
    "cannot rollback - no transaction is active" *from the except block* and
    replace the real cause with a second, useless error.
    """
    if connection.in_transaction:
        connection.execute("ROLLBACK")


def _where_the_database_is(connection: sqlite3.Connection) -> str:
    """A true clause about the database's version, for a failure message.

    Read, not computed. This used to be `f"still at version {version - 1}"`,
    which is arithmetic on an assumption: it is right only if this process is
    the only one that has touched the file. It was wrong exactly when it
    mattered, in the race this module now serialises - a process that lost the
    race for migration 1 died saying "the database is still at version 0" about
    a file that was at 4, and the person reading that went looking for an
    unmigrated database that did not exist.

    Call it after the rollback, so it reports the state the caller will find.
    If the read itself fails there is no number to report and it says that,
    because a message inventing one would be the same defect again.
    """
    try:
        applied = _applied(connection)
    except sqlite3.Error as error:
        return f"at a version this process could not read back ({error})"
    if not applied:
        return "at version 0, with no migration recorded"
    return f"at version {applied[-1]}"


def _statements(sql: str) -> Iterator[str]:
    """Split a migration into statements without breaking on a `;` in a string.

    `sqlite3.complete_statement` is the stdlib's own answer to "is this whole
    yet", and it knows about quoted strings and comments, which `sql.split(";")`
    does not. It does not understand a trigger body's `BEGIN ... END;`; no
    migration here defines one, and the migration that first does gets its own
    answer rather than a splitter that is quietly wrong.
    """
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            buffer = ""
            if statement.strip(";").strip():
                yield statement
    trailing = buffer.strip()
    if trailing:
        raise MigrationError(
            f"migration ends with an unterminated statement: {trailing!r}"
        )
