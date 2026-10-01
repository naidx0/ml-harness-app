"""3 - `projects`, the top level of the data model.

`docs/ARCHITECTURE.md` §5.1 makes a project the root: a goal, plus the machine,
plus the things attached to it. A thread is one conversation inside a project;
a run is one execution. The rail's top level *is* the project list, which is
why the rail is a flat list of threads today and Codex has folders.

`portal` is `consumer` or `enterprise` and is the only column that will ever
differ between the two products. `harness_md_path` is where M2's standing
context file lives; it is nullable and unused until then, and it is here rather
than in M2 because adding a column to a table is a migration and adding a
top-level foreign key across fifteen tables is a week.

**One column beyond the roadmap's DDL:** `archived_at`. Step 1.3 lists six
columns and does not include it, but the brief this migration was written for
asks for an archive endpoint, and archiving with nowhere to write is a claim.
It is a nullable timestamp rather than a boolean for the same reason
`providers.tool_calling` is TEXT: "archived" and "archived on the 14th" are
different facts and the second one is free. `threads` gets the same column in
migration 4, and `docs/ARCHITECTURE.md` already names `threads.archived_at`.

SHIPPED. Never edit this file. A correction is a new migration.
"""

VERSION = 3

SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    root_path TEXT,
    harness_md_path TEXT,
    portal TEXT NOT NULL DEFAULT 'consumer',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    archived_at TEXT
);
"""
