"""A project remembers, the person is known, and a number cannot sneak in.

Hermes' curated memory (MEMORY.md / USER.md), rebuilt per project - see
`app/memory.py`. Each rule Hermes keeps has a case; the one rule this
product adds - a number needs its origin - has both directions.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path


class _Sandboxed(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._old = os.environ.get("ML_HARNESS_DB")
        os.environ["ML_HARNESS_DB"] = str(Path(self._tmp.name) / "memory.db")
        from app import db
        self._old_path = db.DB_PATH
        db.DB_PATH = Path(os.environ["ML_HARNESS_DB"])
        db.init_db()
        self.project = int(db.create_project("p", None)["id"])

    def tearDown(self) -> None:
        from app import db
        db.DB_PATH = self._old_path
        if self._old is None:
            os.environ.pop("ML_HARNESS_DB", None)
        else:
            os.environ["ML_HARNESS_DB"] = self._old


class TheStoreTest(_Sandboxed):
    def test_add_replace_remove_by_a_few_words(self):
        from app import memory
        self.assertTrue(memory.add("project", "The router model is granite4-hermes; ornith was ruled out.", self.project)["ok"])
        self.assertTrue(memory.add("project", "Support tickets live in the exports folder.", self.project)["ok"])
        replaced = memory.replace("project", "router model", "The router model is granite4-hermes, chosen for tool calling.", self.project)
        self.assertTrue(replaced["ok"], replaced)
        self.assertIn("ornith", replaced["was"])
        removed = memory.remove("project", "exports folder", self.project)
        self.assertTrue(removed["ok"], removed)
        self.assertEqual([r["content"] for r in memory.entries("project", self.project)],
                         ["The router model is granite4-hermes, chosen for tool calling."])

    def test_an_ambiguous_match_is_refused_with_the_candidates(self):
        from app import memory
        memory.add("project", "The eval set is carved from the tickets.", self.project)
        memory.add("project", "The eval set must not overlap the train split.", self.project)
        out = memory.remove("project", "eval set", self.project)
        self.assertEqual(out["error"], "ambiguous")
        self.assertEqual(len(out["candidates"]), 2)
        self.assertEqual(memory.remove("project", "zebra", self.project)["error"], "no_match")

    def test_a_duplicate_is_refused(self):
        from app import memory
        memory.add("user", "Max prefers short answers.", None)
        self.assertEqual(memory.add("user", "max prefers short answers.", None)["error"], "duplicate")

    def test_the_limit_is_hermes_and_the_refusal_says_what_to_do(self):
        from app import memory
        self.assertEqual(memory.LIMITS, {"project": 2200, "user": 1375})
        long = "x" * 1300
        self.assertTrue(memory.add("user", long, None)["ok"])
        out = memory.add("user", "y" * 100, None)
        self.assertEqual(out["error"], "over_limit")
        self.assertIn("1,375", out["detail"])
        self.assertIn("Remove or replace", out["detail"])

    def test_the_project_and_the_person_are_separate_and_projects_are_separate(self):
        from app import db, memory
        other = int(db.create_project("other", None)["id"])
        memory.add("project", "Ours.", self.project)
        memory.add("project", "Theirs.", other)
        memory.add("user", "Max is in Toronto.", None)
        self.assertEqual([r["content"] for r in memory.entries("project", self.project)], ["Ours."])
        self.assertEqual([r["content"] for r in memory.entries("project", other)], ["Theirs."])
        self.assertEqual([r["content"] for r in memory.entries("user")], ["Max is in Toronto."])


class ANumberNeedsItsOriginTest(_Sandboxed):
    def test_a_bare_number_is_refused_and_says_why(self):
        from app import memory
        out = memory.add("project", "The card has 8 GB of VRAM.", self.project)
        self.assertEqual(out["error"], "number_without_origin")
        self.assertIn("measured", out["detail"])

    def test_a_number_with_its_origin_is_kept(self):
        from app import memory
        self.assertTrue(memory.add("project", "VRAM 8 GB, measured by inspect_hardware on thread 12.", self.project)["ok"])
        self.assertTrue(memory.add("project", "Target score 0.9, stated by Max.", self.project)["ok"])

    def test_dates_versions_and_model_names_are_not_readings(self):
        from app import memory
        for entry in (
            "Decided on 2026-09-11 to use granite4-hermes.",
            "The engine is v0.1.0 on this machine.",
            "The RTX 2060 SUPER is the card here.",
            "A 7b model is the ceiling we discussed.",
        ):
            with self.subTest(entry=entry):
                self.assertTrue(memory.add("project", entry, self.project)["ok"], entry)

    def test_the_pane_save_applies_the_same_rule_per_entry(self):
        from app import memory
        out = memory.set_text("project", "Fine entry.\n§\nThe card has 8 GB.", self.project)
        self.assertEqual(out["error"], "number_without_origin")
        self.assertEqual(memory.entries("project", self.project), [])
        ok = memory.set_text("project", "Fine entry.\n§\nVRAM 8 GB, measured.", self.project)
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["count"], 2)


class WhatThePersonAskedToKeepIsKeptTest(_Sandboxed):
    """MEASURED 2026-09-11, six live turns: asked to keep a decision in mind
    for the project, the model called `remember` in two. The harness keeps
    the person's own words when the model did not - the `goal` rule."""

    def test_the_shapes_a_person_uses(self):
        from app import memory
        for text in (
            "Keep that in mind for every conversation in this project.",
            "Remember: the eval set is the March export.",
            "please note this down - we ship on Fridays",
            "I don't want to repeat it every time",
        ):
            with self.subTest(text=text):
                self.assertTrue(memory.asks_to_keep(text))
        for text in ("which model should route the tickets?", "carve the eval set", "I remembered to run it"):
            with self.subTest(text=text):
                self.assertFalse(memory.asks_to_keep(text))

    def test_the_words_are_kept_verbatim_with_their_origin(self):
        from app import memory
        out = memory.keep_what_was_asked(self.project, 12, "For this project the router is granite4 on the 8 GB card. Keep it in mind.")
        self.assertTrue(out["ok"], out)
        entry = memory.entries("project", self.project)[0]["content"]
        self.assertTrue(entry.startswith("Stated by the person (thread 12): For this project"))
        self.assertIn("8 GB", entry, "the person's own figure is theirs to state")

    def test_a_very_long_ask_is_clipped_not_refused(self):
        from app import memory
        out = memory.keep_what_was_asked(self.project, 1, "keep this in mind " + "x" * 900)
        self.assertTrue(out["ok"], out)
        self.assertLessEqual(len(memory.entries("project", self.project)[0]["content"]), memory.KEPT_CHARS + 40)


class WhatATurnTaughtIsKeptTest(_Sandboxed):
    """Hermes' `sync_turn`, through the same connection: after an answered
    turn the harness asks what the exchange taught and keeps it, with the
    number rule at the door and nothing added twice. Max, 2026-09-12: "it's
    not condensing, saving anything."."""

    ASKED = "For this project use the March export as the eval set, and stop asking me about the label column - it is `intent`."
    SPOKEN = "Understood. " + "The eval set is the March export and the label column is intent. " * 6

    def test_facts_the_extractor_names_are_kept_under_their_target(self):
        from app import memory
        reply = "\n".join(
            [
                json.dumps({"target": "project", "fact": "The eval set is the March export."}),
                json.dumps({"target": "project", "fact": "The label column is `intent`."}),
                json.dumps({"target": "user", "fact": "Max does not want to be asked about the label column again."}),
            ]
        )
        seen = {}
        out = memory.extract_after_turn(self.project, 7, self.ASKED, self.SPOKEN, lambda s, u: seen.update(system=s, user=u) or reply)
        self.assertTrue(out["asked"])
        self.assertEqual(len(out["added"]), 3)
        self.assertIn("MEMORY NOW", seen["user"])
        # MEASURED 2026-09-12: "NONE is the usual answer" in the instruction
        # made the owner's model answer NONE to an exchange that named the
        # router, the data path and the label column. The instruction now
        # says what qualifies and reserves NONE for when nothing does.
        self.assertIn("Reply NONE only when", seen["system"])
        self.assertNotIn("usual answer", seen["system"])
        project = [e["content"] for e in memory.entries("project", self.project)]
        self.assertEqual(len(project), 2)
        self.assertTrue(all(p.endswith("(from thread 7)") for p in project))
        self.assertEqual(memory.entries("user")[0]["content"], "Max does not want to be asked about the label column again.")

    def test_nothing_is_kept_twice_and_none_is_an_answer(self):
        from app import memory
        memory.add("project", "The eval set is the March export. (from thread 3)", self.project)
        reply = json.dumps({"target": "project", "fact": "the eval set is the March export."})
        out = memory.extract_after_turn(self.project, 7, self.ASKED, self.SPOKEN, lambda s, u: reply)
        self.assertEqual(out["added"], [])
        self.assertEqual(out["skipped"], 1)
        self.assertEqual(len(memory.entries("project", self.project)), 1)
        none = memory.extract_after_turn(self.project, 7, self.ASKED, self.SPOKEN, lambda s, u: "NONE")
        self.assertEqual(none["added"], [])

    def test_a_figure_without_its_origin_is_refused_at_the_door(self):
        from app import memory
        reply = "\n".join(
            [
                json.dumps({"target": "project", "fact": "The baseline is 0.62."}),
                json.dumps({"target": "project", "fact": "The baseline is 0.62, measured by measure_baseline."}),
            ]
        )
        out = memory.extract_after_turn(self.project, 7, self.ASKED, self.SPOKEN, lambda s, u: reply)
        self.assertEqual(out["refused"], 1)
        self.assertEqual(len(out["added"]), 1)

    def test_a_figure_the_person_wrote_is_kept_as_stated_by_them(self):
        """"We'll hold out 40 rows, not 30" - the extractor dropped the origin
        word, but every figure is in the person's own message, and the harness
        can read that. The entry says so; a figure the person did NOT write
        stays refused."""
        from app import memory
        asked = "I decided we'll hold out 40 rows, not 30, because the classes are uneven."
        reply = "\n".join(
            [
                json.dumps({"target": "project", "fact": "The eval holdout is 40 rows, not 30, because the classes are uneven."}),
                json.dumps({"target": "project", "fact": "The eval set has 400 training rows."}),
            ]
        )
        out = memory.extract_after_turn(self.project, 9, asked, self.SPOKEN, lambda s, u: reply)
        self.assertEqual(len(out["added"]), 1)
        self.assertEqual(out["refused"], 1)
        entry = memory.entries("project", self.project)[0]["content"]
        self.assertTrue(entry.endswith("(stated by the person, thread 9)"), entry)

    def test_a_short_reply_or_a_dead_connection_is_an_empty_pass(self):
        from app import memory
        calls = []
        out = memory.extract_after_turn(self.project, 7, "hi", "hello", lambda s, u: calls.append(1) or "NONE")
        self.assertFalse(out["asked"])
        self.assertEqual(calls, [])

        def dead(s, u):
            raise RuntimeError("gone")

        out = memory.extract_after_turn(self.project, 7, self.ASKED, self.SPOKEN, dead)
        self.assertFalse(out["asked"])
        self.assertEqual(out["added"], [])

    def test_the_sandbox_keeps_extraction_out_of_every_other_test(self):
        """`support.sandbox` - what every conductor test isolates with - turns
        the pass off and restores it, so a scripted provider is never handed
        the extractor's question in place of the turn's."""
        import support
        from app import memory

        self.assertTrue(memory.EXTRACTION_ENABLED, "the product default is on")
        support.sandbox(self)
        self.assertFalse(memory.EXTRACTION_ENABLED)


class ThePromptBlockTest(_Sandboxed):
    def test_both_blocks_render_with_hermes_headers_and_nothing_when_empty(self):
        from app import memory
        self.assertEqual(memory.render_block(self.project), "")
        memory.add("project", "We ruled out renting a GPU.", self.project)
        memory.add("user", "Max prefers short answers.", None)
        block = memory.render_block(self.project)
        self.assertIn("MEMORY (this project's notes)", block)
        self.assertIn("- We ruled out renting a GPU.", block)
        self.assertIn("USER PROFILE (who the person is)", block)
        self.assertIn("- Max prefers short answers.", block)

    def test_the_note_is_on_the_prompt_and_says_how_to_quote_a_number(self):
        from app import conductor, events, memory
        thread = events.create_thread("t", project_id=self.project)
        memory.add("project", "VRAM 8 GB, measured by inspect_hardware on an earlier thread.", self.project)
        note = conductor._memory_note(thread)
        self.assertIn("MEMORY (this project's notes)", note)
        self.assertIn("remember", note)
        self.assertIn("from memory", note)
        self.assertEqual(conductor._memory_note({"id": 0, "project_id": None}), conductor._memory_note({"id": 0, "project_id": None}))

    def test_the_note_carries_the_guidance_even_when_empty(self):
        """Hermes injects MEMORY_GUIDANCE in every prompt; the model has to
        know the door exists before anything is behind it."""
        from app import conductor, events
        thread = events.create_thread("t", project_id=self.project)
        note = conductor._memory_note(thread)
        self.assertIn("remember", note)
        self.assertIn("stale in a week", note)


class TheToolTest(_Sandboxed):
    def test_the_tool_writes_the_calling_threads_project(self):
        from app import events, memory
        from app.tools import REGISTRY, evidence
        thread = events.create_thread("t", project_id=self.project)["id"]
        out = REGISTRY.call(
            "remember", {"action": "add", "target": "project", "content": "We ruled out renting a GPU."},
            actor=evidence.MODEL, thread_id=thread,
        )
        self.assertTrue(out["ok"], out)
        self.assertEqual([r["content"] for r in memory.entries("project", self.project)], ["We ruled out renting a GPU."])
        written = [r for r in events.since(f"thread:{thread}", limit=100) if r["kind"] == "memory.written"]
        self.assertEqual(len(written), 1)

    def test_the_user_profile_needs_no_project(self):
        from app import memory
        from app.tools import REGISTRY, evidence
        out = REGISTRY.call("remember", {"action": "add", "target": "user", "content": "Max prefers short answers."}, actor=evidence.MODEL, thread_id=None)
        self.assertTrue(out["ok"], out)
        self.assertEqual(len(memory.entries("user")), 1)

    def test_it_is_offered_in_plan_mode(self):
        from app import modes
        self.assertIn("remember", modes.PLAN_TOOLS)


if __name__ == "__main__":
    unittest.main()
