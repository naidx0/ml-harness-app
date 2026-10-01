"""A KEEP whose stated reason is contradicted by the rewrite is not a verdict.

MEASURED 2026-09-05 on 72 rows that are not degradations at all. The pipeline's
judge kept 19, and every one justified the verdict with a clause the rewrite
still contains word for word - "The rewrite drops the 'over 25.00' condition,
making the recommendation unconditional" about a rewrite whose only difference
from its source is a removed final full stop.

The mechanism is in our own prompt: `what_the_judge_is_shown` tells the judge
the rewrite "was supposed to be worse in exactly this way", so a primed judge
finds the named degradation whether or not it happened.

The wall is deterministic because the failure is: the judge NAMES the clause it
believes was dropped, and a clause still in the rewrite was not dropped.
"""

from __future__ import annotations

import json
import unittest

import support

wall = support.import_file(
    "a_verdict_must_not_contradict_the_rewrite",
    support.REPO_ROOT / "scripts" / "a_verdict_must_not_contradict_the_rewrite.py",
)

#: The measured run this wall was built from. `runs/` is gitignored, so a clean
#: checkout skips the cases that need it rather than failing to import - the
#: rule learned on this repository the same day.
_RESULTS = support.REPO_ROOT / "runs" / "judge-sentinel-n" / "results.jsonl"
MEASURED = (
    [
        json.loads(line)
        for line in _RESULTS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if _RESULTS.is_file()
    else []
)
NEEDS_THE_RUN = unittest.skipUnless(
    MEASURED, f"{_RESULTS} is not in this checkout (runs/ is gitignored); "
    "run the sentinel-N job to produce it"
)

#: Verbatim from the run, including the curly apostrophe the model used.
A_REAL_CONFABULATION = (
    'The rewrite drops the "over 25.00" condition, making the recommendation '
    "unconditional, which is more permissive while retaining all original "
    "facts and numbers.\nKEEP"
)
THE_REWRITE_IT_JUDGED = (
    "Standard post is untracked. Tracked is 2.20 extra and I would recommend "
    "it for anything over 25.00"
)


class AKeepThatNamesAPresentClauseIsRefusedTest(unittest.TestCase):
    def test_the_real_confabulation_is_refused(self):
        said = wall.why_this_keep_cannot_stand(
            "KEEP", A_REAL_CONFABULATION, THE_REWRITE_IT_JUDGED
        )
        self.assertIsNotNone(said)
        self.assertIn("over 25.00", said)

    def test_the_reason_names_the_clause_so_a_reader_can_check_it(self):
        """A refusal a reader cannot check is the same failure one layer up."""
        said = wall.why_this_keep_cannot_stand(
            "KEEP", A_REAL_CONFABULATION, THE_REWRITE_IT_JUDGED
        )
        self.assertIn("still in the rewrite", said)

    def test_a_keep_citing_a_clause_that_really_went_is_allowed(self):
        """THE OTHER HALF. A wall that refused every KEEP would pass the test
        above and be worthless."""
        self.assertIsNone(
            wall.why_this_keep_cannot_stand(
                "KEEP",
                'The rewrite drops the "within 30 days" deadline.\nKEEP',
                "you can return it for credit and use the credit on anything.",
            )
        )

    def test_curly_quotes_and_odd_hyphens_still_match(self):
        """The model used both quote styles and a non-breaking hyphen in one
        run. A clause that fails to match because of punctuation would clear a
        confabulation."""
        self.assertIsNotNone(
            wall.why_this_keep_cannot_stand(
                "KEEP",
                "The rewrite drops the “30‑day window”.\nKEEP",
                "returns inside the 30-day window are fine",
            )
        )


class ADropVerdictIsNeverRefusedTest(unittest.TestCase):
    """THE ASYMMETRY, AND IT IS STRUCTURAL. A DROP's reasoning routinely
    discusses what was NOT removed. This exact reply is from the run and is a
    CORRECT verdict correctly argued."""

    A_CORRECT_DROP = (
        "The rewrite retains the 'usually' qualifier, so it is not more "
        "permissive; condition (1) fails.\nDROP"
    )

    def test_a_correct_drop_is_left_alone(self):
        self.assertIsNone(
            wall.why_this_keep_cannot_stand(
                "DROP", self.A_CORRECT_DROP, "Ireland usually arrives in four days"
            )
        )

    def test_an_unreadable_verdict_is_left_alone(self):
        self.assertIsNone(
            wall.why_this_keep_cannot_stand(None, A_REAL_CONFABULATION, "over 25.00")
        )

    def test_the_verdict_word_is_not_read_as_a_claim_that_something_was_dropped(self):
        """THE BUG THIS TEST EXISTS FOR. The pattern for "something was
        dropped" matched the word DROP itself, so every DROP reply trivially
        looked like a deletion claim - it showed up as one flagged row whose
        reasoning was in fact right. The trailing verdict is stripped before the
        argument is read."""
        self.assertEqual(
            wall.the_clauses_the_reply_says_were_dropped(self.A_CORRECT_DROP), []
        )
        self.assertEqual(
            wall.the_reasoning_without_the_verdict("It retains the qualifier.\nDROP"),
            "It retains the qualifier.",
        )


class WhatThisWallCannotSeeTest(unittest.TestCase):
    """Stated limits, asserted so they stay limits rather than becoming
    surprises."""

    def test_an_unquoted_claim_is_invisible(self):
        """"drops the final condition" names nothing checkable, and guessing
        which clause was meant would put this file in the business of
        interpreting the judge."""
        self.assertIsNone(
            wall.why_this_keep_cannot_stand(
                "KEEP",
                "Rewrite drops the final condition, making it unconditional.\nKEEP",
                "Sale shelf sales are final, and that is written on the label",
            )
        )

    def test_a_fragment_shorter_than_the_floor_is_not_checked(self):
        self.assertEqual(
            wall.the_clauses_the_reply_says_were_dropped('It drops "no".\nKEEP'), []
        )


@NEEDS_THE_RUN
class TheMeasuredNumbersAreLockedTest(unittest.TestCase):
    """The wall against the run it was built from. These are not out-of-sample
    numbers - the quoted-clause floor was chosen after looking at these rows -
    and they are locked here so a later change to the pattern has to explain
    itself."""

    def test_it_catches_fifteen_of_the_nineteen_confabulated_keeps(self):
        report = wall.the_contradiction_report(MEASURED)
        self.assertEqual(report["kept"], 19)
        self.assertEqual(report["kept_contradicted"], 15)

    def test_it_refuses_no_drop_verdict_at_all(self):
        refused = [
            row for row in MEASURED
            if wall.why_this_keep_cannot_stand(
                row.get("got"), row.get("reply", ""), row.get("rewrite", "")
            )
            and row.get("got") == "DROP"
        ]
        self.assertEqual(refused, [])

    def test_the_four_it_misses_are_the_ones_that_quote_nothing(self):
        report = wall.the_contradiction_report(MEASURED)
        self.assertEqual(
            report["kept"] - report["kept_contradicted"],
            report["kept_with_no_quoted_clause"],
        )


if __name__ == "__main__":
    unittest.main()
