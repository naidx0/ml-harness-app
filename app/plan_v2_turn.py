"""Slice 2a of docs/plan-mode-v2-plan.md: one constrained plan request, then write_plan.

No conductor wiring yet (that is slice 2b, behind `MLH_PLAN_V2`). The request carries
the A12 system prompt, the tool list, and the A12 JSON schema as `response_format`, and
no tools: a small model writes the whole plan in one reply instead of looping over
tool calls. The reply goes through `plan_v2.to_plan_markdown`, so a pasted or filler
plan is refused before anything is saved.
"""
from __future__ import annotations

import json
from typing import Any

from app import plan_v2

#: `MLH_PLAN_V2=1` turns the one-request plan turn on (slice 2b wires it in).
FLAG = "MLH_PLAN_V2"

GATES = ("eval_set", "baseline", "prompting", "retrieval", "smaller_model")
GATE_VALUES = ("passed", "blocked", "not needed")

#: The A12 system prompt: prototype/plan_v2_json.md with the example to-do object
#: replaced by a field list and rule 7 (plan-kit prompts.v_v2json_desc).
SYSTEM = """## This turn is planning
The person chose Plan. You write the plan; you do not run the work. Build or Full runs it next, one to-do at a time, calling the tool each to-do names, without asking the person anything. So this turn always ends with a whole plan, even when the ask is vague.

Answer with one JSON object and nothing else. The harness turns it into the plan the person sees.

{"kind": "plan",
 "goal": "one sentence: what will exist when the work is done, in the person's words",
 "done_when": "the one check that proves the goal: a number on a named set, a file or a test, and the bar it must clear",
 "known": ["a fact the plan rests on, ending (Measured), (Stated) or (Defaulted); an unmeasured number is 'not measured' plus the tool that measures it"],
 "gates": {"eval_set": "passed|blocked|not needed", "baseline": "...", "prompting": "...", "retrieval": "...", "smaller_model": "..."},
 "decided": ["a choice you made instead of asking (what the model is for, model, split, metric, budget)"],
 "not_doing": "what this plan leaves out",
 "todos": [ ...one object per step, with the fields do, tool, args, check and approval... ],
 "question": "one question about intent, or empty"}

Rules:
1. 4 to 10 todos, in the order they run, one tool call each.
2. Measure before you build. The first todos fill the blocked gates in order: eval set, baseline, prompting, retrieval, smaller model. Training comes after them. If the person asked to train anyway, keep the cheap gate todos first and say in decided what skipping the rest costs.
3. When the facts are empty or the ask is vague, the first todos find out: list_context, recall, profile_dataset, inspect_hardware. Never ask for a path, a count or hardware the harness can read.
4. approval is set on a todo that costs money, runs longer than 10 minutes, deletes something or sends data off this machine.
5. The last todo produces the evidence done_when names.
6. No number that is not in known. A target is written as a target.
7. Each todo's do is YOUR step for THIS ask: it starts with a verb and names what it acts on (for example: Measure the eval set, Split train from eval). tool is one name from the tool list. check says what that tool's result must show. Never copy words from this instruction into a field."""


#: The one repair turn after a refused or unreadable plan.
RETRY = (
    "That reply was refused ({error}). {detail} Answer again with one JSON object and "
    "nothing else: this ask's own goal, done_when and to-dos."
)


def schema(tool_names: list[str]) -> dict[str, Any]:
    """The A12 object, with `todos[].tool` an enum of real tool names plus "edit"."""
    tool = {"type": "string", "enum": sorted(set(tool_names)) + ["edit"]}

    def strs(n: int, mx: int) -> dict[str, Any]:
        return {"type": "array", "maxItems": mx, "items": {"type": "string", "maxLength": n}}

    todo = {
        "type": "object",
        "properties": {
            "do": {"type": "string", "minLength": 8, "maxLength": 160},
            "tool": tool,
            "args": {"type": "object"},
            "check": {"type": "string", "maxLength": 200},
            "approval": {"type": "string", "maxLength": 80},
        },
        "required": ["do", "tool", "args", "check", "approval"],
        "additionalProperties": False,
    }
    props = {
        "kind": {"type": "string", "enum": ["plan"]},
        "goal": {"type": "string", "minLength": 8, "maxLength": 300},
        "done_when": {"type": "string", "minLength": 8, "maxLength": 300},
        "known": strs(200, 8),
        "gates": {
            "type": "object",
            "properties": {g: {"type": "string", "enum": list(GATE_VALUES)} for g in GATES},
            "required": list(GATES),
            "additionalProperties": False,
        },
        "decided": strs(200, 6),
        "not_doing": {"type": "string", "maxLength": 300},
        "todos": {"type": "array", "minItems": 4, "maxItems": 10, "items": todo},
        "question": {"type": "string", "maxLength": 300},
    }
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def messages(ask: str, facts: str, tools: list[tuple[str, str]]) -> list[dict[str, str]]:
    """System = the A12 prompt plus the tool list; user = the ask and what is known."""
    listing = "\n".join(f"- {name}: {(purpose or '').strip()[:110]}" for name, purpose in tools)
    user = (
        f"Mode: Plan\n\nRequest: {ask.strip()}\n\nFacts:\n{facts.strip() or 'none yet'}"
        "\n\nNo tool can be called in this turn."
    )
    return [
        {"role": "system", "content": f"{SYSTEM}\n\n## Tools\n{listing}"},
        {"role": "user", "content": user},
    ]


def plan_once(
    adapter: Any,
    ask: str,
    facts: str,
    tools: list[tuple[str, str]],
    *,
    thread_id: int,
    secret: str | None = None,
) -> dict[str, Any]:
    """One constrained request; the plan it returns saved with `write_plan`.

    Returns `{"ok": True, "plan": ..., "saved": ...}`, or `ok: False` with the reason
    and the raw reply, so a refused plan is on the record. A reply that is not JSON or
    is refused gets one retry that names the fault (H-v2b, slice 3's run 2 fell back on
    `not_json`); a provider error does not. Thinking is the provider's
    own setting (`think_field`); A12 was measured with it off.
    """
    from app.tools import planning

    conversation = messages(ask, facts, tools)
    fmt = schema([name for name, _ in tools])
    out: dict[str, Any] = {}
    for attempt in (1, 2):
        text: list[str] = []
        errors: list[str] = []
        for delta in adapter.stream(conversation, None, secret=secret, response_format=fmt):
            if delta.kind == "text":
                text.append(delta.text)
            elif delta.kind == "error":
                errors.append(delta.detail or "provider error")
        raw = "".join(text).strip()
        if errors and not raw:
            return {"ok": False, "error": "provider_error", "detail": "; ".join(errors), "attempts": attempt}
        try:
            obj = json.loads(raw)
        except ValueError:
            out = {"ok": False, "error": "not_json", "raw": raw[:2000], "attempts": attempt}
        else:
            out = dict(plan_v2.to_plan_markdown(obj), attempts=attempt)
            if out["ok"]:
                saved = planning.write_plan(out["plan"], thread_id=thread_id)
                return {"ok": bool(saved.get("ok")), "plan": out["plan"], "saved": saved,
                        "object": obj, "attempts": attempt}
            out["raw"] = raw[:2000]
        # ONE RETRY, told what was wrong (the prototype's repair call, E11).
        conversation = conversation + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": RETRY.format(error=out["error"], detail=out.get("detail") or "")},
        ]
    return out
