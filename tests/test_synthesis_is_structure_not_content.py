"""Data is work, not a precondition - and synthetic rows are structure, not content."""

import json
import tempfile
import unittest
from pathlib import Path

from app import diagnosis
from app.tools import datawork
import support


class SynthesisIsStructureNotContent(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)

    def _source(self, rows, columns=("input", "expected")):
        tmp = Path(tempfile.mkdtemp())
        path = tmp / "source.jsonl"
        with open(path, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")
        return path

    def test_it_samples_with_replacement_and_tags_every_row(self):
        source = self._source(
            [
                {"input": "hello", "expected": "bonjour"},
                {"input": "goodbye", "expected": "au revoir"},
                {"input": "thanks", "expected": "merci"},
            ]
        )
        into = Path(tempfile.mkdtemp()) / "new_synth"
        result = datawork.synthesize_rows(
            path=str(source),
            answer_column="expected",
            into=str(into),
            count=10,
            seed="test-seed",
            ledger=diagnosis.default_spec(),
        )
        self.assertTrue(result["ok"], result)
        synthetic_path = Path(result["synthetic_path"])
        self.assertTrue(synthetic_path.exists())
        rows = [json.loads(line) for line in synthetic_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 10)
        for row in rows:
            self.assertTrue(row.get("synthetic"))
            self.assertIn("synthetic_source_index", row)
            # Answer copied, never invented - every synthetic expected is one of the three
            self.assertIn(row["expected"], {"bonjour", "au revoir", "merci"})

    def test_it_refuses_without_an_answer_column(self):
        source = self._source([{"input": "hi", "expected": "salut"}])
        into = Path(tempfile.mkdtemp()) / "x"
        result = datawork.synthesize_rows(
            path=str(source),
            answer_column="missing",
            into=str(into),
            count=5,
            ledger=diagnosis.default_spec(),
        )
        self.assertFalse(result["ok"])
        self.assertIn("no_such_column", result["error"])

    def test_it_never_overwrites_and_never_in_place(self):
        """LAW SUBSTITUTED 2026-09-17: a folder that exists is not refused,
        the rows land in the next free name beside it and the folder that
        was there keeps every byte."""
        source = self._source([{"input": "a", "expected": "b"}])
        into = Path(tempfile.mkdtemp()) / "exists"
        into.mkdir(parents=True)
        result = datawork.synthesize_rows(
            path=str(source),
            answer_column="expected",
            into=str(into),
            count=1,
            ledger=diagnosis.default_spec(),
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(Path(result["into"]).name, "exists-2")
        self.assertEqual(list(into.iterdir()), [], "the folder that was there is untouched")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
