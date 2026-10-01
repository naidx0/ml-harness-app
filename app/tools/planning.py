"""The plan is a tool call, not a chat message - because a small model acts.

## What this was written from

2026-09-11, thread 64, `minicpm5-hermes` in plan mode, autonomous on. Two
turns in a row went the same way: eight lookups - `read_the_standing_constraints`,
`list_context`, `what_is_missing`, `read_eval_results`, `list_local_models`,
`map_the_ask` - and then `empty_reply`. No words, no plan. Max, watching it:
*"it's not making a plan. It's not writing any markdowns. It seems to maybe be
restricted in some sense."*

It was, and the restriction was mine. Plan mode had been handed lookups only,
and a lookup answers a question about the world; none of them PRODUCES the
thing the mode exists for. A model that acts through tools kept choosing the
next lookup because that was the only kind of move on offer, spent its budget,
and had nothing to say when the budget ran out.

`app/conductor.py` had already measured the shape of this fault: withdraw the
engine and the same model goes silent thirteen turns in twenty, "denied the
engine, this model has no move on the product's central question and says
nothing at all". Plan mode reproduced that result one mode over.

## What these two do about it

`write_plan` IS the move. It takes the phased markdown and saves it as the
thread's plan - the same column `POST /api/threads/{id}/plan` writes, the same
thing the Plan pane shows and Build works down. Calling it ends the search for
the next lookup, because the plan is now the deliverable and it has been
delivered. A revision is a second call.

`read_plan` is how the model revises without the harness quoting the draft
back at it every turn. `_plan_note` is empty in plan mode ON PURPOSE - a draft
handed back as a standing instruction has the conversation arguing with an
earlier version of itself - so reading it is a choice the model makes when it
wants to change something, not a thing that happens to it.

## What they will not do

Neither one starts anything. `write_plan` writes a column; it does not switch
the thread to `build`, because a mode is set by a person and never by a model
(`app/modes.py`). Pressing Build is still the person's click.
"""

from __future__ import annotations

import re
from typing import Any

from app import events, plandiff
from app.tools.registry import tool

#: A plan so short it cannot be a plan. Forty characters is a sentence.
TOO_SHORT_TO_BE_A_PLAN = 40


def checklist_text(thread: dict[str, Any] | None) -> str:
    """CS9 — the markdown list longrun and GoalBar work right now."""
    row = thread or {}
    if str(row.get("checklist_source") or "plan") == "todo":
        return str(row.get("todo") or "")
    return str(row.get("plan") or "")


def _phases_in(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.lstrip().startswith("## "))


#: A step written loosely - `- []`, `-[ ]`, `- [x ]` - is still a step. Max's
#: thread 75, 2026-09-17: a rewrite produced `- []` and the parser stopped
#: seeing six steps, so the bar read 0 of 0 and nothing could be unparked.
#: Written as `- [ ]` on save, so every later reader sees one shape.
BS = chr(92)
_LOOSE_STEP = re.compile("^(" + BS + "s*[-*])" + BS + "s*" + BS + "[" + BS + "s*([xX!]?)" + BS + "s*" + BS + "]" + BS + "s*(.*)$")


def tidy_steps(text: str) -> str:
    """Every loosely written step line rewritten as `- [ ] text`."""
    out = []
    for line in str(text or '').splitlines():
        match = _LOOSE_STEP.match(line)
        if match and not _STEP.match(line):
            mark = match.group(2) or ' '
            line = f"{match.group(1)} [{mark}] {match.group(3).strip()}"
        out.append(line)
    return chr(10).join(out) + (chr(10) if str(text or '').endswith(chr(10)) else '')


#: A PLAN OF BULLETS IS A PLAN OF STEPS NOBODY MARKED. Journey 2026-09-25 18:00Z
#: (H-path-e run 1): five phases of `- \`drop_duplicates\` on ...` bullets and no
#: `- [ ]` line, so the run endpoint found nothing to work and the journey ended
#: after one turn (1 of 15 plans). Only when a plan has no step line at all, a
#: plain bullet under a `## Phase` heading that names a registered tool is saved
#: as an open step. A plan with any step line is left exactly as written.
_BULLET = re.compile(r"^(\s*[-*])\s+(?!\[)(\S.*)$")


def bullets_as_steps(text: str) -> str:
    lines = str(text or '').split(chr(10))
    if any(_STEP.match(line) for line in lines):
        return text
    from app.tools.registry import REGISTRY as _registry

    names = [n for n in (str(getattr(spec, 'name', '') or '').lower() for spec in _registry) if n]
    out: list[str] = []
    in_phase = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('## '):
            in_phase = stripped[3:].strip().lower().startswith('phase')
        match = _BULLET.match(line) if in_phase else None
        if match and any(name in match.group(2).lower() for name in names):
            line = f"{match.group(1)} [ ] {match.group(2)}"
        out.append(line)
    return chr(10).join(out)


def phases_without_steps(text: str) -> list[str]:
    """`## Phase` headings whose section carries no step line."""
    out: list[str] = []
    heading: str | None = None
    seen = False
    for line in str(text or '').splitlines():
        stripped = line.strip()
        if stripped.startswith('## '):
            if heading is not None and not seen:
                out.append(heading)
            name = stripped[3:].strip()
            heading = name if name.lower().startswith('phase') else None
            seen = False
        elif _STEP.match(line):
            seen = True
    if heading is not None and not seen:
        out.append(heading)
    return out


def steps_without_a_tool(text: str) -> list[str]:
    """Open steps naming no registered tool - a condition, not an action."""
    from app.tools.registry import REGISTRY as _registry

    names = [str(getattr(spec, 'name', '') or '').lower() for spec in _registry]
    out: list[str] = []
    for step in open_steps(text):
        low = str(step['text']).lower()
        if not any(name and name in low for name in names):
            out.append(str(step['text']))
    return out


@tool(
    name="write_plan",
    #: TERSE ON PURPOSE. Every word here is on every prompt that offers the
    #: tool, and `_mode_note` already explains its role in planning; the
    #: first draft was three times this length and pushed the measured
    #: prompt budget over by fifty-eight tokens.
    description=(
        "Save this conversation's plan as markdown with a `## Phase N - ...` "
        "heading per phase. Calling this is how a plan is delivered; call it "
        "again to revise."
    ),
    schema={
        "type": "object",
        "properties": {
            "plan": {
                "type": "string",
                "description": (
                    "The whole plan, as markdown, with phases as "
                    "`## Phase N - ...` headings."
                ),
            },
            "thread_id": {
                "type": "integer",
                "description": "The conversation this plan belongs to. Filled in for you.",
            },
        },
        "required": ["plan"],
    },
    reads=(),
    writes=("threads",),
    measures=(),
    approval="never",
    provides=("ledger.plan.write",),
    label="Write the plan",
    group="Decide",
    verb="write the plan for this conversation",
    order=1,
)
def write_plan(plan: str, thread_id: int | None = None) -> dict[str, Any]:
    text = bullets_as_steps(tidy_steps(str(plan or "").strip()))
    if len(text) < TOO_SHORT_TO_BE_A_PLAN:
        return {
            "ok": False,
            "error": "not_a_plan",
            "detail": (
                f"{len(text)} characters is a sentence, not a plan. Write the "
                "phases out - what each one does, what it needs, what it produces."
            ),
        }
    if thread_id is None:
        return {
            "ok": False,
            "error": "missing_thread_id",
            "detail": "a plan belongs to a conversation, and this call named none",
        }
    phases = _phases_in(text)
    # A PHASE WITH NO STEPS IS A PHASE NOBODY CAN WORK. Max's thread 75,
    # 2026-09-17: eight phases carried `**Tools:**` lines and not one `- [ ]`
    # line; the only steps were six gate sentences under Verification, which
    # is the shape cond_planning already warned about. The run aimed at the
    # gates and parked them one by one. Refused here, with the phases named,
    # so the model fixes the plan while it is still writing it.
    # SAVED, AND TOLD. A plan written as prose is saved by the conductor
    # whatever its shape, so a refusal here would only catch the second
    # draft; and a person reading the plan beside the chat is better served
    # by seeing it with the gap named than by seeing nothing. The reply names
    # the phases, and `app/longrun.py` says the same thing on the first turn
    # of a run, before it aims at anything.
    empty = phases_without_steps(text)
    vague = steps_without_a_tool(text)
    # WHAT CHANGED, READ BEFORE IT CHANGES. Max, 2026-09-14: *"when the agent
    # reads or writes anything and does any change, like adding to the plan, we
    # should have that diff as an expandable feature."* The old text is only
    # available here, one line before it stops existing - the transcript holds
    # messages and tool rows, not the document's history, so nothing downstream
    # could reconstruct this later without replaying every version.
    before = (events.get_thread(int(thread_id)) or {}).get("plan")
    row = events.set_thread_plan(int(thread_id), text)
    if row is None:
        return {"ok": False, "error": "no_such_thread", "thread_id": thread_id}
    change = plandiff.rows_between(before, text)
    events.append(
        "thread.plan_written",
        {
            "thread_id": int(thread_id),
            "phases": phases,
            "characters": len(text),
            "headings": headings_in(text)[:16],
            "steps_open": len(open_steps(text)),
            "phases_without_steps": empty,
            "diff": change,
        },
        thread_id=int(thread_id),
    )
    return {
        "ok": True,
        "saved": True,
        "phases": phases,
        "characters": len(text),
        "steps_open": len(open_steps(text)),
        "phases_without_steps": empty,
        "steps_without_a_tool": vague,
        "next": (
            (
                f"Saved, but {len(empty)} phase(s) have no `- [ ]` step line: "
                + "; ".join(empty[:6])
                + ". A build works steps, not headings: under each phase write "
                "one `- [ ]` line per tool call - the tool and its arguments - "
                "and save again. "
            )
            if empty
            else ""
        )
        + (
            (
                f"Saved. {len(vague)} step(s) name no registered tool and read as "
                "conditions rather than actions: "
                + "; ".join(v[:60] for v in vague[:4])
                + ". Rewrite each as the tool call that does it, then "
            )
            if vague
            else ""
        )
        + (
            "The plan is saved and is what the person sees beside the chat. "
            "Tell them what is in it in two or three sentences, then stop - "
            "the person presses Build."
            if phases
            else "Saved, but with no `## Phase` headings. A plan with no phases "
            "cannot be worked down one phase at a time - revise it into phases."
        ),
    }


@tool(
    name="compile_the_plan",
    #: TERSE, for `write_plan`'s reason: the schema this renders is on every
    #: prompt that offers the tool, and the first draft of this line was 249
    #: characters of it. What the standing BRIEF costs is a different line -
    #: `name - verb`, 69 characters with its newline - and that is what took
    #: the widest focused brief from 2,999 to 3,068 and moved
    #: `FOCUSED_BUDGET`, measured both sides. A core tool costs that whatever
    #: its description says; this keeps it from costing twice.
    description=(
        "Write this conversation's plan from the journey it is on: a phase per "
        "block of the route, a `- [ ]` line per tool call, what is already done "
        "ticked."
    ),
    schema={
        "type": "object",
        "properties": {
            "thread_id": {
                "type": "integer",
                "description": "The conversation. Filled in for you.",
            },
        },
    },
    reads=("threads",),
    writes=("threads",),
    measures=(),
    approval="never",
    provides=("ledger.plan.compile",),
    label="Compile the plan from the journey",
    group="Decide",
    verb="compile this conversation's plan from its journey",
    order=6,
)
def compile_the_plan(thread_id: int | None = None) -> dict[str, Any]:
    """The journey, written out as the plan. `app/journey.py` does the work.

    Max, 2026-09-18: *"journey is an amazing way to empower the plan."* The
    route knows every step's tool and the arguments this thread already
    measured for it; typing that out by hand is what a small model gets wrong
    (thread 75: eight phases, no steps). This is the same document, compiled.
    """
    if thread_id is None:
        return {"ok": False, "error": "missing_thread_id"}
    from app import journey as _journey

    out = _journey.compile_plan(int(thread_id))
    if not out.get("ok"):
        return out
    return {
        **out,
        "next": (
            f"Compiled {out['phases']} phases from the `{out['journey']}` route, "
            f"{out['steps_done']} steps already ticked and {out['steps_open']} "
            "open. The plan is saved and is what the person sees beside the "
            "chat. Tell them what is in it in two or three sentences, then stop."
        ),
    }


@tool(
    name="read_plan",
    description=(
        "Read the plan saved for this conversation, to revise it with write_plan. "
        "`scope: project` reads the project's own plan instead - the one a new "
        "conversation in this folder starts from."
    ),
    schema={
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "enum": ["thread", "project"],
                "description": (
                    "`thread` (the default) is this conversation's plan; "
                    "`project` is the folder's project-plan.md."
                ),
            },
            "thread_id": {
                "type": "integer",
                "description": "The conversation. Filled in for you.",
            },
        },
    },
    reads=("threads",),
    writes=(),
    measures=(),
    approval="never",
    provides=("ledger.plan.read",),
    label="Read the plan",
    group="Decide",
    verb="read the plan saved for this conversation",
    order=2,
)
def read_plan(scope: str = "thread", thread_id: int | None = None) -> dict[str, Any]:
    if thread_id is None:
        return {"ok": False, "error": "missing_thread_id"}
    row = events.get_thread(int(thread_id))
    if row is None:
        return {"ok": False, "error": "no_such_thread", "thread_id": thread_id}
    from app import planfile as _planfile

    # THE PROJECT'S PLAN IS A DIFFERENT DOCUMENT, NOT A DIFFERENT THREAD'S.
    # Max, 2026-09-18: *"trouble sharing a journey and plan within one folder
    # and between sessions."* `thread_id` is overwritten by the registry on
    # every call (wall 4 and the three plans it cost, `registry.call`), so a
    # thread cannot ask for another thread's plan and this does not try to let
    # it: `scope` names a document the FOLDER holds, which every conversation
    # in it may read.
    if str(scope or "thread").lower() == "project":
        found = _planfile.project_plan(row)
        text = str(found.get("plan") or "").strip()
        return {
            "ok": True,
            "scope": "project",
            "has_plan": bool(text),
            "plan": text,
            "path": found.get("path"),
            "phases": _phases_in(text),
            "steps": len(steps_in(text)),
            "next": (
                "This is the plan a new conversation in this folder starts from. "
                "Editing it changes what the NEXT conversation adopts, not this "
                "one - revise this conversation's plan with write_plan."
                if text
                else "This folder has no project plan yet. The first plan written "
                "in it becomes one."
            ),
        }
    row = _planfile.sync(row)
    if row is None:
        return {"ok": False, "error": "no_such_thread", "thread_id": thread_id}
    text = (row.get("plan") or "").strip()
    still_open = open_steps(text)
    return {
        "ok": True,
        "scope": "thread",
        "has_plan": bool(text),
        "plan": text,
        "phases": _phases_in(text),
        "steps": len(steps_in(text)),
        "open_steps": [s["text"] for s in still_open][:20],
        "parked": [{"step": s["text"], "why": s["why"]} for s in steps_in(text) if s["state"] == "parked"],
        "mode": row.get("mode"),
    }


# ---------------------------------------------------------------------------
# The to-do list IS the goal function
# ---------------------------------------------------------------------------
#
# Max, 2026-09-12: *"I can tell my model stops in the middle of the task...
# I want this goal function to be thorough, like this to-do list where it
# creates a to-do list and that's the goal - until every single part of that's
# fixed it doesn't exit and it keeps the long running task."* Cursor's plans
# are the reference: a plan is a document whose steps are `- [ ]` lines, the
# agent works them in order and ticks them, and the loop runs until none are
# open. Here the plan column holds the document, `steps_in` reads the ticks,
# `mark_step_done` writes one, `_plan_note` puts the open ones on every build
# prompt, and the browser's loop (`lib/theBuildKeepsGoing.ts`) keeps going
# while any is open - the four halves of one rule.

#: A step is open `[ ]`, done `[x]`, or PARKED `[!]`. Max, 2026-09-13:
#: *"on any kind of stops or rule gateways, it goes as far as it can without
#: that exception in particular."* A step the run cannot do is parked with
#: its reason written into the line, so the file a person reads says what
#: was skipped and why, and the loop goes on to the next step instead of
#: ending the run. `app/longrun.py` is what parks one.
_STEP = re.compile(r"^(\s*[-*]\s+\[)([ xX!])(\]\s+)(.*)$")
#: The reason written on a parked line. Split off the step text with a
#: plain partition rather than a pattern: the mark is a fixed string and
#: a regular expression for it would be one more thing to get wrong.
PARKED_MARK = " — parked: "


def headings_in(plan: str) -> list[str]:
    """The `## ` headings of the plan, in order, without the marks - the
    phase names a person reads in the transcript row that says the plan is
    ready. `# Title` lines are not phases and are left out."""
    out: list[str] = []
    for line in str(plan or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            out.append(stripped[3:].strip())
    return out


def steps_in(plan: str) -> list[dict[str, Any]]:
    """Every step line of the plan, in order, with its line index and state.

    `state` is `open`, `done` or `parked`; `done` stays a boolean for the
    callers that only ever asked that question. A parked step's `why` is the
    reason written on the line, and `text` is the step without it.
    """
    out = []
    for index, line in enumerate(str(plan or "").splitlines()):
        match = _STEP.match(line)
        if not match:
            continue
        mark = match.group(2).lower()
        state = "done" if mark == "x" else "parked" if mark == "!" else "open"
        text = match.group(4).strip()
        why = ""
        if PARKED_MARK in text:
            text, _, why = text.partition(PARKED_MARK)
            text, why = text.strip(), why.strip()
        out.append({"line": index, "done": mark == "x", "state": state, "text": text, "why": why})
    return out


def open_steps(plan: str) -> list[dict[str, Any]]:
    """The steps still to do - neither ticked nor parked."""
    return [step for step in steps_in(plan) if step["state"] == "open"]


def park_step(thread_id: int, step: str, why: str) -> dict[str, Any] | None:
    """Park one open step with its reason. `None` when no open step matches.

    The line becomes `- [!] <text> — parked: <why>`, which the plan file
    carries and the document draws. Parking is not ticking: the step was not
    done, and the run says so when it finishes.

    CS9: when `checklist_source` is `todo`, parks on `threads.todo` instead.
    """
    row = events.get_thread(int(thread_id))
    if row is None:
        return None
    source = str(row.get("checklist_source") or "plan")
    plan = (row.get("todo") if source == "todo" else row.get("plan")) or ""
    wanted = " ".join(str(step or "").lower().split())
    if not wanted:
        return None
    hits = [s for s in steps_in(plan) if s["state"] == "open" and wanted in s["text"].lower()]
    if len(hits) != 1:
        hits = [s for s in steps_in(plan) if s["state"] == "open" and s["text"].lower() == wanted]
        if len(hits) != 1:
            return None
    found = hits[0]
    lines = plan.splitlines()
    match = _STEP.match(lines[found["line"]])
    reason = " ".join(str(why or "no reason recorded").split())[:220]
    lines[found["line"]] = f"{match.group(1)}!{match.group(3)}{found['text']}{PARKED_MARK}{reason}"
    updated = chr(10).join(lines) + (chr(10) if plan.endswith(chr(10)) else "")
    if source == "todo":
        events.set_thread_todo(int(thread_id), updated)
    else:
        events.set_thread_plan(int(thread_id), updated)
    events.append(
        "thread.step_parked",
        {"thread_id": int(thread_id), "step": found["text"], "why": reason,
         "diff": plandiff.rows_between(plan, updated)},
        project_id=row.get("project_id"),
        thread_id=int(thread_id),
    )
    return {"step": found["text"], "why": reason, "open_steps": [s["text"] for s in open_steps(updated)]}


def unpark_step(thread_id: int, step: str) -> dict[str, Any] | None:
    """Put one parked step back to open. `None` when no parked step matches.

    The line becomes `- [ ] <text>` and the ` — parked: …` reason is dropped —
    same rewrite the GoalBar Unpark button does. CS9: when `checklist_source`
    is `todo`, writes `threads.todo`.
    """
    row = events.get_thread(int(thread_id))
    if row is None:
        return None
    source = str(row.get("checklist_source") or "plan")
    plan = (row.get("todo") if source == "todo" else row.get("plan")) or ""
    wanted = " ".join(str(step or "").lower().split())
    if not wanted:
        return None
    parked = [s for s in steps_in(plan) if s["state"] == "parked"]
    hits = [s for s in parked if wanted in " ".join(s["text"].lower().split())]
    if len(hits) != 1:
        hits = [s for s in parked if " ".join(s["text"].lower().split()) == wanted]
        if len(hits) != 1:
            return None
    found = hits[0]
    lines = plan.splitlines()
    match = _STEP.match(lines[found["line"]])
    if not match:
        return None
    lines[found["line"]] = f"{match.group(1)} {match.group(3)}{found['text']}"
    updated = chr(10).join(lines) + (chr(10) if plan.endswith(chr(10)) else "")
    if source == "todo":
        events.set_thread_todo(int(thread_id), updated)
    else:
        events.set_thread_plan(int(thread_id), updated)
    events.append(
        "thread.step_unparked",
        {
            "thread_id": int(thread_id),
            "step": found["text"],
            "diff": plandiff.rows_between(plan, updated),
        },
        project_id=row.get("project_id"),
        thread_id=int(thread_id),
    )
    return {"step": found["text"], "open_steps": [s["text"] for s in open_steps(updated)]}


def tick_step(thread_id: int, step: str, by: str = "harness") -> dict[str, Any] | None:
    """Tick one open step by its own words. `None` when no open step matches.

    The plain function behind the tool, and the one `subagents.harvest` calls to
    fold a sub-agent's finished work into the parent's plan. Matched the way
    `park_step` matches, so the pair behave the same: the step's words, then an
    exact match if the words hit more than one.
    """
    row = events.get_thread(int(thread_id))
    if row is None:
        return None
    source = str(row.get("checklist_source") or "plan")
    plan = (row.get("todo") if source == "todo" else row.get("plan")) or ""
    wanted = " ".join(str(step or "").lower().split())
    if not wanted:
        return None
    hits = [
        s
        for s in steps_in(plan)
        if s["state"] == "open" and wanted in " ".join(s["text"].lower().split())
    ]
    if len(hits) != 1:
        hits = [
            s
            for s in steps_in(plan)
            if s["state"] == "open" and " ".join(s["text"].lower().split()) == wanted
        ]
        if len(hits) != 1:
            return None
    found = hits[0]
    updated = _tick(plan, found["line"])
    if source == "todo":
        events.set_thread_todo(int(thread_id), updated)
    else:
        events.set_thread_plan(int(thread_id), updated)
    remaining = open_steps(updated)
    events.append(
        "thread.step_done",
        {
            "thread_id": int(thread_id),
            "step": found["text"],
            "by": by,
            "open": len(remaining),
            "done": len(steps_in(updated)) - len(remaining),
        },
        project_id=row.get("project_id"),
        thread_id=int(thread_id),
    )
    return {"step": found["text"], "open_steps": [s["text"] for s in remaining]}


def _tick(plan: str, line_index: int) -> str:
    lines = str(plan or "").splitlines()
    match = _STEP.match(lines[line_index])
    lines[line_index] = f"{match.group(1)}x{match.group(3)}{match.group(4)}"
    return "\n".join(lines) + ("\n" if str(plan or "").endswith("\n") else "")


def tick_for_tool(thread_id: int, tool_name: str) -> dict[str, Any] | None:
    """Tick the one open step that names `tool_name`, after that tool ran.

    MEASURED 2026-09-12: handed the open steps and told to tick each, the
    owner's model did the three lookups the steps named and ticked none.
    A step written as "Read the hardware with inspect_hardware" is done the
    moment inspect_hardware returns ok, and the harness can see that without
    asking. Only when exactly ONE open step names the tool: two would be a
    guess, and a guess is not a tick.

    ONLY WHILE A RUN (OR AUTONOMY) IS WORKING THE PLAN. Max, 2026-09-14: a
    casual build ask that happens to call a tool named in a saved plan must
    not silently tick the checklist - that is the todo skill firing without
    being invoked. `mark_step_done` stays for every mode; this auto-tick is
    the longrun half.
    """
    row = events.get_thread(int(thread_id))
    if row is None or str(row.get("mode") or "") != "build":
        return None
    from app import longrun as _longrun

    row = events.get_thread(int(thread_id)) or {}
    from app import autonomy as _autonomy
    from app import longrun as _longrun

    perm = _autonomy.normalise(str(row.get("permission") or "ask"))
    if perm == "ask" and bool(row.get("autonomous")):
        perm = "write"
    if not (
        _autonomy.autonomous_from_permission(perm) or _longrun.is_running(int(thread_id))
    ):
        return None
    plan = checklist_text(row) or ""
    name = str(tool_name or "").strip().lower()
    # A REGISTERED TOOL'S NAME, not a word. "decide" in a step is English;
    # "inspect_hardware" is a tool that either ran or did not.
    from app.tools.registry import REGISTRY

    if not name or REGISTRY.get(name) is None:
        return None
    pattern = re.compile(r"(?<![a-z0-9_])" + re.escape(name) + r"(?![a-z0-9_])")
    hits = [s for s in open_steps(plan) if pattern.search(s["text"].lower())]
    if len(hits) != 1:
        return None
    hit = hits[0]
    updated = _tick(plan, hit["line"])
    source = str(row.get("checklist_source") or "plan")
    if source == "todo":
        events.set_thread_todo(int(thread_id), updated)
    else:
        events.set_thread_plan(int(thread_id), updated)
    remaining = open_steps(updated)
    total = len(steps_in(updated))
    payload = {
        "thread_id": int(thread_id),
        "step": hit["text"],
        "by": "harness",
        "tool": tool_name,
        "open": len(remaining),
        "done": total - len(remaining),
    }
    events.append("thread.step_done", payload, thread_id=int(thread_id))
    return payload


@tool(
    name="mark_step_done",
    description=(
        "Tick one `- [ ]` step of this conversation's plan as done, by a few of "
        "its words. Call it the moment the step is done, then go on to the next "
        "open step without stopping to summarise. The plan's open steps are on "
        "your prompt."
    ),
    schema={
        "type": "object",
        "properties": {
            "step": {
                "type": "string",
                "description": "A few words from the step's line - enough to match exactly one open step.",
            },
            "thread_id": {"type": "integer", "description": "The conversation. Filled in for you."},
        },
        "required": ["step"],
    },
    reads=("threads",),
    writes=("threads",),
    measures=(),
    approval="never",
    provides=("ledger.plan.step",),
    label="Tick a plan step",
    group="Decide",
    verb="tick one step of the plan as done",
    order=3,
)
def mark_step_done(step: str, thread_id: int | None = None) -> dict[str, Any]:
    if thread_id is None:
        return {"ok": False, "error": "missing_thread_id"}
    row = events.get_thread(int(thread_id))
    if row is None:
        return {"ok": False, "error": "no_such_thread", "thread_id": thread_id}
    plan = row.get("plan") or ""
    steps = steps_in(plan)
    if not steps:
        return {
            "ok": False,
            "error": "no_steps",
            "detail": "The plan has no `- [ ]` step lines to tick. Revise it with write_plan so each phase lists its steps as `- [ ]` lines.",
        }
    words = " ".join(str(step or "").lower().split())
    if not words:
        return {"ok": False, "error": "no_step_named"}
    still_open = [s for s in steps if s["state"] == "open"]
    hits = [s for s in still_open if words in " ".join(s["text"].lower().split())]
    if not hits:
        already = [s for s in steps if s["done"] and words in s["text"].lower()]
        return {
            "ok": False,
            "error": "no_such_open_step",
            "detail": (
                "That step is already ticked." if already else "No open step contains those words."
            ),
            "open_steps": [s["text"] for s in still_open][:20],
        }
    if len(hits) > 1:
        return {
            "ok": False,
            "error": "ambiguous_step",
            "detail": "Those words match more than one open step - use more of the line.",
            "matches": [s["text"] for s in hits][:10],
        }
    hit = hits[0]
    updated = _tick(plan, hit["line"])
    events.set_thread_plan(int(thread_id), updated)
    remaining = [s["text"] for s in open_steps(updated)]
    events.append(
        "thread.step_done",
        {"thread_id": int(thread_id), "step": hit["text"], "open": len(remaining),
         "done": len(steps) - len(remaining),
         "diff": plandiff.rows_between(plan, updated)},
        thread_id=int(thread_id),
    )
    return {
        "ok": True,
        "ticked": hit["text"],
        "open_steps": remaining[:20],
        "done": len(steps) - len(remaining),
        "of": len(steps),
        "next": (
            f"Next open step: {remaining[0]}" if remaining else "Every step is ticked. Say so in one line and stop."
        ),
    }


@tool(
    name="unpark_step",
    description=(
        "Put one parked `- [!]` step of this conversation's checklist back to "
        "`- [ ]` so a run can try it again. Match by a few of its words. The "
        "park reason is dropped from the line."
    ),
    schema={
        "type": "object",
        "properties": {
            "step": {
                "type": "string",
                "description": "A few words from the parked step's line - enough to match exactly one.",
            },
            "thread_id": {"type": "integer", "description": "The conversation. Filled in for you."},
        },
        "required": ["step"],
    },
    reads=("threads",),
    writes=("threads",),
    measures=(),
    approval="never",
    provides=("ledger.plan.step",),
    label="Unpark a plan step",
    group="Decide",
    verb="reopen a parked step",
    order=4,
)
def unpark_step_tool(step: str, thread_id: int | None = None) -> dict[str, Any]:
    if thread_id is None:
        return {"ok": False, "error": "missing_thread_id"}
    row = events.get_thread(int(thread_id))
    if row is None:
        return {"ok": False, "error": "no_such_thread", "thread_id": thread_id}
    text = checklist_text(row)
    steps = steps_in(text)
    parked = [s for s in steps if s["state"] == "parked"]
    if not parked:
        return {
            "ok": False,
            "error": "no_parked_steps",
            "detail": "Nothing is parked on this checklist.",
            "open_steps": [s["text"] for s in open_steps(text)][:20],
        }
    words = " ".join(str(step or "").lower().split())
    if not words:
        return {"ok": False, "error": "no_step_named"}
    hits = [s for s in parked if words in " ".join(s["text"].lower().split())]
    if not hits:
        return {
            "ok": False,
            "error": "no_such_parked_step",
            "detail": "No parked step contains those words.",
            "parked": [{"step": s["text"], "why": s["why"]} for s in parked][:20],
        }
    if len(hits) > 1:
        return {
            "ok": False,
            "error": "ambiguous_step",
            "detail": "Those words match more than one parked step - use more of the line.",
            "matches": [s["text"] for s in hits][:10],
        }
    result = unpark_step(int(thread_id), hits[0]["text"])
    if result is None:
        return {"ok": False, "error": "unpark_failed"}
    return {
        "ok": True,
        "unparked": result["step"],
        "open_steps": result["open_steps"][:20],
        "next": (
            f"Next open step: {result['open_steps'][0]}"
            if result["open_steps"]
            else "No open steps left."
        ),
    }
