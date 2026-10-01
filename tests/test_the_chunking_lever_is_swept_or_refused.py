"""The outcome our own last change made reachable, and whether the plan for it is honest.

`docs/VISION.md` lists `NO_TRAIN__FIX_RETRIEVAL` among the four workbench
specifications the engine had already written down. The retrieval bench made it
REACHABLE - `retriever_recall_at_k` had no instrument before it, so the node
could not fire - and left it uncovered, which is worse than the dead end the
bench closed: the product could now tell somebody "your retriever scores 0.55,
go and fix it" and offer them nothing.

**What is checked here, and why none of it is a formality.**

1. **The engine declares no exit criterion for this node.** Read out of
   `docs/diagnosis_engine.yaml` here rather than believed, because the whole
   difficulty of this proposer follows from it. A build whose success condition
   was invented by the proposer is the proposal-loop trap in its purest form,
   and the build has to say which of the two cases it is in - engine's criterion
   or none - rather than presenting a sentence somebody typed.
2. **The criterion is not "recall goes up".** Recall rising two points on ninety
   questions is inside the resolution. Both step criteria and the build's are
   about the comparison having been possible and complete; a mutation that
   points any of them at a score has to be visible here.
3. **THE NULL.** The sweep is run on settings that genuinely cannot differ - a
   corpus where every setting cuts identically - through the real tool, and the
   verdict has to be NO EVIDENCE with nothing crowned. A tool that crowns a
   winner there is wrong, and this is where we would have found it ourselves.
   The upward bias of a maximum is measured rather than asserted, on simulated
   runs where every setting is identical by construction.
4. **The floor is exact and is the sweep's own.** The fewest questions that
   would have to change verdict before anything can separate is asked of
   `evals.mcnemar` here and of `2 ** (1 - m)` in `app/tools/retrieval.py`; the
   two derivations are pinned against each other, and against the family size
   the tool reports back from a real run.
5. **The plan runs.** Every step, against the real registry, with `Step.bind`
   resolving references and `ExitCriterion.met` deciding - possible on a fresh
   checkout with no key because a BM25 sweep asks no model anything.
6. **The refusals**, each driven to the sentence a person would read.
"""

from __future__ import annotations

import dataclasses
import json
import random
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import diagnosis_fixtures

from app import diagnosis, storm
from app.build import BuildInvalid
from app.tools import REGISTRY, evals, evidence, propose, retrieval
from app.tools.registry import Registry

import support


THE_TOOL = "compare_chunkings"
THE_NODE = "S3_RETRIEVAL_IS_THE_BOTTLENECK"
THE_OUTCOME = "NO_TRAIN__FIX_RETRIEVAL"


def registry_without(*names: str) -> Registry:
    """A copy of the live registry with tools taken out.

    `Registry` has no `remove` on purpose - nothing in the product may
    unregister a tool at runtime - so the mutation is a smaller registry built
    from the same declarations. It is how this file proves the coverage tables
    read the registry rather than describe it.
    """
    smaller = Registry()
    for spec in REGISTRY:
        if spec.name not in names:
            smaller.add(spec)
    return smaller


class SweepProposalTestCase(unittest.TestCase):
    """Its own database, its own directory, and a corpus that is not the eval set."""

    def setUp(self):
        self.root = support.sandbox(self)
        self.thread = 1
        support.a_conversation(self.thread)

    # -- the files ---------------------------------------------------------

    def corpus(self, name: str = "corpus", documents: int = 8, paragraphs: int = 6) -> Path:
        """A folder of documents long enough that passage size changes the cut.

        Several paragraphs each, so a small `passage_chars` splits them and a
        large one packs them - which is the thing a sweep varies. A corpus of
        one-line files would cut identically at every setting and is the NULL
        below rather than the ordinary case.
        """
        folder = self.root / name
        folder.mkdir(parents=True, exist_ok=True)
        for index in range(documents):
            body = "\n\n".join(
                f"Section {part} of policy {index}. The refund window for "
                f"product {index} is {index + 10} days from delivery. Returns "
                f"are free for product {index}, and the restocking fee for "
                f"product {index} is waived. " * 3
                for part in range(paragraphs)
            )
            (folder / f"doc_{index}.txt").write_text(body, encoding="utf-8")
        return folder

    def flat_corpus(self, name: str = "flat", documents: int = 8) -> Path:
        """THE NULL: documents that every chunk setting cuts exactly the same way.

        One short paragraph each, well under the smallest passage size any
        setting below uses, so `cut_into_passages` packs each document into one
        passage whatever the window is. Every setting therefore indexes byte for
        byte the same passages and scores identically - not approximately, not
        within noise, identically - which is the only construction where "the
        tool must not crown a winner" is a claim about the tool rather than
        about the data.
        """
        folder = self.root / name
        folder.mkdir(parents=True, exist_ok=True)
        for index in range(documents):
            (folder / f"doc_{index}.txt").write_text(
                f"Policy {index}: the refund window for product {index} is "
                f"{index + 10} days.\n",
                encoding="utf-8",
            )
        return folder

    def questions(self, rows: int = 60, name: str = "questions.jsonl", documents: int = 8) -> Path:
        path = self.root / name
        path.write_text(
            "\n".join(
                json.dumps(
                    {
                        "q": f"what is the refund window for product {index % documents}",
                        "doc": f"doc_{index % documents}.txt",
                    }
                )
                for index in range(rows)
            ),
            encoding="utf-8",
        )
        return path

    # -- the situation -----------------------------------------------------

    def situation(self, **paths) -> propose.Situation:
        """A situation for `NO_TRAIN__FIX_RETRIEVAL`, decided by the real engine.

        The fact sheet comes from `tests/diagnosis_fixtures.py` because
        `retriever_recall_at_k` is `source: inspect` - the only honest way into
        the ledger is a real run against a real index - and `retrieval_tried` is
        `source: ask`. What is bypassed is the ledger round trip, never the
        tree: the outcome asserted is whatever `diagnosis.diagnose` returned.
        """
        sheet = dict(diagnosis_fixtures.REACHING[THE_OUTCOME])
        for name, value in paths.pop("facts", {}).items():
            sheet[name] = value
        result = diagnosis.diagnose(sheet)
        self.assertEqual(result.outcome, THE_OUTCOME)
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

    def a_plan(self, **overrides):
        arguments: dict[str, Any] = {
            "corpus_path": str(self.corpus()),
            "eval_path": str(self.questions()),
            "input_field": "q",
            "expected_field": "doc",
            "chunk_settings": (400, 900, 2000),
        }
        arguments.update(overrides)
        return propose.propose(self.situation(**arguments))

    def refusal(self, **overrides) -> propose.NotEnoughToPropose:
        with self.assertRaises(propose.NotEnoughToPropose) as refused:
            self.a_plan(**overrides)
        return refused.exception


# ---------------------------------------------------------------------------
# 1. The outcome, and whether the product now covers it.


class TheOutcomeOurOwnChangeMadeReachableTest(SweepProposalTestCase):
    def test_the_outcome_is_covered_now(self):
        self.assertIn(THE_OUTCOME, propose.PROPOSERS)
        self.assertIn(THE_OUTCOME, propose.COVERAGE)
        self.assertNotIn(THE_OUTCOME, propose.NOT_COVERED)

    def test_the_tool_name_is_the_one_both_lanes_agreed_on(self):
        """Fixed across two lanes so the plan and the instrument cannot disagree
        about what to call the thing. A rename in either lane turns this red."""
        self.assertEqual(propose.THE_CHUNKING_TOOLS, (THE_TOOL,))
        self.assertEqual(propose.chunking_sweep_missing(), ())
        self.assertIsNotNone(REGISTRY.get(THE_TOOL))

    def test_one_node_emits_this_outcome_and_it_is_the_one_this_file_names(self):
        """`_THE_BOTTLENECK_NODE` is a constant because exactly one node emits
        this outcome. If a second ever appears, which node's words the build
        quotes stops being obvious and this says so before the build does."""
        spec = diagnosis.default_spec()
        emitting = sorted(
            str(row.get("node"))
            for row in spec.node_index.values()
            if row.get("outcome") == THE_OUTCOME
        )
        self.assertEqual(emitting, [THE_NODE])
        self.assertEqual(propose._THE_BOTTLENECK_NODE, THE_NODE)

    def test_the_sweep_records_no_fact_so_one_instrument_still_owns_the_recall(self):
        """The build's refusal to re-stamp is structural on the tool's side too:
        `retriever_recall_at_k` is source: inspect and exactly one tool measures
        it. A sweep that could stamp would make a selected maximum routable."""
        measurers = sorted(
            spec.name for spec in REGISTRY if "retriever_recall_at_k" in spec.measures
        )
        self.assertEqual(measurers, ["measure_retriever_recall"])
        self.assertEqual(REGISTRY.get(THE_TOOL).measures, ())

    def test_the_coverage_statement_follows_the_registry_rather_than_describing_it(self):
        """THE MUTATION FOR THE COVERAGE MECHANISM, on the new entry.

        `propose_build` reports `sorted(PROPOSERS)` to its caller as
        `covered_outcomes`, so a hardcoded entry would make the product SAY it
        covers an outcome it cannot build. Take the sweep out of the registry
        and the outcome has to move back to `NOT_COVERED` with a reason naming
        the tool that went missing - and the proposer has to refuse rather than
        draw a step naming it.
        """
        smaller = registry_without(THE_TOOL)
        with mock.patch.object(propose, "REGISTRY", smaller):
            self.assertEqual(propose.chunking_sweep_missing(), (THE_TOOL,))
            self.assertNotIn(THE_OUTCOME, propose.PROPOSERS)
            self.assertNotIn(THE_OUTCOME, propose.COVERAGE)
            self.assertIn(THE_OUTCOME, propose.NOT_COVERED)
            self.assertIn(THE_TOOL, propose.NOT_COVERED[THE_OUTCOME])
            # The two lists stay disjoint and stay complete with one bench gone.
            self.assertEqual(set(propose.COVERAGE) & set(propose.NOT_COVERED), set())
            self.assertEqual(set(propose.COVERAGE), set(propose.PROPOSERS))
            # Dispatch no longer finds a proposer, and the sentence a person
            # reads is the `NOT_COVERED` reason - which names the tool.
            with self.assertRaises(propose.NotEnoughToPropose) as refused:
                self.a_plan()
            self.assertIn(THE_TOOL, refused.exception.detail)
            # And the proposer itself, called directly, refuses in its own words
            # rather than drawing steps naming a tool nobody registered.
            with self.assertRaises(propose.NotEnoughToPropose) as direct:
                propose._propose_fix_the_retriever(
                    self.situation(
                        corpus_path=str(self.corpus()),
                        eval_path=str(self.questions()),
                        input_field="q",
                        expected_field="doc",
                        chunk_settings=(400, 900),
                    )
                )
            self.assertEqual(direct.exception.needs, (THE_TOOL,))
            self.assertIn("not registered", direct.exception.detail)

        # And back, with nothing edited.
        self.assertIn(THE_OUTCOME, propose.PROPOSERS)
        self.assertNotIn(THE_OUTCOME, propose.NOT_COVERED)

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

    def test_the_reason_that_went_false_is_gone(self):
        """`_FIX_THE_RETRIEVER_IS_WORK_NOT_A_MEASUREMENT` said no tool here does
        any of the engine's four things. Its FIRST ITEM was chunking, and
        `build_retrieval_index` has taken `passage_chars` since the retrieval
        bench landed - so half the sentence was false before it was written.
        This is the canary for that shape, wherever the reason now lives."""
        reason = propose.NOT_COVERED.get(THE_OUTCOME, "")
        if not reason:
            reason = propose.COVERAGE[THE_OUTCOME]
        self.assertNotIn("no tool in this harness does any of them", reason)
        self.assertIn("passage_chars", reason)
        self.assertIn(
            "passage_chars",
            (REGISTRY.get("build_retrieval_index").schema.get("properties") or {}),
        )


# ---------------------------------------------------------------------------
# 2. The criterion, which the engine did not state.


class TheCriterionIsNotInventedTest(SweepProposalTestCase):
    def test_the_engine_really_does_declare_no_exit_criterion_for_this_node(self):
        """THE FACT THE WHOLE PROPOSER TURNS ON, read out of the spec rather
        than taken from a brief. `S3_BUILD_RAG` and `S3_RECALL_UNMEASURED` both
        state one and this node does not, which is why its build cannot be
        written the way theirs are."""
        row = diagnosis.default_spec().node_index[THE_NODE]
        self.assertIsNone(row.get("exit_criterion"))
        self.assertEqual(propose.engine_exit_criterion(THE_NODE), "")
        self.assertTrue(propose.engine_exit_criterion("S3_BUILD_RAG"))
        self.assertTrue(propose.engine_exit_criterion("S3_RECALL_UNMEASURED"))

    def test_the_build_says_the_engine_declared_none_and_names_what_it_derived(self):
        stated = self.a_plan().exit_criterion.stated
        self.assertIn(f"{THE_NODE} DECLARES NO exit_criterion", stated)
        # The derivation, and the thing it was derived FROM, quoted from the file.
        condition = diagnosis.default_spec().node_index[THE_NODE]["condition"].strip()
        self.assertIn(condition, stated)
        self.assertIn("WHAT IS DERIVED, AND FROM WHAT", stated)
        self.assertIn("THAT IS NOT THIS BUILD'S CRITERION", stated)
        self.assertIn(f"{propose.recall_bar()}", stated)

    def test_the_action_and_the_say_are_the_engines_words_rather_than_ours(self):
        plan = self.a_plan()
        row = diagnosis.default_spec().node_index[THE_NODE]
        self.assertIn(row["action"].strip(), plan.because)
        self.assertIn(row["say"].strip(), plan.because)

    def test_if_the_engine_ever_states_one_the_build_is_held_to_it(self):
        """The self-correcting half. `engine_exit_criterion` is read every time,
        so the day somebody writes an `exit_criterion:` on this node the build
        quotes it instead of explaining that there is none - with nothing in
        `app/tools/propose.py` edited. Driven by adding one to the spec."""
        spec = diagnosis.default_spec()
        row = dict(spec.node_index[THE_NODE])
        row["exit_criterion"] = "the retriever is fixed, somehow"
        with mock.patch.dict(spec.node_index, {THE_NODE: row}):
            stated = self.a_plan().exit_criterion.stated
        self.assertIn("the retriever is fixed, somehow", stated)
        self.assertNotIn("DECLARES NO exit_criterion", stated)

    def test_no_criterion_in_this_build_is_about_a_score_going_up(self):
        """THE TRAP THIS PROPOSER EXISTS TO AVOID. `evals.py`'s lesson is that a
        delta inside the resolution is NO EVIDENCE, so a build whose success
        condition is "recall improved" would be satisfied by noise. Every
        criterion here is about the comparison having been possible and complete,
        and the subjects say so."""
        plan = self.a_plan()
        subjects = {step.id: step.exit_criterion.subject for step in plan.steps}
        self.assertEqual(subjects["count"], "rows")
        self.assertEqual(
            subjects["preflight"], "will_do.questions_each_setting_is_scored_on"
        )
        self.assertEqual(subjects["sweep"], "compared_questions")
        self.assertEqual(plan.exit_criterion.subject, "sweep.family_size")
        # And not one of them names a field the sweep reports a SCORE under.
        # These are the subjects a criterion meaning "it got better" would have
        # to reach for, and they are all present in the tool's own result.
        scored = (
            "recall_at_k",
            "highest_recall_here",
            "per_setting",
            "crowned",
            "separated_n",
            "beaten_by",
        )
        every = [step.exit_criterion.subject for step in plan.steps]
        every.append(plan.exit_criterion.subject)
        for subject in every:
            for name in scored:
                self.assertNotIn(name, subject)

    def test_a_verdict_alone_is_not_the_criterion_because_a_refusal_has_one(self):
        """`ok` and `verdict` are both TRUE of a sweep that compared nothing -
        the tool returns its refusals in the same shape as its answers, exactly
        as `measure_retriever_recall` does. Driven against the real refusal
        payload rather than argued about."""
        refused = retrieval._sweep_refusal(
            error="whatever", sentence="nothing was compared", plan={}
        )
        self.assertTrue(refused["ok"])
        self.assertTrue(refused["verdict"])
        plan = self.a_plan()
        sweep = plan.step("sweep")
        self.assertFalse(sweep.exit_criterion.met(refused).ok)
        self.assertFalse(
            plan.exit_criterion.met({"sweep": {"family_size": refused["family_size"]}}).ok
        )
        # And the weaker criteria somebody would reach for DO pass on it, which
        # is why neither is used.
        self.assertTrue(refused.get("ok"))
        self.assertIsNotNone(refused.get("verdict"))


# ---------------------------------------------------------------------------
# 3. The statistics, and the floor that is not a rule of thumb.


class TheFloorIsComputedNotRememberedTest(SweepProposalTestCase):
    def test_the_alpha_is_the_one_the_rest_of_this_product_calls_evidence(self):
        """A third copy of 0.05 is the drift this repository has been bitten by
        twice. `app/tools/propose.py` does not import either other definition -
        it keeps working when a bench is absent - so this is the pin."""
        self.assertEqual(propose.RESOLVED_AT, retrieval.SWEEP_ALPHA)
        import inspect

        source = inspect.getsource(evals.compare).replace(" ", "")
        self.assertIn(f"p_value<={propose.RESOLVED_AT}", source)

    def test_the_floor_agrees_with_the_tool_that_will_judge(self):
        """Two derivations of the same number - `evals.mcnemar` counted upwards
        here, the closed form `2 ** (1 - m)` in the sweep - pinned against each
        other. A plan that refused work the sweep would have resolved, or planned
        work it could not, is this disagreeing with itself."""
        for settings in range(2, 13):
            family = propose.pairwise_comparisons(settings)
            with self.subTest(settings=settings, family=family):
                self.assertEqual(family, settings * (settings - 1) // 2)
                self.assertEqual(
                    propose.discordant_rows_that_could_resolve(family),
                    retrieval.min_discordant_for(retrieval.SWEEP_ALPHA / family),
                )

    def test_the_floor_is_the_smallest_number_that_works_and_one_less_does_not(self):
        """Non-vacuous by construction: the row below it cannot reach the
        threshold however the changes fall, which is what makes the refusal a
        proof rather than a preference."""
        for family in (1, 3, 6, 28):
            floor = propose.discordant_rows_that_could_resolve(family)
            alpha = propose.RESOLVED_AT / family
            with self.subTest(family=family, floor=floor):
                self.assertLessEqual(evals.mcnemar(floor, 0), alpha)
                self.assertGreater(evals.mcnemar(floor - 1, 0), alpha)
                # And every other split of the same number of changed rows is
                # worse, so "all one way" really is the best case.
                for improved in range(0, floor + 1):
                    self.assertGreaterEqual(
                        evals.mcnemar(improved, floor - improved),
                        evals.mcnemar(floor, 0),
                    )

    def test_the_rows_needed_is_the_smallest_eval_set_where_the_floor_can_exist(self):
        for recall in (0.0, 0.25, 0.55, 0.79):
            for family in (1, 3, 6):
                needed = propose.questions_that_could_resolve(recall, family)
                floor = propose.discordant_rows_that_could_resolve(family)
                with self.subTest(recall=recall, family=family):
                    self.assertGreaterEqual(
                        propose.questions_wrong_now(recall, needed), floor
                    )
                    self.assertLess(
                        propose.questions_wrong_now(recall, needed - 1), floor
                    )

    def test_the_family_size_this_file_computes_is_the_one_the_tool_reports(self):
        """The plan's floor is derived from `m(m-1)/2`; the tool corrects over
        `len(pairs)`. Driven through a real sweep rather than compared on paper."""
        settings = (300, 700, 1500, 2600)
        result = REGISTRY.call(
            THE_TOOL,
            {
                "corpus_path": str(self.corpus()),
                "eval_path": str(self.questions(rows=40)),
                "question_field": "q",
                "ground_truth_field": "doc",
                "settings": [{"passage_chars": size} for size in settings],
                "run": True,
            },
            actor=evidence.USER,
            thread_id=self.thread,
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(
            result["family_size"], propose.pairwise_comparisons(len(settings))
        )
        self.assertEqual(
            result["min_changed_questions_at_this_family_size"],
            propose.discordant_rows_that_could_resolve(result["family_size"]),
        )


# ---------------------------------------------------------------------------
# 4. THE NULL, CONSTRUCTED AND SHOWN.


class TheNullTest(SweepProposalTestCase):
    """Run the sweep where every setting is genuinely identical, and look."""

    def test_settings_that_cannot_differ_come_back_as_no_evidence_with_nothing_crowned(self):
        """Every document is one short paragraph, so every setting cuts the
        corpus into byte-identical passages and scores identically - not within
        noise, identically. If anything is crowned here the tool is wrong, and
        this is where we would find it ourselves."""
        flat = self.flat_corpus()
        result = REGISTRY.call(
            THE_TOOL,
            {
                "corpus_path": str(flat),
                "eval_path": str(self.questions(rows=60)),
                "question_field": "q",
                "ground_truth_field": "doc",
                "settings": [
                    {"passage_chars": size} for size in (500, 900, 1400, 2200, 3000)
                ],
                "run": True,
            },
            actor=evidence.USER,
            thread_id=self.thread,
        )
        self.assertTrue(result["ok"], result)
        # THE PREMISE IS MEASURED BEFORE THE VERDICT IS READ. "Every setting cuts
        # this corpus identically" is the whole construction, and a test that
        # assumed it would keep passing on a corpus where the settings really do
        # differ - at which point "nothing separated" would be a fact about a
        # small eval set rather than about the tool. So it is checked against
        # the index's own cutter, and against the passage counts the sweep came
        # back with.
        sizes = [row["passage_chars"] for row in result["per_setting"]]
        for document in sorted(Path(flat).glob("*.txt")):
            text = document.read_text(encoding="utf-8")
            for size in sizes:
                self.assertEqual(
                    len(retrieval.cut_into_passages(text, size, 200)),
                    1,
                    f"{document.name} is not one passage at passage_chars={size}",
                )
        self.assertEqual(
            len({row["passages"] for row in result["per_setting"]}),
            1,
            f"the settings built different indexes: "
            f"{[(r['setting'], r['passages']) for r in result['per_setting']]}",
        )
        recalls = {row["setting"]: row["hits"] for row in result["per_setting"]}
        self.assertEqual(
            len(set(recalls.values())),
            1,
            f"the null is not a null: {recalls}",
        )
        self.assertEqual(result["separated_n"], 0)
        self.assertIsNone(result["crowned"])
        self.assertEqual(result["verdict"], "no_evidence")
        self.assertIn("NO EVIDENCE", result["says"])
        self.assertEqual(result["measured"], [])
        for pair in result["comparisons"]:
            self.assertEqual(pair["changed"], 0, pair["says"])
            self.assertFalse(pair["separated"], pair["says"])
        # And this file's own reading of "nothing changed" is the same one.
        self.assertEqual(evals.mcnemar(0, 0), 1.0)

        # THE POSITIVE CONTROL. The same settings over the ordinary corpus cut
        # it into DIFFERENT numbers of passages, so "every setting is identical"
        # above is a property of that corpus and not something these settings
        # would do to anything. Without this, the null could be passing because
        # the sweep never varies anything at all.
        varied = REGISTRY.call(
            THE_TOOL,
            {
                "corpus_path": str(self.corpus()),
                "eval_path": str(self.questions(rows=60)),
                "question_field": "q",
                "ground_truth_field": "doc",
                "settings": [
                    {"passage_chars": size} for size in (500, 900, 1400, 2200, 3000)
                ],
                "run": True,
            },
            actor=evidence.USER,
            thread_id=self.thread,
        )
        self.assertTrue(varied["ok"], varied)
        self.assertGreater(
            len({row["passages"] for row in varied["per_setting"]}),
            1,
            "these settings do not vary the cut on any corpus, so the null above "
            "proves nothing about the tool",
        )

    def test_pure_noise_between_eight_settings_separates_nothing_and_the_correction_is_why(self):
        """THE OTHER NULL: settings that are not identical, only indistinguishable.

        Eight hit vectors drawn from the SAME Bernoulli over the same 90
        questions, so every difference between them is noise by construction,
        pushed through the sweep's own comparison. Two hundred seeded families,
        and the number of them in which anything separates is what the
        family-wise error rate promises. The uncorrected count is run beside it,
        because "twenty-eight tests at 0.05 apiece" is a sentence and this is the
        measurement under it - and without that comparison the corrected zero
        could just as easily mean the null is too easy.
        """
        rng = random.Random(20260821)
        truth, settings, rows, trials = 0.6, 8, 90, 200
        corrected = uncorrected = 0
        for _ in range(trials):
            vectors = [
                (f"setting_{index}", [rng.random() < truth for _ in range(rows)])
                for index in range(settings)
            ]
            verdict = retrieval.compare_hit_vectors(
                vectors, alpha=propose.RESOLVED_AT
            )
            if verdict["separated_n"]:
                corrected += 1
            if any(
                pair["p"] is not None and pair["p"] <= propose.RESOLVED_AT
                for pair in verdict["comparisons"]
            ):
                uncorrected += 1
            self.assertEqual(
                verdict["family_size"], propose.pairwise_comparisons(settings)
            )
        # 200 families of 28 tests. Uncorrected, a good share of them contain a
        # false separation; corrected, the family-wise rate holds them at or
        # under 5%. Both counts are asserted so neither can be read as the
        # other.
        self.assertGreater(uncorrected, trials * 0.2)
        self.assertLessEqual(corrected, trials * 0.05)
        self.assertLess(corrected, uncorrected)

        # AND THE SENTENCE THE PRODUCT SAYS OUT LOUD IS THIS NUMBER.
        #
        # `compare_chunkings`'s own description tells the model "two in five
        # families of eight settings that do not differ at all contain a false
        # separation without it - 42.0% of 200 seeded null families, against
        # 3.5% with it", and the module comment above `compare_hit_vectors`
        # says the same. Until 2026-08-21 both said "roughly a one-in-three
        # chance", which was never measured and was wrong at every family size
        # the tool allows - and the same clause was interpolated into the
        # `correction` field of every reply a user reads.
        #
        # So the two rates are pinned to the band the claim needs, not merely
        # ordered. Loosening these back to `> 0.2` would let the prose drift
        # again with nothing to catch it; the range is wide enough that only a
        # real change in `compare_hit_vectors` moves it out.
        self.assertEqual(
            (uncorrected, corrected),
            (84, 7),
            "the seeded null moved. The 42.0% and 3.5% in `compare_chunkings`'s "
            "description and in this module's header comment are THIS "
            "measurement; if the numbers here changed, change those sentences "
            "in the same commit rather than widening this assertion.",
        )
        self.assertAlmostEqual(uncorrected / trials, 0.42, places=2)
        self.assertAlmostEqual(corrected / trials, 0.035, places=3)

    def test_the_null_still_satisfies_this_builds_criteria_because_it_is_an_answer(self):
        """The other half, and the one a criterion gets wrong. "Nothing
        separated" is the plan working: the comparison happened, on enough rows,
        over every pair. A build whose criterion failed here would be a build
        that calls an honest null a failure and teaches people to keep sweeping
        until something separates."""
        plan = self.a_plan(
            corpus_path=str(self.flat_corpus()),
            eval_path=str(self.questions(rows=60)),
            chunk_settings=(600, 1200, 2400),
        )
        result = REGISTRY.call(
            THE_TOOL,
            plan.step("sweep").arguments,
            actor=evidence.USER,
            thread_id=self.thread,
        )
        self.assertEqual(result["verdict"], "no_evidence")
        self.assertTrue(plan.step("sweep").exit_criterion.met(result).ok)
        outputs = {"sweep": plan.step("sweep").harvest(result)}
        self.assertTrue(plan.exit_criterion.met(outputs).ok)

    def test_the_maximum_of_identical_settings_is_biased_upward_and_here_is_by_how_much(self):
        """WHY THIS BUILD RECORDS NO NUMBER, measured rather than asserted.

        Eight settings, all with the SAME true recall, scored on the same 90
        questions. Every difference between them is noise by construction. The
        highest of the eight is nevertheless above the truth almost every time,
        which is exactly what stamping a swept winner as `retriever_recall_at_k`
        would put into the ledger - and `retriever_recall_at_k < 0.8` is this
        node's own condition, so it would route people out of the outcome on
        selection noise.

        Seeded, so the number in the assertion is reproducible rather than a
        number that happened.
        """
        rng = random.Random(20260821)
        truth, settings, rows, trials = 0.6, 8, 90, 400
        maxima = []
        for _ in range(trials):
            scores = [
                sum(1 for _ in range(rows) if rng.random() < truth) / rows
                for _ in range(settings)
            ]
            maxima.append(max(scores))
        mean_max = sum(maxima) / len(maxima)
        above = sum(1 for value in maxima if value > truth)
        self.assertGreater(
            mean_max,
            truth,
            "the maximum of identical estimates should sit above the truth",
        )
        # The bias is worth several points, which is the size of difference a
        # person would happily act on. Stated as counts, in the assertion.
        self.assertGreater(mean_max - truth, 0.03)
        self.assertGreater(above, trials * 0.9)

    def test_a_corpus_of_one_document_is_a_null_the_proposer_can_see_in_advance(self):
        """The null this file's own tool refuses rather than measures: with one
        document, chunking cannot change which document comes back."""
        alone = self.root / "alone"
        alone.mkdir()
        (alone / "only.txt").write_text("the refund window is thirty days\n", "utf-8")
        refusal = self.refusal(corpus_path=str(alone))
        self.assertIn("one document", refusal.detail)
        self.assertIn("guaranteed null", refusal.detail)
        self.assertEqual(refusal.needs, ("corpus_path",))
        # And a single STRUCTURED file is not that case - one row is one
        # document - so it is not refused on a file count.
        rows = self.root / "rows.jsonl"
        rows.write_text(
            "\n".join(json.dumps({"text": f"policy {i}"}) for i in range(20)), "utf-8"
        )
        self.assertFalse(propose._the_corpus_is_one_document(str(rows)))
        self.assertTrue(propose._the_corpus_is_one_document(str(alone / "only.txt")))


# ---------------------------------------------------------------------------
# 5. The plan is the thing that runs.


class ThePlanIsTheThingThatRunsTest(SweepProposalTestCase):
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

    def test_the_whole_build_runs_and_every_step_shows_it_worked(self):
        plan = self.a_plan()
        self.assertEqual(
            [step.tool for step in plan.steps],
            ["attach_context", "measure_eval_set", THE_TOOL, THE_TOOL],
        )
        produced = self.run_the_plan(plan)
        self.assertEqual(produced["count"]["rows"], 60)
        self.assertEqual(produced["preflight"]["rebuilds"], 3)
        self.assertEqual(produced["sweep"]["family_size"], 3)
        self.assertIn(
            produced["sweep"]["verdict"], ("no_evidence", "some_settings_separated")
        )
        self.assertTrue(plan.exit_criterion.met(produced).ok)

    def test_the_preflight_builds_nothing_and_the_run_step_is_the_one_that_does(self):
        """`run` is the tool's own switch and its default is off, which is what
        makes the preflight a real step rather than a rehearsal this file
        invented. Checked on the database, not on the argument."""
        plan = self.a_plan()
        self.assertNotIn("run", plan.step("preflight").arguments)
        self.assertIs(plan.step("sweep").arguments["run"], True)
        for step in plan.steps[:3]:
            REGISTRY.call(
                step.tool,
                step.bind({}),
                actor=evidence.USER,
                thread_id=self.thread,
            )
        self.assertEqual(retrieval.indexes_in(self.thread), [])
        REGISTRY.call(
            THE_TOOL,
            plan.step("sweep").arguments,
            actor=evidence.USER,
            thread_id=self.thread,
        )
        self.assertEqual(len(retrieval.indexes_in(self.thread)), 3)

    def test_nothing_in_this_build_records_the_fact_the_engine_routes_on(self):
        """THE REFUSAL AT THE CENTRE OF THE PLAN, checked on the ledger. A swept
        winner is a maximum selected on the rows it is reported against; putting
        it in as `retriever_recall_at_k` would route the knowledge branch on
        selection noise. So the plan runs and the fact's origin is untouched."""
        plan = self.a_plan()
        self.run_the_plan(plan)
        sheet, _trail = evidence.assemble_facts(self.thread, {}, evidence.USER)
        self.assertNotIn("retriever_recall_at_k", sheet)
        self.assertEqual(
            [step.tool for step in plan.steps if step.tool == "run_diagnosis"], []
        )
        # It ends in questions instead, and they are the facts the node's own
        # condition reads that no tool here can measure.
        self.assertEqual(
            sorted(q.fact for q in plan.questions),
            ["query_rewriting_tried", "reranker_tried"],
        )
        for fact in ("reranker_tried", "query_rewriting_tried"):
            self.assertEqual(diagnosis.default_spec().facts[fact]["source"], "ask")
            self.assertEqual([s.name for s in REGISTRY if fact in s.measures], [])

    def test_a_local_sweep_is_local(self):
        plan = self.a_plan()
        self.assertFalse(plan.environment.egress)
        self.assertEqual(plan.environment.egress_reason, "")
        for step in plan.steps:
            self.assertEqual(
                set(REGISTRY.get(step.tool).reads) & {"providers", "huggingface_hub"},
                set(),
                f"{step.id} would reach the network",
            )

    def test_the_sweep_waits_for_the_preflight_rather_than_sharing_its_wave(self):
        """Steps with no dependency between them run at once, so a plan whose
        sentence is 'count what this would do BEFORE it does it' has to say so
        in `needs` or the executor is free not to keep it."""
        plan = self.a_plan()
        waves = [set(wave) for wave in plan.waves()]
        preflight = next(i for i, wave in enumerate(waves) if "preflight" in wave)
        sweep = next(i for i, wave in enumerate(waves) if "sweep" in wave)
        self.assertLess(preflight, sweep)
        self.assertIn("preflight", plan.step("sweep").needs)
        with self.assertRaises(BuildInvalid):
            dataclasses.replace(
                plan, steps=tuple(s for s in plan.steps if s.id != "preflight")
            )

    def test_the_count_is_skipped_when_this_file_has_already_been_counted(self):
        """And only when it is THIS file: a measured count of some other file is
        a real number about the wrong thing."""
        questions = self.questions(rows=60)
        REGISTRY.call(
            "measure_eval_set",
            {"path": str(questions), "finish_the_count": True},
            actor=evidence.USER,
            thread_id=self.thread,
        )
        sheet, trail = evidence.assemble_facts(self.thread, {}, evidence.USER)
        situation = dataclasses.replace(
            self.situation(
                corpus_path=str(self.corpus()),
                eval_path=str(questions),
                input_field="q",
                expected_field="doc",
                chunk_settings=(400, 900, 2000),
            ),
            values={
                **{name: getattr(value, "value", value) for name, value in sheet.items()},
                "retriever_recall_at_k": 0.55,
            },
            origins={
                **{row["fact"]: row["origin"] for row in trail},
                "retriever_recall_at_k": diagnosis.MEASURED,
            },
            hows={row["fact"]: row.get("how") or "" for row in trail},
            recorded_at=propose.when_each_row_was_written(self.thread, trail),
        )
        plan = propose.propose(situation)
        self.assertEqual([step.id for step in plan.steps], ["attach", "preflight", "sweep"])
        self.assertIn("60 counted questions", plan.because)


# ---------------------------------------------------------------------------
# 6. The refusals, each in the words a person reads.


class TheRefusalsTest(SweepProposalTestCase):
    def test_a_typed_recall_is_refused_because_there_is_nothing_to_improve_on(self):
        """`tests/test_a_typed_recall_routes_like_a_measured_one.py` pins the
        hole: no gate reads this fact, so a person who TYPED a recall reaches
        this outcome. A sweep for them would compare settings this harness
        measured against a baseline nobody read - two facts, not a difference."""
        refusal = self.refusal(
            facts={"retriever_recall_at_k": diagnosis.stated(0.55)}
        )
        self.assertIn("stated rather than measured", refusal.detail)
        self.assertIn("ACTION__MEASURE_RETRIEVER_RECALL", refusal.detail)
        self.assertEqual(refusal.needs, ("a measured retriever_recall_at_k",))

    def test_a_measured_origin_with_no_number_behind_it_is_refused_rather_than_read_as_zero(self):
        """Every figure in this plan is arithmetic on the recall, so a missing
        value would quietly become 0.0 and print "your retriever scores 0.0"
        beside a floor computed from it - an invented number with a real origin
        attached, which is the only kind that survives review."""
        situation = self.situation(
            corpus_path=str(self.corpus()),
            eval_path=str(self.questions()),
            input_field="q",
            expected_field="doc",
            chunk_settings=(400, 900),
        )
        hollow = dataclasses.replace(
            situation,
            values={
                name: value
                for name, value in situation.values.items()
                if name != "retriever_recall_at_k"
            },
        )
        self.assertTrue(hollow.is_measured("retriever_recall_at_k"))
        with self.assertRaises(propose.NotEnoughToPropose) as refused:
            propose._propose_fix_the_retriever(hollow)
        self.assertIn("holds no number for it", refused.exception.detail)
        self.assertEqual(refused.exception.needs, ("retriever_recall_at_k",))

    def test_a_recall_already_past_the_bar_has_nothing_to_improve(self):
        situation = self.situation(
            corpus_path=str(self.corpus()),
            eval_path=str(self.questions()),
            input_field="q",
            expected_field="doc",
            chunk_settings=(400, 900),
        )
        past = dataclasses.replace(
            situation, values={**situation.values, "retriever_recall_at_k": 0.9}
        )
        with self.assertRaises(propose.NotEnoughToPropose) as refused:
            propose._propose_fix_the_retriever(past)
        self.assertIn("already scores 0.9", refused.exception.detail)
        self.assertIn(str(propose.recall_bar()), refused.exception.detail)

    def test_the_eval_set_inside_the_corpus_is_refused_in_both_spellings(self):
        corpus = self.corpus()
        inside = corpus / "questions.jsonl"
        inside.write_text(
            "\n".join(
                json.dumps({"q": f"q{i}", "doc": f"doc_{i}.txt"}) for i in range(20)
            ),
            encoding="utf-8",
        )
        refusal = self.refusal(eval_path=str(inside))
        self.assertIn("is inside the corpus", refusal.detail)
        self.assertIn("looks exactly like a real one", refusal.detail)
        same = self.refusal(corpus_path=str(inside), eval_path=str(inside))
        self.assertIn("are the same file", same.detail)

    def test_the_settings_are_the_persons_and_this_file_will_not_choose_them(self):
        """The prompt bench's refusal in a new place, and for a sharper reason:
        the number of settings is the family size every p-value is corrected
        against, so choosing them chooses the false-winner rate."""
        refusal = self.refusal(chunk_settings=())
        self.assertIn("I can plan the sweep and I will not choose", refusal.detail)
        self.assertEqual(refusal.needs, ("chunk_settings",))
        # The trade is stated in numbers this file computed, not adjectives.
        self.assertIn(
            str(propose.discordant_rows_that_could_resolve(propose.pairwise_comparisons(2))),
            refusal.detail,
        )
        self.assertIn(
            str(propose.discordant_rows_that_could_resolve(propose.pairwise_comparisons(8))),
            refusal.detail,
        )
        # One setting is a measurement and not a comparison, and duplicates do
        # not make a second one.
        self.assertIn("at least 2", self.refusal(chunk_settings=(900,)).detail)
        self.assertIn("at least 2", self.refusal(chunk_settings=(900, 900)).detail)
        # And `settings` really is the tool's own argument, so the refusal is
        # about a thing the person can supply rather than about a gap here.
        self.assertIn(
            "settings", (REGISTRY.get(THE_TOOL).schema.get("properties") or {})
        )

    def test_an_eval_set_that_cannot_resolve_anything_is_refused_with_the_rows_that_would(self):
        """THE REFUSAL THAT SAVES THE HOURS. The rows that can change are at most
        the rows the retriever gets wrong; below the floor, even a setting that
        fixed every one of them comes back NO EVIDENCE. Computed from two
        measured facts, before a single index is rebuilt."""
        questions = self.questions(rows=12, name="twelve.jsonl")
        REGISTRY.call(
            "measure_eval_set",
            {"path": str(questions), "finish_the_count": True},
            actor=evidence.USER,
            thread_id=self.thread,
        )
        sheet, trail = evidence.assemble_facts(self.thread, {}, evidence.USER)
        situation = dataclasses.replace(
            self.situation(
                corpus_path=str(self.corpus()),
                eval_path=str(questions),
                input_field="q",
                expected_field="doc",
                chunk_settings=(400, 900, 2000),
            ),
            values={
                **{name: getattr(value, "value", value) for name, value in sheet.items()},
                "retriever_recall_at_k": 0.55,
            },
            origins={
                **{row["fact"]: row["origin"] for row in trail},
                "retriever_recall_at_k": diagnosis.MEASURED,
            },
            hows={row["fact"]: row.get("how") or "" for row in trail},
            recorded_at=propose.when_each_row_was_written(self.thread, trail),
        )
        with self.assertRaises(propose.NotEnoughToPropose) as refused:
            propose.propose(situation)
        detail = refused.exception.detail
        family = propose.pairwise_comparisons(3)
        floor = propose.discordant_rows_that_could_resolve(family)
        needed = propose.questions_that_could_resolve(0.55, family)
        self.assertIn("cannot resolve any chunking difference", detail)
        self.assertIn("12 counted questions", detail)
        self.assertIn(f"gets {propose.questions_wrong_now(0.55, 12)} of them wrong", detail)
        self.assertIn(f"until {floor} questions change verdict", detail)
        self.assertIn(f"at least {needed} questions", detail)
        self.assertEqual(refused.exception.needs, (f"eval_size_n >= {needed}",))
        # And the refusal is TRUE: even a perfect setting cannot reach the
        # threshold on this many wrong answers.
        self.assertGreater(
            evals.mcnemar(propose.questions_wrong_now(0.55, 12), 0),
            propose.RESOLVED_AT / family,
        )

    def test_when_nobody_has_counted_the_file_the_floor_becomes_a_step_that_stops(self):
        """The same refusal where it cannot be made yet. The count's criterion
        and the preflight's are the floor, so the storm stops before a single
        index is rebuilt rather than after all of them are."""
        plan = self.a_plan(
            eval_path=str(self.questions(rows=12, name="twelve.jsonl"))
        )
        needed = propose.questions_that_could_resolve(
            0.55, propose.pairwise_comparisons(3)
        )
        self.assertEqual(plan.step("count").exit_criterion.value, needed)
        self.assertEqual(plan.step("preflight").exit_criterion.value, needed)
        result = REGISTRY.call(
            "measure_eval_set",
            plan.step("count").arguments,
            actor=evidence.USER,
            thread_id=self.thread,
        )
        self.assertEqual(result["rows"], 12)
        verification = plan.step("count").exit_criterion.met(result)
        self.assertFalse(verification.ok)
        self.assertIn("wanted at least", verification.because)

    def test_a_missing_corpus_a_missing_eval_set_and_a_missing_column_all_refuse(self):
        self.assertEqual(self.refusal(corpus_path="").needs, ("corpus_path",))
        self.assertEqual(self.refusal(eval_path="").needs, ("eval_path",))
        self.assertEqual(self.refusal(input_field="").needs, ("input_field",))
        gone = self.refusal(corpus_path=str(self.root / "nowhere"))
        self.assertIn("There is nothing at", gone.detail)

    def test_a_cross_lane_rename_refuses_at_proposal_time_rather_than_after_approval(self):
        """The argument names are the tool's own and this file keeps no table of
        them: `_a_call_that_fits` asks the schema. A sweep that renamed
        `eval_path` reaches the person as a refusal naming the argument, never as
        a plan rejected after they approved it."""
        spec = REGISTRY.get(THE_TOOL)
        properties = {
            key: value
            for key, value in (spec.schema.get("properties") or {}).items()
            if key not in ("corpus_path", "path")
        }
        renamed = Registry()
        for other in REGISTRY:
            renamed.add(
                dataclasses.replace(
                    other,
                    schema={
                        **other.schema,
                        "properties": properties,
                        "required": [
                            name
                            for name in (other.schema.get("required") or ())
                            if name in properties
                        ],
                    },
                )
                if other.name == THE_TOOL
                else other
            )
        with mock.patch.object(propose, "REGISTRY", renamed):
            with self.assertRaises(propose.NotEnoughToPropose) as refused:
                self.a_plan()
        self.assertIn("which corpus to rebuild the index over", refused.exception.detail)
        self.assertIn("corpus_path", refused.exception.detail)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
