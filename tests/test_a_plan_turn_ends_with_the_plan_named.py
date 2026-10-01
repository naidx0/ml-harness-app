"""A planning turn ends by naming the plan, and an announced move is made.

Max, 2026-09-12, of his planning agent: it said "Let me look at what's
already in the project and check the current plan status." and stopped; sent
again, "Let me read the current plan..." and stopped. And: *"saying your plan
is built, with the following phases, it's ready to go, do you want to run it?
... that would be nice to see, then I would stop asking it."*

Two halves. `said_it_would_and_did_nothing` reads a reply that announces a
move and makes none, and the loop hands the turn back once with
`INTENT_NUDGE` (in `conversation`, never in `messages`). And every answered
planning turn on a thread with a plan ends with a `thread.plan_ready` row
carrying the phase names, so the transcript says what the plan is and where
the Build door is whether or not the model said so.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import conductor, events  # noqa: E402
from app.providers import Delta, ToolCall  # noqa: E402
from app.providers import store as provider_store  # noqa: E402
from app.tools import planning  # noqa: E402
from app.tools.registry import REGISTRY  # noqa: E402

PLAN = "\n".join(
    [
        "# Train the router",
        "",
        "## Root of the ask",
        "A small model that routes tickets.",
        "",
        "## Phase 1 - Data",
        "- [ ] Carve the eval set from tickets.jsonl",
        "",
        "## Phase 2 - Baseline",
        "- [x] Measure the baseline",
        "",
        "## Verification",
        "- [ ] Compare the adapter to the baseline",
    ]
)


class SaidItWouldTest(unittest.TestCase):
    def test_an_announced_move_with_nothing_after_it(self):
        for said in (
            "Let me look at what's already in the project and check the current plan status.",
            "Let me read the current plan to see what's there and what needs updating.",
            "I'll read the plan first.",
            "Now I need to inspect the hardware.",
        ):
            self.assertTrue(conductor.said_it_would_and_did_nothing(said), said)

    def test_a_reply_that_did_the_work_is_not_an_intent(self):
        for said in (
            "Plan saved. It has three phases: data, baseline, verification.",
            "The plan is already saved and complete. Let me know if you want changes.",
            "Let me know if this works for you.",
            "",
            "Let me " + ("explain the whole thing in detail. " * 40),
        ):
            self.assertFalse(conductor.said_it_would_and_did_nothing(said), said[:60])


class HeadingsTest(unittest.TestCase):
    def test_the_phase_headings_in_order(self):
        self.assertEqual(
            planning.headings_in(PLAN),
            ["Root of the ask", "Phase 1 - Data", "Phase 2 - Baseline", "Verification"],
        )


class _Fake:
    """An adapter whose rounds are scripted: each entry is what the model
    says (text) or does (a tool name) on that round."""

    id = "fake"
    locality = "local"

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.seen: list[list[dict[str, Any]]] = []

    def stream(self, messages, tools=None, *, secret=None):
        self.seen.append([dict(m) for m in messages])
        step = self.script.pop(0) if self.script else "Done."
        if isinstance(step, tuple):
            name, args = step
            yield Delta(kind="tool_call", tool_calls=(ToolCall(f"c{len(self.seen)}", name, args),))
        else:
            yield Delta(kind="text", text=str(step))


def _connect() -> None:
    row = provider_store.create("Fake", "http://127.0.0.1:11434", "fake-model", "ollama")
    provider_store.record_capabilities(
        row["id"],
        type("Caps", (), {"tool_calling": True, "detail": "test", "ctx_len": None, "provenance": {}})(),
    )
    provider_store.set_active(row["id"])


def _run(thread: int, fake: _Fake) -> list[dict[str, Any]]:
    original = conductor.build
    conductor.build = lambda *a, **k: fake
    try:
        for _ in conductor.run_turn(thread):
            pass
    finally:
        conductor.build = original
    return events.since(f"thread:{thread}", limit=5000)


class TheAnnouncedMoveIsMadeTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        _connect()

    def test_the_turn_is_handed_back_once_and_the_tool_runs(self):
        thread = int(events.create_thread("t", mode="plan")["id"])
        events.set_thread_plan(thread, PLAN)
        events.add_message(thread, "user", "make the plan thorough and go")
        fake = _Fake(["Let me read the current plan to see what's there.", ("read_plan", {}), "The plan stands as written."])
        rows = _run(thread, fake)
        calls = [r["payload"].get("name") for r in rows if r["kind"] == "tool.call"]
        self.assertEqual(calls, ["read_plan"])
        notices = [r["payload"].get("reason") for r in rows if r["kind"] == "conductor.notice"]
        self.assertIn("said_it_would_and_did_nothing", notices)
        nudges = [m for turn in fake.seen for m in turn if m.get("content") == conductor.INTENT_NUDGE]
        self.assertEqual(len(nudges), 2, "the nudge was in the conversation for the rounds after it, and only there")
        self.assertNotIn(
            conductor.INTENT_NUDGE, [m["content"] for m in events.messages_for(thread)],
            "scaffolding never lands in the thread's messages",
        )

    def test_a_second_intent_is_not_nudged_again(self):
        thread = int(events.create_thread("t", mode="plan")["id"])
        events.add_message(thread, "user", "go")
        fake = _Fake(["Let me look at the project.", "Let me read the plan.", "I'll do it."])
        rows = _run(thread, fake)
        ends = [r["payload"].get("ending") for r in rows if r["kind"] == "stream.end"]
        self.assertEqual(ends[-1], "answered")
        self.assertEqual(len(fake.seen), 2, "one nudge, then the reply stands")


class TheBuildToolIsNamedInPlanModeTest(unittest.TestCase):
    """Max, 2026-09-12, in plan mode: "go do that now" - "Let me execute what
    I can now with the available tools." / "I'll execute the remaining
    blocked phases now." - and nothing, because measure_baseline is not
    offered in plan mode. The harness says which door."""

    def setUp(self) -> None:
        support.sandbox(self)
        _connect()

    def test_the_second_intent_gets_the_build_mode_sentence(self):
        thread = int(events.create_thread("t", mode="plan")["id"])
        events.set_thread_plan(thread, PLAN)
        events.add_message(thread, "user", "what can you solve now? go do it")
        rows = _run(thread, _Fake(["Let me run measure_baseline now.", "I'll run measure_baseline and inspect_hardware now."]))
        harness = [r["payload"] for r in rows if r["kind"] == "chat.delta" and r["payload"].get("written_by") == "harness"]
        self.assertTrue(harness, "the harness said why the move was not available")
        said = harness[-1]["text"]
        self.assertIn("measure_baseline", said)
        self.assertNotIn("inspect_hardware", said, "a lookup IS offered in plan mode, so it is not named as a build tool")
        self.assertIn("Switch to Build", said)

    def test_one_intent_that_is_then_acted_on_gets_no_sentence(self):
        thread = int(events.create_thread("t", mode="plan")["id"])
        events.add_message(thread, "user", "look at the machine")
        rows = _run(thread, _Fake(["Let me inspect the hardware.", ("inspect_hardware", {}), "Done: one card."]))
        harness = [r for r in rows if r["kind"] == "chat.delta" and r["payload"].get("written_by") == "harness"]
        self.assertEqual(harness, [])


class RunDiagnosisNamesTheNextMoveTest(unittest.TestCase):
    """MEASURED 2026-09-13, ten turns of it: the walk stopped at a node
    reading `task_family` and `modality`, two facts NO tool measures. The
    next-move line named the next ANSWERABLE question instead - `classes_n`,
    settled by assess_the_data - so the model ran that tool, the verdict did
    not move, and the same sentence came back. A gap is a hard stop; it is
    named first, with the door out of it."""

    def setUp(self) -> None:
        support.sandbox(self)
        self.thread = int(events.create_thread("t", mode="build")["id"])

    def run_it(self, facts=None):
        from app.tools import evidence as _evidence

        return REGISTRY.call(
            "run_diagnosis", {"facts": facts} if facts else {},
            actor=_evidence.MODEL, thread_id=self.thread,
        )

    def counted_with_nothing_to_derive_from(self):
        """An eval set counted on this thread, with no call row naming its file.

        `full_defaults._from_the_eval_file` finds the file through the thread's
        own `tool.call` rows; without one it has nothing to read, so a `derive`
        fact stays a gap the model has to decide - the state these sentences
        are about. (Counting it through the conductor settles the fact:
        tests/test_a_text_eval_set_settles_its_modality.py.)
        """
        import json as _json
        import tempfile as _tempfile

        from app.tools import evidence as _evidence

        folder = Path(_tempfile.mkdtemp())
        path = folder / "eval.jsonl"
        path.write_bytes(
            "".join(_json.dumps({"q": f"q{i}", "a": "yes"}) + chr(10) for i in range(40)).encode()
        )
        counted = REGISTRY.call(
            "measure_eval_set", {"path": str(path)}, actor=_evidence.MODEL,
            thread_id=self.thread,
        )
        self.assertTrue(counted["ok"], counted)
        REGISTRY.call(
            "state_facts", {"facts": {"target_score": 0.8}}, actor=_evidence.USER,
            thread_id=self.thread,
        )

    def test_a_derived_gap_on_an_uncounted_thread_names_the_count(self):
        """CHANGED CONTRACT, 2026-09-22. `task_family` and `modality` are
        `source: derive`, and the harness now derives them from a counted eval
        set on every permission, not only Full. So a thread with nothing
        counted is told to count, the door to decide it anyway stays on the
        sentence, and "decide it yourself" is kept for a gap no count answers."""
        out = self.run_it()
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["next_step"]["kind"], "gap")
        self.assertIn(out["next_step"]["fact"], ("task_family", "modality"))
        self.assertEqual(out["next_step"]["tool"], "measure_eval_set")
        self.assertIn("Run measure_eval_set now", out["next"])
        self.assertIn('{"facts": {"' + out["next_step"]["fact"] + '"', out["next"])

    def test_the_gap_is_named_first_with_the_values_it_accepts(self):
        self.counted_with_nothing_to_derive_from()
        out = self.run_it()
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["next_step"]["kind"], "gap")
        self.assertEqual(out["next_step"]["tool"], "state_facts")
        fact = out["next_step"]["fact"]
        self.assertTrue(out["gaps"], "the frontier's gaps reach the model now")
        self.assertEqual(out["gaps"][0]["fact"], fact)
        self.assertIn("NOTHING in this harness measures it", out["next"])
        self.assertIn("state_facts", out["next"])
        self.assertIn("run_diagnosis again", out["next"])
        accepts = (out["gaps"][0].get("accepts") or {}).get("one_of") or []
        for value in accepts[:2]:
            self.assertIn(str(value), out["next"], "the accepted values are on the sentence")

    def test_the_sentence_carries_a_whole_call_with_a_value_in_it(self):
        """MEASURED 2026-09-13, the second live run: told to record the fact,
        the model called state_facts with `{"facts": {}}`. It had learnt the
        door and not what to put through it, because the sentence showed an
        ellipsis. An ellipsis is not an example."""
        self.counted_with_nothing_to_derive_from()
        out = self.run_it()
        nxt = out["next"]
        fact = out["next_step"]["fact"]
        accepts = (out["gaps"][0].get("accepts") or {}).get("one_of") or []
        self.assertIn('{"facts": {"' + fact + '"', nxt, "a whole call, not a fragment")
        if accepts:
            self.assertIn(f'"{accepts[0]}"', nxt, "with a real value standing in for the answer")
        self.assertNotIn("...", nxt)
        self.assertIn("An empty facts object records nothing", nxt)

    def test_an_empty_facts_object_is_refused_with_the_move_on_it(self):
        from app.tools import evidence as _evidence

        out = REGISTRY.call(
            "state_facts", {"facts": {}}, actor=_evidence.MODEL, thread_id=self.thread
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "nothing_supplied")
        self.assertTrue(out["the_walk_is_blocked_on"], "the refusal names what would move the walk")
        blocked = out["the_walk_is_blocked_on"][0]
        self.assertIn(blocked, out["for_this_tool"])
        self.assertIn('{"facts"', out["for_this_tool"])

    def test_a_quoted_number_comes_back_as_the_call_to_send(self):
        """MEASURED 2026-09-13, third live run: the model sent the right facts
        with the numbers quoted, because a model writing JSON quotes things.
        The refusal was true and taught nothing, and it was not retried."""
        from app.tools import evidence as _evidence

        out = REGISTRY.call(
            "state_facts", {"facts": {"eval_size_n": "40"}},
            actor=_evidence.MODEL, thread_id=self.thread,
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["send_this_instead"], {"facts": {"eval_size_n": 40}})
        self.assertIn("arrived as strings", out["for_this_tool"])

    def test_the_word_unknown_is_pointed_at_the_door_for_not_knowing(self):
        """And it sent `{"target_score": "unknown"}` - it was trying to say it
        did not know. The engine has a door for that and never showed it."""
        from app.tools import evidence as _evidence

        out = REGISTRY.call(
            "state_facts", {"facts": {"target_score": "unknown"}},
            actor=_evidence.MODEL, thread_id=self.thread,
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["you_do_not_know"], ["target_score"])
        self.assertIn("LEFT OUT", out["if_you_do_not_know"])
        self.assertIn("assumption on the next verdict", out["if_you_do_not_know"])

    def test_a_real_fact_still_records(self):
        """The regression this suite would have caught: a local import named
        `diagnosis` inside the refusal branch made the module-level one a
        local for the whole function, and EVERY non-empty call raised
        UnboundLocalError."""
        from app.tools import evidence as _evidence

        out = REGISTRY.call(
            "state_facts", {"facts": {"task_family": "generation"}},
            actor=_evidence.MODEL, thread_id=self.thread,
        )
        self.assertTrue(out["ok"], out)

    def test_a_remedy_already_spent_is_not_offered_again(self):
        """The other half of the loop: assess_the_data ran, the fact stayed
        unanswered, and the harness asked for assess_the_data again."""
        from app.tools import evidence as _evidence

        # The gap decided, so the next move is the answerable question.
        gap = self.run_it()["next_step"]["fact"]
        events.append(
            "tool.result",
            {"name": "assess_the_data", "ok": True, "result": {"ok": True}},
            thread_id=self.thread,
        )
        self.assertIn("assess_the_data", _evidence.tools_already_run(self.thread))
        out = self.run_it({gap: "generation"} if gap == "task_family" else {gap: "text"})
        step = out.get("next_step") or {}
        if step.get("kind") == "question" and step.get("tool") == "assess_the_data":
            self.assertTrue(step["already_run"])
            self.assertIn("has already run in this conversation", out["next"])
            self.assertIn("state_facts", out["next"])


class ThePlanIsNamedTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        _connect()

    def test_a_plan_turn_on_a_thread_with_a_plan_ends_with_plan_ready(self):
        thread = int(events.create_thread("t", mode="plan")["id"])
        events.set_thread_plan(thread, PLAN)
        events.add_message(thread, "user", "is the plan ready?")
        rows = _run(thread, _Fake(["The plan is saved and complete."]))
        ready = [r["payload"] for r in rows if r["kind"] == "thread.plan_ready"]
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0]["phases"], 4)
        self.assertEqual(ready[0]["headings"][1], "Phase 1 - Data")
        self.assertEqual(ready[0]["steps"], 3)
        self.assertEqual(ready[0]["steps_open"], 2)
        self.assertFalse(ready[0]["written_this_turn"])

    def test_a_plan_written_this_turn_says_so_and_carries_its_headings(self):
        thread = int(events.create_thread("t", mode="plan")["id"])
        events.add_message(thread, "user", "plan it")
        rows = _run(thread, _Fake([("write_plan", {"plan": PLAN}), "Plan saved."]))
        written = [r["payload"] for r in rows if r["kind"] == "thread.plan_written"]
        self.assertEqual(written[0]["headings"][0], "Root of the ask")
        self.assertEqual(written[0]["steps_open"], 2)
        ready = [r["payload"] for r in rows if r["kind"] == "thread.plan_ready"]
        self.assertTrue(ready and ready[0]["written_this_turn"])

    def test_an_unchanged_plan_is_named_once_not_once_per_turn(self):
        thread = int(events.create_thread("t", mode="plan")["id"])
        events.set_thread_plan(thread, PLAN)
        events.add_message(thread, "user", "is the plan ready?")
        _run(thread, _Fake(["Yes."]))
        events.add_message(thread, "user", "and now?")
        rows = _run(thread, _Fake(["Still yes."]))
        self.assertEqual(sum(1 for r in rows if r["kind"] == "thread.plan_ready"), 1)
        events.add_message(thread, "user", "add a phase")
        rows = _run(thread, _Fake([("write_plan", {"plan": PLAN + "\n## Phase 3 - Ship\n- [ ] Ship it\n"}), "Added."]))
        self.assertEqual(sum(1 for r in rows if r["kind"] == "thread.plan_ready"), 2)

    def test_no_plan_no_row(self):
        thread = int(events.create_thread("t", mode="plan")["id"])
        events.add_message(thread, "user", "hello")
        rows = _run(thread, _Fake(["Hello."]))
        self.assertEqual([r for r in rows if r["kind"] == "thread.plan_ready"], [])

    def test_not_in_build_mode(self):
        thread = int(events.create_thread("t", mode="build")["id"])
        events.set_thread_plan(thread, PLAN)
        events.add_message(thread, "user", "go")
        rows = _run(thread, _Fake(["Working."]))
        self.assertEqual([r for r in rows if r["kind"] == "thread.plan_ready"], [])


class AProsePlanLandsInBuildModeTooTest(unittest.TestCase):
    """P0's live row, 2026-09-18: under Full (which forces build mode) the
    model wrote two well-structured `## Phase` reports and never called
    write_plan; the prose rescue fired only in plan mode, and the Run button
    answered "every step of this plan is ticked or parked" to a thread that
    had never had a plan. A prose plan on a plan-less build thread IS the plan,
    and a run on a plan-less thread says there is no plan."""

    PROSE = chr(10).join([
        "Here is the plan.", "",
        "## Phase 1 - Data",
        "- [ ] Carve the eval set with carve_eval_set from data/train.jsonl",
        "",
        "## Phase 2 - Baseline",
        "- [ ] Measure the baseline with measure_baseline on data/eval.jsonl",
    ])

    def setUp(self) -> None:
        support.sandbox(self)
        _connect()

    def test_a_build_thread_with_no_plan_adopts_the_prose_plan(self):
        thread = int(events.create_thread("t", mode="build")["id"])
        events.add_message(thread, "user", "plan it and go")
        rows = _run(thread, _Fake([self.PROSE]))
        written = [r["payload"] for r in rows if r["kind"] == "thread.plan_written"]
        self.assertEqual(len(written), 1, "the prose plan was not adopted in build mode")
        self.assertEqual(written[0]["source"], "prose")
        self.assertIn("- [ ] Carve the eval set", events.get_thread(thread)["plan"])

    def test_a_build_thread_with_a_plan_keeps_it(self):
        thread = int(events.create_thread("t", mode="build")["id"])
        events.set_thread_plan(thread, PLAN)
        events.add_message(thread, "user", "status?")
        rows = _run(thread, _Fake([self.PROSE]))
        self.assertEqual([r for r in rows if r["kind"] == "thread.plan_written"], [])
        self.assertEqual(events.get_thread(thread)["plan"], PLAN)

    def test_a_run_on_a_plan_less_thread_says_there_is_no_plan(self):
        from app import longrun

        thread = int(events.create_thread("t", mode="build")["id"])
        out = longrun.start(thread, background=False)
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "no_plan")
        self.assertIn("no plan yet", out["detail"])


if __name__ == "__main__":
    unittest.main()
