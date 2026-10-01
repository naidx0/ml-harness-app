"""A stated modality the file on record contradicts is quarantined, and the walk leaves the tabular branch.

The owner's thread 93. On 2026-09-22 the model stated `modality` "tabular"
(fact_evidence row 933) for `ml-principles-dataset/data/splits/eval.jsonl` -
JSONL of `task_type`, `input`, `expected`: a prose question and a record of
prose answers. On 2026-09-23 `state_facts` learnt to refuse such a statement,
but the row already on record still outranked the harness's derivation, and
every walk went down the tabular branch to S8_TABULAR_ROWS_UNKNOWN asking for
the row count of a table that does not exist.

  (d) a STATED modality inspection contradicts -> the row is moved to
      `quarantined_facts` with a reason naming the file and the prose fields,
      modality resolves to `text` (DEFAULTED, by the harness), and the verdict
      leaves S8_TABULAR_ROWS_UNKNOWN - moved by the `run_diagnosis` tool (ii),
      the conductor's walk, and by NO read route: (i) the Stage and the report
      show the honest branch in memory and leave both tables as they found them;
  (e) a STATED modality inspection agrees with -> untouched; and a table the
      inspection settles nothing about -> untouched;
  (f) a second walk adds no second quarantine row and no second DEFAULTED row;
  (h) and once off that branch, an inspect gap nothing measures does not
      outrank the question a tool can settle;
  (j) and when it IS the move, its sentence never says state_facts.
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
from app import conductor, db, diagnosis, events  # noqa: E402
from app.tools import evidence  # noqa: E402
from app.tools.evidence import Instrument  # noqa: E402
from app.tools.registry import REGISTRY  # noqa: E402


def _stamp(thread_id: int, tool: str, fact: str, value: Any) -> None:
    declared = REGISTRY.get(tool)
    Instrument(
        tool=tool,
        actor=evidence.MODEL,
        thread_id=thread_id,
        measures=frozenset({fact}),
        provides=frozenset(getattr(declared, "provides", ()) or ()),
    ).measured(fact, value, how=f"{tool} read it")


def _default(thread_id: int, fact: str, value: Any) -> None:
    evidence.record(
        fact=fact, value=value, origin=evidence.DEFAULTED, actor=evidence.HARNESS,
        how=f"Full: set {fact} by rule for this test", thread_id=thread_id,
        ledger=diagnosis.default_spec(),
    )


def _quarantined(thread_id: int) -> list[dict[str, Any]]:
    return [row for row in evidence.quarantine_view() if row["thread_id"] == thread_id]


class _Thread93(unittest.TestCase):

    def setUp(self) -> None:
        support.sandbox(self)
        self.folder = Path(tempfile.mkdtemp())
        self.thread_id = int(events.create_thread("thread 93")["id"])
        events.set_thread_permission(self.thread_id, "full")
        t = self.thread_id
        _stamp(t, "measure_eval_set", "eval_size_n", 40)
        _stamp(t, "measure_baseline", "baseline_score", 0.0)
        _stamp(t, "measure_baseline", "trivial_baseline_score", 0.05)
        _stamp(t, "measure_baseline", "baseline_measured", True)
        _default(t, "task_family", "extraction")
        _default(t, "target_score", 0.2691)
        _default(t, "privacy", "on_prem_only")

    def _state(self, value: str) -> None:
        """Row 933, as it was written: STATED by the model under Full."""
        evidence.record(
            fact="modality", value=value, origin=evidence.STATED, actor=evidence.MODEL,
            how="full mode: the person delegated this decision to the model via state_facts",
            tool="state_facts", thread_id=self.thread_id, ledger=diagnosis.default_spec(),
        )

    def _on_record(self, rows: list[dict[str, Any]], name: str = "eval.jsonl") -> Path:
        path = self.folder / name
        path.write_bytes("\n".join(json.dumps(row) for row in rows).encode("utf-8"))
        events.append(
            "tool.call",
            {"id": "p1", "name": "profile_dataset", "arguments": {"path": str(path)}},
            thread_id=self.thread_id,
        )
        events.append(
            "tool.result",
            {"id": "p1", "name": "profile_dataset", "ok": True, "result": {"path": str(path)}},
            thread_id=self.thread_id,
        )
        return path

    def _principles(self) -> Path:
        """The shape of Max's ml-principles eval.jsonl."""
        return self._on_record(
            [
                {
                    "row_id": i,
                    "task_type": "concept" if i % 2 else "decide",
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
                }
                for i in range(40)
            ]
        )

    def _walk(self, persist: bool = False) -> tuple[dict[str, Any], Any]:
        """A read route's walk by default - called exactly as the readers call it,
        with no `persist` at all - and the tool's walk with `persist=True`."""
        ledger = diagnosis.default_spec()
        extra = {"persist": True} if persist else {}
        sheet, trail = evidence.assemble_facts(self.thread_id, ledger=ledger, **extra)
        return sheet, diagnosis.diagnose(sheet, ledger)

    def _run_diagnosis(self) -> dict[str, Any]:
        """The walk the conductor's turn goes through: the tool, as the harness."""
        payload = REGISTRY.call(
            "run_diagnosis", {"facts": {}}, actor=evidence.HARNESS, thread_id=self.thread_id
        )
        self.assertTrue(payload.get("ok"), payload)
        return payload

    def _counts(self) -> tuple[int, int]:
        """Whole-table row counts: the ledger and the quarantine."""
        evidence.ensure_quarantine_table()
        with db.session() as connection:
            return (
                connection.execute("SELECT COUNT(*) FROM fact_evidence").fetchone()[0],
                connection.execute("SELECT COUNT(*) FROM quarantined_facts").fetchone()[0],
            )

    def _modality_rows(self) -> list[tuple[Any, str]]:
        return [(row["value"], row["origin"]) for row in evidence.rows_for(self.thread_id)
                if row["fact"] == "modality"]


class AReadRouteResolvesButWritesNothingTest(_Thread93):
    """(i) The Stage, the report and the export are readers. Their contract -
    `thread_stage_ep`: "A GET ... writes nothing" - holds, and they still show
    the honest branch the moment the contradiction exists."""

    def test_the_stage_and_the_report_show_the_honest_branch_and_write_nothing(self) -> None:
        from app import journey_report, stage

        self._principles()
        self._state("tabular")
        before = self._counts()

        report = journey_report.build(self.thread_id)
        staged = stage.build(self.thread_id)
        sheet, result = self._walk()

        self.assertEqual(self._counts(), before)
        self.assertEqual(_quarantined(self.thread_id), [])
        self.assertEqual(self._modality_rows(), [("tabular", evidence.STATED)])
        for outcome in (report["verdict"]["outcome"],
                        staged["diagnosis"]["verdict"]["outcome"], result.outcome):
            self.assertEqual(outcome, "ACTION__CLASSIFY_FAILURES")
        self.assertEqual((sheet["modality"].value, sheet["modality"].origin),
                         ("text", evidence.DEFAULTED))
        self.assertNotIn("S8_TABULAR_ROWS_UNKNOWN", [e.as_dict().get("id") for e in result.path])


class TheToolWalkQuarantinesOnceTest(_Thread93):
    """(d), (ii) and (f): the `run_diagnosis` tool - the conductor's walk - moves it, once."""

    def test_run_diagnosis_moves_the_row_with_reason_and_leaves_the_tabular_branch(self) -> None:
        path = self._principles()
        self._state("tabular")
        payload = self._run_diagnosis()
        self.assertEqual(payload["outcome"], "ACTION__CLASSIFY_FAILURES")
        self.assertEqual(payload["facts_used"]["modality"]["value"], "text")
        self.assertEqual(payload["facts_used"]["modality"]["origin"], evidence.DEFAULTED)

        moved = _quarantined(self.thread_id)
        self.assertEqual(len(moved), 1, moved)
        self.assertEqual((moved[0]["fact"], moved[0]["value"], moved[0]["origin"]),
                         ("modality", "tabular", evidence.STATED))
        because = moved[0]["quarantined_because"]
        self.assertIn(str(path), because)
        self.assertIn("input", because)
        self.assertIn("expected", because)
        # Moved, not copied: the claim can never route a walk again.
        self.assertEqual(self._modality_rows(), [("text", evidence.DEFAULTED)])
        derived = [r for r in evidence.rows_for(self.thread_id) if r["fact"] == "modality"][0]
        self.assertEqual(derived["actor"], evidence.HARNESS)
        self.assertIn(str(path), derived["how"])

    def test_a_second_tool_walk_adds_no_second_quarantine_row(self) -> None:
        self._principles()
        self._state("tabular")
        self._run_diagnosis()
        after_first = self._counts()
        again = self._run_diagnosis()
        self.assertEqual(self._counts(), after_first)
        self.assertEqual(again["outcome"], "ACTION__CLASSIFY_FAILURES")
        self.assertEqual(len(_quarantined(self.thread_id)), 1)
        self.assertEqual(self._modality_rows(), [("text", evidence.DEFAULTED)])

    def test_moving_the_same_row_twice_adds_nothing(self) -> None:
        self._state("tabular")
        row = [r for r in evidence.rows_for(self.thread_id) if r["fact"] == "modality"][0]
        evidence.quarantine_rows([row], "first")
        evidence.quarantine_rows([row], "second")
        with db.session() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM quarantined_facts WHERE id = ?", (int(row["id"]),)
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_a_database_that_cannot_be_written_still_walks_off_the_branch(self) -> None:
        """The contradiction is re-derived each walk; the move is the durable half."""
        self._principles()
        self._state("tabular")
        original = evidence.quarantine_rows

        def refuse(*_args: Any, **_kwargs: Any) -> list[int]:
            import sqlite3
            raise sqlite3.OperationalError("attempt to write a readonly database")

        evidence.quarantine_rows = refuse
        try:
            sheet, result = self._walk(persist=True)
        finally:
            evidence.quarantine_rows = original
        self.assertEqual(sheet["modality"].value, "text")
        self.assertNotEqual(result.outcome, "ACTION__COUNT_THE_ROWS")
        self.assertEqual(_quarantined(self.thread_id), [])


class AStatementTheFileDoesNotContradictStandsTest(_Thread93):
    """(e) On the writing walk, so "untouched" is a claim about a walk that could write."""

    def test_a_statement_inspection_agrees_with_is_untouched(self) -> None:
        self._principles()
        self._state("text")
        sheet, _ = self._walk(persist=True)
        self.assertEqual((sheet["modality"].value, sheet["modality"].origin),
                         ("text", evidence.STATED))
        self.assertEqual(self._modality_rows(), [("text", evidence.STATED)])
        self.assertEqual(_quarantined(self.thread_id), [])

    def test_a_table_the_inspection_settles_nothing_about_is_untouched(self) -> None:
        """Rows of labels and numbers are what a tabular claim describes."""
        self._on_record([{"age": 30 + i, "income": 1000 * i, "label": "yes" if i % 2 else "no"}
                         for i in range(40)])
        self._state("tabular")
        sheet, result = self._walk(persist=True)
        self.assertEqual((sheet["modality"].value, sheet["modality"].origin),
                         ("tabular", evidence.STATED))
        self.assertEqual(result.outcome, "ACTION__COUNT_THE_ROWS")
        self.assertEqual(_quarantined(self.thread_id), [])

    def test_no_file_on_record_is_untouched(self) -> None:
        self._state("tabular")
        sheet, _ = self._walk(persist=True)
        self.assertEqual(sheet["modality"].origin, evidence.STATED)
        self.assertEqual(_quarantined(self.thread_id), [])


class AnInspectGapIsNotTheMoveTest(_Thread93):

    def test_off_the_branch_the_move_is_the_question_a_tool_settles(self) -> None:
        """(h) Thread 93 after (d): the walk stops at ACTION__CLASSIFY_FAILURES,
        and `data_quality` - inspect, nothing registered reads it - was named
        over `failure_histogram`."""
        self._principles()
        self._state("tabular")
        payload = self._run_diagnosis()
        self.assertEqual(payload["outcome"], "ACTION__CLASSIFY_FAILURES")
        step = payload.get("next_step") or {}
        self.assertNotEqual(step.get("fact"), "data_quality")
        self.assertEqual(step.get("fact"), "failure_histogram")
        self.assertNotIn("state_facts", conductor._next_move_line(payload, permission="full"))

    def test_with_no_question_left_the_inspect_gap_is_named_and_never_stated(self) -> None:
        """(j) The gap branch's own sentence, for the case where the inspect gap
        IS the move because nothing else is asked: never "call state_facts"."""
        from types import SimpleNamespace
        from unittest import mock

        from app import asking

        self._principles()
        self._state("tabular")
        with mock.patch.object(
            asking, "next_step", return_value=SimpleNamespace(kind="none", question=None)
        ):
            payload = self._run_diagnosis()
        step = payload.get("next_step") or {}
        self.assertEqual((step.get("kind"), step.get("fact"), step.get("source")),
                         ("gap", "data_quality", "inspect"))
        self.assertIn("data_quality", payload["next"])
        self.assertIn("not something to state", payload["next"])
        self.assertNotIn("state_facts", payload["next"])
        self.assertNotIn("state_facts", conductor._next_move_line(payload, permission="full"))

if __name__ == "__main__":
    unittest.main()
