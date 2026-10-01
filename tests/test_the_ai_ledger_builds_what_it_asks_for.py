"""Four AI outcomes that had builds written and never wired, driven to done.

## What was found

`app/tools/propose.py` held three finished proposers - 778 lines carrying their
own refusal arguments - that appeared exactly once each in the module, at their
own `def`. Nothing referenced them. The three predicates written to gate them,
`the_failure_runner_is_registered`, `the_trace_reader_is_registered` and
`the_agent_bucketer_is_registered`, were unreferenced too. The last wire was
never soldered, and four outcomes reported as uncovered while their builds sat
in the file:

    _propose_run_the_failures            -> ACTION__BUILD_AN_EVAL_HARNESS
                                            ACTION__MEASURE_THE_BASELINE
    _propose_read_the_traces             -> BLOCKED__NO_TRACES
    _propose_classify_the_agent_failures -> ACTION__CLASSIFY_THE_FAILURES

Wiring them takes this ledger from 4 of 23 covered to 8 of 23.

## Why registration is not the evidence

**The four entries in `NOT_COVERED` argued AGAINST these builds**, and each
proposer's own docstring already answered the argument its entry was making:
*"the scaffolding build does not yet"* against a build that refuses with the
path it wanted named; *"what is missing is the step that grows the row set"*
against a build that refuses on a measured count below the ledger's floor and
names both numbers; *"the missing half is driving somebody's agent"* against a
build that drives nothing and grades the recording the person made.

Two written arguments in the same file, disagreeing. That is exactly the state
`docs/PHASES.md` records as worse than an incomplete plan, and the only thing
that settles it is driving them - so this file drives all four end to end
rather than asserting they are registered. **Anything that does not hold up
under a driven run comes back out; it does not get its assertion loosened.**

## What "end to end" means here

Propose, declare, run, and read the storm back: every step `done`, the state
`done`, `deviations` empty. The verification is against the exit criterion each
build stated BEFORE it ran, which is the whole difference between a plan and a
hope - and all four of these criteria are `is_measured` on a fact, so a build
that ran and stamped nothing fails its own test rather than passing quietly.
"""

from pathlib import Path
import unittest

from app import diagnosis, storm
from app.tools import REGISTRY, propose

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "agent"
TRACES = str(FIXTURES / "journey-traces.jsonl")
FAILURES = str(FIXTURES / "journey-failures.jsonl")
AI_LEDGER = "docs/ledgers/ai_engineering.yaml"

#: The four, with the paths each one needs and the fact its criterion is held
#: to. Written as a table because the four are the same shape and a copy of
#: the driving code per outcome is four places for a fifth to be forgotten.
THE_FOUR = (
    (
        "ACTION__BUILD_AN_EVAL_HARNESS",
        "build_the_failure_harness",
        "can_rerun_failures",
        {"failures_path": FAILURES},
    ),
    (
        "ACTION__MEASURE_THE_BASELINE",
        "measure_the_failure_rate",
        "failure_rate_measured",
        {"failures_path": FAILURES},
    ),
    (
        "BLOCKED__NO_TRACES",
        "read_the_traces",
        "has_traces",
        {"trace_path": TRACES},
    ),
    (
        "ACTION__CLASSIFY_THE_FAILURES",
        "classify_the_agent_failures",
        "failure_buckets",
        {"trace_path": TRACES, "failures_path": FAILURES},
    ),
)

FIELDS = {"input_field": "input", "expected_field": "expected", "answer_field": "answer"}


class TheyAreRegisteredTest(unittest.TestCase):
    def setUp(self):
        import support

        support.sandbox(self)

    def test_all_four_have_a_proposer(self):
        for outcome, _id, _fact, _paths in THE_FOUR:
            with self.subTest(outcome=outcome):
                self.assertIn(outcome, propose.PROPOSERS)

    def test_all_four_have_a_coverage_sentence(self):
        """A proposer with no sentence beside it is a build nobody can find out
        about without reading Python."""
        for outcome, _id, _fact, _paths in THE_FOUR:
            with self.subTest(outcome=outcome):
                self.assertIn(outcome, propose.COVERAGE)
                self.assertGreater(len(propose.COVERAGE[outcome]), 200)

    def test_none_of_them_is_still_listed_as_a_gap(self):
        """THE HALF THAT WOULD HAVE BEEN EASY TO SKIP. An outcome in both maps
        is the product telling somebody it cannot do the thing it is about to
        offer, and it is the shape these two tables exist to refuse."""
        for outcome, _id, _fact, _paths in THE_FOUR:
            with self.subTest(outcome=outcome):
                self.assertNotIn(outcome, propose.NOT_COVERED)

    def test_each_is_gated_on_the_tools_it_actually_names(self):
        """Not on all four instruments. `BUILD__` outcomes here need the whole
        set because they read traces AND definitions AND re-run AND bound;
        these do not, and gating them on the full set would have made three of
        them unreachable on a machine holding exactly what they need."""
        self.assertTrue(propose.the_failure_runner_is_registered())
        self.assertTrue(propose.the_trace_reader_is_registered())
        self.assertTrue(propose.the_agent_bucketer_is_registered())
        self.assertEqual(
            {"ACTION__BUILD_AN_EVAL_HARNESS", "ACTION__MEASURE_THE_BASELINE"},
            set(propose._PROPOSERS_THE_FAILURE_RUNNER_BRINGS),
        )
        self.assertEqual(
            {"BLOCKED__NO_TRACES"}, set(propose._PROPOSERS_THE_TRACE_READER_BRINGS)
        )
        self.assertEqual(
            {"ACTION__CLASSIFY_THE_FAILURES"},
            set(propose._PROPOSERS_THE_AGENT_BUCKETER_BRINGS),
        )


class TheyDrawARealPlanTest(unittest.TestCase):
    def setUp(self):
        import support

        support.sandbox(self)
        self.ai = diagnosis.spec_at(AI_LEDGER)

    def _situation(self, outcome, paths):
        return propose.Situation(
            outcome=outcome,
            result=diagnosis.diagnose({}, self.ai),
            **paths,
            **FIELDS,
        )

    def test_each_draws_steps_that_end_in_re_entering_the_tree(self):
        """Every one of these is an ACTION or a BLOCKED - "we cannot answer
        until you do this and re-enter" - so a plan that does the work and does
        not walk the tree again has left the person exactly where they were."""
        for outcome, build_id, _fact, paths in THE_FOUR:
            with self.subTest(outcome=outcome):
                build = propose.PROPOSERS[outcome](self._situation(outcome, paths))
                self.assertEqual(build_id, build.id)
                steps = [step.id for step in build.steps]
                self.assertGreaterEqual(len(steps), 2)
                self.assertEqual("recheck", steps[-1])
                self.assertEqual("run_diagnosis", build.steps[-1].tool)

    def test_each_criterion_is_a_reading_and_names_its_own_fact(self):
        """`is_measured` on the fact the outcome is blocked on. A criterion
        that compared a VALUE would be this build promising what the number
        will be, which is the one thing a plan may not do."""
        for outcome, _id, fact, paths in THE_FOUR:
            with self.subTest(outcome=outcome):
                build = propose.PROPOSERS[outcome](self._situation(outcome, paths))
                criterion = build.exit_criterion
                self.assertEqual("is_measured", criterion.comparator)
                self.assertEqual(f"fact_origins.{fact}", criterion.subject)
                self.assertIn(fact, criterion.stated)

    def test_the_two_that_share_a_proposer_are_held_to_different_facts(self):
        """One proposer, two outcomes, and the difference is the thing the
        person is owed a sentence about: one is waiting to learn the failures
        CAN be re-run, the other for the number that comes out when they are."""
        harness = propose.PROPOSERS["ACTION__BUILD_AN_EVAL_HARNESS"](
            self._situation("ACTION__BUILD_AN_EVAL_HARNESS", {"failures_path": FAILURES})
        )
        rate = propose.PROPOSERS["ACTION__MEASURE_THE_BASELINE"](
            self._situation("ACTION__MEASURE_THE_BASELINE", {"failures_path": FAILURES})
        )
        self.assertNotEqual(harness.id, rate.id)
        self.assertNotEqual(harness.exit_criterion.subject, rate.exit_criterion.subject)


class TheyRefuseRatherThanGuessTest(unittest.TestCase):
    """The half that makes them safe to register. Each was written to refuse
    on a missing path rather than fill one in, and a refusal nobody has driven
    is a refusal nobody knows the shape of."""

    def setUp(self):
        import support

        support.sandbox(self)
        self.ai = diagnosis.spec_at(AI_LEDGER)

    def _bare(self, outcome):
        return propose.Situation(outcome=outcome, result=diagnosis.diagnose({}, self.ai))

    def test_no_traces_refuses_without_a_path_and_says_which(self):
        """This outcome has two populations. Somebody whose system records
        nothing needs an exporter line in code this harness does not own;
        somebody with a directory of traces needs one read. Which one they are
        is decided by whether they can name a file."""
        with self.assertRaises(propose.NotEnoughToPropose) as caught:
            propose.PROPOSERS["BLOCKED__NO_TRACES"](self._bare("BLOCKED__NO_TRACES"))
        self.assertIn("trace_path", str(caught.exception))

    def test_the_bucketer_refuses_without_a_path_too(self):
        with self.assertRaises(propose.NotEnoughToPropose):
            propose.PROPOSERS["ACTION__CLASSIFY_THE_FAILURES"](
                self._bare("ACTION__CLASSIFY_THE_FAILURES")
            )

    def test_the_failure_runner_refuses_without_the_failure_file(self):
        with self.assertRaises(propose.NotEnoughToPropose):
            propose.PROPOSERS["ACTION__BUILD_AN_EVAL_HARNESS"](
                self._bare("ACTION__BUILD_AN_EVAL_HARNESS")
            )


class TheyExecuteAndVerifyCleanTest(unittest.TestCase):
    """THE ACCEPTANCE. Propose, declare, run, read back: every step done, the
    state done, deviations empty - judged against the criterion each build
    stated before it ran."""

    def setUp(self):
        import support

        support.sandbox(self)
        self.ai = diagnosis.spec_at(AI_LEDGER)

    def _thread(self):
        """ON THE AI LEDGER, and the default would have been wrong in a way
        worth recording: `create_thread` defaults to `diagnosis.DEFAULT_LEDGER`,
        which is the ML one, and the first driven run of this file failed at
        step 2 of all four builds with the instruments refusing - *"this tool is
        not refusing because the product cannot do the work, it is refusing
        because the work belongs to a different domain's knowledge."* That is
        migration v011 and wall 5 working exactly as designed, caught by driving
        rather than by reading, and it is the reason this file exists in this
        shape."""
        from app import events

        return events.create_thread(title="an agent that fails", ledger=AI_LEDGER)["id"]

    def _drive(self, outcome, paths):
        thread_id = self._thread()
        situation = propose.Situation(
            outcome=outcome,
            result=diagnosis.diagnose({}, self.ai),
            **paths,
            **FIELDS,
        )
        plan = propose.PROPOSERS[outcome](situation)
        declared = storm.declare(plan, thread_id=thread_id)
        list(storm.run(declared["storm"]))
        return storm.attach(declared["storm"])

    def test_all_four_run_to_done_with_no_deviations(self):
        for outcome, _id, _fact, paths in THE_FOUR:
            with self.subTest(outcome=outcome):
                finished = self._drive(outcome, paths)
                self.assertEqual(
                    "done",
                    finished.state,
                    f"{outcome} did not finish cleanly: {finished.as_dict()}",
                )
                self.assertEqual(
                    (),
                    finished.deviations,
                    f"{outcome} deviated from what was approved",
                )

    def test_every_step_of_every_build_reports_done(self):
        """A storm whose state is done over a step that is not is the shape
        `docs/PHASES.md` records under 'an assertion about a comparison's
        INPUTS is not an assertion about its RESULT'."""
        for outcome, _id, _fact, paths in THE_FOUR:
            with self.subTest(outcome=outcome):
                finished = self._drive(outcome, paths)
                states = [step.get("state") for step in finished.as_dict()["steps"]]
                self.assertTrue(
                    all(state == "done" for state in states),
                    f"{outcome} left steps unfinished: {states}",
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
