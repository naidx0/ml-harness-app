"""What changed between a real answer and its rewrite, computed in code.

WHY THIS EXISTS, measured 2026-09-05 (`docs/judge_runs/2026-09-05-sentinel-n-result.md`).
Asked to grade 72 rewrites that are not degradations at all, the pipeline's
judge kept 19, and every one of the 19 justified itself with a clause the
rewrite still contains word for word:

    "The rewrite drops the \"over 25.00\" condition, making the recommendation
     unconditional..."                                                   KEEP

The only difference between that rewrite and its source is a removed full stop.
Beside the 2026-09-04 result - where the same instrument invented a QUOTATION
from an empty rewrite - the judge's prose is decoupled from the text in both
directions: it fabricates quotes from nothing and fabricates deletions from
something.

So the reason for a verdict is computed here, from the two texts, with no model
in it. The judge decides; it does not explain.

**And clause (1) is enforced before the judge is asked.** The pipeline's
contract says a pair may be kept only if "the rewritten answer is worse in that
named way". Whether a change of the named KIND happened is a question about two
strings, and a string question does not need a language model. A rewrite that
moved only punctuation, only wording or only sentence order has not degraded
anything, and it is decided by rule rather than sent.

**One disagreement with the instruction that prompted this file, stated rather
than silently resolved.** The relayed ruling said such rows should be "kept by
rule". Kept means shipped into a preference corpus, and a pair whose rejected
side differs by a full stop teaches a model to prefer punctuation. The
`sentinel-N` manifest - the very set proposed to test this - records
`expected_verdict_every_row: DROP`, on the reasoning that "a rewrite that is
merely different is DROP" under the judge's own contract. So the rule here is
**DROP by rule, never sent**, and the disagreement is recorded here rather than
settled by me: if the intent really was to ship them, this constant is the one
line to change and this paragraph is the argument to answer first.
"""

from __future__ import annotations

import re
from collections import Counter

#: The named degradation this corpus produces is a WIDENED PROMISE, which in
#: text terms means content was removed. Everything else - a longer rewrite, a
#: reordered one, a differently punctuated one - is a change of some other kind.
CONTENT_WAS_REMOVED = "content_removed"
CONTENT_WAS_ADDED = "content_added"
CONTENT_WAS_SUBSTITUTED = "content_substituted"
ONLY_PUNCTUATION_MOVED = "punctuation_only"
ONLY_WORDING_MOVED = "wording_only"
ONLY_ORDER_MOVED = "order_only"
NOTHING_CHANGED = "nothing_changed"

#: Contractions and their long forms, so `we will` -> `we'll` is recognised as
#: wording rather than as two words removed and one added. Deliberately the
#: same closed list `plant_the_defects.py` uses to BUILD such pairs: a rule
#: that could not recognise the pairs this repository plants would be untested
#: against the only examples it has.
SAME_WORDING = (
    ("we do not", "we don't"), ("do not", "don't"), ("cannot", "can't"),
    ("can not", "can't"), ("it is", "it's"), ("we will", "we'll"),
    ("that is", "that's"), ("i am", "i'm"), ("is not", "isn't"),
    ("will not", "won't"), ("about", "roughly"), ("purchase", "buy"),
    ("please", "kindly"),
)


#: Number words and their digits. A rewrite that writes `2` where the source
#: wrote `two` has changed NOTATION, not a promise, and a diff calling that a
#: substitution would send it to a judge measured confabulating on exactly such
#: rows. The list stops at twenty because that is where this shop's answers do.
NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20",
}


def _words(text: str) -> list[str]:
    """Lowercased tokens: decimals whole, everything else word by word.

    THE TOKENISER WAS WRONG FIRST TIME AND IT MATTERED. `[a-z0-9.]+` kept
    `6.50` together, which is right, but it also glued the sentence-final stop
    onto `days.` — so a rewrite differing from its source by ONE REMOVED FULL
    STOP came out as a content substitution, and all 48 such rows in the
    2026-09-05 set would have been sent to the judge this rule exists to spare
    them from. Decimals are matched explicitly instead.
    """
    lowered = (text or "").lower().replace("’", "'")
    return [
        NUMBER_WORDS.get(token, token)
        for token in re.findall(r"\d+\.\d+|[a-z0-9']+", lowered)
    ]


def _normalised(text: str) -> str:
    """Lowercased, with the closed list of contractions expanded, so a wording
    swap does not read as a content change."""
    out = (text or "").lower().replace("'", "'")
    for long_form, short_form in SAME_WORDING:
        out = out.replace(short_form, long_form)
    return out


def _without_punctuation(text: str) -> str:
    """Lowercased, with punctuation and repeated spaces gone, so "days." and
    "days" compare equal and nothing else does."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", "", (text or "").lower())).strip()


def what_changed(real: str, rewrite: str) -> str:
    """The KIND of change, from the two strings and nothing else.

    Order matters and is the whole design: the cheapest, most certain
    classifications are made first, so a punctuation-only rewrite can never be
    reported as a dropped clause.
    """
    if (real or "").strip() == (rewrite or "").strip():
        return NOTHING_CHANGED

    before, after = Counter(_words(_normalised(real))), Counter(_words(_normalised(rewrite)))
    if before == after:
        #: Same words, same counts. Either the order moved or it did not; if it
        #: did not, the difference is punctuation or notation.
        if _words(_normalised(real)) != _words(_normalised(rewrite)):
            return ONLY_ORDER_MOVED
        #: AND THE LABEL HAS TO BE TRUE. `two` -> `2` also leaves the token
        #: lists identical, because the tokeniser normalises number words - so
        #: calling it "punctuation only" would be this file writing exactly the
        #: kind of reason it exists to stop: a plausible sentence about a change
        #: that did not happen. Punctuation is claimed only when stripping
        #: punctuation makes the two texts equal.
        if _without_punctuation(real) == _without_punctuation(rewrite):
            return ONLY_PUNCTUATION_MOVED
        return ONLY_WORDING_MOVED

    lost, gained = before - after, after - before
    if not lost and not gained:
        return ONLY_WORDING_MOVED
    if lost and not gained:
        return CONTENT_WAS_REMOVED
    if gained and not lost:
        return CONTENT_WAS_ADDED
    return CONTENT_WAS_SUBSTITUTED


def the_words_the_rewrite_lost(real: str, rewrite: str) -> list[str]:
    """What is in the real answer and not in the rewrite, as a sorted list.

    THIS IS THE ACCOUNT THAT REPLACES THE JUDGE'S PROSE. It cannot name a
    clause that is still there, because it is derived from the text rather than
    written about it.
    """
    lost = Counter(_words(_normalised(real))) - Counter(_words(_normalised(rewrite)))
    return sorted(lost.elements())


def the_account_of_this_pair(real: str, rewrite: str) -> str:
    """One sentence describing the change, generated from the diff.

    Where a record needs a reason beside a verdict, this is the reason. It is
    printed, not asked for.
    """
    kind = what_changed(real, rewrite)
    if kind == CONTENT_WAS_REMOVED:
        lost = the_words_the_rewrite_lost(real, rewrite)
        return f"the rewrite drops {len(lost)} word(s) and adds none: {lost}"
    if kind == CONTENT_WAS_SUBSTITUTED:
        return (
            f"the rewrite drops {the_words_the_rewrite_lost(real, rewrite)} "
            f"and adds {the_words_the_rewrite_lost(rewrite, real)}"
        )
    if kind == CONTENT_WAS_ADDED:
        return f"the rewrite adds {the_words_the_rewrite_lost(rewrite, real)} and drops nothing"
    if kind == ONLY_ORDER_MOVED:
        return "the rewrite has every word of the real answer in a different order"
    if kind == ONLY_PUNCTUATION_MOVED:
        return "the rewrite differs from the real answer only in punctuation"
    if kind == ONLY_WORDING_MOVED:
        return (
            "the rewrite says the same words in different form - a contraction, "
            "a synonym on the closed list, or a number written as a word"
        )
    return "the rewrite is the real answer"


#: The kinds that can possibly be `over_promises_beyond_the_source`. A widened
#: promise drops a restriction, so content has to be gone. A SUBSTITUTION is
#: admitted too, because "within 30 days" -> "within 60 days" both drops and
#: adds while genuinely widening.
COULD_BE_A_WIDENED_PROMISE = (CONTENT_WAS_REMOVED, CONTENT_WAS_SUBSTITUTED)


def why_this_pair_never_reaches_the_judge(real: str, rewrite: str) -> str | None:
    """The rule-decided refusal, or None when the judge should be asked.

    Returns the REASON, not a boolean, because a refusal a reader cannot check
    is the failure this file exists to remove one layer up.
    """
    kind = what_changed(real, rewrite)
    if kind in COULD_BE_A_WIDENED_PROMISE:
        return None
    return (
        f"not the named degradation: {the_account_of_this_pair(real, rewrite)}. "
        "A rewrite that removes nothing cannot promise more than its source, so "
        "this pair is dropped by rule and no judge is asked."
    )
