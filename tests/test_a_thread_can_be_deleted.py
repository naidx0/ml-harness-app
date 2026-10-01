"""Delete is the other door. Archive keeps the transcript; delete removes it.

Max, 2026-09-12: *"add a delete thread and project/file so that old projects
that people really don't work with aren't just infinitely archived adding
space, but they are deleted and removed."* `events.delete_thread` removes the
thread and every row keyed to it - the cascading tables through the schema,
the four bare `thread_id` tables by hand (`THREAD_TABLES_WITHOUT_CASCADE`),
the FTS index through its own trigger. `db.delete_project` does that for each
thread, then the project's memory and ledger, then the row, and refuses the
last live project for the reason `archive_project` does. Nothing on disk.
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
from app import db, events, memory, recall  # noqa: E402
from app.tools import context  # noqa: E402


def _count(table: str, column: str, value: int) -> int:
    with db.session() as connection:
        return connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (value,)
        ).fetchone()[0]


def _fts_hits(word: str) -> int:
    with db.session() as connection:
        return connection.execute(
            "SELECT COUNT(*) FROM messages_fts WHERE messages_fts MATCH ?", (word,)
        ).fetchone()[0]


class DeleteThreadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)
        self.project = db.create_project("Router", root_path=str(self.root / "router"))
        self.thread = int(events.create_thread("routing", project_id=self.project["id"])["id"])
        events.add_message(self.thread, "user", "carve the holdout from tickets.jsonl")
        events.add_message(self.thread, "assistant", "carved forty rows")
        events.append(
            "thread.plan_written", {"phases": 2}, project_id=self.project["id"], thread_id=self.thread
        )
        context.ensure_contexts_table()
        context.record_context(
            str(self.root / "tickets.jsonl"), "file", "data", "", thread_id=self.thread
        )
        recall.ensure_recall_index()
        with db.session() as connection:
            connection.execute(
                "INSERT INTO fact_evidence(thread_id, fact, value, origin, actor, how) "
                "VALUES (?, 'gpu', 'one card', 'tool', 'model', 'read')",
                (self.thread,),
            )

    def test_every_row_keyed_to_the_thread_goes_with_it(self):
        self.assertEqual(_count("messages", "thread_id", self.thread), 2)
        self.assertEqual(_count("contexts", "thread_id", self.thread), 1)
        self.assertEqual(_count("fact_evidence", "thread_id", self.thread), 1)
        self.assertGreaterEqual(_count("events", "thread_id", self.thread), 1)
        self.assertEqual(_fts_hits("holdout"), 1, "the FTS index sees the message before")

        out = events.delete_thread(self.thread)
        self.assertIsNotNone(out)
        self.assertEqual(out["thread"]["title"], "routing")
        self.assertEqual(out["removed"]["messages"], 2)
        self.assertEqual(out["removed"]["contexts"], 1)
        self.assertEqual(out["removed"]["fact_evidence"], 1)

        self.assertIsNone(events.get_thread(self.thread))
        for table in ("messages", "contexts", "events", "fact_evidence", "quarantined_facts"):
            self.assertEqual(_count(table, "thread_id", self.thread), 0, table)
        self.assertEqual(_fts_hits("holdout"), 0, "the FTS index forgets the message with it")

    def test_a_missing_thread_is_none(self):
        self.assertIsNone(events.delete_thread(99999))

    def test_the_other_threads_are_untouched(self):
        other = int(events.create_thread("other", project_id=self.project["id"])["id"])
        events.add_message(other, "user", "keep me")
        events.delete_thread(self.thread)
        self.assertEqual([m["content"] for m in events.messages_for(other)], ["keep me"])


class DeleteProjectTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)
        self.keep = db.default_project()
        (self.root / "old").mkdir()
        (self.root / "old" / "notes.txt").write_text("mine", encoding="utf-8")
        self.project = db.create_project("Old", root_path=str(self.root / "old"))
        self.threads = [
            int(events.create_thread(f"t{i}", project_id=self.project["id"])["id"])
            for i in range(3)
        ]
        for thread in self.threads:
            events.add_message(thread, "user", "hello")
        kept = memory.add(
            "project",
            "The router is minicpm5-hermes because it fits the card",
            project_id=self.project["id"],
        )
        self.assertTrue(kept.get("ok"), kept)
        events.append("project.root_set", {"root": "x"}, project_id=self.project["id"])

    def test_the_project_its_threads_and_its_memory_go_together(self):
        out = db.delete_project(self.project["id"])
        self.assertIsNotNone(out)
        self.assertEqual(out["removed"]["threads"], 3)
        self.assertEqual(out["removed"]["memory_entries"], 1)
        self.assertGreaterEqual(out["removed"]["events"], 1)
        self.assertEqual(
            [p["id"] for p in db.list_projects(include_archived=True)], [self.keep["id"]]
        )
        for thread in self.threads:
            self.assertIsNone(events.get_thread(thread))
            self.assertEqual(_count("messages", "thread_id", thread), 0)
        self.assertEqual(_count("memory_entries", "project_id", self.project["id"]), 0)
        self.assertEqual(_count("events", "project_id", self.project["id"]), 0)
        self.assertTrue(
            (self.root / "old" / "notes.txt").exists(), "the folder on disk is the person's"
        )

    def test_the_last_live_project_is_refused(self):
        db.delete_project(self.project["id"])
        with self.assertRaises(ValueError):
            db.delete_project(self.keep["id"])

    def test_an_archived_project_can_still_be_deleted(self):
        db.archive_project(self.project["id"])
        self.assertIsNotNone(db.delete_project(self.project["id"]))

    def test_a_missing_project_is_none(self):
        self.assertIsNone(db.delete_project(99999))


class OverHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)
        from app.main import app

        self.client = support.api_client(app)
        self.addCleanup(self.client.close)

    def kinds(self) -> list[str]:
        with db.session() as connection:
            return [row[0] for row in connection.execute("SELECT kind FROM events ORDER BY id")]

    def test_delete_thread_keeps_one_ledger_line_on_the_project(self):
        thread = self.client.post("/api/threads", json={"title": "gone"}).json()
        self.client.post(f"/api/threads/{thread['id']}/rename", json={"title": "gone soon"})
        resp = self.client.delete(f"/api/threads/{thread['id']}")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["deleted"], thread["id"])
        self.assertEqual(self.client.get(f"/api/threads/{thread['id']}").status_code, 404)
        self.assertIn("thread.deleted", self.kinds())
        with db.session() as connection:
            row = connection.execute(
                "SELECT thread_id, payload_json FROM events WHERE kind = 'thread.deleted'"
            ).fetchone()
        self.assertIsNone(row[0], "the event names no thread - it is gone")
        self.assertIn("gone soon", row[1])
        self.assertEqual(self.client.delete("/api/threads/99999").status_code, 404)

    def test_delete_project_and_the_last_one_is_refused(self):
        first = db.default_project()
        second = self.client.post("/api/projects", json={"name": "Second"}).json()
        self.client.post(
            "/api/threads", json={"title": "in second", "project_id": second["id"]}
        )
        resp = self.client.delete(f"/api/projects/{second['id']}")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["removed"]["threads"], 1)
        self.assertEqual(
            [p["id"] for p in self.client.get("/api/projects").json()], [first["id"]]
        )
        self.assertIn("project.deleted", self.kinds())
        refused = self.client.delete(f"/api/projects/{first['id']}")
        self.assertEqual(refused.status_code, 409)
        self.assertIn("last project", refused.json()["detail"])
        self.assertEqual(self.client.delete("/api/projects/99999").status_code, 404)


class AThreadsAttachmentsAreReadableTest(unittest.TestCase):
    """The line above the composer names the attached file without running a
    tool: `list_context` through the user door files a transcript row, and a
    row on every thread open is the spam the owner keeps naming. A GET."""

    def setUp(self) -> None:
        self.root = support.sandbox(self)
        from app.main import app

        self.client = support.api_client(app)
        self.addCleanup(self.client.close)

    def test_get_contexts_is_scoped_to_the_thread(self):
        mine = int(events.create_thread("mine")["id"])
        other = int(events.create_thread("other")["id"])
        context.ensure_contexts_table()
        context.record_context(str(self.root / "a.jsonl"), "file", "data", "", thread_id=mine)
        context.record_context(str(self.root / "b.jsonl"), "file", "data", "", thread_id=other)
        resp = self.client.get(f"/api/threads/{mine}/contexts")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual([Path(c["path"]).name for c in resp.json()["contexts"]], ["a.jsonl"])
        self.assertEqual(self.client.get("/api/threads/99999/contexts").status_code, 404)


if __name__ == "__main__":
    unittest.main()
