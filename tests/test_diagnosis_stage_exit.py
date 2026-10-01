"""TEST 6. RC8_NO_STAGE_RUNS_OFF_THE_END. Every stage has a way out.

The spec states the rule in `uninspectable_facts`, in capitals, because it is the
policy that makes the whole fact ledger safe:

    EVERY STAGE ENDS IN A NODE THAT CANNOT FAIL TO FIRE for any run that can
    reach it, or in an `always` router.

That sentence exists because a fact declared `source: inspect` with no default
resolves to null when the harness cannot read it, and a null takes every node in
its branch false with it. When that happens the walk falls out of the bottom of
the stage and `_walk_stage` raises ERROR__NO_NODE_MATCHED - a stack trace, from a
product whose entire pitch is an honest answer. 1.2% of randomized fact sets used
to get one.

TWO CLASSES, BECAUSE THE PROPERTY HAS A DECIDABLE HALF AND AN UNDECIDABLE HALF,
AND CONFLATING THEM IS HOW A CHECK LOOKS STRONGER THAN IT IS.

  EveryStageEndsInANodeThatCannotFailToFireTest is the decidable half. The spec
  does not merely follow the rule, it DECLARES the result of following it:
  `uninspectable_facts.stage_terminators` names the last node of every stage, and
  `uninspectable_facts.ask_nodes` names the six facts whose absence gets its own
  terminal answer. Both are claims about the graph, written in the graph's own
  file, and neither was checked against it. This class checks them: the declared
  terminator really is last, it is a node and not a gate, it can actually answer,
  and it obeys the file's own rule about `always`. Every one of those is settled
  by reading the graph, so it holds for every stage and every run at once - which
  no number of draws can give you.

  NoFactSetRunsOffTheEndOfAStageTest is the undecidable half, approached the only
  way it can be. Whether the last node of a stage is true for every run that can
  reach it is the same question `shadowing_rule` is honest about being unable to
  answer, seen from the other side; RC8 says so itself, and says what to do about
  it: "A fuzzer can find the counterexample, and a counterexample is all this
  needs."

WHAT THE HUNT DRAWS, AND WHY IT STARTS FROM THE FIXTURES.

A fact set drawn uniformly over sixty-eight facts almost never gets past stage 1.
The interesting stages are deep, their entry conditions are conjunctions of four
or five facts, and the last node of a stage is behind every node above it. So the
hunt does not draw fact sets - it PERTURBS the ones the suite already has. Every
fact set in tests/diagnosis_fixtures.py is a consistent story about a real user
that reaches somewhere specific; one to four mutations away from one of those is
the shape a real intake form produces when a field is blank, a number is off, or
the harness read one thing wrong. That is where the escapes live.

  * The seeds are MINTING, SPREAD and REACHING, whole, read at import.
  * Values come from the fact's own `enum`/`multi`, from `True`/`False` for
    booleans, and for numbers from the numeric literals in the spec document
    itself plus each integer's two neighbours - so every threshold in the file
    gets straddled from both sides and no number here is one somebody chose.
  * A mutation is one of three things, and only the first is obvious: give the
    fact a value, REMOVE it, or set it explicitly to null. Removing resolves the
    fact through its declared default; passing null bypasses that default, which
    is what a blank field on a form actually sends.

AND THE SECOND HUNT, WHICH IS DETERMINISTIC AND IS AIMED AT THE DEFECT ITSELF.
`test_blanking_the_facts_that_answered_never_runs_off_the_end` takes each fixture,
finds the node that answered it, blanks every fact that node's condition reads,
and runs it again - over and over. That is the RC8 hazard performed on purpose: it
removes exactly the knowledge that let the run stop where it did and asks what
catches it now. It needs no seed and no draws, it is the cheapest thing in this
file, and it walks runs down their stages one node at a time.

WHERE THE COVERAGE COMES FROM, said out loud because it is not where a reader
would assume. Every stage's terminator is reached, and it is the FIXTURES that
reach them, not the draws. Random perturbation is hopeless at this: reaching
S8_TEXT_CLASSIFICATION_NEEDS_LABELS needs seven facts true at once - text or
code, a classification task, closed labels, no multistep requirement, at least
eight examples per class, more than fifty classes and fewer than a thousand
examples - and twenty thousand draws found it zero times. Measured, not guessed.
So the sweep runs every fact set unmutated first and perturbs afterwards, and
`test_every_stage_terminator_is_actually_put_to_the_test` fails by naming the
stage that needs a story rather than by hoping for one. Three terminators needed
one when this file was written.

Its relationship to tests/test_diagnosis_no_crash.py is the same division. That
file draws whole fact sets uniformly over the ledger, a quarter of a million of
them, and asks only that nothing raises anywhere. This one starts from the
product's own stories, stays small, and asks specifically about stage exits.
"""

from __future__ import annotations

import ast
import random
import re
import unittest
from typing import Any

import diagnosis_fixtures as fixtures

from app.diagnosis import (
    EngineError,
    FactError,
    SpecError,
    compile_condition,
    default_spec,
    diagnose,
)

# Fixed so a failure is reproducible and so a green run today is the same green
# run tomorrow. Changing it is changing the test.
SEED = 20260818

# Sized for the suite, not for a nightly. Eight thousand perturbations of
# sixty-eight real stories runs in under two seconds; the exhaustive sweep over
# the whole ledger is tests/test_diagnosis_no_crash.py's job and it costs
# thirty. RC8's own "40,000 draws at each of several omission rates" is that
# file's budget, quoted there.
DRAWS = 8_000

# How many facts one draw disturbs. One finds the single blank field; four finds
# the intake form somebody filled in badly.
MUTATIONS = (1, 4)

# Of the mutations that do not give the fact a value, how they split between
# "the form never had this field" and "the field was there and left blank".
# These are different code paths in `validate_facts` and only the first is
# obvious.
REMOVE_SHARE = 0.15
NULL_SHARE = 0.07

# How many times the blanking descent is allowed to go round before we call it
# stuck. It stops on its own as soon as an answering node has nothing left to
# blank; this only bounds a pathological graph.
BLANKING_ROUNDS = 40

_NUMBER = re.compile(r"\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def facts_named_in(spec, condition: Any) -> set[str]:
    """The declared facts a condition reads.

    Parsed with the engine's own `compile_condition`, so the dialect is read the
    way the engine reads it rather than by a regex over the text. `always` and
    the prose conditions that have Python handlers name nothing, and say so by
    returning an empty set rather than by raising.
    """
    if not isinstance(condition, str) or condition == "always":
        return set()
    try:
        tree = compile_condition(condition)
    except SpecError:
        return set()  # a prose condition with a handler; it names no facts here
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} & set(spec.facts)


def stage_nodes(spec, stage: str) -> list[str]:
    """The node ids of a stage, in order, with the `gate_ref` entries dropped."""
    return [item["node"] for item in spec.stages[stage] if "gate_ref" not in item]


def numbers_in(spec) -> set[float]:
    """Every number the spec document contains, scalars and numbers inside prose.

    Read rather than chosen, which is the repo's hardest rule applied to a test:
    a threshold moved in the YAML is a threshold this file starts straddling on
    the next run, with nobody remembering to come here and change it.
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


def seed_fact_sets() -> dict[str, dict[str, Any]]:
    """Every fact set the suite holds, labelled by where it lives.

    The label is carried so a failure names the story it started from. "Four
    mutations away from MINTING:TRAIN__DPO" is a place to start reading; a bare
    dict of sixty-eight facts is not.
    """
    seeds: dict[str, dict[str, Any]] = {}
    for outcome, facts in fixtures.MINTING.items():
        seeds[f"MINTING:{outcome}"] = facts
    for label, case in fixtures.SPREAD.items():
        seeds[f"SPREAD:{label}"] = case["facts"]
    for outcome, facts in fixtures.REACHING.items():
        seeds[f"REACHING:{outcome}"] = facts
    return seeds


class _Bank:
    """The per-fact value banks, built once from the spec and the fixtures."""

    def __init__(self, spec) -> None:
        self.spec = spec
        numbers = numbers_in(spec)

        integers: set[int] = set()
        for number in numbers:
            if number.is_integer() and 0 <= number <= 10**12:
                whole = int(number)
                # The neighbours matter as much as the threshold. `>= 1000` and
                # `> 1000` are different nodes and only 999/1000/1001 tell them
                # apart.
                integers.update({max(0, whole - 1), whole, whole + 1})
        self.ints = sorted(integers)
        self.floats = sorted(
            {round(x, 4) for n in numbers if 0.0 <= n <= 1.0
             for x in (n, min(1.0, n + 0.01), max(0.0, n - 0.01))}
        )

        # Values the fixtures themselves use, kept per fact. A mapping fact -
        # failure_histogram is the only one - has no vocabulary this file could
        # invent honestly: `failure_mode` is not a declared enum, and the spec
        # names that as an open gap under `uninspectable_facts.one_known_gap`
        # rather than papering over it. So its values come only from the
        # fixtures, whose buckets are the eight S1_ROUTE_BY_FAILURE_MODE routes
        # for. Drawing invented keys here would fail on a gap that is already
        # recorded honestly.
        self.values: dict[str, list[Any]] = {}
        for facts in seed_fact_sets().values():
            for name, value in facts.items():
                if name in spec.facts:
                    self.values.setdefault(name, []).append(value)

        for name, decl in spec.facts.items():
            pool = self.values.setdefault(name, [])
            if "enum" in decl:
                pool.extend(decl["enum"])
            elif "multi" in decl:
                pool.extend([[member] for member in decl["multi"]])
                pool.append([])
            elif decl.get("type") == "bool":
                pool.extend([True, False])
            elif decl.get("type") == "int":
                pool.extend(self.ints)
            elif decl.get("type") == "float":
                pool.extend(self.floats)

    def draw(self, rng: random.Random, name: str) -> Any:
        pool = self.values.get(name)
        if not pool:
            return None
        value = rng.choice(pool)
        # Copied, never handed out by reference: a fixture whose histogram a
        # draw mutated would contaminate every test after it in a way no single
        # assertion could see.
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, list):
            return list(value)
        return value

    def mutate(self, rng: random.Random, facts: dict[str, Any]) -> dict[str, Any]:
        out = dict(facts)
        name = rng.choice(sorted(self.spec.facts))
        roll = rng.random()
        if roll < REMOVE_SHARE:
            out.pop(name, None)  # absent: resolves through the declared default
        elif roll < REMOVE_SHARE + NULL_SHARE:
            out[name] = None  # supplied but blank: bypasses that default
        else:
            out[name] = self.draw(rng, name)
        return out


def where(label: str, index: int, facts: dict[str, Any], spec) -> str:
    """The whole point of a failure message: WHICH INPUT BROKE IT.

    Printed as a dict literal that pastes straight into a fixture or a REPL,
    because running that exact fact set again is the next thing anyone reading
    this failure wants to do.

    THE ABSENT LIST IS NOT PADDING. The defect this file exists for is a fact
    that resolves to null and takes a whole branch false with it, and a fact that
    is missing is invisible in a dict of the facts that are present. So the facts
    the draw left out are named too, and they are the first place to look.
    """
    present = [f"    {name!r}: {value!r}," for name, value in sorted(facts.items())]
    absent = sorted(name for name in spec.facts if name not in facts)
    blank = sorted(name for name, value in facts.items() if value is None)
    return (
        f"seed={SEED} started from {label} draw #{index}\n"
        "facts = {\n" + "\n".join(present) + "\n}\n"
        f"supplied but blank ({len(blank)}): {', '.join(blank) or 'none'}\n"
        f"absent, so resolved through the ledger ({len(absent)}): "
        f"{', '.join(absent) or 'none'}"
    )


class EveryStageEndsInANodeThatCannotFailToFireTest(unittest.TestCase):
    """The decidable half: the spec's own declaration, checked against the graph.

    `uninspectable_facts.stage_terminators` is a table of ten claims - this stage
    ends in that node - and nothing read it. A table nobody reads is a table that
    drifts, and it drifts silently in the direction that matters: someone appends
    a node to a stage, the declared terminator is no longer last, and the new last
    node's condition is a predicate that can be false. The stage now has a way to
    run off the end and the file still says it does not.

    That is not hypothetical. The pass that added S1_CLOSED_SET_CLASSIFICATION
    opened a NEW DOOR into stage_8_classical - text and code runs, which
    `modality == tabular` does not describe - and the old terminator
    S8_TABULAR_UNMATCHED stopped covering everything that could reach the bottom
    of that stage. The spec's own comment on that line says so: "the stage would
    have run off the end for a text classifier with 60 labels and 500 examples".
    A new door into a stage means a new terminator, and this class is what makes
    that a build failure rather than a thing someone has to remember.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = default_spec()
        cls.policy = cls.spec.raw["uninspectable_facts"]
        cls.terminators = cls.policy["stage_terminators"]

    def test_the_declaration_covers_every_stage_and_names_only_real_ones(self):
        """The vacuum guard, in both directions.

        An empty table would make every assertion below loop over nothing. A
        table missing a stage is worse than that: it looks like coverage of the
        stages it does name, while the stage it forgot is the one nobody is
        looking at.
        """
        self.assertTrue(
            self.terminators,
            "uninspectable_facts.stage_terminators is empty, so every assertion "
            "in this class would pass over nothing",
        )
        undeclared = sorted(set(self.spec.stages) - set(self.terminators))
        self.assertEqual(
            undeclared,
            [],
            f"{undeclared} exist as stages and are not in "
            "uninspectable_facts.stage_terminators. A stage with no declared "
            "terminator is a stage nobody has said can be exited, and RC8's rule "
            "is that every one of them can be",
        )
        invented = sorted(set(self.terminators) - set(self.spec.stages))
        self.assertEqual(
            invented,
            [],
            f"stage_terminators names {invented}, which is not a stage in this "
            "file. Either the stage was renamed or the table was written from "
            "memory",
        )

    def test_the_declared_terminator_is_the_last_node_of_its_stage(self):
        """The claim itself, and the one an appended node breaks.

        Being present in the stage is not enough and never was: the walk
        evaluates the stage top to bottom and returns on the first node that
        fires, so a terminator with anything below it does not terminate
        anything. Only the last position does.
        """
        for stage in sorted(self.terminators):
            with self.subTest(stage=stage):
                order = stage_nodes(self.spec, stage)
                self.assertTrue(order, f"{stage} holds no nodes at all")
                declared = self.terminators[stage]
                self.assertEqual(
                    declared,
                    order[-1],
                    f"{stage} declares {declared} as its terminator and its last "
                    f"node is {order[-1]}. If {order[-1]} was appended, read its "
                    "condition: a run that reaches it and does not satisfy it "
                    "falls out of the bottom of the stage with "
                    "ERROR__NO_NODE_MATCHED. A new node at the end of a stage is "
                    "a new terminator whether or not anybody meant it to be",
                )

    def test_no_stage_ends_in_a_gate(self):
        """A trailing `gate_ref` is an exit that only exists when the gate FAILS.

        `_walk_stage` continues past a gate that passes, so a gate in the last
        position leaves the loop with nothing having answered - and the stage
        runs off the end for exactly the runs that did the work the gate asked
        about. The failure mode is inverted from every other one in this file,
        which is why it gets its own assertion instead of being folded into the
        one above.
        """
        for stage, items in sorted(self.spec.stages.items()):
            with self.subTest(stage=stage):
                self.assertNotIn(
                    "gate_ref",
                    items[-1],
                    f"{stage} ends in the gate {items[-1].get('gate_ref')}. A "
                    "gate that PASSES falls through to the end of the stage and "
                    "nothing catches the run. Put a node after it",
                )

    def test_every_terminator_can_actually_answer(self):
        """Firing is not the same as answering, and only one of them exits a stage.

        `_evaluate_node` returns None for a node that has no outcome, no route
        and no `fork:` - an effect-only node, of which this file has three.
        Evaluation continues in the stage afterwards. So a terminator that is
        effect-only fires, does nothing, and the stage runs off the end anyway.

        A FORK IS A `fork:` BLOCK NOW, NOT A BARE `routes:` MAPPING. This used to
        read `isinstance(node.get("routes"), dict)`, which was true of a mapping
        the engine could only execute if a Python function happened to be
        registered against that node's id. The block is the declaration, so this
        asks the same question of the thing that actually answers it.
        """
        for stage in sorted(self.terminators):
            with self.subTest(stage=stage):
                node = self.spec.node_index[self.terminators[stage]]
                answers = (
                    node.get("outcome") is not None
                    or node.get("route") is not None
                    or isinstance(node.get("fork"), dict)
                )
                self.assertTrue(
                    answers,
                    f"{node['node']} terminates {stage} and carries no outcome, "
                    "no route and no fork. It is an effect-only node: it fires, "
                    "returns None, and the walk carries on to the end of the "
                    "stage and raises",
                )

    def test_an_always_terminator_is_a_router_and_nothing_else_is_always(self):
        """The file's own rule about `always`, quoted and then enforced.

        uninspectable_facts: the last node of a stage carries a condition true
        for every run the nodes above it did not terminate, "written as a real
        predicate, never as `condition: always`, because an `always` non-router
        is indistinguishable from a node whose condition someone deleted."

        Two exceptions are named there and they are the two forks, so the rule
        has an exact mechanical form: `always` if and only if it forks.

        `is_fork` reads the declared `fork:` block rather than a bare `routes:`
        mapping, for the reason above: the block is what the engine executes.
        """
        for stage in sorted(self.terminators):
            with self.subTest(stage=stage):
                node = self.spec.node_index[self.terminators[stage]]
                is_router = isinstance(node.get("fork"), dict)
                is_always = node.get("condition") == "always"
                self.assertEqual(
                    is_always,
                    is_router,
                    f"{node['node']} terminates {stage} with condition "
                    f"{node.get('condition')!r} and {'is' if is_router else 'is not'} "
                    "a router. A router may be `always`, because the fork is the "
                    "answer. A terminator that is not a router must carry a real "
                    "predicate: `always` on one of those cannot be told apart "
                    "from a condition somebody deleted, and a deleted condition "
                    "is invisible in review and green in every test",
                )

    def test_the_ask_nodes_the_policy_names_are_real_and_can_fire(self):
        """The other declaration nothing read: `uninspectable_facts.ask_nodes`.

        The policy gives a fact three legal ways to be unreadable - a default, a
        null-safe reading, or an ASK node that names it and says how to supply
        it - and lists six facts that take the third. "Saying 'I could not read
        X, here is how to tell me' is a real answer. Raising is not."

        Four things have to hold for that to be true of a given row, and all four
        are decidable: the fact is in the ledger; it has NO default, because a
        fact with a default never arrives null and its ASK node would be dead
        code; the node exists and its outcome is terminal; and the node's own
        condition actually tests that fact for null, rather than being a node
        somebody put in the table because it looked related.
        """
        ask_nodes = self.policy["ask_nodes"]
        self.assertTrue(ask_nodes, "uninspectable_facts.ask_nodes is empty")

        for fact, node_id in sorted(ask_nodes.items()):
            with self.subTest(fact=fact, node=node_id):
                self.assertIn(
                    fact,
                    self.spec.facts,
                    f"ask_nodes names {fact!r}, which is not in the ledger",
                )
                self.assertNotIn(
                    "default",
                    self.spec.facts[fact],
                    f"{fact} has a declared default AND an ASK node. It can never "
                    f"arrive null, so {node_id} can never fire - which makes it "
                    "dead code claiming to be the policy's answer for this fact",
                )
                self.assertIn(
                    node_id,
                    self.spec.node_index,
                    f"ask_nodes points {fact!r} at {node_id}, which is not a node",
                )
                node = self.spec.node_index[node_id]
                outcome = node.get("outcome")
                self.assertIsInstance(
                    outcome,
                    str,
                    f"{node_id} is the ASK node for {fact} and has no outcome, so "
                    "a run that reaches it carries on rather than telling the "
                    "user what to supply",
                )
                _, decl = self.spec.outcome_prefix(outcome)
                self.assertTrue(
                    decl["terminal"],
                    f"{node_id} answers with {outcome}, which the contract says "
                    "is not terminal",
                )
                condition = str(node.get("condition", ""))
                self.assertIn(
                    fact,
                    facts_named_in(self.spec, condition),
                    f"{node_id} is registered as the ASK node for {fact} and its "
                    f"condition does not read it: {condition!r}",
                )
                self.assertIn(
                    "is null",
                    condition,
                    f"{node_id} is the ASK node for {fact} and its condition does "
                    "not test anything for null. The row exists to catch the "
                    "unreadable case; a condition that never asks whether the "
                    "fact is missing does not catch it",
                )


class NoFactSetRunsOffTheEndOfAStageTest(unittest.TestCase):
    """The undecidable half: hunt for the fact set that escapes.

    Two hunts, and they look for different things.

    THE PERTURBATION SWEEP takes the suite's own stories and moves one to four
    facts. That is the shape a real intake produces - a blank field, a number the
    harness read wrong, a checkbox nobody ticked - and it is where the escapes
    were found last time. Fixed seed, so a failure is reproducible; the message
    carries the whole fact set anyway, so it does not have to be.

    THE BLANKING DESCENT is deterministic and it is aimed straight at the defect.
    RC8 exists because a fact that cannot be inspected resolves to null and takes
    its branch false. So: run a fixture, find the node that answered it, blank
    every fact that node's condition reads, and run it again. Repeat. Each round
    removes exactly the knowledge that let the run stop where it did and asks
    what catches it now, which is the question the policy is an answer to. It
    costs a hundred and twenty diagnose() calls and it walks runs down their
    stages a node at a time.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = default_spec()
        cls.bank = _Bank(cls.spec)
        cls.seeds = seed_fact_sets()

    def _run(self, label: str, index: int, facts: dict[str, Any]):
        """diagnose(), or fail with the fact set that broke it.

        The message is built only when something is wrong. Formatting sixty-eight
        facts eight thousand times costs more than every diagnose() call in the
        sweep put together.
        """
        try:
            return diagnose(facts, self.spec)
        except (EngineError, SpecError, FactError) as exc:
            escaped = ""
            if str(exc).startswith("ERROR__NO_NODE_MATCHED"):
                escaped = (
                    "\nThis is RC8 exactly: the stage named above ran out of "
                    "nodes. Its last node's condition was false for this run. The "
                    "fix is that node's condition - widen it, or add the answer "
                    "below it - and never a catch at the top of the walk.\n"
                )
            self.fail(
                f"diagnose() raised {type(exc).__name__}: {exc}\n{escaped}\n"
                "A fact set the engine cannot answer is a user who gets a stack "
                "trace where the product promises an honest answer.\n\n"
                f"{where(label, index, facts, self.spec)}"
            )

    def test_the_seeds_and_the_value_banks_are_not_empty(self):
        """The vacuum guard. Empty banks would make every draw the same draw."""
        self.assertTrue(self.seeds, "no fact sets in tests/diagnosis_fixtures.py")
        self.assertTrue(self.bank.ints, "no integers were found in the spec file")
        self.assertTrue(self.bank.floats, "no floats were found in the spec file")
        empty = sorted(name for name in self.spec.facts if not self.bank.values.get(name))
        self.assertEqual(
            empty,
            ["goal_text"],
            f"these facts have no values to draw from: {empty}. A fact the hunt "
            "cannot vary is a fact the hunt is not testing. `goal_text` is the "
            "one legitimate entry - nothing in the graph reads it, "
            "`goal_is_learning` is the derived fact the tree turns on - so any "
            "other name here is a gap",
        )

    def test_every_stage_terminator_is_actually_put_to_the_test(self):
        """Non-vacuity, per stage, and at the only place that matters: the bottom.

        A stage the hunt never reaches the bottom of is a stage whose terminator
        this file says nothing about. Entering the stage is not enough - a run
        that stops three nodes in has not asked the terminator anything. So the
        measure is whether the LAST node of the stage was evaluated, which
        `path_ids()` records: `note_node` writes the id before the condition
        runs, so the node appearing there means the run got that far and the
        terminator was the only thing between it and ERROR__NO_NODE_MATCHED.

        THE FIXTURES ARE WHAT MAKE THIS PASS, NOT THE DRAWS, and that is
        deliberate. Every fact set is run unmutated first, so a terminator with a
        hand-written story behind it is reached with certainty rather than when a
        draw happens to go the right way. Perturbations then pile on top. If this
        fails, the fix is a fixture, and the message says which stage needs one.

        Three terminators had no story when this test was written, and all three
        were invisible for the same reason: the OUTCOME each emits was already
        covered from a different stage, so the reachability check in
        tests/test_diagnosis_invariant.py was green while the node had never run
        once. S3_KNOWLEDGE_GAP_IS_NOT_RETRIEVAL, S6_ABSENT_AND_NO_DATA and
        S8_TEXT_CLASSIFICATION_NEEDS_LABELS. Covering an outcome is not covering
        the node that emits it, and the bottom of a stage is exactly where that
        difference bites.
        """
        rng = random.Random(SEED)
        labels = sorted(self.seeds)
        terminators = self.spec.raw["uninspectable_facts"]["stage_terminators"]
        reached: dict[str, int] = {stage: 0 for stage in terminators}

        def census(label: str, index: int, facts: dict[str, Any]) -> None:
            walked = set(self._run(label, index, facts).path_ids())
            for stage, node_id in terminators.items():
                if node_id in walked:
                    reached[stage] += 1

        for index, label in enumerate(labels):
            census(label, index, dict(self.seeds[label]))
        for index in range(DRAWS):
            label = labels[index % len(labels)]
            facts = dict(self.seeds[label])
            for _ in range(rng.randint(*MUTATIONS)):
                facts = self.bank.mutate(rng, facts)
            census(label, index, facts)

        never = sorted(stage for stage, count in reached.items() if count == 0)
        self.assertEqual(
            never,
            [],
            "nothing in the suite ever reaches the last node of "
            f"{never}, so this file asserts nothing about {'those' if len(never) > 1 else 'that'} "
            f"terminator. Times each terminator was evaluated: {reached}.\n\n"
            "Write a fact set that gets to the bottom of that stage and put it in "
            "SPREAD in tests/diagnosis_fixtures.py, asserting the terminator by "
            "name. Do not look at whether the outcome it emits is already covered "
            "- it usually is, from some other stage, and that is exactly why the "
            "gap is invisible everywhere else",
        )

    def test_no_perturbed_fact_set_runs_off_the_end_of_a_stage(self):
        """RC8. Every run returns a Diagnosis, and it is one the spec declares.

        Two assertions, because "did not raise" is the weaker half. An engine
        that answered with an outcome the file does not declare would satisfy the
        first and still be shipping something the UI cannot render and the gate
        ledger cannot explain.
        """
        rng = random.Random(SEED)
        labels = sorted(self.seeds)
        declared = self.spec.declared_outcomes()
        self.assertTrue(declared, "the spec declares no terminal outcomes")

        for index in range(DRAWS):
            label = labels[index % len(labels)]
            facts = dict(self.seeds[label])
            for _ in range(rng.randint(*MUTATIONS)):
                facts = self.bank.mutate(rng, facts)
            result = self._run(label, index, facts)
            if result.outcome not in declared:
                self.fail(
                    f"diagnose() answered {result.outcome!r} at {result.node}, "
                    "which is not a terminal outcome the spec declares.\n\n"
                    f"{where(label, index, facts, self.spec)}"
                )

    def test_blanking_the_facts_that_answered_never_runs_off_the_end(self):
        """The deterministic hunt, performing the RC8 hazard on purpose.

        Take the node that answered, blank every fact its condition reads, run
        again. The run can no longer stop where it stopped, so it must be caught
        by something below - which is the policy's whole claim. Repeat until an
        answering node has nothing left to blank.

        The count of rounds is asserted at the end. A version of this that blanked
        nothing would pass every assertion inside the loop and prove nothing, and
        that is not a hypothetical: the first thing that goes wrong here is a
        change to how conditions are written that makes `facts_named_in` return
        empty sets, at which point every fixture stops after one round and the
        test goes quietly green.
        """
        descended = 0
        for label, seed in sorted(self.seeds.items()):
            facts = dict(seed)
            for round_number in range(BLANKING_ROUNDS):
                result = self._run(f"{label} blanked x{round_number}", round_number, facts)
                node = self.spec.node_index.get(result.node)
                if node is None:
                    break  # answered by a gate's on_fail, which has no condition
                blank = {
                    name
                    for name in facts_named_in(self.spec, node.get("condition"))
                    if facts.get(name) is not None
                }
                if not blank:
                    break
                for name in blank:
                    facts[name] = None
                descended += 1

        self.assertGreater(
            descended,
            len(self.seeds) // 4,
            f"the blanking descent only managed {descended} rounds over "
            f"{len(self.seeds)} fixtures, which is too few to be walking runs "
            "down their stages. Either the answering nodes have stopped naming "
            "facts in their conditions, or `facts_named_in` has stopped reading "
            "them - and in both cases this test is now green over nothing",
        )


if __name__ == "__main__":
    unittest.main()
