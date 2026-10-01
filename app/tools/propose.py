"""The proposer: a diagnosis outcome in, a `Build` out - or an honest refusal.

`app/build.py` is the object. This is the thing that produces one, and the two
decisions that matter here are both about what it will NOT do.

## YOU DO NOT GET TO NAME THE OUTCOME YOU WANT A PLAN FOR

`propose_build` takes **facts**, exactly as `run_diagnosis` does. It runs the
diagnosis itself and proposes a build for whatever the engine decided. There is
no argument that says which remedy to plan for, and there is not going to be
one.

That is not a schema detail, it is the same wall the whole product stands on. A
tool with an `outcome` argument would let a model ask for a training plan
directly, and a model that wants to be helpful will agree that you should
fine-tune every single time. `app/tools/registry.py` already refuses to register
a tool with an argument called `outcome` (wall 2); this module would have had to
find a synonym to get around that, and finding a synonym for a banned argument
is how a guarantee becomes decoration. **Facts in, engine decides, proposer
plans what the engine decided.** The five gates therefore sit between a model's
request and any training plan, structurally, with nothing to remember.

## A PROPOSER THAT CANNOT RUN THE THING REFUSES TO DRAW IT

The instruction for this run says it plainly: *do not stub a proposer that emits
a plausible-looking build for something we cannot run - a plan that cannot
execute is the exact failure mode this object exists to prevent.* So every
proposer below either produces a build whose steps are registered tools with
satisfied schemas, or raises `NotEnoughToPropose`, which comes back to the
caller as a refusal that names what is missing.

Two refusals are worth reading before the code, because both were nearly
plausible-looking builds:

- **`ACTION__COUNT_THE_ROWS` is not covered**, and it looks like it should be.
  `profile_dataset` reads a table and reports its row count, so "profile the
  dataset, then re-run the diagnosis" writes itself. It would not work. The
  outcome is blocked on `tabular_rows`, and **no registered tool declares
  `measures=("tabular_rows",)`** - `profile_dataset` stamps `eval_size_n` and
  nothing else. The build would run, look successful, re-enter the tree and land
  on the same outcome, having spent the user's time to move nothing. The fix is
  a tool that measures `tabular_rows`; that is a tool change, not a proposer,
  and inventing a proposer for it here would hide the gap rather than name it.
- **`NO_TRAIN__OFF_THE_SHELF_MODEL` is not covered.** It is reached only on
  `modality in {image, audio}` (node `S8_VISION_AUDIO_OFFTHESHELF`), and all
  three scoring tools in this harness — `measure_baseline`, `run_eval` and
  `try_prompt` — send text to a chat provider and grade by exact match,
  containment, or a chat model judging. Whisper on an audio eval set is not
  something we can run today.

  **THE CANARY HAS NOW FIRED TWICE AND THE ANSWER HAS NOT MOVED EITHER TIME.**
  The evaluation bench added a second scorer; the prompt bench added a third.
  The guard is
  `tests/test_the_proposal_is_executable.py::TheCoverageStatementIsCompleteAndTrueTest::test_the_reason_given_for_the_off_the_shelf_outcome_is_actually_true`,
  whose canary is the roster of tools that talk to a model at all, and it goes
  red on each new one so that somebody has to re-read this rather than assume.
  Both times the conclusion held for the same reason: each addition was the same
  KIND of scorer, and more ways to send text to a chat provider is not a way to
  score audio. It stops holding the day an adapter sends audio or pixels, and
  that is a tool change rather than a proposer.

The full list of what is and is not covered, and why, is in `COVERAGE` at the
bottom of this file. It is a data structure rather than a comment so a test can
read it and so it cannot quietly drift from the proposers above it.

## AND COVERAGE IS NOW A QUESTION ABOUT THE REGISTRY, NOT A LINE IN A TABLE

Two entries of `COVERAGE` and `NOT_COVERED` are decided by whether three tools
are registered - see `_WhatTheRegistryDecides`. That is not cleverness, it is
the same rule as everything else here applied to the tables themselves.
`propose_build` reports `covered_outcomes: sorted(PROPOSERS)` and `app/asking.py`
reads all three tables to tell a person whether the product can act on their
verdict, so a hardcoded entry for an outcome whose tools are absent would make
the product SAY it covers something it cannot build. Twice already a sentence in
`NOT_COVERED` went false and stayed false for as long as it took somebody to
re-read it - once for the eval runner, once for the prompt bench - and each time
it was a written claim that this product could not do a thing it could. This
shape cannot go stale in either direction.

## THE RETRIEVAL BENCH, AND THE HALF OF A CRITERION IT CANNOT REACH

`NO_TRAIN__RAG` is the largest of the thirteen dead-end no-train outcomes and
`ACTION__MEASURE_RETRIEVER_RECALL` is the engine asking a person to go and
measure something the harness could not help them measure.
`_propose_the_retrieval_bench` answers both, and the thing to read before
changing it is what it says about `S3_BUILD_RAG`'s exit criterion: *recall >=
0.8 on the eval set AND end-to-end score >= target_score*. This build measures
the first half. Nothing in this harness does retrieval-augmented generation, so
the second half is not reachable - and the build states the engine's criterion
as written, checks the half it reaches, and says which half that is, instead of
declaring a criterion shaped to what it can do.

## THE CARVE, AND THE HALF OF A REFUSAL THAT WAS TRUE

`BLOCKED__BUILD_EVAL_SET` has two builds behind it now and a person gets
whichever one their FILE says they should. The old one - attach, count,
re-check - is right for somebody who has an eval file, and its refusal for
somebody who does not was *"what is needed is more graded examples, and writing
them is yours"*. That sentence is exactly right for data with no answers in it
and false for a labelled dataset, where the eval set does not have to be
written, it has to be held out. `assess_the_data` part five has been announcing
that carve and then saying *"nothing has been carved and no file has been
written"* since it was written.

So the false half is fixed and the true half is untouched, and which one a
person is in is decided by reading their file rather than by asking:
`_why_carving_is_not_honest_here` requires that they NAME the column holding the
answers - this file will not pick it, because which column is a right answer is
the definition of correct for their task - and then reads that column off the
disk and counts the graded rows against G0's own threshold. Fail any of it and
the old sentence comes back word for word.

**AND IT IS THE FIRST BUILD IN THIS PRODUCT THAT CHANGES SOMEBODY'S DISK**,
which is why the plan names the directory it will create before anybody approves
it and refuses outright when something is already there. `_disk_cost` had to be
corrected for it: that function told every writer it wrote *rows in the harness
database, no files*, which was true of the six tools it was written for and
false of the five that write files.

## THE FIRST BUILD UNDER A TRAIN VERDICT, AND THE INSTRUMENT THAT IS MISSING

`TRAIN__LORA_SFT` is the outcome this product is named after and it was the
emptiest entry in the table: nine `TRAIN__` outcomes and no build behind any of
them, so a run that passed all five gates ended at the verdict while a run that
failed them was handed work. Every tool a fine-tune needs is registered.
Assembling them is what found the piece that is not.

**Nothing in this harness can score what it trains.** Every tool here that can
score a model declares `providers` in its `reads`; a provider is a CONNECTION,
of which `app/providers/__init__.py` declares exactly two kinds; and a LoRA
adapter written into a run directory is not one. No registered tool loads,
merges, converts or serves an adapter, and no shipped recipe declares kind
`eval` or `convert`, so the sandbox cannot be asked either.
`why_the_full_run_is_not_drawn` computes that off both rosters rather than
asserting it, and a test over the same two rosters goes red the day either
changes.

That decides the build's shape rather than annotating it. The exit criterion
for a fine-tune is the adapter BEATING THE MEASURED BASELINE on the person's
own eval set by a margin those rows can resolve; "training finished" and "the
loss went down" are the two sentences `app/tools/evals.py` exists to refuse. The
retrieval bench could state a two-halved criterion and measure one half. Here
the reachable fraction is none of it, and the honest consequence of none is not
to draw the run. So `_propose_train_the_adapter` proves the card can hold the
model, proves the split does not leak, makes the disposable pinned sandbox, and
runs the real recipe over a bounded slice - which turns the one estimate this
whole file has never been able to make into a measured number, and is the
spec's own preferred answer to not knowing.

**And no step in it stamps a fact any gate reads.** That is a property of the
step list, checked by a test that derives the gate facts from the spec rather
than listing them. It is also the second reason the eval leg cannot be drawn:
`run_eval` measures `baseline_score` and `baseline_measured`, so scoring an
adapter with it would file a real measurement of a DIFFERENT MODEL under the
name G1 reads - the `eval_size_n` subject defect in a fine-tune costume.

## WHERE THE NUMBERS COME FROM, AND WHY MOST OF THEM ARE UNKNOWN

`docs/THE_PROPOSAL_LOOP.md` names the trap: a proposal contains estimates, and
"about forty minutes and roughly fourteen cents" is exactly the sentence we
would be inventing. `app/build.py` makes an unprovenanced number impossible to
construct. This module is where that bites, and the honest result today is:

- **Model tokens and requests are provable in both directions.** A tool that
  does not declare `providers` in its `reads` sends nothing to the user's model
  - not "almost nothing", nought, and the reason is a line in the tool's own
  registration. For `measure_baseline`, which does read providers, the number of
  requests is `min(eval_size_n, sample)`: a measured row count, bounded by a
  stated cap, one request per row. That is a derivation with no fudge factor in
  it, and it is INFERRED with the derivation shown. The token count is UNKNOWN,
  because turning rows into tokens needs a tokenizer we do not have at proposal
  time, and characters-times-a-number-somebody-remembered is the trap.
- **Wall clock is UNKNOWN for every step, and this is the named gap.**
  `measure_eval_set` and `measure_baseline` both already return a real `seconds`
  in their results, and nothing in this harness stores it. There is no per-tool
  timing history to read at proposal time, so there is nothing to measure from
  and nothing honest to infer from. Every wall-clock estimate therefore says so
  and says how to find out - usually "run this on a small sample first and read
  the seconds it reports", which is the spec's own preferred answer. When a
  timing history exists, `Reading.of_measured_fact` is the door it comes through
  and these become MEASURED with no other change.
- **Disk is provable for a tool that declares `writes=()`** and UNKNOWN for one
  that appends rows to the harness database, because nobody has measured how
  many bytes a row costs.

## AND THE NUMBER THAT WAS REAL AND WAS OF THE WRONG FILE

The one derived number in this file was wrong in a way none of the walls above
could see. A proposal for a 777-row eval file promised **"model_requests: 120
requests (inferred)"**, derived as *"counted 120 rows in
...\\Temp\\tmph_4tt4go\\eval.jsonl; capped at 500"*. The count happened. The cap
is `measure_baseline`'s own. The arithmetic is right. The answer is four times
too small, because `eval_size_n` in the ledger was a count of a file this build
does not touch, and `Reading.of_measured_fact` had no way to say what a
measurement was OF.

`app/build.py` now carries `Subject` and refuses to mint a reading without one.
This file is where the refusal has to become a product behaviour rather than a
crash, and the shape is the one `docs/THE_PROPOSAL_LOOP.md` already argues for:

> *"I do not know how long this takes, let me run it on 1% and find out"* is
> worth more than a guess.

So `_baseline_requests` establishes what the step will run on, recovers what the
stored count was of, and **when they are not the same thing the estimate is
UNKNOWN, the reason names both subjects, and the build plans the count itself**.
The person sees "unknown, because the count on file is a count of that other
file - here is a step that counts this one", which is worth more than 120 and
worth more than a refusal to plan.

**AND WHICH ARGUMENT THE STEP READS IS THE TOOL'S TO SAY.** The check above
turns on knowing what a step will open. This file used to answer that from a
tuple of argument names it kept itself - `("eval_path", "path",
"dataset_path")` - and `app/build.py`'s validator answered it by scanning every
string argument for one that matched the declared subject. Both were guesses,
and the second was the original defect reproduced through its own fix: point
`eval_path` at a 777-row file, hide the 120-row file's path in `expected_field`,
declare `operates_on` as the 120-row file, and a real count of it costed a step
that opens the other one, showing 120 requests where 500 would be spent. The
tuple is gone and `_subject_of_a_call` asks `app/build.py`, which asks the TOOL
- see `declared_subject_arguments` there for the `subject=` declaration wanted
from `app/tools/registry.py`, and for what an undeclared tool falls back to,
which is a refusal to pick rather than a better guess. When it cannot tell, the
request count is UNKNOWN and this build plans the count, which is the same
answer this file already gives to every other way of not knowing.

**HOW THE SUBJECT OF A STORED FACT IS RECOVERED, AND WHAT THAT COSTS.**
`app/tools/evidence.py` has no column for what a measurement was of; the only
record is the derivation sentence the measuring tool wrote, and both tools that
stamp `eval_size_n` write `counted <n> rows in <path>`. `subject_of_a_recorded_
measurement` reads that, and nothing else. That is a parser over prose and it
will stop matching the day somebody rewords a `how`.

**AND THE LEDGER'S DATE IS READ BESIDE IT, WHICH CLOSES THE OTHER HALF.** A
recovered subject carries no witness - nothing recorded the file's size or
contents at the time - so until now a file WHOLLY REPLACED since it was counted
still matched by identity, and "500 requests" was accepted for a file that now
holds two rows. What the ledger does hold is when each row was written, and a
file modified after that is not the file that was counted.
`when_each_row_was_written` finds the row each trail entry came from and reads
its `created_at`; `app/build.py`'s `Subject.matches` refuses on it. It costs one
`stat()` on a file of any size, it is defeated by anything that preserves a
modification time, and a fact whose row nobody can date is matched on identity
exactly as before - absent is absent, never fresh.

**The direction it fails in is the whole defence.** An unreadable derivation
yields no subject, no subject yields UNKNOWN, and UNKNOWN yields a build that
goes and counts the file. It cannot yield a number. And
`tests/test_a_measurement_carries_its_subject.py` drives both live minting tools
through the real registry and asserts the recovery works, so a reworded `how`
turns the suite red instead of quietly degrading every proposal to unknown.
"""

from __future__ import annotations

import importlib.util
import math
import re
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Mapping

from app import build, dataquality, diagnosis
from app.build import (
    Build,
    BuildInvalid,
    Cost,
    Environment,
    Estimate,
    ExitCriterion,
    Output,
    Question,
    Reading,
    Ref,
    Risk,
    Step,
    Subject,
    SubjectMismatch,
)
from app.tools import evidence
from app.tools.evidence import Instrument
from app.tools.registry import REGISTRY, tool

# Imported for the caps `measure_baseline` actually enforces, so a proposal's
# request count is bounded by the same number the tool is bounded by rather than
# by one this file remembered. `app/tools/__init__.py` imports `measure` before
# it imports this module.
from app.tools.measure import DEFAULT_BASELINE_SAMPLE, MAX_BASELINE_SAMPLE

# The eval bench's own caps, and the prompt bench's own ceiling, for the same
# reason and through the same door. `app/tools/__init__.py` imports `evals` and
# then `prompts` before this module, and the comments there say why the order is
# forced rather than tidy. Both are imported as MODULES as well, because what is
# wanted from them - the routable failure modes, the exemplar ceiling, the modes
# a bucket cannot be keyed on - are answers those modules already derive, and a
# second copy here is the drift this repository has been bitten by twice.
from app.tools import evals, prompts
from app.tools.evals import DEFAULT_EVAL_SAMPLE, MAX_EVAL_SAMPLE


class NotEnoughToPropose(Exception):
    """We know what should happen and cannot yet write a build that does it.

    Carries what is missing, so the answer to the user is "point me at your eval
    file and I will plan this" rather than a plan with a hole in it.
    """

    def __init__(self, detail: str, *, needs: tuple[str, ...] = ()) -> None:
        super().__init__(detail)
        self.detail = detail
        self.needs = tuple(needs)


# ---------------------------------------------------------------------------
# What the proposer knows when it starts.


@dataclass(frozen=True)
class Situation:
    """The diagnosis, the facts behind it, and the paths the caller named."""

    outcome: str
    result: diagnosis.Diagnosis
    values: Mapping[str, Any] = field(default_factory=dict)
    origins: Mapping[str, str] = field(default_factory=dict)
    hows: Mapping[str, str] = field(default_factory=dict)
    #: WHEN each fact's winning row was written into the ledger, where that can
    #: be established. It is the only thing any record here holds about the state
    #: of the file at the time a measurement was taken, and it is what lets a
    #: count of a file that has since been replaced be refused. Empty for a fact
    #: whose row nobody could date, and an absent date means the check does not
    #: run - never that the count is fresh. `propose_build` fills it; a caller
    #: assembling a `Situation` by hand and leaving it out gets exactly the
    #: behaviour that existed before it, which is identity matching alone.
    recorded_at: Mapping[str, str] = field(default_factory=dict)
    eval_path: str = ""
    input_field: str = ""
    expected_field: str = ""
    dataset_path: str = ""
    sample: int = DEFAULT_BASELINE_SAMPLE
    #: THE PROMPT THE PERSON WANTS TO TRY, and it is theirs rather than ours.
    #: `run_eval` takes a system prompt and scores under it, so the before/after
    #: the prompt bench is made of is two calls to one tool - but the second
    #: call's prompt is a thing only the person can write. This file will not
    #: draft one: a proposal whose central argument the harness invented is a
    #: plan for an experiment nobody chose. Empty means no prompt was given, and
    #: `_propose_try_a_prompt` refuses rather than filling it in.
    prompt: str = ""
    #: WHICH LINE OF DESCENT THE ATTEMPT IS ADDED TO. `try_prompt` compares every
    #: version against its line's current champion, so this name decides what an
    #: attempt is measured against. Empty means the caller did not say and
    #: `_the_prompt_line` takes one from the eval file, which the step then says
    #: out loud rather than leaving the person to guess what they beat.
    prompt_line: str = ""
    #: THE DOCUMENTS THE RETRIEVER IS SUPPOSED TO FETCH FROM. A separate field
    #: from `dataset_path` on purpose: a corpus is not a dataset with columns,
    #: it is the pile of text the answer is supposed to be in, and the retrieval
    #: build indexes THIS and scores against `eval_path`. Empty means nobody has
    #: named one and `_propose_the_retrieval_bench` refuses rather than indexing
    #: whichever path happened to be lying around.
    corpus_path: str = ""
    #: THE AGENT-INSTRUMENT PATHS, and they are three because somebody else's
    #: agent is read from three files, not one. `traces_path` is what
    #: read_agent_traces and bound_the_loop read; `failures_path` is what
    #: run_the_failures grades; `tooldefs_path` is optional and names a
    #: definitions file when the person wants one re-read beside the re-run.
    #: Empty means nobody named it, and `_propose_the_tool_layer_loop` refuses
    #: rather than pointing an instrument at whichever path happened to be
    #: lying around - the same refusal `_propose_the_retrieval_bench` gives an
    #: unnamed corpus.
    traces_path: str = ""
    failures_path: str = ""
    tooldefs_path: str = ""
    #: A QUESTION THE PERSON WOULD ACTUALLY ASK, so the build can show them what
    #: their index returns before it shows them a number about it. Empty means
    #: none was given: the look step is left out and the build says so, because
    #: a question this file made up would be a demonstration nobody chose.
    query: str = ""
    #: THE PASSAGE SIZES A CHUNKING SWEEP IS TO COMPARE, in characters, and they
    #: are the person's rather than ours. `compare_chunkings` declares `settings`
    #: required with no default and says why in its own schema: the number of
    #: settings is the family size every p-value is corrected against, so
    #: choosing them chooses how likely a false winner is. Empty means nobody
    #: said, and `_propose_fix_the_retriever` refuses rather than picking a
    #: sweep - the same refusal `prompt` gets, for the same reason.
    chunk_settings: tuple[int, ...] = ()
    #: HOW MANY PASSAGES COUNT AS "THE TOP FEW". `retriever_recall_at_k` has k in
    #: its name and a recall figure means nothing without it, but 0 here means
    #: the caller did not name one - and then the argument is omitted and the
    #: tool's own default stands, said out loud in the step. Picking a k here
    #: would be this file choosing the shape of somebody else's measurement.
    top_k: int = 0
    #: THE MODEL TO FINE-TUNE, and it is the person's. `find_models` ranks
    #: candidates by how well each fits THIS card, which is help; which one to
    #: train carries a licence and a commitment about what their product is,
    #: which is a decision. Empty means nobody named one and
    #: `_propose_train_the_adapter` refuses rather than taking the top of a
    #: ranking - the same refusal `prompt` and `chunk_settings` get.
    base_model: str = ""
    #: HOW MANY TOKENS LONG A TRAINING EXAMPLE IS. Required by the training
    #: build rather than defaulted, and the reason is sharper than for the
    #: model: this one number sets the activation and logits terms, and every
    #: tool that could default it defaults to a DIFFERENT one - so omitting it
    #: does not mean the tools agree, it means the fit answer and the run are
    #: two different runs. 0 is "nobody said" and is a refusal.
    max_seq_len: int = 0
    #: WHICH FIELD OF THE TRAINING JSONL HOLDS THE TEXT. Empty means nobody
    #: said, the argument is omitted, and the recipe's own default stands -
    #: which also accepts a prompt/completion pair and refuses the file loudly
    #: when it has neither. The step says which case it is in.
    text_field: str = ""
    #: THE THIRD LEDGER'S THREE INPUTS. Separate fields for the reason every
    #: path on this dataclass is separate: a checker is not a task set is not a
    #: pair of ablation arms, and a plan costed against the wrong one of them is
    #: a real number about a file the step never opens.
    #:
    #: `ablation_arms` is the only structured one, and it is structured because
    #: `G3_EVERY_COMPONENT_IS_LOAD_BEARING` asks about EVERY component: the unit
    #: of that measurement is the whole set, so the argument is the whole set.
    checker_path: str = ""
    tasks_path: str = ""
    ablation_arms: tuple[Any, ...] = ()
    #: THE ADAPTER A PREFERENCE RUN CONTINUES FROM, and it is required rather
    #: than optional because the ledger says so. `docs/diagnosis_engine.yaml`
    #: declares `DPO: {prerequisite: LORA_SFT}` and
    #: `S5_PREFERENCES_NOT_DEMONSTRATIONS` repeats it - *run preference
    #: optimization AFTER AN SFT PASS*. Empty means nobody named one and
    #: `_propose_train_on_preferences` refuses, quoting the line rather than
    #: paraphrasing it. It is not used by any other build: an SFT run starts
    #: from the base model by definition.
    adapter_dir: str = ""
    #: HOW MANY OPTIMIZER STEPS THE TRIAL RUNS. 0 means the caller did not say
    #: and the recipe's own default stands, said out loud. How much of somebody
    #: else's machine a measurement takes is their call, not this file's.
    trial_steps: int = 0
    #: THE FAILURE SET THIS DOMAIN IS MEASURED AGAINST, and it is a separate
    #: field from `eval_path` on purpose. An eval set is inputs and right
    #: answers; a failure set is *ten real failures from actual use, with what
    #: should have happened* - the same shape wearing a different name in a
    #: different ledger, and conflating them would let a plan for one domain be
    #: costed against the other's stored count. Empty means nobody named one and
    #: the agent proposers refuse rather than pointing at whichever file was
    #: lying around.
    failures_path: str = ""
    #: THE RECORD OF WHAT THE AGENT ACTUALLY DID - one OTLP/JSON file or a
    #: directory of them. Separate from everything above for the same reason a
    #: corpus is: a trace is not a dataset with columns, it is what happened.
    #: Empty means nobody named one, and `_propose_read_the_traces` refuses
    #: rather than reading whatever is nearby.
    trace_path: str = ""
    #: WHERE THE AGENT'S OWN ANSWERS ARE, when they are not in the failure file.
    #: `run_the_failures` grades answers rather than driving somebody's agent -
    #: running their code is their business and this harness executes no shell -
    #: so the answers are an input. Empty means they are in the failure file
    #: itself, which the tool's own schema allows, and the argument is omitted.
    answers_path: str = ""
    #: WHERE THE OUTPUTS ARE, AND WHAT SHAPE THEY WERE SUPPOSED TO BE.
    #:
    #: `stage_4_format`'s ask node wants the fraction of outputs that come back
    #: satisfying a schema, and both halves of that are the person's: the file
    #: their system produced, and the schema they wanted. `measure_the_format`
    #: will infer neither - a schema derived from the outputs being graded
    #: scores 100% by construction - so both are inputs and the proposer
    #: refuses by name without them.
    outputs_path: str = ""
    schema_path: str = ""
    #: WHERE THE ANSWERS ARE AFTER THE PERSON CHANGED SOMETHING, and it is the
    #: half of a paired proof this harness cannot produce for anybody.
    #:
    #: Six outcomes on the AI ledger name a cheap local fix - the tool
    #: description is the bug, the prompt is the bug, constrain the output, fix
    #: the context, fix the tool, try one API call - and each is only worth
    #: saying if the person can find out whether the fix worked. Finding that
    #: out is running THEIR agent again, which this harness will not do: their
    #: code is theirs. So the second recording is an input exactly as the first
    #: one is, and `_propose_prove_the_fix` refuses without it in words that say
    #: what to go and do. `BUILD__TOOLS_FOR_AN_EXISTING_LOOP` already states the
    #: same division: "wiring them and exporting a fresh answers file is yours
    #: between approving and running."
    after_answers_path: str = ""
    #: WHICH COLUMN HOLDS WHAT THE AGENT ANSWERED. Required by
    #: `run_the_failures` and refused rather than guessed here, for the reason
    #: `expected_field` is: which column is the answer is a statement about
    #: somebody's file that only they can make, and a wrong guess grades a
    #: whole failure set against the wrong text.
    answer_field: str = ""
    #: WHICH CONVERSATION THIS IS, and it is here for exactly one question: is
    #: there a completed eval run in it that the adapter could be compared
    #: against. `score_the_adapter` declares `baseline_run_id` required and its
    #: schema says why - the baseline run's graded rows ARE the rows the adapter
    #: is scored on - and eval runs are thread scoped, so the question cannot be
    #: asked without knowing the thread. 0 means the caller did not say, and
    #: then `the_baseline_run_to_beat` answers None and the training build draws
    #: the bounded trial rather than the run and the comparison. Absent is
    #: absent, never "there is one".
    thread_id: int = 0

    def origin(self, fact: str) -> str:
        return self.origins.get(fact) or self.result.fact_origins.get(fact, "")

    def is_measured(self, fact: str) -> bool:
        return self.origin(fact) == diagnosis.MEASURED

    @property
    def spec(self) -> diagnosis.Spec:
        """The ledger this situation's verdict was computed from.

        NOT LOOKED UP AGAIN - CARRIED. `diagnosis.Diagnosis` holds the `Spec`
        that produced it, so every one of this file's proposers already has the
        right ledger in its hand and cannot reach a different one by accident.
        This is the alternative to threading a handle through 9,800 lines: an
        answer carries the knowledge it was computed from.

        The fallback is for a `Situation` some test built around a hand-made
        `Diagnosis`; `diagnose()` always fills it.
        """
        return self.result.spec or diagnosis.default_spec()

    def measured_subject(self, fact: str) -> Subject | None:
        """What the stored measurement of `fact` was a measurement OF, or None.

        None is a real answer and the caller must treat it as one: it means the
        harness holds a measured number and cannot say what it counted, which is
        exactly as useless for costing a step as no number at all.
        """
        if not self.is_measured(fact):
            return None
        return subject_of_a_recorded_measurement(
            self.hows.get(fact, ""), measured_at=self.recorded_at.get(fact, "")
        )

    def require_path(self, name: str) -> str:
        value = str(getattr(self, name) or "").strip()
        if not value:
            raise NotEnoughToPropose(
                f"I cannot plan this without {name}. Tell me where it is and I "
                "will write the build; a plan with a path I guessed is a plan "
                "that fails after you approved it.",
                needs=(name,),
            )
        if not Path(value).exists():
            raise NotEnoughToPropose(
                f"There is nothing at {value}. Nothing is planned against a path "
                "that is not there.",
                needs=(name,),
            )
        return value


# ---------------------------------------------------------------------------
# What a stored measurement was a measurement of.

#: The sentence both minting tools write into the ledger's `how` when they count
#: rows: `f"counted {rows} rows in {path}"`, in `app/tools/measure.py` and
#: `app/tools/data.py`. This is a parser over prose, which is not a thing to be
#: pleased about - see the module docstring for why it is the only record there
#: is and why the direction it fails in makes it safe.
_A_RECORDED_COUNT = re.compile(r"counted\s+[\d,]+\s+rows\s+in\s+(?P<path>\S.*?)\s*(?:;|$)")

#: The witness the minting tools now append, read back out of the same
#: sentence. See `build.WITNESS_CLAUSE`. Absent on every row written
#: before that clause existed, which is why the subject below still
#: works without one.
_A_RECORDED_WITNESS = re.compile(r"the file was\s+(?P<witness>[\d,]+\s+bytes,\s+modified\s+\d+)\s+when it was counted")


def subject_of_a_recorded_measurement(
    how: str, *, measured_at: str = ""
) -> Subject | None:
    """The thing a stored fact was measured off, read out of its own derivation.

    Returns None when the derivation does not name one. That is not a failure to
    handle later: a measurement whose subject cannot be established cannot cost
    anything, and every caller here turns None into an UNKNOWN estimate that
    offers to go and measure.

    `measured_at` is WHEN THAT ROW WAS WRITTEN, and it is the whole of what the
    ledger holds about the file's state at the time. With it, a file modified
    since the count is refused - which closes "500 requests for a file that now
    holds two rows", a real measurement of a file that no longer exists in the
    form it was measured in. Without it the subject is matched by identity
    alone, exactly as before, because a caller who cannot date the row must be
    able to say so rather than assert a freshness nobody established.
    """
    text = str(how or "").strip()
    match = _A_RECORDED_COUNT.search(text)
    if not match:
        return None
    # THE WITNESS, WHEN THE ROW CARRIES ONE. Written at the moment of the count
    # by `build.counted_rows_how`, so it describes the file as it was then
    # rather than as it is now - which is the whole reason
    # `Subject.of_recorded_path` refuses to stat. Rows written before that
    # clause existed have none, and are matched by identity and date exactly as
    # they were.
    seen = _A_RECORDED_WITNESS.search(text)
    witness = seen.group("witness") if seen else ""
    try:
        return Subject.of_recorded_path(
            match.group("path"),
            witness=witness,
            how=(
                "recovered from the derivation the fact ledger recorded: "
                f"{text!r}. "
                + (
                    "The ledger recorded what that file looked like when it was "
                    f"counted ({witness}), so a file that differs from it now is "
                    "refused"
                    if witness
                    else "Nothing recorded what that file looked like at the "
                    "time, so this subject carries no witness"
                )
                + (
                    f"; the ledger does record that the row was written at "
                    f"{measured_at}, so a file modified after that is refused"
                    if str(measured_at or "").strip()
                    else " and nothing dates the row either, so it can only be "
                    "matched by identity"
                )
            ),
            measured_at=measured_at,
        )
    except build.CostError:  # pragma: no cover - a derivation naming an empty path
        return None


def when_each_row_was_written(
    thread_id: int | None, trail: list[dict[str, Any]]
) -> dict[str, str]:
    """The date beside each winning fact, read off the ledger row itself.

    `evidence.assemble_facts` returns the trail without `created_at` - it is a
    statement of what is true and who said it, not of when it was filed - so
    this goes back to the rows and finds the one each trail entry came from, by
    the fact, the origin and the derivation it carries. Nothing here re-decides
    which row won; it only dates the row that did.

    **The EARLIEST matching row wins**, which is the conservative direction: two
    identical counts filed at different times can only mean the file was read
    twice, and dating that pair from the later one would let a change between
    them go unseen. The cost of being early is a re-count, which is the
    direction everything in this area is arranged to fail in.

    A row nobody can find yields no date, and no date means the freshness check
    does not run rather than that it passed. That is the honest state and it is
    why this returns a dict with holes in it rather than raising.
    """
    try:
        rows = evidence.rows_for(thread_id)
    except Exception:  # noqa: BLE001 - the ledger's own refusals are not this
        # function's to interpret; a proposal without dates is the behaviour
        # that existed before dates, and it is never a wrong number.
        return {}
    wanted = {
        (str(row.get("fact")), str(row.get("origin")), str(row.get("how") or ""))
        for row in trail
    }
    when: dict[str, str] = {}
    for row in rows:  # oldest first, and `setdefault` keeps the oldest
        key = (str(row.get("fact")), str(row.get("origin")), str(row.get("how") or ""))
        if key in wanted and str(row.get("created_at") or "").strip():
            when.setdefault(key[0], str(row["created_at"]).strip())
    return when


# ---------------------------------------------------------------------------
# Costing, derived from what a tool declared about itself.


def _an_integer(value: Any) -> int:
    """`value` as an int, or 0 - which every caller here reads as "nobody said"."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _spec(name: str) -> Any:
    found = REGISTRY.get(name)
    if found is None:  # pragma: no cover - a proposer naming a missing tool
        raise NotEnoughToPropose(
            f"{name!r} is not a registered tool, so nothing can be planned with it."
        )
    return found


def _reaches_the_model(name: str) -> bool:
    return "providers" in _spec(name).reads


def _writes_to_disk(name: str) -> tuple[str, ...]:
    return tuple(_spec(name).writes)


def _model_cost_of_a_local_tool(name: str) -> tuple[Estimate, Estimate]:
    """Zero tokens and zero requests, proved off the tool's own registration."""
    because = (
        f"{name} declares reads={list(_spec(name).reads)}, which does not include "
        "`providers`, so it cannot send anything to your model"
    )
    return (
        Estimate.none(build.MODEL_TOKENS, because=because),
        Estimate.none(build.MODEL_REQUESTS, because=because),
    )


#: THE WORD THIS REPOSITORY ALREADY USES FOR "THIS TOOL PUTS FILES ON YOUR
#: DISK". Not invented here: `app/tools/sandbox.py` declares it on
#: `create_sandbox`, `run_in_sandbox` and `delete_sandbox`, and it is the one
#: word that separates a row in the harness database from a file in somebody's
#: folder. `_disk_cost` used to say *rows in the harness database, no files*
#: about every writer there was, which was true of the six tools it was written
#: for and false of the three beside it - and would have been false of every
#: proposal that planned a step which writes a dataset.
_THE_FILESYSTEM = "filesystem"

#: THE OTHER STORE THAT IS FILES AND NOT ROWS, and it was about to make
#: `_disk_cost` say something false. `find_models` and `read_model_config`
#: declare `writes=("model_config_cache",)` and what they write is a JSON file
#: per model under `.hub-cache/` - `app/feasibility.py::store_model_config`
#: returns the path. Left out of this set they would have taken the middle
#: branch below, whose sentence is *rows in the harness database, no files*, and
#: a true-sounding claim about somebody's disk in a plan they are about to
#: approve is the invented-number defect wearing prose. This is the set that
#: docstring says the next file-writing tool should join rather than a fourth
#: function; `_retrieval_disk` stays separate because it says something
#: different about the index, not because a file store needs its own function.
_STORES_THAT_ARE_FILES = frozenset({_THE_FILESYSTEM, "model_config_cache"})


def _disk_cost(name: str) -> Estimate:
    """What one step costs on disk, in the sentence that is true of THIS tool.

    THREE BRANCHES BECAUSE THERE ARE THREE ANSWERS, and which one applies is
    read off the tool's own `writes` rather than assumed. A tool that writes
    nothing costs nothing and can prove it. A tool that appends rows costs an
    unmeasured number of bytes per row. A tool that writes FILES costs whatever
    the person's rows turn into, which is a different unknown with a different
    way of finding out - and reusing the database sentence for it would put a
    true-sounding claim about somebody's disk into a plan they are about to
    approve. `_retrieval_disk` split this once already for the index store; this
    is the same split made general, so the next file-writing tool does not need
    a fourth function.
    """
    written = _writes_to_disk(name)
    if not written:
        return Estimate.none(
            build.DISK,
            because=(
                f"{name} declares writes=(), so it creates no file and adds "
                "nothing to disk"
            ),
        )
    if set(written) & _STORES_THAT_ARE_FILES:
        return Estimate.unknown(
            build.DISK,
            why=(
                f"{name} declares writes={list(written)}, so it writes FILES and "
                "not rows - and how many bytes that is depends on your rows and "
                "on the format they are written in, neither of which has been "
                "measured here. A figure would be one somebody remembered about "
                "some other dataset"
            ),
            find_out_by=(
                "run it over a small slice first and compare the size of the "
                "directory it writes into before and after; that is a measurement "
                "of YOUR rows rather than of an average one"
            ),
        )
    return Estimate.unknown(
        build.DISK,
        why=(
            f"{name} writes {list(written)} - rows in the harness database, no "
            "files - and nothing has measured how many bytes a row costs"
        ),
        find_out_by=(
            "compare the size of the harness database before and after one run "
            "of this step"
        ),
    )


def _wall_clock(name: str, *, find_out_by: str) -> Estimate:
    """UNKNOWN, always, today. See the module docstring's named gap."""
    return Estimate.unknown(
        build.WALL_CLOCK,
        why=(
            f"nothing in this harness has recorded how long {name} takes on data "
            "this size on this machine, so there is no measurement to derive one "
            "from and any figure here would be invented"
        ),
        find_out_by=find_out_by,
    )


def _local_cost(name: str, *, find_out_by: str) -> Cost:
    tokens, requests = _model_cost_of_a_local_tool(name)
    return Cost(
        model_tokens=tokens,
        model_requests=requests,
        wall_clock=_wall_clock(name, find_out_by=find_out_by),
        disk=_disk_cost(name),
    )


#: What to do when the request count cannot be derived. One sentence for every
#: branch, because every branch has the same answer and the spec's preferred one:
#: go and count the thing this step will actually read.
_GO_AND_COUNT_IT = (
    "count the eval set this step will score - measure_eval_set does exactly "
    "that, and this build runs it first whenever it can - and the request count "
    "is one per row it finds, bounded by the sample cap"
)


def _one_request_per_row(
    situation: Situation,
    target: Subject | None,
    *,
    tool: str,
    sample: int,
    unidentified: str = "",
) -> Estimate:
    """min(rows, sample) requests - measured OF THIS FILE, bounded, one per row.

    The one place in this file where a real number reaches a proposal, and it
    reaches it through all four of `app/build.py`'s doors in order: a Reading
    off a fact the ledger stamped MEASURED, carrying the subject that
    measurement was taken of; a check that the subject is what this step runs
    on; a cap that states the rule rather than guessing a size; and a
    one-for-one reinterpretation that names the property of the tool making it
    one for one.

    THE SUBJECT AND THE CHECK ON IT ARE THE NEW DOORS, and they are why this
    function takes a target at all. Without them it returned 120 requests for a
    777-row file, off a genuine count of a different file, with a derivation
    that read as impeccable. Every way of failing to establish that the count
    was of THIS file ends in the same place: UNKNOWN, with the reason, and an
    offer to measure.

    **`tool` AND `sample` ARE PARAMETERS BECAUSE A SECOND TOOL NOW SCORES ROWS.**
    `run_eval` asks the model exactly one question per row it grades, exactly as
    `measure_baseline` does, and it enforces a cap of its own. Writing this
    arithmetic out a second time for the eval bench would be two derivations of
    one number with nothing holding them together, and the one that drifted
    would still print a derivation that reads as impeccable - which is the
    failure this function exists to have survived once already.
    """
    if target is None:
        return Estimate.unknown(
            build.MODEL_REQUESTS,
            why=(
                "this build cannot identify the file this step would score, so a "
                "row count taken from anywhere could not be shown to be a count "
                "of it" + (f". {unidentified}" if unidentified else "")
            ),
            find_out_by=_GO_AND_COUNT_IT,
        )
    if not situation.is_measured("eval_size_n"):
        return Estimate.unknown(
            build.MODEL_REQUESTS,
            why=(
                "how many rows your eval set has is not measured yet, and the "
                "number of requests is one per row scored"
            ),
            find_out_by=_GO_AND_COUNT_IT,
        )

    recorded = situation.hows.get("eval_size_n", "")
    measured_of = situation.measured_subject("eval_size_n")
    if measured_of is None:
        return Estimate.unknown(
            build.MODEL_REQUESTS,
            why=(
                f"eval_size_n is measured - {situation.values.get('eval_size_n')!r} "
                "- and nothing in what was recorded says what was counted. The "
                f"derivation on file reads {recorded!r}. A request count derived "
                "from it would be a real measurement of something this build "
                "cannot identify, which is the one kind of wrong number that "
                "answers 'where did this come from?' correctly."
            ),
            find_out_by=_GO_AND_COUNT_IT,
        )

    rows = Estimate.measured(
        build.ROWS,
        reading=Reading.of_measured_fact(
            "eval_size_n",
            situation.values.get("eval_size_n"),
            situation.origin("eval_size_n"),
            recorded or "counted in this thread",
            subject=measured_of,
        ),
    )
    try:
        rows = rows.about(target)
    except SubjectMismatch as wrong:
        return Estimate.unknown(
            build.MODEL_REQUESTS,
            why=(
                f"{wrong}. So it says nothing about how many requests this step "
                "makes, and this build will not price one file with a count of "
                "another"
            ),
            find_out_by=_GO_AND_COUNT_IT,
        )
    return rows.capped_at(
        sample,
        because=f"{tool} scores at most sample={sample} rows",
    ).counted_as(
        build.MODEL_REQUESTS,
        because=f"{tool} asks your model exactly one question per row it scores",
    )


def _baseline_requests(
    situation: Situation, target: Subject | None, *, unidentified: str = ""
) -> Estimate:
    """`measure_baseline`'s request count, through the shared arithmetic above."""
    return _one_request_per_row(
        situation,
        target,
        tool="measure_baseline",
        sample=situation.sample,
        unidentified=unidentified,
    )


def _eval_sample(situation: Situation) -> int:
    """How many rows `run_eval` would grade, inside the caps that tool enforces.

    Bounded by `run_eval`'s own `MAX_EVAL_SAMPLE` rather than by
    `measure_baseline`'s, because a plan that names a sample the tool would
    silently reduce is a plan whose cost is not the cost of what runs.
    """
    try:
        wanted = int(situation.sample)
    except (TypeError, ValueError):  # pragma: no cover - Situation is typed
        wanted = DEFAULT_EVAL_SAMPLE
    return max(1, min(wanted, MAX_EVAL_SAMPLE))


def _eval_cost(
    situation: Situation,
    target: Subject | None,
    *,
    sample: int,
    unidentified: str = "",
) -> Cost:
    """What one `run_eval` step costs. The same four slots, the same refusals.

    **A PROMPT CAN COST THIS STEP ITS DERIVED REQUEST COUNT, AND THAT IS THE
    SAFE DIRECTION.** `run_eval` has not declared `subject=`, so
    `build.subject_of_a_call` falls back to *a call with nothing to guess
    between needs no guess*: it gathers every argument that might be naming a
    path and answers only if they all name the same one. A system prompt is a
    free-text argument, so `"Answer yes/no only."` reads as a second path, the
    call becomes ambiguous, and the request count comes back UNKNOWN with a step
    that goes and counts the file.

    That is the wrong answer to give a person and the right way to be wrong: the
    alternative is picking `eval_path` because this file recognises the name,
    which is the exact second-opinion-about-somebody-else's-tool that
    `_subject_of_a_call` exists to have deleted. It closes properly when
    `run_eval` declares `subject=("eval_path",)` - a one-line change in the
    tool's own registration, in a file this proposer does not own - and nothing
    here needs to change on the day it does.
    """
    return Cost(
        model_tokens=Estimate.unknown(
            build.MODEL_TOKENS,
            why=(
                "turning rows into tokens needs your model's tokenizer and the "
                "length of your rows, and neither is readable at proposal time. "
                "Multiplying characters by a remembered constant is the number "
                "this product refuses to invent."
            ),
            find_out_by=(
                "run this step once with a small sample and read the token usage "
                "your provider reports back"
            ),
        ),
        model_requests=_one_request_per_row(
            situation, target, tool="run_eval", sample=sample, unidentified=unidentified
        ),
        wall_clock=_wall_clock(
            "run_eval",
            find_out_by=(
                "run it with sample=5 first; every graded row is kept and the "
                "result carries the seconds it took, so the full run is that per "
                "row - and calling it again with the full sample continues rather "
                "than starting over"
            ),
        ),
        disk=_disk_cost("run_eval"),
    )


def _baseline_cost(
    situation: Situation, target: Subject | None, *, unidentified: str = ""
) -> Cost:
    return Cost(
        model_tokens=Estimate.unknown(
            build.MODEL_TOKENS,
            why=(
                "turning rows into tokens needs your model's tokenizer and the "
                "length of your rows, and neither is readable at proposal time. "
                "Multiplying characters by a remembered constant is the number "
                "this product refuses to invent."
            ),
            find_out_by=(
                "run this step once with a small sample and read the token usage "
                "your provider reports back"
            ),
        ),
        model_requests=_baseline_requests(
            situation, target, unidentified=unidentified
        ),
        wall_clock=_wall_clock(
            "measure_baseline",
            find_out_by=(
                "run it with sample=5 first; the result carries the seconds it "
                "actually took, and the full run is that per row"
            ),
        ),
        disk=_disk_cost("measure_baseline"),
    )


# ---------------------------------------------------------------------------
# Environments.


def _sandbox(name: str, *paths: str, reason: str = "") -> Environment:
    """A working directory of its own, a snapshot of the data, and no egress.

    `reason` is what turns egress on, and it is keyword-only so that a path
    passed positionally can never land in it. That is not hypothetical
    tidiness: the first version of this took `reason` positionally after
    `*paths` was spread into the call, and a data path silently became the
    sentence explaining why this sandbox may reach the network.
    """
    return Environment(
        name=name,
        working_dir=f"runs/proposals/{name}",
        egress=bool(reason),
        egress_reason=reason,
        data=tuple(build.DataSnapshot.of(path) for path in paths if path),
        installs=(),
    )


# ---------------------------------------------------------------------------
# Shared pieces.


_G0_REQUIRES = re.compile(r"eval_size_n\s*>=\s*(\d+)")

#: THE FACT, NOT THE GATE ID. `G0_EVAL_SET` was hardcoded here and in three
#: other modules, and it was always a proxy for this name: what these callers
#: want is the floor the ledger puts on the size of an eval set, and the gate is
#: merely where that floor is written. Asking by fact follows the ledger if the
#: ledger moves the fact, works unchanged on a ledger whose gates are spelled
#: differently, and cannot read the wrong gate in silence. See
#: `diagnosis.Spec.gate_reading`.
THE_EVAL_SIZE_FACT = "eval_size_n"


def g0_minimum(spec: diagnosis.Spec | None = None) -> int:
    """How many eval rows the gate about eval size asks for, read off the spec.

    Read rather than typed. The threshold is the product's own promise and it
    lives in the ledger; a copy of it here would be a second number that could
    drift from the first one silently.

    A LEDGER WITH NO SUCH GATE IS A REFUSAL, NOT A DEFAULT. `gate_reading`
    returns None when nothing in this domain's gates reads `eval_size_n`, and
    the honest answer is to say which ledger was asked - not to fall back to the
    first ledger's number, which is the exact silent wrong read this whole pass
    exists to remove.
    """
    current = spec or diagnosis.default_spec()
    reading = current.gate_reading(THE_EVAL_SIZE_FACT)
    if reading is None:
        raise NotEnoughToPropose(
            f"No gate in {current.as_written} reads {THE_EVAL_SIZE_FACT!r}, so this "
            "proposer cannot read a floor for the size of an eval set out of it. "
            "That is a fact about which domain this conversation is in, not a "
            "defect: the number would have to come from somewhere, and inventing "
            "one is what this file exists not to do.",
            needs=(THE_EVAL_SIZE_FACT,),
        )
    match = _G0_REQUIRES.search(str(reading.row.get("requires") or ""))
    if not match:  # pragma: no cover - the spec changed shape
        raise NotEnoughToPropose(
            f"{reading.gate_id} no longer states its threshold as "
            "`eval_size_n >= N`, so this proposer cannot read it. Nothing is "
            "planned against a threshold this file guessed."
        )
    return int(match.group(1))


def a_measurement_of(situation: Situation, fact: str, path: str) -> tuple[bool, Subject | None]:
    """Is the stored `fact` a measurement OF the file at `path`?

    Returns the answer and what the stored measurement was of, which may be
    `None` while the answer is False - and those are two different states that
    every caller here has to keep apart. `None` means the harness holds a number
    and cannot say what it counted; False with a subject means it can say, and
    it was something else. Neither is "already done", and the direction is
    always the same: what cannot be shown to be a measurement of THIS file does
    not stop this build from measuring it.

    ONE DERIVATION OF IT, NOT TWO. `_propose_build_the_eval_set` worked this out
    inline to decide whether counting again would be theatre, and the retrieval
    bench needs the identical question about two different facts. A second copy
    is the drift this repository has been bitten by twice, and the copy that
    drifted would still refuse - or fail to refuse - with a sentence that reads
    as impeccable.
    """
    recorded = situation.measured_subject(fact)
    if recorded is None:
        return False, None
    return Subject.of_path(path).matches(recorded)[0], recorded


def _recheck_step(needs: tuple[str, ...], fact: str, *, why: str) -> Step:
    """Re-enter the tree. Every build ends here, and it is not a formality.

    A bench never re-decides the verdict (`docs/PRODUCT_SPEC.md` 6.4). The steps
    above write facts; the engine reads them and decides again. That is why the
    last step of every build is `run_diagnosis` and why its exit criterion is
    about a fact's ORIGIN rather than about the verdict: the build's job is to
    make a fact measured, and what that then means is the engine's to say.
    """
    return Step(
        id="recheck",
        tool="run_diagnosis",
        why=why,
        arguments={"facts": {}},
        produces=(
            Output("verdict", "string", "the verdict the engine reached", at="verdict"),
        ),
        needs=needs,
        cost=_local_cost(
            "run_diagnosis",
            find_out_by=(
                "the diagnosis is a tree walk over facts already in the ledger; "
                "time one and it is timed for every build"
            ),
        ),
        exit_criterion=ExitCriterion(
            stated=f"{fact} is recorded as measured when the tree is walked again",
            source="diagnosis",
            subject=f"fact_origins.{fact}",
            comparator="is_measured",
        ),
    )


# ---------------------------------------------------------------------------
# Carving a held-out eval set, and the one line this whole file turns on.
#
# G0's recipe, in `docs/diagnosis_engine.yaml`: *"30-50 real inputs sampled from
# actual traffic, GRADED BY THE PERSON WHO CARES ABOUT THE ANSWER."*
#
# SPLITTING IS MECHANICAL. GRADING IS JUDGEMENT. A held-out slice of unlabelled
# rows is not an eval set: it is a pile of inputs with no right answers, and a
# gate that opened on one would be the five-gate test defeated by a file this
# harness wrote itself. That is the worst thing this build could do, so the line
# is drawn here, in code, rather than in a sentence somebody could stop meaning:
#
#   * The person names the column that holds the right answer. This file will
#     not guess it and no fallback picks a conventional name - which is the
#     opposite of `_the_question_and_the_right_passage`, where letting the tool
#     pick is right because it is naming a DOCUMENT and says which it picked.
#     Here the column is the definition of "correct", and choosing it is the one
#     judgement `docs/VISION.md` says the product never makes for anybody.
#   * The column is then READ OFF THE FILE rather than believed, because a claim
#     is exactly what the gates exist to distrust.
#   * Enough rows actually carry an answer to fill the eval set the gate asks
#     for - counted, on this file, at proposal time.
#
# Fail any of the three and the refusal is the one that was already here and is
# still true: what is needed is more graded examples, and writing them is yours.


#: THE TOOL NAME, FIXED SO THE TWO LANES CANNOT DISAGREE, exactly as
#: `THE_RETRIEVAL_TOOLS` and `THE_CHUNKING_TOOLS` are - and it is not the name
#: this file guessed. `docs/ROADMAP.md` Milestone 15 calls the splitting tool
#: `split_dataset`; what the sibling lane shipped in `app/tools/datawork.py` is
#: `carve_eval_set`, with an argument list this file had wrong in every
#: particular - `into` is a NEW DIRECTORY and the tool names the two files
#: inside it, the column is `answer_column`, and the seed is a string. Every one
#: of those was caught by `_a_call_that_fits` at proposal time rather than by a
#: step failing after somebody approved it, which is the whole reason the
#: argument names are asked of the schema instead of kept in a table here.
#:
#: A tuple of one, for `THE_CHUNKING_TOOLS`'s reason: the shape has to match the
#: refusal and the coverage entry that read it. `drop_duplicates` is the other
#: tool in that module and it answers a different question; a second carving
#: tool would be added here rather than in a second mechanism.
THE_CARVING_TOOLS: tuple[str, ...] = ("carve_eval_set",)

THE_CARVE = THE_CARVING_TOOLS[0]


def carving_tools_missing() -> tuple[str, ...]:
    """Which of the carving tools are not registered in this process, right now.

    Read off the live registry every time, for `retrieval_tools_missing`'s
    reason: nothing in this file had to be edited on the day the sibling lane's
    tool registered, and nothing in it goes stale on the day it does not.
    """
    return tuple(name for name in THE_CARVING_TOOLS if REGISTRY.get(name) is None)


def the_carve_is_registered() -> bool:
    return not carving_tools_missing()


#: WHAT THE DIRECTORY IS CALLED. Beside the dataset, named from the dataset
#: rather than from the clock - so the same call names the same place
#: (`tests/test_a_plan_keeps_its_identity.py`: the clock is not part of a plan's
#: identity), the person can find what we wrote, and nothing here invents a
#: location. What goes INSIDE it is the carving tool's to name and this file
#: does not guess: `into` takes a directory, the two files are written under it,
#: and their paths come back in the reply, which is what the steps below refer
#: to. A filename typed here would be a claim about somebody else's output.
_CARVED = "_carved"


def where_the_carve_would_land(dataset: str) -> Path:
    """The NEW directory this build would create, and a refusal if it is there.

    NEVER OVERWRITE AND NEVER WRITE IN PLACE. The user's data is the one thing in
    this product that cannot be regenerated. `carve_eval_set` claims its output
    directory with a bare `mkdir` and refuses anything already there, which is
    the guard; this is the same question asked at PROPOSAL time, so a person is
    told before they approve rather than after the plan stops on step one.

    A sibling of the dataset rather than a child of it, which matters when the
    dataset is a folder: the carving tool refuses a destination inside a folder
    it is reading, because our files landing in somebody's dataset directory
    means their next profile counts our rows as theirs.
    """
    source = Path(dataset)
    try:
        source = source.resolve(strict=False)
    except (OSError, ValueError):  # pragma: no cover - a path the OS refuses
        pass
    folder = source.parent / f"{source.stem}{_CARVED}"
    if folder.exists():
        raise NotEnoughToPropose(
            f"There is already something at {folder}. Nothing is planned that "
            "would write over it: a carve that overwrites is the one mistake in "
            "this product that cannot be undone, because the thing it lands on is "
            "yours and we did not make it. Move or rename that directory and ask "
            "again, or point me at the eval file inside it with eval_path and the "
            "harness will count that instead of carving a second one.",
            needs=(str(folder),),
        )
    return folder


@dataclass(frozen=True)
class WhatTheDataAlreadyAnswers:
    """What reading the file established about the column holding the answers.

    Every field is a count of something this process did, which is the point:
    the decision to carve turns on a measurement of the person's file and not on
    anybody's description of it.
    """

    column: str
    rows_read: int
    rows_with_an_answer: int
    columns_seen: tuple[str, ...]
    stopped_because: str

    @property
    def the_column_is_there(self) -> bool:
        return self.column in self.columns_seen


def the_answers_are_already_in_the_data(
    dataset: str, column: str, *, at_least: int
) -> WhatTheDataAlreadyAnswers:
    """Read far enough to say whether `at_least` rows carry an answer. No further.

    THE BOUND COMES FROM THE GATE. This stops the moment it has seen the number
    of graded rows G0 asks for, because that is the whole question and reading
    on would be this file spending somebody's seconds to learn something no
    decision here uses. The ceiling underneath it - `dataquality.DEFAULT_ROW_CAP`,
    the same one `profile_dataset` stops its own scan at - is what keeps a file
    of a million ungraded rows from turning a proposal into a scan, and the
    result says which of the three ways it stopped so the refusal can say it too.

    A row COUNTS when the column is present in it and the value is not null by
    `dataquality.is_null`, which treats absent, empty and whitespace-only alike -
    the three shapes an ungraded row actually arrives in.

    Anything the filesystem or the reader refuses comes back as zero rows read,
    which is the safe direction: this decides whether to plan a carve, and a file
    nobody could read is not a file anybody can show is graded.
    """
    seen: dict[str, None] = {}
    rows_read = 0
    with_an_answer = 0
    stopped = "the file ended"
    try:
        for record in dataquality.iter_records(dataset):
            rows_read += 1
            if isinstance(record, dict):
                for key in record:
                    if len(seen) < dataquality.COLUMN_CAP:
                        seen.setdefault(str(key), None)
                value = record.get(column)
                if column in record and not dataquality.is_null(value):
                    with_an_answer += 1
            if with_an_answer >= at_least:
                stopped = f"{at_least} graded rows had been seen, which is the question"
                break
            if rows_read >= dataquality.DEFAULT_ROW_CAP:
                stopped = (
                    f"{dataquality.DEFAULT_ROW_CAP} rows had been read, which is the "
                    "cap profile_dataset stops its own scan at"
                )
                break
    except (OSError, ValueError):  # pragma: no cover - a file the reader refuses
        return WhatTheDataAlreadyAnswers(
            column=column,
            rows_read=0,
            rows_with_an_answer=0,
            columns_seen=(),
            stopped_because="the file could not be read",
        )
    return WhatTheDataAlreadyAnswers(
        column=column,
        rows_read=rows_read,
        rows_with_an_answer=with_an_answer,
        columns_seen=tuple(seen),
        stopped_because=stopped,
    )


#: THE HALF OF THE OLD REFUSAL THAT IS STILL TRUE, and it is quoted rather than
#: reworded so that the sentence a person reads when carving is not possible is
#: the sentence they read before carving existed. It is the engine's own recipe,
#: and it is what the harness may never do on somebody's behalf.
_WRITING_THEM_IS_YOURS = (
    "What is needed is more graded examples, and writing them is yours - 30 to "
    "50 real inputs from actual traffic, graded by the person who cares about "
    "the answer. Splitting is mechanical and this harness will do it; grading is "
    "judgement and it is not ours to make. A held-out slice of rows with no right "
    "answers is not an eval set, and handing one over as if it were would open "
    "the gate on a file we wrote ourselves."
)


def _the_graded_rows(found: "WhatTheDataAlreadyAnswers", column: str) -> str:
    """What the bounded read established, in the clause both places print.

    One derivation, two places - the step's `why` and the build's `because` -
    because the same numbers said twice out of two f-strings is how the two
    start disagreeing after somebody edits one of them.
    """
    return (
        f" {found.rows_with_an_answer} of the {found.rows_read} rows read carry a "
        f"value in {column!r}; reading stopped because {found.stopped_because}."
    )


def _why_carving_is_not_honest_here(
    situation: Situation, minimum: int
) -> tuple[str, tuple[str, ...]]:
    """The reason this dataset cannot be carved, and what would fix it.

    A sentence rather than a raise, because both callers want it in a different
    envelope: the person with no eval file at all gets it as the refusal, and
    the person whose eval file is measured and short gets it after the refusal
    that was already theirs. One derivation, two envelopes - the second copy is
    the drift this repository has been bitten by twice.

    **AND `needs` IS PART OF THE ANSWER RATHER THAN THE CALLER'S GUESS.** Every
    refusal on this path used to come back needing `eval_path`, which is right
    for somebody who has an eval file somewhere and wrong for somebody standing
    on a labelled dataset who has only not said which column holds the answers -
    they would be asked for a file they do not have instead of for the one word
    that would unblock them. `ProposalRefusalCard` draws these as the things to
    supply, so a wrong one is a wrong instruction rather than a wrong sentence.

    **THE ORDER OF THE QUESTIONS IS THE POINT, AND IT WAS WRONG FIRST.** The
    registry question - is the carving tool here - came first, because it is the
    cheapest and it is the one this lane cares about. That told a person whose
    data has NO ANSWERS IN IT that a tool was missing, which reads as *this will
    work once we ship it*, and it will not: their answer is permanent and it is
    about grading. So the questions about THEIR data are asked first and answered
    completely, and the question about OUR harness is asked last. Only the first
    kind carries `_WRITING_THEM_IS_YOURS`, because that sentence is true of
    ungraded data and false of a registry gap.
    """
    if not situation.dataset_path:
        #: NO NEEDS FROM THIS BRANCH, and that is not an oversight. What the
        #: person should do next depends on which envelope they are in - point at
        #: an eval file, or write more graded rows - and only the caller knows
        #: which. A needs this function chose would be right for one of them and
        #: an instruction to do the wrong thing for the other.
        return (
            "Nothing here names a dataset the answers could be carved out of; "
            f"dataset_path is empty. {_WRITING_THEM_IS_YOURS}",
            (),
        )
    column = str(situation.expected_field or "").strip()
    if not column:
        return (
            "A dataset can only be held out as an eval set if it already carries "
            "the right answers, and nothing has said which column holds them. "
            "Tell me with expected_field and I will read that column and plan the "
            "carve. This file will not pick the column for you: which column is "
            "the right answer is the definition of correct for your task, and "
            f"that judgement is yours. {_WRITING_THEM_IS_YOURS}",
            ("expected_field",),
        )
    try:
        path = situation.require_path("dataset_path")
        # ASKED BEFORE THE FILE IS READ, because the answer to a folder is about
        # the folder. `dataquality.iter_records` reads a directory of documents
        # as one row per file with a `text` column, so a folder that reaches the
        # column check comes back as "there is no column called answer", which is
        # true, useless, and points the person at the wrong thing.
        where_the_carve_would_land(path)
    except NotEnoughToPropose as gap:
        return gap.detail, gap.needs
    found = the_answers_are_already_in_the_data(path, column, at_least=minimum)
    if not found.the_column_is_there:
        return (
            f"There is no column called {column!r} in {path}. What is there, in "
            f"the {found.rows_read} rows read, is "
            f"{sorted(found.columns_seen) or 'nothing this reader could parse'}. "
            "Nothing is carved against a column name that is not in the file. "
            f"{_WRITING_THEM_IS_YOURS}",
            ("expected_field",),
        )
    if found.rows_with_an_answer < minimum:
        return (
            f"{found.rows_with_an_answer} of the {found.rows_read} rows read from "
            f"{path} carry a value in {column!r}, and G0 asks for {minimum}. "
            f"Reading stopped because {found.stopped_because}. There is not "
            "enough already-graded data here to hold an eval set out of, so a "
            "carve would hand you rows with no right answers in them. "
            f"{_WRITING_THEM_IS_YOURS}",
            ("more graded examples",),
        )
    missing = carving_tools_missing()
    if missing:
        return (
            f"{found.rows_with_an_answer} rows of {path} carry a value in "
            f"{column!r}, so an eval set could be held out of it mechanically - "
            "and the tool that would write it is not registered here: "
            f"{list(missing)} of {list(THE_CARVING_TOOLS)} are missing from this "
            "registry. A step naming a tool nobody registered is a plan that "
            "fails after you approved it, so none is drawn. This is a gap in the "
            "harness rather than in your data, and it closes when the tool "
            "registers rather than when you write anything.",
            missing,
        )
    return "", ()


def _carve_the_eval_set(situation: Situation, minimum: int) -> Build:
    """The build: carve a graded dataset, attach what it wrote, count it, re-enter.

    Reached only when `_why_carving_is_not_honest_here` returned no reason, so
    everything below is standing on a measurement of the person's own file.

    **THE LEAK CHECK IS NOT A STEP HERE, AND THAT IS THE OPPOSITE OF CARELESS.**
    The first draft of this build ran `check_split_leakage` on the carve's own
    output as step two. `carve_eval_set` already runs the real one over the two
    files it has just written and puts the answer in its reply, so a second step
    would be a second full near-duplicate scan of somebody's dataset to learn a
    number already in the payload. What the plan does instead is be HELD TO it:
    the carve's exit criterion is the tool's `ok`, which that tool sets false
    when its own leak check finds anything or when the two files do not add up to
    what was read. A split this harness produced and did not verify would be
    worse than one the person made themselves; a split it verified twice is a
    scan they paid for twice.

    **THE SIZE COMES FROM THE GATE, AND FROM ONE DERIVATION OF IT.** `rows` is
    NOT passed. The tool reads G0's own threshold out of
    `docs/diagnosis_engine.yaml` itself and says in its reply where it read it;
    passing this file's `g0_minimum()` would put a second parser of the same gate
    row into the same call, and the day they disagree the plan would be arguing
    with the tool about the product's own policy. What this plan does with the
    number is hold the COUNT step to it, which is the half a proposal is for.

    **AND IT DOES NOT RE-IMPLEMENT THE TOOL'S OTHER REFUSALS.** `carve_eval_set`
    also declines a one-value answer column, a dataset too small to give the rows
    up without starving training, and a read longer than its own cap. Those are
    its rules, they are checked against the whole file rather than against the
    bounded read this proposer does, and it is explicit that there is no state of
    the world in which it refused and also wrote. So they are carried as a risk
    that names them rather than copied here, because a second implementation of
    somebody else's rule is the drift this repository has been bitten by twice.
    """
    dataset = situation.require_path("dataset_path")
    column = str(situation.expected_field or "").strip()
    into = where_the_carve_would_land(dataset)
    found = the_answers_are_already_in_the_data(dataset, column, at_least=minimum)

    # WHAT THE CARVING STEP WILL BE CALLED WITH. Offered, filtered by the tool's
    # own schema, and refused when the two lanes disagree about what to call
    # things - `_a_call_that_fits` and `_at_least_one_of` are that contract made
    # mechanical, and the alternative is a private table of somebody else's
    # argument names, which is the closed list `_subject_of_a_call` deleted. It
    # earned its keep on the first day: every name this file offered first was
    # wrong, and the disagreement was a refusal rather than a broken plan.
    offer: dict[str, Any] = {
        "path": dataset,
        "dataset_path": dataset,
        "answer_column": column,
        "expected_field": column,
        "label_field": column,
        "into": str(into),
        "out_dir": str(into),
        "destination": str(into),
    }
    carving = _a_call_that_fits(THE_CARVE, offer)
    _at_least_one_of(
        carving,
        THE_CARVE,
        ("path", "dataset_path"),
        what="which dataset to carve the eval set out of",
    )
    _at_least_one_of(
        carving,
        THE_CARVE,
        ("answer_column", "expected_field", "label_field"),
        what=(
            "which column already holds the right answers. That column is the "
            "whole difference between a split and a manufactured eval set, and a "
            "carve that ran without it would be holding out rows nobody graded"
        ),
    )
    _at_least_one_of(
        carving,
        THE_CARVE,
        ("into", "out_dir", "destination"),
        what=(
            "where to put what it writes. This plan names the directory before "
            "you approve it, because what a person approves is what appears on "
            "their disk, and because a plan that cannot say where the files go "
            "cannot promise that nothing is written over"
        ),
    )

    carve = Step(
        id="carve",
        tool=THE_CARVE,
        why=(
            f"Hold out the rows G0 asks for from {Path(dataset).name}, graded in "
            f"the column {column!r} that you named, and write them and the "
            f"remainder as two new files under {into}. Your file is read and "
            "never written, the directory does not exist yet, and how many rows "
            "are held out is the gate's own threshold read off the engine by the "
            "tool rather than a percentage chosen by anybody."
            + _the_graded_rows(found, column)
        ),
        arguments=carving,
        produces=(
            Output(
                "eval_path",
                "string",
                "the held-out file the carve wrote",
                at="eval_path",
            ),
        ),
        cost=_local_cost(
            THE_CARVE,
            find_out_by=(
                "carve a small slice first and read the seconds back; the rate is "
                "then known for this machine and this format"
            ),
        ),
        exit_criterion=ExitCriterion(
            stated=(
                "the carve reports ok - which that tool sets only when the two "
                "files it wrote account for every row it read AND the leak check "
                "it ran over them found nothing. A split we produced and did not "
                "verify would be worse than one you made yourself"
            ),
            source="tool_result",
            subject="ok",
            comparator="is_true",
        ),
        risks=(
            Risk(
                what=(
                    "the carve refuses - the answers are all one value, or holding "
                    f"{minimum} rows out would leave fewer than "
                    f"{dataquality.MIN_ROWS_FOR_TRAINING} to train on, or the file "
                    "is longer than its own read cap"
                ),
                what_we_do=(
                    "the plan stops at this step and nothing else runs. Those are "
                    f"{THE_CARVE}'s own rules, checked against your whole file "
                    "rather than against the bounded read this proposal did, and "
                    "they are not re-implemented here because a second copy of "
                    "somebody else's rule is how two answers to one question "
                    "start. It refuses before it creates anything, so a refused "
                    "carve leaves your disk exactly as it was"
                ),
            ),
            Risk(
                what=(
                    "the held-out file comes back with more rows than the gate "
                    "asked for"
                ),
                what_we_do=(
                    "nothing, and it is not a fault. Identical rows hash the same "
                    "and are drawn together, so a run of them cannot be split "
                    "across the two files - which is what makes exact-duplicate "
                    "leakage impossible here by construction. The count below is "
                    "held to a floor rather than to an exact number for that "
                    "reason"
                ),
            ),
        ),
    )

    attach = Step(
        id="attach",
        tool="attach_context",
        why=(
            "Record where the carved eval set is, so everything after this refers "
            "to the same file and so a month from now the thread says where this "
            "eval set came from. The path is the one the carve reported rather "
            "than one this plan predicted: the tool names the files it writes."
        ),
        arguments={
            "path": Ref("carve", "eval_path"),
            "role": "the evaluation set",
            "note": (
                f"carved by this harness from {dataset}, graded in the column "
                f"{column!r} of that file, not by us"
            ),
        },
        produces=(
            Output(
                "path",
                "string",
                "the path as the harness recorded it",
                at="what_it_is.path",
            ),
        ),
        needs=("carve",),
        cost=_local_cost(
            "attach_context",
            find_out_by="it is one filesystem stat and one row written; time it once",
        ),
        exit_criterion=ExitCriterion(
            stated="the harness has the carved eval set's path on file",
            source="tool_result",
            subject="ok",
            comparator="is_true",
        ),
    )

    count = Step(
        id="count",
        tool="measure_eval_set",
        why=(
            "Count the file we wrote rather than trusting the number we wrote it "
            f"with. G0 asks for {minimum}, and the carve saying it held back "
            f"{minimum} rows is this harness's own arithmetic until a tool reads "
            "the file and finds them. The carve stamps nothing and says so; this "
            "is the step that makes eval_size_n a measurement."
        ),
        arguments={"path": Ref("attach", "path"), "finish_the_count": True},
        produces=(Output("rows", "integer", "the counted rows", at="rows"),),
        needs=("attach",),
        cost=_local_cost(
            "measure_eval_set",
            find_out_by=(
                "the result carries the seconds the count took; run it once and "
                "the rate is known for this machine and this format"
            ),
        ),
        exit_criterion=ExitCriterion(
            stated=(
                f"the count reaches the end of the carved file and clears {minimum} rows"
            ),
            source="tool_result",
            subject="rows",
            comparator="at_least",
            value=minimum,
        ),
    )

    return Build(
        id="carve_the_eval_set",
        title="Carve a held-out eval set out of the answers your data already has",
        for_outcome=situation.outcome,
        because=(
            "The diagnosis stopped at G0: there is no counted eval set. You have a "
            "dataset that already carries the right answers, so the eval set does "
            "not have to be written - it has to be held out."
            + _the_graded_rows(found, column)
            + " Splitting is mechanical and this plan does it; the grading was "
            "already yours and nothing here touches it or checks it. Your dataset "
            f"is read and never written: what the carve writes goes under {into}, "
            "which does not exist yet."
        ),
        steps=(
            carve,
            attach,
            count,
            _recheck_step(
                ("count",),
                "eval_size_n",
                why=(
                    "Walk the tree again on the counted number. The count is a "
                    "fact; what it means is the engine's to decide, not this "
                    "plan's."
                ),
            ),
        ),
        environment=_sandbox("carve_the_eval_set", dataset),
        exit_criterion=ExitCriterion(
            stated=(
                f"eval_size_n is MEASURED and at least {minimum}, so G0_EVAL_SET "
                "opens on a file this harness wrote and then counted - not on the "
                "row count it wrote the file with"
            ),
            source="diagnosis",
            subject="gate_ledger.G0_EVAL_SET.status",
            comparator="equals",
            value=diagnosis.GATE_PASSED,
        ),
        risks=(
            Risk(
                what=(
                    "the rows this holds out are not representative of the traffic "
                    "you actually get, because your dataset is not"
                ),
                what_we_do=(
                    "nothing here can fix that and nothing here pretends to. G0's "
                    "recipe asks for real inputs sampled from actual traffic; what "
                    "this plan holds out is a slice of the file you have, and if "
                    "that file is not your traffic then neither is the eval set. "
                    "The score it later produces is a score on your dataset and "
                    "should be read as one"
                ),
            ),
            Risk(
                what="the answers in that column are wrong",
                what_we_do=(
                    "nothing, and no step here could. This plan checked that the "
                    "answers are THERE, which is a question about the file; "
                    "whether they are RIGHT is the judgement G0's recipe asks the "
                    "person who cares about the answer to make, and it is the one "
                    "thing this product never does on anybody's behalf"
                ),
            ),
            Risk(
                what=(
                    "holding the eval set out leaves fewer rows to train on than "
                    "you expected"
                ),
                what_we_do=(
                    "this plan read only as far as it needed to answer G0's "
                    f"question - {found.rows_read} rows, stopping because "
                    f"{found.stopped_because} - so it does not know how large your "
                    "dataset is and does not claim to. assess_the_data answers "
                    f"that and reports what a carve would leave, and {THE_CARVE} "
                    "refuses outright rather than leaving you a training set too "
                    "small to train on"
                ),
            ),
        ),
        facts=dict(situation.origins),
    )


# ---------------------------------------------------------------------------
# The proposers.


def _propose_build_the_eval_set(situation: Situation) -> Build:
    """`BLOCKED__BUILD_EVAL_SET` - when the harness has simply never counted.

    The gate's own `on_unsubstantiated` note is this build in prose: *"Point me
    at the file or the folder and I will count it myself; if the count clears
    thirty, this gate opens on the same breath."*

    AND IT REFUSES WHEN COUNTING WOULD CHANGE NOTHING. If `eval_size_n` is
    already MEASURED and still short, the person needs more examples, and that
    is their work rather than a build. Proposing a count that has already
    happened would be the product looking busy.

    "ALREADY COUNTED" IS A CLAIM ABOUT A FILE AND NOT ABOUT A NUMBER, which is
    why the path is established before the refusal instead of after it. The
    refusal used to fire on any measured `eval_size_n`, so a person who pointed
    at a new eval file was told "your eval set has already been counted: 120
    rows" - about a file they had not mentioned. That is the same omission as
    the request-count defect, reached through the door marked refusal: a number
    genuinely measured, attached to nothing saying what it counted, answering a
    question about something else.

    **AND THE OTHER REFUSAL WAS HALF TRUE, WHICH IS THE WORSE KIND.** *"What is
    needed is more graded examples, and writing them is yours"* is exactly right
    for somebody whose data has no right answers in it, and wrong for somebody
    holding a labelled dataset: for them the eval set does not have to be
    written, it has to be held out, and holding it out is mechanical work this
    harness refused to do while announcing that it could - `assess_the_data`
    part five answers *"an evaluation set can be carved out of this"* and then
    says *"nothing has been carved and no file has been written."*

    So counting a file is no longer the only build here. The half that was true
    is untouched and is still reached the same way; what changed is that it is
    now reached only when it IS true, and `_why_carving_is_not_honest_here` is
    what decides which of the two a person is, by reading their file rather than
    by taking anybody's description of it.
    """
    minimum = g0_minimum(situation.spec)

    # NO EVAL FILE AT ALL. Counting a file that does not exist helps nobody, and
    # `require_path` below would refuse with "tell me where it is" - which is the
    # right answer for somebody who has one and the wrong one for somebody whose
    # answers are sitting in a column of the dataset they already named.
    if not str(situation.eval_path or "").strip() and situation.dataset_path:
        why_not, needs = _why_carving_is_not_honest_here(situation, minimum)
        if not why_not:
            return _carve_the_eval_set(situation, minimum)
        raise NotEnoughToPropose(
            "There is no eval set here to count, and no build that would make one "
            f"honestly. {why_not}",
            needs=needs or ("eval_path",),
        )

    path = situation.require_path("eval_path")
    target = Subject.of_path(path)
    already_counted, counted_before = a_measurement_of(situation, "eval_size_n", path)

    if already_counted:
        # THE EVAL FILE IS COUNTED AND SHORT, AND THE ANSWERS MAY BE ELSEWHERE.
        # The same half-truth reached through the other door: counting this file
        # again would change nothing, and that says nothing about a labelled
        # dataset sitting beside it. Carving from that dataset writes a NEW eval
        # set and leaves the short one exactly where it is.
        why_not, needs = _why_carving_is_not_honest_here(situation, minimum)
        if not why_not:
            return _carve_the_eval_set(situation, minimum)
        raise NotEnoughToPropose(
            f"Your eval set has already been counted: {situation.values.get('eval_size_n')} "
            f"rows, measured, in {target.key}, against the {minimum} this gate "
            f"asks for. Counting it again would change nothing. {why_not} There "
            "is no build here that would be honest.",
            needs=needs or ("more graded examples",),
        )

    #: Said in the proposal itself when a count exists and is of something else,
    #: because "there is a measured count and we are counting anyway" is the
    #: kind of thing that looks like the product having forgotten.
    stale_count = ""
    if situation.is_measured("eval_size_n"):
        stale_count = (
            f" A count of {counted_before.key} is on file"
            if counted_before
            else " A count is on file and nothing records what it counted"
        ) + (
            f", and that is not {target.key}, so it says nothing about this "
            "file and this build counts it rather than reusing a number that "
            "was measured off something else."
        )

    attach = Step(
        id="attach",
        tool="attach_context",
        why="Record where the eval set is, so everything after this refers to the same file.",
        arguments={"path": path, "role": "the evaluation set"},
        produces=(
            Output(
                "path",
                "string",
                "the path as the harness recorded it",
                at="what_it_is.path",
            ),
        ),
        cost=_local_cost(
            "attach_context",
            find_out_by="it is one filesystem stat and one row written; time it once",
        ),
        exit_criterion=ExitCriterion(
            stated="the harness has the path on file",
            source="tool_result",
            subject="ok",
            comparator="is_true",
        ),
        operates_on=target,
    )
    count = Step(
        id="count",
        tool="measure_eval_set",
        why=(
            "Count the rows myself rather than taking anybody's word for the "
            f"number. G0 asks for {minimum}."
        ),
        arguments={"path": Ref("attach", "path"), "finish_the_count": True},
        produces=(Output("rows", "integer", "the counted rows", at="rows"),),
        needs=("attach",),
        cost=_local_cost(
            "measure_eval_set",
            find_out_by=(
                "the result carries the seconds the count took; run it once and "
                "the rate is known for this machine and this format"
            ),
        ),
        exit_criterion=ExitCriterion(
            stated=f"the count reaches the end of the file and clears {minimum} rows",
            source="tool_result",
            subject="rows",
            comparator="at_least",
            value=minimum,
        ),
        risks=(
            Risk(
                what="the eval set is very large and the count takes a long time",
                what_we_do=(
                    "the count runs unbounded on purpose so it cannot return a "
                    "lower bound dressed as an answer; it streams its progress and "
                    "can be cancelled, and a cancelled count records nothing"
                ),
            ),
            Risk(
                what="the file is a format no reader in this harness can open",
                what_we_do=(
                    "the step says so and stamps nothing; the plan stops here "
                    "rather than running a diagnosis on a count that did not happen"
                ),
            ),
        ),
    )
    return Build(
        id="build_the_eval_set",
        title="Count the eval set you have, and see whether G0 opens",
        for_outcome=situation.outcome,
        because=(
            "The diagnosis stopped at G0: there is no counted eval set, so nothing "
            "downstream can be measured rather than felt. You pointed at a file; "
            "the harness counts it rather than believing it." + stale_count
        ),
        steps=(attach, count, _recheck_step(("count",), "eval_size_n", why=(
            "Walk the tree again on the counted number. The count is a fact; what "
            "it means is the engine's to decide, not this plan's."
        ))),
        environment=_sandbox("build_the_eval_set", path),
        exit_criterion=ExitCriterion(
            stated=(
                f"eval_size_n is MEASURED and at least {minimum}, so G0_EVAL_SET "
                "opens on a number the harness read itself"
            ),
            source="diagnosis",
            subject="gate_ledger.G0_EVAL_SET.status",
            comparator="equals",
            value=diagnosis.GATE_PASSED,
        ),
        risks=(
            Risk(
                what="the file turns out to hold fewer rows than the gate asks for",
                what_we_do=(
                    "the plan does not pass, and it says so with the real count. "
                    "That is the honest outcome, not a failure of the build - the "
                    "next move is more graded examples, which is yours"
                ),
            ),
        ),
        facts=dict(situation.origins),
    )


def _propose_measure_the_baseline(situation: Situation) -> Build:
    """`ACTION__MEASURE_BASELINE` - G1's remedy, and the one that spends tokens.

    The step order is the argument: count the eval set first, then score against
    it, then re-enter the tree. Counting first is not tidiness - it is what makes
    the request count of the second step a derived number instead of an unknown
    one, which is visible in this build's own cost.

    AND WHETHER THE COUNT STEP IS NEEDED IS DECIDED BY THE COST, NOT THE OTHER
    WAY ROUND. It used to be decided by "is `eval_size_n` measured", which is a
    question about a number rather than about this file, so a count of some
    other file both suppressed the count step and supplied the request estimate.
    Now the estimate is worked out first against the file this build will score;
    if it could not be derived - never counted, counted off something else,
    counted with no record of what - the build counts, and the estimate's own
    `find_out_by` is describing a step that is really there.
    """
    path = situation.require_path("eval_path")
    input_field = str(situation.input_field or "").strip()
    expected_field = str(situation.expected_field or "").strip()
    missing = [
        name
        for name, value in (
            ("input_field", input_field),
            ("expected_field", expected_field),
        )
        if not value
    ]
    if missing:
        raise NotEnoughToPropose(
            "I cannot plan a baseline without knowing which column holds the input "
            f"and which holds the answer that would be right. Missing: {missing}. "
            "Run preview_dataset_rows on the file and the column names are in the "
            "result.",
            needs=tuple(missing),
        )

    # THE SUBJECT COMES OUT OF THE CALL THIS STEP WILL MAKE, not out of the path
    # the caller named. They are the same file whenever the call is legible, and
    # when it is not - two of these arguments naming files, and nothing on
    # `measure_baseline` saying which one it opens - this is where the product
    # finds out, in time to cost the step UNKNOWN and plan the count, rather than
    # in `Build.validate` where the only available answer is a refusal to plan.
    # `input_field` and `expected_field` are strings a caller supplies, so this
    # is reachable without anybody being adversarial.
    scoring = {
        "eval_path": path,
        "input_field": input_field,
        "expected_field": expected_field,
        "sample": situation.sample,
    }
    target, unidentified = _subject_of_a_call("measure_baseline", scoring)

    cost = _baseline_cost(situation, target, unidentified=unidentified)
    steps: list[Step] = []
    needs_for_baseline: tuple[str, ...] = ()
    if not cost.model_requests.known:
        counting = {"path": path, "finish_the_count": True}
        steps.append(
            Step(
                id="count",
                tool="measure_eval_set",
                why=(
                    "Count the eval set before scoring against it, so the score "
                    "has a denominator the harness read itself - and so this "
                    "build can say how many requests the next step makes."
                ),
                arguments=counting,
                produces=(Output("rows", "integer", "the counted rows", at="rows"),),
                cost=_local_cost(
                    "measure_eval_set",
                    find_out_by=(
                        "the result carries the seconds the count took; run it "
                        "once and the rate is known for this machine"
                    ),
                ),
                exit_criterion=ExitCriterion(
                    stated="the rows are counted to the end of the file",
                    source="tool_result",
                    subject="exact",
                    comparator="is_true",
                ),
                operates_on=_subject_of_a_call("measure_eval_set", counting)[0],
            )
        )
        needs_for_baseline = ("count",)

    steps.append(
        Step(
            id="baseline",
            tool="measure_baseline",
            why=(
                "Score what already exists on your own eval set. This is the "
                "number every later claim of improvement is measured against, and "
                "the gate will not open on anybody's word for it."
            ),
            arguments=scoring,
            produces=(
                Output("score", "number", "what the connected model scored", at="baseline_score"),
                Output("rows_scored", "integer", "how many rows it was scored on", at="rows_scored"),
                Output(
                    "resolution",
                    "string",
                    "what difference this many rows can actually resolve",
                    at="resolution",
                ),
            ),
            needs=needs_for_baseline,
            cost=cost,
            operates_on=target,
            exit_criterion=ExitCriterion(
                stated=(
                    "the connected model is scored on your eval rows and a trivial "
                    "baseline is scored on the same rows"
                ),
                source="tool_result",
                subject="ok",
                comparator="is_true",
            ),
            risks=(
                Risk(
                    what=(
                        "the connected model is not on this machine, so scoring "
                        "would send your rows off it"
                    ),
                    what_we_do=(
                        "the step refuses to run on a model's say-so and stops to "
                        "ask you to start it yourself. That refusal is in "
                        "app/tools/measure.py and is not something this plan can "
                        "wave through"
                    ),
                ),
                Risk(
                    what="the named columns are not in the file",
                    what_we_do=(
                        "nothing is scored and nothing is stamped; the step reports "
                        "the column names it did find so the plan can be corrected "
                        "rather than re-run hopefully"
                    ),
                ),
                Risk(
                    what=(
                        "the sample is small enough that the score cannot resolve a "
                        "difference you would care about"
                    ),
                    what_we_do=(
                        "the result states its own resolution and this build "
                        "carries it as an output, so the number is never shown "
                        "without what it can actually tell apart"
                    ),
                ),
            ),
        )
    )
    steps.append(
        _recheck_step(
            ("baseline",),
            "baseline_measured",
            why=(
                "Walk the tree again now that a baseline exists. G1 asks whether "
                "one was measured, and only the engine decides whether it passes."
            ),
        )
    )

    return Build(
        id="measure_the_baseline",
        title="Measure what you already have, before anybody trains anything",
        for_outcome=situation.outcome,
        because=(
            "The diagnosis stopped at G1: nothing has scored the model you already "
            "have on your own eval set, so there is no number for a later "
            "improvement to be measured against."
        ),
        steps=tuple(steps),
        environment=_sandbox(
            "measure_the_baseline",
            path,
            reason=(
                "scoring sends rows of your eval set to the model you connected. "
                "If that model runs on this machine nothing leaves it; if it is a "
                "hosted API, these rows do, and that is why this is declared here "
                "where you can see it before you say yes"
            ),
        ),
        exit_criterion=ExitCriterion(
            stated=(
                "baseline_measured is MEASURED - a score the harness took itself, "
                "on your rows, with the resolution stated beside it"
            ),
            source="diagnosis",
            subject="fact_origins.baseline_measured",
            comparator="is_measured",
        ),
        risks=(
            Risk(
                what="the model scores badly and the answer changes",
                what_we_do=(
                    "that is the plan working. The build's job is to produce the "
                    "number, not a particular value of it, and the engine re-reads "
                    "the tree on whatever comes back"
                ),
            ),
        ),
        facts=dict(situation.origins),
    )


#: The tool that scores a model nobody trained. Named rather than spelled at
#: each use, for `THE_ADAPTER_SCORER`'s reason: which tool a plan drives is a
#: thing the plan says out loud.
THE_CANDIDATE_SCORER = "score_a_candidate_model"

#: The two outcomes this build serves, and the fact each one turns on. Both
#: facts are `source: ask`, so both builds end in a question and neither can
#: ever end in a stamp - see the proposer.
_CANDIDATE_OUTCOMES = {
    "NO_TRAIN__SWAP_MODEL": (
        "model_swap_tried",
        "Having seen that score: have you tried a different model?",
    ),
    "NO_TRAIN__USE_EXISTING_BASE": (
        "user_requested_from_scratch",
        "Having seen that score: do you still want to train from scratch?",
    ),
}


def the_candidate_scorer_is_registered() -> bool:
    """Whether the sandbox scorer this build drives exists.

    The shape every bench predicate here uses: read the registry rather than
    assume, so removing the tool moves both outcomes back to `NOT_COVERED` with
    a reason naming it instead of drawing a plan whose step is missing.
    """
    return REGISTRY.get(THE_CANDIDATE_SCORER) is not None


def _propose_score_a_candidate(situation: Situation) -> Build:
    """`NO_TRAIN__SWAP_MODEL` / `NO_TRAIN__USE_EXISTING_BASE` - measure, then ask.

    THE REFUSAL THIS REPLACES NAMED ITS OWN REMEDY: *"find_models and
    read_model_config can find a candidate and nothing here can connect it or
    score it, so a plan would stop one step short of the number that decides
    the question."* `score_a_candidate_model` is that step, and it needs no
    connection - it answers in a sandbox, the way the control arm of an adapter
    run always has.

    IT ENDS IN A QUESTION AND THAT IS PERMANENT, NOT A SHORTFALL. Both facts
    these outcomes turn on are `source: ask`, and
    `evidence.may_be_declared_measurable` refuses an asked fact to every
    instrument forever - so nothing will ever stamp them, and
    `Build._validate_questions` permits the question for exactly that reason.
    `G4_CHEAPER_MODEL_CONSIDERED` says it in the ledger's own voice: *"Tell me
    yourself that you looked, and this one opens."* What the build changes is
    that the person tells us having just seen the candidate's score on their own
    rows, instead of from memory.
    """
    fact, question = _CANDIDATE_OUTCOMES[situation.outcome]
    evaluation = situation.require_path("eval_path")
    candidate = str(situation.base_model or "").strip()

    if not candidate:
        raise NotEnoughToPropose(
            "I can rank what fits this machine and I will not choose which model "
            "to try for you. Name it with base_model and I will write the build: "
            "which model you put in front of your users carries a licence and a "
            "commitment about what your product is, and that is not a choice "
            "this harness makes on your behalf.",
            needs=("base_model",),
        )

    baseline_run = the_baseline_run_to_beat(situation.thread_id, evaluation)
    if baseline_run is None:
        raise NotEnoughToPropose(
            "there is no completed eval run in this conversation over "
            f"{evaluation}, and a candidate's score is only worth having as a "
            "PAIRED comparison against one - the same rows, graded twice. "
            "measure_baseline scores and keeps no rows; run_eval keeps every "
            "row, and it is the one step that unlocks this build.",
            needs=("run_eval",),
        )

    rank = Step(
        id="rank",
        tool="find_models",
        why=(
            "Show what actually fits this machine, with the reasoning shown and "
            "every candidate that was thrown out carrying its reason. It does "
            f"not choose {candidate} for you and is not wired to - it is here so "
            "you can see, before you approve anything, whether the model you "
            "named is the one this machine should be running."
        ),
        arguments=_a_call_that_fits("find_models", {}, must_carry=()),
        produces=(
            Output("ranked", "array", "the candidates that fit, best first", at="ranked"),
        ),
        cost=_local_cost(
            "find_models",
            find_out_by="it reads the hub index and this machine's profile; time one call",
        ),
        exit_criterion=ExitCriterion(
            stated="a ranked list of what fits is on screen",
            source="tool_result",
            subject="ranked",
            comparator="exists",
        ),
    )

    config = Step(
        id="config",
        tool="read_model_config",
        why=(
            f"Fetch the real config.json for {candidate} rather than assuming "
            "its shape. The scoring step below loads it, and a geometry taken "
            "from memory is how a run fails at minute one."
        ),
        arguments=_a_call_that_fits(
            "read_model_config", {"repo_id": candidate}, must_carry=("repo_id",)
        ),
        produces=(
            Output("geometry", "object", "what the config actually says", at="geometry"),
        ),
        needs=("rank",),
        cost=_local_cost(
            "read_model_config",
            find_out_by="one small file over the network; time one fetch",
        ),
        exit_criterion=ExitCriterion(
            stated="the model's real configuration has been read",
            source="tool_result",
            subject="geometry",
            comparator="exists",
        ),
    )

    sandbox_step = Step(
        id="sandbox",
        tool="make_sandbox",
        why=(
            "Make the isolated place this answers in, and make it part of the "
            f"build rather than something you set up first. It pins the "
            f"{THE_LORA_RECIPE} environment, whose eval kind is what answers "
            "your rows, and gets its own working directory so a trial that goes "
            "wrong is deleted rather than untangled."
        ),
        arguments=_a_call_that_fits(
            "make_sandbox",
            {
                "purpose": (
                    f"score {candidate} on the rows eval run "
                    f"{baseline_run['run_id']} graded, to see whether a "
                    "different model clears your bar before anything is trained"
                ),
                "recipe": THE_LORA_RECIPE,
                "egress": True,
                "egress_reason": (
                    f"the weights for {candidate} have to be fetched before "
                    "anything can be answered with them"
                ),
            },
            must_carry=("recipe", "egress", "egress_reason"),
        ),
        produces=(
            Output(
                "sandbox_name",
                "string",
                "what this sandbox is called, so the step below names it rather "
                "than taking whichever one is newest",
                at="name",
            ),
        ),
        needs=("config",),
        cost=_local_cost(
            "make_sandbox",
            find_out_by="pinning an environment already materialised; time one call",
        ),
        exit_criterion=ExitCriterion(
            stated="an isolated, pinned place to answer in exists",
            source="tool_result",
            subject="name",
            comparator="exists",
        ),
    )

    score = Step(
        id="score",
        tool=THE_CANDIDATE_SCORER,
        why=(
            f"Answer the SAME rows eval run {baseline_run['run_id']} graded, "
            f"with {candidate}, and report the paired difference. This is the "
            "number the question below is worth answering against - and a "
            "difference inside what those rows can resolve comes back as no "
            "evidence rather than as a win."
        ),
        arguments=_a_call_that_fits(
            THE_CANDIDATE_SCORER,
            {
                # A `Ref` AND NOT A NAME: the executor must answer in the sandbox
                # THIS plan made, rather than whichever one is newest when it
                # gets there.
                "sandbox": Ref("sandbox", "sandbox_name"),
                "baseline_run_id": int(baseline_run["run_id"]),
                "thread_id": int(situation.thread_id),
                "base_model": candidate,
            },
            must_carry=("sandbox", "baseline_run_id", "thread_id", "base_model"),
        ),
        produces=(
            Output(
                "against_baseline",
                "object",
                "the paired comparison, with its resolution",
                at="against_baseline",
            ),
        ),
        needs=("sandbox",),
        cost=_local_cost(
            THE_CANDIDATE_SCORER,
            find_out_by=(
                "one generate() call per graded row inside the sandbox; the "
                "recipe's own log reports the seconds and the peak memory"
            ),
        ),
        exit_criterion=ExitCriterion(
            stated="the candidate has a score on your rows, paired against your baseline",
            source="tool_result",
            subject="against_baseline",
            comparator="exists",
        ),
        risks=(
            Risk(
                what="the weights do not fit on this machine, or the fetch fails",
                what_we_do=(
                    "the step reports the recipe's own refusal and what it "
                    "needed; nothing is stamped either way, so a failed answer "
                    "leaves the conversation exactly where it was"
                ),
            ),
        ),
    )

    return Build(
        id="score_a_candidate",
        title=f"Score {candidate} on your own rows, then decide",
        for_outcome=situation.outcome,
        because=(
            "The gate below asks whether you have considered something cheaper, "
            "and it is yours to answer. This build exists so that you answer it "
            "against a number measured on your own eval set rather than from "
            "memory - the same rows your baseline was graded on, the same "
            "comparison, with its resolution stated."
        ),
        steps=(rank, config, sandbox_step, score),
        # EGRESS ON, WITH THE SENTENCE THAT TURNS IT ON. `find_models` reads the
        # hub index and the scoring step fetches weights, so this plan does
        # leave the machine - and `Build._validate_egress` refuses a step that
        # might, in an environment that did not say so. The reason is what the
        # person reads before approving.
        environment=_sandbox(
            "score_a_candidate",
            evaluation,
            reason=(
                f"the hub is read to rank what fits, and {candidate}'s weights "
                "are fetched before anything can be answered with them"
            ),
        ),
        exit_criterion=ExitCriterion(
            stated=(
                "you have said, in your own person, whether this settles it - "
                "and the tree has a branch to take"
            ),
            source="diagnosis",
            subject=f"fact_origins.{fact}",
            comparator="equals",
            value=diagnosis.STATED,
        ),
        questions=(
            Question(
                ask=question,
                why=(
                    "No tool in this harness measures this and none ever can - "
                    "the ledger declares it `source: ask`, which is it saying "
                    "there is nobody to ask but you. The steps above are so that "
                    "you answer it having seen the number."
                ),
                fact=fact,
            ),
        ),
        facts=dict(situation.origins),
    )


def _propose_make_the_metric_programmatic(situation: Situation) -> Build:
    """`ACTION__MAKE_THE_METRIC_PROGRAMMATIC` - look at your own answers, then say.

    THE ASK-SHAPED ONE, AND THE TRAP IS NAMED IN ITS OWN OLD REASON. That reason
    said `run_eval`'s `exact_match` and `contains` ARE programmatic metrics,
    "which makes this look coverable and is the trap - grading with one says
    nothing about whether the score the person cares about can be computed
    without them." That is exactly right, and it is why no step here scores
    anything: a build that ran `run_eval` and reported 61% would be answering a
    different question loudly.

    What the harness CAN do is show the person the answers they are asking a
    program to judge. A closed label a rule can compare and a paragraph only a
    reader can judge look different at a glance, and that difference is the whole
    question. So: one local step that reads their own eval file, then the
    question, which is theirs.

    Contrast `_propose_count_the_rows` below, which asks nothing at all. The rule
    the two of them make together is the one worth carrying: **ask only what
    cannot be looked at.**
    """
    path = situation.require_path("eval_path")
    expected = (situation.expected_field or "").strip()

    look = Step(
        id="look",
        tool="preview_dataset_rows",
        why=(
            "Put the answers you are grading in front of you. Whether a program "
            "can decide 'right' is a question about what these look like - a "
            "closed label a rule can compare, or a paragraph only a reader can "
            "judge - and it is quicker to see than to remember."
        ),
        arguments={"path": path, "limit": 10},
        produces=(Output("rows", "array", "the first rows, as they are", at="rows"),),
        cost=_local_cost(
            "preview_dataset_rows",
            find_out_by="it reads a handful of rows; time one preview and it is known",
        ),
        exit_criterion=ExitCriterion(
            stated="rows from your eval set are on screen",
            source="tool_result",
            subject="rows",
            comparator="exists",
        ),
    )

    field = f" in `{expected}`" if expected else ""
    return Build(
        id="make_the_metric_programmatic",
        title="Look at your answers, then say whether a program can score them",
        for_outcome=situation.outcome,
        because=(
            "Nothing can search for a better prompt while only a person can say "
            "whether an output is good, and a fine-tune has nothing to aim at "
            "either. Whether your score is computable is not a fact about this "
            "harness - it is a fact about your definition of right, so the last "
            "move here is yours."
        ),
        steps=(look,),
        environment=_sandbox("make_the_metric_programmatic", path),
        exit_criterion=ExitCriterion(
            stated=(
                "you have said whether a program can decide right from wrong on "
                "your task, and the tree has a branch to take"
            ),
            source="diagnosis",
            subject="fact_origins.metric_is_programmatic",
            comparator="equals",
            value=diagnosis.STATED,
        ),
        questions=(
            Question(
                ask=(
                    f"Looking at the answers{field}: could a program decide "
                    "whether one is right, without a person reading it?"
                ),
                why=(
                    "This harness scores with exact match, containment and a "
                    "judge, and any of those would return a number here. None of "
                    "them can tell you whether the number means what you need it "
                    "to mean, which is why this is a question and not a step."
                ),
                fact="metric_is_programmatic",
            ),
        ),
        facts=dict(situation.origins),
    )


def _propose_count_the_rows(situation: Situation) -> Build:
    """`ACTION__COUNT_THE_ROWS` - go and count, do not ask.

    THE OPPOSITE SHAPE TO `_propose_name_the_modality` BELOW, AND THE
    DIFFERENCE IS THE WHOLE ARGUMENT. `modality` ends in a Question because no
    tool can read what kind of data something is off a file. A row count is not
    a judgement, and since 2026-08-28 `profile_dataset` stamps `tabular_rows`
    from the same completed scan it has always counted `eval_size_n` with. So
    this build has no question in it at all: it runs, the number is MEASURED,
    and the tree moves.

    Until that stamp existed this proposer would have been the defect its own
    `NOT_COVERED` entry described - "it would run, look successful, re-enter the
    tree and land on this same outcome, having spent the user's time to move
    nothing." That sentence was true when it was written and is why the tool
    came first. The exit criterion below is what makes it stay false: it is not
    "the tool returned ok", it is that the LEDGER now holds this fact as a
    measurement.
    """
    path = situation.require_path("dataset_path")

    count = Step(
        id="count",
        tool="profile_dataset",
        why=(
            "Read the table and count its rows. One number decides this whole "
            "branch - under 1,000 the honest answer is statistics and more data, "
            "1,000 to 10,000 a tabular foundation model, above that a "
            "gradient-boosted tree - and it is a number the harness can take for "
            "itself rather than ask you to remember."
        ),
        arguments={"path": path},
        produces=(
            Output("rows", "integer", "how many rows the scan counted", at="rows"),
        ),
        cost=_local_cost(
            "profile_dataset",
            find_out_by=(
                "profiling scans rows; run it once on this file and the time is "
                "known for this size"
            ),
        ),
        exit_criterion=ExitCriterion(
            stated="the harness has counted the rows in your table",
            source="tool_result",
            subject="rows",
            comparator="exists",
        ),
        risks=(
            Risk(
                what="the scan stops at the row cap and returns a lower bound",
                what_we_do=(
                    "a capped scan reports `rows_are_truncated` and the stamp does "
                    "not happen - `profile_dataset` only measures when the scan "
                    "reached the end, because a lower bound is not a count. The "
                    "exit criterion below reads the ledger and not the tool, so a "
                    "truncated run fails this build instead of passing it"
                ),
            ),
        ),
    )

    return Build(
        id="count_the_rows",
        title="Count the rows in your table",
        for_outcome=situation.outcome,
        because=(
            "The diagnosis stopped because nothing here knows how big your table "
            "is, and that single number chooses between four different honest "
            "answers. Nothing needs to be decided by you first - the file is on "
            "this machine and the harness can read it."
        ),
        steps=(count,),
        environment=_sandbox("count_the_rows", path),
        exit_criterion=ExitCriterion(
            stated=(
                "the row count is in the ledger as a measurement the harness took "
                "off your file, and the tree has a branch to take"
            ),
            source="diagnosis",
            subject="fact_origins.tabular_rows",
            comparator="equals",
            value=diagnosis.MEASURED,
        ),
        facts=dict(situation.origins),
    )


def _propose_name_the_modality(situation: Situation) -> Build:
    """`ACTION__NAME_THE_MODALITY` - look first, then ask what only you can say.

    This is the shape `docs/PRODUCT_SPEC.md` 6.4 argues for and the reason
    `Build` carries questions at all. `modality` is not something any tool in
    this harness stamps, so the last move is the person's - but the two steps
    before it mean they are answering while looking at their own data rather
    than from memory. Asking a good question and waiting is also doing the
    thing; asking it blind is not.
    """
    path = situation.require_path("dataset_path")
    choices = list((situation.spec.facts.get("modality") or {}).get("enum") or ())
    if not choices:  # pragma: no cover - the ledger stopped declaring the enum
        raise NotEnoughToPropose(
            "The fact ledger no longer declares what the modality choices are, so "
            "this proposer cannot ask the question without inventing the options."
        )

    look = Step(
        id="look",
        tool="preview_dataset_rows",
        why="Show you actual rows of your own file, so the answer is read rather than remembered.",
        arguments={"path": path, "limit": 5},
        produces=(Output("rows", "array", "the first rows, as they are", at="rows"),),
        cost=_local_cost(
            "preview_dataset_rows",
            find_out_by="it reads a handful of rows; time one preview and it is known",
        ),
        exit_criterion=ExitCriterion(
            stated="rows from the file are on screen",
            source="tool_result",
            subject="rows",
            comparator="exists",
        ),
    )
    profile = Step(
        id="profile",
        tool="profile_dataset",
        why=(
            "Report what is in the file - format, columns, what kind of dataset it "
            "looks like - so the choice below is made against the shape of the "
            "data and not its filename."
        ),
        arguments={"path": path},
        produces=(
            Output("format", "string", "the format the harness read it as", at="format"),
        ),
        needs=("look",),
        cost=_local_cost(
            "profile_dataset",
            find_out_by=(
                "profiling scans rows; run it once on this file and the time is "
                "known for this size"
            ),
        ),
        exit_criterion=ExitCriterion(
            stated="the harness can say what format the file is and what columns it has",
            source="tool_result",
            subject="format",
            comparator="exists",
        ),
        risks=(
            Risk(
                what="the file is in a format no reader here can open",
                what_we_do=(
                    "the step says which format it looks like and that no reader "
                    "ships for it; the question below is then the only route and "
                    "the plan says so rather than pretending the profile worked"
                ),
            ),
        ),
    )

    return Build(
        id="name_the_modality",
        title="Look at the data, then tell me what kind of data it is",
        for_outcome=situation.outcome,
        because=(
            "The diagnosis stopped at the first fork in the tree. Which kind of "
            "data this is decides which of eight branches you are even on - the "
            "tabular answer and the text answer share almost nothing - and nothing "
            "in this harness can read it off a file."
        ),
        steps=(look, profile),
        environment=_sandbox("name_the_modality", path),
        exit_criterion=ExitCriterion(
            stated=(
                "you have said which kind of data this is, in your own person, and "
                "the tree has a fork to take"
            ),
            source="diagnosis",
            subject="fact_origins.modality",
            comparator="equals",
            value=diagnosis.STATED,
        ),
        questions=(
            Question(
                ask=(
                    "Which of these describes your data: "
                    + ", ".join(choices)
                    + "?"
                ),
                why=(
                    "It is the first fork in the tree and everything below it "
                    "follows. No tool in this harness measures it, which is why "
                    "this is a question and not a step."
                ),
                fact="modality",
            ),
        ),
        facts=dict(situation.origins),
    )


def _propose_substantiate(situation: Situation) -> Build:
    """`ACTION__SUBSTANTIATE_CLAIMED_FACTS` - go and check what was claimed.

    The most derived proposer here and the least hardcoded: it reads
    `result.unsubstantiated`, asks `evidence.resolves()` which tool settles each
    fact, and builds a step per tool. Nothing in this function knows the name of
    a fact, so a fact added to the ledger next year with a tool that measures it
    is covered on the day that tool is registered.

    A fact whose answer is the person's - `resolves` sends those to
    `state_facts`, which `app/build.py` refuses as a step for good reason -
    becomes a question instead of being dropped.
    """
    rows = list(situation.result.unsubstantiated or ())
    if not rows:  # pragma: no cover - the outcome is only reached with rows
        raise NotEnoughToPropose(
            "Nothing was challenged, so there is nothing to substantiate."
        )

    steps: list[Step] = []
    questions: list[Question] = []
    planned: dict[str, str] = {}
    unreachable: list[str] = []

    for row in rows:
        fact = str(row.get("fact") or "")
        # THE ONE PLACE THE TWO LEDGERS ACTUALLY MEET, AND IT WAS THE MOST
        # INVISIBLE COUPLING IN THE FILE. `ACTION__SUBSTANTIATE_CLAIMED_FACTS`
        # is declared by BOTH shipped ledgers - the only outcome name they share
        # - so this proposer is the only one an AI-engineering thread can reach.
        # It then asked `evidence.resolves(fact)` with no ledger, which read the
        # ML file, which declares none of that domain's sixteen facts, so every
        # row came back unreachable and the build was refused with a sentence
        # about a gap in the product. The most domain-general function in this
        # module was the one silently pinned to one domain.
        route = evidence.resolves(fact, situation.spec)
        tool_name = route.get("tool")
        if not tool_name:
            unreachable.append(fact)
            continue
        if tool_name in build.PERSON_ONLY_TOOLS:
            questions.append(
                Question(
                    ask=(
                        f"Say for yourself whether {fact} is what you told me. "
                        f"{route.get('substantiation') or ''}".strip()
                    ),
                    why=(
                        "A gate opened on this would be opened on a model agreeing "
                        "with you, and that is worth nothing. Said in your own "
                        "person it is worth what the ledger says it is worth."
                    ),
                    fact=fact,
                )
            )
            continue
        if tool_name in planned:
            continue
        try:
            arguments = _arguments_for(tool_name, situation)
        except NotEnoughToPropose as gap:
            raise NotEnoughToPropose(
                f"To substantiate {fact!r} I would run {tool_name}, and "
                f"{gap.detail}",
                needs=gap.needs,
            ) from gap
        planned[tool_name] = fact
        # WHAT THIS STEP WILL RUN ON, taken from the arguments it will actually
        # be called with rather than from anything else - so a cost derived from
        # a measurement is checked against the call and not against a second
        # account of the call. A tool with no path argument gets no subject, and
        # a subjectless target makes a measured cost UNKNOWN rather than wrong.
        runs_on, unidentified = _subject_of_a_call(tool_name, arguments)
        steps.append(
            Step(
                id=f"settle_{fact}"[:48],
                tool=tool_name,
                why=(
                    f"You told me {fact}. Nothing in this run measured it, and a "
                    "gate opened on a claim is a gate that means nothing, so the "
                    f"harness goes and {route.get('verb') or 'checks it'}."
                ),
                arguments=arguments,
                produces=(),
                cost=(
                    _baseline_cost(situation, runs_on, unidentified=unidentified)
                    if _reaches_the_model(tool_name)
                    else _local_cost(
                        tool_name,
                        find_out_by=(
                            f"run {tool_name} once and its result carries how long "
                            "it took on data this size"
                        ),
                    )
                ),
                exit_criterion=ExitCriterion(
                    stated=f"{tool_name} ran and stamped {fact} from a reading",
                    source="tool_result",
                    subject="ok",
                    comparator="is_true",
                ),
                operates_on=runs_on,
            )
        )

    if not steps:
        raise NotEnoughToPropose(
            "Everything challenged here is something only you can answer, or "
            "something no tool in this harness can measure yet"
            + (f" ({', '.join(unreachable)})" if unreachable else "")
            + ". There is no build that would be honest - the next move is yours.",
            needs=tuple(unreachable) or ("your own answer",),
        )

    first_fact = planned[steps[0].tool]
    steps.append(
        _recheck_step(
            tuple(step.id for step in steps),
            first_fact,
            why=(
                "Walk the tree again on what was actually measured. Whether the "
                "gates open is the engine's to decide."
            ),
        )
    )

    touches_the_model = any(_reaches_the_model(step.tool) for step in steps)
    known_paths = [p for p in (situation.eval_path, situation.dataset_path) if p]
    environment = _sandbox(
        "substantiate",
        *known_paths,
        reason=(
            (
                "one of these checks scores your connected model, which sends rows "
                "of your data to it"
            )
            if touches_the_model
            else ""
        ),
    )

    return Build(
        id="substantiate_claims",
        title="Go and check the things you told me",
        for_outcome=situation.outcome,
        because=(
            "The run was not refused. It was stopped at facts nobody can vouch "
            "for: "
            + ", ".join(sorted(planned.values()))
            + ". Each one has a tool that would settle it, and this runs them."
        ),
        steps=tuple(steps),
        environment=environment,
        exit_criterion=ExitCriterion(
            stated=(
                f"{first_fact} carries origin MEASURED - read by the harness rather "
                "than claimed - and the tree is walked again on the readings"
            ),
            source="diagnosis",
            subject=f"fact_origins.{first_fact}",
            comparator="is_measured",
        ),
        questions=tuple(questions),
        risks=(
            Risk(
                what="a measurement disagrees with what was claimed",
                what_we_do=(
                    "the measured value is what the engine reads, and the verdict "
                    "may change. That is the point of measuring rather than asking"
                ),
            ),
        ),
        facts=dict(situation.origins),
    )


def _require_the_two_columns(situation: Situation) -> tuple[str, str]:
    """The input column and the answer column, or a refusal that names them.

    Both proposers below need them for the reason `measure_baseline` does: a
    tool that grades rows has to be told which field is the question and which
    is the right answer, and guessing either turns a scored eval into a scored
    accident.
    """
    input_field = str(situation.input_field or "").strip()
    expected_field = str(situation.expected_field or "").strip()
    missing = [
        name
        for name, value in (
            ("input_field", input_field),
            ("expected_field", expected_field),
        )
        if not value
    ]
    if missing:
        raise NotEnoughToPropose(
            "I cannot plan an eval run without knowing which column holds the "
            f"input and which holds the answer that would be right. Missing: "
            f"{missing}. Run preview_dataset_rows on the file and the column "
            "names are in the result.",
            needs=tuple(missing),
        )
    return input_field, expected_field


def _grading_call(situation: Situation, path: str, *, sample: int) -> dict[str, Any]:
    """The arguments a `run_eval` step passes, and nothing it does not need.

    NO `prompt` ARGUMENT, DELIBERATELY. `run_eval` reads an absent prompt as
    *the baseline* - `prompt_is_default` is what decides whether a run may stamp
    `baseline_score` at all - so the one build that calls this wants the default
    and must not pass one. Scoring a prompt somebody wrote is the prompt bench's
    job and goes through `try_prompt`, which keeps the version, the parent and
    the comparison that make *better* mean anything.
    """
    input_field, expected_field = _require_the_two_columns(situation)
    return {
        "eval_path": path,
        "input_field": input_field,
        "expected_field": expected_field,
        "sample": sample,
    }


def _eval_outputs() -> tuple[Output, ...]:
    """What a `run_eval` step produces.

    `run_id` is the load-bearing one: `read_eval_results` consumes it through a
    `Ref`, so a name that drifted here would fail validation rather than fail
    quietly.
    """
    return (
        Output(
            "run_id",
            "integer",
            "the stored run, so a later step can read or compare it",
            at="run_id",
        ),
        Output("score", "number", "what the model scored on the graded rows", at="score"),
        Output("graded", "integer", "how many rows were actually graded", at="graded"),
        Output(
            "resolution",
            "object",
            "the smallest difference this many rows can tell apart",
            at="resolution",
        ),
    )


def _counting_step_if_needed(
    situation: Situation, path: str, cost: Cost
) -> tuple[list[Step], tuple[str, ...]]:
    """Count first when the request count could not be derived.

    Exactly what `_propose_measure_the_baseline` does, and for its reason: the
    estimate's own `find_out_by` then describes a step that is really in the
    plan rather than advice about one that is not.
    """
    if cost.model_requests.known:
        return [], ()
    counting = {"path": path, "finish_the_count": True}
    return (
        [
            Step(
                id="count",
                tool="measure_eval_set",
                why=(
                    "Count the eval set before grading against it, so the score "
                    "has a denominator the harness read itself - and so this "
                    "build can say how many requests the grading steps make."
                ),
                arguments=counting,
                produces=(Output("rows", "integer", "the counted rows", at="rows"),),
                cost=_local_cost(
                    "measure_eval_set",
                    find_out_by=(
                        "the result carries the seconds the count took; run it "
                        "once and the rate is known for this machine"
                    ),
                ),
                exit_criterion=ExitCriterion(
                    stated="the rows are counted to the end of the file",
                    source="tool_result",
                    subject="exact",
                    comparator="is_true",
                ),
                operates_on=_subject_of_a_call("measure_eval_set", counting)[0],
            )
        ],
        ("count",),
    )


#: Why an environment that grades rows has to declare egress, in the sentence
#: the person reads before approving it.
_SENDS_YOUR_ROWS = (
    "grading sends rows of your eval set to the model you connected. If that "
    "model runs on this machine nothing leaves it; if it is a hosted API, these "
    "rows do, and that is why this is declared here where you can see it before "
    "you say yes"
)

_THE_MODEL_IS_NOT_HERE = Risk(
    what=(
        "the connected model is not on this machine, so grading would send your "
        "rows off it"
    ),
    what_we_do=(
        "run_eval refuses to run against a remote endpoint on a model's say-so "
        "and stops to ask you to start it yourself. That refusal is in "
        "app/tools/evals.py and is not something this plan can wave through"
    ),
)

_A_RUN_THAT_STOPS = Risk(
    what="the run is interrupted part way through",
    what_we_do=(
        "every graded row is already on disk and nothing at all is stamped - a "
        "score from a run that fell over is not a score. Running the step again "
        "with the same arguments continues from where it stopped rather than "
        "starting over or billing you twice"
    ),
)


def _propose_classify_the_failures(situation: Situation) -> Build:
    """`ACTION__CLASSIFY_FAILURES` - the outcome the eval bench was built to move.

    THIS OUTCOME'S REASON WAS TRUE UNTIL `app/tools/evals.py` LANDED, AND IS NOT
    TRUE NOW. `failure_histogram` is declared `source: derive` in
    `docs/diagnosis_engine.yaml`, `derive` admits MEASURED and nothing else, and
    until `run_eval` registered `measures=("failure_histogram", ...)` no tool in
    this harness could produce one. Stage 1 therefore terminated here for
    everybody, always, and the eight routes below `S1_ROUTE_BY_FAILURE_MODE`
    were unreachable. One tool changed that; this proposer is the other half of
    the change, because the engine saying *bucket at least 20 failures* is worth
    nothing until there is a step that buckets them.

    **WHY THIS IS NOT THE `ACTION__COUNT_THE_ROWS` TRAP.** That outcome stays
    uncovered because NO tool measures `tabular_rows`, so a build for it would
    run, look successful, re-enter the tree and land on the same outcome having
    moved nothing - by construction, on every input, for every user. Here the
    blocking fact is genuinely measured by the step this build runs, so the
    build CAN move the outcome. Whether it does on a particular file depends on
    how many rows fail, which is a property of the person's data rather than of
    the plan, and it is carried as a risk that says so and says what to do next.
    """
    path = situation.require_path("eval_path")
    sample = _eval_sample(situation)
    grading = _grading_call(situation, path, sample=sample)

    target, unidentified = _subject_of_a_call("run_eval", grading)
    cost = _eval_cost(situation, target, sample=sample, unidentified=unidentified)
    steps, needs = _counting_step_if_needed(situation, path, cost)

    steps.append(
        Step(
            id="run",
            tool="run_eval",
            why=(
                "Run your eval set, keep the result of every row, and sort the "
                "failures into the engine's own buckets by rules you can check "
                "by eye. The diagnosis is stuck because nothing knows WHAT is "
                "going wrong - only that something is - and which bucket "
                "dominates decides which of eight branches you are on."
            ),
            arguments=grading,
            produces=_eval_outputs(),
            needs=needs,
            cost=cost,
            operates_on=target,
            exit_criterion=ExitCriterion(
                stated=(
                    "every chosen row is graded and on disk, and the failures are "
                    "bucketed by rule"
                ),
                source="tool_result",
                subject="ok",
                comparator="is_true",
            ),
            risks=(
                _THE_MODEL_IS_NOT_HERE,
                _A_RUN_THAT_STOPS,
                Risk(
                    what=(
                        "fewer than 20 rows fail, so the histogram is real and too "
                        "small to route on - S1_GAP_UNDIAGNOSED asks for at least 20"
                    ),
                    what_we_do=(
                        "the step reports how many rows it graded and how many it "
                        "bucketed, so a second call raises the sample against a "
                        "number rather than a guess. This plan does not pick a "
                        "sample that would guarantee 20 failures, because that "
                        "means assuming a failure rate, and the assumed rate would "
                        "be spent as your tokens"
                    ),
                ),
                Risk(
                    what="the failures are ones no rule here can name",
                    what_we_do=(
                        "they are counted as unclassified and left out rather than "
                        "guessed at, and if that is all of them the step stamps "
                        "nothing and says so. A bucket guessed at would route your "
                        "whole diagnosis"
                    ),
                ),
            ),
        )
    )

    steps.append(
        Step(
            id="read",
            tool="read_eval_results",
            why=(
                "Put the buckets and the rows behind them in front of you. The "
                "histogram is what the engine routes on, and a routing decision "
                "whose evidence you cannot see is one you cannot disagree with."
            ),
            arguments={"run_id": Ref("run", "run_id"), "failures": 20},
            produces=(
                Output(
                    "failure_histogram",
                    "object",
                    "how the failing rows bucketed",
                    at="failure_histogram",
                ),
                Output(
                    "failures",
                    "array",
                    "the failing rows, with what was expected and what came back",
                    at="failures",
                ),
            ),
            needs=("run",),
            cost=_local_cost(
                "read_eval_results",
                find_out_by=(
                    "it reads rows this harness already wrote and asks your model "
                    "nothing; time one read and it is timed for every build"
                ),
            ),
            exit_criterion=ExitCriterion(
                stated="the stored run reads back with its buckets and its failing rows",
                source="tool_result",
                subject="ok",
                comparator="is_true",
            ),
        )
    )

    steps.append(
        _recheck_step(
            ("read",),
            "failure_histogram",
            why=(
                "Walk the tree again now that the failures are bucketed. Which "
                "bucket dominates is what decides the branch, and only the engine "
                "decides that."
            ),
        )
    )

    return Build(
        id="classify_the_failures",
        title="Find out what is actually going wrong, before choosing a fix",
        for_outcome=situation.outcome,
        because=(
            "The diagnosis stopped at S1_GAP_UNDIAGNOSED: something is failing "
            "and nothing here knows what kind of failing it is. Wrong facts, "
            "wrong shape, wrong style and too slow are four different problems "
            "with four different cheapest fixes, and one fine-tune cannot fix "
            "four different problems."
        ),
        steps=tuple(steps),
        environment=_sandbox("classify_the_failures", path, reason=_SENDS_YOUR_ROWS),
        exit_criterion=ExitCriterion(
            stated=(
                "failure_histogram is MEASURED - buckets this harness produced "
                "from rows it graded itself, not a shape somebody described"
            ),
            source="diagnosis",
            subject="fact_origins.failure_histogram",
            comparator="is_measured",
        ),
        risks=(
            Risk(
                what="the dominant bucket is not the one you expected",
                what_we_do=(
                    "that is the plan working. The build's job is to produce the "
                    "histogram, not a particular shape of it, and the engine "
                    "re-reads the tree on whatever comes back"
                ),
            ),
        ),
        facts=dict(situation.origins),
    )


#: WHICH FACT EACH PROMPT OUTCOME IS WAITING ON, and what the person has to say
#: for the tree to move. Both are `source: ask` in the ledger, which is why the
#: build below ends in a question rather than in `run_diagnosis`: no step here
#: can stamp them, and a re-check whose criterion could never be met is a step
#: that reports failure for doing its job.
_THE_PROMPT_OUTCOMES: dict[str, dict[str, str]] = {
    "NO_TRAIN__BETTER_PROMPT": {
        "fact": "prompt_iterations",
        "id": "try_a_better_prompt",
        "title": "Score the rewritten prompt against the one you have",
        "because": (
            "The diagnosis stopped at S5_BETTER_PROMPT: the failures are about "
            "how the model behaves, and the prompt has not been rewritten "
            "against them three times yet. A rewrite costs a few minutes and one "
            "eval run; the fine-tune below it costs a GPU, and G2 will not let a "
            "training branch open until this has been pushed as far as it goes."
        ),
        "ask": (
            "How many times have you now rewritten the system prompt against "
            "these failures? Count this attempt."
        ),
        "why": (
            "G2 asks whether the no-training version of this has been pushed as "
            "far as it goes, and it counts rewrites. Nothing in this harness "
            "watches you edit a prompt, so the count is yours to state - and the "
            "verdict above is what makes it worth stating rather than a number "
            "to inflate."
        ),
    },
    "NO_TRAIN__FEW_SHOT": {
        "fact": "fewshot_tried",
        "id": "try_few_shot",
        "title": "Put worked examples in the prompt, taken from what it got wrong",
        "because": (
            "The diagnosis stopped at S5_FEWSHOT_UNTRIED. Five to twenty "
            "exemplars in the prompt is the cheapest available predictor of "
            "whether a fine-tune would work at all: if examples in the prompt "
            "move nothing, five hundred in a LoRA usually will not either. It "
            "costs one eval run to find out, and G2 asks for it before any "
            "training branch opens."
        ),
        "ask": (
            "Have you now tried few-shot exemplars in the prompt, and are you "
            "satisfied this line of attack is done?"
        ),
        "why": (
            "G2 counts few-shot as one of the things that must be tried before a "
            "training branch opens. Nothing here watches you decide you are "
            "finished with it, so it is yours to state; the run above is what "
            "makes the answer worth anything."
        ),
    },
}


def _the_prompt_line(situation: Situation, path: str) -> str:
    """The name of the line of descent this attempt is added to.

    `try_prompt` compares every version against its LINE's current champion, so
    the name decides what this attempt is measured against. When the caller does
    not name one it is taken from the eval file, which is the one thing on the
    table that is already specific to this job - and the step says so in its
    `why`, because a person who does not know which line they are extending
    cannot tell whether "no evidence" was a fair test.
    """
    named = str(situation.prompt_line or "").strip()
    return named or Path(path).stem or "the prompt"


def _aim_at(situation: Situation) -> str:
    """The failure bucket to aim the change at, when one can be read off honestly.

    `try_prompt`'s `targets=` makes the reply say what happened to THAT bucket
    rather than only to the aggregate, which matters because an aggregate can be
    flat while a change fixes every format failure and breaks as many factual
    ones. The bucket to aim at is the one the engine routed on - the largest -
    and this reads it off the same histogram the engine read.

    Returns "" rather than guessing whenever it cannot be sure: no histogram, a
    histogram that is not a mapping, a tie for largest, a mode the bench cannot
    key a bucket on, or a mode this harness's own router does not know. Every
    one of those ends with the argument omitted, and an omitted `targets=` costs
    a sentence in the report rather than correctness.
    """
    histogram = situation.values.get("failure_histogram")
    if not isinstance(histogram, Mapping) or not histogram:
        return ""
    try:
        counts = {str(mode): int(count) for mode, count in histogram.items()}
    except (TypeError, ValueError):
        return ""
    if not counts:
        return ""
    top = max(counts.values())
    leaders = [mode for mode, count in counts.items() if count == top]
    if len(leaders) != 1:
        # A TIE IS NOT A TARGET. Picking either one would be this file deciding
        # what the change is aimed at, which is the person's call and the
        # engine's routing question, not a tiebreak worth inventing.
        return ""
    aim = leaders[0]
    if aim in prompts.NOT_A_ROW_LOCAL_MODE:
        return ""
    if aim not in set(evals.routable_modes()):
        return ""
    return aim


def _propose_try_a_prompt(situation: Situation) -> Build:
    """`NO_TRAIN__BETTER_PROMPT` and `NO_TRAIN__FEW_SHOT` - one `try_prompt` each.

    `docs/PRODUCT_SPEC.md` 6.5 marks both v1, and the reason recorded against
    all seven prompt outcomes until now said the opposite in as many words:
    *"it needs a stored prompt to change and an eval runner to score it before
    and after, and neither ships ... there is no run_eval."* Both ship. A false
    reason in `NOT_COVERED` is a written claim that this product cannot do
    something it can, which is worse than no proposer at all.

    **THE STEP IS `try_prompt` RATHER THAN `run_eval` TWICE**, and the
    difference is not convenience. `app/tools/prompts.py` makes a prompt a
    VERSION of something - a parent, a number, a note, the bucket it was aimed
    at - so *better* is a claim about a recorded pair rather than about whichever
    two runs somebody put side by side. It also computes `paired_delta` over the
    rows both runs actually graded, which is the correction few-shot needs and
    the plain eval bench does not make: `evals.compare`'s headline `delta`
    subtracts two aggregate scores, and the moment exemplars are held out of one
    side those two aggregates are measured over different sets of rows. A build
    that ran the eval twice itself would have to re-derive all of that, and the
    copy that drifted would still print a plausible number.

    **THE PROMPT IS THE PERSON'S FOR A REWRITE, AND IS NOT NEEDED AT ALL FOR
    FEW-SHOT.** `NO_TRAIN__BETTER_PROMPT` refuses without one, in the same shape
    as a missing path: a proposal whose central argument the harness invented is
    an experiment nobody chose, judged by a comparison it also chose.
    `NO_TRAIN__FEW_SHOT` is the opposite case and it is the tool's doing -
    `fewshot_from_failures` builds the examples out of the rows the current
    champion got WRONG and holds exactly those rows out of the score. The
    engine's instruction is *chosen from the eval failures, not from the
    successes*, and that is a thing the bench can do correctly and a person
    doing it by hand very easily gets backwards.
    """
    plan = _THE_PROMPT_OUTCOMES[situation.outcome]
    path = situation.require_path("eval_path")
    input_field, expected_field = _require_the_two_columns(situation)
    candidate = str(situation.prompt or "").strip()
    few_shot = situation.outcome == "NO_TRAIN__FEW_SHOT"

    if not candidate and not few_shot:
        raise NotEnoughToPropose(
            "I can plan the attempt and I will not write the prompt. Give me the "
            "system prompt you want to try and this build scores it on your eval "
            "set and compares it against the version it has to beat, pairwise, "
            "with the smallest difference those rows can resolve stated beside "
            "the answer. A prompt this harness drafted for you would be an "
            "experiment you did not choose, judged by a comparison you did not "
            "choose either.",
            needs=("prompt",),
        )

    sample = _eval_sample(situation)
    line = _the_prompt_line(situation, path)
    aim = _aim_at(situation)

    attempt: dict[str, Any] = {
        "line": line,
        "eval_path": path,
        "input_field": input_field,
        "expected_field": expected_field,
        "sample": sample,
    }
    if candidate:
        attempt["prompt"] = candidate
    if aim:
        attempt["targets"] = aim
    if few_shot:
        # THE COUNT IS THE TOOL'S OWN CEILING, not a number chosen here. The
        # engine asks for 5-20 exemplars and `prompts.MAX_EXEMPLARS` is 20, so
        # the top of the engine's range and the tool's maximum are the same
        # number - and `choose_exemplars` takes it as "up to this many", so a
        # line with fewer failures than that gets the failures it has rather
        # than a refusal.
        attempt["fewshot_from_failures"] = prompts.MAX_EXEMPLARS
        attempt["change_note"] = (
            f"up to {prompts.MAX_EXEMPLARS} worked examples built from the rows "
            "the current best prompt got wrong"
            + (f", drawn from the {aim} bucket" if aim else "")
        )
    else:
        attempt["change_note"] = (
            "a rewritten system prompt, supplied to propose_build and scored "
            "against the version it has to beat"
            + (f"; aimed at the {aim} failures" if aim else "")
        )

    target, unidentified = _subject_of_a_call("try_prompt", attempt)
    cost = _eval_cost(situation, target, sample=sample, unidentified=unidentified)
    steps, needs = _counting_step_if_needed(situation, path, cost)

    why = (
        (
            "Build the examples out of the rows your current best prompt got "
            "WRONG, add them to that prompt, and score the result on the same "
            "eval set. The exemplar rows are held out of the score, because "
            "grading a prompt on the very rows it was shown is a leak and it "
            "does not look like one from the outside - it looks like the prompt "
            "worked."
        )
        if few_shot
        else (
            "Score the prompt you supplied on your own eval set and compare it "
            "against the version it has to beat, row by row. Nothing here "
            "decides that it is better: the comparison is McNemar's exact test "
            "over the rows that changed, and it is allowed to come back saying "
            "this eval set cannot tell the two apart."
        )
    )

    steps.append(
        Step(
            id="attempt",
            tool="try_prompt",
            why=(
                why
                + f" The attempt is filed on the prompt line {line!r}"
                + (
                    ", which you named"
                    if str(situation.prompt_line or "").strip()
                    else ", a name taken from your eval file because you did not "
                    "give one - every comparison is against that line's current "
                    "champion, so it decides what this is measured against"
                )
                + "."
            ),
            arguments=attempt,
            produces=(
                Output(
                    "verdict",
                    "string",
                    "better, worse, no_evidence, or first - and no_evidence is a real answer",
                    at="verdict",
                ),
                Output(
                    "version",
                    "integer",
                    "which version of this prompt line the attempt became",
                    at="version",
                ),
                Output(
                    "run_id",
                    "integer",
                    "the eval run that scored it, so its rows can be read back",
                    at="run_id",
                ),
            ),
            needs=needs,
            cost=cost,
            operates_on=target,
            exit_criterion=ExitCriterion(
                stated=(
                    "the attempt is scored, stored as a numbered version, and "
                    "compared against the one it had to beat"
                ),
                source="tool_result",
                subject="ok",
                comparator="is_true",
            ),
            risks=(
                _THE_MODEL_IS_NOT_HERE,
                _A_RUN_THAT_STOPS,
                Risk(
                    what=(
                        "the eval set is too small to resolve the difference this "
                        "change actually makes"
                    ),
                    what_we_do=(
                        "the verdict is no_evidence, in those words, with the "
                        "number of extra rows that would settle it - never a small "
                        "win. A prompt change is cheap enough to make forty times "
                        "and anybody shown forty unresolvable deltas will believe "
                        "the tenth, which is why the rule is a CHECK constraint on "
                        "prompt_champions rather than a paragraph"
                    ),
                ),
                Risk(
                    what=(
                        f"the prompt line {line!r} has nothing scored on it yet"
                        + (
                            ", so there are no failures to draw examples from"
                            if few_shot
                            else ", so there is nothing to compare against"
                        )
                    ),
                    what_we_do=(
                        (
                            "the step refuses before it spends anything and says to "
                            "score a prompt on this line first - its failures are "
                            "the material this change is made of"
                        )
                        if few_shot
                        else (
                            "the verdict comes back 'first': the attempt is scored "
                            "and recorded as the thing to beat, which is a real "
                            "answer and is what the next attempt is measured "
                            "against"
                        )
                    ),
                ),
            ),
        )
    )

    return Build(
        id=plan["id"],
        title=plan["title"],
        for_outcome=situation.outcome,
        because=plan["because"],
        steps=tuple(steps),
        environment=_sandbox(plan["id"], path, reason=_SENDS_YOUR_ROWS),
        exit_criterion=ExitCriterion(
            stated=(
                "the attempt is scored against the version it had to beat and a "
                "verdict is on the table - including 'these two are "
                "indistinguishable on this eval set', which is an answer and not "
                "a failure"
            ),
            source="outputs",
            subject="attempt.verdict",
            comparator="exists",
        ),
        questions=(
            Question(ask=plan["ask"], why=plan["why"], fact=plan["fact"]),
        ),
        risks=(
            Risk(
                what="the change turns out to be no better, or worse",
                what_we_do=(
                    "that is the plan working, and it is worth more than a win: "
                    "the engine reads this lever as having been tried, and a "
                    "change that moves nothing on twenty worked examples is the "
                    "cheapest evidence available that a fine-tune would not move "
                    "it either"
                ),
            ),
            Risk(
                what=(
                    "the model behind the name changes between the version being "
                    "beaten and this one - a re-pulled tag, or an API model "
                    "updated server-side"
                ),
                what_we_do=(
                    "two variants scored by DIFFERENT connections are refused by "
                    "name rather than compared, because a prompt that scores "
                    "better because the connection changed underneath it is the "
                    "easiest way there is to believe a prompt change worked. A "
                    "re-pulled tag under one connection is not caught by that, "
                    "and app/tools/evals.py says so rather than implying otherwise"
                ),
            ),
        ),
        facts=dict(situation.origins),
    )


# ---------------------------------------------------------------------------
# The retrieval bench.
#
# THE DEAD END THIS CLOSES, MEASURED. `docs/THE_PROPOSAL_LOOP.md` says a
# no-train diagnosis has to produce a build for the thing we said instead. Of
# the fifteen `NO_TRAIN__*` outcomes, thirteen were dead ends and the two that
# were not were the prompt ones. `NO_TRAIN__RAG` is the largest of the thirteen:
# four separate nodes of stage 3 emit it, and until now the product's answer to
# every one of them was a sentence.
#
# AND THE ENGINE HAD ALREADY SPECIFIED THE MISSING PIECE IN FULL.
# `retriever_recall_at_k` is declared `source: inspect`, so only a tool may
# stamp it, and `ACTION__MEASURE_RETRIEVER_RECALL` tells a person to go and
# measure their retriever - which this harness then could not help them do.
# `app/tools/retrieval.py` is where the instrument lives; this is the half that
# turns it into a plan somebody can approve.
#
# WHAT THIS FILE OWNS AND WHAT IT DOES NOT. The three tool NAMES below are fixed
# across two lanes so the plan and the instrument cannot disagree about what to
# call anything. Their ARGUMENT names are the tools' own business, and this file
# does not get a second opinion about them: `_a_call_that_fits` asks the
# registered schema what it takes, passes what fits, and REFUSES when something
# the tool requires is not a thing this situation can supply. A cross-lane
# disagreement therefore reaches the person as a refusal that names the
# argument, never as a plan that would be rejected at execution time after they
# approved it.

#: THE THREE TOOL NAMES, FIXED SO THE TWO LANES CANNOT DISAGREE.
THE_RETRIEVAL_TOOLS: tuple[str, ...] = (
    "build_retrieval_index",
    "search_the_index",
    "measure_retriever_recall",
)


def retrieval_tools_missing() -> tuple[str, ...]:
    """Which of the three are not registered in this process, right now.

    Read off the live registry every time rather than answered once at import,
    because the answer changes the day `app/tools/retrieval.py` lands and
    nothing in this file should have to be edited on that day. It is also what
    keeps `COVERAGE` and `NOT_COVERED` from stating the opposite of the truth
    for however long it takes somebody to notice - see `_RETRIEVAL_NOT_HERE_YET`.
    """
    return tuple(name for name in THE_RETRIEVAL_TOOLS if REGISTRY.get(name) is None)


def the_retrieval_bench_is_registered() -> bool:
    return not retrieval_tools_missing()


def engine_node_says(
    node: str, field_name: str, spec: diagnosis.Spec | None = None
) -> str:
    """One field of one node, verbatim, or "" when the node does not state it.

    THE GENERAL FORM OF `engine_exit_criterion`, AND IT IS NOT A TIDY-UP. A
    proposer for a node that declares NO exit criterion has to quote the node's
    `condition` and `action` instead - that is what "either derive one and say
    what from, or say plainly that the engine declared none" turns into in code
    - and quoting them means reading them from `docs/diagnosis_engine.yaml`
    rather than typing them here. The empty string is a real answer and every
    caller has to treat it as one: it means the node does not state this, which
    for `exit_criterion` is the whole difficulty of `NO_TRAIN__FIX_RETRIEVAL`.
    """
    current = spec or diagnosis.default_spec()
    row = current.node_index.get(str(node or "")) or {}
    return str(row.get(str(field_name)) or "").strip()


def engine_exit_criterion(node: str, spec: diagnosis.Spec | None = None) -> str:
    """The `exit_criterion:` a node declares, verbatim, or "" when it declares none.

    Read rather than typed, for the reason `g0_minimum` is read rather than
    typed: the criterion is the engine's promise and it lives in
    `docs/diagnosis_engine.yaml`. A copy of it here is a second sentence that can
    drift from the first one silently, and the drift would be invisible
    precisely because both sentences would read well.
    """
    return engine_node_says(node, "exit_criterion", spec)


#: The node whose exit criterion the RAG outcome is held to. Four nodes emit
#: `NO_TRAIN__RAG` and only this one states a criterion; the engine's own
#: `S3_RECALL_UNMEASURED` calls it "the bar S3_BUILD_RAG already sets", so which
#: node speaks for the outcome is the file's answer rather than this module's
#: preference.
_THE_RAG_CRITERION_NODE = "S3_BUILD_RAG"

_THE_RECALL_BAR = re.compile(r"retriever_recall_at_k\s*>=\s*([0-9]*\.?[0-9]+)")


def recall_bar(spec: diagnosis.Spec | None = None) -> float:
    """The recall `S3_BUILD_RAG` asks for, read off the spec rather than typed."""
    stated = engine_exit_criterion(_THE_RAG_CRITERION_NODE, spec)
    match = _THE_RECALL_BAR.search(stated)
    if not match:  # pragma: no cover - the spec changed shape
        raise NotEnoughToPropose(
            f"{_THE_RAG_CRITERION_NODE} no longer states its bar as "
            "`retriever_recall_at_k >= N`, so this proposer cannot read it. "
            "Nothing is planned against a threshold this file guessed."
        )
    return float(match.group(1))


#: `Default 1200.` in the sentence `build_retrieval_index` shows a person about
#: its own `passage_chars`. A parser over prose, which is not a thing to be
#: pleased about - see `subject_of_a_recorded_measurement` for the other one -
#: and it is safe for the same reason: it decides whether a SENTENCE is printed,
#: never a number this file plans against, so a reworded schema drops the clause
#: instead of inventing a default.
_THE_STATED_DEFAULT = re.compile(r"Default\s+(\d+)")


def _what_the_index_calls_its_default() -> str:
    """The default passage size, read out of the schema the person is shown.

    Empty when `build_retrieval_index` is not registered here or has reworded
    its own description, because the alternative is a number remembered from
    somewhere else - and the clause this fills is worth having only while it is
    read off the same text the person can read.
    """
    spec = REGISTRY.get("build_retrieval_index")
    if spec is None:
        return ""
    said = str(
        ((spec.schema.get("properties") or {}).get("passage_chars") or {}).get(
            "description"
        )
        or ""
    )
    found = _THE_STATED_DEFAULT.search(said)
    if not found:
        return ""
    return (
        f" The index's own default is {found.group(1)} characters, and its "
        "schema calls that a stated choice rather than a measured optimum, "
        "which is the whole reason there is anything here to measure."
    )


def _a_call_that_fits(
    tool_name: str, offered: Mapping[str, Any], *, must_carry: tuple[str, ...] = ()
) -> dict[str, Any]:
    """The arguments this tool actually declares, out of the ones we can supply.

    THE CROSS-LANE CONTRACT, MADE MECHANICAL. The tool names are fixed; the
    argument names are the tool's own, and this file will not hold a private
    table of them - that is the closed list `_subject_of_a_call` deleted, put
    back in a new place. So the offer is generous and the schema decides: an
    argument the tool does not declare is dropped rather than passed, and an
    argument the tool REQUIRES that nothing here can name is a refusal.

    `must_carry` is the other direction and it is the one that matters. Dropping
    an argument the tool never heard of is harmless; dropping the one that says
    which corpus to index is a step that would run on nothing and report
    success. So a name in `must_carry` that does not survive into the call stops
    the plan and says which tool and which argument, which is a sentence
    somebody can act on rather than a build that quietly indexes the void.
    """
    spec = _spec(tool_name)
    properties = set((spec.schema.get("properties") or {}).keys())
    required = set(spec.schema.get("required") or ())
    call = {key: value for key, value in offered.items() if key in properties}

    dropped = sorted(name for name in must_carry if name not in call)
    if dropped:
        raise NotEnoughToPropose(
            f"This plan would pass {dropped} to {tool_name}, and {tool_name} "
            f"declares no such argument - it takes {sorted(properties)}. That is "
            "the two halves of this bench disagreeing about what to call things, "
            "and the honest answer is to stop rather than to draw a step that "
            "would run on nothing and report success.",
            needs=tuple(f"{tool_name}.{name}" for name in dropped),
        )
    missing = sorted(required - set(call))
    if missing:
        raise NotEnoughToPropose(
            f"{tool_name} requires {missing} and nothing in this situation can "
            "supply it, so no step is written for it. A call the tool would "
            "refuse is a call refused after somebody approved the plan.",
            needs=tuple(f"{tool_name}.{name}" for name in missing),
        )
    return call


def _at_least_one_of(
    call: Mapping[str, Any], tool_name: str, names: tuple[str, ...], *, what: str
) -> str:
    """One of these spellings survived into the call, or a refusal naming all of them.

    THE OTHER HALF OF `must_carry`, AND IT EXISTS BECAUSE OF SYNONYMS. `must_carry`
    is an AND - every name in it has to survive - which is right when the plan
    knows the argument's name and wrong the moment the same thing has two
    spellings in this repository. A corpus is `path` to `build_retrieval_index`
    and `corpus_path` to a `Situation`, so a plan that offered only one of them
    would refuse over a synonym, and a plan that `must_carry`-ed both could never
    pass. Offering both and requiring one is the honest shape: the tool's schema
    picks, and a tool that declares NEITHER stops the plan with a sentence naming
    every spelling that was tried, which is something a person in the other lane
    can act on.
    """
    survived = [name for name in names if name in call]
    if not survived:
        raise NotEnoughToPropose(
            f"Nothing in this plan can tell {tool_name} {what}. It was offered "
            f"under {list(names)} and its schema declares none of them - it "
            f"takes {sorted((_spec(tool_name).schema.get('properties') or {}).keys())}. "
            "That is the two halves of this bench disagreeing about what to call "
            "things, and the honest answer is to stop rather than to draw a step "
            "that would run on whatever was lying around.",
            needs=tuple(f"{tool_name}.{name}" for name in names),
        )
    return survived[0]


#: The store `app/tools/retrieval.py` declares for the index it writes, and the
#: one word that separates "rows in the harness database" from "however many
#: bytes this person's documents turn into". Read from the tool's own `writes`.
_THE_INDEX_STORE = "retrieval"


def _retrieval_disk(name: str) -> Estimate:
    """What an index costs on disk: unknown, because nobody has built one here.

    NOT `_disk_cost` FOR THE TOOL THAT WRITES AN INDEX, and `_disk_cost` for
    every other one. That function is right about the tools it was written for
    and says so in as many words - *rows in the harness database, no files* -
    and an index is the first thing this product writes whose size is a function
    of how much text somebody has. Reusing its sentence for the indexer would
    put a true-sounding claim into every retrieval proposal; reusing THIS
    sentence for `measure_retriever_recall`, which writes one fact row, would do
    the same thing in the other direction. Both are the invented-number defect
    wearing prose, so which sentence applies is read off the tool's `writes`.
    """
    written = _writes_to_disk(name)
    if not written:
        return Estimate.none(
            build.DISK,
            because=(
                f"{name} declares writes=(), so it creates no file and adds "
                "nothing to disk"
            ),
        )
    if _THE_INDEX_STORE not in written:
        return _disk_cost(name)
    return Estimate.unknown(
        build.DISK,
        why=(
            f"{name} declares writes={list(written)}, and no retrieval index has "
            "ever been built on this machine - there is no run of it recorded "
            "anywhere in this harness, so how many bytes your documents turn into "
            "is not derivable from anything measured. A number here would be one "
            "somebody remembered about some other corpus"
        ),
        find_out_by=(
            "build the index over a slice of the corpus first and compare the size "
            "of the working directory and of the harness database before and "
            "after; that is a measurement of YOUR documents rather than of an "
            "average one"
        ),
    )


def _retrieval_cost(name: str, *, find_out_by: str) -> Cost:
    """One retrieval step's cost, derived from what the tool declared about itself.

    TWO BRANCHES BECAUSE THE ANSWER GENUINELY HAS TWO SHAPES, and which one
    applies is the tool's to say rather than this file's to assume. A BM25 index
    is a token count over text on this machine and sends nothing anywhere: that
    is provable from `reads` not containing `providers`, and it is the whole
    reason a local index can be costed at zero tokens instead of at unknown. An
    embedding retriever goes through the user's own connected model, and then the
    token and request counts are UNKNOWN here - how many calls a retrieval tool
    makes per document is a property of its chunking, which this file cannot read
    and will not guess at.
    """
    if not _reaches_the_model(name):
        tokens, requests = _model_cost_of_a_local_tool(name)
        return Cost(
            model_tokens=tokens,
            model_requests=requests,
            wall_clock=_wall_clock(name, find_out_by=find_out_by),
            disk=_retrieval_disk(name),
        )
    reaches = (
        f"{name} declares reads={list(_spec(name).reads)}, which includes "
        "`providers`, so it sends your text to the model you connected"
    )
    return Cost(
        model_tokens=Estimate.unknown(
            build.MODEL_TOKENS,
            why=(
                f"{reaches} - and turning documents into tokens needs your model's "
                "tokenizer and the length of your documents, neither of which is "
                "readable at proposal time. Characters times a remembered constant "
                "is the number this product refuses to invent"
            ),
            find_out_by=(
                "run this step over a small slice of the corpus and read the token "
                "usage your provider reports back"
            ),
        ),
        model_requests=Estimate.unknown(
            build.MODEL_REQUESTS,
            why=(
                f"{reaches}, and how many calls that is depends on how the tool "
                "chunks your documents and how many it batches per call. Both are "
                "properties of that tool rather than of this plan, and nothing "
                "here has measured either"
            ),
            find_out_by=(
                "run it over a slice of the corpus and read the request count "
                "back; the whole corpus is that per document"
            ),
        ),
        wall_clock=_wall_clock(name, find_out_by=find_out_by),
        disk=_retrieval_disk(name),
    )


def _egress_for(tools: list[str]) -> str:
    """Why this sandbox may reach the network, or "" - and the "" is a claim.

    A LOCAL INDEX IS LOCAL, and this is where that stops being a slogan. The
    reason is derived from what the steps' own tools declare in `reads`, so an
    environment with egress off is one in which `Build.validate` has checked
    every step against `NETWORK_READS` and found none. If the retrieval tools are
    local, the plan can say the corpus never leaves the machine and be checked on
    it; the day one of them reads `providers`, this turns the egress on and
    writes the sentence, rather than the build failing validation or - far worse
    - the claim staying in the prose.
    """
    reaching = sorted(
        {read for name in tools for read in set(_spec(name).reads) & build.NETWORK_READS}
    )
    if not reaching:
        return ""
    return (
        "a step in this plan declares reads="
        + repr(reaching)
        + ", so your documents and your eval rows go to the model you connected. "
        "If that model runs on this machine nothing leaves it; if it is a hosted "
        "API, this text does, and that is why it is declared here where you can "
        "see it before you say yes"
    )


def _the_eval_set_is_inside(evaluation: str, corpus: str) -> bool:
    """Would indexing `corpus` put the eval file into the index?

    A corpus is normally a FOLDER, so "the eval set is in the corpus" is the
    spelling of the circular measurement that a person reaches by accident and
    that does not look like anything from the two arguments: they are different
    strings, and one of them is a directory. Resolved on both sides so a relative
    path, a `..` and a symlink cannot walk around it.

    False on anything the filesystem will not answer, which is the safe direction
    here: this decides a REFUSAL, and refusing a plan because a path could not be
    resolved would stop work over a question nobody asked.
    """
    try:
        here = Path(evaluation).resolve(strict=False)
        there = Path(corpus).resolve(strict=False)
    except (OSError, ValueError):  # pragma: no cover - a path the OS refuses
        return False
    if not there.is_dir():
        return False
    return here.is_relative_to(there)


#: Suffixes for which ONE FILE IS ONE DOCUMENT. A `.csv` or `.jsonl` corpus is
#: one file and many documents - `build_retrieval_index` takes `text_field` for
#: exactly that case, one row per document - so a file count is not a document
#: count for them and the refusal below does not apply.
_ONE_FILE_IS_ONE_DOCUMENT: tuple[str, ...] = (".txt", ".md")


def _the_corpus_is_one_document(corpus: str) -> bool:
    """Is there exactly one document here? Only `True` when that is certain.

    ONE QUESTION, ASKED IN ONE DIRECTION. A chunking sweep over a corpus of one
    document is a guaranteed null - the eval set names the right DOCUMENT, there
    is only one, and every setting retrieves it - so this decides a refusal, and
    a refusal decided on a guess is worse than no refusal at all.

    So it is `True` only where the count is exact: one file, and a file for which
    one file is one document. Files the index's own reader skips can only make
    the true count SMALLER, so several files never prove several documents and
    are not treated as proving anything; a structured file is one row per
    document and is never counted as one. The walk stops at the second file
    because that is where the answer is settled, and a path the filesystem will
    not walk answers `False` - stopping a plan because a directory could not be
    listed would be a refusal about the OS wearing a refusal about the corpus.
    """
    root = Path(corpus)
    try:
        if root.is_file():
            return root.suffix.lower() in _ONE_FILE_IS_ONE_DOCUMENT
        found: list[Path] = []
        for candidate in root.rglob("*"):
            if candidate.is_file():
                found.append(candidate)
                if len(found) > 1:
                    return False
        return len(found) == 1 and found[0].suffix.lower() in _ONE_FILE_IS_ONE_DOCUMENT
    except (OSError, ValueError):  # pragma: no cover - a path the OS refuses
        return False


def _the_question_and_the_right_passage(situation: Situation) -> tuple[str, str]:
    """The column holding the question, and the one naming the right passage.

    NOT `_require_the_two_columns`, and the difference is what the second column
    means rather than a spelling. Recall@k asks, for each row, whether the
    passage that should have come back is among the top k the retriever fetched.
    So `expected_field` here is not the answer TEXT a grader compares against -
    it is what identifies the right DOCUMENT, and a person who supplies the
    answer column instead gets a number measuring something else.
    `measure_retriever_recall` has a separate `answer_field` for the answer text
    and is explicit that what it produces from it is weaker and different, so
    this proposer never passes one.

    ONLY THE FIRST IS REQUIRED, and that is the tool's call rather than this
    file's: `question_field` is in its `required` list and `ground_truth_field`
    is not, because it will pick a conventional column and say in its reply which
    one it used. Refusing to plan when the tool would have found the column is
    the product being strict at the person's expense; the step says which case it
    is in, and the tool's own refusal is carried as a risk.
    """
    question = str(situation.input_field or "").strip()
    if not question:
        raise NotEnoughToPropose(
            "Recall@k asks, for every row of your eval set, whether the passage "
            "that should have come back is among the top few the retriever "
            "fetched, so it needs the column holding the question. Run "
            "preview_dataset_rows on the eval file and the column names are in "
            "the result. If you also know which column names the right DOCUMENT, "
            "give it as expected_field - and note that it is the document, not "
            "the answer text: point it at the answer column and the number that "
            "comes back is measuring something else.",
            needs=("input_field",),
        )
    return question, str(situation.expected_field or "").strip()


#: WHAT EACH RETRIEVAL OUTCOME IS, in the words that belong to it. The two share
#: every step; what differs is which node's exit criterion the build is held to,
#: and - for the recall outcome - that the person already runs a retriever of
#: their own, which the build must not pretend to be measuring.
_THE_RETRIEVAL_OUTCOMES: dict[str, dict[str, str]] = {
    "NO_TRAIN__RAG": {
        "id": "build_the_index",
        "title": "Build the retrieval you were told to build, and measure whether it works",
        "node": _THE_RAG_CRITERION_NODE,
    },
    "ACTION__MEASURE_RETRIEVER_RECALL": {
        "id": "measure_the_retriever",
        "title": "Score a retriever on its own, before anybody blames the generator",
        "node": "S3_RECALL_UNMEASURED",
    },
}


def _propose_the_retrieval_bench(situation: Situation) -> Build:
    """`NO_TRAIN__RAG` and `ACTION__MEASURE_RETRIEVER_RECALL` - the dead end, closed.

    THE HEADLINE IS THE FIRST ONE. "Do not train anything" is the most valuable
    thing this product says and until now it was a sentence: the person was told
    their answer is retrieval and handed nothing. This build indexes the
    documents they point at, shows them what comes back for a question they
    chose, and measures - on their own eval set, with a number the harness took
    itself - whether the right passage is actually in the top few. That is an
    artifact and a measurement rather than advice, which is the whole of
    `docs/THE_PROPOSAL_LOOP.md`'s "an actual outcome, not an answer".

    **THE EXIT CRITERION IS THE ENGINE'S AND THIS BUILD REACHES HALF OF IT.**
    `S3_BUILD_RAG` says *retriever_recall_at_k >= 0.8 on the eval set AND
    end-to-end score >= target_score*. The first half is what this plan measures.
    The second half needs the retrieved passages put in front of the model and
    the answer graded, and nothing in this harness does retrieval-augmented
    generation - `run_eval` sends a system prompt and grades text, which is not
    the same tool wearing a different hat. So the criterion is stated as the
    engine wrote it, the half this build reaches is what the comparator checks,
    and the gap is said out loud in the plan rather than closed by quietly
    declaring a weaker criterion. A criterion whose sentence promises more than
    its comparator checks is the trap this module is built against, drawn in
    prose instead of in numbers.

    **AND THE NUMBER IS ABOUT THE INDEX THIS HARNESS BUILDS.** For
    `ACTION__MEASURE_RETRIEVER_RECALL` the person already has retrieval, and
    theirs is not the one being scored here. That is carried as the first risk
    and said in `because`, because a figure stamped `retriever_recall_at_k` that
    was taken off a different retriever is exactly the shape of the defect this
    file spent a milestone closing on eval-set row counts: a real measurement,
    completely derived, of something other than the thing the reader thinks. What
    it IS worth is a floor and a comparison - if a plain token-count retriever
    over the same corpus finds the passage and theirs does not, the corpus is
    fine and the retriever is the problem, which is the question
    `S3_RECALL_UNMEASURED` exists to settle.
    """
    plan = _THE_RETRIEVAL_OUTCOMES[situation.outcome]

    missing = retrieval_tools_missing()
    if missing:
        raise NotEnoughToPropose(
            "The retrieval bench is not in this harness yet: "
            f"{list(missing)} of {list(THE_RETRIEVAL_TOOLS)} are not registered "
            "tools. The plan for this outcome is written and it will not be drawn "
            "against tools that do not exist, because a step naming a tool nobody "
            "registered is a plan that fails after you approved it.",
            needs=tuple(missing),
        )

    corpus = situation.require_path("corpus_path")
    evaluation = situation.require_path("eval_path")
    question_field, passage_field = _the_question_and_the_right_passage(situation)
    bar = recall_bar(situation.spec)
    # 0 IS "NOBODY SAID", and it is read through the same coercion the tool
    # argument gets, so a `Situation` assembled by hand with a string or a
    # negative in it means the tool's own default rather than a crash or a k
    # this file chose.
    depth = max(0, _an_integer(situation.top_k))

    corpus_subject = Subject.of_path(corpus)
    eval_subject = Subject.of_path(evaluation)

    # REFUSAL: THE EVAL SET IS IN THE CORPUS. Indexing the file that holds the
    # right answers and then asking whether the right answers can be found is a
    # measurement of nothing, and it comes back high. It is the
    # `ACTION__COUNT_THE_ROWS` trap wearing a retrieval costume: the build would
    # run, look successful, stamp a number and route the whole diagnosis on it.
    #
    # BOTH SPELLINGS OF IT, because the second is the one somebody actually does:
    # `corpus_path` pointed at a folder that HAPPENS TO CONTAIN the eval file is
    # the same leak and does not look like one - the two arguments are different
    # strings, and a folder is exactly what a corpus normally is.
    inside = _the_eval_set_is_inside(evaluation, corpus)
    if corpus_subject.key == eval_subject.key or inside:
        raise NotEnoughToPropose(
            (
                f"Your corpus and your eval set are the same file "
                f"({corpus_subject.key})."
                if corpus_subject.key == eval_subject.key
                else f"Your eval set is inside the corpus you asked me to index: "
                f"{eval_subject.key} is under {corpus_subject.key}, so the index "
                "would contain the questions and their answers."
            )
            + " Indexing what holds the answers and then measuring whether the "
            "answers can be retrieved does not measure a retriever - it comes "
            "back near perfect whatever the retriever is, and this diagnosis "
            "would then be routed on it. Point corpus_path at the documents the "
            "answers are supposed to be found IN, and eval_path at the questions.",
            needs=("corpus_path", "eval_path"),
        )

    # RECALL ALREADY MEASURED ON THIS CORPUS - THE REFUSAL THAT CANNOT FIRE
    # TODAY, WRITTEN AS THE OTHERS ARE AND SAID TO BE UNREACHABLE RATHER THAN
    # PRESENTED AS A GUARANTEE.
    #
    # The eval-set proposer's rule is that "already measured" is a claim about a
    # THING and not about a number, and this is the same question about a
    # different fact. Applying it here means recovering what a stored recall
    # figure was measured OF, and the ledger cannot say: the derivation
    # `measure_retriever_recall` writes names the eval file, the index by name
    # and id, k and the ground-truth column - and NOT the corpus, because an
    # index is a thing in this harness's database rather than a path.
    # `subject_of_a_recorded_measurement` reads one sentence, `counted N rows in
    # <path>`, so it returns None here and this guard falls through to the note.
    #
    # THAT IS THE HONEST ANSWER AND NOT A GAP TO PAPER OVER. Refusing on the
    # number alone is exactly the defect this proposer's sibling spent a
    # milestone removing - "your eval set has already been counted: 120 rows",
    # about a file the person had not mentioned. A recall figure taken off some
    # other corpus says nothing about this one, a figure whose subject nothing
    # recorded is not evidence of freshness, and absent is absent. So both fall
    # through to a sentence in the plan, and the refusal stands ready for the day
    # a recall derivation names something this file can match a corpus against.
    already, measured_of = a_measurement_of(situation, "retriever_recall_at_k", corpus)
    if already:
        raise NotEnoughToPropose(
            "Your retriever has already been scored on this corpus: "
            f"retriever_recall_at_k is "
            f"{situation.values.get('retriever_recall_at_k')!r}, measured, on "
            f"{corpus_subject.key}, against the {bar} bar "
            f"{_THE_RAG_CRITERION_NODE} sets. Indexing it and measuring it again "
            "would return the same number and move nothing. What is left is the "
            "work that number points at - chunking, a reranker, query rewriting, "
            "or the generator - and none of it is a step this build can run.",
            needs=("a change to the retriever, not another measurement of it",),
        )

    stale_recall = ""
    if situation.is_measured("retriever_recall_at_k"):
        stale_recall = (
            (
                f" A recall figure measured on {measured_of.key} is on file, and "
                f"that is not {corpus_subject.key}, so it says nothing about the "
                "index this build makes"
                if measured_of
                else " A recall figure is on file and nothing records which corpus "
                "it was measured over - what was recorded is the eval file and the "
                "index by name, and an index is a thing in this database rather "
                "than a path this build can compare against the folder you named"
            )
            + ", so this build measures rather than reusing it."
        )

    # WHAT EACH STEP WILL BE CALLED WITH. Offered generously, filtered by the
    # tools' own schemas, and refused when one of them wants something this
    # situation cannot name - see `_a_call_that_fits`.
    attaching = {"path": corpus, "role": "the corpus the retriever fetches from"}
    indexing = _a_call_that_fits(
        "build_retrieval_index", {"path": corpus}, must_carry=("path",)
    )
    scoring_offer: dict[str, Any] = {
        "eval_path": evaluation,
        "question_field": question_field,
        # THE INDEX IS NAMED RATHER THAN INFERRED. Both retrieval readers default
        # to "the most recent index in this conversation", which is a fine
        # default for a person typing and a bad one for a plan: a build approved
        # on Tuesday and run on Wednesday would score whichever index happened to
        # be newest. A `Ref` makes the dependency a thing `Build.validate` checks
        # rather than an ordering this file asserted.
        "index_id": Ref("index", "index_id"),
    }
    if passage_field:
        scoring_offer["ground_truth_field"] = passage_field
    if depth > 0:
        scoring_offer["k"] = depth
    # NO `answer_field`, DELIBERATELY. Supplying it adds `answer_in_passage_rate`
    # - the tool says in as many words that it is a WEAKER and DIFFERENT
    # measurement and is never recorded as `retriever_recall_at_k`. The engine
    # asked for recall, so this plan asks for recall and nothing that could be
    # read as it.
    scoring = _a_call_that_fits(
        "measure_retriever_recall",
        scoring_offer,
        must_carry=("eval_path", "question_field"),
    )

    steps: list[Step] = []

    steps.append(
        Step(
            id="attach",
            tool="attach_context",
            why=(
                "Record where the corpus is, so the index, the search and the "
                "score below are all about the same pile of documents rather than "
                "about three paths that happen to look alike."
            ),
            arguments=attaching,
            produces=(
                Output(
                    "path",
                    "string",
                    "the path as the harness recorded it",
                    at="what_it_is.path",
                ),
            ),
            cost=_local_cost(
                "attach_context",
                find_out_by="it is one filesystem stat and one row written; time it once",
            ),
            exit_criterion=ExitCriterion(
                stated="the harness has the corpus path on file",
                source="tool_result",
                subject="ok",
                comparator="is_true",
            ),
            operates_on=corpus_subject,
        )
    )

    # COUNT THE EVAL SET FIRST WHEN NOBODY HAS COUNTED THIS ONE. Recall is a
    # fraction and a fraction has a denominator; `_propose_measure_the_baseline`
    # counts first for the same reason and this is the same question about the
    # same fact, asked through `a_measurement_of` so that a count of some OTHER
    # file does not suppress it.
    counted_here, _ = a_measurement_of(situation, "eval_size_n", evaluation)
    needs_for_recall: tuple[str, ...] = ("index",)
    if not counted_here:
        counting = {"path": evaluation, "finish_the_count": True}
        steps.append(
            Step(
                id="count",
                tool="measure_eval_set",
                why=(
                    "Count the eval set before scoring a retriever against it, so "
                    "the recall figure has a denominator the harness read itself. "
                    "A fraction over an eval set nobody counted is a fraction with "
                    "one half of it missing."
                ),
                arguments=counting,
                produces=(Output("rows", "integer", "the counted rows", at="rows"),),
                cost=_local_cost(
                    "measure_eval_set",
                    find_out_by=(
                        "the result carries the seconds the count took; run it "
                        "once and the rate is known for this machine"
                    ),
                ),
                exit_criterion=ExitCriterion(
                    stated="the rows are counted to the end of the file",
                    source="tool_result",
                    subject="exact",
                    comparator="is_true",
                ),
                operates_on=_subject_of_a_call("measure_eval_set", counting)[0],
            )
        )
        needs_for_recall = ("index", "count")

    steps.append(
        Step(
            id="index",
            tool="build_retrieval_index",
            why=(
                "Index your documents on this machine. This is the artifact the "
                "diagnosis asked for: the thing that puts the right passage in "
                "front of the model instead of hoping the weights remember it."
            ),
            arguments=indexing,
            produces=(
                Output(
                    "index_id",
                    "integer",
                    "the index that was built, so the steps below name it "
                    "rather than taking whichever one is newest",
                    at="index_id",
                ),
                Output(
                    "passages",
                    "integer",
                    "how many passages your documents were cut into",
                    at="passages",
                ),
            ),
            needs=("attach",),
            cost=_retrieval_cost(
                "build_retrieval_index",
                find_out_by=(
                    "no index has been built on this machine, so run it over a "
                    "slice of the corpus first and read the seconds it reports; "
                    "the whole corpus is that per document"
                ),
            ),
            operates_on=_subject_of_a_call("build_retrieval_index", indexing)[0],
            exit_criterion=ExitCriterion(
                stated=(
                    "your documents are cut into at least one passage and the "
                    "index is on this machine"
                ),
                source="tool_result",
                subject="passages",
                comparator="at_least",
                value=1,
            ),
            risks=(
                Risk(
                    what="the corpus is in formats no reader in this harness opens",
                    what_we_do=(
                        "the step reports which files it could read and which it "
                        "skipped, and an index built over a fraction of your "
                        "documents is said to be that rather than reported as an "
                        "index of the corpus"
                    ),
                ),
                Risk(
                    what=(
                        "the corpus is larger than the index's own passage cap, so "
                        "the index covers part of it"
                    ),
                    what_we_do=(
                        "the step says the index is truncated, and "
                        "measure_retriever_recall then refuses to stamp anything "
                        "off it - a recall measured against part of a corpus is "
                        "not a recall over the corpus. The plan stops there rather "
                        "than reporting a number about a fraction"
                    ),
                ),
                Risk(
                    what="the corpus is large enough that indexing takes a long time",
                    what_we_do=(
                        "nothing here knows how long, and this plan says so rather "
                        "than guessing - run it over a slice first, which is the "
                        "`find_out_by` on this step's own wall-clock estimate"
                    ),
                ),
            ),
        )
    )

    asked = str(situation.query or "").strip()
    if asked:
        # THE LOOK RUNS BEFORE THE SCORE, AND `needs` IS WHAT MAKES THAT TRUE.
        # Steps with no dependency between them share a wave and run at once, so
        # a step whose `why` says "before it shows you a number" and which the
        # executor is free to run beside the scoring is a sentence the plan does
        # not keep. Nothing is passed between them; the ordering is the product
        # intent, which is a legitimate thing for `needs` to carry as long as the
        # plan does not pretend it is a data dependency.
        needs_for_recall = needs_for_recall + ("look",)
        looking_offer: dict[str, Any] = {
            "query": asked,
            "index_id": Ref("index", "index_id"),
        }
        if depth > 0:
            looking_offer["k"] = depth
        looking = _a_call_that_fits(
            "search_the_index", looking_offer, must_carry=("query",)
        )
        steps.append(
            Step(
                id="look",
                tool="search_the_index",
                why=(
                    "Show you what your own index returns for a question you chose "
                    f"({asked!r}), before it shows you a number about it. A recall "
                    "figure you have no way to sanity check is a number you have to "
                    "take on trust, and this product does not ask for that anywhere "
                    "else."
                ),
                arguments=looking,
                produces=(
                    Output(
                        "passages",
                        "array",
                        "the passages that came back, in the order they came back",
                        at="passages",
                    ),
                ),
                needs=("index",),
                cost=_retrieval_cost(
                    "search_the_index",
                    find_out_by=(
                        "one query against an index that exists; time it once and "
                        "it is timed for every query of this size"
                    ),
                ),
                exit_criterion=ExitCriterion(
                    stated=(
                        "a ranking comes back for your query and you can read the "
                        "passages in it"
                    ),
                    source="tool_result",
                    subject="passages",
                    comparator="exists",
                ),
                risks=(
                    Risk(
                        what=(
                            "your query has no term the index's tokeniser keeps, "
                            "so there is no ranking to show"
                        ),
                        what_we_do=(
                            "the step says that in those words rather than "
                            "returning an empty result set, which reads as 'the "
                            "index found nothing' and means something else "
                            "entirely"
                        ),
                    ),
                ),
            )
        )

    steps.append(
        Step(
            id="recall",
            tool="measure_retriever_recall",
            why=(
                "Score the retriever ON ITS OWN: for every row of your eval set, is "
                "the passage that should answer it among the top few that came "
                "back? That single number decides whether the next piece of work is "
                "fixing the retriever, training the retriever, or the generator - "
                "three different jobs, and nothing else tells them apart."
                + (
                    ""
                    if "k" in scoring
                    else " k is left to the tool's own default, because how many "
                    "passages count as 'the top few' is a property of that "
                    "instrument and not a number this plan gets to pick."
                )
                + (
                    ""
                    if "ground_truth_field" in scoring
                    else " You did not say which column names the right document, "
                    "so the tool picks a conventional one and its reply says which "
                    "it used - and refuses rather than guessing if there is none."
                )
            ),
            arguments=scoring,
            produces=(
                Output(
                    "recall_at_k",
                    "number",
                    "how often the right passage was in the top k",
                    at="recall_at_k",
                ),
                Output(
                    "questions_scored",
                    "integer",
                    "how many questions the figure is over - the denominator",
                    at="questions_scored",
                ),
                Output(
                    "k_used",
                    "integer",
                    "how deep the retriever was allowed to look - the k in "
                    "retriever_recall_at_k, which is half of what the number means",
                    at="k",
                ),
                Output(
                    "resolution",
                    "object",
                    "the smallest difference this many questions can tell apart",
                    at="resolution",
                ),
            ),
            needs=needs_for_recall,
            cost=_retrieval_cost(
                "measure_retriever_recall",
                find_out_by=(
                    "run it with a handful of rows first and read the seconds it "
                    "reports; the full eval set is that per row"
                ),
            ),
            operates_on=_subject_of_a_call("measure_retriever_recall", scoring)[0],
            # `stampable` AND NOT `ok`, AND THE DIFFERENCE IS THE WHOLE CHECK.
            # This tool returns a refusal in the SAME SHAPE as a scored run -
            # `ok: True`, every key present, `recall_at_k: None` - deliberately,
            # so a caller cannot forget to handle one. That makes `ok is_true`
            # the exit criterion that passes on a run which measured nothing, and
            # `recall_at_k exists` no better, because a null is present. The one
            # field that separates them is `stampable`, which the tool sets only
            # when the run scored every eligible row, resolved every ground
            # truth, did not hit the row cap and ran against an untruncated
            # index. A step that cannot show it worked did not work.
            exit_criterion=ExitCriterion(
                stated=(
                    "the run is one this harness would stamp: every eligible row "
                    "scored, every ground truth resolved, no row cap hit, and the "
                    "index covering the whole corpus"
                ),
                source="tool_result",
                subject="stampable",
                comparator="is_true",
            ),
            risks=(
                Risk(
                    what=(
                        "the eval set identifies the right passage in a way the "
                        "index cannot match - a title against chunk ids, or free "
                        "text against a document name"
                    ),
                    what_we_do=(
                        "the step names the rows it could not resolve and records "
                        "NOTHING rather than scoring the rows that happened to "
                        "line up. A recall over the subset that matched is a "
                        "number about a set nobody chose, and it reads exactly "
                        "like a recall over the eval set"
                    ),
                ),
                Risk(
                    what=(
                        f"recall comes back below {bar}, which is the bar "
                        f"{_THE_RAG_CRITERION_NODE} sets"
                    ),
                    what_we_do=(
                        "that is the plan working. The build's job is to produce "
                        "the number, not a particular value of it, and a low one is "
                        "the useful answer: it sends the next move to chunking, "
                        "hybrid search, a reranker or query rewriting rather than "
                        "to the generator"
                    ),
                ),
            ),
        )
    )

    steps.append(
        _recheck_step(
            ("recall",),
            "retriever_recall_at_k",
            why=(
                "Walk the tree again on the measured recall. Whether it means 'fix "
                "the retriever', 'train the retriever' or 'the generator is the "
                "problem' is the engine's to decide, and those are three different "
                "pieces of work."
            ),
        )
    )

    stated = engine_exit_criterion(plan["node"], situation.spec)
    if not stated:  # pragma: no cover - the spec stopped stating one
        raise NotEnoughToPropose(
            f"{plan['node']} no longer declares an exit_criterion, so this build "
            "has nothing to hold itself to but a sentence this file wrote. Nothing "
            "is planned against a criterion this file preferred."
        )

    the_half_we_reach = (
        " THIS BUILD REACHES THE FIRST HALF OF THAT. It indexes your corpus and "
        "measures retriever_recall_at_k on your eval set. It does NOT measure the "
        "end-to-end score: that needs the retrieved passages put in front of your "
        "model and the answer graded, and no tool in this harness does "
        "retrieval-augmented generation - run_eval sends a system prompt and "
        "grades text, which is not the same thing. So this plan ends with a "
        "measured retriever and an unmeasured end-to-end score, and says so rather "
        "than declaring a criterion it can meet."
        if situation.outcome == "NO_TRAIN__RAG"
        else ""
    )

    egress = _egress_for([step.tool for step in steps])
    said = str(situation.result.say or "").strip()

    theirs_not_ours = (
        "You already run a retriever and this does not measure it. It measures the "
        "one this harness builds over the corpus you point at, which is a floor "
        "and a comparison: if a plain index over the same documents finds the "
        "right passage and yours does not, the corpus is fine and the retriever is "
        "the problem. "
        if situation.outcome == "ACTION__MEASURE_RETRIEVER_RECALL"
        else ""
    )
    no_query = (
        ""
        if asked
        else " You did not give me a question to try, so this plan indexes and "
        "measures without showing you a single retrieval first. Pass `query` with "
        "something you would actually ask and the plan adds a step that puts the "
        "passages in front of you before anything is scored; a question this file "
        "made up would be a demonstration nobody chose."
    )

    questions: tuple[Question, ...] = ()
    if not situation.values.get("retrieval_tried"):
        questions = (
            Question(
                ask=(
                    "Once this has run you will have built retrieval and measured "
                    "it. Is retrieval now something you have tried?"
                ),
                why=(
                    "retrieval_tried is what routed you here - S3_BUILD_RAG fires "
                    "on `not retrieval_tried` - and G2 and G3 both read it before "
                    "any training branch may open. Nothing in this harness watches "
                    "you adopt a retriever, so it is yours to say, and the "
                    "measurement above is what makes saying it worth anything."
                ),
                fact="retrieval_tried",
            ),
        )

    return Build(
        id=plan["id"],
        title=plan["title"],
        for_outcome=situation.outcome,
        because=(
            (f"{said} " if said else "")
            + theirs_not_ours
            + "This build indexes the documents you point at, on this machine, and "
            "then scores the retriever alone on your own eval set - for each "
            "question, is the right passage in the top few. "
            + (
                "Nothing in this plan can leave the machine: not one step's tool "
                "declares a network read, so the sandbox declares no egress at all "
                "and Build.validate refuses any step that would need one. A local "
                "index is local."
                if not egress
                else "One step in this plan reaches your connected model, which is "
                "declared on the environment below where you can see it before you "
                "approve it."
            )
            + f" The bar is {bar}, read off {_THE_RAG_CRITERION_NODE} rather than "
            "chosen here."
            + the_half_we_reach
            + stale_recall
            + no_query
        ),
        steps=tuple(steps),
        environment=_sandbox(plan["id"], corpus, evaluation, reason=egress),
        exit_criterion=ExitCriterion(
            stated=(
                # WHICH NODE THE BAR COMES FROM, and, when the run stopped
                # somewhere else, that it stopped somewhere else. Four nodes emit
                # NO_TRAIN__RAG and only S3_BUILD_RAG states a criterion, so a
                # person whose diagnosis stopped at S3_VOLATILE_KNOWLEDGE would
                # otherwise read a criterion attributed to a node they never
                # reached and have no way to tell whether this file picked it or
                # the engine did.
                (
                    ""
                    if str(situation.result.node or "") == plan["node"]
                    else f"Your run stopped at {situation.result.node}, which "
                    f"declares no exit criterion of its own; {plan['node']} is "
                    "where the bar for this outcome is set. "
                )
                + f"{plan['node']} states it as: {stated!r}."
                + (
                    the_half_we_reach
                    or " What this build produces is exactly that: "
                    "retriever_recall_at_k, recorded by the tool that measured it, "
                    "so the tree is walked again on a number rather than on a gap."
                )
            ),
            source="diagnosis",
            subject="fact_origins.retriever_recall_at_k",
            comparator="is_measured",
        ),
        questions=questions,
        risks=(
            Risk(
                what=(
                    "the index this harness builds is not the retriever you run in "
                    "production"
                ),
                what_we_do=(
                    "the number is stamped as a measurement of the index built "
                    "here, over the corpus you named, and every step says so. It is "
                    "a floor and a comparison rather than a report card on your "
                    "system, and the engine reads it as the recall of a retriever "
                    "over this corpus - which is the question the branch turns on"
                ),
            ),
            Risk(
                what="the right passage is simply not in the corpus for some questions",
                what_we_do=(
                    "recall comes back low and the honest next move is the corpus "
                    "rather than the retriever. No amount of chunking finds a "
                    "document that is not there, and this is the cheapest way there "
                    "is to find that out - before a fine-tune is blamed for it"
                ),
            ),
        ),
        facts=dict(situation.origins),
    )


# ---------------------------------------------------------------------------
# The chunking sweep, and the one lever of four that this harness owns.
#
# `S3_RETRIEVAL_IS_THE_BOTTLENECK` became REACHABLE the day the retrieval bench
# landed: `retriever_recall_at_k` had no instrument before it, so the node could
# not fire, and the moment it could the product had an outcome it could measure
# its way into and nothing at all to offer afterwards. That is worse than the
# dead end the bench closed - we made the measurement possible and left the
# consequence dangling.
#
# THE NODE NAMES FOUR LEVERS AND WE OWN ONE. `chunking strategy, hybrid BM25 +
# dense, a cross-encoder reranker, query rewriting`. `passage_chars` is an
# argument of `build_retrieval_index`, whose own schema calls it "a stated
# choice, not a measured optimum", so chunking is a thing this harness can vary,
# rebuild and re-measure on the person's own eval set. The other three need an
# embedding model, a cross-encoder, or the person's own connected model, and
# this product ships no AI. Three refusals of honesty rather than of laziness,
# and the build NAMES them rather than quietly proposing the one it can do as
# though it were the whole of the engine's sentence.
#
# AND A SWEEP IS STRICTLY WORSE THAN THE TWO-RUN CASE `app/tools/evals.py` WAS
# BUILT FOR. Two failures arrive the moment there are more than two settings:
# the maximum of N noisy estimates is biased upward even when every setting is
# identical, and a family of tests at 0.05 apiece separates something in TWO IN
# FIVE families of eight settings that do not differ at all - 42.0% of 200
# seeded null families, measured, against 3.5% after Holm. Both are the "a user
# shown forty unresolvable deltas will believe the tenth" sentence in a new
# costume.
#
# THIS READ "ROUGHLY A ONE-IN-THREE CHANCE ... AT EIGHT SETTINGS" until
# 2026-08-21, which was a number nobody had computed: 33% is 1-(1-.05)^8, and
# eight settings is twenty-eight tests, not eight. See the note beside the
# same correction in `app/tools/retrieval.py`. `compare_chunkings` owns the correction and the split-half
# confirmation; what THIS file owns of the problem is three things, and each one
# is a refusal rather than a feature:
#
#   1. IT WILL NOT CHOOSE THE SETTINGS. The number of settings is the family
#      size every p-value is corrected against, so choosing them is choosing the
#      false-winner rate on somebody's behalf. The tool declares `settings`
#      required with no default for exactly this reason and this plan does not
#      supply one it invented.
#   2. IT WILL NOT RECORD A WINNER. Nothing in this build stamps
#      `retriever_recall_at_k`, so no diagnosis is routed on a maximum selected
#      on the rows it is then reported against.
#   3. IT REFUSES IN ADVANCE WHEN NOTHING COULD BE RESOLVED, with the number of
#      rows that would fix it, computed from two measured facts.

#: THE TOOL NAME, FIXED SO THE TWO LANES CANNOT DISAGREE, exactly as
#: `THE_RETRIEVAL_TOOLS` is. A tuple of one because the shape has to match the
#: refusal and the coverage entry that read it, and because a second sweep tool
#: would be added here rather than in a second mechanism.
THE_CHUNKING_TOOLS: tuple[str, ...] = ("compare_chunkings",)

THE_CHUNKING_SWEEP = THE_CHUNKING_TOOLS[0]


def chunking_sweep_missing() -> tuple[str, ...]:
    """Which of the sweep's tools are not registered in this process, right now.

    Read off the live registry every time, for `retrieval_tools_missing`'s
    reason: the answer changed the day the sibling lane's `compare_chunkings`
    registered, and nothing in this file had to be edited on that day.
    """
    return tuple(name for name in THE_CHUNKING_TOOLS if REGISTRY.get(name) is None)


def the_chunking_sweep_is_registered() -> bool:
    return not chunking_sweep_missing()


#: The node that emits `NO_TRAIN__FIX_RETRIEVAL`. One node emits it, which is
#: why this is a constant and not a search: `S3_BUILD_RAG` shares its outcome
#: with three other nodes and the retrieval bench had to say which one spoke for
#: it. Here there is only one, and the test that reads this constant back
#: against the spec is what says so if a second ever appears.
_THE_BOTTLENECK_NODE = "S3_RETRIEVAL_IS_THE_BOTTLENECK"

#: The significance level this product calls evidence at. It is 0.05 in two
#: other places - `evals.compare` sets `resolved = p_value <= 0.05`, and
#: `app/tools/retrieval.py` corrects the sweep's family at `SWEEP_ALPHA = 0.05`
#: - and a third copy is exactly the drift this repository has been bitten by
#: twice. It is not imported, because `app/tools/propose.py` refusing to import
#: at module level is what lets this file keep working when a bench is absent;
#: it is PINNED instead, by
#: `tests/test_the_chunking_lever_is_swept_or_refused.py`, which reads both
#: other definitions and goes red if either moves. A plan that refused work the
#: sweep would have resolved, or planned work it could not, would be this number
#: disagreeing with itself.
RESOLVED_AT = 0.05

#: A guard on the search below rather than a threshold: `mcnemar(b, 0)` is
#: `2 ** (1 - b)`, so it passes any positive alpha within a few dozen rows and a
#: loop that has not terminated by here is a changed test, not a large eval set.
_A_FLOOR_NOBODY_COULD_REACH = 4096


def discordant_rows_that_could_resolve(comparisons: int = 1) -> int:
    """The fewest rows that must CHANGE, all one way, before a paired test resolves.

    **ASKED OF `evals.mcnemar` RATHER THAN DERIVED HERE.** The closed form is
    one line - two-sided exact McNemar over `m` discordant rows is smallest when
    every one goes the same way, and then `p = 2 ** (1 - m)` - and writing it
    would be a second definition of this product's idea of evidence, sitting in
    the file that plans work rather than in the file that judges it. So this
    counts upwards and asks the real function, which is slower by an amount
    nobody can measure and cannot disagree with the verdict the sweep will
    return.

    `comparisons` is the family size and it is the whole reason a sweep is
    harder than a pair. Eight settings is twenty-eight pairwise tests; the
    correction that keeps the family-wise error rate at `RESOLVED_AT` tests the
    smallest p-value against `RESOLVED_AT / family`, so the floor rises with
    every setting added. That threshold is the most lenient one in a Holm
    step-down family, which is what makes this a NECESSARY condition for any
    pair to separate at all rather than a rule of thumb about the average pair.
    """
    alpha = RESOLVED_AT / max(1, int(comparisons))
    changed = 0
    while changed < _A_FLOOR_NOBODY_COULD_REACH:
        changed += 1
        if evals.mcnemar(changed, 0) <= alpha:
            return changed
    raise NotEnoughToPropose(  # pragma: no cover - evals.mcnemar changed shape
        f"evals.mcnemar no longer reaches {alpha} for any number of rows this "
        "file can search, so the smallest resolvable difference cannot be "
        "computed and nothing is planned against a floor this file guessed."
    )


def pairwise_comparisons(settings: int) -> int:
    """How many pairwise tests a sweep of `settings` settings is - `m(m-1)/2`.

    EVERY PAIR AND NOT EVERY SETTING, because that is what the tool actually
    runs: `compare_chunkings` compares each setting with each other setting and
    corrects the whole family together. Four settings is six tests, not four,
    and the difference is the floor below moving by a row - which is the sort of
    arithmetic that is right in one file and remembered wrongly in another, so
    it is computed here and pinned against the tool's own `family_size` by test.
    """
    count = max(0, int(settings))
    return count * (count - 1) // 2


def _as_exact(score: float) -> Fraction:
    """A score as the decimal it is printed as, not as the binary float it is.

    THIS IS THE FABRICATION INVARIANT, IN ARITHMETIC. `1.0 - 0.55` is
    `0.44999999999999996`, so `int((1 - 0.55) * 100)` is 44 and the plan printed
    "44 of them are wrong today" about a hundred rows at 0.55 where the
    arithmetic it states - a hundred times forty-five hundredths - is 45. A
    displayed number that its own printed derivation contradicts is an invented
    number whatever produced it, and a rounding error is not a better author
    than a person guessing.

    `Fraction(repr(x))` is the shortest decimal that round-trips to this float,
    which is the number the user typed, the number `measure_baseline` reported,
    and the number the sentence beside it prints. Everything downstream is then
    exact integer arithmetic on that.

    A non-finite score is clamped rather than raised on. `Fraction('nan')` is a
    `ValueError`, and the float arithmetic this replaced returned 0 for it - a
    proposer that CRASHES where it used to answer would be a worse defect than
    the one being fixed here, and no measured score is ever nan or inf, so this
    is a floor under a case that should not arise rather than a behaviour.
    """
    value = float(score)
    if not math.isfinite(value):
        return Fraction(1)
    return Fraction(repr(value))


def questions_wrong_now(recall: float, rows: int) -> int:
    """How many questions the measured retriever gets WRONG - the rows that can move.

    THE BOUND THAT MAKES THE REFUSAL EXACT. A chunk setting can only turn a row
    from wrong to right; a row the retriever already answers cannot improve on
    it. So the rows that could change in the winning direction number at most
    the rows it currently gets wrong, and that is `rows * (1 - recall)`,
    floored, because a fraction of a question is not a question.

    Floored on the EXACT decimal - see `_as_exact`. In float it was floored on a
    value a hair under the truth, and 144 of the 7,600 points on a 19-score by
    400-row grid came out one question low, every one of them under. Two of them
    crossed the refusal floor: 30 graded rows at a measured 0.8 has exactly 6
    wrong rows and was refused as having 5.
    """
    return max(0, int(max(Fraction(0), Fraction(1) - _as_exact(recall)) * max(0, int(rows))))


def questions_that_could_resolve(recall: float, comparisons: int = 1) -> int:
    """How many eval questions are needed before ANY setting could be shown better.

    The smallest `n` for which `questions_wrong_now(recall, n)` reaches the
    discordant floor. It is a NECESSARY condition and not a sufficient one - it
    says a comparison against the retriever you measured cannot possibly resolve
    below this, never that it will resolve above it - and every sentence that
    carries it says so, because a floor read as a promise is
    `docs/PRODUCT_SPEC.md`'s "n>=100 to trust a 5-10 point delta" being used as
    a threshold again, which is the misreading `evals.resolution_for` exists to
    stop.

    EXACT, for the reason in `_as_exact`: `6 / (1 - 0.8)` in float is
    `30.000000000000007`, so this returned 31 while the sentence that carries it
    printed "6 / (1 - 0.8), rounded up" - a number contradicted by its own
    stated derivation, in a refusal.
    """
    floor = discordant_rows_that_could_resolve(comparisons)
    wrong = max(Fraction(0), Fraction(1) - _as_exact(recall))
    if wrong <= 0:
        return 0
    return int(-((-Fraction(floor)) // wrong))


#: The libraries a dense or hybrid retriever needs, none of which this product
#: ships. Named so the sentence about them is a reading of THIS machine rather
#: than something somebody remembered about the environment.
_THE_DENSE_LIBRARIES: tuple[str, ...] = (
    "sentence_transformers",
    "faiss",
    "rank_bm25",
)


def dense_libraries_missing() -> tuple[str, ...]:
    """Which of them are not importable here, LOOKED AT rather than assumed.

    `importlib.util.find_spec` finds a module without executing it, so this
    costs a path search and imports nothing - which matters, because importing a
    library to find out whether it is there is how a proposal acquires a side
    effect.

    It is a reading and not a claim, and it fails in the right direction twice
    over. If somebody installs sentence-transformers tomorrow, the sentence in
    the plan changes from "not on this machine" to "on this machine, and still
    not something any tool here uses" rather than staying false. And if the
    search itself raises - a broken meta path finder, a namespace package with
    no spec - the name is reported as missing, which understates what is
    available and can only make the plan more cautious about what it offers.
    """
    absent: list[str] = []
    for name in _THE_DENSE_LIBRARIES:
        try:
            found = importlib.util.find_spec(name)
        except (ImportError, ValueError, AttributeError):
            found = None
        if found is None:
            absent.append(name)
    return tuple(absent)


def _the_levers_we_do_not_own() -> str:
    """The three of the engine's four this product cannot pull, and why each fails.

    `docs/VISION.md`: *"Bring your own model. We ship no AI."* That is the whole
    reason and it is one sentence for all three - but they fail differently and
    a person deciding what to do next week needs them apart. Two need a model
    this product does not have and would have to acquire as a dependency; the
    third needs the model they already connected, which is a different
    provenance and a different egress conversation from anything in this plan,
    every step of which sends nothing anywhere.
    """
    absent = dense_libraries_missing()
    if len(absent) == len(_THE_DENSE_LIBRARIES):
        dense = (
            "none of " + ", ".join(_THE_DENSE_LIBRARIES) + " is importable on "
            "this machine, looked at with importlib rather than remembered"
        )
    elif absent:
        dense = (
            ", ".join(absent) + " is not importable here, and no tool registered "
            "in this harness uses any of " + ", ".join(_THE_DENSE_LIBRARIES)
        )
    else:
        dense = (
            "all of "
            + ", ".join(_THE_DENSE_LIBRARIES)
            + " are importable on this machine and no tool registered in this "
            "harness uses any of them, so the gap is a tool rather than a "
            "dependency"
        )
    return (
        "THE THREE THIS HARNESS CANNOT PULL WITH YOU, named rather than left "
        "out. HYBRID BM25 + DENSE and A CROSS-ENCODER RERANKER both need an "
        f"embedding or cross-encoder model, and this product ships none - {dense}. "
        "QUERY REWRITING needs the model you connected, which would send your "
        "questions to it - a different provenance from every step in this plan "
        "and an egress conversation that belongs where you can see it rather "
        "than inside a sweep. All three are yours, and the engine reads two of "
        "them: reranker_tried and query_rewriting_tried are both source: ask "
        "with no tool measuring either, so nothing here can watch you do them "
        "and they are yours to say. A sweep of chunk sizes is one quarter of "
        "what the engine asked for."
    )


def _the_reason_the_sweep_is_not_here_yet() -> dict[str, str]:
    """Why `NO_TRAIN__FIX_RETRIEVAL` is uncovered WHILE it is, naming what is absent.

    A function and not a constant, for `_RETRIEVAL_NOT_HERE_YET`'s reason: the
    sentence that used to sit here answered for four outcomes at once and two of
    them went false. While `compare_chunkings` is registered this returns
    nothing at all, the outcome sits in `COVERAGE` alone, and the day it is not
    registered the reason comes back naming the tool that went missing - with
    nothing in this file edited either way.

    The half of the old reason that is STILL TRUE is kept, because it is what
    makes any answer here a partial one: three of the engine's four levers are
    not ours, and the two facts that clear the rest of the node's condition are
    source: ask.
    """
    if the_chunking_sweep_is_registered():
        return {}
    return {
        "NO_TRAIN__FIX_RETRIEVAL": (
            "the four things the engine names - chunking strategy, hybrid BM25 "
            "plus dense, a cross-encoder reranker, query rewriting. Exactly one "
            "of them is a thing this harness could do with you: passage_chars "
            "is an argument of build_retrieval_index and its own schema calls "
            "it a stated choice rather than a measured optimum, so a sweep over "
            "it is real work this product could run and measure. The tool that "
            "runs it is not registered here - "
            f"{list(chunking_sweep_missing())} of "
            f"{list(THE_CHUNKING_TOOLS)} are missing from this registry - and a "
            "step naming a tool nobody registered is a plan that fails after "
            "you approved it. The other three are not a gap in this file: they "
            "need an embedding model, a cross-encoder, or your own connected "
            "model, and this product ships no AI. reranker_tried and "
            "query_rewriting_tried are both source: ask with no tool measuring "
            "either, so what moves this outcome the rest of the way is you "
            "doing the work and saying you did."
        )
    }


#: WHAT THIS BUILD IS. One outcome, one node, one lever - so this is a constant
#: rather than the table the two-outcome benches needed.
_THE_BOTTLENECK_BUILD = {
    "id": "fix_the_retriever",
    "title": "Sweep the one retrieval lever this harness owns, and say what it settles",
}

#: The fewest settings a comparison can be made of. Not the tool's limit, which
#: is the tool's to state and to refuse on: this is arithmetic, because
#: `pairwise_comparisons(1)` is zero tests and a sweep of one setting is a
#: measurement rather than a comparison.
_A_COMPARISON_NEEDS = 2


def _propose_fix_the_retriever(situation: Situation) -> Build:
    """`NO_TRAIN__FIX_RETRIEVAL` - the consequence our own last change made reachable.

    **THE EXIT CRITERION IS THE HARD PART AND IT IS AN HONESTY PROBLEM.**
    `S3_RETRIEVAL_IS_THE_BOTTLENECK` states an `action:` and a `say:` and - alone
    among the nodes any proposer here answers - **no `exit_criterion:` at all**.
    That is read off the spec every time rather than believed: if the engine ever
    states one, this build is held to it and says so, and until then the build
    says in as many words that the engine declared none, and names what it checks
    instead. A build whose success condition was invented by the proposer is the
    proposal-loop trap in its purest form, and it is invisible precisely because
    an invented criterion reads better than a derived one.

    What IS derived, and from what: the node's own `condition` contains
    `retriever_recall_at_k < 0.8`, so the clause a chunking sweep could act on
    stops holding at the bar `S3_BUILD_RAG` states. That derivation is stated in
    the build, attributed to the condition it came from, and then explicitly NOT
    made this build's criterion - because chunking is one of the four levers the
    node names and the only one we own, so clearing the bar is not a thing this
    plan can promise, and a criterion that promised it would be claiming the
    other three levers' work.

    **AND "RECALL GOES UP" IS A TRAP, NOT A CRITERION.** Recall rising two points
    on ninety questions is inside the resolution and means nothing;
    `app/tools/evals.py` exists because a prompt playground shows you 73% then
    76% and lets you conclude. Worse here than there: the maximum of N noisy
    estimates is biased upward even when every setting is identical, so a
    sweep's best is optimistic BY CONSTRUCTION and optimistic on the very rows
    that chose it. So the criteria this build is held to are about the
    comparison having been POSSIBLE and COMPLETE - enough paired questions
    survived, every pair of the settings you named was tested and corrected
    together - and never about the direction a number moved.

    **THREE THINGS THIS BUILD REFUSES TO DO, EACH OF WHICH WOULD READ AS A
    FEATURE.**

    1. **It will not choose the settings.** `compare_chunkings` declares
       `settings` required with no default, and says why in its own schema: the
       number of settings is the family size every p-value is corrected against.
       Choosing eight for somebody is choosing their false-winner rate. This is
       the same refusal `_propose_try_a_prompt` makes about the prompt - a
       proposal whose central argument the harness invented is an experiment
       nobody chose - and it is a refusal rather than a gap.
    2. **It will not record a winner.** The obvious plan - rebuild at the best
       setting, run `measure_retriever_recall`, re-enter the tree - would put a
       maximum selected on these rows into the ledger as the number the whole
       knowledge branch routes on, and `retriever_recall_at_k < 0.8` is this
       node's own condition, so an optimistic figure routes a person OUT of "fix
       the retriever" on selection noise. `compare_chunkings` cannot stamp it
       either - it declares `measures=()`, checked at registration - and it
       measures the selection bias itself, on a split half of the same
       questions, which is the honest thing available and is still half the
       rows. So this plan ends in a question rather than in `run_diagnosis`,
       exactly as the prompt bench does when no step it runs can stamp what the
       engine reads.
    3. **It refuses in advance when nothing could be resolved.** The rows that
       can change in the winning direction number at most the rows the measured
       retriever gets WRONG, and a paired test needs a floor of them to move one
       way before it can reach the corrected threshold at all. When `eval_size_n`
       is a measured count of THIS file that product is arithmetic, and the
       refusal is exact and comes with the row count that would fix it. When
       nobody has counted the file, the same number is the exit criterion of the
       count step AND of the sweep's own dry run, so the plan stops before a
       single index is rebuilt rather than after all of them are.
    """
    missing = chunking_sweep_missing()
    if missing:
        raise NotEnoughToPropose(
            "The chunking sweep is not in this harness: "
            f"{list(missing)} of {list(THE_CHUNKING_TOOLS)} are not registered "
            "tools. The plan for this outcome is written and it will not be "
            "drawn against a tool that does not exist, because a step naming a "
            "tool nobody registered is a plan that fails after you approved it.",
            needs=tuple(missing),
        )

    corpus = situation.require_path("corpus_path")
    evaluation = situation.require_path("eval_path")
    question_field, passage_field = _the_question_and_the_right_passage(situation)
    bar = recall_bar(situation.spec)
    depth = max(0, _an_integer(situation.top_k))

    corpus_subject = Subject.of_path(corpus)
    eval_subject = Subject.of_path(evaluation)

    # REFUSAL: THE RECALL THAT SENT YOU HERE WAS TYPED, NOT MEASURED.
    #
    # `retriever_recall_at_k` is declared source: inspect, so only a tool may
    # stamp it - and `tests/test_a_typed_recall_routes_like_a_measured_one.py`
    # pins the hole that leaves: no GATE reads this fact, and the three S3 nodes
    # that do read its VALUE whatever its origin. So a person who typed "my
    # recall is about 0.6" reaches this outcome, and a sweep run for them would
    # compare settings this harness measured against a baseline nobody read.
    # There is nothing to improve on: two numbers from two instruments are two
    # facts and not a difference, which is `evals.compare`'s first refusal
    # wearing a retrieval costume.
    if not situation.is_measured("retriever_recall_at_k"):
        raise NotEnoughToPropose(
            "The recall that routed you here was stated rather than measured: "
            "retriever_recall_at_k is on file as "
            f"{situation.values.get('retriever_recall_at_k')!r} with origin "
            f"{situation.origin('retriever_recall_at_k') or 'nothing recorded'}. "
            "A sweep compares chunk settings this harness measured itself, and "
            "against a baseline nobody read that comparison is two numbers from "
            "two instruments - two facts, not a difference. Measure the "
            "retriever first: that is what ACTION__MEASURE_RETRIEVER_RECALL asks "
            "for and "
            + (
                "propose_build plans it as soon as the diagnosis lands there"
                if the_retrieval_bench_is_registered()
                else "the retrieval bench plans it when it registers"
            )
            + ". Then this sweep has something to improve on.",
            needs=("a measured retriever_recall_at_k",),
        )

    # AND A MEASURED ORIGIN WITH NO VALUE BEHIND IT IS NOT A MEASUREMENT.
    # Origin and value travel together out of the ledger, so this cannot happen
    # through `propose_build` - and every number this build states is derived
    # from the recall, so a missing one would silently become 0.0 and print
    # "your retriever scores 0.0" beside a floor computed from it. That is the
    # invented-number defect with a real origin attached, which is the only kind
    # that survives review.
    try:
        recall = float(situation.values["retriever_recall_at_k"])
    except (KeyError, TypeError, ValueError):
        raise NotEnoughToPropose(
            "The harness records retriever_recall_at_k as measured and holds no "
            f"number for it: the value on file is "
            f"{situation.values.get('retriever_recall_at_k')!r}. Every figure in "
            "this plan - how many questions could change, how many you would "
            "need - is arithmetic on that recall, so there is nothing to compute "
            "and nothing will be made up to stand in for it. Re-measure the "
            "retriever and ask again.",
            needs=("retriever_recall_at_k",),
        ) from None
    condition = engine_node_says(_THE_BOTTLENECK_NODE, "condition", situation.spec)

    # REFUSAL: THERE IS NOTHING TO IMPROVE. The node's own condition is
    # `retriever_recall_at_k < 0.8`, so a recall at or above the bar is not this
    # outcome, and a sweep run to raise a number already past the bar spends
    # hours of rebuilds on a question the diagnosis is not asking. Unreachable
    # through `propose_build`, which runs the engine itself; reachable by any
    # caller assembling a `Situation` by hand, which is exactly how a proposer
    # ends up planning work for a verdict other than the one in front of it.
    if recall >= bar:
        raise NotEnoughToPropose(
            f"Your retriever already scores {recall} and the bar this node turns "
            f"on is {bar} - {_THE_BOTTLENECK_NODE}'s own condition is "
            f"`{condition}`. There is nothing here for a chunking sweep to "
            "improve: rebuilding the index at several settings to raise a number "
            "already past the bar is hours of work for a question this diagnosis "
            "is not asking.",
            needs=("a recall below the bar, or a different outcome",),
        )

    # REFUSAL: THE EVAL SET IS IN THE CORPUS. The retrieval bench's refusal,
    # repeated rather than assumed away, because a sweep makes it worse: every
    # setting indexes the answers, every setting scores near perfect, and the
    # sweep reports that chunking makes no difference - which would be true of
    # the measurement rather than of the retriever, and reads exactly like a
    # real null.
    inside = _the_eval_set_is_inside(evaluation, corpus)
    if corpus_subject.key == eval_subject.key or inside:
        raise NotEnoughToPropose(
            (
                f"Your corpus and your eval set are the same file "
                f"({corpus_subject.key})."
                if corpus_subject.key == eval_subject.key
                else f"Your eval set is inside the corpus you asked me to sweep: "
                f"{eval_subject.key} is under {corpus_subject.key}, so every "
                "index this sweep builds would contain the questions and their "
                "answers."
            )
            + " Every setting then scores near perfect, the sweep reports that "
            "no chunking differs from any other, and that sentence would be "
            "about the measurement rather than about your retriever - a null "
            "that looks exactly like a real one. Point corpus_path at the "
            "documents the answers are supposed to be found IN, and eval_path at "
            "the questions.",
            needs=("corpus_path", "eval_path"),
        )

    # REFUSAL: CHUNKING CANNOT MATTER OVER ONE DOCUMENT. Recall@k asks whether
    # the right passage came back and the eval set names the right DOCUMENT; with
    # one document in the corpus that answer does not depend on how it was cut,
    # so every setting scores identically by construction. It is a guaranteed
    # null and running it is rebuilds for nothing.
    if _the_corpus_is_one_document(corpus):
        raise NotEnoughToPropose(
            f"There is one document at {corpus_subject.key}, so chunking cannot "
            "change which document comes back - every setting retrieves the same "
            "one and scores identically. A sweep over it is a guaranteed null: "
            "it would rebuild the index once per setting and report that nothing "
            "differs, which was true before it ran. Point corpus_path at the "
            "folder holding the documents the retriever has to choose BETWEEN.",
            needs=("corpus_path",),
        )

    # REFUSAL: I WILL NOT CHOOSE THE SETTINGS, AND IT IS NOT A GAP.
    #
    # `compare_chunkings` declares `settings` and says in its own schema that
    # there is no default, with the reason: the number of settings is the family
    # size every p-value in the reply is corrected against. So the settings
    # decide the correction, the correction decides the threshold, and the
    # threshold decides how many questions have to change before anything can
    # separate. A plan that supplied eight of them would be choosing the person's
    # false-winner rate and then showing them a result computed under it.
    # `_propose_try_a_prompt` refuses to draft the prompt for the same reason in
    # the same shape.
    #
    # THIS REFUSAL DOES NOT RIDE ON THE TOOL'S `required` LIST, deliberately.
    # Whether the sweep refuses a call with no settings is the sweep's business
    # and could change; whether THIS FILE picks a family size on somebody's
    # behalf is this file's, and the answer is no either way.
    settings = tuple(
        size for size in (_an_integer(one) for one in situation.chunk_settings) if size > 0
    )
    if len(set(settings)) < _A_COMPARISON_NEEDS:
        raise NotEnoughToPropose(
            "I can plan the sweep and I will not choose what it sweeps over. "
            "Give me at least "
            f"{_A_COMPARISON_NEEDS} different passage sizes, in characters, as "
            "chunk_settings."
            + _what_the_index_calls_its_default()
            + " The reason this one is yours: the "
            "number of settings is the family size every p-value is corrected "
            "against, so choosing them chooses how likely a false winner is. "
            "Two settings is "
            f"{pairwise_comparisons(2)} comparison and needs "
            f"{discordant_rows_that_could_resolve(pairwise_comparisons(2))} "
            "questions to change verdict before anything can separate; eight is "
            f"{pairwise_comparisons(8)} comparisons and needs "
            f"{discordant_rows_that_could_resolve(pairwise_comparisons(8))}. "
            "That is the trade this plan will not make on your behalf.",
            needs=("chunk_settings",),
        )

    family = pairwise_comparisons(len(set(settings)))
    floor = discordant_rows_that_could_resolve(family)
    rows_needed = questions_that_could_resolve(recall, family)

    # REFUSAL: THIS EVAL SET CANNOT RESOLVE ANYTHING, AND THE ROWS THAT WOULD
    # ARE COMPUTED HERE RATHER THAN GUESSED.
    #
    # It fires only on a count OF THIS FILE, through `a_measurement_of`, for the
    # reason the eval-set proposer learned the hard way: a measured `eval_size_n`
    # that counted some other file is a real number about the wrong thing, and
    # refusing on it would stop work over a file the person never mentioned.
    counted_here, _ = a_measurement_of(situation, "eval_size_n", evaluation)
    rows_on_file = _an_integer(situation.values.get("eval_size_n")) if counted_here else 0
    wrong_now = questions_wrong_now(recall, rows_on_file)
    if counted_here and wrong_now < floor:
        raise NotEnoughToPropose(
            f"This eval set cannot resolve any chunking difference. It holds "
            f"{rows_on_file} counted questions and your retriever scores "
            f"{recall}, so it gets {wrong_now} of them wrong - and those are the "
            "only rows a different chunk size could turn around. "
            f"{len(set(settings))} settings is {family} pairwise comparison(s), "
            f"corrected together at {RESOLVED_AT}, so the most lenient threshold "
            f"in the family is {RESOLVED_AT / max(1, family)}, which McNemar's "
            f"exact test cannot reach until {floor} questions change verdict "
            f"between two settings (evals.mcnemar({floor}, 0) = "
            f"{evals.mcnemar(floor, 0)}). Even a setting that fixed every "
            "question you currently get wrong would come back NO EVIDENCE. You "
            f"would need at least {rows_needed} questions at this recall and this "
            f"family size - {floor} / (1 - {recall}), rounded up - which is "
            f"{max(0, rows_needed - rows_on_file)} more than you have. Grading "
            "them is work; rebuilding the index "
            f"{len(set(settings))} times to learn nothing is more.",
            needs=(f"eval_size_n >= {rows_needed}",),
        )

    # WHAT THE SWEEP WILL BE CALLED WITH. Offered generously and filtered by the
    # tool's own schema, exactly as the retrieval bench's calls are - see
    # `_a_call_that_fits`. The corpus is offered under BOTH spellings this
    # repository uses for it, because `build_retrieval_index` calls it `path` and
    # this `Situation` calls it `corpus_path`; which one the sweep declares is
    # the sweep's business, and that at least one survives is this plan's.
    sweeping_offer: dict[str, Any] = {
        "path": corpus,
        "corpus_path": corpus,
        "eval_path": evaluation,
        "question_field": question_field,
        # EACH SETTING AS AN OBJECT, WHICH IS WHAT THE SCHEMA DECLARES ITS ITEMS
        # TO BE. Only `passage_chars` varies: `passage_overlap` is left to the
        # tool's own default so that the one thing this sweep changes is the one
        # thing it is about, which is the tool's stated reason for having a
        # sweep-wide overlap at all.
        "settings": [{"passage_chars": size} for size in sorted(set(settings))],
    }
    if passage_field:
        sweeping_offer["ground_truth_field"] = passage_field
    if depth > 0:
        sweeping_offer["k"] = depth
    planning = _a_call_that_fits(
        THE_CHUNKING_SWEEP,
        sweeping_offer,
        must_carry=("eval_path", "question_field", "settings"),
    )
    _at_least_one_of(
        planning,
        THE_CHUNKING_SWEEP,
        ("corpus_path", "path"),
        what="which corpus to rebuild the index over",
    )
    # THE SAME CALL WITH THE SWITCH ON. `run` is the tool's own word for "do it"
    # and its default is off, which is what makes a preflight a real step rather
    # than a rehearsal this file invented.
    running = _a_call_that_fits(
        THE_CHUNKING_SWEEP, {**sweeping_offer, "run": True}, must_carry=("run",)
    )

    steps: list[Step] = []

    attaching = {"path": corpus, "role": "the corpus the retriever fetches from"}
    steps.append(
        Step(
            id="attach",
            tool="attach_context",
            why=(
                "Record where the corpus is, so every index this sweep builds and "
                "every score it takes are about the same pile of documents rather "
                "than about paths that happen to look alike."
            ),
            arguments=attaching,
            produces=(
                Output(
                    "path",
                    "string",
                    "the path as the harness recorded it",
                    at="what_it_is.path",
                ),
            ),
            cost=_local_cost(
                "attach_context",
                find_out_by="it is one filesystem stat and one row written; time it once",
            ),
            exit_criterion=ExitCriterion(
                stated="the harness has the corpus path on file",
                source="tool_result",
                subject="ok",
                comparator="is_true",
            ),
            operates_on=corpus_subject,
        )
    )

    needs_for_preflight: tuple[str, ...] = ("attach",)
    if not counted_here:
        # THE COUNT IS WHERE THE REFUSAL ABOVE GOES WHEN IT CANNOT BE MADE YET,
        # AND ITS EXIT CRITERION IS THE FLOOR RATHER THAN `exact`. A finished
        # count is the usual criterion and it is the wrong one here: a finished
        # count of twelve rows is a step that worked and a sweep that cannot
        # conclude anything, and the storm would go on to spend the rebuilds.
        # `finish_the_count` is still passed, so a count that stopped early
        # reports fewer rows than the file holds and stops the plan - the safe
        # direction for a check that decides whether to spend hours.
        counting = {"path": evaluation, "finish_the_count": True}
        steps.append(
            Step(
                id="count",
                tool="measure_eval_set",
                why=(
                    "Count the eval set before rebuilding anything. The rows that "
                    "can change in a chunking comparison are the ones your "
                    f"retriever gets wrong - at {recall} recall that is a "
                    f"{1.0 - recall:.2f} share of them - and at this family size "
                    f"a paired test needs {floor} of them to move the same way "
                    "before it can separate anything at all. This step is what "
                    "decides whether the sweep below is worth running, before it "
                    "runs."
                ),
                arguments=counting,
                produces=(Output("rows", "integer", "the counted rows", at="rows"),),
                cost=_local_cost(
                    "measure_eval_set",
                    find_out_by=(
                        "the result carries the seconds the count took; run it "
                        "once and the rate is known for this machine"
                    ),
                ),
                exit_criterion=ExitCriterion(
                    stated=(
                        f"the eval set holds at least {rows_needed} questions. "
                        f"Below that the {floor} changed rows a paired test needs "
                        f"at this family size cannot exist, because at {recall} "
                        "recall only the questions you currently get wrong can "
                        f"move and there would be fewer than {floor} of them. "
                        f"Derived as {floor} / (1 - {recall}), rounded up; it is "
                        "what makes a difference POSSIBLE and never what makes "
                        "one likely"
                    ),
                    source="tool_result",
                    subject="rows",
                    comparator="at_least",
                    value=rows_needed,
                ),
                operates_on=_subject_of_a_call("measure_eval_set", counting)[0],
            )
        )
        needs_for_preflight = ("attach", "count")

    steps.append(
        Step(
            id="preflight",
            tool=THE_CHUNKING_SWEEP,
            why=(
                "Ask the sweep what it would do, before it does it. Without "
                "run=true it builds nothing and reports counts it took itself - "
                "how many indexes would be rebuilt, how many passages and "
                "posting rows would go into this project's database, how many "
                "retrievals it would run, and how many of your questions every "
                "setting could actually be scored on. Every wall-clock estimate "
                "in this plan is UNKNOWN because nothing here has ever timed "
                "this; this step is the plan's own answer to that, and it is the "
                "cheapest place to find out that the whole sweep is not worth "
                "starting."
            ),
            arguments=planning,
            produces=(
                Output(
                    "rebuilds",
                    "integer",
                    "how many indexes would be built, counted rather than estimated",
                    at="will_do.rebuilds",
                ),
                Output(
                    "questions_each_setting",
                    "integer",
                    "how many of your questions every setting could be scored on",
                    at="will_do.questions_each_setting_is_scored_on",
                ),
            ),
            needs=needs_for_preflight,
            cost=_retrieval_cost(
                THE_CHUNKING_SWEEP,
                find_out_by=(
                    "this step is itself the cheap answer: it counts what the "
                    "sweep would write without writing any of it"
                ),
            ),
            operates_on=_subject_of_a_call(THE_CHUNKING_SWEEP, planning)[0],
            exit_criterion=ExitCriterion(
                stated=(
                    f"every setting could be scored on at least {rows_needed} of "
                    "your questions - the point below which no pair could "
                    f"separate at all, because {floor} of them would have to "
                    f"change verdict and at {recall} recall there are not that "
                    "many that could. This is checked BEFORE anything is built, "
                    "so a sweep that could not conclude anything costs nothing"
                ),
                source="tool_result",
                subject="will_do.questions_each_setting_is_scored_on",
                comparator="at_least",
                value=rows_needed,
            ),
            risks=(
                Risk(
                    what=(
                        "one of the passage sizes you named is one the sweep will "
                        "not accept - it would cut this corpus into more passages "
                        "than an index may hold, or it is smaller than the "
                        "overlap the sweep would use, or an index of that name "
                        "already exists over different documents"
                    ),
                    what_we_do=(
                        "the sweep refuses at THIS step and nothing is built. "
                        "Every one of those is a property of your corpus and your "
                        "settings together, which this plan cannot check without "
                        "reading your documents, and the honest place to find out "
                        "is a step that writes nothing. A truncated index is not "
                        "the corpus, so comparing one against a whole one would "
                        "be comparing two different corpora - and that refusal "
                        "arriving here, before anything is written, is the reason "
                        "this step is in the plan at all"
                    ),
                ),
            ),
        )
    )

    steps.append(
        Step(
            id="sweep",
            tool=THE_CHUNKING_SWEEP,
            why=(
                "Rebuild the index at each of the "
                f"{len(set(settings))} passage sizes you named and score every "
                "one of them on the SAME eval set with the SAME ground truth, "
                "paired question by question. This is the one of the engine's "
                "four levers this harness owns. Nothing here decides that a "
                "setting is better: the "
                f"{family} pairwise comparison(s) are corrected together, and "
                "the answer is allowed to be - and on most eval sets will be - "
                "that these questions cannot tell your settings apart."
            ),
            arguments=running,
            produces=(
                Output(
                    "verdict",
                    "string",
                    "what the sweep concluded, including that it could conclude "
                    "nothing - which is an answer and not a failure",
                    at="verdict",
                ),
                Output(
                    "family_size",
                    "integer",
                    "how many pairwise comparisons were tested and corrected together",
                    at="family_size",
                ),
                Output(
                    "compared_questions",
                    "integer",
                    "the questions every setting scored - the only rows a "
                    "difference between them means anything on",
                    at="compared_questions",
                ),
            ),
            needs=("preflight",),
            cost=_retrieval_cost(
                THE_CHUNKING_SWEEP,
                find_out_by=(
                    "the step above counts what this one will write, without "
                    "writing it - and no duration is stated anywhere because "
                    "nothing on this machine has measured one"
                ),
            ),
            operates_on=_subject_of_a_call(THE_CHUNKING_SWEEP, running)[0],
            # `compared_questions` AND NOT `ok`, FOR THE REASON THE RECALL STEP
            # USES `stampable` AND NOT `ok`. This tool returns its refusals in
            # the SAME SHAPE as its answers - `ok: True`, every key present,
            # `verdict: "nothing_was_compared"` - so `ok is_true` passes on a run
            # that compared nothing, and `verdict exists` passes on it too,
            # because a refusal has a verdict. The field that separates them is
            # the number of questions every setting was scored on, and holding it
            # to the same floor the preflight was held to is what makes this
            # criterion about the comparison having been POSSIBLE rather than
            # about which way a number went. The sweep drops questions not every
            # setting could score and questions decided by a score tie, so this
            # is a smaller number than the eval file's row count and is the one
            # that matters.
            exit_criterion=ExitCriterion(
                stated=(
                    f"the comparison ran on at least {rows_needed} questions that "
                    "EVERY setting scored - after the sweep drops the ones some "
                    "setting could not score and the ones a score tie rather than "
                    "the retriever decided. A verdict alone is not enough here: "
                    "this tool reports a refusal in the same shape as an answer, "
                    "so a run that compared nothing still has a verdict"
                ),
                source="tool_result",
                subject="compared_questions",
                comparator="at_least",
                value=rows_needed,
            ),
            risks=(
                Risk(
                    what=(
                        "the sweep crowns whichever setting scored highest, and "
                        "the highest of several noisy estimates is biased upward "
                        "even when every setting is truly identical"
                    ),
                    what_we_do=(
                        "it crowns nothing - it reports the whole curve and the "
                        "set of settings nothing was shown to beat, which is a "
                        "set and not a winner - and it measures the bias rather "
                        "than asserting it, by choosing on half your questions "
                        "and looking the choice up on the other half. This build "
                        "then records none of it: nothing here stamps "
                        "retriever_recall_at_k, so no diagnosis is routed on a "
                        "maximum selected on the rows it is reported against"
                    ),
                ),
                Risk(
                    what=(
                        f"{family} comparison(s) at {RESOLVED_AT} apiece is a "
                        "real chance of at least one false separation"
                    ),
                    what_we_do=(
                        "the whole family is corrected together, so the most "
                        "lenient threshold in it is "
                        f"{RESOLVED_AT / max(1, family)} and no pair can separate "
                        f"until {floor} questions change verdict between the two "
                        "being compared. That number is why this plan states a "
                        "row floor before it runs rather than a disappointment "
                        "afterwards: "
                        + ", ".join(
                            f"{n} settings is {pairwise_comparisons(n)} "
                            f"comparison(s) and needs "
                            f"{discordant_rows_that_could_resolve(pairwise_comparisons(n))} "
                            "changed questions"
                            for n in (2, 4, 8)
                        )
                    ),
                ),
                Risk(
                    what=(
                        "rebuilding the index once per setting takes a long time "
                        "on a large corpus"
                    ),
                    what_we_do=(
                        "nothing here knows how long and this plan says so rather "
                        "than guessing - every wall-clock estimate in it is "
                        "UNKNOWN. The step above is the answer: it counts the "
                        "rebuilds, passages and posting rows this one would write, "
                        "without writing any of them"
                    ),
                ),
                Risk(
                    what=(
                        "your eval set names the right answer by PASSAGE rather "
                        "than by document"
                    ),
                    what_we_do=(
                        "the sweep refuses it. Changing passage_chars changes what "
                        "the passages ARE, so a passage key names a different piece "
                        "of text at every setting and the thing being looked for "
                        "would move with the thing being measured. "
                        "measure_retriever_recall accepts a passage-level column "
                        "happily for a single index, which is why this is worth "
                        "reading before you approve it rather than after"
                    ),
                ),
            ),
        )
    )

    egress = _egress_for([step.tool for step in steps])
    said = str(situation.result.say or "").strip()
    action = engine_node_says(_THE_BOTTLENECK_NODE, "action", situation.spec)
    stated = engine_exit_criterion(_THE_BOTTLENECK_NODE, situation.spec)

    # THE CRITERION, AND WHICH OF THE TWO CASES WE ARE IN, DECIDED BY READING THE
    # SPEC RATHER THAN BY REMEMBERING IT. Today the node states none. The day
    # somebody adds one, this build is held to what the engine wrote and says so
    # - which is the property the retrieval bench's criterion has and the reason
    # `engine_exit_criterion` exists at all.
    if stated:
        criterion = (
            f"{_THE_BOTTLENECK_NODE} states it as: {stated!r}. This build varies "
            "the one lever of the four the node names that this harness owns, so "
            "what it produces is to be read AGAINST that sentence rather than AS "
            "that sentence."
        )
    else:
        criterion = (
            f"{_THE_BOTTLENECK_NODE} DECLARES NO exit_criterion. It states an "
            "action and a say and nothing a build could be held to, so nothing "
            "below was taken from the engine and nothing was invented to stand "
            "in for it. WHAT IS DERIVED, AND FROM WHAT: the node's own condition "
            f"is `{condition}`, and the clause a chunking sweep could act on is "
            f"`retriever_recall_at_k < {bar}` - so the node stops firing at the "
            f"{bar} bar {_THE_RAG_CRITERION_NODE} states. THAT IS NOT THIS "
            "BUILD'S CRITERION, and why not is the point: chunking is one of the "
            "four levers the node names and the only one this harness owns, so a "
            "plan promising the bar would be promising the other three levers' "
            "work as well. WHAT THIS BUILD IS HELD TO INSTEAD: every pair of the "
            f"{len(set(settings))} settings you named was tested and corrected "
            f"together - {family} comparison(s) - over questions every setting "
            "scored. It is a criterion about the comparison having been possible "
            "and complete, and NOT about the direction a number moved: recall "
            "rising two points on ninety questions is inside the resolution, and "
            "a criterion that read as an improvement would be satisfied by noise."
        )

    because = (
        (f"{said} " if said else "")
        + f"The engine's instruction is: {action!r}. THIS HARNESS OWNS ONE OF "
        "THOSE FOUR. Passage size is a stated choice rather than a measured "
        "optimum - the index's own schema says so - so this build varies it "
        "across the settings you named, rebuilds, and scores each one on your "
        "own eval set, paired question by question. "
        + _the_levers_we_do_not_own()
        + " WHAT THIS CAN AND CANNOT SETTLE. Your retriever scores "
        f"{recall} against the {bar} bar, measured. "
        + (
            f"Your eval set holds {rows_on_file} counted questions, so "
            f"{wrong_now} of them are wrong today, and those are the only rows a "
            "different chunk size can turn around. "
            if counted_here
            else "Nobody has counted this eval file, so the step above counts it "
            "first. "
        )
        + f"{len(set(settings))} settings is {family} pairwise comparison(s) "
        f"corrected together at {RESOLVED_AT}, and at that family size no pair "
        f"can separate until {floor} questions change verdict between them - "
        f"which needs at least {rows_needed} questions at this recall. The plan "
        "checks that before it builds anything and again on the questions that "
        "actually survive pairing. THE SWEEP IS ALLOWED TO FIND NOTHING, and on "
        "most eval sets it will: NO EVIDENCE in those words is the answer, not a "
        "small win. AND THIS BUILD RECORDS NO NUMBER. The best of several noisy "
        "estimates is optimistic by construction and optimistic on the rows that "
        "chose it; the sweep measures that bias on a split half of your own "
        "questions rather than asserting it, and even so nothing here stamps "
        "retriever_recall_at_k - compare_chunkings declares measures=(), checked "
        "at registration, and measure_retriever_recall stays the only instrument "
        "for that fact. So this plan ends with a comparison and two questions "
        "rather than with a number the engine would route on. "
        + (
            "Nothing in this plan can leave the machine: not one step's tool "
            "declares a network read, so the sandbox declares no egress at all "
            "and Build.validate refuses any step that would need one."
            if not egress
            else "One step in this plan reaches your connected model, which is "
            "declared on the environment below where you can see it before you "
            "approve it."
        )
    )

    return Build(
        id=_THE_BOTTLENECK_BUILD["id"],
        title=_THE_BOTTLENECK_BUILD["title"],
        for_outcome=situation.outcome,
        because=because,
        steps=tuple(steps),
        environment=_sandbox(
            _THE_BOTTLENECK_BUILD["id"], corpus, evaluation, reason=egress
        ),
        exit_criterion=ExitCriterion(
            stated=criterion,
            source="outputs",
            subject="sweep.family_size",
            comparator="at_least",
            value=family,
        ),
        questions=(
            Question(
                ask=(
                    "Have you put a cross-encoder reranker in front of your "
                    "retriever's results?"
                ),
                why=(
                    "One of the four things the engine names, and this harness "
                    f"cannot do it with you. {_THE_BOTTLENECK_NODE}'s condition "
                    f"is `{condition}`, which stops holding only when "
                    "reranker_tried and query_rewriting_tried are both true and "
                    "you have the labelled pairs. reranker_tried is source: ask "
                    "and no tool here measures it, so nothing can watch you do it "
                    "and it is yours to say."
                ),
                fact="reranker_tried",
            ),
            Question(
                ask=(
                    "Have you tried rewriting the query before it reaches the "
                    "retriever?"
                ),
                why=(
                    "The engine's fourth lever, and the one that would send your "
                    "questions to the model you connected - a different "
                    "provenance from every step in this plan, which sends nothing "
                    "anywhere. query_rewriting_tried is source: ask with no tool "
                    "measuring it, so it is yours to do and yours to say."
                ),
                fact="query_rewriting_tried",
            ),
        ),
        risks=(
            Risk(
                what=(
                    "the sweep separates nothing, which on most eval sets is what "
                    "will happen"
                ),
                what_we_do=(
                    "that is the plan working and it is worth the rebuilds. It "
                    "says chunking is not your lever - one of four crossed off "
                    "with a measurement rather than an opinion - and it points at "
                    "the three that are yours. The alternative is a week on a "
                    "reranker for a corpus whose real problem was that the right "
                    "passage is not in it"
                ),
            ),
            Risk(
                what=(
                    "the right passage is simply not in the corpus for some of "
                    "your questions"
                ),
                what_we_do=(
                    "no chunk size finds a document that is not there, and the "
                    "sweep shows it as a floor every setting shares. That is the "
                    "cheapest way there is to learn that the next move is the "
                    "corpus rather than the retriever - before a fine-tune is "
                    "blamed for it"
                ),
            ),
        ),
        facts=dict(situation.origins),
    )


# ---------------------------------------------------------------------------
# THE TRAINING BUILD, AND THE HALF OF ITS CRITERION NOTHING HERE CAN TAKE.
#
# `TRAIN__LORA_SFT` is the outcome this product is named after and it was the
# emptiest one in the file. Nine TRAIN__ outcomes, zero builds: the harness was
# willing to say "do not train" and hand over a build for the cheaper thing,
# and when all five gates passed and the honest answer was TRAIN the
# conversation ended at the verdict. Every tool the run needs is registered -
# `find_models`, `read_model_config`, `can_this_machine_train`, `make_sandbox`,
# `run_in_sandbox`, `start_training`, `training_status` - and nobody had
# written the thing that assembles them.
#
# THE FIRST THING THAT ASSEMBLING THEM SETTLES IS THAT ONE PIECE IS MISSING,
# and it is the piece the whole build is FOR. Read `why_the_full_run_is_not_
# drawn` before anything else here: every tool in this harness that can score a
# model declares `providers` in its `reads`, a provider is a CONNECTION
# (`app/providers/__init__.py` declares two adapters, `openai-compatible` and
# `ollama`), and a LoRA adapter written into a run directory is neither. No
# registered tool loads one, merges one, converts one or serves one, and no
# shipped recipe declares kind `eval` or `convert`, so `run_in_sandbox` cannot
# be asked to score one either. **This harness can train an adapter and cannot
# measure what it trained.**
#
# WHICH DECIDES THE SHAPE OF THE BUILD RATHER THAN BEING A FOOTNOTE ON IT.
# `docs/THE_PROPOSAL_LOOP.md`: *"Every step is verified when it finishes,
# against the exit criterion the build declared before it ran. A step that
# cannot show it worked did not work."* The exit criterion for a fine-tune is
# the adapter BEATING THE MEASURED BASELINE on the person's own eval set by a
# margin those rows can resolve - "the loss went down" and "training finished"
# are the two sentences this product exists to refuse. So a build that ran the
# whole fine-tune would end holding an artifact nothing here can score, with
# "the run exited zero" as the only thing it could check. That is not the
# retrieval bench's situation, where the engine's criterion had two halves and
# the build measured one of them and said which: here the reachable fraction of
# the criterion is NONE of it, and the honest consequence of none is not to
# draw the step.
#
# SO THE BUILD RUNS THE PART THAT IS VERIFIABLE AND MEASURES THE THING NOBODY
# HAS EVER MEASURED. `S9_MINT_TRAIN_VERDICT`'s own `say` is *"Here is what is
# left, WHAT IT WILL COST, and how you will know if it worked"*, and its
# `requires_in_diagnosis` asks for `estimated_cost set, stamped with
# cost_provenance`. Every wall-clock estimate in this file is UNKNOWN because
# nothing in this harness has ever timed a training step on this machine - see
# `_wall_clock` - and `docs/THE_PROPOSAL_LOOP.md` names the answer to that
# exactly: *"a proposal that says 'I do not know how long this takes, let me
# run it on 1% and find out' is worth more than one that guesses."* This build
# is that sentence: check the card against the model's real geometry, check the
# split for leakage, make the disposable sandbox with the data snapshotted, and
# run the real recipe on a bounded slice of the real data so the seconds, the
# tokens per second and the peak VRAM are read off this card instead of
# imagined. What it hands back is a measured cost and a pipeline proved to run,
# and it says in as many words that it stops before the full fine-tune and why.
#
# AND NOTHING IN IT TOUCHES A GATE. A build downstream of a TRAIN verdict is
# downstream of five gates that already passed, and the one thing it may never
# do is make that verdict easier to reach. Not one step here runs a tool that
# `measures=` any fact any gate row reads: `measure_baseline`, `run_eval` and
# `profile_dataset` are all absent, which also happens to be the second reason
# the eval leg cannot be drawn - `run_eval` stamps `baseline_score` and
# `baseline_measured`, so scoring an adapter with it would file a real
# measurement of a DIFFERENT MODEL under the name G1 reads. That is the
# `eval_size_n` subject defect wearing a fine-tune costume, and it is worth
# knowing that even a served adapter would not close this without a tool that
# knows it is not measuring the baseline.

#: THE TOOLS THIS BUILD NAMES, fixed in one place so a step and a coverage
#: entry cannot disagree about what has to exist, exactly as
#: `THE_RETRIEVAL_TOOLS` and `THE_CHUNKING_TOOLS` are.
THE_TRAINING_TOOLS: tuple[str, ...] = (
    "inspect_hardware",
    "find_models",
    "read_model_config",
    "can_this_machine_train",
    "check_split_leakage",
    "make_sandbox",
    "run_in_sandbox",
)

#: The backend the engine's own hand-off names. `S9_MINT_TRAIN_VERDICT` says
#: *"Execution goes to a pinned backend - Unsloth, HF peft+trl, or MLX-LM"*,
#: and `recipes/hf-peft-lora/` is the one of those three this harness ships.
#: A name rather than a search, because which recipe a plan drives is a thing
#: the plan must say out loud before anybody approves it.
THE_LORA_RECIPE = "hf-peft-lora"

#: The kind of job the recipe is asked for. `app/jobspec.py` declares five and
#: refuses a kind the recipe itself does not declare, which is what makes the
#: check in `the_recipe_on_this_machine` a reading rather than a hope.
THE_TRAINING_KIND = "train"

#: WHAT EVERY SCORER IN THIS HARNESS READS, and the one word that decides this
#: whole build's shape. A tool that can score a model sends rows to a PROVIDER,
#: and a provider is a connection - `app/providers/__init__.py` declares
#: `openai-compatible` and `ollama` and nothing else. An adapter directory is
#: not a connection, so a tool that reads `providers` cannot be pointed at one.
THE_SCORING_READ = "providers"

#: Tools that read a connection WITHOUT scoring a model, each with the reason.
#: The roster below is derived off `reads` so a scorer registers itself, and
#: 2026-09-12 brought the first two tools that send text to a provider for
#: another purpose: `generate_rows` has the model WRITE rows for a task, and
#: `judge_rows` has it grade ROWS against a rubric - a reading of the rows,
#: not of the model. Listing them here rather than dropping `providers` from
#: their `reads` keeps the egress classification honest (`app/build.py`
#: counts `providers` as NETWORK) and keeps the training proposal's sentence
#: true: it names the tools that score a model, and says these two exist.
NOT_A_SCORER: dict[str, str] = {
    "generate_rows": "sends a task and seed rows to a connection so the model writes new rows; it grades nothing",
    "judge_rows": "sends generated rows to a connection so the model grades the ROWS against a rubric; the model is the judge, not the subject",
    "generate_tool_rows": "sends a real tool chain and its results to a connection so the model writes the question the chain answers; the registry ran the chain, the model grades nothing",
}

#: The job kinds that would have to exist before a recipe could score or
#: convert what it trained. Both are declared in `app/jobspec.KINDS`, and which
#: shipped recipe declares one is read rather than remembered - see
#: `recipes_that_could_score_an_adapter`.
THE_SCORING_KINDS: tuple[str, ...] = ("eval", "convert")

#: THE TOOL THAT CLOSED THE LOOP, and the name is the cross-lane contract in
#: the same sense `THE_RETRIEVAL_TOOLS` and `THE_TABULAR_TOOLS` are. It scores
#: an adapter WHERE IT WAS MADE - inside the sandbox whose pinned environment
#: did the training - which is the only place in this product that can, because
#: an adapter is a directory of weights and every other scorer here talks to a
#: connection.
THE_ADAPTER_SCORING_TOOLS: tuple[str, ...] = ("score_the_adapter",)

THE_ADAPTER_SCORER = THE_ADAPTER_SCORING_TOOLS[0]


def tools_that_score_an_adapter() -> tuple[str, ...]:
    """Registered tools that can score a model which is NOT a connected provider.

    THE THIRD ROSTER, AND IT EXISTS BECAUSE THE SENTENCE BUILT ON THE FIRST TWO
    WENT FALSE. `why_the_full_run_is_not_drawn` opened with *THE THING THAT
    WOULD SCORE THE ADAPTER DOES NOT EXIST IN THIS HARNESS* and computed that
    off two rosters - the tools that score through a connection, and the
    recipes that declare an evaluating kind. Both rosters stayed correct and
    the conclusion stopped being: `score_the_adapter` registered, it does not
    read `providers` (which is exactly why it can be pointed at an adapter), so
    it never appeared in the first roster, and the second roster's change made
    the sentence's own sub-clause true while the headline stayed false. A false
    headline in every training proposal, computed from two true readings.
    So there is a reading for the question the headline was actually asking.

    The `providers` check is what makes this a reading rather than a name
    lookup: a tool registered under this name that turned out to talk to a
    connection is NOT one of these, it is one of the others, and it would show
    up in `tools_that_score_a_model` instead.
    """
    found: list[str] = []
    for name in THE_ADAPTER_SCORING_TOOLS:
        spec = REGISTRY.get(name)
        if spec is None or THE_SCORING_READ in spec.reads:
            continue
        found.append(name)
    return tuple(sorted(found))


def the_adapter_scorer_is_registered() -> bool:
    return bool(tools_that_score_an_adapter())


def the_baseline_run_to_beat(thread_id: Any, evaluation: str) -> dict[str, Any] | None:
    """The completed eval run in this conversation that graded THIS eval file.

    **THE SCORING LEG IS A COMPARISON AND A COMPARISON NEEDS SOMETHING TO
    COMPARE AGAINST.** `score_the_adapter` declares `baseline_run_id` required
    and says why in its own schema: *its graded rows ARE the rows the adapter
    is scored on - that is what makes the comparison a comparison.* So the
    build cannot be drawn against a run that does not exist, and it may not be
    drawn against a run of a DIFFERENT FILE - which is the `eval_size_n`
    subject defect, in the one place where being wrong costs a GPU.

    Newest first, complete only, and matched on `Subject` so a relative path
    and an absolute one are the same file here exactly as they are in a cost
    check. `None` on anything unreadable, which is the safe direction: it
    decides whether a build stops at the trial, and a database this cannot read
    is not evidence that a baseline was measured.

    `measure_baseline` does not put a row in these tables - it scores and
    stamps and keeps no rows - so a person who measured their baseline that way
    has a MEASURED `baseline_score` and nothing here to pair against. That is
    not a defect in either tool and the build says so rather than refusing: it
    draws the trial and names `run_eval` as the one step that would unlock the
    comparison.
    """
    try:
        wanted = Subject.of_path(evaluation).key
    except (build.CostError, build.BuildInvalid):  # pragma: no cover - no path
        return None
    try:
        thread = int(thread_id)
    except (TypeError, ValueError):
        return None
    if thread <= 0:
        return None
    try:
        rows = evals.runs_in(thread)
    except Exception:  # noqa: BLE001 - no tables, no database, no answer
        return None
    for row in rows:
        try:
            report = evals.read(int(row["id"]))
        except Exception:  # noqa: BLE001 - a row this cannot read is not a baseline
            continue
        if not report.get("ok") or not report.get("complete"):
            continue
        # AND A SANDBOX ARM IS NOT A BASELINE. `score_the_adapter` keeps the
        # adapter's and the base model's graded rows in these same tables -
        # correctly, because that is where graded rows live - so after one
        # scoring run the newest complete run over this file is the ADAPTER'S
        # OWN. Measured on a scratch database: this function returned it, at
        # its own score, and the next training build would have planned a
        # fine-tune against the last fine-tune while calling it the person's
        # measured baseline and printing the connection it was supposedly
        # measured through. `evals.was_measured_through_a_connection` reads the
        # mark that arm was written with.
        if not evals.was_measured_through_a_connection(report):
            continue
        try:
            same = Subject.of_recorded_path(
                str(report.get("eval_path") or ""),
                how=f"the eval file eval run {report['run_id']} graded",
            ).key
        except (build.CostError, build.BuildInvalid):  # pragma: no cover
            continue
        if same == wanted:
            return report
    return None


def training_tools_missing() -> tuple[str, ...]:
    """Which of them are not registered in this process, right now.

    Read off the live registry every time, for `retrieval_tools_missing`'s
    reason: a table that answered this once at import would state the opposite
    of the truth for as long as it took somebody to notice.
    """
    return tuple(name for name in THE_TRAINING_TOOLS if REGISTRY.get(name) is None)


def the_training_bench_is_registered() -> bool:
    return not training_tools_missing()


def tools_that_score_a_model() -> tuple[str, ...]:
    """Every registered tool that can put text in front of a model and grade it.

    Read off `reads` rather than off a list of names, so a scorer added next
    week is in here on the day it registers. It is the first half of
    `why_the_full_run_is_not_drawn` and the first half of that function's
    canary: the sentence names this roster, so the roster growing changes the
    sentence and turns
    `tests/test_a_trained_adapter_is_measured_or_not_trained.py` red rather
    than leaving a false claim in every training proposal.
    """
    return tuple(
        sorted(
            spec.name
            for spec in REGISTRY
            if THE_SCORING_READ in spec.reads and spec.name not in NOT_A_SCORER
        )
    )


def recipes_that_could_score_an_adapter() -> tuple[str, ...]:
    """Shipped recipes declaring a kind that could evaluate or convert a model.

    The second half of the same question, asked of the other half of the
    product. `run_in_sandbox` takes a `kind` and `app/jobspec.py` refuses one
    the recipe does not declare, so "could the sandbox score it" is decided by
    what the recipe files on disk say and by nothing else.

    Empty on any failure to read, which is the safe direction here: it decides
    whether a build STOPS, and a recipe this cannot parse is not evidence that
    something can score an adapter.
    """
    from app import jobspec  # local: a proposer must not need the job layer to import

    found: list[str] = []
    try:
        names = jobspec.available_recipes()
    except Exception:  # noqa: BLE001 - a recipes directory the OS will not list
        return ()
    for name in names:
        try:
            recipe = jobspec.load_recipe(name)
        except Exception:  # noqa: BLE001 - an unreadable recipe.toml
            continue
        if set(recipe.kinds) & set(THE_SCORING_KINDS):
            found.append(name)
    return tuple(sorted(found))


def why_the_full_run_is_not_drawn() -> str:
    """The sentence that decides this build's shape, computed off this process.

    NOT A CONSTANT, for `_RETRIEVAL_NOT_HERE_YET`'s reason and one more. It
    names the two rosters it read - the tools that can score a model and the
    recipes that could evaluate or convert one - so the day either changes the
    sentence changes with it instead of staying true-sounding and wrong. And it
    is stated as a FINDING rather than wired to a switch: a function returning
    "" the moment an instrument appeared would silently drop the explanation
    from a build that still stops, which is the worst of both. The canary is a
    test over these two rosters, so an adapter scorer arriving turns the suite
    red and somebody re-reads this rather than assuming.
    """
    scorers = tools_that_score_a_model()
    evaluating = recipes_that_could_score_an_adapter()
    in_place = tools_that_score_an_adapter()
    connections = (
        "Every tool here that scores a model through a CONNECTION - "
        + (", ".join(scorers) if scorers else "and there are none registered")
        + " - declares `"
        + THE_SCORING_READ
        + "` in its reads, which means it sends your rows to one. app/providers "
        "declares two kinds of connection, an OpenAI-compatible endpoint and "
        "Ollama, and a LoRA adapter written into a run directory is neither, so "
        "not one of them can be pointed at an adapter. "
        + (
            "Two more tools send rows to a connection without scoring a model - "
            + ", ".join(sorted(NOT_A_SCORER))
            + " - and are not counted here for that reason. "
            if NOT_A_SCORER
            else ""
        )
    )
    if not in_place:
        return (
            "THE THING THAT WOULD SCORE THE ADAPTER DOES NOT EXIST IN THIS "
            "HARNESS, and that is why this plan stops where it stops rather "
            "than running the whole fine-tune. " + connections + "Nothing "
            "registered here loads one, merges one, converts one or serves "
            "one. The sandbox cannot be asked either - "
            + (
                "no recipe this harness ships declares kind "
                + " or ".join(repr(kind) for kind in THE_SCORING_KINDS)
                if not evaluating
                else "the recipes that declare one are "
                + ", ".join(evaluating)
                + ", and no registered tool drives one"
            )
            + ", and run_in_sandbox refuses a kind the recipe did not declare. "
            "So a build that ran the fine-tune to the end would hand you an "
            "adapter and nothing that could say whether it is better than what "
            "you already have, with 'the run exited zero' as the only thing "
            "anybody could check. That is the sentence this product exists to "
            "refuse, so the run is not drawn."
        )
    return (
        "THE THING THAT WOULD SCORE THE ADAPTER NOW EXISTS, and this sentence "
        "is what it used to say. " + connections + "That half has not moved "
        "and it is exactly why the thing that CAN score one is not on that "
        "list: "
        + ", ".join(in_place)
        + " does not read `"
        + THE_SCORING_READ
        + "` at all, because there is no connection in its path - it scores "
        "the adapter WHERE IT WAS MADE, inside the sandbox whose pinned "
        "environment did the training, on the rows a completed eval run "
        "already graded, with the same grader that graded them. "
        + (
            "The recipe half is what unblocked it: "
            + ", ".join(evaluating)
            + " declares an evaluating kind, and run_in_sandbox refuses a kind "
            "the recipe did not declare, which was the whole blocker. "
            if evaluating
            else "No shipped recipe declares an evaluating kind, so "
            "run_in_sandbox cannot be asked for one and that scorer cannot "
            "run. "
        )
        + "So the fine-tune and the comparison against your measured baseline "
        "are a build, and whether THIS run gets it turns on one more thing "
        "that is about your conversation rather than about the harness: there "
        "has to be a completed eval run for the adapter to be compared "
        "against, because its graded rows ARE the rows the adapter is scored "
        "on."
    )


def the_recipe_on_this_machine(recipe: str = "") -> dict[str, Any]:
    """What a recipe IS here: pinned or not, and what it locks.

    TAKES A NAME NOW, AND THE DEFAULT IS STILL `hf-peft-lora`. Two builds ask
    this question - the SFT one and the preference one - and each names its own
    backend, because which recipe a plan drives is the thing the plan must say
    out loud. A second copy of this function would be a second opinion about
    whether an environment on this machine has been built, which is the one
    thing the docstring below exists to prevent.

    `app/tools/sandbox.pin` already answers this - the venv, its interpreter,
    the Python version out of the venv's own `pyvenv.cfg`, and the lockfile's
    lines - and asking it is what stops this file holding a second opinion
    about whether an environment on this machine has been built. Imported
    inside the function on purpose: this module is imported last and must keep
    importing when a sibling does not, which is the same rule
    `RESOLVED_AT` is pinned by a test rather than imported for.

    An unreadable answer comes back as `pinned: False` with the reason, and the
    proposer refuses on it - the safe direction, because the alternative is a
    plan that names a pinned environment that is not there.
    """
    wanted = str(recipe or "").strip() or THE_LORA_RECIPE
    try:
        from app.tools import sandbox as sandboxes

        return dict(sandboxes.pin(wanted))
    except Exception as unreadable:  # noqa: BLE001 - an absent or broken recipe
        return {
            "recipe": wanted,
            "pinned": False,
            "kinds": [],
            "installs": (),
            "python": "",
            "why": (
                f"{wanted} could not be read on this machine: "
                f"{type(unreadable).__name__}: {unreadable}"
            ),
        }


def sandboxes_already_holding(path: str) -> tuple[str, ...]:
    """Sandboxes on this machine whose snapshot is a copy of THIS file.

    "AN ADAPTER ALREADY TRAINED ON THIS DATA", asked of the record this harness
    actually keeps. A sandbox's manifest records every file it snapshotted, by
    path, so the question is decidable without guessing - and `list_sandboxes`
    says in its own description why it matters: *use it before making another
    one, so an experiment is resumed rather than duplicated.*

    Matched on the path key `app/build.py` uses for every other subject, so a
    relative path and an absolute one are the same file here exactly as they
    are in a cost check. Empty on any failure to read, which is the safe
    direction: this decides a REFUSAL, and a directory the OS would not list is
    not evidence that a run already happened.
    """
    try:
        from app.tools import sandbox as sandboxes

        wanted = Subject.of_path(path).key
        found: list[str] = []
        for row in sandboxes.every():
            for snapshot in row.get("snapshotted") or ():
                held = str((snapshot or {}).get("path") or "")
                if not held:
                    continue
                try:
                    same = Subject.of_recorded_path(
                        held, how="recorded in a sandbox manifest"
                    ).key
                except (build.CostError, build.BuildInvalid):  # pragma: no cover
                    continue
                if same == wanted:
                    found.append(str(row.get("name") or ""))
                    break
        return tuple(name for name in found if name)
    except Exception:  # noqa: BLE001 - no sandbox module, no sandbox root, no answer
        return ()


#: THE NODE THIS BUILD IS HELD TO. One node mints every training verdict and
#: `TRAIN__LORA_SFT` is one of the nine it emits, so which node speaks for the
#: outcome is the file's answer rather than this module's preference.
_THE_MINT = "S9_MINT_TRAIN_VERDICT"

#: What a comparison of the adapter against the baseline would be: ONE paired
#: test, over the rows both runs graded. Not a family - there is one challenger
#: and one champion - so the correction the chunking sweep needs does not apply
#: and the floor is the smallest one there is.
_ONE_COMPARISON = 1


def engine_requires_in_diagnosis(
    node: str, spec: diagnosis.Spec | None = None
) -> tuple[str, ...]:
    """The `requires_in_diagnosis:` lines a node declares, verbatim.

    `engine_node_says` stringifies, which turns a list into its repr and would
    put `["rejected[] non-empty - ...", ...]` into a proposal. The mint's list
    is the closest thing the engine has to a contract for a TRAIN verdict and
    one of its four lines is about the exit criterion, so it is read as the
    list it is.
    """
    current = spec or diagnosis.default_spec()
    row = current.node_index.get(str(node or "")) or {}
    declared = row.get("requires_in_diagnosis")
    if isinstance(declared, str):
        declared = [declared]
    if not isinstance(declared, (list, tuple)):
        return ()
    return tuple(str(line).strip() for line in declared if str(line).strip())


def the_criterion_the_engine_owes(spec: diagnosis.Spec | None = None) -> str:
    """The mint's own line about the exit criterion, quoted or honestly absent.

    Read rather than typed, for `g0_minimum`'s reason. The mint declares no
    `exit_criterion:` of its own - it declares that a diagnosis carrying this
    verdict must SET one - and the difference between those two is the whole
    difficulty of this build, so the sentence is fetched from the file instead
    of being paraphrased here.
    """
    for line in engine_requires_in_diagnosis(_THE_MINT, spec):
        if line.lower().startswith("exit_criterion"):
            return line
    return ""


def _the_method_for(route: str) -> str:
    """The `find_models`/`can_this_machine_train` method word, or "" for no.

    `S9_HARDWARE_ROUTER` sets `route` from the spec's own VRAM table and the
    recipe this build drives holds the base model at LoRA precision - it
    attaches a `LoraConfig` to a model loaded normally and quantises nothing,
    which is read out of `recipes/hf-peft-lora/entrypoint.py` rather than
    assumed. So the fit question is asked at `lora` for the two routes where
    the card can hold a base model at that precision, and QLORA is the route
    where the engine's table says it cannot - which is a real answer and not
    this build's to talk its way past.
    """
    if route in ("LORA", "FULL_FT"):
        return "lora"
    return ""


#: WHAT THIS BUILD IS, AND THERE ARE TWO OF THEM NOW. One outcome, one node,
#: one recipe - and two builds behind it, exactly as `BLOCKED__BUILD_EVAL_SET`
#: has two, decided by reading rather than by asking. Which one a person gets
#: turns on whether there is a completed eval run for the adapter to be scored
#: against; both are named here so a step, a title and a coverage entry cannot
#: drift into describing different plans.
_THE_TRAINING_BUILD = {
    "id": "lora_trial_run",
    "title": "Run the fine-tune on a slice, and measure what the whole of it would cost",
}

_THE_SCORED_TRAINING_BUILD = {
    "id": "lora_run_and_score",
    "title": "Fine-tune, then score the adapter against the baseline you measured",
}


def _why_this_run_cannot_be_scored(
    situation: Situation, eval_subject: Subject, too_small: str = ""
) -> str:
    """Why THIS run stops at the trial, when the instrument itself exists.

    THREE ABSENCES NOW, AND `too_small` IS THE THIRD. A completed run over this
    file can exist and still be no use: if it graded few enough rows that even
    an adapter fixing every one it got wrong could not reach McNemar's floor,
    the comparison would come back NO EVIDENCE whatever the training did. The
    caller works that out - it has the arithmetic - and hands the sentence in,
    because "there is no such run" would be a false statement about a
    conversation that has one.

    TWO DIFFERENT ABSENCES AND THEY ARE NOT THE SAME NEWS.
    `why_the_full_run_is_not_drawn` answers about the HARNESS - is there a tool
    that can score an adapter at all - and it is the same answer for everybody.
    This one answers about the CONVERSATION, and it is the sentence that used
    to be impossible to write: the instrument is here, and your run has nothing
    for it to compare against.

    It is a real distinction rather than a nicety, and it is the one
    `_why_carving_is_not_honest_here` had to learn in the other direction: "no
    tool ships" reads as *wait for us*, and "run_eval on this file first" is a
    thing a person can go and do in the next minute. Telling somebody the first
    when the second is true is telling them to wait for something that already
    arrived.
    """
    if not the_adapter_scorer_is_registered():
        return (
            "The tool that would score it is not registered in this process: "
            f"{list(name for name in THE_ADAPTER_SCORING_TOOLS if REGISTRY.get(name) is None)} "
            f"of {list(THE_ADAPTER_SCORING_TOOLS)} are missing."
        )
    if too_small:
        return too_small
    return (
        "THE INSTRUMENT IS HERE AND YOUR CONVERSATION HAS NOTHING FOR IT TO "
        "COMPARE AGAINST, which is a different sentence from the one this "
        "build used to carry and is one you can act on today. "
        + ", ".join(tools_that_score_an_adapter())
        + " scores an adapter on the rows a COMPLETED EVAL RUN already graded - "
        "its schema says why in as many words: those graded rows ARE the rows "
        "the adapter is scored on, and that is what makes the comparison a "
        f"comparison. There is no such run in this conversation over "
        f"{eval_subject.key}"
        + (
            ""
            if _an_integer(situation.thread_id) > 0
            else ", and nothing here even knows which conversation this is - "
            "the thread comes from the instrument, and a Situation assembled "
            "without one cannot be asked the question"
        )
        + ". A measured baseline_score is not the same thing: measure_baseline "
        "scores and stamps and keeps no rows, so a baseline measured that way "
        "clears G1 and leaves nothing to pair against. run_eval keeps every "
        "row it graded, and one run of it over this file is the whole of what "
        "stands between this plan and the comparison the verdict is actually "
        "about."
    )


def _hub_cost(name: str, *, find_out_by: str) -> Cost:
    """One Hub-reading step's cost. Zero of the user's tokens, provably.

    NOT `_retrieval_cost` AND NOT A NEW OPINION. The token and request
    dimensions of a `Cost` are about the model the person connected, and a tool
    that reads `huggingface_hub` sends nothing to it - which is provable off
    `reads` and is exactly what `_model_cost_of_a_local_tool` says. What is
    different from a local tool is that this one does leave the machine, and
    that is carried where a person can act on it: the environment's egress
    reason, which `Build.validate` checks against these same declarations.
    """
    tokens, requests = _model_cost_of_a_local_tool(name)
    return Cost(
        model_tokens=tokens,
        model_requests=requests,
        wall_clock=_wall_clock(name, find_out_by=find_out_by),
        disk=_disk_cost(name),
    )


def _egress_for_the_hub(tools: list[str], *, weights: bool) -> str:
    """Why this sandbox may reach the network - and it is a different why.

    `_egress_for` writes one sentence and it is about `providers`: *your
    documents and your eval rows go to the model you connected.* Not one step
    in this build reads `providers`, and reusing that sentence would put a
    false claim about somebody's data into the one field they are supposed to
    read before approving. What is true here is smaller and has to be said
    exactly: two steps ask huggingface.co about a model, and the training run
    fetches that model's weights the first time - which is also why this
    sandbox cannot be a no-egress one, because `app/tools/sandbox.py` sets
    HF_HUB_OFFLINE in those and the run would refuse rather than download.
    """
    reaching = sorted(
        {read for name in tools for read in set(_spec(name).reads) & build.NETWORK_READS}
    )
    if not reaching and not weights:  # pragma: no cover - a build with no Hub step
        return ""
    return (
        "this plan reaches huggingface.co and nothing else. "
        + (
            "The steps that declare it read " + repr(reaching) + ", which is a "
            "request for one model's public metadata and its config.json - your "
            "rows are not in it. "
            if reaching
            else ""
        )
        + (
            "And the trial run downloads the base model's weights the first "
            "time, which is what makes this sandbox an egress one: a no-egress "
            "sandbox sets HF_HUB_OFFLINE and TRANSFORMERS_OFFLINE, so the run "
            "would refuse rather than fetch. The cost of declaring it is stated "
            "by the sandbox itself - an egress sandbox is handed this harness's "
            "address and token, where a no-egress one is handed neither. "
            if weights
            else ""
        )
        + "No step in this plan declares `"
        + THE_SCORING_READ
        + "`, so none of your rows goes to the model you connected."
    )


def _propose_train_the_adapter(situation: Situation) -> Build:
    """`TRAIN__LORA_SFT` - the flagship verdict, and the first build under one.

    **THE EXIT CRITERION IS THE WHOLE OF THIS AND IT IS AN HONESTY PROBLEM.**
    `S9_MINT_TRAIN_VERDICT` declares no `exit_criterion:` - like
    `S3_RETRIEVAL_IS_THE_BOTTLENECK`, and unlike `S3_BUILD_RAG` - and what it
    declares instead is that a diagnosis carrying this verdict must SET one.
    That is read off the spec every time rather than believed: the day the mint
    states a criterion, this build is held to it and says so, and until then it
    says the engine declared none, quotes the line that says one is owed, and
    names what it checks instead.

    What the criterion for a fine-tune actually is, is not in doubt and is not
    something this file gets to soften: the adapter beats the measured baseline
    on the person's own eval set, by a margin those rows can resolve.
    "Training finished" and "the loss went down" are the two sentences
    `app/tools/evals.py` exists to refuse, and a build whose success condition
    cannot tell a real gain from noise has declared victory in advance.

    **AND NOTHING IN THIS HARNESS CAN TAKE THAT MEASUREMENT.** See
    `why_the_full_run_is_not_drawn`, which computes it off two rosters rather
    than asserting it. So the full run is not a step here. This build proves
    the machine can hold the model, proves the split does not leak, makes the
    disposable sandbox, and runs the real recipe over a bounded slice of the
    real data so that the seconds and the peak VRAM are read off this card -
    turning the one estimate this whole file has never been able to make into a
    measured number. `docs/THE_PROPOSAL_LOOP.md` calls that worth more than a
    guess, and it is also the second of the three things the mint's own `say`
    promises: what is left, WHAT IT WILL COST, and how you will know.

    **FIVE THINGS THIS BUILD REFUSES, EACH COMPUTED RATHER THAN ASSUMED.**

    1. **It will not pick the model.** `find_models` ranks candidates for this
       card and this method, and which one to fine-tune carries a licence
       decision and a "what is your product" decision that are not this file's.
       Same refusal as the prompt and the chunk settings, same reason.
    2. **It will not pick the example length.** One number sets the activation
       and logits terms, which are most of what moves in the memory budget AND
       what the trial's timing is a measurement of. A fit answer computed at
       one length beside a run executed at another is two facts about two
       different runs, which is `evals.compare`'s first refusal in a memory
       costume.
    3. **It refuses when the eval set could not resolve the improvement.** The
       rows that can change are at most the rows the baseline gets wrong, and a
       paired test needs a floor of them to move one way before it can reach
       0.05 at all. When that floor is out of reach the fine-tune could not be
       shown to have worked even if it worked, and the row count that would fix
       it is arithmetic - the same arithmetic `_propose_fix_the_retriever` uses,
       through the same three functions, asked of one comparison instead of a
       family.
    4. **It refuses when the eval set is inside the training data.** Training
       on the rows the comparison is measured against does not degrade the
       comparison, it removes its meaning - and the resulting number is exactly
       the number a person would quote as proof the fine-tune worked.
    5. **It refuses when a sandbox on this machine already holds this file.**
       That is "an adapter already trained on this data" asked of the record
       the harness keeps, and the answer is to resume or delete rather than to
       make a second copy of somebody's data and a second pinned environment.
    """
    missing = training_tools_missing()
    if missing:
        raise NotEnoughToPropose(
            "The training build is not drawable in this harness: "
            f"{list(missing)} of {list(THE_TRAINING_TOOLS)} are not registered "
            "tools. The plan for this outcome is written and it will not be "
            "drawn against tools that do not exist, because a step naming a "
            "tool nobody registered is a plan that fails after you approved it.",
            needs=tuple(missing),
        )

    # REFUSAL: THE BACKEND THE ENGINE HANDS OFF TO IS NOT BUILT HERE. The mint
    # says execution goes to a pinned backend; a recipe whose virtualenv has
    # not been materialised is not a pin, its own entrypoint refuses to train
    # in it, and `make_sandbox` would report `pinned: false` on a sandbox this
    # plan calls reproducible. Read off this machine rather than assumed.
    recipe = the_recipe_on_this_machine()
    if not recipe.get("pinned") or THE_TRAINING_KIND not in (recipe.get("kinds") or ()):
        raise NotEnoughToPropose(
            f"The {THE_LORA_RECIPE} backend is not ready on this machine, so "
            "there is nothing here to drive. "
            + (
                str(recipe.get("why") or "")
                or f"It declares kinds {list(recipe.get('kinds') or ())}, which "
                f"does not include {THE_TRAINING_KIND!r}."
            )
            + " list_recipes reports what each backend needs and prints the "
            "exact commands to build its environment. A plan that named an "
            "unbuilt environment would be a plan whose own recipe refuses it "
            "after you approved it.",
            needs=(f"the {THE_LORA_RECIPE} pinned environment",),
        )

    # REFUSAL: I WILL NOT PICK THE MODEL, AND IT IS NOT A GAP.
    base_model = str(situation.base_model or "").strip()
    if not base_model:
        raise NotEnoughToPropose(
            "I can plan the fine-tune and I will not choose what to fine-tune. "
            "Give me base_model - a Hugging Face repo like 'Qwen/Qwen3-4B'. "
            "find_models ranks candidates by how well they fit THIS card at "
            "this method and this example length, and returns every model it "
            "threw out with the reason, so the ranking is help rather than a "
            "decision. The decision is yours because it carries a licence and a "
            "commitment about what your product is, and this file picking one "
            "would be an experiment nobody chose.",
            needs=("base_model",),
        )

    # REFUSAL: I WILL NOT PICK THE EXAMPLE LENGTH EITHER, AND FOR A SHARPER
    # REASON THAN THE MODEL. Every tool here that could default it defaults to
    # a DIFFERENT number - `can_this_machine_train` budgets against its own and
    # says so, the recipe against its own - so leaving it out does not mean
    # "the tools agree", it means the fit answer and the run are two different
    # runs and the plan would be pricing one and executing the other.
    length = max(0, _an_integer(situation.max_seq_len))
    if length <= 0:
        raise NotEnoughToPropose(
            "I need max_seq_len: how many tokens long a training example is. "
            "This one number sets the activation and logits terms, which are "
            "most of what moves in the memory budget, and it is also what the "
            "trial below measures its seconds against. Left out, the fit check "
            "and the run would take it from two different defaults - a memory "
            "answer computed at one length beside a run executed at another is "
            "two facts about two different runs, not a plan. Look at your own "
            "rows with preview_dataset_rows and pass the length you are "
            "actually going to train at.",
            needs=("max_seq_len",),
        )

    training = situation.require_path("dataset_path")
    evaluation = situation.require_path("eval_path")

    training_subject = Subject.of_path(training)
    eval_subject = Subject.of_path(evaluation)

    # REFUSAL: THE EVAL SET IS THE TRAINING SET, OR IS INSIDE IT. The retrieval
    # bench's refusal, asked about the pair that matters here. Training on the
    # rows the comparison is measured against does not weaken the comparison,
    # it deletes its meaning - and the number that comes back is high, which is
    # exactly the number somebody would show as proof the fine-tune worked.
    # `check_split_leakage` is a step below and it is the row-level version of
    # this; this is the version that does not need to open either file.
    inside = _the_eval_set_is_inside(evaluation, training)
    if training_subject.key == eval_subject.key or inside:
        raise NotEnoughToPropose(
            (
                f"Your training data and your eval set are the same file "
                f"({training_subject.key})."
                if training_subject.key == eval_subject.key
                else f"Your eval set is inside the training data you asked me "
                f"to train on: {eval_subject.key} is under "
                f"{training_subject.key}."
            )
            + " Then the adapter is scored on rows it was trained on, and the "
            "number that comes back measures recall of the training set rather "
            "than anything about your task. It comes back high whatever the "
            "fine-tune did, and it is the number a person would show as proof "
            "it worked. Point dataset_path at what the model learns from and "
            "eval_path at what it is judged on, and keep them apart.",
            needs=("dataset_path", "eval_path"),
        )

    # REFUSAL: THE RECIPE READS JSONL AND NOTHING ELSE. `load_rows` opens the
    # file line by line and refuses a row that is not a JSON object; a folder or
    # a CSV is a step that fails at minute one, having taken the slot.
    #
    # AFTER THE LEAK CHECK ABOVE AND NOT BEFORE IT, which is the difference
    # between a refusal somebody can act on and a true sentence about the wrong
    # thing. A folder holding both files fails BOTH tests, and the one worth
    # telling them about is the leak: "convert it to JSONL" sends a person off
    # to convert a directory whose real problem is that the answers are in it.
    if Path(training).suffix.lower() != ".jsonl":
        raise NotEnoughToPropose(
            f"{training_subject.key} is not a .jsonl file, and "
            f"{THE_LORA_RECIPE} reads its training data as JSONL - one JSON "
            "object per line, holding the training text or a prompt/completion "
            "pair. Convert it first; a step that fails on the format at minute "
            "one has still taken the slot and still needed an approval.",
            needs=("dataset_path",),
        )

    # REFUSAL: NO EVAL SET TO VERIFY AGAINST - AND "MEASURED" IS A CLAIM ABOUT
    # A FILE RATHER THAN ABOUT A NUMBER. G0 passed to get here, so some
    # eval_size_n is on file and above the threshold; that says nothing about
    # WHICH file was counted, and a count of some other file is the defect this
    # module spent a milestone removing.
    counted_here, counted_of = a_measurement_of(situation, "eval_size_n", evaluation)
    if not counted_here:
        raise NotEnoughToPropose(
            "The eval set this fine-tune would be judged on has not been "
            "counted. "
            + (
                f"What is on file is a count of {counted_of.key}, and that is "
                f"not {eval_subject.key}"
                if counted_of is not None
                else "eval_size_n is on file as "
                f"{situation.values.get('eval_size_n')!r} and nothing recorded "
                "which file it counted"
            )
            + ". Everything below turns on it: whether these rows could resolve "
            "an improvement at all is arithmetic on the row count and the "
            "baseline, and a fine-tune planned against a count of a different "
            "file is hours of GPU planned against nothing. Run measure_eval_set "
            "on this file and ask again.",
            needs=("eval_size_n", "eval_path"),
        )
    # AND A COUNT WITH NO NUMBER IN IT IS NOT A COUNT, for the reason the
    # baseline below gets the same guard: `_an_integer` answers 0 for anything
    # it cannot read, and a 0 here would flow into the arithmetic and print
    # "your baseline scores 0.55 on the 0 rows counted" beside a refusal derived
    # from it. Zero rows is also a real state and the same answer: there is
    # nothing to judge a fine-tune on.
    rows = _an_integer(situation.values.get("eval_size_n"))
    if rows <= 0:
        raise NotEnoughToPropose(
            "The harness records eval_size_n as a measured count of "
            f"{eval_subject.key} and holds no usable number for it: the value on "
            f"file is {situation.values.get('eval_size_n')!r}. Every figure in "
            "this plan about what your eval set could resolve is arithmetic on "
            "that count, so there is nothing to compute and nothing will be "
            "made up to stand in for it. Run measure_eval_set on this file and "
            "ask again.",
            needs=("eval_size_n",),
        )

    # REFUSAL: NO MEASURED BASELINE TO BEAT. Two numbers from two instruments
    # are two facts and not a difference - `evals.compare`'s first refusal, and
    # the reason G1 exists at all. A baseline somebody typed cannot be the
    # thing an adapter is shown to have beaten.
    if not situation.is_measured("baseline_score"):
        raise NotEnoughToPropose(
            "The baseline this fine-tune would have to beat was stated rather "
            "than measured: baseline_score is on file as "
            f"{situation.values.get('baseline_score')!r} with origin "
            f"{situation.origin('baseline_score') or 'nothing recorded'}. An "
            "adapter beating a number nobody read is not a comparison, it is "
            "two facts. measure_baseline scores your own model on your own eval "
            "set and records what it read; then there is something to beat.",
            needs=("a measured baseline_score",),
        )
    try:
        score = float(situation.values["baseline_score"])
    except (KeyError, TypeError, ValueError):
        raise NotEnoughToPropose(
            "The harness records baseline_score as measured and holds no number "
            f"for it: the value on file is "
            f"{situation.values.get('baseline_score')!r}. Every figure in this "
            "plan about what your eval set could resolve is arithmetic on that "
            "score, so there is nothing to compute and nothing will be made up "
            "to stand in for it.",
            needs=("baseline_score",),
        ) from None

    # REFUSAL: THIS EVAL SET COULD NOT SHOW THE FINE-TUNE WORKED.
    #
    # The same three functions the chunking sweep uses, asked of ONE comparison
    # rather than a family: the rows that can move in the winning direction are
    # at most the rows the measured baseline gets wrong, and a two-sided exact
    # McNemar over them cannot reach 0.05 until a floor of them change the same
    # way. Below that floor a real improvement and no improvement produce the
    # same verdict - NO EVIDENCE, in those words - so the fine-tune could not be
    # shown to have worked even if it did, and hours of GPU buy a sentence that
    # was available before it ran.
    floor = discordant_rows_that_could_resolve(_ONE_COMPARISON)
    wrong_now = questions_wrong_now(score, rows)
    rows_needed = questions_that_could_resolve(score, _ONE_COMPARISON)

    # THE SECOND BUILD BEHIND THIS OUTCOME, AND IT IS LOOKED UP HERE RATHER
    # THAN WHERE ITS STEP IS DRAWN, because the arithmetic that thresholds it
    # is above and the arithmetic has to be about the rows the comparison will
    # actually run on.
    #
    # **THE ROWS THE COMPARISON RUNS ON ARE NOT `eval_size_n`.** That count is
    # the size of the FILE. `score_the_adapter` answers the rows the baseline
    # run graded and `evals.compare` reports its delta over the rows both runs
    # graded, so the denominator of any threshold in the units evals.compare
    # answers in is the BASELINE RUN'S GRADED ROWS - and `run_eval` grades
    # `evals.DEFAULT_EVAL_SAMPLE` of them unless somebody says otherwise, which
    # on this machine is 50. Measured: a 400-row eval file with a default
    # `run_eval` behind it produced a threshold of 6/400 = 0.015 for a delta
    # measured over 50 rows, so ONE row of fifty improving - McNemar p=1.0,
    # no evidence of anything - satisfied a criterion whose own sentence said
    # six rows had to change. A build claiming an exit criterion it cannot
    # check is the worst thing in this file and this was one.
    baseline_run = (
        the_baseline_run_to_beat(situation.thread_id, evaluation)
        if the_adapter_scorer_is_registered()
        else None
    )
    #: HOW MANY ROWS THAT RUN GRADED, and what it scored ON THOSE ROWS. Both
    #: are read off the run rather than off the ledger: the ledger's
    #: `baseline_score` is a fact about the model and this is a fact about the
    #: comparison, and where a run graded a sample they are not the same
    #: number.
    paired_rows = 0
    paired_score = score
    if baseline_run is not None:
        paired_rows = _an_integer(baseline_run.get("graded"))
        try:
            paired_score = float(baseline_run["score"])
        except (KeyError, TypeError, ValueError):  # pragma: no cover - a run with no score
            paired_score = score
    # AND A RUN WHOSE ROWS COULD NOT RESOLVE ANYTHING IS NOT SOMETHING TO
    # SCORE AGAINST. With the right denominator a tiny paired set produces a
    # demanding threshold rather than a lenient one, which is the correct
    # direction - but a threshold no adapter could reach is a build drawn to
    # fail, so this falls back to the bounded trial and says which row count
    # made it do so. The same sentence the refusal above uses, about the
    # rows that will actually be compared.
    paired_wrong = questions_wrong_now(paired_score, paired_rows)
    the_run_is_too_small = ""
    if baseline_run is not None and paired_wrong < floor:
        the_run_is_too_small = (
            f"THERE IS A COMPLETED EVAL RUN OVER THIS FILE AND ITS ROWS COULD "
            f"NOT RESOLVE THE COMPARISON. Eval run {baseline_run['run_id']} "
            f"graded {paired_rows} of the {rows} rows in {eval_subject.key} and "
            f"scored {paired_score} on them, so it gets {paired_wrong} of them "
            f"wrong - and those are the only rows an adapter could turn around. "
            f"A paired comparison needs {floor} rows to change verdict before "
            f"McNemar's exact test reaches {RESOLVED_AT} "
            f"(evals.mcnemar({floor}, 0) = {evals.mcnemar(floor, 0)}), so "
            "scoring against that run would come back NO EVIDENCE whatever the "
            "adapter learned. run_eval over this same file with a larger "
            f"sample - at least {questions_that_could_resolve(paired_score, _ONE_COMPARISON)} "
            "rows at that score - and ask again, and the fine-tune is drawn "
            "with the comparison on the end of it."
        )
        baseline_run = None
        paired_rows = 0

    # AND THE CASE WHERE MORE ROWS IS THE WRONG ASK, split off because the
    # sentence below would otherwise say "you would need at least 0 rows, which
    # is 0 more than you have" - `questions_that_could_resolve` answers 0 when
    # nothing can move, which is arithmetic and reads as permission. A baseline
    # that gets every graded row right leaves an adapter nothing to turn around
    # on THIS eval set at any size, so what is needed is rows it gets wrong
    # rather than more of the ones it gets right. Unreachable through
    # `propose_build`, which runs the engine and routes a passing score to
    # S1_ALREADY_PASSES; reachable by a caller assembling a `Situation`, which
    # is how a proposer ends up planning for a verdict other than the one in
    # front of it.
    if wrong_now <= 0:
        raise NotEnoughToPropose(
            f"Your baseline scores {score} on the {rows} rows counted in "
            f"{eval_subject.key}, so it gets none of them wrong - and the rows a "
            "fine-tune could turn around are exactly the rows that are wrong "
            "now. On this eval set no adapter can be shown to be better than "
            "what you already have, whatever it learns, because there is nothing "
            "here for it to fix. More rows of the same kind would not change "
            "that: what is needed is graded examples your current model gets "
            "WRONG, which is where the fine-tune's value would show up if it has "
            "any.",
            needs=("eval rows the baseline gets wrong",),
        )
    if wrong_now < floor:
        raise NotEnoughToPropose(
            f"This eval set could not show a fine-tune worked. It holds {rows} "
            f"counted rows and your baseline scores {score}, so it gets "
            f"{wrong_now} of them wrong - and those are the only rows an adapter "
            "could turn around. A paired comparison of the adapter against the "
            f"baseline needs {floor} rows to change verdict before McNemar's "
            f"exact test reaches {RESOLVED_AT} (evals.mcnemar({floor}, 0) = "
            f"{evals.mcnemar(floor, 0)}), so even an adapter that fixed every "
            "row you currently get wrong would come back NO EVIDENCE. You would "
            f"need at least {rows_needed} graded rows at this baseline - {floor} "
            f"/ (1 - {score}), rounded up - which is "
            f"{max(0, rows_needed - rows)} more than you have. Grading them is "
            "work; a fine-tune whose result cannot be read is more.",
            needs=(f"eval_size_n >= {rows_needed}",),
        )

    # REFUSAL: THIS MACHINE HAS NO ACCELERATOR TO TRAIN ON. Not the engine's
    # 7B-indexed VRAM table, which is a claim about a model size nobody has
    # named yet - this is the recipe's own preflight, which refuses a CPU-only
    # torch in as many words because a CPU run here is roughly twenty times
    # slower and looks exactly like a working one.
    if situation.values.get("accelerator") == "cpu_only":
        raise NotEnoughToPropose(
            "This machine reports no training accelerator - accelerator is on "
            f"file as {situation.values.get('accelerator')!r}. "
            f"{THE_LORA_RECIPE} refuses to start on a CPU-only torch and says "
            "why: a CPU run is roughly twenty times slower and looks exactly "
            "like a working one, which is the single worst trap there is here. "
            "where_to_train answers where this run should happen instead; "
            "nothing in this plan can make it happen on this box.",
            needs=("an accelerator, or a different machine",),
        )

    route = str(situation.result.route or "")
    method = _the_method_for(route)
    if not method:
        reference = situation.result.hardware_reference or {}
        raise NotEnoughToPropose(
            f"The engine routed this run to {route or 'nowhere'}, and there is "
            "no step in this plan that can run what that route asks for. "
            + (
                f"{THE_LORA_RECIPE} holds the base model at LoRA precision - it "
                "attaches an adapter to a model loaded normally and quantises "
                "nothing - so a route that says this card can only hold a "
                "quantised base is a route it cannot serve. "
                if route == "QLORA"
                else "This build runs a fine-tune on THIS machine, and that "
                "route is the engine saying the run belongs somewhere else or "
                "on a smaller base. "
            )
            + "S9_HARDWARE_ROUTER decided it from this "
            f"machine's VRAM against its own reference row {reference or '{}'}, "
            "and that row is indexed by BASE MODEL SIZE while the fact ledger "
            "has no base-model-size fact - the engine says so itself - so a "
            "smaller base than the row assumes may well fit. "
            "can_this_machine_train answers that for the model you actually "
            "mean, from its own config.json, and it is the better instrument. "
            "Ask it, then ask again.",
            needs=("a route this recipe can run",),
        )

    # REFUSAL: THIS DATA IS ALREADY IN A SANDBOX ON THIS MACHINE.
    already = sandboxes_already_holding(training)
    if already:
        raise NotEnoughToPropose(
            f"There is already a sandbox holding a snapshot of "
            f"{training_subject.key}: {list(already)}. Making another one "
            "copies your data a second time, builds a second pinned "
            "environment beside the first, and leaves two experiments in this "
            "transcript that nobody can tell apart. list_sandboxes says what "
            "each one pinned and what it holds; run_in_sandbox continues the "
            "one that is there, and delete_sandbox removes it if it went "
            "wrong. An experiment is resumed or disposed of, not duplicated.",
            needs=("a sandbox to resume, or delete_sandbox",),
        )

    # WHAT THE ENGINE'S OWN TABLES SAY THIS RUN IS. Read, never typed: the rank
    # band and the epoch band are S9_SIZE_TO_METHOD's own cells, matched to the
    # person's labelled-example count by the engine before this file was
    # reached. `rank_min` is the cheap end of the band the engine named and this
    # run is a measurement of cost rather than of quality, which is said out
    # loud in the step rather than left as a preference.
    size_row = dict(situation.result.size_row or {})
    rank = _an_integer(size_row.get("rank_min"))

    trial_config: dict[str, Any] = {
        "base_model": base_model,
        "dataset_path": training,
        "max_seq_len": length,
    }
    if rank > 0:
        trial_config["lora_r"] = rank
    text_field = str(situation.text_field or "").strip()
    if text_field:
        trial_config["text_field"] = text_field
    steps_asked = max(0, _an_integer(situation.trial_steps))
    if steps_asked > 0:
        trial_config["max_steps"] = steps_asked

    ranking = _a_call_that_fits(
        "find_models",
        {"method": method, "max_seq_len": length},
        must_carry=("method", "max_seq_len"),
    )
    reading = _a_call_that_fits(
        "read_model_config", {"repo_id": base_model}, must_carry=("repo_id",)
    )
    fitting = _a_call_that_fits(
        "can_this_machine_train",
        {"repo_id": base_model, "method": method, "seq_len": length},
        must_carry=("repo_id", "method", "seq_len"),
    )
    leaking = _a_call_that_fits(
        "check_split_leakage",
        {"train_path": training, "eval_path": evaluation},
        must_carry=("train_path", "eval_path"),
    )

    steps: list[Step] = []

    # THE CARD IS READ FIRST WHEN NOBODY HAS READ IT. The same shape as counting
    # the eval set before scoring against it: the fit answer below is VRAM
    # against a real geometry, and a VRAM figure that was defaulted is not a
    # measurement of this machine. `cost_provenance` is the engine's own word
    # for having noticed.
    fit_needs: tuple[str, ...] = ("config",)
    if not situation.is_measured("vram_gb"):
        steps.append(
            Step(
                id="card",
                tool="inspect_hardware",
                why=(
                    "Read this machine before deciding what fits on it. Nobody "
                    "has measured this card in this conversation - vram_gb is on "
                    f"file as {situation.values.get('vram_gb')!r} with origin "
                    f"{situation.origin('vram_gb') or 'nothing recorded'} - and "
                    "the whole fit question below is video memory against the "
                    "model's own geometry. The engine already stamped this run "
                    f"cost_provenance {situation.result.cost_provenance!r}, "
                    "which is its word for the same thing."
                ),
                arguments={},
                produces=(
                    Output(
                        "vram_gb",
                        "number",
                        "the video memory this card actually reports",
                        at="vram_gb",
                    ),
                ),
                cost=_local_cost(
                    "inspect_hardware",
                    find_out_by=(
                        "it is one read of this machine's own device tables; "
                        "time it once and it is timed"
                    ),
                ),
                exit_criterion=ExitCriterion(
                    stated=(
                        "the video memory was MEASURED off this card rather than "
                        "defaulted. A card nobody could read is reported as "
                        "defaulted and stamps nothing, and a fit verdict "
                        "computed from a defaulted number is a different claim "
                        "from one computed from a measured GPU"
                    ),
                    source="tool_result",
                    subject="provenance.vram_gb",
                    comparator="equals",
                    value="measured",
                ),
            )
        )
        fit_needs = ("config", "card")

    steps.append(
        Step(
            id="rank",
            tool="find_models",
            why=(
                "Show what actually fits this card at "
                f"{length} tokens per example, with the reasoning shown: fitting "
                "is worth 35 points out of 100 and downloads is worth 5, and "
                "every candidate that was thrown out comes back with the reason. "
                f"This does not choose {base_model} for you and it is not "
                "wired to - which model you fine-tune carries a licence and a "
                "commitment about what your product is. It is here so you can "
                "see, before you approve anything, whether the model you named "
                "is the one this machine should be running. It is not told "
                "whether your use is commercial either, so the tool's own "
                "default stands and licences are scored as unspecified - "
                "whether a licence is acceptable for what you are building is "
                "a judgement, and this plan does not make it for you."
            ),
            arguments=ranking,
            produces=(
                Output(
                    "ranked",
                    "array",
                    "the candidates that fit, best first, each with its own "
                    "memory figure and where that figure came from",
                    at="ranked",
                ),
            ),
            cost=_hub_cost(
                "find_models",
                find_out_by=(
                    "it is one search of the Hub plus a config read for the top "
                    "few; run it once and the rate is known for this connection"
                ),
            ),
            exit_criterion=ExitCriterion(
                stated=(
                    "a ranking came back, so the Hub answered and this machine's "
                    "video memory was known well enough to rank against. A Hub "
                    "that did not answer returns no ranking at all rather than "
                    "an empty one"
                ),
                source="tool_result",
                subject="ranked",
                comparator="exists",
            ),
            risks=(
                Risk(
                    what=(
                        "the ranking is budgeted against the example length you "
                        "gave rather than against a measured token length of "
                        "your own rows"
                    ),
                    what_we_do=(
                        "the reply says which, in its own `max_seq_len_source` "
                        "field, and this plan passes the length you named rather "
                        "than a default - so the ranking, the fit check and the "
                        "trial run are all about the same run"
                    ),
                ),
            ),
        )
    )

    steps.append(
        Step(
            id="config",
            tool="read_model_config",
            why=(
                f"Read {base_model}'s own config.json, so the memory answer "
                "below is computed from its real layers, heads and vocabulary "
                "instead of borrowed from another architecture. Without it the "
                "fit verdict is UNKNOWN and says so: the logits buffer is "
                "vocabulary times sequence times batch times four bytes, it is "
                "one of the largest terms in a training budget, and this product "
                "once returned SPILLS-with-headroom on an 8 GB card by leaving "
                "it out of the sum it had already computed."
            ),
            arguments=reading,
            produces=(
                Output(
                    "geometry",
                    "object",
                    "the layers, heads, head dimension and vocabulary size, read "
                    "from the model's own file",
                    at="geometry",
                ),
            ),
            cost=_hub_cost(
                "read_model_config",
                find_out_by=(
                    "it is a metadata request and a file request against "
                    "huggingface.co; time it once"
                ),
            ),
            exit_criterion=ExitCriterion(
                stated=(
                    "the config was read AND it carries a vocabulary size. That "
                    "is the term the logits buffer is computed from, and a "
                    "config with no vocabulary describes something that is not "
                    "an autoregressive text decoder - for which the memory "
                    "verdict stays UNKNOWN rather than becoming a yes"
                ),
                source="tool_result",
                subject="geometry.vocab_size",
                comparator="exists",
            ),
            operates_on=None,
        )
    )

    steps.append(
        Step(
            id="fits",
            tool="can_this_machine_train",
            why=(
                f"Answer YES or NO: can this card hold {base_model} at "
                f"method={method}, {length} tokens per example - with every term "
                "of the sum and where each came from. This is the step that "
                "decides whether anything else is worth doing, and it is asked "
                "before a single byte of weights is downloaded or a sandbox is "
                "made. It consults no gate and opens none: it declares "
                "measures=(), so it can stamp no fact at all."
            ),
            arguments=fitting,
            produces=(
                Output(
                    "answer",
                    "string",
                    "YES, NO or UNKNOWN - and a NO carries the longest example "
                    "length that WOULD fit",
                    at="answer",
                ),
            ),
            needs=fit_needs,
            cost=_local_cost(
                "can_this_machine_train",
                find_out_by=(
                    "it is arithmetic over a config already on disk; time it "
                    "once and it is timed"
                ),
            ),
            exit_criterion=ExitCriterion(
                stated=(
                    "the answer is YES. Not 'it did not crash' and not "
                    "'a number came back': UNKNOWN is a real answer this tool "
                    "gives when the geometry is missing a term it needs, and a "
                    "plan that treated UNKNOWN as permission to spend a GPU hour "
                    "would be doing the thing this whole file is against"
                ),
                source="tool_result",
                subject="answer",
                comparator="equals",
                value="YES",
            ),
            risks=(
                Risk(
                    what=(
                        "the answer is NO, or UNKNOWN because the model's config "
                        "carries no vocabulary size"
                    ),
                    what_we_do=(
                        "the plan stops here and nothing is downloaded, copied "
                        "or built. A NO carries the longest example length that "
                        "WOULD fit on this card, so the next move is a shorter "
                        "max_seq_len or a smaller base - both of which are "
                        "cheaper decisions than an OOM at minute twenty"
                    ),
                ),
                Risk(
                    what=(
                        "the example length you gave is outside the range this "
                        "tool will budget against, so it answers about a "
                        "different length from the one the trial runs at"
                    ),
                    what_we_do=(
                        "its reply says what it budgeted against and where that "
                        "came from, in its own seq_len fields, so the two can be "
                        "compared rather than assumed equal. This plan passes "
                        f"the {length} you named to the fit check and to the run "
                        "so that they are the same number; a tool that bounds it "
                        "is the one place they can come apart, and it says so "
                        "where you can see it"
                    ),
                ),
            ),
        )
    )

    steps.append(
        Step(
            id="leak",
            tool="check_split_leakage",
            why=(
                "Check that no row of the training data is also in the eval set - "
                "near-identical rows, not only byte-identical copies. This is the "
                "check a person cannot run by eye and it is the one that decides "
                "whether any later comparison means anything: a single leaked row "
                "does not weaken the eval, it removes its meaning, and the score "
                "it produces is the number this product would otherwise quote as "
                "a measured baseline."
            ),
            arguments=leaking,
            produces=(
                Output(
                    "leak_rate",
                    "number",
                    "the share of eval rows that also appear in the training "
                    "data - null when the check could not run at all",
                    at="leak_rate",
                ),
                Output(
                    "leaked_rows",
                    "integer",
                    "how many eval rows were found on both sides",
                    at="leaked_rows",
                ),
            ),
            cost=_local_cost(
                "check_split_leakage",
                find_out_by=(
                    "it shingles both files and indexes the training side; run it "
                    "on these two and it is timed for files of this size"
                ),
            ),
            # `leak_rate` AND NOT `leaked_rows`, AND THE DIFFERENCE IS THE WHOLE
            # CHECK. This tool reports a check it could NOT run in the same shape
            # as a clean one: `leaked_rows` is initialised to 0 and returned as 0
            # when the file does not exist or no reader ships for its format, so
            # `leaked_rows at_most 0` passes on a check that never happened. The
            # one field that separates the three states is `leak_rate`, which is
            # null unless rows were actually compared - the same reason the
            # recall step is held to `stampable` rather than to `ok`.
            exit_criterion=ExitCriterion(
                stated=(
                    "the check RAN and found no overlap at all. A check that "
                    "could not run reports no rate rather than a rate of zero, "
                    "and fails this - which is the point: 'we could not look' and "
                    "'we looked and it is clean' are the same sentence to a "
                    "reader and opposite facts"
                ),
                source="tool_result",
                subject="leak_rate",
                comparator="at_most",
                value=0,
            ),
            operates_on=None,
            risks=(
                Risk(
                    what="rows appear on both sides of your split",
                    what_we_do=(
                        "the plan stops before anything is trained, and the step "
                        "names the overlapping rows with the similarity that "
                        "matched them. Training on them would produce an adapter "
                        "whose score on this eval set is a measurement of memory "
                        "rather than of learning - and a high one, which is worse "
                        "than a low one"
                    ),
                ),
            ),
        )
    )

    egress = _egress_for_the_hub([step.tool for step in steps], weights=True)

    sandboxing = _a_call_that_fits(
        "make_sandbox",
        {
            "purpose": (
                "a bounded trial of the "
                + THE_LORA_RECIPE
                + " fine-tune, to measure what the whole run would cost on this "
                "machine before any of it is spent"
            ),
            "recipe": THE_LORA_RECIPE,
            "data": [training],
            "egress": True,
            "egress_reason": egress,
        },
        must_carry=("recipe", "data", "egress", "egress_reason"),
    )
    steps.append(
        Step(
            id="sandbox",
            tool="make_sandbox",
            why=(
                "Make the isolated place this runs in, and make it part of the "
                "build rather than something you set up first. It pins the "
                f"{THE_LORA_RECIPE} environment - the locked requirements are on "
                "the environment below, read off that recipe's own lockfile - "
                "takes a snapshot of your training file as it is right now with "
                "its size, modification time and digest, and gets its own "
                "working directory so an experiment that goes wrong is deleted "
                "rather than untangled. It reports what it can and cannot reach, "
                "including the parts of 'no egress' this harness does not enforce."
            ),
            arguments=sandboxing,
            produces=(
                Output(
                    "sandbox_name",
                    "string",
                    "what this sandbox is called, so the step below names it "
                    "rather than taking whichever one is newest",
                    at="name",
                ),
                Output(
                    "fingerprint",
                    "string",
                    "what this sandbox IS, as a digest - the reproducibility "
                    "claim, checkable",
                    at="fingerprint",
                ),
            ),
            needs=("fits", "leak"),
            cost=_local_cost(
                "make_sandbox",
                find_out_by=(
                    "it copies your training file and reads a lockfile; the copy "
                    "is the whole of it, so time one copy of a file this size"
                ),
            ),
            exit_criterion=ExitCriterion(
                stated=(
                    "the environment is PINNED: the recipe's own virtualenv is "
                    "built and its lockfile is there. A sandbox that pins "
                    "nothing is isolated and disposable and NOT reproducible, "
                    "and this plan would rather stop than call it one"
                ),
                source="tool_result",
                subject="pinned.pinned",
                comparator="is_true",
            ),
            operates_on=None,
            risks=(
                Risk(
                    what=(
                        "'no egress' is read as a guarantee the operating system "
                        "is enforcing"
                    ),
                    what_we_do=(
                        "the sandbox says so itself, in its own reply: there is "
                        "no network namespace, no firewall rule and no "
                        "container, so what it guarantees is what it HANDS a run "
                        "- no provider key, no HF token, no address for this "
                        "harness - and not what the run is able to do. This one "
                        "declares egress anyway and says why, which is the "
                        "honest version of the same sentence"
                    ),
                ),
                Risk(
                    what="the training file is large enough not to be copied",
                    what_we_do=(
                        "over half a gigabyte it is recorded where it is rather "
                        "than duplicated, and the row says so with its size and "
                        "modification time. What is lost is named rather than "
                        "discovered later: if the original changes, this sandbox "
                        "can detect it and cannot undo it"
                    ),
                ),
            ),
        )
    )

    running = _a_call_that_fits(
        "run_in_sandbox",
        {
            "name": Ref("sandbox", "sandbox_name"),
            "kind": THE_TRAINING_KIND,
            "config": trial_config,
        },
        must_carry=("name", "kind", "config"),
    )
    steps.append(
        Step(
            id="trial",
            tool="run_in_sandbox",
            why=(
                "Run the real recipe, on your real data, on this card - bounded, "
                "and only far enough to find out what it costs. This is the step "
                "every UNKNOWN wall-clock estimate in this plan points at: "
                "nothing in this harness has ever timed a training step on this "
                "machine, so there is nothing to derive one from and any figure "
                "here would be invented. What comes back is measured - the "
                "seconds, the steps done, the tokens per second and the peak "
                "video memory, printed as it goes - and it is the number the "
                "full run would be planned against. It also finds out, for the "
                "price of a few steps, the two things that otherwise fail at "
                "minute twenty: that the pinned environment holds a CUDA torch "
                "rather than the CPU-only wheel, and that your rows have the "
                "field the recipe reads."
                + (
                    ""
                    if steps_asked > 0
                    else " You did not say how many steps, so the recipe's own "
                    "default stands and its log reports how many it ran - pass "
                    "trial_steps to size the slice yourself, because how much of "
                    "your machine this takes is your call rather than this "
                    "file's."
                )
                + (
                    ""
                    if text_field
                    else " You did not name the field holding the training text, "
                    "so the recipe reads its own default and accepts a "
                    "prompt/completion pair instead - and refuses the file "
                    "loudly if it has neither, rather than training happily on "
                    "an empty string."
                )
            ),
            arguments=running,
            produces=(
                Output(
                    "exit_code",
                    "integer",
                    "what the recipe returned - zero only when it trained to the "
                    "end of the slice",
                    at="exit_code",
                ),
                Output(
                    "timed_out",
                    "boolean",
                    "whether the bound killed it rather than it finishing",
                    at="timed_out",
                ),
                Output(
                    "log_path",
                    "string",
                    "the log this run wrote, which carries the measured seconds, "
                    "tokens per second and peak VRAM",
                    at="log_path",
                ),
            ),
            needs=("sandbox",),
            cost=Cost(
                model_tokens=Estimate.none(
                    build.MODEL_TOKENS,
                    because=(
                        "run_in_sandbox declares reads="
                        f"{list(_spec('run_in_sandbox').reads)}, which does not "
                        "include `providers`, so nothing in this run reaches the "
                        "model you connected. Training is your machine's time, "
                        "not a bill"
                    ),
                ),
                model_requests=Estimate.none(
                    build.MODEL_REQUESTS,
                    because=(
                        "the same declaration - run_in_sandbox reads "
                        f"{list(_spec('run_in_sandbox').reads)} and not "
                        "`providers` - so this run asks your model nothing, "
                        "not once"
                    ),
                ),
                wall_clock=_wall_clock(
                    "run_in_sandbox",
                    find_out_by=(
                        "THIS STEP IS THE ANSWER. Nothing on this machine has "
                        "ever timed a training step, which is why every "
                        "wall-clock figure in this plan is UNKNOWN. The recipe "
                        "prints elapsed seconds, steps done, tokens per second "
                        "and peak VRAM as it runs, so a bounded slice is a "
                        "measurement of the whole - and the run is killed at the "
                        "sandbox's own timeout, which bounds what not knowing "
                        "can cost you"
                    ),
                ),
                disk=Estimate.unknown(
                    build.DISK,
                    why=(
                        "run_in_sandbox declares writes="
                        f"{list(_writes_to_disk('run_in_sandbox'))}, and this run "
                        "writes three things nobody here has measured: the base "
                        "model's weights into your Hugging Face cache, the "
                        "adapter into the sandbox, and the log. The first is by "
                        "far the largest and it is a property of the model you "
                        "named rather than of this plan"
                    ),
                    find_out_by=(
                        "read_model_config above reports the parameter count off "
                        "the repo's own safetensors index, which is what the "
                        "download is; and the sandbox is one directory, so "
                        "measuring it before and after is a measurement of YOUR "
                        "run rather than of an average one"
                    ),
                ),
            ),
            exit_criterion=ExitCriterion(
                stated=(
                    "the recipe ran your own data through the real trainer on "
                    "this card and returned zero. That is not 'training "
                    "finished' standing in for a result - this build's artifact "
                    "IS the measurement, and a non-zero code is what the recipe "
                    "returns when its preflight is red (a CPU-only torch, too "
                    "little free video memory) or your rows have no field it can "
                    "read. Both of those are things it is far better to learn "
                    "here than after an approval to spend the whole run"
                ),
                source="tool_result",
                subject="exit_code",
                comparator="equals",
                value=0,
            ),
            operates_on=None,
            risks=(
                Risk(
                    what=(
                        "the base model's weights have to be downloaded before "
                        "anything can train, and that is the largest thing this "
                        "step does"
                    ),
                    what_we_do=(
                        "it is why this sandbox declares egress and says so on "
                        "the environment below, where you can read it before you "
                        "approve it. A no-egress sandbox sets HF_HUB_OFFLINE and "
                        "the run would refuse rather than fetch - which is the "
                        "honest behaviour and not the one you want here"
                    ),
                ),
                Risk(
                    what=(
                        "the slice takes longer than the sandbox's own bound - "
                        "which the FIRST run of any model makes likely, because "
                        "it downloads the weights before it trains a step"
                    ),
                    what_we_do=(
                        "the whole process tree is killed at the timeout and the "
                        "step reports timed_out rather than a result, which fails "
                        "this step's criterion. That is the bound doing its job: "
                        "not knowing how long a step takes is exactly why it runs "
                        "under one, and it is the only thing standing between an "
                        "unmeasured run and your whole evening. It also costs "
                        "less than it reads: the weights land in your Hugging "
                        "Face cache, which is outside the sandbox and survives "
                        "it, so a second run of this starts at the training "
                        "rather than at the download"
                    ),
                ),
                Risk(
                    what=(
                        "the adapter this writes is mistaken for a fine-tune you "
                        "can use"
                    ),
                    what_we_do=(
                        "it is not one and this plan says so twice. A bounded "
                        "slice of a training run produces adapter weights the "
                        "way a test print produces a page - it proves the "
                        "pipeline, it is not the product. It lives inside a "
                        "disposable sandbox, the sandbox's own reply tells you "
                        "the delete_sandbox call that removes it, and nothing "
                        "here scores it, because nothing here can"
                    ),
                ),
            ),
        )
    )

    # THE SECOND BUILD BEHIND THIS OUTCOME, AND WHICH ONE YOU GET IS DECIDED BY
    # READING YOUR CONVERSATION RATHER THAN BY ASKING - the shape
    # `BLOCKED__BUILD_EVAL_SET` already has. The instrument that scores an
    # adapter now exists, so the fine-tune and the comparison against your
    # measured baseline are drawable; what decides whether THIS run gets them is
    # whether there is a completed eval run whose graded rows the adapter can be
    # scored on. Absent, the trial is drawn exactly as it was and the plan names
    # the one step that would unlock the other.
    #
    # `baseline_run` and `paired_rows` were read further up, beside the
    # arithmetic they threshold - see the comment there for why the two cannot
    # be separated.
    if baseline_run is not None:
        scoring = _a_call_that_fits(
            THE_ADAPTER_SCORER,
            {
                # A `Ref` AND NOT A NAME, for the trial step's reason: the
                # executor must score in the sandbox THIS plan made rather than
                # in whichever one is newest when it gets there.
                "sandbox": Ref("sandbox", "sandbox_name"),
                "baseline_run_id": int(baseline_run["run_id"]),
                "thread_id": int(situation.thread_id),
                # ON, AND IT IS THE ONLY COMPARISON THAT ISOLATES THE TRAINING.
                # The tool's own default is on and its reply says why: the
                # baseline went through a chat endpoint and this goes through a
                # greedy continuation in a sandbox, so the comparison against
                # your baseline crosses two instruments. Answering the same rows
                # with the adapter switched off, on the same loaded weights, is
                # one instrument throughout. It is passed explicitly rather than
                # left to the default because a plan that quietly relied on a
                # default for the control arm would be one edit away from having
                # no control arm.
                "include_base": True,
            },
            must_carry=("sandbox", "baseline_run_id", "thread_id"),
        )
        steps.append(
            Step(
                id="score",
                tool=THE_ADAPTER_SCORER,
                why=(
                    "Score the adapter you just trained on the SAME rows eval "
                    f"run {baseline_run['run_id']} graded, inside the sandbox "
                    "that made it, and report the paired comparison against "
                    "that baseline. This is the step that makes the run above "
                    "worth approving: without it the artifact is an adapter and "
                    "'the run exited zero', which is the sentence this product "
                    "exists to refuse. It runs the sandbox's own pinned "
                    "environment - the same interpreter and the same locked "
                    "requirements that did the training - because nothing "
                    "outside a sandbox in this harness can load an adapter at "
                    "all. IT ALSO ANSWERS THE SAME ROWS WITH THE ADAPTER "
                    "SWITCHED OFF, on the same loaded weights, and that second "
                    "comparison is the one that isolates what the training did: "
                    f"your baseline was measured through {baseline_run.get('provider') or 'a connection'} "
                    "under a chat prompt and this is a greedy continuation in a "
                    "sandbox, so the comparison against the baseline crosses "
                    "two instruments and carries the decoding path as well as "
                    "the model. Both are reported and neither is presented as "
                    "the other."
                ),
                arguments=scoring,
                produces=(
                    Output(
                        "delta",
                        "number",
                        "the paired difference against your measured baseline, "
                        "over the rows both runs graded",
                        at="against_the_baseline.delta",
                    ),
                    Output(
                        "verdict",
                        "string",
                        "'different' or 'no_evidence' - whether that difference "
                        "is bigger than these rows can resolve",
                        at="against_the_baseline.verdict",
                    ),
                    Output(
                        "isolated_delta",
                        "number",
                        "the same difference against the BASE MODEL on one "
                        "instrument, which is what the training itself did",
                        at="against_the_base_model.delta",
                    ),
                ),
                # BOTH, AND `sandbox` IS NOT REDUNDANT. `trial` already waits on
                # `sandbox`, so the ordering would hold either way - but this
                # step takes an argument OUT of the sandbox step, and
                # `Build.validate` requires a step that reads another's output
                # to declare it. That is the rule doing its job: a transitive
                # ordering is not a data dependency, and an executor is entitled
                # to schedule on what a step declares rather than on what a
                # reader of the plan can infer.
                needs=("trial", "sandbox"),
                cost=Cost(
                    model_tokens=Estimate.none(
                        build.MODEL_TOKENS,
                        because=(
                            f"{THE_ADAPTER_SCORER} declares reads="
                            f"{list(_spec(THE_ADAPTER_SCORER).reads)}, which does "
                            f"not include `{THE_SCORING_READ}` - and that is not "
                            "an accident of this tool, it is the reason it can be "
                            "pointed at an adapter at all. Generating the answers "
                            "is your machine's time, not a bill"
                        ),
                    ),
                    model_requests=Estimate.none(
                        build.MODEL_REQUESTS,
                        because=(
                            f"the same declaration - {THE_ADAPTER_SCORER} reads "
                            f"{list(_spec(THE_ADAPTER_SCORER).reads)} and not "
                            f"`{THE_SCORING_READ}`. Every answer is generated in "
                            "the sandbox and graded in this process by the same "
                            "function that graded your baseline, so your "
                            "connected model is asked nothing, not once"
                        ),
                    ),
                    wall_clock=_wall_clock(
                        THE_ADAPTER_SCORER,
                        find_out_by=(
                            "it generates one answer per row twice - once with "
                            "the adapter and once without - over the "
                            f"{baseline_run.get('graded')} rows eval run "
                            f"{baseline_run['run_id']} graded, and nothing on "
                            "this machine has timed generation in this sandbox. "
                            "The step above is what makes that timeable: run it "
                            "and the tokens per second it prints is the number "
                            "this derives from"
                        ),
                    ),
                    disk=_disk_cost(THE_ADAPTER_SCORER),
                ),
                exit_criterion=ExitCriterion(
                    stated=(
                        "every row that eval run "
                        f"{baseline_run['run_id']} graded was answered by the "
                        "adapter and graded by the same grader. NOT that the "
                        "adapter won - that is this build's criterion below and "
                        "it is a different sentence - and not 'a score came "
                        "back': a run that stops early reports no score at all, "
                        "keeps every answered row on disk, and does not run the "
                        "comparison. A partial score is not a score, and a "
                        "comparison over the rows that happened to finish is a "
                        "comparison over the rows that were quickest"
                    ),
                    source="tool_result",
                    subject="adapter_score.complete",
                    comparator="is_true",
                ),
                operates_on=None,
                risks=(
                    Risk(
                        what=(
                            "the comparison against your baseline is read as one "
                            "measurement of one thing"
                        ),
                        what_we_do=(
                            "it is two instruments and the reply says so in its "
                            "own words: your baseline went through a connection "
                            "under a system prompt, this went through a greedy "
                            "continuation in a sandbox, and the difference "
                            "between them carries the decoding path as well as "
                            "the model. That is why the base model is scored in "
                            "there too - against_the_base_model is one "
                            "instrument throughout and is the comparison that "
                            "isolates the adapter. The plan carries both and "
                            "picks neither for you"
                        ),
                    ),
                    Risk(
                        what=(
                            "the scoring run takes longer than its bound and is "
                            "killed"
                        ),
                        what_we_do=(
                            "the tool bounds itself and kills the whole process "
                            "tree at its own timeout; the rows answered before "
                            "that are on disk and the comparison does not run, "
                            "which fails this step rather than reporting a score "
                            "over whichever rows finished first"
                        ),
                    ),
                ),
            )
        )

    stated = engine_exit_criterion(_THE_MINT, situation.spec)
    owed = the_criterion_the_engine_owes(situation.spec)
    said = str(situation.result.say or "").strip()
    hand_off = engine_node_says(_THE_MINT, "hand_off", situation.spec)

    the_real_criterion = (
        "WHAT A FINE-TUNE IS ACTUALLY HELD TO, so that what this build is held "
        "to cannot be mistaken for it: the adapter beats your measured baseline "
        f"of {score} on {eval_subject.key}, by a margin these rows can resolve. "
        f"Your eval set holds {rows} counted rows, so at that baseline "
        f"{wrong_now} of them are wrong today and those are the only rows an "
        "adapter can turn around. A paired comparison of two models over the "
        f"same rows needs {floor} of them to change verdict before McNemar's "
        f"exact test reaches {RESOLVED_AT} (evals.mcnemar({floor}, 0) = "
        f"{evals.mcnemar(floor, 0)}), which needs at least {rows_needed} rows at "
        f"this baseline - {floor} / (1 - {score}), rounded up. You have enough "
        "for that comparison to be POSSIBLE, which is never the same as likely: "
        "a delta inside what these rows can resolve is reported as NO EVIDENCE, "
        "in those words, and 'the loss went down' is not evidence of anything at "
        "all."
    )

    # THE SMALLEST IMPROVEMENT THE COMPARED ROWS COULD RESOLVE, as a delta
    # rather than as a row count. `floor` rows changing one way out of the rows
    # the two runs BOTH graded IS a delta of `floor / paired_rows`, in the units
    # `evals.compare` answers in - and `paired_rows` is the baseline run's
    # graded count, not `eval_size_n`.
    #
    # IT WAS `floor / rows` AND THAT WAS A CRITERION THAT COULD NOT CHECK ITS
    # OWN SENTENCE. `run_eval` grades `evals.DEFAULT_EVAL_SAMPLE` rows unless
    # told otherwise; a 400-row file behind a default run gave 6/400 = 0.015 for
    # a delta measured over 50 rows, so one row of fifty improving passed a
    # criterion that printed "6 of them have to change verdict". The
    # denominator is the compared set or the arithmetic is about a different
    # measurement than the one being taken.
    #
    # It is a NECESSARY condition and not a sufficient one - the verdict beside
    # it is what says whether the difference separated - and the criterion below
    # says so in as many words.
    smallest_resolvable = float(Fraction(floor, max(1, paired_rows or rows)))

    if stated:  # pragma: no cover - the spec started stating one
        criterion = (
            f"{_THE_MINT} states it as: {stated!r}. This build reaches the part "
            "of that a bounded trial can reach and says so below rather than "
            "reading the sentence as satisfied."
        )
    elif baseline_run is not None:
        criterion = (
            f"{_THE_MINT} DECLARES NO exit_criterion OF ITS OWN. What it "
            "declares instead is that a diagnosis carrying this verdict must "
            "set one"
            + (f" - {owed!r}" if owed else "")
            + ", so what follows was not taken from the engine and was not "
            "invented either: it is the sentence a fine-tune has always been "
            "held to, and it is now CHECKABLE. "
            + the_real_criterion
            + " AND THIS BUILD IS HELD TO EXACTLY THAT SENTENCE, because "
            + ", ".join(tools_that_score_an_adapter())
            + " can now take the measurement. The check is the paired delta "
            f"against eval run {baseline_run['run_id']} reaching "
            f"{smallest_resolvable} - which is {floor} / {paired_rows}, the "
            "smallest improvement THE ROWS THIS COMPARISON RUNS ON could "
            "resolve, in the units evals.compare reports. "
            + (
                f"That denominator is {paired_rows} and not the {rows} rows in "
                f"your file, because eval run {baseline_run['run_id']} graded "
                f"{paired_rows} of them and the adapter is answered on exactly "
                "those: evals.compare measures its delta over the rows both "
                "runs graded, so a threshold over the file's row count would "
                f"pass on {round(smallest_resolvable * paired_rows, 2)} rows "
                "changing. Grade more of the file with run_eval and this "
                "threshold gets harder, which is the right direction. "
                if paired_rows < rows
                else f"That run graded all {rows} counted rows, so the compared "
                "set and the file are the same set here. "
            )
            + "THAT IS A NECESSARY CONDITION AND NOT A "
            "SUFFICIENT ONE, and the difference matters: the verdict printed "
            "beside the delta is the tool's own word for whether these rows "
            "separated the two models at all, and a delta over this threshold "
            "with a verdict of no_evidence is not a fine-tune that worked. "
            "The step's own criterion is a different sentence again - that "
            "every graded row was answered - because a comparison over the "
            "rows that happened to finish is a comparison over the rows that "
            "were quickest."
        )
    else:
        criterion = (
            f"{_THE_MINT} DECLARES NO exit_criterion OF ITS OWN. What it "
            "declares instead is that a diagnosis carrying this verdict must "
            "set one"
            + (f" - {owed!r}" if owed else "")
            + ", so nothing below was taken from the engine and nothing was "
            "invented to stand in for it. "
            + the_real_criterion
            + " AND THIS RUN CANNOT CHECK THAT SENTENCE, which is why this "
            "build does not run the fine-tune to a comparison and does not "
            "pretend to. "
            + _why_this_run_cannot_be_scored(
                situation, eval_subject, the_run_is_too_small
            )
            + " WHAT IT IS HELD TO INSTEAD: the pinned recipe ran your own rows "
            "through the real trainer on this card and returned zero. That is a "
            "criterion about a MEASUREMENT having been taken, not about a model "
            "having been produced - the artifact here is the cost of the run and "
            "the proof that the pipeline works end to end on this machine, and "
            "both of those are things the log carries and nothing else in this "
            "product has ever held."
        )

    because = (
        (f"{said} " if said else "")
        + (f"The engine's hand-off is: {hand_off!r} " if hand_off else "")
        + f"This harness ships one of those three, {THE_LORA_RECIPE}, and its "
        "pinned environment is built on this machine - "
        + f"{len(recipe.get('installs') or ())} locked requirements, Python "
        + f"{recipe.get('python') or 'unknown'}, listed on the environment below. "
        + "WHAT THE ENGINE'S OWN TABLES SAY THIS RUN IS: method "
        + f"{situation.result.proposed_method!r}"
        + (
            f", rank {size_row.get('rank')!r} and {size_row.get('epochs')!r} "
            f"epochs for a set of {size_row.get('examples')!r} examples, which "
            "is S9_SIZE_TO_METHOD's own row matched to your labelled-example "
            f"count - the realistic gain it names is {size_row.get('realistic_gain')!r}"
            if size_row
            else ", and S9_SIZE_TO_METHOD matched no size row, so no rank or "
            "epoch band was read and the recipe's own defaults stand"
        )
        + f". S9_HARDWARE_ROUTER routed this machine to {route!r} against its "
        f"reference row {situation.result.hardware_reference or '{}'}, and that "
        "table is indexed by base model size while the ledger has no "
        "base-model-size fact - the engine says so itself - so the fit question "
        f"is put to can_this_machine_train about {base_model} instead, from its "
        "own config.json. "
        + the_real_criterion
        + " "
        + why_the_full_run_is_not_drawn()
        + (
            " SO THIS BUILD RUNS THE FINE-TUNE AND THEN SCORES WHAT IT MADE. It "
            "reads this card, ranks what fits it, reads "
            f"{base_model}'s real geometry, answers YES or NO on the memory "
            "before a byte is downloaded, checks that your split does not leak, "
            "makes the disposable pinned sandbox with your data snapshotted as "
            "it is now, runs the real recipe on this card, and then scores the "
            "adapter it produced against eval run "
            f"{baseline_run['run_id']} - the {baseline_run.get('graded')} rows "
            "that run graded, answered again in the sandbox that trained the "
            "adapter and graded by the same function that graded them the first "
            "time. HOW MUCH TRAINING IS BEING SCORED IS YOURS: "
            + (
                f"you asked for {steps_asked} optimizer steps"
                if steps_asked > 0
                else "you did not say how many optimizer steps, so the recipe's "
                "own default stands and its log reports how many it ran - which "
                "is a small number, and a comparison after a handful of steps "
                "will very likely come back NO EVIDENCE and be right to. Pass "
                "trial_steps to decide how much of your machine this spends"
            )
            + ". Every wall-clock estimate in this plan is UNKNOWN and the "
            "training step is the plan's own answer to it. "
            if baseline_run is not None
            else " SO THIS BUILD DOES THE HALF THAT CAN BE VERIFIED AND MEASURES "
            "THE THING NOBODY HAS EVER MEASURED. It reads this card, ranks what "
            f"fits it, reads {base_model}'s real geometry, answers YES or NO on "
            "the memory before a byte is downloaded, checks that your split does "
            "not leak, makes the disposable pinned sandbox with your data "
            "snapshotted as it is now, and runs the real recipe over a bounded "
            "slice so the seconds, the tokens per second and the peak video "
            "memory come off this card instead of out of somebody's memory. "
            "Every wall-clock estimate in this plan is UNKNOWN and that step is "
            "the plan's own answer to it. "
        )
        + "AND NOTHING HERE STAMPS ANYTHING THE FIVE GATES READ: no step runs a "
        "tool that measures eval_size_n, baseline_score, baseline_measured or "
        "any other fact a gate row asks for, so a build downstream of a TRAIN "
        "verdict cannot make that verdict easier to reach. "
        + (
            "The scoring step is the sharpest case of that and it declares "
            "measures=() for exactly this reason: an adapter's score filed "
            "under baseline_score would be a real measurement of a DIFFERENT "
            "MODEL under the name G1 reads. The rows live in the eval bench's "
            "own tables and the five gates are where they were. "
            if baseline_run is not None
            else ""
        )
        + egress
    )

    identity = (
        _THE_SCORED_TRAINING_BUILD if baseline_run is not None else _THE_TRAINING_BUILD
    )

    return Build(
        id=identity["id"],
        title=identity["title"],
        for_outcome=situation.outcome,
        because=because,
        steps=tuple(steps),
        environment=Environment(
            name=identity["id"],
            working_dir=f"runs/proposals/{identity['id']}",
            egress=True,
            egress_reason=egress,
            data=tuple(
                build.DataSnapshot.of(path) for path in (training, evaluation) if path
            ),
            # THE RECORD OF EXACTLY WHAT WAS INSTALLED, which is the spec's own
            # phrase and is the recipe's lockfile lines rather than a summary of
            # them. Read off this machine through the same function the sandbox
            # uses, so the environment this plan DECLARES and the environment
            # the sandbox step PINS cannot be two different claims.
            installs=tuple(recipe.get("installs") or ()),
            python=str(recipe.get("python") or ""),
        ),
        # THE CRITERION IS THE REAL ONE WHEN IT CAN BE, AND THE MEASURED ONE
        # WHEN IT CANNOT. With a baseline run to beat, this is the sentence a
        # fine-tune has always been held to - the adapter beats your measured
        # baseline by a margin these rows can resolve - checked as a paired
        # delta reaching the smallest improvement those rows could resolve.
        # Without one it is what it always was: the pipeline ran on this card
        # and returned zero, which is a criterion about a measurement having
        # been taken.
        exit_criterion=(
            ExitCriterion(
                stated=criterion,
                source="outputs",
                subject="score.delta",
                comparator="at_least",
                value=smallest_resolvable,
            )
            if baseline_run is not None
            else ExitCriterion(
                stated=criterion,
                source="outputs",
                subject="trial.exit_code",
                comparator="equals",
                value=0,
            )
        ),
        risks=(
            Risk(
                what=(
                    "this build ends with a measured cost and no fine-tuned "
                    "model, which is less than the verdict promised"
                ),
                what_we_do=(
                    "it is less, and it is what this product can honestly hand "
                    "over today. The alternative is an adapter with no "
                    "measurement beside it, which is the one thing this product "
                    "exists not to give people - and the gap is a tool that can "
                    "score a model that is not a connected provider, not a "
                    "proposer. When that tool registers, the full run and the "
                    "comparison against your baseline are a build, and the "
                    "numbers this trial measures are what it will be planned "
                    "against"
                ),
            ),
            Risk(
                what=(
                    "a trial that runs cleanly is read as evidence that the "
                    "fine-tune will work"
                ),
                what_we_do=(
                    "it is evidence about the MACHINE and about the PIPELINE and "
                    "about nothing else. Whether a fine-tune helps is decided by "
                    "the comparison in the criterion above, on your own eval set, "
                    "and no step here takes it. A short run's loss curve is the "
                    "single most persuasive thing in machine learning that means "
                    "nothing at all"
                ),
            ),
            Risk(
                what=(
                    "the sandbox and the downloaded weights take disk that is "
                    "never reclaimed"
                ),
                what_we_do=(
                    "the sandbox is disposable by design and its own reply gives "
                    "you the delete_sandbox call that removes it, which takes "
                    "nothing outside it with it. The weights land in your "
                    "Hugging Face cache and stay there, which is what makes the "
                    "next run of this cheaper and is worth knowing before the "
                    "first one"
                ),
            ),
        ),
        facts=dict(situation.origins),
    )


# ---------------------------------------------------------------------------
# THE SECOND TRAINING BACKEND, AND WHAT IT MADE FALSE.
#
# `_TRAINING` answered for eight uncovered outcomes with one sentence, and the
# sentence named its own expiry: *"recipes/ holds one real trainer, hf-peft-lora,
# and it does a LoRA supervised fine-tune and nothing else: NO PREFERENCE
# OPTIMISATION, no reinforcement loop..."*. `recipes/hf-peft-dpo/` makes the
# clause about preference optimisation false, so `TRAIN__DPO` leaves that group
# and the group's sentence is narrowed to the seven it is still true of.
#
# This is the third time a shared reason in this file went half false - the eval
# bench, the retrieval bench, and now the training backends - and each time the
# fix was the same: narrow the reason to the outcomes it still answers for,
# rather than leave the product claiming it cannot do a thing it can.

#: The backend this build drives. `S9_MINT_TRAIN_VERDICT` names three families
#: it hands off to - Unsloth, HF peft+trl, MLX-LM - and this is the second of
#: the peft+trl ones this harness ships. Named rather than searched for, for
#: `THE_LORA_RECIPE`'s reason: which recipe a plan drives is a thing the plan
#: says out loud before anybody approves it.
THE_DPO_RECIPE = "hf-peft-dpo"

#: THE NODE THAT PROPOSES DPO, which is NOT the node that mints the verdict.
#: `S9_MINT_TRAIN_VERDICT` emits nine training outcomes and knows nothing about
#: preferences; this one carries the condition, the `say`, and the one line this
#: build's hardest refusal is quoted from.
_THE_PREFERENCE_NODE = "S5_PREFERENCES_NOT_DEMONSTRATIONS"


def the_preference_prerequisite(spec: diagnosis.Spec | None = None) -> str:
    """The method DPO is declared to come after, read off the ledger.

    TWO PLACES SAY IT AND THEY AGREE, which is why this reads the node rather
    than the methods table: `methods.DPO.prerequisite` is the machine-readable
    half and `S5_PREFERENCES_NOT_DEMONSTRATIONS.prerequisite` is the one beside
    the sentence a person is shown. Nothing in `app/diagnosis.py` reads either -
    measured, by grep, on 2026-08-28 - so the prerequisite is DECLARED AND
    UNENFORCED, and a proposer is the only thing in this product positioned to
    enforce it. Typing "LORA_SFT" here instead would be this file holding an
    opinion about a decision the ledger already made.
    """
    return engine_node_says(_THE_PREFERENCE_NODE, "prerequisite", spec)


def the_preference_floor(spec: diagnosis.Spec | None = None) -> int:
    """How many pairs the ledger's own condition asks for. 0 when unreadable.

    Parsed out of `condition:` rather than typed, for the reason every threshold
    in this file is read: the number is the ledger's and a copy of it here is a
    second place that goes stale. 0 means the condition could not be read as a
    threshold on this fact, and the caller treats that as "no floor to check"
    rather than as zero - a build that refused everything because it could not
    parse a string would be the worst of both.
    """
    condition = engine_node_says(_THE_PREFERENCE_NODE, "condition", spec)
    match = re.search(r"preference_pairs_n\s*>=\s*(\d+)", condition)
    return int(match.group(1)) if match else 0


#: WHAT THIS BUILD IS. One build and not two, and the difference from the SFT
#: outcome is stated in `_why_a_preference_run_is_not_scored_here`: the artifact
#: this run produces is not the artifact `score_the_adapter` can assemble.
_THE_PREFERENCE_BUILD = {
    "id": "dpo_trial_run",
    "title": "Run the preference optimisation on a slice, and measure what the whole of it would cost",
}


def _why_a_preference_run_is_not_scored_here() -> str:
    """Why this build stops at the trial WHILE the adapter scorer is registered.

    THE SFT BUILD GREW A SECOND HALF AND THIS ONE HAS NOT, and the reason is a
    fact about trl rather than a gap in this harness. Read at
    `recipes/hf-peft-dpo/entrypoint.py` merges the SFT adapter into the base
    weights before training, so the policy starts at the SFT weights and the
    reference is the SFT model rather than the raw base. That means the adapter
    this run writes is an adapter over MERGED weights: it does not load onto the
    base model and it does not stack on the SFT adapter. Both of those run and
    return text, which is what makes it worth saying in a plan rather than in a
    README.

    `score_the_adapter` takes a base model and an adapter directory. Pointed at
    this pair it would assemble a model nobody trained, score it, and report the
    number as the preference run's. That is a worse failure than having no
    score: it is a real measurement of the wrong artifact, arriving under the
    right name.

    So the recipe saves the merged base beside the adapter, this build says the
    two travel together, and the comparison is a build for the day a scoring
    step can be handed both. Naming what is absent is the same discipline
    `why_the_full_run_is_not_drawn` applies to the SFT side; the difference is
    that there the missing thing was a tool, and here it is an ARGUMENT.
    """
    return (
        "THIS BUILD MEASURES THE COST AND DOES NOT SCORE THE RESULT, and that "
        "is a fact about the artifact rather than about this harness. "
        + THE_ADAPTER_SCORER
        + " is registered and it takes a base model and an adapter directory. "
        "A preference run continued from your SFT adapter does not produce that "
        "pair: the recipe merges the SFT adapter into the base weights before "
        "attaching the new one, which is the correct setup - the reference this "
        "run is pulled away from is your SFT model and not the raw base - and "
        "it means the adapter that comes out applies to the MERGED weights and "
        "to nothing else. Handed your "
        "base model and this adapter, the scorer would assemble a model nobody "
        "trained and report its score under this run's name, which is worse "
        "than no score. The run saves the merged base beside the adapter for "
        "exactly this reason; the two travel together, and the comparison is a "
        "build for the day a scoring step can be handed both."
    )


def _propose_train_on_preferences(situation: Situation) -> Build:
    """`TRAIN__DPO` - the second verdict with a real backend under it.

    **WHAT MAKES THIS NOT A COPY OF THE SFT BUILD.** Four things, and each of
    them is a refusal rather than a step:

    1. **The prerequisite is enforced here or nowhere.** The ledger declares
       `DPO: {prerequisite: LORA_SFT}` in two places and `app/diagnosis.py`
       reads neither. A DPO run that started from the base model would be
       preference optimisation of a model that has never seen the task, which
       is the thing the node's own `say` tells people not to do - *collect
       pairs and run preference optimization AFTER AN SFT PASS.* So
       `adapter_dir` is required, and the refusal quotes the line.
    2. **The data contract is a different contract.** DPO trains on
       prompt/chosen/rejected triples. The SFT recipe's file - a `text`, or a
       prompt with the answer beside it - is not fewer preferences, it is a
       different objective, and pointed at it this build names `hf-peft-lora`
       rather than reporting zero.
    3. **The count is read off the ledger and not off the file.** This proposer
       opens nothing. `count_preference_pairs` is the instrument, and what this
       checks is that the number on file is a MEASURED count OF THE FILE THIS
       PLAN WOULD TRAIN ON - the distinction `a_measurement_of` exists for, and
       the one that made "12 of 55 covered" mean something different from what
       it looked like.
    4. **It ends at the trial and says why in terms of the artifact.** See
       `_why_a_preference_run_is_not_scored_here`. The SFT build stops for want
       of a run to compare against; this one stops because the thing it makes
       is not the thing the scorer can load.

    Everything else is deliberately the SFT build's shape - the same fit check,
    the same leak check, the same disposable sandbox, the same bounded run whose
    seconds and peak VRAM are the measurement. A person who has approved one of
    these should not have to learn a second product to approve the other.
    """
    missing = training_tools_missing()
    if missing:
        raise NotEnoughToPropose(
            "The preference-optimisation build is not drawable in this harness: "
            f"{list(missing)} of {list(THE_TRAINING_TOOLS)} are not registered "
            "tools. It shares its instruments with the supervised build - the "
            "fit check, the leak check and the sandbox are the same ones - so "
            "what is absent here is absent there too.",
            needs=tuple(missing),
        )

    # REFUSAL: THE BACKEND IS NOT BUILT ON THIS MACHINE. The same reading as the
    # SFT build takes, asked of a different recipe through the same function -
    # which is why `the_recipe_on_this_machine` takes a name. Two copies of this
    # check would be two opinions about whether an environment exists.
    recipe = the_recipe_on_this_machine(THE_DPO_RECIPE)
    if not recipe.get("pinned") or THE_TRAINING_KIND not in (recipe.get("kinds") or ()):
        raise NotEnoughToPropose(
            f"The {THE_DPO_RECIPE} backend is not ready on this machine, so "
            "there is nothing here to drive. "
            + (
                str(recipe.get("why") or "")
                or f"It declares kinds {list(recipe.get('kinds') or ())}, which "
                f"does not include {THE_TRAINING_KIND!r}."
            )
            + " list_recipes reports what each backend needs and prints the "
            "exact commands to build its environment. It is a separate "
            f"environment from {THE_LORA_RECIPE}'s and it is about the same "
            "size, even though the pinned versions are identical - two recipes "
            "sharing one virtualenv are two plans that could drift apart with "
            "nowhere to put the difference. A plan that named an unbuilt "
            "environment would be a plan whose own recipe refuses it after you "
            "approved it.",
            needs=(f"the {THE_DPO_RECIPE} pinned environment",),
        )

    # REFUSAL: THE PREREQUISITE, AND IT IS THE ONE THIS BUILD EXISTS TO ENFORCE.
    prerequisite = the_preference_prerequisite(situation.spec)
    adapter = str(situation.adapter_dir or "").strip()
    if not adapter:
        raise NotEnoughToPropose(
            "I need adapter_dir: the adapter a supervised fine-tune already "
            "produced, which this preference run continues from. "
            + (
                f"The ledger declares this and nothing in the engine enforces "
                f"it - {_THE_PREFERENCE_NODE} states `prerequisite: "
                f"{prerequisite}`"
                if prerequisite
                else "The ledger declares a prerequisite for this method and "
                f"{_THE_PREFERENCE_NODE} does not state which"
            )
            + ", and its own sentence is: "
            + repr(engine_node_says(_THE_PREFERENCE_NODE, "say", situation.spec))
            + ". Preference optimisation moves a model AWAY FROM WHAT IT "
            "ALREADY DOES, so a run that started from the base model would be "
            "pulling a model away from a task it has never seen - the pairs "
            "would teach it style before they taught it the job, and the loss "
            "would fall the whole time. Point adapter_dir at the directory "
            f"{THE_LORA_RECIPE} wrote, or run that fine-tune first.",
            needs=("adapter_dir",),
        )
    if not (Path(adapter) / "adapter_config.json").is_file():
        raise NotEnoughToPropose(
            f"There is no adapter_config.json in {adapter}, so that directory "
            "is not an adapter this run could continue from. The recipe refuses "
            "the same thing at minute one, and a step that fails there has "
            "still taken the slot and still needed an approval. It should be "
            f"the directory {THE_LORA_RECIPE} wrote - the one holding "
            "adapter_config.json and the adapter weights beside it.",
            needs=("adapter_dir",),
        )

    # REFUSAL: I WILL NOT PICK THE MODEL. Same refusal, same reason, and one
    # more of them here: the base model has to be the one the SFT adapter was
    # trained against, which is a fact about your run that this file cannot read
    # off an adapter directory reliably.
    base_model = str(situation.base_model or "").strip()
    if not base_model:
        raise NotEnoughToPropose(
            "I can plan the preference run and I will not choose what it runs "
            "on. Give me base_model - the Hugging Face repo the adapter in "
            f"{adapter} was fine-tuned from. It has to be that one: an adapter "
            "is a difference from particular weights, and loading it onto a "
            "different model produces something that runs, returns text, and is "
            "not what anybody trained. find_models ranks candidates and returns "
            "what it threw out, so a ranking is help rather than a decision.",
            needs=("base_model",),
        )

    # REFUSAL: I WILL NOT PICK THE EXAMPLE LENGTH. The SFT build's reason, and
    # the arithmetic is worse here: a preference row is a prompt and TWO
    # answers, so a length guessed against demonstrations is short by roughly a
    # response every time, and it is the truncated half that carries the signal.
    length = max(0, _an_integer(situation.max_seq_len))
    if length <= 0:
        raise NotEnoughToPropose(
            "I need max_seq_len: how many tokens long a training example is. "
            "It sets the activation and logits terms, which are most of what "
            "moves in the memory budget, and it is what the trial below times "
            "itself against - a fit answer computed at one length beside a run "
            "executed at another is two facts about two different runs. Ask it "
            "of a PREFERENCE row rather than of a demonstration: the row is a "
            "prompt and two complete answers, so a length carried over from "
            "the supervised pass is short by about one response, and the end "
            "that gets truncated is where the two answers differ.",
            needs=("max_seq_len",),
        )

    preferences = situation.require_path("dataset_path")
    evaluation = situation.require_path("eval_path")

    preference_subject = Subject.of_path(preferences)
    eval_subject = Subject.of_path(evaluation)

    # REFUSAL: THE EVAL SET IS THE TRAINING DATA, OR IS INSIDE IT. The SFT
    # build's refusal, unchanged, because the defect is unchanged: a model
    # scored on rows it was trained on returns a high number whatever happened.
    inside = _the_eval_set_is_inside(evaluation, preferences)
    if preference_subject.key == eval_subject.key or inside:
        raise NotEnoughToPropose(
            (
                f"Your preference pairs and your eval set are the same file "
                f"({preference_subject.key})."
                if preference_subject.key == eval_subject.key
                else f"Your eval set is inside the preference data you asked me "
                f"to train on: {eval_subject.key} is under "
                f"{preference_subject.key}."
            )
            + " Then whatever comes out is judged on rows it learned from, and "
            "the number measures recall of the training set rather than "
            "anything about your task. Point dataset_path at the pairs and "
            "eval_path at what the result is judged on, and keep them apart.",
            needs=("dataset_path", "eval_path"),
        )

    # REFUSAL: THE RECIPE READS JSONL. After the leak check, for the reason the
    # SFT build puts it there: a folder holding both files fails both tests and
    # the one worth telling somebody about is the leak.
    if Path(preferences).suffix.lower() != ".jsonl":
        raise NotEnoughToPropose(
            f"{preference_subject.key} is not a .jsonl file, and "
            f"{THE_DPO_RECIPE} reads its training data as JSONL - one JSON "
            "object per line, each carrying a prompt, the answer you preferred "
            "and the one you did not. Convert it first.",
            needs=("dataset_path",),
        )

    # REFUSAL: NOBODY HAS COUNTED THE PAIRS IN THIS FILE.
    #
    # THE OUTCOME IS ONLY REACHABLE BECAUSE SOME preference_pairs_n ROUTED, and
    # that says nothing about WHICH FILE was counted. It is the eval_size_n
    # defect in the one place it would be most expensive: hours of GPU planned
    # against a count of somebody else's file.
    #
    # AND UNTIL THIS MILESTONE THERE WAS NO HONEST WAY TO SATISFY IT.
    # `evidence.resolves` reported, in the words the frontier shows a person,
    # that no registered instrument produced this fact at all.
    # `count_preference_pairs` is that instrument, and this refusal names it.
    counted_here, counted_of = a_measurement_of(
        situation, "preference_pairs_n", preferences
    )
    if not counted_here:
        raise NotEnoughToPropose(
            "The preference pairs this run would train on have not been "
            "counted. "
            + (
                f"What is on file is a count of {counted_of.key}, and that is "
                f"not {preference_subject.key}"
                if counted_of is not None
                else "preference_pairs_n is on file as "
                f"{situation.values.get('preference_pairs_n')!r} and nothing "
                "recorded which file it counted"
            )
            + ". Run count_preference_pairs on this file and ask again. It "
            "counts COMPLETE rows - a prompt, a chosen answer and a rejected "
            "one, all three with something in them - because a row missing one "
            "of them is not half a preference, it is a row this recipe cannot "
            "learn from. If the file turns out to hold demonstrations instead, "
            "it says so and names the recipe that wants them rather than "
            "reporting a zero.",
            needs=("preference_pairs_n", "dataset_path"),
        )

    pairs = _an_integer(situation.values.get("preference_pairs_n"))
    floor = the_preference_floor(situation.spec)
    if pairs < floor:
        raise NotEnoughToPropose(
            f"{preference_subject.key} holds {pairs:,} complete preference "
            f"pairs and the ledger's own condition for this route asks for "
            f"{floor:,}: {_THE_PREFERENCE_NODE} reads "
            + repr(engine_node_says(_THE_PREFERENCE_NODE, "condition", situation.spec))
            + ". That number is not this file's opinion and it is not mine - it "
            "is the threshold the engine used to send you here, and a run below "
            "it fits a preference model to noise and reports a falling loss "
            "while doing it. count_preference_pairs also reports the rows that "
            "carry SOME of the three fields and not all three; if there are "
            "many, the gap between what you have and what this asks for may be "
            "a column name rather than more work.",
            needs=(f"{floor:,} preference pairs",),
        )

    # REFUSAL: NOTHING HERE TO TRAIN ON. The SFT build's, unchanged.
    if situation.values.get("accelerator") == "cpu_only":
        raise NotEnoughToPropose(
            "This machine reports no accelerator - accelerator is on file as "
            f"{situation.values.get('accelerator')!r} - and a preference run on "
            "CPU is not slow, it is a different order of magnitude. The recipe "
            "refuses the CPU-only torch wheel in its own preflight for the same "
            "reason, and it refuses rather than warning because every setup "
            "step succeeds on that wheel and the only symptom is twenty times "
            "the wall clock with no error anywhere.",
            needs=("a GPU",),
        )

    # REFUSAL: THIS DATA IS ALREADY IN A SANDBOX ON THIS MACHINE.
    already = sandboxes_already_holding(preferences)
    if already:
        raise NotEnoughToPropose(
            f"A sandbox on this machine already holds a snapshot of "
            f"{preference_subject.key}: {list(already)}. Making a second one "
            "copies your pairs again, builds a second pinned environment beside "
            "the first, and leaves two experiments in this transcript that "
            "nobody can tell apart. list_sandboxes says what each one pinned "
            "and what it holds; run_in_sandbox continues the one that is there, "
            "and delete_sandbox removes it if it went wrong.",
            needs=("a sandbox to resume, or delete_sandbox",),
        )

    # WHAT THE ENGINE'S OWN TABLE SAYS THIS RUN IS. The rank band is
    # `S9_SIZE_TO_METHOD`'s cell, matched to the person's labelled-example count
    # before this file was reached, and it is read rather than typed for the
    # reason the SFT build reads it.
    #
    # `beta` IS DELIBERATELY NOT SET HERE. It is DPO's own knob - how hard to
    # move away from the reference - and no table in the ledger names one, so
    # setting a number would be this file inventing a hyperparameter and calling
    # it the engine's. The recipe's default stands and the plan says so.
    size_row = dict(situation.result.size_row or {})
    rank = _an_integer(size_row.get("rank_min"))

    trial_config: dict[str, Any] = {
        "base_model": base_model,
        "dataset_path": preferences,
        "adapter_dir": adapter,
        "max_seq_len": length,
    }
    if rank > 0:
        trial_config["lora_r"] = rank
    steps_asked = max(0, _an_integer(situation.trial_steps))
    if steps_asked > 0:
        trial_config["max_steps"] = steps_asked

    # THE FIT QUESTION IS ASKED AT `lora` AND THE REASON IS A READING OF trl.
    # A preference run looks like it should need two models - a policy and a
    # reference - and that is what would double the residency this check sizes.
    # It does not: trl serves the reference by DISABLING the adapter on the
    # model already loaded (`dpo_trainer.py:915-921`, `:934-936`), and refuses a
    # `ref_model` passed beside a `peft_config` at `:582-586`. So one set of
    # base weights, and `lora` is the honest method word.
    route = str(situation.result.route or "")
    method = _the_method_for(route)
    if not method:
        raise NotEnoughToPropose(
            "The engine routed this run to "
            + repr(route)
            + " and this build asks the fit question at LoRA precision, because "
            f"{THE_DPO_RECIPE} attaches an adapter to a model loaded normally "
            "and quantises nothing. On that route the engine's own VRAM table "
            "says this card cannot hold the base model that way, which is an "
            "answer rather than something to talk past. A quantised recipe is a "
            "recipe this harness does not ship.",
            needs=(f"a run the engine routes to LORA, not {route!r}",),
        )

    reading = _a_call_that_fits(
        "read_model_config", {"repo_id": base_model}, must_carry=("repo_id",)
    )
    fitting = _a_call_that_fits(
        "can_this_machine_train",
        {"repo_id": base_model, "method": method, "seq_len": length},
        must_carry=("repo_id", "method", "seq_len"),
    )
    leaking = _a_call_that_fits(
        "check_split_leakage",
        {"train_path": preferences, "eval_path": evaluation},
        must_carry=("train_path", "eval_path"),
    )

    steps: list[Step] = []

    if not situation.is_measured("vram_gb"):
        steps.append(
            Step(
                id="card",
                tool="inspect_hardware",
                why=(
                    "Read this machine before deciding what fits on it. Nobody "
                    "has measured this card in this conversation - vram_gb is "
                    f"on file as {situation.values.get('vram_gb')!r} with origin "
                    f"{situation.origin('vram_gb') or 'nothing recorded'} - and "
                    "the fit question below is video memory against a real "
                    "geometry. A VRAM figure that was defaulted is not a "
                    "measurement of this machine."
                ),
                arguments={},
                produces=(
                    Output(
                        "vram_gb",
                        "number",
                        "how much video memory this card actually has",
                        at="vram_gb",
                    ),
                ),
                needs=(),
                cost=_local_cost(
                    "inspect_hardware",
                    find_out_by="it reads the driver and returns; time one call",
                ),
                exit_criterion=ExitCriterion(
                    stated=(
                        "the video memory was MEASURED off this card rather than "
                        "defaulted. A card nobody could read is reported as "
                        "defaulted and stamps nothing, and a fit verdict "
                        "computed from a defaulted number is a different claim "
                        "from one computed from a measured GPU"
                    ),
                    source="tool_result",
                    subject="provenance.vram_gb",
                    comparator="equals",
                    value="measured",
                ),
                operates_on=None,
            )
        )

    steps.append(
        Step(
            id="config",
            tool="read_model_config",
            why=(
                "Read this model's real geometry off the Hub - layers, hidden "
                "size, vocabulary, attention heads - rather than guessing it "
                "from the name. The memory arithmetic below is that geometry "
                "against this card, and a parameter count taken from a repo "
                "name is the kind of number that is right until it is not."
            ),
            arguments=reading,
            produces=(
                Output(
                    "geometry",
                    "object",
                    "the config.json this model publishes",
                    at="config",
                ),
            ),
            needs=tuple("card" for _ in range(1) if not situation.is_measured("vram_gb")),
            cost=_hub_cost(
                "read_model_config",
                find_out_by=(
                    "one HTTPS request for one small JSON file; time one fetch"
                ),
            ),
            exit_criterion=ExitCriterion(
                stated=(
                    "the config was read AND it carries a vocabulary size. That "
                    "is the term the logits buffer is computed from, and a "
                    "config with no vocabulary describes something that is not "
                    "an autoregressive text decoder - for which the memory "
                    "verdict stays UNKNOWN rather than becoming a yes"
                ),
                source="tool_result",
                subject="geometry.vocab_size",
                comparator="exists",
            ),
            operates_on=None,
        )
    )

    steps.append(
        Step(
            id="fits",
            tool="can_this_machine_train",
            why=(
                "Ask whether this run fits on this card BEFORE anything is "
                "downloaded or copied. It is asked at LoRA precision, and a "
                "preference run is the case where that looks wrong: DPO needs a "
                "reference model to be pulled away from, and a second copy of "
                "the base weights would not fit anywhere this one does. It does "
                "not need a second copy - trl serves the reference by disabling "
                "the adapter on the model already loaded, and refuses a "
                "ref_model passed beside an adapter config. So the residency is "
                "one set of base weights, and this check is sizing the run that "
                "will actually happen."
            ),
            arguments=fitting,
            produces=(
                Output(
                    "verdict",
                    "object",
                    "whether it fits, and the terms of the arithmetic it fits by",
                    at="fits",
                ),
            ),
            needs=("config",),
            cost=_hub_cost(
                "can_this_machine_train",
                find_out_by=(
                    "arithmetic over one config it has already read; time one call"
                ),
            ),
            exit_criterion=ExitCriterion(
                stated=(
                    "it FITS. A run planned onto a card that cannot hold it is "
                    "an out-of-memory error an hour in, after the weights have "
                    "downloaded and the data has been copied"
                ),
                source="tool_result",
                subject="fits",
                comparator="is_true",
            ),
            operates_on=None,
        )
    )

    steps.append(
        Step(
            id="leak",
            tool="check_split_leakage",
            why=(
                "Check that the rows this learns preferences from are not the "
                "rows it will be judged on, including near-identical ones. This "
                "is the row-level version of the refusal this plan already made "
                "about the two paths: those are different files, and different "
                "files can still share rows."
            ),
            arguments=leaking,
            produces=(
                Output(
                    "overlap",
                    "object",
                    "how many rows appear on both sides, exactly and nearly",
                    at="overlap",
                ),
            ),
            needs=("fits",),
            cost=_local_cost(
                "check_split_leakage",
                find_out_by=(
                    "it indexes both files and compares; time it on a file this "
                    "size, once"
                ),
            ),
            exit_criterion=ExitCriterion(
                stated=(
                    "no rows overlap. Preferences learned from rows the eval set "
                    "also holds produce a number that measures memory rather "
                    "than learning - and a high one, which is worse than a low "
                    "one"
                ),
                source="tool_result",
                subject="overlap.exact",
                comparator="equals",
                value=0,
            ),
            # NOT `Subject.of_path(preferences)`, AND THE CHECK IS RIGHT TO
            # REFUSE IT. `check_split_leakage` takes two paths and declares no
            # `subject=`, so nothing here can show WHICH of them the step opens -
            # and it opens both. A second statement of what a step runs on, that
            # nothing checks, is how a cost measured off the wrong file passes a
            # check that reads the declaration. The SFT build says None here for
            # the same reason.
            operates_on=None,
        )
    )

    egress = _egress_for_the_hub([step.tool for step in steps], weights=True)

    sandboxing = _a_call_that_fits(
        "make_sandbox",
        {
            "purpose": (
                "a bounded trial of the "
                + THE_DPO_RECIPE
                + " preference run, to measure what the whole run would cost on "
                "this machine before any of it is spent"
            ),
            "recipe": THE_DPO_RECIPE,
            "data": [preferences],
            "egress": True,
            "egress_reason": egress,
        },
        must_carry=("recipe", "data", "egress", "egress_reason"),
    )
    steps.append(
        Step(
            id="sandbox",
            tool="make_sandbox",
            why=(
                "Make the isolated place this runs in, and make it part of the "
                f"build rather than something you set up first. It pins the "
                f"{THE_DPO_RECIPE} environment - a separate one from "
                f"{THE_LORA_RECIPE}'s, and the locked requirements on the "
                "environment below are read off this recipe's own lockfile - "
                "takes a snapshot of your preference file as it is right now "
                "with its size, modification time and digest, and gets its own "
                "working directory so an experiment that goes wrong is deleted "
                "rather than untangled."
            ),
            arguments=sandboxing,
            produces=(
                Output(
                    "sandbox_name",
                    "string",
                    "what this sandbox is called, so the step below names it "
                    "rather than taking whichever one is newest",
                    at="name",
                ),
                Output(
                    "fingerprint",
                    "string",
                    "what this sandbox IS, as a digest - the reproducibility "
                    "claim, checkable",
                    at="fingerprint",
                ),
            ),
            needs=("fits", "leak"),
            cost=_local_cost(
                "make_sandbox",
                find_out_by=(
                    "it copies your preference file and reads a lockfile; the "
                    "copy is the whole of it, so time one copy of a file this size"
                ),
            ),
            exit_criterion=ExitCriterion(
                stated=(
                    "the environment is PINNED: the recipe's own virtualenv is "
                    "built and its lockfile is there. A sandbox that pins "
                    "nothing is isolated and disposable and NOT reproducible"
                ),
                source="tool_result",
                subject="pinned.pinned",
                comparator="is_true",
            ),
            operates_on=None,
            risks=(
                Risk(
                    what=(
                        "the adapter this continues from is outside the sandbox "
                        "and is not snapshotted with the data"
                    ),
                    what_we_do=(
                        "it is named in the run's config and read where it is. "
                        f"An adapter directory is weights, and snapshotting it "
                        "beside every trial would copy gigabytes to record "
                        "something that is already a file on this machine. What "
                        "is lost is said rather than discovered: if you retrain "
                        f"the adapter at {adapter} between approving this and "
                        "running it, this sandbox cannot tell"
                    ),
                ),
                Risk(
                    what=(
                        "'no egress' is read as a guarantee the operating system "
                        "is enforcing"
                    ),
                    what_we_do=(
                        "the sandbox says so itself, in its own reply: there is "
                        "no network namespace, no firewall rule and no "
                        "container, so what it guarantees is what it HANDS a "
                        "run. This one declares egress anyway and says why, "
                        "which is the honest version of the same sentence"
                    ),
                ),
            ),
        )
    )

    running = _a_call_that_fits(
        "run_in_sandbox",
        {
            "name": Ref("sandbox", "sandbox_name"),
            "kind": THE_TRAINING_KIND,
            "config": trial_config,
        },
        must_carry=("name", "kind", "config"),
    )
    steps.append(
        Step(
            id="trial",
            tool="run_in_sandbox",
            why=(
                "Run the real recipe, on your real pairs, on this card - "
                "bounded, and only far enough to find out what it costs. This "
                "is the step every UNKNOWN wall-clock estimate in this plan "
                "points at: nothing in this harness has timed a preference step "
                "on this machine, so any figure here would be invented. What "
                "comes back is measured - the seconds, the steps done and the "
                "peak video memory - and it is what the whole run can be priced "
                "against afterwards. The recipe refuses before it trains if the "
                "file is demonstrations rather than preferences, if the torch "
                "wheel is the CPU-only one, or if there are too few pairs to "
                "learn anything from; each of those is a refusal rather than a "
                "warning, because each of them otherwise produces a real "
                "adapter from a meaningless run."
            ),
            arguments=running,
            produces=(
                Output(
                    "seconds",
                    "number",
                    "how long the bounded run actually took on this machine",
                    at="seconds",
                ),
                Output(
                    "peak_vram_gb",
                    "number",
                    "the high-water mark of video memory, measured rather than "
                    "predicted",
                    at="peak_vram_gb",
                ),
                Output(
                    "adapter_dir",
                    "string",
                    "where the preference adapter was written - together with "
                    "the merged base it applies to, which travels with it",
                    at="adapter_dir",
                ),
            ),
            needs=("sandbox",),
            cost=Cost(
                model_tokens=Estimate.none(
                    build.MODEL_TOKENS,
                    because=(
                        "run_in_sandbox declares reads="
                        f"{list(_spec('run_in_sandbox').reads)}, which does not "
                        f"include `{THE_SCORING_READ}`, so nothing in this run "
                        "reaches the model you connected. A preference run is "
                        "your machine's time, not a bill"
                    ),
                ),
                model_requests=Estimate.none(
                    build.MODEL_REQUESTS,
                    because=(
                        "the same declaration - run_in_sandbox reads "
                        f"{list(_spec('run_in_sandbox').reads)} and not "
                        f"`{THE_SCORING_READ}` - so this run asks your model "
                        "nothing, not once"
                    ),
                ),
                wall_clock=_wall_clock(
                    "run_in_sandbox",
                    find_out_by=(
                        "THIS STEP IS THE ANSWER. Nothing on this machine has "
                        "timed a preference-optimisation step, and it is not the "
                        "same measurement as a supervised one even where one "
                        "exists: every optimizer step here scores TWO answers "
                        "under the policy and both again under the reference, so "
                        "a second per step from an SFT run is not a second per "
                        "step here. The recipe prints elapsed seconds, steps "
                        "done and peak VRAM as it runs, so a bounded slice is a "
                        "measurement of the whole - and the run is killed at the "
                        "sandbox's own timeout, which bounds what not knowing "
                        "can cost you"
                    ),
                ),
                disk=_disk_cost("run_in_sandbox"),
            ),
            exit_criterion=ExitCriterion(
                stated=(
                    "the run returns 0 - the pipeline held together on this "
                    "machine, and the seconds and the peak memory are now "
                    "measured rather than guessed. This is a criterion about a "
                    "MEASUREMENT HAVING BEEN TAKEN and not about the "
                    "preferences having been learned; the second one is a "
                    "comparison and no step here takes it"
                ),
                source="outputs",
                subject="trial.exit_code",
                comparator="equals",
                value=0,
            ),
            # None, AND THE SANDBOX IS WHY. This call names its sandbox with a
            # `Ref` to the step above, so which directory it opens is decided
            # while the plan runs; a cost established now cannot be shown to be
            # about a file nobody has named yet. The file itself is declared
            # where it can be checked - the environment's `data`, which is a
            # snapshot of this exact path taken before anything runs.
            operates_on=None,
        )
    )

    said = str(situation.result.say or "").strip()
    hand_off = engine_node_says("S9_MINT_TRAIN_VERDICT", "hand_off", situation.spec)

    criterion = (
        "the bounded run returns 0 on this card, and the seconds and the peak "
        "video memory it reports become the measured basis for pricing the "
        "whole run. "
        + _why_a_preference_run_is_not_scored_here()
    )

    because = (
        "The engine reached "
        + repr(situation.outcome)
        + " at "
        + _THE_PREFERENCE_NODE
        + ", whose condition is "
        + repr(engine_node_says(_THE_PREFERENCE_NODE, "condition", situation.spec))
        + " and whose own sentence is "
        + repr(said)
        + ". Both halves of that condition are on file for this conversation: "
        + f"{pairs:,} complete preference pairs, counted in "
        + preference_subject.key
        + " by count_preference_pairs rather than taken from anybody, against "
        + f"the ledger's floor of {floor:,}; and user_can_rank_but_not_write, "
        + "which is yours to say and which you said. "
        + "The method's prerequisite is "
        + repr(prerequisite or "declared and unreadable")
        + " and it is met by the adapter at "
        + adapter
        + ", which this run continues from rather than starting beside. "
        + "THE VERDICT HANDS OFF TO A PINNED BACKEND - "
        + repr(hand_off)
        + " - and the one this drives is "
        + THE_DPO_RECIPE
        + ", built on this machine, whose locked requirements are on the "
        "environment below. "
        + "The engine routed this run to "
        + repr(situation.result.route)
        + " against "
        + str(situation.result.hardware_reference)
        + ", and the adapter rank comes from its own size table rather than "
        "from a preference here: "
        + repr(size_row.get("rank"))
        + ", of which this trial takes the cheap end, "
        + repr(size_row.get("rank_min"))
        + ", because it is measuring cost rather than quality. "
        + "beta - how hard a preference run is pulled away from its reference - "
        "is NOT set by this plan: no table in the ledger names one, and a "
        "number invented here would arrive wearing the engine's authority. The "
        "recipe's own default stands. "
        + _why_a_preference_run_is_not_scored_here()
        + " "
        + egress
    )

    return Build(
        id=_THE_PREFERENCE_BUILD["id"],
        title=_THE_PREFERENCE_BUILD["title"],
        for_outcome=situation.outcome,
        because=because,
        steps=tuple(steps),
        environment=Environment(
            name=_THE_PREFERENCE_BUILD["id"],
            working_dir=f"runs/proposals/{_THE_PREFERENCE_BUILD['id']}",
            egress=True,
            egress_reason=egress,
            data=tuple(
                build.DataSnapshot.of(path)
                for path in (preferences, evaluation)
                if path
            ),
            installs=tuple(recipe.get("installs") or ()),
            python=str(recipe.get("python") or ""),
        ),
        exit_criterion=ExitCriterion(
            stated=criterion,
            source="outputs",
            subject="trial.exit_code",
            comparator="equals",
            value=0,
        ),
        risks=(
            Risk(
                what=(
                    "this build ends with a measured cost and no scored model, "
                    "which is less than the verdict promised"
                ),
                what_we_do=(
                    "it is less, and the reason is stated rather than left as a "
                    "gap: the adapter a preference run produces applies to "
                    "SFT-merged weights, and the scorer this harness has takes a "
                    "base model and an adapter. Handing it the pair it expects "
                    "would score a model nobody trained. The run saves the "
                    "merged base beside the adapter so the comparison is "
                    "possible the day a scoring step can take both"
                ),
            ),
            Risk(
                what=(
                    "a falling loss curve is read as evidence the preferences "
                    "were learned"
                ),
                what_we_do=(
                    "it is evidence about the MACHINE and the PIPELINE and "
                    "nothing else, and preference optimisation is the worst "
                    "place in this product to read a loss curve: the objective "
                    "is a margin between two answers, so the loss falls "
                    "whenever the model separates them - including when it "
                    "separates them on length, or on formatting, or on which "
                    "one was written first. Whether the result is better is "
                    "decided by a comparison on your own eval set, and no step "
                    "here takes it"
                ),
            ),
            Risk(
                what=(
                    "the preference adapter is deployed on top of the SFT "
                    "adapter, or on the base model"
                ),
                what_we_do=(
                    "neither works and both run. trl merges the SFT adapter "
                    "down before attaching this one, so what comes out is a "
                    "difference from the MERGED weights - loaded onto the raw "
                    "base it is a difference from something else, and stacked "
                    "on the SFT adapter it is that difference applied twice. "
                    "The run writes the merged base beside the adapter and says "
                    "so in its own log; they travel together or neither is "
                    "usable"
                ),
            ),
            Risk(
                what=(
                    "the sandbox and the downloaded weights take disk that is "
                    "never reclaimed"
                ),
                what_we_do=(
                    "the sandbox is disposable by design and its own reply gives "
                    "you the delete_sandbox call that removes it. The weights "
                    "land in your Hugging Face cache and stay there, which is "
                    "what makes the next run cheaper and is worth knowing before "
                    "the first one"
                ),
            ),
        ),
        facts=dict(situation.origins),
    )


# ---------------------------------------------------------------------------
# THE THIRD LEDGER'S BUILDS.
#
# `docs/ledgers/harness_design.yaml` asks whether to build a harness at all, and
# `app/tools/harness.py` is its six instruments. Every build below is one of
# those instruments plus `run_diagnosis`, which is the shape the second ledger's
# builds already have and it is the honest one for this domain: THIS HARNESS
# CANNOT BUILD SOMEBODY'S HARNESS. What it can do is take the measurement the
# verdict is waiting on, off files the person already has, and walk the tree
# again - and the exit criterion is always about the LEDGER holding the fact,
# never about the tool having returned.
#
# The refusals are not here and that is the product rather than a gap. Eleven of
# this ledger's twenty-eight outcomes are `NO_HARNESS__`, `NO_TOOLING__` or
# `HANDOFF__`; each one is a complete answer, and `NOT_COVERED` says so in the
# words `NO_AGENT__A_SCRIPT` already uses.

#: The six instruments this ledger's builds are made of. A roster rather than a
#: literal at each site, for `THE_TRAINING_TOOLS`'s reason: a build that names a
#: tool nobody registered is a plan that fails after you approved it, and the
#: check has to be a reading of the live registry rather than a memory.
THE_HARNESS_TOOLS: tuple[str, ...] = (
    "read_the_success_check",
    "count_the_task_set",
    "score_a_recorded_run",
    "ablate_a_component",
    "read_the_tool_risks",
    "bound_the_harness_run",
)


def harness_tools_missing() -> tuple[str, ...]:
    """Which of them are not registered in this process, right now."""
    return tuple(name for name in THE_HARNESS_TOOLS if REGISTRY.get(name) is None)


def the_harness_bench_is_registered() -> bool:
    return not harness_tools_missing()


def _harness_step(
    step_id: str,
    tool_name: str,
    *,
    why: str,
    arguments: dict[str, Any],
    produces: tuple[Output, ...],
    stated: str,
    subject: str,
    comparator: str = "exists",
    find_out_by: str,
    needs: tuple[str, ...] = (),
    operates_on: Subject | None = None,
) -> Step:
    """One instrument, drawn once. Every harness build is made of these.

    A shared constructor rather than six near-identical blocks, because the six
    differ only in which file they open and which fact they stamp - and where
    two things differ only in data, writing them out twice is how they drift.
    What is NOT shared is the `why`: each step has to say what it reads and what
    that decides, in the words of this domain, and a generated sentence would be
    the thing this whole file refuses to put in front of somebody.
    """
    return Step(
        id=step_id,
        tool=tool_name,
        why=why,
        arguments=_a_call_that_fits(tool_name, arguments, must_carry=tuple(arguments)),
        produces=produces,
        needs=needs,
        cost=_local_cost(tool_name, find_out_by=find_out_by),
        exit_criterion=ExitCriterion(
            stated=stated, source="tool_result", subject=subject, comparator=comparator
        ),
        operates_on=operates_on,
    )


def _the_checker_step(situation: Situation, needs: tuple[str, ...] = ()) -> Step:
    path = situation.require_path("checker_path")
    return _harness_step(
        "checker",
        "read_the_success_check",
        why=(
            "Read the file that decides whether an answer was right. IT IS READ "
            "AND NOT RUN, which is the whole design of this gate: running your "
            "code is your business, and a first gate's job is to separate "
            "'there is a definition of success' from 'there is not' rather than "
            "to judge the definition. Everything downstream is a comparison, and "
            "a comparison needs a fixed end."
        ),
        arguments={"path": path},
        produces=(
            Output(
                "looks_like_a_program",
                "boolean",
                "whether the file reads as something that could decide a case",
                at="looks_like_a_program",
            ),
        ),
        stated=(
            "the checker was read off this machine and reported as a program or "
            "not - and it was not executed, which the reply says in its own field"
        ),
        subject="looks_like_a_program",
        find_out_by="it opens one file and reads the first 200KB; time one read",
        needs=needs,
        operates_on=Subject.of_path(path),
    )


def _the_task_step(situation: Situation, needs: tuple[str, ...] = ()) -> Step:
    path = situation.require_path("tasks_path")
    _needs_columns(situation, ("input_field", "expected_field"))
    return _harness_step(
        "tasks",
        "count_the_task_set",
        why=(
            "Count the tasks that can actually be graded - the ones carrying "
            "both the task and the outcome that would be right. That second "
            "column is what re-runnable MEANS, so the count and the "
            "re-runnability are one reading rather than a count and a promise. "
            "A row with no expected outcome is not a task yet, and it is "
            "reported rather than quietly left in the denominator."
        ),
        arguments={
            "path": path,
            "input_field": situation.input_field,
            "expected_field": situation.expected_field,
        },
        produces=(
            Output("gradeable", "integer", "how many rows can be graded", at="gradeable_tasks"),
            Output("can_rerun", "boolean", "whether every row can be", at="can_rerun"),
        ),
        stated="the harness has counted the tasks it can grade in this file",
        subject="gradeable_tasks",
        find_out_by="it scans the file once; time one scan at this size",
        needs=needs,
        operates_on=Subject.of_path(path),
    )


def _the_tool_risk_step(situation: Situation, needs: tuple[str, ...] = ()) -> Step:
    path = situation.require_path("tooldefs_path")
    return _harness_step(
        "tools",
        "read_the_tool_risks",
        why=(
            "Count the tools this can reach and how many of them say what they "
            "can destroy. It reads the annotations off the file and NEVER "
            "guesses a tool's risk from its name - a tool called `sync` that "
            "carries `destructiveHint` is annotated and a tool called "
            "`delete_everything` that carries nothing is not. What a tool can "
            "destroy is the one property of a harness that is not recoverable "
            "when it turns out to be wrong."
        ),
        arguments={"path": path},
        produces=(
            Output("tool_count", "integer", "how many tools were declared", at="tool_count"),
            Output(
                "risk_annotated",
                "integer",
                "how many of them say what they can destroy",
                at="risk_annotated",
            ),
        ),
        stated="the tool definitions were read and counted off this machine",
        subject="tool_count",
        find_out_by="it reads one definitions file; time one read",
        needs=needs,
        operates_on=Subject.of_path(path),
    )


def _the_bound_step(situation: Situation, needs: tuple[str, ...] = ()) -> Step:
    path = situation.require_path("trace_path")
    return _harness_step(
        "bound",
        "bound_the_harness_run",
        why=(
            "Read one run's spans for the two facts an approval is made of: what "
            "it costs in tokens and whether it stopped. DENOMINATED IN TOKENS "
            "AND NOT IN MONEY, because a price is a fact about somebody's "
            "contract on a Tuesday. It refuses to total a run where any "
            "inference span carries no usage attributes - a partial sum is a "
            "lower bound and a lower bound is the number that is always smaller "
            "than the bill."
        ),
        arguments={"path": path},
        produces=(
            Output("runs", "integer", "how many runs were in the trace", at="runs"),
            Output("has_traces", "boolean", "whether anything was readable", at="has_traces"),
        ),
        stated="spans were read off this machine and the runs in them counted",
        subject="runs",
        find_out_by="it parses one trace file; time one parse at this size",
        needs=needs,
        operates_on=Subject.of_path(path),
    )


def _needs_columns(situation: Situation, names: tuple[str, ...]) -> None:
    """Refuse before the plan when a column nobody named would be guessed.

    `_tool_layer_step_list`'s rule, and its reason: a refusal before the plan is
    cheap and a refusal after approval is not. It checks EVERY name it asks for,
    because the version that checked one while asking for three drew a plan that
    failed at run time on the other two.
    """
    missing = tuple(
        name for name in names if not str(getattr(situation, name, "") or "").strip()
    )
    if missing:
        raise NotEnoughToPropose(
            "I cannot grade a recording without knowing which columns hold what. "
            "Missing: "
            + ", ".join(missing)
            + ". Which column is the answer is a statement about your file that "
            "only you can make, and a wrong guess grades the whole set against "
            "the wrong text.",
            needs=missing,
        )


def _harness_build(
    situation: Situation,
    *,
    build_id: str,
    title: str,
    because: str,
    steps: list[Step],
    fact: str,
    criterion: str,
    paths: tuple[str, ...],
    risks: tuple[Risk, ...] = (),
) -> Build:
    """Every harness build ends the same way and the ending is the point.

    The last step is `run_diagnosis` and the exit criterion reads the LEDGER
    rather than the tool. `docs/PRODUCT_SPEC.md` 6.4: a bench never re-decides
    the verdict. The steps write facts; the engine reads them and decides again,
    and what that then means is the engine's to say rather than this plan's.
    """
    steps = list(steps)
    steps.append(
        _recheck_step(
            (steps[-1].id,),
            fact,
            why=(
                "Walk the tree again on the refreshed sheet. Whether the verdict "
                "moves - and toward what - is the engine's sentence on evidence "
                "this build just made current, never this plan's."
            ),
        )
    )
    return Build(
        id=build_id,
        title=title,
        for_outcome=situation.outcome,
        because=because,
        steps=tuple(steps),
        environment=_sandbox(build_id, *paths),
        exit_criterion=ExitCriterion(
            stated=criterion,
            source="diagnosis",
            subject=f"fact_origins.{fact}",
            comparator="is_measured",
        ),
        risks=risks
        or (
            Risk(
                what="the number comes back and the verdict does not move",
                what_we_do=(
                    "that is the build working and it is worth saying before you "
                    "approve it. This plan makes one fact MEASURED; what the "
                    "engine then does with it is the engine's. A build that "
                    "promised a particular verdict would be a build deciding the "
                    "diagnosis, which is the one thing no bench here may do"
                ),
            ),
        ),
        facts=dict(situation.origins),
    )


def _propose_read_the_checker(situation: Situation) -> Build:
    """`SPEC__WRITE_THE_TASK` - the first rung, and it is a reading not a run."""
    checker = situation.require_path("checker_path")
    return _harness_build(
        situation,
        build_id="read_the_success_check",
        title="Read the checker you named, and record whether it is a program",
        because=(
            "You have said there is a definition of success and nothing here has "
            "seen it. That file decides every number after it - the bare model's "
            "rate, whether a component earns its place, whether the whole thing "
            "is worth building - so a checker nobody has looked at is the one "
            "thing it cannot be. This reads it and does not run it."
        ),
        steps=[_the_checker_step(situation)],
        fact="success_check_is_a_program",
        criterion=(
            "success_check_is_a_program is MEASURED - the harness opened the file "
            "you named and read it, rather than taking the claim that it exists"
        ),
        paths=(checker,),
    )


def _propose_count_the_tasks(situation: Situation) -> Build:
    """`SPEC__BUILD_A_STARTER_EVAL` and `SPEC__MAKE_THE_TASKS_RERUNNABLE`.

    ONE BUILD BEHIND TWO OUTCOMES, and the fact it is held to is the difference.
    "There are not enough tasks" and "the tasks cannot be re-run" are two
    readings of one scan - the second is whether every row carries the outcome
    that would be right - so one instrument answers both and the exit criterion
    names whichever one this verdict is waiting on.
    """
    tasks = situation.require_path("tasks_path")
    rerun = situation.outcome == "SPEC__MAKE_THE_TASKS_RERUNNABLE"
    return _harness_build(
        situation,
        build_id="count_the_task_set",
        title=(
            "Count how many of your tasks can actually be graded"
            if not rerun
            else "Find out which of your tasks carry the outcome that would be right"
        ),
        because=(
            "Everything after this is a comparison between runs, and the "
            "denominator of every one of them is this count. "
            + (
                "Re-runnable means every task carries the outcome that would be "
                "right - that is what re-running IS, sending it again and "
                "comparing against something - so the scan that counts them is "
                "the scan that settles it."
                if rerun
                else "The floor is twenty because below it the smallest "
                "difference you can observe is bigger than the difference a "
                "harness is being built to make."
            )
        ),
        steps=[_the_task_step(situation)],
        fact="can_rerun_tasks" if rerun else "harness_tasks_n",
        criterion=(
            (
                "can_rerun_tasks is MEASURED - every row was checked for the "
                "outcome that would be right, rather than the set being taken on "
                "trust as re-runnable"
            )
            if rerun
            else (
                "harness_tasks_n is MEASURED - the harness counted the tasks it "
                "can grade in your own file"
            )
        ),
        paths=(tasks,),
    )


def _propose_score_the_bare_model(situation: Situation) -> Build:
    """`SPEC__RUN_THE_MODEL_ALONE` - and this plan does not run anything.

    THE STEP THE PERSON TAKES IS NOT IN THIS PLAN, and saying so is the whole
    honesty of it. Running the bare model over their tasks is theirs to do: this
    harness will not drive somebody else's system, and where the model is a
    connected provider the ML ledger's own `run_eval` already does it. What this
    build does is GRADE the recording, which is a file on disk, and the
    difference between those two is the reason `solo_pass_rate` can be `inspect`
    at all.
    """
    tasks = situation.require_path("tasks_path")
    _needs_columns(situation, ("input_field", "expected_field", "answer_field"))
    answers = str(situation.answers_path or "").strip()
    if not answers:
        raise NotEnoughToPropose(
            "I need answers_path: the file holding what your model actually "
            "answered on these tasks. This harness will not run your system - "
            "your code is yours - so the run is the one part of this you do "
            "between approving this plan and executing it. Send each task to the "
            "model with nothing around it, save what came back in the same row "
            "order, and point me at it. Then the rate is a measurement rather "
            "than a memory.",
            needs=("answers_path",),
        )
    return _harness_build(
        situation,
        build_id="score_the_bare_model",
        title="Grade what the bare model answered, and record the rate to beat",
        because=(
            "The bare model has never been scored on these tasks, so there is no "
            "number any harness would have to beat. A surprising share of "
            "harnesses are built to fix a problem the model stopped having two "
            "releases ago, and this is the step that finds that out before the "
            "money is spent. You run it; this grades it."
        ),
        steps=[
            _harness_step(
                "solo",
                "score_a_recorded_run",
                why=(
                    "Grade the answers you recorded against your own expected "
                    "column, and file the rate under the bare-model rung. The "
                    "rung is named explicitly rather than inferred, because each "
                    "one opens a different row of the ladder gate and a rate "
                    "filed under the wrong rung would pass a gate that exists to "
                    "ask whether the cheaper thing was tried."
                ),
                arguments={
                    "tasks_path": tasks,
                    "answers_path": answers,
                    "input_field": situation.input_field,
                    "expected_field": situation.expected_field,
                    "answer_field": situation.answer_field,
                    "variant": "solo",
                },
                produces=(
                    Output("pass_rate", "number", "the rate over graded rows", at="pass_rate"),
                    Output("graded", "integer", "how many rows were graded", at="graded"),
                ),
                stated=(
                    "a rate was computed over rows that were actually graded - "
                    "a rate over zero rows is not zero, it is nothing"
                ),
                subject="pass_rate",
                find_out_by="it joins two files and compares strings; time one pass",
                operates_on=Subject.of_path(tasks),
            )
        ],
        fact="solo_pass_rate",
        criterion=(
            "solo_pass_rate is MEASURED - graded off the answers your model "
            "actually gave, on your own tasks, against your own expected column"
        ),
        paths=(tasks, answers),
    )


def _propose_ablate_the_components(situation: Situation) -> Build:
    """`SPEC__ABLATE_THE_HARNESS` - the build for the gate this domain exists for.

    NO EVIDENCE IS AN ANSWER HERE AND THE PLAN SAYS SO BEFORE IT RUNS. A paired
    exact McNemar over the rows that changed returns 1.0 when nothing changed,
    which is the honest reading rather than a failure to get one - and a
    component that did not move the score by more than noise is latency, a
    failure mode, and an assumption that will rot.
    """
    tasks = situation.require_path("tasks_path")
    _needs_columns(situation, ("input_field", "expected_field", "answer_field"))
    arms = [dict(one) for one in (situation.ablation_arms or ()) if isinstance(one, Mapping)]
    if not arms:
        raise NotEnoughToPropose(
            "I need ablation_arms: for each component you intend to build, the "
            "answers from a run WITH it and a run WITHOUT it, over these same "
            "tasks. All of them at once, because the gate asks whether EVERY "
            "component is load-bearing and the unit of that measurement is the "
            "whole set. Running the two arms is yours - this harness does not "
            "drive your system - and pairing them is this build's.",
            needs=("ablation_arms",),
        )
    return _harness_build(
        situation,
        build_id="ablate_the_components",
        title="Pair your with-and-without runs, and find out which components earn their place",
        because=(
            "Every component encodes an assumption about something the model "
            "cannot do alone, and those assumptions rot as models improve. This "
            "pairs your two recordings row by row and tests the rows that "
            "CHANGED - the ones a component fixed against the ones it broke - "
            "because comparing two aggregate rates throws away exactly the "
            "information that decides this. A component that survives is one you "
            "can defend."
        ),
        steps=[
            _harness_step(
                "ablate",
                "ablate_a_component",
                why=(
                    "Grade both arms of every component and pair them per row. "
                    "The test is exact and two-sided, and NO EVIDENCE is a real "
                    "result rather than a failed one: it means that component "
                    "did not change the score by more than noise, which is the "
                    "most common finding in this whole ledger and the least "
                    "welcome, because code that was right when it was written is "
                    "the hardest kind to delete."
                ),
                arguments={
                    "tasks_path": tasks,
                    "input_field": situation.input_field,
                    "expected_field": situation.expected_field,
                    "answer_field": situation.answer_field,
                    "arms": arms,
                },
                produces=(
                    Output("ablated", "integer", "how many components were paired", at="ablated"),
                    Output(
                        "earned",
                        "integer",
                        "how many changed the score by more than noise",
                        at="earned_their_place",
                    ),
                ),
                stated=(
                    "every arm was paired and tested - the count of components "
                    "measured is what the gate reads, and an arm this could not "
                    "read is reported rather than counted"
                ),
                subject="ablated",
                find_out_by=(
                    "it grades two recordings per component and runs an exact "
                    "test over the rows that changed; time one component"
                ),
                operates_on=Subject.of_path(tasks),
            )
        ],
        fact="components_ablated_n",
        criterion=(
            "components_ablated_n is MEASURED - every component you named was "
            "paired against a run without it, on your own tasks, and the verdict "
            "on each one is a p-value rather than a preference"
        ),
        paths=(tasks,),
        risks=(
            Risk(
                what="a component comes back NO EVIDENCE and it is one you wanted",
                what_we_do=(
                    "that is the finding and not a failure of the test. NO "
                    "EVIDENCE means the rows that changed were too few to tell "
                    "the difference from chance, and the two honest moves are to "
                    "take the component out or to bring more tasks - never to "
                    "keep it because it felt right"
                ),
            ),
            Risk(
                what="the two arms were not run over the same tasks",
                what_we_do=(
                    "the pairing is keyed on the row's position in YOUR task "
                    "file, so an arm exported from a different or reordered set "
                    "pairs the wrong rows and the result is meaningless. Export "
                    "both arms from one run of one task file, in order"
                ),
            ),
        ),
    )


def _propose_read_the_blast_radius(situation: Situation) -> Build:
    """`SPEC__DECLARE_THE_BLAST_RADIUS` - counted off the file, never guessed."""
    tooldefs = situation.require_path("tooldefs_path")
    return _harness_build(
        situation,
        build_id="read_the_blast_radius",
        title="Count your tools and how many say what they can destroy",
        because=(
            "Nobody can approve a thing whose worst case has not been written "
            "down. For a fixed sequence the blast radius is a property of code "
            "somebody can read; for anything that CHOOSES, it is the union of "
            "everything the loop can reach. This counts the annotations that are "
            "there - it does not infer risk from a tool's name, because a tool "
            "called `sync` can be the destructive one."
        ),
        steps=[_the_tool_risk_step(situation)],
        fact="tools_risk_annotated_n",
        criterion=(
            "tools_risk_annotated_n is MEASURED - read off the definitions file "
            "rather than taken from a claim about how careful the layer is"
        ),
        paths=(tooldefs,),
    )


def _propose_bound_the_harness(situation: Situation) -> Build:
    """`SPEC__BOUND_THE_RUN` and `SPEC__INSTRUMENT_THE_LOOP`.

    One instrument, two verdicts, and the fact it is held to is the difference:
    "nothing recorded what happened" and "there are traces and they do not
    settle the cost" are different sentences with the same next step.
    """
    trace = situation.require_path("trace_path")
    nothing_recorded = situation.outcome == "SPEC__INSTRUMENT_THE_LOOP"
    return _harness_build(
        situation,
        build_id="bound_the_harness_run",
        title=(
            "Read your trace and find out whether anything was recorded at all"
            if nothing_recorded
            else "Read your trace for what one run costs and whether it stopped"
        ),
        because=(
            "Every question left is answered by reading one trace and none of "
            "them can be answered by remembering. "
            + (
                "This reads the file you point it at and reports what it found. "
                "If the spans are not there, that is the finding, and it is "
                "cheaper to know now than after the build."
                if nothing_recorded
                else "A token total needs usage attributes on every inference "
                "span; if one is missing this refuses to total, because a "
                "partial sum is a lower bound and a lower bound is the number "
                "that is always smaller than the bill."
            )
        ),
        steps=[_the_bound_step(situation)],
        fact="harness_has_traces" if nothing_recorded else "harness_tokens_per_run",
        criterion=(
            (
                "harness_has_traces is MEASURED - something on this machine was "
                "read, rather than the recording being taken on trust"
            )
            if nothing_recorded
            else (
                "harness_tokens_per_run is MEASURED - totalled from every "
                "inference span's own usage attributes, and not stamped at all "
                "when one of them carries none"
            )
        ),
        paths=(trace,),
    )


#: THE FOUR BUILDS, AND THE ONE PROPOSER BEHIND THEM. They differ in what the
#: person is about to build and not in what this harness can measure about it,
#: which is the same finding the second ledger reported: "the same measurement
#: core answers each, differing only in what they lead with and why".
_THE_HARNESS_SHAPES = {
    "HARNESS__TOOL_LAYER": (
        "the_tool_layer",
        "Re-read the tool layer and the task set, then let the engine decide again",
        "typed, described, risk-annotated tools - and nothing about the ORDER of "
        "the work decided at run time",
    ),
    "HARNESS__FIXED_PIPELINE": (
        "the_fixed_pipeline",
        "Re-measure what the pipeline will be judged on, then let the engine decide again",
        "a fixed sequence, in your code, where you can read it and test it and "
        "bound it - and no model-driven control flow",
    ),
    "HARNESS__AGENT_LOOP": (
        "the_agent_loop",
        "Re-measure what the loop will be judged on, then let the engine decide again",
        "one loop, where the next step genuinely depends on what the last one "
        "returned",
    ),
    "HARNESS__AGENT_TEAM": (
        "the_agent_team",
        "Re-measure what the team will be judged on, then let the engine decide again",
        "more than one agent, which is the highest bar in this ledger and the "
        "only shape with its own row of the ladder gate",
    ),
}


def _propose_the_harness(situation: Situation) -> Build:
    """The four `HARNESS__` outcomes - and this build does not build the harness.

    SAYING THAT PLAINLY IS THE POINT. The ML ledger's training build cannot
    train the model for somebody either; what it does is prove the machine can
    hold it and measure what the run would cost. The same shape is honest here
    and the reason is sharper: the harness being proposed is THEIR system, in
    their repository, in a language this product never sees.

    So what this build does is take again, off files on disk, every measurement
    the verdict was paid with - the task set, the tool layer, one run's bound -
    and walk the tree. Those numbers go stale the moment anything changes: a
    prompt edit, a tool description rewrite, a model swap. A verdict standing on
    a measurement taken last month is a verdict about last month.

    IT DOES NOT RE-SCORE THE LADDER, and that absence is deliberate rather than
    missing. Re-measuring `solo_pass_rate` would need a fresh recording of the
    bare model, which only the person can produce, and a build that silently
    reused the old one would be presenting a stale rate as a current one. The
    plan says so in its risks instead.
    """
    missing = harness_tools_missing()
    if missing:
        raise NotEnoughToPropose(
            "The harness bench is not drawable in this process: "
            f"{list(missing)} of {list(THE_HARNESS_TOOLS)} are not registered "
            "tools. A step naming a tool nobody registered is a plan that fails "
            "after you approved it.",
            needs=tuple(missing),
        )
    build_id, title, shape = _THE_HARNESS_SHAPES[situation.outcome]

    steps: list[Step] = [_the_task_step(situation)]
    paths: list[str] = [situation.require_path("tasks_path")]

    # THE TOOL LAYER IS READ WHEN THERE IS ONE, and its absence is a real state
    # rather than an omission: `HARNESS__TOOL_LAYER` is reached from ZERO tools,
    # so a step that demanded a definitions file would refuse the one verdict
    # that arrives without one.
    if str(situation.tooldefs_path or "").strip():
        steps.append(_the_tool_risk_step(situation, needs=("tasks",)))
        paths.append(situation.tooldefs_path)
    if str(situation.trace_path or "").strip():
        steps.append(_the_bound_step(situation, needs=(steps[-1].id,)))
        paths.append(situation.trace_path)

    return _harness_build(
        situation,
        build_id=build_id,
        title=title,
        because=(
            "The engine says the right thing to build here is "
            + shape
            + ", and it says so on measurements taken off files on this machine. "
            "Every one of those numbers goes stale the moment anything changes, "
            "so this build takes them again and walks the tree again - and what "
            "the verdict then is, is the engine's sentence rather than this "
            "plan's. IT DOES NOT BUILD YOUR HARNESS. That is your system, in "
            "your repository, and nothing here will write it for you or run it "
            "for you. What this product can honestly hand over is the "
            "specification you just paid six gates for, and current evidence "
            "underneath it."
        ),
        steps=steps,
        fact="harness_tasks_n",
        criterion=(
            "the measurements this verdict rests on are MEASURED AS OF THIS RUN "
            "- refreshed from files on disk rather than carried forward - and the "
            "engine has walked the tree again on them"
        ),
        paths=tuple(paths),
        risks=(
            Risk(
                what=(
                    "this build ends with current measurements and no harness, "
                    "which is less than the verdict sounds like it promised"
                ),
                what_we_do=(
                    "it is less, and it is what this product can honestly hand "
                    "over. The harness is your code. What the six gates bought "
                    "you is the knowledge that every cheaper shape was tried and "
                    "measured, that every component you named carries its "
                    "weight, that every tool says what it can destroy and that "
                    "one run has a token count and a proof it stops - which is a "
                    "specification most teams never write down"
                ),
            ),
            Risk(
                what="the ladder rates are not re-scored by this build",
                what_we_do=(
                    "they cannot be. Re-scoring the bare model or the pipeline "
                    "needs a fresh recording of a run only you can make, and "
                    "reusing the old one would present a stale rate as a current "
                    "one. If anything about your model or your prompts has "
                    "changed since you scored them, run score_a_recorded_run "
                    "again before trusting the ladder this verdict stands on"
                ),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# THE CLASSICAL BRANCH, WHICH HAD TWELVE OUTCOMES AND NO FLOOR AT ALL.
#
# `stage_8_classical` is the largest dead stage in the engine, and the reason
# six of its outcomes carried was ONE SENTENCE - *fitting a cheaper model, which
# this harness has no tool to fit.* That is the shape `_EVAL_BENCH`,
# `_RETRIEVAL_BENCH` and `_TRAINING` were all in before they went half false: a
# single reason answering for several outcomes, going stale for one of them, and
# staying in the product as a written claim that we cannot do a thing we can.
#
# ONE OF THE SIX MOVES, AND NOT SIX. `fit_a_tree_model` fits a gradient-boosted
# tree and scores it on held-out rows. That is exactly what
# `NO_DEEP__GRADIENT_BOOSTED_TREES` asks for and it is NOT what the other five
# ask for, so the other five keep the reason and it is narrowed to name them one
# at a time. Writing one proposer and pointing all six at it would be the
# widened `S8_TABULAR_STANDARD` bound this very stage was broken by: a general
# answer put where specific ones belong, quietly swallowing five users.

#: THE TOOL THIS BUILD NAMES, fixed in one place for the reason
#: `THE_RETRIEVAL_TOOLS`, `THE_CHUNKING_TOOLS` and `THE_TRAINING_TOOLS` are: a
#: step and a coverage entry may not disagree about what has to exist. The name
#: is the cross-lane contract and it is not this file's to change.
THE_TABULAR_TOOLS: tuple[str, ...] = ("fit_a_tree_model",)

THE_TREE_FIT = THE_TABULAR_TOOLS[0]


def tabular_tools_missing() -> tuple[str, ...]:
    """Which of them are not registered in this process, right now.

    Read off the live registry every time, for `retrieval_tools_missing`'s
    reason: a table that answered this once at import would state the opposite
    of the truth for as long as it took somebody to notice.
    """
    return tuple(name for name in THE_TABULAR_TOOLS if REGISTRY.get(name) is None)


def the_tabular_bench_is_registered() -> bool:
    return not tabular_tools_missing()


def nodes_that_emit(
    outcome: str, spec: diagnosis.Spec | None = None
) -> tuple[str, ...]:
    """Every node in the spec whose `outcome:` is this one, read off the file.

    THE RETRIEVAL BENCH HAD TO ASK THIS BY HAND and answered it in a comment -
    *four nodes emit `NO_TRAIN__RAG` and only this one states a criterion.* The
    tabular default is emitted by TWO nodes, so the question stops being a
    comment and becomes a function: which node speaks for a run is
    `situation.result.node`, the one that actually fired, and this says which
    nodes could have fired at all. A test reads it back, so a third emitter
    appearing turns the suite red instead of leaving a plan quoting a node the
    run never reached.
    """
    current = spec or diagnosis.default_spec()
    return tuple(
        sorted(
            name
            for name, row in current.node_index.items()
            if str((row or {}).get("outcome") or "") == str(outcome or "")
        )
    )


def engine_method(node: str, spec: diagnosis.Spec | None = None) -> dict[str, Any]:
    """A node's `method:` block as the mapping it is, or {} when it is not one.

    `engine_node_says` stringifies, which turns this block into its repr and
    would put `{'libs': ['LightGBM', ...]}` into a proposal. The tabular nodes'
    method block is where the engine names the three libraries and the
    fifty-trial search, and both are things this build has to be honest about
    NOT being - so they are read as data rather than as prose.

    A node whose `method:` is a plain sentence - `S8_TABULAR_WITH_TEXT`'s is -
    comes back empty rather than mangled, which is the honest answer: there is
    no libs list in it to read.
    """
    return (spec or diagnosis.default_spec()).method_block(node)


def libraries_the_engine_names(
    node: str, spec: diagnosis.Spec | None = None
) -> tuple[str, ...]:
    """The `method.libs` a node names, verbatim - the GBDT implementations.

    `Spec.method_libs`, because `app/tools/classical.py` had its own copy of
    this walk and neither module may import the other - the registry imports
    both. One reader, beside the spec it reads.
    """
    return (spec or diagnosis.default_spec()).method_libs(node)


def tree_libraries_missing(node: str) -> tuple[str, ...]:
    """Which of the libraries the engine names are not importable here.

    LOOKED AT RATHER THAN ASSUMED, exactly as `dense_libraries_missing` looks:
    `importlib.util.find_spec` finds a module without executing it, so this
    costs a path search and imports nothing - which matters, because importing a
    library to find out whether it is there is how a proposal acquires a side
    effect.

    The module name is the engine's own name lower-cased, which is what
    LightGBM, XGBoost and CatBoost are called on an import line. That is a
    derivation and every sentence carrying its answer says so; a table mapping
    display names to module names would be this file holding a private opinion
    about somebody else's packaging.

    It fails in the direction that makes the plan more cautious: a search that
    raises reports the name as missing, which can only make the sentence claim
    that LESS is available than is.
    """
    absent: list[str] = []
    for name in libraries_the_engine_names(node):
        try:
            found = importlib.util.find_spec(name.lower())
        except (ImportError, ValueError, AttributeError):
            found = None
        if found is None:
            absent.append(name)
    return tuple(absent)


#: The node whose condition holds the engine's own floor for this whole branch.
#: `S8_TABULAR_TINY` is `tabular_rows < 1000` and its answer below that is
#: statistics and more data, so 1000 is the number under which the engine itself
#: says a model is not the honest answer for a table. Read rather than typed,
#: for `g0_minimum`'s reason.
_THE_TINY_NODE = "S8_TABULAR_TINY"

_THE_TABULAR_FLOOR = re.compile(r"tabular_rows\s*<\s*(\d+)")


def rows_a_tree_needs(spec: diagnosis.Spec | None = None) -> int:
    """The row count below which the engine's own answer is not a model at all."""
    stated = engine_node_says(_THE_TINY_NODE, "condition", spec)
    match = _THE_TABULAR_FLOOR.search(stated)
    if not match:  # pragma: no cover - the spec changed shape
        raise NotEnoughToPropose(
            f"{_THE_TINY_NODE} no longer states its floor as `tabular_rows < N`, "
            "so this proposer cannot read it. Nothing is planned against a "
            "threshold this file guessed."
        )
    return int(match.group(1))


#: THE GATE WHOSE OWN WORDS SAY WHAT A BASELINE IS ON THIS BRANCH, and the row
#: that says it. `G1_BASELINE_MEASURED.what_counts_as_the_baseline.classical_deep`
#: is *a gradient-boosted tree, and TabPFN where the size allows, both fitted and
#: scored* - which is this build, minus the half nothing here can fit. It is the
#: closest thing the engine has to a criterion for this outcome, so it is quoted
#: rather than paraphrased and it is attributed to the gate rather than to the
#: node, because the node states nothing.
#: THE FACT THE BASELINE GATE READS, for `g0_minimum`'s reason: the gate id was
#: a proxy for it, and `G1_BASELINE_MEASURED` is one ledger's spelling.
THE_BASELINE_FACT = "baseline_measured"
_THE_CLASSICAL_ROW = "classical_deep"


def the_baseline_gate_name(spec: diagnosis.Spec | None = None) -> str:
    """How to name the gate that reads `baseline_measured`, in an attribution.

    `G1_BASELINE_MEASURED` on the first ledger - the same string the id used to
    be typed as, and now READ rather than typed, so the sentence a person
    approves names the gate the ledger actually put the fact in. A ledger whose
    gates never read it has no name to give and the phrase says what was looked
    for instead, which is the honest half of a `None` answer.
    """
    current = spec or diagnosis.default_spec()
    reading = current.gate_reading(THE_BASELINE_FACT, method_class=_THE_CLASSICAL_ROW)
    return reading.gate_id if reading is not None else (
        f"the gate reading {THE_BASELINE_FACT}"
    )


def the_classical_baseline(spec: diagnosis.Spec | None = None) -> str:
    """What the baseline gate says a measured baseline IS on the classical branch.

    Found through the fact it reads. "" when this ledger has no such gate or
    states nothing for that row - which every caller already treats as an answer
    rather than a failure, because the empty string is what a node that states
    nothing has always returned here.
    """
    current = spec or diagnosis.default_spec()
    reading = current.gate_reading(THE_BASELINE_FACT, method_class=_THE_CLASSICAL_ROW)
    if reading is None:
        return ""
    said = reading.gate.get("what_counts_as_the_baseline")
    if not isinstance(said, dict):
        return ""
    return str(said.get(_THE_CLASSICAL_ROW) or "").strip()


#: Anything that looks like an identifier inside a gate's `requires:` string.
#: Whether it IS a fact is then decided by the ledger, which is the only thing
#: entitled to say.
_A_FACT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def gate_facts(spec_: diagnosis.Spec | None = None) -> frozenset[str]:
    """Every fact any row of any gate reads, straight out of the spec.

    NOT A LIST IN THIS FILE, for the reason the training build's test gives
    about its own derivation: a copy goes stale in the direction nobody looks,
    and a gate row that starts reading a sixth fact would leave the copy green
    while the product's promise moved underneath it.

    It is here rather than only in a test because a BUILD now needs the answer
    at proposal time. `_propose_fit_the_tree` plans a step whose tool may or may
    not stamp `trivial_baseline_score` - a fact a gate row reads - and which
    it is, is the other lane's decision. What is not negotiable is that the
    person reads the true sentence before approving, so the sentence is computed
    here instead of being written once and hoped over.
    """
    spec = spec_ or diagnosis.default_spec()
    found: set[str] = set()
    for gate in spec.gates.values():
        for row in gate.get("passes_when") or ():
            for name in _A_FACT_NAME.findall(str(row.get("requires") or "")):
                if name in spec.facts:
                    found.add(name)
    return frozenset(found)


def gate_rows_reading(
    fact: str, spec_: diagnosis.Spec | None = None
) -> tuple[str, ...]:
    """Which gate rows read this fact, as `GATE / method_class`, read off the spec.

    COUNTED RATHER THAN COUNTED ON. The sentence this fills used to say *a fact
    three gate rows read* about `hparam_search_trials`, and one row reads it -
    `G2_PROMPT_EXHAUSTED / classical_deep`. A number in a proposal that nothing
    computed is the invented number this whole file is organised against, and it
    is no better for being small or for being about our own spec. So the rows
    are named and the reader can count them.
    """
    spec = spec_ or diagnosis.default_spec()
    rows: list[str] = []
    for name, gate in spec.gates.items():
        for row in gate.get("passes_when") or ():
            if fact in _A_FACT_NAME.findall(str(row.get("requires") or "")):
                rows.append(f"{name} / {row.get('method_class')}")
    return tuple(rows)


#: WHAT THIS BUILD IS. One outcome, one tool - a constant rather than the table
#: the two-outcome benches needed.
_THE_TABULAR_BUILD = {
    "id": "fit_the_tree",
    "title": "Fit the tree the engine recommends, and score it against the trivial baseline",
}

#: THE RESULT KEYS THIS PLAN READS OUT OF THE FIT, AND THE ONE OF THEM THAT IS
#: A CRITERION. `_a_call_that_fits` makes the ARGUMENT half of a cross-lane
#: contract mechanical: an argument the tool does not declare is dropped, and a
#: name that had to survive and did not stops the plan. There is no such
#: mechanism for the RESULT half - an `ExitCriterion` names a dotted path into
#: the tool's reply and the registry declares nothing about replies - so these
#: are a contract in the same sense the tool NAME is, and they live in one place
#: so a step, a coverage entry and a test cannot hold three versions of it.
#:
#: **AND THE OBVIOUS CRITERION WOULD HAVE PASSED ON A REFUSAL.** The first
#: version of this held the step to `resolution` existing, on the reasoning that
#: a fit which could not run reports no resolution. `fit_a_tree_model` reports
#: `evals.resolution_for(0, 0)` on EVERY refusal - it fills every key a scored
#: run carries with the honest null, which is the right thing for it to do - so
#: `resolution exists` is true of a run that fitted nothing. That is
#: `check_split_leakage`'s `leaked_rows == 0` trap exactly, one bench over, and
#: it was found by reading the payload rather than by assuming the shape.
#:
#: `comparison` is `None` on a refusal, and `None` is PRESENT: `_dig` walks a
#: mapping by key, so `comparison` alone would pass too. `comparison.mcnemar_p`
#: cannot - the walk stops at a `None` that is not a mapping and reports the
#: subject absent, which fails every comparator. So the criterion is the paired
#: test's own p-value BEING THERE, which is true exactly when the tree and the
#: trivial answer were both scored on the same held-out rows.
#:
#: AND IT IS NOT `comparison.separated`, which is the tool's word for the tree
#: having won. That is the answer, not the criterion.
_THE_RESOLUTION = "resolution"
_THE_TREE_SCORE = "score.accuracy"
_THE_TRIVIAL_SCORE = "trivial_baseline.accuracy"
_THE_PAIRED_TEST = "comparison.mcnemar_p"


def _propose_fit_the_tree(situation: Situation) -> Build:
    """`NO_DEEP__GRADIENT_BOOSTED_TREES` - the first build on the classical branch.

    **THE ENGINE DECLARES NO EXIT CRITERION HERE AND BOTH ITS NODES ARE
    SILENT.** `S8_TABULAR_STANDARD` and `S8_TABULAR_UNMATCHED` state a
    `method:`, an `evidence:` and a `say:`, and neither states an
    `exit_criterion:` - the same shape as `S3_RETRIEVAL_IS_THE_BOTTLENECK` and
    `S9_MINT_TRAIN_VERDICT`, read off the spec every time rather than believed.
    So this build says the engine declared none, states what it DERIVED and from
    which of the engine's own words, and says what that derivation is not. A
    criterion the proposer invented is the proposal-loop trap in its purest form
    and it is invisible precisely because an invented one reads better than a
    derived one.

    **AND "THE TREE SCORED HIGHER" IS NOT A CRITERION.** It is "recall went up"
    one branch over: a tree that beats a majority-class baseline by two points
    on a few hundred held-out rows has not beaten it, because that difference is
    inside what those rows resolve. So this build is held to the comparison
    having been MADE and REPORTED WITH ITS RESOLUTION, never to which way it
    came out.

    **THE ENGINE NAMES THREE LIBRARIES AND THIS MACHINE HAS NONE OF THEM.**
    `method.libs` is LightGBM, XGBoost and CatBoost; `tree_libraries_missing`
    looks for each with `importlib` and the plan says what it found. That
    belongs in front of a person before they approve rather than in a footnote
    after: both nodes carry an `evidence:` key pointing at a paper about those
    implementations, and whatever fits a tree here is not one of them.

    **AND IT IS ONE FIT, NOT THE FIFTY-TRIAL SEARCH THE SAME BLOCK
    PRESCRIBES.** `method.tuning` says *50-trial random or optuna search*,
    `fit_a_tree_model` fits a model, and `hparam_search_trials` is `source: ask`
    with no registered tool measuring it. The plan states all three rather than
    letting one fit stand in for the answer - and it does not ASK for that
    number, because a gate row reads it and a no-train build soliciting a gate
    fact is a no-train build leaning on a gate.

    **FIVE REFUSALS, AND THEIR ORDER IS THE POINT.** The questions about the
    person's DATA are asked first and answered completely; the question about
    OUR harness is asked last. That is the order `_why_carving_is_not_honest_here`
    had to learn: a registry gap reads as *this will work once we ship it*, and
    "four hundred of your rows carry a label" does not stop being true the day a
    tool registers. Telling somebody about a missing tool when their real answer
    is permanent is telling them the wrong thing first.
    """
    dataset = situation.require_path("dataset_path")

    # REFUSAL: NOBODY SAID WHICH COLUMN IS THE ANSWER, and it is the carve's
    # refusal for the carve's reason. `expected_field` and not a new argument:
    # this is the same question `_why_carving_is_not_honest_here` asks about the
    # same `dataset_path`, and two names for one question is how two answers
    # start.
    column = str(situation.expected_field or "").strip()
    if not column:
        raise NotEnoughToPropose(
            "I can plan the fit and I will not choose what it is predicting. "
            "Tell me with expected_field which column holds the answer - the "
            "label, the class, the target - and I will read that column off "
            f"{dataset} and plan the fit. This file will not pick it for you: "
            "which column is the right answer is the definition of correct for "
            "your task, and a tree fitted against a column this harness chose "
            "would be a model of a question nobody asked, reporting a real "
            "number about it.",
            needs=("expected_field",),
        )

    floor = rows_a_tree_needs(situation.spec)
    found = the_answers_are_already_in_the_data(dataset, column, at_least=floor)

    # REFUSAL: THAT COLUMN IS NOT IN THE FILE. Read rather than assumed, and the
    # reply names what IS there so the next message is a column name rather than
    # another guess.
    if not found.the_column_is_there:
        raise NotEnoughToPropose(
            f"There is no column called {column!r} in {dataset}. What is there, "
            f"in the {found.rows_read} rows read, is "
            f"{sorted(found.columns_seen) or 'nothing this reader could parse'}. "
            "Nothing is fitted against a column name that is not in the file: a "
            "tree with no target still fits something and still reports a "
            "number, which is worse than an error.",
            needs=("expected_field",),
        )

    # REFUSAL: THE ROW COUNT THE ENGINE ROUTED ON IS NOT THE ROW COUNT A TREE
    # LEARNS FROM, AND THIS IS THE `eval_size_n` SUBJECT DEFECT IN A TABULAR
    # COSTUME. `tabular_rows` counts ROWS; a supervised fit learns only from
    # rows that carry a LABEL, and nothing upstream has ever compared the two. A
    # five-million-row table whose target column is populated in four hundred
    # rows reaches this outcome through `S8_TABULAR_STANDARD` - `tabular_rows >
    # 10000` is true of it - and the honest answer for those four hundred rows
    # is the one the engine already gives one node earlier.
    if found.rows_with_an_answer < floor:
        raise NotEnoughToPropose(
            f"{found.rows_with_an_answer} of the {found.rows_read} rows read "
            f"from {dataset} carry a value in {column!r}, and reading stopped "
            f"because {found.stopped_because}. The engine routed you here on "
            "tabular_rows, which is on file as "
            f"{situation.values.get('tabular_rows')!r} - and that is a count of "
            "ROWS, while a tree learns only from the rows that carry the label. "
            f"{_THE_TINY_NODE}'s own condition is "
            f"`{engine_node_says(_THE_TINY_NODE, 'condition', situation.spec)}` "
            f"and its answer below that floor is: "
            f"{engine_node_says(_THE_TINY_NODE, 'say', situation.spec)!r} "
            "Do that instead, or fill the label in. Nothing here fits a "
            "gradient-boosted tree on fewer labelled rows than the engine says a "
            "model is honest on and then reports its score as though it meant "
            "something.",
            needs=(f"{floor} rows carrying a value in {column!r}",),
        )

    # REFUSAL: THE ROWS IT WOULD BE SCORED ON ARE THE ROWS IT WOULD BE FITTED
    # ON. The training build's refusal and the retrieval bench's, asked about
    # the pair that matters here. `fit_a_tree_model` checks its two sides for
    # shared rows itself and refuses on a leak, which is the row-level version;
    # this is the version that does not need to open either file, and it is
    # worth making here because the answer is a sentence about which file to
    # point at rather than a count of overlapping rows.
    held_out = str(situation.eval_path or "").strip()
    if held_out:
        held_out = situation.require_path("eval_path")
        if Subject.of_path(held_out).key == Subject.of_path(dataset).key:
            raise NotEnoughToPropose(
                f"The rows you named as the hold-out are the rows the tree would "
                f"be fitted on ({Subject.of_path(dataset).key}). Then the score "
                "that comes back measures how well a tree memorises rows it has "
                "already seen, which is high whatever it learned and is the "
                "number a person would show as proof the model works. Leave "
                "eval_path out and the fit carves its own hold-out by hashing "
                "each row, or point it at a genuinely separate file.",
                needs=("dataset_path", "eval_path"),
            )

    # REFUSAL: THE TRIVIAL BASELINE ALREADY CLEARS YOUR BAR. Then the thing this
    # build would be compared against has already won, and fitting anything is
    # work for a question that is answered. It fires only on a MEASURED trivial
    # baseline - `evals.compare`'s first refusal: a number somebody typed and a
    # number this harness read are two facts and not a comparison. Unreachable
    # through `propose_build`, which runs the engine, and a tabular run never
    # enters stage 1, so nothing has scored a trivial baseline by the time this
    # outcome is reached; reachable by a caller assembling a `Situation`, which
    # is exactly how a proposer ends up planning work for a verdict other than
    # the one in front of it.
    if situation.is_measured("trivial_baseline_score"):
        try:
            already = float(situation.values["trivial_baseline_score"])
            bar = float(situation.values["target_score"])
        except (KeyError, TypeError, ValueError):
            already, bar = 0.0, 1.0
        if already >= bar:
            raise NotEnoughToPropose(
                f"The trivial baseline here is a measured {already} and the "
                f"score you are aiming at is {bar}, so the majority class "
                "already clears your bar. A gradient-boosted tree fitted to beat "
                "it would be work to answer a question that is answered, and the "
                "number that came back would be held up against something that "
                "has already won. Either the target is below what the task "
                "actually needs, or the labels are more skewed than the task "
                "assumes - and both of those are yours to settle before anything "
                "is fitted.",
                needs=("a target above the measured trivial baseline",),
            )

    # AND NOW THE QUESTION ABOUT OUR HARNESS, LAST, BECAUSE IT IS THE ONLY ONE
    # OF THE FIVE THAT STOPS BEING TRUE WHEN SOMEBODY SHIPS SOMETHING.
    missing = tabular_tools_missing()
    if missing:
        raise NotEnoughToPropose(
            f"{found.rows_with_an_answer} rows of {dataset} carry a value in "
            f"{column!r}, so a gradient-boosted tree could be fitted and scored "
            "on them mechanically - and the tool that would fit it is not "
            f"registered here: {list(missing)} of {list(THE_TABULAR_TOOLS)} are "
            "missing from this registry. A step naming a tool nobody registered "
            "is a plan that fails after you approved it, so none is drawn. This "
            "is a gap in the harness rather than in your data, and it closes "
            "when the tool registers rather than when you write anything.",
            needs=missing,
        )

    # REFUSAL: A TREE FIT THAT LEAVES THIS MACHINE IS NOT THIS ANSWER. Read off
    # the tool's own registration rather than assumed, and it decides two things
    # at once. Every cost below is `_local_cost`, which PROVES zero tokens and
    # zero requests off exactly this declaration, so a tool reading `providers`
    # would make this plan state a nought it cannot stand behind - and the whole
    # argument of the classical branch is that the answer costs no GPU and no
    # model tokens. `Build.validate` would refuse the no-egress environment
    # below for either network read anyway; this is the same refusal arriving as
    # a sentence a person can act on instead of as a proposer defect.
    reaching = sorted(set(_spec(THE_TREE_FIT).reads) & build.NETWORK_READS)
    if reaching:
        raise NotEnoughToPropose(
            f"{THE_TREE_FIT} declares reads="
            f"{list(_spec(THE_TREE_FIT).reads)}, and {reaching} leaves this "
            "machine. That is not what this outcome says to do: the engine's own "
            "reason for the classical branch is that trees train and infer "
            "faster with no GPU and are easier to tune and to interpret, and the "
            "value of the answer is that it costs neither a GPU nor your model's "
            "tokens. A plan that priced this at nothing while a step of it spent "
            "your budget would be inventing the most persuasive number in it.",
            needs=(f"a {THE_TREE_FIT} that stays on this machine",),
        )

    node = str(situation.result.node or "")
    emitters = nodes_that_emit(situation.outcome, situation.spec)
    condition = engine_node_says(node, "condition", situation.spec)
    method = engine_method(node, situation.spec)
    libs = libraries_the_engine_names(node, situation.spec)
    absent = tree_libraries_missing(node)
    tuning = str(method.get("tuning") or "")
    hardware = str(method.get("hardware") or "")
    stated = engine_exit_criterion(node, situation.spec)
    said = str(situation.result.say or "").strip()
    g1 = the_classical_baseline(situation.spec)

    fitting_offer: dict[str, Any] = {
        # THE PATH UNDER BOTH SPELLINGS THIS REPOSITORY USES, for the reason
        # `_at_least_one_of` exists: a dataset is `dataset_path` to
        # `carve_eval_set` and an input is `path` to `build_retrieval_index`, so
        # a plan that offered one of them would refuse over a synonym.
        "dataset_path": dataset,
        "path": dataset,
        # AND THE TARGET UNDER EVERY SPELLING THIS REPOSITORY HAS FOR "THE
        # COLUMN HOLDING THE ANSWER". Which one the fit declares is the fit's
        # business; that at least one survives is this plan's.
        "target": column,
        "target_column": column,
        "label_column": column,
        "expected_field": column,
    }
    # AND THE SPLIT THE PERSON ALREADY HAS, WHEN THEY HAVE ONE. This is the one
    # place this build passes something optional, and it is not a default this
    # file chose - it is a file the caller named. `docs/VISION.md`'s whole
    # argument for one chat box is that the eval set which produced the
    # diagnosis is the one the fix is measured against, and scoring the tree on
    # a hash-carved slice while an eval file the person made sits beside it is
    # exactly the seam that argument is about. Left out when nobody named one,
    # and then the fit's own hashed split stands and the step says so.
    if held_out:
        fitting_offer["holdout_path"] = held_out
    fitting = _a_call_that_fits(THE_TREE_FIT, fitting_offer)
    where = _at_least_one_of(
        fitting, THE_TREE_FIT, ("dataset_path", "path"), what="which table to fit"
    )
    what = _at_least_one_of(
        fitting,
        THE_TREE_FIT,
        ("target", "target_column", "label_column", "expected_field"),
        what="which column it is predicting",
    )

    # WHAT THIS STEP STAMPS, READ OFF THE REGISTRY RATHER THAN ASSERTED. The
    # training build can say "nothing here stamps anything the five gates read"
    # because it checked. This one cannot say it in advance and must not guess:
    # G1's own `what_counts_as_the_baseline` for the classical branch is *a
    # gradient-boosted tree, and TabPFN where the size allows, both fitted and
    # scored*, so a tool that fits and scores one has a real claim on
    # `trivial_baseline_score`, which a gate row reads. Whether it declares
    # that is the other lane's decision. What is not negotiable is that the
    # person reads the true sentence before approving, so it is computed from
    # `measures=` at proposal time and printed either way.
    stamps = tuple(_spec(THE_TREE_FIT).measures)
    stamped_gate_facts = sorted(set(stamps) & gate_facts(situation.spec))

    the_derivation = (
        f"WHAT WAS DERIVED, AND FROM WHAT. {node} states no exit criterion, so "
        "this comes from the engine's own words elsewhere and is attributed "
        "rather than presented as the node's. "
        + (
            f"{the_baseline_gate_name(situation.spec)}'s what_counts_as_the_baseline for "
            f"{_THE_CLASSICAL_ROW} is {g1!r} - which is this build, minus the "
            "half nothing here can fit. So what a fitted tree settles is whether "
            "the cheap model clears your bar, measured, with the resolution of "
            "the rows it was scored on printed beside it. "
            if g1
            else f"{the_baseline_gate_name(situation.spec)} no longer states what a baseline is for "
            f"{_THE_CLASSICAL_ROW}, so there was nothing to derive from and "
            "nothing has been invented to replace it. "
        )
        + "WHAT THAT DERIVATION IS NOT: it is not a promise that the tree wins, "
        "and it is not this node's criterion, because this node does not have "
        "one."
    )

    the_trap = (
        "AND THE DIRECTION A NUMBER MOVED IS NOT EVIDENCE. A tree that beats a "
        "majority-class baseline by two points on a few hundred held-out rows "
        "has not beaten it - that difference is inside what those rows resolve, "
        "and app/tools/evals.py exists because a playground shows you 73% and "
        "then 76% and lets you conclude. So this build is held to the comparison "
        "having been made and reported WITH ITS RESOLUTION and never to which "
        "way it came out. The engine draws the same line at five points in "
        "S1_LABELS_ARE_NOISE, where being inside it is a statement about your "
        "labels rather than about your model."
    )

    the_libraries = (
        "THE ENGINE'S METHOD BLOCK NAMES "
        + (", ".join(libs) if libs else "no libraries")
        + " AND THIS MACHINE HAS "
        + (
            "none of them"
            if libs and len(absent) == len(libs)
            else ("none of " + ", ".join(absent) if absent else "all of them")
        )
        + ", looked for with importlib under the engine's own names lower-cased "
        "rather than remembered. "
        + (
            "So whatever fits your tree here is a different implementation from "
            "the ones this node's evidence key is about, and a score is not "
            "transferable between implementations by assumption. It is a "
            "gradient booster either way; what changes is which one, and the "
            "reply says. "
            if absent
            else "So a library the engine cites is importable here, which is "
            "worth knowing and is still not a claim about which one the fit "
            "uses - that is the fit's to report. "
        )
        + (
            f"The same block prescribes {tuning!r} and THIS IS ONE FIT, not that "
            "search. hparam_search_trials is source: ask with default 0 and no "
            "registered tool measures it, so a tuned tree is work you do and say "
            "you did - and an untuned tree is not a baseline anything can be "
            "compared against, it is a tree nobody tuned, which is the engine's "
            "own sentence at S8_TABULAR_DEEP_NEEDS_HPARAM_SEARCH. This plan does "
            "not ask you for that number either: it is read by "
            + str(list(gate_rows_reading("hparam_search_trials", situation.spec)))
            + ", and a no-train build soliciting a gate fact is a no-train "
            "build leaning on a gate. "
            if tuning
            else ""
        )
        + (f"The engine says of the hardware: {hardware!r}." if hardware else "")
    )

    criterion = (
        (
            f"{node} states it as: {stated!r}. This build is held to that."
            if stated
            else f"{node} DECLARES NO exit_criterion OF ITS OWN, and neither does "
            f"the other node that emits this outcome - {list(emitters)} between "
            "them state a method, an evidence key and a sentence to say, and no "
            "criterion. Nothing below was taken from the engine and nothing was "
            f"invented to stand in for it. {the_derivation}"
        )
        + " WHAT THIS BUILD IS HELD TO: the fit ran on your own rows and came "
        "back with the comparison against the trivial baseline AND the "
        "resolution of the rows it was scored on. Not that the tree won. "
        + the_trap
    )

    because = (
        (f"{said} " if said else "")
        + f"The engine landed on {node}, whose condition is `{condition}`"
        + (
            f", and this outcome is emitted by {list(emitters)} - so the plan "
            "quotes the node your run actually reached rather than whichever one "
            "is more convenient. "
            if len(emitters) > 1
            else ". "
        )
        + "WHAT THIS BUILD DOES: one fit of a gradient-boosted tree on "
        f"{dataset}, predicting {column!r}, scored on rows held out of the fit, "
        "reported beside the trivial baseline on those same rows with the "
        "resolution those rows carry. "
        f"{found.rows_with_an_answer} of the {found.rows_read} rows read carry a "
        f"value in {column!r} - read off your own file at proposal time, "
        f"stopping because {found.stopped_because} - against the engine's own "
        f"floor of {floor} from {_THE_TINY_NODE}. "
        + the_libraries
        + " "
        + criterion
        + " WHAT THIS BUILD DELIBERATELY DOES NOT DO: it does not profile your "
        "dataset first. profile_dataset stamps eval_size_n, which is the fact "
        "G0_EVAL_SET reads, and it would stamp it with a count of the TRAINING "
        "table - a real measurement of the wrong file, filed under the name a "
        "gate opens on. That is the defect this module spent a milestone "
        "removing and it is not coming back through the tabular door. "
        + (
            (
                f"WHAT THE FIT ITSELF STAMPS: {list(stamps)}, read off its own "
                "measures= at proposal time. "
                + (
                    f"{stamped_gate_facts} of that is read by a gate row, which "
                    "is stated here rather than hidden: "
                    f"{the_baseline_gate_name(situation.spec)}'s {_THE_CLASSICAL_ROW} row describes "
                    "this very build as what a baseline IS on this branch, so "
                    "the stamp is the engine's own definition being honoured "
                    "rather than a no-train build nudging a gate - and you are "
                    "reading it before you approve rather than finding it "
                    "afterwards. "
                    if stamped_gate_facts
                    else "None of that is a fact any gate row reads, checked "
                    "against the gates at proposal time rather than remembered. "
                )
            )
            if stamps
            else "WHAT THE FIT STAMPS: nothing. It declares measures=(), so no "
            "fact enters the ledger from this build at all and the score is "
            "yours to read rather than the tree's to file. "
        )
    )

    return Build(
        id=_THE_TABULAR_BUILD["id"],
        title=_THE_TABULAR_BUILD["title"],
        for_outcome=situation.outcome,
        because=because,
        steps=(
            Step(
                id="fit",
                tool=THE_TREE_FIT,
                why=(
                    f"Fit a gradient-boosted tree on {dataset} to predict "
                    f"{column!r}, and score it on rows held out of the fit "
                    "against the trivial baseline on those same rows. One step, "
                    "because it is one piece of work: the comparison is worth "
                    "something only if both numbers come off the same rows from "
                    "the same instrument, which is why it is not two steps that "
                    "could be run against two different splits. It is told where "
                    f"by {where!r} and what to predict by {what!r} - the fit's "
                    "own argument names, taken from its schema rather than "
                    "chosen here. "
                    + (
                        f"It is scored on {held_out}, which you named, and the "
                        "fit checks the two sides for shared rows and refuses "
                        "rather than trusting the split. "
                        if "holdout_path" in fitting
                        else "Nobody named a hold-out file, so the fit carves "
                        "one itself by hashing each row - reproducible, and two "
                        "identical rows cannot land on opposite sides. "
                    )
                    + "How big that hold-out is, which rows the seed picks, "
                    "which columns are features and which are dropped are all "
                    "left to the fit's own defaults and to you: this plan passes "
                    "none of them, because how much of your data is held back "
                    "and which column is a leak are your calls and the fit's "
                    "schema says what each default is. "
                    + (
                        "The libraries the engine's method block names ("
                        + ", ".join(absent)
                        + ") are not importable on this machine, so the booster "
                        "that runs is a different implementation and its score is "
                        "not the cited paper's score transplanted."
                        if absent
                        else "The libraries the engine's method block names are "
                        "importable here, which is not the same as this fit using "
                        "one; the reply says which it used."
                    )
                ),
                arguments=fitting,
                produces=(
                    Output(
                        "tree_accuracy",
                        "number",
                        "what the tree scored on the held-out rows",
                        at=_THE_TREE_SCORE,
                    ),
                    Output(
                        "trivial_accuracy",
                        "number",
                        "what always answering the commonest training label "
                        "scored on the SAME held-out rows, which is the only "
                        "thing the tree's number means anything against",
                        at=_THE_TRIVIAL_SCORE,
                    ),
                    Output(
                        "paired_p",
                        "number",
                        "the paired McNemar p-value over the rows where the two "
                        "disagreed - the rows they agree on carry no information "
                        "about the difference",
                        at=_THE_PAIRED_TEST,
                    ),
                    Output(
                        _THE_RESOLUTION,
                        "object",
                        "how big a difference a hold-out that size could resolve "
                        "at all - the half of a score that makes it a "
                        "measurement rather than a number",
                        at=_THE_RESOLUTION,
                    ),
                ),
                cost=_local_cost(
                    THE_TREE_FIT,
                    find_out_by=(
                        "nothing on this machine has ever timed a tree fit, so "
                        "run it over a slice of these rows and read the seconds "
                        "it reports - which is the only honest thing this plan "
                        "can say about how long the whole of it takes"
                    ),
                ),
                exit_criterion=ExitCriterion(
                    stated=(
                        "the PAIRED TEST RAN - the tree and the trivial answer "
                        "were both scored on the same held-out rows and "
                        "McNemar's exact test came back with a p-value over the "
                        "rows where they disagreed. Not 'a score came back', "
                        "which a refusal also produces; not 'the resolution is "
                        "there', which this tool reports on every refusal too, "
                        "filling every key a scored run carries with the honest "
                        "null; and NOT that the tree won, which is the answer "
                        "rather than the criterion. A build whose success "
                        "condition is that its own result came out one way has "
                        "declared victory in advance"
                    ),
                    source="tool_result",
                    subject=_THE_PAIRED_TEST,
                    comparator="exists",
                ),
                risks=(
                    Risk(
                        what=(
                            "the tree beats the trivial baseline by a margin the "
                            "held-out rows cannot resolve, and that is read as "
                            "the tree working"
                        ),
                        what_we_do=(
                            "the resolution comes back beside the score and this "
                            "step is held to it being there. A difference inside "
                            "it is no evidence, in those words - and the engine "
                            "draws the same line at five points in "
                            "S1_LABELS_ARE_NOISE, where being inside it is a "
                            "statement about your labels rather than about your "
                            "model"
                        ),
                    ),
                    Risk(
                        what=(
                            "one fit is read as the tuned tree the engine's "
                            "method block prescribes"
                        ),
                        what_we_do=(
                            f"it is not, and the plan says so: {tuning!r} is the "
                            "engine's own tuning line and this runs one model. "
                            "The search is yours to run and to state, and this "
                            "plan does not ask you for the number, because "
                            "hparam_search_trials is read by a gate row"
                            if tuning
                            else "the node states no tuning line, so nothing here "
                            "claims one was followed"
                        ),
                    ),
                    Risk(
                        what=(
                            "the score is read as a score on your production "
                            "distribution"
                        ),
                        what_we_do=(
                            "it is a score on rows held out of THIS file, split "
                            "by the fit itself, and nothing here can tell you "
                            "whether that file looks like next month's traffic. "
                            "That question is yours and no tool in this harness "
                            "answers it"
                        ),
                    ),
                ),
            ),
        ),
        environment=_sandbox(_THE_TABULAR_BUILD["id"], dataset),
        exit_criterion=ExitCriterion(
            stated=criterion,
            source="outputs",
            subject="fit.paired_p",
            comparator="exists",
        ),
        risks=(
            Risk(
                what=(
                    "this build fits one of the two baselines G1 names for this "
                    "branch and is read as both"
                ),
                what_we_do=(
                    f"{the_baseline_gate_name(situation.spec)}'s {_THE_CLASSICAL_ROW} row is {g1!r} "
                    "and the TabPFN half is not here: NO_DEEP__TABPFN stays "
                    "uncovered, because a tabular foundation model is a specific "
                    "model to load rather than a fit to run, and nothing "
                    "registered here loads one. The plan hands you half of that "
                    "row and says which half"
                ),
            ),
            Risk(
                what="the fit writes a model somebody later ships",
                what_we_do=(
                    "what this build hands over is a measurement, and whether "
                    f"{THE_TREE_FIT} keeps the fitted model is its own to say in "
                    "its reply. Nothing in this plan promises a servable "
                    "artifact: the engine's answer here is a recommendation about "
                    "a METHOD, and the model that goes to production is fitted on "
                    "the whole of your data by you, on the settings this "
                    "comparison justified"
                ),
            ),
        ),
        facts=dict(situation.origins),
    )


# ---------------------------------------------------------------------------
# THE SECOND LEDGER'S BUILDS - somebody else's agent, read rather than run.
#
# `docs/ledgers/ai_engineering.yaml` diagnoses and mints verdicts on the same
# engine as the first ledger, and until this section existed not one of its
# outcomes led anywhere. That is the defect `docs/PHASES.md` measured in the ML
# ledger - 43 of 55 dead - arriving in a second domain on day one, and the
# answer is the one the retrieval bench used: the plans are written against tool
# names fixed between lanes, and they are DRAWN only while the tools that would
# run them are registered.
#
# THE FOUR NAMES ARE FIXED SO THE LANES CANNOT DISAGREE, exactly as
# `THE_RETRIEVAL_TOOLS` and `THE_CARVING_TOOLS` are:
#
#     read_agent_traces      parse a trace file and report what the agent did
#     read_tool_definitions  read somebody's tool schemas and report them
#     run_the_failures       re-run the failure set and report the rate
#     bound_the_loop         measure cost and termination over runs
#
# NOTHING HERE TYPES A THRESHOLD, A BUCKET NAME OR A CRITERION. This domain's
# ledger declares no `exit_criterion:` on any node - measured rather than
# remembered, and asserted in this lane's own test - so every build below says
# so plainly and derives what it can from the gate that READS its fact or from
# the node whose condition NAMES it, attributing each sentence to where it was
# read. That is the habit `_propose_fit_the_tree` established for the two
# tabular nodes, which declare none either.
#
# AND THE ANTI-THEATRE CHECK IS COMPUTED RATHER THAN ARGUED.
# `ACTION__COUNT_THE_ROWS` is uncovered in the first ledger because no tool
# stamps the fact it waits on, so a build for it would run, look successful,
# re-enter the tree and land on the same outcome. Every proposer below calls
# `_nothing_would_stamp_it` before it draws a step, so the day a lane ships one
# of these four tools WITHOUT the `measures=` its ledger needs, the plan is
# refused with the fact named rather than drawn and spent.


#: THE FOUR TOOL NAMES, FIXED ACROSS LANES. `docs/PHASES.md` Phase 1 names them
#: and `docs/AGENT_INSTRUMENTS.md` is the format research behind them. What this
#: file owes them is that nothing here guesses an ARGUMENT name - see
#: `_a_call_that_fits`, which asks each schema and stops the plan when the two
#: halves of a bench disagree about what to call things.
THE_TRACE_READER = "read_agent_traces"
THE_TOOL_READER = "read_tool_definitions"
THE_FAILURE_RUNNER = "run_the_failures"
THE_LOOP_BOUNDER = "bound_the_loop"

THE_AGENT_TOOLS: tuple[str, ...] = (
    THE_TRACE_READER,
    THE_TOOL_READER,
    THE_FAILURE_RUNNER,
    THE_LOOP_BOUNDER,
)

#: The fact this ledger's hinge turns on. A name rather than a derivation
#: because it is the key of a proposer table entry and there is nothing to
#: derive it FROM; everything else about it - the floor, the bucket names, the
#: node that states them - is read off the ledger by the two functions below.
THE_BUCKET_FACT = "failure_buckets"


def agent_tools_missing(*names: str) -> tuple[str, ...]:
    """Which of these agent instruments are not registered in this process, now.

    Read off the live registry every time, for `retrieval_tools_missing`'s
    reason. With no arguments it answers for all four; each proposer asks only
    about the tools its own steps name, because a build that needs the trace
    reader must not be withheld because the loop bounder is late.
    """
    wanted = names or THE_AGENT_TOOLS
    return tuple(name for name in wanted if REGISTRY.get(name) is None)


def the_failure_runner_is_registered() -> bool:
    return not agent_tools_missing(THE_FAILURE_RUNNER)


def the_trace_reader_is_registered() -> bool:
    return not agent_tools_missing(THE_TRACE_READER)


def the_agent_bucketer_is_registered() -> bool:
    """Both halves of the bucketer. It is one build and not two.

    `docs/AGENT_INSTRUMENTS.md` §6.3 is where the reason was measured rather
    than assumed: of the five buckets this ledger routes on, the ones decidable
    from the answer string alone are a minority. `tool_choice` needs to know
    which tool should have been called, `tool_execution` needs a status on the
    tool span, and `context` needs what the model was actually given - all three
    are in the trace or nowhere. So the classification build names both tools
    and is drawn only while both are here.
    """
    return not agent_tools_missing(THE_TRACE_READER, THE_FAILURE_RUNNER)


def instruments_that_measure(fact: str) -> tuple[str, ...]:
    """Every registered tool declaring `measures=(fact,)`. The anti-theatre check.

    THE ONE QUESTION THAT SEPARATES A BUILD FROM A PERFORMANCE, and it is the
    question `NOT_COVERED`'s entry for `ACTION__COUNT_THE_ROWS` had to answer by
    hand. A step whose tool does not stamp the fact its outcome is blocked on
    cannot move that outcome - not on this input, not on any input - so the plan
    would run, report success, re-enter the tree and arrive back where it
    started, having spent somebody's time and tokens.

    Asked of the REGISTRY rather than of a table here, so a lane that ships
    `run_the_failures` with a different `measures=` than its ledger needs is
    caught at proposal time with the fact named, rather than after approval.
    """
    return tuple(
        sorted(spec.name for spec in REGISTRY if fact in tuple(spec.measures))
    )


def _nothing_would_stamp_it(fact: str, outcome: str, spec: diagnosis.Spec) -> None:
    """Refuse when no registered tool could make `fact` a reading. See above."""
    if instruments_that_measure(fact):
        return
    declared = str((spec.facts.get(fact) or {}).get("source") or "undeclared")
    raise NotEnoughToPropose(
        f"{outcome} is blocked on {fact!r}, {spec.as_written} declares it "
        f"source: {declared}, and NO REGISTERED TOOL DECLARES "
        f"measures=({fact!r},). A plan for it would run, look successful, "
        "re-enter the tree and land on this same outcome having moved nothing, "
        "which is the one failure this module exists to refuse. The fix is a "
        "tool that measures it, not a proposer.",
        needs=(fact,),
    )


def buckets_the_ledger_routes(spec: diagnosis.Spec) -> tuple[str, ...]:
    """The failure buckets this ledger has a route for, read off its own fork.

    FOUND BY THE FACT THE FORK BRANCHES ON, never by a node id, for the reason
    `Spec.gate_reading` gives about gates: an id is a second spelling of the
    fact and it is wrong on any other ledger. `app/tools/evals.py` reads its own
    routable modes the same way and says in as many words why it will not fall
    back to the first ledger's eight names.

    Empty is a real answer and the caller has to treat it as one: a ledger with
    no such fork routes on nothing, and five names this file chose would be five
    names nobody's ledger declared.
    """
    for row in (spec.node_index or {}).values():
        fork = (row or {}).get("fork") or {}
        if str(fork.get("branch_on") or "") == THE_BUCKET_FACT:
            return tuple(sorted((fork.get("routes") or {}).keys()))
    return ()


_A_BUCKET_FLOOR = re.compile(
    rf"sum\(\s*{re.escape(THE_BUCKET_FACT)}\.values\(\)\s*\)\s*<\s*(\d+)"
)


def failures_to_bucket(outcome: str, spec: diagnosis.Spec) -> tuple[int, str]:
    """How many bucketed failures this ledger asks for, and where it says so.

    Read rather than typed, for `g0_minimum`'s reason, and attributed for
    invariant 3's: a number in a proposal with no address is a number nobody can
    check. A ledger that states no such floor is a refusal rather than a
    default, exactly as a missing eval-size gate is.
    """
    for node in nodes_that_emit(outcome, spec):
        found = _A_BUCKET_FLOOR.search(engine_node_says(node, "condition", spec))
        if found:
            return int(found.group(1)), f"{node}.condition in {spec.as_written}"
    raise NotEnoughToPropose(
        f"No node in {spec.as_written} that emits {outcome} states its floor as "
        f"`sum({THE_BUCKET_FACT}.values()) < N`, so this proposer cannot read "
        "one. Nothing is planned against a threshold this file guessed.",
        needs=(THE_BUCKET_FACT,),
    )


def facts_an_outcome_waits_on(
    outcome: str, spec: diagnosis.Spec
) -> tuple[str, ...]:
    """Every declared fact read by something that could state this outcome.

    Both halves, because an outcome reaches a person by two different routes and
    only one of them is a node. `Spec.outcome_sites()` is the single enumeration
    of where an outcome may be stated - it is what SC1 was fixed to use after a
    fifth site arrived and nothing scanned it - and a gate's `on_fail` is one of
    those sites with no node at all. So node conditions are read through the
    node index and gate rows through `gate_row_facts`, which the engine's own
    compiler built, rather than through a regular expression over prose.
    """
    found: set[str] = set()
    for site in spec.outcome_sites():
        if site.outcome != outcome or not site.node:
            continue
        condition = engine_node_says(site.node, "condition", spec)
        found |= {
            name for name in _A_FACT_NAME.findall(condition) if name in spec.facts
        }
    for gate_id, gate in (spec.gates or {}).items():
        if str((gate.get("on_fail") or {}).get("outcome") or "") != outcome:
            continue
        for (named, _row), facts in (spec.gate_row_facts or {}).items():
            if named == gate_id:
                found |= {name for name in facts if name in spec.facts}
    return tuple(sorted(found))


def the_criterion_this_ledger_owes(
    fact: str, spec: diagnosis.Spec, *, node: str, outcome: str
) -> str:
    """The sentence a build holds itself to, and where every word of it was read.

    FOUR PLACES, TRIED IN ORDER, AND THE FIRST THREE ARE THE LEDGER'S OWN WORDS.
    The AI-engineering ledger declares no `exit_criterion:` anywhere, so the
    first branch is unreachable against it today and is written first anyway:
    the day somebody adds one, this quotes it and stops deriving, which is what
    `engine_exit_criterion` exists to make automatic rather than remembered.

    The second branch is the gate that READS the fact - found by fact, never by
    a hardcoded gate id - carrying the gate's own question, the row's `requires`
    and the ledger's recipe for failing it. The third is the node whose
    condition NAMES the fact, which is where a non-gate outcome states its bar.
    The fourth is a refusal, because a build held to nothing but a sentence this
    file wrote is the thing this module exists to refuse.
    """
    declared = engine_exit_criterion(node, spec)
    if declared:
        return (
            f"{node} in {spec.as_written} states it as: {declared!r}, and this "
            f"build is held to the half of it that is about {fact}."
        )

    reading = spec.gate_reading(fact)
    if reading is not None:
        recipe = str((reading.gate.get("on_fail") or {}).get("recipe") or "").strip()
        return (
            f"{node} declares no exit_criterion and neither does any other node "
            f"in {spec.as_written}, so this build quotes none and says what it "
            f"derived instead. {reading.gate_id} asks "
            f"{str(reading.gate.get('asks') or '').strip()!r} and its "
            f"{reading.row_key} row requires "
            f"{str(reading.row.get('requires') or '').strip()!r}"
            + (f"; the recipe for failing it is {recipe!r}" if recipe else "")
            + ". THAT IS THE GATE'S SENTENCE AND NOT THIS BUILD'S PROMISE: what "
            f"this build promises is that {fact} stops being nobody's word and "
            "becomes a reading. Whether the gate then opens is the engine's to "
            "say, and this plan does not pre-empt it."
        )

    for candidate in (node,) + nodes_that_emit(outcome, spec):
        condition = engine_node_says(candidate, "condition", spec)
        if fact in _A_FACT_NAME.findall(condition):
            return (
                f"{node} declares no exit_criterion and neither does any other "
                f"node in {spec.as_written}, so this build quotes none. "
                f"{candidate} is where the bar for {outcome} is stated, as the "
                f"condition {condition!r}. What this build produces is {fact}, "
                "measured, so the tree is walked again on a reading rather than "
                "on a gap - and this build is NOT held to the condition going "
                "the other way, because which way it goes is the answer."
            )

    raise NotEnoughToPropose(
        f"Nothing in {spec.as_written} states a bar for {outcome} that mentions "
        f"{fact!r} - no exit_criterion, no gate row reading it, no node "
        "condition naming it - so this build would be held to nothing but a "
        "sentence this file wrote. Nothing is planned against a criterion this "
        "file preferred.",
        needs=(fact,),
    )


def _agent_cost(name: str, *, find_out_by: str, requests_why: str) -> Cost:
    """What one agent step costs, with the model half decided by the tool itself.

    `_local_cost` proves zero tokens off `reads` and is right for a reader; a
    step that re-runs somebody's failure set against their own system is the
    other case and there is no honest number for it. So the branch is taken on
    the tool's own registration rather than on this file's expectation of it: a
    `run_the_failures` that turns out NOT to declare `providers` gets the proved
    zero, and one that does gets UNKNOWN with the reason and the way to find
    out. Nothing here multiplies a failure count by a guess at how many model
    calls one agent run makes, which is the whole difficulty - a loop makes as
    many as it decides to, and that is the fact `G4` exists to bound.
    """
    if not _reaches_the_model(name):
        tokens, requests = _model_cost_of_a_local_tool(name)
    else:
        tokens = Estimate.unknown(
            build.MODEL_TOKENS,
            why=(
                f"{name} sends work to the system you connected, and turning "
                "your failures into tokens needs that system's tokenizer, which "
                "this harness does not have at proposal time"
            ),
            find_out_by=(
                "run the set with a small cap first; the reply carries what it "
                "actually spent, which is a measurement of YOUR system rather "
                "than of an average one"
            ),
        )
        requests = Estimate.unknown(
            build.MODEL_REQUESTS,
            why=requests_why,
            find_out_by=(
                "run the set with a small cap first and read the request count "
                "the step reports back"
            ),
        )
    return Cost(
        model_tokens=tokens,
        model_requests=requests,
        wall_clock=_wall_clock(name, find_out_by=find_out_by),
        disk=_disk_cost(name),
    )


def _attach(step_id: str, path: str, *, role: str, why: str) -> Step:
    """Record where something is, so every later step is about the same thing."""
    arguments = _a_call_that_fits(
        "attach_context", {"path": path, "role": role}, must_carry=("path",)
    )
    return Step(
        id=step_id,
        tool="attach_context",
        why=why,
        arguments=arguments,
        produces=(
            Output(
                "path",
                "string",
                "the path as the harness recorded it",
                at="what_it_is.path",
            ),
        ),
        cost=_local_cost(
            "attach_context",
            find_out_by="it is one filesystem stat and one row written; time it once",
        ),
        exit_criterion=ExitCriterion(
            stated="the harness has the path on file",
            source="tool_result",
            subject="ok",
            comparator="is_true",
        ),
        operates_on=Subject.of_path(path),
    )


#: WHERE A TRACE FILE MIGHT BE CALLED SOMETHING ELSE. Offered generously and
#: filtered by the tool's own schema - see `_at_least_one_of`, which exists
#: because a corpus is `path` to one tool and `corpus_path` to a `Situation` and
#: a plan that insisted on one spelling would refuse over a synonym. The two
#: lanes agreed the tool NAMES and nothing else, and this is the mechanism that
#: turns that into a refusal somebody can act on instead of a broken step: the
#: reader landed taking `path` and the runner taking `traces_path`, both of
#: which are in here, and neither of which this file had to be edited for.
_THE_TRACE_ARGUMENTS = ("trace_path", "traces_path", "path")

#: The same, for the file holding the failures to re-run.
_THE_FAILURE_ARGUMENTS = ("failures_path", "path", "eval_path")


def _the_agent_columns(situation: Situation) -> dict[str, str]:
    """The three columns a failure run needs, or a refusal naming the missing ones.

    `_require_the_two_columns` is the first ledger's version of this and there
    are THREE here, which is the difference between grading a model and grading
    an agent: the harness drives the model, so its answer is produced during the
    run, and it does not drive somebody's agent - `run_the_failures` grades
    answers that already exist because running their code is their business.
    So the answer is an input column and it is the person's to name, exactly as
    the expected column is. A guess would grade a whole failure set against the
    wrong text and report a rate for it.
    """
    columns = {
        "input_field": str(situation.input_field or "").strip(),
        "expected_field": str(situation.expected_field or "").strip(),
        "answer_field": str(situation.answer_field or "").strip(),
    }
    missing = sorted(name for name, value in columns.items() if not value)
    if missing:
        raise NotEnoughToPropose(
            "I cannot plan a run over your failures without knowing which "
            "column holds the case, which holds what should have happened, and "
            f"which holds what your agent actually answered. Missing: {missing}. "
            "Run preview_dataset_rows on the file and the column names are in "
            "the result - this file will not pick them, because which column is "
            "the right answer is the definition of correct for your task.",
            needs=tuple(missing),
        )
    return columns


def _the_failure_run_call(situation: Situation, failures: str) -> dict[str, Any]:
    """What `run_the_failures` will be called with, offered generously.

    Every spelling this file can supply goes in and the tool's schema decides -
    `_a_call_that_fits` drops what it does not declare and STOPS THE PLAN over
    a required argument nothing here can name, which is the cross-lane contract
    made mechanical rather than remembered.
    """
    offered: dict[str, Any] = {
        name: failures for name in _THE_FAILURE_ARGUMENTS
    }
    offered.update(_the_agent_columns(situation))
    if str(situation.answers_path or "").strip():
        offered["answers_path"] = situation.require_path("answers_path")
    if str(situation.trace_path or "").strip():
        traces = situation.require_path("trace_path")
        for name in _THE_TRACE_ARGUMENTS:
            offered.setdefault(name, traces)
        offered["traces_path"] = traces
    return _a_call_that_fits(THE_FAILURE_RUNNER, offered)

#: THE TWO OUTCOMES THE FAILURE RUNNER ANSWERS FOR, and which fact each waits
#: on. One proposer for both, exactly as the retrieval bench has one for its
#: two: the steps are the same and what differs is the fact the build is held
#: to, which is the thing the person is actually owed a sentence about.
#:
#: `ACTION__BUILD_AN_EVAL_HARNESS` IS THIS LEDGER'S OWN CLASSIFICATION AND NOT A
#: MISTAKE. `docs/ledgers/AI_ENGINEERING_DESIGN.md` lists an eval harness among
#: the BUILDS; the ledger moved it to `ACTION__` and wrote the argument down in
#: `contract.why_the_eval_harness_is_not_a_build` - under `gated: all` the build
#: prefix would put the instrument behind the gates it is the instrument FOR.
#: This file follows the ledger, because the ledger is the specification.
_THE_FAILURE_RUNNER_OUTCOMES: dict[str, dict[str, str]] = {
    "ACTION__BUILD_AN_EVAL_HARNESS": {
        "id": "build_the_failure_harness",
        "title": "Make your failures runnable - the instrument everything after this is measured with",
        "fact": "can_rerun_failures",
        "because": (
            "There are failures written down and no way to run them again. Every "
            "number after this one - the rate, whether a change helped, whether "
            "the loop stops - is taken by running them, so this is the first "
            "real work and it is the cheap one."
        ),
    },
    "ACTION__MEASURE_THE_BASELINE": {
        "id": "measure_the_failure_rate",
        "title": "Measure how often it actually fails, as a rate rather than an impression",
        "fact": "failure_rate_measured",
        "because": (
            "The diagnosis stopped at the gate that asks how often the thing you "
            "have now fails. 'It fails sometimes' is not a baseline and nothing "
            "later can be measured against it; 14 of 50 is."
        ),
    },
}


def _propose_run_the_failures(situation: Situation) -> Build:
    """`ACTION__BUILD_AN_EVAL_HARNESS` and `ACTION__MEASURE_THE_BASELINE`.

    THE SAME THREE STEPS, HELD TO TWO DIFFERENT FACTS. Attaching the failure set
    records what everything below is about; `run_the_failures` re-runs it against
    the system the person has now and reports how many still fail;
    `run_diagnosis` walks the tree again. Which fact the build is held to is the
    only difference and it is the difference the person is owed: one of these
    outcomes is waiting to learn that the failures CAN be re-run, and the other
    is waiting for the number that comes out when they are.

    **WHY THIS IS NOT THE `ACTION__COUNT_THE_ROWS` TRAP**, checked rather than
    argued: `_nothing_would_stamp_it` asks the live registry whether any tool
    declares `measures=` for the fact this outcome is blocked on, and refuses
    with that fact named when none does. The retrieval bench had to make the
    same argument in prose; here it is a call, so the day the instrument lands
    without the declaration the plan is refused instead of drawn.

    **AND IT REFUSES A RE-RUN THAT WOULD RETURN THE SAME NUMBER.** A rate already
    measured on THIS failure file is not moved by measuring it again, and
    `a_measurement_of` is the question about a THING rather than about a number:
    a rate taken off some other file does not suppress this build, and a number
    whose subject nothing recorded does not either. Absent is absent.
    """
    plan = _THE_FAILURE_RUNNER_OUTCOMES[situation.outcome]
    fact = plan["fact"]
    spec = situation.spec

    missing = agent_tools_missing(THE_FAILURE_RUNNER)
    if missing:
        raise NotEnoughToPropose(
            "The failure runner is not in this harness yet: "
            f"{list(missing)} of {list(THE_AGENT_TOOLS)} are not registered "
            "tools. The plan for this outcome is written and it will not be "
            "drawn against a tool that does not exist, because a step naming a "
            "tool nobody registered is a plan that fails after you approved it.",
            needs=tuple(missing),
        )

    _nothing_would_stamp_it(fact, situation.outcome, spec)

    failures = situation.require_path("failures_path")
    subject = Subject.of_path(failures)

    already, measured_of = a_measurement_of(situation, fact, failures)
    if already:
        raise NotEnoughToPropose(
            f"{fact} has already been measured on this failure set "
            f"({subject.key}): the harness holds {situation.values.get(fact)!r}, "
            "measured, of that file. Running them again returns the same answer "
            "and moves nothing. What is left is a change to the system under "
            "test, and that is not a step this build can run.",
            needs=("a change to the system, not another run of the same failures",),
        )

    stale = ""
    if situation.is_measured(fact):
        stale = (
            (
                f" A reading of {fact} is on file and it was taken of "
                f"{measured_of.key}, which is not {subject.key}, so it says "
                "nothing about the failures this build runs"
                if measured_of
                else f" A reading of {fact} is on file and nothing records what "
                "it was taken of, and a number whose subject nobody recorded is "
                "not evidence about this file"
            )
            + ", so this build measures rather than reusing it."
        )

    running = _the_failure_run_call(situation, failures)
    names_the_file = _at_least_one_of(
        running,
        THE_FAILURE_RUNNER,
        _THE_FAILURE_ARGUMENTS,
        what="which file holds the failures to re-run",
    )
    target, unidentified = _subject_of_a_call(THE_FAILURE_RUNNER, running)

    steps: list[Step] = [
        _attach(
            "attach",
            failures,
            role="the failure set the system is re-run against",
            why=(
                "Record where the failures are, so the run below and every later "
                "comparison are about the same set of cases rather than about "
                "two files that happen to look alike."
            ),
        ),
        Step(
            id="run",
            tool=THE_FAILURE_RUNNER,
            why=(
                "Re-run every failure against the system you have now and report "
                "how many still fail. That fraction is the only thing a later "
                "'it got better' can be measured against, and this harness will "
                "not take it on anybody's word."
                + (
                    " Your traces are named on this call too, so more than the "
                    "shape of the answer is decidable."
                    if any(
                        name in running for name in ("traces_path", "trace_path")
                    )
                    else " No traces were named, so what this reports is what "
                    "can be decided from the answers alone; point trace_path at "
                    "the recording and the plan for classifying them is the one "
                    "below this outcome."
                )
            ),
            arguments=running,
            produces=(
                Output(
                    "ok",
                    "boolean",
                    "whether the run completed rather than stopping part way",
                    at="ok",
                ),
            ),
            needs=("attach",),
            cost=_agent_cost(
                THE_FAILURE_RUNNER,
                find_out_by=(
                    "nothing has timed a run of your system on this machine; run "
                    "the set with a small cap first and read the seconds the "
                    "step reports"
                ),
                requests_why=(
                    "one failure is at least one request and a loop makes as "
                    "many as it decides to, so the number of requests is a "
                    "property of your system rather than of your file - and "
                    "multiplying the failure count by a number this file chose "
                    "is the invented figure this whole module is organised "
                    "against"
                ),
            ),
            operates_on=target,
            exit_criterion=ExitCriterion(
                stated=(
                    f"{THE_FAILURE_RUNNER} reports a completed run over the "
                    "failure set rather than one that stopped part way"
                ),
                source="tool_result",
                subject="ok",
                comparator="is_true",
            ),
            risks=(
                Risk(
                    what=(
                        "the system under test cannot be reached the way this "
                        "harness reaches a model"
                    ),
                    what_we_do=(
                        "the step refuses and says so rather than scoring "
                        "nothing and reporting a rate. Running your agent means "
                        "running your code and this product executes no shell - "
                        "the honest fallback is that you run it and hand the "
                        "harness what it recorded"
                    ),
                ),
                Risk(
                    what="a run does not terminate",
                    what_we_do=(
                        "a run that hit a bound has no answer, and grading it as "
                        "though it had answered would put a made-up disposition "
                        "into the number a gate opens on. It belongs to the "
                        "question about termination and is counted apart from "
                        "this one"
                    ),
                ),
                Risk(
                    what="the run is interrupted part way through",
                    what_we_do=(
                        "the exit criterion above is the run COMPLETING, so a "
                        "partial run fails this step rather than passing it with "
                        "a rate taken over whichever cases happened to finish"
                    ),
                ),
            ),
        ),
        _recheck_step(
            ("run",),
            fact,
            why=(
                "Walk the tree again on what was actually measured. Whether the "
                "rate is good enough, and which of this domain's answers you are "
                "on, is the engine's to decide and not this build's."
            ),
        ),
    ]

    egress = _egress_for([step.tool for step in steps])
    said = str(situation.result.say or "").strip()

    return Build(
        id=plan["id"],
        title=plan["title"],
        for_outcome=situation.outcome,
        because=(
            (f"{said} " if said else "")
            + plan["because"]
            + f" This plan points {THE_FAILURE_RUNNER} at {subject.key} through "
            f"its own `{names_the_file}` argument - the name came from that "
            "tool's schema rather than from a table in this file - and ends by "
            "walking the tree again."
            + (
                " Nothing in this plan can leave the machine: not one step's "
                "tool declares a network read, so the sandbox declares no egress "
                "at all and Build.validate refuses any step that would need one."
                if not egress
                else " One step in this plan reaches the system you connected, "
                "which is declared on the environment below where you can see it "
                "before you approve it."
            )
            + (
                ""
                if not unidentified
                else f" {unidentified} - so no cost here is derived from a stored "
                "count, and the estimates say so."
            )
            + stale
        ),
        steps=tuple(steps),
        environment=_sandbox(plan["id"], failures, reason=egress),
        exit_criterion=ExitCriterion(
            stated=(
                f"{fact} is MEASURED - a reading this harness took by running "
                "your failures, not a description of them. "
                + the_criterion_this_ledger_owes(
                    fact,
                    spec,
                    node=str(situation.result.node or ""),
                    outcome=situation.outcome,
                )
            ),
            source="diagnosis",
            subject=f"fact_origins.{fact}",
            comparator="is_measured",
        ),
        risks=(
            Risk(
                what="the rate comes back worse than you expected",
                what_we_do=(
                    "that is the plan working. The build's job is to produce the "
                    "number, not a particular value of it, and the engine "
                    "re-reads the tree on whatever comes back - including the "
                    "answer that you are already below your target and should "
                    "stop"
                ),
            ),
            Risk(
                what="the failures were written from memory rather than from use",
                what_we_do=(
                    "nothing in this harness can tell the difference and this "
                    "plan does not pretend to. What it produces is a rate over "
                    "the cases you gave it, which is what every number here is, "
                    "and it is why the file is attached by name in step one"
                ),
            ),
        ),
        facts=dict(situation.origins),
    )


def _propose_read_the_traces(situation: Situation) -> Build:
    """`BLOCKED__NO_TRACES` - and the half of it that is a build rather than advice.

    THE OUTCOME HAS TWO POPULATIONS AND ONLY ONE OF THEM IS OURS. `has_traces`
    defaults to false, which is this ledger's honest reading of "nobody has done
    this yet", so the node fires both for somebody whose system records nothing
    and for somebody with a directory of trace files who has never pointed the
    harness at it. For the first, the work is turning tracing on inside code
    this harness does not own and there is no step for it. For the second, the
    work is one read - and which population somebody is in is decided by whether
    they can name a file, which is exactly what `require_path` asks.

    So this build refuses without a path, in words that name what is missing,
    and draws three steps with one. It never claims the read will succeed: the
    criterion is `has_traces` becoming a reading, and a directory holding no
    agent trace produces no reading and the outcome does not move. That is
    carried as a risk which says what to do next rather than as an assumption
    about somebody's file.
    """
    fact = "has_traces"
    spec = situation.spec

    missing = agent_tools_missing(THE_TRACE_READER)
    if missing:
        raise NotEnoughToPropose(
            "The trace reader is not in this harness yet: "
            f"{list(missing)} of {list(THE_AGENT_TOOLS)} are not registered "
            "tools. The plan for this outcome is written and it will not be "
            "drawn against a tool that does not exist.",
            needs=tuple(missing),
        )

    _nothing_would_stamp_it(fact, situation.outcome, spec)

    traces = situation.require_path("trace_path")
    subject = Subject.of_path(traces)

    already, _ = a_measurement_of(situation, fact, traces)
    if already:
        raise NotEnoughToPropose(
            f"{fact} has already been read off {subject.key}. Reading the same "
            "files again returns the same answer and moves nothing. If the "
            "diagnosis still says nothing recorded what happened, then the files "
            "that were read are not the ones the failing runs are in - point me "
            "at those.",
            needs=("trace_path",),
        )

    reading = _a_call_that_fits(
        THE_TRACE_READER, {name: traces for name in _THE_TRACE_ARGUMENTS}
    )
    names_the_file = _at_least_one_of(
        reading,
        THE_TRACE_READER,
        _THE_TRACE_ARGUMENTS,
        what="which file or directory holds the traces",
    )
    target, unidentified = _subject_of_a_call(THE_TRACE_READER, reading)

    steps: list[Step] = [
        _attach(
            "attach",
            traces,
            role="the traces of what the system actually did",
            why=(
                "Record where the traces are, so the read below and anything "
                "later taken off them are about the same recording."
            ),
        ),
        Step(
            id="traces",
            tool=THE_TRACE_READER,
            why=(
                "Read what your system actually did, rather than what it was "
                "asked to do. Every diagnosis from here turns on telling several "
                "identical-looking problems apart, and a tool that is never "
                "called looks exactly like a tool that does not work."
            ),
            arguments=reading,
            produces=(
                Output(
                    "ok",
                    "boolean",
                    "whether the files were read as traces",
                    at="ok",
                ),
            ),
            needs=("attach",),
            cost=_agent_cost(
                THE_TRACE_READER,
                find_out_by=(
                    "it reads files already on your disk; run it over one file "
                    "and the rate is known for this machine"
                ),
                requests_why=(
                    "reading a file that is already on your disk asks your model "
                    "nothing"
                ),
            ),
            operates_on=target,
            exit_criterion=ExitCriterion(
                stated=(
                    f"{THE_TRACE_READER} reports a completed read of the files "
                    "you named"
                ),
                source="tool_result",
                subject="ok",
                comparator="is_true",
            ),
            risks=(
                Risk(
                    what=(
                        "the files are a well-formed trace of something that is "
                        "not an agent"
                    ),
                    what_we_do=(
                        "nothing is stamped. A file of HTTP and database spans "
                        "is a real trace and it is not a record of what an agent "
                        "did, and opening this outcome with one would be the "
                        "honesty test defeated by a file that merely parsed"
                    ),
                ),
                Risk(
                    what="the files are a vendor's own export rather than a trace",
                    what_we_do=(
                        "the step says which format it could not read rather "
                        "than reporting an empty trace, which reads as 'your "
                        "system did nothing'. The escape is a configuration line "
                        "on your side rather than a smaller answer from ours"
                    ),
                ),
                Risk(
                    what="there genuinely is no recording of the failing runs",
                    what_we_do=(
                        "then this build does not move the outcome and says so "
                        "rather than pretending. The next move is turning "
                        "tracing on inside code this harness does not own, and "
                        "that one is yours"
                    ),
                ),
            ),
        ),
        _recheck_step(
            ("traces",),
            fact,
            why=(
                "Walk the tree again now that something has actually been read. "
                "Which problem you have is the engine's to decide from what the "
                "trace says, and it could not decide anything without one."
            ),
        ),
    ]

    egress = _egress_for([step.tool for step in steps])
    said = str(situation.result.say or "").strip()

    return Build(
        id="read_the_traces",
        title="Read what the agent actually did, before diagnosing why it went wrong",
        for_outcome=situation.outcome,
        because=(
            (f"{said} " if said else "")
            + "This build reads the recording you point at and reports what is "
            f"in it. It names your files through {THE_TRACE_READER}'s own "
            f"`{names_the_file}` argument, taken from that tool's schema rather "
            "than from a table in this file."
            + (
                " Nothing in this plan can leave the machine: not one step's "
                "tool declares a network read, so the sandbox declares no egress "
                "at all, and a local read is local."
                if not egress
                else " One step in this plan reaches the network, which is "
                "declared on the environment below where you can see it before "
                "you approve it."
            )
            + (
                ""
                if not unidentified
                else f" {unidentified} - so nothing here is costed from a stored "
                "measurement."
            )
            + " AND WHAT IS IN A TRACE IS SOMEBODY ELSE'S TEXT. Tool "
            "descriptions and tool arguments arrive from a file this harness did "
            "not write, and text in one that tries to instruct a model is a "
            "finding worth showing you rather than something to pass along "
            "quietly."
        ),
        steps=tuple(steps),
        environment=_sandbox("read_the_traces", traces, reason=egress),
        exit_criterion=ExitCriterion(
            stated=(
                f"{fact} is MEASURED - read out of the files you named rather "
                "than assumed from their being there. "
                + the_criterion_this_ledger_owes(
                    fact,
                    spec,
                    node=str(situation.result.node or ""),
                    outcome=situation.outcome,
                )
            ),
            source="diagnosis",
            subject=f"fact_origins.{fact}",
            comparator="is_measured",
        ),
        risks=(
            Risk(
                what="the traces say the tools were never called at all",
                what_we_do=(
                    "that is the plan working, and it is the most valuable answer "
                    "this instrument gives. A tool that is never called is the "
                    "commonest real defect in an agent system and the least often "
                    "diagnosed, and it is invisible without the recording"
                ),
            ),
        ),
        facts=dict(situation.origins),
    )


def _propose_classify_the_agent_failures(situation: Situation) -> Build:
    """`ACTION__CLASSIFY_THE_FAILURES` - the hinge of this ledger, and one build.

    THE SAME PLACE THE FIRST LEDGER TURNS ON, REACHED INDEPENDENTLY. Until the
    failures are bucketed every remedy is a guess, and this ledger routes its
    buckets to different stages, several of which end in a refusal rather than a
    build. `_propose_classify_the_failures` is the first ledger's version of the
    same sentence and the shape is the same; what is different here is that it
    takes TWO instruments, and that is a measurement rather than a preference -
    see `the_agent_bucketer_is_registered`.

    **AND IT REFUSES WHEN THE FLOOR CANNOT BE REACHED.** The ledger asks for at
    least N bucketed failures before it will route, and N is read off the node
    that states it rather than typed. A failure set the harness has already
    COUNTED as smaller than N cannot produce a histogram that opens this
    outcome, however well it runs - so the plan stops, names both numbers and
    where the floor was read, rather than spending somebody's system to arrive
    back here. That refusal fires on a MEASURED count and on nothing else,
    because a count nobody took is not evidence that the set is small.
    """
    spec = situation.spec
    fact = THE_BUCKET_FACT

    missing = agent_tools_missing(THE_TRACE_READER, THE_FAILURE_RUNNER)
    if missing:
        raise NotEnoughToPropose(
            "The bucketer is two instruments and "
            f"{list(missing)} of {list(THE_AGENT_TOOLS)} are not registered here. "
            "Several of the buckets this ledger routes on cannot be decided from "
            "an answer string, so a build that ran the failures without reading "
            "the traces would produce a histogram missing exactly the buckets "
            "that send you somewhere different.",
            needs=tuple(missing),
        )

    _nothing_would_stamp_it(fact, situation.outcome, spec)

    floor, floor_said_in = failures_to_bucket(situation.outcome, spec)
    buckets = buckets_the_ledger_routes(spec)
    if not buckets:  # pragma: no cover - the ledger stopped forking on this fact
        raise NotEnoughToPropose(
            f"No node in {spec.as_written} forks on {fact!r}, so this ledger "
            "routes no buckets and a classification would decide nothing. "
            "Nothing is planned against bucket names this file chose.",
            needs=(fact,),
        )

    counted = _an_integer(situation.values.get("failing_cases_n"))
    if situation.is_measured("failing_cases_n") and counted < floor:
        raise NotEnoughToPropose(
            f"You have {counted} failures, measured, and this ledger will not "
            f"route on fewer than {floor} bucketed ones - read from "
            f"{floor_said_in}. Running and bucketing what you have cannot reach "
            "the floor however well it goes, so this plan would spend your "
            "system to land back on this outcome. What is needed is more real "
            "failures from actual use, and writing those down is yours.",
            needs=("failing_cases_n",),
        )

    failures = situation.require_path("failures_path")
    traces = situation.require_path("trace_path")

    reading = _a_call_that_fits(
        THE_TRACE_READER, {name: traces for name in _THE_TRACE_ARGUMENTS}
    )
    _at_least_one_of(
        reading,
        THE_TRACE_READER,
        _THE_TRACE_ARGUMENTS,
        what="which file or directory holds the traces",
    )

    running = _the_failure_run_call(situation, failures)
    _at_least_one_of(
        running,
        THE_FAILURE_RUNNER,
        _THE_FAILURE_ARGUMENTS,
        what="which file holds the failures to re-run",
    )
    joined = any(name in running for name in ("trace_path", "traces_path"))
    if not joined:
        raise NotEnoughToPropose(
            f"{THE_FAILURE_RUNNER} declares no argument this plan can hand the "
            f"traces to - it takes "
            f"{sorted((_spec(THE_FAILURE_RUNNER).schema.get('properties') or {}).keys())} "
            f"and none of {list(_THE_TRACE_ARGUMENTS)} is among them. Then the "
            "buckets that need the trace cannot be decided at all, the histogram "
            "would be missing exactly the ones that route somewhere different, "
            "and a build that produced it would send your whole diagnosis down "
            "the branch the readable buckets happened to win. That is a "
            "disagreement between two lanes about what an argument is called, "
            "and the honest answer is to stop rather than to draw it.",
            needs=tuple(f"{THE_FAILURE_RUNNER}.{n}" for n in _THE_TRACE_ARGUMENTS),
        )
    target, unidentified = _subject_of_a_call(THE_FAILURE_RUNNER, running)

    steps: list[Step] = [
        _attach(
            "attach",
            failures,
            role="the failure set to bucket",
            why=(
                "Record where the failures are, so the run and the histogram "
                "below are about the set you named rather than about whichever "
                "file was mentioned most recently."
            ),
        ),
        Step(
            id="traces",
            tool=THE_TRACE_READER,
            why=(
                "Read what the system actually did on these runs. Which tool was "
                "chosen, whether it returned an error, and what the model was "
                "given are things this ledger routes on and none of them is "
                "visible in the answer the agent produced."
            ),
            arguments=reading,
            produces=(
                Output("ok", "boolean", "whether the traces were read", at="ok"),
            ),
            needs=("attach",),
            cost=_agent_cost(
                THE_TRACE_READER,
                find_out_by=(
                    "it reads files already on your disk; run it over one file "
                    "and the rate is known for this machine"
                ),
                requests_why="reading a file on your disk asks your model nothing",
            ),
            operates_on=_subject_of_a_call(THE_TRACE_READER, reading)[0],
            exit_criterion=ExitCriterion(
                stated=f"{THE_TRACE_READER} reports a completed read",
                source="tool_result",
                subject="ok",
                comparator="is_true",
            ),
        ),
        Step(
            id="run",
            tool=THE_FAILURE_RUNNER,
            why=(
                "Run the failures and sort the ones that still fail into this "
                f"ledger's own buckets: {', '.join(buckets)}. Which of them holds "
                "the most decides what you are asked about next, and this ledger "
                "sends them to different places - several of which end in 'do "
                "not build it'."
                + (
                    " The traces are named on this call, so the buckets that "
                    "need them can be decided rather than left unclassified."
                    if joined
                    else f" {THE_FAILURE_RUNNER} declares no argument for the "
                    "traces, so this plan runs the read first and lets the two "
                    "instruments meet in the harness rather than in one call - "
                    "and a failure no rule could name is reported unclassified "
                    "rather than guessed at."
                )
            ),
            arguments=running,
            produces=(
                Output(
                    "ok",
                    "boolean",
                    "whether the run completed rather than stopping part way",
                    at="ok",
                ),
            ),
            needs=("traces",),
            cost=_agent_cost(
                THE_FAILURE_RUNNER,
                find_out_by=(
                    "nothing has timed a run of your system on this machine; run "
                    "the set with a small cap first and read the seconds back"
                ),
                requests_why=(
                    "one failure is at least one request and a loop makes as "
                    "many as it decides to, so the count is a property of your "
                    "system rather than of your file"
                ),
            ),
            operates_on=target,
            exit_criterion=ExitCriterion(
                stated=(
                    f"{THE_FAILURE_RUNNER} reports a completed run over the "
                    "failure set"
                ),
                source="tool_result",
                subject="ok",
                comparator="is_true",
            ),
            risks=(
                Risk(
                    what=(
                        f"fewer than {floor} failures end up bucketed, which is "
                        f"the floor {floor_said_in} states"
                    ),
                    what_we_do=(
                        "the histogram is real and too small to route on, and "
                        "the diagnosis lands back here rather than on a branch "
                        "chosen from a handful of cases. This plan does not "
                        "raise the sample to guarantee the floor, because that "
                        "means assuming a failure rate and spending your system "
                        "on the assumption"
                    ),
                ),
                Risk(
                    what="the failures are ones no rule here can name",
                    what_we_do=(
                        "they are reported unclassified and left out of the "
                        "histogram rather than guessed into a bucket. A bucket "
                        "guessed from an answer string would route your whole "
                        "diagnosis on a fact about our guesser"
                    ),
                ),
                Risk(
                    what="a run does not terminate",
                    what_we_do=(
                        "it has no answer, so it is not in the histogram. "
                        "Bucketing it is how a loop that never stops gets "
                        "diagnosed as a formatting problem; it is evidence for "
                        "the question about termination instead"
                    ),
                ),
            ),
        ),
        _recheck_step(
            ("run",),
            fact,
            why=(
                "Walk the tree again on the buckets. Which one dominates decides "
                "the branch, several of this ledger's routes end in a refusal "
                "rather than a build, and choosing between them is the engine's "
                "job rather than this plan's."
            ),
        ),
    ]

    egress = _egress_for([step.tool for step in steps])
    said = str(situation.result.say or "").strip()

    return Build(
        id="classify_the_agent_failures",
        title="Find out what kind of failing it is, before choosing what to build",
        for_outcome=situation.outcome,
        because=(
            (f"{said} " if said else "")
            + "Something is failing and nothing here knows what KIND of failing "
            "it is. The wrong tool, a tool that broke, a wrong conclusion, "
            "missing context and an unusable answer are different problems with "
            "different cheapest fixes, and this ledger sends them to different "
            f"stages. The floor is {floor}, read from {floor_said_in} rather "
            f"than chosen here, and the buckets are {list(buckets)}, read off "
            "this ledger's own fork rather than listed in this file."
            + (
                " Nothing in this plan can leave the machine."
                if not egress
                else " One step in this plan reaches the system you connected, "
                "which is declared on the environment below where you can see it "
                "before you approve it."
            )
            + (
                ""
                if not unidentified
                else f" {unidentified} - so no cost here is derived from a stored "
                "count."
            )
        ),
        steps=tuple(steps),
        environment=_sandbox(
            "classify_the_agent_failures", failures, traces, reason=egress
        ),
        exit_criterion=ExitCriterion(
            stated=(
                f"{fact} is MEASURED - buckets this harness produced from runs it "
                "graded itself and traces it read itself, not a shape somebody "
                "described. "
                + the_criterion_this_ledger_owes(
                    fact,
                    spec,
                    node=str(situation.result.node or ""),
                    outcome=situation.outcome,
                )
            ),
            source="diagnosis",
            subject=f"fact_origins.{fact}",
            comparator="is_measured",
        ),
        risks=(
            Risk(
                what="the dominant bucket is not the one you expected",
                what_we_do=(
                    "that is the plan working. The build's job is to produce the "
                    "histogram, not a particular shape of it, and the engine "
                    "re-reads the tree on whatever comes back - including the "
                    "answers that say not to build an agent at all"
                ),
            ),
        ),
        facts=dict(situation.origins),
    )


def _subject_of_a_call(
    tool_name: str, arguments: Mapping[str, Any]
) -> tuple[Subject | None, str]:
    """What a step running this tool with these arguments will operate on.

    THE LIST THAT USED TO BE HERE IS GONE, and its removal is the point rather
    than a tidy-up. It was `("eval_path", "path", "dataset_path")` - a closed
    table in this file naming which argument of somebody else's tool holds the
    thing that tool opens. Every such list is a second opinion that drifts: the
    tool grows an argument, or a tool arrives that reads `train_path`, and the
    list here is still right about the tools it was written for and silently
    wrong about the new one. `app/build.py`'s `subject_of_a_call` asks the TOOL,
    through the declaration described in `declared_subject_arguments`, and where
    a tool has not declared, refuses to guess rather than picking the first name
    it recognises.

    The second half of the return is why nobody can tell, when nobody can. It is
    not decoration: it goes into the UNKNOWN estimate the caller builds, so the
    person reads "this call names two files and nothing says which one gets
    scored - here is a step that counts the one you named" instead of a number.
    """
    return build.subject_of_a_call(_spec(tool_name), arguments)


def _arguments_for(tool_name: str, situation: Situation) -> dict[str, Any]:
    """The arguments a settling tool needs, from what the caller told us.

    Deliberately a small closed table rather than anything clever. A tool whose
    arguments cannot be filled from the situation raises, and the refusal names
    what is missing - which is the whole contract of this module.
    """
    if tool_name == "measure_eval_set":
        return {"path": situation.require_path("eval_path"), "finish_the_count": True}
    if tool_name == "profile_dataset":
        return {"path": situation.require_path("dataset_path") if situation.dataset_path else situation.require_path("eval_path")}
    if tool_name == "measure_baseline":
        path = situation.require_path("eval_path")
        if not situation.input_field or not situation.expected_field:
            raise NotEnoughToPropose(
                "measure_baseline needs the column holding the input and the "
                "column holding the right answer, and neither was given",
                needs=("input_field", "expected_field"),
            )
        return {
            "eval_path": path,
            "input_field": situation.input_field,
            "expected_field": situation.expected_field,
            "sample": situation.sample,
        }
    if tool_name == "inspect_hardware":
        return {}
    if tool_name == "measure_retriever_recall":
        # THE ONE TOOL `evidence.resolves` WILL ROUTE HERE THAT THIS FUNCTION
        # CANNOT ANSWER, and the reason is a shape rather than a missing path.
        # `_propose_substantiate` writes ONE step per tool; recall needs an index
        # to exist before it can be measured, and there is no way to say "and
        # build the index first" in a one-step-per-tool build. Handing back
        # arguments anyway would produce a step that runs against no index and
        # reports whatever that is, which is the plausible-looking build this
        # module exists to refuse.
        raise NotEnoughToPropose(
            "measuring a retriever needs an index to measure, and a "
            "substantiation build is one step per tool with nowhere to put the "
            "indexing. Ask for a build for the retrieval outcome instead - "
            "propose_build with corpus_path names the corpus, indexes it, and "
            "measures recall against your eval set in one plan",
            needs=("corpus_path",),
        )
    raise NotEnoughToPropose(
        f"nothing here knows what arguments {tool_name} needs for this situation, "
        "so no step is written for it",
        needs=(tool_name,),
    )


# ---------------------------------------------------------------------------
# The table, and the honest account of what is not in it.


class _WhatTheRegistryDecides(Mapping[str, Any]):
    """A table whose last entries exist only while the tools behind them do.

    **WHY THIS IS NOT A PLAIN DICT, AND IT IS NOT CLEVERNESS.** `propose_build`
    hands `sorted(PROPOSERS)` back to the caller as `covered_outcomes`, and
    `app/asking.py` reads these three tables to tell a person whether the
    product can act on their verdict. A hardcoded entry for an outcome whose
    tools are not registered would make the product SAY it covers something it
    cannot build - which is the one failure this module exists to prevent,
    reached through the door marked coverage instead of the door marked plan.

    So membership is decided by the live registry, every time it is read. Today
    `app/tools/retrieval.py` is being written in another lane and the three tool
    names are fixed between us; the day it lands, `NO_TRAIN__RAG` and
    `ACTION__MEASURE_RETRIEVER_RECALL` move from `NOT_COVERED` to `COVERAGE` and
    the proposer starts answering, with nothing here edited and no window in
    which one of these tables is a lie. It also survives any import order:
    reading at import time would freeze the answer that happened to be true when
    `app/tools/__init__.py` reached this module.

    A `Mapping` rather than a dict subclass because everything that reads these
    wants `in`, `len`, `get`, `items` and iteration, and none of them may write.
    """

    def __init__(
        self,
        fixed: Mapping[str, Any],
        *,
        extra: Callable[[], Mapping[str, Any]],
        when: Callable[[], bool] | None = None,
    ) -> None:
        self._fixed = dict(fixed)
        self._extra = extra
        # `when` IS OPTIONAL NOW BECAUSE THERE ARE TWO BENCHES BEHIND ONE TABLE.
        # One conditional group needed one question; two need a function that
        # asks both and merges what it finds, and folding the condition into
        # `extra` is the only shape that stays correct when a third arrives. A
        # missing `when` therefore means "always ask `extra`", and `extra`
        # answers with nothing when nothing applies - which is what makes
        # `COVERAGE` and `NOT_COVERED` disjoint by construction rather than by a
        # rule somebody remembers.
        self._when = when or (lambda: True)

    def _live(self) -> dict[str, Any]:
        merged = dict(self._fixed)
        if self._when():
            merged.update(self._extra())
        return merged

    def __getitem__(self, key: str) -> Any:
        return self._live()[key]

    def __iter__(self):
        return iter(self._live())

    def __len__(self) -> int:
        return len(self._live())

    def __repr__(self) -> str:  # pragma: no cover - a debugging convenience
        return repr(self._live())


_PROPOSERS_THAT_ALWAYS_EXIST: dict[str, Callable[[Situation], Build]] = {
    "BLOCKED__BUILD_EVAL_SET": _propose_build_the_eval_set,
    "ACTION__MEASURE_BASELINE": _propose_measure_the_baseline,
    "ACTION__COUNT_THE_ROWS": _propose_count_the_rows,
    "ACTION__MAKE_THE_METRIC_PROGRAMMATIC": _propose_make_the_metric_programmatic,
    "ACTION__NAME_THE_MODALITY": _propose_name_the_modality,
    "ACTION__SUBSTANTIATE_CLAIMED_FACTS": _propose_substantiate,
    "ACTION__CLASSIFY_FAILURES": _propose_classify_the_failures,
    "NO_TRAIN__BETTER_PROMPT": _propose_try_a_prompt,
    "NO_TRAIN__FEW_SHOT": _propose_try_a_prompt,
}

#: The two the retrieval bench answers. Both go through one proposer, as the two
#: prompt outcomes do, because they share every step and differ in which node's
#: exit criterion they are held to.
_PROPOSERS_THE_RETRIEVAL_BENCH_BRINGS: dict[str, Callable[[Situation], Build]] = {
    "NO_TRAIN__RAG": _propose_the_retrieval_bench,
    "ACTION__MEASURE_RETRIEVER_RECALL": _propose_the_retrieval_bench,
}

#: The one the chunking sweep brings, kept in the same shape as the group above
#: so a third bench is a third dict rather than a third mechanism.
_PROPOSERS_THE_CHUNKING_SWEEP_BRINGS: dict[str, Callable[[Situation], Build]] = {
    "NO_TRAIN__FIX_RETRIEVAL": _propose_fix_the_retriever,
}

#: THE FIRST TRAINING OUTCOME WITH A BUILD BEHIND IT, in the same shape as the
#: three groups above and conditional for the same reason - the seven tools it
#: names are registered by four different modules and a hardcoded entry would
#: make this product SAY it covers a training verdict in a process where it
#: cannot. One entry and not nine: the other eight training outcomes stay in
#: `NOT_COVERED` with their own reason, because a DPO run, a distillation and a
#: from-scratch pretrain are three different builds and one of them has no
#: backend here at all.
_PROPOSERS_THE_TRAINING_BENCH_BRINGS: dict[str, Callable[[Situation], Build]] = {
    "TRAIN__LORA_SFT": _propose_train_the_adapter,
    "TRAIN__DPO": _propose_train_on_preferences,
    # THE THIRD LEDGER. Eight builds behind twenty-eight outcomes, and the other
    # twenty are refusals, handoffs, and the four questions only the person can
    # answer - each with its reason in NOT_COVERED rather than a build that
    # would spend somebody's afternoon arriving back where it started.
    "SPEC__WRITE_THE_TASK": _propose_read_the_checker,
    "SPEC__BUILD_A_STARTER_EVAL": _propose_count_the_tasks,
    "SPEC__MAKE_THE_TASKS_RERUNNABLE": _propose_count_the_tasks,
    "SPEC__RUN_THE_MODEL_ALONE": _propose_score_the_bare_model,
    "SPEC__ABLATE_THE_HARNESS": _propose_ablate_the_components,
    "SPEC__DECLARE_THE_BLAST_RADIUS": _propose_read_the_blast_radius,
    "SPEC__BOUND_THE_RUN": _propose_bound_the_harness,
    "SPEC__INSTRUMENT_THE_LOOP": _propose_bound_the_harness,
    "HARNESS__TOOL_LAYER": _propose_the_harness,
    "HARNESS__FIXED_PIPELINE": _propose_the_harness,
    "HARNESS__AGENT_LOOP": _propose_the_harness,
    "HARNESS__AGENT_TEAM": _propose_the_harness,
}

#: THE FIRST OUTCOME OF THE CLASSICAL BRANCH WITH A BUILD BEHIND IT. ONE entry
#: and not six: `NO_DEEP__TABPFN`, `NO_DEEP__TUNE_THE_TREES_FIRST`,
#: `NO_DEEP__HYBRID_EMBED_PLUS_GBDT`, `NO_DEEP__CLASSICAL_FORECAST` and
#: `NO_DEEP__FIND_THE_MISSING_FEATURE` stay in `NOT_COVERED` with their own
#: reasons, because a foundation model, a fifty-trial search, a sentence
#: encoder, a forecaster and a join are five different pieces of work and a
#: single tree fit is none of them.
_PROPOSERS_THE_TABULAR_BENCH_BRINGS: dict[str, Callable[[Situation], Build]] = {
    "NO_DEEP__GRADIENT_BOOSTED_TREES": _propose_fit_the_tree,
}


def the_agent_instruments_are_registered() -> bool:
    """All four instruments, or none of this ledger's coverage is claimed."""
    names = {spec.name for spec in REGISTRY}
    return {
        "read_agent_traces",
        "read_tool_definitions",
        "run_the_failures",
        "bound_the_loop",
    } <= names


def _tool_layer_step_list(
    situation: Situation,
    *,
    leading_definitions: bool,
) -> list[Step]:
    """The measurement core both tool-layer builds share, and the one seam.

    `leading_definitions` is the difference between the two outcomes, stated
    as order rather than as prose: AGENT_WITH_TOOLS has tools whose layer went
    stale, so it re-grades first; TOOLS_FOR_AN_EXISTING_LOOP is arriving from
    ZERO tools, so the first thing to verify is that what the person wired
    actually parses as definitions - name and description by AST or JSON,
    before anything is graded against them.
    """
    traces = situation.require_path("traces_path")
    failures = situation.require_path("failures_path")

    grading = {
        "failures_path": failures,
        "input_field": situation.input_field,
        "expected_field": situation.expected_field,
        "answer_field": situation.answer_field,
        "traces_path": traces,
    }
    # CHECKED ON ALL THREE, BECAUSE THE MESSAGE NAMES ALL THREE. It used to test
    # `input_field` alone while asking for three, so a caller who named two got
    # a plan that was drawn, approved and then failed on the third at run time -
    # which is the one thing `NotEnoughToPropose` exists to prevent. A refusal
    # before the plan is cheap; a refusal after approval is not.
    _missing = tuple(
        name
        for name in ("input_field", "expected_field", "answer_field")
        if not str(getattr(situation, name, "") or "").strip()
    )
    if _missing:
        raise NotEnoughToPropose(
            "I cannot grade a recording without knowing which columns hold the "
            "input, the answer that would be right, and what the agent actually "
            "said. Missing: " + ", ".join(_missing) + ".",
            needs=_missing,
        )

    steps: list[Step] = []

    if leading_definitions:
        definitions = situation.require_path("tooldefs_path")
        steps.append(
            Step(
                id="defs",
                tool="read_tool_definitions",
                why=(
                    "You arrived here from zero tools, so the first thing to "
                    "confirm is that what you just wired PARSES as tool "
                    "definitions - names, descriptions, schemas where the "
                    "format carries them, Python read by AST and nothing "
                    "executed. Grading failures against definitions that do "
                    "not parse measures nothing."
                ),
                arguments={"path": definitions},
                produces=(
                    Output(
                        "tool_count",
                        "integer",
                        "how many tool definitions the file declares",
                        at="tool_count",
                    ),
                ),
                needs=(),
                cost=_local_cost(
                    "read_tool_definitions",
                    find_out_by=(
                        "it reads one file this machine already holds; time "
                        "one read and it is timed for every build"
                    ),
                ),
                exit_criterion=ExitCriterion(
                    stated="the definitions file parses and at least one tool is declared",
                    source="tool_result",
                    subject="ok",
                    comparator="is_true",
                ),
            )
        )

    steps.append(
        Step(
            id="rerun",
            tool="run_the_failures",
            why=(
                "Grade the same failure rows against the newest record of your "
                "agent's answers, joined to its traces, and bucket every "
                "failure into this ledger's own five. Everything the gates "
                "paid with goes stale when the agent changes; this refreshes "
                "the half that says WHAT is failing and how often."
            ),
            arguments=grading,
            produces=(
                Output(
                    # THE SECOND LEDGER'S NAME, NOT THE FIRST'S. The ML bench
                    # stamps `failure_histogram`; run_the_failures stamps THIS
                    # ledger's `failure_buckets`, and a plan that promised the
                    # other word would fail at execution with "the plan and
                    # the tool disagree" - which is precisely what the storm
                    # said when this said the wrong noun.
                    "failure_buckets",
                    "object",
                    "how the failing rows bucketed, in this ledger's five buckets",
                    at="failure_buckets",
                ),
                Output(
                    "success_rate",
                    "number",
                    "the share of rows answered correctly, with its interval",
                    at="success_rate",
                ),
            ),
            needs=("defs",) if leading_definitions else (),
            cost=_local_cost(
                "run_the_failures",
                find_out_by=(
                    "it grades answers already on your disk and asks your model "
                    "nothing; time one read and it is timed for every build"
                ),
            ),
            operates_on=_subject_of_a_call("run_the_failures", grading)[0],
            exit_criterion=ExitCriterion(
                stated=(
                    "every row is graded, the failures are bucketed by rule "
                    "into this ledger's own vocabulary, and the count is on disk"
                ),
                source="tool_result",
                subject="ok",
                comparator="is_true",
            ),
        )
    )

    steps.append(
        Step(
            id="bound",
            tool="bound_the_loop",
            why=(
                "Re-read cost and termination off the traces, so the size of a "
                "run is measured as of NOW rather than borrowed from the run "
                "that routed you here in the first place. A loop bound that "
                "was true last week is an anecdote."
            ),
            arguments={"path": traces},
            produces=(
                Output(
                    "tokens_per_run",
                    "number",
                    "median tokens per run across the set, all-or-nothing",
                    at="tokens_per_run.median",
                ),
            ),
            needs=(),
            cost=_local_cost(
                "bound_the_loop",
                find_out_by=(
                    "it parses JSON Lines this machine already holds; time one "
                    "read and it is timed for every build"
                ),
            ),
            exit_criterion=ExitCriterion(
                stated="the set reads back with per-run token totals and a termination figure",
                source="tool_result",
                subject="ok",
                comparator="is_true",
            ),
        )
    )

    steps.append(
        _recheck_step(
            ("rerun", "bound"),
            "failure_buckets",
            why=(
                "Walk the tree again on the refreshed sheet. Whether the "
                "verdict moves - and toward what - is the engine's sentence "
                "on evidence this build just made current, never this plan's."
            ),
        )
    )

    return steps


def _propose_the_tool_layer_loop(situation: Situation) -> Build:
    """`BUILD__AGENT_WITH_TOOLS` - the first second-ledger build.

    THE VERDICT SAYS TOOLS BELONG IN THIS LOOP; THE MEASUREMENT SAYS NOBODY
    KNOWS WHETHER THEY HELPED. An agent-with-tools diagnosis that cleared all
    five gates stands on a measured tool layer - call rate, bucketed failures,
    tokens per run, termination - and every one of those numbers goes stale the
    moment anything changes: a prompt edit, a tool description rewrite, a model
    swap. This build re-measures the layer and walks the tree again, so the
    next verdict is attributed to what changed rather than asserted about it.
    It runs nobody's agent: `run_the_failures` grades answers already on disk,
    which is the honest fallback for code that is theirs (see that tool's
    docstring), and `bound_the_loop` reads traces the same way.

    IT IS DELIBERATELY NOT A PAIRED COMPARISON YET. The proof that a description
    change moved the failure rate is this build run twice - once before, once
    after - over the SAME rows, compared with McNemar; `evals.compare` exists
    and nothing here re-implements it. What is missing is the second recording,
    which only the person can produce by running their changed agent. The plan
    says so in its risks rather than pretending one leg of a paired test is a
    difference.
    """
    return Build(
        id="the_tool_layer_loop",
        title="Re-measure the agent's tool layer, then let the engine decide again",
        for_outcome=situation.outcome,
        because=(
            "The verdict says an agent with tools is the right shape of thing "
            "here, and the gates were paid with measurements of the tool "
            "layer as it WAS. Any change - prompt, description, model - makes "
            "those numbers someone else's until they are taken again. This "
            "build takes them again: grade, bound, walk. It does not run your "
            "agent; it reads the records your agent leaves."
        ),
        steps=tuple(_tool_layer_step_list(situation, leading_definitions=False)),
        environment=_sandbox(
            "the_tool_layer_loop",
            situation.traces_path,
            situation.failures_path,
        ),
        exit_criterion=ExitCriterion(
            stated=(
                "failure_buckets and the loop bounds are MEASURED as of this "
                "build's run - refreshed from files on disk, not carried forward"
            ),
            source="diagnosis",
            subject="fact_origins.failure_buckets",
            comparator="is_measured",
        ),
        risks=(
            Risk(
                what="the dominant bucket is not the one it was",
                what_we_do=(
                    "that is the plan working. The build's job is a current "
                    "picture, not a particular one, and the engine re-reads "
                    "the tree on whatever comes back"
                ),
            ),
            Risk(
                what=(
                    "the answers file predates your latest change, so the "
                    "re-run measures an agent that no longer exists"
                ),
                what_we_do=(
                    "this build cannot tell, and says so instead of guessing: "
                    "re-export your agent's answers after each change and keep "
                    "one file per change. The paired comparison that proves a "
                    "difference is two such recordings over the same rows, "
                    "compared with McNemar - the second recording is yours"
                ),
            ),
            Risk(
                what="some runs carry inference spans without token counts",
                what_we_do=(
                    "nothing is stamped from a set the reader knows is short. "
                    "The step refuses whole and names the spans, because a "
                    "partial total reads as complete"
                ),
            ),
        ),
    )


def _propose_tools_for_an_existing_loop(situation: Situation) -> Build:
    """`BUILD__TOOLS_FOR_AN_EXISTING_LOOP` - arriving from zero tools.

    THE VERDICT'S OWN `say` CALLS IT THE CHEAP BUILD: *give the loop you
    already have the tools it is missing.* This outcome mints at
    S3_NO_TOOLS_AT_ALL - choice failures on a sheet where tool_count read zero -
    so the movement this build owes is from NOTHING DECLARED to tools declared,
    called and graded. That is why its step list leads with the definitions
    reader where the sibling build leads with the re-run: before anything is
    graded against what you wired, the harness confirms it parses as
    definitions at all. Same measurement core, different first question, and
    the order says so.

    WHAT IT DOES NOT DO IS WRITE YOUR TOOLS. A tool definition for YOUR loop
    encodes YOUR business logic, and authoring it here would be this file
    guessing at the thing only you know. The plan's risk column carries that
    obligation in so many words: between approving and running, you wire the
    definitions and export a fresh answers file - and if the count still reads
    zero when the storm arrives, the defs step refuses rather than grading
    against nothing.
    """
    return Build(
        id="tools_for_an_existing_loop",
        title="Wire the missing tools into the loop you already have, then measure",
        for_outcome=situation.outcome,
        because=(
            "Choice failures on a sheet whose tool count read zero mean the "
            "loop was never given anything to call. The cheapest honest move "
            "is the one the verdict names: add the tools, then measure whether "
            "the same rows do better - with this harness reading definitions, "
            "grades and bounds off disk, never running your loop."
        ),
        steps=tuple(_tool_layer_step_list(situation, leading_definitions=True)),
        environment=_sandbox(
            "tools_for_an_existing_loop",
            situation.traces_path,
            situation.failures_path,
            situation.tooldefs_path,
        ),
        exit_criterion=ExitCriterion(
            stated=(
                "tool definitions parse, failure_buckets and the loop bounds "
                "are MEASURED as of this build's run"
            ),
            source="diagnosis",
            subject="fact_origins.failure_buckets",
            comparator="is_measured",
        ),
        risks=(
            Risk(
                what=(
                    "the definitions file still declares nothing when the "
                    "storm reaches the defs step"
                ),
                what_we_do=(
                    "it refuses there rather than grading against nothing, and "
                    "the refusal names the file. Wiring the tools is the half "
                    "only you can do; this plan cannot and will not fake it"
                ),
            ),
            Risk(
                what="the new tools fire and the answers are STILL wrong",
                what_we_do=(
                    "that is a result, not a failure of the plan: the recheck "
                    "walks whatever tree the refreshed buckets route to, and "
                    "the next verdict costs one more recording, not a rebuild"
                ),
            ),
            Risk(
                what="some runs carry inference spans without token counts",
                what_we_do=(
                    "nothing is stamped from a set the reader knows is short. "
                    "The step refuses whole and names the spans, because a "
                    "partial total reads as complete"
                ),
            ),
        ),
    )


def _propose_multi_agent(situation: Situation) -> Build:
    """`BUILD__MULTI_AGENT` - the hardest outcome in the ledger by design.

    `docs/ledgers/AI_ENGINEERING_DESIGN.md`: *"BUILD__MULTI_AGENT should be the
    hardest outcome in the ledger to reach, for the same reason
    TRAIN__FROM_SCRATCH is in the ML one."* Its gate row is the strict
    superset (adds `single_agent_tried`), and fourteen of MAST's modes cannot
    occur in a single agent at all. This build does not pretend to orchestrate
    your agents - it measures whether the failure distribution across the traces
    you already have justifies ever asking that question, and it refuses rather
    than scaffolding a fleet on a hunch.
    """
    return Build(
        id="multi_agent_from_single_recordings",
        title="Measure whether your single-agent failures justify a multi-agent shape",
        for_outcome=situation.outcome,
        because=(
            "The verdict says one context cannot hold this, and every easier "
            "shape - one call, a fixed sequence, one agent - has been tried and "
            "measured. A fleet is coordination debt you cannot undo, so the "
            "harness re-grades and re-bounds the same rows and walks again on "
            "paper before anybody writes orchestration. If the re-measured "
            "buckets still point here, you have the numbers to justify the next "
            "build; if they do not, you just saved the build that would have "
            "failed for the same reason the diagnosis already named."
        ),
        steps=tuple(_tool_layer_step_list(situation, leading_definitions=False)),
        environment=_sandbox(
            "multi_agent_from_single_recordings",
            situation.traces_path,
            situation.failures_path,
        ),
        exit_criterion=ExitCriterion(
            stated=(
                "failure_buckets and the loop bounds are MEASURED as of this "
                "build's run - the shape of failing does not change until it does"
            ),
            source="diagnosis",
            subject="fact_origins.failure_buckets",
            comparator="is_measured",
        ),
        risks=(
            Risk(
                what="the dominant bucket moved away from reasoning",
                what_we_do=(
                    "that is the plan working: the measurement cost one re-grade "
                    "and the engine re-reads the tree on whatever comes back - "
                    "including a single-agent fix you already have"
                ),
            ),
            Risk(
                what="the fleet you imagine needs a corpus MAST actually studied",
                what_we_do=(
                    "eight of fourteen multi-agent modes need inter-agent trace "
                    "shapes this file never invents. The plan measures the "
                    "single-agent distribution you have rather than the fleet "
                    "you have not built"
                ),
            ),
            Risk(
                what="some runs carry inference spans without token counts",
                what_we_do=(
                    "nothing is stamped from a set the reader knows is short. "
                    "The step refuses whole and names the spans"
                ),
            ),
        ),
    )


#: The reader that compares two recordings. Migration 12 gave agent runs a
#: place to live; this is the tool that reads two of them.
THE_RESULT_READER = "read_agent_results"


def the_paired_proof_is_possible() -> bool:
    """Both halves: something that grades, and something that compares.

    A comparison tool with nothing recorded to compare is a button that always
    refuses, and a grader whose output nobody keeps is the state this ledger's
    six cheapest refusals were stuck in until 2026-08-27.
    """
    return not agent_tools_missing(THE_FAILURE_RUNNER, THE_RESULT_READER)


#: THE SIX REFUSALS THAT NAME A CHEAP FIX, and what each one says is wrong.
#:
#: `docs/VISION.md` names the hole these fill: *"We tell somebody their problem
#: is the prompt, or retrieval, or their data, and hand them nothing; they close
#: the app and go and do it in the tabs we said they would not need."*
#:
#: They share one build because they share one shape. The FIX differs and is
#: always the person's - this harness will not write somebody's tool
#: description - and what the harness can do is identical in all six: measure
#: what you have, measure what you changed it to, and say whether the
#: difference is real. The `because` is per outcome because the sentence a
#: person reads has to be about THEIR problem; the steps are not.
_THE_FIXES_WORTH_PROVING: dict[str, dict[str, str]] = {
    "NO_TOOLS__DESCRIPTION_IS_THE_BUG": {
        "id": "prove_the_description_change",
        "title": "Change the descriptions, then find out whether it worked",
        "what_you_change": "the descriptions your tools declare",
        "because": (
            "The tools exist and are not being called. The description is what "
            "the model reads when it decides, so that is the thing to change - "
            "and a change nobody measured is a change nobody can keep."
        ),
    },
    "NO_TOOLS__PROMPT_IS_THE_BUG": {
        "id": "prove_the_prompt_change",
        "title": "Change the instructions, then find out whether it worked",
        "what_you_change": "the instructions your agent runs under",
        "because": (
            "The tools fire and the answers are still wrong, so the tools are "
            "not the bug and the instructions are. Rewriting them is an "
            "afternoon; knowing whether the rewrite helped is this build."
        ),
    },
    "NO_AGENT__CONSTRAIN_THE_OUTPUT": {
        "id": "prove_the_constraint",
        "title": "Constrain the output, then find out whether it worked",
        "what_you_change": "the decoding constraint or schema the output has to satisfy",
        "because": (
            "The answers are the right idea in the wrong shape. A grammar or a "
            "schema fixes shape at the point of generation, which is cheaper "
            "than any training - and the rate over the same failures is how "
            "you find out it did."
        ),
    },
    "NO_AGENT__FIX_THE_CONTEXT": {
        "id": "prove_the_context_change",
        "title": "Fix what the model is given, then find out whether it worked",
        "what_you_change": "what your agent puts in front of the model",
        "because": (
            "The failures are about what the model could not see rather than "
            "what it could not do. Changing what it is handed is the cheapest "
            "fix there is, and the same failures re-run are how you know."
        ),
    },
    "NO_AGENT__FIX_THE_TOOL": {
        "id": "prove_the_tool_fix",
        "title": "Fix the tool, then find out whether it worked",
        "what_you_change": "the tool that was failing when it ran",
        "because": (
            "The model chose correctly and the tool did not do its job. That "
            "is ordinary software repair on your side; this measures whether "
            "the repair moved the failures it was supposed to."
        ),
    },
    "NO_AGENT__ONE_API_CALL": {
        "id": "prove_the_simple_version",
        "title": "Try the simple version, then find out whether it was enough",
        "what_you_change": "the loop, replaced by one call",
        "because": (
            "The loop is not earning its complexity. One call over the same "
            "failures either answers them or does not, and that comparison is "
            "cheaper than every argument about it."
        ),
    },
}


def _propose_prove_the_fix(situation: Situation) -> Build:
    """The workbench: measure, hand the change back, re-measure, compare paired.

    ## What this build promises, and what it deliberately does not

    It does NOT promise the fix works. It promises the question *did it work*
    gets an answer that is not a guess. The exit criterion is that a paired
    comparison ran, not that its verdict is favourable - a build held to its
    own result would be a plan with a preferred outcome, and that is the one
    thing a plan may not have.

    ## Why the second recording is an input

    Because making the change means running the person's agent, and their code
    is theirs. `BUILD__TOOLS_FOR_AN_EXISTING_LOOP` already draws this line -
    *"wiring them and exporting a fresh answers file is yours between approving
    and running"* - and this refuses without `after_answers_path` in words that
    say what to go and do rather than filling one in.

    ## Why it compares rather than subtracting two rates

    Two aggregate rates subtracted is how a difference that is really noise
    gets reported as an improvement, and on failure sets of ten or twenty that
    is most differences. `read_agent_results` pairs on the QUESTION over the
    cases both recordings graded and says NO EVIDENCE when they cannot separate
    the two - the same semantics the eval bench has, inherited rather than
    re-argued.
    """
    written = _THE_FIXES_WORTH_PROVING[situation.outcome]
    failures = situation.require_path("failures_path")

    after = str(situation.after_answers_path or "").strip()
    if not after:
        raise NotEnoughToPropose(
            "I cannot prove a change that has not been made yet. This build "
            f"measures {written['what_you_change']} before and after, over the "
            "same failures, and the 'after' is your agent's answers once you "
            "have changed it - which means running your agent, which is yours "
            "rather than mine. Change it, record its answers over these same "
            "failures, and point me at that file as after_answers_path. "
            "Nothing here will write the change for you and nothing here will "
            "guess at what it produced.",
            needs=("after_answers_path",),
        )

    before = str(situation.answers_path or "").strip() or failures
    fields = {
        "input_field": situation.input_field,
        "expected_field": situation.expected_field,
        "answer_field": situation.answer_field,
    }
    missing = [name for name, value in fields.items() if not str(value or "").strip()]
    if missing:
        raise NotEnoughToPropose(
            "I cannot grade a failure set without knowing which column is the "
            f"question, which is the right answer and which is what your agent "
            f"said. Missing: {', '.join(sorted(missing))}. A grader that guessed "
            "at a column would produce a real-looking rate for a question "
            "nobody asked.",
            needs=tuple(sorted(missing)),
        )

    subject = Subject.of_path(failures)
    steps: list[Step] = [
        _attach(
            "attach",
            failures,
            role="the failures both recordings are graded over",
            why=(
                "Record which failures this is about, so the two recordings "
                "below are compared over the same questions rather than over "
                "two files that happen to look alike."
            ),
        ),
        Step(
            id="before",
            tool=THE_FAILURE_RUNNER,
            why=(
                "Grade what your agent did BEFORE the change, and keep every "
                "case. This is the leg the comparison is measured against, and "
                "a rate with no cases behind it cannot be compared to anything."
            ),
            arguments=_a_call_that_fits(
                THE_FAILURE_RUNNER,
                {"failures_path": failures, "answers_path": before,
                 "label": "before", **fields},
            ),
            produces=(
                Output("run_id", "integer", "the recording this leg wrote",
                       at="recording.run_id"),
            ),
            needs=("attach",),
            cost=_agent_cost(
                THE_FAILURE_RUNNER,
                find_out_by=(
                    "it grades rows already on your disk; one run over this set "
                    "and the rate is known for this machine"
                ),
                requests_why="grading answers you already have asks your model nothing",
            ),
            operates_on=subject,
            exit_criterion=ExitCriterion(
                stated=(
                    "the before recording exists, with one row per case it "
                    "graded"
                ),
                source="tool_result",
                subject="ok",
                comparator="is_true",
            ),
        ),
        Step(
            id="after",
            tool=THE_FAILURE_RUNNER,
            why=(
                f"Grade what your agent did AFTER you changed "
                f"{written['what_you_change']}, over the same failures. Same "
                "questions, same grader, different answers - which is the only "
                "arrangement in which the difference means anything."
            ),
            arguments=_a_call_that_fits(
                THE_FAILURE_RUNNER,
                {"failures_path": failures, "answers_path": after,
                 "label": "after", **fields},
            ),
            produces=(
                Output("run_id", "integer", "the recording this leg wrote",
                       at="recording.run_id"),
            ),
            needs=("before",),
            cost=_agent_cost(
                THE_FAILURE_RUNNER,
                find_out_by="the same read as the leg before it, over the same set",
                requests_why="grading answers you already have asks your model nothing",
            ),
            # THE FAILURES, and not the after file, and the distinction is the
            # point of the whole build. What this leg is costed from is how
            # many QUESTIONS it grades, and the questions live in the failure
            # set both legs read; `after_answers_path` supplies the replies to
            # those same questions. Declaring the after file here would have
            # been a step costed off a file whose row count is not what the
            # work is proportional to - and `run_the_failures` says the same
            # thing from its own side through `subject=("failures_path",)`, so
            # the two statements are checked against each other rather than
            # believed separately.
            operates_on=subject,
            exit_criterion=ExitCriterion(
                stated="the after recording exists, over the same questions",
                source="tool_result",
                subject="ok",
                comparator="is_true",
            ),
        ),
        Step(
            id="compare",
            tool=THE_RESULT_READER,
            why=(
                "Compare the two recordings PAIRWISE - over the cases both "
                "graded, keyed by the question rather than by row position - "
                "with McNemar's exact test. When these failures cannot tell "
                "the two apart it says NO EVIDENCE, which is the answer that "
                "keeps a change from being kept for no reason."
            ),
            # BOTH RUN IDS COME FROM THE STEPS THAT WROTE THEM, and neither is
            # written down here. A recording's id is decided when the row is
            # inserted, so a plan that named one would be naming a row that
            # does not exist yet - and a plan that named none would leave this
            # step comparing whichever two runs happened to be newest, which is
            # a comparison of two things nobody chose.
            arguments=_a_call_that_fits(
                THE_RESULT_READER,
                {
                    "run_id": Ref("after", "run_id"),
                    "against": Ref("before", "run_id"),
                },
            ),
            produces=(
                Output("verdict", "string",
                       "different, or no_evidence", at="verdict"),
                Output("delta", "number",
                       "the change in rate over the paired cases", at="delta"),
            ),
            needs=("before", "after"),
            cost=_agent_cost(
                THE_RESULT_READER,
                find_out_by="it reads two recordings already in this conversation",
                requests_why="reading back what is already recorded asks your model nothing",
            ),
            # NOTHING, AND THAT IS THE HONEST ANSWER RATHER THAN A GAP. This
            # step opens no file: it reads two rows this conversation's own
            # database already holds, put there by the two legs above. Naming
            # the failure set here would have been a step declaring it operates
            # on a file it will never open, which is the exact shape
            # `_validate_subject` exists to catch - and it is legal to say
            # nothing precisely because this step's cost is derived from no
            # measurement of anything, so there is no number for the
            # declaration to be checked against.
            operates_on=None,
            exit_criterion=ExitCriterion(
                stated=(
                    "the comparison ran and returned a verdict over the cases "
                    "both recordings graded"
                ),
                source="tool_result",
                subject="ok",
                comparator="is_true",
            ),
        ),
        # THE SAME RE-ENTRY EVERY BUILD ENDS WITH, held to the rate rather than
        # to the comparison. The `after` leg re-measures baseline_success_rate
        # over the changed answers, so the tree is walked again on a reading
        # this build produced; whether the new rate is good enough, and which
        # of this ledger's answers the person is on now, is the engine's to
        # decide and never this build's.
        _recheck_step(
            ("compare",),
            "baseline_success_rate",
            why=(
                "Walk the tree again on the rate your changed system actually "
                "scored. A comparison says whether the change moved anything; "
                "what that means for what to do next is the engine's answer."
            ),
        ),
    ]

    return Build(
        id=written["id"],
        for_outcome=situation.outcome,
        title=written["title"],
        because=written["because"],
        steps=tuple(steps),
        # NO EGRESS, and nothing here would want any: both legs grade files
        # already on this machine and the comparison reads two rows out of this
        # conversation's own database. Somebody's agent ran on their side,
        # before this plan could be drawn.
        environment=_sandbox(written["id"], failures, after),
        exit_criterion=ExitCriterion(
            stated=(
                "a paired comparison of the two recordings ran and returned a "
                "verdict. NOT that the verdict is favourable: this build "
                "promises that the question 'did it work' gets an answer which "
                "is not a guess, and a plan held to its own preferred result "
                "would be a plan with a thumb on the scale. NO EVIDENCE is a "
                "successful outcome of this build."
            ),
            source="tool_result",
            subject="verdict",
            comparator="exists",
        ),
        risks=(
            Risk(
                what="the comparison comes back NO EVIDENCE",
                what_we_do=(
                    "that is the build working. It means these failures cannot "
                    "tell the two versions apart, which is a real answer and the "
                    "one that stops a change being kept on a difference the data "
                    "cannot support. What moves it is more real failures written "
                    "down, and the report says how many"
                ),
            ),
            Risk(
                what="the two recordings are not over the same questions",
                what_we_do=(
                    "the cases only one of them graded are excluded from both "
                    "sides and counted out loud, rather than a delta being "
                    "measured across two different subjects"
                ),
            ),
            Risk(
                what="the change made things worse",
                what_we_do=(
                    "the comparison reports regressed cases beside improved "
                    "ones, and a negative delta resolves exactly as readily as "
                    "a positive one. This build has no preferred direction"
                ),
            ),
        ),
    )


#: The instrument `stage_4_format`'s ask node has been waiting for.
THE_FORMAT_METER = "measure_the_format"


def the_format_can_be_measured() -> bool:
    """Is there a tool that can read `schema_compliance` off a file?

    Written as a predicate for `the_paired_proof_is_possible`'s reason: the
    coverage of this outcome is a fact about the registry, and a table that
    said otherwise would be the state four AI outcomes were in for weeks.
    """
    return REGISTRY.get(THE_FORMAT_METER) is not None


def _propose_measure_the_format(situation: Situation) -> Build:
    """Count how many outputs came back in the right shape, then re-enter.

    ## The half this closes, and the half it does not

    `S4_FORMAT_UNMEASURED` asks two things and its own `asks:` sentence puts
    them in order: *"With the grammar on, what fraction of outputs come back in
    the right shape - and could a schema describe that shape at all?"*

    The first is a count over rows on a disk and this build takes it. The
    second, `schema_expressible`, is a judgement about the person's own
    requirements, is declared `source: derive` with no entry in the ledger's
    `derived:` block, and admits MEASURED only - so nothing derives it, no
    instrument can read it, and the person cannot state it either. **That is a
    defect in a fact's declaration and no proposer can fix it.** It is written
    down in `docs/PHASES.md`; this build does not pretend to close it and says
    so in its own risks.

    A build that closed half of an outcome used to be the argument for building
    none of it. That argument is wrong here and the ledger says why: a null in
    EITHER fact made every remaining node in the stage false, so the stage ran
    off the end. Measuring one of the two is what lets the other be the only
    thing missing, which is a sentence a person can act on.

    ## Why both paths are inputs

    `measure_the_format` will not infer a schema, and this will not guess a
    file. A schema derived from the outputs being graded scores 100% by
    construction and means nothing; a compliance figure for a file nobody
    named is a number about somebody else's system.
    """
    outputs = situation.require_path("outputs_path")
    schema = situation.require_path("schema_path")

    steps: list[Step] = [
        _attach(
            "attach",
            outputs,
            role="the outputs whose shape is being counted",
            why=(
                "Record which file this is about, so the fraction below is "
                "attached to a named file rather than to a description of one."
            ),
        ),
        Step(
            id="count",
            tool=THE_FORMAT_METER,
            why=(
                "Count what fraction of these outputs satisfy your schema. "
                "Every row counts in the denominator - a row that is not JSON "
                "at all is a row where the format did not come back right, and "
                "a fraction computed over the rows that parsed would rise as "
                "your system got worse."
            ),
            arguments=_a_call_that_fits(
                THE_FORMAT_METER,
                {"path": outputs, "schema_path": schema},
                must_carry=("path", "schema_path"),
            ),
            produces=(
                Output(
                    "schema_compliance",
                    "number",
                    "the fraction that satisfied the schema",
                    at="schema_compliance",
                ),
            ),
            needs=("attach",),
            cost=_local_cost(
                THE_FORMAT_METER,
                find_out_by=(
                    "it reads two files on this machine and calls nothing; one "
                    "run over this file and the time is known for it"
                ),
            ),
            operates_on=Subject.of_path(outputs),
            exit_criterion=ExitCriterion(
                stated="the outputs were checked and a fraction came back",
                source="tool_result",
                subject="ok",
                comparator="is_true",
            ),
        ),
        _recheck_step(
            ("count",),
            "schema_compliance",
            why=(
                "Walk the tree again on the fraction that was actually "
                "measured. Whether the shape is solved, and what to do if it is "
                "not, is the engine's answer and never this build's."
            ),
        ),
    ]

    return Build(
        id="measure_the_format",
        for_outcome=situation.outcome,
        title="Count how many outputs came back in the right shape",
        because=(
            "The decoder is on and nothing has said what it achieved. Every "
            "node left in this stage reads schema_compliance, so a null there "
            "is not a missing detail - it is the stage running off the end at "
            "somebody who has already done the work."
        ),
        steps=tuple(steps),
        # NO EGRESS. Two files on this machine, a checker written in this
        # repository, and no model in the loop at any point.
        environment=_sandbox("measure_the_format", outputs, schema),
        exit_criterion=ExitCriterion(
            stated=(
                "schema_compliance is recorded as measured when the tree is "
                "walked again. NOT that the fraction is high: this build "
                "promises the number is known, and what a low one means is the "
                "engine's to say - S4_CONSTRAINT_NOT_HOLDING is a real answer "
                "and it is reached by measuring, not by hoping."
            ),
            source="diagnosis",
            subject="fact_origins.schema_compliance",
            comparator="is_measured",
        ),
        risks=(
            Risk(
                what="the schema uses keywords this harness does not implement",
                what_we_do=(
                    "the step refuses and names them, rather than skipping them "
                    "and reporting a fraction for a schema whose hardest half "
                    "was never checked. Nothing is recorded on that path"
                ),
            ),
            Risk(
                what=(
                    "the stage wants a second fact, schema_expressible, and this "
                    "build does not produce it"
                ),
                what_we_do=(
                    "says so here rather than after the run. That fact is "
                    "declared source: derive with nothing deriving it and admits "
                    "MEASURED only, so no tool can read it and you cannot state "
                    "it - a defect in its declaration, recorded in "
                    "docs/PHASES.md, which no build can close"
                ),
            ),
            Risk(
                what="the outputs are your system's and this harness never ran it",
                what_we_do=(
                    "grades the file you exported and never calls anything. If "
                    "the file is stale, the fraction is about the version that "
                    "wrote it, which is why the attach step names it"
                ),
            ),
        ),
    )


_PROPOSERS_THE_FORMAT_METER_BRINGS: dict[str, Callable[[Situation], Build]] = {
    "ACTION__MEASURE_THE_FORMAT": _propose_measure_the_format,
}


_COVERAGE_THE_FORMAT_METER_BRINGS: dict[str, str] = {
    "ACTION__MEASURE_THE_FORMAT": (
        "attach_context, then measure_the_format, then run_diagnosis. It counts "
        "what fraction of the outputs your system produced satisfy the schema "
        "you name - two files on this machine, no model called, nothing sent "
        "anywhere. Both are yours and neither is guessed: a schema inferred "
        "from the outputs being graded scores 100% by construction. Every row "
        "is in the denominator, including the ones that are not JSON at all, "
        "because those are rows where the format did not come back right. It "
        "closes ONE of the two facts this stage asks for and says so: "
        "schema_expressible is a judgement about your own requirements, "
        "declared source: derive with nothing deriving it, and no build can "
        "reach it. Measuring one is what makes the other the only thing "
        "missing."
    ),
}


_PROPOSERS_THE_PAIRED_PROOF_BRINGS: dict[str, Callable[[Situation], Build]] = {
    outcome: _propose_prove_the_fix for outcome in _THE_FIXES_WORTH_PROVING
}


_PROPOSERS_THE_AGENT_INSTRUMENTS_BRING: dict[str, Callable[[Situation], Build]] = {
    "BUILD__AGENT_WITH_TOOLS": _propose_the_tool_layer_loop,
    "BUILD__TOOLS_FOR_AN_EXISTING_LOOP": _propose_tools_for_an_existing_loop,
    "BUILD__MULTI_AGENT": _propose_multi_agent,
}


#: THE FOUR THAT WERE WRITTEN AND NEVER WIRED, gated by the tools each one
#: actually names rather than by all four instruments together.
#:
#: `_PROPOSERS_THE_AGENT_INSTRUMENTS_BRING` above requires the whole set,
#: because a `BUILD__` on this ledger reads traces AND definitions AND re-runs
#: AND bounds. These three do not: the failure runner alone answers the two
#: outcomes it measures the facts for, the trace reader alone answers the one
#: about traces, and the bucketer needs exactly two of the four and says so in
#: `the_agent_bucketer_is_registered`. Gating each on what it names is the same
#: rule the retrieval and tabular benches follow, and it is the reason those
#: three predicates were written.
_PROPOSERS_THE_FAILURE_RUNNER_BRINGS: dict[str, Callable[[Situation], Build]] = {
    outcome: _propose_run_the_failures for outcome in _THE_FAILURE_RUNNER_OUTCOMES
}

_PROPOSERS_THE_TRACE_READER_BRINGS: dict[str, Callable[[Situation], Build]] = {
    "BLOCKED__NO_TRACES": _propose_read_the_traces,
}

_PROPOSERS_THE_AGENT_BUCKETER_BRINGS: dict[str, Callable[[Situation], Build]] = {
    "ACTION__CLASSIFY_THE_FAILURES": _propose_classify_the_agent_failures,
}


#: Both outcomes take the SAME proposer, because the build is the same four
#: steps and only the question at the end differs - which is what
#: `_CANDIDATE_OUTCOMES` holds. Two entries pointing at one function is the
#: shape `NO_TRAIN__BETTER_PROMPT` / `NO_TRAIN__FEW_SHOT` already use.
_PROPOSERS_THE_CANDIDATE_SCORER_BRINGS: dict[str, Callable[[Situation], Build]] = {
    outcome: _propose_score_a_candidate for outcome in _CANDIDATE_OUTCOMES
}


def _what_the_benches_bring() -> dict[str, Callable[[Situation], Build]]:
    """The proposers whose tools are registered in this process, right now."""
    live: dict[str, Callable[[Situation], Build]] = {}
    if the_retrieval_bench_is_registered():
        live.update(_PROPOSERS_THE_RETRIEVAL_BENCH_BRINGS)
    if the_chunking_sweep_is_registered():
        live.update(_PROPOSERS_THE_CHUNKING_SWEEP_BRINGS)
    if the_training_bench_is_registered():
        live.update(_PROPOSERS_THE_TRAINING_BENCH_BRINGS)
    if the_tabular_bench_is_registered():
        live.update(_PROPOSERS_THE_TABULAR_BENCH_BRINGS)
    if the_agent_instruments_are_registered():
        live.update(_PROPOSERS_THE_AGENT_INSTRUMENTS_BRING)
    if the_failure_runner_is_registered():
        live.update(_PROPOSERS_THE_FAILURE_RUNNER_BRINGS)
    if the_trace_reader_is_registered():
        live.update(_PROPOSERS_THE_TRACE_READER_BRINGS)
    if the_agent_bucketer_is_registered():
        live.update(_PROPOSERS_THE_AGENT_BUCKETER_BRINGS)
    if the_paired_proof_is_possible():
        live.update(_PROPOSERS_THE_PAIRED_PROOF_BRINGS)
    if the_format_can_be_measured():
        live.update(_PROPOSERS_THE_FORMAT_METER_BRINGS)
    if the_candidate_scorer_is_registered():
        live.update(_PROPOSERS_THE_CANDIDATE_SCORER_BRINGS)
    return live


PROPOSERS: Mapping[str, Callable[[Situation], Build]] = _WhatTheRegistryDecides(
    _PROPOSERS_THAT_ALWAYS_EXIST,
    extra=_what_the_benches_bring,
)

#: WHY AN OUTCOME IS NOT COVERED, in a structure a test reads rather than a
#: comment a reader trusts. The instruction for this build says to say plainly
#: which outcomes were not covered and why, and a list that lives in prose is a
#: list that goes stale the first time somebody adds a proposer.
#:
#: `tests/test_the_proposal_is_executable.py` asserts that COVERAGE and
#: NOT_COVERED between them account for EVERY outcome the engine declares, so an
#: outcome added to `docs/diagnosis_engine.yaml` cannot arrive with no statement
#: about whether this product can act on it.

#: THE REASON THAT USED TO BE HERE IS GONE BECAUSE IT WENT FALSE.
#:
#: It read: *"the prompt bench. It needs a stored prompt to change and an eval
#: runner to score it before and after, and neither ships: PRODUCT_SPEC 6.5 has
#: the two cheap halves as 'run_eval called twice' and there is no run_eval."*
#: There is a `run_eval` now; `read_eval_results` pairs two runs with McNemar;
#: and `app/tools/prompts.py` went further than the sentence assumed, making a
#: prompt a VERSION with a parent and a champion to beat, so the before and
#: after is one `try_prompt` call rather than two eval runs this file would have
#: had to pair itself. The two cheap halves - `NO_TRAIN__BETTER_PROMPT` and
#: `NO_TRAIN__FEW_SHOT`, which PRODUCT_SPEC 6.5 marks v1 for exactly this reason
#: - moved to `COVERAGE` and are planned by `_propose_try_a_prompt`.
#:
#: The five that stay uncovered were never blocked on the eval runner, and
#: saying they were is what made one sentence do work it could not do. Each now
#: carries its own, because they fail for three different reasons: one needs a
#: dependency that does not ship, two need a backend that does not exist, and
#: two are blocked on a FACT WITH NO DOOR - declared in a way that admits only
#: MEASURED, with nothing in this harness measuring it. That last shape is worth
#: naming clearly: the engine asks the person a question they are not permitted
#: to answer, and it is a hole in the product rather than in this file.

_NEEDS_A_DECODER = (
    "a constrained-decoding backend, which does not ship (PRODUCT_SPEC 6.5 puts "
    "it post-v1 and says why: it brings a dependency, and a dependency gets its "
    "own step). Nothing here can attach a JSON schema or a GBNF grammar to a "
    "call - run_eval and try_prompt send a system prompt and read text back, and "
    "that is the whole of the surface. Planning 'switch structured outputs on' "
    "with no step that switches anything on is advice with a plan's formatting."
)
_A_FACT_WITH_NO_DOOR = (
    "schema_expressible cannot enter the ledger by any route. It is declared "
    "source: derive, which admits MEASURED only - so the person cannot state it "
    "- it has NO ENTRY in the ledger's own `derived:` block, so nothing derives "
    "it, and no registered tool declares measures= for it. The engine asks "
    "whether a schema could express the target shape at all, which is a "
    "judgement about the asker's own requirements, and then will not accept the "
    "answer from the only party who has it. That is a defect in the fact's "
    "DECLARATION and it is upstream of this file: it closes when the ledger "
    "says source: ask, not when a proposer is written. Its twin closed on "
    "2026-08-27 the way this sentence predicted - schema_compliance is measured "
    "by measure_the_format now, and ACTION__MEASURE_THE_FORMAT has a build."
)
_THE_DECODER_IS_YOURS = (
    "a wiring fault in code this harness does not own - is the constraint on the "
    "call you are actually measuring, is the schema the one you think it is, is "
    "something downstream re-serialising the output. There is no step here that "
    "can look at your calling code, and confirming the fix means re-measuring "
    "schema_compliance, which nothing in this harness measures. Both halves are "
    "missing, not one."
)
_NEEDS_AN_OPTIMIZER = (
    "DSPy - GEPA or MIPROv2 - which is a dependency this harness does not ship "
    "and PRODUCT_SPEC 6.5 puts post-v1 for that reason. try_prompt scores a "
    "prompt somebody wrote and keeps the line of descent; neither it nor "
    "run_eval SEARCHES the space of prompts, and a build that called try_prompt "
    "in a loop and named the winner would be claiming the strongest do-not-train "
    "lever there is on the strength of a for-loop over candidates nobody "
    "generated. The proposer half of this is ready the day the optimiser is."
)
#: `_RETRIEVAL_BENCH` IS GONE AND ITS FOUR OUTCOMES WENT FOUR SEPARATE WAYS. It
#: read: *"the retrieval bench, which is post-v1 (PRODUCT_SPEC 6.6). Nothing
#: here indexes documents or scores a retriever on its own, so there is no step
#: to name and no number to end on."* That sentence did work it could not do -
#: exactly as `_EVAL_BENCH`'s did before it. Two of the four are now planned by
#: `_propose_the_retrieval_bench`; the other two were never blocked on the
#: indexer and get their own reasons below, because they fail for two different
#: reasons and neither is "we cannot index documents".
#: `_FIX_THE_RETRIEVER_IS_WORK_NOT_A_MEASUREMENT` IS GONE AND HALF OF IT WAS
#: ALREADY FALSE. It read: *"the four things the engine actually names ... and no
#: tool in this harness does any of them. What the retrieval bench can do is
#: BUILD an index and SCORE one, and this outcome is only reached when a
#: retriever has already been scored below the bar, so the one thing there is a
#: step for has already happened."* The first clause was wrong about ITS OWN
#: FIRST ITEM: chunking strategy is `passage_chars` on `build_retrieval_index`,
#: which the retrieval bench shipped, and varying it is not re-measuring an
#: unchanged retriever - it is changing the retriever and measuring the change.
#: The reason now lives in `_the_reason_the_sweep_is_not_here_yet`, is true only
#: while the sweep tool is absent, names which tool is missing, and keeps the
#: half that stays true whatever registers: three of the four levers need a
#: model this product does not ship, and the two facts that clear the rest of
#: the node's condition are source: ask.
_CONTEXT_STUFFING_IS_A_PROMPT_NOT_AN_INDEX = (
    "putting the whole corpus in the prompt with caching and building nothing - "
    "which is the opposite of what the retrieval bench does, not a smaller "
    "version of it. Nothing here assembles a context, and nothing here measures "
    "or configures a provider's prompt cache, so the two things this outcome is "
    "made of are both absent. Its condition is corpus_tokens <= 50000, and "
    "corpus_tokens is source: inspect with no registered tool measuring it: "
    "counting tokens needs your model's tokenizer, which is the same reason "
    "every token estimate in this file is UNKNOWN. The index this bench builds "
    "is a token COUNT over text, which is not a tokenizer and cannot be made to "
    "answer this."
)
#: `_EVAL_BENCH` IS GONE FOR THE SAME REASON. It read: *"the evaluation bench
#: (Milestone 3). It needs per-row eval results stored and bucketed;
#: measure_baseline returns example failures and nothing keeps them."* The bench
#: shipped, the rows are kept, and `ACTION__CLASSIFY_FAILURES` moved to
#: `COVERAGE`. `ACTION__RE_BUCKET_THE_FAILURES` was never blocked on it and gets
#: its own entry below.
#: SPLIT ON 2026-08-28, because one sentence had been answering for three
#: outcomes whose blockers stopped being the same thing. It read: *"find_models
#: and read_model_config can find a candidate and nothing here can connect it or
#: score it, so a plan would stop one step short of the number that decides the
#: question."* The scorer it asked for now exists, so that sentence is false for
#: two of the three and still true - for a different reason - for the third.
#: This is the shape `_EVAL_BENCH`, `_RETRIEVAL_BENCH` and `_TRAINING` were each
#: caught in: a group reason outliving the group.
#: `_A_SCORER_EXISTS_AND_THE_PLAN_DOES_NOT` IS GONE, and it lasted one commit.
#: It was split out of `_MODEL_AND_COST` when `score_a_candidate_model` shipped,
#: to say the number could now be taken and no plan took it. The plan is written,
#: so both outcomes moved to `COVERAGE` and the sentence went with them - a
#: reason kept beside a covered outcome is how the two tables start disagreeing,
#: and `test_the_proposal_is_executable` refuses an outcome in both.

#: The third one, and it is NOT the sentence above. Scoring an unquantised
#: candidate does not measure the quantised one, and offering it would be the
#: `ACTION__COUNT_THE_ROWS` trap - a build that runs, looks successful, and
#: moves nothing.
#: REWRITTEN 2026-09-09, because the sentence it replaced had gone false in its
#: specifics the way `_DATA_BENCH` did. It read: *"quantisation, which this
#: harness does not do. No bitsandbytes, no GGUF writer, no Q4_K_M in the pinned
#: lockfile... What would change this is a quantising backend - a recipe, not a
#: proposer."* `recipes/hf-quantize` is that backend and it pins
#: bitsandbytes==0.50.2, so the first half is now wrong and this outcome would
#: have kept telling people the harness cannot do a thing it can.
#:
#: WHAT THE BACKEND MEASURED CHANGES WHAT A PROPOSER MAY SAY, which is why one
#: is not written here yet rather than written badly. On `SmolLM2-135M` over 24
#: rows: peak VRAM 0.314 GB -> 0.125 GB, and generation 74.3s -> 120.1s. The
#: memory saving is real and deterministic; **the run got 1.6x SLOWER**, because
#: dequantisation costs more than the matmul it saves at that size. This outcome
#: recommends quantising to cut the cost of serving, so a proposer that drew it
#: without measuring latency would recommend a change that makes the thing it
#: was called about worse - the `ACTION__COUNT_THE_ROWS` trap wearing a number.
_NOTHING_HERE_QUANTISES = (
    "a proposer, and no longer a backend: `recipes/hf-quantize` quantises and "
    "measures both arms in one process, pinning bitsandbytes. Two things still "
    "stop a build being drawn, and BOTH have been narrowed by measurement "
    "rather than restated. THE FORMAT: this outcome names Q4_K_M, and the "
    "quantiser for it is already on this machine - Ollama ships "
    "`llama-quantize.exe`, which offers Q4_K_M as type 15. What is absent is "
    "the step BEFORE it: `llama-quantize` takes a GGUF and nothing here "
    "converts safetensors into one, because `convert_hf_to_gguf.py` lives in "
    "the llama.cpp repository and not in the `gguf` package on PyPI. So the "
    "gap is one vendored converter, which is a dependency decision about "
    "licence and pinning rather than a missing capability. THE COST, AND IT "
    "IS THE REVERSE OF WHAT THIS REASON SAID UNTIL 2026-09-11: the third "
    "within-family size was measured and the earlier sentence - that the "
    "4-bit latency penalty shrinks with model size, so the folklore is "
    "about small models - was an OUTPUT-LENGTH ARTEFACT. Quantisation "
    "changes the weights, so it changes what the model writes and when it "
    "stops, and the two arms do not emit the same amount of text: at 135M "
    "the 4-bit arm emitted 1.45x MORE tokens than fp16 and at 1.7B it "
    "emitted 0.72x - fewer. Per generated token, counted with each model's "
    "own tokeniser, the penalty GROWS: 1.11x at 135M, 1.12x at 360M, 1.76x "
    "at 1.7B, and the 1.7B figure is a LOWER BOUND because any prefill "
    "widens it. Per ROW - what a person actually waits - it is 1.62x, "
    "1.17x, 1.26x, which is not monotone in either direction. Memory is "
    "2.51x / 2.04x / 2.50x, so the 'identical 2.50x' in the earlier "
    "sentence was also wrong. A proposer must therefore state WHICH cost it "
    "means, the PROMPT it measured - a one-line template change moved the "
    "135M per-row ratio from 1.42x to 1.62x, 55% of the whole claimed size "
    "effect - and refuse to extrapolate past its measured sizes. What would "
    "change this is a converter chosen on purpose. THE REPEAT HAS BEEN "
    "DONE: 1.7B re-run from a byte-identical job file returned 1.695x "
    "against the original 1.757x, so the spread is 0.062 and the gap the "
    "conclusion rests on is 10.3x it. Two runs are a SPREAD and not a "
    "variance - no degrees of freedom, and 0.062 is a floor on the noise "
    "rather than a measure of it - and it is ONE size, so 135M and 360M "
    "stay single measurements and the 0.008 between them remains a "
    "distinction this data cannot make. The repeat also settled something "
    "it was not asked: both runs produced BYTE-IDENTICAL answers, 24 of 24 "
    "rows in both arms, because greedy decoding at a fixed seed on fixed "
    "weights is deterministic. So the token counts did not vary at all "
    "(380 fp16, 273 4-bit, twice) and the token-count asymmetry this "
    "correction rests on is an EXACT property of the two models rather "
    "than a noisy measurement. What DID vary was wall clock alone - both "
    "arms 13-16% faster on the repeat while the ratio moved 3.5% - which "
    "is machine state acting on both arms together, and is why the measure "
    "is a ratio taken inside ONE process: an ABSOLUTE latency published "
    "from this rig would have been 13% wrong between two runs of identical "
    "work."
)
#: `_DATA_BENCH` IS GONE AND IT HAD GONE HALF FALSE, in the same way
#: `_EVAL_BENCH` and `_FIX_THE_RETRIEVER` did before it. It read: *"the data
#: bench, which is post-v1 (PRODUCT_SPEC 6.7). The tools that would split,
#: deduplicate, label, convert or join a dataset do not exist yet, and profiling
#: on its own does not move this outcome."* The first two of the five shipped -
#: `carve_eval_set` and `drop_duplicates` in `app/tools/datawork.py`, in the Data
#: group, writing files - and a person who climbed the whole ladder and landed on
#: `BLOCKED__FIX_LABELS_OR_TASK` was told, in the same session in which they had
#: just carved an eval set with it, that this product has no tool that splits a
#: dataset.
#:
#: The half that stays true is the half that matters here and the new sentence
#: says only that: what exists does not move THESE three outcomes, and it says
#: why for each rather than by claiming an absence.
#:
#: Tools that write a dataset, so the sentence is a reading of the roster.
THE_DATASET_WRITE: str = "datasets"


def tools_that_write_a_dataset() -> tuple[str, ...]:
    """Every registered tool that can write a dataset to the user's disk.

    Read off `writes` rather than listed, for `why_the_full_run_is_not_drawn`'s
    reason: a name typed here is a claim about the registry that stops being
    checked the moment it is written. The canary is a test over this roster, so
    a third data tool registering turns the suite red and somebody re-reads the
    sentence below instead of assuming it still holds.
    """
    return tuple(
        sorted(
            spec.name
            for spec in REGISTRY
            if THE_DATASET_WRITE in tuple(getattr(spec, "writes", ()))
        )
    )


#: The three outcomes the data bench would answer for. Kept beside the reason so
#: the two cannot drift.
_PROPOSERS_THE_DATA_BENCH_WOULD_BRING = (
    "BLOCKED__COLLECT_OR_SYNTHESIZE_DATA",
    "BLOCKED__FIX_LABELS_OR_TASK",
    "NO_DEEP__FIND_THE_MISSING_FEATURE",
)


def _THE_DATA_BENCH_NOT_HERE_YET() -> dict[str, str]:
    """Why these three are uncovered, with what DOES exist named first."""
    have = tools_that_write_a_dataset()
    reason = (
        "the data bench, which is post-v1 (PRODUCT_SPEC 6.7). What this harness "
        "can do to a dataset today is "
        + (", ".join(have) if have else "nothing - no registered tool writes one")
        + " - and not one of those moves THIS outcome, which is the honest part "
        "and not a technicality. BLOCKED__COLLECT_OR_SYNTHESIZE_DATA asks for "
        "rows that do not exist. Splitting the rows you have makes two smaller "
        "files rather than more data, and amplifying them makes more ROWS "
        "without making more INFORMATION: synthesize_rows samples the answers "
        "you already wrote, so a file of a thousand sampled rows carries "
        "exactly what its source carried. The ledger's own recipe here is to "
        "synthesize from the real input distribution WITH A TEACHER MODEL and "
        "then verify a tenth of it by hand. As of 2026-09-12 both halves "
        "ship as tools: generate_rows has a connected model write new rows for "
        "a task from your seeds, judge_rows scores them against your rubric "
        "and writes chosen/rejected pairs, and draw_verification_sample and "
        "record_verification are the tenth read by hand; as of 2026-09-18 "
        "generate_tool_rows writes tool-use rows the other way round, running a "
        "chain of this harness's read-only tools first and deriving the question "
        "from what ran. What is NOT written "
        "is the proposer that chains them into one build - generate, judge, "
        "read the tenth, train on what survived, and measure it against an "
        "eval set carved from REAL rows - so until it is, this outcome hands "
        "over the tool names rather than a plan, and a proposer that offered "
        "sampling in its place would be answering a shortage of information "
        "with a shortage of information. BLOCKED__FIX_LABELS_OR_TASK is "
        "reached when a majority-class baseline is within five points of the "
        "model, which is a statement about whether the labels mean anything; "
        "removing duplicate rows does not change what a label says. "
        "NO_DEEP__FIND_THE_MISSING_FEATURE needs a column that is not in the "
        "file yet, and nothing here joins or derives one. Labelling, format "
        "conversion, joins and derived columns are the parts of that bench that "
        "are not written."
    )
    return _reasons(reason, *_PROPOSERS_THE_DATA_BENCH_WOULD_BRING)
#: `_CHEAPER_MODEL` IS GONE AND IT HAD ALWAYS BEEN SEVEN CLAIMS IN ONE SENTENCE.
#: It read: *"fitting a cheaper model - a gradient-boosted tree, TabPFN, SetFit,
#: an encoder - which this harness has no tool to fit. The engine is right that
#: these are the honest answers; today the product hands over a homework
#: assignment."* Half of that was the truest sentence in this file and the shape
#: of it was the one `_EVAL_BENCH`, `_RETRIEVAL_BENCH` and `_TRAINING` were each
#: caught in: ONE reason answering for a whole stage, so the day any one of them
#: became false the product went on saying it about all seven.
#:
#: The seven are separated now and each says what IT needs, because they need
#: five different things. Only one of them is a tree fit.
#: The library TabPFN actually is, so the sentence about it is a reading of this
#: machine rather than something somebody remembered about the environment - the
#: same reason `_THE_DENSE_LIBRARIES` is named where `dense_libraries_missing`
#: can look for it.
_THE_TABPFN_LIBRARY = "tabpfn"


def _tabpfn_is_here() -> bool:
    """Is TabPFN importable on this machine? LOOKED AT, never assumed."""
    try:
        return importlib.util.find_spec(_THE_TABPFN_LIBRARY) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def _tabpfn_is_a_model_not_a_fit() -> str:
    """Why `NO_DEEP__TABPFN` is uncovered, with the import question actually asked."""
    return (
        "TabPFN, which is a specific pretrained transformer you download and run "
        "a forward pass through - not a fitting procedure with a different "
        "hyperparameter on it. "
        + (
            f"`{_THE_TABPFN_LIBRARY}` IS importable on this machine, looked for "
            "with importlib rather than remembered, and no registered tool loads "
            "it - so this is now a tool that nobody has written rather than a "
            "dependency that is missing, and the sentence has changed because "
            "the machine did"
            if _tabpfn_is_here()
            else f"`{_THE_TABPFN_LIBRARY}` is not importable on this machine, "
            "looked for with importlib rather than remembered, and it is a "
            "dependency this product does not ship"
        )
        + ". A gradient-boosted tree is NOT a substitute and planning one here "
        "would be answering a different question: S8_TABULAR_SMALL is the "
        "1,000-to-10,000-row band, which is the band its own evidence says a "
        "tabular foundation model wins in and a tuned ensemble takes hours to "
        "match. Handing that user a tree is handing them the thing the node "
        "exists to route them away from."
    )


_A_SEARCH_IS_NOT_A_FIT = (
    "a fifty-trial hyperparameter search, and the node says so in its own exit "
    "criterion - '50 trials completed and the best GBDT scored on the eval "
    "set'. Nothing in this harness searches a hyperparameter space: a tool that "
    "fits a tree fits the tree it was asked for, and a proposer that called it "
    "fifty times and named the best would be choosing the person's "
    "false-winner rate and then reporting the maximum of fifty noisy estimates "
    "as a result - which is the defect the chunking sweep exists to refuse, "
    "with the family size multiplied by ten. The engine is asking for this "
    "search precisely because it is about to consider a neural net, so a "
    "number this harness got by picking a winner off its own noise is the worst "
    "possible input to that decision."
)
_FORECASTING_IS_NOT_CLASSIFYING = (
    "ETS, ARIMA, Prophet, a GBDT on LAG FEATURES, and a zero-shot foundation "
    "forecaster - four instruments, and the engine says to beat all three "
    "baselines before training anything. A forecast is not a classification: "
    "the rows are ordered, the split has to be in time, and the features the "
    "tree needs (lags, rolling windows, seasonality) do not exist in the file "
    "yet, which makes this the missing-feature problem as well as the "
    "forecasting one. Nothing here builds a lag column, nothing here splits on "
    "time, and a tree fitted on shuffled rows of a time series scores well by "
    "reading the future - the highest number in this whole document and the "
    "most worthless."
)
def _a_small_encoder_is_still_a_model_we_do_not_ship() -> str:
    """Why the two small-encoder outcomes are uncovered, with the imports asked.

    `dense_libraries_missing` is reused rather than re-implemented: SetFit is a
    contrastively fine-tuned SENTENCE TRANSFORMER, so the library it needs is
    the same one the retrieval bench reports absent for its own dense lever, and
    two functions asking the same question is how two answers start.
    """
    absent = dense_libraries_missing()
    return (
        "a sentence encoder, or a text encoder with a classification head - "
        "SetFit is a contrastively fine-tuned sentence transformer and the "
        "encoder answer is DeBERTa-v3 or ModernBERT - and this product ships no "
        "AI and no embedding model. "
        + (
            "Of the libraries that would be needed, " + ", ".join(absent) + " "
            + ("are" if len(absent) > 1 else "is")
            + " not importable on this machine, looked at with importlib rather "
            "than remembered"
            if absent
            else "The libraries that would be needed ARE importable on this "
            "machine, looked at with importlib rather than remembered, and no "
            "registered tool uses any of them - so this is a tool nobody has "
            "written rather than a dependency that is missing"
        )
        + ". It is the same absence the retrieval bench reports for its own "
        "dense lever, asked one stage over. And the tree fit that closed the "
        "tabular default is no help here: a gradient-boosted tree cannot read "
        "text, which is the whole reason these two outcomes are guarded to "
        "`modality in {text, code}` and the tabular ones are not."
    )


def _the_hybrid_needs_the_half_we_do_not_have() -> str:
    """Why `NO_DEEP__HYBRID_EMBED_PLUS_GBDT` is uncovered, naming which half.

    THE SHARPEST OF THE FIVE, because half of it IS built. The node's method is
    *embed the text columns with a small sentence encoder, concatenate to the
    numeric features, fit a GBDT* - three operations, and the third is the one
    outcome on this branch that has a proposer. Saying "we have no tool to fit a
    cheaper model" about this outcome would be false as soon as
    `fit_a_tree_model` registers, which is exactly how `_EVAL_BENCH` and
    `_RETRIEVAL_BENCH` went stale. So it names the two that are missing and
    concedes the one that is not.
    """
    absent = dense_libraries_missing()
    have = (
        f"{THE_TREE_FIT} is registered here and fits the third"
        if the_tabular_bench_is_registered()
        else f"the third would be {THE_TREE_FIT}, which is not registered here "
        "either"
    )
    return (
        "three operations - embed the free-text columns with a small sentence "
        "encoder, concatenate the vectors to the numeric features, fit a GBDT on "
        "the result - and this harness has the third of them and neither of the "
        f"first two. {have}; nothing here embeds text, "
        + (
            "with " + ", ".join(absent) + " not importable on this machine, "
            "looked at with importlib rather than remembered"
            if absent
            else "even though the libraries that could are importable here, "
            "because no registered tool uses one"
        )
        + "; and nothing here joins a vector to a table, which is the same "
        "column-derivation gap NO_DEEP__FIND_THE_MISSING_FEATURE is blocked on. "
        "A plan that fitted a tree on the numeric columns and left the text out "
        "would not be a smaller version of this answer, it would be the answer "
        "S8_TABULAR_WITH_TEXT sits ABOVE the plain-tree node specifically to "
        "stop somebody being given - the free-text column is the reason that "
        "node exists, and dropping it is dropping the point."
    )


def _THE_TABULAR_BENCH_NOT_HERE_YET() -> dict[str, str]:
    """Why `NO_DEEP__GRADIENT_BOOSTED_TREES` is uncovered WHILE it is.

    A function for `_RETRIEVAL_NOT_HERE_YET`'s reason, and it returns nothing at
    all while the fit is registered, so the outcome sits in `COVERAGE` alone and
    exactly one statement about it is ever on the table.
    """
    if the_tabular_bench_is_registered():
        return {}
    return {
        "NO_DEEP__GRADIENT_BOOSTED_TREES": (
            "the proposer for it is written and the instrument is not registered "
            f"here yet: {list(tabular_tools_missing())} of "
            f"{list(THE_TABULAR_TOOLS)} are missing from this registry. This is "
            "the ONE outcome of the classical branch that is a fit rather than a "
            "model to download, a search to run, a column to build or a text "
            "encoder to ship - the engine's own method block for it is "
            "libraries, a tuning line and 'CPU is sufficient' - so it is the one "
            "a tool closes. A step naming a tool nobody registered is a plan "
            "that fails after you approved it, so none is drawn. This is a gap "
            "in the harness rather than in the plan, and it closes when the tool "
            "registers, not when a proposer is written."
        )
    }
_THE_PERSONS = (
    "a question or a judgement that is the person's: what does success mean, what "
    "is your bar, how often do your facts change, is this licence acceptable. "
    "Asking a good question and waiting is also doing the thing, and a build that "
    "automated it would be inventing the user's judgement, which is the same "
    "defect as inventing a number."
)
_OUT_OF_SCOPE = (
    "correct, and somebody else's product. We can measure what a cache or a router "
    "would save; we do not build a serving layer or an agent. PRODUCT_SPEC 6.4 "
    "draws the line here on purpose."
)
#: `_TRAINING` USED TO ANSWER FOR ALL NINE AND HALF OF IT HAS GONE FALSE. It
#: read: *"a training plan, and nothing in this file proposes one. A training
#: build needs a prepared dataset, a chosen base model and a recipe sized
#: against real hardware - three proposers of their own... start_training exists
#: and is approval-gated; that is not the same as being ready to plan."* One
#: proposer, not three, turned out to be what LORA_SFT needed, and it is written
#: - see `_propose_train_the_adapter`. The sentence stayed true for the other
#: eight for a reason the old one did not name, so the new one names it: what
#: this harness can drive is a LoRA supervised fine-tune, because that is the
#: one thing `recipes/` holds a backend for.
#: THE REFUSALS OF THE THIRD LEDGER, AND WHY AN EMPTY BUILD LIST IS CORRECT.
#: `NO_AGENT__A_SCRIPT` made this argument first and it is the same one: a
#: verdict that says "do not build the thing" has nothing to build. What it has
#: is a sentence, and the sentence is what the person came for.
_THE_REFUSAL_IS_THE_ANSWER = (
    "the refusal IS the product here: this ledger exists to say that almost "
    "nobody needs the expensive thing, and this outcome is one of the ways it "
    "says so. There is nothing to build because the answer is not to build. "
    "What is owed is the sentence, and the node carries it - every one of these "
    "names the cheaper thing to do instead and what would tell you it was wrong."
)

#: THE TWO HANDOFFS, AND THE MECHANISM THAT DOES NOT EXIST.
_THE_OTHER_LEDGER_ASKS_THIS = (
    "this is a real question and it is another ledger's. The verdict names the "
    "file that asks it and what that file opens on, which is the whole of what "
    "can honestly be offered today: cross-ledger routing has no mechanism, and "
    "the disjoint-fact rule the domain router depends on means the evidence "
    "would not travel even if a route existed. A build here would be this "
    "product pretending to carry somebody across a gap it has not built - see "
    "known_gaps.cross_ledger_handoff_has_no_mechanism in harness_design.yaml."
)

_TRAINING = (
    "a training backend this harness does not ship. `recipes/` holds two real "
    "trainers - hf-peft-lora, which does a LoRA supervised fine-tune, and "
    "hf-peft-dpo, which does preference optimisation on top of one - and "
    "neither of them is a reinforcement loop, a distillation student, an "
    "embedding or tabular head, continued pretraining, or a from-scratch run. "
    "So a plan for this outcome would name a step that does not exist, which is "
    "the one thing this module refuses to draw. TRAIN__LORA_SFT and TRAIN__DPO "
    "are the exceptions and both are covered.\n\n"
    "THIS SENTENCE HAS BEEN NARROWED ONCE AND THAT IS THE POINT OF IT. It used "
    "to say `recipes/` holds ONE real trainer and that it does a fine-tune 'and "
    "nothing else: NO PREFERENCE OPTIMISATION, no reinforcement loop...'. The "
    "clause about preference optimisation went false the day hf-peft-dpo "
    "shipped, and a shared reason going half false is the shape this file has "
    "now hit three times - the eval bench, the retrieval bench, the training "
    "backends. Each time the fix is the same: narrow the reason to the outcomes "
    "it still answers for, rather than leave the product telling somebody it "
    "cannot do a thing it can."
)


def _reasons(reason: str, *outcomes: str) -> dict[str, str]:
    return {outcome: reason for outcome in outcomes}


_NOT_COVERED_WHATEVER_IS_REGISTERED: dict[str, str] = {
    # THE SECOND LEDGER'S UNCOVERED OUTCOMES, each with its own sentence.
    # BUILD__AGENT_WITH_TOOLS and BUILD__TOOLS_FOR_AN_EXISTING_LOOP are
    # deliberately absent: they are in COVERAGE while the instruments are
    # registered. The NO_AGENT__/NO_TOOLS__ refusals are
    # not gaps - the refusal IS the answer, and the reason column says what
    # would change it. The ACTION__/BLOCKED__ rows are real gaps named as one.
    "ACTION__BOUND_THE_LOOP": (
        "the verdict's own remedy is bound_the_loop over a set of runs, which "
        "exists; a build is owed once a second AI outcome closes and the "
        "storm drives these steps end to end on real traces rather than "
        "fixtures."
    ),
    # ACTION__BUILD_AN_EVAL_HARNESS, ACTION__CLASSIFY_THE_FAILURES and
    # ACTION__MEASURE_THE_BASELINE are deliberately absent as of 2026-08-27:
    # they are in COVERAGE while their instruments are registered.
    #
    # THE REASONS THAT STOOD HERE WERE ANSWERED BY THE PROPOSERS THEMSELVES,
    # which had been written and never registered - each one already argues,
    # in its own docstring, the case its entry here was making against it:
    #
    #   "the scaffolding build (carve the set from raw tickets/logs) does not
    #    yet" -> the build refuses with the path it wanted named, which is the
    #    same two-population argument BLOCKED__NO_TRACES makes explicitly. A
    #    person who has a failure file does not need one carved.
    #   "what is missing is the step that grows the row set when ten is not
    #    met" -> the build refuses on a MEASURED count below the ledger's own
    #    floor, names both numbers and where the floor was read, and does not
    #    spend somebody's system to arrive back here.
    #   "the missing half is driving somebody's agent over the set" -> it does
    #    not drive anything. It grades the answers the person recorded, which
    #    is exactly the recording that entry said the harness waits for.
    #
    # An entry that argues against a build already in the file is worse than
    # no entry: it is the product telling somebody it cannot do the thing it
    # is about to offer.
    "ACTION__SET_A_TARGET_RATE": (
        "a target rate is the person's to state; the build owed here is a "
        "form-grade question in the thread, not a plan this file can draw."
    ),
    # ACTION__SUBSTANTIATE_CLAIMED_FACTS is deliberately absent here: one
    # proposer already covers it for BOTH ledgers - the door names each
    # ledger's own instrument per fact, which is exactly what
    # _propose_substantiate surfaces. A second key would be a duplicate, and
    # covered-and-explained-at-once is the one shape these tables refuse.
    "ACTION__WRITE_DOWN_TEN_FAILURES": (
        "ten real failures come out of the person's ticket export or logs; "
        "the harness can help carve them (Phase E) but cannot author them."
    ),
    "BLOCKED__CANNOT_REPRODUCE": (
        "reproducibility is established by pinning seed/model/inputs and "
        "running twice - their side. Until a recording shows two runs, no "
        "plan here can be honest about measuring anything."
    ),
    "BLOCKED__NOTHING_TO_MEASURE_AGAINST": (
        "there is nothing to grade yet; every instrument here reads records "
        "that presuppose failures written down."
    ),
    # BLOCKED__NO_TRACES is deliberately absent for the same reason, and its
    # old entry - "no recording exists to read" - was true of ONE of this
    # outcome's two populations. `_propose_read_the_traces` splits them on
    # whether a path can be named, refuses without one, and fabricates
    # nothing; the exporter-line half is still nobody's build here and the
    # refusal says so.
    "NO_AGENT__A_SCRIPT": (
        "the refusal IS the product: one API call beats the loop. Nothing to "
        "build; everything to say."
    ),
    "NO_AGENT__A_WORKFLOW": (
        "same answer one rung up - a fixed sequence ends when the sequence "
        "ends, and this harness will not scaffold what a config file already "
        "does."
    ),
    # NO_AGENT__CONSTRAIN_THE_OUTPUT, NO_AGENT__FIX_THE_CONTEXT,
    # NO_AGENT__FIX_THE_TOOL, NO_AGENT__ONE_API_CALL,
    # NO_TOOLS__DESCRIPTION_IS_THE_BUG and NO_TOOLS__PROMPT_IS_THE_BUG are
    # deliberately absent as of 2026-08-27. They are in COVERAGE while a
    # grader and a comparer are both registered.
    #
    # EVERY ONE OF THE SIX REASONS THAT STOOD HERE WAS AN ARGUMENT AGAINST A
    # BUILD THAT APPLIES THE FIX, and `_propose_prove_the_fix` does not apply
    # anything. It measures whether the fix the PERSON applied worked. The
    # distinction is the whole design and every one of these sentences is still
    # true under it:
    #
    #   "which lives in the agent's stack, not in files this harness reads. The
    #    verdict names the fix; applying it is theirs" -> still theirs. The
    #    build refuses without `after_answers_path`, which is the recording of
    #    their agent AFTER they changed it, and it says so in those words.
    #   "the fix is in the tool's own implementation, which this harness will
    #    not edit" -> it does not edit it. It grades the same failures against
    #    what the repaired tool produced.
    #   "a build for it would be a plan to try one API call, which is an
    #    afternoon, not a product" -> and this is not that build. The afternoon
    #    is the person's and has already happened by the time this plan can be
    #    drawn; what ships is the paired comparison that says whether the
    #    afternoon was enough, with NO EVIDENCE when the failures cannot tell.
    #   "the ML prompt bench's subject is a chat completion, not an agent
    #    endpoint, and the adapter decision is still open" -> that decision is
    #    not on this path. Nothing here calls anybody's endpoint; it grades a
    #    recording, so there is no adapter to decide.
    #   "the owed piece is the compare step wired over two recordings" -> that
    #    is migration 12 and `read_agent_results`, and this is it.
    #
    # ONE OF THE SIX NAMED A LIMIT THAT IS STILL REAL and it is kept here
    # rather than lost with its entry: `context` is one of the buckets the
    # trace reader CANNOT decide without message attributes most exporters do
    # not emit. That is a statement about how confidently this ledger reaches
    # NO_AGENT__FIX_THE_CONTEXT, and it is unchanged. It is not an argument
    # against measuring a context change once somebody has made one, which is
    # all this build does.
    "NO_AGENT__ONE_AGENT_FIRST": (
        "build the single agent before the fleet; the ladder clause exists "
        "so this sentence is heard. Nothing to execute."
    ),
    "NO_AGENT__SHIP_IT": (
        "the numbers say the thing works. Shipping is the person's act; the "
        "harness's job was proving it, and it did."
    ),
    "NO_TRAIN__CONSTRAINED_DECODING": _NEEDS_A_DECODER,
    # ACTION__MEASURE_THE_FORMAT is deliberately absent as of 2026-08-27. It is
    # in COVERAGE while `measure_the_format` is registered.
    #
    # `_A_FACT_WITH_NO_DOOR` NAMED ITS OWN REMEDY AND THE REMEDY WAS BUILT:
    # *"it closes when a tool measures schema_compliance, not when a proposer is
    # written."* `app/tools/shapes.py` is that tool. The other half of the
    # sentence is still true and is kept below on ACTION__FIX_THE_DECODER and in
    # `_A_FACT_WITH_NO_DOOR`'s own text, which now describes one fact rather
    # than two.
    "ACTION__FIX_THE_DECODER": _THE_DECODER_IS_YOURS,
    "NO_TRAIN__PROMPT_OPTIMIZER": _NEEDS_AN_OPTIMIZER,
    "NO_TRAIN__CONTEXT_STUFFING": _CONTEXT_STUFFING_IS_A_PROMPT_NOT_AN_INDEX,
    # THE OUTCOME THAT LOOKS COVERED BY THE NEW BENCH AND IS NOT, and it is the
    # sharpest of the three refusals in this file: the machinery that would have
    # to be used to cover it is exactly the machinery that makes it impossible.
    "ACTION__RE_BUCKET_THE_FAILURES": (
        "settled by the offer, not a build - and the route it used to say was "
        "shut is open. This entry read: 'a histogram the person corrected cannot "
        "enter the ledger at all… Every route is shut, in the right direction.' "
        "That was true while `run_eval` was the only instrument for the fact: it "
        "buckets by fixed rules, so re-running it returns the identical "
        "histogram. `rebucket_failures` is the SECOND instrument, added "
        "2026-08-28 - it re-tallies the rows an eval run already graded, using "
        "the person's reading where they gave one, and the count is what it "
        "measures. `evidence.resolves` now names it, so the frontier offers it. "
        "It stays a refusal here because the build would have to carry a "
        "decision the person has not made yet: which rows were mis-bucketed is "
        "the thing they go and find out, and a plan cannot hold it in advance."
    ),
    "NO_TRAIN__QUANTIZE": _NOTHING_HERE_QUANTISES,
    # THE CLASSICAL BRANCH, ONE OUTCOME AT A TIME. `NO_DEEP__GRADIENT_BOOSTED_
    # TREES` is not here: it moved to the conditional half, because it is the
    # one of the seven a registered tool can answer for and a hardcoded entry
    # would be this product saying it cannot do a thing it can.
    "NO_DEEP__TUNE_THE_TREES_FIRST": _A_SEARCH_IS_NOT_A_FIT,
    "NO_DEEP__CLASSICAL_FORECAST": _FORECASTING_IS_NOT_CLASSIFYING,
    **_reasons(
        _THE_PERSONS,
        "BLOCKED__DEFINE_SUCCESS_FIRST",
        "ACTION__SET_A_TARGET_SCORE",
        "ACTION__STATE_KNOWLEDGE_VOLATILITY",
        "ACTION__SPLIT_THE_TASK",
        "BLOCKED__LICENCE",
        "ACTION__FIX_QUALITY_FIRST",
        "NO_TRAIN__RULED_OUT_EARLIER",
        "NO_TRAIN__SHIP_AS_IS",
        "NO_ML__WRITE_CODE",
        "NO_ML__STATISTICS_OR_MORE_DATA",
        "TEACH__FROM_SCRATCH_NANOGPT",
    ),
    **_reasons(_OUT_OF_SCOPE, "NO_TRAIN__CACHE_AND_ROUTE", "NO_TRAIN__AGENT_SCAFFOLD"),
    **_reasons(
        _TRAINING,
        "TRAIN__CONTINUED_PRETRAINING",
        "TRAIN__DISTILLATION",
        # TRAIN__DPO IS DELIBERATELY ABSENT. `recipes/hf-peft-dpo/` ships and
        # `_propose_train_on_preferences` drives it, so this group's sentence
        # stopped being true of it - see the narrowing in `_TRAINING` itself.
        "TRAIN__EMBEDDING_FINETUNE",
        "TRAIN__FROM_SCRATCH",
        "TRAIN__FULL_FINETUNE",
        "TRAIN__RL_GRPO",
        "TRAIN__TABULAR_DEEP",
    ),
    # THE THREE THAT LOOKED COVERABLE AND ARE NOT. Each gets its own entry rather
    # than a group reason, because each was nearly a plausible-looking build -
    # which is the one failure mode this module exists to prevent.
    "NO_TRAIN__OFF_THE_SHELF_MODEL": (
        "reached only for image and audio data (node S8_VISION_AUDIO_OFFTHESHELF). "
        "All three scoring tools here - measure_baseline, run_eval and try_prompt "
        "- send TEXT to a chat provider and grade it by exact match, containment, "
        "or a chat model judging, so not one of them can measure Whisper, SAM or "
        "CLIP on an eval set. The roster has gone from one to three during this "
        "milestone and the conclusion has not moved once, because every addition "
        "was the same KIND of scorer: more ways to send text is not a way to "
        "score audio. What would change this is an adapter that sends audio or "
        "pixels - a tool, not a proposer. The outcome names the catalogue and we "
        "cannot run any of it."
    ),
    "NO_TRAIN__WONT_FIT_THIS_MACHINE": (
        "the refusal IS the answer, and it is the one outcome here that was "
        "measured rather than reasoned: `record_that_this_card_refuses` reached "
        "it by pricing the model against this card and finding no headroom. "
        "There is nothing to build for it because a build is a plan to spend "
        "this machine, and the fact that closed the route says this machine "
        "cannot pay. What it records instead is the margin and the longest "
        "example length that WOULD fit, so the person's next move is a number "
        "to change rather than a door to try - which is a better answer than "
        "any plan, and is why this sits here rather than in COVERAGE. What "
        "would move it is not a proposer: it is a bigger card, a smaller "
        "model, or somebody else's."
    ),
    # ---- THE THIRD LEDGER'S TWENTY --------------------------------------
    #
    # ELEVEN OF THEM ARE THE PRODUCT AND NOT A GAP. `NO_HARNESS__`,
    # `NO_TOOLING__` and `HANDOFF__` are complete answers: the whole thesis of
    # `docs/ledgers/harness_design.yaml` is that almost nobody needs the
    # expensive thing, so a refusal with nothing to build behind it is the file
    # working. The wording follows `NO_AGENT__A_SCRIPT`, which made the same
    # argument first.
    **_reasons(
        _THE_REFUSAL_IS_THE_ANSWER,
        "NO_HARNESS__ONE_CALL",
        "NO_HARNESS__A_SCRIPT",
        "NO_HARNESS__A_PIPELINE_FIRST",
        "NO_HARNESS__ONE_LOOP_FIRST",
        "NO_HARNESS__USE_AN_EXISTING_ONE",
        "NO_HARNESS__NOT_AN_AI_PROBLEM",
        "NO_HARNESS__STRIP_A_COMPONENT",
        "NO_TOOLING__FEWER_TOOLS",
        "NO_TOOLING__REWRITE_THE_DESCRIPTIONS",
        "NO_TOOLING__TYPE_THE_BOUNDARY",
    ),
    **_reasons(
        _THE_OTHER_LEDGER_ASKS_THIS,
        "HANDOFF__DIAGNOSE_THE_EXISTING_AGENT",
        "HANDOFF__THE_KNOWLEDGE_IS_THE_PROBLEM",
    ),
    # AND FIVE THAT NOTHING HERE CAN ANSWER FOR SOMEBODY, each with its own
    # sentence because each is a different kind of nobody-else-knows.
    "BLOCKED__NO_SUCCESS_CRITERION": (
        "there is no definition of success at all, and writing one is the "
        "person's - a checker this harness invented would be this product "
        "deciding what right looks like for somebody else's work, which is the "
        "one judgement no instrument here may make. read_the_success_check "
        "exists and it reads a file that has to be written first. The build "
        "owed is SPEC__WRITE_THE_TASK's, one rung along, and it is covered."
    ),
    "SPEC__SET_THE_BAR": (
        "what good enough is is the person's number and nobody else's. A target "
        "this file picked would decide, silently, whether the bare model already "
        "clears it - which is the entire verdict of this ledger for a large "
        "share of the people who reach it. state_facts records it when they say "
        "it, and there is nothing to run."
    ),
    "SPEC__NAME_THE_COMPONENTS": (
        "nothing can read an intention. components_proposed_n is what the person "
        "INTENDS to build, not what exists, so there is no file to open and no "
        "count to take - which is exactly why the ledger declares it source: ask "
        "while every other fact in that gate is inspect. state_facts records it; "
        "the ablation build is what comes next and it is covered."
    ),
    "SPEC__DRAW_THE_APPROVAL_BOUNDARY": (
        "where a person has to say yes is a policy decision about somebody's "
        "organisation, and a boundary this harness drew would be a safety claim "
        "nobody agreed to. read_the_tool_risks counts what each tool says it can "
        "destroy, which is the half that IS readable and is covered under "
        "SPEC__DECLARE_THE_BLAST_RADIUS; the line through that list is theirs."
    ),
    "SPEC__SUBSTANTIATE_CLAIMED_FACTS": (
        "the remedy is to run whichever instrument reads the fact that was "
        "claimed, and which fact that is depends on the claim rather than on the "
        "outcome - so a single build here would either name one instrument and "
        "be wrong most of the time, or name all six and be a plan to do "
        "everything. The frontier already routes each claimed fact to its own "
        "tool, which is the same answer arriving in a shape that fits."
    ),
    "ACTION__GROW_THE_EVAL_SET": (
        "the work is writing more graded examples, and grading is the person's "
        "judgement. No tool here can grade an example for them, and one that "
        "guessed would be inventing the very thing every later number is measured "
        "against."
    ),
}

def _RETRIEVAL_NOT_HERE_YET() -> dict[str, str]:
    """The reason the two retrieval outcomes are uncovered WHILE they are.

    Written as a function and not a constant because it names which of the three
    tools are actually absent, read off the registry at the moment somebody
    asks. A hardcoded "the retrieval bench does not ship" is the sentence that
    went false twice already in this file - once for the eval runner, once for
    the prompt bench - and each time it was a written claim that this product
    could not do something it could. This one cannot go false: the day
    `app/tools/retrieval.py` registers all three, `the_retrieval_bench_is_
    registered()` turns true, these entries leave `NOT_COVERED` altogether and
    the same outcomes appear in `COVERAGE`, with nothing here edited.
    """
    missing = retrieval_tools_missing()
    reason = (
        "the proposer for it is written and the instrument is not registered "
        f"here yet: {list(missing)} of {list(THE_RETRIEVAL_TOOLS)} are missing "
        "from this registry. `retriever_recall_at_k` is declared source: inspect, "
        "so only a tool may stamp it, and until one does, a build that indexed a "
        "corpus and measured recall would be naming steps that do not exist - a "
        "plan that fails after somebody approved it. This is a gap in the "
        "harness rather than in the plan, and it closes when the tools register, "
        "not when a proposer is written."
    )
    return _reasons(reason, *_PROPOSERS_THE_RETRIEVAL_BENCH_BRINGS)


def _THE_TRAINING_BENCH_NOT_HERE_YET() -> dict[str, str]:
    """Why the two training outcomes are uncovered WHILE they are.

    A function for `_RETRIEVAL_NOT_HERE_YET`'s reason, and the seven tools it
    reports come from four different modules - the hardware reader, the model
    catalogue, the data checker and the sandbox - so a process missing any one
    of them cannot draw either build and must say which. It returns nothing at
    all while they are all registered, so both outcomes sit in `COVERAGE` alone.

    IT ANSWERS FOR `TRAIN__DPO` TOO, AND THAT IS NOT THE `_TRAINING` MISTAKE
    REPEATED. The group reason this file has narrowed three times was a sentence
    about BACKENDS answering for outcomes with different backends; this is a
    reading of ONE ROSTER, and both builds assemble that same roster. When the
    reason is genuinely the same fact, one reading is what keeps the two
    statements from drifting apart.
    """
    if the_training_bench_is_registered():
        return {}
    reason = (
        "the proposer for it is written and the tools it assembles are not "
        f"all registered here: {list(training_tools_missing())} of "
        f"{list(THE_TRAINING_TOOLS)} are missing from this registry. A step "
        "naming a tool nobody registered is a plan that fails after you "
        "approved it, and these are the outcomes where what fails after "
        "approval is hours of somebody's GPU. This is a gap in the harness "
        "rather than in the plan, and it closes when the tools register."
    )
    # TWO OUTCOMES AND ONE ROSTER, WHICH IS WHY THEY ANSWER TOGETHER. The
    # supervised build and the preference build assemble the SAME seven tools -
    # the hardware reader, the model catalogue, the data checker, the sandbox -
    # so a process missing any one of them can draw neither, and two separately
    # worded sentences would eventually disagree about a single fact.
    return _reasons(reason, "TRAIN__LORA_SFT", "TRAIN__DPO")


def _the_benches_that_are_not_here() -> dict[str, str]:
    """Why each uncovered bench outcome is uncovered, WHILE it is.

    Every half answers for itself and every half returns nothing when its tools
    are registered, so exactly one statement about any outcome is ever on the
    table and `COVERAGE` and `NOT_COVERED` cannot both hold it.
    """
    absent: dict[str, str] = {}
    if not the_retrieval_bench_is_registered():
        absent.update(_RETRIEVAL_NOT_HERE_YET())
    absent.update(_the_reason_the_sweep_is_not_here_yet())
    absent.update(_THE_TRAINING_BENCH_NOT_HERE_YET())
    absent.update(_THE_DATA_BENCH_NOT_HERE_YET())
    absent.update(_THE_TABULAR_BENCH_NOT_HERE_YET())
    # THE FOUR CLASSICAL OUTCOMES WHOSE REASON IS A READING OF THIS MACHINE
    # RATHER THAN A SENTENCE. Each asks its own import question every time it is
    # read, so the day somebody installs TabPFN or sentence-transformers the
    # reason says what actually changed - "the library is here and no tool uses
    # it" - instead of going on claiming an absence that has ended. That is the
    # failure `_CHEAPER_MODEL` was carrying for all seven at once.
    absent["NO_DEEP__TABPFN"] = _tabpfn_is_a_model_not_a_fit()
    absent["NO_DEEP__HYBRID_EMBED_PLUS_GBDT"] = (
        _the_hybrid_needs_the_half_we_do_not_have()
    )
    encoders = _a_small_encoder_is_still_a_model_we_do_not_ship()
    absent["NO_LLM__SETFIT"] = encoders
    absent["NO_LLM__ENCODER_FINETUNE"] = encoders
    return absent


NOT_COVERED: Mapping[str, str] = _WhatTheRegistryDecides(
    _NOT_COVERED_WHATEVER_IS_REGISTERED,
    extra=_the_benches_that_are_not_here,
)

#: What IS covered, said the same way, so the two lists can be compared.
_COVERAGE_WHATEVER_IS_REGISTERED: dict[str, str] = {
    "BLOCKED__BUILD_EVAL_SET": (
        "attach_context, then measure_eval_set, then run_diagnosis. Refuses when "
        "THIS FILE is already MEASURED, because counting it again changes nothing "
        "and the next move is more graded examples, which is the person's. A "
        "measured count of a different file is not that, and does not refuse."
    ),
    "ACTION__MEASURE_BASELINE": (
        "measure_eval_set (only when the request count cannot already be derived "
        "from a count OF THIS FILE), then measure_baseline, then run_diagnosis. "
        "The count comes first so the request cost of the scoring step is derived "
        "rather than unknown - and a count of some other file does not count."
    ),
    "ACTION__MAKE_THE_METRIC_PROGRAMMATIC": (
        "preview_dataset_rows on the eval file, then a question - and NOTHING "
        "that scores. run_eval's exact_match and contains would both return a "
        "number here and neither would answer whether the score the person cares "
        "about can be computed without them, which is the trap this outcome's "
        "old reason named. The step shows them their own answers; the judgement "
        "stays theirs."
    ),
    "ACTION__COUNT_THE_ROWS": (
        "profile_dataset, and nothing else - no question. The row count is not a "
        "judgement, and since 2026-08-28 that tool stamps `tabular_rows` from the "
        "same completed scan it has always counted `eval_size_n` with. The exit "
        "criterion reads the LEDGER rather than the tool result, so a scan that "
        "stopped at the row cap fails this build instead of passing it."
    ),
    "ACTION__NAME_THE_MODALITY": (
        "preview_dataset_rows, then profile_dataset, and then a question - because "
        "no tool here measures modality, and the two steps mean the person answers "
        "while looking at their own data instead of from memory."
    ),
    "ACTION__SUBSTANTIATE_CLAIMED_FACTS": (
        "derived rather than written: one step per tool that evidence.resolves() "
        "names for each challenged fact, a question for anything only the person "
        "can answer, then run_diagnosis. Nothing in it knows a fact by name."
    ),
    "ACTION__CLASSIFY_FAILURES": (
        "run_eval, then read_eval_results, then run_diagnosis - with "
        "measure_eval_set first when the request count cannot be derived from a "
        "count OF THIS FILE. run_eval is the first and only tool that measures "
        "failure_histogram, which is what unblocks this: the fact is source: "
        "derive, admits MEASURED alone, and had no instrument until the bench "
        "shipped. The build can move the outcome and is honest that it might "
        "not - fewer than 20 failures leaves the histogram too small to route "
        "on, which is a property of the data, carried as a risk that says what "
        "to do next rather than as a sample size this file assumed."
    ),
    "NO_TRAIN__BETTER_PROMPT": (
        "one try_prompt step, scoring the prompt YOU supply against the version "
        "it has to beat, aimed at the bucket the engine routed on. PRODUCT_SPEC "
        "6.5 marks this v1. Refuses without a prompt: this file will not draft "
        "the candidate, because a proposal whose central argument the harness "
        "invented is an experiment nobody chose, judged by a comparison it also "
        "chose. Ends in a question rather than run_diagnosis, because "
        "prompt_iterations is source: ask and no step here can stamp it."
    ),
    "NO_TRAIN__FEW_SHOT": (
        "the same step with fewshot_from_failures instead of a prompt, and it "
        "needs nothing written by hand: the bench builds the examples out of the "
        "rows the current champion got WRONG and holds exactly those rows out of "
        "the score. The engine's instruction is 'from the eval failures, not "
        "from the successes', which is the half people get backwards and the "
        "bench cannot. Refuses, before spending anything, when the line has no "
        "scored run to take failures from."
    ),
}

#: What the retrieval bench covers, WHILE its three tools are registered. Paired
#: with `_RETRIEVAL_NOT_HERE_YET` through the same registry question, so exactly
#: one of the two statements about these outcomes is ever on the table.
_COVERAGE_THE_RETRIEVAL_BENCH_BRINGS: dict[str, str] = {
    "NO_TRAIN__RAG": (
        "attach_context, then build_retrieval_index over the corpus you name, "
        "then search_the_index when you give a query, then "
        "measure_retriever_recall on your eval set, then run_diagnosis - with "
        "measure_eval_set first when nobody has counted THIS eval file, because "
        "recall is a fraction and the denominator is read rather than assumed. "
        "This is the headline no-train build: the verdict hands over an index "
        "and a number instead of a sentence. THE ENGINE'S EXIT CRITERION HAS TWO "
        "HALVES AND THIS REACHES ONE - recall on the eval set, yes; end-to-end "
        "score against target_score, no, because no tool here puts retrieved "
        "passages in front of the model and grades the answer. The build says so "
        "in its own exit criterion rather than declaring a weaker one. Refuses "
        "when the eval set IS the corpus or sits inside it - indexing the "
        "answers and then asking whether the answers can be found comes back "
        "near perfect whatever the retriever is - when no corpus is named, when "
        "the eval file is not there, when nothing says which column holds the "
        "question, and when the two lanes disagree about what an argument is "
        "called. There is one refusal it CANNOT make and it says so rather than "
        "implying otherwise: 'recall was already measured on this corpus' needs "
        "the ledger to record which corpus a recall figure was measured over, "
        "and what it records is the eval file and the index by name."
    ),
    "ACTION__MEASURE_RETRIEVER_RECALL": (
        "the same steps, held to S3_RECALL_UNMEASURED's own criterion - "
        "'retriever_recall_at_k recorded; 0.8 is the bar S3_BUILD_RAG already "
        "sets' - and honest about whose retriever it is measuring. The person "
        "here already runs one; this scores the index THIS harness builds over "
        "the corpus they name, which is a floor and a comparison rather than a "
        "report card on their system, and every step and the first risk say so. "
        "Without that sentence the number would be a real measurement of one "
        "retriever answering a question about another, which is the defect this "
        "file spent a milestone closing on row counts."
    ),
}

#: What the chunking sweep covers, WHILE `compare_chunkings` is registered.
#: Paired with `_the_reason_the_sweep_is_not_here_yet` through the same registry
#: question, so exactly one of the two statements about this outcome is on the
#: table at any moment.
_COVERAGE_THE_CHUNKING_SWEEP_BRINGS: dict[str, str] = {
    "NO_TRAIN__FIX_RETRIEVAL": (
        "attach_context, then compare_chunkings over the corpus you name, "
        "scoring every passage size on the SAME eval set, paired - with "
        "measure_eval_set first when nobody has counted THIS eval file. ONE OF "
        "THE ENGINE'S FOUR LEVERS AND THE BUILD SAYS SO: passage_chars is an "
        "argument of build_retrieval_index and its own schema calls it a stated "
        "choice rather than a measured optimum, so chunking is real work this "
        "harness can do with you. Hybrid BM25 plus dense and a cross-encoder "
        "reranker need an embedding model this product does not ship; query "
        "rewriting needs the model you connected and the egress conversation "
        "that comes with it. All three are named in the plan rather than "
        "omitted from it. THE NODE DECLARES NO exit_criterion - alone among the "
        "nodes any proposer here answers - so the build says that in as many "
        "words, states what it DERIVED from the node's own condition and what "
        "that derivation is not, and is held to the verdict the sweep produced "
        "rather than to the direction a number moved. IT DOES NOT RECORD A "
        "WINNER: the best of several noisy estimates is optimistic by "
        "construction and optimistic on the rows that chose it, nothing here "
        "can split an eval set to confirm one on rows that did not, so the plan "
        "ends in a question rather than re-stamping retriever_recall_at_k. "
        "Refuses when the recall that routed you here was typed rather than "
        "measured, when it is already at or above the bar, when the eval set is "
        "the corpus or sits inside it, when the corpus holds one document so "
        "every setting scores the same, and - the one that saves the most time "
        "- when the questions your retriever gets wrong number fewer than the "
        "rows McNemar needs to see change, which is arithmetic on two measured "
        "facts and is stated with the row count that would fix it."
    ),
}


#: WHAT THE CARVE ADDS TO AN OUTCOME THAT WAS ALREADY COVERED, and the reason
#: it is here rather than in the base table. `BLOCKED__BUILD_EVAL_SET` has had a
#: proposer since the beginning, so nothing about it moves between COVERAGE and
#: NOT_COVERED - what moves is WHAT that proposer can do, and a sentence in the
#: base table describing a second build whose tool is not registered would be
#: this product saying it covers something it cannot run. Same mechanism as the
#: two benches above, applied to a second build behind one outcome instead of to
#: a first build behind a new one.
_COVERAGE_THE_CARVE_BRINGS: dict[str, str] = {
    "BLOCKED__BUILD_EVAL_SET": (
        "two builds behind one outcome, and which one you get is decided by "
        "reading your file rather than by asking. WITH AN EVAL FILE: "
        "attach_context, then measure_eval_set, then run_diagnosis - unchanged, "
        "and it still refuses when THIS FILE is already MEASURED, because "
        "counting it again changes nothing. WITH A LABELLED DATASET: "
        "carve_eval_set, then attach_context, measure_eval_set and "
        "run_diagnosis - which is the first build in this product that changes "
        "your disk, so it says the directory it will create before you approve "
        "it, that directory must not exist, and your dataset is read and never "
        "written. The carve is offered only where the answers are ALREADY in the "
        "data: you name the column holding them - this file will not pick it, "
        "because which column is the right answer is the definition of correct "
        "for your task - and that column is then read off the file and the "
        "graded rows counted, at proposal time, against G0's own threshold. Fail "
        "any of that and the refusal is the one that was always here: what is "
        "needed is more graded examples, and writing them is yours. Splitting is "
        "mechanical and this harness does it; grading is judgement and it is not "
        "ours to make. It passes no row count, because carve_eval_set reads G0's "
        "threshold itself and a second parser of the same gate row in the same "
        "call is two answers to one question. It runs no second leak check, "
        "because that tool already runs the real one over what it wrote - what "
        "this plan does is be HELD TO it, and a carve that leaks fails its step "
        "and cancels the count. Nothing here stamps anything: the gate opens on "
        "measure_eval_set counting the file, never on the row count the file was "
        "written with."
    ),
}


#: THE FIRST TRAINING VERDICT THIS PRODUCT CAN ACT ON, and the entry says what
#: the build actually does rather than what the outcome is called. That
#: distinction is the whole of this one: a reader who saw `TRAIN__LORA_SFT` in
#: `COVERAGE` and inferred "it fine-tunes for you" would have been told
#: something false by a table whose only job is to be true.
_COVERAGE_THE_TRAINING_BENCH_BRINGS: dict[str, str] = {
    "TRAIN__LORA_SFT": (
        "TWO BUILDS BEHIND ONE OUTCOME, and which one you get is decided by "
        "reading your conversation rather than by asking - the shape "
        "BLOCKED__BUILD_EVAL_SET already has. BOTH START THE SAME WAY: "
        "inspect_hardware when the card has not been read, find_models, "
        "read_model_config, can_this_machine_train, check_split_leakage, "
        "make_sandbox, then run_in_sandbox on the real data in the sandbox's "
        "own pinned environment. WITH A COMPLETED EVAL RUN OVER THIS EVAL FILE "
        "IN THIS CONVERSATION: a score_the_adapter step follows, scoring the "
        "adapter on exactly the rows that run graded, inside the sandbox that "
        "trained it, against the baseline it measured - and the build's exit "
        "criterion becomes THE REAL ONE, the paired delta reaching the smallest "
        "improvement your counted rows could resolve, with the verdict beside "
        "it saying whether they separated at all. It asks for the base model to "
        "be answered again with the adapter switched off, because the "
        "comparison against your baseline crosses two instruments - a chat "
        "endpoint and a greedy continuation - and the one that isolates the "
        "training is the one taken on the same loaded weights. WITHOUT ONE it "
        "STOPS AT THE TRIAL and says so: measure_baseline scores and stamps and "
        "keeps no rows, so a baseline measured that way clears G1 and leaves "
        "nothing to pair against, and the plan names run_eval as the one step "
        "that would unlock the comparison. What that build produces instead is "
        "the number the whole product was missing - what a training step costs "
        "in seconds and peak VRAM on THIS card, measured - plus a YES/NO on the "
        "memory before a byte is downloaded and a leak check on the split the "
        "comparison would use. BOTH refuse to pick the base model or the "
        "example length, refuse when the eval set could not resolve an "
        "improvement even in principle, refuse when the eval set is inside the "
        "training data, and refuse when a sandbox on this machine already holds "
        "this file. Nothing in either stamps any fact a gate reads: "
        "score_the_adapter declares measures=() for the sharpest version of "
        "that reason - an adapter's score filed under baseline_score would be a "
        "real measurement of a different model under the name G1 reads."
    ),
    # ---- THE THIRD LEDGER'S EIGHT BUILDS --------------------------------
    #
    # Every one of them is an instrument from `app/tools/harness.py` plus
    # `run_diagnosis`, and every exit criterion reads the LEDGER rather than the
    # tool. That shape is not thinness: this harness cannot build somebody's
    # harness, and what it can do is take the measurement the verdict is waiting
    # on off files they already have, then let the engine decide again.
    "SPEC__WRITE_THE_TASK": (
        "read_the_success_check on the file the person named, then run_diagnosis. "
        "IT READS AND DOES NOT RUN, which is the settled design of this gate: "
        "executing somebody's checker would mean running their program, and the "
        "`agent` pack's rule is that this harness never executes somebody else's "
        "system. So the gate is denominated in something readable, the same move "
        "that turned cost_per_run_usd into tokens_per_run, and the reply says in "
        "its own field that nothing was executed. The exit criterion is that "
        "success_check_is_a_program is MEASURED in the ledger, not that the tool "
        "returned ok."
    ),
    "SPEC__BUILD_A_STARTER_EVAL": (
        "count_the_task_set on the person's own file, then run_diagnosis. It "
        "counts the rows carrying BOTH the task and the outcome that would be "
        "right, because a row with no expected outcome is not a task yet and "
        "counting it would put something in the denominator that can never be "
        "graded. Rows it had to drop are reported rather than silently left out. "
        "It refuses to guess which column is which - that is a statement about "
        "somebody's file only they can make."
    ),
    "SPEC__MAKE_THE_TASKS_RERUNNABLE": (
        "the same count_the_task_set scan, held to a different fact. "
        "Re-runnable MEANS every task carries the outcome that would be right - "
        "that is what re-running is, sending it again and comparing against "
        "something - so re-runnability is a property of the file rather than a "
        "second question, and one scan settles both. The exit criterion here is "
        "can_rerun_tasks MEASURED where the sibling outcome's is harness_tasks_n."
    ),
    "SPEC__RUN_THE_MODEL_ALONE": (
        "score_a_recorded_run with variant=solo, then run_diagnosis. THE RUN "
        "ITSELF IS NOT IN THIS PLAN and the build says so: this harness will not "
        "drive somebody's system, so sending the tasks to the bare model is "
        "theirs to do between approving and executing. What the build does is "
        "GRADE the recording against their own expected column, which is a file "
        "on disk - and that distinction is the only reason solo_pass_rate can be "
        "source: inspect at all. It refuses without answers_path and says what "
        "to go and produce. The variant is a closed set, because each rung opens "
        "a different row of the ladder gate."
    ),
    "SPEC__ABLATE_THE_HARNESS": (
        "ablate_a_component over every component at once, then run_diagnosis. "
        "This is the build for G3_EVERY_COMPONENT_IS_LOAD_BEARING, which has no "
        "analogue in either shipped ledger. It grades both recorded arms per "
        "component and pairs them ROW BY ROW, then tests the rows that CHANGED "
        "with an exact two-sided McNemar - comparing two aggregate rates would "
        "throw away exactly the information that decides this. NO EVIDENCE is a "
        "real result and the plan says so before you approve it: a component "
        "that did not move the score by more than noise is latency, a failure "
        "mode, and an assumption that will rot. All components in one call, "
        "because the gate asks about every one of them."
    ),
    "SPEC__DECLARE_THE_BLAST_RADIUS": (
        "read_the_tool_risks on the definitions file, then run_diagnosis. It "
        "counts the tools through the same reader the AI ledger uses, so the two "
        "can never disagree about what a tool is, and then makes a second narrow "
        "pass for the annotation keys - MCP's own destructiveHint and "
        "readOnlyHint among them. IT NEVER INFERS RISK FROM A NAME: a tool "
        "called sync that carries destructiveHint is annotated and one called "
        "delete_everything that carries nothing is not. A Python source file "
        "cannot be annotation-counted and the reply says why rather than "
        "returning a silent zero that fails the gate."
    ),
    "SPEC__BOUND_THE_RUN": (
        "bound_the_harness_run on one or more OTLP traces, then run_diagnosis. "
        "It reads the same spans as the AI ledger's bound_the_loop through the "
        "same helpers and files them under this ledger's own fact names, which "
        "the disjointness rule requires. It refuses to total a run where any "
        "inference span carries no usage attributes: a partial sum is a lower "
        "bound and a lower bound is the number that is always smaller than the "
        "bill, so harness_tokens_per_run is not stamped and the gate stays shut, "
        "with the missing spans named."
    ),
    "SPEC__INSTRUMENT_THE_LOOP": (
        "the same bound_the_harness_run read, held to harness_has_traces rather "
        "than to the token total. 'Nothing recorded what happened' and 'there "
        "are traces and they do not settle the cost' are two different sentences "
        "with the same next step, so one instrument answers both and the exit "
        "criterion names whichever fact this verdict is waiting on."
    ),
    **_reasons(
        "one proposer behind four outcomes, and IT DOES NOT BUILD THE HARNESS - "
        "that is the person's system, in their repository, and nothing here will "
        "write it or run it. What it does is take again, off files on disk, every "
        "measurement the verdict was paid with: count_the_task_set on the task "
        "set, read_the_tool_risks on the tool layer when there is one, "
        "bound_the_harness_run on a trace when there is one, then run_diagnosis. "
        "Those numbers go stale the moment a prompt is edited or a model swapped, "
        "and a verdict standing on last month's measurement is a verdict about "
        "last month. It deliberately does NOT re-score the ladder: that needs a "
        "fresh recording only the person can produce, and reusing the old one "
        "would present a stale rate as a current one - the plan carries that in "
        "its risks rather than hiding it. HARNESS__TOOL_LAYER is the one that "
        "arrives from ZERO tools, so the tool step is drawn only when there is a "
        "definitions file to read.",
        "HARNESS__TOOL_LAYER",
        "HARNESS__FIXED_PIPELINE",
        "HARNESS__AGENT_LOOP",
        "HARNESS__AGENT_TEAM",
    ),
    "TRAIN__DPO": (
        "ONE BUILD, and it is the supervised one's shape with four things "
        "changed - each of them a refusal rather than a step. It runs "
        "inspect_hardware when the card has not been read, read_model_config, "
        "can_this_machine_train, check_split_leakage, make_sandbox, then "
        "run_in_sandbox on your real preference pairs in the "
        "hf-peft-dpo recipe's own pinned environment, which is a SEPARATE "
        "environment from hf-peft-lora's. What it produces is what a "
        "preference-optimisation step costs in seconds and peak VRAM on THIS "
        "card, measured, plus a YES/NO on the memory before a byte is "
        "downloaded and a leak check on the split. "
        "IT REQUIRES AN ADAPTER TO CONTINUE FROM: the ledger declares "
        "`DPO: {prerequisite: LORA_SFT}` in two places and the engine reads "
        "neither, so this build is where that gets enforced, and the refusal "
        "quotes the line. IT WILL NOT TAKE A DEMONSTRATIONS FILE - "
        "prompt/chosen/rejected is a different contract from a text or a "
        "prompt with the answer beside it, and pointed at the other recipe's "
        "data both this build and the recipe name hf-peft-lora rather than "
        "reporting a zero. IT READS THE PAIR COUNT OFF THE LEDGER RATHER THAN "
        "OFF THE FILE: count_preference_pairs is the instrument, this checks "
        "that the number on file is a MEASURED count of the file this plan "
        "would train on, and it checks that count against the ledger's own "
        "floor read out of the node's condition rather than typed here. AND IT "
        "STOPS AT THE TRIAL FOR A REASON ABOUT THE ARTIFACT, not about a "
        "missing tool: trl merges the SFT adapter into the base weights before "
        "attaching the new one, so what comes out applies to the merged weights "
        "and score_the_adapter - which is registered - takes a base model and "
        "an adapter. Handed that pair it would score a model nobody trained. "
        "The run saves the merged base beside the adapter and the plan says "
        "they travel together. It refuses the same way the supervised build "
        "does about the model, the example length, an eval set inside the "
        "training data, a machine with no accelerator, and a sandbox that "
        "already holds this file. Nothing in it stamps any fact a gate reads."
    ),
}


#: THE FIRST VERDICT ON THE CLASSICAL BRANCH THIS PRODUCT CAN ACT ON, and the
#: entry says what the build does rather than what the outcome is called - the
#: distinction `_COVERAGE_THE_TRAINING_BENCH_BRINGS` had to make. A reader who
#: saw `NO_DEEP__GRADIENT_BOOSTED_TREES` in `COVERAGE` and inferred "it does the
#: classical branch for you" would have been told something false by a table
#: whose only job is to be true: this is ONE outcome of twelve in that stage,
#: and one fit rather than the tuned search the same node prescribes.
_COVERAGE_THE_TABULAR_BENCH_BRINGS: dict[str, str] = {
    "NO_DEEP__GRADIENT_BOOSTED_TREES": (
        "one fit_a_tree_model step: a gradient-boosted tree fitted on the "
        "dataset you name, predicting the column YOU say holds the answer, "
        "scored on rows held out of the fit against the trivial baseline on "
        "those same rows, with the resolution of those rows printed beside the "
        "difference. One step because it is one piece of work - two steps could "
        "be run against two different splits, and then the comparison is two "
        "facts rather than a difference. NEITHER NODE THAT EMITS THIS OUTCOME "
        "DECLARES AN exit_criterion, so the build says so, derives what it can "
        "from G1_BASELINE_MEASURED's own classical_deep row - 'a "
        "gradient-boosted tree, and TabPFN where the size allows, both fitted "
        "and scored' - attributes it to the gate rather than to the node, and "
        "says what the derivation is NOT. IT IS NOT HELD TO THE TREE WINNING: "
        "the criterion is that the fit ran and reported its resolution, because "
        "a tree that beats a majority class by two points on a few hundred "
        "held-out rows has not beaten it. IT SAYS THE LIBRARY IS NOT THE ONE "
        "THE ENGINE NAMES: LightGBM, XGBoost and CatBoost are the method "
        "block's own list, importlib is asked about each one on this machine, "
        "and the answer goes in the plan. IT SAYS IT IS ONE FIT AND NOT THE "
        "FIFTY-TRIAL SEARCH the same block prescribes - and does not ask you "
        "for hparam_search_trials, because that fact is read by a gate row and "
        "a no-train build soliciting one is a no-train build leaning on a gate. "
        "It refuses when nothing has said which column is the answer, when that "
        "column is not in the file, when the rows CARRYING that column number "
        "fewer than the engine's own tabular floor - which tabular_rows cannot "
        "catch, because a row count is not a label count - and when a measured "
        "trivial baseline already clears your target. It runs no "
        "profile_dataset: that tool stamps eval_size_n, and stamping G0's fact "
        "with a count of the training table is the subject defect this module "
        "spent a milestone removing."
    ),
}


#: What the agent instruments cover, WHILE they are registered. The first
#: entry from the second ledger to reach these tables, which is why the reason
#: names its domain: `asking.py` reads this table to tell a person whether the
#: product can act on their verdict, and an AI-engineering verdict deserves a
#: true sentence there the same as an ML one.
_COVERAGE_THE_AGENT_INSTRUMENTS_BRING: dict[str, str] = {
    "BUILD__AGENT_WITH_TOOLS": (
        "run_the_failures re-grades your recorded failure rows against your "
        "agent's newest answers, joined to its traces; bound_the_loop re-reads "
        "tokens-per-run and termination off those traces; run_diagnosis walks "
        "the tree again on the refreshed sheet. It runs nobody's agent - it "
        "reads the records your agent leaves - so it needs three paths from "
        "you (traces_path, failures_path, and the field names) and refuses "
        "rather than guessing them. It is one leg of a paired comparison, not "
        "both: proving a change moved the rate means recording twice over the "
        "same rows and comparing with McNemar, and the second recording is "
        "yours."
    ),
    "BUILD__TOOLS_FOR_AN_EXISTING_LOOP": (
        "the zero-tools verdict, so the plan leads with read_tool_definitions "
        "- confirming what you wired parses as definitions before anything is "
        "graded against it - then the same re-grade, bound and re-walk as its "
        "sibling. It needs tooldefs_path besides the traces and failures "
        "paths. It does not write your tools for you: wiring them and "
        "exporting a fresh answers file is yours between approving and "
        "running, and if the definitions file still declares nothing the defs "
        "step refuses rather than grading against nothing."
    ),
    "BUILD__MULTI_AGENT": (
        "all fourteen MAST failure modes demand inter-agent traces the product "
        "does not invent: this build re-grades and re-bounds the single-agent "
        "recordings you already have and walks again, because a fleet justified "
        "on a hunch is coordination debt. If the re-measured buckets still point "
        "here, you have the numbers to justify the next build; if not, you just "
        "saved the build that would have failed for the same reason the "
        "diagnosis already named."
    ),
}


#: WHAT THE FAILURE RUNNER COVERS ON ITS OWN, and it is the two outcomes whose
#: facts it is the instrument for. Both sentences are about the same three
#: steps; what differs is which fact the build is held to, which is the thing
#: the person is owed a sentence about.
_COVERAGE_THE_FAILURE_RUNNER_BRINGS: dict[str, str] = {
    "ACTION__BUILD_AN_EVAL_HARNESS": (
        "attaching the failure set makes it runnable, which is what this "
        "outcome is waiting to learn: run_the_failures re-runs the cases "
        "against the answers your agent produced for them and stamps "
        "can_rerun_failures, then run_diagnosis walks the tree again. It does "
        "not drive your agent - it grades the recording you made - so it needs "
        "the failure file and the answers file from you and refuses rather "
        "than guessing them. If you have failures in a ticket export and not "
        "in a file yet, that carving step is still yours; the build refuses "
        "with the path it wanted named."
    ),
    "ACTION__MEASURE_THE_BASELINE": (
        "the same three steps held to a different fact: the rate. "
        "run_the_failures reports how many of your recorded cases still fail "
        "and stamps failure_rate_measured and baseline_success_rate with the "
        "resolution beside them, because 14 of 50 is a baseline and 'it fails "
        "sometimes' is not. It refuses a re-run that would return the same "
        "number - a rate already measured on THIS file is not moved by "
        "measuring it again - and it refuses when nothing in the live registry "
        "declares it measures the fact this outcome is blocked on, checked by "
        "call rather than argued in prose."
    ),
}

#: The trace reader alone, for the population of this outcome that HAS a
#: recording and has never pointed the harness at it.
_COVERAGE_THE_TRACE_READER_BRINGS: dict[str, str] = {
    "BLOCKED__NO_TRACES": (
        "this outcome has two populations and only one of them is ours. "
        "has_traces defaults to false, which is this ledger reading 'nobody "
        "has done this yet' honestly - so the node fires both for somebody "
        "whose system records nothing AND for somebody with a directory of "
        "trace files who has never pointed the harness at it. For the first, "
        "the work is an exporter line inside code this harness does not own "
        "and there is no step for it. For the second it is one read, and "
        "which population you are in is decided by whether you can name a "
        "file. So the build refuses without a path, in words that name what "
        "is missing, and never claims the read will succeed: a directory "
        "holding no agent trace produces no reading and the outcome does not "
        "move, carried as a risk that says what to do next."
    ),
}

#: The bucketer needs two of the four instruments and the ledger's own floor.
_COVERAGE_THE_AGENT_BUCKETER_BRINGS: dict[str, str] = {
    "ACTION__CLASSIFY_THE_FAILURES": (
        "the hinge of this ledger: until the failures are bucketed every "
        "remedy is a guess, and this ledger routes its buckets to different "
        "stages, several of which end in a refusal rather than a build. The "
        "plan names two instruments rather than one and that is a measurement "
        "rather than a preference - of the five buckets this ledger routes on, "
        "tool_choice needs to know which tool should have been called, "
        "tool_execution needs a status on the tool span, and context needs "
        "what the model was actually given, all three of which are in the "
        "trace or nowhere. And it refuses when the floor cannot be reached: a "
        "failure set already COUNTED as smaller than the ledger's minimum "
        "cannot produce a histogram that opens this outcome however well it "
        "runs, so the plan stops and names both numbers and where the floor "
        "was read, rather than spending your system to arrive back here."
    ),
}


#: THE WORKBENCH. One sentence per outcome, because these six are the answers
#: this ledger reaches most often and a person reading "we can help with that"
#: is owed the shape of the help rather than a category.
#:
#: Each says the same three things in its own terms: what you change, that the
#: change is yours to make, and that the answer may be NO EVIDENCE. The last of
#: those is the one worth writing six times - a coverage sentence promising an
#: improvement would be this table making the claim the build is careful not to.
_COVERAGE_THE_CANDIDATE_SCORER_BRINGS: dict[str, str] = {
    outcome: (
        "find_models, read_model_config, make_sandbox, score_a_candidate_model - "
        "and then a QUESTION. The scoring step needs no connection: it answers "
        "your graded rows in a sandbox, the way the control arm of an adapter "
        "run always has. The question is permanent, not a shortfall - the fact "
        "this turns on is `source: ask`, which no instrument may ever measure. "
        "What the build buys is that you answer it having seen the number."
    )
    for outcome in _CANDIDATE_OUTCOMES
}


_COVERAGE_THE_PAIRED_PROOF_BRINGS: dict[str, str] = {
    outcome: (
        f"attach_context, then run_the_failures twice - once over the answers "
        f"your agent gave BEFORE you changed {written['what_you_change']} and "
        "once over the answers it gives after - then read_agent_results "
        "compares the two PAIRWISE, over the cases both graded, keyed by the "
        "question rather than by row position, with McNemar's exact test. "
        "Nothing here changes your system and nothing here runs your agent: "
        "the 'after' recording is a file you produce, and the build refuses by "
        "name on after_answers_path rather than inventing one. What it "
        "promises is an ANSWER and never a favourable one - when these "
        "failures cannot tell the two apart it says NO EVIDENCE and tells you "
        "to write down more failures, which is the answer that keeps a change "
        "from being kept for no reason."
    )
    for outcome, written in _THE_FIXES_WORTH_PROVING.items()
}


def _what_the_benches_cover() -> dict[str, str]:
    """What each bench covers, WHILE its tools are registered."""
    live: dict[str, str] = {}
    if the_retrieval_bench_is_registered():
        live.update(_COVERAGE_THE_RETRIEVAL_BENCH_BRINGS)
    if the_chunking_sweep_is_registered():
        live.update(_COVERAGE_THE_CHUNKING_SWEEP_BRINGS)
    if the_carve_is_registered():
        live.update(_COVERAGE_THE_CARVE_BRINGS)
    if the_training_bench_is_registered():
        live.update(_COVERAGE_THE_TRAINING_BENCH_BRINGS)
    if the_tabular_bench_is_registered():
        live.update(_COVERAGE_THE_TABULAR_BENCH_BRINGS)
    if the_agent_instruments_are_registered():
        live.update(_COVERAGE_THE_AGENT_INSTRUMENTS_BRING)
    if the_failure_runner_is_registered():
        live.update(_COVERAGE_THE_FAILURE_RUNNER_BRINGS)
    if the_trace_reader_is_registered():
        live.update(_COVERAGE_THE_TRACE_READER_BRINGS)
    if the_agent_bucketer_is_registered():
        live.update(_COVERAGE_THE_AGENT_BUCKETER_BRINGS)
    if the_paired_proof_is_possible():
        live.update(_COVERAGE_THE_PAIRED_PROOF_BRINGS)
    if the_candidate_scorer_is_registered():
        live.update(_COVERAGE_THE_CANDIDATE_SCORER_BRINGS)
    if the_format_can_be_measured():
        live.update(_COVERAGE_THE_FORMAT_METER_BRINGS)
    return live


COVERAGE: Mapping[str, str] = _WhatTheRegistryDecides(
    _COVERAGE_WHATEVER_IS_REGISTERED,
    extra=_what_the_benches_cover,
)


def the_ledger_these_tables_are_keyed_to() -> diagnosis.Spec:
    """The one ledger `PROPOSERS`, `COVERAGE` and `NOT_COVERED` are written for.

    AN UNCONDITIONAL READ OF THE FIRST LEDGER, DELIBERATE AND NAMED. Everywhere
    else in this file the ledger arrives from the situation, because the answer
    depends on which conversation is being planned for. Here it does not: the
    three tables below hold 12 + 12 + 43 entries and every key is an outcome id
    of `docs/diagnosis_engine.yaml`. That is a fact about this module, not about
    a thread, and the honest way to hold it is a function that says so - so the
    refusal above can tell "we measured that we cannot build this" apart from
    "these tables were never asked this domain's question".

    It goes away with `contract.builds`, where an outcome declares the
    capabilities a build for it needs and coverage is computed over the live
    registry. That is `ledger_format: 4` and step 5 of
    `docs/CAPABILITY_BLOCKS.md`'s migration path.
    """
    return diagnosis.default_spec()


def propose(situation: Situation) -> Build:
    """Dispatch. Raises `NotEnoughToPropose` when there is no honest build.

    TWO DIFFERENT REFUSALS WEAR ONE SHAPE HERE, AND ONLY ONE OF THEM IS A GAP IN
    THE PRODUCT. `PROPOSERS`, `COVERAGE` and `NOT_COVERED` are keyed by the
    first ledger's 55 outcome ids and by nothing else, so an outcome from a
    second ledger misses all three - and the fallback sentence, *"Nothing in
    this harness can run what that outcome asks for"*, is then a statement about
    coverage made about a domain the tables were never asked about. That is the
    same defect `evidence.resolves` was carrying: a true sentence with a false
    reason.

    The structural fix is `contract.builds` - the outcome declaring which
    capabilities a build for it needs, with coverage computed over the live
    registry rather than tabulated here - and it is `ledger_format: 4` and step
    5 of `docs/CAPABILITY_BLOCKS.md`'s migration path. What this pass owes is
    that the two states are told apart and said out loud.
    """
    proposer = PROPOSERS.get(situation.outcome)
    if proposer is None:
        first = the_ledger_these_tables_are_keyed_to()
        mine = situation.outcome in situation.spec.declared_outcomes()
        elsewhere = mine and situation.outcome not in first.declared_outcomes()
        raise NotEnoughToPropose(
            f"There is no proposer for {situation.outcome!r} today. "
            + NOT_COVERED.get(
                situation.outcome,
                (
                    f"{situation.outcome!r} is an outcome of "
                    f"{situation.spec.as_written}, and every proposer in this "
                    f"file is keyed to an outcome of {first.as_written} - so "
                    "this is not a measured gap in what the harness can build, "
                    "it is a tool layer that has never been asked this domain's "
                    "question. Nothing is planned, and a plan drawn from another "
                    "domain's table would be worse than none."
                )
                if elsewhere
                else "Nothing in this harness can run what that outcome asks "
                "for, and a plan that cannot execute is worse than no plan.",
            ),
            needs=(situation.outcome,),
        )
    return proposer(situation)


# ---------------------------------------------------------------------------
# The tool.


@tool(
    "propose_build",
    description=(
        "Turn the standing diagnosis into a typed build plan: each step names "
        "a real tool, its cost, what could go wrong, and how we will know it "
        "worked. You supply facts; the engine chooses what is proposed. If "
        "nothing here can honestly run what the diagnosis asked for, it says "
        "what is missing rather than drawing a plan that would fail."
    ),
    schema={
        "type": "object",
        "properties": {
            "facts": {
                "type": "object",
                "description": (
                    "Fact name to value, exactly as run_diagnosis takes them. "
                    "Only names declared in the harness fact ledger are accepted, "
                    "and what you supply is worth what you are worth."
                ),
                "additionalProperties": True,
            },
            "eval_path": {
                "type": "string",
                "description": "The evaluation file or folder on this machine, if there is one.",
            },
            "input_field": {
                "type": "string",
                "description": "The column holding the input to send to the model.",
            },
            "expected_field": {
                "type": "string",
                "description": "The column holding the answer that would be right.",
            },
            "answer_field": {
                "type": "string",
                "description": (
                    "The column holding what the agent actually answered. Only "
                    "the agent builds read this - a recording of somebody's own "
                    "run has three columns, not two, and grading it needs all "
                    "three."
                ),
            },
            "prompt": {
                "type": "string",
                "description": (
                    "A system prompt YOU want to try, when the diagnosis says to "
                    "improve the prompt. The build then measures it against your "
                    "current baseline on the same rows and reports whether the "
                    "difference is real. This harness will not write one for "
                    "you: without it the plan is refused rather than invented."
                ),
            },
            "prompt_line": {
                "type": "string",
                "description": (
                    "The name of the prompt line the attempt is filed on. Every "
                    "comparison is against that line's current champion, so this "
                    "decides what the attempt is measured against. Leave it out "
                    "and the eval file's name is used, and the plan says so."
                ),
            },
            "dataset_path": {
                "type": "string",
                "description": "The dataset file or folder the question is about.",
            },
            "corpus_path": {
                "type": "string",
                "description": (
                    "The documents a retriever is supposed to fetch from - a "
                    "folder or a file on this machine. Needed when the diagnosis "
                    "says to build retrieval or to measure a retriever; without "
                    "it that plan is refused rather than pointed at whichever "
                    "path was lying around. It must not be the eval file: "
                    "indexing the answers and then asking whether the answers "
                    "can be found measures nothing."
                ),
            },
            "traces_path": {
                "type": "string",
                "description": (
                    "The OTLP trace file or folder somebody's agent left on "
                    "this machine. Needed when the diagnosis says to build for "
                    "an agent with tools: the re-run joins failure rows to "
                    "runs by trace id and the loop bounds are re-read from it."
                ),
            },
            "failures_path": {
                "type": "string",
                "description": (
                    "The JSONL of recorded failure cases - input, expected, "
                    "answer, and optionally which trace_id each belongs to. "
                    "Needed when the diagnosis says to build for an agent with "
                    "tools; grading runs against THIS file, so a stale export "
                    "measures an agent that no longer exists."
                ),
            },
            "tooldefs_path": {
                "type": "string",
                "description": (
                    "Optional. A tool-definitions file (MCP tools/list result, "
                    "an OpenAI or Anthropic tools array, or decorated Python) "
                    "to re-read beside the failure re-run, so a description "
                    "change and its effect land in the same conversation."
                ),
            },
            "query": {
                "type": "string",
                "description": (
                    "A question you would actually ask your retriever. The "
                    "retrieval build adds a step that shows you the passages it "
                    "returns, before it shows you a number about them. Leave it "
                    "out and that step is left out, and the plan says so - this "
                    "harness will not make up a question for you to be "
                    "impressed by."
                ),
            },
            "chunk_settings": {
                "type": "array",
                "items": {"type": "integer"},
                "description": (
                    "The passage sizes, in characters, a chunking sweep should "
                    "compare - at least two of them. Needed when the diagnosis "
                    "says to fix the retriever, and refused rather than filled "
                    "in: the number of settings is the family size every "
                    "p-value is corrected against, so choosing them chooses how "
                    "likely a false winner is, and that is not a choice this "
                    "harness makes on your behalf."
                ),
            },
            "top_k": {
                "type": "integer",
                "description": (
                    "How many passages count as 'the top few' when recall is "
                    "measured. Leave it out and the measuring tool's own default "
                    "is used and the plan says which case applies; this file "
                    "does not pick a k, because k is half of what "
                    "retriever_recall_at_k means."
                ),
            },
            "base_model": {
                "type": "string",
                "description": (
                    "The Hugging Face repo to fine-tune, e.g. 'Qwen/Qwen3-4B'. "
                    "Needed when the diagnosis says to train, and refused rather "
                    "than filled in: find_models ranks what fits THIS card and "
                    "shows why, which is help, but which model to train carries "
                    "a licence and a commitment about what your product is, and "
                    "that is not a choice this harness makes for you."
                ),
            },
            "max_seq_len": {
                "type": "integer",
                "description": (
                    "How many tokens long a training example is. Needed when the "
                    "diagnosis says to train, and refused rather than defaulted: "
                    "it sets the activation and logits terms, which are most of "
                    "the memory budget, and every tool that could default it "
                    "defaults to a different number - so a fit answer computed "
                    "at one length beside a run executed at another would be two "
                    "facts about two different runs."
                ),
            },
            "text_field": {
                "type": "string",
                "description": (
                    "Which field of the training JSONL holds the text to train "
                    "on. Leave it out and the recipe's own default is used - it "
                    "also accepts a prompt/completion pair, and refuses the file "
                    "loudly if it has neither - and the plan says which case "
                    "applies."
                ),
            },
            "checker_path": {
                "type": "string",
                "description": (
                    "The file that decides whether an answer was right. It is "
                    "READ and never run."
                ),
            },
            "tasks_path": {
                "type": "string",
                "description": (
                    "The task set a harness would be measured on - the tasks and "
                    "the outcomes that would be right."
                ),
            },
            "ablation_arms": {
                "type": "array",
                "description": (
                    "One entry per component: its name, the answers from a run "
                    "WITH it, and the answers from a run WITHOUT it. All of them "
                    "at once, because the gate asks about every component."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "component": {"type": "string"},
                        "with_answers": {"type": "string"},
                        "without_answers": {"type": "string"},
                    },
                    "required": ["component", "with_answers", "without_answers"],
                },
            },
            "adapter_dir": {
                "type": "string",
                "description": (
                    "The directory holding the adapter a supervised fine-tune "
                    "already produced. Preference optimisation continues from "
                    "it rather than starting beside it - the ledger declares "
                    "LORA_SFT as this method's prerequisite - so the "
                    "preference build refuses without it and says why."
                ),
            },
            "trial_steps": {
                "type": "integer",
                "description": (
                    "How many optimizer steps the trial run should take. Leave "
                    "it out and the recipe's own default stands and its log "
                    "reports how many it ran. It is what bounds how much of your "
                    "machine the measurement costs, which is your call."
                ),
            },
            "sample": {
                "type": "integer",
                "description": (
                    f"How many rows a scoring step would use. Default "
                    f"{DEFAULT_BASELINE_SAMPLE}, maximum {MAX_BASELINE_SAMPLE}. It "
                    "bounds the work and it is what the request count is derived "
                    "from."
                ),
            },
        },
        "required": ["facts"],
    },
    reads=("facts", "filesystem", "datasets"),
    writes=(),
    provides=("ledger.build.propose",),
    label="Propose a build",
    group="Decide",
    verb="propose a build for what the diagnosis said to do",
    order=22,
)
def propose_build(
    facts: dict[str, Any] | None = None,
    eval_path: str = "",
    input_field: str = "",
    expected_field: str = "",
    answer_field: str = "",
    dataset_path: str = "",
    sample: int = DEFAULT_BASELINE_SAMPLE,
    prompt: str = "",
    prompt_line: str = "",
    corpus_path: str = "",
    traces_path: str = "",
    failures_path: str = "",
    tooldefs_path: str = "",
    query: str = "",
    top_k: int = 0,
    chunk_settings: list[Any] | None = None,
    base_model: str = "",
    max_seq_len: int = 0,
    text_field: str = "",
    checker_path: str = "",
    tasks_path: str = "",
    ablation_arms: list[Any] | None = None,
    adapter_dir: str = "",
    trial_steps: int = 0,
    *,
    instrument: Instrument,
    ledger: diagnosis.Spec,
) -> dict[str, Any]:
    """Facts in, a validated plan out - or a refusal that names what is missing.

    `measures=()`, like `run_diagnosis`, and for the same reason: this tool
    produces a plan, not a measurement, and the facts arriving in its arguments
    are worth exactly what their speaker is worth. It writes nothing either. A
    proposal is not an approval and calling this forty times accumulates no
    authority.
    """
    supplied = dict(facts or {})
    try:
        sheet, trail = evidence.assemble_facts(
            instrument.thread_id, supplied, instrument.actor, ledger=ledger
        )
        # THE LEDGER THIS THREAD IS RUNNING. `diagnose(sheet)` fell back to the
        # first ledger, so the verdict this file plans against and the verdict
        # `run_diagnosis` showed the person could have come from two different
        # documents on the same thread.
        result = diagnosis.diagnose(sheet, ledger)
    except diagnosis.FactError as error:
        return {
            "ok": False,
            "error": "rejected_fact",
            "detail": str(error),
            "help": (
                "Fact names come from the harness fact ledger. Send only facts you "
                "have actually established."
            ),
        }
    except diagnosis.EngineError as error:
        return {"ok": False, "error": "engine_error", "detail": str(error)}
    except evidence.MeasurementError as error:
        return {"ok": False, "error": "measurement_refused", "detail": str(error)}
    except Exception as error:  # noqa: BLE001 - the product boundary, as run_diagnosis
        return {
            "ok": False,
            "error": "engine_failed",
            "detail": f"{type(error).__name__}: {error}",
            "help": (
                "The diagnosis could not be computed from these facts, so nothing "
                "could be proposed. Nothing was run and nothing was recorded."
            ),
        }

    try:
        bound = max(1, min(int(sample), MAX_BASELINE_SAMPLE))
    except (TypeError, ValueError):
        bound = DEFAULT_BASELINE_SAMPLE

    situation = Situation(
        outcome=result.outcome,
        result=result,
        values={row["fact"]: row["value"] for row in trail},
        origins={row["fact"]: row["origin"] for row in trail},
        hows={row["fact"]: row.get("how") or "" for row in trail},
        recorded_at=when_each_row_was_written(instrument.thread_id, trail),
        eval_path=str(eval_path or ""),
        input_field=str(input_field or ""),
        expected_field=str(expected_field or ""),
        # WAS MISSING, AND THE OMISSION WAS SILENT. `Situation.answer_field`
        # existed and three agent proposers read it; this constructor never set
        # it, so every plan drawn through the TOOL boundary carried
        # `answer_field=""` while the same plan built by hand in a test carried
        # the real column. `BUILD__AGENT_WITH_TOOLS` then failed at run time -
        # "12 row(s) of 12 carry no 'input', no 'expected' or no ''" - and the
        # empty quotes at the end of that message are this bug printing itself.
        answer_field=str(answer_field or ""),
        dataset_path=str(dataset_path or ""),
        sample=bound,
        prompt=str(prompt or ""),
        prompt_line=str(prompt_line or ""),
        corpus_path=str(corpus_path or ""),
        traces_path=str(traces_path or ""),
        failures_path=str(failures_path or ""),
        tooldefs_path=str(tooldefs_path or ""),
        query=str(query or ""),
        # A NEGATIVE OR UNREADABLE k IS "YOU DID NOT SAY", not an error and not
        # a k this file chose. Zero and below both mean the tool's own default
        # stands, which is the only honest answer to a number nobody supplied.
        top_k=max(0, _an_integer(top_k)),
        # UNREADABLE OR NON-POSITIVE SIZES ARE DROPPED RATHER THAN CORRECTED,
        # and what is left is what the plan is drawn against. A sweep of one
        # usable setting is not a comparison, and the proposer refuses on the
        # count it can actually use rather than on the length of what arrived -
        # so a caller who sent `[400, "big", 0]` reads "give me two sizes", not a
        # plan built over one.
        chunk_settings=tuple(
            size for size in (_an_integer(one) for one in (chunk_settings or ())) if size > 0
        ),
        base_model=str(base_model or ""),
        # AN UNREADABLE OR NON-POSITIVE LENGTH IS "YOU DID NOT SAY", not a
        # length this file chose. `_propose_train_the_adapter` refuses on it and
        # says why, which is a sentence somebody can act on - where a silent
        # correction to a default would price one run and execute another.
        max_seq_len=max(0, _an_integer(max_seq_len)),
        text_field=str(text_field or ""),
        # THE FIELD THE TOOL BOUNDARY MUST CARRY OR THE BUILD CANNOT BE DRAWN
        # AT ALL. `answer_field` above is the record of what happens when a
        # Situation field exists and this constructor does not set it: the plan
        # built by hand in a test carries the real value, the plan built through
        # the tool carries "", and the difference only shows up at run time. The
        # preference build refuses without this one, so the failure would be
        # loud rather than silent - and a build that is unreachable through the
        # only door a model can open is still an uncovered outcome wearing a
        # COVERAGE entry.
        # THE THIRD LEDGER'S THREE, SET HERE OR THE BUILDS ARE UNREACHABLE. The
        # `answer_field` bug is the record of what happens otherwise: a field
        # that exists on the Situation and is never set by this constructor
        # makes every plan drawn through the TOOL boundary carry the empty
        # default, while the same plan built by hand in a test carries the real
        # value - and a build unreachable through the only door a model can open
        # is an uncovered outcome wearing a COVERAGE entry.
        checker_path=str(checker_path or ""),
        tasks_path=str(tasks_path or ""),
        ablation_arms=tuple(ablation_arms or ()),
        adapter_dir=str(adapter_dir or ""),
        trial_steps=max(0, _an_integer(trial_steps)),
        # NOT AN ARGUMENT, AND THAT IS THE POINT. The thread comes from the
        # INSTRUMENT, so a caller cannot point the training build at somebody
        # else's eval runs by naming a number. It is the same wall the outcome
        # argument does not get: what a proposal is allowed to stand on is what
        # this conversation actually holds.
        thread_id=_an_integer(instrument.thread_id),
    )

    try:
        plan = propose(situation)
    except NotEnoughToPropose as gap:
        return {
            "ok": False,
            "error": "no_honest_build",
            "outcome": result.outcome,
            "verdict": result.verdict,
            "say": result.say,
            "detail": gap.detail,
            "needs": list(gap.needs),
            "help": (
                "This is a refusal to draw a plan that could not run, not a "
                "failure. Supply what is named above and ask again, or do the part "
                "that is yours."
            ),
            "covered_outcomes": sorted(PROPOSERS),
        }
    except BuildInvalid as error:
        # A proposer built something that does not validate. That is a defect in
        # this file rather than in the request, and it must surface as one: an
        # unvalidated build must never reach a user as a plan.
        return {
            "ok": False,
            "error": "proposer_defect",
            "outcome": result.outcome,
            "detail": str(error),
            "help": (
                "The harness assembled a plan that failed its own validation, so "
                "it was not shown. Nothing was run. This is a bug in "
                "app/tools/propose.py."
            ),
        }
    except build.CostError as error:
        return {
            "ok": False,
            "error": "proposer_defect",
            "outcome": result.outcome,
            "detail": str(error),
            "help": (
                "A cost in this plan could not say where it came from, so the plan "
                "was refused rather than shown with a number nobody can vouch for."
            ),
        }

    return {
        "ok": True,
        "outcome": result.outcome,
        "verdict": result.verdict,
        "say": result.say,
        "build": plan.as_dict(),
        "approve": plan.fingerprint(),
        "your_facts_were_recorded_as": instrument.supplied_origin,
        "decided_by": "app/diagnosis.py",
        "planned_by": "app/tools/propose.py",
        "note": (
            "Nothing here has run. This is a proposal: approving it is what starts "
            "it, and what runs is what is in this object."
        ),
    }


__all__ = [
    "COVERAGE",
    "NOT_COVERED",
    "NotEnoughToPropose",
    "PROPOSERS",
    "Situation",
    "THE_ADAPTER_SCORER",
    "THE_ADAPTER_SCORING_TOOLS",
    "THE_CARVING_TOOLS",
    "THE_TABULAR_TOOLS",
    "THE_TREE_FIT",
    "THE_LORA_RECIPE",
    "THE_RETRIEVAL_TOOLS",
    "THE_SCORING_KINDS",
    "THE_SCORING_READ",
    "THE_TRAINING_TOOLS",
    "WhatTheDataAlreadyAnswers",
    "a_measurement_of",
    "carving_tools_missing",
    "engine_exit_criterion",
    "engine_method",
    "engine_node_says",
    "engine_requires_in_diagnosis",
    "g0_minimum",
    "gate_facts",
    "gate_rows_reading",
    "libraries_the_engine_names",
    "nodes_that_emit",
    "propose",
    "propose_build",
    "recall_bar",
    "recipes_that_could_score_an_adapter",
    "retrieval_tools_missing",
    "rows_a_tree_needs",
    "sandboxes_already_holding",
    "subject_of_a_recorded_measurement",
    "tabular_tools_missing",
    "the_answers_are_already_in_the_data",
    "the_adapter_scorer_is_registered",
    "the_baseline_run_to_beat",
    "the_carve_is_registered",
    "the_classical_baseline",
    "the_criterion_the_engine_owes",
    "the_recipe_on_this_machine",
    "the_retrieval_bench_is_registered",
    "the_tabular_bench_is_registered",
    "the_training_bench_is_registered",
    "tree_libraries_missing",
    "tools_that_score_a_model",
    "tools_that_score_an_adapter",
    "training_tools_missing",
    "when_each_row_was_written",
    "where_the_carve_would_land",
    "why_the_full_run_is_not_drawn",
]
