"""The edge-direction rule, in one place, used by the tool and by the CLI.

THE DENOMINATOR RULE: direction is scored over MATCHED edges only, coverage is
reported beside it, and any reversed share is quoted with its matched count or
not at all.

THIS FILE EXISTS BECAUSE TWO IMPLEMENTATIONS OF ONE RULE IS TWO ANSWERS WAITING
TO DISAGREE. `evals/architecture-json/edge_direction.py` is the command a person
runs; `app/tools/edge_direction_metric.py` is the call the engine makes. They
were about to be the same hundred lines twice, which is the mistake that cost
this house a wrong lock key and, on this very quantity, a 13-against-11
disagreement that took a three-by-two grid to settle.

`subset_allowed` selects the matching rule: the settled one-directional subset
(an answer may be a shortening of the reference, never the reverse) or plain
equality, which reproduces a stricter count made elsewhere.
"""

from __future__ import annotations

import json
from pathlib import Path

NOISE = {"the", "a", "an", "service", "server", "system"}


def singular(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def tokens(label: str) -> frozenset[str]:
    words = str(label).lower().replace("-", " ").replace("_", " ").split()
    kept = [singular(w) for w in words if w not in NOISE]
    return frozenset(kept or [singular(w) for w in words])


#: Flipped by --equality-only, so this file can reproduce a count made under the
#: stricter rule instead of arguing with it. Two lanes reported 13 and 11 on this
#: quantity; running BOTH rules over BOTH files is the only way to say whether
#: the gap is the rule, the data, or both.
SUBSET_ALLOWED = True
RAW = False


def answer_matches_reference(answer_label: str, reference_label: str,
                             subset_allowed: bool = True) -> bool:
    """ONE-DIRECTIONAL: the answer may be a shortening of the reference."""
    if False:
        #: No tokenising at all: the labels must be the same string once
        #: lowercased and stripped. Included because reproducing another lane's
        #: count is the only way to tell a rule difference from a data
        #: difference, and their denominator did not fall out of the tokenised
        #: equality rule.
        return str(answer_label).strip().lower() == str(reference_label).strip().lower()
    a, b = tokens(answer_label), tokens(reference_label)
    if not a or not b:
        return False
    return a <= b if subset_allowed else a == b


def label_of(graph: dict) -> dict[str, str]:
    return {
        str(n.get("id")): str(n.get("label", "")).strip().lower()
        for n in (graph.get("nodes") or [])
        if isinstance(n, dict)
    }


def build_map(answer: dict, reference_labels: set[str],
              subset_allowed: bool = True) -> dict[str, str]:
    """answer label -> reference label, each reference used at most once."""
    mapping: dict[str, str] = {}
    taken: set[str] = set()
    for answer_label in sorted({l for l in label_of(answer).values() if l}):
        if answer_label in reference_labels and answer_label not in taken:
            mapping[answer_label] = answer_label
            taken.add(answer_label)
            continue
        for reference_label in sorted(reference_labels - taken):
            if answer_matches_reference(answer_label, reference_label, subset_allowed):
                mapping[answer_label] = reference_label
                taken.add(reference_label)
                break
    return mapping


def edges_of(graph: dict) -> tuple[set[tuple[str, str]], int]:
    """(edges as label pairs, count of edges naming an undeclared id)."""
    labels = label_of(graph)
    out: set[tuple[str, str]] = set()
    unresolvable = 0
    for edge in graph.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        a, b = labels.get(str(edge.get("from"))), labels.get(str(edge.get("to")))
        if a and b:
            out.add((a, b))
        else:
            unresolvable += 1
    return out, unresolvable


def reference(paths) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for name in paths:
        with name.open(encoding="utf-8") as handle:
            lines = handle.readlines()
        for line in lines:
            if line.strip():
                row = json.loads(line)
                found.setdefault(str(row["row_id"]), row)
    return found


def reference_rows(paths):
    """Reference rows in file order, and keyed by row_id."""
    ordered = []
    for name in paths:
        with Path(name).open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    ordered.append(json.loads(line))
    return ordered, {str(r["row_id"]): r for r in ordered}


def choose_join(run_indices, ordered, by_id, run_row_ids=(), reference_count=1):
    """(join, reason). NEVER a silent guess.

    `measure_baseline` writes `row_index` as the POSITION in the eval file, not
    the file's own `row_id`. Measured 2026-09-10: a run over held-out-extra
    (row_ids 100-119) came back carrying indices 0-19, which resolved against
    the ORIGINAL twenty and scored the extra set's answers against different
    questions - 0 matched of 62, reported as 0.0% reversed. A mis-join produces
    a number rather than an error, which is the whole reason this returns the
    join it used.
    """
    #: A PREDICTIONS FILE MAY NOW CARRY `row_id` ITSELF, and when it does that is
    #: the answer and nothing is inferred. ML BUILD's half of this fix threads a
    #: caller-supplied `row_id` through the recipe's plan into `predictions.jsonl`
    #: beside the positional index; this is the other half.
    if run_row_ids and all(str(i) in by_id for i in run_row_ids):
        return "declared_row_id", "the predictions file declares a row_id for every row"
    if run_row_ids:
        missing = sorted({str(i) for i in run_row_ids} - set(by_id))[:4]
        return None, ("the predictions file declares row_ids that are not in the "
                      "reference (" + ", ".join(missing) + "), so it was scored "
                      "against a different set than it was generated from")

    #: SEVERAL REFERENCES AND NO DECLARED row_id IS UNRESOLVABLE, and this is
    #: the shape of ML BUILD's fault rather than the positional join I first
    #: blamed. Their predictions came from the 100-based file, carried positional
    #: indices 0-19, and those indices ARE valid row_ids in the original twenty -
    #: so the join succeeded confidently against the wrong questions. Nothing
    #: about a positional index says which file it counts within, so when more
    #: than one reference is in play the index cannot be resolved at all.
    if len(run_indices) and reference_count > 1 and not run_row_ids:
        return None, ("several reference sets were named and the predictions "
                      "declare no row_id, so a positional index cannot say which "
                      "set it counts within - and an index that happens to be a "
                      "valid id in one of them joins confidently to the wrong "
                      "questions. Name the one reference this run came from, or "
                      "re-run with the recipe that declares row_id")

    if run_indices and all(i in by_id for i in run_indices):
        return "row_id", "every run index is a row_id in the reference"

    #: POSITIONAL JOIN IS REFUSED WHEN THE REFERENCE DOES NOT USE THOSE IDS, and
    #: this is the second bite of the same fault. A predictions file numbered
    #: 0-19 against a reference numbered 100-119 has matching COUNTS, so a
    #: positional join succeeds and produces a table that looks entirely
    #: reasonable - ML BUILD hit exactly this and caught it by hand. The counts
    #: matching is not evidence the two files are about the same questions; it is
    #: evidence they are the same length.
    #:
    #: So position is allowed only when the reference's own ids ARE the positions
    #: - which is the case where the two conventions cannot disagree. Otherwise
    #: the caller names the reference the run came from, or re-runs with the
    #: recipe that declares row_id. A refusal is cheap; a good-looking number
    #: about the wrong graphs is not.
    if len(run_indices) == len(ordered):
        positional_ids = {str(i) for i in range(len(ordered))}
        if set(by_id) == positional_ids:
            return "position", ("the run indices are not declared row_ids, the "
                                "counts match, and the reference is itself "
                                "numbered from zero, so file order is unambiguous")
        #: ONE NAMED REFERENCE IS THE CALLER'S PROVENANCE CLAIM. Refusing this
        #: was a notch too strict and it blocked the legitimate call on its first
        #: use - a run generated FROM one file, scored against that same file,
        #: with positional indices, which is exactly what the recipe produces.
        #: The danger ML BUILD hit was the CLI globbing every `held-out*.jsonl`,
        #: where position 0 silently resolved to whichever file sorted first. So
        #: the refusal keys on AMBIGUITY - more than one reference - rather than
        #: on the ids differing, which is a property of the naming convention and
        #: not of the mistake.
        if reference_count == 1:
            return "position", ("the run indices are not declared row_ids, but "
                                "exactly one reference was named and the counts "
                                "match, so file order is the caller's claim")
        return None, ("the run has as many rows as the reference but its indices "
                      "(" + ", ".join(sorted(run_indices)[:3]) + ") are not the "
                      "reference's ids (" + ", ".join(sorted(by_id)[:3]) + "). "
                      "Matching counts is not evidence they are the same "
                      "questions. Name the reference this run was generated "
                      "from, or re-run with the recipe that declares row_id")
    return None, ("the run indices are not row_ids and the row counts differ ("
                  + str(len(run_indices)) + " run rows against " + str(len(ordered))
                  + " reference rows), so there is no join that is not a guess")


def score(run: Path, reference_paths, subset_allowed: bool = True) -> dict:
    ordered, by_id = reference_rows(reference_paths)
    with run.open(encoding="utf-8") as handle:
        run_rows = [json.loads(l) for l in handle if l.strip()]
    indices = [str(r.get("row_index")) for r in run_rows]
    declared = [r.get("row_id") for r in run_rows if r.get("row_id") is not None]
    join, why = choose_join(indices, ordered, by_id, declared,
                            reference_count=len(list(reference_paths)))
    if join is None:
        return {"correct": 0, "reversed": 0, "unmatched": 0, "join": None,
                "unparsed_answers": 0,
                "join_reason": why, "unresolvable_answer_edges": 0, "per_row": []}
    ref = by_id if join in ("row_id", "declared_row_id") else {str(i): row for i, row in enumerate(ordered)}
    correct = reversed_ = unmatched = unresolvable = unparsed = 0
    per_row = []
    for row in run_rows:
        key = row.get("row_id") if join == "declared_row_id" else row.get("row_index")
        want = ref.get(str(key))
        if want is None:
            continue
        #: AN ANSWER THAT DOES NOT PARSE IS A WRONG ANSWER, NOT AN ABSENT ROW.
        #: This used to `continue`, which dropped the row - and with it, the
        #: row's reference edges - out of the DENOMINATOR. A model that emits
        #: garbage on the rows it finds hard therefore scored HIGHER coverage
        #: than one that emitted a wrong graph, because its failures were
        #: deleted from the thing it was measured against.
        #:
        #: MEASURED 2026-09-10 on run 1's adapter over the forty: rows 12 and
        #: 111 did not parse, they carry 2 reference edges each, and coverage
        #: read 56/114 = 49.1% where the honest denominator is 56/118 = 47.5%.
        #: Same family as the constant-answer hole this metric already
        #: closes: a way to score better by answering less.
        try:
            answer = json.loads(row["answer"])
        except (ValueError, TypeError):
            answer = {"nodes": [], "edges": []}
            unparsed += 1
        expected = want["expected"]
        if isinstance(expected, str):
            expected = json.loads(expected)

        reference_labels = {l for l in label_of(expected).values() if l}
        mapping = build_map(answer, reference_labels, subset_allowed)
        theirs, bad = edges_of(answer)
        unresolvable += bad
        theirs = {(mapping.get(a), mapping.get(b)) for a, b in theirs}
        theirs = {(a, b) for a, b in theirs if a and b}
        ours, _ = edges_of(expected)

        row_correct = row_reversed = row_unmatched = 0
        specimens = []
        for edge in sorted(ours):
            if edge in theirs:
                row_correct += 1
            elif (edge[1], edge[0]) in theirs:
                row_reversed += 1
                specimens.append(edge[0] + " -> " + edge[1])
            else:
                row_unmatched += 1
        correct += row_correct
        reversed_ += row_reversed
        unmatched += row_unmatched
        per_row.append({"row": str(row.get("row_index")), "edges": len(ours),
                        "correct": row_correct, "reversed": row_reversed,
                        "unmatched": row_unmatched, "reversed_edges": specimens})
    return {"correct": correct, "reversed": reversed_, "unmatched": unmatched,
            "join": join, "join_reason": why,
            "unresolvable_answer_edges": unresolvable,
            "unparsed_answers": unparsed, "per_row": per_row}


