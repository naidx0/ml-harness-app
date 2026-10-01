"""A claim cannot restate an instrument, and a modality is inspected before it is believed.

MEASURED 2026-09-23, Max's thread 93 on permission `full`, read from a copy of
his database. The harness had MEASURED eval_size_n (40, by measure_eval_set),
the hardware facts (inspect_hardware) and the baseline (measure_baseline), rows
922-930. The model then called state_facts and filed rows 933-940: every one of
those facts again, at the SAME values, as STATED - "full mode: the person
delegated this decision to the model via state_facts" - plus `modality`
"tabular" for a JSONL of ML-principles question/answer rows whose fields are
prose. The walk went down the tabular branch and asked for `tabular_rows` for a
dataset that has no table, and the model spent a round restating what the
harness already knew.

Two guards in `state_facts`, and one case per exit:

  G1  a fact that already has a MEASURED row on this thread is not filed again:
      the same value is answered "already measured ... nothing to do", a
      different value is refused with both numbers and the instrument named,
      and a fact nobody measured in the same call is still filed;
  G2  a stated `modality` that the file on record contradicts is refused with
      the file named, and the inspection's own answer is filed in its place as
      the harness's derived default; with nothing on record that can be
      opened, or a file whose rows do not settle it, the statement stands.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import diagnosis, events  # noqa: E402
from app.tools import evidence, measure  # noqa: E402
from app.tools.evidence import Instrument  # noqa: E402
from app.tools.registry import REGISTRY  # noqa: E402


def _stamp(thread_id: int, tool: str, fact: str, value: Any) -> None:
    """Stamp through an instrument, the way the tool itself does.

    `provides` is read off the tool's own registration because wall 9 checks it
    against the fact's declared `measured_by`.
    """
    declared = getattr(REGISTRY, "_tools", {}).get(tool)
    Instrument(
        tool=tool,
        actor=evidence.MODEL,
        thread_id=thread_id,
        measures=frozenset({fact}),
        provides=frozenset(getattr(declared, "provides", ()) or ()),
    ).measured(fact, value, how=f"{tool} read it off the eval set")


def _full_thread() -> int:
    """A Full thread with eval_size_n and baseline_score MEASURED, like thread 93."""
    thread_id = int(events.create_thread("thread 93")["id"])
    events.set_thread_permission(thread_id, "full")
    _stamp(thread_id, "measure_eval_set", "eval_size_n", 40)
    _stamp(thread_id, "measure_baseline", "baseline_score", 0.0)
    return thread_id


def _say(thread_id: int, facts: dict[str, Any]) -> dict[str, Any]:
    return measure.state_facts(
        facts,
        instrument=Instrument(
            tool="state_facts", actor=evidence.MODEL, thread_id=thread_id
        ),
        ledger=diagnosis.default_spec(),
    )


def _rows(thread_id: int, fact: str) -> list[dict[str, Any]]:
    return [row for row in evidence.rows_for(thread_id) if row["fact"] == fact]


class ARestatedMeasurementIsNotFiledTest(unittest.TestCase):
    """G1."""

    def setUp(self) -> None:
        support.sandbox(self)
        self.thread_id = _full_thread()

    def test_the_same_value_files_nothing_and_says_it_is_already_measured(self) -> None:
        """(a) Rows 937 and 935: 40 said back as 40, and 0 said back for 0.0."""
        before = len(evidence.rows_for(self.thread_id))
        out = _say(self.thread_id, {"eval_size_n": 40, "baseline_score": 0})
        self.assertTrue(out.get("ok"), out)
        self.assertEqual(len(evidence.rows_for(self.thread_id)), before)
        self.assertEqual(
            [row["origin"] for row in _rows(self.thread_id, "eval_size_n")],
            [evidence.MEASURED],
        )
        self.assertIn(
            "already measured: 40 by measure_eval_set - nothing to do", out["summary"]
        )
        self.assertIn(
            "already measured: 0.0 by measure_baseline - nothing to do", out["summary"]
        )
        noted = {row["fact"]: row for row in out.get("already_measured") or []}
        self.assertEqual(sorted(noted), ["baseline_score", "eval_size_n"])
        self.assertEqual(noted["eval_size_n"]["tool"], "measure_eval_set")
        self.assertEqual(out.get("recorded"), [])

    def test_a_different_value_is_refused_naming_both_numbers_and_the_instrument(
        self,
    ) -> None:
        """(b) A claim cannot outrank a measurement, and no row is written."""
        before = len(evidence.rows_for(self.thread_id))
        out = _say(self.thread_id, {"eval_size_n": 120})
        self.assertEqual(len(evidence.rows_for(self.thread_id)), before)
        refused = (out.get("refused") or {}).get("eval_size_n") or ""
        self.assertIn("120", refused)
        self.assertIn("40", refused)
        self.assertIn("measure_eval_set", refused)
        self.assertIn("eval_size_n", out["summary"])
        self.assertFalse(out.get("ok"), out)

    def test_an_untouched_fact_in_the_same_call_is_still_filed_stated(self) -> None:
        """(c) The guard loses the restated fact, never the batch."""
        out = _say(
            self.thread_id,
            {"eval_size_n": 40, "baseline_score": 0.5, "target_score": 0.3},
        )
        self.assertTrue(out.get("ok"), out)
        target = _rows(self.thread_id, "target_score")
        self.assertEqual(len(target), 1)
        self.assertEqual(target[0]["origin"], evidence.STATED)
        self.assertEqual(target[0]["value"], 0.3)
        self.assertEqual(
            [row["origin"] for row in _rows(self.thread_id, "baseline_score")],
            [evidence.MEASURED],
        )
        self.assertEqual([row["fact"] for row in out["recorded"]], ["target_score"])
        self.assertIn("baseline_score", out.get("refused") or {})


class AModalityIsInspectedBeforeItIsBelievedTest(unittest.TestCase):
    """G2."""

    def setUp(self) -> None:
        support.sandbox(self)
        self.thread_id = _full_thread()
        self.folder = Path(tempfile.mkdtemp())

    def _file(self, rows: list[dict[str, Any]], name: str = "eval.jsonl") -> Path:
        path = self.folder / name
        path.write_bytes("\n".join(json.dumps(row) for row in rows).encode("utf-8"))
        return path

    def _principles_file(self) -> Path:
        """The shape of Max's ml-principles eval.jsonl: prose question, record answer."""
        return self._file(
            [
                {
                    "row_id": i,
                    "task_type": "concept" if i % 2 else "decide",
                    "lane": f"L{i % 9}",
                    "input": (
                        f"Question {i}: when should a team pick a loss function that "
                        "matches the decision they will actually make with the model?"
                    ),
                    "expected": {
                        "task_type": "concept",
                        "summary": (
                            "A loss maps predictions and labels to a scalar the "
                            "optimizer minimizes; pick it to match the decision task."
                        ),
                    },
                    "rubric_keys": ["loss", "decision"],
                }
                for i in range(40)
            ]
        )

    def _counted(self, path: Path) -> None:
        """The thread's own record that measure_eval_set counted this file."""
        events.append(
            "tool.call",
            {"id": "c1", "name": "measure_eval_set", "arguments": {"path": str(path)}},
            thread_id=self.thread_id,
        )
        events.append(
            "tool.result",
            {"id": "c1", "name": "measure_eval_set", "ok": True,
             "result": {"path": str(path)}},
            thread_id=self.thread_id,
        )

    def test_tabular_against_a_jsonl_of_text_rows_is_refused_naming_the_file(
        self,
    ) -> None:
        """(d) Row 933."""
        path = self._principles_file()
        self._counted(path)
        out = _say(self.thread_id, {"modality": "tabular"})
        refused = (out.get("refused") or {}).get("modality") or ""
        self.assertIn(str(path), refused)
        self.assertIn("text dataset, not a table", refused)
        self.assertEqual(
            [row for row in _rows(self.thread_id, "modality")
             if row["origin"] == evidence.STATED],
            [],
        )

    def test_the_inspection_files_its_own_answer_with_its_origin_and_how(self) -> None:
        """(f) Refusing alone would leave the walk blocked on modality, and the
        model would state it again. The file answers it, so the harness files
        that answer: DEFAULTED by the harness (the ledger's word for a derived
        value - no instrument declares `modality`), with a `how` naming the file
        and the fields that are prose."""
        path = self._principles_file()
        self._counted(path)
        out = _say(self.thread_id, {"modality": "tabular"})
        rows = _rows(self.thread_id, "modality")
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]["value"], "text")
        self.assertEqual(rows[0]["origin"], evidence.DEFAULTED)
        self.assertEqual(rows[0]["actor"], evidence.HARNESS)
        self.assertIn(str(path), rows[0]["how"])
        self.assertIn("input", rows[0]["how"])
        self.assertIn("expected", rows[0]["how"])
        self.assertEqual((out.get("inspected") or {}).get("modality"), "text")

        facts, _ = evidence.assemble_facts(
            self.thread_id, {}, evidence.MODEL, ledger=diagnosis.default_spec()
        )
        self.assertEqual(facts["modality"].value, "text")

        again = _say(self.thread_id, {"modality": "tabular"})
        self.assertIn("modality", again.get("refused") or {})
        self.assertEqual(len(_rows(self.thread_id, "modality")), 1)

    def test_a_modality_the_file_agrees_with_is_filed_stated(self) -> None:
        """The positive control for (d): the same file, a statement it supports."""
        path = self._principles_file()
        self._counted(path)
        out = _say(self.thread_id, {"modality": "text"})
        self.assertTrue(out.get("ok"), out)
        rows = _rows(self.thread_id, "modality")
        self.assertEqual([(r["value"], r["origin"]) for r in rows],
                         [("text", evidence.STATED)])

    def test_with_nothing_inspectable_the_statement_stands(self) -> None:
        """(e) No file on record: filed STATED exactly as before."""
        out = _say(self.thread_id, {"modality": "tabular"})
        self.assertTrue(out.get("ok"), out)
        rows = _rows(self.thread_id, "modality")
        self.assertEqual([(r["value"], r["origin"]) for r in rows],
                         [("tabular", evidence.STATED)])

    def test_a_file_on_record_that_cannot_be_opened_settles_nothing(self) -> None:
        """(e) A path on record whose file is gone is not an inspection."""
        self._counted(self.folder / "gone.jsonl")
        out = _say(self.thread_id, {"modality": "tabular"})
        self.assertTrue(out.get("ok"), out)
        self.assertEqual(
            [r["origin"] for r in _rows(self.thread_id, "modality")],
            [evidence.STATED],
        )

    def test_rows_of_short_values_do_not_settle_it_so_the_statement_stands(
        self,
    ) -> None:
        """(e) Rows with no prose field are not called text: a table of labels and
        numbers is exactly what a tabular claim describes, so it is filed."""
        path = self._file(
            [{"age": 30 + i, "income": 1000 * i, "label": "yes" if i % 2 else "no"}
             for i in range(40)],
            name="table.jsonl",
        )
        self._counted(path)
        out = _say(self.thread_id, {"modality": "tabular"})
        self.assertTrue(out.get("ok"), out)
        self.assertEqual(
            [(r["value"], r["origin"]) for r in _rows(self.thread_id, "modality")],
            [("tabular", evidence.STATED)],
        )


if __name__ == "__main__":
    unittest.main()
