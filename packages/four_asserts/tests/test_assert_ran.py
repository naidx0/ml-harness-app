"""The counting check, including the case the count cannot see."""

from __future__ import annotations

import unittest

from four_asserts import DID_NOT_SAY, FAILED, GREEN, assert_ran, count_leaves, pending


class AssertRanTest(unittest.TestCase):
    def test_a_full_green_run(self):
        ran = assert_ran(3822, 3822)
        self.assertEqual(ran.exit_code, GREEN)
        self.assertIn("3822 of 3822", ran.verdict)

    def test_the_measured_collision(self):
        """The numbers this exists for: a run that printed OK."""
        ran = assert_ran(3822, 3315)
        self.assertEqual(ran.exit_code, DID_NOT_SAY)
        self.assertIn("507", ran.verdict)
        self.assertIn("3315 of 3822", ran.verdict)

    def test_one_missing_case_is_already_not_green(self):
        self.assertEqual(assert_ran(3822, 3821).exit_code, DID_NOT_SAY)

    def test_a_failing_run_is_red_for_its_own_reason(self):
        ran = assert_ran(10, 10, failures=1)
        self.assertEqual(ran.exit_code, FAILED)
        self.assertIn("all 10 of 10 ran", ran.verdict)

    def test_a_count_mismatch_outranks_a_failure(self):
        """If cases went missing, the failures that did run are not the whole
        story, so the missing cases are what gets reported."""
        ran = assert_ran(10, 8, failures=1)
        self.assertEqual(ran.exit_code, DID_NOT_SAY)
        self.assertIn("never ran", ran.verdict)

    def test_an_unimported_module_is_not_green_even_when_the_counts_agree(self):
        """THE CASE THE COUNT CANNOT SEE. A module replaced by one placeholder
        is discovered and run like anything else, so the totals agree over a
        smaller tree than the one on disk."""
        ran = assert_ran(3958, 3958, unimported=("tests.test_a_thing",))
        self.assertTrue(ran.counts_agree)
        self.assertFalse(ran.said_what_it_holds)
        self.assertEqual(ran.exit_code, DID_NOT_SAY)
        self.assertIn("test_a_thing", ran.verdict)

    def test_every_verdict_carries_its_denominator(self):
        """A number without its denominator is the shape of the original
        defect: '3,315 tests, OK' is true and useless."""
        for ran in (
            assert_ran(10, 10),
            assert_ran(10, 8),
            assert_ran(10, 10, failures=2),
            assert_ran(10, 10, unimported=("m",)),
        ):
            with self.subTest(ran.verdict):
                self.assertIn("10", ran.verdict)

    def test_the_pending_line_does_not_look_like_a_verdict(self):
        """It is printed BEFORE the work, so a killed run cannot read as a
        pass. If it began with the same word as a verdict, a truncated log
        would end on something that looks like one."""
        said = pending()
        self.assertFalse(said.startswith(("GREEN", "RED")))
        self.assertIn("did not finish", said)

    def test_leaves_are_counted_through_nesting(self):
        class Case(unittest.TestCase):
            def test_one(self):
                pass

            def test_two(self):
                pass

        inner = unittest.TestSuite([Case("test_one"), Case("test_two")])
        outer = unittest.TestSuite([inner, Case("test_one")])
        self.assertEqual(count_leaves(outer), 3)
        self.assertEqual(count_leaves(unittest.TestSuite()), 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
