"""Which conversations are working, and a replay that is not three thousand frames.

Max, 2026-09-13: *"on the left chat side we should have it so you can
actually see which sessions are running"*, and *"when I launch the app and
open a chat it loads all the tokens and conversations from scratch... if we
can fix that and remove latency, that'd be really cool."*

`app/activity.py` answers the first off the event log - true for work another
window started. `events.fold_replay` answers the second: MEASURED on his
database, the busiest thread holds 3,294 events and 3,258 of them are single
token deltas, replayed as three thousand frames on every open.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import activity, events, longrun  # noqa: E402


class FoldReplayTest(unittest.TestCase):
    def rows(self, *kinds_and_text):
        out = []
        for index, (kind, payload) in enumerate(kinds_and_text, start=1):
            out.append({"id": index, "kind": kind, "payload": dict(payload)})
        return out

    def test_adjacent_deltas_become_one_row_with_the_last_id(self):
        rows = self.rows(
            ("turn.started", {}),
            ("chat.delta", {"text": "Hel"}),
            ("chat.delta", {"text": "lo "}),
            ("chat.delta", {"text": "there"}),
            ("stream.end", {"ending": "answered"}),
        )
        folded = events.fold_replay(rows)
        self.assertEqual([row["kind"] for row in folded], ["turn.started", "chat.delta", "stream.end"])
        self.assertEqual(folded[1]["payload"]["text"], "Hello there")
        self.assertEqual(folded[1]["id"], 4, "the id is the last of the run, which is what a client resumes from")
        self.assertEqual(folded[-1]["id"], 5)

    def test_the_text_is_identical_and_nothing_else_is_touched(self):
        rows = self.rows(
            ("chat.delta", {"text": "a"}),
            ("tool.call", {"name": "x"}),
            ("chat.delta", {"text": "b"}),
            ("chat.delta", {"text": "c"}),
        )
        folded = events.fold_replay(rows)
        self.assertEqual([row["kind"] for row in folded], ["chat.delta", "tool.call", "chat.delta"])
        self.assertEqual(
            "".join(r["payload"].get("text", "") for r in folded),
            "".join(r["payload"].get("text", "") for r in rows),
        )

    def test_two_voices_never_become_one_row(self):
        """A harness sentence and the model's own words are different rows,
        whatever their order - the transcript draws them differently."""
        rows = self.rows(
            ("chat.delta", {"text": "mine"}),
            ("chat.delta", {"text": "theirs", "written_by": "harness"}),
            ("chat.delta", {"text": " more", "written_by": "harness"}),
        )
        folded = events.fold_replay(rows)
        self.assertEqual(len(folded), 2)
        self.assertEqual(folded[1]["payload"]["text"], "theirs more")

    def test_the_original_rows_are_not_mutated(self):
        rows = self.rows(("chat.delta", {"text": "a"}), ("chat.delta", {"text": "b"}))
        events.fold_replay(rows)
        self.assertEqual(rows[0]["payload"]["text"], "a", "the caller's rows are theirs")


class ActivityTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        self.thread = int(events.create_thread("t", mode="build")["id"])

    def test_a_turn_that_started_and_has_not_ended_is_working(self):
        self.assertEqual(activity.read()["threads"], [])
        events.append("turn.started", {}, thread_id=self.thread)
        found = activity.read()["threads"]
        self.assertEqual([row["thread_id"] for row in found], [self.thread])
        self.assertTrue(found[0]["working"])
        events.append("stream.end", {"ending": "answered"}, thread_id=self.thread)
        self.assertEqual(activity.read()["threads"], [], "a turn that ended is not work")

    def test_it_carries_what_the_last_prompt_cost(self):
        events.append("turn.context", {"total": 21084, "window": 131072}, thread_id=self.thread)
        events.append("turn.started", {}, thread_id=self.thread)
        found = activity.read()["threads"][0]
        self.assertEqual(found["tokens"], 21084)
        self.assertEqual(found["window"], 131072)

    def test_a_run_shows_even_with_no_turn_in_flight(self):
        """A run between turns is still work, and the rail should say so."""
        events.set_thread_plan(self.thread, "## Phase 1\n- [ ] Do the thing\n")
        longrun.ensure_table()
        longrun.start(self.thread, background=False, cap=1, turn=lambda tid: iter(()))
        longrun._write(self.thread, state=longrun.RUNNING)
        found = activity.read()["threads"]
        self.assertEqual([row["thread_id"] for row in found], [self.thread])
        self.assertIsNotNone(found[0]["run"])
        self.assertEqual(found[0]["run"]["state"], longrun.RUNNING)

    def test_a_turn_from_before_this_engine_started_is_not_working(self):
        """MEASURED: a thread whose run was killed an hour earlier still had a
        `turn.started` with no end, and the first cut of this called it live
        forever. A turn is streamed by THIS process; one older than the
        process cannot be in flight."""
        events.append("turn.started", {}, thread_id=self.thread)
        from app import db

        with db.session() as connection:
            connection.execute(
                "UPDATE events SET ts = '2000-01-01 00:00:00' WHERE kind = 'turn.started'"
            )
        self.assertEqual(activity.read()["threads"], [])


class OverHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        from app.main import app

        self.client = support.api_client(app)
        self.addCleanup(self.client.close)

    def test_the_route_answers(self):
        got = self.client.get("/api/activity")
        self.assertEqual(got.status_code, 200, got.text)
        self.assertEqual(got.json(), {"threads": [], "count": 0})


if __name__ == "__main__":
    unittest.main()
