"""Did the outputs come back in the right shape? The one stage with no builds.

## What was measured, and why this module exists

`docs/PHASES.md` step 8 asks for the ML stages that state outcomes and offer no
build at all. `stage_4_format` was the worst of the four and its reason was not
a missing proposer:

> **ACTION__MEASURE_THE_FORMAT** - two facts that cannot enter the ledger by any
> route. `schema_compliance` is declared `source: inspect` and
> `schema_expressible` `source: derive`, and BOTH admit MEASURED only - so the
> person cannot state them - while no registered tool declares `measures=` for
> either, so nothing can measure them. **The engine asks for two numbers the
> harness will not accept from the only party who has them.** That is a real
> hole and it is upstream of this file: it closes when a tool measures
> `schema_compliance`, not when a proposer is written.

This is that tool. Every node in `stage_4_format` reads one of those two facts,
so a null in either made all of them false and the stage ran off the end - at
exactly the people who had already turned structured outputs on and wanted to
know what it achieved.

## What it reads, and what it refuses to guess

A file of the outputs the person's system produced, one per row, and a JSON
Schema they name. It counts the fraction that satisfy the schema. That is a
count over rows on a disk: no model is called, nothing is sent anywhere, and
the number is a reading rather than a judgement.

**IT WILL NOT INVENT THE SCHEMA.** Inferring one from the outputs would be
measuring compliance against a shape derived from the very outputs being
graded, which scores 100% by construction and means nothing. The schema is the
person's statement of what they wanted; a harness that guessed it would be
answering a question nobody asked.

## THE VALIDATOR IS A DECLARED SUBSET, AND THE SUBSET IS THE HONEST PART

There is no JSON Schema library in this project's dependencies and this module
does not add one - a dependency is a decision, and `docs/PHASES.md` records
that decision being made deliberately twice. So the checker here understands a
stated subset of draft-2020-12, in `SUPPORTED`, and **refuses a schema using
anything outside it** rather than ignoring the keyword and reporting a number.

That refusal is the whole reason a subset is acceptable. A validator that
silently skipped `allOf` would report 100% compliance for a schema whose
hardest half it never checked, which is a fabricated number with a real
provenance chain - the exact failure `app/tools/evidence.py`'s walls exist for.
A validator that says "this schema uses `allOf` and I do not implement it,
nothing was measured" costs the person a sentence and costs them nothing else.

## What it does NOT close, said here rather than discovered later

`schema_expressible` - *could a schema express the target shape at all* - is
still unobtainable and this module does not pretend otherwise. It is a
judgement about the person's own requirements, declared `source: derive` with
NO ENTRY IN THE LEDGER'S `derived:` BLOCK, so nothing derives it, no instrument
can read it, and its origin rule admits MEASURED only, so the person cannot
state it either. That is a defect in the fact's declaration rather than a gap
in this harness, it is written down in `docs/PHASES.md`, and it is not fixed by
a tool.

So `ACTION__MEASURE_THE_FORMAT` is half-closed by this file, and the half that
is closed is the half the stage's own `asks:` sentence puts first.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from app import diagnosis
from app.tools.evidence import Instrument
from app.tools.registry import tool

#: The JSON Schema keywords this validator implements. A schema using anything
#: else is REFUSED rather than partially checked - see the module docstring.
#: Chosen as the closure of "what a structured-output schema for an LLM call
#: actually says": a shape, its fields, which are required, and their types.
SUPPORTED: frozenset[str] = frozenset(
    {
        "type",
        "properties",
        "required",
        "items",
        "enum",
        "const",
        "additionalProperties",
        # Annotation-only in every draft. Carried through so a person's schema
        # does not have to be stripped of its documentation to be checkable.
        "title",
        "description",
        "$schema",
        "$id",
        "examples",
        "default",
    }
)

#: JSON Schema's type names, mapped to what Python calls the same thing. `int`
#: is not in the `number` row by accident: JSON has one numeric type and
#: `json.loads("1")` gives an `int`, so a schema saying `number` that refused
#: `1` would be refusing valid JSON.
_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
    "null": (type(None),),
}

#: How many failing rows come back in the report. A refusal that returned every
#: row would be the file again; a refusal that returned none would be a number
#: with nothing to look at.
EXAMPLES_SHOWN = 5


class SchemaError(ValueError):
    """The schema itself cannot be checked. Distinct from a row failing it."""


def unsupported_keywords(schema: Any, path: str = "$") -> list[str]:
    """Every keyword in this schema this validator does not implement.

    Walked rather than checked at the top level, because the keyword that would
    silently change the answer is usually nested: `{"type": "object",
    "properties": {"x": {"anyOf": [...]}}}` is a schema whose top level is
    entirely supported and whose meaning this module cannot compute.
    """
    found: list[str] = []
    if isinstance(schema, Mapping):
        for key, value in schema.items():
            name = str(key)
            if name not in SUPPORTED:
                found.append(f"{path}.{name}")
                continue
            if name == "properties" and isinstance(value, Mapping):
                for field, sub in value.items():
                    found.extend(unsupported_keywords(sub, f"{path}.properties.{field}"))
            elif name == "items":
                found.extend(unsupported_keywords(value, f"{path}.items"))
            elif name == "additionalProperties" and isinstance(value, Mapping):
                found.extend(
                    unsupported_keywords(value, f"{path}.additionalProperties")
                )
    return found


def check_schema(schema: Any) -> Mapping[str, Any]:
    """The schema, or a refusal naming what it uses that this cannot check."""
    if not isinstance(schema, Mapping):
        raise SchemaError(
            "a JSON Schema is an object. This file holds "
            f"{type(schema).__name__}, so there is nothing here to check "
            "outputs against."
        )
    unsupported = unsupported_keywords(schema)
    if unsupported:
        raise SchemaError(
            f"this schema uses {sorted(unsupported)}, and this harness does not "
            "implement those keywords. NOTHING WAS MEASURED, deliberately: a "
            "checker that skipped them would report a compliance figure for a "
            "schema whose hardest half it never looked at, which is a made-up "
            "number with a real provenance chain behind it. What is implemented "
            f"is: {', '.join(sorted(SUPPORTED))}. Simplify the schema to those, "
            "or measure this fraction with your own validator and tell the "
            "harness what you found."
        )
    return schema


def _fails(value: Any, schema: Mapping[str, Any], where: str = "$") -> str | None:
    """Why this value does not satisfy this schema, or None when it does.

    A sentence rather than a boolean, because the report shows the first few
    failures and *"expected object, saw string"* is what tells somebody their
    model is wrapping the JSON in prose.
    """
    if "const" in schema and value != schema["const"]:
        return f"{where}: expected the constant {schema['const']!r}, saw {value!r}"

    if "enum" in schema:
        allowed = list(schema["enum"] or ())
        if value not in allowed:
            return f"{where}: {value!r} is not one of {allowed!r}"

    declared = schema.get("type")
    if declared is not None:
        wanted = [declared] if isinstance(declared, str) else list(declared)
        # `True` is an `int` in Python and is not a number in JSON. Checked
        # before the type table, because `isinstance(True, int)` would let a
        # boolean satisfy `{"type": "integer"}` and that is a real output shape
        # a model produces.
        ok = False
        for name in wanted:
            kinds = _TYPES.get(str(name))
            if kinds is None:
                return f"{where}: the schema names an unknown type {name!r}"
            if type(value) is bool and str(name) in ("number", "integer"):
                continue
            if isinstance(value, kinds):
                ok = True
                break
        if not ok:
            return (
                f"{where}: expected {' or '.join(str(n) for n in wanted)}, saw "
                f"{_names(value)}"
            )

    if isinstance(value, Mapping):
        properties = schema.get("properties") or {}
        for name in schema.get("required") or ():
            if str(name) not in value:
                return f"{where}: required field {str(name)!r} is missing"
        for name, sub in properties.items():
            if str(name) in value and isinstance(sub, Mapping):
                failure = _fails(value[str(name)], sub, f"{where}.{name}")
                if failure:
                    return failure
        extra = schema.get("additionalProperties")
        if extra is False:
            unknown = sorted(set(map(str, value)) - set(map(str, properties)))
            if unknown:
                return f"{where}: fields not in the schema: {unknown}"

    if isinstance(value, list):
        items = schema.get("items")
        if isinstance(items, Mapping):
            for index, item in enumerate(value):
                failure = _fails(item, items, f"{where}[{index}]")
                if failure:
                    return failure

    return None


def _names(value: Any) -> str:
    """What JSON calls this value's type, for a sentence a person reads."""
    for name, kinds in _TYPES.items():
        if type(value) is bool:
            return "boolean"
        if isinstance(value, kinds):
            return name
    return type(value).__name__


def _outputs(path: Path, field: str) -> Iterable[tuple[int, Any, str | None]]:
    """Each row's output, as `(row number, parsed value, why not)`.

    THE PARSE IS PART OF THE MEASUREMENT AND NOT A PRECONDITION. A model that
    returns `"Sure! Here is the JSON: {...}"` has failed the format, and a row
    that is not JSON at all is a row that did not comply - counted as a failure
    with that sentence, never skipped. Skipping it would compute the fraction
    over the rows that already parsed, which is the number that always looks
    good.
    """
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError as error:
                yield number, None, f"row {number} is not JSON: {error.msg}"
                continue
            if not isinstance(row, Mapping) or field not in row:
                yield number, None, (
                    f"row {number} has no {field!r} field, so there is no output "
                    "on it to check"
                )
                continue
            raw = row[field]
            if isinstance(raw, str):
                try:
                    yield number, json.loads(raw), None
                except json.JSONDecodeError as error:
                    yield number, None, (
                        f"row {number}: the output is text rather than JSON "
                        f"({error.msg})"
                    )
                continue
            yield number, raw, None


@tool(
    "measure_the_format",
    description=(
        "Count what fraction of your system's outputs come back in the shape "
        "your schema asks for. Reads a file of outputs and a JSON Schema you "
        "name, both on this machine. Calls no model and sends nothing "
        "anywhere. This is the number stage 4 of the diagnosis is waiting for."
    ),
    schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "JSONL file of the outputs your system produced, one row "
                    "per output."
                ),
            },
            "output_field": {
                "type": "string",
                "description": (
                    "Which column on each row holds the output to check. "
                    "Default: output."
                ),
            },
            "schema_path": {
                "type": "string",
                "description": (
                    "The JSON Schema file the outputs are supposed to satisfy. "
                    "Yours - this harness will not infer one."
                ),
            },
        },
        "required": ["path", "schema_path"],
    },
    reads=("filesystem", "datasets"),
    writes=("facts",),
    measures=("schema_compliance",),
    subject=("path",),
    provides=("measurement.format.score",),
    label="Measure the format",
    group="Measure",
    verb="count how many outputs match your schema",
    order=46,
)
def measure_the_format(
    path: str,
    schema_path: str,
    output_field: str = "output",
    *,
    instrument: Instrument,
    ledger: diagnosis.Spec,
) -> dict[str, Any]:
    """The fraction of outputs that satisfy the schema, and which ones did not.

    THE DENOMINATOR IS EVERY ROW IN THE FILE, and that is the decision worth
    reading. A row that is not JSON, a row whose output field is missing, a row
    that is prose with a brace in it - each is a row where the format did not
    come back right, so each counts against. Computing the fraction over "the
    rows that parsed" would be a compliance figure that rises as the system
    gets worse, because the rows it fails hardest on are the ones it would
    drop.
    """
    source = Path(str(path)).expanduser()
    schema_file = Path(str(schema_path)).expanduser()
    field = str(output_field or "output").strip() or "output"

    for named, what in ((source, "outputs"), (schema_file, "schema")):
        if not named.is_file():
            return {
                "ok": False,
                "error": "no_such_file",
                "summary": (
                    f"There is no {what} file at {named}. Nothing was measured "
                    "and nothing was recorded."
                ),
            }

    try:
        declared = check_schema(json.loads(schema_file.read_text(encoding="utf-8")))
    except json.JSONDecodeError as error:
        return {
            "ok": False,
            "error": "schema_is_not_json",
            "summary": f"{schema_file} is not valid JSON: {error.msg}.",
        }
    except SchemaError as error:
        return {
            "ok": False,
            "error": "schema_not_supported",
            "summary": str(error),
            "supported": sorted(SUPPORTED),
        }

    total = passed = 0
    failures: list[dict[str, Any]] = []
    for number, value, why_not in _outputs(source, field):
        total += 1
        reason = why_not or _fails(value, declared)
        if reason is None:
            passed += 1
        elif len(failures) < EXAMPLES_SHOWN:
            failures.append({"row": number, "why": reason})

    if total == 0:
        return {
            "ok": False,
            "error": "no_rows",
            "summary": (
                f"{source} holds no rows, so there is no fraction to compute. "
                "A compliance figure over nothing is not zero, it is undefined, "
                "and nothing was recorded."
            ),
        }

    fraction = passed / total
    measured = instrument.measured(
        "schema_compliance",
        fraction,
        how=(
            f"checked {total} output(s) in {source} against the schema in "
            f"{schema_file}; {passed} satisfied it"
        ),
        from_file=str(source),
    )
    return {
        "ok": True,
        "path": str(source),
        "schema_path": str(schema_file),
        "output_field": field,
        "outputs": total,
        "satisfied": passed,
        "schema_compliance": fraction,
        "first_failures": failures,
        "checked_with": (
            "this harness's own checker, which implements "
            f"{', '.join(sorted(SUPPORTED))} and refuses a schema using "
            "anything else rather than skipping it"
        ),
        "measured": [measured],
        "what_now": (
            "Re-run the diagnosis. Stage 4 also wants schema_expressible - "
            "whether a schema could express your target shape at all - and "
            "nothing here can read that; it is a judgement about your own "
            "requirements."
        ),
    }


__all__ = [
    "EXAMPLES_SHOWN",
    "SUPPORTED",
    "SchemaError",
    "check_schema",
    "measure_the_format",
    "unsupported_keywords",
]
