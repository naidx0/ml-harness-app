"""The fine-tune stops at a trial, or it runs and is scored - and which, is read.

`_propose_train_the_adapter` stopped before the fine-tune for one reason,
stated in every proposal it drew: **nothing in this harness could score what it
trained.** That was true, it was computed off two rosters rather than asserted,
and it carried a canary so that the day it stopped being true somebody would
have to re-read it.

**IT STOPPED BEING TRUE AND THE CANARY DID NOT CATCH IT.** `score_the_adapter`
registered; it does not read `providers`, which is exactly why it can be pointed
at an adapter, so it never appeared in the roster of tools that score a model;
`recipes/hf-peft-lora/recipe.toml` grew `kinds = ["train", "eval"]`, which made
the sentence's own sub-clause true while its headline - *THE THING THAT WOULD
SCORE THE ADAPTER DOES NOT EXIST IN THIS HARNESS* - went false. A false headline
in every training proposal, computed from two correct readings of two correct
rosters. That is the failure this file is about, and the fix is a third roster
that answers the question the headline was actually asking.

**AND THE BUILD IS NOW TWO BUILDS.** The instrument existing is not the whole
of it: `score_the_adapter` scores an adapter on the rows a COMPLETED EVAL RUN
already graded, so a conversation with no such run has nothing to compare
against. `measure_baseline` clears G1 and keeps no rows, so that is a real and
common state rather than a corner. With a run, the fine-tune runs and is scored
and **the exit criterion becomes the real one**. Without, the bounded trial is
drawn exactly as it was, and the plan names `run_eval` as the one step that
would unlock the other - which is a thing a person can do today, where "no tool
ships" was a thing they could only wait for.

The thing this file exists to stop is the opposite mistake: a build that claims
an exit criterion it cannot check. So every assertion below about the scored
variant is about the criterion being CHECKABLE - the subject is a path into a
payload the tool really produces, the threshold is derived from arithmetic the
plan prints, and the step's own criterion is a different sentence from the
build's.
"""

from __future__ import annotations

import json
import sys
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import diagnosis_fixtures

from app import diagnosis, events
from app.tools import REGISTRY, evals, propose

import support


class TrainingSituationTestCase(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        support.pin_a_training_recipe(propose.THE_LORA_RECIPE)
        self.thread = events.create_thread("a conversation that measured a baseline")

    # -- the files -------------------------------------------------------

    def eval_file(self, rows: int = 100, name: str = "eval.jsonl") -> Path:
        path = self.root / name
        path.write_text(
            "\n".join(
                json.dumps({"q": f"question {i}", "a": "yes"}) for i in range(rows)
            ),
            encoding="utf-8",
        )
        return path

    def training_file(self, rows: int = 200, name: str = "train.jsonl") -> Path:
        path = self.root / name
        path.write_text(
            "\n".join(
                json.dumps({"text": f"a training example, number {i}"})
                for i in range(rows)
            ),
            encoding="utf-8",
        )
        return path

    # -- a stored eval run, written the way run_eval writes one ----------

    def a_completed_run(self, eval_path: Path, *, thread_id: int | None = None) -> dict:
        """A real row in the eval bench's own tables.

        Through `evals.create_run` / `evals.record_row` rather than by calling
        `run_eval`, because `run_eval` needs somebody's model running and this
        file is about the plan drawn afterwards. Every column that decides
        anything here - the thread, the eval path, whether it is complete - is
        the real one.
        """
        run = evals.create_run(
            thread_id=int(thread_id if thread_id is not None else self.thread["id"]),
            signature="a-baseline",
            eval_path=str(eval_path),
            eval_fingerprint="fingerprint",
            input_field="q",
            expected_field="a",
            metric=evals.EXACT_MATCH,
            prompt="",
            prompt_is_default=1,
            provider_id=None,
            provider_name="ollama",
            model="granite4-hermes:latest",
            locality="local",
            judge_model=None,
            planned=100,
            rows_available=100,
            trivial_baseline=0.5,
            trivial_answer="yes",
            latency_budget_ms=None,
        )
        for index in range(100):
            right = bool(index % 2)
            evals.record_row(
                int(run["id"]),
                index,
                question=f"question {index}",
                expected="yes",
                answer="yes" if right else "no",
                correct=right,
                verdicts={"exact_match": right},
                failure_mode=None if right else "wrong_facts",
                graded_by=evals.EXACT_MATCH,
                seconds=0.1,
            )
        return dict(run)

    # -- the situation ---------------------------------------------------

    def situation(self, **over) -> propose.Situation:
        facts = over.pop("facts", {})
        sheet = dict(diagnosis_fixtures.MINTING["TRAIN__LORA_SFT"])
        sheet.update(facts)
        result = diagnosis.diagnose(sheet)
        self.assertEqual(result.outcome, "TRAIN__LORA_SFT")
        values = {n: getattr(v, "value", v) for n, v in sheet.items()}
        evaluation = over.pop("eval_path", None) or str(self.eval_file())
        base = dict(
            outcome=result.outcome,
            result=result,
            values=values,
            origins=dict(result.fact_origins),
            hows={
                "eval_size_n": f"counted {values['eval_size_n']} rows in {evaluation}"
            },
            dataset_path=str(self.training_file()),
            eval_path=evaluation,
            base_model="Qwen/Qwen3-4B",
            max_seq_len=512,
        )
        base.update(over)
        return propose.Situation(**base)

    def plan(self, **over):
        return propose.propose(self.situation(**over))

    def scored_plan(self, **over):
        """The plan drawn when there IS a completed run over this eval file."""
        evaluation = str(self.eval_file())
        self.a_completed_run(Path(evaluation))
        return self.plan(
            eval_path=evaluation, thread_id=int(self.thread["id"]), **over
        )


# ---------------------------------------------------------------------------
# The sentence that went false.


class TheSentenceIsTrueInBothDirectionsTest(TrainingSituationTestCase):
    def test_the_third_roster_answers_the_question_the_headline_was_asking(self):
        """`score_the_adapter` is a scorer and is not in the scorer roster.

        Both of those are correct and together they are how the old sentence
        went false. The `providers` check is what makes this a reading rather
        than a name lookup: a tool by that name that talked to a connection
        would be in the other roster and not this one.
        """
        spec = REGISTRY.get(propose.THE_ADAPTER_SCORER)
        if spec is None:  # pragma: no cover - the sibling's tool is absent
            self.assertFalse(propose.the_adapter_scorer_is_registered())
            self.skipTest("score_the_adapter is not registered in this process")
        self.assertNotIn(propose.THE_SCORING_READ, spec.reads)
        self.assertNotIn(propose.THE_ADAPTER_SCORER, propose.tools_that_score_a_model())
        self.assertIn(propose.THE_ADAPTER_SCORER, propose.tools_that_score_an_adapter())

    def test_the_sentence_does_not_claim_an_absence_that_has_ended(self):
        said = propose.why_the_full_run_is_not_drawn()
        if propose.the_adapter_scorer_is_registered():
            self.assertNotIn("DOES NOT EXIST IN THIS HARNESS", said)
            self.assertIn(propose.THE_ADAPTER_SCORER, said)
        else:  # pragma: no cover - reached only where the sibling's tool is absent
            self.assertIn("DOES NOT EXIST IN THIS HARNESS", said)
        # Both halves still name the rosters they read, whichever branch ran.
        for name in propose.tools_that_score_a_model():
            self.assertIn(name, said)
        self.assertIn(propose.THE_SCORING_READ, said)

    def test_the_sentence_is_in_the_plan_it_is_about(self):
        self.assertIn(propose.why_the_full_run_is_not_drawn(), self.plan().because)


# ---------------------------------------------------------------------------
# Which build you get, and why.


class WhichBuildYouGetIsReadNotAskedTest(TrainingSituationTestCase):
    def test_no_completed_run_means_the_trial_and_the_steps_are_unchanged(self):
        plan = self.plan()
        self.assertEqual(plan.id, "lora_trial_run")
        self.assertEqual(
            [(step.id, step.tool) for step in plan.steps],
            [
                ("rank", "find_models"),
                ("config", "read_model_config"),
                ("fits", "can_this_machine_train"),
                ("leak", "check_split_leakage"),
                ("sandbox", "make_sandbox"),
                ("trial", "run_in_sandbox"),
            ],
        )
        self.assertEqual(plan.exit_criterion.subject, "trial.exit_code")

    def test_the_trial_names_the_one_step_that_would_unlock_the_comparison(self):
        """The difference between "wait for us" and "do this now"."""
        if not propose.the_adapter_scorer_is_registered():  # pragma: no cover
            self.skipTest("score_the_adapter is not registered in this process")
        stated = self.plan().exit_criterion.stated
        self.assertIn("THE INSTRUMENT IS HERE", stated)
        self.assertIn("run_eval", stated)
        self.assertIn("measure_baseline scores and stamps and keeps no rows", stated)

    def test_a_run_over_a_different_file_is_not_a_baseline_for_this_one(self):
        """The `eval_size_n` subject defect, where being wrong costs a GPU."""
        other = self.eval_file(name="somebody-elses.jsonl")
        self.a_completed_run(other)
        plan = self.plan(thread_id=int(self.thread["id"]))
        self.assertEqual(plan.id, "lora_trial_run")

    def test_a_run_in_another_conversation_is_not_this_conversations_baseline(self):
        evaluation = str(self.eval_file())
        elsewhere = events.create_thread("a different conversation")
        self.a_completed_run(Path(evaluation), thread_id=int(elsewhere["id"]))
        plan = self.plan(eval_path=evaluation, thread_id=int(self.thread["id"]))
        self.assertEqual(plan.id, "lora_trial_run")

    def test_an_incomplete_run_is_not_a_baseline(self):
        """A partial score is not a score, and it is not something to beat."""
        evaluation = str(self.eval_file())
        run = evals.create_run(
            thread_id=int(self.thread["id"]),
            signature="half-done",
            eval_path=evaluation,
            eval_fingerprint="fingerprint",
            input_field="q",
            expected_field="a",
            metric=evals.EXACT_MATCH,
            prompt="",
            prompt_is_default=1,
            provider_id=None,
            provider_name="ollama",
            model="m",
            locality="local",
            judge_model=None,
            planned=100,
            rows_available=100,
            trivial_baseline=0.5,
            trivial_answer="yes",
            latency_budget_ms=None,
        )
        evals.record_row(
            int(run["id"]), 0, question="q", expected="yes", answer="yes",
            correct=True, verdicts={"exact_match": True}, failure_mode=None,
            graded_by=evals.EXACT_MATCH, seconds=0.1,
        )
        self.assertFalse(evals.read(int(run["id"]))["complete"])
        self.assertIsNone(
            propose.the_baseline_run_to_beat(int(self.thread["id"]), evaluation)
        )
        self.assertEqual(
            self.plan(eval_path=evaluation, thread_id=int(self.thread["id"])).id,
            "lora_trial_run",
        )

    def test_the_adapters_own_arm_does_not_become_the_next_baseline(self):
        """THE FINE-TUNE MAY NOT BE PAIRED AGAINST THE LAST FINE-TUNE.

        `score_the_adapter` keeps the adapter's and the base model's graded rows
        in the eval bench's own tables, which is right - that is where graded
        rows live, it is what makes the comparison reproducible, and
        `_store_an_arm`'s docstring is correct that the row cannot be mistaken
        for the baseline `G1_BASELINE_MEASURED` reads.

        It could be mistaken for the baseline THIS FILE reads. Measured before
        the fix: after one scoring run, `the_baseline_run_to_beat` returned the
        adapter's own arm - newest, complete, same eval file - so the next
        training proposal would have planned a fine-tune to beat the previous
        fine-tune, at its sandbox score, while printing the connection the
        baseline was supposedly measured through.
        """
        from app.tools import training

        evaluation = str(self.eval_file())
        real = self.a_completed_run(Path(evaluation))
        before = propose.the_baseline_run_to_beat(int(self.thread["id"]), evaluation)
        self.assertEqual(int(before["run_id"]), int(real["id"]))

        rows = [
            {"row_index": index, "input": f"question {index}", "expected": "yes"}
            for index in range(100)
        ]
        arm = training._store_an_arm(
            arm="adapter",
            thread_id=int(self.thread["id"]),
            baseline={
                "run_id": int(real["id"]), "eval_path": evaluation,
                "input_field": "q", "expected_field": "a",
                "metric": evals.EXACT_MATCH,
            },
            chosen={"rows": rows, "fingerprint": "fingerprint", "available": 100},
            answers={index: {"answer": "yes"} for index in range(100)},
            model_name="a base model + LoRA",
            prompt_template="{input}",
            where=str(self.root / "adapter"),
        )
        # It really is a complete run over this file, and it really does score
        # higher - so nothing but the mark distinguishes it.
        self.assertTrue(arm["complete"])
        self.assertGreater(arm["score"], evals.read(int(real["id"]))["score"])
        self.assertGreater(int(arm["run_id"]), int(real["id"]))
        self.assertFalse(evals.was_measured_through_a_connection(arm))

        after = propose.the_baseline_run_to_beat(int(self.thread["id"]), evaluation)
        self.assertEqual(int(after["run_id"]), int(real["id"]))
        plan = self.plan(eval_path=evaluation, thread_id=int(self.thread["id"]))
        self.assertEqual(
            plan.step("score").arguments["baseline_run_id"], int(real["id"])
        )

    def test_the_thread_is_not_an_argument_anybody_can_send(self):
        """It comes from the instrument, so a caller cannot point this at
        somebody else's eval runs by naming a number."""
        properties = set(REGISTRY.get("propose_build").schema["properties"])
        self.assertNotIn("thread_id", properties)
        self.assertNotIn("baseline_run_id", properties)


# ---------------------------------------------------------------------------
# The scored build.


@unittest.skipUnless(
    propose.the_adapter_scorer_is_registered(),
    "score_the_adapter is not registered in this process",
)
class TheScoredBuildIsHeldToTheRealCriterionTest(TrainingSituationTestCase):
    def test_the_score_step_is_appended_and_waits_for_the_training(self):
        plan = self.scored_plan()
        self.assertEqual(plan.id, "lora_run_and_score")
        self.assertEqual(
            [(step.id, step.tool) for step in plan.steps][-2:],
            [("trial", "run_in_sandbox"), ("score", propose.THE_ADAPTER_SCORER)],
        )
        self.assertEqual(set(plan.step("score").needs), {"trial", "sandbox"})
        self.assertEqual(plan.waves()[-1], ("score",))

    def test_it_scores_in_the_sandbox_this_plan_made(self):
        """A `Ref`, so the executor cannot score in whichever one is newest."""
        referenced = dict(self.scored_plan().step("score").refs())
        self.assertIn("sandbox", referenced)
        self.assertEqual(referenced["sandbox"].step, "sandbox")
        self.assertEqual(referenced["sandbox"].output, "sandbox_name")

    def test_it_names_the_run_it_found_rather_than_the_newest_one(self):
        evaluation = str(self.eval_file())
        wanted = self.a_completed_run(Path(evaluation))
        # A later run over a DIFFERENT file must not be the one chosen.
        self.a_completed_run(self.eval_file(name="other.jsonl"))
        plan = self.plan(eval_path=evaluation, thread_id=int(self.thread["id"]))
        self.assertEqual(
            plan.step("score").arguments["baseline_run_id"], int(wanted["id"])
        )

    def test_the_control_arm_is_passed_rather_than_left_to_a_default(self):
        arguments = self.scored_plan().step("score").arguments
        self.assertIs(arguments["include_base"], True)

    def test_the_step_criterion_is_that_it_finished_not_that_it_won(self):
        criterion = self.scored_plan().step("score").exit_criterion
        self.assertEqual(criterion.subject, "adapter_score.complete")
        self.assertEqual(criterion.comparator, "is_true")
        self.assertTrue(criterion.met({"adapter_score": {"complete": True}}).ok)
        self.assertFalse(criterion.met({"adapter_score": {"complete": False}}).ok)
        self.assertFalse(criterion.met({"adapter_score": None}).ok)
        self.assertFalse(criterion.met({}).ok)

    def test_the_build_criterion_is_the_real_one_and_its_threshold_is_derived(self):
        """`floor / paired_rows` - the smallest improvement THE COMPARED rows resolve.

        Not a number this file chose: `discordant_rows_that_could_resolve(1)` is
        how many rows must change verdict before McNemar's exact test can reach
        0.05 at all, and a change of that many out of the rows both runs graded
        IS that delta. The same arithmetic the plan prints, in the units
        evals.compare answers in.

        The denominator is the BASELINE RUN'S GRADED COUNT and not
        `eval_size_n`; here the staged run graded all hundred rows, so the two
        coincide and the case where they do not is the test below.
        """
        plan = self.scored_plan()
        floor = propose.discordant_rows_that_could_resolve(1)
        rows = diagnosis_fixtures.MINTING["TRAIN__LORA_SFT"]["eval_size_n"].value
        self.assertEqual(plan.exit_criterion.subject, "score.delta")
        self.assertEqual(plan.exit_criterion.comparator, "at_least")
        self.assertEqual(plan.exit_criterion.value, float(Fraction(floor, rows)))
        self.assertIn(f"{floor} / {rows}", plan.exit_criterion.stated)

    # -- the denominator, which was the wrong one ------------------------

    def a_sampled_run(self, eval_path: Path, *, graded: int, correct_every: int = 2):
        """A COMPLETE eval run that graded a SAMPLE of the file.

        This is what `run_eval` does by default: `evals.DEFAULT_EVAL_SAMPLE` is
        50, so a run over a longer file is complete and pairs on fifty rows.
        """
        run = evals.create_run(
            thread_id=int(self.thread["id"]), signature=f"sampled-{graded}",
            eval_path=str(eval_path), eval_fingerprint="fingerprint",
            input_field="q", expected_field="a", metric=evals.EXACT_MATCH,
            prompt="", prompt_is_default=1, provider_id=None,
            provider_name="ollama", model="m", locality="local", judge_model=None,
            planned=graded, rows_available=1000, trivial_baseline=0.5,
            trivial_answer="yes", latency_budget_ms=None,
        )
        for index in range(graded):
            right = index % correct_every == 0
            evals.record_row(
                int(run["id"]), index, question=f"question {index}", expected="yes",
                answer="yes" if right else "no", correct=right,
                verdicts={"exact_match": right},
                failure_mode=None if right else "wrong_facts",
                graded_by=evals.EXACT_MATCH, seconds=0.1,
            )
        self.assertTrue(evals.read(int(run["id"]))["complete"])
        return run

    def test_the_threshold_is_over_the_rows_that_are_compared_not_the_file(self):
        """THE DEFECT THIS TEST EXISTS FOR, driven end to end.

        `evals.compare` measures its delta over the rows both runs graded, and
        `score_the_adapter` answers exactly the rows the baseline run graded. So
        a threshold divided by the FILE's row count is a threshold about a
        different measurement than the one the storm will take. Measured before
        the fix: a 400-row file behind a default 50-row `run_eval` produced
        `value=0.015` (6/400), and one row of fifty improving - McNemar p=1.0,
        the tool's own words for no evidence at all - satisfied a criterion
        whose printed sentence said six rows had to change.
        """
        evaluation = self.eval_file(rows=400, name="four-hundred.jsonl")
        graded = evals.DEFAULT_EVAL_SAMPLE
        self.a_sampled_run(evaluation, graded=graded)
        plan = self.plan(
            eval_path=str(evaluation),
            thread_id=int(self.thread["id"]),
            facts={"eval_size_n": diagnosis.measured(400)},
        )
        self.assertEqual(plan.id, "lora_run_and_score")
        floor = propose.discordant_rows_that_could_resolve(1)
        self.assertEqual(plan.exit_criterion.value, float(Fraction(floor, graded)))
        self.assertNotEqual(plan.exit_criterion.value, float(Fraction(floor, 400)))
        self.assertIn(f"{floor} / {graded}", plan.exit_criterion.stated)
        # And the plan says which count it used and why, rather than leaving
        # the reader to divide.
        self.assertIn(f"denominator is {graded} and not the 400 rows", plan.exit_criterion.stated)

    def test_a_delta_the_compared_rows_cannot_resolve_fails_the_criterion(self):
        """The whole point of the denominator, expressed as pass and fail.

        `floor` rows changing out of the paired set is exactly where McNemar's
        exact test first reaches 0.05, so that is where this criterion first
        passes - and every smaller number of rows, which the old threshold
        accepted, now fails.
        """
        evaluation = self.eval_file(rows=400, name="four-hundred.jsonl")
        graded = evals.DEFAULT_EVAL_SAMPLE
        self.a_sampled_run(evaluation, graded=graded)
        criterion = self.plan(
            eval_path=str(evaluation),
            thread_id=int(self.thread["id"]),
            facts={"eval_size_n": diagnosis.measured(400)},
        ).exit_criterion
        floor = propose.discordant_rows_that_could_resolve(1)
        for changed in range(1, floor):
            delta = changed / graded
            self.assertGreater(evals.mcnemar(changed, 0), propose.RESOLVED_AT)
            self.assertFalse(
                criterion.met({"score": {"delta": delta}}).ok,
                f"{changed} of {graded} rows (McNemar p={evals.mcnemar(changed, 0)}) passed",
            )
        self.assertLessEqual(evals.mcnemar(floor, 0), propose.RESOLVED_AT)
        self.assertTrue(criterion.met({"score": {"delta": floor / graded}}).ok)

    def test_a_run_whose_rows_could_not_resolve_anything_is_not_scored_against(self):
        """A completed run can exist and still be no use, and that is said.

        With the right denominator a tiny paired set produces a DEMANDING
        threshold rather than a lenient one - which is the correct direction and
        is also a build drawn to fail. So the plan falls back to the trial and
        names the row count that made it, instead of planning a GPU run whose
        comparison could only come back NO EVIDENCE.
        """
        evaluation = self.eval_file(rows=400, name="four-hundred.jsonl")
        # Eight rows graded, seven of them right: one row is wrong, and the
        # floor is six, so no adapter could reach it.
        self.a_sampled_run(evaluation, graded=8, correct_every=1)
        plan = self.plan(
            eval_path=str(evaluation),
            thread_id=int(self.thread["id"]),
            facts={"eval_size_n": diagnosis.measured(400)},
        )
        self.assertEqual(plan.id, "lora_trial_run")
        stated = plan.exit_criterion.stated
        self.assertIn("COULD NOT RESOLVE THE COMPARISON", stated)
        self.assertIn("graded 8 of the 400 rows", stated)
        self.assertIn("run_eval", stated)
        # And it does NOT claim the conversation has no run in it, which is
        # what the old sentence would have said about this conversation.
        self.assertNotIn("HAS NOTHING FOR IT TO COMPARE AGAINST", stated)

    def test_the_criterion_refuses_a_delta_under_the_threshold_and_a_negative_one(self):
        criterion = self.scored_plan().exit_criterion
        floor = propose.discordant_rows_that_could_resolve(1)
        rows = diagnosis_fixtures.MINTING["TRAIN__LORA_SFT"]["eval_size_n"].value
        just_enough = float(Fraction(floor, rows))
        self.assertTrue(criterion.met({"score": {"delta": just_enough}}).ok)
        for worse in (just_enough / 2, 0.0, -just_enough):
            self.assertFalse(criterion.met({"score": {"delta": worse}}).ok, worse)
        # And a step that produced no delta at all does not pass by absence.
        self.assertFalse(criterion.met({"score": {}}).ok)
        self.assertFalse(criterion.met({}).ok)

    def test_the_criterion_says_the_threshold_is_necessary_and_not_sufficient(self):
        stated = self.scored_plan().exit_criterion.stated
        self.assertIn("NECESSARY CONDITION AND NOT A SUFFICIENT ONE", stated)
        self.assertIn("no_evidence", stated)

    def test_the_criterion_no_longer_says_nothing_can_check_it(self):
        stated = self.scored_plan().exit_criterion.stated
        self.assertNotIn("CANNOT CHECK THAT SENTENCE", stated)
        self.assertIn("CHECKABLE", stated)
        self.assertIn(propose.THE_ADAPTER_SCORER, stated)

    def test_nothing_in_the_scored_build_stamps_a_fact_a_gate_reads(self):
        """The sharpest case: an adapter's score is not the baseline G1 reads."""
        plan = self.scored_plan()
        for step in plan.steps:
            stamped = set(REGISTRY.get(step.tool).measures)
            if step.id == "card":  # inspect_hardware, and no gate reads any of it
                continue
            self.assertEqual(
                stamped & propose.gate_facts(), set(), f"{step.id} stamps a gate fact"
            )
        self.assertEqual(REGISTRY.get(propose.THE_ADAPTER_SCORER).measures, ())

    def test_the_scoring_step_spends_none_of_the_users_model(self):
        cost = self.scored_plan().step("score").cost
        for zero in (cost.model_tokens, cost.model_requests):
            self.assertEqual(zero.value, 0.0)
            self.assertIn(propose.THE_SCORING_READ, zero.how)
        self.assertEqual(cost.wall_clock.provenance, "UNKNOWN")

    def test_the_plan_says_the_comparison_crosses_two_instruments(self):
        plan = self.scored_plan()
        self.assertIn("two instruments", plan.step("score").why)
        self.assertIn("isolates", plan.step("score").why)

    def test_the_declared_outputs_are_where_the_scorer_actually_puts_them(self):
        """Checked against the payload builder, not against a shape this file wrote.

        `training._scoring_report` is the one function that assembles the
        reply, so it is the only honest oracle for a dotted path short of
        running a GPU. A key renamed in there turns this red instead of leaving
        a build whose criterion checks a path that is not in the payload.
        """
        from app.build import _dig
        from app.tools import training

        payload = training._scoring_report(
            sandbox_name="s",
            # A DICT, because that is what `find_the_adapter` returns and what
            # the report reads: it now compares the base model the adapter
            # RECORDS with the one it was scored against, and says so when they
            # disagree. A string here was a fixture that could not have caught
            # the argument being unused, which is how that went unnoticed.
            adapter={
                "path": "a",
                "base_model": "b",
                "made_in_this_sandbox": True,
                "found_by": "the newest run in this sandbox",
            },
            base="b",
            base_was_named=False,
            include_base=True,
            base_answers=2,
            chosen={"rows": [1, 2], "fingerprint": "f"},
            template="{input}",
            seconds=1.0,
            baseline={"run_id": 1, "eval_path": "e", "metric": "exact_match"},
            adapter_report={"complete": True, "graded": 2, "planned": 2, "score": 0.5,
                            "run_id": 10},
            base_report={"complete": True, "graded": 2, "planned": 2, "score": 0.4,
                         "run_id": 11},
            against_baseline={"ok": True, "says": "s", "delta": 0.1,
                              "verdict": "different"},
            against_base={"ok": True, "says": "s", "delta": 0.1,
                          "verdict": "different"},
            ran={"exit_code": 0, "timed_out": False, "timeout_seconds": 1,
                 "run_dir": "d", "interpreter": "p", "pinned": True,
                 "recipe": "r", "output": "", "reach": {}},
        )
        plan = self.scored_plan()
        for output in plan.step("score").produces:
            _, present = _dig(payload, output.at or output.name)
            self.assertTrue(present, f"{output.name} is not at {output.at!r}")
        _, present = _dig(payload, plan.step("score").exit_criterion.subject)
        self.assertTrue(present, "the step criterion checks a path that is not there")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
