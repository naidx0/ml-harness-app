"""The same twenty systems, asked for with one worked example.

CORRECTION, 2026-09-09, AND IT IS TO THIS FILE'S OWN CLAIM.

The commit that shipped this file (e6af71c) says "one worked example takes node
labels from 50% to 80%". The direction was right and the ATTRIBUTION WAS WRONG.

INSTRUCTION below changes TWO things against BASE_INSTRUCTION, not one: it adds
a worked example, and it adds a naming rule -- "Name EVERY component the
description mentions, including the client or caller at one end and the store at
the other." The Practical ML lane's ladder separated them and measured the
sentence alone at 79% against a 53% bare arm, with one, two and three examples
landing at 80, 81, 80. The sentence carries about 26 of the 27 available points;
the examples carry approximately nothing. An example about making a cheese
omelette scored 79%, which is what you see when an example teaches nothing.

WHY I MISSED IT, because the shape recurs. The docstring below says "the ONLY
difference is the instruction, so a difference in score is attributable to the
instruction rather than to which systems were picked" -- and that is true and
was carefully done. I controlled the rows, the order, the expected graphs and
the model, and then changed two variables inside the one thing I was varying. A
paired design is not a controlled one if the treatment is a bundle.

The file is kept as it is. It is the artefact the corrected reading is about,
and rewriting it would leave the correction describing something that no longer
exists.


WHY: `G2_PROMPT_EXHAUSTED` is the gate between here and any training verdict,
and the engine is right to put it there. Both arms of the constrained /
unconstrained run scored about 50% on node labels with a bare instruction. If a
single worked example moves that, the content gap is a prompting gap and no
training is warranted; if it does not, the gap is real and the training question
becomes worth asking.

PAIRED ON PURPOSE. Same twenty descriptions, same expected graphs, same row
order, same model. The ONLY difference is the instruction, so a difference in
score is attributable to the instruction rather than to which systems were
picked. A fresh sample would have confounded the thing under test with the draw.

THE EXAMPLE IS NOT ONE OF THE TWENTY. It is a system that appears nowhere in the
held-out set -- a print queue -- because showing the model one of the rows it is
about to be scored on measures memory rather than instruction.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).parent

# A worked example, deliberately from outside the set.
EXAMPLE_IN = "A workstation sends print jobs to a print service, which queues them and dispatches to a printer."
EXAMPLE_OUT = json.dumps(
    {
        "nodes": [
            {"id": "printer", "label": "Printer", "kind": "service"},
            {"id": "queue", "label": "Print queue", "kind": "queue"},
            {"id": "svc", "label": "Print service", "kind": "service"},
            {"id": "ws", "label": "Workstation", "kind": "client"},
        ],
        "edges": [
            {"from": "svc", "to": "queue"},
            {"from": "queue", "to": "printer"},
            {"from": "ws", "to": "svc"},
        ],
    },
    separators=(",", ":"),
    ensure_ascii=False,
)

INSTRUCTION = (
    "Return ONLY a JSON object with two keys: nodes and edges. "
    'Each node is {"id","label","kind"} where kind is one of '
    "service, datastore, queue, gateway, client, job, cache. "
    'Each edge is {"from","to"} using node ids, optionally with "label". '
    "No prose, no markdown fence.\n\n"
    "Name EVERY component the description mentions, including the client or "
    "caller at one end and the store at the other. Use the words the "
    "description itself uses for each part.\n\n"
    "Example.\n"
    "Description: " + EXAMPLE_IN + "\n"
    "Answer: " + EXAMPLE_OUT + "\n\n"
    "Now do the same for this description."
)

BASE_INSTRUCTION = (
    "Return ONLY a JSON object with two keys: nodes and edges. "
    'Each node is {"id","label","kind"} where kind is one of '
    "service, datastore, queue, gateway, client, job, cache. "
    'Each edge is {"from","to"} using node ids, optionally with "label". '
    "No prose, no markdown fence."
)


def main() -> int:
    src = HERE / "held-out.jsonl"
    rows = [json.loads(line) for line in src.open(encoding="utf-8") if line.strip()]

    out_rows = []
    for row in rows:
        description = row["input"]
        if not description.endswith(BASE_INSTRUCTION):
            print("REFUSING: row " + str(row["row_id"]) + " does not end with the base instruction, "
                  "so stripping it would change the description rather than the ask.")
            return 1
        description = description[: -len(BASE_INSTRUCTION)].strip()
        if EXAMPLE_IN.lower() in description.lower():
            print("REFUSING: the worked example appears in row " + str(row["row_id"]))
            return 1
        out_rows.append(
            {
                "row_id": row["row_id"],
                "input": description + " " + INSTRUCTION,
                "expected": row["expected"],
                "node_labels": row["node_labels"],
                "edge_count": row["edge_count"],
            }
        )

    out = HERE / "held-out-fewshot.jsonl"
    with out.open("w", encoding="utf-8", newline=chr(10)) as handle:
        for row in out_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + chr(10))

    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print("rows: " + str(len(out_rows)))
    print("expected graphs identical to the base set: "
          + str(all(a["expected"] == b["expected"] for a, b in zip(rows, out_rows))))
    print("row order identical: "
          + str([r["row_id"] for r in rows] == [r["row_id"] for r in out_rows]))
    print("worked example appears in no row: checked, 0 of " + str(len(out_rows)))
    print("sha256: " + digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
