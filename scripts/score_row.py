"""The score row: seven numbers read off one thread's database, and nothing else.

This module exists because TWO callers need the same row and neither may own
it. `scripts/tune_the_harness.py` computes it once per arm of a bandit over
harness knobs; the nightly journey computes it once per night on one thread.
Two copies of "what does a good run look like" drift within a week, and the
first symptom is a tuning report and a nightly report disagreeing about the
same thread on the same day - at which point neither number can be believed
and there is no way to tell which one is wrong.

## WHY IT OPENS A PATH RATHER THAN IMPORTING `app.db`

`compute_row` takes a `db_path`. It does not take a thread out of the ambient
database, because the caller that needs it most is looking at a database it
deliberately put somewhere else: a tuning arm runs an engine subprocess with
`MLH_DATA_ROOT` pointed at a scratch directory, and the whole point is that
the row comes from THAT database and not from whatever `db.DB_PATH` happens to
be bound to in this process. A function that resolved the database for itself
could not read an arm at all, and - worse - would read the owner's real one and
report it as the arm's result.

## WHY IT IS STDLIB ONLY

`sqlite3`, `json`, `hashlib`, `datetime`. No `app` import, no third party. Two
reasons, and the second is the one that matters:

1. A row computation that imports the product cannot be used to measure a
   version of the product that does not import cleanly, which is exactly the
   arm somebody will want to measure one day.
2. **It must not be able to touch anything.** `app.db` and `app.events` carry
   module-level path globals, migrations that run on import of a table, and a
   tool registry. Reading a scratch database through them would migrate it, and
   a reader that writes is not a reader. Opening the file read-only with
   `sqlite3` is the whole of the isolation, and it is complete.

## THE SEVEN, AND WHAT EACH ONE IS COUNTED FROM

Every one of them names the rows it was counted from, and every rate ships its
numerator and its denominator beside it, so the reader can recompute the number
rather than take it. A rate whose counts are not printed is a mood.

| number | counted from |
| --- | --- |
| `plan_written_on_turn_1` | a `thread.plan_written` event before the first `run.turn` |
| `steps_ticked` / `steps_open_at_start` | the step lines of `threads.plan` (or `threads.todo`) |
| `refusals_per_call` | `tool.result` with `ok: false` or a `result.error`, over `tool.call` |
| `empty_replies` | `stream.end` whose `ending` is `empty_reply`, over all `stream.end` |
| `tokens_before_first_word` | the first `turn.context` payload's `system` + `tools` |
| `questions_asked` | assistant `messages` ending in `?`, when the thread is at `full` |
| `minutes_to_first_measurement` | first `fact_evidence` row at `MEASURED`, minus `threads.created_at` |

### The two that need their reading written down

**`steps_open_at_start` is the plan's every step, not a snapshot taken before
the run.** Nothing in the database records the checklist as it stood at the
first turn - `run.turn` carries `open` AFTER its turn, which is one turn too
late, and the plan column holds only the latest text. In the shape this row is
computed for, that costs nothing: the thread writes its plan inside the run it
is being scored on, so every step the plan carries was open when the run began.
A thread handed a plan with steps ALREADY TICKED would have those counted as
work this run did, and would read better than it was. If that shape ever gets
scored, this number needs the snapshot and this paragraph is the warning.

**`questions_asked` is gated on the thread's permission as it stands now.** The
`messages` table does not record what the permission was when each message was
written; `threads.permission` is one column holding one value. Under `full` the
harness is supposed to act rather than ask, so a question is a defect and this
counts them; under `ask` a question is the product working correctly and
counting them would be counting the feature. So a thread not at `full` reports
`0` - which means "not measurable here", not "asked nothing", and
`questions_measurable` says which of the two it is rather than leaving a reader
to guess from a zero.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

#: The event kinds this module reads. Named here rather than spelled inline in
#: five places, because a typo in one of five string literals is a number that
#: silently reads zero - and a zero from a misspelt kind looks exactly like a
#: zero from a run that did nothing.
PLAN_WRITTEN = "thread.plan_written"
#: A plan a new thread ADOPTED from the project's plan file is a plan on
#: turn 1 as much as one written; the third live row had one and read "no".
PLAN_ADOPTED = "thread.plan_adopted"
RUN_TURN = "run.turn"
TURN_STARTED = "turn.started"
TOOL_CALL = "tool.call"
TOOL_RESULT = "tool.result"
STREAM_END = "stream.end"
TURN_CONTEXT = "turn.context"

#: `app/conductor.py` writes this `ending` when a turn produced no words and no
#: tool calls. Note what it already means: the harness NUDGES once and only
#: gives up on the second silence, so one of these is two empty replies, not
#: one. `answered_after_empty_reply` is NOT counted - the model went quiet and
#: then answered, the person got a reply, and folding the two together would
#: report a harness that recovered as a harness that failed.
EMPTY_ENDING = "empty_reply"

#: `app/build.py`'s provenance vocabulary. Only the first of the four is a
#: measurement; the others are somebody saying so.
MEASURED = "MEASURED"

#: `app/autonomy.py` MODES. Only the last one makes a question a defect.
FULL = "full"

#: The column order of `rows.csv`, and the order the report's table prints.
#: Derived from here by both, so a number added to the row cannot be added to
#: the file and forgotten in the table.
FIELDS: tuple[str, ...] = (
    "plan_written_on_turn_1",
    "steps_ticked",
    "steps_open_at_start",
    "refusals_per_call",
    "refusals",
    "tool_calls",
    "empty_replies",
    "empty_reply_turns",
    "turns",
    "tokens_before_first_word",
    "questions_asked",
    "questions_measurable",
    "minutes_to_first_measurement",
)

#: The seven headline numbers, in the order a person reads them: did it plan,
#: did it do the work, did the tools refuse, did it go quiet, what did the
#: prompt cost before a word was said, did it ask instead of acting, and how
#: long until something was actually measured. The counts behind the rates are
#: in `FIELDS` and not here; they are how a rate is checked, not what it says.
HEADLINE: tuple[str, ...] = (
    "plan_written_on_turn_1",
    "steps_ticked",
    "steps_open_at_start",
    "refusals_per_call",
    "empty_replies",
    "tokens_before_first_word",
    "questions_asked",
    "minutes_to_first_measurement",
)


def _connect(db_path: str | Path) -> sqlite3.Connection:
    """The database, opened read-only, or a clear error naming the file.

    `mode=ro` and not merely "we promise not to write": a URI-mode read-only
    connection makes a stray `INSERT` in this module raise instead of landing,
    which is the difference between a bug and a corrupted arm. It also refuses
    to CREATE the file, so a mistyped path is an error here rather than an
    empty database that reports a perfect run of nothing.
    """
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(
            f"no database at {path} - an arm that never started has no row, and "
            "an empty one would score as a run that did nothing wrong"
        )
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _events(connection: sqlite3.Connection, thread_id: int) -> list[dict[str, Any]]:
    """Every event on the thread, oldest first, payload decoded.

    Ordered by `id` and not by `ts`: `ts` is `CURRENT_TIMESTAMP`, whole seconds,
    and a turn writes a dozen events inside one of them. Sorting on a stamp with
    one-second resolution would shuffle a turn's events among themselves, and
    `plan_written_on_turn_1` is a question about ORDER.
    """
    rows = connection.execute(
        "SELECT id, kind, payload_json, ts FROM events "
        "WHERE thread_id = ? ORDER BY id ASC",
        (int(thread_id),),
    ).fetchall()
    out = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except (TypeError, ValueError):
            payload = {}
        out.append(
            {
                "id": int(row["id"]),
                "kind": str(row["kind"] or ""),
                "payload": payload if isinstance(payload, dict) else {},
                "ts": str(row["ts"] or ""),
            }
        )
    return out


def step_state(line: str) -> str | None:
    """`- [ ]` -> open, `- [x]` -> done, `- [!]` -> parked. `None` when not a step.

    Written as a parser rather than a pattern, and LOOSELY, for the reason
    `app/tools/planning.py` records: a rewrite produced `- []` and a strict
    pattern stopped seeing six steps, so the bar read 0 of 0 and a run that did
    the work scored as one that did none. `- []`, `-[ ]`, `* [x ]` are all
    steps. A line this cannot read is not a step and is not counted either way,
    which keeps the denominator and the numerator reading the same lines.
    """
    text = str(line or "").strip()
    if not text or text[0] not in "-*":
        return None
    rest = text[1:].strip()
    if not rest.startswith("["):
        return None
    close = rest.find("]")
    if close < 0:
        return None
    mark = rest[1:close].strip()
    if mark == "":
        return "open"
    if mark in ("x", "X"):
        return "done"
    if mark == "!":
        return "parked"
    return None


def steps_in(checklist: str) -> dict[str, int]:
    """How many step lines the checklist has, and how many are in each state."""
    counts = {"open": 0, "done": 0, "parked": 0}
    for line in str(checklist or "").splitlines():
        state = step_state(line)
        if state is not None:
            counts[state] += 1
    counts["total"] = counts["open"] + counts["done"] + counts["parked"]
    return counts


def _parse_stamp(value: Any) -> datetime | None:
    """A SQLite `CURRENT_TIMESTAMP` string to a datetime, or `None`.

    `YYYY-MM-DD HH:MM:SS` in UTC is what the schema's defaults write.
    `fromisoformat` reads it, and reads the fractional and `T`-separated
    variants too, which is why it is used instead of a format string that would
    refuse a stamp written by a different writer.
    """
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def instruction_fingerprint(db_path: str | Path, thread_id: int) -> str | None:
    """A fingerprint of what this thread's FIRST turn was sent, before any reply.

    THIS IS THE INERTNESS DETECTOR, and it is the reason a tuning run can say
    "that knob did nothing" rather than "that knob made no difference". Those
    are different findings with opposite next moves: the first is a bug in the
    matrix, the second is a result.

    It is taken from BOTH rows the conductor writes before the model is asked
    anything, because they answer different halves of the question:

    * `turn.started` carries `instruction_set` - `app/instructions/__init__.py`
      `version()`, a sha256 over every core and conditional fragment that went
      into the prompt plus the capability digest. A laws knob that works moves
      this, and nothing else in the payload can move it by accident.
    * `turn.context` is written at the moment the conductor has the assembled
      conversation and the tool schemas in hand - the two things that actually
      go on the wire - and its `system`, `tools` and `tool_count` are what a
      schemas knob moves.

    Two arms agreeing on all four were sent the same laws and the same tools,
    and whatever the knob did, it did not do it here.

    The FIRST turn only, and deliberately: later turns carry the conversation,
    which diverges between arms because the model said different things, and a
    fingerprint that moved because the model was chatty would say every knob
    works. Returns `None` when the thread never took a turn.
    """
    connection = _connect(db_path)
    try:
        rows = _events(connection, thread_id)
    finally:
        connection.close()
    context = next((row for row in rows if row["kind"] == TURN_CONTEXT), None)
    started = next((row for row in rows if row["kind"] == TURN_STARTED), None)
    if context is None and started is None:
        return None
    payload = context["payload"] if context is not None else {}
    shape = {
        "system": int(payload.get("system") or 0),
        "tools": int(payload.get("tools") or 0),
        "tool_count": int(payload.get("tool_count") or 0),
        "mode": str(payload.get("mode") or ""),
        "instruction_set": str(
            (started["payload"] if started is not None else {}).get("instruction_set") or ""
        ),
    }
    body = json.dumps(shape, sort_keys=True).encode("utf-8")
    return hashlib.sha256(body).hexdigest()[:16]


def compute_row(db_path: str | Path, thread_id: int) -> dict[str, Any]:
    """The seven numbers for one thread, plus the counts each rate came from.

    Every value is read; nothing is inferred and nothing is defaulted to a
    flattering number. A rate whose denominator is zero is `None` and not
    `0.0` - no tool calls means "there is no refusal rate", and a harness that
    called nothing scoring a perfect 0.0 refusal rate is the exact shape of lie
    this repository keeps finding.
    """
    connection = _connect(db_path)
    try:
        thread = connection.execute(
            "SELECT id, created_at, plan, todo, checklist_source, permission "
            "FROM threads WHERE id = ?",
            (int(thread_id),),
        ).fetchone()
        if thread is None:
            raise LookupError(
                f"no thread {thread_id} in {Path(db_path)} - an arm whose thread "
                "was never created has no row"
            )
        rows = _events(connection, thread_id)
        assistant = connection.execute(
            "SELECT content FROM messages WHERE thread_id = ? AND role = 'assistant' "
            "ORDER BY id ASC",
            (int(thread_id),),
        ).fetchall()
        measured = connection.execute(
            "SELECT created_at FROM fact_evidence WHERE thread_id = ? AND origin = ? "
            "ORDER BY id ASC LIMIT 1",
            (int(thread_id), MEASURED),
        ).fetchone()
    finally:
        connection.close()

    # 1. THE PLAN, ON THE FIRST TURN. The boundary is THE END OF TURN 1, and
    #    two different rows mark it depending on who drove the thread:
    #
    #    * `run.turn` - written by `app/longrun.py` once per turn of a run. The
    #      preferred boundary, and the one both callers of this module use
    #      whenever a run is what took the turns.
    #    * `stream.end` - written by the conductor at the end of EVERY turn,
    #      including turns a run did not drive.
    #
    #    THE FALLBACK IS NOT A CONVENIENCE. A thread driven by bare `POST
    #    /turn` calls has no `run.turn` row at all, so a boundary that knew
    #    only about runs would report every such thread as "no plan on turn 1"
    #    - a number that is False for every arm, looks like a finding, and is
    #    an artefact of the driver. Preferring `run.turn` where it exists keeps
    #    the two callers agreeing on any thread that had a run, which is what
    #    sharing this module is for.
    first_run_turn = next((row["id"] for row in rows if row["kind"] == RUN_TURN), None)
    if first_run_turn is None:
        first_run_turn = next(
            (row["id"] for row in rows if row["kind"] == STREAM_END), None
        )
    plan_events = [row["id"] for row in rows if row["kind"] in (PLAN_WRITTEN, PLAN_ADOPTED)]
    plan_on_one = bool(
        first_run_turn is not None
        and plan_events
        and min(plan_events) < first_run_turn
    )

    # 2. THE WORK. See the module docstring for why every step the plan carries
    #    counts as open at the start.
    source = str(thread["checklist_source"] or "plan")
    checklist = str((thread["todo"] if source == "todo" else thread["plan"]) or "")
    steps = steps_in(checklist)

    # 3. THE REFUSALS. Two shapes, because the conductor writes both: the
    #    envelope's own `ok: false`, and an `ok` envelope around a result dict
    #    that carries an `error`. Counting only the first missed every tool that
    #    ran and reported its own failure.
    tool_calls = sum(1 for row in rows if row["kind"] == TOOL_CALL)
    refusals = 0
    for row in rows:
        if row["kind"] != TOOL_RESULT:
            continue
        payload = row["payload"]
        result = payload.get("result")
        result = result if isinstance(result, dict) else {}
        if payload.get("ok") is False or result.get("ok") is False or result.get("error"):
            refusals += 1

    # 4. THE SILENCES, over the turns that could have been silent.
    endings = [
        str(row["payload"].get("ending") or "")
        for row in rows
        if row["kind"] == STREAM_END
    ]
    turns = len(endings)
    empty_turns = sum(1 for ending in endings if ending == EMPTY_ENDING)

    # 5. WHAT THE PROMPT COST BEFORE A WORD WAS SAID. The product's own two
    #    fixed costs - the instruction set and the tool schemas - on the first
    #    turn, which is the only turn where they are not mixed with history.
    first_context = next((row for row in rows if row["kind"] == TURN_CONTEXT), None)
    if first_context is None:
        tokens_first = None
    else:
        payload = first_context["payload"]
        tokens_first = int(payload.get("system") or 0) + int(payload.get("tools") or 0)

    # 6. THE QUESTIONS. See the module docstring for the permission gate.
    permission = str(thread["permission"] or "")
    measurable = permission == FULL
    questions = 0
    if measurable:
        questions = sum(
            1
            for row in assistant
            if str(row["content"] or "").strip().endswith("?")
        )

    # 7. HOW LONG UNTIL SOMETHING WAS MEASURED. Not "until a tool ran" and not
    #    "until the model said a number": until a row landed in the evidence
    #    ledger stamped MEASURED, which is the only origin an instrument writes.
    started = _parse_stamp(thread["created_at"])
    first_measured = _parse_stamp(measured["created_at"]) if measured else None
    if started is None or first_measured is None:
        minutes = None
    else:
        minutes = round((first_measured - started).total_seconds() / 60.0, 3)

    return {
        "thread_id": int(thread_id),
        "plan_written_on_turn_1": plan_on_one,
        "steps_ticked": int(steps["done"]),
        "steps_open_at_start": int(steps["total"]),
        "refusals_per_call": (refusals / tool_calls) if tool_calls else None,
        "refusals": int(refusals),
        "tool_calls": int(tool_calls),
        "empty_replies": (empty_turns / turns) if turns else None,
        "empty_reply_turns": int(empty_turns),
        "turns": int(turns),
        "tokens_before_first_word": tokens_first,
        "questions_asked": int(questions),
        "questions_measurable": bool(measurable),
        "minutes_to_first_measurement": minutes,
    }
