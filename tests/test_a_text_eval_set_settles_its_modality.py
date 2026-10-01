"""A counted eval set of text rows settles `modality` - on every permission.

Max's run of 2026-09-21, on a thread that was not on Full. The eval set was
counted (`measure_eval_set`, 40 rows) and profiled, and the walk still stopped
at `S0_MODALITY_UNKNOWN`, telling the model to decide a fact "NOTHING in this
harness measures". `modality` and `task_family` are declared `source: derive`
- computed from data, never asked - and the rule that computes them from the
eval file (`full_defaults._from_the_eval_file`) only ran under Full. So on
every other permission a routing fact the harness could read off a file it had
just counted became a question for a model that had no tool to answer it.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import conductor, diagnosis, events  # noqa: E402
from app.tools import evidence  # noqa: E402
from app.tools.registry import REGISTRY  # noqa: E402


def _rows(folder: Path, name: str, rows: list[dict]) -> Path:
    path = folder / name
    path.write_bytes(("\n".join(json.dumps(row) for row in rows) + "\n").encode("utf-8"))
    return path


def _owner_rows() -> list[dict]:
    """Shaped like his ml-principles eval rows: an `input` and a JSON `expected`."""
    return [
        {
            "row_id": i,
            "task_type": "explain",
            "lane": "principles",
            "input": f"Why does a model overfit when the training set is tiny? ({i})",
            "expected": json.dumps(
                {
                    "task_type": ["explain", "compare", "debug"][i % 3],
                    "principles": ["bias variance", "regularisation"],
                    "summary": "A small set lets the model memorise noise instead of the signal.",
                }
            ),
            "rubric_keys": ["names the principle", "gives the mechanism"],
        }
        for i in range(40)
    ]


class ATextEvalSetSettlesItsModality(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(support.sandbox(self))

    def thread(self, permission: str) -> int:
        tid = int(events.create_thread(f"on {permission}")["id"])
        events.set_thread_permission(tid, permission)
        return tid

    def count(self, tid: int, path: Path) -> dict:
        """The conductor's own sequence: the call row, the call, the re-walk."""
        arguments = {"path": str(path)}
        events.append(
            "tool.call", {"id": "c1", "name": "measure_eval_set", "arguments": arguments},
            thread_id=tid,
        )
        result = REGISTRY.call(
            "measure_eval_set", arguments, actor=evidence.MODEL, thread_id=tid
        )
        self.assertTrue(result["ok"], result)
        standing = conductor._Standing(None, thread_id=tid)
        standing.note(result, tool_name="measure_eval_set")
        return standing.payload or {}

    def walk(self, tid: int) -> dict:
        return REGISTRY.call(
            "run_diagnosis", {"facts": {}}, actor=evidence.HARNESS, thread_id=tid
        )

    def test_on_ask_counting_the_eval_set_settles_modality_as_text(self) -> None:
        tid = self.thread("ask")
        standing = self.count(tid, _rows(self.root, "eval.jsonl", _owner_rows()))
        derived = {row["fact"]: row["value"] for row in standing.get("derived") or []}
        self.assertEqual(derived.get("modality"), "text")
        walked = self.walk(tid)
        self.assertEqual(walked["facts_used"]["modality"]["value"], "text")
        self.assertEqual(walked["fact_origins"]["modality"], diagnosis.DEFAULTED)

    def test_the_walk_never_asks_for_modality_once_the_file_is_counted(self) -> None:
        for permission in ("ask", "measure", "write", "full"):
            with self.subTest(permission=permission):
                tid = self.thread(permission)
                self.count(tid, _rows(self.root, f"eval-{permission}.jsonl", _owner_rows()))
                REGISTRY.call(
                    "state_facts", {"facts": {"target_score": 0.6}}, actor=evidence.USER,
                    thread_id=tid,
                )
                walked = self.walk(tid)
                self.assertNotEqual(walked["outcome"], "ACTION__NAME_THE_MODALITY", walked["next"])
                self.assertNotEqual((walked.get("next_step") or {}).get("fact"), "modality")

    def test_a_column_of_image_files_is_not_called_text(self) -> None:
        tid = self.thread("ask")
        rows = [{"input": f"img_{i}.png", "expected": f"cat_{i}.png"} for i in range(40)]
        self.count(tid, _rows(self.root, "images.jsonl", rows))
        walked = self.walk(tid)
        self.assertNotEqual((walked.get("facts_used") or {}).get("modality", {}).get("value"), "text")

    def test_a_person_who_said_otherwise_is_not_overruled(self) -> None:
        tid = self.thread("ask")
        REGISTRY.call(
            "state_facts", {"facts": {"modality": "code"}}, actor=evidence.USER, thread_id=tid
        )
        self.count(tid, _rows(self.root, "eval.jsonl", _owner_rows()))
        walked = self.walk(tid)
        self.assertEqual(walked["facts_used"]["modality"]["value"], "code")


if __name__ == "__main__":
    unittest.main()
