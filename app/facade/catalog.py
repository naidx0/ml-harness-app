"""Their catalogs - agents, providers, models, config - read off our engine.

## What a provider and a model are, on each side

Their catalog is two-level: a provider (a vendor or a server) offers models,
and a model has variants. This engine's unit is the CONNECTION - one row in
`providers` naming a server, an adapter and ONE model, with its key in the OS
keychain (`app/providers/store.py`). So each connection is offered as a
provider of exactly one model: provider `conn-<row id>` named after the row,
model id the row's model name. A person who has connected three models sees
three entries, which is what the harness's own model picker showed.

The one exception is this machine's Ollama: every model it has, connected or
not, is listed under one provider, `local-ollama` (see "The models already on
this machine" below), and choosing one that is not connected connects it.

THE KEY NEVER LEAVES. Nothing here reads `app/providers/secrets.py`; their
`Provider.Info` has `headers` and `body` fields that could carry one, and they
are left out rather than filled, because a field that is present-but-empty is
one refactor away from being present-and-full.

## Variants are the effort setting

Their "variant" is a named reasoning level on a model; this engine's is the
connection's `effort` (`store.EFFORTS`: default, off, low, medium, high),
which each adapter turns into its own wire field. So a connection's variants
are the four non-default efforts, their "default" is ours, and choosing one
writes the connection's `effort` exactly as the old composer's effort chip did
through `PATCH /api/providers/{id}`.

## One active model, stated plainly

Their protocol keeps a model per session. This engine keeps one ACTIVE
connection for the whole machine, and a turn uses it unless told otherwise. So
switching model in one chat switches it in every chat; the facade does not
invent a per-session binding the engine would not honour on the next turn.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Any
from urllib.parse import urlparse

from app import providers as provider_package
from app.facade import sessions
from app.providers import store as provider_store

PROVIDER_PREFIX = "conn-"

#: What their client sends for "no variant chosen", which is our `default`.
DEFAULT_VARIANT = "default"

#: Their `Provider.Request` requires all three keys; nothing is sent in them.
EMPTY_REQUEST: dict[str, Any] = {"settings": {}, "headers": {}, "body": {}}

# ---------------------------------------------------------------------------
# The models already on this machine
#
# A person who has pulled models into Ollama should find them in the picker
# without connecting anything first. Their connect dialog cannot do it - a key
# method demands a key, and other method types are replaced by a key prompt
# (`docs/PHASE-5-SURFACES.md`, fact 5) - so the models come through the model
# list itself, under ONE provider, `local-ollama`, and choosing one connects
# it (`select_model`).
#
# THE PAIR NEVER CHANGES. Their composer saves the selection as `(providerID,
# modelID)`. So a connected local model is listed under `local-ollama` with
# the model name it was chosen by, exactly as it was listed before it was
# connected - not as `conn-<id>`, which would silently drop the saved
# selection the moment the click succeeded. Every connection to this machine's
# Ollama is listed that way, however it was made, so a model has one name.

LOCAL_PROVIDER = "local-ollama"
LOCAL_PROVIDER_NAME = "Ollama (this machine)"

#: Whether the local Ollama daemon is asked what it has. Off in a test sandbox
#: (`tests/support.py`), where the developer's own models must not appear.
DISCOVER_LOCAL = True

#: How long one answer from the daemon is reused. Their client re-reads the
#: model list on every catalog event and every location switch, and asking
#: Ollama for each model's details costs a request per model.
LOCAL_TTL_SECONDS = 30.0

_LOCAL_GUARD = threading.Lock()
_LOCAL_CACHE: dict[str, Any] = {"at": None, "models": []}


def _ollama_preset() -> dict[str, Any]:
    return next(p for p in provider_package.PRESETS if p["adapter"] == "ollama")


def is_local_ollama(row: dict[str, Any]) -> bool:
    """Is this connection this machine's Ollama, at the preset's port?"""
    if str(row.get("adapter")) != "ollama":
        return False
    try:
        mine = urlparse(str(row.get("base_url") or ""))
        preset = urlparse(str(_ollama_preset()["base_url"]))
        host = (mine.hostname or "").strip("[]").lower()
    except ValueError:
        return False
    return host in provider_package.LOCAL_HOSTS and mine.port == preset.port


def canonical_model(name: Any) -> str:
    """Ollama's name for a model: `llama3.2` and `llama3.2:latest` are one."""
    text = str(name or "")
    return text[: -len(":latest")] if text.endswith(":latest") else text


#: How a model was fetched rather than what it is: a file format in a repo
#: name, or a quantisation or precision in an Ollama tag. Whole `-` pieces only.
_FORMAT = re.compile(r"^(gguf|ggml|safetensors)$", re.IGNORECASE)
_QUANT = re.compile(r"^(i?q[0-9]+(_[0-9a-z]+)*|f16|f32|fp16|fp32|fp8|bf16|int4|int8)$", re.IGNORECASE)


def short_model_name(model_id: Any) -> str:
    """The name a person reads for a model id with no nickname.

    Max, 2026-09-22: `hf.co/openbmb/MiniCPM5-1B-GGUF:Q8_0` reads as
    `MiniCPM5-1B`. The registry host and organisation (everything up to the
    last `/`), a format marker in the repo name (`-GGUF`, `-safetensors`) and
    the tag's `latest` and quantisation (`Q8_0`, `q4_K_M`, `fp16`) go; what is
    left of the tag is what the model IS - `qwen3.5:4b` is `qwen3.5 4b`,
    `llama3:8b-instruct-q4_K_M` is `llama3 8b-instruct`. A name that would be
    empty is the id.
    """
    text = str(model_id or "")
    base, _, tag = text.rpartition("/")[2].partition(":")
    base = "-".join(piece for piece in base.split("-") if not _FORMAT.match(piece))
    tag = "-".join(
        piece
        for piece in tag.split("-")
        if piece and piece.lower() != "latest" and not _QUANT.match(piece)
    )
    if not base:
        return text
    return f"{base} {tag}" if tag else base


def local_rows() -> list[dict[str, Any]]:
    """Connections to this machine's Ollama, newest first."""
    return [row for row in provider_store.list_all() if is_local_ollama(row)]


def _fetch_local() -> list[dict[str, Any]]:
    """What the daemon has, by the `list_local_models` tool's own logic.

    Called in-process rather than through the registry: this is a read for a
    menu, not a step of anybody's work, and it must not land in a transcript.
    A daemon that is not running is an empty list, never an error - the
    picker simply has nothing from this machine in it.
    """
    from app.tools import models as model_tools

    try:
        answer = model_tools.list_local_models()
    except Exception:  # noqa: BLE001 - a menu must render whatever Ollama does
        return []
    if not isinstance(answer, dict) or not answer.get("ok"):
        return []
    found = []
    for entry in answer.get("models") or []:
        name = str((entry or {}).get("name") or "")
        capabilities = (entry or {}).get("capabilities")
        # An embedding model is not something to chat with; Ollama says which
        # models complete text, and a model it says nothing about is kept.
        if not name or (isinstance(capabilities, list) and "completion" not in capabilities):
            continue
        found.append({"name": name, "capabilities": capabilities})
    return found


def discovered_local() -> list[dict[str, Any]]:
    """The daemon's models, from a short-lived cache. Empty when not asked."""
    if not DISCOVER_LOCAL:
        return []
    now = time.monotonic()
    with _LOCAL_GUARD:
        at = _LOCAL_CACHE["at"]
        if at is not None and now - at < LOCAL_TTL_SECONDS:
            return list(_LOCAL_CACHE["models"])
    fresh = _fetch_local()
    with _LOCAL_GUARD:
        _LOCAL_CACHE["at"] = time.monotonic()
        _LOCAL_CACHE["models"] = fresh
    return list(fresh)


def forget_discovered() -> None:
    """Drop the cached answer, so the next read asks the daemon again."""
    with _LOCAL_GUARD:
        _LOCAL_CACHE["at"] = None
        _LOCAL_CACHE["models"] = []


def provider_id(row: dict[str, Any]) -> str:
    if is_local_ollama(row):
        return LOCAL_PROVIDER
    return f"{PROVIDER_PREFIX}{int(row['id'])}"


def connection_of(pid: str) -> int | None:
    """Our connection row id for their provider id, or `None`."""
    text = str(pid)
    if not text.startswith(PROVIDER_PREFIX):
        return None
    rest = text[len(PROVIDER_PREFIX):]
    return int(rest) if rest.isdigit() else None


def variants() -> list[str]:
    return [effort for effort in provider_store.EFFORTS if effort != DEFAULT_VARIANT]


def model_ref(row: dict[str, Any]) -> dict[str, Any]:
    """A connection as their `Model.Ref`: provider, model and chosen variant."""
    ref: dict[str, Any] = {"id": str(row["model"]), "providerID": provider_id(row)}
    effort = str(row.get("effort") or DEFAULT_VARIANT)
    if effort != DEFAULT_VARIANT:
        ref["variant"] = effort
    return ref


def active_model_ref() -> dict[str, Any] | None:
    row = provider_store.active()
    return model_ref(row) if row else None


def ref_for_turn(name: Any, model: Any) -> dict[str, Any]:
    """The `Model.Ref` for a turn that recorded a connection's name and model.

    `turn.started` records the connection by name and model rather than by row
    id, so the row is found by those two. A row that has since been edited or
    deleted is still named honestly - by the model the turn ran - under a
    provider id that says the connection is gone.
    """
    for row in provider_store.list_all():
        if str(row.get("name")) == str(name) and str(row.get("model")) == str(model):
            return {"id": str(model), "providerID": provider_id(row)}
    return {"id": str(model or "unknown"), "providerID": f"{PROVIDER_PREFIX}gone"}


def provider_info(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": provider_id(row),
        "name": str(row.get("name") or row.get("model") or provider_id(row)),
        # Every saved connection can be used; activation decides which one a
        # turn uses, and that is the model choice, not the provider's.
        "activation": "enabled",
        "package": str(row.get("adapter") or ""),
    }


def local_provider_info() -> dict[str, Any]:
    return {
        "id": LOCAL_PROVIDER,
        "name": LOCAL_PROVIDER_NAME,
        "activation": "enabled",
        "package": "ollama",
    }


def _model(
    *, model: str, pid: str, family: str, tools: bool, context: int, name: str | None = None
) -> dict[str, Any]:
    """Their `Model.Info`, for a connection or for a model not yet connected.

    `cost` is empty and `limit.output` is 0 because the engine knows neither;
    `limit.context` is the probe's measured window when there is one and 0 when
    nobody has asked, which is the same "not measured" the harness's own
    settings page shows.

    `time.released` IS A VISIBILITY STAMP, NOT A RELEASE DATE, and it has to
    be one. Their model picker (`providers/models/models.tsx`, `latest`) shows
    a model unasked only if its release date is within six months of now and it
    is the newest of its `family` within its provider - and `released` is
    required, so "unknown" is not sayable. The engine does not know when
    anyone's model was released; a person who connected one, or pulled one
    into Ollama, wants it in the picker. So `released` is the moment of
    answering, and every model is the only member of its family within its
    provider: a connection's family is the connection, and under
    `local-ollama` (one provider, many models) a model's family is the model.
    """
    return {
        "id": model,
        "modelID": model,
        "providerID": pid,
        "family": family,
        "name": name or short_model_name(model),
        "capabilities": {"tools": tools, "input": ["text"], "output": ["text"]},
        "variants": [{"id": effort} for effort in variants()],
        "time": {"released": int(time.time() * 1000)},
        "cost": [],
        "status": "active",
        "enabled": True,
        "limit": {"context": context, "output": 0},
    }


def model_info(row: dict[str, Any]) -> dict[str, Any]:
    """A connection's model as their `Model.Info`.

    `name` IS THE CONNECTION'S NAME - the person's nickname for it, which
    `PATCH /api/providers/{id} {"name": ...}` edits - and their picker draws
    `name`. Max, 2026-09-22: he wants his own names for models, not
    `minicpm5-hermes:latest`. `id` and `modelID` stay the model id, because
    their composer saves the selection as `(providerID, modelID)` and a rename
    must not drop it. A row with no name falls back to the model id.
    """
    pid = provider_id(row)
    return _model(
        model=str(row["model"]),
        pid=pid,
        family=str(row["model"]) if pid == LOCAL_PROVIDER else pid,
        tools=str(row.get("tool_calling")) == "yes",
        context=int(row.get("ctx_len") or 0),
        name=_nickname(row),
    )


def _nickname(row: dict[str, Any]) -> str | None:
    """The connection's name, unless it is only the model id again.

    `default_model` connects a local model under its own id as the name, and a
    name that repeats the id is no nickname - the short name reads better.
    """
    name = str(row.get("name") or "").strip()
    if not name or canonical_model(name) == canonical_model(row.get("model")):
        return None
    return name


def discovered_info(entry: dict[str, Any]) -> dict[str, Any]:
    """A model Ollama has and nobody has connected yet.

    Tool calling is what Ollama itself says the model can do. The connection
    made when it is chosen is probed, and from then on the probe's answer is
    the one listed.
    """
    capabilities = entry.get("capabilities")
    return _model(
        model=str(entry["name"]),
        pid=LOCAL_PROVIDER,
        family=str(entry["name"]),
        tools=isinstance(capabilities, list) and "tools" in capabilities,
        context=0,
    )


def fingerprint() -> tuple[Any, ...]:
    """Everything about the connections that their catalogs are drawn from.

    The event stream compares this between polls and tells their client to
    re-read providers, models and config when it moves, because no door that
    edits a connection (`/api/providers/*`, this facade's model switch) writes
    an event of its own.
    """
    return tuple(
        (
            row.get("id"),
            row.get("name"),
            row.get("model"),
            row.get("adapter"),
            row.get("effort"),
            row.get("is_active"),
            row.get("tool_calling"),
            row.get("ctx_len"),
        )
        for row in provider_store.list_all()
    )


def _local_listing() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """`(connected rows, one per model; discovered models not connected)`.

    Two connections to one local model are one entry, because they are one
    `(local-ollama, model)` pair to their picker: the active one if either is,
    else the newest.
    """
    chosen: dict[str, dict[str, Any]] = {}
    for row in local_rows():  # newest first
        key = canonical_model(row["model"])
        if key not in chosen or (row.get("is_active") and not chosen[key].get("is_active")):
            chosen[key] = row
    connected = list(chosen.values())
    seen = set(chosen)
    loose = []
    for entry in discovered_local():
        key = canonical_model(entry["name"])
        if key not in seen:
            seen.add(key)
            loose.append(entry)
    return connected, loose


def providers() -> list[dict[str, Any]]:
    out = [provider_info(row) for row in provider_store.list_all() if not is_local_ollama(row)]
    connected, loose = _local_listing()
    if connected or loose:
        out.append(local_provider_info())
    return out


def models() -> list[dict[str, Any]]:
    out = [model_info(row) for row in provider_store.list_all() if not is_local_ollama(row)]
    connected, loose = _local_listing()
    out += [model_info(row) for row in connected]
    out += [discovered_info(entry) for entry in loose]
    return out


def default_model() -> dict[str, Any] | None:
    row = provider_store.active()
    return model_info(row) if row else None


def _local_row_for(model: str) -> dict[str, Any] | None:
    """The connection a `(local-ollama, model)` pair means, if it is connected.

    The exact name first, then the same model under Ollama's other spelling;
    the active connection before an inactive one, the newest before an older.
    """
    wanted = canonical_model(model)
    rows = [row for row in local_rows() if canonical_model(row["model"]) == wanted]
    rows.sort(key=lambda row: (str(row["model"]) != model, not row.get("is_active")))
    return rows[0] if rows else None


def connect_local(model: str) -> dict[str, Any]:
    """Connect a model Ollama has: a connection named after it, active, probed.

    Refused with `LookupError` when the daemon does not list the model, because
    a connection to a model that is not there would fail on the first turn
    with a stranger error than this one.
    """
    names = [entry["name"] for entry in discovered_local()]
    if not any(canonical_model(name) == canonical_model(model) for name in names):
        forget_discovered()
        names = [entry["name"] for entry in discovered_local()]
    if not any(canonical_model(name) == canonical_model(model) for name in names):
        listed = ", ".join(names[:12]) if names else "nothing (is Ollama running?)"
        raise LookupError(f"Ollama on this machine does not have {model!r}; it lists {listed}")
    preset = _ollama_preset()
    row = provider_store.create(canonical_model(model)[:120], str(preset["base_url"]), model, "ollama")
    provider_store.set_active(int(row["id"]))
    probe_later(int(row["id"]))
    return provider_store.get(int(row["id"])) or row


def select_model(ref: dict[str, Any] | None) -> None:
    """Make the named connection the active one, at the named effort.

    A `local-ollama` model that is not connected yet is connected here - one
    click, from their own picker (`connect_local`). Raises `LookupError` for a
    provider id or local model that names nothing, so the route can answer with
    their declared error rather than activate nothing and report success.
    """
    if not ref:
        return
    variant = ref.get("variant") or DEFAULT_VARIANT
    if variant not in provider_store.EFFORTS:
        raise ValueError(
            f"unknown variant {variant!r}; expected one of {', '.join(provider_store.EFFORTS)}"
        )
    pid = str(ref.get("providerID") or "")
    if pid == LOCAL_PROVIDER:
        model = str(ref.get("id") or "").strip()
        if not model:
            raise LookupError("a local model needs its name")
        row = _local_row_for(model) or connect_local(model)
    else:
        connection = connection_of(pid)
        row = provider_store.get(connection) if connection is not None else None
        if row is None:
            raise LookupError(f"no connection named {ref.get('providerID')!r}")
    provider_store.set_active(int(row["id"]))
    if str(row.get("effort") or DEFAULT_VARIANT) != variant:
        provider_store.update(int(row["id"]), effort=variant)


#: Whether a connection made through this facade is probed after it is made.
#: `tests/support.py::sandbox` turns it off, because a probe is a real request
#: to the connection's server - a vendor's API with a test's fake key, or the
#: developer's own Ollama - and a test that wants one patches `probe_later`.
PROBE_AFTER_CONNECT = True


def probe_later(connection: int) -> None:
    """Ask a new connection what it can do, without making anybody wait.

    `conductor.probe` is the engine's own probe (`POST /api/providers/{id}/
    probe`): it calls the server once and writes tool calling and context
    length on the row. It runs on a daemon thread because the person is
    looking at a dialog that has already done its part, and the answer reaches
    their catalogs the way every connection edit does: the event stream sees
    the row change and tells their client to re-read (`stream.catalog_changed`).
    A probe that fails leaves the row as it was, which is "not probed yet".
    """
    if not PROBE_AFTER_CONNECT:
        return
    import threading

    def run() -> None:
        from app import conductor

        try:
            conductor.probe(int(connection))
        except Exception:  # noqa: BLE001 - a daemon thread has nobody to raise to
            pass

    threading.Thread(target=run, name=f"facade-probe-{connection}", daemon=True).start()


def agents() -> list[dict[str, Any]]:
    """The thread's mode-and-ladder pairs (`sessions.AGENTS`) as their `Agent.Info`."""
    out = []
    for name, preset in sessions.AGENTS.items():
        out.append(
            {
                "id": name,
                "name": name.capitalize(),
                "description": preset["description"],
                "request": dict(EMPTY_REQUEST),
                "mode": "primary",
                "hidden": False,
                "permissions": sessions.ruleset_of(preset["permission"]),
            }
        )
    return out


def config_entries() -> list[dict[str, Any]]:
    """Their config as one document: the default agent and the active model.

    `default_agent` is the mode a person's new conversation opens in
    (`modes.WHEN_A_PERSON_OPENS_A_CONVERSATION`), so their composer starts where
    the harness's own route does.
    """
    from app import modes

    info: dict[str, Any] = {"default_agent": modes.WHEN_A_PERSON_OPENS_A_CONVERSATION}
    row = provider_store.active()
    if row is not None:
        chosen: dict[str, Any] = {"providerID": provider_id(row), "model": str(row["model"])}
        effort = str(row.get("effort") or DEFAULT_VARIANT)
        if effort != DEFAULT_VARIANT:
            chosen["variant"] = effort
        info["model"] = chosen
    return [{"type": "document", "info": info}]
