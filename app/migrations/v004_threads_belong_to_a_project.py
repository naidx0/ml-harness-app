"""4 - the transcript tables become versioned, and a thread gets a home.

Two jobs, and they are one migration because the second cannot be written
without the first.

**The fold.** `threads`, `messages` and `events` were created by
`app/events.py` with the same self-healing `CREATE TABLE IF NOT EXISTS` the
rest of the tree used, because the Conductor needed them before this runner
existed - `docs/ROADMAP.md` step 1.4 says so in as many words and lists the
fold as still owed. The statements below are the ones from `events._SCHEMA` as
it stood at `88388d3`, so an existing database applies them as a no-op, and
`events.ensure_tables()` now calls this runner instead of owning them.
`providers` is deliberately *not* folded here: nothing in this change needs it,
and a migration that rewrites a table for tidiness is a risk taken for no
reason. It is still owed and it is still one line of SQL when someone has a
reason to write it.

**The home.** `threads.project_id` is what makes the rail a tree instead of a
flat list. Three facts decide how existing threads get one:

1. SQLite cannot add a `NOT NULL` column to a populated table without a
   non-null default, and it refuses a `REFERENCES` clause on an added column
   unless the default is NULL. The choices are therefore a nullable column with
   a real foreign key, or a `NOT NULL DEFAULT 1` column with no foreign key and
   a hardcoded id. The first is chosen; the backfill below and
   `tests/test_projects.py` are what stop it becoming the nullable-forever
   column `docs/ROADMAP.md` warns about.
2. Rebuilding `threads` to get a true `NOT NULL` would mean dropping a table
   that holds the user's conversations while `messages` holds a foreign key
   into it. That is a real risk to real data in exchange for a constraint the
   application already enforces on every write.
3. The home itself is **one project named `Default`, created here**, and every
   thread that predates projects goes into it. Not one project per thread: a
   thread title is not a project name, and splitting four conversations into
   four folders the user never asked for is inventing structure. Not NULL: a
   nullable foreign key that nothing fills in is how "projects exist" becomes
   true in the schema and false in the product.

The `Default` row is created **only if there is at least one thread to put in
it**. A brand-new database gets no project from this migration - it gets one
from `db.default_project()` the first time anything needs one - so
`list_projects()` on an empty database still returns an empty list, which
`tests/test_empty_state_all_helpers.py` checks for every reader in `db`.

SHIPPED. Never edit this file. A correction is a new migration.
"""

VERSION = 4

SQL = """
CREATE TABLE IF NOT EXISTS threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    tool_calls_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id, id);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    thread_id INTEGER,
    run_id INTEGER,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    ts TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_events_thread ON events(thread_id, id);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, id);
CREATE INDEX IF NOT EXISTS idx_events_project ON events(project_id, id);
INSERT INTO projects (name)
    SELECT 'Default'
    WHERE EXISTS (SELECT 1 FROM threads)
      AND NOT EXISTS (SELECT 1 FROM projects);
ALTER TABLE threads ADD COLUMN project_id INTEGER REFERENCES projects(id);
ALTER TABLE threads ADD COLUMN archived_at TEXT;
UPDATE threads
    SET project_id = (SELECT MIN(id) FROM projects)
    WHERE project_id IS NULL;
"""
