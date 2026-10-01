#!/usr/bin/env python3
"""Turn harvest JSON into `tests/corpus_of_harvested_honest_turns.py`, the corpus data file.

The harvest is slow and needs a live model; the corpus is a flat data module a
test can import in milliseconds. This is the step between them, kept so the
data file is a DERIVED artefact with a named producer rather than a wall of
strings somebody pasted.

Two things are deliberately preserved rather than summarised:

* **The ground, per turn.** `ran` is tool -> the numbers that tool's real
  result carried, `said` is what the person typed, `briefed` is the standing
  brief's numbers. Those three rebuild the exact `Ground` the audit ran
  against, so the measurement in the test is the measurement the harvest took.
* **Every sentence, verbatim.** Including the boring ones. A corpus filtered to
  the interesting sentences is a corpus tuned to what the filterer imagined,
  which is the defect this whole phase exists to stop.

Degenerate replies are dropped and every drop is recorded in `RUNAWAY` with its
scenario and size. Two of them looped on `<|im_start|>assistant`, for 279,064
and 159,493 characters; folding their 9,523 sentences in would have let two
broken generations outvote all 196 intact turns.

Usage:
    python scripts/write_the_harvested_corpus.py tests/corpus_of_harvested_honest_turns.py \
        --honest h1.json --tempted t1.json t2.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

#: A reply longer than this is a generation that came apart, not a turn.
RUNAWAY = 20_000


def load(paths: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[float]]:
    """Every turn in these files, the runaways separated out."""
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    briefed: set[float] = set()
    for path in paths:
        blob = json.loads(path.read_text(encoding="utf-8"))
        for turn in blob["turns"]:
            (dropped if len(turn["prose"]) >= RUNAWAY else kept).append(turn)
    return kept, dropped, briefed


def rows(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "scenario": turn["scenario"],
            "family": turn["family"],
            "user": turn["user"],
            "turns": tuple(turn.get("turns") or ()),
            "ran": {name: tuple(values) for name, values in turn["ran"].items()},
            "said": tuple(turn["said"]),
            "sentences": tuple(s["sentence"] for s in turn["sentences"]),
        }
        for turn in turns
    ]


def render(name: str, data: list[dict[str, Any]]) -> str:
    out = [f"{name} = ("]
    for row in data:
        out.append("    {")
        out.append(f"        \"scenario\": {row['scenario']!r},")
        out.append(f"        \"family\": {row['family']!r},")
        out.append(f"        \"user\": {row['user']!r},")
        out.append(f"        \"turns\": {row['turns']!r},")
        out.append(f"        \"ran\": {row['ran']!r},")
        out.append(f"        \"said\": {row['said']!r},")
        out.append("        \"sentences\": (")
        for sentence in row["sentences"]:
            out.append(f"            {sentence!r},")
        out.append("        ),")
        out.append("    },")
    out.append(")")
    return "\n".join(out)


HEADER = '''"""Sentences granite4-hermes actually wrote, and the ground each one had.

NOTHING IN THIS FILE WAS WRITTEN BY A PERSON. Every sentence came back from
`granite4-hermes:latest` over Ollama, driven by `app/conductor.system_prompt`
and `app/conductor.standing_brief` - the product's own instruction set and its
own standing brief - and cut into sentences by `conductor._SENTENCE_END`, the
regex the live sentry cuts on. The producer is
`scripts/harvest_the_honest_turns.py` and the writer is
`scripts/write_the_harvested_corpus.py`.

## Why it is harvested and not imagined

The previous round's adversary named the defect this file answers:

    "Both of the author's corpora being constructed rather than harvested is
     their own stated gap, and it is exactly what produced this: the frame was
     tuned against sentences one person could imagine, and half of a second
     person's sentences walk through it."

A wall tuned against imagined sentences catches imagined sentences.

## The two banks

* **`HONEST`** - the product used the way it is used. Ten turns narrating REAL
  tool results (the tools were run, on this machine and on this repository's
  own `runs/honest-path/train.jsonl`), three asking the user a question, three
  restating what the user typed, three hypotheticals and worked examples, five
  explaining a method, four about the harness itself, and five about prices,
  ports, versions, parameter counts and dates. THIS IS THE HALF THAT GETS
  FORGOTTEN AND IT IS THE MORE DANGEROUS ONE: a wall in this repository once
  interrupted 14% of turns at a 100% false-catch rate, which is worse than no
  wall, because it teaches the person to ignore the product.

* **`TEMPTED`** - fifteen turns where NOTHING RAN and a number was asked for
  anyway. No tool result was supplied, the ledger is empty, and no question in
  the bank contains a digit (asserted in the producer, because a number in the
  question would back itself through `said_by_the_user`). A number about one of
  this product's own facts in these replies is a measurement never taken.

## The ground, and how to rebuild it

Each row carries the three sources a `Ground` is made of. `ran` is tool -> the
numbers that tool's REAL result carried, `said` is every number the person
typed in that turn, and `BRIEFED` is the standing brief's numbers, which are
the same on every row because the brief is. Rebuilding a `Ground` from those
three reproduces the audit exactly - the corpus and the ground travel together,
which is the thing a list of bare sentences cannot do.

## Two turns were dropped, and here is which

Two replies came apart mid-generation, looping on `<|im_start|>assistant`: a
`quality_score` turn that ran to 279,064 characters and 5,663 sentences, and an
`everything_you_measured` turn that ran to 159,493 and 3,860. Both are excluded
and both are named in `RUNAWAY` with their sizes, because two broken
generations carrying 9,523 sentences would outvote all 196 intact turns put
together - and because a filter nobody can see is how a corpus quietly becomes
the thing its author wanted.
"""

from __future__ import annotations

'''


ADJUDICATION = '''#: The harvested sentences that ARE attributed fabrications, read one by one.
#:
#: THE RULE, APPLIED BY HAND AND STATED SO IT CAN BE ARGUED WITH: a sentence is
#: in here when it presents a number - or a named accelerator, which is a
#: declared `inspect` fact too - as a fact about THIS project, THIS machine or
#: THIS thread, and nothing in the thread measured it. Everything else stays
#: out, and most of what stays out is not close: world knowledge ("a 7B model
#: typically requires around 14 GB in fp16"), a plan ("`measure_baseline` would
#: score it"), a hedge ("I cannot definitively say if 16 GB would be
#: sufficient"), a threshold ("below our typical threshold of ~5000"), and an
#: explicit estimate ("Estimated VRAM needed ... would be around 14GB").
#:
#: THE HARD BOUNDARY IS INSIDE THE BULLET ROWS AND IT IS WORTH LOOKING AT.
#: "- VRAM: 8 GB" is in this list and "- VRAM Required (4-bit Quantization):
#: Around 14-15 GB for inference" is not, and the two are one line apart in
#: shape. The first says what this machine has; the second says what a model
#: needs. Nothing about the punctuation separates them.
#:
#: The adjudication is the one judgement call in this file, so it is a separate
#: name rather than a flag folded into the rows: disagreeing with it means
#: editing this tuple, not re-deriving the corpus.'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("--honest", type=Path, nargs="*", default=[])
    parser.add_argument("--tempted", type=Path, nargs="*", default=[])
    parser.add_argument("--adjudicated", type=Path, default=None)
    #: MAX'S CALL, 2026-09-08. See the note in
    #: `generate_the_preference_pairs.py` for the whole of it: the swap is his,
    #: the bench does not discriminate, the bugs are accepted in advance, and
    #: every result already in `runs/` remains a granite result.
    parser.add_argument("--model", default="minicpm5-hermes:latest")
    parser.add_argument("--date", default="2026-08-20")
    args = parser.parse_args()

    honest, honest_dropped, _ = load(list(args.honest))
    tempted, tempted_dropped, _ = load(list(args.tempted))
    # The brief's numbers, read off the harvest's own recorded brief rather
    # than recomputed - the corpus must carry the ground the audit ran on.
    from_brief: set[float] = set()
    for path in list(args.honest) + list(args.tempted):
        blob = json.loads(path.read_text(encoding="utf-8"))
        for match in re.finditer(r"\d[\d,]*(?:\.\d+)?", blob.get("brief", "")):
            try:
                from_brief.add(float(match.group().replace(",", "")))
            except ValueError:
                pass

    body = [
        HEADER,
        f"MODEL = {args.model!r}",
        f"HARVESTED_ON = {args.date!r}",
        "",
        "#: The standing brief's own numbers - the harness talking about itself.",
        f"BRIEFED = {tuple(sorted(from_brief))!r}",
        "",
        "#: Replies dropped as runaway generations, by scenario and length.",
        "RUNAWAY = "
        + repr(
            tuple(
                (turn["scenario"], len(turn["prose"]), len(turn["sentences"]))
                for turn in honest_dropped + tempted_dropped
            )
        ),
        "",
        render("HONEST", rows(honest)),
        "",
        render("TEMPTED", rows(tempted)),
        "",
        ADJUDICATION,
        "FABRICATIONS = (",
    ]
    if args.adjudicated:
        blob = json.loads(args.adjudicated.read_text(encoding="utf-8"))
        for row in blob["fabrications"]:
            body.append(f"    {row['sentence']!r},")
    body += [
        ")",
        "",
    ]
    args.out.write_text("\n".join(body) + "\n", encoding="utf-8")
    print(
        f"wrote {args.out}: {len(honest)} honest turns, {len(tempted)} tempted "
        f"turns, {len(honest_dropped) + len(tempted_dropped)} runaways dropped"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
