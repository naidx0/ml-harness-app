"""Three walls that closed on each other, measured on thread 70 and opened.

Max, 2026-09-13, after nine turns of the same non-answer: *"we don't
overpopulate too many requirements and too many tools and too many required
fields - the models get stuck in infinite loops... If you could measure it, you
could finish it, go do it. If you can't, then let's take a step back."*

His transcript reads as a model that will not do as it is told. It is not. It
is three harness rules meeting, and each of them is defensible alone:

1. THE SCOPER withholds every tool that cannot move the current frontier
   (`app/tools/blocks.py`). The frontier was `modality`, a fact declared
   `source: derive` - NO TOOL MEASURES IT. So `measure_baseline` was withheld
   on the grounds that it would not clear a block that nothing could clear.
2. THE REPEAT GUARD ends a turn when every call in a round is one already
   answered (`app/conductor.py`). The model, unable to call the tool it
   announced, reached at the nearest one it could see. Twice. Turn over.
3. THE PROVENANCE WALL refutes a number that disagrees with what the ledger
   holds (`app/provenance.py`). `measure_eval_set` had been pointed at
   `train.jsonl` as well as `eval.jsonl`, so `eval_size_n` held 400 and 40 in
   turn; the true sentence "eval.jsonl: 40 rows" was killed mid-stream against
   the 400.

Nine turns, each ending "measure_baseline - not run this turn". The fixture
numbers below are his: 36 tools offered, `measure_baseline` not among them.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import diagnosis, provenance  # noqa: E402
from app.tools import blocks  # noqa: E402


class TheScoperStopsWithholdingWhenTheWalkCannotMove(unittest.TestCase):
    """A frontier no tool can settle is not a reason to keep the drawer shut."""

    def setUp(self) -> None:
        support.sandbox(self)
        self.spec = diagnosis.default_spec()

    def _payload(self, **over: Any) -> dict[str, Any]:
        """A standing diagnosis stopped at a node, shaped as the engine's."""
        base = {
            "ok": True,
            "outcome": "ACTION__NAME_THE_MODALITY",
            "verdict": "BLOCKED",
            "path": [{"id": "S0_RULES_SUFFICE", "kind": "node"}],
            "alternatives": [],
            "unsubstantiated": [],
        }
        base.update(over)
        return base

    def test_a_fact_no_tool_measures_is_named_as_the_stuck_one(self) -> None:
        stuck = blocks._what_no_tool_can_settle(self._payload(), self.spec, None)
        rests = blocks.rests_on(self._payload(), self.spec)
        self.assertTrue(rests, "the fixture must reach a node with facts")
        # Whatever the node rests on, the answer is a fact with no instrument -
        # or the empty string if every one of them has one.
        if stuck:
            self.assertFalse(blocks._measured_by(stuck, None))
            self.assertIn(stuck, rests)

    def test_the_instruments_come_on_when_nothing_can_clear_the_block(self) -> None:
        """THE REGRESSION, and it is his: measure_baseline reaches the model.

        Same payload, the only difference being whether the frontier's facts
        have an instrument. A node stopped on an unmeasurable fact must offer
        strictly MORE than the same node would if a tool could settle it.
        """
        payload = self._payload()
        if not blocks._what_no_tool_can_settle(payload, self.spec, None):
            self.skipTest("this ledger's stage-0 node rests on measurable facts only")
        widened = blocks.active(payload, thread_id=None, spec=self.spec, evidence_rows=[])
        self.assertIn("measure_baseline", widened.names())
        self.assertIn("measurement", widened.packs)
        # And it says why, in words, on the pack.
        self.assertIn("no tool measures", widened.because["measurement"])

    def test_a_walk_that_can_move_still_gets_the_narrow_turn(self) -> None:
        """The widening is not a way to load everything.

        A frontier whose facts DO have instruments gets exactly what it always
        got - which is the property that keeps this from being the forty-tool
        problem reached by another road.
        """
        measurable = self._payload(path=[{"id": "G1_BASELINE_MEASURED", "kind": "gate"}])
        if blocks._what_no_tool_can_settle(measurable, self.spec, None):
            self.skipTest("this fixture's node is itself unsettleable")
        narrow = blocks.active(measurable, thread_id=None, spec=self.spec, evidence_rows=[])
        for name in narrow.because.values():
            self.assertNotIn("no tool measures", name)

    def test_the_gate_facts_are_read_from_the_engine_s_own_index(self) -> None:
        facts = blocks._every_fact_a_gate_reads(self.spec)
        self.assertIn("baseline_measured", facts)
        self.assertIn("eval_size_n", facts)
        # It is the union of the compiled index, not a re-parse.
        self.assertEqual(
            facts,
            frozenset(str(f) for row in self.spec.gate_row_facts.values() for f in row),
        )

    def test_no_spec_no_widening(self) -> None:
        """A ledger that cannot be read must not silently widen on a guess."""
        self.assertEqual(blocks._every_fact_a_gate_reads(None), frozenset())
        self.assertEqual(blocks._every_fact_a_gate_reads(object()), frozenset())


class TheWallStopsRefutingItsOwnMeasurements(unittest.TestCase):
    """A number this thread measured is not invented, whatever came after it."""

    def setUp(self) -> None:
        support.sandbox(self)

    def _ground(self, rows: list[dict[str, Any]]) -> Any:
        ground = provenance.Ground(thread_id=0)
        for row in rows:
            ground.ledger.setdefault(row["fact"], []).append(row)
        return ground

    def _rows(self) -> list[dict[str, Any]]:
        """His: eval.jsonl counted 40, then train.jsonl counted 400, by the
        same instrument, into the same fact."""
        return [
            {
                "fact": "eval_size_n",
                "value": "40",
                "origin": provenance.evidence.MEASURED,
                "tool": "measure_eval_set",
            },
            {
                "fact": "eval_size_n",
                "value": "400",
                "origin": provenance.evidence.MEASURED,
                "tool": "measure_eval_set",
            },
        ]

    def test_holds_still_answers_what_it_was_written_to_answer(self) -> None:
        ground = self._ground(self._rows())
        self.assertEqual(ground.holds("eval_size_n")["value"], "400")

    def test_every_measurement_is_readable_not_only_the_last(self) -> None:
        ground = self._ground(self._rows())
        seen = [row["value"] for row in ground.ever_measured("eval_size_n")]
        self.assertEqual(seen, ["40", "400"])

    def test_a_stated_value_is_not_a_measurement(self) -> None:
        ground = self._ground(
            [
                {
                    "fact": "eval_size_n",
                    "value": "40",
                    "origin": provenance.evidence.STATED,
                    "tool": "state_facts",
                }
            ]
        )
        self.assertEqual(ground.ever_measured("eval_size_n"), ())

    def test_the_earlier_reading_is_not_refuted(self) -> None:
        """THE EIGHT KILLED REPLIES. 40 was measured here; 400 came later."""
        ground = self._ground(self._rows())
        self.assertIsNone(
            provenance._refute(
                "measurement", "measure_eval_set", True, "eval_size_n", "40", ground
            )
        )

    def test_a_number_nothing_here_measured_is_still_refuted(self) -> None:
        """The wall keeps doing the only job it has.

        137, and not 40000: the non-exact matcher accepts a scaled reading of
        400, which is its business and not this test's subject.
        """
        ground = self._ground(self._rows())
        refuted = provenance._refute(
            "measurement", "measure_eval_set", True, "eval_size_n", "137", ground
        )
        self.assertIsNotNone(refuted)
        self.assertEqual(refuted["refuted_by"], provenance.MISMATCH)


class ARoundOfRepeatsIsWorthASentenceBeforeItIsWorthTheTurn(unittest.TestCase):
    def test_the_nudge_tells_it_to_call_something_else(self) -> None:
        from app import conductor

        said = conductor.REPEAT_NUDGE
        self.assertIn("already been answered", said)
        self.assertIn("DIFFERENT tool", said)
        # And its OWN sentence never mentions the plumbing - the shared
        # PLUMBING clause it ends with is the one that names those words, to
        # forbid them.
        mine = said.replace(conductor.PLUMBING, "")
        for word in ("turn", "round", "budget", "phase"):
            self.assertNotIn(word, mine.lower())

    def test_the_loop_nudges_once_and_only_ends_on_the_second(self) -> None:
        """Read from the source, because the alternative is a live model.

        A behavioural test here would need a model that repeats a call twice in
        one turn and then again in the next round, which is a fixture about
        `_stream_once` rather than about this rule. What the rule IS, is that
        the end is guarded by a flag set on the first occurrence - the same
        shape the silence and intent nudges use, and the thing that was missing.
        """
        source = (REPO / "app" / "conductor.py").read_text(encoding="utf-8")
        block = source[source.index("if repeated == len(calls):") :][:1400]
        self.assertIn("if not nudged_for_repeats:", block)
        self.assertIn("nudged_for_repeats = True", block)
        self.assertIn("REPEAT_NUDGE", block)
        # The end is still there, after the flag.
        self.assertLess(block.index("nudged_for_repeats = True"), block.index('ending = "repeat_loop"'))


if __name__ == "__main__":
    unittest.main()
