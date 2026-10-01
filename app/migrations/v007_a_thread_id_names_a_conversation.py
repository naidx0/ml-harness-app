"""7 - the ledger's thread id becomes a reference to a real conversation.

## What was wrong

Migration 6 and wall 5 made a thread-scoped fact say WHICH conversation it
belongs to. Nothing checked that the id NAMED one. `evidence.record()` accepted
any integer, `fact_evidence.thread_id` had no foreign key, and the two siblings
of this table - `app/storm.py`'s `declare` ("there is no thread {id}") and
`app/events.py`'s `add_message` - had been checking their parent row all along.

The consequence is worse than an orphan row, because SQLite hands out rowids in
order from 1. A row filed against a conversation that does not exist YET is a row
the next conversation INHERITS. Reproduced end to end on an empty database
before this was written:

    record(eval_size_n = 120, MEASURED, thread_id=1)   # no threads exist
    POST /api/threads                                  # -> id 1
    -> the first conversation the user ever opens reads
       Fact(value=120, origin='MEASURED'), having been shown no file

    control thread: BLOCKED__BUILD_EVAL_SET, G0_EVAL_SET FAILED
    seeded  thread: TRAIN__LORA_SFT, all five gates PASSED

`0`, `-1` and `999999` were accepted the same way.

## What this migration does

Two things, in this order, and the order is forced.

**It quarantines every row that cannot satisfy the new constraint** - a row whose
`thread_id` is not NULL and names no row in `threads`, and a row whose
`thread_id` is zero or negative. This is migration 6's move, for migration 6's
reason: the measurement may well be real, what is missing is where it belongs,
and a migration cannot supply that without inventing the exact fact that is
absent. Nothing is deleted, nothing is edited, each row keeps its id, its value,
its origin, its actor, its tool, its `how` and its `created_at`, and gains one
sentence saying why it moved. `evidence.quarantine_view` and `GET /api/evidence`
show them.

**Then it rebuilds `fact_evidence`** with `thread_id INTEGER REFERENCES
threads(id)` and `CHECK (thread_id IS NULL OR thread_id > 0)`. SQLite cannot add
a constraint to an existing table, so this is the standard rebuild: create,
copy, drop, rename. Ids are copied explicitly, so the append-only ledger's
history survives.

## Why the last two statements write to `sqlite_sequence`

Because a rebuild silently un-does what `AUTOINCREMENT` is for, and the first
draft of this file did. `DROP TABLE` removes the table's `sqlite_sequence` row,
and copying the surviving rows back sets the counter to the highest id that
SURVIVED - so the ids of the rows this migration just quarantined, and the ids
migration 6 quarantined before it, are handed out again to new rows. Then a
ledger whose whole discipline is "nothing is ever updated and nothing is ever
deleted" has two different rows with id 37, one of them in `quarantined_facts`
whose primary key is that id, and the next quarantine of the reused one fails on
a collision. The counter is therefore set to the high-water mark across BOTH
tables, which is what it would have been had the rebuild never happened.
Verified: 5 rows in, 3 quarantined, the next row written gets id 6.

## Why the quarantine has to come first, which is the foreign key's real cost

`PRAGMA foreign_keys` is a no-op inside a transaction, and this runner executes
every migration inside one - deliberately, so that a migration and the
`schema_version` row that records it commit together. So enforcement cannot be
switched off for the rebuild, and `INSERT INTO ... SELECT` checks every row as it
goes: one orphan would abort migration 7 on somebody's real database and roll it
back. That constraint is not a defect in the runner. It is what a foreign key
costs, and it is the honest half of the trade the ledger is making here - the
store will now refuse a row no caller can talk it out of, and the price is that
the order rows may be written in is fixed and this file had to say what happens
to the rows already written.

## Why a foreign key AND a check in `record()`

Both, and `app/tools/evidence.py` argues it where the check lives. In one line:
the foreign key is the property no future caller can forget, and it cannot say a
sentence - `FOREIGN KEY constraint failed` names no argument, no fact and no
gate. The `CHECK` is there because a foreign key refuses `0` only because no
`threads` row happens to have that id, and "happens to" is not a rule.

## What this does to a database with nothing wrong with it

Nothing that shows. The quarantine `SELECT` matches no rows, and the rebuild
copies the table into an identically-shaped one with two constraints added.
Measured on a copy of the owner's real database: 47 evidence rows before, 47
after, 0 quarantined, every row byte-identical including its id, and
`PRAGMA foreign_key_check` clean.

SHIPPED. Never edit this file. A correction is a new migration.
"""

VERSION = 7

#: The reason, written into every row this moves. One sentence, in the row, so
#: somebody reading the table in six months does not have to find this file.
_BECAUSE = (
    "its thread_id named no conversation on this machine, so it was a row filed "
    "against a thread that did not exist - and ids are handed out in order from "
    "1, which means the next conversation to be opened would have inherited it. "
    "Moved rather than deleted: the measurement may have been real, only "
    "misfiled. See app/migrations/v007_a_thread_id_names_a_conversation.py."
)

#: SQL-quoted by doubling, for the reason migration 6 gives: an edit to the
#: sentence above must not be able to turn this into a syntax error - or into
#: something else - on somebody's real database.
_BECAUSE_SQL = _BECAUSE.replace("'", "''")

#: A row the rebuilt table could not hold. Written once and used twice, so the
#: rows that are copied out and the rows that are removed cannot drift apart.
_ORPHANED = (
    "thread_id IS NOT NULL AND ("
    "thread_id <= 0 OR NOT EXISTS ("
    "SELECT 1 FROM threads WHERE threads.id = fact_evidence.thread_id))"
)

SQL = f"""
CREATE TABLE IF NOT EXISTS quarantined_facts (
    id INTEGER PRIMARY KEY,
    thread_id INTEGER,
    fact TEXT NOT NULL,
    value TEXT NOT NULL,
    origin TEXT NOT NULL,
    actor TEXT NOT NULL,
    tool TEXT,
    how TEXT NOT NULL,
    created_at TEXT NOT NULL,
    quarantined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    quarantined_because TEXT NOT NULL
);
INSERT INTO quarantined_facts
    (id, thread_id, fact, value, origin, actor, tool, how, created_at,
     quarantined_because)
    SELECT id, thread_id, fact, value, origin, actor, tool, how, created_at,
           '{_BECAUSE_SQL}'
    FROM fact_evidence
    WHERE {_ORPHANED};
DELETE FROM fact_evidence WHERE {_ORPHANED};
CREATE TABLE fact_evidence_v7 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER REFERENCES threads(id),
    fact TEXT NOT NULL,
    value TEXT NOT NULL,
    origin TEXT NOT NULL,
    actor TEXT NOT NULL,
    tool TEXT,
    how TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (thread_id IS NULL OR thread_id > 0)
);
INSERT INTO fact_evidence_v7
    (id, thread_id, fact, value, origin, actor, tool, how, created_at)
    SELECT id, thread_id, fact, value, origin, actor, tool, how, created_at
    FROM fact_evidence;
DROP TABLE fact_evidence;
ALTER TABLE fact_evidence_v7 RENAME TO fact_evidence;
DELETE FROM sqlite_sequence WHERE name = 'fact_evidence';
INSERT INTO sqlite_sequence (name, seq)
    SELECT 'fact_evidence', MAX(high) FROM (
        SELECT IFNULL(MAX(id), 0) AS high FROM fact_evidence
        UNION ALL
        SELECT IFNULL(MAX(id), 0) AS high FROM quarantined_facts
    );
"""
