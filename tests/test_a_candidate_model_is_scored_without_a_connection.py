"""A model nobody trained can be scored on the rows the baseline graded.

## The refusal this closes half of

`NO_TRAIN__SWAP_MODEL`, `NO_TRAIN__USE_EXISTING_BASE` and `NO_TRAIN__QUANTIZE`
shared one sentence in `propose.NOT_COVERED`:

    find_models and read_model_config can find a candidate and nothing here can
    connect it or score it, so a plan would stop one step short of the number
    that decides the question.

The blocking half was "nothing here can score it", and it was true of a
CONNECTION - `measure_baseline`, `run_eval` and `try_prompt` all send rows to a
provider. It was never true of the sandbox: the pinned recipe's `eval` kind
loads a base model and answers with it, which is exactly what `include_base` has
always used for the control arm of an adapter run. `score_a_candidate_model`
makes that arm the whole run.

## What this file pins, and what it deliberately does not

It asserts the DECLARATIONS and the REFUSALS, which are where this tool can do
harm. It does not drive a scoring run to completion - that needs a pinned recipe
venv and a real model, and `tests/test_an_adapter_is_scored_where_it_was_made.py`
is where that harness lives. What matters here is that a tool which produces a
number about somebody's model cannot stamp a fact, cannot claim a connection,
and refuses every input that would make its number mean something else.

## Why it stamps nothing, permanently

The facts these outcomes turn on - `model_swap_tried`, `quantization_tried` -
are `source: ask`, and `evidence.may_be_declared_measurable` refuses an asked
fact to every instrument. That is not a gap to be closed later: the ledger is
saying there is nobody to ask but the user. So the build this tool will sit in
ends in a QUESTION, and what it buys is that the person answers it having just
seen the candidate's score on their own rows rather than from memory.
"""

import unittest

from app import diagnosis
from app.tools import REGISTRY
from app.tools import evidence
from app.tools import propose
from app.tools import training
import support


TOOL = "score_a_candidate_model"

#: The three tools that score a model through a CONNECTION. Two other tests pin
#: this roster by exact equality; it is repeated here because the whole design
#: of the new tool is that it does not join it.
THROUGH_A_CONNECTION = ("measure_baseline", "run_eval", "try_prompt")


class ACandidateModelIsScoredWithoutAConnectionTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        self.thread = int(support.conversations(1)[0]["id"])

    def test_it_stamps_nothing_and_claims_no_connection(self):
        """The two declarations that keep this honest, asserted together.

        `measures=()` because the facts it informs are `source: ask` and can
        never be measured by anything. No `providers` in `reads` because it
        sends rows to a process in a sandbox, and `propose.py` derives its
        roster of connection-scorers from that word.
        """
        spec = REGISTRY.get(TOOL)
        self.assertIsNotNone(spec)
        self.assertEqual(spec.measures, ())
        self.assertNotIn("providers", spec.reads or ())
        self.assertEqual(spec.provides, ("models.candidate.score",))
        self.assertEqual(spec.approval, "always")

    def test_it_did_not_join_the_roster_of_connection_scorers(self):
        """The roster is derived, so a tool that lied about `reads` would show.

        Derived here independently of `propose`, minus the tools `propose`
        names as reading a connection for another purpose (2026-09-12: the
        invent-a-dataset pair writes and grades ROWS, not a model) - each of
        which must carry its reason there, so a tool cannot slip off this
        roster by being added to that dict without one.
        """
        from app.tools import propose

        for name, reason in propose.NOT_A_SCORER.items():
            self.assertTrue(reason and len(reason) > 20, f"{name} is excused with no reason")
            self.assertIn("providers", REGISTRY.get(name).reads, f"{name} is excused from a roster it is not on")
        scorers = sorted(
            spec.name
            for spec in REGISTRY
            if "providers" in (spec.reads or ()) and spec.name not in propose.NOT_A_SCORER
        )
        self.assertEqual(scorers, sorted(THROUGH_A_CONNECTION))
        self.assertNotIn(TOOL, scorers)

    def test_the_baseline_is_validated_before_anything_else_is_looked_at(self):
        """Refusal ORDER, and it is not incidental.

        A call with both a missing baseline and no model named comes back about
        the baseline, because `_the_baseline_to_pair_against` runs first. That
        is the right order: the baseline is what makes any of this a paired
        comparison, and a reply complaining about the model name would send
        somebody off to find a repo id for a run that does not exist.
        """
        result = REGISTRY.call(
            TOOL,
            {
                "sandbox": "nowhere",
                "baseline_run_id": 999999,
                "thread_id": self.thread,
                "base_model": "   ",
            },
            actor="user",
            thread_id=self.thread,
            approved=True,
        )
        self.assertFalse(result.get("ok"))
        self.assertIn("no eval run", str(result.get("detail", "")))

    def test_the_missing_model_guard_exists_and_says_what_it_would_cost(self):
        """Driven no further than this, and the reason is written down.

        Reaching that guard needs a real completed eval run in this thread, and
        the harness for that lives in
        `tests/test_an_adapter_is_scored_where_it_was_made.py`. What is asserted
        here is that the guard is present and refuses rather than defaulting -
        the sentence a reviewer needs to see is "guessing one produces a number
        that looks like a score".
        """
        import inspect

        body = inspect.getsource(training.score_candidate)
        self.assertIn("no model was named", body)
        self.assertIn("looks like a score", body)

    def test_a_baseline_that_does_not_exist_is_refused(self):
        """Inherited from `_the_baseline_to_pair_against`, which both scorers
        share so they cannot drift on what makes a baseline pairable."""
        result = REGISTRY.call(
            TOOL,
            {
                "sandbox": "nowhere",
                "baseline_run_id": 999999,
                "thread_id": self.thread,
                "base_model": "Qwen/Qwen3-4B",
            },
            actor="user",
            thread_id=self.thread,
            approved=True,
        )
        self.assertFalse(result.get("ok"))
        self.assertIn("no eval run", str(result.get("detail", "")))

    def test_both_scorers_share_one_definition_of_a_pairable_baseline(self):
        """The extraction, asserted rather than assumed.

        If these two ever validate a baseline differently, one of them is
        pairing against a run the other would refuse - and the paired
        comparison is the only thing that makes either number mean anything.
        """
        import inspect

        source = inspect.getsource(training.score)
        candidate = inspect.getsource(training.score_candidate)
        for body in (source, candidate):
            self.assertIn("_the_baseline_to_pair_against", body)

    def test_the_facts_these_outcomes_turn_on_can_never_be_measured(self):
        """Which is why the build ends in a question, and why that is permanent.

        Not "no tool measures it yet" - `may_be_declared_measurable` refuses an
        `ask` fact to every instrument, so `measures=("model_swap_tried",)`
        cannot be registered by anything, ever.
        """
        spec = diagnosis.load_spec()
        for fact in ("model_swap_tried", "quantization_tried"):
            with self.subTest(fact=fact):
                self.assertEqual(spec.facts[fact]["source"], "ask")
                self.assertFalse(evidence.may_be_declared_measurable(fact, spec))

    def test_the_three_outcomes_went_three_different_ways(self):
        """REWRITTEN in the commit that covered two of them, not loosened.

        One commit ago this read `NOT_COVERED` for all three and asserted the
        stale sentence was gone. Then the proposer landed and two of them left
        that table entirely - so the assertion had to move with them or it would
        have been reading a key that no longer exists.

        What it says now is the stronger thing: the group of three is gone, and
        each of the three is somewhere different for a reason of its own.
        """
        covered = ("NO_TRAIN__SWAP_MODEL", "NO_TRAIN__USE_EXISTING_BASE")
        for outcome in covered:
            with self.subTest(outcome=outcome):
                self.assertIn(outcome, propose.PROPOSERS)
                self.assertNotIn(outcome, propose.NOT_COVERED)
                self.assertIn(TOOL, propose.COVERAGE[outcome])

        # The third did NOT come with them, and its reason is its own.
        quantize = propose.NOT_COVERED["NO_TRAIN__QUANTIZE"]
        self.assertNotIn("NO_TRAIN__QUANTIZE", propose.PROPOSERS)
        self.assertIn("quantis", quantize.lower())

        # And the sentence that answered for all three is gone from both tables.
        stale = "nothing here can connect it or score it"
        for table in (propose.NOT_COVERED, propose.COVERAGE):
            for outcome, text in table.items():
                with self.subTest(outcome=outcome):
                    self.assertNotIn(stale, text)

    def test_both_covered_outcomes_take_the_same_build_and_differ_only_in_the_question(self):
        """Two entries, one function - and the question is what separates them.

        The build is the same four steps either way. What changes is the fact it
        asks about, and both are `source: ask`, which is why neither can end in
        a stamp.
        """
        self.assertIs(
            propose.PROPOSERS["NO_TRAIN__SWAP_MODEL"],
            propose.PROPOSERS["NO_TRAIN__USE_EXISTING_BASE"],
        )
        facts = {fact for fact, _ in propose._CANDIDATE_OUTCOMES.values()}
        self.assertEqual(facts, {"model_swap_tried", "user_requested_from_scratch"})

        spec = diagnosis.load_spec()
        for fact in facts:
            with self.subTest(fact=fact):
                self.assertEqual(spec.facts[fact]["source"], "ask")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
