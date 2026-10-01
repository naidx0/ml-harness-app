"""The provider key is not in the database. Proved against the file's bytes.

`AGENTS.md` invariant 2 says no secrets in SQLite. This is the test that turns
that from a claim into a property of the build, and it is deliberately crude:
it stores a key through the real code path, then reads `ml_harness.db` as bytes
and asserts the marker is not among them.

Crude is the point. A test that asserts "the providers table has no api_key
column" passes for a schema that grew one later under a different name, and a
test that mocks the keychain proves only that the mock was called. Bytes on
disk answer the actual question, which is: if someone copies this file, what
have they got?

Two paths, both asserted, because a machine without a usable secret store must
not become a machine that writes the key somewhere worse:

- **With a keychain** the key is stored there and the database is clean.
- **Without one** the request is refused with a plain 503, the connection row
  still exists, and the database is still clean.
"""

from __future__ import annotations

import ast
import inspect
import os
import re
import unittest
from pathlib import Path

from app import db
from app.providers import secrets as provider_secrets
from app.providers import store as provider_store

import support


#: Distinctive enough that finding it anywhere is unambiguous.
MARKER = "sk-secret-marker-9137-do-not-store"


class KeyNeverReachesSqliteTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        from app.main import app

        self.client = support.api_client(app)
        self.addCleanup(self.client.close)

    def _forget(self, provider_id):
        self.addCleanup(provider_secrets.delete_key, str(provider_id))

    def test_the_key_posted_to_the_api_is_not_in_the_database_file(self):
        response = self.client.post(
            "/api/providers",
            json={
                "name": "Test",
                "base_url": "https://api.example.com/v1",
                "model": "m",
                "adapter": "openai-compatible",
                "api_key": MARKER,
            },
        )
        self.assertIn(response.status_code, (201, 503), response.text)
        self.assertNotIn(MARKER, response.text)

        rows = provider_store.list_all()
        self.assertEqual(len(rows), 1, "the connection row must exist either way")
        self._forget(rows[0]["id"])

        raw = Path(db.DB_PATH).read_bytes()
        self.assertNotIn(
            MARKER.encode("utf-8"),
            raw,
            "the provider API key reached SQLite",
        )
        # UTF-16, in case something wrote it through a Windows API by accident.
        self.assertNotIn(MARKER.encode("utf-16-le"), raw)

    def test_the_providers_table_has_no_column_that_could_hold_a_key(self):
        provider_store.ensure_table()
        with db.session() as connection:
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(providers)")
            }
        for forbidden in ("api_key", "key", "secret", "token", "password"):
            with self.subTest(column=forbidden):
                self.assertNotIn(forbidden, columns)

    def test_a_listed_provider_reports_whether_it_has_a_key_never_the_key(self):
        row = provider_store.create(
            "Test", "https://api.example.com/v1", "m", "openai-compatible"
        )
        self._forget(row["id"])
        os.environ[f"MLH_KEY_{row['id']}"] = MARKER
        self.addCleanup(os.environ.pop, f"MLH_KEY_{row['id']}", None)

        listed = self.client.get("/api/providers").json()
        self.assertTrue(listed[0]["has_key"])
        self.assertNotIn(MARKER, self.client.get("/api/providers").text)


class SecretsModuleShapeTest(unittest.TestCase):
    """The module cannot store a key in the database because it cannot reach it."""

    def test_the_secrets_module_contains_no_sql_and_never_imports_db(self):
        """Read the syntax tree, not the text.

        Grepping the source would also match this module's own prose about why
        it holds no SQL, which is a test that fails for being explained. The
        tree carries only what actually executes.
        """
        tree = ast.parse(inspect.getsource(provider_secrets))

        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for forbidden in ("sqlite3", "db"):
            with self.subTest(module=forbidden):
                self.assertNotIn(forbidden, imported)
        self.assertFalse(hasattr(provider_secrets, "db"))

        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            )
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        }
        sql = re.compile(r"\b(insert\s+into|select\s|update\s+\w+\s+set|create\s+table)\b")
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
            ):
                with self.subTest(literal=node.value[:40]):
                    self.assertIsNone(sql.search(node.value.lower()))

    def test_the_environment_variable_is_read_before_the_keychain(self):
        """A machine with no usable store still has a way in.

        Checked first rather than as a fallback, which is also what lets the
        rest of this suite exercise key-reading paths without ever touching a
        real credential store.
        """
        os.environ["MLH_KEY_TESTPROV"] = "sk-test-123"
        self.addCleanup(os.environ.pop, "MLH_KEY_TESTPROV", None)
        self.assertEqual(provider_secrets.get_key("testprov"), "sk-test-123")
        self.assertTrue(provider_secrets.has_key("testprov"))

    def test_a_missing_key_is_none_rather_than_an_exception(self):
        self.assertIsNone(provider_secrets.get_key("no-such-provider-xyz9"))
        self.assertFalse(provider_secrets.has_key("no-such-provider-xyz9"))

    def test_a_key_round_trips_through_the_real_os_keychain(self):
        """Skipped where there is no store, never faked into passing."""
        store = provider_secrets.backend()
        if store is None:
            self.skipTest("no OS keychain on this machine")
        account = "mlh-selftest-provider"
        self.addCleanup(provider_secrets.delete_key, account)
        provider_secrets.set_key(account, MARKER)
        self.assertEqual(provider_secrets.get_key(account), MARKER)
        provider_secrets.delete_key(account)
        self.assertIsNone(provider_secrets.get_key(account))


if __name__ == "__main__":
    unittest.main()
