"""A thinking model that answers only in its reasoning has answered.

Max's run of 2026-09-21 ended with the harness's own sentence: "The model
answered with nothing - no words and no tool calls - twice, including when
asked directly for a plain answer." The machine's note on this is old: Ollama
thinking models answer in `reasoning`, not `content`, and only
`reasoning_effort: none` turns that off (`think: false` is ignored). Both
adapters dropped the field - Ollama's `message.thinking`, and the
OpenAI-compatible `delta.reasoning` / `reasoning_content` - so a reply made of
reasoning reached the conductor as nothing, was retried with a paragraph, and
was reported as silence.

Locked here: the adapters read the field; the conductor streams it as its own
kind and, when it is all the model said, makes it the answer; a truly empty
reply is retried once with ONE short instruction; and the closing sentence
quotes what was tried. The baseline's own ask reads it too.
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
from app import conductor, events  # noqa: E402
from app.providers import Delta, ollama, openai_compatible  # noqa: E402
from app.providers import store as provider_store  # noqa: E402
from app.tools import measure  # noqa: E402


class Scripted:
    id = "fake"
    locality = "local"

    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.seen = []

    def stream(self, messages, tools=None, *, secret=None, **_):
        self.seen.append([dict(m) for m in messages])
        for delta in (self.scripts.pop(0) if self.scripts else []):
            yield delta

    def capabilities(self, *, secret=None):
        raise AssertionError("no probe mid-turn")


def thinks(*pieces):
    return [Delta(kind="reasoning", text=piece) for piece in pieces]


class TheAdaptersReadTheReasoning(unittest.TestCase):
    def test_ollama_native_thinking_is_a_reasoning_delta(self) -> None:
        lines = [
            json.dumps({"message": {"role": "assistant", "content": "", "thinking": "Let me see."}}),
            json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}),
        ]
        deltas = list(ollama.parse_stream(lines))
        self.assertEqual([(d.kind, d.text) for d in deltas], [("reasoning", "Let me see.")])

    def test_openai_compatible_reasoning_fields_are_reasoning_deltas(self) -> None:
        for field in ("reasoning", "reasoning_content", "reasoning_text"):
            with self.subTest(field=field):
                frame = {"choices": [{"delta": {field: "Thinking it over."}}]}
                deltas = list(openai_compatible.parse_stream(["data: " + json.dumps(frame), "data: [DONE]"]))
                self.assertEqual([(d.kind, d.text) for d in deltas], [("reasoning", "Thinking it over.")])

    def test_the_baseline_ask_reads_an_answer_given_as_reasoning(self) -> None:
        text, error = measure._ask(Scripted([thinks("positive")]), None, "Is this good?")
        self.assertIsNone(error)
        self.assertEqual(text, "positive")


class TheConductorNeverCallsReasoningSilence(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        row = provider_store.create("Fake", "http://127.0.0.1:11434", "fake-model", "ollama")
        provider_store.set_active(row["id"])

    def install(self, provider):
        original = conductor.build
        conductor.build = lambda *a, **k: provider
        self.addCleanup(setattr, conductor, "build", original)
        return provider

    def turn(self, provider, question="what did the baseline score?"):
        self.install(provider)
        thread = int(events.create_thread("t")["id"])
        events.add_message(thread, "user", question)
        list(conductor.run_turn(thread))
        return thread, events.since(f"thread:{thread}", limit=100_000)

    def test_a_reasoning_only_reply_is_the_answer(self) -> None:
        thread, rows = self.turn(Scripted([thinks("The baseline ", "scored 0 of 20 rows.")]))
        end = [r for r in rows if r["kind"] == "stream.end"][-1]["payload"]
        self.assertEqual(end["ending"], "answered", end)
        self.assertEqual(end["closed_by"], "model")
        spoken = "".join(r["payload"]["text"] for r in rows if r["kind"] == "chat.delta")
        self.assertIn("scored 0 of 20 rows", spoken)
        self.assertTrue(
            any(r["kind"] == "conductor.notice" and r["payload"].get("reason") == "answer_was_in_reasoning" for r in rows)
        )

    def test_reasoning_streams_as_its_own_kind_not_as_the_reply(self) -> None:
        thread, rows = self.turn(Scripted([thinks("Weighing the rows. ") + [Delta(kind="text", text="It scored zero.")]]))
        thinking = "".join(r["payload"]["text"] for r in rows if r["kind"] == conductor.REASONING_KIND)
        spoken = "".join(r["payload"]["text"] for r in rows if r["kind"] == "chat.delta")
        self.assertEqual(thinking, "Weighing the rows. ")
        self.assertEqual(spoken, "It scored zero.")
        first_thought = min(r["id"] for r in rows if r["kind"] == conductor.REASONING_KIND)
        first_word = min(r["id"] for r in rows if r["kind"] == "chat.delta")
        self.assertLess(first_thought, first_word, "the thinking is shown as it happens")

    def test_a_truly_empty_reply_is_retried_once_in_one_line_and_the_report_says_so(self) -> None:
        provider = Scripted([[], []])
        thread, rows = self.turn(provider)
        end = [r for r in rows if r["kind"] == "stream.end"][-1]["payload"]
        self.assertEqual(end["ending"], "empty_reply")
        self.assertEqual(len(provider.seen), 2, "one retry, not zero and not three")
        retry = provider.seen[1][-1]
        self.assertEqual(retry["role"], "user")
        self.assertIn("Your last reply was empty", retry["content"])
        self.assertLess(len(retry["content"]), 160)
        closing = [r["payload"]["text"] for r in rows if r["kind"] == "chat.delta" and r["payload"].get("written_by") == "harness"][-1]
        self.assertIn("I asked once more, in one line", closing)
        self.assertIn(retry["content"].replace("[harness] ", ""), closing)
        self.assertIn("no reasoning", closing)


if __name__ == "__main__":
    unittest.main()
