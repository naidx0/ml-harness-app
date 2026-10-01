"""The largest dead end in the product, and whether the plan that closes it runs.

`docs/THE_PROPOSAL_LOOP.md`: *"Today 'do not train anything' is honest and it is
a DEAD END. With the proposal loop, a no-train diagnosis produces a build for the
thing we said instead."* `app/tools/propose.py` covered seven outcomes and left
forty-eight uncovered; thirteen of the fifteen `NO_TRAIN__*` answers were dead
ends. Two of them are covered now, and this file is where that either holds or
turns the suite red.

**What is checked here, and why each one is not a formality.**

1. **The plan runs.** Every step of both builds is executed against the real
   registry, with `Step.bind` resolving the references and `ExitCriterion.met`
   deciding, and every step has to meet the criterion the build stated before it
   ran. That is the strongest available form of *the proposal is the object the
   executor consumes*, and it is possible here and nowhere else in this suite
   because a BM25 index asks no model anything: the whole plan is local, so a
   test can run it on a fresh checkout with no key and no model.
2. **The exit criterion is the ENGINE's.** Both builds state the criterion the
   node declares in `docs/diagnosis_engine.yaml`, compared here against the file
   rather than against a sentence somebody typed twice.
3. **The half of it that cannot be reached is named.** `S3_BUILD_RAG` wants
   recall AND an end-to-end score. Nothing in this harness puts retrieved
   passages in front of a model and grades the answer, so the build says which
   half it reaches - and the canary that the other half is still unreachable is
   checked against the scoring tools' own schemas.
4. **A local index is local.** No step of either build declares a network read,
   the environment declares no egress, and the mutation - a step that reaches
   the model - has to be refused by `Build.validate`.
5. **`stampable` and not `ok`.** `measure_retriever_recall` returns a refusal in
   the SAME SHAPE as a scored run, `ok: True` and all, so the obvious exit
   criterion passes on a run that measured nothing. This drives a real refusal
   out of the real tool and shows both verdicts.
6. **The refusals**, each driven to the sentence a person would read.
"""

from __future__ import annotations

import dataclasses
import json
import unittest
from pathlib import Path
from typing import Any, Mapping
from unittest import mock

import diagnosis_fixtures

from app import build, diagnosis, storm
from app.build import BuildInvalid, ExitCriterion
from app.tools import REGISTRY, evidence, propose
from app.tools.registry import Registry

import support


THE_TOOLS = ("build_retrieval_index", "search_the_index", "measure_retriever_recall")


def registry_without(*names: str) -> Registry:
    """A copy of the live registry with tools taken out.

    `Registry` has no `remove` on purpose - nothing in the product may
    unregister a tool at runtime - so the mutation is a smaller registry built
    from the same declarations. It is how this file proves the coverage tables
    are reading the registry rather than describing it.
    """
    smaller = Registry()
    for spec in REGISTRY:
        if spec.name not in names:
            smaller.add(spec)
    return smaller


class RetrievalProposalTestCase(unittest.TestCase):
    """Its own database, its own directory, and a corpus that is not the eval set."""

    def setUp(self):
        self.root = support.sandbox(self)
        self.thread = 1
        support.a_conversation(self.thread)

    # -- the files ---------------------------------------------------------

    def corpus(self, name: str = "corpus", documents: int = 6) -> Path:
        """A folder of documents, each one the answer to one question."""
        folder = self.root / name
        folder.mkdir(parents=True, exist_ok=True)
        for index in range(documents):
            (folder / f"doc_{index}.txt").write_text(
                f"policy {index}. The refund window for product {index} is "
                f"{index + 10} days from delivery, and returns are free.\n",
                encoding="utf-8",
            )
        return folder

    def questions(self, rows: int = 6, name: str = "questions.jsonl") -> Path:
        """Questions whose answers are in the corpus, with the document that holds each."""
        path = self.root / name
        path.write_text(
            "\n".join(
                json.dumps(
                    {
                        "q": f"what is the refund window for product {index}",
                        "doc": f"doc_{index}.txt",
                    }
                )
                for index in range(rows)
            ),
            encoding="utf-8",
        )
        return path

    # -- the situations ----------------------------------------------------

    def situation(self, outcome: str, **paths) -> propose.Situation:
        """A situation for one of the two outcomes, decided by the real engine.

        The fact sheet comes from `tests/diagnosis_fixtures.py` because
        `retriever_recall_at_k` is `source: inspect` and `retrieval_tried` is
        `source: ask`: the only honest way into the ledger for the first is a run
        against a real index, which is what the execution test below actually
        does. What is bypassed is the ledger round trip, never the tree - the
        outcome asserted is whatever `diagnosis.diagnose` returned.
        """
        sheet = dict(diagnosis_fixtures.REACHING["ACTION__MEASURE_RETRIEVER_RECALL"])
        if outcome == "NO_TRAIN__RAG":
            sheet["retrieval_tried"] = diagnosis.stated(False)
        for name, value in paths.pop("facts", {}).items():
            sheet[name] = value
        result = diagnosis.diagnose(sheet)
        self.assertEqual(result.outcome, outcome)
        return propose.Situation(
            outcome=result.outcome,
            result=result,
            values={
                name: getattr(value, "value", value) for name, value in sheet.items()
            },
            origins=dict(result.fact_origins),
            hows=paths.pop("hows", {}),
            **paths,
        )

    def a_plan(self, outcome: str = "NO_TRAIN__RAG", **overrides):
        arguments: dict[str, Any] = {
            "corpus_path": str(self.corpus()),
            "eval_path": str(self.questions()),
            "input_field": "q",
            "expected_field": "doc",
        }
        arguments.update(overrides)
        return propose.propose(self.situation(outcome, **arguments))


# ---------------------------------------------------------------------------
# 1. The dead end, and whether it is closed.


class TheDeadEndIsClosedTest(RetrievalProposalTestCase):
    def test_both_outcomes_are_covered_now(self):
        for outcome in ("NO_TRAIN__RAG", "ACTION__MEASURE_RETRIEVER_RECALL"):
            with self.subTest(outcome=outcome):
                self.assertIn(outcome, propose.PROPOSERS)
                self.assertIn(outcome, propose.COVERAGE)
                self.assertNotIn(outcome, propose.NOT_COVERED)

    def test_the_three_tool_names_are_the_ones_both_lanes_agreed_on(self):
        """The names are fixed across two lanes so the plan and the instrument
        cannot disagree. A rename in either lane turns this red."""
        self.assertEqual(propose.THE_RETRIEVAL_TOOLS, THE_TOOLS)
        self.assertEqual(propose.retrieval_tools_missing(), ())
        for name in THE_TOOLS:
            self.assertIsNotNone(REGISTRY.get(name), name)

    def test_one_tool_and_only_one_may_declare_the_recall_fact(self):
        """`retriever_recall_at_k` is source: inspect - only a tool may stamp it -
        and the brief fixed which tool. A second measurer is a second definition
        of the number the whole knowledge branch routes on."""
        measurers = sorted(
            spec.name for spec in REGISTRY if "retriever_recall_at_k" in spec.measures
        )
        self.assertEqual(measurers, ["measure_retriever_recall"])
        self.assertTrue(
            evidence.may_be_declared_measurable("retriever_recall_at_k"),
            "the door the engine relies on has been closed",
        )

    def test_the_coverage_statement_follows_the_registry_rather_than_describing_it(self):
        """THE MUTATION FOR THE WHOLE COVERAGE MECHANISM.

        `propose_build` reports `sorted(PROPOSERS)` to its caller as
        `covered_outcomes`, so a hardcoded entry would make the product SAY it
        covers an outcome it cannot build. Take one of the three tools out of the
        registry and both outcomes have to move back to `NOT_COVERED`, with a
        reason that names the tool that went missing - and the proposer has to
        refuse rather than draw steps naming it.
        """
        smaller = registry_without("search_the_index")
        with mock.patch.object(propose, "REGISTRY", smaller):
            self.assertEqual(
                propose.retrieval_tools_missing(), ("search_the_index",)
            )
            for outcome in ("NO_TRAIN__RAG", "ACTION__MEASURE_RETRIEVER_RECALL"):
                with self.subTest(outcome=outcome):
                    self.assertNotIn(outcome, propose.PROPOSERS)
                    self.assertNotIn(outcome, propose.COVERAGE)
                    self.assertIn(outcome, propose.NOT_COVERED)
                    self.assertIn(
                        "search_the_index", propose.NOT_COVERED[outcome]
                    )
            self.assertEqual(set(propose.COVERAGE), set(propose.PROPOSERS))
            self.assertEqual(
                set(propose.COVERAGE) & set(propose.NOT_COVERED), set()
            )
            # Dispatch no longer finds a proposer at all, and the refusal a
            # person reads is the `NOT_COVERED` reason - which names the tool.
            with self.assertRaises(propose.NotEnoughToPropose) as refused:
                self.a_plan()
            self.assertIn("search_the_index", refused.exception.detail)
            # And the proposer itself, called directly, refuses in its own words
            # rather than drawing steps that name a tool nobody registered.
            with self.assertRaises(propose.NotEnoughToPropose) as direct:
                propose._propose_the_retrieval_bench(
                    self.situation(
                        "NO_TRAIN__RAG",
                        corpus_path=str(self.corpus()),
                        eval_path=str(self.questions()),
                        input_field="q",
                        expected_field="doc",
                    )
                )
            self.assertEqual(direct.exception.needs, ("search_the_index",))
            self.assertIn("not registered tools", direct.exception.detail)

        # And back, with nothing edited.
        self.assertIn("NO_TRAIN__RAG", propose.PROPOSERS)
        self.assertNotIn("NO_TRAIN__RAG", propose.NOT_COVERED)

    def test_the_two_lists_still_account_for_every_declared_outcome(self):
        # WIDENED 2026-08-25: the tables now carry a second-ledger key (the
        # agent instruments' proposer), so "every outcome" is every ledger
        # this product ships, read off the specs rather than assumed.
        declared = set()
        for _p in diagnosis.known_ledgers():
            declared |= set(diagnosis.spec_at(_p).declared_outcomes())
        covered = set(propose.COVERAGE)
        explained = set(propose.NOT_COVERED)
        self.assertEqual(covered & explained, set())
        self.assertEqual(covered | explained, declared)

    def test_the_four_outcomes_one_sentence_used_to_answer_for_have_gone_four_ways(self):
        """`_RETRIEVAL_BENCH` used to answer for four outcomes with one sentence -
        *nothing here indexes documents* - and that sentence went false. Two of
        the four are the builds this file drives; a THIRD, NO_TRAIN__FIX_RETRIEVAL,
        left `NOT_COVERED` when the chunking sweep registered. Whichever table
        each one is in, none of them may still be carrying the stale sentence,
        and each statement has to be about that outcome rather than about the
        group it used to belong to."""
        for outcome in (
            "NO_TRAIN__RAG",
            "ACTION__MEASURE_RETRIEVER_RECALL",
            "NO_TRAIN__FIX_RETRIEVAL",
            "NO_TRAIN__CONTEXT_STUFFING",
        ):
            with self.subTest(outcome=outcome):
                said = propose.COVERAGE.get(outcome) or propose.NOT_COVERED[outcome]
                self.assertNotIn("Nothing here indexes documents", said)
                self.assertNotIn("post-v1 (PRODUCT_SPEC 6.6)", said)
                self.assertGreater(len(said.split()), 12)

    def test_the_reason_for_fix_retrieval_is_actually_true(self):
        """THE HALF OF IT THAT SURVIVED THE SWEEP LANDING, AND IT IS THE
        LOAD-BEARING HALF.

        The old reason said this outcome was uncovered because no tool here does
        any of the engine's four things, and the outcome is covered now - a
        chunking sweep is one of the four. What has NOT changed is why that is
        still only a quarter of the answer: the two facts that clear the rest of
        the node's condition are the person's to state and no tool can measure
        them, which is exactly why the build ends in questions about them
        instead of in `run_diagnosis`. Checked against the ledger and the
        registry rather than believed, and the build is checked against both.
        """
        spec = diagnosis.default_spec()
        for fact in ("reranker_tried", "query_rewriting_tried"):
            with self.subTest(fact=fact):
                self.assertEqual(spec.facts[fact]["source"], "ask")
                self.assertEqual(
                    [s.name for s in REGISTRY if fact in s.measures], []
                )
        self.assertIn("NO_TRAIN__FIX_RETRIEVAL", propose.PROPOSERS)
        said = propose.COVERAGE["NO_TRAIN__FIX_RETRIEVAL"]
        self.assertIn("reranker", said)
        self.assertIn("query rewriting", said)
        self.assertIn("this product does not ship", said)

    def test_the_reason_for_context_stuffing_is_actually_true(self):
        """It says corpus_tokens has no instrument. The day one arrives, the
        honest answer changes from 'we cannot' to 'we have not'."""
        self.assertEqual(
            [s.name for s in REGISTRY if "corpus_tokens" in s.measures], []
        )
        self.assertNotIn("NO_TRAIN__CONTEXT_STUFFING", propose.PROPOSERS)


# ---------------------------------------------------------------------------
# 2. The criterion is the engine's, and the half it cannot reach is named.


class TheCriterionIsTheEnginesTest(RetrievalProposalTestCase):
    def test_each_build_states_the_criterion_its_own_node_declares(self):
        """Read out of `docs/diagnosis_engine.yaml`, not typed twice."""
        for outcome, node in (
            ("NO_TRAIN__RAG", "S3_BUILD_RAG"),
            ("ACTION__MEASURE_RETRIEVER_RECALL", "S3_RECALL_UNMEASURED"),
        ):
            with self.subTest(outcome=outcome):
                declared = (
                    diagnosis.default_spec().node_index[node]["exit_criterion"]
                ).strip()
                self.assertTrue(declared)
                plan = self.a_plan(outcome)
                self.assertIn(declared, plan.exit_criterion.stated)
                self.assertIn(node, plan.exit_criterion.stated)

    def test_the_bar_is_read_from_the_spec_rather_than_typed(self):
        stated = diagnosis.default_spec().node_index["S3_BUILD_RAG"]["exit_criterion"]
        self.assertEqual(
            propose.recall_bar(),
            float(stated.split("retriever_recall_at_k >=")[1].split()[0]),
        )
        self.assertIn(f"{propose.recall_bar()}", self.a_plan().because)

    def test_the_rag_build_says_which_half_of_the_criterion_it_reaches(self):
        """Both halves are stated because the engine states both. What this build
        measures is the first, and saying so is the alternative to quietly
        declaring a criterion shaped to what the product can do."""
        plan = self.a_plan("NO_TRAIN__RAG")
        stated = plan.exit_criterion.stated
        self.assertIn("end-to-end score >= target_score", stated)
        self.assertIn("FIRST HALF", stated)
        self.assertIn("does NOT measure the end-to-end score", stated)
        # And the comparator checks the half it reaches, rather than the sentence.
        self.assertEqual(plan.exit_criterion.source, "diagnosis")
        self.assertEqual(
            plan.exit_criterion.subject, "fact_origins.retriever_recall_at_k"
        )
        self.assertEqual(plan.exit_criterion.comparator, "is_measured")

    def test_nothing_in_this_harness_can_reach_the_other_half(self):
        """The canary for the sentence above. Every tool that talks to a model
        sends a system prompt and rows; not one takes retrieved passages, a
        context, or documents. The day one does, the RAG build can reach the
        second half and this claim has to be re-read rather than assumed."""
        # 2026-09-12: generate_rows and judge_rows talk to a model too - to
        # write rows and to grade rows - and the property this canary guards
        # holds of them as of every scorer: neither takes retrieved passages,
        # a context or documents. They are in the list, not excused from it,
        # because the claim is about every tool that talks to a model.
        scorers = sorted(spec.name for spec in REGISTRY if "providers" in spec.reads)
        self.assertEqual(
            scorers,
            # 2026-09-18: generate_tool_rows talks to a model too - to propose
            # a chain and to write its question - and the property holds: it
            # sends tool names and results, never retrieved passages.
            ["generate_rows", "generate_tool_rows", "judge_rows", "measure_baseline", "run_eval", "try_prompt"],
        )
        for name in scorers:
            properties = set((REGISTRY.get(name).schema.get("properties") or {}).keys())
            for absent in ("passages", "context", "documents", "index_id", "retrieved"):
                self.assertNotIn(absent, properties, f"{name} grew {absent}")

    def test_a_run_that_stopped_at_another_node_is_told_where_the_bar_comes_from(self):
        """Four nodes emit `NO_TRAIN__RAG` and only `S3_BUILD_RAG` states a
        criterion. Somebody whose facts change weekly stops at
        `S3_VOLATILE_KNOWLEDGE`, and reading a criterion attributed to a node
        they never reached gives them no way to tell whether this file picked it
        or the engine did."""
        volatile = self.situation(
            "NO_TRAIN__RAG",
            corpus_path=str(self.corpus()),
            eval_path=str(self.questions()),
            input_field="q",
            facts={"knowledge_volatility": diagnosis.stated("weekly")},
        )
        self.assertEqual(volatile.result.node, "S3_VOLATILE_KNOWLEDGE")
        stated = propose.propose(volatile).exit_criterion.stated
        self.assertIn("Your run stopped at S3_VOLATILE_KNOWLEDGE", stated)
        self.assertIn("declares no exit criterion of its own", stated)
        self.assertIn("S3_BUILD_RAG states it as", stated)
        self.assertEqual(
            propose.engine_exit_criterion("S3_VOLATILE_KNOWLEDGE"),
            "",
            "the node now declares one and this build should be held to it",
        )

    def test_the_recall_outcome_ends_where_the_engine_said_it_would(self):
        plan = self.a_plan("ACTION__MEASURE_RETRIEVER_RECALL")
        self.assertIn("retriever_recall_at_k recorded", plan.exit_criterion.stated)
        self.assertEqual(plan.steps[-1].tool, "run_diagnosis")


# ---------------------------------------------------------------------------
# 3. A local index is local.


class AnIndexBuiltHereNeverLeavesTest(RetrievalProposalTestCase):
    def test_no_step_of_either_build_declares_a_network_read(self):
        for outcome in ("NO_TRAIN__RAG", "ACTION__MEASURE_RETRIEVER_RECALL"):
            plan = self.a_plan(outcome, query="what is the refund window")
            for step in plan.steps:
                with self.subTest(outcome=outcome, step=step.id):
                    reads = set(REGISTRY.get(step.tool).reads)
                    self.assertEqual(reads & build.NETWORK_READS, set())
                    self.assertLessEqual(reads, build.LOCAL_READS)
            self.assertFalse(plan.environment.egress, outcome)
            self.assertEqual(plan.environment.egress_reason, "")
            self.assertIn("A local index is local", plan.because)

    def test_a_step_that_reached_the_model_could_not_live_in_this_sandbox(self):
        """THE MUTATION. The sentence above is worth what `Build.validate` makes
        it worth: put a step that reads `providers` into this environment and the
        build must refuse to exist."""
        plan = self.a_plan()
        scoring = dataclasses.replace(
            plan.step("recall"),
            id="score",
            tool="run_eval",
            arguments={
                "eval_path": str(self.questions()),
                "input_field": "q",
                "expected_field": "doc",
            },
            needs=(),
            produces=(),
            operates_on=None,
            exit_criterion=ExitCriterion(
                stated="it ran", source="tool_result", subject="ok", comparator="is_true"
            ),
        )
        with self.assertRaises(BuildInvalid) as refused:
            dataclasses.replace(plan, steps=(scoring,))
        self.assertIn("no egress", str(refused.exception))

    def test_the_corpus_and_the_eval_set_are_both_snapshotted_as_they_were(self):
        plan = self.a_plan()
        paths = {Path(snapshot.path).name for snapshot in plan.environment.data}
        self.assertEqual(paths, {"corpus", "questions.jsonl"})
        for snapshot in plan.environment.data:
            self.assertEqual(
                snapshot.bytes, float(Path(snapshot.path).stat().st_size)
            )


# ---------------------------------------------------------------------------
# 4. The plan runs, and every step meets the criterion it stated.


class ThePlanIsTheThingThatRunsTest(RetrievalProposalTestCase):
    """The strongest check in this file, and it is only possible because the
    whole plan is local: a BM25 index asks no model anything, so a fresh checkout
    with no key can execute the proposal end to end."""

    def run_the_plan(self, plan) -> dict[str, dict[str, Any]]:
        produced: dict[str, dict[str, Any]] = {}
        for step in plan.steps:
            arguments = step.bind(produced)
            result = REGISTRY.call(
                step.tool, arguments, actor=evidence.USER, thread_id=self.thread
            )
            observed = storm._observe(
                step.exit_criterion.source,
                result=result,
                outputs=step.harvest(result),
                thread_id=self.thread,
                registry=REGISTRY,
            )
            verification = step.exit_criterion.met(observed)
            self.assertTrue(
                verification.ok,
                f"{plan.id}.{step.id} ({step.tool}): {verification.because} "
                f"- stated {verification.stated!r}",
            )
            produced[step.id] = step.harvest(result)
        return produced

    def test_the_whole_rag_build_runs_and_every_step_shows_it_worked(self):
        plan = self.a_plan("NO_TRAIN__RAG", query="refund window for product 3")
        self.assertEqual(
            [step.tool for step in plan.steps],
            [
                "attach_context",
                "measure_eval_set",
                "build_retrieval_index",
                "search_the_index",
                "measure_retriever_recall",
                "run_diagnosis",
            ],
        )
        produced = self.run_the_plan(plan)
        self.assertGreaterEqual(produced["index"]["passages"], 1)
        self.assertEqual(produced["count"]["rows"], 6)
        self.assertIsInstance(produced["recall"]["recall_at_k"], float)
        self.assertEqual(produced["recall"]["questions_scored"], 6)

    def test_the_number_it_produces_is_the_one_the_engine_was_waiting_for(self):
        """The dead end closed, end to end: the fact the engine asked a person to
        go and measure is MEASURED in the ledger when this plan finishes, and the
        build's own exit criterion is what says so."""
        plan = self.a_plan("ACTION__MEASURE_RETRIEVER_RECALL")
        self.run_the_plan(plan)
        sheet, _trail = evidence.assemble_facts(self.thread, {}, evidence.USER)
        result = diagnosis.diagnose(sheet)
        self.assertEqual(
            result.fact_origins.get("retriever_recall_at_k"), diagnosis.MEASURED
        )
        self.assertTrue(plan.exit_criterion.met(_as_observed(result)).ok)

    def test_the_look_step_runs_before_the_number_rather_than_beside_it(self):
        """`search_the_index` exists so a person SEES the retriever before
        anybody reports a number about it, and steps with no dependency between
        them share a wave. Without the ordering the plan's own sentence is one
        the executor is free not to keep."""
        plan = self.a_plan(query="refund window for product 3")
        waves = [set(wave) for wave in plan.waves()]
        look = next(i for i, wave in enumerate(waves) if "look" in wave)
        recall = next(i for i, wave in enumerate(waves) if "recall" in wave)
        self.assertLess(look, recall)
        self.assertIn("look", plan.step("recall").needs)

    def test_the_index_the_score_reads_is_the_one_this_plan_built(self):
        """Both readers default to 'the most recent index in this conversation'.
        A plan approved on Tuesday and run on Wednesday would score whichever
        index happened to be newest, so the build names it through a `Ref` and
        `Build.validate` checks that the step really produces it."""
        plan = self.a_plan(query="refund window")
        for step_id in ("look", "recall"):
            reference = plan.step(step_id).arguments["index_id"]
            self.assertEqual(reference.step, "index")
            self.assertEqual(reference.output, "index_id")
            self.assertIn("index", plan.step(step_id).needs)
        with self.assertRaises(BuildInvalid):
            dataclasses.replace(
                plan,
                steps=tuple(s for s in plan.steps if s.id != "index"),
            )


def _as_observed(result: diagnosis.Diagnosis) -> Mapping[str, Any]:
    return {"fact_origins": dict(result.fact_origins), "decided_by": "app/diagnosis.py"}


# ---------------------------------------------------------------------------
# 5. `stampable`, and not `ok`.


class AStepThatCannotShowItWorkedDidNotWorkTest(RetrievalProposalTestCase):
    """`measure_retriever_recall` returns a refusal in the SAME SHAPE as a scored
    run - `ok: True`, every key present, `recall_at_k: None` - deliberately, so a
    caller cannot forget to handle one. That makes the obvious exit criterion
    pass on a run that measured nothing."""

    def a_real_refusal(self) -> Mapping[str, Any]:
        """Drive the real tool into a real refusal: ground truth it cannot resolve."""
        corpus = self.corpus()
        path = self.root / "unmatchable.jsonl"
        path.write_text(
            "\n".join(
                json.dumps({"q": f"question {i}", "doc": f"nothing_like_this_{i}.pdf"})
                for i in range(6)
            ),
            encoding="utf-8",
        )
        REGISTRY.call(
            "build_retrieval_index",
            {"path": str(corpus)},
            actor=evidence.USER,
            thread_id=self.thread,
        )
        return REGISTRY.call(
            "measure_retriever_recall",
            {
                "eval_path": str(path),
                "question_field": "q",
                "ground_truth_field": "doc",
            },
            actor=evidence.USER,
            thread_id=self.thread,
        )

    def test_the_obvious_criterion_would_have_passed_on_a_run_that_measured_nothing(self):
        refusal = self.a_real_refusal()
        self.assertTrue(refusal["ok"], "the premise of this test has changed")
        self.assertIsNone(refusal["recall_at_k"])
        self.assertEqual(refusal["measured"], [])
        would_have_passed = ExitCriterion(
            stated="the tool reported success",
            source="tool_result",
            subject="ok",
            comparator="is_true",
        )
        self.assertTrue(would_have_passed.met(refusal).ok)

    def test_the_criterion_this_build_states_refuses_it(self):
        refusal = self.a_real_refusal()
        criterion = self.a_plan().step("recall").exit_criterion
        self.assertEqual(criterion.subject, "stampable")
        verification = criterion.met(refusal)
        self.assertFalse(verification.ok, verification.because)

    def test_and_nothing_reached_the_ledger_from_it(self):
        self.a_real_refusal()
        sheet, _trail = evidence.assemble_facts(self.thread, {}, evidence.USER)
        result = diagnosis.diagnose(sheet)
        self.assertNotEqual(
            result.fact_origins.get("retriever_recall_at_k"), diagnosis.MEASURED
        )


# ---------------------------------------------------------------------------
# 6. What the plan refuses, and what it will not invent.


class TheProposerRefusesRatherThanDrawingTest(RetrievalProposalTestCase):
    def test_a_corpus_nobody_named_is_a_refusal_and_not_a_guess(self):
        with self.assertRaises(propose.NotEnoughToPropose) as refused:
            propose.propose(
                self.situation(
                    "NO_TRAIN__RAG",
                    eval_path=str(self.questions()),
                    input_field="q",
                    expected_field="doc",
                )
            )
        self.assertIn("corpus_path", refused.exception.needs)

    def test_a_corpus_that_is_not_there_is_refused(self):
        with self.assertRaises(propose.NotEnoughToPropose) as refused:
            self.a_plan(corpus_path=str(self.root / "no_such_folder"))
        self.assertIn("corpus_path", refused.exception.needs)
        self.assertIn("There is nothing at", refused.exception.detail)

    def test_an_eval_set_nobody_named_is_a_refusal(self):
        with self.assertRaises(propose.NotEnoughToPropose) as refused:
            propose.propose(
                self.situation(
                    "NO_TRAIN__RAG",
                    corpus_path=str(self.corpus()),
                    input_field="q",
                )
            )
        self.assertIn("eval_path", refused.exception.needs)

    def test_indexing_the_answers_is_refused_when_they_are_the_same_file(self):
        """A measurement of nothing that comes back near perfect."""
        questions = self.questions()
        with self.assertRaises(propose.NotEnoughToPropose) as refused:
            self.a_plan(corpus_path=str(questions), eval_path=str(questions))
        self.assertIn("corpus_path", refused.exception.needs)
        self.assertIn("near perfect whatever the retriever is", refused.exception.detail)

    def test_indexing_the_answers_is_refused_when_the_eval_set_is_inside_the_corpus(self):
        """THE SPELLING SOMEBODY ACTUALLY REACHES. The two arguments are
        different strings and one of them is a folder, so nothing about the call
        looks wrong - and the index would contain the questions and the answers."""
        corpus = self.corpus()
        inside = corpus / "questions.jsonl"
        inside.write_text(
            json.dumps({"q": "what is the refund window", "doc": "doc_0.txt"}),
            encoding="utf-8",
        )
        with self.assertRaises(propose.NotEnoughToPropose) as refused:
            self.a_plan(eval_path=str(inside))
        self.assertIn("is inside the corpus", refused.exception.detail)

    def test_a_recall_run_with_no_question_column_is_refused_in_those_words(self):
        with self.assertRaises(propose.NotEnoughToPropose) as refused:
            self.a_plan(input_field="")
        self.assertEqual(refused.exception.needs, ("input_field",))
        self.assertIn("among the top few", refused.exception.detail)

    def test_the_two_lanes_disagreeing_about_an_argument_is_a_refusal(self):
        """`_a_call_that_fits` is the cross-lane contract. A tool that renamed the
        argument this plan passes the corpus in must stop the plan and say so,
        rather than have the corpus quietly dropped and the step index nothing."""
        renamed = Registry()
        for spec in REGISTRY:
            if spec.name == "build_retrieval_index":
                renamed.add(
                    dataclasses.replace(
                        spec,
                        schema={
                            "type": "object",
                            "properties": {"corpus": {"type": "string"}},
                            "required": ["corpus"],
                        },
                    )
                )
            else:
                renamed.add(spec)
        with mock.patch.object(propose, "REGISTRY", renamed):
            with self.assertRaises(propose.NotEnoughToPropose) as refused:
                self.a_plan()
        self.assertIn("build_retrieval_index", refused.exception.detail)
        self.assertIn("build_retrieval_index.path", refused.exception.needs)

    def test_and_it_refuses_even_when_the_renamed_argument_is_optional(self):
        """THE CASE THE `required` CHECK DOES NOT CATCH, and the reason
        `must_carry` exists at all. If the tool renamed the corpus argument AND
        made it optional, filtering the call against the schema would simply drop
        the corpus: the step would validate, be approved, run, and index nothing,
        reporting whatever a tool called with no arguments reports. Dropping an
        argument a tool never heard of is harmless; dropping the one that says
        what to index is a plan that looks like it worked.
        """
        renamed = Registry()
        for spec in REGISTRY:
            if spec.name == "build_retrieval_index":
                renamed.add(
                    dataclasses.replace(
                        spec,
                        schema={
                            "type": "object",
                            "properties": {"corpus": {"type": "string"}},
                        },
                    )
                )
            else:
                renamed.add(spec)
        with mock.patch.object(propose, "REGISTRY", renamed):
            with self.assertRaises(propose.NotEnoughToPropose) as refused:
                self.a_plan()
        self.assertIn("build_retrieval_index.path", refused.exception.needs)
        self.assertIn("run on nothing and report success", refused.exception.detail)

    def test_a_substantiation_build_says_why_it_cannot_settle_this_fact(self):
        """`evidence.resolves` routes a challenge on `retriever_recall_at_k` to
        the one tool that measures it, and a substantiation build is one step per
        tool with nowhere to put the indexing. Handing back arguments anyway
        would write a step that scores against no index."""
        self.assertEqual(
            evidence.resolves("retriever_recall_at_k").get("tool"),
            "measure_retriever_recall",
        )
        with self.assertRaises(propose.NotEnoughToPropose) as refused:
            propose._arguments_for(
                "measure_retriever_recall",
                self.situation(
                    "NO_TRAIN__RAG",
                    corpus_path=str(self.corpus()),
                    eval_path=str(self.questions()),
                    input_field="q",
                ),
            )
        self.assertIn("needs an index to measure", refused.exception.detail)

    def test_the_refusal_it_cannot_make_is_said_rather_than_implied(self):
        """"Recall was already measured on this corpus" needs the ledger to
        record WHICH CORPUS a recall figure was measured over, and what
        `measure_retriever_recall` writes is the eval file and the index by name.
        So the build measures again and NAMES THE GAP - which is the eval-set
        proposer's rule, not a lapse from it: refusing on the number alone is how
        somebody who pointed at a new corpus gets told about a different one."""
        plan = self.a_plan(
            "NO_TRAIN__RAG",
            facts={"retriever_recall_at_k": diagnosis.measured(0.91)},
        )
        self.assertIn("nothing records which corpus", plan.because)
        self.assertIn("this build measures rather than reusing it", plan.because)
        self.assertIn(
            "recall was already measured on this corpus",
            propose.COVERAGE["NO_TRAIN__RAG"].lower(),
        )

    def test_but_it_does_fire_when_the_harness_can_say_what_was_measured(self):
        """The guard is written the way the eval-set proposer's is, and this is
        the mutation that shows it is wired rather than decorative: give the fact
        a derivation `subject_of_a_recorded_measurement` can read, pointing at
        this corpus, and the plan refuses instead of measuring again."""
        corpus = self.corpus()
        situation = self.situation(
            "NO_TRAIN__RAG",
            corpus_path=str(corpus),
            eval_path=str(self.questions()),
            input_field="q",
            expected_field="doc",
            facts={"retriever_recall_at_k": diagnosis.measured(0.91)},
            hows={"retriever_recall_at_k": f"counted 6 rows in {corpus}"},
        )
        self.assertIsNotNone(
            propose.a_measurement_of(situation, "retriever_recall_at_k", str(corpus))[1]
        )
        with self.assertRaises(propose.NotEnoughToPropose) as refused:
            propose.propose(situation)
        self.assertIn("already been scored on this corpus", refused.exception.detail)

    def test_a_measurement_of_something_else_does_not_stop_the_build(self):
        """The other half of the same rule. A recall figure measured over a
        different corpus says nothing about this one."""
        situation = self.situation(
            "NO_TRAIN__RAG",
            corpus_path=str(self.corpus()),
            eval_path=str(self.questions()),
            input_field="q",
            expected_field="doc",
            facts={"retriever_recall_at_k": diagnosis.measured(0.91)},
            hows={
                "retriever_recall_at_k": f"counted 6 rows in {self.root / 'elsewhere'}"
            },
        )
        plan = propose.propose(situation)
        self.assertIn("says nothing about the index this build makes", plan.because)


class WhatThePlanWillNotInventTest(RetrievalProposalTestCase):
    def test_no_k_is_chosen_when_nobody_named_one(self):
        """k is half of what `retriever_recall_at_k` means, and it belongs to the
        instrument. A plan that picked one would be choosing the shape of
        somebody else's measurement."""
        plan = self.a_plan(query="refund window")
        self.assertNotIn("k", plan.step("recall").arguments)
        self.assertNotIn("k", plan.step("look").arguments)
        self.assertIn("tool's own default", plan.step("recall").why)

    def test_the_k_you_give_is_the_k_in_the_call(self):
        plan = self.a_plan(query="refund window", top_k=3)
        self.assertEqual(plan.step("recall").arguments["k"], 3)
        self.assertEqual(plan.step("look").arguments["k"], 3)
        self.assertNotIn("tool's own default", plan.step("recall").why)

    def test_a_k_nobody_could_read_is_nobody_said_rather_than_a_crash(self):
        """A `Situation` is assembled by hand in places `propose_build` is not,
        and a negative or unreadable k means the same thing an absent one does."""
        for given in (0, -4, "", "seven", None):
            with self.subTest(top_k=given):
                plan = self.a_plan(top_k=given)
                self.assertNotIn("k", plan.step("recall").arguments)

    def test_the_local_branch_of_the_cost_is_proved_and_the_other_one_is_admitted(self):
        """A BM25 index sends nothing, and that is provable off `reads`. An
        embedding retriever would go through the person's own connected model,
        and then the token and request counts are UNKNOWN here - how many calls a
        retriever makes per document is a property of its chunking. Both branches
        are exercised, the second through a tool that really does read
        `providers`, so the sentence is not one nobody has run."""
        local = propose._retrieval_cost("build_retrieval_index", find_out_by="time it")
        self.assertEqual(local.model_tokens.value, 0)
        self.assertEqual(local.model_requests.value, 0)

        networked = propose._retrieval_cost("measure_baseline", find_out_by="time it")
        self.assertEqual(networked.model_tokens.provenance, build.UNKNOWN)
        self.assertEqual(networked.model_requests.provenance, build.UNKNOWN)
        self.assertIn("includes `providers`", networked.model_requests.how)
        self.assertTrue(networked.model_requests.find_out_by.strip())

    def test_the_egress_sentence_is_derived_and_not_a_constant(self):
        """The empty string is a CLAIM - it says no step of this plan declares a
        network read - so it has to be computed from the tools rather than
        chosen. A step that reaches the model turns it into a sentence."""
        self.assertEqual(propose._egress_for(list(THE_TOOLS)), "")
        reason = propose._egress_for(["build_retrieval_index", "measure_baseline"])
        self.assertIn("providers", reason)
        self.assertIn("nothing leaves it", reason)

    def test_no_query_means_no_look_step_and_the_plan_says_so(self):
        plan = self.a_plan()
        self.assertNotIn("look", [step.id for step in plan.steps])
        self.assertIn("did not give me a question to try", plan.because)
        self.assertIn("a demonstration nobody chose", plan.because)

    def test_the_answer_column_is_never_passed_as_the_thing_retrieval_is_scored_on(self):
        """`measure_retriever_recall` says in its own schema that `answer_field`
        produces a WEAKER and DIFFERENT measurement that is never recorded as
        `retriever_recall_at_k`. The engine asked for recall."""
        plan = self.a_plan()
        self.assertNotIn("answer_field", plan.step("recall").arguments)
        self.assertEqual(plan.step("recall").arguments["ground_truth_field"], "doc")

    def test_an_unnamed_ground_truth_column_is_left_to_the_tool_and_said_so(self):
        """It is optional on the tool, which picks a conventional column and names
        the one it used. Refusing when the tool would have found it is the product
        being strict at the person's expense."""
        plan = self.a_plan(expected_field="")
        self.assertNotIn("ground_truth_field", plan.step("recall").arguments)
        self.assertIn("picks a conventional one", plan.step("recall").why)

    def test_every_cost_in_both_builds_carries_a_provenance_and_none_is_a_guess(self):
        """Nobody has ever built a retrieval index on this machine, so every
        wall-clock and every disk figure has to be UNKNOWN with a way to find
        out. The token and request counts are the two that are PROVABLE, off the
        tools' own `reads`."""
        for outcome in ("NO_TRAIN__RAG", "ACTION__MEASURE_RETRIEVER_RECALL"):
            plan = self.a_plan(outcome, query="refund window")
            for step in plan.steps:
                with self.subTest(outcome=outcome, step=step.id):
                    self.assertEqual(step.cost.wall_clock.provenance, build.UNKNOWN)
                    self.assertTrue(step.cost.wall_clock.find_out_by.strip())
                    self.assertIsNone(step.cost.wall_clock.value)
                    self.assertEqual(step.cost.model_tokens.value, 0)
                    self.assertEqual(step.cost.model_requests.value, 0)
                    self.assertIn(
                        "does not include `providers`", step.cost.model_tokens.how
                    )
            index = plan.step("index").cost.disk
            self.assertEqual(index.provenance, build.UNKNOWN)
            self.assertIn("no retrieval index has ever been built", index.how)
            self.assertIn("slice of the corpus", index.find_out_by)

    def test_the_disk_estimate_does_not_borrow_the_sentence_written_for_other_tools(self):
        """`_disk_cost` says *rows in the harness database, no files* and is right
        about the tools it was written for. An index is the first thing this
        product writes that is neither, and a true-sounding claim about somebody
        else's tool is the same defect as an invented number, in prose.

        AND THE OTHER DIRECTION IS THE SAME DEFECT. `measure_retriever_recall`
        writes one fact row, so the index sentence would be just as wrong about
        it. Which one applies is read off the tool's own `writes`.
        """
        plan = self.a_plan(query="refund window")
        index = plan.step("index").cost.disk
        self.assertNotIn("no files", index.how)
        self.assertIn("no retrieval index has ever been built", index.how)
        self.assertEqual(REGISTRY.get("build_retrieval_index").writes, ("retrieval",))

        recall = plan.step("recall").cost.disk
        self.assertNotIn("no retrieval index has ever been built", recall.how)
        self.assertIn("rows in the harness database", recall.how)
        self.assertEqual(REGISTRY.get("measure_retriever_recall").writes, ("facts",))

        look = plan.step("look").cost.disk
        self.assertEqual(look.value, 0)
        self.assertIn("writes=()", look.how)

    def test_the_recheck_step_asks_the_engine_rather_than_deciding(self):
        plan = self.a_plan()
        recheck = plan.step("recheck")
        self.assertEqual(recheck.tool, "run_diagnosis")
        self.assertEqual(recheck.arguments, {"facts": {}})
        self.assertEqual(recheck.exit_criterion.comparator, "is_measured")

    def test_the_rag_build_asks_the_person_the_one_thing_no_tool_can_answer(self):
        """`retrieval_tried` is `source: ask` and no tool measures it, so a
        question is legitimate - `Build.validate` refuses one that a registered
        tool could answer. The recall outcome is already past it and does not
        ask."""
        rag = self.a_plan("NO_TRAIN__RAG")
        self.assertEqual([q.fact for q in rag.questions], ["retrieval_tried"])
        self.assertEqual(
            [s.name for s in REGISTRY if "retrieval_tried" in s.measures], []
        )
        measured = self.a_plan("ACTION__MEASURE_RETRIEVER_RECALL")
        self.assertEqual(measured.questions, ())

    def test_the_recall_build_never_claims_to_be_measuring_their_retriever(self):
        """The person here already runs one. A figure stamped
        `retriever_recall_at_k` off a different retriever is a real measurement
        answering a question about something else, which is the defect this file
        spent a milestone closing on row counts."""
        plan = self.a_plan("ACTION__MEASURE_RETRIEVER_RECALL")
        self.assertIn("this does not measure it", plan.because)
        self.assertIn("floor and a comparison", plan.because)
        self.assertIn(
            "not the retriever you run in production",
            " ".join(risk.what for risk in plan.risks),
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
