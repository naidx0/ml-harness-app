"""The one ML stage that stated five outcomes and offered no build at all.

## Why it had none, and why that was not a missing proposer

`docs/PHASES.md` step 8 asks for the stages with zero builds, worst first, and
`stage_4_format` was the worst. Its reason, in `propose.NOT_COVERED`, named the
remedy and it was not a proposer:

> two facts that cannot enter the ledger by any route. `schema_compliance` is
> declared `source: inspect` and `schema_expressible` `source: derive`, and BOTH
> admit MEASURED only - so the person cannot state them - while no registered
> tool declares `measures=` for either... **it closes when a tool measures
> `schema_compliance`, not when a proposer is written.**

Every node left in that stage reads one of the two, so a null in either made all
of them false and the stage ran off the end - at exactly the people who had
already turned structured outputs on and wanted to know what it achieved.

`app/tools/shapes.py` is the tool that sentence asked for.

## What is deliberately still open, and this file asserts that too

`schema_expressible` - *could a schema express the target shape at all* - is a
judgement about the person's own requirements. It is declared `source: derive`
with **no entry in the ledger's own `derived:` block**, so nothing derives it;
no tool can read it; and `derive` admits MEASURED only, so the person cannot
state it. That is a defect in a fact's DECLARATION and no build can close it.
`TheOtherHalfIsStillOpenAndSaysSo` pins that state, so the day the ledger says
`source: ask` this file asks to be re-read rather than quietly passing.

## The subset validator, and why refusing is the honest half

There is no JSON Schema library in this project's dependencies. The checker
implements a declared subset and **refuses a schema using anything outside it**.
A validator that silently skipped `anyOf` would report a compliance figure for a
schema whose hardest half it never looked at: a fabricated number with a real
provenance chain, which is the exact failure the walls in
`app/tools/evidence.py` exist for. `TheSubsetRefusesRatherThanSkipping` drives
that against a real schema using `anyOf`.

## The denominator is every row, and that is the decision worth testing

Three of the twenty fixture rows are prose with a brace in them. They are
failures, not skips. A fraction computed over "the rows that parsed" would rise
as the system got worse, because the rows it fails hardest on are the ones it
would drop. `test_prose_wrapping_the_json_counts_against` is that assertion.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from app import diagnosis, events, storm
from app.tools import REGISTRY, evidence, propose, shapes

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "format"
OUTPUTS = str(FIXTURES / "outputs.jsonl")
SCHEMA = str(FIXTURES / "schema.json")
UNSUPPORTED = str(FIXTURES / "unsupported-schema.json")

#: 20 rows: 14 satisfy, 3 are prose, 2 omit a required field, 1 breaks the enum.
ROWS = 20
SATISFY = 14


class TheCheckerIsASubsetAndSaysSoTest(unittest.TestCase):
    def test_the_supported_set_is_small_and_stated(self):
        self.assertIn("type", shapes.SUPPORTED)
        self.assertIn("required", shapes.SUPPORTED)
        self.assertIn("enum", shapes.SUPPORTED)
        self.assertNotIn("anyOf", shapes.SUPPORTED)
        self.assertNotIn("allOf", shapes.SUPPORTED)

    def test_a_supported_schema_is_accepted(self):
        shapes.check_schema(json.loads(Path(SCHEMA).read_text(encoding="utf-8")))

    def test_an_unsupported_keyword_is_refused_and_named(self):
        with self.assertRaises(shapes.SchemaError) as caught:
            shapes.check_schema(
                json.loads(Path(UNSUPPORTED).read_text(encoding="utf-8"))
            )
        said = str(caught.exception)
        self.assertIn("anyOf", said)
        self.assertIn("NOTHING WAS MEASURED", said)

    def test_a_nested_unsupported_keyword_is_found(self):
        """THE ONE THAT MATTERS. A top-level scan would pass this schema: its
        outer keywords are all supported and its meaning is still uncomputable."""
        nested = {
            "type": "object",
            "properties": {"x": {"type": "object", "properties": {"y": {"allOf": []}}}},
        }
        found = shapes.unsupported_keywords(nested)
        self.assertEqual(["$.properties.x.properties.y.allOf"], found)

    def test_a_schema_that_is_not_an_object_is_refused(self):
        with self.assertRaises(shapes.SchemaError):
            shapes.check_schema(["a", "list"])

    def test_a_boolean_does_not_satisfy_integer(self):
        """`isinstance(True, int)` is true in Python and false in JSON, and a
        model returning `true` where a count was wanted is a real output."""
        self.assertIsNotNone(shapes._fails(True, {"type": "integer"}))
        self.assertIsNone(shapes._fails(1, {"type": "integer"}))

    def test_an_integer_satisfies_number(self):
        """The other direction, and it is the one a strict reading gets wrong:
        JSON has one numeric type, so `json.loads("1")` giving an `int` must
        not fail a schema saying `number`."""
        self.assertIsNone(shapes._fails(1, {"type": "number"}))


class TheToolCountsWhatIsThereTest(unittest.TestCase):
    def setUp(self):
        import support

        support.sandbox(self)
        self.thread = int(events.create_thread(title="a format question")["id"])

    def _run(self, **overrides):
        arguments = {"path": OUTPUTS, "schema_path": SCHEMA}
        arguments.update(overrides)
        return REGISTRY.call(
            "measure_the_format",
            arguments,
            actor=evidence.USER,
            thread_id=self.thread,
        )

    def test_it_measures_the_fraction_and_stamps_it(self):
        report = self._run()
        self.assertTrue(report["ok"], report)
        self.assertEqual(ROWS, report["outputs"])
        self.assertEqual(SATISFY, report["satisfied"])
        self.assertAlmostEqual(SATISFY / ROWS, report["schema_compliance"])
        self.assertEqual(1, len(report["measured"]))
        self.assertEqual(diagnosis.MEASURED, report["measured"][0]["origin"])

    def test_prose_wrapping_the_json_counts_against(self):
        """Three fixture rows are `Sure! Here is the JSON: {...}`. A model that
        does that has failed the format, and a denominator that dropped them
        would report 14/17 - a figure that RISES as the system gets worse."""
        report = self._run()
        reasons = " ".join(row["why"] for row in report["first_failures"])
        self.assertIn("text rather than JSON", reasons)
        self.assertNotEqual(SATISFY / 17, report["schema_compliance"])

    def test_the_failures_it_shows_name_the_row_and_the_reason(self):
        report = self._run()
        self.assertTrue(report["first_failures"])
        self.assertLessEqual(len(report["first_failures"]), shapes.EXAMPLES_SHOWN)
        for row in report["first_failures"]:
            self.assertIsInstance(row["row"], int)
            self.assertGreater(len(row["why"]), 10)

    def test_an_unsupported_schema_measures_nothing_at_all(self):
        report = self._run(schema_path=UNSUPPORTED)
        self.assertFalse(report["ok"])
        self.assertEqual("schema_not_supported", report["error"])
        self.assertEqual([], evidence.rows_for(self.thread))

    def test_a_missing_file_measures_nothing(self):
        for missing in ({"path": "/nowhere/outputs.jsonl"}, {"schema_path": "/nowhere/s.json"}):
            with self.subTest(**missing):
                report = self._run(**missing)
                self.assertFalse(report["ok"])
                self.assertEqual("no_such_file", report["error"])
        self.assertEqual([], evidence.rows_for(self.thread))

    def test_an_empty_file_is_undefined_rather_than_zero(self):
        """A compliance figure over no rows is not 0.0, and stamping 0.0 would
        put a number on the ledger meaning 'your format is completely broken'
        for a file that says nothing."""
        empty = Path(self.sandbox_root() if hasattr(self, "sandbox_root") else "/tmp")
        path = Path(__file__).resolve().parent / "fixtures" / "format" / "_empty.jsonl"
        path.write_text("", encoding="utf-8")
        self.addCleanup(path.unlink)
        report = self._run(path=str(path))
        self.assertFalse(report["ok"])
        self.assertEqual("no_rows", report["error"])
        self.assertEqual([], evidence.rows_for(self.thread))

    def test_the_stamp_names_both_files(self):
        report = self._run()
        how = report["measured"][0]["how"]
        self.assertIn("outputs.jsonl", how)
        self.assertIn("schema.json", how)


class TheWallsStillStandOverItTest(unittest.TestCase):
    """It is an instrument like any other, so the walls apply to it like any
    other. Asserted rather than assumed, because a new minting tool is exactly
    where an exemption gets introduced by accident."""

    def test_it_declares_the_one_fact_and_the_capability_that_fact_admits(self):
        spec = REGISTRY.get("measure_the_format")
        self.assertEqual(("schema_compliance",), spec.measures)
        self.assertEqual(("measurement.format.score",), spec.provides)

    def test_wall_9_binds_the_fact_to_it(self):
        ml = diagnosis.load_spec("docs/diagnosis_engine.yaml")
        self.assertEqual(
            ("measurement.format.score",), evidence.measured_by("schema_compliance", ml)
        )

    def test_it_declares_which_argument_it_reads(self):
        """Two of its three arguments name a file, so without this a step
        calling it could not be costed - see app/build.py."""
        spec = REGISTRY.get("measure_the_format")
        self.assertEqual(("path",), spec.subject)


class TheBuildRunsAndReEntersTest(unittest.TestCase):
    def setUp(self):
        import support

        support.sandbox(self)
        self.ml = diagnosis.default_spec()

    def _situation(self, **overrides):
        arguments = {"outputs_path": OUTPUTS, "schema_path": SCHEMA}
        arguments.update(overrides)
        return propose.Situation(
            outcome="ACTION__MEASURE_THE_FORMAT",
            result=diagnosis.diagnose({}, self.ml),
            **arguments,
        )

    def test_the_outcome_has_a_build_and_no_longer_has_a_reason(self):
        self.assertIn("ACTION__MEASURE_THE_FORMAT", propose.PROPOSERS)
        self.assertNotIn("ACTION__MEASURE_THE_FORMAT", propose.NOT_COVERED)
        self.assertIn("ACTION__MEASURE_THE_FORMAT", propose.COVERAGE)

    def test_it_refuses_without_either_path_and_names_which(self):
        for missing in ("outputs_path", "schema_path"):
            with self.subTest(missing=missing):
                with self.assertRaises(propose.NotEnoughToPropose) as caught:
                    propose.PROPOSERS["ACTION__MEASURE_THE_FORMAT"](
                        self._situation(**{missing: ""})
                    )
                self.assertIn(missing, caught.exception.needs)

    def test_the_criterion_is_the_origin_and_never_the_value(self):
        """A build held to a HIGH fraction would be a plan with a preferred
        result. S4_CONSTRAINT_NOT_HOLDING is a real answer, reached by
        measuring."""
        plan = propose.PROPOSERS["ACTION__MEASURE_THE_FORMAT"](self._situation())
        self.assertEqual("is_measured", plan.exit_criterion.comparator)
        self.assertEqual(
            "fact_origins.schema_compliance", plan.exit_criterion.subject
        )

    def test_it_names_the_half_it_cannot_close_before_it_runs(self):
        plan = propose.PROPOSERS["ACTION__MEASURE_THE_FORMAT"](self._situation())
        risks = " ".join(risk.what + " " + risk.what_we_do for risk in plan.risks)
        self.assertIn("schema_expressible", risks)

    def test_it_runs_to_done_with_no_deviations(self):
        thread_id = int(events.create_thread(title="a format question")["id"])
        plan = propose.PROPOSERS["ACTION__MEASURE_THE_FORMAT"](self._situation())
        declared = storm.declare(plan, thread_id=thread_id)
        list(storm.run(declared["storm"]))
        finished = storm.attach(declared["storm"])
        self.assertEqual("done", finished.state, finished.as_dict())
        self.assertEqual((), finished.deviations)
        states = [step.get("state") for step in finished.as_dict()["steps"]]
        self.assertTrue(all(state == "done" for state in states), states)

    def test_the_fraction_it_produced_is_the_one_the_tool_computes(self):
        thread_id = int(events.create_thread(title="a format question")["id"])
        plan = propose.PROPOSERS["ACTION__MEASURE_THE_FORMAT"](self._situation())
        declared = storm.declare(plan, thread_id=thread_id)
        list(storm.run(declared["storm"]))
        counted = [
            step
            for step in storm.attach(declared["storm"]).as_dict()["steps"]
            if step["id"] == "count"
        ][0]
        self.assertAlmostEqual(
            SATISFY / ROWS, counted["outputs"]["schema_compliance"]
        )


class TheOtherHalfIsStillOpenAndSaysSo(unittest.TestCase):
    """`schema_expressible` remains unobtainable, and this pins that state.

    Not an approval of it. The day the ledger declares it `source: ask` this
    test fails and asks to be re-read, which is the only way a limit recorded
    in a docstring stays true.
    """

    def setUp(self):
        self.ml = diagnosis.load_spec("docs/diagnosis_engine.yaml")

    def test_nothing_derives_it(self):
        """Read off the raw document, because `Spec` does not surface the
        `derived:` block - which is itself part of the finding: a fact declared
        `source: derive` is not checked against that block anywhere."""
        derived = (self.ml.raw or {}).get("derived") or {}
        self.assertNotIn("schema_expressible", set(derived))
        # The guard on the guard: the block is real and holds other names, so
        # this is not passing because it read an empty dict.
        self.assertGreater(len(derived), 3, sorted(derived))

    def test_no_tool_measures_it(self):
        self.assertEqual(
            [], [spec.name for spec in REGISTRY if "schema_expressible" in spec.measures]
        )

    def test_the_person_cannot_state_it_either(self):
        """`derive` admits MEASURED and nothing else, so a typed answer is
        refused - which is right for a derived fact and wrong for this one,
        because nothing derives it."""
        self.assertEqual(
            [diagnosis.MEASURED], list(self.ml.admissible_for("schema_expressible"))
        )

    def test_the_written_reason_still_names_it(self):
        reason = propose.NOT_COVERED.get("ACTION__FIX_THE_DECODER", "")
        self.assertIn("schema_compliance", reason + propose._A_FACT_WITH_NO_DOOR)
        self.assertIn("schema_expressible", propose._A_FACT_WITH_NO_DOOR)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
