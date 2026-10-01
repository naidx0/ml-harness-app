"""TEST 1. The reachability-and-gates test. The most important test in the repo.

The product's only real differentiator is one sentence: no user is ever told to
train unless all five gates have been passed on the path that reached the
recommendation. That sentence has two halves and the second one is the half that
was missing.

  THE GATE HALF     every TRAIN__ outcome that a run reaches must have passed
                    all five gates on that run, under the row that applies to
                    the proposed method's class. TRAIN__ ONLY, and correctly so:
                    the gates exist to stop a training recommendation, and a
                    NO_TRAIN__ answer has nothing to be stopped from.

  THE REACHABILITY  EVERY DECLARED OUTCOME must be reachable by SOME consistent
  HALF              fact set - not just the training ones. An outcome no run can
                    reach passes the gate half for free, and a guarantee that
                    holds because nothing can test it is not a guarantee.

Four of the nine TRAIN__ outcomes were dead when the spec was first reviewed -
DISTILLATION, EMBEDDING_FINETUNE, TABULAR_DEEP and FULL_FINETUNE - and every one
of them was reported as gated. They were gated the way an empty room is quiet.

THEN THE PASS THAT FIXED THAT KILLED THREE NO-TRAIN OUTCOMES, and the reason
nobody noticed is written into the shape of this file: the reachability clause
was scoped to TRAIN__ outcomes. S8_TABULAR_STANDARD's bound was widened from
`> 10000` to `>= 1000` and the node moved last, and NO_LLM__SETFIT,
NO_LLM__ENCODER_FINETUNE and the classification reroute below it were swallowed.
A dead NO_LLM__ outcome is invisible to a test that only looks at TRAIN__ ones.
The no-train answers ARE the product; they are the last thing that should be
allowed to die quietly. So reachability is scoped to every terminal outcome the
file declares, and only the five-gate assertion stays scoped to TRAIN__.

Built so neither can happen again:

  * The list of outcomes comes out of the YAML, never out of this file - via
    `Spec.declared_outcomes()`, which reads node outcomes, gate on_fail outcomes
    and the mint's `emits`. Add an outcome of any prefix and it is checked from
    the moment it is added.
  * Each list is asserted non-empty before its loop runs. A spec that lost its
    emits list would otherwise turn the whole test into a loop over nothing,
    which is the same vacuum in a new place.
  * Reaching the outcome is asserted, not assumed. A shadowed outcome does not
    "have no fixture" - its fixture lands somewhere else, and the failure names
    the outcome and says where the run actually stopped.
"""

from __future__ import annotations

import unittest

import diagnosis_fixtures as fixtures

from app.diagnosis import default_spec, diagnose, gates_passed_under


def fact_sets_by_outcome() -> dict[str, dict]:
    """Every fact set the suite holds, indexed by the outcome it claims to reach.

    Three groups, one index. MINTING and REACHING are already keyed by outcome;
    SPREAD is keyed by a label because two of its cases reach the same outcome
    from different nodes, so it is indexed by the outcome each case names.

    The keying is a claim, not a proof. `test_every_declared_outcome_is_reachable`
    runs each fact set and checks where it actually lands, which is the only
    thing that can tell a shadowed outcome from a covered one.
    """
    index: dict[str, dict] = {}
    index.update(fixtures.REACHING)
    for case in fixtures.SPREAD.values():
        index.setdefault(case["outcome"], case["facts"])
    index.update(fixtures.MINTING)
    return index


class TrainOutcomesAreReachableAndGatedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = default_spec()

    def required_train_outcomes(self) -> set[str]:
        """Derive the outcome list from the spec, two independent ways.

        `emits` is what the minting node says it can produce. The method
        vocabulary is what the rest of the file can propose. If those two ever
        disagree, one training outcome has been added or removed in one place
        only, and neither list can be trusted until they agree again.
        """
        mint = self.spec.node_index["S9_MINT_TRAIN_VERDICT"]
        emitted = set(mint["emits"])
        from_methods = {f"TRAIN__{m}" for m in self.spec.methods if m != "UNSET"}
        self.assertEqual(
            emitted,
            from_methods,
            "S9_MINT_TRAIN_VERDICT.emits and `methods` disagree about which "
            "training outcomes exist; fix the spec before trusting this test",
        )
        return emitted

    def test_the_outcome_list_is_not_empty(self):
        outcomes = self.required_train_outcomes()
        self.assertTrue(
            outcomes,
            "the spec declares no TRAIN__ outcomes, so every assertion below "
            "would pass over an empty loop",
        )

    def test_every_train_outcome_has_a_fact_set(self):
        missing = sorted(self.required_train_outcomes() - set(fixtures.MINTING))
        self.assertEqual(
            missing,
            [],
            f"no fact set is registered for {missing}. If one cannot be written, "
            "the outcome is unreachable and its five-gate property is vacuous - "
            "fix the graph, do not weaken this test",
        )

    def test_every_train_outcome_is_reachable(self):
        for outcome in sorted(self.required_train_outcomes()):
            with self.subTest(outcome=outcome):
                facts = fixtures.MINTING.get(outcome)
                self.assertIsNotNone(facts, f"{outcome} has no fact set")
                result = diagnose(facts, self.spec)
                self.assertEqual(
                    result.outcome,
                    outcome,
                    f"{outcome} is NOT REACHABLE: its fact set stopped at "
                    f"{result.outcome} on node {result.node}. Some earlier "
                    "terminal node in that stage shadows it.",
                )
                self.assertEqual(result.verdict, "TRAIN")

    def test_every_reachable_train_outcome_passed_all_five_gates(self):
        for outcome in sorted(self.required_train_outcomes()):
            with self.subTest(outcome=outcome):
                result = diagnose(fixtures.MINTING[outcome], self.spec)
                self.assertEqual(result.outcome, outcome)

                # gates_passed_under, not bare membership in `path`. A gate
                # answered for a different method class did not ask this
                # proposal's question and does not count towards the mint.
                klass = self.spec.method_class(result.proposed_method)
                passed = gates_passed_under(result.path, klass, self.spec)
                missing = sorted(set(self.spec.required_gates) - passed)
                self.assertEqual(
                    missing,
                    [],
                    f"{outcome} was minted without {missing} passed under the "
                    f"{klass} row",
                )

    def test_the_mint_is_the_last_thing_that_happens(self):
        """RC3. A TRAIN verdict that is not the final node came from somewhere else."""
        for outcome in sorted(self.required_train_outcomes()):
            with self.subTest(outcome=outcome):
                result = diagnose(fixtures.MINTING[outcome], self.spec)
                self.assertEqual(result.path[-1].id, "S9_MINT_TRAIN_VERDICT")
                self.assertEqual(result.path[-1].kind, "node")
                self.assertEqual(result.node, "S9_MINT_TRAIN_VERDICT")

    def test_only_one_node_in_the_spec_can_mint(self):
        """SC1. Six stages used to emit TRAIN__ while only stage 9 checked gates."""
        minters = sorted(
            node_id
            for node_id, node in self.spec.node_index.items()
            if isinstance(node.get("outcome"), str) and node["outcome"].startswith("TRAIN__")
        )
        self.assertEqual(minters, ["S9_MINT_TRAIN_VERDICT"])

    def test_every_proposal_is_routed_to_the_stage_that_checks_the_gates(self):
        """SC2. A proposal is a candidate, not an answer."""
        for node_id, node in self.spec.node_index.items():
            if "propose" not in node:
                continue
            with self.subTest(node=node_id):
                in_stage_9 = self.spec.node_stage[node_id] == "stage_9_method_selector"
                self.assertTrue(
                    in_stage_9 or node.get("route") == "stage_9_method_selector",
                    f"{node_id} proposes {node['propose']} without routing to the "
                    "only stage that checks the gates",
                )

    def test_a_no_train_answer_is_reachable_for_every_gate(self):
        """The other side of the product. Each gate must be able to say no.

        A gate that no fact set can fail is decoration. For each of the five,
        some fixture in the spread must have stopped because that gate did not
        pass.
        """
        failed_somewhere: set[str] = set()
        for case in fixtures.SPREAD.values():
            result = diagnose(case["facts"], self.spec)
            for gate_id, entry in result.gate_ledger.items():
                if entry["status"] == "FAILED":
                    failed_somewhere.add(gate_id)
        never_fails = sorted(set(self.spec.required_gates) - failed_somewhere)
        self.assertEqual(
            never_fails,
            [],
            f"no fixture ever fails {never_fails}; a gate that cannot say no is "
            "not a gate",
        )


class EveryDeclaredOutcomeIsReachableTest(unittest.TestCase):
    """The widened half. Reachability applies to every prefix, not just TRAIN__.

    This class is the mechanical form of one sentence from the spec's
    `shadowing_rule`: a dead NO_LLM__ outcome is the same defect wearing a prefix
    that nobody checks. It is an answer the product claims it can give and
    cannot, and the user it was for gets somebody else's answer instead.

    Concretely, the three it would have caught: with S8_TABULAR_STANDARD widened
    to `tabular_rows >= 1000` and moved to the end of its stage, a tabular
    classification run with 5,000 rows, 800 features and 40 closed-set labels
    answered NO_DEEP__GRADIENT_BOOSTED_TREES. It should answer NO_LLM__SETFIT,
    and did before that pass. Nothing in the suite went red.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = default_spec()
        cls.declared = cls.spec.declared_outcomes()
        cls.by_outcome = fact_sets_by_outcome()

    def test_the_declared_outcome_list_is_not_empty_and_is_not_only_train(self):
        """The vacuum guard, in the place the vacuum would appear.

        If `declared_outcomes()` ever came back empty - or came back holding only
        the TRAIN__ family, which is what the narrow version of this check was
        looking at - then every assertion below would pass over nothing, and the
        widening would have bought us the appearance of coverage rather than
        coverage.
        """
        self.assertTrue(
            self.declared,
            "the spec declares no terminal outcomes at all, so every assertion "
            "below would loop over nothing",
        )
        prefixes = {o.split("__", 1)[0] + "__" for o in self.declared}
        self.assertGreater(
            len(prefixes),
            1,
            f"every declared outcome shares the prefix {prefixes}; this check was "
            "widened past TRAIN__ precisely so it would not be looking at one "
            "family",
        )
        non_train = {o for o in self.declared if not o.startswith("TRAIN__")}
        self.assertTrue(
            non_train,
            "no non-training outcome is declared. The no-train answers are the "
            "product; if they are gone, that is the finding, not a passing test",
        )

    def test_every_declared_outcome_has_a_fact_set(self):
        missing = sorted(self.declared - set(self.by_outcome))
        self.assertEqual(
            missing,
            [],
            f"no fact set is registered for {missing}. Add one to REACHING in "
            "tests/diagnosis_fixtures.py. If one cannot be written, the outcome "
            "is DEAD - some node above it in its stage has a condition its own "
            "condition implies - and the fix is the graph, never this test",
        )

    def test_every_declared_outcome_is_reachable(self):
        """The assertion itself. Run the fact set; check where it actually lands.

        A shadowed outcome does not fail by having no fixture. Its fixture lands
        somewhere else, usually on the node that shadows it, so the message says
        both.
        """
        for outcome in sorted(self.declared):
            with self.subTest(outcome=outcome):
                facts = self.by_outcome.get(outcome)
                self.assertIsNotNone(facts, f"{outcome} has no fact set")
                result = diagnose(facts, self.spec)
                self.assertEqual(
                    result.outcome,
                    outcome,
                    f"{outcome} is NOT REACHABLE: the fact set registered for it "
                    f"stopped at {result.outcome} on node {result.node}. Either "
                    f"an earlier terminal node shadows {outcome}, or a condition "
                    "above it was widened until it swallowed it. Fix the graph.",
                )

    def test_no_fact_set_is_registered_for_an_outcome_the_spec_does_not_declare(self):
        """The other direction, which is how a fixture outlives its outcome.

        A fact set keyed to an outcome that no longer exists in the spec is a
        test that passes while checking a claim the product stopped making.
        """
        stray = sorted(set(self.by_outcome) - self.declared)
        self.assertEqual(
            stray,
            [],
            f"fact sets are registered for {stray}, which the spec does not "
            "declare as terminal outcomes",
        )

    def test_the_verdict_of_every_reachable_outcome_matches_its_prefix(self):
        prefixes = self.spec.contract["outcome_prefixes"]
        for outcome in sorted(self.declared):
            with self.subTest(outcome=outcome):
                result = diagnose(self.by_outcome[outcome], self.spec)
                prefix, decl = self.spec.outcome_prefix(result.outcome)
                self.assertIn(prefix, prefixes)
                self.assertEqual(result.verdict, decl["verdict"])
                self.assertTrue(decl["terminal"])


if __name__ == "__main__":
    unittest.main()
