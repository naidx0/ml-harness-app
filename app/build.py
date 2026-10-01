"""A build: the typed plan the person approves and the executor runs.

`docs/THE_PROPOSAL_LOOP.md` is the specification. Three of its properties are
decisions rather than details, and everything in this file exists to make one of
them structural instead of aspirational:

1. **The proposal is the object the executor consumes.** Not prose a second
   system re-derives into steps. If the plan a person approves and the thing
   that runs are different objects, the plan is marketing and it will drift from
   the truth inside a week.
2. **The diagram is the plan rendered.** A `Step` is a node. `Step.id` is the
   node id, in the picture and in the executor's state, so a step that fails
   during the storm changes state in the picture because it *is* that node.
3. **Approval is a contract.** What was approved is what runs; any deviation
   stops and asks. `Step.contract_fingerprint()` and `Build.deviations_from()`
   are what let the executor prove that mechanically rather than promise it.

## What a build carries, and why each part is not optional

Per the spec, in its words and in this order: **steps**, each naming the tool
that runs it with its inputs and outputs; **dependencies**, so the executor
knows what can run at once and what must wait; **the environment** it needs;
**what it will cost** in the user's model tokens, wall-clock time and disk;
**what could go wrong** and what the harness does about it; and **the exit
criterion** - how we will know it worked, stated before it runs.

Two additions this module makes, both of which are the spec's own arguments
followed one step further:

- **Questions.** Twelve of the engine's outcomes end in something only the
  person can answer (`docs/PRODUCT_SPEC.md` section 6.4). A build that had
  nowhere to put those would either drop them or fake them as steps. So a
  `Build` carries `questions` beside `steps`: the harness runs the steps, the
  person answers the questions, and *asking a good question and waiting is also
  doing the thing*. A `Question` may not name a fact any registered tool
  declares it `measures` - a question the harness could answer by looking is a
  step it failed to take, and `validate` refuses one.
- **`model_requests` as a fourth cost dimension.** The spec names three. We can
  derive requests exactly from a measured row count with no tokenizer and no
  fudge factor; we cannot derive tokens from anything without one. A proposal
  that says "412 requests to your model, tokens unknown" is worth more than one
  that multiplies characters by a number somebody remembered.

## THE HARD RULE HERE: A COST CANNOT BE CONSTRUCTED WITHOUT ITS ORIGIN

`docs/THE_PROPOSAL_LOOP.md` names the trap before we walk into it. A proposal
contains estimates, estimates are numbers, and this product's first invariant is
that we never invent one. *"This will take about forty minutes and cost roughly
fourteen cents"* is exactly the sentence that makes a proposal feel trustworthy
and exactly the number we would be making up.

So the type is built the way `app/tools/evidence.py` builds a measurement: not
as a rule a reviewer enforces, but as a thing that cannot be spelled.

## AND THE SECOND HARD RULE: A READING CARRIES ITS SUBJECT

The rule above stops an invented number. It does not stop a REAL one measured
off the wrong thing, and that is the worse defect, because it answers the
question the rule above asks. A proposal for a 777-row eval file promised
*"model_requests: 120 requests (inferred)"* with the derivation *"counted 120
rows in ...\\Temp\\tmph_4tt4go\\eval.jsonl; capped at 500"*. Every clause of
that is true. The count happened, the cap is the tool's own, the arithmetic is
right, and the answer is wrong by a factor of four, because the file counted is
not the file the step runs on. An invented number fails the question *where did
this come from?*. This one answers it correctly.

So `Reading` carries a `Subject` - what was measured - and there is no door
that mints a reading without one. `Step.operates_on` says what the step runs
on, and `Build.validate` refuses a step whose cost descends from a measurement
of anything else, naming the subject it expected and the subject it found.

**What identifies a subject, and why this identity and not another.** A subject
is a `kind` and a `key`. For the only kind that matters today the key is the
path, canonicalised (`resolve()` then `normcase`), and that is a deliberate
choice over the two obvious alternatives:

- **A path alone is weak** - a file at the same path can change under you - so a
  subject also carries a `witness`: the size and modification time read at the
  moment it was established. Same key and a different witness is the same name
  and a different file, and it is refused as such.
- **A content hash is the honest identity and it is not affordable.** Costing a
  step on a 50 GB dataset must not read 50 GB; a proposal that took longer than
  the run it was pricing would not be used, and a check nobody runs is not a
  check. The witness is what a `stat()` can say for free.
- **A subject recovered from a record gets the one check a record can support:
  the date.** Nothing stored what the file looked like when it was counted, so
  it carries no witness - but the ledger stored WHEN, and a file modified after
  a count of it was recorded is not the file that was counted. That is one
  `stat()` and a string comparison, the same cost on 50 GB as on 50 rows, and it
  is `Subject.measured_at` against `Subject.modified_at`.

**WHAT THIS DOES NOT CATCH, said out loud rather than discovered later.**

1. A file rewritten with the same size and modification time - `touch -r`, a
   sync tool that preserves timestamps, or a filesystem whose mtime resolution
   is coarser than the edit. The witness is a cheap check, not a hash, and the
   date beside it is defeated by exactly the same trick.

   **THAT LAST CASE IS NOT EXOTIC AND IT IS NOT RARE, MEASURED 2026-09-05 ON
   THIS MACHINE.** Two different files of the same length, written back to
   back, produced the SAME witness in **157 of 200 trials** - not a filesystem
   somewhere with a coarse clock, but the one this repository is checked out
   on. `st_mtime_ns` reports nanoseconds and the filesystem does not update it
   that finely, so the resolution that matters is the write's, not the field's.
   A witness therefore says "this is the file I counted" with the strength of
   "same length, and changed no later than about now" - which is worth having,
   and is not identity. `test_the_witness_says_what_it_cannot_see` holds this
   number so it stays a measurement rather than a memory.
2. **A subject recovered from the fact ledger still carries no witness**, which
   is the common case. `app/tools/evidence.py` has no column for what a
   measurement was of, so the subject of a stored fact is read back out of the
   derivation sentence the measuring tool wrote, and nothing recorded the file's
   size or contents at the time. WHAT IS CHECKED NOW IS THE DATE: the ledger
   records when each row was written, `app/tools/propose.py` reads it back
   beside the derivation, and a file whose modification time is later than that
   is refused - so "500 requests, counted before you replaced the file" is
   closed. Four things stay open and are worth naming: a replacement that
   preserves the modification time (item 1); a modification inside the same
   SECOND as the record, because the ledger's timestamps are second-resolution
   and a comparison is only as fine as its coarser side; a caller who cannot
   locate the ledger row and therefore supplies no date at all, for whom the
   check does not run - absent is absent, never fresh; and the fact that a date
   dates the RECORD rather than the READING, so a tool that counted for an hour
   and then wrote its row leaves an hour in which a change reads as older than
   the count. Closing those needs a column beside the row saying what the file
   looked like, which is `app/tools/evidence.py`'s to add and not this file's to
   invent.
3. Two spellings of one file that `resolve()` does not fold together - a UNC
   path against a drive letter, an 8.3 short name, a bind mount - read as two
   subjects and are REFUSED. So does a byte-identical copy at another path. Both
   are false refusals, and a false refusal here costs a re-count and can never
   cost a wrong number, which is the direction this is arranged to fail in.
4. A folder's `stat()` says nothing about the files inside it, so a directory
   subject's witness does not move when its contents do. Only the key is worth
   anything for a folder.
5. Nothing here checks that a count was of the same COLUMNS or the same SPLIT as
   the step will read. `eval_size_n` measured on the right file with the wrong
   split is still outside this.

## AND THE THIRD HARD RULE: THE SUBJECT IS THE ARGUMENT THE TOOL READS

The rule above binds a number to a subject. It says nothing about whether the
subject is what the step will actually open, and the first version of that check
asked the wrong question: it scanned EVERY string argument for one that matched
the declared subject. So a step could point `eval_path` at a 777-row file, hide
the 120-row file's path in `expected_field` - which `measure_baseline` reads as
a column name - declare `operates_on` as the 120-row file, and cost itself from
a genuine count of it. Three checks, three passes, "120 requests" shown for a
step that will make 500. **That is the second rule's own defect reproduced
through the fix written for it**, and the shape of the mistake is the same one
this project keeps re-learning: an existence test where an identity test was
needed.

A tool KNOWS which of its arguments it opens. `subject_of_a_call` asks it - see
`declared_subject_arguments` for the declaration this file wants from
`app/tools/registry.py`, spelled out there so the two halves cannot drift - and
where a tool has not said, it refuses to pick: it answers only when every
argument that could name a path names the SAME one, because a call with nothing
to guess between needs no guess. Ambiguity is not resolved here in either
direction; it is reported, and `app/tools/propose.py` turns it into an UNKNOWN
cost with an offer to go and measure.

**No constructor in this module accepts a bare magnitude as the value of an
estimate.** There is no `Estimate(value=40)`, no `Cost(minutes=40)`, and no
free-form `Estimate.inferred(value=..., derivation=...)` either - because a
free-form inference constructor is a magnitude slot with a comment beside it.
The three arms of the provenance vocabulary each have their own door and each
door demands its evidence:

- **MEASURED** - `Estimate.measured(dimension, reading=...)`. The caller
  supplies *no number at all*; the value comes out of a `Reading`, and a
  `Reading` is minted only by a constructor that actually read something (a file
  it stats, a fact the evidence ledger already stamped MEASURED). You cannot
  hand `measured()` a figure, so you cannot hand it a figure you remembered.
- **INFERRED** - arithmetic on estimates that already exist:
  `.capped_at()`, `.scaled_by()`, `.counted_as()`, `Estimate.summed()`, and the
  one zero door, `Estimate.none()`. Every one records its derivation, and the
  derivation is shown because the spec says an inference must show it.
- **UNKNOWN** - `Estimate.unknown(dimension, why=..., find_out_by=...)`. Carries
  no value, and `find_out_by` is required: *"I do not know how long this takes,
  let me run it on 1% and find out"* is worth more than a guess, and it is the
  only version consistent with everything else in this product.

`capped_at(limit)` and `scaled_by(factor)` do take a bare number, and that is
deliberate rather than an oversight. It is the distinction WALL 6 in
`app/tools/registry.py` already drew for tool arguments: **a bound bounds the
work, it does not answer the question.** `measure_baseline` scoring at most
`sample` rows is a rule the caller states, not a measurement they invented, and
the resulting estimate is INFERRED with that rule written into its derivation.

**An inference is never more certain than its inputs.** `Estimate.summed()` of
a measured cost and an unknown one is UNKNOWN, not the measured part - a total
that quietly drops the term nobody could price is the most dangerous number a
proposal could carry, because it reads as complete.

**The honest limit of all of this**, said out loud the way `evidence.py` says
its own: a caller who reaches into this module for `_MINTING` and sets it
defeats every door above, and nothing in Python can stop that. What these walls
stop is the accidental and the plausible - `Cost(minutes=40)` written in good
faith by somebody in a hurry - which is how this invariant actually gets broken.

## Executable by construction, or it is not a plan

A `Build` validates itself at construction and refuses to exist otherwise. That
is the property the rest of this run stands on: **a build that cannot be
validated must never be shown to a user as a plan.** `validate()` checks, and
names the step it is talking about in every message:

- every step's `tool` is a registered tool;
- every argument is in that tool's schema, every required argument is present,
  every declared type and enum is satisfied;
- every `Ref` names a step this step declares in `needs`, and that step really
  produces an output of that name and type - which is what "its outputs are what
  the next step needs" means mechanically;
- the dependency graph is acyclic, and a cycle is rejected loudly at
  construction naming the cycle, not discovered at execution;
- every cost slot on every step carries an `Estimate`, which cannot exist
  without a provenance, and a step costed from a measurement says what it
  operates on and the measurement is OF that;
- every step and the build itself declares an exit criterion;
- no step names a tool that only means something when a person runs it (see
  `PERSON_ONLY_TOOLS`);
- a step whose tool may leave this machine runs only in an environment that
  declared egress.

## What the executor, the diagram and the adversary each use

- **The executor (the storm)** reads `Build.waves()` for what may run at once,
  `Step.bind()` to resolve a step's `Ref` arguments from what earlier steps
  produced, `Step.contract_fingerprint()` to prove the step it is about to run
  is the step that was approved, and `ExitCriterion.met()` to decide whether a
  finished step actually worked.
- **The diagram** reads `Build.as_dict()`. Its `steps` are the nodes, keyed by
  the same `Step.id` the executor reports state under, and its `edges` are the
  dependencies. `STEP_STATES` is the canonical state vocabulary, taken from
  `docs/DESIGN_SYSTEM.md` section 2.5 rather than invented here, so the picture
  and the run cannot disagree about what a step is doing.
- **The adversary** should start at `Estimate`, `Build.validate` and
  `Build.deviations_from`, which are the three places where a lie would be
  worth the most.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path, PurePath
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from app import diagnosis


# ---------------------------------------------------------------------------
# Vocabulary.


class BuildInvalid(ValueError):
    """This plan may not be shown to a user as a plan. The message names the step."""


class CostError(ValueError):
    """A number tried to enter a proposal without saying where it came from."""


class SubjectMismatch(CostError):
    """A real measurement, of something other than what this step runs on.

    Kept as its own class because the caller's right answer is different. A
    `CostError` says a number has no origin and there is nothing to do but stop.
    This says the number has a perfectly good origin and it is the origin of a
    different question - so the honest move is to drop back to UNKNOWN and offer
    to go and measure the right thing, which `app/tools/propose.py` does.
    """


#: The provenance a cost carries, from `docs/THE_PROPOSAL_LOOP.md`. The first
#: two names are already the enum of `cost_provenance` in
#: `docs/diagnosis_engine.yaml` line 176; INFERRED is the third value the
#: proposal loop adds, and it is spelled in the same case as the other two so
#: one vocabulary covers the engine and the proposal rather than two that nearly
#: match.
MEASURED = "MEASURED"
INFERRED = "INFERRED"
UNKNOWN = "UNKNOWN"

PROVENANCES = (MEASURED, INFERRED, UNKNOWN)

#: Dimension to unit. `rows` is not a cost; it is the measured quantity most of
#: our costs are derived from, and it lives here so a derivation from it is
#: type-checked rather than described.
ROWS = "rows"
MODEL_TOKENS = "model_tokens"
MODEL_REQUESTS = "model_requests"
WALL_CLOCK = "wall_clock"
DISK = "disk"

DIMENSIONS: dict[str, str] = {
    ROWS: "rows",
    MODEL_TOKENS: "tokens",
    MODEL_REQUESTS: "requests",
    WALL_CLOCK: "seconds",
    DISK: "bytes",
}

#: The four slots every `Cost` fills. All four, always: a cost dimension left
#: out reads as free, and "unknown" is one line to write.
COST_DIMENSIONS = (MODEL_TOKENS, MODEL_REQUESTS, WALL_CLOCK, DISK)

#: JSON Schema type names, which are the only types a tool's schema can declare
#: and therefore the only types an output can promise.
SCHEMA_TYPES = ("string", "integer", "number", "boolean", "object", "array")

#: What `ExitCriterion.met` should be handed. The name says which observation
#: the executor has to make before it can decide whether a step worked.
SOURCES = ("tool_result", "diagnosis", "outputs")

COMPARATORS = ("is_true", "exists", "is_measured", "at_least", "at_most", "equals")

#: THE CANONICAL RUN-STATE VOCABULARY, from `docs/DESIGN_SYSTEM.md` section 2.5,
#: which is the single statement of it. Three documents once carried three
#: different lists; there is one now, and a build states which list it means so
#: that the storm and the diagram cannot pick different ones. Nothing here
#: stores state - a plan has no state - but the picture and the executor key on
#: `Step.id` and need one agreed set of words for what that node is doing.
STEP_STATES = (
    "queued",
    "preflight",
    "running",
    "waiting_input",
    "waiting_approval",
    "stalled",
    "done",
    "failed",
    "cancelled",
)

#: Tools whose meaning depends on WHO is calling, and which therefore may not
#: appear as a step in a plan the harness executes on its own behalf.
#:
#: `state_facts` is the whole list today. Its rows are worth STATED when the
#: person clicks it and ASSERTED when a model calls it (see the second hard rule
#: in `app/tools/registry.py`), so a storm that "ran" it would be a model
#: answering for the user and producing a fact that opens nothing. That is not a
#: step, it is a question, and a `Build` has a place for questions.
PERSON_ONLY_TOOLS = frozenset({"state_facts"})

#: `reads` values that may leave this machine. `huggingface_hub` obviously does.
#: `providers` is here on the conservative reading: a connected provider may be
#: a local Ollama or a hosted API, the proposal is written before we know which,
#: and an environment that declared no egress must not contain a step that might
#: need it. `app/tools/measure.py` independently refuses to send a user's rows
#: to a remote provider on a model's say-so; this is the other half, at plan
#: time, where the person can still see it.
NETWORK_READS = frozenset({"huggingface_hub", "providers"})

#: `reads` values that stay on this machine. Together with `NETWORK_READS` this
#: must cover every value any registered tool declares - a test asserts exactly
#: that, so a tool added next year with `reads=("s3",)` turns red here instead
#: of silently running inside a sandbox that promised no egress.
LOCAL_READS = frozenset(
    {
        # The freshness-stamped snapshots under app/knowledge/. The TOOLS only
        # read the committed file; the network half lives in
        # scripts/refresh_knowledge.py, which is a person's command, not a step
        # a proposal can contain.
        "knowledge",
        "contexts",
        # The threads table - one row per conversation, in this harness's own
        # SQLite file. `read_plan` reads one column of the calling thread's row
        # and nothing else; `write_plan` writes it. Added 2026-09-11.
        "threads",
        # The messages table - every user and assistant line of every
        # conversation, in the same SQLite file. `recall` reads it through an
        # FTS5 index (`app/recall.py`) and nothing writes it from a tool.
        # Added 2026-09-11.
        "messages",
        # The events table - the append-only spine every turn writes, in the
        # same SQLite file. `write_the_results` reads the calling thread's own
        # tool results off it to say which run scored what; nothing leaves the
        # machine. Added 2026-09-18.
        "events",
        # The curated memory table (`app/memory.py`): this project's notes and
        # the person's profile, in the same SQLite file. `remember` reads and
        # writes it; nothing about it leaves the machine. Added 2026-09-11.
        "memory",
        "datasets",
        # The eval bench's own tables (`app/migrations/v008_an_eval_keeps_its_rows.py`).
        # Local without qualification: `eval_runs` and `eval_results` are rows in
        # this harness's SQLite file, and reading them asks nothing of any
        # network. `run_eval` reads them to resume a run it already started;
        # `read_eval_results` reads them and nothing else at all. Sending the
        # rows to a model is `providers`, which those tools declare separately
        # and which is classified NETWORK above - so a plan that grades rows
        # still cannot land in a no-egress environment on the strength of this
        # word.
        "evals",
        "facts",
        # The prompt bench's own tables
        # (`app/migrations/v009_a_prompt_is_a_version.py`). Local for exactly the
        # reason `evals` is: `prompt_lines`, `prompt_variants`, `prompt_scores`
        # and `prompt_champions` are rows in this harness's SQLite file, and a
        # prompt version stored in one conversation goes nowhere. `try_prompt`
        # declares `providers` separately for the half that does leave the
        # process, so this word cannot smuggle a model call into a no-egress
        # environment.
        "prompts",
        # The retrieval bench's own tables
        # (`app/migrations/v010_a_retriever_can_be_scored_alone.py`):
        # `retrieval_indexes`, `retrieval_documents`, `retrieval_passages` and
        # `retrieval_postings`, which are rows in this harness's SQLite file. A
        # LOCAL INDEX IS LOCAL, and this word is where that stops being a slogan
        # and becomes the thing `_validate_egress` checks: `build_retrieval_index`
        # is a token count over files already on this machine, `search_the_index`
        # reads postings and nothing else, and none of the three retrieval tools
        # declares `providers`. So a retrieval plan can run in an environment
        # that declared no egress, and it says so where the person can see it.
        # The day an embedding retriever ships it declares `providers` for the
        # half that leaves the process - classified NETWORK above - and this word
        # cannot smuggle that call into a no-egress environment, exactly as
        # `evals` and `prompts` cannot.
        "retrieval",
        "filesystem",
        "git",
        "hardware",
        "jobs",
        "local_models",
        # The stored `config.json` envelopes under `feasibility.MODEL_CONFIG_ROOT`.
        # Local WITHOUT QUALIFICATION, and the qualification is worth stating
        # because the same files arrive over the network: `read_model_config`
        # fetches one and declares `reads=("huggingface_hub",)` for that half,
        # which is classified NETWORK above. Reading a config that is already on
        # disk is `feasibility.load_model_config`, which is deliberately offline
        # and never fetches - so `can_this_machine_train` can answer inside an
        # environment that declared no egress, and cannot use this word to
        # smuggle a Hub request into one.
        "model_config_cache",
        "recipes",
        "runs",
        # The four agent instruments read OTLP/JSON trace files that already
        # sit on this machine (`app/tools/agents.py`). A TRACE FILE IS LOCAL:
        # the reader parses JSON Lines with the standard library and declares
        # no `providers` half, so a plan that reads somebody's traces can run
        # in an environment that declared no egress - and this word cannot
        # smuggle a network call into one, exactly as `evals`, `prompts` and
        # `retrieval` cannot. The day an instrument ships a remote-fetch half
        # it declares `huggingface_hub` or `providers` for it, classified
        # NETWORK above.
        "traces",
    }
)

_ID = re.compile(r"^[a-z][a-z0-9_]{1,47}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


#: The fact ledger's own timestamp format (`app/tools/evidence.py::_now`, which
#: writes what SQLite's CURRENT_TIMESTAMP would have written). A file's
#: modification time is put into THAT spelling rather than the ledger's dates
#: being put into this module's, because one of the two is a record that already
#: exists in the user's database and the other is a number this process just
#: read. Same shape, same zone, comparable as strings.
_LEDGER_TIME = "%Y-%m-%d %H:%M:%S"


def _stamp(epoch_seconds: float) -> str:
    """A filesystem modification time, in the ledger's spelling. UTC, to the second.

    To the second because that is the resolution the ledger records at, and a
    comparison is only as fine as its coarser side. The consequence is written
    down rather than discovered: a file modified in the same second the count
    was recorded reads as unmodified.
    """
    try:
        return datetime.fromtimestamp(float(epoch_seconds), tz=timezone.utc).strftime(
            _LEDGER_TIME
        )
    except (OSError, OverflowError, ValueError):  # pragma: no cover - a clock the OS refuses
        return ""


def _text(value: Any) -> str:
    return str(value or "").strip()


# ---------------------------------------------------------------------------
# Subjects. WHAT a measurement was a measurement of.

#: The kinds of thing a measurement can be about. `SUBJECT_PATH` covers a file
#: and a folder with one kind on purpose: which of the two a path was is a
#: property of the disk at the moment somebody looked, and a subject recovered
#: from a record cannot know it. Splitting them would make "the folder I counted
#: is now read back as a file" into a mismatch, which is a false refusal about
#: nothing.
SUBJECT_PATH = "path"
SUBJECT_DATASET = "dataset"
SUBJECT_MACHINE = "machine"

SUBJECT_KINDS = (SUBJECT_PATH, SUBJECT_DATASET, SUBJECT_MACHINE)


def _path_key(value: str | Path) -> str:
    """One spelling for one path, so two spellings of one file compare equal.

    `resolve()` folds `.`, `..`, a relative path against the working directory,
    and a symlink to its target. `normcase` folds the case and the separator on
    Windows, where `C:/data/Eval.jsonl` and `c:\\data\\eval.jsonl` are the same
    file. What it does not fold is in the module docstring under WHAT THIS DOES
    NOT CATCH, item 3.
    """
    text = str(value or "").strip().strip('"')
    if not text:
        raise CostError("a subject identified by a path needs a path")
    try:
        resolved = Path(text).resolve(strict=False)
    except (OSError, ValueError):  # pragma: no cover - a path the OS refuses
        resolved = Path(os.path.abspath(text))
    return os.path.normcase(str(resolved))


@dataclass(frozen=True)
class Subject:
    """The thing a measurement was of. Read the module docstring's second rule.

    `key` is the identity and it is what a mismatch turns on. `witness` is the
    cheap freshness check - size and modification time as they were when this
    subject was established - and it is EMPTY whenever nobody could establish
    it, which is the honest state for a subject recovered from a record that
    never stored one. An empty witness never causes a match and never causes a
    refusal; it is absent, and `as_dict` shows that it is absent.

    `modified_at` and `measured_at` are the two halves of the ONE freshness
    check a recovered subject can take part in, and they exist because a subject
    with no witness had no freshness check at all. A subject established by
    looking carries `modified_at` - when this filesystem says the file last
    changed. A subject recovered from the fact ledger carries `measured_at` -
    when that measurement was WRITTEN. A file modified after the count of it was
    recorded is not the file that was counted, and that is decidable from two
    timestamps and one `stat()`, on a 50 GB dataset as cheaply as on a small
    one. Both are in the ledger's own `%Y-%m-%d %H:%M:%S` UTC so they compare
    directly rather than through a conversion somebody has to get right twice.

    WHAT THE DATE DOES NOT CATCH is in the module docstring under WHAT THIS DOES
    NOT CATCH, item 2, and is written there rather than here because it is the
    same list a reader of this file needs in one place.
    """

    kind: str
    key: str
    how: str
    witness: str = ""
    #: When this filesystem says the file last changed, read at the moment this
    #: subject was established. Empty for a subject nobody could stat.
    modified_at: str = ""
    #: When the measurement this subject was recovered from was RECORDED. Empty
    #: for a subject established by looking - a thing looked at now has no
    #: measurement date, it has a witness.
    measured_at: str = ""

    def __post_init__(self) -> None:
        if self.kind not in SUBJECT_KINDS:
            raise CostError(
                f"{self.kind!r} is not a kind of subject. Expected one of "
                f"{', '.join(SUBJECT_KINDS)}."
            )
        if not _text(self.key):
            raise CostError(
                "a subject with no key identifies nothing, and a measurement "
                "attached to nothing is the defect this type exists to close"
            )
        if not _text(self.how):
            raise CostError("a subject must say how it was established")

    # -- the doors --------------------------------------------------------

    @classmethod
    def of_path(cls, path: str | Path) -> "Subject":
        """A file or folder on this machine, stat'ed now so it carries a witness."""
        key = _path_key(path)
        try:
            stat = Path(path).stat()
        except OSError as error:
            raise CostError(
                f"cannot identify {path} as the subject of anything: {error}. "
                "Nothing is costed against a file this process cannot see."
            ) from error
        if Path(path).is_dir():
            return cls(
                kind=SUBJECT_PATH,
                key=key,
                how=(
                    f"the folder at {key}, which is there now. A folder's stat "
                    "says nothing about the files inside it, so this subject "
                    "carries no witness and only its identity is worth anything"
                ),
                modified_at=_stamp(stat.st_mtime),
            )
        return cls(
            kind=SUBJECT_PATH,
            key=key,
            how=f"the file at {key}, as it is on this filesystem now",
            witness=f"{stat.st_size} bytes, modified {stat.st_mtime_ns}",
            modified_at=_stamp(stat.st_mtime),
        )

    @classmethod
    def of_recorded_path(
        cls, path: str | Path, *, how: str, measured_at: str = "", witness: str = ""
    ) -> "Subject":
        """A path read back out of a record, with no claim about its contents.

        Deliberately does NOT stat. Stat'ing here would describe the file as it
        is now and attach that description to a measurement taken at some other
        time, which is a witness that certifies itself.

        `witness` is the one honest way a recovered subject can carry one: the
        RECORD ITSELF held it, written at the moment of the count by
        `counted_rows_how` and read back out of the derivation. That is a
        description of the file as it was then, which is what a witness is
        supposed to be. It stays optional and empty-by-default because every
        row written before that clause existed has none, and an absent witness
        means the witness check does not run - it never means the subject is
        fresh.

        `measured_at` is WHEN THE RECORD WAS WRITTEN, and it is the only thing
        about the file's state at the time that any record here holds. It is
        optional because a caller who cannot date the record must be able to say
        so: an absent date means the date check does not run, exactly as an
        absent witness means the witness check does not run. It never means the
        subject is fresh.
        """
        if not _text(how):
            raise CostError(
                "a subject recovered from a record must say which record and in "
                "what words, or nobody can check the recovery"
            )
        return cls(
            kind=SUBJECT_PATH,
            key=_path_key(path),
            how=_text(how),
            measured_at=_text(measured_at),
            witness=_text(witness),
        )

    @classmethod
    def named(cls, kind: str, key: str, *, how: str, witness: str = "") -> "Subject":
        """Anything that is not a path on this filesystem - a dataset id, this box."""
        return cls(kind=kind, key=_text(key), how=_text(how), witness=_text(witness))

    # -- reading ----------------------------------------------------------

    def describe(self) -> str:
        return f"{self.kind} {self.key}" + (f" ({self.witness})" if self.witness else "")

    def matches(self, other: Any) -> tuple[bool, str]:
        """Is `other` the same thing as this? Returns the answer and the sentence.

        Three levels, and each of the last two only fires when both sides have
        the halves it needs. Identity first, because that is the failure that
        produced a four-fold understatement wearing a complete provenance chain.

        The third level is the date, and it is what a subject recovered from the
        fact ledger has instead of a witness: **a file modified after a count of
        it was recorded is not the file that was counted.** One `stat()` and a
        string comparison, so it costs the same on a 50 GB dataset as on a small
        one, which is the whole reason it is a date and not a hash.
        """
        if not isinstance(other, Subject):
            return False, f"{other!r} is not a subject at all"
        if self.kind != other.kind or self.key != other.key:
            return (
                False,
                f"expected a measurement of {self.describe()} and found one of "
                f"{other.describe()}",
            )
        if self.witness and other.witness and self.witness != other.witness:
            return (
                False,
                f"{self.key} is the same path and not the same file: it was "
                f"{other.witness} when that was measured and it is {self.witness} "
                "now",
            )
        # Either side may be the recovered one, so both directions are checked.
        # An asymmetric freshness check is a check with a spelling that passes.
        for live, recorded in ((self, other), (other, self)):
            if not (live.modified_at and recorded.measured_at):
                continue
            if live.modified_at > recorded.measured_at:
                return (
                    False,
                    f"{self.key} is the same path and not the same file as it "
                    f"was: that measurement was recorded at {recorded.measured_at} "
                    f"and this filesystem says the file was modified at "
                    f"{live.modified_at}, after it. Nothing recorded what the "
                    "file looked like when it was counted, so the count cannot "
                    "be shown to be a count of what is there now",
                )
        return True, f"both are {self.describe()}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "key": self.key,
            "how": self.how,
            # Empty means nobody could establish one. Shown rather than omitted,
            # so a reader can tell "unchanged" from "never checked".
            "witness": self.witness,
            "modified_at": self.modified_at,
            "measured_at": self.measured_at,
        }


# ---------------------------------------------------------------------------
# WHICH ARGUMENT IS THE SUBJECT. The tool's business, not this file's.

#: The attribute a `ToolSpec` declares it on. Read by name, with `getattr`, so
#: this module keeps working against a registry that has not grown the field -
#: see `declared_subject_arguments` for what an absent declaration falls back to.
SUBJECT_DECLARATION = "subject"


def declared_subject_arguments(spec: Any) -> tuple[str, ...]:
    """The arguments through which this tool receives what it operates on.

    **THE DECLARATION THIS FILE ASKS `app/tools/registry.py` FOR**, stated here
    precisely so the half that lives in the registry and the half that lives in
    the validator cannot drift into two different ideas:

        ToolSpec.subject: tuple[str, ...] = ()

    beside `measures=` and `bounds=`, meaning *the names of this tool's own
    arguments through which it receives the thing it reads* - the file, the
    folder, the dataset - in the order the tool would use them, the first one
    present in a call being what that call operates on. Registration checks each
    name against the tool's own schema, which is the rule `bounds=` already
    gets. Expected declarations today: `measure_baseline` reads `eval_path`;
    `measure_eval_set`, `profile_dataset`, `preview_dataset_rows` and
    `attach_context` read `path`.

    **WHY IT BELONGS TO THE TOOL AND NOT TO A LIST.** The previous rule scanned
    EVERY string argument for one that matched the declared subject, which is
    the original defect reproduced through its own fix: a step could point
    `eval_path` at a 777-row file, hide the 120-row file's path in
    `expected_field` - which `measure_baseline` reads as a COLUMN NAME - declare
    `operates_on` as the 120-row file, cost itself from a real measurement of
    it, and pass all three checks showing "120 requests" for a step that will
    run on the other file. A tool KNOWS which of its arguments it reads. A list
    in a third file is a second opinion about that, and a second opinion about
    which file a tool opens is a guess with a tuple around it.

    **AN EMPTY DECLARATION MEANS THE TOOL HAS NOT SAID**, not that it operates
    on nothing, because a field defaulting to `()` cannot tell those apart and
    reading "has not said" as "operates on nothing" would refuse every proposal
    this product makes today. What an undeclared tool falls back to is in
    `subject_of_a_call`, and it refuses to guess: it requires the call to have
    nothing to guess between.
    """
    declared = getattr(spec, SUBJECT_DECLARATION, ()) or ()
    if isinstance(declared, str):  # a single name, declared without the comma
        declared = (declared,)
    return tuple(str(name) for name in declared if str(name).strip())


def _might_name_a_path(value: str) -> bool:
    """Could this argument value be naming a file or a folder on this machine?

    Generous on purpose, and the direction of the generosity is the point. A
    false YES makes a call AMBIGUOUS, which costs an UNKNOWN estimate and a step
    that goes and measures - the product's own preferred answer. A false NO is a
    decoy nobody noticed.

    So three ways in, and the third was added by attacking the second. Anything
    with a separator counts; anything that names something actually there
    counts; **and anything with a filename extension counts even if there is
    nothing at it**, because `eval_path="ghost.jsonl"` beside a real path in
    another argument is a bare name that exists at neither check and is a file
    the moment somebody creates it between the proposal and the approval. The
    cost of the third rule is that a column called `prompt.text` reads as a path
    and makes its call ambiguous, which costs that proposal an UNKNOWN request
    count and a step that counts the file. That is a price this direction is
    supposed to pay, and the tool declaring `subject=` removes it entirely.
    """
    text = str(value or "").strip().strip('"')
    if not text:
        return False
    if "/" in text or "\\" in text:
        return True
    try:
        if Path(text).exists():
            return True
        return bool(PurePath(text).suffix)
    except (OSError, ValueError):  # pragma: no cover - a string the OS will not stat
        return False


def _strings_in(value: Any, depth: int = 0) -> Iterable[str]:
    """Every string inside an argument, including the ones inside a list or an object.

    A fourth attack on this check, and the answer to a claim that would
    otherwise be false. "This call names one path and there is nothing to guess
    between" has to mean the whole call: a schema with an array or an object
    argument is a place to put a second path where a scan of the top level would
    not see it. The depth bound is there because an argument is data and data
    can be shaped by whoever sends it.
    """
    if depth > 4:  # pragma: no cover - an argument nested deeper than any schema
        return
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _strings_in(item, depth + 1)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _strings_in(item, depth + 1)


#: The clause a minting tool appends to its derivation so the ledger keeps what
#: the file looked like when it was counted.
#:
#: WHY THIS EXISTS. `Subject.of_recorded_path` deliberately does not stat: a
#: description of the file as it is now, attached to a measurement taken at
#: some other time, is a witness that certifies itself. So the witness has to be
#: written down AT THE MOMENT OF THE COUNT or not exist, and until this clause
#: it did not exist - `test_a_recovered_subject_carries_no_witness_and_says_so`
#: asserted that limit rather than describing it.
#:
#: A SEMICOLON, NOT A BRACKET, and that is the whole design. The derivation is
#: parsed to recover the path, and the pattern that reads it ran to the end of
#: the string, so anything appended became part of the path. The clause is
#: delimited the way `capped at 500` already is, and the pattern now stops at
#: the delimiter - which also leaves every row written before tonight readable,
#: because a derivation with no semicolon still runs to the end.
WITNESS_CLAUSE = "; the file was {witness} when it was counted"


def witness_of(path: str | Path) -> str:
    """`"N bytes, modified M"` for a file, or empty when it cannot be stat'ed.

    The same string `Subject.of_path` builds, so a recovered witness and a live
    one compare directly. Empty on failure rather than raising: a count that
    happened is still a count, and a missing witness is the honest state this
    file already knows how to carry.
    """
    try:
        stat = Path(str(path)).stat()
    except (OSError, TypeError, ValueError):
        return ""
    return f"{stat.st_size} bytes, modified {stat.st_mtime_ns}"


def counted_rows_how(rows: int, path: str | Path) -> str:
    """The derivation both minting tools write, with its witness."""
    witness = witness_of(path)
    tail = WITNESS_CLAUSE.format(witness=witness) if witness else ""
    return f"counted {rows} rows in {path}{tail}"


def _subject_at(value: str, how: str) -> Subject:
    """The subject an argument names, stat'ed if it is there and honest if not."""
    try:
        return replace(Subject.of_path(value), how=how)
    except CostError:
        return Subject(
            kind=SUBJECT_PATH,
            key=_path_key(value),
            how=f"{how}, and there is nothing at that path on this machine now",
        )


def subject_of_a_call(
    spec: Any, arguments: Mapping[str, Any]
) -> tuple[Subject | None, str]:
    """WHAT A STEP CALLING THIS TOOL WITH THESE ARGUMENTS WILL OPERATE ON.

    Returns the subject and an empty sentence, or `None` and the sentence saying
    why nobody can tell. Both halves are used: `Build.validate` turns the `None`
    into a refusal, and `app/tools/propose.py` turns it into an UNKNOWN cost
    with an offer to go and measure, which is the same fact reaching a person
    two different ways.

    **Two rules, and which one applies is the tool's to decide.**

    1. **The tool declared which of its arguments it reads** - see
       `declared_subject_arguments`. Then that argument's value is the answer
       and nothing else in the call is anybody's business, so a tool that takes
       a model id, an output directory and a dataset can be costed without this
       file having an opinion about any of them.
    2. **The tool has not said.** Then this refuses to pick. It gathers every
       string in the call that might be naming a path at all - including the
       ones inside a list or an object argument, because a schema with either is
       a place to hide a second path from a scan of the top level - and answers
       only if they all name the SAME one: *a call with nothing to guess between
       needs no guess.* Two different paths and one unnamed reader is exactly
       the shape of the defect, and the honest answer to it is "I cannot tell",
       not "probably the first one".

    A subject-bearing argument that is a `Ref` is `None` with its own reason: a
    step whose input is chosen while the plan runs cannot have a cost checked
    against a file named at plan time, and quietly accepting one would be a
    number about a file nobody has picked yet.
    """
    name = str(getattr(spec, "name", "") or "this tool")
    declared = declared_subject_arguments(spec)

    if declared:
        present = [key for key in declared if key in arguments]
        if not present:
            return None, (
                f"{name} declares that it reads what it operates on from "
                f"{list(declared)}, and this call passes none of them"
            )
        for key in present:
            value = arguments[key]
            if isinstance(value, Ref):
                return None, (
                    f"{name} reads what it operates on from {key!r}, and this call "
                    f"takes {key} from step {value.step!r}. What this step will run "
                    "on is decided while the plan runs, so no number established "
                    "now can be shown to be about it"
                )
            if isinstance(value, str) and value.strip():
                return (
                    _subject_at(
                        value,
                        f"named by the {key!r} argument of this call, which is "
                        f"where {name} declares it receives what it reads",
                    ),
                    "",
                )
        return None, (
            f"{name} reads what it operates on from {present!r}, and this call "
            f"passes {[arguments.get(key) for key in present]!r}, which names "
            "nothing this check can identify"
        )

    # THE TOOL HAS NOT SAID. Answer only when there is nothing to choose between.
    found: dict[str, list[str]] = {}
    references = [
        key for key, value in arguments.items() if isinstance(value, Ref)
    ]
    if references:
        # A REFERENCE IN A CALL NOBODY HAS DECLARED THE READER OF IS UNANSWERABLE,
        # and answering it anyway was a hole this check had until it was attacked:
        # `measure_baseline(eval_path=Ref('count', 'path'), expected_field=<a real
        # file>)` left exactly one literal path in the call, so the literal became
        # "what this step operates on" and a genuine count of it costed a step that
        # will open whatever the earlier step returns.
        return None, (
            f"{list(references)} in this call to {name} comes from an earlier step, "
            f"so what this step opens is decided while the plan runs, and {name} "
            "does not declare which of its arguments it reads. A number established "
            "now cannot be shown to be about a file nobody has named yet"
        )
    for key, value in arguments.items():
        for text in _strings_in(value):
            if not _might_name_a_path(text):
                continue
            try:
                names = found.setdefault(_path_key(text), [])
            except CostError:  # pragma: no cover - _path_key only refuses empties
                continue
            if key not in names:
                names.append(key)

    if not found:
        return None, (
            f"nothing this call passes to {name} names a file or a folder, and "
            f"{name} does not declare which of its arguments it reads, so there "
            "is nothing here to check a measurement against"
        )
    if len(found) > 1:
        listed = "; ".join(
            f"{', '.join(sorted(names))}={key}" for key, names in sorted(found.items())
        )
        return None, (
            f"this call passes {len(found)} different paths to {name} - {listed} - "
            f"and {name} does not declare which of its arguments it reads. One of "
            "them is what the tool opens and the rest are something else, and a "
            "cost checked against the wrong one of them is a real measurement of "
            f"a file the step never touches. Declare subject= on {name} and this "
            "is decidable; until then it is a guess, and guessing which argument "
            "is the subject is guessing at the one thing this check exists to "
            "stop guessing at"
        )

    key, names = next(iter(found.items()))
    return (
        _subject_at(
            key,
            f"the only path this call passes to {name} (as {', '.join(sorted(names))}), "
            f"so there is nothing to guess between - {name} does not declare which "
            "of its arguments it reads",
        ),
        "",
    )


# ---------------------------------------------------------------------------
# Readings. A number this process actually read, off something it can name.

_READING: ContextVar[bool] = ContextVar("_minting_reading", default=False)
_MINTING: ContextVar[bool] = ContextVar("_minting_estimate", default=False)


@dataclass(frozen=True)
class Reading:
    """A magnitude that was read, and what it was read off.

    The only way a number enters a proposal as MEASURED. Direct construction is
    refused: every classmethod below performs the reading itself and takes no
    magnitude from its caller, so there is no signature anywhere in this module
    into which a remembered figure can be typed.
    """

    dimension: str
    value: float
    unit: str
    how: str
    at: str
    #: WHAT WAS MEASURED. Not optional, and there is no door that leaves it out:
    #: a magnitude with a perfect account of how it was taken and no statement of
    #: what it was taken OF is the defect in the module docstring's second rule.
    subject: Subject | None = None

    def __post_init__(self) -> None:
        if not _READING.get():
            raise CostError(
                "A Reading is minted by reading something, not by construction. "
                "Use Reading.of_file_size or Reading.of_measured_fact. A number "
                "typed into this constructor would be an invented one wearing a "
                "measurement badge, which is the exact defect "
                "docs/THE_PROPOSAL_LOOP.md names as the trap in a proposal."
            )
        if self.dimension not in DIMENSIONS:
            raise CostError(f"{self.dimension!r} is not a dimension this module knows")
        if not _text(self.how):
            raise CostError("a reading with no `how` is not a reading")
        if not isinstance(self.subject, Subject):
            raise CostError(
                "a reading must name what it read. `how` is prose and prose is "
                "not checkable: 'counted 120 rows in <a temp file>' is a true "
                "sentence beside a request count for a different file, and it "
                "reads as impeccable provenance. Pass a Subject."
            )

    @classmethod
    def _mint(cls, **fields: Any) -> "Reading":
        token = _READING.set(True)
        try:
            return cls(at=_now(), **fields)
        finally:
            _READING.reset(token)

    @classmethod
    def of_file_size(cls, path: str | Path) -> "Reading":
        """How many bytes that file is, right now, off this filesystem."""
        target = Path(path)
        subject = Subject.of_path(target)
        try:
            size = target.stat().st_size
        except OSError as error:
            raise CostError(
                f"cannot read the size of {target}: {error}. Nothing is measured "
                "from a file that is not there."
            ) from error
        return cls._mint(
            dimension=DISK,
            value=float(size),
            unit=DIMENSIONS[DISK],
            how=f"stat() reported {size} bytes for {target}",
            subject=subject,
        )

    @classmethod
    def of_measured_fact(
        cls,
        name: str,
        value: Any,
        origin: str,
        how: str,
        *,
        subject: Subject,
        dimension: str = ROWS,
    ) -> "Reading":
        """A fact the evidence ledger already stamped MEASURED, and nothing else.

        The origin is passed in rather than looked up because this module does
        not import the tool surface (see the module docstring's note on import
        order), and it is CHECKED rather than trusted: an ASSERTED fact - a
        model saying the eval set has four hundred rows - is refused here, for
        the same reason `app/diagnosis.py` refuses to open a gate on one.

        `subject` IS KEYWORD-ONLY AND REQUIRED, and that is the whole shape of
        the fix. This constructor used to take name, value, origin and how - a
        complete account of a measurement with no statement of what it measured
        - so `eval_size_n` counted off one file could cost a step that runs on
        another, and every clause of the resulting derivation was true. There is
        no default here to fall through, because a default subject would be a
        guess about the one thing nobody may guess at.
        """
        if origin != diagnosis.MEASURED:
            raise CostError(
                f"{name!r} carries origin {origin!r}, so it cannot be read as a "
                "measurement. A proposal's costs may be derived from what the "
                "harness measured, never from what somebody claimed."
            )
        try:
            number = float(value)
        except (TypeError, ValueError) as error:
            raise CostError(
                f"{name!r} is {value!r}, which is not a magnitude anything can be "
                "derived from"
            ) from error
        return cls._mint(
            dimension=dimension,
            value=number,
            unit=DIMENSIONS[dimension],
            how=how or f"{name} was measured in this thread",
            subject=subject,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "value": self.value,
            "unit": self.unit,
            "how": self.how,
            "at": self.at,
            "subject": self.subject.as_dict() if self.subject else None,
        }


# ---------------------------------------------------------------------------
# Estimates.


@dataclass(frozen=True)
class Estimate:
    """One number in a proposal, or the honest absence of one.

    Read the module docstring's hard rule before adding a constructor here. The
    property that matters is not that every estimate happens to carry a
    provenance - it is that one without a provenance cannot be built.
    """

    dimension: str
    unit: str
    provenance: str
    value: float | None
    how: str
    inputs: tuple["Estimate", ...] = ()
    find_out_by: str = ""
    reading: Reading | None = None

    # -- the door ---------------------------------------------------------

    def __post_init__(self) -> None:
        if not _MINTING.get():
            raise CostError(
                "An Estimate is built through measured(), unknown(), none() or "
                "arithmetic on estimates that already exist - never by "
                "construction. This is the trap docs/THE_PROPOSAL_LOOP.md names: "
                "'about forty minutes and roughly fourteen cents' is the sentence "
                "that makes a proposal feel trustworthy and the number we would "
                "be inventing."
            )
        if self.dimension not in DIMENSIONS:
            raise CostError(f"{self.dimension!r} is not a dimension this module knows")
        if self.unit != DIMENSIONS[self.dimension]:
            raise CostError(
                f"{self.dimension!r} is measured in {DIMENSIONS[self.dimension]!r}, "
                f"not {self.unit!r}"
            )
        if self.provenance not in PROVENANCES:
            raise CostError(
                f"{self.provenance!r} is not a cost provenance. The vocabulary is "
                f"{', '.join(PROVENANCES)}."
            )
        if not _text(self.how):
            raise CostError(
                f"an estimate of {self.dimension} carries no account of where it "
                "came from, which is the whole thing this type exists to require"
            )
        if self.provenance == UNKNOWN:
            if self.value is not None:
                raise CostError(
                    "an UNKNOWN estimate carries no number. If there is a number, "
                    "it came from somewhere and that somewhere is its provenance."
                )
            if not _text(self.find_out_by):
                raise CostError(
                    "an UNKNOWN estimate must say how it could be found out. "
                    "'I do not know how long this takes, let me run it on 1% and "
                    "find out' is worth more than a guess; 'I do not know' on its "
                    "own is where a proposal stops being useful."
                )
            return
        if self.value is None or self.value < 0:
            raise CostError(
                f"{self.provenance} estimate of {self.dimension} has value "
                f"{self.value!r}"
            )
        if self.provenance == MEASURED and self.reading is None:
            raise CostError(
                "a MEASURED estimate is built from a Reading. Without one there is "
                "nothing that read anything, and the badge is the only measurement "
                "in the room."
            )

    @classmethod
    def _mint(cls, **fields: Any) -> "Estimate":
        token = _MINTING.set(True)
        try:
            return cls(**fields)
        finally:
            _MINTING.reset(token)

    # -- the three arms ---------------------------------------------------

    @classmethod
    def measured(cls, dimension: str, *, reading: Reading) -> "Estimate":
        """We read this. The caller supplies no magnitude - the reading does."""
        if not isinstance(reading, Reading):
            raise CostError(
                "Estimate.measured takes a Reading, which is minted by reading "
                "something. Passing a number here is the one thing this whole "
                "module is arranged to prevent."
            )
        if dimension not in DIMENSIONS:
            raise CostError(f"{dimension!r} is not a dimension this module knows")
        if reading.unit != DIMENSIONS[dimension]:
            raise CostError(
                f"a reading in {reading.unit!r} cannot measure {dimension!r}, which "
                f"is in {DIMENSIONS[dimension]!r}. Convert it with counted_as() or "
                "scaled_by(), where the rule you are applying gets written down."
            )
        return cls._mint(
            dimension=dimension,
            unit=DIMENSIONS[dimension],
            provenance=MEASURED,
            value=float(reading.value),
            how=reading.how,
            reading=reading,
        )

    @classmethod
    def unknown(cls, dimension: str, *, why: str, find_out_by: str) -> "Estimate":
        """We have never done this and will not pretend. Say so, and say how to find out."""
        if dimension not in DIMENSIONS:
            raise CostError(f"{dimension!r} is not a dimension this module knows")
        return cls._mint(
            dimension=dimension,
            unit=DIMENSIONS[dimension],
            provenance=UNKNOWN,
            value=None,
            how=_text(why),
            find_out_by=_text(find_out_by),
        )

    @classmethod
    def none(cls, dimension: str, *, because: str) -> "Estimate":
        """Zero, and why zero is knowable rather than assumed.

        The one INFERRED estimate with no estimate behind it, and the value is
        fixed at zero by this constructor rather than supplied. It exists for
        the case that is provable off a declaration: a tool that does not read
        `providers` sends nothing to the user's model, so its model cost is not
        small or negligible or probably-fine, it is nought, and the reason is a
        line in the tool's own registration.
        """
        if dimension not in DIMENSIONS:
            raise CostError(f"{dimension!r} is not a dimension this module knows")
        if not _text(because):
            raise CostError(
                "a zero with no reason is an assumption. Say what makes it zero."
            )
        return cls._mint(
            dimension=dimension,
            unit=DIMENSIONS[dimension],
            provenance=INFERRED,
            value=0.0,
            how=_text(because),
        )

    # -- arithmetic, which is how INFERRED is reached ---------------------

    def capped_at(self, limit: float, *, because: str) -> "Estimate":
        """At most `limit`, because of a rule the caller states and this records.

        `limit` is a bare number and that is the WALL 6 distinction from
        `app/tools/registry.py`: a bound bounds the work, it does not answer the
        question. `measure_baseline` scoring at most `sample` rows is a rule,
        not a measurement of anything.
        """
        if not _text(because):
            raise CostError("a cap with no stated rule is a number pulled downward")
        try:
            bound = float(limit)
        except (TypeError, ValueError) as error:
            raise CostError(f"{limit!r} is not a bound") from error
        if bound < 0:
            raise CostError("a negative bound is not a bound")
        if self.provenance == UNKNOWN:
            return self._propagate_unknown(f"capped at {bound:g} because {because}")
        assert self.value is not None  # UNKNOWN is the only None case
        return self._mint(
            dimension=self.dimension,
            unit=self.unit,
            provenance=INFERRED,
            value=min(float(self.value), bound),
            how=f"{self.how}; capped at {bound:g} because {because}",
            inputs=(self,),
        )

    def scaled_by(self, factor: float, *, because: str) -> "Estimate":
        """Multiplied by a stated factor, with the factor in the derivation."""
        if not _text(because):
            raise CostError("a factor with no stated reason is an invented one")
        try:
            multiple = float(factor)
        except (TypeError, ValueError) as error:
            raise CostError(f"{factor!r} is not a factor") from error
        if multiple < 0:
            raise CostError("a negative factor is not a factor")
        if self.provenance == UNKNOWN:
            return self._propagate_unknown(f"scaled by {multiple:g} because {because}")
        assert self.value is not None
        return self._mint(
            dimension=self.dimension,
            unit=self.unit,
            provenance=INFERRED,
            value=float(self.value) * multiple,
            how=f"{self.how}; times {multiple:g} because {because}",
            inputs=(self,),
        )

    def counted_as(self, dimension: str, *, because: str) -> "Estimate":
        """The same magnitude, read as a different dimension, one for one.

        The only conversion with no factor, and it needs a stated rule anyway -
        "measure_baseline sends exactly one request per row it scores" is a
        property of the tool, and the estimate that comes out is INFERRED
        because somebody had to know that.
        """
        if dimension not in DIMENSIONS:
            raise CostError(f"{dimension!r} is not a dimension this module knows")
        if not _text(because):
            raise CostError(
                "reading one dimension as another needs the rule that makes it "
                "one for one"
            )
        if self.provenance == UNKNOWN:
            return Estimate.unknown(
                dimension,
                why=f"{self.how}; read as {dimension} because {because}",
                find_out_by=self.find_out_by,
            )
        assert self.value is not None
        return self._mint(
            dimension=dimension,
            unit=DIMENSIONS[dimension],
            provenance=INFERRED,
            value=float(self.value),
            how=f"{self.how}; read as {dimension} one for one because {because}",
            inputs=(self,),
        )

    @classmethod
    def summed(cls, estimates: Sequence["Estimate"], *, dimension: str) -> "Estimate":
        """Add them up - and stay UNKNOWN if any one of them is.

        THE TOTAL OF A MEASURED COST AND AN UNKNOWN ONE IS UNKNOWN. A total that
        quietly drops the term nobody could price is the most dangerous number a
        proposal could carry, because it reads as complete and it is smaller
        than the truth.
        """
        if dimension not in DIMENSIONS:
            raise CostError(f"{dimension!r} is not a dimension this module knows")
        rows = tuple(estimates)
        for row in rows:
            if not isinstance(row, Estimate):
                raise CostError("only estimates can be summed into an estimate")
            if row.dimension != dimension:
                raise CostError(
                    f"cannot sum a {row.dimension} estimate into a {dimension} total"
                )
        if not rows:
            return cls.none(dimension, because="there are no steps to cost")
        unknowns = [row for row in rows if row.provenance == UNKNOWN]
        if unknowns:
            return cls.unknown(
                dimension,
                why=(
                    f"{len(unknowns)} of {len(rows)} parts of this total are "
                    "unknown, so the total is unknown. Reporting the sum of the "
                    "parts we could price would read as the whole cost and be "
                    "smaller than it."
                ),
                find_out_by="; ".join(
                    sorted({row.find_out_by for row in unknowns if row.find_out_by})
                )
                or "measure the unknown parts on a small slice first",
            )
        # A SUM OF MEASUREMENTS IS STILL INFERRED. Nobody read the total off
        # anything; it was computed, and the parts are carried in `inputs` so
        # the computation can be shown. Calling it MEASURED would be the badge
        # travelling one step further than the instrument did.
        return cls._mint(
            dimension=dimension,
            unit=DIMENSIONS[dimension],
            provenance=INFERRED,
            value=sum(float(row.value or 0.0) for row in rows),
            how=f"the sum of {len(rows)} parts, each shown",
            inputs=rows,
        )

    def _propagate_unknown(self, note: str) -> "Estimate":
        return Estimate.unknown(
            self.dimension,
            why=f"{self.how}; {note}",
            find_out_by=self.find_out_by,
        )

    # -- the subject check ------------------------------------------------

    def subjects(self) -> tuple[Subject, ...]:
        """Every thing this number descends from a measurement of, in order.

        Walks `inputs`, because a cap and a one-for-one reinterpretation are
        both INFERRED and both carry the reading through. A number four
        derivations away from the instrument is still a measurement of whatever
        the instrument was pointed at, and that is exactly the case the defect
        arrived in.
        """
        found: list[Subject] = []

        def walk(item: "Estimate") -> None:
            if item.reading is not None and item.reading.subject is not None:
                if item.reading.subject not in found:
                    found.append(item.reading.subject)
            for parent in item.inputs:
                walk(parent)

        walk(self)
        return tuple(found)

    def about(self, subject: Subject) -> "Estimate":
        """This number, confirmed to be about `subject` - or REFUSED, saying which.

        The door the module docstring's second rule is enforced through, for a
        caller who has a subject in hand. It returns the estimate unchanged
        rather than a new one: the check is a check, not a derivation, and
        appending "and I checked" to a provenance chain would be the fourth
        sentence in a chain whose first three were already true.

        Refuses a number that descends from no measurement at all, on purpose. A
        zero proved off a tool's declaration and an honest UNKNOWN are both fine
        numbers and neither is a measurement OF anything, so neither can be
        confirmed to be a measurement of this - and a check that quietly passed
        them would pass everything that had lost its subject on the way here.
        """
        if not isinstance(subject, Subject):
            raise CostError(
                "about() takes a Subject - the thing this number has to be a "
                "measurement of. Nothing else can be compared against."
            )
        found = self.subjects()
        if not found:
            raise SubjectMismatch(
                f"this {self.provenance.lower()} estimate of {self.dimension} "
                "descends from no measurement, so nothing here can confirm it is "
                f"a measurement of {subject.describe()}. Its account of itself is: "
                f"{self.how}"
            )
        for item in found:
            ok, why = subject.matches(item)
            if not ok:
                raise SubjectMismatch(
                    f"this estimate of {self.dimension} is a real measurement of "
                    f"the wrong thing: {why}. A number measured off something else "
                    "is worse than an invented one - an invented number fails the "
                    "question 'where did this come from?', and this one answers it "
                    f"correctly. Its derivation reads: {self.how}"
                )
        return self

    # -- reading ----------------------------------------------------------

    @property
    def known(self) -> bool:
        return self.provenance != UNKNOWN

    def say(self) -> str:
        """One line a person reads, with the provenance in it rather than beside it."""
        if self.provenance == UNKNOWN:
            return f"{self.dimension}: unknown - {self.how}. To find out: {self.find_out_by}"
        return (
            f"{self.dimension}: {self.value:g} {self.unit} "
            f"({self.provenance.lower()}) - {self.how}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "unit": self.unit,
            "provenance": self.provenance,
            "value": self.value,
            "how": self.how,
            "find_out_by": self.find_out_by,
            "reading": self.reading.as_dict() if self.reading else None,
            # Every thing this number descends from a measurement of. Shown at
            # the top level and not only buried in `reading`, because it is what
            # a person checking a cost has to be able to see at a glance: this
            # many requests, counted off THAT file.
            "subjects": [item.as_dict() for item in self.subjects()],
            "from": [row.as_dict() for row in self.inputs],
            "say": self.say(),
        }


@dataclass(frozen=True)
class Cost:
    """What one step, or one whole build, will cost. Four slots, all required.

    `Cost(minutes=40)` is a TypeError and `Cost(model_tokens=40, ...)` is a
    `CostError`: a cost is four estimates, and an estimate cannot exist without
    its origin. A dimension left out would read as free, which is why none of
    them is optional and why "unknown" is one line to write.
    """

    model_tokens: Estimate
    model_requests: Estimate
    wall_clock: Estimate
    disk: Estimate

    def __post_init__(self) -> None:
        for dimension in COST_DIMENSIONS:
            value = getattr(self, dimension)
            if not isinstance(value, Estimate):
                raise CostError(
                    f"cost.{dimension} is {value!r}. A cost is an Estimate, not a "
                    "number: a bare figure here would be a number with no origin, "
                    "which is the one thing a proposal may never carry."
                )
            if value.dimension != dimension:
                raise CostError(
                    f"cost.{dimension} holds a {value.dimension} estimate"
                )

    @property
    def estimates(self) -> tuple[Estimate, ...]:
        return tuple(getattr(self, dimension) for dimension in COST_DIMENSIONS)

    @property
    def fully_known(self) -> bool:
        return all(item.known for item in self.estimates)

    @classmethod
    def summed(cls, costs: Sequence["Cost"]) -> "Cost":
        rows = tuple(costs)
        return cls(
            **{
                dimension: Estimate.summed(
                    [getattr(row, dimension) for row in rows], dimension=dimension
                )
                for dimension in COST_DIMENSIONS
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            dimension: getattr(self, dimension).as_dict()
            for dimension in COST_DIMENSIONS
        }


# ---------------------------------------------------------------------------
# Exit criteria. How we will know it worked, stated before it runs.


@dataclass(frozen=True)
class Verification:
    ok: bool
    stated: str
    saw: Any
    because: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "stated": self.stated,
            "saw": self.saw,
            "because": self.because,
        }


@dataclass(frozen=True)
class ExitCriterion:
    """A checkable claim about what will be true afterwards.

    `stated` is the sentence a person reads before saying yes. The other four
    fields are how the executor decides, so that "a step that cannot show it
    worked did not work" is a function call and not a judgement.

    `source` says WHICH observation to make - the step's own tool result, a
    fresh diagnosis, or the map of outputs the step produced - which is the
    thing an executor most needs told and the thing prose would leave out.
    """

    stated: str
    source: str
    subject: str
    comparator: str
    value: Any = None

    def __post_init__(self) -> None:
        if not _text(self.stated):
            raise BuildInvalid(
                "an exit criterion with no stated sentence is not stated before it "
                "runs, which is the only property that makes it worth anything"
            )
        if self.source not in SOURCES:
            raise BuildInvalid(
                f"{self.source!r} is not something the executor can observe. "
                f"Expected one of {', '.join(SOURCES)}."
            )
        if not _text(self.subject):
            raise BuildInvalid("an exit criterion must name what it looks at")
        if self.comparator not in COMPARATORS:
            raise BuildInvalid(
                f"{self.comparator!r} is not a comparator. Expected one of "
                f"{', '.join(COMPARATORS)}."
            )
        needs_value = self.comparator in ("at_least", "at_most", "equals")
        if needs_value and self.value is None:
            raise BuildInvalid(
                f"comparator {self.comparator!r} needs something to compare against"
            )
        if not needs_value and self.value is not None:
            raise BuildInvalid(
                f"comparator {self.comparator!r} takes no value; {self.value!r} "
                "would never be read, and a field nobody reads is a field that "
                "misleads whoever reads the plan"
            )

    def met(self, observed: Mapping[str, Any] | None) -> Verification:
        """Did it work? One call, so the storm has nothing to interpret."""
        if observed is None:
            return Verification(
                ok=False,
                stated=self.stated,
                saw=None,
                because=f"nothing was observed from {self.source}",
            )
        found, present = _dig(observed, self.subject)
        if not present and self.comparator != "exists":
            return Verification(
                ok=False,
                stated=self.stated,
                saw=None,
                because=f"{self.subject} is not in the {self.source}",
            )
        ok, because = _compare(self.comparator, found, present, self.value)
        return Verification(
            ok=ok, stated=self.stated, saw=found if present else None, because=because
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "stated": self.stated,
            "source": self.source,
            "subject": self.subject,
            "comparator": self.comparator,
            "value": self.value,
        }


def _dig(observed: Mapping[str, Any], subject: str) -> tuple[Any, bool]:
    """Resolve a dotted path. Returns `(value, present)` and never raises."""
    node: Any = observed
    for part in str(subject).split("."):
        if isinstance(node, Mapping) and part in node:
            node = node[part]
            continue
        return None, False
    return node, True


def _compare(comparator: str, found: Any, present: bool, expected: Any) -> tuple[bool, str]:
    if comparator == "exists":
        return present, ("it is there" if present else "it is not there")
    if comparator == "is_true":
        return bool(found) is True, f"saw {found!r}"
    if comparator == "is_measured":
        ok = found == diagnosis.MEASURED
        return ok, f"origin is {found!r}, and only {diagnosis.MEASURED} counts here"
    try:
        left = float(found)
        right = float(expected)
    except (TypeError, ValueError):
        if comparator == "equals":
            return found == expected, f"saw {found!r}, wanted {expected!r}"
        return False, f"saw {found!r}, which is not a number to compare"
    if comparator == "at_least":
        return left >= right, f"saw {left:g}, wanted at least {right:g}"
    if comparator == "at_most":
        return left <= right, f"saw {left:g}, wanted at most {right:g}"
    return left == right, f"saw {left:g}, wanted {right:g}"


# ---------------------------------------------------------------------------
# Risks, questions, outputs, references.


@dataclass(frozen=True)
class Risk:
    """What could go wrong, and what the harness does about it.

    Both halves are required. "This might fail" is not a risk entry, it is a
    disclaimer, and a proposal full of disclaimers is a proposal that has moved
    the work of thinking onto the person approving it.
    """

    what: str
    what_we_do: str

    def __post_init__(self) -> None:
        if not _text(self.what) or not _text(self.what_we_do):
            raise BuildInvalid(
                "a risk names what could go wrong AND what the harness does about "
                "it. Half of one is a disclaimer."
            )

    def as_dict(self) -> dict[str, Any]:
        return {"what": self.what, "what_we_do": self.what_we_do}


@dataclass(frozen=True)
class Question:
    """Something only the person can answer, carried in the plan rather than faked as a step."""

    ask: str
    why: str
    fact: str = ""
    answered_by: str = "state_facts"

    def __post_init__(self) -> None:
        if not _text(self.ask) or not _text(self.why):
            raise BuildInvalid(
                "a question states what is being asked and what it decides. "
                "Without the second half the person cannot tell whether it is "
                "worth answering."
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "ask": self.ask,
            "why": self.why,
            "fact": self.fact,
            "answered_by": self.answered_by,
        }


@dataclass(frozen=True)
class Output:
    """Something a step produces that a later step, or the person, can use.

    `at` is the dotted path to it inside the tool's own result - `rows`, or
    `what_it_is.path`. It is here so the executor extracts an output
    mechanically (`Step.harvest`) instead of each step needing a rule somebody
    wrote down somewhere else. Empty means the output is at the top level under
    its own name.
    """

    name: str
    type: str
    description: str = ""
    at: str = ""

    def __post_init__(self) -> None:
        if not _ID.match(str(self.name)):
            raise BuildInvalid(
                f"{self.name!r} is not a usable output name: lower case, digits and "
                "underscores"
            )
        if self.type not in SCHEMA_TYPES:
            raise BuildInvalid(
                f"output {self.name!r} declares type {self.type!r}; a step's outputs "
                f"are checked against tool schemas, so the type must be one of "
                f"{', '.join(SCHEMA_TYPES)}"
            )

    @property
    def path(self) -> str:
        return self.at or self.name

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "at": self.path,
        }


@dataclass(frozen=True)
class Ref:
    """An argument that is an earlier step's output. This is what makes a dependency real.

    A `needs` entry with no `Ref` behind it is an ordering the author asserted.
    A `Ref` is an ordering the graph can check: `validate` refuses one whose
    step is not in `needs`, or whose named output that step does not produce, or
    whose type the consuming schema will not take.
    """

    step: str
    output: str

    def as_dict(self) -> dict[str, Any]:
        return {"$from_step": self.step, "output": self.output}


# ---------------------------------------------------------------------------
# The environment a build runs in.


@dataclass(frozen=True)
class DataSnapshot:
    """The data as it was, recorded at proposal time so the run is reproducible."""

    path: str
    bytes: float
    modified_at: str
    how: str

    @classmethod
    def of(cls, path: str | Path) -> "DataSnapshot":
        """Read the file. The size comes through `Reading`, like every other measurement."""
        target = Path(path)
        try:
            modified = datetime.fromtimestamp(
                target.stat().st_mtime, tz=timezone.utc
            ).isoformat(timespec="seconds")
            size = Reading.of_file_size(target)
        except (OSError, CostError) as error:
            raise BuildInvalid(
                f"cannot snapshot {target}: {error}. A build that names data it "
                "cannot see is a build that will fail after somebody approved it."
            ) from error
        return cls(
            path=str(target),
            bytes=size.value,
            modified_at=modified,
            # `size.how` and NOT `size.at`. A snapshot is part of the build, the
            # build is what `Build.fingerprint()` hashes, and that fingerprint is
            # what "approval is a contract" compares - `Manifest.of` re-proposes
            # server-side and refuses unless the digest matches what was
            # approved. So anything in here that moves on its own breaks
            # approval, and `Reading.at` is `datetime.now(...)` to the second.
            #
            # The line between them: the size and the modification time are
            # properties OF THE DATA and belong in the hash, because a plan
            # costed against a different file is a different plan. The moment
            # somebody happened to look is a property of the RUN and does not -
            # a human takes longer than a second to read a plan and press
            # approve, so including it made approval fail for every human and
            # made two storm tests intermittently red at roughly one run in
            # eight. The reading's own timestamp is still on the `Reading`; it
            # is simply not part of what the plan IS.
            how=size.how,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "bytes": self.bytes,
            "modified_at": self.modified_at,
            "how": self.how,
        }


@dataclass(frozen=True)
class Environment:
    """Where a build runs. Part of the build, not something the user sets up first.

    `docs/THE_PROPOSAL_LOOP.md` wants a sandbox to be three things: reproducible
    (a pinned environment and a snapshot of the data as it was), disposable (its
    own working directory), and unable to reach anything it was not given
    (egress off unless declared). This records all three, and `Build.validate`
    enforces the third against the tools the steps actually name.
    """

    name: str
    working_dir: str
    egress: bool = False
    egress_reason: str = ""
    data: tuple[DataSnapshot, ...] = ()
    installs: tuple[str, ...] = ()
    python: str = ""

    def __post_init__(self) -> None:
        if not _text(self.name):
            raise BuildInvalid("an environment needs a name a person can refer to")
        if not _text(self.working_dir):
            raise BuildInvalid(
                "an environment needs its own working directory. An experiment "
                "that goes wrong should be deleted, not untangled."
            )
        if self.egress and not _text(self.egress_reason):
            raise BuildInvalid(
                "an environment that can reach the network must say what for. A "
                "sandbox with no egress cannot leak whatever the model says; one "
                "with unexplained egress has given that guarantee away silently."
            )
        if not self.egress and _text(self.egress_reason):
            raise BuildInvalid(
                "this environment has no egress but carries a reason for it, which "
                "will read to the next person as though it does"
            )
        if not _text(self.python):
            object.__setattr__(self, "python", sys.version.split()[0])

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "working_dir": self.working_dir,
            "egress": self.egress,
            "egress_reason": self.egress_reason,
            "data": [item.as_dict() for item in self.data],
            "installs": list(self.installs),
            "python": self.python,
        }


# ---------------------------------------------------------------------------
# Steps.


@dataclass(frozen=True)
class Step:
    """One node. Names the tool that runs it, its inputs, and its outputs.

    `id` is the node id in the diagram AND the key the executor reports state
    under. That is the whole reason the diagram cannot lie about what is
    happening: it is not drawn beside the plan, it is the plan, and a node that
    fails is this step failing.
    """

    id: str
    tool: str
    why: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    produces: tuple[Output, ...] = ()
    needs: tuple[str, ...] = ()
    cost: Cost | None = None
    exit_criterion: ExitCriterion | None = None
    risks: tuple[Risk, ...] = ()
    #: WHAT THIS STEP RUNS ON. Optional only because a step that carries no
    #: measured cost has nothing to check against; the moment a cost descends
    #: from a reading, `Build.validate` requires it and requires the reading to
    #: be OF it. It must also be what the step's own CALL opens - the argument
    #: the tool declares it reads, or, where a tool has not declared one, the
    #: single path the call names - so it cannot become a second, unchecked
    #: account of what runs. See `subject_of_a_call`.
    operates_on: Subject | None = None

    def __post_init__(self) -> None:
        if not _ID.match(str(self.id)):
            raise BuildInvalid(
                f"{self.id!r} is not a usable step id: lower case, digits and "
                "underscores, 2 to 48 characters"
            )
        if not _text(self.why):
            raise BuildInvalid(
                f"step {self.id!r} does not say why it is in the plan. A person is "
                "about to approve this."
            )
        if not isinstance(self.cost, Cost):
            raise BuildInvalid(
                f"step {self.id!r} carries no cost. The spec says a build states "
                "what it will cost in model tokens, wall-clock time and disk; a "
                "step with no cost makes the build's total a lie by omission."
            )
        if not isinstance(self.exit_criterion, ExitCriterion):
            raise BuildInvalid(
                f"step {self.id!r} has no exit criterion. A step that cannot show "
                "it worked did not work."
            )
        if self.operates_on is not None and not isinstance(self.operates_on, Subject):
            raise BuildInvalid(
                f"step {self.id!r} says it operates on {self.operates_on!r}, which "
                "is not a Subject. What a step runs on is an identity a cost can "
                "be checked against, not a sentence."
            )
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))
        object.__setattr__(self, "produces", tuple(self.produces))
        object.__setattr__(self, "needs", tuple(dict.fromkeys(self.needs)))
        object.__setattr__(self, "risks", tuple(self.risks))
        if self.id in self.needs:
            raise BuildInvalid(f"step {self.id!r} depends on itself")
        names = [item.name for item in self.produces]
        if len(set(names)) != len(names):
            raise BuildInvalid(
                f"step {self.id!r} declares the same output name twice: {names}"
            )

    # -- what the executor calls -----------------------------------------

    def refs(self) -> tuple[tuple[str, Ref], ...]:
        return tuple(
            (key, value) for key, value in self.arguments.items() if isinstance(value, Ref)
        )

    def bind(self, produced: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        """This step's arguments with every `Ref` replaced by the real value.

        `produced` is `{step_id: {output_name: value}}`, which is what the storm
        accumulates as it goes. A reference that cannot be resolved raises here
        rather than reaching a tool as `None` - a step running on a silently
        missing input is the shape of failure this object exists to prevent.
        """
        bound: dict[str, Any] = {}
        for key, value in self.arguments.items():
            if not isinstance(value, Ref):
                bound[key] = value
                continue
            source = produced.get(value.step)
            if source is None or value.output not in source:
                raise BuildInvalid(
                    f"step {self.id!r} needs {value.output!r} from step "
                    f"{value.step!r} and it is not there. Nothing was run."
                )
            bound[key] = source[value.output]
        return bound

    def harvest(self, result: Mapping[str, Any] | None) -> dict[str, Any]:
        """The outputs this step declared, pulled out of the tool's own result.

        The other half of `bind`. An output the step promised and the tool did
        not return raises here, which is the executor finding out that a step
        did not do what the plan said before the next step runs on nothing.
        """
        found: dict[str, Any] = {}
        for output in self.produces:
            value, present = _dig(result or {}, output.path)
            if not present:
                raise BuildInvalid(
                    f"step {self.id!r} promised {output.name!r} at "
                    f"{output.path!r} in the result of {self.tool!r}, and it is "
                    "not there. The plan and the tool disagree."
                )
            found[output.name] = value
        return found

    def contract_fingerprint(self) -> str:
        """What was approved about what this step DOES, hashed.

        Deliberately narrower than the whole step: it covers the tool, the
        arguments, the dependencies, the outputs and the exit criterion, and not
        the cost. The executor's question is "is the step I am about to run the
        step that was approved"; a cost estimate that improved between proposal
        and execution is not a deviation from the contract, and treating it as
        one would train people to click through the check that matters.

        `operates_on` is deliberately not in here either, and it is safe out for
        a reason worth writing down rather than assuming: `validate` refuses a
        path subject that is not what the step's own call opens, and the
        arguments ARE fingerprinted. So a step cannot change what it runs on
        without changing this hash. Putting the subject in would
        also drag its WITNESS in, and a file whose modification time moved
        between the proposal and the approval would then read as "this step does
        something different now" - which is a true statement about the data and
        a false one about the contract, in the one place where a false alarm
        teaches people to click through.
        """
        return _digest(
            {
                "id": self.id,
                "tool": self.tool,
                "arguments": _plain(dict(self.arguments)),
                "needs": list(self.needs),
                "produces": [item.as_dict() for item in self.produces],
                "exit_criterion": self.exit_criterion.as_dict()
                if self.exit_criterion
                else None,
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool": self.tool,
            "why": self.why,
            "arguments": _plain(dict(self.arguments)),
            "produces": [item.as_dict() for item in self.produces],
            "needs": list(self.needs),
            "cost": self.cost.as_dict() if self.cost else None,
            "exit_criterion": self.exit_criterion.as_dict()
            if self.exit_criterion
            else None,
            "risks": [item.as_dict() for item in self.risks],
            "contract": self.contract_fingerprint(),
            # `operates_on` IS emitted, as of the change that taught
            # `app/storm.py` to record and rehydrate it. It was held out until
            # then for a good reason, kept here because the reason is still the
            # rule: the storm refuses to rehydrate a recorded step carrying a
            # key it cannot map onto a constructor argument - "a field the
            # validation never sees is a field nobody checked" - so emitting
            # this before `_RECORDED_STEP_KEYS` knew about it turned every
            # approval into a 409.
            #
            # It belongs in the record because it is what a step's cost was
            # measured AGAINST, and a plan whose subject is not recorded is a
            # plan whose most important claim is re-derived on trust. It is
            # rebuilt verbatim rather than re-stat'ed, so `_the_same_plan`
            # compares it like every other key, and a witness that moved
            # between proposal and approval is caught by the check that is for
            # that rather than absorbed by the rebuild.
            #
            # It stays OUT of `contract_fingerprint()` - see the comment there.
            # Including it would drag the witness into the fingerprint, and a
            # file whose mtime moved would then read as "this step does
            # something different now", which is not what changed.
            "operates_on": (
                self.operates_on.as_dict() if self.operates_on else None
            ),
        }


# ---------------------------------------------------------------------------
# The build.


@dataclass(frozen=True)
class Build:
    """The proposal, and the thing the executor consumes. One object, not two.

    Validated at construction: an invalid build cannot exist, so "a build that
    cannot be validated must not be shown to a user as a plan" is a property of
    the type rather than a rule somebody remembers.

    Editing is `dataclasses.replace(build, steps=...)`, which re-runs validation
    - which is what makes "editing a node edits the build" safe: the edited plan
    is checked against the registry again before anybody sees it.
    """

    id: str
    title: str
    for_outcome: str
    because: str
    steps: tuple[Step, ...]
    environment: Environment
    exit_criterion: ExitCriterion
    risks: tuple[Risk, ...] = ()
    questions: tuple[Question, ...] = ()
    #: The facts the diagnosis used, with their origins, as the proposer saw
    #: them. Carried so the proposal can show its own footing and so an
    #: adversary can check that a cost derived from a fact matches the fact's
    #: recorded origin.
    facts: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(self, "risks", tuple(self.risks))
        object.__setattr__(self, "questions", tuple(self.questions))
        object.__setattr__(self, "facts", MappingProxyType(dict(self.facts)))
        self.validate()

    # -- validation -------------------------------------------------------

    def validate(self, registry: Any = None) -> "Build":
        """Executable by construction, or refuse and name the step.

        `registry` defaults to the one live registry. It is an argument so that
        a test can hand in one with a tool taken out and see this refuse - which
        is the mutation check that proves this is checking rather than
        describing.
        """
        registry = _registry(registry)

        if not self.id or not _ID.match(str(self.id)):
            raise BuildInvalid(f"{self.id!r} is not a usable build id")
        if not _text(self.title):
            raise BuildInvalid("a build needs a title a person can read")
        if not _text(self.for_outcome):
            raise BuildInvalid(
                "a build must name the diagnosis outcome it answers. A plan that "
                "is not the answer to anything is a plan nobody asked for."
            )
        if not _text(self.because):
            raise BuildInvalid(
                f"build {self.id!r} does not say why it is being proposed"
            )
        if not isinstance(self.environment, Environment):
            raise BuildInvalid(f"build {self.id!r} has no environment")
        if not isinstance(self.exit_criterion, ExitCriterion):
            raise BuildInvalid(
                f"build {self.id!r} has no exit criterion. How we will know it "
                "worked is stated before it runs, or it is not stated."
            )
        if not self.steps:
            raise BuildInvalid(
                f"build {self.id!r} has no steps. If there is nothing to run, the "
                "honest answer is a question, not a plan with an empty middle."
            )

        seen: dict[str, Step] = {}
        for step in self.steps:
            if step.id in seen:
                raise BuildInvalid(f"step id {step.id!r} is used twice")
            seen[step.id] = step

        for step in self.steps:
            self._validate_step(step, seen, registry)

        self._validate_graph(seen)
        self._validate_questions(registry)
        self._validate_egress(registry)
        return self

    def _validate_step(
        self, step: Step, steps: Mapping[str, Step], registry: Any
    ) -> None:
        spec = registry.get(step.tool)
        if spec is None:
            raise BuildInvalid(
                f"step {step.id!r} names the tool {step.tool!r}, which is not "
                "registered. A step names a registered tool - that is what keeps a "
                "proposal executable rather than aspirational, and a build whose "
                "steps name tools that do not exist is a plan that cannot run."
            )
        if step.tool in PERSON_ONLY_TOOLS:
            raise BuildInvalid(
                f"step {step.id!r} names {step.tool!r}, which only means anything "
                "when the person calls it themselves. Run by the harness it would "
                "record the model's word as the user's and open nothing. That is a "
                "question, and a build carries questions beside its steps."
            )

        properties = dict(spec.schema.get("properties") or {})
        required = set(spec.schema.get("required") or ())
        supplied = dict(step.arguments)

        unknown = sorted(set(supplied) - set(properties))
        if unknown:
            raise BuildInvalid(
                f"step {step.id!r} passes {unknown} to {step.tool!r}, which has no "
                f"such argument. Its schema takes {sorted(properties)}."
            )
        missing = sorted(required - set(supplied))
        if missing:
            raise BuildInvalid(
                f"step {step.id!r} calls {step.tool!r} without {missing}, which its "
                "schema requires. The call would be refused at execution time, "
                "after somebody approved the plan."
            )

        self._validate_subject(step, spec)

        for key, value in supplied.items():
            declared = properties.get(key) or {}
            wanted = declared.get("type")
            if isinstance(value, Ref):
                self._validate_ref(step, key, value, steps, wanted)
                continue
            if wanted and not _matches_type(value, wanted):
                raise BuildInvalid(
                    f"step {step.id!r} passes {key}={value!r} to {step.tool!r}, "
                    f"whose schema declares {key} as {wanted!r}"
                )
            choices = declared.get("enum")
            if choices and value not in choices:
                raise BuildInvalid(
                    f"step {step.id!r} passes {key}={value!r}, which is not one of "
                    f"{list(choices)}"
                )

    def _validate_subject(self, step: Step, spec: Any) -> None:
        """A measured cost must be a measurement of what this step runs on.

        THE WALL FOR THE MODULE DOCSTRING'S SECOND HARD RULE, and the reason it
        lives in `validate` rather than in a proposer: a proposer that forgets
        the check produces a build that cannot be constructed, and an
        unconstructable build never reaches a user as a plan. It is three
        refusals, and the third is the one that is easy to leave out.

        1. A cost that descends from a measurement, on a step that does not say
           what it operates on. That is the defect exactly: a number genuinely
           measured, genuinely stamped, attached to nothing that says what it is
           a measurement OF.
        2. A cost measured off a subject that is not the one this step runs on.
        3. **A subject that is not what the call will actually run on.** Without
           this, a proposer that took its `operates_on` from the same reading it
           took its number from would satisfy (2) trivially, and the check would
           be reading the declaration instead of the call.

        **THE THIRD ONE WAS WRITTEN AS "SOME ARGUMENT NAMES IT" AND THAT WAS THE
        DEFECT AGAIN.** Scanning every string argument for one that matches is
        an existence test where an identity test was needed: a step could point
        `eval_path` at a 777-row file, hide the 120-row file's path in
        `expected_field` - a COLUMN NAME as far as `measure_baseline` is
        concerned - declare `operates_on` as the 120-row file and cost itself
        from a genuine count of it. All three checks passed. The plan said "120
        requests" for a step that would make 500, with a derivation in which
        every clause was true. So the question is no longer *does anything in
        this call mention that file* but *what will this call actually open*,
        and `subject_of_a_call` answers it from the tool's own declaration or
        refuses to answer at all.
        """
        measured_of: list[Subject] = []
        for estimate in step.cost.estimates if step.cost else ():
            for item in estimate.subjects():
                if item not in measured_of:
                    measured_of.append(item)

        if step.operates_on is None:
            if measured_of:
                raise BuildInvalid(
                    f"step {step.id!r} is costed from a measurement of "
                    f"{measured_of[0].describe()} and does not say what it "
                    "operates on. A number that was genuinely measured and is "
                    "attached to nothing saying what it is a measurement OF is "
                    "the one kind of wrong number that survives every question a "
                    "reviewer knows to ask."
                )
            return

        for item in measured_of:
            ok, why = step.operates_on.matches(item)
            if not ok:
                raise BuildInvalid(
                    f"step {step.id!r} runs {step.tool!r} on "
                    f"{step.operates_on.describe()} and its cost was derived from "
                    f"a measurement of something else: {why}. This plan would show "
                    "a real number, with a complete derivation, for a different "
                    "thing."
                )

        runs_on, why_not = subject_of_a_call(spec, step.arguments)

        if step.operates_on.kind != SUBJECT_PATH:
            # A SUBJECT OF ANOTHER KIND USED TO RETURN EARLY, on the reasonable
            # ground that a dataset id or a machine is not a path in a call. It
            # was the shortest way past this whole check: mint the reading with
            # `Subject.named(SUBJECT_DATASET, key=<the file that was counted>)`,
            # declare the same, and a step whose call opens a different file
            # passed every line above. So the early return survives only when
            # the call opens nothing.
            if runs_on is None:
                return
            raise BuildInvalid(
                f"step {step.id!r} says it operates on {step.operates_on.describe()} "
                f"and its call to {step.tool!r} opens {runs_on.key}. A cost checked "
                "against a name for something else has not been checked against the "
                "file this step reads, and a subject of a kind this check does not "
                "compare against paths is the cheapest way to be checked against "
                "nothing."
            )

        if runs_on is None:
            raise BuildInvalid(
                f"step {step.id!r} says it operates on {step.operates_on.key}, and "
                f"this build cannot show that is what its call to {step.tool!r} "
                f"will open: {why_not}. What a step runs on is what its call says "
                "it runs on; a second statement of it that nothing checks is how a "
                "cost measured off the wrong file passes a check that reads the "
                "declaration."
            )
        if runs_on.key != step.operates_on.key:
            raise BuildInvalid(
                f"step {step.id!r} says it operates on {step.operates_on.key}, and "
                f"none of the arguments it passes to {step.tool!r} names that file "
                f"as the thing it reads: this call runs {step.tool!r} on "
                f"{runs_on.key} - {runs_on.how}. What a step runs on is what its "
                "call says it runs on, and a cost checked against a second "
                "statement of it is a cost checked against nothing."
            )

    def _validate_ref(
        self,
        step: Step,
        key: str,
        ref: Ref,
        steps: Mapping[str, Step],
        wanted: str | None,
    ) -> None:
        if ref.step not in steps:
            raise BuildInvalid(
                f"step {step.id!r} takes {key} from step {ref.step!r}, which is not "
                "in this build"
            )
        if ref.step not in step.needs:
            raise BuildInvalid(
                f"step {step.id!r} takes {key} from step {ref.step!r} but does not "
                "declare it in `needs`. The executor would be free to run them at "
                "the same time."
            )
        producer = steps[ref.step]
        output = next((o for o in producer.produces if o.name == ref.output), None)
        if output is None:
            raise BuildInvalid(
                f"step {step.id!r} takes {key} from {ref.step!r}.{ref.output}, and "
                f"{ref.step!r} does not produce {ref.output!r}. It produces "
                f"{[o.name for o in producer.produces]}."
            )
        if wanted and output.type != wanted and not (
            wanted == "number" and output.type == "integer"
        ):
            raise BuildInvalid(
                f"step {step.id!r} needs {key} as {wanted!r} and "
                f"{ref.step!r}.{ref.output} is {output.type!r}"
            )

    def _validate_graph(self, steps: Mapping[str, Step]) -> None:
        for step in steps.values():
            for need in step.needs:
                if need not in steps:
                    raise BuildInvalid(
                        f"step {step.id!r} depends on {need!r}, which is not in this "
                        "build"
                    )
        cycle = _find_cycle(steps)
        if cycle:
            raise BuildInvalid(
                "the dependencies form a cycle: "
                + " -> ".join(cycle)
                + ". A plan with a cycle in it never starts, and finding that out "
                "at execution time means finding it out after somebody approved it."
            )

    def _validate_questions(self, registry: Any) -> None:
        """A build may not ask for something the harness can go and look at.

        `docs/VISION.md` says the harness "asks the questions an ML engineer
        would ask, answers most of them by looking rather than asking". The
        check is against the REGISTRY rather than the ledger's `source:`, and
        that is the load-bearing choice: `source: inspect` describes what kind
        of fact it is, while `measures=` on a registered tool is whether we can
        actually go and get it today. So a question about `tabular_rows` is
        legitimate right now - nothing in this harness stamps it - and turns red
        automatically on the day somebody registers a tool that does.
        """
        facts = diagnosis.default_spec().facts
        for question in self.questions:
            name = _text(question.fact)
            if not name:
                continue
            declared = facts.get(name)
            if declared is None:
                raise BuildInvalid(
                    f"build {self.id!r} asks about {name!r}, which is not a fact "
                    "the ledger declares. A question whose answer has nowhere to go "
                    "is a question that wastes the person's time."
                )
            answerers = sorted(
                spec.name for spec in registry if name in getattr(spec, "measures", ())
            )
            if answerers:
                raise BuildInvalid(
                    f"build {self.id!r} asks the person for {name!r}, and "
                    f"{answerers[0]!r} measures it. Look before you ask: a question "
                    "the product could answer itself is a step it failed to take."
                )

    def _validate_egress(self, registry: Any) -> None:
        if self.environment.egress:
            return
        for step in self.steps:
            spec = registry.get(step.tool)
            reaches = sorted(set(spec.reads) & NETWORK_READS)
            if reaches:
                raise BuildInvalid(
                    f"step {step.id!r} runs {step.tool!r}, which reads {reaches}, "
                    f"and the environment {self.environment.name!r} declares no "
                    "egress. A sandbox that has no egress cannot leak, whatever the "
                    "model says - so a step that might leave the machine has to be "
                    "in an environment that said so, where the person can see it."
                )

    # -- reading ----------------------------------------------------------

    def step(self, step_id: str) -> Step:
        for item in self.steps:
            if item.id == step_id:
                return item
        raise KeyError(step_id)

    def waves(self) -> tuple[tuple[str, ...], ...]:
        """What can run at once, in order. The executor's whole schedule.

        Steps in the same wave have no dependency between them and may run in
        parallel; a wave does not start until the one before it has finished.
        """
        remaining = {step.id: set(step.needs) for step in self.steps}
        order: list[tuple[str, ...]] = []
        done: set[str] = set()
        while remaining:
            ready = tuple(
                sorted(name for name, needs in remaining.items() if needs <= done)
            )
            if not ready:  # unreachable: validate() rejects cycles
                raise BuildInvalid("the dependency graph does not schedule")
            order.append(ready)
            done.update(ready)
            for name in ready:
                remaining.pop(name)
        return tuple(order)

    @property
    def cost(self) -> Cost:
        """What the whole build costs. Unknown wherever any part of it is."""
        return Cost.summed([step.cost for step in self.steps if step.cost])

    def approvals_required(self, registry: Any = None) -> tuple[str, ...]:
        """Steps whose tool will not run without a recorded approval."""
        registry = _registry(registry)
        return tuple(
            step.id
            for step in self.steps
            if getattr(registry.get(step.tool), "approval", "never") == "always"
        )

    def fingerprint(self) -> str:
        """Everything shown to the person, hashed. This is what they approved."""
        return _digest(self.as_dict())

    def deviations_from(self, approved: "Build") -> tuple[str, ...]:
        """What changed since `approved`, in sentences. Empty means the contract holds.

        This is the mechanical half of "what they approved is what runs". The
        executor calls it before it starts and, per step, compares
        `contract_fingerprint()`. Anything non-empty stops and asks; nothing here
        decides on its own that a change is harmless.
        """
        notes: list[str] = []
        if approved.id != self.id:
            notes.append(f"this is build {self.id!r}, not the approved {approved.id!r}")
        if approved.for_outcome != self.for_outcome:
            notes.append(
                f"it now answers {self.for_outcome!r}, not {approved.for_outcome!r}"
            )
        if approved.environment.as_dict() != self.environment.as_dict():
            notes.append("the environment changed")
        if approved.exit_criterion.as_dict() != self.exit_criterion.as_dict():
            notes.append("the exit criterion changed")

        mine = {step.id: step for step in self.steps}
        theirs = {step.id: step for step in approved.steps}
        for added in sorted(set(mine) - set(theirs)):
            notes.append(f"step {added!r} was added and was never approved")
        for removed in sorted(set(theirs) - set(mine)):
            notes.append(f"approved step {removed!r} is gone")
        for shared in sorted(set(mine) & set(theirs)):
            if mine[shared].contract_fingerprint() != theirs[shared].contract_fingerprint():
                notes.append(f"step {shared!r} does something different now")
        return tuple(notes)

    def say(self) -> str:
        """The proposal in the four sentences Max asked for, without a number we invented."""
        wave_count = len(self.waves())
        lines = [
            f"{self.title}.",
            f"Why: {self.because}",
            f"Plan: {len(self.steps)} steps in {wave_count} "
            + ("wave" if wave_count == 1 else "waves")
            + ", running "
            + ", ".join(step.tool for step in self.steps)
            + ".",
            "Cost: " + "; ".join(item.say() for item in self.cost.estimates),
            f"Done when: {self.exit_criterion.stated}",
        ]
        if self.questions:
            lines.append(
                "Needs from you: "
                + "; ".join(question.ask for question in self.questions)
            )
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        """The whole plan, JSON-safe. The diagram renders this; the storm runs it."""
        return {
            "id": self.id,
            "title": self.title,
            "for_outcome": self.for_outcome,
            "because": self.because,
            "steps": [step.as_dict() for step in self.steps],
            "edges": [
                {"from": need, "to": step.id}
                for step in self.steps
                for need in step.needs
            ],
            "waves": [list(wave) for wave in self.waves()],
            "environment": self.environment.as_dict(),
            "cost": self.cost.as_dict(),
            "exit_criterion": self.exit_criterion.as_dict(),
            "risks": [item.as_dict() for item in self.risks],
            "questions": [item.as_dict() for item in self.questions],
            "facts": dict(self.facts),
            "needs_approval": list(self.approvals_required()),
            "step_states": list(STEP_STATES),
            "say": self.say(),
        }


# ---------------------------------------------------------------------------
# Helpers.


def _registry(registry: Any = None) -> Any:
    """The live registry, imported late.

    Late on purpose. `app/tools/__init__.py` imports the proposer, the proposer
    imports this module, and a module-level import of the registry here would
    close that circle - importing `app.build` first would try to finish
    `app.tools` before `Build` exists. The registry is looked up when a build is
    validated instead, which is also the moment it is true.
    """
    if registry is not None:
        return registry
    from app.tools.registry import REGISTRY

    return REGISTRY


def _matches_type(value: Any, declared: str) -> bool:
    if declared == "string":
        return isinstance(value, str)
    if declared == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if declared == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if declared == "boolean":
        return isinstance(value, bool)
    if declared == "object":
        return isinstance(value, Mapping)
    if declared == "array":
        return isinstance(value, (list, tuple))
    return True


def _find_cycle(steps: Mapping[str, Step]) -> list[str]:
    """A cycle in `needs`, as the path around it, or an empty list."""
    colour: dict[str, int] = {}
    stack: list[str] = []

    def walk(name: str) -> list[str]:
        colour[name] = 1
        stack.append(name)
        for need in steps[name].needs:
            if need not in steps:
                continue
            if colour.get(need, 0) == 1:
                return stack[stack.index(need):] + [need]
            if colour.get(need, 0) == 0:
                found = walk(need)
                if found:
                    return found
        stack.pop()
        colour[name] = 2
        return []

    for name in steps:
        if colour.get(name, 0) == 0:
            found = walk(name)
            if found:
                return found
    return []


def _plain(value: Any) -> Any:
    """Make a structure JSON-safe without losing what a `Ref` means."""
    if isinstance(value, Ref):
        return value.as_dict()
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _digest(payload: Any) -> str:
    text = json.dumps(_plain(payload), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


__all__ = [
    "Build",
    "BuildInvalid",
    "COMPARATORS",
    "COST_DIMENSIONS",
    "Cost",
    "CostError",
    "DIMENSIONS",
    "DataSnapshot",
    "DISK",
    "Environment",
    "Estimate",
    "ExitCriterion",
    "INFERRED",
    "LOCAL_READS",
    "MEASURED",
    "MODEL_REQUESTS",
    "MODEL_TOKENS",
    "NETWORK_READS",
    "Output",
    "PERSON_ONLY_TOOLS",
    "PROVENANCES",
    "Question",
    "ROWS",
    "Reading",
    "Ref",
    "Risk",
    "SOURCES",
    "STEP_STATES",
    "SUBJECT_DATASET",
    "SUBJECT_KINDS",
    "SUBJECT_MACHINE",
    "SUBJECT_PATH",
    "Step",
    "Subject",
    "SubjectMismatch",
    "UNKNOWN",
    "Verification",
    "WALL_CLOCK",
]
