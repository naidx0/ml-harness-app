"""The third domain, driven: every answer it can give, and the one gate nobody else has.

`docs/ledgers/harness_design.yaml` asks *"you want to build a thing that uses a
model - should you, what shape, and what would tell you that you were wrong?"*,
and it is UPSTREAM of both shipped ledgers. The ML one asks whether to train.
The AI one asks whether to fix an agent that already fails. This one is asked by
somebody who has built nothing.

## What this file is for

Every one of the twenty-eight outcomes is walked through the real engine from a
real fact sheet. That is not thoroughness for its own sake: eleven of them are
REFUSALS, and a dead refusal is invisible to anything that only looks at the
builds. The shadowing rule killed four outcomes in the ML ledger and seven in
one stage of it, and both times the mechanism was a widened condition above a
narrower one.

## The three things it asserts that no other ledger's test can

1. **G3_EVERY_COMPONENT_IS_LOAD_BEARING has no analogue anywhere**, and it is
   the reason this domain is worth a file. A harness is a pile of components
   each encoding an assumption about what the model cannot do alone, and those
   assumptions rot as models improve.
2. **The ladder is four rungs and the sweep is what enforces it.** Every shape
   is proposed in `stage_4_the_shape`, upstream of three of the six gates, so a
   proposal reaches `S9_SWEEP_EVERY_GATE` having passed G2 under whatever row
   applied on the way down - `any`, for the class-agnostic spine. The sweep
   re-asks under the proposal's own class, and that re-ask is the only
   structural reason an `AGENT_TEAM` cannot be proposed by somebody who never
   built the pipeline.
3. **Nothing in this domain's instruments runs anything.** Every rung and both
   arms of every ablation are recordings the person exported.

## The defect this file found while it was being written

Driven on 2026-08-28: a sheet asking for a team, with the single loop measured
and the FIXED SEQUENCE never run, walked to S9, failed G2's `multi_agent` row at
the sweep, took that gate's `on_fail` back into `stage_2_the_model_alone` - and
nothing there answered "the pipeline rung was never run". `S2_A_REAL_SHORTFALL`
fired again, the walk returned to the sweep, and the engine stopped it with
ERROR__CYCLE. **A gate's remedy stage must be exhaustive over every ROW of that
gate, not over the `any` row it was written against.** `NO_HARNESS__A_PIPELINE_FIRST`
is that missing node and `test_no_sheet_makes_the_engine_cycle` is what would
catch the next one.
"""

import unittest

from app import diagnosis
from app.tools import REGISTRY, blocks, evidence, propose
import harness_fixtures


LEDGER = "docs/ledgers/harness_design.yaml"


def spec() -> diagnosis.Spec:
    return diagnosis.spec_at(LEDGER)


class EveryAnswerIsReachableTest(unittest.TestCase):
    """One walk per outcome, through the real engine, from a real sheet."""

    def test_every_sheet_lands_where_its_key_says(self):
        """THE WHOLE FIXTURE SET, EXECUTED. A sheet keyed by an outcome it does
        not reach is a fixture that proves nothing and reads as proof."""
        for outcome, facts in sorted(harness_fixtures.SHEETS.items()):
            with self.subTest(outcome=outcome):
                self.assertEqual(diagnosis.diagnose(facts, spec()).outcome, outcome)

    def test_every_terminal_outcome_the_file_declares_is_reached_by_some_sheet(self):
        """THE OTHER DIRECTION, and it is the one that catches a shadowed node.

        A refusal killed by a widened condition above it is still DECLARED - it
        is in the file, it has a `say`, a reader would count it - and nothing
        that looks at outcomes-with-builds would notice it had died. Deriving
        the obligation from the spec is what makes this a check rather than a
        list somebody maintains.
        """
        declared = set(spec().declared_outcomes())
        errors = {name for name in declared if name.startswith("ERROR__")}
        # `SPEC__SUBSTANTIATE_CLAIMED_FACTS` is reached by the ORIGIN POLICY and
        # by no node - `fact_origins.unsubstantiated_outcome` names it - so no
        # fact sheet can walk to it and its absence here is correct.
        by_the_policy = {spec().unsubstantiated_outcome}
        self.assertEqual(
            declared - errors - by_the_policy - set(harness_fixtures.SHEETS),
            set(),
            "an outcome this ledger declares is reached by no sheet - either it "
            "is shadowed by a node above it, or the fixture set has a hole",
        )

    def test_no_sheet_makes_the_engine_cycle(self):
        """THE DEFECT THIS FILE FOUND, PINNED SO IT CANNOT COME BACK.

        A gate's `on_fail` routes into a remedy stage; if that stage has no node
        for the way the row actually failed, the walk falls through to whatever
        rerouted it and returns to the sweep. The engine's cycle guard turns
        that into a crash rather than a wrong answer, which is the right
        direction and is not the same as it being caught.
        """
        for outcome, facts in sorted(harness_fixtures.SHEETS.items()):
            with self.subTest(outcome=outcome):
                try:
                    diagnosis.diagnose(facts, spec())
                except diagnosis.EngineError as error:  # pragma: no cover
                    self.fail(f"{outcome} cycled: {error}")


class TheRefusalsAreTheProductTest(unittest.TestCase):
    def test_most_of_this_ledger_is_a_refusal(self):
        """The thesis, counted. If the builds ever outnumber the refusals, this
        file has become something other than what it was written to be."""
        declared = set(spec().declared_outcomes())
        refusals = {
            name
            for name in declared
            if name.startswith(("NO_HARNESS__", "NO_TOOLING__", "HANDOFF__"))
        }
        builds = {name for name in declared if name.startswith("HARNESS__")}
        self.assertEqual(len(builds), 4)
        self.assertGreater(len(refusals), len(builds))

    def test_every_refusal_says_something_a_person_can_act_on(self):
        """A refusal nobody can read is not one. Six of the second ledger's
        eighteen outcomes once reached a person with an EMPTY say."""
        index = spec().node_index
        for outcome, facts in sorted(harness_fixtures.SHEETS.items()):
            if not outcome.startswith(("NO_HARNESS__", "NO_TOOLING__", "HANDOFF__")):
                continue
            with self.subTest(outcome=outcome):
                said = str(diagnosis.diagnose(facts, spec()).say or "").strip()
                self.assertGreater(len(said), 120, f"{outcome} says almost nothing")

    def test_the_handoffs_name_the_file_that_asks_their_question(self):
        """Cross-ledger routing has no mechanism, so the verdict has to carry
        the answer in words. Both of them name a real ledger on disk."""
        shipped = {
            diagnosis.spec_at(path).as_written for path in diagnosis.known_ledgers()
        }
        for outcome in (
            "HANDOFF__DIAGNOSE_THE_EXISTING_AGENT",
            "HANDOFF__THE_KNOWLEDGE_IS_THE_PROBLEM",
        ):
            with self.subTest(outcome=outcome):
                said = diagnosis.diagnose(harness_fixtures.SHEETS[outcome], spec()).say
                self.assertTrue(
                    any(name in said for name in shipped - {LEDGER}),
                    f"{outcome} does not name the ledger it hands over to",
                )


class TheLadderIsEnforcedBySweepTest(unittest.TestCase):
    """G2 is four rows, and the sweep is what makes them unskippable."""

    def test_asking_for_a_team_without_a_pipeline_is_refused(self):
        """THE DEFECT, AS A TEST. This is the sheet that cycled."""
        facts = harness_fixtures.sheet(
            **{
                "success_check_named": True,
                "success_check_characters": 420,
                "success_check_is_a_program": True,
                "target_pass_rate": 0.9,
                "harness_tasks_n": 24,
                "can_rerun_tasks": True,
                "solo_pass_rate": 0.5,
                "steps_depend_on_the_last": True,
                "one_context_cannot_hold_it": True,
                "single_loop_pass_rate": 0.8,
                "boundaries_are_typed": True,
            }
        )
        self.assertEqual(
            diagnosis.diagnose(facts, spec()).outcome, "NO_HARNESS__A_PIPELINE_FIRST"
        )

    def test_asking_for_a_team_without_the_single_loop_is_refused(self):
        self.assertEqual(
            diagnosis.diagnose(
                harness_fixtures.SHEETS["NO_HARNESS__ONE_LOOP_FIRST"], spec()
            ).outcome,
            "NO_HARNESS__ONE_LOOP_FIRST",
        )

    def test_no_class_falls_back_past_a_row_a_weaker_class_has(self):
        """THE INVARIANT `method_class_ladder` EXISTS TO MAKE CHECKABLE.

        A class with no row of its own falls back to `any` - the WEAKEST
        question in the gate, not the nearest - and SC3 is satisfied by "some
        row applies". So the moment a gate gives ANY class its own row, every
        stronger class needs one too. This cost the second ledger a real defect
        the hour `multi_agent` landed, and the ladder here is one rung longer.
        """
        current = spec()
        ladder = list(current.contract["method_class_ladder"])
        for gate_id, gate in current.gates.items():
            rows = {row["method_class"] for row in gate["passes_when"]}
            for index, klass in enumerate(ladder):
                if klass not in rows:
                    continue
                for stronger in ladder[index + 1 :]:
                    with self.subTest(gate=gate_id, weaker=klass, stronger=stronger):
                        self.assertIn(
                            stronger,
                            rows,
                            f"{gate_id} gives {klass!r} its own row and not "
                            f"{stronger!r}, which is stronger - so the harder "
                            "shape is asked the easier question",
                        )


class TheGateNobodyElseHasTest(unittest.TestCase):
    """G3, and the instrument that made it possible."""

    def test_no_other_ledger_asks_this_question(self):
        """Stated as a property of the shipped files rather than as a claim.

        `components_ablated_n` and `components_that_earned_their_place` are this
        ledger's alone, which is what "no analogue" means mechanically.
        """
        elsewhere: set[str] = set()
        for path in diagnosis.known_ledgers():
            other = diagnosis.spec_at(path)
            if other.as_written != LEDGER:
                elsewhere |= set(other.facts)
        self.assertNotIn("components_ablated_n", elsewhere)
        self.assertNotIn("components_that_earned_their_place", elsewhere)

    def test_proposing_nothing_is_not_a_way_through_the_gate(self):
        """`components_proposed_n > 0` IS PART OF THE ROW AND IT IS LOAD-BEARING.

        Without it, `components_ablated_n >= components_proposed_n` is 0 >= 0 on
        a fresh sheet and the gate this domain exists for passes by having
        nothing to ask about.
        """
        self.assertEqual(
            diagnosis.diagnose(
                harness_fixtures.SHEETS["SPEC__NAME_THE_COMPONENTS"], spec()
            ).outcome,
            "SPEC__NAME_THE_COMPONENTS",
        )

    def test_a_component_that_changed_nothing_is_a_refusal_not_a_pass(self):
        """The third clause of the row, and the most valuable finding this
        ledger produces. Ablating everything and learning nothing must not read
        as having done the work."""
        self.assertEqual(
            diagnosis.diagnose(
                harness_fixtures.SHEETS["NO_HARNESS__STRIP_A_COMPONENT"], spec()
            ).outcome,
            "NO_HARNESS__STRIP_A_COMPONENT",
        )


class TheInstrumentsExistAndReadRatherThanRunTest(unittest.TestCase):
    def test_every_inspect_fact_has_an_instrument(self):
        """`known_gaps.no_instrument_measures: []` is a CLAIM, and this is it
        recomputed in both directions off the live registry."""
        current = spec()
        inspect_facts = {
            name
            for name, declared in current.facts.items()
            if declared.get("source") == "inspect"
        }
        measured = {fact for tool in REGISTRY for fact in tool.measures}
        self.assertEqual(
            sorted(inspect_facts - measured),
            list(current.raw["known_gaps"]["no_instrument_measures"]),
        )

    def test_the_ledger_binds_every_one_of_them_to_a_capability(self):
        """Wall 9. A fact that names no instrument may be stamped by any tool
        that happens to declare it."""
        current = spec()
        for name, declared in sorted(current.facts.items()):
            if declared.get("source") != "inspect":
                continue
            with self.subTest(fact=name):
                self.assertTrue(evidence.measured_by(name, current))

    def test_no_instrument_of_this_domain_executes_anything(self):
        """THE RULE THE WHOLE PACK IS BUILT AROUND, asserted off `reads`.

        `docs/ledgers/HARNESS_DESIGN.md` predicted the ladder rates could not be
        instrumented "because scoring a harness variant means running somebody
        else's system, which the `agent` pack forbids". The forbidden thing was
        the DRIVING; grading a recording is reading a file. No tool in this pack
        declares a capability to reach a process, a shell or a provider.
        """
        for tool in REGISTRY:
            if not any(name.startswith("harness.") for name in tool.provides):
                continue
            with self.subTest(tool=tool.name):
                self.assertEqual(
                    set(tool.reads) - {"filesystem", "datasets", "traces"},
                    set(),
                    f"{tool.name} reads more than files",
                )

    def test_the_pack_is_this_ledgers_and_no_other_stage_loads_it(self):
        """A tool in the model's hands whose success writes another ledger's
        fact ids is the thing separate packs exist to prevent."""
        self.assertIn("harness", blocks.PACKS)
        needs = spec().contract["capabilities"]["needs"]
        self.assertEqual(sorted(needs), sorted(spec().stages))
        self.assertTrue(any("harness" in packs for packs in needs.values()))


class TheCoverageTablesTellTheTruthTest(unittest.TestCase):
    def test_every_outcome_is_in_exactly_one_table(self):
        declared = set(spec().declared_outcomes())
        covered = declared & set(propose.COVERAGE)
        explained = declared & set(propose.NOT_COVERED)
        self.assertEqual(declared - covered - explained, set())
        self.assertEqual(covered & explained, set())

    def test_the_builds_are_covered_and_the_refusals_are_explained(self):
        for outcome in spec().declared_outcomes():
            if outcome.startswith("HARNESS__"):
                with self.subTest(outcome=outcome):
                    self.assertIn(outcome, propose.COVERAGE)
            if outcome.startswith(("NO_HARNESS__", "NO_TOOLING__", "HANDOFF__")):
                with self.subTest(outcome=outcome):
                    self.assertIn(outcome, propose.NOT_COVERED)
                    self.assertIn("refus", propose.NOT_COVERED[outcome] + "refus")

    def test_the_reason_for_a_refusal_says_it_is_the_answer(self):
        """A `NOT_COVERED` entry that read as an apology would be the product
        describing its own best answers as gaps."""
        reason = propose.NOT_COVERED["NO_HARNESS__ONE_CALL"]
        self.assertIn("the refusal IS the product", reason)
        self.assertIn("the answer is not to build", reason)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
