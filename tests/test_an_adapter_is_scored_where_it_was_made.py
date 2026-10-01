"""The adapter gets a number, and the number is about the adapter.

`app/tools/propose.py` refused to draw a full fine-tune because nothing in this
harness could score what one produces: every registered scorer declares
`providers` in its reads, `app/providers.ADAPTERS` is exactly
`('openai-compatible', 'ollama')`, and a LoRA adapter is a directory of
safetensors. `score_the_adapter` closes that by scoring the adapter in the
sandbox that trained it, and this file is about the four ways closing it could
have made the product worse.

**ONE: TWO ROW SETS.** `app/tools/evals.py` has the measured card - "-50.0% / A
real difference on this eval set / MEASURED" printed directly above "6
improved, 0 regressed" - from a comparison whose headline and evidence were
measured on different rows. An adapter scored on a fresh sample and compared to
a stored baseline is the same defect with a GPU attached, so the rows here are
not chosen at all: they are READ OUT of the baseline run's own results and
re-read from the eval file at those indexes. `TheRowsAreTheBaselinesRowsTest`
proves it against a baseline whose graded rows are deliberately not the first
n, so "the first n rows" would fail rather than coincide.

**TWO: ONE GRADER, WHOEVER IT IS.** The recipe generates text and grades
nothing; the arms are graded in this process. A rule-graded baseline gets
`evals.grade`; a MODEL-graded baseline gets the anchor's own judge, resolved
among today's connections by the model name the run recorded and asked
through the same seam `run_eval` asks through — see `TheSameJudgeGradesTheArmsTest`.
What still refuses, each with its sentence: a judge no longer connected, a
judge that would carry the rows off this machine, and a judge whose verdict
cannot be read — judged in full BEFORE anything is recorded, so a refusal
leaves the bench untouched.

**THREE: A GATE FACT UNDER THE WRONG NAME.** `run_eval` stamps `baseline_score`,
`baseline_measured`, `trivial_baseline_score` and `failure_histogram`. Every one
of those is a fact about the model the person is running today. `TheGatesAreUntouchedTest`
runs the whole tool over a thread whose ledger is loaded and shows the ledger is
byte-for-byte what it was - with a positive control that stamps one of those
facts through the ordinary route, so a check that could not fail is not the
check being relied on.

**FOUR: A CLAIM OF NO EGRESS THAT WAS NEVER TESTED.** `NoEgressIsProvedAndNotAssertedTest`
runs the real recipe's eval kind, in the real pinned environment, under an audit
hook armed to raise on `socket.connect`, `socket.getaddrinfo`,
`socket.gethostbyname` and `urllib.Request`. If it completes, the run made no
outbound connection - which is a measurement rather than a sentence. It skips
on a machine that has not built the environment or cached the model, and says
which.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import events, jobspec
from app.tools import REGISTRY, evals, evidence, sandbox as sandboxes, training
from app.tools.registry import ApprovalRequired

import support


REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_RECIPE = REPO_ROOT / "recipes" / "hf-peft-lora"

#: A recipe that answers rows without a GPU, a model or a download.
#:
#: It is a real recipe in a real temporary tree, run by the real runner through
#: the real sandbox, and what it fakes is exactly one thing: the generation. Its
#: answer for a row is read out of the ROW'S OWN TEXT - `||adapter=yes||` and
#: `||base=no||` - so each test writes the outcome it wants to reason about into
#: the eval file rather than mocking anything, and the fact that the harness
#: handed the recipe the right row text is checked by the answers coming back
#: matched to the right indexes.
SCORER = """
    import argparse, json
    from pathlib import Path

    parser = argparse.ArgumentParser()
    parser.add_argument("--kind")
    parser.add_argument("--job-json")
    args = parser.parse_args()
    job = json.loads(Path(args.job_json).read_text(encoding="utf-8"))
    config = job.get("config") or {}
    run_dir = Path(args.job_json).parent
    rows = config.get("rows") or []

    print("kind=" + args.kind)
    print("rows=" + str(len(rows)))
    print("indexes=" + ",".join(str(r["row_index"]) for r in rows))
    print("adapter_dir=" + str(config.get("adapter_dir")))
    print("base_model=" + str(config.get("base_model")))
    print("template=" + str(config.get("prompt_template")))
    print("max_new_tokens=" + str(config.get("max_new_tokens")))

    def answer_for(text, arm):
        marker = "||" + arm + "="
        if marker in text:
            return text.split(marker, 1)[1].split("||", 1)[0]
        return text

    def write(name, arm):
        with open(run_dir / name, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps({
                    "row_index": row["row_index"],
                    "answer": answer_for(row["input"], arm),
                    "seconds": 0.001,
                    "arm": arm,
                }) + "\\n")

    write("predictions.jsonl", "adapter")
    if config.get("include_base"):
        write("predictions_base.jsonl", "base")
    print("wrote answers")
"""

#: A recipe that declares `eval` and answers nothing, for the path where the
#: run produced no predictions at all.
SILENT_SCORER = """
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind")
    parser.add_argument("--job-json")
    parser.parse_args()
    print("I did not answer anything")
"""

#: A recipe that answers the first half of the rows and stops - what a
#: wall-clock timeout, an out-of-memory kill or a closed laptop leaves behind.
HALF_SCORER = """
    import argparse, json
    from pathlib import Path

    parser = argparse.ArgumentParser()
    parser.add_argument("--kind")
    parser.add_argument("--job-json")
    args = parser.parse_args()
    job = json.loads(Path(args.job_json).read_text(encoding="utf-8"))
    config = job.get("config") or {}
    run_dir = Path(args.job_json).parent
    rows = (config.get("rows") or [])
    half = rows[: len(rows) // 2]
    with open(run_dir / "predictions.jsonl", "w", encoding="utf-8") as handle:
        for row in half:
            print(json.dumps({
                "row_index": row["row_index"],
                "answer": "yes",
                "seconds": 0.001,
                "arm": "adapter",
            }), file=handle)
    print("stopped after " + str(len(half)) + " of " + str(len(rows)))
"""


#: A recipe that answers every row with the adapter and NONE with the base
#: model, whatever `include_base` said - what a control arm killed by the
#: timeout, or one that fell over on its own, leaves behind.
NO_CONTROL = """
    import argparse, json
    from pathlib import Path

    parser = argparse.ArgumentParser()
    parser.add_argument("--kind")
    parser.add_argument("--job-json")
    args = parser.parse_args()
    job = json.loads(Path(args.job_json).read_text(encoding="utf-8"))
    config = job.get("config") or {}
    run_dir = Path(args.job_json).parent
    with open(run_dir / "predictions.jsonl", "w", encoding="utf-8") as handle:
        for row in (config.get("rows") or []):
            print(json.dumps({
                "row_index": row["row_index"],
                "answer": "yes",
                "seconds": 0.001,
                "arm": "adapter",
            }), file=handle)
    print("the control arm never started")
"""


def a_recipe(name: str, source: str, kinds=("train", "eval")) -> Path:
    """Write a fixture recipe into the temporary tree `support.sandbox` bound."""
    directory = Path(jobspec.RECIPES_ROOT) / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "recipe.toml").write_text(
        f'name = "{name}"\n'
        f"kinds = [{', '.join(chr(34) + k + chr(34) for k in kinds)}]\n"
        'entrypoint = "entrypoint.py"\n',
        encoding="utf-8",
    )
    (directory / "entrypoint.py").write_text(
        textwrap.dedent(source).strip() + "\n", encoding="utf-8"
    )
    return directory


class ScoringTestCase(unittest.TestCase):
    """A sandbox with an adapter in it, and a baseline that graded real rows."""

    def setUp(self):
        self.root = support.sandbox(self)
        a_recipe("scorer", SCORER)
        a_recipe("mute", SILENT_SCORER)
        self.thread = events.create_thread("a conversation that trained something")

    # -- the eval file ---------------------------------------------------

    def eval_file(
        self,
        rows: int = 30,
        adapter=lambda i: "yes",
        base=lambda i: "no",
        expected=lambda i: "yes",
        name: str = "eval.jsonl",
    ) -> Path:
        """An eval file whose rows carry what each arm will answer.

        The markers are inside the INPUT column, which is the column the
        harness sends to the recipe. A row whose marker never arrives is a row
        the harness did not send, so the plumbing is checked by the answers
        rather than by a mock.
        """
        path = self.root / name
        path.write_text(
            "\n".join(
                json.dumps(
                    {
                        "q": (
                            f"question {i} ||adapter={adapter(i)}||"
                            f"||base={base(i)}||"
                        ),
                        "a": expected(i),
                    }
                )
                for i in range(rows)
            ),
            encoding="utf-8",
        )
        return path

    # -- the baseline ----------------------------------------------------

    def baseline(
        self,
        eval_path: Path,
        *,
        right=lambda i: False,
        thread_id: int | None = None,
        metric: str = evals.EXACT_MATCH,
        sample: int = 1000,
        hold_out: tuple[int, ...] = (),
        complete: bool = True,
        judge: str | None = None,
    ) -> dict:
        """A stored eval run, written the way `run_eval` writes one.

        Written through `evals.create_run` / `evals.record_row` rather than by
        calling `run_eval`, because a baseline needs a connected model and this
        file is about what happens AFTERWARDS. Every column that decides
        anything downstream - the fingerprint, the row indexes, the metric -
        is the real one.
        """
        plan = evals._plan(str(eval_path), "q", "a", sample, hold_out)
        chosen = plan["chosen"]
        run = evals.create_run(
            thread_id=int(thread_id or self.thread["id"]),
            signature="baseline-fixture",
            eval_path=str(eval_path),
            eval_fingerprint=plan["fingerprint"],
            input_field="q",
            expected_field="a",
            metric=metric,
            prompt="you are a helpful assistant",
            prompt_is_default=1,
            provider_id=None,
            provider_name="ollama",
            model="granite4-hermes:latest",
            locality="local",
            judge_model=judge,
            planned=len(chosen),
            rows_available=int(plan["available"]),
            trivial_baseline=0.5,
            trivial_answer="yes",
            latency_budget_ms=None,
        )
        keep = chosen if complete else chosen[:-1]
        for index, question, expected in keep:
            answer = expected if right(index) else "definitely not the answer"
            verdicts = evals.grade(expected, answer)
            evals.record_row(
                int(run["id"]),
                index,
                question=question,
                expected=expected,
                answer=answer,
                correct=bool(right(index)),
                verdicts=verdicts,
                failure_mode=None if right(index) else "wrong_facts",
                graded_by=f"model:{judge}" if judge else metric,
                seconds=0.2,
            )
        return dict(run)

    # -- the sandbox and the adapter -------------------------------------

    def a_sandbox_with_an_adapter(
        self, name: str = "lora-try", recipe: str = "scorer", run: int = 1
    ) -> dict:
        made = sandboxes.create(name, recipe=recipe, purpose="scoring tests")
        adapter = Path(made["path"]) / sandboxes.RUNS / f"run_{run}" / "adapter"
        adapter.mkdir(parents=True)
        (adapter / "adapter_config.json").write_text(
            json.dumps(
                {
                    "base_model_name_or_path": "HuggingFaceTB/SmolLM2-135M",
                    "peft_type": "LORA",
                    "r": 16,
                    "lora_alpha": 32,
                    "target_modules": ["q_proj", "v_proj"],
                }
            ),
            encoding="utf-8",
        )
        (adapter / "adapter_model.safetensors").write_bytes(b"not really weights")
        made["adapter_dir"] = str(adapter)
        return made

    def scored(self, **over):
        """The ordinary call: a sandbox, an adapter, a baseline, a score."""
        eval_path = over.pop("eval_path", None) or self.eval_file()
        made = over.pop("sandbox", None) or self.a_sandbox_with_an_adapter()
        run = over.pop("baseline", None) or self.baseline(eval_path)
        arguments = {
            "sandbox": made["name"],
            "baseline_run_id": int(run["id"]),
            "thread_id": int(self.thread["id"]),
        }
        arguments.update(over)
        return REGISTRY.call("score_the_adapter", arguments, approved=True)


# ---------------------------------------------------------------------------
# One: the rows.


class TheRowsAreTheBaselinesRowsTest(ScoringTestCase):
    """The comparison's rows are read, never chosen.

    A tool that took `sample=` here would look identical in every result and
    would be measuring two different things either side of the delta.
    """

    def test_the_recipe_is_handed_exactly_the_indexes_the_baseline_graded(self):
        """And they are deliberately not the first n, so a prefix would fail."""
        eval_path = self.eval_file(rows=20)
        run = self.baseline(eval_path, hold_out=(0, 1, 2, 3, 4, 11, 13))
        graded = sorted(r["row_index"] for r in evals.results_for(int(run["id"])))
        self.assertEqual(graded, [5, 6, 7, 8, 9, 10, 12, 14, 15, 16, 17, 18, 19])

        answered = self.scored(baseline=run, eval_path=eval_path)

        self.assertTrue(answered["ok"], answered)
        job = json.loads(
            (Path(answered["run"]["run_dir"]) / "job.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            [row["row_index"] for row in job["config"]["rows"]],
            graded,
            "the adapter was scored on rows the baseline never graded",
        )
        self.assertEqual(answered["scored"]["rows"], len(graded))

    def test_the_question_text_comes_from_the_file_and_not_from_the_table(self):
        """`eval_results` clips at 4000 characters; the file does not.

        Asking the adapter a truncated question the baseline was never asked is
        the same defect as asking it a different question.
        """
        long_one = "x" * (evals.STORED_TEXT_CHARS + 500)
        path = self.root / "long.jsonl"
        path.write_text(
            json.dumps({"q": long_one + " ||adapter=yes||||base=no||", "a": "yes"})
            + "\n"
            + json.dumps({"q": "short ||adapter=yes||||base=no||", "a": "yes"}),
            encoding="utf-8",
        )
        run = self.baseline(path)
        stored = evals.results_for(int(run["id"]))[0]["input"]
        self.assertIn("truncated by app/tools/evals.py", stored)

        answered = self.scored(baseline=run, eval_path=path)

        job = json.loads(
            (Path(answered["run"]["run_dir"]) / "job.json").read_text(encoding="utf-8")
        )
        sent = job["config"]["rows"][0]["input"]
        self.assertNotIn("truncated by app/tools/evals.py", sent)
        self.assertTrue(sent.startswith(long_one))

    def test_an_eval_file_that_changed_is_a_refusal_and_not_a_delta(self):
        eval_path = self.eval_file(rows=12)
        run = self.baseline(eval_path)
        eval_path.write_text(
            "\n".join(
                json.dumps({"q": f"a different question {i}", "a": "no"})
                for i in range(12)
            ),
            encoding="utf-8",
        )

        answered = self.scored(baseline=run, eval_path=eval_path)

        self.assertFalse(answered["ok"])
        self.assertEqual(answered["error"], "not_scorable")
        self.assertIn("not the file eval run", answered["detail"])
        self.assertIn("two facts subtracted", answered["detail"])
        self.assertEqual(
            evals.runs_in(int(self.thread["id"])),
            [dict(evals.get_run(int(run["id"])), graded=12)],
            "a refused scoring wrote an eval run anyway",
        )

    def test_more_rows_than_one_call_carries_is_refused_with_the_bound(self):
        big = training.MAX_SCORED_ROWS + 1
        eval_path = self.eval_file(rows=big)
        run = self.baseline(eval_path, sample=big)

        answered = self.scored(baseline=run, eval_path=eval_path)

        self.assertFalse(answered["ok"])
        self.assertIn(str(training.MAX_SCORED_ROWS), answered["detail"])
        self.assertIn(str(big), answered["detail"])


# ---------------------------------------------------------------------------
# Two: the grader, and what will not be compared.


class OneGraderOrNoComparisonTest(ScoringTestCase):
    def test_a_judge_graded_baseline_whose_judge_is_gone_is_refused(self):
        """The judge's model name is the instrument. Nothing serving it, no
        comparison — a different judge would be a different instrument
        wearing the same column."""
        eval_path = self.eval_file()
        run = self.baseline(
            eval_path, metric=evals.MODEL_GRADED, judge="granite4-hermes:latest"
        )

        answered = self.scored(baseline=run, eval_path=eval_path)

        self.assertFalse(answered["ok"])
        self.assertIn("no connection serves that model", answered["detail"])
        self.assertIn("granite4-hermes:latest", answered["detail"])

    def test_two_local_judges_with_none_active_is_an_ambiguity_not_a_guess(self):
        from app.providers import store as provider_store

        for port in (11434, 11435):
            provider_store.create(
                f"Local {port}", f"http://127.0.0.1:{port}", "granite4-hermes:latest", "ollama"
            )
        eval_path = self.eval_file()
        run = self.baseline(
            eval_path, metric=evals.MODEL_GRADED, judge="granite4-hermes:latest"
        )

        answered = self.scored(baseline=run, eval_path=eval_path)

        self.assertFalse(answered["ok"])
        self.assertIn("none is active", answered["detail"])

    def test_a_judge_reachable_only_remotely_is_refused_by_name(self):
        from app.providers import store as provider_store

        provider_store.create(
            "Faraway",
            "https://api.example.com/v1",
            "granite4-hermes:latest",
            "openai-compatible",
        )
        eval_path = self.eval_file()
        run = self.baseline(
            eval_path, metric=evals.MODEL_GRADED, judge="granite4-hermes:latest"
        )

        answered = self.scored(baseline=run, eval_path=eval_path)

        self.assertFalse(answered["ok"])
        self.assertIn("off this machine", answered["detail"])

    def test_an_unfinished_baseline_has_no_score_to_beat(self):
        eval_path = self.eval_file(rows=10)
        run = self.baseline(eval_path, complete=False)

        answered = self.scored(baseline=run, eval_path=eval_path)

        self.assertFalse(answered["ok"])
        self.assertIn("did not finish", answered["detail"])

    def test_a_baseline_from_another_conversation_is_refused(self):
        other = events.create_thread("somebody else's conversation")
        eval_path = self.eval_file(rows=10)
        run = self.baseline(eval_path, thread_id=int(other["id"]))

        answered = self.scored(baseline=run, eval_path=eval_path)

        self.assertFalse(answered["ok"])
        self.assertIn("belongs to conversation", answered["detail"])

    def test_a_run_id_that_names_nothing_is_a_message(self):
        answered = self.scored(baseline={"id": 9999})

        self.assertFalse(answered["ok"])
        self.assertIn("no eval run 9999", answered["detail"])

    def test_both_arms_are_graded_by_the_function_that_graded_the_baseline(self):
        """Stated in the reply, and true of the stored rows.

        `graded_by` on every row is the metric, never `model:...`, so
        `evals.read`'s `self_graded` block stays absent - which is what tells a
        reader no model was asked whether it was right.
        """
        answered = self.scored()

        self.assertIn("evals.py::grade", answered["scored"]["graded_by"])
        for run_id in (answered["adapter_run_id"], answered["base_run_id"]):
            for row in evals.results_for(int(run_id)):
                self.assertEqual(row["graded_by"], evals.EXACT_MATCH)
                self.assertEqual(row["bucketed_by"], "rules")
        self.assertIsNone(answered["adapter_score"]["self_graded"])


class TheSameJudgeGradesTheArmsTest(ScoringTestCase):
    """A model-graded anchor is scorable when the anchor's judge is still here.

    The gap this closes was found on a real walk (thread 32, 2026-09-01): the
    baseline scored 23% model_graded and the old flat refusal left nothing to
    compare it to, while the sandbox's whole role was generation — grading
    already happened engine-side.
    """

    def judged(self, verdict: str = "CORRECT", **over):
        model = support.connect_a_model(
            self, support.ScriptedModel(verdict=verdict), name="Judge"
        )
        eval_path = over.pop("eval_path", None) or self.eval_file()
        run = self.baseline(
            eval_path, metric=evals.MODEL_GRADED, judge="scripted"
        )
        return model, self.scored(baseline=run, eval_path=eval_path, **over)

    def test_the_anchors_own_judge_grades_both_arms(self):
        model, answered = self.judged()

        self.assertTrue(answered["ok"])
        self.assertIn("model:scripted", answered["scored"]["graded_by"])
        # The judge was actually asked — once per answered row per arm.
        self.assertGreater(len(model.judged), 0)
        for run_id in (answered["adapter_run_id"], answered["base_run_id"]):
            run = evals.read(int(run_id))
            self.assertEqual(run["judge_model"], "scripted")
            for row in evals.results_for(int(run_id)):
                self.assertEqual(row["graded_by"], "model:scripted")

    def test_the_rule_verdicts_stay_beside_the_judges(self):
        """The judge says CORRECT for everything; the rules still disagree on
        the base arm ('no' against expected 'yes'), and both readings are on
        every stored row — the judge/rule gap run_eval keeps, kept here."""
        _, answered = self.judged()

        base_rows = evals.results_for(int(answered["base_run_id"]))
        self.assertTrue(base_rows)
        for row in base_rows:
            self.assertTrue(row["correct"], "the judge's word decides the metric")
            self.assertFalse(
                row["verdicts"][evals.EXACT_MATCH],
                "the rule's contrary reading must stay stored beside it",
            )

    def test_an_unreadable_verdict_records_nothing(self):
        from app import db

        support.connect_a_model(
            self, support.ScriptedModel(verdict="MAYBE"), name="Judge"
        )
        eval_path = self.eval_file()
        run = self.baseline(eval_path, metric=evals.MODEL_GRADED, judge="scripted")
        with db.session() as connection:
            before = connection.execute(
                "SELECT COUNT(*) FROM eval_runs"
            ).fetchone()[0]

        answered = self.scored(baseline=run, eval_path=eval_path)

        self.assertFalse(answered["ok"])
        self.assertIn("not a verdict", answered["detail"])
        self.assertIn("Nothing was recorded", answered["detail"])
        with db.session() as connection:
            after = connection.execute(
                "SELECT COUNT(*) FROM eval_runs"
            ).fetchone()[0]
        self.assertEqual(
            after, before, "a refused judging must leave the bench untouched"
        )


# ---------------------------------------------------------------------------
# Three: the comparison, and the refusal that is the point.


class ThePairedComparisonTest(ScoringTestCase):
    def test_an_adapter_that_beats_the_baseline_on_every_row_is_resolved(self):
        eval_path = self.eval_file(rows=40, adapter=lambda i: "yes")
        run = self.baseline(eval_path, right=lambda i: False)

        answered = self.scored(baseline=run, eval_path=eval_path)

        against = answered["against_the_baseline"]
        self.assertTrue(against["ok"])
        self.assertEqual(against["paired_rows"], 40)
        self.assertEqual(against["improved"], 40)
        self.assertEqual(against["regressed"], 0)
        self.assertEqual(against["delta"], 1.0)
        self.assertEqual(against["verdict"], "different")
        self.assertLess(against["p_value"], 0.05)
        self.assertEqual(answered["adapter_score"]["score"], 1.0)

    def test_one_row_of_difference_on_thirty_is_no_evidence_in_those_words(self):
        """The whole reason this bench exists, arriving through the new door.

        One row moving out of thirty is McNemar p=1.0. A prompt playground
        prints +3.3% and lets you conclude; this says NO EVIDENCE and says how
        many rows it would take.
        """
        eval_path = self.eval_file(
            rows=30, adapter=lambda i: "yes" if i == 7 else "no"
        )
        run = self.baseline(eval_path, right=lambda i: False)

        answered = self.scored(baseline=run, eval_path=eval_path)

        against = answered["against_the_baseline"]
        self.assertEqual(against["improved"], 1)
        self.assertEqual(against["regressed"], 0)
        self.assertEqual(against["verdict"], "no_evidence")
        self.assertIn("NO EVIDENCE", against["says"])
        self.assertIn("NO EVIDENCE", answered["says"])
        self.assertGreater(against["rows_that_would_resolve_this_delta"], 30)

    def test_the_delta_is_the_paired_strip_divided_by_its_own_width(self):
        """An arithmetic impossibility rather than a thing a reviewer notices."""
        eval_path = self.eval_file(
            rows=20,
            adapter=lambda i: "yes" if i % 2 == 0 else "no",
            expected=lambda i: "yes",
        )
        run = self.baseline(eval_path, right=lambda i: i < 4)

        answered = self.scored(baseline=run, eval_path=eval_path)
        against = answered["against_the_baseline"]

        self.assertEqual(
            against["delta"],
            (against["improved"] - against["regressed"]) / against["paired_rows"],
        )
        self.assertTrue(against["same_rows"])

    def test_the_base_model_is_scored_on_the_same_rows_as_its_own_control(self):
        """The comparison that isolates the training, on one instrument."""
        eval_path = self.eval_file(
            rows=24, adapter=lambda i: "yes", base=lambda i: "no"
        )
        run = self.baseline(eval_path, right=lambda i: False)

        answered = self.scored(baseline=run, eval_path=eval_path)

        control = answered["against_the_base_model"]
        self.assertTrue(control["ok"])
        self.assertEqual(control["paired_rows"], 24)
        self.assertEqual(control["improved"], 24)
        self.assertEqual(answered["base_score"]["score"], 0.0)
        self.assertEqual(
            sorted(r["row_index"] for r in evals.results_for(answered["adapter_run_id"])),
            sorted(r["row_index"] for r in evals.results_for(answered["base_run_id"])),
        )

    def test_an_adapter_that_changed_nothing_says_so(self):
        eval_path = self.eval_file(rows=30, adapter=lambda i: "no", base=lambda i: "no")
        run = self.baseline(eval_path, right=lambda i: False)

        answered = self.scored(baseline=run, eval_path=eval_path)

        control = answered["against_the_base_model"]
        self.assertEqual(control["changed"], 0)
        self.assertIn("Not one of the 30 rows changed", control["says"])

    def test_the_two_arms_are_named_as_two_instruments(self):
        answered = self.scored()

        said = answered["two_instruments"]
        self.assertIn("two instruments", said)
        self.assertIn("against_the_base_model", said)
        self.assertIn("greedy continuation", said)

    def test_without_the_control_arm_the_reply_says_what_is_missing(self):
        answered = self.scored(include_base=False)

        self.assertIsNone(answered["base_run_id"])
        self.assertIsNone(answered["against_the_base_model"])
        self.assertIn("nothing here separates", answered["says"])

    def test_the_failures_are_bucketed_by_the_same_rules_and_not_by_a_model(self):
        """`evals.bucket`, on the adapter's answers, with the same label set.

        Ten of the twenty rows expect `yes` and the adapter answers `no`, which
        IS a member of the expected column's vocabulary - a confident, well
        formed, wrong answer, which is `wrong_facts` and not `wrong_format`.
        Getting that distinction from the shared bucketer rather than from a
        second one here is the point.
        """
        eval_path = self.eval_file(
            rows=20,
            adapter=lambda i: "no",
            expected=lambda i: "yes" if i % 2 == 0 else "no",
        )
        run = self.baseline(eval_path, right=lambda i: False)

        answered = self.scored(baseline=run, eval_path=eval_path)

        report = answered["adapter_score"]
        self.assertEqual(report["failure_histogram"], {"wrong_facts": 10})
        self.assertEqual(report["score"], 0.5)
        self.assertIn("no model was asked why a row failed", report["buckets_decided_by"])


# ---------------------------------------------------------------------------
# Four: the gates.


class TheGatesAreUntouchedTest(ScoringTestCase):
    """An adapter's score is not a fact about the model the person is running.

    The declaration is checked, and then the whole tool is run over a thread
    whose ledger already holds the gate facts, and the ledger is compared row
    for row. The positive control stamps one of those facts through the
    ordinary route so that "nothing changed" is a finding rather than a
    property of a comparison that cannot move.
    """

    def ledger(self) -> list[tuple]:
        return [
            (row["id"], row["fact"], repr(row["value"]), row["origin"], row["how"])
            for row in evidence.rows_for(int(self.thread["id"]))
        ]

    def stamp_a_gate_fact(self, value: float = 0.42) -> None:
        instrument = evidence.instrument_for(
            tool="run_eval",
            measures=("baseline_score",),
            provides=REGISTRY.get("run_eval").provides,
            actor=evidence.MODEL,
            thread_id=int(self.thread["id"]),
            arguments={},
            bounds=(),
        )
        instrument.measured(
            "baseline_score", value, how="a fixture standing in for a real run"
        )

    def test_the_tool_declares_that_it_measures_nothing(self):
        spec = REGISTRY.get("score_the_adapter")

        self.assertEqual(spec.measures, ())
        self.assertFalse(spec.wants_instrument)
        self.assertEqual(spec.bounds, ())

    def test_no_gate_fact_is_declared_by_it_and_the_derivation_finds_real_ones(self):
        gates = set(evidence.gate_facts())

        self.assertTrue(gates, "the gate-fact derivation found nothing to check")
        self.assertIn("baseline_score", gates)
        self.assertIn("baseline_measured", gates)
        self.assertEqual(gates & set(REGISTRY.get("score_the_adapter").measures), set())
        self.assertTrue(
            gates & set(REGISTRY.get("run_eval").measures),
            "the positive control failed: run_eval no longer measures a gate fact",
        )

    def test_scoring_an_adapter_leaves_the_ledger_exactly_as_it_was(self):
        self.stamp_a_gate_fact()
        before = self.ledger()
        self.assertTrue(before, "the ledger was empty, so this could not fail")

        answered = self.scored()

        self.assertTrue(answered["ok"], answered)
        self.assertEqual(self.ledger(), before)
        self.assertIn("No fact was stamped", answered["measured_nothing"])

    def test_the_positive_control_moves_the_ledger(self):
        """If this passes and the one above passes, the check is real."""
        before = self.ledger()
        self.stamp_a_gate_fact(0.9)

        self.assertNotEqual(self.ledger(), before)

    def test_it_writes_eval_rows_which_are_this_bench_s_own_table(self):
        answered = self.scored()

        self.assertEqual(
            len(evals.results_for(answered["adapter_run_id"])),
            answered["scored"]["rows"],
        )
        for run_id in (answered["adapter_run_id"], answered["base_run_id"]):
            stored = evals.get_run(int(run_id))
            self.assertEqual(stored["prompt_is_default"], 0)
            self.assertIsNone(stored["provider_id"])
            self.assertTrue(stored["provider_name"].startswith("sandbox:"))

    def test_the_stored_adapter_run_cannot_be_read_as_a_baseline(self):
        """`run_eval` only stamps a run under the DEFAULT prompt.

        The adapter's run is stored with `prompt_is_default = 0` and a prompt
        that is the template it was actually asked under, so nothing reading
        the eval tables for "the baseline" can find it.
        """
        answered = self.scored()
        stored = evals.get_run(int(answered["adapter_run_id"]))

        self.assertEqual(stored["prompt"], training.DEFAULT_PROMPT_TEMPLATE)
        self.assertEqual(stored["prompt_is_default"], 0)
        self.assertNotEqual(stored["model"], "granite4-hermes:latest")


# ---------------------------------------------------------------------------
# Five: the tool's own shape, and the roster it must not join.


class TheToolIsNotAProviderScorerTest(ScoringTestCase):
    def test_it_does_not_read_providers_and_is_not_in_the_scorer_roster(self):
        """The one word `app/tools/propose.py` derives its roster from.

        A tool that reads `providers` sends rows to a connection. This one
        sends them to a process, which is the only reason it can be pointed at
        an adapter at all, and declaring `providers` would be false in exactly
        the place the product checks.
        """
        from app.tools import propose

        spec = REGISTRY.get("score_the_adapter")

        self.assertNotIn("providers", spec.reads)
        self.assertNotIn("score_the_adapter", propose.tools_that_score_a_model())
        self.assertIn("run_eval", propose.tools_that_score_a_model())

    def test_it_needs_an_approval_because_it_starts_a_process(self):
        with self.assertRaises(ApprovalRequired):
            REGISTRY.call(
                "score_the_adapter",
                {"sandbox": "lora-try", "baseline_run_id": 1, "thread_id": 1},
            )

    def test_it_cannot_write_a_gate(self):
        from app.tools.registry import RESERVED_WRITES

        spec = REGISTRY.get("score_the_adapter")
        self.assertEqual(set(spec.writes) & RESERVED_WRITES, set())

    def test_a_sandbox_whose_recipe_cannot_evaluate_is_refused_by_name(self):
        a_recipe("trainer-only", SCORER, kinds=("train",))
        made = sandboxes.create("train-only", recipe="trainer-only")
        adapter = Path(made["path"]) / sandboxes.RUNS / "run_1" / "adapter"
        adapter.mkdir(parents=True)
        (adapter / "adapter_config.json").write_text(
            json.dumps({"base_model_name_or_path": "acme/tiny"}), encoding="utf-8"
        )
        (adapter / "adapter_model.safetensors").write_bytes(b"x")
        eval_path = self.eval_file(rows=8)
        run = self.baseline(eval_path)

        answered = self.scored(sandbox=made, baseline=run, eval_path=eval_path)

        self.assertFalse(answered["ok"])
        self.assertIn("'eval'", answered["detail"])
        self.assertIn("refuses a kind a recipe did not declare", answered["detail"])

    def test_a_sandbox_name_that_is_a_path_is_refused(self):
        answered = self.scored(sandbox={"name": "../secrets"})

        self.assertFalse(answered["ok"])
        self.assertEqual(answered["error"], "sandbox_rejected")


# ---------------------------------------------------------------------------
# Six: finding the adapter, and saying which one it found.


class FindingTheAdapterTest(ScoringTestCase):
    def test_the_newest_adapter_in_the_sandbox_is_the_one_scored(self):
        made = self.a_sandbox_with_an_adapter(run=1)
        second = Path(made["path"]) / sandboxes.RUNS / "run_2" / "adapter"
        second.mkdir(parents=True)
        (second / "adapter_config.json").write_text(
            json.dumps({"base_model_name_or_path": "acme/second"}), encoding="utf-8"
        )
        (second / "adapter_model.safetensors").write_bytes(b"newer")

        found = training.find_the_adapter(made["name"])

        self.assertEqual(found["path"], str(second))
        self.assertIn("run_2", found["found_by"])
        self.assertTrue(found["made_in_this_sandbox"])

    def test_a_sandbox_that_trained_nothing_says_so(self):
        sandboxes.create("empty", recipe="scorer")

        with self.assertRaises(training.NotScorable) as raised:
            training.find_the_adapter("empty")

        self.assertIn("has not trained anything", str(raised.exception))

    def test_an_adapter_config_with_no_weights_beside_it_is_not_an_adapter(self):
        made = sandboxes.create("half", recipe="scorer")
        adapter = Path(made["path"]) / sandboxes.RUNS / "run_1" / "adapter"
        adapter.mkdir(parents=True)
        (adapter / "adapter_config.json").write_text("{}", encoding="utf-8")

        with self.assertRaises(training.NotScorable) as raised:
            training.find_the_adapter(made["name"])

        self.assertIn("killed before it saved", str(raised.exception))

    def test_an_adapter_from_outside_the_sandbox_is_scored_and_labelled(self):
        made = self.a_sandbox_with_an_adapter()
        elsewhere = self.root / "from-a-job" / "adapter"
        elsewhere.mkdir(parents=True)
        (elsewhere / "adapter_config.json").write_text(
            json.dumps({"base_model_name_or_path": "acme/elsewhere"}), encoding="utf-8"
        )
        (elsewhere / "adapter_model.safetensors").write_bytes(b"elsewhere")

        found = training.find_the_adapter(made["name"], str(elsewhere))

        self.assertFalse(found["made_in_this_sandbox"])
        self.assertEqual(found["found_by"], "the path this call named")

    def test_the_base_model_is_read_from_the_adapter_and_reported(self):
        answered = self.scored()

        self.assertEqual(answered["base_model"], "HuggingFaceTB/SmolLM2-135M")
        self.assertEqual(
            answered["adapter"]["base_model"], "HuggingFaceTB/SmolLM2-135M"
        )
        self.assertEqual(answered["adapter"]["bytes"], len(b"not really weights"))

    def test_a_run_that_stopped_half_way_has_no_score_and_keeps_its_rows(self):
        """A prefix of the rows is not a sample of them.

        `run_eval` refuses to stamp a partial run for exactly this reason and
        the same rule holds here: the answered rows are on disk and readable,
        the report says how far it got, and `evals.compare` refuses to pair an
        incomplete run rather than reporting a delta over half an eval set.
        """
        a_recipe("halfway", HALF_SCORER)
        made = self.a_sandbox_with_an_adapter(name="halfway-box", recipe="halfway")
        eval_path = self.eval_file(rows=20)
        run = self.baseline(eval_path)

        answered = self.scored(sandbox=made, baseline=run, eval_path=eval_path)

        self.assertFalse(answered["ok"])
        report = answered["adapter_score"]
        self.assertFalse(report["complete"])
        self.assertIsNone(report["score"])
        self.assertEqual(report["graded"], 10)
        self.assertEqual(report["planned"], 20)
        self.assertEqual(len(evals.results_for(answered["adapter_run_id"])), 10)
        self.assertFalse(answered["against_the_baseline"]["ok"])
        self.assertEqual(answered["against_the_baseline"]["error"], "incomplete_run")
        self.assertIn("10 of 20 rows were answered", answered["says"])

    def test_a_run_that_answered_nothing_grades_nothing(self):
        made = self.a_sandbox_with_an_adapter(name="mute-box", recipe="mute")
        eval_path = self.eval_file(rows=8)
        run = self.baseline(eval_path)

        answered = self.scored(sandbox=made, baseline=run, eval_path=eval_path)

        self.assertFalse(answered["ok"])
        self.assertEqual(answered["error"], "nothing_was_answered")
        self.assertEqual(
            [r["id"] for r in evals.runs_in(int(self.thread["id"]))],
            [int(run["id"])],
            "an unanswered scoring run left an empty eval run behind",
        )


# ---------------------------------------------------------------------------
# Seven: no egress, proved.


class NoEgressIsProvedAndNotAssertedTest(ScoringTestCase):
    """What the sandbox hands the run, and what the run actually does."""

    def test_the_scoring_run_is_handed_no_token_and_told_to_stay_offline(self):
        made = self.a_sandbox_with_an_adapter()
        manifest = sandboxes.read_manifest(made["name"])

        environment = sandboxes._environment(manifest)

        self.assertNotIn("MLH_TOKEN", environment)
        self.assertNotIn("MLH_PORT", environment)
        self.assertEqual(environment["HF_HUB_OFFLINE"], "1")
        self.assertEqual(environment["TRANSFORMERS_OFFLINE"], "1")
        self.assertEqual(environment["HF_DATASETS_OFFLINE"], "1")

    def test_a_sandbox_job_cannot_import_this_harness(self):
        """EGRESS_ENFORCED's second promise, checked from inside the job.

        *The run is not told where this harness's own API is and is given no
        token for it, so it cannot reach the engine that holds your database.*
        No environment variable carried either - the test above proves that -
        and `jobspec.job_env` set `PYTHONPATH` to the repository root, so the
        job could `import app.security`, read `engine.json` and print the
        engine's URL and its 43-character token, then `import app.db` and print
        the path to the owner's real `ml_harness.db`. All three were measured
        from inside a real sandbox run before this line was removed.

        The sandbox's own `EGRESS_NOT_ENFORCED` is honest that a socket is not
        blocked and that an absolute path reads the whole disk. Those are
        statements about the operating system. This was a statement about one
        line of ours, and it was false.
        """
        a_recipe(
            "importer",
            """
            import argparse, json
            parser = argparse.ArgumentParser()
            parser.add_argument("--kind"); parser.add_argument("--job-json")
            parser.parse_args()
            found = {}
            for name in ("app", "app.security", "app.db"):
                try:
                    __import__(name)
                    found[name] = "IMPORTED"
                except Exception as error:
                    found[name] = type(error).__name__
            print("REACH " + json.dumps(found))
            """,
        )
        made = self.a_sandbox_with_an_adapter(name="importer-box", recipe="importer")
        ran = REGISTRY.call(
            "run_in_sandbox",
            {"name": made["name"], "kind": "train", "config": {}},
            approved=True,
        )
        self.assertTrue(ran["ok"], ran)
        line = next(
            l for l in str(ran["output"]).splitlines() if l.startswith("REACH ")
        )
        found = json.loads(line[len("REACH "):])

        # TWO CONFIGURATIONS, ONE PROPERTY. A checkout is not installed into
        # its own interpreter, so the job cannot import us and the promise
        # holds. An INSTALLED copy - which is what `scripts/stage_bundle.py`
        # builds and what the shell's first run makes with uv - has this
        # product on the job's import path, and withholding the address and the
        # token does nothing when the code that finds them is importable. The
        # test that only checked the first case passed on the machine it was
        # written on and would have shipped a false promise to everybody else.
        importable = sandboxes.harness_is_importable()
        imported = [name for name, how in found.items() if how == "IMPORTED"]

        if not importable:
            self.assertEqual(
                found,
                {
                    "app": "ModuleNotFoundError",
                    "app.security": "ModuleNotFoundError",
                    "app.db": "ModuleNotFoundError",
                },
                "the sandbox says a job cannot import this harness, and one just did",
            )
        else:
            self.assertTrue(
                imported,
                "the sandbox says a job CAN import this harness and none could, "
                "which means the measurement is wrong in the direction that "
                "makes a real promise look broken",
            )
            said = sandboxes.reach(False, "")
            self.assertIn(sandboxes.THE_JOB_CAN_IMPORT_US, said["not_enforced"])
            self.assertNotIn(
                sandboxes.EGRESS_ENFORCED[1],
                said["enforced"],
                "an installed copy is still promising the job cannot reach the "
                "engine, from a sandbox where it just did",
            )
        self.assertNotIn("PYTHONPATH", sandboxes._environment(
            sandboxes.read_manifest(made["name"])
        ))

    def test_the_reach_of_the_sandbox_travels_with_the_score(self):
        answered = self.scored()

        self.assertFalse(answered["reach"]["egress"])
        self.assertTrue(answered["reach"]["not_enforced"])
        self.assertIn("operating system is not stopping a socket",
                      " ".join(answered["reach"]["not_enforced"]))

    def test_the_real_recipe_scores_an_adapter_with_the_network_armed_to_raise(self):
        """THE MEASUREMENT. If this completes, the run opened no connection.

        Skipped on a machine that has not built the pinned environment or has
        not got the base model cached, because both are facts about a machine
        and neither is a fact about this code. On the machine this was written
        on it runs the real `hf-peft-lora` eval kind against a real adapter and
        the real SmolLM2-135M, with an audit hook that raises on every
        outbound primitive.
        """
        interpreter = SHIPPED_RECIPE / ".venv" / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        if not interpreter.is_file():
            self.skipTest(f"the pinned environment is not built: {interpreter}")
        adapter = self.real_adapter()
        if adapter is None:
            self.skipTest("no adapter from a real training run in runs/")
        cache = jobspec.model_cache_home()
        if not cache or not Path(cache).is_dir():
            self.skipTest(f"no model cache on this machine at {cache!r}")

        work = self.root / "offline"
        work.mkdir()
        job = work / "job.json"
        job.write_text(
            json.dumps(
                {
                    "recipe": "hf-peft-lora",
                    "kind": "eval",
                    "config": {
                        "rows": [
                            {"row_index": 3, "input": "The capital of France is"},
                            {"row_index": 9, "input": "2 + 2 ="},
                        ],
                        "adapter_dir": str(adapter),
                        "max_new_tokens": 4,
                        "include_base": True,
                    },
                }
            ),
            encoding="utf-8",
        )
        armed = work / "armed.py"
        armed.write_text(
            textwrap.dedent(
                """
                import runpy, sys
                BLOCKED = ("socket.connect", "socket.getaddrinfo",
                           "socket.gethostbyname", "socket.gethostbyname_ex",
                           "urllib.Request")
                def hook(event, args):
                    if event in BLOCKED:
                        raise RuntimeError("EGRESS ATTEMPTED: " + event)
                sys.addaudithook(hook)
                script = sys.argv[1]
                sys.argv = sys.argv[1:]
                runpy.run_path(script, run_name="__main__")
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        environment = jobspec.job_env(
            {
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "HF_DATASETS_OFFLINE": "1",
                "TEMP": str(work),
                "TMP": str(work),
                "TMPDIR": str(work),
            }
        )
        finished = subprocess.run(
            [
                str(interpreter),
                str(armed),
                str(SHIPPED_RECIPE / "entrypoint.py"),
                "--kind",
                "eval",
                "--job-json",
                str(job),
            ],
            env=environment,
            cwd=str(work),
            capture_output=True,
            text=True,
            timeout=900,
        )

        self.assertNotIn("EGRESS ATTEMPTED", finished.stdout + finished.stderr)
        self.assertEqual(
            finished.returncode,
            0,
            f"stdout:\n{finished.stdout[-4000:]}\nstderr:\n{finished.stderr[-4000:]}",
        )
        answers = training.read_predictions(work / training.PREDICTIONS)
        self.assertEqual(sorted(answers), [3, 9])
        control = training.read_predictions(work / training.PREDICTIONS_BASE)
        self.assertEqual(sorted(control), [3, 9])
        self.assertIn("graded_by", finished.stdout)

    def real_adapter(self) -> Path | None:
        """An adapter a real training run on this machine left behind."""
        runs = REPO_ROOT / "runs"
        if not runs.is_dir():
            return None
        found = sorted(runs.glob("*/job_*/adapter/adapter_config.json"))
        for manifest in reversed(found):
            if (manifest.parent / "adapter_model.safetensors").is_file():
                return manifest.parent
        return None


# ---------------------------------------------------------------------------
# Eight: the shipped recipe, and the model cache a no-egress run needs.


class TheShippedRecipeCanEvaluateTest(unittest.TestCase):
    """Read off the real `recipes/` tree. No database, no writes."""

    def test_the_lora_recipe_declares_the_eval_kind(self):
        previous = jobspec.RECIPES_ROOT
        jobspec.RECIPES_ROOT = REPO_ROOT / "recipes"
        try:
            recipe = jobspec.load_recipe("hf-peft-lora")
        finally:
            jobspec.RECIPES_ROOT = previous

        self.assertIn("train", recipe.kinds)
        self.assertIn(training.SCORING_KIND, recipe.kinds)

    def test_the_entrypoint_implements_the_kind_it_declares(self):
        """A recipe that declared `eval` and could only train is worse than one
        that declared nothing: `jobspec.validate` would accept the job and the
        run would train instead of scoring."""
        source = (SHIPPED_RECIPE / "entrypoint.py").read_text(encoding="utf-8")

        self.assertIn("def evaluate(", source)
        self.assertIn('args.kind == "eval"', source)
        self.assertIn("disable_adapter", source)
        self.assertIn(training.PREDICTIONS, source)

    def test_the_lock_really_holds_what_scoring_needs(self):
        lock = (SHIPPED_RECIPE / "requirements.lock").read_text(encoding="utf-8")
        pinned = {
            line.split("==")[0].strip().lower()
            for line in lock.splitlines()
            if "==" in line and not line.strip().startswith("#")
        }

        for needed in ("peft", "transformers", "torch", "safetensors"):
            self.assertIn(needed, pinned, f"{needed} is not in the recipe's lock")


class TheModelCacheTravelsToTheJobTest(unittest.TestCase):
    """A no-egress run has to find a model that is already on this machine.

    `app/jobspec.py::model_cache_home` carries the measurement. This is the
    check that the measurement stays true, and the mutation that proves it is
    load-bearing: with the variable removed, the job's own interpreter cannot
    expand `~` at all.
    """

    PROBE = (
        "import os;"
        "print('home=' + os.path.expanduser('~'));"
        "print('hf_home=' + os.environ.get('HF_HOME', ''));"
        "print('hf_cache=' + os.environ.get('HF_HUB_CACHE', ''))"
    )

    def test_a_job_is_told_where_the_model_cache_is(self):
        env = jobspec.job_env()
        named = env.get("HF_HUB_CACHE") or env.get("HF_HOME")

        self.assertTrue(named, "a job is not told where the model cache is")
        self.assertTrue(Path(named).is_absolute())
        self.assertEqual(named, jobspec.model_cache_home())

    def test_the_users_own_setting_wins(self):
        from unittest import mock

        with mock.patch.dict(os.environ, {"HF_HOME": "D:/models/hf"}, clear=False):
            self.assertEqual(jobspec.model_cache_home(), "D:/models/hf")
            self.assertEqual(jobspec.job_env()["HF_HOME"], "D:/models/hf")
        with mock.patch.dict(os.environ, {"HF_HUB_CACHE": "D:/models/hub"}, clear=False):
            self.assertEqual(jobspec.job_env()["HF_HUB_CACHE"], "D:/models/hub")

    def test_without_it_the_job_cannot_expand_its_own_home(self):
        """The mutation, run rather than described.

        The passthrough list carries no `USERPROFILE`, `HOME`, `HOMEDRIVE` or
        `HOMEPATH`, so on Windows `expanduser('~')` in a job returns the string
        `~` and every library that keeps a cache under the home directory
        writes it under the working directory instead. There is 260 MB of
        re-downloaded SmolLM2-135M in this repository's own `runs/` tree from
        exactly that.
        """
        env = jobspec.job_env()
        stripped = {
            key: value
            for key, value in env.items()
            if key not in ("HF_HOME", "HF_HUB_CACHE")
        }
        finished = subprocess.run(
            [sys.executable, "-c", self.PROBE],
            env=stripped,
            capture_output=True,
            text=True,
            timeout=120,
        )
        home = ""
        for line in finished.stdout.splitlines():
            if line.startswith("home="):
                home = line.split("=", 1)[1]

        if os.name == "nt":
            self.assertEqual(
                home,
                "~",
                "this machine can expand ~ without USERPROFILE, so the "
                "measurement in jobspec.model_cache_home is stale - re-read it "
                "before relying on HF_HOME being what makes an offline run work",
            )
        self.assertTrue(
            Path(env.get("HF_HUB_CACHE") or env["HF_HOME"]).is_absolute(),
            "the job's model cache path is not absolute, so it is relative to "
            "whatever the working directory happened to be",
        )


# ---------------------------------------------------------------------------
# The sentence a person reads, which is the field that carried the defect.


class TheProseSaysWhichComparisonIsWhichTest(ScoringTestCase):
    """Two comparisons came back and the prose named neither.

    The DICT KEYS were labelled - `against_the_baseline`, `against_the_base_model`
    - and `says` was `" ".join((lead, verdict_line, control_line))` with nothing
    between them. `test_opposite_resolved_verdicts_are_the_headline` below builds
    the case out of a real eval file: the adapter beats the baseline and loses to
    the base model, both resolved, and every sentence of both verdicts is
    `evals.compare`'s own wording - "That is a real difference on this eval set"
    - twice, about opposite findings.

    NON-VACUOUS: swapping `verdict_line` and `control_line` in `_scoring_report`
    and running this file gave "Ran 56 tests / FAILED (failures=1)", the one
    failure being `test_each_comparison_is_under_its_own_name`. The other 55,
    which include all 44 that predate this change, stayed green under the swap.
    """

    def test_each_comparison_is_under_its_own_name(self):
        answered = self.scored(include_base=True)
        says = answered["says"]
        self.assertIn("AGAINST YOUR MEASURED BASELINE", says)
        self.assertIn("AGAINST THE BASE MODEL", says)
        # And each label carries which instrument it is, because that is the
        # difference the two comparisons are ABOUT.
        self.assertIn("two instruments", says)
        self.assertIn("one instrument", says)
        # The two verdicts cannot be swapped without the labels moving with
        # them: each arm's own `says` appears after its own label.
        baseline_at = says.index("AGAINST YOUR MEASURED BASELINE")
        base_at = says.index("AGAINST THE BASE MODEL")
        self.assertLess(baseline_at, base_at)
        # Each arm's own sentence sits inside its own label's section, so the
        # two cannot be swapped without the labels moving with them.
        self.assertIn(
            answered["against_the_baseline"]["says"], says[baseline_at:base_at]
        )
        self.assertIn(answered["against_the_base_model"]["says"], says[base_at:])

    def test_opposite_resolved_verdicts_are_the_headline(self):
        """The adapter beats the baseline and loses to the base model.

        Built out of the eval file rather than out of a stub: the adapter is
        right on 28 of 40 rows, the base model is right on all 40, and the
        baseline was wrong on all 40. So the comparison that crosses two
        instruments resolves as a win and the one that isolates the training
        resolves as a loss, and the reader is told that before either number.
        """
        eval_path = self.eval_file(
            rows=40,
            adapter=lambda i: "yes" if i < 28 else "no",
            base=lambda i: "yes",
            expected=lambda i: "yes",
        )
        run = self.baseline(eval_path, right=lambda i: False)
        answered = self.scored(baseline=run, eval_path=eval_path, include_base=True)

        self.assertTrue(answered["against_the_baseline"]["resolved"])
        self.assertTrue(answered["against_the_base_model"]["resolved"])
        self.assertGreater(answered["against_the_baseline"]["delta"], 0)
        self.assertLess(answered["against_the_base_model"]["delta"], 0)

        says = answered["says"]
        self.assertIn("THE TWO COMPARISONS DISAGREE AND BOTH RESOLVED", says)
        self.assertLess(says.index("DISAGREE"), says.index("AGAINST YOUR MEASURED"))
        self.assertIn("the decoding path made up a difference the training did not", says)

    def test_two_agreeing_verdicts_do_not_manufacture_a_contradiction(self):
        """A null is not a conflict, and neither is agreement."""
        answered = self.scored(include_base=True)
        self.assertNotIn("THE TWO COMPARISONS DISAGREE", answered["says"])


class TheBaseModelIsTheOneTheAdapterKnowsOrItIsSaidTest(ScoringTestCase):
    """`base_model` overrode the adapter's own record and nothing said so.

    `_adapter_at` reads `base_model_name_or_path` out of `adapter_config.json`
    and its docstring says why - *scoring an adapter against a base it was not
    trained on produces a number that looks exactly like a score*. The one line
    that used the field was `base = str(base_model or adapter["base_model"])`,
    so a caller's `base_model` replaced the adapter's own record and nothing
    anywhere compared the two; the payload printed both names side by side.
    `grep base_model tests/test_an_adapter_is_scored_where_it_was_made.py`
    returned no call that passed the argument, so it was untested as well as
    unchecked.
    """

    def test_an_override_that_disagrees_is_the_first_thing_said(self):
        answered = self.scored(base_model="somewhere/a-different-135m")
        self.assertTrue(answered["base_model_disagrees_with_the_adapter"])
        self.assertEqual(
            answered["base_model_recorded_by_the_adapter"],
            "HuggingFaceTB/SmolLM2-135M",
        )
        says = answered["says"]
        self.assertTrue(
            says.startswith("THIS IS NOT THE BASE MODEL THE ADAPTER RECORDS"), says[:120]
        )
        self.assertIn("HuggingFaceTB/SmolLM2-135M", says)
        self.assertIn("somewhere/a-different-135m", says)

    def test_no_override_says_nothing_and_claims_nothing(self):
        answered = self.scored()
        self.assertFalse(answered["base_model_disagrees_with_the_adapter"])
        self.assertNotIn("THIS IS NOT THE BASE MODEL", answered["says"])

    def test_naming_the_same_model_the_adapter_names_is_not_a_disagreement(self):
        answered = self.scored(base_model="HuggingFaceTB/SmolLM2-135M")
        self.assertFalse(answered["base_model_disagrees_with_the_adapter"])
        self.assertNotIn("THIS IS NOT THE BASE MODEL", answered["says"])


class TheAdviceIsSomethingTheCallerCanDoTest(ScoringTestCase):
    """Two sentences told people to do impossible or already-done things."""

    def test_a_caller_who_asked_for_the_control_arm_is_not_told_to_ask_for_it(self):
        """`include_base=True` and no control answers is not "ask again with
        include_base", which is what it said."""
        a_recipe("nocontrol", NO_CONTROL)
        made = self.a_sandbox_with_an_adapter(name="no-control", recipe="nocontrol")
        answered = self.scored(sandbox=made, include_base=True)

        self.assertTrue(answered["ok"])
        self.assertIsNone(answered["against_the_base_model"])
        says = answered["says"]
        self.assertIn("NOT MEASURED, THOUGH YOU ASKED FOR IT", says)
        self.assertNotIn("Ask again with include_base", says)

    def test_a_caller_who_did_not_ask_is_told_how_to_ask(self):
        answered = self.scored(include_base=False)
        self.assertIsNone(answered["against_the_base_model"])
        self.assertIn("Ask again with include_base", answered["says"])
        self.assertNotIn("THOUGH YOU ASKED FOR IT", answered["says"])

    def test_an_unfinished_sandbox_arm_is_not_something_run_eval_can_continue(self):
        """`evals.compare` said "run_eval with the same arguments continues
        where it stopped" about every unfinished run. `run_eval` generates
        through a connection; it cannot generate from an adapter, and
        `score_the_adapter` does not resume. There was no tool that did what
        that sentence told the caller to do."""
        a_recipe("half", HALF_SCORER)
        made = self.a_sandbox_with_an_adapter(name="half-done", recipe="half")
        answered = self.scored(sandbox=made)

        self.assertFalse(answered["ok"])
        self.assertFalse(answered["adapter_score"]["complete"])
        says = answered["says"]
        self.assertIn("score_the_adapter does not resume", says)
        self.assertNotIn("run_eval with the same arguments continues", says)

    def test_the_bench_itself_names_the_run_and_the_remedy(self):
        """The same sentence, fixed where it is written rather than only where
        this tool reads it - `compare` is reachable from the eval bench too."""
        eval_path = self.eval_file(rows=10)
        whole = self.baseline(eval_path)
        short = self.baseline(eval_path, complete=False)
        answer = evals.compare(int(whole["id"]), int(short["id"]))
        self.assertFalse(answer["ok"])
        self.assertEqual(answer["error"], "incomplete_run")
        self.assertIn(f"Run {short['id']} graded", answer["detail"])
        self.assertIn("run_eval with the same arguments continues", answer["detail"])


class TheAdapterSaysWhereItCameFromTest(ScoringTestCase):
    def test_an_adapter_from_outside_the_sandbox_is_said_in_the_prose(self):
        """`made_in_this_sandbox: False` was in the payload and in no sentence."""
        made = self.a_sandbox_with_an_adapter()
        elsewhere = self.root / "somewhere-else" / "adapter"
        elsewhere.mkdir(parents=True)
        for name in ("adapter_config.json", "adapter_model.safetensors"):
            (elsewhere / name).write_bytes(
                (Path(made["adapter_dir"]) / name).read_bytes()
            )
        answered = self.scored(sandbox=made, adapter_dir=str(elsewhere))

        self.assertFalse(answered["adapter"]["made_in_this_sandbox"])
        self.assertFalse(answered["made_in_this_sandbox"])
        says = answered["says"]
        self.assertIn("was not made in the sandbox that scored it", says)
        # And it says only what a path can support.
        self.assertIn("about directories and not about versions", says)

    def test_the_ordinary_case_says_nothing_about_it(self):
        answered = self.scored()
        self.assertTrue(answered["made_in_this_sandbox"])
        self.assertNotIn("was not made in the sandbox", answered["says"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
