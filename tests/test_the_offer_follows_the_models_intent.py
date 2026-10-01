"""The schemas on the wire follow what the model MEANT, not only what it wrote.

MEASURED 2026-09-23, a live journey at 0ffefdd on a scratch engine with the
owner's model (minicpm5-hermes, a 1B local thinking model), a fresh Build/Full
thread whose project folder held `ml-principles-dataset/`: 45 seconds, ended
`answered_after_repeat_loop`. Its REASONING said three times *"Let me use
profile_repository on the ml-principles-dataset folder"*; its tool channel
called `list_local_models` three times with the same empty arguments.
`turn.context.schemas_on_wire` said why - ten schemas rode and
`profile_repository`, `list_context`, `profile_dataset`, `read_context_file`
and `preview_dataset_rows` were all withheld. Ollama lets a model call only a
tool whose schema was sent, so it repeated the one it could. A direct probe of
the same model with three schemas including `profile_repository` called it
correctly in 1.2 s. The offer, not the model, was the fault.

One case per exit, each red before the change it locks:

  (a) the reasoning names a withheld tool -> it rides next, and `because` says
      the model named it in its reasoning;
  (b) the same call twice with the same arguments -> withdrawn from the next
      wire, still considered (so still named in the capability list), with the
      note in `withheld_because`; different arguments are not a repeat;
  (d) a fresh thread on a project with a folder and no dataset on record ->
      the discovery tools ride with the core.

(c), a tool call written as text, is an adapter's job and lives in
`tests/test_a_tool_call_written_as_text_is_a_tool_call.py`.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT, Path(__file__).resolve().parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import support  # noqa: E402
from app import conductor, db, events, modes  # noqa: E402
from app.providers import Delta, ToolCall  # noqa: E402
from app.providers import store as provider_store  # noqa: E402
from app.tools import blocks  # noqa: E402

#: The sentence the owner's model thought, three times, verbatim.
THOUGHT = "Let me use profile_repository on the ml-principles-dataset folder."


class _OnAFreshBuildThread(unittest.TestCase):
    """A build thread with no plan and nothing measured, on a folder-less
    project - so every assertion below is about the source it names and not
    about the discovery rule, which (d) drives on its own."""

    def setUp(self) -> None:
        support.sandbox(self)
        os.environ.pop(blocks.ALL_SCHEMAS_VARIABLE, None)
        self.thread = int(events.create_thread("t", mode="build")["id"])
        self.payload = conductor._standing_diagnosis(self.thread)
        self.active = blocks.active(self.payload, thread_id=self.thread)
        self.among = modes.tools_for("build", self.active.names())

    def wire(self, **kwargs):
        return blocks.on_the_wire(
            self.active,
            thread_id=self.thread,
            payload=self.payload,
            among=self.among,
            **kwargs,
        )


class TheReasoningIsReadTest(_OnAFreshBuildThread):
    """(a) R1: a thinking model states its intent in `reasoning`, not `content`."""

    def test_a_tool_named_only_in_the_reasoning_rides_and_says_why(self):
        quiet = self.wire()
        self.assertIn("profile_repository", self.among, "the pool never held it")
        self.assertNotIn(
            "profile_repository", quiet.tools, "the fixture already handed it over"
        )
        loud = self.wire(reasoning=THOUGHT)
        self.assertIn("profile_repository", loud.tools)
        self.assertEqual(
            loud.because["profile_repository"],
            blocks.BECAUSE_THE_REASONING_NAMED.format(tool="profile_repository"),
        )
        self.assertIn("reasoning", loud.because["profile_repository"])

    def test_the_text_rule_still_stands_and_is_named_first(self):
        """The existing door keeps its own reason when both registers name it."""
        both = self.wire(
            last_reply="I will run profile_repository.", reasoning=THOUGHT
        )
        self.assertIn("last reply", both.because["profile_repository"])

    def test_the_conductor_reads_this_turns_reasoning_and_not_the_last_ones(self):
        events.append("turn.started", {}, thread_id=self.thread)
        events.append(
            conductor.REASONING_KIND,
            {"text": "I should run measure_baseline."},
            thread_id=self.thread,
        )
        events.append("turn.started", {}, thread_id=self.thread)
        events.append(conductor.REASONING_KIND, {"text": "Let me use "}, thread_id=self.thread)
        events.append(
            conductor.REASONING_KIND,
            {"text": "profile_repository on the folder."},
            thread_id=self.thread,
        )
        thought = conductor._what_the_last_round_thought(self.thread)
        self.assertIn("profile_repository", thought, "the rows were not joined")
        self.assertNotIn("measure_baseline", thought, "an older turn was read")

    def test_the_reasoning_is_capped_and_the_cut_names_nothing(self):
        """The last ~4,000 characters, and a cut that lands inside a longer
        name must not leave a shorter registered one behind: `recall` is the
        tail of `measure_retriever_recall`."""
        events.append("turn.started", {}, thread_id=self.thread)
        filler = "x " * 3000
        # The last REASONING_CAP characters begin at the `r` of `recall`.
        pad = "." * (blocks.REASONING_CAP - len("recall") - 2 - len(THOUGHT))
        text = (
            "profile_dataset " + filler + "measure_retriever_recall"
            + " " + pad + " " + THOUGHT
        )
        self.assertTrue(text[-blocks.REASONING_CAP:].startswith("recall "))
        events.append(
            conductor.REASONING_KIND, {"text": text}, thread_id=self.thread
        )
        thought = conductor._what_the_last_round_thought(self.thread)
        self.assertLessEqual(len(thought), blocks.REASONING_CAP)
        self.assertIn("profile_repository", thought)
        self.assertNotIn("profile_dataset", thought, "the head was not dropped")
        self.assertNotIn("recall", blocks._identifiers(thought))

    def test_the_next_turn_carries_the_tool_the_last_one_thought_of(self):
        """THROUGH `run_turn`: the call site passes the reasoning, and the
        request the adapter receives on the next turn carries the schema."""
        row = provider_store.create(
            "Fake", "http://127.0.0.1:11434", "fake-model", "ollama"
        )
        ready = provider_store.record_capabilities(
            row["id"],
            type(
                "Caps", (),
                {"tool_calling": True, "detail": "set by the test",
                 "ctx_len": None, "provenance": {}},
            )(),
        )
        provider_store.set_active(ready["id"])
        events.add_message(self.thread, "user", "look at my data")
        model = _AScriptedModel(
            [
                [Delta(kind="reasoning", text=THOUGHT), Delta(kind="text", text="Looking.")],
                [Delta(kind="text", text="ok")],
            ]
        )
        original = conductor.build
        conductor.build = lambda *a, **k: model
        self.addCleanup(setattr, conductor, "build", original)
        list(conductor.run_turn(self.thread))
        first = {t["function"]["name"] for t in model.sent[0]["tools"]}
        self.assertNotIn("profile_repository", first, "it rode before it was named")
        events.add_message(self.thread, "user", "go on")
        list(conductor.run_turn(self.thread))
        second = {t["function"]["name"] for t in model.sent[1]["tools"]}
        self.assertIn("profile_repository", second)
        said = events.latest("turn.started", self.thread)["payload"]["schemas_on_wire"]
        self.assertIn("reasoning", said["because"]["profile_repository"])


class ARepeatedCallIsWithdrawnTest(_OnAFreshBuildThread):
    """(b) R2: a small model cannot repeat what is not offered."""

    def test_the_same_call_twice_is_withdrawn_and_still_considered(self):
        self.assertIn("list_local_models", self.wire().tools, "the core lost it")
        wire = self.wire(repeated=["list_local_models"])
        self.assertNotIn("list_local_models", wire.tools)
        self.assertIn("list_local_models", wire.considered, "the name left the room")
        said = wire.as_dict()
        self.assertIn("list_local_models", said["withheld"])
        self.assertEqual(
            said["withheld_because"]["list_local_models"],
            "already called this turn with these arguments; the result is above",
        )
        self.assertEqual(
            blocks.BECAUSE_ALREADY_CALLED,
            "already called this turn with these arguments; the result is above",
        )

    def test_only_the_repeated_tool_goes(self):
        wire = self.wire(repeated=["list_local_models"])
        for name in blocks.ALWAYS_ON:
            if name == "list_local_models":
                continue
            with self.subTest(tool=name):
                self.assertIn(name, wire.tools)
        self.assertEqual(set(wire.as_dict()["withheld_because"]), {"list_local_models"})

    def test_the_note_survives_the_capability_list(self):
        """The list is complete whatever rode; the withdrawn tool is named
        and unmarked, so the model sees it exists and that it has no schema."""
        from app.instructions import capabilities

        wire = self.wire(repeated=["list_local_models"])
        rendered = capabilities.render(detail=False, loaded=set(wire.tools))
        self.assertIn("- `list_local_models`", rendered)
        self.assertNotIn("- `list_local_models` (*)", rendered)

    def _two_calls(self, first: dict, second: dict) -> tuple[str, ...]:
        """Two real calls through `_run_tool` with one turn's memo, then the
        conductor's reading of which were repeats."""
        events.append("turn.started", {}, thread_id=self.thread)
        memo: dict = {}
        conversation: list = []
        for index, arguments in enumerate((first, second)):
            call = ToolCall(id=f"c{index}", name="read_plan", arguments=arguments)
            list(conductor._run_tool(self.thread, conversation, call, memo))
        return conductor._calls_repeated_this_turn(self.thread)

    def test_the_conductor_reads_a_repeat_with_the_same_arguments(self):
        self.assertEqual(self._two_calls({}, {}), ("read_plan",))

    def test_different_arguments_are_not_a_repeat(self):
        self.assertEqual(self._two_calls({}, {"phase": "2"}), ())

    def test_a_repeat_from_an_earlier_turn_is_not_this_turns(self):
        self._two_calls({}, {})
        events.append("turn.started", {}, thread_id=self.thread)
        self.assertEqual(conductor._calls_repeated_this_turn(self.thread), ())

    def test_the_next_rounds_wire_withdraws_it(self):
        """The helper the round loop calls between rounds: reads the reply, the
        reasoning and the repeats of THIS turn, and withdraws the repeat."""
        self._two_calls({}, {})
        events.append(
            conductor.REASONING_KIND, {"text": THOUGHT}, thread_id=self.thread
        )
        wire = conductor._the_wire_for_the_next_round(
            self.thread, self.active, self.payload, self.among
        )
        self.assertNotIn("read_plan", wire.tools)
        self.assertIn("read_plan", wire.considered)
        self.assertIn("read_plan", wire.as_dict()["withheld_because"])
        self.assertIn("profile_repository", wire.tools)


class DiscoveryRidesFirstTest(unittest.TestCase):
    """(d) a fresh thread on a folder with nothing on record reaches the
    folder: the discovery tools ride with the core."""

    def setUp(self) -> None:
        support.sandbox(self)
        os.environ.pop(blocks.ALL_SCHEMAS_VARIABLE, None)
        self.root = Path(tempfile.mkdtemp())
        (self.root / "ml-principles-dataset").mkdir()
        project = db.create_project("Owner", root_path=str(self.root))
        self.thread = int(
            events.create_thread("t", project_id=int(project["id"]), mode="build")["id"]
        )

    def wire(self, thread=None, payload=None, **kwargs):
        thread = self.thread if thread is None else thread
        payload = conductor._standing_diagnosis(thread) if payload is None else payload
        active = blocks.active(payload, thread_id=thread)
        return blocks.on_the_wire(
            active,
            thread_id=thread,
            payload=payload,
            among=modes.tools_for("build", active.names()),
            **kwargs,
        )

    def test_the_discovery_tools_ride_on_a_fresh_thread_with_a_folder(self):
        wire = self.wire()
        for name in blocks.DISCOVERY:
            with self.subTest(tool=name):
                self.assertIn(name, wire.considered, "the pool never held it")
                self.assertIn(name, wire.tools)
                self.assertEqual(wire.because[name], blocks.BECAUSE_NOTHING_ON_RECORD)
        self.assertEqual(
            blocks.BECAUSE_NOTHING_ON_RECORD,
            "no dataset on record; discovery rides first",
        )
        for name in blocks.ALWAYS_ON:
            with self.subTest(core=name):
                self.assertIn(name, wire.tools)

    def test_the_wire_stays_modest(self):
        """Nine core, five discovery, and the diagnosis's own move: the
        owner's journey sent ten, and this is the room it lacked."""
        wire = self.wire()
        self.assertLessEqual(len(wire.tools), 16, sorted(wire.tools))
        self.assertLess(len(wire.tools), len(wire.considered))

    def test_a_project_with_no_folder_has_nothing_to_discover(self):
        # Its own folder-less project: a thread created with no project lands
        # in the lowest-id one, which here is the one WITH a folder.
        elsewhere = db.create_project("No folder")
        self.assertFalse(elsewhere.get("root_path"))
        bare = int(
            events.create_thread("t", project_id=int(elsewhere["id"]), mode="build")["id"]
        )
        wire = self.wire(thread=bare)
        for name in blocks.DISCOVERY:
            with self.subTest(tool=name):
                self.assertNotEqual(
                    wire.because.get(name), blocks.BECAUSE_NOTHING_ON_RECORD
                )

    def test_a_dataset_on_record_ends_the_rule(self):
        rows = [{"fact": "eval_size_n", "tool": "measure_eval_set", "value": 48}]
        wire = self.wire(evidence_rows=rows)
        for name in blocks.DISCOVERY:
            with self.subTest(tool=name):
                self.assertNotEqual(
                    wire.because.get(name), blocks.BECAUSE_NOTHING_ON_RECORD
                )

    def test_a_machine_fact_is_not_a_dataset(self):
        """Asking what GPU this is first does not put a dataset on record."""
        rows = [{"fact": "vram_gb", "tool": "inspect_hardware", "value": 8.0}]
        wire = self.wire(evidence_rows=rows)
        self.assertEqual(
            wire.because.get("profile_repository"), blocks.BECAUSE_NOTHING_ON_RECORD
        )

    def test_a_settled_diagnosis_does_not_widen(self):
        payload = dict(conductor._standing_diagnosis(self.thread), verdict="NO_TRAIN")
        wire = self.wire(payload=payload)
        for name in blocks.DISCOVERY:
            with self.subTest(tool=name):
                self.assertNotEqual(
                    wire.because.get(name), blocks.BECAUSE_NOTHING_ON_RECORD
                )


class TheWireMovesBetweenRoundsTest(_OnAFreshBuildThread):
    """THROUGH `run_turn`, inside ONE turn - which is where the owner's journey
    failed: reasoning named `profile_repository` on round one, and a call
    repeated with the same arguments on round two."""

    def test_round_two_carries_the_thought_and_round_three_drops_the_repeat(self):
        row = provider_store.create(
            "Fake", "http://127.0.0.1:11434", "fake-model", "ollama"
        )
        ready = provider_store.record_capabilities(
            row["id"],
            type(
                "Caps", (),
                {"tool_calling": True, "detail": "set by the test",
                 "ctx_len": None, "provenance": {}},
            )(),
        )
        provider_store.set_active(ready["id"])
        events.add_message(self.thread, "user", "look at my data")
        call = lambda index: Delta(  # noqa: E731 - one line per round below
            kind="tool_call",
            tool_calls=(ToolCall(id=f"c{index}", name="read_plan", arguments={}),),
        )
        model = _AScriptedModel(
            [
                [Delta(kind="reasoning", text=THOUGHT), call(0)],
                [call(1)],
                [Delta(kind="text", text="ok")],
            ]
        )
        original = conductor.build
        conductor.build = lambda *a, **k: model
        self.addCleanup(setattr, conductor, "build", original)
        list(conductor.run_turn(self.thread))
        rounds = [{t["function"]["name"] for t in sent["tools"] or ()} for sent in model.sent]
        self.assertGreaterEqual(len(rounds), 3, rounds)
        self.assertNotIn("profile_repository", rounds[0])
        self.assertIn("read_plan", rounds[0])
        self.assertIn("profile_repository", rounds[1], "the thought did not ride next round")
        self.assertIn("read_plan", rounds[1], "one call is not a repeat")
        self.assertNotIn("read_plan", rounds[2], "the repeat was offered again")
        self.assertIn("run_diagnosis", rounds[2], "the withdrawal took the core with it")


class _AScriptedModel:
    """A model that says what the test told it to, and keeps what it was sent."""

    id = "fake"
    locality = "local"

    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.sent = []

    def stream(self, messages, tools=None, *, secret=None):
        self.sent.append({"messages": [dict(m) for m in messages], "tools": tools})
        for delta in self.rounds.pop(0) if self.rounds else []:
            yield delta

    def capabilities(self, *, secret=None):
        raise AssertionError("the loop must not probe mid-turn")


if __name__ == "__main__":
    unittest.main()
