from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from app import paths

#: THE DATABASE. `ML_HARNESS_DB` still wins and always has - a person or a test
#: that named a path said something more specific than anything below.
#: `app/paths.py` decides the rest, and its rule is that A CHECKOUT KEEPS ITS
#: OWN FILE WHERE IT IS: this used to resolve `parents[1]`, which in a wheel is
#: `site-packages`, so an installed engine wrote its database into somebody's
#: Python installation. Moving it unconditionally would have orphaned the
#: database of every person who already has one, which is why the checkout
#: branch exists rather than a migration nobody asked for.
DB_PATH = Path(os.environ.get("ML_HARNESS_DB") or paths.in_data_root("ml_harness.db"))


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def session():
    connection = connect()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_db() -> None:
    """Bring the database up to the current schema, then mint its identity.

    The `executescript` block that used to be here is `MIGRATIONS[0]`. Schema
    lives in exactly one place now - `app/migrations/` - and this function's
    job is to run it, not to know what it says.

    Two calls follow it, and neither is schema.

    `ensure_jobs_table()` is here for the one thing a numbered migration cannot
    express: the pre-`JobSpec` rescue fires only when a legacy `cmd` column is
    present, and SQL has no branch. Running it at open means a database written
    before the structured job contract is repaired when the engine starts it,
    rather than the first time somebody loads the jobs page.

    `get_instance()` stays, and stays last. Creating the `harness_instance`
    *table* is migration 1's job; minting the *row* is this one's, so that a
    database has its uuid from the moment it exists rather than at the first
    call that happens to need a path. Those are two different things, and
    dropping the second reopens the job-log collision fixed at `b024da4`.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    from app import migrations

    migrations.migrate()
    ensure_jobs_table()
    get_instance()


_INSTANCE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS harness_instance (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        instance_id TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
"""


def get_instance() -> dict[str, Any]:
    """This database's identity. Minted once, then permanent.

    A job id is not an identity. It is a counter, and `AUTOINCREMENT` restarts
    it at 1 for every fresh database - so "job 1" names a different job in
    every database that has ever existed on this machine, including the one the
    user got by deleting `ml_harness.db` and starting over. Anything keyed on
    the job id alone is keyed on a name that repeats, which is exactly how two
    unrelated runs came to share a log file and a run directory. The artifact
    paths are keyed on this instead (`jobspec.current_instance`).

    `INSERT OR IGNORE` against a fixed primary key is what makes minting both
    idempotent and safe when two processes do it at the same moment: the second
    insert loses on the key and the reader below returns the winner's value, so
    a database can never end up with two identities.

    Self-healing on purpose, the same way `get_intake` ensures its table before
    reading it. A database written before this table existed gets an identity
    the first time one is asked for, so there is no migration step for somebody
    to forget.

    Returns the row rather than the bare string because that is what every
    other reader in this file returns, and because `created_at` answers "when
    was this database born", which is the other thing an identity is good for.
    `jobspec.current_instance()` is the accessor for the string itself.
    """
    with session() as connection:
        connection.execute(_INSTANCE_SCHEMA)
        connection.execute(
            "INSERT OR IGNORE INTO harness_instance (id, instance_id) "
            "VALUES (1, ?)",
            (uuid.uuid4().hex,),
        )
        row = connection.execute(
            "SELECT * FROM harness_instance WHERE id = 1"
        ).fetchone()
    return dict(row)


def create_run(name: str, params_json: str) -> dict[str, Any]:
    with session() as connection:
        cursor = connection.execute(
            "INSERT INTO runs(name, params_json) VALUES (?, ?)", (name, params_json)
        )
        row = connection.execute("SELECT * FROM runs WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def list_runs() -> list[dict[str, Any]]:
    with session() as connection:
        rows = connection.execute("SELECT * FROM runs ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


def add_metric(run_id: int, step: int, name: str, value: float) -> dict[str, Any] | None:
    with session() as connection:
        exists = connection.execute("SELECT 1 FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not exists:
            return None
        connection.execute(
            """INSERT INTO metrics(run_id, step, name, value) VALUES (?, ?, ?, ?)
               ON CONFLICT(run_id, step, name) DO UPDATE SET value = excluded.value,
               recorded_at = CURRENT_TIMESTAMP""",
            (run_id, step, name, value),
        )
        row = connection.execute(
            "SELECT * FROM metrics WHERE run_id = ? AND step = ? AND name = ?",
            (run_id, step, name),
        ).fetchone()
    return dict(row)


def metrics_for(run_id: int, name: str | None = None) -> list[dict[str, Any]]:
    with session() as connection:
        if name is None:
            rows = connection.execute(
                "SELECT * FROM metrics WHERE run_id = ? ORDER BY step, name", (run_id,)
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM metrics WHERE run_id = ? AND name = ? ORDER BY step",
                (run_id, name),
            ).fetchall()
    return [dict(row) for row in rows]


def complete_run(run_id: int) -> dict[str, Any] | None:
    with session() as connection:
        connection.execute(
            "UPDATE runs SET status = 'completed', finished_at = CURRENT_TIMESTAMP WHERE id = ?",
            (run_id,),
        )
        row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def create_hardware_profile(
    gpu_name: str, vram_gb: float, ram_gb: float, os: str, disk_free_gb: float
) -> dict[str, Any]:
    with session() as connection:
        cursor = connection.execute(
            """INSERT INTO hardware_profile(gpu_name, vram_gb, ram_gb, os, disk_free_gb)
               VALUES (?, ?, ?, ?, ?)""",
            (gpu_name, vram_gb, ram_gb, os, disk_free_gb),
        )
        row = connection.execute("SELECT * FROM hardware_profile ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row)


def get_latest_hardware_profile() -> dict[str, Any] | None:
    with session() as connection:
        row = connection.execute(
            "SELECT * FROM hardware_profile ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def list_hardware_profiles() -> list[dict[str, Any]]:
    with session() as connection:
        rows = connection.execute("SELECT * FROM hardware_profile ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


def ensure_intake_table() -> None:
    """Bring the schema up to date. The intake table is migration 2's.

    This used to hold its own `CREATE TABLE IF NOT EXISTS`, called from the top
    of every reader that touched the table. The function stays - seven call
    sites in this file and several tests name it - but it no longer owns any
    schema. See `app/migrations/v002_lazy_tables.py`.
    """
    from app import migrations

    migrations.migrate()


def create_intake(session_id: str, answers: dict[str, Any]) -> dict[str, Any]:
    ensure_intake_table()
    with session() as connection:
        connection.execute(
            "INSERT INTO intake(session_id, answers) VALUES (?, ?)",
            (session_id, json.dumps(answers)),
        )
        row = connection.execute(
            "SELECT * FROM intake WHERE session_id = ? ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
    out = dict(row)
    out["answers"] = json.loads(out["answers"])
    return out


def get_intake(session_id: str) -> dict[str, Any] | None:
    ensure_intake_table()
    with session() as connection:
        row = connection.execute(
            "SELECT * FROM intake WHERE session_id = ? ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
    if row is None:
        return None
    out = dict(row)
    out["answers"] = json.loads(out["answers"])
    return out




def create_job(intake_id: str, spec: Any) -> dict[str, Any]:
    """Queue a job from a validated `JobSpec`.

    This used to take a command string, which the runner handed to the system
    shell. It takes a structured spec now and the column that held the string
    is gone, so there is no longer a place in the schema for a command to be
    stored even by accident. See `app/jobspec.py`.
    """
    ensure_jobs_table()
    config_json = json.dumps(spec.config, sort_keys=True)
    with session() as connection:
        cursor = connection.execute(
            "INSERT INTO jobs (intake_id, recipe, kind, config_json) "
            "VALUES (?, ?, ?, ?)",
            (intake_id, spec.recipe, spec.kind, config_json),
        )
        row = connection.execute("SELECT * FROM jobs WHERE id = ?", (cursor.lastrowid,)).fetchone()
    out = dict(row)
    return out


def get_job(job_id: int) -> dict[str, Any] | None:
    ensure_jobs_table()
    with session() as connection:
        row = connection.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
    if row is None:
        return None
    out = dict(row)
    return out


#: Only the pre-`JobSpec` rescue below still executes this - it renames the
#: legacy table and needs somewhere to copy the rows to. The schema of record
#: is `app/migrations/v002_lazy_tables.py`.
_JOBS_SCHEMA = """
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        intake_id TEXT NOT NULL,
        recipe TEXT NOT NULL,
        kind TEXT NOT NULL,
        config_json TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'queued',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        finished_at TEXT,
        exit_code INTEGER,
        log_path TEXT
    );
"""


def ensure_jobs_table() -> None:
    """Run the migrations, then rescue a pre-`JobSpec` jobs table if one is here.

    The `CREATE TABLE` is migration 2's now. What is left here is the half that
    a numbered migration cannot express: a database written before the
    structured job contract has a `cmd TEXT NOT NULL` column holding a shell
    command string, and whether to act depends on whether that column is
    present. SQL has no branch, so the check stays in Python.

    Those rows are kept - they are the user's history and deleting someone's
    data to tidy a schema is not our call - but they are moved into a shape
    that cannot execute: the recipe is recorded as `legacy-command`, which is
    not a directory under `recipes/`, so `jobspec.load_recipe` refuses it and
    the runner records the refusal. The old command survives as *data* inside
    `config_json`, where nothing reads it as an instruction.

    This is why this function's body is not the two lines the other three
    `ensure_*` helpers now have. Making it match them would delete a shipped
    security fix, and `tests/test_migrations_fold_lazy_tables.py` builds a
    legacy database to prove it still fires.
    """
    from app import migrations

    migrations.migrate()
    with session() as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(jobs)")
        }
        if columns and "cmd" in columns:
            connection.execute("ALTER TABLE jobs RENAME TO jobs_pre_jobspec")
            connection.execute(_JOBS_SCHEMA)
            connection.execute(
                """
                INSERT INTO jobs (
                    id, intake_id, recipe, kind, config_json,
                    status, created_at, finished_at, exit_code, log_path
                )
                SELECT
                    id, intake_id, 'legacy-command', 'train',
                    json_object('legacy_cmd', cmd),
                    status, created_at, finished_at, exit_code, log_path
                FROM jobs_pre_jobspec
                """
            )
            connection.execute("DROP TABLE jobs_pre_jobspec")


def next_queued_job() -> dict[str, Any] | None:
    """Claim the oldest queued job, atomically, and return it. None if empty.

    IT USED TO BE A SELECT, AND THAT WAS A DECLARED RACE - the only one this
    repository had counted, `next_queued_job_does_not_claim` in
    `tests/test_two_callers_at_once.py`. Two supervisors arriving together
    were handed the same row and would have run one training job twice: same
    subprocess tree, same run directory, two sets of metrics for one run.
    `training._SLOT` is a `threading.Lock` and covers one process; two engines
    on one database were never covered by anything.

    The claim is one statement, so there is no window between reading and
    marking for a second caller to arrive in. SQLite's `RETURNING` (3.35+;
    this venv runs 3.53.1) hands back the row the UPDATE actually took, which
    is the only row the caller may have - reading it back with a second SELECT
    would reopen the same race one line lower down.

    Same omission as list_jobs had, and hidden the same way: the generated
    test created a job before asking for the next queued one.

    WHAT A CLAIM COSTS, SAID PLAINLY. A supervisor that dies between claiming
    and finishing leaves its row `running` and no reaper collects it, so that
    job is skipped rather than retried. Before the claim it stayed `queued`
    and was handed out again forever - which `app/runner.py`'s own comment
    records as having JAMMED the single slot behind a row that could never
    succeed. Skipping one job is the better failure of the two, and neither
    is a substitute for a reaper; there is no queue row for one yet.
    """
    ensure_jobs_table()
    with session() as connection:
        row = connection.execute(
            "UPDATE jobs SET status = 'running' "
            "WHERE id = (SELECT id FROM jobs WHERE status = 'queued' "
            "            ORDER BY id ASC LIMIT 1) "
            "RETURNING *"
        ).fetchone()
        return dict(row) if row else None


def finish_job(job_id: int, exit_code: int, log_path: str) -> dict[str, Any]:
    with session() as connection:
        connection.execute(
            "UPDATE jobs SET status = 'done', finished_at = CURRENT_TIMESTAMP, exit_code = ?, log_path = ? WHERE id = ?",
            (exit_code, log_path, job_id),
        )
        row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row)


def list_jobs() -> list[dict[str, Any]]:
    # Without this, listing on a fresh database raises "no such table: jobs".
    # The generated acceptance test created two jobs first, which built the
    # table as a side effect and hid the omission until a page listed an
    # empty queue.
    ensure_jobs_table()
    with session() as connection:
        rows = connection.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


def ensure_models_table():
    """Bring the schema up to date. The models table is migration 2's."""
    from app import migrations

    migrations.migrate()


def create_model(name: str, base: str, quant: str, method: str, path: str, notes: str) -> dict[str, Any]:
    ensure_models_table()
    with session() as connection:
        cursor = connection.execute(
            "INSERT INTO models(name, base, quant, method, path, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (name, base, quant, method, path, notes)
        )
        row = connection.execute("SELECT * FROM models WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def list_models() -> list[dict[str, Any]]:
    # Same omission as list_jobs. The spec said to call this first and
    # the generated code did not; its acceptance test created a row
    # before listing, so the table always existed by then.
    ensure_models_table()
    with session() as connection:
        rows = connection.execute("SELECT * FROM models ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


def ensure_datasets_table() -> None:
    """Bring the schema up to date. The datasets table is migration 2's."""
    from app import migrations

    migrations.migrate()


def create_dataset(path: str, rows: int, format: str, split: str, notes: str) -> dict[str, Any]:
    ensure_datasets_table()
    with session() as connection:
        cursor = connection.execute(
            "INSERT INTO datasets(path, rows, format, split, notes) VALUES (?, ?, ?, ?, ?)",
            (path, rows, format, split, notes)
        )
        row = connection.execute("SELECT * FROM datasets WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def list_datasets() -> list[dict[str, Any]]:
    # Same omission as list_jobs. The spec said to call this first and
    # the generated code did not; its acceptance test created a row
    # before listing, so the table always existed by then.
    ensure_datasets_table()
    with session() as connection:
        rows = connection.execute("SELECT * FROM datasets ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Projects - the top level of the model.
#
# `docs/ARCHITECTURE.md` makes a project the root: a goal, plus the machine,
# plus the things attached to it. A thread is one conversation inside a
# project; a run is one execution. The rail's top level is the project list,
# and the reason the rail is a flat list of threads today is that this table
# did not exist until migration 3.
#
# Every function here goes through `ensure_projects()` rather than assuming the
# table is there, matching what the rest of this file does, and `archived_at`
# is a nullable timestamp rather than a flag because "archived" and "archived
# on the 14th" are different facts and the second one is free.


#: The two products. `portal` is the only column that differs between them,
#: and they are two portals rather than a toggle - see `docs/VISION.md`.
PORTALS = ("consumer", "enterprise")


def ensure_projects() -> None:
    """Bring the schema up to date. The projects table is migration 3's."""
    from app import migrations

    migrations.migrate()


def create_project(
    name: str, root_path: str | None = None, portal: str = "consumer"
) -> dict[str, Any]:
    """Insert one project and return the row.

    `portal` is validated here rather than trusted, because it is the one
    column the enterprise product is distinguished by and a typo would produce
    a project that belongs to neither.
    """
    if portal not in PORTALS:
        raise ValueError(
            f"unknown portal {portal!r}; expected one of {', '.join(PORTALS)}"
        )
    ensure_projects()
    with session() as connection:
        cursor = connection.execute(
            "INSERT INTO projects (name, root_path, portal) VALUES (?, ?, ?)",
            (name, root_path, portal),
        )
        row = connection.execute(
            "SELECT * FROM projects WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


def list_projects(include_archived: bool = False) -> list[dict[str, Any]]:
    """Newest first, live only unless asked otherwise.

    Same ordering as `list_runs` and `events.list_threads`: a rail read
    oldest-first buries today's work.
    """
    ensure_projects()
    query = "SELECT * FROM projects"
    if not include_archived:
        query += " WHERE archived_at IS NULL"
    query += " ORDER BY id DESC"
    with session() as connection:
        rows = connection.execute(query).fetchall()
    return [dict(row) for row in rows]


def get_project(project_id: int) -> dict[str, Any] | None:
    ensure_projects()
    with session() as connection:
        row = connection.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    return dict(row) if row else None


def default_project() -> dict[str, Any]:
    """The lowest-id live project, creating one named `Default` if there is none.

    This exists so every later step can be project-scoped without the UI having
    to ship a project picker in this milestone. It always returns a dict.

    The insert and the read are one statement pair inside one transaction, and
    the insert is conditional in SQL rather than in Python, because a
    read-then-write would let two processes each decide the table was empty and
    each create a `Default`. Two projects called `Default` is not a cosmetic
    problem: every thread created after the race lands in a different one from
    every thread created before it.
    """
    ensure_projects()
    with session() as connection:
        connection.execute(
            "INSERT INTO projects (name) SELECT 'Default' "
            "WHERE NOT EXISTS (SELECT 1 FROM projects WHERE archived_at IS NULL)"
        )
        row = connection.execute(
            "SELECT * FROM projects WHERE archived_at IS NULL "
            "ORDER BY id ASC LIMIT 1"
        ).fetchone()
    return dict(row)


def rename_project(project_id: int, name: str) -> dict[str, Any] | None:
    """Rename one project. `None` when it does not exist, like `add_metric`."""
    ensure_projects()
    with session() as connection:
        exists = connection.execute(
            "SELECT 1 FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if exists is None:
            return None
        connection.execute(
            "UPDATE projects SET name = ? WHERE id = ?", (name, project_id)
        )
        row = connection.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    return dict(row)


def set_project_root(project_id: int, root_path: str) -> dict[str, Any] | None:
    """Point a project at a directory. `None` when it does not exist.

    THE WRITER THAT WAS MISSING, and its absence made a whole feature
    unreachable. `create_project` was the only code anywhere that ever wrote
    `root_path`, and `default_project()` - the project every thread lands in
    unless somebody says otherwise - inserts a name and nothing else. So on
    every fresh install `Default.root_path` was NULL, and all three
    standing-constraints tools refused with `no_root_path`. The frontend never
    sent a root either: `useThreads.ts` calls `createProject(name)` and drops
    the options argument. The path existed in the schema and in no reachable
    flow.

    **The value is stored verbatim, exactly as `create_project` stores it.**
    Not resolved, not normalised, not checked for existence - and that is a
    deliberate match rather than laziness. `tests/test_projects.py` pins
    `/tmp/x` round-tripping through `create_project`, and a writer that
    normalised where its sibling does not would mean the same project had two
    different roots depending on which function last touched it. The tools that
    READ it are where the checking belongs, and they already do it: they refuse
    `root_is_not_a_directory` with the path in the reply.

    `rename_project`'s shape, and for its reason: the existence check and the
    write are one transaction, so a project archived between them cannot
    produce a row that describes something that is no longer there.
    """
    ensure_projects()
    with session() as connection:
        exists = connection.execute(
            "SELECT 1 FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if exists is None:
            return None
        connection.execute(
            "UPDATE projects SET root_path = ? WHERE id = ?", (root_path, project_id)
        )
        row = connection.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    return dict(row)


def delete_project(project_id: int) -> dict[str, Any] | None:
    """Delete one project, its threads, and its memory. `None` when absent.

    The same refusal as `archive_project`, for the same reason: with no live
    project left `default_project()` would mint a fresh `Default` and the next
    thread would land somewhere nobody chose. Each thread goes through
    `events.delete_thread`, so the per-thread tables are cleaned the one way;
    then the project's own memory (`memory_entries`) and its ledger rows, then
    the row. Nothing on disk: the project's root folder is the person's.
    """
    from app import events as _events  # the two modules import each other lazily

    ensure_projects()
    with session() as connection:
        row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            return None
        if row["archived_at"] is None:
            live = connection.execute(
                "SELECT COUNT(*) FROM projects WHERE archived_at IS NULL"
            ).fetchone()[0]
            if live <= 1:
                raise ValueError("cannot delete the last project; create another one first")
        thread_ids = [
            r[0] for r in connection.execute("SELECT id FROM threads WHERE project_id = ?", (project_id,))
        ]
    threads = 0
    for thread_id in thread_ids:
        if _events.delete_thread(thread_id) is not None:
            threads += 1
    with session() as connection:
        have = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        memory = 0
        if "memory_entries" in have:
            memory = connection.execute(
                "DELETE FROM memory_entries WHERE project_id = ?", (project_id,)
            ).rowcount
        ledger = connection.execute("DELETE FROM events WHERE project_id = ?", (project_id,)).rowcount
        connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    return {"project": dict(row), "removed": {"threads": threads, "memory_entries": memory, "events": ledger}}


def archive_project(project_id: int) -> dict[str, Any] | None:
    """Archive one project. `None` when it does not exist.

    Refuses to archive the last live project. Not tidiness: `default_project()`
    mints a new `Default` when no live project remains, so archiving the last
    one would silently strand every thread in it behind a project the rail no
    longer shows, and put the next thread somewhere else again. Archiving is
    also not deletion - the threads inside keep pointing at it and
    `list_projects(include_archived=True)` still returns it.
    """
    ensure_projects()
    with session() as connection:
        row = connection.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if row is None:
            return None
        if row["archived_at"] is None:
            live = connection.execute(
                "SELECT COUNT(*) FROM projects WHERE archived_at IS NULL"
            ).fetchone()[0]
            if live <= 1:
                raise ValueError(
                    "cannot archive the last project; create another one first"
                )
        connection.execute(
            "UPDATE projects SET archived_at = CURRENT_TIMESTAMP WHERE id = ?",
            (project_id,),
        )
        row = connection.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    return dict(row)
