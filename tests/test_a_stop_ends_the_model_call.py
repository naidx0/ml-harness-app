"""A stop pressed while the model is writing ends that model call, within a second.

Max, 2026-09-23: *"the stop button doesn't seem to actually stop."* It did
not. `app/interrupt.py` honoured the press at the next ROUND BOUNDARY, and a
round is one model call - which on this machine is a local Ollama generation
of 60 to 90 seconds. The press was recorded, the flag was set, and the reply
went on writing itself in front of him until the model decided it was done.

Two ways a model call is ended, and each has a case here that only it can
pass:

- **Between two pieces of the reply.** A provider handing up a token every
  100 ms for ever is stopped by the conductor at the next piece - no socket is
  involved, so the only thing that can end this case is the check between
  deltas (`interrupt.watched`).
- **While the model says nothing at all.** A prompt being evaluated, or a
  thinking model before its first token, sends NO bytes for tens of seconds,
  so there is no next piece to check between. Only severing the in-flight
  request ends this case, and the fake server here proves the connection was
  closed from our side rather than finished from its own.

And the promise `app/interrupt.py` made is kept: a TOOL that is running when
the press lands is never severed - it finishes, is recorded, and no further
round is asked for.
"""
from __future__ import annotations

import json
import select
import sys
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402,F401
from app import conductor, events, interrupt  # noqa: E402
from app.providers import Delta, ToolCall  # noqa: E402
from app.providers.ollama import OllamaProvider  # noqa: E402
from app.providers.openai_compatible import OpenAICompatibleProvider  # noqa: E402
from test_a_turn_always_speaks import ScriptedProvider, TurnTestCase, says  # noqa: E402

#: How long a stopped model call may take to end. The owner's bound is "about a
#: second"; two leaves room for a loaded test machine without letting a
#: round-boundary stop (60-90 s on his Ollama) pass.
BOUND_SECONDS = 2.0


class Endless:
    """A model that writes a word every 100 ms and never finishes on its own.

    `release` is the test's, so a run that ignores the stop (the fault) still
    ends when the test does instead of writing into the next test's database.
    """

    id = "endless"
    locality = "local"

    def __init__(self) -> None:
        self.said = 0
        self.rounds = 0
        self.flowing = threading.Event()
        self.closed = threading.Event()
        self.release = threading.Event()

    def stream(self, messages, tools=None, *, secret=None):
        self.rounds += 1
        try:
            while not self.release.is_set():
                self.said += 1
                if self.said >= 3:
                    self.flowing.set()
                yield Delta(kind="text", text="word ")
                time.sleep(0.1)
        finally:
            self.closed.set()

    def capabilities(self, *, secret=None):
        raise AssertionError("the loop must not probe mid-turn")


class _Silent(BaseHTTPRequestHandler):
    """An Ollama (or OpenAI-compatible server) that is evaluating a long prompt.

    It answers the window questions, accepts the chat request, sends its
    headers and then NOTHING - which is what a server does for the tens of
    seconds before the first token. It watches its own end of the connection:
    `severed` is set only when the CLIENT closed it, never by the server
    giving up, so it is proof that the in-flight request was cancelled.
    """

    protocol_version = "HTTP/1.1"
    arrived: threading.Event
    severed: threading.Event
    release: threading.Event

    def log_message(self, *args):  # noqa: D401 - silence the default stderr log
        return

    def _json(self, body):
        raw = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path.endswith("/models"):
            self._json({"data": [{"id": "silent-7b", "context_length": 131072}]})
            return
        self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        if self.path == "/api/show":
            self._json(
                {
                    "capabilities": ["completion", "tools"],
                    "model_info": {"general.architecture": "llama", "llama.context_length": 131072},
                    "parameters": "num_ctx 65536",
                }
            )
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        self.wfile.flush()
        type(self).arrived.set()
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and not type(self).release.is_set():
            readable, _w, _x = select.select([self.connection], [], [], 0.05)
            if not readable:
                continue
            try:
                gone = self.connection.recv(1) == b""
            except OSError:
                gone = True
            if gone:
                type(self).severed.set()
                return
        self.close_connection = True


class _InTheBackground:
    def _run_in_background(self, thread_id: int):
        """The turn on a worker thread, as the facade runs it (`facade/turns.py`)."""
        rows: list[dict] = []
        done = threading.Event()

        def work():
            try:
                for row in conductor.run_turn(thread_id, max_tool_rounds=8):
                    rows.append(row)
            finally:
                done.set()

        worker = threading.Thread(target=work, name=f"turn-{thread_id}", daemon=True)
        worker.start()
        # Joined before the sandbox goes, even when the test failed: a turn
        # still writing would write into the next test's database.
        self.addCleanup(worker.join, 30)
        return rows, done


class AStopEndsTheModelCallTest(_InTheBackground, TurnTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.addCleanup(lambda: [interrupt.clear(t) for t in interrupt.waiting()])

    def test_a_stop_mid_reply_ends_the_call_and_keeps_what_was_written(self):
        self.connect()
        thread_id = self.new_thread()
        provider = self.install(Endless())
        self.addCleanup(provider.release.set)
        rows, done = self._run_in_background(thread_id)
        self.assertTrue(provider.flowing.wait(30), "the model never started writing")

        pressed = time.monotonic()
        interrupt.ask_to_stop(thread_id)
        ended = done.wait(BOUND_SECONDS)
        took = time.monotonic() - pressed

        self.assertTrue(
            ended,
            f"the turn was still running {BOUND_SECONDS}s after the stop - the "
            "press waited for a round boundary the model never reached",
        )
        self.assertLess(took, BOUND_SECONDS)
        self.assertTrue(provider.closed.wait(1), "the provider's stream was left open")
        self.assertEqual(provider.rounds, 1, "a round was asked for after the stop")

        end = [r for r in rows if r["kind"] == events.END_KIND][-1]
        self.assertEqual(end["payload"]["ending"], interrupt.ENDING)
        notices = [
            r["payload"] for r in rows
            if r["kind"] == "conductor.notice" and r["payload"].get("reason") == interrupt.ENDING
        ]
        self.assertEqual(len(notices), 1, "the transcript does not say a person stopped it, once")
        replies = [m["content"] for m in events.messages_for(thread_id) if m["role"] == "assistant"]
        self.assertTrue(
            any(reply.startswith("word word") for reply in replies),
            f"the words written before the stop were not kept: {replies!r}",
        )
        self.assertNotIn(
            "chat.error", [r["kind"] for r in rows],
            "the stop was reported as a provider fault",
        )
        self.assertFalse(interrupt.was_asked(thread_id), "the flag outlived its turn")

    def test_a_stop_while_the_model_is_silent_severs_the_request(self):
        """No bytes arrive, so only closing the connection can end the call."""
        for label, build in (
            ("ollama", lambda url, opener: OllamaProvider(url, "silent-7b", opener=opener)),
            (
                "openai-compatible",
                lambda url, opener: OpenAICompatibleProvider(url + "/v1", "silent-7b", opener=opener),
            ),
        ):
            with self.subTest(provider=label):
                handler = type(
                    "Silent",
                    (_Silent,),
                    {
                        "arrived": threading.Event(),
                        "severed": threading.Event(),
                        "release": threading.Event(),
                    },
                )
                server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
                server.daemon_threads = True
                threading.Thread(target=server.serve_forever, daemon=True).start()
                self.addCleanup(server.server_close)
                self.addCleanup(server.shutdown)
                self.addCleanup(handler.release.set)
                url = f"http://127.0.0.1:{server.server_address[1]}"
                # No proxy: the request goes to the server this test owns.
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({})).open

                self.connect()
                thread_id = self.new_thread()
                self.install(build(url, opener))
                rows, done = self._run_in_background(thread_id)
                self.assertTrue(handler.arrived.wait(30), "the chat request never reached the server")

                pressed = time.monotonic()
                interrupt.ask_to_stop(thread_id)
                ended = done.wait(BOUND_SECONDS)
                took = time.monotonic() - pressed

                self.assertTrue(
                    ended,
                    f"{label}: the turn was still waiting on a silent model "
                    f"{BOUND_SECONDS}s after the stop",
                )
                self.assertLess(took, BOUND_SECONDS)
                self.assertTrue(
                    handler.severed.wait(2),
                    f"{label}: the server never saw the request closed - the "
                    "model would have gone on generating for nobody",
                )
                end = [r for r in rows if r["kind"] == events.END_KIND][-1]
                self.assertEqual(end["payload"]["ending"], interrupt.ENDING)
                self.assertNotIn(
                    "chat.error", [r["kind"] for r in rows],
                    f"{label}: severing our own request was reported as a provider fault",
                )

    def test_a_stop_while_waiting_to_reconnect_ends_the_wait(self):
        """A provider that died having released nothing is tried again after a
        wait (`PROVIDER_BACKOFF`, up to 3 s). A press during that wait is a
        press during the model call, and it does not sit the wait out."""
        self.connect()
        thread_id = self.new_thread()
        called = threading.Event()

        class DiesAtOnce:
            id = "dead"
            locality = "local"
            calls = 0

            def stream(inner, messages, tools=None, *, secret=None):
                inner.calls += 1
                called.set()
                raise ConnectionResetError("the socket closed before a byte")
                yield  # pragma: no cover - makes this a generator

            def capabilities(inner, *, secret=None):
                raise AssertionError("the loop must not probe mid-turn")

        provider = self.install(DiesAtOnce())
        was = conductor.PROVIDER_BACKOFF
        conductor.PROVIDER_BACKOFF = (10.0,) * len(was)
        self.addCleanup(setattr, conductor, "PROVIDER_BACKOFF", was)
        rows, done = self._run_in_background(thread_id)
        self.assertTrue(called.wait(30), "the model was never called")
        pressed = time.monotonic()
        interrupt.ask_to_stop(thread_id)
        self.assertTrue(
            done.wait(BOUND_SECONDS),
            f"the turn sat out a reconnect wait {BOUND_SECONDS}s after the stop",
        )
        self.assertLess(time.monotonic() - pressed, BOUND_SECONDS)
        self.assertEqual(provider.calls, 1, "it reconnected after the stop")
        end = [r for r in rows if r["kind"] == events.END_KIND][-1]
        self.assertEqual(end["payload"]["ending"], interrupt.ENDING)

    def test_a_stop_during_a_tool_waits_for_the_tool(self):
        """The press lands while the tool runs: it finishes, it is recorded,
        and the turn ends at the boundary after it - never inside it."""
        self.connect()
        thread_id = self.new_thread()
        provider = self.install(
            ScriptedProvider(
                [[Delta(kind="tool_call", tool_calls=(ToolCall("t1", "list_runs", {"limit": 1}),))]]
                + [says("never asked for")]
            )
        )
        original = conductor.REGISTRY.call
        in_tool = threading.Event()
        tool_seconds = 1.0

        def slow(name, *args, **kwargs):
            if name == "list_runs":
                in_tool.set()
                time.sleep(tool_seconds)
            return original(name, *args, **kwargs)

        with mock.patch.object(conductor.REGISTRY, "call", side_effect=slow):
            rows, done = self._run_in_background(thread_id)
            self.assertTrue(in_tool.wait(30), "the tool never started")
            pressed = time.monotonic()
            interrupt.ask_to_stop(thread_id)
            self.assertTrue(done.wait(30), "the turn never ended")
            took = time.monotonic() - pressed

        self.assertGreater(
            took, tool_seconds * 0.8,
            "the turn ended before the tool could have finished - the stop severed it",
        )
        self.assertEqual(provider.rounds, 1, "a round was asked for after the stop")
        calls = [r for r in rows if r["kind"] == "tool.call"]
        results = [r for r in rows if r["kind"] == "tool.result"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(results), 1, "the tool that was running was not recorded")
        end = [r for r in rows if r["kind"] == events.END_KIND][-1]
        self.assertEqual(end["payload"]["ending"], interrupt.ENDING)


#: Over `memory.EXTRACT_FROM_REPLIES_OVER` on its own, so the after-turn
#: memory pass has an exchange to read whatever the model managed to say.
LONG_QUESTION = (
    "I have eleven thousand support tickets in a folder called tickets and a "
    "spreadsheet of the labels my team gave the first two thousand of them. "
    "Should I fine-tune a model to label the rest, or is there something "
    "cheaper I should try first? Please look before you answer."
)


class _Counting(ScriptedProvider):
    """Counts every call to `stream`, from the turn or from anything after it."""

    def __init__(self, scripts, **kwargs):
        super().__init__(scripts, **kwargs)
        self.calls = 0

    def stream(self, messages, tools=None, *, secret=None):
        self.calls += 1
        yield from super().stream(messages, tools, secret=secret)


class NothingAsksTheModelAfterAStopTest(_InTheBackground, TurnTestCase):
    """Thread 93, 2026-09-23, the owner's run: Stop pressed 14 s in; the turn
    ended `stopped_by_the_person` at 04:12:32 - and then NOTHING for 57 s,
    because the after-turn memory pass (`memory.extract_after_turn`) asked the
    model one more question on every ending but `provider_failed`. Then the
    closing called the stop "a bug in the harness", because `SILENT_TURN` had
    no sentence for it and `_closing_sentence` fell through to `unknown`."""

    def setUp(self) -> None:
        super().setUp()
        self.addCleanup(lambda: [interrupt.clear(t) for t in interrupt.waiting()])
        from app import memory

        patcher = mock.patch.object(memory, "EXTRACTION_ENABLED", True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _stop_inside_the_first_tool(self, thread_id: int):
        original = conductor.REGISTRY.call

        def pressing(name, *args, **kwargs):
            if name == "list_runs":
                interrupt.ask_to_stop(thread_id)
            return original(name, *args, **kwargs)

        return mock.patch.object(conductor.REGISTRY, "call", side_effect=pressing)

    def test_a_stop_at_the_boundary_asks_the_model_nothing_more(self):
        """Thread 93's shape: the press lands while a tool runs."""
        self.connect()
        thread_id = self.new_thread(LONG_QUESTION)
        provider = self.install(
            _Counting(
                [[Delta(kind="tool_call", tool_calls=(ToolCall("t1", "list_runs", {"limit": 1}),))]]
                + [says("never asked for")] * 4
            )
        )
        with self._stop_inside_the_first_tool(thread_id):
            rows = list(conductor.run_turn(thread_id, max_tool_rounds=8))
        end = [r for r in rows if r["kind"] == events.END_KIND][-1]
        self.assertEqual(end["payload"]["ending"], interrupt.ENDING)
        self.assertEqual(
            provider.calls, 1,
            "the model was asked something after the person pressed stop",
        )

    def test_a_stop_inside_the_model_call_asks_the_model_nothing_more(self):
        self.connect()
        thread_id = self.new_thread(LONG_QUESTION)

        class PressingWhileItWrites(_Counting):
            def stream(inner, messages, tools=None, *, secret=None):
                inner.calls += 1
                yield Delta(kind="text", text="Before anything else, I want to look at ")
                interrupt.ask_to_stop(thread_id)
                yield Delta(kind="text", text="what never reaches anyone.")

        provider = self.install(PressingWhileItWrites([]))
        rows = list(conductor.run_turn(thread_id, max_tool_rounds=8))
        end = [r for r in rows if r["kind"] == events.END_KIND][-1]
        self.assertEqual(end["payload"]["ending"], interrupt.ENDING)
        self.assertEqual(provider.calls, 1, "the model was asked something after the stop")

    def test_a_stop_during_the_memory_pass_ends_it_and_keeps_the_answer(self):
        """The reply is finished but the turn is not - the memory pass is
        still asking the model, and their composer still shows working. A
        press then ends that call too; the answer it gave stands."""
        self.connect()
        thread_id = self.new_thread(LONG_QUESTION)
        endless = Endless()
        self.addCleanup(endless.release.set)

        class AnswersThenRemembersForEver:
            id = "answers"
            locality = "local"
            calls = 0

            def stream(inner, messages, tools=None, *, secret=None):
                inner.calls += 1
                if inner.calls == 1:
                    yield Delta(kind="text", text="Label two hundred more by hand first. ")
                    return
                yield from endless.stream(messages, tools, secret=secret)

            def capabilities(inner, *, secret=None):
                raise AssertionError("the loop must not probe mid-turn")

        provider = self.install(AnswersThenRemembersForEver())
        rows, done = self._run_in_background(thread_id)
        self.assertTrue(endless.flowing.wait(30), "the memory pass never asked the model")
        pressed = time.monotonic()
        interrupt.ask_to_stop(thread_id)
        self.assertTrue(
            done.wait(BOUND_SECONDS),
            f"the memory pass was still asking the model {BOUND_SECONDS}s after the stop",
        )
        self.assertLess(time.monotonic() - pressed, BOUND_SECONDS)
        self.assertEqual(provider.calls, 2)
        end = [r for r in rows if r["kind"] == events.END_KIND][-1]
        self.assertEqual(end["payload"]["ending"], "answered", "the answer it gave was taken back")
        self.assertNotIn("memory.extracted", [r["kind"] for r in rows])

    def test_the_closing_says_it_was_stopped_and_never_calls_it_a_bug(self):
        self.connect()
        thread_id = self.new_thread()
        self.install(
            ScriptedProvider(
                [[Delta(kind="tool_call", tool_calls=(ToolCall("t1", "list_runs", {"limit": 1}),))]]
            )
        )
        with self._stop_inside_the_first_tool(thread_id):
            rows = list(conductor.run_turn(thread_id, max_tool_rounds=8))
        closings = [
            r["payload"] for r in rows
            if r["kind"] == "chat.delta" and r["payload"].get("written_by") == "harness"
        ]
        self.assertEqual(len(closings), 1)
        self.assertEqual(closings[0]["ending"], interrupt.ENDING)
        self.assertIn(interrupt.ENDING, conductor.SILENT_TURN)
        self.assertEqual(closings[0]["text"], conductor.SILENT_TURN[interrupt.ENDING])
        self.assertNotEqual(closings[0]["text"], conductor.SILENT_TURN["unknown"])
        self.assertNotIn("bug", closings[0]["text"].lower())

    def test_a_stop_during_thinking_stores_no_empty_assistant_message(self):
        """A stopped reply that was only reasoning leaves no assistant row with
        nothing in it (`_record`'s guard). A row with EMPTY TEXT AND TOOL
        CALLS - thread 93's messages.id 1929 - is a different thing and is
        kept: it is the model's call, which the next turn reads back
        (`_what_the_last_reply_said`, the history builder)."""
        self.connect()
        thread_id = self.new_thread()

        class ThinksThenIsStopped:
            id = "thinker"
            locality = "local"

            def stream(inner, messages, tools=None, *, secret=None):
                yield Delta(kind="reasoning", text="Let me think about the labels first.\n")
                interrupt.ask_to_stop(thread_id)
                yield Delta(kind="reasoning", text="never shown")

            def capabilities(inner, *, secret=None):
                raise AssertionError("the loop must not probe mid-turn")

        self.install(ThinksThenIsStopped())
        rows = list(conductor.run_turn(thread_id, max_tool_rounds=8))
        end = [r for r in rows if r["kind"] == events.END_KIND][-1]
        self.assertEqual(end["payload"]["ending"], interrupt.ENDING)
        empty = [
            m for m in events.messages_for(thread_id)
            if m["role"] == "assistant"
            and not str(m["content"] or "").strip()
            and not m.get("tool_calls_json")
        ]
        self.assertEqual(empty, [], "a stopped reply left an empty assistant message")


class TheCancelHookIsKeyedToItsTurnTest(unittest.TestCase):
    """The hook a provider registers belongs to one turn's thread, and dies with it."""

    def tearDown(self) -> None:
        for thread_id in (901, 902):
            interrupt.clear(thread_id)

    def test_a_stop_severs_only_its_own_thread_s_request(self):
        severed: list[int] = []
        with interrupt.reading(901):
            release_mine = interrupt.cancel_with(lambda: severed.append(901))
        with interrupt.reading(902):
            release_theirs = interrupt.cancel_with(lambda: severed.append(902))
        interrupt.ask_to_stop(901)
        self.assertEqual(severed, [901])
        release_mine()
        release_theirs()

    def test_a_released_hook_is_never_called(self):
        severed: list[int] = []
        with interrupt.reading(901):
            release = interrupt.cancel_with(lambda: severed.append(901))
        release()
        interrupt.ask_to_stop(901)
        self.assertEqual(severed, [])

    def test_a_request_opened_after_the_press_is_severed_at_once(self):
        severed: list[int] = []
        interrupt.ask_to_stop(901)
        with interrupt.reading(901):
            interrupt.cancel_with(lambda: severed.append(901))
        self.assertEqual(severed, [901])

    def test_outside_a_turn_nothing_is_registered(self):
        """A provider called by something that is not a turn - a probe, a
        compaction - has no stop to answer, and registers nothing."""
        severed: list[int] = []
        release = interrupt.cancel_with(lambda: severed.append(0))
        release()
        interrupt.ask_to_stop(901)
        self.assertEqual(severed, [])

    def test_clearing_the_turn_drops_its_hooks(self):
        severed: list[int] = []
        with interrupt.reading(901):
            interrupt.cancel_with(lambda: severed.append(901))
        interrupt.clear(901)
        interrupt.ask_to_stop(901)
        self.assertEqual(severed, [])


if __name__ == "__main__":
    unittest.main()
