"""The event log, and the two properties that make it worth having.

A stream that cannot be replayed will lose exactly the message that mattered.
So the two things under test here are not "does it store rows":

1. **The autoincrement id IS the SSE event id.** One monotonic number across
   the whole database, so a client holding 412 can ask for 413 onwards without
   the server needing to remember anything about that client.
2. **`since` is strictly greater than.** `Last-Event-ID` is the id of the last
   frame the client *received*. Replaying it duplicates a token, and a
   duplicated token inside a streamed sentence is a defect the user can see.

Off-by-one in (2) is invisible to a test that only counts rows, which is why
the assertions below check *which* rows come back after a specific id rather
than how many.
"""

from __future__ import annotations

import json
import unittest

from app import events

import support


class EventLogTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)

    def test_ids_are_monotonic_across_scopes(self):
        thread = events.create_thread("t")
        first = events.append("chat.delta", {"text": "He"}, thread_id=thread["id"])
        second = events.append("chat.delta", {"text": "llo"}, thread_id=thread["id"])
        other = events.append("run.log", {"line": "unrelated"}, run_id=999)
        self.assertGreater(second["id"], first["id"])
        self.assertGreater(other["id"], second["id"])
        self.assertEqual(events.last_event_id(), other["id"])

    def test_since_is_strictly_greater_than(self):
        thread = events.create_thread("t")
        first = events.append("chat.delta", {"text": "He"}, thread_id=thread["id"])
        events.append("chat.delta", {"text": "llo"}, thread_id=thread["id"])

        everything = events.since(f"thread:{thread['id']}", 0)
        self.assertEqual([r["payload"]["text"] for r in everything], ["He", "llo"])

        after_first = events.since(f"thread:{thread['id']}", first["id"])
        self.assertEqual(
            [r["payload"]["text"] for r in after_first],
            ["llo"],
            "replaying the event the client already had duplicates a token",
        )

    def test_a_scope_only_sees_its_own_events(self):
        one = events.create_thread("one")
        two = events.create_thread("two")
        events.append("chat.delta", {"text": "a"}, thread_id=one["id"])
        events.append("chat.delta", {"text": "b"}, thread_id=two["id"])
        events.append("run.log", {"line": "c"}, run_id=7)

        self.assertEqual(
            [r["payload"]["text"] for r in events.since(f"thread:{one['id']}")], ["a"]
        )
        self.assertEqual(
            [r["payload"]["line"] for r in events.since("run:7")], ["c"]
        )
        self.assertEqual(events.since("project:1"), [])

    def test_an_unknown_scope_is_an_error_not_an_empty_result(self):
        for bad in ("dataset:1", "thread", "thread:abc", "", ":", "thread:"):
            with self.subTest(scope=bad):
                with self.assertRaises(ValueError):
                    events.since(bad)

    def test_the_payload_round_trips_as_a_dict(self):
        thread = events.create_thread("t")
        payload = {"nested": {"a": [1, 2, 3]}, "unicode": "café", "null": None}
        written = events.append("tool.result", payload, thread_id=thread["id"])
        self.assertEqual(written["payload"], payload)
        self.assertEqual(events.since(f"thread:{thread['id']}")[0]["payload"], payload)

    def test_append_returns_the_committed_row(self):
        """Nothing may stream that was not first durably written.

        `append` returning a row with an id is what lets the Conductor stream
        the value it got back rather than the value it was about to write.
        """
        thread = events.create_thread("t")
        written = events.append("chat.delta", {"text": "x"}, thread_id=thread["id"])
        self.assertIn("id", written)
        self.assertGreater(written["id"], 0)
        replayed = events.since(f"thread:{thread['id']}", written["id"] - 1)
        self.assertEqual(replayed[0]["id"], written["id"])

    def test_limit_bounds_a_replay(self):
        thread = events.create_thread("t")
        for index in range(10):
            events.append("chat.delta", {"text": str(index)}, thread_id=thread["id"])
        page = events.since(f"thread:{thread['id']}", 0, limit=3)
        self.assertEqual([r["payload"]["text"] for r in page], ["0", "1", "2"])
        rest = events.since(f"thread:{thread['id']}", page[-1]["id"], limit=3)
        self.assertEqual([r["payload"]["text"] for r in rest], ["3", "4", "5"])

    def test_last_event_id_is_zero_on_a_fresh_database(self):
        self.assertEqual(events.last_event_id(), 0)

    def test_a_frame_carries_its_id_its_kind_and_its_payload(self):
        thread = events.create_thread("t")
        row = events.append("chat.delta", {"text": "hi"}, thread_id=thread["id"])
        frame = events.frame(row)
        self.assertIn(f"id: {row['id']}\n", frame)
        self.assertIn("event: chat.delta\n", frame)
        self.assertTrue(frame.endswith("\n\n"))
        data = [line for line in frame.splitlines() if line.startswith("data: ")][0]
        self.assertEqual(json.loads(data[6:]), {"text": "hi"})


class TranscriptTest(unittest.TestCase):
    """Threads and messages: the artifact the user keeps."""

    def setUp(self):
        self.root = support.sandbox(self)

    def test_a_transcript_reads_oldest_first_and_a_rail_reads_newest_first(self):
        first = events.create_thread("first thread")
        second = events.create_thread("second thread")
        events.add_message(first["id"], "user", "hello")
        events.add_message(first["id"], "assistant", "hi back")

        messages = events.messages_for(first["id"])
        self.assertEqual([m["role"] for m in messages], ["user", "assistant"])
        self.assertEqual(messages[0]["content"], "hello")

        self.assertEqual(
            [t["id"] for t in events.list_threads()], [second["id"], first["id"]]
        )

    def test_a_message_on_a_missing_thread_returns_none(self):
        self.assertIsNone(events.add_message(99999, "user", "orphan"))

    def test_get_thread_misses_cleanly(self):
        self.assertIsNone(events.get_thread(99999))

    def test_tool_calls_are_persisted_with_the_assistant_message(self):
        thread = events.create_thread("t")
        payload = json.dumps([{"id": "c1", "name": "list_runs", "arguments": {}}])
        events.add_message(thread["id"], "assistant", "", payload)
        stored = events.messages_for(thread["id"])[0]
        self.assertEqual(json.loads(stored["tool_calls_json"])[0]["name"], "list_runs")


if __name__ == "__main__":
    unittest.main()
