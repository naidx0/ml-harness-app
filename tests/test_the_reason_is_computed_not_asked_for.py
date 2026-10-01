"""Clause (1) is a question about two strings, so it is answered without a model.

MEASURED 2026-09-05. Asked to grade 72 rewrites that are not degradations at
all, the pipeline's judge kept 19, and every one of the 19 named a clause the
rewrite still contains word for word. Beside the 2026-09-04 result — where the
same instrument invented a QUOTATION from an empty rewrite — its prose is
decoupled from the text in both directions.

So the reason for a verdict is computed from the two texts, and a rewrite that
changed nothing of the named kind never reaches the judge at all.
"""

from __future__ import annotations

import json
import unittest

import support

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


class TheKindOfChangeIsReadOffTheTextTest(unittest.TestCase):
    def test_a_removed_full_stop_is_punctuation_and_nothing_else(self):
        """THE ROW THAT STARTED THIS. The judge said this rewrite 'drops the
        "over 25.00" condition'. It drops a full stop."""
        real = "Tracked is 2.20 extra and I would recommend it for anything over 25.00."
        self.assertEqual(
            diff.what_changed(real, real[:-1]), diff.ONLY_PUNCTUATION_MOVED
        )

    def test_a_number_written_as_a_word_is_not_punctuation(self):
        """The label has to be TRUE. `two` -> `2` leaves the token lists equal
        because number words are normalised, and calling that "punctuation
        only" would be this module writing the kind of plausible sentence about
        a change that did not happen that it exists to stop."""
        self.assertEqual(
            diff.what_changed("We take two boxes.", "We take 2 boxes."),
            diff.ONLY_WORDING_MOVED,
        )

    def test_a_contraction_is_wording(self):
        self.assertEqual(
            diff.what_changed("We do not sell those.", "We don't sell those."),
            diff.ONLY_WORDING_MOVED,
        )

    def test_swapped_sentences_are_order(self):
        self.assertEqual(
            diff.what_changed("We open at ten. The counter shuts at four.",
                              "The counter shuts at four. We open at ten."),
            diff.ONLY_ORDER_MOVED,
        )

    def test_a_dropped_clause_is_content_removed(self):
        self.assertEqual(
            diff.what_changed(
                "You can return it within 30 days for credit.",
                "You can return it for credit.",
            ),
            diff.CONTENT_WAS_REMOVED,
        )

    def test_a_changed_number_is_a_substitution(self):
        self.assertEqual(
            diff.what_changed("Returns within 30 days.", "Returns within 60 days."),
            diff.CONTENT_WAS_SUBSTITUTED,
        )

    def test_a_decimal_survives_tokenising(self):
        """`6.50` must stay one token, which is why the tokeniser matches
        decimals explicitly rather than allowing dots into every word - the
        first version did the latter and glued sentence stops onto words."""
        self.assertEqual(
            diff.what_changed("Ireland is 6.50 for 2kg.", "Ireland is 13 for 2kg."),
            diff.CONTENT_WAS_SUBSTITUTED,
        )


class TheAccountCannotNameSomethingThatIsStillThereTest(unittest.TestCase):
    """The account replaces the judge's prose, so its one required property is
    that it is derived from the text rather than written about it."""

    def test_the_account_of_a_deletion_lists_the_words_that_went(self):
        said = diff.the_account_of_this_pair(
            "You can return it within 30 days for credit.",
            "You can return it for credit.",
        )
        self.assertIn("within", said)
        self.assertIn("30", said)

    def test_the_account_of_a_punctuation_change_claims_nothing_more(self):
        real = "Tracked is 2.20 extra for anything over 25.00."
        said = diff.the_account_of_this_pair(real, real[:-1])
        self.assertIn("punctuation", said)
        self.assertNotIn("drops", said)

    def test_every_word_the_account_says_went_really_is_gone(self):
        """The property the judge failed. Asserted over every planted pair."""
        for pair in plant.plant(REAL, per_type=99) if REAL else []:
            lost = diff.the_words_the_rewrite_lost(pair["chosen"], pair["rejected"])
            rewritten = " ".join(
                diff._words(diff._normalised(pair["rejected"]))
            ).split()
            for word in lost:
                with self.subTest(edit=pair["edit"], word=word):
                    self.assertLess(
                        rewritten.count(word),
                        " ".join(diff._words(diff._normalised(pair["chosen"]))).split().count(word),
                        f"{word!r} was reported lost but is not less frequent",
                    )


@NEEDS_THE_REAL_ANSWERS
class TheGateAdmitsDefectsAndRefusesNonDegradationsTest(unittest.TestCase):
    """Measured on every set this repository has, with no model.

    A gate that refused everything would spare the judge and lose every defect;
    a gate that admitted everything would change nothing. Both directions are
    asserted, and the numbers are the ones recorded in the preregistration.
    """

    def test_no_planted_defect_is_refused_by_the_rule(self):
        planted = plant.plant(REAL, per_type=99)
        lost = [
            p for p in planted
            if diff.why_this_pair_never_reaches_the_judge(p["chosen"], p["rejected"])
        ]
        self.assertEqual(lost, [], "the rule threw away a real defect")
        self.assertGreaterEqual(len(planted), 30)

    def test_no_over_promise_deletion_is_refused_by_the_rule(self):
        deletions = overs.the_deletion_pairs(REAL)
        lost = [
            p for p in deletions
            if diff.why_this_pair_never_reaches_the_judge(p["chosen"], p["rejected"])
        ]
        self.assertEqual(lost, [])
        self.assertGreaterEqual(len(deletions), 16)

    def test_every_surface_keep_is_refused_before_a_judge_is_asked(self):
        keeps = plant.keeps_that_are_not_deletions(REAL, per_type=99)
        admitted = [
            k for k in keeps
            if not diff.why_this_pair_never_reaches_the_judge(k["chosen"], k["rejected"])
        ]
        self.assertEqual(admitted, [])
        self.assertGreaterEqual(len(keeps), 30)

    def test_the_refusal_says_why_so_a_reader_can_check_it(self):
        said = diff.why_this_pair_never_reaches_the_judge(
            "We open at ten.", "We open at ten"
        )
        self.assertIsNotNone(said)
        self.assertIn("no judge is asked", said)


if __name__ == "__main__":
    unittest.main()
