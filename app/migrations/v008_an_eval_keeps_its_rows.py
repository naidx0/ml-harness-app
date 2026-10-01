"""8 - an eval run keeps the rows it graded, not only the score it produced.

## Why a table at all, when a score is one number

Every other tool in this space gives you the aggregate. `73%` is the thing a
prompt playground shows you, and it is the thing that cannot answer any of the
questions that matter next: *which* rows failed, *how* they failed, whether the
run finished, and whether the 76% you get after editing the prompt is a real
improvement or noise on the same forty rows.

`app/tools/measure.py` already scores a baseline once. It streams the eval file,
asks the model, counts the hits, stamps three facts and throws every row away.
That was right for what it is - the sentence G1 asks for, said once - and it is
exactly half of what the evaluation bench needs, because **the aggregate is what
every other tool already gives you.** The per-row rows are the point.

Three things become possible the moment a row survives its run, and none of them
is possible without this table:

1. **Comparison.** A later run on the same rows can be compared to this one
   PAIRWISE, which is a far stronger test than comparing two aggregates - only
   the rows that CHANGED carry information, and McNemar's exact test over them
   is what lets the harness say "these two are indistinguishable" and mean it.
2. **Failure buckets.** `failure_histogram` is declared `source: derive` in
   `docs/diagnosis_engine.yaml`, which admits MEASURED and nothing else - so
   today nobody can supply it at all and stage 1 always terminates in
   `ACTION__CLASSIFY_FAILURES`. A run that knows which rows failed can bucket
   them and stamp it.
3. **Interruption.** An eval over five hundred rows takes real time, and a
   laptop closes. A row committed the moment it is graded is a row that survives
   the process; a run that is a single in-memory loop loses everything.

## Two tables, and the split is between what was PROMISED and what HAPPENED

The same split `app/migrations/v005_storms.py` makes, for the same reason.

`eval_runs` is written once and never changes: which file, which fields, which
prompt, which model, which metric, how many rows this run intends to grade, and
the `signature` that identifies the question being asked. It is the contract.

`eval_results` is append-only: one row per graded eval row, committed before the
next question goes out.

**There is deliberately no `status` column and no `finished_at`.** A run is
complete when `COUNT(eval_results) = eval_runs.planned` and by no other test.
A status column would be a second answer to the same question, and the two would
disagree the first time a process died between the write and the commit - which
is precisely the event this table exists to survive. `UNIQUE (run_id,
row_index)` is what makes the count trustworthy: resuming a run cannot
double-count a row it already graded, whatever order the resume happens in.

**Nothing in `app/tools/evals.py` issues an `UPDATE` or a `DELETE` against
either table.** Same discipline as `events`.

## What each column is for, where it is not obvious

`signature` is the hash of everything that decides what would be ASKED: the eval
rows themselves, the two field names, the adapter, the base URL, the model, the
system prompt, the metric, the sample size and the held-out rows. Two runs with
the same signature are the same question, so the second one does not re-bill the
user's model for an answer that is already on disk. It is indexed because that
lookup happens on every call.

`eval_fingerprint` is the hash of the graded pairs alone, so two runs of
DIFFERENT prompts over the SAME eval set can be found and compared. That is the
prompt bench's whole query.

`planned` is how many rows the run intends to grade; `rows_available` is how many
rows of the file had both fields. They differ whenever `sample` is smaller than
the file, and the difference is what "grade seventy more rows" is computed from.

`trivial_baseline` and `trivial_answer` are the majority answer over the graded
rows, computed from the file with no model involved. Stored on the run so a
re-read never needs the file back, and kept for the reason `measure_baseline`
keeps it: a system that cannot beat "always say the most common label" has not
been shown to work at all.

`verdicts_json` holds EVERY metric's verdict for the row, not just the one the
run was scored on. That is what makes a model-graded score checkable: when the
judge says a row is right and exact match says it is wrong, both readings are in
the row and the gap between them is visible rather than a thing somebody has to
go and re-derive.

`graded_by` and `bucketed_by` say who decided, per row. `graded_by` is the
metric for a rule and `model:<name>` for a judge. `bucketed_by` is `rules` for
every row this build writes, and it is a column rather than a constant because
the next thing anybody adds here is a judge that buckets, and a bucket decided by
a model must not be indistinguishable from one decided by a rule that a person
can reproduce by eye.

`failure_mode` holds the ROW-LOCAL bucket only. `inconsistent` - the same input
answered two different ways - cannot be seen from one row and is derived over the
run at report time. Storing a cross-row conclusion in a per-row column would mean
either updating rows already written or writing a conclusion before the evidence
for it exists, and both are worse than a derivation that is recomputed from the
same rows every time.

There is no `error` column, and that is a decision rather than an omission. A row
whose model call failed is not graded and is not written: the run stops, keeps
everything already committed, and says which row it stopped at.
`app/tools/measure.py`'s rule - *a score from a run that fell over is not a
score* - is reused verbatim, and resumption is what makes stopping cheap.

## What this migration does to a database that has never seen it

Adds two empty tables and three indexes. Nothing is copied, nothing is moved,
nothing is rebuilt, and no existing table is touched - so unlike migrations 6 and
7 there is no quarantine here and nothing to say about rows that already exist,
because there are none.

`thread_id` is a real foreign key with `ON DELETE CASCADE`, matching `storms`. An
eval run belongs to one conversation for the same reason a measurement does:
`docs/diagnosis_engine.yaml` declares every fact this produces `scope: thread`,
and a run that could be read from another conversation would be the eval-set leak
of `v006`/`v007` with an extra table in the way.

SHIPPED. Never edit this file. A correction is a new migration.
"""

VERSION = 8

SQL = """
CREATE TABLE IF NOT EXISTS eval_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    signature TEXT NOT NULL,
    eval_path TEXT NOT NULL,
    eval_fingerprint TEXT NOT NULL,
    input_field TEXT NOT NULL,
    expected_field TEXT NOT NULL,
    metric TEXT NOT NULL,
    prompt TEXT NOT NULL,
    prompt_is_default INTEGER NOT NULL DEFAULT 0,
    provider_id INTEGER,
    provider_name TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    locality TEXT NOT NULL DEFAULT '',
    judge_model TEXT,
    planned INTEGER NOT NULL,
    rows_available INTEGER NOT NULL,
    trivial_baseline REAL,
    trivial_answer TEXT,
    latency_budget_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (planned >= 0),
    CHECK (rows_available >= 0),
    CHECK (prompt_is_default IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_eval_runs_thread ON eval_runs(thread_id, id);
CREATE INDEX IF NOT EXISTS idx_eval_runs_signature ON eval_runs(signature, id);
CREATE TABLE IF NOT EXISTS eval_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
    row_index INTEGER NOT NULL,
    input TEXT NOT NULL,
    expected TEXT NOT NULL,
    answer TEXT NOT NULL DEFAULT '',
    correct INTEGER NOT NULL,
    verdicts_json TEXT NOT NULL DEFAULT '{}',
    failure_mode TEXT,
    graded_by TEXT NOT NULL,
    bucketed_by TEXT NOT NULL DEFAULT 'rules',
    seconds REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (run_id, row_index),
    CHECK (correct IN (0, 1)),
    CHECK (row_index >= 0)
);
CREATE INDEX IF NOT EXISTS idx_eval_results_run ON eval_results(run_id, row_index);
"""
