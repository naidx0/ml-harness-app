"""THE AI-ENGINEERING LEDGER'S CONTENT, DRIVEN. Phase 1, `docs/PHASES.md`.

`tests/test_a_second_ledger_runs_on_this_engine.py` proves the ENGINE runs a
second domain. This file is about whether the domain is any good, which is a
different question and the one Phase 1 is actually for:
`docs/ledgers/AI_ENGINEERING_DESIGN.md` says *"the refusals first, because they
are the product"*, and a ledger can satisfy every structural check in the engine
while giving a person nothing to read and no answer that fits their problem.

FOUR THINGS WERE MEASURED ON 2026-08-24 AND ALL FOUR WERE WRONG. Each has a class
beside it, because the class is the half that generalises.

  1. SIX OF EIGHTEEN DECLARED OUTCOMES REACHED A PERSON WITH AN EMPTY `say`.
     The engine turns a gate's `on_fail.note` into `Diagnosis.say`; not one gate
     in the file had one, so every outcome minted by a gate failure was silent -
     including NO_AGENT__ONE_API_CALL, the first refusal the design document
     lists and the one this ledger exists to give. **A field the engine reads
     from an optional key is a field that is absent until somebody checks it
     is not.**

  2. `tool_execution` FAILURES WERE TOLD THE TOOLS WERE NOT THE BUG. The fork
     routed five buckets to two stages, and stage_3_tools diagnoses tool CHOICE:
     both its nodes read `tool_call_success_rate`, which measures whether the
     model called the right thing rather than whether the thing worked. So the
     one bucket that names a broken tool got NO_TOOLS__PROMPT_IS_THE_BUG, and
     `context` and `format` were asked whether their control flow was dynamic.
     **A route is an answer, and a route that collapses two questions answers
     one of them wrongly.**

  3. `BUILD__MULTI_AGENT` WAS EXACTLY AS HARD TO REACH AS `BUILD__AGENT_WITH_TOOLS`.
     It carried `class: agent`, so it answered the same rows of the same gates,
     and differed by the SIGN of one `source: ask` boolean read at a node - where
     an assertion is admissible. The design document says its bar is deliberately
     the highest in the ledger. **"The hardest outcome" is a claim about clauses
     and gates, and it is measurable; until somebody counts, it is a comment.**

  4. THE FILE SAID FOUR OF ITS NINE `inspect` FACTS HAD NO INSTRUMENT. Nine of
     nine do. The measurement is one expression, the file already prescribed it
     thirty lines below the sentence that was wrong, and prose cannot be
     recomputed. **A count in a comment is a count that will drift, and it will
     drift in the direction that flatters us.**

Nothing here writes to the repository tree or to a database.
"""

from __future__ import annotations

import itertools
import unittest
from pathlib import Path

from app.diagnosis import (
    GATE_PASSED,
    MEASURED,
    STATED,
    Fact,
    diagnose,
    load_spec,
)
from app.tools import REGISTRY

LEDGER = Path(__file__).resolve().parents[1] / "docs" / "ledgers" / "ai_engineering.yaml"

#: Attribute a fact the way its own `source:` admits - the ledger's column, read
#: rather than restated. A test that granted itself a licence the product cannot
#: grant would prove the ledger works for nobody who exists.
_ORIGIN_FOR_SOURCE = {"inspect": MEASURED, "ask": STATED, "derive": MEASURED}

#: The five buckets, in the fork's own route-declaration order. Ties resolve in
#: this order, in the fork AND in stage_2's node order, and
#: `test_the_tie_break_order_is_the_same_in_both_places` is what keeps them equal.
BUCKETS = ("tool_choice", "tool_execution", "reasoning", "context", "format")


class LedgerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec(LEDGER)

    def base(self) -> dict[str, object]:
        """One coherent story: a real agent, forty real failures, all measured.

        Every sheet below is this story with ONE thing changed, which is what
        makes each of them a diagnosis rather than a coincidence.
        """
        return {
            "failing_cases_n": 40,
            "can_rerun_failures": True,
            "failure_rate_measured": True,
            "baseline_success_rate": 0.55,
            "target_success_rate": 0.9,
            "failure_reproduces": True,
            "has_traces": True,
            "tokens_per_run": 4200,
            "run_terminates": True,
            "simple_version_tried": True,
            "workflow_tried": True,
            "single_agent_tried": True,
            "tool_count": 3,
            "tool_call_success_rate": 0.95,
            "control_flow_is_dynamic": True,
            "one_context_is_insufficient": False,
            "failure_buckets": {"reasoning": 30, "tool_choice": 5, "format": 5},
        }

    def facts(self, *, drop=(), bare=(), **overrides):
        values = self.base()
        values.update(overrides)
        for name in drop:
            values.pop(name, None)
        out = {}
        for name, value in values.items():
            self.assertIn(name, self.spec.facts, f"{name!r} is not a fact in this ledger")
            if name in bare:
                out[name] = value  # bare is ASSERTED, and an assertion opens no gate
            else:
                out[name] = Fact(
                    value, _ORIGIN_FOR_SOURCE[self.spec.facts[name]["source"]]
                )
        return out

    def run_sheet(self, **kwargs):
        return diagnose(self.facts(**kwargs), self.spec)

    def answer(self, **kwargs) -> str:
        return self.run_sheet(**kwargs).outcome


#: ONE SHEET PER DECLARED OUTCOME, and the key is what a person changed rather
#: than what the ledger answers - so a sheet that starts reaching a different
#: outcome shows up as a coverage hole rather than as a renamed label.
SHEETS: dict[str, dict] = {
    "four failures written down": dict(failing_cases_n=4),
    "no failures at all": dict(failing_cases_n=0),
    "cannot re-run them": dict(can_rerun_failures=False),
    "no target rate": dict(drop=("target_success_rate",)),
    "will not reproduce": dict(failure_reproduces=False),
    "rate never measured": dict(
        failure_rate_measured=False, drop=("baseline_success_rate",)
    ),
    "already at target": dict(baseline_success_rate=0.95),
    "nothing recorded": dict(has_traces=False),
    "three failures bucketed": dict(failure_buckets={"reasoning": 3}),
    "buckets with no route": dict(failure_buckets={"latency": 30}),
    "tool choice failures, no tools": dict(
        failure_buckets={"tool_choice": 30}, tool_count=0
    ),
    "tools exist, never called": dict(
        failure_buckets={"tool_choice": 30}, tool_call_success_rate=0.2
    ),
    "tools fire, wrong one chosen": dict(
        failure_buckets={"tool_choice": 30}, tool_call_success_rate=0.95
    ),
    "the tool returns junk": dict(failure_buckets={"tool_execution": 30}),
    "it was not knowable": dict(failure_buckets={"context": 30}),
    "right answer, wrong shape": dict(failure_buckets={"format": 30}),
    "control flow is static": dict(control_flow_is_dynamic=False),
    "fixed sequence never tried": dict(workflow_tried=False),
    "one call never tried": dict(simple_version_tried=False),
    "everything tried, dynamic": dict(),
    "one context is not enough": dict(one_context_is_insufficient=True),
    "wants many, never built one": dict(
        one_context_is_insufficient=True, single_agent_tried=False
    ),
    "loop never bounded": dict(run_terminates=False),
    "the count is only claimed": dict(bare=("failing_cases_n",)),
}


class EveryRefusalCanBeReadTest(LedgerCase):
    """FINDING 1. `say` is the sentence; a refusal nobody can read is not one.

    `app/asking.py:proposal_for` puts `_line(result.say)` on the card, and
    `_line(None)` is the empty string - so a missing `on_fail.note` is not an
    error anywhere. It is a blank space where the product's whole argument was
    supposed to be, and every structural check in the engine stays green.
    """

    def test_every_declared_outcome_is_reached_by_a_sheet(self):
        reached = {self.answer(**change) for change in SHEETS.values()}
        missing = sorted(self.spec.declared_outcomes() - reached)
        self.assertEqual(
            missing,
            [],
            f"{len(missing)} declared outcome(s) no sheet here reaches: {missing}. "
            "Add the sheet, or take the outcome out - a branch nothing reaches is "
            "an answer the product claims it can give and cannot.",
        )

    def test_no_sheet_reaches_an_outcome_the_file_does_not_declare(self):
        """The other direction, which is the one a hand-kept list gets wrong."""
        declared = self.spec.declared_outcomes()
        for label, change in SHEETS.items():
            with self.subTest(sheet=label):
                self.assertIn(self.answer(**change), declared)

    def test_every_outcome_reaches_the_person_with_something_to_read(self):
        """THE REGRESSION. Six of eighteen were silent before 2026-08-24."""
        silent = []
        for label, change in SHEETS.items():
            result = self.run_sheet(**change)
            if not str(result.say or "").strip():
                silent.append(f"{result.outcome} (sheet: {label}, node: {result.node})")
        self.assertEqual(
            silent,
            [],
            "these outcomes reach a person with an empty `say`:\n  "
            + "\n  ".join(silent)
            + "\nA gate states its sentence in `on_fail.note` and a node in `say:`. "
            "The refusals are the product and a blank card is not a refusal.",
        )

    def test_every_gate_states_both_of_its_sentences(self):
        """The structural half, so a SIXTH gate cannot arrive silent.

        The test above needs a sheet that reaches the gate. This one needs
        nothing, so a gate added next month is covered on the day it is added.
        """
        for gate_id in self.spec.required_gates:
            gate = self.spec.gates[gate_id]
            with self.subTest(gate=gate_id):
                on_fail = gate.get("on_fail") or {}
                if "outcome" in on_fail:
                    self.assertTrue(
                        str(on_fail.get("note") or "").strip(),
                        f"{gate_id}.on_fail names {on_fail['outcome']} and no note, so "
                        "that outcome reaches a person with a blank card",
                    )
                else:
                    self.assertIn(
                        "route",
                        on_fail,
                        f"{gate_id}.on_fail neither ends nor routes",
                    )
                self.assertTrue(
                    str((gate.get("on_unsubstantiated") or {}).get("note") or "").strip(),
                    f"{gate_id} has no on_unsubstantiated.note, so a person whose "
                    "claim this gate refused is told nothing about which claim or why",
                )

    def test_a_routing_gate_still_records_that_it_failed(self):
        """G0 routes rather than ending, and the gate ledger must not lose that.

        The whole reason it routes is that "you have four" and "you have none"
        are different sentences. If routing cost the gate ledger its FAILED, the
        trade would have been a sentence for a piece of provenance.
        """
        for label, sheet in (("four", dict(failing_cases_n=4)), ("none", dict(failing_cases_n=0))):
            with self.subTest(failures=label):
                result = self.run_sheet(**sheet)
                self.assertEqual(
                    result.gate_ledger["G0_SOMETHING_TO_MEASURE"]["status"], "FAILED"
                )
                # RETIRED AND REWRITTEN 2026-08-25: this asserted the bare
                # clause "failing_cases_n >= 10". G0 now also reads
                # `can_rerun_failures`, because "written down that we can check
                # against" is one question and a set nobody can re-run is not
                # it - and reading the fact at the GATE is what kills an
                # ASSERTED claim about re-runnability, which nodes may not do.
                self.assertEqual(
                    result.gate_ledger["G0_SOMETHING_TO_MEASURE"]["clause"],
                    "failing_cases_n >= 10 and can_rerun_failures",
                )

    def test_the_two_ends_of_G0_are_different_sentences(self):
        four = self.run_sheet(failing_cases_n=4)
        none = self.run_sheet(failing_cases_n=0)
        self.assertEqual(four.outcome, "ACTION__WRITE_DOWN_TEN_FAILURES")
        self.assertEqual(none.outcome, "BLOCKED__NOTHING_TO_MEASURE_AGAINST")
        self.assertNotEqual(four.say, none.say)

    def test_the_forks_say_is_the_sentence_its_no_match_needs(self):
        """A fork that matches never terminates, so this `say` has ONE reader.

        `_fork_no_match` passes the NODE's `say` through, and the fork's node is
        the fork. So whatever is written there is read by exactly one person -
        the one whose buckets have no route - and it used to describe how argmax
        works to them.
        """
        result = self.run_sheet(failure_buckets={"latency": 30, "cost": 12})
        self.assertEqual(result.outcome, "ACTION__CLASSIFY_THE_FAILURES")
        said = str(result.say or "")
        for bucket in BUCKETS:
            self.assertIn(
                bucket,
                said,
                f"the no-match sentence does not name {bucket!r}. It is the only "
                "sentence this person gets and its job is to name the five buckets "
                "this ledger can actually route on.",
            )


class TheFiveBucketsGetFiveAnswersTest(LedgerCase):
    """FINDING 2. The hinge of the ledger is the fork, and it was collapsing.

    `docs/ledgers/AI_ENGINEERING_DESIGN.md`: *"Each bucket routes somewhere
    different, and three of the five route to a refusal rather than to a build."*
    Five buckets shared two destinations and none of them refused deterministically.
    """

    #: What each bucket means and what it must therefore be answered with.
    EXPECTED = {
        "tool_execution": "NO_AGENT__FIX_THE_TOOL",
        "context": "NO_AGENT__FIX_THE_CONTEXT",
        "format": "NO_AGENT__CONSTRAIN_THE_OUTPUT",
    }

    def test_each_bucket_reaches_a_different_answer(self):
        answers = {b: self.answer(failure_buckets={b: 30}) for b in BUCKETS}
        self.assertEqual(
            len(set(answers.values())),
            len(BUCKETS),
            f"two buckets reach the same answer: {answers}. A bucket that cannot "
            "change the answer is a bucket the person was asked to compute for "
            "nothing.",
        )

    def test_the_three_that_are_not_about_the_loop_refuse(self):
        for bucket, outcome in self.EXPECTED.items():
            with self.subTest(bucket=bucket):
                result = self.run_sheet(failure_buckets={bucket: 30})
                self.assertEqual(result.outcome, outcome)
                self.assertEqual(result.verdict, "NO_BUILD")

    def test_no_build_is_reachable_from_those_three_however_the_rest_is_answered(self):
        """DRIVEN, NOT ARGUED. The claim is about every sheet, so sweep them.

        A refusal that only holds on one fact sheet is a coincidence. These three
        buckets must refuse whatever the person says about their loop, their
        tools, their ladder or their context - because the argument is that
        deciding-what-to-do-next was never the problem, and none of those facts
        touches that.
        """
        switches = (
            "control_flow_is_dynamic",
            "workflow_tried",
            "single_agent_tried",
            "one_context_is_insufficient",
        )
        checked = 0
        for bucket, outcome in self.EXPECTED.items():
            for combo in itertools.product((True, False), repeat=len(switches)):
                for tool_count in (0, 3):
                    sheet = dict(zip(switches, combo))
                    sheet["tool_count"] = tool_count
                    sheet["failure_buckets"] = {bucket: 30}
                    got = self.answer(**sheet)
                    checked += 1
                    self.assertEqual(
                        got,
                        outcome,
                        f"bucket {bucket!r} with {sheet} reached {got}, not {outcome}",
                    )
        self.assertEqual(checked, 96, "the sweep shrank; it is 3 buckets x 16 x 2")

    def test_the_hinge_still_asks_for_ten_before_it_forks(self):
        """ACTION__CLASSIFY_THE_FAILURES is the hinge and it has a floor.

        Nine bucketed failures is the same arithmetic problem as nine written
        down: a histogram over nine cases cannot tell a dominant bucket from a
        near-tie, and every route out of this fork is a different product.
        """
        self.assertEqual(
            self.answer(failure_buckets={"reasoning": 9}),
            "ACTION__CLASSIFY_THE_FAILURES",
        )
        self.assertNotEqual(
            self.answer(failure_buckets={"reasoning": 10}),
            "ACTION__CLASSIFY_THE_FAILURES",
        )

    def test_the_tie_break_order_is_the_same_in_both_places(self):
        """The fork resolves a tie by route order; stage_2 by node order.

        They must be the same order or a tied histogram gets one answer from the
        fork's arithmetic and a different one from the stage it lands in - and
        `shadowing_rule.where_it_bites_here` says why that is the hardest kind of
        change to see in a diff: it moves answers without touching a condition.
        """
        raw = self.spec.raw
        fork = [n for n in raw["stage_1_reproduce"] if n.get("node", "").endswith("BUCKET")]
        self.assertEqual(len(fork), 1)
        route_order = list(fork[0]["fork"]["routes"])
        self.assertEqual(
            route_order,
            list(BUCKETS),
            "the fork's routes were reordered, which changes which bucket wins a tie",
        )

        stage_2 = raw["stage_2_not_the_loop"]
        landing = [b for b in route_order if fork[0]["fork"]["routes"][b] == "stage_2_not_the_loop"]
        conditions = [str(n["condition"]) for n in stage_2]
        self.assertEqual(len(conditions), len(landing))
        for position, bucket in enumerate(landing):
            self.assertIn(
                f"failure_buckets.{bucket} ",
                conditions[position],
                f"stage_2's node {position} does not test {bucket!r}; the fork sends "
                f"{landing} here in that order and this stage answers them in "
                f"{conditions}. Two tie-break rules that disagree is one bug waiting "
                "for a tie.",
            )

    def test_a_tie_between_two_of_them_is_broken_the_same_way_twice(self):
        """The property the test above defends, driven on a real tie."""
        self.assertEqual(
            self.answer(failure_buckets={"context": 20, "format": 20}),
            "NO_AGENT__FIX_THE_CONTEXT",
            "`context` is declared before `format`, so it wins the tie in the fork "
            "and must win it again in the stage",
        )
        self.assertEqual(
            self.answer(failure_buckets={"tool_execution": 20, "format": 20}),
            "NO_AGENT__FIX_THE_TOOL",
        )

    def test_stage_two_never_runs_off_its_end_for_anything_the_fork_sends_it(self):
        """A stage with no matching node raises EngineError, which is a crash.

        Every histogram the fork can route here has one of the three buckets at
        the maximum, so one condition holds. Swept rather than argued, because
        `>= max(...)` over a mapping is exactly the kind of predicate that is
        obviously true until a None turns up in it.
        """
        landing = ("tool_execution", "context", "format")
        for combo in itertools.product((0, 7, 30), repeat=len(landing)):
            buckets = {b: n for b, n in zip(landing, combo) if n}
            if not buckets or sum(buckets.values()) < 10:
                continue
            with self.subTest(buckets=buckets):
                self.assertIn(
                    self.answer(failure_buckets=buckets),
                    set(self.EXPECTED.values()),
                )


class MultiAgentIsTheHardestOutcomeInTheFileTest(LedgerCase):
    """FINDING 3. It is supposed to be, and it was tied for easiest-of-the-builds.

    `docs/ledgers/AI_ENGINEERING_DESIGN.md`: *"BUILD__MULTI_AGENT should be the
    hardest outcome in the ledger to reach, for the same reason
    TRAIN__FROM_SCRATCH is in the ML one."* In the ML ledger that bar is a
    four-clause conjunction with three measured numbers in it. Here it was the
    sign of one boolean.
    """

    def mint(self, **kwargs):
        return self.run_sheet(one_context_is_insufficient=True, **kwargs)

    def test_it_has_a_class_of_its_own_so_it_can_be_asked_a_harder_question(self):
        self.assertEqual(self.spec.methods["MULTI_AGENT"]["class"], "multi_agent")
        self.assertEqual(self.spec.methods["AGENT_WITH_TOOLS"]["class"], "agent")
        self.assertNotEqual(
            self.spec.methods["MULTI_AGENT"]["class"],
            self.spec.methods["AGENT_WITH_TOOLS"]["class"],
            "sharing a class means sharing every gate row, which is what made the "
            "hardest outcome in the file exactly as hard as the one below it",
        )

    def test_its_gate_row_is_a_strict_superset_of_the_one_below_it(self):
        """Counted, in clauses, out of the file."""
        gate = self.spec.gates["G2_SIMPLE_VERSION_TRIED"]
        rows = {r["method_class"]: str(r["requires"]) for r in gate["passes_when"]}
        clauses = {k: {c.strip() for c in v.split(" and ")} for k, v in rows.items()}
        self.assertLess(clauses["any"], clauses["agent"])
        self.assertLess(
            clauses["agent"],
            clauses["multi_agent"],
            f"G2's multi_agent row is {rows.get('multi_agent')!r} and its agent row "
            f"is {rows['agent']!r}. The stronger class must ask strictly more.",
        )
        self.assertEqual(
            clauses["multi_agent"] - clauses["agent"],
            {"single_agent_tried"},
            "the rung the ladder was missing is the single agent",
        )

    def test_no_class_falls_back_past_a_row_a_weaker_class_has(self):
        """THE TRAP, AND IT IS THE ENGINE'S SEMANTICS RATHER THAN THIS FILE'S.

        `Spec.row_key` falls back to `any`, not to the nearest stronger class. So
        a gate that gives `agent` its own row and says nothing about
        `multi_agent` asks the STRONGEST method the WEAKEST question - and SC3 is
        satisfied, because some row applies. G4 was in exactly that state for as
        long as it took to notice: BUILD__MULTI_AGENT would have skipped
        `run_terminates`, the termination proof, which is half of the gate whose
        entire subject is termination.
        """
        ladder = list(self.spec.contract["method_class_ladder"])
        self.assertEqual(
            set(ladder),
            {decl["class"] for decl in self.spec.methods.values()},
            "contract.method_class_ladder must name every class the methods use, "
            "or a class arrives with no place in the order and this check skips it",
        )
        for gate_id in self.spec.required_gates:
            rows = {r["method_class"] for r in self.spec.gates[gate_id]["passes_when"]}
            for position, weaker in enumerate(ladder):
                if weaker not in rows:
                    continue
                for stronger in ladder[position + 1 :]:
                    with self.subTest(gate=gate_id, weaker=weaker, stronger=stronger):
                        self.assertIn(
                            stronger,
                            rows,
                            f"{gate_id} has a row for {weaker!r} and none for "
                            f"{stronger!r}, so {stronger!r} falls back to `any` - the "
                            "weakest question in the gate. The stronger method gets "
                            "the easier question and nothing in the engine says so.",
                        )

    def test_the_sweep_re_asks_G2_under_multi_agent(self):
        """The walk down is class-agnostic; the sweep is where the class arrives.

        G2 is passed under `any` on the spine, because NOTHING_PROPOSED is class
        `tools`. If the sweep did not re-ask it under `multi_agent`, "I tried one
        API call" would satisfy the gate that exists to ask about the ladder.
        """
        result = self.mint()
        self.assertEqual(result.outcome, "BUILD__MULTI_AGENT")
        rows = [
            e.row
            for e in result.path
            if e.kind == "gate" and e.id == "G2_SIMPLE_VERSION_TRIED"
        ]
        self.assertEqual(rows, ["any", "multi_agent"])
        self.assertEqual(
            result.gate_ledger["G2_SIMPLE_VERSION_TRIED"]["clause"],
            "simple_version_tried and workflow_tried and single_agent_tried",
        )
        self.assertEqual(
            result.gate_ledger["G4_COST_AND_TERMINATION_BOUNDED"]["clause"],
            "tokens_per_run is not null and run_terminates and has_traces",
            "G4's multi_agent row must ask for the termination proof over a "
            "record somebody can read. If `has_traces` is missing, an ASSERTED "
            "claim about the record dies nowhere; if `run_terminates` is "
            "missing, the row fell back to `any`.",
        )
        for gate_id in self.spec.required_gates:
            self.assertEqual(result.gate_ledger[gate_id]["status"], GATE_PASSED)

    def test_the_agent_below_it_is_reachable_on_the_same_sheet(self):
        """The control. Without it, "harder" could just mean "broken"."""
        result = self.run_sheet()
        self.assertEqual(result.outcome, "BUILD__AGENT_WITH_TOOLS")
        for gate_id in self.spec.required_gates:
            self.assertEqual(result.gate_ledger[gate_id]["status"], GATE_PASSED)

    def test_the_one_fact_that_separates_them_costs_a_rung(self):
        """Strictly harder, driven: the sheet that mints the agent refuses this."""
        self.assertEqual(self.run_sheet().outcome, "BUILD__AGENT_WITH_TOOLS")
        self.assertEqual(
            self.mint(single_agent_tried=False).outcome, "NO_AGENT__ONE_AGENT_FIRST"
        )

    def test_a_model_answering_for_the_person_cannot_open_it(self):
        """THE HALF A NODE CANNOT DO, which is why the gate row exists as well.

        A node may route on an assertion - `fact_origins.scope` says so, and a
        route is not a verdict. A gate may not open on one. So a
        `single_agent_tried` that a model supplied walks past S5_NOT_TRIED_ONE_AGENT,
        proposes MULTI_AGENT, and is refused at the sweep by the origin policy
        rather than by the graph.
        """
        result = self.mint(bare=("single_agent_tried",))
        self.assertEqual(result.outcome, "ACTION__SUBSTANTIATE_CLAIMED_FACTS")
        self.assertEqual(
            [row["fact"] for row in result.unsubstantiated], ["single_agent_tried"]
        )
        self.assertEqual(result.unsubstantiated[0]["declared_source"], "ask")
        self.assertEqual(result.unsubstantiated[0]["origin"], "ASSERTED")

    def test_the_person_saying_it_themselves_does_open_it(self):
        """The other direction. A wall this tight breaks in exactly this place."""
        self.assertEqual(self.mint().outcome, "BUILD__MULTI_AGENT")

    def test_a_context_bucket_can_never_reach_the_multi_agent_stage(self):
        """The structural half of "most multi-agent systems are a context problem".

        S5_MULTI_AGENT's `say` claims this, so it is asserted here rather than
        believed: a run whose dominant bucket is `context` is refused before
        stage_5 is entered, whatever it says about its context window.
        """
        result = self.run_sheet(
            failure_buckets={"context": 30}, one_context_is_insufficient=True
        )
        self.assertEqual(result.outcome, "NO_AGENT__FIX_THE_CONTEXT")
        self.assertNotIn("S5_MULTI_AGENT", [e.id for e in result.path])


class TheLedgerCountsItsOwnMissingInstrumentsTest(LedgerCase):
    """FINDING 4. The file said four. Nine is the answer, and it drifted because
    it was a sentence.

    `docs/PHASES.md` calls this class out by name in its own debts: a bound that
    only ever pushes in one direction cannot see the failure in the other. So
    this asserts BOTH directions - a fact on the list that something DOES measure
    is as red as a fact off the list that nothing does.
    """

    def measured_by_some_tool(self) -> set[str]:
        return {fact for spec in REGISTRY for fact in spec.measures}

    def test_the_declared_gap_is_exactly_the_measured_gap(self):
        declared = set(self.spec.raw["known_gaps"]["no_instrument_measures"])
        inspect_facts = {
            name for name, decl in self.spec.facts.items() if decl["source"] == "inspect"
        }
        actual = inspect_facts - self.measured_by_some_tool()
        self.assertEqual(
            declared,
            actual,
            "known_gaps.no_instrument_measures disagrees with the registry.\n"
            f"  on the list, but something measures it: {sorted(declared - actual)}\n"
            f"  nothing measures it, and it is not on the list: {sorted(actual - declared)}\n"
            "Shipping an instrument takes a name OFF this list. Declaring a fact "
            "`inspect` that nothing measures puts one ON it.",
        )

    def test_the_gap_list_and_the_registry_partition_the_inspect_facts(self):
        """REWRITTEN 2026-08-25, because the world it described shipped.

        This asserted that NO instrument measured ANY inspect fact here - true
        on 2026-08-24, false the day `app/tools/agents.py` landed. The
        invariant that survives the shipping is the partition: every inspect
        fact is EITHER measured by a registered instrument OR named in
        `known_gaps.no_instrument_measures`, never both, never neither.
        (The equality to the recomputed gap is `test_the_declared_gap_...`;
        this one holds the disjointness half and the provenance half - a fact
        on the list is one a run will reach as ASSERTED, so its gate door must
        be the substantiation outcome and nothing else.)
        """
        inspect_facts = {
            name for name, decl in self.spec.facts.items() if decl["source"] == "inspect"
        }
        declared = set(self.spec.raw["known_gaps"]["no_instrument_measures"])
        measured = self.measured_by_some_tool()
        self.assertFalse(
            declared & measured,
            f"a fact cannot be on the no-instrument list and measured: {sorted(declared & measured)}",
        )
        self.assertTrue(
            declared <= inspect_facts,
            f"the list names facts this ledger does not declare: {sorted(declared - inspect_facts)}",
        )
        for name in sorted(declared):
            with self.subTest(fact=name):
                self.assertEqual(self.spec.facts[name]["source"], "inspect")

    def test_the_registry_is_not_empty_so_the_check_is_not_trivially_green(self):
        """The non-vacuity guard. An empty registry would pass everything above."""
        self.assertGreater(len(self.measured_by_some_tool()), 5)
        self.assertGreater(len(list(REGISTRY)), 30)

    def test_a_claim_about_one_of_them_reaches_the_substantiation_door(self):
        """What the gap COSTS, driven, rather than only counted.

        This is the sentence in `docs/PHASES.md`: until the instruments exist,
        this ledger's honest answer to a real agent problem is
        ACTION__SUBSTANTIATE_CLAIMED_FACTS. Nine facts, nine doors.
        """
        for fact in sorted(self.spec.raw["known_gaps"]["no_instrument_measures"]):
            with self.subTest(fact=fact):
                result = self.run_sheet(bare=(fact,))
                self.assertEqual(
                    result.gate_ledger["G0_SOMETHING_TO_MEASURE"]["status"] != "PASSED"
                    or result.outcome == "ACTION__SUBSTANTIATE_CLAIMED_FACTS"
                    or result.verdict != "BUILD",
                    True,
                    f"a bare {fact} minted a build; an assertion opened a gate",
                )

    def test_no_asserted_inspect_fact_ever_mints_a_build(self):
        """The sharp version of the row above, and the one that matters.

        Every `inspect` fact this ledger has is unmeasurable today, so every one
        of them arrives ASSERTED in a real run. Not one may be the reason a
        BUILD__ was minted.
        """
        inspect_facts = sorted(
            name for name, decl in self.spec.facts.items() if decl["source"] == "inspect"
        )
        minted = []
        for fact in inspect_facts:
            for extra in ({}, {"one_context_is_insufficient": True}):
                result = self.run_sheet(bare=(fact,), **extra)
                if result.verdict == "BUILD":
                    minted.append(f"{fact} -> {result.outcome}")
        self.assertEqual(minted, [], "an assertion opened a gated build: " + str(minted))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
