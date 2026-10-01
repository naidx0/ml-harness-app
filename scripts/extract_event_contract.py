"""Snapshot the event fields OpenCode's client reads, from their schema package.

    python scripts/extract_event_contract.py

Writes `app/facade/event_contract.json`: for each event the facade sends, the
data fields their client requires and the ones it accepts. The facade builds
events against it and the facade's tests assert against it, so the Python gate
never has to parse TypeScript.

The source is `@opencode/schema/dist/event-manifest.d.ts` at whatever version
the workspace installed - which `web/package.json` pins exactly to upstream's
catalog. Re-run after an upgrade and review the diff: a field that appears or
moves from optional to required is a protocol change the facade must follow.

THE PARSER CHECKS ITSELF BEFORE IT WRITES. Two earlier versions printed
plausible, wrong output: one swallowed braces with a greedy value capture and
reported nested fields as top-level; the next counted `<` and `>` as depth and
was thrown by the `=>` in their branded-type signatures. The assertions at the
bottom are cases read by eye from the declaration file. If a future layout
change breaks the scan, the script refuses rather than writing a contract that
looks right.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PACKAGE = REPO / "node_modules" / "@opencode" / "schema"
OUT = REPO / "app" / "facade" / "event_contract.json"

EVENTS = (
    "session.step.started",
    "session.step.ended",
    "session.step.failed",
    "session.text.started",
    "session.text.ended",
    "session.tool.input.started",
    "session.tool.called",
    "session.tool.success",
    "session.tool.failed",
    "session.reasoning.started",
    "session.reasoning.delta",
    "session.reasoning.ended",
    "session.execution.interrupted",
    "session.execution.failed",
    "permission.asked",
    "permission.replied",
)

FIELD = re.compile(r"[{}]|readonly (\w+)(\?)?:")


def data_body(text: str, event: str) -> str:
    start = text.find(f'type: "{event}";')
    if start < 0:
        sys.exit(f"{event} is not in the manifest - has their event vocabulary changed?")
    struct = text.find("data: Schema.Struct<{", start)
    if struct < 0 or struct - start > 2000:
        sys.exit(f"{event}: no data struct near its type literal - layout changed?")
    open_brace = text.find("{", struct)
    depth = 0
    for end in range(open_brace, len(text)):
        if text[end] == "{":
            depth += 1
        elif text[end] == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace + 1 : end]
    sys.exit(f"{event}: unbalanced braces")


def fields(body: str) -> list[tuple[str, bool]]:
    """Top-level keys and whether each is optional.

    BRACES ONLY for depth. The value text between two keys is sliced out
    afterwards, never consumed by the scan, so no brace is ever skipped.
    """
    marks: list[tuple[str, int, bool]] = []
    depth = 0
    for match in FIELD.finditer(body):
        token = match.group(0)
        if token == "{":
            depth += 1
        elif token == "}":
            depth -= 1
        elif depth == 0:
            marks.append((match.group(1), match.end(), bool(match.group(2))))
    out = []
    for index, (name, start, question) in enumerate(marks):
        stop = marks[index + 1][1] if index + 1 < len(marks) else len(body)
        value = body[start:stop].lstrip()
        optional = question or value.startswith(("Schema.optional", "Schema.decodeTo<Schema.optional"))
        out.append((name, optional))
    return out


def main() -> int:
    version = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))["version"]
    text = (PACKAGE / "dist" / "event-manifest.d.ts").read_text(encoding="utf-8")

    contract: dict[str, dict[str, list[str]]] = {}
    for event in EVENTS:
        found = fields(data_body(text, event))
        contract[event] = {
            "required": [name for name, optional in found if not optional],
            "optional": [name for name, optional in found if optional],
        }

    def every(event: str) -> set[str]:
        return set(contract[event]["required"]) | set(contract[event]["optional"])

    checks = [
        ({"agent", "model", "sessionID"} <= every("session.step.started"),
         "step.started must carry agent, model and sessionID"),
        (not ({"id", "providerID"} & every("session.step.started")),
         "model's nested id/providerID leaked to the top level"),
        ("uri" not in every("session.tool.success"),
         "tool content's nested uri leaked to the top level"),
        ({"action", "resources", "id"} <= every("permission.asked"),
         "permission.asked must carry action, resources and id"),
        ("ordinal" in every("session.text.ended"),
         "text events are keyed by ordinal within a message"),
    ]
    failed = [message for ok, message in checks if not ok]
    if failed:
        print("REFUSING TO WRITE: the parser does not reproduce known cases.")
        for message in failed:
            print("  " + message)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "//": "GENERATED by scripts/extract_event_contract.py. Do not edit.",
                "source": f"@opencode/schema@{version}",
                "envelope": ["id", "type", "created", "durable", "location", "data"],
                "events": contract,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {OUT.relative_to(REPO)} from @opencode/schema@{version}: {len(contract)} events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
