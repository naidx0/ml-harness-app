"""Thread and turn usage — tokens, tool calls, wall time — with provenance.

CS3. Every figure is read from events already on disk (`turn.context`,
`tool.call`, `stream.end`). Nothing is invented here; a thread with no turns
returns empty rollups and says so.
"""
from __future__ import annotations

from typing import Any

from app import contextwindow, events

TURN_STARTED = "turn.started"
TOOL_CALL = "tool.call"


def read(thread_id: int) -> dict[str, Any]:
    """Glanceable usage for one thread, per turn and as a rollup."""
    rows = list(events.since(f"thread:{thread_id}", limit=100_000))
    turns: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def close_current() -> None:
        nonlocal current
        if current is not None:
            turns.append(current)
            current = None

    for row in rows:
        kind = str(row.get("kind") or "")
        payload = row.get("payload") or {}
        if kind == TURN_STARTED:
            close_current()
            current = {
                "started_id": int(row.get("id") or 0),
                "at": row.get("ts") or row.get("created_at") or "",
                "tokens": None,
                "tool_calls": 0,
                "seconds": None,
                "window": None,
                "mode": "",
            }
            continue
        if current is None:
            continue
        if kind == contextwindow.KIND:
            current["tokens"] = int(payload.get("total") or 0)
            current["window"] = payload.get("window")
            current["mode"] = str(payload.get("mode") or "")
            current["context_id"] = int(row.get("id") or 0)
            continue
        if kind == TOOL_CALL:
            current["tool_calls"] = int(current["tool_calls"]) + 1
            continue
        if kind == events.END_KIND:
            if payload.get("seconds") is not None:
                try:
                    current["seconds"] = float(payload.get("seconds"))
                except (TypeError, ValueError):
                    current["seconds"] = None
            close_current()

    close_current()

    ctx = contextwindow.read(thread_id)
    total_seconds = sum(
        float(t["seconds"]) for t in turns if t.get("seconds") is not None
    )
    total_calls = sum(int(t["tool_calls"]) for t in turns)
    latest = turns[-1] if turns else None
    token_turns = [t for t in turns if t.get("tokens") is not None]
    total_tokens = sum(int(t["tokens"]) for t in token_turns) if token_turns else None

    return {
        "thread_id": int(thread_id),
        "turns": turns[-48:],
        "thread": {
            "latest_tokens": latest.get("tokens") if latest else None,
            "total_tokens": total_tokens,
            "total_tool_calls": total_calls,
            "total_seconds": round(total_seconds, 3) if turns else None,
            "window": ctx.get("window"),
            "window_provenance": ctx.get("window_provenance") or "",
            "turn_count": len(turns),
        },
        "provenance": {
            "tokens": "measured",
            "tool_calls": "measured",
            "seconds": "measured",
            "window": str(ctx.get("window_provenance") or "defaulted") or "defaulted",
        },
        "counted_by": {
            "tokens": "app/providers/budget.py via turn.context (latest = last turn; total = sum of turns that reported)",
            "tool_calls": "count of tool.call events between turn.started and stream.end",
            "seconds": "stream.end.seconds (time.monotonic wall clock)",
            "window": "active provider ctx_len",
        },
    }
