"""What a person has turned on for a project: sub-agents, and which packs.

Max, 2026-09-14: *"add some UI components which lets you configure the tools -
like how many sub-agents you want to be using, if any at all, often or not
often, and so on, with skills as well."* And, in the same breath about the same
problem: *"make sure the models aren't clouded with too many tools and
guidelines so that they can have free roam in the computer to build, write,
read and do whatever they have to."*

Those are one ask. MEASURED on his database the day he said it: thread 73 sent
the model 26,367 tokens of harness furniture against 3,562 tokens of
conversation - 88% of the prompt was this product talking, of which 12,735 was
tool schemas for 44 tools. A person who can switch a pack off is a person who
can hand their 4B its window back, and the number beside each pack is what
makes that a decision rather than a guess.

## Why this is a table and not a constant

`subagents.AT_MOST_RUNNING` was 2 and `modes.tools_for` offered every pack the
scoper allowed. Both are reasonable defaults and neither is a fact about
anybody's machine: two sub-agents against one 7B is right for his box and wrong
for a workstation, and the data pack is essential on a data thread and dead
weight on a retrieval one.

## Why per project rather than per thread

A thread is a conversation; a project is the work. Someone who has decided
their machine runs one sub-agent at a time has decided it for the project, not
for the chat they happen to have open - and re-deciding it per thread is the
kind of setting nobody maintains. The rows are keyed by project and a thread
reads its project's.

## What is deliberately NOT here

No "how often". He asked for "often or not often" and there is nothing honest
to put behind it: the harness does not choose how often to delegate, a model
does, turn by turn, from the plan in front of it. A dial that pretended to
influence that would be a placebo with a number on it. The cap is real - it is
enforced at the door in `subagents.delegate` - and zero means off, which is the
strongest version of "not often" that can actually be kept.
"""
from __future__ import annotations

import json
from typing import Any

from app import db

#: The most sub-agents one project may have working at once. 0 turns
#: delegation off entirely, which is `if any at all`.
MOST_SUBAGENTS = 4
DEFAULT_SUBAGENTS = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS project_settings (
    project_id INTEGER PRIMARY KEY,
    subagents_max INTEGER NOT NULL DEFAULT 2,
    packs_off TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def ensure_table() -> None:
    with db.session() as connection:
        connection.executescript(_SCHEMA)


def read(project_id: int | None) -> dict[str, Any]:
    """This project's settings, with the defaults filled in.

    A project that has never been configured is not an error and not a null:
    it is the defaults, which is what every project ran on before this module
    existed.
    """
    out = {"project_id": project_id, "subagents_max": DEFAULT_SUBAGENTS, "packs_off": []}
    if project_id is None:
        return out
    ensure_table()
    with db.session() as connection:
        row = connection.execute(
            "SELECT * FROM project_settings WHERE project_id = ?", (int(project_id),)
        ).fetchone()
    if row is None:
        return out
    out["subagents_max"] = max(0, min(MOST_SUBAGENTS, int(row["subagents_max"])))
    try:
        off = json.loads(row["packs_off"])
        out["packs_off"] = sorted({str(name) for name in off}) if isinstance(off, list) else []
    except (TypeError, ValueError):
        #: A column somebody edited by hand. An empty list is the honest
        #: reading of an unreadable one, and it fails OPEN - every pack
        #: offered - because failing closed would silently take a person's
        #: tools away and blame the model for not using them.
        out["packs_off"] = []
    return out


def write(
    project_id: int,
    *,
    subagents_max: int | None = None,
    packs_off: list[str] | None = None,
) -> dict[str, Any]:
    """Change one or both. Absent means unchanged, never means default."""
    ensure_table()
    current = read(project_id)
    wanted_cap = current["subagents_max"] if subagents_max is None else int(subagents_max)
    wanted_cap = max(0, min(MOST_SUBAGENTS, wanted_cap))
    wanted_off = current["packs_off"] if packs_off is None else sorted({str(n) for n in packs_off})
    with db.session() as connection:
        connection.execute(
            "INSERT INTO project_settings(project_id, subagents_max, packs_off, updated_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(project_id) DO UPDATE SET subagents_max = excluded.subagents_max, "
            "packs_off = excluded.packs_off, updated_at = CURRENT_TIMESTAMP",
            (int(project_id), wanted_cap, json.dumps(wanted_off)),
        )
    return read(project_id)


def for_thread(thread_id: int | None) -> dict[str, Any]:
    """The settings a turn in this thread runs under - its project's."""
    if thread_id is None:
        return read(None)
    from app import events

    thread = events.get_thread(int(thread_id)) or {}
    return read(thread.get("project_id"))
