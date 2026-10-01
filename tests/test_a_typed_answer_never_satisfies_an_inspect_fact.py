"""A card is not a form, and a form is how the five gates would be defeated.

`app/asking.py` turns a stopped diagnosis into the question that would move it.
The question is a typed object rather than a sentence, and that is the whole
point: a sentence asking for a number gets a number back in prose, a model
records it with `state_facts`, and the fact arrives ASSERTED. `eval_size_n` is
declared `source: inspect`. An assertion cannot open that gate, so nothing
moves, and the harness asks again. That round-trip is a live defect in the
owner's own transcript and it is what the module exists to end.

WHAT THIS FILE IS ADVERSARIAL ABOUT. The fix creates a new and much sharper
risk: a card that let a person TYPE a value into a `source: inspect` fact would
open G0 and G1 on a form field, and the five-gate honesty test - the sentence
this product is - would be defeated by an input box. So the central test here
does not check that the module happens not to do that. IT TRIES TO BUILD THE
FORBIDDEN CARD, FOR EVERY FACT IN THE LEDGER, and requires each attempt to fail
at construction.

THE LEDGER IS THE SOURCE OF EVERY LIST HERE. No fact name is written down in
this file except in prose about a specific defect. `spec.facts` is iterated,
`spec.admissible_for` decides what should have been allowed, and a fact added
next year is covered on the day it is added rather than on the day somebody
remembers this file exists. The same rule is asserted OF the module itself, in
`TheQuestionIsDerivedNotWrittenTest`: no fact name may appear as a string
literal in `app/asking.py`'s executable code, because a hand-written question
list is how the stale roadmap, the "only scoring tool" undersell and the
capability drift all happened.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from app import asking, diagnosis
from app.diagnosis import ASSERTED, DEFAULTED, MEASURED, STATED
from app.tools import REGISTRY, evidence


SPEC = diagnosis.default_spec()

#: A value of the right declared type for each fact, so a test can try to send
#: one. Derived from the declaration rather than tabulated, so it covers a fact
#: added next year without being edited.
def a_value_for(fact: str):
    decl = SPEC.facts[fact]
    if "enum" in decl:
        return decl["enum"][0]
    if "multi" in decl:
        return [decl["multi"][0]]
    declared = str(decl.get("type") or "")
    if declared == "bool":
        return True
    if declared == "int":
        return 999
    if declared == "float":
        return 0.99
    if declared == "str":
        return "something the person typed"
    return {}


class EveryFactInTheLedgerGetsACardOrAnHonestGapTest(unittest.TestCase):
    """Sixty-nine attempts, and not one of them may raise or be silent."""

    def test_every_declared_fact_produces_a_question_or_a_gap(self):
        for fact in sorted(SPEC.facts):
            with self.subTest(fact=fact):
                card = asking.question_for(fact)
                self.assertIsInstance(card, (asking.Question, asking.Gap))

    def test_an_undeclared_fact_is_refused_and_not_invented(self):
        with self.assertRaises(asking.AskingError):
            asking.question_for("you_have_an_eval_set")

    def test_every_gap_says_why_rather_than_going_quiet(self):
        """A gap is the honest reply and it has to read as one. An empty reason
        is a card that vanished, which is indistinguishable from a bug."""
        for fact in sorted(SPEC.facts):
            card = asking.question_for(fact)
            if isinstance(card, asking.Gap):
                with self.subTest(fact=fact):
                    self.assertTrue(card.reason.strip(), f"{fact} has no reason")


class ATypedAnswerNeverSatisfiesAnInspectFactTest(unittest.TestCase):
    """THE WALL. Every fact in the ledger, from both sides.

    The first three tests ask whether the module DOES the wrong thing. The
    fourth asks whether it CAN, which is the only version worth having: a rule
    that holds because every builder remembers it is a rule that holds until
    somebody writes a fourth builder.
    """

    def test_no_inspect_fact_is_ever_rendered_as_a_field(self):
        for fact, decl in sorted(SPEC.facts.items()):
            if decl.get("source") != "inspect":
                continue
            card = asking.question_for(fact)
            with self.subTest(fact=fact):
                if isinstance(card, asking.Gap):
                    continue
                self.assertFalse(
                    card.typed,
                    f"{fact} is source: inspect and got a typed field. A value "
                    "typed into that field is STATED at best, the ledger admits "
                    "MEASURED alone, and the gate it feeds would have opened on "
                    "a form.",
                )
                self.assertEqual(card.arrives_as, MEASURED)

    def test_every_typed_field_is_a_fact_the_ledger_says_is_the_persons_to_supply(self):
        for fact in sorted(SPEC.facts):
            card = asking.question_for(fact)
            if not isinstance(card, asking.Question) or not card.typed:
                continue
            with self.subTest(fact=fact):
                self.assertIn(
                    STATED,
                    SPEC.admissible_for(fact),
                    f"{fact} renders a field and the ledger does not admit a "
                    "person's own word for it",
                )
                self.assertEqual(SPEC.facts[fact].get("source"), "ask")
                self.assertEqual(card.arrives_as, STATED)

    def test_no_field_asks_for_something_a_registered_tool_measures(self):
        """`Build._validate_questions` enforces this from the other side, against
        the same registry. Look before you ask."""
        for fact in sorted(SPEC.facts):
            card = asking.question_for(fact)
            if not isinstance(card, asking.Question) or not card.typed:
                continue
            answerers = sorted(spec.name for spec in REGISTRY if fact in spec.measures)
            with self.subTest(fact=fact):
                self.assertEqual(answerers, [], f"{answerers} measures {fact}")

    def test_building_the_forbidden_card_raises_for_every_fact_it_would_lie_about(self):
        """THE ADVERSARY'S OWN MOVE, tried once per fact in the ledger.

        Take the card the module built, keep everything about it, and change the
        one thing an attacker would change: make it a typed field whose answer
        arrives STATED. Every fact whose ledger `source:` does not admit STATED
        has to refuse that object at construction - not at render, not at review.
        """
        refused = 0
        for fact, decl in sorted(SPEC.facts.items()):
            if STATED in SPEC.admissible_for(fact):
                continue
            refused += 1
            with self.subTest(fact=fact):
                with self.assertRaises(asking.AskingError) as caught:
                    asking.Question(
                        fact=fact,
                        answer=asking.NUMBER,
                        arrives_as=STATED,
                        accepts={"type": decl.get("type")},
                        declared={},
                        because=asking.Because(entry="", kind="node", stage=""),
                        settled_by={"tool": "state_facts", "run_as": evidence.USER},
                        dont_know=asking.DontKnow(
                            takes=None,
                            recorded_as=DEFAULTED,
                            how="",
                            resurfaces_as="",
                            conservative_because="",
                        ),
                        decides=0,
                    )
                self.assertIn(
                    str(decl.get("source")),
                    str(caught.exception),
                    "the refusal has to name the declared source, or the person "
                    "reading it cannot tell what would have worked",
                )
        self.assertGreater(
            refused,
            0,
            "no fact in the ledger refuses a person's own word, which would mean "
            "this test is asserting nothing at all",
        )

    def test_a_pointer_card_cannot_be_built_over_an_origin_the_ledger_refuses(self):
        """The mirror move: claim a measurement for a fact nothing measures."""
        for fact in sorted(SPEC.facts):
            card = asking.question_for(fact)
            if not isinstance(card, asking.Gap):
                continue
            if evidence.is_an_opinion(fact):
                continue
            with self.subTest(fact=fact):
                with self.assertRaises(asking.AskingError):
                    asking.Question(
                        fact=fact,
                        answer=asking.POINTER,
                        arrives_as=MEASURED,
                        accepts={},
                        declared={},
                        because=asking.Because(entry="", kind="node", stage=""),
                        settled_by={"tool": "measure_eval_set", "run_as": evidence.HARNESS},
                        dont_know=card_dont_know(),
                        decides=0,
                        slots=(asking.Slot("path", "string", "", True),),
                    )

    def test_an_opinion_is_never_asked_at_all(self):
        """Wall 7. A judge's grade of its own homework is not a reading, and no
        gate reads it - so there is nothing a card about it could unblock."""
        opinions = evidence.opinion_facts()
        self.assertTrue(opinions, "the ledger declares no opinion facts to check")
        for fact in opinions:
            with self.subTest(fact=fact):
                self.assertIsInstance(asking.question_for(fact), asking.Gap)

    def test_a_derive_fact_is_never_typed_into(self):
        """It comes from other facts. Where a tool computes one it gets a pointer
        at that tool; where nothing does, it is a gap and the answer is a build."""
        for fact, decl in sorted(SPEC.facts.items()):
            if decl.get("source") != "derive":
                continue
            card = asking.question_for(fact)
            with self.subTest(fact=fact):
                if isinstance(card, asking.Question):
                    self.assertTrue(card.points)
                    self.assertEqual(card.arrives_as, MEASURED)

    def test_every_pointer_names_a_tool_that_actually_declared_the_fact(self):
        for fact in sorted(SPEC.facts):
            card = asking.question_for(fact)
            if not isinstance(card, asking.Question) or not card.points:
                continue
            spec = REGISTRY.get(card.answered_by)
            with self.subTest(fact=fact):
                self.assertIsNotNone(spec, f"{card.answered_by} is not registered")
                self.assertIn(fact, spec.measures)
                self.assertEqual(card.run_as, evidence.HARNESS)


def card_dont_know() -> asking.DontKnow:
    return asking.DontKnow(
        takes=None, recorded_as=DEFAULTED, how="", resurfaces_as="", conservative_because=""
    )


class TheEngineAgreesWithTheCardTest(unittest.TestCase):
    """The card's rule and the engine's rule have to be one rule.

    A card that refuses a typed answer while the engine accepts one would be
    theatre; a card that offers one the engine then refuses would be the
    round-trip this module exists to end, wearing a nicer costume. So this runs
    the engine.
    """

    def test_a_stated_eval_count_does_not_open_the_first_gate(self):
        """The owner's transcript, mechanically. He said he had a thousand
        tickets; the number arrived as somebody's word rather than a count."""
        fact = self._one_inspect_fact_a_gate_reads()
        result = diagnosis.diagnose(
            {"target_score": diagnosis.stated(0.9), fact: diagnosis.stated(1000)}
        )
        self.assertNotEqual(result.verdict, "TRAIN")
        self.assertTrue(
            result.unsubstantiated,
            "a stated value for an inspect fact opened a gate silently",
        )
        self.assertEqual(
            {row["fact"] for row in result.unsubstantiated}, {fact}
        )

    def test_the_same_count_measured_opens_it(self):
        """And the pointer card is what produces this origin, which is why the
        card is a pointer. Refusing the assertion is only honest if the door it
        names actually works."""
        fact = self._one_inspect_fact_a_gate_reads()
        result = diagnosis.diagnose(
            {"target_score": diagnosis.stated(0.9), fact: diagnosis.measured(1000)}
        )
        self.assertEqual(result.gate_ledger["G0_EVAL_SET"]["status"], "PASSED")

    def test_the_card_for_that_fact_is_a_pointer_and_not_a_field(self):
        fact = self._one_inspect_fact_a_gate_reads()
        card = asking.question_for(fact)
        self.assertIsInstance(card, asking.Question)
        self.assertTrue(card.points)
        self.assertFalse(card.typed)
        self.assertTrue(any(slot.required for slot in card.slots))

    def _one_inspect_fact_a_gate_reads(self) -> str:
        """G0's fact, taken from G0's own parsed condition."""
        names = sorted(SPEC.gate_row_facts[("G0_EVAL_SET", "any")])
        self.assertEqual(len(names), 1, f"G0 now reads {names}; this test needs one")
        self.assertEqual(SPEC.facts[names[0]].get("source"), "inspect")
        return names[0]


class TheFrontierIsWhereTheWalkStoppedBelievingItselfTest(unittest.TestCase):
    def test_a_fact_the_walk_never_read_is_not_on_the_frontier(self):
        result = diagnosis.diagnose({})
        edge = asking.frontier(result)
        walked = {entry.id for entry in result.path}
        for item in edge.entries:
            with self.subTest(entry=item.entry):
                self.assertIn(item.entry, walked)

    def test_every_frontier_fact_was_actually_defaulted(self):
        result = diagnosis.diagnose({"target_score": diagnosis.stated(0.9)})
        for item in asking.frontier(result).entries:
            for fact in item.unknown:
                with self.subTest(fact=fact):
                    self.assertEqual(result.fact_origins[fact], DEFAULTED)

    def test_a_supplied_fact_leaves_the_frontier(self):
        """The frontier has to move when the person answers, or the card comes
        back forever and the product is the loop it was built to break."""
        before = asking.next_question(diagnosis.diagnose({}))
        self.assertIsNotNone(before)
        answered = (
            diagnosis.measured(a_value_for(before.fact))
            if before.points
            else diagnosis.stated(a_value_for(before.fact))
        )
        after = asking.next_question(diagnosis.diagnose({before.fact: answered}))
        self.assertTrue(after is None or after.fact != before.fact)

    def test_exactly_one_question_is_returned(self):
        """A form asks six. Nothing here returns a list to render."""
        card = asking.next_question(diagnosis.diagnose({}))
        self.assertIsInstance(card, asking.Question)

    def test_nothing_unknown_is_dropped_without_a_card_or_a_reason(self):
        """Every unknown fact at the frontier becomes exactly one of two things.

        Deliberately NOT "there is an entry nothing can answer". Whether one
        exists depends on which tools are registered today - `classes_n` was a
        gap until a tool that measures it was registered, which is the
        derivation working rather than a change here. What must hold whatever
        the registry holds is that the harness never walks past a fact in
        silence.
        """
        for facts in ({}, {"target_score": diagnosis.stated(0.9)}):
            for item in asking.frontier(diagnosis.diagnose(facts)).entries:
                with self.subTest(entry=item.entry):
                    self.assertEqual(
                        len(item.questions) + len(item.gaps), len(item.unknown)
                    )
                    if not item.answerable:
                        self.assertTrue(item.gaps)

    def test_the_module_still_produces_gaps_at_all(self):
        """If it stopped, every refusal test above would be asserting nothing.
        The opinion fact guarantees at least one, because no tool may ever
        measure a model's grade of its own homework."""
        gaps = [
            asking.question_for(f)
            for f in SPEC.facts
            if isinstance(asking.question_for(f), asking.Gap)
        ]
        self.assertTrue(gaps)


class TheOrderingIsTheSpecsAndNotAListTest(unittest.TestCase):
    """PRODUCT_SPEC 9.8 steps 3 and 4, checked as properties of the output."""

    def setUp(self):
        cards = [asking.question_for(f) for f in sorted(SPEC.facts)]
        self.pointing = [c for c in cards if isinstance(c, asking.Question) and c.points]
        self.typed = [c for c in cards if isinstance(c, asking.Question) and c.typed]
        self.assertTrue(self.pointing, "no fact in the ledger yields a pointer card")
        self.assertTrue(self.typed, "no fact in the ledger yields a typed card")

    def test_what_can_be_inspected_is_offered_before_what_must_be_asked(self):
        """Step 3: drop it and go inspect it. A pointer card IS that.

        Asserted over a DELIBERATELY MIXED list rather than only over whatever a
        frontier happens to hold, because a frontier entry whose facts are all
        one kind satisfies any ordering at all and would make this pass while
        asserting nothing. The mixed list is built from the ledger: every fact
        that yields a pointer, and every fact that yields a field.
        """
        mixed = self.typed + self.pointing  # deliberately the wrong way round
        ordered = asking.rank(mixed)
        kinds = [card.points for card in ordered]
        self.assertEqual(
            kinds,
            sorted(kinds, reverse=True),
            "an ask card was offered ahead of an inspectable one",
        )
        self.assertTrue(ordered[0].points)
        self.assertTrue(ordered[-1].typed)

    def test_the_frontier_uses_that_same_order(self):
        for facts in ({}, {"target_score": diagnosis.stated(0.9)}, self._a_wider_sheet()):
            edge = asking.frontier(diagnosis.diagnose(facts))
            for item in edge.entries:
                with self.subTest(entry=item.entry):
                    self.assertEqual(item.questions, asking.rank(item.questions))

    def test_the_top_card_is_the_top_of_the_frontiers_own_ranking(self):
        result = diagnosis.diagnose({})
        entry = asking.frontier(result).first_answerable
        self.assertEqual(
            asking.next_question(result).as_dict(), entry.questions[0].as_dict()
        )

    def test_within_a_kind_the_answer_that_settles_more_forks_comes_first(self):
        """Step 4, over every card the ledger yields rather than over a frontier
        that might hold one of each."""
        for group in (self.pointing, self.typed):
            counts = [card.decides for card in asking.rank(group)]
            self.assertEqual(counts, sorted(counts, reverse=True))
            self.assertGreater(
                max(counts),
                min(counts),
                "every card settles the same number of forks, so this ordering "
                "is not discriminating anything",
            )

    def test_the_count_is_the_nodes_and_gates_that_read_the_fact(self):
        """Derived, and checkable: every decision point it counted really does
        read the fact, and the number on the card is the size of that set."""
        for fact in sorted(SPEC.facts):
            nodes, gates = asking.decision_points(fact)
            with self.subTest(fact=fact):
                self.assertEqual(asking.decides(fact), len(nodes) + len(gates))
                for node_id in nodes:
                    self.assertIn(
                        fact, diagnosis._facts_read_by(SPEC, SPEC.conditions[node_id])
                    )
                self.assertEqual(list(gates), list(evidence.gates_that_read(fact)))

    def test_a_gate_is_counted_once_however_many_rows_it_has(self):
        """Counting `passes_when` rows would weight a fact for being read once in
        a four-class gate, which is a ranking about gate width and not about
        branches."""
        for fact in sorted(SPEC.facts):
            _nodes, gates = asking.decision_points(fact)
            with self.subTest(fact=fact):
                self.assertEqual(len(gates), len(set(gates)))

    def test_every_card_says_what_its_number_counted(self):
        for fact in sorted(SPEC.facts):
            card = asking.question_for(fact)
            if isinstance(card, asking.Question):
                with self.subTest(fact=fact):
                    self.assertEqual(card.decides_by, asking.DECIDES_BY)
                    self.assertTrue(card.decides_by.strip())

    def _a_wider_sheet(self) -> dict:
        return {
            "target_score": diagnosis.stated(0.9),
            "eval_size_n": diagnosis.measured(120),
        }


class ADontKnowIsAlwaysLegalTest(unittest.TestCase):
    def test_every_card_carries_one(self):
        for fact in sorted(SPEC.facts):
            card = asking.question_for(fact)
            if isinstance(card, asking.Question):
                with self.subTest(fact=fact):
                    self.assertIsInstance(card.dont_know, asking.DontKnow)
                    self.assertTrue(card.dont_know.as_dict()["legal"])

    def test_it_takes_the_ledgers_own_default_and_nothing_invented(self):
        for fact in sorted(SPEC.facts):
            card = asking.question_for(fact)
            if isinstance(card, asking.Question):
                with self.subTest(fact=fact):
                    self.assertEqual(
                        card.dont_know.takes,
                        diagnosis.unsupplied_value(SPEC.facts[fact]),
                    )

    def test_it_is_recorded_as_the_origin_only_the_engine_may_write(self):
        card = asking.next_question(diagnosis.diagnose({}))
        self.assertEqual(card.dont_know.recorded_as, DEFAULTED)
        with self.assertRaises(diagnosis.FactError):
            diagnosis.diagnose({card.fact: diagnosis.Fact(1, DEFAULTED)})

    def test_it_resurfaces_on_the_next_verdict_rather_than_disappearing(self):
        card = asking.next_question(diagnosis.diagnose({}))
        step = asking.next_step({})
        self.assertIn(card.fact, [a.fact for a in step.assumptions])
        assumed = [a for a in step.assumptions if a.fact == card.fact][0]
        self.assertEqual(assumed.origin, DEFAULTED)
        self.assertEqual(assumed.took, card.dont_know.takes)
        self.assertTrue(assumed.read_at)

    def test_an_assumption_is_a_default_the_walk_actually_read(self):
        """Not every defaulted fact. Sixty of them are defaulted in a run that
        supplied three, and listing all of them would bury the ones that decided
        something."""
        result = diagnosis.diagnose({})
        assumed = {a.fact for a in asking.assumptions(result)}
        defaulted = {
            f for f, origin in result.fact_origins.items() if origin == DEFAULTED
        }
        self.assertTrue(assumed)
        self.assertLess(len(assumed), len(defaulted))
        read: set[str] = set()
        for entry in result.path:
            read |= asking.facts_read_by(entry, result)
        self.assertEqual(assumed, defaulted & read)


class WhenTheQuestionsRunOutTheNextThingIsABuildTest(unittest.TestCase):
    def test_a_stopped_run_with_nothing_left_to_ask_proposes_instead(self):
        step = asking.next_step(self._a_sheet_with_no_answerable_frontier())
        self.assertTrue(step.is_build)
        self.assertIsNone(step.question)
        self.assertEqual(step.proposal.build_with, asking.BUILD_TOOL)

    def test_the_coverage_answer_comes_from_the_proposer_and_not_from_a_copy(self):
        from app.tools import propose

        step = asking.next_step(self._a_sheet_with_no_answerable_frontier())
        self.assertEqual(
            step.proposal.covered, step.proposal.outcome in propose.PROPOSERS
        )
        if step.proposal.covered:
            self.assertTrue(step.proposal.how)
            self.assertFalse(step.proposal.why_not)
        else:
            self.assertTrue(step.proposal.why_not)

    def test_the_build_tool_is_one_that_actually_exists(self):
        self.assertIsNotNone(REGISTRY.get(asking.BUILD_TOOL))

    def test_a_step_is_a_question_or_a_proposal_and_never_both(self):
        for facts in ({}, self._a_sheet_with_no_answerable_frontier()):
            step = asking.next_step(facts)
            with self.subTest(facts=sorted(facts)):
                self.assertNotEqual(step.is_question, step.is_build)
                self.assertEqual(step.question is None, step.is_build)
                self.assertEqual(step.proposal is None, step.is_question)

    def _a_sheet_with_no_answerable_frontier(self) -> dict:
        """Answer cards until none is left. Derived by walking the module's own
        output, so it keeps working when the tree changes."""
        facts: dict = {}
        for _ in range(len(SPEC.facts) + 1):
            step = asking.next_step(facts)
            if step.is_build:
                return facts
            card = step.question
            value = a_value_for(card.fact)
            facts[card.fact] = (
                diagnosis.measured(value) if card.points else diagnosis.stated(value)
            )
        raise AssertionError("the questions never ran out")


class TheOwnersTranscriptTest(unittest.TestCase):
    """The failure this module was built for, as a test rather than a story.

    He wrote: *"I have something like 1000 tickets with full information within
    them tracked to clients, reasons and so on."* The harness recorded one fact,
    ASSERTED, and never offered to go and count them.
    """

    def setUp(self):
        """The eval-set fact, the gate that reads it, and the card offered for it.

        All three derived. Which card comes FIRST depends on which tools happen
        to be registered - a tool registered for an earlier node moves the
        frontier, correctly - so this fixes on the entry that is about the eval
        set rather than on a position in a list.
        """
        names = sorted(SPEC.gate_row_facts[("G0_EVAL_SET", "any")])
        self.assertEqual(len(names), 1, f"G0 now reads {names}; this test needs one")
        self.fact = names[0]
        self.gate = evidence.gates_that_read(self.fact)[0]
        result = diagnosis.diagnose({"target_score": diagnosis.stated(0.9)})
        entries = [
            item for item in asking.frontier(result).entries if self.fact in item.unknown
        ]
        self.assertEqual(len(entries), 1, "the eval count is not on the frontier")
        self.entry = entries[0]
        self.card = [q for q in self.entry.questions if q.fact == self.fact][0]

    def test_the_harness_offers_to_count_rather_than_asking_for_the_number(self):
        self.assertTrue(self.card.points, "the card asked him to type the number again")
        self.assertEqual(self.card.arrives_as, MEASURED)
        self.assertTrue(any(slot.required for slot in self.card.slots))

    def test_the_card_says_which_gate_it_would_open_and_in_whose_words(self):
        self.assertEqual(self.entry.kind, "gate")
        self.assertEqual(self.card.because.kind, "gate")
        self.assertEqual(self.card.because.gate, self.gate)
        self.assertEqual(
            self.card.because.asks,
            " ".join(str(SPEC.gates[self.gate]["asks"]).split()).strip('"'),
        )
        self.assertIn(self.gate, self.card.opens())

    def test_a_model_answering_for_him_is_not_him_answering(self):
        """The card promises STATED for a person's own answer. What a model sends
        through the same door is ASSERTED, and the boundary decides that - not
        the card."""
        self.assertEqual(evidence.origin_for(evidence.USER), STATED)
        self.assertEqual(evidence.origin_for(evidence.MODEL), ASSERTED)
        self.assertEqual(asking.TYPED_ANSWER_ARRIVES_AS, STATED)


class TheQuestionIsDerivedNotWrittenTest(unittest.TestCase):
    """No hand-written question list, checked rather than promised.

    A list of questions in this module would drift from the ledger the first time
    a fact changed, which is exactly how the stale roadmap and the capability
    undersell happened. So: no declared fact name may appear as a string literal
    in `app/asking.py`'s executable code. Docstrings are exempt, because prose
    about a specific defect has to be able to name the fact it is about.
    """

    def test_no_fact_name_is_written_into_the_module(self):
        source = Path(asking.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                body = getattr(node, "body", None) or []
                if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                    docstrings.add(id(body[0].value))

        written = sorted(
            {
                node.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
                and node.value in SPEC.facts
            }
        )
        self.assertEqual(
            written,
            [],
            "app/asking.py names facts in code. Every question has to be derived "
            "from the ledger; a name here is a list that goes stale.",
        )

    def test_no_outcome_name_is_written_into_the_module_either(self):
        """The same rule for the other half. Which build follows which outcome is
        `app/tools/propose.py`'s answer, read from its own tables."""
        source = Path(asking.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                body = getattr(node, "body", None) or []
                if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                    docstrings.add(id(body[0].value))
        outcomes = SPEC.declared_outcomes()
        written = sorted(
            {
                node.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
                and node.value in outcomes
            }
        )
        self.assertEqual(written, [])

    def test_the_answer_shapes_come_off_the_declaration(self):
        for fact, decl in sorted(SPEC.facts.items()):
            card = asking.question_for(fact)
            if not isinstance(card, asking.Question) or not card.typed:
                continue
            with self.subTest(fact=fact):
                if "enum" in decl:
                    self.assertEqual(card.accepts, {"one_of": list(decl["enum"])})
                elif "multi" in decl:
                    self.assertEqual(card.accepts, {"any_of": list(decl["multi"])})
                else:
                    self.assertEqual(card.accepts, {"type": decl.get("type")})

    def test_a_pointers_slots_come_off_the_tools_own_schema(self):
        for fact in sorted(SPEC.facts):
            card = asking.question_for(fact)
            if not isinstance(card, asking.Question) or not card.points:
                continue
            spec = REGISTRY.get(card.answered_by)
            properties = spec.schema.get("properties") or {}
            required = set(spec.schema.get("required") or ())
            with self.subTest(fact=fact):
                self.assertEqual(
                    [slot.name for slot in card.slots], list(properties)
                )
                self.assertEqual(
                    {slot.name for slot in card.slots if slot.required}, required
                )
                self.assertEqual(
                    {slot.name for slot in card.slots if slot.bounds},
                    set(spec.bounds),
                )

    def test_the_card_serialises_to_something_a_surface_can_render(self):
        step = asking.next_step({})
        payload = step.as_dict()
        self.assertEqual(payload["kind"], asking.QUESTION)
        self.assertIn("accepts", payload["question"])
        self.assertIn("because", payload["question"])
        self.assertIn("dont_know", payload["question"])
        self.assertIn("entries", payload["frontier"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
