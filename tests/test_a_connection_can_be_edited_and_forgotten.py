"""A connection can be edited and forgotten, and the key goes with it.

`POST /api/providers` was the only door a model connection had. You could make
one and you could never change it or get rid of it, which is fine for a dialog
that connects one model and wrong for a settings surface - a settings page that
can only add is not a settings page. So there are three more routes, and each
one has a way of being subtly dishonest that this file exists to prevent.

**PATCH can strand a measurement.** `tool_calling`, `capability_detail`,
`ctx_len` and `ctx_len_provenance` are what one probe learned about one model on
one server. Point the row at a different model without clearing them and the
interface shows a context length tagged `measured` beside a model nobody
measured. That is worse than a missing number, because a missing number looks
missing. `store.update` resets them and the first two tests hold it to that.

**PATCH can wipe a key by accident.** The engine never gives a key back, so a
settings page redrawing a connection has nothing to send. If `api_key` were an
ordinary optional field, every rename would delete the key. Absent, empty and
present are three different instructions and the third test checks all three.

**DELETE can strand a secret.** The keychain entry is filed under the row id.
Delete the row alone and there is an API key in the user's OS keychain that
nothing in this product points at any more, and nobody will think to remove it.

And the invariant, re-proved at the new doors rather than assumed from the old
one: `AGENTS.md` invariant 2, no secrets in SQLite, checked the same crude way
`tests/test_provider_key_never_reaches_sqlite.py` checks it - by reading the
database file as bytes.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from app import db
from app.providers import secrets as provider_secrets
from app.providers import store as provider_store

import support


#: Distinctive enough that finding it anywhere is unambiguous.
MARKER = "sk-patched-marker-4471-do-not-store"


class ConnectionEditingTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        from app.main import app

        self.client = support.api_client(app)
        self.addCleanup(self.client.close)

    def _connect(self, **overrides):
        payload = {
            "name": "Ollama",
            "base_url": "http://127.0.0.1:11434",
            "model": "granite4-hermes:latest",
            "adapter": "ollama",
        }
        payload.update(overrides)
        response = self.client.post("/api/providers", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        row = response.json()
        self.addCleanup(provider_secrets.delete_key, str(row["id"]))
        return row

    def _pretend_it_was_probed(self, provider_id):
        """Write the shape a real probe leaves behind, without a network call."""
        provider_store.ensure_table()
        with db.session() as connection:
            connection.execute(
                "UPDATE providers SET tool_calling = 'yes', "
                "capability_detail = 'reported by the Ollama server for this "
                "model', ctx_len = 1048576, ctx_len_provenance = 'measured' "
                "WHERE id = ?",
                (provider_id,),
            )

    # ── The probe is a measurement of one model on one server ──────────────

    def test_renaming_a_connection_keeps_what_the_probe_measured(self):
        row = self._connect()
        self._pretend_it_was_probed(row["id"])

        response = self.client.patch(
            f"/api/providers/{row['id']}", json={"name": "My local model"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        after = response.json()

        self.assertEqual(after["name"], "My local model")
        self.assertEqual(after["tool_calling"], "yes")
        self.assertEqual(after["ctx_len"], 1048576)
        self.assertEqual(after["ctx_len_provenance"], "measured")

    def test_changing_the_model_throws_the_old_measurement_away(self):
        row = self._connect()
        self._pretend_it_was_probed(row["id"])

        response = self.client.patch(
            f"/api/providers/{row['id']}", json={"model": "qwen3:4b"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        after = response.json()

        self.assertEqual(after["model"], "qwen3:4b")
        self.assertEqual(
            after["tool_calling"],
            "unknown",
            "a probe of the previous model says nothing about this one",
        )
        self.assertIsNone(after["ctx_len"])
        self.assertEqual(after["ctx_len_provenance"], "defaulted")
        self.assertEqual(after["capability_detail"], "")

    def test_changing_the_base_url_redecides_whether_it_is_local(self):
        row = self._connect()
        self.assertEqual(row["kind"], "local")

        response = self.client.patch(
            f"/api/providers/{row['id']}",
            json={
                "base_url": "https://openrouter.ai/api/v1",
                "adapter": "openai-compatible",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json()["kind"],
            "remote",
            "the egress guard reads kind; it must follow the URL",
        )

    def test_an_unknown_adapter_is_refused_rather_than_written(self):
        row = self._connect()
        response = self.client.patch(
            f"/api/providers/{row['id']}", json={"adapter": "telepathy"}
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(provider_store.get(row["id"])["adapter"], "ollama")

    def test_patching_a_connection_that_is_not_there_is_a_404(self):
        response = self.client.patch("/api/providers/9999", json={"name": "x"})
        self.assertEqual(response.status_code, 404)

    # ── Absent, empty and present are three instructions ───────────────────

    def test_an_absent_api_key_leaves_the_stored_one_alone(self):
        row = self._connect(base_url="https://api.openai.com/v1")
        os.environ[f"MLH_KEY_{row['id']}"] = MARKER
        self.addCleanup(os.environ.pop, f"MLH_KEY_{row['id']}", None)
        self.assertTrue(self.client.get("/api/providers").json()[0]["has_key"])

        response = self.client.patch(
            f"/api/providers/{row['id']}", json={"name": "Renamed"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(
            response.json()["has_key"],
            "renaming a connection must not delete its key",
        )

    def test_an_empty_api_key_deletes_the_stored_one(self):
        store = provider_secrets.backend()
        if store is None:
            self.skipTest("no OS keychain on this machine")
        row = self._connect(base_url="https://api.openai.com/v1")
        provider_secrets.set_key(str(row["id"]), MARKER)
        self.assertTrue(provider_secrets.has_key(str(row["id"])))

        response = self.client.patch(
            f"/api/providers/{row['id']}", json={"api_key": ""}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["has_key"])
        self.assertFalse(provider_secrets.has_key(str(row["id"])))

    def test_a_key_sent_to_the_patch_route_never_reaches_the_database(self):
        row = self._connect(base_url="https://api.openai.com/v1")
        response = self.client.patch(
            f"/api/providers/{row['id']}", json={"api_key": MARKER}
        )
        # 200 with a keychain, 503 without. Never a key in SQLite either way.
        self.assertIn(response.status_code, (200, 503), response.text)
        self.assertNotIn(MARKER, response.text)

        raw = Path(db.DB_PATH).read_bytes()
        self.assertNotIn(MARKER.encode("utf-8"), raw)
        self.assertNotIn(MARKER.encode("utf-16-le"), raw)

    # ── Forgetting takes the key with it ───────────────────────────────────

    def test_deleting_a_connection_removes_the_row(self):
        row = self._connect()
        response = self.client.delete(f"/api/providers/{row['id']}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["deleted"])
        self.assertEqual(self.client.get("/api/providers").json(), [])
        self.assertIsNone(provider_store.get(row["id"]))

    def test_deleting_a_connection_removes_its_key_from_the_keychain(self):
        store = provider_secrets.backend()
        if store is None:
            self.skipTest("no OS keychain on this machine")
        row = self._connect(base_url="https://api.openai.com/v1")
        provider_secrets.set_key(str(row["id"]), MARKER)
        self.assertTrue(provider_secrets.has_key(str(row["id"])))

        self.assertEqual(
            self.client.delete(f"/api/providers/{row['id']}").status_code, 200
        )
        self.assertFalse(
            provider_secrets.has_key(str(row["id"])),
            "the row went and the secret stayed behind on the machine",
        )

    def test_deleting_a_connection_that_is_not_there_is_a_404(self):
        self.assertEqual(self.client.delete("/api/providers/9999").status_code, 404)

    def test_deleting_the_active_connection_leaves_none_active(self):
        row = self._connect()
        self.client.post(f"/api/providers/{row['id']}/activate")
        self.assertIsNotNone(provider_store.active())

        self.client.delete(f"/api/providers/{row['id']}")
        self.assertIsNone(
            provider_store.active(),
            "no model connected is a state the product renders; a dangling "
            "active row is not",
        )


class KeychainRouteTest(unittest.TestCase):
    """Where a key would go, asked BEFORE one is typed.

    `POST /api/providers` answers 503 when there is no OS secret store. That is
    honest and it arrives one step too late - the key is already in a form
    field by then. This route lets the interface say up front what will happen
    to it.
    """

    def setUp(self):
        self.root = support.sandbox(self)
        from app.main import app

        self.client = support.api_client(app)
        self.addCleanup(self.client.close)

    def test_it_reports_whether_this_machine_has_a_store_and_names_it(self):
        response = self.client.get("/api/keychain")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()

        self.assertIsInstance(body["available"], bool)
        self.assertTrue(body["detail"])
        if body["available"]:
            self.assertIn(
                body["backend"],
                {"windows-credential-manager", "macos-keychain", "secret-service"},
            )
        else:
            self.assertIsNone(body["backend"])
            self.assertIn(
                body["env_prefix"],
                body["detail"],
                "with no store, the way in has to be named",
            )

    def test_it_cannot_leak_a_key_because_it_only_returns_constants(self):
        os.environ["MLH_KEY_1"] = MARKER
        self.addCleanup(os.environ.pop, "MLH_KEY_1", None)
        self.assertNotIn(MARKER, self.client.get("/api/keychain").text)


if __name__ == "__main__":
    unittest.main()
