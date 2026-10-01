"""ObservationPack: a large tool result rides whole for two rounds, then as a handle.

`app/observations.py` says why. These tests pin the three sizes and the door:

- a result over `PACK_OVER_CHARS` is sent whole with the next two requests
  and PACKED before the third, and the reader's schema joins the wire the
  round the pack exists;
- a result over `REDUCE_OVER_CHARS` is packed from the first request after
  it, with its logs reduced to evidence lines;
- a small result is never touched;
- `read_observation` returns the whole result, or a window of one field,
  and refuses a handle that is not this thread's;
- a later turn's memory note names the handle, and its wire carries the
  reader.
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

import support  # noqa: E402,F401
from app import conductor, events, observations  # noqa: E402
from app.providers import Delta, ToolCall  # noqa: E402
from app.tools import REGISTRY, blocks  # noqa: E402
from test_a_turn_always_speaks import ScriptedProvider, TurnTestCase, says  # noqa: E402


class _Recording(ScriptedProvider):
    """A scripted model that also keeps every request it was sent."""

    def __init__(self, scripts, **kw):
        super().__init__(scripts, **kw)
        self.requests: list[list[dict]] = []

    def stream(self, messages, tools=None, *, secret=None):
        self.requests.append([dict(m) for m in messages])
        yield from super().stream(messages, tools, secret=secret)


def _calls(n: int, name: str = "list_runs") -> list[list[Delta]]:
    return [
        [Delta(kind="tool_call", tool_calls=(ToolCall(f"c{i}", name, {"limit": i + 1}),))]
        for i in range(n)
    ]


def _big(chars: int) -> dict:
    """A result whose envelope is about `chars` characters, with a log in it."""
    lines = []
    i = 0
    while sum(len(x) + 1 for x in lines) < chars:
        i += 1
        lines.append(f"line {i}" + (" ERROR something failed here" if i % 41 == 0 else " fine"))
    return {"ok": True, "exit_code": 1, "stdout": "\n".join(lines), "summary": "a long log"}


def _tool_messages(request: list[dict], name: str) -> list[dict]:
    return [m for m in request if m.get("role") == "tool" and m.get("name") == name]


def _names(tools) -> set[str]:
    return {(t.get("function") or {}).get("name") for t in (tools or [])}


class _PackedTurn(TurnTestCase):
    def stub(self, name: str, result: dict) -> None:
        original = REGISTRY.call

        def fake(tool_name, arguments=None, **kw):
            if tool_name == name:
                return json.loads(json.dumps(result))
            return original(tool_name, arguments, **kw)

        REGISTRY.call = fake
        self.addCleanup(lambda: setattr(REGISTRY, "call", original))
        self.addCleanup(lambda: REGISTRY.__dict__.pop("call", None))

    def run_turn(self, provider, thread_id):
        self.install(provider)
        return list(conductor.run_turn(thread_id, max_tool_rounds=8))


class ALargeResultRidesWholeForTwoRoundsThenPacksTest(_PackedTurn):
    def test_whole_twice_then_a_handle_and_the_reader_on_the_wire(self):
        self.connect()
        thread_id = self.new_thread()
        self.stub("list_runs", _big(observations.PACK_OVER_CHARS + 2_000))
        provider = _Recording(_calls(4) + [says("done")])
        rows = self.run_turn(provider, thread_id)

        # Round 1's result is tool message 0 of "list_runs" in every later request.
        first_in = [
            _tool_messages(request, "list_runs")[0]["content"]
            for request in provider.requests[1:]
        ]
        self.assertGreaterEqual(len(first_in), 4)
        self.assertNotIn("PACKED", first_in[0], "request 2 must carry it whole")
        self.assertNotIn("PACKED", first_in[1], "request 3 must carry it whole")
        self.assertTrue(first_in[2].startswith("PACKED"), "request 4 carries the pack")
        self.assertIn("obs:", first_in[2])
        self.assertIn("evidence_lines", first_in[2])
        self.assertIn("ERROR something failed", first_in[2], "evidence lines are verbatim")
        self.assertLess(len(first_in[2]), len(first_in[0]) // 2)

        packed = [r["payload"] for r in rows if r["kind"] == observations.PACKED_KIND]
        self.assertTrue(packed)
        self.assertEqual(packed[0]["name"], "list_runs")
        self.assertEqual(packed[0]["why"], "rode_whole")

        self.assertNotIn("read_observation", _names(provider.offered[0]))
        self.assertIn("read_observation", _names(provider.offered[3]))
        self.assert_it_spoke(thread_id, "packed turn")

    def test_a_small_result_is_never_packed(self):
        self.connect()
        thread_id = self.new_thread()
        self.stub("list_runs", {"ok": True, "runs": [], "summary": "nothing yet"})
        provider = _Recording(_calls(4) + [says("done")])
        rows = self.run_turn(provider, thread_id)
        self.assertEqual([r for r in rows if r["kind"] == observations.PACKED_KIND], [])
        for request in provider.requests[1:]:
            for message in _tool_messages(request, "list_runs"):
                self.assertNotIn("PACKED", message["content"])
        self.assertFalse(observations.has_handles(thread_id))


class AHugeResultIsReducedAtOnceTest(_PackedTurn):
    def test_over_the_window_it_is_packed_from_the_first_request(self):
        self.connect()
        thread_id = self.new_thread()
        self.stub("list_runs", _big(observations.REDUCE_OVER_CHARS + 20_000))
        provider = _Recording(_calls(2) + [says("done")])
        rows = self.run_turn(provider, thread_id)
        second = _tool_messages(provider.requests[1], "list_runs")[0]["content"]
        self.assertTrue(second.startswith("PACKED"))
        self.assertLess(len(second), 6_000)
        packed = [r["payload"] for r in rows if r["kind"] == observations.PACKED_KIND]
        self.assertEqual(packed[0]["why"], "reduced")
        self.assertGreater(packed[0]["chars"], observations.REDUCE_OVER_CHARS)
        # The record on file is whole; only the wire was reduced.
        result_rows = [r for r in rows if r["kind"] == "tool.result"]
        self.assertGreater(len(result_rows[0]["payload"]["result"]["stdout"]), observations.REDUCE_OVER_CHARS)


class TheReaderOpensTheHandleTest(_PackedTurn):
    def _packed_thread(self, chars: int) -> tuple[int, str]:
        self.connect()
        thread_id = self.new_thread()
        self.stub("list_runs", _big(chars))
        provider = _Recording(_calls(4) + [says("done")])
        rows = self.run_turn(provider, thread_id)
        packed = [r["payload"] for r in rows if r["kind"] == observations.PACKED_KIND]
        return thread_id, packed[0]["handle"]

    def test_the_whole_result_comes_back_exactly(self):
        thread_id, handle = self._packed_thread(observations.PACK_OVER_CHARS + 2_000)
        out = REGISTRY.get("read_observation").handler(handle=handle, thread_id=thread_id)
        self.assertTrue(out["ok"])
        self.assertTrue(out["whole"])
        self.assertEqual(out["result"]["summary"], "a long log")
        self.assertIn("line 41 ERROR", out["result"]["stdout"])

    def test_a_window_of_one_field(self):
        thread_id, handle = self._packed_thread(observations.REDUCE_OVER_CHARS + 20_000)
        reader = REGISTRY.get("read_observation").handler
        whole = reader(handle=handle, thread_id=thread_id)
        self.assertTrue(whole["ok"])
        self.assertFalse(whole["whole"], "too big to hand back whole; parts are named")
        self.assertIn("stdout", whole["parts"])
        window = reader(handle=handle, part="stdout", from_line=40, lines=3, thread_id=thread_id)
        self.assertEqual(window["from_line"], 40)
        self.assertEqual(window["to_line"], 42)
        self.assertEqual(window["text"].splitlines()[1], "line 41 ERROR something failed here")
        self.assertTrue(window["more"])
        missing = reader(handle=handle, part="nope", thread_id=thread_id)
        self.assertEqual(missing["error"], "no_such_part")

    def test_a_handle_that_is_not_this_threads_is_refused(self):
        thread_id, handle = self._packed_thread(observations.PACK_OVER_CHARS + 2_000)
        reader = REGISTRY.get("read_observation").handler
        other = events.create_thread("other")["id"]
        self.assertEqual(reader(handle=handle, thread_id=other)["error"], "no_such_observation")
        self.assertEqual(reader(handle="obs:999999", thread_id=thread_id)["error"], "no_such_observation")
        self.assertEqual(reader(handle="not-a-handle", thread_id=thread_id)["error"], "not_a_handle")


class ALaterTurnIsNotSentBackToReadItTest(_PackedTurn):
    """THE NOTE STOPPED NAMING THE HANDLE, and the measurement is the argument.

    It named one so a later turn could re-read instead of re-running. Max's
    thread 92, 2026-09-21, is what that bought: `read_observation` was 14 of
    30 real calls - 46%, the most-called tool in the thread, ahead of every
    instrument that measures anything. The note offered a handle, the pack
    offered a handle, and the model took both, every round.

    Three wordings were tried on the offer before this - "open once", "call it
    only if you need what was shortened", "do not call it" - and each was
    still an offer. A model takes an offer. See
    [[an-affordance-can-cost-more-than-it-saves]]: close the loop your
    convenience opens, and when it will not close, stop opening it.

    What the note is FOR survives: it still says the call was made and what
    came back, which is the thing a later turn did not know. A turn that needs
    more than the gist runs the instrument - one call either way, and the
    answer comes back current instead of remembered.
    """

    def test_the_note_says_what_was_read_without_naming_a_handle(self):
        self.connect()
        thread_id = self.new_thread()
        self.stub("list_runs", _big(observations.PACK_OVER_CHARS + 2_000))
        self.run_turn(_Recording(_calls(1) + [says("done")]), thread_id)
        note = conductor._already_read_note(thread_id)
        self.assertIn("list_runs", note, "the note still says the call was made")
        self.assertNotIn("obs:", note)
        self.assertNotIn("open once", note)
        self.assertNotIn(observations.READER, note)
        # The handle still EXISTS - this removes the advertisement, not the door.
        self.assertTrue(observations.has_handles(thread_id))

    def test_a_pack_header_offers_no_call_either(self):
        packed = observations.pack_text(
            "list_runs",
            {"ok": True, "stdout": "x\n" * 4000},
            "obs:1",
            why="rode_whole",
            envelope=lambda _name, body: str(body),
        )
        self.assertIn("Shortened here", packed)
        self.assertIn("run the tool again", packed)
        self.assertNotIn(observations.READER, packed)

    def test_the_schema_still_rides_when_a_handle_exists(self):
        """THE DOOR STAYS; THE SIGN COMES DOWN.

        A schema in the offered list is not an instruction - it is a
        capability a model may reason its way to. The two things removed were
        PROSE telling it to, which is what a small model acts on. Removing the
        schema as well would make a packed field unreachable by any route.
        """
        self.connect()
        thread_id = self.new_thread()
        self.stub("list_runs", _big(observations.PACK_OVER_CHARS + 2_000))
        self.run_turn(_Recording(_calls(1) + [says("done")]), thread_id)
        events.add_message(thread_id, "user", "and now?")
        second = _Recording([says("nothing more")])
        self.run_turn(second, thread_id)
        self.assertIn(
            "read_observation", _names(second.offered[0]),
            "a thread holding a handle offers the reader's schema on its next turn",
        )


class TheReducerKeepsEvidenceTest(unittest.TestCase):
    def test_head_tail_and_flagged_lines_verbatim_with_numbers(self):
        text = "\n".join(
            f"row {i}" + (" Traceback (most recent call last)" if i == 100 else "")
            for i in range(1, 201)
        )
        out = observations.reduce_text(text)
        self.assertEqual(out["lines"], 200)
        self.assertEqual(out["head"][0], "row 1")
        self.assertEqual(out["tail"][-1], "row 200")
        self.assertEqual(out["tail_from_line"], 181)
        self.assertEqual(out["evidence_lines"], ["100: row 100 Traceback (most recent call last)"])

    def test_a_short_log_is_kept_whole(self):
        out = observations.reduce_text("a\nb\nc")
        self.assertEqual(out["whole"], ["a", "b", "c"])

    def test_an_excerpt_reduces_only_the_long_fields(self):
        result = {"ok": True, "exit_code": 0, "stdout": "x\n" * 2000, "summary": "short"}
        out = observations.excerpt(result)
        self.assertEqual(out["summary"], "short")
        self.assertEqual(out["exit_code"], 0)
        self.assertTrue(out["stdout"]["reduced"])
        self.assertEqual(out["stdout"]["lines"], 2000)

    def test_the_capability_and_the_reader_are_published(self):
        self.assertIn("context.observation.read", blocks.CAPABILITIES)
        self.assertEqual(REGISTRY.get("read_observation").provides, ("context.observation.read",))
        self.assertNotIn("read_observation", blocks.ALWAYS_ON, "on demand, like every schema")


class TheDoorIsNeverBehindADoorTest(_PackedTurn):
    """Thread 79, 2026-09-19: the note offered a handle, the model opened it,
    the 8,443-character answer was itself packed, and the pack offered to open
    it again. Four of nine rounds on one verdict it already had."""

    def test_the_readers_own_answer_is_never_packed(self):
        self.connect()
        thread_id = self.new_thread()
        self.stub("list_runs", _big(observations.REDUCE_OVER_CHARS + 20_000))
        rows = self.run_turn(_Recording(_calls(1) + [says("done")]), thread_id)
        handle = [r["payload"] for r in rows if r["kind"] == observations.PACKED_KIND][0]["handle"]

        events.add_message(thread_id, "user", "open it")
        second = _Recording(
            [[Delta(kind="tool_call", tool_calls=(ToolCall("r1", "read_observation", {"handle": handle}),))]]
            + _calls(4)
            + [says("done")]
        )
        rows2 = self.run_turn(second, thread_id)
        opened = [
            r for r in rows2
            if r["kind"] == observations.PACKED_KIND
            and r["payload"].get("name") == "read_observation"
        ]
        self.assertEqual(opened, [], "the reader's own answer was packed, which is the loop")
        for request in second.requests[1:]:
            for message in _tool_messages(request, "read_observation"):
                self.assertNotIn("PACKED", message["content"])

    def test_the_note_does_not_offer_a_handle_for_the_reader(self):
        self.connect()
        thread_id = self.new_thread()
        self.stub("list_runs", _big(observations.REDUCE_OVER_CHARS + 20_000))
        rows = self.run_turn(_Recording(_calls(1) + [says("done")]), thread_id)
        handle = [r["payload"] for r in rows if r["kind"] == observations.PACKED_KIND][0]["handle"]
        events.add_message(thread_id, "user", "open it")
        self.run_turn(
            _Recording(
                [[Delta(kind="tool_call", tool_calls=(ToolCall("r9", "read_observation", {"handle": handle}),))]]
                + [says("done")]
            ),
            thread_id,
        )
        note = conductor._already_read_note(thread_id)
        # THE STRONGER VERSION OF THE SAME PROPERTY. This asserted the reader's
        # call was still LISTED, without a handle on it - "a handle to the door
        # is another door". The door is now not mentioned at all, which
        # satisfies that and one more thing besides.
        #
        # Max's thread 92, 2026-09-21: the note is capped at fourteen lines and
        # eight of his were `read_observation`. `inspect_hardware`,
        # `measure_eval_set` and `read_plan` - the three tools he then watched
        # being run again - had been pushed off the end by a tool whose entire
        # job is handing back a result this conversation already holds. A note
        # listing the reader is the note describing itself, and it was doing it
        # with the budget that belonged to real readings.
        self.assertNotIn("read_observation", note)
        self.assertNotIn("on file as obs:", note)
        # And the cap is now spent on calls that read the world.
        self.assertIn("list_runs", note, "the real reading still has its line")


class ThePackNamesThisResultsOwnFieldsTest(unittest.TestCase):
    """It printed one worked example, part="stdout", whatever the result was -
    so thread 79 asked for stdout on a verdict and got no_such_part."""

    def test_it_names_the_fields_it_shortened_and_no_others(self):
        result = {"ok": True, "stdout": "x\n" * 2000, "verdict": "no", "exit_code": 1}
        text = observations.pack_text(
            "run_project_command", result, "obs:5",
            why="test", envelope=conductor.data_envelope,
        )
        self.assertIn("Shortened here: stdout", text)
        # NO WORKED CALL AT ALL NOW. The example used to be derived from this
        # result's own fields, which fixed it being wrong; 2026-09-21 measured
        # that being right was not enough - an example of a call is an offer,
        # and the reader became 46% of one thread's tool calls.
        self.assertNotIn('part=', text)
        self.assertNotIn(observations.READER, text)
        self.assertIn("run the tool again", text)

    def test_a_result_that_lost_nothing_says_not_to_open_it(self):
        result = {"ok": True, "outcome": "BLOCKED", "say": "short", "verdict": "no"}
        text = observations.pack_text(
            "run_diagnosis", result, "obs:7",
            why="test", envelope=conductor.data_envelope,
        )
        self.assertIn("Nothing was shortened", text)
        # It used to end "so read_observation would hand back this same text.
        # Do not call it." Naming the tool in order to forbid it is still
        # naming it; the sentence simply stops.
        self.assertNotIn(observations.READER, text)
        self.assertNotIn("from_line", text)


if __name__ == "__main__":
    unittest.main()
