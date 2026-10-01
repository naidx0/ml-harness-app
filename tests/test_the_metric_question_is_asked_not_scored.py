"""The metric outcome asks, and scores nothing - which is the harder half.

## The trap, named by the entry this build replaced

`ACTION__MAKE_THE_METRIC_PROGRAMMATIC` sat in `propose.NOT_COVERED` with a reason
that got its own remedy right and its own diagnosis wrong. The right half:

    run_eval's exact_match and contains ARE programmatic metrics, which makes
    this look coverable and is the trap - grading with one says nothing about
    whether the score the person cares about can be computed without them.

That is the whole design constraint. A build here that ran `run_eval` and
reported 61% would be answering a different question loudly, and it would look
like progress.

The wrong half was the sentence beside it - *"there is no door for the answer"*.
Measured on 2026-08-28: origins are checked at GATES and nowhere else
(`_challenged_facts` is called from `_evaluate_gate` alone), so a STATED value
enters and routes. The door was open; nobody had drawn the question.

## The pair this file completes

| fact | shape | why |
|---|---|---|
| `tabular_rows` | count it | a row count is not a judgement |
| `metric_is_programmatic` | **ask** | whether a rule captures YOUR notion of right is yours |

`tests/test_the_row_count_moves_the_tree.py` holds the other one. Together they
are the rule: **ask only what cannot be looked at.** Getting this backwards in
either direction is a real defect - a build that asks for a number the harness
could read is the shape
`tests/test_a_stated_quantity_becomes_an_offer_to_count_it.py` refuses, and a
build that scores its way past a judgement is this file's trap.
"""

import unittest

from app import diagnosis
from app.tools import propose
import diagnosis_fixtures
import support


OUTCOME = "ACTION__MAKE_THE_METRIC_PROGRAMMATIC"


def _sheet(**over):
    """The minting sheet with the metric turned off.

    Built from `diagnosis_fixtures.MINTING["TRAIN__LORA_SFT"]` rather than by
    hand, because a sheet assembled to reach one node is a sheet that stops
    proving anything the day the node above it changes. This one is the fully
    gated situation with exactly two facts flipped, so what it demonstrates is
    that the metric question is what stands between a person and the prompt
    optimiser - not that some invented sheet lands somewhere.
    """
    sheet = dict(diagnosis_fixtures.MINTING["TRAIN__LORA_SFT"])
    sheet["failure_histogram"] = diagnosis.measured({"wrong_style": 30})
    sheet["metric_is_programmatic"] = diagnosis.measured(False)
    sheet["prompt_optimizer_tried"] = diagnosis.stated(False)
    sheet.update(over)
    return sheet


class TheMetricQuestionIsAskedNotScoredTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        self.eval_path = str(self.root / "eval.jsonl")
        with open(self.eval_path, "w", encoding="utf-8") as handle:
            for index in range(10):
                handle.write(
                    '{"q": "ticket %d", "a": "a paragraph a person has to read"}\n'
                    % index
                )

    def _plan(self):
        return propose.PROPOSERS[OUTCOME](
            propose.Situation(
                outcome=OUTCOME,
                result=diagnosis.diagnose(_sheet()),
                eval_path=self.eval_path,
                input_field="q",
                expected_field="a",
            )
        )

    def test_the_outcome_is_reachable_so_this_file_is_not_vacuous(self):
        self.assertEqual(diagnosis.diagnose(_sheet()).outcome, OUTCOME)

    def test_answering_it_moves_the_tree_to_the_prompt_optimiser(self):
        """The re-entry proof, and the reason the answer is worth collecting.

        A STATED answer is enough - which is the correction this build rests on.
        If this ever stops being true the build's exit criterion is a promise
        the ledger will not keep.
        """
        before = diagnosis.diagnose(_sheet()).outcome
        after = diagnosis.diagnose(
            _sheet(metric_is_programmatic=diagnosis.stated(True))
        ).outcome

        self.assertEqual(before, OUTCOME)
        self.assertEqual(after, "NO_TRAIN__PROMPT_OPTIMIZER")

    def test_the_build_scores_nothing(self):
        """THE TRAP, PINNED. Not "it has one step" - which tools specifically.

        `run_eval`, `measure_baseline` and `try_prompt` are the three tools in
        this harness that send an eval set to a model and grade what comes back.
        Any of them here would produce a number, and the number would not be an
        answer to the question this outcome asks. Asserting on the roster rather
        than on a count is what makes this catch a future step that scores.
        """
        plan = self._plan()
        scoring = {"run_eval", "measure_baseline", "try_prompt"}
        self.assertEqual(
            {step.tool for step in plan.steps} & scoring,
            set(),
            "a step here scores the eval set, which answers a different question",
        )
        self.assertEqual([step.tool for step in plan.steps], ["preview_dataset_rows"])

    def test_the_build_asks_the_person_and_says_why(self):
        """It ends in a Question on the fact, and the criterion reads the ledger."""
        plan = self._plan()

        self.assertEqual([q.fact for q in plan.questions], ["metric_is_programmatic"])
        self.assertEqual(plan.exit_criterion.source, "diagnosis")
        self.assertEqual(
            plan.exit_criterion.subject, "fact_origins.metric_is_programmatic"
        )
        self.assertEqual(plan.exit_criterion.value, diagnosis.STATED)

    def test_the_question_names_the_field_the_person_will_be_looking_at(self):
        """Small, and the difference between a card somebody can answer and one
        that makes them go and find out what it means."""
        plan = self._plan()
        self.assertIn("`a`", plan.questions[0].ask)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
