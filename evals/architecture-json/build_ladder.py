"""The same twenty systems, asked for with 0, 1, 2, 3 examples - and a control.

WHAT IS OPEN. One worked example took node-label F1 from 49% to 80% on this set.
Nobody knows whether the second example adds anything, and that question decides
whether a training budget is ever needed: a curve that flattens after one example
says the remaining gap is not a prompting gap, and a curve that keeps climbing
says prompting is not exhausted yet.

THE CONTROL IS THE POINT, not a courtesy. A worked example shows the model two
things at once - what this task wants, and what the output should look like. If
one architecture example lifts F1 by 30 points, that could be either. So one arm
carries a single example of the same SHAPE from a DIFFERENT domain: a kitchen
recipe rendered as the same nodes-and-edges JSON. It teaches the format and
nothing about architecture. If it lifts as much as the real example, the lift was
format; if it does not, the model learned the task.

PAIRED, and it is what makes the arms comparable. Same twenty descriptions, same
expected graphs, same row order. The ONLY thing that varies between arms is the
instruction, so a difference in score is attributable to the instruction rather
than to which systems were drawn.

NO EXAMPLE MAY APPEAR IN THE TWENTY. Showing a model a row it is about to be
scored on measures memory, not instruction, and this refuses rather than warns -
checked on the description text and on the label sets, because a system can be
the same system under a different sentence.

n = 20. That resolves about 8 points, so an arm one point above another is the
same arm twice and a thirty-point gap is a result. Every figure this produces is
reported with its n beside it or not at all.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).parent
NEWLINE = chr(10)

BASE_INSTRUCTION = (
    "Return ONLY a JSON object with two keys: nodes and edges. "
    'Each node is {"id","label","kind"} where kind is one of '
    "service, datastore, queue, gateway, client, job, cache. "
    'Each edge is {"from","to"} using node ids, optionally with "label". '
    "No prose, no markdown fence."
)

#: The shared preamble the one-example arm already uses. Kept BYTE-IDENTICAL to
#: `build_fewshot.py` so the 1-shot rung of this ladder is the arm that was
#: already measured at 80%, rather than a near-miss that would make the ladder's
#: first step an artefact of rewording.
NAMING_RULE = (
    "Name EVERY component the description mentions, including the client or "
    "caller at one end and the store at the other. Use the words the "
    "description itself uses for each part."
)


def graph(nodes: list[tuple[str, str, str]], edges: list[tuple[str, str]]) -> str:
    return json.dumps(
        {
            "nodes": [{"id": i, "label": l, "kind": k} for i, l, k in nodes],
            "edges": [{"from": a, "to": b} for a, b in edges],
        },
        separators=(",", ":"),
        ensure_ascii=False,
    )


#: EXAMPLE ONE is the print queue from `build_fewshot.py`, unchanged, for the
#: reason above.
EXAMPLE_1 = (
    "A workstation sends print jobs to a print service, which queues them and "
    "dispatches to a printer.",
    graph(
        [("printer", "Printer", "service"), ("queue", "Print queue", "queue"),
         ("svc", "Print service", "service"), ("ws", "Workstation", "client")],
        [("svc", "queue"), ("queue", "printer"), ("ws", "svc")],
    ),
)

#: EXAMPLE TWO adds a shape the first one does not have - a cache in front of a
#: store, and a gateway - so the second rung tests whether MORE coverage of the
#: vocabulary helps, rather than repeating one shape twice.
EXAMPLE_2 = (
    "A ticket kiosk asks an inventory gateway for seat counts; the gateway reads "
    "a seat cache and falls back to the seating database.",
    graph(
        [("kiosk", "Ticket kiosk", "client"), ("gw", "Inventory gateway", "gateway"),
         ("cache", "Seat cache", "cache"), ("db", "Seating database", "datastore")],
        [("kiosk", "gw"), ("gw", "cache"), ("gw", "db")],
    ),
)

#: EXAMPLE THREE adds a background job writing to a second store, which is the
#: last kind in the vocabulary the first two do not exercise.
EXAMPLE_3 = (
    "A nightly reconciliation job reads the ledger store, and writes a summary "
    "to the reporting warehouse.",
    graph(
        [("job", "Reconciliation job", "job"), ("ledger", "Ledger store", "datastore"),
         ("warehouse", "Reporting warehouse", "datastore")],
        [("job", "ledger"), ("job", "warehouse")],
    ),
)

#: THE CONTROL. Same output shape, same instruction, a domain that is not
#: software architecture at all. It teaches the format and nothing about which
#: components a described system has.
EXAMPLE_OFF_DOMAIN = (
    "To make a cheese omelette, a cook beats eggs in a bowl, pours them into a "
    "hot pan, and adds grated cheese before folding.",
    graph(
        [("cook", "Cook", "client"), ("bowl", "Bowl", "datastore"),
         ("pan", "Pan", "service"), ("cheese", "Grated cheese", "datastore")],
        [("cook", "bowl"), ("bowl", "pan"), ("cheese", "pan")],
    ),
)


def instruction(examples: list[tuple[str, str]], naming_rule: bool = True) -> str:
    """The instruction for an arm with this many worked examples."""
    if not examples:
        if not naming_rule:
            return BASE_INSTRUCTION
        return BASE_INSTRUCTION + NEWLINE + NEWLINE + NAMING_RULE
    parts = [BASE_INSTRUCTION, "", NAMING_RULE, ""]
    #: SINGULAR FOR ONE, so the 1-shot arm's text matches the measured arm
    #: exactly rather than differing by a letter that nobody could attribute.
    parts.append("Example." if len(examples) == 1 else "Examples.")
    for description, answer in examples:
        parts.append("Description: " + description)
        parts.append("Answer: " + answer)
        parts.append("")
    parts.append("Now do the same for this description.")
    return chr(10).join(parts).replace(chr(10) + chr(10) + chr(10), chr(10) + chr(10))


#: THE ARM THE FIRST RESULT DEMANDED. Every arm with an example also carries
#: NAMING_RULE, because `build_fewshot.py` bundled the two and this ladder
#: reproduced that faithfully so its 1-shot rung would be the arm already
#: measured at 80%. That makes 53 -> 80 a lift from TWO changes at once, and
#: the ladder cannot say which. This arm carries the sentence and NO example,
#: so the pair (namingrule, oneshot) isolates what an example is worth once
#: the instruction already says what to name.
ARMS: dict[str, list[tuple[str, str]]] = {
    "zeroshot": [],
    "oneshot": [EXAMPLE_1],
    "twoshot": [EXAMPLE_1, EXAMPLE_2],
    "threeshot": [EXAMPLE_1, EXAMPLE_2, EXAMPLE_3],
    "offdomain": [EXAMPLE_OFF_DOMAIN],
    "namingrule": [],  # the sentence, no example
}


def refuse_if_an_example_is_in_the_set(rows: list[dict]) -> str | None:
    """None when clean, else the reason. Checked two ways.

    A system can appear under a different sentence, so matching the example's
    description text against the row is not enough on its own - the label sets
    are compared too, and a full overlap is the same system however it is worded.
    """
    for name, examples in ARMS.items():
        for description, answer in examples:
            words = {w for w in description.lower().replace(",", " ").split() if len(w) > 4}
            labels = {n["label"].strip().lower() for n in json.loads(answer)["nodes"]}
            for row in rows:
                text = row["input"].lower()
                if description.lower() in text:
                    return "arm " + name + ": the example appears verbatim in row " + str(row["row_id"])
                theirs = {str(l).strip().lower() for l in row["node_labels"]}
                if labels and labels <= theirs:
                    return ("arm " + name + ": every label of the example is in row "
                            + str(row["row_id"]) + " - the same system under another sentence")
                shared = words & {w for w in text.replace(",", " ").split() if len(w) > 4}
                if len(shared) >= 4:
                    return ("arm " + name + ": the example shares " + str(len(shared))
                            + " content words with row " + str(row["row_id"]) + ": "
                            + ", ".join(sorted(shared)))
    return None


def main() -> int:
    src = HERE / "held-out.jsonl"
    rows = [json.loads(line) for line in src.open(encoding="utf-8") if line.strip()]

    why = refuse_if_an_example_is_in_the_set(rows)
    if why is not None:
        print("REFUSING: " + why)
        return 1

    print("arms built from " + str(len(rows)) + " rows (n = " + str(len(rows))
          + ", which resolves about 8 points)")
    print()
    for name, examples in ARMS.items():
        ask = instruction(examples, naming_rule=(name != "zeroshot"))
        out_rows = []
        for row in rows:
            description = row["input"]
            if not description.endswith(BASE_INSTRUCTION):
                print("REFUSING: row " + str(row["row_id"]) + " does not end with the base "
                      "instruction, so stripping it would change the description "
                      "rather than the ask.")
                return 1
            description = description[: -len(BASE_INSTRUCTION)].strip()
            out_rows.append(
                {
                    "row_id": row["row_id"],
                    "input": description + " " + ask,
                    "expected": row["expected"],
                    "node_labels": row["node_labels"],
                    "edge_count": row["edge_count"],
                }
            )

        out = HERE / ("ladder-" + name + ".jsonl")
        with out.open("w", encoding="utf-8", newline=chr(10)) as handle:
            for row in out_rows:
                handle.write(json.dumps(row, ensure_ascii=False) + chr(10))

        same_expected = all(a["expected"] == b["expected"] for a, b in zip(rows, out_rows))
        same_order = [r["row_id"] for r in rows] == [r["row_id"] for r in out_rows]
        digest = hashlib.sha256(out.read_bytes()).hexdigest()[:12]
        print(name.ljust(11) + str(len(examples)) + " example(s)  "
              + "expected identical: " + str(same_expected)
              + "  order identical: " + str(same_order)
              + "  sha " + digest)
        if not (same_expected and same_order):
            print("REFUSING: the arms are not paired, so a difference between them "
                  "would not be attributable to the instruction.")
            return 1
    print()
    print("no example appears in any row: checked verbatim, by label subset, and "
          "by content-word overlap")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
