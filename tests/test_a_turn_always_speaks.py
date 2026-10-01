"""A turn always produces assistant text. Every exit path, not one of them.

This is the regression for the worst bug this product has shipped so far, and
it is written as a property because the bug was not a case.

A real user asked "should i train a model for this application that i am
working inside off" and got nothing. The event log for that thread is four tool
calls, four tool results, `stream.end` at 5.296 seconds, and zero `chat.delta`
rows. `MAX_TOOL_ROUNDS` was 4, the model spent one round on each call, and the
`for` loop simply ran out of iterations - so the last tool result was written
into the conversation and the model was never asked what it meant. No error, no
warning, no words. A question, and silence.

Fixing that one path would have been a morning's work and would have left five
others: a model that returns an empty message, a model that asks for the same
fact until the budget is gone, a provider that times out, a stream that drops
half way through a tool call, and a fault in our own code. Each of those ended
a turn quietly too.

So the test is a table of exit paths, and the assertion on every row is the
same four things:

1. the turn produced non-empty assistant prose,
2. the last thing in it, before `stream.end`, is words rather than a tool
   result,
3. the transcript's last message is an assistant message with content in it,
4. `stream.end` names which path it was.

A new way out of the loop is a new row here. If someone adds one and does not,
the property test that walks `SILENT_TURN` catches the missing sentence.
"""

from __future__ import annotations

import unittest
from unittest import mock

from app import conductor, events
from app.providers import Delta, ToolCall
from app.providers import store as provider_store

import support


class ScriptedProvider:
    """A model that says what the test told it to, and can die on cue.

    `raise_on` holds 1-based round numbers. The exception is raised *after* the
    round's deltas, which is how a provider that drops mid-reply actually
    behaves - some of the answer arrived, and then the socket did not.

    `dead_from` is the other fault and it needed its own flag once the
    conductor learned to reconnect (`PROVIDER_TRIES`, 2026-09-14). A provider
    that goes DOWN stays down - ollama stopped, the port refusing, the machine
    asleep - so from that round on it raises on every call, including the
    retries within a round. Before the retry the two were indistinguishable
    from in here, because there was exactly one call per round; now a round
    that released nothing is tried again, and a provider that answers the
    second time has RECOVERED, which is the feature. A test that means "it
    never came back" has to say so.
    """

    id = "fake"
    locality = "local"

    def __init__(self, scripts, raise_on=(), dead_from=None):
        self.scripts = list(scripts)
        self.raise_on = set(raise_on)
        self.dead_from = dead_from
        self.rounds = 0
        self.offered = []

    def stream(self, messages, tools=None, *, secret=None):
        self.rounds += 1
        this_round = self.rounds
        self.offered.append(tools)
        script = self.scripts.pop(0) if self.scripts else []
        for delta in script:
            yield delta
        if (self.dead_from is not None and this_round >= self.dead_from) or (
            this_round in self.raise_on
        ):
            raise TimeoutError("the model stopped responding after 30s")

    def capabilities(self, *, secret=None):
        raise AssertionError("the loop must not probe mid-turn")


class MalformedCall:
    """What a broken adapter hands up: a call whose arguments cannot be read.

    Used to reach the harness's own failure path without patching a private
    function. Reading `.arguments` raises, which happens inside `run_turn` and
    not inside the provider call, so it is our fault rather than the model's.
    """

    id = "boom"
    name = "list_runs"

    @property
    def arguments(self):
        raise RuntimeError("the adapter produced a call with no arguments")


def says(text):
    return [Delta(kind="text", text=text)]


#: Call ids are unique even when the call is identical, because that is what a
#: real model does - and it is what makes `repeat_of` provable.
_CALL_IDS = iter(f"call_{n}" for n in range(1, 10_000))


def asks(name="list_runs", **arguments):
    return [
        Delta(
            kind="tool_call",
            tool_calls=(ToolCall(next(_CALL_IDS), name, arguments),),
        )
    ]


def asks_n(n, name="list_runs"):
    """`n` rounds, each asking for something different from the last."""
    return [
        [
            Delta(
                kind="tool_call",
                tool_calls=(ToolCall(f"c{i}", name, {"limit": i + 1}),),
            )
        ]
        for i in range(n)
    ]


class TurnTestCase(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)
        self.provider = None
        # NO WAITING IN THE SUITE. `PROVIDER_BACKOFF` is a real product
        # decision and none of these tests are about it: they are about which
        # ending a dead provider produces, and the five attempts still happen.
        # Left alone, the dead-provider paths slept the suite from 18 seconds
        # to 124, which on a 5,400-test gate is how a watchdog starts firing.
        was = conductor.PROVIDER_BACKOFF
        conductor.PROVIDER_BACKOFF = (0.0,) * len(was)
        self.addCleanup(setattr, conductor, "PROVIDER_BACKOFF", was)

    def connect(self, tool_calling="yes"):
        row = provider_store.create(
            "Fake", "http://127.0.0.1:11434", "fake-model", "ollama"
        )
        with_state = provider_store.record_capabilities(
            row["id"],
            type(
                "Caps",
                (),
                {
                    "tool_calling": {"yes": True, "no": False, "unknown": None}[
                        tool_calling
                    ],
                    "detail": "set by the test",
                    "ctx_len": None,
                    "provenance": {},
                },
            )(),
        )
        provider_store.set_active(with_state["id"])
        return with_state

    def install(self, provider):
        original = conductor.build
        conductor.build = lambda *a, **k: provider
        self.addCleanup(setattr, conductor, "build", original)
        return provider

    def new_thread(self, question="should i train a model for this?"):
        thread = events.create_thread("t")
        events.add_message(thread["id"], "user", question)
        return thread["id"]

    def rows(self, thread_id):
        return events.since(f"thread:{thread_id}")

    def prose(self, thread_id):
        return "".join(
            row["payload"].get("text", "")
            for row in self.rows(thread_id)
            if row["kind"] == "chat.delta"
        )

    def assert_it_spoke(self, thread_id, label):
        """The four things that are true of every turn. Returns `stream.end`."""
        rows = self.rows(thread_id)
        kinds = [row["kind"] for row in rows]

        self.assertEqual(kinds[-1], events.END_KIND, f"{label}: no stream.end")
        self.assertTrue(
            self.prose(thread_id).strip(),
            f"{label}: the turn produced no assistant text at all - this is "
            f"the silence the user was shown. Kinds: {kinds}",
        )
        # THE VERDICT CARD IS NOT PROSE AND IS SKIPPED HERE ON PURPOSE. It is
        # the engine's own answer standing beside the reply, it carries no
        # assistant text, and it sits after the words because it is about them.
        # The property this line is for - the last thing the user was SHOWN is
        # words - is unchanged; what changed is that a turn can now end with
        # one row after the words that is not a way of being silent.
        spoken = [
            kind
            for kind in kinds
            if kind not in (conductor.VERDICT_KIND, "turn.effects")
        ]
        self.assertEqual(
            spoken[-2],
            "chat.delta",
            f"{label}: the turn ended on {spoken[-2]!r} rather than on words",
        )
        messages = events.messages_for(thread_id)
        self.assertEqual(messages[-1]["role"], "assistant", label)
        self.assertTrue(
            messages[-1]["content"].strip(),
            f"{label}: the transcript's last message is empty",
        )
        return rows[-1]["payload"]


class EveryExitPathSpeaksTest(TurnTestCase):
    """The property. One row per way a turn can end."""

    #: (label, scripts, raise_on | "dead", expected ending, who closed it)
    PATHS = (
        (
            "the model answers",
            [says("Here is what your thread holds so far.")],
            (),
            "answered",
            "model",
        ),
        (
            "the model looks something up and then answers",
            [asks(), says("You have no runs yet.")],
            (),
            "answered",
            "model",
        ),
        # TWO SILENCES, since 2026-09-11. An empty reply is named once and the
        # move is named with it, and the model gets one round to take it -
        # `EMPTY_REPLY_NUDGE`. So `empty_reply` now means silent TWICE; one
        # silence followed by an answer is the row after these, and answers.
        (
            "the model returns nothing at all, twice",
            [[], []],
            (),
            "empty_reply",
            "harness",
        ),
        (
            "the model returns whitespace, twice",
            [says("   \n  "), says("   \n  ")],
            (),
            "empty_reply",
            "harness",
        ),
        (
            "the model returns nothing, then answers when told",
            [[], says("Here is where it stands.")],
            (),
            "answered",
            "model",
        ),
        (
            "the model calls tools until the budget is gone",
            asks_n(9),
            (),
            "round_cap",
            "harness",
        ),
        (
            "the model calls tools until the budget is gone, then answers",
            [*asks_n(8), says("Given all that, here is where it stands.")],
            (),
            "answered_after_round_cap",
            "model",
        ),
        (
            # THREE identical rounds, not two, since 2026-09-13: the first
            # all-repeat round is now worth one sentence saying so
            # (`conductor.REPEAT_NUDGE`) and only the second ends the turn.
            # The owner's thread 70 lost nine turns here, every one of them to
            # a model reaching at the nearest tool it could see because the one
            # it announced had been withheld from it.
            "the model asks for the same fact twice",
            [asks(), asks(), asks(), asks()],
            (),
            "repeat_loop",
            "harness",
        ),
        (
            # AND THIS ONE NO LONGER CARRIES THE LABEL AT ALL, which is the
            # point of the nudge: told it already had the answer, the model
            # answered, and a turn that ended in an answer should not be
            # filed under a loop it did not complete.
            "the model asks for the same fact twice, then answers",
            [asks(), asks(), says("Right - here is what that means.")],
            (),
            "answered",
            "model",
        ),
        (
            "the provider reports an error",
            [[Delta(kind="error", detail="connection refused")]],
            (),
            "provider_failed",
            "harness",
        ),
        (
            # DEAD, not "raises on round 1": a round that released nothing is
            # retried now, so a provider that fails once and then answers has
            # recovered. This path is the one that never comes back, and the
            # `raise_on` rows below still mean what they always did, because a
            # stream that died AFTER releasing text is never retried.
            "the provider times out before saying anything",
            [[]],
            ("dead", 1),
            "provider_failed",
            "harness",
        ),
        (
            "the provider drops half way through the answer",
            [says("Looking at your hardw")],
            ("dead", 1),
            "provider_failed",
            "harness",
        ),
        (
            "the provider drops half way through a tool call",
            [asks()],
            ("dead", 1),
            "provider_failed",
            "harness",
        ),
        (
            "the provider dies on the round after a tool ran",
            [asks(), []],
            ("dead", 2),
            "provider_failed",
            "harness",
        ),
        # THE WALL IS AN EXIT PATH TOO, and it belongs in this table for the
        # reason the table exists: it is a new way out of the loop, and a way
        # out of the loop is a new way for a turn to end in silence. It does
        # not, and the four assertions above are how we know.
        #
        # BOTH ROWS NOW SPEAK FOR THE ENGINE, because that is the only shape
        # this wall still stops. A model stating a verdict on its own authority
        # is delivered whole and annotated, which is not an exit path at all -
        # it is the `answered` path with one more row after the words, and
        # `test_an_annotated_turn_is_still_the_answered_path` is where it lives.
        (
            "the model puts a verdict the engine did not reach in our mouth",
            [says("Based on the harness diagnosis, you should fine-tune. Here is how.")],
            (),
            conductor.WITHHELD,
            "harness",
        ),
        (
            "the model does it after looking something up",
            [asks(), says("The harness has concluded that you should fine-tune.")],
            (),
            conductor.WITHHELD,
            "harness",
        ),
    )

    def test_an_annotated_turn_is_still_the_answered_path(self):
        """A verdict the model owns is not an exit path, and still speaks.

        This is the row the two above used to be. It is asserted here rather
        than in `PATHS` because its ending is `answered` and its closer is the
        MODEL - the whole point of the change is that nothing about the turn
        degrades - and the four properties at the top of this file still hold
        over it with one extra event on the end.
        """
        self.connect()
        thread_id = self.new_thread()
        self.install(
            ScriptedProvider([says("You should fine-tune a model for this.")])
        )
        list(conductor.run_turn(thread_id, max_tool_rounds=8))

        end = self.assert_it_spoke(thread_id, "annotated")
        self.assertEqual(end["ending"], "answered")
        self.assertEqual(end["closed_by"], "model")
        self.assertIn("You should fine-tune a model for this.", self.prose(thread_id))
        kinds = [row["kind"] for row in self.rows(thread_id)]
        self.assertEqual(kinds[-2], conductor.VERDICT_KIND)

    def test_every_exit_path_ends_in_words(self):
        self.connect()
        for label, scripts, raise_on, ending, closed_by in self.PATHS:
            with self.subTest(path=label):
                thread_id = self.new_thread()
                self.install(
                    ScriptedProvider(scripts, dead_from=raise_on[1])
                    if isinstance(raise_on, tuple) and raise_on and raise_on[0] == "dead"
                    else ScriptedProvider(scripts, raise_on=raise_on)
                )
                list(conductor.run_turn(thread_id, max_tool_rounds=8))
                end = self.assert_it_spoke(thread_id, label)
                self.assertEqual(end["ending"], ending, label)
                self.assertEqual(end["closed_by"], closed_by, label)

    def test_a_fault_in_the_harness_itself_still_ends_in_words(self):
        """Our bug is still the user's turn. It gets a sentence, not a stall."""
        self.connect()
        thread_id = self.new_thread()
        self.install(
            ScriptedProvider(
                [[Delta(kind="tool_call", tool_calls=(MalformedCall(),))]]
            )
        )
        list(conductor.run_turn(thread_id))
        end = self.assert_it_spoke(thread_id, "harness fault")
        self.assertEqual(end["ending"], "harness_failed")
        self.assertIn("fault inside the harness", self.prose(thread_id))
        self.assertIn(
            "chat.error", [row["kind"] for row in self.rows(thread_id)]
        )

    def test_a_provider_that_dies_in_the_final_round_says_which_fault_it_was(self):
        """The last round is a provider call too, and it can fail like any other.

        Saying "the model would not answer" when the socket closed would send
        the user to the wrong next move.
        """
        self.connect()
        thread_id = self.new_thread()
        # DEAD, not "dies on round 4". The conductor reconnects a round that
        # released nothing, so a provider that fails once and then answers is
        # a provider that recovered - which is the feature. This test is about
        # the one that does not come back.
        self.install(ScriptedProvider(asks_n(4), dead_from=4))
        list(conductor.run_turn(thread_id, max_tool_rounds=3))
        end = self.assert_it_spoke(thread_id, "died in the final round")
        self.assertEqual(end["ending"], "provider_failed")
        self.assertIn("connection to the model failed", self.prose(thread_id))
        self.assertIn("TimeoutError", self.prose(thread_id))

    def test_a_model_that_cannot_call_tools_and_says_nothing_still_speaks(self):
        self.connect(tool_calling="no")
        thread_id = self.new_thread()
        self.install(ScriptedProvider([[]]))
        list(conductor.run_turn(thread_id))
        end = self.assert_it_spoke(thread_id, "no tool calling, empty reply")
        self.assertEqual(end["ending"], "empty_reply")

    def test_the_harness_never_puts_the_model_in_a_position_to_be_silent(self):
        """The budget is spent, so the last call offers no tools at all.

        This is the mechanism, not the symptom: a model with nothing to call
        cannot answer with a tool call, so the round either produces prose or
        produces nothing - and nothing is caught by the sentence.
        """
        self.connect()
        thread_id = self.new_thread()
        provider = self.install(ScriptedProvider(asks_n(9)))
        list(conductor.run_turn(thread_id, max_tool_rounds=4))
        self.assertEqual(provider.rounds, 5, "no final answer round was made")
        self.assertIsNone(provider.offered[-1], "tools were still on the table")
        self.assertIsNotNone(provider.offered[0])

    def test_the_last_round_carries_a_plain_instruction_to_answer(self):
        """The nudge reaches the model and never reaches the transcript.

        A harness sentence stored as a user message would be read back, in
        every turn after this one, as something the user said.
        """
        self.connect()
        thread_id = self.new_thread()
        provider = self.install(ScriptedProvider(asks_n(9)))
        captured = []
        original = provider.stream

        def watching(messages, tools=None, *, secret=None):
            captured.append([dict(m) for m in messages])
            return original(messages, tools, secret=secret)

        provider.stream = watching
        list(conductor.run_turn(thread_id, max_tool_rounds=3))

        self.assertEqual(len(captured), 4, "no final answer round was made")
        last = captured[-1][-1]
        self.assertEqual(last["role"], "user")
        # The wording changed on 2026-09-13 with the turn-language purge: the
        # sentence said "the tool phase of this turn is over" and the model was
        # repeating that back to the person. What it must still SAY is that no
        # tool will run before the answer, which is what is asserted.
        self.assertIn("No more tools will run before you answer", last["content"])
        self.assertIn("do not guess it", last["content"])

        stored = events.messages_for(thread_id)
        self.assertEqual(
            [m["content"] for m in stored if m["role"] == "user"],
            ["should i train a model for this?"],
            "the harness put words in the user's mouth in the transcript",
        )


class EverySilentEndingHasASentenceTest(unittest.TestCase):
    """The table and the code cannot drift apart without the suite noticing."""

    def test_every_ending_the_loop_can_produce_has_words_for_it(self):
        for ending in (
            "empty_reply",
            "round_cap",
            "repeat_loop",
            "provider_failed",
            "harness_failed",
            conductor.WITHHELD,
            conductor.MEASUREMENT_WITHHELD,
        ):
            with self.subTest(ending=ending):
                self.assertIn(ending, conductor.SILENT_TURN)

    def test_an_ending_nobody_wrote_a_sentence_for_still_says_something(self):
        said = conductor._closing_sentence(
            "a_path_added_after_this_test", rounds=3, detail=""
        )
        self.assertTrue(said.strip())
        self.assertIn("bug in the harness", said)

    def test_no_sentence_invents_a_number(self):
        """Invariant 5, applied to our own words.

        The only number any of these may carry is the round count, which the
        loop counted. A sentence with a second placeholder is a sentence that
        is about to state something nobody measured.
        """
        for ending, template in conductor.SILENT_TURN.items():
            with self.subTest(ending=ending):
                filled = template.format(rounds=7, detail="d")
                for token in ("{", "}"):
                    self.assertNotIn(token, filled)
                digits = [c for c in filled if c.isdigit()]
                self.assertTrue(
                    not digits or filled.count("7") == len(digits),
                    f"{ending} states a number the harness did not count",
                )

    def test_every_sentence_says_what_the_person_can_do_next(self):
        """An explanation with no next move is an apology, not an answer."""
        for ending, template in conductor.SILENT_TURN.items():
            with self.subTest(ending=ending):
                filled = template.format(rounds=4, detail="d").lower()
                self.assertTrue(
                    any(
                        clue in filled
                        for clue in (
                            "ask again",
                            "send it again",
                            "try again",
                            "connect a different model",
                            "send the question again",
                            "press yourself",
                        )
                    ),
                    f"{ending} does not tell the user what to do next",
                )


class TheProviderIsGivenFiveChancesTest(TurnTestCase):
    """Max, 2026-09-14: *"do we also have a provider retry? If the provider
    fails should we try 5 times to reconnect and try again and continue the
    workflow instead of auto quitting and leaving the work undone."*

    There was none anywhere: a stream that died ended the turn, and the run
    loop gave up after two such turns. These pin the two halves - that a
    provider which comes back is not a lost turn, and that the retry can only
    ever happen when nobody has seen anything.
    """

    class _DiesThenAnswers:
        """Down for `dies` calls, then it answers. A restarted ollama."""

        id = "fake"
        locality = "local"

        def __init__(self, dies: int, then):
            self.dies = dies
            self.then = then
            self.rounds = 0

        def stream(self, messages, tools=None, *, secret=None):
            self.rounds += 1
            if self.rounds <= self.dies:
                raise TimeoutError("connection refused")
            for delta in self.then:
                yield delta

        def capabilities(self, *, secret=None):
            raise AssertionError("the loop must not probe mid-turn")

    def test_a_provider_that_comes_back_is_not_a_lost_turn(self):
        self.connect()
        thread_id = self.new_thread()
        provider = self.install(
            self._DiesThenAnswers(3, says("Two of eight gigabytes are free."))
        )
        list(conductor.run_turn(thread_id))

        end = self.assert_it_spoke(thread_id, "a provider that came back")
        self.assertEqual(
            end["ending"], "answered",
            "the turn was lost to a provider that was only briefly down")
        self.assertEqual(provider.rounds, 4, "it did not keep trying")

    def test_it_gives_up_after_five_and_says_which_fault_it_was(self):
        self.connect()
        thread_id = self.new_thread()
        provider = self.install(self._DiesThenAnswers(99, says("never")))
        list(conductor.run_turn(thread_id))

        end = self.assert_it_spoke(thread_id, "a provider that stayed down")
        self.assertEqual(end["ending"], "provider_failed")
        self.assertEqual(
            provider.rounds, conductor.PROVIDER_TRIES,
            "a provider that is down must be tried exactly five times, not "
            "forever and not once")

    def test_it_never_retries_once_the_person_has_read_something(self):
        """THE WHOLE SAFETY OF IT. Released text is already written and already
        on screen; a second attempt would repeat it, and the person would read
        the same sentence twice with no way to tell which one was meant."""
        self.connect()
        thread_id = self.new_thread()
        provider = self.install(
            ScriptedProvider([says("The card has eight gigabytes. ")], dead_from=1)
        )
        list(conductor.run_turn(thread_id))

        end = self.assert_it_spoke(thread_id, "a provider that died mid-answer")
        self.assertEqual(end["ending"], "provider_failed")
        self.assertEqual(
            provider.rounds, 1,
            "it retried a stream that had already released a sentence")
        said = "".join(
            row["payload"].get("text", "")
            for row in self.rows(thread_id)
            if row["kind"] == "chat.delta"
        )
        self.assertEqual(
            said.count("The card has eight gigabytes."), 1,
            "the sentence reached the person twice")


class TheSameQuestionIsNotAskedTwiceTest(TurnTestCase):
    """Identical calls inside one turn are answered from what we already have."""

    def counting_registry(self):
        patcher = mock.patch.object(
            conductor.REGISTRY, "call", wraps=conductor.REGISTRY.call
        )
        counted = patcher.start()
        self.addCleanup(patcher.stop)
        return counted

    @staticmethod
    def times_run(counted, name="list_runs"):
        """How often ONE tool actually ran, rather than how often any did.

        Counted by name because the harness now runs `run_diagnosis` itself,
        once, before every turn - the standing diagnosis. A bare `call_count`
        would fold that into the number these tests are about, and the memo
        they assert on has nothing to do with it. This is narrower than the
        old assertion, not looser: it says which tool ran and how often, where
        `call_count` only said how many calls there were in total.
        """
        return sum(1 for call in counted.call_args_list if call.args[0] == name)

    @staticmethod
    def walks(counted):
        """The thread each `run_diagnosis` walk was run over, in order.

        THERE ARE TWO WALKS A TURN AND THEY ARE DIFFERENT WALKS, which is why
        this replaced a bare count of the name. One is the standing diagnosis
        over THIS thread's ledger, before the model speaks. The other is the
        same engine asked what it says over NOTHING - `thread_id=None` - which
        is the reference `conductor.says_nothing_new` compares against to tell
        a finding about this person from the sentence everybody gets. Counting
        the name alone could not tell them apart, and a test that cannot tell
        them apart cannot notice one of them going missing.
        """
        return [
            call.kwargs.get("thread_id")
            for call in counted.call_args_list
            if call.args[0] == "run_diagnosis"
        ]

    def test_an_identical_call_is_not_run_a_second_time(self):
        self.connect()
        counted = self.counting_registry()
        thread_id = self.new_thread()
        self.install(ScriptedProvider([asks(), asks(), says("Fine, no.")]))
        list(conductor.run_turn(thread_id))

        self.assertEqual(
            self.times_run(counted),
            1,
            "the same tool with the same arguments ran twice in one turn",
        )
        self.assertEqual(
            self.walks(counted),
            [thread_id, None],
            "one walk over this thread and one over nothing, once each",
        )
        results = [
            row["payload"]
            for row in self.rows(thread_id)
            if row["kind"] == "tool.result"
        ]
        self.assertEqual(len(results), 2, "the repeat was hidden from the log")
        self.assertNotIn("repeat_of", results[0])
        self.assertEqual(results[1]["repeat_of"], results[0]["id"])
        self.assertIs(results[1]["rerun"], False)
        self.assertEqual(results[1]["result"], results[0]["result"])

    def test_the_model_is_told_it_already_has_the_answer(self):
        self.connect()
        thread_id = self.new_thread()
        provider = self.install(
            ScriptedProvider([asks(), asks(), says("Fine, no.")])
        )
        captured = []
        original = provider.stream

        def watching(messages, tools=None, *, secret=None):
            captured.append([dict(m) for m in messages])
            return original(messages, tools, secret=secret)

        provider.stream = watching
        list(conductor.run_turn(thread_id))

        tool_messages = [m for m in captured[-1] if m["role"] == "tool"]
        self.assertEqual(len(tool_messages), 2)
        repeated = tool_messages[-1]
        self.assertIn("You already called list_runs", repeated["content"])
        self.assertIn("Do not call it again", repeated["content"])
        # It still carries the result, inside the envelope it always had.
        self.assertIn('<data source="tool:list_runs">', repeated["content"])

    def test_a_round_of_nothing_but_repeats_ends_the_tool_phase(self):
        """No new fact is possible, so another round cannot help."""
        self.connect()
        thread_id = self.new_thread()
        provider = self.install(ScriptedProvider([asks(), asks(), asks(), asks()]))
        list(conductor.run_turn(thread_id, max_tool_rounds=8))
        end = self.rows(thread_id)[-1]["payload"]
        self.assertEqual(end["ending"], "repeat_loop")
        # FOUR, NOT THREE, SINCE 2026-09-13, and the extra one is the nudge.
        # Ending the turn on the FIRST all-repeat round cost the owner nine
        # turns: the tool his model announced had been withheld by the scoper
        # (app/tools/blocks.py), so it reached at the nearest one it could see
        # and was ended for it. One sentence saying "you already have that,
        # call something else" is cheap; the turn was not.
        self.assertEqual(
            provider.rounds, 4, "the loop kept going after it stopped learning"
        )
        told = [
            row for row in self.rows(thread_id)
            if row["kind"] == "conductor.notice"
            and (row["payload"] or {}).get("reason") == "repeated_every_call"
        ]
        self.assertEqual(len(told), 1, "it was ended without being told once")

    def test_a_different_argument_is_a_different_question(self):
        self.connect()
        counted = self.counting_registry()
        thread_id = self.new_thread()
        self.install(
            ScriptedProvider(
                [asks(limit=1), asks(limit=2), says("Two different looks.")]
            )
        )
        list(conductor.run_turn(thread_id))
        self.assertEqual(self.times_run(counted), 2)

    def test_the_memory_is_one_turn_deep(self):
        """A fact can change between turns. It cannot change inside one."""
        self.connect()
        counted = self.counting_registry()
        thread_id = self.new_thread()
        for _ in range(2):
            self.install(ScriptedProvider([asks(), says("Done.")]))
            list(conductor.run_turn(thread_id))
        self.assertEqual(self.times_run(counted), 2)
        self.assertEqual(
            self.walks(counted),
            [thread_id, None, thread_id, None],
            "both walks are once per TURN, not once per thread",
        )


class TheModelIsNotObeyedBeyondWhatWasOfferedTest(TurnTestCase):
    def test_a_tool_call_from_a_round_that_offered_no_tools_is_not_run(self):
        """The final round offers nothing, so a call in it is not a call.

        Same rule as "we never emulate tool calling by parsing JSON out of
        prose", in the other direction: a call we did not offer arrived from
        somewhere we did not authorise.
        """
        self.connect()
        counted_thread = self.new_thread()
        self.install(ScriptedProvider(asks_n(6)))
        list(conductor.run_turn(counted_thread, max_tool_rounds=3))
        self.assertEqual(
            [row["kind"] for row in self.rows(counted_thread)].count("tool.call"),
            3,
            "a tool ran in a round where no tools were offered",
        )


class ASilenceGetsOneMoreRoundTest(EveryExitPathSpeaksTest):
    """The retry, measured with the same instrument as every other exit.

    2026-09-11, thread 64, twice: eight lookups, then no words. Thirteen of
    twenty in the record. The harness now names the silence once and names
    the move, and the model gets one round - the `PATHS` rows above hold
    what that does to the endings. Held here: the shape of the retry itself
    - one round, never more, never a wider tool budget - and that the memory
    note reads the events a real turn actually writes.
    """

    def test_a_silence_costs_exactly_one_extra_provider_call(self):
        self.connect()
        thread_id = self.new_thread()
        provider = self.install(ScriptedProvider([[], says("Here it is.")]))
        list(conductor.run_turn(thread_id, max_tool_rounds=8))
        self.assertEqual(provider.rounds, 2)

    def test_two_silences_do_not_earn_a_third_round(self):
        self.connect()
        thread_id = self.new_thread()
        provider = self.install(ScriptedProvider([[], [], says("never asked")]))
        list(conductor.run_turn(thread_id, max_tool_rounds=8))
        self.assertEqual(provider.rounds, 2)
        self.assertNotIn("never asked", self.prose(thread_id))

    def test_the_retry_does_not_widen_the_tool_budget(self):
        """A model that calls tools every round gets exactly its budget. The
        extra round exists only after a silence - a first cut handed every
        tool-calling model a ninth round, and `test_the_loop_is_bounded`
        caught it as four calls on a budget of three."""
        self.connect()
        thread_id = self.new_thread()
        self.install(ScriptedProvider(asks_n(9)))
        list(conductor.run_turn(thread_id, max_tool_rounds=3))
        kinds = [row["kind"] for row in self.rows(thread_id)]
        self.assertEqual(kinds.count("tool.call"), 3)

    def test_the_nudge_names_the_silence_and_the_move(self):
        # CHANGED CONTRACT, 2026-09-22: one line, the silence named and ONE
        # move (`conductor._silence_retry`) - the tool the walk names when it
        # is on offer, else a one-sentence answer; write_plan when planning.
        named = conductor._silence_retry(
            {"next_step": {"tool": "measure_eval_set"}}, frozenset({"measure_eval_set"}),
            full=False, planning=False,
        )
        self.assertIn("reply was empty", named)
        self.assertIn("call measure_eval_set now", named)
        bare = conductor._silence_retry(None, frozenset(), full=False, planning=False)
        self.assertIn("one or two plain sentences", bare)
        self.assertIn(
            "write_plan", conductor._silence_retry(None, frozenset(), full=False, planning=True)
        )
        self.assertLess(len(named), 160, "a retry a stalled model can act on is short")

    def test_the_memory_note_reads_what_a_real_turn_wrote(self):
        """The note pairs `tool.call` with `tool.result` by name and order.
        A unit test could append events in any shape it liked; this runs a
        real turn and reads them back, so the shapes cannot drift apart
        without this going red."""
        self.connect()
        thread_id = self.new_thread()
        self.install(ScriptedProvider([asks(), says("You have no runs yet.")]))
        list(conductor.run_turn(thread_id, max_tool_rounds=8))
        note = conductor._already_read_note(thread_id)
        self.assertIn("Already read in this conversation", note)
        self.assertIn("list_runs", note)


PHASED = "\n".join([
    "## Phase 1 - Data",
    "Carve rows into an eval set.",
    "",
    "## Phase 2 - Baseline",
    "Measure the connected model on it first.",
])


class AProsePlanIsThePlanTest(EveryExitPathSpeaksTest):
    """Measured 2026-09-11: handed `write_plan`, the owner's model never called
    it - it wrote six phases into the reply in 28 seconds. So an answered
    plan-mode turn whose text carries `## Phase` headings becomes the plan,
    verbatim, the same way the Build button already treats the last reply.

    THE FIXTURE IS CHOSEN BY CHECKING IT AGAINST THE GATE READER, not by
    hoping. The first draft read *Carve an eval set from what is attached*
    and was withheld whole: `gates_claimed_by` saw `eval`, `set` and the
    assert-verb `is` in one sentence and read it as G0_EVAL_SET satisfied.
    That reader is coarse by design - its docstring says the failure mode
    is to miss a fabrication, never to block a true sentence - and this is
    the sentence where it blocks one. Recorded here rather than routed
    around silently; the criterion vocabulary fix (2026-09-11) closed the
    live catch, and this one is the next candidate.
    """

    def test_phased_prose_in_plan_mode_is_saved_as_the_plan(self):
        self.connect()
        thread_id = self.new_thread()
        events.set_thread_mode(thread_id, "plan")
        self.install(ScriptedProvider([says(PHASED)]))
        list(conductor.run_turn(thread_id, max_tool_rounds=8))
        self.assertEqual(events.get_thread(thread_id)["plan"], PHASED)
        kinds = [row["kind"] for row in self.rows(thread_id)]
        self.assertIn("thread.plan_written", kinds)

    def test_prose_without_phases_is_not_a_plan(self):
        self.connect()
        thread_id = self.new_thread()
        events.set_thread_mode(thread_id, "plan")
        self.install(ScriptedProvider([says("Here is what I would do, roughly.")]))
        list(conductor.run_turn(thread_id, max_tool_rounds=8))
        self.assertIsNone(events.get_thread(thread_id)["plan"])

    def test_a_build_turn_does_not_rewrite_the_plan_from_prose(self):
        """In build the plan is the standing instruction; the reply narrates
        working it down, and narration with headings is not a new plan.

        LAW NARROWED 2026-09-18 (P0's live row): this used to assert on a
        thread with NO plan. Under Full, which forces build, the model wrote
        two `## Phase` reports and never called write_plan, and the Run
        button answered 409 to a thread that had never had a plan. So a
        plan-less build thread now ADOPTS the prose plan; a thread that has
        one keeps it, which is the law this test was really about."""
        self.connect()
        thread_id = self.new_thread()
        events.set_thread_mode(thread_id, "build")
        standing = "## Phase 1 - Keep" + chr(10) + "- [ ] Measure the baseline with measure_baseline"
        events.set_thread_plan(thread_id, standing)
        self.install(ScriptedProvider([says(PHASED)]))
        list(conductor.run_turn(thread_id, max_tool_rounds=8))
        self.assertEqual(events.get_thread(thread_id)["plan"], standing)

    def test_a_plan_less_build_turn_adopts_the_prose_plan(self):
        """The half P0 found missing."""
        self.connect()
        thread_id = self.new_thread()
        events.set_thread_mode(thread_id, "build")
        self.install(ScriptedProvider([says(PHASED)]))
        list(conductor.run_turn(thread_id, max_tool_rounds=8))
        self.assertIn("## Phase 1", events.get_thread(thread_id)["plan"] or "")


if __name__ == "__main__":
    unittest.main()
