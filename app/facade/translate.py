"""The engine's event log, re-framed as OpenCode's session events.

The engine already writes everything a transcript needs to one append-only
log (`app/events.py`): a `turn.started`, the reply as `chat.delta` rows, a
`tool.call`/`tool.result` pair per tool, a `stream.end` with the ending. Their
client builds its transcript from a DIFFERENT vocabulary - a step per turn, a
text part opened, filled and closed, a tool part that streams, runs and
settles (`createData` in `@opencode/client`, the `handleEvent` reducer). This
module is the dictionary between the two, and it is the only one: the live
stream, the transcript read (`session.message.list`) and the tests all go
through `Translator`, so what a person sees live and what they see after a
reload cannot disagree.

## The mapping

    engine row                  their events
    thread.created              session.created
    thread.renamed              session.renamed
    thread.deleted              session.deleted
    thread.mode / .permission   session.agent.selected (+ session.permissions)
    message.created (user)      session.inbox.enqueued, session.inbox.delivered
    turn.started                session.execution.started, session.step.started
    chat.delta                  session.text.started (first), session.text.delta
    chat.reasoning              session.reasoning.started (first),
                                session.reasoning.delta; .ended when the reply,
                                a tool or the end of the step follows
    tool.call                   session.text.ended (if open),
                                session.tool.input.started, session.tool.called
    tool.result ok              session.tool.success
      ... tool writes files     + filesystem.changed (location-scoped)
    tool.result refused         session.tool.failed
      ... approval_required     + permission.asked
      ... answering a request   permission.replied
    stream.end                  session.text.ended (if open), session.step.ended,
                                session.execution.succeeded / .interrupted
      ... provider or harness   session.step.failed, session.execution.failed
          failure
    turn.refused (facade)       session.step.failed, session.execution.failed

THE DOCUMENT THAT PLANNED THIS (`docs/PHASE-4-FACADE.md`) GOT TWO ROWS WRONG,
and the log is what settled it. It said the reply arrives as one assistant
`message.created`; the conductor writes no such row - the reply is `chat.delta`
rows, streamed as they are released, so their `session.text.delta` IS sent live
and replay folds the deltas (`events.fold_replay`). And it mapped
`thread.permission` to `permission.asked`; `thread.permission` is the person
moving the ladder, and the thing that asks is a `tool.result` whose error is
`approval_required` - which is also exactly what `app/remote.py` reads as "a
tool is waiting for approval". So that is what becomes `permission.asked`.

## Three rules the reducer on their side depends on

1. **A step is always closed.** Their reducer marks an assistant message
   complete only on `step.ended`/`step.failed`. A turn whose engine died never
   writes `stream.end`, so the next `turn.started` on that thread closes the
   orphan as failed rather than leaving it spinning forever.
2. **A tool that never reports does not hang the transcript.** Tools still open
   when the turn ends are failed with a sentence saying the turn ended first;
   the turn itself still ends the way it ended.
3. **A stop is an interruption, not an error.** `stopped_by_the_person` ends as
   `session.execution.interrupted` with reason `user`, which their transcript
   draws as the "Interrupted" divider rather than an error card.

## Identifiers

Every event id is `evt_<engine row id, 16 digits><index, 2 digits>`: one engine
row can become several of their events, and the index keeps them distinct and
ordered, so `Last-Event-ID` can resume in the middle of a row's expansion. An
assistant message is `msg_<turn.started row id>`, a user message is the id
their client minted (recorded on the `message.created` row as `oc_id`) or
`msg_<row id>` for a message sent through another door.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app import db, events
from app.facade import catalog, sessions, spend

#: Their events that are live-only. Every other type carries a `durable`
#: envelope. From `@opencode/schema` (`Event.ephemeral` in session-event.js,
#: permission.js, server-event.js).
EPHEMERAL = frozenset(
    {
        "server.connected",
        "session.text.delta",
        "session.reasoning.delta",
        "session.tool.input.delta",
        "session.tool.progress",
        "session.usage.updated",
        "permission.asked",
        "permission.replied",
        "filesystem.changed",
    }
)

#: Their location-scoped file event (`@opencode/schema` event manifest:
#: data `{file, event: add | change | unlink}`), sent after a tool that writes
#: files succeeds.
FILESYSTEM_CHANGED = "filesystem.changed"

#: Result keys a file-writing tool names what it wrote under.
_PATH_KEYS = ("path", "file", "output", "output_path", "out_path", "written", "wrote")


def written_file(result: Any, directory: str) -> str:
    """The first path a tool result names inside `directory`, relative, or `""`.

    Read only from the result's top level, under a key that names a path
    (`_PATH_KEYS`, or any key ending in `_path`), and only when it is inside
    the project's folder - a path elsewhere is not a change their tree shows.
    """
    import os

    if not isinstance(result, dict):
        return ""
    root = os.path.normcase(os.path.realpath(directory))
    for key, value in result.items():
        if not isinstance(value, str) or not (key in _PATH_KEYS or key.endswith("_path")):
            continue
        if not os.path.isabs(value):
            continue
        resolved = os.path.realpath(value)
        if os.path.normcase(resolved).startswith(root + os.sep):
            return os.path.relpath(resolved, os.path.realpath(directory)).replace(os.sep, "/")
    return ""


#: The prefix of the engine's own events, passed through unrenamed. Their
#: client yields any event type its reader can parse and their store's reducer
#: ignores a type it has no case for, so an event only this product's panes
#: understand can ride the same stream without a second connection.
HARNESS_PREFIX = "harness."


def is_ephemeral(kind: str) -> bool:
    """Whether an event of this type goes without a `durable` envelope.

    The engine's passed-through events are not durable in THEIR sense - their
    durable envelope promises a slot in one of their aggregates' logs, which an
    event their protocol does not define has none of.
    """
    return kind in EPHEMERAL or kind.startswith(HARNESS_PREFIX)


#: Durable types whose schema version is not 1 (session-event.js).
VERSION_TWO = frozenset({"session.tool.success", "session.tool.failed", "session.deleted"})

#: The ending `app/interrupt.py` records when the person pressed stop.
STOPPED = "stopped_by_the_person"

#: Endings that mean the turn could not do its work, as opposed to a turn that
#: answered - including one whose answer was withheld, which is the harness
#: working rather than failing.
FAILED_ENDINGS = frozenset({"provider_failed", "harness_failed"})

#: Kinds the facade itself writes to the log. They are here, beside the reader,
#: so the writer (`app/facade/turns.py`) and the reader cannot spell them
#: differently.
TURN_REFUSED = "turn.refused"
TURN_CRASHED = "turn.crashed"
#: A request, written by the facade, that this product's panes open one of
#: theirs - `/goal` opens the Plan tab. Sent as `harness.ui.open` with data
#: `{tab, sessionID, threadID}`; `HarnessSessionMount` in `web/` acts on it.
UI_OPEN = "ui.open"

#: How much of one tool result is carried as text. A result is shown to the
#: person in their tool card; a dataset preview can be megabytes, and their SSE
#: reader refuses any single event above 16 MB. Cut, and SAID to be cut.
MAX_RESULT_CHARS = 200_000

_EVENT_ID = re.compile(r"^evt_([0-9]{16})([0-9]{2})$")


def event_id(row_id: int, index: int) -> str:
    return f"evt_{int(row_id):016d}{int(index):02d}"


def parse_event_id(value: str | None) -> tuple[int, int] | None:
    """`(row id, index)` from an id this module minted, or `None`."""
    match = _EVENT_ID.match(str(value or ""))
    return (int(match.group(1)), int(match.group(2))) if match else None


def message_id(row_id: int) -> str:
    return f"msg_{int(row_id):016d}"


def zero_tokens() -> dict[str, Any]:
    return spend.zero()


def render_result(result: Any) -> str:
    """A tool result as the text their tool card shows. Never empty."""
    if isinstance(result, str):
        text = result
    else:
        try:
            text = json.dumps(result, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(result)
    if not text:
        text = "(the tool returned nothing)"
    if len(text) > MAX_RESULT_CHARS:
        text = (
            text[:MAX_RESULT_CHARS]
            + f"\n... cut at {MAX_RESULT_CHARS} of {len(text)} characters; "
            "the whole result is in the engine's transcript."
        )
    return text


#: The engine's own fields on a `tool.result` row that a harness result card
#: reads, carried beside the result under their camel-case names.
_RESULT_FIELDS = {
    "repeat_of": "repeatOf",
    "rerun": "rerun",
    "driven_by": "drivenBy",
    "via": "via",
    "answers": "answers",
    "decision": "decision",
}


#: Refusals where the tool never ran: these stay their "tool failed".
NOT_RAN = frozenset({"approval_required", "not_offered", "no_such_tool", "malformed_call"})

#: The keys every refusal carries. A refusal with anything more is an answer.
_BARE_REFUSAL = frozenset({"ok", "error", "detail"})


def reasoned_refusal(payload: dict[str, Any]) -> bool:
    """A tool that RAN and answered no, with its reasons - shown as a result.

    The harness's tools refuse as data: "no plan, and why", a carve that found
    leakage, a chunking sweep declined with the numbers that declined it. The
    outgoing transcript drew each of those as its own card. Sent as their
    `session.tool.failed`, their renderer shows a generic error card before it
    ever consults the tool-card registry, so the reasons were lost - found when
    the harness cards were ported. A refusal the tool never got to make
    (approval, not offered, malformed) and a bare `{ok, error, detail}` stay
    failures; `metadata.harness.ok` stays false either way, so a card knows it
    is drawing a refusal. What the model reads is unchanged.
    """
    result = payload.get("result")
    if not isinstance(result, dict) or result.get("ok") is not False:
        return False
    if not bool(payload.get("ok", True)):
        return False
    if str(result.get("error") or "") in NOT_RAN:
        return False
    return bool(set(result) - _BARE_REFUSAL)


def harness_metadata(payload: dict[str, Any], call_id: str) -> dict[str, Any]:
    """The structured result, for this product's result cards.

    Their tool card draws `content`, which is text. This product's cards draw
    the engine's result as the engine wrote it - a table of rows, a verdict, a
    plan diff - so the dict rides in their `metadata`, an open record their
    schema allows on every tool event. The same size bound as the text applies,
    and a result over it is said to be over it rather than cut mid-structure.
    """
    result = payload.get("result")
    out: dict[str, Any] = {
        "tool": str(payload.get("name") or "tool"),
        "callID": call_id,
        "ok": bool(payload.get("ok", True))
        and not (isinstance(result, dict) and result.get("ok") is False),
    }
    try:
        encoded = json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        encoded = json.dumps(str(result), ensure_ascii=False)
    if len(encoded) > MAX_RESULT_CHARS:
        out["resultOmitted"] = {"chars": len(encoded), "limit": MAX_RESULT_CHARS}
    else:
        out["result"] = json.loads(encoded)
    for key, name in _RESULT_FIELDS.items():
        if payload.get(key) is not None:
            out[name] = payload[key]
    return out


@dataclass
class _Thread:
    """What the translator must remember about one thread between rows."""

    step: str | None = None
    implicit: bool = False
    agent: str = "build"
    model: dict[str, Any] = field(default_factory=lambda: {"id": "unknown", "providerID": "conn-gone"})
    text_open: bool = False
    text: str = ""
    #: A reasoning part open on the step, and what it holds so far. It shares
    #: `ordinal` with text parts: each is one part of the message, in order.
    reasoning_open: bool = False
    reasoning: str = ""
    ordinal: int = 0
    #: Open tool calls, call id -> tool name, in the order they were called.
    tools: dict[str, str] = field(default_factory=dict)
    last_error: str | None = None
    #: What the open step spent, for `session.step.ended.tokens` (`spend.step`):
    #: the prompt the conductor counted on `turn.context`, and the text and
    #: reasoning the model streamed.
    prompt: int = 0
    said: list[str] = field(default_factory=list)
    thought: list[str] = field(default_factory=list)
    selected: str | None = None
    #: The thread's two settings AS OF THE ROW BEING READ, which on a replay
    #: is not what the thread row says now. Each is moved by its own event.
    mode: str = "build"
    permission: str = "ask"


class Translator:
    """Feed engine rows in id order; get their events back.

    `prime=True` is for a reader that starts in the middle of the log - the
    live stream, which begins at the newest row. The first time it meets a
    thread it replays that thread's rows from its latest `turn.started`
    silently, so a turn already under way when the stream opened arrives with
    its step and text part already open rather than as orphan deltas.
    """

    def __init__(self, *, prime: bool = False) -> None:
        self.prime = prime
        self._threads: dict[int, _Thread] = {}
        self._sids: dict[int, str] = {}

    # -- helpers ---------------------------------------------------------

    def _sid(self, thread_id: int) -> str:
        sid = self._sids.get(int(thread_id))
        if sid is None:
            sid = sessions.session_id(int(thread_id))
            self._sids[int(thread_id)] = sid
        return sid

    def _state(self, thread_id: int, before: int) -> _Thread:
        state = self._threads.get(int(thread_id))
        if state is not None:
            return state
        state = _Thread()
        thread = events.get_thread(int(thread_id))
        if thread is not None:
            state.mode = str(thread.get("mode") or "build")
            # A reader starting at the newest row can believe the row; one
            # replaying from the first cannot, and every thread's ladder starts
            # at the column default, `ask`, until a `thread.permission` moves it.
            state.permission = str(thread.get("permission") or "ask") if self.prime else "ask"
            state.agent = self._agent(state)
        self._threads[int(thread_id)] = state
        if self.prime:
            self._prime(int(thread_id), before)
        return state

    def _prime(self, thread_id: int, before: int) -> None:
        """Replay the running turn, if there is one, without emitting it."""
        rows = [
            row
            for row in events.since(f"thread:{thread_id}", 0, limit=100_000)
            if int(row["id"]) < before
        ]
        start = 0
        for index, row in enumerate(rows):
            if row.get("kind") == "turn.started":
                start = index
        was, self.prime = self.prime, False
        try:
            for row in rows[start:]:
                self.feed(row)
        finally:
            self.prime = was

    def _envelope(
        self,
        row: dict[str, Any],
        out: list[dict[str, Any]],
        kind: str,
        data: dict[str, Any],
        *,
        location: dict[str, Any] | None = None,
    ) -> None:
        index = len(out)
        envelope: dict[str, Any] = {
            "id": event_id(int(row["id"]), index),
            "type": kind,
            "created": sessions.ms(row.get("ts")),
            "data": data,
        }
        if location is not None:
            envelope["location"] = location
        if not is_ephemeral(kind):
            envelope["durable"] = {
                "aggregateID": data.get("sessionID", ""),
                "seq": int(row["id"]) * 100 + index,
                "version": 2 if kind in VERSION_TWO else 1,
            }
        out.append(envelope)

    # -- the parts of a step -----------------------------------------------

    def _open_step(self, row, out, state: _Thread, sid: str, *, implicit: bool) -> None:
        state.step = message_id(int(row["id"]))
        state.implicit = implicit
        state.text_open = False
        state.text = ""
        state.reasoning_open = False
        state.reasoning = ""
        state.ordinal = 0
        state.tools = {}
        state.last_error = None
        state.prompt = 0
        state.said = []
        state.thought = []
        self._envelope(
            row,
            out,
            "session.step.started",
            {
                "sessionID": sid,
                "assistantMessageID": state.step,
                "agent": state.agent,
                "model": dict(state.model),
                "started": sessions.ms(row.get("ts")),
            },
        )

    def _close_reasoning(self, row, out, state: _Thread, sid: str) -> None:
        if not state.reasoning_open or state.step is None:
            return
        self._envelope(
            row,
            out,
            "session.reasoning.ended",
            {
                "sessionID": sid,
                "assistantMessageID": state.step,
                "ordinal": state.ordinal,
                "text": state.reasoning,
            },
        )
        state.reasoning_open = False
        state.reasoning = ""
        state.ordinal += 1

    def _close_text(self, row, out, state: _Thread, sid: str) -> None:
        # A reasoning part is closed by whatever comes after it - the reply's
        # first words, a tool, or the end of the step - so every door that
        # closes text closes it too.
        self._close_reasoning(row, out, state, sid)
        if not state.text_open or state.step is None:
            return
        self._envelope(
            row,
            out,
            "session.text.ended",
            {
                "sessionID": sid,
                "assistantMessageID": state.step,
                "ordinal": state.ordinal,
                "text": state.text,
            },
        )
        state.text_open = False
        state.text = ""
        state.ordinal += 1

    def _fail_open_tools(self, row, out, state: _Thread, sid: str, message: str) -> None:
        for call_id in list(state.tools):
            self._envelope(
                row,
                out,
                "session.tool.failed",
                {
                    "sessionID": sid,
                    "assistantMessageID": state.step,
                    "id": call_id,
                    "error": {"type": "tool.unfinished", "message": message},
                    "executed": False,
                },
            )
        state.tools = {}

    def _end_step(self, row, out, state: _Thread, sid: str, *, ending: str, error: str | None) -> None:
        """Close the step and the execution the way the turn ended."""
        if state.step is None:
            return
        self._close_text(row, out, state, sid)
        self._fail_open_tools(
            row, out, state, sid, "The turn ended before this tool reported a result."
        )
        failed = ending in FAILED_ENDINGS or ending in (TURN_REFUSED, TURN_CRASHED)
        if failed:
            structured = {"type": ending, "message": error or state.last_error or ending}
            self._envelope(
                row,
                out,
                "session.step.failed",
                {"sessionID": sid, "assistantMessageID": state.step, "error": structured},
            )
        else:
            if ending.startswith("answered"):
                finish = "stop"
            elif "round_cap" in ending:
                finish = "length"
            else:
                finish = "unknown"
            self._envelope(
                row,
                out,
                "session.step.ended",
                {
                    "sessionID": sid,
                    "assistantMessageID": state.step,
                    "finish": finish,
                    "rawFinish": ending,
                    # The engine prices nothing (`catalog`: `cost: []`).
                    "cost": 0,
                    "tokens": spend.step(state.prompt, state.said, state.thought),
                },
            )
        implicit = state.implicit
        state.step = None
        state.implicit = False
        state.last_error = None
        if implicit:
            return
        if failed:
            self._envelope(
                row,
                out,
                "session.execution.failed",
                {"sessionID": sid, "error": {"type": ending, "message": error or ending}},
            )
        elif ending == STOPPED:
            self._envelope(
                row, out, "session.execution.interrupted", {"sessionID": sid, "reason": "user"}
            )
        else:
            self._envelope(row, out, "session.execution.succeeded", {"sessionID": sid})

    def _ensure_step(self, row, out, state: _Thread, sid: str) -> None:
        if state.step is None:
            self._open_step(row, out, state, sid, implicit=True)

    def _call(self, row, out, state: _Thread, sid: str, call_id: str, name: str, arguments: Any) -> None:
        self._ensure_step(row, out, state, sid)
        self._close_text(row, out, state, sid)
        state.tools[call_id] = name
        self._envelope(
            row,
            out,
            "session.tool.input.started",
            {"sessionID": sid, "assistantMessageID": state.step, "id": call_id, "name": name},
        )
        self._envelope(
            row,
            out,
            "session.tool.called",
            {
                "sessionID": sid,
                "assistantMessageID": state.step,
                "id": call_id,
                "input": arguments if isinstance(arguments, dict) else {"value": arguments},
                "executed": True,
            },
        )

    # -- the dispatcher ------------------------------------------------------

    def feed(self, row: dict[str, Any]) -> list[dict[str, Any]]:
        """Their events for one engine row, in order. Often none."""
        out: list[dict[str, Any]] = []
        kind = str(row.get("kind") or "")
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}

        if kind == "thread.deleted":
            gone = payload.get("id")
            if gone is not None:
                self._envelope(row, out, "session.deleted", {"sessionID": self._sid(int(gone))})
                self._threads.pop(int(gone), None)
            return out

        thread_id = row.get("thread_id")
        if thread_id is None:
            self._pass_through(row, out, kind, payload, None)
            return out
        thread_id = int(thread_id)
        sid = self._sid(thread_id)
        state = self._state(thread_id, int(row["id"]))
        handler = getattr(self, "_on_" + kind.replace(".", "_"), None)
        if handler is not None:
            handler(row, out, state, sid, payload, thread_id)
        else:
            self._pass_through(row, out, kind, payload, sid)
        return out

    def _pass_through(self, row, out, kind: str, payload: dict[str, Any], sid: str | None) -> None:
        """An engine event their protocol has no word for, as `harness.<kind>`.

        The plan, the context window, runs, sub-agents, the stage and the rest
        are this product's own panes, and they read the engine's own payloads.
        Renaming a payload into a vocabulary nobody else speaks would only add
        a second dictionary to keep true, so the payload travels as written,
        with the ids a pane needs to file it.
        """
        data: dict[str, Any] = {"eventID": int(row["id"]), "payload": payload}
        if sid is not None:
            data["sessionID"] = sid
        if row.get("thread_id") is not None:
            data["threadID"] = int(row["thread_id"])
        if row.get("project_id") is not None:
            data["projectID"] = int(row["project_id"])
        if row.get("run_id") is not None:
            data["runID"] = int(row["run_id"])
        self._envelope(row, out, HARNESS_PREFIX + kind, data)

    # -- one method per engine kind ------------------------------------------

    def _on_thread_created(self, row, out, state, sid, payload, thread_id) -> None:
        thread = events.get_thread(thread_id)
        if thread is None:
            return
        info = sessions.session_info(thread)
        if not self.prime:
            # The session as it was born, not as it is now.
            info["agent"] = self._agent(state)
        self._envelope(
            row,
            out,
            "session.created",
            {
                "sessionID": sid,
                "projectID": info["projectID"],
                "location": dict(info["location"]),
                "slug": f"thread-{thread_id}",
                "title": str(payload.get("title") or thread.get("title") or ""),
                "agent": info["agent"],
                "version": sessions.VERSION,
            },
        )
        state.selected = info["agent"]

    def _on_thread_renamed(self, row, out, state, sid, payload, thread_id) -> None:
        self._envelope(
            row, out, "session.renamed", {"sessionID": sid, "title": str(payload.get("title") or "")}
        )

    @staticmethod
    def _agent(state: _Thread) -> str:
        return sessions.agent_of({"mode": state.mode, "permission": state.permission})

    def _agent_moved(self, row, out, state, sid) -> None:
        agent = self._agent(state)
        state.agent = agent
        if agent == state.selected:
            return
        data: dict[str, Any] = {"sessionID": sid, "agent": agent}
        if state.selected:
            data["previous"] = state.selected
        self._envelope(row, out, "session.agent.selected", data)
        state.selected = agent

    def _on_thread_mode(self, row, out, state, sid, payload, thread_id) -> None:
        state.mode = str(payload.get("mode") or state.mode)
        self._agent_moved(row, out, state, sid)

    def _on_thread_permission(self, row, out, state, sid, payload, thread_id) -> None:
        state.permission = str(payload.get("permission") or state.permission)
        if state.permission == "full":
            # `events.set_thread_permission`: full forces build.
            state.mode = "build"
        self._agent_moved(row, out, state, sid)
        self._envelope(
            row,
            out,
            "session.permissions",
            {"sessionID": sid, "permissions": sessions.ruleset_of(payload.get("permission"))},
        )

    def _on_thread_autonomous(self, row, out, state, sid, payload, thread_id) -> None:
        # The legacy switch mirrors onto the ladder (`events.set_thread_autonomous`).
        state.permission = "write" if payload.get("autonomous") else "ask"
        self._agent_moved(row, out, state, sid)

    def _on_message_created(self, row, out, state, sid, payload, thread_id) -> None:
        if payload.get("role") != "user":
            return
        inbox = str(payload.get("oc_id") or message_id(int(row["id"])))
        self._envelope(
            row,
            out,
            "session.inbox.enqueued",
            {
                "sessionID": sid,
                "inboxID": inbox,
                "item": {
                    "type": "user",
                    "payload": {"text": str(payload.get("content") or "")},
                    "delivery": "steer",
                },
            },
        )
        self._envelope(row, out, "session.inbox.delivered", {"sessionID": sid, "inboxID": inbox})

    def _on_turn_started(self, row, out, state, sid, payload, thread_id) -> None:
        if state.step is not None:
            # Rule 1: the previous turn never wrote its ending.
            self._end_step(
                row,
                out,
                state,
                sid,
                ending="harness_failed",
                error="The engine stopped before this turn ended.",
            )
        state.agent = self._agent(state)
        state.model = catalog.ref_for_turn(payload.get("provider"), payload.get("model"))
        self._envelope(row, out, "session.execution.started", {"sessionID": sid})
        self._open_step(row, out, state, sid, implicit=False)

    def _on_chat_reasoning(self, row, out, state, sid, payload, thread_id) -> None:
        """A thinking model's reasoning, as their reasoning part.

        `session.reasoning.started` / `.delta` / `.ended` in `@opencode/schema`
        (same data shape as the text part's, `ordinal` shared), so their
        transcript draws "thinking" live while the turn runs rather than a
        spinner over nothing.
        """
        text = payload.get("text")
        if not isinstance(text, str) or text == "":
            return
        self._ensure_step(row, out, state, sid)
        if state.text_open:
            self._close_text(row, out, state, sid)
        if not state.reasoning_open:
            state.reasoning_open = True
            state.reasoning = ""
            self._envelope(
                row,
                out,
                "session.reasoning.started",
                {"sessionID": sid, "assistantMessageID": state.step, "ordinal": state.ordinal},
            )
        state.reasoning += text
        state.thought.append(text)
        self._envelope(
            row,
            out,
            "session.reasoning.delta",
            {
                "sessionID": sid,
                "assistantMessageID": state.step,
                "ordinal": state.ordinal,
                "delta": text,
            },
        )

    def _on_chat_delta(self, row, out, state, sid, payload, thread_id) -> None:
        text = payload.get("text")
        if not isinstance(text, str) or text == "":
            return
        self._ensure_step(row, out, state, sid)
        self._close_reasoning(row, out, state, sid)
        if not state.text_open:
            state.text_open = True
            state.text = ""
            self._envelope(
                row,
                out,
                "session.text.started",
                {"sessionID": sid, "assistantMessageID": state.step, "ordinal": state.ordinal},
            )
        state.text += text
        state.said.append(text)
        self._envelope(
            row,
            out,
            "session.text.delta",
            {
                "sessionID": sid,
                "assistantMessageID": state.step,
                "ordinal": state.ordinal,
                "delta": text,
            },
        )

    def _on_turn_context(self, row, out, state, sid, payload, thread_id) -> None:
        """The prompt the conductor counted, kept for the step's `tokens`.

        Still passed through as `harness.turn.context` - the context pane reads
        the whole payload - so this only remembers the total on the way by.
        """
        if state.step is not None:
            state.prompt = spend.prompt_of(payload)
        self._pass_through(row, out, "turn.context", payload, sid)

    def _on_chat_error(self, row, out, state, sid, payload, thread_id) -> None:
        state.last_error = str(payload.get("detail") or "") or state.last_error

    def _on_tool_call(self, row, out, state, sid, payload, thread_id) -> None:
        call_id = str(payload.get("id") or f"call_{int(row['id'])}")
        self._call(
            row, out, state, sid, call_id, str(payload.get("name") or "tool"), payload.get("arguments") or {}
        )

    def _on_tool_result(self, row, out, state, sid, payload, thread_id) -> None:
        name = str(payload.get("name") or "tool")
        result = payload.get("result")
        answers = payload.get("answers")
        decision = payload.get("decision")
        if answers and decision == "reject":
            # A refusal ran nothing, so there is no tool to draw - only the
            # request to take off the approval dock.
            self._envelope(
                row,
                out,
                "permission.replied",
                {"sessionID": sid, "requestID": str(answers), "reply": "reject"},
            )
            return

        call_id = payload.get("id")
        if not call_id or str(call_id) not in state.tools:
            # No id (a remote-page approval), or a result whose call this
            # reader never saw: the newest open call of the same name is it,
            # and failing that the call is drawn here so the result has a card.
            same = [cid for cid, open_name in state.tools.items() if open_name == name]
            if same:
                call_id = same[-1]
            else:
                call_id = str(call_id or f"call_{int(row['id'])}")
                self._call(row, out, state, sid, call_id, name, payload.get("arguments") or {})
        call_id = str(call_id)
        text = render_result(result)
        refused = isinstance(result, dict) and result.get("ok") is False
        ok = bool(payload.get("ok", True)) and not refused
        metadata = {"harness": harness_metadata(payload, call_id)}
        if ok or reasoned_refusal(payload):
            self._envelope(
                row,
                out,
                "session.tool.success",
                {
                    "sessionID": sid,
                    "assistantMessageID": state.step,
                    "id": call_id,
                    "content": [{"type": "text", "text": text}],
                    "metadata": metadata,
                    "executed": True,
                },
            )
            self._filesystem_changed(row, out, thread_id, name, result)
        else:
            error_kind = str((result or {}).get("error") or "tool_failed") if isinstance(result, dict) else "tool_failed"
            detail = str((result or {}).get("detail") or "") if isinstance(result, dict) else ""
            ran = error_kind not in NOT_RAN
            self._envelope(
                row,
                out,
                "session.tool.failed",
                {
                    "sessionID": sid,
                    "assistantMessageID": state.step,
                    "id": call_id,
                    "error": {"type": error_kind, "message": detail or text[:2000]},
                    "content": [{"type": "text", "text": text}],
                    "metadata": metadata,
                    "executed": ran,
                },
            )
            if error_kind == "approval_required":
                arguments = payload.get("arguments")
                request: dict[str, Any] = {
                    "sessionID": sid,
                    "id": f"per_{int(row['id'])}",
                    "action": name,
                    "resources": [name],
                    "source": {"type": "tool", "messageID": str(state.step), "id": call_id},
                }
                if detail:
                    request["message"] = detail
                if isinstance(arguments, dict):
                    request["metadata"] = {"arguments": arguments}
                self._envelope(row, out, "permission.asked", request)
        state.tools.pop(call_id, None)
        if answers:
            self._envelope(
                row,
                out,
                "permission.replied",
                {"sessionID": sid, "requestID": str(answers), "reply": str(decision or "once")},
            )
        if state.implicit and not state.tools:
            self._end_step(row, out, state, sid, ending="answered", error=None)

    def _filesystem_changed(self, row, out, thread_id: int, tool: str, result: Any) -> None:
        """`filesystem.changed` after a tool that writes files succeeded.

        Their review panel re-reads its diff, and their file tree re-lists a
        folder, on this event (`session/review/model.ts`,
        `workspaces/files/watcher.ts`). A tool says it writes files by
        declaring `writes=("filesystem",)` in the registry - declared, not
        guessed from its name. The file is the first path the result names
        inside the project's folder; when it names none the event still goes,
        with an empty `file`, which their review panel reads as "re-read" and
        their tree ignores rather than guessing a folder.
        """
        from app.tools import REGISTRY

        spec = REGISTRY.get(tool)
        if spec is None or "filesystem" not in spec.writes:
            return
        thread = events.get_thread(thread_id)
        project = db.get_project(int(thread["project_id"])) if thread and thread.get("project_id") else None
        if project is None:
            return
        directory = sessions.directory_of(project)
        self._envelope(
            row,
            out,
            FILESYSTEM_CHANGED,
            {"file": written_file(result, directory), "event": "add"},
            location={"directory": directory},
        )

    def _on_ui_open(self, row, out, state, sid, payload, thread_id) -> None:
        """`harness.ui.open`, flat: the pane to open and the session it is for.

        Not the generic pass-through shape (`{eventID, payload, ...}`) because
        this is not an engine event a pane reads the payload of - it is an
        instruction to the interface, and its consumer reads `data.tab`.
        """
        self._envelope(
            row,
            out,
            HARNESS_PREFIX + UI_OPEN,
            {"tab": str(payload.get("tab") or ""), "sessionID": sid, "threadID": int(thread_id)},
        )

    def _on_stream_end(self, row, out, state, sid, payload, thread_id) -> None:
        ending = str(payload.get("ending") or "answered")
        self._end_step(row, out, state, sid, ending=ending, error=state.last_error)

    def _on_turn_refused(self, row, out, state, sid, payload, thread_id) -> None:
        detail = str(payload.get("detail") or "The turn could not start.")
        if state.step is not None:
            self._end_step(row, out, state, sid, ending=TURN_CRASHED, error=detail)
        self._envelope(row, out, "session.execution.started", {"sessionID": sid})
        self._open_step(row, out, state, sid, implicit=False)
        self._end_step(row, out, state, sid, ending=TURN_REFUSED, error=detail)

    def _on_turn_crashed(self, row, out, state, sid, payload, thread_id) -> None:
        detail = str(payload.get("detail") or "The turn stopped with an error.")
        if state.step is None:
            self._envelope(row, out, "session.execution.started", {"sessionID": sid})
            self._open_step(row, out, state, sid, implicit=False)
        self._end_step(row, out, state, sid, ending=TURN_CRASHED, error=detail)


def translate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every event for `rows`, read from the start of whatever they cover."""
    translator = Translator()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.extend(translator.feed(row))
    return out


# ---------------------------------------------------------------------------
# Folding events into their message objects, for the transcript read


def fold(stream: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Their `Session.Message.*` objects from their events, oldest first.

    The same reduction their `handleEvent` performs in the browser, for the
    types this translator emits, so `session.message.list` returns the
    transcript a client that had been listening all along would already hold.
    Every object is built with exactly the keys their schema allows - their
    message schemas forbid additional properties, and a field left `None`
    would be one.
    """
    messages: list[dict[str, Any]] = []
    index: dict[str, int] = {}

    def append(message: dict[str, Any]) -> None:
        index[message["id"]] = len(messages)
        messages.append(message)

    def assistant(mid: str) -> dict[str, Any] | None:
        position = index.get(mid)
        return messages[position] if position is not None else None

    def last_text(message: dict[str, Any]) -> dict[str, Any] | None:
        for part in reversed(message["content"]):
            if part["type"] == "text":
                return part
        return None

    def tool(message: dict[str, Any], call_id: str) -> dict[str, Any] | None:
        for part in reversed(message["content"]):
            if part["type"] == "tool" and part["id"] == call_id:
                return part
        return None

    for event in stream:
        kind = event["type"]
        data = event["data"]
        created = event["created"]
        if kind == "session.inbox.enqueued":
            item = data["item"]
            if item.get("type") == "user" and data["inboxID"] not in index:
                append(
                    {
                        "id": data["inboxID"],
                        "type": "user",
                        "text": item["payload"]["text"],
                        "time": {"created": created},
                    }
                )
        elif kind == "session.step.started":
            append(
                {
                    "id": data["assistantMessageID"],
                    "type": "assistant",
                    "agent": data["agent"],
                    "model": dict(data["model"]),
                    "content": [],
                    "time": {"created": data["started"]},
                }
            )
        elif kind == "session.text.started":
            message = assistant(data["assistantMessageID"])
            if message is not None:
                message["content"].append({"type": "text", "text": ""})
        elif kind in ("session.text.delta", "session.text.ended"):
            message = assistant(data["assistantMessageID"])
            part = last_text(message) if message is not None else None
            if part is not None:
                part["text"] = part["text"] + data["delta"] if kind.endswith("delta") else data["text"]
        elif kind == "session.reasoning.started":
            message = assistant(data["assistantMessageID"])
            if message is not None:
                message["content"].append(
                    {"type": "reasoning", "text": "", "time": {"created": created}}
                )
        elif kind in ("session.reasoning.delta", "session.reasoning.ended"):
            message = assistant(data["assistantMessageID"])
            part = None
            for candidate in reversed(message["content"] if message is not None else []):
                if candidate["type"] == "reasoning":
                    part = candidate
                    break
            if part is not None:
                if kind.endswith("delta"):
                    part["text"] = part["text"] + data["delta"]
                else:
                    part["text"] = data["text"]
                    part["time"]["completed"] = created
        elif kind == "session.tool.input.started":
            message = assistant(data["assistantMessageID"])
            if message is not None:
                message["content"].append(
                    {
                        "type": "tool",
                        "id": data["id"],
                        "name": data["name"],
                        "time": {"created": created},
                        "state": {"status": "streaming", "input": ""},
                    }
                )
        elif kind == "session.tool.called":
            message = assistant(data["assistantMessageID"])
            part = tool(message, data["id"]) if message is not None else None
            if part is not None:
                part["time"]["ran"] = created
                part["executed"] = data["executed"]
                part["state"] = {"status": "running", "input": data["input"], "metadata": {}}
        elif kind in ("session.tool.success", "session.tool.failed"):
            message = assistant(data["assistantMessageID"])
            part = tool(message, data["id"]) if message is not None else None
            if part is not None and part["state"]["status"] in ("streaming", "running"):
                previous = part["state"].get("input")
                given = previous if isinstance(previous, dict) else {}
                if kind == "session.tool.success":
                    state = {"status": "completed", "input": given, "content": list(data["content"])}
                else:
                    state = {"status": "error", "input": given, "error": dict(data["error"])}
                    if data.get("content"):
                        state["content"] = list(data["content"])
                if data.get("metadata") is not None:
                    state["metadata"] = data["metadata"]
                part["state"] = state
                part["executed"] = bool(data["executed"] or part.get("executed"))
                part["time"]["completed"] = created
        elif kind == "session.step.ended":
            message = assistant(data["assistantMessageID"])
            if message is not None:
                message["time"]["completed"] = created
                message["finish"] = data["finish"]
                if "rawFinish" in data:
                    message["rawFinish"] = data["rawFinish"]
                message["cost"] = data["cost"]
                message["tokens"] = data["tokens"]
        elif kind == "session.step.failed":
            message = assistant(data["assistantMessageID"])
            if message is not None:
                message["time"]["completed"] = created
                message["finish"] = "error"
                message["error"] = dict(data["error"])
        elif kind in (
            "session.execution.succeeded",
            "session.execution.failed",
            "session.execution.interrupted",
        ):
            outcome = {
                "session.execution.succeeded": "succeeded",
                "session.execution.failed": "failed",
                "session.execution.interrupted": "interrupted",
            }[kind]
            append(
                {
                    "id": event["id"].replace("evt_", "msg_", 1),
                    "type": "idle",
                    "outcome": outcome,
                    "time": {"created": created},
                }
            )
        elif kind == "session.agent.selected":
            message = {
                "id": event["id"].replace("evt_", "msg_", 1),
                "type": "agent-switched",
                "agent": data["agent"],
                "time": {"created": created},
            }
            if "previous" in data:
                message["previous"] = data["previous"]
            append(message)
    return messages


def transcript(thread_id: int) -> list[dict[str, Any]]:
    """One thread's transcript as their message objects, oldest first.

    Replay is folded first (`events.fold_replay`), so a reply written as three
    thousand deltas is one text part built from one row rather than three
    thousand appends.
    """
    rows = events.fold_replay(events.since(f"thread:{int(thread_id)}", 0, limit=1_000_000))
    return fold(translate(rows))


def pending_approval(thread_id: int) -> dict[str, Any] | None:
    """The approval this thread is waiting on, as their `Permission.Request`.

    THE SAME RULE AS `app/remote.py::pending_approval`: a tool is waiting only
    while the NEWEST tool result on the thread is its `approval_required`. Once
    anything later has settled - the person answered, or the model moved on and
    ran something else - the request is no longer in front of anyone.
    """
    rows = events.since(f"thread:{int(thread_id)}", 0, limit=1_000_000)
    translator = Translator()
    asked: dict[str, Any] | None = None
    # The asking row emits its own `session.tool.failed` BEFORE its
    # `permission.asked`, so a settled tool clears only the requests that
    # were made before it.
    for row in rows:
        for event in translator.feed(row):
            if event["type"] == "permission.asked":
                asked = event["data"]
            elif event["type"] in ("session.tool.success", "session.tool.failed", "permission.replied"):
                asked = None
    return asked
