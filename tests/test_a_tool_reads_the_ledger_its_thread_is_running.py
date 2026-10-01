"""PHASE 1a. The engine was domain-general and the TOOL LAYER was not.

`docs/PHASES.md` records the Phase 0 finding that made this file necessary, and
it is worth quoting because every test below is one sentence of it:

    "26 `default_spec()` call sites across 11 modules resolve to SPEC_PATH - the
     ML ledger - unconditionally, and index it by 12 hardcoded ML ids. A second
     ledger will diagnose correctly and then hand its verdict to a tool layer
     still reading the first ledger's file."

`docs/CAPABILITY_BLOCKS.md` Â§1.4 re-measured it and found the count an
undercount: seventeen more sites reach the same file through three functions in
`app/tools/evidence.py`, so the real figure is 33 sites in 15 modules, and Â§1.5
found the sharper half - `load_spec()` is called from ONE place in `app/`, on a
module constant, so **no route through the running product reached the second
ledger at all**.

What this file asserts, in the order the problem was found:

  * a conversation NAMES its ledger, in a column, defaulting to the one every
    existing thread has in fact been running;
  * a tool asked to work in that conversation is HANDED it, through a declared
    injection channel no schema may fill;
  * a gate is found by the FACT its condition reads, never by an id typed into
    a tool - and the fact-derived lookup survives a gate being renamed, which
    the hardcoded one does not;
  * where an instrument genuinely does not exist in a domain, the refusal SAYS
    SO AND NAMES THE DOMAIN. Silence is the failure this whole pass is about,
    and `evidence.resolves` was giving a true sentence for a false reason;
  * and the machine-learning path does not move. `TheMlPathDoesNotMoveTest` is
    the small in-suite half of that; the byte-for-byte half is a capture of all
    72 fixtures through `run_diagnosis` and `propose_build`, run before and
    after, and it is recorded in the lane's report rather than here because it
    takes 17 seconds and this suite has 2,967 tests in it.

EVERY TEST HERE WAS BROKEN BEFORE IT WAS BELIEVED. A test that passes against
the defect is worth nothing, and this repository has written that down more than
once; where a check could plausibly be vacuous the test says in a comment what
was broken to make it fail.
"""

from __future__ import annotations

import ast
import inspect
import tempfile
import unittest
from pathlib import Path

#: Shared with the Phase-B journey test - the only files shaped like what the
#: instruments accept, and therefore what an agent build is planned against.
AGENT_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "agent"

import yaml

from app import db, diagnosis, events
from app.tools import evidence
from app.tools.registry import (
    INJECTED_ARGUMENTS,
    RESERVED_ARGUMENTS,
    REGISTRY,
    Registry,
    ToolError,
    ToolSpec,
    Control,
)

import support

AI_LEDGER = "docs/ledgers/ai_engineering.yaml"
ML_LEDGER = "docs/diagnosis_engine.yaml"

#: A fact only the AI-engineering ledger declares, and only the ML one. Both are
#: asserted to be exactly that in `TheTwoLedgersShareNoFactsTest`, so a rename
#: in either file turns this module red rather than quietly making it vacuous.
AN_AI_FACT = "has_traces"
AN_ML_FACT = "eval_size_n"


class TheTwoLedgersShareNoFactsTest(unittest.TestCase):
    """The premise every other test here rests on, checked rather than assumed."""

    def test_the_two_shipped_ledgers_declare_no_fact_in_common(self):
        ml = diagnosis.spec_at(ML_LEDGER)
        ai = diagnosis.spec_at(AI_LEDGER)
        self.assertEqual(
            set(ml.facts) & set(ai.facts),
            set(),
            "The two ledgers used to share zero fact names, which is what makes "
            "'read the wrong file' a visible failure rather than a subtle one. "
            "If they now overlap, every refusal in this module needs re-reading.",
        )

    def test_the_two_facts_this_module_uses_belong_to_one_ledger_each(self):
        ml = diagnosis.spec_at(ML_LEDGER)
        ai = diagnosis.spec_at(AI_LEDGER)
        self.assertIn(AN_AI_FACT, ai.facts)
        self.assertNotIn(AN_AI_FACT, ml.facts)
        self.assertIn(AN_ML_FACT, ml.facts)
        self.assertNotIn(AN_ML_FACT, ai.facts)


class AThreadNamesItsLedgerTest(unittest.TestCase):
    """Migration v011: the column, its default, and what it does to old rows."""

    def setUp(self):
        support.sandbox(self)

    def test_the_column_exists_and_defaults_to_the_ledger_everything_has_been_running(self):
        with db.session() as connection:
            columns = {
                row["name"]: row for row in connection.execute("PRAGMA table_info(threads)")
            }
        self.assertIn("ledger", columns)
        self.assertEqual(columns["ledger"]["notnull"], 1)
        self.assertEqual(columns["ledger"]["dflt_value"], f"'{ML_LEDGER}'")

    def test_the_migrations_frozen_default_still_agrees_with_the_live_constant(self):
        # v006's docstring makes the argument: a migration must mean the same
        # thing forever, so it freezes its constant rather than reading the live
        # one - and then a test asserts the two agreed on the day of shipping,
        # so a divergence is a red suite rather than a silent drift.
        from app.migrations import v011_a_thread_names_its_ledger as v011

        self.assertEqual(
            v011._THE_LEDGER_EVERY_EXISTING_THREAD_IS_RUNNING,
            diagnosis.DEFAULT_LEDGER,
        )

    def test_a_thread_created_the_ordinary_way_runs_the_first_ledger(self):
        thread = events.create_thread("an ordinary conversation")
        self.assertEqual(thread["ledger"], ML_LEDGER)
        self.assertEqual(
            evidence.ledger_for_thread(thread["id"]).as_written, ML_LEDGER
        )

    def test_a_thread_can_name_the_second_ledger_and_is_handed_it(self):
        thread = events.create_thread("an agent problem", ledger=AI_LEDGER)
        self.assertEqual(thread["ledger"], AI_LEDGER)
        self.assertEqual(
            evidence.ledger_for_thread(thread["id"]).as_written, AI_LEDGER
        )

    def test_a_ledger_that_does_not_load_is_refused_at_the_thread_not_at_a_tool(self):
        # SAFE AND BROKEN IS NOT THE SAME AS SAFE AND WORKING. The alternative -
        # store it, fall back to the first ledger later - is the exact silent
        # wrong read this whole pass removes, arriving several turns after the
        # mistake and unable to say what was wrong.
        with self.assertRaises(OSError):
            events.create_thread("nonsense", ledger="docs/ledgers/no_such_file.yaml")
        self.assertEqual(events.list_threads(), [])


class TheInjectionChannelTest(unittest.TestCase):
    """`ledger` reaches a handler the way `instrument` does, and no other way."""

    def test_the_ledger_is_an_injected_argument_and_a_reserved_one(self):
        self.assertIn("ledger", INJECTED_ARGUMENTS)
        self.assertIn("ledger", RESERVED_ARGUMENTS)

    def test_no_registered_tool_offers_a_ledger_slot_in_its_schema(self):
        # Wall 4's shape: which knowledge a thread is judged against is a
        # property of the conversation, and a model that could name its own
        # ledger could pick the domain whose gates it finds easiest.
        for spec in REGISTRY:
            self.assertNotIn(
                "ledger",
                (spec.schema.get("properties") or {}),
                f"{spec.name} offers a `ledger` argument",
            )

    def test_a_schema_declaring_a_ledger_argument_does_not_register(self):
        private = Registry()
        with self.assertRaises(ToolError) as caught:
            private.add(
                ToolSpec(
                    name="picks_its_own_knowledge",
                    description="x",
                    schema={
                        "type": "object",
                        "properties": {"ledger": {"type": "string"}},
                    },
                    reads=(),
                    writes=(),
                    approval="never",
                    control=Control(label="x", group="Look", verb="x"),
                    handler=lambda ledger="": None,
                )
            )
        self.assertIn("ledger", str(caught.exception))

    def test_wants_ledger_is_read_off_the_signature_and_not_declared_twice(self):
        def asks(*, ledger):  # noqa: ANN001
            return ledger

        def does_not_ask():
            return None

        make = lambda handler: ToolSpec(  # noqa: E731
            name="probe",
            description="x",
            schema={"type": "object", "properties": {}},
            reads=(),
            writes=(),
            approval="never",
            control=Control(label="x", group="Look", verb="x"),
            handler=handler,
        )
        self.assertTrue(make(asks).wants_ledger)
        self.assertFalse(make(does_not_ask).wants_ledger)

    def test_the_handler_is_handed_the_thread_s_own_ledger(self):
        support.sandbox(self)
        seen = {}

        private = Registry()

        @private.tool(
            "remember_the_ledger",
            description="x",
            provides=("ledger.diagnosis.run",),
            label="x",
            group="Look",
            verb="x",
        )
        def remember(*, ledger):  # noqa: ANN001
            seen["as_written"] = ledger.as_written
            return {"ok": True}

        ml = events.create_thread("ml")["id"]
        ai = events.create_thread("ai", ledger=AI_LEDGER)["id"]
        private.call("remember_the_ledger", {}, thread_id=ml)
        self.assertEqual(seen["as_written"], ML_LEDGER)
        private.call("remember_the_ledger", {}, thread_id=ai)
        self.assertEqual(seen["as_written"], AI_LEDGER)


class AToolWorksInTheDomainItsThreadIsInTest(unittest.TestCase):
    """The headline: the same registry, two threads, two ledgers, one process."""

    def setUp(self):
        support.sandbox(self)
        self.ml = events.create_thread("a machine learning problem")["id"]
        self.ai = events.create_thread("an agent problem", ledger=AI_LEDGER)["id"]

    def test_run_diagnosis_walks_the_ledger_the_thread_named(self):
        # BROKEN BEFORE BELIEVED: with `diagnosis.diagnose(sheet)` restored to
        # its no-argument form, the AI thread answers BLOCKED__DEFINE_SUCCESS_
        # FIRST - the ML ledger's empty-sheet outcome - and this fails.
        ml = REGISTRY.call("run_diagnosis", {"facts": {}}, actor="user", thread_id=self.ml)
        ai = REGISTRY.call("run_diagnosis", {"facts": {}}, actor="user", thread_id=self.ai)
        self.assertEqual(ml["outcome"], "BLOCKED__DEFINE_SUCCESS_FIRST")
        self.assertEqual(ai["outcome"], "BLOCKED__NOTHING_TO_MEASURE_AGAINST")
        self.assertNotEqual(ml["outcome"], ai["outcome"])

    def test_state_facts_accepts_this_domain_s_fact_and_refuses_the_other_s(self):
        mine = REGISTRY.call(
            "state_facts", {"facts": {AN_AI_FACT: True}}, actor="user", thread_id=self.ai
        )
        self.assertTrue(mine["ok"], mine)

        theirs = REGISTRY.call(
            "state_facts", {"facts": {AN_AI_FACT: True}}, actor="user", thread_id=self.ml
        )
        self.assertFalse(theirs["ok"])
        self.assertEqual(theirs["error"], "rejected_fact")
        # AND THE REFUSAL NAMES THE LEDGER IT ACTUALLY READ. A message quoting a
        # file the caller was never asking about sends them to the wrong
        # document to find out what is legal.
        self.assertEqual(theirs["the_ledger"]["file"], ML_LEDGER)

    def test_the_same_ml_fact_is_refused_on_the_agent_thread(self):
        refused = REGISTRY.call(
            "state_facts", {"facts": {AN_ML_FACT: 100}}, actor="user", thread_id=self.ai
        )
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["the_ledger"]["file"], AI_LEDGER)


class TheHonestNextStepTellsFourStatesApartTest(unittest.TestCase):
    """`evidence.resolves` had one sentence for two different situations.

    Â§1.3 of `docs/CAPABILITY_BLOCKS.md` is the sharpest finding in the research
    and it is about this function: *"its sentence is TRUE and its reason is
    WRONG"*. "No tool in this harness measures this yet" is a real product gap
    when the fact belongs to the ledger being consulted, and it was being said
    about a fact from a different ledger entirely.
    """

    def test_a_fact_of_this_ledger_with_an_instrument_names_the_instrument(self):
        answer = evidence.resolves(AN_ML_FACT)
        self.assertEqual(answer["tool"], "measure_eval_set")

    def test_every_inspect_fact_of_this_ledger_names_its_instrument(self):
        """RETIRED AND INVERTED 2026-08-25. Was: ONE fact, still a product gap.

        `cost_per_run_usd` was the honest anchor for this test until the gate
        was denominated in what an instrument can read - G4 asks
        `tokens_per_run` now, which bound_the_loop measures - so this ledger
        has NO unmeasured inspect fact left, and the property worth holding
        flipped polarity: every inspect fact resolves to the tool that settles
        a challenge on it. A gap sentence here is red rather than documented.
        """
        ai = diagnosis.spec_at(AI_LEDGER)
        inspect_facts = sorted(
            name for name, decl in ai.facts.items() if decl["source"] == "inspect"
        )
        self.assertTrue(inspect_facts)
        for name in inspect_facts:
            with self.subTest(fact=name):
                answer = evidence.resolves(name, ai)
                self.assertIsNotNone(
                    answer["tool"],
                    f"{name} is declared inspect and no instrument settles it",
                )

    def test_a_fact_of_another_ledger_is_not_reported_as_a_gap_in_the_product(self):
        answer = evidence.resolves(AN_AI_FACT)  # the AI fact, on the ML ledger
        self.assertIsNone(answer["tool"])
        self.assertNotIn("No tool in this harness measures this yet", answer["note"])
        self.assertIn("is not a fact of", answer["note"])
        self.assertEqual(answer["declared_in"], [AI_LEDGER])

    def test_a_name_no_ledger_declares_says_that_instead(self):
        answer = evidence.resolves("not_a_fact_in_any_ledger")
        self.assertIsNone(answer["tool"])
        self.assertIn("No ledger in this product declares it", answer["note"])
        self.assertEqual(answer["declared_in"], [])


class RegistrationAsksEveryLedgerAndCallingAsksOneTest(unittest.TestCase):
    """The two questions that used to be one, and the wall each of them is.

    Â§1.3: a plausible trace reader declaring `measures=("has_traces",)` could not
    be registered at all, and *"the check is right at every step and the ledger
    it consults is wrong at every step"*. Phase 1 lists four such tools. So
    registration asks the union of the ledgers this product ships; what may be
    STAMPED is asked per call, against the ledger that thread is running.
    """

    def _probe(self, registry, measures, provides=("agent.traces.read",)):
        # THE CAPABILITY IS THE PROBE'S TOO, since wall 9. `has_traces` is
        # bound in the AI ledger to `agent.traces.read`, which is what the tool
        # this probe stands in for actually provides; the two refusal cases
        # below never reach that check, because a fact no ledger declares and
        # a `source: ask` fact are both refused before it.
        @registry.tool(
            "read_agent_traces",
            description="x",
            provides=provides,
            measures=measures,
            label="x",
            group="Look",
            verb="x",
        )
        def handler(*, instrument):  # noqa: ANN001
            return {"ok": True}

        return handler

    def test_a_second_ledgers_fact_may_now_be_declared(self):
        self._probe(Registry(), (AN_AI_FACT,))  # registers, or this raises

    def test_a_fact_no_ledger_declares_is_still_refused_at_import(self):
        with self.assertRaises(ToolError) as caught:
            self._probe(Registry(), ("not_a_fact_in_any_ledger",))
        self.assertIn("not a declared fact", str(caught.exception))

    def test_an_ask_fact_is_still_refused_in_every_ledger(self):
        # `may_be_declared_measurable` refuses `source: ask` because nothing in
        # this harness watches somebody's week happen. Widening registration to
        # the union of ledgers must not widen THAT.
        with self.assertRaises(ToolError) as caught:
            self._probe(Registry(), ("prompt_iterations",))
        self.assertIn("source: ask", str(caught.exception))

    def test_a_tool_whose_facts_are_foreign_to_this_thread_refuses_and_says_why(self):
        """THE THREAD HAS TO HAVE MEASURED SOMETHING, AS OF 2026-08-28.

        This used to make a bare thread and call across the domain. It now
        profiles a table first, and the difference is the change that made it
        necessary rather than a convenience: a thread that has measured nothing
        has not named its domain, and reaching for a foreign instrument on one
        is now read as the person saying which domain they are in - see
        `events.adopt_ledger` and
        `tests/test_a_person_can_reach_the_domain_they_are_in.py`.

        NOTHING THIS TEST PROTECTED IS DROPPED. The refusal, its error, the
        ledger it names, the fact it names, the other ledger it points at, and
        the tool working where it belongs are all still asserted - in the state
        where the wall is what decides, which is a thread that has invested
        something in a domain.
        """
        root = support.sandbox(self)
        private = Registry()
        self._probe(private, (AN_AI_FACT,))
        ml = events.create_thread("ml")["id"]
        ai = events.create_thread("ai", ledger=AI_LEDGER)["id"]

        # The thread names its domain by using it. One real measurement is
        # enough, and it is what makes the refusal below a statement about the
        # domain rather than about a conversation that has not started.
        table = root / "rows.csv"
        table.write_text(
            "q,a" + "".join(f"{chr(10)}ticket {i},label" for i in range(30)),
            encoding="utf-8",
        )
        profiled = REGISTRY.call(
            "profile_dataset", {"path": str(table)}, actor="user", thread_id=ml
        )
        self.assertTrue(profiled.get("ok"), profiled)

        refused = private.call("read_agent_traces", {}, thread_id=ml)
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "not_in_this_domain")
        self.assertEqual(refused["ledger"], ML_LEDGER)
        self.assertIn(AN_AI_FACT, refused["detail"])
        self.assertIn(AI_LEDGER, refused["detail"])

        # AND IT WORKS WHERE IT BELONGS, which is what makes the refusal a
        # statement about the domain rather than about the tool.
        self.assertTrue(private.call("read_agent_traces", {}, thread_id=ai)["ok"])

    def test_an_instrument_will_not_stamp_a_fact_this_thread_s_ledger_lacks(self):
        support.sandbox(self)
        private = Registry()

        @private.tool(
            "stamp_something_foreign",
            description="x",
            # BOTH CAPABILITIES, because it declares a fact from each ledger and
            # wall 9 asks each ledger separately at registration. What is being
            # tested here is the DOMAIN wall - a fact this thread's ledger has
            # never heard of - so the probe has to get past every earlier wall
            # to reach it, which is what these two names buy.
            provides=("agent.traces.read", "data.eval_set.count"),
            measures=(AN_AI_FACT, AN_ML_FACT),
            label="x",
            group="Look",
            verb="x",
        )
        def handler(*, instrument):  # noqa: ANN001
            try:
                instrument.measured(AN_AI_FACT, True, how="read a trace directory")
                return {"ok": True}
            except evidence.MeasurementError as error:
                return {"ok": False, "detail": str(error)}

        ml = events.create_thread("ml")["id"]
        # The call is NOT refused up front - this tool measures one fact the ML
        # ledger does declare - so the narrower wall is the one that must hold.
        result = private.call("stamp_something_foreign", {}, thread_id=ml)
        self.assertFalse(result["ok"])
        self.assertIn("declares no such fact", result["detail"])
        self.assertIn(AI_LEDGER, result["detail"])
        self.assertEqual(evidence.rows_for(ml), [])


class AGateIsFoundByTheFactItReadsTest(unittest.TestCase):
    """`Spec.gate_reading`, and the rename that proves it is not the old lookup.

    Â§8.2's non-vacuous check, written as the research specified it: *"rename
    `G0_EVAL_SET` in a scratch copy of the ledger and confirm `data.py` still
    finds the floor - and that the old code would not have."*
    """

    def _ledger_with_the_gate_renamed(self) -> diagnosis.Spec:
        raw = yaml.safe_load(diagnosis.SPEC_PATH.read_text(encoding="utf-8"))
        gates = raw["gates"]
        renamed = {}
        for gate_id, gate in gates.items():
            renamed["G0_A_DIFFERENT_NAME" if gate_id == "G0_EVAL_SET" else gate_id] = gate
        raw["gates"] = renamed
        text = yaml.safe_dump(raw, sort_keys=False, allow_unicode=True)
        # EVERY reference, not only the definition: `contract.required_gates`
        # lists it and a stage carries a `gate_ref` to it, and the loader
        # refuses a document where those disagree - which is the loader being
        # right. A rename is a rename of the name.
        text = text.replace("G0_EVAL_SET", "G0_A_DIFFERENT_NAME")
        scratch = Path(tempfile.mkdtemp()) / "renamed.yaml"
        scratch.write_text(text, encoding="utf-8")
        self.addCleanup(scratch.unlink, missing_ok=True)
        return diagnosis.load_spec(scratch)

    def test_the_first_ledgers_floor_is_found_by_the_fact(self):
        reading = diagnosis.default_spec().gate_reading(AN_ML_FACT)
        self.assertIsNotNone(reading)
        self.assertEqual(reading.gate_id, "G0_EVAL_SET")
        self.assertEqual(reading.row_key, "any")

    def test_the_floor_survives_the_gate_being_renamed(self):
        from app.tools import data, propose

        moved = self._ledger_with_the_gate_renamed()
        # The old code was `spec.gates.get("G0_EVAL_SET")`, and this line is what
        # it would have returned on this document - nothing at all.
        self.assertIsNone(moved.gates.get("G0_EVAL_SET"))
        reading = moved.gate_reading(AN_ML_FACT)
        self.assertIsNotNone(reading)
        self.assertEqual(reading.gate_id, "G0_A_DIFFERENT_NAME")
        self.assertEqual(data.eval_set_floor(moved)["rows"], 30)
        self.assertEqual(propose.g0_minimum(moved), 30)

    def test_a_ledger_whose_gates_never_read_the_fact_answers_none(self):
        # NONE IS THE LOAD-BEARING ANSWER. Eclipse's contract for an extension
        # point nobody bound: unbound is empty, and empty is a fact the caller
        # has to state rather than a mapping to proceed over.
        ai = diagnosis.spec_at(AI_LEDGER)
        self.assertIsNone(ai.gate_reading(AN_ML_FACT))

    def test_a_second_ledgers_own_gates_are_found_the_same_way(self):
        ai = diagnosis.spec_at(AI_LEDGER)
        reading = ai.gate_reading("failing_cases_n")
        self.assertIsNotNone(reading)
        self.assertEqual(reading.gate_id, "G0_SOMETHING_TO_MEASURE")

    def test_the_tie_is_broken_by_the_ledgers_own_declared_gate_order(self):
        # `eval_size_n` is read by G0_EVAL_SET/any AND by
        # G2_PROMPT_EXHAUSTED/llm_weights. Which one answers is decided by
        # `contract.required_gates` - the ledger's own order - and not by a
        # position this file assumed.
        spec = diagnosis.default_spec()
        readers = {
            gate for (gate, _row), facts in spec.gate_row_facts.items() if AN_ML_FACT in facts
        }
        self.assertEqual(readers, {"G0_EVAL_SET", "G2_PROMPT_EXHAUSTED"})
        first = next(g for g in spec.required_gates if g in readers)
        self.assertEqual(spec.gate_reading(AN_ML_FACT).gate_id, first)


class WhereAnInstrumentDoesNotExistTheAnswerSaysSoTest(unittest.TestCase):
    """A second domain gets nothing, never the first domain's answer."""

    def setUp(self):
        self.ai = diagnosis.spec_at(AI_LEDGER)

    def test_the_tabular_libraries_are_empty_rather_than_the_ml_ledgers_three(self):
        from app.tools import classical

        self.assertEqual(
            classical.libraries_the_engine_names(), ["LightGBM", "XGBoost", "CatBoost"]
        )
        self.assertEqual(classical.libraries_the_engine_names(self.ai), [])

    def test_the_tuning_trial_count_is_none_rather_than_fifty(self):
        from app.tools import classical

        self.assertEqual(classical.trials_the_gate_asks_for(), 50)
        self.assertIsNone(classical.trials_the_gate_asks_for(self.ai))

    def test_the_failure_buckets_are_empty_rather_than_the_ml_ledgers_eight(self):
        from app.tools import evals

        # The fallback constant exists so a paid eval run does not die on a
        # renamed node. It must NEVER stand in for a second domain's vocabulary,
        # which is the wrong-file read dressed as resilience.
        self.assertEqual(len(evals.routable_modes()), 8)
        # THE SECOND LEDGER PUBLISHES ITS OWN VOCABULARY NOW. It used to be ()
        # here - correct, and a blocker: run_the_failures could grade rows but
        # the ledger published no buckets for the histogram to route on. The
        # fork declares itself under contract.knowledge and evals reads THAT,
        # so these five names are this ledger's own answer, not a borrowed one.
        self.assertEqual(
            evals.routable_modes(self.ai),
            ("context", "format", "reasoning", "tool_choice", "tool_execution"),
        )

    def test_the_eval_floor_refuses_rather_than_handing_over_thirty(self):
        from app.tools import data, propose

        answer = data.eval_set_floor(self.ai)
        self.assertIsNone(answer["rows"])
        self.assertIn(AI_LEDGER, answer["why_not"])
        with self.assertRaises(propose.NotEnoughToPropose) as caught:
            propose.g0_minimum(self.ai)
        self.assertIn(AI_LEDGER, str(caught.exception))


class ARefusalTellsACoverageGapFromAnotherDomainTest(unittest.TestCase):
    """`PROPOSERS` is keyed by one ledger's 55 outcome ids and by nothing else.

    Â§8.3 is the largest coupling and its structural fix - `contract.builds`,
    coverage computed over the live registry - is `ledger_format: 4` and is not
    this pass's work. What IS this pass's work is that the fallback sentence
    stops making a claim about coverage that the tables were never asked.
    """

    def setUp(self):
        support.sandbox(self)
        self.ai = events.create_thread("an agent problem", ledger=AI_LEDGER)["id"]

    def test_a_second_ledgers_outcome_now_plans_when_given_its_paths(self):
        """RETIRED AND INVERTED 2026-08-25. Was: a refusal naming the domain.

        This asserted that an AI thread's propose_build said *"these tables
        were never asked this domain's question"* - true until
        `_propose_the_tool_layer_loop` shipped, seeded by exactly this test's
        fact rows. The property worth holding now has two halves: WITHOUT the
        paths, the refusal names what is missing (a need, not a wrong-domain
        wall); WITH them, the same seeded thread gets an executable plan for
        BUILD__AGENT_WITH_TOOLS.
        """
        ai = diagnosis.spec_at(AI_LEDGER)
        token = evidence._STAMPING.set(True)
        try:
            for name, value in {
                "failing_cases_n": 20,
                "can_rerun_failures": True,
                "target_success_rate": 0.9,
                "baseline_success_rate": 0.4,
                "failure_rate_measured": True,
                "simple_version_tried": True,
                "workflow_tried": True,
                "failure_reproduces": True,
                "tokens_per_run": 2100.0,
                "run_terminates": True,
                "has_traces": True,
                "tool_count": 3,
                "tool_call_success_rate": 0.9,
                "control_flow_is_dynamic": True,
                "one_context_is_insufficient": False,
                "failure_buckets": {"reasoning": 15, "format": 5},
            }.items():
                source = ai.facts[name].get("source")
                origin = evidence.STATED if source == "ask" else evidence.MEASURED
                evidence.record(
                    fact=name,
                    value=value,
                    origin=origin,
                    actor="user" if origin == evidence.STATED else "harness",
                    how="seeded by this test",
                    tool="a_test",
                    thread_id=self.ai,
                    ledger=ai,
                )
        finally:
            evidence._STAMPING.reset(token)

        starved = REGISTRY.call(
            "propose_build", {"facts": {}}, actor="user", thread_id=self.ai
        )
        self.assertFalse(starved["ok"])
        self.assertEqual(starved["error"], "no_honest_build")
        self.assertIn("traces_path", starved.get("needs", []))

        fed = REGISTRY.call(
            "propose_build",
            {
                "facts": {},
                "traces_path": str(AGENT_FIXTURES / "journey-traces.jsonl"),
                "failures_path": str(AGENT_FIXTURES / "journey-failures.jsonl"),
                "input_field": "input",
                "expected_field": "expected",
                "answer_field": "answer",
            },
            actor="user",
            thread_id=self.ai,
        )
        self.assertTrue(fed["ok"], fed)
        self.assertEqual((fed.get("build") or {}).get("for_outcome"), "BUILD__AGENT_WITH_TOOLS")


class TheMlPathDoesNotMoveTest(unittest.TestCase):
    """A generalisation that moves a machine-learning verdict is a regression."""

    def test_the_gate_floor_and_its_attribution_are_unchanged(self):
        from app.tools import data, propose

        floor = data.eval_set_floor()
        self.assertEqual(floor["rows"], 30)
        self.assertEqual(
            floor["declared_in"], f"G0_EVAL_SET.passes_when in {ML_LEDGER}"
        )
        self.assertEqual(propose.g0_minimum(), 30)

    def test_the_empty_sheet_still_reaches_the_first_ledgers_first_answer(self):
        self.assertEqual(
            diagnosis.diagnose({}).outcome, "BLOCKED__DEFINE_SUCCESS_FIRST"
        )

    def test_a_diagnosis_carries_the_ledger_it_was_computed_from(self):
        self.assertIs(diagnosis.diagnose({}).spec, diagnosis.default_spec())
        ai = diagnosis.spec_at(AI_LEDGER)
        self.assertIs(diagnosis.diagnose({}, ai).spec, ai)

    def test_two_diagnoses_that_say_the_same_thing_are_still_equal(self):
        # The `Spec` is excluded from comparison on purpose: two answers are the
        # same answer when they say the same thing, and a 3,468-line parsed
        # document in a dataclass `__eq__` would be a slow way to say so.
        self.assertEqual(diagnosis.diagnose({}), diagnosis.diagnose({}))


class NothingInTheToolLayerReadsOneLedgerUnconditionallyTest(unittest.TestCase):
    """The structural half, checked by reading the code rather than by care.

    `default_spec()` survives and is SCOPED: it is the answer for a caller with
    no thread - registration, and the standing walk over nothing. What must not
    return is the UNCONDITIONAL use of it by something that could have been
    handed the thread's ledger, because that is the whole defect and it is
    invisible at the call site.

    So every `default_spec()` under `app/tools/` must be the right-hand side of
    a fallback - `spec or diagnosis.default_spec()` - or an early return from a
    function whose whole job is to resolve one. BROKEN BEFORE BELIEVED: putting
    `diagnosis.default_spec().facts` back into `evidence.declared_fact` fails
    this test by name.
    """

    def test_every_default_spec_in_the_tool_layer_is_a_fallback(self):
        root = Path(__file__).resolve().parents[1] / "app" / "tools"
        offenders: list[str] = []
        for path in sorted(root.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            parents: dict[ast.AST, ast.AST] = {}
            for node in ast.walk(tree):
                for child in ast.iter_child_nodes(node):
                    parents[child] = node
            for node in ast.walk(tree):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "default_spec"
                ):
                    continue
                parent = parents.get(node)
                # `x or default_spec()` and `default_spec() if ... else ...`,
                # plus `return default_spec()` inside a resolver.
                ok = isinstance(parent, (ast.BoolOp, ast.IfExp)) or (
                    isinstance(parent, ast.Return)
                    and _enclosing_function(parents, node) in _RESOLVERS
                )
                if not ok:
                    offenders.append(
                        f"{path.name}:{node.lineno} in "
                        f"{_enclosing_function(parents, node)}"
                    )
        self.assertEqual(
            offenders,
            [],
            "These read the first ledger without asking which one the thread is "
            "running. Take the ledger as a parameter, or fall back to it "
            "explicitly so a reader can see the choice being made.",
        )


#: The functions whose entire job is to answer "which ledger", and which are
#: therefore allowed to return the default outright. Named rather than pattern
#: matched, so adding a third one is a decision somebody made here.
_RESOLVERS = frozenset(
    {
        "spec",
        "ledger_for_thread",
        # `propose.py`'s three dispatch tables are keyed by one ledger's outcome
        # ids; the function names that coupling rather than hiding it, and it is
        # what lets the refusal tell a coverage gap from another domain's
        # question. See `docs/CAPABILITY_BLOCKS.md` Â§8.3.
        "the_ledger_these_tables_are_keyed_to",
    }
)


def _enclosing_function(parents: dict, node: ast.AST) -> str:
    walker = parents.get(node)
    while walker is not None:
        if isinstance(walker, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return walker.name
        walker = parents.get(walker)
    return "<module>"


class EveryLedgerThisProductShipsIsFoundTest(unittest.TestCase):
    """`known_ledgers()` is discovered, never listed. Â§4's rejected manifest."""

    def test_both_shipped_ledgers_are_found_and_the_default_is_first(self):
        found = [diagnosis.spec_at(p).as_written for p in diagnosis.known_ledgers()]
        self.assertEqual(found[0], ML_LEDGER)
        self.assertIn(AI_LEDGER, found)

    def test_a_ledger_dropped_into_the_directory_is_found_with_no_edit_here(self):
        # The manifest Â§4 rejected would need a second edit and it is the second
        # edit people forget. This asserts there is no second edit.
        #
        # NOT BY WRITING INTO THE CHECKOUT. `docs/ledgers/` is source and
        # `tests/support.py` lists it read-only for exactly that reason, so the
        # directory is rebound to a temporary one instead - which tests the same
        # derivation and leaves the user's repository alone.
        elsewhere = Path(tempfile.mkdtemp())
        (elsewhere / "a_third_ledger.yaml").write_text(
            (diagnosis.LEDGERS_DIR / "ai_engineering.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        original = diagnosis.LEDGERS_DIR
        diagnosis.LEDGERS_DIR = elsewhere
        self.addCleanup(setattr, diagnosis, "LEDGERS_DIR", original)
        self.assertIn(
            (elsewhere / "a_third_ledger.yaml").resolve(), diagnosis.known_ledgers()
        )

    def test_the_spec_cache_hands_back_one_object_per_file(self):
        self.assertIs(diagnosis.spec_at(ML_LEDGER), diagnosis.default_spec())
        self.assertIs(diagnosis.spec_at(AI_LEDGER), diagnosis.spec_at(AI_LEDGER))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
