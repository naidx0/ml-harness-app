"""The A12 plan object, as the phase markdown `write_plan` stores.

A12 (ml-harness-lab log.md, 2026-09-24): one JSON plan, thinking off, no example to-do in
the prompt. On MiniCPM5 it passed 61 of 66 plans against 42 for the schema shape. This
module is the half that needs no model: it turns that object into `## Phase N - ...`
headings with one `- [ ]` step each, and refuses an object whose to-dos are the prompt's
own placeholder text or say there is nothing to do - the two ways A11 and A12 went wrong.
See docs/plan-mode-v2-plan.md.
"""
from __future__ import annotations

import re
from typing import Any

#: Placeholder text from the plan prompts' own examples. A to-do that starts with one
#: was pasted, not written (A11: 55 of 66 plans).
TEMPLATE_TEXT = (
    "verb-first step",
    "what the result must show before the next step",
    "a tool name from the tool list",
)
#: The plan prompt's own description of `goal` and `done_when`. A plan that carries one
#: copied the instruction instead of stating this ask's goal (slice 3, 2026-09-25: both
#: v2 plans that landed in the journeys had "a number on a named set, a file or a test,
#: and the bar it must clear" as their done_when).
PLACEHOLDER_GOAL = (
    "one sentence: what will exist",
    "the one check that proves the goal",
    "a number on a named set, a file or a test",
)
#: A to-do that says there is nothing to do (A12: 24 of 441).
FILLER = re.compile(
    r"^(none|not|no step|nothing)( is| are)? (needed|required|applicable)\b|^n/?a\b|^none$",
    re.I,
)


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def is_template_text(todo: str) -> bool:
    t = re.sub(r"[<>`*_\[\]]", "", str(todo)).strip().lower()
    return any(t.startswith(x) for x in TEMPLATE_TEXT)


def is_filler(todo: str) -> bool:
    return bool(FILLER.match(re.sub(r"[<>`*_\[\]]", "", str(todo)).strip()))


def is_placeholder_goal(text: str) -> bool:
    t = _text(text).lower()
    return any(x in t for x in PLACEHOLDER_GOAL)


def to_plan_markdown(obj: dict[str, Any]) -> dict[str, Any]:
    """`{"ok": True, "plan": markdown}` for `write_plan`, or `{"ok": False, ...}`."""
    if not isinstance(obj, dict) or obj.get("kind") == "answer":
        return {"ok": False, "error": "not_a_plan", "detail": "the reply is an answer, not a plan"}
    todos = [t for t in (obj.get("todos") or []) if isinstance(t, dict)]
    if not todos:
        return {"ok": False, "error": "no_todos", "detail": "the plan has no to-dos"}
    pasted = [i + 1 for i, t in enumerate(todos) if is_template_text(t.get("do", ""))]
    filler = [i + 1 for i, t in enumerate(todos) if is_filler(t.get("do", ""))]
    if pasted or filler:
        return {
            "ok": False,
            "error": "template_or_filler_todos",
            "pasted": pasted,
            "filler": filler,
            "detail": "to-dos must be this ask's own steps, not the prompt's example text or 'none needed'",
        }
    copied = [f for f in ("goal", "done_when") if is_placeholder_goal(obj.get(f, ""))]
    if copied:
        return {
            "ok": False,
            "error": "template_goal",
            "copied": copied,
            "detail": "goal and done_when must be this ask's own, not the prompt's description of them",
        }
    lines = [f"# {_text(obj.get('goal')) or 'Plan'}", ""]
    if obj.get("done_when"):
        lines += [f"**Done when:** {_text(obj['done_when'])}", ""]
    for i, t in enumerate(todos, 1):
        do, tool = _text(t.get("do")), _text(t.get("tool"))
        lines.append(f"## Phase {i} - {do}")
        step = f"- [ ] {do}" + (f" with {tool}" if tool and tool != "edit" and tool not in do else "")
        lines.append(step)
        if t.get("check"):
            lines.append(f"  Check: {_text(t['check'])}")
        if t.get("approval"):
            lines.append(f"  Approval: {_text(t['approval'])}")
        lines.append("")
    return {"ok": True, "plan": "\n".join(lines).rstrip() + "\n", "todos": len(todos)}
