"""2 - the four tables that used to be created by whoever read them first.

`intake`, `jobs`, `models` and `datasets` were each created by an
`ensure_*_table()` helper called from the top of every reader that touched
them. Those helpers stay - seven call sites in `app/db.py` and several tests
call them by name - but they no longer own the schema. Their bodies now run
this runner instead.

The columns are exactly those of `db.ensure_intake_table`, `db._JOBS_SCHEMA`,
`db.ensure_models_table` and `db.ensure_datasets_table` as they stood at
`88388d3`, so an existing database applies this as a no-op. `models` and
`datasets` were single-line `CREATE` statements there and are broken across
lines here; nothing about the columns, their types or their defaults changed,
and `tests/test_migrations_fold_lazy_tables.py` compares the resulting
`PRAGMA table_info` against the old helpers' output rather than taking that on
trust.

Note what is deliberately *not* here: the pre-`JobSpec` rescue that renames a
legacy `jobs` table with a `cmd TEXT NOT NULL` column and moves the shell
command into `config_json` as inert data. That is a conditional data migration
- it fires only when the old column is present - and SQL has no branch. It
stays in `db.ensure_jobs_table()`, which now runs this migration first and then
checks for the legacy column. Deleting it to make this file's story tidier
would revert a shipped security fix.

SHIPPED. Never edit this file. A correction is a new migration.
"""

VERSION = 2

SQL = """
CREATE TABLE IF NOT EXISTS intake (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    answers TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
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
CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    base TEXT,
    quant TEXT,
    method TEXT,
    path TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    rows INTEGER,
    format TEXT,
    split TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""
