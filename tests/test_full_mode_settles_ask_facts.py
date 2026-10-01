"""AU1/AU5/AU6: permission full is zero-ask — settle, intent, grind, invariants."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import conductor, diagnosis, events, full_defaults, goal_invite  # noqa: E402
from app.providers import Delta, ToolCall  # noqa: E402
from app.providers import store as provider_store  # noqa: E402
from app.tools import evals, evidence, goal_todo, measure  # noqa: E402
from app.tools.evidence import Instrument  # noqa: E402
from app.tools.registry import REGISTRY  # noqa: E402


class FullModeSettlesAskFactsTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        self.spec = diagnosis.default_spec()

    def test_model_state_facts_open_gates_under_full(self) -> None:
        tid = events.create_thread("full bypass")["id"]
        events.set_thread_permission(tid, "full")
        instrument = Instrument(
            tool="state_facts",
            actor=evidence.MODEL,
            thread_id=tid,
        )
        out = measure.state_facts(
            {"target_score": 0.25},
            instrument=instrument,
            ledger=self.spec,
        )
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("origin"), evidence.STATED)
        rows = out.get("recorded") or []
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["can_open_a_gate"])

    def test_model_state_facts_do_not_open_gates_under_ask(self) -> None:
        tid = events.create_thread("ask honesty")["id"]
        events.set_thread_permission(tid, "ask")
        instrument = Instrument(
            tool="state_facts",
            actor=evidence.MODEL,
            thread_id=tid,
        )
        out = measure.state_facts(
            {"target_score": 0.25},
            instrument=instrument,
            ledger=self.spec,
        )
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("origin"), evidence.ASSERTED)
        rows = out.get("recorded") or []
        self.assertFalse(rows[0]["can_open_a_gate"])

    def test_set_goal_without_invite_under_full(self) -> None:
        tid = events.create_thread("full goal")["id"]
        events.set_thread_permission(tid, "full")
        goal_invite.clear(tid)
        out = goal_todo.set_goal("Ship the router", thread_id=tid)
        self.assertTrue(out.get("ok"), out)
        self.assertEqual(out.get("goal"), "Ship the router")

    def test_set_goal_refuses_without_invite_under_ask(self) -> None:
        tid = events.create_thread("ask goal")["id"]
        events.set_thread_permission(tid, "ask")
        goal_invite.clear(tid)
        out = goal_todo.set_goal("Should refuse", thread_id=tid)
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "invite_required")

    def test_standing_brief_under_full_settles_not_asks(self) -> None:
        payload = {
            "facts_used": {"eval_size_n": 40},
            "verdict": "BLOCKED",
            "outcome": "BLOCKED__MISSING_FACTS",
            "say": "privacy is still open",
            "gate_ledger": {},
            "unsubstantiated": [],
            "next_step": {
                "fact": "privacy",
                "tool": "state_facts",
                "kind": "question",
            },
        }
        brief = conductor.standing_brief(payload, permission="full")
        self.assertIn("under Full, call state_facts NOW", brief)
        self.assertIn("Do not ask the person", brief)
        self.assertIn("Full mode: settle ask-facts", brief)
        self.assertNotIn("ask the person for", brief.lower())

    def test_full_footer_says_what_the_person_said(self) -> None:
        """LAW SUBSTITUTED 2026-09-17. This footer used to name three tools
        for one outcome and then say "or stop"; the model on thread 75 quoted
        that sentence back four times and stopped. Max: "nothing is blocked,
        I am approving all the work ahead of time... use your full computer
        abilities." The footer now says that, and names the shell."""
        footer = conductor._full_settle_footer()
        self.assertIn("Full mode: settle ask-facts", footer)
        self.assertIn("approved every step in advance", footer)
        self.assertIn("fix the argument and call again", footer)
        self.assertIn("run_project_command", footer)
        self.assertIn("set_baseline_target", footer)
        self.assertNotIn("generate_rows", footer)
        self.assertNotIn("or stop", footer)
        self.assertNotIn("BLOCKED__FIX_LABELS_OR_TASK", footer)

    def test_permission_note_names_goal_tools(self) -> None:
        note = conductor._permission_note("full")
        self.assertIn("state_facts", note)
        self.assertIn("set_goal", note)
        self.assertIn("do not narrate", note.lower())
        self.assertEqual(conductor._permission_note("ask"), "")


class FullGrindInvariantTest(unittest.TestCase):
    """AU6 — full⇔build, state_facts copy, grind nudge, intent under full."""

    def setUp(self) -> None:
        support.sandbox(self)

    def test_setting_full_forces_mode_build(self) -> None:
        tid = events.create_thread("was plan", mode="plan")["id"]
        row = events.set_thread_permission(tid, "full")
        self.assertEqual(row["permission"], "full")
        self.assertEqual(row["mode"], "build")

    def test_setting_plan_forces_permission_ask(self) -> None:
        tid = events.create_thread("was full")["id"]
        events.set_thread_permission(tid, "full")
        row = events.set_thread_mode(tid, "plan")
        self.assertEqual(row["mode"], "plan")
        self.assertEqual(row["permission"], "ask")

    def test_state_facts_description_names_full_stated(self) -> None:
        card = REGISTRY.get("state_facts")
        self.assertIsNotNone(card)
        desc = card.description
        self.assertIn("full", desc.lower())
        self.assertIn("STATED", desc)
        self.assertIn("do not invent measurements", desc.lower())

    def test_empty_reply_nudge_full_does_not_push_write_plan(self) -> None:
        """CHANGED CONTRACT, 2026-09-22: the retry is one line naming one move
        (`conductor._silence_retry`), not a paragraph. Planning still names
        write_plan; Full never does, and names the walk's tool without asking."""
        walk = {"next_step": {"tool": "state_facts"}}
        offered = frozenset({"state_facts", "write_plan"})
        planning = conductor._silence_retry(walk, offered, full=False, planning=True)
        full = conductor._silence_retry(walk, offered, full=True, planning=False)
        self.assertIn("write_plan", planning)
        self.assertNotIn("write_plan", full)
        self.assertIn("state_facts", full)
        self.assertIn("without asking the person", full)

    def test_intent_nudge_full_refuses_approval_wait(self) -> None:
        self.assertIn("Do not ask the person", conductor.INTENT_NUDGE_FULL)
        self.assertIn("approval", conductor.INTENT_NUDGE_FULL.lower())
        self.assertNotIn("approval", conductor.INTENT_NUDGE.lower())

    def test_full_grind_tool_reads_next_step(self) -> None:
        self.assertEqual(
            conductor._full_grind_tool(
                {"next_step": {"tool": "measure_baseline"}}
            ),
            "measure_baseline",
        )
        # ANY REGISTERED TOOL, because the sentence the nudge says is true of
        # all of them: the brief named a next tool and under Full the model is
        # to call it. It used to be a five-name list, and on Max's thread the
        # walk named `assess_the_data` - not one of the five - so the nudge
        # stayed silent and the model narrated for four turns until the run
        # killed itself. The registry is the check.
        self.assertEqual(
            conductor._full_grind_tool({"next_step": {"tool": "write_plan"}}),
            "write_plan",
        )
        self.assertEqual(
            conductor._full_grind_tool({"next_step": {"tool": "assess_the_data"}}),
            "assess_the_data",
        )
        self.assertIsNone(
            conductor._full_grind_tool({"next_step": {"tool": "no_such_tool_ships"}}),
            "a name no tool answers to is not a move",
        )
        self.assertIsNone(conductor._full_grind_tool({}))


class _Fake:
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
            yield Delta(
                kind="tool_call",
                tool_calls=(ToolCall(f"c{len(self.seen)}", name, args),),
            )
        else:
            yield Delta(kind="text", text=str(step))


def _connect() -> None:
    row = provider_store.create(
        "Fake", "http://127.0.0.1:11434", "fake-model", "ollama"
    )
    provider_store.record_capabilities(
        row["id"],
        type(
            "Caps",
            (),
            {
                "tool_calling": True,
                "detail": "test",
                "ctx_len": None,
                "provenance": {},
            },
        )(),
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


_STANDING = {
    "facts_used": {"eval_size_n": 40},
    "verdict": "BLOCKED",
    "outcome": "BLOCKED__MISSING_FACTS",
    "say": "privacy is still open",
    "gate_ledger": {},
    "unsubstantiated": [],
    "next_step": {
        "fact": "privacy",
        "tool": "state_facts",
        "kind": "question",
    },
}


class FullGrindTurnTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        _connect()
        self._orig_standing = conductor._standing_diagnosis
        conductor._standing_diagnosis = lambda _tid: dict(_STANDING)

    def tearDown(self) -> None:
        conductor._standing_diagnosis = self._orig_standing

    def test_turn_started_packs_contain_intent_under_full(self) -> None:
        tid = int(events.create_thread("full intent")["id"])
        events.set_thread_permission(tid, "full")
        events.add_message(tid, "user", "settle the open facts")
        rows = _run(tid, _Fake(["Calling state_facts now."]))
        started = [r["payload"] for r in rows if r["kind"] == "turn.started"]
        self.assertTrue(started)
        packs = (started[0].get("blocks") or {}).get("packs") or []
        self.assertIn("intent", packs)

    def test_narrating_only_gets_full_grind_nudge(self) -> None:
        tid = int(events.create_thread("full narrate")["id"])
        events.set_thread_permission(tid, "full")
        events.add_message(tid, "user", "keep going")
        fake = _Fake(
            [
                "The brief shows BLOCKED__MISSING_FACTS. Privacy is still open. "
                "I would settle that next.",
                ("state_facts", {"facts": {"privacy": "public"}}),
                "Recorded.",
            ]
        )
        rows = _run(tid, fake)
        notices = [
            r["payload"].get("reason")
            for r in rows
            if r["kind"] == "conductor.notice"
        ]
        self.assertIn("full_grind_nudge", notices)
        nudges = [
            m
            for turn in fake.seen
            for m in turn
            if m.get("content") == conductor.FULL_GRIND_NUDGE
        ]
        self.assertTrue(nudges, "FULL_GRIND_NUDGE must enter the conversation")
        self.assertNotIn(
            conductor.FULL_GRIND_NUDGE,
            [m["content"] for m in events.messages_for(tid)],
            "scaffolding never lands in the thread's messages",
        )


# ---------------------------------------------------------------------------
# P3. Full answers ask-facts itself.


def _stamp(thread_id: int, tool: str, fact: str, value: Any) -> None:
    """Stamp through an instrument, the way the tool itself does.

    `evidence.record` refuses a MEASURED row written straight to the ledger and
    is right to - the badge is the instrument's to give. `provides` is read off
    the tool's OWN registration because wall 9 checks it against the fact's
    declared `measured_by`, so a fixture that hardcoded a capability would trip
    that wall instead of testing what it came to test.
    """
    declared = getattr(REGISTRY, "_tools", {}).get(tool)
    instrument = Instrument(
        tool=tool,
        actor=evidence.USER,
        thread_id=thread_id,
        measures=frozenset({fact}),
        provides=frozenset(getattr(declared, "provides", ()) or ()),
    )
    instrument.measured(fact, value, how=f"{tool} read it off the eval set")


def _measured_thread(
    baseline: float = 0.30, trivial: float = 0.05, rows: int = 40
) -> int:
    """A Full thread that has measured its eval set and its baseline, and nothing else."""
    thread_id = int(events.create_thread("full defaults")["id"])
    events.set_thread_permission(thread_id, "full")
    _stamp(thread_id, "measure_eval_set", "eval_size_n", rows)
    _stamp(thread_id, "measure_baseline", "baseline_measured", True)
    _stamp(thread_id, "measure_baseline", "baseline_score", baseline)
    _stamp(thread_id, "measure_baseline", "trivial_baseline_score", trivial)
    return thread_id


def _row_for(thread_id: int, fact: str) -> dict[str, Any] | None:
    for row in evidence.ledger_view(thread_id):
        if row["fact"] == fact:
            return row
    return None


class FullSettlesTargetScoreByRuleTest(unittest.TestCase):
    """P3, measured on thread 78, 2026-09-18.

    Under permission `full` - `app/autonomy.py`'s zero-ask bypass - the walk
    stopped at `S0_NO_DEFINITION_OF_SUCCESS` and the model ended its turn asking
    Max for `target_score` and for what the task was. Max, the same day:
    *"based on the data, certain target scores are usually this amount... set it
    at this, I think this is correct."*

    LAW SUBSTITUTED 2026-09-18. `app/tools/next_moves.py` pinned the refusal to
    derive this fact: *"the user is the only witness to their own bar"*. That is
    not appended to or argued with - it still holds everywhere `target_score`
    is a READING, which is what move 3 offers. It is SCOPED: under `full` the
    person has already said the harness decides, so `app/full_defaults.py`
    settles it by a rule that states its own arithmetic, and the fact's declared
    `source: ask` is untouched.
    """

    def setUp(self) -> None:
        support.sandbox(self)

    def test_the_default_is_the_rule_and_the_numbers_are_recomputable(self) -> None:
        """0.05 trivial, 0.30 baseline, 40 rows -> 0.40, and a reader can check it.

        Two floors, and this thread is the one where the baseline floor wins:
        `0.30 + 0.10 = 0.40` beats `0.05 + 0.219 = 0.269`. The resolution is not
        a number written here - it is what `evals.resolution_for` says 40 rows
        can tell two runs apart by, so a change to that computation fails this
        rather than sailing past a constant somebody typed.
        """
        thread_id = _measured_thread()
        payload = conductor._standing_diagnosis(thread_id)
        settled = payload.get("full_settled") or []
        self.assertEqual([row["fact"] for row in settled], ["target_score"])
        self.assertEqual(settled[0]["value"], 0.4)

        resolution = evals.resolution_for(12, 40)[
            "resolves_a_difference_of_at_least_points"
        ]
        self.assertIn(f"resolution {resolution / 100.0:.3f} on 40 rows", settled[0]["how"])
        self.assertIn("trivial baseline plus the resolution", settled[0]["how"])

    def test_the_resolution_floor_wins_when_the_trivial_answer_is_strong(self) -> None:
        """0.60 trivial, 0.30 baseline, 40 rows -> 0.60 + 0.219 = 0.819.

        The other branch of `max`, and the one the ten-point rule alone would get
        wrong: a bar of 0.40 on a set whose majority-class answer already scores
        0.60 is a bar the trivial answer clears.
        """
        thread_id = _measured_thread(baseline=0.30, trivial=0.60)
        payload = conductor._standing_diagnosis(thread_id)
        settled = payload["full_settled"][0]
        self.assertEqual(settled["fact"], "target_score")
        self.assertAlmostEqual(settled["value"], 0.8191, places=3)

    def test_the_cap_holds_at_ninety_five(self) -> None:
        """0.90 and 0.90 on 40 rows would ask for 1.119. A bar nothing can clear
        is not a bar, and a rule that can write one can block a thread for ever
        on the harness's own arithmetic."""
        thread_id = _measured_thread(baseline=0.90, trivial=0.90)
        payload = conductor._standing_diagnosis(thread_id)
        self.assertEqual(payload["full_settled"][0]["value"], 0.95)

    #: THE TWO WAYS A WALK SAYS "still waiting on target_score". Which of them
    #: you get depends on whether the person can show graded rows, and from
    #: 2026-09-21 a MEASURED eval set answers that by itself - so a thread with
    #: forty counted rows reaches the ACTION rather than the BLOCK. Both are
    #: the same fact about the walk, and pinning one name made this test about
    #: the wording instead of the property.
    STILL_ON_TARGET_SCORE = (
        "BLOCKED__DEFINE_SUCCESS_FIRST",
        "ACTION__SET_A_TARGET_SCORE",
    )

    def test_the_walk_is_no_longer_blocked_on_defining_success(self) -> None:
        """The two outcomes the ask cost Max a turn on, gone from the same walk."""
        thread_id = _measured_thread()
        before = conductor._walk(thread_id)
        self.assertIn(before["outcome"], self.STILL_ON_TARGET_SCORE)

        after = conductor._standing_diagnosis(thread_id)
        self.assertNotIn(
            after["outcome"],
            ("BLOCKED__DEFINE_SUCCESS_FIRST", "ACTION__SET_A_TARGET_SCORE"),
        )
        self.assertNotEqual(
            (after.get("next_step") or {}).get("fact"), "target_score"
        )

    def test_under_ask_nothing_is_defaulted(self) -> None:
        """The same ledger, one word different, and the harness decides nothing."""
        thread_id = _measured_thread()
        events.set_thread_permission(thread_id, "ask")
        payload = conductor._standing_diagnosis(thread_id)
        self.assertIsNone(payload.get("full_settled"))
        self.assertIn(payload["outcome"], self.STILL_ON_TARGET_SCORE)
        self.assertIsNone((payload.get("facts_used") or {}).get("target_score"))
        self.assertIsNone(_row_for(thread_id, "target_score"))

    def test_no_baseline_means_no_default_and_the_walk_goes_measuring(self) -> None:
        """A bar set before anything was scored is a number with nothing under it.

        The rule needs `baseline_score` and `trivial_baseline_score` MEASURED, so
        a thread that has only counted its rows is left exactly where the walk
        already puts it: go and measure.
        """
        thread_id = int(events.create_thread("no baseline")["id"])
        events.set_thread_permission(thread_id, "full")
        _stamp(thread_id, "measure_eval_set", "eval_size_n", 40)
        payload = conductor._standing_diagnosis(thread_id)
        self.assertIsNone(payload.get("full_settled"))
        self.assertIsNone(_row_for(thread_id, "target_score"))

    def test_the_word_stays_defaulted_and_never_measured(self) -> None:
        """Nothing read this number off anything. The card must say so."""
        thread_id = _measured_thread()
        payload = conductor._standing_diagnosis(thread_id)
        self.assertEqual(payload["fact_origins"]["target_score"], diagnosis.DEFAULTED)
        self.assertEqual(
            payload["facts_used"]["target_score"]["origin"], diagnosis.DEFAULTED
        )
        row = _row_for(thread_id, "target_score")
        self.assertIsNotNone(row)
        self.assertEqual(row["origin"], diagnosis.DEFAULTED)
        self.assertEqual(row["actor"], evidence.HARNESS)
        self.assertNotEqual(row["origin"], diagnosis.MEASURED)

    def test_a_person_overrules_the_default_by_saying_so(self) -> None:
        """STATED outranks DEFAULTED, so there is nothing to undo."""
        thread_id = _measured_thread()
        conductor._standing_diagnosis(thread_id)
        out = measure.state_facts(
            {"target_score": 0.8},
            instrument=Instrument(
                tool="state_facts", actor=evidence.USER, thread_id=thread_id
            ),
            ledger=diagnosis.default_spec(),
        )
        self.assertTrue(out.get("ok"), out)

        payload = conductor._standing_diagnosis(thread_id)
        self.assertEqual(payload["facts_used"]["target_score"]["value"], 0.8)
        self.assertEqual(payload["fact_origins"]["target_score"], diagnosis.STATED)

    def test_it_settles_once_and_not_once_a_turn(self) -> None:
        """A second walk over a settled thread writes nothing and says nothing new."""
        thread_id = _measured_thread()
        conductor._standing_diagnosis(thread_id)
        again = conductor._standing_diagnosis(thread_id)
        self.assertIsNone(again.get("full_settled"))
        rows = [r for r in evidence.ledger_view(thread_id) if r["fact"] == "target_score"]
        self.assertEqual(len(rows), 1)

    def test_the_brief_says_what_was_settled_and_by_what_rule(self) -> None:
        """One line, above the standing instruction, naming the rule and the number."""
        thread_id = _measured_thread()
        payload = conductor._standing_diagnosis(thread_id)
        brief = conductor.standing_brief(payload, permission="full")
        self.assertIn("Full settled target_score at 0.4 by rule:", brief)
        self.assertIn("trivial baseline plus the resolution", brief)
        self.assertIn("Full mode: settle ask-facts", brief)

    def test_the_footer_still_stands_alone(self) -> None:
        """No payload, no settled lines, and the instruction is unchanged."""
        self.assertEqual(
            conductor._full_settle_footer(), conductor._full_settle_footer(None)
        )
        self.assertNotIn("Full settled", conductor._full_settle_footer())


class FullSettlesFromTheEvalFileTest(unittest.TestCase):
    """`task_family` and `modality`, derived from the file the thread profiled.

    Max, 2026-09-18, on the same turn: the model asked him what the task was
    while holding a profiled eval set that answers it.
    """

    def setUp(self) -> None:
        support.sandbox(self)
        self.folder = Path(tempfile.mkdtemp())

    def _eval_file(self, rows: list[dict[str, Any]]) -> Path:
        path = self.folder / "eval.jsonl"
        body = "\n".join(json.dumps(row) for row in rows)
        path.write_bytes(body.encode("utf-8"))
        return path

    def _worked(self, thread_id: int, path: Path) -> None:
        """The thread's own record that this is the file it is working."""
        events.append(
            "tool.call",
            {
                "id": "c1",
                "name": "measure_baseline",
                "arguments": {
                    "eval_path": str(path),
                    "input_field": "input",
                    "expected_field": "expected",
                },
            },
            thread_id=thread_id,
        )
        events.append(
            "tool.result",
            {"id": "c1", "name": "measure_baseline", "ok": True,
             "result": {"eval_path": str(path)}},
            thread_id=thread_id,
        )

    def test_a_short_label_set_is_classification_and_the_modality_is_text(self) -> None:
        thread_id = _measured_thread()
        path = self._eval_file(
            [
                {"input": f"row {i}", "expected": "positive" if i % 2 else "negative"}
                for i in range(40)
            ]
        )
        self._worked(thread_id, path)
        payload = conductor._standing_diagnosis(thread_id)
        settled = {row["fact"]: row["value"] for row in payload["full_settled"]}
        self.assertEqual(settled["task_family"], "classification")
        self.assertEqual(settled["modality"], "text")
        self.assertEqual(
            payload["fact_origins"]["task_family"], diagnosis.DEFAULTED
        )

    def test_json_records_are_extraction_and_never_an_undeclared_word(self) -> None:
        """`structured_generation` is not a value this ledger declares.

        The brief for this pass named it as one of the two answers for JSON
        records. `task_family`'s enum does not hold it, `_declared` refuses any
        value the enum does not, and a harness that wrote it would be inventing
        a category the engine cannot route on.
        """
        thread_id = _measured_thread()
        path = self._eval_file(
            [
                {"input": f"row {i}", "expected": json.dumps({"name": f"n{i}", "id": i})}
                for i in range(40)
            ]
        )
        self._worked(thread_id, path)
        payload = conductor._standing_diagnosis(thread_id)
        settled = {row["fact"]: row["value"] for row in payload["full_settled"]}
        self.assertEqual(settled["task_family"], "extraction")
        self.assertNotIn(
            "structured_generation",
            list(diagnosis.default_spec().facts["task_family"]["enum"]),
        )

    def test_free_text_is_generation(self) -> None:
        thread_id = _measured_thread()
        path = self._eval_file(
            [
                {"input": f"row {i}", "expected": f"a whole sentence about item {i}"}
                for i in range(40)
            ]
        )
        self._worked(thread_id, path)
        payload = conductor._standing_diagnosis(thread_id)
        settled = {row["fact"]: row["value"] for row in payload["full_settled"]}
        self.assertEqual(settled["task_family"], "generation")

    def test_no_profiled_file_settles_neither(self) -> None:
        """The thread is blocked on `task_family` and there is no file to read.

        Nothing is invented for it - it is left to the Full grind nudge, which
        is what `conductor._full_grind_tool` is for.
        """
        thread_id = _measured_thread()
        payload = conductor._standing_diagnosis(thread_id)
        self.assertEqual(
            [row["fact"] for row in payload["full_settled"]], ["target_score"]
        )
        self.assertIn("task_family", full_defaults.blocked_facts(payload))
        self.assertIsNone(_row_for(thread_id, "task_family"))


class ADefaultedRowIsTheHarnessOwnWordTest(unittest.TestCase):
    """The walls around the word, so that "Full settled it" cannot become a lever."""

    def setUp(self) -> None:
        support.sandbox(self)
        self.spec = diagnosis.default_spec()

    def test_no_settleable_fact_is_read_by_any_gate_row(self) -> None:
        """Derived from the spec, not listed here.

        `diagnosis._challenged_facts` skips DEFAULTED, so a defaulted fact is
        never masked back to unsupplied at a gate. That is right for a fact the
        gates do not read and would be a hole for one they did, so the property
        is checked against the gate rows the file actually declares - and a
        ledger that put one of these into a `requires` string next year fails
        here rather than opening a gate on the harness's own arithmetic.
        """
        gate_facts: set[str] = set()
        for names in self.spec.gate_row_facts.values():
            gate_facts |= set(names)
        self.assertTrue(gate_facts, "the spec declares gate rows at all")
        self.assertEqual(gate_facts & set(full_defaults.SETTLEABLE), set())

    def test_a_model_may_not_write_a_defaulted_row(self) -> None:
        thread_id = int(events.create_thread("minting")["id"])
        with self.assertRaises(evidence.MeasurementError) as caught:
            evidence.record(
                fact="target_score",
                value=0.99,
                origin=diagnosis.DEFAULTED,
                actor=evidence.MODEL,
                how="I decided",
                thread_id=thread_id,
                ledger=self.spec,
            )
        self.assertIn("only the harness", str(caught.exception))
        self.assertIsNone(_row_for(thread_id, "target_score"))

    def test_a_caller_still_may_not_claim_the_engines_origin(self) -> None:
        """`Settled` is the engine's carrier and a bare `Fact` is still refused.

        A tool call is JSON and JSON carries no Python class, so no argument a
        model sends can arrive as a `Settled`. This is the half of that sentence
        that a test can hold.
        """
        with self.assertRaises(diagnosis.FactError):
            diagnosis.diagnose(
                {"target_score": diagnosis.Fact(0.99, diagnosis.DEFAULTED)}, self.spec
            )
        result = diagnosis.diagnose(
            {"target_score": diagnosis.settled(0.99, "a rule said so")}, self.spec
        )
        self.assertEqual(result.fact_origins["target_score"], diagnosis.DEFAULTED)

    def test_a_settled_fact_carries_the_origin_and_nothing_else(self) -> None:
        with self.assertRaises(diagnosis.FactError):
            diagnosis.Settled(0.4, diagnosis.STATED, "not a default")

    def test_privacy_defaults_only_when_every_provider_is_local(self) -> None:
        """The rule, exercised directly, because no walk in this suite blocks on it.

        `privacy` is read by stage 7's conditions rather than by an ask node of
        its own, so a fixture that reached it would be a fixture about stage 7.
        The rule is three lines and the interesting half is what it REFUSES: one
        hosted provider and it does not weigh them up, because "mostly local" is
        not a privacy posture and guessing which way somebody leans is the
        invention this module may not make.
        """
        payload = {"facts_used": {}, "fact_origins": {}}
        spec = diagnosis.default_spec()
        self.assertIsNone(full_defaults._privacy(1, payload, spec))

        provider_store.create("Local", "http://127.0.0.1:11434", "m", "ollama")
        settled = full_defaults._privacy(1, payload, spec)
        self.assertIsNotNone(settled)
        self.assertEqual(settled[0], "on_prem_only")
        self.assertIn("local", settled[1])
        self.assertIn(
            "on_prem_only", list(spec.facts["privacy"]["enum"])
        )

        provider_store.create(
            "Hosted", "https://api.openai.com/v1", "m", "openai-compatible"
        )
        self.assertIsNone(full_defaults._privacy(1, payload, spec))

    def test_stated_outranks_defaulted_in_the_table(self) -> None:
        self.assertGreater(
            evidence.ORIGIN_RANK[diagnosis.STATED],
            evidence.ORIGIN_RANK[diagnosis.DEFAULTED],
        )
        self.assertEqual(evidence.ORIGIN_RANK[diagnosis.DEFAULTED], 0)


if __name__ == "__main__":
    unittest.main()
