"""Classify what the node-label F1 is actually losing, row by row.

    python evals/architecture-json/what_the_remaining_gap_is.py <run.jsonl>

THE OPEN QUESTION AFTER THE LADDER. Four prompt shapes all land at 79-81%, so
the remaining fifth is not moved by the prompting tried. That is the fact the
training question needs - but "what is left" is not the same as "what training
would fix", and nobody had looked at the failures.

WHAT IT SEPARATES, because these are four different problems with four different
answers and one number calls them all the same:

  same component, other words   `postgres` where the reference says
                                `postgres database`. The component was found and
                                named; set overlap charges it TWICE, once as a
                                miss and once as an extra.
  missed                        a component in the description that the answer
                                does not mention at all.
  invented                      a component the answer names that the reference
                                does not have, and which is not a rewording of
                                anything missed.
  edges                         count, and direction: an edge present but
                                reversed is a different failure from an absent
                                one.

THE PAIRING RULE IS A JUDGEMENT AND IS PRINTED. Deciding that `postgres` and
`postgres database` are one component is exactly the sort of call an instrument
should not make silently, so every pair it draws is listed and the count of
decisions resting on the rule is reported beside the result. A reader who
disagrees with one can subtract it.

The rule: after lowercasing and dropping a small set of generic words, two
labels are the same component when one's token set is a subset of the other's,
or when they share at least half their tokens. It is deliberately conservative
about `invented` - anything that could be a rewording is called a rewording,
because the interesting claim is that the model is NOT inventing, and an
instrument should not make its own claim easy.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).parent

#: Words that carry no identity on their own. Kept short on purpose: a long list
#: would let this rule call any two components the same thing.
NOISE = {"the", "a", "an", "service", "server", "system"}


def singular(word: str) -> str:
    """A crude stem, and crude on purpose.

    THE FIRST VERSION DID NOT DO THIS AND MIS-CLASSIFIED SIX DISAGREEMENTS.
    `sensor` against `sensors`, `encoder` against `encoders`, `player` against
    `players` were each counted as a component MISSED and a component INVENTED
    - two serious findings apiece - when the answer had named the thing and
    pluralised it. Reporting five missed components when two were missed would
    have been the instrument, not the model.

    Only a trailing s, and never on a three-letter word, so `bus` and `gas`
    survive. Anything cleverer would start merging words that are genuinely
    different.
    """
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def tokens(label: str) -> frozenset[str]:
    words = [w for w in str(label).lower().replace("-", " ").replace("_", " ").split()]
    kept = [singular(w) for w in words if w not in NOISE]
    return frozenset(kept or [singular(w) for w in words])


def the_same_component(one: str, two: str) -> bool:
    a, b = tokens(one), tokens(two)
    if not a or not b:
        return False
    if a <= b or b <= a:
        return True
    return len(a & b) / len(a | b) >= 0.5


def reference() -> dict[str, dict]:
    found: dict[str, dict] = {}
    for name in sorted(HERE.glob("ladder-*.jsonl")) + sorted(HERE.glob("held-out*.jsonl")):
        for line in name.open(encoding="utf-8"):
            if line.strip():
                row = json.loads(line)
                found.setdefault(str(row["row_id"]), row)
    return found


def edges_by_label(graph: dict) -> set[tuple[str, str]]:
    """Edges as (from-label, to-label), so two graphs can be compared at all.

    Ids are the model's own invention and never match between two answers; the
    labels are the only shared vocabulary.
    """
    label = {
        str(n.get("id")): str(n.get("label", "")).strip().lower()
        for n in (graph.get("nodes") or [])
        if isinstance(n, dict)
    }
    out = set()
    for edge in graph.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        a, b = label.get(str(edge.get("from"))), label.get(str(edge.get("to")))
        if a and b:
            out.add((a, b))
    return out


def classify(run: Path) -> dict:
    ref = reference()
    rows = [json.loads(l) for l in run.open(encoding="utf-8") if l.strip()]

    same_word_pairs: list[tuple[str, str, str]] = []
    missed: list[tuple[str, str]] = []
    invented: list[tuple[str, str]] = []
    edge_same = edge_missing = edge_reversed = edge_extra = 0
    graded = 0

    for row in rows:
        want = ref.get(str(row.get("row_index")))
        if want is None:
            continue
        try:
            answer = json.loads(row["answer"])
        except (ValueError, TypeError):
            continue
        graded += 1
        rid = str(row.get("row_index"))

        got = {str(n.get("label", "")).strip().lower()
               for n in (answer.get("nodes") or []) if isinstance(n, dict)}
        wanted = {str(l).strip().lower() for l in want["node_labels"]}

        still_missing = set(wanted - got)
        still_extra = set(got - wanted)
        #: Greedy pairing. Each miss may absorb at most one extra, so a single
        #: invented component cannot excuse two real misses.
        for miss in sorted(still_missing):
            partner = next((e for e in sorted(still_extra) if the_same_component(miss, e)), None)
            if partner is not None:
                same_word_pairs.append((rid, miss, partner))
                still_extra.discard(partner)
            else:
                missed.append((rid, miss))
        for extra in sorted(still_extra):
            invented.append((rid, extra))

        expected_graph = want["expected"]
        if isinstance(expected_graph, str):
            expected_graph = json.loads(expected_graph)
        #: EDGES ARE COMPARED AFTER THE LABELS ARE RECONCILED. Without this the
        #: edge numbers restate the label numbers: an edge whose endpoint is
        #: called `postgres` instead of `postgres database` cannot match, so a
        #: naming difference is counted once as a label disagreement and again
        #: as two broken edges. The first version reported 29 missing edges that
        #: way, and most of them were one word.
        rename = {partner: miss for r, miss, partner in same_word_pairs if r == rid}
        theirs = {(rename.get(a, a), rename.get(b, b)) for a, b in edges_by_label(answer)}
        ours = edges_by_label(expected_graph)
        for edge in ours:
            if edge in theirs:
                edge_same += 1
            elif (edge[1], edge[0]) in theirs:
                edge_reversed += 1
            else:
                edge_missing += 1
        edge_extra += len(theirs - ours - {(b, a) for a, b in ours})

    return {
        "graded": graded,
        "same_word_pairs": same_word_pairs,
        "missed": missed,
        "invented": invented,
        "edges": {"matched": edge_same, "reversed": edge_reversed,
                  "missing": edge_missing, "extra": edge_extra},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run", type=Path)
    args = parser.parse_args()

    found = classify(args.run)
    n = found["graded"]
    pairs, missed, invented = found["same_word_pairs"], found["missed"], found["invented"]
    total = len(pairs) + len(missed) + len(invented)

    print("run   " + args.run.name)
    print("n     " + str(n) + " rows graded")
    print()
    print("LABEL DISAGREEMENTS: " + str(total))
    print("  same component, other words  " + str(len(pairs)).rjust(3)
          + "   scored as a miss AND an extra, so charged twice")
    print("  missed entirely              " + str(len(missed)).rjust(3))
    print("  invented                     " + str(len(invented)).rjust(3))
    print()
    e = found["edges"]
    print("EDGES (by label, since ids are the model's own):")
    print("  matched   " + str(e["matched"]).rjust(3))
    print("  reversed  " + str(e["reversed"]).rjust(3) + "   present but pointing the other way")
    print("  missing   " + str(e["missing"]).rjust(3))
    print("  extra     " + str(e["extra"]).rjust(3))
    print()
    print("EVERY PAIR THE RULE DREW, so a reader who disagrees can subtract it:")
    for rid, miss, partner in pairs:
        print("  row " + rid.rjust(2) + "   reference " + repr(miss) + "  answer " + repr(partner))
    if missed:
        print()
        print("MISSED, which the rule could not pair with anything:")
        for rid, miss in missed:
            print("  row " + rid.rjust(2) + "   " + repr(miss))
    if invented:
        print()
        print("INVENTED:")
        for rid, extra in invented:
            print("  row " + rid.rjust(2) + "   " + repr(extra))
    print()
    print("The pairing rule decided " + str(len(pairs)) + " of these " + str(total)
          + " disagreements. It is a judgement, not a measurement, and the pairs "
            "are listed above for that reason.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
