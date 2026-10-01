"""The orchestrator's two moves: hand a phase out, and read what came back.

`app/subagents.py` carries the argument for the whole feature. These are the
door a model reaches it through, and they are deliberately only two:

- `delegate_phase` hands one `## ` phase of this conversation's plan to a
  sub-agent, which works it to the end in the project folder.
- `check_the_sub_agents` says what each one is doing, and folds every finished
  one back into the plan before answering.

There is no third tool for reading a sub-agent's transcript, and that absence is
the design. Max: *"the orchestrator model just waits for the agent to finish and
reads its responses, so it doesn't burn up its own context window."* A tool that
returned the child's conversation would undo the only thing delegation buys. The
child's words are in the child's thread, where a PERSON can read them.

## Why these are safe to hand a small model

Neither one can start work twice: `delegate` refuses a phase whose steps are all
ticked or parked, refuses a second sub-agent on the same phase by the same
argument once the first has ticked them, and refuses anything at all past two
running. And a sub-agent cannot delegate, so a model that discovers the tool
cannot build a tree with it.
"""
from __future__ import annotations

from typing import Any

from app import events, subagents
from app.tools.registry import tool


@tool(
    name="delegate_phase",
    description=(
        "Hand one `## ` phase of this conversation's plan to a sub-agent, which "
        "works its steps to the end in this project folder while you carry on. "
        "Name the phase in a few of its own words. At most two sub-agents run at "
        "once; when both are busy this refuses and says so."
    ),
    schema={
        "type": "object",
        "properties": {
            "phase": {
                "type": "string",
                "description": (
                    "A few words from the `## ` phase heading - enough to match "
                    "exactly one phase of the plan."
                ),
            },
            "thread_id": {
                "type": "integer",
                "description": "The conversation. Filled in for you.",
            },
        },
        "required": ["phase"],
    },
    reads=("threads",),
    writes=("threads",),
    measures=(),
    approval="never",
    provides=("ledger.plan.phase",),
    label="Hand a phase to a sub-agent",
    group="Decide",
    verb="hand one phase of the plan to a sub-agent",
    order=4,
)
def delegate_phase(phase: str, thread_id: int | None = None) -> dict[str, Any]:
    if thread_id is None:
        return {"ok": False, "error": "missing_thread_id"}
    outcome = subagents.delegate(int(thread_id), phase)
    if not outcome.get("ok"):
        return outcome
    return {
        "ok": True,
        "next": (
            "It is working now. Hand out another phase if one is ready and fewer "
            "than two are running, or work an open step yourself. Its result "
            "comes back into the plan on its own."
        ),
        "phase": outcome["phase"],
        "working_on": outcome["steps"],
        "conversation": outcome["child_thread_id"],
        "running": outcome["running"],
        "at_most": outcome["at_most"],
    }


@tool(
    name="check_the_sub_agents",
    description=(
        "What each sub-agent of this conversation is doing, and what the finished "
        "ones did. Their results are folded into the plan for you before this "
        "answers, so what it says is already true of the plan."
    ),
    schema={
        "type": "object",
        "properties": {
            "thread_id": {
                "type": "integer",
                "description": "The conversation. Filled in for you.",
            }
        },
    },
    reads=("threads",),
    writes=("threads",),
    measures=(),
    approval="never",
    provides=("ledger.plan.phase",),
    label="Check the sub-agents",
    group="Read",
    verb="read what the sub-agents are doing",
    order=5,
)
def check_the_sub_agents(thread_id: int | None = None) -> dict[str, Any]:
    if thread_id is None:
        return {"ok": False, "error": "missing_thread_id"}
    if events.get_thread(int(thread_id)) is None:
        return {"ok": False, "error": "no_such_thread", "thread_id": thread_id}
    # `read` harvests too, so this is the same fold either way; taking the
    # summaries here is what lets the answer say what just came back.
    folded = subagents.harvest(int(thread_id))
    state = subagents.read(int(thread_id))
    working = [row for row in state["subagents"] if row["state"] == subagents.RUNNING]
    if not state["subagents"]:
        return {
            "ok": True,
            "next": (
                "No phase has been handed out yet. delegate_phase gives one to a "
                "sub-agent; up to two work at a time."
            ),
            "subagents": [],
            "running": 0,
            "at_most": state["at_most"],
        }
    return {
        "ok": True,
        "next": (
            "Wait for them and work an open step of your own meanwhile."
            if working
            else "Nothing is working. Hand out the next phase, or work the next "
            "open step yourself."
        ),
        "running": len(working),
        "at_most": state["at_most"],
        "still_working": [
            {
                "phase": row["phase"],
                "done": row["done"],
                "of": row["steps"],
                "turns": row["turns"],
            }
            for row in working
        ],
        "just_came_back": [
            {
                "phase": one["phase"],
                "ticked": one["ticked"],
                "parked": one["parked"],
                "never_reached": one["unreached"],
                "ended": one["reason"],
            }
            for one in folded
        ],
        "finished_earlier": [
            {"phase": row["phase"], "done": row["done"], "of": row["steps"]}
            for row in state["subagents"]
            if row["state"] != subagents.RUNNING
            and row["id"] not in {one["id"] for one in folded}
        ],
    }
