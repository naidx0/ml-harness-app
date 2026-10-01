"""A default the person cannot see is a number the product chose for them.

Every question card in this harness offers "I don't know" as a legal answer, and
what taking it costs is the ledger's own default for that fact. So the card has
to be able to say what that default IS, before the person decides - "eval_size_n
stays 0" is an informed decline and a bare em dash is a decline made blind.

`app/tools/evidence.py::declaration()` is the one function that answers "what
does the ledger say this fact is, in the shape a caller needs to send one", and
it returned `accepts`, `settled_by` and the admissible origins and nothing about
the default. `frontend/src/components/QuestionCard.tsx` says so in its own
header - *"the default NOT ON THE WIRE, and the card says the em dash rather than
a number"* - and carries a `fallback: {value, known}` slot that was false for
every fact on the wire because no route filled it.

## TWO KEYS, AND THE SECOND ONE IS WHY THIS FILE EXISTS

The obvious patch is `out["default"] = decl.get("default")`. It is wrong twice,
and both ways matter more than the missing field did:

  * **It states a default the engine will not apply.** `need_type` is a `multi:`
    with no declared default, and `diagnosis.unsupplied_value` resolves it to
    `[]`, not to null. `decl.get` would have the card announce null while the
    engine took the empty list. One function in this repository answers "what
    happens when nobody supplies this"; a second opinion about it is a drift
    machine, and it drifts on the very first fact.

  * **It cannot tell a chosen zero from an absent one.** `eval_size_n` declares
    `default: 0` because somebody decided that nobody having built an eval set
    reads as zero examples. `target_score` declares nothing, and its null is the
    absence of a decision. Both send a `default` key. Only one of them is a
    number anybody stands behind, and this whole product exists because a
    hardcoded 8.0 and a RAM field reading free disk space made the app
    confidently wrong. So `declares_a_default` travels beside the value and says
    which kind it is.

The rule the suite pins: A MISSING DEFAULT MUST NEVER ARRIVE AS 0.
"""

from __future__ import annotations

import unittest

from app import asking, diagnosis
from app.tools import evidence


class TheDeclarationCarriesTheDefault(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = diagnosis.default_spec()

    # -- the field is there, and it is the engine's own answer --------------
    def test_every_declared_fact_says_what_it_takes_when_nobody_answers(self):
        """The field exists on every fact, not only on the ones with a default."""
        for fact in self.spec.facts:
            with self.subTest(fact=fact):
                row = evidence.declaration(fact)
                self.assertIn(
                    "default",
                    row,
                    "the card has no number to offer beside 'I don't know'",
                )
                self.assertIn("declares_a_default", row)

    def test_the_default_is_the_value_the_engine_would_actually_apply(self):
        """`unsupplied_value`, not `decl.get('default')`. See the header.

        Checked against the function the walk itself calls, over every fact,
        so a fact declared in a shape this file has never seen is covered on
        the day it is added rather than the day somebody remembers this test.
        """
        for fact, decl in self.spec.facts.items():
            with self.subTest(fact=fact):
                self.assertEqual(
                    evidence.declaration(fact)["default"],
                    diagnosis.unsupplied_value(decl),
                    "the declaration states a default the engine would not apply",
                )

    def test_a_multi_with_no_declared_default_takes_the_empty_list_not_null(self):
        """The exact case `decl.get('default')` gets wrong. Derived, then pinned.

        `need_type` is the multi in the ledger today. The loop finds them rather
        than trusting that; the assertion is that at least one exists, because a
        version of this test that iterated an empty set would pass against the
        wrong fix.
        """
        multis = [f for f, d in self.spec.facts.items() if "multi" in d]
        self.assertTrue(multis, "no `multi:` fact in the ledger; this test is vacuous")
        for fact in multis:
            with self.subTest(fact=fact):
                decl = self.spec.facts[fact]
                if "default" in decl:
                    continue
                row = evidence.declaration(fact)
                self.assertEqual(row["default"], [])
                self.assertFalse(row["declares_a_default"])

    # -- a chosen number and an absent one are not the same thing -----------
    def test_a_fact_with_no_declared_default_never_arrives_as_a_number(self):
        """Rule 5 of this repository, asked of this one field.

        An absent default resolves to null - or to the empty list for a multi,
        which is a shape and not a quantity. It may never resolve to 0, 0.0,
        False or "": each of those is a value somebody could act on, and nobody
        chose it.
        """
        for fact, decl in self.spec.facts.items():
            if "default" in decl:
                continue
            with self.subTest(fact=fact):
                row = evidence.declaration(fact)
                self.assertFalse(row["declares_a_default"])
                self.assertIn(
                    row["default"],
                    (None, []),
                    f"{fact} declares no default and the wire invented "
                    f"{row['default']!r} for it",
                )

    def test_a_declared_default_is_marked_as_one_and_kept_verbatim(self):
        for fact, decl in self.spec.facts.items():
            if "default" not in decl:
                continue
            with self.subTest(fact=fact):
                row = evidence.declaration(fact)
                self.assertTrue(row["declares_a_default"])
                self.assertEqual(row["default"], decl["default"])

    def test_the_two_facts_the_brief_named_read_the_way_the_brief_says(self):
        """The concrete pair, so the general properties above have a witness."""
        counted = evidence.declaration("eval_size_n")
        self.assertEqual(counted["default"], 0)
        self.assertTrue(counted["declares_a_default"])

        target = evidence.declaration("target_score")
        self.assertIsNone(target["default"])
        self.assertFalse(
            target["declares_a_default"],
            "target_score declares no default; saying it stays 0 would be the "
            "product putting a score on 'good enough' on the user's behalf",
        )

    # -- the refusal and the card must not hold two opinions ----------------
    def test_the_tool_refusal_and_the_question_card_agree_on_every_fact(self):
        """`asking._declared` wraps this function and used to overwrite the field.

        Two answers to "what is the default" is how the tool refusal and the
        card come to disagree in front of the same user about the same fact.
        There is one answer now and this is the assertion that keeps it one.
        """
        for fact in self.spec.facts:
            with self.subTest(fact=fact):
                card = asking._declared(fact)
                row = evidence.declaration(fact)
                self.assertEqual(card["default"], row["default"])
                self.assertEqual(card["declares_a_default"], row["declares_a_default"])

    def test_an_undeclared_fact_is_still_refused_without_a_default(self):
        """A name the ledger never heard of gets no default field to misread."""
        row = evidence.declaration("hardware_is_sufficient_for_training")
        self.assertFalse(row["declared"])
        self.assertNotIn("default", row)


class TheCardCanNameWhatDecliningCosts(unittest.TestCase):
    """The consequence, at the consumer, rather than at the field."""

    def test_a_real_card_holds_the_default_before_the_person_chooses(self):
        card = asking.question_for("eval_size_n")
        self.assertEqual(card.declared["default"], 0)
        self.assertTrue(card.declared["declares_a_default"])
        # And "I don't know" takes exactly that, recorded as DEFAULTED.
        self.assertEqual(card.dont_know.takes, 0)
        self.assertEqual(card.dont_know.recorded_as, diagnosis.DEFAULTED)

    def test_a_card_for_a_fact_with_no_default_offers_no_number(self):
        card = asking.question_for("target_score")
        self.assertIsNone(card.declared["default"])
        self.assertFalse(card.declared["declares_a_default"])
        self.assertIsNone(card.dont_know.takes)


if __name__ == "__main__":
    unittest.main()
