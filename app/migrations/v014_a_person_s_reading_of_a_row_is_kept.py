"""A person's reading of a failing row is kept, beside the rule's, not over it.

## The gap this closes

`rebucket_failures` (2026-08-30) let a person say which failure mode each
graded row really belongs to, and stamped the re-tallied histogram as a
MEASURED fact. But the reading itself was thrown away the moment the tally was
made: `eval_results` is append-only (migration 8, held by a test that reads
`app/tools/evals.py` for the verb), so nothing wrote the person's bucket onto
the row, and every other reader of that run - `choose_exemplars`, which builds
few-shot prompts out of the failures in a named bucket; `read_eval_results`;
the failure list in the pane - kept reading the rule's bucket.

Seen on 2026-09-01, thread 33 of the Practical ML workspace: 26 failing rows
re-bucketed `wrong_facts` by the person who read them, the histogram fact
recorded, and one call later `try_prompt(fewshot_from_failures=8,
targets="wrong_facts")` answered *"there are no failing rows to draw exemplars
from in the wrong_facts bucket"*. The correction existed as a count and
nowhere else.

## One table, append-only, like the rows it annotates

`eval_rebuckets` holds one row per (run, row, reading). A person can re-read a
row twice; both readings are kept and the latest wins when a reader overlays
them, which is what `results_for` does. Nothing in `eval_results` changes - the
rule's bucket stays on the row underneath and the reader can still see what
the rule said and what the person said, which is the provenance question this
product exists to keep answerable.

`failure_mode` is not an enum here for the same reason it is not one in
`eval_results`: the routable vocabulary is the ledger's, read at call time by
`rebucket_failures`, and a schema that froze it would have to migrate every
time the ledger learned a route.

## What this does to a database with nothing wrong with it

Creates one empty table and one index. No existing table is touched.

SHIPPED. Never edit this file. A correction is a new migration.
"""

VERSION = 14

SQL = """
CREATE TABLE IF NOT EXISTS eval_rebuckets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
    row_index INTEGER NOT NULL,
    failure_mode TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (row_index >= 0),
    CHECK (length(failure_mode) > 0)
);
CREATE INDEX IF NOT EXISTS idx_eval_rebuckets_run_row
    ON eval_rebuckets(run_id, row_index, id);
"""
