"""One undeclared fact name loses that fact; the declared ones still land.

Max's thread 78, 2026-09-18, the first turn under Full: the model sent nine
facts, one of them `data_location`, which no ledger declares. The whole call
was refused, twice - the second time over `corpus_rows` - and target_score and
task_family went with it both times. The turn then ended by asking the person
for exactly the two facts it had already tried to record.

A wrong name is a slip about one fact. It is not evidence about the other
eight, and a refusal that throws them away is a wall where a door was meant.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import events  # noqa: E402
from app.tools import REGISTRY, evidence  # noqa: E402


class AWrongNameLosesThatFactTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        self.thread = int(events.create_thread("facts", mode="build")["id"])
        events.set_thread_permission(self.thread, "full")

    def state(self, facts):
        return REGISTRY.call(
            "state_facts", {"facts": facts}, actor=evidence.MODEL, thread_id=self.thread,
        )

    def test_the_declared_facts_land_and_the_wrong_name_is_named(self):
        out = self.state({"target_score": 0.85, "data_location": "here", "modality": "text"})
        self.assertTrue(out["ok"], out)
        self.assertEqual(sorted(r["fact"] for r in out["recorded"]), ["modality", "target_score"])
        self.assertEqual(sorted(out["rejected"]), ["data_location"])
        self.assertIn("NOT recorded: data_location", out["summary"])
        self.assertIn("The rest landed", out["summary"])
        facts = {r["fact"] for r in evidence.rows_for(self.thread)}
        self.assertIn("target_score", facts)
        self.assertNotIn("data_location", facts)

    def test_all_wrong_is_still_the_old_refusal(self):
        out = self.state({"data_location": "here", "corpus_rows": 42})
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "rejected_fact")
        self.assertEqual(evidence.rows_for(self.thread), [])

    def test_a_bad_value_on_a_declared_fact_is_rejected_alone(self):
        out = self.state({"target_score": 0.85, "privacy": "full"})
        self.assertTrue(out["ok"], out)
        self.assertEqual(list(out["rejected"]), ["privacy"])
        self.assertIn("privacy", out["summary"])


class FullWithNoPlanWritesThePlanFirstTest(unittest.TestCase):
    def test_the_build_note_says_to_write_the_plan(self):
        from app import conductor

        note = conductor._plan_note({"plan": None}, "build", True)
        self.assertIn("write_plan", note)
        self.assertIn("Do not ask them", note)
        self.assertIn("- [ ]", note)

    def test_a_casual_build_turn_without_a_plan_is_left_alone(self):
        from app import conductor

        self.assertEqual(conductor._plan_note({"plan": None}, "build", False), "")
        self.assertEqual(conductor._plan_note({"plan": None}, "plan", True), "")


if __name__ == "__main__":
    unittest.main()
