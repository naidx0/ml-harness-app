"""TEST 5. RC8. The engine answers. It does not raise.

A product whose entire pitch is an honest answer must not answer with a stack
trace. 493 of 40,000 randomized fact sets used to do exactly that - 321
ERROR__NO_NODE_MATCHED and 172 ERROR__CYCLE, 1.2% - and every one of them was a
real user shape: a dataset the harness could not open, a tabular team that never
ran a hyperparameter search, a cost-pressured team that never tried quantising.

WHY THIS IS A PROPERTY TEST AND NOT A FIXTURE. Whether the last node of a stage
is true for every run that can reach it is the same undecidable question the
spec's `shadowing_rule` is honest about, approached from the other side. A grep
cannot answer it and a reviewer reading the file did not: three of the four
looping routes were found by an adversary re-reading the graph, and the fourth -
S4_FORMAT_FIXED_CONTENT_STILL_WRONG rerouting into the stage that had sent the
run to it - was found by nobody until a fuzzer ran. A counterexample is all this
needs, and a fuzzer can find one.

WHAT IT DRAWS, AND WHY NONE OF IT IS TYPED IN HERE.

  * The fact list is the ledger, read from the spec.
  * Values come from each fact's own `enum`, `multi` or `type`.
  * The numbers come out of the spec document itself - every numeric literal it
    contains, plus each integer's two neighbours, so that every threshold in the
    file gets straddled from both sides. Nothing in this file is a number
    somebody chose; a threshold that moves in the YAML moves here with it.
  * The failure-mode keys come from S1_ROUTE_BY_FAILURE_MODE's own `routes`.
  * A fact is drawn three ways: given a value, OMITTED, or set explicitly to
    null. Those are three different code paths and only the first is obvious.
    Omitting a fact resolves it through its declared default; passing null
    BYPASSES that default, which is what an intake form with a blank field
    actually sends.

WHAT IT DOES NOT DRAW, said out loud rather than left as a silent hole:

  * Failure-mode keys the router has no route for. `failure_mode` is not a
    declared enum, so the spec cannot close that from inside itself; it is a
    fact-validation job and the spec names it as an open gap under
    `uninspectable_facts.one_known_gap` rather than papering over it. Drawing
    those keys here would fail on a gap that is already recorded honestly.
  * Values large enough to satisfy `tokens_available >= 20 * target_params`, the
    from-scratch floor, because no number that large appears in the file to draw
    from. TRAIN__FROM_SCRATCH is covered by a hand-written fixture in
    tests/diagnosis_fixtures.py instead; reachability is that test's job, and
    this one's job is that nothing raises.

WHAT A FAILURE PRINTS. The fact set that broke it - the facts it supplied, the
facts it supplied blank, and the facts it left out. A property test that says
"something failed" without saying which input is half a test; the first version
of this defect cost a re-run to reproduce, which is the mistake
scripts/flake_hunt.py exists to stop. The seed is fixed, so the failing draw is
reproducible, and the message carries the whole draw so it does not have to be.
The absent list is there because a null fact taking a branch false with it is
this test's whole subject, and a missing fact is invisible in a dict of the
facts that are present.
"""

from __future__ import annotations

import re
import unittest
from typing import Any

from app.diagnosis import EngineError, FactError, SpecError, default_spec, diagnose

# Fixed so a failure is reproducible, and so a green run today is the same green
# run tomorrow. Changing it is changing the test.
SEED = 20260818

# The uninspectable case is the one that broke, so it is swept rather than
# sampled at one rate: at 5% almost every fact is present, at 95% almost none is.
OMISSION_RATES = (0.05, 0.20, 0.40, 0.60, 0.80, 0.95)

# The spec's own RC8 asks for 40,000 draws at each of several omission rates.
DRAWS_PER_RATE = 40_000

# Of the facts that ARE supplied, this share arrive as an explicit null - a
# blank field on a form, rather than a field the form never had.
EXPLICIT_NULL_SHARE = 0.10

_NUMBER = re.compile(r"\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _numbers_in(spec) -> set[float]:
    """Every number the spec document contains, scalars and numbers inside prose.

    Reading them instead of choosing them is the point twice over. It keeps the
    repo's hardest rule - no invented numbers, in code as hard as in a document.
    And it keeps the draws pointed at the thresholds that exist: a bound moved in
    the YAML is a bound this test starts straddling on the next run, with nobody
    remembering to come here.
    """
    found: set[float] = set()

    def walk(value: Any) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            found.add(float(value))
        elif isinstance(value, str):
            for token in _NUMBER.findall(value):
                found.add(float(token))
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(spec.raw)
    return found


class _Draw:
    """The value banks, built once from the spec."""

    def __init__(self, spec) -> None:
        self.spec = spec
        numbers = _numbers_in(spec)

        integers: set[int] = set()
        for number in numbers:
            if number.is_integer() and 0 <= number <= 10**12:
                whole = int(number)
                # The neighbours matter as much as the threshold. `>= 1000` and
                # `> 1000` are different nodes, and only 999/1000/1001 tell them
                # apart.
                integers.update({max(0, whole - 1), whole, whole + 1})
        self.ints = sorted(integers)

        floats: set[float] = {n for n in numbers if 0 <= n <= 10**12}
        for number in list(floats):
            if 0.0 <= number <= 1.0:
                floats.add(round(min(1.0, number + 0.01), 4))
                floats.add(round(max(0.0, number - 0.01), 4))
        self.floats = sorted(floats)

        # DERIVED FROM THE FORKS, NOT FROM ONE NODE BY NAME. This read
        # `node_index["S1_ROUTE_BY_FAILURE_MODE"]["routes"]` - a bare mapping on
        # a node named in Python, which is the shape the fork schema replaced.
        # Taking the keys of every `argmax` fork means a ledger that adds a
        # second histogram fork is covered on the day it is added, and a ledger
        # that renames this one does not silently lose its adversarial inputs.
        self.failure_modes = sorted(
            {
                key
                for node in spec.node_index.values()
                if isinstance(node.get("fork"), dict)
                and node["fork"].get("select") == "argmax"
                for key in node["fork"]["routes"]
            }
        )
        assert self.failure_modes, "no argmax fork in the ledger to draw histogram keys from"
        # goal_text is read by nothing in the graph - `goal_is_learning` is the
        # derived fact the tree actually turns on - so any string will do, and
        # these say so rather than pretending to be samples.
        self.strings = ["", "a goal", "another goal"]

    def value(self, rng, name: str, decl: dict[str, Any]) -> Any:
        if "enum" in decl:
            return rng.choice(decl["enum"])
        if "multi" in decl:
            members = decl["multi"]
            return rng.sample(members, rng.randint(0, len(members)))
        declared = decl.get("type")
        if declared == "bool":
            return rng.random() < 0.5
        if declared == "int":
            return rng.choice(self.ints)
        if declared == "float":
            return float(rng.choice(self.floats))
        if declared == "str":
            return rng.choice(self.strings)
        if isinstance(declared, str) and declared.startswith("map"):
            keys = rng.sample(self.failure_modes, rng.randint(0, len(self.failure_modes)))
            return {key: rng.choice(self.ints) for key in keys}
        raise AssertionError(
            f"fact {name!r} is declared {decl!r} and this test has no way to draw a "
            "value for it. A fact the fuzzer cannot draw is a fact the fuzzer is "
            "not testing - add the shape here rather than skipping the fact."
        )

    def fact_set(self, rng, omission_rate: float) -> dict[str, Any]:
        facts: dict[str, Any] = {}
        for name, decl in self.spec.facts.items():
            if rng.random() < omission_rate:
                continue  # absent: resolves through the declared default
            if rng.random() < EXPLICIT_NULL_SHARE:
                facts[name] = None  # supplied but blank: bypasses the default
                continue
            facts[name] = self.value(rng, name, decl)
        return facts


def _where(rate: float, index: int, facts: dict[str, Any], ledger) -> str:
    """The whole point of the failure message: WHICH INPUT BROKE IT.

    Printed as a dict literal that can be pasted straight into a fixture or a
    REPL, because the next thing anyone reading this failure wants to do is run
    that exact fact set again. The seed and the draw number are here as well, so
    the failure is reproducible even if the message is truncated somewhere.

    THE ABSENT LIST IS NOT PADDING. The defect this test exists for is a fact
    that resolves to null and takes a whole branch false with it, and a fact
    that is missing is invisible in a dict of the facts that are present. So the
    facts the draw left out are named too, and they are the first place to look.
    """
    present = [f"    {name!r}: {value!r}," for name, value in sorted(facts.items())]
    absent = sorted(name for name in ledger if name not in facts)
    blank = sorted(name for name, value in facts.items() if value is None)
    return (
        f"seed={SEED} omission_rate={rate} draw #{index}\n"
        "facts = {\n" + "\n".join(present) + "\n}\n"
        f"supplied but blank ({len(blank)}): {', '.join(blank) or 'none'}\n"
        f"absent, so resolved through the ledger ({len(absent)}): "
        f"{', '.join(absent) or 'none'}"
    )


class NoFactSetMakesTheEngineRaiseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = default_spec()
        cls.draw = _Draw(cls.spec)
        cls.declared = cls.spec.declared_outcomes()

    def test_the_value_banks_are_not_empty(self):
        """The vacuum guard. Empty banks would make every draw the same draw."""
        self.assertTrue(self.draw.ints, "no integers were found in the spec file")
        self.assertTrue(self.draw.floats, "no floats were found in the spec file")
        self.assertTrue(self.draw.failure_modes, "S1_ROUTE_BY_FAILURE_MODE has no routes")
        self.assertTrue(self.declared, "the spec declares no terminal outcomes")

    def test_every_declared_fact_can_be_drawn(self):
        """A fact this test cannot draw is a fact this test is not exercising.

        Asserted separately from the sweep so that adding a new fact shape to the
        ledger fails here, with the fact's name, rather than as one confusing
        line inside a quarter of a million draws.
        """
        import random

        rng = random.Random(SEED)
        for name, decl in self.spec.facts.items():
            with self.subTest(fact=name):
                self.draw.value(rng, name, decl)

    def test_no_randomized_fact_set_raises_or_lands_off_the_ledger(self):
        """RC8. Every run returns a Diagnosis, and it is one the spec declares.

        Two assertions, because "did not raise" is the weaker half. An engine
        that answered with an outcome the file does not declare would satisfy the
        first and still be shipping something the UI cannot render and the ledger
        cannot explain.
        """
        import random

        declared = self.declared
        spec = self.spec
        for rate in OMISSION_RATES:
            rng = random.Random(SEED)
            for index in range(DRAWS_PER_RATE):
                facts = self.draw.fact_set(rng, rate)
                # The message is built only when something is wrong. Formatting
                # sixty-eight facts a quarter of a million times costs more than
                # every diagnose() call in this loop put together.
                try:
                    result = diagnose(facts, spec)
                except (EngineError, SpecError, FactError) as exc:
                    self.fail(
                        f"diagnose() raised {type(exc).__name__}: {exc}\n\n"
                        "A fact set the engine cannot answer is a user who gets a "
                        "stack trace where the product promises an honest answer. "
                        "ERROR__NO_NODE_MATCHED and ERROR__CYCLE are failures, not "
                        "acceptable results - the fix is the node the run should "
                        "have landed on, never a catch at the top.\n\n"
                        f"{_where(rate, index, facts, spec.facts)}"
                    )
                if result.outcome not in declared:
                    self.fail(
                        f"diagnose() returned {result.outcome!r} at node "
                        f"{result.node}, which is not a terminal outcome the spec "
                        f"declares.\n\n{_where(rate, index, facts, spec.facts)}"
                    )


if __name__ == "__main__":
    unittest.main()
