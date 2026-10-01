"""A tool call written as text is a tool call - for a tool that was offered.

MEASURED 2026-09-23, the owner's model (minicpm5-hermes, a 1B local thinking
model) on a fresh Build/Full thread: in the forced final round it wrote, as its
whole answer, `<function name="profile_repository"></function>` - the call it
wanted, in text. Small local models trained on Hermes or Llama chat templates
write calls this way whenever the server's tool parser misses them, and the
person saw a tag instead of a result.

(c), one case per exit, on both adapters:

  * `<function name="profile_repository">{"path":"."}</function>` in content,
    for an offered tool -> a `tool_call` Delta, marked `from_text`, and no text;
  * the same tag naming a tool that was NOT offered -> text, untouched;
  * `<tool_call>{"name": .., "arguments": ..}</tool_call>` (Hermes) -> a call;
  * a tag split across two chunks -> ONE call and no leaked text;
  * key=value arguments and an empty body are read; a malformed body is text.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.providers import Delta, TextCalls, TEXT_CALL_ID_PREFIX  # noqa: E402
from app.providers import ollama, openai_compatible  # noqa: E402

OFFERED = ("profile_repository", "list_local_models")

WHOLE = '<function name="profile_repository">{"path":"."}</function>'


def _ollama(pieces, offered=OFFERED):
    lines = [
        json.dumps({"message": {"content": piece}, "done": False}) for piece in pieces
    ] + [json.dumps({"message": {"content": ""}, "done": True})]
    return list(ollama.parse_stream(lines, offered=offered))


def _openai(pieces, offered=OFFERED):
    lines = [
        "data: " + json.dumps({"choices": [{"delta": {"content": piece}}]})
        for piece in pieces
    ] + ["data: [DONE]"]
    return list(openai_compatible.parse_stream(lines, offered=offered))


def _text(deltas):
    return "".join(d.text for d in deltas if d.kind == "text")


def _calls(deltas):
    return [c for d in deltas if d.kind == "tool_call" for c in d.tool_calls]


class _BothAdapters:
    """The same six exits, driven through each adapter's own parser."""

    parse = None

    def test_a_whole_function_tag_for_an_offered_tool_is_a_call(self):
        deltas = self.parse(["Let me look. ", WHOLE])
        calls = _calls(deltas)
        self.assertEqual([c.name for c in calls], ["profile_repository"])
        self.assertEqual(calls[0].arguments, {"path": "."})
        self.assertTrue(calls[0].id.startswith(TEXT_CALL_ID_PREFIX))
        self.assertTrue(
            all(d.from_text for d in deltas if d.kind == "tool_call"),
            "the salvage was not marked, so the transcript cannot record it",
        )
        self.assertEqual(_text(deltas), "Let me look. ")
        self.assertNotIn("<function", _text(deltas))

    def test_an_unknown_name_stays_text(self):
        tag = '<function name="start_training">{}</function>'
        deltas = self.parse([tag])
        self.assertEqual(_calls(deltas), [])
        self.assertEqual(_text(deltas), tag)

    def test_the_hermes_tool_call_form_is_a_call(self):
        tag = (
            '<tool_call>{"name": "list_local_models", "arguments": {"verbose": true}}'
            "</tool_call>"
        )
        calls = _calls(self.parse([tag]))
        self.assertEqual([c.name for c in calls], ["list_local_models"])
        self.assertEqual(calls[0].arguments, {"verbose": True})

    def test_a_tag_split_across_chunks_is_one_call_and_leaks_nothing(self):
        cut = WHOLE.index("repo")
        deltas = self.parse(["Checking <fun", WHOLE[len("<fun"):cut], WHOLE[cut:]])
        self.assertEqual([c.name for c in _calls(deltas)], ["profile_repository"])
        self.assertEqual(_text(deltas), "Checking ")

    def test_the_empty_body_the_owners_model_wrote_is_a_call(self):
        calls = _calls(self.parse(['<function name="profile_repository"></function>']))
        self.assertEqual([(c.name, c.arguments) for c in calls], [("profile_repository", {})])

    def test_key_value_arguments_are_read(self):
        calls = _calls(
            self.parse(['<function name="profile_repository">path=".", depth=2</function>'])
        )
        self.assertEqual(calls[0].arguments, {"path": ".", "depth": 2})

    def test_a_malformed_body_is_left_as_text(self):
        tag = '<function name="profile_repository">{"path": </function>'
        deltas = self.parse([tag])
        self.assertEqual(_calls(deltas), [])
        self.assertEqual(_text(deltas), tag)

    def test_an_unclosed_tag_is_text_at_the_end(self):
        deltas = self.parse(['a <function name="profile_repository">{"path": "."}'])
        self.assertEqual(_calls(deltas), [])
        self.assertEqual(_text(deltas), 'a <function name="profile_repository">{"path": "."}')

    def test_nothing_offered_means_nothing_salvaged(self):
        """The forced final round offers no tools; its text is its text."""
        deltas = self.parse([WHOLE], offered=None)
        self.assertEqual(_calls(deltas), [])
        self.assertEqual(_text(deltas), WHOLE)

    def test_a_less_than_sign_is_not_held_forever(self):
        deltas = self.parse(["if a < b then ", "c <", "3"])
        self.assertEqual(_text(deltas), "if a < b then c <3")


class TheOllamaAdapterSalvagesTest(_BothAdapters, unittest.TestCase):
    parse = staticmethod(_ollama)


class TheOpenAICompatibleAdapterSalvagesTest(_BothAdapters, unittest.TestCase):
    parse = staticmethod(_openai)


class TheStreamPassesTheOfferedNamesTest(unittest.TestCase):
    """THROUGH `stream()`: the adapter reads the names off the tools it sent."""

    def test_ollama_stream_salvages_an_offered_tool(self):
        lines = [
            json.dumps({"message": {"content": WHOLE}, "done": False}).encode(),
            json.dumps({"message": {"content": ""}, "done": True}).encode(),
        ]

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def __iter__(self):
                return iter(lines)

            def read(self):
                return b"{}"

        provider = ollama.OllamaProvider(
            "http://127.0.0.1:11434", "m", opener=lambda request, timeout=None: Response()
        )
        tools = [
            {"type": "function", "function": {"name": "profile_repository", "parameters": {}}}
        ]
        deltas = list(provider.stream([{"role": "user", "content": "hi"}], tools))
        self.assertEqual([c.name for c in _calls(deltas)], ["profile_repository"], deltas)


class TheSalvagerOnItsOwnTest(unittest.TestCase):
    def test_close_flushes_a_held_prefix_as_text(self):
        salvager = TextCalls(OFFERED)
        out = salvager.feed("ends with <tool_ca")
        out += salvager.close()
        self.assertEqual("".join(d.text for d in out), "ends with <tool_ca")
        self.assertTrue(all(isinstance(d, Delta) for d in out))


if __name__ == "__main__":
    unittest.main()
