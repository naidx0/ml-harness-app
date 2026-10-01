"""The two adapters, and the parsing that is where the risk actually lives.

No network. Every call goes through an injectable opener, which is not a
convenience: the cases that matter - a malformed frame mid-stream, a tool call
whose arguments arrive in four pieces, a server that returns half a call - are
cases a live server will not produce on demand.
"""

from __future__ import annotations

import io
import json
import unittest

from app import providers
from app.providers import ollama, openai_compatible


class FakeResponse:
    """A context manager that iterates byte lines, like `urlopen` does."""

    def __init__(self, lines, body=b""):
        self._lines = list(lines)
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(self._lines)

    def read(self):
        return self._body


def opener_for(lines=(), body=b"", captured=None):
    def opener(request, timeout=None):
        if captured is not None:
            captured["url"] = request.full_url
            captured["headers"] = dict(request.headers)
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
        return FakeResponse(lines, body)

    return opener


class ClassifyTest(unittest.TestCase):
    def test_loopback_and_dot_local_are_local(self):
        for url in (
            "http://127.0.0.1:11434",
            "http://localhost:1234/v1",
            "http://[::1]:8080/v1",
            "http://0.0.0.0:8000/v1",
            "http://workstation.local:11434",
        ):
            with self.subTest(url=url):
                self.assertEqual(providers.classify(url), "local")

    def test_everything_else_is_remote_including_nonsense(self):
        """Unknown is remote. The egress guard reads this field."""
        for url in (
            "https://api.openai.com/v1",
            "https://openrouter.ai/api/v1",
            "",
            "not a url at all",
            None,
            "http://192.168.0.9:11434",
        ):
            with self.subTest(url=url):
                self.assertEqual(providers.classify(url), "remote")

    def test_the_local_presets_really_are_local(self):
        self.assertGreaterEqual(len(providers.PRESETS), 5)
        for preset in providers.PRESETS:
            with self.subTest(preset=preset["name"]):
                self.assertIn(preset["adapter"], providers.ADAPTERS)
                if not preset["needs_key"]:
                    self.assertEqual(providers.classify(preset["base_url"]), "local")


class OpenAICompatibleParsingTest(unittest.TestCase):
    def test_text_deltas_stream_and_done_stops_the_stream(self):
        lines = [
            'data: {"choices":[{"delta":{"content":"Hel"}}]}',
            "",
            'data: {"choices":[{"delta":{"content":"lo"}}]}',
            "data: not json at all",
            'data: {"choices":[{"delta":{}}]}',
            "data: [DONE]",
            'data: {"choices":[{"delta":{"content":"after the end"}}]}',
        ]
        deltas = list(openai_compatible.parse_stream(lines))
        self.assertEqual(
            "".join(d.text for d in deltas if d.kind == "text"), "Hello"
        )

    def test_a_malformed_frame_does_not_kill_the_reply(self):
        lines = [
            'data: {"choices":[{"delta":{"content":"a"}}]}',
            "data: {truncated",
            'data: {"choices":[{"delta":{"content":"b"}}]}',
        ]
        text = "".join(
            d.text for d in openai_compatible.parse_stream(lines) if d.kind == "text"
        )
        self.assertEqual(text, "ab")

    def test_a_tool_call_split_across_chunks_is_reassembled(self):
        """The silent failure this accumulator exists to prevent.

        A call emitted with half its arguments is a tool that runs on partial
        input, and nothing downstream would notice.
        """
        lines = [
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_a",'
            '"function":{"name":"list_runs","arguments":"{\\"li"}}]}}]}',
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
            '"function":{"arguments":"mit\\": 5}"}}]}}]}',
            "data: [DONE]",
        ]
        deltas = [d for d in openai_compatible.parse_stream(lines) if d.kind == "tool_call"]
        self.assertEqual(len(deltas), 1)
        call = deltas[0].tool_calls[0]
        self.assertEqual(call.id, "call_a")
        self.assertEqual(call.name, "list_runs")
        self.assertEqual(call.arguments, {"limit": 5})

    def test_two_parallel_calls_stay_separate(self):
        lines = [
            'data: {"choices":[{"delta":{"tool_calls":['
            '{"index":0,"id":"a","function":{"name":"inspect_hardware","arguments":"{}"}},'
            '{"index":1,"id":"b","function":{"name":"list_runs","arguments":"{}"}}'
            "]}}]}",
            "data: [DONE]",
        ]
        calls = [
            c
            for d in openai_compatible.parse_stream(lines)
            if d.kind == "tool_call"
            for c in d.tool_calls
        ]
        self.assertEqual([c.name for c in calls], ["inspect_hardware", "list_runs"])

    def test_arguments_that_do_not_parse_become_an_error_never_a_guess(self):
        lines = [
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"a",'
            '"function":{"name":"list_runs","arguments":"{not json"}}]}}]}',
            "data: [DONE]",
        ]
        deltas = list(openai_compatible.parse_stream(lines))
        self.assertEqual([d.kind for d in deltas], ["error"])
        self.assertIn("did not parse", deltas[0].detail)

    def test_a_call_with_no_name_is_reported_not_invented(self):
        lines = [
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
            '"function":{"arguments":"{}"}}]}}]}',
            "data: [DONE]",
        ]
        deltas = list(openai_compatible.parse_stream(lines))
        self.assertEqual([d.kind for d in deltas], ["error"])


class OpenAICompatibleRequestTest(unittest.TestCase):
    def test_no_authorization_header_without_a_key(self):
        """A local server handed `Bearer None` is a support ticket."""
        captured = {}
        provider = openai_compatible.OpenAICompatibleProvider(
            "http://127.0.0.1:1234/v1", "m", opener=opener_for(["data: [DONE]"], captured=captured)
        )
        list(provider.stream([], None))
        self.assertNotIn("Authorization", captured["headers"])
        self.assertNotIn("tools", captured["body"])

    def test_the_key_is_sent_only_when_there_is_one(self):
        captured = {}
        provider = openai_compatible.OpenAICompatibleProvider(
            "https://api.example.com/v1",
            "m",
            opener=opener_for(["data: [DONE]"], captured=captured),
        )
        list(provider.stream([], None, secret="sk-abc"))
        self.assertEqual(captured["headers"]["Authorization"], "Bearer sk-abc")

    def test_tools_are_absent_rather_than_null(self):
        """Some OpenAI-compatible servers reject an explicit null."""
        captured = {}
        provider = openai_compatible.OpenAICompatibleProvider(
            "http://127.0.0.1:1234/v1", "m", opener=opener_for(["data: [DONE]"], captured=captured)
        )
        list(provider.stream([], []))
        self.assertNotIn("tools", captured["body"])
        list(provider.stream([], [{"type": "function"}]))
        self.assertIn("tools", captured["body"])

    def test_an_unreachable_endpoint_becomes_an_error_delta(self):
        def broken(request, timeout=None):
            raise OSError("connection refused")

        provider = openai_compatible.OpenAICompatibleProvider(
            "http://127.0.0.1:9/v1", "m", opener=broken
        )
        deltas = list(provider.stream([], None))
        self.assertEqual([d.kind for d in deltas], ["error"])
        self.assertIn("connection refused", deltas[0].detail)

    def test_the_capability_probe_reports_measured_or_defaulted(self):
        called = openai_compatible.OpenAICompatibleProvider(
            "https://api.example.com/v1",
            "m",
            opener=opener_for(
                body=json.dumps(
                    {"choices": [{"message": {"tool_calls": [{"id": "a"}]}}]}
                ).encode()
            ),
        ).capabilities()
        self.assertIs(called.tool_calling, True)
        self.assertEqual(called.provenance["tool_calling"], "measured")

        talked = openai_compatible.OpenAICompatibleProvider(
            "https://api.example.com/v1",
            "m",
            opener=opener_for(
                body=json.dumps(
                    {"choices": [{"message": {"content": "Sure, I will!"}}]}
                ).encode()
            ),
        ).capabilities()
        self.assertIs(talked.tool_calling, False)
        self.assertEqual(talked.provenance["tool_calling"], "measured")

    def test_an_unreachable_probe_is_unknown_not_false(self):
        """Not probed and probed-and-no are different facts."""

        def broken(request, timeout=None):
            raise OSError("nobody home")

        caps = openai_compatible.OpenAICompatibleProvider(
            "https://api.example.com/v1", "m", opener=broken
        ).capabilities()
        self.assertIsNone(caps.tool_calling)
        self.assertEqual(caps.provenance["tool_calling"], "defaulted")


class OllamaTest(unittest.TestCase):
    def test_newline_delimited_json_streams(self):
        lines = [
            json.dumps({"message": {"content": "Hel"}, "done": False}),
            "",
            json.dumps({"message": {"content": "lo"}, "done": False}),
            "not json",
            json.dumps({"message": {"content": ""}, "done": True}),
            json.dumps({"message": {"content": "after done"}, "done": False}),
        ]
        text = "".join(d.text for d in ollama.parse_stream(lines) if d.kind == "text")
        self.assertEqual(text, "Hello")

    def test_a_tool_call_arrives_whole(self):
        lines = [
            json.dumps(
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {"function": {"name": "list_runs", "arguments": {"limit": 3}}}
                        ],
                    },
                    "done": True,
                }
            )
        ]
        calls = [
            c for d in ollama.parse_stream(lines) if d.kind == "tool_call" for c in d.tool_calls
        ]
        self.assertEqual(calls[0].name, "list_runs")
        self.assertEqual(calls[0].arguments, {"limit": 3})

    def test_an_error_line_becomes_an_error_delta(self):
        deltas = list(ollama.parse_stream([json.dumps({"error": "model not found"})]))
        self.assertEqual([d.kind for d in deltas], ["error"])
        self.assertIn("model not found", deltas[0].detail)

    def test_a_v1_suffix_is_stripped_rather_than_rejected(self):
        provider = ollama.OllamaProvider("http://127.0.0.1:11434/v1", "m")
        self.assertEqual(provider.base_url, "http://127.0.0.1:11434")
        self.assertEqual(provider.locality, "local")

    def test_capabilities_prefers_the_server_over_a_probe(self):
        shown = {
            "capabilities": ["completion", "tools"],
            "model_info": {"qwen3.context_length": 40960},
        }
        caps = ollama.OllamaProvider(
            "http://127.0.0.1:11434", "m", opener=opener_for(body=json.dumps(shown).encode())
        ).capabilities()
        self.assertIs(caps.tool_calling, True)
        self.assertEqual(caps.ctx_len, 40960)
        self.assertEqual(caps.provenance["ctx_len"], "measured")

    def test_an_unknown_context_length_is_none_and_defaulted(self):
        """Invariant 5: a number nobody measured is not a number we hold."""
        caps = ollama.OllamaProvider(
            "http://127.0.0.1:11434",
            "m",
            opener=opener_for(body=json.dumps({"capabilities": ["completion"]}).encode()),
        ).capabilities()
        self.assertIsNone(caps.ctx_len)
        self.assertEqual(caps.provenance["ctx_len"], "defaulted")
        self.assertIs(caps.tool_calling, False)


class WireShapeTest(unittest.TestCase):
    """The two servers disagree about tool messages. Found on a live model.

    A real Ollama turn failed on the second round with
    `HTTP 400: Value looks like object, but can't find closing '}' symbol`,
    which names neither the field nor the message. The cause was the
    OpenAI-shaped `arguments` JSON *string* being sent to a server that wants
    an *object*. These assertions are the regression.
    """

    NEUTRAL = [
        {"role": "system", "content": "laws"},
        {"role": "user", "content": "what gpu"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "c1", "name": "inspect_hardware", "arguments": {"a": 1}}
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "c1",
            "name": "inspect_hardware",
            "content": "8 GB",
        },
    ]

    def test_openai_wants_arguments_as_a_json_string_and_a_tool_call_id(self):
        wire = openai_compatible.to_wire(self.NEUTRAL)
        call = wire[2]["tool_calls"][0]
        self.assertEqual(call["type"], "function")
        self.assertIsInstance(call["function"]["arguments"], str)
        self.assertEqual(json.loads(call["function"]["arguments"]), {"a": 1})
        self.assertEqual(wire[3]["tool_call_id"], "c1")
        self.assertNotIn("tool_name", wire[3])

    def test_ollama_wants_arguments_as_an_object_and_a_tool_name(self):
        wire = ollama.to_wire(self.NEUTRAL)
        call = wire[2]["tool_calls"][0]
        self.assertIsInstance(call["function"]["arguments"], dict)
        self.assertEqual(call["function"]["arguments"], {"a": 1})
        self.assertEqual(wire[3]["tool_name"], "inspect_hardware")
        self.assertNotIn("tool_call_id", wire[3])

    def test_plain_messages_pass_through_both_unchanged(self):
        plain = [{"role": "user", "content": "hello"}]
        self.assertEqual(
            openai_compatible.to_wire(plain), [{"role": "user", "content": "hello"}]
        )
        self.assertEqual(
            ollama.to_wire(plain), [{"role": "user", "content": "hello"}]
        )

    def test_an_http_error_carries_what_the_server_said(self):
        """A bare status code is a support ticket. The body is the diagnosis."""
        import urllib.error

        class Failing:
            def __call__(self, request, timeout=None):
                raise urllib.error.HTTPError(
                    request.full_url, 400, "Bad Request", {}, io.BytesIO(
                        b'{"error":"Value looks like object"}'
                    )
                )

        provider = ollama.OllamaProvider(
            "http://127.0.0.1:11434", "m", opener=Failing()
        )
        deltas = list(provider.stream([], None))
        self.assertEqual(deltas[0].kind, "error")
        self.assertIn("HTTP 400", deltas[0].detail)
        self.assertIn("Value looks like object", deltas[0].detail)


class BuildTest(unittest.TestCase):
    def test_build_returns_the_named_adapter(self):
        self.assertEqual(
            providers.build("ollama", "http://127.0.0.1:11434", "m").id, "ollama"
        )
        self.assertEqual(
            providers.build("openai-compatible", "https://x/v1", "m").id,
            "openai-compatible",
        )

    def test_an_unknown_adapter_is_refused(self):
        with self.assertRaises(ValueError):
            providers.build("anthropic", "https://api.anthropic.com", "m")

    def test_both_adapters_satisfy_the_protocol(self):
        for adapter in ("ollama", "openai-compatible"):
            with self.subTest(adapter=adapter):
                built = providers.build(adapter, "http://127.0.0.1:1/v1", "m")
                self.assertIsInstance(built, providers.Provider)


class MagnitudeIsFoundWithoutBeingConfiguredTest(unittest.TestCase):
    """The one-click local setup the owner asked for, by name.

    2026-09-11: *"I kinda wanna implement is a one-click local AI setup. I
    think there already exists something called magnitude... it's a one-click
    AI setup for any local application."*

    It serves an OpenAI-compatible API, so nothing had to be integrated - the
    endpoint joins the keyless presets and `discover()` finds it on first run
    like any other local daemon. What these hold is that it STAYS findable:
    the path is unusual enough that a tidy could shorten it to `/v1` and the
    probe would quietly stop reaching anything.
    """

    def preset(self):
        found = [p for p in providers.PRESETS if p["name"] == "Magnitude"]
        self.assertEqual(len(found), 1, "expected exactly one Magnitude preset")
        return found[0]

    def test_it_is_on_the_list_discovery_actually_probes(self):
        #: `discover()` probes `[p for p in PRESETS if not p["needs_key"]]`.
        #: A preset that needs a key is never probed, so needing one would
        #: take it off the first-run screen entirely.
        self.assertFalse(self.preset()["needs_key"])

    def test_the_path_is_the_one_magnitude_documents(self):
        #: docs.magnitude.dev names the OpenAI-compatible API at
        #: 127.0.0.1:10100/inference/v1, read 2026-09-11. `discover()` asks
        #: for `{base_url}/models`, so the whole prefix has to be here.
        self.assertEqual(
            self.preset()["base_url"],
            "http://127.0.0.1:10100/inference/v1",
        )
        self.assertEqual(self.preset()["adapter"], "openai-compatible")

    def test_it_does_not_collide_with_another_local_daemon(self):
        #: `discover()` skips a (base_url, adapter) pair it has already seen,
        #: so a port clash would silently drop one of the two.
        keyless = [p for p in providers.PRESETS if not p["needs_key"]]
        pairs = [(p["base_url"].rstrip("/"), p["adapter"]) for p in keyless]
        self.assertEqual(len(pairs), len(set(pairs)))


if __name__ == "__main__":
    unittest.main()
