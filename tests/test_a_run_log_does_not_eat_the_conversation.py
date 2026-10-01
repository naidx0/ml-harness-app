"""A run's log is bounded before it enters the payload, and says it was.

## What was measured, 2026-09-05

One `run_in_sandbox` result in thread 33 of this machine's own database is
**310,530 characters — about 77,632 tokens**. `app/conductor.py::data_envelope`
wraps a tool result for provenance and does **not** shorten it, so all of it
entered the next turn's prompt. The composition of that turn:

| source | tokens | share |
|---|---|---|
| the tool result | ~77,677 | **85%** |
| every tool schema | ~11,430 | 13% |
| the whole transcript | ~2,067 | 2% |

A single log is larger than a 64k context window on its own, and six times the
entire scoped schema set. The capability-blocks work bounds what a model may
CALL; nothing bounded what a tool hands BACK.

## Why the mark matters as much as the cap

A truncated log that did not say so is worse than a long one. A model reading it
would conclude the run ended at the last line visible — which for a timed-out or
still-running job is a false statement about the world rather than a shorter
true one. So the elision carries the count that is missing, where the whole file
is, and the fact that nothing was deleted.

## Why head AND tail

A run's log has evidence at both ends and filler between: setup and first error
at the top, final metrics and traceback at the bottom, a thousand progress lines
in the middle. Keeping one end drops half of what a reader needs.
"""

from __future__ import annotations

import unittest

import support

from app.tools import sandbox


class AShortLogIsUntouchedTest(unittest.TestCase):
    def test_a_log_under_the_cap_passes_through_byte_for_byte(self):
        text = "line one\nline two\n"
        self.assertEqual(
            sandbox.the_output_a_model_can_read(text, "C:/runs/1/log.txt"), text
        )

    def test_a_log_exactly_at_the_cap_is_untouched(self):
        text = "x" * (sandbox.LOG_HEAD_CHARS + sandbox.LOG_TAIL_CHARS)
        self.assertEqual(
            sandbox.the_output_a_model_can_read(text, "p"), text
        )

    def test_an_empty_log_is_empty(self):
        self.assertEqual(sandbox.the_output_a_model_can_read("", "p"), "")


class ALongLogIsCappedAndSaysSoTest(unittest.TestCase):
    def setUp(self):
        self.head = "FIRST-LINE-MARKER\n" + "h" * 8_000
        self.tail = "t" * 8_000 + "\nFINAL-METRIC-MARKER"
        self.whole = self.head + ("m" * 300_000) + self.tail
        self.capped = sandbox.the_output_a_model_can_read(
            self.whole, "C:/runs/33/log.txt"
        )

    def test_it_is_dramatically_smaller(self):
        self.assertLess(len(self.capped), 15_000)
        self.assertGreater(len(self.whole), 300_000)

    def test_the_beginning_survives(self):
        """Where the setup and the first failure are."""
        self.assertIn("FIRST-LINE-MARKER", self.capped)

    def test_the_end_survives(self):
        """Where the final metrics and the traceback are. A cap that kept only
        the head would drop the answer to 'how did the run come out'."""
        self.assertIn("FINAL-METRIC-MARKER", self.capped)

    def test_the_middle_is_gone(self):
        self.assertNotIn("m" * 1_000, self.capped)

    def test_it_says_how_much_is_missing(self):
        missing = len(self.whole) - sandbox.LOG_HEAD_CHARS - sandbox.LOG_TAIL_CHARS
        self.assertIn(f"{missing:,} characters", self.capped)

    def test_it_names_where_the_whole_log_is(self):
        self.assertIn("C:/runs/33/log.txt", self.capped)

    def test_it_says_nothing_was_deleted(self):
        """The file is untouched; only this copy is short. A reader who thinks
        the log was destroyed will not go and read it."""
        self.assertIn("nothing was deleted", self.capped)

    def test_it_says_why_rather_than_only_that(self):
        self.assertIn("context", self.capped)


class TheResultCarriesTheRealSizeTest(unittest.TestCase):
    """`output_chars_total` is how a reader knows what the cap cost.

    Without it the shortened copy is the only number available and the true
    size is unrecoverable from the result - which is the shape of a measurement
    with no denominator.
    """

    def test_the_field_is_built_from_the_uncapped_length(self):
        whole = "z" * 50_000
        capped = sandbox.the_output_a_model_can_read(whole, "p")
        self.assertLess(len(capped), len(whole))
        # what the result records is the length BEFORE capping
        self.assertEqual(len(whole), 50_000)


class TheResultActuallyUsesItTest(unittest.TestCase):
    """A perfect function nobody calls is not a fix.

    FOUND BY MUTATION. Every other test in this file passed with the cap
    written, tested and NOT WIRED IN - reverting `"output": the_output_a_model
    _can_read(...)` to `"output": output` left the suite green. The tests proved
    the function worked and never proved the product used it.

    Asserted through the AST rather than by grepping the source, because a
    string match breaks on a line wrap and would be a test about formatting
    wearing the clothes of a test about behaviour - a mistake already made once
    tonight in `scripts/gate.py`'s tests.
    """

    def test_the_output_key_is_built_by_the_capping_function(self):
        import ast

        source = (support.REPO_ROOT / "app" / "tools" / "sandbox.py").read_text(
            encoding="utf-8"
        )
        wired = False
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if not (isinstance(key, ast.Constant) and key.value == "output"):
                    continue
                if (
                    isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Name)
                    and value.func.id == "the_output_a_model_can_read"
                ):
                    wired = True
        self.assertTrue(
            wired,
            "no dict in sandbox.py builds its 'output' key by calling "
            "the_output_a_model_can_read, so a run's whole log still reaches "
            "the payload however well the function works",
        )

    def test_the_untruncated_size_travels_with_it(self):
        import ast

        source = (support.REPO_ROOT / "app" / "tools" / "sandbox.py").read_text(
            encoding="utf-8"
        )
        keys = {
            key.value
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Dict)
            for key in node.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
        self.assertIn("output_chars_total", keys)


class TheCapIsNotSoTightItLosesAShortRunTest(unittest.TestCase):
    def test_a_typical_training_log_fits_whole(self):
        """A 200-step run's log at ~40 characters a line is about 8,000
        characters and must arrive intact - the cap is for the pathological
        case, not the ordinary one."""
        typical = "\n".join(f"step {i} loss 0.69" for i in range(200))
        self.assertEqual(
            sandbox.the_output_a_model_can_read(typical, "p"), typical
        )


if __name__ == "__main__":
    unittest.main()
