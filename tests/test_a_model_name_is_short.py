"""A model with no nickname is listed under a short name, not its whole id.

Max, 2026-09-22: `hf.co/openbmb/MiniCPM5-1B-GGUF:Q8_0` must read as
`MiniCPM5-1B` in their picker. The registry host and the organisation, the
file format and the quantisation are how the model was fetched, not what it
is; a size tag (`4b`, `3b`) is what it is, and stays. `id`, `modelID` and
`providerID` are untouched: their composer saves the selection by those.
"""
from __future__ import annotations

import base64
import unittest

from fastapi.testclient import TestClient

import openapi_contract as contract
import support
from app import security
from app.facade import catalog
from app.providers import store as provider_store

CASES = [
    ("hf.co/openbmb/MiniCPM5-1B-GGUF:Q8_0", "MiniCPM5-1B"),
    ("hf.co/unsloth/Qwen3-4B-Instruct-2507-GGUF:q4_K_M", "Qwen3-4B-Instruct-2507"),
    ("someone/model-safetensors", "model"),
    ("qwen3.5:4b", "qwen3.5 4b"),
    ("granite4.2:3b", "granite4.2 3b"),
    ("llama3.2:latest", "llama3.2"),
    ("llama3.2", "llama3.2"),
    ("llama3:8b-instruct-q4_K_M", "llama3 8b-instruct"),
    ("gemma3:27b-it-fp16", "gemma3 27b-it"),
    ("minicpm5-hermes:latest", "minicpm5-hermes"),
    ("gpt-9-mini", "gpt-9-mini"),
    ("", ""),
]


class AShortNameTest(unittest.TestCase):
    def test_every_case(self):
        for model_id, expected in CASES:
            with self.subTest(model_id=model_id):
                self.assertEqual(catalog.short_model_name(model_id), expected)

    def test_a_name_that_would_be_empty_is_the_id(self):
        self.assertEqual(catalog.short_model_name("GGUF:Q8_0"), "GGUF:Q8_0")


class ThePickerShowsItTest(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)
        from app.main import app

        raw = base64.b64encode(f"opencode:{security.current_token()}".encode()).decode()
        self.facade = TestClient(app, headers={"Authorization": f"Basic {raw}"})
        self.addCleanup(self.facade.close)

    def listed(self, model_id):
        body = contract.assert_response(self, "model.list", self.facade.get("/oc/api/model"))
        return next(m for m in body["data"] if m["id"] == model_id)

    def test_a_connection_named_after_its_model_is_listed_short_and_keeps_its_ids(self):
        # How `default_model` connects a local model: named after the model id.
        model = "hf.co/openbmb/MiniCPM5-1B-GGUF:Q8_0"
        row = provider_store.create(model, "http://127.0.0.1:11434", model, "ollama")
        provider_store.set_active(row["id"])
        entry = self.listed(model)
        self.assertEqual(entry["name"], "MiniCPM5-1B")
        self.assertEqual((entry["id"], entry["modelID"]), (model, model))
        self.assertEqual(entry["providerID"], catalog.LOCAL_PROVIDER)

    def test_a_nickname_still_wins(self):
        model = "hf.co/openbmb/MiniCPM5-1B-GGUF:Q8_0"
        row = provider_store.create("Tiny", "http://127.0.0.1:11434", model, "ollama")
        provider_store.set_active(row["id"])
        self.assertEqual(self.listed(model)["name"], "Tiny")

    def test_a_model_nobody_connected_is_listed_short(self):
        entry = catalog.discovered_info({"name": "granite4.2:3b", "capabilities": ["tools"]})
        self.assertEqual(entry["name"], "granite4.2 3b")
        self.assertEqual(entry["id"], "granite4.2:3b")


if __name__ == "__main__":
    unittest.main()
