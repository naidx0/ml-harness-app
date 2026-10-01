"""A turn carries every tool's NAME and only the named tools' SCHEMAS.

Max, 2026-09-14: *"make sure the models aren't clouded with too many tools and
guidelines so that they can have free roam in the computer to build, write,
read and do whatever they have to."*

MEASURED 2026-09-18 with `app/providers/budget.py`'s estimator over
`REGISTRY.model_tools`, on the owner's own registry:

    every pack on                88 schemas   26,992 tokens
    a build turn's pack floor    27 schemas    6,330 tokens
    a fresh build thread         48 schemas   13,514 tokens (65k window)
    the capability list           0 schemas    1,716 tokens, NAMING ALL 88

and 58 of the 88 tools have never been called by any model on that machine.

THE THIRD ROW IS THE OWNER'S OWN THREAD 75 REPRODUCED, which is what makes it a
measurement here rather than a report from a database this file cannot read: a
fresh build thread on the shipped ledger carried 13,514 tokens of schema on the
turn after "hello". It now sends 9 schemas and 1,512 tokens - driven in
`tests/test_conductor_loop.py`, where the equality that used to be taken on the
schemas is taken twice, on the two records that now exist.

Packs were the first answer to that sentence and they are not enough: a pack is
the unit a ledger AUTHOR reasons in, and the narrowest pack selection this
engine produces is still 27 tools. `blocks.on_the_wire` is the second cut, and
it is a cut at the SCHEMA rather than at the tool: the name stays in the room -
`app/instructions/capabilities.py` holds the measured reason it must - and only
the tools something in front of the model has named arrive with their
parameters.

WHAT THIS FILE DRIVES is one source each, plus the bound, plus the switch. A
test that only checked the total would go green on a selector that had lost
three of its four sources and widened the fourth.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT, Path(__file__).resolve().parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import support  # noqa: E402
from app import conductor, db, events, modes, settings, subagents  # noqa: E402
from app.instructions import capabilities  # noqa: E402
from app.providers import Delta  # noqa: E402
from app.providers import budget  # noqa: E402
from app.providers import store as provider_store  # noqa: E402
from app.tools import blocks  # noqa: E402
from app.tools.registry import REGISTRY  # noqa: E402


#: The plan `docs/PHASES.md` shape, aimed at phase one. Phase two's tools are
#: real registered tools, which is what makes "a tool from another phase does
#: not ride" a claim about the selector rather than about a typo.
PLAN = chr(10).join(
    [
        "# Train an adapter",
        "",
        "## Phase 1 - Baseline",
        "**Tools:** `measure_baseline`",
        "- [x] Preview the rows with preview_dataset_rows",
        "- [ ] Measure the baseline on eval.jsonl with measure_baseline",
        "",
        "## Phase 2 - Train",
        "**Tools:** `run_eval`",
        "- [ ] Train the adapter",
        "- [ ] Score it with read_eval_results",
    ]
)

PAYLOAD = {
    "ok": True,
    "outcome": "ACTION__MEASURE_BASELINE",
    "verdict": "BLOCKED",
    "path": [{"id": "S1_UNMEASURED", "kind": "node"}],
    "alternatives": [],
    "unsubstantiated": [],
    "gate_ledger": {},
    "next_step": {
        "kind": "question",
        "fact": "baseline_measured",
        "tool": "measure_baseline",
    },
}


def _schema_tokens(names) -> int:
    """What these schemas cost, counted the way the conductor counts them."""
    return budget.estimate(
        *budget.billable(None, REGISTRY.model_tools(sorted(names)))
    ).tokens


class _OnAThreadWithAPlan(unittest.TestCase):
    """A build thread aimed at phase one, which is the measured situation."""

    def setUp(self) -> None:
        support.sandbox(self)
        self.project = int(db.default_project()["id"])
        self.thread = int(
            events.create_thread("t", project_id=self.project, mode="build")["id"]
        )
        events.set_thread_plan(self.thread, PLAN)
        #: `active` narrows PACKS to the aimed phase only on a live run. The
        #: schema cut does not need that and must not depend on it, so this
        #: fixture leaves the run OFF: every assertion below is about the
        #: narrower cut working on the wider pack set.
        self.active = blocks.active(PAYLOAD, thread_id=self.thread)
        self.among = modes.tools_for("build", self.active.names())

    def wire(self, *, last_reply: str = "", among=None, payload=PAYLOAD):
        return blocks.on_the_wire(
            self.active,
            thread_id=self.thread,
            payload=payload,
            last_reply=last_reply,
            among=self.among if among is None else among,
        )


class TheAimedPhaseIsTheScopeTest(_OnAThreadWithAPlan):
    def test_the_aimed_phases_tool_rides_and_another_phases_does_not(self):
        """Max, 2026-09-17, on thread 75: 51 tools and 13.5k tokens of schema on
        every turn of a run whose aimed phase named one tool."""
        wire = self.wire()
        self.assertIn("measure_baseline", wire.tools)
        self.assertIn("measure_baseline", wire.because["measure_baseline"])
        self.assertIn("aimed phase", wire.because["measure_baseline"])
        for later in ("run_eval", "read_eval_results"):
            with self.subTest(tool=later):
                self.assertIn(
                    later, self.among, "the fixture never offered it to begin with"
                )
                self.assertNotIn(
                    later,
                    wire.tools,
                    "phase two's schema rode on a turn aimed at phase one",
                )

    def test_a_step_names_a_tool_as_loudly_as_the_tools_line_does(self):
        """Both halves of the phase, because a plan writes in both.

        `preview_dataset_rows` is named in a STEP and in no `**Tools:**` line;
        `measure_baseline` is in both. A reader that took only the declared line
        would still pass the assertion above.
        """
        wire = self.wire()
        self.assertIn("preview_dataset_rows", wire.tools)

    def test_a_thread_with_no_plan_is_not_narrowed_to_nothing(self):
        """No plan is not the same as an empty phase.

        The other sources still run: the diagnosis's own next step and the core
        are what a fresh thread has, and they are enough to move it.
        """
        events.set_thread_plan(self.thread, "")
        active = blocks.active(PAYLOAD, thread_id=self.thread)
        wire = blocks.on_the_wire(
            active, thread_id=self.thread, payload=PAYLOAD,
            among=modes.tools_for("build", active.names()),
        )
        self.assertIn("measure_baseline", wire.tools)
        self.assertIn("run_diagnosis", wire.tools)

    def test_a_name_inside_a_longer_name_is_not_a_mention(self):
        """`recall` is a registered tool and a substring of
        `measure_retriever_recall`. A substring match - which is what
        `_narrow_to_phase_packs` does one layer out, where a false positive
        only widens a pack - would load a tool nobody named.
        """
        self.assertIn("recall", REGISTRY.names())
        self.assertIn("measure_retriever_recall", REGISTRY.names())
        said = blocks._named_in(
            "run measure_retriever_recall on the index", REGISTRY.names()
        )
        self.assertIn("measure_retriever_recall", said)
        self.assertNotIn("recall", said)


class TheDiagnosisNamesTheMoveTest(_OnAThreadWithAPlan):
    def test_the_next_step_tool_rides(self):
        """The engine reached this on THIS sheet a millisecond ago, which is the
        most specific thing anyone knows about the turn."""
        events.set_thread_plan(self.thread, "")
        active = blocks.active(PAYLOAD, thread_id=self.thread)
        wire = blocks.on_the_wire(
            active, thread_id=self.thread, payload=PAYLOAD,
            among=modes.tools_for("build", active.names()),
        )
        self.assertIn("measure_baseline", wire.tools)
        self.assertIn("next step", wire.because["measure_baseline"])

    def test_an_alternative_and_an_unsettled_claim_each_ride(self):
        """Three readings of the diagnosis, each driven on its own.

        A test that only drove `next_step` would go green on a selector that had
        dropped the other two, and the other two are where a thread that has
        stopped moving finds its way out.
        """
        payload = dict(
            PAYLOAD,
            next_step={},
            alternatives=[{"tool": "try_prompt"}],
            unsubstantiated=[
                {"fact": "baseline_score", "next_step": {"tool": "measure_baseline"}}
            ],
        )
        events.set_thread_plan(self.thread, "")
        active = blocks.active(payload, thread_id=self.thread)
        wire = blocks.on_the_wire(
            active, thread_id=self.thread, payload=payload,
            among=modes.tools_for("build", active.names()),
        )
        self.assertIn("try_prompt", wire.tools)
        self.assertIn("measure_baseline", wire.tools)
        self.assertIn("baseline_score", wire.because["measure_baseline"])


class WhatTheLastReplyNamedRidesNextTurnTest(_OnAThreadWithAPlan):
    """THE DOOR IN THE WALL, and the reason it has to be here.

    MEASURED 2026-09-13, thread 70 of the owner's own database: nine turns, each
    one announcing `measure_baseline`, unable to call it, `measure_eval_set`
    called twice on the same file instead, ended by the repeat guard. That
    thread died because nothing read what it kept saying.

    A cut at the schema layer would reproduce it exactly, one layer in, if the
    only way to widen were the diagnosis moving. So the model's own previous
    words are a source - of the turn AFTER them, never of the turn they are on.
    """

    def test_a_tool_the_reply_named_arrives_with_its_schema_next_turn(self):
        quiet = self.wire()
        self.assertIn(
            "profile_repository", self.among,
            "the packs never offered it, so this would drive the wrong layer",
        )
        self.assertNotIn(
            "profile_repository", quiet.tools, "the fixture already handed it over"
        )
        loud = self.wire(
            last_reply="I will run profile_repository on the codebase next."
        )
        self.assertIn("profile_repository", loud.tools)
        self.assertIn("last reply", loud.because["profile_repository"])

    def test_a_call_it_tried_counts_as_naming_it(self):
        """A model asks in two registers - prose and a tool call.

        `app/conductor.py:_what_the_last_reply_said` reads both off one row, so
        this drives the JSON half that the prose half would hide.
        """
        events.add_message(
            self.thread, "assistant", "Working on it.",
            '[{"name": "profile_repository", "arguments": "{}"}]',
        )
        said = conductor._what_the_last_reply_said(self.thread)
        self.assertIn("profile_repository", said)
        self.assertIn("profile_repository", self.wire(last_reply=said).tools)

    def test_only_the_last_reply_is_read_and_a_user_message_is_not_one(self):
        """The model's words, not the person's, and not every turn ever.

        A reader that took the whole transcript would accumulate: by turn ten a
        thread would be back at every schema, which is the 26,992-token problem
        reached slowly. `docs/CAPABILITY_BLOCKS.md` §7 rejects that shape for
        packs and it is no better here.
        """
        events.add_message(self.thread, "assistant", "I will run profile_repository.")
        events.add_message(self.thread, "user", "no, do the baseline")
        events.add_message(self.thread, "assistant", "Right - measure_baseline it is.")
        said = conductor._what_the_last_reply_said(self.thread)
        self.assertIn("measure_baseline", said)
        self.assertNotIn("profile_repository", said)


class TheCoreRidesOnEveryTurnTest(_OnAThreadWithAPlan):
    def test_the_always_on_set_is_small_and_is_on_every_turn(self):
        """Nine, and the bound is the claim: a core that grew back to a pack
        would be this feature undone by addition."""
        self.assertLess(
            len(blocks.ALWAYS_ON), 10,
            "the always-on set grew past ten tools; write the argument for the "
            "tenth beside it or take it out",
        )
        self.assertEqual(
            len(set(blocks.ALWAYS_ON)), len(blocks.ALWAYS_ON), "a name twice"
        )
        for name in blocks.ALWAYS_ON:
            with self.subTest(tool=name):
                self.assertIn(name, REGISTRY.names(), "an always-on tool nobody registers")

    def test_every_one_of_them_rides_on_a_narrow_turn(self):
        wire = self.wire()
        for name in blocks.ALWAYS_ON:
            with self.subTest(tool=name):
                self.assertIn(name, wire.tools)
                self.assertIn("every turn", wire.because[name])

    def test_a_walk_that_could_not_be_computed_gets_every_schema(self):
        """The same direction `everything()` takes one layer out: a failure to
        select is not evidence about a person's situation."""
        active = blocks.active(None, thread_id=self.thread)
        wire = blocks.on_the_wire(active, thread_id=self.thread, payload=None)
        self.assertEqual(set(wire.tools), set(active.tools))
        #: READ OFF A TOOL THE CORE DOES NOT ALREADY CARRY. `wire.tools[0]`
        #: happens to be an always-on tool, whose reason is the core's, and an
        #: assertion on that one would pass on a selector that widened nothing.
        widened = [name for name in wire.tools if name not in blocks.ALWAYS_ON]
        self.assertTrue(widened)
        self.assertIn("nothing narrowed", wire.because[widened[0]])

    def test_a_pack_a_person_switched_off_is_not_reachable_by_naming_it(self):
        """SOURCE 5, AND IT NEEDS NO CODE HERE, which is the point of it.

        The pool is `active.tools`, and `_minus_what_was_switched_off` has
        already run. A model naming a switched-off tool in its reply must not
        get it back - a schema cut that could undo a person's switch would be a
        worse defect than the one it was built for.
        """
        settings.write(self.project, packs_off=["training"])
        active = blocks.active(PAYLOAD, thread_id=self.thread)
        self.assertNotIn("start_training", active.tools)
        wire = blocks.on_the_wire(
            active, thread_id=self.thread, payload=PAYLOAD,
            last_reply="I will run start_training now.",
            among=modes.tools_for("build", active.names()),
        )
        self.assertNotIn("start_training", wire.tools)


class TheSwitchIsRecordedEitherWayTest(_OnAThreadWithAPlan):
    """`MLH_ALL_SCHEMAS`, in the spirit of `MLH_FILL_BLANKS_FROM_THREAD`.

    On-demand schemas are a CONFOUND for any run that compares models, so a
    trial has to be able to turn them off - and a reading that cannot say which
    arm it was in is not a reading.
    """

    def test_the_default_is_on_demand(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(blocks.ALL_SCHEMAS_VARIABLE, None)
            self.assertFalse(blocks.all_schemas_ride())
            self.assertFalse(self.wire().all_schemas)

    def test_the_variable_restores_every_schema_and_the_turn_says_so(self):
        with mock.patch.dict(os.environ, {blocks.ALL_SCHEMAS_VARIABLE: "1"}):
            self.assertTrue(blocks.all_schemas_ride())
            wide = self.wire()
        self.assertEqual(set(wide.tools), set(self.among))
        self.assertTrue(wide.all_schemas)
        self.assertTrue(wide.as_dict()["all_schemas"])
        self.assertEqual(wide.as_dict()["withheld"], [])
        self.assertIn("MLH_ALL_SCHEMAS", wide.because[wide.tools[0]])

    def test_a_typo_reads_as_on_demand_rather_than_as_everything(self):
        """The safe direction is the one where the window stays the person's.

        The opposite default to `conductor.filling_is_on()`, and deliberately:
        the fill is help a person GETS, this is a cost a person PAYS.
        """
        with mock.patch.dict(os.environ, {blocks.ALL_SCHEMAS_VARIABLE: "yse"}):
            self.assertFalse(blocks.all_schemas_ride())

    def test_the_record_says_what_was_withheld_as_well_as_what_rode(self):
        """A pane that showed only what rode could not tell a narrow turn from a
        small harness, which is the fabrication `capabilities.py` exists for."""
        said = self.wire().as_dict()
        self.assertEqual(
            set(said["tools"]) | set(said["withheld"]), set(said["considered"])
        )
        self.assertTrue(said["withheld"], "this fixture withheld nothing")
        self.assertEqual(set(said["because"]), set(said["tools"]))


class TheNameIsStillInTheRoomTest(_OnAThreadWithAPlan):
    """THE HALF THAT MAY NOT MOVE.

    `app/instructions/capabilities.py`: asked through the real UI whether it
    could help build anything, a connected model said *"you will still need to
    handle the actual building and training"* while `start_training` was
    registered. It was repeating what we told it. A cut that dropped the names
    would rebuild that defect for 1,716 tokens of saving.
    """

    def test_the_list_names_every_registered_tool_whatever_rode(self):
        wire = self.wire()
        rendered = capabilities.render(detail=False, loaded=set(wire.tools))
        named = [
            line for line in rendered.splitlines() if line.startswith("- `")
        ]
        self.assertEqual(len(named), len(REGISTRY.names()))
        # 88 -> 90 on 2026-09-18: P9 landed build_environment (sandbox) and
        # write_the_results (training) in the same integration as this file.
        # 90 -> 91 at integration: P6 landed compile_the_plan (ledger, core).
        # 91 -> 93 later on 2026-09-18: read_observation (context; the door a
        # packed result is opened with) and generate_tool_rows (data; chain-first
        # rows). Neither is always-on; the reader rides only on a thread holding
        # a handle.
        self.assertEqual(len(REGISTRY.names()), 93, "the registry moved; re-take the census")
        for name in REGISTRY.names():
            with self.subTest(tool=name):
                self.assertIn(f"- `{name}`", rendered)

    def test_the_marks_are_the_schemas_and_the_count_is_honest(self):
        """The prompt says how many are loaded. It must be the number of tool
        definitions in the same request, or the harness is lying about its own
        request - which is the same defect as a number with no provenance."""
        wire = self.wire()
        rendered = capabilities.render(detail=False, loaded=set(wire.tools))
        self.assertIn(f"{len(wire.tools)} of these {len(REGISTRY.names())} are loaded", rendered)
        for name in wire.tools:
            with self.subTest(tool=name):
                self.assertIn(f"- `{name}` (*)", rendered)
        withheld = set(self.among) - set(wire.tools)
        self.assertTrue(withheld)
        for name in sorted(withheld):
            with self.subTest(withheld=name):
                self.assertNotIn(f"- `{name}` (*)", rendered)


class WhatTheTurnCostsNowTest(_OnAThreadWithAPlan):
    """THE NUMBER, RE-DERIVED RATHER THAN TRUSTED.

    MEASURED 2026-09-18 on this fixture, which is Max's own situation: a build
    thread whose plan aims at a phase that measures the baseline.

        before, packs only    34 schemas    9,395 tokens
        after, on the wire    10 schemas    2,238 tokens

    and with the instruction set at 7,825 tokens, system+tools falls from
    17,247 to 10,063.

    THE PLAN ASKED FOR UNDER 9,000 AND IT IS NOT REACHABLE HERE. That figure
    assumed instructions of ~7,900 and schemas of ~1,100; the nine-tool ledger
    core alone measures 1,512, so no selection at this layer can meet it. The
    remaining 7,825 is the instruction set, which is a different phase's lane -
    this file pins what the tool layer can actually hold and says so, rather
    than pinning a bound that would go red for somebody else's reason.
    """

    #: At most this many schemas on a turn aimed at one phase. TWELVE, not the
    #: ten measured, because the aimed phase is the author's list and a person
    #: who names two more instruments in a phase has not broken anything.
    MOST_SCHEMAS = 12

    #: The instruction set plus those schemas, in tokens.
    SYSTEM_AND_TOOLS = 10_300  # 10,200 -> 10,300 at integration 2026-09-18: measured 10,267; compile_the_plan is core and its schema now rides every turn

    def test_the_aimed_turn_carries_at_most_twelve_schemas(self):
        wire = self.wire()
        self.assertLessEqual(
            len(wire.tools), self.MOST_SCHEMAS,
            f"the aimed turn carried {len(wire.tools)} schemas: {sorted(wire.tools)}",
        )
        self.assertLess(
            len(wire.tools), len(self.among),
            "nothing was narrowed, so nothing was gained",
        )

    def test_system_plus_tools_fits_the_bound_this_was_measured_at(self):
        prompt = conductor.system_prompt(
            {"name": "x", "model": "m", "adapter": "openai", "base_url": "",
             "kind": "local", "tool_calling": "yes"},
            sensitive=False,
            loaded=frozenset(self.wire().tools),
            planning=False,
            examples=False,
        )
        cost = budget.estimate(prompt).tokens + _schema_tokens(self.wire().tools)
        self.assertLessEqual(
            cost, self.SYSTEM_AND_TOOLS,
            f"system+tools is {cost} tokens. Re-take this pin from a measurement "
            "rather than raising it because something shipped.",
        )

    def test_the_cut_is_worth_taking_on_this_thread(self):
        """NON-VACUOUS. A bound that the un-narrowed turn also met would be a
        number that proves nothing about the selector."""
        before = _schema_tokens(self.among)
        after = _schema_tokens(self.wire().tools)
        self.assertLess(after * 2, before, f"{before} -> {after} is not a cut")


class PlanModeIsAlreadyTheNarrowingTest(_OnAThreadWithAPlan):
    """`modes.PLAN_TOOLS` is a MEASURED list, not a derived one.

    Three arms on the owner's own question through his own model, 2026-09-11:
    lookups with no move gave `empty_reply` twice; the core on offer sent every
    turn to `run_diagnosis` instead of planning. Narrowing that list a second
    time here would be a heuristic overruling a trial.
    """

    def test_every_plan_tool_keeps_its_schema(self):
        pool = sorted(modes.tools_for("plan", self.active.names()))
        wire = blocks.every_schema(
            pool, because=blocks.BECAUSE_THE_MODE_IS_ALREADY_THE_LIST
        )
        self.assertEqual(set(wire.tools), set(pool))
        self.assertEqual(wire.as_dict()["withheld"], [])
        self.assertIn("PLAN_TOOLS", wire.because[wire.tools[0]])


class ASubAgentReadsItsWholePlanTest(unittest.TestCase):
    """A sub-agent's whole plan is one phase, so all of its steps are in scope.

    The same reading `_narrow_to_phase_packs` takes for a child, kept in step
    with it here so the two cannot drift into disagreeing about what a child's
    scope is.
    """

    def setUp(self) -> None:
        support.sandbox(self)
        parent = events.create_thread("parent", mode="build")
        self.child = int(
            events.create_thread(
                "child", mode="build", project_id=parent["project_id"]
            )["id"]
        )
        events.set_thread_plan(
            self.child,
            "# Phase" + chr(10) * 2 + "## Steps" + chr(10)
            + "- [ ] Score with measure_baseline" + chr(10)
            + "- [ ] Then run_eval on the winner" + chr(10),
        )
        subagents.ensure_table()
        with db.session() as connection:
            connection.execute(
                "INSERT INTO subagents(parent_thread_id, child_thread_id, phase, state) "
                "VALUES (?, ?, ?, ?)",
                (int(parent["id"]), self.child, "Phase", "running"),
            )

    def test_every_tool_its_steps_name_rides(self):
        self.assertTrue(subagents.is_a_subagent(self.child))
        active = blocks.active(PAYLOAD, thread_id=self.child)
        wire = blocks.on_the_wire(
            active, thread_id=self.child, payload=PAYLOAD,
            among=modes.tools_for("build", active.names()),
        )
        self.assertIn("measure_baseline", wire.tools)
        self.assertIn("run_eval", wire.tools)
        self.assertIn("sub-agent's plan", wire.because["run_eval"])


class _AScriptedModel:
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


class TheTurnRecordsWhichArmItRanInTest(unittest.TestCase):
    """THROUGH `run_turn`, because the unit above cannot see the wiring.

    Every assertion in this file until now is on `blocks.on_the_wire`. A
    conductor that computed a beautiful selection and then sent
    `REGISTRY.model_tools(in_this_mode)` anyway would pass all of them. So this
    drives a real turn and reads the two things a person and a trial each need:
    what the request actually carried, and which arm it was.
    """

    def setUp(self) -> None:
        support.sandbox(self)
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
        self.thread = int(events.create_thread("t", mode="build")["id"])
        events.add_message(self.thread, "user", "here is my dataset, what should I do")

    def turn(self):
        model = _AScriptedModel([[Delta(kind="text", text="ok")]])
        original = conductor.build
        conductor.build = lambda *a, **k: model
        self.addCleanup(setattr, conductor, "build", original)
        list(conductor.run_turn(self.thread))
        sent = {t["function"]["name"] for t in model.sent[0]["tools"]}
        context = events.latest("turn.context", self.thread)["payload"]
        return sent, context

    def test_the_request_carries_the_chosen_schemas_and_says_so(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(blocks.ALL_SCHEMAS_VARIABLE, None)
            sent, context = self.turn()
        said = context["schemas_on_wire"]
        self.assertEqual(sent, set(said["tools"]))
        self.assertEqual(context["tool_count"], len(said["tools"]))
        self.assertFalse(said["all_schemas"])
        self.assertEqual(said["switch"], blocks.ALL_SCHEMAS_VARIABLE)
        # NON-VACUOUS: a turn that withheld nothing would satisfy every line
        # above while costing the person exactly what it did before.
        self.assertTrue(said["withheld"])
        self.assertLess(len(said["tools"]), len(said["considered"]))
        for name in said["tools"]:
            with self.subTest(tool=name):
                self.assertTrue(said["because"][name].strip())

    def test_the_switch_restores_every_schema_through_the_conductor(self):
        with mock.patch.dict(os.environ, {blocks.ALL_SCHEMAS_VARIABLE: "1"}):
            sent, context = self.turn()
        said = context["schemas_on_wire"]
        self.assertEqual(sent, set(said["considered"]))
        self.assertEqual(said["withheld"], [])
        self.assertTrue(said["all_schemas"], "the arm was not recorded")
        self.assertGreater(len(sent), len(blocks.ALWAYS_ON))

    def test_the_two_arms_are_a_real_difference_in_what_a_person_pays(self):
        """A switch worth shipping is one that changes the number.

        The same assertion `test_a_person_can_turn_tools_off` makes about packs,
        one layer in: not that the record was written, but that the turn moved.
        """
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(blocks.ALL_SCHEMAS_VARIABLE, None)
            _, narrow = self.turn()
        with mock.patch.dict(os.environ, {blocks.ALL_SCHEMAS_VARIABLE: "1"}):
            _, wide = self.turn()
        self.assertLess(
            narrow["tools"] * 3,
            wide["tools"],
            f"{wide['tools']} -> {narrow['tools']} tokens of schema is not a cut",
        )


if __name__ == "__main__":
    unittest.main()
