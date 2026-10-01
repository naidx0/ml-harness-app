"""A plan whose phase carries no step is saved and told so, at once.

Max's thread 75, 2026-09-17: eight phases carried `**Tools:**` lines and not
one `- [ ]` line. The only steps were six gate sentences under Verification,
which cond_planning had already warned produces "ten turns, nothing ticked,
everything parked" - and that is what happened, again. write_plan saved it
without a word. Then a rewrite produced `- []` and the parser stopped seeing
the steps at all, so the bar read 0 of 0 and nothing could be unparked.

Three laws. A phase with no step is named in the reply while the model is
still writing, and again on the first turn of a run - saved, because a plan
written as prose is saved whatever its shape and a refusal would only catch
the second draft. A loosely written step is still a step, and is saved
as `- [ ]`. A step that names no registered tool is called out in the reply,
because a condition is not an action.
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

HEADINGS_ONLY = NL.join([
    "# Train on ML principles",
    "",
    "## Phase 1 - Confirm data",
    "**Tools:** `preview_dataset_rows`, `profile_repository`",
    "**Verify:** row counts match.",
    "",
    "## Phase 2 - Measure baseline",
    "**Tools:** `measure_baseline`",
    "",
    "## Verification",
    "- [ ] Baseline measured on eval set",
])

LOOSE = NL.join([
    "# Train on ML principles",
    "",
    "## Phase 1 - Data",
    "- [] Carve the eval set with carve_eval_set from data/train.jsonl into data/split",
    "-[x] Preview five rows with preview_dataset_rows",
    "",
    "## Phase 2 - Baseline",
    "- [ ] Prompting exhausted",
])


class APlanWithoutStepsIsToldSoTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        self.thread = int(events.create_thread("planning", mode="plan")["id"])

    def write(self, plan: str):
        return REGISTRY.call(
            "write_plan", {"plan": plan}, actor=evidence.MODEL, thread_id=self.thread,
        )

    def test_phases_with_only_tool_lines_are_named_in_the_reply(self):
        out = self.write(HEADINGS_ONLY)
        self.assertTrue(out["ok"], out)
        self.assertEqual(
            out["phases_without_steps"],
            ["Phase 1 - Confirm data", "Phase 2 - Measure baseline"],
        )
        self.assertIn("Phase 2 - Measure baseline", out["next"])
        self.assertIn("no `- [ ]` step line", out["next"])
        self.assertIsNotNone(events.get_thread(self.thread)["plan"], "saved, and told")

    def test_a_run_says_it_before_aiming_at_anything(self):
        from app import longrun

        self.write(HEADINGS_ONLY)
        events.set_thread_mode(self.thread, "build")
        seen: list[str | None] = []

        def take(thread_id: int, scaffold: str | None = None):
            seen.append(scaffold)
            yield events.append("stream.end", {"ending": "answered"}, thread_id=thread_id)

        longrun.start(self.thread, background=False, cap=2, turn=take)
        self.assertTrue(seen and seen[0], seen)
        self.assertIn("Phase 1 - Confirm data", seen[0])
        self.assertIn("write_plan", seen[0])

    def test_a_loosely_written_step_is_saved_as_a_step(self):
        out = self.write(LOOSE)
        self.assertTrue(out["ok"], out)
        saved = events.get_thread(self.thread)["plan"]
        self.assertIn("- [ ] Carve the eval set", saved)
        self.assertIn("- [x] Preview five rows", saved)
        steps = planning.steps_in(saved)
        self.assertEqual([s["state"] for s in steps], ["open", "done", "open"])
        self.assertEqual(out["steps_open"], 2)

    def test_a_step_that_names_no_tool_is_called_out(self):
        out = self.write(LOOSE)
        self.assertEqual(out["steps_without_a_tool"], ["Prompting exhausted"])
        self.assertIn("Prompting exhausted", out["next"])
        self.assertIn("name no registered tool", out["next"])

    def test_a_parked_loose_step_can_be_unparked(self):
        """The failure that made 'unpark all' impossible: `- [!]` written as
        `- []` was no longer a step. Saved tidy, it is one again."""
        self.write(LOOSE)
        planning.park_step(self.thread, "Carve the eval set", "no file")
        plan = events.get_thread(self.thread)["plan"]
        self.assertIn("- [!] Carve the eval set", plan)
        back = REGISTRY.call(
            "unpark_step", {"step": "Carve the eval set"},
            actor=evidence.MODEL, thread_id=self.thread,
        )
        self.assertTrue(back["ok"], back)
        self.assertEqual(len(planning.open_steps(events.get_thread(self.thread)["plan"])), 2)


if __name__ == "__main__":
    unittest.main()
