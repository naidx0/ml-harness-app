"""What the third live score row found in the run loop, 2026-09-18.

Three faults, one row. `run.turn` was written at the bottom of the loop, after
every `continue`, so the parent's two turns and a child's twenty-one left no
row and "plan written on turn 1" read false against a plan that was there.
The Full-without-a-wall path shared its counter with the narration check,
which zeroed it every turn, so a child ran twenty-one turns on one step
without ticking, parking or finishing. And the parent sat thirty-three minutes
waiting on that child with fourteen of its own steps open.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import db, events, longrun, subagents  # noqa: E402

NL = chr(10)
PLAN = NL.join([
    "# Train",
    "",
    "## Phase 1 - Data",
    "- [ ] Measure the baseline with measure_baseline on eval.jsonl",
    "",
    "## Phase 2 - Train",
    "- [ ] Train with start_training",
])


def _turns(script: list[Callable[[int], None]], ending: str = "answered") -> Callable[[int], Any]:
    taken = {"n": 0}

    def take(thread_id: int, scaffold: str | None = None):
        index = min(taken["n"], len(script) - 1)
        taken["n"] += 1
        script[index](thread_id)
        yield events.append("stream.end", {"ending": ending}, thread_id=thread_id)

    return take


def _slip(thread_id: int) -> None:
    events.append(
        "tool.result",
        {"name": "state_facts", "ok": False,
         "result": {"ok": False, "error": "rejected_fact", "detail": "not a declared fact"}},
        thread_id=thread_id,
    )
    events.append("chat.delta", {"text": "Still working on it."}, thread_id=thread_id)


class ATurnIsCountedWhenItIsTakenTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        self.thread = int(events.create_thread("t", mode="build")["id"])
        events.set_thread_permission(self.thread, "full")
        events.set_thread_plan(self.thread, PLAN)

    def test_every_turn_leaves_a_run_turn_row_even_an_empty_one(self):
        longrun.start(self.thread, background=False, cap=3,
                      turn=_turns([lambda t: None], ending="empty_reply"))
        run = longrun.status(self.thread) or {}
        rows = [r for r in events.since(f"thread:{self.thread}") if r["kind"] == "run.turn"]
        self.assertEqual(len(rows), int(run["turns"]), (run, len(rows)))
        self.assertGreater(len(rows), 0)

    def test_a_full_run_with_no_wall_stops_after_narration_turns(self):
        longrun.start(self.thread, background=False, cap=12, turn=_turns([_slip] * 12))
        run = longrun.status(self.thread) or {}
        self.assertEqual(run["parked"], [])
        self.assertEqual(run.get("stop_reason"), "the_model_only_narrated", run)
        self.assertLessEqual(int(run["turns"]), longrun.NARRATION_TURNS)


class TheParentWorksWhileAChildWorksTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        self.thread = int(events.create_thread("parent", mode="build")["id"])
        events.set_thread_plan(self.thread, PLAN)
        subagents.ensure_table()

    def _hand_out(self, phase: str) -> None:
        child = events.create_thread("child", mode="build", project_id=events.get_thread(self.thread)["project_id"])
        with db.session() as connection:
            connection.execute(
                "INSERT INTO subagents(parent_thread_id, child_thread_id, phase, state) VALUES (?, ?, ?, ?)",
                (self.thread, int(child["id"]), phase, "running"),
            )

    def test_the_phases_still_its_own_are_named(self):
        self._hand_out("Phase 2 - Train")
        self.assertEqual(longrun._open_phases_not_handed_out(self.thread), ["Phase 1 - Data"])

    def test_it_aims_at_its_own_step_not_the_childs(self):
        self._hand_out("Phase 1 - Data")
        open_steps = longrun.planning.open_steps(PLAN)
        own = longrun._steps_outside_handed_out_phases(self.thread, open_steps)
        self.assertEqual([s["text"] for s in own], ["Train with start_training"])

    def test_it_does_not_wait_when_it_has_its_own_work(self):
        self._hand_out("Phase 2 - Train")
        was = subagents.WAIT_AT_MOST_SECONDS
        subagents.WAIT_AT_MOST_SECONDS = 5.0
        self.addCleanup(lambda: setattr(subagents, "WAIT_AT_MOST_SECONDS", was))
        import time

        started = time.monotonic()
        out = longrun._wait_for_the_sub_agents(self.thread, patient=False)
        self.assertLess(time.monotonic() - started, 2.0, "it waited on a child while it had work")
        self.assertIsNone(out)


class AnAdoptedPlanCountsOnTurnOneTest(unittest.TestCase):
    def test_the_scorer_reads_plan_adopted(self):
        support.sandbox(self)
        thread = int(events.create_thread("scored", mode="build")["id"])
        events.append("thread.plan_adopted", {"thread_id": thread, "source": "project"}, thread_id=thread)
        events.append("run.turn", {"thread_id": thread, "turn": 1, "aimed_at": "x", "open": 1}, thread_id=thread)
        events.append("stream.end", {"ending": "answered"}, thread_id=thread)
        sys.path.insert(0, str(REPO / "scripts"))
        import score_row

        row = score_row.compute_row(str(db.DB_PATH), thread)
        self.assertTrue(row["plan_written_on_turn_1"], row)


if __name__ == "__main__":
    unittest.main()
