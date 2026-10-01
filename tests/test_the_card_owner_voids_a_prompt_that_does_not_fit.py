"""Planted case 1 of the card owner: a prompt that does not fit is void.

    1. The halved prompt. 13,213 estimated tokens at a 4,096 window: today
       HTTP 200 with 2,050 kept. Expected: refused, `need 17,177 > applied
       4,096`, zero tokens generated, one void row.

**These tests were written after their module and that is the wrong order.**
`card_owner/the_window.py` went into the 200-row commit with no test beside it,
which is a module making a claim nothing had checked. The cases are supposed to
come before the build; this one came second and the record says so.
"""

from __future__ import annotations

import unittest

import support

window = support.import_file(
    "card_owner_the_window", support.REPO_ROOT / "card_owner" / "the_window.py"
)


class ARecordingRuntime:
    """Says whether it was reached. "Zero tokens generated" is not provable by
    reading the code."""

    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return "the model answered"


class TheHalvedPromptTest(unittest.TestCase):
    """The case verbatim: 13,213 estimated at a 4,096 window."""

    def test_it_is_void_with_the_arithmetic_in_the_reason(self):
        verdict = window.the_window_verdict(13_213, 4_096)
        self.assertTrue(verdict.void)
        self.assertEqual(verdict.with_headroom, 17_177)
        self.assertIn("17,177", verdict.reason)
        self.assertIn("4,096", verdict.reason)

    def test_the_runtime_is_never_reached(self):
        runtime = ARecordingRuntime()
        with self.assertRaises(window.ThisCallIsVoid):
            window.send_or_void(13_213, 4_096, runtime)
        self.assertEqual(runtime.calls, 0, "it sent the prompt anyway")

    def test_a_prompt_that_fits_is_sent(self):
        """A rule that voided everything would pass the tests above."""
        runtime = ARecordingRuntime()
        self.assertEqual(
            window.send_or_void(1_000, 65_536, runtime), "the model answered"
        )
        self.assertEqual(runtime.calls, 1)

    def test_the_boundary_is_inclusive(self):
        """`need x 1.3 <= applied` - equality fits, because a bound that
        refuses what it says it allows is a different bound."""
        self.assertFalse(window.the_window_verdict(1_000, 1_300).void)
        self.assertTrue(window.the_window_verdict(1_001, 1_300).void)


class AnUnverifiedWindowIsNotAVerifiedOneTest(unittest.TestCase):
    """THE HEART OF THE CASE. The defect is an HTTP 200 that kept 2,050 of
    13,213 and said nothing. An owner that assumes its `num_ctx` was honoured
    reproduces that with a nicer log line."""

    def test_an_unknown_window_is_void(self):
        verdict = window.the_window_verdict(1_000, None)
        self.assertTrue(verdict.void)
        self.assertIn("did not say what window", verdict.reason)

    def test_the_runtime_is_not_reached_when_the_window_is_unknown(self):
        runtime = ARecordingRuntime()
        with self.assertRaises(window.ThisCallIsVoid):
            window.send_or_void(10, None, runtime)
        self.assertEqual(runtime.calls, 0)

    def test_the_reason_names_the_defect_it_exists_for(self):
        self.assertIn("2,050", window.the_window_verdict(10, None).reason)


class ItReadsTheWindowBackFromShapesTheRuntimeSendsTest(unittest.TestCase):
    def test_the_echoed_options(self):
        self.assertEqual(
            window.what_the_runtime_applied({"options": {"num_ctx": 65_536}}), 65_536
        )

    def test_a_loaded_model_report(self):
        self.assertEqual(
            window.what_the_runtime_applied(
                {"model_info": {"granite.context_length": 131_072}}
            ),
            131_072,
        )

    def test_a_bare_num_ctx(self):
        self.assertEqual(window.what_the_runtime_applied({"num_ctx": 4_096}), 4_096)

    def test_nothing_readable_is_none_and_none_means_void(self):
        for report in ({}, None, "200 OK", {"options": {}}, {"num_ctx": 0}):
            with self.subTest(report=report):
                self.assertIsNone(window.what_the_runtime_applied(report))

    def test_a_boolean_is_not_a_window(self):
        """`isinstance(True, int)` is True in Python, and a `num_ctx` of True
        would otherwise read as a window of 1."""
        self.assertIsNone(window.what_the_runtime_applied({"num_ctx": True}))


class AVoidRunSaysSoTest(unittest.TestCase):
    def test_the_voided_line_carries_both_numbers(self):
        """A job that voided half its rows must not read as a job that made
        them - the same argument as `ran N of N discovered`."""
        self.assertEqual(window.the_voided_line(37, 72), "voided 37 of 72")

    def test_a_void_raises_rather_than_returning(self):
        """Returned, a void verdict can be used by accident."""
        with self.assertRaises(window.ThisCallIsVoid) as caught:
            window.send_or_void(13_213, 4_096, ARecordingRuntime())
        self.assertTrue(caught.exception.verdict.void)
        self.assertEqual(caught.exception.verdict.applied, 4_096)

    def test_the_headroom_is_named_where_it_can_be_argued_with(self):
        self.assertEqual(window.THE_HEADROOM, 1.3)


if __name__ == "__main__":
    unittest.main()
