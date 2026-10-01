"""Four defects found by running thread 33 of the Practical ML workspace to a
verdict on 2026-09-01, each reproduced here from the transcript and closed.

1. `rebucket_failures` tallied the person's reading and stamped the histogram,
   but never wrote it onto the rows. `try_prompt(fewshot_from_failures=8,
   targets="wrong_facts")` then answered "no failing rows in the wrong_facts
   bucket" one call after 26 rows had been put there.
2. `build_retrieval_index` on a JSONL whose id column repeats - three facets of
   one glossary concept - aborted on `UNIQUE (index_id, passage_key)` and said
   "that is a defect in the harness, not in the request". It was.
3. `try_prompt` with no metric named defaulted to `exact_match` on a line that
   graded by `model_graded`, then refused itself as a different instrument.
   The refusal was right; the default it refused was the bench's, not the
   line's.
4. A training run started while the harness's own judge model held 4.9 GB of
   an 8 GB card. It ran 36x slower than the same run on a free card and nothing
   said so.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from app.tools import REGISTRY, evals, prompts, retrieval, sandbox
from app.tools.evidence import USER
import support

from test_a_sandbox_is_reproducible import a_recipe


class ARebucketReachesTheRowsTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        self.thread = int(support.conversations(1)[0]["id"])
        self.eval_path = self.root / "eval.jsonl"
        self.eval_path.write_text("", encoding="utf-8")
        self.run = support.a_completed_eval_run(self.thread, self.eval_path, rows=20)

    def test_the_person_s_bucket_is_what_every_reader_sees_afterwards(self):
        answered = REGISTRY.call(
            "rebucket_failures",
            {"run_id": int(self.run["id"]), "buckets": {"0": "wrong_format", "2": "wrong_style"}},
            actor="user",
            thread_id=self.thread,
        )
        self.assertTrue(answered.get("ok"), answered)

        by_index = {int(r["row_index"]): r for r in evals.results_for(int(self.run["id"]))}
        self.assertEqual(by_index[0]["failure_mode"], "wrong_format")
        self.assertEqual(by_index[2]["failure_mode"], "wrong_style")
        # A row the person did not name keeps the rule's bucket, on the row too.
        self.assertEqual(by_index[4]["failure_mode"], "wrong_facts")

    def test_few_shot_can_now_draw_from_the_corrected_bucket(self):
        """The defect as it was seen: exemplars aimed at a bucket the person
        had just filled came back empty."""
        REGISTRY.call(
            "rebucket_failures",
            {"run_id": int(self.run["id"]), "buckets": {"0": "wrong_format", "2": "wrong_format"}},
            actor="user",
            thread_id=self.thread,
        )
        drawn = prompts.choose_exemplars(int(self.run["id"]), 5, mode="wrong_format")
        self.assertEqual([e["row_index"] for e in drawn["exemplars"]], [0, 2])


class ARepeatedIdIsNotACrashTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        self.thread = int(support.conversations(1)[0]["id"])
        rows = [
            {"concept": "chip", "text": "A chip shows one compact fact in a pill."},
            {"concept": "chip", "text": "Use chips to keep small facts visible."},
            {"concept": "chip", "text": "A chip never wraps; it truncates with an ellipsis."},
            {"concept": "rail", "text": "A rail is a narrow vertical list of destinations."},
            {"concept": "rail", "text": "Reach for a rail when there are few destinations."},
        ]
        self.path = self.root / "glossary.jsonl"
        self.path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    def test_the_index_builds_and_every_passage_key_is_unique(self):
        built = REGISTRY.call(
            "build_retrieval_index",
            {"path": str(self.path), "text_field": "text", "id_field": "concept", "name": "glossary"},
            actor=USER,
            thread_id=self.thread,
        )
        self.assertTrue(built.get("ok"), built)
        found = REGISTRY.call(
            "search_the_index",
            {"query": "chip pill fact", "k": 5},
            actor=USER,
            thread_id=self.thread,
        )
        keys = [hit["passage_key"] for hit in found["passages"]]
        self.assertEqual(len(keys), len(set(keys)), keys)
        # The first document keeps the plain key; the repeats say which row they were.
        self.assertIn("chip#0", keys)
        self.assertTrue(any(k.startswith("chip@") for k in keys), keys)
        # Recall still resolves at the document level, by the shared id.
        self.assertTrue(all(hit["doc_key"] in {"chip", "rail"} for hit in found["passages"]))


class AMetricLeftUnsaidMeansTheLineSTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        self.thread = int(support.conversations(1)[0]["id"])
        self.path = self.root / "eval.jsonl"
        self.path.write_text(
            "\n".join(json.dumps({"q": f"q{i}", "a": f"a{i}"}) for i in range(5)),
            encoding="utf-8",
        )
        prompts.create_line(
            thread_id=self.thread,
            name="judged",
            eval_path=str(self.path),
            input_field="q",
            expected_field="a",
            metric=evals.MODEL_GRADED,
            sample=5,
            latency_budget_ms=None,
        )

    def _attempt(self, **kw):
        return prompts.attempt(
            thread_id=self.thread,
            line="judged",
            eval_path=str(self.path),
            input_field="q",
            expected_field="a",
            prompt="Answer plainly.",
            actor=USER,
            **kw,
        )

    def test_no_metric_on_an_open_line_is_not_a_different_instrument(self):
        answered = self._attempt()
        self.assertNotEqual(answered.get("error"), "different_instrument", answered)

    def test_a_metric_that_disagrees_with_the_line_is_still_refused(self):
        answered = self._attempt(metric=evals.EXACT_MATCH)
        self.assertEqual(answered.get("error"), "different_instrument", answered)


class ACrowdedCardRefusesToTrainTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        a_recipe("deterministic")
        sandbox.create("gpu", recipe="deterministic")

    def _capture(self):
        seen = {}

        def capture(argv, timeout, log_path, cwd=None, env=None):
            seen["argv"] = list(argv)
            Path(log_path).write_text("", encoding="utf-8")
            return 0

        return seen, capture

    def test_a_resident_model_refuses_the_run_and_names_itself(self):
        crowded = {"used_gb": 4.9, "total_gb": 8.0,
                   "resident": [{"name": "granite4-hermes:latest", "size_gb": 4.9}]}
        seen, capture = self._capture()
        with mock.patch.object(sandbox, "_gpu_occupancy", lambda: crowded), \
             mock.patch.object(sandbox.runner, "_run_streaming", capture):
            answered = REGISTRY.call(
                "run_in_sandbox", {"name": "gpu", "kind": "train"}, approved=True
            )
        self.assertFalse(answered["ok"], answered)
        self.assertEqual(answered["error"], "sandbox_rejected")
        self.assertIn("granite4-hermes:latest", answered["detail"])
        self.assertIn("ollama stop", answered["detail"])
        self.assertNotIn("argv", seen, "the run was started anyway")

    def test_share_gpu_runs_anyway_and_a_free_card_runs_without_asking(self):
        crowded = {"used_gb": 4.9, "total_gb": 8.0,
                   "resident": [{"name": "granite4-hermes:latest", "size_gb": 4.9}]}
        seen, capture = self._capture()
        with mock.patch.object(sandbox, "_gpu_occupancy", lambda: crowded), \
             mock.patch.object(sandbox.runner, "_run_streaming", capture):
            answered = sandbox.run("gpu", kind="train", config={"share_gpu": True})
        self.assertTrue(answered["ok"], answered)
        self.assertIn("argv", seen)

        free = {"used_gb": 0.55, "total_gb": 8.0, "resident": []}
        seen, capture = self._capture()
        with mock.patch.object(sandbox, "_gpu_occupancy", lambda: free), \
             mock.patch.object(sandbox.runner, "_run_streaming", capture):
            answered = sandbox.run("gpu", kind="train", config={})
        self.assertTrue(answered["ok"], answered)

    def test_a_machine_with_no_card_is_not_refused(self):
        seen, capture = self._capture()
        with mock.patch.object(sandbox, "_gpu_occupancy", lambda: None), \
             mock.patch.object(sandbox.runner, "_run_streaming", capture):
            answered = sandbox.run("gpu", kind="train", config={})
        self.assertTrue(answered["ok"], answered)

    def test_prepare_never_asks_about_the_card(self):
        a_recipe("wide", kinds=("train", "eval", "prepare"))
        sandbox.create("gpu-prep", recipe="wide")
        crowded = {"used_gb": 7.0, "total_gb": 8.0, "resident": [{"name": "x", "size_gb": 7.0}]}
        seen, capture = self._capture()
        with mock.patch.object(sandbox, "_gpu_occupancy", lambda: crowded), \
             mock.patch.object(sandbox.runner, "_run_streaming", capture):
            answered = sandbox.run("gpu-prep", kind="prepare", config={})
        self.assertTrue(answered["ok"], answered)


if __name__ == "__main__":
    unittest.main()
