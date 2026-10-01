"""The instruments of the harness-building ledger.

`docs/ledgers/harness_design.yaml` declares eleven `inspect` facts and an
`inspect` fact with no instrument is a gate nobody can open. This module is the
six tools that read them, and it is the third such pack: `app/tools/agents.py`
did it for the AI-engineering ledger, and most of what is done here is done by
calling into that one.

## The thing `HARNESS_DESIGN.md` said could not be done

That document lists the ladder rates and the ablation counts as NEW instruments
"and the hard one, because scoring a harness variant means running somebody
else's system, which the `agent` pack forbids".

**The forbidden thing was never the measurement. It was the DRIVING.**
`run_the_failures` already found the way through and this module takes the same
road: the person runs their own system, exports what it answered, and the
harness GRADES that against their own expected column. Nothing of theirs is
executed. The number is a real measurement, and the fact stays `source: inspect`
rather than being demoted to `ask`.

That one move makes G2 and G3 implementable, and G3 is the gate this whole
domain exists for.

## What is deliberately duplicated, and why it is not a mistake

`bound_the_harness_run` reads the same OTLP spans through the same helpers as
`bound_the_loop`, and stamps different fact names. The ledgers share zero fact
names by design - `app/tools/registry.py`'s domain adoption depends on it, since
a fact declared by two ledgers stops naming a domain - so `has_traces` and
`harness_has_traces` are two facts about one file, and that is exactly right:
two domains asking the same question of the same trace are still two domains,
and one fact answering for both would mean a person's traces opened a gate in a
ledger they were never diagnosed under.

## What none of these do

Execute anything. Read the checker, count the tasks, grade recorded answers,
pair recorded arms, read tool definitions, read spans. Six readers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from app import dataquality
from app.tools import agents, context, evals
from app.tools.evidence import Instrument, MeasurementError
from app.tools.registry import tool


#: What a recorded run's answer is graded against. The same two comparators
#: `run_eval` uses, and the same reason there is no third: a judge model grading
#: a harness variant would be a measurement of the judge.
def _is_right(answer: Any, expected: Any) -> bool:
    left = str(answer or "").strip()
    right = str(expected or "").strip()
    if not right:
        return False
    return left.casefold() == right.casefold() or right.casefold() in left.casefold()


#: The three rungs of the ladder, and which fact each one is filed under. A
#: closed set, because `variant` decides which gate row a number can open and a
#: free string would let a caller file a pipeline's rate as a bare model's.
THE_RUNGS: dict[str, str] = {
    "solo": "solo_pass_rate",
    "pipeline": "pipeline_pass_rate",
    "single_loop": "single_loop_pass_rate",
}

#: What a tool definition has to carry before this counts it as risk-annotated.
#: MCP's own `annotations` block is the standard one; the other two are what
#: hand-written tool arrays tend to use. Read off the file, never inferred from
#: a name - `delete_everything` is not annotated just because it sounds it.
RISK_KEYS = ("destructiveHint", "readOnlyHint", "risk", "blast_radius", "destructive")

#: How much of a checker this will read. It is read to decide whether it is a
#: program, not to understand it, and a multi-megabyte file is not more of an
#: answer than the first few kilobytes.
CHECKER_READ_BYTES = 200_000

#: What makes a file look like a program rather than a paragraph. Deliberately
#: crude and deliberately stated: this is a FIRST gate separating "there is a
#: definition of success" from "there is not", and the sharper question - does
#: the checker actually pass - is what G1's twenty tasks are for.
PROGRAM_MARKERS = (
    "def ",
    "function ",
    "=>",
    "assert",
    "return ",
    "class ",
    "$schema",
    '"type"',
    "'type'",
    "#!/",
)


def _refuse(code: str, *, read: str, needed: str, **extra: Any) -> dict[str, Any]:
    """One refusal shape, borrowed from the agent pack so the two read alike."""
    return agents.refusal(code, read=read, needed=needed, **extra)


# ---------------------------------------------------------------------------
# G0 - is there a definition of success at all?


@tool(
    "read_the_success_check",
    description=(
        "Read the file that decides whether an answer was right, and report "
        "whether it is a program this harness could point at rather than a "
        "paragraph. It READS the file and never runs it: running your code is "
        "your business. Point it at the checker you named."
    ),
    schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "The checker on this machine - a script, a function, or a "
                    "JSON Schema the answers have to satisfy."
                ),
            }
        },
        "required": ["path"],
    },
    reads=("filesystem",),
    writes=("facts",),
    measures=("success_check_characters", "success_check_is_a_program"),
    provides=("harness.success_check.read",),
    label="Read the success check",
    group="Look",
    verb="read the checker you named",
    order=60,
)
def read_the_success_check(path: str, *, instrument: Instrument) -> dict[str, Any]:
    """READ, NEVER RUN, and that restraint is the whole design of this gate.

    `docs/ledgers/HARNESS_DESIGN.md` settled this on 2026-08-28 and it is worth
    restating where the code is. The tempting fact was `success_check_runs` -
    execute the person's checker on one case and report pass or fail. That means
    running somebody else's program, and `app/tools/blocks.py`'s `agent` pack
    states the rule plainly: never execute somebody else's system, read files.

    So the gate is denominated in something readable, which is the same move
    that turned `cost_per_run_usd` into `tokens_per_run` when a price turned out
    to be a fact about somebody's contract rather than about the work. Weaker
    than executing it, and enough for a FIRST gate.

    **Choosing the option that keeps an existing wall intact is not the same
    kind of call as choosing one that widens it.** A wall kept can be opened
    later on purpose; a wall widened is opened by accident first.

    The contents are quarantined before they go anywhere near a model. This is a
    stranger's file being read off disk and put in front of something that acts
    on text, which is the shape `_describe_one` already refuses to take
    shortcuts on.
    """
    target = Path(path)
    payload: dict[str, Any] = {"path": str(target), "refusals": [], "ran_it": False}

    if not target.is_file():
        payload["refusals"].append(
            _refuse(
                "no_such_file",
                read=f"{target} is not a file on this machine",
                needed=(
                    "the checker you named - a script, a function, or a JSON "
                    "Schema. Nothing was read, so nothing was recorded."
                ),
            )
        )
        payload["ok"] = False
        return payload

    try:
        handle, encoding = dataquality.open_text(target, newline=None)
        try:
            text = handle.read(CHECKER_READ_BYTES)
        finally:
            handle.close()
    except (OSError, UnicodeDecodeError) as error:
        payload["refusals"].append(
            _refuse(
                "unreadable",
                read=f"{type(error).__name__}: {error}",
                needed=(
                    "a text file. A binary checker may be a real checker and it "
                    "is not one this can read, so nothing was recorded."
                ),
            )
        )
        payload["ok"] = False
        return payload

    found = sorted({marker for marker in PROGRAM_MARKERS if marker in text})
    is_a_program = bool(found)

    payload.update(
        {
            "ok": True,
            "encoding": encoding,
            "characters_read": len(text),
            "looks_like_a_program": is_a_program,
            "markers_found": found,
            "how_it_was_decided": (
                "the file was read and searched for the shapes a checker takes - "
                f"{list(PROGRAM_MARKERS)}. This is crude on purpose: it separates "
                "'there is a definition of success' from 'there is not', which is "
                "what a first gate is for. Whether the checker is CORRECT is what "
                "your twenty tasks are for, and by then you will have run it "
                "yourself."
            ),
            "first_lines": context.quarantine(
                "\n".join(text.splitlines()[:12]),
                source=f"the success checker at {target}",
            ),
        }
    )

    # THE READING FIRST, THEN THE FLAG, AND THE ORDER IS THE WALL'S. A boolean
    # stamped MEASURED by a call that has measured nothing else is refused by
    # `app/tools/evidence.py` - correctly, because `bool(argument)` produces a
    # True that no comparison has ever seen, and there is no caller mark a
    # boolean can carry. The character count IS the reading: it says a file was
    # opened and had something in it, and the flag is a summary of what was in
    # it. This was driven rather than designed - the wall refused the first
    # version of this tool - and G0 was widened to ask for both.
    try:
        instrument.measured(
            "success_check_characters",
            len(text),
            how=f"read {len(text):,} characters of {target} without executing it",
            from_file=str(target),
        )
        instrument.measured(
            "success_check_is_a_program",
            is_a_program,
            how=(
                f"read {len(text):,} characters of {target} and "
                + (
                    f"found {found}"
                    if is_a_program
                    else "found none of the shapes a checker takes"
                )
                + ". It was not executed."
            ),
            from_file=str(target),
        )
    except MeasurementError as error:  # pragma: no cover - no thread, no record
        payload["not_stamped"] = str(error)
    return payload


# ---------------------------------------------------------------------------
# G1 - is there enough to measure on?


@tool(
    "count_the_task_set",
    description=(
        "Count the tasks in a file and report how many carry the outcome that "
        "would be right. A task with no expected outcome cannot be graded, so "
        "it is counted separately rather than included. Nothing is sent anywhere."
    ),
    schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The task file on this machine.",
            },
            "input_field": {
                "type": "string",
                "description": "The column holding the task itself.",
            },
            "expected_field": {
                "type": "string",
                "description": "The column holding the outcome that would be right.",
            },
        },
        "required": ["path", "input_field", "expected_field"],
    },
    reads=("filesystem", "datasets"),
    writes=("facts",),
    measures=("harness_tasks_n", "can_rerun_tasks"),
    provides=("harness.tasks.count",),
    label="Count the task set",
    group="Data",
    verb="count the tasks I can grade",
    order=61,
)
def count_the_task_set(
    path: str, input_field: str, expected_field: str, *, instrument: Instrument
) -> dict[str, Any]:
    """A count of what is GRADEABLE, which is not a count of the file's rows.

    **`can_rerun_tasks` IS MEASURED HERE RATHER THAN ASKED, and it is the same
    argument `run_the_failures` makes about `can_rerun_failures`.** A task set is
    re-runnable when every task carries the outcome that would be right - that
    is what re-running means: send it again and compare against something. So
    the fact is not a separate question, it is a property of the file, and a
    file where two rows in forty have no expected column is a file where those
    two rows are not tasks.

    The two columns are the person's to name for `carve_eval_set`'s reason:
    which column is the answer is a statement about somebody's file that only
    they can make, and a wrong guess grades a whole task set against the wrong
    text.
    """
    target = Path(path)
    payload: dict[str, Any] = {"path": str(target), "refusals": []}

    if not target.exists():
        payload["refusals"].append(
            _refuse(
                "no_such_file",
                read=f"nothing at {target}",
                needed="a task set on this machine",
            )
        )
        payload["ok"] = False
        return payload

    gradeable = 0
    missing_expected = 0
    missing_input = 0
    rows = 0
    try:
        for record in dataquality.iter_records(target):
            rows += 1
            if not isinstance(record, Mapping):  # pragma: no cover - a text row
                missing_input += 1
                continue
            has_input = bool(str(record.get(input_field) or "").strip())
            has_expected = bool(str(record.get(expected_field) or "").strip())
            if has_input and has_expected:
                gradeable += 1
            elif has_input:
                missing_expected += 1
            else:
                missing_input += 1
    except (OSError, ValueError, UnicodeDecodeError) as error:
        payload["refusals"].append(
            _refuse(
                "unreadable",
                read=f"{type(error).__name__}: {error}",
                needed="a readable CSV or JSONL",
            )
        )
        payload["ok"] = False
        return payload

    # A task set is re-runnable when EVERY row it holds can be graded. Not most
    # of them: the rows that cannot are the ones that will quietly leave the
    # denominator later, and a rate whose denominator moved between runs is not
    # a comparison.
    rerunnable = rows > 0 and gradeable == rows

    payload.update(
        {
            "ok": True,
            "rows": rows,
            "gradeable_tasks": gradeable,
            "rows_missing_the_expected_outcome": missing_expected,
            "rows_missing_the_task": missing_input,
            "can_rerun": rerunnable,
            "fields": {"input": input_field, "expected": expected_field},
        }
    )
    if missing_expected:
        payload["summary_of_what_was_dropped"] = (
            f"{missing_expected:,} row(s) carry a task and no expected outcome. "
            "Those are not tasks yet - there is nothing to compare an answer "
            "against - and writing the outcome beside each one is the half "
            "people skip and the half that makes the set re-runnable."
        )

    how_counted = (
        f"counted {gradeable} row(s) of {rows} in {target} carrying both "
        f"{input_field!r} and {expected_field!r}"
    )
    try:
        instrument.measured("harness_tasks_n", gradeable, how=how_counted, from_file=str(target))
        instrument.measured(
            "can_rerun_tasks",
            rerunnable,
            how=(
                how_counted
                + "; re-runnable means every row can be graded, and "
                + (
                    "every one can"
                    if rerunnable
                    else f"{rows - gradeable} cannot"
                )
            ),
            from_file=str(target),
        )
    except MeasurementError as error:  # pragma: no cover - no thread, no record
        payload["not_stamped"] = str(error)
    return payload


# ---------------------------------------------------------------------------
# G2 - the ladder.


def _graded(
    tasks: Path,
    answers: Path | None,
    input_field: str,
    expected_field: str,
    answer_field: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Join tasks to recorded answers and grade each one. Never drives anything.

    Answers may live in the task file itself or in a second file in the same row
    order, which is the shape `run_the_failures` established. A row missing any
    of the three fields is DROPPED and reported, never defaulted: grading an
    answer that is not there against an expectation that is not there would put
    a pass or a fail in the denominator nobody measured.
    """
    rows = list(dataquality.iter_records(tasks))
    other: list[Any] = list(dataquality.iter_records(answers)) if answers else []

    graded: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for index, record in enumerate(rows):
        if not isinstance(record, Mapping):  # pragma: no cover - a text row
            dropped.append({"row": index, "why": "not a record"})
            continue
        answered = record
        if other:
            if index >= len(other) or not isinstance(other[index], Mapping):
                dropped.append({"row": index, "why": "no answer in the same position"})
                continue
            answered = other[index]
        task = str(record.get(input_field) or "").strip()
        expected = str(record.get(expected_field) or "").strip()
        answer = str(answered.get(answer_field) or "").strip()
        if not task or not expected or not answer:
            dropped.append(
                {
                    "row": index,
                    "why": "missing the task, the expected outcome, or the answer",
                }
            )
            continue
        graded.append(
            {"row": index, "task": task, "passed": _is_right(answer, expected)}
        )
    return graded, dropped


@tool(
    "score_a_recorded_run",
    description=(
        "Grade what your system actually answered on your task set, and record "
        "the rate for one rung of the ladder: the bare model, the fixed "
        "pipeline, or the single loop. You run it and export the answers; this "
        "grades them. It never drives your system - your code is yours."
    ),
    schema={
        "type": "object",
        "properties": {
            "tasks_path": {
                "type": "string",
                "description": "The task set on this machine.",
            },
            "answers_path": {
                "type": "string",
                "description": (
                    "The answers your system produced, in the same row order. "
                    "Leave it out if the answers are in the task file itself."
                ),
            },
            "input_field": {"type": "string", "description": "The column holding the task."},
            "expected_field": {
                "type": "string",
                "description": "The column holding the outcome that would be right.",
            },
            "answer_field": {
                "type": "string",
                "description": "The column holding what your system actually answered.",
            },
            "variant": {
                "type": "string",
                "description": (
                    "Which rung this run was: 'solo' (the bare model), "
                    "'pipeline' (a fixed sequence, no model-driven control "
                    "flow), or 'single_loop' (one agent). Each is filed under "
                    "its own fact, because each opens a different row of the "
                    "ladder gate."
                ),
                "enum": ["solo", "pipeline", "single_loop"],
            },
        },
        "required": [
            "tasks_path",
            "input_field",
            "expected_field",
            "answer_field",
            "variant",
        ],
    },
    reads=("filesystem", "datasets"),
    writes=("facts",),
    measures=("solo_pass_rate", "pipeline_pass_rate", "single_loop_pass_rate"),
    # WHICH ARGUMENT THIS OPENS, DECLARED, because two of these tools take more
    # than one path and `app/build.py` refuses to cost a step against a file it
    # cannot show the call will open. The task set is the subject: it is the
    # denominator of every rate this produces and the thing the work scales
    # with, where the answers files are the other side of the comparison.
    subject=("tasks_path",),
    provides=("harness.variant.score",),
    label="Score a recorded run",
    group="Measure",
    verb="grade what your system answered",
    order=62,
)
def score_a_recorded_run(
    tasks_path: str,
    input_field: str,
    expected_field: str,
    answer_field: str,
    variant: str,
    answers_path: str | None = None,
    *,
    instrument: Instrument,
) -> dict[str, Any]:
    """A rate for one rung, graded off a recording rather than driven.

    THIS IS THE TOOL `HARNESS_DESIGN.md` SAID COULD NOT EXIST. That document
    lists these three facts as "the hard one, because scoring a harness variant
    means running somebody else's system, which the `agent` pack forbids", and
    it was right about the rule and wrong about the consequence. The forbidden
    thing is the DRIVING. Grading a recording is reading a file.

    **`variant` is a closed set and that is load-bearing.** Each rung opens a
    different row of G2 - `agent` needs the pipeline's rate, `multi_agent` needs
    the single loop's - so a free-text variant would let a caller file a
    pipeline's rate under the bare model's name and pass a gate that exists to
    ask whether the cheaper rung was tried.

    **It stamps exactly one fact per call**, which is why `measures=` names all
    three: that tuple is what a tool MAY stamp, and this one picks by argument.
    """
    rung = str(variant or "").strip()
    payload: dict[str, Any] = {
        "variant": rung,
        "tasks_path": str(tasks_path),
        "answers_path": str(answers_path or ""),
        "refusals": [],
        "drove_anything": False,
    }
    if rung not in THE_RUNGS:
        payload["refusals"].append(
            _refuse(
                "unknown_rung",
                read=f"variant {rung!r}",
                needed=(
                    f"one of {sorted(THE_RUNGS)}. Each opens a different row of "
                    "the ladder gate, so which rung a rate belongs to is not "
                    "something this can guess."
                ),
            )
        )
        payload["ok"] = False
        return payload

    tasks = Path(tasks_path)
    answers = Path(answers_path) if answers_path else None
    for candidate, what in ((tasks, "task set"), (answers, "answers file")):
        if candidate is not None and not candidate.exists():
            payload["refusals"].append(
                _refuse(
                    "no_such_file",
                    read=f"nothing at {candidate}",
                    needed=f"the {what} on this machine",
                )
            )
    if payload["refusals"]:
        payload["ok"] = False
        return payload

    try:
        graded, dropped = _graded(
            tasks, answers, input_field, expected_field, answer_field
        )
    except (OSError, ValueError, UnicodeDecodeError) as error:
        payload["refusals"].append(
            _refuse(
                "unreadable",
                read=f"{type(error).__name__}: {error}",
                needed="a readable CSV or JSONL on both sides",
            )
        )
        payload["ok"] = False
        return payload

    passed = sum(1 for row in graded if row["passed"])
    payload.update(
        {
            "ok": bool(graded),
            "graded": len(graded),
            "passed": passed,
            "dropped": dropped,
            "fact": THE_RUNGS[rung],
        }
    )
    if not graded:
        payload["summary"] = (
            "Nothing could be graded, so no rate was recorded. A rate over zero "
            "rows is not zero, it is nothing - and it would open a gate."
        )
        return payload

    rate = passed / len(graded)
    payload["pass_rate"] = round(rate, 4)
    payload["summary"] = (
        f"{passed} of {len(graded)} tasks passed - {rate:.1%} for the {rung} rung"
        + (
            f". {len(dropped)} row(s) could not be graded and are not in the "
            "denominator"
            if dropped
            else ""
        )
        + "."
    )
    how = (
        f"graded {len(graded)} recorded answer(s) against {expected_field!r} in "
        f"{tasks}, {passed} correct, for the {rung} rung. Nothing was driven; "
        "the answers were read."
    )
    # THREE BRANCHES RATHER THAN `THE_RUNGS[rung]`, AND A TEST ASKED FOR IT.
    # `test_the_wall_is_a_property_not_a_special_case` reads tool source for
    # `measured("<literal>", <value>` and checks the value is not a caller's
    # argument. A computed fact name defeats that check - it found no stamps at
    # all here and said so - and the honest response to a source-level guard
    # going blind is to write the source it can read, not to weaken the guard.
    # `THE_RUNGS` stays as the closed set `variant` is validated against.
    try:
        if rung == "solo":
            instrument.measured("solo_pass_rate", rate, how=how, from_file=str(tasks))
        elif rung == "pipeline":
            instrument.measured("pipeline_pass_rate", rate, how=how, from_file=str(tasks))
        else:
            instrument.measured(
                "single_loop_pass_rate", rate, how=how, from_file=str(tasks)
            )
    except MeasurementError as error:  # pragma: no cover - no thread, no record
        payload["not_stamped"] = str(error)
    return payload


# ---------------------------------------------------------------------------
# G3 - the gate this domain exists for.


@tool(
    "ablate_a_component",
    description=(
        "For each component of your harness, pair a recorded run WITH it "
        "against a recorded run WITHOUT it, over the same tasks, and report "
        "whether the difference is real. NO EVIDENCE is a real answer here: a "
        "component that changes nothing is one you were about to pay for."
    ),
    schema={
        "type": "object",
        "properties": {
            "tasks_path": {"type": "string", "description": "The task set on this machine."},
            "input_field": {"type": "string", "description": "The column holding the task."},
            "expected_field": {
                "type": "string",
                "description": "The column holding the outcome that would be right.",
            },
            "answer_field": {
                "type": "string",
                "description": "The column holding what the system answered.",
            },
            "arms": {
                "type": "array",
                "description": (
                    "One entry per component: its name, the answers file from "
                    "the run WITH it, and the answers file from the run "
                    "WITHOUT it. All of them at once, because the gate asks "
                    "about every component and not about one."
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
        },
        "required": [
            "tasks_path",
            "input_field",
            "expected_field",
            "answer_field",
            "arms",
        ],
    },
    reads=("filesystem", "datasets"),
    writes=("facts",),
    measures=("components_ablated_n", "components_that_earned_their_place"),
    subject=("tasks_path",),
    provides=("harness.component.ablate",),
    label="Ablate a component",
    group="Measure",
    verb="pair your with-and-without runs",
    order=63,
)
def ablate_a_component(
    tasks_path: str,
    input_field: str,
    expected_field: str,
    answer_field: str,
    arms: list[Mapping[str, Any]],
    *,
    instrument: Instrument,
) -> dict[str, Any]:
    """The G3 instrument. Paired, per row, with a real NO EVIDENCE answer.

    ## Why every arm at once rather than one call per component

    The gate asks whether EVERY component is load-bearing, so the unit of the
    measurement is the whole set. One call per component would need somewhere to
    accumulate a running count between calls, which is a table, which is state
    the answer does not need: `components_ablated_n` is how many arms were
    handed over and `components_that_earned_their_place` is how many of them
    survived, both computed in one pass over one call.

    ## Why paired, and why McNemar

    Comparing two aggregate rates throws away the information that matters. What
    decides whether a component earned its place is the rows that CHANGED - the
    ones it fixed against the ones it broke - and rows that agree carry nothing
    about the difference. `evals.mcnemar` is the exact two-sided test over
    exactly those rows and it returns 1.0 when nothing changed, which is the
    honest reading rather than a failure to compute one.

    **NO EVIDENCE IS THE POINT OF THIS TOOL.** A component that did not move the
    score by more than noise is a latency cost, a failure mode and an assumption
    that will rot, and it is the hardest kind of code to delete because it was
    right when it was written. The task set is what lets somebody delete it
    without arguing.
    """
    tasks = Path(tasks_path)
    payload: dict[str, Any] = {
        "tasks_path": str(tasks),
        "components": [],
        "refusals": [],
        "drove_anything": False,
    }
    if not tasks.exists():
        payload["refusals"].append(
            _refuse(
                "no_such_file",
                read=f"nothing at {tasks}",
                needed="a task set on this machine",
            )
        )
        payload["ok"] = False
        return payload
    if not arms:
        payload["refusals"].append(
            _refuse(
                "no_arms",
                read="an empty list of components",
                needed=(
                    "one entry per component you intend to build, each with the "
                    "answers from a run with it and a run without it. Nothing "
                    "was recorded: zero components ablated is not the same "
                    "statement as zero components proposed, and this gate is "
                    "about the difference."
                ),
            )
        )
        payload["ok"] = False
        return payload

    earned = 0
    for arm in arms:
        name = str((arm or {}).get("component") or "").strip() or "(unnamed)"
        row: dict[str, Any] = {"component": name}
        with_path = Path(str((arm or {}).get("with_answers") or ""))
        without_path = Path(str((arm or {}).get("without_answers") or ""))
        if not with_path.is_file() or not without_path.is_file():
            row["refused"] = "one of the two answer files is not on this machine"
            row["earned_its_place"] = False
            payload["components"].append(row)
            continue
        try:
            kept, _ = _graded(tasks, with_path, input_field, expected_field, answer_field)
            stripped, _ = _graded(
                tasks, without_path, input_field, expected_field, answer_field
            )
        except (OSError, ValueError, UnicodeDecodeError) as error:
            row["refused"] = f"{type(error).__name__}: {error}"
            row["earned_its_place"] = False
            payload["components"].append(row)
            continue

        by_row = {entry["row"]: entry["passed"] for entry in stripped}
        improved = regressed = agreed = 0
        for entry in kept:
            was = by_row.get(entry["row"])
            if was is None:
                continue
            if entry["passed"] and not was:
                improved += 1
            elif was and not entry["passed"]:
                regressed += 1
            else:
                agreed += 1
        paired = improved + regressed + agreed
        p_value = evals.mcnemar(improved, regressed)
        # EARNED means the component made it BETTER and the difference is real.
        # A component that made it significantly WORSE has not earned its place
        # either, and that is not a technicality: it is the most valuable finding
        # this tool can produce.
        verdict = bool(paired and p_value < 0.05 and improved > regressed)
        earned += 1 if verdict else 0
        row.update(
            {
                "rows_paired": paired,
                "fixed_by_it": improved,
                "broken_by_it": regressed,
                "unchanged": agreed,
                "p_value": round(p_value, 4),
                "earned_its_place": verdict,
                "reading": (
                    f"{improved} fixed, {regressed} broken, p={p_value:.3f}"
                    + (
                        " - a real improvement"
                        if verdict
                        else " - NO EVIDENCE that this component changes anything"
                        if improved <= regressed or p_value >= 0.05
                        else ""
                    )
                ),
            }
        )
        payload["components"].append(row)

    payload.update(
        {
            "ok": True,
            "ablated": len(arms),
            "earned_their_place": earned,
            "summary": (
                f"{earned} of {len(arms)} component(s) changed the score by more "
                "than noise on your own tasks."
                + (
                    ""
                    if earned == len(arms)
                    else " The rest are latency and a failure mode. Take one out "
                    "and measure again."
                )
            ),
        }
    )
    how = (
        f"paired {len(arms)} with/without run(s) over {tasks}, row by row, and "
        f"tested each with an exact two-sided McNemar; {earned} reached p<0.05 "
        "in the improving direction"
    )
    try:
        instrument.measured(
            "components_ablated_n", len(arms), how=how, from_file=str(tasks)
        )
        instrument.measured(
            "components_that_earned_their_place", earned, how=how, from_file=str(tasks)
        )
    except MeasurementError as error:  # pragma: no cover - no thread, no record
        payload["not_stamped"] = str(error)
    return payload


# ---------------------------------------------------------------------------
# G4 - what can it destroy?


def _annotated(entry: Any) -> bool:
    """Does this tool definition say what it can destroy?

    READ OFF THE FILE, NEVER INFERRED FROM A NAME. `delete_everything` is not
    annotated because it sounds like it; a tool called `sync` that carries
    `destructiveHint: true` is. MCP's own `annotations` block is the standard
    place and the other keys are what hand-written tool arrays tend to use.
    """
    if not isinstance(entry, Mapping):
        return False
    blocks: list[Any] = [entry]
    for key in ("annotations", "metadata", "x-annotations"):
        nested = entry.get(key)
        if isinstance(nested, Mapping):
            blocks.append(nested)
    for block in blocks:
        for key in RISK_KEYS:
            if key in block and block[key] is not None:
                return True
    return False


def _tool_entries(path: Path) -> tuple[list[Any], str]:
    """The raw tool objects in a definitions file, and how they were found."""
    try:
        document = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return [], "not JSON"
    for finder, why in (
        (agents._mcp_tools, "an MCP tools/list result"),
        (agents._tools_array, "a tools array"),
    ):
        found = finder(document)
        if found:
            return list(found), why
    return [], "no tool array this reader knows"


@tool(
    "read_the_tool_risks",
    description=(
        "Count the tools a harness can reach and how many of them say what they "
        "can destroy. Reads a saved MCP tools/list, an OpenAI or Anthropic "
        "tools array, or a Python file whose tools are decorated. It counts "
        "annotations; it never guesses a tool's risk from its name."
    ),
    schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The tool definitions file on this machine.",
            }
        },
        "required": ["path"],
    },
    reads=("filesystem",),
    writes=("facts",),
    measures=("harness_tools_n", "tools_risk_annotated_n"),
    provides=("harness.tools.risk",),
    label="Read the tool risks",
    group="Look",
    verb="count what your tools can destroy",
    order=64,
)
def read_the_tool_risks(path: str, *, instrument: Instrument) -> dict[str, Any]:
    """Two counts, and the second one is the gate.

    THE COUNT COMES FROM `agents.read_definitions` AND NOT FROM A SECOND READER.
    That function already knows the four shapes a tool file takes and it already
    quarantines every description it returns. A private parser here would be a
    second opinion about what a tool is, and the two would eventually disagree
    about a file in front of a person.

    What it does not return is the RAW annotations, because the AI ledger has no
    fact that needs them - so the risk count is taken from a second, narrow pass
    that looks only for the annotation keys and reads nothing else.

    **A Python source file cannot be annotated-counted and says so.**
    `read_definitions` reads decorated Python by AST rather than by import,
    which is right - importing a stranger's module executes it - and an AST walk
    that recovered arbitrary decorator keyword values would be re-implementing
    evaluation. So the count of annotated tools is zero there, with the reason
    in the payload rather than as a silent zero that fails the gate.
    """
    target = Path(path)
    read = agents.read_definitions(target)
    tools = list(read.get("tools") or [])
    payload: dict[str, Any] = {
        "path": str(target),
        "tools": tools,
        "refusals": list(read.get("refusals") or []),
        "tool_count": len(tools),
    }
    if payload["refusals"] and not tools:
        payload["ok"] = False
        return payload

    entries, how_found = _tool_entries(target)
    annotated = sum(1 for entry in entries if _annotated(entry))
    payload.update(
        {
            "ok": True,
            "risk_annotated": annotated,
            "annotations_read_from": how_found,
            "annotation_keys_looked_for": list(RISK_KEYS),
        }
    )
    if entries == [] and tools:
        payload["why_no_annotations_were_read"] = (
            f"{target} was read as {how_found}, so there is no JSON tool object "
            "to look for annotations in. A Python file's tools are read by AST "
            "rather than by import - importing a stranger's module executes it - "
            "and an AST walk that recovered arbitrary decorator values would be "
            "re-implementing evaluation. Export the tools your framework "
            "publishes and this reads them."
        )

    how = (
        f"read {len(tools)} tool definition(s) from {target} ({how_found}); "
        f"{annotated} of them carry one of {list(RISK_KEYS)}"
    )
    try:
        instrument.measured("harness_tools_n", len(tools), how=how, from_file=str(target))
        instrument.measured(
            "tools_risk_annotated_n", annotated, how=how, from_file=str(target)
        )
    except MeasurementError as error:  # pragma: no cover - no thread, no record
        payload["not_stamped"] = str(error)
    return payload


# ---------------------------------------------------------------------------
# G5 - what does one run cost, and does it stop?


@tool(
    "bound_the_harness_run",
    description=(
        "Read one or more OTLP traces of your harness running and report what a "
        "run costs in tokens and whether every run stopped. It reports tokens "
        "and refuses to turn them into money, because no price in a trace "
        "carries a date."
    ),
    schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "An OTLP trace file on this machine, or a folder of them."
                ),
            }
        },
        "required": ["path"],
    },
    reads=("filesystem", "traces"),
    writes=("facts",),
    measures=(
        "harness_spans_read",
        "harness_has_traces",
        "harness_tokens_per_run",
        "harness_run_terminates",
    ),
    provides=("harness.run.bound",),
    label="Bound the harness run",
    group="Look",
    verb="read one run's trace",
    order=65,
)
def bound_the_harness_run(path: str, *, instrument: Instrument) -> dict[str, Any]:
    """The same spans `bound_the_loop` reads, filed under this ledger's names.

    ## The duplication is the point

    Three of G5's facts are exactly the AI ledger's `has_traces`,
    `tokens_per_run` and `run_terminates`, and this ledger cannot use those
    names: `app/tools/registry.py`'s domain adoption resolves a tool's domain by
    finding the ONE ledger that declares the facts it measures, and a fact
    declared by two ledgers names no domain at all. So the facts are
    `harness_*`, and this tool reads the same file through the same helpers.

    Two domains asking the same question of one trace are still two domains. One
    fact answering for both would mean a person's traces opened a gate in a
    ledger they were never diagnosed under, which is the exact defect the
    disjointness rule exists to prevent.

    ## The partial-total refusal, inherited rather than re-argued

    `agents._tokens_of_run` refuses to total a run where any inference span
    carries no usage attributes, and this does not soften that. A total missing
    one span is a lower bound, and a lower bound is the number that is always
    smaller than the bill. When it refuses, `harness_tokens_per_run` is not
    stamped and G5 stays shut - which is correct, and the payload says which
    spans were missing so it is fixable rather than mysterious.
    """
    payload: dict[str, Any] = {"path": str(path), "refusals": []}
    read = agents.read_spans(path)
    spans = list(read.get("spans") or [])
    payload["refusals"].extend(read.get("refusals") or [])

    has_traces = bool(spans)
    payload["spans"] = len(spans)
    payload["has_traces"] = has_traces

    # THE COUNT BEFORE THE FLAG, for `read_the_success_check`'s reason and the
    # same wall. Zero spans is a real reading and a legal stamp - it is the
    # evidence behind `harness_has_traces: false`, which is what routes somebody
    # to SPEC__INSTRUMENT_THE_LOOP.
    try:
        instrument.measured(
            "harness_spans_read",
            len(spans),
            how=f"parsed {path} and read {len(spans)} span(s) out of it",
            from_file=str(path),
        )
        instrument.measured(
            "harness_has_traces",
            has_traces,
            how=(
                f"read {len(spans)} span(s) from {path}"
                if has_traces
                else f"found no readable spans at {path}"
            ),
            from_file=str(path),
        )
    except MeasurementError as error:  # pragma: no cover - no thread, no record
        payload["not_stamped"] = str(error)
    if not has_traces:
        payload["ok"] = False
        payload["summary"] = (
            f"Nothing recorded what happened at {path}. Every question left - "
            "what a run costs, whether it stops, which tool failed - is answered "
            "by reading one trace, and none of them can be answered by "
            "remembering."
        )
        return payload

    runs = agents.runs_of(spans)
    totals: list[int] = []
    incomplete: list[dict[str, Any]] = []
    stopped: list[bool | None] = []
    for run_id, run_spans in sorted(runs.items()):
        tokens = agents._tokens_of_run(run_spans)
        if tokens.get("ok"):
            totals.append(int(tokens["total"]))
        else:
            incomplete.append({"run": run_id, "why": tokens.get("why")})
        stopped.append(agents._terminated(run_spans))

    payload.update(
        {
            "ok": True,
            "runs": len(runs),
            "runs_with_a_complete_token_total": len(totals),
            "runs_whose_total_is_incomplete": incomplete,
            "runs_that_stopped": sum(1 for one in stopped if one is True),
            "runs_whose_ending_could_not_be_read": sum(1 for one in stopped if one is None),
        }
    )

    every_run_stopped = bool(stopped) and all(one is True for one in stopped)
    try:
        instrument.measured(
            "harness_run_terminates",
            every_run_stopped,
            how=(
                f"every one of {len(runs)} run(s) in {path} was checked for a root "
                f"span that ended; {sum(1 for one in stopped if one is True)} "
                "did"
            ),
            from_file=str(path),
        )
    except MeasurementError as error:  # pragma: no cover - no thread, no record
        payload.setdefault("not_stamped", str(error))

    if incomplete or not totals:
        payload["tokens_per_run_not_stamped"] = (
            f"{len(incomplete)} of {len(runs)} run(s) carry an inference span "
            "with no token counts, so no total here would be a total. A partial "
            "sum is a lower bound, and a lower bound is the number that is "
            "always smaller than the bill."
        )
        return payload

    ordered = sorted(totals)
    median = float(ordered[len(ordered) // 2])
    payload["tokens_per_run"] = median
    payload["token_totals"] = ordered
    try:
        instrument.measured(
            "harness_tokens_per_run",
            median,
            how=(
                f"median across {len(totals)} run(s) in {path}, each total summed "
                "from every inference span's usage attributes"
            ),
            from_file=str(path),
        )
    except MeasurementError as error:  # pragma: no cover - no thread, no record
        payload.setdefault("not_stamped", str(error))
    return payload


__all__ = [
    "read_the_success_check",
    "count_the_task_set",
    "score_a_recorded_run",
    "ablate_a_component",
    "read_the_tool_risks",
    "bound_the_harness_run",
    "THE_RUNGS",
    "RISK_KEYS",
    "PROGRAM_MARKERS",
]
