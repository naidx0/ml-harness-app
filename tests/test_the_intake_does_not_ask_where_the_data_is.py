"""The intake stops asking for a path to data the harness is sitting on.

## The complaint, in the user's own words

2026-09-10, walking the intake with a model attached, at the diagnosis step:

    "Looking through all of these routes that you stopped on, they all stop at
     this diagnosis ... it says, how much of this data is usable? A tool has to
     run and asks for a path where the data is sitting. I have no idea ...
     ml_harness.db could be it, test scripts, I'm not really sure."

That is the complaint this lane exists for - *"it throws tools in your face"* -
arriving inside the tool that was meant to answer it. `assess_the_data`
required `path`, so the intake's only move was to hand the question back.

## What changed, and what deliberately did not

**No path is no longer an error.** It is the commonest true state of somebody
who has data and does not know what this tool calls it, and the harness can
look: every `.jsonl` and `.csv` under `evals/` and `runs/`, with the rows it
counted.

**Nothing is stamped by looking.** `labeled_examples_n` and `classes_n` still
require a named `label_column` on a named file, for every reason the tool's own
docstring gives. An offer is a list of file names and row counts; it is not an
assessment, and it says so in `nothing_is_recorded_yet` rather than leaving a
reader to infer it.

**A row count that could not be taken is `None`, never `0`.** An offer saying
"0 rows" about a file it failed to open would be worse than one admitting it
does not know - the same rule the rest of this repository applies to every
measurement.

## And the offer is capped, which is the other half of the same complaint

The first version listed all ninety-four files in this checkout. Ninety-four
names is not an offer, it is the same refusal wearing a list. Eight, ranked
training-shaped first and then by size, with a count of what was held back.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import support

from app.tools import REGISTRY, data


def a_dataset(path: Path, rows: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for i in range(rows):
            handle.write(json.dumps({"prompt": f"q{i}", "completion": "a"}) + "\n")
    return path


class ItLooksInsteadOfAskingTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(support.sandbox(self))
        a_dataset(self.root / "evals" / "train.jsonl", 40)
        a_dataset(self.root / "runs" / "one" / "held-out.jsonl", 12)

    def test_it_finds_what_is_under_evals_and_runs(self):
        found = data.datasets_already_here(self.root)
        self.assertEqual(
            {"evals/train.jsonl", "runs/one/held-out.jsonl"},
            {row["shown_as"] for row in found},
        )

    def test_it_counts_the_rows_it_offers(self):
        found = {r["shown_as"]: r["rows"] for r in data.datasets_already_here(self.root)}
        self.assertEqual(40, found["evals/train.jsonl"])
        self.assertEqual(12, found["runs/one/held-out.jsonl"])

    def test_a_directory_wearing_a_dataset_name_is_not_offered(self):
        broken = self.root / "evals" / "unreadable.jsonl"
        broken.mkdir()
        found = {r["shown_as"]: r for r in data.datasets_already_here(self.root)}
        self.assertNotIn("evals/unreadable.jsonl", found)

    def test_a_count_it_could_not_take_is_none_and_not_zero(self):
        """THE RULE THIS REPOSITORY APPLIES EVERYWHERE ELSE, and the case above
        does not exercise it: a directory is filtered out before anything tries
        to count it, so `_rows_in` is never reached. Mutation found that -
        returning 0 from the failure path left the suite green.

        "0 rows" about a file nobody could open is a measurement that was never
        made, reported as one that was.
        """
        unopenable = self.root / "evals" / "a-directory"
        unopenable.mkdir(exist_ok=True)
        self.assertIsNone(data._rows_in(unopenable))

    def test_build_spoil_is_not_offered_as_data(self):
        a_dataset(self.root / "evals" / "__pycache__" / "junk.jsonl", 3)
        self.assertNotIn(
            "evals/__pycache__/junk.jsonl",
            {row["shown_as"] for row in data.datasets_already_here(self.root)},
        )

    def test_a_database_is_not_a_dataset(self):
        """`ml_harness.db` is the file the user guessed at, and it is not one.
        Offering it would answer the complaint with a wrong answer."""
        (self.root / "evals" / "ml_harness.db").write_bytes(b"SQLite format 3\x00")
        self.assertEqual([], [
            row for row in data.datasets_already_here(self.root)
            if row["shown_as"].endswith(".db")
        ])


class TheOfferIsShortEnoughToReadTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(support.sandbox(self))
        #: THE BIG FILES ARE THE ONES THAT ARE NOT TRAINING-SHAPED, so size
        #: alone cannot put `train.jsonl` first. The first version of this made
        #: the training file the largest too, and mutation showed the ranking
        #: could be deleted without the test noticing.
        for i in range(20):
            a_dataset(self.root / "evals" / f"held-out-{i:02d}.jsonl", 900)
        a_dataset(self.root / "evals" / "train.jsonl", 5)

    def test_it_offers_no_more_than_a_screenful(self):
        """NINETY-FOUR NAMES IS NOT AN OFFER. The first version of this listed
        every file in the checkout, which is the same refusal wearing a list."""
        ranked = sorted(data.datasets_already_here(self.root), key=data._worth_offering)
        self.assertGreater(len(ranked), data.HOW_MANY_TO_OFFER)
        self.assertLessEqual(data.HOW_MANY_TO_OFFER, 10)

    def test_the_training_shaped_file_is_offered_first(self):
        """A person who cannot name their data is not looking for
        `held-out-07.jsonl`."""
        ranked = sorted(data.datasets_already_here(self.root), key=data._worth_offering)
        self.assertEqual("evals/train.jsonl", ranked[0]["shown_as"])


class NothingIsStampedByLookingTest(unittest.TestCase):
    """The separation the tool's own docstring defends, kept across the change."""

    def setUp(self):
        support.sandbox(self)

    def test_an_empty_path_records_no_fact_and_says_so(self):
        out = REGISTRY.call("assess_the_data", {}, actor="user")
        self.assertIn("nothing_is_recorded_yet", out)
        self.assertIn("not an assessment", out["nothing_is_recorded_yet"])

    def test_an_empty_path_is_not_an_error(self):
        """It was one. That is the whole change: a person who does not know
        the path is not making a mistake."""
        out = REGISTRY.call("assess_the_data", {}, actor="user")
        self.assertIsNone(out.get("error"))

    def test_the_tool_no_longer_demands_a_path(self):
        spec = REGISTRY.get("assess_the_data")
        self.assertNotIn("path", spec.schema.get("required") or [])

    def test_a_named_file_still_has_to_name_its_label_column(self):
        """THE CONTROL. Looking got easier; the stamp did not. A count under a
        guessed column is a judgement wearing a number."""
        root = Path(support.sandbox(self))
        path = a_dataset(root / "train.jsonl", 30)
        out = REGISTRY.call("assess_the_data", {"path": str(path)}, actor="user")
        self.assertEqual([], out.get("recorded") or [])


class APickedRowIsTheCallTest(unittest.TestCase):
    """A list somebody has to retype is the same demand in a friendlier voice.

    Listing the datasets answered *"where is the data"*. It does not answer
    *"and now what do I type"* - and a person who has to copy
    `evals/architecture-json/train.jsonl` out of a list and spell it back has
    been handed a tool again, just a politer one. So the row IS the call: the
    path travels from what the harness measured to what the tool receives
    without passing through anybody's keyboard.
    """

    def setUp(self):
        self.root = Path(support.sandbox(self))
        a_dataset(self.root / "evals" / "train.jsonl", 40)

    def offer(self):
        return REGISTRY.call("assess_the_data", {}, actor="user")

    def test_every_offered_row_carries_the_tool_and_its_arguments(self):
        for row in self.offer()["found"]:
            with self.subTest(row=row["shown_as"]):
                self.assertEqual("assess_the_data", row["run_this"]["tool"])
                self.assertEqual(row["path"], row["run_this"]["arguments"]["path"])

    def test_a_picked_row_runs_as_it_stands(self):
        """THE CASE. Nothing is composed, nothing is edited, nothing is typed."""
        row = self.offer()["found"][0]
        out = REGISTRY.call(
            row["run_this"]["tool"], row["run_this"]["arguments"], actor="user"
        )
        self.assertTrue(out.get("ok"), out.get("summary"))
        self.assertIsNone(out.get("error"))
        self.assertEqual(row["rows"], out.get("rows"))

    def test_picking_a_row_reaches_what_typing_the_path_reaches(self):
        """THE EQUIVALENCE, stated as one: a picked row is not a second route
        with its own behaviour, it is the same call with the typing removed."""
        row = self.offer()["found"][0]
        picked = REGISTRY.call(
            row["run_this"]["tool"], row["run_this"]["arguments"], actor="user"
        )
        typed = REGISTRY.call(
            "assess_the_data", {"path": row["path"]}, actor="user"
        )
        for key in ("ok", "error", "rows", "path"):
            with self.subTest(key=key):
                self.assertEqual(typed.get(key), picked.get(key))

    def test_the_diagnosis_after_a_picked_row_is_the_diagnosis_after_a_typed_one(self):
        """AND THE WALK DOES NOT NOTICE. If picking changed where a thread
        ended up, the offer would be a second product rather than a shortcut
        through the first one."""
        from app import events
        from app.tools import evidence

        def walk_after(arguments):
            thread = int(events.create_thread("picked or typed", None)["id"])
            REGISTRY.call(
                "assess_the_data", arguments,
                actor=evidence.USER, thread_id=thread,
            )
            return REGISTRY.call(
                "run_diagnosis", {"facts": {}},
                actor=evidence.USER, thread_id=thread,
            ).get("outcome")

        row = self.offer()["found"][0]
        self.assertEqual(
            walk_after({"path": row["path"]}),
            walk_after(row["run_this"]["arguments"]),
        )

    def test_the_answer_says_the_rows_are_runnable(self):
        """An affordance nobody is told about is one nobody uses."""
        self.assertIn("nothing to type", self.offer()["how_to_pick_one"])


class WhenThereIsNothingToOfferTest(unittest.TestCase):
    def test_it_says_so_and_says_what_would_not_help(self):
        """The user guessed at a database and a directory of scripts. The
        refusal names both rather than repeating the question."""
        support.sandbox(self)
        out = REGISTRY.call("assess_the_data", {}, actor="user")
        if out.get("found"):
            self.skipTest("this sandbox has datasets in it")
        self.assertEqual("no_path_and_nothing_here", out["error"])
        self.assertIn("database", out["summary"])


if __name__ == "__main__":
    unittest.main()
