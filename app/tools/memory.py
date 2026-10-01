"""The `remember` tool: Hermes' `memory` tool, one door to both stores.

`action` is add / replace / remove; `target` is `project` (this project's
notes) or `user` (who the person is). Replace and remove name the entry by
a few words from it, never by an id - Hermes' rule, because an id is a
thing the model would have to have read back, and a substring is a thing
it already knows. See `app/memory.py` for what is kept from Hermes and
what is not.

There is no `recall`-style read here on purpose: both blocks are on every
prompt already (`conductor._memory_note`), and a tool to read what the
model is holding would be a tool to spend a round on nothing.
"""

from __future__ import annotations

from typing import Any

from app import events, memory
from app.tools.registry import tool


@tool(
    name="remember",
    #: TERSE ON PURPOSE - see `write_plan`. The guidance on WHAT to remember
    #: is in the prompt note, once, not here on every offer.
    description=(
        "Save, rewrite or drop one durable fact in memory. `target` `project` "
        "for this project's notes, `user` for who the person is. Replace and "
        "remove name the entry by a few words from it. A number needs its "
        "origin word (measured/stated/declared/defaulted)."
    ),
    schema={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "replace", "remove"]},
            "target": {"type": "string", "enum": ["project", "user"]},
            "content": {"type": "string", "description": "The entry, for add and replace."},
            "match": {"type": "string", "description": "A few words of the entry, for replace and remove."},
            "thread_id": {"type": "integer", "description": "Filled in for you."},
        },
        "required": ["action", "target"],
    },
    reads=("memory",),
    writes=("memory",),
    measures=(),
    approval="never",
    provides=("context.memory.write",),
    label="Remember",
    group="Context",
    verb="save a durable fact to memory",
    order=15,
)
def remember(
    action: str,
    target: str,
    content: str | None = None,
    match: str | None = None,
    thread_id: int | None = None,
) -> dict[str, Any]:
    action = str(action or "").strip().lower()
    target = str(target or "").strip().lower()
    if action not in memory.ACTIONS:
        return {"ok": False, "error": "bad_action", "detail": f"action is one of {memory.ACTIONS}"}
    if target not in memory.TARGETS:
        return {"ok": False, "error": "bad_target", "detail": f"target is one of {memory.TARGETS}"}

    project_id = None
    if target == "project":
        thread = events.get_thread(int(thread_id)) if thread_id is not None else None
        project_id = thread.get("project_id") if thread else None
        if project_id is None:
            return {
                "ok": False,
                "error": "no_project",
                "detail": "this conversation belongs to no project, so there is no project memory to write",
            }

    if action == "add":
        result = memory.add(target, content or "", project_id)
    elif action == "replace":
        result = memory.replace(target, match or "", content or "", project_id)
    else:
        result = memory.remove(target, match or "", project_id)

    if result.get("ok"):
        events.append(
            "memory.written",
            {"action": action, "target": target, "project_id": project_id, "used": result.get("used"), "limit": result.get("limit")},
            project_id=project_id,
            thread_id=int(thread_id) if thread_id is not None else None,
        )
    return result
