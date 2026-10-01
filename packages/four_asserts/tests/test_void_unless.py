"""The verdict is void until its reason survives a rule."""

from __future__ import annotations

import unittest

from four_asserts import (
    NO_RULE,
    Verdict,
    account,
    added_word,
    changed_number,
    dropped_clause,
    inverted_negation,
    standard_register,
    void_unless,
)


class VoidUnlessTest(unittest.TestCase):
    def test_the_measured_fabrication_is_void(self):
        """THE CASE THIS EXISTS FOR. A verdict justified by a clause the
        rewrite still contains, where the only difference is a full stop."""
        before = "Recommend the upgrade for any order over 25.00."
        after = "Recommend the upgrade for any order over 25.00"
        v = Verdict(
            value="KEEP",
            reason="The rewrite drops the 'over 25.00' condition, making it unconditional.",
            before=before,
            after=after,
        )
        ruling = standard_register().check(v)
        self.assertTrue(ruling.void)
        self.assertEqual(ruling.rule, "dropped clause")
        self.assertIn("NOT present", ruling.why)

    def test_a_real_deletion_lets_the_verdict_stand(self):
        v = Verdict(
            value="KEEP",
            reason="The rewrite drops the 'over 25.00' condition.",
            before="Recommend the upgrade for any order over 25.00.",
            after="Recommend the upgrade.",
        )
        ruling = standard_register().check(v)
        self.assertTrue(ruling.stands)
        self.assertEqual(ruling.rule, "dropped clause")

    def test_a_reason_with_no_rule_is_void_and_says_which_kind_of_void(self):
        """'Nobody checked' and 'the check failed' are different facts, and
        collapsing them is how an unchecked field starts looking checked."""
        v = Verdict(value="KEEP", reason="It feels less helpful.", before="a", after="b")
        ruling = standard_register().check(v)
        self.assertTrue(ruling.void)
        self.assertEqual(ruling.why, NO_RULE)
        self.assertEqual(ruling.rule, "")

    def test_the_four_rules_on_pairs_they_are_about(self):
        self.assertTrue(dropped_clause("a b c", "a b"))
        self.assertFalse(dropped_clause("a b", "a b c"))

        self.assertTrue(added_word("a b", "a b c"))
        self.assertFalse(added_word("a b c", "a b"))

        self.assertTrue(changed_number("pay 25.00 now", "pay 30.00 now"))
        self.assertFalse(changed_number("pay 25.00 now", "now pay 25.00"))

        self.assertTrue(inverted_negation("do not send it", "send it"))
        self.assertTrue(inverted_negation("send it", "never send it"))
        self.assertFalse(inverted_negation("do not send it", "do not post it"))

    def test_a_negation_surviving_in_both_is_not_an_inversion(self):
        """A reason claiming an inversion over an unchanged count is exactly
        the fabrication this is for."""
        v = Verdict(
            value="KEEP",
            reason="The rewrite inverts the negation.",
            before="Do not refund without a receipt.",
            after="Do not refund unless there is a receipt.",
        )
        self.assertTrue(standard_register().check(v).void)

    def test_an_empty_rewrite_cannot_support_a_quotation(self):
        """The other direction of the same decoupling: a reason quoting text
        from a rewrite that has none."""
        v = Verdict(
            value="KEEP",
            reason="The rewrite adds a condition that was not there.",
            before="Refund within 30 days.",
            after="",
        )
        self.assertTrue(standard_register().check(v).void)

    def test_the_account_carries_its_denominator(self):
        """'19 were void' and '19 of 72 were void' are different claims, and
        only the second is a measurement."""
        good = Verdict("KEEP", "The rewrite drops a clause.", "a b c", "a b")
        bad = Verdict("KEEP", "The rewrite drops a clause.", "a b", "a b")
        none = Verdict("KEEP", "It reads worse.", "a", "a")
        said = account(void_unless([good, bad, none]))
        self.assertIn("2 of 3", said)
        self.assertIn("1 of those", said)

    def test_nothing_stands_by_default(self):
        """A verdict that met no rule is void, not pending and not accepted."""
        self.assertEqual(account([]), "no verdicts were ruled on")
        rulings = void_unless([Verdict("KEEP", "", "a", "b")])
        self.assertTrue(rulings[0].void)

    def test_it_does_not_claim_the_verdict_was_right(self):
        """A reason that survives its rule can still be a bad call. This says
        only that the stated reason is about the text in front of it."""
        v = Verdict("KEEP", "The rewrite drops a clause.", "a b c", "a b")
        ruling = standard_register().check(v)
        self.assertTrue(ruling.stands)
        self.assertNotIn("correct", ruling.why)
        self.assertNotIn("right", ruling.why)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
