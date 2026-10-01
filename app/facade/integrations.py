"""Their connect dialog, over the harness's keyed presets.

Their "Connect a provider" dialog (`providers/connect/dialog.tsx` and
`controller.ts` in the vendored app) lists `integration.list`, reads one
integration's methods with `integration.get`, walks a key method's form, and
sends the key with the form's answer to `integration.connect.key`. Their
settings page disconnects by reading `integration.get` for the provider and
removing every credential connection it lists through `credential.remove`.

This engine's unit is still the CONNECTION (`app/providers/store.py`): one
row, one server, one model, its key in the OS keychain. So an integration here
is a PRESET that needs a key - OpenAI, OpenRouter - and connecting through it
creates one connection row the same way `POST /api/providers` does, by calling
that route's own function, so the keychain handling and its refusal sentence
are the engine's and not a copy.

## What is offered, and what is not

* **Only presets with `needs_key`.** A local server needs no key, and their key
  method always demands one (`ApiAuthView` refuses an empty key), so local
  servers come through the model picker instead (`catalog.local_models`).
* **Never OAuth.** Their OAuth method opens a browser and polls a sign-in this
  engine has no counterpart for; the method list is key-only.
* **No Anthropic.** `app/providers` has no adapter that speaks Anthropic's own
  API (its docstring: a native adapter is post-v1, and Anthropic models are
  reached through OpenRouter). Offering it would create a connection the
  engine cannot use.

## The model is a form field

A connection names one model, so the key method carries a form. Their form
renders a string field WITH options as a pick list and one WITHOUT options as
free text, never both (`AuthFormView`). So the choice is two fields: the
preset's suggested models plus "Another model...", and a free-text field shown
only when that last option is picked (their `when` condition). A preset with
no suggestions gets the free-text field alone.

## Disconnecting one connection, not a whole vendor

Their settings page disconnects a provider by `integration.get` on the
provider's `integrationID ?? id`. Connection providers are listed without an
`integrationID`, so the page asks for `conn-<id>` - and `integration.get`
answers that with a one-connection integration, which makes "Disconnect" on
one row forget exactly that row. `local-ollama` is answered the same way with
every connection to this machine's Ollama. Neither is ever LISTED as an
integration.
"""

from __future__ import annotations

import re
from typing import Any

from app import providers
from app.providers import store as provider_store

#: The option value that reveals the free-text model field. Not a model id any
#: vendor uses, because it is not an id at all.
OTHER_MODEL = "__another__"

#: The form keys their dialog sends back in `answer`.
MODEL_FIELD = "model"
CUSTOM_MODEL_FIELD = "model_id"


def integration_id(preset: dict[str, Any]) -> str:
    """`OpenAI` -> `openai`: the ids their provider icons and featured list use."""
    return re.sub(r"[^a-z0-9]+", "-", str(preset["name"]).lower()).strip("-")


def keyed_presets() -> dict[str, dict[str, Any]]:
    """Every preset that needs a key, by integration id, in preset order."""
    return {integration_id(p): p for p in providers.PRESETS if p.get("needs_key")}


def _same_url(left: Any, right: Any) -> bool:
    return str(left or "").rstrip("/").lower() == str(right or "").rstrip("/").lower()


def rows_for(preset: dict[str, Any]) -> list[dict[str, Any]]:
    """The connections made to this preset's endpoint, however they were made."""
    return [
        row
        for row in provider_store.list_all()
        if _same_url(row.get("base_url"), preset["base_url"])
        and str(row.get("adapter")) == str(preset["adapter"])
    ]


def credential_id(row: dict[str, Any]) -> str:
    """A connection as their credential id - the provider id it is listed under."""
    return f"conn-{int(row['id'])}"


def connection_of_credential(credential: str) -> int | None:
    text = str(credential)
    if text.startswith("conn-") and text[len("conn-"):].isdigit():
        return int(text[len("conn-"):])
    return None


def credential(row: dict[str, Any]) -> dict[str, Any]:
    name = str(row.get("name") or "")
    model = str(row.get("model") or "")
    label = f"{name} ({model})" if name and model and model not in name else (name or model)
    return {"type": "credential", "id": credential_id(row), "label": label, "method": "key"}


def model_form(preset: dict[str, Any]) -> list[dict[str, Any]]:
    """The key method's form: which model this connection will use."""
    suggested = [str(m) for m in preset.get("suggested_models") or [] if str(m).strip()]
    custom: dict[str, Any] = {
        "key": CUSTOM_MODEL_FIELD,
        "type": "string",
        "title": "Model id",
        "description": f"The model's id exactly as {preset['name']} names it.",
        "placeholder": suggested[0] if suggested else "model id",
        "required": True,
    }
    if not suggested:
        return [dict(custom, key=MODEL_FIELD)]
    choice = {
        "key": MODEL_FIELD,
        "type": "string",
        "title": "Model",
        "description": "The model this connection will use. Each model is its own connection.",
        "required": True,
        "options": [{"value": m, "label": m} for m in suggested]
        + [{"value": OTHER_MODEL, "label": "Another model...", "description": "type its id"}],
    }
    custom["when"] = [{"key": MODEL_FIELD, "op": "eq", "value": OTHER_MODEL}]
    return [choice, custom]


def info(iid: str, preset: dict[str, Any]) -> dict[str, Any]:
    """A keyed preset as their `Integration.Info`."""
    return {
        "id": iid,
        "name": str(preset["name"]),
        "metadata": {"harness": {"baseURL": preset["base_url"], "adapter": preset["adapter"]}},
        "methods": [{"type": "key", "label": "API key", "form": model_form(preset)}],
        "connections": [credential(row) for row in rows_for(preset)],
    }


def listed() -> list[dict[str, Any]]:
    return [info(iid, preset) for iid, preset in keyed_presets().items()]


def one_connection(row: dict[str, Any], iid: str, name: str | None = None) -> dict[str, Any]:
    """A single connection answered as an integration, so it can be disconnected alone."""
    return {
        "id": iid,
        "name": name or str(row.get("name") or row.get("model") or iid),
        "methods": [],
        "connections": [credential(row)],
    }


def find(iid: str) -> dict[str, Any] | None:
    """`integration.get`: a keyed preset, one connection, or this machine's Ollama."""
    from app.facade import catalog

    presets = keyed_presets()
    if iid in presets:
        return info(iid, presets[iid])
    connection = catalog.connection_of(iid)
    if connection is not None:
        row = provider_store.get(connection)
        return one_connection(row, iid) if row is not None else None
    if iid == catalog.LOCAL_PROVIDER:
        # Their settings page lists `local-ollama` as a connected provider;
        # its Disconnect forgets every connection to this machine's Ollama.
        # The models stay in the picker, not connected, because Ollama still
        # has them.
        return {
            "id": iid,
            "name": catalog.LOCAL_PROVIDER_NAME,
            "methods": [],
            "connections": [credential(row) for row in catalog.local_rows()],
        }
    return None


def chosen_model(preset: dict[str, Any], answer: Any) -> str:
    """The model the form's answer names, or a `ValueError` saying what is missing."""
    answer = answer if isinstance(answer, dict) else {}
    picked = str(answer.get(MODEL_FIELD) or "").strip()
    typed = str(answer.get(CUSTOM_MODEL_FIELD) or "").strip()
    model = typed if picked == OTHER_MODEL or (typed and not picked) else picked
    if model == OTHER_MODEL:
        model = ""
    if not model:
        suggested = [str(m) for m in preset.get("suggested_models") or [] if str(m).strip()]
        if suggested:
            return suggested[0]
        raise ValueError(f"choose which {preset['name']} model this connection will use")
    if len(model) > 200:
        raise ValueError("a model id is at most 200 characters")
    return model
