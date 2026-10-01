"""The resolution sentence must not call a sample the whole file.

MEASURED 2026-09-09. `run_eval` graded its default 50 rows of a 196-row eval
file and reported:

    "To resolve a 10-point difference this way you would need 193 rows, which
     is 143 more than you have."

The 196 rows were in the file it had just streamed to the end to compute the
fingerprint. A reader told that cannot act on it, because the one fix available
to them -- grade more of what is already there -- is exactly what the sentence
says is impossible. The number was right and the noun was wrong: 50 is what it
GRADED, not what it HAS.

It matters more than a wording quibble because of what the same run showed
beside it. `measure_baseline` scored 32.7% over 196 rows; `run_eval` scored 6%
over 50. Same file, same metric, same model. The sample is taken in file order
(`_plan`: `if len(chosen) < sample`), the file is grouped by family, and the
first sixty rows are the hardest one -- so the default sample was not a sample
of the set at all. A reader chasing that 26-point gap is sent, by this
sentence, to go and write more rows.
"""

from __future__ import annotations

import unittest

from app.tools.evals import resolution_for


class ASampleIsNotTheFile(unittest.TestCase):
    def test_a_short_sample_of_a_long_file_says_raise_the_sample(self) -> None:
        """THE REPORTED CASE. 50 graded, 196 available, 193 needed."""
        says = resolution_for(3, 50, 196)["says"]
        self.assertIn("which the file already has", says)
        self.assertIn("196", says)
        self.assertIn("graded 50", says)
        self.assertNotIn(
            "more than you have",
            says,
            "the file has them; only the sample did not take them",
        )

    def test_a_file_that_is_genuinely_too_small_still_says_so(self) -> None:
        """The old sentence is not deleted, it is narrowed to when it is true."""
        says = resolution_for(3, 20, 20)["says"]
        self.assertIn("more than you have", says)
        self.assertNotIn("Raise the sample", says)

    def test_a_file_with_enough_rows_all_graded_says_which_you_have(self) -> None:
        says = resolution_for(64, 196, 196)["says"]
        self.assertIn("which you have", says)
        self.assertNotIn("Raise the sample", says)
        self.assertNotIn("more than you have", says)

    def test_the_old_two_argument_call_still_works(self) -> None:
        """`available` is optional: every existing caller keeps its behaviour."""
        says = resolution_for(3, 20)["says"]
        self.assertIn("more than you have", says)

    def test_the_sentence_never_claims_a_file_has_fewer_rows_than_it_does(self) -> None:
        """The property under all of it, checked across a range rather than at a point."""
        for graded, available in ((10, 500), (50, 196), (100, 193), (192, 196)):
            says = resolution_for(graded // 3, graded, available)["says"]
            if "more than you have" in says:
                self.fail(
                    "said rows are missing while "
                    + str(available)
                    + " were available and "
                    + str(graded)
                    + " graded: "
                    + says
                )


if __name__ == "__main__":
    unittest.main()
