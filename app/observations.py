"""ObservationPack and the evidence reducer: what a large tool result costs.

MEASURED 2026-09-18 on the four live score rows: a turn is eight rounds, and
every round re-sends every tool result the turn has produced so far. A
profile, an eval result or a shell log that came back once is on the wire
eight times, whole, and the record is what the model is billed for and what
it has to read past to find the next move. SoL-Pi (arXiv 2609.20519) measured
the same shape at scale and kept two mechanisms out of the search that fixed
it: ObservationPack, where a large result rides in full for two requests and
is then replaced by a stable handle and an excerpt that can be read back
exactly; and an evidence-preserving reducer, where a log is replaced by the
lines that carry evidence and the original is kept.

THIS IS NOT TRUNCATION, and `app/providers/budget.py`'s "refuse rather than
truncate" still holds. Truncation throws the tail away; a pack keeps the whole
result on file - it was already written to `events` before the model saw it -
and hands the model a handle, `obs:<event id>`, that `read_observation` turns
back into the whole thing, or any window of it. What the model loses is the
copy it was not reading; what it keeps is the door.

Three sizes decide what happens, measured in characters of the envelope the
model would be sent:

- under `PACK_OVER_CHARS`: never packed. Small results ride whole all turn.
- over it: ride whole for `KEEP_ROUNDS` more requests, then packed.
- over `REDUCE_OVER_CHARS`: packed from the first request, because a 4B on
  an 8k window cannot hold a 100,000-byte log at all - today that result
  either blew the budget or crowded out the plan.

The reducer is deterministic on purpose. The paper uses a cheaper model to
extract evidence; here the cheaper model would be the same 4B, and a small
model taking the usual answer as the answer (see the memory of the same name)
is exactly the wrong instrument for "which lines matter". Head, tail and
every line that names an error, a failure, a result count or an exit code are
kept verbatim; nothing is paraphrased.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Iterable, Mapping

from app import events

#: A result whose envelope is under this rides whole for the whole turn.
#: MEASURED AND RAISED, 2026-09-21. At 2,000 almost every useful tool result
#: was a pack candidate, and Max's run that night made `read_observation` 14 of
#: 30 real calls - 46%, the top tool in the thread, ahead of every instrument
#: that measures anything. The convenience was not saving a re-run; it WAS the
#: run. 8,000 characters is roughly the largest result this harness produces
#: that a model can still act on in one read, and the two that exceed it and
#: matter - `run_diagnosis`, `what_is_missing` - are in `NEVER_PACKED` anyway.
#: See [[an-affordance-can-cost-more-than-it-saves]]: close the loop your
#: convenience opens, and when it will not close, stop opening it.
PACK_OVER_CHARS = 8_000
#: How many further requests a large result rides whole before it is packed.
#: Two, as the paper measured: the round it came back in is when it is read;
#: the round after is when it is acted on; after that it is history.
KEEP_ROUNDS = 2
#: Over this it is packed from the first request. 12,000 characters is about
#: 3,000 tokens - a third of an 8k window on one tool result.
REDUCE_OVER_CHARS = 12_000
#: The excerpt a pack carries for a result that is not a log.
EXCERPT_CHARS = 700
#: A string field this long inside a result is treated as a log and reduced.
LOG_FIELD_CHARS = 800

HEAD_LINES = 8
TAIL_LINES = 20
FLAGGED_LINES = 30
#: Lines that carry evidence in a build, test or training log. Case-insensitive.
EVIDENCE_LINE = re.compile(
    r"error|fail|exception|traceback|warning|refused|denied|not found|"
    r"passed|\bok\b|exit|loss|accuracy|epoch|step \d|\d+ tests?|"
    r"could not|cannot|missing|timeout|killed",
    re.IGNORECASE,
)
#: Result fields that are logs when they are long.
LOG_FIELDS = ("stdout", "stderr", "text", "content", "log", "output", "body")

HANDLE_PREFIX = "obs:"
#: The kind written when a result is packed, so a transcript can say so.
PACKED_KIND = "observation.packed"
#: The tool that opens a handle. Named here so the conductor and the pack text
#: agree on it, and so the schema can be put on the wire the round a handle
#: first appears.
READER = "read_observation"
#: A RESULT THIS TOOL PRODUCED IS NEVER PACKED, and thread 79 is why. The
#: memory note offered `obs:16347`, the model opened it, the 8,443-character
#: answer was itself a pack candidate, it was packed at the next round, and the
#: pack offered to open it again - which the model did, twice, spending four of
#: nine rounds re-reading one verdict. A door that can be put behind another
#: door is not a door. The reader's answer rides whole for the turn that asked
#: for it, whatever it costs: the model asked for exactly this text and paying
#: twice to hand it over is the loop.
#: `run_diagnosis` and `what_is_missing` JOINED IT, and Max's run of
#: 2026-09-19/20 is why. Those two answer one question - *what should I do
#: next* - and the whole answer is the reply. Packing shortens the answer to a
#: question the model asked THIS ROUND and hands back a receipt for it, so the
#: only way to read the verdict is to spend the next round opening it. Thread
#: 83 and its children: 64 `run_diagnosis`, 17 `what_is_missing`, and 62
#: `read_observation` to open what those had already said - 143 of 263 calls in
#: one night spent re-reading the harness's own state, while the baseline the
#: run existed to measure was never measured at all. A verdict of 6,842
#: characters riding whole is cheaper than the same 6,842 plus a handle plus a
#: 5,655-character re-read, and it is the thing the turn is supposed to act on.
NEVER_PACKED: frozenset[str] = frozenset(
    {"read_observation", "run_diagnosis", "what_is_missing"}
)

#: The key a conversation message carries while it is a candidate for packing.
#: Adapters copy `role`, `content` and `tool_call_id` and nothing else, so it
#: never reaches a provider; `budget.billable` counts the same three.
MARK = "_observation"


def handle_for(event_id: int) -> str:
    return f"{HANDLE_PREFIX}{int(event_id)}"


def event_id_of(handle: Any) -> int | None:
    text = str(handle or "").strip()
    if not text.startswith(HANDLE_PREFIX):
        return None
    try:
        return int(text[len(HANDLE_PREFIX):])
    except ValueError:
        return None


def reduce_text(
    text: str,
    *,
    head: int = HEAD_LINES,
    tail: int = TAIL_LINES,
    flagged: int = FLAGGED_LINES,
) -> dict[str, Any]:
    """The lines of a log that carry evidence, and where they were.

    Head and tail verbatim; between them, up to `flagged` lines matching
    `EVIDENCE_LINE`, each prefixed with its 1-based line number so a window
    can be asked for by number. Nothing is paraphrased.
    """
    lines = str(text or "").splitlines()
    n = len(lines)
    if n <= head + tail:
        return {"lines": n, "chars": len(text or ""), "whole": lines}
    middle = range(head, n - tail)
    hits: list[str] = []
    for i in middle:
        if EVIDENCE_LINE.search(lines[i]):
            hits.append(f"{i + 1}: {lines[i]}")
            if len(hits) >= flagged:
                hits.append(f"... more matching lines; {READER} with from_line shows them")
                break
    return {
        "lines": n,
        "chars": len(text or ""),
        "head": lines[:head],
        "evidence_lines": hits,
        "tail_from_line": n - tail + 1,
        "tail": lines[n - tail:],
    }


def excerpt(result: Any) -> Any:
    """A result with its logs reduced and everything else kept, or a head."""
    if isinstance(result, Mapping):
        out: dict[str, Any] = {}
        for key, value in result.items():
            if isinstance(value, str) and (
                key in LOG_FIELDS or len(value) > LOG_FIELD_CHARS
            ) and len(value) > LOG_FIELD_CHARS:
                out[key] = {"reduced": True, **reduce_text(value)}
            elif isinstance(value, (list, tuple)) and len(json.dumps(value, default=str)) > LOG_FIELD_CHARS:
                out[key] = {
                    "reduced": True,
                    "items": len(value),
                    "first": list(value[:3]),
                }
            elif isinstance(value, Mapping) and len(json.dumps(value, default=str)) > LOG_FIELD_CHARS:
                out[key] = {"reduced": True, "keys": list(value.keys())[:20]}
            else:
                out[key] = value
        return out
    if isinstance(result, str):
        return {"reduced": True, **reduce_text(result)}
    if isinstance(result, (list, tuple)):
        return {"reduced": True, "items": len(result), "first": list(result[:3])}
    return result


def reduced_fields(result: Any, body: Any) -> list[str]:
    """The field names the excerpt actually shortened. Empty when it shortened none."""
    if not isinstance(body, Mapping):
        return []
    out = []
    for key, value in body.items():
        if isinstance(value, Mapping) and value.get("reduced"):
            out.append(str(key))
    return out


def pack_text(
    name: str,
    result: Any,
    handle: str,
    *,
    why: str,
    envelope: Callable[[str, Any], str],
) -> str:
    """What the model is handed in place of the whole result.

    THE HEADER NAMES THIS RESULT'S OWN FIELDS, and thread 79 is why it has to.
    It used to print one worked example, `part="stdout"`, as the way to read a
    window - so the model asked for `stdout` on a verdict that has no such
    field and got `no_such_part` for a round. A worked example is an
    instruction about the result in front of it, and a generic one is an
    instruction about a result that is not there.

    It also says when opening the handle would buy NOTHING. An excerpt that
    shortened no field is the whole result already; inviting a call that can
    only return the same text is what spent three rounds of that thread.
    """
    body = excerpt(result)
    shortened = reduced_fields(result, body)
    # THE HEADER NO LONGER OFFERS A CALL, and the measurement is why. Every
    # wording tried - "open once", "call it only if you need what was
    # shortened", "do not call it" - was still an offer, and a model takes an
    # offer. Thread 92, 2026-09-21: 14 of 30 real calls were the reader.
    #
    # What a model needs here is not a door, it is to know whether the text in
    # front of it is the whole answer. So the header says which fields are
    # short and what to do about it WITHOUT naming a tool: re-run the
    # instrument, which is one call either way and comes back current instead
    # of remembered. `read_observation` stays registered - a model that reasons
    # its way to it is not wrong - but nothing here suggests it.
    if shortened:
        how = (
            f"Shortened here: {', '.join(shortened)}. Everything else is whole. "
            "If you need what was cut, run the tool again rather than working "
            "from the excerpt."
        )
    else:
        how = "Nothing was shortened - every field below is whole."
    head = f"PACKED: {name}'s result is on file as {handle} ({why}). {how}"
    text = envelope(f"tool:{name}", body)
    return head + "\n" + text


def size_of(result: Any) -> int:
    if isinstance(result, str):
        return len(result)
    return len(json.dumps(result, indent=2, default=str))


def mark(message: dict[str, Any], *, event_id: int, name: str, chars: int) -> None:
    """Make a conversation message a candidate for packing later this turn."""
    message[MARK] = {"event_id": int(event_id), "name": name, "chars": chars, "round": None}


def stamp(conversation: Iterable[dict[str, Any]], round_number: int) -> None:
    """Give every unstamped candidate the round it was appended in."""
    for message in conversation:
        info = message.get(MARK)
        if isinstance(info, dict) and info.get("round") is None:
            info["round"] = int(round_number)


def pack_older(
    conversation: Iterable[dict[str, Any]],
    round_now: int,
    *,
    envelope: Callable[[str, Any], str],
    result_of: Callable[[int], Any],
    keep_rounds: int = KEEP_ROUNDS,
) -> list[dict[str, Any]]:
    """Pack every candidate older than `keep_rounds` rounds; say which.

    Called at the top of a round, before the request is built. A result
    appended in round r is sent whole with the requests of rounds r+1 and
    r+2 and packed before the request of round r+3.
    """
    packed: list[dict[str, Any]] = []
    for message in conversation:
        info = message.get(MARK)
        if not isinstance(info, dict) or info.get("packed"):
            continue
        appended = info.get("round")
        if appended is None or round_now - int(appended) <= keep_rounds:
            continue
        handle = handle_for(int(info["event_id"]))
        result = result_of(int(info["event_id"]))
        message["content"] = pack_text(
            str(info["name"]),
            result,
            handle,
            why=f"it rode whole for {keep_rounds} rounds",
            envelope=envelope,
        )
        info["packed"] = True
        packed.append({"handle": handle, "name": info["name"], "chars": info["chars"]})
    return packed


def full(thread_id: int, handle: Any) -> dict[str, Any] | None:
    """The `tool.result` event a handle names, if it is this thread's."""
    event_id = event_id_of(handle)
    if event_id is None:
        return None
    rows = events.since(f"thread:{int(thread_id)}", after=event_id - 1, limit=1)
    for row in rows:
        if int(row.get("id") or 0) == event_id and row.get("kind") == "tool.result":
            return row
    return None


def result_on_file(thread_id: int, event_id: int) -> Any:
    """The `result` of one `tool.result` event of this thread, or `None`."""
    row = full(thread_id, handle_for(event_id))
    if row is None:
        return None
    return (row.get("payload") or {}).get("result")


def any_packed(conversation: Iterable[dict[str, Any]]) -> bool:
    return any(
        isinstance(m.get(MARK), dict) and m[MARK].get("packed") for m in conversation
    )


def has_handles(thread_id: int) -> bool:
    """Has this thread ever held a result large enough to be worth a handle?

    True when a result was packed, or when any earlier result was large enough
    that the memory note names its handle. Bounded scan, newest 2,000 rows -
    the same window `_already_read_note` reads.
    """
    for row in events.since(f"thread:{int(thread_id)}", limit=2000):
        kind = row.get("kind")
        if kind == PACKED_KIND:
            return True
        if kind == "tool.result":
            result = (row.get("payload") or {}).get("result")
            if size_of(result) >= PACK_OVER_CHARS:
                return True
    return False


def handles_in(thread_id: int) -> list[str]:
    """Every handle this thread has been handed, oldest first."""
    out: list[str] = []
    for row in events.since(f"thread:{int(thread_id)}", limit=100_000):
        if row.get("kind") == PACKED_KIND:
            handle = str((row.get("payload") or {}).get("handle") or "")
            if handle:
                out.append(handle)
    return out
