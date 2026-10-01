"""Generate preference pairs from rows that already exist, and account for them.

STAGE 4 AND THE REPORT LIVE HERE, AND THEY ARE PURE. `stamp_the_provenance`
returns a row; it does not write one. A stamper that also wrote would be a
function nobody could exercise without a filesystem, and this is the function
whose output a skeptic reads.

THE GOVERNING RULE, from `10-Signals/specs/synthetic-data.md`:

    the `prompt` comes from a real row he already has; the `chosen` is that real
    row's real answer, copied verbatim; only the `rejected` is generated, and
    only as a degradation of the real answer under a named, closed list of
    degradations.

That rule is not enforced by this docstring. It is enforced at the row by
`scripts/check_that_a_tool_call_could_run.py::why_this_preference_pair_is_malformed`,
which compares `chosen` against the source file's own answer byte for byte, and
by `DEGRADATIONS` below, which is a closed tuple rather than an instruction to a
model to "make it worse".

THE FOUR STAGES, AND WHICH OF THEM A TEST CAN REACH. Stage 1 reads the seed
file; stage 2 is `check_that_a_tool_call_could_run.py`, its own module; stage 3
asks a model and then asks a judge; stage 4 stamps. Stages 2 and 4 are pure and
are exercised by `tests/` in under a second with nothing installed - the reason
`recipes/hf-peft-dpo` gives for splitting out `adapter_keys_in`: the decision is
the part that gets written wrong. Stage 3 needs a model on the other end of a
socket, so what is tested there is the parsing and the refusals, against a
scripted adapter, and the model call itself is proven by running it.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

#: `scripts/` is not a package and this file is run directly, so the repository
#: root has to be on the path before `app` can be imported. The same three lines
#: open `scripts/capture_datawork_fixtures.py`; guarded, so importing this
#: module from `tests/` (where the root is already there) changes nothing.
REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ---------------------------------------------------------------------------
# The closed list
# ---------------------------------------------------------------------------

#: The named ways a real answer may be degraded into a `rejected` one.
#:
#: A TUPLE, AND SHORT, ON PURPOSE. The spec: *"an open-ended 'make it worse'
#: instruction is the fabrication door."* A generator told to write a worse
#: answer writes a DIFFERENT answer, and a different answer is a new claim about
#: the world - which is the one thing a corpus built out of real rows was
#: supposed to avoid.
#:
#: ONE ENTRY, BECAUSE ONE IS ALL THAT HAS BEEN DECIDED. The spec names exactly
#: this one and files the rest under *"Open questions for Max, not for the
#: builder"*: *"Which degradations belong on the closed list for `rejected`? The
#: list should be his, written down, and small."* Adding a second here would be
#: inferring an answer to a question that was explicitly reserved. When he names
#: them, they go here, each with the sentence that says what it does to an
#: answer.
DEGRADATIONS: tuple[str, ...] = ("over_promises_beyond_the_source",)

#: What each degradation instructs, in the words the generator is shown. The key
#: set is `DEGRADATIONS` and a test holds them equal, so a name added to one
#: without the other is a failure rather than a silently unprompted run.
WHAT_EACH_DEGRADATION_DOES: dict[str, str] = {
    "over_promises_beyond_the_source": (
        "Rewrite the answer so it promises more than the source answer allows: "
        "drop a condition, widen a limit, or state as unconditional something "
        "the source made conditional. Change nothing else. Do not add a new "
        "fact, a number, or a name that is not already in the source answer."
    ),
}

# ---------------------------------------------------------------------------
# The tag wall 8 reads
# ---------------------------------------------------------------------------

#: The three keys, spelled the way `app/tools/datawork.py:1553-1555` already
#: spells them when `synthesize_rows` writes a file.
#:
#: `app/dataquality.py::is_synthetic_row` reads exactly the first of these, and
#: reads it truthily so it survives a round trip through CSV. Get it wrong and
#: `synthetic_census` reports `clean: true`, wall 8 does not fire, and a
#: generated file opens a gate - the failure `docs/PHASES.md` records as DONE on
#: 2026-08-27, which must stay done.
TAG_KEYS: tuple[str, str, str] = (
    "synthetic",
    "synthetic_source_index",
    "synthetic_seed",
)

#: Every check `check_that_a_tool_call_could_run.py` can perform. A row's
#: provenance names the SUBSET that ran on it - four of these are tool-call
#: checks and a preference pair never meets them - so a reader knows which
#: questions were asked of that row and, by omission, which were not.
WHAT_THE_VALIDATOR_CHECKED: tuple[str, ...] = (
    "required_present",
    "no_unknown_params",
    "types_match",
    "enums_match",
    "chosen_is_the_source_answer",
    "rejected_adds_no_new_specifics",
)

#: The subset of the above that a PREFERENCE PAIR meets. The other four are
#: tool-call checks. Named against `WHAT_THE_VALIDATOR_CHECKED` rather than
#: written out twice, so a rename over there is a failure here rather than a
#: provenance block that quietly lists a check nothing performs.
WHAT_A_PREFERENCE_PAIR_IS_CHECKED_FOR: tuple[str, ...] = tuple(
    name for name in WHAT_THE_VALIDATOR_CHECKED
    if name in ("chosen_is_the_source_answer", "rejected_adds_no_new_specifics")
)
assert WHAT_A_PREFERENCE_PAIR_IS_CHECKED_FOR, (
    "chosen_is_the_source_answer left WHAT_THE_VALIDATOR_CHECKED; a preference "
    "row would now claim no check ran on it at all"
)

#: RETIRED 2026-09-05. Kept as a name so a reader meeting it in an old run
#: report knows what it was and why it went: it refused a judge reply under
#: forty characters, it would have refused 0 of the 111 replies on record, and
#: the fabrications it was meant to catch averaged 124 characters. See
#: `why_this_row_must_not_ship`.
#:
#: A verdict with no account is a verdict nobody can check. Refusal 2 of the
#: four - and it applies to a DROP as much as to a KEEP, because both are
#: readings somebody may want to argue with.
FEWEST_REASONING_CHARS = 40


class TheStamperHasABug(Exception):
    """Raised when a stamped row would not carry all three tag keys.

    RAISES RATHER THAN DROPS, which is refusal 4 of the four the spec lists.
    The other three describe a row that came back wrong from a model; this one
    describes a row this module built wrong, and a builder's own defect that
    presented as a slightly smaller output file would be a defect nobody found.
    """


def stamp_the_provenance(
    row: Mapping[str, Any],
    *,
    generator: Mapping[str, Any],
    validator: Mapping[str, Any],
    judge: Mapping[str, Any],
    source: Mapping[str, Any],
    script: str,
    seed: str,
    now: str,
) -> dict[str, Any]:
    """Return the row with its tag and its provenance block. Pure, so it is tested.

    It does NOT write. Writing is the driver's job.

    `origin` is `ASSERTED` and there is no parameter that can make it anything
    else. `app/diagnosis.py` on that origin: *"A model said so, or nobody said
    where it came from."* `MEASURED` is what `Instrument.measured` mints and it
    is walled eight ways; `STATED` is the user speaking in their own person. A
    generated row is a model's assertion, and writing anything stronger here
    would be exactly the laundering `app/tools/evidence.py` exists to refuse.

    `actor` is `evidence.MODEL`, so `SUPPLIED_ORIGIN[MODEL] == ASSERTED` makes
    the two fields agree by construction rather than by care.
    """
    from app.tools import evidence

    stamped: dict[str, Any] = dict(row)
    stamped["synthetic"] = True
    stamped["synthetic_source_index"] = source["row_index"]
    stamped["synthetic_seed"] = seed

    same_weights = str(generator.get("model") or "") == str(judge.get("model") or "")

    stamped["provenance"] = {
        "origin": evidence.ASSERTED,
        "actor": evidence.MODEL,
        "tool": script,
        "how": how_this_row_came_to_exist(
            generator_model=str(generator.get("model") or "an unnamed model"),
            source=source,
            degradation=str(generator.get("degradation") or ""),
        ),
        "created_at": now,
        "generator": dict(generator),
        "validator": dict(validator),
        "judge": {**dict(judge), "same_weights_as_generator": same_weights},
        "source": dict(source),
    }

    missing = [key for key in TAG_KEYS if key not in stamped]
    if missing:
        raise TheStamperHasABug(
            f"a stamped row must carry {list(TAG_KEYS)}; it is missing {missing}. "
            "Without them app/dataquality.py::is_synthetic_row reads the row as "
            "real and wall 8 does not fire."
        )
    return stamped


def how_this_row_came_to_exist(
    *,
    generator_model: str,
    source: Mapping[str, Any],
    degradation: str,
) -> str:
    """The `how` sentence: what was done, and what was NOT.

    `Instrument.measured`'s docstring: *"`how` is not decoration. It is the
    sentence the interface shows next to the number."* It ends the same way
    every time, because the one thing a reader of a generated file might assume
    is the one thing that is not true of any row in it.
    """
    where = f"row {source.get('row_index')} of {source.get('path')}"
    under = f" under the degradation {degradation!r}" if degradation else ""
    return (
        f"{generator_model} was shown {where} and asked for one worse answer to "
        f"the same question{under}. The prompt and the chosen answer are that "
        "row's own, copied. Only the rejected answer was written by a model. "
        "Nothing here was measured."
    )


def _the_reply_is_only_a_verdict(reply: str) -> bool:
    """Did the judge answer with nothing but KEEP or DROP?

    Not a length test. `read_the_judges_verdict` reads the LAST verdict word,
    so a reply that is only that word is perfectly readable and slips past the
    unreadable check - while having answered a rubric that asks for a line of
    reasoning first with no line at all.
    """
    import re as _re

    left = _re.sub(r"\b(KEEP|DROP)\b", " ", str(reply or ""), flags=_re.IGNORECASE)
    return not _re.sub(r"[^A-Za-z0-9]+", "", left)


def why_this_row_must_not_ship(stamped: Mapping[str, Any]) -> list[str]:
    """The per-row half of the four refusals. Empty means the row may be written.

    Refusals 1 and 2 are here because they are about ONE row. Refusal 3 (the
    source file changed under the run) and the unreadable-verdict SHARE are
    about the run, stop it rather than the row, and belong to the driver.
    Refusal 4 is `TheStamperHasABug`, raised above.
    """
    provenance = stamped.get("provenance") or {}
    judge = provenance.get("judge") or {}
    reasoning = str(judge.get("reasoning") or "").strip()
    faults: list[str] = []

    if judge.get("verdict") is None:
        faults.append(
            "the judge's verdict was unreadable; a row nobody graded is not a "
            "row that passed"
        )
    #: THE REASONING FLOOR WAS REMOVED HERE ON 2026-09-05, measured rather than
    #: argued. It refused a row whose judge reasoning ran under forty characters,
    #: because "a verdict with no account is a verdict nobody can check".
    #:
    #: Two facts retired it. The account can be FABRICATED - 19 of 19 KEEPs in
    #: the sentinel-N run named a clause the rewrite still contained, none of
    #: them short - so length measures verbosity. And across every recorded
    #: `JUDGE_SYSTEM` reply this repository holds, 111 rows over two runs, the
    #: floor would have refused ZERO: the shortest reply is 54 characters and
    #: all 23 wrong verdicts ran 99 or more. A check that has never fired on any
    #: recorded run is carrying a theory rather than a load.
    #:
    #: Preregistered in `docs/judge_runs/2026-09-05-retire-the-reasoning-floor-prereg.md`,
    #: which fixed "removed if it refuses zero rows across all 111" before the
    #: counting. This change stated its own test coverage WRONG TWICE. It
    #: said no test asserted the floor, then said one did. TWO did, in two
    #: files - `test_a_keep_with_no_reasoning_is_dropped` and
    #: `test_a_keep_with_no_account_stops_the_row` - and both wrong counts
    #: came from grepping (first for the constant, then for a phrase in one
    #: file) instead of enumerating the callers of this function. The gate
    #: found the second one. Both are retargeted, neither deleted.
    #:
    #: The reasoning is still RECORDED on every row. It is simply not a gate,
    #: and per this repository's law it is not evidence: the account that
    #: belongs beside a verdict is the diff from `what_actually_changed.py`.
    #:
    #: WHAT REPLACES IT, AND WHY IT IS A DIFFERENT CHECK. Removing the floor
    #: was going to let a reply of the single word "KEEP" ship - a case an
    #: existing test already covered, which I claimed in a first draft nothing
    #: tested. That is not a verbosity failure and no length decides it: the
    #: rubric asks for "a single line of reasoning, then the word", and a reply
    #: that is ONLY the word did not follow the rubric at all. So the check is
    #: now about FORMAT, and it fires on nothing else - the shortest real reply
    #: on record, 54 characters, passes it, and so would a four-word one.
    #:
    #: This replacement is a design choice, NOT a measured result. The
    #: measurement retired the length floor; nothing measures how often a bare
    #: verdict occurs, because it never has on the 111 replies recorded.
    if judge.get("verdict") is not None and _the_reply_is_only_a_verdict(reasoning):
        faults.append(
            "the judge replied with a bare verdict and no account at all; the "
            "rubric asks for a line of reasoning first, so this reply did not "
            "follow it and the row is not graded"
        )
    return faults


def sha256_of(path: Path) -> str:
    """The source file's digest, read in blocks so a large file is not resident.

    Refusal 3 compares this at write time against what was read at start time.
    A seed file that changed mid-run makes every `synthetic_source_index` in
    the run point somewhere else, and there is no repair for that afterwards -
    only a stop.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_of_text(text: str) -> str:
    """The digest of a prompt, so two runs can be compared without storing it."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def the_kept_and_dropped_report(
    *,
    generated: int,
    validator_dropped: Mapping[str, int],
    judge_dropped: int,
    generator_failed: int = 0,
    judge_unreadable: int,
    kept: int,
    distinct_sources: int,
    source_rows: int,
    control: Mapping[str, Any] | None,
    generator_model: str,
    judge_model: str,
) -> dict[str, Any]:
    """Everything a skeptic needs, and nothing that reads as a conclusion.

    THE REPORT NEVER PRINTS A BARE KEEP RATE. It prints the two factors, because
    `keep_rate = (1 - validator_drop) x (1 - judge_drop)` and the merged number
    hides the only information that says what to do next: a run that is 95%
    validator-pass and 42% judge-pass has a prompting problem, and one that is
    42% validator-pass and 95% judge-pass has a format problem. They are
    different repairs and the same 40%.

    `control` is `None` until the control run has been done, and it renders as
    the absence it is rather than as a zero. It is the whole answer to "is 40%
    good": the same filter over rows already trusted. Without it the keep rate
    is a number about nothing.
    """
    from app.tools import evals

    validator_total = sum(int(count) for count in validator_dropped.values())
    #: A row the generator never produced was never offered to the validator, so
    #: it is neither a validator pass nor a validator fault. Counting it as
    #: either would make an endpoint that went down look like a prompting
    #: problem, which is the wrong repair.
    validator_saw = generated - generator_failed
    report: dict[str, Any] = {
        "generated": generated,
        "generator": {"failed": generator_failed},
        "validator": {
            "offered": validator_saw,
            "dropped": validator_total,
            "by_fault": dict(validator_dropped),
            "pass_rate": _share(validator_saw - validator_total, validator_saw),
        },
        "judge": {
            "dropped": judge_dropped,
            "unreadable": judge_unreadable,
            "kept": kept,
            "pass_rate": _share(kept, validator_saw - validator_total),
            #: STATED, from this file's own rubric, not measured. A reader who
            #: sees a high judge pass rate will read it as "these rows are
            #: faithful". It does not say that. `what_the_judge_is_shown` tells
            #: the judge in as many words that removing a condition or widening
            #: a limit IS the degradation and must never be dropped for - so a
            #: row that over-promises passes this filter BY DESIGN, because
            #: over-promising is what the generator was asked to do.
            #:
            #: Measured 2026-09-05 on a separate faithfulness rubric: adding one
            #: sentence about dropped limits took a judge from 4/9 to 9/9 on
            #: widened promises while keeping 8/8 surface-only rewrites. That
            #: clause belongs to the instrument that asks "is this true to its
            #: source" and NOT here - see
            #: docs/judge_runs/2026-09-05-does-the-rubric-decide-deletions-result.md.
            "screens_for": "facts the rewrite ADDED that the real answer does not contain",
            "does_not_screen_for": (
                "promises the rewrite widened by dropping a condition - that is the "
                "named degradation and the rubric instructs the judge to keep it"
            ),
            "provenance": "STATED: read from this file's rubric, not measured here",
        },
        "kept": kept,
        "keep_rate": _share(kept, generated),
        "resolution": evals.resolution_for(kept, generated) if generated else None,
        "diversity": {
            "distinct_source_rows_kept": distinct_sources,
            "source_rows_available": source_rows,
        },
        "control": dict(control) if control is not None else None,
        "who_judged": {
            "generator_model": generator_model,
            "judge_model": judge_model,
            "same_weights": generator_model == judge_model,
        },
        "human": {"sample_drawn": None, "kept_rows_read": 0, "dropped_rows_read": 0},
    }
    if report["control"] is None:
        report["control_note"] = (
            "No control run. The same validator and the same judge have not been "
            "run over rows already trusted, so this keep rate cannot be read as a "
            "fact about the generator rather than about the filter."
        )
    if report["who_judged"]["same_weights"]:
        report["who_judged"]["note"] = (
            "The judge and the generator are the same weights. Its agreement is "
            "not independent evidence."
        )
    return report


def _share(part: int, whole: int) -> float | None:
    """A rate, or `None` when there is no denominator. Never a zero standing in.

    A run that generated nothing has no keep rate. Printing `0.0` there would be
    the invented number this repository refuses everywhere else.
    """
    if whole <= 0:
        return None
    return round(part / whole, 4)


# ---------------------------------------------------------------------------
# Stage 1 - the rows that already exist
# ---------------------------------------------------------------------------


def read_the_source_rows(
    path: Path, *, question_field: str, answer_field: str
) -> list[dict[str, Any]]:
    """Every usable row of the seed file, carrying the index it came from.

    THE INDEX TRAVELS WITH THE ROW because sampling puts source row 2 at output
    position 7, and an index that counted outputs would send every reviewer to
    the wrong line of the seed file. It is the line number in the file, counted
    from zero over ALL lines, so a reader can find it with `sed -n`.

    A row missing either field is skipped and counted, not silently dropped:
    the count reaches the report, where a seed file that is mostly unusable is
    a fact about the run rather than a smaller number nobody can explain.
    """
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        question = str(record.get(question_field) or "").strip()
        answer = str(record.get(answer_field) or "").strip()
        if not question or not answer:
            continue
        rows.append({"row_index": index, "question": question, "answer": answer})
    return rows


# ---------------------------------------------------------------------------
# Stage 3 - the two model calls
# ---------------------------------------------------------------------------

#: How the generator is addressed. It is shown the real question and the real
#: answer and asked for ONE rewrite of the answer it was given. It is never
#: asked a question of its own, because a model answering the question would be
#: writing a new answer, and a new answer is a new claim about the world.
GENERATOR_SYSTEM = (
    "You rewrite one answer into a worse version of itself. You are given a "
    "customer's question and the answer a real shop gave. Return ONLY the "
    "rewritten answer - no preamble, no explanation, no quotation marks. Keep "
    "it about the same length and in the same voice."
)

#: How the judge is addressed. It grades ONE thing: did the rewrite degrade the
#: real answer in the named way WITHOUT reaching outside it. A rewrite that is
#: merely different, or that invented a fact, is a DROP even though it is worse.
#:
#: THE PROHIBITION IS SCOPED TO ADDITIONS, AND IT WAS NOT AT FIRST. Measured on
#: the first ten-row run (2026-09-03, `runs/synthetic-granite42-2026-09-03-a`):
#: the judge dropped the cleanest pair in the set - the returns answer, whose
#: rewrite removed the shop's refusal of marked books - and said why in its own
#: words: *"introducing a new policy (returning even if underlined/highlighted)
#: that was not present in the original answer, which violates the 'no new
#: policy' constraint."* It was right about the instruction it was given. For
#: `over_promises_beyond_the_source`, removing a condition IS a change of
#: policy, so "be worse by widening a limit" and "state no policy not in the
#: source" were the same sentence pointing in opposite directions. The judge
#: applied the prohibition and ignored the degradation, which is the correct
#: reading of a self-contradicting instruction.
#:
#: A KEEP RATE FROM BEFORE THIS CHANGE AND ONE FROM AFTER ARE NOT COMPARABLE as
#: evidence about the generator. The difference measures the contradiction, not
#: the rows.
JUDGE_SYSTEM = (
    "You grade one rewritten answer. Reply with a single line of reasoning, "
    "then the word KEEP or the word DROP on its own line at the end."
)

#: The share of unreadable verdicts above which the run stops rather than
#: continuing to produce rows nobody graded. `_read_verdict` in
#: `app/tools/evals.py` makes the same argument for a single run: *"`None` is
#: not a third grade and it is not counted as a failure: it stops the run."*
MOST_UNREADABLE_SHARE = 0.10

#: Below this many rows, a share is noise and the run is not stopped by one bad
#: reply. Ten rows with one unreadable verdict is 10%, and stopping there would
#: make the spec's own first run unrunnable.
FEWEST_ROWS_BEFORE_A_SHARE_MEANS_ANYTHING = 20


def what_the_generator_is_shown(
    *, question: str, answer: str, degradation: str
) -> str:
    """The generator's user message: the real pair, and the named degradation."""
    return (
        f"Question: {question}\n"
        f"Answer the shop gave: {answer}\n\n"
        f"{WHAT_EACH_DEGRADATION_DOES[degradation]}"
    )


def what_the_judge_is_shown(
    *, question: str, chosen: str, rejected: str, degradation: str
) -> str:
    """The judge's user message. It grades the degradation, not the writing."""
    return (
        f"Question: {question}\n"
        f"The real answer: {chosen}\n"
        f"The rewritten answer: {rejected}\n\n"
        f"The rewrite was supposed to be worse in exactly this way: "
        f"{WHAT_EACH_DEGRADATION_DOES[degradation]}\n\n"
        "Answer KEEP only if BOTH are true.\n"
        "(1) The rewritten answer is worse in that named way.\n"
        "(2) Every fact, number, name, price and place in the rewritten "
        "answer already appears in the real answer.\n\n"
        "JUDGE (2) ON WHAT WAS ADDED, NEVER ON WHAT WAS DROPPED. Removing a "
        "condition, widening a limit, or making something unconditional is "
        "the degradation itself - it is what the rewrite was asked for, and "
        "it is never 'introducing a new policy'. Answer DROP if the rewrite "
        "is merely different rather than more permissive, or if it added a "
        "specific that is not in the real answer."
    )


def ask_one_model(adapter, system: str, question: str) -> tuple[str, str | None, float]:
    """One non-tool turn against a provider. Never raises: a dead endpoint is a report.

    WHAT BOUNDS ONE CALL IS THE PROVIDER'S SOCKET TIMEOUT AND NOTHING HERE, AND
    THAT BOUND HAS ALREADY BEEN APPROACHED. `OllamaProvider.STREAM_TIMEOUT_SECONDS`
    is 600 and it is a ceiling per READ, not per call and not per run.

    Measured on this machine on 2026-09-03, granite42-hermes:latest over ten
    rows of `runs/honest-path/train.jsonl`: most calls took 9-29 seconds, and
    ONE judge call took 500.9 - twenty times the rest, and inside 17% of the
    socket timeout. So the pathological row is not hypothetical; it happened on
    the first ten-row run. At 500 rows a handful of those is hours nobody
    planned for, and there is no wall-clock ceiling on the run to catch it.

    A `--deadline` belongs here, and it is deliberately not added in this
    commit: the honest version stops the run and writes the report it has,
    which is a fourth stop condition and it should be specified beside the
    other three rather than invented at the bottom of a docstring. What this
    run does instead is RECORD `seconds` on every call, so the next reader has
    the distribution rather than an impression of it.

    The same `Delta` handling as `app/tools/evals.py::_ask`, and `perf_counter`
    for the same measured reason recorded there: on Windows `time.monotonic()`
    resolves to about 15.6 ms, so every reply faster than that would be stored
    as zero seconds - a made-up number in a column the report prints.
    """
    import time

    from app.providers import Delta

    conversation = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]
    parts: list[str] = []
    started = time.perf_counter()
    try:
        for delta in adapter.stream(conversation, None, secret=None):
            if not isinstance(delta, Delta):
                continue
            if delta.kind == "text" and delta.text:
                parts.append(delta.text)
            elif delta.kind == "error":
                return "", delta.detail, time.perf_counter() - started
    except Exception as error:  # noqa: BLE001 - a dead endpoint is a report
        return "", f"{type(error).__name__}: {error}", time.perf_counter() - started
    return "".join(parts).strip(), None, time.perf_counter() - started


def pairs_that_are_two_real_answers(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each real answer beside the NEXT real answer. Nothing generated at all.

    WHY THIS IS THE CONTROL THAT CAN BE RUN, AND WHY IT IS NOT THE SPEC'S.
    `10-Signals/specs/synthetic-data.md` says to run *"the identical validator
    and the identical judge over all 49 rows"* of the seed file and read a high
    drop rate as the judge rejecting the house style. That is well posed when
    the judged unit is ONE ROW - a tool call is right or wrong on its own. Here
    the judged unit is a PAIR, and the judge's question is "is this rewrite a
    degradation of that answer". A real row has no rewrite, so there is nothing
    to hand it.

    A pair Max already trusts would be a real answer beside a worse one HE
    would rank lower. None are written down, so the spec's control needs him
    and is parked.

    What can be run without him is the other side of the same coin. Two
    unrelated real answers are NOT a degradation of one another - they are
    merely different, which the judge is explicitly told to DROP. So:

        THE SIGN IS INVERTED RELATIVE TO THE SPEC'S CONTROL. Here a high DROP
        rate is the judge working. What this measures is the FALSE-KEEP rate:
        how often the judge waves through something that is not the named
        degradation at all. It does not measure the false-DROP rate, which is
        the half the spec's control was for, and which still needs his pairs.

    `chosen` stays the row's own answer, so `why_this_preference_pair_is_malformed`
    still checks it against the file and the validator is exercised unchanged.
    """
    return [
        {
            "prompt": row["question"],
            "chosen": row["answer"],
            "rejected": rows[(index + 1) % len(rows)]["answer"],
            "row_index": row["row_index"],
            "rejected_from_row_index": rows[(index + 1) % len(rows)]["row_index"],
        }
        for index, row in enumerate(rows)
        if len(rows) > 1
    ]


def the_control_reading(*, kept: int, graded: int) -> dict[str, Any]:
    """The control's numbers with the sentence that says which way to read them.

    A control whose sign a reader has to work out is a control that will be
    read backwards once, and once is enough.
    """
    rate = _share(kept, graded)
    return {
        "what": (
            "the same validator and the same judge over pairs of two REAL "
            "answers, which are merely different rather than degradations"
        ),
        "graded": graded,
        "judge_kept": kept,
        "judge_dropped": graded - kept,
        "false_keep_rate": rate,
        "read_it_this_way": (
            "A LOW number is the judge working. These pairs contain no "
            "degradation, so every KEEP is the judge waving through something "
            "it was told to drop. This is the FALSE-KEEP half only; the "
            "false-DROP half needs pairs a person has ranked, and the spec's "
            "own control is parked on that."
            if rate is not None
            else "Nothing was graded, so there is no rate."
        ),
    }


def read_the_judges_verdict(text: str) -> bool | None:
    """`True` (KEEP) / `False` (DROP) / `None` (unreadable), from the LAST word.

    THE LAST VERDICT WORD, NOT THE FIRST, because the judge is asked for
    reasoning first and the reasoning routinely contains both words ("it does
    not DROP the condition, so KEEP"). Reading the first would grade the
    argument rather than the conclusion.

    `None` is not a third grade. It is a row nobody graded, and
    `why_this_row_must_not_ship` drops it; enough of them stop the run.
    """
    import re

    found = re.findall(r"\b(KEEP|DROP)\b", str(text or "").upper())
    if not found:
        return None
    return found[-1] == "KEEP"


def strip_the_models_scaffolding(text: str) -> str:
    """Remove the wrapping a chat model adds around a bare rewrite.

    Only wrapping is removed - surrounding quotation marks, a leading
    "Rewritten answer:" label, a markdown fence. Nothing inside is edited,
    because editing the generated text here would make the row something
    neither the model nor the person wrote.
    """
    import re

    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^```[a-z]*\s*|\s*```$", "", cleaned).strip()
    cleaned = re.sub(
        r"^(rewritten answer|worse answer|answer)\s*:\s*", "", cleaned,
        flags=re.IGNORECASE,
    ).strip()
    if len(cleaned) >= 2 and cleaned[0] in "\"'“" and cleaned[-1] in "\"'”":
        cleaned = cleaned[1:-1].strip()
    return cleaned


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


class TheRunMustStop(Exception):
    """A condition no further row can repair. Refusal 1 (share) and refusal 3."""


def _the_deterministic_gates():
    """`an_inverted_refusal` and `what_actually_changed`, loaded from `scripts/`.

    Loaded rather than imported because this file is a script beside them, not
    a package - the same way `checker` is already obtained here.
    """
    import importlib.util

    here = Path(__file__).resolve().parent
    loaded = []
    for name in ("an_inverted_refusal", "what_actually_changed",
                 "a_rewrite_that_adds_a_fact", "a_row_we_already_have"):
        spec = importlib.util.spec_from_file_location(name, here / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        loaded.append(module)
    return loaded[0], loaded[1], loaded[2], loaded[3]


def generate(
    *,
    source: Path,
    out_dir: Path,
    how_many: int,
    model: str,
    base_url: str,
    seed: str,
    question_field: str,
    answer_field: str,
    degradation: str,
    adapter=None,
    now=None,
    say=None,
    enforce_clause_one: bool = True,
    refuse_added_facts: bool = True,
    refuse_duplicates: bool = True,
    rows_already_kept=None,
) -> dict[str, Any]:
    """Produce rows, account for every one, and write four files. Returns the report.

    WHAT IS WRITTEN, ALWAYS, EVEN ON A STOP: the kept rows, `dropped.jsonl` with
    every dropped row AND why, and `report.json`. The spec's own line is that
    `dropped.jsonl` holds *"Every dropped row, with why. Not a count"* - a run
    whose failures were counted rather than kept is a run whose generator cannot
    be fixed, because the sentences that would say how are gone.
    """
    import datetime

    from app.providers.ollama import OllamaProvider

    #: QUIET BY DEFAULT, LOUD FROM THE COMMAND LINE. A ten-row run against a
    #: local model takes minutes and printing nothing until it finishes is
    #: indistinguishable from a hung run - so it gets killed, and the person
    #: concludes the pipeline does not work. `_main` passes a printer; a test
    #: passes nothing and the suite stays readable.
    say = say if say is not None else (lambda line: None)

    checker = _the_checker()
    now = now or (lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    adapter = adapter or OllamaProvider(base_url, model)

    source = source.resolve()
    digest_at_start = sha256_of(source)
    rows = read_the_source_rows(
        source, question_field=question_field, answer_field=answer_field
    )
    if not rows:
        raise TheRunMustStop(
            f"{source} has no row carrying both {question_field!r} and "
            f"{answer_field!r}. Nothing can be generated from it."
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    #: ONE TALLY PER STAGE, NOT ONE TALLY. A judge drop counted among the
    #: validator's faults inflates `validator.dropped`, which makes both pass
    #: rates wrong - and the two pass rates are the only thing in the report
    #: that says which repair to make. Merging them would hide exactly the
    #: information the report exists to separate.
    by_stage: dict[str, dict[str, int]] = {
        "generator": {}, "validator": {}, "duplicate": {}, "judge": {}
    }
    inverted, changed, adds_a_fact, already_have = _the_deterministic_gates()
    #: SEEDED FROM THE CORPUS AND GROWN DURING THE RUN. A gate that knew
    #: only the corpus at start-up would let a run duplicate against itself,
    #: which is how one triple came to appear seven times inside one run.
    the_corpus = already_have.TheRowsWeAlreadyHave(rows_already_kept or ())
    generator_failed = 0
    judge_dropped = 0
    unreadable = 0
    stopped: str | None = None

    # ROUND ROBIN, NOT RANDOM. Ten rows asked for over forty-nine sources are
    # sources 0 through 9, every time, and the same command run twice reads the
    # same source rows. Random sampling would be more diverse at 500 and it is
    # the wrong default at 10, where the whole point is that a person can open
    # the seed file at the named line and check the pair against it. When the
    # run is large enough for diversity to matter, `report["diversity"]` is
    # what says whether it was reached.
    for position in range(how_many):
        picked = rows[position % len(rows)]
        generator_prompt = what_the_generator_is_shown(
            question=picked["question"],
            answer=picked["answer"],
            degradation=degradation,
        )
        say(f"[{position + 1}/{how_many}] source row {picked['row_index']}: asking {model}")
        raw, error, seconds = ask_one_model(adapter, GENERATOR_SYSTEM, generator_prompt)
        generator = {
            "model": model,
            "base_url": base_url,
            "options": _what_was_actually_sent(),
            "degradation": degradation,
            "prompt_sha256": sha256_of_text(GENERATOR_SYSTEM + generator_prompt),
            "seconds": round(seconds, 3),
        }
        if error:
            say(f"    the generator failed after {seconds:.1f}s: {error}")
            generator_failed += 1
            _drop(dropped, by_stage, picked, [f"the generator failed: {error}"],
                  stage="generator")
            continue

        pair = {
            "prompt": picked["question"],
            "chosen": picked["answer"],
            "rejected": strip_the_models_scaffolding(raw),
        }
        faults = checker.why_this_preference_pair_is_malformed(
            pair, source_answer=picked["answer"]
        )
        if faults:
            say(f"    dropped by the validator after {seconds:.1f}s: {faults[0]}")
            _drop(dropped, by_stage, {**picked, **pair}, faults, stage="validator")
            continue

        #: THE TWO DETERMINISTIC GATES, BEFORE ANY JUDGE IS ASKED.
        #:
        #: Both were measured on constructed rows first and neither is a
        #: rubric change: they answer questions about two strings that this
        #: judge has been measured answering wrongly.
        #:
        #: ORDER MATTERS. The inversion backstop runs first, because a reversed
        #: refusal IS a content change and the diff would admit it - "we cannot
        #: take back" to "we can take back" is a substitution, and the judge
        #: kept 3 of 6 of those while narrating each inversion as a deletion.
        #:
        #: `enforce_clause_one=False` restores the shipped behaviour exactly,
        #: which is what the A arm of
        #: `docs/judge_runs/2026-09-05-the-gates-on-generated-rows-prereg.md`
        #: needs. It is a measurement switch, not a way to turn a refusal off
        #: in production.
        if enforce_clause_one:
            reversed_refusal = inverted.the_refusal_this_rewrite_inverted(
                pair["chosen"], pair["rejected"]
            )
            if reversed_refusal:
                say(f"    dropped by rule after {seconds:.1f}s: a reversed refusal")
                _drop(dropped, by_stage, {**picked, **pair}, [reversed_refusal],
                      stage="validator")
                continue
            not_the_named_kind = changed.why_this_pair_never_reaches_the_judge(
                pair["chosen"], pair["rejected"]
            )
            if not_the_named_kind:
                say(f"    dropped by rule after {seconds:.1f}s: not a degradation")
                _drop(dropped, by_stage, {**picked, **pair}, [not_the_named_kind],
                      stage="validator")
                continue

        #: CLAUSE (2), ENFORCED RATHER THAN ASKED. The contract already says
        #: "every fact, number, name, price and place in the rewritten answer
        #: already appears in the real answer"; this is that sentence at zero
        #: calls, because the judge was measured certifying its opposite.
        #:
        #: Measured 2026-09-05 on 20 rows the judge KEPT: eight add a content
        #: word, three of those are flat falsehoods - "except Christmas Day and
        #: Boxing Day WHEN WE ARE CLOSED" became "INCLUDING Christmas Day", and
        #: the judge wrote "uses only facts present in the real answer".
        #:
        #: THE COST IS REAL AND IS NOT ZERO. Three of the seven it refuses on
        #: that draw are genuine degradations - a model that rephrased while it
        #: degraded, "usually arrives" to "will arrive within". The trade is
        #: three lost pairs against three planted lies, taken deliberately: a
        #: generator can be asked for more pairs and a corpus cannot be told to
        #: forget that the shop opens on Christmas Day.
        #:
        #: A composition that readmitted rows where a scope marker was dropped
        #: was tried first and REJECTED: it readmitted two of the three lies,
        #: because a lie here is a removed marker with its opposite in the gap.
        #: See docs/judge_runs/2026-09-05-the-composition-readmits-the-lies.md.
        if refuse_added_facts:
            invented = adds_a_fact.why_this_rewrite_adds_a_fact(
                pair["chosen"], pair["rejected"]
            )
            if invented:
                say(f"    dropped by rule after {seconds:.1f}s: it adds a fact")
                _drop(dropped, by_stage, {**picked, **pair}, [invented],
                      stage="validator")
                continue

        #: A ROW WE ALREADY HAVE. Zero calls: three strings against a set. Its
        #: own stage, because a duplicate is redundant and not wrong, and a
        #: report that filed it under `validator` would say the generator
        #: produced something broken when it produced something we had.
        if refuse_duplicates:
            already = already_have.why_this_row_is_one_we_already_have(
                {**picked, **pair}, the_corpus
            )
            if already:
                say(f"    dropped after {seconds:.1f}s: a row we already have")
                _drop(dropped, by_stage, {**picked, **pair}, [already],
                      stage=already_have.THE_STAGE)
                continue

        say(f"    rewrote it in {seconds:.1f}s; asking the judge")
        judge_reply, judge_error, judge_seconds = ask_one_model(
            adapter,
            JUDGE_SYSTEM,
            what_the_judge_is_shown(
                question=pair["prompt"], chosen=pair["chosen"],
                rejected=pair["rejected"], degradation=degradation,
            ),
        )
        verdict = None if judge_error else read_the_judges_verdict(judge_reply)
        judge = {
            "model": model,
            "options": _what_was_actually_sent(),
            "verdict": None if verdict is None else ("KEEP" if verdict else "DROP"),
            "reasoning": (judge_error or judge_reply).strip(),
            "seconds": round(judge_seconds, 3),
        }

        stamped = stamp_the_provenance(
            pair,
            generator=generator,
            validator={
                "module": "scripts/check_that_a_tool_call_could_run.py",
                # ONLY THE CHECKS THAT ACTUALLY RAN. The spec's illustrative
                # block also carries `registry_tools`, which belongs to the
                # tool-call corpus: a preference pair is never checked against
                # a tool schema, and a count of registered tools sitting in its
                # provenance would read as though one had been.
                "checked": list(WHAT_A_PREFERENCE_PAIR_IS_CHECKED_FOR),
                "faults": [],
            },
            judge=judge,
            source={
                "path": str(source),
                "sha256": digest_at_start,
                "row_index": picked["row_index"],
                "answer_field": answer_field,
            },
            script="scripts/generate_the_preference_pairs.py",
            seed=seed,
            now=now(),
        )

        if verdict is None:
            unreadable += 1
        refusals = why_this_row_must_not_ship(stamped)
        if verdict is False:
            # NAMED FIRST, AND ALWAYS. A DROP is why this row is not shipping;
            # a thin explanation alongside it is a second fact about the judge,
            # not a replacement for the verdict. Reporting only the thin
            # reasoning would send a reader to fix the judge's verbosity when
            # what happened is that the judge rejected the row.
            refusals = ["the judge said DROP"] + refusals
        if refusals:
            if verdict is not None:
                judge_dropped += 1
            say(f"    dropped after {judge_seconds:.1f}s: {refusals[0]}")
            _drop(dropped, by_stage, stamped, refusals, stage="judge")
        else:
            say(f"    KEPT after {judge_seconds:.1f}s")
            kept.append(stamped)
            the_corpus.remember(stamped)

        graded = len(kept) + judge_dropped + unreadable
        if (
            graded >= FEWEST_ROWS_BEFORE_A_SHARE_MEANS_ANYTHING
            and unreadable / graded > MOST_UNREADABLE_SHARE
        ):
            stopped = (
                f"{unreadable} of {graded} verdicts were unreadable, over the "
                f"{MOST_UNREADABLE_SHARE:.0%} share this run stops at. Producing "
                "more rows nobody graded is not progress."
            )
            break

    digest_at_write = sha256_of(source)
    if digest_at_write != digest_at_start:
        stopped = (
            f"{source} changed while the run was in progress "
            f"({digest_at_start[:12]} -> {digest_at_write[:12]}). Every "
            "synthetic_source_index written by this run now points somewhere "
            "else, and there is no repair for that afterwards."
        )
        kept = []

    _write_jsonl(out_dir / f"{source.stem}.synthetic.jsonl", kept)
    _write_jsonl(out_dir / "dropped.jsonl", dropped)

    report = the_kept_and_dropped_report(
        generated=how_many,
        validator_dropped=by_stage["validator"],
        generator_failed=generator_failed,
        judge_dropped=judge_dropped,
        judge_unreadable=unreadable,
        kept=len(kept),
        distinct_sources=len({r["synthetic_source_index"] for r in kept}),
        source_rows=len(rows),
        control=None,
        generator_model=model,
        judge_model=model,
    )
    report["dropped_by_stage"] = by_stage
    report["stopped"] = stopped
    # BOTH DIGESTS, ALWAYS. Printing only the one read at the start would make
    # a report of a stopped run say the file was fine; printing only the one
    # read at the end would lose what the rows were actually generated from.
    report["source"] = {
        "path": str(source),
        "sha256_when_the_run_started": digest_at_start,
        "sha256_when_it_finished": digest_at_write,
        "usable_rows": len(rows),
    }
    (out_dir / "report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    if stopped:
        raise TheRunMustStop(stopped)
    return report


def run_the_control(
    *,
    source: Path,
    model: str,
    base_url: str,
    question_field: str,
    answer_field: str,
    degradation: str,
    adapter=None,
    say=None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Grade real-answer-vs-real-answer pairs with the same judge. No generator.

    Costs one judge call per row and nothing else - `pairs_that_are_two_real_answers`
    invents no text, so there is no generation stage to pay for. The validator
    runs unchanged on every pair, and its drop count is reported: on real rows
    with a `chosen` copied from the file it should be zero, and a non-zero one
    would mean the validator itself is broken.
    """
    from app.providers.ollama import OllamaProvider

    say = say if say is not None else (lambda line: None)
    adapter = adapter or OllamaProvider(base_url, model)
    checker = _the_checker()

    rows = read_the_source_rows(
        source.resolve(), question_field=question_field, answer_field=answer_field
    )
    pairs = pairs_that_are_two_real_answers(rows)
    if limit is not None:
        pairs = pairs[:limit]
    if not pairs:
        raise TheRunMustStop(
            f"{source} yields fewer than two usable rows, so no real-vs-real "
            "pair can be formed and there is nothing to control against."
        )

    kept = 0
    graded = 0
    unreadable = 0
    validator_dropped = 0
    waved_through: list[dict[str, Any]] = []

    for position, pair in enumerate(pairs):
        say(f"[control {position + 1}/{len(pairs)}] row {pair['row_index']}")
        faults = checker.why_this_preference_pair_is_malformed(
            pair, source_answer=pair["chosen"]
        )
        if faults:
            validator_dropped += 1
            continue
        reply, error, seconds = ask_one_model(
            adapter,
            JUDGE_SYSTEM,
            what_the_judge_is_shown(
                question=pair["prompt"], chosen=pair["chosen"],
                rejected=pair["rejected"], degradation=degradation,
            ),
        )
        verdict = None if error else read_the_judges_verdict(reply)
        if verdict is None:
            unreadable += 1
            say(f"    unreadable after {seconds:.1f}s")
            continue
        graded += 1
        if verdict:
            kept += 1
            # KEPT ROWS ARE THE INTERESTING ONES HERE, which is the opposite of
            # a generation run. Each one is a pair with no degradation in it
            # that the judge accepted anyway, so each is a sentence worth
            # reading rather than a tick in a column.
            waved_through.append({
                "row_index": pair["row_index"],
                "rejected_from_row_index": pair["rejected_from_row_index"],
                "prompt": pair["prompt"],
                "chosen": pair["chosen"],
                "rejected": pair["rejected"],
                "judge_said": reply.strip(),
            })
            say(f"    WAVED THROUGH after {seconds:.1f}s")
        else:
            say(f"    dropped after {seconds:.1f}s (correct)")

    reading = the_control_reading(kept=kept, graded=graded)
    reading["path"] = str(source)
    reading["pairs_offered"] = len(pairs)
    reading["validator_dropped"] = validator_dropped
    reading["unreadable"] = unreadable
    reading["judge_model"] = model
    reading["waved_through"] = waved_through
    return reading


def _what_was_actually_sent() -> dict[str, Any]:
    """The generation options this run sent. It sent none, and says so.

    THIS DEPARTS FROM THE SPEC'S ILLUSTRATIVE BLOCK, WHICH SHOWS
    `{"temperature": 0.9, "seed": 4412}`. `OllamaProvider.stream` sends
    `model`, `messages`, `stream` and - when the budget planner asks for one -
    `num_ctx`. There is no parameter on it that carries a temperature or a
    seed, and the product's own judge (`app/tools/evals.py::_ask`) sends none
    either. Recording options that were not sent would be the invented number
    this repository refuses everywhere else; the honest block says what the
    absence is.

    Adding them is a real improvement and it belongs in `OllamaProvider`, where
    the conductor and the eval runner would get it too - not in a copy of the
    request builder living in a script.
    """
    return {
        "sent": [],
        "note": (
            "No temperature and no seed were sent. OllamaProvider.stream has no "
            "parameter for either, so this run used the model's own defaults "
            "and is not reproducible from these fields alone."
        ),
    }


def _the_checker():
    """The stage 2 validator, imported by path so `scripts/` needs no package."""
    import importlib.util
    import sys as _sys

    path = Path(__file__).resolve().parent / "check_that_a_tool_call_could_run.py"
    spec = importlib.util.spec_from_file_location("_stage_two_checker", path)
    module = importlib.util.module_from_spec(spec)
    was = _sys.dont_write_bytecode
    _sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        _sys.dont_write_bytecode = was
    return module


def _drop(dropped, by_stage, row, faults, *, stage):
    """Keep the row AND the sentences. A count cannot be argued with."""
    dropped.append({**dict(row), "dropped_by": stage, "why": list(faults)})
    tally = by_stage[stage]
    for fault in faults:
        tally[fault] = tally.get(fault, 0) + 1


def _write_jsonl(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _main(argv=None) -> int:
    #: STDOUT IN UTF-8 BEFORE ANYTHING PRINTS. What this run prints is model
    #: text, and model text carries characters the Windows console codec cannot
    #: encode. The 200-row run of 2026-09-05 finished its work, wrote its three
    #: files, and then died on `UnicodeEncodeError: '‑'` - a non-breaking
    #: hyphen - while PRINTING a row. Nothing was lost, because the files were
    #: already on disk and the lock release was chained to the command rather
    #: than to the script's success. But a report that crashes on its own
    #: output is a report nobody reads.
    #:
    #: The fourth character-escape failure of that night and the first on
    #: OUTPUT rather than source, which is why this is a line of code and not a
    #: note about being careful.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # a stream that cannot be
            pass                              # reconfigured is not a reason to stop

    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("-n", "--how-many", type=int, default=10)
    #: MAX'S CALL, 2026-09-08, and it is his rather than a bench's.
    #: `09-Nightshift/MAX DIRECTION 2026-09-08.md`: *"minicpm5-hermes replaces
    #: granite everywhere, granite4 included ... obviously it's new, so we could
    #: have some tinkering, have some bugs."* THE BUGS ARE ACCEPTED IN ADVANCE
    #: and are not a reason to hold the swap.
    #:
    #: `model_bench.py` scores 13/13 for BOTH models, so the bench does not
    #: discriminate and is not the reason. One probe on this machine, same path
    #: and same question, put granite at 3,308 completion tokens against
    #: minicpm's 1,310 for a comparable answer - one probe, not a bench.
    #:
    #: EVERY RECORDED RESULT IN `runs/` IS A GRANITE RESULT AND STAYS ONE. No
    #: row on disk names the model that produced it, so nothing in an artefact
    #: distinguishes the two - a comparison arm across this change would need
    #: the model named AND the quantisation matched (granite is Q4_K_M, this
    #: build is Q8_0). Changing the default is not a licence to compare over it.
    parser.add_argument("--model", default="minicpm5-hermes:latest")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--seed", required=True, help="names this run, e.g. granite42-2026-09-03-a")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--question-field", default="instruction")
    parser.add_argument("--answer-field", default="response")
    parser.add_argument("--degradation", default=DEGRADATIONS[0], choices=DEGRADATIONS)
    parser.add_argument(
        "--control",
        action="store_true",
        help=(
            "grade real-answer-vs-real-answer pairs instead of generating. One "
            "judge call per row, no generator. A LOW keep rate is the judge "
            "working - see pairs_that_are_two_real_answers for why the sign is "
            "inverted relative to the spec's control."
        ),
    )
    args = parser.parse_args(argv)

    out = args.out or (Path("runs") / f"synthetic-{args.seed}")
    loud = lambda line: print(line, file=sys.stderr, flush=True)  # noqa: E731

    if args.control:
        try:
            reading = run_the_control(
                source=args.source, model=args.model, base_url=args.base_url,
                question_field=args.question_field,
                answer_field=args.answer_field, degradation=args.degradation,
                say=loud,
            )
        except TheRunMustStop as stop:
            print(f"THE CONTROL STOPPED: {stop}")
            return 1
        out.mkdir(parents=True, exist_ok=True)
        (out / "control.json").write_text(
            json.dumps(reading, indent=2), encoding="utf-8"
        )
        print(json.dumps(reading, indent=2))
        print(f"\nWritten to {out / 'control.json'}")
        return 0

    try:
        report = generate(
            source=args.source, out_dir=out, how_many=args.how_many,
            model=args.model, base_url=args.base_url, seed=args.seed,
            question_field=args.question_field, answer_field=args.answer_field,
            degradation=args.degradation,
            say=loud,
        )
    except TheRunMustStop as stop:
        print(f"THE RUN STOPPED: {stop}")
        print(f"What it wrote before stopping is in {out}")
        return 1
    print(json.dumps(report, indent=2))
    print(f"\nWritten to {out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
