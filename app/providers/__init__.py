"""The provider protocol, and the two adapters v1 ships.

We ship no AI. The user lends us theirs. Everything in this package exists to
make "your model" a replaceable part rather than an assumption baked through
the codebase.

Two adapters, and this is decided (`ARCHITECTURE.md` Â§4.3):

- **`openai_compatible`** - one code path driven by a base URL, covering
  OpenAI, OpenRouter, vLLM, LM Studio and llama.cpp's server. The reason to
  prefer it is that it is one adapter, not five.
- **`ollama`** - Ollama's own `/api/chat`, because it is the local default and
  its native envelope reports tool calls more reliably than its
  OpenAI-compatible shim does.

A native Anthropic adapter is post-v1. Anthropic's API is a different endpoint,
a different streaming envelope and a different tool-call shape, so it is a
second adapter and not a base URL. Until then, Anthropic models are reachable
through OpenRouter, which is OpenAI-compatible.

## `locality` is not cosmetic

`classify()` decides it and the egress guard reads it. Unknown is `remote`,
always, because the safe default is the restrictive one: a URL we could not
parse must not be treated as if it stayed on this machine.

## Provenance on capabilities

`Caps` carries a `provenance` map alongside its values because invariant 3 says
every displayed number does. A context length read from a model's own metadata
is `measured`; one we assumed because the endpoint would not tell us is
`defaulted`, and the interface has to be able to say which. `tool_calling` is
tri-state for the same reason - `None` means "not probed yet", which is a
different fact from "probed, and no".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Literal, Protocol, runtime_checkable
from urllib.parse import urlparse


#: What a value's provenance may be. `measured` - a tool or an endpoint told
#: us. `inferred` - computed from something measured. `defaulted` - detection
#: failed and we filled it in, which is an assumption and not a measurement.
PROVENANCE = ("measured", "inferred", "defaulted")

#: Hostnames that mean "this machine".
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})


@dataclass(frozen=True)
class Caps:
    """What a connected model can do.

    `tool_calling` is `True` / `False` / `None`, where `None` means we have not
    asked. The product behaves differently in all three states and collapsing
    the third into `False` would make "we have not looked" indistinguishable
    from "we looked and it cannot", which is the difference between a probe
    that has not run and a limitation we are entitled to tell the user about.
    """

    tool_calling: bool | None = None
    json_mode: bool | None = None
    ctx_len: int | None = None
    vision: bool | None = None
    provenance: dict[str, str] = field(default_factory=dict)
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool_calling": self.tool_calling,
            "json_mode": self.json_mode,
            "ctx_len": self.ctx_len,
            "vision": self.vision,
            "provenance": dict(self.provenance),
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ToolCall:
    """One tool the model asked for. `arguments` is already decoded."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Delta:
    """One increment of a reply.

    `kind` is `"text"`, `"reasoning"`, `"tool_call"`, `"error"` or `"end"`.
    Every adapter normalises to this so the Conductor never learns which
    provider it is talking to. `"reasoning"` is a thinking model's thinking,
    in `text`: shown as thinking, never as the reply - unless it is the only
    thing the model said (`conductor._stream_once`).

    `from_text` is true on a `"tool_call"` the model WROTE AS TEXT and an
    adapter salvaged (`TextCalls`), so a reader can record that it happened;
    the call's id also carries `TEXT_CALL_ID_PREFIX`, which reaches the
    transcript through the `tool.call` row whatever reads this field.
    """

    kind: str
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    detail: str = ""
    from_text: bool = False


# ---------------------------------------------------------------------------
# A TOOL CALL WRITTEN AS TEXT IS A TOOL CALL.
#
# MEASURED 2026-09-23 on the owner's model (minicpm5-hermes, a 1B local
# thinking model), a fresh Build/Full thread: after three rounds of calling the
# one tool it had a schema for, its whole final answer was the text
# `<function name="profile_repository"></function>` - the call it wanted,
# written in its chat template's own syntax. Small models trained on Hermes or
# Llama templates do this whenever the server's tool parser misses the call,
# and the person was shown a tag.
#
# THIS IS A NARROW EXCEPTION TO "WE NEVER EMULATE TOOL CALLING BY PARSING JSON
# OUT OF PROSE" (`app/conductor.py`), and the three bounds are what keep it
# narrow: the tag is WHOLE and well-formed, its name is one THIS REQUEST
# OFFERED (a name the harness did not hand over stays text, so nothing here
# can reach a tool the scoping withheld), and the arguments parse or the tag
# is left as the text it was. Nothing is guessed and nothing is repaired.
# ---------------------------------------------------------------------------

#: The id prefix of a salvaged call, so the `tool.call` row says where it came
#: from without any reader having to know about `Delta.from_text`.
TEXT_CALL_ID_PREFIX = "text_call_"

#: The two forms, as (opening marker, closing tag). `<function name="X">` is
#: what the owner's model wrote; `<tool_call>{json}</tool_call>` is Hermes'.
_TEXT_CALL_FORMS: tuple[tuple[str, str], ...] = (
    ("<function", "</function>"),
    ("<tool_call>", "</tool_call>"),
)

#: A tag held this long with no closing tag is prose that happens to contain
#: `<function`, and is released as text rather than held for the whole reply.
_TEXT_CALL_HOLD = 8_000


def offered_names(tools: list[dict[str, Any]] | None) -> tuple[str, ...]:
    """The function names in an OpenAI-shaped `tools` list - what was offered."""
    names: list[str] = []
    for tool in tools or ():
        name = ((tool or {}).get("function") or {}).get("name") if isinstance(tool, dict) else None
        if name:
            names.append(str(name))
    return tuple(names)


def _text_call_arguments(body: str) -> dict[str, Any] | None:
    """A `<function>` body as arguments: empty, a JSON object, or key=value.

    `None` when it is none of those - a body that parses as nothing is not a
    call, and the tag stays text.
    """
    import json
    import os
    import re

    body = body.strip()
    if not body:
        return {}
    if body.startswith("<param") and os.environ.get("MLH_CAP_CALL", "").strip() == "1":
        # MiniCPM5's own template writes `<param name="path">x</param>` per
        # argument (journey databases 2026-09-25: 4 of 11 tags left as text).
        # Behind MLH_CAP_CALL with the round-cap salvage: measured together.
        param = re.compile(r"\s*<param\s+name\s*=\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']\s*>(.*?)</param>\s*", re.DOTALL)
        found: dict[str, Any] = {}
        at = 0
        while at < len(body):
            match = param.match(body, at)
            if match is None or match.end() == at:
                return None
            raw = match.group(2).strip()
            try:
                found[match.group(1)] = json.loads(raw)
            except ValueError:
                found[match.group(1)] = raw
            at = match.end()
        return found
    if body.startswith("{"):
        try:
            value = json.loads(body)
        except ValueError:
            return None
        return value if isinstance(value, dict) else None
    pair = re.compile(
        r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\"[^\"]*\"|'[^']*'|[^,\s]+)\s*(?:,|\n|$)"
    )
    out: dict[str, Any] = {}
    at = 0
    while at < len(body):
        match = pair.match(body, at)
        if match is None or match.end() == at:
            return None
        key, raw = match.group(1), match.group(2)
        if raw[:1] in ("'", '"'):
            out[key] = raw[1:-1]
        else:
            try:
                out[key] = json.loads(raw)
            except ValueError:
                out[key] = raw
        at = match.end()
    return out


def _text_call(tag: str, offered: frozenset[str]) -> tuple[str, dict[str, Any]] | None:
    """`(name, arguments)` for one whole tag, or `None` to leave it as text."""
    import json
    import re

    if tag.startswith("<tool_call>"):
        try:
            value = json.loads(tag[len("<tool_call>"):-len("</tool_call>")].strip())
        except ValueError:
            return None
        if not isinstance(value, dict) or not isinstance(value.get("name"), str):
            return None
        arguments = value.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments or "{}")
            except ValueError:
                return None
        name = value["name"]
    else:
        match = re.fullmatch(
            r"<function\s+name\s*=\s*[\"']([A-Za-z_][A-Za-z0-9_.-]*)[\"']\s*>(.*)</function>",
            tag,
            flags=re.DOTALL,
        )
        if match is None:
            return None
        name, arguments = match.group(1), _text_call_arguments(match.group(2))
    if name not in offered or not isinstance(arguments, dict):
        return None
    return name, arguments


class TextCalls:
    """Finds whole tool-call tags in a stream of text, for the offered names.

    STREAM-SAFE: `feed` releases text up to anything that could be the start
    of a tag and holds the rest until the closing tag arrives, so a tag split
    across chunks becomes one call and none of it leaks as text. `close`
    releases whatever is still held, as text - an unclosed tag was never a
    call.
    """

    def __init__(self, offered: Any) -> None:
        self.offered = frozenset(str(one) for one in offered or ())
        self.held = ""
        self.found = 0

    def feed(self, text: str) -> list[Delta]:
        if not self.offered:
            return [Delta(kind="text", text=text)] if text else []
        self.held += text
        return self._drain(final=False)

    def close(self) -> list[Delta]:
        return self._drain(final=True)

    def _drain(self, *, final: bool) -> list[Delta]:
        out: list[Delta] = []
        text: list[str] = []
        while self.held:
            opening = self._next_opening()
            if opening is None:
                keep = 0 if final else self._partial_marker_at_end()
                text.append(self.held[: len(self.held) - keep])
                self.held = self.held[len(self.held) - keep:]
                break
            start, closing = opening
            text.append(self.held[:start])
            self.held = self.held[start:]
            end = self.held.find(closing)
            if end < 0:
                if final or len(self.held) > _TEXT_CALL_HOLD:
                    text.append(self.held)
                    self.held = ""
                break
            tag = self.held[: end + len(closing)]
            self.held = self.held[end + len(closing):]
            call = _text_call(tag, self.offered)
            if call is None:
                text.append(tag)
                continue
            if "".join(text):
                out.append(Delta(kind="text", text="".join(text)))
            text = []
            name, arguments = call
            out.append(
                Delta(
                    kind="tool_call",
                    tool_calls=(
                        ToolCall(
                            id=f"{TEXT_CALL_ID_PREFIX}{self.found}",
                            name=name,
                            arguments=arguments,
                        ),
                    ),
                    from_text=True,
                )
            )
            self.found += 1
        if "".join(text):
            out.append(Delta(kind="text", text="".join(text)))
        return out

    def _next_opening(self) -> tuple[int, str] | None:
        """The earliest whole opening marker in `held`, and its closing tag.

        `<function` counts only when followed by whitespace, so `<functional`
        in prose is not a marker.
        """
        best: tuple[int, str] | None = None
        for marker, closing in _TEXT_CALL_FORMS:
            at = self.held.find(marker)
            while at >= 0 and marker == "<function":
                after = self.held[at + len(marker): at + len(marker) + 1]
                if after == "" or after.isspace():
                    break
                at = self.held.find(marker, at + 1)
            if at >= 0 and (best is None or at < best[0]):
                best = (at, closing)
        return best

    def _partial_marker_at_end(self) -> int:
        """How many trailing characters could be the start of a marker."""
        for size in range(min(len(self.held), max(len(m) for m, _ in _TEXT_CALL_FORMS)), 0, -1):
            tail = self.held[-size:]
            if any(marker.startswith(tail) for marker, _ in _TEXT_CALL_FORMS):
                return size
        return 0


@runtime_checkable
class Provider(Protocol):
    """The whole surface a model connection has to offer."""

    id: str
    locality: Literal["local", "remote"]

    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        secret: str | None = None,
    ) -> Iterator[Delta]: ...

    def capabilities(self) -> Caps: ...


def classify(base_url: str) -> Literal["local", "remote"]:
    """`"local"` or `"remote"` for an endpoint. Pure; no network.

    Unknown is `remote`. `urlparse("not a url at all").hostname` is `None`
    rather than an exception, so that case is handled explicitly instead of
    being left to an `except` that would never fire.
    """
    try:
        parsed = urlparse(str(base_url))
        host = parsed.hostname
    except Exception:  # noqa: BLE001 - a parse failure is remote, not a crash
        return "remote"
    if not host:
        return "remote"
    host = host.strip("[]").lower()
    if host in LOCAL_HOSTS or host.endswith(".local"):
        return "local"
    return "remote"


#: Endpoints a user can pick without typing a URL. Not an endorsement and not a
#: ranking - the three local ones are first because "your data stays on your
#: machine" is the default this product argues for.
PRESETS: list[dict[str, Any]] = [
    {
        "name": "Ollama",
        "base_url": "http://127.0.0.1:11434",
        "adapter": "ollama",
        "default_model": "",
        "needs_key": False,
    },
    #: MAGNITUDE, and it is here because the owner asked for it by name.
    #:
    #: 2026-09-11: *"stuff I haven't talked about earlier I kinda wanna
    #: implement is a one-click local AI setup. I think there already exists
    #: something called magnitude... it's a one-click AI setup for any local
    #: application."*
    #:
    #: It profiles the machine, picks models that fit it, downloads them and
    #: serves them - and it serves them on an OpenAI-compatible route, which
    #: is why this is ONE LINE and not an integration. `discover()` already
    #: probes every keyless preset for `/models`; adding the endpoint means
    #: a machine running Magnitude is found on first run and its models are
    #: listed beside Ollama's, with one click to connect.
    #:
    #: WHAT IS DELIBERATELY NOT TAKEN. Magnitude also recommends which model
    #: to run on this hardware, and so does this product - `feasibility`, the
    #: fit ranker, `can_this_machine_train`, `where_to_train`. Adopting a
    #: second opinion about the same question would give a person two answers
    #: and no way to choose between them. This takes the serving and leaves
    #: the judgement, which is the half the harness exists to do.
    #:
    #: The path is `/inference/v1` rather than `/v1`: docs.magnitude.dev
    #: names `http://127.0.0.1:10100/inference/v1` for the OpenAI-compatible
    #: API, read 2026-09-11.
    {
        "name": "Magnitude",
        "base_url": "http://127.0.0.1:10100/inference/v1",
        "adapter": "openai-compatible",
        "default_model": "",
        "needs_key": False,
    },
    {
        "name": "LM Studio",
        "base_url": "http://127.0.0.1:1234/v1",
        "adapter": "openai-compatible",
        "default_model": "",
        "needs_key": False,
    },
    {
        "name": "llama.cpp server",
        "base_url": "http://127.0.0.1:8080/v1",
        "adapter": "openai-compatible",
        "default_model": "",
        "needs_key": False,
    },
    #: `suggested_models` ON THE TWO KEYED PRESETS ARE SUGGESTIONS, NOT A
    #: CATALOGUE. They fill the model choice in the connect dialog
    #: (`app/facade/integrations.py`), which always also takes any model id
    #: typed by hand - a vendor's list moves faster than this file, and a
    #: stale entry here costs one failed probe, never a blocked connection.
    #: Written 2026-09-22.
    {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "adapter": "openai-compatible",
        "default_model": "",
        "needs_key": True,
        "suggested_models": ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini", "o4-mini"],
    },
    {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "adapter": "openai-compatible",
        "default_model": "",
        "needs_key": True,
        "suggested_models": [
            "openai/gpt-4.1-mini",
            "anthropic/claude-sonnet-4",
            "google/gemini-2.5-flash",
            "meta-llama/llama-3.3-70b-instruct",
        ],
    },
    {
        "name": "vLLM",
        "base_url": "http://127.0.0.1:8000/v1",
        "adapter": "openai-compatible",
        "default_model": "",
        "needs_key": False,
    },
]

#: The adapter ids a `providers` row may name.
ADAPTERS = ("openai-compatible", "ollama")


def discover(
    probes: list[dict[str, Any]] | None = None, *, timeout: float = 0.6
) -> list[dict[str, Any]]:
    """What is ALREADY running on this machine, before the user types anything.

    Phase C's first-run question is *"what do you already have running?"*
    rather than *"pick a vendor"* - `docs/VISION.md`: it looks. This probes
    every keyless preset's well-known port with a sub-second timeout and
    reports what answered, including the models each one offers. It CREATES
    NOTHING: connecting stays an explicit click on an explicit row, because
    auto-activating whatever answered first would be the harness choosing the
    model that prices every later turn.

    Every preset that `needs_key` is skipped by construction: discovery never
    touches a remote host, so the function cannot leak "somebody here uses
    OpenAI" to anybody, and cannot block first-run on network latency to a
    datacenter.

    `probes` exists for tests: the same shape as PRESETS entries, so a test can
    point discovery at its own ephemeral port instead of pretending 11434 is
    free.
    """
    import json as _json
    import urllib.request

    checked: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for preset in probes if probes is not None else [p for p in PRESETS if not p["needs_key"]]:
        base_url = str(preset["base_url"]).rstrip("/")
        key = (base_url, preset["adapter"])
        if key in seen:
            continue
        seen.add(key)
        entry: dict[str, Any] = {
            "name": preset["name"],
            "base_url": base_url,
            "adapter": preset["adapter"],
            "reachable": False,
            "models": [],
        }
        try:
            if preset["adapter"] == "ollama":
                with urllib.request.urlopen(
                    f"{base_url}/api/tags", timeout=timeout
                ) as response:
                    payload = _json.loads(response.read().decode("utf-8"))
                    entry["reachable"] = True
                    entry["models"] = [
                        str(m.get("name"))
                        for m in (payload.get("models") or [])[:20]
                        if m.get("name")
                    ]
            else:
                with urllib.request.urlopen(
                    f"{base_url}/models", timeout=timeout
                ) as response:
                    payload = _json.loads(response.read().decode("utf-8"))
                    entry["reachable"] = True
                    entry["models"] = [
                        str(m.get("id"))
                        for m in (payload.get("data") or [])[:20]
                        if m.get("id")
                    ]
        except urllib.error.HTTPError:
            # SOMETHING IS LISTENING AND IT SPOKE HTTP - a half-started server,
            # an auth wall, whatever. That is 'alive' and the UI should say so;
            # it is not a model source until it answers the list endpoint.
            entry["reachable"] = True
        except Exception:  # noqa: BLE001 - nothing answering IS the answer here
            pass
        if entry["reachable"] and entry["models"]:
            entry["suggested_model"] = entry["models"][0]
        checked.append(entry)
    return checked


def build(adapter: str, base_url: str, model: str, effort: str = "default") -> Provider:
    """Construct the adapter named on a provider row.

    Imports inside the function so that importing this package does not import
    both adapters, and so a broken adapter cannot take the whole app down at
    import time. `effort` is the row's thinking setting (`store.EFFORTS`);
    each adapter turns it into its own wire field, or nothing.
    """
    if adapter == "ollama":
        from app.providers.ollama import OllamaProvider

        return OllamaProvider(base_url, model, effort=effort)
    if adapter == "openai-compatible":
        from app.providers.openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider(base_url, model, effort=effort)
    raise ValueError(
        f"unknown adapter {adapter!r}; expected one of {', '.join(ADAPTERS)}"
    )
