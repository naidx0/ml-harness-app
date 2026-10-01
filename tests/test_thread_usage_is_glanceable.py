"""CS3: usage strip figures come from events, with provenance."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import contextwindow, events, usage  # noqa: E402


class UsageReadTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)

    def test_empty_thread_has_no_invented_totals(self) -> None:
        tid = events.create_thread("usage empty")["id"]
        out = usage.read(tid)
        self.assertEqual(out["thread"]["turn_count"], 0)
        self.assertIsNone(out["thread"]["latest_tokens"])
        self.assertEqual(out["thread"]["total_tool_calls"], 0)
        self.assertEqual(out["provenance"]["tokens"], "measured")

    def test_one_turn_rolls_up_tokens_calls_and_seconds(self) -> None:
        tid = events.create_thread("usage one")["id"]
        events.append(usage.TURN_STARTED, {"model": "x"}, thread_id=tid)
        events.append(
            contextwindow.KIND,
            {"total": 1200, "system": 400, "tools": 200, "history": 600, "window": 8192, "mode": "build"},
            thread_id=tid,
        )
        events.append("tool.call", {"name": "look_up"}, thread_id=tid)
        events.append("tool.call", {"name": "measure_baseline"}, thread_id=tid)
        events.append(events.END_KIND, {"seconds": 4.5, "rounds": 2}, thread_id=tid)

        out = usage.read(tid)
        self.assertEqual(out["thread"]["turn_count"], 1)
        self.assertEqual(out["thread"]["latest_tokens"], 1200)
        self.assertEqual(out["thread"]["total_tool_calls"], 2)
        self.assertEqual(out["thread"]["total_seconds"], 4.5)
        self.assertEqual(out["turns"][0]["tool_calls"], 2)
        self.assertEqual(out["provenance"]["seconds"], "measured")
        for key in ("tokens", "tool_calls", "seconds", "window"):
            self.assertIn(key, out["counted_by"])


if __name__ == "__main__":
    unittest.main()
