"""The loader fails loudly on a malformed spec instead of degrading.

Degrading is the failure mode that matters here. A loader that skips what it
cannot parse produces an engine that walks a smaller tree than the file
describes, reports success, and is wrong in a way no test notices - which is
close to how four training outcomes came to be dead while the file claimed all
nine were gated. So every check below asserts a RAISE, and each one is a real
way the file could go wrong.

The last class checks the other direction: a fact dict cannot smuggle in a
decision. The product will let a user's own model FILL facts. It must never let
one DECIDE a gate, and that is enforced by construction rather than by review.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.diagnosis import (
    CURRENT_LEDGER_FORMAT,
    SPEC_PATH,
    FactError,
    SpecError,
    default_spec,
    diagnose,
    load_spec,
    validate_facts,
)

import diagnosis_fixtures as fixtures


class SpecLoadsTest(unittest.TestCase):
    def test_the_repo_spec_loads_and_validates(self):
        spec = load_spec(SPEC_PATH)
        # TWO VERSIONS NOW, AND THEY ARE OWNED BY DIFFERENT PEOPLE. This used to
        # assert `spec.raw["version"]` is an int, which was the whole of the
        # scheme: one field, read twice, both `isinstance(int)`, no consequence
        # either way. `ledger_format` is the GRAMMAR and the engine owns it;
        # `ledger_version` is the KNOWLEDGE and the author owns it.
        self.assertEqual(spec.raw["ledger_format"], CURRENT_LEDGER_FORMAT)
        self.assertEqual(spec.ledger_format, CURRENT_LEDGER_FORMAT)
        self.assertIsInstance(spec.raw["ledger_version"], int)

        # AND THE STAGE NAMES COME OUT OF THE FILE. The two lines this replaces
        # asserted `"stage_0_admissibility" in spec.stages` and the same for
        # stage 9 - which is the defect, not the property. The engine held both
        # names as Python constants and no second ledger could satisfy them. What
        # is actually required is that the ledger NAMES its entry and its commit
        # stages and that the names resolve.
        self.assertIn(spec.roles.entry_stage, spec.stages)
        self.assertEqual(spec.roles.entry_stage, "stage_0_admissibility")
        self.assertEqual(spec.roles.commit_stages, ("stage_9_method_selector",))
        for stage in spec.roles.commit_stages:
            self.assertIn(stage, spec.stages)
        self.assertEqual(spec.gated_prefix, "TRAIN__")
        self.assertEqual(spec.mint_node, "S9_MINT_TRAIN_VERDICT")
        self.assertEqual(spec.no_proposal, "UNSET")
        self.assertEqual(len(spec.required_gates), 5)

    def test_every_node_in_every_stage_is_executable(self):
        """Not "parses" - executable. A node with no outcome, no route, no
        proposal and no handler would be silently skipped by the walker, and a
        silently skipped node looks exactly like coverage."""
        spec = default_spec()
        self.assertGreater(len(spec.node_index), 50)
        for node_id in spec.node_index:
            with self.subTest(node=node_id):
                self.assertIn(node_id, spec.node_stage)

    def test_every_condition_in_the_file_compiles(self):
        spec = default_spec()
        conditions = {
            node_id: node["condition"]
            for node_id, node in spec.node_index.items()
            if node.get("condition") not in (None, "always")
        }
        self.assertGreater(len(conditions), 40)
        for gate_id, gate in spec.gates.items():
            for row in gate["passes_when"]:
                self.assertIn((gate_id, row["method_class"]), spec.gate_conditions)


class MalformedSpecTest(unittest.TestCase):
    """Each case edits the real file and asserts the loader refuses it."""

    def setUp(self) -> None:
        self.text = SPEC_PATH.read_text(encoding="utf-8")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def load_with(self, old: str, new: str) -> None:
        self.assertIn(old, self.text, "the fragment this test edits is no longer in the file")
        path = Path(self.tmp.name) / "spec.yaml"
        path.write_text(self.text.replace(old, new, 1), encoding="utf-8")
        return load_spec(path)

    def test_a_condition_naming_an_undeclared_fact_is_refused(self):
        with self.assertRaises(SpecError) as caught:
            self.load_with(
                'condition: "not model_swap_tried"',
                'condition: "not model_swap_attempted"',
            )
        self.assertIn("model_swap_attempted", str(caught.exception))

    def test_a_second_node_minting_a_train_outcome_is_refused(self):
        with self.assertRaises(SpecError) as caught:
            self.load_with(
                "    outcome: NO_TRAIN__SWAP_MODEL",
                "    outcome: TRAIN__LORA_SFT",
            )
        self.assertIn("SC1", str(caught.exception))

    def test_a_proposal_that_does_not_route_to_stage_nine_is_refused(self):
        with self.assertRaises(SpecError) as caught:
            self.load_with(
                "    propose: DISTILLATION\n    route: stage_9_method_selector",
                "    propose: DISTILLATION",
            )
        self.assertIn("SC2", str(caught.exception))

    def test_a_condition_comparing_required_rank_to_a_number_is_refused(self):
        """The exact defect that made TRAIN__FULL_FINETUNE unreachable: the
        condition read `required_rank > 256` while every rank cell in the table
        was a string like "64-256", so it could never be true."""
        with self.assertRaises(SpecError) as caught:
            self.load_with(
                'condition: "proposed_method in {UNSET, LORA_SFT, FULL_FINETUNE} and labeled_examples_n > 50000',
                'condition: "required_rank > 256 and labeled_examples_n > 50000',
            )
        self.assertIn("SC4", str(caught.exception))

    def test_a_gate_row_for_an_unknown_method_class_is_refused(self):
        with self.assertRaises(SpecError) as caught:
            self.load_with(
                "{method_class: classical_deep,    requires: \"hparam_search_trials >= 50\"}",
                "{method_class: tabular_things,    requires: \"hparam_search_trials >= 50\"}",
            )
        self.assertIn("tabular_things", str(caught.exception))

    def test_a_method_with_no_row_in_a_gate_is_refused(self):
        """SC3. A new method whose class no gate has a row for has no question
        to answer, and the engine must crash rather than wave it through. This
        is the whole reason ERROR__UNCLASSIFIED_METHOD exists."""
        with self.assertRaises(SpecError) as caught:
            self.load_with(
                "  TABULAR_DEEP:           {class: classical_deep}",
                "  TABULAR_DEEP:           {class: classical_deep}\n"
                "  MOE_UPCYCLE:            {class: moe_weights}",
            )
        message = str(caught.exception)
        self.assertIn("SC3", message)
        self.assertIn("MOE_UPCYCLE", message)

    def test_an_effect_with_no_handler_is_refused(self):
        with self.assertRaises(SpecError) as caught:
            self.load_with(
                "  - node: S5_BETTER_PROMPT\n    condition: \"prompt_iterations < 3\"\n    outcome: NO_TRAIN__BETTER_PROMPT",
                "  - node: S5_BETTER_PROMPT\n    condition: \"prompt_iterations < 3\"\n    effect: \"do something the engine has never heard of\"",
            )
        message = str(caught.exception)
        self.assertIn("S5_BETTER_PROMPT", message)

    def test_a_route_to_a_stage_that_does_not_exist_is_refused(self):
        with self.assertRaises(SpecError) as caught:
            self.load_with("route: stage_7_efficiency", "route: stage_7_efficency")
        self.assertIn("stage_7_efficency", str(caught.exception))

    def test_an_outcome_with_no_declared_prefix_is_refused(self):
        with self.assertRaises(SpecError) as caught:
            self.load_with("outcome: NO_TRAIN__QUANTIZE", "outcome: MAYBE_QUANTIZE")
        self.assertIn("MAYBE_QUANTIZE", str(caught.exception))

    def test_emits_and_the_method_vocabulary_must_agree(self):
        with self.assertRaises(SpecError) as caught:
            self.load_with("            TRAIN__EMBEDDING_FINETUNE, TRAIN__TABULAR_DEEP]", "            TRAIN__TABULAR_DEEP]")
        self.assertIn("TRAIN__EMBEDDING_FINETUNE", str(caught.exception))

    def test_a_missing_top_level_key_is_refused(self):
        path = Path(self.tmp.name) / "tiny.yaml"
        path.write_text("version: 2\n", encoding="utf-8")
        with self.assertRaises(SpecError):
            load_spec(path)


class FactsCannotDecideTest(unittest.TestCase):
    """Filling a fact is upstream. Deciding a gate is here, and it is not pluggable."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = default_spec()

    def test_a_callable_fact_is_refused(self):
        facts = dict(fixtures.MINTING["TRAIN__LORA_SFT"])
        facts["model_swap_tried"] = lambda: True
        with self.assertRaises(FactError) as caught:
            diagnose(facts, self.spec)
        self.assertIn("decide a gate", str(caught.exception))

    def test_an_undeclared_fact_is_refused(self):
        facts = dict(fixtures.MINTING["TRAIN__LORA_SFT"])
        facts["gates_are_fine_actually"] = True
        with self.assertRaises(FactError):
            diagnose(facts, self.spec)

    def test_a_value_outside_a_declared_enum_is_refused(self):
        facts = dict(fixtures.MINTING["TRAIN__LORA_SFT"])
        facts["modality"] = "interpretive_dance"
        with self.assertRaises(FactError):
            diagnose(facts, self.spec)

    def test_a_wrongly_typed_fact_is_refused(self):
        facts = dict(fixtures.MINTING["TRAIN__LORA_SFT"])
        facts["eval_size_n"] = "lots"
        with self.assertRaises(FactError):
            diagnose(facts, self.spec)

    def test_declared_defaults_are_applied(self):
        resolved = validate_facts({"modality": "text"}, self.spec)
        self.assertEqual(resolved["eval_size_n"], 0)
        self.assertEqual(resolved["retrieval_tried"], False)
        self.assertIsNone(resolved["baseline_score"])


class ABlankFieldMeansTheSameAsAMissingFieldTest(unittest.TestCase):
    """Both defects here were found by the property test, not by reading the code.

    A caller has two ways to say "I do not know this": leave the key out, or send
    the key with a null. An intake form with a blank field sends the second. They
    used to be different: omitting a fact applied its declared default, and
    passing null skipped straight past it. One of the two raised.

    Named here as well as covered by the fuzzer, because a defect whose only
    record is one draw out of a quarter of a million is a defect nobody can find
    again from the test name.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = default_spec()
        # Attributed, because the subject here is null-versus-absent and nothing
        # else. Left bare, every value would be an ASSERTED value, G0 would
        # refuse the claimed eval set, and both runs below would stop at
        # ACTION__SUBSTANTIATE_CLAIMED_FACTS - agreeing with each other for a
        # reason that has nothing to do with the defect this class is named for.
        # A test that passes for the wrong reason is the failure mode this whole
        # file was written against.
        cls.text = fixtures.attribute(
            {
                "modality": "text",
                "task_family": "generation",
                "eval_size_n": 100,
                "target_score": 0.85,
                "privacy": "public_ok",
                "needs_citations": False,
                "baseline_measured": True,
                "baseline_score": 0.55,
                "trivial_baseline_score": 0.20,
                "data_quality": 0.9,
            }
        )

    def test_a_null_fact_resolves_through_its_declared_default(self):
        resolved = validate_facts({"modality": "text", "eval_size_n": None}, self.spec)
        self.assertEqual(resolved["eval_size_n"], 0)
        self.assertEqual(resolved["failure_histogram"], {})

    def test_a_null_failure_histogram_answers_instead_of_raising(self):
        """The crash itself. `sum(failure_histogram.values())` against a null is
        not a false answer, it is a stack trace - and S1_GAP_UNDIAGNOSED is
        exactly the node that should have caught this user and told them to go
        bucket their failures."""
        omitted = diagnose(self.text, self.spec)
        blank = diagnose(dict(self.text, failure_histogram=None), self.spec)
        self.assertEqual(blank.outcome, "ACTION__CLASSIFY_FAILURES")
        self.assertEqual(blank.outcome, omitted.outcome)
        self.assertEqual(blank.node, omitted.node)

    def test_a_null_hardware_fact_is_not_a_measured_number(self):
        """Invariant 3, through the other door. A verdict computed from a
        hardware number the caller does not have must not look on screen like one
        computed from a measured GPU - and `vram_gb: null` is a number the caller
        does not have."""
        measured = diagnose(fixtures.MINTING["TRAIN__LORA_SFT"], self.spec)
        self.assertEqual(measured.cost_provenance, "MEASURED")

        blank = diagnose(
            dict(fixtures.MINTING["TRAIN__LORA_SFT"], vram_gb=None), self.spec
        )
        self.assertEqual(blank.cost_provenance, "UNKNOWN")

    def test_a_run_cannot_mutate_the_default_the_spec_holds(self):
        """The spec is cached for the life of the process, so a default handed
        out by reference is a default one run could change for every run after
        it - and no single test would see it."""
        first = validate_facts({"modality": "text"}, self.spec)
        first["failure_histogram"]["wrong_style"] = 99
        second = validate_facts({"modality": "text"}, self.spec)
        self.assertEqual(second["failure_histogram"], {})
        self.assertEqual(self.spec.facts["failure_histogram"]["default"], {})

    def test_a_contains_test_names_an_enum_member_not_a_fact(self):
        """`need_type contains privacy` must ask about the need_type member
        called privacy, not about the value of the `privacy` fact. They collide
        by name and only one of them is the question being asked."""
        facts = dict(fixtures.MINTING["TRAIN__DISTILLATION"])
        facts["need_type"] = ["privacy"]
        facts["privacy"] = "public_ok"
        result = diagnose(facts, self.spec)
        self.assertIn("S1_QUALITY_PASSES_BUT_CONSTRAINED", result.path_ids())


if __name__ == "__main__":
    unittest.main()
