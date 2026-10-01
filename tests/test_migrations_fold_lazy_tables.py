"""The four lazily-created tables are migration 2's now, and nothing else's.

`intake`, `jobs`, `models` and `datasets` were each created by an
`ensure_*_table()` helper that ran at the top of every reader. That is how a
table's existence became a race: `list_jobs` shipped without its call and
returned "no such table" the first time a page listed an empty queue, and the
generated acceptance test never saw it because it created a job first.

So the tests here never call an `ensure_*_table` function. They run the
migrations and then use the tables, which is the only way to prove migration 2
alone builds them.

The other half is what the fold must NOT lose. `ensure_jobs_table` also carries
the pre-`JobSpec` rescue: a database written before the structured job contract
has a `cmd TEXT NOT NULL` column holding a shell command, and those rows are
moved into a shape that cannot execute. That is a conditional data migration -
it fires only when the old column is there - and SQL has no branch, so it stays
in Python. `test_a_legacy_jobs_table_is_still_rescued` is the test that stops
the next person tidying it away.
"""

from __future__ import annotations

import json
import unittest

from app import db, migrations

import support


def columns(table: str) -> list[str]:
    with db.session() as connection:
        return [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]


class FoldedTablesTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)

    def test_migration_2_alone_builds_the_four_tables(self):
        """Step 1.2's acceptance, with one substitution that the tree forced.

        The step's line is `db.create_job("s1", "echo hi")`. That signature is
        gone: `create_job` takes a validated `JobSpec` since the shell-execution
        hole was closed, and there is no longer a column for a command string
        to live in. `support.spec` builds the structured equivalent. Asserting
        the old call would be asserting the hole was still open.
        """
        self.assertEqual(migrations.migrate(), migrations.MIGRATIONS[-1][0])
        db.create_intake("s1", {"goal": "x"})
        db.create_job("s1", support.spec("printer"))
        db.create_model("m", "b", "Q4", "LoRA", "/p", "n")
        db.create_dataset("/d.csv", 10, "csv", "train", "n")
        self.assertEqual(db.get_intake("s1")["answers"]["goal"], "x")

    def test_the_folded_shapes_are_the_shapes_that_were_there_before(self):
        """The columns, checked rather than assumed.

        `models` and `datasets` were one-line `CREATE` statements in `db.py` and
        are broken across lines in the migration. This is the assertion that
        makes "nothing changed but the whitespace" a measurement.
        """
        self.assertEqual(
            columns("intake"), ["id", "session_id", "answers", "created_at"]
        )
        self.assertEqual(
            columns("jobs"),
            ["id", "intake_id", "recipe", "kind", "config_json", "status",
             "created_at", "finished_at", "exit_code", "log_path"],
        )
        self.assertEqual(
            columns("models"),
            ["id", "name", "base", "quant", "method", "path", "notes",
             "created_at"],
        )
        self.assertEqual(
            columns("datasets"),
            ["id", "path", "rows", "format", "split", "notes", "created_at"],
        )

    def test_the_ensure_helpers_no_longer_own_any_schema(self):
        """They stay, they are still called, and they create nothing.

        Seven call sites in `app/db.py` and several tests name these functions,
        so deleting them was never on the table. What matters is that calling
        one on a database that is already migrated changes nothing at all.
        """
        with db.session() as connection:
            before = sorted(
                row[0]
                for row in connection.execute(
                    "SELECT name || ':' || COALESCE(sql, '') FROM sqlite_master"
                )
            )
        db.ensure_intake_table()
        db.ensure_jobs_table()
        db.ensure_models_table()
        db.ensure_datasets_table()
        with db.session() as connection:
            after = sorted(
                row[0]
                for row in connection.execute(
                    "SELECT name || ':' || COALESCE(sql, '') FROM sqlite_master"
                )
            )
        self.assertEqual(before, after)

    def test_a_legacy_jobs_table_is_still_rescued(self):
        """A pre-`JobSpec` database keeps its history, in an inert shape.

        The rescue survived the fold. The command string ends up inside
        `config_json` as data, under the recipe name `legacy-command`, which is
        not a directory under `recipes/` - so `jobspec.load_recipe` refuses it
        and the runner records the refusal instead of finding something to run.
        """
        db.DB_PATH = self.root / "legacy.db"
        with db.session() as connection:
            connection.executescript(
                """
                CREATE TABLE jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    intake_id TEXT NOT NULL,
                    cmd TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    finished_at TEXT,
                    exit_code INTEGER,
                    log_path TEXT
                );
                INSERT INTO jobs (intake_id, cmd) VALUES ('old', 'calc.exe');
                """
            )
        db.init_db()

        self.assertNotIn("cmd", columns("jobs"))
        rows = db.list_jobs()
        self.assertEqual(len(rows), 1, "the user's history must survive")
        self.assertEqual(rows[0]["recipe"], "legacy-command")
        self.assertEqual(
            json.loads(rows[0]["config_json"])["legacy_cmd"], "calc.exe"
        )


if __name__ == "__main__":
    unittest.main()
