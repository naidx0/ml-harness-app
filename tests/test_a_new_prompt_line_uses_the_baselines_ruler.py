"""A new prompt line grades with the ruler measure_baseline picks for the same answers.

Adapter run 1 (2026-09-23): try_prompt opened its line on exact_match while
measure_baseline, on the same JSON-record answers, chose fields. The bench read
0% where the baseline's ruler gave 4.8%, and neither result said which ruler it
used. A line left without a metric now opens on `choose_metric` of its own file.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.tools import evals, prompts
from app.tools.measure import FIELDS, choose_metric


def write(root: Path, name: str, answers: list[object]) -> Path:
    path = root / name
    path.write_text(
        "\n".join(json.dumps({"input": f"q{i}", "expected": a}) for i, a in enumerate(answers)) + "\n",
        encoding="utf-8",
    )
    return path


class ANewLineTakesTheBaselinesRulerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def test_json_record_answers_open_on_fields(self) -> None:
        records = [json.dumps({"task_type": "concept", "summary": f"s{i}"}) for i in range(6)]
        path = write(self.root, "records.jsonl", records)
        self.assertEqual(prompts._baseline_ruler(str(path), "expected"), FIELDS)
        self.assertEqual(prompts._baseline_ruler(str(path), "expected"), choose_metric(records)[0])

    def test_short_labels_still_open_on_exact_match(self) -> None:
        path = write(self.root, "labels.jsonl", ["yes", "no", "maybe", "yes"])
        self.assertEqual(prompts._baseline_ruler(str(path), "expected"), evals.EXACT_MATCH)

    def test_a_missing_file_or_column_falls_back_to_the_bench_default(self) -> None:
        self.assertEqual(prompts._baseline_ruler(str(self.root / "nope.jsonl"), "expected"), evals.EXACT_MATCH)
        path = write(self.root, "records.jsonl", ["a"])
        self.assertEqual(prompts._baseline_ruler(str(path), "answer"), evals.EXACT_MATCH)


if __name__ == "__main__":
    unittest.main()
