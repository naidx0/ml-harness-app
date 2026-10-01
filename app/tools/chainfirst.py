"""`generate_tool_rows`: training rows built chain first, question last.

ToolGrad (Google Research, 2026) inverted the usual synthetic-data pipeline
for tool use. The usual one starts from a question and searches for the API
calls that answer it, and most searches fail, so every good row costs many
bad ones. ToolGrad builds a chain of calls that provably RAN, then asks the
model what question that chain answers; 99.8% of its chains came out valid,
and 500 of them took a 12B to 83.1 on BFCL.

This is that idea on this harness's own tools. A row here teaches a small
model to answer a question about a project by calling the harness's read-only
tools in the right order with arguments that work. The chain is real: every
call in it was executed here, against this database, and its result is on
file; the question and the answer are derived from what came back.

FOUR ROLES, ONE OF THEM NOT A MODEL. The paper's proposer, executors,
selector and updater are all LLM calls. Here the executors are the registry
and the selector is a rule, for the reason `app/observations.py` gives about
small models as instruments: whether a call ran, returned ok and said
something the chain did not already have is a fact the harness can read off
the result, and a 4B asked to judge it would take the usual answer. The
proposer and the updater are the connected model.

WHAT MAY BE CALLED. Only tools that need no approval, write nothing, measure
nothing and read only this machine. A generator that could train a model to
delete a sandbox by running `delete_sandbox` to see what happens is not a
generator. The set is derived from the registry's own declarations, not
listed by hand, so a tool added next year is in or out by what it declares.

THE ROW. `prompt` is the task, the tools offered and the question; `completion`
is the chain as JSON lines of `{"tool", "arguments"}`; both are what
`recipes/hf-peft-lora` reads when `prompt_field`/`completion_field` are named.
`question`, `answer` and `chain` (with result excerpts) ride beside them so
`judge_rows` and a person can read what the row teaches.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app import build as _build
from app import db, events, observations
from app.tools import datawork, evidence, invent
from app.tools.registry import REGISTRY, tool

DEFAULT_ROWS = 20
MAX_ROWS = 200
DEFAULT_CHAIN = 2
MAX_CHAIN = 4
#: Candidate calls the proposer is asked for per step; the first that runs
#: and says something new is kept.
PROPOSALS = 3
#: Characters of a result an excerpt in the chain, or shown to the proposer,
#: may take. Enough for the keys and the first values; a log is reduced first.
RESULT_EXCERPT_CHARS = 500
ROWS_FILE = "tool_rows.jsonl"
#: Tools that read only this machine and still must not be in a training
#: chain: they read the conversation itself, or hand work to another thread.
NEVER_IN_A_CHAIN = frozenset(
    {
        "read_observation",
        "check_the_sub_agents",
        "delegate_phase",
        "read_plan",
        "recall",
        "map_the_ask",
        "what_is_missing",
        "run_diagnosis",
    }
)

_PROPOSER_SYSTEM = (
    "You are choosing the next tool call in a chain that will become a training "
    "row. The task the rows must teach:\n{task}\n\n"
    "Tools you may call (name: what it does; arguments):\n{tools}\n\n"
    "Reply with JSON lines only, one object per line, at most {proposals} lines: "
    '{{"tool": "<name>", "arguments": {{...}}}}. Choose calls whose result would '
    "extend what the chain already knows; never repeat a call already in the chain."
)
_UPDATER_SYSTEM = (
    "A chain of tool calls was run and these are the real results. Write the "
    "question a person working on this project would have asked that this exact "
    "chain answers, and the answer, using only what the results say. The task "
    "the rows must teach:\n{task}\n\n"
    'Reply with one JSON object only: {{"question": "...", "answer": "..."}}. '
    "The question must not name the tools; the answer must be one to three "
    "sentences of fact from the results."
)


def candidates(only: list[str] | None = None) -> list[Any]:
    """The tools a chain may contain, derived from what each declares."""
    out = []
    for name in REGISTRY.names():
        spec = REGISTRY.get(name)
        if spec is None or name in NEVER_IN_A_CHAIN:
            continue
        if spec.approval != "never" or spec.writes or spec.measures:
            continue
        if spec.wants_instrument or spec.wants_ledger:
            continue
        if set(spec.reads) - _build.LOCAL_READS:
            continue
        if only is not None and name not in only:
            continue
        out.append(spec)
    return out


def _tool_lines(specs: list[Any]) -> str:
    lines = []
    for spec in specs:
        params = [
            p for p in (spec.schema.get("properties") or {}).keys() if p != "thread_id"
        ]
        lines.append(f"- {spec.name}: {spec.description.split('. ')[0][:140]}; arguments: {', '.join(params) or 'none'}")
    return "\n".join(lines)


def _excerpt(result: Any) -> str:
    text = json.dumps(observations.excerpt(result), default=str, ensure_ascii=False)
    return text if len(text) <= RESULT_EXCERPT_CHARS else text[:RESULT_EXCERPT_CHARS] + " ..."


def _run(spec: Any, arguments: dict[str, Any], thread_id: int | None) -> tuple[bool, Any]:
    try:
        result = REGISTRY.call(
            spec.name,
            dict(arguments or {}),
            approved=False,
            actor=evidence.HARNESS,
            thread_id=thread_id,
        )
    except Exception as error:  # noqa: BLE001 - a failed candidate is a fact, not a fault
        return False, {"ok": False, "error": "tool_failed", "detail": f"{type(error).__name__}: {error}"}
    ok = not (isinstance(result, dict) and result.get("ok") is False)
    return ok, result


def _select(
    proposals: list[dict[str, Any]],
    specs_by_name: dict[str, Any],
    chain: list[dict[str, Any]],
    thread_id: int | None,
) -> dict[str, Any] | None:
    """Run the proposals in order; keep the first that ran and said something new.

    The rule, not a model: ran without refusing, and its result is not one
    the chain already holds. Everything tried is reported on the kept step
    so the row says what was rejected and why.
    """
    seen = {json.dumps(step["result"], sort_keys=True, default=str) for step in chain}
    tried: list[dict[str, Any]] = []
    for proposal in proposals[:PROPOSALS]:
        name = str(proposal.get("tool") or "").strip()
        arguments = proposal.get("arguments")
        arguments = dict(arguments) if isinstance(arguments, dict) else {}
        spec = specs_by_name.get(name)
        if spec is None:
            tried.append({"tool": name, "why": "not a tool a chain may call"})
            continue
        if any(s["tool"] == name and s["arguments"] == arguments for s in chain):
            tried.append({"tool": name, "why": "already in the chain"})
            continue
        ok, result = _run(spec, arguments, thread_id)
        if not ok:
            tried.append({"tool": name, "why": "refused: " + str((result or {}).get("error") or "")[:60]})
            continue
        key = json.dumps(result, sort_keys=True, default=str)
        if key in seen:
            tried.append({"tool": name, "why": "said nothing the chain did not have"})
            continue
        return {
            "tool": name,
            "arguments": arguments,
            "result": result,
            "result_excerpt": _excerpt(result),
            "rejected": tried,
        }
    return None


def _prompt_for(task: str, specs: list[Any], question: str) -> str:
    return (
        f"{task}\n\nTools:\n{_tool_lines(specs)}\n\n"
        f"Question: {question}\n"
        'Reply with the tool calls that answer it, one JSON object per line: {"tool": "...", "arguments": {...}}'
    )


@tool(
    name="generate_tool_rows",
    description=(
        "Write training rows for tool use the chain-first way: run a chain of "
        "this harness's read-only tools for real, keep the calls that worked "
        "and said something new, then have the model write the question that "
        "chain answers. Each row is prompt (task, tools, question) and "
        "completion (the calls as JSON), with the real results beside it. "
        "Needs a connected model. Tagged generated; not an eval set."
    ),
    schema={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "What the rows must teach - e.g. answer questions about this project's runs, hardware and data by calling the right tools.",
            },
            "into": {
                "type": "string",
                "description": "A new folder to write tool_rows.jsonl into.",
            },
            "count": {
                "type": "integer",
                "description": f"How many rows. Default {DEFAULT_ROWS}, at most {MAX_ROWS}.",
            },
            "chain_length": {
                "type": "integer",
                "description": f"Calls per chain. Default {DEFAULT_CHAIN}, at most {MAX_CHAIN}.",
            },
            "tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Only draw from these tool names. Default: every read-only, approval-free tool.",
            },
            "seed": {"type": "string", "description": "Varies the proposer; the same seed asks the same way."},
            "thread_id": {"type": "integer", "description": "The conversation. Filled in for you."},
        },
        "required": ["task", "into"],
    },
    reads=("filesystem", "datasets", "providers", "events"),
    writes=("filesystem", "datasets"),
    measures=(),
    approval="always",
    provides=("data.synthetic.chain_first",),
    label="Generate tool rows",
    group="Data",
    verb="write chain-first tool-use rows",
    order=24,
)
def generate_tool_rows(
    task: str,
    into: str,
    count: int = DEFAULT_ROWS,
    chain_length: int = DEFAULT_CHAIN,
    tools: list[str] | None = None,
    seed: str = "",
    thread_id: int | None = None,
) -> dict[str, Any]:
    want = datawork.data.bounded(count, DEFAULT_ROWS, 1, MAX_ROWS)
    steps = datawork.data.bounded(chain_length, DEFAULT_CHAIN, 1, MAX_CHAIN)
    task_text = " ".join(str(task or "").split())
    try:
        if len(task_text) < 12:
            raise datawork._refuse(
                "no_task",
                "Say what the rows must teach - a sentence or two - or the chains are for nothing.",
            )
        only = [str(t) for t in tools] if tools else None
        specs = candidates(only)
        if only:
            unknown = sorted(set(only) - {s.name for s in specs})
            if unknown:
                raise datawork._refuse(
                    "not_chainable",
                    f"{', '.join(unknown)}: not a tool a chain may call. A chain may hold only tools "
                    "that need no approval, write nothing, measure nothing and read only this machine.",
                    chainable=[s.name for s in candidates()],
                )
        if not specs:
            raise datawork._refuse("no_chainable_tools", "No registered tool qualifies for a chain.")
        adapter, key, row = invent._connected()
        directory = datawork._claim(into, Path(db.DB_PATH))
        out_path = directory / ROWS_FILE
        by_name = {s.name: s for s in specs}
        tool_text = _tool_lines(specs)

        seen: set[str] = set()
        written = 0
        attempts = 0
        empty_chains = 0
        duplicates = 0
        unparseable = 0
        requests = 0
        errors: list[str] = []
        chain_lengths: list[int] = []
        with open(out_path, "w", encoding="utf-8") as handle:
            while written < want and attempts < want * 3 + 4:
                attempts += 1
                chain: list[dict[str, Any]] = []
                for _ in range(steps):
                    so_far = (
                        "\n".join(
                            json.dumps({"tool": s["tool"], "arguments": s["arguments"], "result": s["result_excerpt"]}, ensure_ascii=False)
                            for s in chain
                        )
                        or "(empty)"
                    )
                    requests += 1
                    text, error = invent._ask(
                        adapter,
                        key,
                        _PROPOSER_SYSTEM.format(task=task_text, tools=tool_text, proposals=PROPOSALS),
                        f"Seed: {seed}|{attempts}\nThe chain so far:\n{so_far}\n\nPropose the next call(s).",
                    )
                    if error:
                        errors.append(error)
                        break
                    proposals = invent._objects(text)
                    if not proposals:
                        unparseable += 1
                        break
                    kept = _select(proposals, by_name, chain, thread_id)
                    if kept is None:
                        break
                    chain.append(kept)
                if len(errors) >= 3:
                    break
                if not chain:
                    empty_chains += 1
                    continue
                requests += 1
                shown = "\n".join(
                    json.dumps({"tool": s["tool"], "arguments": s["arguments"], "result": s["result_excerpt"]}, ensure_ascii=False)
                    for s in chain
                )
                text, error = invent._ask(
                    adapter, key, _UPDATER_SYSTEM.format(task=task_text), f"The chain and its results:\n{shown}"
                )
                if error:
                    errors.append(error)
                    if len(errors) >= 3:
                        break
                    continue
                objects = invent._objects(text)
                question = str((objects[0].get("question") if objects else "") or "").strip()
                answer = str((objects[0].get("answer") if objects else "") or "").strip()
                if not question or not answer:
                    unparseable += 1
                    continue
                if invent._norm(question) in seen:
                    duplicates += 1
                    continue
                seen.add(invent._norm(question))
                calls = [{"tool": s["tool"], "arguments": s["arguments"]} for s in chain]
                handle.write(
                    json.dumps(
                        {
                            "prompt": _prompt_for(task_text, specs, question),
                            "completion": "\n".join(json.dumps(c, ensure_ascii=False) for c in calls),
                            "question": question,
                            "answer": answer,
                            "chain": [
                                {
                                    "tool": s["tool"],
                                    "arguments": s["arguments"],
                                    "result_excerpt": s["result_excerpt"],
                                    "rejected": s["rejected"],
                                }
                                for s in chain
                            ],
                            "tools_offered": [s.name for s in specs],
                            "chain_length": len(chain),
                            "origin": "chain_first",
                            "generated": True,
                            "synthetic": True,
                            "generator": row["model"],
                            "task": task_text,
                            "group_id": invent._fingerprint(question),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                written += 1
                chain_lengths.append(len(chain))
        manifest = datawork._write_manifest(
            directory,
            {
                "operation": "generate_tool_rows",
                "complete": written >= want,
                "task": task_text,
                "generator": row["model"],
                "tools_offered": [s.name for s in specs],
                "chain_length_asked": steps,
                "rows_written": written,
                "attempts": attempts,
                "empty_chains": empty_chains,
                "duplicates_dropped": duplicates,
                "unparseable_replies": unparseable,
                "requests": requests,
                "errors": errors,
                "wrote": [datawork._written(out_path, written)],
                "method": (
                    "chain first, question last: the model proposed calls, the registry ran "
                    "them, a rule kept the first that ran and said something new, and the "
                    "model wrote the question and answer the chain supports"
                ),
                "does_not_open_g0": (
                    "This wrote a generated file. It did not count one. A generated "
                    "file is not an eval set by construction."
                ),
            },
        )
        events.append(
            "dataset.generated",
            {"into": str(directory), "rows": written, "generator": row["model"], "task": task_text[:200], "method": "chain_first"},
            thread_id=thread_id,
        )
        return {
            "ok": written > 0,
            "summary": (
                f"Wrote {written} chain-first rows with {row['model']}, chains of "
                f"{min(chain_lengths)}-{max(chain_lengths)} calls, for: {task_text[:80]}"
                if written
                else "No chain produced a row - see errors, empty_chains and unparseable_replies."
            ),
            "into": str(directory),
            "rows_path": str(out_path),
            "manifest_path": manifest["path"],
            "rows_written": written,
            "attempts": attempts,
            "empty_chains": empty_chains,
            "duplicates_dropped": duplicates,
            "unparseable_replies": unparseable,
            "requests": requests,
            "errors": errors,
            "tools_offered": [s.name for s in specs],
            "generator": row["model"],
            "wrote": [datawork._written(out_path, written)],
            "measured": [],
            "next": (
                "judge_rows scores them against your rubric; start_training with "
                "prompt_field=prompt and completion_field=completion trains on them."
            ),
        }
    except datawork.Refusal as refusal:
        return dict(refusal.payload)
