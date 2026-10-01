"""What a turn spent, in their token record's shape.

Their context ring (`session/timeline/session-context-usage.tsx`) and the
context tab read the LAST assistant message that has `tokens`, add
`input + output + reasoning + cache.read + cache.write`, and divide by the
`limit.context` of the model that message names. Their reducer fills a
message's `tokens` from `session.step.ended`. Zeros there drew a ring at 0% on
every thread, so the step carries the engine's own counts instead:

- `input` - MEASURED at assembly: the `total` of the turn's `turn.context` row,
  which the conductor counts on the prompt it actually sent (system prompt,
  tool schemas, conversation) with `providers.budget`. It is the same figure
  `/api/threads/{id}/usage` and `/context` report. The counter is the engine's
  length-based one (`budget.CHARS_PER_TOKEN`), not a provider tokeniser.
- `output`, `reasoning` - ESTIMATED here, with the same `budget.estimate`, on
  the text the model streamed (`chat.delta`, `chat.reasoning`). Tool-call
  arguments are not counted.
- `cache` - 0: the engine keeps no prompt-cache accounting.

`cost` stays 0 wherever this is used, because the engine prices nothing - the
catalog sends every model with `cost: []`.

`Session.Info.tokens` is the sum of every turn's record, read from the same
rows by `thread`, so the session total and the steps cannot tell two stories.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

from app import db
from app.providers import budget

CONTEXT = "turn.context"
TEXT = "chat.delta"
REASONING = "chat.reasoning"
TURN = "turn.started"


def zero() -> dict[str, Any]:
    return {"input": 0, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}}


def step(prompt: int, said: Iterable[str], thought: Iterable[str]) -> dict[str, Any]:
    """One step's record: the counted prompt and what the model wrote."""
    said, thought = list(said), list(thought)
    record = zero()
    record["input"] = max(0, int(prompt or 0))
    record["output"] = budget.estimate(*said).tokens if any(said) else 0
    record["reasoning"] = budget.estimate(*thought).tokens if any(thought) else 0
    return record


def prompt_of(payload: dict[str, Any]) -> int:
    try:
        return max(0, int(payload.get("total") or 0))
    except (TypeError, ValueError):
        return 0


def thread(thread_id: int) -> dict[str, Any]:
    """Every turn of one thread, summed. One indexed query, three kinds.

    Grouped by `turn.started`, which is where the translator opens each step,
    so the sum is the sum of the `session.step.ended` records a client holds.
    """
    from app import activity

    activity.ensure_index()
    with db.session() as connection:
        rows = connection.execute(
            "SELECT kind, payload_json FROM events WHERE thread_id = ? AND kind IN (?, ?, ?, ?) "
            "ORDER BY id ASC",
            (int(thread_id), TURN, CONTEXT, TEXT, REASONING),
        ).fetchall()
    total = zero()
    turn: list[Any] = [0, [], []]

    def close() -> None:
        record = step(*turn)
        for key in ("input", "output", "reasoning"):
            total[key] += record[key]

    for row in rows:
        kind = row["kind"]
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        if kind == TURN:
            close()
            turn = [0, [], []]
        elif kind == CONTEXT:
            turn[0] = prompt_of(payload)
        elif isinstance(payload.get("text"), str):
            turn[1 if kind == TEXT else 2].append(payload["text"])
    close()
    return total
