"""OpenCode's OpenAPI document, and a validator small enough to read.

`app/facade/openapi.json` is their protocol's machine-readable definition,
copied from upstream `anomalyco/opencode` at commit `ad1a4a6`
(`packages/protocol/openapi.json`, MIT licence - see
`vendor/opencode/LICENSE`). It is the contract the facade is tested against:
a response that drifts from their schema fails here, not in their interface.

## Why a validator of our own

`jsonschema` happens to be installed on the machine this was written on, and
it is not a dependency of this project - `pyproject.toml` does not name it,
so a clean `pip install -e .[test]` does not have it, and a test that imported
it would pass here and fail in CI. Adding it would be a dependency arriving as
a side effect of a feature, which `AGENTS.md` asks not to happen. Their
document uses a small part of JSON Schema - `$ref`, types, `properties`,
`required`, `additionalProperties`, `anyOf`/`oneOf`/`allOf`, `enum`,
`pattern`, array items and numeric bounds - and those are implemented below.
A keyword this validator does not know is REPORTED as an error rather than
skipped, so a schema that grows a new rule fails loudly instead of passing by
default.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

OPENAPI = Path(__file__).resolve().parents[1] / "app" / "facade" / "openapi.json"
EVENT_CONTRACT = Path(__file__).resolve().parents[1] / "app" / "facade" / "event_contract.json"

#: Keywords that describe rather than constrain. Ignoring them cannot make an
#: invalid document pass.
ANNOTATIONS = frozenset(
    {
        "description",
        "title",
        "format",
        "contentMediaType",
        "contentEncoding",
        "default",
        "examples",
        "deprecated",
        "readOnly",
        "writeOnly",
        "$comment",
        "x-effect-stream",
    }
)

KNOWN = frozenset(
    {
        "$ref",
        "type",
        "enum",
        "const",
        "properties",
        "required",
        "additionalProperties",
        "patternProperties",
        "items",
        "prefixItems",
        "minItems",
        "maxItems",
        "anyOf",
        "oneOf",
        "allOf",
        "not",
        "pattern",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
    }
)


@lru_cache(maxsize=1)
def document() -> dict[str, Any]:
    return json.loads(OPENAPI.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def event_contract() -> dict[str, Any]:
    return json.loads(EVENT_CONTRACT.read_text(encoding="utf-8"))


def operation(operation_id: str) -> tuple[str, str, dict[str, Any]]:
    """`(METHOD, path, operation)` for an operation id in their document."""
    for path, methods in document()["paths"].items():
        for method, body in methods.items():
            if body.get("operationId") == operation_id:
                return method.upper(), path, body
    raise KeyError(f"{operation_id} is not in their OpenAPI document")


def operation_ids() -> set[str]:
    return {
        body["operationId"]
        for methods in document()["paths"].values()
        for body in methods.values()
        if "operationId" in body
    }


def response_schema(operation_id: str, status: int) -> dict[str, Any] | None:
    """The JSON schema for one status of one operation, or `None` if bodiless."""
    _method, _path, body = operation(operation_id)
    response = body["responses"].get(str(status))
    if response is None:
        raise KeyError(f"{operation_id} declares no {status} response")
    content = response.get("content") or {}
    media = content.get("application/json")
    return None if media is None else media.get("schema")


def component(name: str) -> dict[str, Any]:
    return document()["components"]["schemas"][name]


def _resolve(ref: str) -> dict[str, Any]:
    prefix = "#/components/schemas/"
    if not ref.startswith(prefix):
        raise KeyError(f"unsupported $ref {ref}")
    return component(ref[len(prefix):])


def _is_type(value: Any, kind: str) -> bool:
    if kind == "null":
        return value is None
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "string":
        return isinstance(value, str)
    if kind == "array":
        return isinstance(value, list)
    if kind == "object":
        return isinstance(value, dict)
    raise KeyError(f"unknown type {kind}")


def errors(value: Any, schema: Any, where: str = "$") -> list[str]:
    """Every way `value` fails `schema`. Empty means valid."""
    if schema is True or schema == {}:
        return []
    if schema is False:
        return [f"{where}: nothing is allowed here"]
    unknown = set(schema) - KNOWN - ANNOTATIONS
    if unknown:
        return [f"{where}: schema keyword(s) this validator does not know: {sorted(unknown)}"]
    found: list[str] = []
    if "$ref" in schema:
        found += errors(value, _resolve(schema["$ref"]), where)
    if "type" in schema:
        kinds = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(value, kind) for kind in kinds):
            return found + [f"{where}: expected {'/'.join(kinds)}, got {type(value).__name__} {value!r:.80}"]
    if "enum" in schema and value not in schema["enum"]:
        found.append(f"{where}: {value!r} is not one of {schema['enum']}")
    if "const" in schema and value != schema["const"]:
        found.append(f"{where}: {value!r} is not {schema['const']!r}")
    if "anyOf" in schema:
        branches = [errors(value, branch, where) for branch in schema["anyOf"]]
        if all(branches):
            found.append(f"{where}: matches no anyOf branch; nearest: {min(branches, key=len)}")
    if "oneOf" in schema:
        matching = [branch for branch in schema["oneOf"] if not errors(value, branch, where)]
        if len(matching) != 1:
            found.append(f"{where}: matches {len(matching)} oneOf branches, not exactly one")
    for branch in schema.get("allOf", []):
        found += errors(value, branch, where)
    if "not" in schema and not errors(value, schema["not"], where):
        found.append(f"{where}: matches a schema it must not")
    if isinstance(value, str):
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            found.append(f"{where}: {value!r:.80} does not match {schema['pattern']}")
        if "minLength" in schema and len(value) < schema["minLength"]:
            found.append(f"{where}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            found.append(f"{where}: longer than {schema['maxLength']}")
    if _is_type(value, "number"):
        if "minimum" in schema and value < schema["minimum"]:
            found.append(f"{where}: {value} < {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            found.append(f"{where}: {value} > {schema['maximum']}")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            found.append(f"{where}: {value} <= {schema['exclusiveMinimum']}")
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            found.append(f"{where}: {value} >= {schema['exclusiveMaximum']}")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                found.append(f"{where}: missing required {key!r}")
        patterns = schema.get("patternProperties", {})
        for key, item in value.items():
            if key in properties:
                found += errors(item, properties[key], f"{where}.{key}")
                continue
            matched = [p for p in patterns if re.search(p, key)]
            for pattern in matched:
                found += errors(item, patterns[pattern], f"{where}.{key}")
            if matched:
                continue
            extra = schema.get("additionalProperties", True)
            if extra is False:
                found.append(f"{where}: {key!r} is not allowed")
            elif isinstance(extra, dict):
                found += errors(item, extra, f"{where}.{key}")
    if isinstance(value, list):
        prefix = schema.get("prefixItems", [])
        for index, item in enumerate(value):
            if index < len(prefix):
                found += errors(item, prefix[index], f"{where}[{index}]")
            elif "items" in schema:
                found += errors(item, schema["items"], f"{where}[{index}]")
        if "minItems" in schema and len(value) < schema["minItems"]:
            found.append(f"{where}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            found.append(f"{where}: more than {schema['maxItems']} items")
    return found


def assert_response(test, operation_id: str, response, status: int = 200) -> Any:
    """Assert `response` has `status` and a body valid for that status."""
    test.assertEqual(response.status_code, status, f"{operation_id}: {response.text[:800]}")
    schema = response_schema(operation_id, status)
    if schema is None:
        test.assertIn(response.content, (b"", b"null"), f"{operation_id} {status} has no body")
        return None
    body = response.json()
    problems = errors(body, schema)
    test.assertEqual(problems, [], f"{operation_id} {status} does not match their schema")
    return body


def event_problems(event: dict[str, Any]) -> list[str]:
    """How one event breaks the envelope or the field contract, if it does.

    The envelope keys come from `event_contract.json`; so do the required and
    optional data fields of every event type the contract lists. A type the
    contract does not list (`session.created`, `session.inbox.enqueued`, ...)
    is checked for the envelope only - the contract names the events their
    session reducer reads field by field, and extending it is
    `scripts/extract_event_contract.py`'s job, not a test's.
    """
    contract = event_contract()
    found = []
    extra = set(event) - set(contract["envelope"])
    if extra:
        found.append(f"{event.get('type')}: envelope keys {sorted(extra)} are not theirs")
    for key in ("id", "type", "created", "data"):
        if key not in event:
            found.append(f"{event.get('type')}: envelope is missing {key!r}")
    if not str(event.get("id", "")).startswith("evt_"):
        found.append(f"{event.get('type')}: id {event.get('id')!r} does not start with evt_")
    shape = contract["events"].get(event.get("type"))
    if shape is not None:
        data = event.get("data") or {}
        for key in shape["required"]:
            if key not in data:
                found.append(f"{event['type']}: data is missing required {key!r}")
        allowed = set(shape["required"]) | set(shape["optional"])
        stray = set(data) - allowed
        if stray:
            found.append(f"{event['type']}: data carries {sorted(stray)}, which their schema does not")
    return found
