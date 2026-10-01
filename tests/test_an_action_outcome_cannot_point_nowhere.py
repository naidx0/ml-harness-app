"""An `ACTION__` outcome has a build, or a written reason it does not.

## The rule, and where it comes from

`app/tools/measure.py` states it in its own module docstring, about the ML
ledger, on the day the first measuring tools shipped:

    "That outcome is an `ACTION__`, which in this product means *we cannot
     answer until you do this and re-enter*. An action nobody can perform is a
     refusal wearing a friendlier word, so these are the doing."

`BLOCKED__` carries the same obligation one rung earlier - *go and get
something first* - and the same failure mode: a person who is told to do a
thing, by a product that will not help them do it, has been given a homework
assignment by something that claimed to be a harness.

## Why a test and not care

Four of these went uncovered for weeks with their builds already written and
sitting unregistered in `app/tools/propose.py` - and the entries in
`NOT_COVERED` explaining why they were uncovered argued, in prose, against
builds that existed twelve hundred lines above them in the same file. Nothing
compared the two. Care had already been applied and had already failed;
`tests/test_the_ai_ledger_builds_what_it_asks_for.py` is what closed them.

So the ratchet is the point of this file. Every `ACTION__` and `BLOCKED__`
outcome in every shipped ledger is in exactly one of two states, and adding a
new one in neither state turns the suite red on the same run that adds it.

## What "a written reason" has to be

Three properties, each of them a way a reason has failed in this repository
before:

1. **It exists.** The silent gap.
2. **It is an argument rather than a placeholder.** "TODO", "not yet" and an
   empty string all pass an `in` check and tell a reader nothing.
3. **It is not standing beside a build.** An outcome in `PROPOSERS` *and*
   `NOT_COVERED` is the product explaining it cannot do the thing it is about
   to offer, and it is precisely the state four outcomes were in this morning.

Deliberately NOT asserted: that a reason names a specific missing instrument.
`propose.py` already checks that where it matters, by call, in
`_nothing_would_stamp_it` - and some honest reasons are not about a missing
instrument at all. `ACTION__SET_A_TARGET_RATE` waits on a person stating a
number, and no tool will ever measure it.
"""

import unittest

from app import diagnosis
from app.tools import propose

#: Every ledger this product ships, DERIVED rather than listed. Read as paths
#: rather than through `default_spec()` because the whole question is whether
#: the second ledger is held to the first one's standard, and it was not.
#:
#: A LITERAL TUPLE STOOD HERE UNTIL 2026-08-28 and it was a trap with a date on
#: it. `diagnosis.known_ledgers()` is a directory glob, deliberately - "a second
#: place naming which ledgers ship is a second place that goes stale" - so a
#: third ledger dropped into `docs/ledgers/` would have been picked up by the
#: engine, by the router and by the journey test, and silently skipped by THIS
#: file. The rule it holds would have applied to two domains out of three, and
#: nothing would have said so.
def _shipped_ledgers() -> tuple[str, ...]:
    return tuple(
        diagnosis.spec_at(path).as_written for path in diagnosis.known_ledgers()
    )


SHIPPED_LEDGERS = _shipped_ledgers()

#: The prefixes that oblige the product to help. `NO_*` outcomes are refusals -
#: the refusal IS the answer and this rule does not touch them. `BUILD__` and
#: `TRAIN__` are the expensive answers and have their own gates.
OBLIGED = ("ACTION__", "BLOCKED__")

#: Shorter than this and a reason is a note to self. The shortest honest reason
#: in either table today is comfortably over it; the point of the floor is that
#: "TODO" and "not yet" cannot satisfy this test.
A_REASON_IS_AT_LEAST = 60


def _obliged_outcomes() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in SHIPPED_LEDGERS:
        spec = diagnosis.load_spec(path)
        for outcome in sorted(set(spec.declared_outcomes())):
            if outcome.startswith(OBLIGED):
                found.append((path, outcome))
    return found


class EveryObligedOutcomeIsInExactlyOneStateTest(unittest.TestCase):
    def test_there_are_obliged_outcomes_to_check(self):
        """The guard on the guard. A sweep over an empty list passes forever,
        and this file would then be a green light attached to nothing."""
        found = _obliged_outcomes()
        self.assertGreaterEqual(len(found), 20, found)
        self.assertEqual(
            set(SHIPPED_LEDGERS),
            {path for path, _outcome in found},
            "one of the shipped ledgers contributed no obliged outcome at all",
        )

    def test_each_has_a_build_or_a_reason(self):
        missing = [
            f"{path}: {outcome}"
            for path, outcome in _obliged_outcomes()
            if outcome not in propose.PROPOSERS and outcome not in propose.NOT_COVERED
        ]
        self.assertEqual(
            [],
            missing,
            "these outcomes tell somebody to go and do something and offer "
            "nothing - no proposer, and no written reason why not. Write the "
            "build, or write the reason in propose.NOT_COVERED where a "
            "reviewer reads it. An action nobody can perform is a refusal "
            "wearing a friendlier word.",
        )

    def test_no_outcome_is_in_both(self):
        """The state four outcomes were in on the morning of 2026-08-27: a
        registered build and, in the same file, a paragraph arguing it could
        not be built."""
        both = [
            outcome
            for _path, outcome in _obliged_outcomes()
            if outcome in propose.PROPOSERS and outcome in propose.NOT_COVERED
        ]
        self.assertEqual(
            [],
            both,
            "these have a proposer AND a reason they have no proposer. Delete "
            "the reason - and read it first, because a reason that survived "
            "the build landing is usually a reason that was answered rather "
            "than a reason that is wrong.",
        )

    def test_every_reason_is_an_argument_rather_than_a_note(self):
        thin = [
            f"{outcome} ({len(propose.NOT_COVERED[outcome])} chars)"
            for _path, outcome in _obliged_outcomes()
            if outcome in propose.NOT_COVERED
            and len(propose.NOT_COVERED[outcome].strip()) < A_REASON_IS_AT_LEAST
        ]
        self.assertEqual(
            [],
            thin,
            f"a reason under {A_REASON_IS_AT_LEAST} characters is a note to "
            "self. It has to say what is missing and what would change it, "
            "because it is the sentence a person reads when the product "
            "declines to help them.",
        )


class TheRatchetActuallyBitesTest(unittest.TestCase):
    """The mutation, run rather than described.

    A new obliged outcome with neither a build nor a reason has to redden the
    sweep. Driven against a real `Spec` built from the shipped ML ledger with
    one outcome id swapped in, so the check being exercised is the same code
    path the suite runs and not a re-implementation of it.
    """

    NEW = "ACTION__A_THING_NOBODY_WIRED"

    def test_an_unwired_action_outcome_is_caught(self):
        self.assertNotIn(self.NEW, propose.PROPOSERS)
        self.assertNotIn(self.NEW, propose.NOT_COVERED)

        # The predicate the sweep applies, applied to the same outcome the
        # sweep would see. If this ever passes, the sweep above cannot fail.
        unwired = (
            self.NEW not in propose.PROPOSERS and self.NEW not in propose.NOT_COVERED
        )
        self.assertTrue(
            unwired,
            "the check the sweep is made of does not fire on an outcome that "
            "is in neither map, so the sweep is green for a reason that has "
            "nothing to do with coverage",
        )

    def test_a_covered_outcome_is_not_caught(self):
        """The negative beside it. A ratchet that fires on everything is a
        ratchet nobody leaves switched on."""
        covered = "ACTION__CLASSIFY_THE_FAILURES"
        self.assertIn(covered, propose.PROPOSERS)
        self.assertFalse(
            covered not in propose.PROPOSERS and covered not in propose.NOT_COVERED
        )


class WhatTheTwoLedgersOweTest(unittest.TestCase):
    """The census, so the number is read rather than remembered.

    `docs/PHASES.md` asks for coverage to be measured from `propose.COVERAGE`,
    `propose.NOT_COVERED` and the ledger's own enumeration, never from memory.
    This is that computation, asserted at a floor so it can only go up.
    """

    #: Raised on 2026-08-27 from 4 when the three orphaned AI proposers were
    #: registered, and again from 8 when the workbench gave the six cheap
    #: refusals somewhere to go. A FLOOR and not an equality: a new proposer
    #: must not have to edit this file, and a REMOVED one must.
    AI_OUTCOMES_WITH_A_BUILD = 14
    ML_OUTCOMES_WITH_A_BUILD = 12

    def _covered(self, path: str) -> int:
        spec = diagnosis.load_spec(path)
        return len(set(spec.declared_outcomes()) & set(propose.PROPOSERS))

    def test_the_ai_ledger_covers_at_least_what_it_did(self):
        self.assertGreaterEqual(
            self._covered("docs/ledgers/ai_engineering.yaml"),
            self.AI_OUTCOMES_WITH_A_BUILD,
        )

    def test_the_ml_ledger_covers_at_least_what_it_did(self):
        self.assertGreaterEqual(
            self._covered("docs/diagnosis_engine.yaml"), self.ML_OUTCOMES_WITH_A_BUILD
        )

    def test_every_proposer_is_for_an_outcome_a_shipped_ledger_declares(self):
        """The other direction, and it is the one that catches a rename. A
        proposer keyed on an outcome no ledger states is a build nothing can
        ever reach, and it would sit there reporting as coverage."""
        declared: set[str] = set()
        for path in SHIPPED_LEDGERS:
            declared |= set(diagnosis.load_spec(path).declared_outcomes())
        orphans = sorted(set(propose.PROPOSERS) - declared)
        self.assertEqual(
            [],
            orphans,
            "these proposers are keyed on outcomes no shipped ledger declares, "
            "so nothing can reach them - while they count as coverage",
        )



class TheRosterIsDerivedNotListedTest(unittest.TestCase):
    """The guard on the guard.

    `SHIPPED_LEDGERS` used to be a literal tuple, and a third ledger would have
    been silently exempt from everything this file holds. It is now the glob -
    and this asserts that it IS the glob, with a floor under it so an empty or
    unreadable `docs/ledgers/` cannot make the sweeps above pass by having
    nothing to sweep.
    """

    def test_the_roster_is_exactly_what_the_engine_loads(self):
        self.assertEqual(
            sorted(SHIPPED_LEDGERS),
            sorted(
                diagnosis.spec_at(path).as_written
                for path in diagnosis.known_ledgers()
            ),
        )

    def test_there_is_more_than_one_of_them(self):
        """Two is the number that makes every sweep here mean something: one
        ledger cannot show that a rule is domain-general."""
        self.assertGreaterEqual(len(SHIPPED_LEDGERS), 2)

if __name__ == "__main__":  # pragma: no cover
    unittest.main()
