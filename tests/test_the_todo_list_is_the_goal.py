"""The to-do list is the goal function: a build ticks steps until none is open.

Max, 2026-09-12: *"I can tell my model stops in the middle of the task... I
want this goal function to be thorough, like this to-do list where it creates
a to-do list and that's the goal - until every single part of that's fixed it
doesn't exit."* Four halves of one rule: the plan's `- [ ]` lines are the
steps (`planning.steps_in`), `mark_step_done` ticks one, `_plan_note` lists
the open ones on every build prompt with the working rule, and the browser's
loop keeps going while any is open (`lib/theBuildKeepsGoing.test.ts`).
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
from app import conductor, events  # noqa: E402
from app.tools import evidence, planning  # noqa: E402
from app.tools.registry import REGISTRY  # noqa: E402

PLAN = "\n".join(
    [
        "# Train the router",
        "",
        "## Root of the ask",
        "A small model that routes tickets.",
        "",
        "## Phase 1 - Data",
        "**Tools:** carve_eval_set",
        "- [ ] Carve the eval set from tickets.jsonl",
        "- [x] Profile tickets.jsonl",
        "**Verify:** measure_eval_set reads at least thirty rows",
        "",
        "## Phase 2 - Baseline",
        "- [ ] Measure the baseline with the connected model",
        "",
        "## Verification",
        "- [ ] Compare the adapter to the baseline on the same eval set",
    ]
)


class StepsTest(unittest.TestCase):
    def test_the_task_lines_are_the_steps_in_order_with_their_state(self):
        steps = planning.steps_in(PLAN)
        self.assertEqual(
            [(s["done"], s["text"]) for s in steps],
            [
                (False, "Carve the eval set from tickets.jsonl"),
                (True, "Profile tickets.jsonl"),
                (False, "Measure the baseline with the connected model"),
                (False, "Compare the adapter to the baseline on the same eval set"),
            ],
        )

    def test_a_plan_without_task_lines_has_no_steps(self):
        self.assertEqual(planning.steps_in("## Phase 1 - Data\nCarve the eval set."), [])


class MarkStepDoneTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        self.thread = int(events.create_thread("t", mode="build")["id"])
        events.set_thread_plan(self.thread, PLAN)

    def call(self, step: str):
        return REGISTRY.call("mark_step_done", {"step": step}, actor=evidence.MODEL, thread_id=self.thread)

    def test_a_few_words_tick_exactly_one_open_step_and_name_the_next(self):
        out = self.call("carve the eval set")
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["ticked"], "Carve the eval set from tickets.jsonl")
        self.assertEqual(out["done"], 2)
        self.assertEqual(out["of"], 4)
        self.assertEqual(out["open_steps"][0], "Measure the baseline with the connected model")
        self.assertIn("Next open step: Measure the baseline", out["next"])
        plan = events.get_thread(self.thread)["plan"]
        self.assertIn("- [x] Carve the eval set from tickets.jsonl", plan)
        self.assertIn("- [ ] Measure the baseline", plan)
        kinds = [r["kind"] for r in events.since(f"thread:{self.thread}", limit=100)]
        self.assertIn("thread.step_done", kinds)

    def test_the_last_tick_says_so_and_stops(self):
        for words in ("carve the eval set", "measure the baseline", "compare the adapter"):
            self.assertTrue(self.call(words)["ok"])
        out = REGISTRY.call("read_plan", {}, actor=evidence.MODEL, thread_id=self.thread)
        self.assertEqual(out["open_steps"], [])
        last = self.call("compare the adapter")
        self.assertEqual(last["error"], "no_such_open_step")
        self.assertIn("already ticked", last["detail"])

    def test_words_that_match_two_steps_are_refused_with_both(self):
        events.set_thread_plan(self.thread, PLAN + "\n- [ ] Measure the baseline again\n")
        out = self.call("measure the baseline")
        self.assertEqual(out["error"], "ambiguous_step")
        self.assertEqual(len(out["matches"]), 2)

    def test_a_plan_with_no_task_lines_says_how_to_get_some(self):
        events.set_thread_plan(self.thread, "## Phase 1 - Data\nCarve it.")
        out = self.call("carve")
        self.assertEqual(out["error"], "no_steps")
        self.assertIn("write_plan", out["detail"])

    def test_the_model_cannot_name_another_thread(self):
        other = int(events.create_thread("other", mode="build")["id"])
        events.set_thread_plan(other, PLAN)
        out = REGISTRY.call(
            "mark_step_done", {"step": "carve the eval set", "thread_id": other},
            actor=evidence.MODEL, thread_id=self.thread,
        )
        self.assertTrue(out["ok"])
        self.assertIn("- [ ] Carve the eval set", events.get_thread(other)["plan"], "the other thread's plan was ticked")
        self.assertIn("- [x] Carve the eval set", events.get_thread(self.thread)["plan"])


class AToolShapedStepTicksItselfTest(unittest.TestCase):
    """MEASURED 2026-09-12: the model did the lookups the steps named and
    ticked none. A step that names a tool is done when that tool returns ok,
    and the harness ticks it - only when exactly one open step names it."""

    TOOLY = "\n".join(
        [
            "## Phase 1 - Inventory",
            "- [ ] Read the hardware with inspect_hardware",
            "- [ ] List the models with list_local_models",
            "- [ ] Decide which model to use",
            "- [ ] Read the runs with list_runs",
            "- [ ] Read the runs again with list_runs",
        ]
    )

    def setUp(self) -> None:
        support.sandbox(self)
        self.thread = int(events.create_thread("t", mode="build")["id"])
        events.set_thread_plan(self.thread, self.TOOLY)
        # Auto-tick is the Run/autonomy skill - casual build must not grind.
        events.set_thread_autonomous(self.thread, True)

    def test_the_one_step_naming_the_tool_is_ticked_by_the_harness(self):
        out = planning.tick_for_tool(self.thread, "inspect_hardware")
        self.assertIsNotNone(out)
        self.assertEqual(out["step"], "Read the hardware with inspect_hardware")
        self.assertEqual(out["by"], "harness")
        self.assertIn("- [x] Read the hardware with inspect_hardware", events.get_thread(self.thread)["plan"])
        self.assertIsNone(planning.tick_for_tool(self.thread, "inspect_hardware"), "ticked once, not twice")

    def test_two_open_steps_naming_the_tool_is_a_guess_so_nothing_is_ticked(self):
        self.assertIsNone(planning.tick_for_tool(self.thread, "list_runs"))
        self.assertNotIn("- [x]", events.get_thread(self.thread)["plan"])

    def test_a_step_that_names_no_tool_is_left_to_mark_step_done(self):
        self.assertIsNone(planning.tick_for_tool(self.thread, "decide"))
        self.assertIsNone(planning.tick_for_tool(self.thread, "list_local"), "a prefix is not the tool's name")

    def test_not_in_plan_mode(self):
        events.set_thread_mode(self.thread, "plan")
        self.assertIsNone(planning.tick_for_tool(self.thread, "inspect_hardware"))


class ABuildTurnWithOpenStepsIsNotHandedReadPlanTest(unittest.TestCase):
    """MEASURED 2026-09-12: with the open steps on the prompt, the model read
    the plan four times instead of doing the one step left. The tool it
    stalled on is not offered on such a turn; with no open steps it is."""

    def setUp(self) -> None:
        support.sandbox(self)

    def offered_on(self, plan: str, mode: str = "build") -> set[str]:
        from app.providers import Delta
        from app.providers import store as provider_store

        row = provider_store.create("Fake", "http://127.0.0.1:11434", "fake-model", "ollama")
        provider_store.record_capabilities(
            row["id"],
            type("Caps", (), {"tool_calling": True, "detail": "test", "ctx_len": None, "provenance": {}})(),
        )
        provider_store.set_active(row["id"])
        thread = int(events.create_thread("t", mode=mode)["id"])
        events.add_message(thread, "user", "build it")
        events.set_thread_plan(thread, plan)
        seen: dict[str, Any] = {}

        class Fake:
            id = "fake"
            locality = "local"

            def stream(self, messages, tools=None, *, secret=None):
                seen["tools"] = tools
                yield Delta(kind="text", text="Done.")

        original = conductor.build
        conductor.build = lambda *a, **k: Fake()
        try:
            for _ in conductor.run_turn(thread):
                pass
        finally:
            conductor.build = original
        return {t["function"]["name"] for t in (seen.get("tools") or [])}

    def test_read_plan_is_withheld_while_a_step_is_open(self):
        offered = self.offered_on(PLAN)
        self.assertIn("mark_step_done", offered)
        self.assertNotIn("read_plan", offered)

    def test_read_plan_is_offered_once_every_step_is_ticked(self):
        offered = self.offered_on(PLAN.replace("- [ ]", "- [x]"))
        self.assertIn("read_plan", offered)


class ThePromptCarriesTheOpenStepsTest(unittest.TestCase):
    def test_build_mode_lists_the_open_steps_and_the_working_rule(self):
        note = conductor._plan_note(
            {"plan": PLAN, "mode": "build"}, "build", working=True
        )
        self.assertIn("STEPS: 1 of 4 ticked", note)
        self.assertIn("- [ ] Carve the eval set from tickets.jsonl", note)
        self.assertNotIn("- [ ] Profile tickets.jsonl", note)
        self.assertIn("Work the FIRST open step now", note)
        self.assertIn("mark_step_done", note)
        self.assertIn("do not stop to summarise", note)

    def test_a_casual_build_turn_does_not_order_the_grind(self):
        """Max, 2026-09-14: goal/todo is a skill for Run, not every ask."""
        note = conductor._plan_note({"plan": PLAN, "mode": "build"}, "build")
        self.assertIn("The plan this thread is building", note)
        self.assertNotIn("Work the FIRST open step now", note)
        self.assertIn("presses Run the plan", note)

    def test_every_step_ticked_says_so(self):
        done = PLAN.replace("- [ ]", "- [x]")
        note = conductor._plan_note(
            {"plan": done, "mode": "build"}, "build", working=True
        )
        # The sentence carries the parked count since 2026-09-13, so it says
        # how many of how many rather than "every one" - a plan can end with
        # nothing open and not everything done.
        self.assertIn("nothing is left open - 4 of 4 ticked", note)
        self.assertNotIn("Work the FIRST", note)

    def test_a_plan_that_ends_with_a_parked_step_says_which(self):
        """`app/longrun.py` parks a step it cannot do. Nothing is open, and
        four of four ticked would be a lie."""
        done = PLAN.replace("- [ ]", "- [x]").replace(
            "- [x] Measure the baseline with the connected model",
            "- [!] Measure the baseline with the connected model — parked: no eval set exists",
        )
        note = conductor._plan_note(
            {"plan": done, "mode": "build"}, "build", working=True
        )
        self.assertIn("nothing is left open - 3 of 4 ticked, 1 parked as undoable", note)
        self.assertIn("Say which are parked and why", note)

    def test_a_plan_without_steps_keeps_the_older_rule(self):
        note = conductor._plan_note(
            {"plan": "## Phase 1 - Data\nCarve it.", "mode": "build"},
            "build",
            working=True,
        )
        self.assertIn("say which step you are on", note)
        self.assertNotIn("STEPS:", note)

    def test_planning_asks_for_task_lines_in_the_document_shape(self):
        from app import instructions
        prompt = instructions.assemble(planning=True)
        for piece in ("## Root of the ask", "- [ ] <one concrete step", "**Verify:**", "## Out of scope", "mark_step_done"):
            self.assertIn(piece, prompt)

    def test_planning_asks_for_actions_that_run_to_the_end_of_the_work(self):
        """MEASURED 2026-09-13: a plan whose five steps were the five GATE
        names ran ten turns, ticked nothing, parked everything - and a plan
        whose last phase was "build the plan" had planned one turn."""
        from app import instructions
        prompt = instructions.assemble(planning=True)
        self.assertIn("A STEP IS AN ACTION, NOT A CONDITION", prompt)
        self.assertIn("THE PLAN RUNS TO THE END OF THE WORK", prompt)
        self.assertIn('never write a phase called "build the plan"', prompt.lower())
        self.assertIn("A FACT NOBODY CAN MEASURE IS DECIDED, NOT ASKED", prompt)
        self.assertIn("state_facts", prompt)

    def test_the_build_prompt_is_unchanged_by_the_planning_law(self):
        """The law above is plan mode's. A build turn must not be handed the
        document shape - it has a document already."""
        from app import instructions
        build = instructions.assemble(planning=False)
        self.assertNotIn("A STEP IS AN ACTION, NOT A CONDITION", build)


if __name__ == "__main__":
    unittest.main()
