"""The reasons in `NOT_COVERED` went false, and this is what checks they stay true.

`docs/VISION.md` says the most valuable thing this product can say is *"do not
train anything"* and then names the hole: that answer is a dead end. The
evaluation bench closed part of it, and the moment it did, two sentences in
`app/tools/propose.py` became written claims that this product cannot do
something it can:

  *"the prompt bench. It needs a stored prompt to change and an eval runner to
   score it before and after, and neither ships ... there is no run_eval."*
  *"the evaluation bench (Milestone 3). It needs per-row eval results stored."*

A false reason in that dict is worse than no proposer. It is the product
telling somebody their real problem is the prompt, naming precisely what to do
instead, and then declining to do it on grounds that stopped being true.

So this file checks three different things, and they are three because a
coverage dict can go wrong in three different directions:

1. **What is now covered really runs.** The structural work - every step a
   registered tool, every schema satisfied, the graph acyclic, every cost
   provenanced - is done for every proposer by
   `tests/test_the_proposal_is_executable.py`, which counts its builds against
   `len(propose.PROPOSERS)` and goes red if a proposer arrives without one.
   What is here instead is the part that file cannot see: that the step this
   build runs is the step that moves THIS outcome's blocking fact.
2. **What is still not covered is not covered for the reason given.** Each
   surviving reason is checked against the live registry and the live fact
   ledger rather than believed, in the shape
   `test_the_reason_given_for_the_row_count_outcome_is_actually_true` already
   established: the day somebody registers the tool that would close one of
   these, the reason turns red instead of quietly becoming a lie.
3. **The refusals are refusals.** A proposer that emits a plausible-looking
   plan for something that cannot execute is the failure the `Build` object
   exists to prevent. The rewrite refuses without a prompt rather than drafting
   one, the classify build refuses without the two column names rather than
   guessing them, and neither may quietly become a helpful default.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import diagnosis_fixtures

from app import build, diagnosis
from app.build import BuildInvalid, Question, Ref
from app.tools import REGISTRY, evidence, prompts, propose

import support


class BenchProposalTestCase(unittest.TestCase):
    """A scratch database each, because proposing reads the ledger."""

    def setUp(self):
        self.root = support.sandbox(self)

    def eval_file(self, rows: int = 60, name: str = "eval.jsonl") -> Path:
        path = self.root / name
        path.write_text(
            "\n".join(
                json.dumps({"q": f"question {i}", "a": "yes"}) for i in range(rows)
            ),
            encoding="utf-8",
        )
        return path

    def situation(self, histogram, *, outcome: str, facts=None, **paths):
        """The engine decides, over a fact sheet the fixtures know how to build.

        See `bench_situation` in `tests/test_the_proposal_is_executable.py` for
        why the ledger round trip is skipped and the tree walk is not: a
        MEASURED `failure_histogram` can only be produced by running `run_eval`
        against somebody's model, and a test that needs a model running is a
        test that fails on a fresh checkout.
        """
        sheet = dict(diagnosis_fixtures.MINTING["TRAIN__LORA_SFT"])
        sheet["failure_histogram"] = diagnosis.measured(histogram)
        sheet.update(facts or {})
        result = diagnosis.diagnose(sheet)
        self.assertEqual(result.outcome, outcome)
        # `values` is filled the way `propose_build` fills it - from the facts
        # behind the diagnosis - because a proposer that reads a fact reads it
        # from there, and a helper that left it empty would test a situation no
        # caller can produce.
        return propose.Situation(
            outcome=result.outcome,
            result=result,
            values={
                name: getattr(value, "value", value) for name, value in sheet.items()
            },
            origins=dict(result.fact_origins),
            **paths,
        )

    def classify(self, **paths):
        paths.setdefault("input_field", "q")
        paths.setdefault("expected_field", "a")
        return self.situation({}, outcome="ACTION__CLASSIFY_FAILURES", **paths)

    def better_prompt(self, **paths):
        paths.setdefault("input_field", "q")
        paths.setdefault("expected_field", "a")
        return self.situation(
            {"wrong_style": 30},
            outcome="NO_TRAIN__BETTER_PROMPT",
            facts={"prompt_iterations": 0},
            **paths,
        )

    def few_shot(self, **paths):
        paths.setdefault("input_field", "q")
        paths.setdefault("expected_field", "a")
        return self.situation(
            {"wrong_style": 30},
            outcome="NO_TRAIN__FEW_SHOT",
            facts={"prompt_iterations": 3, "fewshot_tried": False},
            **paths,
        )


# ---------------------------------------------------------------------------
# 1. WHAT IS NOW COVERED REALLY MOVES THE THING IT IS FOR.


class TheEvalBenchClosesTheClassifyOutcomeTest(BenchProposalTestCase):
    """`ACTION__CLASSIFY_FAILURES` was where every run in this product stopped."""

    def test_the_outcome_is_covered_now(self):
        self.assertIn("ACTION__CLASSIFY_FAILURES", propose.PROPOSERS)
        self.assertIn("ACTION__CLASSIFY_FAILURES", propose.COVERAGE)
        self.assertNotIn("ACTION__CLASSIFY_FAILURES", propose.NOT_COVERED)

    def test_the_build_runs_a_tool_that_really_measures_the_blocking_fact(self):
        """The check that separates this from the ACTION__COUNT_THE_ROWS trap.

        That outcome stays uncovered because NO registered tool measures
        `tabular_rows`, so a build for it would re-enter the tree and land on
        the same outcome having moved nothing. This asserts the opposite
        property here, off the registry rather than off a docstring: some step
        in this build runs a tool that declares it measures the fact the
        outcome is blocked on. Take `failure_histogram` out of `run_eval`'s
        `measures=` and this goes red.
        """
        plan = propose.propose(self.classify(eval_path=str(self.eval_file())))
        measurers = {
            step.tool
            for step in plan.steps
            if "failure_histogram" in REGISTRY.get(step.tool).measures
        }
        self.assertTrue(
            measurers,
            "no step in the classify build measures failure_histogram, so the "
            "build cannot move the outcome it is for",
        )

    def test_the_build_ends_on_the_fact_becoming_measured(self):
        plan = propose.propose(self.classify(eval_path=str(self.eval_file())))
        self.assertEqual(plan.exit_criterion.source, "diagnosis")
        self.assertEqual(
            plan.exit_criterion.subject, "fact_origins.failure_histogram"
        )
        self.assertEqual(plan.exit_criterion.comparator, "is_measured")

    def test_the_last_step_re_enters_the_tree_rather_than_deciding(self):
        plan = propose.propose(self.classify(eval_path=str(self.eval_file())))
        self.assertEqual(plan.steps[-1].tool, "run_diagnosis")

    def test_the_reading_step_takes_its_run_from_the_step_that_made_it(self):
        """A `needs` entry with no `Ref` behind it is an ordering somebody
        asserted; a `Ref` is one the graph checks. The run id cannot be known at
        proposal time, so this is the only honest way to wire the two - and
        `Build.validate` refuses it if the named output is not really produced.
        """
        plan = propose.propose(self.classify(eval_path=str(self.eval_file())))
        read = plan.step("read")
        self.assertEqual(read.arguments["run_id"], Ref("run", "run_id"))
        self.assertIn("run", read.needs)
        self.assertIn("run_id", {out.name for out in plan.step("run").produces})

    def test_the_plan_says_out_loud_that_twenty_failures_may_not_appear(self):
        """The honest half. The build CAN move the outcome; whether it does on a
        given file depends on how many rows fail, and a plan that implied
        otherwise would be promising a result rather than a step."""
        plan = propose.propose(self.classify(eval_path=str(self.eval_file())))
        grading = [step for step in plan.steps if step.tool == "run_eval"]
        self.assertEqual(len(grading), 1)
        risks = " ".join(risk.what for risk in grading[0].risks)
        self.assertIn("20", risks)

    def test_it_refuses_without_the_columns_rather_than_guessing_them(self):
        with self.assertRaises(propose.NotEnoughToPropose) as raised:
            propose.propose(
                self.situation(
                    {},
                    outcome="ACTION__CLASSIFY_FAILURES",
                    eval_path=str(self.eval_file()),
                    input_field="",
                    expected_field="",
                )
            )
        self.assertEqual(
            set(raised.exception.needs), {"input_field", "expected_field"}
        )


class TheRequestCountIsDerivedOrItIsUnknownTest(BenchProposalTestCase):
    """`run_eval` asks one question per row, so the count is derivable - when the
    count on file can be shown to be a count of THIS file, and never otherwise."""

    def measured_situation(self, path: Path, base=None, thread_id: int = 1, **extra):
        """`base`, carrying a REAL measured `eval_size_n` from the real ledger.

        The count is taken through the real tool into the real ledger and read
        back out of it, so what is exercised is the same recovery path
        `_baseline_requests` uses - the derivation parser, the subject and the
        row's date - rather than a hand-made `Situation`.
        """
        support.a_conversation(thread_id)
        counted = REGISTRY.call(
            "measure_eval_set",
            {"path": str(path), "finish_the_count": True},
            actor=evidence.USER,
            thread_id=thread_id,
        )
        self.assertTrue(counted.get("exact"), counted)
        _sheet, trail = evidence.assemble_facts(thread_id, {}, evidence.USER)
        situation = base if base is not None else self.classify(eval_path=str(path))
        fields = dict(
            outcome=situation.outcome,
            result=situation.result,
            values={row["fact"]: row["value"] for row in trail},
            origins={row["fact"]: row["origin"] for row in trail},
            hows={row["fact"]: row.get("how") or "" for row in trail},
            recorded_at=propose.when_each_row_was_written(thread_id, trail),
            eval_path=str(path),
            input_field="q",
            expected_field="a",
            sample=situation.sample,
            prompt=situation.prompt,
            prompt_line=situation.prompt_line,
        )
        fields.update(extra)
        return propose.Situation(**fields)

    def test_a_count_of_this_file_becomes_a_derived_request_count(self):
        evaluation = self.eval_file(rows=60)
        plan = propose.propose(self.measured_situation(evaluation))
        grading = plan.step("run")
        self.assertEqual(grading.cost.model_requests.provenance, build.INFERRED)
        self.assertIn("counted 60 rows", grading.cost.model_requests.how)

    def test_the_derived_count_is_capped_by_the_sample_the_tool_enforces(self):
        evaluation = self.eval_file(rows=60)
        situation = self.measured_situation(evaluation)
        plan = propose.propose(situation)
        self.assertEqual(
            plan.step("run").cost.model_requests.value, float(situation.sample)
        )

    def test_a_derived_count_makes_the_counting_step_unnecessary(self):
        evaluation = self.eval_file(rows=60)
        plan = propose.propose(self.measured_situation(evaluation))
        self.assertNotIn("measure_eval_set", {step.tool for step in plan.steps})

    def test_an_uncounted_file_is_unknown_and_the_build_goes_and_counts(self):
        plan = propose.propose(self.classify(eval_path=str(self.eval_file())))
        requests = plan.step("run").cost.model_requests
        self.assertEqual(requests.provenance, build.UNKNOWN)
        self.assertIn("count the eval set", requests.find_out_by)
        self.assertEqual(plan.steps[0].tool, "measure_eval_set")

    def test_a_prompt_that_reads_as_a_path_costs_the_estimate_not_the_truth(self):
        """A free-text prompt can make the call ambiguous, and the answer to that
        is UNKNOWN plus a step that counts - never a number picked by guessing
        which argument this file recognises. See `_eval_cost` for the one-line
        change in `run_eval`'s own registration that closes it properly."""
        evaluation = self.eval_file(rows=60)

        # A prompt with no separator in it leaves the call legible, so the count
        # is derived off the real measurement.
        legible = propose.propose(
            self.measured_situation(
                evaluation,
                base=self.better_prompt(
                    eval_path=str(evaluation), prompt="Answer with one word."
                ),
            )
        ).step("attempt")
        self.assertEqual(legible.cost.model_requests.provenance, build.INFERRED)

        # One slash and the call names two things that might be paths, so the
        # estimate refuses and the build goes and counts instead.
        ambiguous = propose.propose(
            self.measured_situation(
                evaluation,
                base=self.better_prompt(
                    eval_path=str(evaluation),
                    prompt="Answer yes/no and nothing else.",
                ),
            )
        ).step("attempt")
        self.assertIsNone(ambiguous.operates_on)
        self.assertEqual(ambiguous.cost.model_requests.provenance, build.UNKNOWN)
        self.assertIsNone(ambiguous.cost.model_requests.value)
        self.assertIn(
            "count the eval set", ambiguous.cost.model_requests.find_out_by
        )


class ThePromptBenchTurnsTheVerdictIntoAStepTest(BenchProposalTestCase):
    """PRODUCT_SPEC 6.5: rewrite and few-shot are v1. They are one tool call each."""

    def test_both_outcomes_are_covered_now(self):
        for outcome in ("NO_TRAIN__BETTER_PROMPT", "NO_TRAIN__FEW_SHOT"):
            with self.subTest(outcome=outcome):
                self.assertIn(outcome, propose.PROPOSERS)
                self.assertIn(outcome, propose.COVERAGE)
                self.assertNotIn(outcome, propose.NOT_COVERED)

    def test_the_build_scores_the_attempt_with_the_prompt_bench(self):
        """`try_prompt` rather than `run_eval` twice, because a prompt here is a
        VERSION of something: better is a claim about a recorded pair."""
        plan = propose.propose(
            self.better_prompt(
                eval_path=str(self.eval_file()), prompt="Answer with one word."
            )
        )
        self.assertEqual(plan.step("attempt").tool, "try_prompt")

    def test_the_prompt_that_reaches_the_step_is_the_one_the_caller_gave(self):
        mine = "Be terse. Answer with the label and nothing else."
        plan = propose.propose(
            self.better_prompt(eval_path=str(self.eval_file()), prompt=mine)
        )
        self.assertEqual(plan.step("attempt").arguments["prompt"], mine)

    def test_a_rewrite_is_refused_without_a_prompt_rather_than_drafted(self):
        with self.assertRaises(propose.NotEnoughToPropose) as raised:
            propose.propose(self.better_prompt(eval_path=str(self.eval_file())))
        self.assertEqual(raised.exception.needs, ("prompt",))

    def test_few_shot_needs_no_prompt_because_the_bench_builds_it(self):
        """The engine says the exemplars come from the eval FAILURES, and that is
        the half people get backwards. `fewshot_from_failures` takes them from
        the rows the champion got wrong and holds exactly those out of the
        score, so there is nothing here for a person to write or to leak."""
        plan = propose.propose(self.few_shot(eval_path=str(self.eval_file())))
        attempt = plan.step("attempt")
        self.assertNotIn("prompt", attempt.arguments)
        self.assertEqual(
            attempt.arguments["fewshot_from_failures"], prompts.MAX_EXEMPLARS
        )

    def test_the_exemplar_count_is_the_tools_own_ceiling_not_a_number_typed_here(self):
        """The engine asks for 5-20 and `prompts.MAX_EXEMPLARS` is the top of it.
        Reading the tool's constant rather than typing 20 is what keeps the two
        from drifting apart silently."""
        plan = propose.propose(self.few_shot(eval_path=str(self.eval_file())))
        self.assertEqual(
            plan.step("attempt").arguments["fewshot_from_failures"],
            prompts.MAX_EXEMPLARS,
        )

    def test_the_change_is_aimed_at_the_bucket_the_engine_routed_on(self):
        """`targets=` makes the reply say what happened to THAT bucket, which
        matters because an aggregate can be flat while a change fixes every
        format failure and breaks as many factual ones."""
        plan = propose.propose(
            self.better_prompt(
                eval_path=str(self.eval_file()), prompt="Answer with one word."
            )
        )
        self.assertEqual(plan.step("attempt").arguments["targets"], "wrong_style")

    def with_histogram(self, histogram) -> propose.Situation:
        """A situation carrying just the histogram, to exercise `_aim_at` alone.

        Constructed rather than diagnosed because what is under test is the rule
        for reading a target off a histogram, and several of the histograms
        below are ones the engine would route somewhere else entirely - which is
        beside the point and would make the test about routing.
        """
        return propose.Situation(
            outcome="NO_TRAIN__BETTER_PROMPT",
            result=None,
            values={"failure_histogram": histogram},
        )

    def test_a_tie_for_the_largest_bucket_is_not_aimed_at(self):
        """Picking either side of a tie would be this file deciding what the
        change is aimed at, which is the person's call and the engine's routing
        question, not a tiebreak worth inventing."""
        self.assertEqual(
            propose._aim_at(self.with_histogram({"wrong_style": 15, "refuses": 15})),
            "",
        )

    def test_a_bucket_no_row_can_be_in_is_never_aimed_at(self):
        """`inconsistent` is a property of a PAIR of rows, so the bench cannot
        key a bucket on it and refuses by name. This reads that list off the
        bench rather than repeating it here."""
        self.assertIn("inconsistent", prompts.NOT_A_ROW_LOCAL_MODE)
        self.assertEqual(
            propose._aim_at(self.with_histogram({"inconsistent": 30})), ""
        )

    def test_a_mode_the_router_does_not_know_is_never_aimed_at(self):
        self.assertEqual(
            propose._aim_at(self.with_histogram({"vibes_were_off": 30})), ""
        )

    def test_no_histogram_at_all_is_no_target_rather_than_a_default(self):
        for histogram in ({}, None, "wrong_style"):
            with self.subTest(histogram=histogram):
                self.assertEqual(
                    propose._aim_at(self.with_histogram(histogram)), ""
                )

    def test_the_line_is_named_by_the_caller_or_taken_from_the_eval_file(self):
        """Every comparison is against the line's champion, so the name decides
        what the attempt is measured against - and the step says which it is."""
        evaluation = self.eval_file(name="tickets.jsonl")
        derived = propose.propose(
            self.better_prompt(eval_path=str(evaluation), prompt="One word.")
        ).step("attempt")
        self.assertEqual(derived.arguments["line"], "tickets")
        self.assertIn("did not give one", derived.why)

        named = propose.propose(
            self.better_prompt(
                eval_path=str(evaluation),
                prompt="One word.",
                prompt_line="ticket router",
            )
        ).step("attempt")
        self.assertEqual(named.arguments["line"], "ticket router")
        self.assertIn("which you named", named.why)

    def test_the_build_ends_on_a_verdict_and_no_evidence_is_one(self):
        plan = propose.propose(
            self.better_prompt(
                eval_path=str(self.eval_file()), prompt="Answer with one word."
            )
        )
        self.assertEqual(plan.exit_criterion.source, "outputs")
        self.assertEqual(plan.exit_criterion.subject, "attempt.verdict")
        self.assertIn("indistinguishable", plan.exit_criterion.stated)

    def test_it_asks_for_the_fact_it_cannot_stamp_rather_than_pretending(self):
        """`prompt_iterations` and `fewshot_tried` are `source: ask`. No step
        here can stamp one, so the build carries a question - and a re-check
        whose criterion could never be met is not quietly added to make the plan
        look like the others."""
        for situation, fact in (
            (
                self.better_prompt(
                    eval_path=str(self.eval_file()), prompt="Answer with one word."
                ),
                "prompt_iterations",
            ),
            (self.few_shot(eval_path=str(self.eval_file())), "fewshot_tried"),
        ):
            with self.subTest(fact=fact):
                plan = propose.propose(situation)
                self.assertEqual([q.fact for q in plan.questions], [fact])
                self.assertNotIn("run_diagnosis", {step.tool for step in plan.steps})

    def test_the_plan_says_what_happens_when_the_line_has_nothing_on_it(self):
        """The proposer cannot read the prompt store - `propose_build` does not
        declare `reads=("prompts",)` and should not - so the state of the line is
        something the step finds out. What the plan owes the person is to say so
        before they approve it, and to say the two answers are different."""
        first = propose.propose(
            self.better_prompt(
                eval_path=str(self.eval_file()), prompt="Answer with one word."
            )
        ).step("attempt")
        self.assertIn("first", " ".join(r.what_we_do for r in first.risks))

        exemplars = propose.propose(
            self.few_shot(eval_path=str(self.eval_file()))
        ).step("attempt")
        self.assertIn(
            "no scored run",
            " ".join(r.what for r in exemplars.risks).replace(
                "nothing scored on it yet", "no scored run"
            ),
        )

    def test_the_proposer_does_not_read_the_prompt_store(self):
        """A tool that declared `reads=("prompts",)` would have to be classified
        in `app/build.py` before any build containing it could be planned, and
        `propose_build` has no business reading a bench's tables to decide what
        to draw."""
        self.assertNotIn("prompts", REGISTRY.get("propose_build").reads)


class TheLeakIsClosedByTheBenchNotByTheProposalTest(BenchProposalTestCase):
    """Scoring a prompt on the rows it was shown is a leak, and it does not look
    like one from the outside: it looks like the prompt worked."""

    def test_the_proposer_never_asks_anybody_to_hand_over_row_indexes(self):
        """An earlier draft of this proposer took a `hold_out` list and applied
        it to two `run_eval` calls itself. `try_prompt` makes that wrong rather
        than merely redundant: it chooses the exemplars, so it knows exactly
        which rows to exclude, and a list supplied from outside could only
        disagree with the rows actually used."""
        self.assertNotIn("hold_out", REGISTRY.get("propose_build").schema["properties"])
        self.assertFalse(hasattr(propose.Situation(outcome="x", result=None), "hold_out"))

    def test_the_step_asks_the_bench_to_choose_the_exemplars(self):
        plan = propose.propose(self.few_shot(eval_path=str(self.eval_file())))
        attempt = plan.step("attempt")
        self.assertIn("fewshot_from_failures", attempt.arguments)
        self.assertIn("held out", attempt.why)

    def test_the_tool_this_leans_on_really_holds_the_exemplars_out(self):
        """Checked against the tool's own declaration rather than believed: the
        argument this build passes is the one documented to exclude the rows it
        draws from. If that stops being true the sentence in the plan is a lie
        and this goes red."""
        spec = REGISTRY.get("try_prompt")
        described = spec.schema["properties"]["fewshot_from_failures"]["description"]
        self.assertIn("hold those rows out", described)


# ---------------------------------------------------------------------------
# 2. WHAT IS STILL NOT COVERED IS NOT COVERED FOR THE REASON GIVEN.


class TheSurvivingReasonsAreCheckedNotBelievedTest(BenchProposalTestCase):
    """Each reason is verified against the live registry and the live ledger.

    The shape is the one `test_the_reason_given_for_the_row_count_outcome_is_
    actually_true` established: the day somebody registers the tool that would
    close one of these, the reason turns red instead of becoming a lie.
    """

    def measurers_of(self, fact: str) -> list[str]:
        return sorted(spec.name for spec in REGISTRY if fact in spec.measures)

    def test_no_stale_reason_still_claims_the_eval_runner_does_not_exist(self):
        """The regression guard for this whole run. Both blocking sentences named
        a tool that had not been written; both tools exist now."""
        self.assertIsNotNone(REGISTRY.get("run_eval"))
        self.assertIsNotNone(REGISTRY.get("read_eval_results"))
        for outcome, reason in propose.NOT_COVERED.items():
            with self.subTest(outcome=outcome):
                self.assertNotIn("there is no run_eval", reason)
                self.assertNotIn("It needs per-row eval results stored", reason)

    def test_re_bucketing_HAS_a_door_now_and_two_of_the_three_closures_remain(self):
        """The tripwire fired on 2026-08-28, and it fired on the right one.

        It held three closures. The engine says *re-enter with the corrected
        histogram*, and that could not be stated (the fact admits MEASURED
        alone), could not be re-measured into anything different (the only
        measurer buckets by fixed rules, never by a model), and could not be
        ASKED for either (`Build.validate` refuses a question about a fact a
        registered tool measures).

        TWO OF THE THREE ARE UNCHANGED AND ARE STILL ASSERTED BELOW. What moved
        is the middle one, which was never a law - it was a fact about there
        being one instrument. `rebucket_failures` is a second, and it answers
        the question the first cannot: it re-tallies the rows an eval run
        already graded, using the person's reading where they gave one. The
        count is what it measures; the buckets are theirs, and its reply says so.

        The outcome STAYS in `NOT_COVERED`, and that is not a leftover. A build
        would have to carry which rows were mis-bucketed, and that is the thing
        the person goes and finds out - a plan cannot hold a decision nobody has
        made yet.
        """
        outcome = "ACTION__RE_BUCKET_THE_FAILURES"
        self.assertNotIn(outcome, propose.PROPOSERS)
        self.assertIn(outcome, propose.NOT_COVERED)

        # Closure one, unchanged: nothing but a measurement counts here.
        spec = diagnosis.default_spec()
        self.assertEqual(
            sorted(spec.admissible_for("failure_histogram")), [diagnosis.MEASURED]
        )

        # Closure two, OPENED - and this is the line the tripwire was watching.
        self.assertEqual(
            self.measurers_of("failure_histogram"),
            ["rebucket_failures", "run_eval"],
        )

        # Closure three, unchanged: still not askable, and now for two reasons.
        # The refusal names A measurer rather than a particular one - it says
        # "look before you ask", and which instrument it points at is whichever
        # the registry offers first. Asserting the exact name here would be this
        # test having an opinion about `evidence.resolves`'s ordering, which is
        # a different file's decision.
        with self.assertRaises(BuildInvalid) as raised:
            self.a_build_asking_for("failure_histogram")
        message = str(raised.exception)
        self.assertTrue(
            any(name in message for name in self.measurers_of("failure_histogram")),
            f"the refusal named no instrument that measures it: {message}",
        )

    def a_build_asking_for(self, fact: str):
        """A build whose only question is about `fact`, to prove it is refused."""
        plan = propose.propose(self.classify(eval_path=str(self.eval_file())))
        import dataclasses

        asking = dataclasses.replace(
            plan,
            questions=(
                Question(
                    ask=f"What is {fact}?",
                    why="this test needs a question about it",
                    fact=fact,
                ),
            ),
        )
        return asking.validate(REGISTRY)

    def test_one_of_the_two_format_facts_now_has_a_door_and_one_does_not(self):
        """REWRITTEN 2026-08-27, and the rewrite is the finding.

        This test used to assert that `schema_compliance` AND
        `schema_expressible` both admit MEASURED only with nothing measuring
        either, so the engine asked a person for two numbers the ledger would
        not take from them. That was true and it was the reason `stage_4_format`
        had zero builds.

        **Half of it stopped being true when `app/tools/shapes.py` shipped.**
        The reason in `NOT_COVERED` had named its own remedy - *"it closes when
        a tool measures schema_compliance, not when a proposer is written"* -
        and the tool is that. Loosening this test to keep it green would have
        hidden the one thing worth knowing about the stage; what it asserts now
        is the ASYMMETRY, because the asymmetry is what a reader needs.
        """
        spec = diagnosis.default_spec()

        # MEASURABLE NOW. The origin rule is unchanged - it still admits
        # MEASURED and nothing else - and that is no longer a wall, because
        # there is an instrument that produces MEASURED.
        self.assertEqual(
            sorted(spec.admissible_for("schema_compliance")), [diagnosis.MEASURED]
        )
        self.assertEqual(self.measurers_of("schema_compliance"), ["measure_the_format"])
        self.assertIn("ACTION__MEASURE_THE_FORMAT", propose.PROPOSERS)
        self.assertNotIn("ACTION__MEASURE_THE_FORMAT", propose.NOT_COVERED)

        # STILL WITHOUT A DOOR, and it is a different KIND of problem: a
        # judgement about the person's own requirements, declared source:
        # derive with nothing in the ledger's `derived:` block deriving it, so
        # no tool can read it and the person cannot state it. That closes when
        # the ledger says `source: ask`.
        self.assertEqual(
            sorted(spec.admissible_for("schema_expressible")), [diagnosis.MEASURED]
        )
        self.assertEqual(self.measurers_of("schema_expressible"), [])
        self.assertNotIn("schema_expressible", set((spec.raw or {}).get("derived") or {}))

        # And the outcome that is still blocked is blocked on the OTHER half:
        # somebody's calling code, which no step here can read.
        self.assertIn("ACTION__FIX_THE_DECODER", propose.NOT_COVERED)
        self.assertNotIn("ACTION__FIX_THE_DECODER", propose.PROPOSERS)

    def test_the_programmatic_metric_is_a_question_because_no_tool_can_answer_it(self):
        """RENAMED 2026-08-28, and the old name is the point.

        It was `..._is_blocked_on_a_fact_with_no_door`, and "no door" was false.
        `metric_is_programmatic` admits MEASURED alone AT GATES - which is what
        the first assertion still says - but `_challenged_facts` is called from
        `_evaluate_gate` and from nowhere else, so origins are never checked at
        a NODE. `S5_METRIC_NOT_PROGRAMMATIC` is a node. A STATED value entered
        and routed the whole time; what was missing was a build that asked for
        one, and the belief that no door existed is why nobody wrote it.

        The two assertions that were true stay, because they are the reason this
        outcome ends in a Question rather than a step: nothing measures this
        fact, and nothing can - it is a judgement about the person's own
        definition of right.
        """
        spec = diagnosis.default_spec()
        self.assertEqual(
            sorted(spec.admissible_for("metric_is_programmatic")),
            [diagnosis.MEASURED],
        )
        self.assertEqual(self.measurers_of("metric_is_programmatic"), [])

        # And the third assertion, replaced rather than dropped: the outcome now
        # has a build, and the half worth pinning is that it SCORES NOTHING.
        # `run_eval` would return a number here and would be answering a
        # different question - the trap this outcome's old reason named.
        self.assertNotIn("ACTION__MAKE_THE_METRIC_PROGRAMMATIC", propose.NOT_COVERED)
        self.assertIn("ACTION__MAKE_THE_METRIC_PROGRAMMATIC", propose.PROPOSERS)

    def test_the_optimiser_and_the_decoder_are_dependencies_that_do_not_ship(self):
        """Neither is a fact problem: nothing here searches a prompt space, and
        nothing here attaches a schema or grammar to a call."""
        for outcome in (
            "NO_TRAIN__PROMPT_OPTIMIZER",
            "NO_TRAIN__CONSTRAINED_DECODING",
        ):
            with self.subTest(outcome=outcome):
                self.assertIn(outcome, propose.NOT_COVERED)
                self.assertNotIn(outcome, propose.PROPOSERS)
        # No scorer here can be handed a schema or a grammar, and none of them
        # searches a prompt space. Both halves checked against the tools rather
        # than asserted in prose.
        for tool in ("run_eval", "try_prompt"):
            properties = set(REGISTRY.get(tool).schema.get("properties") or {})
            for absent in ("schema", "grammar", "response_format", "candidates"):
                self.assertNotIn(absent, properties, f"{tool} grew {absent}")

    def test_the_row_count_tripwire_HAS_FIRED_and_the_outcome_now_has_a_build(self):
        """The tripwire this file carried went off on 2026-08-28, as designed.

        It used to read `assertEqual(self.measurers_of("tabular_rows"), [])`
        beside a docstring saying the tool it waits for had not arrived. The
        sibling in `tests/test_the_proposal_is_executable.py` said what to do
        when it did: *"the honest answer changes from 'we cannot' to 'we have
        not'. Then this fails, and writing the proposer is the fix."*

        NOT LOOSENED. The same invariant is asserted on the other side of the
        event the tripwire was watching for, and it is a stronger statement:
        the tool exists, the frontier can offer to run it, and the outcome has
        a build that ends in a MEASURED fact rather than a question.

        THE BUILD COUNTS, IT DOES NOT ASK, and that is the half worth pinning.
        A proposer that asked the person to type a number the harness can read
        is the shape
        `tests/test_a_stated_quantity_becomes_an_offer_to_count_it.py` exists to
        refuse, so this asserts the plan carries no questions at all.
        """
        self.assertEqual(self.measurers_of("tabular_rows"), ["profile_dataset"])

        # `run_as` is what makes it a pointer card at the frontier rather than a
        # Gap rendered as prose with no control on it.
        resolved = evidence.resolves("tabular_rows", diagnosis.load_spec())
        self.assertEqual(resolved["tool"], "profile_dataset")
        self.assertEqual(resolved["run_as"], "harness")

        self.assertIn("ACTION__COUNT_THE_ROWS", propose.PROPOSERS)
        self.assertNotIn("ACTION__COUNT_THE_ROWS", propose.NOT_COVERED)


class TheTwoListsStillAccountForEverythingTest(BenchProposalTestCase):
    """Moving three outcomes between the lists is exactly how they drift."""

    def test_covered_and_not_covered_are_disjoint_and_complete(self):
        # WIDENED 2026-08-25: the tables now carry a second-ledger key (the
        # agent instruments' proposer), so "every outcome" is every ledger
        # this product ships, read off the specs rather than assumed.
        declared = set()
        for _p in diagnosis.known_ledgers():
            declared |= set(diagnosis.spec_at(_p).declared_outcomes())
        covered = set(propose.COVERAGE)
        explained = set(propose.NOT_COVERED)
        self.assertEqual(covered & explained, set())
        self.assertEqual(covered | explained, declared)

    def test_the_covered_list_is_still_the_proposer_table(self):
        self.assertEqual(set(propose.COVERAGE), set(propose.PROPOSERS))

    def test_every_reason_is_still_more_than_a_shrug(self):
        for outcome, reason in propose.NOT_COVERED.items():
            with self.subTest(outcome=outcome):
                self.assertGreater(len(reason.split()), 12, outcome)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
