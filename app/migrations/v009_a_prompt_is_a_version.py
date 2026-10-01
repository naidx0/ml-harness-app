"""9 - a prompt is a version of something, and a winner is a row nobody can
write without the evidence.

## Why a prompt needs tables when `eval_runs` already stores the prompt text

`app/migrations/v008_an_eval_keeps_its_rows.py` stores `prompt` on every run, so
the naive reading is that the prompt bench needs no schema at all: run the eval
twice with two different strings and subtract. That reading is exactly the
product this repository exists not to be, and it fails on three questions a
prompt playground cannot answer:

1. **Better than what?** A score is a number about one prompt. "Better" is a
   claim about a PAIR, and the pair has to be recorded or the comparison is
   whichever two runs somebody happened to put side by side. `eval_runs` has no
   idea that run 7 was an edit of run 4 rather than an unrelated experiment.
2. **Changed how, and aimed at what?** `docs/VISION.md` quotes the engine's own
   instruction - *"Rewrite the system prompt against the failure buckets. Name
   the rule that was broken, explicitly."* A prompt change with no named target
   cannot be checked against the bucket it claimed to fix, and the bucket is the
   material the eval bench produces.
3. **Which one is the one to beat?** Without that, the fortieth edit is compared
   against whichever of the previous thirty-nine the user remembers, and
   `docs/PRODUCT_SPEC.md` §6.5 is precise about why that is dangerous: *"a
   prompt change is cheap enough to make forty times and a user who is shown
   forty unresolvable deltas will believe the tenth one."*

## THIS IS NOT THE PROMPT REGISTRY §6.5 REFUSES, AND THE DIFFERENCE IS REAL

`docs/PRODUCT_SPEC.md` §6.5 says in as many words: *"It does not manage prompt
versions as a product - no prompt registry, no A/B traffic split, no
deployment."* Three tables named `prompt_*` deserve an answer to that and not a
shrug, so here it is.

What §6.5 forbids is a PRODUCTION artefact: a place prompts are served from,
split across traffic, promoted between environments, shared between projects.
Nothing here can do any of that. Every row is `thread_id`-scoped through
`prompt_lines`, which cascades from `threads`; nothing outside one conversation
can read a line; there is no export, no endpoint that serves a prompt to a
runtime, and no notion of an environment at all.

What these tables ARE is the sentence §6.5 says the bench does do - *"It writes
each attempt into the thread, which is the lab notebook"* - made queryable
instead of left in prose. A lab notebook you cannot query cannot answer "better
than what", and the alternative to a table is not "no registry", it is the same
history stored in a chat transcript where a comparison has to be reconstructed
by a model reading back over its own words. That is the drift this repository
has been bitten by twice.

## THREE TABLES, AND THE THIRD ONE IS THE WALL

`prompt_lines` - one line of descent. It pins the INSTRUMENT: which eval file,
which two columns, which metric, how many rows, and the latency budget. Every
variant in a line is scored the same way, because two prompts graded by
different metrics were never comparable and a bench that let that happen would
be handing out the defect it exists to catch.

`prompt_variants` - one version of the prompt. Append-only. `parent_id` is what
it was edited from, `change_note` is what changed in words, `targets` is the
failure mode it was aimed at, and `exemplars_json` is the row indexes used as
few-shot examples - which are the rows that MUST be held out of its score.
`UNIQUE (line_id, text_sha)` is why a byte-for-byte re-submission is caught
before anybody's tokens are spent on measuring the same prompt twice.

`prompt_scores` - the join from a variant to the `eval_runs` row that scored it.
Its own table rather than a column on the variant, so that re-scoring is an
INSERT and never an UPDATE, and so that a variant whose run was interrupted and
later resumed keeps one row rather than growing a second answer. **No score,
resolution, model or fingerprint is copied here.** All of that is read back
through `app/tools/evals.py` from `eval_runs` and `eval_results`, because a
second copy of a number is a second answer to the same question, and this
repository has watched that go wrong.

`prompt_champions` - **the wall, and it is in SQL rather than in prose.**

## WHY THE WALL IS A `CHECK` AND NOT A DOCSTRING

The one thing that makes this bench different from every prompt playground is
that it refuses to declare a winner it cannot resolve. `app/tools/evals.py`
already computes that refusal - McNemar's exact test over the rows that changed,
and the words NO EVIDENCE when the test cannot separate two runs. The risk is
not that the computation is wrong. The risk is that six months from now
somebody adds a second path that records a winner and forgets to consult it.

`docs/THE_PROPOSAL_LOOP.md` says it about a different failure and it is the same
failure: *prose is not a wall*. So the constraint is on the table:

    CHECK (basis = 'first' OR (beat_variant_id IS NOT NULL
           AND p_value IS NOT NULL AND p_value <= 0.05
           AND improved IS NOT NULL AND regressed IS NOT NULL
           AND improved > regressed
           AND paired_rows IS NOT NULL AND paired_rows > 0))

A row that claims one prompt beat another must carry the paired counts and a
p-value at or under 0.05, and must have more rows improved than regressed - the
last clause because McNemar is TWO-SIDED and a significant result is just as
easily a significant regression. SQLite rejects the INSERT otherwise. There is
no code path, present or future, that can crown an unresolvable winner, and a
patch that tried would fail with an integrity error rather than with a review
comment.

`0.05` is written here as a literal and it is not this file's invention: it is
the same threshold `evals.compare` applies when it sets `resolved`, and
`app/tools/prompts.py` never makes the decision itself - it reads that flag and
this constraint is the floor underneath it.
`tests/test_the_prompt_bench_refuses_to_pick.py` pins the two together, so a
change to either that leaves them disagreeing turns the suite red.

**The other direction is closed too.** A `basis = 'first'` row - the first
variant of a line, crowned because there was nothing to beat - must carry NO
comparison figures at all. Otherwise "first" would be the hole: a row claiming a
delta and a p-value while declaring itself exempt from having to justify them.

## THE NULL TRAP THIS CONSTRAINT IS WRITTEN AROUND

SQLite's `CHECK` fails only when its expression evaluates to FALSE. **NULL
passes.** So `improved > regressed` alone would be satisfied by a row with a
NULL `improved`, which is precisely the row a careless INSERT writes. Every
column in the constraint is therefore tested `IS NOT NULL` before it is compared,
and the `IS NOT NULL` is written to the LEFT so the AND short-circuits to 0
rather than to NULL. This is the reason the constraint reads longer than it
needs to.

## WHAT THIS MIGRATION DOES TO A DATABASE THAT HAS NEVER SEEN IT

Adds three empty tables and four indexes. Nothing is copied, moved or rebuilt,
and no existing table is altered - `eval_runs` is referenced and not touched. As
with migration 8 there is no quarantine and nothing to say about rows that
already exist, because there are none.

`prompt_lines.thread_id` is a real foreign key with `ON DELETE CASCADE`,
matching `storms` and `eval_runs`. A prompt line belongs to one conversation for
the reason everything measured here does: the eval set that scores it is
thread-scoped, and a line readable from a second conversation would be the
eval-set leak of `v006`/`v007` wearing a third table.

SHIPPED. Never edit this file. A correction is a new migration.
"""

VERSION = 9

SQL = """
CREATE TABLE IF NOT EXISTS prompt_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    eval_path TEXT NOT NULL,
    input_field TEXT NOT NULL,
    expected_field TEXT NOT NULL,
    metric TEXT NOT NULL,
    sample INTEGER NOT NULL,
    latency_budget_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (thread_id, name),
    CHECK (sample >= 1),
    CHECK (length(name) > 0)
);
CREATE INDEX IF NOT EXISTS idx_prompt_lines_thread ON prompt_lines(thread_id, id);
CREATE TABLE IF NOT EXISTS prompt_variants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    line_id INTEGER NOT NULL REFERENCES prompt_lines(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    parent_id INTEGER REFERENCES prompt_variants(id) ON DELETE SET NULL,
    text TEXT NOT NULL,
    text_sha TEXT NOT NULL,
    change_note TEXT NOT NULL DEFAULT '',
    targets TEXT,
    exemplars_json TEXT NOT NULL DEFAULT '[]',
    author TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (line_id, version),
    UNIQUE (line_id, text_sha),
    CHECK (version >= 1),
    CHECK (length(text) > 0),
    CHECK (parent_id IS NULL OR parent_id <> id)
);
CREATE INDEX IF NOT EXISTS idx_prompt_variants_line
    ON prompt_variants(line_id, version);
CREATE TABLE IF NOT EXISTS prompt_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    variant_id INTEGER NOT NULL REFERENCES prompt_variants(id) ON DELETE CASCADE,
    run_id INTEGER NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (variant_id, run_id)
);
CREATE INDEX IF NOT EXISTS idx_prompt_scores_variant
    ON prompt_scores(variant_id, id);
CREATE TABLE IF NOT EXISTS prompt_champions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    line_id INTEGER NOT NULL REFERENCES prompt_lines(id) ON DELETE CASCADE,
    variant_id INTEGER NOT NULL REFERENCES prompt_variants(id) ON DELETE CASCADE,
    beat_variant_id INTEGER REFERENCES prompt_variants(id) ON DELETE SET NULL,
    run_id INTEGER REFERENCES eval_runs(id) ON DELETE SET NULL,
    beat_run_id INTEGER REFERENCES eval_runs(id) ON DELETE SET NULL,
    basis TEXT NOT NULL,
    paired_rows INTEGER,
    improved INTEGER,
    regressed INTEGER,
    delta REAL,
    p_value REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (basis IN ('first', 'resolved')),
    CHECK (beat_variant_id IS NULL OR beat_variant_id <> variant_id),
    CHECK (
        basis <> 'resolved'
        OR (
            beat_variant_id IS NOT NULL
            AND p_value IS NOT NULL AND p_value <= 0.05
            AND improved IS NOT NULL AND regressed IS NOT NULL
            AND improved > regressed
            AND paired_rows IS NOT NULL AND paired_rows > 0
        )
    ),
    CHECK (
        basis <> 'first'
        OR (
            beat_variant_id IS NULL
            AND beat_run_id IS NULL
            AND p_value IS NULL
            AND improved IS NULL
            AND regressed IS NULL
            AND delta IS NULL
            AND paired_rows IS NULL
        )
    )
);
CREATE INDEX IF NOT EXISTS idx_prompt_champions_line
    ON prompt_champions(line_id, id);
"""
