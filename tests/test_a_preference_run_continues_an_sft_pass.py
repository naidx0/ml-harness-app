"""The second training backend, and the four things that make it not a copy.

## What moved

`TRAIN__DPO` sat in `propose.NOT_COVERED` under the group reason `_TRAINING`,
whose sentence named its own expiry:

    recipes/ holds one real trainer, hf-peft-lora, and it does a LoRA
    supervised fine-tune and nothing else: NO PREFERENCE OPTIMISATION, no
    reinforcement loop...

`recipes/hf-peft-dpo/` makes that clause false. This is the third time a shared
reason in `propose.py` has gone half true - the eval bench, the retrieval bench,
the training backends - and the fix is the same each time: narrow the reason to
the outcomes it still answers for, rather than leave the product telling
somebody it cannot do a thing it can.

## The four differences, each a refusal rather than a step

1. **The prerequisite is enforced here or nowhere.** `docs/diagnosis_engine.yaml`
   declares `DPO: {prerequisite: LORA_SFT}` in the methods table AND on
   `S5_PREFERENCES_NOT_DEMONSTRATIONS`. Nothing in `app/diagnosis.py` reads
   either - measured by grep - so the declaration was inert, and a proposer is
   the only thing positioned to act on it.
2. **A different data contract.** prompt/chosen/rejected, not a `text`. Pointed
   at the SFT recipe's file, both this build and the recipe itself name
   `hf-peft-lora` rather than reporting a zero.
3. **The count is read off the ledger, not off the file.** This proposer opens
   nothing; `count_preference_pairs` is the instrument, and what is checked is
   that the number on file is a MEASURED count OF THE FILE THIS PLAN WOULD
   TRAIN ON.
4. **It stops at the trial for a reason about the ARTIFACT.** `score_the_adapter`
   is registered and takes a base model plus an adapter directory. trl merges
   the SFT adapter into the base weights before attaching the new one
   (`trl/trainer/dpo_trainer.py:578-580`, read in the installed 0.24.0), so what
   this run produces applies to the merged weights. Handed the pair the scorer
   expects, it would score a model nobody trained and file the number under this
   run's name - which is worse than having no number.

## What is NOT asserted here

That a DPO run trains anything. That needs the recipe's own 4.8 GB pinned
environment and a GPU-hour, and it is named in `docs/THE_PLAN.md` as work a test
suite cannot stand in for. What IS asserted against the real shipped recipe is
everything before the weights load: that it is discovered, that it refuses a
demonstrations file, that it refuses below its own floor, and that with no
pinned environment it refuses with an exit code rather than training in whatever
happened to be importable.
"""

import dataclasses
import json
import subprocess
import sys
import unittest
from pathlib import Path

from app import diagnosis, jobspec
from app.tools import propose
import diagnosis_fixtures
import support


REPO = Path(__file__).resolve().parents[1]
RECIPE_DIR = REPO / "recipes" / "hf-peft-dpo"


class PreferenceBuildTestCase(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        support.pin_a_training_recipe(propose.THE_DPO_RECIPE)

    # -- the files --------------------------------------------------------

    def preference_file(self, rows: int = 4000, name: str = "pairs.jsonl") -> Path:
        path = self.root / name
        path.write_text(
            "\n".join(
                json.dumps(
                    {"prompt": f"ticket {i}", "chosen": "the reply we want",
                     "rejected": "the reply we do not"}
                )
                for i in range(rows)
            ),
            encoding="utf-8",
        )
        return path

    def eval_file(self, rows: int = 100, name: str = "eval.jsonl") -> Path:
        path = self.root / name
        path.write_text(
            "\n".join(
                json.dumps({"q": f"question {i}", "a": "yes"}) for i in range(rows)
            ),
            encoding="utf-8",
        )
        return path

    def sft_adapter(self, name: str = "sft_adapter") -> Path:
        directory = self.root / name
        directory.mkdir(exist_ok=True)
        (directory / "adapter_config.json").write_text("{}", encoding="utf-8")
        return directory

    # -- the situation ----------------------------------------------------

    def situation(self, **over) -> propose.Situation:
        """A `Situation` for the minted verdict, filled the way `propose_build` fills one.

        The tree is NOT bypassed: `diagnose` runs for real over the fixture
        sheet. `hows` carries the derivation `count_preference_pairs` writes,
        because the proposer refuses unless `preference_pairs_n` is a measured
        count OF the file this run would train on - and a fixture that faked
        that would be a fixture that stopped proving the refusal exists.
        """
        facts = over.pop("facts", {})
        sheet = dict(diagnosis_fixtures.MINTING["TRAIN__DPO"])
        sheet.update(facts)
        result = diagnosis.diagnose(sheet)

        pairs = over.pop("dataset_path", None)
        if pairs is None:
            pairs = str(self.preference_file())
        counted = over.pop("counted_file", pairs)

        fields = {
            "outcome": result.outcome,
            "result": result,
            "values": {name: fact.value for name, fact in sheet.items()},
            "origins": {name: fact.origin for name, fact in sheet.items()},
            "hows": {
                "preference_pairs_n": (
                    "preference pairs, meaning rows carrying all of "
                    "['prompt', 'chosen', 'rejected']: counted "
                    f"{sheet['preference_pairs_n'].value} rows in {counted}"
                )
            },
            "eval_path": str(self.eval_file()),
            "dataset_path": str(pairs),
            "base_model": "Qwen/Qwen3-4B",
            "max_seq_len": 1024,
            "adapter_dir": str(self.sft_adapter()),
        }
        fields.update(over)
        return propose.Situation(**fields)

    def plan(self, **over):
        return propose.propose(self.situation(**over))

    def refusal(self, **over) -> propose.NotEnoughToPropose:
        with self.assertRaises(propose.NotEnoughToPropose) as raised:
            self.plan(**over)
        return raised.exception


# ---------------------------------------------------------------------------


class TheOutcomeIsCoveredTest(PreferenceBuildTestCase):
    def test_the_verdict_is_reachable_so_this_file_is_not_vacuous(self):
        sheet = dict(diagnosis_fixtures.MINTING["TRAIN__DPO"])
        self.assertEqual(diagnosis.diagnose(sheet).outcome, "TRAIN__DPO")

    def test_it_moved_out_of_the_uncovered_table_entirely(self):
        self.assertIn("TRAIN__DPO", propose.COVERAGE)
        self.assertNotIn("TRAIN__DPO", propose.NOT_COVERED)
        self.assertIn("TRAIN__DPO", propose.PROPOSERS)

    def test_the_group_reason_stopped_claiming_what_stopped_being_true(self):
        """THE SENTENCE THAT WENT HALF FALSE, PINNED SO IT CANNOT AGAIN.

        `_TRAINING` still answers for seven outcomes and it must not answer for
        this one, and it must not still say this harness ships no preference
        optimisation - a claim now contradicted by a directory in the tree.
        """
        self.assertNotIn("no preference optimisation", propose._TRAINING)
        self.assertIn("hf-peft-dpo", propose._TRAINING)
        for still_uncovered in (
            "TRAIN__RL_GRPO",
            "TRAIN__DISTILLATION",
            "TRAIN__FROM_SCRATCH",
        ):
            with self.subTest(outcome=still_uncovered):
                self.assertEqual(propose.NOT_COVERED[still_uncovered], propose._TRAINING)

    def test_the_coverage_entry_describes_the_build_that_exists(self):
        entry = propose.COVERAGE["TRAIN__DPO"]
        plan = self.plan()
        for step in plan.steps:
            with self.subTest(tool=step.tool):
                self.assertIn(step.tool, entry)
        self.assertIn(propose.THE_DPO_RECIPE, entry)
        self.assertIn("count_preference_pairs", entry)

    def test_the_two_tables_cannot_both_hold_it(self):
        self.assertEqual(set(propose.COVERAGE), set(propose.PROPOSERS))
        self.assertFalse(set(propose.COVERAGE) & set(propose.NOT_COVERED))


class TheRecipeIsRealTest(PreferenceBuildTestCase):
    """Asserted against `recipes/hf-peft-dpo/` on disk, not against a fixture."""

    def test_the_shipped_recipe_is_discovered_and_declares_one_kind(self):
        self.assertIn("hf-peft-dpo", jobspec.available_recipes())
        recipe = jobspec.load_recipe("hf-peft-dpo")
        self.assertEqual(recipe.kinds, ("train",))

    def test_it_declares_no_scoring_kind_and_that_is_load_bearing(self):
        """`tests/test_a_trained_adapter_is_measured_or_not_trained.py` asserts
        that exactly one recipe can score an adapter. A second one declaring
        `eval` would make `score_the_adapter`'s choice of backend ambiguous
        without anybody deciding it should be."""
        scoring = [
            name
            for name in jobspec.available_recipes()
            if set(jobspec.load_recipe(name).kinds) & {"eval", "convert"}
        ]
        self.assertNotIn("hf-peft-dpo", scoring)

    def test_the_pins_are_identical_to_the_supervised_recipe(self):
        """Deliberate duplication, and the file says so. Two recipes sharing one
        virtualenv are two plans that could drift apart with nowhere to put the
        difference - so the environments are separate even though today the
        locked versions are the same."""

        def pins(name: str) -> list[str]:
            text = (REPO / "recipes" / name / "requirements.lock").read_text(
                encoding="utf-8"
            )
            return sorted(
                line.strip()
                for line in text.splitlines()
                if line.strip() and not line.strip().startswith("#")
            )

        self.assertEqual(pins("hf-peft-dpo"), pins("hf-peft-lora"))

    def test_a_demonstrations_file_is_refused_by_name(self):
        module = self._entrypoint()
        path = self.root / "demos.jsonl"
        path.write_text(
            "\n".join(json.dumps({"text": f"example {i}"}) for i in range(80)),
            encoding="utf-8",
        )
        with self.assertRaises(SystemExit) as refused:
            module.load_pairs(path)
        self.assertIn("hf-peft-lora", str(refused.exception))
        self.assertIn("Nothing was trained", str(refused.exception).replace(".", ""))

    def test_too_few_pairs_are_refused_rather_than_trained_on(self):
        module = self._entrypoint()
        path = self.root / "few.jsonl"
        path.write_text(
            "\n".join(
                json.dumps({"prompt": "p", "chosen": "c", "rejected": "r"})
                for _ in range(module.FEWEST_PAIRS - 1)
            ),
            encoding="utf-8",
        )
        with self.assertRaises(SystemExit) as refused:
            module.load_pairs(path)
        self.assertIn(str(module.FEWEST_PAIRS), str(refused.exception))

    def test_complete_triples_are_accepted(self):
        """The control. Every refusal above is one change away from this."""
        module = self._entrypoint()
        path = self.root / "ok.jsonl"
        path.write_text(
            "\n".join(
                json.dumps({"prompt": f"p{i}", "chosen": "c", "rejected": "r"})
                for i in range(module.FEWEST_PAIRS + 10)
            ),
            encoding="utf-8",
        )
        rows = module.load_pairs(path)
        self.assertEqual(len(rows), module.FEWEST_PAIRS + 10)
        self.assertEqual(sorted(rows[0]), ["chosen", "prompt", "rejected"])

    def test_an_unmerged_state_dict_is_recognised_as_unmerged(self):
        """THE DEFECT A REAL RUN FOUND, AS A TEST OF THE DECISION IT TURNS ON.

        The adapter a preference run writes sits on SFT-MERGED weights, so the
        merged base has to travel with it. Twice this recipe saved something
        that was NOT merged - first through `trainer.model.get_base_model()`,
        which returns the model with LoRA wrappers still attached, then through
        the merged object itself, which `get_peft_model` MUTATES IN PLACE.

        **Loading that directory silently dropped every adapter key and randomly
        initialised sixty attention projections.** An artifact that loads and is
        wrong, which is the worst kind this product can produce.

        The first guard could not have caught it: it loaded the directory back
        and inspected the RESULT, and transformers has already discarded those
        keys by then. A check that cannot observe the failure it is written for
        is worse than none, because it reports success.
        """
        module = self._entrypoint()
        unmerged = [
            "model.embed_tokens.weight",
            "model.layers.0.self_attn.q_proj.base_layer.weight",
            "model.layers.0.self_attn.q_proj.lora_A.default.weight",
            "model.layers.0.self_attn.q_proj.lora_B.default.weight",
        ]
        found = module.adapter_keys_in(unmerged)
        self.assertEqual(len(found), 3)
        self.assertNotIn("model.embed_tokens.weight", found)

    def test_a_properly_merged_state_dict_passes(self):
        """The control. Without it the assertion above passes for any input."""
        module = self._entrypoint()
        self.assertEqual(
            module.adapter_keys_in(
                [
                    "model.embed_tokens.weight",
                    "model.layers.0.self_attn.q_proj.weight",
                    "model.layers.0.self_attn.v_proj.weight",
                ]
            ),
            [],
        )

    def test_both_shapes_of_wrapper_key_are_looked_for(self):
        """`peft` writes three kinds and any one of them is proof. A marker set
        that caught `lora_` alone would miss a file carrying only
        `base_layer.weight`, which is exactly what a half-merged save looks
        like."""
        module = self._entrypoint()
        self.assertEqual(sorted(module.ADAPTER_KEY_MARKERS), ["base_layer", "lora_"])
        for one in ("x.base_layer.weight", "x.lora_A.default.weight"):
            with self.subTest(key=one):
                self.assertEqual(module.adapter_keys_in([one]), [one])

    def test_with_no_pinned_environment_it_refuses_instead_of_training(self):
        """DRIVEN, NOT READ. A run that cannot have its pinned environment must
        not quietly proceed in whatever interpreter happened to be available -
        an unreproducible training run is worse than none.

        **IT ASKS THE FUNCTION RATHER THAN SPAWNING A PROCESS, and the reason is
        that the environment now exists on this machine.** Materialised
        2026-08-28: 4.7 GB, and a real DPO run drove it. So spawning the
        entrypoint would take the HAPPY path and this test would pass by never
        reaching the branch it is named for. Pointing `venv_python` at somewhere
        it is not is what keeps the refusal exercised on a machine that has the
        thing being refused.
        """
        module = self._entrypoint()
        module.RECIPE_DIR = self.root / "not-built"
        code = module.bootstrap(["--kind", "train", "--job-json", "x"])
        self.assertEqual(code, 2)

    def test_the_pinned_environment_is_real_on_this_machine(self):
        """The other half, and it is what makes the test above meaningful.

        A refusal test that passed because nothing was ever built would be a
        refusal test for a recipe nobody can run. This asserts the environment
        IS there, so the two together say: it is built, and if it were not the
        run would stop rather than improvise.
        """
        from app.tools import propose

        pinned = propose.the_recipe_on_this_machine(propose.THE_DPO_RECIPE)
        if not pinned.get("pinned"):
            self.skipTest(
                "the hf-peft-dpo environment is not built on this machine; "
                "`uv pip sync` it from the commands the refusal prints"
            )
        self.assertIn("train", pinned["kinds"])
        self.assertTrue(pinned["installs"])

    def _entrypoint(self):
        # `support.import_file` and not `exec_module` directly: importing a
        # recipe entrypoint from inside the repository writes a `.pyc` beside
        # it, which is a write into the working tree that
        # `test_the_sandbox_isolates_everything_the_product_writes` watches.
        # This was the SECOND of two importers; fixing only the first left the
        # suite still polluting, and the watcher said so.
        return support.import_file("dpo_entrypoint", RECIPE_DIR / "entrypoint.py")


def module_prefix() -> str:
    return "MLH_EVENT "


class TheBuildIsDrawnFromTheLedgerTest(PreferenceBuildTestCase):
    def test_the_control_builds(self):
        """Every refusal below is one change away from this. If this stops
        building, every `assertRaises` beneath it passes for the wrong reason."""
        self.assertEqual(self.plan().id, "dpo_trial_run")

    def test_the_steps_are_the_supervised_shape_and_end_at_the_trial(self):
        plan = self.plan()
        self.assertEqual(
            [step.tool for step in plan.steps],
            [
                "read_model_config",
                "can_this_machine_train",
                "check_split_leakage",
                "make_sandbox",
                "run_in_sandbox",
            ],
        )

    def test_the_card_is_read_first_when_nobody_has_read_it(self):
        plan = self.plan(facts={"vram_gb": diagnosis.stated(24.0)})
        self.assertEqual(plan.steps[0].tool, "inspect_hardware")
        self.assertEqual(plan.step("config").needs, ("card",))

    def test_the_run_names_this_recipe_and_its_own_environment(self):
        plan = self.plan()
        self.assertEqual(
            plan.step("sandbox").arguments["recipe"], propose.THE_DPO_RECIPE
        )
        pinned = propose.the_recipe_on_this_machine(propose.THE_DPO_RECIPE)
        self.assertTrue(pinned["pinned"])
        self.assertEqual(plan.environment.installs, tuple(pinned["installs"]))
        self.assertTrue(plan.environment.installs)

    def test_the_config_carries_the_adapter_it_continues_from(self):
        config = self.plan().step("trial").arguments["config"]
        self.assertEqual(config["adapter_dir"], str(self.sft_adapter()))
        self.assertEqual(config["dataset_path"], str(self.root / "pairs.jsonl"))

    def test_the_rank_is_the_engines_band_and_beta_is_nobodys(self):
        """THE LINE BETWEEN READING AND INVENTING, in one assertion.

        `lora_r` comes from `S9_SIZE_TO_METHOD`'s own cell, so it is the
        engine's. `beta` - how hard a preference run is pulled away from its
        reference - is DPO's own knob and NO table in the ledger names one, so
        setting it here would be this file inventing a hyperparameter and
        handing it over wearing the engine's authority. The recipe's default
        stands and the plan says so out loud.
        """
        situation = self.situation()
        plan = propose.propose(situation)
        config = plan.step("trial").arguments["config"]

        self.assertEqual(config["lora_r"], situation.result.size_row["rank_min"])
        self.assertNotIn("beta", config)
        self.assertIn("beta", plan.because)
        self.assertIn("is NOT set by this plan", plan.because)

    def test_the_prerequisite_is_quoted_from_the_ledger_and_not_typed(self):
        """It reads the file, so the day the ledger changes its mind the plan
        changes with it rather than repeating a sentence nobody maintains."""
        self.assertEqual(propose.the_preference_prerequisite(), "LORA_SFT")
        self.assertIn("LORA_SFT", self.plan().because)

    def test_the_floor_is_the_ledgers_own_number(self):
        self.assertEqual(propose.the_preference_floor(), 1000)
        because = self.plan().because
        self.assertIn("1,000", because)
        self.assertIn("preference_pairs_n >= 1000", because)

    def test_every_wall_clock_is_unknown_and_says_how_to_find_out(self):
        from app import build

        for step in self.plan().steps:
            with self.subTest(step=step.id):
                estimate = step.cost.wall_clock
                self.assertEqual(estimate.provenance, build.UNKNOWN)
                self.assertTrue(estimate.find_out_by.strip())
        self.assertIn(
            "THIS STEP IS THE ANSWER",
            self.plan().step("trial").cost.wall_clock.find_out_by,
        )

    def test_nothing_in_this_plan_reaches_the_connected_model(self):
        """Proved off each tool's own `reads`, not asserted. A preference run is
        the machine's time, and a plan that quietly billed somebody's provider
        would be a cost nobody agreed to."""
        for step in self.plan().steps:
            with self.subTest(tool=step.tool):
                self.assertNotIn(
                    propose.THE_SCORING_READ, propose._spec(step.tool).reads
                )
                self.assertEqual(step.cost.model_tokens.value, 0)


class TheBuildDoesNotScoreAndSaysWhyTest(PreferenceBuildTestCase):
    def test_no_step_scores_anything(self):
        scoring = {"run_eval", "measure_baseline", "try_prompt", "score_the_adapter"}
        self.assertEqual({step.tool for step in self.plan().steps} & scoring, set())

    def test_the_reason_is_the_artifact_and_not_a_missing_tool(self):
        """THE DIFFERENCE FROM THE SUPERVISED BUILD'S REASON, PINNED.

        The SFT build stops for want of a completed eval run to pair against -
        a fact about the CONVERSATION. This one stops because the thing it
        produces is not the thing the scorer can load, which is a fact about
        trl. Saying "the scorer does not exist" here would be false: it is
        registered, and this file asserts that too, so the sentence cannot
        quietly become the other one.
        """
        self.assertTrue(propose.the_adapter_scorer_is_registered())
        plan = self.plan()
        # `dpo_trainer.py:578-580` was cited here and is not any more, and the
        # removal is the correction: that line DOES merge an already-loaded
        # PeftModel, and leaving the merge inside trl is what left the recipe
        # with no clean handle on the merged weights. The recipe now merges
        # explicitly, so a plan citing trl's line would be crediting the wrong
        # code for the property the plan turns on.
        for phrase in (
            "merge",
            "worse than no score",
            propose.THE_ADAPTER_SCORER,
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, plan.because)

    def test_the_criterion_is_about_a_measurement_being_taken(self):
        plan = self.plan()
        self.assertEqual(plan.exit_criterion.subject, "trial.exit_code")
        self.assertEqual(plan.exit_criterion.value, 0)
        self.assertIn("MEASURES THE COST AND DOES NOT SCORE", plan.exit_criterion.stated)

    def test_a_risk_names_the_way_the_adapter_can_be_misdeployed(self):
        """It runs either way, which is what makes it a risk rather than an
        error. An adapter over merged weights loaded onto the raw base is a
        difference from something else, and it returns text."""
        risks = " ".join(risk.what + " " + risk.what_we_do for risk in self.plan().risks)
        self.assertIn("merged", risks)
        self.assertIn("neither works and both run", risks)


class TheBuildRefusesWhenItWouldBeTheatreTest(PreferenceBuildTestCase):
    def test_it_will_not_start_without_the_sft_pass_the_ledger_requires(self):
        """THE REFUSAL THIS BUILD EXISTS FOR. The declaration is inert in the
        engine, so if the proposer does not act on it nothing does."""
        gap = self.refusal(adapter_dir="")
        self.assertIn("adapter_dir", gap.needs)
        self.assertIn("LORA_SFT", gap.detail)
        self.assertIn("after an SFT pass", gap.detail)
        self.assertIn(propose.THE_LORA_RECIPE, gap.detail)

    def test_a_directory_that_is_not_an_adapter_is_refused(self):
        empty = self.root / "not_an_adapter"
        empty.mkdir()
        gap = self.refusal(adapter_dir=str(empty))
        self.assertIn("adapter_dir", gap.needs)
        self.assertIn("adapter_config.json", gap.detail)

    def test_the_recipe_must_be_built_on_this_machine(self):
        venv = Path(jobspec.RECIPES_ROOT) / propose.THE_DPO_RECIPE / ".venv"
        for interpreter in (venv / "Scripts" / "python.exe", venv / "bin" / "python"):
            interpreter.unlink()
        self.assertFalse(
            propose.the_recipe_on_this_machine(propose.THE_DPO_RECIPE)["pinned"]
        )
        gap = self.refusal()
        self.assertIn("list_recipes", gap.detail)
        self.assertIn(propose.THE_DPO_RECIPE, gap.detail)
        self.assertIn(propose.THE_LORA_RECIPE, gap.detail)

    def test_the_supervised_recipe_being_built_is_not_this_one_being_built(self):
        """The reading is per recipe, which is what `the_recipe_on_this_machine`
        taking a name is for. One environment standing in for the other is how a
        plan comes to name a backend that is not there."""
        venv = Path(jobspec.RECIPES_ROOT) / propose.THE_DPO_RECIPE / ".venv"
        for interpreter in (venv / "Scripts" / "python.exe", venv / "bin" / "python"):
            interpreter.unlink()
        support.pin_a_training_recipe(propose.THE_LORA_RECIPE)

        self.assertTrue(
            propose.the_recipe_on_this_machine(propose.THE_LORA_RECIPE)["pinned"]
        )
        self.assertIn(propose.THE_DPO_RECIPE, self.refusal().detail)

    def test_it_will_not_choose_the_model(self):
        gap = self.refusal(base_model="")
        self.assertIn("base_model", gap.needs)
        self.assertIn("find_models", gap.detail)

    def test_it_will_not_choose_the_example_length(self):
        gap = self.refusal(max_seq_len=0)
        self.assertIn("max_seq_len", gap.needs)
        self.assertIn("two complete answers", gap.detail)

    def test_a_count_of_a_different_file_is_not_a_count_of_this_one(self):
        """THE DEFECT THIS PRODUCT SPENT A MILESTONE REMOVING, asked here.

        The outcome is only reachable because SOME `preference_pairs_n` routed,
        and that says nothing about which file was counted. Here it would be
        hours of somebody's GPU planned against a count of a file this run never
        opens.
        """
        other = self.preference_file(rows=10, name="somebody_elses.jsonl")
        gap = self.refusal(counted_file=str(other))
        self.assertIn("preference_pairs_n", gap.needs)
        self.assertIn("count_preference_pairs", gap.detail)
        self.assertIn("somebody_elses.jsonl", gap.detail)

    def test_a_count_that_named_no_file_is_refused_too(self):
        gap = self.refusal(hows={})
        self.assertIn("nothing recorded which file it counted", gap.detail)

    def test_below_the_ledgers_floor_it_refuses_with_both_numbers(self):
        """A GUARD FOR THE DOOR THE TREE DOES NOT COME THROUGH, and it is worth
        having for the reason every other belt-and-braces check here is.

        Put 120 into the fact sheet and the ENGINE routes elsewhere entirely -
        `BLOCKED__COLLECT_OR_SYNTHESIZE_DATA`, because the node's condition is
        the floor - so this refusal is unreachable by diagnosis and reachable by
        a caller who assembles a `Situation`, which every test in this file
        does and which `propose()` cannot tell apart. So the Situation is built
        the normal way and the value is put back afterwards: the outcome is the
        real minted one, and the number the proposer reads is under the floor.
        """
        situation = self.situation()
        with_fewer = dict(situation.values)
        with_fewer["preference_pairs_n"] = 120
        situation = dataclasses.replace(situation, values=with_fewer)

        with self.assertRaises(propose.NotEnoughToPropose) as raised:
            propose.propose(situation)
        self.assertIn("120", raised.exception.detail)
        self.assertIn("1,000", raised.exception.detail)
        self.assertIn("noise", raised.exception.detail)

    def test_training_data_that_is_not_jsonl_is_refused(self):
        csv = self.root / "pairs.csv"
        csv.write_text("prompt,chosen,rejected\na,b,c\n", encoding="utf-8")
        gap = self.refusal(dataset_path=str(csv))
        self.assertIn("dataset_path", gap.needs)
        self.assertIn(".jsonl", gap.detail)

    def test_training_on_the_eval_set_is_refused(self):
        evaluation = self.eval_file()
        gap = self.refusal(dataset_path=str(evaluation), eval_path=str(evaluation))
        self.assertIn("eval_path", gap.needs)
        self.assertIn("same file", gap.detail)

    def test_a_machine_with_no_accelerator_is_refused(self):
        gap = self.refusal(facts={"accelerator": diagnosis.measured("cpu_only")})
        self.assertIn("CPU", gap.detail)
        self.assertIn("preflight", gap.detail)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
