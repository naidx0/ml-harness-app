"""Planted case: a KEEP whose stated removal is still in the text goes red.

    the judge names the span it says was removed; when that span is present in
    the original AND the rewrite, the removal it reasons from did not happen

WHAT THIS EXISTS FOR. A seed makes this judge perfectly repeatable - 72 of 72 -
and it still wrongly keeps 8 sentinel rows, the same 8 every time. Reading the
eight rather than counting them showed they are not eight accidents: the judge
invents a deleted condition and then reasons soundly from the deletion it
invented. Across all 19 unseeded false keeps, 19 of 19 justified themselves by a
removal, and where the claim was checkable it was false 14 times out of 15.

THE REAL CASES ARE IN THE SUITE. Every string below is a reply this judge
actually produced, and the false-positive cases are rows where KEEP was the
correct answer. A rule tested only on examples its author invented is a rule
tested against its author's imagination.
"""

from __future__ import annotations

import unittest

import support

refuted = support.import_file(
    "a_removal_the_text_refutes",
    support.REPO_ROOT / "scripts" / "a_removal_the_text_refutes.py",
)


class TheConfabulatedRemovalIsCaughtTest(unittest.TestCase):
    """THE PLANTED CASE, on rows the judge really got wrong."""

    def test_the_isbn_row(self):
        """N-063. Only the final full stop was removed."""
        said = refuted.the_removal_the_text_refutes(
            'The rewrite drops the "Send me the ISBN" requirement, making the '
            "promise more permissive while preserving all facts.",
            "Send me the ISBN and I will search our stock and the trade network, "
            "and tell you the best price I can get it for.",
            "Send me the ISBN and I will search our stock and the trade network, "
            "and tell you the best price I can get it for",
        )
        self.assertEqual(said, "Send me the ISBN")

    def test_the_reservation_row(self):
        """N-044. Both named limits are still there."""
        self.assertIsNotNone(
            refuted.the_removal_the_text_refutes(
                "Rewrite drops the 'under your name' and 48-hour limits, widening "
                "the reservation terms.",
                "Yes. We hold reservations for 48 hours under your name, no payment needed.",
                "Yes. We hold reservations for 48 hours under your name, no payment needed",
            )
        )

    def test_the_double_charge_row(self):
        """N-069. The conditional is present, word for word."""
        self.assertIsNotNone(
            refuted.the_removal_the_text_refutes(
                'The rewrite removes the conditional "If both are still showing on '
                'Friday," making the promise unconditional.',
                "That is usually a pending authorisation. If both are still showing "
                "on Friday, tell me and we will refund one.",
                "That's usually a pending authorisation. If both are still showing "
                "on Friday, tell me and we will refund one.",
            )
        )

    def test_the_sentence_says_the_verdict_may_still_be_right(self):
        """It voids a JUSTIFICATION, not a row. On a set where every answer
        should be DROP the two coincide; on real degradations they can come
        apart, and a rule that overstated itself would be voiding training
        rows on the strength of the judge's prose."""
        said = refuted.why_this_keep_has_no_evidence(
            'drops the "under your name" limit', "a under your name b", "a under your name c"
        )
        self.assertIn("may still be right", said)
        self.assertIn("did not happen", said)


class AReplacementIsNotADeletionTest(unittest.TestCase):
    """THE BUG THE FIRST VERSION SHIPPED, and it is the same error the rule
    exists to catch. Taking any quoted span read the REPLACEMENT as the removed
    text, announced it was still present - which it was, being the new text -
    and reported 8 false positives on 170 genuine degradations. Every one was
    the rule's fault, and I was one step from writing the number down as a
    property of the judge."""

    def test_a_replaces_x_with_y_reply_does_not_fire(self):
        """Real row 31. `all between 1.50 and 4.00` is the new text."""
        self.assertIsNone(
            refuted.the_removal_the_text_refutes(
                'Rewrite replaces "most between 1.50 and 4.00" with "all between '
                '1.50 and 4.00", dropping the original condition.',
                "A whole bay of them by the window, most between 1.50 and 4.00.",
                "A whole bay of them by the window, all between 1.50 and 4.00.",
            )
        )

    def test_a_span_quoted_as_the_result_does_not_fire(self):
        """Real row 34. `at any time` is what the rewrite now says, and it is
        not in the original at all - which is the second condition earning its
        place."""
        self.assertIsNone(
            refuted.the_removal_the_text_refutes(
                'The rewrite drops the 30-day limit, making the rule unconditional '
                '("at any time"), which is more permissive.',
                "you can return it within 30 days for credit",
                "you can return it at any time for credit",
            )
        )

    def test_a_span_quoted_far_from_the_verb_does_not_fire(self):
        """Real row 42. The reply quotes facts it says are PRESERVED, in a
        later clause. Distance from the verb is what tells the two apart."""
        self.assertIsNone(
            refuted.the_removal_the_text_refutes(
                "The rewrite drops the time condition, making the answer more "
                'permissive. All facts in the rewrite ("shop line is on the contact '
                'page") come from the original.',
                "The shop line is on the contact page and it is answered between 10 and 5.",
                "The shop line is on the contact page and is answered Tuesday to Saturday.",
            )
        )

    def test_a_genuine_removal_does_not_fire(self):
        """The correct case, and the one that must stay quiet: the span really
        is gone from the rewrite."""
        self.assertIsNone(
            refuted.the_removal_the_text_refutes(
                'The rewrite removes the conditional clause "If you give me your '
                'order number", turning it into an unconditional promise.',
                "Orders placed on the 3rd ship within two working days. If you give "
                "me your order number I can check the tracking.",
                "Orders placed on the 3rd ship within two working days. I can check "
                "the tracking for you.",
            )
        )


class ItStaysSilentWhereItHasNothingToSayTest(unittest.TestCase):
    """A checker that spoke on every reply would be switched off in a day."""

    def test_a_reply_claiming_no_removal_is_silent(self):
        for reply in (
            "The rewrite is identical; it does not become more permissive, so "
            "condition (1) fails. DROP",
            "The rewrite does not drop a condition or widen a limit; it's merely a "
            "numeric formatting change.",
        ):
            with self.subTest(reply=reply[:40]):
                self.assertIsNone(
                    refuted.the_removal_the_text_refutes(reply, "a b c", "a b c")
                )

    def test_the_word_drop_alone_is_not_a_finding(self):
        """`drop` with nothing quoted after it names no span to check."""
        self.assertIsNone(
            refuted.the_removal_the_text_refutes(
                "The rewrite drops a condition and is more permissive.", "a b", "a b"
            )
        )

    def test_replaced_and_changed_are_not_removal_verbs(self):
        """A substitution's new text being present proves nothing, so those
        verbs must not open the check at all."""
        for verb in ("replaces", "changed", "rewrote", "substitutes"):
            with self.subTest(verb=verb):
                self.assertIsNone(
                    refuted.the_removal_the_text_refutes(
                        f'The rewrite {verb} "the limit" here.', "the limit", "the limit"
                    )
                )

    def test_empty_input_is_silent_rather_than_an_error(self):
        for a, b, c in (("", "x", "y"), ("drops 'x'", "", "y"), ("drops 'x'", "x", "")):
            with self.subTest(a=a[:10]):
                self.assertIsNone(refuted.the_removal_the_text_refutes(a, b, c))


class TheDetectorCanFailTest(unittest.TestCase):
    """A gate you cannot make fail is not a gate."""

    def test_the_span_must_be_in_the_rewrite(self):
        self.assertIsNone(
            refuted.the_removal_the_text_refutes("drops 'the limit'", "the limit", "gone")
        )

    def test_the_span_must_also_be_in_the_original(self):
        self.assertIsNone(
            refuted.the_removal_the_text_refutes("drops 'the limit'", "gone", "the limit")
        )

    def test_in_both_is_what_fires(self):
        self.assertEqual(
            refuted.the_removal_the_text_refutes("drops 'the limit'", "the limit", "the limit"),
            "the limit",
        )

    def test_punctuation_and_curly_quotes_do_not_defeat_it(self):
        """The judge quotes with whatever punctuation it feels like."""
        self.assertIsNotNone(
            refuted.the_removal_the_text_refutes(
                "removes “over 25.00” from the promise",
                "recommended for anything over 25.00,",
                "recommended for anything over 25.00.",
            )
        )

    def test_the_window_is_a_threshold_and_it_holds(self):
        far = "drops the condition" + ("x" * refuted.THE_WINDOW) + " 'the limit'"
        self.assertIsNone(refuted.the_removal_the_text_refutes(far, "the limit", "the limit"))


class ItReportsUnderItsOwnNameTest(unittest.TestCase):
    def test_the_stage_is_its_own(self):
        """A rule reporting under somebody else's name has its refusals read as
        theirs, and a stage's numbers stop being its own."""
        self.assertEqual(refuted.THE_STAGE, "refuted-removal")
        self.assertNotIn(refuted.THE_STAGE, {"validator", "judge", "duplicate"})


class TheMeasuredRatesAreOnTheRecordTest(unittest.TestCase):
    """The claim this rule ships with, run against the real files rather than
    quoted from a document that nothing checks."""

    def test_it_still_catches_the_sentinel_false_keeps(self):
        import json

        path = support.REPO_ROOT / "runs" / "judge-sentinel-n" / "results.jsonl"
        if not path.is_file():
            self.skipTest("runs/ is gitignored; this checks the real artefact when it exists")
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        keeps = [r for r in rows if r["got"] == "KEEP"]
        caught = [
            r for r in keeps
            if refuted.the_removal_the_text_refutes(r["reply"], r["real"], r["rewrite"])
        ]
        drops_disturbed = [
            r for r in rows if r["got"] == "DROP"
            and refuted.the_removal_the_text_refutes(r["reply"], r["real"], r["rewrite"])
        ]
        self.assertEqual(len(keeps), 19, "the set changed; the measured claim is about 19")
        self.assertEqual(len(caught), 14, "the catch rate moved from what was recorded")
        self.assertEqual(len(drops_disturbed), 0, "it fired on a verdict that was correct")


if __name__ == "__main__":
    unittest.main()
