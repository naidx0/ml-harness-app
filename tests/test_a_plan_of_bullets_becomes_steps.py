"""A plan written as plain bullets, with no step line at all, is saved as steps.

Journey 2026-09-25 18:00Z (H-path-e run 1): write_plan saved five phases of
`- \`drop_duplicates\` on ...` bullets and not one `- [ ]` line. The run endpoint
found nothing to work and the journey ended after one turn. Two laws: when a
plan has no step line, a bullet under a `## Phase` heading that names a
registered tool is saved as an open step; a plan with any step line is saved
exactly as written.
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
from app.tools import REGISTRY, evidence, planning  # noqa: E402

NL = chr(10)

BULLETS = NL.join([
    "# Train on ML principles",
    "",
    "## Phase 1 - Data preparation",
    "- `drop_duplicates` on `data/splits/train.jsonl` to clean training data",
    "- `measure_eval_set` on `data/splits/eval.jsonl`",
    "- the data is small",
    "",
    "## Phase 2 - Baseline measurement",
    "- `measure_baseline` on the eval set",
    "",
    "## Gates status",
    "- measure_eval_set passed",
])

MIXED = NL.join([
    "# Train",
    "",
    "## Phase 1 - Data",
    "- [ ] Count the eval rows with measure_eval_set",
    "- `drop_duplicates` on train",
])


class APlanOfBulletsBecomesStepsTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        self.thread = int(events.create_thread("planning", mode="plan")["id"])

    def write(self, plan: str):
        return REGISTRY.call(
            "write_plan", {"plan": plan}, actor=evidence.MODEL, thread_id=self.thread,
        )

    def saved(self) -> str:
        return str((events.get_thread(self.thread) or {}).get("plan") or "")

    def test_tool_bullets_under_phases_become_open_steps(self) -> None:
        self.write(BULLETS)
        steps = [s["text"] for s in planning.open_steps(self.saved())]
        self.assertEqual(len(steps), 3, steps)
        self.assertTrue(any("drop_duplicates" in s for s in steps))
        self.assertTrue(any("measure_baseline" in s for s in steps))

    def test_a_bullet_naming_no_tool_stays_a_bullet(self) -> None:
        self.write(BULLETS)
        self.assertIn(NL + "- the data is small", self.saved())

    def test_a_bullet_outside_a_phase_stays_a_bullet(self) -> None:
        self.write(BULLETS)
        self.assertIn("- measure_eval_set passed", self.saved())
        self.assertNotIn("[ ] measure_eval_set passed", self.saved())

    def test_a_plan_with_any_step_is_saved_as_written(self) -> None:
        self.assertEqual(planning.bullets_as_steps(MIXED), MIXED)
        self.write(MIXED)
        self.assertEqual(len(planning.open_steps(self.saved())), 1)


if __name__ == "__main__":
    unittest.main()
