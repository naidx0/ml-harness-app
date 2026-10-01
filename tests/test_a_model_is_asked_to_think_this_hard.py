"""Effort is a knob on the connection, and each adapter turns it into its own field.

Max, 2026-09-12: *"I'm not seeing an effort system for our models right now."*
`providers.effort` holds one of `store.EFFORTS`; Ollama sends it as `think`
(only for a model whose `/api/show` lists `thinking`), an OpenAI-compatible
server as `reasoning_effort` for the three levels, and `default` sends nothing
anywhere - the wire looks exactly as it did before the knob existed.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app.providers import build, ollama, openai_compatible  # noqa: E402
from app.providers import store as provider_store  # noqa: E402
from test_the_prompt_is_never_silently_truncated import Recorder, a_real_turn, a_reply, shown  # noqa: E402


def _thinking_show() -> bytes:
    body = json.loads(shown(ceiling=1_048_576, num_ctx=65_536))
    body["capabilities"] = ["completion", "tools", "thinking"]
    return json.dumps(body).encode()


class OllamaTest(unittest.TestCase):
    def sent(self, effort: str, show: bytes) -> dict:
        recorder = Recorder({"/api/show": show}, {"/api/chat": a_reply()})
        messages, tools = a_real_turn()
        provider = ollama.OllamaProvider("http://127.0.0.1:11434", "m", opener=recorder, effort=effort)
        list(provider.stream(messages, tools))
        return recorder.sent_to("/api/chat")[0]["payload"]

    def test_default_sends_nothing(self):
        self.assertNotIn("think", self.sent("default", _thinking_show()))

    def test_off_and_the_levels_on_a_thinking_model(self):
        self.assertIs(self.sent("off", _thinking_show())["think"], False)
        for level in ("low", "medium", "high"):
            self.assertIs(self.sent(level, _thinking_show())["think"], True, level)

    def test_a_model_that_cannot_think_is_not_asked_to(self):
        """Ollama answers `think` on such a model with an error, so the field
        stays off the wire whatever the knob says."""
        for level in ("off", "high"):
            self.assertNotIn("think", self.sent(level, shown(ceiling=1_048_576, num_ctx=65_536)), level)


class OpenAICompatibleTest(unittest.TestCase):
    def test_the_levels_go_on_the_wire_and_the_rest_do_not(self):
        adapter = openai_compatible.OpenAICompatibleProvider("http://x/v1", "m", effort="high")
        self.assertEqual(adapter.effort, "high")
        for quiet in ("default", "off"):
            self.assertEqual(
                openai_compatible.OpenAICompatibleProvider("http://x/v1", "m", effort=quiet).effort, quiet
            )


class TheRowCarriesItTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)

    def test_a_row_starts_at_default_and_takes_a_known_value(self):
        row = provider_store.create("Ollama", "http://127.0.0.1:11434", "m", "ollama")
        self.assertEqual(row["effort"], "default")
        row = provider_store.update(row["id"], effort="high")
        self.assertEqual(row["effort"], "high")
        with self.assertRaises(ValueError):
            provider_store.update(row["id"], effort="turbo")
        adapter = build(row["adapter"], row["base_url"], row["model"], effort=row["effort"])
        self.assertEqual(adapter.effort, "high")

    def test_the_route_takes_it(self):
        from app.main import app

        client = support.api_client(app)
        self.addCleanup(client.close)
        row = provider_store.create("Ollama", "http://127.0.0.1:11434", "m", "ollama")
        resp = client.patch(f"/api/providers/{row['id']}", json={"effort": "low"})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["effort"], "low")
        self.assertEqual(client.patch(f"/api/providers/{row['id']}", json={"effort": "turbo"}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
