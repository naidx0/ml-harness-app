"""Where am I on this journey, and what is the one next thing?

`app/knowledge/playbook.json` has held five named journeys since 2026-08-30,
and `train_on_my_files` is a seventeen-step route from a folder to a scored
adapter. A model could ask for it with `map_the_ask`. A PERSON could not see it
at all: the route existed as data, and every step of it was reachable only by
knowing which of sixty-seven tools to reach for.

Max, relayed 2026-09-02: "launching a journey overview... with easy
interactable tools, and simple prompting and instruction."

## The one thing this module must not do

Claim a step happened. Thread 33 walked this route for real on 1 September and
skipped five of its steps - it arrived with data already carved, and it put a
baseline on the record with `run_eval` rather than `measure_baseline`. A naive
"did step 13 run?" reads that thread as stuck at step 2 forever; a generous one
ticks steps nobody did. Both are the same defect: an overview that is not a
reading of the record.

So a step is DONE when its tool ran here, and separately a step's PURPOSE is
MET when every fact its tool declares in `measures` is on the ledger - put
there by whichever tool actually did it, which the reply names. Everything else
is ahead, and the first thing that is neither is next.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from app import events, journey
import support


TRAIN = "train_on_my_files"


class JourneyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)
        self.thread = int(support.conversations(1)[0]["id"])

    def ran(self, name, *, ok=True, summary="", driven_by="user", result=None):
        body = dict(result) if result is not None else {"ok": ok}
        body.setdefault("summary", summary)
        events.append(
            "tool.result",
            {
                "id": f"{driven_by}-{name}",
                "name": name,
                "ok": ok,
                "result": body,
                "driven_by": driven_by,
            },
            thread_id=self.thread,
        )

    def a_fact(self, fact, value, tool="run_eval"):
        """Stamp through an instrument, the way a tool does. `record` refuses a
        MEASURED row written straight to the ledger (wall 5), and rightly: the
        badge is the instrument's to give."""
        from app.tools import evidence as evidence_module

        from app.tools import REGISTRY

        # The tool's OWN declared capability, not a guessed one: `eval_size_n`
        # names `data.eval_set.count` in the ledger and wall 9 refuses any
        # other kind of instrument for it. A fixture that hardcoded one
        # capability would trip that wall instead of testing this module.
        declared = getattr(REGISTRY, "_tools", {}).get(tool)
        instrument = evidence_module.Instrument(
            tool=tool,
            actor=evidence_module.USER,
            thread_id=self.thread,
            measures=frozenset({fact}),
            provides=frozenset(getattr(declared, "provides", ()) or ()),
        )
        instrument.measured(fact, value, how=f"{tool} measured it on 30 rows")

    def on_the_route(self):
        events.set_thread_goal(self.thread, "train a model on my design system", TRAIN)
        return journey.build(self.thread)


class WhichJourneyTest(JourneyTest):
    def test_a_thread_with_no_goal_names_the_journeys_rather_than_guessing(self):
        report = journey.build(self.thread)
        self.assertIsNone(report["journey"])
        self.assertEqual(report["steps"], [])
        self.assertIn(TRAIN, report["journeys_available"])
        self.assertIn("no goal", report["say"])

    def test_a_recorded_journey_is_read_and_not_re_matched(self):
        report = self.on_the_route()
        self.assertEqual(report["journey"], TRAIN)
        self.assertEqual(report["journey_origin"], "recorded")
        self.assertEqual(report["total"], 17)
        self.assertEqual(report["steps"][0]["tool"], "attach_context")
        self.assertEqual(report["steps"][-1]["tool"], "score_the_adapter")
        self.assertEqual([s["ordinal"] for s in report["steps"]], list(range(1, 18)))

    def test_a_goal_with_no_recorded_journey_is_matched_from_its_own_words(self):
        events.set_thread_goal(self.thread, "I want to fine-tune on my folder", None)
        report = journey.build(self.thread)
        self.assertEqual(report["journey"], TRAIN)
        self.assertEqual(report["journey_origin"], "matched")
        self.assertTrue(report["matched_on"], "the words it matched on are the evidence")


class WhatIsDoneTest(JourneyTest):
    def test_a_step_whose_tool_ran_is_done_and_carries_what_it_said(self):
        self.ran("attach_context", summary="Attached C:/work/design-system")
        step = self.on_the_route()["steps"][0]
        self.assertEqual(step["state"], "done")
        self.assertEqual(step["produced"], "Attached C:/work/design-system")
        self.assertEqual(step["driven_by"], "user")
        self.assertIsNotNone(step["ran_at"])

    def test_a_tool_that_failed_did_not_do_its_step(self):
        self.ran("attach_context", ok=False, summary="no such folder")
        step = self.on_the_route()["steps"][0]
        self.assertEqual(step["state"], "next")
        self.assertIsNone(step["produced"])

    def test_a_purpose_met_by_another_tool_is_named_rather_than_ticked(self):
        """Thread 33's own shape: `run_eval` stamped every fact
        `measure_baseline` declares, so step 13's purpose is met and step 13
        did not run. Saying "done" would be a claim about a tool that never
        ran; saying "not done" would ask for work already finished."""
        self.a_fact("baseline_measured", True, "run_eval")
        self.a_fact("baseline_score", 0.13, "run_eval")
        self.a_fact("trivial_baseline_score", 0.03, "run_eval")
        steps = {s["tool"]: s for s in self.on_the_route()["steps"]}
        met = steps["measure_baseline"]
        self.assertEqual(met["state"], "done_elsewhere")
        self.assertEqual(met["satisfied_by"]["tool"], "run_eval")
        self.assertEqual(
            sorted(met["satisfied_by"]["facts"]),
            ["baseline_measured", "baseline_score", "trivial_baseline_score"],
        )

    def test_a_fact_stamped_by_the_step_s_own_tool_means_the_step_ran(self):
        """Found by running this against thread 32 rather than by reasoning.

        That thread's `measure_eval_set` stamped `eval_size_n` and left no
        tool.result row, because user-driven calls did not write one until
        1 September. The first draft reported step 7 as "done elsewhere, by
        measure_eval_set" - satisfied by itself, which is not English and not
        true. A fact carrying the step's own tool IS the record of that step
        running; the event row is a second, younger witness to the same thing.
        """
        self.a_fact("eval_size_n", 30, tool="measure_eval_set")
        step = {s["tool"]: s for s in self.on_the_route()["steps"]}["measure_eval_set"]
        self.assertEqual(step["state"], "done")
        self.assertIsNone(step["satisfied_by"])
        self.assertEqual(step["evidence"], "ledger")

    def test_a_step_done_by_its_own_event_says_the_event_was_the_evidence(self):
        self.ran("attach_context", summary="attached")
        step = self.on_the_route()["steps"][0]
        self.assertEqual(step["evidence"], "event")

    def test_a_purpose_only_half_met_is_not_met(self):
        self.a_fact("baseline_score", 0.13, "run_eval")
        steps = {s["tool"]: s for s in self.on_the_route()["steps"]}
        self.assertNotEqual(steps["measure_baseline"]["state"], "done_elsewhere")

    def test_a_step_whose_tool_measures_nothing_is_only_ever_done_by_running(self):
        """`attach_context` stamps no fact, so no ledger reading can stand in
        for it. Its `measures` is empty, and an "all of them present" rule over
        an empty set is vacuously true - which would tick every such step on an
        empty thread."""
        report = self.on_the_route()
        steps = {s["tool"]: s for s in report["steps"]}
        self.assertEqual(steps["attach_context"]["state"], "next")
        self.assertEqual(steps["carve_rows"]["state"], "ahead")


class WhatIsNextTest(JourneyTest):
    def test_next_is_the_first_step_neither_done_nor_met(self):
        self.ran("attach_context", summary="attached")
        self.ran("carve_rows", summary="cut 400 rows")
        report = self.on_the_route()
        self.assertEqual(report["next"]["tool"], "drop_duplicates")
        self.assertEqual(report["next"]["ordinal"], 3)
        self.assertEqual(report["done_n"], 2)

    def test_a_finished_route_has_no_next_and_says_so(self):
        for step in self.on_the_route()["steps"]:
            self.ran(step["tool"], summary=f"{step['tool']} done")
        report = journey.build(self.thread)
        self.assertIsNone(report["next"])
        self.assertEqual(report["done_n"], 17)
        self.assertIn("every step", report["say"].lower())

    def test_a_later_step_done_out_of_order_does_not_move_next_past_a_gap(self):
        """Order is the route's claim, not the person's obligation. Running
        step 15 early does not mean steps 1-14 happened."""
        self.ran("make_sandbox", summary="made")
        report = self.on_the_route()
        self.assertEqual(report["next"]["tool"], "attach_context")
        states = {s["tool"]: s["state"] for s in report["steps"]}
        self.assertEqual(states["make_sandbox"], "done")


class WhatTheStepAlreadyKnowsTest(JourneyTest):
    """J4: a control opens knowing what the thread already knows.

    The training tail is the case that forced this. `run_in_sandbox` wants a
    sandbox NAME and `score_the_adapter` wants a sandbox, a BASELINE RUN ID and
    a thread id - three things a person cannot be expected to type and all
    three of which the harness measured itself. A form that asks for them is a
    tool picker wearing a step's clothes.

    Every prefilled value is read off the record and carries `from`, naming
    where it came from. Nothing is defaulted: a value nobody measured is absent
    rather than guessed, because a guess sitting in a filled field is
    indistinguishable from a measurement to the person about to press Run.
    """

    def test_only_what_is_true_of_any_thread_is_offered_before_anything_ran(self):
        """Rewritten rather than loosened, and the first draft was the wrong
        assertion: it demanded an EMPTY prefill for `score_the_adapter` on a
        fresh thread, and a conversation always knows its own id. What must be
        absent is everything that needs a record - the sandbox nobody made, the
        baseline nobody measured - and those are absent."""
        steps = {s["tool"]: s for s in self.on_the_route()["steps"]}
        scoring = steps["score_the_adapter"]["prefill"]
        self.assertEqual(set(scoring), {"thread_id"})
        self.assertEqual(scoring["thread_id"]["value"], self.thread)
        self.assertEqual(steps["measure_baseline"]["prefill"], {})
        self.assertEqual(steps["measure_eval_set"]["prefill"], {})

    def test_the_carve_fills_every_step_that_wants_its_files(self):
        self.ran(
            "carve_eval_set",
            summary="Carved 30 rows",
            result={
                "ok": True,
                "eval_path": "C:/w/split/ui.eval.jsonl",
                "train_path": "C:/w/split/ui.train.jsonl",
                "answer_column": "a",
            },
        )
        steps = {s["tool"]: s for s in self.on_the_route()["steps"]}

        counted = steps["measure_eval_set"]["prefill"]
        self.assertEqual(counted["path"]["value"], "C:/w/split/ui.eval.jsonl")
        self.assertIn("carve", counted["path"]["from"])

        leak = steps["check_split_leakage"]["prefill"]
        self.assertEqual(leak["train_path"]["value"], "C:/w/split/ui.train.jsonl")
        self.assertEqual(leak["eval_path"]["value"], "C:/w/split/ui.eval.jsonl")

        scored = steps["measure_baseline"]["prefill"]
        self.assertEqual(scored["eval_path"]["value"], "C:/w/split/ui.eval.jsonl")
        self.assertEqual(scored["expected_field"]["value"], "a")
        # The QUESTION column is not in the carve's record, so it is not filled.
        self.assertNotIn("input_field", scored)

    def test_a_step_is_only_offered_fields_its_own_schema_declares(self):
        self.ran(
            "carve_eval_set",
            summary="carved",
            result={"ok": True, "eval_path": "C:/w/e.jsonl", "answer_column": "a"},
        )
        steps = {s["tool"]: s for s in self.on_the_route()["steps"]}
        for tool, filled in ((t, s["prefill"]) for t, s in steps.items()):
            spec = self._spec(tool)
            declared = set((getattr(spec, "schema", {}) or {}).get("properties") or {})
            self.assertTrue(
                set(filled) <= declared,
                f"{tool} was offered {set(filled) - declared}, which it does not take",
            )

    def test_every_filled_value_says_where_it_came_from(self):
        self.ran(
            "carve_eval_set",
            summary="carved",
            result={"ok": True, "eval_path": "C:/w/e.jsonl", "answer_column": "a"},
        )
        for step in self.on_the_route()["steps"]:
            for field, filled in step["prefill"].items():
                self.assertIn("value", filled, f"{step['tool']}.{field}")
                self.assertTrue(
                    str(filled.get("from") or "").strip(),
                    f"{step['tool']}.{field} was filled with no account of where from",
                )

    def test_the_first_step_is_offered_the_folder_this_project_already_has(self):
        """`attach_context` asks where the material lives, and a project that
        has a root has answered that already. Offered, not assumed: the field
        is filled and the person can replace it, because a project root and
        the folder they mean this time are allowed to differ."""
        from app import db as db_module

        with db_module.session() as connection:
            row = connection.execute(
                "SELECT project_id FROM threads WHERE id = ?", (self.thread,)
            ).fetchone()
            connection.execute(
                "UPDATE projects SET root_path = ? WHERE id = ?",
                ("C:/w/design-system", int(row["project_id"])),
            )
        filled = {s["tool"]: s for s in self.on_the_route()["steps"]}["attach_context"]["prefill"]
        self.assertEqual(filled["path"]["value"], "C:/w/design-system")
        self.assertIn("project", filled["path"]["from"])

    def test_the_fit_questions_are_asked_about_the_model_you_sized(self):
        """Steps 11 and 12 ask "can this machine train it" and "where should it
        run", and both need a repo id. The thread has one the moment somebody
        reads a config: reading a config is how a person says which model they
        mean. Step 10 itself is NOT filled - choosing the model is the choice,
        and a shortlist entry offered into that field would be this product
        making it for them."""
        self.ran(
            "read_model_config",
            summary="sized",
            result={"ok": True, "repo_id": "HuggingFaceTB/SmolLM2-1.7B"},
        )
        steps = {s["tool"]: s for s in self.on_the_route()["steps"]}
        for tool in ("can_this_machine_train", "where_to_train"):
            filled = steps[tool]["prefill"]
            self.assertEqual(filled["repo_id"]["value"], "HuggingFaceTB/SmolLM2-1.7B", tool)
            self.assertIn("sized", filled["repo_id"]["from"])
        self.assertNotIn("repo_id", steps["read_model_config"]["prefill"])

    def test_making_a_sandbox_carries_the_recipe_the_route_names(self):
        """The stranger walk found this and it was mine.

        `make_sandbox` declares no REQUIRED arguments, so the route called it a
        one-click step and clicking it made a sandbox with no recipe pinned -
        which `run_in_sandbox` then refused, correctly, with "pins no recipe,
        so there is nothing in it to run". A step that can be pressed is not
        the same as a step that is useful when pressed.

        The route has always named the recipe, in the step's own `args_hint`
        - "recipe = hf-peft-lora" - so it is read from there rather than
        written into this module: the playbook is where a route's knowledge
        lives, and a second route with a different backend would otherwise
        need a change here that nobody would remember to make.
        """
        filled = {s["tool"]: s for s in self.on_the_route()["steps"]}["make_sandbox"]["prefill"]
        self.assertEqual(filled["recipe"]["value"], "hf-peft-lora")
        self.assertIn("route", filled["recipe"]["from"])

    def test_the_training_config_is_assembled_from_what_was_chosen_and_copied(self):
        """The training config is the hardest thing on the route to type, and
        every part of it that CAN be known is known: the model the person
        sized, and the training file as the sandbox copied it - which is not
        the path they carved, but the copy inside the sandbox, and getting that
        wrong is the single most likely way this step fails.

        `max_steps` is NOT filled. Nobody measured it, the recipe's own default
        stands if it is left alone, and a number invented here would sit in a
        filled field looking exactly like the two beside it that were read.
        """
        self.ran(
            "carve_eval_set",
            summary="carved",
            result={
                "ok": True,
                "eval_path": "C:/w/split/ui.eval.jsonl",
                "train_path": "C:/w/split/ui.train.jsonl",
                "answer_column": "a",
            },
        )
        self.ran(
            "read_model_config",
            summary="sized",
            result={"ok": True, "repo_id": "HuggingFaceTB/SmolLM2-1.7B"},
        )
        made = {
            "ok": True,
            "name": "practical-ml",
            "snapshotted": [
                {"path": "C:/w/split/ui.train.jsonl", "copied_to": "C:/sb/data/00_ui.train.jsonl"},
                {"path": "C:/w/split/ui.eval.jsonl", "copied_to": "C:/sb/data/01_ui.eval.jsonl"},
            ],
        }
        self.ran("make_sandbox", summary="made", result=made)

        filled = {s["tool"]: s for s in self.on_the_route()["steps"]}["run_in_sandbox"]["prefill"]
        config = filled["config"]["value"]
        self.assertEqual(config["base_model"], "HuggingFaceTB/SmolLM2-1.7B")
        # The COPY inside the sandbox, matched to the carve's own train file -
        # never the original, and never a filename that merely looks like it.
        self.assertEqual(config["dataset_path"], "C:/sb/data/00_ui.train.jsonl")
        self.assertNotIn("max_steps", config)
        self.assertTrue(str(filled["config"]["from"]).strip())

    def test_no_config_is_offered_when_neither_half_is_known(self):
        filled = {s["tool"]: s for s in self.on_the_route()["steps"]}["run_in_sandbox"]["prefill"]
        self.assertNotIn("config", filled)

    def test_a_sandbox_offered_is_the_project_s_and_says_so(self):
        """Found by walking a fresh thread on a project that already had one.

        Sandboxes are project-scoped, so offering one to a conversation that
        never made it is right. Calling it "the sandbox you made" was not: that
        thread made nothing, and the words were a claim about the person rather
        than a reading of the record.
        """
        from unittest import mock

        # The prefill reads REAL sandboxes off disk rather than the event that
        # announced one - which is right, and is why this patches the reader
        # rather than writing a make_sandbox row: what is under test is the
        # sentence, not whether a sandbox exists.
        with mock.patch.object(journey, "_newest_sandbox", lambda _p: "practical-ml"):
            steps = {s["tool"]: s for s in self.on_the_route()["steps"]}
        for tool, field in (("run_in_sandbox", "name"), ("score_the_adapter", "sandbox")):
            source = steps[tool]["prefill"][field]["from"]
            self.assertIn("project", source, tool)
            self.assertNotIn("you made", source, tool)

    def test_the_lora_settings_come_from_the_recipe_that_will_use_them(self):
        """The LoRA choice, made visible instead of invisible.

        `lora_r`, `lora_alpha`, `learning_rate` and `max_steps` are real knobs
        with real defaults, and until now a person had no way to know they
        existed: the recipe applied its own and the form said nothing. They are
        offered now, so the settings can be SEEN and changed rather than
        discovered by reading a trainer.

        The values are read from the recipe's own `recipe.toml` - the table
        `entrypoint.py` reads too - so there is one copy of each number. This
        writes its own recipe into the test's recipes root and asserts the
        MECHANISM; that the shipped recipe really declares them is asserted
        separately below, against the file itself.
        """
        from app import jobspec

        directory = Path(jobspec.RECIPES_ROOT) / "hf-peft-lora"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "recipe.toml").write_text(
            chr(10).join(
                [
                    'name = "hf-peft-lora"',
                    'kinds = ["train", "eval"]',
                    'entrypoint = "entrypoint.py"',
                    "[defaults]",
                    "lora_r = 16",
                    "lora_alpha = 32",
                    "learning_rate = 2e-4",
                    "max_steps = 20",
                ]
            ),
            encoding="utf-8",
        )
        self.ran(
            "read_model_config",
            summary="sized",
            result={"ok": True, "repo_id": "HuggingFaceTB/SmolLM2-1.7B"},
        )
        config = {s["tool"]: s for s in self.on_the_route()["steps"]}["run_in_sandbox"]["prefill"]["config"]
        for knob in ("lora_r", "lora_alpha", "learning_rate", "max_steps"):
            self.assertIn(knob, config["value"], knob)
        self.assertEqual(config["value"]["lora_r"], 16)
        self.assertEqual(config["value"]["base_model"], "HuggingFaceTB/SmolLM2-1.7B")
        self.assertIn("recipe", config["from"])

    def test_the_shipped_recipe_declares_the_knobs_its_trainer_reads(self):
        """The other half, against the real file rather than a fixture: the
        recipe a person actually trains with has to carry the table, or the
        mechanism above has nothing to read on their machine."""
        import tomllib

        shipped = Path(__file__).resolve().parents[1] / "recipes" / "hf-peft-lora" / "recipe.toml"
        declared = tomllib.loads(shipped.read_text(encoding="utf-8")).get("defaults") or {}
        for knob in ("lora_r", "lora_alpha", "lora_dropout", "learning_rate", "max_seq_len", "max_steps"):
            self.assertIn(knob, declared, knob)
        # And the trainer must actually consult it, rather than keeping its own.
        entry = (shipped.parent / "entrypoint.py").read_text(encoding="utf-8")
        self.assertIn("_declared_defaults()", entry)

    def test_the_scoring_step_is_handed_the_baseline_it_must_beat(self):
        """The one a person could not possibly type: an eval run's id."""
        self.a_fact("eval_size_n", 30, tool="measure_eval_set")
        run = support.a_completed_eval_run(self.thread, self.root / "eval.jsonl", rows=20)
        steps = {s["tool"]: s for s in self.on_the_route()["steps"]}
        filled = steps["score_the_adapter"]["prefill"]
        self.assertEqual(filled["baseline_run_id"]["value"], int(run["id"]))
        self.assertEqual(filled["thread_id"]["value"], self.thread)

    def _spec(self, tool):
        from app.tools import REGISTRY

        return getattr(REGISTRY, "_tools", {}).get(tool)


class WhatCameOutTheOtherEndTest(JourneyTest):
    """The loop Max described closes here: data in one end, a trained adapter
    or an honest do-not-train out the other.

    Until now the route could reach seventeen of seventeen and say nothing
    about what it produced. The scores were in the eval bench, the adapter was
    on disk, and a person had to go and find both. The outcome is READ off the
    runs the thread already has - the same `evals.compare` the Stage uses,
    never a second implementation of "is this difference real", because two
    would disagree within a month.
    """

    def test_a_thread_with_no_adapter_scored_has_no_outcome(self):
        self.assertIsNone(self.on_the_route()["outcome"])

    def test_a_baseline_alone_is_not_an_outcome(self):
        """One score is a fact about one model, not a result."""
        support.a_completed_eval_run(self.thread, self.root / "eval.jsonl", rows=20)
        self.assertIsNone(self.on_the_route()["outcome"])


class TheOtherAnswerTest(JourneyTest):
    """The half of Max's sentence the outcome card did not carry.

    "Data in one end, a trained adapter OR AN HONEST DO-NOT-TRAIN out the
    other." The adapter half landed with `outcome`. The other half - the
    ledger's own verdict, which is the answer this product exists to be able
    to give - was reachable from the Evidence pane and the Stage's gate map
    and from nowhere on the route a person was walking.

    It is READ from `journey_report`, the same builder the printable report and
    the Stage both use. Nothing here re-walks the tree: a second opinion about
    a verdict would be a second product.
    """

    def test_a_thread_that_has_diagnosed_nothing_has_no_verdict(self):
        self.assertIsNone(self.on_the_route()["verdict"])

    def test_the_ledger_s_answer_is_carried_with_its_gates(self):
        from unittest import mock

        answer = {
            "verdict": {
                "outcome": "NO_TRAIN__RAG",
                "say": "Under roughly 100M domain tokens, continued pretraining buys less than a good retriever.",
                "gates": {
                    "G0_EVAL_SET": {"status": "PASSED"},
                    "G1_BASELINE_MEASURED": {"status": "PASSED"},
                    "G2_PROMPT_EXHAUSTED": {"status": "NOT_REACHED"},
                    "G3_RETRIEVAL_CONSIDERED": {"status": "PASSED"},
                    "G4_CHEAPER_MODEL_CONSIDERED": {"status": "NOT_REACHED"},
                },
            }
        }
        with mock.patch.object(journey.journey_report, "build", lambda _t: answer):
            got = self.on_the_route()["verdict"]
        self.assertEqual(got["outcome"], "NO_TRAIN__RAG")
        self.assertTrue(got["trains"] is False)
        self.assertEqual(got["gates_passed"], 3)
        self.assertEqual(got["gates_total"], 5)
        self.assertIn("retriever", got["say"])

    def test_a_training_verdict_says_it_trains(self):
        """The same field, the other way, so nothing has to read the prefix
        at the far end to know which answer it got."""
        from unittest import mock

        answer = {"verdict": {"outcome": "TRAIN__LORA_SFT", "say": "", "gates": {}}}
        with mock.patch.object(journey.journey_report, "build", lambda _t: answer):
            got = self.on_the_route()["verdict"]
        self.assertTrue(got["trains"])


class WhatHappenedWhenYouTriedTest(JourneyTest):
    """A step that was tried and refused says so, and says what to do.

    ## Why this is worth a feature rather than a shrug

    Two literature reviews commissioned overnight (vault, `10-Signals/specs/
    teaching-evidence.md`) put numbers on feedback in a guided task: bare
    right/wrong is d = 0.05, DISCOURAGING feedback is NEGATIVE at -0.14, and
    feedback that says why and what next is 0.49 - high-information 0.99. A
    step that ends in a bare failure is measurably worse than saying nothing.

    This route said nothing, which is the other failure. Seventeen refused runs
    sat in the event log of this database alone, each carrying a `detail` this
    product had already written AS A REMEDY - "needs an approval before it can
    run... it is a person saying yes to this specific action" - and none of it
    reached the person walking the route. They pressed the button, it refused,
    and the step looked untouched.

    So the refusal is surfaced, and it is surfaced as guidance rather than as
    an alarm: the highest-information feedback in this product is already
    written, in the tool's own words, and it was being thrown away.
    """

    def test_a_step_nobody_tried_reports_no_attempt(self):
        self.assertIsNone(self.on_the_route()["steps"][0]["attempted"])

    def test_a_refused_step_carries_the_tool_s_own_remedy(self):
        self.ran(
            "carve_eval_set",
            ok=False,
            result={
                "ok": False,
                "error": "approval_required",
                "detail": (
                    "split graded data into eval and train files needs an approval "
                    "before it can run."
                ),
            },
        )
        step = {s["tool"]: s for s in self.on_the_route()["steps"]}["carve_eval_set"]
        self.assertIsNotNone(step["attempted"])
        self.assertEqual(step["attempted"]["error"], "approval_required")
        self.assertIn("needs an approval", step["attempted"]["detail"])
        self.assertIsNotNone(step["attempted"]["at"])
        # And it is still not done, because a refusal is not a completion.
        self.assertNotEqual(step["state"], "done")

    def test_a_step_that_later_succeeded_stops_reporting_the_refusal(self):
        """The remedy worked. Leaving it on screen would be this surface
        telling somebody off for something they already fixed - which is the
        `-0.14` case, and the whole reason to be careful here."""
        self.ran("attach_context", ok=False, result={"ok": False, "detail": "no such folder"})
        self.ran("attach_context", summary="Attached C:/w")
        step = self.on_the_route()["steps"][0]
        self.assertEqual(step["state"], "done")
        self.assertIsNone(step["attempted"])


class ChoosingARouteTest(JourneyTest):
    """Starting a journey is a click, not an essay.

    The route was reachable one way: type prose in the chat and hope the
    keyword matcher agreed with you. A person who could SEE the five routes
    listed - which the empty state has shown all along - still had to guess a
    sentence that would land on the one they were pointing at.

    THE GOAL IS NOT SET BY THIS. `events.set_thread_goal`'s own docstring is
    the reason: the goal is "the person's own words, verbatim... never a
    model's paraphrase". A menu pick is not their words either, so choosing a
    route records the ROUTE and leaves the goal exactly as it was - empty if
    it was empty, theirs if they had written one.
    """

    def _choose(self, name):
        from app.main import app

        return support.api_client(app).post(
            f"/api/threads/{self.thread}/journey", json={"journey": name}
        )

    def test_choosing_a_route_puts_the_thread_on_it(self):
        answered = self._choose(TRAIN)
        self.assertEqual(answered.status_code, 200, answered.text)
        report = journey.build(self.thread)
        self.assertEqual(report["journey"], TRAIN)
        self.assertEqual(report["journey_origin"], "recorded")
        self.assertEqual(report["total"], 17)

    def test_choosing_a_route_does_not_write_words_the_person_did_not_say(self):
        events.set_thread_goal(self.thread, "my own sentence", None)
        self._choose(TRAIN)
        self.assertEqual(events.get_thread(self.thread)["goal"], "my own sentence")

    def test_a_thread_with_no_goal_still_has_none_after_choosing(self):
        self._choose(TRAIN)
        self.assertIn(events.get_thread(self.thread)["goal"], (None, ""))

    def test_a_route_the_playbook_does_not_have_is_refused(self):
        """Not stored and not guessed at. A thread carrying a journey name
        nothing can look up would render an empty route with no way back."""
        answered = self._choose("train_on_someone_elses_files")
        self.assertEqual(answered.status_code, 400, answered.text)
        self.assertIsNone(events.get_thread(self.thread)["goal_journey"])
        self.assertIn("train_on_my_files", answered.text)


class CanThisStepRunTest(JourneyTest):
    """Whether a step can be a click, and if not, what it still needs.

    The acceptance for this goal is blunt: "every step is ONE obvious click,
    and if a step needs a form the form is the design failure". That is true
    of most of this route and not all of it, and the honest surface says which
    is which rather than opening a form seventeen times and hoping.

    Three answers, and the third is the useful one:

      click   every required argument is already on the record. Press it.
      approve  the same, but the tool needs a person to say yes. TWO clicks
               here is deliberate - `Registry.call`'s own rule is that
               approval "is a person saying yes to THIS specific action", and
               a single click that sent `approved: true` would launder it.
      needs    something required is missing that only the person can give -
               their own words, or a choice. The missing fields are NAMED, so
               the button can say what it wants instead of opening a form and
               letting them find out.
    """

    def _readiness(self, tool):
        return {s["tool"]: s for s in self.on_the_route()["steps"]}[tool]["readiness"]

    def test_a_step_whose_arguments_are_all_on_the_record_is_a_click(self):
        r = self._readiness("read_model_shortlist")
        self.assertEqual(r["mode"], "click")
        self.assertEqual(r["missing"], [])

    def test_a_step_still_missing_the_person_s_own_words_says_which(self):
        """`state_facts` wants the person's bar and task. Nothing measured it
        and nothing should: naming the field is the honest answer."""
        r = self._readiness("state_facts")
        self.assertEqual(r["mode"], "needs")
        self.assertEqual(r["missing"], ["facts"])

    def test_a_prefilled_step_becomes_a_click_once_the_record_holds_it(self):
        before = self._readiness("measure_eval_set")
        self.assertEqual(before["mode"], "needs")
        self.assertEqual(before["missing"], ["path"])
        self.ran(
            "carve_eval_set",
            summary="carved",
            result={"ok": True, "eval_path": "C:/w/e.jsonl", "answer_column": "a"},
        )
        after = self._readiness("measure_eval_set")
        self.assertEqual(after["mode"], "click")

    def test_a_tool_that_needs_a_person_to_say_yes_never_reports_click(self):
        """Even with every argument on the record. Approval is not an
        argument, and a mode that let the button send one would be laundering
        the person's yes."""
        from unittest import mock

        # The prefill reads real sandboxes off disk, not the event announcing
        # one - so this patches the reader. What is under test is that approval
        # outranks a full argument list, not whether a directory exists.
        with mock.patch.object(journey, "_newest_sandbox", lambda _p: "sb"):
            r = {s["tool"]: s for s in self.on_the_route()["steps"]}["run_in_sandbox"]["readiness"]
        self.assertEqual(r["mode"], "approve")
        self.assertEqual(r["missing"], [])

    def test_every_step_on_the_route_answers_the_question(self):
        for step in self.on_the_route()["steps"]:
            with self.subTest(step["tool"]):
                self.assertIn(step["readiness"]["mode"], ("click", "approve", "needs"))
                if step["readiness"]["mode"] != "needs":
                    self.assertEqual(step["readiness"]["missing"], [])


class TheRouteNeverDeadEndsTest(JourneyTest):
    """The walk found this, and no test would have.

    A fresh thread on a workspace that arrived with graded rows: pick the
    route, click step 1, and step 2 is `carve_rows`, which wants a folder of
    markdown and CSS this workspace does not have. The route offered exactly
    one action and that action asked for something that does not exist - while
    steps 6, 7 and 9 sat ready to run.

    So `next` - the first step nobody has done - is the wrong anchor for the
    ACTION, though it is still the right answer to "where am I". The action
    goes to `next_runnable`: the first step that can actually be pressed. One
    primary control, still; just the next POSSIBLE one rather than the next
    ordinal one.
    """

    def _carved(self):
        self.ran(
            "carve_eval_set",
            summary="carved",
            result={"ok": True, "eval_path": "C:/w/e.jsonl", "train_path": "C:/w/t.jsonl", "answer_column": "a"},
        )

    def _a_project_folder(self):
        """`attach_context` wants a path, and a project that has a root has
        answered that - so this is what makes step 1 pressable at all."""
        from app import db as db_module

        with db_module.session() as connection:
            row = connection.execute(
                "SELECT project_id FROM threads WHERE id = ?", (self.thread,)
            ).fetchone()
            connection.execute(
                "UPDATE projects SET root_path = ? WHERE id = ?",
                ("C:/w/design-system", int(row["project_id"])),
            )

    def test_a_route_whose_next_step_cannot_run_still_offers_one_that_can(self):
        self.ran("attach_context", summary="attached")
        self._carved()
        report = self.on_the_route()
        # `carve_rows` and `drop_duplicates` are NOT NEEDED here - the carve
        # proved rows existed - so the first step nobody has reached is
        # `synthesize_rows`, which wants four arguments and cannot be pressed.
        # Same property as before the route learned to skip: a blocked `next`
        # does not get to be the only thing on offer.
        self.assertEqual(report["next"]["tool"], "synthesize_rows")
        self.assertEqual(report["next"]["readiness"]["mode"], "needs")
        self.assertIsNotNone(report["next_runnable"])
        self.assertEqual(report["next_runnable"]["tool"], "check_split_leakage")
        self.assertEqual(report["next_runnable"]["readiness"]["mode"], "click")

    def test_the_runnable_step_is_the_next_one_when_it_can_run(self):
        """No second control when the obvious step is already the one to
        press: `next` and `next_runnable` are the same step, and the surface
        draws one button."""
        self._a_project_folder()
        report = self.on_the_route()
        self.assertEqual(report["next"]["tool"], "attach_context")
        self.assertEqual(report["next_runnable"]["tool"], "attach_context")

    def test_a_route_with_nothing_runnable_says_so_rather_than_pointing_nowhere(self):
        from unittest import mock

        with mock.patch.object(journey, "_readiness", lambda t, p: {"mode": "needs", "missing": ["x"]}):
            report = self.on_the_route()
        self.assertIsNone(report["next_runnable"])
        self.assertIsNotNone(report["next"])

    def test_a_finished_route_has_neither(self):
        for step in self.on_the_route()["steps"]:
            self.ran(step["tool"], summary="done")
        report = journey.build(self.thread)
        self.assertIsNone(report["next"])
        self.assertIsNone(report["next_runnable"])


class ArrivingWithDataTest(JourneyTest):
    """A person who already has rows can finish this route.

    ## The decision, and it is a decision rather than a discovery

    `train_on_my_files` opens by cutting a folder of markdown and CSS into
    rows: `carve_rows`, then `drop_duplicates`. Somebody who arrives with a
    graded JSONL - which is how every real walk of this route has started -
    cannot do either, because there is no folder of documents to cut. Left
    alone the route reads 13 of 17 forever and never completes, which fails
    the one thing it is for.

    Marking them "done" would be a lie about work nobody did. Leaving them
    "not started" is a lie about work nobody needs. So there is a third state,
    and the ROUTE declares when it applies: a step carries `unnecessary_if`
    naming the later step whose success makes it moot. `carve_eval_set`
    running proves rows existed and were good enough to split, which is
    precisely what `carve_rows` and `drop_duplicates` exist to produce.

    That knowledge is the route's, not the engine's, so it lives in
    `playbook.json` beside the steps rather than as a table in `journey.py` -
    a second route would otherwise need a second table nobody would remember
    to write.
    """

    def test_a_prep_step_is_not_needed_once_the_step_it_feeds_has_run(self):
        self.ran("carve_eval_set", summary="carved 30 of 135")
        steps = {s["tool"]: s for s in self.on_the_route()["steps"]}
        for tool in ("carve_rows", "drop_duplicates"):
            with self.subTest(tool):
                self.assertEqual(steps[tool]["state"], "not_needed", tool)
                self.assertEqual(steps[tool]["unnecessary_because"], "carve_eval_set")

    def test_it_counts_as_work_that_does_not_have_to_happen(self):
        self.ran("carve_eval_set", summary="carved")
        report = self.on_the_route()
        self.assertEqual(report["done_n"], 3)
        self.assertEqual(report["next"]["tool"], "attach_context")

    def test_before_that_it_is_an_ordinary_step_nobody_has_reached(self):
        steps = {s["tool"]: s for s in self.on_the_route()["steps"]}
        self.assertEqual(steps["carve_rows"]["state"], "ahead")
        self.assertIsNone(steps["carve_rows"]["unnecessary_because"])

    def test_a_step_that_actually_ran_is_done_and_not_explained_away(self):
        """`carve_rows` really running outranks any later step making it moot:
        it happened, and the route says so."""
        self.ran("carve_rows", summary="cut 400 rows")
        self.ran("carve_eval_set", summary="carved")
        steps = {s["tool"]: s for s in self.on_the_route()["steps"]}
        self.assertEqual(steps["carve_rows"]["state"], "done")

    def test_the_route_can_now_reach_every_step(self):
        """The point of the whole decision: a thread that arrived with rows
        can finish, rather than sitting four short of the end forever."""
        for step in self.on_the_route()["steps"]:
            if step["tool"] not in ("carve_rows", "drop_duplicates", "synthesize_rows"):
                self.ran(step["tool"], summary="done")
        report = journey.build(self.thread)
        self.assertEqual(report["done_n"], report["total"])
        self.assertIsNone(report["next"])


class TheGateThatSaysWhyTest(JourneyTest):
    """A blocked route names the rule, the value, and where the value came from.

    Taken from the research lane's built format (`10-Signals/specs/
    refusal-formats.md` §1, `the-gate-that-says-why.html`): a refusal screen
    is worth building only if it carries "the rule, the value, its origin, the
    arithmetic". The route already said WHICH outcome it reached and how many
    gates passed; it did not say which rule stopped it or what number failed
    it, which is the whole of the why.

    Every part of this is the ledger's own: the gate id and its `clause` come
    from `journey_report`, the facts are the ones that clause names, and their
    values carry the origins the ledger stamped. Nothing is composed here that
    the engine did not already decide - a refusal screen that paraphrased its
    own verdict would be the one place in this product allowed to drift.
    """

    def _blocked(self, gates, facts=(), declared=()):
        from unittest import mock

        # `fact_origins` carries EVERY fact the ledger declares, measured or
        # not - that is how a real report reads - so a clause naming a fact
        # nobody measured still resolves to a name this knows.
        origins = {f["fact"]: f["origin"] for f in facts}
        for name in declared:
            origins.setdefault(name, "DEFAULTED")
        answer = {
            "verdict": {
                "outcome": "ACTION__MEASURE_BASELINE",
                "say": "",
                "gates": gates,
                "fact_origins": origins,
            },
            "facts": list(facts),
        }
        with mock.patch.object(journey.journey_report, "build", lambda _t: answer):
            return self.on_the_route()["verdict"]

    def test_the_first_failed_gate_is_the_one_named(self):
        got = self._blocked(
            {
                "G0_EVAL_SET": {"status": "PASSED", "clause": "eval_size_n >= 30"},
                "G1_BASELINE_MEASURED": {
                    "status": "FAILED",
                    "clause": "baseline_measured and baseline_score is not null",
                },
                "G2_PROMPT_EXHAUSTED": {"status": "NOT_REACHED", "clause": None},
            },
            facts=[{"fact": "eval_size_n", "value": 30, "origin": "MEASURED", "how": "counted"}],
        )
        self.assertEqual(got["blocked_by"]["gate"], "G1_BASELINE_MEASURED")
        self.assertIn("baseline_measured", got["blocked_by"]["clause"])

    def test_the_clause_s_own_facts_are_named_with_their_values(self):
        got = self._blocked(
            {
                "G0_EVAL_SET": {"status": "FAILED", "clause": "eval_size_n >= 30"},
            },
            facts=[{"fact": "eval_size_n", "value": 24, "origin": "MEASURED",
                    "how": "counted 24 rows in ui.eval.jsonl"}],
        )
        reads = got["blocked_by"]["reads"]
        self.assertEqual(len(reads), 1)
        self.assertEqual(reads[0]["fact"], "eval_size_n")
        self.assertEqual(reads[0]["value"], 24)
        self.assertEqual(reads[0]["origin"], "MEASURED")
        self.assertIn("counted 24 rows", reads[0]["how"])

    def test_a_fact_the_clause_wants_and_nobody_measured_says_so(self):
        """The commonest refusal on this route, and the one a bare verdict
        hides: the rule is not false, it is unanswered."""
        got = self._blocked(
            {"G1_BASELINE_MEASURED": {"status": "FAILED", "clause": "baseline_score is not null"}},
            facts=[],
            declared=["baseline_score"],
        )
        reads = got["blocked_by"]["reads"]
        self.assertEqual(reads[0]["fact"], "baseline_score")
        self.assertIsNone(reads[0]["origin"])
        self.assertTrue(reads[0]["unmeasured"])

    def test_a_route_nothing_is_blocking_names_no_gate(self):
        got = self._blocked({"G0_EVAL_SET": {"status": "PASSED", "clause": "eval_size_n >= 30"}})
        self.assertIsNone(got["blocked_by"])


class EveryGateCanActuallyFailTest(JourneyTest):
    """Prove each gate can fail before trusting the screen that reports it.

    `blocked_by` reads the first gate whose status is FAILED and shows its
    clause. That is worth nothing if a gate never reaches FAILED, or reaches
    it carrying no clause - the screen would be silently empty on exactly the
    refusal it exists for, and nothing would say so. A refusal format is only
    as good as its worst gate.

    Each case below drives the real ledger to that gate's own failure and
    asserts the screen has something to show: the gate named, the clause the
    ledger states it in, and at least one fact it reads.
    """

    def _screen(self, gates, facts, declared):
        from unittest import mock

        origins = {f["fact"]: f["origin"] for f in facts}
        for name in declared:
            origins.setdefault(name, "DEFAULTED")
        answer = {
            "verdict": {"outcome": "ACTION__X", "say": "", "gates": gates, "fact_origins": origins},
            "facts": list(facts),
        }
        with mock.patch.object(journey.journey_report, "build", lambda _t: answer):
            return self.on_the_route()["verdict"]["blocked_by"]

    #: The five gates, each with the clause the ledger states it in and one
    #: fact that clause reads. Taken from docs/diagnosis_engine.yaml's own
    #: `passes_when` rows rather than paraphrased.
    GATES = [
        ("G0_EVAL_SET", "eval_size_n >= 30", "eval_size_n"),
        (
            "G1_BASELINE_MEASURED",
            "baseline_measured and baseline_score is not null and trivial_baseline_score is not null",
            "baseline_measured",
        ),
        (
            "G2_PROMPT_EXHAUSTED",
            "prompt_iterations >= 3 and fewshot_tried and (prompt_optimizer_tried or not metric_is_programmatic or eval_size_n < 50)",
            "prompt_iterations",
        ),
        ("G3_RETRIEVAL_CONSIDERED", "retrieval_tried", "retrieval_tried"),
        ("G4_CHEAPER_MODEL_CONSIDERED", "model_swap_tried", "model_swap_tried"),
    ]

    def test_each_of_the_five_gates_produces_a_readable_refusal_when_it_fails(self):
        for gate, clause, reads in self.GATES:
            with self.subTest(gate):
                screen = self._screen(
                    {gate: {"status": "FAILED", "clause": clause}},
                    facts=[],
                    declared=[reads],
                )
                self.assertIsNotNone(screen, f"{gate} failed and the screen was empty")
                self.assertEqual(screen["gate"], gate)
                self.assertEqual(screen["clause"], clause)
                self.assertTrue(screen["reads"], f"{gate}'s clause named no fact this could show")
                self.assertIn(reads, [r["fact"] for r in screen["reads"]])

    def test_the_ledger_still_states_each_gate_the_way_this_screen_reads_it(self):
        """The clauses above are quoted from the ledger. If one is edited there
        and not here, this screen would be showing a rule the engine no longer
        applies - so the file is read and the quotes are checked against it."""
        from pathlib import Path

        ledger = (Path(__file__).resolve().parents[1] / "docs" / "diagnosis_engine.yaml").read_text(
            encoding="utf-8"
        )
        for gate, clause, _ in self.GATES:
            with self.subTest(gate):
                self.assertIn(clause, ledger, f"{gate}'s clause is not in the ledger as quoted")


class ARouteThatStoppedBeforeAnyGateTest(JourneyTest):
    """A blocked route with nothing FAILED still has to say what was checked.

    `blocked_by` read the first FAILED gate and returned nothing otherwise, so
    BLOCKED__DEFINE_SUCCESS_FIRST - where all five gates are NOT_REACHED and
    none carries a clause - rendered no rule at all. The screen was empty on
    exactly the refusal it exists for, and nothing in the product said so.
    """

    def _screen(self, outcome, statuses, facts=(), declared=()):
        from unittest import mock

        origins = {f["fact"]: f["origin"] for f in facts}
        for name in declared:
            origins.setdefault(name, "DEFAULTED")
        answer = {
            "verdict": {
                "outcome": outcome,
                "say": "",
                "gates": {g: {"status": st, "clause": None} for g, st in statuses.items()},
                "fact_origins": origins,
            },
            "facts": list(facts),
        }
        with mock.patch.object(journey.journey_report, "build", lambda _t: answer):
            return self.on_the_route()["verdict"]["blocked_by"]

    ALL_UNREACHED = {
        "G0_EVAL_SET": "NOT_REACHED",
        "G1_BASELINE_MEASURED": "NOT_REACHED",
        "G2_PROMPT_EXHAUSTED": "NOT_REACHED",
        "G3_RETRIEVAL_CONSIDERED": "NOT_REACHED",
        "G4_CHEAPER_MODEL_CONSIDERED": "NOT_REACHED",
    }

    def test_a_blocked_route_with_no_failed_gate_still_names_the_first_rule(self):
        screen = self._screen("BLOCKED__DEFINE_SUCCESS_FIRST", self.ALL_UNREACHED)
        self.assertIsNotNone(screen, "the refusal screen was empty")
        self.assertEqual(screen["gate"], "G0_EVAL_SET")
        self.assertEqual(screen["clause"], "eval_size_n >= 30")

    def test_it_says_that_gate_was_never_checked_rather_than_that_it_failed(self):
        """The two are different claims and call for different next moves. A
        rule nobody evaluated is not a rule that came back false."""
        screen = self._screen("BLOCKED__DEFINE_SUCCESS_FIRST", self.ALL_UNREACHED)
        self.assertIs(screen["reached"], False)
        self.assertEqual(screen["checked"], 0)
        self.assertEqual(screen["of"], 5)

    def test_the_rule_it_names_is_read_from_the_ledger_not_invented(self):
        """An unreached gate carries no clause, so the rule has to come from
        somewhere. It comes from the ledger's own `passes_when` row, which is
        the same text the engine would apply had it got that far."""
        from app import diagnosis

        screen = self._screen("BLOCKED__DEFINE_SUCCESS_FIRST", self.ALL_UNREACHED)
        row = diagnosis.load_spec().gate_row("G0_EVAL_SET", "any")
        self.assertEqual(screen["clause"], row["requires"])

    def test_it_reports_an_undecided_class_instead_of_guessing_a_rule(self):
        """G2 and G3 carry no `any` row - which rule applies depends on a
        method class this run has not chosen. Filling the line with one class's
        rule would teach a rule the run is not being judged by."""
        statuses = dict(self.ALL_UNREACHED)
        statuses["G0_EVAL_SET"] = "PASSED"
        statuses["G1_BASELINE_MEASURED"] = "PASSED"
        screen = self._screen("NO_TRAIN__RAG", statuses)
        self.assertEqual(screen["gate"], "G2_PROMPT_EXHAUSTED")
        self.assertIs(screen["class_undecided"], True)
        self.assertEqual(screen["clause"], "")
        self.assertEqual(screen["checked"], 2)

    def test_a_route_that_is_not_refusing_gets_no_first_rule_banner(self):
        """A route still working through its steps is not blocked. Showing it
        "the rule that comes first" would be noise dressed as a refusal."""
        self.assertIsNone(self._screen("ACTION__MEASURE_BASELINE", self.ALL_UNREACHED))

    def test_a_failed_gate_still_wins_over_an_unreached_one(self):
        """When something actually failed, that is the rule that stopped the
        route - the fallback must not shadow it."""
        statuses = dict(self.ALL_UNREACHED)
        statuses["G1_BASELINE_MEASURED"] = "FAILED"
        from unittest import mock

        answer = {
            "verdict": {
                "outcome": "BLOCKED__DEFINE_SUCCESS_FIRST",
                "say": "",
                "gates": {
                    g: {
                        "status": st,
                        "clause": "baseline_measured" if st == "FAILED" else None,
                    }
                    for g, st in statuses.items()
                },
                "fact_origins": {"baseline_measured": "DEFAULTED"},
            },
            "facts": [],
        }
        with mock.patch.object(journey.journey_report, "build", lambda _t: answer):
            screen = self.on_the_route()["verdict"]["blocked_by"]
        self.assertEqual(screen["gate"], "G1_BASELINE_MEASURED")
        self.assertIs(screen["reached"], True)


class TheOverviewNeverWritesTest(JourneyTest):
    def test_building_it_files_nothing_into_the_thread(self):
        """The Stage's law, and this surface is under it too: a reader that
        wrote would file rows into the thread it is reading."""
        self.ran("attach_context", summary="attached")
        before = len(events.since(f"thread:{self.thread}", 0))
        journey.build(self.thread)
        journey.build(self.thread)
        self.assertEqual(len(events.since(f"thread:{self.thread}", 0)), before)


if __name__ == "__main__":
    unittest.main()
