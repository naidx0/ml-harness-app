"""PHASE B, DRIVEN: the instruments carry a real sheet to a gated verdict.

`docs/PHASES.md` Phase B wants one closed AI-engineering journey on real
recordings. This file is the engine-level half of that journey, driven the way
the second ML journey was re-driven under capability blocks - through the same
`REGISTRY.call` entry point a turn uses, with every fact arriving MEASURED from
an instrument or STATED by a person, and nothing else.

The fixtures under `tests/fixtures/agent/` are shaped like real third-party
traces (OpenTelemetry GenAI dialect, JSON Lines) rather than like this test:
two runs of one agent, one tool span carrying `STATUS_CODE_ERROR`, usage
attributes on every inference span. They are synthetic because TRAIL is gated
and the census is still owed - and the moment it is not, this journey is
re-pointed at real traces by changing three path constants, which is the point
of driving it at all.

THE WALL THIS JOURNEY ENDS AT IS THE FINDING, NOT A FAILURE. Four instruments
stamp eight facts, a person states six, all five gates pass under the
proposal's own class - and `propose_build` refuses with `no_honest_build`,
because no proposer exists for any BUILD__ outcome of this ledger yet. That is
exactly the shape the first ML journey taught this repository to record: the
machine works; the coverage is the next lane.
"""

from pathlib import Path
import unittest

from app import events, storm
from app import diagnosis
from app.tools import REGISTRY, propose, propose

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "agent"
TRACES = str(FIXTURES / "journey-traces.jsonl")
TOOLDEFS = str(FIXTURES / "journey-tools.json")
FAILURES = str(FIXTURES / "journey-failures.jsonl")
AI_LEDGER = "docs/ledgers/ai_engineering.yaml"

#: What the person says, in their own person (`actor="user"`). Everything else
#: on the sheet arrives MEASURED, which is what makes the verdict downstream of
#: evidence instead of downstream of whoever typed fastest.
PERSON_FACTS = {
    "target_success_rate": 0.9,
    "failure_reproduces": True,
    "simple_version_tried": True,
    "workflow_tried": True,
    "control_flow_is_dynamic": True,
    "one_context_is_insufficient": False,
}


class TheInstrumentsDriveAGatedVerdict(unittest.TestCase):
    def setUp(self):
        import support

        support.sandbox(self)

    #: The sheet the planner is handed, attributed exactly as the thread above
    #: holds it: instruments' readings MEASURED, the person's half STATED.
    #: Bare values would all arrive ASSERTED and the walk would stop at the
    #: substantiation door instead of minting.
    def _situation(self):
        ai = diagnosis.spec_at(AI_LEDGER)
        raw = {
            "failing_cases_n": 12,
            "can_rerun_failures": True,
            "failure_rate_measured": True,
            "baseline_success_rate": 1 / 12,
            "target_success_rate": 0.9,
            "failure_reproduces": True,
            "has_traces": True,
            "tokens_per_run": 250.0,
            "run_terminates": True,
            "simple_version_tried": True,
            "workflow_tried": True,
            "tool_count": 3,
            "tool_call_success_rate": 2 / 3,
            "control_flow_is_dynamic": True,
            "one_context_is_insufficient": False,
            "failure_buckets": {"reasoning": 9, "format": 1, "tool_execution": 1},
        }
        _origin = {
            "inspect": diagnosis.MEASURED,
            "derive": diagnosis.MEASURED,
            "ask": diagnosis.STATED,
        }
        sheet = {
            name: diagnosis.Fact(value, _origin[ai.facts[name]["source"]])
            for name, value in raw.items()
        }
        result = diagnosis.diagnose(sheet, ai)
        self.assertEqual(result.outcome, "BUILD__AGENT_WITH_TOOLS")
        return propose.Situation(
            outcome=result.outcome,
            result=result,
            values={name: getattr(f, "value", f) for name, f in sheet.items()},
            origins=dict(result.fact_origins),
            traces_path=TRACES,
            failures_path=FAILURES,
            input_field="input",
            expected_field="expected",
            answer_field="answer",
        )

    def _call(self, name, arguments, thread_id):
        result = REGISTRY.call(name, arguments, actor="user", thread_id=thread_id)
        self.assertTrue(
            result.get("ok"),
            f"{name} refused; the journey cannot continue on a refusal: {result}",
        )
        return result

    def _seed(self) -> int:
        """The four instrument calls and the person's six facts, on one thread."""
        thread = events.create_thread("phase-b-journey", ledger=AI_LEDGER)
        tid = thread["id"]

        # RUNG 1-2 - somebody else's agent, read.
        traced = self._call("read_agent_traces", {"path": TRACES}, tid)
        self.assertEqual(traced.get("runs"), 1 + 1)

        defined = self._call("read_tool_definitions", {"path": TOOLDEFS}, tid)
        self.assertGreaterEqual(defined.get("tool_count"), 3)

        bounded = self._call("bound_the_loop", {"path": TRACES}, tid)
        self.assertEqual(bounded.get("runs"), 2)
        self.assertIs(bounded.get("run_terminates"), True)

        # RUNG 3 - the failure set graded off its own record, buckets routed on
        # this ledger's OWN vocabulary (contract.knowledge, not a borrowed map).
        graded = self._call(
            "run_the_failures",
            {
                "failures_path": FAILURES,
                "input_field": "input",
                "expected_field": "expected",
                "answer_field": "answer",
                "traces_path": TRACES,
            },
            tid,
        )
        self.assertEqual(graded.get("cases"), 12)

        # RUNG 4 - the person's half, in their own person.
        self._call("state_facts", {"facts": PERSON_FACTS}, tid)
        return tid

    def test_traces_tools_failures_and_a_person_reach_a_gated_build_verdict(self):
        tid = self._seed()

        # RUNG 5 - the verdict, and the proof it stands on gates. The empty
        # `facts` object is the schema's required key; everything that matters
        # arrives from the thread's own measured rows.
        diagnosed = self._call("run_diagnosis", {"facts": {}}, tid)
        self.assertEqual(diagnosed.get("outcome"), "BUILD__AGENT_WITH_TOOLS")
        ledger = diagnosed.get("gate_ledger") or {}
        for gate_id in (
            "G0_SOMETHING_TO_MEASURE",
            "G1_FAILURE_RATE_MEASURED",
            "G2_SIMPLE_VERSION_TRIED",
            "G3_FAILURE_REPRODUCES",
            "G4_COST_AND_TERMINATION_BOUNDED",
        ):
            self.assertIn(gate_id, ledger)
        origins = diagnosed.get("fact_origins") or {}
        for stamped in ("has_traces", "tokens_per_run", "tool_count"):
            self.assertIn(stamped, origins)
            self.assertEqual(
                origins[stamped],
                "MEASURED",
                f"{stamped} must arrive from an instrument, never asserted",
            )

        # RUNG 6 - THE LOOP CLOSES. The proposer for this outcome shipped the
        # same day the instruments did; a refusal here would be a regression,
        # not a wall. (This rung used to assert the wall itself -
        # `no_honest_build`, `covered_outcomes` excluding this verdict - and
        # was retired the day `_propose_the_tool_layer_loop` paid it. The
        # first ML journey kept its coverage-gap recording for the same reason
        # this one kept its red test for a day: the gap named where to build.)
        proposal = REGISTRY.call(
            "propose_build",
            {
                "facts": {},
                "traces_path": TRACES,
                "failures_path": FAILURES,
                "input_field": "input",
                "expected_field": "expected",
                "answer_field": "answer",
            },
            actor="user",
            thread_id=tid,
        )
        self.assertTrue(
            proposal.get("ok"),
            f"the tool-layer build refused; the loop no longer closes: {proposal}",
        )
        build = proposal.get("build") or {}
        self.assertEqual(build.get("for_outcome"), "BUILD__AGENT_WITH_TOOLS")
        self.assertTrue(
            proposal.get("approve"), "a plan without a fingerprint cannot be approved"
        )
        self.assertEqual(build.get("id"), "the_tool_layer_loop")
        self.assertEqual(
            [s.get("id") for s in build.get("steps") or []],
            ["rerun", "bound", "recheck"],
            "the build is re-measure, re-bound, re-enter the tree - nothing else",
        )
        self.assertIn("BUILD__AGENT_WITH_TOOLS", sorted(propose.PROPOSERS))

    def test_the_approved_build_executes_and_verifies_clean(self):
        """RUNGS 8-12. The plan becomes a storm, the storm finishes, and the
        contract holds: every step done, judged by the criterion it stated
        before it ran, `deviations` empty.

        This is the half of Phase B that "approve-ready" was not: the build's
        own steps re-stamp this thread's facts (rerun and bound read the same
        fixtures), so the recheck walks a sheet that is CURRENT as of the
        storm - which is the entire difference between a plan and a hope.
        """
        tid = self._seed()
        plan = propose.propose(self._situation())
        declared = storm.declare(plan, thread_id=tid)
        list(storm.run(declared["storm"]))

        attached = storm.attach(declared["storm"])
        self.assertEqual(
            attached.state,
            "done",
            f"storm did not finish cleanly: {attached.as_dict()}",
        )
        self.assertEqual(
            attached.deviations,
            (),
            "the storm deviated from what was approved",
        )
        states = {name: step.state for name, step in attached.steps.items()}
        self.assertEqual(states, {"rerun": "done", "bound": "done", "recheck": "done"})
        self.assertTrue(attached.verification and attached.verification.get("ok"))

        # AND THE WALK'S ANSWER, AFTER THE REFRESH: still gated, still the
        # agent-with-tools verdict - the same answer reached from facts whose
        # origins are now younger than the plan that asked for them.
        after = REGISTRY.call("run_diagnosis", {"facts": {}}, actor="user", thread_id=tid)
        self.assertEqual(after.get("outcome"), "BUILD__AGENT_WITH_TOOLS")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
