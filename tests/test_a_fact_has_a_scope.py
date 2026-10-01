"""Every fact says what it is a fact ABOUT, and only four are about the machine.

`source:` says where a fact should come from. `origin` says where one value
actually came from. Neither answers "a fact about WHAT", and that missing third
question is the whole of wall 5: a number can be genuinely measured, genuinely
stamped by the code that ran the instrument, and attached to nothing that says
what it is a measurement of.

This file is about the DECLARATION - that the ledger carries one for every fact,
that the words mean what the vocabulary says, and that the four the machine owns
are the four the machine actually has. What the declaration DOES is
`tests/test_a_thread_scoped_fact_needs_a_thread.py`.

THE COUNT IS ASSERTED AS A SHAPE, NOT AS A NUMBER. "68 facts carry a scope" would
be a copy of the ledger in a test, and this repository has already been bitten by
that: the fact count was 42 in three documents on the day it was 68. So the
assertion is `every fact in the loaded ledger`, derived from the loaded ledger,
and a fact added next year is covered on the day it is added.
"""

from __future__ import annotations

import unittest

from app import diagnosis
from app.migrations import v006_machine_scope_is_declared_not_assumed as migration
from app.tools import evidence


class EveryFactDeclaresItsScopeTest(unittest.TestCase):
    def setUp(self):
        self.spec = diagnosis.default_spec()

    def test_every_declared_fact_carries_a_scope(self):
        """No fact may be silent about this, the way none may be silent about
        `source:`. A missing scope reads as `thread` at runtime, which is safe -
        and safe by accident is not the same as declared, and a reviewer looking
        at the line has to be able to see the answer."""
        silent = sorted(
            name for name, decl in self.spec.facts.items() if "scope" not in decl
        )
        self.assertEqual(
            silent,
            [],
            "these facts do not say what they are facts about. Add `scope: "
            "machine` or `scope: thread` to each, next to its `source:`, and read "
            "`fact_scopes` in docs/diagnosis_engine.yaml before choosing.",
        )

    def test_every_declared_scope_is_a_word_the_vocabulary_has(self):
        wrong = sorted(
            (name, decl.get("scope"))
            for name, decl in self.spec.facts.items()
            if decl.get("scope") not in evidence.SCOPES
        )
        self.assertEqual(wrong, [], f"the vocabulary is {list(evidence.SCOPES)}")

    def test_the_vocabulary_in_the_file_and_the_module_are_the_same_two_words(self):
        """The same check `_load_origin_policy` runs on the origin names, for the
        same reason: two lists of words that must agree, kept in two files."""
        self.assertEqual(
            sorted(evidence.scope_policy()["vocabulary"]), sorted(evidence.SCOPES)
        )

    def test_the_machine_owns_exactly_the_facts_the_machine_has(self):
        """FOUR, and they are the four `inspect_hardware` reads off this box.

        This is the assertion that keeps the exception small. Machine scope means
        "visible in every conversation on this computer", and the argument for it
        is that the box does not change between conversations. That argument is
        true of the accelerator and the RAM; it is not true of a budget, a
        deadline, a privacy constraint or an eval set, and every one of those is a
        plausible-sounding candidate somebody could talk themselves into.
        """
        self.assertEqual(
            evidence.facts_at_scope(evidence.MACHINE),
            ("accelerator", "disk_free_gb", "ram_gb", "vram_gb"),
        )

    def test_the_machine_facts_are_what_the_hardware_tool_declares_it_measures(self):
        """Derived from the other end: the tool that reads the machine."""
        from app.tools.registry import REGISTRY

        hardware = REGISTRY.get("inspect_hardware")
        self.assertEqual(
            sorted(hardware.measures), sorted(evidence.facts_at_scope(evidence.MACHINE))
        )

    def test_eval_size_n_is_a_fact_about_one_conversation(self):
        """The sharpest example in the product, and the one that was live.

        `rows_for`'s docstring named this fact, at this number, as the thing that
        must not leak sideways - and three rows in the owner's real database were
        exactly that, written through a door that never asked."""
        self.assertEqual(evidence.scope_of("eval_size_n"), evidence.THREAD)
        self.assertFalse(evidence.is_machine_scoped("eval_size_n"))

    def test_the_baseline_and_the_goal_belong_to_one_conversation_too(self):
        for name in ("baseline_score", "baseline_measured", "goal_text", "target_score"):
            with self.subTest(fact=name):
                self.assertEqual(evidence.scope_of(name), evidence.THREAD)

    def test_a_fact_the_ledger_never_heard_of_is_read_as_a_conversations_own(self):
        """Fail closed, the same way an unattributed value reads as ASSERTED.

        `answer_given` is one of three names a real local model invented in one
        session. None of them is in the ledger, and a name nobody declared is not
        evidence that the machine owns it."""
        self.assertEqual(evidence.scope_of("answer_given"), evidence.THREAD)
        self.assertEqual(evidence.DEFAULT_SCOPE, evidence.THREAD)

    def test_a_fact_declaring_a_scope_nobody_recognises_is_read_the_same_way(self):
        """A typo widens nothing. The check is membership, not truthiness."""
        saved = dict(self.spec.facts["vram_gb"])
        self.spec.facts["vram_gb"] = {**saved, "scope": "machien"}
        try:
            self.assertEqual(evidence.scope_of("vram_gb"), evidence.THREAD)
        finally:
            self.spec.facts["vram_gb"] = saved

    def test_the_shipped_migration_and_the_live_ledger_agree_today(self):
        """The one place the frozen list and the living one are compared.

        `v006` writes the four machine facts out as SQL literals on purpose: a
        migration is a statement about a database at one moment and must mean the
        same thing forever, so it cannot read a ledger that will change. The cost
        of freezing is drift, and this is where drift is caught - not by making
        the migration dynamic, but by failing here on the day the two diverge, so
        somebody decides what a NEW migration should do about it.
        """
        frozen = {
            name.strip().strip("'")
            for name in migration._MACHINE_FACTS.split(",")
        }
        self.assertEqual(frozen, set(evidence.facts_at_scope(evidence.MACHINE)))


class TheScopePolicyIsReadableTest(unittest.TestCase):
    """The block exists, says what the words mean, and names its own gaps."""

    def test_the_policy_block_is_in_the_ledger(self):
        policy = evidence.scope_policy()
        for key in (
            "vocabulary",
            "scope_of_an_undeclared_fact",
            "rule",
            "the_http_door",
            "known_gaps",
        ):
            with self.subTest(key=key):
                self.assertIn(key, policy)

    def test_the_undeclared_reading_in_the_file_is_the_one_the_module_uses(self):
        self.assertEqual(
            evidence.scope_policy()["scope_of_an_undeclared_fact"],
            evidence.DEFAULT_SCOPE,
        )

    def test_the_gates_a_fact_opens_are_derived_from_the_engines_own_rows(self):
        """POSITIVE CONTROL for the refusal message, which names them.

        A `gates_that_read` that always returned nothing would make the refusal
        quietly weaker and no test would notice, because the message would still
        be a long true sentence."""
        self.assertIn("G0_EVAL_SET", evidence.gates_that_read("eval_size_n"))
        self.assertEqual(evidence.gates_that_read("goal_text"), ())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
