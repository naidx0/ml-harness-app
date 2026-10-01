"""CS5: tick a plan step, then revert restores the open step — facts stay."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import effects, events  # noqa: E402


PLAN_OPEN = """# Work

## Phase 1
- [ ] Carve the eval set
- [ ] Measure the baseline
"""

PLAN_TICKED = """# Work

## Phase 1
- [x] Carve the eval set
- [ ] Measure the baseline
"""


class TurnEffectsRevertTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)

    def test_tick_then_revert_restores_open_step(self) -> None:
        tid = events.create_thread("effects revert", mode="build")["id"]
        events.set_thread_plan(tid, PLAN_OPEN)
        before = events.get_thread(tid)["plan"]

        started = events.append("turn.started", {"model": "x"}, thread_id=tid)
        events.set_thread_plan(tid, PLAN_TICKED)
        events.append(
            "thread.step_done",
            {
                "thread_id": tid,
                "step": "Carve the eval set",
                "by": "test",
                "open": 1,
                "done": 1,
            },
            thread_id=tid,
        )
        after_tick = events.get_thread(tid)["plan"]
        self.assertIn("- [x] Carve the eval set", after_tick)
        self.assertIn("- [ ] Measure the baseline", after_tick)

        summary = effects.gather(
            tid,
            after_id=int(started["id"]),
            plan_before=before,
        )
        self.assertFalse(summary["empty"])
        self.assertTrue(summary["can_revert"])
        self.assertEqual(summary["steps_done"], ["Carve the eval set"])

        written = events.append(effects.KIND, summary, thread_id=tid)
        out = effects.revert(tid, int(written["id"]))
        self.assertTrue(out["ok"])
        self.assertTrue(out["facts_untouched"])

        restored = events.get_thread(tid)["plan"]
        self.assertIn("- [ ] Carve the eval set", restored)
        self.assertNotIn("- [x] Carve the eval set", restored)

    def test_revert_does_not_claim_to_delete_facts(self) -> None:
        tid = events.create_thread("effects facts", mode="build")["id"]
        events.set_thread_plan(tid, PLAN_OPEN)
        before = events.get_thread(tid)["plan"]
        started = events.append("turn.started", {}, thread_id=tid)
        events.set_thread_plan(tid, PLAN_TICKED)
        events.append(
            "thread.step_done",
            {"thread_id": tid, "step": "Carve the eval set", "by": "test"},
            thread_id=tid,
        )
        summary = effects.gather(
            tid,
            after_id=int(started["id"]),
            plan_before=before,
        )
        summary["facts"] = [
            {"fact": "eval_size_n", "origin": "MEASURED", "how": "counted", "tool": "x"}
        ]
        written = events.append(effects.KIND, summary, thread_id=tid)
        out = effects.revert(tid, int(written["id"]))
        self.assertTrue(out["facts_untouched"])
        kinds = [r["kind"] for r in events.since(f"thread:{tid}", limit=100)]
        self.assertIn("turn.effects_reverted", kinds)


if __name__ == "__main__":
    unittest.main()
