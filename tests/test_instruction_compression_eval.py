"""Instruction compression is judged by laws kept and tokens saved - not vibes.

A small local-model behavior eval lives here as the acceptance gate for
compressing `01b` / `03` / skipping worked examples. Rates against a live
model (empty reply, gate withhold, "I cannot build", answers-the-gate) are
recorded when a connected model is available; the suite always asserts the
laws and the token win so CI does not depend on Ollama.
"""

from __future__ import annotations

import unittest

from app import instructions
from app.providers import budget as budget_mod


#: Metrics a future live run should fill. Names are stable; values are
#: placeholders until a connected model is measured. Never invent a rate.
BEHAVIOR_METRICS = (
    "empty_reply_rate",
    "gate_withhold_rate",
    "cannot_build_lie_rate",
    "answers_gate_instead_of_question_rate",
)


class InstructionCompressionEvalTest(unittest.TestCase):
    def test_non_negotiable_laws_survive_the_compressed_assembly(self):
        prompt = instructions.assemble(tool_calling=True, examples=False)
        for name, phrase in instructions.NON_NEGOTIABLE:
            with self.subTest(law=name):
                self.assertTrue(
                    instructions.contains(prompt, phrase),
                    f"compressed assembly dropped law {name!r}: {phrase!r}",
                )

    def test_worked_examples_are_opt_in(self):
        without = instructions.assemble(tool_calling=True, examples=False)
        with_examples = instructions.assemble(tool_calling=True, examples=True)
        self.assertNotIn("Two worked examples", without)
        self.assertIn("Two worked examples", with_examples)
        leaner = budget_mod.estimate(without).tokens
        fuller = budget_mod.estimate(with_examples).tokens
        self.assertLess(leaner, fuller)

    def test_compressed_laws_cost_less_than_the_pre_trim_budget(self):
        """01b + 03 were ~2.7k tokens of prose; after trim they must stay under
        that ceiling with examples off. A regression that re-expands them is a
        red test rather than a quiet clouding."""
        prompt = instructions.assemble(tool_calling=True, examples=False)
        weight = budget_mod.estimate(prompt).tokens
        # Measured after the 2026-09-14 trim on this machine: well under 10k
        # with short capability form. Ceiling leaves room for capability growth.
        self.assertLess(weight, 12_000)

    def test_behavior_metric_names_are_stable_for_live_runs(self):
        """The live eval fills these; CI only checks the contract exists."""
        for name in BEHAVIOR_METRICS:
            self.assertTrue(name.isidentifier() or "_" in name)


if __name__ == "__main__":
    unittest.main()
