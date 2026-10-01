"""An inspect fact is read off a file, so the next move names the instrument and the file.

The owner's thread 93, 2026-09-23 14:12-14:15, permission Full, a small local
model. The walk stopped at S8_TABULAR_ROWS_UNKNOWN on `tabular_rows`, which the
ledger declares `source: inspect`. `profile_dataset` had run - on the EVAL file -
so the `already_run` branch of `conductor._next_move_line` said:

    next move: under Full, call state_facts NOW for tabular_rows - do not ask
    the person - or work the next step with tools

and the same standing brief says "A fact the ledger declares source: inspect is
not something to state". The model spent 471 reasoning events between the two
sentences and called no tool. It had already named the training split itself,
`ml-principles-dataset/data/splits/train.jsonl`, to `profile_repository` - the
wrong instrument, which answered "that is a file, not a repository".

One case per exit:

  (a)  inspect fact, instrument already ran, training split on record -> the
       line names profile_dataset and that file, and says no "state_facts";
  (a2) the same, instrument never ran -> "run profile_dataset on <file>";
  (b)  inspect fact, no training file on record -> the instrument and "the
       training file";
  (c)  an ask fact under Full still says state_facts - the control, unchanged;
  (g)  an inspect fact nothing registered measures -> no state_facts either;
  and the finder: a failed call is not a file on record, `train_eval` is not a
  training split, `split: "train"` names one whatever the file is called.
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
from app import conductor, diagnosis, events  # noqa: E402
from app.tools import evidence, measure  # noqa: E402
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
        fact=fact,
        value=value,
        origin=evidence.DEFAULTED,
        actor=evidence.HARNESS,
        how=f"Full: set {fact} by rule for this test",
        thread_id=thread_id,
        ledger=diagnosis.default_spec(),
    )


def _call(thread_id: int, call_id: str, name: str, arguments: dict, ok: bool,
          result: dict) -> None:
    events.append(
        "tool.call",
        {"id": call_id, "name": name, "arguments": arguments},
        thread_id=thread_id,
    )
    events.append(
        "tool.result",
        {"id": call_id, "name": name, "ok": ok, "result": result},
        thread_id=thread_id,
    )


class _Thread93(unittest.TestCase):
    """A Full thread with thread 93's ledger, on a table that really is a table.

    The eval file is a table of numbers and labels, so inspecting it settles
    nothing and the STATED `tabular` stands - these tests are about the line on
    a thread that is honestly on the tabular branch.
    """

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
        _default(t, "task_family", "classification")
        _default(t, "target_score", 0.2691)
        _default(t, "privacy", "on_prem_only")
        evidence.record(
            fact="modality",
            value="tabular",
            origin=evidence.STATED,
            actor=evidence.MODEL,
            how="full mode: the person delegated this decision to the model via state_facts",
            tool="state_facts",
            thread_id=t,
            ledger=diagnosis.default_spec(),
        )
        self.eval_file = self.folder / "eval.jsonl"
        self.eval_file.write_bytes(
            "\n".join(
                json.dumps({"age": 30 + i, "income": 1000 * i, "label": "yes" if i % 2 else "no"})
                for i in range(40)
            ).encode("utf-8")
        )
        self.train_file = self.folder / "train.csv"
        self.train_file.write_bytes(
            ("age,income,label\n" + "".join(f"{30 + i},{1000 * i},yes\n" for i in range(50))).encode("utf-8")
        )

    def _profiled_the_eval_file(self) -> None:
        """`profile_dataset` spent - on the EVAL file, as on thread 93."""
        _call(self.thread_id, "p1", "profile_dataset", {"path": str(self.eval_file)}, True,
              {"path": str(self.eval_file)})

    def _named_the_training_split_to_the_wrong_tool(self) -> None:
        """Thread 93's event 19884: profile_repository on the training split."""
        _call(
            self.thread_id, "r1", "profile_repository", {"path": "data/train.csv"}, True,
            {
                "repository": {"path": str(self.train_file), "exists": True,
                               "notes": ["That is a file, not a repository."]},
                "workspace_resolved": {"path": {"from": "data/train.csv",
                                                "to": str(self.train_file)}},
            },
        )

    def _walk(self) -> dict[str, Any]:
        payload = REGISTRY.call(
            "run_diagnosis", {"facts": {}}, actor=evidence.HARNESS, thread_id=self.thread_id
        )
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual(payload["outcome"], "ACTION__COUNT_THE_ROWS", payload.get("path"))
        self.assertEqual((payload.get("next_step") or {}).get("fact"), "tabular_rows")
        return payload


class TheLineNamesTheInstrumentAndTheFileTest(_Thread93):

    def test_a_wrong_tool_already_ran_the_line_names_profile_dataset_and_the_train_file(
        self,
    ) -> None:
        """(a) Thread 93 exactly."""
        self._named_the_training_split_to_the_wrong_tool()
        self._profiled_the_eval_file()
        payload = self._walk()
        self.assertTrue(payload["next_step"].get("already_run"))
        line = conductor._next_move_line(payload, permission="full")
        self.assertIn("profile_dataset", line)
        self.assertIn("profile_dataset on data/train.csv", line)
        self.assertIn("do not ask the person", line)
        self.assertNotIn("state_facts", line)
        # And the tool result's own sentence, which the model reads too.
        self.assertIn("data/train.csv", payload["next"])
        self.assertNotIn("state_facts", payload["next"])
        # Under every permission, not only Full.
        self.assertNotIn("state_facts", conductor._next_move_line(payload, permission="ask"))

    def test_the_instrument_never_ran_the_line_says_run_it_on_the_file(self) -> None:
        """(a2) The not-yet-run exit, same file."""
        self._named_the_training_split_to_the_wrong_tool()
        payload = self._walk()
        self.assertFalse(payload["next_step"].get("already_run"))
        line = conductor._next_move_line(payload, permission="full")
        self.assertIn("run profile_dataset on data/train.csv for tabular_rows", line)
        self.assertNotIn("state_facts", line)

    def test_no_file_on_record_names_the_instrument_and_the_training_file(self) -> None:
        """(b)"""
        self._profiled_the_eval_file()
        payload = self._walk()
        line = conductor._next_move_line(payload, permission="full")
        self.assertIn("profile_dataset on the training file", line)
        self.assertNotIn("state_facts", line)
        self.assertNotIn(str(self.eval_file), line)


class AnAskFactIsStillStatedTest(unittest.TestCase):
    """(c) The control: the exits an ask fact takes are unchanged."""

    def test_an_ask_fact_under_full_still_says_state_facts(self) -> None:
        for already in (False, True):
            payload = {"next_step": {"kind": "question", "fact": "target_score",
                                     "tool": "state_facts", "already_run": already,
                                     "source": "ask"}}
            line = conductor._next_move_line(payload, permission="full")
            self.assertIn("call state_facts NOW for target_score", line)
            self.assertIn("do not ask the person", line)

    def test_an_ask_gap_under_full_still_says_state_facts(self) -> None:
        payload = {"next_step": {"kind": "gap", "fact": "goal_text", "tool": "state_facts",
                                 "source": "ask"}}
        self.assertIn("call state_facts NOW for goal_text",
                      conductor._next_move_line(payload, permission="full"))


class AnUnmeasuredInspectFactIsNotStatedEitherTest(unittest.TestCase):
    """(g) Nothing registered measures `tabular_features`; it is still not said."""

    def test_no_instrument_no_state_facts(self) -> None:
        for kind in ("gap", "question"):
            for permission in ("full", "ask"):
                payload = {"next_step": {"kind": kind, "fact": "tabular_features",
                                         "tool": "state_facts" if kind == "gap" else None,
                                         "source": "inspect"}}
                line = conductor._next_move_line(payload, permission=permission)
                self.assertIn("tabular_features", line)
                self.assertNotIn("state_facts", line)


class TheTrainingFileOnRecordTest(unittest.TestCase):

    def setUp(self) -> None:
        support.sandbox(self)
        self.folder = Path(tempfile.mkdtemp())
        self.thread_id = int(events.create_thread("finder")["id"])
        self.train = self.folder / "train.jsonl"
        self.train.write_bytes(b'{"a": 1}\n')

    def test_a_file_a_tool_found_is_on_record_as_named(self) -> None:
        _call(self.thread_id, "a", "profile_repository", {"path": "splits/train.jsonl"}, True,
              {"workspace_resolved": {"path": {"from": "splits/train.jsonl", "to": str(self.train)}}})
        self.assertEqual(measure.training_file_on_record(self.thread_id),
                         ("splits/train.jsonl", str(self.train)))

    def test_a_call_that_failed_is_not_a_file_on_record(self) -> None:
        """Thread 93's event 19811: the right name read against the wrong folder."""
        _call(self.thread_id, "a", "profile_repository", {"path": "data/splits/train.jsonl"}, False,
              {"summary": "There is nothing at that path."})
        self.assertIsNone(measure.training_file_on_record(self.thread_id))

    def test_a_name_that_also_names_another_split_is_not_guessed(self) -> None:
        _call(self.thread_id, "a", "profile_dataset", {"path": "train_eval.jsonl"}, True, {})
        _call(self.thread_id, "b", "profile_dataset", {"path": "constrained.jsonl"}, True, {})
        self.assertIsNone(measure.training_file_on_record(self.thread_id))

    def test_split_train_names_the_training_file_whatever_it_is_called(self) -> None:
        _call(self.thread_id, "a", "profile_dataset", {"path": "rows.jsonl", "split": "train"}, True, {})
        self.assertEqual(measure.training_file_on_record(self.thread_id), ("rows.jsonl", None))

    def test_the_newest_wins(self) -> None:
        _call(self.thread_id, "a", "profile_dataset", {"path": "old/train.jsonl"}, True, {})
        _call(self.thread_id, "b", "profile_dataset", {"path": "new/train.jsonl"}, True, {})
        self.assertEqual(measure.training_file_on_record(self.thread_id)[0], "new/train.jsonl")


if __name__ == "__main__":
    unittest.main()
