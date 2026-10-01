"""A model that thinks the same paragraph over and over is cut short, once.

Thread 93, 2026-09-23 14:12-14:15, Full mode, minicpm5-hermes on the owner's
machine: ONE model call produced 471 `chat.reasoning` rows over 3.3 minutes
and no tool call. The thinking was the same paragraph about twelve times,
nearly verbatim - "Actually, I think I'm overcomplicating this. Let me just
call state_facts with tabular_rows and see what the tool does..." - and then
the turn ended `answer_was_in_reasoning`, the loop was promoted to the reply,
and the reply was withheld for a number it had invented.

Nothing noticed. The loop the conductor already catches (`repeat_loop`) is
the same TOOL CALL across rounds; a model going round in circles inside one
call never reaches a round boundary to be caught at.

One case per exit, and each is a case only that exit can pass:

- the paragraph twelve times: the call is cut inside the third copy, the
  transcript says why, and the model is asked once more with a nudge that
  names one move - and the tool it then calls runs;
- the second call loops too: the turn ends `reasoning_loop` in the harness's
  words, and nothing from the loop is shown as an answer;
- a long think that never repeats itself is never cut;
- a person's Stop during a loop is still the person's stop - the two cuts do
  not borrow each other's ending.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402,F401
from app import conductor, events, interrupt  # noqa: E402
from app.providers import Delta, ToolCall  # noqa: E402
from test_a_turn_always_speaks import TurnTestCase  # noqa: E402

#: The owner's paragraph, one line per piece the way a thinking model streams
#: it. Built around the lines thread 93 repeated; about 900 characters, so a
#: copy is well over the breaker's window plus its gap.
PARAGRAPH = [
    "Actually, I think I'm overcomplicating this.\n",
    "Let me just call state_facts with tabular_rows and see what the tool does.\n",
    "But I need a value.\n",
    "OK, let me just call profile_repository on the train.jsonl file and count the rows.\n",
    "Wait, the brief says the next step is to settle tabular_rows, not to profile.\n",
    "The person asked whether they should fine-tune, and the diagnosis is waiting on this fact.\n",
    "If the data is tabular, the answer changes, so I should decide it from what I have read.\n",
    "I have read the file listing, which shows train.jsonl and a README.\n",
    "The README describes support tickets with a label column, which is text, not a table.\n",
    "So tabular_rows is probably false, but I am not certain without looking at a row.\n",
    "Hmm, under Full I should not ask the person, I should call the tool myself.\n",
    "So the right move is one tool call, and then run_diagnosis again.\n",
]
LINES = len(PARAGRAPH)


def _count(rows, reason):
    return [
        r["payload"] for r in rows
        if r["kind"] == "conductor.notice" and r["payload"].get("reason") == reason
    ]


class Looper:
    """A model whose rounds are scripted, and whose looping rounds can be cut.

    A round is `"loop"` - the paragraph twelve times as reasoning, a line per
    piece - or a list of deltas. For every round it records how many pieces
    it handed up and whether it was closed before it had finished, which is
    the only way a test can see that the call was ended rather than read to
    its end and ignored.
    """

    id = "looper"
    locality = "local"

    def __init__(self, rounds, *, press_stop_at=None, thread_id=None):
        self.rounds = list(rounds)
        self.seen: list[list[dict]] = []
        self.handed: list[int] = []
        self.cut: list[bool] = []
        self.press_stop_at = press_stop_at
        self.thread_id = thread_id

    def stream(self, messages, tools=None, *, secret=None):
        self.seen.append([dict(m) for m in messages])
        script = self.rounds.pop(0) if self.rounds else []
        index = len(self.handed)
        self.handed.append(0)
        self.cut.append(True)
        pieces = (
            [Delta(kind="reasoning", text=line) for line in PARAGRAPH * 12]
            if script == "loop"
            else list(script)
        )
        # A close before the last piece raises GeneratorExit at the `yield`,
        # so `cut` stays True only for a call that was ended from outside.
        for piece in pieces:
            if self.press_stop_at is not None and self.press_stop_at == (index, self.handed[index]):
                interrupt.ask_to_stop(self.thread_id)
            self.handed[index] += 1
            yield piece
        self.cut[index] = False

    def capabilities(self, *, secret=None):
        raise AssertionError("the loop must not probe mid-turn")


def _list_runs():
    return [Delta(kind="tool_call", tool_calls=(ToolCall("t1", "list_runs", {"limit": 1}),))]


class AModelThatRepeatsItselfIsCutShortTest(TurnTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.addCleanup(lambda: [interrupt.clear(t) for t in interrupt.waiting()])

    def _turn(self, provider, thread_id=None, *, next_move=""):
        self.connect()
        thread_id = thread_id if thread_id is not None else self.new_thread()
        provider.thread_id = thread_id
        self.install(provider)
        # WHICH next-move line the nudge carries is `_next_move_line`'s
        # business and another lane's; this file only pins that the nudge
        # carries it when there is one and the fallback when there is not.
        with mock.patch.object(conductor, "_next_move_line", return_value=next_move):
            rows = list(conductor.run_turn(thread_id, max_tool_rounds=8))
        return thread_id, rows

    def test_the_owners_loop_is_cut_inside_the_third_copy_and_the_next_round_acts(self):
        provider = Looper(["loop", _list_runs(), [Delta(kind="text", text="There are no runs yet.")]])
        thread_id, rows = self._turn(provider)

        # CUT, not read to the end: the fake never finished its first round,
        # and it had handed up more than two copies and not all of a third.
        self.assertTrue(provider.cut[0], "the looping call was read to its end")
        self.assertGreater(provider.handed[0], 2 * LINES, "cut before the third copy began")
        self.assertLessEqual(
            provider.handed[0], 3 * LINES,
            f"not cut within the third copy: {provider.handed[0]} lines of {12 * LINES}",
        )

        notices = _count(rows, "reasoning_loop")
        self.assertEqual(len(notices), 1, f"the transcript does not say why, once: {notices}")
        self.assertGreaterEqual(notices[0]["repeats"], 3)
        self.assertTrue(notices[0]["window"])
        self.assertLessEqual(len(notices[0]["window"]), 80)
        self.assertIn(notices[0]["window"], " ".join("".join(PARAGRAPH * 3).split()))

        # THE NUDGE is in the next request, as the last message, from nobody.
        self.assertGreaterEqual(len(provider.seen), 2, "the model was not asked again")
        nudge = provider.seen[1][-1]
        self.assertEqual(nudge["role"], "user")
        self.assertIn(
            f"You repeated the same reasoning {notices[0]['repeats']} times without acting. "
            "Do not think further: call one tool now.",
            nudge["content"],
        )
        self.assertIn("Call the tool the last refusal named.", nudge["content"])
        stored = [m["content"] for m in events.messages_for(thread_id)]
        self.assertFalse(
            any("You repeated the same reasoning" in c for c in stored),
            "the harness's nudge was stored as a message someone said",
        )

        # AND THE TOOL IT THEN CALLED RAN.
        calls = [r["payload"] for r in rows if r["kind"] == "tool.call"]
        self.assertEqual([c.get("name") for c in calls], ["list_runs"])
        self.assertEqual(len([r for r in rows if r["kind"] == "tool.result"]), 1)

        end = [r for r in rows if r["kind"] == events.END_KIND][-1]["payload"]
        self.assertEqual(end["ending"], "answered", end)
        self.assertEqual(end["closed_by"], "model")

        # What happened stays in the transcript: the loop is shown as thinking.
        thinking = "".join(r["payload"]["text"] for r in rows if r["kind"] == conductor.REASONING_KIND)
        self.assertGreaterEqual(thinking.count(PARAGRAPH[0]), 2)
        self.assertEqual(_count(rows, "answer_was_in_reasoning"), [])
        # The harness's own cut is not the person's stop.
        self.assertEqual(_count(rows, interrupt.ENDING), [])

    def test_the_nudge_carries_the_diagnosis_next_move_when_there_is_one(self):
        move = "next move: run profile_repository for tabular_rows - then run_diagnosis again, not before"
        provider = Looper(["loop", [Delta(kind="text", text="Done.")]])
        _thread, rows = self._turn(provider, next_move=move)
        self.assertGreaterEqual(len(provider.seen), 2)
        nudge = provider.seen[1][-1]["content"]
        self.assertIn("run profile_repository for tabular_rows", nudge)
        self.assertNotIn("Call the tool the last refusal named.", nudge)

    def test_a_second_loop_ends_the_turn_in_the_harness_words(self):
        provider = Looper(["loop", "loop", [Delta(kind="text", text="never asked for")]])
        _thread, rows = self._turn(provider)

        self.assertEqual(len(provider.seen), 2, "one extra round, not zero and not two")
        self.assertTrue(all(provider.cut), "a looping call was read to its end")
        self.assertEqual(len(_count(rows, "reasoning_loop")), 2)

        end = [r for r in rows if r["kind"] == events.END_KIND][-1]["payload"]
        self.assertEqual(end["ending"], "reasoning_loop", end)
        self.assertEqual(end["closed_by"], "harness")
        self.assertIn("reasoning_loop", conductor.SILENT_TURN)
        closings = [
            r["payload"] for r in rows
            if r["kind"] == "chat.delta" and r["payload"].get("written_by") == "harness"
        ]
        self.assertEqual(len(closings), 1)
        self.assertEqual(closings[0]["text"], conductor.SILENT_TURN["reasoning_loop"])

        # NOTHING FROM THE LOOP IS THE ANSWER.
        self.assertEqual(_count(rows, "answer_was_in_reasoning"), [])
        spoken = [
            r["payload"]["text"] for r in rows
            if r["kind"] == "chat.delta" and r["payload"].get("written_by") != "harness"
        ]
        self.assertEqual(spoken, [], "the loop was shown as the reply")
        self.assertFalse(any(line.strip() in closings[0]["text"] for line in PARAGRAPH))

    def test_a_long_think_that_never_repeats_is_never_cut(self):
        words = [f"thought{n}" for n in range(3000)]
        pieces = [" ".join(words[i:i + 12]) + ("\n" if i % 120 == 0 else " ") for i in range(0, 3000, 12)]
        provider = Looper(
            [[Delta(kind="reasoning", text=p) for p in pieces] + [Delta(kind="text", text="Label two hundred more by hand first.")]]
        )
        _thread, rows = self._turn(provider)
        self.assertEqual(provider.cut, [False], "a think that never repeated was cut")
        self.assertEqual(provider.handed[0], len(pieces) + 1)
        self.assertEqual(_count(rows, "reasoning_loop"), [])
        end = [r for r in rows if r["kind"] == events.END_KIND][-1]["payload"]
        self.assertEqual(end["ending"], "answered", end)
        self.assertEqual(len(provider.seen), 1)

    def test_a_think_that_returns_to_a_short_sentence_is_not_a_loop(self):
        """The ordinary shape of a long think: the same short sentence comes
        back between different thoughts. Under the window, never a loop."""
        pieces = []
        for n in range(40):
            pieces.append(Delta(kind="reasoning", text="Let me check the data again.\n"))
            pieces.append(Delta(kind="reasoning", text=f"Row {n} has label class{n % 7} and length {n * 13}, which is fine.\n"))
        provider = Looper([pieces + [Delta(kind="text", text="The data looks fine.")]])
        _thread, rows = self._turn(provider)
        self.assertEqual(provider.cut, [False])
        self.assertEqual(_count(rows, "reasoning_loop"), [])

    def test_a_stop_during_a_loop_is_the_persons_stop(self):
        # Pressed in the second copy, before the breaker could trip.
        provider = Looper(["loop", [Delta(kind="text", text="never asked for")]], press_stop_at=(0, LINES + 3))
        _thread, rows = self._turn(provider)
        end = [r for r in rows if r["kind"] == events.END_KIND][-1]["payload"]
        self.assertEqual(end["ending"], interrupt.ENDING, end)
        self.assertEqual(len(provider.seen), 1, "the model was asked again after the stop")
        self.assertEqual(_count(rows, "reasoning_loop"), [])

    def test_a_stop_during_the_nudged_round_is_the_persons_stop(self):
        # The breaker cut round one; the person pressed stop while round two
        # was still thinking. Neither ending is mistaken for the other.
        provider = Looper(
            ["loop", "loop", [Delta(kind="text", text="never asked for")]],
            press_stop_at=(1, 4),
        )
        _thread, rows = self._turn(provider)
        end = [r for r in rows if r["kind"] == events.END_KIND][-1]["payload"]
        self.assertEqual(end["ending"], interrupt.ENDING, end)
        self.assertEqual(len(provider.seen), 2)
        self.assertEqual(len(_count(rows, "reasoning_loop")), 1)
        self.assertEqual(len(_count(rows, interrupt.ENDING)), 1)


class TheBreakerReadsTheThoughtTest(unittest.TestCase):
    """The detector alone: two copies are not a loop, three are."""

    def test_two_copies_are_not_a_loop_and_three_are(self):
        two = "".join(PARAGRAPH * 2)
        # AT EVERY PREFIX, not only the end: a first cut tripped four lines
        # into the second copy (a negative `rfind` end counts from the right).
        for size in range(1, len(two) + 1, 7):
            self.assertIsNone(conductor._reasoning_loop(two[:size]), f"tripped at {size} of {len(two)}")
        found = conductor._reasoning_loop(two + "".join(PARAGRAPH)[:400])
        self.assertIsNotNone(found)
        self.assertEqual(found[0], 3)

    def test_whitespace_does_not_hide_a_loop(self):
        spaced = "".join(line.replace(" ", "  ") for line in PARAGRAPH)
        text = "".join(PARAGRAPH) + spaced + "".join(PARAGRAPH).replace("\n", " ")
        self.assertIsNotNone(conductor._reasoning_loop(text))


if __name__ == "__main__":
    unittest.main()
