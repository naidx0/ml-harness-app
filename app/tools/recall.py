"""The `recall` tool: Hermes' session search, over this harness's conversations.

One tool, three shapes, told apart by the arguments present - see
`app/recall.py` for the design and what it was written from. The tool's
job here is the schema and the scoping: a lookup on a thread searches that
thread's PROJECT by default, and marks the calling conversation in its
results so the model can tell "we said this here" from "a sibling said it".

`in_thread` rather than `thread_id` for the scroll target, on purpose: the
registry fills a declared `thread_id` with the CALLING conversation's, and
overrides whatever the model sent (measured 2026-09-11 - a small model
invents the number). A scroll names some other conversation, so its
argument cannot share that name.
"""

from __future__ import annotations

from typing import Any

from app import events, recall
from app.tools.registry import tool


@tool(
    name="recall",
    #: TERSE ON PURPOSE, like `write_plan`: the first draft put the widest
    #: prompt 12 tokens over `test_the_diagnosis_is_not_optional`'s budget.
    description=(
        "Search earlier conversations in this project before re-asking what "
        "another chat may have settled. `query` finds them; `in_thread` + "
        "`around_message_id` scrolls one; nothing lists recent ones. Numbers "
        "it returns were measured then, not now."
    ),
    schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Words to look for."},
            "in_thread": {"type": "integer", "description": "A conversation to scroll."},
            "around_message_id": {"type": "integer", "description": "The message to centre on."},
            "scope": {
                "type": "string",
                "enum": ["project", "all"],
                "description": "`all` searches every project.",
            },
            "thread_id": {"type": "integer", "description": "Filled in for you."},
        },
    },
    reads=("messages", "threads"),
    writes=(),
    measures=(),
    approval="never",
    provides=("context.recall.search",),
    label="Recall an earlier conversation",
    group="Context",
    verb="search earlier conversations in this project",
    order=14,
)
def recall_tool(
    query: str | None = None,
    in_thread: int | None = None,
    around_message_id: int | None = None,
    scope: str = "project",
    thread_id: int | None = None,
) -> dict[str, Any]:
    limit = None
    project_id = None
    if thread_id is not None:
        thread = events.get_thread(int(thread_id))
        project_id = thread.get("project_id") if thread else None
    scope = "all" if str(scope or "project") == "all" else "project"

    if in_thread is not None and around_message_id is not None:
        return recall.scroll(int(in_thread), int(around_message_id))
    if query and str(query).strip():
        return recall.discover(
            str(query),
            project_id=project_id,
            scope=scope,
            this_thread=thread_id,
            limit=int(limit or recall.DEFAULT_LIMIT),
        )
    return recall.browse(
        project_id=project_id, scope=scope, this_thread=thread_id, limit=int(limit or 10)
    )
