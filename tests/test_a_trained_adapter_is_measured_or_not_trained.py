"""The first build under a TRAIN verdict, and the two things it must not become.

`TRAIN__LORA_SFT` is the outcome this product is named after and it was the
emptiest entry in `app/tools/propose.py`: nine `TRAIN__` outcomes and no build
behind any of them, so the harness handed work to everybody it told NOT to
train and handed the conversation's end to everybody it told to. This file is
about the build that closes it and about the two ways closing it could have made
the product worse.

**ONE: the gates.** A build downstream of a TRAIN verdict is downstream of five
gates that already passed, and the single thing it may never do is make that
verdict easier to reach. So the check here is not "the proposer looks careful":
it is that NO STEP IN THE BUILD RUNS A TOOL THAT MEASURES ANY FACT ANY GATE ROW
READS, with the gate facts derived from `docs/diagnosis_engine.yaml` rather than
listed, and with a positive control proving the derivation found real facts and
that some registered tool really does measure one. And the same fact sheet with
its gate facts re-attributed as ASSERTED must not reach a training outcome at
all, so no new argument on `propose_build` is a route around the tree.

**TWO: the criterion.** `docs/THE_PROPOSAL_LOOP.md` wants the exit criterion
stated before the run, and for a fine-tune the only honest one is the adapter
BEATING THE MEASURED BASELINE on the person's own eval set by a margin those
rows can resolve. "Training finished" and "the loss went down" are the two
sentences `app/tools/evals.py` exists to refuse. So the build states that
criterion with its arithmetic - the rows that could move, the number that would
have to change verdict, the p-value that would take - and then says plainly that
nothing in this harness can check it, and does not run the fine-tune.

**WHICH IS A CLAIM ABOUT THE PRODUCT, SO IT IS CHECKED AND NOT ASSERTED.**
`NothingHereCanScoreAnAdapterTest` reads the two rosters the claim rests on -
every registered tool that can put text in front of a model, and every shipped
recipe's declared kinds - and pins them. The day a tool arrives that can score
something other than a connected provider, or a recipe declares kind `eval` or
`convert`, these go red and somebody re-reads the build instead of leaving a
false sentence in every training proposal. That is the same canary
`NO_TRAIN__OFF_THE_SHELF_MODEL` carries, pointed at the other half of the
product.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import diagnosis_fixtures

from app import build, diagnosis, jobspec
from app.build import BuildInvalid, Subject
from app.tools import REGISTRY, evidence, propose, sandbox as sandboxes
from app.tools.registry import Registry

import support


REPO_ROOT = Path(__file__).resolve().parents[1]

#: The gate facts are derived from the spec, so the derivation needs a way to
#: pick names out of a `requires:` string. Anything that looks like an
#: identifier; whether it IS a fact is then decided by the ledger.
_A_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def gate_facts() -> set[str]:
    """Every fact any row of any gate reads, straight out of the spec.

    NOT A LIST IN THIS FILE. A copy would go stale in the direction nobody
    looks: a gate row that starts reading a sixth fact would leave the copy
    green while the product's own promise moved underneath it.
    """
    spec = diagnosis.default_spec()
    found: set[str] = set()
    for gate in spec.gates.values():
        for row in gate.get("passes_when") or ():
            for name in _A_NAME.findall(str(row.get("requires") or "")):
                if name in spec.facts:
                    found.add(name)
    return found


class TrainingBuildTestCase(unittest.TestCase):
    """Everything here needs its own database, its own recipes and real files."""

    def setUp(self):
        self.root = support.sandbox(self)
        support.pin_a_training_recipe(propose.THE_LORA_RECIPE)

    # -- the files -------------------------------------------------------

    def eval_file(self, rows: int = 100, name: str = "eval.jsonl") -> Path:
        path = self.root / name
        path.write_text(
            "\n".join(
                json.dumps({"q": f"question {i}", "a": "yes"}) for i in range(rows)
            ),
            encoding="utf-8",
        )
        return path

    def training_file(self, rows: int = 200, name: str = "train.jsonl") -> Path:
        path = self.root / name
        path.write_text(
            "\n".join(
                json.dumps({"text": f"a training example, number {i}"})
                for i in range(rows)
            ),
            encoding="utf-8",
        )
        return path

    # -- the situation ---------------------------------------------------

    def diagnosis_that_mints(self, **facts):
        sheet = dict(diagnosis_fixtures.MINTING["TRAIN__LORA_SFT"])
        sheet.update(facts)
        result = diagnosis.diagnose(sheet)
        return sheet, result

    def situation(self, **over) -> propose.Situation:
        """A `Situation` for the minted verdict, filled the way `propose_build` fills one.

        The ledger round trip is bypassed and the TREE IS NOT: `diagnose` runs
        for real over the fixture sheet. `hows` carries the derivation
        `measure_eval_set` writes, because the proposer refuses unless
        `eval_size_n` is a measured count OF the file the fine-tune would be
        judged on.
        """
        facts = over.pop("facts", {})
        sheet, result = self.diagnosis_that_mints(**facts)
        self.assertEqual(result.outcome, "TRAIN__LORA_SFT")
        values = {n: getattr(v, "value", v) for n, v in sheet.items()}
        evaluation = over.get("eval_path") or str(self.eval_file())
        base = dict(
            outcome=result.outcome,
            result=result,
            values=values,
            origins=dict(result.fact_origins),
            hows={
                "eval_size_n": f"counted {values['eval_size_n']} rows in {evaluation}"
            },
            dataset_path=str(self.training_file()),
            eval_path=evaluation,
            base_model="Qwen/Qwen3-4B",
            max_seq_len=512,
        )
        base.update(over)
        return propose.Situation(**base)

    def plan(self, **over):
        return propose.propose(self.situation(**over))

    def refusal(self, **over) -> propose.NotEnoughToPropose:
        with self.assertRaises(propose.NotEnoughToPropose) as raised:
            self.plan(**over)
        return raised.exception

    def variant(self, situation: propose.Situation, **fields) -> propose.Situation:
        """The same situation with some fields replaced.

        A `Situation` is frozen and several tests here need one that
        `propose_build` could not produce - a caller assembling one by hand,
        which is exactly how a proposer ends up planning for a verdict other
        than the one in front of it. Several of the refusals below are
        unreachable through the tool because the ENGINE would route those facts
        somewhere else; they are still the proposer's to make, and this is how
        they are reached without pretending the tree allowed it.
        """
        import dataclasses

        return dataclasses.replace(situation, **fields)

    def refusal_from(self, situation: propose.Situation) -> propose.NotEnoughToPropose:
        with self.assertRaises(propose.NotEnoughToPropose) as raised:
            propose.propose(situation)
        return raised.exception


# ---------------------------------------------------------------------------
# ONE. The five gates.


#: Every step of every plan this build draws that measures anything, and
#: exactly what it measures.
#:
#: THIS DICTIONARY EXISTS BECAUSE THE TEST BELOW WAS GREEN AND WRONG. It said
#: "no step in the training build measures anything at all" and iterated
#: `self.plan()`, whose Situation comes from `diagnosis_fixtures.MINTING`, where
#: `vram_gb` is MEASURED. `_propose_train_the_adapter` prepends a `card` step
#: running `inspect_hardware` exactly when `vram_gb` is NOT measured - which is
#: the case the step was written for, and a user answering the router's
#: `fallback: ask` with "24" reaches it - so the only step that could falsify
#: the assertion was the one plan the assertion never ran over. Pointed at the
#: card-carrying plan with nothing else changed, it fails.
#:
#: An entry here is not permission. It is the sentence somebody has to write
#: before a build downstream of a TRAIN verdict stamps a new fact, and the test
#: below checks the four names as well as the tool, so widening what
#: `inspect_hardware` measures fails this file too.
MEASURED_BY_THE_TRAINING_BUILD = {
    ("card", "inspect_hardware"): (
        "ram_gb",
        "vram_gb",
        "disk_free_gb",
        "accelerator",
    ),
}


class TheFiveGatesAreNotWeakenedTest(TrainingBuildTestCase):
    def plans(self) -> dict[str, object]:
        """Both plans this build draws, by the thing that decides between them.

        The gate assertions below have to run over every plan `propose` can
        return for a TRAIN verdict, not over the one the fixture happens to
        produce. There are two, and the difference is whether anybody has
        measured this machine's VRAM.
        """
        import dataclasses

        measured = self.situation()
        stated = dataclasses.replace(
            measured, origins={**measured.origins, "vram_gb": diagnosis.STATED}
        )
        drawn = {
            "vram_gb measured": propose.propose(measured),
            "vram_gb stated": propose.propose(stated),
        }
        # The positive control for this helper: the second plan really does
        # carry the step the first one does not, so "over both plans" is not
        # "over the same plan twice".
        self.assertNotIn("card", [s.id for s in drawn["vram_gb measured"].steps])
        self.assertIn("card", [s.id for s in drawn["vram_gb stated"].steps])
        return drawn

    def test_the_derivation_of_the_gate_facts_found_real_ones(self):
        """A positive control, so the test below cannot pass by finding nothing.

        Every assertion in this class is of the form "no step measures one of
        these". An empty set makes all of them vacuous, and a set that quietly
        stopped matching the spec's spelling would make them vacuous without
        looking empty. So: the derivation finds facts, it finds the five the
        gates are named for, and at least one REGISTERED TOOL measures one of
        them - which is what makes "no step in this build does" a claim.
        """
        facts = gate_facts()
        self.assertTrue(facts)
        for name in (
            "eval_size_n",
            "baseline_measured",
            "baseline_score",
            "retrieval_tried",
            "model_swap_tried",
        ):
            self.assertIn(name, facts)
        measurers = {
            spec.name
            for spec in REGISTRY
            if set(getattr(spec, "measures", ())) & facts
        }
        self.assertTrue(
            measurers,
            "no registered tool measures a gate fact, so the check below is empty",
        )

    def test_no_step_in_the_training_build_measures_a_fact_a_gate_reads(self):
        """THE GUARANTEE, over every plan this build can draw and not just one."""
        facts = gate_facts()
        for which, plan in self.plans().items():
            for step in plan.steps:
                spec = REGISTRY.get(step.tool)
                self.assertIsNotNone(spec, step.tool)
                stamped = set(getattr(spec, "measures", ()))
                self.assertEqual(
                    stamped & facts,
                    set(),
                    f"[{which}] {plan.id}.{step.id} runs {step.tool}, which "
                    f"measures {sorted(stamped & facts)} - a build downstream "
                    "of a TRAIN verdict may not stamp anything the gates read",
                )

    def test_every_step_that_measures_anything_at_all_is_written_down(self):
        """Stricter than the gates, and it is the honest state of this build.

        Almost nothing here reads a number into the ledger: every step is a
        look, a check or a run, and the artifact is the log the trial writes.
        The exception is the `card` step, which is the whole point of the card
        step - it exists to MEASURE the VRAM nobody has measured - and it is in
        `MEASURED_BY_THE_TRAINING_BUILD` above with the four facts it stamps.

        Written as its own test rather than folded into the one above, because
        the two go false for different reasons: a step that measured a NON-gate
        fact would still be a change to what this build asserts about the world,
        and somebody should have to read this file before making it. That is
        exactly what did NOT happen, which is why this now runs over both plans
        and pins the fact names instead of asserting an empty tuple.
        """
        for which, plan in self.plans().items():
            for step in plan.steps:
                self.assertEqual(
                    tuple(getattr(REGISTRY.get(step.tool), "measures", ())),
                    MEASURED_BY_THE_TRAINING_BUILD.get((step.id, step.tool), ()),
                    f"[{which}] {plan.id}.{step.id} runs {step.tool}, which "
                    "measures something this file does not say it measures",
                )

    def test_nothing_the_build_measures_is_a_fact_any_gate_reads(self):
        """The written-down measurers, checked against the gates by name.

        The dictionary above is a record of what is allowed to be stamped, so
        the record itself has to be held to the guarantee: none of the four
        facts the card step writes appears in any gate row. If a future entry
        named one, this fails here rather than only in the loop over the plans -
        which matters because the loop can only see the plans that exist.
        """
        facts = gate_facts()
        for key, stamped in MEASURED_BY_THE_TRAINING_BUILD.items():
            self.assertEqual(
                set(stamped) & facts,
                set(),
                f"{key} is written down as measuring {sorted(set(stamped) & facts)}, "
                "which a gate reads",
            )

    def test_a_verdict_reached_on_asserted_facts_never_gets_a_training_build(self):
        """The adversary case: same values, no provenance, no training plan.

        `tests/test_fact_origins.py` does this for the diagnosis; this does it
        for the BUILD, because the proposer is the new surface and the question
        is whether anything about it is a second door into a TRAIN outcome.
        """
        sheet = {
            name: diagnosis.asserted(getattr(value, "value", value))
            for name, value in diagnosis_fixtures.MINTING["TRAIN__LORA_SFT"].items()
        }
        result = diagnosis.diagnose(sheet)
        self.assertNotEqual(result.verdict, "TRAIN")
        self.assertFalse(result.outcome.startswith("TRAIN__"))

    def test_the_new_arguments_are_not_a_route_into_a_training_plan(self):
        """base_model, max_seq_len, text_field and trial_steps decide nothing.

        They are the arguments this build needed, and the fear about any new
        argument on `propose_build` is that it becomes a way to ask for a
        training plan. So: send all four, with a fact sheet that does not mint,
        through the real tool, and the answer must be the outcome the engine
        reached and no build for a training outcome.
        """
        support.a_conversation(77)
        result = REGISTRY.call(
            "propose_build",
            {
                "facts": {"goal_text": "make it better", "modality": "text"},
                "eval_path": str(self.eval_file()),
                "dataset_path": str(self.training_file()),
                "base_model": "Qwen/Qwen3-4B",
                "max_seq_len": 512,
                "text_field": "text",
                "trial_steps": 5,
            },
            actor=evidence.MODEL,
            thread_id=77,
        )
        self.assertNotEqual(result.get("verdict"), "TRAIN")
        self.assertFalse(str(result.get("outcome", "")).startswith("TRAIN__"))

    def test_the_tool_still_has_no_argument_that_selects_an_outcome(self):
        spec = REGISTRY.get("propose_build")
        properties = set((spec.schema.get("properties") or {}).keys())
        for forbidden in ("outcome", "verdict", "diagnosis", "method", "recipe", "plan"):
            self.assertNotIn(forbidden, properties)

    def test_no_step_reaches_the_model_the_person_connected(self):
        """Which is also why the build's own token cost can be proved zero."""
        plan = self.plan()
        for step in plan.steps:
            self.assertNotIn(
                propose.THE_SCORING_READ,
                REGISTRY.get(step.tool).reads,
                f"{plan.id}.{step.id} sends the person's rows to their model",
            )


# ---------------------------------------------------------------------------
# TWO. The criterion.


class TheCriterionIsTheAdapterBeatingTheBaselineTest(TrainingBuildTestCase):
    def test_the_mint_declares_no_exit_criterion_and_the_build_says_so(self):
        self.assertEqual(propose.engine_exit_criterion("S9_MINT_TRAIN_VERDICT"), "")
        owed = propose.the_criterion_the_engine_owes()
        self.assertTrue(owed)
        self.assertIn("exit_criterion", owed)
        stated = self.plan().exit_criterion.stated
        self.assertIn("DECLARES NO exit_criterion", stated)
        self.assertIn(owed, stated)

    def test_a_criterion_the_engine_did_state_would_be_quoted_instead(self):
        """The reading is live, so the day the spec states one this is held to it.

        The mutation that proves it: put a criterion on the node and the build's
        sentence changes to quote it. Restored afterwards, because
        `default_spec()` is cached for the process.
        """
        node = diagnosis.default_spec().node_index["S9_MINT_TRAIN_VERDICT"]
        self.addCleanup(node.pop, "exit_criterion", None)
        node["exit_criterion"] = "the adapter beats baseline_score on the eval set"
        stated = self.plan().exit_criterion.stated
        self.assertIn("the adapter beats baseline_score on the eval set", stated)
        self.assertNotIn("DECLARES NO exit_criterion", stated)

    def test_the_criterion_names_the_measured_baseline_and_what_these_rows_resolve(self):
        """Every number in it is arithmetic on two measured facts, and shown."""
        plan = self.plan()
        stated = plan.exit_criterion.stated
        floor = propose.discordant_rows_that_could_resolve(1)
        for fragment in (
            "0.55",                                   # the measured baseline
            "100",                                    # the counted rows
            str(floor),                               # rows that must change
            str(propose.evals.mcnemar(floor, 0)),     # what that p-value is
            "NO EVIDENCE",
        ):
            self.assertIn(fragment, stated, f"the criterion never says {fragment!r}")

    def test_the_criterion_keeps_what_it_checks_apart_from_what_it_cannot(self):
        """Two halves, and the second one makes no claim about a model.

        The criterion has to STATE what a fine-tune is really held to - that is
        the whole point of writing it before the run - and the risk in doing so
        is that a reader takes the stated sentence for the checked one. So the
        structure is asserted rather than a form of words: everything after
        "WHAT IT IS HELD TO INSTEAD:" is what the executor actually verifies,
        and it must not mention the adapter or beating anything.

        **REWRITTEN TO THE NEW BEHAVIOUR RATHER THAN LOOSENED, and the sentence
        it used to require is exactly what went stale.** It asserted *NOTHING
        IN THIS HARNESS CAN CHECK THAT SENTENCE*, and something in this harness
        can: `score_the_adapter` registered and the LoRA recipe declares kind
        `eval`. The claim this test guards did NOT go away - it narrowed. A run
        with no completed eval run to be compared against still cannot check
        the sentence, still draws the trial, and its held-to half must still
        make no claim about a model. What changed is the reason, from *nothing
        can* to *this conversation has nothing to compare against*, which is
        the difference between a thing to wait for and a thing to do. The other
        variant - where the comparison IS drawn and the criterion IS the real
        one - is checked in
        `tests/test_the_training_build_scores_what_it_trains.py`; this is the
        one that stops.
        """
        plan = self.plan()
        self.assertEqual(plan.id, "lora_trial_run", "this is the stopping variant")
        stated = plan.exit_criterion.stated
        self.assertIn("does not run the fine-tune to a comparison", stated)
        self.assertIn("CANNOT CHECK THAT SENTENCE", stated)
        # And the reason is about THIS RUN, not about the harness, whenever the
        # instrument is actually here - the sentence a person can act on.
        if propose.the_adapter_scorer_is_registered():
            self.assertIn("THE INSTRUMENT IS HERE", stated)
            self.assertIn("run_eval", stated)
        marker = "WHAT IT IS HELD TO INSTEAD:"
        self.assertIn(marker, stated)
        checked = stated.split(marker, 1)[1].lower()
        for forbidden in ("adapter", "beat", "better", "improve"):
            self.assertNotIn(
                forbidden,
                checked,
                f"what this build is HELD TO says {forbidden!r}, and it checks "
                "nothing of the kind",
            )

    def test_the_builds_criterion_is_checked_against_a_step_the_build_runs(self):
        plan = self.plan()
        self.assertEqual(plan.exit_criterion.source, "outputs")
        step_id, _, output = plan.exit_criterion.subject.partition(".")
        step = plan.step(step_id)
        self.assertIn(output, [item.name for item in step.produces])

    def test_a_run_the_recipe_refused_does_not_satisfy_the_criterion(self):
        """`exit_code equals 0` and not `ok exists`, checked by running it.

        `recipes/hf-peft-lora/entrypoint.py` returns 3 on a red preflight and 4
        on a config it cannot use, and both of those are runs that produced no
        measurement. A criterion that passed on them would be exactly the "a
        step that cannot show it worked did not work" failure.
        """
        criterion = self.plan().exit_criterion
        self.assertTrue(criterion.met({"trial": {"exit_code": 0}}).ok)
        for refused in (3, 4, 1, -1):
            self.assertFalse(
                criterion.met({"trial": {"exit_code": refused}}).ok,
                f"exit code {refused} satisfied the criterion",
            )
        self.assertFalse(criterion.met({"trial": {}}).ok)


# ---------------------------------------------------------------------------
# The claim the whole shape rests on.


class NothingHereCanScoreAnAdapterTest(TrainingBuildTestCase):
    """THE CANARY. Both rosters are pinned; either one moving means re-read.

    The build stops before the fine-tune because nothing here can measure what a
    fine-tune produces. That is a statement about the registry and about
    `recipes/`, not an opinion, and it is the kind of statement this repository
    has watched go false twice while a sentence about it stayed in the file.

    **AND HALF OF IT HAS NOW GONE FALSE, WHICH IS WHY THE CANARY WAS HERE.**
    `recipes/hf-peft-lora` declares kind `eval` and `score_the_adapter` drives
    it, so the sandbox CAN be asked to score what it trained - see
    `tests/test_an_adapter_is_scored_where_it_was_made.py`. The half that has
    not moved is the roster of tools that score through a CONNECTION, and the
    two tests below now pin one each: exactly one shipped recipe can evaluate,
    and the thing that scores an adapter is not a connection. The class keeps
    its name so the history is legible; what it guards is stated test by test.
    """

    def test_every_tool_that_can_score_a_model_goes_through_a_connection(self):
        self.assertEqual(
            propose.tools_that_score_a_model(),
            ("measure_baseline", "run_eval", "try_prompt"),
            "the roster of tools that can put text in front of a model has "
            "changed. Re-read app/tools/propose.py's training section: it says "
            "no build can score a trained adapter BECAUSE every scorer here "
            "reads `providers`, and a provider is a connection. If the new one "
            "can score something that is not a connection, the full fine-tune "
            "and the comparison against the baseline are now drawable and this "
            "build should grow them.",
        )
        for name in propose.tools_that_score_a_model():
            self.assertIn(propose.THE_SCORING_READ, REGISTRY.get(name).reads)

    def test_a_lora_adapter_is_not_a_kind_of_connection_this_product_has(self):
        from app import providers

        self.assertEqual(providers.ADAPTERS, ("openai-compatible", "ollama"))

    def test_the_detector_would_notice_a_recipe_that_could(self):
        """The positive control for the canary below, and it is free.

        `support.FIXTURE_RECIPES` ships one recipe declaring kind `eval`, so
        inside a test sandbox the detector has something real to find. Without
        this, "no shipped recipe can evaluate" would pass just as well if the
        function returned `()` for every tree it was ever pointed at.
        """
        self.assertIn("noisy", propose.recipes_that_could_score_an_adapter())

    def test_exactly_one_shipped_recipe_can_evaluate_and_it_is_the_lora_one(self):
        """THE CANARY FIRED, AND THIS IS WHAT IT WAS FIRING ABOUT.

        It read `assertEqual(recipes_that_could_score_an_adapter(), ())` and it
        went red the day `recipes/hf-peft-lora/recipe.toml` grew `kinds =
        ["train", "eval"]`. That is the canary working: `run_in_sandbox` CAN
        now be asked to score what it trained, `app/tools/training.py`'s
        `score_the_adapter` is the tool that asks, and
        `tests/test_an_adapter_is_scored_where_it_was_made.py` is where that is
        checked.

        Rewritten to the new state rather than deleted or widened, because the
        thing it guards has not gone away: it is still true that a build must
        not claim an adapter can be scored by a recipe that cannot score one,
        and it is still true that a recipe quietly growing `eval` or `convert`
        should make somebody re-read this. So the assertion is now an EQUALITY
        against exactly the one recipe that ships with the kind - a second
        recipe declaring one turns it red, and `hf-peft-lora` losing the kind
        turns it red too.

        Read off the real `recipes/` tree, not the fixture one:
        `support.sandbox()` points `jobspec.RECIPES_ROOT` at fixture recipes and
        one of them declares kind `eval`, which is correct for the runner's
        tests and is not the product's state.
        """
        previous = jobspec.RECIPES_ROOT
        jobspec.RECIPES_ROOT = REPO_ROOT / "recipes"
        try:
            shipped = jobspec.available_recipes()
            self.assertTrue(shipped)
            self.assertIn(propose.THE_LORA_RECIPE, shipped)
            self.assertEqual(
                propose.recipes_that_could_score_an_adapter(),
                ("hf-peft-lora", "hf-quantize"),
                "the set of shipped recipes that can evaluate or convert a "
                "model has changed. If one was added, the training build's "
                "sentence about what can score an adapter is now wrong about "
                "it; if hf-peft-lora lost the kind, score_the_adapter cannot "
                "run at all.",
            )
            self.assertIn(
                propose.THE_SCORING_KINDS[0],
                jobspec.load_recipe(propose.THE_LORA_RECIPE).kinds,
            )
        finally:
            jobspec.RECIPES_ROOT = previous

    def test_the_second_evaluating_recipe_refuses_to_score_an_adapter(self):
        """WHY THE ROSTER ABOVE GREW, and why that is not a widened guarantee.

        `hf-quantize` was added 2026-09-09 to answer `NO_TRAIN__QUANTIZE` with
        numbers instead of advice, and it declares `eval` because it has to
        measure both arms in one process. That put it in a roster whose name
        says "could score an adapter" - and it CANNOT. It has no peft in its
        lockfile and no code path that applies deltas.

        THAT IS THE DANGEROUS PART, because `score_the_adapter` drives whichever
        recipe the SANDBOX was pinned to. A sandbox pinned to hf-quantize would
        reach its eval kind carrying `adapter_dir`, every row would be answered
        by the UNADAPTED base, and the result would be reported as the
        adapter's score: a real number about a different model, which is the
        failure `_adapter_at` reads `adapter_config.json` to prevent.

        So the recipe refuses, and this pins the refusal. Widening the roster
        without this test would have traded a red canary for a silent wrong
        number.
        """
        entrypoint = (REPO_ROOT / "recipes" / "hf-quantize" / "entrypoint.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'if config.get("adapter_dir"):',
            entrypoint,
            "hf-quantize no longer refuses a job naming an adapter_dir, so a "
            "sandbox pinned to it would score the unadapted base and report it "
            "as the adapter's score.",
        )
        # The PINNED PACKAGES, not the whole file: this lockfile's header
        # explains in prose that hf-peft-lora is the one pinning peft, and
        # matching that sentence would make this assertion pass or fail on a
        # comment rather than on what gets installed.
        pinned = [
            line.split("==")[0].strip().lower()
            for line in (REPO_ROOT / "recipes" / "hf-quantize" / "requirements.lock")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertIn("bitsandbytes", pinned, "the positive control: this is a "
                      "quantisation recipe and its quantiser must be pinned, "
                      "or the parse above is reading nothing.")
        self.assertNotIn(
            "peft",
            pinned,
            "hf-quantize grew peft. If it can now apply an adapter, the "
            "refusal above is wrong and this recipe's docstring is wrong.",
        )

    def test_the_thing_that_scores_an_adapter_is_not_a_connection(self):
        """The other half of the canary, and it did NOT move.

        `score_the_adapter` exists now, and the reason the roster above is
        unchanged is the reason it can be pointed at an adapter at all: it does
        not read `providers`, because there is no connection in the path. The
        day something scores an adapter THROUGH a connection, the roster grows
        and the test above it goes red.
        """
        spec = REGISTRY.get("score_the_adapter")

        self.assertIsNotNone(spec, "the adapter scorer is no longer registered")
        self.assertNotIn(propose.THE_SCORING_READ, spec.reads)
        self.assertNotIn("score_the_adapter", propose.tools_that_score_a_model())
        self.assertEqual(spec.measures, ())

    def test_the_sentence_names_the_rosters_it_read(self):
        said = propose.why_the_full_run_is_not_drawn()
        for name in propose.tools_that_score_a_model():
            self.assertIn(name, said)
        self.assertIn(propose.THE_SCORING_READ, said)
        self.assertIn(said, self.plan().because)

    def test_the_build_runs_no_training_tool_that_would_hand_over_an_adapter(self):
        """`start_training` is not a step, and neither is anything that scores.

        The full fine-tune is the thing that is deliberately absent. Asserting
        the step list is what stops it being added later without anybody
        re-reading why it is not here.
        """
        plan = self.plan()
        tools = [step.tool for step in plan.steps]
        self.assertNotIn("start_training", tools)
        self.assertNotIn("run_eval", tools)
        self.assertNotIn("measure_baseline", tools)
        self.assertNotIn("try_prompt", tools)


# ---------------------------------------------------------------------------
# The build itself.


class TheBuildDoesTheHalfThatCanBeCheckedTest(TrainingBuildTestCase):
    def test_the_steps_are_the_ones_the_coverage_entry_names(self):
        plan = self.plan()
        self.assertEqual(
            [(step.id, step.tool) for step in plan.steps],
            [
                ("rank", "find_models"),
                ("config", "read_model_config"),
                ("fits", "can_this_machine_train"),
                ("leak", "check_split_leakage"),
                ("sandbox", "make_sandbox"),
                ("trial", "run_in_sandbox"),
            ],
        )
        for step in plan.steps:
            self.assertIn(step.tool, propose.COVERAGE["TRAIN__LORA_SFT"])

    def test_nothing_is_built_or_downloaded_before_the_fit_and_the_leak_check(self):
        """The ordering is a data dependency the graph checks, not an assertion."""
        plan = self.plan()
        self.assertEqual(set(plan.step("sandbox").needs), {"fits", "leak"})
        self.assertEqual(set(plan.step("trial").needs), {"sandbox"})
        waves = plan.waves()
        self.assertLess(waves.index(("fits",)), len(waves) - 1)
        self.assertEqual(waves[-1], ("trial",))

    def test_the_run_takes_its_sandbox_from_the_step_that_made_it(self):
        """A `Ref`, so the executor cannot run the trial in whatever is newest."""
        plan = self.plan()
        referenced = dict(plan.step("trial").refs())
        self.assertIn("name", referenced)
        self.assertEqual(referenced["name"].step, "sandbox")
        self.assertEqual(referenced["name"].output, "sandbox_name")

    def test_the_fit_criterion_is_yes_and_unknown_is_not_permission(self):
        criterion = self.plan().step("fits").exit_criterion
        self.assertTrue(criterion.met({"answer": "YES"}).ok)
        for other in ("NO", "UNKNOWN", "", None):
            self.assertFalse(
                criterion.met({"answer": other}).ok, f"{other!r} passed the fit check"
            )

    def test_the_leak_criterion_separates_a_clean_check_from_one_that_did_not_run(self):
        """Driven through the REAL tool, because that is where the trap is.

        `check_split_leakage` reports a check it could not run in the same shape
        as a clean one: `leaked_rows` is 0 either way. A criterion on that field
        would pass on a check that never looked - which reads to the person as
        "your split is clean" and means "we could not tell". The field that
        separates them is `leak_rate`, which is null unless rows were compared,
        and this proves both halves against results the tool actually produced.
        """
        train = self.training_file()
        evaluation = self.eval_file()
        criterion = self.plan().step("leak").exit_criterion

        clean = REGISTRY.call(
            "check_split_leakage",
            {"train_path": str(train), "eval_path": str(evaluation)},
            actor=evidence.USER,
            thread_id=1,
        )
        self.assertTrue(clean["ran"])
        self.assertEqual(clean["leaked_rows"], 0)
        self.assertTrue(criterion.met(clean).ok)

        never_ran = REGISTRY.call(
            "check_split_leakage",
            {"train_path": str(self.root / "not-here.jsonl"), "eval_path": str(evaluation)},
            actor=evidence.USER,
            thread_id=1,
        )
        self.assertFalse(never_ran["ran"])
        self.assertEqual(
            never_ran["leaked_rows"],
            0,
            "the trap this criterion is written around has gone: a check that "
            "did not run no longer reports zero leaked rows",
        )
        self.assertFalse(
            criterion.met(never_ran).ok,
            "a leak check that never ran satisfied the criterion",
        )

        leaking = REGISTRY.call(
            "check_split_leakage",
            {"train_path": str(evaluation), "eval_path": str(evaluation)},
            actor=evidence.USER,
            thread_id=1,
        )
        self.assertTrue(leaking["ran"])
        self.assertGreater(leaking["leaked_rows"], 0)
        self.assertFalse(criterion.met(leaking).ok)

    def test_the_card_is_read_first_only_when_nobody_has_measured_it(self):
        with_measured_card = self.plan()
        self.assertNotIn("card", [step.id for step in with_measured_card.steps])

        situation = self.situation()
        plan = propose.propose(
            self.variant(
                situation, origins={**situation.origins, "vram_gb": diagnosis.STATED}
            )
        )
        self.assertEqual(plan.steps[0].id, "card")
        self.assertEqual(plan.steps[0].tool, "inspect_hardware")
        self.assertIn("card", plan.step("fits").needs)
        criterion = plan.step("card").exit_criterion
        self.assertTrue(criterion.met({"provenance": {"vram_gb": "measured"}}).ok)
        self.assertFalse(criterion.met({"provenance": {"vram_gb": "defaulted"}}).ok)

    def test_the_config_step_demands_the_term_that_was_once_left_out(self):
        """A config with no vocabulary sizes no logits buffer, so it is not a pass."""
        criterion = self.plan().step("config").exit_criterion
        self.assertTrue(criterion.met({"geometry": {"vocab_size": 151936}}).ok)
        self.assertFalse(criterion.met({"geometry": None}).ok)
        self.assertFalse(criterion.met({"geometry": {}}).ok)

    def test_the_only_approval_the_build_needs_is_the_one_that_spends_the_machine(self):
        plan = self.plan()
        self.assertEqual(plan.approvals_required(), ("trial",))

    def test_removing_any_of_the_tools_makes_the_build_refuse(self):
        """The mutation check, over this build's own tools rather than in general."""
        plan = self.plan()
        for step in plan.steps:
            smaller = Registry()
            for spec in REGISTRY:
                if spec.name != step.tool:
                    smaller.add(spec)
            with self.assertRaises(BuildInvalid) as raised:
                plan.validate(registry=smaller)
            self.assertIn(step.tool, str(raised.exception))


# ---------------------------------------------------------------------------
# The numbers, and where each came from.


class EveryNumberInThePlanWasReadTest(TrainingBuildTestCase):
    def test_the_method_rank_and_epochs_come_from_the_engines_own_size_row(self):
        situation = self.situation()
        row = situation.result.size_row
        self.assertTrue(row)
        because = propose.propose(situation).because
        self.assertIn(repr(situation.result.proposed_method), because)
        for cell in ("rank", "epochs", "examples", "realistic_gain"):
            self.assertIn(repr(row[cell]), because)

    def test_the_lora_rank_passed_to_the_run_is_the_engines_band_and_not_a_choice(self):
        situation = self.situation()
        plan = propose.propose(situation)
        self.assertEqual(
            plan.step("trial").arguments["config"]["lora_r"],
            situation.result.size_row["rank_min"],
        )

    def test_the_hand_off_and_the_route_are_quoted_from_the_spec(self):
        situation = self.situation()
        because = propose.propose(situation).because
        self.assertIn(
            propose.engine_node_says("S9_MINT_TRAIN_VERDICT", "hand_off"), because
        )
        self.assertIn(repr(situation.result.route), because)
        self.assertIn(str(situation.result.hardware_reference), because)

    def test_the_environment_records_what_the_recipe_locks_on_this_machine(self):
        plan = self.plan()
        pinned = propose.the_recipe_on_this_machine()
        self.assertTrue(pinned["pinned"])
        self.assertEqual(plan.environment.installs, tuple(pinned["installs"]))
        self.assertEqual(plan.environment.python, pinned["python"])
        self.assertTrue(plan.environment.installs)

    def test_every_wall_clock_is_unknown_and_says_how_to_find_out(self):
        """The named gap, and this build is the first thing that closes it."""
        plan = self.plan()
        for step in plan.steps:
            estimate = step.cost.wall_clock
            self.assertEqual(estimate.provenance, build.UNKNOWN, step.id)
            self.assertIsNone(estimate.value, step.id)
            self.assertTrue(estimate.find_out_by.strip(), step.id)
        self.assertIn(
            "THIS STEP IS THE ANSWER", plan.step("trial").cost.wall_clock.find_out_by
        )

    def test_the_token_and_request_costs_are_proved_off_the_tools_own_reads(self):
        """Nought, not negligible - and the reason is a line in each registration.

        `Estimate.none` is the one INFERRED estimate with nothing behind it, and
        the thing that makes it honest is that the `how` quotes the declaration
        it is derived from. So both halves are checked: the number is zero, and
        the sentence says which read is absent.
        """
        plan = self.plan()
        for step in plan.steps:
            for estimate in (step.cost.model_tokens, step.cost.model_requests):
                self.assertEqual(estimate.provenance, build.INFERRED, step.id)
                self.assertEqual(estimate.value, 0.0, step.id)
                self.assertIn(propose.THE_SCORING_READ, estimate.how, step.id)

    def test_a_tool_that_writes_config_files_is_not_described_as_writing_rows(self):
        """The sentence `_disk_cost` used to give every non-filesystem writer.

        `find_models` and `read_model_config` declare
        `writes=("model_config_cache",)` and what they write is a JSON file per
        model. The old middle branch called that *rows in the harness database,
        no files*, which is a true-sounding claim about somebody's disk in a
        plan they are about to approve. The positive control is in the same
        test: a tool that really does write rows still gets the rows sentence.
        """
        plan = self.plan()
        rows_sentence = "rows in the harness database"
        for step_id in ("rank", "config"):
            how = plan.step(step_id).cost.disk.how
            self.assertIn("model_config_cache", how)
            self.assertNotIn(rows_sentence, how)
            self.assertIn("FILES", how)
        self.assertIn(rows_sentence, propose._disk_cost("measure_eval_set").how)

    def test_the_trial_states_the_three_things_it_writes_and_measures_none(self):
        estimate = self.plan().step("trial").cost.disk
        self.assertEqual(estimate.provenance, build.UNKNOWN)
        for written in ("weights", "adapter", "log"):
            self.assertIn(written, estimate.how)


# ---------------------------------------------------------------------------
# Egress.


class TheEgressIsDeclaredAndSaysWhatItIsForTest(TrainingBuildTestCase):
    def test_the_environment_declares_egress_and_the_sandbox_asks_for_the_same_thing(self):
        plan = self.plan()
        self.assertTrue(plan.environment.egress)
        self.assertTrue(plan.environment.egress_reason.strip())
        asked = plan.step("sandbox").arguments
        self.assertIs(asked["egress"], True)
        self.assertEqual(asked["egress_reason"], plan.environment.egress_reason)

    def test_the_reason_is_about_the_hub_and_not_about_the_persons_model(self):
        """`_egress_for`'s sentence is about `providers` and would be false here."""
        reason = self.plan().environment.egress_reason
        self.assertIn("huggingface.co", reason)
        self.assertIn("huggingface_hub", reason)
        self.assertNotIn("go to the model you connected", reason)
        self.assertIn("HF_HUB_OFFLINE", reason)

    def test_a_build_that_declared_no_egress_would_be_refused_by_validate(self):
        """The mutation: the environment is not a description, it is checked."""
        import dataclasses

        plan = self.plan()
        with self.assertRaises(BuildInvalid) as raised:
            dataclasses.replace(
                plan,
                environment=dataclasses.replace(
                    plan.environment, egress=False, egress_reason=""
                ),
            )
        self.assertIn("egress", str(raised.exception))


# ---------------------------------------------------------------------------
# The refusals. Each one is checked against the case that should NOT refuse.


class TheBuildRefusesWhenItWouldBeTheatreTest(TrainingBuildTestCase):
    def test_the_control_builds(self):
        """Every refusal below is one change away from this. If this stops
        building, every `assertRaises` beneath it is passing for the wrong
        reason."""
        self.assertEqual(self.plan().id, "lora_trial_run")

    def test_it_will_not_choose_the_model(self):
        gap = self.refusal(base_model="")
        self.assertIn("base_model", gap.needs)
        self.assertIn("find_models", gap.detail)
        self.assertIn("licence", gap.detail)

    def test_it_will_not_choose_the_example_length(self):
        gap = self.refusal(max_seq_len=0)
        self.assertIn("max_seq_len", gap.needs)
        self.assertIn("two different runs", gap.detail)

    def test_the_recipe_must_be_built_on_this_machine(self):
        """The engine hands off to a pinned backend; an unbuilt one is not a pin."""
        venv = Path(jobspec.RECIPES_ROOT) / propose.THE_LORA_RECIPE / ".venv"
        for interpreter in (venv / "Scripts" / "python.exe", venv / "bin" / "python"):
            interpreter.unlink()
        self.assertFalse(propose.the_recipe_on_this_machine()["pinned"])
        gap = self.refusal()
        self.assertIn("list_recipes", gap.detail)
        self.assertIn(propose.THE_LORA_RECIPE, gap.detail)

    def test_training_data_that_is_not_jsonl_is_refused(self):
        csv = self.root / "train.csv"
        csv.write_text("text\nhello\n", encoding="utf-8")
        gap = self.refusal(dataset_path=str(csv))
        self.assertIn("dataset_path", gap.needs)
        self.assertIn(".jsonl", gap.detail)

    def test_training_on_the_eval_set_is_refused(self):
        evaluation = self.eval_file()
        gap = self.refusal(dataset_path=str(evaluation), eval_path=str(evaluation))
        self.assertIn("eval_path", gap.needs)
        self.assertIn("recall of the training set", gap.detail)

    def test_an_eval_set_inside_the_training_data_is_refused_before_the_format_is(self):
        """The folder case, and the message has to be about the leak.

        A folder fails the JSONL check too, and "convert it to JSONL" sends a
        person off to convert a directory whose real problem is that the answers
        are in it.
        """
        folder = self.root / "bundle"
        folder.mkdir()
        inside = folder / "eval.jsonl"
        inside.write_text(self.eval_file().read_text(encoding="utf-8"), encoding="utf-8")
        gap = self.refusal(dataset_path=str(folder), eval_path=str(inside))
        self.assertIn("inside the training data", gap.detail)
        self.assertNotIn(".jsonl file", gap.detail)

    def test_a_count_of_a_different_file_does_not_count_as_the_eval_set(self):
        other = self.root / "somewhere-else.jsonl"
        other.write_text("{}\n", encoding="utf-8")
        gap = self.refusal(
            hows={"eval_size_n": f"counted 100 rows in {other}"}
        )
        self.assertIn("eval_size_n", gap.needs)
        self.assertIn("measure_eval_set", gap.detail)
        self.assertIn(Subject.of_path(str(other)).key, gap.detail)

    def test_a_baseline_nobody_read_is_not_something_to_beat(self):
        situation = self.situation()
        gap = self.refusal_from(
            self.variant(
                situation,
                origins={**situation.origins, "baseline_score": diagnosis.ASSERTED},
            )
        )
        self.assertIn("measure_baseline", gap.detail)
        self.assertIn("two facts", gap.detail)

    def test_a_measured_count_with_no_number_behind_it_is_refused(self):
        """`_an_integer` answers 0 for anything it cannot read, and a 0 would
        flow into every figure in the plan and print a refusal derived from it."""
        situation = self.situation()
        gap = self.refusal_from(
            self.variant(situation, values={**situation.values, "eval_size_n": None})
        )
        self.assertIn("eval_size_n", gap.needs)
        self.assertIn("nothing will be made up", gap.detail)

    def test_a_measured_baseline_with_no_number_behind_it_is_refused(self):
        """Origin and value travel together out of the ledger, so this is a hand
        case - and every figure in the plan is arithmetic on that score, so a
        missing one would silently become zero and print a baseline nobody had."""
        situation = self.situation()
        gap = self.refusal_from(
            self.variant(situation, values={**situation.values, "baseline_score": None})
        )
        self.assertIn("baseline_score", gap.needs)
        self.assertIn("nothing will be made up", gap.detail)

    def test_an_eval_set_that_could_not_resolve_an_improvement_is_refused(self):
        """The arithmetic is exact, and the row count that would fix it is shown.

        Reached by hand rather than through the fact sheet: an `eval_size_n` of
        ten fails G0 and the engine routes it to BLOCKED__BUILD_EVAL_SET, so it
        never reaches this proposer through `propose_build`. Thirty rows pass
        G0 and still cannot resolve anything at a 0.55 baseline, which is the
        gap this refusal exists for - the gate asks whether an eval set EXISTS
        and this asks whether it could answer THIS question.
        """
        situation = self.situation()
        small = self.variant(
            situation, values={**situation.values, "eval_size_n": 12}
        )
        gap = self.refusal_from(small)
        needed = propose.questions_that_could_resolve(0.55, 1)
        self.assertEqual(gap.needs, (f"eval_size_n >= {needed}",))
        self.assertIn("NO EVIDENCE", gap.detail)
        self.assertIn(str(needed), gap.detail)
        self.assertIn(str(propose.evals.mcnemar(6, 0)), gap.detail)

    def test_the_row_floor_is_the_one_evals_mcnemar_actually_reaches(self):
        """Asked of the real function rather than restated, and non-vacuously.

        The floor decides a refusal that stops a GPU run, so a floor that drifted
        from `evals.compare`'s own idea of evidence would refuse work the bench
        would have resolved, or plan work it could not. One below the floor must
        fail the threshold and the floor itself must reach it.
        """
        floor = propose.discordant_rows_that_could_resolve(1)
        self.assertLessEqual(propose.evals.mcnemar(floor, 0), propose.RESOLVED_AT)
        self.assertGreater(propose.evals.mcnemar(floor - 1, 0), propose.RESOLVED_AT)

    def test_the_criterion_prints_the_number_its_own_derivation_gives(self):
        """A rounding error is an invented number wearing arithmetic's clothes.

        `int((1 - 0.55) * 100)` is 44 in binary floating point and the sentence
        beside it says a hundred rows at a measured 0.55 - which is 45 wrong.
        Over a grid of every whole percent from 1 to 99 against 0 to 400 rows,
        144 of the 39,600 points came out one question LOW, and this repository's
        first invariant is that no displayed number is invented.

        Held to `Fraction(repr(score))` - the exact decimal the score is printed
        as - rather than to a second float expression, which would agree with the
        first one's error.
        """
        from fractions import Fraction

        self.assertEqual(propose.questions_wrong_now(0.55, 100), 45)
        for percent in range(1, 100):
            score = percent / 100
            for rows in (0, 1, 12, 30, 60, 100, 137, 400):
                with self.subTest(score=score, rows=rows):
                    self.assertEqual(
                        propose.questions_wrong_now(score, rows),
                        int(Fraction(rows) * (1 - Fraction(repr(score)))),
                    )

    def test_a_score_that_is_not_a_number_answers_rather_than_raising(self):
        """The regression the exact arithmetic could have introduced.

        `Fraction('nan')` is a ValueError and the float expression it replaced
        returned 0. No measured score is ever nan or inf - which is why this is
        a floor and not a behaviour - but a proposer that crashes where it used
        to answer would be a worse defect than the rounding it was fixing.
        """
        for score in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(score=score):
                self.assertEqual(propose.questions_wrong_now(score, 100), 0)
                self.assertEqual(propose.questions_that_could_resolve(score, 1), 0)

    def test_the_rows_needed_is_the_division_the_refusal_says_it_is(self):
        """The refusal prints "6 / (1 - 0.8), rounded up" and used to say 31.

        Two of these crossed the floor and turned into REFUSALS: thirty graded
        rows at a measured baseline of 0.8 has exactly six wrong rows, which is
        the discordant floor, and the person was told they could not show a
        fine-tune worked and needed a thirty-first row. Thirty is the G0
        threshold, so this was reachable by the smallest eval set the product
        will accept at all.
        """
        from fractions import Fraction

        floor = propose.discordant_rows_that_could_resolve(1)
        for score in (0.8, 0.9):
            with self.subTest(score=score):
                self.assertEqual(
                    propose.questions_that_could_resolve(score, 1),
                    int(-((-Fraction(floor)) // (1 - Fraction(repr(score))))),
                )
                # And the row count it names really does reach the floor.
                needed = propose.questions_that_could_resolve(score, 1)
                self.assertGreaterEqual(
                    propose.questions_wrong_now(score, needed), floor
                )
                self.assertLess(
                    propose.questions_wrong_now(score, needed - 1), floor
                )

    def test_the_smallest_eval_set_the_gate_accepts_gets_a_build_at_a_high_baseline(self):
        """The behaviour the two above are about, driven through the proposer.

        Thirty rows at 0.8: six wrong, the floor is six, so the comparison can
        resolve and the build is drawn. It was refused.
        """
        situation = self.situation()
        for score, rows in ((0.8, 30), (0.9, 60)):
            with self.subTest(score=score, rows=rows):
                plan = propose.propose(
                    self.variant(
                        situation,
                        values={
                            **situation.values,
                            "baseline_score": score,
                            "eval_size_n": rows,
                        },
                        hows={
                            "eval_size_n": (
                                f"counted {rows} rows in {situation.eval_path}"
                            )
                        },
                    )
                )
                self.assertIn("trial", [step.id for step in plan.steps])

    def test_a_baseline_that_gets_everything_right_is_a_different_refusal(self):
        """Because "you need 0 more rows" is arithmetic that reads as permission."""
        situation = self.situation()
        gap = self.refusal_from(
            self.variant(situation, values={**situation.values, "baseline_score": 1.0})
        )
        self.assertIn("eval rows the baseline gets wrong", gap.needs)
        self.assertNotIn("0 more than you have", gap.detail)

    def test_a_machine_with_no_accelerator_is_refused(self):
        gap = self.refusal(facts={"accelerator": diagnosis.measured("cpu_only")})
        self.assertIn("where_to_train", gap.detail)
        self.assertIn("twenty times slower", gap.detail)

    def test_a_route_this_recipe_cannot_run_is_refused_and_names_the_better_instrument(self):
        gap = self.refusal(facts={"vram_gb": diagnosis.measured(13.0)})
        self.assertIn("QLORA", gap.detail)
        self.assertIn("can_this_machine_train", gap.detail)
        self.assertIn("indexed by BASE MODEL SIZE", gap.detail)

    def test_data_already_snapshotted_into_a_sandbox_is_refused(self):
        """An experiment is resumed or disposed of, and never duplicated."""
        training = self.training_file()
        made = sandboxes.create("already-here", purpose="a prior run", data=[str(training)])
        self.addCleanup(sandboxes.destroy, made["name"])
        self.assertEqual(
            propose.sandboxes_already_holding(str(training)), (made["name"],)
        )
        gap = self.refusal(dataset_path=str(training))
        self.assertIn(made["name"], gap.detail)
        self.assertIn("delete_sandbox", gap.detail)

    def test_a_path_that_is_not_there_is_named_rather_than_planned_against(self):
        gap = self.refusal(dataset_path=str(self.root / "nothing.jsonl"))
        self.assertIn("dataset_path", gap.needs)


# ---------------------------------------------------------------------------
# The tables.


class TheCoverageTablesTellTheTruthTest(TrainingBuildTestCase):
    def test_the_outcome_is_covered_while_its_tools_are_registered(self):
        self.assertEqual(propose.training_tools_missing(), ())
        self.assertIn("TRAIN__LORA_SFT", propose.PROPOSERS)
        self.assertIn("TRAIN__LORA_SFT", propose.COVERAGE)
        self.assertNotIn("TRAIN__LORA_SFT", propose.NOT_COVERED)

    def test_the_coverage_entry_says_which_of_the_two_builds_you_get(self):
        """REWRITTEN TO THE NEW BEHAVIOUR, and it is a stronger assertion.

        It read `assertIn("STOPS THERE", entry)` and `assertIn("does not run
        the whole fine-tune", entry)`, which was the whole truth while there
        was one build. There are two now and the entry has to say BOTH - a
        reader who saw only the stopping half would be told this product cannot
        do a thing it can, and a reader who saw only the scoring half would be
        told a fine-tune runs for people whose conversation holds no eval run
        to compare it against. So the assertion is that both halves are there
        and that the entry names the condition that decides between them.
        """
        entry = propose.COVERAGE["TRAIN__LORA_SFT"]
        self.assertIn("TWO BUILDS BEHIND ONE OUTCOME", entry)
        self.assertIn("STOPS AT THE TRIAL", entry)
        self.assertIn("COMPLETED EVAL RUN", entry)
        self.assertIn("run_eval", entry)
        self.assertIn(propose.THE_ADAPTER_SCORER, entry)
        # Every tool either build runs is named in it, which is what the
        # executability test reads this entry for.
        for name in propose.THE_TRAINING_TOOLS:
            self.assertIn(name, entry)

    def test_the_reason_written_for_an_absent_bench_names_what_is_absent(self):
        """It cannot be exercised while the tools are here, so it is read directly."""
        reason = propose._THE_TRAINING_BENCH_NOT_HERE_YET()
        self.assertEqual(reason, {}, "the tools are registered, so there is no reason")
        for name in propose.THE_TRAINING_TOOLS:
            self.assertIsNotNone(REGISTRY.get(name), name)

    def test_the_training_outcomes_with_no_backend_blame_the_backend(self):
        """IT WAS EIGHT AND IT IS SEVEN, and the shape survived the change.

        `recipes/hf-peft-dpo/` gave `TRAIN__DPO` a backend, so it left this
        group. The loop skips whatever has a proposer rather than one named
        outcome, which is what let a second recipe land without this test having
        to be rewritten - and the reason each remaining one carries still has to
        name the backend AND both shipped recipes, because a reason that named
        only one of them would be half a sentence about what this harness holds.
        """
        for outcome in diagnosis.default_spec().train_outcomes:
            if outcome in propose.PROPOSERS:
                continue
            with self.subTest(outcome=outcome):
                self.assertIn("backend", propose.NOT_COVERED[outcome])
                self.assertIn(propose.THE_LORA_RECIPE, propose.NOT_COVERED[outcome])
                self.assertIn(propose.THE_DPO_RECIPE, propose.NOT_COVERED[outcome])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
