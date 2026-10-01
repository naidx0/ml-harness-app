"""measure_baseline, then run_diagnosis: G1 is asked, and it opens.

Max's run of 2026-09-21: measure_baseline returned `baseline_measured: true`
and run_diagnosis still showed `G1_BASELINE_MEASURED NOT_REACHED`, which the
model reported as "a discrepancy" in the engine's own tracking.

THERE WAS NO KEY MISMATCH, and the test below that reads the ledger keys says
so: the tool stamps `baseline_measured`, `baseline_score` and
`trivial_baseline_score`, and those are exactly what G1's row requires. G1
sits in `stage_1_baseline`, below `S0_MODALITY_FORK`, and the walk had stopped
at `S0_MODALITY_UNKNOWN` above it - so the gate was never asked. The cause was
the modality nobody derived (tests/test_a_text_eval_set_settles_its_modality.py);
what this file locks is the owner's sequence end to end, and the sentence that
joins "measured" to "not reached" when a walk does stop above a gate.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import conductor, diagnosis, events  # noqa: E402
from app.providers import Caps, Delta  # noqa: E402
from app.tools import evidence  # noqa: E402
from app.tools.registry import REGISTRY  # noqa: E402


class _AnswersInJson:
    """A local model that answers every row with the same short record."""

    def stream(self, conversation, offered=None, *, secret=None, **_):
        yield Delta(kind="text", text=json.dumps({"answer": "yes"}))

    def capabilities(self):
        return Caps(tool_calling=False, detail="scripted", ctx_len=8192)


class AMeasuredBaselineOpensG1(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(support.sandbox(self))
        support.connect_a_model(self, _AnswersInJson())
        self.thread = int(events.create_thread("the owner's run")["id"])
        self.path = self.root / "eval.jsonl"
        rows = [{"input": f"is {i} even?", "expected": "yes" if i % 2 == 0 else "no"} for i in range(40)]
        self.path.write_bytes(("\n".join(json.dumps(r) for r in rows) + "\n").encode("utf-8"))

    def through_the_conductor(self, name: str, arguments: dict) -> dict:
        """What `conductor._run_tool` does: the call row, the call, the re-walk."""
        events.append(
            "tool.call", {"id": name, "name": name, "arguments": arguments}, thread_id=self.thread
        )
        result = REGISTRY.call(name, arguments, actor=evidence.MODEL, thread_id=self.thread)
        conductor._Standing(None, thread_id=self.thread).note(result, tool_name=name)
        return result

    def walk(self) -> dict:
        return REGISTRY.call(
            "run_diagnosis", {"facts": {}}, actor=evidence.MODEL, thread_id=self.thread
        )

    def test_the_tool_stamps_exactly_what_the_gate_reads(self) -> None:
        spec = diagnosis.default_spec()
        needs = set().union(
            *(facts for (gate, _), facts in spec.gate_row_facts.items() if gate == "G1_BASELINE_MEASURED")
        )
        self.assertTrue(needs)
        self.assertLessEqual(needs, set(REGISTRY.get("measure_baseline").measures))

    def test_measure_baseline_then_run_diagnosis_reaches_g1(self) -> None:
        counted = self.through_the_conductor("measure_eval_set", {"path": str(self.path)})
        self.assertTrue(counted["ok"], counted)
        REGISTRY.call(
            "state_facts", {"facts": {"target_score": 0.9}}, actor=evidence.USER,
            thread_id=self.thread,
        )
        scored = self.through_the_conductor(
            "measure_baseline",
            {"eval_path": str(self.path), "input_field": "input", "expected_field": "expected"},
        )
        self.assertTrue(scored["ok"], scored)
        walked = self.walk()
        self.assertEqual(walked["fact_origins"]["baseline_measured"], diagnosis.MEASURED)
        self.assertNotEqual(
            walked["gate_ledger"]["G1_BASELINE_MEASURED"]["status"], "NOT_REACHED",
            walked["next"],
        )
        self.assertEqual(walked["gate_ledger"]["G1_BASELINE_MEASURED"]["status"], "PASSED")

    def test_a_walk_stopped_above_a_measured_gate_says_so(self) -> None:
        """No call row names the file, so nothing derives modality: the walk
        stops above stage 1 with G1's facts measured, and says which node."""
        REGISTRY.call(
            "measure_eval_set", {"path": str(self.path)}, actor=evidence.MODEL,
            thread_id=self.thread,
        )
        REGISTRY.call(
            "state_facts", {"facts": {"target_score": 0.9, "task_family": "classification"}},
            actor=evidence.USER, thread_id=self.thread,
        )
        REGISTRY.call(
            "measure_baseline",
            {"eval_path": str(self.path), "input_field": "input", "expected_field": "expected"},
            actor=evidence.MODEL, thread_id=self.thread,
        )
        walked = self.walk()
        self.assertEqual(walked["gate_ledger"]["G1_BASELINE_MEASURED"]["status"], "NOT_REACHED")
        said = walked["measured_but_not_reached"]["G1_BASELINE_MEASURED"]
        self.assertIn("baseline_measured", said)
        self.assertIn(walked["path"][-1]["id"], said)
        self.assertIn("not failed", said)


if __name__ == "__main__":
    unittest.main()
