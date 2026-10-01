"""Whether a generated tool call COULD RUN. Stdlib only, no model, no network.

It mirrors the two refusals `app/tools/registry.py::Registry.call` performs -
unknown arguments, and required ones that did not arrive - plus the type and
enum checks `ToolSpec.as_control` already reads off the same JSON Schema. One
schema, two readers, and they cannot disagree about what a parameter is.

WHAT IT CANNOT TELL YOU. Whether the call is the RIGHT call. A perfectly formed
`list_runs()` in answer to "what is in my training file?" has no faults and is
the wrong tool. That question belongs to a judge, and a judge is a model with
an opinion. This one is arithmetic, and arithmetic is the only part of a
generation pipeline whose verdict is the same verdict tomorrow.

WHY IT IS ITS OWN MODULE. The same argument `recipes/hf-peft-dpo` makes for
splitting out `adapter_keys_in`: "the decision ... is the part that was wrong
twice, and it is the part a test suite running in an interpreter with no torch
and no safetensors can still exercise." Everything downstream of a synthetic
corpus depends on this verdict, so it is the piece that must be right on its
own merits, in a second, with nothing installed.

Written from `10-Signals/specs/synthetic-data.md`, whose every claim about this
repository's API was checked against the tree before this file was written:
`RESERVED_ARGUMENTS` and `INJECTED_ARGUMENTS` are importable from
`app.tools.registry`, and iterating `REGISTRY` yields `ToolSpec` objects
carrying `.name` and `.schema`.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

#: `scripts/` is not a package and this file is run directly, so the repository
#: root has to be on the path before `app` can be imported. The same three lines
#: open `scripts/capture_datawork_fixtures.py`; guarded, so importing this
#: module from `tests/` (where the root is already there) changes nothing.
REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

#: JSON Schema type -> what Python calls it after `json.loads`. `"null"` is
#: absent on purpose: a null in a generated call is a missing value wearing a
#: value's clothes, and it is reported as the missing parameter it is.
JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}


def the_tool_schemas_this_harness_ships() -> dict[str, dict[str, Any]]:
    """Every registered tool's JSON Schema, by name, read off the registry.

    The registry, not a copy of it. A second list of tool names in a script is
    a vocabulary that goes stale the first time somebody registers a tool.
    """
    from app.tools import REGISTRY

    return {spec.name: dict(spec.schema or {}) for spec in REGISTRY}


def why_this_tool_call_is_malformed(
    call: Mapping[str, Any],
    schemas: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """Every reason this call could not run, in order. Empty means well formed.

    EMPTY IS NOT "CORRECT". See the module docstring. Empty means the registry
    would accept the arguments, nothing more.
    """
    name = str(call.get("name") or "").strip()
    if not name:
        return ["no tool was named"]

    schema = schemas.get(name)
    if schema is None:
        near = difflib.get_close_matches(name, sorted(schemas), n=3)
        return [
            f"no tool called {name!r}"
            + (f"; nearest registered: {', '.join(near)}" if near else "")
        ]

    raw: Any = call.get("arguments")
    if isinstance(raw, str):
        # Models emit arguments as a JSON STRING as often as an object. Both
        # are accepted and the string is parsed, because a pipeline that
        # refused the string form would drop well-formed calls for a transport
        # detail.
        try:
            raw = json.loads(raw)
        except ValueError as error:
            return [f"arguments are not parseable JSON: {error}"]
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        return [f"arguments are a {type(raw).__name__}, not a JSON object"]

    properties: dict[str, Any] = dict(schema.get("properties") or {})
    required: set[str] = set(schema.get("required") or ())
    faults: list[str] = []

    # (1) Required parameters that did not arrive.
    for key in sorted(required - set(raw)):
        faults.append(f"required parameter {key!r} is missing")

    # (2) Parameters this tool does not have. Reserved and injected names get
    #     their own sentence: they are not merely unknown, they are names a
    #     call may never carry at all.
    from app.tools.registry import INJECTED_ARGUMENTS, RESERVED_ARGUMENTS

    for key in sorted(set(raw) - set(properties)):
        if str(key).lower() in RESERVED_ARGUMENTS or key in INJECTED_ARGUMENTS:
            faults.append(
                f"{key!r} is a reserved argument; no tool schema may accept it "
                "and the registry refuses a call that carries one"
            )
        else:
            faults.append(f"{key!r} is not a parameter of {name}")

    # (3) Types, and enums where the schema declares one.
    for key in sorted(set(raw) & set(properties)):
        value = raw[key]
        declared = str((properties[key] or {}).get("type") or "")
        allowed = JSON_TYPES.get(declared)

        if value is None:
            faults.append(
                f"{key!r} is null; {name} declares it "
                + (f"{declared}" if declared else "a value")
            )
            continue

        if allowed is None:
            pass  # the schema declared no type; there is nothing to check
        elif declared == "boolean":
            if not isinstance(value, bool):
                faults.append(
                    f"{key!r} is a {type(value).__name__}; {name} declares it boolean"
                )
        elif isinstance(value, bool):
            # `bool` IS a subclass of `int` in Python, so `isinstance(True,
            # int)` is True and a naive check would accept `{"count": true}`
            # as an integer. Caught here explicitly.
            faults.append(f"{key!r} is a boolean; {name} declares it {declared}")
        elif not isinstance(value, allowed):
            faults.append(
                f"{key!r} is a {type(value).__name__}; {name} declares it {declared}"
            )

        choices = (properties[key] or {}).get("enum")
        if choices and value not in choices:
            faults.append(f"{key!r} is {value!r}, which is not one of {list(choices)}")

    return faults


#: Days a rewrite can name. A weekday that was not in the real answer is a
#: commitment the shop never made.
_WEEKDAYS = frozenset(
    "monday tuesday wednesday thursday friday saturday sunday".split()
)

#: Currency, as a symbol or a code. `2.00` and `$2.00` are different claims and
#: the second was measured being invented - see the test that carries it.
_MONEY = re.compile(r"[£$€¥]|\b(?:GBP|USD|EUR)\b", re.I)

#: "I" is capitalised everywhere in English and names nobody. Counting it would
#: fire on any rewrite that moved to the first person, which is a style change
#: rather than an added fact. Found by measurement: without this exclusion one
#: of the three confabulated control pairs was "caught" on the strength of a
#: pronoun, which would have been a right answer for a wrong reason.
_NOT_A_NAME = frozenset(("I", "I'll", "I'm", "I've", "I'd"))


def the_specifics_in(text: str) -> set[tuple[str, str]]:
    """Numbers, money, weekdays, addresses and names, each tagged by kind.

    NARROW ON PURPOSE. This is not "what does the sentence mean" - that is the
    judge's question and it is the one that cannot be trusted. These are the
    categories a rewrite can *add* that turn a degraded answer into a fabricated
    one: a price the shop never quoted, a day it never promised, a name it never
    used. Everything else a rewrite does - dropping a condition, widening a
    limit - is the degradation itself and is invisible here, correctly.
    """
    found: set[tuple[str, str]] = set()
    found |= {("num", n) for n in re.findall(r"\d+(?:[.,]\d+)*", text or "")}
    found |= {("money", m.group(0).upper()) for m in _MONEY.finditer(text or "")}
    found |= {
        ("day", w.lower())
        for w in re.findall(r"[A-Za-z]+", text or "")
        if w.lower() in _WEEKDAYS
    }
    found |= {
        ("addr", a) for a in re.findall(r"\S+@\S+|https?://\S+", text or "")
    }
    for sentence in re.split(r"(?<=[.!?])\s+", text or ""):
        for index, token in enumerate(re.findall(r"[A-Za-z][A-Za-z'\-]*", sentence)):
            # `index` and not `0`: the first word of a sentence is capitalised
            # by grammar, so only a later capital is evidence of a name.
            if index and token[:1].isupper() and len(token) > 1:
                if token not in _NOT_A_NAME:
                    found.add(("name", token))
    return found


def specifics_the_rewrite_adds(chosen: str, rejected: str) -> list[tuple[str, str]]:
    """What the generated side names that the real answer never did.

    THIS IS THE JUDGE'S SECOND CLAUSE, MOVED INTO ARITHMETIC. The generator is
    told "do not add a new fact, a number, or a name that is not already in the
    source answer" and the judge was asked to police it. A judge's verdict is an
    opinion that can be different tomorrow; this is a set difference.

    Measured on 2026-09-03/04 over every row this repository had generated:
    it flagged 1 of 20 rows, and that one row was the fabrication a human had
    already found by hand - a `$` invented for a shop that writes plain `2.00`.
    Nineteen legitimate degradations passed. Over the 49 real-vs-real control
    pairs it caught 28 before any judge call was spent on them.
    """
    return sorted(the_specifics_in(rejected) - the_specifics_in(chosen))


def why_this_preference_pair_is_malformed(
    row: Mapping[str, Any],
    *,
    source_answer: str,
    fewest_chars: int = 8,
) -> list[str]:
    """Every reason this pair could not be trained on. Empty means well formed.

    Four checks, and the last is the one that enforces `docs/VISION.md`'s
    "structure, not content" at the ROW rather than in a docstring: the chosen
    side must be the source row's answer byte for byte. Only the rejected side
    may be generated.
    """
    faults: list[str] = []
    for field in ("prompt", "chosen", "rejected"):
        value = row.get(field)
        if not isinstance(value, str) or not value.strip():
            faults.append(f"{field!r} is missing or empty")
        elif len(value.strip()) < fewest_chars:
            faults.append(
                f"{field!r} is {len(value.strip())} characters, which is not an answer"
            )
    if faults:
        return faults
    if row["chosen"].strip() == row["rejected"].strip():
        faults.append(
            "chosen and rejected are the same string; there is no preference here"
        )
    if row["chosen"].strip() != source_answer.strip():
        faults.append(
            "chosen is not the source row's answer verbatim. Only the rejected "
            "side may be generated - docs/VISION.md, a right answer is copied, "
            "never invented"
        )
    invented = specifics_the_rewrite_adds(row["chosen"], row["rejected"])
    if invented:
        faults.append(
            "the rejected side names "
            + ", ".join(f"{kind} {value!r}" for kind, value in invented)
            + ", which the real answer never did. A degradation drops or widens "
            "what was there; naming something new makes it a fabrication rather "
            "than a worse answer"
        )
    return faults


def the_source_answer_behind(row: Mapping[str, Any]) -> tuple[str, str | None]:
    """The real answer this row's `chosen` is supposed to be, read off the file.

    WHY THIS EXISTS AND WHY IT IS NOT `row["chosen"]`. The verbatim check is the
    one that enforces "only the rejected side may be generated". Handing it the
    row's own `chosen` would compare a string to itself - a check that passes
    for every row ever written, including a row whose `chosen` a model rewrote,
    which is precisely the case it is there to catch.

    So the source is re-read. A stamped row names it: `provenance.source` holds
    the path, the row index and the answer field, and those three open the seed
    file at the line the row came from. A row that names no source cannot be
    checked this way and SAYS SO rather than being waved through.
    """
    provenance = row.get("provenance") or {}
    source = provenance.get("source") or {}
    path, index, field = (
        source.get("path"), source.get("row_index"), source.get("answer_field")
    )
    if not path or index is None or not field:
        return "", (
            "this row names no source, so 'chosen' cannot be checked against "
            "the answer it was copied from. Only a row stamped by "
            "scripts/generate_the_preference_pairs.py carries provenance.source"
        )
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        record = json.loads(lines[int(index)])
    except (OSError, ValueError, IndexError) as error:
        return "", (
            f"row {index} of {path} could not be read back "
            f"({type(error).__name__}), so 'chosen' cannot be checked against it"
        )
    return str(record.get(field) or ""), None


def _main(argv: list[str] | None = None) -> int:
    """Check a JSONL file of generated rows and report, one line per fault.

    Reports rather than deletes. A generation run whose bad rows were silently
    dropped is a run whose keep rate cannot be read afterwards, and the keep
    rate is the number that says whether the generator is worth running again.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path, help="JSONL of generated rows")
    parser.add_argument(
        "--kind",
        choices=("tool_call", "preference_pair"),
        default="tool_call",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    schemas = the_tool_schemas_this_harness_ships() if args.kind == "tool_call" else {}
    kept = 0
    total = 0
    for line in args.path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        total += 1
        row = json.loads(line)
        if args.kind == "tool_call":
            faults = why_this_tool_call_is_malformed(row, schemas)
        else:
            source_answer, why_not = the_source_answer_behind(row)
            if why_not:
                faults = [why_not]
            else:
                faults = why_this_preference_pair_is_malformed(
                    row, source_answer=source_answer
                )
        if faults:
            print(f"row {total}: " + "; ".join(faults))
        else:
            kept += 1
    # The denominator is printed with the numerator, always. A keep rate with
    # no denominator is the kind of number this repository refuses everywhere
    # else.
    print(f"\n{kept} of {total} rows are well formed")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
