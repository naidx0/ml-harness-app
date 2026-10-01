"""Planted case 6: a job of 72 calls reports 72, not 71.

    6. The record count. A job of 72 calls with one killed mid-stream:
       expected `calls 72 of 72 requested` with one aborted row, not 71.

The same law as the counting gate, which exists because a suite reported
`Ran 3315 tests ... OK` when discovery found 3,822. A call that did not finish
is still a call.
"""

from __future__ import annotations

import unittest

import support

record = support.import_file(
    "card_owner_the_record", support.REPO_ROOT / "card_owner" / "the_record.py"
)


def rows(answered=0, refused=0, void=0, aborted=0):
    out = []
    for name, many in (
        (record.ANSWERED, answered),
        (record.REFUSED, refused),
        (record.VOID, void),
        (record.ABORTED, aborted),
    ):
        out.extend({"outcome": name} for _ in range(many))
    return out


class TheKilledCallIsStillCountedTest(unittest.TestCase):
    """The case verbatim: 72 asked for, one killed mid-stream."""

    def test_seventy_two_of_seventy_two(self):
        tally = record.the_tally(72, rows(answered=71, aborted=1))
        self.assertEqual(tally.accounted, 72)
        self.assertTrue(tally.complete)
        self.assertIsNone(record.why_this_record_is_red(tally))

    def test_the_line_says_seventy_two_and_shows_the_split(self):
        said = record.the_calls_line(record.the_tally(72, rows(answered=71, aborted=1)))
        self.assertIn("calls 72 of 72 requested", said)
        self.assertIn("1 aborted", said)

    def test_dropping_the_aborted_row_is_red(self):
        """THE FAILURE THIS CASE EXISTS FOR: 71 true rows, and the collection
        a lie by omission."""
        tally = record.the_tally(72, rows(answered=71))
        self.assertFalse(tally.complete)
        said = record.why_this_record_is_red(tally)
        self.assertIn("1 call(s) of 72 are in no outcome", said)
        self.assertIn("3,315 of 3,822", said)

    def test_an_aborted_row_is_written_when_it_happens(self):
        row = record.an_aborted_row(41, "the stream closed after 12 tokens")
        self.assertEqual(row["outcome"], record.ABORTED)
        self.assertEqual(row["index"], 41)
        self.assertIn("12 tokens", row["why"])
        self.assertIn("none should be inferred", row["note"])


class EveryCallEndsInExactlyOneOutcomeTest(unittest.TestCase):
    def test_the_four_outcomes_sum_to_the_ask(self):
        tally = record.the_tally(72, rows(answered=60, refused=6, void=5, aborted=1))
        self.assertTrue(tally.complete)
        self.assertEqual(tally.accounted, 72)

    def test_a_row_with_an_outcome_nobody_named_is_not_counted(self):
        """It is not silently absorbed either: the tally comes up short and the
        record goes red, which is what makes an unnamed outcome visible."""
        tally = record.the_tally(2, [{"outcome": "maybe"}, {"outcome": record.ANSWERED}])
        self.assertEqual(tally.accounted, 1)
        self.assertIsNotNone(record.why_this_record_is_red(tally))

    def test_a_row_with_no_outcome_at_all_is_not_counted(self):
        tally = record.the_tally(1, [{}])
        self.assertFalse(tally.complete)

    def test_more_rows_than_calls_is_also_red(self):
        """Counted twice is not a smaller kind of wrong than counted once."""
        tally = record.the_tally(2, rows(answered=3))
        said = record.why_this_record_is_red(tally)
        self.assertIn("counted twice", said)

    def test_the_outcome_list_is_closed(self):
        """A fifth outcome is a change to the list AND to the tests that count
        it. An outcome nobody named cannot appear by accident."""
        self.assertEqual(
            set(record.EVERY_OUTCOME),
            {record.ANSWERED, record.REFUSED, record.VOID, record.ABORTED},
        )


class ARefusedOrVoidCallIsNotAMissingOneTest(unittest.TestCase):
    """The two zero-GPU outcomes are still outcomes: the owner decided, and a
    decision is a row."""

    def test_a_job_that_refused_everything_is_complete(self):
        tally = record.the_tally(72, rows(refused=72))
        self.assertTrue(tally.complete)
        self.assertIn("72 refused", record.the_calls_line(tally))

    def test_a_job_that_voided_everything_is_complete(self):
        tally = record.the_tally(72, rows(void=72))
        self.assertTrue(tally.complete)
        self.assertIn("72 void", record.the_calls_line(tally))

    def test_a_job_of_nothing_is_complete_and_says_so(self):
        tally = record.the_tally(0, [])
        self.assertTrue(tally.complete)
        self.assertIn("calls 0 of 0 requested", record.the_calls_line(tally))


if __name__ == "__main__":
    unittest.main()
