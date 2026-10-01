"""The journey is written out as the plan, and the plan is workable.

Max, 2026-09-18: *"journey is an amazing way to empower the plan... it's not
using any sub agents... trouble sharing a journey and plan within one folder
and between sessions."*

`app/journey.py` has read the route since 2026-09-02 - the tool each step
calls, the arguments this conversation measured for it, the fact it puts on the
ledger - and wrote none of it down. The plans a model typed instead had phases
with nothing under them (thread 75, 2026-09-17: eight phases, eight
`**Tools:**` lines, not one `- [ ]` step), and the run aimed at whatever
checkbox lines it could find and parked them.

Four claims, and each one is a way a compiled plan could look right and be
useless:

1. NO PHASE WITHOUT STEPS. The exact fault thread 75 hit, asserted with the
   product's own reader (`planning.phases_without_steps`) rather than a second
   opinion about what a phase is.
2. EVERY OPEN STEP NAMES A REGISTERED TOOL. A step that is a condition is a
   gate, and a plan made of gates parks everything.
3. WHAT IS ALREADY DONE IS TICKED, AND WHAT NOBODY DID IS NOT. A compiled plan
   that asked for work on the record would send a run to redo it; one that
   ticked a step nobody ran would be the generous lie `app/journey.py` exists
   to refuse.
4. A RUN ON A PLAN-LESS THREAD GETS ONE BEFORE ITS FIRST TURN. This is the
   Full-with-no-plan path: the person's ask is a route, and the route is the
   plan.
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
from app import db, events, journey, longrun  # noqa: E402
from app.tools import evidence, planning  # noqa: E402
from app.tools.registry import REGISTRY  # noqa: E402

TRAIN = "train_on_my_files"


class CompileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)
        row = support.conversations(1)[0]
        self.thread = int(row["id"])
        self.project = int(row["project"]["id"])
        events.set_thread_goal(self.thread, "train on my own markdown files", TRAIN)

    def ran(self, name: str, result: dict[str, Any] | None = None) -> None:
        body = dict(result or {})
        body.setdefault("ok", True)
        events.append(
            "tool.result",
            {"id": f"user-{name}", "name": name, "ok": True, "result": body,
             "driven_by": "user"},
            thread_id=self.thread,
        )

    # -- 1 and 2: the shape a run can actually work ------------------------

    def test_every_phase_has_steps_and_every_step_names_a_tool(self) -> None:
        out = journey.compile_plan(self.thread)
        self.assertTrue(out["ok"], out)
        plan = out["plan"]
        self.assertEqual(planning.phases_without_steps(plan), [])
        self.assertEqual(planning.steps_without_a_tool(plan), [])
        self.assertGreater(out["phases"], 1)
        self.assertGreater(out["steps_open"], 1)

    def test_every_journey_in_the_playbook_compiles_into_a_workable_plan(self) -> None:
        """THE SUBJECT SET IS DERIVED, not typed out here.

        A test that listed the routes by hand could not fail for a route
        somebody adds tomorrow, which is the failure this file exists to catch:
        a plan nobody can work, written by the harness itself.
        """
        from app.tools import knowledge

        names = knowledge.journey_names()
        self.assertGreaterEqual(len(names), 5, names)
        for name in names:
            with self.subTest(journey=name):
                thread = int(support.conversations(1)[0]["id"])
                events.set_thread_goal(thread, f"a {name} conversation", name)
                out = journey.compile_plan(thread)
                self.assertTrue(out["ok"], out)
                plan = out["plan"]
                self.assertEqual(planning.phases_without_steps(plan), [], name)
                self.assertEqual(planning.steps_without_a_tool(plan), [], name)
                self.assertGreater(out["steps_open"], 0, name)
                headings = [
                    h for h in planning.headings_in(plan) if h.lower().startswith("phase")
                ]
                self.assertEqual(len(headings), len(set(headings)), name)

    def test_it_is_the_document_cond_planning_asks_for(self) -> None:
        plan = journey.compile_plan(self.thread)["plan"]
        self.assertTrue(plan.startswith("# "), plan[:80])
        self.assertIn("## Root of the ask", plan)
        self.assertIn("## Phase 1 - ", plan)
        self.assertIn("**Files/data:**", plan)
        self.assertIn("**Tools:**", plan)
        self.assertIn("**Verify:**", plan)
        self.assertIn("## Verification", plan)
        self.assertIn("## Out of scope", plan)
        # The route's own tools, named in the steps and on the Tools lines.
        self.assertIn("`carve_eval_set`", plan)
        self.assertIn("`score_the_adapter`", plan)

    def test_each_phase_is_one_agent_s_worth_and_can_be_named(self) -> None:
        """A heading that matches two phases is a phase nobody can delegate."""
        from app import subagents

        plan = journey.compile_plan(self.thread)["plan"]
        headings = planning.headings_in(plan)
        phases = [h for h in headings if h.lower().startswith("phase")]
        self.assertEqual(len(phases), len(set(phases)))
        for heading in phases:
            self.assertIsNotNone(
                subagents.phase_slice(plan, heading),
                f"{heading} does not match exactly one phase",
            )

    def test_the_steps_carry_the_arguments_this_thread_measured(self) -> None:
        self.ran(
            "carve_eval_set",
            {"eval_path": str(self.root / "eval.jsonl"),
             "train_path": str(self.root / "train.jsonl"),
             "answer_column": "a"},
        )
        plan = journey.compile_plan(self.thread)["plan"]
        line = next(
            line
            for line in plan.splitlines()
            if "`measure_baseline`" in line and line.lstrip().startswith("- [")
        )
        self.assertIn("eval.jsonl", line)
        self.assertIn("expected_field = a", line)

    # -- 3: ticked where the record says so, parked where it does not ------

    def test_a_step_already_on_the_record_is_ticked(self) -> None:
        self.ran("attach_context")
        plan = journey.compile_plan(self.thread)["plan"]
        ticked = [s["text"] for s in planning.steps_in(plan) if s["state"] == "done"]
        self.assertTrue(any("attach_context" in t for t in ticked), ticked)
        still_open = [s["text"] for s in planning.open_steps(plan)]
        self.assertFalse(any("attach_context" in t for t in still_open))

    def test_a_step_the_route_says_is_unnecessary_is_parked_not_ticked(self) -> None:
        # `carve_eval_set` succeeding is what makes `carve_rows` moot: the rows
        # existed and were good enough to split. The step did not run.
        self.ran("carve_eval_set", {"eval_path": "e.jsonl", "answer_column": "a"})
        plan = journey.compile_plan(self.thread)["plan"]
        parked = {s["text"]: s["why"] for s in planning.steps_in(plan)
                  if s["state"] == "parked"}
        carve = next((t for t in parked if "carve_rows" in t), None)
        self.assertIsNotNone(carve, parked)
        self.assertIn("carve_eval_set", parked[carve])
        ticked = [s["text"] for s in planning.steps_in(plan) if s["state"] == "done"]
        self.assertFalse(any("carve_rows" in t for t in ticked))

    def test_a_thread_with_no_journey_is_told_so_and_nothing_is_written(self) -> None:
        other = int(support.conversations(1)[0]["id"])
        out = journey.compile_plan(other)
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "no_journey")
        self.assertTrue(out["journeys_available"])
        self.assertIsNone(events.get_thread(other)["plan"])

    def test_a_saved_plan_is_never_written_over(self) -> None:
        events.set_thread_plan(self.thread, "# Mine\n\n## Phase 1 - Mine\n- [ ] Do it\n")
        out = journey.compile_plan(self.thread)
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "a_plan_is_already_saved")
        self.assertIn("Mine", events.get_thread(self.thread)["plan"])

    # -- the tool, and the row it leaves -----------------------------------

    def test_the_tool_writes_the_plan_and_says_where_it_came_from(self) -> None:
        out = REGISTRY.call(
            "compile_the_plan", {}, actor=evidence.MODEL, thread_id=self.thread
        )
        self.assertTrue(out["ok"], out)
        self.assertIn("## Phase 1 - ", events.get_thread(self.thread)["plan"])
        written = [
            r["payload"]
            for r in events.since(f"thread:{self.thread}", limit=200)
            if r["kind"] == "thread.plan_written"
        ]
        self.assertEqual(len(written), 1, written)
        self.assertEqual(written[0]["source"], "journey")
        self.assertEqual(written[0]["journey"], TRAIN)
        self.assertEqual(written[0]["phases_without_steps"], [])
        self.assertIn("diff", written[0])

    def test_the_plan_reaches_the_project_folder(self) -> None:
        folder = self.root / "proj"
        folder.mkdir()
        db.set_project_root(self.project, str(folder))
        journey.compile_plan(self.thread)
        path = folder / "harness-plans" / f"thread-{self.thread}-plan.md"
        self.assertTrue(path.is_file())
        self.assertIn("## Phase 1 - ", path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 4. A run on a plan-less thread compiles one before its first turn


def _turns(script: list[Callable[[int], None]]) -> Callable[..., Any]:
    def take(thread_id: int, scaffold: str | None = None):
        index = min(take.taken["n"], len(script) - 1)  # type: ignore[attr-defined]
        take.taken["n"] += 1  # type: ignore[attr-defined]
        take.aimed.append(  # type: ignore[attr-defined]
            [s["text"] for s in planning.open_steps(
                events.get_thread(thread_id)["plan"] or ""
            )][:1]
        )
        script[index](thread_id)
        yield events.append("stream.end", {"ending": "answered"}, thread_id=thread_id)

    take.taken = {"n": 0}  # type: ignore[attr-defined]
    take.aimed = []  # type: ignore[attr-defined]
    return take


class ARunCompilesFirstTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)
        longrun.ensure_table()
        row = support.conversations(1)[0]
        self.thread = int(row["id"])
        events.set_thread_mode(self.thread, "build")
        events.set_thread_goal(self.thread, "train on my own markdown files", TRAIN)

    def test_a_run_on_a_plan_less_thread_gets_a_compiled_plan(self) -> None:
        self.assertIsNone(events.get_thread(self.thread)["plan"])

        def stop_it(thread_id: int) -> None:
            longrun.stop(thread_id, "enough for a test")

        take = _turns([stop_it])
        out = longrun.start(self.thread, background=False, turn=take)
        self.assertTrue(out["ok"], out)
        plan = events.get_thread(self.thread)["plan"]
        self.assertIn("## Phase 1 - ", plan)
        # THE PLAN WAS THERE BEFORE THE FIRST TURN AIMED, which is the claim.
        self.assertTrue(take.aimed, "no turn was taken")  # type: ignore[attr-defined]
        self.assertTrue(take.aimed[0][0], take.aimed)  # type: ignore[attr-defined]

    def test_a_run_with_no_journey_says_there_is_no_plan(self) -> None:
        """LAW SUBSTITUTED at integration 2026-09-18: a thread with no journey
        and no plan is told there is NO PLAN (P0's finding), not that every
        step is ticked - the compile still runs first and finds nothing."""
        bare = int(support.conversations(1)[0]["id"])
        events.set_thread_mode(bare, "build")
        out = longrun.start(bare, background=False, turn=_turns([lambda t: None]))
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "no_plan")

    def test_a_plan_that_is_already_saved_is_not_recompiled(self) -> None:
        mine = "# Mine\n\n## Phase 1 - Mine\n- [ ] Call inspect_hardware\n"
        events.set_thread_plan(self.thread, mine)

        def stop_it(thread_id: int) -> None:
            longrun.stop(thread_id, "enough for a test")

        longrun.start(self.thread, background=False, turn=_turns([stop_it]))
        self.assertEqual(events.get_thread(self.thread)["plan"].rstrip(), mine.rstrip())


class PlanModeCanCompileTest(unittest.TestCase):
    def test_compile_the_plan_is_offered_in_plan_mode(self):
        """Max, 2026-09-18: the one line P6 left undone. A person in plan mode
        can ask for the journey written out without switching to build."""
        from app import modes

        self.assertIn("compile_the_plan", modes.PLAN_TOOLS)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
