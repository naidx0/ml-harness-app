"""Slice 1 of docs/plan-mode-v2-plan.md: the A12 plan object as write_plan markdown."""
from __future__ import annotations

import unittest

import support

from app import events, plan_v2
from app.tools import planning

GOOD = {
    "kind": "plan",
    "goal": "an adapter that answers ML-principles questions better than the base model",
    "done_when": "adapter beats baseline on eval.jsonl by 10 points",
    "todos": [
        {"do": "Measure the eval set", "tool": "measure_eval_set", "args": {"path": "eval.jsonl"},
         "check": "row count is recorded", "approval": ""},
        {"do": "Measure the baseline", "tool": "measure_baseline", "args": {},
         "check": "a baseline score exists", "approval": ""},
        {"do": "Train a LoRA adapter", "tool": "start_training", "args": {},
         "check": "a job id comes back", "approval": "time, over 10 minutes"},
    ],
}


class TheObjectBecomesPhasesTest(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)

    def test_one_phase_per_todo_each_with_a_step_naming_its_tool(self):
        out = plan_v2.to_plan_markdown(GOOD)
        self.assertTrue(out["ok"])
        self.assertEqual(out["plan"].count("## Phase "), 3)
        self.assertIn("- [ ] Measure the eval set with measure_eval_set", out["plan"])
        self.assertIn("Approval: time, over 10 minutes", out["plan"])

    def test_write_plan_accepts_it_with_no_empty_phase_and_no_toolless_step(self):
        text = plan_v2.to_plan_markdown(GOOD)["plan"]
        self.assertEqual(planning.phases_without_steps(text), [])
        self.assertEqual(planning.steps_without_a_tool(text), [])
        thread = int(events.create_thread("plan", None)["id"])
        saved = planning.write_plan(text, thread_id=thread)
        self.assertTrue(saved.get("ok"), saved)

    def test_pasted_template_todos_are_refused(self):
        bad = dict(GOOD, todos=[dict(t, do="verb-first step") for t in GOOD["todos"]])
        out = plan_v2.to_plan_markdown(bad)
        self.assertFalse(out["ok"])
        self.assertEqual(out["pasted"], [1, 2, 3])

    def test_filler_todos_are_refused(self):
        bad = dict(GOOD, todos=GOOD["todos"] + [{"do": "None needed", "tool": "edit"}])
        out = plan_v2.to_plan_markdown(bad)
        self.assertFalse(out["ok"])
        self.assertEqual(out["filler"], [4])

    def test_an_answer_or_an_empty_plan_is_not_a_plan(self):
        self.assertFalse(plan_v2.to_plan_markdown({"kind": "answer", "text": "hi"})["ok"])
        self.assertEqual(plan_v2.to_plan_markdown({"kind": "plan", "todos": []})["error"], "no_todos")


if __name__ == "__main__":
    unittest.main()
