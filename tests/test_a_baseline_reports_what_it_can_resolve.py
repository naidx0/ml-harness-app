"""`measure_baseline` reports the resolution the product computes, not 1/n.

INVARIANT 3, AND THIS TOOL WAS BREAKING IT. It ended its reply with

    f"{asked} rows resolves a difference of about {1/asked:.0%} at best."

1/n is the GRANULARITY of a score - the smallest step it can take when one more
row is right. It is a true number and it was labelled with the wrong word.
"Resolves a difference" means something specific in this product and it is
computed: `app/tools/evals.py:resolution_for` does a Wilson interval and the
worst-case two-run threshold, and `docs/PRODUCT_SPEC.md` requires it be reported
alongside every score.

On thirty rows the two numbers are 3 points and 25 points. The tool printed the
3, on the very number gate G1 opens on and against which every later delta in
the thread is compared, and it printed it under the word that means the 25.

FOUND BY DRIVING THE LOOP, not by reading the file: a journey lane took a real
baseline and got "30 rows resolves a difference of about 3% at best" while
`evals.resolution_for(0, 30)` - the product's own instrument, already used by
`run_eval`, `score_retrieval`, `fit_a_tree` and the chunking sweep - said the
same run "cannot be told apart unless they differ by about 25 points".

The fix is not a reworded string. It is that there is ONE computation of what a
score resolves and every scorer calls it. The granularity survives under its own
name, because it is useful and was only ever mislabelled.
"""

from __future__ import annotations

import unittest

from app.tools import evals, measure


class TheTwoNumbersAreDifferentAndBothAreSaidTest(unittest.TestCase):
    def test_the_computed_resolution_is_not_one_over_n(self):
        """The measurement that makes this a defect rather than a preference."""
        computed = evals.resolution_for(0, 30)
        granularity = 1.0 / 30
        self.assertAlmostEqual(granularity, 0.0333, places=4)
        self.assertGreater(
            computed["resolves_a_difference_of_at_least_points"], 25.0
        )
        self.assertLess(computed["resolves_a_difference_of_at_least_points"], 26.0)
        self.assertGreater(
            computed["resolves_a_difference_of_at_least_points"] / 100.0,
            granularity * 7,
            "1/n understated what thirty rows resolve by a factor of seven",
        )

    def test_the_tool_calls_the_products_own_instrument(self):
        """Not a second copy of the arithmetic. The same function `run_eval` uses."""
        for correct, n in ((0, 30), (7, 10), (19, 20), (250, 500)):
            with self.subTest(correct=correct, n=n):
                self.assertEqual(
                    measure._resolution_for(correct, n),
                    evals.resolution_for(correct, n),
                )

    def test_the_resolution_is_a_block_and_not_a_sentence(self):
        """Every other scorer in the product returns this shape under this key.

        `classical.fit_a_tree`, `evals.run_eval`, `retrieval.score_retrieval` and
        the chunking sweep all put `evals.resolution_for(...)` under
        `result["resolution"]`, and their tests read `["ci_95"]`, `["n"]` and
        `["says"]` off it. `measure_baseline` returned a STRING there, so a
        surface that rendered the block for four tools and the sentence for the
        fifth had to know which was which - or, more likely, showed nothing.
        """
        block = measure._resolution_for(3, 30)
        for key in ("n", "ci_95", "half_width_points",
                    "resolves_a_difference_of_at_least_points",
                    "rows_for_a_10_point_difference", "method", "says"):
            self.assertIn(key, block)
        self.assertEqual(block["n"], 30)


class TheSourceSaysBothThingsUnderTheRightNamesTest(unittest.TestCase):
    """Asserted on the source, because the tool needs a live provider to run.

    A test that mocked a model to check a string would be checking the mock. What
    is actually at stake is which function computes the number and which word it
    is printed under, and both are visible in the file.
    """

    def setUp(self):
        import inspect

        whole = inspect.getsource(measure.measure_baseline)
        # COMMENTS ARE STRIPPED, because the comment that records this defect
        # quotes the defective line verbatim - which is the right thing for it
        # to do and would make a naive scan of the file fail on the fix.
        self.source = "\n".join(
            line for line in whole.splitlines() if not line.lstrip().startswith("#")
        )
        self.comments = "\n".join(
            line for line in whole.splitlines() if line.lstrip().startswith("#")
        )

    def test_the_one_over_n_claim_no_longer_wears_the_word_resolves(self):
        self.assertNotIn("rows resolves a difference of about", self.source)

    def test_the_defect_is_recorded_where_it_happened(self):
        """The comment quotes the line it replaced, so the next reader knows why."""
        self.assertIn("rows resolves a difference of about", self.comments)

    def test_the_granularity_is_kept_under_its_own_name(self):
        self.assertIn('"granularity"', self.source)
        self.assertIn("STEP SIZE", self.source)

    def test_the_resolution_travels_in_the_sentence_a_person_reads(self):
        """The old line ended "Report it with the score" and then put the number
        in a field nobody rendered, so the instruction was addressed to whoever
        was reading the JSON."""
        self.assertIn("{resolution['says']}", self.source)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
