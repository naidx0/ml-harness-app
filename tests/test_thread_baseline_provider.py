"""AU3: thread baseline_provider_id steers measure_baseline."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import events, main  # noqa: E402


class ThreadBaselineProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        self.client = support.api_client(main.app)

    def test_set_and_read_baseline_provider(self) -> None:
        tid = events.create_thread("baseline bind")["id"]
        row = events.set_thread_baseline_provider(tid, 42)
        self.assertEqual(row.get("baseline_provider_id"), 42)
        again = events.get_thread(tid)
        self.assertEqual(again.get("baseline_provider_id"), 42)

    def test_api_sets_baseline_provider(self) -> None:
        tid = events.create_thread("baseline api")["id"]
        answered = self.client.post(
            f"/api/threads/{tid}/baseline_provider",
            json={"provider_id": 7},
        )
        self.assertEqual(answered.status_code, 200)
        self.assertEqual(answered.json().get("baseline_provider_id"), 7)
        cleared = self.client.post(
            f"/api/threads/{tid}/baseline_provider",
            json={"provider_id": None},
        )
        self.assertEqual(cleared.status_code, 200)
        self.assertIsNone(cleared.json().get("baseline_provider_id"))


if __name__ == "__main__":
    unittest.main()
