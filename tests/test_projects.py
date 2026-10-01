"""`projects`, and the promise that a thread always has one.

`docs/ARCHITECTURE.md` makes a project the root of the data model. It had never
been built, which is exactly why the rail is a flat list of threads where Codex
has folders.

Two things are worth testing and only one of them is "the table exists".

**`default_project()` must return the same project every time.** Calling it
twice and getting two projects called `Default` is not a cosmetic bug: threads
created before the second call and threads created after it would be in
different folders, and nobody would notice for a week, by which point the rail
is full of empty duplicates.

**A thread that existed before projects did must end up somewhere.** The
migration backfills it into a project named `Default`. The test that matters is
the one below that builds a database in the *old* shape - a `threads` table
with no `project_id` at all, exactly what `app/events.py` created before the
fold - migrates it, and asserts that nothing is left homeless. A nullable
foreign key that nothing fills in is how "projects exist" becomes true in the
schema and false in the product.
"""

from __future__ import annotations

import sqlite3
import unittest

from app import db, events, migrations

import support


class ProjectsTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)

    def test_the_default_project_is_one_project(self):
        """Step 1.3's acceptance, with the version literal made current.

        The step asserts `migrate() == 3` because it was written when the list
        ended at 3. Everything else is the step's own lines.
        """
        self.assertEqual(migrations.migrate(), migrations.MIGRATIONS[-1][0])
        p = db.default_project()
        self.assertEqual(p["name"], "Default")
        self.assertEqual(db.default_project()["id"], p["id"])
        self.assertEqual(len(db.list_projects()), 1)
        q = db.create_project("Second", "/tmp/x")
        self.assertEqual(db.default_project()["id"], p["id"])
        self.assertEqual(db.get_project(q["id"])["root_path"], "/tmp/x")

    def test_a_fresh_database_has_no_project_until_something_needs_one(self):
        """The migration must not invent a row on an empty database.

        `tests/test_empty_state_all_helpers.py` asserts that no reader in
        `db.py` returns rows from nothing, and `list_projects` is one. The
        `Default` row is created by migration 4 only when there are threads to
        put in it, and by `default_project()` otherwise.
        """
        self.assertEqual(db.list_projects(), [])

    def test_portal_is_the_only_thing_that_differs_between_the_products(self):
        consumer = db.create_project("c")
        enterprise = db.create_project("e", None, "enterprise")
        self.assertEqual(consumer["portal"], "consumer")
        self.assertEqual(enterprise["portal"], "enterprise")
        with self.assertRaises(ValueError):
            db.create_project("neither", None, "freemium")

    def test_rename_and_archive(self):
        first = db.create_project("first")
        second = db.create_project("second")
        self.assertEqual(db.rename_project(first["id"], "renamed")["name"], "renamed")
        self.assertIsNone(db.rename_project(99999, "nobody"))

        archived = db.archive_project(second["id"])
        self.assertIsNotNone(archived["archived_at"])
        self.assertEqual([p["id"] for p in db.list_projects()], [first["id"]])
        self.assertEqual(len(db.list_projects(include_archived=True)), 2)
        self.assertIsNone(db.archive_project(99999))

    def test_the_last_project_cannot_be_archived(self):
        """Archiving it would strand every thread in it behind an empty rail.

        `default_project()` mints a fresh `Default` when no live project
        remains, so the next thread would land somewhere the user cannot see
        the old ones from. A refusal with a reason beats a silent surprise.
        """
        only = db.default_project()
        with self.assertRaises(ValueError):
            db.archive_project(only["id"])
        self.assertIsNone(db.get_project(only["id"])["archived_at"])

    def test_a_thread_always_belongs_to_a_project(self):
        thread = events.create_thread("first thread")
        self.assertEqual(thread["project_id"], db.default_project()["id"])

        other = db.create_project("other")
        moved = events.move_thread(thread["id"], other["id"])
        self.assertEqual(moved["project_id"], other["id"])
        self.assertEqual(
            [t["id"] for t in events.list_threads(project_id=other["id"])],
            [thread["id"]],
        )
        self.assertEqual(events.list_threads(project_id=db.default_project()["id"]), [])

    def test_a_thread_cannot_be_moved_to_a_project_that_is_not_there(self):
        """The foreign key is real, not decorative."""
        thread = events.create_thread("t")
        with self.assertRaises(sqlite3.IntegrityError):
            events.move_thread(thread["id"], 99999)

    def test_rename_archive_and_the_missing_thread(self):
        thread = events.create_thread("t")
        self.assertEqual(events.rename_thread(thread["id"], "new")["title"], "new")
        self.assertIsNotNone(events.archive_thread(thread["id"])["archived_at"])
        self.assertEqual(events.list_threads(), [])
        self.assertEqual(len(events.list_threads(include_archived=True)), 1)
        self.assertIsNone(events.rename_thread(99999, "x"))
        self.assertIsNone(events.archive_thread(99999))
        self.assertIsNone(events.move_thread(99999, db.default_project()["id"]))

    def test_archiving_a_thread_deletes_nothing(self):
        """The transcript is the artifact. Archiving is not deletion."""
        thread = events.create_thread("t")
        events.add_message(thread["id"], "user", "hello")
        events.archive_thread(thread["id"])
        self.assertEqual(
            [m["content"] for m in events.messages_for(thread["id"])], ["hello"]
        )

    def test_threads_written_before_projects_existed_get_a_home(self):
        """The migration, run forward on a database in the old shape.

        This is the fixture that matters: `threads` exactly as `app/events.py`
        created it before the fold - no `project_id`, no `archived_at` - with
        rows in it and messages hanging off them.
        """
        db.DB_PATH = self.root / "pre_projects.db"
        with db.session() as connection:
            connection.executescript(
                """
                CREATE TABLE threads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id INTEGER NOT NULL REFERENCES threads(id)
                        ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tool_calls_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO threads (title) VALUES ('older than projects');
                INSERT INTO threads (title) VALUES ('also older');
                INSERT INTO messages (thread_id, role, content)
                    VALUES (1, 'user', 'hello');
                """
            )

        db.init_db()

        homes = {t["project_id"] for t in events.list_threads()}
        self.assertEqual(len(homes), 1, "every old thread lands in one project")
        self.assertNotIn(None, homes)
        home = db.get_project(homes.pop())
        self.assertEqual(home["name"], "Default")
        self.assertEqual(len(events.list_threads()), 2)
        self.assertEqual(
            [m["content"] for m in events.messages_for(1)],
            ["hello"],
            "the migration must not touch the transcript",
        )
        with db.session() as connection:
            self.assertEqual(
                connection.execute("PRAGMA foreign_key_check").fetchall(), []
            )


if __name__ == "__main__":
    unittest.main()
