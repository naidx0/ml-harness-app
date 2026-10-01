"""A gate that is killed must not look like a gate that passed.

MEASURED 2026-09-05. A full run was killed mid-suite and left exactly this on
disk: `discovered 3958 tests`, then a stream of dots. No RED, no GREEN — a grep
for either returned zero. A reader grepping for failures finds none, which is
one glance away from "it was fine", and that is the same shape as the defect
`gate.py` exists for: a run that covered part of the suite reading as a pass.

The count assertion cannot close this. The process that would have made it is
the one that went away. Nor would a signal handler: the kill that produced this
was `Stop-Process -Force`, which is `TerminateProcess` on Windows and not
catchable.

So the run states its own contract before it starts, and the absence of the
closing line becomes evidence rather than silence.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("gate_script", REPO / "scripts" / "gate.py")
gate = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(gate)


class TheContractIsStatedBeforeTheRunTest(unittest.TestCase):
    def test_it_names_the_line_a_finished_run_ends_with(self):
        said = gate.what_a_finished_run_looks_like()
        self.assertIn("GATE IS", said)

    def test_it_says_an_unfinished_run_is_not_green(self):
        """The whole point. "Unknown" and "green" are the two readings a reader
        has to choose between, and the sentence has to close that off."""
        said = gate.what_a_finished_run_looks_like().lower()
        self.assertIn("did not finish", said)
        self.assertIn("not green", said)

    def test_the_line_it_promises_is_the_line_the_gate_actually_prints(self):
        """A promise about output that the output does not keep would be worse
        than no promise. Both verdict lines are read off the source rather than
        retyped, so a reworded verdict fails here."""
        source = (REPO / "scripts" / "gate.py").read_text(encoding="utf-8")
        self.assertIn('"GATE IS GREEN:', source)
        self.assertIn('"GATE IS RED:', source)

    def test_the_pending_line_is_distinguishable_from_a_verdict(self):
        """It must not itself match a reader's search for the closing line in a
        way that lets an unfinished run pass. It says GATE IS inside quotes, as
        a description; the verdicts begin with it."""
        said = gate.what_a_finished_run_looks_like()
        self.assertFalse(said.startswith("GATE IS"))
        self.assertTrue(said.startswith("GATE VERDICT PENDING"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
