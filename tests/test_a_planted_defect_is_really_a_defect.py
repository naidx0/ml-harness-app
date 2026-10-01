"""The truth path of the judge instrument, checked before a call is spent on it.

Every judge number this repository has produced is measured against these
labels. A generator that mislabels a pair does not produce one wrong row — it
produces a wrong RATE, silently, for every run that uses it. So the edits are
pure functions and they are tested against the owner's real answers here, in an
interpreter with no model and no GPU.

**The claim a planted pair makes, and the only one.** The rewrite is FALSE about
the shop — not merely worse. A degradation the generator produces is a real
answer made worse and still faithful; a planted defect says something the real
answer contradicts. The judge is supposed to drop it, and that is what the label
means.

**Why the negation list is ordered longest-first.** `no longer` must be matched
before `no`, or "we no longer take cheques" becomes "we yes longer take
cheques": fluent nonsense rather than a plausible lie, and a judge dropping it
would be right for the wrong reason — which would inflate recall with a case no
real generator produces.
"""

from __future__ import annotations

import json
import unittest

import support

plant = support.import_file(
    "plant_the_defects", support.REPO_ROOT / "scripts" / "plant_the_defects.py"
)

#: The owner's real answers. `runs/` is gitignored (.gitignore line 28), so this
#: file exists on the machine that produced it and on no other checkout - and
#: read at import time, its absence was an ImportError that took the whole
#: module down and turned the shared gate red for anybody who had not run that
#: job. A precondition a checkout cannot satisfy is a skip, not an error: the
#: cases below that need these answers say so individually, and the ones that
#: do not need them keep running everywhere.
_ANSWERS = support.REPO_ROOT / "runs" / "honest-path" / "train.jsonl"
REAL = (
    [
        json.loads(line)["response"]
        for line in _ANSWERS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if _ANSWERS.is_file()
    else []
)

#: Named so a skipped run says which artifact is missing and how to make it,
#: rather than leaving somebody to guess why a class vanished.
NEEDS_THE_REAL_ANSWERS = unittest.skipUnless(
    REAL, f"{_ANSWERS} is not in this checkout (runs/ is gitignored); "
    "run the honest-path job to produce it"
)


class EachEditMakesTheAnswerFalseTest(unittest.TestCase):
    def test_a_number_is_doubled_and_the_rest_is_untouched(self):
        out, what = plant.a_number_is_doubled("Ireland is 6.50 for up to 2kg.")
        self.assertEqual(out, "Ireland is 13 for up to 2kg.")
        self.assertIn("6.50", what)

    def test_a_refusal_becomes_a_promise(self):
        out, what = plant.a_refusal_is_inverted(
            "Underlining makes it unsellable, so those we cannot take back."
        )
        self.assertIn("we can take back", out)
        self.assertIn("negation", what)

    def test_no_longer_is_matched_before_no(self):
        """THE ORDERING BUG THIS LIST EXISTS TO AVOID. Matching `no` first
        yields 'we yes longer take cheques' — nonsense a judge would drop for
        the wrong reason, inflating recall with a case nothing produces."""
        out, _ = plant.a_refusal_is_inverted("We no longer take cheques.")
        self.assertEqual(out, "We still take cheques.")

    def test_a_unit_changes_while_the_number_stays(self):
        """This is what makes `unit` a different type from `number`. If the
        digits moved too, the two types would be measuring the same thing."""
        out, what = plant.a_unit_is_changed("ship within two working days")
        self.assertIn("working weeks", out)
        self.assertNotIn("working days", out)
        self.assertIn("unit", what)


    def test_an_entity_is_swapped_for_another_real_one(self):
        out, what = plant.an_entity_is_swapped("Yes. Ireland is 6.50 for up to 2kg.")
        self.assertIn("Belgium", out)
        self.assertNotIn("Ireland", out)
        self.assertIn("entity", what)


class AnEditThatCannotApplyReturnsNothingTest(unittest.TestCase):
    """Silence, never a pair. A generator that returned the input unchanged
    would put a pair labelled DROP into the set whose rewrite is identical to
    the real answer, and every judge that kept it would be marked wrong."""

    def test_no_number_no_pair(self):
        self.assertIsNone(plant.a_number_is_doubled("We wrap books at the counter."))

    def test_no_refusal_no_pair(self):
        self.assertIsNone(plant.a_refusal_is_inverted("We wrap books at the counter."))

    def test_no_unit_no_pair(self):
        self.assertIsNone(plant.a_unit_is_changed("We wrap books at the counter."))

    def test_no_entity_no_pair(self):
        self.assertIsNone(plant.an_entity_is_swapped("We wrap books at the counter."))

    def test_no_qualifying_sentence_no_pair(self):
        self.assertIsNone(plant.a_qualifying_sentence_is_removed("We wrap books."))


@NEEDS_THE_REAL_ANSWERS
class NoPlantedPairEqualsItsOwnRealAnswerTest(unittest.TestCase):
    """The failure that would silently corrupt every rate.

    A pair whose rewrite equals its chosen side is labelled DROP and is not a
    defect at all. Asserted over the OWNER'S REAL ANSWERS rather than a fixture,
    because the fixture is what the instrument will actually be built from.
    """

    def test_over_every_real_answer_and_every_edit(self):
        made = 0
        for answer in REAL:
            for kind, edit in plant.EDITS.items():
                result = edit(answer)
                if result is None:
                    continue
                rewritten, _ = result
                made += 1
                with self.subTest(kind=kind, answer=answer[:40]):
                    self.assertNotEqual(rewritten.strip(), answer.strip())
        self.assertGreater(made, 20, "the real rows should yield plenty of edits")


@NEEDS_THE_REAL_ANSWERS
class DeletionMayNotCarryADropLabelTest(unittest.TestCase):
    """The withdrawal of 2026-09-05, locked so it cannot come back quietly.

    `constraint` shipped as a DROP edit type on the claim that removing a
    qualifier widens the promise. All six pairs it produced were mislabelled:
    two were ungrammatical splices, four were LOSSY BUT TRUE - removing "If you
    give me your order number I can check the tracking" deletes an offer, so the
    rewrite promises less rather than more, and nothing in it is false. The
    judge dropped one of the six and it was a fragment. The published "1 of 6
    constraint recall" was a correct judge scored against a wrong key.

    THE RULE. A truth path may only emit a label it can guarantee. The four
    surviving edits SUBSTITUTE: each leaves a statement standing and makes that
    statement false. No rule in that module can tell a widened promise from a
    shortened answer, so deletion may not be labelled DROP there.
    """

    def test_the_constraint_type_is_not_in_the_closed_list(self):
        self.assertNotIn("constraint", plant.EDITS)

    def test_no_planted_pair_claims_to_be_a_deletion(self):
        for pair in plant.plant(REAL, per_type=6):
            with self.subTest(kind=pair["edit_type"]):
                self.assertNotEqual(pair["edit_type"], "constraint")

    def test_every_sentence_of_the_source_survives_into_the_rewrite(self):
        """The operational difference between a substitution and a deletion,
        asserted rather than described.

        Length is the wrong test and was tried first: `cannot` -> `can` and
        `Christmas` -> `Easter` both SHORTEN the answer while substituting. What
        distinguishes the two operations is that a substitution leaves every
        sentence standing with one span changed, so each source sentence still
        has a near counterpart. A deletion leaves one with no counterpart at
        all - which is exactly what the withdrawn `constraint` edit did.
        """
        import re as _re
        from difflib import SequenceMatcher

        def sentences(text):
            return [s for s in _re.split(r"(?<=[.!?])\s+", text.strip()) if s]

        for pair in plant.plant(REAL, per_type=99):
            was, now = sentences(pair["chosen"]), sentences(pair["rejected"])
            with self.subTest(kind=pair["edit_type"], edit=pair["edit"]):
                self.assertEqual(len(was), len(now), "a sentence went missing")
                for source in was:
                    best = max(
                        SequenceMatcher(None, source, other).ratio() for other in now
                    )
                    self.assertGreater(
                        best, self.COUNTERPART, f"no counterpart for {source!r}"
                    )

    #: Where a substituted sentence lands versus a deleted one. "We no longer
    #: take cheques." -> "We still take cheques." scores 0.75, the lowest any
    #: surviving edit produces, because the sentence is short and the swap is
    #: most of it. A deleted sentence scores against unrelated text. The next
    #: test asserts the gap rather than trusting this number.
    COUNTERPART = 0.5

    def test_the_withdrawn_generator_fails_the_test_the_others_pass(self):
        """PROOF THAT THE TEST ABOVE DISCRIMINATES. A threshold no input can
        fail is not a threshold. The withdrawn deletion edit is run through the
        same property and must fail it - if it ever passes, the property has
        stopped telling substitutions and deletions apart."""
        import re as _re
        from difflib import SequenceMatcher

        def sentences(text):
            return [s for s in _re.split(r"(?<=[.!?])\s+", text.strip()) if s]

        orphaned = 0
        for answer in REAL:
            result = plant.a_qualifying_sentence_is_removed(answer)
            if result is None:
                continue
            now = sentences(result[0])
            for source in sentences(answer):
                best = max(
                    (SequenceMatcher(None, source, other).ratio() for other in now),
                    default=0.0,
                )
                if best <= self.COUNTERPART:
                    orphaned += 1
        self.assertGreater(
            orphaned, 0, "the deletion edit no longer orphans any sentence"
        )

    def test_the_withdrawn_generator_is_kept_and_named_for_what_it_does(self):
        """Kept, not deleted: removing it would remove the record of how a
        wrong rate was produced. Named so no caller mistakes it for a defect."""
        self.assertTrue(hasattr(plant, "a_qualifying_sentence_is_removed"))
        doc = plant.a_qualifying_sentence_is_removed.__doc__ or ""
        self.assertIn("NOT A DEFECT GENERATOR", doc)


@NEEDS_THE_REAL_ANSWERS
class ASubstitutionMustNotProduceNonsenseTest(unittest.TestCase):
    """Three defects found by READING ALL 41 ROWS after the claim that they had
    been read was already published. The claim was overstated; this class is
    what checking it actually produced.

    Each is the same shape as the tell `_matching_case` was written for: a
    rewrite a judge can drop for LOOKING wrong rather than for BEING false, and
    recall measured on one of those is measuring the artefact.
    """

    def test_a_unit_is_not_swapped_inside_a_longer_word(self):
        """THE BUG. A substring search found `days` inside `holidays` and
        `Sundays`: "bank holiweeks", "free on Sunweeks". Two of thirteen unit
        rows, in a class whose recall had been published as 6 of 6."""
        self.assertIsNone(
            plant.a_unit_is_changed("We open 11am to 4pm on bank holidays.")
        )
        out, _ = plant.a_unit_is_changed("free on Sundays and two minutes away")
        self.assertNotIn("Sunweeks", out)

    def test_a_unit_still_swaps_when_the_word_stands_alone(self):
        """The other half: a fix that refused everything would pass the test
        above and destroy the class."""
        out, _ = plant.a_unit_is_changed("ship within two working days")
        self.assertIn("working weeks", out)

    def test_a_four_digit_year_is_not_doubled(self):
        """`A 1798 sermon collection` doubling to 3596 is false but ABSURD, and
        this module's standard is the lie a fluent generator would produce. The
        edit moves on to the next number rather than refusing the row."""
        out, what = plant.a_number_is_doubled(
            "A 1798 sermon collection in the locked case, 240.00."
        )
        self.assertIn("1798", out)
        self.assertIn("480", out)
        self.assertIn("240.00", what)

    def test_a_repeated_source_answer_yields_one_row_not_two(self):
        """`train.jsonl` holds one answer twice and the unit class drew it
        twice. Two rows from one sentence are not two observations - the rule
        `plant`'s own docstring claimed and did not enforce."""
        twice = ["ship within two working days.", "ship within two working days."]
        self.assertEqual(len(plant.plant(twice, per_type=99)), 1)

    def test_no_row_in_the_real_set_repeats_a_source_answer(self):
        seen = set()
        for pair in plant.plant(REAL, per_type=99):
            key = (pair["edit_type"], pair["chosen"])
            with self.subTest(edit=pair["edit"]):
                self.assertNotIn(key, seen)
            seen.add(key)


@NEEDS_THE_REAL_ANSWERS
class TheSetIsStratifiedAndHonestAboutItsDenominatorTest(unittest.TestCase):
    def test_it_draws_from_every_type_it_can(self):
        pairs = plant.plant(REAL, per_type=6)
        kinds = {p["edit_type"] for p in pairs}
        self.assertGreaterEqual(len(kinds), 4, f"only got {kinds}")

    def test_it_returns_fewer_rather_than_reusing_an_answer(self):
        """Two pairs from one sentence are not two observations. Asked for six
        of each from a single answer, it yields at most one per type."""
        one = ["Unmarked books can be returned within 30 days, but we cannot take marked ones."]
        pairs = plant.plant(one, per_type=6)
        by_type = {}
        for p in pairs:
            by_type[p["edit_type"]] = by_type.get(p["edit_type"], 0) + 1
        for kind, n in by_type.items():
            with self.subTest(kind=kind):
                self.assertEqual(n, 1)

    def test_every_pair_records_the_edit_so_a_reader_can_check_it(self):
        for p in plant.plant(REAL, per_type=3):
            with self.subTest(kind=p["edit_type"]):
                self.assertTrue(p["edit"].strip())
                self.assertEqual(p["truth"], "DROP")


@NEEDS_THE_REAL_ANSWERS
class AKeepPairKeepsEveryFactTest(unittest.TestCase):
    """The other half of the truth path, and it closes a measured confound.

    The 2026-09-05 stratified run measured this judge catching substitutions
    21 times out of 21 and deletions once out of six. The constructed KEEP set
    is deletions by design — so precision was measured ONLY on the class the
    judge cannot see, and a low false-drop rate there is equally consistent with
    good judgement and with noticing nothing.

    A paraphrase or a reorder keeps every fact and moves the surface. If the
    judge keeps those too, its precision is about meaning; if it drops them, it
    was reading the surface — the same finding from the other side. Either way
    the pair must be a genuine KEEP, and a mislabelled one corrupts the rate as
    surely as a mislabelled DROP would.
    """

    def test_a_contraction_changes_no_fact(self):
        out, what = plant.a_wording_is_swapped("We do not take cheques.")
        self.assertEqual(out, "We don't take cheques.")
        self.assertIn("same meaning", what)

    def test_case_is_preserved_at_the_swap(self):
        """The same lowercase-splice tell the DROP side already fixed. A
        KEEP pair with a broken sentence start could be dropped for looking
        malformed, which would inflate the false-drop rate."""
        out, _ = plant.a_wording_is_swapped("Cannot be returned after 30 days.")
        self.assertTrue(out[0].isupper(), out)

    def test_a_reorder_keeps_every_sentence(self):
        text = "We open at eleven. The counter closes at four."
        out, what = plant.the_sentences_are_reordered(text)
        self.assertIn("We open at eleven.", out)
        self.assertIn("The counter closes at four.", out)
        self.assertNotEqual(out, text)
        self.assertIn("reorder", what)

    def test_the_sentence_that_answers_the_question_is_never_moved(self):
        """THE DEFECT READING ALL 35 REORDER ROWS FOUND. Twelve pushed the
        answer to the end - "Ireland is 6.50 ... Yes." - and one changed the
        meaning outright: "I can put you on the want list and we will email you
        the day one comes in. Not at the moment.", where the refusal now
        attaches to the promise before it. A DROP pair labelled KEEP.

        The research lane's generator hit this and fixed it in its own v2->v3.
        I read that manifest before writing this and did not carry it across.
        """
        for text in (
            "Yes. Ireland is 6.50 for up to 2kg.",
            "Not at the moment. I can put you on the want list.",
            "I am sorry. Send a photo of the packaging.",
            "We do, for 2.00 a book. Add a note at checkout.",
            "No minimum. A single paperback posts happily.",
            "Good. The dust jacket is rubbed at the head.",
        ):
            with self.subTest(text=text):
                self.assertIsNone(plant.the_sentences_are_reordered(text))

    def test_a_sentence_that_is_not_an_answer_still_reorders(self):
        """The other half: a guard that refused everything would pass the test
        above and empty the class."""
        out, _ = plant.the_sentences_are_reordered(
            "Orders placed on the 3rd ship within two working days. "
            "Give me your order number and I can check the tracking."
        )
        self.assertTrue(out.startswith("Give me your order number"))

    def test_no_shipped_reorder_row_moves_an_answer(self):
        import re as _re

        for pair in plant.keeps_that_are_not_deletions(REAL, per_type=99):
            if pair["edit_type"] != "keep:reorder":
                continue
            parts = [
                s.strip()
                for s in _re.split(r"(?<=[.!?])\s+", pair["chosen"].strip())
                if s.strip()
            ]
            with self.subTest(answer=pair["chosen"][:40]):
                self.assertFalse(
                    parts[-2].lower().startswith(plant.ANSWER_OPENERS),
                    f"moved the answer: {parts[-2]!r}",
                )

    def test_a_dependent_sentence_is_never_reordered(self):
        """THE FAILURE THIS GUARD EXISTS FOR. 'It is by the till' after 'There
        is a water bowl' means something only in that order; swapping them
        changes the meaning, which would make it a DROP pair labelled KEEP —
        the one mistake a truth path may not make."""
        for text in (
            "There is a water bowl. It is by the till.",
            "We wrap books. They cost two pounds.",
            "Bring the receipt. That is all we need.",
        ):
            with self.subTest(text=text):
                self.assertIsNone(plant.the_sentences_are_reordered(text))

    def test_one_sentence_cannot_be_reordered(self):
        self.assertIsNone(plant.the_sentences_are_reordered("We open at eleven."))

    def test_no_keep_pair_equals_its_own_answer(self):
        for pair in plant.keeps_that_are_not_deletions(REAL, per_type=99):
            with self.subTest(kind=pair["edit_type"]):
                self.assertNotEqual(
                    pair["rejected"].strip(), pair["chosen"].strip()
                )

    def test_a_keep_pair_adds_no_digit_that_was_not_there(self):
        """A surface change that introduced a number would be adding a fact,
        which is the judge's second clause and would make the pair a DROP."""
        import re as _re

        for pair in plant.keeps_that_are_not_deletions(REAL, per_type=99):
            before = sorted(_re.findall(r"\d+", pair["chosen"]))
            after = sorted(_re.findall(r"\d+", pair["rejected"]))
            with self.subTest(kind=pair["edit_type"]):
                self.assertEqual(before, after)

    def test_a_reorder_preserves_the_whole_word_set(self):
        """The strongest available check that a reorder changed only order:
        the multiset of words is identical."""
        import re as _re
        from collections import Counter

        for pair in plant.keeps_that_are_not_deletions(REAL, per_type=99):
            if pair["edit_type"] != "keep:reorder":
                continue
            with self.subTest(answer=pair["chosen"][:40]):
                self.assertEqual(
                    Counter(_re.findall(r"[a-z']+", pair["chosen"].lower())),
                    Counter(_re.findall(r"[a-z']+", pair["rejected"].lower())),
                )


if __name__ == "__main__":
    unittest.main()
