"""Planted case: a report line carrying a bare count goes red.

    every count the harness prints or writes to a report carries the key it is
    distinct over, or the word "rows" where it is not, so a reader can never
    again take a row count for a corpus size

WHAT THIS EXISTS FOR. `kept: 164` was read as 164 training examples for two
days. It was 127 distinct `(prompt, chosen, rejected)` triples; the 156 kept by
both judge passes were 119; the 95 that survived every gate were 60. One triple
appeared seven times. Every decision about whether the corpus was large enough
was made against a number that was counting the same row up to seven times, and
NOTHING IN THE LINE SAID SO - because `164` on its own says nothing about what
it counted.

The repair is not to count better. It is to make a count that does not say what
it counts impossible to print.
"""

from __future__ import annotations

import unittest

import support

counting = support.import_file(
    "a_count_says_what_it_counts",
    support.REPO_ROOT / "scripts" / "a_count_says_what_it_counts.py",
)


class ABareCountIsRedTest(unittest.TestCase):
    """THE PLANTED CASE."""

    def test_a_bare_count_is_refused(self):
        said = counting.why_this_line_hides_what_it_counts("kept: 164")
        self.assertIsNotNone(said)
        self.assertIn("164", said)

    def test_the_reason_names_the_failure_it_exists_for(self):
        said = counting.why_this_line_hides_what_it_counts("kept: 164")
        self.assertIn("distinct", said.lower())

    def test_it_does_not_catch_a_count_followed_by_the_next_label(self):
        """THE LIMIT, STATED RATHER THAN HIDDEN. `kept 164 dropped 36` is two
        bare counts and this check passes it, because telling a unit from the
        next field needs a lexicon and a check that guessed would be switched
        off the first time it was wrong. It catches the shape the real failure
        had - a number with NOTHING after it - and says so."""
        # Asserted on the structured result, not the sentence: the reason text
        # quotes `kept: 164` as its worked example, so a substring check against
        # the prose finds "164" whatever the finding was.
        self.assertEqual(
            counting.the_bare_counts_in("kept 164 dropped 36"),
            ["36"],
            "36 ends the line and is caught; 164 is followed by `dropped` and escapes",
        )

    def test_a_line_naming_a_distinct_key_passes_wherever_the_number_sits(self):
        self.assertIsNone(
            counting.why_this_line_hides_what_it_counts("the corpus, distinct triples: 63")
        )

    def test_an_index_is_not_a_count(self):
        self.assertIsNone(
            counting.why_this_line_hides_what_it_counts("judge pass 1: 11 rows")
        )

    def test_a_count_of_rows_passes(self):
        """`rows` is the honest word when a count is not distinct over
        anything - it says "these are rows and rows repeat"."""
        self.assertIsNone(counting.why_this_line_hides_what_it_counts("kept: 164 rows"))

    def test_a_count_distinct_over_a_key_passes(self):
        self.assertIsNone(
            counting.why_this_line_hides_what_it_counts(
                "kept: 127 distinct (prompt, chosen, rejected)"
            )
        )

    def test_the_word_must_follow_the_number_not_precede_it(self):
        """A line mentioning `rows` BEFORE the number does not qualify it: the
        count still ends the line saying nothing about itself."""
        said = counting.why_this_line_hides_what_it_counts("of the rows kept: 164")
        self.assertIsNotNone(said)

    def test_it_does_not_judge_whether_the_unit_is_the_right_one(self):
        """DELIBERATE LIMIT. Telling `164 rows` from `164 survived` needs a
        noun-verb distinction no regex holds, and a check that guessed would be
        switched off the first time it was wrong. A word after the number is the
        author's claim about what it counts; nothing after it is no claim."""
        self.assertIsNone(
            counting.why_this_line_hides_what_it_counts("164 survived"),
            "the check is guessing at parts of speech",
        )


class WhatDoesNotCountAsACountTest(unittest.TestCase):
    """A checker that flagged every digit would be turned off within a day."""

    def test_a_ratio_is_not_a_count(self):
        for line in ("pass rate: 0.82", "agreement 0.61 - 0.81", "yield 0.414"):
            with self.subTest(line=line):
                self.assertIsNone(counting.why_this_line_hides_what_it_counts(line))

    def test_a_percentage_is_not_a_count(self):
        self.assertIsNone(counting.why_this_line_hides_what_it_counts("kept 82% of them"))

    def test_a_duration_is_not_a_count(self):
        for line in ("wall 53.8 min", "median 0.54 ms", "held=2157", "240s deadline"):
            with self.subTest(line=line):
                self.assertIsNone(counting.why_this_line_hides_what_it_counts(line))

    def test_an_n_of_m_form_is_already_honest(self):
        """`72 of 72 requested` names its denominator, which is the thing a bare
        count is missing. The counting gate's own line must keep passing."""
        for line in ("calls 72 of 72 requested", "ran 4364 of 4364 discovered",
                     "46 of 72 comparable"):
            with self.subTest(line=line):
                self.assertIsNone(counting.why_this_line_hides_what_it_counts(line))

    def test_a_date_or_a_sha_is_not_a_count(self):
        for line in ("2026-09-06 10:52", "commit d8fcb24", "seed 20260906"):
            with self.subTest(line=line):
                self.assertIsNone(counting.why_this_line_hides_what_it_counts(line))

    def test_a_line_with_no_digits_passes(self):
        self.assertIsNone(counting.why_this_line_hides_what_it_counts("the card is free"))


class TheHelperWritesLinesThatPassTest(unittest.TestCase):
    """The point is not to reject lines, it is to make honest ones easy."""

    def test_a_row_count_says_rows(self):
        self.assertEqual(counting.a_count_of(164, "rows"), "164 rows")

    def test_a_distinct_count_names_its_key(self):
        self.assertEqual(
            counting.a_count_distinct_over(127, "(prompt, chosen, rejected)"),
            "127 distinct (prompt, chosen, rejected)",
        )

    def test_what_it_writes_passes_its_own_check(self):
        """The round trip, which is what makes the pair a rule rather than two
        opinions."""
        for line in (
            counting.a_count_of(164, "rows"),
            counting.a_count_of(0, "rows"),
            counting.a_count_distinct_over(127, "(prompt, chosen, rejected)"),
            counting.a_count_distinct_over(60, "triples"),
        ):
            with self.subTest(line=line):
                self.assertIsNone(counting.why_this_line_hides_what_it_counts(line))

    def test_a_distinct_count_refuses_to_be_written_without_a_key(self):
        """`127 distinct` is the same lie one word shorter."""
        with self.assertRaises(ValueError):
            counting.a_count_distinct_over(127, "")


class TheRealLinesThisWouldHaveCaughtTest(unittest.TestCase):
    """The lines this project actually printed, before and after."""

    def test_it_catches_what_was_printed_for_two_days(self):
        for line in ("kept: 164", "  kept                     164", "distinct_sources 47"):
            with self.subTest(line=line):
                self.assertIsNotNone(
                    counting.why_this_line_hides_what_it_counts(line),
                    f"{line!r} would still print a bare count",
                )

    def test_it_passes_the_lines_written_since(self):
        for line in (
            "the corpus, distinct triples: 63",
            "kept after all three gates and judge pass 1: 11 rows",
            "834 calls, 0 hangs",
            "calls 188 of 188 requested",
        ):
            with self.subTest(line=line):
                self.assertIsNone(counting.why_this_line_hides_what_it_counts(line))


if __name__ == "__main__":
    unittest.main()
