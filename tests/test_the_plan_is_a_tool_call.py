"""A plan is delivered by a tool call, and a turn remembers its earlier turns -
two halves of one fault. The third half, the silence retry, is tested where
every other exit path is: `test_a_turn_always_speaks.py`.

## The fault, in the owner's words

2026-09-11, thread 64, plan mode, autonomous on: *"it's not making a plan. It's
not writing any markdowns... every time I run it, it's - again, let me
understand the journey. Let me run the diagnosis. Where's my consistent memory
system? It's rescanning every time."*

Two turns in a row: eight lookups, then `empty_reply`. The same five lookups in
six turns out of six. No plan, ever.

## The mechanisms

**No move.** Plan mode offered lookups only, and a lookup answers a question
about the world - none of them produces the thing the mode is for. A model
that acts through tools chose the next lookup until the budget ran out, then
had nothing to say. `app/conductor.py` had already measured that shape:
withdraw the engine and the same model goes silent thirteen turns in twenty.
`write_plan` is the move; `read_plan` is how it revises.

**No memory.** The conversation is rebuilt each turn from `messages_for`, which
is user and assistant messages only; every earlier tool call and result sits in
`events` and reaches the model in none of it. `_already_read_note` lists what
earlier turns read, so this one does not read it again.

**No scope.** The plus listed every file ever attached in every chat, because
the `contexts` row had nothing that said whose it was.

And one more, found while writing `write_plan`: a tool that declares
`thread_id` in its schema was asking the model for a number the prompt never
carries. The registry fills it from the call site now - only when declared,
so nothing acquires a thread it did not ask for.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "tests") not in sys.path:
    sys.path.insert(0, str(REPO / "tests"))

import support  # noqa: E402
from app import conductor, events  # noqa: E402
from app.tools import context as context_tools  # noqa: E402
from app.tools import evidence  # noqa: E402
from app.tools.registry import REGISTRY  # noqa: E402

A_PLAN = "\n".join(
    [
        "## Phase 1 - Data",
        "Carve an eval set from the rows already attached.",
        "",
        "## Phase 2 - Baseline",
        "Measure the connected model on it before anything is trained.",
    ]
)


class ThePlanIsAToolCallTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        self.thread = events.create_thread("planning")["id"]

    def test_a_sentence_is_refused_as_not_a_plan(self):
        """Forty characters is a sentence. Saving one as the plan would hand
        the build loop a vague instruction to repeat for hours."""
        result = REGISTRY.call(
            "write_plan", {"plan": "train a model"}, actor=evidence.MODEL,
            thread_id=self.thread,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "not_a_plan")
        self.assertIsNone(events.get_thread(self.thread)["plan"])

    def test_a_phased_plan_is_saved_to_the_thread(self):
        result = REGISTRY.call(
            "write_plan", {"plan": A_PLAN}, actor=evidence.MODEL, thread_id=self.thread
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["phases"], 2)
        self.assertEqual(events.get_thread(self.thread)["plan"], A_PLAN)
        kinds = [row["kind"] for row in events.since(f"thread:{self.thread}")]
        self.assertIn("thread.plan_written", kinds)

    def test_the_thread_is_filled_from_the_call_site(self):
        """THE MODEL NEVER SEES ITS THREAD NUMBER. The prompt does not carry it,
        so a schema that requires it requires something unknowable. The call
        sends no `thread_id` in its arguments and still lands on the right
        thread: the registry filled it from the call site."""
        REGISTRY.call("write_plan", {"plan": A_PLAN}, actor=evidence.MODEL, thread_id=self.thread)
        self.assertEqual(events.get_thread(self.thread)["plan"], A_PLAN)

    def test_a_thread_the_model_made_up_is_replaced_by_the_call_site(self):
        """MEASURED 2026-09-11, three live plan turns: the model called
        `write_plan` every time and sent `thread_id: 1`, `0`, `1` - numbers it
        invented because the schema asked. Two plans landed on thread 1 and the
        third was refused as `no_such_thread`. A value the model cannot know is
        not a value it can supply: the call site's replaces it."""
        made_up = 1 if self.thread != 1 else 2
        result = REGISTRY.call(
            "write_plan", {"plan": A_PLAN, "thread_id": made_up},
            actor=evidence.MODEL, thread_id=self.thread,
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(events.get_thread(self.thread)["plan"], A_PLAN)
        other = events.get_thread(made_up)
        self.assertNotEqual((other or {}).get("plan"), A_PLAN, "the plan landed on the invented thread")

    def test_only_a_tool_that_declares_the_thread_is_handed_one(self):
        """`list_runs` declares no `thread_id`; sent one anyway, it is set
        aside as an unknown argument rather than quietly accepted."""
        result = REGISTRY.call(
            "list_runs", {"thread_id": self.thread}, actor=evidence.MODEL, thread_id=self.thread
        )
        aside = list(result.get("ignored_arguments", [])) + list(result.get("refused_arguments", []))
        self.assertIn("thread_id", aside)

    def test_read_plan_reads_back_what_write_plan_saved(self):
        REGISTRY.call("write_plan", {"plan": A_PLAN}, actor=evidence.MODEL, thread_id=self.thread)
        result = REGISTRY.call("read_plan", {}, actor=evidence.MODEL, thread_id=self.thread)
        self.assertTrue(result["ok"])
        self.assertTrue(result["has_plan"])
        self.assertEqual(result["phases"], 2)
        self.assertEqual(result["plan"], A_PLAN)

    def test_a_plan_with_no_phases_is_saved_but_told_so(self):
        """Saved, because refusing a real document is worse than a nudge; and
        told, because a plan the loop cannot walk phase by phase is a plan it
        will repeat whole."""
        flat = "Do these things: carve rows, measure the baseline, train, evaluate."
        result = REGISTRY.call("write_plan", {"plan": flat}, actor=evidence.MODEL, thread_id=self.thread)
        self.assertTrue(result["ok"])
        self.assertEqual(result["phases"], 0)
        self.assertIn("no `## Phase`", result["next"])

    def test_writing_a_plan_does_not_switch_the_mode(self):
        """A mode is set by a person, never by a model - `app/modes.py`."""
        before = events.get_thread(self.thread)["mode"]
        REGISTRY.call("write_plan", {"plan": A_PLAN}, actor=evidence.MODEL, thread_id=self.thread)
        self.assertEqual(events.get_thread(self.thread)["mode"], before)


class ATurnRemembersItsEarlierTurnsTest(unittest.TestCase):
    """A direct `REGISTRY.call` writes no events - the conductor does, during
    a turn - so these write the two events the conductor writes, in its
    shape: `tool.call` carries name and arguments, `tool.result` carries
    name, ok and result. `test_a_turn_always_speaks` runs a real turn and
    reads the note back, which is what keeps this shape honest.
    """

    def setUp(self):
        self.root = support.sandbox(self)
        self.thread = events.create_thread("remembering")["id"]

    def ran(self, name, arguments=None, result=None, ok=True):
        events.append("tool.call", {"name": name, "arguments": arguments or {}}, thread_id=self.thread)
        events.append(
            "tool.result",
            {"name": name, "ok": ok, "result": result if result is not None else {"ok": ok}},
            thread_id=self.thread,
        )

    def test_a_fresh_thread_has_nothing_to_remember(self):
        self.assertEqual(conductor._already_read_note(self.thread), "")

    def test_an_earlier_call_is_listed_with_what_it_answered(self):
        self.ran("list_runs", result={"ok": True, "runs": []})
        note = conductor._already_read_note(self.thread)
        self.assertIn("Already read in this conversation", note)
        self.assertIn("list_runs()", note)
        self.assertIn("answered", note)

    def test_a_refusal_is_remembered_as_a_refusal(self):
        """So the next turn does not try the same bad path again."""
        self.ran("read_context_file", {"path": "nowhere/at/all.txt"}, result={"ok": False, "error": "not_found"}, ok=False)
        note = conductor._already_read_note(self.thread)
        self.assertIn("read_context_file", note)
        self.assertIn("refused", note)

    def test_the_same_call_twice_is_one_line(self):
        for _ in range(3):
            self.ran("list_runs", result={"ok": True, "runs": []})
        note = conductor._already_read_note(self.thread)
        self.assertEqual(note.count("- list_runs()"), 1)

    def test_it_is_facts_and_not_a_ban(self):
        """The model may call any of them again; what it is told is that the
        answer already exists. The word `unless` carries that."""
        self.ran("list_runs", result={"ok": True, "runs": []})
        note = conductor._already_read_note(self.thread)
        self.assertIn("unless something has changed", note)

    def test_it_is_bounded(self):
        for n in range(conductor.ALREADY_READ_LIMIT + 6):
            self.ran("list_runs", {"limit": n + 1}, result={"ok": True, "runs": []})
        note = conductor._already_read_note(self.thread)
        self.assertEqual(note.count("- list_runs("), conductor.ALREADY_READ_LIMIT)


class AnAttachmentBelongsToAConversationTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        self.here = events.create_thread("here")["id"]
        self.there = events.create_thread("there")["id"]
        (self.root / "mine.txt").write_text("mine", encoding="utf-8")
        (self.root / "theirs.txt").write_text("theirs", encoding="utf-8")

    def test_the_plus_lists_this_conversation_and_not_the_other(self):
        """THE OWNER'S BUG: every file ever attached, in every chat."""
        REGISTRY.call(
            "attach_context", {"path": str(self.root / "mine.txt")},
            actor=evidence.USER, thread_id=self.here,
        )
        REGISTRY.call(
            "attach_context", {"path": str(self.root / "theirs.txt")},
            actor=evidence.USER, thread_id=self.there,
        )
        here = REGISTRY.call("list_context", {}, actor=evidence.USER, thread_id=self.here)
        paths = [row["path"] for row in here["contexts"]]
        self.assertEqual(len(paths), 1, paths)
        self.assertTrue(paths[0].endswith("mine.txt"))

    def test_an_unscoped_listing_still_sees_everything(self):
        """A tool call with no thread got everything before; it still does."""
        REGISTRY.call(
            "attach_context", {"path": str(self.root / "mine.txt")},
            actor=evidence.USER, thread_id=self.here,
        )
        REGISTRY.call(
            "attach_context", {"path": str(self.root / "theirs.txt")},
            actor=evidence.USER, thread_id=self.there,
        )
        self.assertEqual(len(context_tools.list_contexts()), 2)

    def test_a_row_from_before_the_column_is_hidden_from_a_scoped_listing(self):
        """The rows that predate the column have no conversation to be given
        retroactively. Guessing one would be worse than showing none."""
        context_tools.record_context(str(self.root / "theirs.txt"), "file", "", "")
        self.assertEqual(context_tools.list_contexts(self.here), [])
        self.assertEqual(len(context_tools.list_contexts()), 1)

    def test_an_older_table_grows_the_column_on_first_ask(self):
        """The table is not migration-managed - `ensure_contexts_table` makes it
        on first ask - so the column heals the same way. A first cut was a
        migration, and it broke every fresh database by altering a table that
        did not exist yet."""
        from app import db
        with db.session() as connection:
            connection.execute("DROP TABLE IF EXISTS contexts")
            connection.execute(
                "CREATE TABLE contexts (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "path TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, role TEXT, note TEXT)"
            )
        context_tools.ensure_contexts_table()
        with db.session() as connection:
            have = {row[1] for row in connection.execute("PRAGMA table_info(contexts)")}
        self.assertIn("thread_id", have)


class PlanModeSpendsFewerRoundsTest(unittest.TestCase):
    def test_the_plan_budget_is_smaller_than_the_build_budget(self):
        """Four is enough to read the machine, the rows and the runs; the
        fifth was `what_is_missing` again. The budget is what makes the model
        stop looking and start writing."""
        self.assertLess(conductor.PLAN_TOOL_ROUNDS, conductor.MAX_TOOL_ROUNDS)
        self.assertGreaterEqual(conductor.PLAN_TOOL_ROUNDS, 3)


if __name__ == "__main__":
    unittest.main()
