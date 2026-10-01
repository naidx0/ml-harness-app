"""The person's reading of their own failures can be counted.

## The dead end this opens, and why it was a real one

`ACTION__RE_BUCKET_THE_FAILURES` had every route out shut, and its own reason
said so with unusual precision:

    failure_histogram is declared source: derive, which admits MEASURED and
    nothing else, so a histogram the person corrected cannot enter the ledger at
    all. The only tool that can measure it, run_eval, buckets by fixed rules and
    never by a model, so re-running it reproduces the identical buckets… And
    asking instead of running is closed too: Build.validate refuses a question
    about a fact a registered tool measures, and run_eval measures this one.
    Every route is shut, in the right direction, for a reason each part of the
    product is individually correct about.

This is the only true dead end the 2026-08-28 sweep found - the others turned
out to be facts whose STATED value routes fine at a node, because origins are
checked at gates and nowhere else. This one is different: `failure_histogram` is
`source: derive`, a MEASURED value is the only kind that counts anywhere, and
the one instrument that could produce it is deterministic.

## Why a second instrument is the answer, and why it is honestly a measurement

The tension the code argues both ways on: *a person correcting their own
judgement is not a measurement*, against *a re-tally over rows the tool read
is*. Both are true of different halves, and the split is the same one
`carve_eval_set` already ships - the person says which column holds the answer,
the harness counts the rows.

So `rebucket_failures` measures the COUNT. The buckets are the person's, and the
reply says so in `whose_judgement` rather than letting the number imply
otherwise. That is the same shape every provenance decision in this product
takes: not "who is right", but "who said what, and which part of it did we
check".

## What this file holds

The three refusals are as load-bearing as the tally. A histogram whose keys the
router cannot route makes `S1_ROUTE_BY_FAILURE_MODE` RAISE - the ledger names
that as a known gap in `uninspectable_facts.one_known_gap` - and the sum of this
histogram is what stage 1 reads to decide whether there is anything to diagnose
at all. So a bucket that is not routable, a row that is not in the run, and a
row that PASSED are each refused before anything is recorded.
"""

import unittest

from app import diagnosis
from app.tools import REGISTRY
from app.tools import evals
from app.tools import evidence
import support


class ACorrectedHistogramCanEnterTheLedgerTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        self.thread = int(support.conversations(1)[0]["id"])
        self.eval_path = self.root / "eval.jsonl"
        self.eval_path.write_text("", encoding="utf-8")
        #: 20 rows, every other one wrong - so ten failures, all bucketed
        #: `wrong_facts` by the helper, which is what makes a correction visible.
        self.run = support.a_completed_eval_run(self.thread, self.eval_path, rows=20)

    def _rebucket(self, buckets, thread=None):
        return REGISTRY.call(
            "rebucket_failures",
            {"run_id": int(self.run["id"]), "buckets": buckets},
            actor="user",
            thread_id=thread if thread is not None else self.thread,
        )

    def test_the_route_out_of_this_outcome_is_open_at_all(self):
        """Rung one. `evidence.resolves` is what the frontier reads to decide
        whether a fact can be settled, and it used to name only `run_eval` -
        the tool whose answer never changes."""
        resolved = evidence.resolves("failure_histogram", diagnosis.load_spec())
        self.assertEqual(resolved["tool"], "rebucket_failures")
        self.assertEqual(resolved["run_as"], "harness")
        self.assertIn("run_eval", resolved["also"])

    def test_a_corrected_histogram_is_recorded_as_MEASURED(self):
        """Rung two, and the origin is the whole of it.

        A STATED histogram would route at a node and open nothing, because this
        fact is `source: derive`. The reason the dead end was real is that only
        MEASURED counts here, so only a MEASURED value proves it is open.
        """
        result = self._rebucket({"0": "wrong_format", "2": "wrong_style"})
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result["corrected"], 2)

        sheet, _ = evidence.assemble_facts(self.thread, {}, "user")
        recorded = sheet.get("failure_histogram")
        self.assertIsNotNone(recorded, "nothing reached the ledger")
        self.assertEqual(recorded.origin, diagnosis.MEASURED)
        self.assertEqual(
            recorded.value, {"wrong_facts": 8, "wrong_format": 1, "wrong_style": 1}
        )

    def test_a_row_the_person_did_not_name_keeps_the_rule_s_bucket(self):
        """Silence is not agreement, and the reply says which it was.

        Eight of the ten failures were never looked at. They stay where the rule
        put them - and `whose_judgement` says that is because the person did not
        say, not because they agreed.
        """
        result = self._rebucket({"0": "wrong_format"})
        self.assertEqual(result["kept_the_rule_s_bucket"], 9)
        self.assertIn("did not say", result["whose_judgement"])

    def test_the_counts_are_ours_and_the_buckets_are_theirs_and_it_says_so(self):
        """The provenance sentence, asserted rather than hoped.

        This is the claim that makes the stamp honest: the tally is measured off
        rows this process read, the labels are the person's, and a reply that
        printed the histogram without saying which half was whose would be the
        defect every wall here is about.
        """
        result = self._rebucket({"0": "wrong_format"})
        self.assertIn("counts are this tool's", result["whose_judgement"])
        self.assertIn("buckets", result["whose_judgement"])

    def test_a_bucket_the_router_cannot_route_is_refused(self):
        """`S1_ROUTE_BY_FAILURE_MODE` RAISES on a key it has no route for, and
        the ledger names that as a known gap. The vocabulary comes off the
        ledger's own router, never from a list in the tool."""
        result = self._rebucket({"0": "a_bucket_nobody_declared"})
        self.assertFalse(result.get("ok"))
        self.assertEqual(result["error"], "rejected_buckets")
        self.assertEqual(result["refusals"][0]["refused"], "not_a_routable_mode")
        self.assertEqual(
            sorted(result["routable_modes"]),
            sorted(evals.routable_modes(diagnosis.load_spec())),
        )

    def test_a_row_that_passed_cannot_be_put_in_the_failure_histogram(self):
        """The sum of this histogram is what stage 1 reads to decide whether
        there is anything to diagnose. A passing row in it is a failure that
        did not happen."""
        result = self._rebucket({"1": "wrong_format"})
        self.assertFalse(result.get("ok"))
        self.assertEqual(result["refusals"][0]["refused"], "this_row_passed")

    def test_a_row_that_is_not_in_this_run_is_refused(self):
        result = self._rebucket({"9999": "wrong_format"})
        self.assertFalse(result.get("ok"))
        self.assertEqual(result["refusals"][0]["refused"], "not_in_this_run")

    def test_nothing_is_recorded_when_anything_was_refused(self):
        """All or nothing, so a half-applied correction cannot exist.

        A person who mistyped one bucket out of six must not end up with a
        histogram carrying the other five and no way to tell.
        """
        before, _ = evidence.assemble_facts(self.thread, {}, "user")
        self.assertIsNone(before.get("failure_histogram"))

        self._rebucket({"0": "wrong_format", "9999": "wrong_style"})

        after, _ = evidence.assemble_facts(self.thread, {}, "user")
        self.assertIsNone(
            after.get("failure_histogram"), "a refused call recorded something"
        )

    def test_another_conversations_run_is_refused(self):
        """Re-reading somebody else's failures here would file their rows under
        this thread - the same rule `score` keeps about a baseline."""
        other = int(support.conversations(2)[1]["id"])
        result = self._rebucket({"0": "wrong_format"}, thread=other)
        self.assertFalse(result.get("ok"))
        self.assertEqual(result["error"], "another_conversation")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
