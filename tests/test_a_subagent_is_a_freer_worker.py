"""A sub-agent is a freer, smaller worker - light brief, phase-scoped packs."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import conductor, db, events, subagents  # noqa: E402
from app.tools import blocks  # noqa: E402


class ASubAgentGetsALightBriefTest(unittest.TestCase):
    def test_light_brief_skips_the_gate_lecture(self):
        payload = {
            "ok": True,
            "verdict": "BLOCKED",
            "outcome": "ACTION__MEASURE_BASELINE",
            "facts_used": {"eval_size_n": 40},
            "gate_ledger": {
                "G1_BASELINE_MEASURED": {"status": "NOT_REACHED"},
            },
            "next_step": {"fact": "baseline_measured", "tool": "measure_baseline"},
            "say": "a long lecture about gates that a child should not replay",
        }
        full = conductor.standing_brief(payload, None, blocks.everything())
        light = conductor.standing_brief(
            payload, None, blocks.everything(), light=True
        )
        self.assertIn("Sub-agent turn", light)
        self.assertIn("measure_baseline", light)
        self.assertNotIn("the engine says:", light)
        self.assertLess(len(light), len(full))


class ASubAgentKeepsPacksNamedInItsPhaseTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)

    def test_phase_named_tools_keep_their_packs_beside_core(self):
        parent = events.create_thread("parent", mode="build")
        child = events.create_thread(
            "child", mode="build", project_id=parent["project_id"]
        )
        events.set_thread_plan(
            int(child["id"]),
            "# Phase\n\n## Steps\n- [ ] Score with measure_baseline\n",
        )
        subagents.ensure_table()
        with db.session() as connection:
            connection.execute(
                "INSERT INTO subagents(parent_thread_id, child_thread_id, phase, state) "
                "VALUES (?, ?, ?, ?)",
                (int(parent["id"]), int(child["id"]), "Phase", "running"),
            )
        self.assertTrue(subagents.is_a_subagent(int(child["id"])))
        payload = {
            "ok": True,
            "outcome": "ACTION__MEASURE_BASELINE",
            "verdict": "BLOCKED",
            "path": [{"id": "S1_UNMEASURED", "kind": "node"}],
            "alternatives": [],
            "unsubstantiated": [],
            "gate_ledger": {},
        }
        active = blocks.active(payload, thread_id=int(child["id"]))
        self.assertIn("ledger", active.packs)
        self.assertIn("measurement", active.packs)
        self.assertNotIn("training", active.packs)


class AParentOnALiveRunCarriesTheAimedPhaseTest(unittest.TestCase):
    """Max, 2026-09-17, measured on thread 75: 51 tools and 13.5k tokens of
    schema on every turn of a run whose aimed phase named one tool."""

    def setUp(self) -> None:
        support.sandbox(self)
        self.thread = int(events.create_thread("parent", mode="build")["id"])
        events.set_thread_plan(self.thread, chr(10).join([
            "# Train",
            "",
            "## Phase 1 - Baseline",
            "**Tools:** `measure_baseline`",
            "- [x] Preview the rows with preview_dataset_rows",
            "- [ ] Measure the baseline on eval.jsonl",
            "",
            "## Phase 2 - Train",
            "**Tools:** `start_training`, `score_the_adapter`",
            "- [ ] Train the adapter",
        ]))
        self.payload = {
            "ok": True, "outcome": "ACTION__MEASURE_BASELINE", "verdict": "BLOCKED",
            "path": [{"id": "S1_UNMEASURED", "kind": "node"}],
            "alternatives": [], "unsubstantiated": [], "gate_ledger": {},
        }

    def test_the_first_open_steps_phase_is_the_scope(self):
        scope = blocks.phase_of_first_open_step(events.get_thread(self.thread)["plan"])
        self.assertIn("## Phase 1 - Baseline", scope)
        self.assertIn("measure_baseline", scope)
        self.assertNotIn("start_training", scope)

    def test_off_a_run_nothing_is_narrowed(self):
        chosen = {name: "core" for name in blocks.CORE}
        chosen["training"] = "the walk asked for it"
        kept = blocks._narrow_to_phase_packs(chosen, self.thread, None)
        self.assertIn("training", kept, "a casual build turn keeps what the walk chose")

    def test_on_a_run_only_the_aimed_phases_packs_ride_beside_core(self):
        was = blocks._a_run_is_live
        blocks._a_run_is_live = lambda thread_id: True
        self.addCleanup(lambda: setattr(blocks, "_a_run_is_live", was))
        active = blocks.active(self.payload, thread_id=self.thread)
        for name in blocks.CORE:
            self.assertIn(name, active.packs)
        self.assertIn("measurement", active.packs)
        self.assertNotIn("training", active.packs, "phase 2's pack rides on nobody's turn")
        self.assertIn("measure_baseline", active.tools)


if __name__ == "__main__":
    unittest.main()
