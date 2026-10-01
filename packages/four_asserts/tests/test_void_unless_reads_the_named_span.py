"""The reason names a span; the rule must be held to THAT span.

MEASURED 2026-09-07 on the harness these rules were extracted from, over 19
verdicts a model produced on rewrites that are not degradations at all.

`dropped_clause` asks *did the rewrite lose any words?* Every fabricated reason
asks a narrower question: *did THIS clause go?* The two come apart, and the gap
is not theoretical - a rewrite of "That is" to "That's" really does lose a word,
so the coarse rule let a verdict stand whose named conditional was sitting
untouched in the rewrite it was said to have left.

    "The rewrite removes the conditional 'If both are still showing on Friday,'
     making the promise unconditional."                                    KEEP

The only change was `That is` -> `That's`.

Three defects were measured and all three are fixed here:

* the coarse rule answered an easier question than the reason asked - 14 of 19
* the closed phrase list had no GERUNDS, so "By removing the ... clause" and
  "By dropping the ... condition" matched nothing and came back NO RULE
  REGISTERED, which means *nobody checked* - 3 of 19
* `holds(before, after)` could not see the reason at all, so a rule that reads
  the named span was not expressible in this register - the interface itself

Together: **19 of 19 now void by rule**, at a cost of 3 in 170 genuine
degradations touched, against a threshold of 5 fixed before the number was read.
"""

from __future__ import annotations

import unittest

from four_asserts import Verdict, void_unless
from four_asserts.void_unless import (
    NO_RULE,
    Register,
    dropped_clause,
    dropped_clause_named,
    standard_register,
)
from four_asserts.void_unless import _named_span_removed


def only(reply, before, after):
    return void_unless([Verdict("KEEP", reply, before, after)])[0]


class TheNamedSpanIsTheClaimTest(unittest.TestCase):
    """THE CASE, on the verdict that used to stand."""

    REPLY = (
        "The rewrite removes the conditional “If both are still showing on "
        "Friday,” making the promise unconditional."
    )
    BEFORE = (
        "That is usually a pending authorisation that will drop off in a day or "
        "two. If both are still showing on Friday, tell me and we will refund one."
    )
    AFTER = (
        "That's usually a pending authorisation that will drop off in a day or "
        "two. If both are still showing on Friday, tell me and we will refund one."
    )

    def test_the_verdict_is_void_because_the_named_span_never_left(self):
        self.assertTrue(only(self.REPLY, self.BEFORE, self.AFTER).void)

    def test_the_coarse_rule_alone_would_have_let_it_stand(self):
        """`That is` -> `That's` really does lose a word, so the easier question
        gets the wrong answer. This is the gap, asserted rather than described."""
        self.assertTrue(dropped_clause(self.BEFORE, self.AFTER))
        self.assertFalse(dropped_clause_named(self.BEFORE, self.AFTER, self.REPLY))

    def test_a_span_that_really_left_keeps_its_verdict(self):
        """The correct case, and the one that must stay quiet."""
        self.assertFalse(
            only(
                'The rewrite removes the conditional "If you give me your order '
                'number", turning it into an unconditional promise.',
                "Orders ship in two days. If you give me your order number I can check.",
                "Orders ship in two days. I can check the tracking for you.",
            ).void
        )

    def test_a_replacement_is_not_read_as_a_deletion(self):
        """A reason saying `replaces "A" with "B"` quotes the REPLACEMENT, and a
        rule taking any quoted span would read the new text as the deleted one -
        the fabrication itself, committed by the checker.

        MY FIRST VERSION OF THIS TEST ASSERTED THE OPPOSITE AND WAS WRONG. Here
        `most` really was dropped, so the verdict SHOULD stand; the thing to
        prove is that it stands for the right reason. The quotes sit before
        `dropping`, no span is governed by it, and the coarse fallback answers -
        rather than the replacement being mistaken for evidence of a removal
        that did not happen.
        """
        before = "A whole bay of them by the window, most between 1.50 and 4.00."
        after = "A whole bay of them by the window, all between 1.50 and 4.00."
        reply = ('Rewrite replaces "most between 1.50 and 4.00" with "all between '
                 '1.50 and 4.00", dropping the original condition.')
        self.assertIsNone(_named_span_removed(reply, before, after),
                          "a quote not governed by the verb was taken as its object")
        self.assertTrue(dropped_clause_named(before, after, reply),
                        "the genuine loss of `most` should leave the verdict standing")

    def test_presence_in_the_rewrite_alone_is_not_evidence(self):
        """The second condition, earning its place. A span present in the
        rewrite but ABSENT from the original is the new wording, and treating
        it as a refuted removal is what produced eight wrong answers in the
        first version of this rule."""
        self.assertIsNone(
            _named_span_removed(
                'drops the 30-day limit, making it unconditional ("at any time")',
                "you can return it within 30 days for credit",
                "you can return it at any time for credit",
            ),
            "a span absent from the original was treated as a removed one",
        )

    def test_a_span_quoted_far_from_the_verb_is_not_its_object(self):
        """Distance is the whole of condition one, so it needs a case either
        side of the window rather than a tautology."""
        near = "drops 'the limit' entirely"
        far = "drops the condition" + ("x" * 80) + " 'the limit'"
        self.assertFalse(
            _named_span_removed(near, "a the limit b", "a the limit b"),
            "a governed span present in both texts must refute the claim",
        )
        self.assertIsNone(
            _named_span_removed(far, "a the limit b", "a the limit b"),
            "a span beyond the window was taken as the verb's object",
        )

    def test_no_named_span_falls_back_rather_than_inventing_an_answer(self):
        self.assertTrue(dropped_clause_named("a b c", "a b", "the rewrite drops a condition"))
        self.assertFalse(dropped_clause_named("a b", "a b", "the rewrite drops a condition"))


class TheGerundsWereMissingTest(unittest.TestCase):
    """A closed list is the right design. An incomplete one fails quietly.

    MEASURED: three of nineteen fabricated verdicts came back NO RULE
    REGISTERED - the answer that means *nobody checked* - because the replies
    said "By removing" and "By dropping" and the list held only "removes",
    "removed", "drops", "dropped".
    """

    def test_the_three_real_replies_now_find_their_rule(self):
        for reply in (
            'By removing the "refund if we buy" clause the rewrite is more permissive.',
            "The rewrite widens the limit by removing the 'secondhand' restriction.",
            'By dropping the "has not shipped" condition, the answer promises refund.',
        ):
            with self.subTest(reply=reply[:38]):
                self.assertEqual(standard_register().which_rule(reply.lower()), "dropped clause")

    def test_the_base_forms_still_match(self):
        for word in ("drops", "dropped", "removes", "removed", "omits", "omitted"):
            with self.subTest(word=word):
                self.assertEqual(
                    standard_register().which_rule(f"the rewrite {word} a clause"),
                    "dropped clause",
                )

    def test_added_word_gained_its_gerunds_too(self):
        self.assertEqual(
            standard_register().which_rule("the rewrite is adding a new fact"), "added word"
        )

    def test_an_unrelated_reason_still_finds_no_rule(self):
        """The list stays closed. A reason nobody wrote a rule for must come
        back as NO RULE, because *nobody checked* and *the check failed* are
        different facts and collapsing them is the whole point of this module."""
        ruling = only("the tone is worse", "a b", "a b")
        self.assertTrue(ruling.void)
        self.assertEqual(ruling.why, NO_RULE)


class ARuleMayAskForTheReasonTest(unittest.TestCase):
    """The interface limit, fixed compatibly."""

    def test_a_two_argument_rule_still_works_untouched(self):
        register = Register()
        register.add("old style", claims=lambda r: "old" in r, holds=lambda b, a: b == a)
        self.assertFalse(register.check(Verdict("KEEP", "old way", "x", "y")).stands)
        self.assertTrue(register.check(Verdict("KEEP", "old way", "x", "x")).stands)

    def test_a_three_argument_rule_receives_the_reason(self):
        seen = []

        def holds(before, after, reason):
            seen.append(reason)
            return True

        register = Register()
        register.add("new style", claims=lambda r: "new" in r, holds=holds)
        register.check(Verdict("KEEP", "new reason here", "x", "y"))
        self.assertEqual(seen, ["new reason here"])

    def test_a_builtin_without_a_readable_signature_is_not_a_crash(self):
        """`inspect.signature` raises on some callables. Bookkeeping must never
        decide a verdict, and must never raise into one either."""
        register = Register()
        register.add("builtin", claims=lambda r: "b" in r, holds=lambda b, a: True)
        self.assertTrue(register.check(Verdict("KEEP", "b", "x", "y")).stands)


if __name__ == "__main__":
    unittest.main()
