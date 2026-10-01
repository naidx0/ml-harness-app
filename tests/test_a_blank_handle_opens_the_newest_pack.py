"""`read_observation` with no handle opens the newest pack, behind MLH_OBS_FILL.

The journey A/B of 2026-09-24 (docs/score_rows/baseline-2026-09-24.md): the
model called `read_observation` with no arguments 16 times in three runs while
its thread held packed results. Off, nothing changes.
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

import support

from app import conductor, events, observations


def _a_pack(thread_id: int, handle: str) -> None:
    events.append(
        observations.PACKED_KIND,
        {"handle": handle, "name": "profile_dataset", "chars": 20_000, "why": "reduced"},
        thread_id=thread_id,
    )


class ABlankHandleTest(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)
        self.thread = int(events.create_thread("look at the data", None)["id"])

    def _fill(self, flag: str, arguments=None):
        with mock.patch.dict(os.environ, {"MLH_OBS_FILL": flag}):
            return conductor._fill_from_the_thread(
                "read_observation", arguments or {}, self.thread
            )

    def test_off_a_blank_handle_is_left_blank(self):
        _a_pack(self.thread, "obs:180")
        filled, said = self._fill("")
        self.assertEqual([], said)
        self.assertNotIn("handle", filled)

    def test_on_a_blank_handle_opens_the_newest_pack(self):
        _a_pack(self.thread, "obs:180")
        _a_pack(self.thread, "obs:186")
        filled, said = self._fill("1")
        self.assertEqual(["handle"], said)
        self.assertEqual("obs:186", filled["handle"])

    def test_on_a_handle_the_model_sent_is_its_own(self):
        _a_pack(self.thread, "obs:186")
        filled, said = self._fill("1", {"handle": "obs:180"})
        self.assertEqual([], said)
        self.assertEqual("obs:180", filled["handle"])

    def test_on_a_thread_with_no_pack_fills_nothing(self):
        filled, said = self._fill("1")
        self.assertEqual([], said)
        self.assertNotIn("handle", filled)

    def test_on_another_threads_pack_is_not_borrowed(self):
        other = int(events.create_thread("other", None)["id"])
        _a_pack(other, "obs:500")
        _filled, said = self._fill("1")
        self.assertEqual([], said)

    def test_the_person_is_told_where_it_came_from(self):
        self.assertEqual(
            conductor.FILLED_FROM_THE_LAST_PACK,
            conductor._the_fill_sentence("read_observation", ["handle"]),
        )


if __name__ == "__main__":
    unittest.main()
