"""12 - an agent run keeps the cases it graded, so a second run can be compared to it.

## What was missing, measured

`app/tools/agents.py` contained no database write of any kind. `run_the_failures`
read a failure file, graded every case against the answers somebody's agent
produced, stamped `baseline_success_rate` and `failure_buckets`, reported - and
forgot. The rate was on the ledger; the rows behind it were gone.

That is what stood between this product and its own thesis. The six outcomes
this harness reaches most often on the AI ledger are refusals that name a cheap,
local fix - *the tool description is the bug*, *the prompt is the bug*,
*constrain the output* - and every one of them is only worth saying if the
person can then find out whether the fix worked. Finding that out is a PAIRED
comparison over the same cases, and a paired comparison needs both recordings.

`propose.NOT_COVERED` had already written down exactly this:

    "the paired proof is designed (change description, re-run same rows,
     McNemar) and half-built: run_the_failures grades leg one today. The owed
     piece is the compare step wired to evals.compare over two recordings."

## Why it mirrors `eval_runs` / `eval_results` rather than reusing them

The shapes rhyme and the subjects do not. An eval run scores a MODEL over an
eval set through a prompt; an agent run grades a recording somebody's AGENT
produced over a failure set, and this harness never drives that agent. The
columns that differ are the ones that carry that difference: there is no
`prompt` and no `provider_id`, because nothing here called a model - and there
IS an `answers_path` and a `traces_path`, because what was graded is a file the
person made.

Writing agent cases into `eval_results` would have made every reader of that
table ask which kind of row it was holding, on every query, forever. Two tables
that rhyme cost one migration; one table with a `kind` column costs a check in
every reader.

## What makes a comparison PAIRED, and it is `case_key` rather than `row_index`

`eval_results` pairs on `row_index` - the position of the row among the
eligible ones - because an eval set is a file the harness itself carved and
counts through. A failure set is not that. It is the person's export, and
between two recordings they will have re-exported it, sorted it, dropped a
fixed case, or added three new ones. Pairing on position would then compare
case 7 of one run against a different case 7 of the other and call the
difference an improvement.

So a case is keyed by a digest of its INPUT and its EXPECTED answer, which is
what makes it the same question. Two runs are paired on the keys they share;
what only one of them holds is reported as such and is not scored. That is the
same discipline `read_eval_results(against=...)` already applies to the rows
both runs graded, expressed for a file whose row order is nobody's promise.

## The uniqueness constraint is on `(run_id, case_key)` and it bites

One run may not grade the same question twice. A failure export with a
duplicated case is a real thing and the honest response is to refuse the second
write rather than record two verdicts for one question and average them later.

## `thread_id` cascades, like `storms` and `eval_runs`

Every fact these runs produce is declared `scope: thread` in
`docs/ledgers/ai_engineering.yaml`. A run readable from another conversation
would be the eval-set leak of `v006`/`v007` with an extra table in the way.

SHIPPED. Never edit this file. A correction is a new migration.
"""

VERSION = 12

SQL = """
CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    -- What was graded, and where it came from. `signature` is a digest of the
    -- failure set itself, so two runs over the same questions can be found
    -- without trusting that the file kept its name or its path.
    signature TEXT NOT NULL,
    failures_path TEXT NOT NULL,
    answers_path TEXT NOT NULL DEFAULT '',
    traces_path TEXT NOT NULL DEFAULT '',
    input_field TEXT NOT NULL,
    expected_field TEXT NOT NULL,
    answer_field TEXT NOT NULL DEFAULT '',
    -- A label the person gives a recording so two of them can be told apart in
    -- a comparison: "before the description change", "after". Never invented
    -- here; empty is a legal and common value.
    label TEXT NOT NULL DEFAULT '',
    graded INTEGER NOT NULL,
    passed INTEGER NOT NULL,
    unterminated INTEGER NOT NULL DEFAULT 0,
    buckets_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (graded >= 0),
    CHECK (passed >= 0),
    CHECK (passed <= graded),
    CHECK (unterminated >= 0)
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_thread ON agent_runs(thread_id, id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_signature ON agent_runs(signature, id);
CREATE TABLE IF NOT EXISTS agent_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    -- THE PAIRING KEY. A digest of input+expected, because a failure export's
    -- row order is nobody's promise. See the module docstring.
    case_key TEXT NOT NULL,
    input TEXT NOT NULL,
    expected TEXT NOT NULL,
    answer TEXT NOT NULL DEFAULT '',
    passed INTEGER NOT NULL,
    terminated INTEGER NOT NULL DEFAULT 1,
    bucket TEXT,
    bucketed_by TEXT NOT NULL DEFAULT 'rules',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (run_id, case_key),
    CHECK (passed IN (0, 1)),
    CHECK (terminated IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_agent_results_run ON agent_results(run_id, case_key);
"""
