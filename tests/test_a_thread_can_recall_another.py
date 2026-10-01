"""A conversation can find what a sibling conversation settled.

Max, 2026-09-11: *"where is my consistent memory system? it is rescanning
every time"* - and, having read Hermes' `session_search`: *"implement all 3
exact same systems in ours."* This is the first: one tool, three shapes,
no model in the loop, every result an actual message from the database.
See `app/recall.py`.

Each shape has a case that produces only it; the scoping and the index's
self-healing have theirs.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class _Sandboxed(unittest.TestCase):
    """A fresh database per test, so nothing here reads the owner's threads."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._old = os.environ.get("ML_HARNESS_DB")
        os.environ["ML_HARNESS_DB"] = str(Path(self._tmp.name) / "recall.db")
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

    def a_thread(self, title: str, lines: list[tuple[str, str]], project_id: int | None = None) -> int:
        from app import events
        thread = events.create_thread(title, project_id=project_id)
        for role, text in lines:
            events.add_message(thread["id"], role, text)
        return int(thread["id"])

    def a_project(self, name: str) -> int:
        from app import db
        return int(db.create_project(name, None)["id"])


class DiscoverTest(_Sandboxed):
    def test_a_sibling_thread_is_found_by_what_it_said(self):
        from app import recall
        project = self.a_project("support")
        earlier = self.a_thread(
            "which model",
            [
                ("user", "which model should we use for the tickets"),
                ("assistant", "We settled on granite4 for the ticket router; it fits the card."),
                ("user", "good"),
            ],
            project_id=project,
        )
        now = self.a_thread("later", [("user", "remind me")], project_id=project)
        found = recall.discover("ticket router model", project_id=project, this_thread=now)
        self.assertTrue(found["ok"], found)
        self.assertEqual([c["thread_id"] for c in found["conversations"]], [earlier])
        hit = found["conversations"][0]
        self.assertFalse(hit["this_conversation"])
        # bm25 may rank the short question above the long answer; the answer
        # is in the window either way, which is what the window is for.
        self.assertIn(
            "granite4",
            hit["hit"]["snippet"] + " ".join(m["text"] for m in hit["around"]),
        )
        self.assertEqual(hit["opening"][0]["text"], "which model should we use for the tickets")
        self.assertEqual(hit["latest"][-1]["text"], "good")
        self.assertTrue(any(m["role"] == "assistant" for m in hit["around"]))

    def test_one_entry_per_conversation_however_often_it_said_the_word(self):
        from app import recall
        project = self.a_project("p")
        chatty = self.a_thread(
            "chatty", [("user", "baseline " + str(i)) for i in range(12)], project_id=project
        )
        quiet = self.a_thread("quiet", [("assistant", "the baseline was 0.62")], project_id=project)
        found = recall.discover("baseline", project_id=project, limit=5)
        ids = [c["thread_id"] for c in found["conversations"]]
        self.assertEqual(sorted(ids), sorted([chatty, quiet]))
        self.assertEqual(len(ids), len(set(ids)))

    def test_the_calling_conversation_is_marked_as_itself(self):
        from app import recall
        project = self.a_project("p")
        here = self.a_thread("here", [("user", "we chose the smaller adapter")], project_id=project)
        found = recall.discover("smaller adapter", project_id=project, this_thread=here)
        self.assertTrue(found["conversations"][0]["this_conversation"])

    def test_another_project_is_not_searched_unless_asked(self):
        from app import recall
        mine = self.a_project("mine")
        theirs = self.a_project("theirs")
        self.a_thread("theirs", [("user", "the eval set has forty rows")], project_id=theirs)
        self.assertEqual(recall.discover("eval set rows", project_id=mine)["count"], 0)
        self.assertEqual(recall.discover("eval set rows", project_id=mine, scope="all")["count"], 1)

    def test_a_query_written_in_fts_syntax_does_not_crash_it(self):
        from app import recall
        project = self.a_project("p")
        self.a_thread("t", [("user", "the design model")], project_id=project)
        for hostile in ('design AND "', "model:*", "NOT design", "(design", 'design "model'):
            with self.subTest(query=hostile):
                out = recall.discover(hostile, project_id=project)
                self.assertTrue(out["ok"], out)

    def test_all_the_words_first_then_any_of_them(self):
        """Hermes matches every term; this falls back to any term rather than
        answering nothing, and SAYS it did."""
        from app import recall
        project = self.a_project("p")
        self.a_thread("t", [("user", "we carved the eval set")], project_id=project)
        strict = recall.discover("carved eval", project_id=project)
        self.assertNotIn("any of these words", strict["matched"])
        loose = recall.discover("carved zebra", project_id=project)
        self.assertEqual(loose["count"], 1)
        self.assertIn("any of these words", loose["matched"])

    def test_an_empty_query_is_refused_not_searched(self):
        from app import recall
        self.assertFalse(recall.discover("   ")["ok"])

    def test_the_result_says_its_numbers_are_quotations(self):
        from app import recall
        project = self.a_project("p")
        self.a_thread("t", [("assistant", "your VRAM is 8 GB")], project_id=project)
        self.assertIn("measured then", recall.discover("VRAM", project_id=project)["provenance"])


class ScrollTest(_Sandboxed):
    def test_a_window_is_centred_on_the_anchor_and_says_how_to_move(self):
        from app import events, recall
        thread = self.a_thread("long", [("user", f"line {i}") for i in range(20)])
        ids = [m["id"] for m in events.messages_for(thread)]
        out = recall.scroll(thread, ids[10], window=2)
        self.assertTrue(out["ok"])
        self.assertEqual([m["text"] for m in out["messages"]], [f"line {i}" for i in range(8, 13)])
        self.assertEqual(out["first_id"], ids[8])
        self.assertEqual(out["last_id"], ids[12])
        again = recall.scroll(thread, out["last_id"], window=2)
        self.assertEqual(again["messages"][0]["text"], "line 10")

    def test_a_message_from_another_thread_is_not_an_anchor(self):
        from app import events, recall
        a = self.a_thread("a", [("user", "one")])
        b = self.a_thread("b", [("user", "two")])
        foreign = events.messages_for(b)[0]["id"]
        self.assertEqual(recall.scroll(a, foreign)["error"], "no_such_message")

    def test_no_such_thread(self):
        from app import recall
        self.assertEqual(recall.scroll(99_999, 1)["error"], "no_such_thread")


class BrowseTest(_Sandboxed):
    def test_recent_conversations_newest_first_with_what_they_opened_on(self):
        from app import recall
        project = self.a_project("p")
        self.a_thread("first", [("user", "the first ask")], project_id=project)
        second = self.a_thread("second", [("user", "the second ask")], project_id=project)
        out = recall.browse(project_id=project, this_thread=second)
        self.assertEqual(out["count"], 2)
        titles = [c["title"] for c in out["conversations"]]
        self.assertEqual(set(titles), {"first", "second"})
        by_title = {c["title"]: c for c in out["conversations"]}
        self.assertEqual(by_title["first"]["opened_with"], "the first ask")
        self.assertTrue(by_title["second"]["this_conversation"])
        self.assertEqual(by_title["first"]["messages"], 1)


class TheIndexHealsTest(_Sandboxed):
    def test_messages_written_before_the_index_existed_are_searchable(self):
        """A database that predates recall gets the index on first use, back-
        filled - the `contexts` rule: no migration for somebody to forget."""
        from app import db, recall
        thread = self.a_thread("old", [("user", "written before any index")])
        with db.session() as connection:
            self.assertIsNone(
                connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE name = 'messages_fts'"
                ).fetchone()
            )
        self.assertEqual(recall.discover("before index", scope="all")["count"], 1)
        # And what is written AFTER is indexed by the trigger, not a rebuild.
        self.a_thread("new", [("user", "written after the index")])
        self.assertEqual(recall.discover("after index", scope="all")["count"], 1)
        self.assertEqual(recall.discover("before index", scope="all")["conversations"][0]["thread_id"], thread)


class TheToolIsOneShapeTest(_Sandboxed):
    def test_the_three_shapes_through_the_registry(self):
        from app.tools import REGISTRY, evidence
        project = self.a_project("p")
        earlier = self.a_thread("earlier", [("assistant", "we ruled out renting a GPU")], project_id=project)
        here = self.a_thread("here", [("user", "again?")], project_id=project)
        found = REGISTRY.call("recall", {"query": "renting GPU"}, actor=evidence.MODEL, thread_id=here)
        self.assertTrue(found["ok"], found)
        self.assertEqual(found["conversations"][0]["thread_id"], earlier)
        self.assertEqual(found["scope"], "this project")
        message_id = found["conversations"][0]["hit"]["message_id"]
        scrolled = REGISTRY.call(
            "recall", {"in_thread": earlier, "around_message_id": message_id},
            actor=evidence.MODEL, thread_id=here,
        )
        self.assertTrue(scrolled["ok"], scrolled)
        self.assertEqual(scrolled["thread_id"], earlier)
        browsed = REGISTRY.call("recall", {}, actor=evidence.MODEL, thread_id=here)
        self.assertEqual(browsed["count"], 2)

    def test_a_thread_id_the_model_invents_does_not_change_the_scope(self):
        """The registry fills `thread_id` from the call site over anything sent;
        the scroll target is `in_thread` for exactly that reason."""
        from app.tools import REGISTRY, evidence
        project = self.a_project("p")
        here = self.a_thread("here", [("user", "hello")], project_id=project)
        other = self.a_project("other")
        elsewhere = self.a_thread("elsewhere", [("user", "hello there")], project_id=other)
        out = REGISTRY.call("recall", {"query": "hello", "thread_id": elsewhere}, actor=evidence.MODEL, thread_id=here)
        self.assertEqual([c["thread_id"] for c in out["conversations"]], [here])

    def test_it_is_offered_in_plan_mode(self):
        from app import modes
        self.assertIn("recall", modes.PLAN_TOOLS)


if __name__ == "__main__":
    unittest.main()
