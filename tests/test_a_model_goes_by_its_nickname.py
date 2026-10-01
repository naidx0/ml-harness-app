"""A connected model is listed under the name the person gave it.

Max, 2026-09-22: he wants nicknames for his models. A connection already has
a `name` - the settings page and `PATCH /api/providers/{id} {"name": ...}` edit
it - but their model picker draws `Model.Info.name`, and the facade filled it
with the raw model id, so every entry read `minicpm5-hermes:latest` whatever
he had called it. `id` and `modelID` must stay the model id: their composer
saves the selection as `(providerID, modelID)`, and a rename must not drop it.
"""
from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from fastapi.testclient import TestClient  # noqa: E402

import openapi_contract as contract  # noqa: E402
import support  # noqa: E402
from app import security  # noqa: E402
from app.facade import catalog  # noqa: E402
from app.providers import store as provider_store  # noqa: E402


def _basic(token: str) -> dict[str, str]:
    raw = base64.b64encode(f"opencode:{token}".encode()).decode()
    return {"Authorization": f"Basic {raw}"}


class AModelGoesByItsNickname(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        from app.main import app

        self.facade = TestClient(app, headers=_basic(security.current_token()))
        self.addCleanup(self.facade.close)
        self.engine = support.api_client(app)

    def listed(self, model_id: str) -> dict:
        body = contract.assert_response(self, "model.list", self.facade.get("/oc/api/model"))
        return next(m for m in body["data"] if m["id"] == model_id)

    def test_a_remote_connection_is_listed_under_its_name(self) -> None:
        row = provider_store.create("Sparky", "https://api.example.com/v1", "gpt-9-mini", "openai-compatible")
        provider_store.set_active(row["id"])
        entry = self.listed("gpt-9-mini")
        self.assertEqual(entry["name"], "Sparky")
        self.assertEqual(entry["modelID"], "gpt-9-mini")

    def test_a_local_connection_is_listed_under_its_name(self) -> None:
        row = provider_store.create("Hermes the small", "http://127.0.0.1:11434", "minicpm5-hermes:latest", "ollama")
        provider_store.set_active(row["id"])
        entry = self.listed("minicpm5-hermes:latest")
        self.assertEqual(entry["providerID"], catalog.LOCAL_PROVIDER)
        self.assertEqual(entry["name"], "Hermes the small")

    def test_renaming_the_connection_renames_the_entry_and_keeps_the_id(self) -> None:
        row = provider_store.create("Local", "http://127.0.0.1:11434", "scripted-7b", "ollama")
        provider_store.set_active(row["id"])
        before = self.listed("scripted-7b")
        response = self.engine.patch(f"/api/providers/{row['id']}", json={"name": "Scribbler"})
        self.assertEqual(response.status_code, 200, response.text)
        after = self.listed("scripted-7b")
        self.assertEqual(after["name"], "Scribbler")
        self.assertEqual((after["id"], after["modelID"], after["providerID"]),
                         (before["id"], before["modelID"], before["providerID"]))
        self.assertEqual(catalog.default_model()["name"], "Scribbler")

    def test_a_connection_with_no_name_falls_back_to_the_model_id(self) -> None:
        row = provider_store.create("", "https://api.example.com/v1", "gpt-9-mini", "openai-compatible")
        self.assertEqual(catalog.model_info(provider_store.get(row["id"]))["name"], "gpt-9-mini")


if __name__ == "__main__":
    unittest.main()
