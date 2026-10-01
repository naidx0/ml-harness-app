"""The instruction set is a library, and the harness pulls the shelf.

## What was measured, and against what

`app/instructions.assemble()` sent all eighteen numbered laws on every turn.
Measured on this machine at `ce03a31`, with the estimator the adapters use
(`app/providers/budget.py`, `CHARS_PER_TOKEN` 3.6) and `tool_calling=True`:

    law text, every law, build mode      5,863 tokens
    law text, every law, plan mode       7,350 tokens
    whole system prompt, build mode      7,757 tokens

"Law text" is `instructions.laws()` - the numbered fragments, the index, and the
tool-calling conditional. It deliberately excludes the preamble and the
capability list, which are GENERATED FROM THE TOOL REGISTRY and grow when a tool
is registered. A ceiling that counted them would be a ceiling on how many tools
this product is allowed to have, which is not a thing anybody wants to pin. Name
what the check reads: this file reads `instructions.laws()`.

## Why this is allowed to be smaller

The laws are not the wall. `app/conductor.py`'s sentry withholds a sentence that
invents a measurement and annotates one that borrows a verdict; the registry
refuses an invented fact id, an unapproved step, and a remote provider on
sensitive data. Those hold whether or not the model read the paragraph about
them, and `tests/corpus_of_harvested_*.py` and their consumers are the proof -
none of them assembles a prompt. So a law the code enforces is worth its tokens
only where a model's WORDING changes because it read it, and the phase is what
decides which of those are in play this turn.

Max, on the alternative to sending everything: *"if it's better to have a
library of components that the system can rag from, instead of having it just
infinitely be instructed... take up a bunch of tokens"*.

## The one thing the packs may not become

A menu. There is no tool that loads a law, no argument a model can send that
widens the set, and `packs_for()` reads only facts a model cannot reach - the
mode a person set, the engine's verdict, the plan's open steps, the live run,
the schemas on the wire, the ledger's own origins. `NoModelChoosesItsOwnLawsTest`
holds that structurally rather than by policy, which is the same rule
`app/tools/blocks.py` holds for the tool packs and for the same reason.
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from app import conductor, events, instructions
from app.providers import Delta
from app.providers import budget as budget_mod
from app.providers import store as provider_store

import support


def law_tokens(**kwargs) -> int:
    """The law text one phase sends, in the estimator both adapters use."""
    text = instructions.laws(tool_calling=True, examples=False, **kwargs)
    return budget_mod.estimate(text).tokens


#: The phase a build turn is in once a plan exists and has open steps.
BUILD_WITH_PLAN = ("core", "build")

#: The phase a turn is in while the engine's verdict is still BLOCKED and no
#: plan is being worked.
DIAGNOSING = ("core", "diagnose")

#: Plan mode. `cond_planning.md` stands in the after-the-verdict slot, which is
#: the substitution the module already made.
PLANNING = ("core", "plan")


# ---------------------------------------------------------------------------
# The declaration, checked against the files rather than against itself.


class EveryLawIsInTheBookTest(unittest.TestCase):
    """DERIVE THE SUBJECT SET. Every assertion here walks the files on disk.

    A hand-listed version of this test cannot fail for a law nobody added to
    it, and a law added to the package and to no pack would be a law that never
    reaches a model again - the exact defect the packs are most likely to cause.
    """

    def test_every_pack_names_fragments_that_exist(self):
        stems = {path.stem for path in instructions.core_files()}
        for pack, members in instructions.PACKS.items():
            for stem in members:
                with self.subTest(pack=pack, law=stem):
                    self.assertIn(stem, stems, f"{pack} names {stem}, which has no file")

    def test_every_law_rides_in_some_pack(self):
        """Worked examples are the one exception and say so out loud."""
        in_a_pack = {stem for members in instructions.PACKS.values() for stem in members}
        for path in instructions.core_files():
            if path.stem == instructions.WORKED_EXAMPLES:
                continue
            with self.subTest(law=path.stem):
                self.assertIn(
                    path.stem,
                    in_a_pack,
                    f"{path.stem} is in no pack, so no phase will ever load it",
                )

    def test_every_law_has_an_index_line(self):
        for path in instructions.core_files():
            with self.subTest(law=path.stem):
                gist = instructions.LAW_INDEX.get(path.stem, "")
                self.assertTrue(gist.strip(), f"{path.stem} has no index sentence")
                self.assertNotIn("`", gist, "an index gist may not quote an id")

    def test_the_index_has_no_entry_for_a_law_that_is_gone(self):
        stems = {path.stem for path in instructions.core_files()}
        for stem in instructions.LAW_INDEX:
            with self.subTest(law=stem):
                self.assertIn(stem, stems, f"{stem} is indexed and has no file")

    def test_a_title_is_read_off_the_file(self):
        """Not kept beside it, so a renamed law cannot be misfiled here."""
        self.assertEqual(instructions.title_of("02_five_gates"), "The five gates")
        self.assertEqual(
            instructions.title_of("06_never_invent_a_number"),
            "Never invent a number — and never let that stop you building",
        )


# ---------------------------------------------------------------------------
# Each pack rides in its phase, and outside it does not.


class APackRidesInItsPhaseTest(unittest.TestCase):
    #: THE HEADING, NOT THE TITLE. A withheld law's title is in the prompt -
    #: that is what the index is - so a membership test on the bare words would
    #: pass for a law that never rode. `## <title>` is the law itself.
    def heading(self, stem: str) -> str:
        return f"## {instructions.title_of(stem)}"

    def assertRides(self, stem: str, packs, *, planning: bool = False) -> None:
        text = instructions.laws(tool_calling=True, packs=packs, planning=planning)
        self.assertIn(self.heading(stem), text, f"{stem} did not ride")

    def assertWithheld(self, stem: str, packs, *, planning: bool = False) -> None:
        text = instructions.laws(tool_calling=True, packs=packs, planning=planning)
        self.assertNotIn(self.heading(stem), text, f"{stem} rode outside its phase")
        self.assertIn(
            f"**{instructions.title_of(stem)}**",
            text,
            f"{stem} was withheld and not indexed",
        )

    def test_core_rides_in_every_phase(self):
        for packs in (("core",), BUILD_WITH_PLAN, DIAGNOSING, PLANNING):
            for stem in instructions.PACKS["core"]:
                with self.subTest(packs=packs, law=stem):
                    self.assertRides(stem, packs, planning=packs == PLANNING)

    def test_the_diagnosis_laws_ride_only_when_diagnosing(self):
        for stem in instructions.PACKS["diagnose"]:
            with self.subTest(law=stem):
                self.assertRides(stem, DIAGNOSING)
                self.assertWithheld(stem, BUILD_WITH_PLAN)

    def test_the_build_laws_ride_only_on_a_build_turn(self):
        for stem in instructions.PACKS["build"]:
            with self.subTest(law=stem):
                self.assertRides(stem, BUILD_WITH_PLAN)
                self.assertWithheld(stem, DIAGNOSING)

    def test_the_provenance_laws_ride_only_when_a_number_is_in_play(self):
        with_them = instructions.laws(
            tool_calling=True, packs=("core", "build", "provenance")
        )
        without = instructions.laws(tool_calling=True, packs=BUILD_WITH_PLAN)
        for stem in instructions.PACKS["provenance"]:
            with self.subTest(law=stem):
                self.assertIn(f"## {instructions.title_of(stem)}", with_them)
                self.assertNotIn(f"## {instructions.title_of(stem)}", without)

    def test_plan_mode_substitutes_rather_than_adds(self):
        """The substitution that already existed, now inside a pack.

        `cond_planning.md` stands in `01b`'s slot; the after-the-verdict law it
        replaces does not also appear, which is what "substitutes" means and
        what a pack that merely added a fragment would break.
        """
        text = instructions.laws(tool_calling=True, packs=PLANNING, planning=True)
        self.assertIn("This turn is planning", text)
        self.assertNotIn("After the verdict: you build the thing", text)

    def test_worked_examples_stay_opt_in_under_every_phase(self):
        for packs in (BUILD_WITH_PLAN, DIAGNOSING):
            with self.subTest(packs=packs):
                self.assertNotIn(
                    "## Two worked examples",
                    instructions.laws(tool_calling=True, packs=packs, examples=False),
                )
                self.assertIn(
                    "## Two worked examples",
                    instructions.laws(tool_calling=True, packs=packs, examples=True),
                )


# ---------------------------------------------------------------------------
# The index, which is what stops a withheld law from being an invisible one.


class TheIndexNamesWhatDidNotRideTest(unittest.TestCase):
    def test_every_law_not_loaded_is_named_in_the_index(self):
        for packs in (("core",), BUILD_WITH_PLAN, DIAGNOSING, PLANNING):
            text = instructions.laws(
                tool_calling=True, packs=packs, planning=packs == PLANNING
            )
            riding = set(instructions.laws_in(packs))
            for path in instructions.core_files():
                if path.stem in riding:
                    continue
                with self.subTest(packs=packs, law=path.stem):
                    self.assertIn(
                        f"**{instructions.title_of(path.stem)}**",
                        text,
                        f"{path.stem} neither rode nor was indexed",
                    )

    def test_a_law_that_rode_is_not_also_indexed(self):
        text = instructions.laws(tool_calling=True, packs=BUILD_WITH_PLAN)
        for stem in instructions.laws_in(BUILD_WITH_PLAN):
            with self.subTest(law=stem):
                self.assertNotIn(f"**{instructions.title_of(stem)}** -", text)

    def test_the_index_says_there_is_no_door_to_ask_at(self):
        """A model told about a library with no door invents the door."""
        text = instructions.laws(tool_calling=True, packs=BUILD_WITH_PLAN)
        self.assertIn("no tool that fetches one", text)

    def test_a_full_assembly_prints_no_index(self):
        self.assertNotIn(
            "The rest of your instruction set", instructions.laws(tool_calling=True)
        )


# ---------------------------------------------------------------------------
# What it costs. Every figure below was measured, not chosen.


class WhatThePhasesCostTest(unittest.TestCase):
    """The budgets, retaken 2026-09-18 on this machine.

    MEASURED 2026-09-18, `instructions.laws(tool_calling=True, examples=False)`:

        every law (the pre-pack set)           5,712
        core alone                             2,187
        core + build (a build turn with a plan) 3,473
        core + build + provenance              4,015
        core + diagnose                        3,979
        core + diagnose + provenance           4,521
        plan mode, pre-pack                    7,199
        plan mode, packs                       4,262

    The ceilings below sit above the measurement with room for a law to gain a
    sentence and below the figure that would mean a pack had quietly stopped
    selecting. They are not the measurement: a test that pinned the exact number
    would go red on a typo fix.
    """

    #: A build turn carrying a plan. The headline of this change.
    BUILD_WITH_PLAN_BUDGET = 3_500

    #: The same turn when a measuring tool is also on the wire. Over the
    #: headline on purpose and recorded rather than hidden: the two provenance
    #: laws cost 542 tokens and a turn that can produce a number is the turn
    #: that needs them. Nothing here trims a ratified law to make a number.
    BUILD_WITH_PROVENANCE_BUDGET = 4_100

    #: A turn where the verdict is still BLOCKED and the diagnosis laws ride.
    DIAGNOSE_BUDGET = 5_000

    #: The five core fragments and the tool-calling conditional, alone. The
    #: index is not in this figure: its size is a fact about what ELSE the turn
    #: loaded, so charging it to the core would make the core's budget move
    #: whenever another pack did.
    CORE_BUDGET = 2_000

    def test_a_build_turn_with_a_plan_fits_its_budget(self):
        self.assertLessEqual(law_tokens(packs=BUILD_WITH_PLAN), self.BUILD_WITH_PLAN_BUDGET)

    def test_the_same_turn_with_the_provenance_pack_is_recorded(self):
        self.assertLessEqual(
            law_tokens(packs=("core", "build", "provenance")),
            self.BUILD_WITH_PROVENANCE_BUDGET,
        )

    def test_a_diagnosing_turn_fits_its_budget(self):
        self.assertLessEqual(law_tokens(packs=DIAGNOSING), self.DIAGNOSE_BUDGET)
        self.assertLessEqual(
            law_tokens(packs=("core", "diagnose", "provenance")), self.DIAGNOSE_BUDGET
        )

    def test_the_core_stays_under_its_budget(self):
        core = "\n\n".join(
            [instructions.read(stem) for stem in instructions.PACKS["core"]]
            + [instructions.read("cond_tools_available")]
        )
        self.assertLessEqual(budget_mod.estimate(core).tokens, self.CORE_BUDGET)

    def test_plan_mode_did_not_get_bigger(self):
        packed = law_tokens(packs=PLANNING, planning=True)
        every_law = law_tokens(planning=True)
        self.assertLess(packed, every_law)

    def test_every_phase_is_cheaper_than_sending_every_law(self):
        """NON-VACUOUS. A selection that loaded everything would pass the
        ceilings above by being under them; this is the strict inequality."""
        every_law = law_tokens()
        for packs in (("core",), BUILD_WITH_PLAN, DIAGNOSING, ("core", "build", "provenance")):
            with self.subTest(packs=packs):
                self.assertLess(law_tokens(packs=packs), every_law)


# ---------------------------------------------------------------------------
# The phase is read off the turn, and the turn is not the model's to write.


class NoModelChoosesItsOwnLawsTest(unittest.TestCase):
    def test_a_blocked_verdict_with_no_plan_is_a_diagnosing_turn(self):
        self.assertEqual(
            instructions.packs_for(verdict="BLOCKED"), ("core", "diagnose")
        )

    def test_a_thread_with_no_walk_reads_as_diagnosing(self):
        """An absent verdict is not a reason to send the thinnest prompt."""
        self.assertIn("diagnose", instructions.packs_for(verdict=None))

    def test_an_open_plan_is_a_build_turn_and_not_a_diagnosing_one(self):
        chosen = instructions.packs_for(verdict="BLOCKED", plan_open=True)
        self.assertIn("build", chosen)
        self.assertNotIn("diagnose", chosen)

    def test_a_live_run_is_a_build_turn(self):
        self.assertIn("build", instructions.packs_for(verdict="TRAIN", working=True))

    def test_plan_mode_is_a_planning_turn_whatever_the_verdict(self):
        for verdict in (None, "BLOCKED", "TRAIN", "NO_TRAIN"):
            with self.subTest(verdict=verdict):
                chosen = instructions.packs_for(planning=True, verdict=verdict)
                self.assertIn("plan", chosen)
                self.assertNotIn("build", chosen)

    def test_provenance_rides_on_a_measuring_tool_or_a_measured_fact(self):
        self.assertIn("provenance", instructions.packs_for(measuring=True))
        self.assertIn("provenance", instructions.packs_for(measured=True))
        self.assertNotIn("provenance", instructions.packs_for(verdict="TRAIN", plan_open=True))

    def test_core_is_in_every_selection(self):
        for kwargs in (
            {},
            {"planning": True},
            {"plan_open": True},
            {"working": True},
            {"verdict": "TRAIN"},
            {"measuring": True},
        ):
            with self.subTest(**kwargs):
                self.assertIn("core", instructions.packs_for(**kwargs))

    def test_the_selection_is_ordered_the_same_way_every_time(self):
        self.assertEqual(
            instructions.packs_for(measuring=True, plan_open=True),
            ("core", "build", "provenance"),
        )


# ---------------------------------------------------------------------------
# The escape hatch.


class TheWholeSetIsOneEnvironmentVariableAwayTest(unittest.TestCase):
    """`MLH_ALL_LAWS=1` is for a bisect: run with the pre-pack prompt, change
    nothing else, compare. It is an env var rather than an argument because a
    person doing that is not editing Python."""

    def test_the_variable_restores_every_law(self):
        with mock.patch.dict(os.environ, {instructions.ALL_LAWS_ENV: "1"}):
            self.assertEqual(instructions.packs_for(verdict="BLOCKED"), ("all",))
            packed = instructions.laws(tool_calling=True, packs=("all",))
        self.assertEqual(packed, instructions.laws(tool_calling=True))

    def test_the_assembly_under_the_hatch_is_the_pre_pack_one(self):
        with mock.patch.dict(os.environ, {instructions.ALL_LAWS_ENV: "1"}):
            chosen = instructions.packs_for(plan_open=True, measuring=True)
            prompt = instructions.assemble(tool_calling=True, packs=chosen)
        self.assertEqual(prompt, instructions.assemble(tool_calling=True))
        self.assertNotIn("The rest of your instruction set", prompt)

    def test_an_unset_variable_selects_packs(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(instructions.ALL_LAWS_ENV, None)
            self.assertNotEqual(instructions.packs_for(verdict="BLOCKED"), ("all",))

    def test_every_non_negotiable_law_survives_the_restored_set(self):
        with mock.patch.dict(os.environ, {instructions.ALL_LAWS_ENV: "1"}):
            prompt = instructions.assemble(tool_calling=True, packs=("all",))
        for name, phrase in instructions.NON_NEGOTIABLE:
            with self.subTest(law=name):
                self.assertTrue(instructions.contains(prompt, phrase), name)


# ---------------------------------------------------------------------------
# And the record, which is what makes a transcript answerable six months later.


class ScriptedModel:
    """A model that says what the test told it to, and keeps what it was sent."""

    id = "fake"
    locality = "local"

    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.sent = []

    def stream(self, messages, tools=None, *, secret=None):
        self.sent.append({"messages": [dict(m) for m in messages], "tools": tools})
        for delta in self.rounds.pop(0) if self.rounds else []:
            yield delta

    def capabilities(self, *, secret=None):
        raise AssertionError("the loop must not probe mid-turn")


class ATurnRecordsWhichLawsRodeTest(unittest.TestCase):
    """`instruction_set` says which library. `law_packs` says which shelf.

    A transcript carrying only the first cannot tell you whether the model was
    ever shown the law it broke, which is the question anybody reading a bad
    turn six months from now is going to ask.
    """

    def setUp(self):
        self.root = support.sandbox(self)
        row = provider_store.create(
            "Fake", "http://127.0.0.1:11434", "fake-model", "ollama"
        )
        ready = provider_store.record_capabilities(
            row["id"],
            type(
                "Caps",
                (),
                {
                    "tool_calling": True,
                    "detail": "set by the test",
                    "ctx_len": None,
                    "provenance": {},
                },
            )(),
        )
        provider_store.set_active(ready["id"])
        original = conductor.build
        model = ScriptedModel([[Delta(kind="text", text="Here is an answer.")]])
        conductor.build = lambda *a, **k: model
        self.addCleanup(setattr, conductor, "build", original)
        self.model = model

    def turn(self, question: str) -> list[dict]:
        thread = events.create_thread("t")
        events.add_message(thread["id"], "user", question)
        list(conductor.run_turn(thread["id"]))
        return events.since(f"thread:{thread['id']}")

    def test_the_started_row_names_the_packs(self):
        rows = self.turn("what can this thing actually do?")
        started = [row for row in rows if row["kind"] == "turn.started"]
        self.assertTrue(started, "the turn never started")
        packs = started[0]["payload"].get("law_packs")
        self.assertTrue(packs, "turn.started carries no law_packs")
        self.assertIn("core", packs)
        for name in packs:
            self.assertIn(
                name,
                set(instructions.PACK_ORDER) | {instructions.ALL_LAWS},
                f"{name} is not a pack this module publishes",
            )

    def test_the_context_row_names_the_same_packs(self):
        rows = self.turn("what can this thing actually do?")
        started = [row for row in rows if row["kind"] == "turn.started"]
        context = [row for row in rows if row["kind"] == "turn.context"]
        self.assertTrue(context, "no turn.context row")
        self.assertEqual(
            context[0]["payload"].get("law_packs"),
            started[0]["payload"].get("law_packs"),
        )

    def test_a_fresh_thread_is_sent_the_diagnosis_laws(self):
        """The selection is real rather than always-core: a thread with nothing
        measured and no plan gets the pack about finding out."""
        rows = self.turn("I want to fine-tune a model on my tickets.")
        started = [row for row in rows if row["kind"] == "turn.started"]
        self.assertIn("diagnose", started[0]["payload"]["law_packs"])
        system = self.model.sent[0]["messages"][0]["content"]
        self.assertIn("## The five gates", system)

    def test_the_hatch_puts_every_law_back_on_a_real_turn(self):
        with mock.patch.dict(os.environ, {instructions.ALL_LAWS_ENV: "1"}):
            rows = self.turn("I want to fine-tune a model on my tickets.")
        started = [row for row in rows if row["kind"] == "turn.started"]
        self.assertEqual(started[0]["payload"]["law_packs"], ["all"])
        system = self.model.sent[0]["messages"][0]["content"]
        self.assertNotIn("The rest of your instruction set", system)


if __name__ == "__main__":
    unittest.main()
