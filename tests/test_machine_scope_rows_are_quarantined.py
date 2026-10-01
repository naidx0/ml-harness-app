"""Migration 6 moves the rows that could open a gate anywhere, and deletes none.

Three rows in the owner's real database were written at machine scope for a fact
the ledger declares belongs to one conversation. All three were `eval_size_n`,
all three MEASURED, all three real counts of files in temporary directories that
no longer exist, and two of the three were written by a reviewer through
`POST /api/tools/{name}` while verifying something else. `evidence.rows_for`
showed every one of them to every conversation on the machine.

They are the user's data and they are not junk: a file really was counted. What
is missing is what the count was OF, and a migration cannot supply that - the
directories are gone, and guessing a thread id would be inventing the exact fact
that is missing. So NOTHING IS DELETED AND NOTHING IS EDITED. Each row moves,
whole, into `quarantined_facts`, keeping its id, its value, its origin, its
actor, its tool, its `how` sentence and its `created_at`, and gaining two columns:
when it was moved, and why.

The fixture below is the owner's database rebuilt from what was read off a COPY
of it - three bad rows at ids 36, 37 and 38, thirty-six hardware rows that all
carry a thread, and the thread-scoped facts around them - so this file asserts
against the real shape rather than against a shape invented to pass.

THE CONTROLS. Every assertion here is about a refusal or a removal, and would
pass against a migration that emptied the table. So: the good rows are counted
before and after and must be identical, a database with nothing wrong with it
must come out byte-for-byte unchanged in its evidence, and the quarantined rows
must still be readable with their values intact.
"""

from __future__ import annotations

import sqlite3
import unittest

from app import db, migrations
from app.tools import evidence

import support


#: The version `migrate()` leaves a database at, read off the runner rather than
#: written down. This file is about what migration 6 DID; `migrate()` applies
#: everything it knows, so the number it returns is the head of the list and goes
#: up every time a migration ships. Asserting the literal 6 here made this test
#: fail on the day migration 7 arrived, for a reason that was not about
#: migration 6 at all.
HEAD = migrations.MIGRATIONS[-1][0]


#: Read off a copy of the owner's real `ml_harness.db`. Three rows, one fact.
THE_THREE_BAD_ROWS = [
    (36, None, "eval_size_n", "120", "MEASURED", "user", "profile_dataset",
     r"counted 120 rows in C:\Users\example\AppData\Local\Temp\tmp4myaw83y\eval.jsonl",
     "2026-08-19 15:11:32"),
    (37, None, "eval_size_n", "120", "MEASURED", "user", "profile_dataset",
     r"counted 120 rows in C:\Users\example\AppData\Local\Temp\tmp4myaw83y\eval.jsonl",
     "2026-08-19 15:11:32"),
    (38, None, "eval_size_n", "120", "MEASURED", "user", "profile_dataset",
     r"counted 120 rows in C:\Users\example\AppData\Local\Temp\tmph_4tt4go\eval.jsonl",
     "2026-08-19 15:11:51"),
]

#: The rows that must survive untouched: the machine's own facts written with no
#: thread (which is what machine scope is FOR and which this migration must not
#: touch), the machine's own facts written inside a thread (which is how all
#: thirty-six hardware rows in the real database actually look), and the
#: thread-scoped facts that were filed correctly.
THE_GOOD_ROWS = [
    (1, None, "vram_gb", "24.0", "MEASURED", "harness", "inspect_hardware",
     "read off the machine", "2026-08-19 08:23:46"),
    (2, None, "accelerator", '"nvidia"', "MEASURED", "harness", "inspect_hardware",
     "read off the machine", "2026-08-19 08:23:46"),
    (3, 5, "ram_gb", "64.0", "MEASURED", "harness", "inspect_hardware",
     "read off the machine", "2026-08-19 08:23:47"),
    (4, 5, "eval_size_n", "500", "MEASURED", "user", "measure_eval_set",
     "counted 500 rows in eval.jsonl", "2026-08-19 09:00:00"),
    (5, 5, "goal_text", '"route support tickets"', "STATED", "user", "state_facts",
     "the user said so, through state_facts", "2026-08-19 09:00:01"),
]

_COLUMNS = (
    "id, thread_id, fact, value, origin, actor, tool, how, created_at"
)

_EVIDENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS fact_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER,
    fact TEXT NOT NULL,
    value TEXT NOT NULL,
    origin TEXT NOT NULL,
    actor TEXT NOT NULL,
    tool TEXT,
    how TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def a_database_at_version_five(path, rows) -> None:
    """A database as it stood before this migration: five migrations, a lazily
    created `fact_evidence`, and whatever rows the caller wants in it.

    THREAD 5 IS CREATED, and that is not scaffolding - it is what the owner's
    database actually looked like. The three rows migration 6 moved had no
    thread at all; every other row in that database named a conversation that
    was really there. A fixture that skipped the conversation would be a fixture
    of a database nobody has, and migration 7 - which quarantines a row whose
    thread_id names nothing - would move rows 3, 4 and 5 as well and this file
    would be asserting about the wrong migration.
    """
    connection = sqlite3.connect(path)
    try:
        connection.execute(migrations._SCHEMA_VERSION)
        for version, sql in migrations.MIGRATIONS[:5]:
            for statement in migrations._statements(sql):
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (version,)
            )
        connection.execute(
            "INSERT INTO threads (id, title) VALUES (5, 'the conversation that "
            "counted its own file')"
        )
        connection.execute(_EVIDENCE_SCHEMA)
        connection.executemany(
            f"INSERT INTO fact_evidence ({_COLUMNS}) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        connection.commit()
    finally:
        connection.close()


def read(path, sql, parameters=()) -> list[dict]:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(sql, parameters)]
    finally:
        connection.close()


class TheThreeRowsAreQuarantinedTest(unittest.TestCase):
    """Against the owner's database, rebuilt row for row from a copy of it."""

    def setUp(self):
        self.root = support.sandbox(self)
        self.path = self.root / "as_it_was.db"
        a_database_at_version_five(
            self.path, THE_GOOD_ROWS + THE_THREE_BAD_ROWS
        )
        self.before = read(self.path, "SELECT * FROM fact_evidence ORDER BY id")
        db.DB_PATH = self.path
        self.version = migrations.migrate()
        self.after = read(self.path, "SELECT * FROM fact_evidence ORDER BY id")
        self.quarantined = read(
            self.path, "SELECT * FROM quarantined_facts ORDER BY id"
        )

    def test_the_migration_applied(self):
        self.assertEqual(self.version, HEAD)

    def test_the_counts_add_up_and_nothing_vanished(self):
        """ROW COUNTS BEFORE AND AFTER, which is the whole promise.

        8 rows in, 5 left in the ledger, 3 in quarantine. Not "about 8".
        """
        self.assertEqual(len(self.before), 8)
        self.assertEqual(len(self.after), 5)
        self.assertEqual(len(self.quarantined), 3)
        self.assertEqual(len(self.after) + len(self.quarantined), len(self.before))

    def test_exactly_the_three_bad_rows_moved(self):
        self.assertEqual([row["id"] for row in self.quarantined], [36, 37, 38])
        self.assertEqual(
            {row["fact"] for row in self.quarantined}, {"eval_size_n"}
        )

    def test_each_moved_row_is_identical_to_what_it_was(self):
        """MOVED, NOT REWRITTEN. Every original column, unchanged."""
        was = {row["id"]: row for row in self.before}
        for row in self.quarantined:
            with self.subTest(id=row["id"]):
                original = was[row["id"]]
                for column in (
                    "thread_id", "fact", "value", "origin", "actor", "tool",
                    "how", "created_at",
                ):
                    self.assertEqual(row[column], original[column], column)

    def test_each_moved_row_says_why_it_moved(self):
        for row in self.quarantined:
            with self.subTest(id=row["id"]):
                because = row["quarantined_because"]
                self.assertIn("thread_id", because)
                self.assertIn("scope: thread", because)
                self.assertIn("Moved rather than deleted", because)
                self.assertTrue(row["quarantined_at"])

    def test_the_rows_that_were_fine_are_all_still_there(self):
        """POSITIVE CONTROL. A migration that emptied the table would pass every
        assertion above."""
        self.assertEqual(
            [row["id"] for row in self.after], [row[0] for row in THE_GOOD_ROWS]
        )
        self.assertEqual(self.after, [row for row in self.before if row["id"] <= 5])

    def test_the_machines_own_facts_keep_their_machine_scope(self):
        """The mechanism is not being removed, only the misuse of it. Two of the
        surviving rows have no thread and are hardware, and they stay that way."""
        machine = [row for row in self.after if row["thread_id"] is None]
        self.assertEqual({row["fact"] for row in machine}, {"vram_gb", "accelerator"})

    def test_the_quarantined_rows_are_readable_through_the_product(self):
        """"Kept readable" is not a claim about sqlite3. `quarantine_view` is
        where a person meets these rows, and `GET /api/evidence` shows it."""
        rows = evidence.quarantine_view()
        self.assertEqual([row["id"] for row in rows], [38, 37, 36])
        self.assertEqual({row["value"] for row in rows}, {120})
        self.assertIn("tmph_4tt4go", rows[0]["how"])

    def test_a_quarantined_value_comes_back_marked_as_a_claim(self):
        """Stricter than the live ledger, and deliberately. A row is in here
        because the product decided its measurement is attached to no
        conversation it can be trusted in; handing it back unmarked would let a
        minting tool read one and re-stamp it, which is wall 3's laundering with
        an extra hop."""
        rows = evidence.quarantine_view()
        self.assertTrue(
            all(isinstance(row["value"], evidence.CallerValue) for row in rows),
            [type(row["value"]) for row in rows],
        )

    def test_no_conversation_can_see_them_any_more(self):
        """THE CONSEQUENCE, which is the only reason any of this matters."""
        for thread_id in (None, 4242, 5):
            with self.subTest(thread=thread_id):
                seen, _ = evidence.assemble_facts(thread_id)
                if thread_id == 5:
                    # thread 5 counted its own file and still knows its own count
                    self.assertEqual(seen["eval_size_n"].value, 500)
                else:
                    self.assertNotIn("eval_size_n", seen)

    def test_running_it_again_changes_nothing(self):
        """Idempotent, like every migration here. A data migration that runs
        twice is the failure this package's docstring is most afraid of."""
        self.assertEqual(migrations.migrate(), HEAD)
        self.assertEqual(
            read(self.path, "SELECT * FROM fact_evidence ORDER BY id"), self.after
        )
        self.assertEqual(
            read(self.path, "SELECT * FROM quarantined_facts ORDER BY id"),
            self.quarantined,
        )


class ADatabaseWithNothingWrongWithItIsUntouchedTest(unittest.TestCase):
    """The other direction, which is what makes this safe to ship to everybody."""

    def test_a_clean_ledger_comes_out_exactly_as_it_went_in(self):
        root = support.sandbox(self)
        path = root / "clean.db"
        a_database_at_version_five(path, THE_GOOD_ROWS)
        before = read(path, "SELECT * FROM fact_evidence ORDER BY id")
        db.DB_PATH = path
        self.assertEqual(migrations.migrate(), HEAD)
        self.assertEqual(read(path, "SELECT * FROM fact_evidence ORDER BY id"), before)
        self.assertEqual(read(path, "SELECT * FROM quarantined_facts"), [])

    def test_a_database_that_never_recorded_a_fact_migrates_anyway(self):
        """`fact_evidence` is created lazily by `evidence.ensure_table`, so a
        fresh install does not have it and `INSERT ... SELECT FROM fact_evidence`
        would be "no such table" - a failed migration on every new install. The
        `CREATE TABLE IF NOT EXISTS` in migration 6 is what stops that."""
        root = support.sandbox(self)
        path = root / "fresh.db"
        connection = sqlite3.connect(path)
        connection.close()
        db.DB_PATH = path
        self.assertEqual(migrations.migrate(), HEAD)
        self.assertEqual(read(path, "SELECT * FROM fact_evidence"), [])
        self.assertEqual(read(path, "SELECT * FROM quarantined_facts"), [])

    def test_the_reader_answers_none_before_anything_is_quarantined(self):
        """POSITIVE CONTROL for `ensure_quarantine_table`: "no such table" is
        the `list_jobs` defect in this repository's git log, and it is not being
        repeated."""
        support.sandbox(self)
        self.assertEqual(evidence.quarantine_view(), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
