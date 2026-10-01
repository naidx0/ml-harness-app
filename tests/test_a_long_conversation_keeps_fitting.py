"""A long conversation is compacted, not refused - and a summary cannot mint a number.

Hermes' context compressor, rebuilt (see `app/compaction.py`). No model is
called here: a fake adapter returns a canned checkpoint, so every case is
about the split, the record, the framing, the iteration and the sentry.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class _Delta:
    def __init__(self, kind, text="", detail=""):
        self.kind, self.text, self.detail = kind, text, detail


class _Adapter:
    """Answers every summary prompt with `answer`; remembers what it was asked."""

    def __init__(self, answer: str):
        self.answer = answer
        self.prompts: list[str] = []

    def stream(self, messages, tools, secret=None):
        self.prompts.append(messages[-1]["content"])
        yield _Delta("text", self.answer)
        yield _Delta("end")


class _Failing:
    def stream(self, messages, tools, secret=None):
        yield _Delta("error", detail="the model is gone")


class _Sandboxed(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._old = os.environ.get("ML_HARNESS_DB")
        os.environ["ML_HARNESS_DB"] = str(Path(self._tmp.name) / "compaction.db")
        from app import db
        self._old_path = db.DB_PATH
        db.DB_PATH = Path(os.environ["ML_HARNESS_DB"])
        db.init_db()

    def tearDown(self) -> None:
        from app import db
        db.DB_PATH = self._old_path
        if self._old is None:
            os.environ.pop("ML_HARNESS_DB", None)
        else:
            os.environ["ML_HARNESS_DB"] = self._old

    def a_long_thread(self, turns: int = 16, words: int = 220) -> int:
        """Past the unknown-window floor: ~16 x 1,600 characters, ~6,400 tokens."""
        from app import events
        thread = events.create_thread("long")["id"]
        events.add_message(thread, "user", "GOAL: train a router for the tickets on this machine.")
        for i in range(turns):
            events.add_message(thread, "assistant", f"turn {i} answer " + ("detail " * words))
            events.add_message(thread, "user", f"turn {i} follow-up question " + ("more " * (words // 4)))
        return int(thread)


SUMMARY = """## Active Task
The person asked which adapter to try next.

## Completed Actions
1. read_the_standing_constraints - none found.
2. inspect_hardware - the card was read (measured).

## Key Decisions
We chose granite4 for the router because it fits the card.

## Critical Context
Your baseline score is 0.82 on the eval set.
Your eval size is 40,000 rows."""


class TheBudgetTest(unittest.TestCase):
    def test_the_transcript_budget_is_a_share_of_the_window_or_a_floor(self):
        from app import compaction
        self.assertEqual(compaction.transcript_budget(None), compaction.TRANSCRIPT_FLOOR)
        self.assertEqual(compaction.transcript_budget(65_536), int(65_536 * compaction.TRANSCRIPT_SHARE))
        self.assertGreaterEqual(compaction.transcript_budget(4_096), compaction.TRANSCRIPT_FLOOR // 2)


class TheSplitTest(_Sandboxed):
    def test_head_is_the_goal_tail_holds_the_latest_user_message(self):
        from app import compaction, events
        thread = self.a_long_thread()
        rows = events.messages_for(thread)
        head, middle, tail = compaction.split(rows, 1000, None)
        self.assertEqual([r["content"][:4] for r in head], ["GOAL"])
        self.assertTrue(any(r["role"] == "user" for r in tail))
        self.assertEqual(tail[-1]["id"], rows[-1]["id"])
        self.assertGreaterEqual(len(tail), compaction.MIN_TAIL_MESSAGES)
        self.assertTrue(middle)
        ids = [r["id"] for r in head + middle + tail]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(ids), len(rows))

    def test_a_second_split_starts_after_what_was_already_covered(self):
        from app import compaction, events
        thread = self.a_long_thread()
        rows = events.messages_for(thread)
        _, middle, _ = compaction.split(rows, 1000, None)
        through = middle[-1]["id"]
        head2, middle2, _ = compaction.split(rows, 1000, through)
        self.assertEqual(head2, [])
        self.assertTrue(all(r["id"] > through for r in middle2))


class TheRecordTest(_Sandboxed):
    def test_nothing_happens_under_budget(self):
        from app import compaction, events
        thread = events.create_thread("short")["id"]
        events.add_message(thread, "user", "hello")
        self.assertIsNone(compaction.compact(thread, _Adapter(SUMMARY), window=65_536))
        self.assertIsNone(compaction.latest(thread))

    def test_over_budget_the_middle_becomes_a_checkpoint_event_and_messages_are_untouched(self):
        from app import compaction, events
        thread = self.a_long_thread()
        before = len(events.messages_for(thread))
        record = compaction.compact(thread, _Adapter(SUMMARY), window=None)
        self.assertIsNotNone(record)
        self.assertEqual(len(events.messages_for(thread)), before, "messages were edited")
        self.assertEqual(record["iteration"], 1)
        self.assertLess(record["tokens_after"], record["tokens_before"])
        self.assertIn("## Key Decisions", record["summary"])
        self.assertEqual(compaction.latest(thread)["through_message_id"], record["through_message_id"])

    def test_the_conversation_a_turn_sends_is_head_summary_tail(self):
        from app import compaction, events
        thread = self.a_long_thread()
        compaction.compact(thread, _Adapter(SUMMARY), window=None)
        sent, asked = compaction.conversation_for(thread)
        self.assertTrue(sent[0]["content"].startswith("GOAL"))
        self.assertTrue(sent[1]["content"].startswith(compaction.SUMMARY_PREFIX))
        self.assertIn(compaction.SUMMARY_END, sent[1]["content"])
        self.assertEqual(sent[2]["role"], "assistant")
        self.assertEqual(sent[-1]["role"], "user")
        self.assertEqual(asked, events.messages_for(thread)[-1]["content"])
        rows = events.messages_for(thread)
        self.assertLess(len(sent), len(rows))

    def test_the_framing_keeps_memory_authoritative_and_tools_active(self):
        from app import compaction
        self.assertIn("memory note in the system prompt stays authoritative", compaction.SUMMARY_PREFIX)
        self.assertIn("tools remain fully active", compaction.SUMMARY_PREFIX)
        self.assertIn("ledger, not the summary, holds the measurements", compaction.SUMMARY_PREFIX)

    def test_a_second_compaction_updates_the_previous_summary(self):
        from app import compaction, events
        thread = self.a_long_thread()
        adapter = _Adapter(SUMMARY)
        first = compaction.compact(thread, adapter, window=None)
        self.assertIsNotNone(first)
        for i in range(14):
            events.add_message(thread, "assistant", f"later {i} " + ("words " * 220))
            events.add_message(thread, "user", f"later question {i} " + ("more " * 40))
        second = compaction.compact(thread, adapter, window=None)
        self.assertIsNotNone(second)
        self.assertEqual(second["iteration"], 2)
        self.assertGreater(second["through_message_id"], first["through_message_id"])
        self.assertIn("PREVIOUS SUMMARY", adapter.prompts[-1])
        self.assertIn("NEW TURNS TO INCORPORATE", adapter.prompts[-1])
        self.assertGreater(second["messages_summarised"], first["messages_summarised"])

    def test_a_summariser_that_fails_leaves_the_thread_as_it_was_and_says_so(self):
        from app import compaction, events
        thread = self.a_long_thread()
        self.assertIsNone(compaction.compact(thread, _Failing(), window=None))
        self.assertIsNone(compaction.latest(thread))
        kinds = [r["kind"] for r in events.since(f"thread:{thread}", limit=1000)]
        self.assertIn("thread.compaction_failed", kinds)
        sent, _ = compaction.conversation_for(thread)
        self.assertEqual(len(sent), len(events.messages_for(thread)))


class ASummaryCannotMintANumberTest(_Sandboxed):
    def test_lines_the_sentry_refutes_are_dropped_and_counted(self):
        from app import compaction, provenance
        thread = self.a_long_thread()
        ground = provenance.Ground(thread)
        reads = lambda line: provenance.reads_as_a_measurement(line, ground)  # noqa: E731
        record = compaction.compact(thread, _Adapter(SUMMARY), window=None, reads=reads)
        # The same reader the wall uses, so the same sentences: a reading of a
        # declared fact that nothing in this thread produced is dropped; a
        # decision with no figure is kept; the section stays.
        self.assertNotIn("0.82", record["summary"])
        self.assertIn("granite4", record["summary"])
        self.assertIn("## Critical Context", record["summary"])
        self.assertGreaterEqual(record["lines_dropped_by_the_sentry"], 1)
        self.assertTrue(record["sentry_ran"])

    def test_without_a_ground_nothing_is_dropped_and_the_record_says_the_sentry_did_not_run(self):
        from app import compaction
        thread = self.a_long_thread()
        record = compaction.compact(thread, _Adapter(SUMMARY), window=None)
        self.assertIn("0.82", record["summary"])
        self.assertFalse(record["sentry_ran"])

    def test_the_prompt_asks_for_origin_words_and_forbids_secrets(self):
        from app import compaction
        prompt = compaction.summary_prompt([{"role": "user", "content": "x", "id": 1}], None, 400)
        self.assertIn("origin word", prompt)
        self.assertIn("[REDACTED]", prompt)
        self.assertIn("## Active Task", prompt)


if __name__ == "__main__":
    unittest.main()
