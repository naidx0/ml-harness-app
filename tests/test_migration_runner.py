"""The migration runner, and the four ways it is allowed to refuse.

A migration runner that mostly works is worse than none, because "mostly"
means a database somewhere is in a state no code was written for. So this file
does not test that four tables appear. It tests the properties that make the
runner trustworthy, and three of the five tests below are mutation checks -
they deliberately hand the runner a broken list or a broken database and assert
it stops rather than doing its best.

1. **Idempotent.** Called twice, it applies nothing the second time. A runner
   that re-applies will run somebody's data migration again.
2. **A gap in `MIGRATIONS` applies nothing at all.** Not the migrations before
   the gap, not the ones after it. The list is checked before the database is
   opened, so the failure cannot leave a half-migrated file behind.
3. **A migration that fails is rolled back whole**, including its
   `schema_version` row. This is why the runner executes statements one at a
   time instead of using `executescript`, which issues an implicit `COMMIT`
   before it runs.
4. **A database from the future is refused.** Version 99 opened by a build that
   knows 4 was written by a newer ML Harness; writing an older shape into it is
   how you corrupt someone's data while believing you repaired it.
5. **A hole in `schema_version` is refused.** It means something half-applied a
   migration before this runner existed. Continuing on top of it guesses.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from app import db, migrations

import support


class MigrationRunnerTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)

    def fresh(self) -> Path:
        """A database path nothing has migrated yet.

        `support.sandbox` already ran `init_db()` on `test.db`, which is what
        the idempotence assertions below are written against. The mutation
        checks need a file with no `schema_version` at all, so that "nothing
        was applied" is observable.
        """
        db.DB_PATH = self.root / "fresh.db"
        return db.DB_PATH

    def tables(self) -> set[str]:
        with db.session() as connection:
            return {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }

    def test_migrate_is_idempotent_and_the_database_works(self):
        """The step 1.1 acceptance, adjusted for a tree with four migrations.

        `docs/ROADMAP.md` step 1.1 was written when `MIGRATIONS` had exactly one
        entry and its acceptance asserts `migrate() == 1` twice. Asserting the
        literal 1 now would be asserting that steps 1.2 and 1.3 had not
        happened, so this asserts the highest version in the list - which is
        the same claim - and keeps the shape that is the actual point: call it
        twice, get the same answer, and add no second row.
        """
        highest = migrations.MIGRATIONS[-1][0]
        self.assertEqual(migrations.migrate(), highest)
        self.assertEqual(migrations.migrate(), highest)
        run = db.create_run("m", "{}")
        self.assertEqual(run["name"], "m")
        with db.session() as c:
            rows = c.execute("SELECT version FROM schema_version").fetchall()
        self.assertEqual(len(rows), len(migrations.MIGRATIONS))
        self.assertEqual([r[0] for r in rows], [v for v, _ in migrations.MIGRATIONS])

    def test_the_versions_are_1_to_n_with_no_gaps(self):
        versions = [version for version, _ in migrations.MIGRATIONS]
        self.assertEqual(versions, list(range(1, len(versions) + 1)))

    def test_a_gap_in_the_list_applies_nothing(self):
        """Mutation check: renumber a migration so 2 is missing.

        The assertion that matters is the second one. A runner that validated
        after applying would have created `runs` from migration 1 and then
        refused, leaving a database that is at version 1 and looks fine until
        something reads a table migration 2 was supposed to build.
        """
        self.fresh()
        good = migrations.MIGRATIONS
        migrations.MIGRATIONS = [good[0], (3, good[1][1])]
        self.addCleanup(setattr, migrations, "MIGRATIONS", good)

        with self.assertRaises(migrations.MigrationError) as raised:
            migrations.migrate()
        self.assertIn("[1, 3]", str(raised.exception))
        self.assertEqual(
            self.tables(),
            set(),
            "a gap must apply NOTHING - not even the migrations before it",
        )

    def test_a_migration_that_fails_leaves_no_trace_of_itself(self):
        """Mutation check: a migration whose second statement is nonsense.

        Its first statement is a perfectly good `CREATE TABLE`. If the
        statements were not inside one transaction with the `schema_version`
        row, that table would survive the failure and the database would be
        at version 1 with a table only version 2 knows about.
        """
        self.fresh()
        good = migrations.MIGRATIONS
        migrations.MIGRATIONS = [
            good[0],
            (
                2,
                "CREATE TABLE half_applied (id INTEGER PRIMARY KEY);\n"
                "CREATE TABLE nonsense (id INTEGER PRIMARY KEY) SYNTAX ERROR;\n",
            ),
        ]
        self.addCleanup(setattr, migrations, "MIGRATIONS", good)

        with self.assertRaises(migrations.MigrationError) as raised:
            migrations.migrate()
        self.assertIn("migration 2 failed", str(raised.exception))
        self.assertNotIn("half_applied", self.tables())
        with db.session() as c:
            applied = [r[0] for r in c.execute("SELECT version FROM schema_version")]
        self.assertEqual(applied, [1], "version 2 must not be recorded")

    def test_a_database_from_the_future_is_refused(self):
        with db.session() as c:
            c.execute("INSERT INTO schema_version (version) VALUES (99)")
        with self.assertRaises(migrations.MigrationError) as raised:
            migrations.migrate()
        self.assertIn("99", str(raised.exception))
        self.assertIn("newer version", str(raised.exception))

    def test_a_hole_in_schema_version_is_refused(self):
        self.fresh()
        with db.session() as c:
            c.execute(
                "CREATE TABLE schema_version (version INTEGER PRIMARY KEY, "
                "applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            c.execute("INSERT INTO schema_version (version) VALUES (1)")
            c.execute("INSERT INTO schema_version (version) VALUES (3)")
        with self.assertRaises(migrations.MigrationError) as raised:
            migrations.migrate()
        self.assertIn("[2]", str(raised.exception))
        self.assertNotIn("runs", self.tables())

    def test_every_migration_is_its_own_frozen_file(self):
        """Each shipped migration is a file whose name carries its version.

        Not decoration: the rule is that a migration is never edited once it
        has shipped, and a rule that lives only in a comment is a rule nobody
        can see they are breaking. A version whose file is missing means
        somebody renumbered in place.
        """
        package = Path(migrations.__file__).parent
        for version, _ in migrations.MIGRATIONS:
            matches = sorted(package.glob(f"v{version:03d}_*.py"))
            self.assertEqual(
                len(matches), 1, f"migration {version} has no single file"
            )


if __name__ == "__main__":
    unittest.main()
