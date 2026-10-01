"""The second truth path, built after the first one produced a wrong rate.

`plant_the_defects.py` withdrew its `constraint` edit on 2026-09-05: a rule that
removes "a qualifying clause" cannot tell a widened promise from a shortened
answer, and four of its six pairs were lossy but TRUE. The published "1 of 6
constraint recall" was a correct judge scored against a wrong key.

So this key is smaller and written out span by span, and the tests below check
the two things a reader cannot: that every span still has exactly one home in
the owner's answers, and that no rewrite carries a punctuation scar. The third
thing - whether removing the span really widens the promise - is ASSERTED, is
recorded in each row's own words, and is falsifiable by a reader disagreeing.
"""

from __future__ import annotations

import json
import unittest

import support

deletions = support.import_file(
    "over_promise_deletions",
    support.REPO_ROOT / "scripts" / "over_promise_deletions.py",
)

#: The owner's real answers. `runs/` is gitignored, so this file exists on the
#: machine that produced it and on no other checkout - and read at import time
#: its absence is an ImportError that takes the whole module down and turns the
#: shared gate red for anybody who has not run that job. A precondition a
#: checkout cannot satisfy is a SKIP, not an error. Borrowed from
#: `test_a_planted_defect_is_really_a_defect.py`, where it was fixed first.
_ANSWERS = support.REPO_ROOT / "runs" / "honest-path" / "train.jsonl"
REAL = (
    [
        json.loads(line)["response"]
        for line in _ANSWERS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if _ANSWERS.is_file()
    else []
)

#: Named so a skipped run says which artifact is missing and how to make it.
NEEDS_THE_REAL_ANSWERS = unittest.skipUnless(
    REAL, f"{_ANSWERS} is not in this checkout (runs/ is gitignored); "
    "run the honest-path job to produce it"
)


@NEEDS_THE_REAL_ANSWERS
class NoRewriteCarriesAPunctuationScarTest(unittest.TestCase):
    """The tell that sank the withdrawn generator. Two of its six pairs read
    "If it is Underlining or highlighting makes it unsellable" - and the ONE
    pair of six the judge dropped was one of those two fragments. A judge
    ruling on how a pair looks is measuring the artefact."""

    def test_every_shipped_rewrite_is_clean(self):
        for pair in deletions.the_deletion_pairs(REAL):
            with self.subTest(edit=pair["edit"]):
                self.assertIsNone(
                    deletions.why_this_rewrite_is_malformed(pair["rejected"])
                )

    def test_the_scar_check_can_fail(self):
        """A check nothing can fail is not a check. These are the exact shapes
        the withdrawn generator produced."""
        for bad in ("We do, . Add a note.", "We do, but only editions and. Bring them.",
                    "If it is unmarked and, yes."):
            with self.subTest(bad=bad):
                self.assertIsNotNone(deletions.why_this_rewrite_is_malformed(bad))


@NEEDS_THE_REAL_ANSWERS
class EverySpanHasExactlyOneHomeTest(unittest.TestCase):
    def test_a_span_with_two_homes_is_refused_when_nothing_says_which(self):
        """`for 48 hours` limits a promise in the hold answer AND in the
        reservation answer. Picking one would make the edit depend on file
        order, so an unanchored span with two homes resolves to nothing."""
        self.assertGreater(
            len({a for a in REAL if " for 48 hours" in a}), 1,
            "the ambiguity this rule exists for",
        )
        self.assertIsNone(
            deletions.the_answer_this_span_belongs_to(REAL, "", " for 48 hours")
        )

    def test_a_span_with_no_home_resolves_to_nothing(self):
        self.assertIsNone(
            deletions.the_answer_this_span_belongs_to(REAL, "", " within a fortnight")
        )

    def test_an_anchor_resolves_a_span_that_lives_in_two_answers(self):
        """AND THE REFUSAL WAS TOO BLUNT ON ITS OWN. Refusing `for 48 hours`
        outright cost two good rows, because the span limits a real promise in
        both answers. The anchor names which answer, and the pair must still
        have exactly one home."""
        edits = [p["edit"] for p in deletions.the_deletion_pairs(REAL)]
        self.assertEqual(
            sum(1 for e in edits if "for 48 hours" in e), 2,
            "both homes of the span should be placed once each",
        )
        rewrites = {
            p["rejected"] for p in deletions.the_deletion_pairs(REAL)
            if "for 48 hours" in p["edit"]
        }
        self.assertEqual(len(rewrites), 2, "two answers, two distinct rewrites")

    def test_the_unplaced_report_accounts_for_every_missing_span(self):
        """THE ARITHMETIC THAT MUST ADD UP. placed + unplaced == the table."""
        placed = deletions.the_deletion_pairs(REAL)
        unplaced = deletions.spans_that_could_not_be_placed(REAL)
        self.assertEqual(len(placed) + len(unplaced), len(deletions.DELETIONS))

    def test_every_unplaced_span_carries_its_reason(self):
        for span, reason in deletions.spans_that_could_not_be_placed(REAL):
            with self.subTest(span=span):
                self.assertTrue(reason.strip())


@NEEDS_THE_REAL_ANSWERS
class EveryRowSaysWhyItIsADefectTest(unittest.TestCase):
    """The row's own words are the falsifier. A reader who disagrees with one
    takes it out of the denominator and the run is re-reported - which is only
    possible because the reason is written down beside the pair."""

    def test_each_pair_names_the_promise_it_widened(self):
        for pair in deletions.the_deletion_pairs(REAL):
            with self.subTest(edit=pair["edit"]):
                self.assertTrue(pair["why"].strip())
                self.assertIn("promised", pair["why"])

    def test_each_pair_stamps_its_label_as_asserted_not_measured(self):
        for pair in deletions.the_deletion_pairs(REAL):
            with self.subTest(edit=pair["edit"]):
                self.assertTrue(pair["provenance"].startswith("ASSERTED"))

    def test_no_rewrite_equals_its_own_source(self):
        for pair in deletions.the_deletion_pairs(REAL):
            with self.subTest(edit=pair["edit"]):
                self.assertNotEqual(pair["rejected"].strip(), pair["chosen"].strip())

    def test_every_rewrite_really_is_shorter(self):
        """The operational difference from the four surviving substitution
        edits, which leave every sentence standing."""
        for pair in deletions.the_deletion_pairs(REAL):
            with self.subTest(edit=pair["edit"]):
                self.assertLess(len(pair["rejected"]), len(pair["chosen"]))

    def test_the_set_is_big_enough_to_report_and_small_enough_to_read(self):
        n = len(deletions.the_deletion_pairs(REAL))
        self.assertGreaterEqual(n, 8, "too few rows to report a rate")
        self.assertLessEqual(n, 20, "too many rows for a person to check each one")


if __name__ == "__main__":
    unittest.main()
