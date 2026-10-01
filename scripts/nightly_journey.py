#!/usr/bin/env python3
"""ONE live journey a night, scored into one row pinned to the commit.

## Why this is in the tree

Max, on what the product has to do: *"a massive prompt and the whole thing
finishes from end to end on itself"*. That is a sentence, not a number, so on
any given morning nothing in this repository could say whether last night's
tree was better at it than the night before. Every end-to-end walk this
project has taken was driven by hand, read once, and argued from afterwards -
which is the same hole `scripts/harvest_the_walls.py` was written to close for
the wall figures, and it closed it by keeping the driver.

This is that walk, kept, and taken at 03:30 by
`scripts/schedule_nightly_journey.ps1`.

## What it is NOT

It is not a test. It needs a live model, a live card and about an hour, and it
is ALLOWED TO PRODUCE A BAD ROW. A run that parked every step, asked four
questions and measured nothing is a finding: it is written down, and the exit
code is 0. A driver that exited non-zero on a bad result is a driver somebody
switches off in week two, and the row nobody wrote is the regression nobody
saw.

Exit 2 is reserved for "the instrument could not take a reading at all" - the
engine did not come up, or Ollama did not answer, or the model is not on this
machine - and it says which of those it was. There is no exit 1 on this path.

## The seven numbers

`docs/score_rows/README.md` is the definition and this file is the
implementation; the seven functions below are named after the seven columns so
a reader can put them side by side. Each is a different way "it finished on its
own" fails, and a single did-it-finish would hide all seven:

    plan_written_on_turn_1        did it plan before the run started taking turns
    steps_ticked / open_at_start  how much of its own plan it actually worked
    refusals_per_call             how often the harness said no to its own model
    empty_replies / replies       how often a turn ended with nothing said
    tokens_before_first_word      the fixed cost of every turn, before any work
    questions_asked               it was told not to ask, in full mode
    minutes_to_first_measurement  how long before an instrument produced a fact

## It cannot touch the owner's install

Every live journey gets a FRESH data root under the machine's temp directory,
and the engine child is started with `MLH_DATA_ROOT` pointing at it - so the
database, the portfile, the token and the run artifacts are all in the scratch
directory and the owner's `ml_harness.db` is not opened by anything this file
starts. The guard is `why_this_root_is_not_scratch`; it decides "is this a
checkout" with `app/paths.py`'s OWN marker rather than a second opinion, for
the reason that module gives about `diagnosis._ledger_root`; and it runs on the
dry path too, because `--from-root` is a directory somebody types.

Port 8078 is refused by name. It is the owner's running app.

## The dry path, and why the arithmetic is separately testable

`--dry-run --from-root <root>` starts no engine, needs no Ollama, and computes
the row from a database that is already on disk. That is what makes the seven
definitions testable at all: a test can append known events into a sandbox
database and assert each number, which is impossible against a live model whose
transcript is different every night.

Usage:
    python scripts/nightly_journey.py
    python scripts/nightly_journey.py --port 8079 --minutes-cap 45
    python scripts/nightly_journey.py --dry-run --from-root C:/Temp/mlh-nightly/2026-09-18
"""

# NO `from __future__ import annotations` IN THIS FILE, AND IT IS NOT AN
# OVERSIGHT. That import turns every annotation into a string, and a string
# annotation on a `@dataclass` is resolved at class-creation time through
# `sys.modules[cls.__module__]`. `tests/support.py::import_file` loads a script
# by path WITHOUT registering it in `sys.modules` - deliberately, so the import
# leaves nothing behind - so that lookup returns `None` and the dataclass fails
# to build with `AttributeError: 'NoneType' object has no attribute '__dict__'`,
# at import, before one test has run. This repository is Python 3.11, where
# `str | None` and `dict[str, Any]` are native at runtime and the import buys
# nothing this file needs.

import argparse
import datetime as dt
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import paths  # noqa: E402  - after the sys.path insert, on purpose


#: 8079 rather than 8078. Every note in this tree says the same thing: 8078 is
#: the engine the owner has open in front of him, and a nightly job that
#: restarted it would take his session away at 03:30.
DEFAULT_PORT = 8079

#: THE OWNER'S PORT, refused by name rather than by convention. A default that
#: is merely different is one `--port 8078` away from the failure.
HIS_PORT = 8078

#: MAX'S CALL, 2026-09-08, same as `scripts/harvest_the_walls.py`: the swap is
#: his and every result already in `runs/` remains a granite result.
DEFAULT_MODEL = "minicpm5-hermes:latest"
DEFAULT_OLLAMA = "http://127.0.0.1:11434"

#: His own dataset, on his own machine. A journey against a fixture would
#: measure the fixture. Written with forward slashes and handed to `Path`,
#: which prints it back in this machine's own spelling.
#: Read from the environment rather than written here: a shipped file must
#: not name a person's machine (tests/test_no_shipped_file_names_a_person.py).
#: `MLH_DATASET_ROOT` on the scheduler's task, or --dataset-root on the call.
DEFAULT_DATASET_ROOT = (
    Path(os.environ["MLH_DATASET_ROOT"]) if os.environ.get("MLH_DATASET_ROOT") else None
)

DEFAULT_BRIEF = REPO / "docs" / "score_rows" / "brief.md"
DEFAULT_OUT = REPO / "docs" / "score_rows"
DEFAULT_MINUTES_CAP = 60.0

#: The name every scratch root sits under, so a morning's inspection is one
#: directory listing and a clean-up is one delete.
SCRATCH_PARENT = "mlh-nightly"

#: THE HEADER IS THE CONTRACT. Every ratio carries its denominator beside it,
#: because a rate whose bottom half the reader cannot recover is a mood rather
#: than a measurement - the rule `docs/score_rows/README.md` states and the one
#: `kept: 164` cost this project two days.
CSV_HEADER = (
    "date,sha,model,"
    "plan_written_on_turn_1,"
    "steps_ticked,steps_open_at_run_start,"
    "refusals,tool_calls,refusals_per_call,"
    "empty_replies,replies,"
    "tokens_before_first_word,"
    "questions_asked,"
    "minutes_to_first_measurement,"
    "stop_reason"
)

#: What the seven readings are taken from. Named here rather than spelled into
#: each function so the README and the code cannot drift apart silently.
PLAN_WRITTEN = "thread.plan_written"
PLAN_ADOPTED = "thread.plan_adopted"
RUN_TURN = "run.turn"
RUN_STARTED = "run.started"
RUN_FINISHED = "run.finished"
TOOL_CALL = "tool.call"
TOOL_RESULT = "tool.result"
CHAT_DELTA = "chat.delta"
STREAM_END = "stream.end"
TURN_CONTEXT = "turn.context"
THREAD_PERMISSION = "thread.permission"

#: `app/diagnosis.py::MEASURED`. An instrument produced it while the
#: conversation was happening; everything else in `fact_evidence` is a claim.
MEASURED = "MEASURED"

#: The permission this journey runs at, and the one `questions_asked` is
#: counted under. `app/autonomy.py`.
FULL = "full"

#: One newline, built rather than typed, because this file is written by
#: tooling that has eaten an escape before.
NL = chr(10)


class Unreachable(Exception):
    """The instrument could not take a reading. Exit 2, and say which."""


# ---------------------------------------------------------------------------
# The guard. It runs before anything is created and before anything is read.


def why_this_root_is_not_scratch(root: Path) -> str | None:
    """A sentence when `root` must not be used as a data root, else `None`.

    THE ONE THING THIS SCRIPT MUST NEVER DO is point an engine - or a reader -
    at the working tree. `MLH_DATA_ROOT` moves the database, the portfile and
    the runs directory together (`app/paths.py`), so a root that is a checkout
    is a night spent writing into somebody's repository, and on this machine
    the checkout in question holds the owner's real `ml_harness.db`.

    The test for "is this a checkout" is `paths.CHECKOUT_MARKER`, not a second
    opinion. `app/paths.py` says why in its own words: two functions deciding
    "am I in a repository" by two different tests are two answers waiting to
    disagree on the machine where it matters.

    A root INSIDE the checkout is refused as well, and so is an ANCESTOR of it.
    Neither carries the marker, and both would put an engine's database
    somewhere a `git status` is about to complain about.
    """
    resolved = Path(root).expanduser().resolve()
    if (resolved / paths.CHECKOUT_MARKER).is_file():
        return (
            f"{resolved} holds {paths.CHECKOUT_MARKER.as_posix()}, which is what "
            "app/paths.py calls a CHECKOUT. Pointing MLH_DATA_ROOT at it would "
            "put this journey's database, portfile and runs inside the working "
            "tree - and on this machine that tree holds the owner's real "
            "ml_harness.db. Use a scratch root."
        )
    if resolved == REPO:
        return f"{resolved} is this checkout itself. Use a scratch root."
    if REPO in resolved.parents:
        return (
            f"{resolved} is inside the checkout at {REPO}. A data root under "
            "the working tree is still the working tree. Use a scratch root."
        )
    if resolved in REPO.parents:
        return (
            f"{resolved} is a parent of the checkout at {REPO}, so a data root "
            "there would swallow the repository. Use a scratch root."
        )
    return None


def refuse_unless_scratch(root: Path) -> Path:
    """`root`, resolved, or `Unreachable` carrying the sentence above."""
    complaint = why_this_root_is_not_scratch(root)
    if complaint:
        raise Unreachable(complaint)
    return Path(root).expanduser().resolve()


def scratch_root_for(today: str, parent: Path | None = None) -> Path:
    """A FRESH directory for tonight, never an existing one reopened.

    A second run on one day gets `-2`, `-3`, and so on. Reusing the directory
    would mix two journeys into one database, and the row computed from it
    would be an average of two nights presented as one.
    """
    base = parent or temp_parent()
    candidate = base / today
    suffix = 2
    while candidate.exists():
        candidate = base / f"{today}-{suffix}"
        suffix += 1
    return candidate


def temp_parent() -> Path:
    """LOCALAPPDATA over Temp over `mlh-nightly`, built piece by piece.

    LOCAL rather than ROAMING for `app/paths.py`'s reason - this directory
    holds a SQLite database and run artifacts, and none of that should be
    copied across a network at login.
    """
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "Temp" / SCRATCH_PARENT
    import tempfile

    return Path(tempfile.gettempdir()) / SCRATCH_PARENT


# ---------------------------------------------------------------------------
# What one journey left behind, read back out of its database.


@dataclass
class Journey:
    """Everything the seven readings are taken from, read once.

    A dataclass rather than seven queries so that every number in one row comes
    from ONE read of the database. Two readings taken a second apart while a
    run is still finishing would disagree with each other, and the row would
    have no moment it was true at.
    """

    db_path: Path
    thread: dict[str, Any]
    events: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    facts: list[dict[str, Any]] = field(default_factory=list)
    long_run: dict[str, Any] | None = None

    def of_kind(self, kind: str) -> list[dict[str, Any]]:
        return [row for row in self.events if row["kind"] == kind]

    def first(self, kind: str) -> dict[str, Any] | None:
        for row in self.events:
            if row["kind"] == kind:
                return row
        return None


def _decode(row: sqlite3.Row) -> dict[str, Any]:
    out = dict(row)
    body = out.pop("payload_json", None)
    if body is not None:
        try:
            out["payload"] = json.loads(body)
        except (TypeError, ValueError):
            out["payload"] = {}
    return out


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    found = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return found is not None


def read_journey(db_path: Path, thread_id: int | None = None) -> Journey:
    """Read one thread's whole record out of a database, read-only.

    `thread_id=None` means THE NEWEST THREAD, which is the right default for
    exactly one reason: a scratch root holds one journey. Against any other
    database it would be a guess, which is why `--from-root` is guarded and
    why `--thread` exists.

    Opened `mode=ro` through a URI. A reader that could write is a reader that
    can corrupt the thing it was sent to inspect, and this one runs against a
    directory somebody typed.
    """
    path = Path(db_path)
    if not path.is_file():
        raise Unreachable(f"there is no database at {path}")
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        if thread_id is None:
            row = connection.execute(
                "SELECT id FROM threads ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row is None:
                raise Unreachable(f"{path} holds no threads - no journey ran")
            thread_id = int(row["id"])
        thread = connection.execute(
            "SELECT * FROM threads WHERE id = ?", (thread_id,)
        ).fetchone()
        if thread is None:
            raise Unreachable(f"{path} has no thread {thread_id}")
        events = [
            _decode(row)
            for row in connection.execute(
                "SELECT * FROM events WHERE thread_id = ? ORDER BY id ASC",
                (thread_id,),
            ).fetchall()
        ]
        messages = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM messages WHERE thread_id = ? ORDER BY id ASC",
                (thread_id,),
            ).fetchall()
        ]
        facts: list[dict[str, Any]] = []
        if _table_exists(connection, "fact_evidence"):
            facts = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM fact_evidence WHERE thread_id = ? ORDER BY id ASC",
                    (thread_id,),
                ).fetchall()
            ]
        long_run: dict[str, Any] | None = None
        if _table_exists(connection, "long_runs"):
            found = connection.execute(
                "SELECT * FROM long_runs WHERE thread_id = ?", (thread_id,)
            ).fetchone()
            long_run = dict(found) if found is not None else None
        return Journey(
            db_path=path,
            thread=dict(thread),
            events=events,
            messages=messages,
            facts=facts,
            long_run=long_run,
        )
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# The seven readings. One function each, named after its column.


def plan_written_on_turn_1(journey: Journey) -> bool:
    """Was a plan written BEFORE the run took its first turn?

    The boundary is the first `run.turn` event - the row `app/longrun.py`
    writes after each turn of the run - and the question is whether a
    `thread.plan_written` row sits before it. Both the tool (`write_plan`) and
    the prose path (`app/conductor.py`, a plan-mode reply carrying `## Phase`
    headings) write that row, so this counts a plan however it arrived.

    A journey with no `run.turn` at all has no boundary, so any plan row
    counts: nothing came after it to be late for.
    """
    first_turn = journey.first(RUN_TURN)
    boundary = int(first_turn["id"]) if first_turn else None
    for kind in (PLAN_WRITTEN, PLAN_ADOPTED):
        for row in journey.of_kind(kind):
            if boundary is None or int(row["id"]) < boundary:
                return True
    return False


def steps_ticked(journey: Journey) -> tuple[int, int]:
    """`(ticked, open at run start)`, read from two places on purpose.

    The denominator is `run.started`'s own `open` count - what the plan had to
    do when the run began. The numerator is the FINAL plan text, parsed by
    `app/tools/planning.py::steps_in`, which is the same parser the run itself
    ticks and parks through. One reader for one source: a second step parser
    in this file would disagree with the product's within a month.

    Why not `run.finished`'s `done`: a run stopped at the minutes cap never
    writes one, and a number that is absent exactly when the night went badly
    is the wrong number.
    """
    started = journey.first(RUN_STARTED)
    open_at_start = int((started or {}).get("payload", {}).get("open") or 0)
    ticked = sum(
        1 for step in _steps_in(_plan_text(journey)) if step["state"] == "done"
    )
    return ticked, open_at_start


def refusals_per_call(journey: Journey) -> tuple[int, int, float]:
    """`(refusals, calls, rate)` - how often the harness said no to its model.

    A refusal is a `tool.result` whose `ok` is false, OR whose `result` carries
    an `error`. Both shapes are in the transcript: `app/conductor.py` writes
    `ok: False` for a wall it raised itself, and a tool that ran and failed
    hands back a result dict with `error` in it while `ok` may still be true.
    Counting only the first shape undercounts, and this product has already
    paid once for a detector that could only see one spelling of the thing it
    was watching (`scripts/did_it_answer_the_question.py`).

    The rate is over `tool.call`, not over turns: the question is what fraction
    of the model's reaches came back empty-handed. No calls is a rate of 0.0,
    and the numerator beside it in the row says so.
    """
    calls = len(journey.of_kind(TOOL_CALL))
    refused = 0
    for row in journey.of_kind(TOOL_RESULT):
        payload = row.get("payload") or {}
        result = payload.get("result")
        if payload.get("ok") is False:
            refused += 1
        elif isinstance(result, dict) and result.get("error"):
            refused += 1
    rate = round(refused / calls, 4) if calls else 0.0
    return refused, calls, rate


def empty_replies(journey: Journey) -> tuple[int, int]:
    """`(empty, replies)` - turns that ended having said nothing.

    A reply is one `stream.end`. It is EMPTY when no `chat.delta` between it
    and the previous `stream.end` carried any non-blank text. Counted by
    walking the events in id order rather than by reading a field, because
    `stream.end` carries an `ending` and a round count and never carried a
    character count - and a reading taken from the deltas is the same thing the
    person saw on the screen.
    """
    replies = 0
    empty = 0
    spoken = ""
    for row in journey.events:
        if row["kind"] == CHAT_DELTA:
            spoken += str((row.get("payload") or {}).get("text") or "")
        elif row["kind"] == STREAM_END:
            replies += 1
            if not spoken.strip():
                empty += 1
            spoken = ""
    return empty, replies


def tokens_before_first_word(journey: Journey) -> int:
    """The fixed cost of the first turn: system prompt plus tool schemas.

    Taken from the FIRST `turn.context` row, which `app/conductor.py` writes at
    the moment it has the assembled conversation and the tool schemas in hand -
    the two things that actually go on the wire, counted by the same counter
    both adapters use. `system + tools` and not `total`, because `history` is
    what the work accumulated and this number is what the product charges
    before any work has happened.

    Zero when no turn was ever assembled, which is itself the finding.
    """
    first = journey.first(TURN_CONTEXT)
    if first is None:
        return 0
    payload = first.get("payload") or {}
    return int(payload.get("system") or 0) + int(payload.get("tools") or 0)


def questions_asked(journey: Journey) -> int:
    """Assistant messages ending in a question mark, while permission was full.

    The brief says *"Full mode: do not ask me anything, decide yourself"*, so
    every one of these is the product ignoring an instruction it was given, and
    at 03:30 there is nobody to answer.

    WHILE FULL, and that qualifier is doing work. A thread opens in `plan` at
    `ask` (`app/modes.py`), where a question is the correct behaviour; the
    permission timeline is read from the `thread.permission` events, and a
    message is counted under the last permission set at or before its own
    timestamp. Both timestamps are the database's own `CURRENT_TIMESTAMP`, so
    they are the same clock to the second; a tie goes to the permission event,
    which is the order this driver performs them in.
    """
    windows = [
        (
            str(row.get("ts") or ""),
            str((row.get("payload") or {}).get("permission") or ""),
        )
        for row in journey.of_kind(THREAD_PERMISSION)
    ]
    asked = 0
    for message in journey.messages:
        if str(message.get("role") or "") != "assistant":
            continue
        if not str(message.get("content") or "").rstrip().endswith("?"):
            continue
        at = str(message.get("created_at") or "")
        permission = ""
        for ts, mode in windows:
            if ts <= at:
                permission = mode
        if permission == FULL:
            asked += 1
    return asked


def minutes_to_first_measurement(journey: Journey) -> float | None:
    """Minutes from the thread being created to the first MEASURED fact.

    A MEASURED row in `fact_evidence` is an instrument having produced a number
    while the conversation was happening (`app/diagnosis.py`); everything else
    in that table is a claim. So this is the time from "the person asked" to
    "something was actually read off this machine", which is the half of
    end-to-end that a transcript full of confident prose can hide completely.

    `None` when the journey never measured anything. NOT zero: zero would read
    as instant.
    """
    created = _stamp(journey.thread.get("created_at"))
    if created is None:
        return None
    for fact in journey.facts:
        if str(fact.get("origin") or "") != MEASURED:
            continue
        at = _stamp(fact.get("created_at"))
        if at is None:
            continue
        return round(max(0.0, (at - created).total_seconds()) / 60.0, 2)
    return None


def _stamp(value: Any) -> dt.datetime | None:
    """SQLite's `CURRENT_TIMESTAMP` as a datetime, or `None`.

    Both ends of every subtraction here are the table's own clock, in UTC, and
    never this process's - the arithmetic is between two of ours.
    """
    text = str(value or "").strip()
    if not text:
        return None
    for shape in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(text, shape)
        except ValueError:
            continue
    return None


def _plan_text(journey: Journey) -> str:
    """The checklist this run worked - the plan, or the todo when it said so.

    `app/tools/planning.py::checklist_text`'s rule, applied to a row read out
    of SQLite rather than through `events.get_thread`.
    """
    thread = journey.thread
    if str(thread.get("checklist_source") or "plan") == "todo":
        return str(thread.get("todo") or "")
    return str(thread.get("plan") or "")


def _steps_in(text: str) -> list[dict[str, Any]]:
    """The product's own step parser, imported late and used as a pure function.

    Late because importing `app.tools.planning` pulls in the registry and the
    event spine, and this module is imported by a test that has already bound
    its own database - nothing here opens one, and the import is deferred so
    that reading a row never depends on the product's import graph for any
    other reason.
    """
    from app.tools import planning

    return planning.steps_in(text)


def parked_steps(journey: Journey) -> list[dict[str, str]]:
    """Every parked step with the reason written on its line, in plan order."""
    return [
        {"step": step["text"], "why": step["why"]}
        for step in _steps_in(_plan_text(journey))
        if step["state"] == "parked"
    ]


def stop_reason(journey: Journey) -> tuple[str, str, int]:
    """`(reason, detail, turns)` for the run, from the durable table first.

    `long_runs` is what `app/longrun.py` writes on every transition, including
    the one a `run.finished` event is never written for: a run stopped by hand
    or by this driver's minutes cap breaks the loop without finishing. A row
    that reported nothing in exactly that case would be silent about the
    nights that went long, which are the nights worth reading.
    """
    run = journey.long_run or {}
    reason = str(run.get("stop_reason") or "")
    detail = str(run.get("detail") or "")
    turns = int(run.get("turns") or 0)
    if not reason:
        finished = journey.first(RUN_FINISHED)
        if finished:
            payload = finished.get("payload") or {}
            reason = str(payload.get("reason") or "")
            detail = str(payload.get("detail") or "")
            turns = int(payload.get("turns") or turns)
    if not reason:
        state = str(run.get("state") or "")
        reason = f"did_not_finish ({state})" if state else "no_run"
        detail = detail or "the run has no stop reason in long_runs"
    return reason, detail, turns


# ---------------------------------------------------------------------------
# The row.


@dataclass
class Row:
    """One night, as it will be read next morning."""

    date: str
    sha: str
    model: str
    thread_id: int
    plan_written_on_turn_1: bool
    steps_ticked: int
    steps_open_at_run_start: int
    refusals: int
    tool_calls: int
    refusals_per_call: float
    empty_replies: int
    replies: int
    tokens_before_first_word: int
    questions_asked: int
    minutes_to_first_measurement: float | None
    stop_reason: str
    stop_detail: str
    turns: int
    parked: list[dict[str, str]]
    plan: str
    scratch_root: str = ""
    #: What the DRIVER saw, which is not in the database: the cap it stopped
    #: at, or the sentence a broken-off journey ended on. It goes on the page
    #: and not in the CSV - the CSV is the seven numbers and the run's own stop
    #: reason, and a column that only sometimes has anything in it is a column
    #: every reader has to learn to ignore.
    driver_note: str = ""

    @property
    def sha7(self) -> str:
        return (self.sha or "unknown")[:7]

    def csv_line(self) -> str:
        minutes = (
            ""
            if self.minutes_to_first_measurement is None
            else f"{self.minutes_to_first_measurement}"
        )
        fields = [
            self.date,
            self.sha,
            self.model,
            "yes" if self.plan_written_on_turn_1 else "no",
            str(self.steps_ticked),
            str(self.steps_open_at_run_start),
            str(self.refusals),
            str(self.tool_calls),
            f"{self.refusals_per_call}",
            str(self.empty_replies),
            str(self.replies),
            str(self.tokens_before_first_word),
            str(self.questions_asked),
            minutes,
            self.stop_reason,
        ]
        return ",".join(_csv_safe(value) for value in fields)


def _csv_safe(value: str) -> str:
    """One field, with the characters that would break a line taken out.

    Quoting would be the other answer and this file does not take it: a row
    file is read by eye and by `grep` as often as by a parser, and a stop
    reason with a comma in it is a stop reason this product wrote, not data
    from outside. Replacing the comma is visible; a quoted field that a later
    `cut -d,` splits down the middle is not.
    """
    out = str(value).replace(",", ";")
    return out.replace(NL, " ").replace(chr(13), " ")


def score(
    db_path: Path,
    model: str,
    sha: str,
    today: str,
    thread_id: int | None = None,
) -> Row:
    """One database in, one row out. The whole of the arithmetic.

    Nothing in here starts a process, opens a socket or writes a file, which is
    what makes `--dry-run` a real rehearsal of the live path rather than a
    different program that resembles it.
    """
    journey = read_journey(db_path, thread_id=thread_id)
    ticked, open_at_start = steps_ticked(journey)
    refused, calls, rate = refusals_per_call(journey)
    empty, replies = empty_replies(journey)
    reason, detail, turns = stop_reason(journey)
    return Row(
        date=today,
        sha=sha,
        model=model,
        thread_id=int(journey.thread.get("id") or 0),
        plan_written_on_turn_1=plan_written_on_turn_1(journey),
        steps_ticked=ticked,
        steps_open_at_run_start=open_at_start,
        refusals=refused,
        tool_calls=calls,
        refusals_per_call=rate,
        empty_replies=empty,
        replies=replies,
        tokens_before_first_word=tokens_before_first_word(journey),
        questions_asked=questions_asked(journey),
        minutes_to_first_measurement=minutes_to_first_measurement(journey),
        stop_reason=reason,
        stop_detail=detail,
        turns=turns,
        parked=parked_steps(journey),
        plan=_plan_text(journey),
    )


def markdown(row: Row) -> str:
    """The night, written for a person reading it over coffee.

    The table first, because the seven numbers are the thing that is compared
    between nights. The facts second, because the first question a bad number
    raises is "against what" - the sha, the model and the stop reason answer
    it. The plan last and VERBATIM, because a plan summarised is a plan whose
    steps nobody can check against the ticks.
    """
    minutes = (
        "not measured"
        if row.minutes_to_first_measurement is None
        else f"{row.minutes_to_first_measurement}"
    )
    planned = "yes" if row.plan_written_on_turn_1 else "no"
    lines = [
        f"# Nightly journey {row.date} at {row.sha7}",
        "",
        "| number | value | out of |",
        "| --- | --- | --- |",
        f"| plan_written_on_turn_1 | {planned} | before the first run.turn |",
        f"| steps_ticked | {row.steps_ticked} | {row.steps_open_at_run_start} open at run start |",
        f"| refusals_per_call | {row.refusals_per_call} | {row.refusals} of {row.tool_calls} calls |",
        f"| empty_replies | {row.empty_replies} | {row.replies} replies |",
        f"| tokens_before_first_word | {row.tokens_before_first_word} | system + tools; first turn |",
        f"| questions_asked | {row.questions_asked} | assistant messages; while full |",
        f"| minutes_to_first_measurement | {minutes} | thread created to first MEASURED fact |",
        "",
        "## Facts",
        "",
        f"- sha: `{row.sha}`",
        f"- model: `{row.model}`",
        f"- thread: {row.thread_id}",
        f"- stop reason: `{row.stop_reason}`",
        f"- stop detail: {row.stop_detail or '-'}",
        f"- turns: {row.turns}",
        f"- what the driver saw: {row.driver_note or 'the run ended on its own'}",
        f"- scratch root: `{row.scratch_root or '-'}`",
        "",
        f"## Parked steps ({len(row.parked)})",
        "",
    ]
    if row.parked:
        for parked in row.parked:
            why = parked["why"] or "no reason written"
            lines.append(f"- {parked['step']} - {why}")
    else:
        lines.append("- none")
    #: A FENCE LONGER THAN ANYTHING INSIDE IT. A plan is written by a model
    #: that has been asked for a training plan, so it arrives with code blocks
    #: in it more often than not - and a three-backtick fence around a plan
    #: containing three backticks ends the block halfway down the page, with
    #: the rest of the plan rendering as prose. Markdown's own rule is that the
    #: fence may be longer, so it is made longer.
    # QUOTED, NOT FENCED. A plan carries its own `## Phase` headings, and a
    # fenced block does not stop a markdown carver from splitting the page on
    # them - the second row's file was cut inside its own fence, which
    # tests/test_a_carved_answer_is_whole.py caught. `app/conductor.py`'s plan
    # note quotes every line with `> ` for the same reason, so this does too.
    plan_text = row.plan.rstrip() or "(no plan was written)"
    lines += [
        "",
        "## The plan, verbatim",
        "",
        *("> " + line for line in plan_text.splitlines()),
        "",
    ]
    return NL.join(lines)


def write_the_row(row: Row, out: Path) -> tuple[Path, Path]:
    """The night's page, and ONE line appended to `rows.csv`.

    One line per run, appended, with the header written only when the file is
    not there. A rewritten table is a table that can lose a night; an appended
    line can only ever lose the night it failed on.
    """
    out.mkdir(parents=True, exist_ok=True)
    page = out / f"{row.date}-{row.sha7}.md"
    page.write_bytes(markdown(row).encode("utf-8"))
    table = out / "rows.csv"
    body = "" if table.exists() else CSV_HEADER + NL
    with table.open("ab") as handle:
        handle.write((body + row.csv_line() + NL).encode("utf-8"))
    return page, table


# ---------------------------------------------------------------------------
# The live half: an engine of our own, on a port that is not his.


def _request(
    method: str,
    url: str,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = response.getcode()
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        status = error.code
    except (urllib.error.URLError, OSError) as error:
        return 0, str(error)
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw


def _must(
    method: str,
    url: str,
    token: str,
    body: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> Any:
    status, payload = _request(method, url, token=token, body=body, timeout=timeout)
    if status == 0 or status >= 400:
        raise Unreachable(f"{method} {url} answered {status}: {payload!r}")
    return payload


def start_engine(
    port: int, data_root: Path, log: Path, token: str, nonce: str
) -> subprocess.Popen:
    """Uvicorn, in its own data root, with its output going to a file we keep.

    No `--reload`, for `scripts/launch.py`'s reason: reload puts a supervisor
    between the pid that answers and the pid that owns the socket. Not
    detached, for the opposite of that file's reason - this parent is the only
    thing that will ever stop this child, so it holds the handle.
    """
    child = dict(os.environ)
    child["MLH_DATA_ROOT"] = str(data_root)
    child["MLH_PORT"] = str(port)
    child["MLH_TOKEN"] = token
    child["MLH_LAUNCH_NONCE"] = nonce
    child["PYTHONIOENCODING"] = "utf-8"
    #: NOT INHERITED. `ML_HARNESS_DB` and `MLH_ENGINE_FILE` BEAT MLH_DATA_ROOT
    #: in `app/paths.py`, by design - so a shell that happens to have either of
    #: them set would send this journey's writes straight back to whatever they
    #: name, which on this machine is the owner's own database.
    child.pop("ML_HARNESS_DB", None)
    child.pop("MLH_ENGINE_FILE", None)
    log.parent.mkdir(parents=True, exist_ok=True)
    handle = log.open("wb")
    command = [
        paths.python_executable(),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "info",
    ]
    return subprocess.Popen(
        command,
        cwd=str(REPO),
        env=child,
        stdout=handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
    )


def wait_for_health(
    child: subprocess.Popen, port: int, nonce: str, timeout: float = 90.0
) -> dict[str, Any]:
    """Wait until THIS child says it is ready, and take the sha from its mouth.

    `expect_launch` is the nonce this process invented and handed the child in
    its environment, which is the check `scripts/launch.py` had to learn the
    hard way: a pid comparison fails on this machine because the venv's
    `python.exe` re-execs, and a value the child carries does not.
    """
    deadline = time.monotonic() + timeout
    last = "nothing answered"
    while time.monotonic() < deadline:
        code = child.poll()
        if code is not None:
            raise Unreachable(
                f"the engine exited with code {code} before it was ready - the "
                "engine could not be reached"
            )
        status, payload = _request(
            "GET",
            f"http://127.0.0.1:{port}/health?expect_launch={nonce}",
            timeout=5.0,
        )
        if status == 200 and isinstance(payload, dict):
            return payload
        if status == 409:
            raise Unreachable(
                f"something else is already an ML Harness engine on {port} and "
                "it is not the one this driver started - nothing was "
                "terminated. The engine could not be reached."
            )
        last = f"status {status}"
        time.sleep(0.5)
    raise Unreachable(
        f"the engine did not become ready on {port} within {timeout:.0f}s "
        f"(last: {last}) - the engine could not be reached"
    )


def check_ollama(base_url: str, model: str) -> None:
    """Ollama is up AND has this model. Two questions, two failures.

    "The model could not be reached" and "Ollama could not be reached" send a
    person to two different places at 08:00, so they are never collapsed into
    one sentence here.
    """
    status, payload = _request("GET", f"{base_url.rstrip('/')}/api/tags", timeout=10.0)
    if status != 200 or not isinstance(payload, dict):
        raise Unreachable(
            f"Ollama did not answer at {base_url} (status {status}) - the model "
            "could not be reached because its server is not there"
        )
    names = {str(row.get("name") or "") for row in (payload.get("models") or [])}
    if model not in names:
        listed = "; ".join(sorted(names)) or "(nothing)"
        raise Unreachable(
            f"Ollama at {base_url} is up and does not have {model!r}. It has: "
            f"{listed} - the model could not be reached"
        )


def drive(
    port: int,
    token: str,
    dataset_root: Path,
    model: str,
    ollama: str,
    brief: str,
    minutes_cap: float,
) -> tuple[int, str]:
    """The journey itself: connect, project, thread, full, the brief, the run.

    Returns `(thread id, note)`. Every step is the same HTTP door the desktop
    app presses, in the order a person presses them - a driver that reached
    past the routes would be measuring something no user can run.

    THE SEAM IS THE THREAD. Everything before it - the connection, the probe,
    the project - failing means the instrument never took a reading, and that
    is the exit-2 case. Everything after it failing is a JOURNEY THAT WENT
    BADLY, which is a row: the turn timed out, the run 500'd, the engine fell
    over halfway. Those are exactly the nights worth having a number for, and
    a driver that turned them into exit 2 and no row would go quiet on the
    worst ones. The sentence comes back as the note and lands on the page.
    """
    base = f"http://127.0.0.1:{port}"
    provider = _must(
        "POST",
        f"{base}/api/providers",
        token,
        {
            "name": "Nightly",
            "base_url": ollama,
            "model": model,
            "adapter": "ollama",
        },
    )
    provider_id = int(provider["id"])
    #: PROBE BEFORE ACTIVATE. The capability reading is what tells the
    #: conductor whether this model can call tools at all, and a journey driven
    #: by a connection that never answered that question would be measuring the
    #: default rather than the model.
    _must("POST", f"{base}/api/providers/{provider_id}/probe", token, timeout=180.0)
    _must("POST", f"{base}/api/providers/{provider_id}/activate", token)

    project = _must(
        "POST",
        f"{base}/api/projects",
        token,
        {
            "name": f"Nightly journey {dt.date.today().isoformat()}",
            "root_path": str(dataset_root),
        },
    )
    thread = _must(
        "POST",
        f"{base}/api/threads",
        token,
        {"title": "nightly journey", "project_id": int(project["id"])},
    )
    thread_id = int(thread["id"])
    #: FULL FORCES BUILD (`app/events.py::set_thread_permission`, AU6), which
    #: is why this happens before the brief is posted rather than after: the
    #: first turn has to be the turn the brief asked for.
    _must("POST", f"{base}/api/threads/{thread_id}/permission", token, {"mode": FULL})
    _must("POST", f"{base}/api/threads/{thread_id}/messages", token, {"content": brief})

    try:
        print(f"  thread {thread_id}: taking the brief's turn", flush=True)
        _must(
            "POST",
            f"{base}/api/threads/{thread_id}/turn",
            token,
            {},
            timeout=max(120.0, minutes_cap * 60.0),
        )

        print("  starting the run", flush=True)
        _must("POST", f"{base}/api/threads/{thread_id}/run", token, {})
        deadline = time.monotonic() + minutes_cap * 60.0
        while time.monotonic() < deadline:
            run = _must(
                "GET", f"{base}/api/threads/{thread_id}/run", token, timeout=30.0
            )
            state = str(run.get("state") or "")
            if state != "running":
                print(
                    f"  the run ended: {state} / {run.get('stop_reason')}", flush=True
                )
                return thread_id, ""
            time.sleep(10.0)

        print(
            f"  the {minutes_cap:.0f} minute cap - asking the run to stop", flush=True
        )
        _request(
            "POST", f"{base}/api/threads/{thread_id}/run/stop", token=token, body={}
        )
        #: The run stops AFTER the turn it is in, never mid-turn
        #: (`app/longrun.py::stop`), so this waits for the turn to land rather
        #: than reporting a state the engine has not reached yet.
        settle = time.monotonic() + 600.0
        while time.monotonic() < settle:
            run = _must(
                "GET", f"{base}/api/threads/{thread_id}/run", token, timeout=30.0
            )
            if str(run.get("state") or "") != "running":
                break
            time.sleep(10.0)
        return thread_id, f"the driver stopped it at the {minutes_cap:.0f} minute cap"
    except Unreachable as broke:
        #: NOT EXIT 2. The engine answered, the model answered, and then the
        #: journey went wrong - which is a row, and the worst nights are the
        #: ones a driver must not go quiet on.
        print(f"  the journey broke off: {broke}", flush=True)
        return thread_id, f"the journey broke off: {broke}"


def stop_engine(child: subprocess.Popen) -> None:
    """Ask, then insist. Nothing else on this machine is touched."""
    if child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=20)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=20)


def git_head() -> str:
    """This checkout's HEAD, read out of the git directory with no subprocess.

    The dry path's fallback when a scratch root carries no `engine.json`. The
    live path never uses it: there, the sha comes from the engine's own
    `/health`, because the row is pinned to the code that TOOK the journey and
    this function reads the code that is checked out now.

    A WORKTREE IS THE CASE THAT BREAKS THE OBVIOUS VERSION. In a worktree
    `.git` is a FILE naming the real directory, and the ref `HEAD` points at
    may live in the main repository's directory or in `packed-refs` and in no
    file of its own. A row whose sha is `unknown` is a row pinned to nothing,
    so all three are read here.
    """
    git = REPO / ".git"
    if git.is_file():
        try:
            pointer = git.read_text(encoding="utf-8").strip()
        except OSError:
            return "unknown"
        if pointer.startswith("gitdir:"):
            named = Path(pointer.split(":", 1)[1].strip())
            git = named if named.is_absolute() else (REPO / named).resolve()
    try:
        text = (git / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    if not text.startswith("ref:"):
        return text or "unknown"
    name = text.split(" ", 1)[1].strip()
    common = git
    try:
        common = (git / (git / "commondir").read_text(encoding="utf-8").strip()).resolve()
    except OSError:
        pass
    for candidate in (git / name, common / name):
        try:
            return candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
    for packed in (git / "packed-refs", common / "packed-refs"):
        try:
            body = packed.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in body.splitlines():
            if line.endswith(" " + name):
                return line.split(" ", 1)[0]
    return "unknown"


def sha_of_root(root: Path) -> str:
    """The sha the engine that wrote this scratch root was running.

    Out of the root's own `engine.json`, which `app/security.py` writes from
    `identity.identity()` - the same function `/health` answers from, so the
    dry path and the live path are quoting one source.
    """
    portfile = Path(root) / "engine.json"
    try:
        payload = json.loads(portfile.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return git_head()
    build = (payload.get("build") or {}) if isinstance(payload, dict) else {}
    return str(build.get("sha") or "") or git_head()


# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="one live journey, one score row")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ollama", default=DEFAULT_OLLAMA)
    parser.add_argument(
        "--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT,
        help="the folder the project points at; or set MLH_DATASET_ROOT. Needed on the live path only.",
    )
    parser.add_argument("--brief-file", type=Path, default=DEFAULT_BRIEF)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--minutes-cap", type=float, default=DEFAULT_MINUTES_CAP)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="start no engine and need no Ollama: score a root that already exists",
    )
    parser.add_argument(
        "--from-root",
        type=Path,
        default=None,
        help="the scratch data root to score, with --dry-run",
    )
    parser.add_argument(
        "--thread",
        type=int,
        default=None,
        help=(
            "which thread to score; the newest by default, which is the only "
            "one a scratch root has"
        ),
    )
    args = parser.parse_args(argv)
    today = dt.date.today().isoformat()

    try:
        if args.dry_run:
            if args.from_root is None:
                raise Unreachable("--dry-run needs --from-root <scratch data root>")
            root = refuse_unless_scratch(args.from_root)
            row = score(
                root / "ml_harness.db",
                model=args.model,
                sha=sha_of_root(root),
                today=today,
                thread_id=args.thread,
            )
            row.scratch_root = str(root)
            page, table = write_the_row(row, args.out)
            print(row.csv_line(), flush=True)
            print(f"wrote {page}", flush=True)
            print(f"appended to {table}", flush=True)
            return 0

        if int(args.port) == HIS_PORT:
            raise Unreachable(
                f"{HIS_PORT} is the engine the owner has open. This journey runs "
                f"on {DEFAULT_PORT}. Nothing was started."
            )

        root = refuse_unless_scratch(scratch_root_for(today))
        root.mkdir(parents=True, exist_ok=True)
        brief = Path(args.brief_file).read_text(encoding="utf-8").strip()
        if not brief:
            raise Unreachable(f"{args.brief_file} is empty - there is nothing to ask")

        #: SAID, NOT REFUSED. A missing dataset is a journey that will park
        #: every step for want of files, and that is a ROW - one of the more
        #: useful ones, because it says the folder moved. Exit 2 is for an
        #: instrument that could not read, and this instrument can.
        if args.dataset_root is None:
            print(
                "COULD NOT BE REACHED: no dataset root. Pass --dataset-root or set "
                "MLH_DATASET_ROOT to the folder the project points at.",
                file=sys.stderr,
            )
            return 2
        if not Path(args.dataset_root).is_dir():
            print(
                f"WARNING: {args.dataset_root} is not a directory on this "
                "machine. The journey runs anyway and the row will say what "
                "happened.",
                flush=True,
            )

        check_ollama(args.ollama, args.model)

        token = secrets.token_hex(32)
        nonce = secrets.token_hex(16)
        log = root / "engine.log"
        print(f"scratch root: {root}", flush=True)
        child = start_engine(args.port, root, log, token, nonce)
        try:
            health = wait_for_health(child, args.port, nonce)
            sha = str((health.get("build") or {}).get("sha") or "") or git_head()
            print(f"engine ready on {args.port} at {sha[:7]}", flush=True)
            thread_id, note = drive(
                args.port,
                token,
                Path(args.dataset_root),
                args.model,
                args.ollama,
                brief,
                float(args.minutes_cap),
            )
        finally:
            stop_engine(child)

        row = score(
            root / "ml_harness.db",
            model=args.model,
            sha=sha,
            today=today,
            thread_id=thread_id,
        )
        row.scratch_root = str(root)
        row.driver_note = note
        page, table = write_the_row(row, args.out)
        print(row.csv_line(), flush=True)
        print(f"wrote {page}", flush=True)
        print(f"appended to {table}", flush=True)
        print(f"the scratch root is left for inspection: {root}", flush=True)
        return 0
    except Unreachable as unreachable:
        print(f"NOT REACHED: {unreachable}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
