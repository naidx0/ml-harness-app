"""Ask-gated goal and secondary todo tools (CS9).

`threads.todo` is a checklist that may exist without mirroring `threads.plan`.
Every write tool refuses unless `goal_invite.is_invited(thread_id)` this turn.
The `intent` pack is never CORE — conductor only offers it when invited.
"""
from __future__ import annotations

from typing import Any

from app import events, goal_invite
from app.tools.registry import tool


def _need_invite(thread_id: int | None) -> dict[str, Any] | None:
    if goal_invite.is_invited(thread_id):
        return None
    # AU5 — permission full is zero-ask: goal/todo edits do not wait for a
    # composer checkbox. The person already opted into Full on the thread.
    if thread_id is not None:
        from app import autonomy as _autonomy

        row = events.get_thread(int(thread_id))
        if row and _autonomy.normalise(str(row.get("permission") or "")) == "full":
            return None
    return goal_invite.refuse()


@tool(
    name="set_goal",
    description=(
        "Set this thread's standing goal in the person's words. "
        "Only when they invited goal/todo edits this turn."
    ),
    schema={
        "type": "object",
        "properties": {
            "goal": {"type": "string", "description": "The goal, verbatim."},
            "thread_id": {
                "type": "integer",
                "description": "Filled in for you.",
            },
        },
        "required": ["goal"],
    },
    approval="never",
    writes=("threads",),
    provides=("intent.goal.write",),
    label="Set the goal",
    group="Decide",
    verb="set this conversation's goal",
)
def set_goal(goal: str, thread_id: int | None = None) -> dict[str, Any]:
    blocked = _need_invite(thread_id)
    if blocked is not None:
        return blocked
    if thread_id is None:
        return {"ok": False, "error": "missing_thread_id"}
    text = (goal or "").strip()
    if not text:
        return {"ok": False, "error": "empty_goal", "detail": "goal must not be empty"}
    row = events.set_thread_goal(thread_id, text, None)
    return {"ok": True, "goal": (row or {}).get("goal")}


@tool(
    name="clear_goal",
    description="Clear this thread's standing goal. Only when invited this turn.",
    schema={
        "type": "object",
        "properties": {
            "thread_id": {"type": "integer", "description": "Filled in for you."},
        },
    },
    approval="never",
    writes=("threads",),
    provides=("intent.goal.write",),
    label="Clear the goal",
    group="Decide",
    verb="clear this conversation's goal",
)
def clear_goal(thread_id: int | None = None) -> dict[str, Any]:
    blocked = _need_invite(thread_id)
    if blocked is not None:
        return blocked
    if thread_id is None:
        return {"ok": False, "error": "missing_thread_id"}
    events.set_thread_goal(thread_id, None, None)
    return {"ok": True, "goal": None}


@tool(
    name="write_todo",
    description=(
        "Write the secondary checklist for this thread as markdown with "
        "`- [ ]` steps. Separate from the diagnosis plan. Only when invited."
    ),
    schema={
        "type": "object",
        "properties": {
            "todo": {
                "type": "string",
                "description": "Markdown checklist (`- [ ]` / `- [x]` lines).",
            },
            "thread_id": {"type": "integer", "description": "Filled in for you."},
        },
        "required": ["todo"],
    },
    approval="never",
    writes=("threads",),
    provides=("intent.todo.write",),
    label="Write the todo list",
    group="Decide",
    verb="write this conversation's todo list",
)
def write_todo(todo: str, thread_id: int | None = None) -> dict[str, Any]:
    blocked = _need_invite(thread_id)
    if blocked is not None:
        return blocked
    if thread_id is None:
        return {"ok": False, "error": "missing_thread_id"}
    text = (todo or "").strip()
    if not text:
        return {"ok": False, "error": "empty_todo"}
    row = events.set_thread_todo(thread_id, text)
    return {"ok": True, "todo": (row or {}).get("todo")}


@tool(
    name="clear_todo",
    description="Clear the secondary checklist. Only when invited this turn.",
    schema={
        "type": "object",
        "properties": {
            "thread_id": {"type": "integer", "description": "Filled in for you."},
        },
    },
    approval="never",
    writes=("threads",),
    provides=("intent.todo.write",),
    label="Clear the todo list",
    group="Decide",
    verb="clear this conversation's todo list",
)
def clear_todo(thread_id: int | None = None) -> dict[str, Any]:
    blocked = _need_invite(thread_id)
    if blocked is not None:
        return blocked
    if thread_id is None:
        return {"ok": False, "error": "missing_thread_id"}
    events.set_thread_todo(thread_id, None)
    return {"ok": True, "todo": None}
