"""6 - three rows that could open the first gate in any conversation, quarantined.

## What was wrong with the data

`fact_evidence.thread_id` is nullable and `evidence.rows_for` reads a NULL there
as MACHINE SCOPE: this box's GPU is this box's GPU whichever conversation asked,
so a row with no thread is shown to every thread. That reading is right and it
stays. What did not exist was any rule on the WRITE side - `record()` took
`thread_id=None` for any fact at all, and `POST /api/tools/{name}` made the
argument optional - so `measure_eval_set` and `profile_dataset` called without
one counted a real file honestly and filed the answer where every conversation
on the machine could read it.

The owner's database held exactly three such rows when this was found. All three
were `eval_size_n`, all three MEASURED, all three from `profile_dataset`, and
between them they name two temporary directories that no longer exist:

    id 36  eval_size_n = 120  MEASURED  ...Temp\\tmp4myaw83y\\eval.jsonl
    id 37  eval_size_n = 120  MEASURED  ...Temp\\tmp4myaw83y\\eval.jsonl
    id 38  eval_size_n = 120  MEASURED  ...Temp\\tmph_4tt4go\\eval.jsonl

NONE of the machine-scope rows were hardware. Every one of the 36 hardware rows
in that database carries a thread. So the mechanism that exists for the machine's
own facts was, in practice, in use by exactly one fact - the one fact in the
product that must never use it, and the one the first gate reads.

The consequence, reproduced before this was written: a thread that had never been
shown a file read `Fact(value=120, origin='MEASURED')`, and G0_EVAL_SET - the
gate the whole decision tree stands on - opened on it.

## Why quarantine and not DELETE

These are the user's rows and they are real measurements: a file really was
counted, by a real tool, and the count really was 120. What is missing is what
the count was OF and where it belongs, and that is not something a migration can
supply - the directories are gone, and guessing a thread id would be inventing
the exact fact that is missing. So nothing is deleted and nothing is edited.

Each row moves, whole, into `quarantined_facts`, keeping its original id, its
value, its origin, its actor, its tool, its `how` sentence and its `created_at`.
It gains two columns: when it was moved, and one sentence saying why. `rows_for`
does not read that table and never will, so a quarantined row cannot open a gate
in any conversation; `evidence.quarantine_view` does, so a person can still see
it, and `GET /api/evidence` shows it beside the live ledger.

A separate table rather than a flag on `fact_evidence`, for the same reason the
ledger is append-only: `rows_for` composes its own WHERE clause, and a flag is a
condition somebody has to remember to add to it. A row in another table cannot be
forgotten back into a gate.

## Why the four fact names are written out here

A migration is a statement about a database at one moment, and it must mean the
same thing forever. `docs/diagnosis_engine.yaml` is where scope is declared and
where it will change; if this file read that ledger, then adding a `scope:
machine` fact next year would silently change what this migration DID to a
database it ran against last year. So the four names are frozen here, as of the
day this shipped, and they are the four `app/hwdetect.py` reads:

    accelerator, vram_gb, ram_gb, disk_free_gb

The live rule is `evidence.scope_of`, read off the ledger, checked on every
write. This is the one-time repair, and `tests/test_a_thread_scoped_fact_needs
_a_thread.py` asserts the two agree on the day of shipping, so a divergence is a
failing test rather than a silent drift.

## Why `fact_evidence` is created here

That table has never been in a migration - `evidence.ensure_table()` creates it
lazily on first use, in the self-healing style this package's docstring is a
complaint about. A database that has never recorded a fact does not have it, and
`INSERT INTO ... SELECT FROM fact_evidence` against such a database is "no such
table" and a failed migration on a brand-new install. The `CREATE TABLE IF NOT
EXISTS` below is `evidence._SCHEMA` verbatim, so on any existing database it is a
no-op, and the fold of that table into this runner is one line whenever somebody
has a reason to finish it.

## What this does to a database with nothing wrong with it

Nothing. The `SELECT` matches no rows, the `DELETE` removes none, and the two
`CREATE TABLE IF NOT EXISTS` statements find or make empty tables. Measured on a
copy of the owner's real database: 50 evidence rows before, 47 after, 3
quarantined, and every other table byte-identical.

SHIPPED. Never edit this file. A correction is a new migration.
"""

VERSION = 6

#: The reason, written into every row this moves. One sentence, in the row, so
#: somebody reading the table in six months does not have to find this file.
_BECAUSE = (
    "written with no thread_id before facts declared a scope, so evidence.rows_for "
    "showed it to every conversation on this machine; the ledger declares this "
    "fact scope: thread, meaning it is true of one project in one conversation "
    "and of no other. Moved rather than deleted: the measurement was real, only "
    "unattached. See app/migrations/v006_machine_scope_is_declared_not_assumed.py."
)

#: Frozen on the day this shipped. See the docstring: a migration that read the
#: live ledger would change what it did to yesterday's database when tomorrow's
#: ledger changes.
_MACHINE_FACTS = "'accelerator', 'vram_gb', 'ram_gb', 'disk_free_gb'"

#: SQL-quoted, by doubling, rather than trusted to contain no apostrophe. It
#: contains none today; an edit to the sentence above must not be able to turn
#: this migration into a syntax error - or into something else - on somebody's
#: real database.
_BECAUSE_SQL = _BECAUSE.replace("'", "''")

SQL = f"""
CREATE TABLE IF NOT EXISTS fact_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER,
    fact TEXT NOT NULL,
    value TEXT NOT NULL,
    origin TEXT NOT NULL,
    actor TEXT NOT NULL,
    tool TEXT,
    how TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
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
    WHERE thread_id IS NULL
      AND fact NOT IN ({_MACHINE_FACTS});
DELETE FROM fact_evidence
    WHERE thread_id IS NULL
      AND fact NOT IN ({_MACHINE_FACTS});
"""
