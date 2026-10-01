"""`read_observation`: the door a packed tool result is opened with.

`app/observations.py` says why a large result stops riding whole; this is the
half that makes that a pack rather than a loss. A handle names one
`tool.result` event of this thread, and this returns it - whole when it fits,
or one field by line window when it does not. It reads nothing but the event
log, so it can be offered on any turn that has ever handed out a handle.
"""
from __future__ import annotations

import json
from typing import Any

from app import observations
from app.tools.registry import tool

#: A whole result over this is returned as its excerpt plus a line count, and
#: the caller is told to ask for a window. The same bound the pack used.
WHOLE_AT_MOST = observations.REDUCE_OVER_CHARS
DEFAULT_LINES = 120
MAX_LINES = 400


@tool(
    name="read_observation",
    description=(
        "A tool result this conversation already holds, in full. A result "
        "that was PACKED carries a handle like obs:123; pass it here to read "
        "the whole result back, or name one field (part, e.g. stdout) and a "
        "line window (from_line, lines) to read part of a long log. Nothing "
        "is re-run: this reads what already came back."
    ),
    schema={
        "type": "object",
        "properties": {
            "handle": {
                "type": "string",
                "description": "The handle the packed result named, e.g. obs:123.",
            },
            "part": {
                "type": "string",
                "description": (
                    "One field of the result to read, e.g. stdout or stderr. "
                    "Leave out for the whole result."
                ),
            },
            "from_line": {
                "type": "integer",
                "description": "First line of the window, 1-based. Default 1.",
            },
            "lines": {
                "type": "integer",
                "description": f"How many lines. Default {DEFAULT_LINES}, at most {MAX_LINES}.",
            },
            "thread_id": {
                "type": "integer",
                "description": "The conversation. Filled in for you.",
            },
        },
        "required": ["handle"],
    },
    reads=("events",),
    writes=(),
    measures=(),
    approval="never",
    provides=("context.observation.read",),
    label="Read a packed result",
    group="Look",
    verb="read a tool result this conversation already holds",
    order=19,
)
def read_observation(
    handle: str,
    part: str | None = None,
    from_line: int | None = None,
    lines: int | None = None,
    thread_id: int | None = None,
) -> dict[str, Any]:
    if thread_id is None:
        return {"ok": False, "error": "missing_thread_id"}
    if observations.event_id_of(handle) is None:
        return {
            "ok": False,
            "error": "not_a_handle",
            "detail": f"{handle!r} is not a handle. One looks like obs:123 and appears in a PACKED result.",
        }
    row = observations.full(int(thread_id), handle)
    if row is None:
        # THE LIST GOES IN THE SENTENCE. It was already in `handles`, one key
        # over, and thread 87 of Max's run of 2026-09-19/20 walked obs:17292,
        # 17293, 17295, 17296, 17297, 17298 - six consecutive integers, one
        # per round, eleven refusals in a single turn - with the real list
        # sitting in the reply each time. A handle looks like an integer, so a
        # model treats it like one unless the refusal says otherwise. What it
        # reads is the sentence.
        held = observations.handles_in(int(thread_id))[-10:]
        return {
            "ok": False,
            "error": "no_such_observation",
            "detail": (
                f"{handle} names no tool result of this conversation. Handles are "
                "event ids and are NOT consecutive - the next number up belongs to "
                "another conversation or to no result at all, so guessing costs a "
                "round and can never land. "
                + (
                    "This conversation holds " + ", ".join(held) + "."
                    if held
                    else "This conversation holds none: nothing here was large "
                    "enough to be packed, so there is nothing to open."
                )
            ),
            "handles": held,
        }
    payload = row.get("payload") or {}
    result = payload.get("result")
    name = str(payload.get("name") or "")
    field = str(part or "").strip()
    if field:
        if not isinstance(result, dict) or field not in result:
            return {
                "ok": False,
                "error": "no_such_part",
                "detail": f"{name}'s result has no field {field!r}.",
                "parts": list(result.keys()) if isinstance(result, dict) else [],
            }
        value = result[field]
        text = value if isinstance(value, str) else json.dumps(value, indent=2, default=str)
        all_lines = text.splitlines()
        start = max(1, int(from_line or 1))
        count = max(1, min(int(lines or DEFAULT_LINES), MAX_LINES))
        window = all_lines[start - 1 : start - 1 + count]
        return {
            "ok": True,
            "handle": str(handle),
            "name": name,
            "part": field,
            "from_line": start,
            "to_line": start - 1 + len(window),
            "of_lines": len(all_lines),
            "text": "\n".join(window),
            "more": start - 1 + len(window) < len(all_lines),
        }
    if observations.size_of(result) > WHOLE_AT_MOST:
        parts = list(result.keys()) if isinstance(result, dict) else []
        return {
            "ok": True,
            "handle": str(handle),
            "name": name,
            "whole": False,
            "detail": (
                f"The whole result is {observations.size_of(result):,} characters; "
                "ask for one part with a line window."
            ),
            "parts": parts,
            "excerpt": observations.excerpt(result),
        }
    return {"ok": True, "handle": str(handle), "name": name, "whole": True, "result": result}
