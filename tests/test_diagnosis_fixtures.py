"""TEST 4. A real spread of outcomes, and the answers that are the product.

Most of what this engine should say is "do not train". These fixtures walk that
spread: no eval set, no measured baseline, it already works, the facts move too
fast for weights, the prompt is not exhausted, quantise it first, fit a tree.
Plus the two halves the spec cares most about - the cost/latency/privacy branch
that used to be unreachable, and the failing halves where a proposal reaches the
sweep and a gate sends it back to something cheaper.

THREE CLASSES, AND THE MIDDLE ONE IS THE NEW HALF.

  OutcomeSpreadTest                      the spread, the cost branch, provenance.
  EveryProposingNodeOwesAFailingHalfTest RC5_FIXTURE_COVERAGE, executed. It
                                         derives the proposing nodes from the
                                         spec and demands a failing half for
                                         each - the half RC5 calls "the ones that
                                         matter; they are the product".
  EveryGateFailureEndsAtACheaperAnswerTest
                                         the routes that used to cycle, and the
                                         ordering property the fix rests on.

The last class of test in this file used to PIN three routes the spec could not
answer: the walk cycled and the engine raised. They are fixed, so it asserts the
answers instead, and it guards the structural property the fix rests on.
"""

from __future__ import annotations

import unittest

import diagnosis_fixtures as fixtures

from app.diagnosis import default_spec, diagnose


class OutcomeSpreadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = default_spec()

    def test_each_fixture_reaches_the_outcome_and_the_node_it_names(self):
        """The node matters as much as the outcome.

        Two different nodes emit NO_TRAIN__SHIP_AS_IS for two very different
        reasons - "it already works" and "quality passes and the cost pressure
        is not there yet" - and a test that checked only the outcome would not
        notice them swapping.
        """
        for label, case in fixtures.SPREAD.items():
            with self.subTest(case=label):
                result = diagnose(case["facts"], self.spec)
                self.assertEqual(result.outcome, case["outcome"])
                self.assertEqual(result.node, case["node"])

    def test_no_fixture_in_the_spread_is_a_train_verdict(self):
        for label, case in fixtures.SPREAD.items():
            with self.subTest(case=label):
                result = diagnose(case["facts"], self.spec)
                self.assertNotEqual(result.verdict, "TRAIN")
                self.assertFalse(result.outcome.startswith("TRAIN__"))

    def test_the_verdict_matches_the_prefix_the_contract_declares(self):
        prefixes = self.spec.contract["outcome_prefixes"]
        for label, case in fixtures.SPREAD.items():
            with self.subTest(case=label):
                result = diagnose(case["facts"], self.spec)
                prefix = next(p for p in prefixes if result.outcome.startswith(p))
                self.assertEqual(result.verdict, prefixes[prefix]["verdict"])
                self.assertTrue(prefixes[prefix]["terminal"])

    # -- the branch that was dead ------------------------------------------
    def test_the_cost_branch_is_reachable_and_answers_three_different_ways(self):
        """Stage 7 had no way in, so every user whose model worked but cost too
        much was told "ship it as is" and the run ended. That is arguably the
        most common enterprise case in the file and the product could not see
        it. It can now, and it gives three different answers depending on how
        much pressure there is."""
        cheapest = diagnose(fixtures.SPREAD["latency_quantize_first"]["facts"], self.spec)
        self.assertEqual(cheapest.outcome, "NO_TRAIN__QUANTIZE")

        below = diagnose(fixtures.SPREAD["cost_pressure_below_the_line"]["facts"], self.spec)
        self.assertEqual(below.node, "S7_PRESSURE_BELOW_THE_LINE")

        train = diagnose(fixtures.MINTING["TRAIN__DISTILLATION"], self.spec)
        self.assertEqual(train.outcome, "TRAIN__DISTILLATION")

        for result in (cheapest, below, train):
            self.assertIn("S1_QUALITY_PASSES_BUT_CONSTRAINED", result.path_ids())

    def test_the_privacy_branch_does_not_strike_distillation(self):
        """A one-off teacher run that generates a training set is data
        collection, not the deployed system. Striking distillation here would
        delete the privacy branch of stage 7, which is the case the constraint
        exists for."""
        facts = dict(fixtures.MINTING["TRAIN__DISTILLATION"])
        facts["privacy"] = "on_prem_only"
        facts["need_type"] = ["privacy"]
        result = diagnose(facts, self.spec)
        self.assertEqual(result.outcome, "TRAIN__DISTILLATION")
        self.assertIn("FORBID_THIRD_PARTY_API", result.constraints)
        self.assertNotIn("DISTILLATION", result.struck_methods)

    # -- the failing halves, which are the product -------------------------
    def test_a_proposal_that_fails_a_gate_dies_and_is_recorded(self):
        """Three named cases. EveryProposingNodeOwesAFailingHalfTest does this
        over every proposing node the spec has; this stays as the small readable
        version.

        `retriever_fails_g3` used to be the third name here and it is not one of
        these. It fails G3 at the TOP of stage 3, before any node in that stage
        runs, so no proposal exists when the gate says no - the ledger shows a
        FAILED gate either way, which is why the swap makes no difference to what
        passes and every difference to what the test is about.
        `retriever_fails_g4` is the retriever case where a proposal really does
        reach the sweep.
        """
        for label in ("distillation_fails_g4", "tabular_deep_fails_g4", "retriever_fails_g4"):
            with self.subTest(case=label):
                result = diagnose(fixtures.SPREAD[label]["facts"], self.spec)
                self.assertNotEqual(result.verdict, "TRAIN")
                failed = [g for g, e in result.gate_ledger.items() if e["status"] == "FAILED"]
                self.assertTrue(failed, "a gate stopped the run but the ledger does not say so")
                self.assertTrue(
                    any(r.get("reason", "").startswith(failed[0]) for r in result.rejected),
                    "the gate that stopped the run is not in rejected[]",
                )

    def test_the_tabular_branch_pays_for_the_four_gates_it_skipped(self):
        """S0_MODALITY_FORK sends tabular straight to stage 8, skipping four of
        the five gates. That is exactly why nothing past the fork may mint
        without going through the sweep first."""
        result = diagnose(fixtures.MINTING["TRAIN__TABULAR_DEEP"], self.spec)
        ids = result.path_ids()
        self.assertLess(ids.index("S8_TABULAR_DEEP_JUSTIFIED"), ids.index("S9_GATE_SWEEP"))
        for gate_id in ("G1_BASELINE_MEASURED", "G2_PROMPT_EXHAUSTED", "G3_RETRIEVAL_CONSIDERED"):
            entry = result.gate_ledger[gate_id]
            self.assertEqual(entry["status"], "PASSED")
            self.assertGreater(
                ids.index("S9_GATE_SWEEP"),
                0,
                "the tabular run reached the mint without the sweep",
            )

    def test_a_teaching_outcome_is_not_a_training_verdict(self):
        """TEACH__ does train a model, so it gets its own fence rather than a
        quiet exemption. It is not a TRAIN__ verdict because it recommends
        nothing about the user's actual problem."""
        result = diagnose(fixtures.SPREAD["teaching_from_scratch"]["facts"], self.spec)
        self.assertEqual(result.outcome, "TEACH__FROM_SCRATCH_NANOGPT")
        self.assertEqual(result.verdict, "NO_TRAIN")

    # -- provenance ---------------------------------------------------------
    def test_a_defaulted_hardware_fact_makes_the_cost_provenance_unknown(self):
        """Invariant 3. A verdict computed from a defaulted hardware number is a
        different claim from one computed from a measured GPU, and must not look
        the same on screen."""
        measured = diagnose(fixtures.MINTING["TRAIN__LORA_SFT"], self.spec)
        self.assertEqual(measured.cost_provenance, "MEASURED")

        facts = dict(fixtures.MINTING["TRAIN__LORA_SFT"])
        del facts["vram_gb"]
        self.assertEqual(diagnose(facts, self.spec).cost_provenance, "UNKNOWN")

    def test_the_hardware_router_records_which_reference_row_it_used(self):
        """The fact ledger has no base-model-size fact, so the VRAM table cannot
        be indexed by the model being trained. The router uses the smallest
        reference point in the file and says so, rather than letting a reader
        inherit the assumption invisibly."""
        result = diagnose(fixtures.MINTING["TRAIN__LORA_SFT"], self.spec)
        self.assertIsNotNone(result.hardware_reference)
        self.assertEqual(result.hardware_reference["model"], "7B")
        self.assertEqual(result.route, "LORA")

        table = self.spec.node_index["S9_HARDWARE_ROUTER"]["reference_points"]
        self.assertIn(result.hardware_reference, table)

    def test_the_router_does_not_run_for_a_proposal_it_does_not_describe(self):
        """Its table is an LLM VRAM table. Run over a tabular or retriever
        proposal, its cpu_only route would send a TABULAR_DEEP proposal back to
        the stage it came from."""
        for outcome in ("TRAIN__TABULAR_DEEP", "TRAIN__EMBEDDING_FINETUNE"):
            with self.subTest(outcome=outcome):
                result = diagnose(fixtures.MINTING[outcome], self.spec)
                self.assertIsNone(result.route)
                self.assertIsNone(result.hardware_permits)

    # -- purity -------------------------------------------------------------
    def test_diagnose_does_not_mutate_the_facts_it_is_given(self):
        facts = fixtures.MINTING["TRAIN__LORA_SFT"]
        before = {k: (list(v) if isinstance(v, list) else v) for k, v in facts.items()}
        diagnose(facts, self.spec)
        self.assertEqual(facts, before)

    def test_the_same_facts_always_give_the_same_answer(self):
        for outcome, facts in fixtures.MINTING.items():
            with self.subTest(outcome=outcome):
                first = diagnose(facts, self.spec)
                second = diagnose(facts, self.spec)
                self.assertEqual(first.outcome, second.outcome)
                self.assertEqual(first.path_ids(), second.path_ids())



class EveryProposingNodeOwesAFailingHalfTest(unittest.TestCase):
    """RC5_FIXTURE_COVERAGE, executed instead of counted.

    RC5 states the rule in two halves with two different counts, and is explicit
    that conflating them is what made the old wording wrong twice. The minting
    half is counted per OUTCOME and is checked in tests/test_diagnosis_invariant.py.
    This class is the other half: counted per PROPOSING NODE, one fact set for
    every node in the spec carrying `propose:`, each one letting that node put a
    method forward and then having the proposal refused.

    WHY THE LIST IS DERIVED AND NEVER TRANSCRIBED. RC5's own `proposing_nodes`
    block says it "is derivable by grepping this file for `propose:`, and it
    should be derived rather than transcribed, because transcribing it is how two
    went missing" - S6_GENUINELY_ABSENT and S8_VISION_AUDIO_GAP, both of which
    propose UNSET and were absent from the list that preceded it. So nothing here
    names a node. The set comes out of `spec.node_index`, and a thirteenth
    proposing node added to the YAML tomorrow fails this class with its own id in
    the message.

    WHAT A FAILING HALF HAS TO PROVE, and why three assertions rather than one.

      IT REACHED THE NODE. Asserted as `proposed_method`, not as membership in
      `path`. `_evaluate_node` calls `note_node` BEFORE it evaluates the
      condition, so a node id in the path proves only that the engine looked at
      it. `retriever_fails_g3` is the fixture that makes this concrete: it was
      credited by RC5 with covering S3_TRAIN_THE_RETRIEVER_NOT_THE_LLM and it
      never reaches it, because G3 is the leading gate of stage 3 and fails at
      the top of the stage under the provisional llm_weights row. It comes back
      UNSET. A membership check would not have noticed.

      SOMETHING REFUSED IT, AND WE SAY WHAT. `refused_by` names a gate or a node,
      and the assertion differs accordingly: a gate must be FAILED in the ledger
      and present in `rejected[]`; a node must be the one that answered.

      THE REFUSAL IS THE REASON. `mints_when` restores the single flipped fact
      and the run must train. Without that, a fixture that landed on the cheap
      answer for some unrelated reason would look exactly like a fixture that
      landed there because the gate said no. Two of the twelve carry no
      `mints_when` and both say why in the fixture file: one is refused by a
      strike that lasts the life of the run, so no single fact undoes it.

    A NOTE ON WHERE THE SWEEP SITS, because it bounds what this class can ask
    for. RC5's wording is "flipping one fact so a gate fails AT THE SWEEP", and
    that is achievable for ten of the twelve. It is not achievable for
    S9_FULL_FT_JUSTIFIED and S9_FROM_SCRATCH, which are themselves inside
    stage_9_method_selector, below S9_GATE_SWEEP. No gate is evaluated after they
    propose, and none could be: both propose an llm_weights method into a run
    whose sweep already ran under llm_weights, so `row_key` does not change and
    the latching rule would skip the re-ask. Stage 9 refuses those two by strike
    and by the teaching node instead. That is a fact about the graph, recorded
    here rather than smoothed over by pretending a gate did it.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = default_spec()
        cls.proposing_nodes = {
            node_id
            for node_id, node in cls.spec.node_index.items()
            if "propose" in node
        }
        cls.halves = fixtures.failing_halves()

    def test_the_proposing_node_set_is_derived_from_the_spec_and_is_not_empty(self):
        """The vacuum guard, and it is not decoration.

        Every assertion below loops over this set. If `propose:` were renamed in
        the YAML, or the node index stopped carrying it, this class would go
        green over nothing and the product's most important fixtures would have
        stopped being checked without anything going red.
        """
        self.assertTrue(
            self.proposing_nodes,
            "no node in the spec carries `propose:`, so every assertion in this "
            "class would loop over an empty set. Either the key was renamed or "
            "the graph can no longer propose a method at all",
        )
        for node_id in sorted(self.proposing_nodes):
            with self.subTest(node=node_id):
                self.assertIn(self.spec.node_index[node_id]["propose"], self.spec.methods)

    def test_every_proposing_node_has_a_failing_half(self):
        missing = sorted(self.proposing_nodes - set(self.halves))
        self.assertEqual(
            missing,
            [],
            f"{len(missing)} proposing node(s) owe a failing half and have none: "
            f"{missing}. A proposing node with no failing half is a way the "
            "product can say 'train this' that nothing has ever made say no. Add "
            "a fact set to tests/diagnosis_fixtures.py that reaches the node, "
            "lets it propose, and has the proposal refused; mark it with "
            "`failing_half_of=` and it is picked up here automatically. If one "
            "genuinely cannot be written, that is a finding about the graph - "
            "the node proposes a method nothing can refuse - and the fix is the "
            "graph, not this test",
        )

    def test_no_failing_half_claims_a_node_the_spec_does_not_have(self):
        """The other direction, which is how an index goes quietly stale.

        A fixture marked `failing_half_of` a node that has been renamed or has
        stopped proposing still passes the check above - it simply stops
        satisfying anything. Named separately so a rename fails with the old id
        visible rather than with a count.
        """
        orphaned = sorted(set(self.halves) - self.proposing_nodes)
        self.assertEqual(
            orphaned,
            [],
            f"these fixtures claim to be the failing half of {orphaned}, which "
            "no longer proposes anything in the spec. Either the node was "
            "renamed or its `propose:` was removed; in both cases the fixture is "
            "now covering nothing",
        )

    def test_each_failing_half_reaches_its_node_lets_it_propose_and_is_refused(self):
        """The assertion itself. Three claims per fixture, and the first is the
        one a weaker test would have got wrong.

        `proposed_method` is checked against what the node's own `propose:` says
        in the SPEC, not against a string in the fixture, so a node that changes
        which method it puts forward breaks here rather than silently making the
        fixture cover a different thing.
        """
        for node_id in sorted(self.proposing_nodes):
            for label in self.halves.get(node_id, []):
                case = fixtures.SPREAD[label]
                with self.subTest(node=node_id, case=label):
                    result = diagnose(case["facts"], self.spec)
                    self.assertEqual(
                        result.proposed_method,
                        self.spec.node_index[node_id]["propose"],
                        f"{label} is registered as the failing half of {node_id}, "
                        f"but the run came back proposing {result.proposed_method!r}. "
                        f"It never reached {node_id}, so nothing about that node "
                        "is being tested. Membership in path() is not enough - "
                        "note_node writes the id before the condition runs",
                    )
                    self.assertEqual(case["proposes"], result.proposed_method)
                    self.assertNotEqual(
                        result.verdict,
                        "TRAIN",
                        f"{label} is a failing half and it minted a training "
                        "verdict; the refusal is gone",
                    )
                    self.assertEqual(result.outcome, case["outcome"])
                    self.assertEqual(result.node, case["node"])

    def test_the_thing_that_refused_the_proposal_says_so_in_the_record(self):
        """A refusal the audit trail cannot show is a refusal the UI cannot render.

        Two shapes, because stage 9 has two. A gate refusal must be FAILED in the
        ledger AND named in `rejected[]`; the ledger alone is not enough, because
        `rejected[]` is what the plan page reads. A node refusal must be the node
        that actually answered.
        """
        for node_id in sorted(self.proposing_nodes):
            for label in self.halves.get(node_id, []):
                case = fixtures.SPREAD[label]
                refused_by = case["refused_by"]
                with self.subTest(node=node_id, case=label, refused_by=refused_by):
                    result = diagnose(case["facts"], self.spec)
                    if refused_by in self.spec.gates:
                        entry = result.gate_ledger[refused_by]
                        self.assertEqual(
                            entry["status"],
                            "FAILED",
                            f"{label} says {refused_by} refused the proposal from "
                            f"{node_id}, and the ledger says {entry['status']}",
                        )
                        self.assertTrue(
                            any(
                                r.get("reason", "").startswith(refused_by)
                                for r in result.rejected
                            ),
                            f"{refused_by} stopped the run and is not in rejected[], "
                            "so the plan cannot show the user why",
                        )
                    else:
                        self.assertIn(
                            refused_by,
                            self.spec.node_index,
                            f"{label} says it was refused by {refused_by!r}, which "
                            "is neither a gate nor a node in the spec",
                        )
                        self.assertEqual(result.node, refused_by)

    def test_restoring_the_one_flipped_fact_turns_the_refusal_back_into_a_train(self):
        """The counterexample, and the reason each of these is a diagnosis.

        Every fixture here differs from a training run by one fact. Put it back
        and the run must train. Without this, a fact set that reached the cheap
        answer for some reason nobody noticed would be indistinguishable from one
        that reached it because the gate said no - which is exactly the failure
        mode `shadowing_rule` describes for outcomes, wearing fixtures instead.
        """
        checked = 0
        for node_id in sorted(self.proposing_nodes):
            for label in self.halves.get(node_id, []):
                case = fixtures.SPREAD[label]
                restore = case["mints_when"]
                if restore is None:
                    continue
                with self.subTest(node=node_id, case=label, restore=sorted(restore)):
                    self.assertEqual(
                        len(restore),
                        1,
                        f"{label} restores {sorted(restore)}; a failing half is one "
                        "flipped fact, and a multi-fact restore hides which one "
                        "the gate was actually about",
                    )
                    result = diagnose(dict(case["facts"], **restore), self.spec)
                    self.assertEqual(
                        result.verdict,
                        "TRAIN",
                        f"{label} put {restore} back and the run still did not "
                        f"train - it answered {result.outcome} at {result.node}. "
                        "So the fixture is not one fact away from a training "
                        "verdict, and what it demonstrates about "
                        f"{node_id} is not what it claims",
                    )
                    checked += 1
        self.assertGreater(
            checked,
            0,
            "not one failing half carries a `mints_when`, so this test checked "
            "nothing. The restore is what makes these fixtures diagnoses rather "
            "than coincidences",
        )


class EveryGateFailureEndsAtACheaperAnswerTest(unittest.TestCase):
    """The three routes that used to loop. They answer now, and this says how.

    WHAT THE DEFECT WAS. When a gate fails, evaluation resumes at the first
    non-gate node of the stage its `on_fail` names. That works wherever the
    target stage contains a terminal remedy for the thing the gate row asked
    about, and four of the seven routes did:

        G2 llm_weights    -> stage_5_behaviour   its first three nodes are
                                                 exactly the negation of the row
        G3 llm_weights    -> stage_3_knowledge   S3_BUILD_RAG is `not retrieval_tried`
        G3 llm_efficiency -> stage_3_knowledge   same
        G4 any            -> stage_6_capability  S6_SWAP_THE_MODEL is `not model_swap_tried`

    The other three routed back into the stage that had produced the proposal,
    and that stage had no node answering the gate's question:

        G2 classical_deep -> stage_8_classical   nothing asked for a hyperparameter search
        G3 classical_deep -> stage_8_classical   nothing asked about features
        G2 llm_efficiency -> stage_7_efficiency  nothing asked about quantisation

    So the same node proposed again, the sweep failed the same gate again, and
    the walk cycled until the guard raised ERROR__CYCLE. The users that hit were
    precisely the ones the gates exist for - a tabular team that never ran a
    hyperparameter search, a cost-pressured team that never tried quantising -
    and they got a Python exception where they should have got the cheap remedy.

    WHAT THE FIX ACTUALLY DID, because it is not what the words "add a remedy"
    suggest and the difference is worth knowing. The new remedies -
    S8_TABULAR_DEEP_NEEDS_HPARAM_SEARCH, S8_TABULAR_DEEP_NEEDS_FEATURE_WORK,
    S7_QUANTIZATION_UNTRIED, S7_CACHING_UNTRIED - sit ABOVE the node that makes
    the proposal. So the run never proposes at all: the stage answers the gate's
    own question before anything reaches the sweep. The gate is then honestly
    NOT_REACHED in the ledger rather than FAILED, and the user gets the cheaper
    answer one step earlier than before.

    That is also why those `on_fail` routes are now unreachable from the sweep.
    S8_TABULAR_DEEP_JUSTIFIED only fires when `hparam_search_trials >= 50`, which
    IS G2's classical_deep row, so a classical_deep proposal cannot fail G2. The
    remedy is not a landing pad for a failure; it is what stops the failure.

    The last test here guards the ordering that makes all of that true, because
    the ordering is the whole fix. Move a proposing node above the remedies in
    its stage and the loop comes straight back.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = default_spec()

    def test_the_three_routes_that_used_to_cycle_now_answer(self):
        """Each names the cheap work that was skipped, and none is a TRAIN."""
        cases = {
            "tabular_deep_fails_g2": ("NO_DEEP__TUNE_THE_TREES_FIRST",
                                      "S8_TABULAR_DEEP_NEEDS_HPARAM_SEARCH"),
            "tabular_deep_fails_g3": ("NO_DEEP__FIND_THE_MISSING_FEATURE",
                                      "S8_TABULAR_DEEP_NEEDS_FEATURE_WORK"),
            "distillation_fails_g2": ("NO_TRAIN__QUANTIZE",
                                      "S7_QUANTIZATION_UNTRIED"),
        }
        for label, (outcome, node) in cases.items():
            with self.subTest(case=label):
                result = diagnose(fixtures.SPREAD[label]["facts"], self.spec)
                self.assertEqual(result.outcome, outcome)
                self.assertEqual(result.node, node)
                self.assertEqual(result.verdict, "NO_TRAIN")

    def test_the_minting_half_of_each_of_those_three_still_trains(self):
        """The counterexample that makes the test above a diagnosis rather than a
        coincidence. Each of the three fact sets differs from a minting one by a
        single flipped fact; flip it back and the run trains."""
        for outcome in ("TRAIN__TABULAR_DEEP", "TRAIN__DISTILLATION"):
            with self.subTest(outcome=outcome):
                result = diagnose(fixtures.MINTING[outcome], self.spec)
                self.assertEqual(result.outcome, outcome)

    def test_the_routes_that_always_worked_still_reach_a_cheaper_answer(self):
        cases = {
            "distillation_fails_g4": "S6_SWAP_THE_MODEL",
            "retriever_fails_g3": "S3_BUILD_RAG",
            "prompt_not_exhausted": "S5_FEWSHOT_UNTRIED",
        }
        for label, node in cases.items():
            with self.subTest(case=label):
                result = diagnose(fixtures.SPREAD[label]["facts"], self.spec)
                self.assertEqual(result.node, node)

    def test_no_fact_set_in_the_suite_makes_the_walk_cycle(self):
        """Every fixture in every group, run for the one thing this class is about.

        The property test in tests/test_diagnosis_no_crash.py covers this far
        more widely over random draws. This is the cheap named version over the
        hand-written stories, so a reintroduced loop names the fixture it broke.
        """
        groups = {
            "minting": fixtures.MINTING,
            "reaching": fixtures.REACHING,
        }
        for group, cases in groups.items():
            for key, facts in cases.items():
                with self.subTest(case=f"{group}:{key}"):
                    diagnose(facts, self.spec)
        for label, case in fixtures.SPREAD.items():
            with self.subTest(case=f"spread:{label}"):
                diagnose(case["facts"], self.spec)

    def _on_fail_targets(self) -> set[str]:
        targets: set[str] = set()
        for gate in self.spec.gates.values():
            on_fail = gate["on_fail"]
            if "route" in on_fail:
                targets.add(on_fail["route"])
            targets.update((on_fail.get("route_by_class") or {}).values())
        return targets

    def _is_terminal(self, item) -> bool:
        outcome = item.get("outcome")
        if not isinstance(outcome, str):
            return False
        _, decl = self.spec.outcome_prefix(outcome)
        return bool(decl["terminal"])

    def test_a_stage_a_gate_routes_into_has_a_terminal_answer_above_its_proposal(self):
        """The weak, universal half. Necessary, and on its own not sufficient.

        For every stage some gate's `on_fail` sends a run into, there must be at
        least one terminal node ABOVE the first node in that stage carrying
        `propose:`. Without one, a failing gate lands in the stage, the first
        thing it meets proposes again, the sweep fails the same gate, and the
        walk cycles.

        What this does NOT prove is that the terminal node above the proposal is
        the one that answers the gate's own question - S8_TABULAR_ROWS_UNKNOWN is
        above every proposal in stage 8 and answers nothing about hyperparameter
        searches. The test below is the half that checks that, and the two are
        kept apart so neither is mistaken for the other.

        Derived from the spec, both halves: the target stages come out of the
        gates' own `on_fail`, and the node order comes out of the stage lists.
        """
        targets = self._on_fail_targets()
        self.assertTrue(targets, "no gate routes anywhere on failure; check the spec")

        for stage in sorted(targets):
            items = [i for i in self.spec.stages[stage] if "gate_ref" not in i]
            proposers = [n for n, i in enumerate(items) if "propose" in i]
            if not proposers:
                continue  # nothing here can restart the loop
            first_proposal = min(proposers)
            remedies = [
                items[n]["node"] for n in range(first_proposal) if self._is_terminal(items[n])
            ]
            self.assertTrue(
                remedies,
                f"{stage} is a gate's on_fail target and its first proposing node, "
                f"{items[first_proposal]['node']}, has no terminal node above it. A "
                "gate that fails into this stage will meet a proposal, propose the "
                "same method, fail the same gate and cycle. Put the remedy above "
                "the proposal.",
            )

    def test_the_node_that_answers_a_gate_row_sits_above_every_proposal_in_its_stage(self):
        """The sharp half, and the one a reordering trips.

        The four nodes added to close the looping routes each carry an
        `answers_gate_row:` field naming the gate and method class they exist to
        answer. That annotation is the fix written down, so it is what gets
        checked: the node must be terminal, must name a gate that really routes
        into its stage on failure, and must sit above EVERY proposing node in
        that stage.

        Move S8_TABULAR_DEEP_JUSTIFIED above S8_TABULAR_DEEP_NEEDS_HPARAM_SEARCH
        and the loop is back; this is the assertion that says so, by name.
        """
        annotated = {
            node_id: node
            for node_id, node in self.spec.node_index.items()
            if "answers_gate_row" in node
        }
        self.assertTrue(
            annotated,
            "no node claims to answer a gate row. The four remedies that closed "
            "the looping routes each carried `answers_gate_row:`; if none does "
            "now, either they are gone or the annotation was dropped, and this "
            "test has quietly stopped checking anything",
        )

        classes = self.spec.method_classes
        for node_id, node in sorted(annotated.items()):
            with self.subTest(node=node_id):
                claim = str(node["answers_gate_row"])
                gate_id, _, remainder = claim.partition("/")
                gate_id = gate_id.strip()
                klass = remainder.split(",")[0].strip()

                self.assertIn(
                    gate_id,
                    self.spec.gates,
                    f"{node_id} claims to answer {claim!r}, which names no gate",
                )
                self.assertIn(
                    klass,
                    classes | {"any"},
                    f"{node_id} claims to answer {claim!r}, which names no method class",
                )
                self.assertEqual(
                    self.spec.row_key(gate_id, klass),
                    klass,
                    f"{node_id} claims the {klass} row of {gate_id}, but that gate "
                    f"has no such row - it would be answered under "
                    f"{self.spec.row_key(gate_id, klass)!r}",
                )
                self.assertTrue(
                    self._is_terminal(node),
                    f"{node_id} answers a gate row but is not terminal, so a run "
                    "that reaches it carries on and can still meet the proposal",
                )

                stage = self.spec.node_stage[node_id]
                on_fail = self.spec.gates[gate_id]["on_fail"]
                routes_here = on_fail.get("route") == stage or stage in (
                    on_fail.get("route_by_class") or {}
                ).values()
                self.assertTrue(
                    routes_here,
                    f"{node_id} is in {stage} and answers {gate_id}, but {gate_id} "
                    f"does not route into {stage} on failure. One of the two is "
                    "wrong and a run failing that gate lands somewhere else",
                )

                items = [i for i in self.spec.stages[stage] if "gate_ref" not in i]
                order = [i["node"] for i in items]
                proposals = [i["node"] for i in items if "propose" in i]
                below = [p for p in proposals if order.index(p) < order.index(node_id)]
                self.assertEqual(
                    below,
                    [],
                    f"{node_id} answers {gate_id} / {klass} but sits BELOW "
                    f"{below} in {stage}. A run reaches the proposal first, the "
                    f"sweep fails {gate_id}, on_fail routes back into {stage}, the "
                    "proposal fires again and the walk cycles. That is the exact "
                    "defect this node was added to remove - the remedy has to be "
                    "above the proposal, not merely present in the stage.",
                )


if __name__ == "__main__":
    unittest.main()
