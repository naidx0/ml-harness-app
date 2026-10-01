"""One adapter for OpenAI, OpenRouter, vLLM, LM Studio and llama.cpp.

They all speak the same `/chat/completions` shape with the same `data: ` SSE
envelope, so they are one code path driven by a base URL. That is the entire
reason this adapter is preferred over a per-vendor one.

## Where the risk actually is

Not in the HTTP. In the parsing. A streamed tool call arrives as fragments -
the id in one chunk, the function name in another, the arguments split across
however many the server felt like - keyed by an `index` that identifies which
of several parallel calls a fragment belongs to. Reassembling that wrong is
silent: you get a call with half its arguments, which is a tool that runs on
partial input. So the accumulator is explicit, keyed by index, and the call is
only emitted once the stream is over and its arguments parse as JSON.

**Arguments that do not parse are dropped with an error delta, never guessed.**
A half-parsed argument object is exactly the "diagnosis computed from defaults"
failure this product exists to prevent.

## The context window, where the endpoint will say

`/models` is the only place these servers volunteer it, and they disagree about
the field name: OpenRouter says `context_length`, vLLM says `max_model_len`, LM
Studio says `max_context_length`, and OpenAI says nothing at all. All four are
handled the same way - read what is there, and where nothing is there, report
an unknown window rather than a comfortable default. See
`app/providers/budget.py`.

Unlike Ollama, none of these endpoints takes a per-request window, so the
harness cannot raise it; and unlike Ollama, most of them answer an oversized
prompt with an HTTP 400 that names the limit rather than silently dropping the
end of it. That 400 already reaches the user through `_http_detail`. The check
here exists for the ones that do not - llama.cpp's server shifts context
instead of erroring - and to spend nothing on a request we already know cannot
arrive whole.

## `opener`

Every network call goes through an injectable opener defaulting to
`urllib.request.urlopen`. Tests need no network and no running model server,
and the parameter is not optional-in-name-only - the fake is how the suite
covers the malformed-chunk paths a live server will not produce on demand.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Iterable, Iterator

from app import interrupt as _interrupt
from app.providers import Caps, Delta, TextCalls, ToolCall, classify, offered_names
from app.providers import budget as budget_mod


#: What the four endpoints call the same number. Read in order; the first one
#: present wins. Nothing is computed from a model id - "32k" in a name is a
#: marketing string, not a measurement.
CONTEXT_FIELDS = (
    "context_length",
    "max_model_len",
    "max_context_length",
    "context_window",
    "loaded_context_length",
)


#: How long we wait on a streaming response. Generous, because a local model on
#: a small card is slow, and a bounded wait is still a bound.
STREAM_TIMEOUT_SECONDS = 300

#: The probe is a different question and gets a shorter leash.
PROBE_TIMEOUT_SECONDS = 60

#: The tool the capability probe offers. Trivial on purpose: a model that will
#: not call this one will not call ours either.
PROBE_TOOL = {
    "type": "function",
    "function": {
        "name": "report_ok",
        "description": "Report that you can call a tool.",
        "parameters": {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
        },
    },
}


class OpenAICompatibleProvider:
    id = "openai-compatible"

    def __init__(self, base_url: str, model: str, opener=None, effort: str = "default") -> None:
        self.base_url = str(base_url).rstrip("/")
        self.model = model
        #: `store.EFFORTS`. `low` / `medium` / `high` go on the wire as
        #: `reasoning_effort`, the field the OpenAI API and the servers that
        #: imitate it grade by. `default` and `off` send nothing: there is no
        #: portable "off" - `none` is accepted by some servers and refused by
        #: others - and a field a server rejects is a turn that does not happen.
        self.effort = effort
        self.locality = classify(self.base_url)
        self._opener = opener or urllib.request.urlopen
        #: `/models`, fetched at most once per instance. A turn streams once
        #: per tool round against the same object and the window is fixed.
        self._listed: dict[str, Any] | None = None

    # -- streaming ---------------------------------------------------------

    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        secret: str | None = None,
    ) -> Iterator[Delta]:
        wire = to_wire(messages)
        plan = self.plan_for(wire, tools, secret=secret)
        if not plan.send:
            # Refused before a byte leaves. On a metered endpoint this is also
            # the difference between being told and being billed to be told.
            yield Delta(kind="error", detail=plan.refusal)
            return

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": wire,
            "stream": True,
        }
        # Absent rather than null. Some OpenAI-compatible servers reject an
        # explicit `"tools": null`, and a local server given one is a support
        # ticket nobody will diagnose.
        if tools:
            payload["tools"] = tools
        if self.effort in ("low", "medium", "high"):
            payload["reasoning_effort"] = self.effort
        request = self._request("/chat/completions", payload, secret)
        try:
            with self._opener(request, timeout=STREAM_TIMEOUT_SECONDS) as response:
                # A stop closes this request (`app/interrupt.py`, 2026-09-23):
                # the same silence before the first token as Ollama's, and on
                # a metered endpoint the tokens after a press are billed.
                release = _interrupt.cancel_with(lambda: _interrupt.sever(response))
                try:
                    lines = (
                        line.decode("utf-8", "replace")
                        for line in response
                    )
                    yield from parse_stream(lines, offered=offered_names(tools))
                finally:
                    release()
        except urllib.error.HTTPError as error:
            yield Delta(kind="error", detail=_http_detail(self.base_url, error))
        except Exception as error:  # noqa: BLE001 - surfaced, never swallowed
            yield Delta(kind="error", detail=f"{type(error).__name__}: {error}")

    # -- capabilities ------------------------------------------------------

    def capabilities(self, *, secret: str | None = None) -> Caps:
        """Ask the endpoint what it can do. One real call, no guessing.

        A model that cannot call tools is a supported configuration, not a
        fault, so the failure mode here is an honest `False` with a reason -
        never an optimistic `True` that produces a diagnosis built on defaults
        three turns later.
        """
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": "Call the report_ok tool with ok set to true.",
                }
            ],
            "tools": [PROBE_TOOL],
            "stream": False,
        }
        request = self._request("/chat/completions", payload, secret)
        try:
            with self._opener(request, timeout=PROBE_TIMEOUT_SECONDS) as response:
                body = json.loads(response.read().decode("utf-8", "replace"))
        except Exception as error:  # noqa: BLE001
            return Caps(
                tool_calling=None,
                provenance={"tool_calling": "defaulted"},
                detail=f"could not reach {self.base_url}: {error}",
            )
        message = (body.get("choices") or [{}])[0].get("message") or {}
        called = bool(message.get("tool_calls"))
        window = self.context_budget(secret=secret)
        return Caps(
            tool_calling=called,
            ctx_len=window.ceiling,
            provenance={
                "tool_calling": "measured",
                "ctx_len": window.provenance,
            },
            detail=(
                "the model called the probe tool"
                if called
                else "the model replied with text instead of calling the probe tool"
            ),
        )

    # -- the context budget ------------------------------------------------

    def context_budget(self, *, secret: str | None = None) -> budget_mod.Budget:
        """What this endpoint says its window is, or an honest unknown.

        `settable` is `False` and that is a fact about these servers rather
        than a limitation of this code: `/chat/completions` has no field for a
        context window. llama.cpp's `n_ctx` is set when the server starts, and
        a hosted endpoint's is not the user's to set at all.
        """
        entry = self._model_entry(secret)
        if entry is None:
            return budget_mod.Budget(
                source=f"{self.base_url} did not list {self.model} with a window",
            )
        for field in CONTEXT_FIELDS:
            value = entry.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                continue
            return budget_mod.Budget(
                ceiling=value,
                configured=value,
                provenance="measured",
                source=(
                    f"{self.base_url}/models reports {field} = {value:,} for "
                    f"{self.model}"
                ),
            )
        return budget_mod.Budget(
            source=(
                f"{self.base_url}/models lists {self.model} but states no "
                "context window"
            ),
        )

    def plan_for(
        self,
        wire: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        *,
        secret: str | None = None,
    ) -> budget_mod.Plan:
        """Whether this turn goes. Counts the tool schemas, which are on the wire."""
        need = budget_mod.estimate(*budget_mod.billable(wire, tools))
        return budget_mod.plan(need, self.context_budget(secret=secret), model=self.model)

    def _model_entry(self, secret: str | None) -> dict[str, Any] | None:
        """This model's row out of `/models`, or `None`.

        A `GET`, unlike everything else here. Cached per instance because a
        turn with four tool rounds is four `stream()` calls and one window.
        """
        if self._listed is None:
            self._listed = self._models(secret)
        rows = self._listed.get("data")
        if not isinstance(rows, list):
            return None
        for row in rows:
            if isinstance(row, dict) and str(row.get("id") or "") == self.model:
                return row
        return None

    def _models(self, secret: str | None) -> dict[str, Any]:
        headers = {}
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        request = urllib.request.Request(
            self.base_url + "/models", headers=headers, method="GET"
        )
        try:
            with self._opener(request, timeout=PROBE_TIMEOUT_SECONDS) as response:
                body = json.loads(response.read().decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001 - an endpoint without /models is fine
            return {}
        return body if isinstance(body, dict) else {}

    # -- plumbing ----------------------------------------------------------

    def _request(
        self, path: str, payload: dict[str, Any], secret: str | None
    ) -> urllib.request.Request:
        headers = {"Content-Type": "application/json"}
        # Only when there is one. A local server handed `Bearer None` fails in
        # a way that reads like a model problem and is not.
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        return urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )


# ---------------------------------------------------------------------------
# Wire translation. The Conductor speaks one neutral message shape; each
# adapter renders it the way its server wants.


def to_wire(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Neutral messages -> the OpenAI `chat/completions` message shape.

    The one thing that actually differs: `tool_calls[].function.arguments` is
    a JSON **string** here. Ollama wants an object and refuses a string, which
    is why this translation exists rather than one shape for both.
    """
    out: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "assistant" and message.get("tool_calls"):
            out.append(
                {
                    "role": "assistant",
                    "content": message.get("content", ""),
                    "tool_calls": [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": json.dumps(call.get("arguments") or {}),
                            },
                        }
                        for call in message["tool_calls"]
                    ],
                }
            )
        elif role == "tool":
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": message.get("tool_call_id", ""),
                    "content": message.get("content", ""),
                }
            )
        else:
            out.append({"role": role, "content": message.get("content", "")})
    return out


def _http_detail(base_url: str, error: urllib.error.HTTPError) -> str:
    """An HTTP failure with what the server actually said in it.

    A bare "HTTP 400" is a support ticket. The server's own message is usually
    the whole diagnosis, and hiding it helps nobody.
    """
    try:
        body = error.read().decode("utf-8", "replace").strip()
    except Exception:  # noqa: BLE001
        body = ""
    if len(body) > 500:
        body = body[:500] + " ...(truncated)"
    return f"{base_url} returned HTTP {error.code}" + (f": {body}" if body else "")


# ---------------------------------------------------------------------------
# The parser. Pure, and where all the risk lives.


#: Where OpenAI-compatible servers put a thinking model's reasoning, in the
#: order they are tried (their `Model.ReasoningField` enum names the same three).
REASONING_FIELDS = ("reasoning", "reasoning_content", "reasoning_text")


def parse_stream(
    lines: Iterable[str], offered: Iterable[str] | None = None
) -> Iterator[Delta]:
    """Turn an OpenAI-compatible SSE body into `Delta`s.

    Text is yielded as it arrives. Tool calls are accumulated and yielded once,
    at the end, because a call is not callable until its arguments are whole.

    `offered` is the tool names this request sent, and a whole tag for one of
    them written into `content` is a call - `TextCalls` holds the owner's
    2026-09-23 run and the bounds. llama.cpp's server and LM Studio pass a
    Hermes `<tool_call>` through as content whenever their template parser
    misses it, which is this adapter's share of the same fault.
    """
    salvage = TextCalls(offered or ())
    pending: dict[int, dict[str, Any]] = {}
    for line in lines:
        line = line.strip()
        if not line or not line.startswith("data:"):
            continue
        body = line[5:].strip()
        if body == "[DONE]":
            break
        try:
            chunk = json.loads(body)
        except Exception:  # noqa: BLE001
            # One malformed frame must not kill a reply. It is skipped, not
            # repaired - repairing it would be inventing content.
            continue
        choices = chunk.get("choices") or [{}]
        delta = (choices[0] or {}).get("delta") or {}
        # A THINKING MODEL ANSWERS IN `reasoning`, NOT `content` - Ollama's
        # /v1 endpoint and llama.cpp both stream it there, under one of three
        # names. It was dropped, so a reply made entirely of reasoning reached
        # the conductor as nothing at all: "no words and no tool calls".
        for field in REASONING_FIELDS:
            thought = delta.get(field)
            if isinstance(thought, str) and thought:
                yield Delta(kind="reasoning", text=thought)
                break
        text = delta.get("content")
        if isinstance(text, str) and text:
            yield from salvage.feed(text)
        for fragment in delta.get("tool_calls") or []:
            _accumulate(pending, fragment)

    yield from salvage.close()
    calls, errors = _finish(pending)
    for detail in errors:
        yield Delta(kind="error", detail=detail)
    if calls:
        yield Delta(kind="tool_call", tool_calls=tuple(calls))


def _accumulate(pending: dict[int, dict[str, Any]], fragment: dict[str, Any]) -> None:
    """Merge one streamed tool-call fragment into the call it belongs to."""
    try:
        index = int(fragment.get("index") or 0)
    except (TypeError, ValueError):
        index = 0
    slot = pending.setdefault(index, {"id": "", "name": "", "arguments": ""})
    if fragment.get("id"):
        slot["id"] = str(fragment["id"])
    function = fragment.get("function") or {}
    if function.get("name"):
        slot["name"] = str(function["name"])
    piece = function.get("arguments")
    if isinstance(piece, str):
        slot["arguments"] += piece


def _finish(
    pending: dict[int, dict[str, Any]]
) -> tuple[list[ToolCall], list[str]]:
    calls: list[ToolCall] = []
    errors: list[str] = []
    for index in sorted(pending):
        slot = pending[index]
        if not slot["name"]:
            errors.append("the model sent a tool call with no tool name")
            continue
        raw = slot["arguments"].strip() or "{}"
        try:
            arguments = json.loads(raw)
        except Exception:  # noqa: BLE001
            errors.append(
                f"the model's arguments for {slot['name']} did not parse as JSON"
            )
            continue
        if not isinstance(arguments, dict):
            errors.append(
                f"the model's arguments for {slot['name']} were not an object"
            )
            continue
        calls.append(
            ToolCall(
                id=slot["id"] or f"call_{index}",
                name=slot["name"],
                arguments=arguments,
            )
        )
    return calls, errors
