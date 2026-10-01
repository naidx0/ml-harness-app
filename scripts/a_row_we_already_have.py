"""A row whose triple is already in the corpus. Refused at generation.

## What it exists for, measured

Every count on this project counted duplicate rows as separate rows:

    kept by judge pass 1        164 rows ->  127 distinct
    kept by both passes         156 rows ->  119 distinct
    kept by both and all gates   95 rows ->   60 distinct
    a run that "added 11"        11 rows ->    3 new

One triple appeared **seven times** in the 95. Fourteen appeared twice. A model
trained on that corpus would have seen one row seven times and counted it as
seven examples, and every decision about whether the corpus was large enough was
made against a number 58% too high.

The cause is structural and unglamorous: the generator draws from 49 source
answers with one degradation instruction, reproduces the same rewrite for the
same source again and again, and **nothing anywhere deduplicated** - not the
generator, not the validator, not the judge, not the report. This gate is what
makes `kept: N` mean N different things.

## A duplicate is not a defect, and gets its own column

`THE_STAGE` is `duplicate`, not `validator`. A row refused here is not wrong -
it is one we already have. Folding it into the validator's faults would make the
report say the generator produced something broken when it produced something
redundant, and "12 duplicates" would read as "12 defects" to anyone scanning the
run. **The two facts are different and the report has to be able to say both.**

## Zero calls

The check is three strings against a set, so it runs where the other three
deterministic gates run: before the judge, costing nothing. A duplicate
discovered after the judge has answered is a duplicate that has already been
paid for at 40 seconds a call.

## Why the whole triple, and why stripped

A training row is `(prompt, chosen, rejected)`. Two rows sharing a prompt and a
source answer but differing in the rewrite are two different examples and both
belong. Two rows differing only in trailing whitespace are one example twice,
and a gate defeated by a trailing space is a formality rather than a check.
"""

from __future__ import annotations

#: Its own column in the report. Not `validator`: see the docstring.
THE_STAGE = "duplicate"


def the_triple(row: dict) -> tuple[str, str, str] | None:
    """`(prompt, chosen, rejected)` stripped, or None if the row is not one.

    A malformed row is NOT a duplicate. It may well be a defect, but that is
    the validator's judgement to make and not this gate's, and answering "yes,
    duplicate" for a row this gate cannot even read would hide the real fault.
    """
    try:
        return (
            str(row["prompt"]).strip(),
            str(row["chosen"]).strip(),
            str(row["rejected"]).strip(),
        )
    except (KeyError, TypeError):
        return None


class TheRowsWeAlreadyHave:
    """The corpus, as a set of triples, that grows as a run goes.

    IT GROWS DURING THE RUN on purpose. A gate that only knew the corpus as it
    was at start-up would let a run duplicate against itself, which is exactly
    how one triple came to appear seven times inside a single 200-row run.
    """

    def __init__(self, rows=()):
        self._seen: set[tuple[str, str, str]] = set()
        for row in rows:
            self.remember(row)

    def __len__(self) -> int:
        return len(self._seen)

    def __contains__(self, row: dict) -> bool:
        """Membership by ROW. Kept for callers that hold a row."""
        triple = the_triple(row)
        return triple is not None and self.holds(triple)

    def holds(self, triple) -> bool:
        """Membership by TRIPLE, named separately on purpose.

        The first version of this class had only `__contains__(row)`, and the
        function below passed it a triple - so `the_triple` was handed a tuple,
        raised, returned None, and EVERY duplicate read as new. The gate was
        inert and its six "is refused" cases all failed at once, which is the
        only reason it was caught. Two shapes behind one operator is how that
        happens; two names cannot.
        """
        return triple in self._seen

    def remember(self, row: dict) -> None:
        triple = the_triple(row)
        if triple is not None:
            self._seen.add(triple)


def why_this_row_is_one_we_already_have(
    row: dict, already: TheRowsWeAlreadyHave
) -> str | None:
    """The sentence when the corpus already holds this triple, else None."""
    triple = the_triple(row)
    if triple is None or not already.holds(triple):
        return None
    return (
        f"the corpus already holds this exact (prompt, chosen, rejected) triple: "
        f"{triple[2][:60]!r}. This is not a defect - the row is correct and it is "
        "redundant. Counting it again would make the corpus report more training "
        "examples than it has, which is how 95 rows came to be 60."
    )
