"""The evaluation bench: run an eval set, keep every row, and say what the
number can and cannot resolve.

`docs/VISION.md` says the most valuable thing this product can say is *"do not
train anything"*, and then names the hole: that answer is a dead end. Forty-six
of the engine's fifty-five outcomes are the product saying *do this cheaper thing
instead*, and every one of them is a thing that has to be MEASURED before and
after or it is advice. **Nothing can be optimised that cannot be measured**, and
until this module existed the harness could count an eval set (`measure_eval_set`)
and score a baseline once (`measure_baseline`) and nothing else: it could not run
an eval, keep the per-row results, or say which rows failed and why.

This is the keystone. The prompt bench, the retrieval bench and the comparison
surface all stand on the two tools here, so the shape they consume is documented
below rather than left to be read out of the code.

## What this module is FOR, in one sentence per job

**RUN.** `run_eval` sends the user's eval rows to the user's own model, through
the adapters that already exist, under a system prompt the caller chooses.

**KEEP.** Every graded row is committed to `eval_results` before the next
question goes out. That is what makes a run resumable, and it is what makes a
later run comparable to this one - see `app/migrations/v008_an_eval_keeps_its_rows.py`
for why the per-row rows are the point and the aggregate is not.

**BUCKET.** Failing rows are sorted into the engine's own failure modes by rules
a person can reproduce by eye, and the histogram is stamped MEASURED. This is the
largest single thing this module unlocks: `failure_histogram` is declared
`source: derive` in `docs/diagnosis_engine.yaml`, `derive` admits MEASURED and
nothing else, and no tool in this harness measured it - so stage 1 of the
diagnosis tree terminated in `ACTION__CLASSIFY_FAILURES` for everybody, always,
and the eight routes below `S1_ROUTE_BY_FAILURE_MODE` were unreachable.

**RESOLVE.** Every score is reported with a 95% Wilson interval and with the
smallest difference this eval set could tell apart. *A score without its
resolution is half a number.*

## THE REFUSAL THAT IS THE POINT

A prompt playground shows you 73% and then 76% and lets you conclude. Comparing
two prompts on thirty rows and declaring a winner is the never-invent-a-number
failure wearing statistical clothing, and it is the failure this module exists to
survive.

So `compare` does not diff two aggregates. It pairs the runs row by row - only
the rows that CHANGED carry any information - and runs McNemar's exact test over
them. When the test cannot separate the two, the answer is **no evidence**, in
those words, with the number of rows that would be needed. Not "a small win".

Two rules that are not negotiable and that a sibling bench must not soften:

* **A delta inside the resolution is reported as no evidence.** A prompt change
  is cheap enough to make forty times, and a user shown forty unresolvable deltas
  will believe the tenth.
* **Rows used as few-shot exemplars are held out of the score.** `hold_out=`
  exists for exactly that, it enters the run signature, and a run with different
  held-out rows is a different run rather than the same one with a footnote.

## THE DELTA IS PAIRED, AND WHY THE FINGERPRINT DID NOT MAKE IT SO

`compare` used to headline the difference of the two runs' AGGREGATE scores -
each run's own correct-count over its own graded rows - while the evidence
printed underneath it (`improved`, `regressed`, `p_value`) was paired over the
intersection. Those are two different measurements of two different row sets,
and when the row sets differ they do not merely drift apart, they can point in
OPPOSITE DIRECTIONS. Constructed and measured before this was changed:
`run_eval(sample=30)` then `run_eval(sample=100)` on one file produced a card
reading **"-50.0% / A real difference on this eval set / MEASURED"** sitting
directly above **"6 improved, 0 regressed, p=0.031"**. The new run was the same
or better on every row both runs graded, and the headline said it was fifty
points worse. On the few-shot path - which `NO_TRAIN__FEW_SHOT` RECOMMENDS - a
challenger holding out ten exemplar rows reported **+12.0 points where the
honest paired difference was +4.0**: a threefold exaggeration in the flattering
direction, arriving exactly when the user does the recommended thing.

**And it is not a property of the fixture.** Measured against
granite4-hermes:latest on a live Ollama, thirty rows of three-label sentiment,
on a scratch database. A champion prompt naming two of the three labels scored
26/30 = 86.7% and failed rows 22, 24, 26 and 27. A few-shot challenger took
those four failures as exemplars, held them out - which is what
`docs/PRODUCT_SPEC.md` §6.5 requires - and scored 26/26 = 100%. On the
twenty-six rows both runs graded, **not one row changed its verdict**: 0
improved, 0 regressed, p=1. The old headline was **+13.3%**. The whole of that
"improvement" was the champion's own four failures leaving the denominator. The
first attempt at this live check used the thin baseline prompt as the champion,
which scored 0/30; removing four of its failures leaves 0/24 and the two
numbers agree at +100%, so that run measured nothing about this defect at all -
recorded because a control that cannot fail certifies nothing.

**The fingerprint was never the instrument for this.** `eval_fingerprint` hashes
every ELIGIBLE row of the file (see `_plan`) and it answers one question - *is
this the same eval SET?* - which is the question its name asks and the only one
it can answer before a single row has been graded. It is not moved onto `chosen`,
for two reasons. First, it would still be the wrong instrument: which rows a run
GRADED is not a thing to hash, it is a thing to READ, and it is on disk in
`eval_results` keyed by `row_index`. Second, it would answer by REFUSING - a
re-run at a different `sample`, and every few-shot comparison the bench itself
recommends, would become `different_eval_sets`. `sample` and `hold_out` are
already in `signature_for`, so a re-run at a different size is already a
different RUN; it is not a different eval set and must not be reported as one.

So `compare` reads both runs' graded `row_index` sets and:

* **`delta`, `score` and `score_against` are all PAIRED**, over the rows both
  runs graded. `delta` is therefore identically `(improved - regressed) /
  paired_rows` - the headline is the paired strip divided by its own width, so
  a card whose big number disagrees with the counts beneath it is now an
  arithmetic impossibility rather than a thing a reviewer has to notice. When
  the two runs graded the same rows - the ordinary case - this is bit-for-bit
  the number the aggregate difference used to be, so a real difference is still
  reported, and a bench that refuses everything is as useless as one that
  concludes everything.
* **The aggregate difference is demoted, not deleted**, to the `aggregate` block,
  which carries both runs' own scores, their row counts, the rows only one of
  them graded, and a sentence saying it is over two different row sets. It is a
  fact about two runs; it is not the difference between them.
* **No shared row is a refusal.** Two runs that graded disjoint rows have not
  been compared at all, and reporting "not one of the 0 rows changed its
  verdict" - which is what this returned - reads as agreement.

`prompts.paired()` computed the honest number already and its docstring already
said this delta was "misleading the moment they did not [grade the same rows]".
The correction had been written down and never applied to the function
`read_eval_results` exposes directly. That is why it shipped.

## What was TAKEN from `app/tools/measure.py` rather than rewritten

Said explicitly because the brief asked, and because a second normalisation would
mean a baseline and an eval score were measured with two different instruments
and were never comparable:

* **`measure.normalise_answer`** - case, whitespace and edge punctuation, and
  nothing cleverer. Imported and used unchanged. Every metric here is built on
  it, so `measure_baseline`'s number and `run_eval`'s number mean the same thing.
* **`measure.BASELINE_SYSTEM`** - the deliberately thin baseline prompt, and the
  default for `prompt=`. A baseline measured under a clever prompt is a
  measurement of the prompt.
* **The trivial baseline's definition** - the majority answer over the same rows,
  computed from the file with no model involved. A system that cannot beat it has
  not been shown to work at all.
* **The egress refusal** - a model asking to send the user's eval rows to a
  remote endpoint is not the user asking. Copied in full, including the sentence,
  because a second door with a weaker rule is the same as no rule.
* **"A score from a run that fell over is not a score."** A run that stops
  mid-way stamps nothing at all.
* **The streaming read with `stream.close()`** - an abandoned generator holds its
  file handle until the collector runs, which on Windows keeps the directory.

What is NOT taken is `measure._ask`, and the reason is a real difference rather
than taste: it hardcodes `BASELINE_SYSTEM` and reports no clock. `_ask` here
takes the system prompt as a parameter and times the call, because the prompt is
the thing the prompt bench changes and the clock is what `too_slow` is decided
on. The `Delta` handling is deliberately the same shape.

## DETERMINISM AND COST, and what the choice does not catch

An eval run spends the user's own tokens. A re-run of the same eval on the same
prompt against the same model must be recognisable as such rather than silently
re-billed.

The mechanism is a **signature**: a hash over everything that decides what would
be asked, or what would be recorded - the graded rows themselves, the two field
names, the adapter, the base URL, the model, the system prompt, the metric, the
judge, the sample size, the held-out rows and the latency budget. A call whose
signature names a COMPLETE run in this conversation returns that run's stored
results and spends nothing. A call whose signature names an INCOMPLETE run
resumes it. `rerun=True` forces a fresh one.

**What it does not catch, stated rather than discovered:**

1. **The model behind a name can change.** `granite4-hermes:latest` is a tag, and
   re-pulling it changes the weights without changing the string. An API model id
   can be updated server-side with no notice at all. The signature names the
   model; it cannot fingerprint it.
2. **This is not a claim of determinism.** No adapter here sends a temperature,
   so the server's default applies and two runs of the same signature can
   genuinely differ. Reuse is a refusal to re-bill, not a promise that the answer
   would have been the same.
3. **The eval fingerprint covers the graded fields only.** A change to a column
   neither `input_field` nor `expected_field` names is invisible - correctly, but
   it means "the eval set is unchanged" is a claim about the two columns.
4. **Row order is part of the eval set.** The fingerprint hashes pairs in file
   order, so shuffling a file produces a different eval set and a full re-run.
   That is honest and it is expensive; it is the price of `row_index` meaning the
   same thing across runs, which is what pairing needs.
5. **The prompt is hashed verbatim.** A whitespace change is a different run. We
   are not in the business of deciding which whitespace matters to a model.
6. **Reuse is scoped to the conversation.** The same run in a second thread is
   billed again. A stored run in another conversation is somebody else's
   measurement as far as this one is concerned, and re-stamping it here would be
   the eval-set leak of migrations 6 and 7 with an extra table in the way.

## INTERRUPTION

An eval over five hundred rows takes real time and a laptop closes.

* Each graded row is committed in its own transaction before the next question is
  asked, so a kill loses at most the row in flight.
* The run row, with `planned`, is written before any grading starts. Completion is
  `COUNT(eval_results) = planned` and there is no status column to disagree with
  it.
* `deadline_seconds` (default `DEFAULT_DEADLINE_SECONDS`) stops the loop cleanly
  and reports how far it got, so a tool call can never hold a turn for half an
  hour. Calling `run_eval` again with the same arguments continues from where it
  stopped.
* Progress goes onto the **event spine**, whose autoincrement id is the SSE event
  id, so a client that reconnects mid-eval gets the frames it missed by asking for
  everything after the last id it saw. `eval.started`, `eval.progress` (every
  `PROGRESS_STRIDE` rows), and one of `eval.finished` / `eval.interrupted` /
  `eval.reused`. Nothing per-row goes into the transcript: the durable per-row
  record is the table, and a five-hundred-line eval in a chat thread is the
  failure `docs/ROADMAP.md` calls out by name.

## GRADING, and the sycophancy this product exists to survive

Three metrics ship. Every one of them is computed for EVERY row whatever the run
is scored on, and all three verdicts are stored in `verdicts_json`, because the
gap between them is the most informative thing on the page.

* **`exact_match`** (default) - `normalise_answer(reply) == normalise_answer(expected)`.
  Reproducible by eye. Blind to a right answer wearing a sentence.
* **`contains`** - the expected answer appears inside the reply after
  normalisation. Loose on purpose, and dishonest on its own: a reply that
  contains the right answer and three wrong ones passes. It is here because the
  gap between it and `exact_match` is the single most reliable signal of a FORMAT
  failure, which is what the bucketer uses it for.
* **`model_graded`** - opt-in, and **this is the user's own model grading its own
  answers.** That sentence is not buried: the row records
  `graded_by = "model:<name>"`, the run records `judge_model`, the payload carries
  a `self_graded` block, and the `how=` written next to the stamped
  `baseline_score` says it in words, which is where invariant 3 says a
  provenance has to be. And because `exact_match` and `contains` are computed on
  the same rows for free, a judge that says 90% while exact match says 40% shows
  that gap rather than replacing it. Pass `judge_provider_id` to have a DIFFERENT
  connection grade, which is weaker sycophancy but is still a model.

**A judge never buckets.** `failure_histogram` is stamped from the rules below and
from nothing else, in every configuration. A bucket is what routes the diagnosis
tree, and the model's own account of why it was wrong is exactly the input this
product must not route on. When a judge is used it decides one thing - was this
row right - and that decision is labelled on the row.

**An unreadable judge verdict stops the run.** Counting it as INCORRECT would be
a reading nobody made; counting it as CORRECT would be worse. The run keeps its
graded rows, stamps nothing, and says how many verdicts could not be read and what
they said.

## THE BUCKETING RULES, and what they refuse to guess

The engine routes on eight failure modes, read off
`S1_ROUTE_BY_FAILURE_MODE`'s own `routes:` block at load time rather than listed
here. Rules, highest precedence first:

1. **`inconsistent`** - the same input appears more than once in the graded rows
   and did not get the same verdict every time. The model has demonstrably done
   this task; the failure is inconsistency and not knowledge. Cannot be seen from
   one row, so it is derived over the run at report time rather than stored.
2. **`refuses`** - the reply is empty, or opens with one of `REFUSAL_OPENINGS`.
   An empty reply is bucketed here on purpose: the model was asked and did not
   answer, and `refuses` routes to stage 5, which is where "it will not do it"
   belongs.
3. **`wrong_format`** - the expected answer IS in the reply and the reply is not
   the expected answer (`contains` and not `exact_match`); or the expected value
   parses as JSON and the reply does not; or the expected column is a closed
   vocabulary (see `_label_set`) and the reply is not a member of it at all.
   Right content, wrong shape - and the third clause is the one a real model
   made necessary, argued in `bucket`.
4. **`wrong_facts`** - the expected column is a closed vocabulary and the reply
   is a DIFFERENT member of it. A confident, well formed, wrong answer. This and
   the third `wrong_format` clause are the same test read two ways, and they
   have opposite correct answers: stage 3 for content, stage 4 for shape.
5. **`too_slow`** - only when the caller supplied `latency_budget_ms`, and only
   on a row that was otherwise CORRECT. Without a budget there is no such thing
   as too slow and inventing one would be inventing a number; and on a wrong row,
   fixing the latency does not fix the wrongness.
6. Anything else - which after rule 4 means a FREE-TEXT expected column, where
   there is no vocabulary to check a reply against - is **`unclassified`**,
   which is NOT a routable mode, is NOT put in the histogram, and IS counted and
   reported. `wrong_style`,
   `wrong_reasoning` and `too_expensive` are never assigned by rule: the first two
   need a judgement about meaning and the third needs token prices we do not
   have. Guessing them would route somebody's diagnosis on a coin flip.

Leaving unclassified failures out of the histogram makes `sum(values())` an
UNDER-count of failures, which is the conservative direction: it routes to
`ACTION__CLASSIFY_FAILURES` ("go and bucket more") rather than to a stage chosen
from a guess.

## THE SHAPE THE SIBLINGS CONSUME

Python, not HTTP. Import these; do not re-derive them.

    evals.run(...)                  -> dict, the run report (below)
    evals.read(run_id)              -> dict, the same report for a stored run
    evals.compare(run_id, against)  -> dict, the paired verdict
    evals.runs_in(thread_id)        -> list[dict], newest first
    evals.resolution_for(correct, n)-> dict, the honest confidence block
    evals.wilson(correct, n)        -> (low, high)
    evals.mcnemar(improved, regressed) -> float, two-sided exact p
    evals.signature_for(...)        -> str

The run report is a `dict` with, at minimum::

    {
      "ok": bool,
      "run_id": int,
      "complete": bool,          # every planned row graded
      "reused": bool,            # answered from disk; no tokens spent
      "metric": str,             # which metric the score is
      "score": float | None,     # None while incomplete
      "correct": int, "graded": int, "planned": int,
      "rows_available": int,     # eligible rows in the file
      "trivial_baseline_score": float | None,
      "scores": {metric: float},         # every metric, on the same rows
      "resolution": {...},               # see resolution_for()
      "failure_histogram": {mode: int},  # routable modes only
      "unclassified": int,
      "failures": [ {row_index, input, expected, answer, failure_mode, ...} ],
      "self_graded": {...} | None,
      "eval_fingerprint": str, "signature": str,
      "summary": str,
    }

A prompt bench scores a change by calling `run(...)` twice with different
`prompt=` against the same `eval_path`, then `compare(new_run, against=old_run)`.
Both runs carry the same `eval_fingerprint`, which is how they are known to be
about the same eval SET at all; `compare` refuses two runs whose fingerprints
differ, because two scores on two different eval sets are two facts and not a
delta. **A shared fingerprint does not mean the two runs graded the same rows** -
`sample` and `hold_out` decide that and neither is in the fingerprint - so
`compare` reads the graded `row_index` sets and reports the PAIRED difference.
See THE DELTA IS PAIRED above.

## WHAT THIS MODULE DELIBERATELY DOES NOT DO

* It does not BUILD an eval set. `build_eval_set` / `import_eval_set` are
  `docs/ROADMAP.md` M3's other tools and they are a conversation, not a runner.
* It does not optimise a prompt. It scores one.
* It does not run BM25 or a regex as trivial baselines. Majority class is the one
  that needs nothing but the file; the other two need a retriever and a pattern
  the user has not given us, and a trivial baseline we invented is not trivial.
* It does not estimate cost in money. `too_expensive` is a routable failure mode
  and it stays unassigned until something in this product knows token prices.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from app import dataquality, db, diagnosis, events
from app.providers import Delta, build, secrets, store
from app.tools import evidence, measure
from app.tools.evidence import Instrument
from app.tools.registry import tool


# ---------------------------------------------------------------------------
# Constants. Every number here says where it came from.


#: How many rows a run grades unless told otherwise. `docs/ROADMAP.md` M3 asks
#: for "30-50 real inputs from actual traffic" and `G0_EVAL_SET` opens at 30, so
#: the default is the top of that band: enough to open the gate and enough to be
#: worth a resolution statement, without being a twenty-minute default.
DEFAULT_EVAL_SAMPLE = 50

#: THE `provider_name` PREFIX ON A RUN THAT WAS NOT MEASURED THROUGH A
#: CONNECTION. `app/tools/training.py::_store_an_arm` keeps the adapter's and
#: the base model's answers in these tables - which is right, because they are
#: graded rows and this is where graded rows live - and stamps the column with
#: `sandbox:adapter` / `sandbox:base` because there was no connection involved
#: at all.
#:
#: IT IS A CONSTANT BECAUSE READING IT WRONG COSTS A GPU. `_store_an_arm`'s own
#: docstring said the run was written so that *nothing downstream can mistake it
#: for the baseline `G1_BASELINE_MEASURED` reads* - true of the gate, and false
#: of `propose.the_baseline_run_to_beat`, which filtered on completeness and on
#: the eval file and not on this. Measured on a scratch database: after one
#: `score_the_adapter`, that function returned the ADAPTER'S OWN ARM as the
#: baseline to beat, at its own score, and the next training proposal would have
#: planned a fine-tune against it while calling it the person's measured
#: baseline. A correct reading of the gate and a false headline about the
#: harness, which is the exact shape this product keeps having to remove.
SANDBOX_ARM_PREFIX = "sandbox:"


def was_measured_through_a_connection(report: Mapping[str, Any]) -> bool:
    """Did a model this person connected produce the answers in this run?

    False for a sandbox arm - an adapter or a base model generating locally
    inside a pinned environment. Both are real graded runs; only one of them is
    a BASELINE, and a comparison drawn against the other compares a fine-tune
    with the last fine-tune and calls it the baseline.
    """
    return not str(report.get("provider") or "").startswith(SANDBOX_ARM_PREFIX)


#: A bound on how much of somebody's model budget ONE call may spend. It is not a
#: limit on the eval set: `rows_available` reports the whole file and the
#: resolution block says how many more rows would be needed. Chosen so that a
#: full run at roughly a second a row is about half an hour of somebody's
#: machine, which is already past what a single tool call should ask for - which
#: is why `deadline_seconds` exists beside it.
MAX_EVAL_SAMPLE = 2000

#: How long one call will keep grading before it stops cleanly and reports how
#: far it got. Ten minutes, which is `ollama.STREAM_TIMEOUT_SECONDS` - the bound
#: on a SINGLE request - so the bound on a whole run is the same order as the
#: bound on one row of it. A run that hits this is not an error: it is resumable
#: and the reply says so.
DEFAULT_DEADLINE_SECONDS = 600.0

#: How often a progress frame goes onto the event spine. The transcript stays
#: calm - `docs/ROADMAP.md` is explicit that nothing heavy streams into it - so a
#: 500-row run produces twenty progress events and not five hundred.
PROGRESS_STRIDE = 25

#: How much of an input, an expected answer or a reply is stored per row. The
#: per-row table is for READING - which rows failed and how - and the dataset is
#: still on disk. A row longer than this is stored truncated with a marker, and
#: nothing re-derives a verdict from the stored text: the verdicts are stored
#: beside it.
STORED_TEXT_CHARS = 4000

#: The most distinct expected values a column may have and still be treated as a
#: CLOSED LABEL SET, and the largest share of the graded rows those distinct
#: values may account for. Both bounds are needed: twenty labels over twenty-five
#: rows is not a label set, it is free text that happens to be short. Used only
#: to decide whether `wrong_facts` may be assigned - a column that fails these
#: tests buckets to `unclassified` instead, which is the direction that guesses
#: less.
CLOSED_SET_MAX_LABELS = 20
CLOSED_SET_MAX_SHARE = 0.5

#: The openings that make a reply a refusal. A closed, short, readable list
#: rather than a classifier: every entry is a phrase that cannot begin an answer
#: to anything, and a reply that merely CONTAINS one of them ("the sorry state of
#: the art") is not matched, because the test is on the opening.
REFUSAL_OPENINGS = (
    "i can't", "i cannot", "i can not", "i won't", "i will not",
    "i'm sorry", "i am sorry", "sorry, i", "sorry i",
    "i'm unable", "i am unable", "unable to",
    "i'm not able", "i am not able",
    "as an ai", "as a language model",
    "i don't have", "i do not have",
    "i'm afraid", "i am afraid",
)

#: The metrics that ship. See GRADING in the module docstring, and note that all
#: three are computed on every row whatever the run is scored on.
EXACT_MATCH = "exact_match"
CONTAINS = "contains"
MODEL_GRADED = "model_graded"
FIELDS = measure.FIELDS
#: `fields` JOINED THEM, AND THE GAP IT CLOSES IS A REAL ONE. `measure_baseline`
#: has graded JSON records field by field since it was written; `run_eval` -
#: the tool the diagnosis NAMES as the remedy for ACTION__CLASSIFY_FAILURES -
#: could only offer exact_match, contains and a judge.
#:
#: Max's thread 92, 2026-09-21. `measure_baseline` graded 20 rows with `fields`
#: and scored 0%. The walk routed, correctly, to "go and bucket twenty
#: failures". Bucketing means re-running the same rows through `run_eval` - and
#: `run_eval` could not grade them the same way. Run with exact_match instead,
#: all forty failed (no JSON record ever equals another byte for byte), every
#: failure came back UNCLASSIFIED because the replies ARE json so the
#: wrong_format rule correctly did not fire, and `failure_histogram` stayed {}.
#: The walk cannot leave ACTION__CLASSIFY_FAILURES until that histogram fills,
#: so the thread could not move, and nothing in the product said why.
#:
#: Two tools that grade the same eval set must share a metric vocabulary. The
#: implementation is `measure.grade_fields` itself - imported, not copied, so
#: a baseline and the bucketing of its own failures can never disagree about
#: what counted as right.
METRICS = (EXACT_MATCH, CONTAINS, MODEL_GRADED, FIELDS)

#: The bucket for a failure the rules will not name. Deliberately NOT one of the
#: engine's routable modes: it is excluded from the stamped histogram and
#: reported on its own, because a failure nobody classified is a fact about this
#: bucketer and not about the user's model.
UNCLASSIFIED = "unclassified"

#: What the judge is told. One word back, and the word is checked rather than
#: parsed leniently - see `_read_verdict`.
JUDGE_SYSTEM = (
    "You are grading one answer against the answer that would have been right. "
    "Reply with exactly one word and nothing else: CORRECT if the answer means "
    "the same thing as the expected answer, or INCORRECT if it does not. No "
    "explanation, no punctuation, no other word."
)

#: 95%, two-sided. The one distributional constant in this file.
Z_95 = 1.959963984540054

#: The failure modes `S1_ROUTE_BY_FAILURE_MODE` has a route for, used only if
#: reading them off the loaded spec fails. See `routable_modes`.
_FALLBACK_ROUTABLE = (
    "inconsistent", "refuses", "too_expensive", "too_slow",
    "wrong_facts", "wrong_format", "wrong_reasoning", "wrong_style",
)

#: Event kinds. The id of each of these rows is the SSE event id a reconnecting
#: client resumes from; see `app/events.py`.
STARTED = "eval.started"
PROGRESS = "eval.progress"
FINISHED = "eval.finished"
INTERRUPTED = "eval.interrupted"
REUSED = "eval.reused"


#: Reused unchanged, so a baseline and an eval score are the same instrument.
normalise_answer = measure.normalise_answer


#: THE NODE THAT CARRIES THIS LEDGER'S FAILURE-BUCKET VOCABULARY, and it is an
#: ML-only id by name. `S1_ROUTE_BY_FAILURE_MODE` is one ledger's spelling; the
#: declared alternative is `contract.knowledge: {failure.buckets: <node>}`, which
#: is `ledger_format: 4` and is step 3 of `docs/CAPABILITY_BLOCKS.md`'s migration
#: path rather than this pass's work. What this pass owes is that a ledger with
#: no such node gets an honest empty answer instead of a read of the first
#: ledger's file, and that the FALLBACK below never stands in for another
#: domain's vocabulary.
_THE_ROUTER_NODE = "S1_ROUTE_BY_FAILURE_MODE"


def routable_modes(spec: diagnosis.Spec | None = None) -> tuple[str, ...]:
    """The failure modes the diagnosis engine can actually route on.

    READ OFF THE SPEC, not listed here. The router node carries its own
    `routes:` map, and the spec warns in `uninspectable_facts.one_known_gap`
    that the router "raises if failure_histogram carries only keys the router
    has no route for". A list in this file would be a second answer to a
    question the ledger already answers, which is the drift this repository has
    been bitten by twice.

    WHICH NODE IS THE ROUTER IS THE LEDGER'S OWN DECLARATION. A ledger may name
    it under `contract.knowledge: {failure.buckets: <node id>}` - the second
    ledger's fork is called something else on purpose, and a hard-coded node
    name here is this file guessing at another domain's grammar. A declared
    node that cannot be read yields `()` for THAT ledger; there is no fallback
    to any other ledger's vocabulary, because handing one domain the other's
    bucket names would be the wrong-file read dressed as resilience.

    For a ledger that declares nothing, the ML router node is looked up by its
    historical name, and the constant fallback below applies only when THAT
    node exists with no routes - the same narrow case as before, unchanged.

    The fallback exists because a bucketer that raises during a paid eval run
    because a node was renamed would throw away work the user paid for. It is
    the same eight names, and it is a constant so that a divergence is a visible
    diff rather than a silent behaviour change.
    """
    current = spec or diagnosis.default_spec()
    contract = getattr(current, "contract", None) or {}
    declared = (contract.get("knowledge") or {}).get("failure.buckets")
    if declared:
        try:
            node = current.node_index.get(declared)
            if node is None:
                return ()
            # TWO SHAPES, BOTH REAL. The first ledger's router declares
            # `routes:` on the node; the second's fork declares them under
            # `fork:` - a fork IS a route map, that is what the word means -
            # and a reader that knows only one shape would report the other
            # ledger as having no vocabulary at all.
            routes = node.get("routes")
            if routes is None and isinstance(node.get("fork"), Mapping):
                routes = node["fork"].get("routes")
            return tuple(sorted(routes or ()))
        except Exception:  # noqa: BLE001 - a spec that will not load is not our news
            return ()
    try:
        node = current.node_index.get(_THE_ROUTER_NODE)
        if node is None:
            return ()
        names = tuple(sorted(node.get("routes") or ()))
    except Exception:  # noqa: BLE001 - a spec that will not load is not our news
        names = ()
    return names or _FALLBACK_ROUTABLE


# ---------------------------------------------------------------------------
# The statistics. A score without its resolution is half a number.


def wilson(correct: int, n: int, z: float = Z_95) -> tuple[float, float] | None:
    """The Wilson score interval for `correct` of `n`. `None` when `n` is 0.

    WILSON AND NOT THE NORMAL APPROXIMATION, and the reason is the case that
    matters most: `sqrt(p(1-p)/n)` is exactly zero at p=0 and p=1, so a run that
    scored 20 out of 20 would report an interval of +-0.0 points. That is an
    invented number in the most dangerous possible place - the run that looks
    perfect - and it is why every "95% CI" in a spreadsheet is wrong at the
    edges. Wilson is asymmetric, never zero-width, and is the standard answer.
    """
    if n <= 0:
        return None
    p = correct / n
    denominator = 1.0 + (z * z) / n
    centre = (p + (z * z) / (2 * n)) / denominator
    half = (z / denominator) * math.sqrt(p * (1 - p) / n + (z * z) / (4 * n * n))
    return (max(0.0, centre - half), min(1.0, centre + half))


def rows_for_points(points: float, z: float = Z_95) -> int:
    """How many rows are needed to resolve a difference of `points` percent.

    Worst case, at p=0.5, for two INDEPENDENT runs: the standard error of a
    difference of two proportions is `sqrt(2 p(1-p)/n)`, so `n = 2 z^2 p(1-p) /
    d^2` with `p = 0.5` gives `n = z^2 / (2 d^2)`.

    A PAIRED comparison of two runs over the same rows needs fewer, sometimes far
    fewer, because only the rows that changed carry information - that is what
    `mcnemar` is for and it is why this number is labelled as the unpaired worst
    case wherever it is reported. Reporting the smaller paired figure here would
    require knowing how many rows are going to change, which is the thing being
    measured.
    """
    fraction = max(1e-9, float(points) / 100.0)
    return max(1, math.ceil((z * z) / (2.0 * fraction * fraction)))


def resolution_for(correct: int, n: int, available: int | None = None) -> dict[str, Any]:
    """The confidence block that travels with every score in this module.

    `docs/PRODUCT_SPEC.md`'s own sentence is *"n=30 only resolves differences
    larger than ~15 points. n>=100 to trust a 5-10 point delta. Report the
    resolution alongside every score."* The first half of that is the SINGLE
    SCORE's half-width - Wilson at n=30 and p=0.5 is +-16.8 points, computed, not
    quoted - and it gets used loosely as though it were a threshold for a
    DIFFERENCE. A difference has two errors in it, so its threshold is larger,
    and both numbers are reported here under names that say which is which rather
    than one number under a name that could mean either.
    """
    interval = wilson(correct, n)
    if interval is None:
        return {
            "n": 0,
            "method": "no rows were graded, so there is nothing to resolve",
            "says": "Nothing has been graded, so there is no score and no interval.",
        }
    low, high = interval
    half_points = (high - low) / 2.0 * 100.0
    worst_case = Z_95 * math.sqrt(0.5 / n) * 100.0
    needed_10 = rows_for_points(10.0)
    return {
        "n": n,
        "ci_95": [low, high],
        "half_width_points": half_points,
        "resolves_a_difference_of_at_least_points": worst_case,
        "rows_for_a_10_point_difference": needed_10,
        "more_rows_needed_for_10_points": max(0, needed_10 - n),
        "method": (
            "Wilson score interval, 95%, two-sided. The difference figure is the "
            "worst case (p=0.5) for two INDEPENDENT runs; two runs over the same "
            "rows are compared pairwise with McNemar's exact test, which needs "
            "fewer rows. Neither figure is a quoted rule of thumb - both are "
            "computed from n."
        ),
        "says": (
            f"{n} rows put this score between {low:.0%} and {high:.0%} with 95% "
            f"confidence (+-{half_points:.1f} points). Two separate runs on a set "
            f"this size cannot be told apart unless they differ by about "
            f"{worst_case:.0f} points. To resolve a 10-point difference this way "
            f"you would need {needed_10} rows"
            + (
                # ROWS GRADED IS NOT ROWS AVAILABLE, and saying "more than you
                # have" about a sample is a lie about a file.
                #
                # Measured 2026-09-09: run_eval graded its default 50 rows of a
                # 196-row file and reported "you would need 193 rows, which is
                # 143 more than you have". The 196 were sitting in the file it
                # had just streamed to the end. A reader told that cannot fix
                # it, because the fix -- grade more of what is already there --
                # is the one thing the sentence says is impossible.
                ", which the file already has: it has "
                + str(available)
                + " rows and this run graded "
                + str(n)
                + ". Raise the sample."
                if available is not None and needed_10 <= available and needed_10 > n
                else f", which is {needed_10 - n} more than you have."
                if needed_10 > n
                else ", which you have."
            )
        ),
    }


def mcnemar(improved: int, regressed: int) -> float:
    """Two-sided exact McNemar p-value over the rows that CHANGED.

    `improved` is rows the new run got right and the old one got wrong;
    `regressed` is the reverse. Rows that agree carry no information about the
    difference and are correctly ignored - which is the whole reason a paired
    test is stronger than comparing two aggregates, and the reason this module
    keeps per-row results at all.

    Exact binomial rather than the chi-square approximation, because the
    interesting case here is small: an eval set of thirty rows where four changed
    is exactly where the approximation is worst and exactly where somebody is
    about to declare a winner.

    Returns 1.0 when nothing changed, which is the honest reading: no evidence of
    any difference whatsoever.
    """
    b, c = int(improved), int(regressed)
    total = b + c
    if total <= 0:
        return 1.0
    tail = sum(math.comb(total, k) for k in range(0, min(b, c) + 1))
    return min(1.0, 2.0 * tail / (2.0**total))


# ---------------------------------------------------------------------------
# The metrics, and the bucketer.


def grade(expected: Any, answer: Any) -> dict[str, bool]:
    """Every deterministic metric's verdict on one row, in one place.

    Both are computed for every row however the run is scored, because the GAP
    between them is what the bucketer reads and what makes a model-graded score
    checkable. A row where `contains` is true and `exact_match` is false is a
    right answer wearing a sentence, and that is a format problem and not a
    knowledge problem - which are opposite correct answers.
    """
    wanted = normalise_answer(expected)
    got = normalise_answer(answer)
    return {
        EXACT_MATCH: got == wanted,
        CONTAINS: bool(wanted) and wanted in got,
        # Field by field, through the one implementation both tools call.
        FIELDS: bool(measure.grade_fields(expected, answer).get("correct")),
    }


def _as_number(value: Any, default: Any = None) -> Any:
    """A caller's number, WITHOUT converting one numeric type into another.

    This is not defensive tidying, it is wall 2. `evidence._note_conversion`
    remembers `int(x)` and `float(x)` performed on a value the caller supplied -
    because CPython will not let a converted value carry the caller mark - and
    `Instrument.measured` then refuses to stamp anything equal to what was
    remembered. `float(deadline_seconds)` on a `deadline_seconds` of 1 therefore
    remembers `1.0`, and a run that scored 100% would be refused a stamp for a
    reason that has nothing to do with where its score came from.

    An identity conversion is already exempt in `_note_conversion`, so the fix is
    simply not to convert what is already a number. A string is converted, and
    safely: a caller's strings are not marked, so nothing is remembered.
    """
    if value is None:
        return default
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def _looks_like_json(text: str) -> bool:
    stripped = str(text).strip()
    if not stripped or stripped[0] not in "[{":
        return False
    try:
        json.loads(stripped)
    except ValueError:
        return False
    return True


def _label_set(expected_values: Iterable[Any]) -> frozenset[str]:
    """The closed label set of the expected column, or empty if it is not one.

    THIS IS THE FUNCTION THAT DECIDES WHETHER `bucket` HAS A VOCABULARY TO CHECK
    AGAINST, and both of the rules that use it turn on knowing what a well formed
    answer looks like: a member of the set that is not the right one is
    `wrong_facts`, and something that is not in the set at all is
    `wrong_format`. A column of five labels over fifty rows gives that; a column
    of fifty distinct sentences over fifty rows does not, and treating the second
    as a vocabulary would bucket every free-text failure and route the whole
    diagnosis on a category error.

    Both bounds are checked because either alone is wrong: `<= 20 distinct` calls
    a 25-row free-text set a label set, and `<= half the rows` calls a 4000-row
    free-text set one.
    """
    values = [normalise_answer(v) for v in expected_values]
    distinct = {v for v in values if v}
    if not values or not distinct:
        return frozenset()
    if len(distinct) > CLOSED_SET_MAX_LABELS:
        return frozenset()
    if len(distinct) > CLOSED_SET_MAX_SHARE * len(values):
        return frozenset()
    return frozenset(distinct)


def bucket(
    expected: Any,
    answer: Any,
    verdicts: dict[str, bool],
    labels: frozenset[str] = frozenset(),
) -> str:
    """The row-local failure mode for one FAILING row. Never called on a pass.

    Precedence and reasons are in the module docstring. `inconsistent` is not
    here because it cannot be decided from one row, and `too_slow` is not here
    because it is a property of the clock rather than of the text.

    Returns `UNCLASSIFIED` rather than guessing. Three of the engine's eight
    modes - `wrong_style`, `wrong_reasoning`, `too_expensive` - are never
    returned by any rule in this file, and that is the honest state of a bucketer
    that reads text and has no prices.

    THE LAST RULE WAS ADDED BY RUNNING THIS AGAINST A REAL MODEL AND IT IS THE
    ONE THAT EARNS THE BENCH ITS KEEP. On a forty-row sentiment set whose
    expected column is `{positive, negative, neutral}`, granite4-hermes:latest on
    a live Ollama, under the thin baseline prompt, scored 0/40 - and 37 of the 40
    failures came back `unclassified`, because a paraphrase ("The product broke
    after using it for only two days") is neither the label nor a different
    label. That is not an unclassifiable failure. When the expected column IS a
    closed vocabulary, a reply that is not a member of it did not answer in the
    required shape, and that is `wrong_format` - the exact route the engine sends
    to stage 4 and `NO_TRAIN__CONSTRAINED_DECODING`. Measured on the same rows
    immediately afterwards: naming the three labels in the prompt took the same
    model from 0/40 to 40/40, paired McNemar p = 1.8e-12. The bucket was right
    and the residue was hiding it.

    With this rule in place the same live eval buckets 38 `wrong_format` and 2
    `refuses`, nothing unclassified. It was 3 refusals on the run before, on the
    same rows and the same prompt, because the model is not deterministic - which
    is the DETERMINISM section's second caveat arriving in the evidence for this
    one.

    The distinction is worth stating because the two halves have OPPOSITE correct
    answers: a reply that is a DIFFERENT member of the vocabulary is a content
    failure (`wrong_facts`, stage 3), and a reply that is not in the vocabulary
    at all is a shape failure (`wrong_format`, stage 4).
    """
    text = str(answer or "").strip()
    if not text:
        return "refuses"
    opening = normalise_answer(text)
    if any(opening.startswith(phrase) for phrase in REFUSAL_OPENINGS):
        return "refuses"
    if verdicts.get(CONTAINS) and not verdicts.get(EXACT_MATCH):
        return "wrong_format"
    if _looks_like_json(str(expected)) and not _looks_like_json(text):
        return "wrong_format"

    # A RECORD THAT IS THE WRONG RECORD, which is the commonest failure a
    # structured task has and had no rule at all.
    #
    # Max's thread 92, 2026-09-21, graded with `fields`: 40 failures, 2
    # bucketed. The replies were JSON, the expected values were JSON, there was
    # no closed vocabulary, and every rule above declined - correctly, each on
    # its own terms - so 38 rows reached UNCLASSIFIED and the histogram could
    # not fill. A histogram that cannot fill is a walk that cannot leave
    # ACTION__CLASSIFY_FAILURES, which is where his run spent fifteen turns.
    #
    # The split is the one this module already argues for two rules up, applied
    # to records instead of to labels: a key that is ABSENT means the reply did
    # not answer in the required shape, and that is stage 4 and a grammar. A key
    # that is PRESENT and disagrees is a content failure, and that is stage 3
    # and knowledge. Opposite correct answers, and `grade_fields` already
    # separates them - it returns `missing` and `disagreed` as different lists,
    # and this is the first caller to read the difference.
    #
    # Missing is checked first: a reply short of half its keys is a shape
    # problem even if the keys it did produce disagree too, because fixing the
    # shape is what makes the content question askable.
    if _looks_like_json(str(expected)):
        graded = measure.grade_fields(expected, text)
        if graded.get("shape") == "record":
            if graded.get("missing"):
                return "wrong_format"
            if graded.get("disagreed"):
                return "wrong_facts"

    if labels:
        return "wrong_facts" if opening in labels else "wrong_format"
    return UNCLASSIFIED


# ---------------------------------------------------------------------------
# The store. Nothing here issues an UPDATE or a DELETE.


def ensure_tables() -> None:
    """Bring the schema up to date. The eval tables are migration 8's."""
    from app import migrations

    migrations.migrate()


def _clip(text: Any) -> str:
    """Store enough of a value to read it back, and say when it was cut."""
    body = str(text if text is not None else "")
    if len(body) <= STORED_TEXT_CHARS:
        return body
    return body[:STORED_TEXT_CHARS] + " ... [truncated by app/tools/evals.py]"


def fingerprint_pairs(pairs: Iterable[tuple[int, str, str]]) -> str:
    """The hash that identifies an eval SET: its ELIGIBLE pairs, in file order.

    ELIGIBLE, NOT GRADED, and the distinction is the whole of the defect this
    module shipped with. `_plan` hands this every row of the file that has both
    columns, so the answer is a property of the FILE and the two column names -
    settled before a single row is graded, and unchanged by `sample` or
    `hold_out`. That is what makes it the right key for "are these two runs even
    about the same thing", and it is exactly why it cannot answer "did these two
    runs grade the same rows". `compare` asks that second question of
    `eval_results` instead, where the graded row indexes actually are.

    Not the file's bytes. Two files that differ only in a column nobody grades,
    in their line endings, or in their format are the same eval set as far as
    every question this module asks, and hashing the bytes would force a full
    re-run for a change that alters nothing that would be asked. The index is
    hashed alongside the pair so that reordering IS a change - `row_index` has to
    mean the same thing in both runs for a paired comparison to be legitimate.
    """
    digest = hashlib.sha256()
    for index, question, expected in pairs:
        digest.update(f"{index}\x00{question}\x00{expected}\x1e".encode("utf-8"))
    return digest.hexdigest()


def signature_for(
    *,
    eval_fingerprint: str,
    input_field: str,
    expected_field: str,
    adapter: str,
    base_url: str,
    model: str,
    prompt: str,
    metric: str,
    judge_model: str,
    sample: int,
    hold_out: tuple[int, ...],
    latency_budget_ms: Any = None,
) -> str:
    """Everything that decides what would be ASKED - or RECORDED - as one name.

    `latency_budget_ms` is in here and it is the one entry that does not change a
    single question. It changes what is WRITTEN: `too_slow` is decided against
    the budget and stored per row, and it cannot be recomputed from the table
    afterwards because the clock has moved on. A run reused across a change of
    budget would hand back buckets measured against a budget nobody asked for,
    which is a wrong histogram rather than a stale one.

    `deadline_seconds` is deliberately NOT in here, for the opposite reason: it
    decides when a run PAUSES and nothing about what any row says. A run resumed
    with a different deadline has to be the same run or resumption does not
    exist.

    Read the module docstring's DETERMINISM section for what this catches and,
    more importantly, for the six things it does not.
    """
    parts = [
        eval_fingerprint, input_field, expected_field, adapter, base_url, model,
        prompt, metric, judge_model, str(int(sample)),
        ",".join(str(int(i)) for i in sorted(hold_out)),
        "" if latency_budget_ms is None else str(latency_budget_ms),
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def create_run(**columns: Any) -> dict[str, Any]:
    """Insert one `eval_runs` row and return it. Written before any grading."""
    ensure_tables()
    names = sorted(columns)
    with db.session() as connection:
        cursor = connection.execute(
            "INSERT INTO eval_runs (%s) VALUES (%s)"  # noqa: S608 - names are ours
            % (", ".join(names), ", ".join("?" for _ in names)),
            tuple(columns[name] for name in names),
        )
        row = connection.execute(
            "SELECT * FROM eval_runs WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


def get_run(run_id: int) -> dict[str, Any] | None:
    ensure_tables()
    with db.session() as connection:
        row = connection.execute(
            "SELECT * FROM eval_runs WHERE id = ?", (int(run_id),)
        ).fetchone()
    return None if row is None else dict(row)


def runs_in(thread_id: int, limit: int = 50) -> list[dict[str, Any]]:
    """Every eval run in this conversation, newest first, with its progress.

    THREAD SCOPED, and the join counts the rows rather than reading a status
    column, because there is no status column - see the migration. A run's
    progress is the number of results it has and nothing else can disagree.
    """
    ensure_tables()
    with db.session() as connection:
        rows = connection.execute(
            "SELECT r.*, "
            "(SELECT COUNT(*) FROM eval_results e WHERE e.run_id = r.id) AS graded "
            "FROM eval_runs r WHERE r.thread_id = ? ORDER BY r.id DESC LIMIT ?",
            (int(thread_id), int(limit)),
        ).fetchall()
    return [dict(row) for row in rows]


def _latest_matching(thread_id: int, signature: str) -> dict[str, Any] | None:
    ensure_tables()
    with db.session() as connection:
        row = connection.execute(
            "SELECT * FROM eval_runs WHERE thread_id = ? AND signature = ? "
            "ORDER BY id DESC LIMIT 1",
            (int(thread_id), str(signature)),
        ).fetchone()
    return None if row is None else dict(row)


def results_for(run_id: int) -> list[dict[str, Any]]:
    ensure_tables()
    with db.session() as connection:
        rows = connection.execute(
            "SELECT * FROM eval_results WHERE run_id = ? ORDER BY row_index",
            (int(run_id),),
        ).fetchall()
        # The person's reading of a row, when there is one, sits on top of the
        # rule's (migration 14). Latest per row wins; the stored row is never
        # changed, so `rule_failure_mode` still says what the rule decided.
        readings = {
            int(r["row_index"]): str(r["failure_mode"])
            for r in connection.execute(
                "SELECT row_index, failure_mode FROM eval_rebuckets "
                "WHERE run_id = ? ORDER BY id",
                (int(run_id),),
            ).fetchall()
        }
    out = []
    for row in rows:
        item = dict(row)
        if int(item["row_index"]) in readings:
            item["rule_failure_mode"] = item.get("failure_mode")
            item["failure_mode"] = readings[int(item["row_index"])]
            item["bucketed_by"] = "the person who read the row"
        try:
            item["verdicts"] = json.loads(item.pop("verdicts_json") or "{}")
        except ValueError:  # pragma: no cover - we wrote it
            item["verdicts"] = {}
        item["correct"] = bool(item["correct"])
        out.append(item)
    return out


def record_row(
    run_id: int,
    row_index: int,
    *,
    question: Any,
    expected: Any,
    answer: Any,
    correct: bool,
    verdicts: dict[str, bool],
    failure_mode: str | None,
    graded_by: str,
    seconds: float,
) -> None:
    """Commit one graded row, before the next question goes out.

    `INSERT OR IGNORE` on the `(run_id, row_index)` unique key, so a resume that
    races another resume - or a caller that lost track - cannot double-count a
    row. That property is what lets completion be `COUNT(*) = planned` rather
    than a status column somebody has to keep true.
    """
    ensure_tables()
    with db.session() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO eval_results "
            "(run_id, row_index, input, expected, answer, correct, "
            " verdicts_json, failure_mode, graded_by, bucketed_by, seconds) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'rules', ?)",
            (
                int(run_id),
                int(row_index),
                _clip(question),
                _clip(expected),
                _clip(answer),
                1 if correct else 0,
                json.dumps({k: bool(v) for k, v in verdicts.items()}, sort_keys=True),
                failure_mode,
                str(graded_by),
                float(seconds),
            ),
        )


# ---------------------------------------------------------------------------
# Reading a run back: the report both tools return, computed in one place.


def _histogram(rows: list[dict[str, Any]]) -> tuple[dict[str, int], int, list[str]]:
    """`(routable histogram, unclassified count, modes dropped)` over one run.

    THE CROSS-ROW PASS LIVES HERE, not in the stored column, because
    `inconsistent` cannot be decided from one row: it is the same input answered
    two different ways, and the second answer has not been written yet when the
    first row is committed. Deriving it at read time keeps the table append-only
    and keeps the conclusion reproducible from the same rows.

    Only modes the engine has a route for reach the histogram.
    `S1_ROUTE_BY_FAILURE_MODE` raises on a key it cannot route, so a bucket this
    file invented would take down the diagnosis instead of the eval.
    """
    routable = set(routable_modes())
    modes: dict[int, str | None] = {
        row["row_index"]: row["failure_mode"] for row in rows
    }

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(normalise_answer(row["input"]), []).append(row)
    for members in groups.values():
        if len(members) < 2:
            continue
        if len({bool(m["correct"]) for m in members}) < 2:
            continue
        for member in members:
            if not member["correct"]:
                modes[member["row_index"]] = "inconsistent"

    counts: Counter[str] = Counter()
    unclassified = 0
    dropped: set[str] = set()
    for mode in modes.values():
        if not mode:
            continue
        if mode == UNCLASSIFIED:
            unclassified += 1
        elif mode in routable:
            counts[mode] += 1
        else:  # pragma: no cover - nothing in this file produces one today
            dropped.add(mode)
            unclassified += 1
    return dict(counts), unclassified, sorted(dropped)


def read(run_id: int, *, failures: int = 20) -> dict[str, Any]:
    """One stored run as the report shape the siblings consume.

    Reads only this module's own tables. It is NOT a reader of the claim ledger
    or the transcript, so wall 3 does not apply to it and it is safe to call from
    a tool that measures nothing; `run_eval` calls it after it has finished
    stamping, from its own results, which are its own instrument's readings and
    not anybody's claim.
    """
    run = get_run(run_id)
    if run is None:
        return {"ok": False, "error": "no_such_run", "run_id": int(run_id)}

    rows = results_for(run_id)
    graded = len(rows)
    planned = int(run["planned"])
    complete = graded >= planned and planned > 0
    metric = str(run["metric"])

    scores: dict[str, float] = {}
    if graded:
        for name in METRICS:
            hits = [row["verdicts"].get(name) for row in rows]
            if all(hit is not None for hit in hits):
                scores[name] = sum(1 for hit in hits if hit) / graded

    correct = sum(1 for row in rows if row["correct"])
    histogram, unclassified, dropped = _histogram(rows)
    failing = [row for row in rows if row["failure_mode"]]

    payload: dict[str, Any] = {
        "ok": True,
        "run_id": int(run["id"]),
        "thread_id": int(run["thread_id"]),
        "complete": complete,
        "reused": False,
        "eval_path": run["eval_path"],
        "eval_fingerprint": run["eval_fingerprint"],
        "signature": run["signature"],
        "input_field": run["input_field"],
        "expected_field": run["expected_field"],
        "metric": metric,
        "prompt": run["prompt"],
        "prompt_is_default": bool(run["prompt_is_default"]),
        "provider": run["provider_name"],
        "model": run["model"],
        "locality": run["locality"],
        "judge_model": run["judge_model"],
        "planned": planned,
        "graded": graded,
        "correct": correct,
        "rows_available": int(run["rows_available"]),
        "score": (correct / graded) if (graded and complete) else None,
        "partial_score": (correct / graded) if graded and not complete else None,
        "scores": scores,
        "trivial_baseline_score": run["trivial_baseline"],
        "trivial_answer": run["trivial_answer"],
        "resolution": resolution_for(correct, graded, int(run["rows_available"])),
        "failure_histogram": histogram,
        "unclassified": unclassified,
        "failures": [
            {
                "row_index": row["row_index"],
                "input": row["input"],
                "expected": row["expected"],
                "answer": row["answer"],
                "failure_mode": row["failure_mode"],
                "verdicts": row["verdicts"],
                "graded_by": row["graded_by"],
                "bucketed_by": row["bucketed_by"],
                "seconds": row["seconds"],
            }
            for row in failing[: max(0, int(failures))]
        ],
        "failures_total": len(failing),
        "self_graded": _self_graded(run, rows, scores),
        "buckets_decided_by": (
            "rules in app/tools/evals.py that a person can reproduce by eye; no "
            "model was asked why a row failed"
        ),
    }
    if dropped:  # pragma: no cover - unreachable from this file's rules
        payload["modes_the_engine_cannot_route"] = dropped
    payload["summary"] = _summarise(payload)
    return payload


def _self_graded(
    run: dict[str, Any], rows: list[dict[str, Any]], scores: dict[str, float]
) -> dict[str, Any] | None:
    """The block that makes a model-graded score impossible to read as a rule.

    Returned only when a judge actually graded rows. It names the judge, says
    whether it is the same connection that produced the answers, counts the rows
    it decided, and puts the deterministic scores beside it - so a judge claiming
    ninety per cent where exact match says forty is a visible gap and not
    something a reader has to go and derive.
    """
    judge = run["judge_model"]
    if not judge:
        return None
    judged = [row for row in rows if str(row["graded_by"]).startswith("model:")]
    if not judged:
        return None
    same = str(judge) == str(run["model"])
    return {
        "judge_model": judge,
        "rows_judged": len(judged),
        "is_the_model_that_answered": same,
        "deterministic_scores_on_the_same_rows": {
            name: scores[name] for name in (EXACT_MATCH, CONTAINS) if name in scores
        },
        "warning": (
            (
                f"{judge} graded its own answers. A model asked whether it was "
                "right will tend to say yes, and that is the failure this whole "
                "product exists to survive."
                if same
                else f"{judge} graded another model's answers. That is weaker "
                "self-assessment than a model grading itself, and it is still a "
                "model rather than a rule."
            )
            + " The exact-match and contains scores above were computed on the "
            "same rows for free; read the gap between them and the judge before "
            "believing the judge."
        ),
    }


def _summarise(payload: dict[str, Any]) -> str:
    """The one-line sentence, with the resolution attached to the score."""
    if not payload["complete"]:
        return (
            f"Graded {payload['graded']} of {payload['planned']} rows of "
            f"{payload['eval_path']} and stopped. Nothing was recorded as measured "
            "- a score from a run that did not finish is not a score. Every graded "
            "row is on disk; run this again with the same arguments and it "
            "continues with the ones it has not reached."
        )
    trivial = payload["trivial_baseline_score"]
    trivial_line = (
        f" Always answering {payload['trivial_answer']!r} scores {trivial:.0%} on "
        "the same rows."
        if trivial is not None
        else ""
    )
    buckets = payload["failure_histogram"]
    bucket_line = (
        " Failures bucket as "
        + ", ".join(f"{k} {v}" for k, v in sorted(buckets.items(), key=lambda kv: -kv[1]))
        + "."
        if buckets
        else ""
    )
    unclassified = payload["unclassified"]
    unclassified_line = (
        f" {unclassified} failure(s) could not be bucketed by rule and are left "
        "out of the histogram rather than guessed at."
        if unclassified
        else ""
    )
    return (
        f"{payload['model']} scores {payload['score']:.0%} on {payload['graded']} "
        f"rows of {payload['eval_path']}, graded by {payload['metric']}."
        + trivial_line
        + f" {payload['resolution']['says']}"
        + bucket_line
        + unclassified_line
    )


# ---------------------------------------------------------------------------
# Comparison. The refusal is the point.


def compare(run_id: int, against: int, *, failures: int = 20) -> dict[str, Any]:
    """Two runs over the same eval set, paired row by row. `run_id` is the new one.

    REFUSES TWO RUNS WITH DIFFERENT `eval_fingerprint`s. Two scores measured on
    two different eval sets are two facts, not a delta, and subtracting them is
    the most common way a person convinces themselves a change worked.

    The verdict is McNemar's exact test over the rows that changed, and when it
    cannot separate the two the answer is NO EVIDENCE in those words, with the
    number of rows that would be needed. A prompt change is cheap enough to make
    forty times; a user shown forty unresolvable deltas will believe the tenth.

    EVERY NUMBER IN THE HEADLINE IS MEASURED ON THE ROWS BOTH RUNS GRADED.
    `delta`, `score`, `score_against` and `resolution` are all over the
    intersection, so `delta` is identically `(improved - regressed) /
    paired_rows` and the big number on the card cannot contradict the counts
    printed under it. A shared fingerprint says the two runs are about the same
    eval SET; it says nothing about which rows either of them graded, because
    `sample` and `hold_out` decide that and neither is in the fingerprint. The
    difference of the two runs' own aggregate scores is still reported - it is a
    real fact about two runs - under `aggregate`, where it is named as being over
    two different row sets. The full argument, and the measured card that made it
    necessary, is in the module docstring under THE DELTA IS PAIRED.
    """
    new = read(run_id, failures=failures)
    old = read(against, failures=0)
    if not new.get("ok"):
        return new
    if not old.get("ok"):
        return old
    if new["eval_fingerprint"] != old["eval_fingerprint"]:
        return {
            "ok": False,
            "error": "different_eval_sets",
            "detail": (
                f"Run {run_id} graded {new['eval_path']} and run {against} graded "
                f"{old['eval_path']}, and their graded rows do not hash to the same "
                "eval set. Two scores on two different sets are two facts, not a "
                "delta. Re-run both against the same file, with the same fields, "
                "and compare then."
            ),
        }
    if not (new["complete"] and old["complete"]):
        # NAME THE RUN, AND GIVE ADVICE THAT RUN CAN TAKE. This said "run_eval
        # with the same arguments continues where it stopped" about whichever
        # run was short - which is true of every run `run_eval` made and
        # impossible for a sandbox arm: `run_eval` generates through a
        # connection and cannot generate from an adapter, and
        # `score_the_adapter` does not resume. A person following that sentence
        # would have run the wrong tool and got a different model's answers.
        unfinished = [
            (identifier, report)
            for identifier, report in ((run_id, new), (against, old))
            if not report["complete"]
        ]
        pieces = []
        for identifier, report in unfinished:
            pieces.append(
                f"Run {identifier} graded {report['graded']} of its "
                f"{report['planned']} planned rows"
                + (
                    " - run_eval with the same arguments continues where it "
                    "stopped."
                    if was_measured_through_a_connection(report)
                    else f" and was produced by {report.get('provider')}, which "
                    "is not a connection: run_eval cannot continue it, because "
                    "nothing outside a sandbox can generate from an adapter, "
                    "and score_the_adapter does not resume. Score it again with "
                    "a longer bound or over fewer rows."
                )
            )
        return {
            "ok": False,
            "error": "incomplete_run",
            "detail": (
                "A run that did not finish has no score, and a comparison over "
                "the rows that happened to finish is a comparison over the rows "
                "that were quickest. " + " ".join(pieces)
            ),
            "complete": {str(run_id): new["complete"], str(against): old["complete"]},
        }

    new_rows = {row["row_index"]: row for row in results_for(run_id)}
    old_rows = {row["row_index"]: row for row in results_for(against)}
    shared = sorted(set(new_rows) & set(old_rows))
    only_new = sorted(set(new_rows) - set(old_rows))
    only_old = sorted(set(old_rows) - set(new_rows))
    keep = max(0, int(failures))

    if not shared:
        # NOT "not one of the 0 rows changed its verdict", WHICH IS WHAT THIS
        # SAID. Two runs with no graded row in common have not been compared at
        # all, and a sentence about zero rows agreeing reads as agreement. The
        # fingerprints match here by construction - this is one eval set, graded
        # twice, on disjoint slices of it - which is precisely why the
        # fingerprint could not have caught it.
        return {
            "ok": False,
            "error": "no_shared_rows",
            "detail": (
                f"Run {run_id} graded {new['graded']} rows and run {against} graded "
                f"{old['graded']}, and not one row index is in both. They are the "
                "same eval set graded on disjoint slices of it, so there is nothing "
                "to pair and no difference between them to report. Score both over "
                "an overlapping set of rows and ask again."
            ),
            "eval_fingerprint": new["eval_fingerprint"],
            "paired_rows": 0,
            "graded": {str(run_id): new["graded"], str(against): old["graded"]},
            "only_this_run_graded": only_new[:keep],
            "only_the_other_graded": only_old[:keep],
        }

    improved = [i for i in shared if new_rows[i]["correct"] and not old_rows[i]["correct"]]
    regressed = [i for i in shared if old_rows[i]["correct"] and not new_rows[i]["correct"]]
    changed = len(improved) + len(regressed)
    p_value = mcnemar(len(improved), len(regressed))

    # THE HEADLINE, MEASURED ON THE ROWS BOTH RUNS GRADED AND ON NOTHING ELSE.
    # `delta` is `(len(improved) - len(regressed)) / len(shared)` by
    # construction, which is what makes it impossible for the big number to
    # disagree with the strip beneath it.
    new_correct = sum(1 for i in shared if new_rows[i]["correct"])
    old_correct = sum(1 for i in shared if old_rows[i]["correct"])
    paired_new = new_correct / len(shared)
    paired_old = old_correct / len(shared)
    delta = paired_new - paired_old
    same_rows = not only_new and not only_old

    needed = rows_for_points(abs(delta) * 100.0) if delta else None
    resolved = p_value <= 0.05 and changed > 0

    aggregate_difference = (new["score"] or 0.0) - (old["score"] or 0.0)
    aggregate_says = (
        (
            f"Both runs graded the same {len(shared)} rows, so each run's own "
            f"score over its own rows is the paired score and this difference is "
            f"the reported one."
        )
        if same_rows
        else (
            f"Run {run_id} scored {new['score']:.1%} over its own {new['graded']} "
            f"rows and run {against} scored {old['score']:.1%} over its own "
            f"{old['graded']}. Those are two different row sets - "
            f"{len(only_old)} row(s) only run {against} graded and "
            f"{len(only_new)} row(s) only run {run_id} graded - so their "
            f"difference of {aggregate_difference:+.1%} is a fact about two runs "
            "and is NOT the difference between them. The reported delta is "
            f"{delta:+.1%}, measured on the {len(shared)} rows both graded."
        )
    )

    mismatch = (
        ""
        if same_rows
        else (
            f" These two runs did not grade the same rows: {len(only_old)} row(s) "
            f"only run {against} graded and {len(only_new)} row(s) only run "
            f"{run_id} graded are excluded from both sides. Subtracting their own "
            f"aggregate scores would have said {aggregate_difference:+.1%}, over "
            "two different row sets."
        )
    )

    if resolved:
        says = (
            f"{delta:+.1%} on {len(shared)} paired rows: {len(improved)} rows "
            f"improved and {len(regressed)} regressed, McNemar exact p={p_value:.3g}. "
            "That is a real difference on this eval set." + mismatch
        )
    elif changed == 0:
        says = (
            f"Not one of the {len(shared)} rows changed its verdict. These two are "
            "the same on this eval set - there is no evidence of any difference, "
            "and none to report as a small win." + mismatch
        )
    else:
        says = (
            f"NO EVIDENCE. The scores differ by {delta:+.1%} on the "
            f"{len(shared)} rows both runs graded, but only {changed} of them "
            f"changed ({len(improved)} improved, "
            f"{len(regressed)} regressed) and McNemar's exact test gives "
            f"p={p_value:.3g}. This eval set cannot tell these two apart. "
            + (
                f"Grade {needed - len(shared)} more rows and ask again."
                if needed and needed > len(shared)
                else "Grade more rows and ask again."
            )
            + mismatch
        )

    return {
        "ok": True,
        "run_id": int(run_id),
        "against": int(against),
        "eval_fingerprint": new["eval_fingerprint"],
        "paired_rows": len(shared),
        "same_rows": same_rows,
        "score": paired_new,
        "score_against": paired_old,
        "delta": delta,
        "correct": new_correct,
        "correct_against": old_correct,
        "improved": len(improved),
        "regressed": len(regressed),
        "changed": changed,
        "p_value": p_value,
        "test": "McNemar, two-sided exact binomial over the rows that changed",
        "resolved": resolved,
        "verdict": "different" if resolved else "no_evidence",
        "rows_that_would_resolve_this_delta": needed,
        "improved_rows": improved[:keep],
        "regressed_rows": regressed[:keep],
        "measured_on": (
            "the rows both runs graded, which is the only set on which a "
            "difference between them means anything"
        ),
        # DEMOTED, NOT DELETED. Each run's own aggregate over its own rows is a
        # real number and somebody will want it; what it is not is the
        # difference between the two runs, and it is labelled here rather than
        # printed as the headline.
        "aggregate": {
            "score": new["score"],
            "score_against": old["score"],
            "difference": aggregate_difference,
            "rows": new["graded"],
            "rows_against": old["graded"],
            "only_this_run_graded": only_new[:keep],
            "only_the_other_graded": only_old[:keep],
            "only_this_run_graded_count": len(only_new),
            "only_the_other_graded_count": len(only_old),
            "says": aggregate_says,
        },
        "prompts": {str(run_id): new["prompt"], str(against): old["prompt"]},
        "resolution": resolution_for(new_correct, len(shared)),
        "says": says,
        "summary": says,
    }


# ---------------------------------------------------------------------------
# Asking the model.


def _ask(
    adapter: Any, key: str | None, system: str, question: str
) -> tuple[str, str | None, float]:
    """One question, one answer, one clock. Returns `(text, error, seconds)`.

    The same `Delta` handling as `measure._ask`, which is deliberate - a baseline
    and an eval score have to be produced by the same instrument or they were
    never comparable. What is added is the system prompt as a parameter, because
    the prompt is what the prompt bench changes, and the elapsed time, because
    `too_slow` is a routable failure mode and it has to be decided on a reading.

    Never raises: a dead endpoint is a report.

    `perf_counter` AND NOT `monotonic`, WHICH IS A MEASUREMENT DEFECT AND NOT A
    STYLE CHOICE. On Windows - the platform this product is being built on -
    `time.monotonic()` is `GetTickCount64`, whose resolution is about 15.6
    milliseconds, so every row faster than that reads as ZERO seconds. That is a
    made-up number in a column this file stores and buckets on: a
    `latency_budget_ms` under about sixteen milliseconds could never be exceeded
    however slow the model was, and `seconds` on a fast local model would be
    stored as 0.0 for every row. `perf_counter` is the high-resolution clock and
    is what a short interval is measured with. The run-level deadline below stays
    on `monotonic`, where minutes are the unit and coarse is correct.
    """
    conversation = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]
    parts: list[str] = []
    thought: list[str] = []
    started = time.perf_counter()
    try:
        for delta in adapter.stream(conversation, None, secret=key):
            if not isinstance(delta, Delta):
                continue
            if delta.kind == "text" and delta.text:
                parts.append(delta.text)
            elif delta.kind == "reasoning" and delta.text:
                thought.append(delta.text)
            elif delta.kind == "error":
                return "", delta.detail, time.perf_counter() - started
    except Exception as error:  # noqa: BLE001 - a dead endpoint is a report
        return "", f"{type(error).__name__}: {error}", time.perf_counter() - started
    # The same rule as `measure._ask`: an answer given only as reasoning is an
    # answer, or a baseline and an eval score would read the same model apart.
    text = "".join(parts).strip() or "".join(thought).strip()
    return text, None, time.perf_counter() - started


_VERDICT_WORD = re.compile(r"[A-Za-z]+")


def _read_verdict(text: str) -> bool | None:
    """`True` / `False` / `None` from a judge's reply. `None` means unreadable.

    INCORRECT is checked first because it contains CORRECT, which is the one
    parsing mistake in this function that would silently invert a grade.

    `None` is not a third grade and it is not counted as a failure: it stops the
    run. Reading an unreadable verdict as INCORRECT would be a reading nobody
    made, and reading it as CORRECT would be that plus flattery.
    """
    match = _VERDICT_WORD.search(str(text or ""))
    if not match:
        return None
    word = match.group(0).upper()
    if word == "INCORRECT":
        return False
    if word == "CORRECT":
        return True
    return None


# ---------------------------------------------------------------------------
# The run itself.


#: Extensions an eval set can be in. The same list `dataquality` reads rows
#: from, kept short here because this is a NAME search and not a reader.
_ROW_SUFFIXES = (".jsonl", ".ndjson", ".csv", ".tsv", ".json")

#: How many candidate files a refusal prints.
_CANDIDATES_NAMED = 12


def eval_files_under_the_workspace(thread_id: int | None) -> list[str]:
    """Files in this thread's project folder whose name says they are an eval set.

    THE REFUSAL THAT POINTS AT A FILE THAT EXISTS. Max's run of 2026-09-19/20:
    eleven `measure_baseline`/`run_eval` calls asked for `eval.jsonl` at the
    project root, which is not there, and got "no rows could be read" eleven
    times. The file it wanted was three folders down. A refusal that says only
    that the path is empty leaves the model to guess the path again, and it
    guessed the same one eleven times.

    A FILESYSTEM READING, NOT A CLAIM. `measure_baseline` holds a measuring
    instrument, so `events.since` and the claim ledger are both closed to it -
    `evidence.refuse_a_minting_reader`, and rightly: a tool that can stamp
    MEASURED must not read what anybody asserted. What is on the disk is not an
    assertion. This walks the project's own folder, matches on NAME only, and
    reads not one byte of any of them.
    """
    if thread_id is None:
        return []
    try:
        from app import db, events as _events

        thread = _events.get_thread(int(thread_id))
        project_id = (thread or {}).get("project_id")
        project = db.get_project(int(project_id)) if project_id else None
        root = (project or {}).get("root_path")
    except Exception:  # noqa: BLE001 - a broken lookup must not break a refusal
        return []
    if not root:
        return []
    base = Path(str(root))
    if not base.is_dir():
        return []
    found: list[str] = []
    try:
        for candidate in sorted(base.rglob("*")):
            if len(found) >= _CANDIDATES_NAMED:
                break
            if not candidate.is_file():
                continue
            if candidate.suffix.lower() not in _ROW_SUFFIXES:
                continue
            if "eval" not in candidate.name.lower():
                continue
            found.append(str(candidate.relative_to(base)).replace("\\", "/"))
    except OSError:
        return []
    return found


def _and_what_is_on_disk(thread_id: int | None, eval_path: str) -> dict[str, Any]:
    """The `where it actually is` half of a refusal, or {} when there is none."""
    if Path(eval_path).exists():
        return {}
    candidates = eval_files_under_the_workspace(thread_id)
    if not candidates:
        return {}
    return {
        "there_is_nothing_at_that_path": eval_path,
        "files_under_this_project_whose_name_says_eval": candidates,
        "so": (
            "call this again with eval_path set to one of those, relative to the "
            "project folder. Matched on the file NAME alone - nothing in them was "
            "read - so check it is the split you meant before you grade on it."
        ),
    }


def _plan(
    eval_path: str,
    input_field: str,
    expected_field: str,
    sample: int,
    hold_out: tuple[int, ...],
) -> dict[str, Any]:
    """One streaming pass over the eval file: choose the rows and hash the set.

    STREAMED, NOT COLLECTED, for `measure_baseline`'s reason - the whole eval set
    held in memory in order to grade at most `sample` rows of it is how a
    five-million-row eval set becomes a memory error. What is kept is the chosen
    rows, two counts, the column names and a rolling hash.

    The file is read TO THE END even when `sample` is small, because the hash has
    to cover the whole eval set for "this is the same eval set" to mean anything.
    That is one local pass, against a run that is about to spend the user's tokens
    on every chosen row.

    `row_index` counts ELIGIBLE rows - the ones with both fields - from 0, in file
    order. Not the file's line number: a ragged file would then hand out indexes
    that move when a blank line is deleted, and `row_index` is what a paired
    comparison and `hold_out` are both keyed on.
    """
    seen = 0
    available = 0
    generated = 0
    names: set[str] = set()
    chosen: list[tuple[int, str, str]] = []
    everything: list[tuple[int, str, str]] = []
    excluded = set(int(i) for i in hold_out)

    stream = dataquality.iter_records(eval_path)
    try:
        for record in stream:
            if not isinstance(record, dict):
                record = {"value": record}
            seen += 1
            # Wall 8, counted in the pass this function already makes over
            # every row. The caller decides what to do with it; this only
            # reports, because reading and refusing are different jobs.
            if dataquality.is_synthetic_row(record):
                generated += 1
            if len(names) < dataquality.COLUMN_CAP:
                names.update(str(key) for key in record)
            question = record.get(input_field)
            expected = record.get(expected_field)
            if question is None or expected is None:
                continue
            index = available
            available += 1
            pair = (index, str(question), str(expected))
            everything.append(pair)
            if index in excluded:
                continue
            if len(chosen) < sample:
                chosen.append(pair)
    finally:
        # See `dataquality.count_rows`: an abandoned generator holds its file
        # handle until the collector runs, which on Windows keeps the directory.
        stream.close()

    return {
        "seen": seen,
        "available": available,
        "generated": generated,
        "columns": sorted(names),
        "chosen": chosen,
        # OVER `everything` AND DELIBERATELY NOT OVER `chosen`. This names the
        # eval SET - the file and the two columns - so that two runs at
        # different `sample` sizes, or with different `hold_out` rows, are
        # recognised as being about the same set rather than refused as two
        # different ones. Which ROWS a run graded is not hashed here at all: it
        # is written to `eval_results` a row at a time, and `compare` reads it
        # from there. See THE DELTA IS PAIRED in the module docstring for the
        # measured card this distinction was collapsed into.
        "fingerprint": fingerprint_pairs(everything),
    }


def run(
    *,
    eval_path: str,
    input_field: str,
    expected_field: str,
    thread_id: int,
    prompt: str | None = None,
    metric: str = EXACT_MATCH,
    sample: int = DEFAULT_EVAL_SAMPLE,
    provider_id: int | None = None,
    judge_provider_id: int | None = None,
    latency_budget_ms: int | None = None,
    hold_out: Iterable[int] = (),
    deadline_seconds: float | None = DEFAULT_DEADLINE_SECONDS,
    rerun: bool = False,
    actor: str = evidence.MODEL,
) -> dict[str, Any]:
    """Run an eval set, keep every row, and return the report. No stamping here.

    Separated from the tool handler on purpose: the tool holds the instrument and
    decides what may be stamped, and this holds the work. A sibling bench that
    wants a score without touching the fact ledger calls this; nothing here can
    write a fact, because nothing here has an `Instrument`.
    """
    metric = str(metric)
    if metric not in METRICS:
        return {
            "ok": False,
            "error": "unknown_metric",
            "detail": (
                f"{metric!r} is not a metric this bench has. It grades with "
                f"{', '.join(METRICS)}. `{MODEL_GRADED}` is the user's own model "
                "grading its own answers and is opt-in for that reason."
            ),
            "metrics": list(METRICS),
        }
    if thread_id is None:
        return {
            "ok": False,
            "error": "no_thread",
            "detail": evidence.thread_is_required_by("run_eval")
            or (
                "An eval run belongs to one conversation: its rows, its score and "
                "every fact it produces are thread-scoped."
            ),
            **evidence.thread_id_help("run_eval"),
        }
    if not evidence.names_a_conversation(thread_id):
        return {
            "ok": False,
            "error": "no_such_thread",
            "detail": (
                f"There is no conversation {thread_id!r} on this machine, so there "
                "is nowhere to file this run. Nothing was asked and nothing was "
                "spent."
            ),
        }

    # Clamped by COMPARISON rather than by `int()`, for `_as_number`'s reason:
    # a comparison returns a bool and remembers nothing, and `wanted` is only
    # ever used to bound `len(chosen)`. The number that is stored and signed is
    # `len(chosen)` - a count of rows this code chose - and never this.
    wanted = _as_number(sample, DEFAULT_EVAL_SAMPLE)
    if not isinstance(wanted, (int, float)):
        wanted = DEFAULT_EVAL_SAMPLE
    if wanted > MAX_EVAL_SAMPLE:
        wanted = MAX_EVAL_SAMPLE
    elif wanted < 1:
        wanted = 1

    row = store.get(int(provider_id)) if provider_id else store.active()
    if row is None:
        return {
            "ok": False,
            "error": "no_provider",
            "summary": (
                "No model is connected, so there is nothing to run the eval "
                "against. Connect one and run this again."
            ),
        }

    # TAKEN FROM `measure_baseline` VERBATIM, sentence included. The person may
    # send their own data wherever they like; a model asking to send it on their
    # behalf is a different event, and a second door with a weaker rule is the
    # same as no rule.
    if row["kind"] != "local" and actor != evidence.USER:
        return {
            "ok": False,
            "error": "remote_needs_the_user",
            "summary": (
                f"Running this eval would send rows of {eval_path} to "
                f"{row['name']}, which is not on this machine. I will not do that "
                "because a model asked me to. Start it from the control yourself, "
                "or connect a local model and ask again."
            ),
            "provider": row["name"],
            "locality": row["kind"],
        }

    judge_row = row
    if metric == MODEL_GRADED and judge_provider_id:
        judge_row = store.get(int(judge_provider_id))
        if judge_row is None:
            return {
                "ok": False,
                "error": "no_such_judge",
                "detail": f"There is no connection {int(judge_provider_id)} to grade with.",
            }
        if judge_row["kind"] != "local" and actor != evidence.USER:
            return {
                "ok": False,
                "error": "remote_needs_the_user",
                "summary": (
                    f"Grading with {judge_row['name']} would send the eval rows and "
                    "the model's answers off this machine. Start it yourself."
                ),
            }

    system_prompt = measure.BASELINE_SYSTEM if prompt is None else str(prompt)
    is_default = prompt is None or str(prompt) == measure.BASELINE_SYSTEM
    held = tuple(sorted({int(i) for i in (hold_out or ())}))
    budget = _as_number(latency_budget_ms) or None
    limit = _as_number(deadline_seconds)

    plan = _plan(eval_path, input_field, expected_field, wanted, held)
    if not plan["seen"]:
        return {
            "ok": False,
            "error": "no_rows",
            "summary": (
                f"No rows could be read from {eval_path}, so there is nothing to "
                "grade. Nothing was recorded."
            ),
            "eval_path": eval_path,
            "the_path_exists": Path(eval_path).exists(),
            **_and_what_is_on_disk(thread_id, eval_path),
        }
    if plan["generated"]:
        # WALL 8, BEFORE A SINGLE ROW IS SENT ANYWHERE. `measure_baseline` gives
        # the same refusal for the same two reasons: every graded row is the
        # user's money, and G1 takes all three of its facts from one run or none
        # of them. The stamp itself is walled too - `measured(from_file=...)` -
        # and this is the door that keeps the wall from costing anybody a run.
        return {
            "ok": False,
            "error": "generated_rows",
            "summary": (
                f"{plan['generated']} of the {plan['seen']} rows in {eval_path} "
                "are rows this harness generated, so nothing was graded and "
                "nothing was recorded. An eval run over invented rows scores a "
                "distribution we made up, and G1 would open on the result. The "
                f"{plan['seen'] - plan['generated']} real rows in there are still "
                "real: put them in a file of their own and grade that."
            ),
            "eval_path": eval_path,
            "rows": plan["seen"],
            "generated_rows": plan["generated"],
        }
    if not plan["available"]:
        return {
            "ok": False,
            "error": "no_such_columns",
            "summary": (
                f"No row in {eval_path} has both {input_field!r} and "
                f"{expected_field!r}. The columns present are {plan['columns']}. "
                "Nothing was graded."
            ),
            "eval_path": eval_path,
            "columns": plan["columns"],
            **_and_what_is_on_disk(thread_id, eval_path),
        }
    chosen = plan["chosen"]
    if not chosen:
        return {
            "ok": False,
            "error": "everything_held_out",
            "summary": (
                f"All {plan['available']} eligible rows of {eval_path} are in "
                "hold_out, so there is nothing left to score on. Exemplars have to "
                "come out of the score, but not all of it."
            ),
        }

    judge_model = str(judge_row["model"]) if metric == MODEL_GRADED else ""
    signature = signature_for(
        eval_fingerprint=plan["fingerprint"],
        input_field=str(input_field),
        expected_field=str(expected_field),
        adapter=str(row["adapter"]),
        base_url=str(row["base_url"]),
        model=str(row["model"]),
        prompt=system_prompt,
        metric=metric,
        judge_model=judge_model,
        sample=len(chosen),
        hold_out=held,
        latency_budget_ms=budget,
    )

    counts = Counter(normalise_answer(expected) for _, _, expected in chosen)
    trivial_answer, trivial_hits = counts.most_common(1)[0]
    trivial = trivial_hits / len(chosen)

    existing = None if rerun else _latest_matching(int(thread_id), signature)
    if existing is not None and int(existing["planned"]) != len(chosen):
        # Defensive: the signature covers everything that decides the row set, so
        # this should be unreachable. If it ever is reached, a fresh run is the
        # answer - resuming into a plan that is not the stored plan would grade
        # different rows under one run id and make every pairing wrong.
        existing = None

    if existing is not None:
        already = len(results_for(int(existing["id"])))
        if already >= int(existing["planned"]):
            report = read(int(existing["id"]))
            report["reused"] = True
            report["summary"] = (
                "This exact eval - same rows, same prompt, same model, same metric "
                "- has already been run in this conversation. Answered from the "
                f"stored run {existing['id']} without asking the model anything, so "
                "it cost nothing. Pass rerun=true to spend the tokens again; note "
                "that nothing here promises the answers would be identical, only "
                "that the question is. " + report["summary"]
            )
            _emit(REUSED, thread_id, {"run_id": int(existing["id"]), "rows": already})
            return report
        run_row = existing
    else:
        run_row = create_run(
            thread_id=int(thread_id),
            signature=signature,
            eval_path=str(eval_path),
            eval_fingerprint=plan["fingerprint"],
            input_field=str(input_field),
            expected_field=str(expected_field),
            metric=metric,
            prompt=system_prompt,
            prompt_is_default=1 if is_default else 0,
            provider_id=int(row["id"]),
            provider_name=str(row["name"]),
            model=str(row["model"]),
            locality=str(row["kind"]),
            judge_model=judge_model or None,
            planned=len(chosen),
            rows_available=int(plan["available"]),
            trivial_baseline=float(trivial),
            trivial_answer=str(trivial_answer),
            latency_budget_ms=budget,
        )

    run_id = int(run_row["id"])
    done = {int(r["row_index"]) for r in results_for(run_id)}
    outstanding = [item for item in chosen if item[0] not in done]
    labels = _label_set(expected for _, _, expected in chosen)

    _emit(
        STARTED,
        thread_id,
        {
            "run_id": run_id,
            "eval_path": str(eval_path),
            "model": str(row["model"]),
            "metric": metric,
            "planned": len(chosen),
            "already_graded": len(done),
            "prompt_is_default": is_default,
        },
    )

    adapter = build(row["adapter"], row["base_url"], row["model"])
    key = secrets.get_key(str(row["id"]))
    judge_adapter = None
    judge_key = None
    if metric == MODEL_GRADED:
        judge_adapter = build(
            judge_row["adapter"], judge_row["base_url"], judge_row["model"]
        )
        judge_key = secrets.get_key(str(judge_row["id"]))

    started_at = time.monotonic()
    stopped: dict[str, Any] | None = None
    graded_now = 0

    try:
        for index, question, expected in outstanding:
            if limit is not None and (time.monotonic() - started_at) >= limit:
                stopped = {
                    "error": "deadline",
                    "detail": (
                        f"Stopped after {limit:g} seconds with "
                        f"{len(done) + graded_now} of {len(chosen)} rows graded. "
                        "Every graded row is on disk. Run this again with the same "
                        "arguments and it continues from where it stopped."
                    ),
                }
                break

            answer, error, seconds = _ask(adapter, key, system_prompt, question)
            if error is not None:
                stopped = {
                    "error": "model_failed",
                    "detail": (
                        f"The connected model stopped answering at row {index}: "
                        f"{error}. The {len(done) + graded_now} rows already graded "
                        "are kept - run this again to continue. If this one row is "
                        "the problem, put its index in hold_out."
                    ),
                    "row_index": index,
                }
                break

            verdicts = grade(expected, answer)
            graded_by = metric
            if metric == MODEL_GRADED:
                verdict, judge_error, judge_seconds = _ask(
                    judge_adapter,
                    judge_key,
                    JUDGE_SYSTEM,
                    _judge_question(question, expected, answer),
                )
                if judge_error is not None:
                    stopped = {
                        "error": "judge_failed",
                        "detail": (
                            f"The grading model stopped answering at row {index}: "
                            f"{judge_error}. Rows already graded are kept."
                        ),
                        "row_index": index,
                    }
                    break
                read_back = _read_verdict(verdict)
                if read_back is None:
                    stopped = {
                        "error": "judge_unreadable",
                        "detail": (
                            f"The grading model was asked for CORRECT or INCORRECT "
                            f"at row {index} and said {verdict[:200]!r}. That is not "
                            "a verdict, and reading it as either one would be a "
                            "reading nobody made. Rows already graded are kept; "
                            f"score this run with {EXACT_MATCH} or {CONTAINS}, or "
                            "grade with a model that follows the instruction."
                        ),
                        "row_index": index,
                        "judge_said": verdict[:200],
                    }
                    break
                verdicts[MODEL_GRADED] = read_back
                graded_by = f"model:{judge_row['model']}"
                seconds += judge_seconds

            correct = bool(verdicts[metric])
            mode: str | None = None
            if not correct:
                mode = bucket(expected, answer, verdicts, labels)
            elif budget is not None and seconds * 1000.0 > budget:
                mode = "too_slow"

            record_row(
                run_id,
                index,
                question=question,
                expected=expected,
                answer=answer,
                correct=correct,
                verdicts=verdicts,
                failure_mode=mode,
                graded_by=graded_by,
                seconds=seconds,
            )
            graded_now += 1
            if graded_now % PROGRESS_STRIDE == 0:
                _emit(
                    PROGRESS,
                    thread_id,
                    {
                        "run_id": run_id,
                        "graded": len(done) + graded_now,
                        "planned": len(chosen),
                        "seconds": round(time.monotonic() - started_at, 2),
                    },
                )
    finally:
        key = None
        judge_key = None

    report = read(run_id)
    report["rows_graded_now"] = graded_now
    report["seconds"] = round(time.monotonic() - started_at, 2)
    if stopped is not None:
        report["ok"] = False
        report.update(stopped)
        report["resumable"] = True
        _emit(
            INTERRUPTED,
            thread_id,
            {"run_id": run_id, "graded": report["graded"], "why": stopped["error"]},
        )
        report["summary"] = stopped["detail"]
    else:
        _emit(
            FINISHED,
            thread_id,
            {
                "run_id": run_id,
                "graded": report["graded"],
                "score": report["score"],
                "metric": metric,
            },
        )
    return report


def _judge_question(question: str, expected: str, answer: str) -> str:
    return (
        f"Question:\n{question}\n\n"
        f"Expected answer:\n{expected}\n\n"
        f"Answer to grade:\n{answer}\n\n"
        "CORRECT or INCORRECT?"
    )


def _emit(kind: str, thread_id: int | None, payload: dict[str, Any]) -> None:
    """One frame onto the append-only spine, best effort.

    `events.append` returns only after the row is committed and its id is the SSE
    event id, which is what lets a client that reconnected mid-eval ask for
    everything after the last id it saw.

    Best effort because a failure to narrate must never lose a graded row: the
    durable record of the work is `eval_results`, and the event log is how the
    conversation watches it happen.
    """
    if thread_id is None:
        return
    try:
        events.append(kind, payload, thread_id=int(thread_id))
    except Exception:  # noqa: BLE001 - narration must not cost a measurement
        pass


# ---------------------------------------------------------------------------
# The two tools.


@tool(
    "run_eval",
    description=(
        "Run an evaluation set against the connected model and keep the result "
        "of every row, not just the score. Grades with exact match by default; "
        "buckets the failures into the diagnosis engine's own failure modes with "
        "rules you can check by eye; and reports the score with the smallest "
        "difference that many rows could resolve, because a score without its "
        "resolution is half a number. Re-running the same eval on the same "
        "prompt against the same model is recognised and answered from disk "
        "rather than billed again, and a run that is interrupted keeps every row "
        "it graded and continues where it stopped. It sends the eval rows to the "
        "connected model, so it will not run against a remote endpoint unless "
        "the user starts it themselves."
    ),
    schema={
        "type": "object",
        "properties": {
            "eval_path": {
                "type": "string",
                "description": "The evaluation file on this machine.",
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
                    "The system prompt to run under. Leave it out to measure the "
                    "BASELINE - what the model already does with a deliberately "
                    "thin instruction. Only a run with the default prompt is "
                    "recorded as the baseline the gates read."
                ),
            },
            "metric": {
                "type": "string",
                "enum": list(METRICS),
                "description": (
                    "How a row is graded. exact_match (default) and contains are "
                    "rules anyone can reproduce. model_graded asks a model whether "
                    "each answer was right, which by default is the same model "
                    "that produced it grading itself - the reply says so, and "
                    "reports the rule-based scores on the same rows beside it."
                ),
            },
            "sample": {
                "type": "integer",
                "description": (
                    f"How many rows to grade. Default {DEFAULT_EVAL_SAMPLE}, "
                    f"maximum {MAX_EVAL_SAMPLE}. The score always says how many "
                    "rows it was measured on and what that many can resolve."
                ),
            },
            "provider_id": {
                "type": "integer",
                "description": "Which connection to evaluate. Default: the active one.",
            },
            "judge_provider_id": {
                "type": "integer",
                "description": (
                    "With metric=model_graded, a different connection to grade "
                    "with. Default: the same one that answered, and the reply says "
                    "so."
                ),
            },
            "latency_budget_ms": {
                "type": "integer",
                "description": (
                    "A per-row time budget. Without one, no row is ever bucketed "
                    "too_slow - there is no such thing as too slow until somebody "
                    "says what fast enough is."
                ),
            },
            "hold_out": {
                "type": "array",
                "items": {"type": "integer"},
                "description": (
                    "Row indexes to leave out of the score. Use it for rows you "
                    "used as few-shot exemplars: scoring on your own exemplars is "
                    "a leak. Indexes count rows that have both fields, from 0."
                ),
            },
            "deadline_seconds": {
                "type": "number",
                "description": (
                    f"Stop cleanly after this long. Default "
                    f"{DEFAULT_DEADLINE_SECONDS:g}. Every graded row is kept and "
                    "calling this again with the same arguments continues."
                ),
            },
            "rerun": {
                "type": "boolean",
                "description": (
                    "Spend the tokens again on an eval that has already been run "
                    "identically in this conversation, instead of answering from "
                    "the stored rows."
                ),
            },
        },
        "required": ["eval_path", "input_field", "expected_field"],
    },
    reads=("filesystem", "datasets", "providers", "evals"),
    writes=("evals", "facts"),
    measures=(
        "baseline_score",
        "trivial_baseline_score",
        "baseline_measured",
        "failure_histogram",
        "failures_seen",
    ),
    # WALL 6, and every one of these four is a real false refusal rather than a
    # convenience. What this tool stamps is a fraction in [0, 1], a second
    # fraction in [0, 1], the boolean `True`, and a histogram. `rerun=true` is
    # the boolean `True` sitting in the arguments, so `baseline_measured` would
    # be refused for equalling it; and `sample`, `deadline_seconds` and
    # `latency_budget_ms` are numbers a caller can perfectly well send as `1` or
    # `0`, which is exactly the value of a score on a run that got everything
    # right or everything wrong. `eval_path`, the two field names and `prompt`
    # are deliberately NOT bounded: they stay quarantined.
    #
    # THE FIFTH FACT NARROWS THIS ARGUMENT AND THE OLD WORDING IS NOW WRONG.
    # This block used to finish "None of the four could ever BE the answer to
    # [the four questions] - each one bounds how much work is done and nothing
    # else." `failures_seen` is a COUNT OF ROWS, and `sample` bounds the rows
    # scored, so on a run where every scored row fails the two are the same
    # number: `sample=40`, forty failures, `failures_seen=40`. The old sentence
    # would have gone on covering a case it was never argued for.
    #
    # The bound still stands, on the narrower ground the registry already names:
    # `sample` says how many rows to score and `failures_seen` is counted off
    # the rows this tool actually graded, so the coincidence is arithmetic
    # rather than laundering. That is wall 1's question - is the source honest -
    # and it is answered by the count being taken from the graded rows and from
    # nowhere else. A reader who wants to check that reads `graded - correct`
    # below, which is the only expression that produces this number.
    bounds=("sample", "deadline_seconds", "latency_budget_ms", "rerun"),
    provides=("measurement.eval.run",),
    label="Run the eval",
    group="Data",
    verb="run the eval set and keep every row",
    order=23,
)
def run_eval(
    eval_path: str,
    input_field: str,
    expected_field: str,
    prompt: str | None = None,
    metric: str = EXACT_MATCH,
    sample: int = DEFAULT_EVAL_SAMPLE,
    provider_id: int | None = None,
    judge_provider_id: int | None = None,
    latency_budget_ms: int | None = None,
    hold_out: list[int] | None = None,
    deadline_seconds: float | None = DEFAULT_DEADLINE_SECONDS,
    rerun: bool = False,
    *,
    instrument: Instrument,
) -> dict[str, Any]:
    """Run it, keep it, bucket it - and stamp only what a finished run earned.

    THREE RULES DECIDE WHAT IS STAMPED, and each one is a refusal:

    **An incomplete run stamps nothing.** `measure_baseline`'s sentence, reused:
    a score from a run that fell over is not a score. It is worse here than
    there, because the rows this bench grades are a PREFIX of the file - a file
    sorted by label would give a partial run a badly biased score, and the
    partial number is reported as `partial_score` where nothing can mistake it
    for the answer.

    **Only a run under the DEFAULT prompt is a baseline.** `G1_BASELINE_MEASURED`
    asks what the best thing that already exists scores, before anybody changes
    anything. A run under a prompt the caller wrote is a measurement of that
    prompt, and stamping it as the baseline would let the prompt bench overwrite
    the number it is supposed to be beating.

    **An empty histogram is not stamped.** `inspect_hardware` established the
    doctrine and it holds here: "the tool ran and found nothing" and "the tool did
    not run" are the same state of knowledge, and the ledger already defaults
    `failure_histogram` to `{}`. A run where nothing failed, or where every
    failure was unclassified, reports that in words and writes no row.

    The instrument cannot be talked out of any of this: `measures=` bounds what
    may be stamped at registration, `Instrument.measured` refuses a value this
    call was handed, and the numbers below are computed from rows this tool wrote
    from answers it received - not from anything in the arguments.
    """
    report = run(
        eval_path=str(eval_path),
        input_field=str(input_field),
        expected_field=str(expected_field),
        thread_id=instrument.thread_id,
        prompt=prompt,
        metric=metric,
        sample=sample,
        provider_id=provider_id,
        judge_provider_id=judge_provider_id,
        latency_budget_ms=latency_budget_ms,
        hold_out=hold_out or (),
        deadline_seconds=deadline_seconds,
        rerun=bool(rerun),
        actor=instrument.actor,
    )

    if not report.get("ok") or not report.get("complete"):
        report["nothing_was_recorded"] = (
            "No fact was stamped. A score from a run that did not finish is not a "
            "score, and a partial run grades a prefix of the file rather than a "
            "sample of it."
        )
        return report

    graded = int(report["graded"])
    correct = int(report["correct"])
    score = float(report["score"])
    metric_used = str(report["metric"])
    how_graded = (
        f"graded by {metric_used}"
        if metric_used != MODEL_GRADED
        else f"graded by {report['judge_model']}, a model, judging"
        + (
            " its own answers"
            if (report.get("self_graded") or {}).get("is_the_model_that_answered")
            else " another model's answers"
        )
    )

    if report["prompt_is_default"]:
        # All three of G1's facts from one run or none of them - the gate's
        # predicate is stronger than a boolean on purpose, and a flag set true
        # with no score behind it is not a measured baseline. The score is
        # stamped FIRST so the boolean is never the only thing this call minted.
        instrument.measured(
            "baseline_score",
            score,
            how=(
                f"{report['model']} answered {correct} of {graded} rows of "
                f"{eval_path} correctly under the default baseline prompt, "
                f"{how_graded}; 95% interval "
                f"{report['resolution']['ci_95'][0]:.0%}-"
                f"{report['resolution']['ci_95'][1]:.0%}"
            ),
            # Wall 8: G1's three facts and the histogram all describe the rows
            # in this file, so all four say which file.
            from_file=eval_path,
        )
        instrument.measured(
            "trivial_baseline_score",
            float(report["trivial_baseline_score"]),
            how=(
                f"always answering {report['trivial_answer']!r} scores "
                f"{report['trivial_baseline_score']:.0%} on the same {graded} rows"
            ),
            from_file=eval_path,
        )
        instrument.measured(
            "baseline_measured",
            True,
            how=(
                f"eval run {report['run_id']} scored {report['model']} on {graded} "
                f"rows of {eval_path}, and every row is on disk"
            ),
            from_file=eval_path,
        )
    else:
        report["not_a_baseline"] = (
            "This run used a prompt you supplied, so it measures that prompt "
            "rather than the baseline. baseline_score was not touched - compare "
            "it against the baseline run with read_eval_results instead."
        )

    histogram = dict(report["failure_histogram"])
    if histogram:
        # THE DENOMINATOR, STAMPED BESIDE THE HISTOGRAM AND NOT ONLY INSIDE THE
        # SENTENCE. The `how` below has always read "N of M failing rows"; M was
        # prose, so `S1_CLASSIFICATION_IS_TOO_THIN` had nothing to divide by and
        # the walk could route on the argmax of a minority. Stamped here rather
        # than in a second place so the two facts cannot disagree about one run.
        instrument.measured(
            "failures_seen",
            graded - correct,
            how=(
                f"eval run {report['run_id']} graded {graded} rows and "
                f"{graded - correct} of them were wrong; this is the count the "
                "failure histogram is a fraction of"
            ),
            from_file=eval_path,
        )
        instrument.measured(
            "failure_histogram",
            histogram,
            how=(
                f"{sum(histogram.values())} of {graded - correct} failing rows of "
                f"eval run {report['run_id']} bucketed by rule (never by a model): "
                + ", ".join(f"{k} {v}" for k, v in sorted(histogram.items()))
                + (
                    f"; {report['unclassified']} failure(s) no rule could name are "
                    "left out rather than guessed at"
                    if report["unclassified"]
                    else ""
                )
            ),
            from_file=eval_path,
        )
    else:
        report["no_histogram_recorded"] = (
            "Nothing was recorded for failure_histogram. "
            + (
                f"All {report['unclassified']} failing row(s) are ones no rule here "
                "can name, and a bucket guessed at would route your whole diagnosis."
                if report["unclassified"]
                else "No row failed under this metric."
            )
            + " A tool that ran and found nothing has the same knowledge as a tool "
            "that did not run, and the ledger already defaults this to {}."
        )
    return report


@tool(
    "rebucket_failures",
    description=(
        "Re-tally the failure histogram of an eval run using YOUR reading of the "
        "rows instead of the automatic one. Use it when the diagnosis says to "
        "re-bucket the failures - when the rule-based buckets named the wrong "
        "thing and the route out of stage 1 depends on getting them right. It "
        "reads the rows the run already graded; it does not re-run anything and "
        "costs no tokens."
    ),
    schema={
        "type": "object",
        "properties": {
            "run_id": {
                "type": "integer",
                "description": (
                    "The eval run whose failures you are re-reading. Its rows are "
                    "what gets re-tallied, so the histogram stays a count of real "
                    "graded rows."
                ),
            },
            "buckets": {
                "type": "object",
                "description": (
                    "Your correction, as {row index: failure mode}. Only the rows "
                    "you name change; every other failing row keeps the bucket the "
                    "rule gave it. A row you do not name is not a row you agreed "
                    "with, it is a row you did not look at, and both are left "
                    "alone."
                ),
            },
        },
        "required": ["run_id", "buckets"],
    },
    reads=("evals",),
    writes=(),
    measures=("failure_histogram", "failures_seen"),
    # WALL 6, AND THIS ONE WAS A REAL FALSE REFUSAL FOUND BY HITTING IT.
    # `failures_seen` is a count of rows, `run_id` is an integer argument, and
    # when a run's id equals its number of failing rows the wall refuses the
    # stamp and takes the whole call down with it. Not hypothetical: a sandbox
    # whose first run is id 1, graded over two rows so exactly one fails,
    # raised `MeasurementError` on `run_id=1, failing=1` - measured 2026-09-09,
    # and it is asserted in
    # `tests/test_a_dominant_bucket_needs_the_rows_it_was_counted_from.py`.
    #
    # `run_id` says WHICH run to re-tally. It could never be the answer to "how
    # many rows of it failed" - that number is counted off the run's own graded
    # rows - so it bounds the work and does not answer the question, which is
    # exactly what this declaration is for. `buckets` stays quarantined: it is
    # the person's judgement and the histogram is built out of it.
    bounds=("run_id",),
    approval="never",
    provides=("measurement.eval.rebucket",),
    label="Re-bucket the failures",
    group="Measure",
    verb="re-tally a histogram you corrected",
    order=44,
)
def rebucket_failures(
    run_id: int,
    buckets: dict[str, Any],
    *,
    instrument: Instrument,
    ledger: diagnosis.Spec,
) -> dict[str, Any]:
    """The person's reading of their own failures, counted.

    ## Why this exists, and why it is a MEASUREMENT

    `ACTION__RE_BUCKET_THE_FAILURES` had every route out shut, each for a reason
    the product was individually right about. `failure_histogram` is
    `source: derive`, so only a MEASURED value opens anything. The one tool that
    measured it - `run_eval` - buckets by fixed rules and never by a model, so
    re-running it returns the identical histogram and lands on the same outcome.
    And asking was closed too, because `Build.validate` refuses a question about
    a fact a registered tool measures.

    So the missing thing was a SECOND INSTRUMENT, and this is it. What it
    measures is the COUNT: it reads the rows an eval run already graded and
    tallies them. What the person supplies is the classification, which is
    exactly the division `carve_eval_set` already ships - they say which column
    holds the answer, the harness counts the rows. A tally over rows this
    process read is a measurement; whose judgement decided the labels is a
    different question and it is answered in `how`.

    ## What it refuses, and why each one matters

    * **A bucket the router cannot route.** `failure_mode` is deliberately not a
      declared enum, and `S1_ROUTE_BY_FAILURE_MODE` RAISES on a histogram whose
      keys it has no route for - the ledger names that as a known gap. So the
      vocabulary here is `routable_modes(ledger)`, read off the ledger's own
      router, never listed in this file.
    * **A row that is not in this run**, and **a row that PASSED.** Bucketing a
      correct answer would put a row in the failure histogram that is not a
      failure, and the sum of that histogram is what stage 1 reads to decide
      whether there is anything to diagnose at all.
    * **An incomplete run**, for `score`'s reason: a partial tally is not a
      tally.
    """
    report = read(int(run_id))
    if not report.get("ok"):
        return {
            "ok": False,
            "error": "no_such_run",
            "run_id": int(run_id),
            "detail": (
                f"there is no eval run {int(run_id)} on this machine. "
                "read_eval_results lists the runs this conversation has."
            ),
        }
    if int(report["thread_id"]) != int(instrument.thread_id or 0):
        return {
            "ok": False,
            "error": "another_conversation",
            "detail": (
                f"eval run {int(run_id)} belongs to conversation "
                f"{report['thread_id']} and this call is in "
                f"{instrument.thread_id}. Re-reading somebody else's failures "
                "here would file their rows under this thread."
            ),
        }
    if not report["complete"]:
        return {
            "ok": False,
            "error": "run_incomplete",
            "detail": (
                f"eval run {int(run_id)} did not finish, so the rows it graded "
                "are a prefix rather than a sample and a tally over them is not "
                "a tally. Finish it and ask again."
            ),
        }

    rows = {int(row["row_index"]): row for row in results_for(int(run_id))}
    failing = {index for index, row in rows.items() if not row["correct"]}
    allowed = set(routable_modes(ledger))

    corrections: dict[int, str] = {}
    refusals: list[dict[str, Any]] = []
    for key, value in (buckets or {}).items():
        try:
            index = int(key)
        except (TypeError, ValueError):
            refusals.append({"row": key, "refused": "not_a_row_index"})
            continue
        mode = str(value or "").strip()
        if index not in rows:
            refusals.append({"row": index, "refused": "not_in_this_run"})
        elif index not in failing:
            refusals.append({"row": index, "refused": "this_row_passed"})
        elif mode not in allowed:
            refusals.append(
                {"row": index, "refused": "not_a_routable_mode", "given": mode}
            )
        else:
            corrections[index] = mode

    if refusals:
        return {
            "ok": False,
            "error": "rejected_buckets",
            "refusals": refusals,
            "routable_modes": sorted(allowed),
            "detail": (
                "Nothing was recorded. A histogram is only worth having if every "
                "bucket in it is one the tree can route on and every row in it "
                "actually failed - the router raises on a key it has no route "
                "for, and the sum of this histogram is what decides whether "
                "there is anything to diagnose."
            ),
        }

    # THE CORRECTION IS KEPT WHERE EVERY READER LOOKS, not only tallied.
    # `choose_exemplars`, `read_eval_results` and the failure list in the pane
    # all read `failure_mode` through `results_for`. A re-bucketing that lived
    # only in the histogram fact left them on the rule's bucket:
    # `try_prompt(fewshot_from_failures=8, targets="wrong_facts")` answered "no
    # failing rows in the wrong_facts bucket" one call after the person had put
    # 26 rows in it. `eval_results` itself is append-only (migration 8, and a
    # test reads this module's source to hold it to that), so the person's
    # reading goes to its own append-only table, `eval_rebuckets`, and
    # `results_for` overlays the latest one per row. The rule's own bucket is
    # never overwritten; it is still on the row underneath.
    if corrections:
        with db.session() as connection:
            connection.executemany(
                "INSERT INTO eval_rebuckets (run_id, row_index, failure_mode) "
                "VALUES (?, ?, ?)",
                [
                    (int(run_id), index, mode)
                    for index, mode in sorted(corrections.items())
                ],
            )

    histogram: dict[str, int] = {}
    unclassified = 0
    for index in sorted(failing):
        mode = corrections.get(index) or str(rows[index].get("failure_mode") or "")
        if mode not in allowed:
            unclassified += 1
            continue
        histogram[mode] = histogram.get(mode, 0) + 1

    payload = {
        "ok": True,
        "run_id": int(run_id),
        "failing_rows": len(failing),
        "corrected": len(corrections),
        "kept_the_rule_s_bucket": len(failing) - len(corrections) - unclassified,
        "unclassified": unclassified,
        "failure_histogram": dict(sorted(histogram.items())),
        "routable_modes": sorted(allowed),
        "whose_judgement": (
            "The counts are this tool's, read off rows eval run "
            f"{int(run_id)} already graded. The buckets on the "
            f"{len(corrections)} row(s) named above are yours. A row you did not "
            "name kept the bucket the rule gave it - not because you agreed with "
            "it, but because you did not say."
        ),
    }

    if histogram:
        # Same denominator, same reason as `run_eval`. This tool re-tallies over
        # the rows a person re-read, and `len(failing)` is every failing row of
        # the run - not the subset they were shown. Run 51 is the case: 20
        # re-tallied against 47 failing, which reads as a taxonomy until the 47
        # is beside it.
        instrument.measured(
            "failures_seen",
            len(failing),
            how=(
                f"eval run {int(run_id)} has {len(failing)} failing row(s); this "
                "is the count the failure histogram is a fraction of"
            ),
            from_file=report.get("eval_path"),
        )
        instrument.measured(
            "failure_histogram",
            dict(histogram),
            how=(
                f"{sum(histogram.values())} of {len(failing)} failing rows of "
                f"eval run {int(run_id)} re-tallied, {len(corrections)} of them "
                "re-bucketed by the person who read them: "
                + ", ".join(f"{k} {v}" for k, v in sorted(histogram.items()))
                + (
                    f"; {unclassified} failure(s) carrying no routable bucket are "
                    "left out rather than guessed at"
                    if unclassified
                    else ""
                )
            ),
            from_file=report.get("eval_path"),
        )
    else:
        payload["nothing_was_recorded"] = (
            "Every failing row carries a bucket the tree has no route for, so "
            "there is no histogram to record. Name those rows with a routable "
            "mode and ask again."
        )
    return payload


@tool(
    "read_eval_results",
    description=(
        "Read eval runs already stored in this conversation: the score with its "
        "resolution, the failure histogram, and the rows that failed. With "
        "`against`, it compares two runs over the same eval set PAIRWISE with "
        "McNemar's exact test - every reported number, the difference included, "
        "measured on the rows BOTH runs graded - and when the difference is "
        "inside what that many "
        "rows can resolve it says NO EVIDENCE rather than reporting a small win. "
        "Costs nothing and asks the model nothing."
    ),
    schema={
        "type": "object",
        "properties": {
            "run_id": {
                "type": "integer",
                "description": (
                    "Which run to read. Leave it out to list the runs in this "
                    "conversation, newest first."
                ),
            },
            "against": {
                "type": "integer",
                "description": (
                    "Another run over the same eval set, to compare this one "
                    "against row by row."
                ),
            },
            "failures": {
                "type": "integer",
                "description": "How many failing rows to return. Default 20.",
            },
        },
    },
    reads=("evals",),
    writes=(),
    provides=("measurement.eval.read",),
    label="Read eval results",
    group="Data",
    verb="read what an eval run actually found",
    order=24,
)
def read_eval_results(
    run_id: int | None = None,
    against: int | None = None,
    failures: int = 20,
    *,
    instrument: Instrument,
) -> dict[str, Any]:
    """List, read or compare - and only within this conversation.

    The instrument is taken only for `thread_id`. It can stamp nothing: an empty
    `measures=` is a structural property checked at registration, not a promise.

    THE THREAD IS REQUIRED HERE EVEN THOUGH THE ROUTE DOES NOT DEMAND IT.
    `evidence.thread_is_required_by` answers off `measures=` and `writes=`, and
    this tool has neither - correctly, because it cannot write a fact. But it can
    READ one conversation's eval rows, and served with no thread it would serve
    every conversation's. That opens no gate (nothing it returns can be stamped;
    a model repeating a number back is ASSERTED and opens nothing) and it is
    still the eval-set leak in a smaller shape: one project's data read out in
    another project's transcript. The direction to fail in is closed, so a call
    with no conversation is refused here rather than served.
    """
    try:
        limit = max(0, min(int(failures), 200))
    except (TypeError, ValueError):
        limit = 20

    if instrument.thread_id is None:
        return {
            "ok": False,
            "error": "no_thread",
            "detail": (
                "read_eval_results reads the eval runs of ONE conversation, and "
                "this call did not say which. An eval run belongs to the "
                "conversation it was measured in, for the same reason a fact does."
            ),
            **evidence.thread_id_help("read_eval_results"),
        }

    if run_id is None:
        rows = runs_in(instrument.thread_id)
        return {
            "ok": True,
            "count": len(rows),
            "runs": [
                {
                    "run_id": int(row["id"]),
                    "eval_path": row["eval_path"],
                    "metric": row["metric"],
                    "model": row["model"],
                    "prompt_is_default": bool(row["prompt_is_default"]),
                    "planned": int(row["planned"]),
                    "graded": int(row["graded"]),
                    "complete": int(row["graded"]) >= int(row["planned"]),
                    "eval_fingerprint": row["eval_fingerprint"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ],
            "help": (
                "Two runs with the same eval_fingerprint are about the same eval "
                "set and can be compared; pass one as run_id and the other as "
                "against. The fingerprint does NOT mean they graded the same rows "
                "- sample and hold_out decide that - so the comparison pairs them "
                "on the rows both graded and reports the difference over those."
            ),
        }

    # BOTH ids are checked, not only the first. A comparison against a run in
    # another conversation would report that run's score, its prompt and its
    # failing rows into this one, which is the same leak by a longer route.
    wanted = [int(run_id)] + ([int(against)] if against is not None else [])
    for candidate in wanted:
        owned = get_run(candidate)
        if owned is None or int(owned["thread_id"]) != int(instrument.thread_id):
            return {
                "ok": False,
                "error": "no_such_run",
                "run_id": candidate,
                "detail": (
                    f"There is no eval run {candidate} in this conversation. Runs "
                    "belong to the conversation they were measured in, for the "
                    "same reason facts do."
                ),
            }

    if against is None:
        return read(int(run_id), failures=limit)
    return compare(int(run_id), int(against), failures=limit)


__all__ = [
    "CONTAINS",
    "DEFAULT_DEADLINE_SECONDS",
    "DEFAULT_EVAL_SAMPLE",
    "EXACT_MATCH",
    "MAX_EVAL_SAMPLE",
    "METRICS",
    "MODEL_GRADED",
    "UNCLASSIFIED",
    "bucket",
    "compare",
    "ensure_tables",
    "fingerprint_pairs",
    "grade",
    "mcnemar",
    "normalise_answer",
    "read",
    "read_eval_results",
    "resolution_for",
    "routable_modes",
    "rows_for_points",
    "run",
    "run_eval",
    "runs_in",
    "signature_for",
    "wilson",
]
