"""The engine recommends constrained decoding; the product must be able to do it.

MEASURED 2026-09-09, on a real thread. With a representative baseline restored,
`run_diagnosis` returned:

    NO_TRAIN__CONSTRAINED_DECODING
    "Never fine-tune for a format a grammar can enforce."
    Next: JSON schema / structured outputs / GBNF grammar. Format compliance
    becomes 100% by construction.

That verdict was correct -- 13 of 20 labelled failures were `wrong_format` --
and it could not be acted on. There was no `format` on the Ollama adapter, no
`response_format` on the OpenAI-compatible one, and no tool anywhere declaring
`constrained_decoding_tried`. The engine named a move the product could not
make, which is worse than not recommending it: a user follows the advice, finds
no door, and concludes the advice was wrong.

These lock the door open. They do NOT test that constrained decoding improves a
score -- that is a measurement, it needs a model and a baseline beside it, and
asserting it here would be a test that passes on a hope.
"""

from __future__ import annotations

import inspect
import unittest
from typing import Any

from app.providers.ollama import OllamaProvider
from app.tools import measure
from app.tools.registry import REGISTRY


class ConstrainedDecodingIsReachable(unittest.TestCase):
    def test_the_ollama_adapter_accepts_a_response_format(self) -> None:
        params = inspect.signature(OllamaProvider.stream).parameters
        self.assertIn(
            "response_format",
            params,
            "the adapter must be able to carry the schema the engine recommends",
        )
        self.assertIsNone(
            params["response_format"].default,
            "unconstrained stays the default; a baseline is measured without one",
        )

    def test_it_reaches_the_wire_as_ollama_expects(self) -> None:
        """`format` on the request body is what constrains Ollama's generation."""
        sent: dict[str, Any] = {}

        class Recorder(OllamaProvider):  # type: ignore[misc]
            # `/api/show` is probed for the context window before the chat call.
            # Stubbing it keeps this test about the CHAT payload, which is the
            # only place a response_format could be lost.
            def _show(self, secret: str | None):  # noqa: ANN202
                return {}

            def _request(self, path: str, payload: dict[str, Any], secret: str | None):  # noqa: ANN202
                if path != "/api/chat":
                    return super()._request(path, payload, secret)
                sent.update(payload)
                raise RuntimeError("stop here: the payload is what is under test")

        adapter = Recorder("http://127.0.0.1:11434", "x")
        schema = {"type": "object", "properties": {"components": {"type": "array"}}}
        # `_request` is called OUTSIDE the adapter's try block, so the sentinel
        # escapes rather than becoming an error Delta. Catching it here keeps the
        # test about the payload instead of about the adapter's error handling.
        with self.assertRaises(RuntimeError):
            for _ in adapter.stream(
                [{"role": "user", "content": "hi"}], None, secret=None, response_format=schema
            ):
                pass

        self.assertEqual(
            sent.get("format"),
            schema,
            "the schema must be sent as `format`, which is the key Ollama constrains on",
        )

    def test_no_format_is_sent_when_none_is_asked_for(self) -> None:
        """A baseline must not be silently constrained."""
        sent: dict[str, Any] = {}

        class Recorder(OllamaProvider):  # type: ignore[misc]
            def _show(self, secret: str | None):  # noqa: ANN202
                return {}

            def _request(self, path: str, payload: dict[str, Any], secret: str | None):  # noqa: ANN202
                if path != "/api/chat":
                    return super()._request(path, payload, secret)
                sent.update(payload)
                raise RuntimeError("stop here")

        adapter = Recorder("http://127.0.0.1:11434", "x")
        with self.assertRaises(RuntimeError):
            for _ in adapter.stream([{"role": "user", "content": "hi"}], None, secret=None):
                pass
        self.assertNotIn("format", sent, "an unconstrained run must stay unconstrained")

    def test_measure_baseline_offers_it_and_does_not_require_it(self) -> None:
        spec = REGISTRY.get("measure_baseline")
        self.assertIsNotNone(spec)
        props = spec.schema.get("properties") or {}
        self.assertIn("response_format", props, "the tool must expose the door")
        self.assertNotIn(
            "response_format",
            spec.schema.get("required") or (),
            "a baseline is the UNCONSTRAINED number; requiring a schema would delete it",
        )

    def test_ask_carries_it_through(self) -> None:
        params = inspect.signature(measure._ask).parameters
        self.assertIn("response_format", params)


if __name__ == "__main__":
    unittest.main()
