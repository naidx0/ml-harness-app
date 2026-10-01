"""A KEEP whose stated removal is still in the text is a verdict without evidence.

## What this exists for

Measured 2026-09-07 on `runs/judge-sentinel-n/results.jsonl`, a set where every
row's correct answer is DROP:

| | count |
|---|---|
| false keeps | **19 of 72** |
| whose reply justifies itself by a **removal** | **19 of 19** |
| which quote a span for that removal | 15 |
| where the quoted span is **still in both texts** | **14** |
| where the quoted span was genuinely gone | 1 |

**The judge is not misapplying its rule. It is applying its rule correctly to a
deletion it invented.** It says *"drops the 'Send me the ISBN' requirement"* about
a rewrite in which that phrase is still present, word for word - and then reasons
soundly from the removal it imagined. The rows it gets right say the opposite in
the same confident voice, so the failure is not in the reasoning step at all.
It is in the perception of what changed.

That is checkable without asking anybody. **A deterministic rule that catches the
judge being wrong is worth more than a better judge**: it costs nothing per row
and it cannot itself drift.

## The two conditions, and the first version had neither

A reply that says *replaces "most between 1.50 and 4.00" with "all between 1.50
and 4.00"* quotes the REPLACEMENT, not the removal. A rule that takes any quoted
span reads the new text as the deleted text and announces it is "still present" -
which it is, because it is the new text. That version reported 8 false positives
on 170 genuine degradations and every one of them was the rule's fault.

So a span counts only when:

1. it is **governed by the removal verb** - within `THE_WINDOW` characters after
   it, not merely somewhere in the same reply, and
2. it is present in the **original as well as** the rewrite. Present in the
   rewrite alone means the judge quoted the new wording.

**A DETECTOR THAT READS A REPLACEMENT AS A DELETION IS MAKING THE EXACT ERROR IT
WAS BUILT TO CATCH.** With both conditions: 14 of 19 caught, 0 of 53 correct
DROPs disturbed, 2 of 170 genuine degradations touched.

## What it does NOT claim

It voids a **justification**, not a verdict. On a set where every answer should be
DROP the two coincide, because a KEEP is wrong whatever its reasoning. On real
degradations they can come apart: a row can be a genuine degradation that the
judge kept for a confabulated reason, and 2 of 170 are exactly that. `THE_STAGE`
is its own report column for this reason - it is evidence about the judge, and it
is not by itself a decision about the row.
"""

from __future__ import annotations

import re

#: This check's own column in a report. It is not the validator's and not the
#: judge's: a rule that reported under somebody else's name would have its
#: refusals read as theirs, which is how a stage's numbers stop being its own.
THE_STAGE = "refuted-removal"

#: How far after the removal verb a quoted span still counts as its object.
#: Sixty characters holds "drops the 'under your name' and 48-hour limits" and
#: excludes a replacement quoted later in the same sentence. It is a threshold
#: and it was fixed before the numbers were read.
THE_WINDOW = 60

#: The verbs that assert something was taken out. Deliberately not `changed`,
#: `replaced` or `rewrote` - those describe a substitution, where the new text
#: being present proves nothing at all.
A_REMOVAL = re.compile(
    r"\b(?:drops?|dropping|removes?|removing|omits?|omitting|deletes?|deleting|strips?)\b",
    re.I,
)

#: Straight and curly quotes both, because the model emits both in one reply.
#: Four characters minimum: shorter spans match too much of any text.
A_QUOTED_SPAN = re.compile(r"[“‘\"']([^”’\"']{4,80})[”’\"']")


def _comparable(text: str) -> str:
    """Letters and digits only, single-spaced.

    So `"over 25.00"` matches `over 25.00,` and a curly apostrophe matches a
    straight one. The judge quotes with the punctuation it feels like using.
    """
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def the_removal_the_text_refutes(reply: str, original: str, rewrite: str) -> str | None:
    """The span the reply says was removed, when both texts still contain it.

    None when the reply claims no removal, quotes nothing for it, or names a
    span that really is gone - all three are silences rather than findings.
    """
    before, after = _comparable(original), _comparable(rewrite)
    if not before or not after:
        return None
    for verb in A_REMOVAL.finditer(str(reply or "")):
        governed = str(reply)[verb.end(): verb.end() + THE_WINDOW]
        for span in A_QUOTED_SPAN.findall(governed):
            wanted = _comparable(span)
            if wanted and wanted in after and wanted in before:
                return span
    return None


def why_this_keep_has_no_evidence(reply: str, original: str, rewrite: str) -> str | None:
    """The sentence for a KEEP resting on a removal that did not happen."""
    span = the_removal_the_text_refutes(reply, original, rewrite)
    if span is None:
        return None
    return (
        f"this KEEP says {span!r} was removed, and {span!r} is still in the "
        f"rewrite AND in the original - so the removal it reasons from did not "
        f"happen. Measured on sentinel-N: every one of 19 false keeps justified "
        f"itself by a removal, and where the claim was checkable it was false 14 "
        f"times out of 15. The verdict may still be right for another reason; "
        f"what is established is that THIS reason is not one."
    )
