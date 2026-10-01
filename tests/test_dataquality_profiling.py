"""Profiling real files: what is in them, and what could not be checked.

Every test here writes an actual file and reads it back through the real code
path. There is no fake reader and no stubbed row source, because the two defects
this module was rewritten around - a Windows encoding default and a `None` that
is not `""` - both live in the gap between "the logic is right" and "the file on
disk is read correctly", and a test that hands the profiler a list of dicts
cannot see either of them.

The rule under most of these assertions is the one in the module docstring: a
check that could not run says so. An empty finding list is only good news when
`checks_not_run` is empty too.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app import dataquality


class ProfilingTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)

    def tearDown(self):
        try:
            self.temp.cleanup()
        except (PermissionError, OSError):
            pass

    def write(self, name: str, text: str, encoding: str = "utf-8") -> Path:
        path = self.dir / name
        path.write_text(text, encoding=encoding)
        return path

    def write_bytes(self, name: str, payload: bytes) -> Path:
        path = self.dir / name
        path.write_bytes(payload)
        return path

    def csv(self, name: str, header: str, rows: list[str]) -> Path:
        return self.write(name, header + "\n" + "\n".join(rows) + "\n")


class FormatDetectionTest(ProfilingTestCase):
    """Magic bytes, not extensions. A file's name is a claim; its bytes are not."""

    def test_a_csv_is_detected_from_its_first_line(self):
        path = self.csv("d.csv", "a,b", ["1,x", "2,y"])

        fmt = dataquality.detect_format(path)

        self.assertEqual(fmt["name"], "csv")
        self.assertTrue(fmt["readable"])

    def test_a_tsv_is_told_apart_from_a_csv(self):
        path = self.write("d.tsv", "a\tb\n1\tx\n")

        self.assertEqual(dataquality.detect_format(path)["name"], "tsv")

    def test_jsonl_is_detected_by_parsing_lines_not_by_the_extension(self):
        path = self.write("mislabelled.csv", '{"a": 1}\n{"a": 2}\n')

        fmt = dataquality.detect_format(path)

        self.assertEqual(fmt["name"], "jsonl")
        self.assertEqual(fmt["extension"], ".csv")

    def test_a_json_array_is_not_mistaken_for_jsonl(self):
        path = self.write("d.json", '[\n  {"a": 1},\n  {"a": 2}\n]\n')

        self.assertEqual(dataquality.detect_format(path)["name"], "json")

    def test_a_parquet_file_is_recognised_by_its_magic_bytes_and_refused_honestly(self):
        """The point is the refusal, not the recognition.

        A format we cannot read must come back unreadable rather than be guessed
        at from the extension. `PAR1` is a real Parquet header; the rest of this
        file is not a real Parquet file, and that is deliberate - nothing here
        should be reading past the magic bytes.
        """
        path = self.write_bytes("d.parquet", b"PAR1" + b"\x00" * 64)

        fmt = dataquality.detect_format(path)

        self.assertEqual(fmt["name"], "parquet")
        self.assertEqual(fmt["how"], "magic bytes")
        self.assertEqual(fmt["provenance"], dataquality.MEASURED)
        self.assertFalse(fmt["readable"])

    def test_a_sqlite_file_is_recognised(self):
        path = self.write_bytes("d.db", b"SQLite format 3\x00" + b"\x00" * 32)

        self.assertEqual(dataquality.detect_format(path)["name"], "sqlite")

    def test_a_missing_path_is_reported_rather_than_guessed(self):
        fmt = dataquality.detect_format(self.dir / "nope.csv")

        self.assertIsNone(fmt["name"])
        self.assertFalse(fmt["readable"])


class UnreadableFormatsAreNotCleanTest(ProfilingTestCase):
    """The defect-3 pattern, generalised: silence must never read as approval."""

    def test_an_unreadable_format_lists_every_check_it_could_not_run(self):
        path = self.write_bytes("d.parquet", b"PAR1" + b"\x00" * 64)

        profile = dataquality.profile(path)

        self.assertFalse(profile["readable"])
        self.assertTrue(profile["checks_not_run"])
        names = {entry["check"] for entry in profile["checks_not_run"]}
        self.assertIn("duplicates", names)
        self.assertIn("label_imbalance", names)
        for entry in profile["checks_not_run"]:
            self.assertTrue(entry["why"].strip())

    def test_the_only_finding_for_an_unreadable_file_says_nothing_was_inspected(self):
        path = self.write_bytes("d.parquet", b"PAR1" + b"\x00" * 64)

        profile = dataquality.profile(path)
        findings = dataquality.quality_report(profile)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, dataquality.BLOCK)
        self.assertEqual(findings[0].code, "format_unreadable")
        self.assertIn("clean bill of health", findings[0].message)

    def test_the_plain_language_summary_refuses_to_imply_the_file_is_fine(self):
        path = self.write_bytes("d.parquet", b"PAR1" + b"\x00" * 64)

        profile = dataquality.profile(path)
        text = dataquality.describe(profile, dataquality.quality_report(profile))

        self.assertIn("could not check", text)
        self.assertNotIn("no problems", text.lower())

    def test_a_missing_file_is_a_block_and_not_an_empty_pass(self):
        profile = dataquality.profile(self.dir / "nope.csv")
        findings = dataquality.quality_report(profile)

        self.assertFalse(profile["exists"])
        self.assertEqual([f.code for f in findings], ["path_missing"])


class SchemaAndProvenanceTest(ProfilingTestCase):
    def test_every_number_in_a_profile_carries_a_provenance_word(self):
        """Invariant 3, applied to the object the tools actually return."""
        path = self.csv("d.csv", "text,label", ["hello,a", "goodbye,b"])

        profile = dataquality.profile(path)

        for key, value in profile["provenance"].items():
            with self.subTest(field=key):
                self.assertIn(value, dataquality.PROVENANCE)
        for column, stats in profile["schema"].items():
            with self.subTest(column=column):
                self.assertIn(stats["null_rate_provenance"], dataquality.PROVENANCE)
                self.assertIn(stats["type_provenance"], dataquality.PROVENANCE)
                self.assertIn(
                    stats["length_chars"]["provenance"], dataquality.PROVENANCE
                )

    def test_lengths_are_labelled_as_characters_and_not_as_tokens(self):
        """A character count under the word 'tokens' would be a fabricated number."""
        path = self.csv("d.csv", "text", ["hello there", "goodbye"])

        profile = dataquality.profile(path)

        self.assertEqual(profile["length"]["unit"], "characters")
        self.assertIn("tokenizer", profile["length"]["not_tokens"])
        self.assertEqual(profile["schema"]["text"]["length_chars"]["unit"], "characters")

    def test_types_are_inferred_per_column(self):
        path = self.csv(
            "d.csv", "n,x,flag,word", ["1,1.5,true,alpha", "2,2.5,false,beta"]
        )

        schema = dataquality.profile(path)["schema"]

        self.assertEqual(schema["n"]["type"], "integer")
        self.assertEqual(schema["x"]["type"], "number")
        self.assertEqual(schema["flag"]["type"], "boolean")
        self.assertEqual(schema["word"]["type"], "string")

    def test_a_numeric_looking_string_with_underscores_is_not_an_integer(self):
        """`int("1_0")` is 10 in Python. A regex is used precisely so it is not."""
        path = self.csv("d.csv", "code", ["1_0", "2_0"])

        self.assertEqual(dataquality.profile(path)["schema"]["code"]["type"], "string")

    def test_a_wholly_missing_column_still_reports_a_full_null_rate(self):
        """Defect 3, asserted against the new profiler as well as the old report."""
        path = self.write("short.csv", "a,b\n1\n2\n3\n")

        schema = dataquality.profile(path)["schema"]

        self.assertEqual(schema["b"]["null_rate"], 1.0)
        self.assertEqual(schema["a"]["null_rate"], 0.0)

    def test_a_header_only_file_reports_no_rate_rather_than_a_clean_one(self):
        path = self.write("header.csv", "a,b\n")

        profile = dataquality.profile(path)

        self.assertEqual(profile["rows"], 0)
        self.assertIsNone(profile["schema"]["a"]["null_rate"])
        self.assertEqual(profile["schema"]["a"]["null_rate_provenance"], "defaulted")
        self.assertTrue(profile["checks_not_run"])

    def test_a_utf8_csv_with_accents_profiles_without_raising(self):
        path = self.write("accents.csv", "name,city\nRene,café\nZoe,naïve\n")

        profile = dataquality.profile(path)

        self.assertEqual(profile["rows"], 2)
        self.assertEqual(profile["encoding"], "utf-8")

    def test_a_latin1_file_is_read_and_the_report_says_which_rung_it_landed_on(self):
        path = self.dir / "latin.csv"
        path.write_bytes("name,city\nRene,café\n".encode("latin-1"))

        profile = dataquality.profile(path)

        self.assertEqual(profile["encoding"], "latin-1")
        self.assertTrue(any("latin-1" in note for note in profile["notes"]))

    def test_an_empty_file_is_an_empty_profile_and_not_a_crash(self):
        path = self.write("empty.csv", "")

        profile = dataquality.profile(path)

        self.assertEqual(profile["rows"], 0)
        self.assertEqual(profile["columns"], [])
        self.assertEqual(
            [f.code for f in dataquality.quality_report(profile)], ["no_rows"]
        )


class DuplicatesTest(ProfilingTestCase):
    def test_exact_duplicate_rows_are_counted(self):
        path = self.csv("d.csv", "a,b", ["1,x", "2,y", "1,x", "1,x"])

        duplicates = dataquality.profile(path)["duplicates"]

        self.assertEqual(duplicates["exact"], 2)
        self.assertEqual(duplicates["exact_rate"], 0.5)

    def test_a_near_copy_is_found_even_though_it_is_not_identical(self):
        original = (
            "How do I reset my password on the customer portal? Click the forgot "
            "password link on the login screen and follow the emailed instructions."
        )
        paraphrase = original.replace("login screen", "sign-in screen")
        unrelated = (
            "What is the refund window for an order placed with express delivery "
            "in the winter sale?"
        )
        path = self.csv("d.csv", "text", [f'"{t}"' for t in (original, unrelated, paraphrase)])

        duplicates = dataquality.profile(path)["duplicates"]

        self.assertEqual(duplicates["exact"], 0)
        self.assertEqual(duplicates["near"], 1)

    def test_near_duplicates_exclude_the_exact_ones_so_the_two_figures_add_up(self):
        """A reader shown two percentages will add them. They should be right to."""
        original = (
            "How do I reset my password on the customer portal? Click the forgot "
            "password link on the login screen and follow the emailed instructions."
        )
        paraphrase = original.replace("login screen", "sign-in screen")
        rows = [f'"{original}"', f'"{original}"', f'"{paraphrase}"']
        path = self.csv("d.csv", "text", rows)

        duplicates = dataquality.profile(path)["duplicates"]

        self.assertEqual(duplicates["exact"], 1)
        self.assertEqual(duplicates["near"], 1)
        self.assertTrue(duplicates["near_excludes_exact"])

    def test_the_duplicate_threshold_is_labelled_as_our_policy(self):
        path = self.csv("d.csv", "a", ["1", "1"])

        duplicates = dataquality.profile(path)["duplicates"]

        self.assertEqual(duplicates["threshold"], dataquality.JACCARD_THRESHOLD)
        self.assertIn("policy", duplicates["threshold_is"])

    def test_a_duplicate_finding_carries_the_measurement_and_the_threshold(self):
        path = self.csv("d.csv", "a,b", ["1,x"] * 6 + ["2,y", "3,z", "4,w", "5,v"])

        findings = dataquality.quality_report(dataquality.profile(path))
        duplicate = next(f for f in findings if f.code == "duplicates")

        self.assertEqual(duplicate.evidence["provenance"], dataquality.MEASURED)
        self.assertIn("threshold", duplicate.evidence)
        self.assertTrue(duplicate.remediation.strip())


class LabelImbalanceTest(ProfilingTestCase):
    """A deliberately lopsided label, because that is what the check is for."""

    def imbalanced(self, majority: int, minority: int) -> Path:
        rows = [f"row number {i} of the majority class,yes" for i in range(majority)]
        rows += [f"row number {i} of the minority class,no" for i in range(minority)]
        return self.csv("d.csv", "text,label", rows)

    def test_the_label_column_is_found_by_name(self):
        path = self.imbalanced(80, 20)

        label = dataquality.profile(path)["label"]

        self.assertEqual(label["column"], "label")
        self.assertEqual(label["column_provenance"], dataquality.INFERRED)
        self.assertEqual(label["majority_class"], "yes")
        self.assertEqual(label["majority_share"], 0.8)
        self.assertEqual(label["provenance"], dataquality.MEASURED)

    def test_an_80_20_label_is_a_warning_with_the_share_in_it(self):
        path = self.imbalanced(80, 20)

        findings = dataquality.quality_report(dataquality.profile(path))
        imbalance = next(f for f in findings if f.code == "label_imbalance")

        self.assertEqual(imbalance.level, dataquality.WARN)
        self.assertIn("80%", imbalance.message)
        self.assertEqual(imbalance.evidence["share_provenance"], dataquality.MEASURED)

    def test_a_99_to_1_label_blocks_and_says_why_accuracy_is_meaningless(self):
        path = self.imbalanced(198, 2)

        findings = dataquality.quality_report(dataquality.profile(path))
        imbalance = next(f for f in findings if f.code == "label_imbalance")

        self.assertEqual(imbalance.level, dataquality.BLOCK)
        self.assertIn("has learned nothing", imbalance.message)

    def test_a_balanced_label_produces_no_imbalance_finding(self):
        path = self.imbalanced(100, 100)

        codes = [f.code for f in dataquality.quality_report(dataquality.profile(path))]

        self.assertNotIn("label_imbalance", codes)

    def test_when_no_column_looks_like_a_label_the_report_says_so(self):
        path = self.csv("d.csv", "first,second", ["alpha,1.5", "beta,2.5"])

        label = dataquality.profile(path)["label"]

        self.assertIsNone(label["column"])
        self.assertEqual(label["provenance"], dataquality.DEFAULTED)


class VolumeAndDegeneracyTest(ProfilingTestCase):
    def test_too_few_rows_blocks_and_recommends_prompting_instead(self):
        """docs/VISION.md: the most valuable thing this product can say."""
        path = self.csv("d.csv", "text,label", [f"row {i},a" for i in range(30)])

        findings = dataquality.quality_report(dataquality.profile(path))
        volume = next(f for f in findings if f.code == "volume_vs_method")

        self.assertEqual(volume.level, dataquality.BLOCK)
        self.assertIn("few-shot prompting", volume.remediation)
        self.assertEqual(volume.evidence["rows"], 30)
        self.assertIn("policy", volume.evidence["threshold_is"])

    def test_refusal_templates_are_counted_and_warned_about(self):
        rows = [f'"As an AI language model, I cannot answer question {i}.",a' for i in range(20)]
        rows += [f'"A perfectly ordinary answer number {i}.",b' for i in range(120)]
        path = self.csv("d.csv", "text,label", rows)

        profile = dataquality.profile(path)
        findings = dataquality.quality_report(profile)
        degenerate = next(f for f in findings if f.code == "degenerate_targets")

        self.assertEqual(profile["degenerate"]["rows_with_markers"], 20)
        self.assertEqual(degenerate.level, dataquality.WARN)
        self.assertIn("teaches the model to refuse", degenerate.remediation)

    def test_a_column_that_is_empty_in_every_row_blocks(self):
        rows = [f"value {i},," for i in range(120)]
        path = self.csv("d.csv", "a,b,c", rows)

        findings = dataquality.quality_report(dataquality.profile(path))
        empty = [f for f in findings if f.code == "column_entirely_missing"]

        self.assertTrue(empty)
        self.assertEqual(empty[0].level, dataquality.BLOCK)


class ShapeClassificationTest(ProfilingTestCase):
    """A confidence and a runner-up, always. A silent misclassification is the risk."""

    def profile_of(self, name: str, text: str) -> dict:
        return dataquality.profile(self.write(name, text))

    def test_instruction_pairs_are_recognised(self):
        rows = [
            json.dumps({"instruction": f"Do thing {i}", "output": f"Done {i}"})
            for i in range(20)
        ]
        guess = dataquality.classify_shape(
            self.profile_of("d.jsonl", "\n".join(rows) + "\n")
        )

        self.assertEqual(guess["shape"], "instruction_pairs")

    def test_preference_pairs_are_recognised(self):
        rows = [
            json.dumps(
                {"prompt": f"q{i}", "chosen": f"good {i}", "rejected": f"bad {i}"}
            )
            for i in range(20)
        ]
        guess = dataquality.classify_shape(
            self.profile_of("d.jsonl", "\n".join(rows) + "\n")
        )

        self.assertEqual(guess["shape"], "preference_pairs")

    def test_a_chat_export_is_recognised_from_its_structure_not_its_name(self):
        rows = [
            json.dumps(
                {"messages": [{"role": "user", "content": f"hi {i}"}]}
            )
            for i in range(20)
        ]
        guess = dataquality.classify_shape(
            self.profile_of("d.jsonl", "\n".join(rows) + "\n")
        )

        self.assertEqual(guess["shape"], "chat")
        self.assertTrue(any("list" in signal for signal in guess["signals"]))

    def test_a_folder_of_text_files_is_raw_text(self):
        folder = self.dir / "corpus"
        folder.mkdir()
        for index in range(3):
            (folder / f"doc{index}.txt").write_text(
                f"Document {index} body text.", encoding="utf-8"
            )

        profile = dataquality.profile(folder)

        self.assertEqual(profile["format"]["name"], "text_folder")
        self.assertEqual(profile["rows"], 3)
        self.assertEqual(dataquality.classify_shape(profile)["shape"], "raw_text")

    def test_every_guess_carries_a_confidence_and_a_runner_up(self):
        for name, text in (
            ("a.csv", "text,label\nhello,a\nbye,b\n"),
            ("b.jsonl", '{"instruction": "x", "output": "y"}\n'),
            ("c.csv", "one,two,three\n1,2,3\n4,5,6\n"),
        ):
            with self.subTest(file=name):
                guess = dataquality.classify_shape(self.profile_of(name, text))
                self.assertIsNotNone(guess["shape"])
                self.assertIsNotNone(guess["runner_up"])
                self.assertNotEqual(guess["shape"], guess["runner_up"])
                self.assertEqual(guess["confidence_provenance"], dataquality.INFERRED)
                self.assertTrue(guess["must_be_confirmed"])


class PlainLanguageTest(ProfilingTestCase):
    """docs/VISION.md: described back to you in plain language."""

    def test_the_summary_reads_like_a_colleague_saying_it(self):
        rows = [f"customer question number {i} about billing,billing" for i in range(160)]
        rows += [f"customer question number {i} about shipping,shipping" for i in range(40)]
        rows += rows[:6]  # a few exact duplicates
        path = self.csv("d.csv", "text,label", rows)

        profile = dataquality.profile(path)
        text = dataquality.describe(profile, dataquality.quality_report(profile))

        self.assertIn("206 rows", text)
        self.assertIn("duplicated", text)
        self.assertIn("one class", text)
        self.assertTrue(text.endswith(".") or text.endswith("baseline."))

    def test_the_summary_names_what_was_not_checked(self):
        path = self.write_bytes("d.parquet", b"PAR1" + b"\x00" * 64)

        text = dataquality.describe(dataquality.profile(path))

        self.assertIn("not", text.lower())

    def test_no_jargon_leaks_into_the_summary(self):
        path = self.csv("d.csv", "text,label", [f"row {i},a" for i in range(120)])

        text = dataquality.describe(dataquality.profile(path))

        for word in ("jaccard", "minhash", "shingle", "provenance", "kmv"):
            with self.subTest(word=word):
                self.assertNotIn(word, text.lower())


class StreamingTest(ProfilingTestCase):
    def test_a_row_cap_is_reported_rather_than_silently_applied(self):
        path = self.csv("d.csv", "a", [str(i) for i in range(50)])

        profile = dataquality.profile(path, max_rows=10)

        self.assertTrue(profile["truncated"])
        self.assertEqual(profile["rows"], 10)
        self.assertEqual(profile["provenance"]["rows"], dataquality.INFERRED)
        self.assertTrue(any("10 rows" in note for note in profile["notes"]))

    def test_iter_records_is_a_generator_and_not_a_list(self):
        """'Never loads a whole dataset into memory' has to be structural."""
        path = self.csv("d.csv", "a", [str(i) for i in range(1000)])

        stream = dataquality.iter_records(path)

        self.assertTrue(hasattr(stream, "__next__"))
        self.assertEqual(next(stream), {"a": "0"})
        stream.close()


class HashStabilityTest(unittest.TestCase):
    """`hash()` is salted per process. A leakage result that moves is useless.

    Measured against a real second interpreter rather than against a constant
    somebody typed in. A hardcoded expected value would have to come from
    running the function - so it proves only that the function equals itself -
    and it would be a number in the repository whose provenance is "an agent
    pasted it".
    """

    def test_the_row_hash_is_the_same_in_a_second_python_process(self):
        import subprocess
        import sys

        here = dataquality._stable_hash("the quick brown fox")
        there = subprocess.run(
            [
                sys.executable,
                "-c",
                "from app.dataquality import _stable_hash;"
                "print(_stable_hash('the quick brown fox'))",
            ],
            shell=False,
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parents[1]),
            timeout=60,
        )

        self.assertEqual(there.returncode, 0, there.stderr)
        self.assertEqual(int(there.stdout.strip()), here)

    def test_two_shingle_sets_of_the_same_text_are_identical(self):
        self.assertEqual(
            dataquality.shingles("How do I reset my password?"),
            dataquality.shingles("how   do i   reset my password?"),
        )


if __name__ == "__main__":
    unittest.main()
