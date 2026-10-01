"""One-turn invite for the agent to edit goal/todo (CS9).

Default is refuse. Composer checkbox sets the flag for this turn only.
"""
from __future__ import annotations

from typing import Any

_invited: dict[int, bool] = {}


def set_invited(thread_id: int, invited: bool) -> None:
    if invited:
        _invited[int(thread_id)] = True
    else:
        _invited.pop(int(thread_id), None)


def is_invited(thread_id: int | None) -> bool:
    if thread_id is None:
        return False
    return bool(_invited.get(int(thread_id)))


def clear(thread_id: int | None) -> None:
    if thread_id is None:
        return
    _invited.pop(int(thread_id), None)


def refuse() -> dict[str, Any]:
    return {
        "ok": False,
        "error": "invite_required",
        "detail": (
            "Goal and todo edits need an explicit invite this turn. "
            "Check 'Agent may edit goal/todo this turn' in the composer and send again."
        ),
    }
