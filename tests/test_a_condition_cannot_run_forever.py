"""A ledger's condition dialect had no bound on what one expression could cost.

## The debt, and the half of it that was to WRITE DOWN WHICH KIND

`docs/PHASES.md` carried it under "Still open, and all are real":

> **The condition dialect has no bound on cost.** Arithmetic on text is refused
> now (`'a' * 2_000_000_000` was a two-gigabyte allocation from two constants in
> a data file) but nothing bounds a comprehension over a large map, and nothing
> times a condition out. A ledger is authored rather than user input, so this is
> a **robustness** debt, not a security one - and it should be written down as
> which before somebody treats a ledger as untrusted input.

Written down as which: **robustness.** Nothing here defends against an attacker.
A ledger is a file a person wrote and a reviewer read. What it defends against is
an author's honest mistake becoming a hang - `sum(x for x in some_map)` over a
fact that turns out to hold half a million rows is a condition that runs for a
minute and looks, from outside, like the product being broken.

If a ledger ever DOES become untrusted input, this bound is necessary and not
sufficient, and that sentence belongs here rather than in a later post-mortem:
a step budget stops a runaway, and it says nothing about what an authored
condition is allowed to read.

## A STEP COUNT AND NOT A CLOCK, which is the decision this file is really about

A wall-clock timeout makes a ledger's validity a property of the machine it is
evaluated on. The same file would pass on a laptop and fail in CI under load,
and a diagnosis that depends on how busy the box was is not a diagnosis - it is
the same defect as an unstable test, moved into the product. A step count is
deterministic: the same condition over the same facts costs the same number
everywhere, so a ledger that loads here loads for everybody.

`TheBoundIsDeterministic` is that argument, driven: the same condition evaluated
twice spends exactly the same budget.

## One counter, at the one door

Every `visit_*` method reaches its children through `visit`, so counting there
counts everything - including a comprehension's per-item work, which is where
the cost actually is. A counter inside `_comprehend` would have bounded the case
somebody thought of and nothing else, which is the shape of defect this
repository has closed twice under *"a guard on the function nobody calls"*.

## The number

Swept over every fixture sheet in this repository, the most expensive real
condition costs **35 steps**. The bound is 100,000. That is deliberate slack:
this bounds RUNAWAY, not authoring. A condition that reaches it is not one
somebody wrote slightly too generously - it is one that was not going to finish.
`TheRealLedgersAreNowhereNearIt` measures that rather than asserting it, so the
day a condition gets genuinely expensive this file says so.
"""

from __future__ import annotations

import ast
import unittest

import diagnosis_fixtures as fixtures

from app import diagnosis


def _steps_for(condition: str, facts: dict) -> int:
    """How many evaluation steps this condition spends over these facts."""
    spec = diagnosis.default_spec()
    state = diagnosis._State(spec=spec, facts=dict(facts))
    evaluator = diagnosis._Evaluator(state)
    evaluator.visit(ast.parse(condition, mode="eval").body)
    return evaluator.steps


class TheBoundExistsAndIsAStepCountTest(unittest.TestCase):
    def test_the_budget_is_declared_and_finite(self):
        self.assertIsInstance(diagnosis.CONDITION_STEP_BUDGET, int)
        self.assertGreater(diagnosis.CONDITION_STEP_BUDGET, 1_000)

    def test_an_evaluator_counts_what_it_visits(self):
        self.assertEqual(1, _steps_for("True", {}))
        self.assertGreater(_steps_for("1 + 2 + 3 + 4", {}), 4)

    def test_a_runaway_comprehension_is_stopped(self):
        """THE CASE THE DEBT NAMED. A fact holding half a million rows and a
        condition that sums a comprehension over it - the author's honest
        mistake, not an attack."""
        facts = {"failure_histogram": {f"k{i}": 1 for i in range(500_000)}}
        with self.assertRaises(diagnosis.EngineError) as caught:
            _steps_for("sum(1 for x in failure_histogram)", facts)
        said = str(caught.exception)
        self.assertIn("evaluation steps", said)
        self.assertIn("NOTHING WAS ANSWERED", said)

    def test_the_refusal_is_not_a_false(self):
        """A gate decided by a condition that ran out of budget would be a gate
        decided by exhaustion. It raises; it does not answer."""
        facts = {"failure_histogram": {f"k{i}": 1 for i in range(500_000)}}
        with self.assertRaises(diagnosis.EngineError):
            _steps_for("sum(1 for x in failure_histogram) > 0", facts)

    def test_a_comprehension_within_the_budget_still_works(self):
        """THE CONTROL. A bound that refused the real comprehensions in the
        shipped ledgers would be a bound nobody could leave switched on."""
        facts = {"failure_histogram": {"reasoning": 9, "format": 1}}
        state = diagnosis._State(spec=diagnosis.default_spec(), facts=dict(facts))
        got = diagnosis._Evaluator(state).visit(
            ast.parse("sum(1 for x in failure_histogram)", mode="eval").body
        )
        self.assertEqual(2, got, "the two keys were not both counted")

        # And the real shape the shipped ledgers use, which sums the VALUES.
        state = diagnosis._State(spec=diagnosis.default_spec(), facts=dict(facts))
        self.assertEqual(
            10,
            diagnosis._Evaluator(state).visit(
                ast.parse("sum(failure_histogram)", mode="eval").body
            ),
        )

    def test_the_bound_is_the_one_that_bites_rather_than_a_smaller_one(self):
        """Driven with a tiny budget, so the mechanism is shown working rather
        than inferred from a half-million-row fixture that could be slow for
        some other reason."""
        state = diagnosis._State(spec=diagnosis.default_spec(), facts={})
        evaluator = diagnosis._Evaluator(state, budget=3)
        with self.assertRaises(diagnosis.EngineError):
            evaluator.visit(ast.parse("1 + 2 + 3 + 4 + 5", mode="eval").body)


class TheBoundIsDeterministic(unittest.TestCase):
    """The whole reason it is a step count. A clock would make a ledger's
    validity a property of the machine, and the same file would pass on a
    laptop and fail in CI under load."""

    CONDITION = "sum(1 for x in failure_histogram) > 3"
    FACTS = {"failure_histogram": {"reasoning": 9, "format": 1, "tool_choice": 2}}

    def test_the_same_condition_costs_the_same_twice(self):
        first = _steps_for(self.CONDITION, self.FACTS)
        second = _steps_for(self.CONDITION, self.FACTS)
        self.assertEqual(first, second)

    def test_the_cost_scales_with_the_data_and_not_with_the_clock(self):
        small = _steps_for(
            "sum(1 for x in failure_histogram)", {"failure_histogram": {"a": 1}}
        )
        larger = _steps_for(
            "sum(1 for x in failure_histogram)",
            {"failure_histogram": {"a": 1, "b": 2, "c": 3, "d": 4}},
        )
        self.assertGreater(larger, small)


class TheRealLedgersAreNowhereNearItTest(unittest.TestCase):
    """The headroom, measured over the corpus rather than remembered.

    The day a shipped condition gets genuinely expensive, this reports it - and
    a bound whose headroom nobody re-measures is a bound that eventually bites
    an honest ledger.
    """

    #: The most expensive condition in either shipped ledger, over every fixture
    #: sheet, on 2026-08-27. A CEILING with generous slack: this is here to
    #: notice a change in kind, not to police an authoring style.
    THE_WORST_TODAY = 35
    ROOM_FOR = 4

    def _worst(self) -> tuple[int, str]:
        seen: dict[str, int] = {}
        original = diagnosis._State.eval

        def watched(state, tree):
            evaluator = diagnosis._Evaluator(state)
            try:
                return evaluator.visit(tree)
            finally:
                key = diagnosis._render(tree)[:80]
                seen[key] = max(seen.get(key, 0), evaluator.steps)

        diagnosis._State.eval = watched
        try:
            sheets = [sheet["facts"] for sheet in fixtures.SPREAD.values()]
            sheets += list(fixtures.REACHING.values())
            for facts in sheets:
                try:
                    diagnosis.diagnose(dict(facts))
                except diagnosis.EngineError:  # a fixture that reaches a raise
                    continue
        finally:
            diagnosis._State.eval = original
        cost, condition = max((n, c) for c, n in seen.items())
        return cost, condition

    def test_the_worst_real_condition_is_far_under_the_bound(self):
        cost, condition = self._worst()
        self.assertLessEqual(
            cost,
            self.THE_WORST_TODAY * self.ROOM_FOR,
            f"the most expensive shipped condition now costs {cost} steps "
            f"({condition!r}), against {self.THE_WORST_TODAY} when the bound was "
            "set. That is a change in kind rather than a drift; re-read the "
            "condition and then re-take this number.",
        )
        self.assertLess(cost * 1_000, diagnosis.CONDITION_STEP_BUDGET)

    def test_the_sweep_actually_measured_something(self):
        """A sweep that recorded nothing would make the assertion above pass
        against an engine that evaluates no conditions at all."""
        cost, _condition = self._worst()
        self.assertGreater(cost, 5)


class TheProductStillDiagnosesTest(unittest.TestCase):
    """Non-vacuity for the whole change: every fixture sheet still reaches a
    verdict. A bound that quietly broke the engine would pass every test above.
    """

    def test_every_reaching_fixture_still_reaches_its_outcome(self):
        reached = 0
        for outcome, facts in sorted(fixtures.REACHING.items()):
            with self.subTest(outcome=outcome):
                result = diagnosis.diagnose(dict(facts))
                self.assertEqual(outcome, result.outcome)
                reached += 1
        self.assertGreater(reached, 30, "the corpus this rests on is not there")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
