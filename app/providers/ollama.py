"""Ollama, spoken natively rather than through its OpenAI-compatible shim.

Ollama is the local default for this product and it gets its own adapter for
two concrete reasons, not for symmetry:

1. **`/api/show` answers the capability question without spending a turn.** It
   reports a `capabilities` list and the model's real `context_length`. Both
   are *measured* - read from the model the user actually pulled - where a
   guess from a name like "8b" would be defaulted, and invariant 3 says the
   interface has to be able to tell those apart.
2. **The native envelope is newline-delimited JSON with whole tool calls.**
   Ollama sends `arguments` as an object in one chunk rather than as string
   fragments spread across many, so there is no accumulator here and therefore
   no class of reassembly bug. Going through the shim would reintroduce it for
   nothing.

The base URL is the server root (`http://127.0.0.1:11434`), not a `/v1` path.
A trailing `/v1` is stripped rather than rejected, because a user who copies
the OpenAI-compatible URL out of Ollama's own documentation has not made a
mistake worth an error message.

## The window is named, not inherited

This adapter used to send no `num_ctx`, which meant the runtime context was
whatever the server felt like - 65,536 where a Modelfile said so, 4,096 where
nothing did. A turn puts 13,213 tokens on the wire before the user types
anything: 7,108 for the system prompt and 6,074 for the 28 tool schemas, on
granite4-hermes's own tokeniser through `prompt_eval_count`.

Ollama does not error when a prompt exceeds the window. It keeps as much as fits
in half of it - the other half is reserved for generation - and answers as if
nothing had been lost. At the 4,096 default that is 2,050 of the 13,213 tokens,
returned as HTTP 200 with no error field.

So `stream()` now names the window it needs, and refuses when the model cannot
give it. See `app/providers/budget.py` for the arithmetic and for why an
estimate is allowed to be one. The rule here is only: never lower a window the
user set on purpose, never exceed what the weights support, and never send a
prompt we know will be cut.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Iterable, Iterator

from app import interrupt as _interrupt
from app.providers import Caps, Delta, TextCalls, ToolCall, classify, offered_names
from app.providers import budget as budget_mod


STREAM_TIMEOUT_SECONDS = 600
PROBE_TIMEOUT_SECONDS = 60

#: Offered to the model when `/api/show` will not say. Trivial on purpose.
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


#: WHAT A STRANGER IS TOLD WHEN NOTHING ANSWERS, and it is the route rather
#: than the exception.
#:
#: MEASURED 2026-09-10 on a bare Windows Sandbox: the stranger walk reached its
#: own "=== done ===" with no model, and the one-click "Connect a model" button
#: calls activate and then probe. With no daemon the probe returned
#: `could not reach http://127.0.0.1:11434: <urlopen error ...>` - a Python
#: exception handed to somebody who has never heard of urllib, at the exact
#: moment they are trying to start. That is the complaint this lane exists for
#: in its purest form: a tool in the face, at the first step.
#:
#: THREE SENTENCES, AND EACH ONE IS A THING THE PERSON CAN DO OR STOP WORRYING
#: ABOUT: which of the two states this is, where the thing comes from, and that
#: nobody has to come back and press anything. The last one matters most - a
#: person who is not told the harness re-probes will sit and click.
#:
#: The installer is named and NOT automated: measured the same day, Ollama's
#: Windows installer answers no unattended flag - `/S` and `/VERYSILENT` were
#: both still alive after 240 seconds - and a human clicks through it in
#: seconds. Telling somebody to click is honest; pretending to do it for them
#: and hanging is not.
THE_DAEMON_IS_NOT_RUNNING = (
    "The local model daemon is not running. This is not 'you have no models' - "
    "it is a different thing, and nothing is wrong with your setup. "
    "Ollama is what serves them: install it from https://ollama.com/download "
    "and it starts itself. "
    "You do not have to come back here - the harness re-probes when it appears."
)
def cannot_reach(base_url: str, error: object) -> str:
    """The route, with the exception kept where a maintainer can still read it."""
    return f"{THE_DAEMON_IS_NOT_RUNNING} (nothing answered at {base_url}: {error})"


class OllamaProvider:
    id = "ollama"

    def __init__(self, base_url: str, model: str, opener=None, effort: str = "default") -> None:
        root = str(base_url).rstrip("/")
        if root.endswith("/v1"):
            root = root[: -len("/v1")]
        self.base_url = root
        self.model = model
        #: `store.EFFORTS`. Sent as Ollama's `think` - and only when `/api/show`
        #: lists `thinking` among the model's capabilities, because Ollama
        #: answers `think` on a model without it with an error, not a shrug.
        self.effort = effort
        self.locality = classify(self.base_url)
        self._opener = opener or urllib.request.urlopen
        #: `/api/show` for this model, fetched at most once per instance. A
        #: turn streams once per tool round against the same adapter object,
        #: and the model's window does not change between rounds.
        self._shown: dict[str, Any] | None = None

    # -- streaming ---------------------------------------------------------

    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        secret: str | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> Iterator[Delta]:
        wire = to_wire(messages)
        plan = self.plan_for(wire, tools, secret=secret)
        if not plan.send:
            # NOTHING IS SENT. Not a shorter prompt, not the prompt with the
            # end missing - the turn does not happen and the user is told why.
            # A reply produced from a truncated instruction set is worse than
            # no reply, because it looks like one.
            yield Delta(kind="error", detail=plan.refusal)
            return

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": wire,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
        if plan.request is not None:
            payload["options"] = {"num_ctx": plan.request}
        think = self.think_field(secret=secret)
        if think is not None:
            payload["think"] = think
        if response_format is not None:
            # CONSTRAINED DECODING, which the diagnosis engine recommends and
            # this product could not do.
            #
            # `NO_TRAIN__CONSTRAINED_DECODING` says "never fine-tune for a
            # format a grammar can enforce" and points at JSON schema /
            # structured outputs / GBNF. On 2026-09-09 that verdict was reached
            # on a real thread and there was no way to act on it: no `format` on
            # this adapter, no `response_format` on the OpenAI-compatible one,
            # and no tool declaring `constrained_decoding_tried`. The engine
            # recommended a move the product could not make.
            #
            # Ollama takes a JSON Schema here and constrains generation to it,
            # so compliance is 100% by construction rather than by asking.
            payload["format"] = response_format
        request = self._request("/api/chat", payload, secret)
        try:
            with self._opener(request, timeout=STREAM_TIMEOUT_SECONDS) as response:
                # A STOP CLOSES THIS REQUEST, 2026-09-23 (`app/interrupt.py`).
                # Before the first token Ollama sends nothing for as long as
                # the prompt takes to evaluate, so there is no next line for
                # the conductor to check the flag between - the socket is the
                # only thing a press can reach, and Ollama stops generating
                # when it sees the client go.
                release = _interrupt.cancel_with(lambda: _interrupt.sever(response))
                try:
                    lines = (line.decode("utf-8", "replace") for line in response)
                    yield from parse_stream(lines, offered=offered_names(tools))
                finally:
                    release()
        except urllib.error.HTTPError as error:
            yield Delta(kind="error", detail=_http_detail(self.base_url, error))
        except Exception as error:  # noqa: BLE001
            yield Delta(kind="error", detail=f"{type(error).__name__}: {error}")

    # -- capabilities ------------------------------------------------------

    def capabilities(self, *, secret: str | None = None) -> Caps:
        """Ask `/api/show` first; fall back to a live probe.

        `/api/show` is authoritative and free. Older Ollama builds do not
        report `capabilities`, so the fallback spends one short turn asking the
        model to call a trivial tool. If neither works, `tool_calling` is
        `None` - not probed - and the provenance says `defaulted`, because a
        cheerful `True` here is how a product ends up reporting numbers it
        never measured.
        """
        shown = self._show(secret)
        ctx_len, ctx_provenance = _context_length(shown)
        listed = shown.get("capabilities") if isinstance(shown, dict) else None
        if isinstance(listed, list):
            return Caps(
                tool_calling="tools" in listed,
                vision="vision" in listed,
                ctx_len=ctx_len,
                provenance={
                    "tool_calling": "measured",
                    "ctx_len": ctx_provenance,
                },
                detail="reported by the Ollama server for this model",
            )

        probed, detail = self._probe(secret)
        return Caps(
            tool_calling=probed,
            ctx_len=ctx_len,
            provenance={
                "tool_calling": "measured" if probed is not None else "defaulted",
                "ctx_len": ctx_provenance,
            },
            detail=detail,
        )

    # -- the context budget ------------------------------------------------

    def context_budget(self, *, secret: str | None = None) -> budget_mod.Budget:
        """What this connection will accept, in tokens, and where that came from.

        Two different numbers live in `/api/show` and conflating them is the
        whole defect:

        - `model_info["<arch>.context_length"]` is the **ceiling** - what the
          weights support. `granite4-hermes` reports 1,048,576.
        - `parameters` carries `num_ctx` when a Modelfile set one. That is the
          **configured** window - what the server uses if we say nothing. The
          same model reports 65,536, sixteen times smaller than its ceiling.

        A server that reports neither leaves an honestly unknown budget rather
        than a cheerful default, because `budget.UNKNOWN` is a state the caller
        handles and an invented number is not.
        """
        shown = self._show(secret)
        if not shown:
            return budget_mod.Budget(
                settable=True,
                source=f"{self.base_url} did not answer /api/show for {self.model}",
            )
        ceiling, ceiling_provenance = _context_length(shown)
        configured = _configured_num_ctx(shown)
        return budget_mod.Budget(
            ceiling=ceiling,
            configured=configured,
            # Ollama takes `options.num_ctx` on every request, so the window is
            # ours to name rather than ours to discover.
            settable=True,
            provenance=ceiling_provenance,
            source=_budget_source(self.model, ceiling, configured),
        )

    def plan_for(
        self,
        wire: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        *,
        secret: str | None = None,
    ) -> budget_mod.Plan:
        """Whether this turn goes, and with what window. No bytes sent yet.

        The estimate counts what actually goes on the wire - every message AND
        the tool schemas, which are the half that gets forgotten. They cost
        6,074 tokens against granite4-hermes, on every turn, alongside the
        8,025 the system prompt costs.
        """
        need = budget_mod.estimate(*budget_mod.billable(wire, tools))
        budget = self.context_budget(secret=secret)
        return budget_mod.plan(need, budget, model=self.model)

    def think_field(self, *, secret: str | None = None) -> bool | None:
        """What goes on the wire as `think`, or `None` for nothing.

        `default` sends nothing. `off` sends `think: false`, the other three
        `think: true`. Ollama's `think` takes a level ("low"/"medium"/"high")
        for a few models and a boolean for the rest, and a level on a model
        that only takes a boolean is a 400 - so this sends the boolean, which
        every thinking model accepts, and the level is left to the servers
        that grade it. Nothing at all for a model whose `/api/show` does not
        list `thinking`: the field would be an error there.
        """
        if self.effort in (None, "", "default"):
            return None
        shown = self._show(secret)
        caps = shown.get("capabilities") if isinstance(shown, dict) else None
        if not isinstance(caps, list) or "thinking" not in caps:
            return None
        return self.effort != "off"

    def _show(self, secret: str | None) -> dict[str, Any]:
        if self._shown is not None:
            return self._shown
        request = self._request("/api/show", {"model": self.model}, secret)
        try:
            with self._opener(request, timeout=PROBE_TIMEOUT_SECONDS) as response:
                shown = json.loads(response.read().decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001 - an older server is not a crash
            shown = {}
        self._shown = shown if isinstance(shown, dict) else {}
        return self._shown

    def _probe(self, secret: str | None) -> tuple[bool | None, str]:
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
        request = self._request("/api/chat", payload, secret)
        try:
            with self._opener(request, timeout=PROBE_TIMEOUT_SECONDS) as response:
                body = json.loads(response.read().decode("utf-8", "replace"))
        except Exception as error:  # noqa: BLE001
            #: THE ROUTE, NOT THE TRACEBACK. The exception is kept in
            #: parentheses because a maintainer reading a log still needs it;
            #: it just stops being the whole answer.
            return None, cannot_reach(self.base_url, error)
        called = bool((body.get("message") or {}).get("tool_calls"))
        return called, (
            "the model called the probe tool"
            if called
            else "the model replied with text instead of calling the probe tool"
        )

    def _request(
        self, path: str, payload: dict[str, Any], secret: str | None
    ) -> urllib.request.Request:
        headers = {"Content-Type": "application/json"}
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        return urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )


# ---------------------------------------------------------------------------


def to_wire(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Neutral messages -> Ollama's `/api/chat` message shape.

    Two differences from the OpenAI shape, both found against a live server
    rather than read off a page:

    - `tool_calls[].function.arguments` must be an **object**. A JSON string
      there is rejected with `HTTP 400: Value looks like object, but can't find
      closing '}' symbol`, which names neither the field nor the message.
    - a tool result is identified by `tool_name`, not by `tool_call_id`.
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
                            "function": {
                                "name": call["name"],
                                "arguments": call.get("arguments") or {},
                            }
                        }
                        for call in message["tool_calls"]
                    ],
                }
            )
        elif role == "tool":
            entry = {"role": "tool", "content": message.get("content", "")}
            if message.get("name"):
                entry["tool_name"] = message["name"]
            out.append(entry)
        else:
            out.append({"role": role, "content": message.get("content", "")})
    return out


def _http_detail(base_url: str, error: urllib.error.HTTPError) -> str:
    """An HTTP failure carrying what the server actually said."""
    try:
        body = error.read().decode("utf-8", "replace").strip()
    except Exception:  # noqa: BLE001
        body = ""
    if len(body) > 500:
        body = body[:500] + " ...(truncated)"
    return f"{base_url} returned HTTP {error.code}" + (f": {body}" if body else "")


def parse_stream(
    lines: Iterable[str], offered: Iterable[str] | None = None
) -> Iterator[Delta]:
    """Newline-delimited JSON in, `Delta`s out.

    No accumulator: Ollama sends each tool call whole. A line that does not
    parse is skipped rather than repaired.

    `offered` is the tool names this request sent. A whole
    `<function name="X">...</function>` or `<tool_call>{...}</tool_call>` in
    the CONTENT, for an offered X, is a tool call - see `TextCalls` for the
    owner's 2026-09-23 run that wrote its call as text, and for the bounds.
    `None` - the forced final round, a probe - salvages nothing.
    """
    salvage = TextCalls(offered or ())
    yield from _parse_lines(lines, salvage)
    # Whatever is still held - a lone `<` at the very end, an unclosed tag -
    # is released as the text it was.
    yield from salvage.close()


def _parse_lines(lines: Iterable[str], salvage: TextCalls) -> Iterator[Delta]:
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            chunk = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if chunk.get("error"):
            yield Delta(kind="error", detail=str(chunk["error"]))
            continue
        message = chunk.get("message") or {}
        # A thinking model's reasoning arrives in `message.thinking` on the
        # native API; see `openai_compatible.parse_stream` for why it matters.
        thought = message.get("thinking")
        if isinstance(thought, str) and thought:
            yield Delta(kind="reasoning", text=thought)
        text = message.get("content")
        if isinstance(text, str) and text:
            yield from salvage.feed(text)
        calls = _calls(message.get("tool_calls") or [])
        if calls:
            yield Delta(kind="tool_call", tool_calls=tuple(calls))
        if chunk.get("done"):
            break


def _calls(raw: list[dict[str, Any]]) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for index, item in enumerate(raw):
        function = (item or {}).get("function") or {}
        name = function.get("name")
        if not name:
            continue
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments or "{}")
            except Exception:  # noqa: BLE001
                continue
        if not isinstance(arguments, dict):
            continue
        calls.append(
            ToolCall(
                id=str(item.get("id") or f"call_{index}"),
                name=str(name),
                arguments=arguments,
            )
        )
    return calls


def _configured_num_ctx(shown: dict[str, Any]) -> int | None:
    """The `num_ctx` a Modelfile set, from `/api/show`'s `parameters` block.

    That block is the Modelfile's own text, not JSON - lines of
    `name<spaces>value`. Absent means the Modelfile set nothing, which means
    the server will use its own default, which we cannot read over HTTP and
    therefore do not pretend to know.
    """
    raw = shown.get("parameters") if isinstance(shown, dict) else None
    if not isinstance(raw, str):
        return None
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "num_ctx":
            try:
                value = int(parts[1])
            except ValueError:
                return None
            return value if value > 0 else None
    return None


def _budget_source(model: str, ceiling: int | None, configured: int | None) -> str:
    """Plain words for where the window numbers came from."""
    if ceiling is None and configured is None:
        return (
            f"/api/show answered for {model} but reported neither a context "
            "length nor a num_ctx"
        )
    said = []
    if ceiling is not None:
        said.append(f"{model}'s weights support {ceiling:,} tokens")
    if configured is not None:
        said.append(f"its Modelfile sets num_ctx to {configured:,}")
    return "/api/show reports " + " and ".join(said)


def _context_length(shown: dict[str, Any]) -> tuple[int | None, str]:
    """The model's real context length, and where the figure came from.

    `measured` when the server told us. `defaulted` when it did not - and in
    that case the value is `None`, because invariant 5 says we do not invent a
    number, and a context length nobody measured is exactly the kind of number
    that gets invented.
    """
    info = shown.get("model_info") if isinstance(shown, dict) else None
    if isinstance(info, dict):
        for key, value in info.items():
            if key.endswith(".context_length") and isinstance(value, int):
                return value, "measured"
    return None, "defaulted"
