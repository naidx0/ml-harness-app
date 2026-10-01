"""The class of defect that had no backstop, and now has one.

MEASURED 2026-09-05. Of the four planted defects the pipeline's judge wrongly
kept, `specifics_the_rewrite_adds` catches one, the diff gate correctly admits
all four, and three are caught by nothing:

    We no longer take cheques.  ->  We still take cheques.        KEPT

The shop does not take cheques. That row would have entered a preference corpus
as an acceptable degradation.
"""

from __future__ import annotations

import json
import unittest

import support

inverted = support.import_file(
    "an_inverted_refusal", support.REPO_ROOT / "scripts" / "an_inverted_refusal.py"
)
diff = support.import_file(
    "what_actually_changed",
    support.REPO_ROOT / "scripts" / "what_actually_changed.py",
)
plant = support.import_file(
    "plant_the_defects", support.REPO_ROOT / "scripts" / "plant_the_defects.py"
)
overs = support.import_file(
    "over_promise_deletions",
    support.REPO_ROOT / "scripts" / "over_promise_deletions.py",
)

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
NEEDS_THE_REAL_ANSWERS = unittest.skipUnless(
    REAL, f"{_ANSWERS} is not in this checkout (runs/ is gitignored)"
)


class TheThreeRowsNothingElseCatchesTest(unittest.TestCase):
    """Verbatim from `runs/judge-clause-one/results.jsonl`."""

    def test_a_refusal_inverted_to_a_promise(self):
        said = inverted.the_refusal_this_rewrite_inverted(
            "Underlining or highlighting makes it unsellable, so those we cannot take back.",
            "Underlining or highlighting makes it unsellable, so those we can take back.",
        )
        self.assertIsNotNone(said)
        self.assertIn("reverses the refusal", said)

    def test_no_longer_inverted_to_still(self):
        self.assertIsNotNone(
            inverted.the_refusal_this_rewrite_inverted(
                "We no longer take cheques. Card, cash and bank transfer are all fine.",
                "We still take cheques. Card, cash and bank transfer are all fine.",
            )
        )

    def test_do_not_inverted_to_do(self):
        self.assertIsNotNone(
            inverted.the_refusal_this_rewrite_inverted(
                "Codes stop working the day after they expire and they do not stack with the sale shelf.",
                "Codes stop working the day after they expire and they do stack with the sale shelf.",
            )
        )


class AContractionIsNotAnInversionTest(unittest.TestCase):
    """THE FIVE FALSE POSITIVES THAT FAILED THE FIRST VERSION against its own
    preregistration. `do not` -> `don't` loses the tokens `do` and `not` and
    gains one, so a contraction read as a reversed refusal."""

    def test_do_not_to_dont_does_not_fire(self):
        self.assertIsNone(
            inverted.the_refusal_this_rewrite_inverted(
                "We do not sell digital audio.", "We don't sell digital audio."
            )
        )

    def test_cannot_to_cant_does_not_fire(self):
        self.assertIsNone(
            inverted.the_refusal_this_rewrite_inverted(
                "Underlining makes it unsellable, so those we cannot take back.",
                "Underlining makes it unsellable, so those we can't take back.",
            )
        )

    def test_the_two_contraction_lists_agree(self):
        """Two copies of one list is how a rule starts disagreeing with itself.
        Every pair here must mean the same as the one in the diff module."""
        mine = {short: long for short, long in inverted.CONTRACTIONS}
        #: FIRST ENTRY WINS, because `_normalised` applies the pairs in order
        #: with `str.replace` - by the time `("can not", "can't")` is reached,
        #: `("cannot", "can't")` has already consumed every `can't`. Building
        #: this the obvious way and letting the last entry win made the test
        #: report a disagreement that the module does not actually have.
        theirs: dict[str, str] = {}
        for long, short in diff.SAME_WORDING:
            theirs.setdefault(short, long)
        for short, long in mine.items():
            if short in theirs:
                with self.subTest(short=short):
                    self.assertEqual(long, theirs[short])


class ADeletedClauseIsNotAnInversionTest(unittest.TestCase):
    """The bound is what makes this a check rather than a guess: removing a
    clause removes the negations inside it, and that is the named degradation,
    not a reversal."""

    def test_a_whole_clause_carrying_a_negation_does_not_fire(self):
        self.assertIsNone(
            inverted.the_refusal_this_rewrite_inverted(
                "Codes stop working the day after they expire and they do not stack with the sale shelf.",
                "Codes stop working the day after they expire.",
            )
        )

    def test_a_sentence_that_is_simply_gone_does_not_fire(self):
        self.assertIsNone(
            inverted.the_refusal_this_rewrite_inverted(
                "We do, up to two boxes. Please no encyclopaedias, as we cannot sell those.",
                "We do, up to two boxes.",
            )
        )


@NEEDS_THE_REAL_ANSWERS
class TheMeasuredNumbersAreLockedTest(unittest.TestCase):
    """The preregistered decision rule: 6 of 6 caught, 0 of 155 false. One
    false positive fails it, because this refuses a pair before any judge sees
    it and a wrong refusal silently removes a defect from the corpus."""

    def _rows(self):
        planted = plant.plant(REAL, per_type=99)
        return (
            [p for p in planted if p["edit_type"] == "negation"],
            [p for p in planted if p["edit_type"] != "negation"],
        )

    def test_it_catches_every_planted_inversion(self):
        negations, _ = self._rows()
        caught = [
            p for p in negations
            if inverted.the_refusal_this_rewrite_inverted(p["chosen"], p["rejected"])
        ]
        self.assertEqual(len(caught), len(negations))
        self.assertGreaterEqual(len(negations), 6)

    def test_it_fires_on_nothing_else_in_the_repository(self):
        _, others = self._rows()
        sets = [
            others,
            plant.keeps_that_are_not_deletions(REAL, per_type=99),
            overs.the_deletion_pairs(REAL),
        ]
        fired = [
            inverted.the_refusal_this_rewrite_inverted(row["chosen"], row["rejected"])
            for rows in sets for row in rows
        ]
        self.assertEqual([f for f in fired if f], [])
        self.assertGreaterEqual(sum(len(rows) for rows in sets), 80)

    def test_the_reason_names_both_sentences_so_a_reader_can_check_it(self):
        negations, _ = self._rows()
        said = inverted.the_refusal_this_rewrite_inverted(
            negations[0]["chosen"], negations[0]["rejected"]
        )
        self.assertIn("the real answer says", said)
        self.assertIn("the rewrite says", said)


if __name__ == "__main__":
    unittest.main()
