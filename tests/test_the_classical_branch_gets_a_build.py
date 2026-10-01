"""The tabular default stops being a homework assignment, and the five it is not.

`stage_8_classical` had twelve outcomes and no floor at all, and every one of
the six model-fitting ones carried the same sentence in `NOT_COVERED`: *fitting
a cheaper model, which this harness has no tool to fit.* One sentence answering
for six outcomes is the shape `_EVAL_BENCH`, `_RETRIEVAL_BENCH` and `_TRAINING`
were each caught in, and it goes false one outcome at a time while the product
goes on saying it about all of them.

`fit_a_tree_model` closes exactly ONE of the six. This file is about that one
and about the five it does not close, and the second half is the half worth
testing: a proposer pointed at all six would be the widened
`S8_TABULAR_STANDARD` bound that killed three outcomes in this very stage, made
again in the proposer instead of in the spec.

**WHAT IS CHECKED HERE THAT NOTHING ELSE CHECKS.**

1. **The exit criterion is derived and says so.** Neither node that emits this
   outcome declares one - read off the spec, not asserted - so the build states
   that, quotes G1's own `classical_deep` row as what it derived from, and says
   what the derivation is not.
2. **It is not held to the tree winning.** `comparison.separated` is the tool's
   word for that and it is deliberately not the subject of any criterion here.
3. **AND THE OBVIOUS CRITERION WOULD HAVE PASSED ON A REFUSAL.** The first draft
   held the step to `resolution` existing. `fit_a_tree_model` fills every key a
   scored run carries with the honest null on every refusal, `resolution`
   included, so that criterion is true of a run that fitted nothing. This is
   `check_split_leakage`'s `leaked_rows == 0` trap one bench over, and it is
   checked here against results the REAL TOOL produces rather than against a
   payload this file wrote.
4. **The row count the engine routed on is not the row count a tree learns
   from.** `tabular_rows` counts rows; a fit learns from rows carrying a LABEL,
   and nothing upstream compares the two. The proposer reads the column and
   refuses on what it finds.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import diagnosis_fixtures

from app import diagnosis
from app.tools import REGISTRY, propose

import support


class TabularBuildTestCase(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)

    def table(self, rows: int = 3000, labelled: int | None = None, name="table.csv") -> Path:
        """A table with `rows` rows, `labelled` of which carry a label.

        `size` REPEATS. It used to be the row index, which is a different whole
        number in every row - a counter, which is an identifier, which
        `fit_a_tree_model`'s check C now refuses in as many words. That refusal
        is correct and this fixture was wrong: a table whose first column is the
        export order is exactly the table that produces a perfect score off
        nothing, and two tests here need a REAL scored fit to check the
        criterion against.
        """
        labelled = rows if labelled is None else labelled
        path = self.root / name
        lines = ["size,region,label"]
        for index in range(rows):
            label = ("yes", "no", "maybe")[index % 3] if index < labelled else ""
            lines.append(f"{index % 97},{index % 7},{label}")
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def situation(self, **over) -> propose.Situation:
        """A situation for the tabular default, with the engine deciding.

        `SPREAD['tabular_default']` is the fact set that lands on
        `S8_TABULAR_STANDARD` and it is already asserted against that node
        there. What is bypassed is the ledger round trip, not the tree.
        """
        facts = over.pop("facts", {})
        sheet = dict(diagnosis_fixtures.SPREAD["tabular_default"]["facts"])
        sheet.update(facts)
        result = diagnosis.diagnose(sheet)
        self.assertEqual(result.outcome, "NO_DEEP__GRADIENT_BOOSTED_TREES")
        base = dict(
            outcome=result.outcome,
            result=result,
            values={n: getattr(v, "value", v) for n, v in sheet.items()},
            origins=dict(result.fact_origins),
            expected_field="label",
        )
        # THE DEFAULT TABLE IS ONLY WRITTEN WHEN NOBODY NAMED ONE, and even
        # `setdefault` was too eager: its second argument is evaluated whether
        # or not it is used, so it rewrote the caller's file - same default
        # name - and `self.refusal(dataset_path=str(self.table(labelled=400)))`
        # planned happily against a fully labelled table. The refusal under
        # test could not fire, and the test passed the day it was wrong.
        if "dataset_path" not in over:
            base["dataset_path"] = str(self.table())
        base.update(over)
        return propose.Situation(**base)

    def plan(self, **over):
        return propose.propose(self.situation(**over))

    def refusal(self, **over) -> propose.NotEnoughToPropose:
        with self.assertRaises(propose.NotEnoughToPropose) as raised:
            self.plan(**over)
        return raised.exception


# ---------------------------------------------------------------------------
# What the engine actually says, read rather than remembered.


class TheEngineIsReadAndNotQuotedFromMemoryTest(TabularBuildTestCase):
    def test_two_nodes_emit_this_outcome_and_the_constant_finds_both(self):
        """A third emitter turns this red rather than leaving a plan quoting one.

        The retrieval bench answered this question in a comment - *four nodes
        emit NO_TRAIN__RAG* - and a comment cannot go red.
        """
        self.assertEqual(
            propose.nodes_that_emit("NO_DEEP__GRADIENT_BOOSTED_TREES"),
            ("S8_TABULAR_STANDARD", "S8_TABULAR_UNMATCHED"),
        )

    def test_neither_emitting_node_declares_an_exit_criterion(self):
        """The premise the whole build's honesty rests on."""
        for node in propose.nodes_that_emit("NO_DEEP__GRADIENT_BOOSTED_TREES"):
            self.assertEqual(propose.engine_exit_criterion(node), "", node)
        # The positive control: the function finds a real one where there is one.
        self.assertIn(
            "retriever_recall_at_k", propose.engine_exit_criterion("S3_BUILD_RAG")
        )

    def test_the_floor_is_the_engines_number_and_not_this_files(self):
        self.assertEqual(propose.rows_a_tree_needs(), 1000)
        self.assertIn(
            "tabular_rows < 1000",
            propose.engine_node_says("S8_TABULAR_TINY", "condition"),
        )

    def test_the_libraries_are_the_engines_and_the_absence_is_looked_at(self):
        """The `method.libs` list is read; whether each is here is measured."""
        named = propose.libraries_the_engine_names("S8_TABULAR_STANDARD")
        self.assertEqual(named, ("LightGBM", "XGBoost", "CatBoost"))
        missing = propose.tree_libraries_missing("S8_TABULAR_STANDARD")
        for name in missing:
            self.assertIn(name, named)
            with self.assertRaises(ImportError):
                __import__(name.lower())

    def test_the_tree_fit_reads_the_same_library_list_this_file_does(self):
        """TWO MODULES ASK THE ENGINE THE SAME QUESTION, so they are pinned.

        `app/tools/classical.py` reads `S8_TABULAR_STANDARD.method.libs` for its
        own reply and `app/tools/propose.py` reads it for the plan. Neither
        imports the other - propose refusing to import a bench at module level
        is what lets it keep working when one is absent - so the two are pinned
        against each other here, exactly as `RESOLVED_AT` is pinned rather than
        imported. A divergence is two different sentences about the same
        machine in one conversation.
        """
        classical = REGISTRY.get(propose.THE_TREE_FIT)
        if classical is None:  # pragma: no cover - the tool is not registered here
            self.skipTest("fit_a_tree_model is not registered in this process")
        from app.tools import classical as bench

        self.assertEqual(
            tuple(bench.libraries_the_engine_names()),
            propose.libraries_the_engine_names("S8_TABULAR_STANDARD"),
        )

    def test_g1s_own_row_is_what_the_criterion_is_derived_from(self):
        said = propose.the_classical_baseline()
        self.assertIn("gradient-boosted tree", said)
        self.assertIn("TabPFN", said)

    def test_the_gate_rows_are_counted_rather_than_counted_on(self):
        """The sentence used to say "three gate rows" and one row reads it."""
        self.assertEqual(
            propose.gate_rows_reading("hparam_search_trials"),
            ("G2_PROMPT_EXHAUSTED / classical_deep",),
        )
        self.assertEqual(
            propose.gate_rows_reading("trivial_baseline_score"),
            ("G1_BASELINE_MEASURED / any",),
        )
        self.assertEqual(propose.gate_rows_reading("not_a_fact_at_all"), ())

    def test_the_gate_facts_this_module_derives_are_the_ones_the_spec_declares(self):
        """An independent derivation, because the module's own is load-bearing.

        `_propose_fit_the_tree` prints which of the fit's stamped facts a gate
        reads. If `gate_facts` quietly stopped matching the spec's spelling that
        sentence would go silently false, and the sentence is the whole reason
        the stamp is acceptable.
        """
        import re

        spec = diagnosis.default_spec()
        name = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
        found = set()
        for gate in spec.gates.values():
            for row in gate.get("passes_when") or ():
                for word in name.findall(str(row.get("requires") or "")):
                    if word in spec.facts:
                        found.add(word)
        self.assertTrue(found)
        self.assertEqual(propose.gate_facts(), frozenset(found))


# ---------------------------------------------------------------------------
# The refusals, and their order.


@unittest.skipUnless(
    propose.the_tabular_bench_is_registered(),
    "fit_a_tree_model is not registered in this process",
)
class ItRefusesAboutYourDataFirstTest(TabularBuildTestCase):
    """Guarded by the registry, because `propose` dispatches before it refuses.

    While `fit_a_tree_model` is absent the outcome is not in `PROPOSERS` at all
    and `propose()` returns the `NOT_COVERED` reason from the dispatcher, so
    the proposer's own refusals are unreachable rather than wrong. That state is
    checked by `TheTableSaysExactlyOneThingTest` below, which asserts whichever
    of the two is true - so neither the covered nor the uncovered case can pass
    by nobody looking.
    """

    def test_it_will_not_choose_the_target_column(self):
        gap = self.refusal(expected_field="")
        self.assertIn("expected_field", gap.needs)
        self.assertIn("definition of correct", gap.detail)

    def test_it_refuses_a_column_that_is_not_in_the_file_and_names_what_is(self):
        gap = self.refusal(expected_field="outcome")
        self.assertIn("expected_field", gap.needs)
        self.assertIn("'outcome'", gap.detail)
        self.assertIn("'label'", gap.detail)
        self.assertIn("'size'", gap.detail)

    def test_it_refuses_when_the_labelled_rows_are_under_the_engines_floor(self):
        """THE ROW COUNT THE ENGINE ROUTED ON IS NOT THE ROW COUNT A TREE LEARNS
        FROM, and this is the case no fact upstream can see.

        Five million `tabular_rows` on file - the fixture is a real
        `S8_TABULAR_STANDARD` run - and four hundred rows of the file actually
        carry a label. Every node in the stage is happy; the fit would be
        fitted on four hundred rows and report a number about them.
        """
        gap = self.refusal(dataset_path=str(self.table(rows=3000, labelled=400)))
        self.assertIn("400 of the 3000 rows read", gap.detail)
        self.assertIn("S8_TABULAR_TINY", gap.detail)
        # The engine's own answer below that floor, quoted rather than
        # paraphrased - so a reworded node changes the refusal instead of
        # leaving this file's summary of it standing.
        self.assertIn(propose.engine_node_says("S8_TABULAR_TINY", "say"), gap.detail)
        self.assertIn("5000000", gap.detail.replace(",", ""))

    def test_the_floor_refusal_is_about_labels_and_not_about_the_file_size(self):
        """The positive control: the same file, fully labelled, plans."""
        self.assertTrue(self.plan(dataset_path=str(self.table(rows=3000))).steps)

    def test_it_refuses_when_the_holdout_is_the_training_file(self):
        table = self.table()
        gap = self.refusal(dataset_path=str(table), eval_path=str(table))
        self.assertIn("dataset_path", gap.needs)
        self.assertIn("memorises", gap.detail)

    def test_it_refuses_when_a_measured_trivial_baseline_already_clears_the_bar(self):
        import dataclasses

        situation = self.situation()
        variant = dataclasses.replace(
            situation,
            values={
                **situation.values,
                "trivial_baseline_score": 0.9,
                "target_score": 0.8,
            },
            origins={**situation.origins, "trivial_baseline_score": diagnosis.MEASURED},
        )
        with self.assertRaises(propose.NotEnoughToPropose) as raised:
            propose.propose(variant)
        self.assertIn("already clears your bar", raised.exception.detail)

    def test_a_typed_trivial_baseline_does_not_trigger_that_refusal(self):
        """Two numbers from two instruments are two facts, not a comparison."""
        import dataclasses

        situation = self.situation()
        variant = dataclasses.replace(
            situation,
            values={
                **situation.values,
                "trivial_baseline_score": 0.9,
                "target_score": 0.8,
            },
            origins={**situation.origins, "trivial_baseline_score": diagnosis.STATED},
        )
        self.assertTrue(propose.propose(variant).steps)

    def test_the_question_about_our_harness_is_asked_last(self):
        """A person with four hundred labelled rows is told about their data.

        The order is the point and it is the order
        `_why_carving_is_not_honest_here` had to learn: a registry gap reads as
        *this will work once we ship it*, and "four hundred of your rows carry a
        label" does not stop being true the day a tool registers.
        """
        gap = self.refusal(dataset_path=str(self.table(rows=3000, labelled=400)))
        self.assertNotIn(propose.THE_TREE_FIT, gap.detail)


# ---------------------------------------------------------------------------
# The build.


@unittest.skipUnless(
    propose.the_tabular_bench_is_registered(),
    "fit_a_tree_model is not registered in this process",
)
class TheBuildIsAMeasurementAndNotAVictoryTest(TabularBuildTestCase):
    def test_it_is_one_step_and_it_is_the_fit(self):
        plan = self.plan()
        self.assertEqual(
            [(step.id, step.tool) for step in plan.steps],
            [("fit", propose.THE_TREE_FIT)],
        )

    def test_it_does_not_profile_the_dataset_first(self):
        """`profile_dataset` stamps eval_size_n, which is G0's fact.

        Stamping it with a count of the TRAINING table is a real measurement of
        the wrong file filed under the name a gate opens on.
        """
        plan = self.plan()
        for step in plan.steps:
            self.assertNotIn(
                "eval_size_n", REGISTRY.get(step.tool).measures, f"{step.id} stamps G0"
            )
        self.assertIn("profile_dataset", plan.because)

    def test_no_step_stamps_a_gate_fact_or_the_plan_says_which(self):
        """Read off `measures=` at proposal time, either way.

        The training build can assert "nothing here stamps a gate fact" because
        it checked. This build cannot promise that in advance - G1's own
        classical_deep row describes it as what a baseline IS - so what is
        checked is that the plan's sentence matches the registry.
        """
        plan = self.plan()
        stamped = set()
        for step in plan.steps:
            stamped |= set(REGISTRY.get(step.tool).measures)
        reads = sorted(stamped & propose.gate_facts())
        if reads:
            self.assertIn(str(reads), plan.because)
            self.assertIn("G1_BASELINE_MEASURED", plan.because)
        else:
            self.assertIn("measures=()", plan.because)

    def test_the_criterion_is_the_paired_test_and_not_the_tree_winning(self):
        plan = self.plan()
        step = plan.step("fit")
        self.assertEqual(step.exit_criterion.subject, "comparison.mcnemar_p")
        self.assertEqual(step.exit_criterion.comparator, "exists")
        for criterion in (step.exit_criterion, plan.exit_criterion):
            self.assertNotIn("separated", criterion.subject)
            self.assertNotIn("difference_points", criterion.subject)

    def test_the_criterion_says_the_engine_declared_none_and_what_it_derived_from(self):
        plan = self.plan()
        self.assertIn("DECLARES NO exit_criterion", plan.exit_criterion.stated)
        self.assertIn("G1_BASELINE_MEASURED", plan.exit_criterion.stated)
        self.assertIn(propose.the_classical_baseline(), plan.exit_criterion.stated)
        self.assertIn("WHAT THAT DERIVATION IS NOT", plan.exit_criterion.stated)

    def test_the_plan_says_the_engines_libraries_are_not_here(self):
        because = self.plan().because
        for name in propose.tree_libraries_missing("S8_TABULAR_STANDARD"):
            self.assertIn(name, because)
        self.assertIn("importlib", because)

    def test_the_plan_says_it_is_one_fit_and_not_the_fifty_trial_search(self):
        because = self.plan().because
        self.assertIn("50-trial random or optuna search", because)
        self.assertIn("ONE FIT", because)
        self.assertNotIn("hparam_search_trials", str(self.plan().questions))

    def test_it_asks_for_no_fact_a_gate_reads(self):
        for question in self.plan().questions:
            self.assertNotIn(question.fact, propose.gate_facts())

    def test_the_call_uses_the_tools_own_argument_names(self):
        arguments = self.plan().step("fit").arguments
        properties = set(REGISTRY.get(propose.THE_TREE_FIT).schema["properties"])
        self.assertTrue(set(arguments) <= properties)
        for required in REGISTRY.get(propose.THE_TREE_FIT).schema["required"]:
            self.assertIn(required, arguments)
        # The synonyms this file offered and the tool does not declare are gone.
        for spelling in ("dataset_path", "target", "label_column", "expected_field"):
            if spelling not in properties:
                self.assertNotIn(spelling, arguments)

    def test_a_named_holdout_is_passed_and_an_unnamed_one_is_not(self):
        holdout = self.table(rows=800, name="holdout.csv")
        with_it = self.plan(eval_path=str(holdout)).step("fit").arguments
        self.assertEqual(with_it.get("holdout_path"), str(holdout))
        self.assertNotIn("holdout_path", self.plan().step("fit").arguments)

    def test_it_chooses_none_of_the_things_that_are_the_persons(self):
        arguments = self.plan().step("fit").arguments
        for theirs in ("holdout_fraction", "seed", "max_rows", "feature_columns", "drop_columns"):
            self.assertNotIn(theirs, arguments)

    def test_the_costs_are_provable_zeros_and_honest_unknowns(self):
        from app import build

        cost = self.plan().step("fit").cost
        for zero in (cost.model_tokens, cost.model_requests):
            self.assertEqual(zero.value, 0.0)
            self.assertEqual(zero.provenance, build.INFERRED)
            self.assertIn("providers", zero.how)
        self.assertEqual(cost.wall_clock.provenance, build.UNKNOWN)
        self.assertTrue(cost.wall_clock.find_out_by)
        self.assertEqual(cost.disk.value, 0.0)


# ---------------------------------------------------------------------------
# The trap the first draft of this build walked into.


@unittest.skipUnless(
    propose.the_tabular_bench_is_registered(),
    "fit_a_tree_model is not registered in this process",
)
class TheCriterionSeparatesAFitFromARefusalTest(TabularBuildTestCase):
    """Driven through the REAL tool, because that is where the trap is.

    `fit_a_tree_model` fills every key a scored run carries with the honest null
    on every refusal - `resolution` included, as `evals.resolution_for(0, 0)` -
    so a criterion on `resolution` existing passes on a run that fitted nothing.
    `comparison` is None on a refusal and `None` is PRESENT to `_dig`, so that
    one passes too. Only a path THROUGH the null separates them.
    """

    def call(self, **arguments):
        from app.tools import evidence

        return REGISTRY.call(
            propose.THE_TREE_FIT, arguments, actor=evidence.USER, thread_id=1
        )

    def test_a_real_fit_passes_and_a_real_refusal_does_not(self):
        criterion = self.plan().step("fit").exit_criterion

        fitted = self.call(path=str(self.table()), target_column="label")
        self.assertTrue(fitted["ok"], fitted.get("summary"))
        self.assertFalse(fitted["nothing_was_fitted"])
        self.assertTrue(criterion.met(fitted).ok)

        refused = self.call(path=str(self.table()), target_column="size")
        self.assertFalse(refused["ok"])
        self.assertTrue(refused["nothing_was_fitted"])
        self.assertFalse(
            criterion.met(refused).ok,
            "a run that fitted nothing satisfied the criterion",
        )

    def test_the_two_traps_this_criterion_is_written_around_are_still_traps(self):
        """If either stops being true, the sentence in the code is stale."""
        from app.build import ExitCriterion

        refused = self.call(path=str(self.table()), target_column="size")
        self.assertTrue(refused["nothing_was_fitted"])
        for subject in ("resolution", "comparison", "score", "estimator"):
            passes = ExitCriterion(
                stated="the naive version", source="tool_result",
                subject=subject, comparator="exists",
            ).met(refused)
            self.assertTrue(
                passes.ok,
                f"{subject!r} no longer passes on a refusal - the comment in "
                "app/tools/propose.py about why the criterion is not that key "
                "has gone stale and should be rewritten to what is true now",
            )

    def test_the_declared_outputs_are_where_the_tool_actually_puts_them(self):
        from app.build import _dig

        fitted = self.call(path=str(self.table()), target_column="label")
        for output in self.plan().step("fit").produces:
            _, present = _dig(fitted, output.at or output.name)
            self.assertTrue(present, f"{output.name} is not at {output.at!r}")


# ---------------------------------------------------------------------------
# The five it does NOT close.


class TheOtherFiveKeepTheirOwnReasonsTest(TabularBuildTestCase):
    def reason(self, outcome: str) -> str:
        self.assertIn(outcome, propose.NOT_COVERED, f"{outcome} is covered now")
        self.assertNotIn(outcome, propose.COVERAGE)
        return propose.NOT_COVERED[outcome]

    def test_no_two_of_the_classical_reasons_are_the_same_sentence(self):
        """The defect this pass is about: one sentence answering for six.

        A shared reason is not wrong by itself - the two small-encoder outcomes
        share one honestly, because they fail for the same reason - so this
        asserts the SET, which is what makes the failure visible: six outcomes
        with fewer than four distinct reasons is `_CHEAPER_MODEL` back again.
        """
        outcomes = (
            "NO_DEEP__TABPFN",
            "NO_DEEP__TUNE_THE_TREES_FIRST",
            "NO_DEEP__CLASSICAL_FORECAST",
            "NO_DEEP__HYBRID_EMBED_PLUS_GBDT",
            "NO_LLM__SETFIT",
            "NO_LLM__ENCODER_FINETUNE",
        )
        self.assertGreaterEqual(len({self.reason(name) for name in outcomes}), 4)

    def test_tabpfn_is_a_model_to_load_and_the_import_is_looked_at(self):
        said = self.reason("NO_DEEP__TABPFN")
        self.assertIn("tabpfn", said)
        self.assertIn("importlib", said)
        try:
            __import__("tabpfn")
        except ImportError:
            self.assertIn("not importable on this machine", said)
        else:  # pragma: no cover - somebody installed it
            self.assertIn("IS importable", said)

    def test_the_tuned_tree_is_a_search_and_this_harness_runs_one_fit(self):
        said = self.reason("NO_DEEP__TUNE_THE_TREES_FIRST")
        self.assertIn("50 trials completed", said)
        self.assertIn(
            "50 trials completed",
            propose.engine_exit_criterion("S8_TABULAR_DEEP_NEEDS_HPARAM_SEARCH"),
        )

    def test_a_forecast_is_not_a_classifier(self):
        said = self.reason("NO_DEEP__CLASSICAL_FORECAST")
        self.assertIn("lag", said.lower())
        self.assertIn("split has to be in time", said)

    def test_the_hybrid_concedes_the_half_that_is_built(self):
        """The sharpest of the five: a third of it IS built now."""
        said = self.reason("NO_DEEP__HYBRID_EMBED_PLUS_GBDT")
        self.assertIn(propose.THE_TREE_FIT, said)
        self.assertIn("NO_DEEP__FIND_THE_MISSING_FEATURE", said)
        if propose.the_tabular_bench_is_registered():
            self.assertIn("is registered here and fits the third", said)

    def test_the_small_encoders_reuse_the_retrieval_benchs_own_reading(self):
        said = self.reason("NO_LLM__SETFIT")
        self.assertEqual(said, self.reason("NO_LLM__ENCODER_FINETUNE"))
        for name in propose.dense_libraries_missing():
            self.assertIn(name, said)

    def test_the_table_says_exactly_one_thing_about_the_tree_outcome(self):
        """Covered or not, and never both - whichever the registry says today.

        Both branches are asserted because both are real states of this
        repository: `app/tools/__init__.py` imports `classical` and the import
        can be absent while somebody is measuring what it changes. The failure
        this guards against is the table saying the product cannot do a thing
        it can, which is the defect `_WhatTheRegistryDecides` exists for.
        """
        outcome = "NO_DEEP__GRADIENT_BOOSTED_TREES"
        if propose.the_tabular_bench_is_registered():
            self.assertIn(outcome, propose.COVERAGE)
            self.assertNotIn(outcome, propose.NOT_COVERED)
            self.assertIn(outcome, propose.PROPOSERS)
            self.assertIn(propose.THE_TREE_FIT, propose.COVERAGE[outcome])
        else:
            self.assertIn(outcome, propose.NOT_COVERED)
            self.assertNotIn(outcome, propose.COVERAGE)
            self.assertNotIn(outcome, propose.PROPOSERS)
            reason = propose.NOT_COVERED[outcome]
            self.assertIn(propose.THE_TREE_FIT, reason)
            self.assertIn("the proposer for it is written", reason)
            # And the refusal a caller gets carries that reason rather than a
            # generic one, so the missing tool is named where it can be acted on.
            with self.assertRaises(propose.NotEnoughToPropose) as raised:
                propose.propose(self.situation())
            self.assertIn(propose.THE_TREE_FIT, raised.exception.detail)

    def test_the_tables_still_account_for_every_outcome_exactly_once(self):
        # WIDENED 2026-08-25: the tables now carry a second-ledger key (the
        # agent instruments' proposer), so "every outcome" is every ledger
        # this product ships, read off the specs rather than assumed.
        declared = set()
        for _p in diagnosis.known_ledgers():
            declared |= set(diagnosis.spec_at(_p).declared_outcomes())
        covered = set(propose.COVERAGE)
        uncovered = set(propose.NOT_COVERED)
        self.assertEqual(covered | uncovered, declared)
        self.assertEqual(covered & uncovered, set())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
