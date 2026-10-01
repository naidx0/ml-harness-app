"""What the showcase may train on, counted two ways and neither one hidden.

## The two counts, and why both are reported

The 200-row corpus was selected by ONE judge pass, and the sentinel pair showed
that pass is not repeatable: 52 of 72 self-agreement, with KEEP the unstable
verdict - 11 of 16 first-pass KEEPs flipped. So membership in the training set
was partly a coin. The second pass over the 188 fixes that by keeping only rows
BOTH passes kept.

Then there is a third filter, and it is the one that needs saying plainly:

* **the two-gate count** - rows kept by both judge passes. Every one of them
  already passed the two gates that ship in the pipeline today, because passing
  them is how the row reached the judge at all
* **the three-gate count** - the same rows, minus any the added-fact rule
  refuses. That rule enforces clause (2) of the judge's own contract: every
  fact in the rewrite already appears in the source

**THE ADDED-FACT RULE IS NOT WIRED INTO THE GENERATOR.** Its module
(`scripts/a_rewrite_that_adds_a_fact.py`) is committed and tested; the wiring is
in `stash@{0}` with nine fixtures still to migrate. So the third count here is
the rule APPLIED, not a pipeline path that ran - this script calls the same
function the gate would call, on the same texts, but nothing in the pipeline
refused these rows at generation time. That distinction belongs in any report
that quotes the number: it is what the rule WOULD do, measured, not what the
product DID do.

The reason to apply it anyway is the measurement behind it: of 68 rows the judge
kept that add content words, 42 are flat falsehoods about the shop. A corpus a
model learns from should not carry them.

## The stopping rule

Fixed before the run at **100 rows**, and by ruling it applies to the
three-gate count. Under 100, the showcase stops before training and the page
states the options with their counts for a person to choose between. This script
decides nothing; it counts, and it prints the same numbers whichever way they
fall.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "runs" / "second-judge-pass" / "results.jsonl"
OUT = REPO / "runs" / "second-judge-pass"

#: Fixed before the run. By ruling it applies to the three-gate count.
THE_SHOWCASE_NEEDS = 100

sys.path.insert(0, str(REPO))
sys.dont_write_bytecode = True
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    if not RESULTS.exists():
        print(
            f"{RESULTS} is not here. The second pass has not finished, and a "
            "count from a partial file would be a smaller number that looked "
            "like a smaller intersection. Nothing was counted.",
            file=sys.stderr,
        )
        return 2

    adds = load("adds_a_fact", REPO / "scripts" / "a_rewrite_that_adds_a_fact.py")
    rows = [
        json.loads(line)
        for line in RESULTS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    aborted = [r for r in rows if r.get("run2") is None]
    both = [r for r in rows if r.get("run1") == "KEEP" and r.get("run2") == "KEEP"]
    disagreed = [
        r
        for r in rows
        if r.get("run2") is not None and r.get("run1") != r.get("run2")
    ]

    refused, survives = [], []
    for row in both:
        why = adds.why_this_rewrite_adds_a_fact(row["chosen"], row["rejected"])
        (refused if why else survives).append({**row, "added_fact": why})

    print("=" * 68)
    print(f"rows judged twice            : {len(rows)}")
    if aborted:
        print(f"  of which unreadable/aborted: {len(aborted)}  (in no intersection)")
    print()
    print(f"THE INTERSECTION, two shipped gates : {len(both)}")
    print(f"THE INTERSECTION, all three gates   : {len(survives)}")
    print(f"  refused by the added-fact rule    : {len(refused)}")
    print()
    print(f"the instrument's own error (one pass kept, the other dropped): {len(disagreed)}")

    OUT.mkdir(parents=True, exist_ok=True)
    for name, kept in (
        ("kept-by-both-two-gates.jsonl", both),
        ("kept-by-both-three-gates.jsonl", survives),
        ("refused-by-the-added-fact-rule.jsonl", refused),
        ("the-instruments-own-error.jsonl", disagreed),
    ):
        (OUT / name).write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in kept) + "\n",
            encoding="utf-8",
        )
        print(f"  wrote {len(kept):>4} to {name}")

    print()
    print(f"THE STOPPING RULE, fixed before the run: {THE_SHOWCASE_NEEDS} rows,")
    print("applied to the THREE-gate count by ruling.")
    if len(survives) >= THE_SHOWCASE_NEEDS:
        print(f"  {len(survives)} >= {THE_SHOWCASE_NEEDS}: the showcase may train on the")
        print("  three-gate intersection.")
    else:
        print(f"  {len(survives)} < {THE_SHOWCASE_NEEDS}: THE SHOWCASE STOPS BEFORE TRAINING.")
        print("  The three options, with their counts, for a person to choose:")
        print(f"    1. train on the three-gate intersection as it is  - {len(survives)} rows")
        print(f"    2. train on the two-gate intersection, the added-fact rows marked "
              f"- {len(both)} rows, {len(refused)} marked")
        print("    3. wait for a larger corpus - generate more rows and judge them twice")
        print("  Nothing trains tonight on rows the rule refuses.")

    print()
    print("READ THIS BESIDE THE NUMBER: the added-fact rule is NOT wired into the")
    print("generator - its module is committed, the wiring is in stash@{0} with nine")
    print("fixtures to migrate. The three-gate count is that rule APPLIED here, not a")
    print("pipeline path that ran. Nothing refused these rows at generation time.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
