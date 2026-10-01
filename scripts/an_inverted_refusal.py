"""A refusal turned into a promise, caught without a model.

THE GAP THIS FILLS, measured 2026-09-05
(`docs/judge_runs/2026-09-05-clause-one-before-the-judge-result.md`). Of the
four planted defects the pipeline's judge wrongly kept, the upstream validator
catches one and the diff gate correctly admits all four — leaving three with no
backstop anywhere:

    We no longer take cheques.  ->  We still take cheques.        KEPT
    so those we cannot take back  ->  so those we can take back   KEPT
    they do not stack with the sale shelf -> they do stack ...    KEPT

Each adds no number, no name, no price and no place, so
`specifics_the_rewrite_adds` passes it. Each is a genuine content change, so the
diff gate admits it. And each is a fluent, plausible lie about the shop: the
shop does not take cheques.

**Why not the generator's own negation table.** `plant_the_defects.py` builds
these from a closed list of pairs, and a checker keyed on the same pairs would
catch exactly what that generator makes and nothing else - a check marking its
own homework. This works on any text: a sentence whose counterpart in the
rewrite has lost a negation AND ALMOST NOTHING ELSE.

**WHAT IT DOES NOT CATCH, found on production output 2026-09-05.** An exclusion
word reverses a refusal without being a negation: `except Christmas Day and
Boxing Day when we are closed` became `including Christmas Day and Boxing Day`,
and this check saw nothing because `except` is not a negation token. Adding it
was preregistered and CANCELLED - the corpus contains exactly one `except`
answer and it is that row, so there is no control set and tuning on it would
spend the 0-in-155 that lets this refuse a pair unasked. See
`docs/judge_runs/2026-09-05-except-as-a-refusal-cancelled.md`.

**The bound is what makes it a check rather than a guess.** Removing a whole
clause also removes the negations inside it, and that is a deletion, not an
inversion. Requiring the lost words to number three or fewer separates them: the
over-promise deletion of "and they do not stack with the sale shelf" loses nine
words and does not fire, while "no longer" -> "still" loses two and does.
"""

from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher

#: Words that carry a refusal. `no` is here and earns its place: "no longer"
#: and "no minimum" both contain it, and the size bound tells them apart rather
#: than a longer list would.
NEGATIONS: frozenset[str] = frozenset(
    {
        "not", "cannot", "can't", "cant", "don't", "dont", "doesn't", "doesnt",
        "won't", "wont", "isn't", "isnt", "aren't", "arent", "never", "no",
        "nor", "none", "nothing", "neither",
    }
)

#: The most words that may go missing alongside the negation before this stops
#: being an inversion and starts being a deletion. Three admits `no longer` ->
#: `still` (losing two) with one word of slack; the row that fixes the bound is
#: the over-promise deletion that loses nine.
MOST_WORDS_AN_INVERSION_LOSES = 3

#: How similar two sentences must be to count as the same sentence rewritten.
#: Below this they are different sentences and the negation left with its clause.
SAME_SENTENCE = 0.6


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s.strip()]


#: Contractions expanded before anything is compared. THE FIRST VERSION DID NOT
#: DO THIS AND FAILED ITS OWN PREREGISTRATION: `We do not sell digital audio.`
#: -> `We don't sell digital audio.` loses the tokens `do` and `not` and gains
#: `don't`, so a contraction read as a reversed refusal. Five false positives
#: across 155 rows, every one of them a contraction.
#:
#: This list must agree with `SAME_WORDING` in `what_actually_changed.py`; a
#: test asserts it, because two copies of one list is how a rule starts
#: disagreeing with itself.
CONTRACTIONS: tuple[tuple[str, str], ...] = (
    ("don't", "do not"), ("doesn't", "does not"), ("can't", "cannot"),
    ("won't", "will not"), ("isn't", "is not"), ("aren't", "are not"),
    ("we'll", "we will"), ("it's", "it is"), ("that's", "that is"),
    ("i'm", "i am"), ("didn't", "did not"), ("haven't", "have not"),
)


def _words(text: str) -> list[str]:
    lowered = (text or "").lower().replace("’", "'")
    for short_form, long_form in CONTRACTIONS:
        lowered = lowered.replace(short_form, long_form)
    return re.findall(r"[a-z']+", lowered)


def the_refusal_this_rewrite_inverted(real: str, rewrite: str) -> str | None:
    """The sentence whose refusal was flipped, or None.

    Returns the REASON rather than a boolean, because this refusal happens
    before any judge is asked and a refusal a reader cannot check removes a row
    from a corpus with nobody able to say why.
    """
    after = _sentences(rewrite)
    if not after:
        return None
    for sentence in _sentences(real):
        said_no = [w for w in _words(sentence) if w in NEGATIONS]
        if not said_no:
            continue
        counterpart = max(
            after, key=lambda other: SequenceMatcher(None, sentence, other).ratio()
        )
        if SequenceMatcher(None, sentence, counterpart).ratio() < SAME_SENTENCE:
            continue
        lost = Counter(_words(sentence)) - Counter(_words(counterpart))
        if not lost:
            continue
        gone = sorted(lost.elements())
        if len(gone) > MOST_WORDS_AN_INVERSION_LOSES:
            #: A whole clause went. That is a deletion, and deletions are the
            #: named degradation - not this file's business.
            continue
        if not any(word in NEGATIONS for word in gone):
            continue
        return (
            f"the real answer says {sentence!r}; the rewrite says "
            f"{counterpart!r}, which drops {gone} and reverses the refusal. "
            "A rewrite that says the opposite of its source is not a worse "
            "version of it."
        )
    return None
