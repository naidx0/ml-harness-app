"""The tools that turn a claim into a measurement, and the one that says who said it.

`app/diagnosis.py` now stops a run at `ACTION__SUBSTANTIATE_CLAIMED_FACTS` when
a gate would have opened on a fact nobody can vouch for. That outcome is an
`ACTION__`, which in this product means *we cannot answer until you do this and
re-enter*. An action nobody can perform is a refusal wearing a friendlier word,
so these are the doing.

The two gates the whole tree stands on say exactly what would settle them, in
the spec, in their own words:

  G0 - "Point me at the file or the folder and I will count it myself; if the
       count clears thirty, this gate opens on the same breath."
  G1 - "Run the eval set against the baseline and against a trivial baseline,
       in front of me, and this gate opens."

`measure_eval_set` is the first sentence. `measure_baseline` is the second.
Neither of them decides anything - the gate is still `app/diagnosis.py`'s to
open - and neither of them can stamp a number it was handed, because
`evidence.Instrument` refuses that. What they can do is make the honest path
walkable, which is the difference between a product that says no and a product
that is any use.

`state_facts` is the third door and the one for facts no instrument will ever
reach. `prompt_iterations`, `retrieval_tried`, `model_swap_tried` are declared
`source: ask` because nobody but the user was there. It records what the CALLER
says at what the CALLER is worth: a person clicking the control is STATED and
opens those gates; the model calling the same tool is ASSERTED and does not.
Same tool, same arguments, two different answers, and the difference is which
door the call came through.

## What these tools deliberately do not do

They do not read the fact ledger. `evidence.assemble_facts` refuses to answer a
tool that is holding a measuring instrument, which is what stops the two-step
version of laundering: read the model's own assertion out of the store, hand it
straight back, and collect a MEASURED stamp on it.

`measure_baseline` will not send a user's eval rows to a remote endpoint on a
model's say-so. A model asking to ship the user's data off this machine is not
the user asking. The person can do it from the control; the model gets told no
and told why.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from app import dataquality, diagnosis
# Aliased: `app.providers.build` already owns the bare name in this module
# and builds provider adapters, which is a different thing entirely.
from app import build as costs
from app.providers import Delta, build, secrets, store
from app.tools import evidence
from app.tools.evidence import Instrument
from app.tools.registry import tool


#: How many eval rows a baseline run scores unless told otherwise. Small,
#: because every row is a round trip to somebody's model and a tool that takes
#: twenty minutes by default is a tool nobody runs twice.
DEFAULT_BASELINE_SAMPLE = 20
MAX_BASELINE_SAMPLE = 500

#: What the baseline model is told. Deliberately thin: the point is to find out
#: what the model already does on this task, not to prompt-engineer it. A
#: baseline measured under a clever prompt is a measurement of the prompt.
BASELINE_SYSTEM = (
    "Answer the question. Reply with the answer only - no preamble, no "
    "explanation, no punctuation that is not part of the answer."
)

_WHITESPACE = re.compile(r"\s+")
_EDGE_PUNCTUATION = re.compile(r"^[\s\"'`(\[{]+|[\s\"'`)\]}.,;:!?]+$")


def normalise_answer(value: Any) -> str:
    """Case, whitespace and edge punctuation, and nothing cleverer than that.

    Anything smarter - stemming, synonyms, a judge model - is a scoring policy
    and would make the number depend on a choice nobody sees. Exact match after
    obvious normalisation is a metric a user can reproduce by eye, which is what
    a baseline has to be.
    """
    text = _WHITESPACE.sub(" ", str(value if value is not None else "")).strip()
    return _EDGE_PUNCTUATION.sub("", text).casefold()


# ---------------------------------------------------------------------------
# THE RULER MUST FIT THE DATA.
#
# Max, 2026-09-17, on thread 75: the eval set's expected answers are 420-
# character JSON records - a summary, principles, steps, pitfalls. Exact match
# on those is zero for every model that will ever exist, the trivial baseline
# is one in twenty because every record is distinct, and the engine read the
# pair as "the labels are wrong". The labels were fine. Re-graded by hand, the
# chat model returned a valid record on 19 of 20 rows and missed on ONE field,
# `task_type`, where it invented values instead of picking one of five. That is
# a format finding, the cheapest thing this product exists to catch, and the
# ruler hid it behind a zero. This file's own comment on thread 44 (2026-09-09)
# recorded the same failure and fixed the warning, not the ruler.
#
# So a baseline names its metric, and chooses one that fits when nobody said:
#
#   exact_match  a label, a number, a short answer - reproducible by eye
#   contains     the expected answer appears inside the reply
#   fields       expected is a JSON record: the reply must be a record with
#                every expected key, and its SHORT fields must agree (a
#                category, a number, a list of tags); long text is free text
#                and is not compared, because no string rule grades prose
#
# `fields` is chosen on its own when the expected values are records, and the
# result says which field disagreed most - that sentence is the finding.

EXACT_MATCH = "exact_match"
CONTAINS = "contains"
FIELDS = "fields"
BASELINE_METRICS: tuple[str, ...] = (EXACT_MATCH, CONTAINS, FIELDS)

#: A string field this long or shorter is a label and is compared; longer is
#: prose and is reported as free text. `task_type`, a score, a tag list are
#: labels; a summary sentence is not.
FIELD_LABEL_CHARS = 48
#: A list field agrees when at least this share of the expected items appear.
LIST_AGREEMENT = 0.5


_FENCE = re.compile(r"^```[a-zA-Z0-9_-]*\s*|\s*```$")


def as_record(value: Any, *, lenient: bool = False) -> dict[str, Any] | None:
    """The value as a JSON object, or None when it is not one.

    A REPLY IS READ THE WAY A PERSON WOULD READ IT (`lenient=True`). Small
    local models wrap a record in a ```json fence or open with "Here is the
    answer:", and this used to require the text to START with "{" - so a
    reply that was a good record inside a fence graded `not_a_record` on every
    row, and a baseline of 0 said nothing about the model. For a reply, the
    first JSON object in the text is the record and prose around it is not
    graded either way. An EXPECTED value stays strict - fence aside, it must
    be a record from its first character - because a free-text answer that
    happens to quote a brace must not turn a column into records.
    """
    if isinstance(value, dict):
        return value
    text = str(value if value is not None else "").strip()
    text = _FENCE.sub("", text).strip()
    start = text.find("{")
    if start < 0 or (start > 0 and not lenient):
        return None
    try:
        if lenient:
            parsed, _ = json.JSONDecoder().raw_decode(text[start:])
        else:
            parsed = json.loads(text)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def record_shape(expected_values: Iterable[Any]) -> dict[str, list[str]]:
    """The keys the expected records carry, split by how `fields` grades them.

    `fields` is every key in first-seen order; `compared` are the ones whose
    values are labels or tag lists on most records (a category, a number, a
    list of terms); `free_text` are prose and never decide a grade. This is
    the sentence a baseline on JSON records owes its reader: which fields the
    score is about.
    """
    order: list[str] = []
    votes: dict[str, list[int]] = {}
    for value in expected_values:
        record = as_record(value)
        if record is None:
            continue
        for key, inner in record.items():
            name = str(key)
            if name not in votes:
                order.append(name)
                votes[name] = [0, 0]
            short = _is_label(inner) or _is_tag_list(inner)
            votes[name][0 if short else 1] += 1
    compared = [name for name in order if votes[name][0] >= votes[name][1]]
    return {
        "fields": order,
        "compared": compared,
        "free_text": [name for name in order if name not in compared],
    }


def _is_label(value: Any) -> bool:
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return True
    return isinstance(value, str) and len(value.strip()) <= FIELD_LABEL_CHARS


#: A list entry that opens with a capital or closes with terminal punctuation
#: is a sentence somebody wrote, not a term somebody chose. Length is the wrong
#: discriminator: `mixture of experts` is a term at 18 characters and `Silent
#: overlap` is prose at 14, and on Max's ML-principles set a 48-character cut
#: graded `pitfalls` as verbatim-match tags on 30 rows and as ignorable prose on
#: the other 10 - the same field, two rulers, decided by how long the sentence
#: happened to be. This errs towards prose on purpose: calling a term prose
#: costs a grade, calling prose a term costs a false failure, and free text
#: never decides.
def _is_sentence(value: Any) -> bool:
    text = str(value).strip()
    return bool(text) and (text[0].isupper() or text[-1] in ".!?")


def _is_tag_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(one, (str, int, float)) and _is_label(one) for one in value)
        and not any(isinstance(one, str) and _is_sentence(one) for one in value)
    )


def grade_fields(expected: Any, answer: Any) -> dict[str, Any]:
    """Grade one reply against one expected record, field by field.

    Returns `shape` (`record`, `not_a_record`), the keys `missing`, `agreed`,
    `disagreed` and `free_text`, and `correct`: a record, nothing missing,
    nothing disagreeing. Free text never decides.
    """
    wanted = as_record(expected)
    got = as_record(answer, lenient=True)
    if wanted is None:
        return {"correct": False, "shape": "expected_not_a_record", "missing": [],
                "agreed": [], "disagreed": [], "free_text": []}
    if got is None:
        return {"correct": False, "shape": "not_a_record", "missing": sorted(str(k) for k in wanted),
                "agreed": [], "disagreed": [], "free_text": []}
    missing: list[str] = []
    agreed: list[str] = []
    disagreed: list[str] = []
    free_text: list[str] = []
    for key, value in wanted.items():
        if key not in got:
            missing.append(str(key))
            continue
        theirs = got[key]
        if _is_label(value):
            (agreed if normalise_answer(theirs) == normalise_answer(value) else disagreed).append(str(key))
        elif _is_tag_list(value):
            mine = {normalise_answer(one) for one in value}
            have = (
                {normalise_answer(one) for one in theirs}
                if isinstance(theirs, list)
                else {normalise_answer(theirs)}
            )
            share = len(mine & have) / len(mine) if mine else 0.0
            (agreed if share >= LIST_AGREEMENT else disagreed).append(str(key))
        else:
            free_text.append(str(key))
    return {
        "correct": not missing and not disagreed,
        "shape": "record",
        "missing": missing,
        "agreed": agreed,
        "disagreed": disagreed,
        "free_text": free_text,
    }


def grade_by(metric: str, expected: Any, answer: Any) -> tuple[bool, dict[str, Any] | None]:
    """One row under one ruler: `(correct, field report or None)`."""
    if metric == FIELDS:
        report = grade_fields(expected, answer)
        return bool(report["correct"]), report
    if metric == CONTAINS:
        wanted = normalise_answer(expected)
        return bool(wanted) and wanted in normalise_answer(answer), None
    return normalise_answer(answer) == normalise_answer(expected), None


def choose_metric(expected_values: Iterable[Any]) -> tuple[str, str]:
    """The ruler that fits these expected answers, and why, when nobody said."""
    values = list(expected_values)
    records = sum(1 for one in values if as_record(one) is not None)
    if values and records * 2 >= len(values):
        return FIELDS, (
            f"{records} of {len(values)} expected answers are JSON records, and "
            "exact match on a record is zero for every model; fields compares the "
            "record's shape and its short fields and leaves prose alone"
        )
    return EXACT_MATCH, "the expected answers are short, so exact match after normalisation is reproducible by eye"


def metric_phrase(metric: str) -> str:
    """How the `how` sentence names the ruler, so the fact carries it."""
    if metric == FIELDS:
        return (
            "scored by fields: the reply is a JSON record with every expected key "
            "and its short fields agree; free text is not compared"
        )
    if metric == CONTAINS:
        return "scored by contains: the expected answer appears in the reply after normalisation"
    return "scored by exact match after case and whitespace normalisation"


# ---------------------------------------------------------------------------


#: What this tool does NOT look at, said out loud. Counting is one pass with one
#: integer in it; every check below needs the rows held, compared or summarised,
#: which is `profile_dataset`'s job and `profile_dataset`'s cost. Reporting an
#: empty finding list without this would be defect 3 again - a clean bill of
#: health nobody earned.
_NOT_INSPECTED = (
    "schema", "duplicates", "near_duplicates", "length_distribution",
    "label_imbalance", "missing_values", "degenerate_targets",
)


#: A file whose stem is one of these is a SPLIT, and a folder holding more
#: than one of them is a split directory rather than an eval set. Named here
#: rather than guessed from counts, because the thing that makes
#: `data/splits` different from a corpus of 5,200 examples is what the files
#: are CALLED, not how many there are.
SPLIT_NAMES = frozenset(
    {"train", "training", "valid", "validation", "val", "dev", "test", "eval", "evaluation", "holdout", "held-out", "held_out"}
)


def _split_files(files: "list[Path]") -> "list[Path]":
    """The files in a folder whose names say they are different splits."""
    out = []
    for one in files:
        stem = one.stem.lower().replace(" ", "")
        for suffix in (".jsonl", ".json", ".csv", ".tsv"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
        if stem in SPLIT_NAMES:
            out.append(one)
    return out


@tool(
    "measure_eval_set",
    description=(
        "Count the rows in an evaluation set, on this machine, and record the "
        "count as measured. This is what G0 asks for: the harness counts the "
        "eval set rather than taking anybody's word for its size. Point it at "
        "the file or folder the user named. There is no size limit on what it "
        "will count; if a very large set takes longer than the default budget "
        "it says how far it got and offers to finish. Nothing is sent anywhere."
    ),
    schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The evaluation file or folder on this machine.",
            },
            "finish_the_count": {
                "type": "boolean",
                "description": (
                    "Keep counting to the end of the data however long it takes. "
                    f"Without it the count gives up after "
                    f"{dataquality.COUNT_TIME_BUDGET_SECONDS:g} seconds and reports "
                    "the rate it managed, so nobody waits forever by accident. Set "
                    "it when you have seen that report and want the count anyway."
                ),
            },
        },
        "required": ["path"],
    },
    reads=("filesystem", "datasets"),
    writes=("facts",),
    measures=("eval_size_n",),
    provides=("data.eval_set.count",),
    label="Count the eval set",
    group="Data",
    verb="count the eval set myself",
    order=18,
)
def measure_eval_set(
    path: str, finish_the_count: bool = False, *, instrument: Instrument
) -> dict[str, Any]:
    """Count it, or say why it could not be counted. Never both, never neither.

    IT USED TO BE UNABLE TO COUNT THE THING IT EXISTS TO COUNT. It called
    `dataquality.profile`, took `DEFAULT_ROW_CAP = 200_000` because it passed no
    `max_rows`, and its schema had one property - so above two hundred thousand
    rows it came back `inferred`, correctly refused to stamp an inferred count,
    and left the caller no lever at all. `evidence.resolves('eval_size_n')` sorts
    by how little a tool asks of the user, so this was the tool the product
    handed somebody blocked on `G0_EVAL_SET`, and it was the tool that could not
    settle it. Measured on a 200,001-row JSONL fixture: 57.7 seconds of work, no
    number, no stamp, and no next step.

    THE FIX IS THAT COUNTING IS NOT PROFILING. `dataquality.count_rows` holds one
    integer and a list of column names - O(1) in memory at any file size - so no
    cap on the number of ROWS is needed to bound it, and the cap it was
    inheriting was sized for the near-duplicate index, which cost 250x more on
    the same fixture. What remains is a bound on TIME, which bounds the wait
    rather than the answer, and which the caller can lift with
    `finish_the_count` once it has seen what the wait would be.

    THE LEVER IS DELIBERATELY A YES AND NOT A NUMBER. `max_rows` would ask the
    user to guess how big their own eval set is, and a wrong guess returns the
    same useless lower bound as before; the only honest answer to "how many rows
    should I be willing to read" is "all of them". It is also the one kind of
    argument that can never collide with a count: `Instrument.measured` compares
    types strictly, so a boolean cannot be mistaken for a row count the way an
    integer cap once was.

    `eval_size_n` is stamped MEASURED only when the scan reached the end of the
    data - `count_rows` answers that as `exact`, and a lower bound is not a
    count. A gate opened on "at least this many" is a gate opened on an estimate.
    """
    # A FOLDER OF SPLITS IS NOT AN EVAL SET, and as of 2026-09-19 a folder of
    # one format READS, which is the day this guard has to exist. `data/splits`
    # holds train, valid and eval; counting the folder would stamp
    # `eval_size_n` at their sum, MEASURED, and G0 would open on a number that
    # is three files added together. That is the exact shape of the defect
    # `_directory_data_files` was rewritten to remove - a wrong number wearing
    # a measurement badge - and it is worse here, because the wrong number
    # opens a gate.
    #
    # One file is an eval set. A folder holding exactly one data file is that
    # file and is counted as it. Anything else is refused WITH THE LIST, so
    # the caller picks rather than guesses.
    named = Path(str(path))
    if named.is_dir():
        inside = dataquality._directory_data_files(named)
        splits = _split_files(inside)
        if len(splits) > 1:
            return {
                "ok": False,
                "error": "a_folder_of_splits_is_not_an_eval_set",
                "path": str(named),
                "files": [str(one) for one in splits],
                "summary": (
                    f"{named.name} holds {len(splits)} splits - "
                    + ", ".join(sorted(one.name for one in splits))
                    + ". Counting the folder would stamp eval_size_n at their sum and "
                    "open G0 on training rows. Name the evaluation file itself."
                ),
                "measured_facts": [],
            }
        if len(inside) == 1:
            # One file in a folder is that file, and the row must say so: the
            # folder is not what was counted.
            path = str(inside[0])

    counted = dataquality.count_rows(path, unbounded=bool(finish_the_count))
    rows = counted.get("rows")
    exact = bool(counted.get("exact")) and isinstance(rows, int)

    payload: dict[str, Any] = {
        "ok": bool(counted.get("exists") and counted.get("readable")),
        "path": counted.get("path"),
        "rows": rows,
        "rows_provenance": counted.get("provenance"),
        "exact": exact,
        # Kept under its old name because every reader of this payload already
        # treats it as "this number is not the whole number".
        "truncated": bool(counted.get("stopped_because")),
        "stopped_because": counted.get("stopped_because"),
        "format": (counted.get("format") or {}).get("name"),
        "columns": counted.get("columns"),
        "seconds": counted.get("seconds"),
        "notes": [note for note in (counted.get("note"), counted.get("what_to_do")) if note],
        "checks_not_run": [
            {
                "check": check,
                "why": (
                    "this tool counts rows and does not inspect them; "
                    "profile_dataset is the one that looks inside"
                ),
            }
            for check in _NOT_INSPECTED
        ],
    }

    if not exact:
        # Every branch that could not count says why in its own words, and each
        # of them ends in something the user can do. `count_rows` composes both
        # because it is the code that knows which limit it met.
        payload["summary"] = " ".join(
            part for part in (counted.get("note"), counted.get("what_to_do")) if part
        )
        return payload

    try:
        instrument.measured(
            "eval_size_n",
            int(rows),
            how=costs.counted_rows_how(int(rows), counted.get("path")),
            # Wall 8, and it is handed the census rather than the path so it
            # reads the file under the SAME lever this count was taken under.
            # `finish_the_count` is the user saying "read all of it however long
            # it takes"; a wall that ignored that would refuse the honest count
            # on exactly the files the lever exists for.
            from_file=dataquality.synthetic_census(
                counted.get("path"), unbounded=bool(finish_the_count)
            ),
        )
    except evidence.GeneratedRowsError as error:
        # NOT RAISED ONWARD. The count happened and it is reported - the number
        # is real and hiding it would be its own dishonesty - but nothing was
        # stamped, and the payload says which of the two happened. A tool that
        # raised here would reach the user as a 500, and this is not a fault.
        payload["ok"] = False
        payload["not_measured"] = str(error)
        payload["summary"] = (
            f"Counted {rows:,} rows in {counted.get('path')} and recorded "
            "nothing. This file holds rows this harness generated, and G0 does "
            "not open on those."
        )
        return payload
    payload["summary"] = (
        f"Counted {rows:,} rows in {counted.get('path')}. eval_size_n is now "
        "measured rather than claimed; run the diagnosis again and G0 will be "
        "asked on the count."
    )
    return payload


# ---------------------------------------------------------------------------
# THE THIRD COUNT, AND IT EXISTS BECAUSE THE PRODUCT SAID SO ITSELF.
#
# `evidence.resolves("preference_pairs_n")` answered, in the words the frontier
# shows a person: *"No tool in this harness measures this yet... that is a gap
# in the product rather than something you can answer."* One node reads that
# fact - `S5_PREFERENCES_NOT_DEMONSTRATIONS`, whose condition is
# `preference_pairs_n >= 1000 and user_can_rank_but_not_write` - and it is the
# only route to `TRAIN__DPO`. So the one number standing between a person and
# the preference-optimisation branch was a number nothing could take.
#
# WHY NOT `profile_dataset`, WHICH ALREADY READS THE FILE. Because it cannot
# answer this question exactly. Its `schema[column]["non_null"]` counts each
# column separately, so the smallest of the three is an UPPER BOUND on complete
# triples and not a count of them - a row with a prompt and a chosen and no
# rejected, and another with a rejected and no prompt, are two incomplete rows
# that a per-column minimum reports as one complete pair. A gate opened on an
# upper bound is a gate opened on an estimate, which is `measure_eval_set`'s own
# rule about lower bounds pointing the other way.

#: The three fields a preference row is. Not configurable, because they are
#: `recipes/hf-peft-dpo/entrypoint.py`'s contract rather than this tool's
#: preference - a count taken under different column names would be a count of
#: rows the recipe would refuse.
PREFERENCE_FIELDS = ("prompt", "chosen", "rejected")

#: What a DEMONSTRATION looks like, so a file of them is named rather than
#: reported as zero. `hf-peft-lora` trains on these and `hf-peft-dpo` refuses
#: them; "0 preference pairs" is true and useless, and "this is the other
#: recipe's data" is the same reading turned into something to go and do.
DEMONSTRATION_FIELDS = ("text", "completion", "output", "response")


@tool(
    "count_preference_pairs",
    description=(
        "Count the preference pairs in a file, on this machine, and record the "
        "count as measured. A preference pair is one row carrying a prompt, a "
        "chosen answer and a rejected one - what preference optimisation trains "
        "on, as against the demonstrations a supervised fine-tune trains on. "
        "Point it at the file the user named. If it is a demonstrations file it "
        "says so and names the recipe that wants it. Nothing is sent anywhere."
    ),
    schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The preference file or folder on this machine.",
            },
            "finish_the_count": {
                "type": "boolean",
                "description": (
                    "Keep counting to the end of the data however long it takes. "
                    f"Without it the count gives up after "
                    f"{dataquality.COUNT_TIME_BUDGET_SECONDS:g} seconds and "
                    "reports how far it got, so nobody waits forever by "
                    "accident. Set it when you have seen that report."
                ),
            },
        },
        "required": ["path"],
    },
    reads=("filesystem", "datasets"),
    writes=("facts",),
    measures=("preference_pairs_n",),
    provides=("data.preferences.count",),
    label="Count the preference pairs",
    group="Data",
    verb="count the preference pairs myself",
    order=32,
)
def count_preference_pairs(
    path: str, finish_the_count: bool = False, *, instrument: Instrument
) -> dict[str, Any]:
    """Count complete triples, or say why there are none. Never both, never neither.

    **THE COUNT IS OF COMPLETE ROWS AND THAT IS THE WHOLE POINT.** A row counts
    when it carries all three of `PREFERENCE_FIELDS` with something in each. A
    row with an empty `rejected` is not half a preference; it is a row DPO
    cannot learn anything from, and counting it would put a number in front of
    the ledger's `>= 1000` threshold that the recipe would then refuse.

    **THE INCOMPLETE ONES ARE REPORTED RATHER THAN DROPPED SILENTLY.** A file of
    990 good rows and 40 broken ones sits under the threshold for a reason a
    person can fix in a minute, and "990" on its own does not say which minute.

    **AND A DEMONSTRATIONS FILE IS NAMED, NOT SCORED ZERO.** Pointed at the data
    `hf-peft-lora` wants, this returns 0 - which is true - and a true zero here
    reads as *your data is no good*, when what is true is *your data is for the
    other backend*. The reply says which, and the reply is the same sentence
    `recipes/hf-peft-dpo/entrypoint.py` refuses with, so a person cannot be told
    two different things by two halves of one product.

    The time budget and its lever are `measure_eval_set`'s, for its reasons: the
    honest answer to "how many rows should I be willing to read" is all of them,
    and the bound belongs on the wait rather than on the answer. Nothing is
    stamped from a scan that stopped early - a lower bound is not a count.
    """
    target = Path(path)
    budget = None if finish_the_count else dataquality.COUNT_TIME_BUDGET_SECONDS
    started = time.monotonic()

    pairs = 0
    incomplete = 0
    demonstrations = 0
    seen = 0
    stopped_because = ""
    # A PATH THAT IS NOT THERE IS NOT A FILE OF NO PAIRS, and this check exists
    # because the tool said it was. `iter_records` over a missing path yields
    # nothing and raises nothing, so the first version of this returned a clean,
    # confident, exact count of ZERO for a filename somebody had mistyped -
    # which is the shape of failure every wall in this product is about. Caught
    # by this tool's own test before it shipped.
    unreadable = (
        ""
        if target.exists()
        else f"there is nothing at {target}, so there was nothing to count"
    )
    fmt = dataquality.detect_format(target) if not unreadable else {}

    def _present(record: dict, fields: tuple[str, ...]) -> list[str]:
        return [str(record.get(field) or "").strip() for field in fields]

    try:
        for record in () if unreadable else dataquality.iter_records(target, fmt):
            # `>=` AND NOT `>`, so a budget of zero seconds stops immediately
            # rather than reading whatever fits inside one clock tick. On this
            # platform `time.monotonic` moves in about fifteen milliseconds, so
            # `>` let a four-hundred-row file finish under a zero budget and
            # report itself exact - which is the state this branch exists to
            # refuse. Indistinguishable from `>` at any real budget.
            if budget is not None and time.monotonic() - started >= budget:
                stopped_because = (
                    f"the {budget:g}-second budget was reached after {seen:,} "
                    "rows; call again with finish_the_count to read all of it"
                )
                break
            seen += 1
            if not isinstance(record, dict):  # pragma: no cover - a text-file row
                continue
            values = _present(record, PREFERENCE_FIELDS)
            if all(values):
                pairs += 1
            elif any(values):
                incomplete += 1
            elif any(_present(record, DEMONSTRATION_FIELDS)):
                demonstrations += 1
    except (OSError, ValueError, UnicodeDecodeError) as error:
        unreadable = f"{type(error).__name__}: {error}"

    payload: dict[str, Any] = {
        "ok": not unreadable and not stopped_because,
        "path": str(target),
        "preference_pairs": pairs,
        "rows_read": seen,
        "incomplete_rows": incomplete,
        "demonstration_rows": demonstrations,
        "fields": list(PREFERENCE_FIELDS),
        "format": (fmt or {}).get("name"),
        "exact": not stopped_because and not unreadable,
        "stopped_because": stopped_because or None,
        "seconds": round(time.monotonic() - started, 2),
    }

    if unreadable:
        payload["ok"] = False
        payload["exact"] = False
        payload["summary"] = (
            f"Nothing was counted in {target} and nothing was recorded: "
            f"{unreadable}."
        )
        return payload

    if stopped_because:
        payload["summary"] = (
            f"Read {seen:,} rows of {target} and found {pairs:,} preference "
            f"pairs, and stopped before the end - {stopped_because}. Nothing "
            "was recorded, because a lower bound is not a count and the "
            "ledger's threshold would be asked of the wrong number."
        )
        return payload

    if not pairs and demonstrations:
        payload["summary"] = (
            f"{target} holds {demonstrations:,} rows that look like "
            "DEMONSTRATIONS - a text, or a prompt with the answer beside it - "
            "and no row carrying prompt, chosen and rejected together. That is "
            "what hf-peft-lora trains on, and it is a different objective: "
            "imitate this answer, rather than prefer this answer to that one. "
            "Nothing was recorded as a preference count, because 0 is a true "
            "number that would read as your data being no good when what is "
            "true is that it is the other backend's data."
        )
        return payload

    instrument.measured(
        "preference_pairs_n",
        int(pairs),
        # THE SHAPE OF THIS SENTENCE IS A CONTRACT AND NOT A STYLE.
        # `propose._A_RECORDED_COUNT` is the ledger's only record of WHICH FILE
        # a count was a count of, and it reads `counted <n> rows in <path>` off
        # the end of the derivation. A proposer that cannot recover the subject
        # refuses - correctly - and the refusal would be "nothing recorded which
        # file it counted" about a count that had just been taken. So the
        # qualification goes in FRONT of the phrase the parser reads, which
        # `search` allows, and the sentence says both what was counted and where.
        how=(
            f"preference pairs, meaning rows carrying all of "
            f"{list(PREFERENCE_FIELDS)}: counted {pairs} rows in {target}"
        ),
        # Wall 8. This fact is the only route to TRAIN__DPO, so the door onto it
        # is walled like every other - generated rows do not open a training
        # branch any more than they open G0.
        from_file=dataquality.synthetic_census(
            target, fmt, unbounded=bool(finish_the_count)
        ),
    )
    payload["summary"] = (
        f"Counted {pairs:,} preference pairs in {target}"
        + (
            f", and {incomplete:,} rows that carry some of "
            f"{list(PREFERENCE_FIELDS)} but not all three - those are rows DPO "
            "cannot learn from, and they are worth a minute before you decide "
            "the count is too low"
            if incomplete
            else ""
        )
        + ". preference_pairs_n is now measured rather than claimed."
    )
    return payload


# ---------------------------------------------------------------------------


@tool(
    "measure_baseline",
    description=(
        "Score the connected model on the user's evaluation set and record the "
        "result as a measured baseline, alongside a trivial baseline computed "
        "from the eval file itself. This is what G1 asks for: what does the best "
        "thing that already exists score, before anybody trains anything. It "
        "sends the eval rows to the connected model, so it will not run against "
        "a remote endpoint unless the user starts it themselves. Score the "
        "model you mean to improve: pass `model` (a local model name as "
        "list_local_models shows it) or pin one with set_baseline_target; "
        "otherwise the thread's baseline connection, else the chat one. The "
        "ruler is chosen to fit the data - JSON records are graded field by "
        "field and the reply names the field that disagreed."
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
            "sample": {
                "type": "integer",
                "description": (
                    f"How many rows to score. Default {DEFAULT_BASELINE_SAMPLE}, "
                    f"maximum {MAX_BASELINE_SAMPLE}. The score says how many it "
                    "was measured on."
                ),
            },
            "provider_id": {
                "type": "integer",
                "description": "Which connection to measure. Default: the active one.",
            },
            "model": {
                "type": "string",
                "description": (
                    "Which LOCAL model to score, by name as list_local_models "
                    "shows it - the base you would train, not the chat model. "
                    "Default: the thread's baseline target, else the connection."
                ),
            },
            "metric": {
                "type": "string",
                "enum": list(BASELINE_METRICS),
                "description": (
                    "How a row is graded. Left out, the ruler is chosen to fit: "
                    "`fields` when expected answers are JSON records, else "
                    "`exact_match`. `contains` when the expected answer may sit "
                    "inside a longer reply."
                ),
            },
            "response_format": {
                "type": "object",
                "description": (
                    "A JSON Schema to CONSTRAIN generation to, so the shape is "
                    "right by construction rather than by asking. This is the "
                    "move NO_TRAIN__CONSTRAINED_DECODING recommends instead of "
                    "training: never fine-tune for a format a grammar can "
                    "enforce. Leave it out to measure the model unconstrained, "
                    "which is what a baseline is."
                ),
            },
        },
        "required": ["eval_path", "input_field", "expected_field"],
    },
    reads=("filesystem", "datasets", "providers"),
    writes=("facts",),
    measures=("baseline_measured", "baseline_score", "trivial_baseline_score"),
    provides=("measurement.baseline.score",),
    label="Measure the baseline",
    group="Data",
    verb="score the connected model on the eval set",
    order=19,
)
def measure_baseline(
    eval_path: str,
    input_field: str,
    expected_field: str,
    sample: int = DEFAULT_BASELINE_SAMPLE,
    provider_id: int | None = None,
    response_format: dict[str, Any] | None = None,
    model: str | None = None,
    metric: str | None = None,
    *,
    instrument: Instrument,
) -> dict[str, Any]:
    """Run the eval, score it, and stamp all three of G1's facts or none of them.

    G1's predicate is `baseline_measured and baseline_score is not null and
    trivial_baseline_score is not null`, which is deliberately stronger than a
    boolean: a flag set true with no score behind it is not a measured baseline.
    So this stamps all three from one run or it stamps nothing. A run that fell
    over half way through has measured a broken thing, and reporting the part
    that worked would be the same defect in a smaller shape.

    The trivial baseline is the majority answer over the same rows, computed
    from the file with no model involved. It is what the eval set scores when
    nobody does anything, and a system that cannot beat it has not been shown to
    work at all.
    """
    try:
        wanted = max(1, min(int(sample), MAX_BASELINE_SAMPLE))
    except (TypeError, ValueError):
        wanted = DEFAULT_BASELINE_SAMPLE

    # AU3 — prefer an explicit arg, then this thread's baseline provider, then
    # the active connection. Chat model ≠ train target was a measured failure.
    chosen_id = provider_id
    thread_baseline = None
    if chosen_id is None and instrument.thread_id is not None:
        from app import events as _events

        thread = _events.get_thread(instrument.thread_id) or {}
        raw = thread.get("baseline_provider_id")
        if raw is not None:
            try:
                thread_baseline = int(raw)
                chosen_id = thread_baseline
            except (TypeError, ValueError):
                thread_baseline = None

    row = store.get(int(chosen_id)) if chosen_id is not None else store.active()
    # THE TARGET, NOT THE CHAT MODEL. Max, 2026-09-17: *"when it went to
    # measure, it measured the baseline of itself, and not the actual model we
    # were pre and post fine-tuning."* A name given here wins; a name pinned on
    # the thread with set_baseline_target comes next; the connection row is
    # what carries the server and adapter either way.
    target = str(model or "").strip()
    if not target and instrument.thread_id is not None:
        from app import events as _events

        target = str((_events.get_thread(instrument.thread_id) or {}).get("baseline_model") or "").strip()
    if row is not None and target and target != str(row.get("model") or ""):
        row = {**dict(row), "model": target, "name": f"{row['name']} ({target})"}
    if metric is not None and str(metric) not in BASELINE_METRICS:
        return {
            "ok": False,
            "error": "unknown_metric",
            "detail": (
                f"{metric!r} is not a ruler this tool has. It grades with "
                f"{', '.join(BASELINE_METRICS)}; leave it out and one is chosen to fit."
            ),
            "metrics": list(BASELINE_METRICS),
        }
    if row is None:
        return {
            "ok": False,
            "error": "no_provider",
            "summary": (
                "No model is connected, so there is nothing to measure a baseline "
                "against. Connect one and run this again."
            ),
        }

    active = store.active()
    if (
        thread_baseline is not None
        and active is not None
        and int(active["id"]) != int(row["id"])
        and provider_id is None
    ):
        # Visible mismatch: chat connection is not the baseline target.
        pass  # continue scoring the baseline provider; name both in summary later

    # The person may send their own data wherever they like. A model asking to
    # send it somewhere on their behalf is a different event, and this is the
    # one place in the product where that difference has teeth.
    if row["kind"] != "local" and instrument.actor != evidence.USER:
        return {
            "ok": False,
            "error": "remote_needs_the_user",
            "summary": (
                f"Measuring the baseline would send rows of {eval_path} to "
                f"{row['name']}, which is not on this machine. I will not do that "
                "because a model asked me to. Start it from the control yourself, "
                "or connect a local model and ask again."
            ),
            "provider": row["name"],
            "locality": row["kind"],
        }

    # STREAMED, NOT COLLECTED. This was `list(iter_records(eval_path))` - the
    # whole eval set held in memory in order to score at most
    # `MAX_BASELINE_SAMPLE` rows of it. Nobody could reach the bad case while
    # `measure_eval_set` refused to stamp anything over 200,000 rows, and the
    # fix to that is what makes this reachable: the product now tells a user
    # their five-million-row eval set is measured and routes them straight here.
    # What is kept is the rows that will actually be asked, plus two counts and
    # the column names, all of which are bounded.
    seen_rows = 0
    available = 0
    generated_rows = 0
    #: (question, answer, the row's OWN id or None). The id is carried
    #: because `row_index` is POSITIONAL - it counts eligible rows from zero -
    #: and a scorer keying on the eval file's own ids reads it as if it were
    #: one. Measured 2026-09-10: an eval set numbered from 100 was scored
    #: against one numbered from 0, with matching COUNTS, and produced a table
    #: that looked entirely reasonable about the wrong questions.
    scored_pairs: list[tuple[Any, Any, Any]] = []
    names: set[str] = set()
    stream = dataquality.iter_records(eval_path)
    try:
        for record in stream:
            if not isinstance(record, dict):
                record = {"value": record}
            seen_rows += 1
            # Wall 8, counted in the pass that is already reading every row
            # rather than in a second one over the same file. See the refusal
            # below for why it is asked before the model is called at all.
            if dataquality.is_synthetic_row(record):
                generated_rows += 1
            if len(names) < dataquality.COLUMN_CAP:
                names.update(str(key) for key in record)
            question = record.get(input_field)
            answer = record.get(expected_field)
            if question is None or answer is None:
                continue
            available += 1
            if len(scored_pairs) < wanted:
                scored_pairs.append((question, answer, record.get("row_id")))
    finally:
        # See `dataquality.count_rows`: an abandoned generator holds its file
        # handle until the collector runs, which on Windows keeps the directory.
        stream.close()

    if not seen_rows:
        # A REFUSAL THAT POINTS AT A FILE THAT EXISTS. See
        # `evals._and_what_is_on_disk`: eleven calls of this in one night all
        # named a path that is not there, while the eval set sat three folders
        # down in the same project.
        from app.tools import evals as _evals

        return {
            "ok": False,
            "error": "no_rows",
            "summary": (
                f"No rows could be read from {eval_path}, so there is nothing to "
                "score. Nothing was recorded."
            ),
            "eval_path": eval_path,
            "the_path_exists": Path(eval_path).exists(),
            **_evals._and_what_is_on_disk(instrument.thread_id, eval_path),
        }

    if generated_rows:
        # WALL 8, AND IT IS ASKED HERE FOR TWO REASONS. Every row scored is a
        # round trip to somebody's model, so refusing after the run would have
        # spent their money to tell them the answer does not count. And G1 wants
        # all three of its facts from one run or none of them - a refusal at the
        # second stamp would leave a score on the ledger with no flag beside it.
        return {
            "ok": False,
            "error": "generated_rows",
            "eval_path": eval_path,
            "rows": seen_rows,
            "generated_rows": generated_rows,
            "summary": (
                f"{generated_rows} of the {seen_rows} rows in {eval_path} are "
                "rows this harness generated, so nothing was scored and nothing "
                "was recorded. A baseline measured against invented rows is a "
                "number about a distribution we made up, and G1 would open on "
                f"it. The {seen_rows - generated_rows} real rows in there are "
                "still real: put them in a file of their own and score that."
            ),
        }

    if not available:
        from app.tools import evals as _evals

        return {
            "ok": False,
            "error": "no_such_columns",
            "summary": (
                f"No row in {eval_path} has both {input_field!r} and "
                f"{expected_field!r}. The columns present are "
                f"{sorted(names)}. Nothing was scored."
            ),
            "eval_path": eval_path,
            "columns": sorted(names),
            **_evals._and_what_is_on_disk(instrument.thread_id, eval_path),
        }

    adapter = build(row["adapter"], row["base_url"], row["model"])
    key = secrets.get_key(str(row["id"]))

    if metric is None:
        ruler, chosen_because = choose_metric(answer for _, answer, _ in scored_pairs)
    else:
        ruler, chosen_because = str(metric), "named in the call"

    # UNDER `fields`, THE MODEL IS TOLD THE KEYS, AND NOTHING ELSE. Max's run of
    # 2026-09-21 scored 0 of 20 on JSON-record answers: the model was sent the
    # bare input under "Answer the question", so it could not know the reply
    # had to be a record with `task_type`, `principles` and `summary` - and a
    # record missing an expected key is wrong on every row, for every model
    # that will ever exist. That measures guessing, not the model. The keys are
    # the task's shape; the VALUES a closed field takes are not named, because
    # whether the model picks the right label is the thing being measured, and
    # naming them is what try_prompt is for.
    shape = record_shape(answer for _, answer, _ in scored_pairs) if ruler == FIELDS else None
    system = BASELINE_SYSTEM
    if shape and shape["fields"]:
        system = (
            BASELINE_SYSTEM
            + " Reply with one JSON object with exactly these keys: "
            + ", ".join(shape["fields"])
            + "."
        )

    started = time.monotonic()
    correct = 0
    failures: list[str] = []
    examples: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    #: Per field, over every scored row: how often the reply had it, agreed
    #: on it, or missed it. The sentence "task_type agreed on 0 of 19" is the
    #: finding the ruler used to hide.
    field_tally: dict[str, dict[str, int]] = {}
    records = 0
    try:
        for index, (question, answer, row_id) in enumerate(scored_pairs):
            reply, error = _ask(adapter, key, str(question), response_format, system=system)
            if error is not None:
                failures.append(f"row {index + 1}: {error}")
                break
            hit, report = grade_by(ruler, answer, reply)
            if report is not None:
                records += 1 if report["shape"] == "record" else 0
                for name in ("agreed", "disagreed", "missing", "free_text"):
                    for key_name in report[name]:
                        tally = field_tally.setdefault(key_name, {"agreed": 0, "disagreed": 0, "missing": 0, "free_text": 0})
                        tally[name] += 1
            correct += 1 if hit else 0
            if len(examples) < 3:
                examples.append(
                    {
                        "expected": str(answer)[:200],
                        "model_said": reply[:200],
                        "counted_as": "correct" if hit else "wrong",
                    }
                )
            # EVERY ROW IS KEPT, NOT THREE. The engine's own next action after
            # G1 is ACTION__CLASSIFY_FAILURES, and `run_the_failures` needs a
            # file of the rows that failed carrying what was asked, what was
            # wanted and what came back. This tool computed all of that, scored
            # it, and discarded everything but three examples -- so the only
            # route to the next step was re-asking the model every row: twenty
            # minutes on 196 rows to recover data that already existed.
            # Measured 2026-09-09.
            all_rows.append(
                {
                    "row_index": index,
                    #: THE EVAL FILE'S OWN ID, when it has one, so a scorer
                    #: never has to infer which question this was. Written
                    #: only when the source row carried it: inventing an id
                    #: equal to the position would make the two conventions
                    #: indistinguishable, which is the fault this exists to
                    #: end rather than to hide.
                    **({"row_id": row_id} if row_id is not None else {}),
                    "input": str(question),
                    "expected": str(answer),
                    "answer": reply,
                    "correct": bool(hit),
                    #: WHICH MODEL ANSWERED, IN THE ROW ITSELF. A baseline
                    #: artefact is read months later by somebody pairing it
                    #: against another arm, and a comparison across arms is
                    #: meaningless unless both name their model.
                    #:
                    #: MEASURED 2026-09-10: kill 13 paired an adapter against a
                    #: naming-rule baseline written by this function, and the
                    #: only record of which model produced that baseline was a
                    #: sentence in a commit message. The research lane filed a
                    #: refusal turning on the two arms sharing a base model and
                    #: could not enforce it, because the fact it needed had
                    #: never been written to a file. A refusal satisfiable only
                    #: by believing a sentence is not a refusal.
                    "model": str(row["model"]),
                }
            )
    finally:
        key = None

    asked = len(scored_pairs)
    if failures:
        return {
            "ok": False,
            "error": "model_failed",
            "summary": (
                f"The connected model stopped answering after {correct} of {asked} "
                "rows, so there is no baseline. Nothing was recorded as measured - "
                "a score from a run that fell over is not a score."
            ),
            "detail": failures,
            "provider": row["name"],
        }

    score = correct / asked
    counts = Counter(normalise_answer(answer) for _, answer, _ in scored_pairs)
    #: THE SAME ROWS UNDER THE SAME RULER. The trivial baseline is the most
    #: common expected answer given every time; under `fields` a record that
    #: shares the right task_type with half the rows scores those rows, which
    #: is exactly the number a model has to beat.
    usual = next(
        (answer for _, answer, _ in scored_pairs if normalise_answer(answer) == counts.most_common(1)[0][0]),
        counts.most_common(1)[0][0],
    )
    trivial = sum(1 for _, answer, _ in scored_pairs if grade_by(ruler, answer, usual)[0]) / asked

    instrument.measured(
        "baseline_score",
        score,
        how=(
            f"{row['model']} answered {correct} of {asked} rows of {eval_path} "
            f"correctly, {metric_phrase(ruler)}"
        ),
        # Wall 8, and G1 is the gate that needs it most: a baseline scored
        # against rows this harness generated is a model being marked on its
        # own homework at one remove.
        from_file=eval_path,
    )
    instrument.measured(
        "trivial_baseline_score",
        trivial,
        how=(
            f"always answering {str(counts.most_common(1)[0][0])[:120]!r} scores "
            f"{trivial:.0%} on the same {asked} rows, {metric_phrase(ruler)}"
        ),
        from_file=eval_path,
    )
    instrument.measured(
        "baseline_measured",
        True,
        how=f"this run scored {row['model']} on {asked} rows of {eval_path}",
        from_file=eval_path,
    )

    resolution = _resolution_for(correct, asked)
    # A BASELINE MEASURED ON A DIFFERENT FILE IS A DIFFERENT BASELINE.
    #
    # `baseline_score` is thread-scoped, and the newest row wins. Measure a
    # second eval set into the same thread and the first set's number is gone,
    # silently, with both rows stamped MEASURED and both of them true.
    #
    # Measured 2026-09-09: thread 44 held ELEVEN baseline_score rows from three
    # different eval files. A properly measured 0.357 over 196 rows was replaced
    # by an exact-match 0.0 from a JSON set that metric cannot express, and
    # run_diagnosis then returned BLOCKED__FIX_LABELS_OR_TASK -- correct
    # reasoning over a fact about a different task.
    #
    # The stamp is not refused: one thread per task is a convention, not a law,
    # and refusing would break a caller deliberately re-measuring. What was
    # missing is that nobody was told. The `how` sentence already carries the
    # path, so the previous file is knowable without any new bookkeeping.
    replaced_a_different_set = None
    try:
        previous = [
            row
            for row in evidence.rows_for(instrument.thread_id)
            if row.get("fact") == "baseline_score" and row.get("how")
        ]
        for row in reversed(previous):
            how = str(row.get("how"))
            if str(eval_path) not in how and " rows of " in how:
                # The `how` sentence continues past the path -- "... rows of
                # <path> correctly, scored by exact match after case and
                # whitespace normalisation" -- so taking everything after
                # "rows of" hands back a path with a clause welded to it. A
                # warning that names a mangled file is a warning that misleads,
                # and it would be quoted straight into somebody's issue.
                tail = how.split(" rows of ", 1)[1]
                replaced_a_different_set = tail.split(" correctly", 1)[0].strip()
                break
    except Exception:  # noqa: BLE001 - a warning that fails is not a failed measurement
        replaced_a_different_set = None

    # THE ROWS GO TO DISK, BESIDE THE EVAL FILE THEY CAME FROM.
    #
    # A verdict that exists only in this return value is a verdict the next
    # tool cannot read. `run_the_failures` wants a file; writing one here costs
    # a few milliseconds against the twenty minutes of model time that produced
    # the rows, and it is the difference between the loop advancing and the
    # loop asking the same 196 questions again.
    #
    # It writes ALL rows and not only the failures, because "which rows failed"
    # is a fact about a scoring rule, and a later pass that grades differently
    # -- set overlap rather than exact match, say -- needs the answers it
    # disagreed with, not a pre-filtered list it has to trust.
    rows_path = None
    failures_path = None
    try:
        eval_file = Path(str(eval_path))
        out_dir = eval_file.parent / "runs"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%S")
        rows_file = out_dir / (eval_file.stem + "-baseline-" + stamp + ".jsonl")
        fails_file = out_dir / (eval_file.stem + "-failures-" + stamp + ".jsonl")
        with rows_file.open("w", encoding="utf-8", newline=chr(10)) as handle:
            for record in all_rows:
                handle.write(json.dumps(record, ensure_ascii=False) + chr(10))
        with fails_file.open("w", encoding="utf-8", newline=chr(10)) as handle:
            for record in all_rows:
                if not record["correct"]:
                    handle.write(json.dumps(record, ensure_ascii=False) + chr(10))
        rows_path = str(rows_file)
        failures_path = str(fails_file)
    except OSError as exc:
        # A run that scored is still a run that scored. Losing the file is worth
        # saying out loud and is not worth discarding the measurement over.
        failures.append("rows not written: " + str(exc))

    # WHICH FIELD, IN A SENTENCE. Sorted worst first, so the first name in
    # `fields_off` is the thing to fix, and the summary says it out loud.
    field_report = {
        name: {**tally, "rows": sum(tally.values())} for name, tally in field_tally.items()
    }
    fields_off = sorted(
        (name for name, tally in field_tally.items() if tally["disagreed"] or tally["missing"]),
        key=lambda name: -(field_tally[name]["disagreed"] + field_tally[name]["missing"]),
    )
    finding = ""
    if ruler == FIELDS:
        if shape and shape["fields"]:
            # THE RECORD SHAPE, SAID FIRST. A 0 on JSON records used to arrive
            # with no sentence saying what was compared, and the owner's model
            # read it as the harness treating his records as free text.
            finding += (
                f" Expected answers are JSON records with fields {', '.join(shape['fields'])};"
                f" scoring compares {', '.join(shape['compared']) or 'no short field'}"
                + (
                    f" and leaves {', '.join(shape['free_text'])} as free text"
                    if shape["free_text"]
                    else ""
                )
                + ", and the prompt named the keys but not their values."
            )
        if correct == 0 and asked:
            not_records = asked - records
            if not_records * 2 > asked:
                finding += f" Why 0: {not_records} of {asked} replies were not JSON records at all."
            elif fields_off:
                worst_off = fields_off[0]
                finding += (
                    f" Why 0: {worst_off} disagreed or was missing on "
                    f"{field_tally[worst_off]['disagreed'] + field_tally[worst_off]['missing']} "
                    f"of {asked} rows - that field decides the score."
                )
        finding += f" By fields: {records} of {asked} replies are JSON records"
        if fields_off:
            worst = fields_off[0]
            tally = field_tally[worst]
            finding += (
                f"; {worst} agreed on {tally['agreed']} of {tally['agreed'] + tally['disagreed']} "
                f"rows that had it"
                + (f" and was missing on {tally['missing']}" if tally["missing"] else "")
                + " - that field is the finding"
            )
        free = [name for name, tally in field_tally.items() if tally["free_text"] and not tally["disagreed"]]
        if free:
            finding += f"; {', '.join(sorted(free)[:4])} are free text and were not compared"
        finding += "."
    return {
        "ok": True,
        "rows_path": rows_path,
        "failures_path": failures_path,
        "failures_written": sum(1 for r in all_rows if not r["correct"]),
        "replaced_a_baseline_from": replaced_a_different_set,
        # AND THE RESOLUTION TRAVELS WITH THE SCORE, in the sentence a person
        # reads, the way it does out of `run_eval` and every other scorer in the
        # product. The old line ended "Report it with the score" and then put a
        # number in a field nobody rendered - so the instruction was addressed to
        # whoever was reading the JSON.
        "summary": (
            f"{row['model']} scores {score:.0%} on {asked} rows of {eval_path}. "
            f"Always answering the most common label scores {trivial:.0%} on the "
            f"same rows. Both are measured; run the diagnosis again and G1 will be "
            f"asked on them. {resolution['says']}" + finding
            + (
                f" Scored thread baseline provider {row['name']}"
                f" (chat active is {active['name']})."
                if (
                    thread_baseline is not None
                    and active is not None
                    and int(active["id"]) != int(row["id"])
                )
                else ""
            )
        ),
        "provider": row["name"],
        "model": row["model"],
        "locality": row["kind"],
        "eval_path": eval_path,
        "rows_available": available,
        "rows_scored": asked,
        "correct": correct,
        "baseline_score": score,
        "trivial_baseline_score": trivial,
        "metric": ruler,
        "metric_chosen_because": chosen_because,
        **({"record_shape": shape} if shape else {}),
        "field_report": field_report,
        "fields_off": fields_off,
        "seconds": round(time.monotonic() - started, 2),
        "examples": examples,
        # INVARIANT 3, AND THIS LINE WAS BREAKING IT. It read
        #
        #     f"{asked} rows resolves a difference of about {1/asked:.0%} at best"
        #
        # which is 1/n - the GRANULARITY of the score, the smallest step it can
        # take - sold under the word "resolves", which in this product means what
        # a difference has to exceed before it is evidence. On thirty rows those
        # two numbers are 3% and 25%, and the smaller one was printed on the very
        # number gate G1 opens on and every later delta is compared against.
        #
        # The product already computes the real one. `evals.resolution_for` does
        # a Wilson interval and the worst-case two-run threshold, `run_eval` uses
        # it, and this tool - the one that produces the baseline - did not. Found
        # by driving the loop on real data. Both numbers are here now, under
        # names that say which is which, because the granularity is true and
        # useful and was only ever mislabelled.
        "granularity": (
            f"One row is {(1.0 / asked):.1%} of this score: with {asked} rows a "
            "score can only take values that many points apart. That is the "
            "STEP SIZE, not what a difference has to exceed to be evidence - see "
            "`resolution`."
        ),
        "resolution": resolution,
    }


def _resolution_for(correct: int, n: int) -> dict[str, Any]:
    """`evals.resolution_for`, imported here because `evals` imports this module.

    ONE COMPUTATION OF WHAT A SCORE RESOLVES, not two, and this tool used to be
    the one that had its own. `app/tools/evals.py` binds `measure.normalise_answer`
    at import, so a module-level `from app.tools import evals` here is a cycle;
    a second copy of the Wilson arithmetic would not be, and would be far worse.
    The import is local, the function is the same one `run_eval` calls, and the
    two numbers a person is shown for the same eval set therefore agree.
    """
    from app.tools import evals

    return evals.resolution_for(correct, n)


def _ask(
    adapter: Any,
    key: str | None,
    question: str,
    response_format: dict[str, Any] | None = None,
    *,
    system: str = BASELINE_SYSTEM,
) -> tuple[str, str | None]:
    """One question, one answer. Returns `(text, error)`; never raises."""
    conversation = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]
    parts: list[str] = []
    try:
        # PASSED ONLY WHEN THERE IS ONE, and that is not tidiness.
        #
        # `stream` is a duck-typed seam: two shipped adapters implement it and
        # so does every fake in the suite. Passing a new keyword unconditionally
        # made every one of those fakes raise TypeError, which this function
        # catches and reports as "the connected model stopped answering after 0
        # of N rows" -- 14 tests failed that way, none of them naming the
        # argument that broke them. An optional feature must be optional on the
        # wire as well as in the signature.
        extra = {"response_format": response_format} if response_format is not None else {}
        thought: list[str] = []
        for delta in adapter.stream(conversation, None, secret=key, **extra):
            if not isinstance(delta, Delta):
                continue
            if delta.kind == "text" and delta.text:
                parts.append(delta.text)
            elif delta.kind == "reasoning" and delta.text:
                thought.append(delta.text)
            elif delta.kind == "error":
                return "", delta.detail
    except Exception as error:  # noqa: BLE001 - a dead endpoint is a report, not a crash
        return "", f"{type(error).__name__}: {error}"
    # A THINKING MODEL THAT ANSWERED ONLY IN ITS REASONING ANSWERED. Scoring
    # that as an empty reply marked a model wrong for where it put the words.
    return ("".join(parts).strip() or "".join(thought).strip()), None


# ---------------------------------------------------------------------------


@tool(
    "set_baseline_target",
    description=(
        "Pin which LOCAL model this conversation's baseline is measured on - "
        "the base you mean to fine-tune, by name as list_local_models shows "
        "it. measure_baseline scores that model from then on instead of the "
        "chat model. Pass an empty name to unpin."
    ),
    schema={
        "type": "object",
        "properties": {
            "model": {
                "type": "string",
                "description": "A local model name, exactly as list_local_models shows it. Empty unpins.",
            },
            "thread_id": {"type": "integer", "description": "Filled in for you."},
        },
        "required": ["model"],
    },
    # No `providers` in `reads`: this puts no text in front of any model, it
    # writes a name on the thread. The roster of tools that can score a model
    # is derived from that declaration, and this is not one of them.
    reads=(),
    writes=("threads",),
    provides=("measurement.baseline.target",),
    label="Baseline target",
    group="Data",
    verb="pin which local model the baseline is measured on",
    order=18,
)
def set_baseline_target(model: str, thread_id: int | None = None) -> dict[str, Any]:
    """The target is a fact about the conversation, so it lives on the thread.

    Max, 2026-09-17: the model measured the baseline of itself because nothing
    let it name the model it was about to train. AU3 gave the thread a
    provider column with a route and no door - no tool, no control - so the
    column stayed empty on every thread that needed it.
    """
    from app import events as _events

    if thread_id is None:
        return {"ok": False, "error": "missing_thread_id"}
    name = str(model or "").strip()
    row = _events.set_thread_baseline_model(int(thread_id), name or None)
    if row is None:
        return {"ok": False, "error": "no_such_thread", "thread_id": thread_id}
    return {
        "ok": True,
        "baseline_model": name or None,
        "summary": (
            f"The baseline for this conversation is now measured on {name}. "
            "measure_baseline scores it next; the chat model keeps talking."
            if name
            else "Unpinned: measure_baseline scores the connection again."
        ),
    }


# ---------------------------------------------------------------------------


def _unwrap_facts(facts: Any) -> dict[str, Any]:
    """The facts a caller meant, from the shapes a model actually sends.

    The guidance prints a whole call - {"facts": {"modality": "text"}} - and a
    model that pastes it INTO the `facts` argument sends it one level deeper;
    one that writes JSON by hand sometimes sends the object as a string. Both
    were refused ("'facts' is not a declared fact", or a ValueError out of
    `dict()`), so the call the harness recommended was a call it rejected. A
    key named `facts` is never itself a fact - the ledger declares no such
    name - so unwrapping it cannot swallow one.
    """
    value: Any = facts
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    if not isinstance(value, dict):
        return {}
    out = dict(value)
    for _ in range(3):
        inner = out.get("facts")
        if not isinstance(inner, dict):
            break
        rest = {k: v for k, v in out.items() if k != "facts"}
        out = {**inner, **rest}
    return out


# ---------------------------------------------------------------------------
# What state_facts may not say again, and what it may not say at all.


def _same_reading(said: Any, measured: Any) -> bool:
    """Is what the caller said the reading the instrument already took?

    NOT `evidence._same`, and on purpose. That one is strict by type because it
    guards a STAMP, where `1` laundering into `True` is the danger. This guards
    a restatement, and Max's thread 93 said `vram_gb` 8 for a measured 8.0 and
    `baseline_score` 0 for a measured 0.0 - the same reading, written the way a
    model writes JSON. A number is compared as a number (a quoted one too), a
    flag as a flag, a word without its case.
    """
    def flag(value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in ("true", "false"):
            return value.strip().lower() == "true"
        return None

    if isinstance(measured, bool) or isinstance(said, bool):
        left, right = flag(said), flag(measured)
        return left is not None and left == right
    if isinstance(measured, (int, float)):
        try:
            return math.isclose(float(said), float(measured), rel_tol=1e-9, abs_tol=1e-12)
        except (TypeError, ValueError):
            return False
    if isinstance(measured, str) and isinstance(said, str):
        return said.strip().lower() == measured.strip().lower()
    return bool(said == measured)


def _measured_on_this_thread(thread_id: int | None) -> dict[str, dict[str, Any]]:
    """The newest MEASURED row per fact this thread can see - the one that wins.

    Machine-scope rows (the hardware) come through `rows_for` too, because the
    box is the same box whichever thread asks, and thread 93 restated those.
    """
    latest: dict[str, dict[str, Any]] = {}
    for row in evidence.rows_for(thread_id):
        if row.get("origin") == evidence.MEASURED:
            latest[str(row["fact"])] = row
    return latest


#: The modalities a file of prose rows is consistent with. `code` is prose to
#: the field rule below and `multimodal` may keep its media beside the file, so
#: neither is contradicted by reading it; every other value in the ledger's
#: enum - a table, a series, an image, a sound - is.
TEXT_ROWS_ADMIT = ("text", "code", "multimodal")


def inspect_modality(path: str | Path) -> dict[str, Any] | None:
    """`text`, when the file's rows carry prose and name no media. Otherwise None.

    NO NEW CLASSIFIER. Three rules this product already runs, in a row:
    `dataquality.iter_records` reads the rows the way every other reader does;
    `record_shape` - the rule the `fields` grader uses - splits the fields into
    labels and prose; `full_defaults._is_text` - the rule that derives
    `modality` from the eval file - says whether any value names an image,
    audio or video file. It says `text` only when all three agree, and None for
    everything else: a file it cannot open, rows with no prose field (a table
    of labels and numbers is what a tabular claim describes), a value that
    names media. None means the inspection settled nothing, and a statement
    stands exactly as it did before this existed.
    """
    from app import full_defaults

    try:
        where = Path(path)
        if not where.exists():
            return None
        fmt = dataquality.detect_format(where)
    except Exception:  # noqa: BLE001 - an unreadable path settles nothing
        return None
    if not fmt.get("readable"):
        return None
    rows: list[dict[str, Any]] = []
    stream = dataquality.iter_records(where, fmt)
    try:
        for record in stream:
            if isinstance(record, dict):
                rows.append(record)
            if len(rows) >= full_defaults.SAMPLE_ROWS:
                break
    except Exception:  # noqa: BLE001 - a file that fails half-read settles nothing
        return None
    finally:
        close = getattr(stream, "close", None)
        if close is not None:
            close()
    if not rows:
        return None
    prose = record_shape(rows)["free_text"]
    if not prose:
        return None
    values = [dataquality.text_of(v) for row in rows for v in row.values() if v is not None]
    if not full_defaults._is_text(values):
        return None
    return {
        "modality": "text",
        "path": str(path),
        "format": str(fmt.get("name") or "file"),
        "rows": len(rows),
        "prose_fields": prose,
    }


#: The argument names a tool takes a data file under. Read off the registry's
#: own schemas on the day this was written - `path` for `profile_dataset`,
#: `assess_the_data`, `profile_repository` and the counters; the rest are the
#: names a training tool would reasonably use - and only ever used to FIND a
#: path the thread already named, never to fill one in.
TRAINING_PATH_ARGUMENTS = ("path", "train_path", "data_path", "dataset_path", "train_file")

#: A file stem naming one of these is some other split, whatever else it says.
_OTHER_SPLITS = frozenset({"eval", "evaluation", "valid", "validation", "val", "test", "dev", "holdout"})


def _names_a_training_split(path: str) -> bool:
    """`train.jsonl`, `sft-train.csv`, `training_rows.parquet` - and not `train_eval.jsonl`.

    A FILE, by its suffix: a folder called `train/` is a folder of files and
    `profile_dataset` refuses a folder of splits. The stem's words are split on
    anything that is not a letter or a digit, so `train` has to be a word of
    the name rather than a substring of one (`constrained.jsonl` is not a
    training split). A name that also names another split is ambiguous and is
    not guessed at.
    """
    where = Path(str(path))
    if not where.suffix:
        return False
    words = {word for word in re.split(r"[^a-z0-9]+", where.stem.lower()) if word}
    return bool(words & {"train", "training"}) and not (words & _OTHER_SPLITS)


def training_file_on_record(thread_id: int | None) -> tuple[str, str | None] | None:
    """The training split this thread has already named, as it named it, and where that is.

    Returns `(as_named, resolved)` - the path exactly as the model passed it,
    which is what its next tool call can pass again (a relative path is read
    against the project's folder by the workspace), and the absolute path the
    tool resolved it to when the result says so - or None when no call on this
    thread named a training split that a tool then found.

    THE SAME READING `full_defaults._eval_file` DOES FOR THE EVAL FILE, for the
    training split, and for the reason the owner's thread 93 gave on
    2026-09-23. The walk stopped on `tabular_rows` - declared `source: inspect`,
    so the only honest way to settle it is an instrument reading the file - and
    the next-move line said "call state_facts NOW for tabular_rows", which the
    standing brief forbids for an inspect fact. The model looped on the
    contradiction for 471 reasoning events and called nothing. It had named
    the training split itself, `ml-principles-dataset/data/splits/train.jsonl`,
    to `profile_repository` - the wrong instrument, which answered "that is a
    file, not a repository" - so the file was on record and the line could have
    named it. This is what lets it.

    Read off the thread's own tool calls, any tool, because the point is the
    FILE the thread named and not which instrument it pointed at it; a call is
    paired with its result by the call id, and only a result that came back
    `ok` counts, so `data/splits/train.jsonl` read against the wrong folder -
    "there is nothing at that path" - is not a file on record. A
    `profile_dataset` call with `split: "train"` names its path the training
    split whatever the file is called. The newest wins, because the newest is
    the file the thread is working.
    """
    if thread_id is None:
        return None
    from app import events

    pending: dict[str, tuple[str, str]] = {}
    found: tuple[str, str | None] | None = None
    for row in events.since(f"thread:{int(thread_id)}", limit=100_000):
        payload = row.get("payload") or {}
        call_id = str(payload.get("id") or "")
        if row.get("kind") == "tool.call":
            arguments = payload.get("arguments") or {}
            if not isinstance(arguments, dict):
                continue
            for key in TRAINING_PATH_ARGUMENTS:
                named = arguments.get(key)
                if not isinstance(named, str) or not named.strip():
                    continue
                if _names_a_training_split(named) or (
                    key == "path" and str(arguments.get("split") or "").lower() == "train"
                ):
                    pending[call_id] = (named, key)
                    break
        elif row.get("kind") == "tool.result" and call_id in pending:
            named, key = pending.pop(call_id)
            if not payload.get("ok"):
                continue
            result = payload.get("result")
            resolved: str | None = None
            if isinstance(result, dict):
                moved = (result.get("workspace_resolved") or {}).get(key)
                if isinstance(moved, dict) and moved.get("to"):
                    resolved = str(moved["to"])
            if resolved is not None and not Path(resolved).exists():
                continue
            found = (named, resolved)
    return found


@tool(
    "state_facts",
    description=(
        "Record facts about this project. What they are worth depends on who "
        "is calling and the thread's permission. Facts recorded by the user in "
        "their own person count as STATED and can open gates marked "
        "`source: ask`. Under permission `full` (zero-ask), the person "
        "delegated those ask-facts to you: your recordings through this tool "
        "are STATED and open those gates — decide from measured data and call "
        "this tool; do not wait for Field cards or ask them again. Under ask/"
        "measure/write, model recordings count as ASSERTED and open nothing — "
        "write down what the user told you; do not invent measurements."
    ),
    schema={
        "type": "object",
        "properties": {
            "facts": {
                "type": "object",
                "description": (
                    "Fact name to value. Only names declared in the harness "
                    "fact ledger are accepted."
                ),
                "additionalProperties": True,
            }
        },
        "required": ["facts"],
    },
    reads=("facts",),
    writes=("facts",),
    provides=("ledger.facts.state",),
    label="Say this yourself",
    group="Decide",
    verb="record what you have already tried",
    order=21,
)
def state_facts(
    facts: dict[str, Any] | None = None,
    *,
    instrument: Instrument,
    ledger: diagnosis.Spec,
) -> dict[str, Any]:
    """One door, two meanings, and the door decides which.

    `measures=()`, so the instrument this handler holds can stamp nothing. Every
    row it writes carries an origin from the actor — unless this thread is on
    permission `full`, where the person delegated ask-facts to the model and
    those rows are recorded STATED so gates can open (AU1, 2026-09-15).
    """
    supplied = _unwrap_facts(facts)
    if not supplied:
        # A REFUSAL THAT NAMES THE NEXT MOVE. MEASURED 2026-09-13: told by
        # `run_diagnosis` to record the fact its walk was blocked on, the
        # owner's model called this with an empty `facts` object and got back
        # a sentence that taught it nothing - a wasted round, and the loop
        # again. The refusal now says the shape AND which facts would move
        # this thread's verdict, read from the same frontier run_diagnosis
        # reads.
        wanted: list[str] = []
        try:
            # ALIASED, AND THAT IS NOT A STYLE CHOICE. `from app import
            # diagnosis` here would make `diagnosis` a LOCAL name for this
            # whole function, and the module-level import three hundred lines
            # up would stop resolving - which is exactly what happened when
            # this branch was first written: every non-empty call to this tool
            # raised UnboundLocalError at `diagnosis.validate_facts` below.
            from app import asking as _asking
            from app import diagnosis as _diagnosis
            from app.tools import evidence as _evidence

            if ledger.as_written == _asking.the_ledger_this_module_is_written_for().as_written:
                sheet, _ = _evidence.assemble_facts(
                    instrument.thread_id, {}, instrument.actor, ledger=ledger
                )
                edge = _asking.frontier(_diagnosis.diagnose(sheet, ledger))
                # THE SAME GAP-FIRST RULE `run_diagnosis` USES, and it has to
                # be the same or the refusal names a different blocker than
                # the verdict does. `first_answerable` steps over an entry
                # whose only unknown is a gap; the gap is exactly what this
                # refusal exists to name.
                first = edge.entries[0] if edge.entries else None
                entry = first if (first is not None and first.gaps) else (
                    edge.first_answerable or first
                )
                wanted = [gap.fact for gap in getattr(entry, "gaps", ())][:3]
        except Exception:  # noqa: BLE001 - a refusal must never raise its own
            wanted = []
        example = wanted[0] if wanted else "target_score"
        accepted_shape = {"facts": {example: "<your answer>" if wanted else 0.85}}
        return {
            "ok": False,
            "error": "nothing_supplied",
            "detail": (
                "No facts were given, so nothing was recorded. Send exactly this shape, "
                f"your value in place of the example: {json.dumps(accepted_shape)}."
            ),
            "accepted_shape": accepted_shape,
            "the_walk_is_blocked_on": wanted,
            "for_this_tool": (
                f'Send {{"facts": {{"{wanted[0]}": "<your answer>"}}}} - nothing in this '
                f"harness measures {wanted[0]}, so deciding it is the move."
                if wanted
                else "Send the facts you have actually established, under `facts`."
            ),
        }

    # THE LEDGER THIS CONVERSATION IS RUNNING. A person saying something true
    # about their agent, in a thread whose ledger is the AI-engineering one, was
    # refused against the ML ledger's 69 fact names with a message naming a file
    # they were never talking about.
    spec = ledger
    # ONE WRONG NAME USED TO THROW THE WHOLE BATCH AWAY. Max's thread 78,
    # 2026-09-18: nine facts sent twice, `data_location` and then `corpus_rows`
    # not declared, and every time the eight declared ones - target_score,
    # task_family among them - went with it. The turn then ended by asking
    # the person for exactly the facts it had already tried to record. Now
    # each fact is checked on its own: the declared ones are recorded and the
    # rejected ones are named, with the same help as before.
    accepted: dict[str, Any] = {}
    rejected: dict[str, str] = {}
    for name, value in supplied.items():
        try:
            diagnosis.validate_facts({name: value}, spec)
        except diagnosis.FactError as one:
            rejected[name] = str(one)
        else:
            accepted[name] = value
    if rejected and accepted:
        supplied = accepted
    try:
        if not accepted:
            diagnosis.validate_facts(supplied, spec)
    except diagnosis.FactError as error:
        # THE REFUSAL NAMES THE DOOR. Watched against the live model:
        # granite4-hermes calls this tool with `answer_given`,
        # `hardware_is_sufficient_for_training` and `you_have_an_eval_set`, the
        # ledger correctly refuses each one, and the old reply said only that
        # they were not declared facts. That is true and it is a wall with no
        # door: the round is spent, the user watches a failed step go by, and
        # the next guess is no better informed than the first.
        # `evidence.fact_name_help` answers out of the ledger's own declarations
        # and the registry's own `measures=`, so what comes back is legal fact
        # ids, what each one accepts, and the tool that would settle it.
        #: AND IT SHOWS THE CORRECTED CALL. MEASURED 2026-09-13, the owner's
        #: model, third live run: it sent `{"classes_n": "60", "eval_size_n":
        #: "40"}` - the right facts, quoted, because a model writing JSON
        #: quotes things - and `{"target_score": "unknown"}`, which is it
        #: saying it does not know. Both were refused with a true sentence
        #: that named no next move, and neither was retried. So: a value that
        #: is the same number wearing quotes is written out unquoted here, and
        #: a fact the caller does not know is pointed at the door the engine
        #: already has for that - leave it out, and it comes back as an
        #: assumption on the next verdict. Nothing is coerced and nothing is
        #: recorded: the refusal stands, and it teaches.
        fixed: dict[str, Any] = {}
        unknown: list[str] = []
        for name, value in supplied.items():
            if not isinstance(value, str):
                continue
            text = value.strip()
            if text.lower() in ("unknown", "none", "null", "n/a", "not known", "i don't know"):
                unknown.append(name)
                continue
            try:
                fixed[name] = int(text) if text.lstrip("-").isdigit() else float(text)
            except ValueError:
                continue
        out = {
            "ok": False,
            "error": "rejected_fact",
            "detail": str(error),
            **evidence.fact_name_help(supplied, ledger=spec),
        }
        if fixed:
            out["send_this_instead"] = {"facts": fixed}
            out["for_this_tool"] = (
                "Those are numbers, and they arrived as strings. Send them again as "
                f"`send_this_instead` has them: {{'facts': {fixed}}}."
            )
        if unknown:
            out["you_do_not_know"] = unknown
            out["if_you_do_not_know"] = (
                "A fact you cannot answer is LEFT OUT, never sent as the word 'unknown'. "
                "The engine applies the ledger's own default, records the origin as "
                "DEFAULTED, and shows it to you as an assumption on the next verdict. "
                "If the person is the only one who can settle it, ask them for exactly "
                "that one thing and stop."
            )
        return out

    # AU1 — permission `full` is zero-ask bypass: the person opted in, so a
    # model's state_facts answers are STATED and can open source:ask gates.
    origin = instrument.supplied_origin
    how = f"the {instrument.actor} said so, through state_facts"
    if instrument.actor == evidence.MODEL and instrument.thread_id is not None:
        from app import autonomy as _autonomy
        from app import events as _events

        thread = _events.get_thread(instrument.thread_id) or {}
        if _autonomy.normalise(str(thread.get("permission") or "")) == "full":
            origin = evidence.STATED
            how = (
                "full mode: the person delegated this decision to the model "
                "via state_facts"
            )

    # G1 - A CLAIM DOES NOT RESTATE AN INSTRUMENT. Max's thread 93, 2026-09-23,
    # permission `full`: the harness had MEASURED eval_size_n, the hardware and
    # the baseline (rows 922-930), and the model filed every one of them again
    # through this door as STATED (rows 934-940) - "full mode: the person
    # delegated this decision to the model". The person delegated DECISIONS; a
    # reading is not one. The same value is a round spent saying what the
    # harness already knew, so it is answered and nothing is filed; a different
    # value is a claim trying to outrank a measurement (`app/provenance.py`'s
    # whole argument), so it is refused with both numbers and the instrument.
    # The other facts in the call are unaffected.
    already: list[dict[str, Any]] = []
    refused: dict[str, str] = {}
    to_file: dict[str, Any] = {}
    measured_now = _measured_on_this_thread(instrument.thread_id)
    for name, value in supplied.items():
        row = measured_now.get(name)
        if row is None:
            to_file[name] = value
            continue
        reading = json.dumps(row["value"], default=str)
        by = row.get("tool") or "an instrument"
        if _same_reading(value, row["value"]):
            already.append(
                {"fact": name, "value": row["value"], "tool": row.get("tool"), "how": row.get("how")}
            )
            continue
        how_it = " ".join(str(row.get("how") or "").split())
        refused[name] = (
            f"{name}: you said {json.dumps(value, default=str)}, and {by} measured "
            f"{reading}" + (f" ({how_it[:160]})" if how_it else "") + ". A claim "
            f"cannot outrank a measurement, so nothing was filed for {name}. If what "
            f"it measured has changed, run {by} again and its reading replaces this one."
        )

    # G2 - A MODALITY IS INSPECTED BEFORE IT IS BELIEVED. The same thread: the
    # model stated `modality` "tabular" for the eval file measure_eval_set had
    # just counted - JSONL whose rows are a prose question and a record of
    # prose answers - and the walk went down the tabular branch and asked for
    # `tabular_rows` for a dataset with no table. When the file on record can
    # be opened and it contradicts the statement, the statement is refused
    # with the file named, and what the file says is filed in its place: as
    # the harness's DEFAULTED row, the ledger's word for a value derived by a
    # written rule (`app/full_defaults.py` files the same fact the same way),
    # because no instrument declares `modality` and this tool - which reads
    # the ledger above - may never hold one that stamps. Nothing on record, or
    # a file that settles nothing, and the statement stands as before.
    inspected: dict[str, Any] = {}
    if "modality" in to_file and instrument.thread_id is not None:
        from app import full_defaults

        said = str(to_file["modality"])
        found = full_defaults._eval_file(int(instrument.thread_id))
        seen = inspect_modality(found[0]) if found else None
        if seen is not None and said.strip().lower() not in TEXT_ROWS_ADMIT:
            to_file.pop("modality")
            kind = "a table" if said.strip().lower() in ("tabular", "timeseries") else said
            refused["modality"] = (
                f"modality: you said {said!r}, and the file on record at {seen['path']} "
                f"is {seen['format'].upper()} whose rows are text fields - "
                f"{', '.join(seen['prose_fields'])} carry prose in the {seen['rows']} rows "
                f"read, and none names an image, audio or video file; that is a text "
                f"dataset, not {kind}. Nothing was filed from what you said."
            )
            how_seen = (
                f"Derived by inspection when state_facts was told {said!r}: read "
                f"{seen['rows']} rows of {seen['path']} ({seen['format']}); the fields "
                f"{', '.join(seen['prose_fields'])} are prose by the rule the fields "
                "grader uses, and no value names an image, audio or video file, so "
                "the modality is text."
            )
            earlier = [r for r in evidence.rows_for(instrument.thread_id) if r["fact"] == "modality"]
            if not any(str(r["value"]) == "text" for r in earlier):
                evidence.record(
                    fact="modality",
                    value="text",
                    origin=evidence.DEFAULTED,
                    actor=evidence.HARNESS,
                    how=how_seen,
                    thread_id=int(instrument.thread_id),
                    ledger=spec,
                )
            inspected = {"modality": "text", "how": how_seen}
            outranked = [
                r for r in earlier
                if r["origin"] in (evidence.STATED, evidence.ASSERTED) and str(r["value"]) != "text"
            ]
            if outranked:
                refused["modality"] += (
                    f" An earlier statement of {str(outranked[-1]['value'])!r} is still on "
                    "this thread and outranks a derived value; send "
                    '{"facts": {"modality": "text"}} to replace it.'
                )

    recorded = []
    for name, value in to_file.items():
        if origin == evidence.STATED and instrument.actor == evidence.MODEL:
            evidence.record(
                fact=name,
                value=value,
                origin=origin,
                actor=instrument.actor,
                how=how,
                tool="state_facts",
                thread_id=instrument.thread_id,
                ledger=spec,
            )
        else:
            instrument.supplied(name, value, how=how)
        admissible = spec.admissible_for(name)
        recorded.append(
            {
                "fact": name,
                "value": value,
                "origin": origin,
                "declared_source": spec.facts[name].get("source"),
                "can_open_a_gate": origin in admissible,
                "if_not": (
                    ""
                    if origin in admissible
                    else spec.substantiation(name).strip()
                ),
                "settled_by": evidence.resolves(name, spec),
            }
        )

    # A FACT NO GATE READS IS NOT HELD BY ITS ORIGIN. Max's run of 2026-09-21:
    # the model stated `modality`, the walk was waiting on exactly that, and
    # the reply said "modality cannot, at this origin - modality needs
    # measure_eval_set" - which the model read as the tool refusing it, while
    # measure_eval_set had already run and does not measure modality. The
    # sentence was about gates, and no gate reads `modality`: node conditions
    # route on the value whatever its origin, so the walk moved on the moment
    # it was recorded. Such a fact is said to route, and nothing else.
    for row in recorded:
        row["routes_the_walk_now"] = (
            not row["can_open_a_gate"] and not evidence._a_gate_reads(row["fact"], spec)
        )
    opens = [r["fact"] for r in recorded if r["can_open_a_gate"]]
    routes_now = [r["fact"] for r in recorded if r["routes_the_walk_now"]]
    holds = [
        r["fact"] for r in recorded if not r["can_open_a_gate"] and not r["routes_the_walk_now"]
    ]
    lines = (
        [f"Recorded {len(recorded)} fact(s) as {origin}."]
        if recorded or not (already or refused)
        else ["Nothing new was recorded."]
    )
    for row in already:
        lines.append(
            f"{row['fact']}: already measured: {json.dumps(row['value'], default=str)} "
            f"by {row.get('tool') or 'an instrument'} - nothing to do."
        )
    for name in sorted(refused):
        lines.append("REFUSED " + refused[name])
    if inspected:
        lines.append("The harness filed modality as text, from the file itself.")
    if routes_now:
        lines.append(
            f"{', '.join(sorted(routes_now))} "
            + ("is" if len(routes_now) == 1 else "are")
            + " on the sheet now: no gate reads "
            + ("it" if len(routes_now) == 1 else "them")
            + ", and the walk routes on "
            + ("it" if len(routes_now) == 1 else "them")
            + " from here - run run_diagnosis to see where it goes."
        )
    if rejected:
        lines.append(
            f"NOT recorded: {', '.join(sorted(rejected))} - "
            + "; ".join(f"{name}: {why[:120]}" for name, why in sorted(rejected.items()))
            + ". The rest landed."
        )
    if opens:
        lines.append(f"{', '.join(sorted(opens))} can now open the gate that reads it.")
    if holds:
        # AND WHAT WOULD SETTLE IT, IN THE SENTENCE. This said "Each row says
        # what would settle it" and left the route in `recorded[i].settled_by`,
        # one level down. Max's run of 2026-09-19/20 stated `task_family`
        # nineteen times, was told nineteen times that it "cannot, at this
        # origin", and never read the row: the summary is what a model acts on.
        # The route comes from `evidence.resolves`, which already had it.
        routes: list[str] = []
        for row in recorded:
            if row["can_open_a_gate"] or row["routes_the_walk_now"]:
                continue
            settles = row.get("settled_by") or {}
            # `tool` is an instrument that STAMPS this fact; `derived_by` is a
            # tool that settles a different fact the harness then derives this
            # one from. Both are a next call, and neither was in the sentence.
            by_tool = settles.get("tool") or settles.get("derived_by")
            if by_tool and by_tool != "state_facts":
                routes.append(f"{row['fact']} needs {by_tool}")
        lines.append(
            f"{', '.join(sorted(holds))} cannot, at this origin"
            + (" - " + "; ".join(routes) + "." if routes else ". Each row says what would settle it.")
        )
    out = {
        # A call whose every fact was refused landed nothing, and `ok` says so;
        # one that was only told "already measured" had nothing to land.
        "ok": bool(recorded or already or inspected or not refused),
        "summary": " ".join(lines),
        "origin": origin,
        "actor": instrument.actor,
        "recorded": recorded,
    }
    if already:
        out["already_measured"] = already
    if refused:
        out["refused"] = refused
    if inspected:
        out["inspected"] = inspected
    if rejected:
        out["rejected"] = rejected
        out.update(evidence.fact_name_help(rejected, ledger=spec))
    return out


__all__ = [
    "BASELINE_SYSTEM",
    "DEFAULT_BASELINE_SAMPLE",
    "MAX_BASELINE_SAMPLE",
    "measure_baseline",
    "measure_eval_set",
    "normalise_answer",
    "state_facts",
]
