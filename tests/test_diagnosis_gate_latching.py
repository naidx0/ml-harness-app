"""TEST 2. No gate is skipped across a method-class change.

The bypass, in one paragraph. A gate used to be latched per RUN: evaluated at
most once, skipped whenever its id was already in `path`. The justification was
that facts are immutable for the duration of one diagnose() call, so
re-evaluating could not change the answer. Facts are immutable. THE ROW IS NOT.
G2 and G3 ask a different question of each method class, so the same immutable
facts give different answers under different rows, and the justification was
simply false.

The concrete hole: walk down the LLM spine, pass G3 on `retrieval_tried` alone,
then propose EMBEDDING_FINETUNE - whose class is retriever_weights, whose G3 row
is `retrieval_tried and reranker_tried`. Under the old rule G3 was already in
`path`, so it was skipped, and the reranker question was never asked. A
recommendation to train a retriever, issued without anyone checking whether an
off-the-shelf reranker fixed it. That is the exact shape these gates exist to
prevent.

It was latent only by luck - the one node proposing EMBEDDING_FINETUNE happened
to also require reranker_tried in its own condition, and that node was itself
dead. Luck is not a mechanism. Four assertions here, from the general property
down to the specific run:

  1. row_key really does differ between classes, so there is something to skip.
  2. gates_passed_under does not count a gate passed under another class's row.
  3. the sweep RE-EVALUATES rather than skips, and a proposal that cannot answer
     the stricter row is stopped by it.
  4. the real retriever run ends up with TWO G3 entries in `path`.
"""

from __future__ import annotations

import unittest

import diagnosis_fixtures as fixtures

from app.diagnosis import (
    PathEntry,
    _State,
    _gate_sweep,
    default_spec,
    diagnose,
    gates_passed_under,
    resolve_facts,
)


class GateLatchingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = default_spec()

    # -- 1. the rows really do differ -------------------------------------
    def test_some_gate_asks_a_different_question_of_a_different_class(self):
        """If no gate's row varied by class there would be no bypass to close."""
        varying = []
        for gate_id in self.spec.required_gates:
            keys = {
                self.spec.row_key(gate_id, decl["class"])
                for decl in self.spec.methods.values()
            }
            if len(keys) > 1:
                varying.append(gate_id)
        self.assertIn(
            "G3_RETRIEVAL_CONSIDERED",
            varying,
            "G3 no longer varies by method class; the bypass this test guards "
            "has either been designed away or accidentally flattened",
        )

    def test_the_retriever_row_is_strictly_stronger_than_the_llm_row(self):
        """The spec's `row_strength` claim, checked against the rows themselves."""
        gate = self.spec.gates["G3_RETRIEVAL_CONSIDERED"]
        rows = {row["method_class"]: row["requires"] for row in gate["passes_when"]}
        self.assertIn("retrieval_tried", rows["llm_weights"])
        self.assertNotIn("reranker_tried", rows["llm_weights"])
        self.assertIn("reranker_tried", rows["retriever_weights"])

    # -- 2. the set function does not launder a gate across classes -------
    def test_a_gate_passed_under_one_class_does_not_count_for_another(self):
        path = [
            PathEntry("S3_RETRIEVAL_NOT_CONSIDERED", "node"),
            PathEntry(
                "G3_RETRIEVAL_CONSIDERED", "gate", row="llm_weights", clause="retrieval_tried"
            ),
        ]
        self.assertEqual(
            gates_passed_under(path, "llm_weights", self.spec),
            {"G3_RETRIEVAL_CONSIDERED"},
        )
        self.assertEqual(
            gates_passed_under(path, "retriever_weights", self.spec),
            set(),
            "a G3 passed under llm_weights was counted as a G3 passed for a "
            "retriever proposal; that is the bypass",
        )

    def test_every_gate_and_class_pair_agrees_with_row_key(self):
        """The general property, over the whole cross-product in the file."""
        for gate_id in self.spec.required_gates:
            for method, decl in self.spec.methods.items():
                klass = decl["class"]
                with self.subTest(gate=gate_id, method=method):
                    row_key = self.spec.row_key(gate_id, klass)
                    path = [PathEntry(gate_id, "gate", row=row_key, clause="x")]
                    self.assertIn(gate_id, gates_passed_under(path, klass, self.spec))
                    for other in self.spec.methods.values():
                        other_key = self.spec.row_key(gate_id, other["class"])
                        if other_key == row_key:
                            continue
                        self.assertNotIn(
                            gate_id,
                            gates_passed_under(path, other["class"], self.spec),
                            f"{gate_id} passed under {row_key} was counted for "
                            f"class {other['class']}, whose row is {other_key}",
                        )

    # -- 3. the sweep re-evaluates, and the re-evaluation can say no ------
    def _swept(self, facts: dict, method: str) -> tuple:
        """Run the sweep alone, over a path that already holds G3 under llm_weights.

        Constructed rather than walked to, and deliberately so. A real run
        cannot arrive at either of these states today: the node proposing
        EMBEDDING_FINETUNE happens to require reranker_tried in its own
        condition, and a tabular run forks away at stage 0 before it can touch
        the LLM spine. That is precisely why the bypass was LATENT rather than
        live - it was closed by luck, by a coincidence between one node's
        condition and one gate's row, not by anything structural. One condition
        edit upstream turns it live, and these assertions are what stop that
        edit shipping.
        """
        values, origins = resolve_facts(facts, self.spec)
        state = _State(spec=self.spec, facts=values, origins=origins)
        state.proposed_method = method
        state.path.extend(
            [
                PathEntry("S3_RETRIEVAL_NOT_CONSIDERED", "node"),
                PathEntry(
                    "G3_RETRIEVAL_CONSIDERED",
                    "gate",
                    row="llm_weights",
                    clause="retrieval_tried",
                ),
            ]
        )
        result = _gate_sweep(state, self.spec.node_index["S9_GATE_SWEEP"])
        return state, result

    def test_the_sweep_re_asks_g3_when_the_applicable_row_changed(self):
        """A G3 in `path` under llm_weights must not answer G3 for another class.

        classical_deep is the class that isolates this. Its G3 row asks about
        feature work and its G2 row asks about a hyperparameter search - two
        unrelated questions - so G3 can be failed while G2 passes. Under the old
        skip-if-present rule this run sails through: G3 is already in `path`, so
        "was the missing signal looked for in the features first" is never
        asked, and a neural net is recommended over a join.
        """
        facts = dict(fixtures.MINTING["TRAIN__TABULAR_DEEP"])
        facts["feature_work_considered"] = False
        state, result = self._swept(facts, "TABULAR_DEEP")

        self.assertIsNotNone(
            result,
            "the sweep skipped G3 because a G3 was already in `path` under the "
            "llm_weights row. That is the bypass.",
        )
        self.assertEqual(
            state.failed_gates.get("G3_RETRIEVAL_CONSIDERED"),
            "classical_deep",
            "G3 was not re-evaluated under the proposal's own row",
        )
        # And it did not quietly count the llm_weights entry as a pass.
        self.assertNotIn(
            "G3_RETRIEVAL_CONSIDERED",
            gates_passed_under(state.path, "classical_deep", self.spec),
        )

    def test_the_sweep_re_asks_the_retriever_questions_too(self):
        """The same, on the class the bypass was actually written about.

        G3's retriever row is a subset of G2's retriever row, so a retriever
        proposal that cannot answer the reranker question is stopped at G2
        first. Either way the point holds and is asserted: the sweep asked the
        retriever_weights questions rather than treating the llm_weights G3 as
        having covered them.
        """
        facts = dict(fixtures.MINTING["TRAIN__EMBEDDING_FINETUNE"])
        facts["reranker_tried"] = False
        state, result = self._swept(facts, "EMBEDDING_FINETUNE")

        self.assertIsNotNone(result, "the sweep waved a retriever proposal through")
        self.assertEqual(result.stage, "stage_3_knowledge")
        self.assertEqual(
            state.failed_gates,
            {"G2_PROMPT_EXHAUSTED": "retriever_weights"},
            "the sweep did not stop on a retriever_weights row",
        )

    def test_the_sweep_does_skip_a_gate_whose_row_has_not_changed(self):
        """Latching is per row, not off. G0 is `any` for every class, so once
        passed it is never asked twice - and the path must not grow a second
        entry pretending otherwise."""
        facts = fixtures.MINTING["TRAIN__EMBEDDING_FINETUNE"]
        result = diagnose(facts, self.spec)
        g0_entries = [e for e in result.path if e.kind == "gate" and e.id == "G0_EVAL_SET"]
        self.assertEqual(len(g0_entries), 1)
        self.assertEqual(g0_entries[0].row, "any")

    # -- 4. the real run, end to end --------------------------------------
    def test_the_retriever_run_carries_two_g3_entries(self):
        """The spec calls this fixture 'not optional', and it is right.

        It is the only test that shows the bypass is closed rather than merely
        described: one G3 from the walk down the LLM spine, one from the sweep
        under the retriever row, both kept, because the second entry is the
        evidence that the second question was actually asked.
        """
        result = diagnose(fixtures.MINTING["TRAIN__EMBEDDING_FINETUNE"], self.spec)
        self.assertEqual(result.outcome, "TRAIN__EMBEDDING_FINETUNE")

        g3 = [e for e in result.path if e.kind == "gate" and e.id == "G3_RETRIEVAL_CONSIDERED"]
        self.assertEqual(
            [e.row for e in g3],
            ["llm_weights", "retriever_weights"],
            "the retriever proposal was not re-asked the retriever question",
        )
        self.assertEqual(g3[0].clause, "retrieval_tried")
        self.assertEqual(g3[1].clause, "retrieval_tried and reranker_tried")

        # And the ledger reports the row that actually applies, not the first one seen.
        self.assertEqual(
            result.gate_ledger["G3_RETRIEVAL_CONSIDERED"]["row"], "retriever_weights"
        )

    def test_a_gate_never_passed_under_the_proposals_row_is_not_passed(self):
        """RC4, stated the way the spec states it: PASSED if and only if."""
        for outcome, facts in fixtures.MINTING.items():
            with self.subTest(outcome=outcome):
                result = diagnose(facts, self.spec)
                klass = self.spec.method_class(result.proposed_method)
                passed = gates_passed_under(result.path, klass, self.spec)
                for gate_id, entry in result.gate_ledger.items():
                    self.assertEqual(
                        entry["status"] == "PASSED",
                        gate_id in passed,
                        f"{gate_id} ledger status and path disagree",
                    )


if __name__ == "__main__":
    unittest.main()
