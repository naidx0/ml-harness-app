"""The tool the product hands a blocked user could not settle what blocked them.

WHAT WAS BROKEN.

`G0_EVAL_SET` is the first of the five gates and `BLOCKED__BUILD_EVAL_SET` is
the product's most common terminal answer. `evidence.resolves('eval_size_n')`
names the tool that would settle it, sorting by how little each tool asks of the
user, so the tool it named was `measure_eval_set` - one property, `path`, and
nothing else to fill in.

`measure_eval_set` called `dataquality.profile(path, split='eval')` with no
`max_rows` and therefore took `DEFAULT_ROW_CAP = 200_000`. Above that the scan
came back `inferred`, the tool correctly refused to stamp an inferred count, and
its schema gave the caller no lever to raise the cap. Measured on a 200,001-row
JSONL fixture before the fix:

    measure_eval_set {"path": ".../eval_big.jsonl"}      57.7 seconds
      rows               200000
      rows_provenance    'inferred'
      summary            "The scan stopped at 200,000 rows before the end of
                          the data, so this is a lower bound and not a count.
                          Nothing was recorded as measured."
      ledger             []

Fifty-seven seconds of work, no number, no stamp, and no next step. The tool a
user is handed to settle G0 was the tool that could not settle it.

WHY THE CAP WAS THERE, AND WHY IT WAS THE WRONG CAP.

`profile` holds a near-duplicate index, a per-column distinct set and an
exact-duplicate table. All three grow with the data and `DEFAULT_ROW_CAP` bounds
them, which is right. Counting holds one integer. Measured on the same fixture,
on one machine:

    counting the rows                                     0.23 s
    profiling them, near-duplicate detection off          1.77 s
    profiling them as `measure_eval_set` actually did     57.7 s

A cap sized for the third number is two orders of magnitude too tight for the
first. So the fix is not a bigger cap, it is a different operation:
`dataquality.count_rows` is O(1) in memory at any file size, so nothing about
the number of rows bounds it, and what remains is a bound on TIME - which bounds
the wait rather than the answer, and which the caller can lift once it has been
shown what the wait would be.

THE LEVER IS A YES AND NOT A NUMBER, which is the part worth arguing. `max_rows`
would ask a user to guess the size of the set they are asking us to count, and a
wrong guess returns the same useless lower bound; the only honest answer to "how
many rows are you willing to read" is "all of them". It is also the one kind of
argument that cannot collide with a count - `Instrument.measured` compares types
strictly, so a boolean can never be mistaken for a row count the way an integer
cap once was, and `tests/test_an_honest_count_is_not_laundering.py` is the file
about what that mistake cost.

THREE MORE WAYS THE SAME TOOL RETURNED A WRONG NUMBER WITH A MEASURED BADGE.

These were found while constructing the failure above and are worse than it: a
refusal to stamp is visible, and a fabricated number that opens a gate is not.
Each is reproduced below on real data.

  * a folder of 5,200 example files was counted as 5,000 and stamped MEASURED,
    because `_directory_data_files` stopped at a cap it did not report;
  * a 60,000-row `.json` array was counted as ZERO and stamped MEASURED - the
    reader took `handle.read(MAX_FILE_CHARS)`, a prefix of a JSON array never
    parses, and the failure arrived downstream as a dataset with nothing in it;
  * a 137-row `.json` array under 64 KB was counted as 1 and stamped MEASURED,
    because a single line holding an array sniffed as JSONL - and the same file
    above 64 KB sniffed as JSON, so the answer changed at a size nobody was told
    about.

Invariant 5 says never invent a number. A count of 5,000 for 5,200 rows, and a
count of 0 for 60,000, are invented numbers wearing this product's own
measurement badge.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from app import dataquality, diagnosis
from app import build
from app.tools import REGISTRY, evidence
from app.tools.evidence import MEASURED, USER

import support


THREAD = 1

#: One row past `DEFAULT_ROW_CAP`. The size is the whole point of the fixture:
#: one row fewer and every assertion in this file passes against the broken code.
OVER_THE_OLD_CAP = dataquality.DEFAULT_ROW_CAP + 1


def jsonl(path: Path, rows: int) -> Path:
    """A real eval set of `rows` rows. Generated cheaply, but generated."""
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for index in range(rows):
            handle.write(json.dumps({"q": f"q{index}", "a": f"l{index % 5}"}) + "\n")
    return path


class TheReportedDefectTest(unittest.TestCase):
    """A real file above the cap, through the registry, and then through G0."""

    def setUp(self):
        self.root = support.sandbox(self)
        support.a_conversation(THREAD)
        evidence.ensure_table()

    def test_an_eval_set_above_the_old_row_cap_is_counted_and_stamped(self):
        path = jsonl(self.root / "eval_big.jsonl", OVER_THE_OLD_CAP)
        result = REGISTRY.call(
            "measure_eval_set", {"path": str(path)}, actor=USER, thread_id=THREAD
        )

        self.assertEqual(result["rows"], OVER_THE_OLD_CAP)
        self.assertTrue(result["exact"])
        self.assertFalse(result["truncated"])
        self.assertEqual(result["rows_provenance"], dataquality.MEASURED)
        self.assertEqual(
            result["measured_facts"],
            [
                {
                    "fact": "eval_size_n",
                    "value": OVER_THE_OLD_CAP,
                    "origin": MEASURED,
                    "how": build.counted_rows_how(OVER_THE_OLD_CAP, path),
                }
            ],
        )
        self.assertEqual(
            [(row["fact"], row["value"], row["origin"]) for row in evidence.rows_for(THREAD)],
            [("eval_size_n", OVER_THE_OLD_CAP, MEASURED)],
        )

    def test_the_gate_it_exists_to_open_opens_on_that_count(self):
        """The stamp is not the point. The verdict is.

        A tool that records a row nobody reads has settled nothing, so this
        walks the tree afterwards and asserts G0 passed on the counted value and
        that the run moved on to the next honest step rather than stopping to
        ask for the thing that was just measured.
        """
        path = jsonl(self.root / "eval_big.jsonl", OVER_THE_OLD_CAP)
        REGISTRY.call(
            "measure_eval_set", {"path": str(path)}, actor=USER, thread_id=THREAD
        )
        after = REGISTRY.call(
            "run_diagnosis",
            {
                "facts": {
                    "modality": "text",
                    "task_family": "generation",
                    "target_score": 0.85,
                    "privacy": "public_ok",
                    "needs_citations": False,
                }
            },
            actor=USER,
            thread_id=THREAD,
        )
        self.assertEqual(after["fact_origins"]["eval_size_n"], MEASURED)
        self.assertEqual(after["facts_used"]["eval_size_n"]["value"], OVER_THE_OLD_CAP)
        gate = after["gate_ledger"]["G0_EVAL_SET"]
        self.assertEqual(gate["status"], "PASSED", after["gate_ledger"])
        self.assertEqual(gate["clause"], "eval_size_n >= 30")
        self.assertEqual(after["outcome"], "ACTION__MEASURE_BASELINE")

    def test_the_users_own_door_counts_it_too(self):
        """Through `POST /api/tools/measure_eval_set`, which is the control."""
        from app.main import app

        path = jsonl(self.root / "eval_big.jsonl", OVER_THE_OLD_CAP)
        response = support.api_client(app).post(
            "/api/tools/measure_eval_set",
            json={"arguments": {"path": str(path)}, "thread_id": THREAD},
        )
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["result"]
        self.assertEqual(result["rows"], OVER_THE_OLD_CAP)
        self.assertEqual(result["measured_facts"][0]["value"], OVER_THE_OLD_CAP)

    def test_the_tool_the_product_names_first_is_one_that_can_finish(self):
        """The recommendation and the capability, asserted together.

        `resolves` sorts by how little a tool asks of the user, which is a
        reasonable key and was not enough on its own: it named the tool with the
        smallest schema without asking whether that tool could settle the fact.
        Rather than assert an ordering, this asserts the property the ordering
        was supposed to deliver - the tool named FIRST settles the fact, on a set
        above the cap that used to defeat it.
        """
        named = evidence.resolves("eval_size_n")
        self.assertEqual(named["tool"], "measure_eval_set")

        path = jsonl(self.root / "eval_big.jsonl", OVER_THE_OLD_CAP)
        result = REGISTRY.call(
            named["tool"], {"path": str(path)}, actor=USER, thread_id=THREAD
        )
        self.assertEqual(result["measured_facts"][0]["fact"], "eval_size_n")
        self.assertEqual(result["measured_facts"][0]["value"], OVER_THE_OLD_CAP)


class TheBudgetBoundsTheWaitAndNeverTheAnswerTest(unittest.TestCase):
    """The one limit that is left, and the lever that lifts it.

    Both halves, or neither means anything. A budget that never bites is not a
    bound, and a bound with no way past it is the defect this file is about.
    """

    def setUp(self):
        self.root = support.sandbox(self)
        support.a_conversation(THREAD)
        evidence.ensure_table()
        # The budget is read at call time precisely so that a test can reach the
        # branch without a multi-gigabyte fixture. Zero seconds means the first
        # clock check, at `_CLOCK_EVERY` rows, is already past the deadline.
        self.original = dataquality.COUNT_TIME_BUDGET_SECONDS
        dataquality.COUNT_TIME_BUDGET_SECONDS = 0.0
        self.addCleanup(
            setattr, dataquality, "COUNT_TIME_BUDGET_SECONDS", self.original
        )
        self.rows = dataquality._CLOCK_EVERY * 4
        self.path = jsonl(self.root / "eval.jsonl", self.rows)

    def test_a_budget_that_bites_stamps_nothing_and_says_what_to_do(self):
        result = REGISTRY.call(
            "measure_eval_set", {"path": str(self.path)}, actor=USER, thread_id=THREAD
        )
        # Non-vacuity: the scan really did stop short of the end.
        self.assertLess(result["rows"], self.rows)
        self.assertFalse(result["exact"])
        self.assertEqual(result["stopped_because"], "time_budget")
        self.assertEqual(result["rows_provenance"], dataquality.INFERRED)

        # Nothing was recorded. A lower bound is not a count.
        self.assertNotIn("measured_facts", result)
        self.assertEqual(evidence.rows_for(THREAD), [])

        # And the sentence the user is shown says both what happened and what
        # they can do about it, because an action nobody can perform is a
        # refusal wearing a friendlier word.
        self.assertIn("fewest rows", result["summary"])
        self.assertIn("finish the count", result["summary"])

    def test_the_lever_finishes_the_count_and_the_stamp_follows(self):
        REGISTRY.call(
            "measure_eval_set", {"path": str(self.path)}, actor=USER, thread_id=THREAD
        )
        self.assertEqual(evidence.rows_for(THREAD), [])

        result = REGISTRY.call(
            "measure_eval_set",
            {"path": str(self.path), "finish_the_count": True},
            actor=USER,
            thread_id=THREAD,
        )
        self.assertEqual(result["rows"], self.rows)
        self.assertTrue(result["exact"])
        self.assertEqual(result["measured_facts"][0]["value"], self.rows)

    def test_the_lever_is_a_boolean_and_therefore_cannot_be_a_row_count(self):
        """Why the lever is not `max_rows`, asserted rather than asserted about.

        `Instrument.measured` compares a stamped value against the caller's
        strings and booleans with strict types, so no boolean argument can ever
        be mistaken for the integer a count produces. An integer cap could be,
        and once was: see `test_an_honest_count_is_not_laundering.py`.
        """
        spec = {tool.name: tool for tool in REGISTRY}["measure_eval_set"]
        properties = spec.schema["properties"]
        self.assertEqual(properties["finish_the_count"]["type"], "boolean")
        self.assertEqual(spec.schema["required"], ["path"])
        for name, field in properties.items():
            with self.subTest(argument=name):
                self.assertNotIn(
                    field["type"],
                    ("integer", "number"),
                    f"{name} is a number the caller controls; a count that "
                    "equalled it would have to be defended rather than trusted",
                )


class ACapThatBitesSilentlyIsAnInventedNumberTest(unittest.TestCase):
    """The three wrong counts that carried a MEASURED badge. Real data, each one."""

    def setUp(self):
        self.root = support.sandbox(self)
        support.a_conversation(THREAD)
        evidence.ensure_table()

    def stamped(self, thread: int):
        return [
            (row["fact"], row["value"], row["origin"])
            for row in evidence.rows_for(thread)
        ]

    def test_a_folder_of_more_than_five_thousand_files_is_counted_whole(self):
        """It reported 5,000 for 5,200 and called that measured."""
        folder = self.root / "evalfolder"
        folder.mkdir()
        files = 5_200
        for index in range(files):
            (folder / f"row{index:05d}.txt").write_text(
                f"example {index}\n", encoding="utf-8"
            )

        result = REGISTRY.call(
            "measure_eval_set", {"path": str(folder)}, actor=USER, thread_id=THREAD
        )
        self.assertEqual(result["rows"], files)
        self.assertTrue(result["exact"])
        self.assertEqual(self.stamped(THREAD), [("eval_size_n", files, MEASURED)])
        # The format report counted the same files and must agree with the count.
        self.assertEqual(dataquality.detect_format(folder)["file_count"], files)

    def test_a_json_array_too_big_to_have_been_truncated_is_counted_whole(self):
        """It reported 0 for 60,000 rows and called that measured."""
        rows = 60_000
        path = self.root / "eval.json"
        path.write_text(
            json.dumps(
                [{"q": f"question number {i}", "a": f"label{i % 5}"} for i in range(rows)]
            ),
            encoding="utf-8",
        )
        self.assertGreater(
            len(path.read_text(encoding="utf-8")),
            dataquality.MAX_FILE_CHARS,
            "the fixture must be over the old whole-file read to reproduce anything",
        )

        result = REGISTRY.call(
            "measure_eval_set", {"path": str(path)}, actor=USER, thread_id=THREAD
        )
        self.assertEqual(result["rows"], rows)
        self.assertEqual(self.stamped(THREAD), [("eval_size_n", rows, MEASURED)])

    def test_a_small_json_array_is_a_document_and_not_one_jsonl_row(self):
        """It reported 1 for 137 rows and called that measured."""
        rows = 137
        path = self.root / "small.json"
        path.write_text(
            json.dumps([{"q": f"q{i}", "a": f"l{i % 5}"} for i in range(rows)]),
            encoding="utf-8",
        )
        self.assertLess(path.stat().st_size, 65536, "the fixture must fit the sniffer")

        self.assertEqual(dataquality.detect_format(path)["name"], "json")
        result = REGISTRY.call(
            "measure_eval_set", {"path": str(path)}, actor=USER, thread_id=THREAD
        )
        self.assertEqual(result["rows"], rows)
        self.assertEqual(self.stamped(THREAD), [("eval_size_n", rows, MEASURED)])

    def test_a_json_document_that_does_not_parse_is_never_a_measured_zero(self):
        """Not read and empty arrive as the same zero. They are not the same fact."""
        path = self.root / "broken.json"
        path.write_text('[{"q": "one"}, {"q": "tw', encoding="utf-8")

        result = REGISTRY.call(
            "measure_eval_set", {"path": str(path)}, actor=USER, thread_id=THREAD
        )
        self.assertFalse(result["exact"])
        self.assertEqual(result["stopped_because"], "json_did_not_parse")
        self.assertNotIn("measured_facts", result)
        self.assertEqual(evidence.rows_for(THREAD), [])
        self.assertIn("does not parse", result["summary"])

        # `profile_dataset` stamps the same fact from the same file and must
        # refuse it for the same reason, or the hole is open one door along.
        profiled = REGISTRY.call(
            "profile_dataset",
            {"path": str(path), "split": "eval"},
            actor=USER,
            thread_id=THREAD,
        )
        self.assertTrue(profiled["rows_are_truncated"])
        self.assertNotIn("measured_facts", profiled)
        self.assertEqual(evidence.rows_for(THREAD), [])

    def test_an_empty_json_array_really_is_a_measured_zero(self):
        """The other side of it, or the guard above would just be a refusal.

        `[]` is a dataset with nothing in it and that IS a count of zero. The
        guard re-parses rather than guessing from the file's size precisely so
        that this case is told apart from the broken one above.
        """
        path = self.root / "empty.json"
        path.write_text("[]", encoding="utf-8")
        result = REGISTRY.call(
            "measure_eval_set", {"path": str(path)}, actor=USER, thread_id=THREAD
        )
        self.assertEqual(result["rows"], 0)
        self.assertTrue(result["exact"])
        self.assertEqual(self.stamped(THREAD), [("eval_size_n", 0, MEASURED)])


class TheCountIsTheRowsEverythingElseWillSeeTest(unittest.TestCase):
    """`count_rows` must not become a faster reader that disagrees with the real one.

    A count taken by a cheaper route that got a different answer from
    `iter_records` would be this defect's fix producing this defect's twin:
    `measure_eval_set` would say 200,001 and `measure_baseline` would score a
    different set of rows. So the count is defined as what `iter_records`
    yields, and this asserts it on every readable shape the sniffer produces -
    including the awkward ones, which is where a hand-rolled counter would drift.
    """

    def setUp(self):
        self.root = support.sandbox(self)
        support.a_conversation(THREAD)

    def fixtures(self) -> dict[str, Path]:
        root = self.root
        rows = 137
        made: dict[str, Path] = {}

        made["jsonl"] = jsonl(root / "a.jsonl", rows)

        csv_path = root / "a.csv"
        csv_path.write_text(
            "q,a\n" + "".join(f"q{i},l{i % 5}\n" for i in range(rows)), encoding="utf-8"
        )
        made["csv"] = csv_path

        tsv_path = root / "a.tsv"
        tsv_path.write_text(
            "q\ta\n" + "".join(f"q{i}\tl{i % 5}\n" for i in range(rows)),
            encoding="utf-8",
        )
        made["tsv"] = tsv_path

        json_path = root / "a.json"
        json_path.write_text(
            json.dumps([{"q": f"q{i}"} for i in range(rows)]), encoding="utf-8"
        )
        made["json"] = json_path

        text_path = root / "a.txt"
        text_path.write_text(
            "".join(f"line {i}\n" for i in range(rows)), encoding="utf-8"
        )
        made["text"] = text_path

        folder = root / "folder"
        folder.mkdir()
        for index in range(rows):
            (folder / f"f{index:04d}.txt").write_text(f"body {index}\n", encoding="utf-8")
        made["text_folder"] = folder

        # A CSV field holding a newline is one row, not two. A counter that read
        # lines instead of records would say three here and it would be wrong.
        awkward = root / "awkward.csv"
        awkward.write_text('a,b\n"one\ntwo",x\n\nthree,y\n', encoding="utf-8")
        made["csv_with_an_embedded_newline"] = awkward

        # Blank lines and a line that is not JSON. `iter_records` yields the
        # unparsable one as a row rather than dropping it, and the count must
        # agree with that choice rather than with a tidier one.
        ragged = root / "ragged.jsonl"
        ragged.write_text('{"a":1}\n\n   \n{"a":2}\n{"a":3}\n', encoding="utf-8")
        made["jsonl_with_blank_lines"] = ragged

        made["empty"] = root / "empty.csv"
        made["empty"].write_text("", encoding="utf-8")

        made["header_only"] = root / "header.csv"
        made["header_only"].write_text("a,b\n", encoding="utf-8")

        return made

    def test_count_rows_agrees_with_iter_records_on_every_readable_shape(self):
        for label, path in self.fixtures().items():
            fmt = dataquality.detect_format(path)
            if not fmt.get("readable"):
                continue
            with self.subTest(shape=label, format=fmt.get("name")):
                truth = sum(1 for _ in dataquality.iter_records(path, fmt))
                counted = dataquality.count_rows(path, fmt=fmt)
                self.assertTrue(counted["exact"], counted["note"])
                self.assertEqual(counted["rows"], truth)
                self.assertEqual(counted["provenance"], dataquality.MEASURED)

    def test_the_awkward_shapes_are_actually_awkward(self):
        """Non-vacuity for the loop above: these differ from a line count.

        Two rows across five lines: one field holds a newline, and the blank
        line between the rows is not a row - which is `csv.DictReader`'s own
        answer, and the count has to be its answer rather than a tidier one.
        """
        made = self.fixtures()
        embedded = made["csv_with_an_embedded_newline"]
        self.assertEqual(dataquality.count_rows(embedded)["rows"], 2)
        self.assertEqual(
            len(embedded.read_text(encoding="utf-8").splitlines()),
            5,
            "the fixture must have more lines than rows or it proves nothing",
        )

    def test_a_count_of_nothing_is_still_a_count(self):
        made = self.fixtures()
        for label in ("empty", "header_only"):
            with self.subTest(shape=label):
                counted = dataquality.count_rows(made[label])
                self.assertEqual(counted["rows"], 0)
                self.assertTrue(counted["exact"])


class TheNextStepMustSurviveTheSetWeJustAgreedToTest(unittest.TestCase):
    """A fix that moves a wall instead of removing it has not removed the wall.

    Passing G0 routes straight to `ACTION__MEASURE_BASELINE`, so the moment
    `measure_eval_set` began stamping five-million-row eval sets, the tool the
    user is sent to next had to survive one. It did not: `measure_baseline`
    began `records = list(dataquality.iter_records(eval_path))`, holding the
    entire set in memory in order to score at most `MAX_BASELINE_SAMPLE` rows of
    it. Nobody could reach that while the count was capped at 200,000, and the
    cap is what this run removed.

    Measured with `tracemalloc` around the real tool call, on an 18.7 MB
    400,000-row set: 153.0 MB peak before, 0.3 MB after, with `rows_available`
    and `rows_scored` identical either way.

    ASSERTED AS A SHAPE AND NOT AS A NUMBER. A megabyte threshold is a number
    about this machine; "the peak does not grow with the size of the eval set"
    is the property that makes the tool safe at sizes no fixture here can build.
    Against the old code the same two measurements were 9.7 MB and 38.0 MB.
    """

    def setUp(self):
        self.root = support.sandbox(self)
        support.a_conversation(THREAD)
        evidence.ensure_table()

        from app.providers import Delta, store as provider_store
        from app.tools import measure

        class Scripted:
            """The one method `measure_baseline` uses. No network, no adapter."""

            def stream(self, conversation, offered, *, secret=None):
                yield Delta(kind="text", text="label0")

        row = provider_store.create(
            "Scripted", "http://127.0.0.1:11434", "scripted", "ollama"
        )
        provider_store.set_active(row["id"])
        original = measure.build
        measure.build = lambda *args, **kwargs: Scripted()
        self.addCleanup(setattr, measure, "build", original)

    def peak_bytes_for(self, rows: int, thread: int) -> int:
        import tracemalloc

        support.a_conversation(thread)

        path = jsonl(self.root / f"eval_{rows}.jsonl", rows)
        tracemalloc.start()
        try:
            result = REGISTRY.call(
                "measure_baseline",
                {
                    "eval_path": str(path),
                    "input_field": "q",
                    "expected_field": "a",
                    "sample": 5,
                },
                actor=USER,
                thread_id=thread,
            )
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        # Non-vacuity: it really did read the whole file and score from it.
        self.assertTrue(result["ok"], result.get("summary"))
        self.assertEqual(result["rows_available"], rows)
        self.assertEqual(result["rows_scored"], 5)
        return peak

    def test_the_baseline_does_not_hold_the_eval_set_it_is_sampling_from(self):
        small = self.peak_bytes_for(25_000, THREAD)
        large = self.peak_bytes_for(100_000, THREAD + 1)
        self.assertLess(
            large - small,
            4 * 1024 * 1024,
            "four times the eval set grew the peak heap by "
            f"{(large - small) / 1e6:.1f} MB, so the rows are being collected "
            "rather than streamed",
        )


class NothingIsCountedThatWasNotReadTest(unittest.TestCase):
    """The refusals, which have to stay refusals."""

    def setUp(self):
        self.root = support.sandbox(self)
        support.a_conversation(THREAD)
        evidence.ensure_table()

    def test_a_path_that_is_not_there_counts_nothing_and_stamps_nothing(self):
        result = REGISTRY.call(
            "measure_eval_set",
            {"path": str(self.root / "nope.jsonl")},
            actor=USER,
            thread_id=THREAD,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["stopped_because"], "no_such_path")
        self.assertEqual(evidence.rows_for(THREAD), [])

    def test_a_format_with_no_reader_is_not_a_count_of_zero(self):
        path = self.root / "eval.parquet"
        path.write_bytes(b"PAR1" + b"\x00" * 64)
        result = REGISTRY.call(
            "measure_eval_set", {"path": str(path)}, actor=USER, thread_id=THREAD
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["stopped_because"], "no_reader")
        self.assertIn("not a count of zero", result["summary"])
        self.assertEqual(evidence.rows_for(THREAD), [])

    def test_the_tool_does_not_claim_to_have_inspected_what_it_only_counted(self):
        """Defect 3's rule: a check that did not run says so.

        The tool used to hand back `profile`'s `checks_not_run`, which was empty
        because `profile` had in fact run them all. It counts now and inspects
        nothing, so an empty list would be a clean bill of health nobody earned.
        """
        path = jsonl(self.root / "eval.jsonl", 40)
        result = REGISTRY.call(
            "measure_eval_set", {"path": str(path)}, actor=USER, thread_id=THREAD
        )
        skipped = {entry["check"] for entry in result["checks_not_run"]}
        self.assertIn("duplicates", skipped)
        self.assertIn("label_imbalance", skipped)
        self.assertNotIn("row_count", skipped)
        for entry in result["checks_not_run"]:
            self.assertTrue(entry["why"].strip())


if __name__ == "__main__":
    unittest.main()
