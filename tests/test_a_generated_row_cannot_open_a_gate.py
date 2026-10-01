"""Synthetic rows can never open a gate, and the rule lives where the stamp is.

`docs/VISION.md` states it as one of the four rules data synthesis is allowed
under. `docs/PHASES.md` Phase 2 lists it as the first thing still owed after
`synthesize_rows` landed. Until 2026-08-27 it was enforced at the WRITER, and
`synthesize_rows`' own docstring said exactly what that left open:

    "nothing here checks whether a later call points measure_eval_set at it -
     that gate still reads the file that exists"

**The writer is the end that cannot enforce this.** It tags every row, declares
`measures=()`, and writes a manifest saying the file is synthetic - and then the
next turn points `measure_eval_set` at the file it just made, `eval_size_n` is
stamped MEASURED off a thousand sampled rows, G0 opens, `measure_baseline`
scores a model against invented rows, G1 opens, and every number after that is a
statement about a distribution this product made up wearing a measurement badge.
Nothing in three thousand tests asked the question, because every test that
existed pointed the counter at a real file.

So the check is at the stamp - `Instrument.measured(from_file=...)`, wall 8 -
and this file drives it three ways:

1. **The wall itself**, on the instrument, which is what cannot be bypassed.
2. **The tools**, which ask the same question early enough that a refusal costs
   nobody a model call, and report it as a refusal rather than raising.
3. **The whole path**, end to end: amplify a real file, point the counter at
   what came out, and watch G0 stay shut.

And one structural sweep, because the wall is only a wall where it is called:
every `instrument.measured(...)` in `app/` either names the file it read or is
one of a small, listed set that reads no file at all.
"""

import ast
import json
import pathlib
import tempfile
import unittest

from app import dataquality, diagnosis
from app.tools import datawork, evidence
from app.tools.registry import REGISTRY
import support

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Stamps taken from something that is not a file on this machine, listed by
#: the file and the fact - `None` where the fact is a loop variable rather than
#: a literal. Each one carries what it read instead, because "it does not read a
#: file" is a claim about a tool and claims about tools belong where a reviewer
#: will see them rather than in a commit message nobody re-reads.
NO_FILE_TO_NAME = {
    # inspect_hardware reads this machine: /proc, nvidia-smi, shutil.disk_usage.
    # The first entry's fact is `field`, the loop variable over the three
    # numbers, so it is listed as None.
    ("app/tools/__init__.py", None): "inspect_hardware reads the machine",
    ("app/tools/__init__.py", "accelerator"): "read from the GPU name, not a file",
    # `record_that_this_card_refuses` stamps a closure it COMPUTED - this card's
    # VRAM against the model's geometry - so there is no file it was read from
    # and `from_file=` would have to name one that does not exist. The same
    # argument as `inspect_hardware` above, and wall 8 has nothing to do here
    # for the same reason: no row of anybody's data reached these numbers.
    ("app/tools/feasible.py", "cannot_train_here"): "computed against this card, not read from a file",
    ("app/tools/feasible.py", "training_headroom_gb"): "computed against this card, not read from a file",
    ("app/tools/feasible.py", "longest_fitting_seq"): "computed against this card, not read from a file",
}


def _rows(path, rows):
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    return str(path)


def _real(n=40):
    return [{"input": f"question {i}", "expected": "yes" if i % 2 else "no"} for i in range(n)]


def _generated(n=40):
    return [
        {
            "input": f"question {i % 3}",
            "expected": "yes",
            "synthetic": True,
            "synthetic_source_index": i % 3,
            "synthetic_seed": "s",
        }
        for i in range(n)
    ]


class TheCensusReadsWhatIsThereTest(unittest.TestCase):
    """The reading the wall is built on, before anything is built on it."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())

    def test_a_real_file_is_clean_and_says_it_was_not_tagged(self):
        census = dataquality.synthetic_census(_rows(self.tmp / "real.jsonl", _real(5)))
        self.assertTrue(census["ok"])
        self.assertIs(census["clean"], True)
        self.assertFalse(census["tagged"])
        self.assertEqual(0, census["synthetic"])
        self.assertEqual(5, census["rows"])

    def test_one_generated_row_among_real_ones_is_found(self):
        census = dataquality.synthetic_census(
            _rows(self.tmp / "mixed.jsonl", _real(9) + _generated(1))
        )
        self.assertIs(census["clean"], False)
        self.assertEqual(1, census["synthetic"])
        self.assertEqual(9, census["real"])

    def test_the_tag_survives_a_round_trip_through_a_spreadsheet(self):
        """`synthetic: true` in JSONL is the string "True" after a save-as, and
        a check that only accepted the boolean would stop being a check at the
        first spreadsheet. The negative spellings are read too, so a file whose
        author wrote `synthetic: false` is not refused for having thought about
        the question."""
        for written, expected in (
            (True, True),
            ("True", True),
            ("true", True),
            (1, True),
            ("yes", True),
            (False, False),
            ("False", False),
            ("false", False),
            ("no", False),
            ("", False),
            (0, False),
            (None, False),
        ):
            with self.subTest(written=written):
                self.assertEqual(
                    expected, dataquality.is_synthetic_row({"synthetic": written})
                )
        self.assertFalse(dataquality.is_synthetic_row({"input": "x"}))


class TheWallIsOnTheStampTest(unittest.TestCase):
    """Wall 8, driven on the instrument itself - the part nothing can route
    around, because every MEASURED row in this product goes through it."""

    THREAD = 1

    def setUp(self):
        support.sandbox(self)
        support.a_conversation(self.THREAD)
        self.tmp = pathlib.Path(tempfile.mkdtemp())

    def _instrument(self):
        # `eval_size_n` is thread-scoped, so the instrument carries a real
        # conversation: wall 5 refuses the row otherwise, and a test that
        # tripped THAT wall would tell us nothing about this one.
        return evidence.Instrument(
            tool="measure_eval_set",
            actor=evidence.USER,
            thread_id=self.THREAD,
            measures=frozenset({"eval_size_n"}),
            # And its capability, because wall 9 asks what KIND of tool this is
            # and the ledger binds `eval_size_n` to the two that count rows. A
            # fixture that left this empty would trip that wall instead of this
            # one, which is the same mistake the comment above avoids for
            # wall 5.
            provides=frozenset({"data.eval_set.count"}),
        )

    def test_a_clean_file_stamps(self):
        path = _rows(self.tmp / "real.jsonl", _real(40))
        row = self._instrument().measured(
            "eval_size_n", 40, how="counted 40 rows", from_file=path
        )
        self.assertEqual(diagnosis.MEASURED, row["origin"])

    def test_a_generated_file_is_refused_and_the_refusal_says_what_to_do(self):
        path = _rows(self.tmp / "synth.jsonl", _generated(40))
        with self.assertRaises(evidence.GeneratedRowsError) as caught:
            self._instrument().measured(
                "eval_size_n", 40, how="counted 40 rows", from_file=path
            )
        said = str(caught.exception)
        self.assertIn("40 generated rows", said)
        self.assertIn("can never open a gate", said)
        # The remedy, not just the refusal.
        self.assertIn("file of their own", said)

    def test_one_generated_row_is_enough(self):
        """Not a proportion and not a threshold. A gate is a claim that a number
        means something, and 39 real rows plus one invented one is a file nobody
        can say that about."""
        path = _rows(self.tmp / "one.jsonl", _real(39) + _generated(1))
        with self.assertRaises(evidence.GeneratedRowsError):
            self._instrument().measured(
                "eval_size_n", 40, how="counted 40 rows", from_file=path
            )

    def test_it_is_a_measurement_error_so_everything_that_already_catches_keeps_working(self):
        self.assertTrue(issubclass(evidence.GeneratedRowsError, evidence.MeasurementError))

    def test_a_stamp_that_names_no_file_is_not_asked_about_one(self):
        """Hardware is read off this machine. A wall that demanded a file from
        every stamp would have made `inspect_hardware` impossible."""
        instrument = evidence.Instrument(
            tool="inspect_hardware",
            actor=evidence.USER,
            measures=frozenset({"ram_gb"}),
            provides=frozenset({"machine.hardware.inspect"}),
        )
        row = instrument.measured("ram_gb", 15.7, how="read from /proc/meminfo")
        self.assertEqual(diagnosis.MEASURED, row["origin"])


class TheToolsRefuseBeforeItCostsAnythingTest(unittest.TestCase):
    THREAD = 1

    def setUp(self):
        support.sandbox(self)
        support.a_conversation(self.THREAD)
        self.tmp = pathlib.Path(tempfile.mkdtemp())

    def test_measure_eval_set_counts_it_and_records_nothing(self):
        """Both halves matter. The count is real and is reported - hiding it
        would be its own dishonesty - and `eval_size_n` is not stamped."""
        path = _rows(self.tmp / "synth.jsonl", _generated(40))
        result = REGISTRY.call(
            "measure_eval_set", {"path": path}, actor="user", thread_id=self.THREAD
        )
        self.assertFalse(result["ok"])
        self.assertEqual(40, result["rows"])
        self.assertIn("generated", result["summary"])
        self.assertIn("not_measured", result)
        self.assertNotIn(
            "eval_size_n is now measured",
            result["summary"],
            "the summary of a refused stamp must not read like a stamp",
        )

    def test_measure_eval_set_on_a_real_file_still_works(self):
        """The negative beside the positive: this wall must not have made the
        honest path harder, and a test that only proves the refusal cannot say
        so."""
        path = _rows(self.tmp / "real.jsonl", _real(40))
        result = REGISTRY.call(
            "measure_eval_set", {"path": path}, actor="user", thread_id=self.THREAD
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(40, result["rows"])
        self.assertIn("eval_size_n is now", result["summary"])


class TheWholePathTest(unittest.TestCase):
    """Amplify a real file the way a person would, then point the counter at
    what came out. This is the sequence that was open, driven end to end."""

    THREAD = 1

    def setUp(self):
        support.sandbox(self)
        support.a_conversation(self.THREAD)
        self.tmp = pathlib.Path(tempfile.mkdtemp())

    def test_amplify_then_count_leaves_g0_shut(self):
        source = pathlib.Path(_rows(self.tmp / "source.jsonl", _real(12)))
        into = self.tmp / "amplified"

        written = datawork.synthesize_rows(
            path=str(source),
            answer_column="expected",
            into=str(into),
            count=200,
            seed="phase-2",
            ledger=diagnosis.default_spec(),
        )
        self.assertTrue(written["ok"], written)
        self.assertEqual(200, written["rows_written"])

        # 200 rows is comfortably over G0's floor of 30, which is exactly why
        # this was worth being able to do by accident.
        counted = REGISTRY.call(
            "measure_eval_set",
            {"path": written["synthetic_path"]},
            actor="user",
            thread_id=self.THREAD,
        )
        self.assertEqual(200, counted["rows"])
        self.assertFalse(counted["ok"])

        # And the gate, asked directly: nothing was stamped, so the ledger has
        # no eval_size_n and G0 cannot open on anything.
        verdict = REGISTRY.call(
            "run_diagnosis",
            {"facts": {"goal_text": "classify tickets", "modality": "text"}},
            actor="model",
            thread_id=self.THREAD,
        )
        gates = verdict.get("gate_ledger") or {}
        self.assertNotEqual(
            "PASSED",
            (gates.get("G0_EVAL_SET") or {}).get("status")
            if isinstance(gates.get("G0_EVAL_SET"), dict)
            else gates.get("G0_EVAL_SET"),
            "G0 opened after a run whose only counted file was generated",
        )

    def test_the_real_source_file_is_still_countable(self):
        """The rows that were amplified FROM are real, and the remedy the
        refusal names has to actually work."""
        source = pathlib.Path(_rows(self.tmp / "source.jsonl", _real(40)))
        counted = REGISTRY.call(
            "measure_eval_set", {"path": str(source)}, actor="user", thread_id=self.THREAD
        )
        self.assertTrue(counted["ok"], counted)


class EveryStampNamesItsFileTest(unittest.TestCase):
    """The sweep, because a wall is only a wall where it is called.

    This is the lesson `docs/PHASES.md` records as *"a bound that only ever
    pushes in one direction cannot see the failure in the other"*, applied
    before the fact rather than after it: the behaviour tests above prove the
    wall works on the paths they drive, and this proves there is no path they
    did not drive.
    """

    def test_every_measured_call_names_a_file_or_is_listed(self):
        missing = []
        walked = sorted((ROOT / "app").rglob("*.py"))
        # A FLOOR ON WHAT WAS LOOKED AT. Audited 2026-09-06 by emptying every
        # discovered set: this passed, because a walk that finds no files
        # finds no offenders and reports the same green as a clean tree. The
        # same defect was found in the mirror's own scan the day before -
        # four of eleven rules running and calling the tree clean.
        self.assertGreater(len(walked), 20, "the walk over app/ found almost nothing")
        for path in walked:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not (isinstance(func, ast.Attribute) and func.attr == "measured"):
                    continue
                if not (isinstance(func.value, ast.Name) and func.value.id == "instrument"):
                    continue
                names_a_file = any(
                    keyword.arg == "from_file" for keyword in node.keywords
                )
                fact = None
                if node.args and isinstance(node.args[0], ast.Constant):
                    fact = node.args[0].value
                relative = str(path.relative_to(ROOT)).replace("\\", "/")
                if names_a_file or (relative, fact) in NO_FILE_TO_NAME:
                    continue
                missing.append(f"{relative}:{node.lineno} stamping {fact!r}")

        self.assertEqual(
            [],
            missing,
            "these stamps do not say which file they were read from, so wall 8 "
            "never runs on them. Pass from_file=<the path this tool read>, or - "
            "if the reading really is not from a file - add it to NO_FILE_TO_NAME "
            "with the reason, where a reviewer will see it.",
        )

    def test_the_listed_exemptions_are_still_real(self):
        """A listed exemption that no longer exists is a hole waiting for
        somebody to reuse the name."""
        for relative in {relative for relative, _fact in NO_FILE_TO_NAME}:
            self.assertTrue(
                (ROOT / relative).exists(), f"{relative} is listed and is not there"
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
