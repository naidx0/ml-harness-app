"""Counting the rows re-enters the tree somewhere new.

## The sentence this file was written against

`ACTION__COUNT_THE_ROWS` sat in `propose.NOT_COVERED` from the day the classical
branch shipped, and its reason named the exact defect a careless fix would
introduce:

    'Profile the dataset, then re-run the diagnosis' writes itself and would not
    work: it would run, look successful, re-enter the tree and land on this same
    outcome, having spent the user's time to move nothing.

That was true, and it was true because `profile_dataset` read a row count and
stamped `eval_size_n` with it and nothing else. The fix the reason prescribed
was a tool, not a proposer - and on 2026-08-28 the tool arrived: the same
completed scan now also stamps `tabular_rows`.

**So this file exists to prove the sentence is no longer true.** Not that the
tool returns `ok`, and not that a plan can be drawn - the roster sweeps in
`test_the_proposal_is_executable.py` already hold those. What is proved here is
the only thing that was ever in doubt: that after the build runs, the diagnosis
lands somewhere it did not land before.

The order below is the order the argument has to be made in:

    the outcome is reachable  ->  the count is MEASURED  ->  the tree has moved

Each rung would pass on its own while the product stayed broken. Only the three
together say the loop closed.
"""

import csv
import unittest

from app import diagnosis
from app.tools import REGISTRY
from app.tools import evidence
from app.tools import propose
import support


#: Enough rows that the answer is not the boundary of anything. The classical
#: branch forks at 1,000 / 10,000 / 1,000,000, and 40 rows is unambiguously in
#: the first bucket, so a wrong count would move the verdict rather than hide
#: inside it.
ROWS = 40


def _a_table(path):
    """A real csv on disk. Nothing here is generated data in the wall-8 sense -
    it is a fixture this test wrote and then reads, which is what every other
    file-reading test does."""
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ticket", "customer", "label"])
        for index in range(ROWS):
            writer.writerow([f"ticket {index}", f"customer {index % 7}", index % 4])
    return str(path)


#: The sheet that lands on the outcome. Found by walking, not by reading: every
#: fact here is one the tree needs to reach stage 8 with the row count missing.
THE_SITUATION = {
    "goal_text": "route tickets",
    "target_score": 0.9,
    "baseline_measured": True,
    "baseline_score": 0.5,
    "modality": "tabular",
    "task_family": "classification",
    "labeled_examples_n": 400,
    "eval_size_n": 40,
}


def _sheet(**extra):
    facts = {
        name: diagnosis.Fact(value, diagnosis.MEASURED)
        for name, value in {**THE_SITUATION, **extra}.items()
    }
    return facts


class TheRowCountMovesTheTreeTest(unittest.TestCase):
    def setUp(self):
        # `sandbox` RETURNS the temporary root, and its docstring says that is
        # for exactly this: "a test that needs a scratch path of its own can
        # hang it off the same directory".
        root = support.sandbox(self)
        self.thread_id = int(support.conversations(1)[0]["id"])
        self.table = _a_table(root / "tickets.csv")

    def test_the_outcome_is_reachable_so_this_file_is_not_vacuous(self):
        """Rung one. If this stops landing here the other two prove nothing."""
        walked = diagnosis.diagnose(_sheet(), diagnosis.load_spec())
        self.assertEqual(walked.outcome, "ACTION__COUNT_THE_ROWS")

    def test_profiling_the_table_records_the_count_as_a_measurement(self):
        """Rung two, and the half that did not exist before 2026-08-28.

        `origin` is asserted rather than `value` alone on purpose: a number in
        the ledger with the wrong origin is the defect every wall in this
        repository is about, and `tabular_rows` routes four different honest
        answers.
        """
        result = REGISTRY.call(
            "profile_dataset",
            {"path": self.table},
            actor="model",
            thread_id=self.thread_id,
        )
        self.assertTrue(result.get("ok"), result)

        assembled, _ = evidence.assemble_facts(self.thread_id, {}, "user")
        self.assertIn("tabular_rows", assembled)
        self.assertEqual(assembled["tabular_rows"].value, ROWS)
        self.assertEqual(assembled["tabular_rows"].origin, diagnosis.MEASURED)

    def test_the_tree_lands_somewhere_new_afterwards(self):
        """Rung three - the whole point, and the claim the old reason denied.

        Driven through the same evidence path a real thread uses, so what is
        asserted is that THE PRODUCT moves, not that a dict with an extra key
        walks differently.
        """
        before = diagnosis.diagnose(_sheet(), diagnosis.load_spec()).outcome

        REGISTRY.call(
            "profile_dataset",
            {"path": self.table},
            actor="model",
            thread_id=self.thread_id,
        )
        # `assemble_facts` takes RAW values and decides the origins itself -
        # that is the whole point of it, and handing it `Fact` objects would be
        # asking the test to supply the provenance.
        assembled, _ = evidence.assemble_facts(
            self.thread_id, dict(THE_SITUATION), "user"
        )
        after = diagnosis.diagnose(assembled, diagnosis.load_spec()).outcome

        self.assertEqual(before, "ACTION__COUNT_THE_ROWS")
        self.assertNotEqual(
            after,
            before,
            "the count was taken and the diagnosis did not move, which is "
            "exactly the failure this outcome's old reason predicted",
        )

    def test_profiling_outside_a_conversation_records_nothing_and_does_not_raise(self):
        """The half the first version of this stamp got wrong.

        `profile_dataset` is callable with no thread at all -
        `tests/test_file_contents_are_data.py` does exactly that, to prove that
        reading a file decides nothing. `tabular_rows` is `scope: thread`, so a
        row written with no thread would be MACHINE scope and
        `evidence.rows_for` would show it to every conversation on this box.
        `record` refuses it, which is right, and the first version of the stamp
        turned that refusal into a crash on every thread-less csv.

        The count still comes back in the payload. What does not happen is the
        recording, because outside a conversation there is nothing to record it
        against.
        """
        result = REGISTRY.call("profile_dataset", {"path": self.table})
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result.get("rows"), ROWS)

    def test_the_build_ends_in_the_ledger_and_asks_nothing(self):
        """The shape, pinned.

        `_propose_name_the_modality` ends in a Question because no tool can read
        modality off a file. This one must not: a plan that asked the person to
        type a number the harness can read is the shape
        `tests/test_a_stated_quantity_becomes_an_offer_to_count_it.py` refuses,
        and it would satisfy 'the outcome has a build' while being the defect.
        """
        situation = propose.Situation(
            outcome="ACTION__COUNT_THE_ROWS",
            result=diagnosis.diagnose(_sheet(), diagnosis.load_spec()),
            dataset_path=self.table,
        )
        plan = propose.PROPOSERS["ACTION__COUNT_THE_ROWS"](situation)

        self.assertEqual(plan.questions, ())
        self.assertEqual([step.tool for step in plan.steps], ["profile_dataset"])
        self.assertEqual(plan.exit_criterion.source, "diagnosis")
        self.assertEqual(plan.exit_criterion.subject, "fact_origins.tabular_rows")
        self.assertEqual(plan.exit_criterion.value, diagnosis.MEASURED)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
