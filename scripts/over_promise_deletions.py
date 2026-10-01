"""Deletions that genuinely widen a promise, written span by span.

WHY THIS FILE EXISTS. `plant_the_defects.py` withdrew its `constraint` edit on
2026-09-05 because a rule that removes "a qualifying clause" cannot tell a
widened promise from a shortened answer: four of the six pairs it produced were
lossy but TRUE, and the "1 of 6 constraint recall" measured against them was a
correct judge scored against a wrong key.

The fix is not a cleverer rule. It is a SMALLER CLAIM. Each row below names one
span, and the span is chosen so the sentence around it still makes the promise
the span limited. Deleting it leaves a rewrite that asserts P where the source
asserted P-only-under-C, which is `over_promises_beyond_the_source` exactly.

**PROVENANCE: ASSERTED.** Nothing here is measured. A person chose each span and
a person can check each one, which is the whole reason the table is written out
rather than generated - thirteen rows a reader can disagree with beat a rule
that produces sixty rows nobody reads. A row a reader rejects comes out of the
denominator and the run is re-reported; that is the falsifier.

**What is checked in code, because a person will not notice it:** the span must
appear in the source exactly once, the rewrite must actually differ, and the
rewrite must carry none of the punctuation scars a naive splice leaves - no
` ,`, no ` .`, no `,.`, no sentence ending in `and`. Those scars are how the
withdrawn generator produced pairs a judge could rule on for how they LOOK.
"""

from __future__ import annotations

import re

#: `(anchor, span removed, the promise it limited)`.
#:
#: THE ANCHOR EXISTS BECAUSE UNIQUENESS WAS TOO BLUNT. The first table keyed a
#: row on its span alone and refused any span appearing in two answers, which
#: silently cost `for 48 hours` - a span that limits a promise in BOTH the hold
#: answer and the reservation answer, so it is two good rows rather than an
#: ambiguity. An empty anchor means "whatever answer holds this span"; a
#: non-empty one must appear in the answer too, and the pair must still have
#: exactly one home. Refusing is still the default, and what it refuses is
#: still printed.
#:
#: The third field is the reason the row is a defect, in the words a reader
#: would use to check it.
DELETIONS: tuple[tuple[str, str, str], ...] = (
    ("", " and only if the spine is intact",
     "buying is now promised on age alone, with no condition on the spine"),
    ("", " and within 30 days",
     "the return is now promised on being unmarked alone, with no deadline"),
    ("", ", except Christmas Day and Boxing Day when we are closed",
     "bank holiday opening is now promised without its two exceptions"),
    ("", " for up to 2kg",
     "6.50 to Ireland is now promised at any weight"),
    ("", ", for 2.00 a book",
     "wrapping is now promised with no price attached"),
    ("", " and they do not stack with the sale shelf",
     "codes are now promised without the restriction against stacking"),
    ("", " with a valid student card",
     "the 10 percent is now promised to anyone, not only to students"),
    ("", ", up to two boxes at a time",
     "buying in is now promised with no cap on quantity"),
    ("", " on Sundays",
     "the car park is now promised free on every day"),
    ("Not as an exchange", " within 30 days",
     "credit on a return is now promised with no window"),
    ("", " from 10.00 upwards",
     "gift cards are now promised at any amount, with no minimum"),
    ("hold it under your name", " for 48 hours",
     "the hold is now promised with no end to it"),
    ("We hold reservations", " for 48 hours",
     "the reservation is now promised with no end to it"),
    ("", " at ten stamps",
     "the 5.00 credit is now promised with no number of stamps to reach"),
    ("Collect in store", " for seven days",
     "the in-store hold is now promised with no end to it"),
    #: REJECTED ON READING, and kept here as the record. Removing
    #: " we refund if we buy" from "there is a 40.00 call out we refund if we
    #: buy" deletes a REFUND, so the rewrite promises LESS than the source, not
    #: more. It is an under-promise wearing a deletion's clothes - the same
    #: mistake that produced the withdrawn `constraint` edit, caught this time
    #: by reading all sixteen rows before any call was spent.
    #: ("", " we refund if we buy", "..."),
    ("", ", Tuesday to Saturday",
     "the phone line is now promised answered on every day of the week"),
)


#: Punctuation a naive splice leaves behind. A pair carrying one of these can be
#: dropped by a judge for looking malformed rather than for being false, which
#: measures the artefact instead of the model.
SCARS: tuple[str, ...] = (" ,", " .", ",.", ",,", "  ", " and.", " and,")


def why_this_rewrite_is_malformed(rewrite: str) -> str | None:
    """The scar this rewrite carries, or None. Named so a test can call it."""
    for scar in SCARS:
        if scar in rewrite:
            return f"punctuation scar {scar!r}"
    if re.search(r"\b(and|but|or|with|for)\s*[.!?]", rewrite):
        return "a sentence ends on a conjunction"
    return None


def the_answer_this_span_belongs_to(
    answers: list[str], anchor: str, span: str
) -> str | None:
    """The one answer this (anchor, span) names, or None when it names none or
    several.

    A FUNCTION RATHER THAN A CONDITION INSIDE THE LOOP so a test can call the
    rule with a span the table does not contain - the ambiguous case has to be
    exercised, and it cannot be exercised through a table that has been fixed
    to avoid it.
    """
    homes = [a for a in answers if a.count(span) == 1 and anchor in a]
    return homes[0] if len(homes) == 1 else None


def the_deletion_pairs(answers: list[str]) -> list[dict]:
    """One pair per span that appears exactly once across these answers.

    RETURNS FEWER RATHER THAN REACHING, and says which spans it could not
    place, because a span that matches twice would make the edit ambiguous and
    a span that matches none is a table entry gone stale.
    """
    out: list[dict] = []
    for anchor, span, why in DELETIONS:
        source = the_answer_this_span_belongs_to(answers, anchor, span)
        if source is None:
            continue
        rewrite = source.replace(span, "", 1)
        if rewrite.strip() == source.strip():
            continue
        if why_this_rewrite_is_malformed(rewrite):
            continue
        out.append(
            {
                "chosen": source,
                "rejected": rewrite,
                "truth": "DROP",
                "edit_type": "over_promise_deletion",
                "edit": f"removed {span.strip()!r}",
                "why": why,
                "provenance": "ASSERTED: a person chose this span and a person can check it",
            }
        )
    return out


def spans_that_could_not_be_placed(answers: list[str]) -> list[tuple[str, str]]:
    """Every span not in the output, with the reason. Printed, never hidden.

    THE FIRST VERSION OF THIS REPORTED ONLY THE AMBIGUOUS ONES, so the table
    said "placed 9 of 12" and listed two - a third span had been dropped for a
    punctuation scar and appeared nowhere. A denominator that does not add up is
    exactly the failure this whole file is a response to.
    """
    unplaced: list[tuple[str, str]] = []
    for anchor, span, _ in DELETIONS:
        hits = [a for a in answers if a.count(span) == 1 and anchor in a]
        if len(hits) == 0:
            unplaced.append((span.strip(), "no answer contains it"))
        elif len(hits) > 1:
            unplaced.append((span.strip(), f"{len(hits)} answers contain it, so the edit is ambiguous"))
        else:
            scar = why_this_rewrite_is_malformed(hits[0].replace(span, "", 1))
            if scar:
                unplaced.append((span.strip(), scar))
    return unplaced
