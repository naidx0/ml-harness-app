"""Prompt arms for the system-design set, per family, paired.

    python evals/system-design/build_arms.py

THE THREE FAMILIES ARE THREE TASKS AND ARE NEVER POOLED. `components` asks for a
set and is scored by set overlap; `missing_component` and `pattern_name` ask for
one string and are scored by exact match and by contains. A single number over
the three would average a set-overlap score against a string match, and the
research lane asked for per-family precisely because they do not combine.

  components         rows   0- 59   60 rows   set_f1
  missing_component  rows  60-111   52 rows   exact_match / contains
  pattern_name       rows 144-195   52 rows   exact_match / contains

`edge_direction`, rows 112-143, is NOT in the assignment. Recording that here
because it is the family the architecture-JSON work just found carries the
surviving error - 13 of 62 reference edges present but reversed - so the one
family excluded from this search is the one with a known open defect. Not a
complaint about the assignment: a note that the exclusion is load-bearing and
should be a decision rather than an oversight.

PAIRED: same rows, same order, same expected answers, only the appended sentence
differs. So a difference between two arms is attributable to the sentence.

THE ORIGINAL SET IS NEVER TOUCHED. `held-out.jsonl` is hash-pinned by
`held-out.sha256` and the arms are written beside it under their own names.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).parent
NEWLINE = chr(10)

#: (family, first row_index, last row_index), exactly as assigned.
RANGES = [
    ("components", 0, 59),
    ("missing_component", 60, 111),
    ("pattern_name", 144, 195),
]

#: THE ARMS. `bare` is the row's own instruction with nothing added - the
#: control, and the thing every other arm is compared against.
#:
#: `naming` is the sentence that carried 26 of 27 points on architecture-JSON.
#: It is the obvious candidate and it is here to be tested rather than assumed:
#: it tells the model to reuse the question's own words, which is plainly right
#: for `components` and plainly WRONG for `pattern_name`, where the answer is a
#: term of art that the question deliberately does not contain. If it helps one
#: family and hurts another, that is the result.
#:
#: The two further prompts are deliberately NOT written yet - see the note at
#: the bottom of this file.
#: WRITTEN AFTER THE FIRST TWO ARMS RAN, from their failures rather than from
#: a guess. The bare arm loses two different ways and these take one each.
#:
#: `terse` takes the wording half: `A read replica` for `read replica`,
#: `Circuit Breaker Pattern` for `circuit breaker`, `Microservices
#: Architecture` for `microservices`, `Rate limiting` for `rate limiter`,
#: `Content Delivery Network` for `cdn`. In every one of those the model has
#: the answer and dresses it.
#:
#: `canonical` takes the other half, where the answer is a DIFFERENT term at a
#: different level of specificity: `Cache-Aside Pattern` for `caching`,
#: `Producer-consumer pattern` for `message queue`. Asking for the standard
#: index term is a different treatment from asking for a bare one, and mixing
#: the two into a single sentence would be the bundling this lab has already
#: paid for once.
ARMS = {
    "bare": "",
    "naming": (
        " Use the words the question itself uses for each part, and do not add "
        "words the question did not use."
    ),
    "terse": (
        " Answer with the bare term only: no leading article, no trailing word "
        "such as pattern, system or architecture, and the singular noun form."
    ),
    "canonical": (
        " Give the single most standard name for it, the one an index would "
        "list, rather than a description or a longer phrase containing it."
    ),
    #: THE CROSSING ARMS. The first three confounded two things: `terse` was the
    #: most specific about form AND the longest (137 chars) and scored worst;
    #: `naming` was 100 chars and scored best of the three. Specificity and
    #: length predict the same ordering across those arms, so neither can be
    #: credited. A mechanism that reproduces exactly under a second variable is
    #: not a mechanism yet - the character counts are 100 / 131 / 137 against
    #: scores 55.5 / 52.6 / 36.4.
    #:
    #: These two cross the confound in opposite directions, which is the entire
    #: reason they exist rather than being two more candidate sentences:
    #:
    #:   S-short    77 chars, says everything `terse` says (article, trailing
    #:              noun, singular) - MAXIMALLY SPECIFIC AND SHORTEST
    #:   V-long    162 chars, says nothing at all about form - LONGEST AND VAGUE
    #:
    #: Registered before either runs, decision line 46%: if SPECIFICITY drives
    #: the effect, S-short lands near 36% and V-long near 55%; if LENGTH drives
    #: it, the reverse. Refutations are numeric - H1 dies if S-short >= 52 and
    #: V-long <= 42; H2 dies if S-short <= 42 and V-long >= 52. If the two arms
    #: disagree with each other, neither survives and a third factor is doing
    #: the work, which is a result rather than a failure.
    "S-short": (
        " Bare term only: no article, no trailing 'pattern' or 'system', "
        "singular noun."
    ),
    "V-long": (
        " Give it in whatever form seems most fitting, taking a moment first to "
        "consider how a reader of this kind of question would most likely "
        "expect to see it presented."
    ),
    #: REGISTERED NON-DECISIVE IN ADVANCE, at 5.3 points and about 1.7 SE. It
    #: describes; it does not decide. Saying so before it runs is what stops a
    #: good-looking number being promoted afterwards.
    "C-content": (
        " Name only the components the description explicitly mentions, and "
        "none that it does not mention."
    ),
}


def main() -> int:
    source = HERE / "held-out.jsonl"
    rows = [json.loads(line) for line in source.open(encoding="utf-8") if line.strip()]

    pinned = (HERE / "held-out.sha256").read_text(encoding="utf-8").split()[0]
    #: ONE RULE, ONE IMPLEMENTATION. baseline.py owns the pin check and this
    #: calls it rather than restating it - two functions deciding whether a set
    #: matches its record is two answers waiting to disagree.
    import sys as _sys; _sys.path.insert(0, str(HERE))
    from baseline import digest_of
    actual = digest_of(source.read_bytes())
    if pinned != actual:
        print("REFUSING: the held-out set does not match its recorded hash, so it "
              "is not the set that was committed.")
        return 1

    print("source " + source.name + " sha " + actual[:12] + " (matches the pin)")
    print()
    for family, lo, hi in RANGES:
        segment = [r for r in rows if lo <= int(r["row_id"]) <= hi]
        wrong = [r["row_id"] for r in segment if r["family"] != family]
        if wrong:
            print("REFUSING: rows " + str(lo) + "-" + str(hi) + " are not all "
                  + family + " - " + str(len(wrong)) + " row(s) are not: "
                  + str(wrong[:5]))
            return 1
        for arm, sentence in ARMS.items():
            out_rows = [
                {
                    "row_id": r["row_id"],
                    "family": r["family"],
                    "input": r["input"] + sentence,
                    "expected": r["expected"],
                }
                for r in segment
            ]
            out = HERE / ("arm-" + family + "-" + arm + ".jsonl")
            with out.open("w", encoding="utf-8", newline=NEWLINE) as handle:
                for row in out_rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + NEWLINE)
            same_expected = [r["expected"] for r in segment] == [r["expected"] for r in out_rows]
            same_order = [r["row_id"] for r in segment] == [r["row_id"] for r in out_rows]
            print(f"  {family:18s} {arm:8s} n={len(out_rows):3d}  "
                  f"expected identical: {same_expected}  order identical: {same_order}  "
                  f"sha {hashlib.sha256(out.read_bytes()).hexdigest()[:12]}")
            if not (same_expected and same_order):
                print("REFUSING: the arms are not paired.")
                return 1
    print()
    print("n per family: " + ", ".join(f"{f} {hi - lo + 1}" for f, lo, hi in RANGES))
    print("The two further prompts are not written yet ON PURPOSE. Writing four")
    print("candidates before seeing the first two spends the card on guesses; the")
    print("bare arm's per-family failures say what the next sentence should try,")
    print("and the same four arms get run either way.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
