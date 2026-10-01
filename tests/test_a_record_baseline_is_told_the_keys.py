"""A baseline on JSON-record answers is a measurement of the model, not of guessing.

Max's run of 2026-09-21: `measure_baseline` on his ml-principles eval set -
rows of `row_id, task_type, lane, input, expected, rubric_keys`, `expected` a
JSON record - scored minicpm5-hermes 0 of 20, and the model reporting it said
the harness had treated his records as free text. The ruler WAS `fields`. The
zero came from three places the grader never said out loud:

1. the model was sent the bare input under "Answer the question", so nothing
   told it the reply had to be a record with these keys - a record missing an
   expected key is wrong on every row for every model;
2. a record inside a ```json fence, which is how small local models answer,
   was `not_a_record`, because the reader required the first character to be
   a brace;
3. the summary never said which fields the score compared, so a 0 read as a
   harness that did not understand the data.

And `task_family` was derived as `extraction` for records whose fields are
mostly sentences the model has to write.
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
from app import events, full_defaults  # noqa: E402
from app.providers import Caps, Delta  # noqa: E402
from app.tools import evidence, measure  # noqa: E402
from app.tools.registry import REGISTRY  # noqa: E402

TYPES = ["concept", "debug", "compare", "design", "evaluate"]


def expected_record(i: int) -> dict:
    return {
        "task_type": TYPES[i % len(TYPES)],
        "principles": ["bias variance", "regularisation"],
        "summary": "A small training set lets the model memorise noise rather than signal.",
        "steps": ["Measure the gap between train and eval.", "Add data or regularise."],
        "pitfalls": ["Tuning on the eval set.", "Reading one run as a trend."],
    }


def owner_rows(count: int = 20) -> list[dict]:
    return [
        {
            "row_id": f"mlp-{i:03d}",
            "task_type": TYPES[i % len(TYPES)],
            "lane": "principles",
            "input": f"Question {i}: why does a tiny dataset overfit?",
            "expected": json.dumps(expected_record(i)),
            "rubric_keys": ["names the principle", "gives the mechanism"],
        }
        for i in range(count)
    ]


class FencedRecordModel:
    """Answers with a record in a ```json fence - but only with the keys it was told.

    Told nothing, it writes the record it would invent (`answer`, `reasoning`).
    Told the keys, it uses them, with the right task_type on every row: the
    difference between the two is exactly what the prompt contributes.
    """

    def __init__(self) -> None:
        self.systems: list[str] = []

    def stream(self, conversation, offered=None, *, secret=None, **_):
        system = conversation[0]["content"]
        self.systems.append(system)
        index = int("".join(ch for ch in conversation[-1]["content"].split(":")[0] if ch.isdigit()) or 0)
        if "task_type" in system:
            record = dict(expected_record(index))
            record["summary"] = "Written in the model's own words."
        else:
            record = {"answer": "overfitting", "reasoning": "small data"}
        yield Delta(kind="text", text="Here is the record:\n```json\n" + json.dumps(record) + "\n```")

    def capabilities(self):
        return Caps(tool_calling=False, detail="scripted", ctx_len=8192)


class WrongLabelModel(FencedRecordModel):
    """Uses the keys, invents the task_type - the finding the grader must name."""

    def stream(self, conversation, offered=None, *, secret=None, **_):
        self.systems.append(conversation[0]["content"])
        record = dict(expected_record(0))
        record["task_type"] = "machine_learning_question"
        yield Delta(kind="text", text=json.dumps(record))


class ARecordBaselineIsToldTheKeys(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(support.sandbox(self))
        self.thread = int(events.create_thread("ml-principles")["id"])
        self.path = self.root / "eval.jsonl"
        self.path.write_bytes(
            ("\n".join(json.dumps(r) for r in owner_rows()) + "\n").encode("utf-8")
        )

    def score(self) -> dict:
        return REGISTRY.call(
            "measure_baseline",
            {"eval_path": str(self.path), "input_field": "input", "expected_field": "expected"},
            actor=evidence.MODEL,
            thread_id=self.thread,
        )

    def test_the_prompt_names_every_expected_key(self) -> None:
        model = support.connect_a_model(self, FencedRecordModel())
        out = self.score()
        self.assertTrue(out["ok"], out)
        for key in expected_record(0):
            self.assertIn(key, model.systems[0])
        for label in TYPES:
            self.assertNotIn(label, model.systems[0], "the values are what is measured")

    def test_a_fenced_record_with_the_right_labels_scores(self) -> None:
        support.connect_a_model(self, FencedRecordModel())
        out = self.score()
        self.assertEqual(out["metric"], measure.FIELDS)
        self.assertEqual(out["correct"], out["rows_scored"], out["summary"])
        self.assertEqual(out["baseline_score"], 1.0)

    def test_the_summary_names_the_record_shape(self) -> None:
        support.connect_a_model(self, FencedRecordModel())
        out = self.score()
        shape = out["record_shape"]
        self.assertEqual(shape["fields"], list(expected_record(0)))
        self.assertEqual(shape["compared"], ["task_type", "principles"])
        self.assertEqual(shape["free_text"], ["summary", "steps", "pitfalls"])
        self.assertIn("Expected answers are JSON records with fields task_type", out["summary"])

    def test_a_zero_says_which_field_decided_it(self) -> None:
        support.connect_a_model(self, WrongLabelModel())
        out = self.score()
        self.assertEqual(out["correct"], 0)
        self.assertIn("Why 0: task_type", out["summary"])

    def test_a_reply_inside_a_fence_is_a_record(self) -> None:
        report = measure.grade_fields(
            json.dumps({"task_type": "concept"}),
            'Sure.\n```json\n{"task_type": "concept"}\n```',
        )
        self.assertEqual(report["shape"], "record")
        self.assertTrue(report["correct"])

    def test_an_expected_answer_that_quotes_a_brace_is_not_a_record(self) -> None:
        values = ['Use {"a": 1} as the config', "plain words"] * 5
        self.assertEqual(measure.choose_metric(values)[0], measure.EXACT_MATCH)

    def test_records_of_mostly_prose_are_generation_not_extraction(self) -> None:
        values = [row["expected"] for row in owner_rows()]
        self.assertEqual(full_defaults._family_of(values), "generation")
        short = [json.dumps({"name": f"n{i}", "id": i}) for i in range(20)]
        self.assertEqual(full_defaults._family_of(short), "extraction")


if __name__ == "__main__":
    unittest.main()
