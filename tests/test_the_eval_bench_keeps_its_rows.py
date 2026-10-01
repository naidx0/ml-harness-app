"""The evaluation bench: it runs, it keeps, it buckets, and it refuses.

`app/tools/evals.py` is the keystone - nothing in this product can be optimised
that cannot be measured, and before it the harness could count an eval set and
score a baseline once and nothing else. This file is the adversarial half of
that claim. It is organised around the four things the bench has to get right
and the one thing it has to refuse:

  RUN      - the rows reach the user's own model, through the adapters that
             already exist, under a prompt the caller chose.
  KEEP     - a row survives its run, so a later run can be compared to this one
             and so an interruption costs one row and not the afternoon.
  BUCKET   - the failures land in the engine's own routable modes, by rules a
             person can reproduce, and `failure_histogram` arrives MEASURED.
             `TheHistogramIsWhatRoutesStageOneTest` is the pay-off: the same
             fact sheet reaches four different outcomes depending only on the
             histogram this bench produced.
  RESOLVE  - every score carries what that many rows can tell apart.
  REFUSE   - and this is the one that makes the product different from a prompt
             playground. `TheRefusalIsThePointTest` puts a real improvement in
             front of the comparison on too few rows and demands the words NO
             EVIDENCE back.

Nothing here uses a network. `ScriptedModel` answers from the question text, so
every number asserted below is arithmetic over a file this module wrote - which
is the same discipline `tests/test_no_tool_can_mint_a_measurement.py` uses and
the reason the assertions can be exact.

The live half - a real eval against granite4-hermes on the running Ollama, on a
scratch database - is not in this file, because a test that needs somebody's
model running is a test that fails on a fresh checkout. It was run by hand and
its numbers are in the commit that added this file.
"""

from __future__ import annotations

import json
import re
import time
import unittest
from pathlib import Path

import diagnosis_fixtures as fixtures

from app import db, diagnosis, events
from app.providers import Delta, store as provider_store
from app.tools import REGISTRY, evals, evidence
from app.tools.evidence import MEASURED, MODEL, USER

import support


LABELS = ("yes", "no", "maybe", "never", "always")


def eval_file(root: Path, rows: int = 40, name: str = "eval.jsonl") -> Path:
    """`rows` questions with a five-label answer column, in equal proportion.

    The trivial baseline is therefore exactly `1 / 5` and every count below is a
    property of this function rather than of anything that had to be run.
    """
    path = Path(root) / name
    path.write_text(
        "\n".join(
            json.dumps({"q": f"q{i}", "a": LABELS[i % len(LABELS)]})
            for i in range(rows)
        ),
        encoding="utf-8",
    )
    return path


class ScriptedModel:
    """Right on the first `correct` rows, then one failure shape per bucket.

    The four shapes after `correct` cycle so that a run of any length has all of
    them: a refusal, the right answer wrapped in a sentence (`wrong_format`), a
    different member of the label set (`wrong_facts`), and something no rule can
    name (`unclassified`). That last one is deliberate - a bucketer with nothing
    it will not classify is a bucketer that guesses.

    IT ALSO GRADES, when it is handed `evals.JUDGE_SYSTEM`, and that is not a
    convenience: with no `judge_provider_id` the bench builds the judge from the
    same connection, so ONE object answering both prompts is exactly the shape
    the honesty machinery is about - the model that produced the answers is the
    model grading them.
    """

    def __init__(
        self,
        correct: int = 20,
        fail_at: int | None = None,
        verdict: str = "CORRECT",
        delay: float = 0.0,
    ) -> None:
        self.correct = correct
        self.fail_at = fail_at
        self.verdict = verdict
        self.delay = delay
        self.asked: list[str] = []
        self.judged: list[str] = []

    def _index(self, question: str) -> int:
        digits = re.sub(r"\D", "", str(question))
        return int(digits or 0)

    def stream(self, conversation, offered=None, *, secret=None):
        if conversation[0]["content"] == evals.JUDGE_SYSTEM:
            self.judged.append(conversation[-1]["content"])
            yield Delta(kind="text", text=self.verdict)
            return
        question = conversation[-1]["content"]
        self.asked.append(question)
        if self.delay:
            time.sleep(self.delay)
        index = self._index(question)
        if self.fail_at is not None and index >= self.fail_at:
            yield Delta(kind="error", detail="the endpoint went away")
            return
        if index < self.correct:
            yield Delta(kind="text", text=LABELS[index % len(LABELS)])
        elif index % 4 == 0:
            yield Delta(kind="text", text="I'm sorry, I cannot answer that.")
        elif index % 4 == 1:
            yield Delta(kind="text", text=f"The answer is {LABELS[index % len(LABELS)]}.")
        elif index % 4 == 2:
            yield Delta(kind="text", text=LABELS[(index + 1) % len(LABELS)])
        else:
            yield Delta(kind="text", text="banana split with sprinkles")


class EvalBenchTest(unittest.TestCase):
    """Sandbox, one local connection, two conversations."""

    def setUp(self) -> None:
        self.root = support.sandbox(self)
        self.threads = support.conversations(2)
        self.thread = self.threads[0]["id"]
        self.other = self.threads[1]["id"]
        self.path = eval_file(self.root)
        row = provider_store.create(
            "Scripted", "http://127.0.0.1:11434", "scripted", "ollama"
        )
        provider_store.set_active(row["id"])
        self.provider = row

    def connect(self, model):
        """Point the bench at a scripted model, and put `build` back afterwards."""
        original = evals.build
        evals.build = lambda adapter, base_url, name: model
        self.addCleanup(lambda: setattr(evals, "build", original))
        return model

    def run_eval(self, thread=None, **arguments):
        payload = {
            "eval_path": str(self.path),
            "input_field": "q",
            "expected_field": "a",
            "sample": 40,
        }
        payload.update(arguments)
        return REGISTRY.call(
            "run_eval", payload, actor=MODEL, thread_id=thread or self.thread
        )


# ---------------------------------------------------------------------------


class TheToolSurfaceIsDeclaredTest(EvalBenchTest):
    """What the bench may stamp, and what it may never be asked for."""

    def test_run_eval_measures_only_facts_the_ledger_admits_measured(self):
        spec = diagnosis.default_spec()
        declared = REGISTRY.get("run_eval").measures
        self.assertEqual(
            sorted(declared),
            [
                "baseline_measured",
                "baseline_score",
                "failure_histogram",
                #: The histogram's denominator. `S1_CLASSIFICATION_IS_TOO_THIN`
                #: divides by it, and without it a twenty-bucket histogram over
                #: forty-seven failing rows reads the same as one over twenty.
                "failures_seen",
                "trivial_baseline_score",
            ],
        )
        for fact in declared:
            with self.subTest(fact=fact):
                self.assertIn(MEASURED, spec.admissible_for(fact))
                self.assertNotEqual(spec.facts[fact].get("source"), "ask")

    def test_the_bench_was_the_first_tool_that_could_measure_a_failure_histogram(self):
        """The hole this module was written to close, asserted as a hole.

        `failure_histogram` is `source: derive`, which admits MEASURED and
        nothing else, so before `run_eval` no origin any caller could produce
        would do - and stage 1 of the tree terminated in
        `ACTION__CLASSIFY_FAILURES` for everybody.

        RENAMED "is" -> "was" ON 2026-08-28, because a second one arrived.
        `rebucket_failures` re-tallies the rows this bench graded using the
        person's own reading, and `evidence.resolves` now offers that one first -
        which is right, because re-running this bench returns the identical
        buckets and the outcome that asks for a corrected histogram needs a
        DIFFERENT answer, not the same one again.

        What this bench still owns is unchanged and is what the rest of the file
        is about: it is the instrument that produces a histogram from a graded
        run in the first place, and nothing can correct what was never measured.
        """
        spec = diagnosis.default_spec()
        self.assertEqual(spec.facts["failure_histogram"]["source"], "derive")
        self.assertEqual(sorted(spec.admissible_for("failure_histogram")), [MEASURED])
        self.assertEqual(
            sorted(t.name for t in REGISTRY if "failure_histogram" in t.measures),
            ["rebucket_failures", "run_eval"],
        )
        # The bench is still named - as the alternative, since a re-tally is the
        # answer to "the buckets were wrong" and a re-run is not.
        resolved = evidence.resolves("failure_histogram")
        self.assertEqual(resolved["tool"], "rebucket_failures")
        self.assertIn("run_eval", resolved["also"])

    def test_the_shortest_route_to_a_baseline_is_still_measure_baseline(self):
        """Two tools measure G1's facts now, and the honest next step is the
        smaller one. `resolves` sorts by how little a tool asks of the user, so
        adding a bench that also scores must not push somebody blocked on G1
        towards the tool with eleven arguments."""
        for fact in ("baseline_measured", "baseline_score", "trivial_baseline_score"):
            with self.subTest(fact=fact):
                route = evidence.resolves(fact)
                self.assertEqual(route["tool"], "measure_baseline")
                self.assertIn("run_eval", route["also"])

    def test_read_eval_results_can_stamp_nothing_at_all(self):
        self.assertEqual(REGISTRY.get("read_eval_results").measures, ())
        self.assertEqual(REGISTRY.get("read_eval_results").writes, ())

    def test_a_run_needs_a_conversation_to_belong_to(self):
        self.assertTrue(evidence.thread_is_required_by("run_eval"))
        refused = evals.run(
            eval_path=str(self.path),
            input_field="q",
            expected_field="a",
            thread_id=None,
        )
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "no_thread")

    def test_the_declared_bounds_are_the_ones_that_could_never_be_an_answer(self):
        """WALL 6, and it is load-bearing rather than decorative here.

        `rerun=true` puts the boolean `True` in the arguments, and
        `baseline_measured` IS `True`; the three numeric bounds can each be sent
        as `1`, which is the score of a run that got everything right. Without
        the declaration those are false refusals on honest measurements.
        """
        self.assertEqual(
            sorted(REGISTRY.get("run_eval").bounds),
            ["deadline_seconds", "latency_budget_ms", "rerun", "sample"],
        )
        for name in REGISTRY.get("run_eval").bounds:
            self.assertIn(name, REGISTRY.get("run_eval").schema["properties"])

    def test_a_perfect_run_asked_to_rerun_still_stamps(self):
        """The bound above, exercised where it bites: `rerun=True` beside a
        `baseline_measured` of `True`, and a score of exactly 1.0 beside a
        deadline that is SET.

        THE DEADLINE IS SIXTY SECONDS AND NOT ONE, and the difference is a
        race rather than a rule. What this test is about is that a re-run
        which finishes still stamps both facts; the deadline has to be
        present for that path to be the one under test, and it does not have
        to be tight. At one second it became a bet on how fast the machine
        grades forty scripted rows - won here, lost on the GitHub Windows
        runner, which graded 23 of 40 before the bound stopped it and left
        the run incomplete with nothing stamped. That is the deadline
        working, reported as this test failing.

        Nothing is loosened: every assertion below is unchanged, and a run
        that overruns sixty seconds is a real defect this would still catch.
        """
        self.connect(ScriptedModel(correct=40))
        first = self.run_eval()
        self.assertTrue(first["ok"])
        again = self.run_eval(rerun=True, deadline_seconds=60)
        self.assertTrue(again["ok"], again.get("detail"))
        self.assertEqual(again["score"], 1.0)
        stamped = {row["fact"] for row in again["measured_facts"]}
        self.assertIn("baseline_measured", stamped)
        self.assertIn("baseline_score", stamped)


class TheRunKeepsEveryRowTest(EvalBenchTest):
    """KEEP. The aggregate is what every other tool already gives you."""

    def test_a_run_stores_one_row_per_graded_row_with_its_verdicts(self):
        self.connect(ScriptedModel(correct=20))
        report = self.run_eval()
        self.assertTrue(report["ok"])
        self.assertTrue(report["complete"])
        self.assertEqual(report["graded"], 40)
        self.assertEqual(report["correct"], 20)
        self.assertEqual(report["score"], 0.5)

        rows = evals.results_for(report["run_id"])
        self.assertEqual(len(rows), 40)
        self.assertEqual([row["row_index"] for row in rows], list(range(40)))
        for row in rows:
            with self.subTest(row=row["row_index"]):
                # EVERY deterministic metric on EVERY row, whatever the run was
                # scored on. The gap between them is what the bucketer reads and
                # what makes a model-graded score checkable.
                # DERIVED FROM THE METRIC LIST, not typed out beside it. This
                # read [CONTAINS, EXACT_MATCH] and went red the day `fields`
                # joined them - which is the right alarm on the wrong pin: the
                # property is "every deterministic metric", and the set of
                # those lives in `evals.METRICS`. `model_graded` is the one
                # that is not deterministic: it needs a judge, and a row that
                # had none carries no verdict from it.
                deterministic = sorted(
                    m for m in evals.METRICS if m != evals.MODEL_GRADED
                )
                self.assertEqual(sorted(row["verdicts"]), deterministic)
                self.assertEqual(row["graded_by"], evals.EXACT_MATCH)
                self.assertEqual(row["bucketed_by"], "rules")
                self.assertIsNotNone(row["seconds"])

    def test_every_other_metric_is_scored_on_the_same_rows_for_free(self):
        """And the arithmetic here is the argument against `contains` on its own.

        Twenty rows are right. Five more are the right answer inside a sentence,
        which is what `contains` is here to see. THE TWENTY-SIXTH IS THE POINT:
        one refusal - "I'm sorry, I cannot answer that" - is scored CORRECT by
        `contains` because the expected answer on that row is "no" and "cannot"
        contains it. That is a metric passing a refusal, on real text, in a
        forty-row file, and it is why `contains` is reported and never the
        default.
        """
        self.connect(ScriptedModel(correct=20))
        report = self.run_eval()
        self.assertEqual(report["scores"][evals.EXACT_MATCH], 0.5)
        self.assertEqual(report["scores"][evals.CONTAINS], 26 / 40)
        refusal_that_passed = [
            row
            for row in evals.results_for(report["run_id"])
            if row["verdicts"][evals.CONTAINS]
            and row["failure_mode"] == "refuses"
        ]
        self.assertEqual(len(refusal_that_passed), 1)
        self.assertEqual(refusal_that_passed[0]["expected"], "no")
        self.assertIn("cannot", refusal_that_passed[0]["answer"])

    def test_the_trivial_baseline_needs_no_model_and_is_the_majority_label(self):
        self.connect(ScriptedModel(correct=20))
        report = self.run_eval()
        self.assertAlmostEqual(report["trivial_baseline_score"], 1 / len(LABELS))
        self.assertIn(report["trivial_answer"], LABELS)

    def test_nothing_in_the_module_updates_or_deletes_a_stored_row(self):
        """Append-only, asserted against the source rather than against a habit.

        The migration promises it and `evals.py` is the only thing that writes
        these tables; a `status` column would be a second answer to "did it
        finish" and the two would disagree the first time a process died.
        """
        source = (
            Path(__file__).resolve().parents[1] / "app" / "tools" / "evals.py"
        ).read_text(encoding="utf-8")
        for verb in ("UPDATE eval_", "DELETE FROM eval_"):
            self.assertNotIn(verb, source, f"{verb} appeared in app/tools/evals.py")
        columns = {
            row[1]
            for row in db.connect().execute("PRAGMA table_info(eval_runs)")
        }
        self.assertNotIn("status", columns)
        self.assertNotIn("finished_at", columns)


class TheRunSurvivesBeingInterruptedTest(EvalBenchTest):
    """An eval over five hundred rows takes real time and a laptop closes."""

    def test_a_model_that_dies_halfway_keeps_the_rows_already_graded(self):
        self.connect(ScriptedModel(correct=40, fail_at=17))
        stopped = self.run_eval()
        self.assertFalse(stopped["ok"])
        self.assertEqual(stopped["error"], "model_failed")
        self.assertEqual(stopped["row_index"], 17)
        self.assertTrue(stopped["resumable"])
        self.assertEqual(stopped["graded"], 17)
        self.assertFalse(stopped["complete"])
        self.assertEqual(len(evals.results_for(stopped["run_id"])), 17)

    def test_an_interrupted_run_stamps_nothing_at_all(self):
        """`measure_baseline`'s rule, reused: a score from a run that fell over
        is not a score. Worse here, because the graded rows are a PREFIX of the
        file and a file sorted by label would make that prefix a lie."""
        self.connect(ScriptedModel(correct=40, fail_at=17))
        stopped = self.run_eval()
        self.assertNotIn("measured_facts", stopped)
        self.assertIn("nothing_was_recorded", stopped)
        self.assertIsNone(stopped["score"])
        self.assertAlmostEqual(stopped["partial_score"], 1.0)
        self.assertEqual(evidence.rows_for(self.thread), [])

    def test_running_it_again_continues_from_where_it_stopped(self):
        self.connect(ScriptedModel(correct=40, fail_at=17))
        stopped = self.run_eval()
        healthy = self.connect(ScriptedModel(correct=40))
        finished = self.run_eval()
        self.assertTrue(finished["ok"])
        self.assertEqual(finished["run_id"], stopped["run_id"])
        self.assertEqual(finished["graded"], 40)
        self.assertEqual(finished["rows_graded_now"], 23)
        # The seventeen rows already on disk were not asked a second time.
        self.assertEqual(len(healthy.asked), 23)

    def test_a_deadline_stops_cleanly_and_says_how_to_carry_on(self):
        self.connect(ScriptedModel(correct=40))
        stopped = self.run_eval(deadline_seconds=0)
        self.assertFalse(stopped["ok"])
        self.assertEqual(stopped["error"], "deadline")
        self.assertEqual(stopped["graded"], 0)
        self.assertIn("continues from where it stopped", stopped["detail"])
        self.assertIsNotNone(evals.get_run(stopped["run_id"]))

    def test_progress_goes_onto_the_append_only_spine(self):
        """The event id IS the SSE event id, which is what lets a client that
        reconnected mid-eval ask for everything after the last id it saw."""
        self.connect(ScriptedModel(correct=40))
        self.run_eval()
        kinds = [
            row["kind"] for row in events.since(f"thread:{self.thread}", 0, 500)
        ]
        self.assertIn(evals.STARTED, kinds)
        self.assertIn(evals.FINISHED, kinds)
        # Forty rows at a stride of twenty-five is one progress frame, not forty.
        self.assertEqual(kinds.count(evals.PROGRESS), 1)


class TheSameEvalIsNotBilledTwiceTest(EvalBenchTest):
    """Determinism and cost. A re-run must be recognisable rather than re-billed."""

    def test_an_identical_call_is_answered_from_disk_and_asks_nothing(self):
        model = self.connect(ScriptedModel(correct=20))
        first = self.run_eval()
        asked = len(model.asked)
        self.assertEqual(asked, 40)
        again = self.run_eval()
        self.assertTrue(again["reused"])
        self.assertEqual(again["run_id"], first["run_id"])
        self.assertEqual(len(model.asked), asked)
        self.assertIn("cost nothing", again["summary"])

    def test_rerun_spends_the_tokens_again_when_asked(self):
        model = self.connect(ScriptedModel(correct=20))
        self.run_eval()
        again = self.run_eval(rerun=True)
        self.assertFalse(again["reused"])
        self.assertEqual(len(model.asked), 80)

    def test_a_different_prompt_is_a_different_question(self):
        model = self.connect(ScriptedModel(correct=20))
        first = self.run_eval()
        second = self.run_eval(prompt="Answer with one word.")
        self.assertNotEqual(second["run_id"], first["run_id"])
        self.assertNotEqual(second["signature"], first["signature"])
        self.assertEqual(second["eval_fingerprint"], first["eval_fingerprint"])
        self.assertEqual(len(model.asked), 80)

    def test_a_changed_eval_file_is_a_different_eval_set(self):
        self.connect(ScriptedModel(correct=20))
        first = self.run_eval()
        eval_file(self.root, rows=40)  # same shape
        self.assertTrue(self.run_eval()["reused"])
        eval_file(self.root, rows=41)  # one more row
        changed = self.run_eval()
        self.assertFalse(changed["reused"])
        self.assertNotEqual(changed["eval_fingerprint"], first["eval_fingerprint"])

    def test_reuse_does_not_reach_into_another_conversation(self):
        """A stored run in another conversation is somebody else's measurement.
        Re-stamping it here would be the eval-set leak with a table in the way."""
        model = self.connect(ScriptedModel(correct=20))
        self.run_eval()
        elsewhere = self.run_eval(thread=self.other)
        self.assertFalse(elsewhere["reused"])
        self.assertEqual(len(model.asked), 80)


class TheFailuresAreBucketedByRuleTest(EvalBenchTest):
    """BUCKET. And what the rules will not guess at."""

    def test_each_failure_shape_lands_in_the_mode_it_belongs_to(self):
        self.connect(ScriptedModel(correct=20))
        report = self.run_eval()
        by_index = {row["row_index"]: row for row in evals.results_for(report["run_id"])}
        self.assertEqual(by_index[20]["failure_mode"], "refuses")
        # The right answer wrapped in a sentence.
        self.assertEqual(by_index[21]["failure_mode"], "wrong_format")
        # A different member of the vocabulary: a confident, well formed, wrong
        # answer, which is a CONTENT failure and routes to stage 3.
        self.assertEqual(by_index[22]["failure_mode"], "wrong_facts")
        # Not in the vocabulary at all: a SHAPE failure, and it routes to stage
        # 4. See `evals.bucket` - this rule is the one a real model made
        # necessary, and it is the same test as the line above read the other
        # way round.
        self.assertEqual(by_index[23]["failure_mode"], "wrong_format")
        self.assertIsNone(by_index[0]["failure_mode"])

    def test_every_key_in_the_histogram_is_one_the_engine_can_route(self):
        """`S1_ROUTE_BY_FAILURE_MODE` RAISES on a key it has no route for, so a
        bucket this bench invented would take down the diagnosis rather than the
        eval. The routable set is read off the spec, not listed."""
        self.connect(ScriptedModel(correct=20))
        report = self.run_eval()
        routable = set(evals.routable_modes())
        self.assertTrue(report["failure_histogram"])
        for mode in report["failure_histogram"]:
            self.assertIn(mode, routable)
        self.assertNotIn(evals.UNCLASSIFIED, routable)

    def test_a_closed_vocabulary_leaves_no_failure_unnamed(self):
        self.connect(ScriptedModel(correct=20))
        report = self.run_eval()
        self.assertEqual(report["unclassified"], 0)
        self.assertEqual(
            report["failure_histogram"],
            {"refuses": 5, "wrong_format": 10, "wrong_facts": 5},
        )
        self.assertEqual(report["failures_total"], 20)

    def test_a_free_text_failure_no_rule_can_name_is_counted_and_left_out(self):
        """The honest residue, and the direction it fails in.

        With no vocabulary to check against there is nothing a rule can say about
        a wrong free-text answer, so it is counted and kept out of the histogram
        rather than pushed into a bucket. That makes `sum(values())` an
        UNDER-count of failures, which routes to `ACTION__CLASSIFY_FAILURES` -
        go and bucket more - instead of to a stage chosen from a guess.
        """
        path = Path(self.root) / "freetext.jsonl"
        path.write_text(
            "\n".join(
                json.dumps({"q": f"q{i}", "a": f"a distinct sentence number {i}"})
                for i in range(20)
            ),
            encoding="utf-8",
        )

        class Wandering:
            def stream(self, conversation, offered=None, *, secret=None):
                yield Delta(kind="text", text="something else altogether")

        self.connect(Wandering())
        report = REGISTRY.call(
            "run_eval",
            {"eval_path": str(path), "input_field": "q", "expected_field": "a"},
            actor=MODEL,
            thread_id=self.thread,
        )
        self.assertEqual(report["score"], 0.0)
        self.assertEqual(report["unclassified"], 20)
        self.assertEqual(report["failure_histogram"], {})
        self.assertIn("no_histogram_recorded", report)

    def test_three_modes_are_never_assigned_by_any_rule_here(self):
        """`wrong_style` and `wrong_reasoning` need a judgement about meaning and
        `too_expensive` needs prices nothing in this product has. Guessing them
        would route somebody's whole diagnosis on a coin flip."""
        for answer in (
            "banana", "", "I'm sorry", "The answer is yes.", "no", "{}", "[1,2]",
        ):
            with self.subTest(answer=answer):
                mode = evals.bucket(
                    "yes", answer, evals.grade("yes", answer), frozenset(LABELS)
                )
                self.assertNotIn(
                    mode, ("wrong_style", "wrong_reasoning", "too_expensive")
                )

    def test_a_free_text_column_is_not_treated_as_a_label_set(self):
        """`wrong_facts` means a confident, well formed, WRONG answer, and the
        only way to see that from a rule is to know what a well formed answer
        looks like. Fifty distinct sentences over fifty rows is not a label set,
        and calling it one would bucket every free-text failure as wrong_facts."""
        self.assertTrue(evals._label_set(["a", "b", "a", "b", "a", "b"]))
        self.assertFalse(evals._label_set([f"sentence number {i}" for i in range(50)]))
        self.assertFalse(evals._label_set(["a", "b", "c", "d"]))

    def test_too_slow_is_never_assigned_without_a_budget(self):
        """There is no such thing as too slow until somebody says what fast
        enough is, and inventing one would be inventing a number."""
        self.connect(ScriptedModel(correct=40, delay=0.004))
        without = self.run_eval(sample=5)
        self.assertEqual(without["failure_histogram"], {})
        self.assertEqual(without["score"], 1.0)
        # Every row answers correctly and every row takes about four
        # milliseconds, so a one-millisecond budget makes all of them too slow -
        # which is the case `too_slow` is for: right answer, wrong speed.
        self.connect(ScriptedModel(correct=40, delay=0.004))
        with_budget = self.run_eval(sample=5, latency_budget_ms=1)
        self.assertEqual(with_budget["failure_histogram"], {"too_slow": 5})
        self.assertEqual(with_budget["score"], 1.0)

    def test_the_same_input_answered_two_ways_is_inconsistent(self):
        """A cross-row conclusion, derived at read time rather than stored: the
        second answer has not been written when the first row is committed."""
        path = Path(self.root) / "dupes.jsonl"
        path.write_text(
            "\n".join(json.dumps({"q": "q0", "a": "yes"}) for _ in range(4)),
            encoding="utf-8",
        )

        class HalfRight:
            def __init__(self):
                self.n = 0

            def stream(self, conversation, offered=None, *, secret=None):
                self.n += 1
                yield Delta(kind="text", text="yes" if self.n % 2 else "no")

        self.connect(HalfRight())
        report = REGISTRY.call(
            "run_eval",
            {"eval_path": str(path), "input_field": "q", "expected_field": "a"},
            actor=MODEL,
            thread_id=self.thread,
        )
        self.assertEqual(report["failure_histogram"], {"inconsistent": 2})
        stored = {row["failure_mode"] for row in evals.results_for(report["run_id"])}
        self.assertNotIn("inconsistent", stored)

    def test_an_empty_histogram_is_reported_and_never_stamped(self):
        """`inspect_hardware`'s doctrine: "the tool ran and found nothing" and
        "the tool did not run" are the same state of knowledge, and the ledger
        already defaults this fact to `{}`."""
        self.connect(ScriptedModel(correct=40))
        report = self.run_eval()
        self.assertEqual(report["failure_histogram"], {})
        self.assertIn("no_histogram_recorded", report)
        self.assertNotIn(
            "failure_histogram", {r["fact"] for r in report["measured_facts"]}
        )


class TheHistogramIsWhatRoutesStageOneTest(EvalBenchTest):
    """The pay-off. A measured histogram is worth more than the score.

    The same fact sheet reaches four different terminal outcomes depending only
    on the buckets, and with an empty histogram it reaches none of them - it
    stops at `ACTION__CLASSIFY_FAILURES`, which is where every run in this
    product stopped before this bench existed.
    """

    def sheet(self, histogram):
        base = dict(fixtures.MINTING["TRAIN__LORA_SFT"])
        base["failure_histogram"] = diagnosis.measured(histogram)
        return base

    def test_without_a_histogram_stage_one_can_only_ask_for_one(self):
        self.assertEqual(
            diagnosis.diagnose(self.sheet({})).outcome, "ACTION__CLASSIFY_FAILURES"
        )

    def test_the_dominant_bucket_decides_where_the_run_goes(self):
        for histogram, outcome in (
            ({"wrong_format": 25}, "NO_TRAIN__CONSTRAINED_DECODING"),
            ({"wrong_facts": 25}, "ACTION__STATE_KNOWLEDGE_VOLATILITY"),
            ({"wrong_style": 30}, "TRAIN__LORA_SFT"),
            ({"wrong_format": 10, "wrong_facts": 9, "refuses": 8}, "ACTION__SPLIT_THE_TASK"),
        ):
            with self.subTest(histogram=histogram):
                self.assertEqual(diagnosis.diagnose(self.sheet(histogram)).outcome, outcome)

    def test_a_histogram_this_bench_measured_is_the_one_the_engine_reads(self):
        """End to end: the eval runs, the rules bucket, the stamp lands MEASURED
        in this conversation, and the value the engine routes on is the value the
        rows produced."""
        self.connect(ScriptedModel(correct=20))
        report = self.run_eval()
        rows = [
            row
            for row in evidence.rows_for(self.thread)
            if row["fact"] == "failure_histogram"
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["origin"], MEASURED)
        self.assertEqual(rows[0]["tool"], "run_eval")
        self.assertEqual(rows[0]["value"], report["failure_histogram"])
        self.assertIn("bucketed by rule (never by a model)", rows[0]["how"])
        # And it is a legal fact sheet rather than something the engine chokes on.
        diagnosis.validate_facts(
            {"failure_histogram": rows[0]["value"]}, diagnosis.default_spec()
        )


class EveryScoreCarriesItsResolutionTest(EvalBenchTest):
    """RESOLVE. A score without its resolution is half a number."""

    def test_the_interval_is_never_zero_wide_on_a_perfect_score(self):
        """The normal approximation is exactly zero at p=1, so a run that scored
        forty out of forty would report +-0.0 points - an invented number in the
        most dangerous possible place. Wilson is why that cannot happen."""
        low, high = evals.wilson(40, 40)
        self.assertEqual(high, 1.0)
        self.assertLess(low, 1.0)
        self.assertGreater(low, 0.8)
        self.assertIsNone(evals.wilson(0, 0))

    def test_thirty_rows_resolves_about_what_the_spec_says_it_does(self):
        """`docs/PRODUCT_SPEC.md` says "n=30 only resolves differences larger
        than ~15 points". Computed rather than quoted: Wilson at n=30 and p=0.5
        is +-16.8 points, and the figure for a DIFFERENCE is larger because a
        difference has two errors in it. Both are reported, under names that say
        which is which."""
        block = evals.resolution_for(15, 30)
        self.assertAlmostEqual(block["half_width_points"], 16.85, places=1)
        self.assertGreater(
            block["resolves_a_difference_of_at_least_points"],
            block["half_width_points"],
        )
        self.assertEqual(block["rows_for_a_10_point_difference"], 193)

    def test_more_rows_resolve_more(self):
        wide = evals.resolution_for(15, 30)["half_width_points"]
        narrow = evals.resolution_for(150, 300)["half_width_points"]
        self.assertLess(narrow, wide)

    def test_every_report_carries_the_block_and_the_sentence(self):
        self.connect(ScriptedModel(correct=20))
        report = self.run_eval()
        self.assertIn("resolution", report)
        self.assertIn("95% confidence", report["resolution"]["says"])
        self.assertIn(report["resolution"]["says"], report["summary"])

    def test_the_stamped_score_carries_its_interval_in_its_own_account(self):
        """Invariant 3: a number with no provenance does not get displayed, and
        `how` is the sentence the interface shows next to it."""
        self.connect(ScriptedModel(correct=20))
        report = self.run_eval()
        how = next(
            row["how"] for row in report["measured_facts"] if row["fact"] == "baseline_score"
        )
        self.assertIn("95% interval", how)
        self.assertIn("20 of 40 rows", how)


class TheRefusalIsThePointTest(EvalBenchTest):
    """A prompt playground shows you 73% and 76% and lets you conclude."""

    def two_runs(self, first_correct, second_correct, rows=30):
        self.path = eval_file(self.root, rows=rows, name="small.jsonl")
        self.connect(ScriptedModel(correct=first_correct))
        before = self.run_eval(sample=rows)
        self.connect(ScriptedModel(correct=second_correct))
        after = self.run_eval(sample=rows, prompt="Try harder.")
        return before, after

    def compare(self, after, before):
        return REGISTRY.call(
            "read_eval_results",
            {"run_id": after["run_id"], "against": before["run_id"]},
            actor=MODEL,
            thread_id=self.thread,
        )

    def test_an_unresolvable_delta_is_reported_as_no_evidence(self):
        before, after = self.two_runs(20, 22)
        self.assertGreater(after["score"], before["score"])
        verdict = self.compare(after, before)
        self.assertEqual(verdict["verdict"], "no_evidence")
        self.assertFalse(verdict["resolved"])
        self.assertIn("NO EVIDENCE", verdict["says"])
        self.assertGreater(verdict["p_value"], 0.05)
        self.assertGreater(verdict["rows_that_would_resolve_this_delta"], 30)

    def test_a_real_difference_is_reported_as_one(self):
        before, after = self.two_runs(10, 28)
        verdict = self.compare(after, before)
        self.assertEqual(verdict["verdict"], "different")
        self.assertTrue(verdict["resolved"])
        self.assertLessEqual(verdict["p_value"], 0.05)

    def test_two_runs_that_agree_on_every_row_are_the_same(self):
        before, after = self.two_runs(20, 20)
        verdict = self.compare(after, before)
        self.assertEqual(verdict["changed"], 0)
        self.assertEqual(verdict["p_value"], 1.0)
        self.assertIn("no evidence of any difference", verdict["says"])

    def test_the_test_is_paired_and_only_the_rows_that_changed_count(self):
        self.assertEqual(evals.mcnemar(0, 0), 1.0)
        self.assertEqual(evals.mcnemar(1, 1), 1.0)
        self.assertAlmostEqual(evals.mcnemar(3, 0), 0.25)
        self.assertLess(evals.mcnemar(10, 0), 0.01)

    def test_two_different_eval_sets_are_two_facts_and_not_a_delta(self):
        self.connect(ScriptedModel(correct=20))
        first = self.run_eval()
        self.path = eval_file(self.root, rows=30, name="other.jsonl")
        second = self.run_eval()
        refused = self.compare(second, first)
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "different_eval_sets")
        self.assertIn("two facts, not a delta", refused["detail"])

    def test_an_unfinished_run_has_no_score_to_compare(self):
        self.connect(ScriptedModel(correct=20))
        finished = self.run_eval()
        self.connect(ScriptedModel(correct=40, fail_at=5))
        broken = self.run_eval(prompt="Try harder.")
        refused = self.compare(broken, finished)
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "incomplete_run")


class ExemplarsAreHeldOutOfTheScoreTest(EvalBenchTest):
    """Scoring on your own few-shot exemplars is a leak."""

    def test_held_out_rows_are_never_asked_and_never_scored(self):
        model = self.connect(ScriptedModel(correct=20))
        report = self.run_eval(hold_out=[0, 1, 2, 3, 4])
        self.assertEqual(report["planned"], 35)
        self.assertEqual(len(model.asked), 35)
        indexes = {row["row_index"] for row in evals.results_for(report["run_id"])}
        self.assertFalse(indexes & {0, 1, 2, 3, 4})

    def test_holding_different_rows_out_is_a_different_run(self):
        self.connect(ScriptedModel(correct=20))
        first = self.run_eval(hold_out=[0])
        second = self.run_eval(hold_out=[1])
        self.assertNotEqual(first["signature"], second["signature"])
        self.assertNotEqual(first["run_id"], second["run_id"])

    def test_holding_everything_out_leaves_nothing_to_score_on(self):
        self.connect(ScriptedModel(correct=20))
        refused = self.run_eval(hold_out=list(range(40)))
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "everything_held_out")


class OnlyABaselineIsRecordedAsTheBaselineTest(EvalBenchTest):
    """G1 asks what the best thing that already exists scores."""

    def test_the_default_prompt_stamps_all_three_of_g1s_facts(self):
        self.connect(ScriptedModel(correct=20))
        report = self.run_eval()
        self.assertEqual(
            sorted(row["fact"] for row in report["measured_facts"]),
            [
                "baseline_measured",
                "baseline_score",
                "failure_histogram",
                #: G1's three are the first, second and last. The histogram and
                #: its denominator ride along because a run that bucketed
                #: failures knows both, and the denominator is useless anywhere
                #: but beside the histogram it divides.
                "failures_seen",
                "trivial_baseline_score",
            ],
        )

    def test_a_prompt_the_caller_wrote_measures_that_prompt_and_not_the_baseline(self):
        """Otherwise the prompt bench overwrites the number it is meant to be
        beating, which makes every comparison it produces meaningless."""
        self.connect(ScriptedModel(correct=20))
        self.run_eval()
        before = evidence.assemble_facts(self.thread, {}, MODEL)[0]["baseline_score"]
        self.connect(ScriptedModel(correct=35))
        changed = self.run_eval(prompt="Answer with one word.")
        self.assertTrue(changed["ok"])
        self.assertEqual(changed["score"], 35 / 40)
        self.assertIn("not_a_baseline", changed)
        self.assertEqual(
            {row["fact"] for row in changed["measured_facts"]},
            #: Still not the baseline - and the denominator is stamped with the
            #: histogram here too, because "how many rows failed" is true of
            #: this run whoever wrote the prompt.
            {"failure_histogram", "failures_seen"},
        )
        after = evidence.assemble_facts(self.thread, {}, MODEL)[0]["baseline_score"]
        self.assertEqual(after.value, before.value)


class AModelGradingItselfSaysSoTest(EvalBenchTest):
    """The sycophancy this product exists to survive, made visible."""

    def test_a_judged_run_names_the_judge_on_every_row_and_in_the_report(self):
        model = self.connect(ScriptedModel(correct=20, verdict="CORRECT"))
        report = self.run_eval(metric=evals.MODEL_GRADED, sample=10)
        self.assertTrue(report["ok"], report.get("detail"))
        self.assertEqual(report["score"], 1.0)
        self.assertEqual(len(model.judged), 10)
        block = report["self_graded"]
        self.assertTrue(block["is_the_model_that_answered"])
        self.assertEqual(block["rows_judged"], 10)
        self.assertIn("graded its own answers", block["warning"])
        for row in evals.results_for(report["run_id"]):
            self.assertEqual(row["graded_by"], "model:scripted")

    def test_the_rule_based_scores_are_reported_beside_the_judges(self):
        """Computed on the same rows for free, so a judge claiming everything is
        right where exact match says half of it is wrong shows the gap rather
        than replacing it."""
        self.connect(ScriptedModel(correct=5, verdict="CORRECT"))
        report = self.run_eval(metric=evals.MODEL_GRADED, sample=10)
        self.assertEqual(report["scores"][evals.MODEL_GRADED], 1.0)
        self.assertEqual(report["scores"][evals.EXACT_MATCH], 0.5)
        self.assertEqual(
            report["self_graded"]["deterministic_scores_on_the_same_rows"][
                evals.EXACT_MATCH
            ],
            0.5,
        )

    def test_the_stamped_score_says_a_model_judged_it(self):
        self.connect(ScriptedModel(correct=5, verdict="CORRECT"))
        report = self.run_eval(metric=evals.MODEL_GRADED, sample=10)
        how = next(
            row["how"] for row in report["measured_facts"] if row["fact"] == "baseline_score"
        )
        self.assertIn("a model, judging its own answers", how)

    def test_a_judge_never_decides_a_bucket(self):
        """A bucket routes the diagnosis tree, and the model's own account of
        why it was wrong is the one input this product must not route on."""
        self.connect(ScriptedModel(correct=5, verdict="INCORRECT"))
        report = self.run_eval(metric=evals.MODEL_GRADED, sample=10)
        self.assertEqual(report["score"], 0.0)
        for row in evals.results_for(report["run_id"]):
            self.assertEqual(row["bucketed_by"], "rules")
        how = next(
            row["how"]
            for row in report["measured_facts"]
            if row["fact"] == "failure_histogram"
        )
        self.assertIn("bucketed by rule (never by a model)", how)

    def test_a_verdict_nobody_can_read_stops_the_run(self):
        """Counting it INCORRECT would be a reading nobody made. Counting it
        CORRECT would be that plus flattery."""
        self.connect(ScriptedModel(correct=20, verdict="well, sort of, maybe"))
        report = self.run_eval(metric=evals.MODEL_GRADED, sample=10)
        self.assertFalse(report["ok"])
        self.assertEqual(report["error"], "judge_unreadable")
        self.assertNotIn("measured_facts", report)

    def test_incorrect_is_read_before_correct(self):
        """The one parsing mistake in this file that would silently invert a
        grade, because INCORRECT contains CORRECT."""
        self.assertIs(evals._read_verdict("INCORRECT"), False)
        self.assertIs(evals._read_verdict("correct"), True)
        self.assertIsNone(evals._read_verdict("mostly"))
        self.assertIsNone(evals._read_verdict(""))

    def test_an_unknown_metric_is_refused_before_anything_is_spent(self):
        model = self.connect(ScriptedModel(correct=20))
        refused = self.run_eval(metric="vibes")
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "unknown_metric")
        self.assertEqual(len(model.asked), 0)


class TheRowsDoNotLeaveThisMachineOnAModelsSayResoTest(EvalBenchTest):
    """Taken from `measure_baseline` verbatim, sentence included."""

    def remote(self):
        row = provider_store.create(
            "Somewhere else", "https://api.example.com/v1", "gpt-x", "openai-compatible"
        )
        provider_store.set_active(row["id"])
        return row

    def test_a_model_may_not_send_the_users_rows_off_this_machine(self):
        self.remote()
        model = self.connect(ScriptedModel(correct=20))
        refused = self.run_eval()
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "remote_needs_the_user")
        self.assertEqual(len(model.asked), 0)
        self.assertIsNone(evals.get_run(1))

    def test_the_person_may(self):
        self.remote()
        self.connect(ScriptedModel(correct=20))
        allowed = REGISTRY.call(
            "run_eval",
            {
                "eval_path": str(self.path),
                "input_field": "q",
                "expected_field": "a",
                "sample": 10,
            },
            actor=USER,
            thread_id=self.thread,
        )
        self.assertTrue(allowed["ok"])
        self.assertEqual(allowed["locality"], "remote")


class ARunBelongsToOneConversationTest(EvalBenchTest):
    """Wall 5's shape, one table further out."""

    def test_a_run_is_not_readable_from_another_conversation(self):
        self.connect(ScriptedModel(correct=20))
        mine = self.run_eval()
        refused = REGISTRY.call(
            "read_eval_results", {"run_id": mine["run_id"]}, actor=MODEL, thread_id=self.other
        )
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "no_such_run")

    def test_a_comparison_checks_both_ids(self):
        """The same leak by a longer route: a comparison would report the other
        run's score, its prompt and its failing rows into this conversation."""
        self.connect(ScriptedModel(correct=20))
        mine = self.run_eval()
        theirs = self.run_eval(thread=self.other)
        refused = REGISTRY.call(
            "read_eval_results",
            {"run_id": mine["run_id"], "against": theirs["run_id"]},
            actor=MODEL,
            thread_id=self.thread,
        )
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "no_such_run")
        self.assertEqual(refused["run_id"], theirs["run_id"])

    def test_listing_shows_only_this_conversations_runs(self):
        self.connect(ScriptedModel(correct=20))
        self.run_eval()
        self.run_eval(thread=self.other)
        listed = REGISTRY.call(
            "read_eval_results", {}, actor=MODEL, thread_id=self.thread
        )
        self.assertEqual(listed["count"], 1)

    def test_a_facts_measurement_lands_in_the_conversation_that_ran_it(self):
        self.connect(ScriptedModel(correct=20))
        self.run_eval()
        self.assertTrue(evidence.rows_for(self.thread))
        self.assertEqual(evidence.rows_for(self.other), [])

    def test_a_run_cannot_be_filed_against_a_conversation_that_does_not_exist(self):
        model = self.connect(ScriptedModel(correct=20))
        refused = evals.run(
            eval_path=str(self.path),
            input_field="q",
            expected_field="a",
            thread_id=999999,
        )
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "no_such_thread")
        self.assertEqual(len(model.asked), 0)


class TheFileIsReadHonestlyTest(EvalBenchTest):
    """The three ways a call can be about a file that will not answer."""

    def test_a_file_with_no_rows_grades_nothing(self):
        empty = Path(self.root) / "empty.jsonl"
        empty.write_text("", encoding="utf-8")
        self.connect(ScriptedModel())
        refused = self.run_eval(eval_path=str(empty))
        self.assertEqual(refused["error"], "no_rows")

    def test_columns_that_are_not_there_are_named_back(self):
        self.connect(ScriptedModel())
        refused = self.run_eval(input_field="question")
        self.assertEqual(refused["error"], "no_such_columns")
        self.assertIn("'q'", refused["summary"])

    def test_no_provider_is_a_sentence_and_not_a_crash(self):
        with db.session() as connection:
            connection.execute("UPDATE providers SET is_active = 0")
        refused = self.run_eval()
        self.assertEqual(refused["error"], "no_provider")

    def test_a_sample_larger_than_the_file_grades_what_is_there(self):
        self.connect(ScriptedModel(correct=40))
        report = self.run_eval(sample=10_000)
        self.assertEqual(report["planned"], 40)
        self.assertEqual(report["rows_available"], 40)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
