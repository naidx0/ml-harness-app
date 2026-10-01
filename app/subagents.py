"""One phase, one sub-agent: work handed out so the orchestrator keeps its head.

Max, 2026-09-13: *"We have our main agent and it's an orchestrator, and then
whenever it comes up with a plan, it goes and it gives one phase of that plan
to one sub-agent... we have a weak model, so at the most we can run two. The
sub-agent, it can build, it can write, it could read, it can do anything on
the computer in that context, in that folder. And then the orchestrator model
just waits for the agent to finish, and it reads its responses, so it doesn't
burn up its own context window."*

## Why a phase and not a step

A step is one call. Handing a step to a sub-agent buys nothing: setting one up
costs more than making the call. A PHASE is a body of work with its own
reading, its own files and its own dead ends - which is exactly what fills a
context window, and exactly what the orchestrator does not want in its own. So
the unit is the phase, and what comes back is the ticks, the parks and one
closing line. `digest_for` is the whole interface.

## Why two

Because the model is small and it is the same model. Two sub-agents against one
local 7B is two turns in flight on one card; three is three queued turns
pretending to be parallel. `AT_MOST_RUNNING` is that number, and it counts
across the whole machine rather than per conversation - two here and two there
is still four turns on one card. `delegate` refuses rather than queues: a
refusal the orchestrator can read and act on beats a queue it cannot see.

## Why the child is an ordinary thread

It has a project, a workspace root, a plan, a mode and a run. It writes files in
the project folder, calls every tool the pack offers and takes turns until its
steps are worked down, because it IS the same machinery - `longrun.work` over
`conductor.run_turn`. Nothing here is a second kind of agent. What makes it a
sub-agent is one row saying which conversation asked for it and which phase it
was given.

It also means a person can open it. The transcript is there, in the rail, under
the phase's name; the orchestrator does not read it and a person can.

## What comes back, and what does not

`harvest` folds a finished child into the parent's plan: every step the child
ticked is ticked in the parent, every step it parked is parked with the child's
reason. Then `digest_for` writes those counts and the closing line as
scaffolding for the parent's next turn. The child's transcript never enters the
parent's messages. That is the point of the module - a phase costs the
orchestrator a paragraph instead of a context window.

## No recursion

A sub-agent may not delegate. One level, checked at the door by `is_a_subagent`:
a tree of agents spawning agents against a 7B is a way to spend a night on
nothing, and nobody asked for it.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

from app import db, events
from app.tools import planning

#: HOW MANY MAY WORK AT ONCE, ACROSS THE MACHINE. Max: *"we have a weak model,
#: so at the most we can run two."*
AT_MOST_RUNNING = 2


def at_most_for(thread_id: int | None) -> int:
    """How many this project may run at once - the person's number, or 2.

    Max, 2026-09-14: *"let you configure the tools, like how many sub-agents
    you want to be using, if any at all."* Zero is a real answer and it means
    delegation is off: `delegate` refuses at the door and says the number,
    rather than starting one and hoping nobody notices.

    Falls back to the constant on any fault, because a settings table that
    cannot be read is a settings table nobody set, and the default is what
    every project ran on before this existed.
    """
    try:
        from app import settings as _settings

        return int(_settings.for_thread(thread_id)["subagents_max"])
    except Exception:  # noqa: BLE001 - never fail a delegation over a setting
        return AT_MOST_RUNNING

#: How long a waiting parent sleeps between looks at its children. A turn takes
#: tens of seconds; two is soon enough to notice and cheap enough not to matter.
LOOK_EVERY_SECONDS = 2.0

#: The longest a parent waits on its children before it stops waiting and says
#: so. A run that waits forever on a child that wedged is a run nobody can read.
WAIT_AT_MOST_SECONDS = 2 * 60 * 60

RUNNING = "running"
DONE = "done"
STOPPED = "stopped"
FAILED = "failed"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS subagents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_thread_id INTEGER NOT NULL,
    child_thread_id INTEGER NOT NULL,
    phase TEXT NOT NULL,
    state TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    closing TEXT NOT NULL DEFAULT '',
    harvested INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_subagents_parent ON subagents(parent_thread_id);
CREATE INDEX IF NOT EXISTS idx_subagents_child ON subagents(child_thread_id);
"""

_WORKERS: dict[int, threading.Thread] = {}


def ensure_table() -> None:
    with db.session() as connection:
        connection.executescript(_SCHEMA)


def reap_orphans() -> int:
    """End delegations whose worker died with the engine. Called at startup.

    Same argument as `longrun.reap_orphans`, and it must run after that one: a
    sub-agent's state is read from its child's run, so reaping the runs first
    means these rows are settled against a settled truth.
    """
    ensure_table()
    with db.session() as connection:
        rows = connection.execute(
            "SELECT id FROM subagents WHERE state = ?", (RUNNING,)
        ).fetchall()
        if rows:
            connection.execute(
                "UPDATE subagents SET state = ?, reason = ?, detail = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE state = ?",
                (
                    STOPPED,
                    "engine_restarted",
                    "the engine stopped while this sub-agent was working; what it "
                    "had already done is in its own conversation",
                    RUNNING,
                ),
            )
    return len(rows)


def is_a_subagent(thread_id: int) -> bool:
    """Was this conversation opened as somebody else's sub-agent?"""
    ensure_table()
    with db.session() as connection:
        row = connection.execute(
            "SELECT 1 FROM subagents WHERE child_thread_id = ?", (int(thread_id),)
        ).fetchone()
    return row is not None


def phase_slice(plan: str, phase: str) -> dict[str, Any] | None:
    """The named `## ` phase of a plan: its heading, its lines, its open steps.

    Matched on a few of the heading's words, the way `mark_step_done` matches a
    step, because a model naming a phase will not reproduce the numbering.
    `None` when nothing matches or when more than one does - a guess about which
    phase to hand out is a guess about an hour of work.
    """
    lines = str(plan or "").splitlines()
    marks = [i for i, line in enumerate(lines) if line.strip().startswith("## ")]
    wanted = " ".join(str(phase or "").lower().split())
    if not wanted or not marks:
        return None
    hits: list[dict[str, Any]] = []
    for position, index in enumerate(marks):
        heading = lines[index].strip()[3:].strip()
        if wanted in " ".join(heading.lower().split()):
            end = marks[position + 1] if position + 1 < len(marks) else len(lines)
            hits.append({"heading": heading, "start": index, "end": end})
    if len(hits) != 1:
        exact = [h for h in hits if " ".join(h["heading"].lower().split()) == wanted]
        if len(exact) != 1:
            return None
        hits = exact
    found = hits[0]
    found["lines"] = lines[found["start"] : found["end"]]
    found["steps"] = [
        step
        for step in planning.steps_in(chr(10).join(found["lines"]))
        if step["state"] == "open"
    ]
    return found


def _brief(parent: dict[str, Any], found: dict[str, Any]) -> str:
    """The child's plan: its phase, where it came from, and the open steps.

    A `# ` title so the goal card has a name to draw, a sentence of provenance
    so a person opening the thread knows who asked, and the steps copied
    verbatim - the same words the parent will tick when they come back, which is
    what makes the fold-back a match rather than a guess.
    """
    who = str(parent.get("title") or "a conversation").strip()
    out = [
        "# " + found["heading"],
        "",
        'Delegated by "' + who + '" (conversation ' + str(parent.get("id")) + "). Work",
        "these steps to the end in this project folder, then stop. What you tick",
        "and what you park is what gets reported back.",
        "",
        "## Steps",
    ]
    out.extend("- [ ] " + step["text"] for step in found["steps"])
    return chr(10).join(out) + chr(10)


def _rows_for(parent_thread_id: int, state: str | None = None) -> list[dict[str, Any]]:
    ensure_table()
    sql = "SELECT * FROM subagents WHERE parent_thread_id = ?"
    args: list[Any] = [int(parent_thread_id)]
    if state is not None:
        sql += " AND state = ?"
        args.append(state)
    sql += " ORDER BY id"
    with db.session() as connection:
        return [dict(row) for row in connection.execute(sql, tuple(args)).fetchall()]


def running_for(parent_thread_id: int) -> list[dict[str, Any]]:
    """The sub-agents of this conversation that are still working."""
    return _rows_for(parent_thread_id, RUNNING)


def phases_handed_out(parent_thread_id: int) -> set[str]:
    """Every phase heading this conversation has already given to a sub-agent.

    ANY STATE, which is the point of it. `app/longrun.py` hands phases out by
    itself now (2026-09-18), turn after turn, and a record of only the RUNNING
    ones would hand the same phase out again the moment the first child
    finished - a second agent starting from the same words, meeting the same
    wall the first one reported, for as long as the run lasts. A phase that was
    worked came back through `harvest`; a phase that failed said why. Neither
    is a reason to spend another agent on it.

    The table is the record because it already is one: a row per delegation,
    with the heading it was given, surviving a restart the way nothing held in
    the loop's own memory could.
    """
    return {str(row["phase"]) for row in _rows_for(int(parent_thread_id))}


def running_anywhere() -> int:
    """How many sub-agents are working across every conversation."""
    ensure_table()
    with db.session() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS n FROM subagents WHERE state = ?", (RUNNING,)
        ).fetchone()
    return int(row["n"] if row else 0)


def _row(subagent_id: int) -> dict[str, Any] | None:
    ensure_table()
    with db.session() as connection:
        row = connection.execute(
            "SELECT * FROM subagents WHERE id = ?", (int(subagent_id),)
        ).fetchone()
    return None if row is None else dict(row)


def _write(subagent_id: int, **fields: Any) -> None:
    ensure_table()
    sets = ", ".join(key + " = ?" for key in fields)
    with db.session() as connection:
        connection.execute(
            "UPDATE subagents SET " + sets + ", updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (*fields.values(), int(subagent_id)),
        )


def delegate(
    parent_thread_id: int,
    phase: str,
    *,
    background: bool = True,
    run: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Hand one phase of the parent's plan to a sub-agent, and start it working.

    Refuses, with words rather than a queue, when: the phase does not name
    exactly one heading, the phase has no open steps, this conversation is
    itself a sub-agent, or two sub-agents are already working.

    `run` is what starts the child's run, defaulting to `longrun.start`. It is a
    parameter so a test can drive the delegation without a model, and for no
    other reason.
    """
    parent = events.get_thread(int(parent_thread_id))
    if parent is None:
        return {"ok": False, "error": "no_such_thread", "thread_id": parent_thread_id}
    if is_a_subagent(int(parent_thread_id)):
        return {
            "ok": False,
            "error": "sub_agents_do_not_delegate",
            "detail": (
                "This conversation is itself a sub-agent working one phase. Work "
                "your own steps; the orchestrator hands out the phases."
            ),
        }
    found = phase_slice(parent.get("plan") or "", phase)
    if found is None:
        headings = planning.headings_in(parent.get("plan") or "")
        return {
            "ok": False,
            "error": "no_such_phase",
            "detail": (
                "Name one `## ` phase of the plan, in enough of its own words to "
                "match exactly one."
            ),
            "phases": headings,
        }
    if not found["steps"]:
        return {
            "ok": False,
            "error": "phase_has_no_open_steps",
            "detail": (
                'Every step under "' + found["heading"] + '" is already ticked or '
                "parked, so there is nothing to hand out."
            ),
        }
    already = running_anywhere()
    at_most = at_most_for(parent_thread_id)
    if at_most <= 0:
        return {
            "ok": False,
            "error": "subagents_are_off",
            "detail": (
                "Sub-agents are switched off for this project, so there is "
                "nobody to hand a phase to. Work the step yourself, or turn "
                "them on in the project's settings."
            ),
            "at_most": 0,
        }
    if already >= at_most:
        return {
            "ok": False,
            "error": "at_the_limit",
            "detail": (
                "Two sub-agents are already working, which is all this machine "
                "runs at once. Wait for one to finish - check_the_sub_agents "
                "tells you what they are doing - then hand out the next phase."
            ),
            "running": already,
            "at_most": at_most,
        }

    child = events.create_thread(
        title=found["heading"],
        project_id=parent.get("project_id"),
        ledger=parent.get("ledger"),
        mode="build",
        # A SUB-AGENT IS HANDED ONE PHASE AND NOT THE FOLDER'S WHOLE PLAN. A
        # new conversation in a project that has a `project-plan.md` adopts a
        # copy of it (2026-09-18, app/planfile.py); this one is about to be
        # given its brief on the next line, and a child that carried the whole
        # plan for those two statements is a second orchestrator for two
        # statements - and a `thread.plan_adopted` row in its transcript that
        # was never true of it.
        adopt_project_plan=False,
    )
    child_id = int(child["id"])
    events.set_thread_plan(child_id, _brief(parent, found))
    if parent.get("autonomous"):
        # A SUB-AGENT INHERITS THE LEASH IT WAS GIVEN. Autonomy is a person's
        # decision about a conversation; delegating a phase out of an
        # autonomous conversation without it would stop the child on the first
        # gate the parent had already been told to pass.
        events.set_thread_autonomous(child_id, True)
    # AND THE PERMISSION STEP, which is the leash's real name since CS1. The
    # second live score row, 2026-09-18: five children of a Full parent ran
    # under `write`, so none could settle an ask-fact by rule and all five
    # parked on "which task_family fits your use case?" - a question their
    # parent had been told never to ask.
    from app import autonomy as _autonomy

    inherited = _autonomy.normalise(str(parent.get("permission") or "ask"))
    if inherited in ("write", "full"):
        events.set_thread_permission(child_id, inherited)

    ensure_table()
    with db.session() as connection:
        cursor = connection.execute(
            "INSERT INTO subagents(parent_thread_id, child_thread_id, phase, state) "
            "VALUES (?, ?, ?, ?)",
            (int(parent_thread_id), child_id, found["heading"], RUNNING),
        )
        subagent_id = int(cursor.lastrowid)

    events.append(
        "subagent.started",
        {
            "subagent_id": subagent_id,
            "thread_id": int(parent_thread_id),
            "child_thread_id": child_id,
            "phase": found["heading"],
            "steps": [step["text"] for step in found["steps"]],
            "running": already + 1,
        },
        project_id=parent.get("project_id"),
        thread_id=int(parent_thread_id),
    )

    start_the_run = run or _start_child_run
    outcome = start_the_run(child_id, background=background)
    if not outcome.get("ok"):
        _write(
            subagent_id,
            state=FAILED,
            reason=str(outcome.get("error") or "would_not_start"),
            detail=str(outcome.get("detail") or ""),
        )
        return {
            "ok": False,
            "error": "would_not_start",
            "detail": outcome.get("detail") or outcome.get("error") or "",
            "subagent_id": subagent_id,
            "child_thread_id": child_id,
        }

    if background:
        watcher = threading.Thread(
            target=_watch,
            args=(subagent_id,),
            name="mlh-subagent-" + str(subagent_id),
            daemon=True,
        )
        _WORKERS[subagent_id] = watcher
        watcher.start()
    else:
        settle(subagent_id)

    return {
        "ok": True,
        "subagent_id": subagent_id,
        "child_thread_id": child_id,
        "phase": found["heading"],
        "steps": [step["text"] for step in found["steps"]],
        "running": running_anywhere(),
        "at_most": at_most,
    }


def _start_child_run(child_id: int, *, background: bool = True) -> dict[str, Any]:
    from app import longrun

    return longrun.start(child_id, background=background)


def _watch(subagent_id: int) -> None:
    """Follow one child's run to its end and record how it ended.

    A thread that sleeps, so the delegation's row is settled the moment the run
    is, without the parent having to ask. `settle` is the same read, and the
    parent calls it too - whichever gets there first writes the same thing.
    """
    waited = 0.0
    while waited < WAIT_AT_MOST_SECONDS:
        if settle(subagent_id) is not None:
            break
        time.sleep(LOOK_EVERY_SECONDS)
        waited += LOOK_EVERY_SECONDS
    _WORKERS.pop(int(subagent_id), None)


def settle(subagent_id: int) -> dict[str, Any] | None:
    """If the child's run has ended, write that ending onto the delegation.

    Returns the settled row, or `None` while it is still working. Idempotent:
    called by the watcher, by the parent's loop and by any read of the list, and
    all three write the same ending.
    """
    from app import longrun

    row = _row(subagent_id)
    if row is None:
        return None
    if str(row.get("state")) != RUNNING:
        return row
    run = longrun.status(int(row["child_thread_id"])) or {}
    state = str(run.get("state") or "")
    if state in ("", longrun.RUNNING):
        return None
    ended = {
        longrun.DONE: DONE,
        longrun.FAILED: FAILED,
        longrun.STOPPED: STOPPED,
    }.get(state, DONE)
    _write(
        subagent_id,
        state=ended,
        reason=str(run.get("stop_reason") or ""),
        detail=str(run.get("detail") or ""),
    )
    child = events.get_thread(int(row["child_thread_id"])) or {}
    events.append(
        "subagent.finished",
        {
            "subagent_id": int(subagent_id),
            "thread_id": int(row["parent_thread_id"]),
            "child_thread_id": int(row["child_thread_id"]),
            "phase": row.get("phase"),
            "state": ended,
            "reason": run.get("stop_reason"),
            "detail": run.get("detail"),
            "done": run.get("done"),
            "parked": run.get("parked"),
        },
        project_id=child.get("project_id"),
        thread_id=int(row["parent_thread_id"]),
    )
    return _row(subagent_id)


def work_of(child_thread_id: int) -> dict[str, Any]:
    """What a sub-agent actually spent: tools run, by name, and context.

    Max, 2026-09-19: *"a bit more information on those agents... how much
    context was used, and what tools they ran collectively. Is it 85 tools
    used? And if you click expand, you can really view them all."* The board
    could say how many STEPS a child ticked and nothing about what it did to
    tick them - so a phase that burned nine turns on one lookup and a phase
    that ran twelve different tools drew the same card.

    Read off the child's own event log rather than kept in a column: the log
    is written by the conductor as the work happens and cannot disagree with
    itself, and a counter would have to be incremented by every path that can
    run a tool. `turn.context` carries the whole turn's token figure, so the
    peak is the widest this child's prompt ever got - the number that says
    whether it was close to the window, which a sum would hide.
    """
    from collections import Counter

    names: list[str] = []
    failed = 0
    peak = 0
    for row in events.since(f"thread:{int(child_thread_id)}", limit=100_000):
        kind = row.get("kind")
        payload = row.get("payload") or {}
        if kind == "tool.call":
            name = str(payload.get("name") or "")
            if name:
                names.append(name)
        elif kind == "tool.result" and payload.get("ok") is False:
            failed += 1
        elif kind == "turn.context":
            try:
                peak = max(peak, int(payload.get("total") or 0))
            except (TypeError, ValueError):
                pass
    counted = Counter(names)
    return {
        "tools_run": len(names),
        "tools_failed": failed,
        "tools_distinct": len(counted),
        "tool_names": [
            {"name": name, "times": times} for name, times in counted.most_common()
        ],
        "context_peak_tokens": peak,
    }


def read(parent_thread_id: int) -> dict[str, Any]:
    """Every sub-agent this conversation has sent out, and what each is doing.

    What the strip in the interface draws, and the same read the tool answers
    from. Each row carries the child's step counts so a person can watch a phase
    being worked without opening it.

    AND IT FOLDS FINISHED WORK BACK IN, which is a write on a read and is
    deliberate. `delegate_phase` promises the model that a sub-agent's result
    comes back into the plan on its own; under a long run `longrun` harvests and
    that is true, but a model that hands a phase out in an ordinary turn has no
    run, and nothing folded until somebody called `check_the_sub_agents`. Its
    next turn then read a stale plan and the promise was a lie. This is the one
    function every door goes through - the strip's poll, the route, the tool -
    so folding here makes it true within one poll of the child ending, whoever
    was reading. Idempotent by the `harvested` column, which is asserted.
    """
    from app import longrun

    harvest(int(parent_thread_id))
    out = []
    for row in _rows_for(parent_thread_id):
        settle(int(row["id"]))
        row = _row(int(row["id"])) or row
        child_id = int(row["child_thread_id"])
        run = longrun.status(child_id) or {}
        child = events.get_thread(child_id) or {}
        steps = planning.steps_in(child.get("plan") or "")
        out.append(
            {
                "id": int(row["id"]),
                "thread_id": child_id,
                "phase": row.get("phase"),
                "state": row.get("state"),
                "reason": row.get("reason"),
                "detail": row.get("detail"),
                "harvested": bool(row.get("harvested")),
                "turns": int(run.get("turns") or 0),
                "seconds": run.get("seconds"),
                "steps": len(steps),
                "done": sum(1 for s in steps if s["state"] == "done"),
                "open": sum(1 for s in steps if s["state"] == "open"),
                "parked": [
                    {"step": s["text"], "why": s["why"]}
                    for s in steps
                    if s["state"] == "parked"
                ],
                # CS4 — inspector pane: aimed packs and last harvest digest,
                # not only the foot board's counts.
                "packs": packs_for(child_id),
                "last_digest": last_digest_for(
                    int(row["id"]), int(parent_thread_id)
                ),
                "started_at": row.get("started_at"),
                "updated_at": row.get("updated_at"),
                # WHAT IT WAS TOLD AND WHAT IT SPENT. The brief is the plan
                # `_brief` wrote when the phase was handed out - the child's
                # instructions, verbatim, which is the one thing a person
                # reading a finished phase most wants and could not see.
                "brief": child.get("plan") or "",
                **work_of(child_id),
            }
        )
    return {
        "thread_id": int(parent_thread_id),
        "subagents": out,
        "running": sum(1 for row in out if row["state"] == RUNNING),
        "running_anywhere": running_anywhere(),
        "at_most": at_most_for(parent_thread_id),
    }


def packs_for(child_thread_id: int) -> list[str]:
    """Packs a sub-agent's turn would load (core + tools named in its phase)."""
    try:
        from app.tools import blocks

        payload = {
            "ok": True,
            "outcome": "",
            "verdict": "BLOCKED",
            "path": [],
            "alternatives": [],
            "unsubstantiated": [],
            "gate_ledger": {},
        }
        active = blocks.active(payload, thread_id=int(child_thread_id))
        return sorted(active.packs)
    except Exception:  # noqa: BLE001 — pane read must not fail the list
        return []


def last_digest_for(subagent_id: int, parent_thread_id: int) -> str:
    """The last harvest paragraph for this worker, or empty while it runs."""
    for row in reversed(list(events.since(f"thread:{parent_thread_id}", limit=8_000))):
        if row.get("kind") != "subagent.harvested":
            continue
        payload = row.get("payload") or {}
        if int(payload.get("id") or 0) != int(subagent_id):
            continue
        return digest_for(int(parent_thread_id), [payload])
    return ""


def harvest(parent_thread_id: int) -> list[dict[str, Any]]:
    """Fold every finished, unharvested sub-agent back into the parent's plan.

    A step the child ticked is ticked in the parent; a step it parked is parked
    in the parent with the child's reason; a step it left open is parked saying
    the sub-agent did not reach it, because a step nobody worked must not sit
    open forever waiting for a sub-agent that has already stopped.

    Matching is by the step's own words, which the brief copied verbatim from
    the parent, so this is a match rather than a guess. Returns one summary per
    sub-agent folded, which is what `digest_for` turns into words.
    """
    folded = []
    for row in _rows_for(parent_thread_id):
        settle(int(row["id"]))
        row = _row(int(row["id"])) or row
        if str(row.get("state")) == RUNNING or row.get("harvested"):
            continue
        child_id = int(row["child_thread_id"])
        child = events.get_thread(child_id) or {}
        steps = planning.steps_in(child.get("plan") or "")
        ticked, parked, unreached = [], [], []
        for step in steps:
            if step["state"] == "done":
                if planning.tick_step(int(parent_thread_id), step["text"]) is not None:
                    ticked.append(step["text"])
            elif step["state"] == "parked":
                why = step["why"] or "the sub-agent could not do it"
                if planning.park_step(int(parent_thread_id), step["text"], why) is not None:
                    parked.append({"step": step["text"], "why": why})
            else:
                why = "the sub-agent stopped before reaching it: " + (
                    str(row.get("detail") or row.get("reason") or "no reason recorded")
                )
                if planning.park_step(int(parent_thread_id), step["text"], why) is not None:
                    unreached.append(step["text"])
        _write(int(row["id"]), harvested=1, closing=str(row.get("detail") or ""))
        # AND THE CONVERSATION CLOSES. Max, 2026-09-14: *"once they stop
        # running they should be closed, only shown when they are running
        # under one plan or session. Once those phases finish then they should
        # close the session so they can't be seen, for easy UX."*
        #
        # ARCHIVED, NOT DELETED, and the distinction is the whole reason this
        # is safe: `events.archive_thread` writes a timestamp and takes the
        # thread out of the rail, leaving every message and every event exactly
        # where they are. What the sub-agent did is already in the parent's
        # plan by the three loops above, and its own reasoning stays on the
        # record for anyone who goes looking. A person is not asked to keep
        # track of six finished conversations they never opened.
        events.archive_thread(child_id)
        summary = {
            "id": int(row["id"]),
            "thread_id": child_id,
            "phase": row.get("phase"),
            "state": row.get("state"),
            "reason": row.get("reason"),
            "detail": row.get("detail"),
            "ticked": ticked,
            "parked": parked,
            "unreached": unreached,
        }
        folded.append(summary)
        parent = events.get_thread(int(parent_thread_id)) or {}
        events.append(
            "subagent.harvested",
            {"thread_id": int(parent_thread_id), **summary},
            project_id=parent.get("project_id"),
            thread_id=int(parent_thread_id),
        )
    return folded


def digest_for(parent_thread_id: int, folded: list[dict[str, Any]]) -> str:
    """What the orchestrator is told, in one paragraph per sub-agent.

    THIS IS THE WHOLE ECONOMY OF THE FEATURE. A phase worked by a sub-agent
    might be forty turns and two hundred thousand characters of reading; what
    reaches the orchestrator is its name, what it ticked, what it parked and
    why. Nothing here quotes the child's transcript, and nothing should: the
    orchestrator that reads a transcript has not saved a context window, it has
    borrowed one.
    """
    if not folded:
        return ""
    said = [
        "[harness] Work you handed out has come back. The plan has already been "
        "updated with what each sub-agent ticked and parked - do not redo it."
    ]
    for one in folded:
        line = ['A sub-agent finished "' + str(one["phase"]) + '":']
        line.append(str(len(one["ticked"])) + " step(s) done")
        if one["parked"]:
            line.append(str(len(one["parked"])) + " parked")
        if one["unreached"]:
            line.append(str(len(one["unreached"])) + " never reached")
        said.append(", ".join(line) + ".")
        for parked in one["parked"][:4]:
            said.append('  parked "' + str(parked["step"]) + '" - ' + str(parked["why"]))
        if one["unreached"]:
            said.append("  it stopped because: " + str(one["detail"] or one["reason"]))
    said.append(
        "Carry on with the plan: hand out the next phase with delegate_phase, or "
        "work the next open step yourself."
    )
    return chr(10).join(said)


def stop(subagent_id: int, reason: str = "stopped by hand") -> dict[str, Any] | None:
    """Ask one sub-agent to stop, on its own thread, at its next round boundary.

    THE CHILD'S OWN THREAD ID IS THE ONE THAT HAS TO CARRY THE STOP, and that
    is the whole of the fix. A child takes its turns on `child_thread_id`, so
    a stop asked for on the PARENT is a flag the child's conductor never
    reads; measured 2026-09-19, a stopped parent left both its children
    streaming a full turn each. `longrun.stop` now asks `interrupt` on the id
    it is given, so passing the child's id here is what stops the child.

    The row is written only when something was actually stopped. It used to be
    written unconditionally, which left the delegation row claiming STOPPED
    for a child whose run had already finished on its own - and `running_for`
    reads this table, so nothing would ever look at it again.
    """
    from app import longrun

    row = _row(subagent_id)
    if row is None:
        return None
    was = str(row.get("state") or "")
    longrun.stop(int(row["child_thread_id"]), reason)
    if was == RUNNING:
        _write(subagent_id, state=STOPPED, reason=reason)
    return _row(subagent_id)


def stop_all(parent_thread_id: int, reason: str = "stopped by hand") -> int:
    """Stop every working sub-agent of this conversation."""
    rows = running_for(parent_thread_id)
    for row in rows:
        stop(int(row["id"]), reason)
    return len(rows)
