"""Planning hands lookups only, building hands everything back, a person decides.

## What this is protecting

Max asked for two modes after watching a 7B spend 241 seconds and all eight
tool rounds on a question about which use case to pick. Every tool on offer
answered "may we train yet", so that is the question it kept answering.

The mechanism is a named allowlist - `plan` is handed lookups and nothing that
acts - and a list that small is exactly the kind that gets "tidied" later by
somebody who reads an omission as an oversight. These are the assertions that
say it is the feature.

## The three that matter

**Nothing that acts, in plan.** A model cannot walk a decision tree it has not
been handed, and it cannot train a model it cannot reach. Three paragraphs of
instruction were tried against this behaviour, measured over six turns each,
and reverted; see `app/instructions/__init__.py`. The list is NAMED rather than
derived from `writes`, because twenty-nine tools write nothing and one of them
is `fit_a_tree_model`.

**A mode is never derived.** Nothing reads the question and picks. The test
below is a grep, which is a weak check for a strong rule - but the rule's whole
value is that the road stays closed, and a grep notices the day somebody opens
it.

**Existing threads keep their tools.** The column defaults to `build` so that
work in flight when this shipped did not silently lose the tools it had; a NEW
thread opens in `plan`, written at the insert rather than in the default.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import modes  # noqa: E402


class TheTwoModesTest(unittest.TestCase):
    def test_there_are_exactly_two(self):
        """A third mode is a product decision, not a config value."""
        self.assertEqual(sorted(modes.MODES), ["build", "plan"])

    def test_planning_is_handed_lookups_only(self):
        """THE WHOLE MECHANISM. Every plan tool answers a question about
        something that already exists; none of them changes it."""
        from app.tools.registry import REGISTRY
        offered = modes.tools_for("plan", REGISTRY.names())
        self.assertTrue(offered, "planning was handed nothing at all")
        acts = {"carve_rows", "carve_eval_set", "drop_duplicates",
                "make_sandbox", "delete_sandbox", "run_in_sandbox",
                "start_training", "score_the_adapter", "run_eval",
                "measure_baseline", "fit_a_tree_model", "build_retrieval_index"}
        self.assertEqual(
            offered & acts, set(),
            "a tool that acts on the machine reached planning. The list is "
            "named rather than derived precisely so this cannot drift.")

    def test_the_diagnosis_machinery_is_withheld_while_planning(self):
        """MEASURED, TWICE, AND THE SECOND MEASUREMENT WON.

        First version: withheld the core, the model went silent (thread 64,
        twice). Second version: restored the core, and three live turns on
        the owner's question wrote 0 plans in a mean of 169 s, every one
        reaching for `run_diagnosis` and narrating BLOCKED. Third arm, no core
        but `write_plan` offered: mean 77 s, and one turn wrote a six-phase
        plan in 28 s as prose. The record in `app/modes.py` has the table.

        The core stays on every BUILD turn - `test_a_constant_is_not_a_record`
        holds that, and that is where its withdrawal was measured to hurt.
        """
        from app.tools.registry import REGISTRY
        offered = modes.tools_for("plan", REGISTRY.names())
        for machinery in ("run_diagnosis", "what_is_missing", "state_facts", "propose_build"):
            self.assertNotIn(machinery, offered, machinery + " is back in planning")
    def test_planning_has_a_move_that_produces_the_plan(self):
        """The other half. Lookups answer questions about the world; none of
        them produces the thing the mode is for, so a model that acts through
        tools kept picking the next lookup. `write_plan` is the move.
        """
        from app.tools.registry import REGISTRY
        offered = modes.tools_for("plan", REGISTRY.names())
        self.assertIn("write_plan", offered)
        self.assertIn("read_plan", offered)
    def test_every_plan_tool_is_a_real_tool(self):
        """A name removed from the roster must stop being offered that day."""
        from app.tools.registry import REGISTRY
        self.assertEqual(sorted(set(modes.PLAN_TOOLS) - set(REGISTRY.names())), [])

    def test_every_plan_tool_says_why_it_is_there(self):
        """The reason is data, not a comment beside it - autonomy.py's rule."""
        for name, why in modes.PLAN_TOOLS.items():
            self.assertTrue(why.strip(), name + " is on the list with no reason")

    def test_building_keeps_exactly_what_the_diagnosis_scoped(self):
        """A mode widens nothing, and narrows nothing, in build."""
        scoped = {"inspect_hardware", "run_eval", "carve_rows"}
        self.assertEqual(modes.tools_for("build", scoped), scoped)

    def test_a_row_that_predates_the_feature_reads_build(self):
        """Every thread that existed before v016 had tools. It keeps them."""
        for value in (None, "", "nonsense", 0):
            self.assertEqual(modes.normalise(value), "build")
            self.assertEqual(modes.tools_for(value, {"run_eval"}), {"run_eval"})

    def test_the_primitive_still_hands_out_tools(self):
        """THE FOUR ASSERTIONS THAT CAUGHT THIS. `create_thread` has one
        product caller and forty-four in this suite; when it opened threads
        in `plan`, fixtures that build a thread and then exercise a turn
        were handed the lookups instead of the scoped set - including
        `test_a_turn_says_which_blocks_it_loaded`, which is about the
        diagnosis scoping and says nothing about modes.
        """
        from app import events
        import inspect
        signature = inspect.signature(events.create_thread)
        self.assertEqual(signature.parameters["mode"].default, "build")

    def test_a_person_opening_a_conversation_gets_planning(self):
        """THE BEHAVIOUR, through the door a click actually reaches.

        Asserting the constant would pass while the route ignored it -
        `test_a_constant_is_not_a_record` is in this suite for a reason.
        So this posts a thread and reads the row back.
        """
        import support
        from app import events, main
        support.sandbox(self)
        client = support.api_client(main.app)
        made = client.post("/api/threads", json={"title": "a new chat"},
                           headers=support.auth_headers())
        self.assertEqual(made.status_code, 201, made.text)
        row = events.get_thread(made.json()["id"])
        self.assertEqual(modes.normalise(row["mode"]), "plan")

    def test_the_column_default_and_the_new_thread_default_differ_on_purpose(self):
        """They are not the same decision and the migration says why.

        The column default protects threads that already existed; the insert
        default is about where work starts. A future edit that "fixes the
        inconsistency" by making them match would either take the tools away
        from old threads or open new ones straight into building.
        """
        migration = (REPO / "app" / "migrations"
                     / "v016_a_thread_plans_before_it_builds.py").read_text(encoding="utf-8")
        self.assertIn("DEFAULT 'build'", migration)
        self.assertIn("opened in `plan` explicitly", migration)


class NothingDerivesAModeTest(unittest.TestCase):
    """A mode is set by a person. The engine never reads the question."""

    def test_the_setter_refuses_anything_that_is_not_a_mode(self):
        from app import events
        with self.assertRaises(ValueError):
            events.set_thread_mode(1, "planning")   # near-miss
        with self.assertRaises(ValueError):
            events.set_thread_mode(1, "")

    def test_no_module_picks_a_mode_from_the_question(self):
        """A grep, and a deliberately weak one, for a rule worth watching.

        `standing_brief` rejected question-matching twice and its docstring
        names the four phrasings that proved why. If a later change starts
        choosing a mode from the message text, the name of the thing doing it
        will almost certainly be near the word `mode` in one of these files.
        """
        for name in ("conductor.py", "modes.py", "events.py"):
            source = (REPO / "app" / name).read_text(encoding="utf-8")
            lowered = source.lower()
            for smell in ("guess_mode", "infer_mode", "detect_mode", "mode_from_text"):
                self.assertNotIn(
                    smell, lowered,
                    "app/" + name + " looks like it derives a mode. A mode is "
                    "the person's choice; see app/modes.py.")


class WhatEachModePutsOnThePromptTest(unittest.TestCase):
    def test_planning_says_what_it_has(self):
        """Otherwise the model spends the turn reporting a fault that is not one."""
        from app import conductor
        note = conductor._mode_note("plan")
        self.assertIn("write_plan", note)
        self.assertIn("rather than a fault to report", note)

    def test_planning_asks_for_the_plan_in_phases(self):
        """Max: a phase per section, so the goal is clear and a build turn
        can work down it. A vague phase becomes a vague instruction repeated
        for hours, which is the failure mode of handing a plan to a loop."""
        from app import conductor
        note = conductor._mode_note("plan")
        self.assertIn("write_plan", note)
        self.assertIn("Phase 1", note)

    def test_planning_does_not_wait_for_the_diagnosis(self):
        """MEASURED 2026-09-11 on the owner's install, thread 66: with the
        diagnosis machinery withheld, four rounds of lookups, and then "I can
        produce a plan here, but I cannot deliver it yet because I have not
        run the diagnosis." The brief carries the engine's verdict on every
        prompt - BLOCKED, nothing reached, on a fresh thread - and nothing
        told the model that in planning the verdict is context and not a
        gate. This is the sentence that does."""
        from app import conductor
        note = conductor._mode_note("plan")
        self.assertIn("NOT A GATE ON THE PLAN", note)
        self.assertIn("Declining to name a build", note)

    def test_building_says_nothing_about_the_mode(self):
        from app import conductor
        self.assertEqual(conductor._mode_note("build"), "")

    def test_the_plan_is_carried_only_while_building(self):
        """While planning, the plan is what is being written.

        Handing a draft back as a standing instruction would have the
        conversation arguing with an earlier version of itself.
        """
        from app import conductor
        thread = {"plan": "1. carve an eval set"}
        self.assertEqual(conductor._plan_note(thread, "plan"), "")
        self.assertIn("carve an eval set", conductor._plan_note(thread, "build"))

    def test_building_with_no_plan_adds_nothing(self):
        """A thread may be switched without one; the honest note is none."""
        from app import conductor
        self.assertEqual(conductor._plan_note({"plan": None}, "build"), "")
        self.assertEqual(conductor._plan_note({"plan": "   "}, "build"), "")

    def test_a_plan_is_quoted_line_by_line(self):
        """A plan is markdown, and its own headings must not become sections.

        The same fault `_goal_note` was fixed for: quoting only the first line
        let the rest land as top-level prompt sections.
        """
        from app import conductor
        note = conductor._plan_note({"plan": "## step\n1. one\n2. two"}, "build")
        for line in ("> ## step", "> 1. one", "> 2. two"):
            self.assertIn(line, note)


if __name__ == "__main__":
    unittest.main()
