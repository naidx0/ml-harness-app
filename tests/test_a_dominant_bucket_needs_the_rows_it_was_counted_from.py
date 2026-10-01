"""A failure bucket is not dominant until you know what it is dominant OF.

## The case, and it is in the database rather than invented

Eval run 51, measured 2026-09-09: `eval_rebuckets` holds 13 `wrong_format`, 5
`wrong_facts` and 2 `wrong_reasoning` - twenty rows - and the run has **47
failing rows**. `S1_GAP_UNDIAGNOSED` asks `sum(failure_histogram.values()) < 20`,
which is an ABSOLUTE floor, so twenty of twenty and twenty of forty-seven answer
it identically. Run 51 cleared it at 43% coverage and `S1_ROUTE_BY_FAILURE_MODE`
routed on the argmax of that twenty.

Worse than a minority, it is a **prefix**: the twenty rebucketed rows are exactly
the first twenty failing rows in row order - `[0, 1, 2, 4, 5, ..., 22]` against
failures spanning 0..49. `read_eval_results` returns twenty failures unless asked
for more, and a person buckets what they were shown. **So the ledger's minimum
and the reader's default are the same number**, and any run with more than
twenty-five failures produces a sub-threshold taxonomy by doing the obvious
thing.

## The number existed and could not be computed on

Both stampers already said it out loud. `run_eval`:

    f"{sum(histogram.values())} of {graded - correct} failing rows of "

and `rebucket_failures` the same shape against `len(failing)`. The denominator
was in the `how` sentence - **prose a reader can see and a condition cannot
divide by**. `failures_seen` is that same number as a fact, stamped beside the
histogram by both instruments so the two cannot disagree about one run, and
`S1_CLASSIFICATION_IS_TOO_THIN` is the node that now divides by it.

## What is NOT claimed here

Not that 0.8 is the right number - it is the registered threshold and this file
asserts the ledger implements the one it declares. And not that historical
threads are re-judged: `failures_seen` defaults to 0, a thread stamped before it
existed has no denominator, and the node deliberately does not fire on one. That
limit is asserted below rather than left to be discovered.
"""

from __future__ import annotations

import unittest

import support

from app import diagnosis
from app.diagnosis import default_spec, diagnose
from app.tools import REGISTRY, evals, evidence

from diagnosis_fixtures import REACHING, attribute

SPEC = default_spec()

#: Run 51's shape: a clear argmax, and twenty rows of it.
RUN_51_BUCKETS = {"wrong_format": 13, "wrong_facts": 5, "wrong_reasoning": 2}
CLASSIFIED = sum(RUN_51_BUCKETS.values())


def walk(*, failures_seen, buckets=None):
    """Diagnose a stage-1 thread carrying this histogram and this denominator."""
    facts = dict(REACHING["ACTION__CLASSIFY_FAILURES"])
    facts.update(
        attribute(
            {
                "failure_histogram": dict(RUN_51_BUCKETS if buckets is None else buckets),
                "failures_seen": failures_seen,
            }
        )
    )
    return diagnose(facts, SPEC)


class APrefixDoesNotNameADominantBucketTest(unittest.TestCase):
    """THE CASE. Same twenty buckets; only the denominator differs."""

    def test_run_51s_shape_refuses_to_route(self):
        got = walk(failures_seen=47)
        self.assertEqual(got.node, "S1_CLASSIFICATION_IS_TOO_THIN")
        self.assertEqual(got.outcome, "ACTION__CLASSIFY_FAILURES")

    def test_the_same_histogram_over_its_own_rows_does_route(self):
        """The control arm differs BY ONE THING. If this also refused, the node
        would be rejecting the histogram rather than its coverage."""
        got = walk(failures_seen=CLASSIFIED)
        self.assertNotEqual(got.node, "S1_CLASSIFICATION_IS_TOO_THIN")

    def test_the_refusal_names_its_remedy(self):
        """A refusal that does not say what to do next is a dead end.

        ASSERTED AGAINST THE LEDGER TEXT, and the first version of this test was
        aimed at the wrong surface: it read `Diagnosis.say` and
        `Diagnosis.proposed_method`, and got `None` and `'UNSET'`. `action:` is
        not loaded by `app/diagnosis.py` at all - `app/asking.py` reads it off
        the raw node - so no field of a `Diagnosis` ever carries it. The
        remedy is a property of the node, so it is checked on the node.
        """
        import yaml

        document = yaml.safe_load(
            (support.REPO_ROOT / "docs" / "diagnosis_engine.yaml").read_text(
                encoding="utf-8"
            )
        )
        found = [
            node
            for stage in document.get("stages", document).values()
            if isinstance(stage, list)
            for node in stage
            if isinstance(node, dict)
            and node.get("node") == "S1_CLASSIFICATION_IS_TOO_THIN"
        ]
        self.assertEqual(len(found), 1, "the node is declared once")
        self.assertIn("read_eval_results", found[0].get("action", ""))


class TheThresholdIsWhereTheLedgerPutsItTest(unittest.TestCase):
    """0.8, inclusive, and asserted on both sides of the line."""

    def test_exactly_the_threshold_is_enough(self):
        #: 20/25 is 0.8 exactly. `< 0.8` is false, so it must NOT refuse.
        self.assertNotEqual(
            walk(failures_seen=25).node, "S1_CLASSIFICATION_IS_TOO_THIN"
        )

    def test_one_row_below_the_threshold_is_not(self):
        #: 20/26 is 0.769.
        self.assertEqual(
            walk(failures_seen=26).node, "S1_CLASSIFICATION_IS_TOO_THIN"
        )

    def test_the_ledger_declares_the_threshold_this_file_asserts(self):
        """Read out of the ledger's own text, so retuning the number fails this
        rather than drifting past it.

        THE FIRST VERSION OF THIS TEST COULD NOT FAIL. It ended
        `self.assertIn("0.8", str(...) or "0.8")`, and `or "0.8"` hands the
        assertion its own expected value whenever the left side is falsy - so it
        asserted `"0.8" in "0.8"`. It is kept named here because a test that
        cannot fail is the fault this whole file exists to catch, one level up.
        """
        import ast

        condition = SPEC.conditions["S1_CLASSIFICATION_IS_TOO_THIN"]
        literals = {
            node.value
            for node in ast.walk(condition)
            if isinstance(node, ast.Constant) and isinstance(node.value, float)
        }
        self.assertIn(0.8, literals, f"the node's float literals are {literals}")


class AThreadWithNoDenominatorRoutesAsItDidTest(unittest.TestCase):
    """THE KNOWN LIMIT, asserted rather than left to be found."""

    def test_a_zero_denominator_does_not_fire_the_node(self):
        """`failures_seen` defaults to 0 on every thread stamped before this
        fact existed. Refusing all of them would be a behaviour change wearing a
        correction's clothes."""
        self.assertNotEqual(
            walk(failures_seen=0).node, "S1_CLASSIFICATION_IS_TOO_THIN"
        )

    def test_the_default_is_what_makes_that_so(self):
        self.assertEqual(SPEC.facts["failures_seen"].get("default"), 0)


class BothInstrumentsStampTheDenominatorTest(unittest.TestCase):
    """Through the harness: the tool is called, and the ledger is read after."""

    def setUp(self):
        self.root = support.sandbox(self)
        self.thread = int(support.conversations(1)[0]["id"])
        self.eval_path = self.root / "eval.jsonl"
        self.eval_path.write_text("", encoding="utf-8")
        self.run = support.a_completed_eval_run(
            self.thread, self.eval_path, rows=20
        )
        self.failing = [
            int(r["row_index"])
            for r in evals.results_for(int(self.run["id"]))
            if not r["correct"]
        ]

    def test_rebucketing_stamps_how_many_failures_there_were(self):
        out = REGISTRY.call(
            "rebucket_failures",
            {
                "run_id": int(self.run["id"]),
                "buckets": {str(self.failing[0]): "wrong_reasoning"},
            },
            actor="user",
            thread_id=self.thread,
        )
        self.assertTrue(out.get("ok"), out)
        sheet, _ = evidence.assemble_facts(self.thread, {}, "user")
        self.assertEqual(sheet["failures_seen"].value, len(self.failing))

    def test_it_is_the_whole_run_and_not_the_rows_that_were_read(self):
        """The bug in one line: re-tallying one row must not report a
        denominator of one."""
        REGISTRY.call(
            "rebucket_failures",
            {
                "run_id": int(self.run["id"]),
                "buckets": {str(self.failing[0]): "wrong_reasoning"},
            },
            actor="user",
            thread_id=self.thread,
        )
        sheet, _ = evidence.assemble_facts(self.thread, {}, "user")
        self.assertGreater(sheet["failures_seen"].value, 1)

    def test_a_run_whose_id_equals_its_failure_count_still_stamps(self):
        """WALL 6, AND THIS WAS A REAL FALSE REFUSAL BEFORE `bounds=("run_id",)`.

        `failures_seen` is a count of rows and `run_id` is an integer argument,
        so when they coincide the wall reads the count as the caller's own
        number handed back. Measured 2026-09-09: a fresh sandbox whose first run
        is id 1, graded over two rows so exactly one fails, raised

            'rebucket_failures' tried to stamp 'failures_seen' MEASURED with 1,
            which is a value it was handed in this call's arguments, as 1

        and took the whole call down with it - a tool broken for every run whose
        id happens to equal its failing-row count. The collision is constructed
        here rather than waited for.
        """
        root = support.sandbox(self)
        thread = int(support.conversations(1)[0]["id"])
        path = root / "collide.jsonl"
        path.write_text("", encoding="utf-8")
        run = support.a_completed_eval_run(thread, path, rows=2)
        run_id = int(run["id"])
        failing = [
            int(r["row_index"])
            for r in evals.results_for(run_id)
            if not r["correct"]
        ]
        self.assertEqual(
            run_id, len(failing), "the fixture no longer produces the collision"
        )
        out = REGISTRY.call(
            "rebucket_failures",
            {"run_id": run_id, "buckets": {str(failing[0]): "wrong_reasoning"}},
            actor="user",
            thread_id=thread,
        )
        self.assertTrue(out.get("ok"), out)

    def test_the_stamp_is_measured_and_not_asserted(self):
        REGISTRY.call(
            "rebucket_failures",
            {
                "run_id": int(self.run["id"]),
                "buckets": {str(self.failing[0]): "wrong_reasoning"},
            },
            actor="user",
            thread_id=self.thread,
        )
        sheet, _ = evidence.assemble_facts(self.thread, {}, "user")
        self.assertEqual(sheet["failures_seen"].origin, diagnosis.MEASURED)


if __name__ == "__main__":
    unittest.main()
