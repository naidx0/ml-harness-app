"""What this conversation is spending of the model's context window.

Max, 2026-09-13: *"we need a context window showcase for ML Harness."*

EVERY NUMBER HERE WAS COUNTED ON A REAL PROMPT, not re-derived. The
conductor writes a `turn.context` event at the moment it has the assembled
conversation and the tool schemas in hand - the two things that actually go
on the wire - counted with `providers.budget.billable`/`estimate`, which is
the same counting both adapters do before deciding whether a turn fits. This
module reads those rows back, adds the window the provider reported (with
its provenance) and the compactions this thread has had, and hands the pane
a shape it can draw without doing any arithmetic of its own.

A thread that has not taken a turn has no reading, and says so. There is no
estimate of a prompt that was never built: the point of the pane is that the
figures on it are the figures that were sent.
"""
from __future__ import annotations

from typing import Any

from app import compaction, events
from app.providers import budget as budget_mod
from app.providers import store as provider_store

KIND = "turn.context"


def measure(conversation: list[dict[str, Any]] | None, tools: list[dict[str, Any]] | None) -> dict[str, int]:
    """Tokens for one assembled turn, split the way a person asks about it.

    The system prompt, the tool schemas and the conversation are the three
    things a prompt is made of, and they behave differently: the first two
    are fixed costs this product chose, the third is what the work has
    accumulated. A single total cannot tell you which one to do something
    about.
    """
    messages = list(conversation or [])
    system = [m for m in messages if str(m.get("role") or "") == "system"]
    rest = [m for m in messages if str(m.get("role") or "") != "system"]
    system_tokens = budget_mod.estimate(*budget_mod.billable(system, None)).tokens
    history_tokens = budget_mod.estimate(*budget_mod.billable(rest, None)).tokens
    tool_tokens = budget_mod.estimate(*budget_mod.billable(None, tools)).tokens
    return {
        "system": system_tokens,
        "tools": tool_tokens,
        "history": history_tokens,
        "messages": len(rest),
        "tool_count": len(tools or []),
        "total": system_tokens + tool_tokens + history_tokens,
    }


#: What each named part is called on the pane, and one line saying what it is.
#: The order is the order the pane falls back to when two parts cost the same;
#: it is the order they are decided in, from the product's own choices down to
#: what this conversation has accumulated.
LABELS: dict[str, tuple[str, str]] = {
    "messages": ("Conversation", "every message in this thread, after any compaction"),
    "brief": ("Standing brief", "the verdict so far and the tool registry, on every turn"),
    "instructions": ("Instruction set", "this product's own prompt - the laws this turn's phase loaded"),
    "memory": ("Memory", "what this project knows and who is asking"),
    "plan": ("Plan and steps", "the plan document and the open steps, on every build turn"),
    "workspace": ("Workspace", "the folder this thread reads and writes in"),
    "goal": ("Goal", "what this thread is for, in the person's words"),
    "mode": ("Mode note", "what plan or build mode changes about this turn"),
    "already_read": ("Already read", "files this thread has read, so it does not read them twice"),
}


def parts(
    *,
    conversation: list[dict[str, Any]] | None,
    tools: list[dict[str, Any]] | None,
    instructions: str,
    notes: dict[str, str],
    brief: str,
) -> list[dict[str, Any]]:
    """Every named piece of this prompt, counted as the piece it is.

    Max, 2026-09-13: *"can we show the breakdown behind token and context
    spend... it's an amazing and transparent breakdown."* The conductor hands
    the pieces it BUILT the prompt from - the instruction set, the six notes,
    the standing brief, the tool schemas - so nothing here is a string being
    guessed at after the fact. The tool schemas are grouped by the pack the
    registry puts each tool in, which is the same grouping the Controls
    dialog draws, so a person can see that (say) the data pack costs more
    than the conversation does.
    """
    from app.tools.registry import REGISTRY

    out: list[dict[str, Any]] = []
    messages = [m for m in (conversation or []) if str(m.get("role") or "") != "system"]
    spoken = [m for m in messages if str(m.get("content") or "") != str(brief or "")]
    out.append(
        {
            "key": "messages",
            "tokens": budget_mod.estimate(*budget_mod.billable(spoken, None)).tokens,
            "count": len(spoken),
        }
    )
    if brief:
        out.append({"key": "brief", "tokens": budget_mod.estimate(brief).tokens, "count": 1})
    out.append({"key": "instructions", "tokens": budget_mod.estimate(instructions or "").tokens, "count": 1})
    for key, text in (notes or {}).items():
        if text:
            out.append({"key": key, "tokens": budget_mod.estimate(text).tokens, "count": 1})

    #: Tool schemas by pack. A tool the registry does not know is counted
    #: under its own name rather than dropped - the wire carried it either way.
    by_pack: dict[str, list[dict[str, Any]]] = {}
    for schema in tools or []:
        name = str(((schema or {}).get("function") or {}).get("name") or "")
        pack = "Tools"
        try:
            spec = REGISTRY.get(name)
            pack = str(getattr(getattr(spec, "control", None), "group", "") or "Tools")
        except Exception:  # noqa: BLE001 - an unknown tool is still on the wire
            pack = "Tools"
        by_pack.setdefault(pack, []).append(schema)
    for pack, schemas in by_pack.items():
        out.append(
            {
                "key": f"tools:{pack}",
                "label": f"{pack} tools",
                "why": f"{len(schemas)} tool schemas, as JSON on the wire",
                "tokens": budget_mod.estimate(*budget_mod.billable(None, schemas)).tokens,
                "count": len(schemas),
            }
        )

    for row in out:
        label, why = LABELS.get(str(row["key"]), ("", ""))
        row.setdefault("label", label or str(row["key"]))
        row.setdefault("why", why)
    return sorted(out, key=lambda row: int(row["tokens"]), reverse=True)


def read(thread_id: int) -> dict[str, Any]:
    """The pane's whole subject: the window, the last few turns, compactions."""
    rows = [
        row
        for row in events.since(f"thread:{thread_id}", limit=100_000)
        if row.get("kind") in (KIND, compaction.KIND)
    ]
    turns = [
        {
            "event_id": int(row.get("id") or 0),
            "at": row.get("ts") or row.get("created_at") or "",
            **{
                key: int((row.get("payload") or {}).get(key) or 0)
                for key in ("system", "tools", "history", "total", "messages", "tool_count")
            },
            "window": (row.get("payload") or {}).get("window"),
            "mode": (row.get("payload") or {}).get("mode") or "",
            "parts": (row.get("payload") or {}).get("parts") or [],
            #: WHICH TOOLS THOSE SCHEMAS WERE, and which were held back. The
            #: `tools` figure above says what they cost; `app/tools/blocks.py`
            #: decided WHICH, one reason per tool, and a pane that showed the
            #: cost without the choice would be showing a number nobody can act
            #: on. `{}` for a turn taken before that record existed, which reads
            #: as "this turn did not narrow" and is what it was.
            "schemas_on_wire": (row.get("payload") or {}).get("schemas_on_wire") or {},
        }
        for row in rows
        if row.get("kind") == KIND
    ]
    compactions = [
        {
            "event_id": int(row.get("id") or 0),
            "at": row.get("ts") or row.get("created_at") or "",
            "messages_summarised": (row.get("payload") or {}).get("messages_summarised"),
            "tokens_before": (row.get("payload") or {}).get("tokens_before"),
            "tokens_after": (row.get("payload") or {}).get("tokens_after"),
        }
        for row in rows
        if row.get("kind") == compaction.KIND
    ]

    active = provider_store.active()
    window = None
    provenance = ""
    if active:
        window = active.get("ctx_len")
        provenance = str(active.get("ctx_len_provenance") or "")
    latest = turns[-1] if turns else None
    if latest and not window:
        window = latest.get("window")

    headroom = None
    if latest and window:
        headroom = max(0, int(window) - int(latest["total"]))

    return {
        "thread_id": int(thread_id),
        "model": (active or {}).get("model") or "",
        "window": int(window) if window else None,
        "window_provenance": provenance,
        "latest": latest,
        "headroom": headroom,
        "share": (round(latest["total"] / int(window), 4) if latest and window else None),
        "turns": turns[-24:],
        "compactions": compactions[-8:],
        "compaction_at": compaction.transcript_budget(int(window) if window else None),
        "counted_by": "app/providers/budget.py, on the prompt as it was sent",
    }
