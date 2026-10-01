"""A removal that drops a scope marker widens the promise by construction.

WHAT THIS IS FOR. `THE-JUDGE.md` records the one thing the deterministic gate
cannot decide without a model: whether a genuine content removal widened a
promise. This finds the decidable subset of that class. A removal that takes out
a time bound, a quantity cap, an exclusivity, a condition, a hedge, a named
party or a day/time window has widened what the answer promises, and no model is
needed to see that the marker is gone.

**The instances come from the corpus; the families are mine, and that matters.**
The seven families below were checked against the 49 source answers and every
one appears in at least two of them, with its counts recorded in
`runs/marker-list.json`. But a family this file does not name is invisible: the
measured misses are a bare price ("for 2.00 a book") and a threshold ("at ten
stamps"), both real restrictions with no family here. Coverage is therefore a
LOWER BOUND on what a marker check could decide, not a ceiling.

**And marker-shaped is not the same as promise-widening.** Dropping "usually"
removes a hedge; whether that widens a promise is the contested question this
corpus has circled all night. This decides the SHAPE.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

#: Number words, so `between 10 and 5` -> `between ten and 5` is not read as a
#: vanished marker. THE FIRST VERSION HAD NO THIS AND FAILED ITS OWN
#: PREREGISTRATION: the `day/time window` family matches digits, so two
#: `sentinel-N` rows that only rewrite a numeral as a word fired the check on
#: rows where nothing was removed at all. The same bug, in the same shape, that
#: `what_actually_changed.py` already carries a fix for.
NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20",
}

#: What this shop uses to restrict a promise. Each family appears in at least
#: two of the 49 answers - a family present in one answer is a coincidence, not
#: a vocabulary - and the per-family counts are in `runs/marker-list.json`.
MARKER_FAMILIES: dict[str, str] = {
    "time bound": r"\bwithin \w+(?: \w+)? (?:days|weeks|hours|months|minutes)\b"
                  r"|\bfor \d+ hours\b|\bfor \w+ days\b",
    "quantity cap": r"\bup to \w+(?: \w+)*?\b|\bno more than \w+\b"
                    r"|\bfrom [\d.]+ upwards\b|\bfor the first \w+\b",
    "exclusivity": r"\bonly\b|\bin store only\b",
    "condition": r"\bif\b|\bunless\b|\bprovided\b|\bexcept\b|\bwith a valid [^,.]+",
    "hedge": r"\busually\b|\bnormally\b|\bsometimes\b|\boccasionally\b|\bmost\b|\bmaybe\b",
    "named party": r"\bstudent card\b|\bloyalty card\b|\bsale shelf\b",
    "day/time window": r"\bon Sundays\b|\bTuesday to Saturday\b"
                       r"|\bbetween \d+ and \d+\b|\b\d+am to \d+pm\b",
}


def _normalised(text: str) -> str:
    """Lowercased with number words written as digits, so notation cannot look
    like a deletion.

    IT LOWERCASES, SO EVERY MATCH AGAINST IT MUST BE CASE-INSENSITIVE. The
    first version normalised to lower case and then matched patterns written
    with capitals - the `on Sundays` and `Tuesday to Saturday` alternatives - without the
    flag, so those two families could never fire and two real removals read as
    carrying no marker. Third time in one night that a check's normalisation
    and its matching disagreed.
    """
    lowered = (text or "").lower()
    for word, digits in NUMBER_WORDS.items():
        lowered = re.sub(rf"\b{word}\b", digits, lowered)
    return lowered


def the_markers_this_rewrite_dropped(real: str, rewrite: str) -> list[str]:
    """Families with fewer occurrences in the rewrite than in the real answer.

    Counts rather than presence, so an answer carrying two conditions that
    loses one is caught.
    """
    before, after = _normalised(real), _normalised(rewrite)
    return [
        name
        for name, pattern in MARKER_FAMILIES.items()
        if len(re.findall(pattern, after, re.IGNORECASE))
        < len(re.findall(pattern, before, re.IGNORECASE))
    ]


def why_this_removal_widens_the_promise(real: str, rewrite: str) -> str | None:
    """The reason, or None. Says which family went, so a reader can check it."""
    dropped = the_markers_this_rewrite_dropped(real, rewrite)
    if not dropped:
        return None
    return (
        f"the rewrite drops a scope marker the real answer set: {dropped}. "
        "A promise with its bound removed reaches further than the one it came "
        "from, and no model is needed to see the bound is gone."
    )


def the_family_counts_over(answers: list[str]) -> dict[str, int]:
    """How many of these answers use each family. Written to
    `runs/marker-list.json` so the list's provenance travels with it."""
    return {
        name: sum(
            1 for answer in answers
            if re.search(pattern, _normalised(answer), re.IGNORECASE)
        )
        for name, pattern in MARKER_FAMILIES.items()
    }


def write_the_marker_list(answers: list[str], where: Path) -> dict:
    """Record the families, their counts and what they were derived from."""
    payload = {
        "derived_from": "runs/honest-path/train.jsonl",
        "unique_answers": len(set(answers)),
        "families": MARKER_FAMILIES,
        "answers_using_each_family": the_family_counts_over(sorted(set(answers))),
        "note": "instances from the corpus; the families are the author's, and a "
                "family not named here is invisible to this check",
    }
    where.parent.mkdir(parents=True, exist_ok=True)
    where.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
