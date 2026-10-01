"""Defects planted in a real answer, deterministically, with no model involved.

This is the TRUTH PATH of the judge instrument, and it is the part that must be
right: every number the instrument produces is measured against these labels, so
a generator that mislabels a pair does not produce a wrong row, it produces a
wrong RATE, silently, for every run that uses it.

So each edit is a pure function returning `(rewritten, what_changed)` or `None`
when the pattern is absent, and each is tested against real rows before a single
model call is spent. `recipes/hf-peft-dpo` makes the same argument for splitting
out `adapter_keys_in`: the decision is the part that gets written wrong, and it
is the part a suite with nothing installed can still exercise.

**Why these five types.** They are the ways a customer-service answer can become
false while staying fluent — the failure a fluent generator actually produces.
A quantity, a qualifying clause, a refusal, a unit, a named thing. Anything
subtler is not decidable without a person, and a truth path that needs a person
is not a truth path.

**What a planted pair is NOT.** It is not a degradation of the kind the
generator produces, which is a real answer made worse but still faithful. It is
a real answer made FALSE. The judge is supposed to drop it, and that is the only
claim these labels make.
"""

from __future__ import annotations

import re
from typing import Callable

#: Refusals, and what inverting one looks like. Ordered longest-first so
#: "no longer" is matched before "no", which would otherwise turn "no longer
#: take cheques" into "yes longer take cheques" - fluent nonsense rather than a
#: plausible lie, and a judge dropping it would be right for the wrong reason.
NEGATIONS: tuple[tuple[str, str], ...] = (
    ("we no longer", "we still"),
    ("no longer", "still"),
    ("cannot", "can"),
    ("can not", "can"),
    ("do not", "do"),
    ("does not", "does"),
    ("will not", "will"),
)

#: Units that can be swapped for a larger one while the number stays. The lie is
#: the unit, which is what makes this different from `a_number_is_doubled`.
UNITS: tuple[tuple[str, str], ...] = (
    ("working days", "working weeks"),
    ("days", "weeks"),
    ("hours", "days"),
    ("minutes", "hours"),
    ("kg", "lb"),
)

#: Clauses that qualify a promise. Removing one widens what was promised.
CONSTRAINTS: tuple[str, ...] = (
    "only if ", "only ", "unmarked ", "if it is ", "if ", "within ", "provided ",
)

#: Named things, swapped for another real one. A shop that says Ireland does not
#: thereby say Belgium.
ENTITIES: tuple[tuple[str, str], ...] = (
    ("Ireland", "Belgium"), ("Penguin", "Vintage"), ("Christmas", "Easter"),
    ("Boxing Day", "New Year"), ("Visa", "Amex"),
)



def _matching_case(original: str, replacement: str) -> str:
    """`replacement`, capitalised if the span it replaces was.

    THE TELL THIS REMOVES. Matching is done on a lowercased copy and the
    replacement is written lowercase, so splicing it in turned "We no longer
    take cheques" into "we still take cheques" - a lowercased sentence start.
    That is a COSMETIC giveaway: a judge could drop the pair because it looks
    malformed rather than because it is false, and recall measured that way is
    measuring the artefact. Found by a test before any call was spent.
    """
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def a_number_is_doubled(text: str) -> tuple[str, str] | None:
    """The first standalone quantity, doubled. `30 days` becomes `60 days`.

    FOUR-DIGIT INTEGERS ARE SKIPPED. Doubling the 1798 in "a 1798 sermon
    collection" gives 3596: false, but absurd rather than plausible, and this
    module's standard is the lie a fluent generator would actually produce.

    A KNOWN REMAINING WEAKNESS of the same shape is named rather than
    engineered away, because a rule guessing at it would refuse good rows:
    "answered between 10 and 5" doubles to "between 20 and 5", a false clock
    time that reads as nonsense. One row of nineteen, and it is named here
    rather than left for a reader to find in the results.
    """
    match = None
    for found in re.finditer(r"\b(\d+(?:\.\d+)?)\b", text):
        digits = found.group(1)
        if "." not in digits and len(digits) == 4:
            continue
        match = found
        break
    if match is None:
        return None
    was = match.group(1)
    now = f"{float(was) * 2:g}" if "." in was else str(int(was) * 2)
    return text[: match.start(1)] + now + text[match.end(1) :], f"number {was} -> {now}"


def a_qualifying_sentence_is_removed(text: str) -> tuple[str, str] | None:
    """A qualifying clause and its sentence, removed. **NOT A DEFECT GENERATOR.**

    WITHDRAWN FROM `EDITS` ON 2026-09-05, AND THIS DOCSTRING IS THE REASON.
    It shipped as the `constraint` edit type on the claim that removing a
    qualifier "widens the promise". Checked row by row after the stratified run,
    all six pairs it produced were mislabelled:

      * two were UNGRAMMATICAL SPLICES - it cuts from the constraint to the next
        full stop, which is clean when the constraint begins a sentence and a
        fused fragment when it does not: "If it is Underlining or highlighting
        makes it unsellable". The same class of tell `_matching_case` removes.
      * four were LOSSY BUT TRUE. Removing "If you give me your order number I
        can check the tracking" deletes an OFFER; the remaining answer promises
        less, not more. Nothing in those rewrites is false.

    The judge dropped exactly one of the six, and it was one of the two
    fragments. So the "1 of 6 constraint recall" this file produced was not a
    judge missing five defects - it was a judge correctly keeping five true
    rewrites, scored against a key that called them defects.

    THE RULE THIS ENFORCES. A truth path may only emit a label it can guarantee.
    This function cannot tell whether removing a span leaves a false answer, an
    under-promise or a merely shorter one, so it may not label its output DROP.
    It is kept, unused and named for what it does, because deleting it would
    delete the record of how a wrong rate was produced.
    """
    lowered = text.lower()
    for clause in CONSTRAINTS:
        start = lowered.find(clause)
        if start == -1:
            continue
        stop = text.find(".", start)
        if stop == -1 or stop <= start:
            continue
        out = (text[:start] + text[stop + 1 :].lstrip()).strip()
        if out and out != text.strip():
            return out, f"constraint '{clause.strip()}' removed"
    return None


def a_refusal_is_inverted(text: str) -> tuple[str, str] | None:
    """A refusal turned into a promise. The most flagrant of the four.

    ONE WEAK ROW OF SIX, named rather than removed. "If it will not work, tell
    me the address" inverts to "If it will work, tell me the address and I will
    remove it by hand" - a conditional that is incoherent rather than false,
    since nothing about the shop is misstated. A judge dropping it may be
    dropping incoherence. The other five invert a real policy ("we can take
    back", "we do sell digital audio") and are exactly what this class claims.
    """
    lowered = text.lower()
    for was, now in NEGATIONS:
        at = lowered.find(was)
        if at == -1:
            continue
        was_text = text[at : at + len(was)]
        return (
            text[:at] + _matching_case(was_text, now) + text[at + len(was) :],
            f"negation '{was}' -> '{now}'",
        )
    return None


def a_unit_is_changed(text: str) -> tuple[str, str] | None:
    """The unit changed, the number kept. `two working days` -> `two working weeks`.

    WHOLE WORDS ONLY, AND THIS WAS WRONG UNTIL 2026-09-05. A plain substring
    search found `days` inside `holidays` and `Sundays` and produced

        We open 11am to 4pm on bank holiweeks
        the multi storey ... is two minutes away and free on Sunweeks

    which are not false answers, they are nonsense words. A judge dropping one
    is right for the wrong reason, and recall measured that way measures the
    artefact - the same failure `_matching_case` was written for. Two of the
    thirteen unit rows were like this, in a class whose per-type recall had
    already been published as 6 of 6.
    """
    for was, now in UNITS:
        found = re.search(rf"\b{re.escape(was)}\b", text, re.IGNORECASE)
        if not found:
            continue
        was_text = text[found.start() : found.end()]
        return (
            text[: found.start()]
            + _matching_case(was_text, now)
            + text[found.end() :],
            f"unit '{was}' -> '{now}'",
        )
    return None


def an_entity_is_swapped(text: str) -> tuple[str, str] | None:
    """A named thing replaced by another real one."""
    for was, now in ENTITIES:
        if was in text:
            return text.replace(was, now, 1), f"entity '{was}' -> '{now}'"
    return None


#: The closed list, in the order a stratified set draws them.
EDITS: dict[str, Callable[[str], "tuple[str, str] | None"]] = {
    "number": a_number_is_doubled,
    "negation": a_refusal_is_inverted,
    "unit": a_unit_is_changed,
    "entity": an_entity_is_swapped,
}
#: `constraint` is deliberately absent. Every one of these four SUBSTITUTES -
#: it leaves a statement standing and makes that statement false, which is a
#: label this file can guarantee. Deletion is not here because no rule in this
#: module can tell a widened promise from a shortened answer. See
#: `a_qualifying_sentence_is_removed`.


def plant(answers: list[str], per_type: int) -> list[dict]:
    """Up to `per_type` planted pairs of each edit type, over these answers.

    RETURNS FEWER RATHER THAN REACHING. If only four answers contain a
    negation, this yields four negation pairs and says so by its length; it does
    not reuse an answer to hit a quota, because two pairs from one sentence are
    not two observations. The caller reports the denominator it actually got,
    which is the whole discipline these files are for.
    """
    out: list[dict] = []
    #: DEDUPLICATED, because `runs/honest-path/train.jsonl` holds one answer
    #: twice and the unit class quietly drew it twice - two rows from one
    #: sentence are not two observations, which is the rule this docstring
    #: already claimed and did not enforce. Order is preserved so the set stays
    #: reproducible.
    answers = list(dict.fromkeys(answers))
    for kind, edit in EDITS.items():
        made = 0
        for answer in answers:
            if made >= per_type:
                break
            result = edit(answer)
            if result is None:
                continue
            rewritten, what = result
            if rewritten.strip() == answer.strip():
                continue
            out.append(
                {
                    "chosen": answer,
                    "rejected": rewritten,
                    "truth": "DROP",
                    "edit_type": kind,
                    "edit": what,
                }
            )
            made += 1
    return out


# ---------------------------------------------------------------------------
# KEEP pairs that are NOT deletions
#
# THE CONFOUND THESE CLOSE. The constructed KEEP set is deletions by design,
# which is what makes its labels sound - a deletion cannot add a fact, so it
# satisfies the judge's second clause by construction. But the 2026-09-05
# stratified run measured this judge catching substitutions 21 times out of 21
# and deletions once out of six: it is nearly blind to absence. So a KEEP set
# made only of deletions measures precision on the one class the judge cannot
# see, and a low false-drop rate there is equally consistent with good judgement
# and with noticing nothing.
#
# A paraphrase or a reorder keeps every fact and moves the SURFACE. If the judge
# keeps those too, its precision is about meaning. If it drops them, it was
# reading the surface all along - and that would be the same finding from the
# other side.


#: Surface swaps that change no fact. Each side means the same thing in a shop's
#: voice, so a rewrite using one is not worse and not false - it is the same
#: answer wearing different words, and the judge must KEEP it.
SAME_MEANING: tuple[tuple[str, str], ...] = (
    ("we do not", "we don't"),
    ("cannot", "can't"),
    ("it is", "it's"),
    ("we will", "we'll"),
    ("I can", "I am able to"),
    ("please", "kindly"),
    ("about", "roughly"),
    ("purchase", "buy"),
)


def a_wording_is_swapped(text: str) -> tuple[str, str] | None:
    """The same claim in different words. Nothing added, nothing removed.

    KEEP BY CONSTRUCTION, and by a different route from a deletion: a deletion
    is the named degradation and adds nothing; this is not a degradation at all
    and adds nothing. Both must be kept, and only this one is visible to a judge
    that reads substitutions.
    """
    lowered = text.lower()
    for was, now in SAME_MEANING:
        at = lowered.find(was)
        if at == -1:
            continue
        original = text[at : at + len(was)]
        return (
            text[:at] + _matching_case(original, now) + text[at + len(was) :],
            f"wording '{was}' -> '{now}', same meaning",
        )
    return None


#: How a shop's answer opens when it is answering. A sentence starting with one
#: of these is the ANSWER, and an answer only makes sense first.
ANSWER_OPENERS: tuple[str, ...] = (
    "yes", "no ", "no.", "no,", "not ", "none", "sorry", "i am sorry",
    "we do", "we did", "we no longer", "good.", "afraid", "certainly",
    "of course",
)


def the_sentences_are_reordered(text: str) -> tuple[str, str] | None:
    """The last two sentences swapped. Every fact survives, the order does not.

    Only where BOTH sentences stand alone: a sentence beginning with a pronoun
    or a connective may depend on the one before it, and reordering those would
    change the meaning rather than the surface - which would make this a DROP
    pair mislabelled KEEP, the one failure a truth path may not have.
    """
    parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    if len(parts) < 2:
        return None
    a, b = parts[-2], parts[-1]
    dependent = ("it ", "they ", "those ", "that ", "this ", "and ", "but ", "so ")
    if b.lower().startswith(dependent) or a.lower().startswith(dependent):
        return None
    #: AND NEVER MOVE THE SENTENCE THAT ANSWERS THE QUESTION. Found by reading
    #: all 35 reorder rows on 2026-09-05: 12 of them pushed the answer to the
    #: end, producing "Ireland is 6.50 ... Yes." and, worse, "I can put you on
    #: the want list and we will email you the day one comes in. Not at the
    #: moment." - where the refusal now attaches to the promise before it and
    #: the meaning has changed. That is a DROP pair labelled KEEP, the one
    #: mistake a truth path may not make.
    #:
    #: The research lane's own generator hit this and fixed it (its manifest
    #: records v2->v3, "still moved an answer-opener sentence second"). I read
    #: that manifest before writing this and did not carry the lesson across.
    if a.lower().startswith(ANSWER_OPENERS):
        return None
    out = " ".join(parts[:-2] + [b, a])
    if out.strip() == text.strip():
        return None
    return out, "reorder: last two sentences swapped, every fact kept"


#: KEEP-by-construction edits that are not deletions.
KEEPS: dict[str, Callable[[str], "tuple[str, str] | None"]] = {
    "wording": a_wording_is_swapped,
    "reorder": the_sentences_are_reordered,
}


def keeps_that_are_not_deletions(answers: list[str], per_type: int) -> list[dict]:
    """KEEP pairs whose surface moved and whose facts did not."""
    out: list[dict] = []
    for kind, edit in KEEPS.items():
        made = 0
        for answer in answers:
            if made >= per_type:
                break
            result = edit(answer)
            if result is None:
                continue
            rewritten, what = result
            if rewritten.strip() == answer.strip():
                continue
            out.append(
                {
                    "chosen": answer,
                    "rejected": rewritten,
                    "truth": "KEEP",
                    "edit_type": f"keep:{kind}",
                    "edit": what,
                }
            )
            made += 1
    return out
