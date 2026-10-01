"""Edge direction, scored under a NAMED endpoint-matching rule.

    python evals/architecture-json/edge_direction.py <run.jsonl> [--rows]

WHY THIS FILE EXISTS. Two lanes counted reversed edges on the same data and got
13 and 11. Neither number was wrong arithmetic: they used different rules for
deciding when an answer's node IS a reference node, and a different rule moves an
edge between *reversed* and *renamed*. Until the rule is written down neither
figure is quotable, so this writes it down and reports the count under it.

`score.py` computes `schema_valid` and `label_f1` and nothing else, so edge
direction has never been scored by anything in this repository. This is not a
metric with a disputed value; it is a quantity choosing its first metric.

## THE RULE

1. **An endpoint is resolved through the answer's own `nodes` list** to that
   node's `label`, lowercased and stripped. An edge naming an id that the answer
   never declares is UNRESOLVABLE and is reported separately - it is not a
   direction error and must not be counted as one.

2. **An answer label matches a reference label** when, after lowercasing,
   splitting on spaces/hyphens/underscores, dropping the generic words
   `the a an service server system`, and removing one trailing `s` from words
   longer than three characters:

   * the token sets are equal, or
   * **the answer's tokens are a SUBSET of the reference's tokens.**

3. **The subset test is ONE-DIRECTIONAL and that is the settled rule.** `postgres`
   matches `postgres database`; `postgres database` does NOT match `postgres`.
   The reason is a claim about what a prompt could fix: a sentence can stop a
   model shortening a name it already produced, and cannot make a model say a
   word its answer never contained. The reference is never normalised towards
   the answer.

4. **Each reference node absorbs at most one answer node**, taken in sorted
   order so the result does not depend on dictionary iteration. One shortened
   name cannot excuse two different omissions.

5. **Buckets over the reference's edges**, and direction is scored over MATCHED
   edges only:

   * `correct`  - both endpoints resolved and matched, arrow the same way
   * `reversed` - both endpoints resolved and matched, arrow the other way
   * `unmatched` - at least one endpoint did not match a reference node

   The denominator for the reversed share is `correct + reversed`. Scoring it
   over every reference edge would re-import the naming problem this rule exists
   to separate: a node named differently makes every edge touching it fail, and
   charging that as a direction error would count one naming difference twice.

## WHAT THE RULE COSTS

A one-directional subset rule calls `postgres` a match for `postgres database`
and refuses the reverse, so a model that pads a name is treated more harshly
than one that clips it. That is deliberate and it is an assumption about
fixability, not a fact about the answers. A reader who rejects it can re-run with
the equality test alone; the per-row output below is there so the disagreement
can be located rather than argued.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).parent

#: THE RULE LIVES IN ONE PLACE. This file was carrying its own copy of the
#: matching and bucketing code while `app/tools/edge_direction_metric.py` was
#: about to carry a second. Two implementations of one rule is two answers
#: waiting to disagree - which is exactly how this quantity came to be reported
#: as 13 by one lane and 11 by another. The core is imported; this file is the
#: command-line door onto it.
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.tools.edge_direction_core import score as _score  # noqa: E402


def reference_files(named=None):
    """The ONE reference a run is scored against, named rather than globbed.

    This used to return every `ladder-*.jsonl` and `held-out*.jsonl` in the
    directory, and that glob is the fault: a predictions file carrying positional
    indices 0-19 has indices that are valid row_ids in the original twenty, so it
    joined confidently to the wrong questions and produced a plausible table.
    Nothing about a positional index says which file it counts within.
    """
    if named:
        return [Path(named)]
    return [HERE / "held-out.jsonl"]


def score(run: Path) -> dict:
    return _score(run, reference_files(REFERENCE), subset_allowed=SUBSET_ALLOWED and not RAW)


#: Kept so the two stricter rules stay reproducible from the command line.
SUBSET_ALLOWED = True
RAW = False
REFERENCE = None

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run", type=Path)
    parser.add_argument("--reference", help="the reference set this run was generated from")
    parser.add_argument("--raw", action="store_true",
                        help="labels compared as whole strings, no tokenising")
    parser.add_argument("--equality-only", action="store_true",
                        help="labels must match exactly; no rename reconciliation")
    parser.add_argument("--rows", action="store_true",
                        help="print the per-row counts this figure is made of")
    args = parser.parse_args()

    global SUBSET_ALLOWED, RAW, REFERENCE
    SUBSET_ALLOWED = not args.equality_only
    RAW = args.raw
    REFERENCE = args.reference
    found = score(args.run)
    matched = found["correct"] + found["reversed"]
    total = matched + found["unmatched"]
    print("run       " + args.run.name)
    print("rule      one-directional subset, answer -> expected; expected never normalised")
    print()
    print("reference edges           " + str(total).rjust(4))
    print("  correct                 " + str(found["correct"]).rjust(4))
    print("  REVERSED                " + str(found["reversed"]).rjust(4))
    print("  unmatched endpoint(s)   " + str(found["unmatched"]).rjust(4)
          + "   a naming difference, NOT a direction error")
    print()
    #: COVERAGE FIRST, AND THE REVERSED SHARE IS NOT A SCORE WITHOUT IT.
    #:
    #: Measured 2026-09-10 and it is a hole in this file: a model that answers
    #: ONE CONSTANT GRAPH to all 93 carved eval rows scores 4 correct, 0
    #: reversed, 342 unmatched - a reversed share of 0.0%, which is the best
    #: possible value of the published metric. The real model scores 26.5%.
    #:
    #: The cause is the denominator that makes the metric honest about naming:
    #: direction is scored over MATCHED edges, so a model that matches nothing
    #: has no reversals to be charged for. Refusing to engage wins.
    #:
    #: Training toward a bare reversed share would therefore teach a model to
    #: emit labels the reference cannot match. So coverage is printed above the
    #: share, and a verdict needs BOTH: the share may only be compared between
    #: runs whose coverage is comparable, and a run whose coverage FALLS has not
    #: improved no matter what its share does.
    coverage = matched / total if total else 0.0
    print("coverage: " + str(matched) + " of " + str(total) + " reference edges matched = "
          + format(coverage, ".1%"))
    if coverage < 0.5:
        print("  *** COVERAGE IS LOW. The reversed share below is not a score: a model")
        print("  *** that matches nothing has no reversals. Compare shares only at")
        print("  *** comparable coverage, and treat a coverage fall as a regression.")
    if matched:
        print("reversed share, over MATCHED edges only: "
              + str(found["reversed"]) + " of " + str(matched)
              + " = " + format(found["reversed"] / matched, ".1%"))
    print("over all reference edges it would read "
          + format(found["reversed"] / total, ".1%") if total else "")
    print("  - the difference between those two is naming, not direction.")
    if found["unresolvable_answer_edges"]:
        print()
        print("answer edges naming an id the answer never declared: "
              + str(found["unresolvable_answer_edges"]) + " (reported, not counted)")

    if args.rows:
        print()
        print("THE ROWS THIS FIGURE IS MADE OF:")
        print("row  edges  correct  reversed  unmatched   reversed edges")
        for row in found["per_row"]:
            print(str(row["row"]).rjust(3) + str(row["edges"]).rjust(7)
                  + str(row["correct"]).rjust(9) + str(row["reversed"]).rjust(10)
                  + str(row["unmatched"]).rjust(11) + "   "
                  + "; ".join(row["reversed_edges"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
