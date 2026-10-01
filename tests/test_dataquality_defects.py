"""The three verified defects in app/dataquality.py.

docs/ARCHITECTURE.md 4.9: "it omits `encoding=` so it raises UnicodeDecodeError
on any UTF-8 CSV on Windows, it raises TypeError on an empty file, and - worst
because it is silent - it reports a column that is 100% missing as having a null
rate of 0.0."
"""

import tempfile
import unittest
from pathlib import Path

from app import dataquality


class DataQualityDefectsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)

    def tearDown(self):
        try:
            self.temp.cleanup()
        except (PermissionError, OSError):
            pass

    def write(self, name: str, text: str, encoding: str = "utf-8") -> str:
        path = self.dir / name
        path.write_text(text, encoding=encoding)
        return str(path)

    # ---- defect 1: the missing encoding= --------------------------------

    def test_a_utf8_csv_profiles_without_raising(self):
        """ROADMAP M0 acceptance evidence: "A UTF-8 CSV containing cafe profiles"."""
        path = self.write("accents.csv", "name,city\nRene,café\nZoe,naïve\n")

        report = dataquality.data_quality_report(path)

        self.assertEqual(report["rows"], 2)
        self.assertEqual(report["encoding"], "utf-8")

    def test_a_utf8_bom_is_not_glued_onto_the_first_column_name(self):
        path = self.write("bom.csv", "a,b\n1,x\n", encoding="utf-8-sig")

        report = dataquality.data_quality_report(path)

        self.assertEqual(report["columns"], ["a", "b"])

    def test_a_non_utf8_file_is_read_and_the_report_says_how(self):
        path = self.dir / "latin.csv"
        path.write_bytes("name\ncafé\n".encode("latin-1"))

        report = dataquality.data_quality_report(str(path))

        self.assertEqual(report["rows"], 1)
        self.assertEqual(report["encoding"], "latin-1")
        self.assertTrue(report["notes"])

    # ---- defect 2: the empty file ---------------------------------------

    def test_an_empty_file_is_an_empty_report_not_a_TypeError(self):
        path = self.write("empty.csv", "")

        report = dataquality.data_quality_report(path)

        self.assertEqual(report["rows"], 0)
        self.assertEqual(report["null_rate"], {})
        self.assertEqual(report["duplicates"], 0)

    def test_a_header_only_file_reports_no_rate_rather_than_a_clean_one(self):
        path = self.write("header.csv", "a,b\n")

        report = dataquality.data_quality_report(path)

        self.assertEqual(report["rows"], 0)
        # 0.0 here would read as "no nulls", which is a claim about data that
        # does not exist.
        self.assertIsNone(report["null_rate"]["a"])

    # ---- defect 3: the silently clean empty column ----------------------

    def test_a_wholly_missing_column_is_not_reported_as_clean(self):
        """The silent one. Short rows leave None, and None != "".

        `b` is absent from every data row, so DictReader fills it with None and
        the old `record[column] == ""` test scored it 0.0 - a column of nothing,
        reported as a column with no nulls.
        """
        path = self.write("short.csv", "a,b\n1\n2\n3\n")

        report = dataquality.data_quality_report(path)

        self.assertEqual(report["null_rate"]["b"], 1.0)
        self.assertEqual(report["null_rate"]["a"], 0.0)

    def test_an_explicitly_empty_column_is_also_fully_null(self):
        path = self.write("blank.csv", "a,b\n1,\n2,\n")

        report = dataquality.data_quality_report(path)

        self.assertEqual(report["null_rate"]["b"], 1.0)

    def test_a_whitespace_only_field_is_null(self):
        path = self.write("spaces.csv", "a,b\n1,   \n2,x\n")

        report = dataquality.data_quality_report(path)

        self.assertEqual(report["null_rate"]["b"], 0.5)

    def test_a_missing_field_and_an_empty_field_are_the_same_row(self):
        # The duplicate count used to treat a short row and an explicitly empty
        # one as different rows, because None and "" are different objects.
        path = self.write("dupes.csv", "a,b\n1,\n1\n")

        report = dataquality.data_quality_report(path)

        self.assertEqual(report["duplicates"], 1)

    # ---- shape that other code depends on -------------------------------

    def test_a_missing_file_is_an_empty_report(self):
        report = dataquality.data_quality_report(str(self.dir / "nope.csv"))

        self.assertEqual(report["rows"], 0)
        self.assertEqual(report["duplicates"], 0)


if __name__ == "__main__":
    unittest.main()
