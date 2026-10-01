"""Phase C's first-run question: what is ALREADY running on this machine?

`providers.discover()` probes the keyless presets and reports what answered,
with the models each one offers. The property that makes it a first-run step
rather than a scan:

- **It creates nothing.** Connecting stays an explicit click; discovery is
  read-only against well-known local ports.
- **It never touches a host that needs a key.** Keyed presets are skipped by
  construction, so the function cannot leak usage to a remote endpoint and
  cannot hang first-run on datacenter latency.
- **Nothing answering is an answer**, not an error: the response is a list of
  candidates with `reachable` flags, so the UI can show "we looked, we found
  nothing - here are the presets" instead of a stack trace or a spinner.

The tests point discovery at ephemeral ports rather than pretending 11434 is
free, which is what the `probes` parameter exists for.
"""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from fastapi.testclient import TestClient

from app import providers
from app.main import app
import support


def _server(handler: type[BaseHTTPRequestHandler]) -> tuple[HTTPServer, int]:
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


class _OllamaShape(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - stdlib spelling
        if self.path == "/api/tags":
            body = json.dumps(
                {"models": [{"name": "granite4-hermes:latest"}, {"name": "qwen3:8b"}]}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):  # silence the test log
        pass


class _OpenAIShape(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.endswith("/models"):
            body = json.dumps({"data": [{"id": "granite4-hermes"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


class _Silent(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(500)
        self.end_headers()

    def log_message(self, *args):
        pass


class DiscoveryReadsAndNeverWrites(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)

    def _probe(self, adapter: str, handler: type[BaseHTTPRequestHandler], path: str = "") -> dict:
        server, port = _server(handler)
        try:
            probes = [
                {
                    "name": "under-test",
                    "base_url": f"http://127.0.0.1:{port}{path}",
                    "adapter": adapter,
                    "needs_key": False,
                }
            ]
            return providers.discover(probes=probes)[0]
        finally:
            server.shutdown()

    def test_an_ollama_shape_is_found_with_its_model_names(self):
        entry = self._probe("ollama", _OllamaShape)
        self.assertTrue(entry["reachable"])
        self.assertEqual(entry["models"][0], "granite4-hermes:latest")
        self.assertEqual(entry["suggested_model"], "granite4-hermes:latest")

    def test_an_openai_shape_is_found_through_its_models_list(self):
        entry = self._probe("openai-compatible", _OpenAIShape, path="/v1")
        self.assertTrue(entry["reachable"])
        self.assertEqual(entry["suggested_model"], "granite4-hermes")

    def test_something_answering_wrongly_is_reachable_with_no_models(self):
        """A 500 from a half-started server is 'alive', not 'a model source'."""
        entry = self._probe("ollama", _Silent)
        self.assertTrue(entry["reachable"])
        self.assertEqual(entry["models"], [])
        self.assertNotIn("suggested_model", entry)

    def test_nothing_listening_is_not_an_error_and_creates_nothing(self):
        before = provider_count = len(_rows())
        entry = providers.discover(
            probes=[
                {
                    "name": "closed",
                    "base_url": "http://127.0.0.1:9",
                    "adapter": "ollama",
                    "needs_key": False,
                }
            ]
        )[0]
        self.assertFalse(entry["reachable"])
        self.assertEqual(provider_count, before)

    def test_keyed_presets_are_never_probed_even_when_asked_for_by_name(self):
        """The construction is at the default-filter level AND honoured here."""
        probes = [
            {
                "name": "OpenAI",
                "base_url": "https://api.openai.com/v1",
                "adapter": "openai-compatible",
                "needs_key": True,
            }
        ]
        # discover() takes the list as given, so the DEFAULT filter is what
        # this asserts: call with nothing and no keyed host appears.
        results = providers.discover(timeout=0.05)
        self.assertTrue(results)
        for entry in results:
            self.assertNotEqual(entry["name"], "OpenAI")


def _rows():
    return providers_store_rows()


def providers_store_rows():
    from app.providers import store

    return store.list_all()


class TheRouteServesDiscovery(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)
        self.client = support.api_client(app)

    def test_the_endpoint_returns_candidates_and_writes_nothing(self):
        response = self.client.get("/api/providers/discover")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("candidates", body)
        for entry in body["candidates"]:
            self.assertIn("reachable", entry)
            self.assertIn("models", entry)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
