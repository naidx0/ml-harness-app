"""The ruler fits the data, and the baseline names the model it measured.

Max, 2026-09-17, reading thread 75: *"when it went to measure, it measured the
baseline of itself, and not the actual model we were pre and post fine-tuning."*
And the number it measured was a zero that meant nothing: the eval set's
expected answers are 420-character JSON records, exact match on a record is
zero for every model that will ever exist, and the engine read the pair as
"the labels are wrong". Re-graded by hand the chat model returned a record on
19 of 20 rows and missed on ONE field, task_type. That sentence is the finding,
and the ruler hid it.

Three laws here. A baseline chooses a ruler that fits when nobody named one.
Under `fields` the reply says which field disagreed. And a baseline can name
the model it scores - by argument, or pinned on the thread - so the number is
about the thing somebody means to improve.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import events  # noqa: E402
from app.tools import REGISTRY, evidence, measure  # noqa: E402

NL = chr(10)

EXPECTED = {
    "task_type": "concept",
    "summary": "A loss maps predictions and labels to a scalar the optimizer minimizes.",
    "principles": ["loss", "cross-entropy", "mse"],
}


class RecordModel:
    """Answers every question with a record whose task_type is invented."""

    def __init__(self, task_type: str = "loss_function") -> None:
        self.task_type = task_type
        self.asked: list[str] = []

    def stream(self, conversation, offered=None, *, secret=None, **extra):
        from app.providers import Delta

        self.asked.append(conversation[-1]["content"])
        reply = {
            "task_type": self.task_type,
            "summary": "Something the model wrote in its own words.",
            "principles": ["loss", "mse", "validation"],
        }
        yield Delta(kind="text", text=json.dumps(reply))

    def capabilities(self):
        from app.providers import Caps

        return Caps(tool_calling=False, detail="scripted", ctx_len=8192)


def write_records(path: Path, count: int = 12) -> Path:
    with path.open("w", encoding="utf-8") as handle:
        for n in range(count):
            row = {"input": f"Question {n}", "expected": json.dumps(EXPECTED)}
            handle.write(json.dumps(row) + NL)
    return path


class GradingByFieldsTest(unittest.TestCase):
    def test_a_record_with_one_wrong_short_field_names_that_field(self):
        report = measure.grade_fields(json.dumps(EXPECTED), json.dumps({
            "task_type": "loss_function",
            "summary": "different prose entirely",
            "principles": ["loss", "mse"],
        }))
        self.assertFalse(report["correct"])
        self.assertEqual(report["disagreed"], ["task_type"])
        self.assertIn("summary", report["free_text"], "prose is not compared")
        self.assertIn("principles", report["agreed"], "two of three tags is agreement")

    def test_a_reply_that_is_not_a_record_is_wrong_on_every_key(self):
        report = measure.grade_fields(json.dumps(EXPECTED), "banana split")
        self.assertFalse(report["correct"])
        self.assertEqual(report["shape"], "not_a_record")
        self.assertEqual(sorted(report["missing"]), ["principles", "summary", "task_type"])

    def test_the_ruler_is_chosen_to_fit(self):
        self.assertEqual(measure.choose_metric([json.dumps(EXPECTED)] * 3)[0], measure.FIELDS)
        self.assertEqual(measure.choose_metric(["billing", "refund", "billing"])[0], measure.EXACT_MATCH)


class ABaselineSaysWhichFieldIsOffTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)
        self.thread = int(events.create_thread("ruler", mode="build")["id"])
        self.model = support.connect_a_model(self, RecordModel())
        self.eval_path = write_records(self.root / "eval.jsonl")

    def measure(self, **extra):
        return REGISTRY.call(
            "measure_baseline",
            {"eval_path": str(self.eval_path), "input_field": "input",
             "expected_field": "expected", "sample": 12, **extra},
            actor=evidence.MODEL,
            thread_id=self.thread,
        )

    def test_records_are_graded_by_fields_and_the_finding_is_the_field(self):
        out = self.measure()
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["metric"], measure.FIELDS)
        self.assertEqual(out["fields_off"][0], "task_type")
        self.assertEqual(out["field_report"]["task_type"]["disagreed"], 12)
        self.assertIn("task_type agreed on 0 of 12", out["summary"])
        self.assertIn("free text and were not compared", out["summary"])
        # THE FACT CARRIES THE RULER, so a later reader knows what the 0 means.
        hows = [r["how"] for r in evidence.rows_for(self.thread) if r["fact"] == "baseline_score"]
        self.assertTrue(hows and "scored by fields" in hows[-1], hows)

    def test_the_trivial_baseline_is_measured_under_the_same_ruler(self):
        """Every expected record here is the same, so 'always answer the usual
        record' is right on every row under fields - a 100% floor the model
        has to beat, which exact match reported as 1 in 12."""
        out = self.measure()
        self.assertEqual(out["trivial_baseline_score"], 1.0)

    def test_a_named_metric_is_used_and_an_unknown_one_is_refused(self):
        self.assertEqual(self.measure(metric="exact_match")["metric"], "exact_match")
        refused = self.measure(metric="vibes")
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "unknown_metric")


class ABaselineNamesItsTargetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)
        self.thread = int(events.create_thread("target", mode="build")["id"])
        support.connect_a_model(self, RecordModel())
        self.eval_path = write_records(self.root / "eval.jsonl", 4)

    def measure(self, **extra):
        return REGISTRY.call(
            "measure_baseline",
            {"eval_path": str(self.eval_path), "input_field": "input",
             "expected_field": "expected", "sample": 4, **extra},
            actor=evidence.MODEL,
            thread_id=self.thread,
        )

    def test_a_model_named_in_the_call_is_the_model_on_the_fact(self):
        out = self.measure(model="qwen3:4b")
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["model"], "qwen3:4b")
        hows = [r["how"] for r in evidence.rows_for(self.thread) if r["fact"] == "baseline_score"]
        self.assertTrue(hows[-1].startswith("qwen3:4b answered"), hows[-1])

    def test_a_target_pinned_on_the_thread_is_scored_without_being_named_again(self):
        pinned = REGISTRY.call(
            "set_baseline_target", {"model": "gemma3:4b"},
            actor=evidence.MODEL, thread_id=self.thread,
        )
        self.assertTrue(pinned["ok"], pinned)
        self.assertEqual(events.get_thread(self.thread)["baseline_model"], "gemma3:4b")
        out = self.measure()
        self.assertEqual(out["model"], "gemma3:4b")
        unpinned = REGISTRY.call(
            "set_baseline_target", {"model": ""}, actor=evidence.MODEL, thread_id=self.thread,
        )
        self.assertTrue(unpinned["ok"])
        self.assertEqual(self.measure()["model"], "scripted", "unpinned scores the connection again")

    def test_the_target_tool_is_offered_beside_the_baseline(self):
        from app.tools import blocks

        self.assertIn("set_baseline_target", blocks.tools_in(["measurement"]))


if __name__ == "__main__":
    unittest.main()
