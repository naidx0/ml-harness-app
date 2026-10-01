"""Capability blocks: what reaches the model, chosen by the thing that already knows.

`docs/PHASES.md` makes this Phase 1a and gives it a done-condition in three
parts: a turn sends the model only the blocks its diagnosis calls for, the
brief's budget stops rising as tools are added, and the active block is visible
as a LABEL rather than a choice. The budget half lives in
`tests/test_the_diagnosis_is_not_optional.py::WhatItCostsTest`, beside the five
paragraphs of history it ends. This file holds the rest.

## The two ways this goes wrong, and they are opposite

`docs/CAPABILITY_BLOCKS.md` names both and this file is organised around them.

**TOO EXCLUSIVE** is the one that would be worst and the one nobody would see:
somebody asks about their GPU in the middle of a data conversation and the
hardware tool is not loaded. That is a tab bar built on the inside of the
product, where the user cannot even see it, and `docs/VISION.md`'s moat is
holding the machine, the data, the repository and the budget AT ONCE.
`TheOffDomainQuestionStillReachesItsToolTest` is the proof it cannot happen -
driven through `run_turn`, on a thread ten rungs into data work, with the
question actually asked and the tool actually run.

**TOO INCLUSIVE** is the quiet one: every block always on, nothing gained, and a
milestone declared. `TheSetIsSmallerThanTheRegistryTest` is the guard, and every
assertion in it is a strict inequality against the registry rather than a
membership test - a selection that loaded everything would satisfy "the core is
present" and fail every line here.

## What is asserted about who chooses

Not the model. There is no tool that widens the set, no search interface to
query, and no argument that reaches the selection. That is
`registry.py`'s hard rule with one more clause on it - *a model may fill facts
and may not decide a gate; it may call tools and may not decide which tools it
has* - and `NoToolCanWidenTheSetTest` holds it structurally rather than by
policy.
"""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from app import conductor, diagnosis, events
from app.instructions import capabilities
from app.providers import Delta, ToolCall
from app.providers import store as provider_store
from app.tools import blocks, evidence
from app.tools.registry import REGISTRY, ToolError

import support


#: ABSOLUTE, off the engine's own constant. A relative path here resolves
#: against whatever directory the suite happens to be started from, and this
#: one is run from `tests/`.
LEDGER = diagnosis.SPEC_PATH.parent / "ledgers" / "ai_engineering.yaml"

#: The third ledger, for the reachability sweep. Resolved through the engine
#: rather than joined by hand, so a rename moves it.
HARNESS_LEDGER = "docs/ledgers/harness_design.yaml"


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


class TurnTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)

    def connect(self):
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

    def install(self, model):
        original = conductor.build
        conductor.build = lambda *a, **k: model
        self.addCleanup(setattr, conductor, "build", original)
        return model

    def thread(self, question):
        row = events.create_thread("t")
        events.add_message(row["id"], "user", question)
        return row["id"]

    def rows(self, thread_id):
        return events.since(f"thread:{thread_id}")

    def kinds(self, thread_id):
        return [row["kind"] for row in self.rows(thread_id)]

    def offered(self, model, round_index: int = 0) -> set[str]:
        return {
            tool["function"]["name"] for tool in model.sent[round_index]["tools"]
        }


# ---------------------------------------------------------------------------
# The declaration.


class EveryToolSaysWhichBlockItIsInTest(unittest.TestCase):
    """Wall 7, on the tools that actually ship."""

    def test_every_registered_tool_declares_a_published_capability(self):
        for spec in REGISTRY:
            with self.subTest(tool=spec.name):
                self.assertTrue(spec.provides, f"{spec.name} is in no block")
                for name in spec.provides:
                    self.assertIn(name, blocks.CAPABILITIES, name)

    def test_the_pack_is_the_namespace_and_nothing_writes_it_down(self):
        """Derived from the capability name, never declared a second time."""
        for spec in REGISTRY:
            with self.subTest(tool=spec.name):
                self.assertEqual(
                    spec.packs,
                    frozenset(name.split(".")[0] for name in spec.provides),
                )

    def test_every_pack_the_vocabulary_defines_has_a_gloss(self):
        """A pack a person can be shown but not told about is half a label."""
        self.assertEqual(set(blocks.packs()), set(blocks.PACKS))

    def test_registering_a_tool_with_no_capability_is_refused(self):
        from app.tools import Control, Registry, ToolSpec

        registry = Registry()
        with self.assertRaises(ToolError) as caught:
            registry.add(
                ToolSpec(
                    name="unplaced_tool",
                    description="A tool that belongs nowhere.",
                    schema={"type": "object", "properties": {}},
                    reads=(),
                    writes=(),
                    approval="never",
                    control=Control(label="X", group="Test", verb="x"),
                    handler=lambda: {"ok": True},
                )
            )
        self.assertIn("provides", str(caught.exception))
        # THE DOOR, NAMED. Every refusal in this product says what would have
        # worked, and there are eleven packs, so the honest answer fits.
        for pack in blocks.packs():
            self.assertIn(pack, str(caught.exception), pack)

    def test_registering_a_tool_with_an_unpublished_capability_is_refused(self):
        from app.tools import Control, Registry, ToolSpec

        registry = Registry()
        for bad in ("data", "retrievel.index.build", "Data.Eval_Set.Carve"):
            with self.subTest(capability=bad):
                with self.assertRaises(ToolError) as caught:
                    registry.add(
                        ToolSpec(
                            name="misspelled_tool",
                            description="A tool that names a pack that is not one.",
                            schema={"type": "object", "properties": {}},
                            reads=(),
                            writes=(),
                            approval="never",
                            provides=(bad,),
                            control=Control(label="X", group="Test", verb="x"),
                            handler=lambda: {"ok": True},
                        )
                    )
                self.assertIn(bad, str(caught.exception))

    def test_a_capability_nothing_provides_is_a_legal_state(self):
        """AND IT IS THE ONE THAT MAKES AN HONEST REFUSAL POSSIBLE.

        `docs/PHASES.md` names four instruments the AI-engineering ledger cannot
        be honest without - a trace reader, a tool-definition reader, a failure
        runner, a loop bounder - and none of them exists. A ledger that binds to
        one must be told exactly that, with the capability named, rather than
        handed a plan whose first step moves nothing. So `providers()` answers
        `()` rather than raising, and this is the shape driven with a name that
        genuinely has no provider.
        """
        published = "sandbox.instance.delete"
        self.assertEqual(blocks.providers(published), ("delete_sandbox",))

        from app.tools import Registry

        empty = Registry()
        self.assertEqual(blocks.providers(published, empty), ())
        self.assertEqual(blocks.tools_in(("sandbox",), empty), ())


# ---------------------------------------------------------------------------
# What is always on.


class TheCoreIsTheClosureOfTheSelectorTest(unittest.TestCase):
    """A selector that can be selected out of existence is a trap."""

    def test_the_door_back_into_the_engine_is_always_loaded(self):
        core = set(blocks.tools_in(blocks.CORE))
        for door in ("run_diagnosis", "propose_build", "state_facts"):
            self.assertIn(door, core, door)

    def test_the_evidence_door_is_always_loaded(self):
        """`offer_to_measure` names no fact of its own and reads whatever ledger
        it is handed. The five gates are the product; the instrument that keeps
        a claim from becoming a gate is not optional on any turn of any domain."""
        self.assertIn("offer_to_measure", blocks.tools_in(blocks.CORE))

    def test_the_machine_and_what_was_pointed_at_are_always_loaded(self):
        core = set(blocks.tools_in(blocks.CORE))
        for name in (
            "inspect_hardware",
            "list_local_models",
            "list_runs",
            "attach_context",
            "list_context",
            "read_context_file",
            "profile_repository",
            "preview_dataset_rows",
        ):
            self.assertIn(name, core, name)

    def test_a_ledger_may_widen_the_core_and_may_not_narrow_it(self):
        """The direction is not configurable, and this drives both halves."""
        widened = _ledger_with(core=["data"])
        self.assertEqual(
            set(blocks._core_packs(blocks.declared(widened))),
            set(blocks.CORE) | {"data"},
        )
        narrowed = _ledger_with(core=[])
        self.assertEqual(
            set(blocks._core_packs(blocks.declared(narrowed))), set(blocks.CORE)
        )
        # AND THROUGH THE SELECTION ITSELF, because a helper that agrees with a
        # test and not with the caller is a helper nobody is using.
        self.assertIn(
            "data",
            blocks.active(_payload({}, widened), thread_id=None, spec=widened).packs,
        )
        self.assertLessEqual(
            set(blocks.CORE),
            blocks.active(_payload({}, narrowed), thread_id=None, spec=narrowed).packs,
        )

    def test_the_core_is_twelve_tools_of_forty(self):
        """A count, so a core that quietly grew is a red test rather than a
        paragraph nobody re-derives. `docs/CAPABILITY_BLOCKS.md` A6 argues each
        of the four groups; if one is added, this number moves and the argument
        has to be written down beside it.

        2026-08-25: the registry is 44, not 40 - the `agent` pack shipped with
        docs/PHASES.md Phase 1's four instruments (`app/tools/agents.py`), and
        not one of them is core: no ML thread needs another ledger's instruments,
        which is the whole argument for packs. The CORE half of this assertion is
        unchanged at 12, which is the point of it.

        2026-08-26: the registry is 45 - `synthesize_rows` in the data pack
        follows the same argument: the floor under every domain that needs
        examples should not be assumed to have enough, and amplifying what you
        already have is structure, not content.

        2026-08-27: the registry is 47. `draw_verification_sample` and
        `record_verification` are the other half of `synthesize_rows` and they
        are in the same pack for the same reason - the ledger's own recipe is
        "have a human verify a 10% sample before training on any of it", so the
        thread that was handed the amplifier is the thread that needs the two
        tools which make its output usable. Neither is core: a domain with no
        synthesis has no use for either, which is the argument for packs again
        rather than a new one. CORE is still 12.

        2026-08-27, later: the registry is 48. `read_agent_results` reads back
        a graded failure run, or compares two of them pairwise, and it is in
        the `agent` pack beside the four instruments whose recordings it reads.
        Not core, and the argument is the sharpest version of the one above:
        it can say nothing at all to a thread that has never graded a failure
        set, because there is no recording for it to read. CORE is still 12,
        and every one of these four entries is the same sentence - a tool
        belongs to the domain whose question it answers.

        2026-08-27, later still: the registry is 49. `measure_the_format` counts
        what fraction of a person's outputs satisfy a schema they name, and it
        is in the `measurement` pack beside the eval bench. Not core, and here
        the argument is the ledger's rather than this file's:
        `contract.capabilities.needs` gives `stage_4_format` `[prompt,
        measurement, data]`, so the thread whose diagnosis reaches the format
        stage is the thread this tool loads on, and no other. CORE is still 12
        - five entries in this docstring now, and not one of them moved it.

        2026-09-09: the registry is 68 and CORE IS 18 - the first time this
        number has moved. `what_is_missing` is in the `ledger` pack, which is
        core, and it belongs there: it is the other half of `run_diagnosis`.
        That one says where a thread stopped; this one says what would move it.
        They were one door and a route for a fortnight - the deriving was built
        in `app/asking.py`, served at `GET /api/next_step`, and offered to
        nobody, which is why a model ran the diagnosis, got five gates reading
        NOT_REACHED, and had sixty-seven doors and no way to learn which one.

        THE COST, SAID RATHER THAN OMITTED. `asking.py` is written for one
        ledger - a recorded bounded debt - so on an AI-engineering thread this
        tool can only refuse, and being core it is offered there anyway. It is
        placed by what it IS rather than by what is currently wrong with it: a
        tool put in a non-core pack to dodge that limit would be in the wrong
        pack the day the limit is paid off, and nobody would move it.
        2026-09-11: the registry is 73 and CORE IS 20. `write_plan` and `read_plan` join the ledger
        pack - the plan is a tool call now, because a small model in plan mode
        kept choosing the next lookup and went silent when its budget ran out
        (thread 64, twice). They are core for the reason `run_diagnosis` is:
        the thread's own state is what every turn is about. The registry
        refuses a tool with no capability, so there was no pack-less way in.
        """
        # 12 -> 13: `read_the_standing_constraints`, in the `context` pack.
        # A test that goes red when core grows is the point of this line, and it
        # went red - the growth is deliberate and argued rather than quiet.
        # 15 -> 16: `set_the_project_root`, in the `context` pack, which is a
        # CORE pack - and core is always on by construction. THE THIRD ENTRY IN
        # THIS DOCSTRING'S ARGUMENT AND THE SAME ONE: the question is not
        # whether core grew, it is whether the tool belongs in core, and
        # `docs/PRODUCT_SPEC.md` 4.3 answers it. A project root is what every
        # other path in a project is found relative to, including the
        # HARNESS.md whose whole purpose is that things "should never be asked
        # twice" - and a tool the model can only sometimes see is a tool that
        # will let it ask twice. It is also the tool that made the other two
        # reachable at all: measured, `root_path` had no writer outside
        # `create_project`, so every fresh install refused all three.
        # 16 -> 17 on 2026-08-31: map_the_ask. The core is where arrival
        # lives, and mapping the arrival sentence is arrival work.
        # 20 -> 21 on 2026-09-11: `recall`, in the `context` pack - Hermes'
        # session search over this harness's own messages. Core for the
        # reason map_the_ask is: the first turn of a new thread is the turn
        # that needs to know what a sibling thread settled.
        # 21 -> 22 on 2026-09-11: `remember`, the second memory system from
        # Hermes (app/memory.py), in the same pack for the same reason.
        # 22 -> 23 on 2026-09-12: `mark_step_done`, the to-do list's tick, in
        # the ledger pack beside write_plan and read_plan - the plan's steps
        # are what every build turn is about, so it is on every build turn.
        # 23 -> 25 on 2026-09-13: `delegate_phase` and `check_the_sub_agents`,
        # in the LEDGER pack. Max asked for sub-agents that work one phase of
        # the plan each; the orchestrator's two moves are core for the reason
        # `write_plan` and `mark_step_done` are - they act on the document the
        # ledger pack exists to carry, and a turn that decides to hand a phase
        # out cannot wait for a pack to load before it can. Plan mode does not
        # see them: `modes.PLAN_TOOLS` does not list them, and there is nothing
        # to delegate before a plan exists.
        # 25 -> 26 on 2026-09-15: AU4 `run_project_command` in CONTEXT (core).
        # `run_sandbox_command` is sandbox pack, not core.
        # 26 -> 27 on 2026-09-16: CS17 `unpark_step`, ledger pack beside
        # `mark_step_done` — same capability (`ledger.plan.step`), same reason
        # the tick is core: a parked step that only the UI can reopen is a
        # door the model cannot walk through on a build turn.
        # 27 -> 28 on 2026-09-18: `compile_the_plan`, ledger pack beside
        # `write_plan` — same document, same argument, and one more: it is what
        # a run calls on a conversation that has no plan at all
        # (`longrun.compile_the_plan_first`), which is the turn that has the
        # least reason to be waiting for a pack to load.
        # 28 -> 29 later on 2026-09-18: `read_observation`, CONTEXT pack (core).
        # Its schema is NOT always-on - it rides only on a thread holding a
        # handle - but the pack it lives in is core, so the floor moves.
        self.assertEqual(len(blocks.tools_in(blocks.CORE)), 29)
        # 49 -> 50 -> 51: `score_a_candidate_model` in the `models` pack and
        # `rebucket_failures` in `measurement`. Neither is in CORE, so the left
        # number - the one this test is actually about - has not moved through
        # either.
        #
        # 54 -> 55: `count_preference_pairs`, in the `data` pack beside the two
        # other counts. Same argument, and it is the ledger's rather than this
        # file's: the fact it measures is read by ONE node, on the route to
        # preference optimisation, so the thread that loads it is the thread
        # whose diagnosis got there. CORE is still 15.
        #
        # 55 -> 61: SIX AT ONCE, and it is the largest single jump this line has
        # taken. `app/tools/harness.py` is a whole ledger's instruments arriving
        # together - `docs/ledgers/harness_design.yaml` declares thirteen
        # `inspect` facts and an `inspect` fact with no instrument is a gate
        # nobody can open, so a third domain either ships its readers or ships
        # gates that cannot be paid.
        #
        # THE LEFT NUMBER DID NOT MOVE AND THAT IS THE WHOLE POINT OF THIS LINE.
        # All six are in the selectable `harness` pack, which no ML sheet and no
        # AI sheet loads, so six tools landed and the core turn cost a person
        # nothing. That is what capability blocks promised and this is the
        # largest test it has been put to.
        # 61 -> 62: `set_the_project_root`, and this one DOES move the left
        # number - it is in `context`, a core pack. That is the honest price of
        # a tool that has to be visible on every turn, and the six before it are
        # the control: they moved the right number by six and the left by zero.
        # 62 -> 64: the knowledge pair (`read_model_shortlist`,
        # `read_gpu_prices`) - world-facts with a fetched_at, in Choose and
        # Look. They measure nothing, so no wall widened for them.
        # 64 -> 65: `carve_rows` - the data-collection instrument the
        # from-zero walk exposed as missing. Data pack, so it rides wherever
        # data work already loads.
        # 65 -> 66: map_the_ask, the playbook's door - core, so a small
        # conductor can map an arrival sentence before anything else loads.
        # 66 -> 67: read_local_recipes - validated serving recipes from the
        # Local AI Registry the owner pointed at, snapshotted with a date.
        # 68 -> 69: record_that_this_card_refuses, in the `models` pack beside
        # the CAN tools it asks. NOT CORE, and the argument is the separation
        # itself: a thread that has not named a model has nothing for it to
        # price, and a tool that can only refuse is the last thing to put in
        # front of somebody who has not asked yet. The left number is the
        # control and it did not move.
        # 69 -> 70: score_edge_direction, the edge-direction scorer the flagship
        # run is judged by - it asks whether relations point the right way,
        # which no schema can express, and it lands in MEASUREMENT rather than
        # core, so only the ceiling moves.
        # 70 -> 71: pair_edge_direction. A PAIRING IS NOT TWO SCORES - `b` and
        # `c` need to know which edges changed, not how many each arm got - so
        # it could not be a second call to the scorer above. Also MEASUREMENT,
        # so again only the ceiling moves.
        # 73 -> 74 on 2026-09-11: `recall`, the first of the three memory
        # systems the owner asked for from Hermes (app/recall.py). CONTEXT,
        # which is core, so the floor above moved with it.
        # 74 -> 75: `remember`, the second (app/memory.py). Core too.
        # 75 -> 77 on 2026-09-12: `generate_rows` and `judge_rows`, the
        # invent-a-dataset pair (app/tools/invent.py), in the DATA pack -
        # not core, so the floor below does not move and the ceiling does.
        # 77 -> 78 on 2026-09-12: `mark_step_done` (app/tools/planning.py), core.
        # 78 -> 80 on 2026-09-13: `delegate_phase` and `check_the_sub_agents`
        # (app/tools/delegation.py), the orchestrator's two moves, in LEDGER -
        # core, so the floor below moves with the ceiling.
        # 80 -> 84 on 2026-09-14: CS9 `set_goal` / `clear_goal` / `write_todo` /
        # `clear_todo` in the INTENT pack — never CORE, invite-only, so the
        # floor and the published selection range do not move.
        # 84 -> 86 on 2026-09-15: AU4 `run_sandbox_command` + `run_project_command`.
        # Project shell is CONTEXT (core) so the floor moves; sandbox shell is not.
        # 86 -> 87 on 2026-09-16: CS17 `unpark_step` (ledger/core).
        # 87 -> 88 on 2026-09-17: `set_baseline_target` (measurement, not core):
        # the baseline names the model it scores. Floor unchanged.
        # 88 -> 91 on 2026-09-18, three tools in one integration: `compile_the_plan`
        # (ledger/core, so the floor moves with the ceiling) and P9's two programs,
        # `build_environment` (SANDBOX) and `write_the_results` (TRAINING), neither
        # core, so they move the ceiling alone. Re-taken from the sweep, not summed.
        # 91 -> 93 later on 2026-09-18: `read_observation` (CONTEXT, core) and
        # `generate_tool_rows` (DATA). Re-taken from the sweep below.
        self.assertEqual(len(REGISTRY.names()), 93)


# ---------------------------------------------------------------------------
# The selection is smaller than the registry, and it is chosen by the walk.


def _payload(facts, spec=None):
    """One standing diagnosis, in the shape `run_diagnosis` puts on the wire."""
    from app.tools import next_moves

    current = spec or diagnosis.default_spec()
    result = diagnosis.diagnose(facts, current)
    payload = {
        "ok": True,
        "outcome": result.outcome,
        "verdict": result.verdict,
        "say": result.say,
        "proposed_method": result.proposed_method,
        "gate_ledger": result.gate_ledger,
        "path": [entry.as_dict() for entry in result.path],
        "fact_origins": result.fact_origins,
        "facts_used": {
            name: {"value": None, "origin": origin, "how": ""}
            for name, origin in result.fact_origins.items()
            if origin != "DEFAULTED"
        },
        "decided_by": "app/diagnosis.py",
    }
    payload.update(next_moves.next_moves(result, spec=current, facts_used={}))
    if result.unsubstantiated:
        payload["unsubstantiated"] = [
            dict(row, next_step=evidence.resolves(row["fact"]))
            for row in result.unsubstantiated
        ]
    return payload


def _ledger_with(**capabilities_block):
    """A scratch copy of the ML ledger whose `contract.capabilities` is replaced.

    WRITTEN INTO A TEMP FILE AND NEVER INTO THE TREE. What is proved is that the
    reader works against a ledger the ENGINE loaded and validated, rather than
    against a stand-in object shaped to agree with it.

    IT REPLACES RATHER THAN INSERTS, AND THAT IS NOT A TIDY-UP. The shipped
    ledger now declares the block itself, so splicing a second `capabilities:`
    under the same `contract:` is a duplicate YAML key - the last one silently
    wins and every case below would have been testing a fixture that lied about
    which declaration it was exercising. So the existing block is cut out by
    indentation and the case's own is put in its place.

    `needs` is COMPLETED AND IS ALWAYS WRITTEN, even by a case that only cares
    about `core:`, because `blocks.declared` now refuses a block that names some
    of a ledger's stages and not all of them - and a block with no `needs:` key
    at all has left every stage out. A case that cares about one stage says so
    and gets `[]` for the rest, which is what a real ledger would have to write.
    A case that wants the SHIPPED declaration back asks for it by name.

    So the default here is the empty declaration, and that is the useful default
    rather than the convenient one: it is the ledger saying "no stage's work
    needs a pack beyond the core", which is exactly the ledger against which the
    DERIVED half of the selection can be tested on its own.
    """
    source = diagnosis.SPEC_PATH.read_text(encoding="utf-8")
    stages = sorted(diagnosis.default_spec().stages)
    block = dict(capabilities_block)
    asked = dict(block.get("needs") or {})
    block["needs"] = {stage: asked.get(stage, ()) for stage in stages} | {
        # A case deliberately naming a stage that does not exist must still
        # reach the refusal that exists for it.
        name: wanted
        for name, wanted in asked.items()
        if name not in set(stages)
    }
    body = ["  capabilities:"]
    for key, value in block.items():
        if isinstance(value, dict):
            body.append(f"    {key}:")
            for inner, items in value.items():
                body.append(f"      {inner}: [{', '.join(items)}]")
        else:
            body.append(f"    {key}: [{', '.join(value)}]")

    out, cutting, replaced = [], False, False
    for line in source.split("\n"):
        if cutting:
            # Inside the shipped block: every line more indented than the key,
            # plus blank lines, belongs to it.
            if not line.strip() or line.startswith("      ") or line.startswith("    "):
                continue
            cutting = False
        if line.rstrip() == "  capabilities:":
            out.extend(body)
            cutting, replaced = True, True
            continue
        out.append(line)
    assert replaced, (
        "the shipped ledger no longer declares contract.capabilities, so this "
        "fixture is replacing nothing and every case below is vacuous"
    )
    path = pathlib.Path(tempfile.mkdtemp()) / "scratch_ledger.yaml"
    path.write_text("\n".join(out), encoding="utf-8")
    return diagnosis.load_spec(path)


class TheSetIsSmallerThanTheRegistryTest(unittest.TestCase):
    """TOO INCLUSIVE is the quiet failure. Every line here is a strict <."""

    def setUp(self):
        self.spec = diagnosis.default_spec()

    def test_an_empty_ledger_gets_the_core_and_what_its_first_stage_declares(self):
        """AND THE SECOND HALF OF THAT NAME IS A CORRECTION, NOT A DETAIL.

        This asserted `== CORE` until 2026-08-24 and passing it was the defect:
        an empty ML thread stops in `stage_0_admissibility`, whose entire work -
        `BLOCKED__DEFINE_SUCCESS_FIRST`, `ACTION__SET_A_TARGET_SCORE`,
        `NO_ML__WRITE_CODE` - is answered by looking at the person's data, and
        the `data` pack was not loaded to do it. A fresh thread asking "how many
        rows are in my eval set?" got `not_loaded`.

        So the assertion is now `core plus exactly what the ledger declares for
        the stage the walk stopped in`, derived from the ledger rather than
        typed, which is the same shape and cannot pass by accident.

        AND SO IS THE THIRD HALF, ADDED 2026-09-13, which is the same
        correction one pack further out. The stage-0 walk stops on `modality`,
        declared `source: derive` - NO INSTRUMENT READS IT. The `data` pack
        arrived above because the stage's work is answered by looking at the
        person's data; `measurement` arrives now because the GATES ahead are
        answered by measuring, and a thread held at a stop nothing can clear
        was being denied the measuring as well. Measured on the owner's thread
        70: nine turns, each one announcing `measure_baseline` and unable to
        call it.
        """
        active = blocks.active(_payload({}), thread_id=None, spec=self.spec)
        declared = blocks.declared(self.spec)
        stage = blocks._stage_of(_payload({}), self.spec)
        self.assertEqual(stage, "stage_0_admissibility")
        self.assertEqual(active.packs, frozenset(_fresh_thread_packs()))
        self.assertIn("data", active.packs)
        self.assertIn("measurement", active.packs)
        self.assertIn("measure_baseline", active.names())
        self.assertLess(len(active.tools), len(REGISTRY.names()))

    def test_the_data_floor_arrives_when_the_walk_asks_for_a_count(self):
        """`BLOCKED__BUILD_EVAL_SET` is where a real thread stops first, and the
        pack that answers it is the one that loads.

        BOTH HALVES, SEPARATELY, because they are two sources and a test that
        cannot tell them apart is a test that would not notice one dying. The
        shipped ledger DECLARES the pack for that stage, so against it the reason
        names the stage. Against a ledger declaring nothing, the derivation
        alone still finds it and the reason names `measure_eval_set` - which is
        what "the derivation is not a fallback" means, driven rather than said.
        """
        payload = _payload({"target_score": 0.8})
        active = blocks.active(payload, thread_id=None, spec=self.spec)
        self.assertIn("data", active.packs)
        self.assertIn("carve_eval_set", active.tools)
        self.assertLess(len(active.tools), len(REGISTRY.names()))
        self.assertIn("stage_0_admissibility", active.because["data"])

        silent = _ledger_with()
        self.assertEqual(blocks.declared(silent).needs["stage_0_admissibility"], ())
        alone = blocks.active(
            _payload({"target_score": 0.8}, silent), thread_id=None, spec=silent
        )
        self.assertIn("data", alone.packs)
        self.assertIn("carve_eval_set", alone.tools)
        self.assertIn("measure_eval_set", alone.because["data"])

    def test_the_retrieval_pack_arrives_on_a_retrieval_answer(self):
        import diagnosis_fixtures as fixtures

        facts = fixtures.REACHING["ACTION__MEASURE_RETRIEVER_RECALL"]
        active = blocks.active(_payload(facts), thread_id=None, spec=self.spec)
        self.assertIn("retrieval", active.packs)
        self.assertIn("measure_retriever_recall", active.tools)
        self.assertNotIn("training", active.packs)

    def test_no_declared_outcome_loads_the_whole_registry(self):
        import diagnosis_fixtures as fixtures

        for outcome, facts in sorted(fixtures.REACHING.items()):
            with self.subTest(outcome=outcome):
                active = blocks.active(
                    _payload(facts), thread_id=None, spec=self.spec
                )
                self.assertLess(
                    len(active.tools),
                    len(REGISTRY.names()),
                    f"{outcome} selected every tool, so nothing was gained",
                )

    def test_every_pack_carries_a_reason_and_the_reason_names_something(self):
        active = blocks.active(
            _payload({"target_score": 0.8}), thread_id=None, spec=self.spec
        )
        self.assertEqual(set(active.because), set(active.packs))
        for pack, why in active.because.items():
            with self.subTest(pack=pack):
                self.assertTrue(why.strip(), pack)

    def test_a_walk_that_could_not_be_computed_gets_everything(self):
        """The expensive direction of being wrong is a person who cannot reach
        what they need, and a failed walk is not evidence about their situation."""
        active = blocks.active(None, thread_id=None, spec=self.spec)
        self.assertEqual(set(active.tools), set(REGISTRY.names()))

    def test_a_ledger_declaration_widens_and_says_which_stage_asked(self):
        spec = _ledger_with(needs={"stage_0_admissibility": ["retrieval"]})
        active = blocks.active(_payload({}, spec), thread_id=None, spec=spec)
        self.assertIn("retrieval", active.packs)
        self.assertIn("stage_0_admissibility", active.because["retrieval"])
        # NON-VACUOUS: without the declaration the same sheet gets the core.
        plain = blocks.active(_payload({}), thread_id=None, spec=self.spec)
        self.assertNotIn("retrieval", plain.packs)

    def test_a_ledger_declaration_can_name_a_build_for_an_outcome(self):
        spec = _ledger_with(
            builds={"BLOCKED__DEFINE_SUCCESS_FIRST": ["prompt.attempt.score"]}
        )
        active = blocks.active(_payload({}, spec), thread_id=None, spec=spec)
        self.assertIn("prompt", active.packs)
        self.assertIn("prompt.attempt.score", active.because["prompt"])

    def test_a_ledger_whose_block_cannot_be_read_widens_and_says_so(self):
        """LOUD WHERE AN AUTHOR IS LOOKING, WIDE WHERE A USER IS STANDING.

        `declared()` refuses a malformed block, which is what a ledger author
        needs. A person mid-conversation needs something else: the expensive
        direction of being wrong about a tool set is somebody who cannot reach
        what they need, so a selection that cannot be computed gets EVERY pack
        and every one of them carries the reason.
        """
        spec = _ledger_with(core=["retrievel"])
        with self.assertRaises(blocks.BlockError):
            blocks.declared(spec)
        active = blocks.active(_payload({}, spec), thread_id=None, spec=spec)
        self.assertEqual(set(active.tools), set(REGISTRY.names()))
        self.assertIn("could not be read", active.because["training"])

    def test_a_ledger_that_misspells_anything_is_refused_rather_than_ignored(self):
        for bad in (
            {"core": ["retrievel"]},
            {"needs": {"stage_nobody_wrote": ["data"]}},
            {"builds": {"X": ["data.eval_set.carve_it"]}},
        ):
            with self.subTest(block=bad):
                with self.assertRaises(blocks.BlockError):
                    blocks.declared(_ledger_with(**bad))


# ---------------------------------------------------------------------------
# THE OTHER HEADLINE, AND IT IS THE ONE THAT WAS MISSING.
#
# Everything above this line asks "is the set smaller than the registry?" and
# every one of those questions had a passing answer on 2026-08-24 while fifteen
# of the forty tools could not be selected on ANY thread against EITHER shipped
# ledger. A bound that only ever pushes one way cannot see that: "fewer than 40"
# is satisfied just as well by 12 as by 12-of-a-reachable-40.
#
# So the class below is the floor under the ceiling. It asks the opposite
# question - is every tool reachable from SOME answer this engine can give? -
# and it is the assertion that would have gone red the day the defect landed.


class EveryToolIsReachableFromSomeAnswerTest(unittest.TestCase):
    """A tool the selector can never choose is a tool the model does not have.

    THE DEFECT THIS CLASS EXISTS FOR, measured before it was fixed. Four
    selection sources, and three of them key on a FACT: what a failed gate is
    waiting on, what an alternative would settle, what this thread has already
    stamped. A pack whose tools declare no `measures=` is unreachable through
    all three - and five packs are exactly that, because measuring and DOING are
    different jobs and it is the doing tools that stamp nothing:

        prompt 2 tools, tabular 1, models 2, training 6, sandbox 4 - 15 of 40.

    Swept over all 63 sheets `diagnosis_fixtures` holds, the union of packs ever
    selected was six of eleven. A thread whose verdict was `TRAIN__LORA_SFT`
    could not be handed `start_training`; a thread whose answer WAS the tree
    could not be handed `fit_a_tree_model`. The fix is the ledger declaring what
    each stage's work needs, and these are the assertions that hold it there.
    """

    def setUp(self):
        self.spec = diagnosis.default_spec()

    def sheets(self):
        """Every fact sheet this repository has, all three sets of them.

        MINTING is included and it is the set that matters most here: it holds
        the nine `TRAIN__` verdicts, which are the answers whose own work was
        unreachable. REACHING alone would have left them out.
        """
        import diagnosis_fixtures as fixtures

        yield "an empty sheet", {}
        for outcome, facts in sorted(fixtures.MINTING.items()):
            yield outcome, facts
        for outcome, facts in sorted(fixtures.REACHING.items()):
            yield outcome, facts
        for label, case in sorted(fixtures.SPREAD.items()):
            yield label, case["facts"]

    def sheet_for(self, outcome):
        """One fact set that actually reaches this outcome, found rather than
        typed - the same outcome lives in a different fixture set depending on
        whether it mints, spreads or merely reaches."""
        for label, facts in self.sheets():
            if _payload(facts, self.spec)["outcome"] == outcome:
                return facts
        raise AssertionError(f"no fixture reaches {outcome}")

    def ai_sheets(self):
        """The second ledger's sheets, imported from the test that owns them.

        ADDED 2026-08-25: the reachability sweep used to mean "every ML sheet",
        because ML was the whole product. The `agent` pack's four tools are
        reachable from no ML answer BY DESIGN - they are the second ledger's
        instruments - so a sweep that does not drive AI sheets proves a third
        of the registry unreachable while believing itself complete, which is
        exactly the one-directional-bound defect docs/PHASES.md records.

        SHEETS entries are kwargs for that module's `LedgerCase.facts()`; the
        case gets its spec attribute here the way its own setUpClass sets it,
        because only the class is borrowed, not its runner.
        """
        import test_the_ai_ledger_refuses_before_it_builds as ai

        if not hasattr(ai.LedgerCase, "spec"):
            ai.LedgerCase.spec = diagnosis.load_spec(ai.LEDGER)
        case = ai.LedgerCase("run")
        yield "ai: an empty sheet", {}
        for label, change in sorted(ai.SHEETS.items()):
            yield f"ai: {label}", case.facts(**change)

    def harness_sheets(self):
        """The third ledger's sheets, and the same argument the AI ones made.

        ADDED 2026-08-28. The `agent` pack's tools were reachable from no ML
        answer BY DESIGN, so a sweep that drove only ML sheets proved a third of
        the registry unreachable while believing itself complete - the
        one-directional-bound defect `docs/PHASES.md` records. The `harness`
        pack's six tools are in exactly that position with respect to both
        earlier ledgers, so this file grows a third source rather than a third
        exception.
        """
        import harness_fixtures

        yield from harness_fixtures.every_sheet()

    def selected(self):
        union: set[str] = set()
        tools: set[str] = set()

        def sweep(spec, sheets):
            nonlocal union, tools
            for _, facts in sheets:
                active = blocks.active(
                    _payload(facts, spec), thread_id=None, spec=spec
                )
                union |= set(active.packs)
                tools |= set(active.tools)

        sweep(self.spec, list(self.sheets()))
        sweep(diagnosis.load_spec(LEDGER), list(self.ai_sheets()))
        sweep(diagnosis.spec_at(HARNESS_LEDGER), list(self.harness_sheets()))
        # CS9 — `intent` is invite-only. No diagnosis sheet selects it; the
        # host checkbox does, the same door `run_turn(..., invite_goal_edit=True)`
        # opens. Counting it here is the fourth reachability source, not an
        # exception that drops the claim "every pack is reachable".
        invite = frozenset({"intent"})
        union |= invite
        tools |= set(blocks.tools_in(invite))
        return union, tools

    #: The narrowest and widest turn this engine produces, MEASURED over every
    #: sheet both ledgers have. `docs/PHASES.md` publishes this pair, and it
    #: published a wrong one: on 2026-08-27 the upper bound had been raised from
    #: 28 to 29 by ADDING ONE when a tool shipped, which is arithmetic standing
    #: where a measurement belongs. A tool going into a pack widens only the
    #: turns that load that pack, and whether any sheet loads it is a question
    #: about the ledger rather than about the registry's size.
    #:
    #: A FLOOR AND A CEILING, both, and the floor is the one that matters. This
    #: file already records the class: *"a bound that only ever pushes in one
    #: direction cannot see the failure in the other"* - every assertion here
    #: was a strict `<` against the registry while a third of the product became
    #: unreachable, because "fewer than 40" is satisfied by 12 just as well as
    #: by 12-of-a-reachable-40.
    #: 12 -> 13 on 2026-08-28, and the LEFT number moving is the news. It had
    #: held through two tools that landed in selectable packs; this one is in
    #: `context`, which is core, so it is on every turn by construction. That is
    #: a deliberate widening of core and not a leak - see FOCUSED_BUDGET in
    #: `tests/test_the_diagnosis_is_not_optional.py` for the argument.
    #: 18 -> 20 on 2026-09-11: `write_plan` and `read_plan` join the ledger
    #: pack, which is core, so the FLOOR moves - both are on the emptiest
    #: turn there is. The ceiling moves by the same two below, which is the
    #: signature of a widening of core rather than a pack growing.
    #: 20/44 -> 21/45 on 2026-09-11: `recall` lands in CONTEXT, which is core,
    #: so both ends move by one - the core signature again, re-taken from
    #: this sweep.
    #: 21/45 -> 22/46, same day: `remember`, CONTEXT, core - both ends again.
    #: 22/48 -> 23/49 on 2026-09-12: `mark_step_done`, LEDGER, core - both
    #: ends by one, the core signature.
    #: 23/49 -> 25/59 on 2026-09-13, and BOTH HALVES ARE DELIBERATE, re-taken
    #: from this sweep rather than added to:
    #:   +2 on both ends - `delegate_phase` and `check_the_sub_agents` join
    #:     LEDGER, which is core, so the floor moves with the ceiling. They
    #:     are core for the reason the plan tools are: an orchestrator that
    #:     cannot hand out a phase on the turn it decides to is not one.
    #:   +8 on the ceiling alone - `blocks.active` now widens when the walk is
    #:     stopped on a fact no tool measures. The widest sheet in this sweep is
    #:     such a sheet, so it loads the instruments the gates read; a sheet
    #:     whose frontier IS a tool call away loads exactly what it used to,
    #:     which is why the floor did not move by more than the two.
    #: 25/59 -> 26/61 on 2026-09-15: AU4 — `run_project_command` (CONTEXT/core)
    #: moves both ends by one; `run_sandbox_command` (sandbox pack) moves the
    #: ceiling by one more on the widest sheet. Re-taken from this sweep.
    #: 26/61 -> 27/62 on 2026-09-16: CS17 `unpark_step` in ledger/core (same
    #: capability as `mark_step_done`) — both ends move by one, the core
    #: signature. Re-taken from this sweep.
    #: 27/63 -> 28/64 on 2026-09-18: `compile_the_plan` in ledger/core beside
    #: `write_plan` — both ends move by one, the core signature for the ninth
    #: time. RE-TAKEN FROM THIS SWEEP: 28 at 'ai: everything tried, dynamic'
    #: and 64 at 'teaching_from_scratch', which is what the runner printed.
    #: 28 -> 29 later on 2026-09-18: `read_observation` (CONTEXT, core). RE-TAKEN.
    NARROWEST_TURN = 29
    #: 28 -> 29 -> 30 across 2026-08-28, EACH TAKEN FROM THIS SWEEP and never
    #: by adding one because a tool shipped - which is what the failure message
    #: below forbids. Two tools landed that day, `score_a_candidate_model` and
    #: `rebucket_failures`, and the sweep reported the number each time. That
    #: the two happen to agree with a count is a coincidence of this pair; the
    #: rule is that the number comes from the sweep, and the day a tool lands in
    #: a pack no wide turn loads it will not move at all.
    #: 15/33 -> 16/34 on 2026-08-28, and BOTH ends moved by exactly one, which
    #: is the signature of a CORE tool rather than a packed one: core is on
    #: every turn, so it widens the narrowest and the widest together. A tool
    #: that had landed in a selectable pack would have moved the ceiling alone,
    #: or neither. Re-taken from this sweep, never by adding one.
    #: 16/34 -> 16/36 on 2026-08-29: the knowledge pack's two tools, and this
    #: time ONLY the ceiling moved - the complementary signature. They ride
    #: stages 6 and 7, which the widest sheet already reaches, and no narrow
    #: turn loads them: exactly what a selectable pack is supposed to cost.
    #: 16/36 -> 16/37 on 2026-08-30: carve_rows joins the data pack; the
    #: ceiling alone moves again. The narrowest turn's sheet does not load
    #: data, so collection costs an empty turn nothing.
    #: 16/37 -> 17/38 on 2026-08-31: map_the_ask - the ask-to-journey
    #: dictionary - lands in CONTEXT, which is core, so both ends move by one:
    #: the map has to be present on the very first turn of an empty thread,
    #: because that is the turn whose ask needs mapping.
    #: 17/38 -> 17/39 on 2026-08-31: read_local_recipes joins the knowledge
    #: pack; the ceiling alone moves, the third time this signature has held.
    #: 18/40 -> 18/41 on 2026-09-10: score_edge_direction joins MEASUREMENT,
    #: which is a pack and not core, so the ceiling alone moves and the floor
    #: does not - the fourth time this signature has held, and the check that
    #: tells a growing registry apart from a leak into every turn.
    #: 42 -> 44 on 2026-09-11: the same two tools, for the same reason.
    #: 44 -> 45 on 2026-09-11: `recall`, core, so the floor moved with it.
    #: 22/46 -> 22/48 on 2026-09-12: `generate_rows` and `judge_rows` join
    #: the DATA pack, which the widest sheet loads and the emptiest turn does
    #: not - the ceiling alone moves, the pack signature, fifth time held.
    #: 49 -> 59 on 2026-09-13: see the note on NARROWEST_TURN - two core tools
    #: and the stuck-walk widening, and this is the number the sweep produced.
    #: 61 -> 62 on 2026-09-16: see NARROWEST_TURN — `unpark_step` core signature.
    #: 62 -> 63 on 2026-09-17: `set_baseline_target` joins `measure_baseline`
    #: in MEASUREMENT, so every sheet that widens to the baseline widens by
    #: one tool. Re-taken from this sweep, not added by hand.
    #: 63 -> 66 on 2026-09-18 at integration: +1 from `compile_the_plan` (core,
    #: moves with the floor) and +2 from P9's SANDBOX and TRAINING tools, which
    #: the widest sheet `teaching_from_scratch` loads. RE-TAKEN FROM THIS SWEEP.
    #: 66 -> 68 later on 2026-09-18: +1 `read_observation` (core, moves with the
    #: floor) and +1 `generate_tool_rows` (DATA, on the widest sheet). RE-TAKEN.
    WIDEST_TURN = 68

    def test_the_published_selection_range_is_the_one_a_sweep_produces(self):
        """The pair `docs/PHASES.md` prints, re-derived rather than trusted."""
        sizes: list[tuple[int, str]] = []

        def sweep(spec, sheets):
            for label, facts in sheets:
                active = blocks.active(
                    _payload(facts, spec), thread_id=None, spec=spec
                )
                sizes.append((len(blocks.tools_in(active.packs)), label))

        sweep(self.spec, list(self.sheets()))
        sweep(diagnosis.load_spec(LEDGER), list(self.ai_sheets()))
        sweep(diagnosis.spec_at(HARNESS_LEDGER), list(self.harness_sheets()))

        self.assertGreaterEqual(
            len(sizes), 90, "the corpus this range is measured over is not there"
        )
        narrowest, where_narrow = min(sizes)
        widest, where_wide = max(sizes)
        self.assertEqual(
            (self.NARROWEST_TURN, self.WIDEST_TURN),
            (narrowest, widest),
            f"the selection range moved: {narrowest} at {where_narrow!r} and "
            f"{widest} at {where_wide!r}. That is a real change in what a turn "
            "costs a person - re-take the number in docs/PHASES.md's census "
            "from THIS sweep, and never by adding one because a tool shipped.",
        )

    def test_every_pack_is_selected_by_at_least_one_answer_this_engine_gives(self):
        union, _ = self.selected()
        self.assertEqual(
            union,
            set(blocks.packs()),
            "a pack no sheet selects is a pack no thread can reach",
        )

    def test_every_registered_tool_reaches_the_model_on_some_sheet(self):
        """The same claim in the units that matter to a person: tools."""
        _, tools = self.selected()
        self.assertEqual(tools, set(REGISTRY.names()))

    def test_the_answers_the_adversary_drove_load_the_tools_that_do_them(self):
        """FOUR NAMED PROBES, each a verdict whose own work was unreachable.

        These are the exact four an adversary drove through `run_turn` on
        2026-08-24 and got `not_loaded` on every one. They are asserted by name
        rather than only through the union above, because the union would go
        green again if some OTHER sheet happened to reach each pack while these
        four still did not.
        """
        for outcome, tool in (
            ("NO_DEEP__GRADIENT_BOOSTED_TREES", "fit_a_tree_model"),
            ("TRAIN__LORA_SFT", "start_training"),
            ("NO_TRAIN__BETTER_PROMPT", "try_prompt"),
            ("NO_TRAIN__SWAP_MODEL", "find_models"),
        ):
            with self.subTest(outcome=outcome):
                payload = _payload(self.sheet_for(outcome), self.spec)
                self.assertEqual(payload["outcome"], outcome)
                active = blocks.active(payload, thread_id=None, spec=self.spec)
                self.assertIn(tool, active.tools)
                # AND STILL NARROW. The cure for "the answer's tools are
                # missing" must not be "load everything", which is the failure
                # this whole file's other half exists to refuse.
                self.assertLess(len(active.tools), len(REGISTRY.names()))

    def test_every_gated_verdict_can_reach_the_work_it_commits_to(self):
        """The expensive irreversible half, by PREFIX rather than by a list.

        `contract.outcome_prefixes` names which prefix is the gated one, so a
        ledger that renames `TRAIN__` tomorrow is followed here rather than
        quietly skipped - the same rule `app/diagnosis.py` follows.
        """
        import diagnosis_fixtures as fixtures

        prefix = self.spec.gated_prefix
        self.assertTrue(prefix, "this ledger declares no gated prefix")
        gated = [one for one in sorted(fixtures.MINTING) if one.startswith(prefix)]
        self.assertGreaterEqual(len(gated), 5, "no gated outcome was exercised")
        for outcome in gated:
            with self.subTest(outcome=outcome):
                payload = _payload(fixtures.MINTING[outcome], self.spec)
                self.assertEqual(payload["outcome"], outcome)
                active = blocks.active(payload, thread_id=None, spec=self.spec)
                self.assertIn("training", active.packs)
                self.assertIn("start_training", active.tools)

    def test_a_declared_block_that_leaves_a_stage_out_is_refused(self):
        """AND THE RULE THAT STOPS IT COMING BACK BY OMISSION.

        A ledger growing a stage and forgetting its capabilities is the same
        defect with a new spelling: an answer reaching a person with the tools
        that would act on it unloaded. `docs/LEDGER_FORMAT.md` §3 already says
        empty is a legal answer and absent is not; this is that rule with teeth.
        """
        # ONE LINE, INSIDE `needs:`, AND NOTHING ELSE. Matched on the exact
        # six-space indent that block uses, because the same stage id is also a
        # TOP-LEVEL key and `contract.roles.commit_stages` names it - cutting
        # that one produces a ledger the engine refuses outright (LF014), which
        # would have made this test green for a completely different reason.
        source = diagnosis.SPEC_PATH.read_text(encoding="utf-8")
        target = "      stage_9_method_selector:"
        self.assertEqual(
            sum(1 for line in source.split("\n") if line.startswith(target)),
            1,
            "the needs: block does not declare that stage on exactly one line",
        )
        out = [line for line in source.split("\n") if not line.startswith(target)]
        path = pathlib.Path(tempfile.mkdtemp()) / "one_stage_short.yaml"
        path.write_text("\n".join(out), encoding="utf-8")

        # The ledger itself is still valid. Only its capability block is short.
        short = diagnosis.load_spec(path)
        self.assertEqual(set(short.stages), set(self.spec.stages))

        with self.assertRaises(blocks.BlockError) as caught:
            blocks.declared(short)
        self.assertIn("stage_9_method_selector", str(caught.exception))

        # AND THE RUNNING PRODUCT WIDENS RATHER THAN GUESSES. Loud where an
        # author can see it, wide where a user is standing: a block that cannot
        # be read gets everything, with the reason on every pack.
        wide = blocks.active(_payload({}, short), thread_id=None, spec=short)
        self.assertEqual(set(wide.tools), set(REGISTRY.names()))
        self.assertIn("contract.capabilities", wide.because["training"])

    def test_the_ledger_declares_a_pack_the_engine_publishes_for_every_stage(self):
        """The shipped ML ledger's own block, checked against the engine.

        Not a re-read of `declared()`: this asserts the DOCUMENT names every
        stage the document has, so the two halves have to agree in the file a
        person edits rather than only in the object the engine built.
        """
        book = blocks.declared(self.spec)
        self.assertTrue(book.present)
        self.assertEqual(set(book.needs), set(self.spec.stages))
        for stage, wanted in book.needs.items():
            for pack in wanted:
                self.assertIn(pack, blocks.packs(), f"{stage} -> {pack}")


# ---------------------------------------------------------------------------
# THE HEADLINE. Too exclusive must be impossible.


class TheOffDomainQuestionStillReachesItsToolTest(TurnTest):
    """A person asks about their GPU in the middle of a data conversation.

    This is the failure `docs/PHASES.md` says would be worst and would be
    invisible: a block that HIDES is a tab, built on the inside of the product
    where the user cannot even see it. So it is driven rather than reasoned
    about - a thread with real data facts on its ledger, a diagnosis standing
    over them, the hardware question actually asked, and `inspect_hardware`
    actually run and actually answering.

    The mechanism that makes it safe is not a special case: `machine` is CORE,
    and the core is the closure of the selector. Nothing about hardware had to
    be anticipated for this to hold.
    """

    def data_conversation(self) -> int:
        """A thread ten rungs in: an eval set counted, a baseline scored.

        Stamped through `evidence.instrument_for`, which is the licence the
        registry hands a handler, on the real tools' own names and their real
        `measures=` declarations. Writing the rows straight to the ledger is
        refused - correctly, by wall 5 - and a fixture that went round the wall
        would be a thread no tool could have produced.
        """
        thread_id = self.thread("here is my dataset, what should I do")
        for tool in ("measure_eval_set", "measure_baseline"):
            spec = REGISTRY.get(tool)
            instrument = evidence.instrument_for(
                tool=tool,
                measures=spec.measures,
                # WALL 9. The registry injects a tool's own capabilities into
                # the licence it issues, so a fixture that hand-builds one has
                # to do the same or it is building a licence the product would
                # never hand out.
                provides=spec.provides,
                actor=evidence.HARNESS,
                thread_id=thread_id,
            )
            for fact, value in (
                ("eval_size_n", 31),
                ("baseline_measured", True),
                ("baseline_score", 0.0),
                ("trivial_baseline_score", 0.35),
            ):
                if fact in spec.measures:
                    instrument.measured(fact, value, how="a stand-in, in a test")
        return thread_id

    def test_the_hardware_tool_is_offered_and_runs_mid_data_thread(self):
        self.connect()
        thread_id = self.data_conversation()
        events.add_message(thread_id, "user", "what GPU does this machine have?")
        model = self.install(
            ScriptedModel(
                [
                    [
                        Delta(
                            kind="tool_call",
                            tool_calls=(ToolCall("c1", "inspect_hardware", {}),),
                        )
                    ],
                    [Delta(kind="text", text="You have this card.")],
                ]
            )
        )
        list(conductor.run_turn(thread_id))

        # 1. It was offered, on a turn whose diagnosis is about data.
        self.assertIn("inspect_hardware", self.offered(model))
        # 2. And the data work is on the same turn, which is the moat: the
        #    machine and the data at once rather than two tabs.
        self.assertIn("measure_eval_set", self.offered(model))
        # 3. It ran, and it answered.
        results = [
            row for row in self.rows(thread_id) if row["kind"] == "tool.result"
        ]
        self.assertEqual([row["payload"]["name"] for row in results], ["inspect_hardware"])
        self.assertTrue(results[0]["payload"]["ok"], results[0]["payload"])
        self.assertNotEqual(
            results[0]["payload"]["result"].get("error"), "not_loaded"
        )

    def test_the_set_was_genuinely_scoped_on_that_same_turn(self):
        """NON-VACUOUS. The test above proves nothing if the turn quietly
        offered all forty, so this asserts the same turn was narrow."""
        self.connect()
        thread_id = self.data_conversation()
        events.add_message(thread_id, "user", "what GPU does this machine have?")
        model = self.install(
            ScriptedModel([[Delta(kind="text", text="Here.")]])
        )
        list(conductor.run_turn(thread_id))
        offered = self.offered(model)
        self.assertLess(len(offered), len(REGISTRY.names()))
        self.assertNotIn("start_training", offered)

    def test_a_pack_stays_for_as_long_as_this_thread_has_evidence_from_it(self):
        """`docs/CAPABILITY_BLOCKS.md` §7: packs accumulate by EVIDENCE, not by
        history. A model that measured a number and can no longer talk about it
        is worse than one that never measured it - so the pack that stamped a
        fact on this thread's sheet stays while the fact does, and a pack that
        loaded and never measured anything falls away with nothing to clean up.

        THE PACK IS `retrieval` AND NOT `data` ON PURPOSE. `data` is declared by
        the ML ledger for its entry stage, so a factless payload loads it either
        way and the negative below could never have failed. `retrieval` is
        declared only for `stage_3_knowledge`, which a walk over no facts never
        reaches, so both halves here are the evidence source and nothing else.
        """
        spec = diagnosis.default_spec()
        self.assertNotIn(
            "retrieval",
            blocks.declared(spec).needs[spec.roles.entry_stage],
            "the entry stage declares retrieval, so the negative below is vacuous",
        )
        rows = [{"fact": "retriever_recall_at_k", "tool": "measure_retriever_recall"}]
        active = blocks.active(
            _payload({}), thread_id=None, spec=spec, evidence_rows=rows
        )
        self.assertIn("retrieval", active.packs)
        self.assertIn("measure_retriever_recall", active.because["retrieval"])

        without = blocks.active(
            _payload({}), thread_id=None, spec=spec, evidence_rows=[]
        )
        self.assertNotIn("retrieval", without.packs)


# ---------------------------------------------------------------------------
# A tool that is real and not loaded.


class ANotLoadedToolIsRefusedWithTheDoorTest(TurnTest):
    """XACML's rule, which five of the eight systems surveyed agree on: a miss
    is a DECLARED OUTCOME, not an accident. And the refusal names what works."""

    def call(self, name: str):
        self.connect()
        thread_id = self.thread("just train it")
        model = self.install(
            ScriptedModel(
                [
                    [Delta(kind="tool_call", tool_calls=(ToolCall("c1", name, {}),))],
                    [Delta(kind="text", text="I could not.")],
                ]
            )
        )
        list(conductor.run_turn(thread_id))
        results = [
            row["payload"]
            for row in self.rows(thread_id)
            if row["kind"] == "tool.result"
        ]
        return results[0], model

    def test_a_registered_tool_outside_the_loaded_packs_does_not_run(self):
        payload, model = self.call("fit_a_tree_model")
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["result"]["error"], "not_loaded")
        self.assertNotIn("fit_a_tree_model", self.offered(model))

    def test_the_refusal_names_the_engine_and_the_button(self):
        payload, _ = self.call("fit_a_tree_model")
        text = payload["result"]["detail"] + payload["result"]["help"]
        self.assertIn("tabular", text)
        self.assertIn("run_diagnosis", text)
        self.assertIn("propose_build", text)
        self.assertIn("button", text)

    def test_an_invented_name_is_still_no_such_tool(self):
        """`there is no such tool` and `that tool is not loaded` are different
        answers and collapsing them would be the wall-with-no-door again."""
        payload, _ = self.call("get_hardware_info")
        self.assertEqual(payload["result"]["error"], "no_such_tool")

    def test_the_person_can_still_run_it_from_the_control_route(self):
        """THE DIFFERENCE BETWEEN SCOPING AND HIDING, at the layer it is made.

        The model was refused on the same tool the user runs here. `controls()`
        is not scoped, `app/main.py` serves all of them, and `Registry.call`
        knows nothing about which schemas a turn sent - so the person's door is
        untouched by anything blocks do.
        """
        from app.main import app

        self.connect()
        client = support.api_client(app)
        listed = client.get("/api/tools").json()
        names = {row["name"] for row in listed["controls"]}
        self.assertEqual(names, set(REGISTRY.names()))
        self.assertIn("fit_a_tree_model", names)


# ---------------------------------------------------------------------------
# The label.


def _fresh_thread_packs():
    """What a thread with no facts loads, read off the ledger rather than typed.

    The core, plus whatever this ledger declares its ENTRY STAGE needs - a walk
    with nothing to walk over cannot leave the stage it starts in, so that is
    the whole of it. Derived from `contract.roles.entry_stage` and
    `contract.capabilities.needs`, which are two different blocks of the same
    document and neither of them is `blocks.active`, so this cannot pass by
    agreeing with the code it is checking.
    """
    spec = diagnosis.default_spec()
    entry = spec.roles.entry_stage
    packs = set(blocks.CORE) | set(blocks.declared(spec).needs[entry])
    # AND THE INSTRUMENTS, WHEN THE ENTRY STAGE CANNOT BE LEFT BY MEASURING.
    # 2026-09-13. This is the same correction
    # `test_an_empty_ledger_gets_the_core_and_what_its_first_stage_declares`
    # already made one pack earlier, one stage further out: a thread stopped
    # where no instrument can move it must still be able to measure the things
    # the gates ahead read, because nothing it could run would clear the stop.
    # Derived here from the ledger's compiled gate index and the registry's own
    # `measures=` declarations - two sources, neither of them `blocks.active` -
    # so this still cannot pass by agreeing with the code it is checking.
    frontier = blocks.rests_on(_payload({}), spec)
    unmeasurable = [
        fact
        for fact in frontier
        if not [one for one in iter(REGISTRY) if fact in one.measures]
    ]
    if unmeasurable:
        for row in spec.gate_row_facts.values():
            for fact in row:
                for one in iter(REGISTRY):
                    if fact in one.measures:
                        packs.update(blocks.pack_of_tool(one.name))
    return sorted(packs)


class TheActiveBlockIsVisibleTest(TurnTest):
    """A label the person can see, never a menu they choose from."""

    def test_the_turn_records_which_blocks_it_ran_under(self):
        """LAW SUBSTITUTED 2026-09-18. `blocks.tools` WAS the set of schemas on
        the wire, and it is now the set of ACTIVE tools, of which only the named
        ones spend a schema - `app/tools/blocks.py:on_the_wire`.

        The old assertion was `blocks.tools == offered`, and it is not weakened
        into "offered is a subset": that would go green on a turn that carried
        nothing. The equality moves to the record that now holds it,
        `schemas_on_wire.tools`, and the relationship between the two records is
        asserted beside it - `considered` is the pool the cut chose from, and
        every tool of `blocks.tools` this mode allows is in it.

        THE REASON IT MOVED, MEASURED 2026-09-18 over `REGISTRY.model_tools`
        with `app/providers/budget.py`: all 88 schemas cost 26,992 tokens, the
        narrowest pack selection this engine produces is 27 of them, and THE
        TURN THIS VERY TEST TAKES - a fresh thread on the shipped ledger -
        selected 48 tools and 13,514 tokens of schema against the 65k window the
        owner's card runs. It now sends nine.

        THE PACK RANGE THIS FILE PINS DID NOT MOVE BY ONE, which is the half
        that had to be checked rather than assumed: `(27, 63)` is a claim about
        `blocks.active`, the cut happens after it, and the sweep below re-derives
        the pair. What moved is how many of a selected pack's tools arrive with
        their parameters.
        """
        self.connect()
        thread_id = self.thread("hello")
        model = self.install(ScriptedModel([[Delta(kind="text", text="Hi.")]]))
        list(conductor.run_turn(thread_id))
        started = [
            row["payload"]
            for row in self.rows(thread_id)
            if row["kind"] == "turn.started"
        ][0]
        self.assertEqual(started["blocks"]["packs"], _fresh_thread_packs())
        self.assertEqual(
            set(started["blocks"]["because"]), set(started["blocks"]["packs"])
        )

        wire = started["schemas_on_wire"]
        self.assertEqual(set(wire["tools"]), set(self.offered(model)))
        self.assertEqual(set(wire["because"]), set(wire["tools"]))
        self.assertFalse(wire["all_schemas"], "this turn ran with the switch off")
        # AND THE TWO RECORDS AGREE ABOUT WHICH IS WHICH. Non-vacuous in both
        # directions: the cut chose from what the packs offered, and it really
        # did cut.
        self.assertLessEqual(set(wire["considered"]), set(started["blocks"]["tools"]))
        self.assertLess(
            len(wire["tools"]),
            len(wire["considered"]),
            "nothing was withheld, so the record cannot be about a cut",
        )

    def test_the_first_turn_says_what_it_added_and_why(self):
        self.connect()
        thread_id = self.thread("hello")
        self.install(ScriptedModel([[Delta(kind="text", text="Hi.")]]))
        list(conductor.run_turn(thread_id))
        moved = [
            row["payload"]
            for row in self.rows(thread_id)
            if row["kind"] == "blocks.changed"
        ]
        self.assertEqual(len(moved), 1)
        self.assertEqual(moved[0]["added"], _fresh_thread_packs())
        self.assertEqual(moved[0]["removed"], [])
        for pack in _fresh_thread_packs():
            self.assertIn(pack, moved[0]["because"])
        self.assertIn("button", moved[0]["controls_are_not_scoped"])

    def test_a_turn_that_moves_nothing_says_nothing(self):
        """When and only when the set changes. A label repeated every turn is
        not a label, it is noise with a provenance field."""
        self.connect()
        thread_id = self.thread("hello")
        self.install(
            ScriptedModel(
                [[Delta(kind="text", text="Hi.")], [Delta(kind="text", text="Hi.")]]
            )
        )
        list(conductor.run_turn(thread_id))
        events.add_message(thread_id, "user", "still hello")
        list(conductor.run_turn(thread_id))
        self.assertEqual(self.kinds(thread_id).count("blocks.changed"), 1)

    def test_a_pack_arriving_mid_thread_is_announced(self):
        """The event fires on the turn the work changes, with the reason.

        THE PACK HAD TO CHANGE AND THE NEW ONE IS THE STRONGER CASE. This used
        `measure_eval_set` and the `data` pack, and once the ML ledger declared
        `stage_0_admissibility: [data]` that pack was already on from turn one -
        so the second event never fired and the test was measuring the
        declaration rather than the evidence. `retrieval` is declared for
        `stage_3_knowledge` and for no stage a factless thread can stop in, so
        this is now the source-4 claim ON ITS OWN: a tool measured something
        here, and the pack that tool is in stays for as long as the row does.
        """
        stage = diagnosis.default_spec().roles.entry_stage
        self.assertNotIn(
            "retrieval",
            blocks.declared(diagnosis.default_spec()).needs[stage],
            "the entry stage declares retrieval, so this proves nothing",
        )
        self.connect()
        thread_id = self.thread("hello")
        self.install(
            ScriptedModel(
                [[Delta(kind="text", text="Hi.")], [Delta(kind="text", text="Hi.")]]
            )
        )
        list(conductor.run_turn(thread_id))
        evidence.instrument_for(
            tool="measure_retriever_recall",
            measures=REGISTRY.get("measure_retriever_recall").measures,
            provides=REGISTRY.get("measure_retriever_recall").provides,
            actor=evidence.HARNESS,
            thread_id=thread_id,
        ).measured("retriever_recall_at_k", 0.4, how="a stand-in, in a test")
        events.add_message(thread_id, "user", "now what")
        list(conductor.run_turn(thread_id))

        moved = [
            row["payload"]
            for row in self.rows(thread_id)
            if row["kind"] == "blocks.changed"
        ]
        self.assertEqual(len(moved), 2)
        self.assertIn("retrieval", moved[1]["added"])
        self.assertIn("measure_retriever_recall", moved[1]["because"]["retrieval"])

    def test_the_surface_draws_the_event_the_conductor_writes(self):
        """THE LABEL REACHES A PERSON, and the two halves are read off the files.

        `docs/PHASES.md`'s done-condition is that the active block is visible in
        the interface. An event nothing renders is a record, not a label, so
        this asserts the transcript builder handles the kind and reads the keys
        this conductor actually emits - the same way
        `tests/test_the_question_reaches_the_surface.py` holds its card to its
        payload. It also asserts what must NOT be there: no control, no choice.
        """
        source = (
            diagnosis.SPEC_PATH.parents[1]
            / "frontend"
            / "src"
            / "lib"
            / "transcript.ts"
        ).read_text(encoding="utf-8")
        self.assertIn("case 'blocks.changed':", source)
        for key in ("added", "removed", "active", "because"):
            self.assertIn(key, source, key)

        self.connect()
        thread_id = self.thread("hello")
        self.install(ScriptedModel([[Delta(kind="text", text="Hi.")]]))
        list(conductor.run_turn(thread_id))
        payload = [
            row["payload"]
            for row in self.rows(thread_id)
            if row["kind"] == "blocks.changed"
        ][0]
        for key in ("added", "removed", "active", "because"):
            self.assertIn(key, payload, key)

    def test_the_prompt_still_names_every_tool_and_marks_the_loaded_ones(self):
        """BLOCKS SCOPE WHAT THE MODEL MAY CALL. THEY DO NOT SCOPE WHAT THE
        HARNESS IS.

        A model told about twelve tools tells the user this product has twelve,
        and that was a live, user-facing defect: asked whether it could build
        anything, a connected model said the person would still have to do the
        training themselves, while `start_training` sat in the registry. So the
        capability list stays complete and the scope is STATED rather than
        applied.
        """
        self.connect()
        thread_id = self.thread("hello")
        model = self.install(ScriptedModel([[Delta(kind="text", text="Hi.")]]))
        list(conductor.run_turn(thread_id))
        prompt = model.sent[0]["messages"][0]["content"]

        for name in capabilities.tool_names():
            self.assertIn(f"`{name}`", prompt, name)
        self.assertIn("`start_training`", prompt)
        self.assertNotIn("start_training", self.offered(model))
        self.assertIn("are loaded for this turn", prompt)
        self.assertIn("`inspect_hardware` (*)", prompt)
        self.assertNotIn("`start_training` (*)", prompt)

    def test_nothing_is_marked_when_no_schema_travels_with_the_turn(self):
        """A mark that says "its schema is here" over a request carrying none.

        When the connected model cannot call tools the conductor sends no
        schemas at all and the long capability list is the model's only account
        of them. Marking twelve of forty there would say twelve are nearer to
        hand when none of them is.
        """
        from app import instructions

        core = blocks.tools_in(blocks.CORE)
        for state in (False, None):
            with self.subTest(tool_calling=state):
                prompt = instructions.assemble(tool_calling=state, loaded=core)
                self.assertNotIn("(*)", prompt)
                self.assertNotIn("are loaded for this turn", prompt)
                for name in capabilities.tool_names():
                    self.assertIn(f"`{name}`", prompt, name)


# ---------------------------------------------------------------------------
# Who chooses.


class NoToolCanWidenTheSetTest(unittest.TestCase):
    """`registry.py`'s hard rule, one clause further on."""

    def test_no_registered_tool_provides_a_capability_over_the_blocks(self):
        """There is no `blocks.request` tool and there is not meant to be one.
        Tool search wearing a different hat: the set would stop being a function
        of the diagnosis and become a function of what the model wanted."""
        self.assertNotIn("blocks", blocks.packs())
        for spec in REGISTRY:
            for name in spec.provides:
                self.assertFalse(name.startswith("blocks."), spec.name)

    def test_the_selection_reads_nothing_a_model_can_write(self):
        """Every input to `active()` is a constant, a diagnosis the model's
        arguments cannot reach, or an evidence row only an instrument writes.

        Driven rather than asserted: the same walk, with a payload carrying a
        model's invented `alternatives` row naming a training tool. The pack
        does not arrive, because `alternatives` is written by the engine from
        the ledger's own words and a row that names a tool nothing registered
        cannot name a pack either.
        """
        spec = diagnosis.default_spec()
        honest = blocks.active(_payload({}), thread_id=None, spec=spec)
        forged = dict(_payload({}))
        forged["alternatives"] = [
            {"move": "x", "tool": "start_training_please", "fact": None}
        ]
        self.assertEqual(
            blocks.active(forged, thread_id=None, spec=spec).packs, honest.packs
        )

    def test_the_registry_control_face_takes_no_scope(self):
        """`model_tools` narrows; `controls` has no such parameter and must not
        grow one. Asserted on the signature rather than on today's behaviour."""
        import inspect

        self.assertEqual(
            list(inspect.signature(REGISTRY.controls).parameters), []
        )
        self.assertIn("only", inspect.signature(REGISTRY.model_tools).parameters)


# ---------------------------------------------------------------------------
# The second ledger.


class TheSecondLedgerGetsItsOwnAnswerTest(unittest.TestCase):
    """Blocks are domain-general, and the honest finding is the interesting one.

    Nothing in `app/tools/blocks.py` knows what machine learning is. Handed the
    AI-engineering ledger it selects the core and nothing else - and that is not
    a defect in the selection, it is the selection REPORTING a debt
    `docs/PHASES.md` already carries: no tool in this harness measures a single
    one of that ledger's sixteen facts, so there is no pack for its work to
    select. When the four instruments Phase 1 names exist, they will declare
    `provides=` and the packs will follow with nothing here to change.
    """

    @classmethod
    def setUpClass(cls):
        cls.spec = diagnosis.load_spec(LEDGER)

    def test_the_two_ledgers_share_no_fact_and_so_share_one_pack_beside_the_core(self):
        ml = diagnosis.default_spec()
        self.assertEqual(set(ml.facts) & set(self.spec.facts), set())
        active = blocks.active(_payload({}, self.spec), thread_id=None, spec=self.spec)
        # RETIRED AND REWRITTEN 2026-08-25: this asserted CORE ONLY. The empty
        # AI sheet now also carries the `agent` pack, and that is the design
        # working rather than scope leaking: stage_0's declared need is
        # `[agent]`, and the next move off BLOCKED__NOTHING_TO_MEASURE_AGAINST
        # is "write down ten real failures", whose instrument -
        # `run_the_failures` - lives there. The packs stay disjoint from every
        # ML-only pack; what changed is that the second ledger finally owns
        # instruments of its own instead of borrowing none and measuring
        # nothing.
        self.assertEqual(
            active.packs | frozenset(blocks.CORE),
            frozenset(blocks.CORE) | {"agent"},
            f"the empty AI sheet selects {sorted(active.packs)}; core+agent is "
            "the expected vocabulary for a ledger whose instruments just shipped",
        )

    def test_every_ai_inspect_fact_is_measured_now(self):
        """RETIRED AND INVERTED TWICE 2026-08-25. Was: NO tool measures an AI fact.

        True on 2026-08-24; false when Phase 1's four instruments shipped; and
        the last holdout, `cost_per_run_usd`, left the ledger entirely the same
        day - G4 was denominated in `tokens_per_run`, which an instrument can
        read, rather than keeping a fact nothing could honestly measure. The
        invariants that survive: the measured intersection is exactly the
        inspect facts plus the derive facts an instrument computes, never an
        `ask` fact, and the declared gap is EMPTY. A ninth fact arriving
        unmeasured, or a user-history fact growing an instrument, is red here."""
        gap = set(self.spec.raw["known_gaps"]["no_instrument_measures"])
        inspect_facts = {
            name for name, decl in self.spec.facts.items() if decl["source"] == "inspect"
        }
        derive_facts = {
            name for name, decl in self.spec.facts.items() if decl["source"] == "derive"
        }
        measured = {fact for spec in REGISTRY for fact in spec.measures}
        got = measured & set(self.spec.facts)
        # `derive` facts are computable over data the harness can read, and
        # run_the_failures computes `failure_buckets`; an instrument measuring
        # one is the design, not an escape hatch. What may NEVER be measured
        # is an `ask` fact - the user's own week.
        allowed = (inspect_facts - gap) | derive_facts
        self.assertEqual(
            got - allowed,
            set(),
            f"tools claim to measure facts outside this ledger's inspect/derive lists: {sorted(got - allowed)}",
        )
        self.assertEqual(
            (inspect_facts - gap) - got,
            set(),
            f"inspect facts with an instrument are not all declared measured: {sorted((inspect_facts - gap) - got)}",
        )
        ask_facts = {
            name for name, decl in self.spec.facts.items() if decl["source"] == "ask"
        }
        self.assertEqual(
            got & ask_facts,
            set(),
            "an instrument claims a fact only the user can answer",
        )
        self.assertEqual(gap, set())

    def test_the_brief_for_the_second_ledger_is_smaller_too(self):
        payload = _payload({}, self.spec)
        active = blocks.active(payload, thread_id=None, spec=self.spec)
        self.assertLess(
            len(conductor.standing_brief(payload, None, active)),
            len(conductor.standing_brief(payload, None, None)),
        )


if __name__ == "__main__":
    unittest.main()
