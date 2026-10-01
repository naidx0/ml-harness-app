"""11 - a conversation says which ledger it is running, instead of everything being ML.

## What was wrong

Nothing, yet, and that is why this is a schema change with no data repair in it.
Every thread in every database that exists today genuinely IS a machine-learning
thread, because `docs/diagnosis_engine.yaml` is the only ledger any route
through the product has ever reached. `app/tools/registry.py` resolves a tool's
ledger from the thread it is called on, and before this column there was nothing
on a thread to resolve.

The defect this closes is the one measured in `docs/CAPABILITY_BLOCKS.md` §1.4:
thirty-three sites across fifteen modules ask for *the ledger this thread is
running* and get the ML file unconditionally, so a second ledger would diagnose
correctly and then hand its verdict to a tool layer still reading the first
ledger's knowledge. A column is what lets those sites be answered honestly.

## Why the value stored is a RELATIVE path

`docs/diagnosis_engine.yaml`, not `C:\\Users\\...\\docs\\diagnosis_engine.yaml`.
A stored absolute path is a promise about a directory rather than about a
document, and it is broken by the two most ordinary events there are: the
checkout moving, and the same database being opened on a second machine. The
repository root is where `app/diagnosis.py` lives and `resolve_ledger()` is the
single reader that joins the two. An absolute path is still honoured if one is
written - a ledger outside the tree is a real case - it is simply not what this
migration writes.

## Why NOT NULL with a default rather than nullable

"This thread never said which ledger it runs" and "this thread runs the ML
ledger" are not different states in any database that exists today, and a
nullable column would invite a reader to invent the difference later. SQLite
allows `ADD COLUMN ... NOT NULL DEFAULT <constant>` precisely because the
constant answers the question for every existing row; every row gets the ledger
it has in fact been running since it was created.

The column is not a foreign key and cannot be: it names a file in the source
tree, not a row. A thread pointing at a ledger that does not load fails LOUDLY
at its first tool call, with the path in the message, rather than falling back
to the default - see `diagnosis.spec_at`. A silent fallback would be a thread
that said it was an AI-engineering thread, got the ML ledger, and diagnosed
confidently against the wrong knowledge, which is the exact defect this column
is here to make impossible.

## What this does to a database with nothing wrong with it

Adds one column and writes one constant into every existing row. Measured on a
fresh database and on one with threads in it: `PRAGMA table_info(threads)` gains
`ledger TEXT NOT NULL DEFAULT 'docs/diagnosis_engine.yaml'`, every existing
thread reads back `docs/diagnosis_engine.yaml`, and no other table is touched.

SHIPPED. Never edit this file. A correction is a new migration.
"""

VERSION = 11

#: Frozen here rather than read from `diagnosis.DEFAULT_LEDGER`, for the reason
#: v006's docstring gives about the four fact names it wrote out: a migration is
#: a statement about a database at one moment and must mean the same thing
#: forever. If this line read the live constant, renaming the default ledger next
#: year would silently change what this migration DID to a database it ran
#: against last year. `tests/test_a_thread_names_its_ledger.py` asserts the two
#: agree on the day of shipping, so a divergence is a failing test rather than a
#: drift nobody sees.
_THE_LEDGER_EVERY_EXISTING_THREAD_IS_RUNNING = "docs/diagnosis_engine.yaml"

SQL = f"""
ALTER TABLE threads
    ADD COLUMN ledger TEXT NOT NULL
    DEFAULT '{_THE_LEDGER_EVERY_EXISTING_THREAD_IS_RUNNING}';
"""
