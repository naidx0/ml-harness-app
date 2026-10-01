"""1 - the four tables `db.init_db()` used to create by hand.

`runs`, `metrics` and `hardware_profile` came from the `executescript` block in
`init_db`; `harness_instance` came from `db._INSTANCE_SCHEMA`. All four are
copied here verbatim, `IF NOT EXISTS` and `CHECK (id = 1)` included, so that a
database written before this package existed applies migration 1 as a no-op and
lands in exactly the same shape as a fresh one.

`harness_instance` is not optional and is not decoration. It is what stops two
databases both minting job 1 from writing to the same log file - the defect
fixed at `b024da4`. The *table* is created here; the *row* is still minted by
`db.get_instance()`, which `init_db` calls immediately afterwards. Those are two
different things and dropping either reopens the bug.

SHIPPED. Never edit this file. A correction is a new migration.
"""

VERSION = 1

SQL = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    params_json TEXT NOT NULL DEFAULT '{}',
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    step INTEGER NOT NULL,
    name TEXT NOT NULL,
    value REAL NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(run_id, step, name)
);
CREATE TABLE IF NOT EXISTS hardware_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gpu_name TEXT NOT NULL,
    vram_gb REAL NOT NULL,
    ram_gb REAL NOT NULL,
    os TEXT NOT NULL,
    disk_free_gb REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS harness_instance (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    instance_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""
