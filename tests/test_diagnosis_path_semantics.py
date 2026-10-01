"""TEST 3. The path the loader produces is the path the contract describes.

`contract.path_semantics` is the single definition of the audit trail, and the
spec file says so in as many words: if ROADMAP, ARCHITECTURE or any other
document describes `path` differently, that document is stale and the YAML wins
- including where a roadmap milestone claims to specify the shape the
implementation will use. ROADMAP M4 does exactly that, and this test is the
mechanical form of that ruling.

Two incompatible definitions of the audit trail is how you ship an invariant
test that checks a structure the engine does not produce. So these assertions
read the shape out of `contract.path_semantics` and check the engine against it,
rather than restating the shape in Python and checking the engine against a
third copy.

Covers RC2, RC3, RC4, RC6 and RC7 from the spec's own `runtime_checks`.
"""

from __future__ import annotations

import re
import unittest
from dataclasses import fields

import diagnosis_fixtures as fixtures

from app.diagnosis import PathEntry, default_spec, diagnose, gates_passed_under


def all_results(spec):
    """Every fixture in the suite, so the shape checks run over real spread.

    All three groups. REACHING was added when the reachability check was widened
    past TRAIN__ outcomes, and it carries the only runs that reach a good part of
    stages 0, 3, 4 and 8 - so leaving it out here would mean the audit-trail
    shape was checked on the outcomes somebody happened to write a story for
    first.
    """
    for outcome, facts in fixtures.MINTING.items():
        yield f"minting:{outcome}", diagnose(facts, spec)
    for label, case in fixtures.SPREAD.items():
        yield f"spread:{label}", diagnose(case["facts"], spec)
    for outcome, facts in fixtures.REACHING.items():
        yield f"reaching:{outcome}", diagnose(facts, spec)


class PathSemanticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = default_spec()
        cls.semantics = cls.spec.contract["path_semantics"]
        cls.results = list(all_results(cls.spec))
        # A node id is real if a stage declares it or a gate names it. Gate nodes
        # (S0_NO_EVAL_SET, S1_UNMEASURED, ...) live in the `gates:` block and
        # appear in a stage only as a `gate_ref`, so both sources are needed.
        cls.known_nodes = set(cls.spec.node_index) | {
            g["node"] for g in cls.spec.gates.values()
        }

    # -- the declared shape ------------------------------------------------
    def test_the_entry_has_exactly_the_fields_the_contract_declares(self):
        declared = set(self.semantics["PathEntry"])
        produced = {f.name for f in fields(PathEntry)}
        self.assertEqual(
            produced,
            declared,
            "PathEntry and contract.path_semantics.PathEntry have drifted apart",
        )

    def test_path_is_a_list_of_records_and_not_a_list_of_strings(self):
        """Finding 4, in one assertion.

        A bare-string path cannot carry which `passes_when` row a gate was
        passed under, and without that the gate check is forgeable. The spec
        tried strings and says so.
        """
        self.assertIn("list[PathEntry]", self.semantics["type"])
        for label, result in self.results:
            with self.subTest(case=label):
                self.assertTrue(result.path, "a run produced an empty audit trail")
                for entry in result.path:
                    self.assertIsInstance(entry, PathEntry)
                    self.assertNotIsInstance(entry, str)

    def test_every_entry_is_well_formed(self):
        """RC6, with the enums read out of the file rather than typed in here.

        THE NODE CLAUSE ASSERTION WAS `assertIsNone` AND IS NOW AN EQUALITY.
        `clause` used to be a gate-only field; it now carries, on a node entry,
        that node's own `condition:` verbatim, because a run that stops above the
        gate tree - which is the common early outcome - put no clause on the wire
        at all and a surface deriving its question from one had nothing to read.
        Re-pinned rather than relaxed: the old test said the field was empty, and
        the honest replacement says exactly what is in it and where it came from,
        which is a stricter claim than "it is null" was.
        """
        kinds = set(self.semantics["PathEntry"]["kind"]["enum"])
        rows = {decl["class"] for decl in self.spec.methods.values()} | {"any"}
        node_re = re.compile(r"^S[0-9]+_")
        gate_re = re.compile(r"^G[0-9]_")
        # A gate's own node lives in the `gates:` block, not in a stage, and has
        # no `condition:` of its own - so it is the one node entry that keeps a
        # null clause. Derived from the spec, never listed here.
        gate_nodes = {g["node"] for g in self.spec.gates.values()}

        for label, result in self.results:
            with self.subTest(case=label):
                for entry in result.path:
                    self.assertIn(entry.kind, kinds)
                    if entry.kind == "node":
                        self.assertRegex(entry.id, node_re)
                        self.assertIsNone(entry.row)
                        self.assertTrue(
                            entry.id in self.known_nodes,
                            f"{entry.id} is not a node the spec declares",
                        )
                        declared = self.spec.node_index.get(entry.id)
                        if declared is None:
                            self.assertIn(
                                entry.id,
                                gate_nodes,
                                f"{entry.id} is in no stage and is no gate's node",
                            )
                            self.assertIsNone(
                                entry.clause,
                                f"{entry.id} has no condition of its own; a clause "
                                "on it would be the engine inventing one",
                            )
                        else:
                            self.assertEqual(
                                entry.clause,
                                " ".join(str(declared["condition"]).split()),
                                f"{entry.id} carries a clause that is not its own "
                                "`condition:` from docs/diagnosis_engine.yaml",
                            )
                    else:
                        self.assertRegex(entry.id, gate_re)
                        self.assertIn(entry.id, self.spec.gates)
                        self.assertIn(entry.row, rows)
                        self.assertTrue(entry.clause)

    # -- the ordering rule, which is what makes the check unforgeable ------
    def test_a_gate_entry_is_always_preceded_by_its_own_node(self):
        """RC2. Iterate POSITIONS - a gate may legitimately appear twice now, so
        list.index() would check only the first occurrence and miss a forged
        second one. This is what stops a gate entry being written by anything
        other than the gate."""
        for label, result in self.results:
            with self.subTest(case=label):
                for i, entry in enumerate(result.path):
                    if entry.kind != "gate":
                        continue
                    self.assertGreater(i, 0, f"{entry.id} is the first entry in the path")
                    before = result.path[i - 1]
                    self.assertEqual(before.kind, "node")
                    self.assertEqual(
                        before.id,
                        self.spec.gates[entry.id]["node"],
                        f"{entry.id} at position {i} does not follow its own node",
                    )

    def test_every_gate_entry_names_a_row_that_exists_in_the_file(self):
        """RC7. A ledger the UI renders from must not be able to name a question
        the engine never asks."""
        for label, result in self.results:
            with self.subTest(case=label):
                for entry in result.path:
                    if entry.kind != "gate":
                        continue
                    rows = self.spec.gates[entry.id]["passes_when"]
                    match = [
                        r
                        for r in rows
                        if r["method_class"] == entry.row and r["requires"] == entry.clause
                    ]
                    self.assertEqual(
                        len(match),
                        1,
                        f"{entry.id} claims row {entry.row!r} / clause "
                        f"{entry.clause!r}, which is not in the file",
                    )

    def test_the_row_recorded_is_the_row_key_for_the_class_in_force(self):
        """A gate entry's row must be a row_key, never an arbitrary row name."""
        for label, result in self.results:
            with self.subTest(case=label):
                for entry in result.path:
                    if entry.kind != "gate":
                        continue
                    possible = {
                        self.spec.row_key(entry.id, decl["class"])
                        for decl in self.spec.methods.values()
                    }
                    self.assertIn(entry.row, possible)

    # -- append-only, in evaluation order, never sorted, never deduplicated -
    def test_the_path_is_append_only_and_never_deduplicated(self):
        """The retriever run passes G3 twice under two different rows and keeps
        both, because the second entry is the evidence that the second question
        was actually asked."""
        result = diagnose(fixtures.MINTING["TRAIN__EMBEDDING_FINETUNE"], self.spec)
        g3_positions = [
            i
            for i, e in enumerate(result.path)
            if e.kind == "gate" and e.id == "G3_RETRIEVAL_CONSIDERED"
        ]
        self.assertEqual(len(g3_positions), 2)
        self.assertLess(g3_positions[0], g3_positions[1])
        self.assertEqual(result.path[g3_positions[0]].row, "llm_weights")
        self.assertEqual(result.path[g3_positions[1]].row, "retriever_weights")

    def test_the_path_is_in_evaluation_order_and_not_sorted(self):
        for label, result in self.results:
            with self.subTest(case=label):
                ids = [e.id for e in result.path]
                self.assertEqual(ids[0], "S0_RULES_SUFFICE", "every run starts at the entry node")
                if len(set(ids)) > 2:
                    self.assertNotEqual(ids, sorted(ids), "the path looks sorted")

    def test_a_failing_gate_writes_no_gate_entry(self):
        """A failed gate and a TRAIN verdict can never coexist in one run."""
        for label, result in self.results:
            with self.subTest(case=label):
                failed = {
                    g for g, e in result.gate_ledger.items() if e["status"] == "FAILED"
                }
                klass = self.spec.method_class(result.proposed_method)
                passed = gates_passed_under(result.path, klass, self.spec)
                self.assertEqual(failed & passed, set())
                if failed:
                    self.assertNotEqual(result.verdict, "TRAIN")

    # -- the ledger is a view over the path, not a second source of truth --
    def test_the_ledger_is_derived_from_the_path(self):
        """RC4, and the statuses the contract allows and no others."""
        allowed = {"PASSED", "FAILED", "NOT_REACHED"}
        for label, result in self.results:
            with self.subTest(case=label):
                self.assertEqual(
                    sorted(result.gate_ledger), sorted(self.spec.required_gates)
                )
                klass = self.spec.method_class(result.proposed_method)
                passed = gates_passed_under(result.path, klass, self.spec)
                for gate_id, entry in result.gate_ledger.items():
                    self.assertIn(entry["status"], allowed)
                    self.assertEqual(entry["status"] == "PASSED", gate_id in passed)
                    self.assertEqual(entry["node"], self.spec.gates[gate_id]["node"])

    def test_a_train_verdict_ends_at_the_mint(self):
        """RC3."""
        for label, result in self.results:
            if result.verdict != "TRAIN":
                continue
            with self.subTest(case=label):
                self.assertEqual(result.path[-1].id, "S9_MINT_TRAIN_VERDICT")
                self.assertEqual(result.path[-1].kind, "node")


if __name__ == "__main__":
    unittest.main()
