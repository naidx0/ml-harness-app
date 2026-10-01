"""Per-turn side effects — what changed, and safe plan/todo revert (CS5).

At the end of a conductor turn the harness names plan ticks, parked steps,
facts stamped, and files tools reported. Revert restores the plan (or
secondary todo) from the snapshot taken at turn start — never ledger facts.
"""
from __future__ import annotations

from typing import Any

from app import events

KIND = "turn.effects"


def gather(
    thread_id: int,
    *,
    after_id: int,
    plan_before: str | None,
    todo_before: str | None = None,
) -> dict[str, Any]:
    """Summarise side effects of this turn from events after `after_id`."""
    steps_done: list[str] = []
    steps_parked: list[dict[str, str]] = []
    facts: list[dict[str, Any]] = []
    files: list[str] = []
    plan_writes = 0

    for row in events.since(f"thread:{thread_id}", limit=100_000):
        if int(row.get("id") or 0) <= int(after_id):
            continue
        kind = str(row.get("kind") or "")
        payload = row.get("payload") or {}
        if kind == "thread.step_done":
            step = str(payload.get("step") or "").strip()
            if step:
                steps_done.append(step)
            continue
        if kind == "thread.step_parked":
            step = str(payload.get("step") or "").strip()
            if step:
                steps_parked.append(
                    {"step": step, "why": str(payload.get("why") or "")}
                )
            continue
        if kind == "thread.plan_written":
            plan_writes += 1
            continue
        if kind == "tool.result":
            result = payload.get("result")
            if isinstance(result, dict):
                for minted in result.get("measured_facts") or []:
                    if isinstance(minted, dict) and minted.get("fact"):
                        facts.append(
                            {
                                "fact": str(minted.get("fact")),
                                "origin": str(minted.get("origin") or "MEASURED"),
                                "how": str(minted.get("how") or ""),
                                "tool": str(payload.get("name") or ""),
                            }
                        )
                for key in ("path", "wrote", "file", "artifact_path", "output_path"):
                    value = result.get(key)
                    if isinstance(value, str) and value.strip():
                        files.append(value.strip())
                written = result.get("written")
                if isinstance(written, list):
                    for one in written:
                        if isinstance(one, str) and one.strip():
                            files.append(one.strip())

    thread = events.get_thread(int(thread_id)) or {}
    source = str(thread.get("checklist_source") or "plan")
    plan_after = thread.get("plan")
    todo_after = thread.get("todo")
    ticks = bool(steps_done or steps_parked or plan_writes)
    if source == "todo":
        can_revert = ticks and (todo_before or "") != (todo_after or "")
        snapshot = todo_before
    else:
        can_revert = ticks and (plan_before or "") != (plan_after or "")
        snapshot = plan_before

    # Deduplicate files while keeping order.
    seen: set[str] = set()
    unique_files: list[str] = []
    for path in files:
        if path in seen:
            continue
        seen.add(path)
        unique_files.append(path)

    return {
        "thread_id": int(thread_id),
        "steps_done": steps_done,
        "steps_parked": steps_parked,
        "facts": facts,
        "files": unique_files[:24],
        "plan_writes": plan_writes,
        "checklist_source": source,
        "plan_before": plan_before,
        "todo_before": todo_before,
        "can_revert": bool(can_revert and snapshot is not None),
        "empty": not (
            steps_done or steps_parked or facts or unique_files or plan_writes
        ),
    }


def revert(thread_id: int, effects_id: int) -> dict[str, Any]:
    """Restore plan/todo from the snapshot on a `turn.effects` event.

    Facts stamped this turn stay in the ledger — revert is ticks only.
    """
    thread = events.get_thread(int(thread_id))
    if thread is None:
        return {"ok": False, "error": "no_such_thread"}

    found = None
    for row in events.since(f"thread:{thread_id}", limit=100_000):
        if int(row.get("id") or 0) == int(effects_id) and row.get("kind") == KIND:
            found = row
            break
    if found is None:
        return {"ok": False, "error": "no_such_effects"}

    payload = found.get("payload") or {}
    if not payload.get("can_revert"):
        return {
            "ok": False,
            "error": "nothing_to_revert",
            "detail": "This turn had no plan/todo ticks to undo.",
        }

    source = str(payload.get("checklist_source") or "plan")
    if source == "todo":
        before = payload.get("todo_before")
        events.set_thread_todo(int(thread_id), before)
    else:
        before = payload.get("plan_before")
        events.set_thread_plan(int(thread_id), before)

    events.append(
        "turn.effects_reverted",
        {
            "thread_id": int(thread_id),
            "effects_id": int(effects_id),
            "checklist_source": source,
            "restored_steps_open": True,
            # Explicit: ledger facts are not touched.
            "facts_untouched": True,
        },
        project_id=thread.get("project_id"),
        thread_id=int(thread_id),
    )
    return {
        "ok": True,
        "thread_id": int(thread_id),
        "effects_id": int(effects_id),
        "checklist_source": source,
        "facts_untouched": True,
    }
