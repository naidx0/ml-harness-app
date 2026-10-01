"""The long run: turns taken one after another until the plan is worked down.

Max, 2026-09-13: *"some sort of long running tasks structure, executed from
the plan, simple re-prompts and tell the agent to work... after each section
is finished and pushed back, the to-do keeps executing, and the model has to
keep thinking and going no matter what. On any kind of stops or rule
gateways, it goes as far as it can without that exception in particular."*

## What this is, and what it is not

It is a loop over `conductor.run_turn`, in the ENGINE rather than in the
browser. `lib/theBuildKeepsGoing.ts` already kept a build going by sending
another turn from the page; that loop dies with the window, the tab, or a
person clicking away, which is the one thing a long run must survive. This
one lives where the work lives: a row in `long_runs`, a worker thread, and
events for the interface to follow.

It is NOT a second way to decide what to do. The plan's `- [ ]` lines are
the to-do list and `_plan_note` is the re-prompt - the loop adds no
instruction of its own. Every turn is an ordinary turn: the same prompt, the
same tools, the same walls. What the loop contributes is that there is
another one.

## Going as far as it can

A step that cannot be done does not end the run. When a turn ends with the
step it was aiming at still open, that is one strike; on the second strike
the step is PARKED with the reason the model gave (`planning.park_step`
writes `- [!] <step> - parked: <why>` into the plan), the prompt is told not
to retry it, and the run moves to the next open step. A run therefore ends
with a list of what was done and a list of what was parked and why - which
is the honest shape of "as far as it can".

Three things do stop it, and each is the person's business rather than the
plan's: an approval waiting on a gated tool, the connection failing twice in
a row, and the turn cap. Plus the stop button, which is a row in the table
so it works from any window and any process.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Any, Callable, Iterable

from app import db, events
from app.tools import planning

#: How many turns one run may take before it hands back to the person. A
#: build turn against a local model costs tens of seconds; twenty-four is
#: most of an afternoon's work and still a bound a person can hold in mind.
TURN_CAP = 24

#: How many more turns a run that is STILL MOVING gets when it reaches its cap.
#:
#: Max, 2026-09-18: *"at the cap, if a step was ticked within the last 3 turns,
#: extend the cap by 6 more turns."* The cap exists to stop a run that is going
#: nowhere from spending the afternoon, and a run ticking steps is not that run
#: - stopping it is throwing away a working plan three steps from the end and
#: handing the person a half-done list to restart by hand.
#:
#: SIX RATHER THAN A DOUBLING, because an extension is a question asked again.
#: Six turns is another handful of steps, and a run that is still moving at the
#: end of them gets asked again; a doubling would make the second decision cost
#: twenty-four turns and the third forty-eight, which is a cap that stops
#: bounding anything after the first extension.
CAP_EXTENSION = 6

#: How recently a step must have been ticked for the extension to be granted.
#: Three turns, so a run that ticked something on the turn before last is still
#: moving and one that has ticked nothing since turn 20 is not. It is the same
#: window `REPLAN_AFTER` uses for "nothing moved", deliberately: two different
#: numbers for one idea is how they drift apart.
PROGRESS_WINDOW = 3

#: The wall the extension cannot climb past, however well the run is going.
#:
#: 96 is four caps. A run is a person's machine and a person's afternoon, and
#: "it kept ticking so it kept going" with no ceiling is a loop that ends when
#: somebody notices rather than when the work does. The ceiling is what makes
#: the extension a BOUND being raised rather than a bound being removed.
ABSOLUTE_TURN_CEILING = 96

#: Steps parked one after another before the run stops and says the plan is
#: the problem. MEASURED 2026-09-13 on the owner's screen: four of five steps
#: parked and the run still reported "plan worked down", which reads as
#: success. Three in a row is a plan nobody can work, and grinding through the
#: rest to park them too proves nothing the third one did not.
PARKS_IN_A_ROW = 3

#: Turns in a row that tick nothing before the run asks for the plan to be
#: rewritten. MEASURED 2026-09-13: a plan whose steps were the five gate names
#: ran ten turns, ticked nothing and parked everything - the steps were not
#: things anyone could do, and no amount of re-prompting would have made them
#: so. When nothing moves, the plan is the suspect, and the run says so once.
REPLAN_AFTER = 3

#: What the run says when it asks for that rewrite. Scaffolding for one turn,
#: in `conversation` and never in `messages`, the same rule the conductor's
#: own nudges follow.
#: Said on the FIRST turn of a run whose plan has phases with no steps.
#: Max's thread 75, 2026-09-17: eight phases with `**Tools:**` lines and no
#: `- [ ]` under them, six gate sentences under Verification, and the run
#: aimed at the gates. Before aiming at anything, the run says so.
STEPLESS_NUDGE = (
    "[harness] This plan's phases {phases} carry no `- [ ]` step, so a run "
    "cannot work them - it would aim at whatever checkbox lines it finds "
    "elsewhere. Before anything else, rewrite the plan with write_plan so "
    "each phase lists one `- [ ]` line per tool call, the tool and its "
    "arguments, keeping what is already ticked or parked exactly as it is. "
    "Then work the first open step."
)

#: A DOOR OUT OF A PARK, said where a run can act on it.
#:
#: `unpark_step` has been registered the whole time and NOTHING has ever named
#: it - not the instruction set, not a scaffold, not a stop reason. Max's run
#: of 2026-09-19/20 ended with seven parked steps and the sentence "Start the
#: run again, or switch model", and starting it again parked them again,
#: because the walls that parked them were still there and the model was never
#: told the steps could be reopened. His words, 2026-09-20: *"we're not just
#: parking for no reason. Get, we're giving the models ways to unpark and not
#: stop."*
#:
#: Said on the FIRST turn of a run that inherits parks, because that is the
#: turn where it changes what happens. It names the reason each was parked, so
#: the model can tell "the tool refused and still would" from "the tool refused
#: because of something that has since been measured".
PARKED_NUDGE = (
    "[harness] This plan carries {count} parked step(s) from an earlier run. "
    "A park is not a verdict - it records that a step could not be done THEN, "
    "with the reason on the line:{lines}"
    "\n\nIf the reason no longer holds, reopen it with `unpark_step` and work "
    "it. If it still holds, leave it parked and go to the first open step; "
    "re-running a step that will refuse again costs a turn and changes "
    "nothing."
)

REPLAN_NUDGE = (
    "[harness] Three turns have passed and no step of this plan has been "
    "ticked, so the steps are the problem rather than the effort. Rewrite the "
    "REMAINING steps now with write_plan, keeping what is already ticked or "
    "parked exactly as it is: every open step must name a registered tool and "
    "the arguments it takes, so that reading the line tells you the call to "
    "make. A step that is a condition rather than an action - 'baseline "
    "measured', 'prompting exhausted' - is a gate, and a gate is not a step. "
    "Then work the first one."
)

#: Turns in a row that come back with nothing - no words, no tool calls -
#: before the run gives up. They cost no step a strike (see `work`), so this is
#: the only thing stopping a model that has gone silent from being retried
#: until the turn cap. Four is enough to ride out a reload or a hiccup and
#: short enough that a genuinely dead connection is reported in a minute.
HOLLOW_TURNS = 4

#: Turns ending with the same step still open before that step is parked.
#: One is too eager - a turn that read a file and will act on the next one
#: is normal work. Two is a model that has tried and cannot.
STRIKES = 2

#: AU7 — when the model only announces a move under Full/longrun, do not
#: strike the step (same honesty as empty_reply). Bound retries so a
#: permanently narrating model cannot spin forever.
NARRATION_TURNS = 4

#: Park reasons that are intentions, not blockers. Screenshot 2026-09-16:
#: parked "eval set ≥ 30" with why "I'll read the current plan…". Saying what
#: it will do next is not evidence the step cannot be done.
_INTENT_WHY = re.compile(
    r"^(i('ll| will| am going to| can)|let me|i'm going to|"
    r"i need to|going to|reading the|i'll get|i'll check)\b",
    re.IGNORECASE,
)

NARRATION_NUDGE = (
    "[harness] That turn announced a move and called no tool, so the step is "
    "untouched. Call the tool named in the first open step now — or, under "
    "Full, state_facts for any open ask-fact the brief names. Do not ask the "
    "person. Do not say you are ready when they approve."
)

RUNNING = "running"
DONE = "done"
STOPPED = "stopped"
FAILED = "failed"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS long_runs (
    thread_id INTEGER PRIMARY KEY,
    state TEXT NOT NULL,
    turns INTEGER NOT NULL DEFAULT 0,
    cap INTEGER NOT NULL,
    stop_reason TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

_WORKERS: dict[int, threading.Thread] = {}


def ensure_table() -> None:
    with db.session() as connection:
        connection.executescript(_SCHEMA)


def reap_orphans() -> int:
    """End runs whose worker died with the engine. Called at startup.

    A run is a thread in this process. When the engine exits - the app quits,
    the machine sleeps, an installer replaces it - the row stays `running`
    and nothing is taking turns, which would leave the chip claiming work
    that stopped hours ago. Every run found `running` at startup is by
    definition orphaned: a live one could not exist before this process did.
    """
    ensure_table()
    with db.session() as connection:
        rows = connection.execute(
            "SELECT thread_id FROM long_runs WHERE state = ?", (RUNNING,)
        ).fetchall()
        if rows:
            connection.execute(
                "UPDATE long_runs SET state = ?, stop_reason = ?, detail = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE state = ?",
                (
                    STOPPED,
                    "engine_restarted",
                    "the engine stopped while this run was working; nothing it "
                    "had already done was lost, and starting it again picks up "
                    "at the first open step",
                    RUNNING,
                ),
            )
    for row in rows:
        thread = events.get_thread(int(row["thread_id"])) or {}
        events.append(
            "run.finished",
            {
                "thread_id": int(row["thread_id"]),
                "reason": "engine_restarted",
                "detail": "the engine stopped while this run was working",
                "turns": 0,
                "parked": [],
            },
            project_id=thread.get("project_id"),
            thread_id=int(row["thread_id"]),
        )
    return len(rows)


def status(thread_id: int) -> dict[str, Any] | None:
    """The run on this thread, or `None` if it has never had one."""
    ensure_table()
    with db.session() as connection:
        row = connection.execute(
            "SELECT * FROM long_runs WHERE thread_id = ?", (int(thread_id),)
        ).fetchone()
    if row is None:
        return None
    out = dict(row)
    thread = events.get_thread(int(thread_id)) or {}
    steps = planning.steps_in(planning.checklist_text(thread))
    out["steps"] = len(steps)
    out["open"] = sum(1 for s in steps if s["state"] == "open")
    out["done"] = sum(1 for s in steps if s["state"] == "done")
    out["parked"] = [
        {"step": s["text"], "why": s["why"]} for s in steps if s["state"] == "parked"
    ]
    # HOW LONG IT HAS BEEN GOING, because "Complete - 14m 17s" is the line Max
    # pointed at in Codex's goal card and a run that took four minutes and one
    # that took forty are different news. Both timestamps are the table's own
    # CURRENT_TIMESTAMP, in UTC, so the arithmetic is between two of ours.
    out["seconds"] = _seconds_between(out.get("started_at"), out.get("updated_at"))
    return out


def is_running(thread_id: int | None) -> bool:
    """Is the durable Run loop live on this thread right now?"""
    if thread_id is None:
        return False
    return _state(int(thread_id)) == RUNNING


def _seconds_between(start: Any, end: Any) -> int | None:
    import datetime

    try:
        opened = datetime.datetime.strptime(str(start), "%Y-%m-%d %H:%M:%S")
        closed = datetime.datetime.strptime(str(end), "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None
    return max(0, int((closed - opened).total_seconds()))


def _write(thread_id: int, **fields: Any) -> None:
    ensure_table()
    sets = ", ".join(f"{key} = ?" for key in fields)
    with db.session() as connection:
        connection.execute(
            f"UPDATE long_runs SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE thread_id = ?",
            (*fields.values(), int(thread_id)),
        )


def _state(thread_id: int) -> str:
    ensure_table()
    with db.session() as connection:
        row = connection.execute(
            "SELECT state FROM long_runs WHERE thread_id = ?", (int(thread_id),)
        ).fetchone()
    return "" if row is None else str(row["state"])


def stop(thread_id: int, reason: str = "stopped by hand") -> dict[str, Any] | None:
    """Ask the run to stop. It ends after the turn it is in, never mid-turn.

    A row rather than a flag in memory: the button is in one window, the
    worker may be in another process, and a turn half-written is worse than
    a turn that finished and then stopped.
    """
    # AND THE TURN IT IS IN, WHICH THE ROW ALONE CANNOT REACH. Max,
    # 2026-09-19: *"Even when you click stop in the plan, it doesn't stop
    # working. You can literally see it highlighted on the chat that I can see
    # on my GPU."* He was right and the mechanism is a gap between two stops.
    # The loop reads this row once per ITERATION - `while True: if _state(...)
    # != RUNNING: break` - and an iteration contains a whole `conductor
    # .run_turn`, up to eight rounds of model call plus tools. So a press two
    # seconds into a turn set the row, returned instantly, and the card kept
    # streaming for the rest of that turn. With two sub-agents out, three
    # turns kept streaming.
    #
    # `app/interrupt.py` is the stop that lands INSIDE a turn, at its next
    # round boundary. It was only wired to `POST /turn/stop`; every other door
    # - the run panel, the remote link, a sub-agent being stopped by its
    # parent - went through here and skipped it. Asked for here instead of at
    # each call site so there is one answer: `subagents.stop` calls this with
    # the CHILD's thread id, so children are covered by the same line.
    from app import interrupt as _interrupt

    if _interrupt.a_turn_is_running(int(thread_id)):
        _interrupt.ask_to_stop(int(thread_id))
    if _state(thread_id) != RUNNING:
        return status(thread_id)
    _write(thread_id, state=STOPPED, stop_reason=reason)
    # THE WORK IT HANDED OUT STOPS WITH IT. A person who stopped a run and
    # then watched two sub-agents keep taking turns on their card would be
    # right to say the button does not work.
    from app import subagents

    subagents.stop_all(int(thread_id), reason)
    return status(thread_id)


def compile_the_plan_first(thread_id: int) -> dict[str, Any] | None:
    """A run on a conversation with NO plan compiles one from its journey.

    Max, 2026-09-18: *"journey is an amazing way to empower the plan."* Under
    Full the model is told to write the plan before it works (see
    `conductor._plan_note`), which is a model being asked to type out a route
    the harness can already read: `app/journey.py` knows every step of it, the
    tool each step calls and the arguments this conversation has measured.

    So the run compiles it, and only when there is nothing at all to work: a
    plan somebody wrote, a plan with every step ticked, or a `todo` checklist
    are all left exactly as they are. Returns the compile's own answer, or
    `None` when there was nothing to compile from.
    """
    thread = events.get_thread(int(thread_id)) or {}
    if str(thread.get("checklist_source") or "plan") != "plan":
        return None
    if str(thread.get("plan") or "").strip():
        return None
    from app import journey

    out = journey.compile_plan(int(thread_id))
    return out if out.get("ok") else None


def start(
    thread_id: int,
    *,
    cap: int = TURN_CAP,
    background: bool = True,
    turn: Callable[[int], Iterable[dict[str, Any]]] | None = None,
    delegate: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Begin working the plan down. Refuses when there is nothing to work.

    `turn` is the thing that takes one turn, defaulting to the conductor's.
    `delegate` is what hands a phase out, defaulting to `subagents.delegate`.
    Both are parameters so a test can drive the loop without a model, and for
    no other reason: nothing in the product passes either.
    """
    thread = events.get_thread(int(thread_id))
    if thread is None:
        return {"ok": False, "error": "no_such_thread", "thread_id": thread_id}
    if str(thread.get("mode") or "build") != "build":
        return {
            "ok": False,
            "error": "not_building",
            "detail": (
                "A run works the plan down, and plan mode does not run steps. "
                "Switch to Build under the chat box first."
            ),
        }
    if not planning.open_steps(planning.checklist_text(thread)):
        # NOTHING OPEN AND NOTHING WRITTEN ARE TWO DIFFERENT EMPTIES, and this
        # refusal used to give them one sentence. A conversation walking a
        # journey with no plan saved has plenty to do; the document saying so
        # is the only thing missing, and the journey is where it comes from -
        # so the run compiles one FIRST (P6), and only then decides.
        if _state(thread_id) != RUNNING and compile_the_plan_first(int(thread_id)):
            thread = events.get_thread(int(thread_id)) or thread
    if not planning.checklist_text(thread).strip():
        # P0's live row, 2026-09-18: a thread that had never had a plan was
        # told "every step of this plan is ticked or parked". Wrong sentence
        # for the case, and the person cannot act on it. Reached only when
        # the journey could not compile one either.
        return {
            "ok": False,
            "error": "no_plan",
            "detail": (
                "This conversation has no plan yet, so there is nothing for a "
                "run to work down. Write one first - Plan mode, or ask for it "
                "and the harness saves the phases the model writes."
            ),
        }
    if not planning.open_steps(planning.checklist_text(thread)):
        return {
            "ok": False,
            "error": "nothing_open",
            "detail": (
                "Every step of this plan is ticked or parked, so there is "
                "nothing for a run to work down."
            ),
        }
    if _state(thread_id) == RUNNING:
        return {"ok": False, "error": "already_running", "run": status(thread_id)}

    ensure_table()
    with db.session() as connection:
        connection.execute(
            "INSERT INTO long_runs(thread_id, state, turns, cap, stop_reason, detail, started_at, updated_at) "
            "VALUES (?, ?, 0, ?, '', '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) "
            "ON CONFLICT(thread_id) DO UPDATE SET state = excluded.state, turns = 0, "
            "cap = excluded.cap, stop_reason = '', detail = '', started_at = CURRENT_TIMESTAMP, "
            "updated_at = CURRENT_TIMESTAMP",
            (int(thread_id), RUNNING, int(cap)),
        )
    events.append(
        "run.started",
        {
            "thread_id": int(thread_id),
            "cap": int(cap),
            "open": len(planning.open_steps(planning.checklist_text(thread))),
        },
        project_id=thread.get("project_id"),
        thread_id=int(thread_id),
    )

    if not background:
        work(thread_id, turn=turn, delegate=delegate)
        return {"ok": True, "run": status(thread_id)}

    worker = threading.Thread(
        target=work, args=(int(thread_id),),
        kwargs={"turn": turn, "delegate": delegate},
        name=f"mlh-run-{thread_id}", daemon=True,
    )
    _WORKERS[int(thread_id)] = worker
    worker.start()
    return {"ok": True, "run": status(thread_id)}


def _take(take_a_turn: Any, thread_id: int, scaffold: str | None) -> Any:
    """Run one turn, handing it this turn's scaffolding when it takes any.

    A scripted turn in a test takes a thread id and nothing else; the
    conductor's takes a keyword. The one that accepts it gets it.
    """
    if scaffold:
        try:
            return take_a_turn(thread_id, scaffold=scaffold)
        except TypeError:
            pass
    return take_a_turn(thread_id)


def _approval_is_waiting(rows: list[dict[str, Any]]) -> bool:
    """Did this turn end on a tool asking the person for a yes?

    The same field `lib/theBuildKeepsGoing.ts` reads and the same field the
    approval card keys on - `{error: 'approval_required'}` - rather than a
    second opinion about what an approval looks like.
    """
    for row in reversed(rows):
        if row.get("kind") != "tool.result":
            continue
        result = (row.get("payload") or {}).get("result")
        return isinstance(result, dict) and result.get("error") == "approval_required"
    return False


def _ending(rows: list[dict[str, Any]]) -> str:
    for row in reversed(rows):
        if row.get("kind") == "stream.end":
            return str((row.get("payload") or {}).get("ending") or "")
    return ""


def _narrated_only(rows: list[dict[str, Any]]) -> bool:
    """Announced a move, called no tool — not evidence the step is undoable."""
    said = False
    called = False
    for row in rows:
        kind = row.get("kind")
        if kind == "tool.call":
            called = True
        if kind == "conductor.notice":
            reason = (row.get("payload") or {}).get("reason")
            if reason in ("said_it_would_and_did_nothing", "full_grind_nudge"):
                said = True
    return said and not called


def _intent_not_a_blocker(why: str) -> bool:
    """True when the park reason is a next-move announcement, not a wall."""
    text = " ".join(str(why or "").strip().split())
    if not text:
        return False
    return bool(_INTENT_WHY.match(text))


#: REFUSALS THAT MEAN "CALL IT AGAIN PROPERLY", NOT "THIS CANNOT BE DONE".
#: Max's thread 75, 2026-09-17: all six parks were one of these - a wrong
#: path, state_facts with no facts, a value not in the fact's list, a number
#: sent as a string, a folder that already existed, nothing to deduplicate.
#: Every one is an argument the model can fix on the next call, and none is
#: evidence about the step. A wall is a tool saying the world refuses: no
#: model connected, no GPU, the file is generated rows, the person must say yes.
NOT_A_WALL: frozenset[str] = frozenset({
    "missing_arguments", "missing_thread_id", "nothing_supplied", "rejected_fact",
    "not_found", "no_such_file", "no_such_columns", "unknown_metric",
    "destination_exists", "would_write_in_place", "would_write_inside_the_source",
    "would_write_inside_a_dataset", "no_destination", "unusable_destination",
    "no_duplicates", "empty_command", "unreadable_format", "no_such_thread",
    "no_honest_build", "different_instrument",
})


def _tools_named_in(step: str) -> frozenset[str]:
    """Registered tool names the step text mentions, lower-cased."""
    try:
        from app.tools.registry import REGISTRY as _registry

        low = str(step or "").lower()
        return frozenset(
            name for name in (str(getattr(spec, "name", "") or "").lower() for spec in _registry)
            if name and name in low
        )
    except Exception:  # noqa: BLE001 - a registry that cannot be read names nothing
        return frozenset()


def _is_a_wall(payload: dict[str, Any], named: frozenset[str]) -> bool:
    """One tool.result payload: does it say the aimed step cannot be done?"""
    result = payload.get("result")
    error = str(result.get("error") or "") if isinstance(result, dict) else ""
    refused = payload.get("ok") is False or bool(error)
    if not refused:
        return False
    if error in NOT_A_WALL:
        # ONE EXCEPTION, AND IT COST A RUN. `unreadable_format` is usually an
        # argument to fix - somebody pointed at a .parquet - so it belongs in
        # the list. But the same error comes back when the tool STRUCTURALLY
        # cannot open what it was given, and then "fix the argument and call
        # again" is advice with nothing behind it. Max's run, 2026-09-19:
        # `assess_the_data` on a folder of .jsonl answered `unreadable_format`,
        # the harness read it as a slip, refused to strike or park the step,
        # nudged four times and killed the run as a narrating model - having
        # recorded no reason at all. The payload says which case it is:
        # `format.name` is the thing that had no reader. (The folder case
        # itself is fixed in `app/dataquality.py`; a MIXED folder still lands
        # here, and it is a wall.)
        if error == "unreadable_format" and isinstance(result, dict):
            shape = result.get("format")
            kind = str((shape or {}).get("name") or "") if isinstance(shape, dict) else ""
            if kind in ("folder", "binary"):
                return True
        return False
    if not error and isinstance(result, dict) and "exit_code" in result:
        # A shell command that exited non-zero: an argument to fix, not a wall.
        return False
    if named and str(payload.get("name") or "").lower() not in named:
        # Only a step's OWN tool failing blocks that step (the build prompt
        # says as much); state_facts refusing says nothing about carving.
        return False
    return True


def _tool_refused(rows: list[dict[str, Any]], aiming: str = "") -> bool:
    """A tool on this turn refused for a reason that is a wall, not a slip."""
    named = _tools_named_in(aiming)
    for row in rows:
        if row.get("kind") != "tool.result":
            continue
        if _is_a_wall(row.get("payload") or {}, named):
            return True
    return False


def _is_full(thread_id: int) -> bool:
    from app import autonomy as _autonomy

    thread = events.get_thread(int(thread_id)) or {}
    return _autonomy.normalise(str(thread.get("permission") or "ask")) == "full"


def _settle_scaffold(thread_id: int) -> str | None:
    """AU7 — under Full, settle open ask-facts before parking plan steps."""
    from app import autonomy as _autonomy
    from app import conductor as _conductor

    thread = events.get_thread(int(thread_id)) or {}
    permission = _autonomy.normalise(str(thread.get("permission") or "ask"))
    if permission != "full":
        return None
    payload = _conductor._standing_diagnosis(int(thread_id)) or {}
    tool = _conductor._full_grind_tool(payload)
    if tool is None:
        return None
    fact = ((payload.get("next_step") or {}) if isinstance(payload.get("next_step"), dict) else {}).get("fact")
    named = f" for `{fact}`" if fact else ""
    return (
        f"[harness] Under Full, call `{tool}`{named} NOW before grinding the "
        "plan step. Do not ask the person. Do not wait for approval. "
        "Do not narrate."
    )


def _last_words(rows: list[dict[str, Any]]) -> str:
    """One short sentence for why a step was parked, not a whole reply.

    MEASURED 2026-09-13: the reason written into the plan file was the model's
    entire closing paragraph - a status report with five bullet points, inside
    a markdown list item. A parked line is read at a glance or it is not read.
    A refusal the tools gave is better than anything the reply says, so that is
    preferred; otherwise the first sentence of the last paragraph, clipped.
    """
    for row in reversed(rows):
        if row.get("kind") != "tool.result":
            continue
        payload = row.get("payload") or {}
        result = payload.get("result")
        if payload.get("ok") is False and isinstance(result, dict):
            if str(result.get("error") or "") in NOT_A_WALL:
                # An argument slip is not why a step was parked; the reply is.
                continue
            said = str(result.get("detail") or result.get("error") or "").strip()
            if said:
                return f"{payload.get('name') or 'a tool'} refused: {said[:140]}"
    said = "".join(
        str((row.get("payload") or {}).get("text") or "")
        for row in rows
        if row.get("kind") == "chat.delta"
    ).strip()
    if not said:
        return "the model said nothing about why"
    paragraphs = [p.strip() for p in said.split(chr(10) + chr(10)) if p.strip()]
    last = paragraphs[-1] if paragraphs else said
    first_sentence = last.split(". ")[0].strip().lstrip("*-# ")
    return (first_sentence[:160] or last[:160]).strip()


def _finish(thread_id: int, reason: str, detail: str, state: str = DONE) -> None:
    run_now = status(thread_id) or {}
    # A STOP THAT LEAVES PARKS SAYS HOW TO REOPEN THEM. "Start the run again,
    # or switch model" was the whole of it, and starting it again parks the
    # same steps for the same reasons. `unpark_step` is registered and, until
    # this line, was named nowhere in the product.
    if run_now.get("parked"):
        detail = (
            detail.rstrip()
            + f" {len(run_now['parked'])} step(s) stay parked; reopen any of them "
            "with `unpark_step` once the reason on the line no longer holds."
        )
    _write(thread_id, state=state, stop_reason=reason, detail=detail)
    run = status(thread_id) or {}
    thread = events.get_thread(int(thread_id)) or {}
    events.append(
        "run.finished",
        {
            "thread_id": int(thread_id),
            "reason": reason,
            "detail": detail,
            "turns": run.get("turns", 0),
            "done": run.get("done", 0),
            "open": run.get("open", 0),
            "parked": run.get("parked", []),
        },
        project_id=thread.get("project_id"),
        thread_id=int(thread_id),
    )


def _steps_outside_handed_out_phases(thread_id: int, open_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The open steps whose phase was never delegated, in plan order."""
    from app import subagents as _subagents

    thread = events.get_thread(int(thread_id)) or {}
    plan = str(planning.checklist_text(thread) or "")
    handed = _subagents.phases_handed_out(int(thread_id))
    if not handed:
        return list(open_steps)
    heading_at: dict[int, str] = {}
    heading = ""
    for index, line in enumerate(plan.splitlines()):
        stripped = line.strip()
        if stripped.startswith("## "):
            heading = stripped[3:].strip()
        heading_at[index] = heading
    return [s for s in open_steps if heading_at.get(int(s["line"]), "") not in handed]


def _open_phases_not_handed_out(thread_id: int) -> list[str]:
    """Headings of phases that still carry an open step and were never
    delegated - the parent's own work while its children have theirs."""
    from app import subagents as _subagents

    thread = events.get_thread(int(thread_id)) or {}
    plan = planning.checklist_text(thread)
    handed = _subagents.phases_handed_out(int(thread_id))
    heading = ""
    out: list[str] = []
    steps = {s["line"]: s for s in planning.steps_in(plan)}
    for index, line in enumerate(str(plan or "").splitlines()):
        stripped = line.strip()
        if stripped.startswith("## "):
            heading = stripped[3:].strip()
            continue
        step = steps.get(index)
        if step and step["state"] == "open" and heading and heading not in handed and heading not in out:
            out.append(heading)
    return out


def _wait_for_the_sub_agents(thread_id: int, *, patient: bool = True) -> str | None:
    """Hold the run while its sub-agents work; hand back what they said.

    PATIENT ONLY WHEN THERE IS NOTHING ELSE TO DO. The third live score row,
    2026-09-18: the parent handed a phase out, took two turns, and then sat
    thirty-three minutes inside this wait while one child ground a single
    step, with fourteen of its own steps open in phases nobody was working.
    With `patient=False` it folds in whatever has finished and goes back to
    its own work; the full wait is for a parent whose every open step is in
    somebody else's hands.

    Returns the digest to put on the next turn when children finished during
    the wait, `"stopped"` when the run was stopped while waiting, and `None`
    when there was nothing to wait for. A wait costs no turn: delegated work
    is being done, and charging the parent for the waiting would spend the cap
    on sleeping.
    """
    from app import subagents

    working = subagents.running_for(int(thread_id))
    if not working or not patient:
        folded = subagents.harvest(int(thread_id))
        return subagents.digest_for(int(thread_id), folded) or None

    waited = 0.0
    while waited < subagents.WAIT_AT_MOST_SECONDS:
        if _state(thread_id) != RUNNING:
            return "stopped"
        if not subagents.running_for(int(thread_id)):
            break
        time.sleep(subagents.LOOK_EVERY_SECONDS)
        waited += subagents.LOOK_EVERY_SECONDS
    folded = subagents.harvest(int(thread_id))
    return subagents.digest_for(int(thread_id), folded) or None


# ---------------------------------------------------------------------------
# THE RUN HANDS OUT THE PHASES IT IS NOT WORKING
# ---------------------------------------------------------------------------
#
# Max, 2026-09-18: *"it's not using any sub agents."* MEASURED on his database
# the same day: `delegate_phase` has been called ZERO times on a real thread.
# The machinery all works - `tests/test_one_phase_one_sub_agent.py` has proved
# it since 2026-09-13 - and nothing has ever opened the door, because the door
# is a tool call and the model has to think of making it while it is in the
# middle of a step.
#
# A RUN KNOWS SOMETHING THE MODEL DOES NOT. It knows which step it is aiming
# at, so it knows which phase is the one being worked, and the plan says in its
# own `**Tools:**` lines which tools the other phases need. A phase whose tools
# do not overlap the aimed phase's is a phase that cannot collide with what the
# parent is doing: different tools, different files, different walls. That is
# exactly what a sub-agent is for and it is decidable without a model.
#
# WHAT THIS DELIBERATELY WILL NOT DO:
#
# - It never hands out the phase the run is aiming at. That is the run eating
#   its own work: the parent would aim at a step a child is doing, fail to tick
#   it, and park it on the second strike.
# - It never hands out a phase whose tools it cannot read. A `**Tools:**` line
#   is a DECLARATION; the tool names in a step's prose are not, and a guess
#   about overlap costs an hour of a 7B's time. No line, no hand-off - from
#   either side, because disjointness is a claim about two sets and an empty
#   set makes it vacuously true.
# - It never goes past the project's cap, and zero means off - `at_most_for`
#   is the person's number (`app/settings.py`) and this reads it rather than
#   the constant.
# - It never hands the same phase out twice. The record is the `subagents`
#   table's own rows, in any state: a phase a child already worked comes back
#   through `harvest`, and a second child would start from the same words and
#   meet the same wall.
#
# AND WHAT DISJOINT TOOLS DO NOT PROVE, said here rather than discovered
# later: that the phase's INPUTS exist yet. A phase that scores an adapter
# uses none of the data pack's tools and still needs the eval set the data
# phase carves. What happens then is the ordinary shape of this product - the
# child's tool refuses, the child parks the step with the refusal as its
# reason, and the park comes back into the parent's plan where a person can
# read it (`subagents.harvest`). That is a wasted turn, not a wrong number,
# and the alternative - a dependency order nobody has declared, inferred from
# prose - would be a guess with the same failure and no reason written down.


def _tools_declared_in(lines: list[str]) -> frozenset[str]:
    """The registered tools named on this phase's `**Tools:**` line."""
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("**tools:**"):
            return _tools_named_in(stripped)
    return frozenset()


def _phases_of(plan: str) -> list[dict[str, Any]]:
    """Every `## ` phase of the plan: its heading, open steps and tools."""
    lines = str(plan or "").splitlines()
    marks = [i for i, line in enumerate(lines) if line.strip().startswith("## ")]
    out: list[dict[str, Any]] = []
    for position, index in enumerate(marks):
        heading = lines[index].strip()[3:].strip()
        end = marks[position + 1] if position + 1 < len(marks) else len(lines)
        body = lines[index:end]
        out.append(
            {
                "heading": heading,
                "open": [s["text"] for s in planning.open_steps(chr(10).join(body))],
                "tools": _tools_declared_in(body),
            }
        )
    return out


def _hand_out_a_disjoint_phase(
    thread_id: int,
    plan: str,
    aiming: str,
    delegate: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Give one phase away, if one can be given away. `None` when none can.

    One per turn, and the first candidate only: a turn that tried every phase
    in the plan until something stuck would be guessing, and the next turn
    comes round in seconds anyway.
    """
    from app import subagents

    if subagents.is_a_subagent(int(thread_id)):
        return None
    at_most = subagents.at_most_for(int(thread_id))
    if at_most <= 0 or subagents.running_anywhere() >= at_most:
        return None
    phases = _phases_of(plan)
    aimed = next((phase for phase in phases if aiming in phase["open"]), None)
    if aimed is None or not aimed["tools"]:
        return None
    handed = subagents.phases_handed_out(int(thread_id))
    for phase in phases:
        if phase["heading"] == aimed["heading"] or phase["heading"] in handed:
            continue
        if not phase["open"] or not phase["tools"]:
            continue
        if phase["tools"] & aimed["tools"]:
            continue
        out = (delegate or subagents.delegate)(int(thread_id), phase["heading"])
        if not out.get("ok"):
            return None
        thread = events.get_thread(int(thread_id)) or {}
        events.append(
            "run.delegated",
            {
                "thread_id": int(thread_id),
                "phase": phase["heading"],
                "child_thread_id": out.get("child_thread_id"),
                "tools": sorted(phase["tools"]),
                "while_aiming_at": aiming,
                "aimed_phase": aimed["heading"],
            },
            project_id=thread.get("project_id"),
            thread_id=int(thread_id),
        )
        return out
    return None


def work(
    thread_id: int,
    *,
    turn: Callable[[int], Iterable[dict[str, Any]]] | None = None,
    delegate: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The loop itself, synchronous. `start` runs this on a worker thread."""
    from app import conductor

    def _conductor_turn(tid: int, scaffold: str | None = None):
        return conductor.run_turn(tid, scaffold=scaffold)

    take_a_turn = turn or _conductor_turn
    strikes: dict[str, int] = {}
    hollow = 0
    narrated = 0
    #: Turns in a row under Full with the aimed step still open and no wall
    #: from its own tool. The third live score row, 2026-09-18: this shared
    #: `narrated`, which the narration check above zeroes every turn, so a
    #: child ran twenty-one turns on one step without ticking, parking or
    #: finishing. Its own counter, reset only when the aimed step moves.
    stalled = 0
    failures = 0
    barren = 0
    parked_in_a_row = 0
    asked_for_a_rewrite = False
    scaffold: str | None = None
    #: WHICH TURN LAST TICKED A STEP, or `None` for a run that never has. It is
    #: the only thing the cap extension reads, and it is counted here rather
    #: than derived from the plan afterwards because the plan says how many
    #: steps are done and not WHEN they became so.
    last_tick: int | None = None

    while True:
        if _state(thread_id) != RUNNING:
            break

        # WORK HANDED OUT IS STILL WORK. A parent that took a turn while its
        # sub-agents were working would aim at a step somebody else is doing,
        # fail to tick it, and park it on the second strike - the run eating
        # its own delegated work. So it waits, off the turn count, and folds
        # the results in when they land (app/subagents.py).
        own_phases = _open_phases_not_handed_out(int(thread_id))
        waited_for = _wait_for_the_sub_agents(thread_id, patient=not own_phases)
        if waited_for == "stopped":
            break
        if waited_for:
            scaffold = waited_for
            events.append(
                "run.harvested",
                {"thread_id": int(thread_id)},
                thread_id=int(thread_id),
            )

        run = status(thread_id) or {}
        turns = int(run.get("turns") or 0)
        cap = int(run.get("cap") or TURN_CAP)
        if turns >= cap:
            # PROGRESS EXTENDS THE CAP, and nothing else does. Max, 2026-09-18.
            #
            # The cap is a bound on a run that is going nowhere. A run that
            # ticked a step two turns ago is not that run, and stopping it
            # there throws away a working plan near the end of it and hands the
            # person a half-done list to restart by hand - which costs them the
            # turns already spent as well as the ones it would have taken.
            #
            # BOUNDED TWICE. The cap moves by `CAP_EXTENSION`, so the decision
            # is asked again in six turns and a run that stops moving stops;
            # and `ABSOLUTE_TURN_CEILING` is the wall no amount of ticking gets
            # past, which is what keeps this a bound being RAISED rather than a
            # bound being removed.
            moving = (
                last_tick is not None and (turns - last_tick) < PROGRESS_WINDOW
            )
            if moving and cap < ABSOLUTE_TURN_CEILING:
                cap = min(cap + CAP_EXTENSION, ABSOLUTE_TURN_CEILING)
                _write(thread_id, cap=cap)
                events.append(
                    "run.extended",
                    {
                        "thread_id": int(thread_id),
                        "turns": turns,
                        "cap": cap,
                        "ticked_on_turn": int(last_tick),
                        # THE REASON, IN THE ROW. A cap that moved is the thing
                        # somebody asks about when a run took forty turns, and
                        # a number with no sentence beside it is the log
                        # declining to answer.
                        "why": (
                            f"a step was ticked on turn {last_tick}, within "
                            f"{PROGRESS_WINDOW} turns of the cap at {turns}, "
                            f"so the run is still working the plan down; "
                            f"{CAP_EXTENSION} more turns, ceiling "
                            f"{ABSOLUTE_TURN_CEILING}"
                        ),
                    },
                    thread_id=int(thread_id),
                )
            else:
                _finish(
                    thread_id,
                    "turn_cap",
                    f"the run took its {cap} turns and handed back"
                    + (
                        f" - it reached the {ABSOLUTE_TURN_CEILING}-turn "
                        "ceiling, which no amount of progress extends past"
                        if moving
                        else ""
                    ),
                )
                break

        thread = events.get_thread(int(thread_id)) or {}
        still_open = planning.open_steps(planning.checklist_text(thread))
        # THE PARENT AIMS AT ITS OWN WORK while a phase is in a child's hands:
        # the first open step outside every handed-out phase, if there is one.
        own = _steps_outside_handed_out_phases(int(thread_id), still_open)
        if own:
            still_open = own
        if not still_open:
            now = status(thread_id) or {}
            parked = now.get("parked") or []
            done = int(now.get("done") or 0)
            # WHAT IT SAYS IS WHAT HAPPENED. Max, 2026-09-13: a run that parked
            # four of five steps reported "plan worked down", which reads as
            # success and was not. Three endings, and the words are different
            # because the outcomes are.
            if not parked:
                _finish(thread_id, "plan_worked_down", f"every step is ticked ({done})")
            elif done == 0:
                _finish(
                    thread_id,
                    "nothing_could_be_worked",
                    f"not one of the {len(parked)} steps could be done - this plan needs "
                    "rewriting as steps that name a tool and its arguments",
                )
            elif len(parked) > done:
                _finish(
                    thread_id,
                    "parked_more_than_it_did",
                    f"{done} ticked, {len(parked)} parked - more of this plan was skipped "
                    "than done, so read the parked lines before running it again",
                )
            else:
                _finish(
                    thread_id,
                    "plan_worked_down",
                    f"{done} ticked, {len(parked)} parked",
                )
            break
        aiming = still_open[0]["text"]

        # BEFORE THIS TURN AIMS, THE WORK IT IS NOT AIMING AT IS HANDED OUT.
        # See `_hand_out_a_disjoint_phase` for the whole argument and for the
        # four things it refuses to do. It costs one read of the plan and, at
        # most, one delegation a turn; the parent goes straight on to its own
        # aimed step, which is the half of this Max asked for first.
        _hand_out_a_disjoint_phase(
            int(thread_id), planning.checklist_text(thread), aiming, delegate
        )

        if scaffold is None and int(run.get("turns") or 0) == 0:
            stepless = planning.phases_without_steps(planning.checklist_text(thread))
            if stepless:
                scaffold = STEPLESS_NUDGE.format(phases="; ".join(stepless[:6]))

        # THE PARKS THIS RUN INHERITED, once, on its first turn. After
        # `stepless`, which is about a plan that cannot be worked at all and so
        # outranks a plan that can be worked but has scars on it.
        if scaffold is None and int(run.get("turns") or 0) == 0:
            inherited = [
                one
                for one in planning.steps_in(planning.checklist_text(thread))
                if one["state"] == "parked"
            ]
            if inherited:
                lines = "".join(
                    f"\n- {one['text']}" + (f" - parked because: {one['why']}" if one["why"] else "")
                    for one in inherited[:8]
                )
                scaffold = PARKED_NUDGE.format(count=len(inherited), lines=lines)

        # AU7 — settle open ask-facts under Full before striking plan steps.
        settle = _settle_scaffold(int(thread_id))
        if settle and scaffold is None:
            scaffold = settle

        before = int(events.latest_id(f"thread:{thread_id}") or 0)
        try:
            for _ in _take(take_a_turn, int(thread_id), scaffold):
                pass
        except Exception as error:  # noqa: BLE001 - a run must report, never vanish
            _finish(
                thread_id,
                "turn_failed",
                f"{type(error).__name__}: {error}",
                state=FAILED,
            )
            break

        rows = events.since(f"thread:{thread_id}", after=before, limit=5000)
        _write(thread_id, turns=turns + 1)
        # A TURN IS A TURN WHATEVER IT ENDED AS. The third live score row,
        # 2026-09-18: `run.turn` was written at the bottom of this loop, after
        # every `continue`, so an empty reply, a narrated turn and a stalled
        # turn left no row - the parent's two turns and a child's twenty-one
        # counted in `long_runs.turns` and nowhere a reader could see them,
        # and "plan written on turn 1" read false against a plan that was
        # there. Written here, once, the moment the turn is over.
        _turn_thread = events.get_thread(int(thread_id)) or {}
        events.append(
            "run.turn",
            {
                "thread_id": int(thread_id),
                "turn": turns + 1,
                "aimed_at": aiming,
                "open": len(planning.open_steps(planning.checklist_text(_turn_thread))),
            },
            project_id=_turn_thread.get("project_id"),
            thread_id=int(thread_id),
        )
        # A STEP TICKED IS THE ONLY EVIDENCE THE CAP EXTENSION ACCEPTS, and
        # `thread.step_done` is the harness's one record of one: `mark_step_done`
        # writes it when the model says so and `planning.tick_for_tool` writes
        # the same row with `by: harness` when a tool-shaped step ticks itself.
        # Counting words, or tool calls, or a turn that "looked productive"
        # would extend a run for the narration this loop already refuses to
        # treat as work.
        if any(row.get("kind") == "thread.step_done" for row in rows):
            last_tick = turns + 1
        scaffold = None

        ending = _ending(rows)
        if ending == "provider_failed":
            failures += 1
            if failures >= 2:
                _finish(
                    thread_id,
                    "provider_failed",
                    "the connection failed twice in a row; nothing was lost",
                    state=FAILED,
                )
                break
            continue
        failures = 0

        if _approval_is_waiting(rows):
            _finish(
                thread_id,
                "approval_needed",
                "a tool is waiting for your yes; approve it and start the run again",
            )
            break

        after = events.get_thread(int(thread_id)) or {}
        open_now = {
            s["text"]
            for s in planning.open_steps(planning.checklist_text(after))
        }

        # A TURN THAT PRODUCED NOTHING IS NOT EVIDENCE ABOUT THE STEP. Max,
        # 2026-09-14: *"I keep hitting this, the model returned empty quite
        # often - how come it cancels mid task? Where's our long-running task
        # policy keeping agents working and thinking instead of failing out
        # early and stopping?"*
        #
        # MEASURED on his database, last 135 turns: `empty_reply` is 5% overall
        # and 4 of 11 on thread 64. Every one of them used to cost the step it
        # was aiming at a STRIKE, because this counted "the step is still open"
        # without asking why - so two empty replies in a row PARKED a step the
        # model never attempted, with the reason "the model said nothing about
        # why". That is the "it keeps parking things" he photographed a day
        # earlier, and the park was a lie about the step.
        #
        # An empty reply and a dropped connection are faults in the turn. The
        # step is untouched by them, so the run retries it instead - bounded,
        # because a model that returns nothing forever must not spin forever.
        # (`provider_failed` never reaches here - it is caught above with its
        # own two-strike bound and its own sentence. This is the silent kind:
        # the connection worked and the model chose to say nothing.)
        if ending == "empty_reply":
            hollow += 1
            if hollow >= HOLLOW_TURNS:
                _finish(
                    thread_id,
                    "the_model_stopped_answering",
                    f"{hollow} turns in a row came back with nothing - no words and no "
                    "tool calls. This step was not parked, because a turn that produced "
                    "nothing says nothing about the steps. The plan is where it was; "
                    "start the run again, or connect a model that answers.",
                    state=FAILED,
                )
                break
            continue
        hollow = 0

        # AU7 — narration-only ("I'll get the next question…") is not a strike.
        # Screenshot 2026-09-15: Full run parked three tools after
        # said_it_would_and_did_nothing while standing still asked for
        # state_facts. Retry with a grind scaffold; bound like hollow.
        if aiming in open_now and _narrated_only(rows):
            narrated += 1
            scaffold = NARRATION_NUDGE
            if narrated >= NARRATION_TURNS:
                _finish(
                    thread_id,
                    "the_model_only_narrated",
                    f"{narrated} turns in a row announced a move and called no tool. "
                    "This step was not parked - a narration is not evidence the "
                    "step is undoable. Start the run again, or switch model.",
                    state=FAILED,
                )
                break
            continue
        narrated = 0

        if aiming in open_now:
            why = _last_words(rows)
            # Intent-as-why ("I'll read the plan…") and Full-without-a-tool-
            # refusal are not evidence the step is undoable — same honesty as
            # AU7 narration. Retry with a nudge; do not park.
            if _intent_not_a_blocker(why) or (
                _is_full(thread_id) and not _tool_refused(rows, aiming)
            ):
                stalled += 1
                scaffold = NARRATION_NUDGE
                if stalled >= NARRATION_TURNS:
                    _finish(
                        thread_id,
                        "the_model_only_narrated",
                        f"{stalled} turns in a row could not show a real blocker "
                        "for the open step (no tool refusal - only narration or "
                        "intent), so this step was not parked. Start the run "
                        "again, or switch model.",
                        state=FAILED,
                    )
                    break
                continue
            strikes[aiming] = strikes.get(aiming, 0) + 1
            barren += 1
            if strikes[aiming] >= STRIKES:
                planning.park_step(thread_id, aiming, why)
                strikes.pop(aiming, None)
                parked_in_a_row += 1
                # THREE IN A ROW IS A PLAN, NOT THREE STEPS. Grinding through
                # the rest to park them too spends an hour proving what the
                # third one already said.
                if parked_in_a_row >= PARKS_IN_A_ROW:
                    _finish(
                        thread_id,
                        "the_plan_could_not_be_worked",
                        f"{parked_in_a_row} steps in a row could not be done - the plan is "
                        "the problem rather than the effort. Rewrite the open steps as "
                        "actions that name a tool, then run it again.",
                    )
                    break
        else:
            strikes.pop(aiming, None)
            stalled = 0
            barren = 0
            parked_in_a_row = 0
            narrated = 0

        # THE PLAN IS THE SUSPECT WHEN NOTHING MOVES. Asked once per run: a
        # second rewrite would be the loop this exists to break. This also
        # clears a sub-agent digest, which belongs to exactly one turn: the
        # one after the work came back.
        scaffold = None
        if barren >= REPLAN_AFTER and not asked_for_a_rewrite:
            asked_for_a_rewrite = True
            barren = 0
            scaffold = REPLAN_NUDGE
            events.append(
                "run.replan",
                {"thread_id": int(thread_id), "after_turns": int(run.get("turns") or 0) + 1},
                project_id=after.get("project_id"),
                thread_id=int(thread_id),
            )

        thread_after = events.get_thread(int(thread_id)) or {}

    _WORKERS.pop(int(thread_id), None)
    return status(thread_id) or {}
