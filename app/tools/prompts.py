"""The prompt bench: change the prompt, score it on the user's own eval set, and
refuse to call it better when the eval set cannot tell.

`docs/VISION.md` says the most valuable thing this product can say is *"do not
train anything"* - and then names the hole: **that answer is currently a dead
end.** We tell somebody their real problem is the prompt, name precisely what to
do instead, and hand them nothing. This module is the first place a no-train
verdict stops being advice and becomes an artifact:

    NO_TRAIN__BETTER_PROMPT  "Rewrite the system prompt against the failure
                              buckets. Name the rule that was broken, explicitly."
    NO_TRAIN__FEW_SHOT       "Put 5-20 exemplars in the prompt, chosen from the
                              eval failures, not from the successes."

Both of those are quoted out of `docs/diagnosis_engine.yaml`. They were written
as terminal advice. They are now two arguments to one tool.

## WHAT THIS MODULE ADDS THAT `app/tools/evals.py` DOES NOT ALREADY DO

The eval bench is the keystone and this stands on it. Nothing here re-implements
grading, bucketing, resolution, pairing or McNemar's test: `evals.run` scores a
prompt, `evals.compare` pairs two runs and refuses the ones it cannot separate,
and `evals.read` is the report shape. Read that module's docstring first; this
one assumes it.

Three things are genuinely new, and each exists because a score alone cannot
answer the question a person actually asked.

**1. BETTER THAN WHAT.** A score is a fact about one prompt. *Better* is a claim
about a PAIR, and until the pair is recorded, "better" means whichever two runs
somebody happened to put side by side. So a prompt here is a VERSION of
something: it has a parent, a version number, a note saying what changed, the
failure mode it was aimed at, and the eval run that scored it. `eval_runs`
stores the prompt text already and has no idea that run 7 was an edit of run 4.

**2. AIMED AT A NAMED FAILURE, AND CHECKED AGAINST THAT BUCKET.** The engine's
own instruction is to rewrite *against the failure buckets*, naming the rule
that was broken. A change with a `targets=` therefore reports what happened to
THAT bucket - how many of its rows the change fixed, whether that many rows
could resolve anything, and what it broke elsewhere - and not only the
aggregate. An aggregate can be flat while a change fixes every format failure
and breaks an equal number of factual ones, and those are opposite findings.

**3. THE REFUSAL, AS A ROW NOBODY CAN WRITE.** Below.

## THE REFUSAL, AND WHY IT IS IN SQL

`docs/PRODUCT_SPEC.md` §6.5: *"a prompt change is cheap enough to make forty
times and a user who is shown forty unresolvable deltas will believe the tenth
one."* Two prompts at 73% and 76% on thirty rows are indistinguishable, and every
prompt playground on earth will let somebody conclude otherwise. The honest
output is *these two are the same as far as this eval can tell; grade this many
more rows and I can answer you*, with the number computed.

`evals.compare` already computes exactly that. The risk was never the arithmetic.
The risk is the second code path added a year from now that records a winner and
forgets to consult it - so the rule is not in this file's prose and not only in
its control flow. It is a `CHECK` on `prompt_champions`, in
`app/migrations/v009_a_prompt_is_a_version.py`:

* a row that says one prompt beat another must carry the paired counts and a
  p-value at or under `RESOLUTION_ALPHA`, and must have more rows improved than
  regressed;
* a row that says "first, there was nothing to beat" must carry no comparison
  figures at all, so `first` cannot become the hole.

SQLite rejects the INSERT otherwise. `docs/THE_PROPOSAL_LOOP.md` says it about a
different failure and it is this one too: **prose is not a wall.** This project
has learned that three times, and a docstring saying "we always check the
p-value" is what the three looked like beforehand.

Two consequences that follow and are worth saying out loud:

* **`attempt` never decides significance itself.** It reads `resolved` off
  `evals.compare` and adds one clause the two-sided test cannot carry -
  `improved > regressed`, because a significant McNemar result is just as easily
  a significant REGRESSION. The constraint is the floor underneath that, not a
  second opinion.
* **There is no override argument.** No `force`, no `adopt_anyway`, no
  `alpha`. A tool that refuses unless you ask it not to has not refused.

## WHAT IT REFUSES TO COMPARE AT ALL, AND ONE OF THESE IS OURS

`evals.compare` refuses two runs whose `eval_fingerprint` differs, because two
scores on two different eval sets are two facts and not a delta. That is
inherited whole. Three more refusals are added here, and the first is the one
that matters most:

1. **Two variants scored by different models are not compared.** `compare`
   checks the eval set and not the connection - correctly, because "did swapping
   the model help" is a legitimate question to ask of two runs. It is not the
   question a PROMPT bench asks. A prompt that scores better because the
   connection changed underneath it is the single easiest way to believe a
   prompt change worked, and it is refused by name.
2. **The line pins the instrument.** Eval file, both column names, metric,
   sample size and latency budget live on `prompt_lines` and are the same for
   every variant in it. Two prompts graded by different metrics were never
   comparable.
3. **A run that did not finish scores nothing.** `evals`' own rule - *a score
   from a run that fell over is not a score* - and here it also means the variant
   is recorded, keeps its graded rows, and cannot become the champion.

## PAIRED ROWS, AND THE DELTA THAT IS REPORTED INSTEAD

`compare` reports `delta` as the difference of the two runs' aggregate scores.
That is right when both runs graded the same rows and it is misleading the
moment they did not - which is exactly what few-shot causes, because the
exemplars are held out of the challenger's score and were not held out of the
champion's.

So this module computes `paired_delta` over the INTERSECTION: the rows both runs
actually graded, scored the same way for both. The McNemar p-value from
`compare` is already a paired statistic and needs no correction; only the delta
did. Both are reported, and the report says when they differ and why.

**This is also why a few-shot variant does not force the champion to be
re-scored.** The exemplar rows are excluded from both sides by the intersection,
so no leak survives into the comparison and nobody pays for a second run of a
prompt that has already been measured.

## FEW-SHOT: CHOSEN FROM THE FAILURES, AND HELD OUT BY CONSTRUCTION

`NO_TRAIN__FEW_SHOT` is explicit that exemplars come *from the eval failures, not
from the successes*, and `docs/PRODUCT_SPEC.md` §6.5 is explicit that they are
held out of the score, *"because scoring on your own exemplars is a leak and this
product exists to catch leaks."*

`fewshot_from_failures=n` therefore:

* reads the CHAMPION's stored per-row results and takes only rows that FAILED;
* spreads the choice round-robin across failure buckets in row order, so one
  bucket cannot own the prompt - unless `targets=` says to draw from one, which
  is the deliberate version of the same thing;
* **skips any row whose stored text was truncated.** `evals` stores at most
  `STORED_TEXT_CHARS` per field; a truncated exemplar teaches a truncated answer,
  and the number skipped is reported rather than quietly absorbed;
* writes the exemplars into the prompt text itself, so the stored variant IS the
  prompt that ran and is reproducible from the row;
* and puts their row indexes into `hold_out`, which there is no argument to turn
  off. The hold-out is not a flag beside the feature, it is the feature.

## WHAT THIS MODULE MEASURES: NOTHING, AND THE REASON IS IN THE LEDGER

`measures=()` on both tools, which is a structural property checked at
registration and not a promise. The bench cannot stamp a fact, so the question
"should an unresolved winner be recorded MEASURED" has no code path to reach.

It is worth writing down why it is not more than that, because the two facts
this bench looks like it observes are `prompt_iterations` and `fewshot_tried` -
G2's own facts - and `evidence.may_be_declared_measurable` refuses both today,
in a paragraph that names this exact tool:

    The ledger admits MEASURED for `source: ask` ... and it is right to. If the
    harness itself drove the five prompt rewrites, it WATCHED them ... Nothing in
    this harness drives that work today. ... THIS IS THE ONE PLACE TO WIDEN when
    a tool genuinely runs the prompt loop: widen it there and then, with the tool
    in front of you.

**That tool is now in front of somebody, and widening it is deliberately not
done in this step.** The reason is not timidity: `prompt_iterations` and
`fewshot_tried` are two of the three facts `G2_PROMPT_EXHAUSTED` reads, and
AGENTS.md invariant 4 says the five-gate test may never be weakened. Changing
which origins can open a gate is a change to the honesty machinery, it belongs
in `app/tools/evidence.py` with its own adversarial tests, and it is a different
step from the one that built the bench. What that step will need, so it is not
re-derived:

* the count is `prompt_variants` in this thread that have a COMPLETE run - a
  variant that was drafted and never scored is not an iteration, and a variant
  whose run was interrupted has not been tried;
* `fewshot_tried` is true only where `exemplars_json` is non-empty on such a
  variant, which is the difference between having few-shot prompted and having
  written the word "example" in a prompt;
* and both are `scope: thread`, which these tables already are.

Until then the honest reading is the one the ledger already has: the user is the
witness to their own week, the bench's history is in the report where they can
read it back, and `state_facts` is how a STATED answer gets recorded.

## WHAT THIS IS NOT

* **Not a prompt registry.** See the migration's docstring for the full answer to
  `docs/PRODUCT_SPEC.md` §6.5. Every row is thread-scoped, nothing is served,
  deployed or split across traffic, and there is no path out of the conversation.
* **Not the optimiser.** `NO_TRAIN__PROMPT_OPTIMIZER` is Milestone 13, brings
  DSPy, and gets its own dependency step. What is here is Milestone 3's half:
  rewrite and few-shot, which cost nothing beyond `run_eval` called twice.
* **Not constrained decoding.** `NO_TRAIN__CONSTRAINED_DECODING` needs a backend
  and a step of its own. The bench will happily show that `wrong_format` is the
  bucket that dominates, which is the finding that routes there.
* **Not a scorer.** Every number here is `evals`' or is counted off rows
  `evals` wrote.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from typing import Any, Iterable

from app import db, events
from app.tools import evals, evidence
from app.tools.evidence import Instrument
from app.tools.registry import tool


# ---------------------------------------------------------------------------
# Constants. Every number here says where it came from.


#: The significance threshold a comparison must clear before one prompt may be
#: recorded as having beaten another. NOT this module's decision and not this
#: module's invention: `evals.compare` sets `resolved` on `p_value <= 0.05` and
#: `attempt` reads that flag rather than re-testing. The constant exists so the
#: same number appears once in Python beside the `CHECK` in
#: `app/migrations/v009_a_prompt_is_a_version.py`, and
#: `tests/test_the_prompt_bench_refuses_to_pick.py` asserts the three agree.
RESOLUTION_ALPHA = 0.05

#: The most exemplars a few-shot variant may carry. `NO_TRAIN__FEW_SHOT` says
#: "5-20 exemplars" and this is the top of that band. There is deliberately no
#: floor enforced: a user with four failing rows should get four exemplars and a
#: sentence saying the engine asks for five, not a refusal that leaves them with
#: nothing.
MAX_EXEMPLARS = 20

#: What the engine asks for, quoted rather than enforced. Reported when a run
#: comes in under it so the shortfall is visible instead of silent.
ENGINE_ASKS_FOR_EXEMPLARS = 5

#: The marker `evals._clip` appends to a value it had to cut at
#: `evals.STORED_TEXT_CHARS`. A row carrying it is excluded from few-shot
#: selection: a truncated exemplar teaches a truncated answer, which is a wrong
#: exemplar rather than a short one. Named here because `_clip` is private;
#: `tests/test_the_prompt_bench_refuses_to_pick.py` round-trips a long value
#: through the eval bench and asserts this string still appears, so a change
#: there turns this suite red rather than quietly producing bad exemplars.
TRUNCATION_MARKER = "[truncated by app/tools/evals.py]"

#: `inconsistent` is a routable failure mode and it can never be a `targets=`.
#: It is not a property of a row - it is the same input answered two ways - so
#: `evals` derives it at report time and never stores it in `failure_mode`. A
#: bucket analysis keyed on stored modes therefore cannot see it, and accepting
#: it as a target would report an empty bucket for a mode that may well be the
#: user's largest.
NOT_A_ROW_LOCAL_MODE = ("inconsistent",)

#: How the exemplars are written into the prompt. Plain, labelled, and the same
#: shape every time, so a diff between two variants shows the exemplars that
#: changed rather than a reflowed block.
EXEMPLAR_PREAMBLE = (
    "Worked examples. Each one is an input of the kind you will be given, "
    "followed by the answer that would have been correct for it."
)

#: Event kinds. Best effort, like `evals._emit`: a failure to narrate must never
#: lose a recorded attempt.
TRIED = "prompt.tried"
ADOPTED = "prompt.adopted"
NO_EVIDENCE = "prompt.no_evidence"


def rows_for_a_clean_sweep(alpha: float = RESOLUTION_ALPHA) -> int:
    """The smallest bucket a change could fix ENTIRELY and still be resolved.

    COMPUTED, and it is the number that makes bucket-level honesty possible.
    Every row in a failure bucket was wrong, so a change aimed at that bucket can
    only improve rows and never regress them: McNemar's exact test over `b`
    improvements and no regressions is `2 / 2**b`, which does not reach 0.05
    until `b` is 6.

    That has a blunt consequence a prompt playground will never tell anybody: **a
    bucket of five rows cannot resolve anything, even if the change fixes all
    five of them.** Reporting "we fixed 100% of your format failures" off five
    rows is the never-invent-a-number failure wearing a percentage.

    Searched rather than solved so that it stays correct if `evals.mcnemar` ever
    changes - the answer must come from the test that will actually be applied.
    """
    for rows in range(1, 64):
        if evals.mcnemar(rows, 0) <= alpha:
            return rows
    return 64  # pragma: no cover - 2/2**64 is far below any usable alpha


#: `rows_for_a_clean_sweep()` at import, because it is a constant of the test and
#: not of the data, and every bucket report quotes it.
CLEAN_SWEEP_ROWS = rows_for_a_clean_sweep()


# ---------------------------------------------------------------------------
# The store. Nothing here issues an UPDATE or a DELETE.


def ensure_tables() -> None:
    """Bring the schema up to date. The prompt tables are migration 9's."""
    from app import migrations

    migrations.migrate()


def _sha(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def create_line(**columns: Any) -> dict[str, Any]:
    ensure_tables()
    names = sorted(columns)
    with db.session() as connection:
        cursor = connection.execute(
            "INSERT INTO prompt_lines (%s) VALUES (%s)"  # noqa: S608 - names are ours
            % (", ".join(names), ", ".join("?" for _ in names)),
            tuple(columns[name] for name in names),
        )
        row = connection.execute(
            "SELECT * FROM prompt_lines WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


def line_named(thread_id: int, name: str) -> dict[str, Any] | None:
    ensure_tables()
    with db.session() as connection:
        row = connection.execute(
            "SELECT * FROM prompt_lines WHERE thread_id = ? AND name = ?",
            (int(thread_id), str(name)),
        ).fetchone()
    return None if row is None else dict(row)


def get_line(line_id: int) -> dict[str, Any] | None:
    ensure_tables()
    with db.session() as connection:
        row = connection.execute(
            "SELECT * FROM prompt_lines WHERE id = ?", (int(line_id),)
        ).fetchone()
    return None if row is None else dict(row)


def lines_in(thread_id: int, limit: int = 50) -> list[dict[str, Any]]:
    """Every prompt line in this conversation, newest first. THREAD SCOPED."""
    ensure_tables()
    with db.session() as connection:
        rows = connection.execute(
            "SELECT l.*, "
            "(SELECT COUNT(*) FROM prompt_variants v WHERE v.line_id = l.id) "
            "  AS variants "
            "FROM prompt_lines l WHERE l.thread_id = ? ORDER BY l.id DESC LIMIT ?",
            (int(thread_id), int(limit)),
        ).fetchall()
    return [dict(row) for row in rows]


def variants_in(line_id: int) -> list[dict[str, Any]]:
    ensure_tables()
    with db.session() as connection:
        rows = connection.execute(
            "SELECT * FROM prompt_variants WHERE line_id = ? ORDER BY version",
            (int(line_id),),
        ).fetchall()
    return [_variant(row) for row in rows]


def get_variant(variant_id: int) -> dict[str, Any] | None:
    ensure_tables()
    with db.session() as connection:
        row = connection.execute(
            "SELECT * FROM prompt_variants WHERE id = ?", (int(variant_id),)
        ).fetchone()
    return None if row is None else _variant(row)


def _variant(row: Any) -> dict[str, Any]:
    item = dict(row)
    try:
        item["exemplars"] = json.loads(item.pop("exemplars_json") or "[]")
    except ValueError:  # pragma: no cover - we wrote it
        item["exemplars"] = []
    return item


def variant_with_text(line_id: int, text: str) -> dict[str, Any] | None:
    """The variant of this line that IS this prompt, byte for byte, or `None`.

    Looked up before anything is spent, so a caller who resubmits the champion
    unchanged is told which version it already is instead of paying to measure
    the same prompt a second time.
    """
    ensure_tables()
    with db.session() as connection:
        row = connection.execute(
            "SELECT * FROM prompt_variants WHERE line_id = ? AND text_sha = ?",
            (int(line_id), _sha(text)),
        ).fetchone()
    return None if row is None else _variant(row)


def create_variant(**columns: Any) -> dict[str, Any]:
    ensure_tables()
    names = sorted(columns)
    with db.session() as connection:
        cursor = connection.execute(
            "INSERT INTO prompt_variants (%s) VALUES (%s)"  # noqa: S608 - ours
            % (", ".join(names), ", ".join("?" for _ in names)),
            tuple(columns[name] for name in names),
        )
        row = connection.execute(
            "SELECT * FROM prompt_variants WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return _variant(row)


def record_score(variant_id: int, run_id: int) -> None:
    """Join a variant to the eval run that scored it. `INSERT OR IGNORE`.

    Nothing about the score is copied. A resumed run keeps its id, so a variant
    scored, interrupted and finished later has one row here and not two.
    """
    ensure_tables()
    with db.session() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO prompt_scores (variant_id, run_id) VALUES (?, ?)",
            (int(variant_id), int(run_id)),
        )


def runs_for_variant(variant_id: int) -> list[int]:
    ensure_tables()
    with db.session() as connection:
        rows = connection.execute(
            "SELECT run_id FROM prompt_scores WHERE variant_id = ? ORDER BY id",
            (int(variant_id),),
        ).fetchall()
    return [int(row["run_id"]) for row in rows]


def scoring_run(variant_id: int) -> dict[str, Any] | None:
    """The COMPLETE eval run that scores this variant, latest first, or `None`.

    A variant with only an interrupted run has no score, which is `evals`' rule
    and not a second one: a score from a run that fell over is not a score.
    """
    for run_id in reversed(runs_for_variant(variant_id)):
        report = evals.read(int(run_id), failures=0)
        if report.get("ok") and report.get("complete"):
            return report
    return None


def champion_of(line_id: int) -> dict[str, Any] | None:
    """The line's current champion row, or `None` before the first variant."""
    ensure_tables()
    with db.session() as connection:
        row = connection.execute(
            "SELECT * FROM prompt_champions WHERE line_id = ? ORDER BY id DESC LIMIT 1",
            (int(line_id),),
        ).fetchone()
    return None if row is None else dict(row)


def champions_of(line_id: int) -> list[dict[str, Any]]:
    """Every crowning this line has had, oldest first. The lineage."""
    ensure_tables()
    with db.session() as connection:
        rows = connection.execute(
            "SELECT * FROM prompt_champions WHERE line_id = ? ORDER BY id",
            (int(line_id),),
        ).fetchall()
    return [dict(row) for row in rows]


def crown(**columns: Any) -> dict[str, Any]:
    """Insert one `prompt_champions` row.

    THE ONLY WAY A WINNER IS EVER RECORDED, and it is deliberately dumb: it
    passes what it is given to SQLite and lets the `CHECK` decide. The
    significance test lives in `evals.compare`, the `improved > regressed` clause
    lives in `attempt`, and the constraint in
    `app/migrations/v009_a_prompt_is_a_version.py` is the floor underneath both -
    which is what makes it a floor and not a third opinion.
    """
    ensure_tables()
    names = sorted(columns)
    with db.session() as connection:
        cursor = connection.execute(
            "INSERT INTO prompt_champions (%s) VALUES (%s)"  # noqa: S608 - ours
            % (", ".join(names), ", ".join("?" for _ in names)),
            tuple(columns[name] for name in names),
        )
        row = connection.execute(
            "SELECT * FROM prompt_champions WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


# ---------------------------------------------------------------------------
# Reading two runs against each other. Every number is counted off rows
# `app/tools/evals.py` wrote; nothing here grades anything.


def paired(new_run: int, against_run: int) -> dict[str, Any]:
    """The rows BOTH runs graded, and the delta measured only on those.

    WHY THIS EXISTS WHEN `evals.compare` ALREADY REPORTS A DELTA. `compare`'s
    delta is the difference of two aggregate scores, which is right when both
    runs graded the same rows and misleading the moment they did not. Few-shot
    makes them not: the exemplars are held out of the challenger and were never
    held out of the champion, so the challenger's aggregate is over fewer rows
    and a different mix of them.

    The p-value needs no such correction - McNemar is already paired, over the
    intersection, and that is the whole reason a paired test is stronger than
    subtracting two aggregates.
    """
    new_rows = {row["row_index"]: row for row in evals.results_for(int(new_run))}
    old_rows = {row["row_index"]: row for row in evals.results_for(int(against_run))}
    shared = sorted(set(new_rows) & set(old_rows))
    new_correct = sum(1 for i in shared if new_rows[i]["correct"])
    old_correct = sum(1 for i in shared if old_rows[i]["correct"])
    new_score = (new_correct / len(shared)) if shared else None
    old_score = (old_correct / len(shared)) if shared else None
    return {
        "rows": len(shared),
        "row_indexes": shared,
        "correct": new_correct,
        "correct_against": old_correct,
        "score": new_score,
        "score_against": old_score,
        "delta": (
            None if new_score is None or old_score is None else new_score - old_score
        ),
        "only_this_run_graded": sorted(set(new_rows) - set(old_rows)),
        "only_the_other_graded": sorted(set(old_rows) - set(new_rows)),
        "measured_on": (
            "the rows both runs graded, which is the only set on which a "
            "difference between them means anything"
        ),
    }


def bucket_effect(
    bucket_rows: list[int],
    new_rows: dict[int, dict[str, Any]],
    mode: str,
) -> dict[str, Any]:
    """What a change did to ONE failure bucket, with what that bucket can resolve.

    Every row in a bucket FAILED in the run the bucket came from, so a change can
    only improve them. McNemar over `fixed` improvements and zero regressions is
    the exact test, and `CLEAN_SWEEP_ROWS` is the blunt fact that falls out of
    it: **under six rows, fixing every one of them still resolves nothing.**

    `rows_this_bucket_would_need` is the honest answer to "so what would it take"
    at the rate actually observed, searched against the same test rather than
    quoted from a rule of thumb.
    """
    fixed = [i for i in bucket_rows if new_rows[i]["correct"]]
    still = [i for i in bucket_rows if not new_rows[i]["correct"]]
    p_value = evals.mcnemar(len(fixed), 0)
    best_possible = evals.mcnemar(len(bucket_rows), 0)
    resolved = bool(fixed) and p_value <= RESOLUTION_ALPHA

    needed: int | None = None
    if fixed:
        rate = len(fixed) / len(bucket_rows)
        for size in range(len(bucket_rows), 512):
            if evals.mcnemar(math.floor(rate * size), 0) <= RESOLUTION_ALPHA:
                needed = size
                break

    if resolved:
        says = (
            f"{len(fixed)} of {len(bucket_rows)} {mode} rows are now correct "
            f"(McNemar exact p={p_value:.3g}). That is a real effect on this "
            "bucket."
        )
    elif not fixed:
        says = (
            f"None of the {len(bucket_rows)} {mode} rows changed. This bucket is "
            "untouched."
        )
    elif best_possible > RESOLUTION_ALPHA:
        says = (
            f"{len(fixed)} of {len(bucket_rows)} {mode} rows are now correct, and "
            f"NO EVIDENCE is the only honest reading: a bucket of "
            f"{len(bucket_rows)} rows could be fixed ENTIRELY and still only "
            f"reach p={best_possible:.3g}. It takes {CLEAN_SWEEP_ROWS} rows in a "
            "bucket before even a clean sweep of it resolves anything."
        )
    else:
        says = (
            f"NO EVIDENCE. {len(fixed)} of {len(bucket_rows)} {mode} rows are now "
            f"correct, which gives p={p_value:.3g} - inside the noise for a "
            "bucket this size."
            + (
                f" At that rate this bucket would need about {needed} rows to "
                "resolve."
                if needed
                else ""
            )
        )

    return {
        "mode": mode,
        "rows": len(bucket_rows),
        "fixed": len(fixed),
        "still_failing": len(still),
        "fixed_rows": fixed,
        "p_value": p_value,
        "resolved": resolved,
        "p_value_if_every_row_were_fixed": best_possible,
        "rows_a_clean_sweep_needs_to_resolve": CLEAN_SWEEP_ROWS,
        "rows_this_bucket_would_need": needed,
        "test": "McNemar, two-sided exact, over rows that were failing and are not",
        "says": says,
    }


def bucket_effects(new_run: int, against_run: int) -> dict[str, Any]:
    """Every failure bucket of `against_run`, and what `new_run` did to it.

    Keyed on the STORED per-row `failure_mode` of the run being beaten, which is
    the run whose failures a change was aimed at. `inconsistent` cannot appear -
    see `NOT_A_ROW_LOCAL_MODE` - and that absence is reported rather than left
    to be noticed.

    `collateral` is the other half and the half a target makes easy to miss: rows
    that were CORRECT before and are not now, grouped by how they fail now. An
    aggregate can sit still while a change fixes every format failure and breaks
    an equal number of factual ones, and those are opposite findings.
    """
    new_rows = {row["row_index"]: row for row in evals.results_for(int(new_run))}
    old_rows = {row["row_index"]: row for row in evals.results_for(int(against_run))}
    shared = set(new_rows) & set(old_rows)

    buckets: dict[str, list[int]] = {}
    for index in sorted(shared):
        mode = old_rows[index]["failure_mode"]
        if mode:
            buckets.setdefault(str(mode), []).append(index)

    broke: dict[str, list[int]] = {}
    for index in sorted(shared):
        if old_rows[index]["correct"] and not new_rows[index]["correct"]:
            broke.setdefault(str(new_rows[index]["failure_mode"] or "?"), []).append(
                index
            )

    return {
        "buckets": {
            mode: bucket_effect(rows, new_rows, mode)
            for mode, rows in sorted(buckets.items())
        },
        "collateral": {mode: rows for mode, rows in sorted(broke.items())},
        "collateral_rows": sum(len(rows) for rows in broke.values()),
        "measured_over": len(shared),
        "keyed_on": (
            f"the per-row failure_mode stored on eval run {int(against_run)}. "
            f"{', '.join(NOT_A_ROW_LOCAL_MODE)} cannot appear here: it is a "
            "property of two rows rather than one, so the eval bench derives it "
            "at report time and never stores it."
        ),
    }


# ---------------------------------------------------------------------------
# Few-shot. From the failures, never from the successes, and held out by
# construction rather than by a flag.


def choose_exemplars(
    run_id: int, count: int, *, mode: str | None = None
) -> dict[str, Any]:
    """Pick `count` exemplars from the FAILING rows of `run_id`.

    THREE RULES, and each one is a way this goes wrong quietly:

    **Failures, never successes.** `NO_TRAIN__FEW_SHOT` says so in the ledger and
    it is the part people get wrong. Exemplars drawn from what the model already
    gets right teach it nothing and inflate nothing except confidence.

    **Spread across buckets, in row order.** Without `mode=`, the choice
    round-robins across the failure modes present, so twenty refusals cannot
    crowd out the format failures. With `mode=`, it draws from one bucket
    deliberately, which is what aiming a change at a named failure means.

    **A truncated row is not an exemplar.** `evals` stores at most
    `STORED_TEXT_CHARS` per field and marks what it cut. Teaching from a cut-off
    expected answer teaches the cut-off answer. Skipped rows are counted and
    reported.

    The exemplar carries the row's EXPECTED answer, never the model's - it is an
    example of being right, and the model's reply on a failing row is by
    definition an example of being wrong.
    """
    rows = [row for row in evals.results_for(int(run_id)) if row["failure_mode"]]
    truncated = [
        row
        for row in rows
        if TRUNCATION_MARKER in str(row["input"])
        or TRUNCATION_MARKER in str(row["expected"])
    ]
    usable = [row for row in rows if row not in truncated]
    if mode:
        usable = [row for row in usable if str(row["failure_mode"]) == str(mode)]

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in sorted(usable, key=lambda r: r["row_index"]):
        groups.setdefault(str(row["failure_mode"]), []).append(row)

    chosen: list[dict[str, Any]] = []
    order = sorted(groups)
    while len(chosen) < count and any(groups[name] for name in order):
        for name in order:
            if not groups[name]:
                continue
            chosen.append(groups[name].pop(0))
            if len(chosen) >= count:
                break

    chosen.sort(key=lambda r: r["row_index"])
    return {
        "exemplars": [
            {
                "row_index": int(row["row_index"]),
                "input": row["input"],
                "expected": row["expected"],
                "failure_mode": row["failure_mode"],
            }
            for row in chosen
        ],
        "failing_rows_available": len(rows),
        "skipped_truncated": len(truncated),
        "drawn_from": (
            f"the {mode} failures of eval run {int(run_id)}"
            if mode
            else f"the failures of eval run {int(run_id)}, spread across buckets"
        ),
    }


def with_exemplars(base: str, exemplars: Iterable[dict[str, Any]]) -> str:
    """The prompt text a few-shot variant actually runs under.

    Written into the variant's stored `text`, so the row IS the prompt that ran
    and can be re-read, diffed and re-run without reconstructing anything.
    """
    blocks = [
        f"Input: {item['input']}\nCorrect answer: {item['expected']}"
        for item in exemplars
    ]
    return f"{str(base).rstrip()}\n\n{EXEMPLAR_PREAMBLE}\n\n" + "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# The attempt. No stamping here - see the module docstring - and no `Instrument`
# in the signature, so there is nothing to stamp with.


def _baseline_ruler(eval_path: str, expected_field: str, limit: int = 200) -> str:
    """The metric measure_baseline would choose for this file (`choose_metric`), or the bench default."""
    from app import dataquality
    from app.tools.measure import choose_metric

    values: list[Any] = []
    try:
        for record in dataquality.iter_records(str(eval_path)):
            if isinstance(record, dict) and expected_field in record:
                values.append(record[expected_field])
                if len(values) >= limit:
                    break
    except Exception:  # noqa: BLE001 - an unreadable file is refused later, by the run itself
        return evals.EXACT_MATCH
    return choose_metric(values)[0] if values else evals.EXACT_MATCH


def attempt(
    *,
    thread_id: int,
    line: str,
    eval_path: str,
    input_field: str,
    expected_field: str,
    prompt: str | None = None,
    change_note: str = "",
    targets: str | None = None,
    fewshot_from_failures: int = 0,
    metric: str | None = None,
    sample: int = evals.DEFAULT_EVAL_SAMPLE,
    latency_budget_ms: int | None = None,
    provider_id: int | None = None,
    deadline_seconds: float | None = evals.DEFAULT_DEADLINE_SECONDS,
    actor: str = evidence.MODEL,
) -> dict[str, Any]:
    """Store one prompt version, score it, and compare it to the one to beat.

    THE ORDER IS THE DESIGN. Everything that can refuse for free refuses before
    the model is asked anything: the conversation, the line's instrument, the
    target's name, an unchanged prompt, an exemplar request with no champion to
    draw from. Only then are the user's tokens spent, and only then is a row
    written.

    NO VERSION IS RECORDED WHEN THE RUN CANNOT START, which is why the variant
    is inserted AFTER `evals.run` returns rather than before. A variant with no
    run at all is not an attempt, it is a draft, and a bench full of drafts is
    the text editor this module exists not to be. The LINE may be opened by a
    call that then fails to run - an empty line is a name and a pinned
    instrument, it claims nothing, and it is what the retry adds to.
    """
    if thread_id is None:
        return {
            "ok": False,
            "error": "no_thread",
            "detail": (
                "A prompt line belongs to one conversation: its variants, its "
                "eval runs and its champion are all thread-scoped, for the same "
                "reason a fact is."
            ),
            **evidence.thread_id_help("try_prompt"),
        }
    if not evidence.names_a_conversation(thread_id):
        return {
            "ok": False,
            "error": "no_such_thread",
            "detail": (
                f"There is no conversation {thread_id!r} on this machine, so there "
                "is nowhere to file this attempt. Nothing was asked and nothing "
                "was spent."
            ),
        }

    name = str(line).strip()
    if not name:
        return {
            "ok": False,
            "error": "no_line",
            "detail": (
                "A prompt bench needs a name for the line of descent it is adding "
                "to, because every comparison it makes is against the line's "
                "current champion. Call it after the job the prompt does."
            ),
        }

    existing = line_named(int(thread_id), name)
    if metric is None:
        # A metric left unsaid on an OPEN line means the line's own metric, not
        # the bench default. The old default was `exact_match` whatever the
        # line graded with, so a second version asked for with no metric was
        # refused as a different instrument - correctly, and uselessly: the
        # caller had not chosen a different instrument, they had chosen none.
        # A line that does not exist yet still opens on the bench default.
        # A NEW line takes the ruler measure_baseline takes on the same file.
        # It used to open on exact_match whatever the answers were, so on JSON
        # records a prompt bench scored 0 on a different metric from the
        # baseline beside it (adapter run 1, 2026-09-23: fields 4.8% read as
        # exact_match 0%), and nothing said which ruler either used.
        metric = str(existing["metric"]) if existing is not None else _baseline_ruler(eval_path, expected_field)
    metric = str(metric)
    if metric not in evals.METRICS:
        return {
            "ok": False,
            "error": "unknown_metric",
            "detail": (
                f"{metric!r} is not a metric the eval bench has. It grades with "
                f"{', '.join(evals.METRICS)}."
            ),
            "metrics": list(evals.METRICS),
        }

    if existing is None:
        try:
            record = create_line(
                thread_id=int(thread_id),
                name=name,
                eval_path=str(eval_path),
                input_field=str(input_field),
                expected_field=str(expected_field),
                metric=metric,
                sample=max(1, min(int(sample), evals.MAX_EVAL_SAMPLE)),
                latency_budget_ms=(
                    None if latency_budget_ms is None else int(latency_budget_ms)
                ),
            )
        except (ValueError, TypeError, sqlite3.IntegrityError) as error:
            # `int()` on a `sample` or a budget that is not a number, and the
            # UNIQUE (thread_id, name) losing a race with a second call. Both
            # mean the same thing to a caller: no line was opened, so nothing was
            # asked and nothing was spent.
            return {
                "ok": False,
                "error": "bad_line",
                "detail": f"That line could not be opened: {error}",
            }
    else:
        record = existing
        drift = _instrument_drift(
            record,
            eval_path=eval_path,
            input_field=input_field,
            expected_field=expected_field,
            metric=metric,
        )
        if drift:
            return drift

    champion = champion_of(int(record["id"]))
    champion_variant = (
        get_variant(int(champion["variant_id"])) if champion is not None else None
    )
    champion_run = (
        scoring_run(int(champion["variant_id"])) if champion is not None else None
    )

    target = None
    if targets:
        target = str(targets).strip()
        refusal = _check_target(target)
        if refusal:
            return refusal

    wanted = max(0, min(int(fewshot_from_failures or 0), MAX_EXEMPLARS))
    if wanted and champion_run is None:
        # CHECKED BEFORE THE BASE PROMPT IS RESOLVED, so the refusal names the
        # thing that is missing. A caller who asked for exemplars and has no
        # scored run is not short of a prompt, they are short of failures, and
        # "send me a prompt" would send them the wrong way.
        return {
            "ok": False,
            "error": "no_failures_to_learn_from",
            "detail": (
                "Few-shot exemplars are chosen from the eval FAILURES, and "
                f"{name!r} has no completed run to take them from yet. Score a "
                "prompt first; its failures are the material."
            ),
        }

    base = str(prompt) if prompt is not None else None
    if base is None:
        if champion_variant is None:
            return {
                "ok": False,
                "error": "no_prompt",
                "detail": (
                    f"There is no prompt to change: {name!r} has no variants yet, "
                    "so there is nothing to build on and nothing to beat. Send the "
                    "prompt you want scored."
                ),
            }
        base = str(champion_variant["text"])

    exemplars: list[dict[str, Any]] = []
    fewshot: dict[str, Any] | None = None
    if wanted:
        fewshot = choose_exemplars(
            int(champion_run["run_id"]), wanted, mode=target or None
        )
        exemplars = fewshot["exemplars"]
        if not exemplars:
            return {
                "ok": False,
                "error": "no_failures_to_learn_from",
                "detail": (
                    "There are no failing rows to draw exemplars from"
                    + (f" in the {target} bucket" if target else "")
                    + f" of eval run {champion_run['run_id']}"
                    + (
                        f"; {fewshot['skipped_truncated']} failing row(s) were "
                        "skipped because the eval bench had to truncate their "
                        "stored text, and a truncated exemplar teaches a "
                        "truncated answer."
                        if fewshot["skipped_truncated"]
                        else "."
                    )
                ),
                "fewshot": fewshot,
            }

    text = with_exemplars(base, exemplars) if exemplars else str(base)

    already = variant_with_text(int(record["id"]), text)
    if already is not None and scoring_run(int(already["id"])) is not None:
        return {
            "ok": False,
            "error": "nothing_changed",
            "detail": (
                f"That is byte for byte version {already['version']} of "
                f"{name!r}, which has already been scored on this eval set. "
                "Nothing was asked and nothing was spent. Change the prompt, or "
                "read the bench to see what version "
                f"{already['version']} scored."
            ),
            "line_id": int(record["id"]),
            "variant_id": int(already["id"]),
            "version": int(already["version"]),
        }
    # A VERSION WHOSE RUN NEVER FINISHED IS NOT A DUPLICATE, IT IS UNFINISHED.
    # Refusing it here would make "run this again with the same arguments and it
    # continues" - the eval bench's own promise, and the only thing that makes an
    # interruption cheap - unreachable through this door.
    resuming = already

    held = tuple(sorted(int(item["row_index"]) for item in exemplars))
    report = evals.run(
        eval_path=str(record["eval_path"]),
        input_field=str(record["input_field"]),
        expected_field=str(record["expected_field"]),
        thread_id=int(thread_id),
        prompt=text,
        metric=str(record["metric"]),
        sample=int(record["sample"]),
        provider_id=provider_id,
        latency_budget_ms=record["latency_budget_ms"],
        hold_out=held,
        deadline_seconds=deadline_seconds,
        actor=actor,
    )
    resumable = bool(report.get("resumable")) and report.get("run_id") is not None
    if not report.get("ok") and not resumable:
        report["nothing_was_recorded"] = (
            "No prompt version was stored. A variant with no eval run behind it "
            "is a draft, and a bench of drafts is a text editor."
        )
        return report

    if resuming is not None:
        variant = resuming
    else:
        try:
            variant = create_variant(
                line_id=int(record["id"]),
                version=len(variants_in(int(record["id"]))) + 1,
                parent_id=(
                    int(champion_variant["id"])
                    if champion_variant is not None
                    else None
                ),
                text=text,
                text_sha=_sha(text),
                change_note=str(change_note or ""),
                targets=target,
                exemplars_json=json.dumps(list(held)),
                author=str(actor),
            )
        except sqlite3.IntegrityError as error:
            # The uniqueness check above is a read and this is the write, so a
            # second call in flight between them lands here. The eval run it just
            # finished is on disk and reusable, so nothing is lost - only the row.
            return {
                "ok": False,
                "error": "nothing_changed",
                "detail": (
                    f"That prompt is already a version of {name!r} - two calls "
                    f"stored it at once ({error}). The eval run is on disk and "
                    "its rows are kept; read the bench to see what it scored."
                ),
                "line_id": int(record["id"]),
                "run_id": int(report["run_id"]),
            }
    record_score(int(variant["id"]), int(report["run_id"]))

    payload = _assemble(
        line=record,
        variant=variant,
        report=report,
        champion=champion,
        champion_variant=champion_variant,
        champion_run=champion_run,
        fewshot=fewshot,
        target=target,
        requested=wanted,
    )
    _emit(
        payload["event"],
        thread_id,
        {
            "line": name,
            "variant_id": int(variant["id"]),
            "version": int(variant["version"]),
            "run_id": int(report["run_id"]),
            "verdict": payload["verdict"],
        },
    )
    return payload


def _instrument_drift(
    line: dict[str, Any],
    *,
    eval_path: str,
    input_field: str,
    expected_field: str,
    metric: str,
) -> dict[str, Any] | None:
    """Refuse a variant measured with a different instrument from its siblings.

    THE LINE PINS THE INSTRUMENT, and this is where that is enforced. Two prompts
    graded by different metrics, or against different columns, were never
    comparable - and unlike a changed eval FILE, which `evals.compare` catches by
    fingerprint, a changed METRIC produces two perfectly valid runs over the same
    fingerprint whose scores mean different things. Nothing downstream would
    notice.
    """
    mismatched = {
        field: (line[field], supplied)
        for field, supplied in (
            ("eval_path", str(eval_path)),
            ("input_field", str(input_field)),
            ("expected_field", str(expected_field)),
            ("metric", str(metric)),
        )
        if str(line[field]) != supplied
    }
    if not mismatched:
        return None
    return {
        "ok": False,
        "error": "different_instrument",
        "detail": (
            f"{line['name']!r} scores every prompt on {line['eval_path']} "
            f"({line['input_field']} -> {line['expected_field']}), graded by "
            f"{line['metric']}. This call asked for "
            + ", ".join(
                f"{field}={supplied!r} instead of {held!r}"
                for field, (held, supplied) in sorted(mismatched.items())
            )
            + ". Two prompts measured with different instruments were never "
            "comparable, so nothing was asked and nothing was spent. Open a new "
            "line for the new measurement."
        ),
        "line_id": int(line["id"]),
        "mismatched": {
            field: {"line": held, "requested": supplied}
            for field, (held, supplied) in sorted(mismatched.items())
        },
    }


def _check_target(target: str) -> dict[str, Any] | None:
    """Is `target` a failure mode a bucket report could ever be keyed on?"""
    if target in NOT_A_ROW_LOCAL_MODE:
        return {
            "ok": False,
            "error": "not_a_row_local_mode",
            "detail": (
                f"{target!r} is a real failure mode and it cannot be aimed at "
                "here. It is the same input answered two different ways, which is "
                "a property of a PAIR of rows: the eval bench derives it when it "
                "reports and never stores it against a row, so there is no bucket "
                "of rows to measure a change against. Aim at a mode a single row "
                "can be in."
            ),
            "modes": sorted(set(evals.routable_modes()) - set(NOT_A_ROW_LOCAL_MODE)),
        }
    known = set(evals.routable_modes()) | {evals.UNCLASSIFIED}
    if target not in known:
        return {
            "ok": False,
            "error": "unknown_failure_mode",
            "detail": (
                f"{target!r} is not a failure mode this harness buckets into. The "
                "modes come from the diagnosis engine's own router, not from a "
                "list in this file."
            ),
            "modes": sorted(known - set(NOT_A_ROW_LOCAL_MODE)),
        }
    return None


def _assemble(
    *,
    line: dict[str, Any],
    variant: dict[str, Any],
    report: dict[str, Any],
    champion: dict[str, Any] | None,
    champion_variant: dict[str, Any] | None,
    champion_run: dict[str, Any] | None,
    fewshot: dict[str, Any] | None,
    target: str | None,
    requested: int = 0,
) -> dict[str, Any]:
    """The report, and the ONE place a champion is ever crowned.

    Four outcomes and they are exhaustive:

    * **incomplete** - the run stopped. No score, no comparison, no crowning, and
      the graded rows are on disk so running it again continues.
    * **first** - nothing to beat. Crowned on `basis='first'`, which the migration
      forbids from carrying any comparison figure at all.
    * **different** - `evals.compare` resolved it AND more rows improved than
      regressed. Crowned on `basis='resolved'` with the counts and the p-value,
      which is the only shape the `CHECK` admits.
    * **no_evidence** - anything else, including a resolved REGRESSION, which is
      information and is not a crowning.
    """
    base: dict[str, Any] = {
        "ok": True,
        "line": {
            "id": int(line["id"]),
            "name": line["name"],
            "eval_path": line["eval_path"],
            "input_field": line["input_field"],
            "expected_field": line["expected_field"],
            "metric": line["metric"],
            "sample": int(line["sample"]),
        },
        "variant": {
            "id": int(variant["id"]),
            "version": int(variant["version"]),
            "parent_id": variant["parent_id"],
            "text": variant["text"],
            "change_note": variant["change_note"],
            "targets": variant["targets"],
            "exemplars": variant["exemplars"],
            "author": variant["author"],
        },
        "run_id": int(report["run_id"]),
        "complete": bool(report["complete"]),
        "reused": bool(report.get("reused")),
        "score": report.get("score"),
        "scores": report.get("scores"),
        "model": report.get("model"),
        "resolution": report.get("resolution"),
        "failure_histogram": report.get("failure_histogram"),
        "unclassified": report.get("unclassified"),
        "eval_summary": report.get("summary"),
        "champion_changed": False,
        "measured_nothing": (
            "No fact was stamped. This bench cannot: it declares measures=(), so "
            "the instrument it is handed can mint nothing at all. In particular a "
            "prompt that wins is not a measurement of anything the diagnosis "
            "engine reads."
        ),
    }
    if fewshot:
        base["fewshot"] = {
            "requested": int(requested),
            "chosen_count": len(variant["exemplars"]),
            "chosen": fewshot["exemplars"],
            "drawn_from": fewshot["drawn_from"],
            "failing_rows_available": fewshot["failing_rows_available"],
            "skipped_truncated": fewshot["skipped_truncated"],
            "held_out_of_the_score": list(variant["exemplars"]),
            "why_held_out": (
                "Scoring a prompt on the rows it was given as examples is a leak. "
                "These rows are out of this run's score, and out of every "
                "comparison against it, because a paired comparison only uses "
                "rows both runs graded."
            ),
            "engine_asks_for": ENGINE_ASKS_FOR_EXEMPLARS,
            "note": (
                f"The engine's own instruction is 5-20 exemplars; this variant "
                f"carries {len(variant['exemplars'])}."
                if len(variant["exemplars"]) < ENGINE_ASKS_FOR_EXEMPLARS
                else ""
            ),
        }

    if not report["complete"]:
        # `ok` FOLLOWS THE RUN AND NOT THE BOOKKEEPING. The version is stored and
        # its graded rows are on disk, which is worth reporting - but a caller
        # who sees `ok: true` reads it as "this was scored", and a prefix of the
        # file is not a sample of it. `evals` already answers this way for the
        # same reason; answering differently here would be a second answer.
        base["ok"] = False
        base["error"] = report.get("error", "incomplete")
        base["resumable"] = True
        base["verdict"] = "incomplete"
        base["event"] = TRIED
        base["says"] = (
            f"Version {variant['version']} of {line['name']!r} graded "
            f"{report['graded']} of {report['planned']} rows and stopped. It has "
            "no score, so it has not been compared to anything and cannot become "
            "the one to beat. The version is stored and every graded row is on "
            "disk; try it again with the same arguments and it continues."
        )
        base["summary"] = base["says"]
        return base

    if champion is not None and (champion_variant is None or champion_run is None):
        # A CROWNED VARIANT WITH NO COMPLETE RUN IS A STATE THIS CODE CANNOT
        # PRODUCE, and the honest response to reaching it is to compare nothing
        # rather than to fall through to the `first` branch. Falling through
        # would crown this variant on `basis='first'` - a second winner with no
        # evidence, admitted by the constraint because it claims none. That is
        # the hole the whole table exists to close, reached by an `or`.
        base["verdict"] = "not_comparable"
        base["event"] = NO_EVIDENCE
        base["says"] = (
            f"{line['name']!r} has a recorded best prompt whose eval run can no "
            "longer be read, so there is nothing to compare this version "
            "against. Its rows are kept and nothing was crowned."
        )
        base["summary"] = base["says"]
        return base

    if champion is None:
        crowned = crown(
            line_id=int(line["id"]),
            variant_id=int(variant["id"]),
            run_id=int(report["run_id"]),
            basis="first",
        )
        base["verdict"] = "first"
        base["event"] = ADOPTED
        base["champion_changed"] = True
        base["champion"] = _champion_view(crowned, variant)
        base["says"] = (
            f"Version {variant['version']} of {line['name']!r} scores "
            f"{report['score']:.0%} on {report['graded']} rows. There was nothing "
            "to beat, so it is the one to beat - not because it is good, but "
            f"because it is first. {report['resolution']['says']}"
        )
        base["summary"] = base["says"]
        return base

    base["against"] = {
        "variant_id": int(champion_variant["id"]),
        "version": int(champion_variant["version"]),
        "run_id": int(champion_run["run_id"]),
        "score": champion_run.get("score"),
        "model": champion_run.get("model"),
    }

    if str(report.get("model")) != str(champion_run.get("model")):
        base["verdict"] = "different_models"
        base["event"] = NO_EVIDENCE
        base["says"] = (
            f"Version {variant['version']} scored {report['score']:.0%} against "
            f"{report['model']}, and version {champion_variant['version']} scored "
            f"{champion_run['score']:.0%} against {champion_run['model']}. Those "
            "are two different models, so the difference between them is not a "
            "fact about the prompt and is not reported as one. The version is "
            "stored and its rows are kept; re-score the champion on this model "
            "and ask again."
        )
        base["summary"] = base["says"]
        return base

    comparison = evals.compare(int(report["run_id"]), int(champion_run["run_id"]))
    base["comparison"] = comparison
    if not comparison.get("ok"):
        base["verdict"] = "not_comparable"
        base["event"] = NO_EVIDENCE
        base["says"] = comparison.get("detail") or comparison.get("error")
        base["summary"] = base["says"]
        return base

    pairing = paired(int(report["run_id"]), int(champion_run["run_id"]))
    if not pairing["rows"]:
        # NO SHARED ROW MEANS NO COMPARISON, and `evals.compare` reports this as
        # "not one of the 0 rows changed", which is true and reads like a
        # finding. It is not one: two runs that graded disjoint rows have not
        # been compared at all.
        base["paired"] = pairing
        base["verdict"] = "not_comparable"
        base["event"] = NO_EVIDENCE
        base["says"] = (
            f"Version {variant['version']} and version "
            f"{champion_variant['version']} have no graded row in common, so "
            "there is nothing to pair and no difference to report. Score them "
            "over the same rows and ask again."
        )
        base["summary"] = base["says"]
        return base
    effects = bucket_effects(int(report["run_id"]), int(champion_run["run_id"]))
    base["paired"] = pairing
    base["bucket_effects"] = effects
    if target:
        base["targeted"] = effects["buckets"].get(target) or {
            "mode": target,
            "rows": 0,
            "fixed": 0,
            "resolved": False,
            "says": (
                f"Version {champion_variant['version']} had no {target} failures "
                "on the rows both runs graded, so a change aimed at that bucket "
                "has nothing here to have fixed."
            ),
        }

    improved = int(comparison["improved"])
    regressed = int(comparison["regressed"])
    won = bool(comparison["resolved"]) and improved > regressed

    if won:
        crowned = crown(
            line_id=int(line["id"]),
            variant_id=int(variant["id"]),
            beat_variant_id=int(champion_variant["id"]),
            run_id=int(report["run_id"]),
            beat_run_id=int(champion_run["run_id"]),
            basis="resolved",
            paired_rows=int(comparison["paired_rows"]),
            improved=improved,
            regressed=regressed,
            delta=float(pairing["delta"]) if pairing["delta"] is not None else None,
            p_value=float(comparison["p_value"]),
        )
        base["verdict"] = "better"
        base["event"] = ADOPTED
        base["champion_changed"] = True
        base["champion"] = _champion_view(crowned, variant)
    elif comparison["resolved"]:
        base["verdict"] = "worse"
        base["event"] = NO_EVIDENCE
    else:
        base["verdict"] = "no_evidence"
        base["event"] = NO_EVIDENCE

    base["says"] = _says(
        line=line,
        variant=variant,
        report=report,
        champion_variant=champion_variant,
        comparison=comparison,
        pairing=pairing,
        effects=effects,
        target=target,
        verdict=base["verdict"],
    )
    base["summary"] = base["says"]
    return base


def _champion_view(row: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
    return {
        "variant_id": int(row["variant_id"]),
        "version": int(variant["version"]),
        "basis": row["basis"],
        "beat_variant_id": row["beat_variant_id"],
        "paired_rows": row["paired_rows"],
        "improved": row["improved"],
        "regressed": row["regressed"],
        "delta": row["delta"],
        "p_value": row["p_value"],
        "recorded_because": (
            "there was nothing to beat"
            if row["basis"] == "first"
            else (
                "the paired test resolved the difference and more rows improved "
                "than regressed - the only shape prompt_champions accepts"
            )
        ),
    }


def _says(
    *,
    line: dict[str, Any],
    variant: dict[str, Any],
    report: dict[str, Any],
    champion_variant: dict[str, Any],
    comparison: dict[str, Any],
    pairing: dict[str, Any],
    effects: dict[str, Any],
    target: str | None,
    verdict: str,
) -> str:
    """The badge sentence `docs/PRODUCT_SPEC.md` §6.5 specifies, and its refusal.

    The spec's shape is *score after vs score before on n items, resolution
    plus-or-minus points*. What is added is the paired score when it differs from
    the aggregate, because with few-shot it always does and the aggregate would
    be the misleading half.
    """
    resolution = report["resolution"]
    head = (
        f"v{variant['version']} {pairing['score']:.0%} vs "
        f"v{champion_variant['version']} {pairing['score_against']:.0%} on "
        f"{pairing['rows']} paired rows "
        f"(+-{resolution['half_width_points']:.1f} points at n={resolution['n']})."
    )
    if pairing["only_the_other_graded"] or pairing["only_this_run_graded"]:
        head += (
            f" Measured on the {pairing['rows']} rows both runs graded: "
            f"{len(pairing['only_the_other_graded'])} row(s) this run held out as "
            "exemplars and "
            f"{len(pairing['only_this_run_graded'])} row(s) the other did not "
            "grade are excluded from both sides. The aggregate difference of "
            f"{comparison['delta']:+.1%} below is over two different row sets and "
            "is NOT the number to read."
        )

    if verdict == "better":
        body = (
            f" {comparison['improved']} rows improved and "
            f"{comparison['regressed']} regressed, McNemar exact "
            f"p={comparison['p_value']:.3g}. This is a real difference on this "
            f"eval set, so v{variant['version']} is now the one to beat."
        )
    elif verdict == "worse":
        body = (
            f" {comparison['improved']} rows improved and "
            f"{comparison['regressed']} regressed, McNemar exact "
            f"p={comparison['p_value']:.3g}. This is a real difference and it is "
            f"the wrong way: v{champion_variant['version']} stays the one to beat."
        )
    else:
        body = " " + comparison["says"]

    tail = ""
    if target:
        bucket = effects["buckets"].get(target)
        tail = " " + (
            bucket["says"]
            if bucket
            else (
                f"There were no {target} failures to fix on the rows both runs "
                "graded."
            )
        )
    if effects["collateral_rows"]:
        tail += (
            f" It also broke {effects['collateral_rows']} row(s) that were "
            "correct before: "
            + ", ".join(
                f"{mode} {len(rows)}"
                for mode, rows in sorted(effects["collateral"].items())
            )
            + "."
        )
    return head + body + tail


def _emit(kind: str, thread_id: int | None, payload: dict[str, Any]) -> None:
    """One frame onto the append-only spine, best effort.

    Best effort for `evals._emit`'s reason: a failure to narrate must never lose
    a recorded attempt. The durable record is the three tables; the event is how
    the conversation watches it happen.
    """
    if thread_id is None:
        return
    try:
        events.append(kind, payload, thread_id=int(thread_id))
    except Exception:  # noqa: BLE001 - narration must not cost a record
        pass


# ---------------------------------------------------------------------------
# Reading a bench back. Costs nothing and asks the model nothing.


def read_line(line_id: int) -> dict[str, Any]:
    """One prompt line, every version, and what each one scored.

    Reads only this module's tables and `app/tools/evals.py`'s. No score is
    stored here, so every number below is read back through `evals.read` from the
    run that produced it - which is what makes it impossible for this view to
    disagree with the eval bench.
    """
    line = get_line(line_id)
    if line is None:
        return {"ok": False, "error": "no_such_line", "line_id": int(line_id)}

    champion = champion_of(int(line["id"]))
    versions = []
    for variant in variants_in(int(line["id"])):
        scored = scoring_run(int(variant["id"]))
        versions.append(
            {
                "variant_id": int(variant["id"]),
                "version": int(variant["version"]),
                "parent_id": variant["parent_id"],
                "change_note": variant["change_note"],
                "targets": variant["targets"],
                "exemplars": variant["exemplars"],
                "author": variant["author"],
                "text": variant["text"],
                "created_at": variant["created_at"],
                "runs": runs_for_variant(int(variant["id"])),
                "run_id": None if scored is None else int(scored["run_id"]),
                "score": None if scored is None else scored.get("score"),
                "graded": None if scored is None else scored.get("graded"),
                "model": None if scored is None else scored.get("model"),
                "resolution": None if scored is None else scored.get("resolution"),
                "failure_histogram": (
                    None if scored is None else scored.get("failure_histogram")
                ),
                "is_champion": (
                    champion is not None
                    and int(champion["variant_id"]) == int(variant["id"])
                ),
            }
        )

    return {
        "ok": True,
        "line": {
            "id": int(line["id"]),
            "thread_id": int(line["thread_id"]),
            "name": line["name"],
            "eval_path": line["eval_path"],
            "input_field": line["input_field"],
            "expected_field": line["expected_field"],
            "metric": line["metric"],
            "sample": int(line["sample"]),
            "latency_budget_ms": line["latency_budget_ms"],
            "created_at": line["created_at"],
        },
        "versions": versions,
        "champion": (
            None
            if champion is None
            else {
                "variant_id": int(champion["variant_id"]),
                "basis": champion["basis"],
                "beat_variant_id": champion["beat_variant_id"],
                "paired_rows": champion["paired_rows"],
                "improved": champion["improved"],
                "regressed": champion["regressed"],
                "delta": champion["delta"],
                "p_value": champion["p_value"],
            }
        ),
        "lineage": champions_of(int(line["id"])),
        "how_a_champion_is_recorded": (
            "A version becomes the one to beat only when the paired McNemar test "
            f"over the rows both runs graded returns p <= {RESOLUTION_ALPHA} AND "
            "more rows improved than regressed. That is a CHECK on the table in "
            "app/migrations/v009_a_prompt_is_a_version.py, not a rule in code: an "
            "unresolvable winner cannot be written here by any path."
        ),
    }


# ---------------------------------------------------------------------------
# The two tools. Both declare measures=() - see the module docstring - so the
# instrument they are handed can mint nothing at all.


@tool(
    "try_prompt",
    description=(
        "Change the system prompt and find out whether it actually got better. "
        "Stores the new prompt as a numbered version of a named prompt line, "
        "scores it on the eval set that line is pinned to, and compares it "
        "PAIRWISE against the current best - and when the eval set cannot tell "
        "the two apart it says NO EVIDENCE in those words, with the number of "
        "rows that would be needed, rather than reporting a small win. Aim a "
        "change at a named failure bucket with `targets` and it reports what "
        "happened to that bucket as well as to the total. `fewshot_from_failures` "
        "builds the prompt's examples from the rows the model got WRONG and holds "
        "those rows out of the score, because scoring on your own exemplars is a "
        "leak. This is what the verdict 'do not train, fix the prompt' turns into "
        "when the product actually does it."
    ),
    schema={
        "type": "object",
        "properties": {
            "line": {
                "type": "string",
                "description": (
                    "The name of the prompt line to add this version to. A new "
                    "name opens a new line; an existing one adds a version and "
                    "compares it against that line's current best. Name it after "
                    "the job the prompt does."
                ),
            },
            "eval_path": {
                "type": "string",
                "description": "The evaluation file this line is scored on.",
            },
            "input_field": {
                "type": "string",
                "description": "The column holding the input to send to the model.",
            },
            "expected_field": {
                "type": "string",
                "description": "The column holding the answer that would be right.",
            },
            "prompt": {
                "type": "string",
                "description": (
                    "The system prompt to score. Leave it out only when "
                    "fewshot_from_failures is set, in which case the current best "
                    "prompt is the base the examples are added to."
                ),
            },
            "change_note": {
                "type": "string",
                "description": (
                    "What you changed and why, in a sentence. It is stored with "
                    "the version and it is what makes the history readable later."
                ),
            },
            "targets": {
                "type": "string",
                "description": (
                    "The failure bucket this change is aimed at - the engine's own "
                    "modes, such as wrong_format or refuses. The reply reports "
                    "what happened to that bucket specifically, including whether "
                    "a bucket that size could resolve anything at all."
                ),
            },
            "fewshot_from_failures": {
                "type": "integer",
                "description": (
                    f"Build up to this many worked examples (max {MAX_EXEMPLARS}) "
                    "from the rows the current best prompt got WRONG, and hold "
                    "those rows out of the score. Examples chosen from successes "
                    "teach nothing; scoring on your own examples is a leak."
                ),
            },
            "metric": {
                "type": "string",
                "enum": list(evals.METRICS),
                "description": (
                    "How a row is graded, fixed for the whole line when it is "
                    "opened. Two prompts graded by different metrics were never "
                    "comparable. Left out on an open line it means the line's "
                    "own metric; on a new line it means the metric measure_baseline "
                    "would choose for the same answers (fields for JSON records)."
                ),
            },
            "sample": {
                "type": "integer",
                "description": (
                    f"How many rows to grade, fixed for the whole line when it is "
                    f"opened. Default {evals.DEFAULT_EVAL_SAMPLE}, maximum "
                    f"{evals.MAX_EVAL_SAMPLE}."
                ),
            },
            "latency_budget_ms": {
                "type": "integer",
                "description": (
                    "A per-row time budget, fixed for the whole line. Without one "
                    "no row is ever bucketed too_slow."
                ),
            },
            "provider_id": {
                "type": "integer",
                "description": "Which connection to score against. Default: active.",
            },
            "deadline_seconds": {
                "type": "number",
                "description": (
                    "Stop cleanly after this long. Every graded row is kept and "
                    "calling this again with the same arguments continues."
                ),
            },
        },
        "required": ["line", "eval_path", "input_field", "expected_field"],
    },
    reads=("filesystem", "datasets", "providers", "evals", "prompts"),
    writes=("evals", "prompts"),
    provides=("prompt.attempt.score",),
    label="Try a prompt",
    group="Data",
    verb="score a prompt change against the eval set",
    order=25,
)
def try_prompt(
    line: str,
    eval_path: str,
    input_field: str,
    expected_field: str,
    prompt: str | None = None,
    change_note: str = "",
    targets: str | None = None,
    fewshot_from_failures: int = 0,
    metric: str | None = None,
    sample: int = evals.DEFAULT_EVAL_SAMPLE,
    latency_budget_ms: int | None = None,
    provider_id: int | None = None,
    deadline_seconds: float | None = evals.DEFAULT_DEADLINE_SECONDS,
    *,
    instrument: Instrument,
) -> dict[str, Any]:
    """Run the attempt in this conversation. Stamps nothing, and cannot.

    `measures=()` is a structural property checked at registration, so the
    instrument handed here can mint no fact whatever a future edit to this body
    tries. That is the answer to "should a winner be recorded MEASURED when the
    delta is inside the noise": there is no path by which a winner is recorded as
    a fact at all, resolvable or not.

    The instrument is taken for `thread_id` and `actor`. `actor` matters: it is
    what `evals.run` checks before it will send somebody's eval rows to a remote
    endpoint, and a model asking is not the user asking.
    """
    return attempt(
        thread_id=instrument.thread_id,
        line=line,
        eval_path=eval_path,
        input_field=input_field,
        expected_field=expected_field,
        prompt=prompt,
        change_note=change_note,
        targets=targets,
        fewshot_from_failures=fewshot_from_failures,
        metric=metric,
        sample=sample,
        latency_budget_ms=latency_budget_ms,
        provider_id=provider_id,
        deadline_seconds=deadline_seconds,
        actor=instrument.actor,
    )


@tool(
    "read_prompt_bench",
    description=(
        "Read the prompt lines in this conversation: every version tried, what "
        "changed, what each one scored with its resolution, and which one is "
        "currently the one to beat and on what evidence. Costs nothing and asks "
        "the model nothing."
    ),
    schema={
        "type": "object",
        "properties": {
            "line_id": {
                "type": "integer",
                "description": (
                    "Which line to read in full. Leave it out to list the lines "
                    "in this conversation, newest first."
                ),
            },
            "line": {
                "type": "string",
                "description": "The line's name, as an alternative to line_id.",
            },
        },
    },
    reads=("evals", "prompts"),
    writes=(),
    provides=("prompt.bench.read",),
    label="Read the prompt bench",
    group="Data",
    verb="read what the prompt attempts actually scored",
    order=26,
)
def read_prompt_bench(
    line_id: int | None = None,
    line: str | None = None,
    *,
    instrument: Instrument,
) -> dict[str, Any]:
    """List or read - and only within this conversation.

    THE THREAD IS REQUIRED EVEN THOUGH THE ROUTE DOES NOT DEMAND IT, for
    `read_eval_results`' reason exactly: this tool has no `measures=` and no
    `writes=` a fact, so `evidence.thread_is_required_by` would not ask for one -
    and served with no thread it would serve every conversation's prompts and
    scores. That is the eval-set leak in a smaller shape, so the direction to
    fail in is closed here rather than reasoned about.
    """
    if instrument.thread_id is None:
        return {
            "ok": False,
            "error": "no_thread",
            "detail": (
                "read_prompt_bench reads the prompt lines of ONE conversation, "
                "and this call did not say which. A prompt line belongs to the "
                "conversation it was measured in, for the same reason a fact does."
            ),
            **evidence.thread_id_help("read_prompt_bench"),
        }

    if line_id is None and line:
        named = line_named(int(instrument.thread_id), str(line))
        if named is None:
            return {
                "ok": False,
                "error": "no_such_line",
                "detail": (
                    f"There is no prompt line named {str(line)!r} in this "
                    "conversation."
                ),
                "lines": [row["name"] for row in lines_in(int(instrument.thread_id))],
            }
        line_id = int(named["id"])

    if line_id is None:
        rows = lines_in(int(instrument.thread_id))
        return {
            "ok": True,
            "count": len(rows),
            "lines": [
                {
                    "line_id": int(row["id"]),
                    "name": row["name"],
                    "eval_path": row["eval_path"],
                    "metric": row["metric"],
                    "sample": int(row["sample"]),
                    "variants": int(row["variants"]),
                    "created_at": row["created_at"],
                }
                for row in rows
            ],
        }

    # OWNERSHIP IS CHECKED BEFORE ANYTHING IS READ. A line id from another
    # conversation would report that conversation's prompts, scores and failing
    # rows into this one, which is the leak by a longer route.
    owned = get_line(int(line_id))
    if owned is None or int(owned["thread_id"]) != int(instrument.thread_id):
        return {
            "ok": False,
            "error": "no_such_line",
            "line_id": int(line_id),
            "detail": (
                f"There is no prompt line {int(line_id)} in this conversation. "
                "Lines belong to the conversation they were measured in, for the "
                "same reason facts do."
            ),
        }
    return read_line(int(line_id))


__all__ = [
    "CLEAN_SWEEP_ROWS",
    "ENGINE_ASKS_FOR_EXEMPLARS",
    "MAX_EXEMPLARS",
    "NOT_A_ROW_LOCAL_MODE",
    "RESOLUTION_ALPHA",
    "TRUNCATION_MARKER",
    "attempt",
    "bucket_effect",
    "bucket_effects",
    "champion_of",
    "champions_of",
    "choose_exemplars",
    "create_line",
    "create_variant",
    "crown",
    "ensure_tables",
    "get_line",
    "get_variant",
    "line_named",
    "lines_in",
    "paired",
    "read_line",
    "read_prompt_bench",
    "record_score",
    "rows_for_a_clean_sweep",
    "runs_for_variant",
    "scoring_run",
    "try_prompt",
    "variant_with_text",
    "variants_in",
    "with_exemplars",
]
