"""Counting the priceable runs must not require knowing where they sit.

Three readers counted this tree tonight and got 0, 5 and 33. The 0 came from
`runs/*/job.json`, and the records live at `runs/<id>/sandboxes/<name>/runs/
run_N/job.json` - four levels deeper than the obvious glob. **If a reader has to
know the directory layout to count the runs, the layout is the record and the
record is decoration.**

The other two are the same tree under two definitions of priceable, which is why
`what_the_runs_cost.py` prints a LADDER rather than a total: base+peak, then
training peaks only, then those recording sequence and batch, then those
recording checkpointing. A disagreement then lands on a rung.
"""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import support

report = support.import_file(
    "what_the_runs_cost", support.REPO_ROOT / "scripts" / "what_the_runs_cost.py"
)


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = report.main(argv)
    return code, out.getvalue() + err.getvalue()


class ARunIsFoundWhereverItSitsTest(unittest.TestCase):
    """The depth that produced a zero."""

    def setUp(self):
        self.root = Path(support.sandbox(self))

    def a_run_at(self, *parts):
        where = self.root.joinpath(*parts)
        where.mkdir(parents=True)
        (where / "job.json").write_text(
            json.dumps(
                {
                    "kind": "train",
                    "recipe": "hf-peft-lora",
                    "config": {
                        "base_model": "org/SmolLM2-135M",
                        "max_seq_len": 512,
                        "batch_size": 1,
                        "grad_checkpointing": True,
                    },
                }
            ),
            encoding="utf-8",
        )
        (where / "job.log").write_text(
            'MLH_EVENT {"kind": "finished", "peak_vram_gb": 0.63}' + chr(10),
            encoding="utf-8",
        )
        return where

    def test_a_run_four_levels_down_is_counted(self):
        """THE CASE. `runs/*/job.json` finds this one nowhere."""
        self.a_run_at("an-id", "sandboxes", "journey", "runs", "run_1")
        code, said = run(["--root", str(self.root)])
        self.assertEqual(code, report.EVERY)
        self.assertIn("SmolLM2-135M", said)
        self.assertIn("1 run record(s)", said)

    def test_the_shallow_glob_really_does_miss_it(self):
        """Asserted so the premise of this file is measured and not recalled."""
        self.a_run_at("an-id", "sandboxes", "journey", "runs", "run_1")
        self.assertEqual(list(self.root.glob("*/job.json")), [])

    def test_a_tree_with_no_records_says_so_rather_than_printing_nothing(self):
        code, said = run(["--root", str(self.root / "empty")])
        self.assertEqual(code, report.NOTHING_TO_READ)
        self.assertIn("no run records", said)


class TheLadderIsPrintedRatherThanATotalTest(unittest.TestCase):
    """Every rung three readers stood on, in one output."""

    def setUp(self):
        self.root = Path(support.sandbox(self))
        self.make("full", seq=512, batch=1, ckpt=True, kind="train", event="finished")
        self.make("no_ckpt", seq=512, batch=1, ckpt=None, kind="train", event="finished")
        self.make("no_geom", seq=None, batch=None, ckpt=None, kind="train", event="finished")
        self.make("an_eval", seq=None, batch=None, ckpt=None, kind="eval",
                  event="eval_finished")

    def make(self, name, *, seq, batch, ckpt, kind, event):
        where = self.root / name / "job_1"
        where.mkdir(parents=True)
        config = {"base_model": "org/SmolLM2-135M"}
        if seq is not None:
            config["max_seq_len"] = seq
        if batch is not None:
            config["batch_size"] = batch
        if ckpt is not None:
            config["grad_checkpointing"] = ckpt
        (where / "job.json").write_text(
            json.dumps({"kind": kind, "recipe": "r", "config": config}), encoding="utf-8"
        )
        (where / "job.log").write_text(
            'MLH_EVENT {"kind": "' + event + '", "peak_vram_gb": 0.63}' + chr(10),
            encoding="utf-8",
        )

    def test_each_rung_is_reported_and_they_descend(self):
        _code, said = run(["--root", str(self.root)])
        self.assertIn("base + peak                       : 4", said)
        self.assertIn("TRAINING peaks      : 3", said)
        self.assertIn("with sequence and batch    : 2", said)
        self.assertIn("and checkpointing        : 1", said)

    def test_the_eval_run_is_excluded_from_the_training_rung(self):
        """The distinction that cost three lanes an hour: an eval peak is a
        measurement of a different quantity, so it must not be counted as a
        training configuration."""
        _code, said = run(["--root", str(self.root)])
        self.assertIn("the rest measure inference", said)

    def test_a_default_is_shown_as_an_assumption_and_not_a_value(self):
        """`(true?)` is the recipe's default showing through. Printing it as
        `true` would make an assumption indistinguishable from a record.

        ASSERTED ON THE ROW, NOT THE OUTPUT, and the first version was not.
        It read `assertIn("(true?)", said)` over everything printed - and the
        footer explaining the convention CONTAINS that string, so the test
        passed on its own explanatory text while the rows said plain `true`.
        Found by mutation: replacing the marker with the bare value turned
        nothing red.
        """
        _code, said = run(["--root", str(self.root)])
        rows = [line for line in said.splitlines() if "job_1" in line]
        self.assertTrue(rows, "no rows were printed at all")
        unrecorded = [line for line in rows if "no_ckpt" in line or "no_geom" in line]
        self.assertTrue(unrecorded)
        for line in unrecorded:
            self.assertIn("(true?)", line)
        recorded = [line for line in rows if "full" in line]
        self.assertTrue(recorded)
        for line in recorded:
            self.assertNotIn("(true?)", line)

    def test_a_configuration_with_no_geometry_is_labelled(self):
        _code, said = run(["--root", str(self.root)])
        self.assertIn("geometry unrecorded", said)


class TheFiltersSelectWhatTheyNameTest(unittest.TestCase):
    """Two flags, and each has a case that shows only what it claims."""

    def setUp(self):
        self.root = Path(support.sandbox(self))
        TheLadderIsPrintedRatherThanATotalTest.make(
            self, "full", seq=512, batch=1, ckpt=True, kind="train", event="finished"
        )
        TheLadderIsPrintedRatherThanATotalTest.make(
            self, "short", seq=None, batch=None, ckpt=None, kind="train",
            event="finished",
        )

    def test_priceable_shows_the_complete_one_only(self):
        _code, said = run(["--root", str(self.root), "--priceable"])
        rows = [line for line in said.splitlines() if "job_1" in line]
        self.assertEqual(len(rows), 1)
        self.assertIn("full", rows[0])

    def test_missing_shows_the_incomplete_one_only(self):
        _code, said = run(["--root", str(self.root), "--missing"])
        rows = [line for line in said.splitlines() if "job_1" in line]
        self.assertEqual(len(rows), 1)
        self.assertIn("short", rows[0])


if __name__ == "__main__":
    unittest.main()
