"""The harness writes a dataset - and refuses to call a pile of inputs an eval set.

`app/tools/datawork.py` is the first capability in this product that changes the
user's disk. Fourteen tools sat in the Data group and every `writes=` among them
was `facts`, `evals`, `prompts` or `retrieval`; `assess_the_data` part five
computed everything a carve needs and ended *"Nothing has been carved and no
file has been written."* That is the same shape as `retriever_recall_at_k` being
declared `source: inspect` with no instrument able to take the reading, sitting
on the blocker a thread reaches first - `BLOCKED__BUILD_EVAL_SET`.

This file is the adversarial half of that claim. It is organised around the one
line the whole capability turns on and the four properties that make writing to
somebody's disk something a product may do at all.

  THE LINE     - splitting is mechanical, grading is judgement. A held-out slice
                 of unlabelled rows is a pile of inputs with no right answers,
                 and a gate that opened on one would be the five-gate test
                 defeated by a file we wrote ourselves.
                 `TheGradingLineIsInTheCodeTest` is the centre of this file.
  NEVER OVER   - the destination must not exist, must not be the source, must
                 not be inside a folder source; and after any refusal there is
                 nothing on disk. Checked by fingerprinting the bytes, not by
                 reading the message.
  THE SIZE     - comes from G0's own threshold, read off the engine. Not a
                 percentage somebody liked, and the same number
                 `propose.g0_minimum` plans against.
  REPRODUCIBLE - the same call gives the same split, in another process and in
                 another row order, and two identical rows cannot be separated.
  IT CHECKS    - the real `check_split_leakage` runs over what was written and
                 the answer is in the reply. A split we produced and did not
                 verify is worse than one a user made.

And the one thing it must NOT do: `AWrittenFileIsNotAMeasurementTest`. Writing
forty rows and counting forty rows in a file that exists are different claims,
and G0 reads the second. Both writing tools declare `measures=()` and neither
handler takes an `instrument`, so there is no object in scope that could stamp -
a shape rather than a promise, and this file asserts the shape.

Nothing here uses a network or a model. Every fixture is written by this file
into the temporary root `support.sandbox` hands out, so every count asserted
below is arithmetic over text that is visible here.
"""

from __future__ import annotations

import csv
import json
import random
import sys
import unittest
from pathlib import Path

from app import dataquality, diagnosis, identity
from app.tools import REGISTRY, data, datawork, propose
from app.tools.evidence import MEASURED, MODEL, USER
from app.tools.registry import ApprovalRequired

import support


# ---------------------------------------------------------------------------
# Fixtures.

#: Twenty ordinary words with nothing in common, shuffled eight at a time into
#: each row. TEXTUALLY DISTINCT ON PURPOSE, and the first draft was not: rows
#: like "customer 41 reports a broken widget number 41" are near-duplicates of
#: each other at Jaccard 0.8, so the carve's own leakage check came back with
#: two leaked rows on a fixture that was meant to be clean. That was the check
#: working, and it is why `ASplitThatLeaksIsAFailedStepTest` below builds that
#: case on purpose instead of leaving it lying under the happy path.
WORDS = (
    "orbit ledger kettle marmalade harbour tundra quartz velvet abacus pylon "
    "cinder thistle granite lagoon ember fathom juniper nimbus obsidian plinth"
).split()

ANSWERS = ("billing", "shipping", "fraud")


def rows_for(count: int, *, answered: bool = True, seed: int = 7) -> list[dict]:
    """`count` rows of distinct text, each with an answer unless told otherwise."""
    rng = random.Random(seed)
    out = []
    for index in range(count):
        row = {"ticket": " ".join(rng.sample(WORDS, 8)) + f" case {index}"}
        if answered:
            row["reason"] = ANSWERS[index % len(ANSWERS)]
        out.append(row)
    return out


def as_csv(path: Path, rows: list[dict]) -> Path:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def as_jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )
    return path


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def multiset(rows: list[dict]) -> list[str]:
    """Rows as comparable, order-insensitive text. Duplicates stay duplicated."""
    return sorted(json.dumps(row, sort_keys=True) for row in rows)


#: THIS FILE IS ABOUT THE MACHINE-LEARNING LEDGER, AND NOW IT SAYS SO.
#: `carve_eval_set` takes the ledger of the conversation it is running in - the
#: eval-set floor it refuses against is `eval_size_n`'s gate, which is a thing
#: one domain's knowledge states and another's does not. Through the registry
#: that ledger is injected from `threads.ledger`; called directly, as these
#: tests do, the caller has to name it, because a default here would be the
#: silent wrong read that `app/tools/registry.py`'s wall 7 exists to remove.
THE_LEDGER = diagnosis.default_spec()


def carve_the_eval_set(**arguments):
    """`datawork.carve_eval_set` against this file's ledger, named once."""
    return datawork.carve_eval_set(ledger=THE_LEDGER, **arguments)


class WritesADatasetTest(unittest.TestCase):
    """A sandbox, a source file, and a place to put things that is not the repo."""

    ROWS = 200

    def setUp(self) -> None:
        self.root = support.sandbox(self)
        self.rows = rows_for(self.ROWS)
        self.source = as_csv(self.root / "tickets.csv", self.rows)
        self.floor = data.eval_set_floor()["rows"]

    def out(self, name: str) -> Path:
        """A destination that does not exist, under this test's own temp root."""
        return self.root / "out" / name

    def carve(self, **arguments):
        payload = {
            "path": str(self.source),
            "answer_column": "reason",
            "into": str(self.out("split")),
        }
        payload.update({k: v for k, v in arguments.items() if v is not None})
        return carve_the_eval_set(**payload)

    def dedupe(self, **arguments):
        payload = {"path": str(self.source), "into": str(self.out("dedup"))}
        payload.update(arguments)
        return datawork.drop_duplicates(**payload)


# ---------------------------------------------------------------------------


class TheGradingLineIsInTheCodeTest(WritesADatasetTest):
    """The centre of this file, and the thing the capability turns on.

    G0's own recipe, in `docs/diagnosis_engine.yaml`: *"30-50 real inputs
    sampled from actual traffic, graded by the person who cares about the
    answer."* Four ways of arriving with rows that carry no right answers, four
    refusals, and nothing on disk after any of them.
    """

    def g0_recipe(self) -> str:
        gate = diagnosis.default_spec().gates["G0_EVAL_SET"]
        return str(gate["on_fail"]["recipe"])

    def assertNothingWritten(self, result, destination: Path) -> None:
        self.assertFalse(result["ok"], result.get("summary"))
        self.assertTrue(result["nothing_was_written"])
        self.assertFalse(
            destination.exists(),
            f"{destination} was created by a call that refused",
        )

    def test_unlabelled_data_is_not_split_at_all(self):
        """No answer column named. The refusal quotes the engine's own recipe."""
        destination = self.out("nope")
        result = carve_the_eval_set(
            path=str(self.source), answer_column="", into=str(destination)
        )
        self.assertEqual(result["error"], "no_answer_column")
        self.assertIn(self.g0_recipe(), result["summary"])
        self.assertNothingWritten(result, destination)

    def test_a_column_that_is_not_there_is_named_along_with_the_ones_that_are(self):
        destination = self.out("nope")
        result = carve_the_eval_set(
            path=str(self.source), answer_column="verdict", into=str(destination)
        )
        self.assertEqual(result["error"], "no_such_column")
        self.assertIn("ticket", result["summary"])
        self.assertIn("reason", result["summary"])
        self.assertNothingWritten(result, destination)

    def test_a_column_that_is_there_and_empty_is_a_pile_of_inputs(self):
        """The case the whole line exists for: the shape is right, the answers
        are absent, and splitting it would produce a file of questions."""
        blank = as_csv(
            self.root / "unanswered.csv",
            [{"ticket": row["ticket"], "reason": ""} for row in self.rows],
        )
        destination = self.out("nope")
        result = carve_the_eval_set(
            path=str(blank), answer_column="reason", into=str(destination)
        )
        self.assertEqual(result["error"], "no_answers_in_the_column")
        self.assertEqual(result["rows_with_an_answer"], 0)
        self.assertEqual(result["grading_is_yours"], self.g0_recipe())
        self.assertNothingWritten(result, destination)

    def test_one_answer_repeated_is_not_a_set_of_right_answers(self):
        """A column full of 'billing' measures nothing: always answering the
        majority already scores 100%, and the threshold is ours and is named."""
        flat = as_csv(
            self.root / "one_class.csv",
            [{"ticket": row["ticket"], "reason": "billing"} for row in self.rows],
        )
        destination = self.out("nope")
        result = carve_the_eval_set(
            path=str(flat), answer_column="reason", into=str(destination)
        )
        self.assertEqual(result["error"], "the_answers_are_one_value")
        self.assertEqual(result["distinct_answers"], 1)
        self.assertEqual(result["threshold"], dataquality.IMBALANCE_BLOCK_SHARE)
        self.assertIn("app/dataquality.py", result["summary"])
        self.assertNothingWritten(result, destination)

    def test_the_same_rows_with_answers_in_them_are_carved(self):
        """Non-vacuity. Every refusal above is about the answers and not about
        the shape of the file, so the identical fixture WITH answers works."""
        result = self.carve()
        self.assertTrue(result["ok"], result["summary"])
        self.assertEqual(result["eval_rows"], self.floor)

    def test_a_dataset_too_small_to_give_up_rows_is_refused_with_the_alternative(self):
        """Carving would leave less than the product's own training floor.

        And the refusal names the honest other answer rather than stopping: if
        you are not training on this, the whole file is the eval set and
        `measure_eval_set` is what counts it.
        """
        small = as_csv(self.root / "small.csv", rows_for(60))
        destination = self.out("nope")
        result = carve_the_eval_set(
            path=str(small), answer_column="reason", into=str(destination)
        )
        self.assertEqual(result["error"], "would_starve_training")
        self.assertEqual(result["rows_read"], 60)
        self.assertEqual(result["would_leave"], 60 - result["would_hold_out"])
        self.assertEqual(
            result["minimum_to_train_on"], dataquality.MIN_ROWS_FOR_TRAINING
        )
        self.assertIn("measure_eval_set", result["summary"])
        self.assertNothingWritten(result, destination)

    def test_too_few_answered_rows_to_reach_the_floor_is_refused(self):
        """Enough rows to train on, not enough answered ones to hold out."""
        mixed = rows_for(300)
        for row in mixed[10:]:
            row["reason"] = ""
        source = as_csv(self.root / "mostly_blank.csv", mixed)
        destination = self.out("nope")
        result = carve_the_eval_set(
            path=str(source), answer_column="reason", into=str(destination)
        )
        self.assertEqual(result["error"], "not_enough_answered_rows")
        self.assertEqual(result["rows_that_could_be_held_out"], 10)
        self.assertEqual(result["short_by"], self.floor - 10)
        self.assertIn(self.g0_recipe(), result["summary"])
        self.assertNothingWritten(result, destination)


# ---------------------------------------------------------------------------


class NothingIsEverWrittenOverTest(WritesADatasetTest):
    """Their data is the one thing we cannot regenerate.

    Every assertion here is about BYTES rather than about a message: the source
    is fingerprinted before and after, and an existing destination is
    fingerprinted before and after, so a refusal that says the right thing while
    doing the wrong thing fails.
    """

    def test_a_destination_that_exists_is_refused_and_left_alone(self):
        destination = self.root / "already"
        destination.mkdir()
        (destination / "someone_elses.txt").write_text("keep me", encoding="utf-8")
        before = support.tree_fingerprint(destination)

        result = self.carve(into=str(destination))

        # LAW SUBSTITUTED 2026-09-17. This read "refused: destination_exists".
        # Max's thread 75: generate_rows was refused four times for naming a
        # folder that existed, and the run stalled on it. Nothing writes over
        # anything - that rule stands - so the output goes to the next free
        # name BESIDE the folder, and the folder somebody else filled is
        # untouched.
        self.assertTrue(result["ok"], result)
        self.assertEqual(Path(result["into"]).name, destination.name + "-2")
        self.assertEqual(support.tree_fingerprint(destination), before)

    def test_a_destination_that_is_a_file_is_refused(self):
        destination = self.root / "already.txt"
        destination.write_text("keep me", encoding="utf-8")
        result = self.carve(into=str(destination))
        # A FILE at the destination is still refused: that is a person's file,
        # not a folder somebody meant to fill.
        self.assertEqual(result["error"], "destination_exists")
        self.assertEqual(destination.read_text(encoding="utf-8"), "keep me")

    def test_writing_onto_the_source_itself_lands_beside_it(self):
        """LAW SUBSTITUTED 2026-09-17: was refused as would_write_in_place.
        Nothing is written in place - the output lands in `<name>-out` beside
        the source, and the source is exactly as it was."""
        before = self.source.read_bytes()
        result = self.carve(into=str(self.source))
        self.assertTrue(result["ok"], result)
        self.assertEqual(Path(result["into"]).name, self.source.name + "-out")
        self.assertEqual(self.source.read_bytes(), before)

    def documents(self, name: str = "corpus", count: int = 200) -> Path:
        """A folder of text files - a dataset `profile_dataset` reads today."""
        folder = self.root / name
        folder.mkdir()
        for index in range(count):
            (folder / f"doc{index}.txt").write_text(
                " ".join(random.Random(index).sample(WORDS, 8)) + f" case {index}",
                encoding="utf-8",
            )
        self.assertTrue(dataquality.detect_format(folder)["readable"])
        return folder

    def test_writing_inside_a_folder_dataset_is_refused(self):
        """A folder dataset is one row per file, so output written inside it
        becomes rows of it the next time anybody profiles it.

        REACHED RATHER THAN ASSUMED. This used to run `drop_duplicates` over a
        three-file folder and accept either `would_write_inside_the_source` or
        `no_duplicates` - and it was always the second, because a folder row
        carries the filename and no two of them can be identical, so the
        destination guard this test is named for was never reached. A folder of
        distinct documents carved on its `text` column reaches it.
        """
        folder = self.documents()
        result = carve_the_eval_set(
            path=str(folder), answer_column="text", into=str(folder / "split")
        )
        self.assertEqual(result["error"], "would_write_inside_the_source")
        self.assertFalse((folder / "split").exists())
        self.assertTrue(dataquality.detect_format(folder)["readable"])

    def test_writing_inside_somebody_elses_dataset_is_refused_too(self):
        """The half the guard above did not have, and the damage is real.

        The reason written beside `would_write_inside_the_source` is not about
        the source: *"our output landing inside somebody's dataset directory
        means their next profile counts our files as their rows."* A carve of
        `graded.csv` into `corpus/carved`, where `corpus` is a folder of `.txt`
        documents nobody mentioned, went through and returned `ok: true` - and
        `corpus` went from `text_folder, readable: True` to `folder,
        readable: False` in the same call, because a folder is only readable
        when every data file under it is text. A dataset this call was not asked
        to touch stopped being openable by every tool in the product, silently.
        """
        folder = self.documents(count=5)
        before = dataquality.detect_format(folder)

        result = self.carve(into=str(folder / "carved"))

        self.assertEqual(result["error"], "would_write_inside_a_dataset")
        self.assertEqual(result["dataset"], str(folder.resolve()))
        self.assertTrue(result["nothing_was_written"])
        self.assertFalse((folder / "carved").exists())
        self.assertEqual(dataquality.detect_format(folder), before)

    def test_the_guard_climbs_past_the_levels_that_do_not_exist_yet(self):
        """`mkdir(parents=True)` creates them, and `rglob` counts every depth.

        A destination two new levels down is still inside the dataset, and a
        check that only looked at the immediate parent - which does not exist
        yet - would see nothing and allow it.
        """
        folder = self.documents(count=5)
        result = self.carve(into=str(folder / "a" / "b" / "out"))
        self.assertEqual(result["error"], "would_write_inside_a_dataset")
        self.assertFalse((folder / "a").exists())
        self.assertTrue(dataquality.detect_format(folder)["readable"])

    def test_an_ordinary_directory_is_not_mistaken_for_a_dataset(self):
        """The negative control. A folder holding a `.csv` is not a text folder,
        and refusing to write beside somebody's data file would be useless."""
        beside = self.root / "beside"
        self.assertFalse(dataquality.detect_format(self.root)["readable"])
        result = self.carve(into=str(beside))
        self.assertTrue(result["ok"], result["summary"])
        self.assertTrue(beside.is_dir())

    def test_a_successful_carve_does_not_touch_the_source(self):
        before = support.tree_fingerprint(self.source)
        result = self.carve()
        self.assertTrue(result["ok"], result["summary"])
        self.assertEqual(support.tree_fingerprint(self.source), before)

    def test_the_same_destination_twice_is_refused_the_second_time(self):
        first = self.carve()
        self.assertTrue(first["ok"], first["summary"])
        before = support.tree_fingerprint(Path(first["into"]))

        second = self.carve()

        # LAW SUBSTITUTED 2026-09-17: the second carve lands beside the first
        # rather than being refused, and the first is untouched.
        self.assertTrue(second["ok"], second)
        self.assertNotEqual(second["into"], first["into"])
        self.assertEqual(support.tree_fingerprint(Path(first["into"])), before)

    def test_a_read_that_would_be_truncated_writes_nothing(self):
        """A cap on a READER truncates the answer. A cap on a WRITER cannot: a
        deduplicated file missing the tail of somebody's data would not say so.
        """
        destination = self.out("capped")
        result = self.carve(into=str(destination), max_rows=50)
        self.assertEqual(result["error"], "more_rows_than_the_limit")
        self.assertEqual(result["max_rows"], 50)
        self.assertFalse(destination.exists())


# ---------------------------------------------------------------------------


class TheSizeComesFromTheGateTest(WritesADatasetTest):
    """Not a percentage somebody liked, and not a number typed in this lane."""

    def test_the_two_readers_of_the_threshold_agree(self):
        """`data.eval_set_floor` and `propose.g0_minimum` read the same gate.

        One is what the carve sizes itself by, the other is what the proposer
        plans against. A threshold that moved for one and not the other would
        let the product propose a build for thirty rows and write forty.
        """
        self.assertEqual(data.eval_set_floor()["rows"], propose.g0_minimum())

    def test_the_eval_file_holds_exactly_what_the_gate_asks_for(self):
        result = self.carve()
        self.assertEqual(result["eval_rows"], self.floor)
        self.assertEqual(result["rows_asked_for"], self.floor)
        self.assertEqual(
            result["floor"]["declared_in"],
            "G0_EVAL_SET.passes_when in docs/diagnosis_engine.yaml",
        )
        self.assertEqual(len(read_jsonl(Path(result["eval_path"]))), self.floor)

    def test_a_bigger_file_does_not_get_a_bigger_eval_set(self):
        """The tell for a hardcoded percentage. 1,000 rows at 20% would be 200."""
        big = as_csv(self.root / "big.csv", rows_for(1000, seed=11))
        result = carve_the_eval_set(
            path=str(big), answer_column="reason", into=str(self.out("big"))
        )
        self.assertTrue(result["ok"], result["summary"])
        self.assertEqual(result["eval_rows"], self.floor)
        self.assertEqual(result["train_rows"], 1000 - self.floor)

    def test_asking_for_fewer_rows_than_the_gate_is_refused(self):
        destination = self.out("tiny")
        result = self.carve(into=str(destination), rows=5)
        self.assertEqual(result["error"], "fewer_rows_than_the_gate_asks_for")
        self.assertEqual(result["asked_for"], 5)
        self.assertFalse(destination.exists())

    def test_asking_for_more_is_allowed_and_recorded_as_the_callers(self):
        result = self.carve(into=str(self.out("more")), rows=60)
        self.assertTrue(result["ok"], result["summary"])
        self.assertEqual(result["eval_rows"], 60)
        self.assertEqual(result["method"]["rows_asked_for_came_from"], "the caller")


# ---------------------------------------------------------------------------


class TheGatesNumberIsDistinctRowsTest(WritesADatasetTest):
    """The same question forty times is one question, and this counted forty.

    THE DEFECT, reproduced on disk before it was fixed. A support export of two
    hundred tickets that are five tickets repeated forty times each carved
    clean: `ok: true`, a forty-row eval file, `check_split_leakage` reporting
    "No overlap: none of the 40 eval rows matched any of the 160 train rows",
    and every one of those forty rows the SAME ROW. `measure_eval_set` on it
    would have counted forty and stamped `eval_size_n = 40` MEASURED, and G0 -
    whose recipe asks for "30-50 real inputs sampled from actual traffic" -
    would have opened on one input.

    That is the module docstring's own sentence coming true: *"a held-out slice
    of unlabelled rows is a pile of inputs with no right answers, and handing
    one over as an eval set would be the five-gate test defeated by a file we
    wrote ourselves."* The rows had answers. There was one of them.

    Nothing here is about duplicates being wrong. A dataset with repeats is
    ordinary; what was wrong was counting them toward a threshold that is about
    how many different questions you can ask.
    """

    def repeated(self, distinct: int, copies: int, name: str = "repeats.csv") -> Path:
        """`distinct` different graded rows, each written `copies` times."""
        base = rows_for(distinct, seed=3)
        out = [dict(base[index % distinct]) for index in range(distinct * copies)]
        self.assertEqual(len({json.dumps(r, sort_keys=True) for r in out}), distinct)
        return as_csv(self.root / name, out)

    def test_a_file_that_is_five_questions_two_hundred_times_is_refused(self):
        source = self.repeated(distinct=5, copies=40)
        destination = self.out("five")

        result = carve_the_eval_set(
            path=str(source), answer_column="reason", into=str(destination)
        )

        self.assertEqual(result["error"], "not_enough_answered_rows")
        self.assertEqual(result["rows_read"], 200)
        self.assertEqual(result["distinct_rows_that_could_be_held_out"], 5)
        self.assertEqual(result["short_by"], self.floor - 5)
        self.assertIn("distinct", result["summary"])
        self.assertTrue(result["nothing_was_written"])
        self.assertFalse(destination.exists())

    def test_the_refusal_says_more_rows_of_the_same_thing_will_not_help(self):
        """Because "get more data" reads as permission to paste the file twice."""
        result = carve_the_eval_set(
            path=str(self.repeated(distinct=5, copies=40)),
            answer_column="reason",
            into=str(self.out("says")),
        )
        self.assertIn("drop_duplicates", result["summary"])
        self.assertIn("repeat an earlier row", result["summary"])
        self.assertIn(
            diagnosis.default_spec().gates["G0_EVAL_SET"]["on_fail"]["recipe"],
            result["summary"],
        )

    def test_enough_distinct_rows_carves_and_the_file_says_which_number_is_which(self):
        """A hundred questions asked three times each is a hundred questions."""
        source = self.repeated(distinct=100, copies=3, name="triple.csv")

        result = carve_the_eval_set(
            path=str(source), answer_column="reason", into=str(self.out("triple"))
        )

        self.assertTrue(result["ok"], result["summary"])
        self.assertEqual(result["eval_distinct_rows"], self.floor)
        written = read_jsonl(Path(result["eval_path"]))
        self.assertEqual(len(written), result["eval_rows"])
        self.assertEqual(
            len({json.dumps(row, sort_keys=True) for row in written}), self.floor
        )
        self.assertGreater(result["eval_rows"], self.floor)
        # And it is said out loud, because `measure_eval_set` will count rows.
        self.assertIn("DISTINCT", result["summary"])
        self.assertIn(f"a score on it is a score on {self.floor} questions", result["summary"])
        self.assertEqual(result["method"]["distinct_rows_held_out"], self.floor)

    def test_a_file_with_no_repeats_is_unchanged_by_any_of_this(self):
        """The negative control: distinct rows and rows are the same number."""
        result = self.carve()
        self.assertTrue(result["ok"], result["summary"])
        self.assertEqual(result["eval_rows"], self.floor)
        self.assertEqual(result["eval_distinct_rows"], self.floor)


# ---------------------------------------------------------------------------


class TheSplitIsReproducibleTest(WritesADatasetTest):
    """A split nobody can reproduce is a number nobody can defend."""

    def test_the_same_call_twice_gives_the_same_split(self):
        first = self.carve(into=str(self.out("a")))
        second = self.carve(into=str(self.out("b")))
        self.assertEqual(
            Path(first["eval_path"]).read_bytes(),
            Path(second["eval_path"]).read_bytes(),
        )
        self.assertEqual(
            Path(first["train_path"]).read_bytes(),
            Path(second["train_path"]).read_bytes(),
        )

    def test_a_different_seed_gives_a_different_split(self):
        first = self.carve(into=str(self.out("a")))
        other = self.carve(into=str(self.out("b")), seed="second-draw")
        self.assertNotEqual(
            Path(first["eval_path"]).read_bytes(),
            Path(other["eval_path"]).read_bytes(),
        )
        self.assertEqual(other["method"]["seed"], "second-draw")

    def test_the_split_does_not_depend_on_the_order_the_rows_were_read_in(self):
        """The property a shuffle cannot have. The rows are hashed, so the same
        rows in a different order draw the same eval set."""
        shuffled = list(self.rows)
        random.Random(99).shuffle(shuffled)
        other = as_csv(self.root / "shuffled.csv", shuffled)

        first = self.carve(into=str(self.out("a")))
        second = carve_the_eval_set(
            path=str(other), answer_column="reason", into=str(self.out("b"))
        )

        self.assertEqual(
            multiset(read_jsonl(Path(first["eval_path"]))),
            multiset(read_jsonl(Path(second["eval_path"]))),
        )

    def test_the_source_format_does_not_change_the_split(self):
        """The same rows in a CSV and in a JSONL draw the same eval set.

        The signature is over the row's values, so the file the rows arrived in
        is not part of the decision - and both are written out as JSON Lines,
        which is the one shape that survives rows whose columns differ.
        """
        other = as_jsonl(self.root / "tickets.jsonl", self.rows)

        from_csv = self.carve(into=str(self.out("a")))
        from_jsonl = carve_the_eval_set(
            path=str(other), answer_column="reason", into=str(self.out("b"))
        )

        self.assertEqual(
            multiset(read_jsonl(Path(from_csv["eval_path"]))),
            multiset(read_jsonl(Path(from_jsonl["eval_path"]))),
        )
        for result in (from_csv, from_jsonl):
            self.assertTrue(result["eval_path"].endswith(".eval.jsonl"))

    def test_the_rule_that_decided_it_is_written_down(self):
        result = self.carve()
        manifest = json.loads(
            Path(result["manifest_path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["method"]["rule"], datawork.SELECTION_RULE)
        self.assertIn("signature_of_text", manifest["method"]["how"])
        self.assertEqual(manifest["method"]["answer_column"], "reason")
        self.assertEqual(manifest["method"]["rows_asked_for"], self.floor)

    def test_a_signature_is_the_same_number_in_every_process(self):
        """`hash()` is salted per process, so a split decided by it would come
        out differently on the next run. This is the one line that stops that,
        and it is asserted against a constant rather than against itself."""
        self.assertEqual(
            dataquality.signature_of_text("the same text"),
            dataquality.signature_of_text("The   Same Text  "),
        )
        self.assertEqual(
            dataquality.row_signature({"a": "one", "b": "two"}),
            dataquality.signature_of_text("one two"),
        )


# ---------------------------------------------------------------------------


class IdenticalRowsCannotBeSplitTest(WritesADatasetTest):
    """The leak the carve is structurally incapable of creating.

    A random split of a file containing duplicates puts the same row in both
    halves, and that is the commonest way a leak gets in. Here the SIGNATURE
    decides the side, so two identical rows have the same key and are drawn
    together - checked on a fixture whose duplicates are visible, and then
    checked again by the real leakage tool.
    """

    def setUp(self) -> None:
        super().setUp()
        doubled = self.rows + [dict(row) for row in self.rows[:40]]
        self.source = as_csv(self.root / "doubled.csv", doubled)
        self.doubled = doubled

    def test_both_copies_of_every_duplicated_row_land_on_the_same_side(self):
        result = self.carve()
        self.assertTrue(result["ok"], result["summary"])
        evaluation = multiset(read_jsonl(Path(result["eval_path"])))
        training = multiset(read_jsonl(Path(result["train_path"])))

        for row in self.doubled[:40]:
            text = json.dumps(row, sort_keys=True)
            with self.subTest(row=text[:40]):
                self.assertFalse(
                    text in evaluation and text in training,
                    "a row that appears twice in the source was split across "
                    "the two files",
                )

    def test_the_leakage_tool_finds_no_exact_match_between_the_two_files(self):
        result = self.carve()
        self.assertEqual(result["verification"]["exact_matches"], 0)

    def test_the_two_files_partition_the_source_exactly(self):
        """Nothing dropped, nothing written twice - including the duplicates,
        which are still all there because a carve is not a dedupe."""
        result = self.carve()
        rebuilt = read_jsonl(Path(result["eval_path"])) + read_jsonl(
            Path(result["train_path"])
        )
        self.assertEqual(multiset(rebuilt), multiset(self.doubled))
        self.assertTrue(result["verification"]["partition_holds"])


# ---------------------------------------------------------------------------


class WeCheckOurOwnWorkTest(WritesADatasetTest):
    """A split this harness produced and did not verify is worse than one a
    user made, because ours came with an implied promise."""

    def test_the_reply_carries_the_real_leakage_tool_run_on_the_real_files(self):
        result = self.carve()
        independent = data.check_split_leakage(
            train_path=result["train_path"], eval_path=result["eval_path"]
        )
        self.assertEqual(result["verification"]["tool"], "check_split_leakage")
        self.assertTrue(result["verification"]["ran"])
        self.assertEqual(
            result["verification"]["leaked_rows"], independent["leaked_rows"]
        )
        self.assertEqual(result["verification"]["summary"], independent["summary"])
        self.assertIn(independent["summary"], result["summary"])

    def test_the_verification_is_recorded_beside_the_files(self):
        result = self.carve()
        manifest = json.loads(
            Path(result["manifest_path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["verification"]["tool"], "check_split_leakage")
        self.assertEqual(
            manifest["verification"]["leaked_rows"],
            result["verification"]["leaked_rows"],
        )

    #: Two hundred tickets differing by one number. Every row is a near-duplicate
    #: of every other at our Jaccard threshold, so the whole file is ONE question
    #: asked two hundred ways.
    def _all_alike(self):
        similar = [
            {"ticket": f"the customer reports a broken widget number {index}",
             "reason": ANSWERS[index % len(ANSWERS)]}
            for index in range(200)
        ]
        return as_csv(self.root / "similar.csv", similar)

    def test_a_file_of_one_question_asked_two_hundred_ways_is_refused_before_writing(self):
        """WHAT THIS TEST USED TO ASSERT, AND WHY THE NEW ANSWER IS BETTER.

        It asserted that this file produced a leaking split reported as
        `ok: false` with the two files left on disk. That was the honest report
        of a bad situation, but the situation was one the tool created: it drew
        the split by EXACT signature and then judged it with a predicate that
        counts near duplicates as leaks, so on a file like this it leaked every
        time - measured at 30 of 30 eval rows, on 25 seeds out of 25.

        The draw is now made in the units the check judges it in, so this file
        does not produce a leaking split. It produces a REFUSAL, before anything
        is written, and the refusal is the true sentence: two hundred rows that
        are all the same question are not thirty questions, and an eval set built
        from them would measure one thing thirty times while `measure_eval_set`
        stamped `eval_size_n = 30` MEASURED onto gate G0.
        """
        result = carve_the_eval_set(
            path=str(self._all_alike()), answer_column="reason",
            into=str(self.out("leaky")),
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "not_enough_answered_rows")
        # FOUR, and the number is measured rather than assumed. `row_text` joins
        # every value, so the three `reason` values pull the rows into three
        # groups of their own; the `fraud` group then splits in two because these
        # strings are short enough that one digit against two is itself a real
        # difference at Jaccard 0.8. Sizes 67, 67, 33, 33 over 200 distinct rows.
        # Whatever the exact number, it is nowhere near the thirty G0 asks for,
        # and that is the sentence the refusal makes.
        self.assertEqual(result["distinct_rows_that_could_be_held_out"], 200)
        self.assertEqual(result["distinct_questions_that_could_be_held_out"], 4)
        self.assertEqual(len(ANSWERS), 3)
        clustering = result["near_duplicate_clustering"]
        self.assertEqual(clustering["clusters"], 4)
        self.assertEqual(clustering["largest_cluster"], 67)
        self.assertTrue(clustering["exhaustive"])
        self.assertIn("NEAR duplicates", result["summary"])
        self.assertNotIn("into", result)
        self.assertFalse(list(self.root.glob("**/*.eval.jsonl")))

    def test_a_split_that_leaks_is_still_reported_as_a_failed_step(self):
        """The `ok: false` path, driven on the one disagreement that survives.

        A carve can no longer leak by construction while the clustering pass sees
        what the check sees. It CAN when the pass was narrowed - a file larger
        than the similarity index holds, which `near_duplicate_clusters` reports
        as `exhaustive: false`. Forcing that is how the reporting path stays
        under test instead of being deleted along with the defect, because
        `ok: true` beside "leakage in what this just wrote" is the transcript
        lying quietly and that must stay impossible.
        """
        def blind(texts, *, threshold=dataquality.JACCARD_THRESHOLD):
            return {key: key for key in texts}, {
                "keys": len(texts), "clusters": len(texts), "pairs_found": 0,
                "largest_cluster": 1, "threshold": threshold,
                "threshold_is": "our policy, not a property of the data",
                "method": "none - the search was fully narrowed",
                "exhaustive": False, "narrowed_by": ["saturated_shingles"],
                "provenance": dataquality.INFERRED,
            }

        original = dataquality.near_duplicate_clusters
        dataquality.near_duplicate_clusters = blind
        try:
            result = carve_the_eval_set(
                path=str(self._all_alike()), answer_column="reason",
                into=str(self.out("leaky")),
            )
        finally:
            dataquality.near_duplicate_clusters = original

        self.assertFalse(result["ok"])
        self.assertGreater(result["verification"]["leaked_rows"], 0)
        self.assertEqual(result["verification"]["exact_matches"], 0)
        self.assertIn("LEAKAGE IN WHAT THIS JUST WROTE", result["summary"])
        self.assertIn("disagreeing with itself", result["summary"])
        # The files are still there and the reply says where. Deleting is the
        # one thing this module does not do.
        self.assertTrue(Path(result["eval_path"]).exists())
        self.assertIn(result["into"], result["summary"])


# ---------------------------------------------------------------------------


class ThereIsOneDefinitionOfADuplicateTest(WritesADatasetTest):
    """`assess_the_data` counts them; this removes them; they must be the same
    number. Before `dataquality.row_signature` they were the same idea written
    twice in two files - one of them through the salted builtin `hash()`."""

    def setUp(self) -> None:
        super().setUp()
        self.duplicated = self.rows + [dict(row) for row in self.rows[:17]]
        self.source = as_csv(self.root / "dupes.csv", self.duplicated)

    def test_the_profiler_the_assessor_and_the_writer_all_say_seventeen(self):
        profile = dataquality.profile(self.source)
        assessed = data.assess_the_data(
            path=str(self.source),
            label_column="reason",
            instrument=_instrument_for_assess(),
        )
        removed = self.dedupe()

        self.assertEqual(profile["duplicates"]["exact"], 17)
        self.assertEqual(assessed["answer"][0]["exact_duplicates"], 17)
        self.assertEqual(removed["exact_duplicates"], 17)
        self.assertEqual(removed["rows_removed"], 17)

    def test_the_definition_travels_with_the_file(self):
        removed = self.dedupe()
        manifest = json.loads(
            Path(removed["manifest_path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["method"]["definition"], datawork.DUPLICATE_IS)
        self.assertEqual(
            manifest["method"]["implementation"], "dataquality.row_signature"
        )

    def test_all_three_go_through_the_one_implementation(self):
        """Three numbers agreeing on a fixture is weak: two implementations that
        happen to match would pass it. So the definition is moved underneath all
        three at once - `signature_of_text` collapsed to a constant, which makes
        every row a duplicate of the first - and each of them has to follow. A
        counter with its own copy of the rule would not move.
        """
        rows = rows_for(40, seed=5)
        source = as_csv(self.root / "probe.csv", rows)
        original = dataquality.signature_of_text
        dataquality.signature_of_text = lambda text: 0
        try:
            profile = dataquality.profile(source)
            assessed = data.assess_the_data(
                path=str(source),
                label_column="reason",
                instrument=_instrument_for_assess(),
            )
            removed = datawork.drop_duplicates(
                path=str(source), into=str(self.out("collapsed"))
            )
        finally:
            dataquality.signature_of_text = original

        self.assertEqual(profile["duplicates"]["exact"], 39)
        self.assertEqual(assessed["answer"][0]["exact_duplicates"], 39)
        self.assertEqual(removed["rows_removed"], 39)
        self.assertEqual(removed["rows_kept"], 1)

    def test_column_names_are_not_part_of_it(self):
        """The definition says so, and it is the reason two exports of the same
        rows under different headers are duplicates of each other."""
        self.assertEqual(
            dataquality.row_signature({"question": "a", "answer": "b"}),
            dataquality.row_signature({"prompt": "a", "completion": "b"}),
        )

    def test_the_removed_rows_are_kept_rather_than_deleted(self):
        removed = self.dedupe()
        kept_rows = read_jsonl(Path(removed["deduplicated_path"]))
        dropped_rows = read_jsonl(Path(removed["removed_path"]))
        self.assertEqual(len(kept_rows), 200)
        self.assertEqual(len(dropped_rows), 17)
        self.assertEqual(
            multiset(kept_rows + dropped_rows), multiset(self.duplicated)
        )

    def test_the_written_file_is_re_read_and_reported_clean(self):
        removed = self.dedupe()
        self.assertTrue(removed["ok"], removed["summary"])
        self.assertEqual(
            removed["verification"]["exact_duplicates_in_the_written_file"], 0
        )
        independent = dataquality.profile(Path(removed["deduplicated_path"]))
        self.assertEqual(independent["duplicates"]["exact"], 0)

    def test_near_duplicates_are_not_removed_and_the_omission_is_stated(self):
        """Dropping rows on OUR threshold is deleting somebody's data on a
        judgement they never made. It is reported, not done."""
        removed = self.dedupe()
        checks = {row["check"] for row in removed["checks_not_run"]}
        self.assertIn("near_duplicates", checks)
        self.assertIn(
            str(dataquality.JACCARD_THRESHOLD),
            json.dumps(removed["checks_not_run"]),
        )

    def test_a_file_with_no_duplicates_is_refused_rather_than_copied(self):
        clean = as_csv(self.root / "clean.csv", rows_for(120, seed=3))
        destination = self.out("nothing_to_do")
        result = datawork.drop_duplicates(path=str(clean), into=str(destination))
        self.assertEqual(result["error"], "no_duplicates")
        self.assertEqual(result["exact_duplicates"], 0)
        self.assertFalse(destination.exists())


def _instrument_for_assess():
    """An instrument for a direct call to `assess_the_data`.

    `assess_the_data` takes one because it can stamp; this file calls it as a
    plain function to compare a count, so it needs one that stamps nothing. It
    is built through the same factory the registry uses, with no thread, so a
    stamp would be refused rather than silently written.
    """
    from app.tools import evidence

    return evidence.instrument_for(
        tool="assess_the_data",
        measures=(),
        actor=USER,
        thread_id=None,
        arguments={},
        bounds=(),
    )


# ---------------------------------------------------------------------------


class AFragmentDoesNotGetAFinishedFilesNameTest(WritesADatasetTest):
    """A write that stopped half way, and what is left in the directory.

    THE REPLY IS A SENTENCE IN A CONVERSATION; THE DIRECTORY IS WHAT IS STILL
    THERE TOMORROW. A carve interrupted after twenty-five rows used to leave
    `tickets.eval.jsonl` and `tickets.train.jsonl` - the exact two names a
    finished carve produces - with no manifest and nothing else in the
    directory. `check_split_leakage` over the two fragments answered "No
    overlap: none of the 7 eval rows matched any of the 18 train rows", which is
    true of the fragments and says nothing about the split that was meant. There
    was no way, from the disk, to tell a fragment from a carve.

    The failure is simulated by making the row writer raise, which is what a
    full disk does at exactly this point. `_write_failed` is the only handler
    for it and it is reached by every real cause.
    """

    def interrupted(self, after: int = 25):
        """A carve that fails on the row after `after`, and where it landed."""
        destination = self.out("stopped")
        real = datawork._line
        written = {"rows": 0}

        def stop(record):
            written["rows"] += 1
            if written["rows"] > after:
                raise OSError(28, "No space left on device")
            return real(record)

        datawork._line = stop
        try:
            return self.carve(into=str(destination)), destination
        finally:
            datawork._line = real

    def test_the_fragments_are_not_left_under_the_names_a_carve_produces(self):
        result, destination = self.interrupted()

        self.assertEqual(result["error"], "write_failed")
        self.assertFalse(result["ok"])
        left = sorted(path.name for path in destination.iterdir())
        stem = self.source.stem
        for finished in (f"{stem}.eval.jsonl", f"{stem}.train.jsonl"):
            self.assertNotIn(finished, left)
            self.assertFalse((destination / finished).exists())
        self.assertIn(f"{stem}.eval.jsonl{datawork.PARTIAL_SUFFIX}", left)
        self.assertIn(f"{stem}.train.jsonl{datawork.PARTIAL_SUFFIX}", left)

    def test_the_directory_says_what_happened_without_anybody_opening_a_file(self):
        _, destination = self.interrupted()
        manifest = json.loads(
            (destination / datawork.MANIFEST_NAME).read_text(encoding="utf-8")
        )
        self.assertIs(manifest["complete"], False)
        self.assertEqual(manifest["operation"], "write_failed")
        self.assertIn("DID NOT FINISH", manifest["this_directory_holds"])
        self.assertIn("No space left on device", manifest["failed_with"])
        self.assertEqual(manifest["written_by"]["sha"], identity.build()["sha"])

    def test_the_source_is_still_untouched_after_a_failed_write(self):
        before = support.tree_fingerprint(self.source)
        self.interrupted()
        self.assertEqual(support.tree_fingerprint(self.source), before)


# ---------------------------------------------------------------------------


class AWrittenFileIsNotAMeasurementTest(WritesADatasetTest):
    """The thing this capability must not do, and the reason it cannot.

    "I wrote 40 rows" is this program's own arithmetic. "A tool counted 40 rows
    in a file that exists" is a claim about the world, and it is the second one
    G0 reads. A carve that stamped its own row count would open the first gate
    on a file the harness wrote for the purpose.
    """

    def setUp(self) -> None:
        super().setUp()
        self.thread = support.conversations(1)[0]["id"]

    def test_neither_writing_tool_can_stamp_anything_at_all(self):
        for name in ("carve_eval_set", "drop_duplicates"):
            spec = REGISTRY.get(name)
            with self.subTest(tool=name):
                self.assertEqual(spec.measures, ())
                self.assertFalse(
                    spec.wants_instrument,
                    "the handler takes an instrument, so there is an object in "
                    "scope that could stamp",
                )

    def test_a_carve_records_no_fact_and_the_gate_stays_shut(self):
        from app.tools import evidence

        result = REGISTRY.call(
            "carve_eval_set",
            {
                "path": str(self.source),
                "answer_column": "reason",
                "into": str(self.out("split")),
            },
            approved=True,
            actor=MODEL,
            thread_id=self.thread,
        )
        self.assertTrue(result["ok"], result["summary"])
        self.assertNotIn("measured_facts", result)
        self.assertEqual(result["measured"], [])

        sheet, trail = evidence.assemble_facts(self.thread, {}, MODEL)
        self.assertEqual(
            [row for row in trail if row["fact"] == "eval_size_n"],
            [],
            "writing a file recorded a count of it",
        )
        self.assertIsNone(sheet.get("eval_size_n"))

    def test_the_reply_names_the_tool_that_would_settle_it(self):
        result = self.carve()
        self.assertIn("measure_eval_set", result["does_not_open_g0"])
        self.assertIn("eval_size_n", result["does_not_open_g0"])

    def test_counting_the_file_afterwards_is_what_measures_it(self):
        """The second claim, made by the instrument that is allowed to make it.

        This is the whole shape of the line: the harness may write the file and
        may not vouch for it, and the vouching is one more tool call that reads
        what is actually on the disk.
        """
        from app.tools import evidence

        carved = self.carve()
        counted = REGISTRY.call(
            "measure_eval_set",
            {"path": carved["eval_path"]},
            actor=MODEL,
            thread_id=self.thread,
        )
        self.assertEqual(counted["rows"], self.floor)

        _sheet, trail = evidence.assemble_facts(self.thread, {}, MODEL)
        rows = [row for row in trail if row["fact"] == "eval_size_n"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["value"], self.floor)
        self.assertEqual(rows[0]["origin"], MEASURED)


# ---------------------------------------------------------------------------


class ADiskWriteNeedsAPersonTest(WritesADatasetTest):
    """`docs/ARCHITECTURE.md` 8: a tool call the model proposes that touches the
    filesystem outside the run directory goes through the approval path
    regardless of what the model claims it was told."""

    def test_a_model_calling_it_is_refused_and_told_where_an_approval_comes_from(self):
        destination = self.out("split")
        with self.assertRaises(ApprovalRequired) as caught:
            REGISTRY.call(
                "carve_eval_set",
                {
                    "path": str(self.source),
                    "answer_column": "reason",
                    "into": str(destination),
                },
                actor=MODEL,
            )
        message = str(caught.exception)
        self.assertIn("not something a tool call can carry", message)
        self.assertIn("control", message)
        self.assertFalse(destination.exists())

    def test_both_writing_tools_declare_it(self):
        for name in ("carve_eval_set", "drop_duplicates"):
            with self.subTest(tool=name):
                self.assertEqual(REGISTRY.get(name).approval, "always")


# ---------------------------------------------------------------------------


class TheFileSaysWhoWroteItTest(WritesADatasetTest):
    """A row that loses its origin is the provenance rule broken in a new
    medium. The rows are verbatim, so the manifest is what carries it."""

    def manifest(self, result) -> dict:
        return json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))

    def test_it_names_the_product_and_the_code_that_wrote_it(self):
        manifest = self.manifest(self.carve())
        build = identity.build()
        self.assertEqual(manifest["written_by"]["product"], "ml-harness")
        self.assertEqual(
            manifest["written_by"]["code_fingerprint"], build["code_fingerprint"]
        )
        self.assertEqual(manifest["written_by"]["sha"], build["sha"])
        self.assertEqual(manifest["operation"], "carve_eval_set")

    def test_it_names_the_source_by_its_bytes_and_not_only_by_its_path(self):
        import hashlib

        manifest = self.manifest(self.carve())
        raw = self.source.read_bytes()
        self.assertEqual(manifest["source"]["path"], str(self.source))
        self.assertEqual(manifest["source"]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(manifest["source"]["bytes"], len(raw))
        self.assertEqual(manifest["source"]["rows_read"], self.ROWS)

    def test_every_file_it_wrote_is_listed_with_its_digest(self):
        import hashlib

        result = self.carve()
        manifest = self.manifest(result)
        self.assertEqual({row["file"] for row in manifest["wrote"]}, {
            Path(result["eval_path"]).name,
            Path(result["train_path"]).name,
        })
        for row in manifest["wrote"]:
            with self.subTest(file=row["file"]):
                raw = Path(row["path"]).read_bytes()
                self.assertEqual(row["sha256"], hashlib.sha256(raw).hexdigest())
                self.assertEqual(row["bytes"], len(raw))
                self.assertEqual(row["rows"], len(read_jsonl(Path(row["path"]))))

    def test_the_eval_rows_carry_their_position_in_the_source(self):
        """One list rather than two: the training file is the complement."""
        result = self.carve()
        manifest = self.manifest(result)
        positions = manifest["eval_source_rows"]
        self.assertEqual(len(positions), result["eval_rows"])
        self.assertEqual(len(set(positions)), len(positions))
        carved = read_jsonl(Path(result["eval_path"]))
        for offset, position in enumerate(positions):
            with self.subTest(position=position):
                self.assertEqual(carved[offset], self.rows[position - 1])

    def test_the_output_is_named_after_the_input(self):
        result = self.carve()
        self.assertTrue(Path(result["eval_path"]).name.startswith("tickets."))
        self.assertTrue(Path(result["train_path"]).name.startswith("tickets."))

    def test_the_manifest_says_it_is_not_evidence_of_anything(self):
        manifest = self.manifest(self.carve())
        self.assertIn("measure_eval_set", manifest["this_file_is"])
        self.assertIn("this program's own arithmetic", manifest["this_file_is"])

    def test_the_rows_themselves_are_not_edited(self):
        """The obvious way to keep provenance in the medium, and the reason it
        is refused: a per-row `split` mark makes every eval row differ from
        every train row, and `check_split_leakage` compares rows as text - so
        the verification would come back clean on any input at all."""
        result = self.carve()
        for row in read_jsonl(Path(result["eval_path"])):
            with self.subTest(row=str(row)[:40]):
                self.assertEqual(set(row), {"ticket", "reason"})
                self.assertIn(row, self.rows)


# ---------------------------------------------------------------------------


class TheWritingHalfIsExactlyOneModuleTest(unittest.TestCase):
    """Where a write may live, asserted against the registry.

    `app/tools/data.py` is the reading half and its docstring is a contract.
    Keeping the writing in a sibling is only worth anything if it is a property
    rather than a habit, so this derives both halves from the registry: no tool
    declared in the reader may write a file, and every tool that writes one is
    declared in the writer.
    """

    READER = "app.tools.data"
    WRITER = "app.tools.datawork"

    def setUp(self) -> None:
        self.root = support.sandbox(self)

    def test_no_tool_in_the_reading_half_writes_anything_to_disk(self):
        for spec in REGISTRY:
            if spec.handler.__module__ != self.READER:
                continue
            with self.subTest(tool=spec.name):
                self.assertNotIn("filesystem", spec.writes)
                self.assertNotIn("datasets", spec.writes)

    def test_every_tool_that_writes_a_dataset_is_in_the_writing_half(self):
        writing = [
            spec.name
            for spec in REGISTRY
            if "datasets" in spec.writes
        ]
        self.assertEqual(
            sorted(writing),
            [
                "carve_eval_set",
                # 2026-08-31: data COLLECTION - raw md/css/html into verbatim
                # tagged rows. Extractors are a library (app/tools/quarry);
                # the registered door lives in datawork with every writer.
                "carve_rows",
                # 2026-08-27: the 10% somebody has to read before anything
                # trains on generated rows. It writes a file - the rows drawn
                # for review - so it belongs in the writing half by the same
                # rule everything else here does.
                "draw_verification_sample",
                "drop_duplicates",
                # 2026-09-12: the invent-a-dataset pair. A connected model
                # writes rows for a task; a judge scores them and writes the
                # kept rows and the chosen/rejected pairs. Both write DATASETS
                # and both go through the writer's own doors - see
                # `test_a_writer_outside_the_module_uses_the_modules_doors`.
                "generate_rows",
                # 2026-09-18: chain-first tool-use rows, app.tools.chainfirst,
                # a third writing module through the same three doors.
                "generate_tool_rows",
                "judge_rows",
                # `record_verification` writes too, and writes a JSON record
                # rather than a DATASET, which is why it is not in this list:
                # `writes=("filesystem",)` and not `("datasets",)`. The
                # distinction is the one this class is about.
                "synthesize_rows",
            ],
        )
        for name in writing:
            with self.subTest(tool=name):
                self.assertIn(REGISTRY.get(name).handler.__module__, self.WRITERS)

    #: THE WRITING HALF GREW A SECOND MODULE ON 2026-09-12, and the property
    #: this class is about did not change: a write lives where the claim, the
    #: manifest and the refusal live. `app/tools/invent.py` holds the two
    #: tools that have a MODEL write rows - a different enough thing from
    #: reading the person's files to be its own file with its own argument -
    #: and it reaches every door through `datawork`, which the test below
    #: asserts rather than trusts.
    WRITERS = ("app.tools.datawork", "app.tools.invent", "app.tools.chainfirst")

    def test_a_writer_outside_the_module_uses_the_modules_doors(self):
        """A second writing module is allowed one way: through the first's
        `_claim` (nothing written over), `_write_manifest` (every write says
        what it is) and `Refusal` (a refusal is a payload, not a crash)."""
        import inspect

        for spec in REGISTRY:
            module = spec.handler.__module__
            if module in (self.READER, self.WRITER) or "datasets" not in spec.writes:
                continue
            with self.subTest(tool=spec.name, module=module):
                self.assertIn(module, self.WRITERS)
                source = inspect.getsource(sys.modules[module])
                for door in ("datawork._claim(", "datawork._write_manifest(", "datawork.Refusal"):
                    self.assertIn(door, source, f"{module} writes a dataset without {door}")

    def test_the_data_group_now_contains_a_tool_that_writes_a_file(self):
        """The gap, stated as the count that made it visible: fourteen tools in
        the Data group and not one that wrote a file.

        THE FOURTEEN WAS A DATE AND NOT A PROPERTY, and it is written down as
        one now. It was the size of the reading half of the Data group on the
        day `carve_eval_set` landed, and asserting it as an equality made every
        later READER fail a test about where WRITES live, for the sole reason
        that it reads. `fit_a_tree_model` was the first to hit it: it fits a
        gradient-boosted tree, declares `writes=()`, creates no file, and is
        exactly the kind of tool this boundary is meant to be indifferent to.

        So the equality moves to the half this file is actually about - the
        writers, named, which is the assertion that goes red if a third write
        appears or one of these two moves out of `datawork` - and the reader
        count becomes the FLOOR it always was. A reader is never removed by
        adding a writer, so `>= 14` still catches the regression the fourteen
        was there to catch, and stops catching the arrival of a reader, which
        it was never meant to.
        """
        group = [spec for spec in REGISTRY if spec.control.group == "Data"]
        writing = [spec for spec in group if "datasets" in spec.writes]
        self.assertEqual(
            sorted(spec.name for spec in writing),
            [
                "carve_eval_set",
                # 2026-08-31: data COLLECTION - raw md/css/html into verbatim
                # tagged rows. Extractors are a library (app/tools/quarry);
                # the registered door lives in datawork with every writer.
                "carve_rows",
                "draw_verification_sample",
                "drop_duplicates",
                # 2026-09-12: the invent-a-dataset pair, Data group, writers.
                "generate_rows",
                # 2026-09-18: chain-first tool-use rows, Data group, writer.
                "generate_tool_rows",
                "judge_rows",
                "synthesize_rows",
            ],
            "the writing half of the Data group is not the tools this file is "
            "about",
        )
        self.assertGreaterEqual(
            len(group) - len(writing),
            14,
            "the Data group held fourteen readers on the day the writing half "
            "was added, and adding a writer does not remove one",
        )

    def test_the_dead_end_now_names_the_tool_that_writes_the_file(self):
        """`assess_the_data` part five used to end "Nothing has been carved and
        no file has been written" with nothing named that would write one."""
        source = as_csv(self.root / "tickets.csv", rows_for(200))
        assessed = data.assess_the_data(
            path=str(source),
            label_column="reason",
            instrument=_instrument_for_assess(),
        )
        part = assessed["answer"][4]
        self.assertTrue(part["can_be_carved"])
        self.assertEqual(part["what_would_carve_it"]["tool"], "carve_eval_set")
        self.assertIn("carve_eval_set", part["answer"])
        self.assertIn("measure_eval_set", part["what_would_carve_it"]["and_then"])
        self.assertIn("carve_eval_set", REGISTRY.names())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
