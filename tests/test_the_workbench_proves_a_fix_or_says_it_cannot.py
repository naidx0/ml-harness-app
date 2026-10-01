"""Six cheap refusals get somewhere to go, and the destination is a paired test.

## The gap this closes, in the ledger's own words

`docs/ledgers/ai_engineering.yaml` reaches six outcomes more often than any
others, and every one of them names a fix that costs an afternoon:

    NO_TOOLS__DESCRIPTION_IS_THE_BUG   the descriptions your tools declare
    NO_TOOLS__PROMPT_IS_THE_BUG        the instructions your agent runs under
    NO_AGENT__CONSTRAIN_THE_OUTPUT     the schema the output has to satisfy
    NO_AGENT__FIX_THE_TOOL             the tool that is returning wrong answers
    NO_AGENT__FIX_THE_CONTEXT          what the agent is given to work from
    NO_AGENT__ONE_API_CALL             the loop that did not need to be a loop

**A cheap fix is only worth naming if the person can find out whether it
worked**, and until this build there was nowhere for them to find out. The
product said "the tool description is the bug", and then stopped. That is a
diagnosis with no follow-through, which is the thing `docs/PHASES.md` calls the
workbench gap: *what is missing is the step that turns a verdict into an edit
and re-measures it.*

## Why this could not be built before the migration

`propose.NOT_COVERED` had all six, and its entry said so precisely:

    "the paired proof is designed (change description, re-run same rows,
     McNemar) and half-built: run_the_failures grades leg one today. The owed
     piece is the compare step wired to evals.compare over two recordings."

`app/tools/agents.py` wrote nothing to the database at all. A rate was stamped
on the ledger and the rows behind it were dropped, so there was no first
recording for a second to be compared against. `v012` gives a run its cases and
`read_agent_results` compares two of them; this file is what shows the two
halves reach a person as one answer.

## What the build does NOT do, on purpose

**It does not make the change.** The 'after' leg grades a file the person
produced by running their own changed agent, and `_propose_prove_the_fix`
refuses - by name, on `after_answers_path` - rather than inventing one. This
harness never drives somebody's agent, and a build that wrote the fix would be
this product guessing at a system it has never seen.

## What the criterion promises, and what it deliberately does not

The build's exit criterion is that a verdict EXISTS, not that the verdict is
favourable. **NO EVIDENCE is a successful outcome of this build.** A plan held
to its own preferred result is a plan with a thumb on the scale, and the whole
reason the comparison is McNemar rather than a subtraction is to be able to say
"these failures cannot tell the two apart" out loud.

`TheVerdictIsEarnedRatherThanAssumedTest` drives both: a real improvement over
twelve cases returns `different`, and an 'after' file identical to the 'before'
returns `no_evidence` from the same build with the same criterion, both `done`.

## The three declarations this build needed, and where each one lives

Driving it found all three, and none of them would have been found by reading:

1. `run_the_failures` takes THREE arguments that can name a file, so nothing
   could tell which one it opens. It now declares `subject=("failures_path",)`
   - see `app/build.py::declared_subject_arguments`, which had specified that
   field and been waiting for the registry to grow it.
2. The 'compare' step declares `operates_on=None`, because it opens no file at
   all: it reads two rows out of this conversation's database.
3. Both run ids reach the comparison as `Ref`s from the legs that wrote them.
   A row id is decided at insert time, so a plan naming one would be naming a
   row that does not exist yet.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from app import diagnosis, events, storm
from app.tools import propose

HERE = Path(__file__).resolve().parent
FAILURES = str(HERE / "fixtures" / "agent" / "journey-failures.jsonl")
AI_LEDGER = "docs/ledgers/ai_engineering.yaml"

FIELDS = {"input_field": "input", "expected_field": "expected", "answer_field": "answer"}

#: Every outcome the workbench answers, with the build id each one draws. A
#: table rather than one representative, because these six are the product's
#: most-reached answers and "the other five presumably work the same way" is
#: the sentence that leaves one of them broken.
THE_SIX = (
    ("NO_TOOLS__DESCRIPTION_IS_THE_BUG", "prove_the_description_change"),
    ("NO_TOOLS__PROMPT_IS_THE_BUG", "prove_the_prompt_change"),
    ("NO_AGENT__CONSTRAIN_THE_OUTPUT", "prove_the_constraint"),
    ("NO_AGENT__FIX_THE_TOOL", "prove_the_tool_fix"),
    ("NO_AGENT__FIX_THE_CONTEXT", "prove_the_context_change"),
    ("NO_AGENT__ONE_API_CALL", "prove_the_simple_version"),
)


def _rows() -> list[dict]:
    return [
        json.loads(line)
        for line in Path(FAILURES).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class _Driving(unittest.TestCase):
    """The shared rig: a sandbox, the AI ledger, and an 'after' file written
    from the fixture so the improvement in it is one this file put there."""

    def setUp(self):
        import support

        support.sandbox(self)
        self.ai = diagnosis.spec_at(AI_LEDGER)
        self.workspace = Path(self.sandbox_dir) if hasattr(self, "sandbox_dir") else None

    def _after_file(self, fixed: int) -> str:
        """A recording of the same questions with `fixed` of them now right.

        The same INPUT and the same EXPECTED on every row, because that pair is
        the case key: an 'after' file whose questions differed would be a
        different question set and the comparison would refuse it, which is
        `TheComparisonRefusesTwoDifferentQuestionSetsTest`.
        """
        rows = _rows()
        for row in rows[:fixed]:
            row["answer"] = row["expected"]
        path = Path(self.enterContext(_tmpdir())) / f"after-{fixed}.jsonl"
        path.write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
        )
        return str(path)

    def _situation(self, outcome: str, **extra) -> propose.Situation:
        return propose.Situation(
            outcome=outcome,
            result=diagnosis.diagnose({}, self.ai),
            failures_path=FAILURES,
            **FIELDS,
            **extra,
        )

    def _drive(self, outcome: str, after: str):
        """Propose, declare, run, read back - on a thread of the AI ledger.

        The ledger is named because the default is the ML one and every
        instrument in this build would refuse there, by domain, which is
        migration v011 doing its job.
        """
        thread_id = events.create_thread(title="a fix to prove", ledger=AI_LEDGER)["id"]
        plan = propose.PROPOSERS[outcome](
            self._situation(outcome, after_answers_path=after)
        )
        declared = storm.declare(plan, thread_id=thread_id)
        list(storm.run(declared["storm"]))
        return plan, storm.attach(declared["storm"])


def _tmpdir():
    import tempfile

    return tempfile.TemporaryDirectory()


class TheSixAreCoveredTest(_Driving):
    def test_each_has_a_proposer(self):
        for outcome, _id in THE_SIX:
            with self.subTest(outcome=outcome):
                self.assertIn(outcome, propose.PROPOSERS)

    def test_none_is_still_listed_as_a_gap(self):
        """An outcome in `PROPOSERS` and `NOT_COVERED` at once is the product
        explaining it cannot do the thing it is about to offer."""
        for outcome, _id in THE_SIX:
            with self.subTest(outcome=outcome):
                self.assertNotIn(outcome, propose.NOT_COVERED)

    def test_each_has_a_coverage_sentence_a_person_can_read(self):
        for outcome, _id in THE_SIX:
            with self.subTest(outcome=outcome):
                self.assertIn(outcome, propose.COVERAGE)
                self.assertGreater(len(propose.COVERAGE[outcome]), 100)

    def test_the_comparison_tool_is_what_gates_them(self):
        """Gated on the paired reader being registered, not on the failure
        runner alone: leg one has existed for weeks and was never the missing
        piece."""
        self.assertTrue(propose.the_paired_proof_is_possible())
        self.assertEqual(
            {outcome for outcome, _id in THE_SIX},
            set(propose._PROPOSERS_THE_PAIRED_PROOF_BRINGS),
        )

    def test_each_draws_its_own_build_rather_than_one_generic_one(self):
        """Six outcomes through one proposer, and the id and the sentence
        differ per outcome. A build that told all six people to change 'the
        thing that is wrong' would be a diagnosis thrown away at the last
        step."""
        after = self._after_file(fixed=1)
        seen = set()
        for outcome, build_id in THE_SIX:
            with self.subTest(outcome=outcome):
                plan = propose.PROPOSERS[outcome](
                    self._situation(outcome, after_answers_path=after)
                )
                self.assertEqual(build_id, plan.id)
                self.assertNotIn(plan.because, seen)
                seen.add(plan.because)


class ItRefusesToInventTheFixTest(_Driving):
    """The half that makes the other half safe. This harness never runs
    somebody's agent, so the 'after' recording is theirs to produce."""

    def test_it_refuses_without_the_after_file_and_names_it(self):
        for outcome, _id in THE_SIX:
            with self.subTest(outcome=outcome):
                with self.assertRaises(propose.NotEnoughToPropose) as caught:
                    propose.PROPOSERS[outcome](self._situation(outcome))
                self.assertIn("after_answers_path", str(caught.exception))
                self.assertIn("after_answers_path", caught.exception.needs)

    def test_it_refuses_without_the_failure_set(self):
        """No failures means no questions, and a comparison over no shared
        questions is not a comparison."""
        for outcome, _id in THE_SIX[:1]:
            with self.assertRaises(propose.NotEnoughToPropose):
                propose.PROPOSERS[outcome](
                    propose.Situation(
                        outcome=outcome,
                        result=diagnosis.diagnose({}, self.ai),
                        after_answers_path=self._after_file(fixed=1),
                        **FIELDS,
                    )
                )

    def test_it_refuses_without_knowing_which_columns_to_grade(self):
        with self.assertRaises(propose.NotEnoughToPropose) as caught:
            propose.PROPOSERS["NO_TOOLS__PROMPT_IS_THE_BUG"](
                propose.Situation(
                    outcome="NO_TOOLS__PROMPT_IS_THE_BUG",
                    result=diagnosis.diagnose({}, self.ai),
                    failures_path=FAILURES,
                    after_answers_path=self._after_file(fixed=1),
                )
            )
        self.assertIn("expected_field", str(caught.exception))


class TheBuildSaysWhatItWillDoBeforeItDoesItTest(_Driving):
    def setUp(self):
        super().setUp()
        self.plan = propose.PROPOSERS["NO_TOOLS__DESCRIPTION_IS_THE_BUG"](
            self._situation(
                "NO_TOOLS__DESCRIPTION_IS_THE_BUG",
                after_answers_path=self._after_file(fixed=9),
            )
        )

    def test_the_shape_is_attach_before_after_compare_recheck(self):
        self.assertEqual(
            ["attach", "before", "after", "compare", "recheck"],
            [step.id for step in self.plan.steps],
        )

    def test_both_legs_grade_the_same_questions(self):
        """The whole arrangement. Same failure set, same grader, same columns,
        two answer files - and a build that pointed the two legs at two
        question sets would be reporting the difference between two subjects."""
        before, after = self.plan.steps[1], self.plan.steps[2]
        self.assertEqual(before.arguments["failures_path"], after.arguments["failures_path"])
        self.assertNotEqual(before.arguments["answers_path"], after.arguments["answers_path"])
        for field, value in FIELDS.items():
            self.assertEqual(value, before.arguments[field])
            self.assertEqual(value, after.arguments[field])

    def test_the_two_legs_are_labelled_so_the_comparison_can_be_read(self):
        self.assertEqual("before", self.plan.steps[1].arguments["label"])
        self.assertEqual("after", self.plan.steps[2].arguments["label"])

    def test_both_legs_are_costed_from_the_failure_set_they_open(self):
        """THE DECLARATION THAT DRIVING FOUND. `run_the_failures` takes three
        arguments that can name a file, so before it declared `subject=` the
        validator could not tell which one a step would open and refused the
        'after' leg outright. Both legs are costed from the questions, because
        the number of questions is what the work is proportional to."""
        from app.build import Subject

        wanted = Subject.of_path(FAILURES).key
        for step in (self.plan.steps[1], self.plan.steps[2]):
            self.assertIsNotNone(step.operates_on)
            self.assertEqual(wanted, step.operates_on.key)

    def test_the_comparison_declares_that_it_opens_nothing(self):
        """It reads two rows out of this conversation's database. Naming a file
        here would be a step declaring a subject it will never open, which is
        exactly what `Build._validate_subject` exists to catch."""
        compare = self.plan.steps[3]
        self.assertIsNone(compare.operates_on)

    def test_both_run_ids_come_from_the_steps_that_wrote_them(self):
        compare = self.plan.steps[3]
        self.assertEqual("after", compare.arguments["run_id"].step)
        self.assertEqual("before", compare.arguments["against"].step)
        self.assertEqual(("before", "after"), compare.needs)

    def test_the_criterion_asks_for_a_verdict_and_never_for_a_good_one(self):
        """The one line that keeps this build honest. `exists` on `verdict`,
        not `is_true` on `resolved` and not a floor on `delta`."""
        criterion = self.plan.exit_criterion
        self.assertEqual("verdict", criterion.subject)
        self.assertEqual("exists", criterion.comparator)
        self.assertIn("NO EVIDENCE", criterion.stated)

    def test_it_ends_by_walking_the_tree_again(self):
        self.assertEqual("recheck", self.plan.steps[-1].id)
        self.assertEqual("run_diagnosis", self.plan.steps[-1].tool)

    def test_it_asks_the_person_to_change_something_specific(self):
        """Six outcomes, six sentences naming the thing to change. 'Change what
        is wrong' is a horoscope."""
        self.assertIn("description", self.plan.steps[2].why.lower())


class TheyExecuteAndVerifyCleanTest(_Driving):
    """THE ACCEPTANCE. All six proposed, declared, run and read back."""

    def test_all_six_run_to_done_with_no_deviations(self):
        after = self._after_file(fixed=9)
        for outcome, _id in THE_SIX:
            with self.subTest(outcome=outcome):
                _plan, finished = self._drive(outcome, after)
                self.assertEqual(
                    "done", finished.state, f"{outcome}: {finished.as_dict()}"
                )
                self.assertEqual((), finished.deviations)

    def test_every_step_of_every_build_reports_done(self):
        after = self._after_file(fixed=9)
        for outcome, _id in THE_SIX:
            with self.subTest(outcome=outcome):
                _plan, finished = self._drive(outcome, after)
                states = [step.get("state") for step in finished.as_dict()["steps"]]
                self.assertTrue(
                    all(state == "done" for state in states),
                    f"{outcome} left steps unfinished: {states}",
                )


class TheVerdictIsEarnedRatherThanAssumedTest(_Driving):
    """The point of the whole build: the answer depends on what happened.

    Two runs of the SAME build with the SAME criterion, differing only in the
    'after' file, and they must return different verdicts. A build that said
    'different' either way would be a ceremony.
    """

    def _verdict(self, after: str) -> dict:
        _plan, finished = self._drive("NO_TOOLS__DESCRIPTION_IS_THE_BUG", after)
        self.assertEqual("done", finished.state, finished.as_dict())
        compare = [
            step for step in finished.as_dict()["steps"] if step["id"] == "compare"
        ][0]
        return compare["outputs"]

    def test_a_real_improvement_is_called_different(self):
        """Nine of twelve cases fixed, none regressed. McNemar's exact test on
        9 versus 0 is p < 0.005, which is a difference these failures CAN
        establish."""
        outputs = self._verdict(self._after_file(fixed=9))
        self.assertEqual("different", outputs["verdict"])
        self.assertAlmostEqual(0.75, outputs["delta"], places=6)

    def test_a_change_that_moved_nothing_is_called_no_evidence(self):
        """The same build, the same criterion, an 'after' file identical to the
        'before' - and the storm still finishes `done`, because the build
        promised an ANSWER and not a favourable one."""
        outputs = self._verdict(self._after_file(fixed=0))
        self.assertEqual("no_evidence", outputs["verdict"])
        self.assertEqual(0.0, outputs["delta"])

    def test_one_fixed_case_out_of_twelve_is_not_enough_to_resolve(self):
        """The failure this whole design exists to prevent: a delta of +8.3%
        reported as an improvement. One case changing gives McNemar p = 1.0,
        and the honest answer is that twelve failures cannot tell the two
        apart - go and write down more."""
        outputs = self._verdict(self._after_file(fixed=1))
        self.assertEqual("no_evidence", outputs["verdict"])
        self.assertGreater(outputs["delta"], 0.0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
