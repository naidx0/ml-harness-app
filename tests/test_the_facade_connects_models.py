"""Models reach their picker in one click: API keys through their connect
dialog, and the models already on this machine through the picker itself.

Their connect dialog (`vendor/opencode/packages/app/src/providers/connect/`)
lists `integration.list`, walks a key method's form, and posts the key with
the form's answer to `integration.connect.key`; their settings page removes a
connection with `integration.get` and `credential.remove`. Each response here
is validated against their OpenAPI document (`tests/openapi_contract.py`).

THE KEYCHAIN IS FAKED IN EVERY TEST HERE. Connection ids restart at 1 in every
database, and the real OS keychain files keys under the connection id, so a
test that stored a key for connection 1 in the real store would overwrite the
key of the person's own connection 1.
"""

from __future__ import annotations

import unittest
from unittest import mock

from app.facade import catalog, integrations
from app.providers import secrets as provider_secrets
from app.providers import store as provider_store

import openapi_contract as contract
from test_the_facade_speaks_their_protocol import FacadeTestCase


class MemoryKeychain:
    name = "memory"

    def __init__(self) -> None:
        self.keys: dict[tuple[str, str], str] = {}

    def available(self) -> bool:
        return True

    def set(self, service: str, account: str, key: str) -> None:
        self.keys[(service, account)] = key

    def get(self, service: str, account: str) -> str | None:
        return self.keys.get((service, account))

    def delete(self, service: str, account: str) -> None:
        self.keys.pop((service, account), None)


class KeychainTestCase(FacadeTestCase):
    def setUp(self):
        super().setUp()
        self.keychain = MemoryKeychain()
        patcher = mock.patch.object(provider_secrets, "backend", return_value=self.keychain)
        patcher.start()
        self.addCleanup(patcher.stop)


class TheirConnectDialogConnectsAKeyedPresetTest(KeychainTestCase):
    def test_only_presets_that_need_a_key_are_offered_and_only_by_key(self):
        body = contract.assert_response(self, "integration.list", self.client.get("/oc/api/integration"))
        ids = [item["id"] for item in body["data"]]
        self.assertEqual(ids, ["openai", "openrouter"])
        for item in body["data"]:
            with self.subTest(integration=item["id"]):
                self.assertEqual([m["type"] for m in item["methods"]], ["key"])
                self.assertEqual(item["connections"], [])
        # No local server, and no vendor the engine has no adapter for.
        self.assertNotIn("ollama", ids)
        self.assertNotIn("anthropic", ids)

    def test_the_model_is_a_pick_list_with_a_free_text_escape(self):
        body = contract.assert_response(
            self, "integration.get", self.client.get("/oc/api/integration/openai")
        )
        choice, typed = body["data"]["methods"][0]["form"]
        values = [option["value"] for option in choice["options"]]
        self.assertIn("gpt-4.1-mini", values)
        self.assertEqual(values[-1], integrations.OTHER_MODEL)
        # Their form shows a field with options as a list and one without as
        # text; the text field appears only when "another model" is picked.
        self.assertNotIn("options", typed)
        self.assertEqual(
            typed["when"], [{"key": "model", "op": "eq", "value": integrations.OTHER_MODEL}]
        )

    def test_a_preset_with_no_suggestions_asks_for_the_model_as_text(self):
        preset = {"name": "Nowhere", "base_url": "https://x.invalid/v1", "adapter": "openai-compatible"}
        (field,) = integrations.model_form(preset)
        self.assertEqual((field["key"], field["type"]), ("model", "string"))
        self.assertNotIn("options", field)

    def connect(self, integration="openai", **body):
        body.setdefault("key", "sk-test-4471")
        return self.client.post(f"/oc/api/integration/{integration}/connect/key", json=body)

    def test_connecting_makes_an_active_connection_with_the_key_in_the_keychain(self):
        probed = []
        with mock.patch.object(catalog, "probe_later", side_effect=probed.append):
            response = self.connect(answer={"model": "gpt-4.1"})
        contract.assert_response(self, "integration.connect.key", response, 204)
        (row,) = provider_store.list_all()
        self.assertEqual(
            (row["name"], row["base_url"], row["model"], row["adapter"]),
            ("OpenAI", "https://api.openai.com/v1", "gpt-4.1", "openai-compatible"),
        )
        self.assertEqual(provider_store.active()["id"], row["id"])
        self.assertEqual(self.keychain.get(provider_secrets.SERVICE, str(row["id"])), "sk-test-4471")
        self.assertEqual(probed, [row["id"]])
        # Listed as a credential of the preset, and as a provider in their picker.
        listed = self.client.get("/oc/api/integration/openai").json()["data"]
        self.assertEqual([c["id"] for c in listed["connections"]], [f"conn-{row['id']}"])
        providers = self.client.get("/oc/api/provider").json()["data"]
        self.assertEqual([p["id"] for p in providers], [f"conn-{row['id']}"])
        # The key is never in any answer.
        for path in ("/oc/api/integration", "/oc/api/provider", "/oc/api/model", "/oc/api/config"):
            self.assertNotIn("sk-test-4471", self.client.get(path).text)

    def test_a_model_typed_by_hand_is_the_one_connected(self):
        response = self.connect(
            "openrouter",
            answer={"model": integrations.OTHER_MODEL, "model_id": "mistralai/mistral-large"},
            label="My router",
        )
        contract.assert_response(self, "integration.connect.key", response, 204)
        (row,) = provider_store.list_all()
        self.assertEqual((row["name"], row["model"]), ("My router", "mistralai/mistral-large"))

    def test_no_answer_takes_the_first_suggestion(self):
        contract.assert_response(self, "integration.connect.key", self.connect(), 204)
        self.assertEqual(provider_store.list_all()[0]["model"], "gpt-4.1-mini")

    def test_an_empty_key_and_an_unknown_integration_are_their_declared_errors(self):
        empty = self.connect(key="  ")
        self.assertEqual(empty.status_code, 400)
        self.assertEqual(contract.errors(empty.json(), contract.component("InvalidRequestErrorEncoded")), [])
        self.assertEqual(provider_store.list_all(), [])
        for iid in ("anthropic", "ollama"):
            with self.subTest(integration=iid):
                missing = self.connect(iid)
                self.assertEqual(missing.status_code, 404)
                self.assertEqual(
                    contract.errors(missing.json(), contract.component("IntegrationNotFoundErrorEncoded")), []
                )
                got = self.client.get(f"/oc/api/integration/{iid}")
                self.assertEqual(got.status_code, 404)

    def test_no_keychain_is_their_400_with_the_engines_sentence_and_nothing_is_activated(self):
        with mock.patch.object(provider_secrets, "backend", return_value=None):
            response = self.connect(answer={"model": "gpt-4.1"})
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(contract.errors(body, contract.component("InvalidRequestErrorEncoded")), [])
        self.assertIn("the key was not", body["message"])
        self.assertIn(provider_secrets.ENV_PREFIX, body["message"])
        self.assertIsNone(provider_store.active())

    def test_disconnecting_one_connection_forgets_it_and_its_key(self):
        """Their settings page asks `integration.get` for the provider's id and
        removes every credential it lists: for a connection that is itself."""
        self.connect(answer={"model": "gpt-4.1"})
        self.connect(answer={"model": "gpt-4o-mini"})
        first, second = sorted(provider_store.list_all(), key=lambda row: row["id"])
        one = contract.assert_response(
            self, "integration.get", self.client.get(f"/oc/api/integration/conn-{first['id']}")
        )
        self.assertEqual([c["id"] for c in one["data"]["connections"]], [f"conn-{first['id']}"])
        removed = self.client.delete(f"/oc/api/credential/conn-{first['id']}")
        contract.assert_response(self, "credential.remove", removed, 204)
        self.assertEqual([row["id"] for row in provider_store.list_all()], [second["id"]])
        self.assertIsNone(self.keychain.get(provider_secrets.SERVICE, str(first["id"])))
        again = self.client.delete(f"/oc/api/credential/conn-{first['id']}")
        self.assertEqual(again.status_code, 400)
        self.assertEqual(contract.errors(again.json(), contract.component("InvalidRequestErrorEncoded")), [])


#: What `list_local_models` answers for a daemon with two chat models and an
#: embedding model, in the tool's own shape.
OLLAMA_HAS = {
    "ok": True,
    "count": 3,
    "models": [
        {"name": "llama3.2:latest", "capabilities": ["completion", "tools"]},
        {"name": "qwen3:8b", "capabilities": ["completion", "thinking"]},
        {"name": "nomic-embed-text:latest", "capabilities": ["embedding"]},
    ],
}


class TheModelsOnThisMachineAreInTheirPickerTest(FacadeTestCase):
    """Discovery is off in a sandbox; these tests turn it on and fake the
    daemon's answer at the tool, so the developer's own Ollama is never read."""

    def setUp(self):
        super().setUp()
        for name, value in (("DISCOVER_LOCAL", True),):
            patcher = mock.patch.object(catalog, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        catalog.forget_discovered()
        self.addCleanup(catalog.forget_discovered)
        from app.tools import models as model_tools

        self.daemon = mock.patch.object(model_tools, "list_local_models", return_value=OLLAMA_HAS)
        self.asked = self.daemon.start()
        self.addCleanup(self.daemon.stop)
        self.probed: list[int] = []
        probe = mock.patch.object(catalog, "probe_later", side_effect=self.probed.append)
        probe.start()
        self.addCleanup(probe.stop)

    def models(self):
        return contract.assert_response(self, "model.list", self.client.get("/oc/api/model"))["data"]

    def test_the_chat_models_ollama_has_are_listed_under_local_ollama(self):
        import time

        providers = contract.assert_response(self, "provider.list", self.client.get("/oc/api/provider"))
        self.assertEqual([p["id"] for p in providers["data"]], ["local-ollama"])
        models = self.models()
        self.assertEqual(
            [(m["providerID"], m["id"]) for m in models],
            [("local-ollama", "llama3.2:latest"), ("local-ollama", "qwen3:8b")],
        )
        self.assertEqual([m["capabilities"]["tools"] for m in models], [True, False])
        for model in models:
            self.assertEqual(model["family"], model["id"])
            self.assertLess(abs(time.time() * 1000 - model["time"]["released"]), 1000 * 60 * 60 * 24)
        self.assertEqual(provider_store.list_all(), [], "listing connects nothing")

    def test_the_daemon_is_asked_once_per_window_not_once_per_read(self):
        self.models()
        self.models()
        self.client.get("/oc/api/provider")
        self.assertEqual(self.asked.call_count, 1)

    def test_ollama_not_running_is_an_empty_picker_not_an_error(self):
        from app.tools import models as model_tools

        self.daemon.stop()
        catalog.forget_discovered()
        refused = {"ok": False, "error": "no_local_daemon", "detail": "nothing answered"}
        with mock.patch.object(model_tools, "list_local_models", return_value=refused):
            self.assertEqual(self.models(), [])
            providers = contract.assert_response(self, "provider.list", self.client.get("/oc/api/provider"))
        self.assertEqual(providers["data"], [])
        self.daemon.start()

    def test_choosing_one_connects_it_and_the_pair_does_not_change(self):
        sid = self.create()["id"]
        ref = {"id": "llama3.2:latest", "providerID": "local-ollama"}
        response = self.client.post(f"/oc/api/session/{sid}/model", json={"model": ref})
        contract.assert_response(self, "session.switchModel", response, 204)
        (row,) = provider_store.list_all()
        self.assertEqual(
            (row["name"], row["model"], row["adapter"], row["base_url"]),
            ("llama3.2", "llama3.2:latest", "ollama", "http://127.0.0.1:11434"),
        )
        self.assertEqual(provider_store.active()["id"], row["id"])
        self.assertEqual(self.probed, [row["id"]])
        # Their saved selection is (local-ollama, llama3.2:latest); it still is.
        listed = [(m["providerID"], m["id"]) for m in self.models()]
        self.assertEqual(listed.count(("local-ollama", "llama3.2:latest")), 1)
        info = self.client.get(f"/oc/api/session/{sid}").json()["data"]
        self.assertEqual(info["model"], ref)
        config = self.client.get("/oc/api/config").json()[0]["info"]["model"]
        self.assertEqual((config["providerID"], config["model"]), ("local-ollama", "llama3.2:latest"))
        default = self.client.get("/oc/api/model/default").json()["data"]
        self.assertEqual((default["providerID"], default["id"]), ("local-ollama", "llama3.2:latest"))
        # Choosing it again reuses the connection rather than making another.
        self.client.post(f"/oc/api/session/{sid}/model", json={"model": dict(ref, variant="high")})
        self.assertEqual(len(provider_store.list_all()), 1)
        self.assertEqual(provider_store.get(row["id"])["effort"], "high")

    def test_a_connection_made_elsewhere_is_the_same_entry_under_either_spelling(self):
        """A connection the harness's settings made as `llama3.2` is the model
        Ollama lists as `llama3.2:latest`: one entry, under the row's name."""
        made = provider_store.create("Mine", "http://localhost:11434", "llama3.2", "ollama")
        listed = [(m["providerID"], m["id"]) for m in self.models()]
        self.assertEqual(listed, [("local-ollama", "llama3.2"), ("local-ollama", "qwen3:8b")])
        sid = self.create()["id"]
        self.client.post(
            f"/oc/api/session/{sid}/model",
            json={"model": {"id": "llama3.2:latest", "providerID": "local-ollama"}},
        )
        self.assertEqual([row["id"] for row in provider_store.list_all()], [made["id"]])
        self.assertEqual(provider_store.active()["id"], made["id"])

    def test_a_model_ollama_does_not_have_is_refused_and_nothing_is_made(self):
        sid = self.create()["id"]
        response = self.client.post(
            f"/oc/api/session/{sid}/model",
            json={"model": {"id": "nowhere:1b", "providerID": "local-ollama"}},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("does not have", response.json()["message"])
        self.assertEqual(provider_store.list_all(), [])

    def test_disconnecting_local_ollama_forgets_its_connections_and_keeps_the_models(self):
        sid = self.create()["id"]
        self.client.post(
            f"/oc/api/session/{sid}/model",
            json={"model": {"id": "qwen3:8b", "providerID": "local-ollama"}},
        )
        got = contract.assert_response(
            self, "integration.get", self.client.get("/oc/api/integration/local-ollama")
        )
        (credential,) = got["data"]["connections"]
        listed = contract.assert_response(self, "integration.list", self.client.get("/oc/api/integration"))
        self.assertNotIn("local-ollama", [item["id"] for item in listed["data"]])
        with mock.patch.object(provider_secrets, "backend", return_value=MemoryKeychain()):
            removed = self.client.delete(f"/oc/api/credential/{credential['id']}")
        contract.assert_response(self, "credential.remove", removed, 204)
        self.assertEqual(provider_store.list_all(), [])
        self.assertIn(("local-ollama", "qwen3:8b"), [(m["providerID"], m["id"]) for m in self.models()])


if __name__ == "__main__":
    unittest.main()
