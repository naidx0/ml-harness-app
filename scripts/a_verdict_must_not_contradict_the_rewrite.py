"""A KEEP whose stated reason is contradicted by the rewrite is not a verdict.

WHAT THIS EXISTS FOR, measured 2026-09-05 on 72 rows that are not degradations
at all (`docs/judge_runs/2026-09-05-sentinel-n-result.md`). The pipeline's judge
kept 19 of them, and **all 19 justified the verdict with a clause the rewrite
still contains, word for word**:

    "The rewrite drops the \"over 25.00\" condition, making the recommendation
     unconditional..."                                                    KEEP

The only difference between that rewrite and its source is a removed final full
stop. `over 25.00` is right there in the text the judge was shown.

The mechanism is in our own prompt: `what_the_judge_is_shown` tells the judge
the rewrite "was supposed to be worse in exactly this way", so a primed judge
finds the named degradation whether or not it happened. That line is what makes
clause (1) checkable at all, and it is also what makes clause (1) fail.

**Why a wall rather than a better prompt.** The failure is mechanically
falsifiable: the judge NAMES the clause it believes was dropped, and a clause
that is still in the rewrite was not dropped. No model is needed to see that,
and `evidence.py`'s wall 8 makes the same argument - a check a generated
artefact cannot talk its way past is worth more than a better instruction.

**What this file does NOT do.** It is not wired into
`generate_the_preference_pairs.py`. Wiring it changes what enters a training
corpus, and the rule adopted on 2026-09-05 is that such a change must be shown
to BEAT what it replaces on rows that were actually generated, not constructed.
This is the check and its evidence; the wiring is a separate, measured decision.
"""

from __future__ import annotations

import re

#: How a judge in this repository says something was taken out. Deliberately
#: narrow: every phrase here is one the measured replies actually used, and a
#: wider list would start catching "the rewrite drops in tone", which is a
#: judgement rather than a claim about text.
SAYS_SOMETHING_WAS_DROPPED = re.compile(
    r"\b(?:drops?|dropped|dropping|removes?|removed|removing|omits?|omitted"
    r"|leaves out|left out)\b",
    re.IGNORECASE,
)

#: The clause a reply names, in the quotation marks it named it with. Straight
#: and curly quotes both, because the model used both in one run.
QUOTED = re.compile(r"[\"“‘']([^\"“”‘’']{3,120})[\"”’']")

#: A quoted fragment shorter than this is not specific enough to check - "it",
#: "no" and "30" appear in almost any answer, so searching for them would clear
#: a confabulation rather than catch it.
#:
#: THE SWEEP, AND ITS CAVEAT. On the 72 rows of 2026-09-05, catching KEEPs by
#: threshold: >=4 and >=5 catch 15 of 19, >=6 catches 14 (it loses a reply that
#: quoted "Today"), >=8 catches 13, >=12 catches 10. Five is chosen because
#: "Today" is a real quoted claim and a four-character floor buys nothing more.
#: That sweep was run on the same rows this wall is reported against, so 15 of
#: 19 is NOT an out-of-sample number and is not offered as one.
SHORTEST_CHECKABLE_CLAUSE = 5


#: The verdict token the judge is asked to put on its own line at the end.
#: STRIPPED BEFORE THE REASONING IS READ, and this was a real bug: the pattern
#: for "something was dropped" matched the word DROP itself, so every DROP reply
#: trivially looked like a claim that something had been removed. It showed up
#: as one flagged DROP row whose reasoning was in fact correct - "The rewrite
#: retains the 'usually' qualifier, so it is not more permissive" - and the
#: thing being matched was the verdict, not the argument.
A_TRAILING_VERDICT = re.compile(r"\s*\b(KEEP|DROP)\b[\s.]*$")


def the_reasoning_without_the_verdict(reply: str) -> str:
    """The reply with its trailing verdict word removed, so the argument can be
    read without the conclusion contaminating it."""
    text = (reply or "").strip()
    while True:
        stripped = A_TRAILING_VERDICT.sub("", text)
        if stripped == text:
            return text
        text = stripped


def the_clauses_the_reply_says_were_dropped(reply: str) -> list[str]:
    """Quoted fragments a reply claims the rewrite removed.

    ONLY QUOTED ONES. A reply that says "drops the final condition" names
    nothing checkable, and guessing which clause it meant would put this file
    in the business of interpreting the judge - which is the thing it exists to
    avoid. Unquoted claims are invisible here and that is a stated limit, not
    an oversight.
    """
    reasoning = the_reasoning_without_the_verdict(reply)
    if not SAYS_SOMETHING_WAS_DROPPED.search(reasoning):
        return []
    return [
        found.strip()
        for found in QUOTED.findall(reasoning)
        if len(found.strip()) >= SHORTEST_CHECKABLE_CLAUSE
    ]


def _flattened(text: str) -> str:
    """Lowercased, with runs of whitespace and curly quotes normalised, so a
    clause quoted with a different apostrophe still matches the text it came
    from."""
    text = (text or "").replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("‑", "-").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip().lower()


def why_this_verdict_contradicts_the_rewrite(reply: str, rewrite: str) -> str | None:
    """The reason this verdict cannot stand, or None.

    Returns a sentence naming the clause and quoting where it still is, because
    a refusal a reader cannot check is the same failure one layer up.
    """
    for clause in the_clauses_the_reply_says_were_dropped(reply):
        if _flattened(clause) in _flattened(rewrite):
            return (
                f"the verdict says {clause!r} was dropped, and {clause!r} is "
                "still in the rewrite word for word"
            )
    return None


def why_this_keep_cannot_stand(
    verdict: str | None, reply: str, rewrite: str
) -> str | None:
    """The wall itself, and it only ever looks at a KEEP.

    THE ASYMMETRY IS STRUCTURAL, NOT A CALLER'S RESPONSIBILITY. A DROP verdict's
    reasoning routinely discusses what was NOT removed - "the rewrite retains
    the 'usually' qualifier, so it is not more permissive" is a correct DROP
    whose reasoning names a clause that is still there. Refusing those would be
    refusing the judge for being right. So the verdict is a parameter and the
    function returns None for anything that is not a KEEP, rather than trusting
    every future caller to remember.
    """
    if verdict != "KEEP":
        return None
    return why_this_verdict_contradicts_the_rewrite(reply, rewrite)


def the_contradiction_report(rows: list[dict]) -> dict:
    """Counts over graded rows, shaped so a caller cannot report a bare rate.

    `rows` are dicts with `got`, `reply` and `rewrite`. KEEP and DROP are
    counted separately on purpose: a wall that fires on DROP rows would be
    refusing verdicts it was never meant to see, and the number that says so
    has to be in the same report as the number that sells it.
    """
    kept = [row for row in rows if row.get("got") == "KEEP"]
    dropped = [row for row in rows if row.get("got") == "DROP"]
    return {
        "kept": len(kept),
        "kept_contradicted": sum(
            1 for row in kept
            if why_this_verdict_contradicts_the_rewrite(row.get("reply", ""), row.get("rewrite", ""))
        ),
        "dropped": len(dropped),
        "dropped_contradicted": sum(
            1 for row in dropped
            if why_this_verdict_contradicts_the_rewrite(row.get("reply", ""), row.get("rewrite", ""))
        ),
        "kept_with_no_quoted_clause": sum(
            1 for row in kept if not the_clauses_the_reply_says_were_dropped(row.get("reply", ""))
        ),
    }
