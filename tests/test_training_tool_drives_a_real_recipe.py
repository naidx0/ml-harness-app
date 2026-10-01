"""Starting a training run, and the run arriving in the transcript.

`docs/VISION.md` is blunt about the failure mode this file guards: *a stub that
looks like a trainer is worse than no trainer*. So the assertions here are
about the things that would let a stub through unnoticed -

* a run that is reported without a job row, a log file and an exit code;
* a recipe that trains against whatever happens to be importable rather than
  its own pinned environment;
* progress that is claimed but never reached the event spine;
* a status call that repeats itself, so a thread fills with the same fifty
  lines every time somebody asks how it is going.

The subprocess tests use the fixture recipes from `tests/support.py`, which are
real recipes in a real temporary `recipes/` tree, run by the real runner. The
shipped `hf-peft-lora` recipe is exercised for its refusal path, which is the
half that must work on a machine where nobody has built anything.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import db, events, jobspec
from app.tools import REGISTRY, training
from app.tools.registry import ApprovalRequired, RESERVED_ARGUMENTS, RESERVED_WRITES

import support


REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_RECIPE = REPO_ROOT / "recipes" / "hf-peft-lora"


class ApprovalWallTest(unittest.TestCase):
    """The expensive tool cannot happen by accident."""

    def setUp(self):
        self.root = support.sandbox(self)
        self.dataset = self.root / "data.jsonl"
        self.dataset.write_text('{"text": "hello"}\n', encoding="utf-8")

    def args(self, **overrides):
        base = {
            "recipe": "printer",
            "base_model": "acme/tiny",
            "dataset_path": str(self.dataset),
            "max_steps": 1,
        }
        base.update(overrides)
        return base

    def test_a_model_call_without_an_approval_is_refused(self):
        with self.assertRaises(ApprovalRequired):
            REGISTRY.call("start_training", self.args())

        self.assertEqual(db.list_jobs(), [], "a refused call must queue nothing")

    def test_the_declaration_says_it_needs_one(self):
        spec = REGISTRY.get("start_training")

        self.assertEqual(spec.approval, "always")
        self.assertTrue(spec.as_control()["needs_approval"])

    def test_the_approved_call_is_the_same_entry_point(self):
        result = REGISTRY.call("start_training", self.args(), approved=True)
        self.addCleanup(training.wait_for_supervisors, 60)

        self.assertTrue(result["ok"])
        self.assertEqual(len(db.list_jobs()), 1)

    def test_no_training_tool_can_write_a_gate(self):
        for name in ("start_training", "training_status", "list_recipes"):
            with self.subTest(tool=name):
                spec = REGISTRY.get(name)
                self.assertIsNotNone(spec)
                self.assertEqual(
                    {w.lower() for w in spec.writes} & RESERVED_WRITES, set()
                )
                properties = spec.schema.get("properties") or {}
                self.assertEqual(
                    {k for k in properties if k.lower() in RESERVED_ARGUMENTS}, set()
                )


class RefusalsTest(unittest.TestCase):
    """Everything that is refused is refused before the slot is taken."""

    def setUp(self):
        self.root = support.sandbox(self)
        self.dataset = self.root / "data.jsonl"
        self.dataset.write_text('{"text": "hello"}\n', encoding="utf-8")

    def test_a_dataset_that_is_not_there_is_refused_and_nothing_is_queued(self):
        result = training.start_training(
            recipe="printer",
            base_model="acme/tiny",
            dataset_path=str(self.root / "nope.jsonl"),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "no_dataset")
        self.assertEqual(db.list_jobs(), [])

    def test_an_unknown_recipe_says_what_there_is(self):
        result = training.start_training(
            recipe="not a recipe name",
            base_model="acme/tiny",
            dataset_path=str(self.dataset),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "unknown_recipe")
        self.assertIn("printer", result["available"])

    def test_a_recipe_whose_environment_is_not_built_is_refused_with_the_reason(self):
        recipe = jobspec.RECIPES_ROOT / "needsvenv"
        recipe.mkdir(parents=True, exist_ok=True)
        (recipe / "recipe.toml").write_text(
            'name = "needsvenv"\nkinds = ["train"]\nentrypoint = "entrypoint.py"\n',
            encoding="utf-8",
        )
        (recipe / "entrypoint.py").write_text("pass\n", encoding="utf-8")
        (recipe / "requirements.lock").write_text("torch==2.6.0\n", encoding="utf-8")

        result = training.start_training(
            recipe="needsvenv",
            base_model="acme/tiny",
            dataset_path=str(self.dataset),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "recipe_not_ready")
        self.assertIn("has not been built", result["detail"])
        self.assertEqual(db.list_jobs(), [])

    def test_only_declared_config_keys_reach_the_job(self):
        """`config` is the one caller-controlled thing that reaches a recipe."""
        result = REGISTRY.call(
            "start_training",
            {
                "recipe": "printer",
                "base_model": "acme/tiny",
                "dataset_path": str(self.dataset),
                "somethingelse": "rm -rf /",
            },
            approved=True,
        )
        self.addCleanup(training.wait_for_supervisors, 60)

        self.assertTrue(result["ok"])
        self.assertIn("somethingelse", result.get("ignored_arguments", []))

        job = db.get_job(result["job_id"])
        config = json.loads(job["config_json"])
        self.assertTrue(set(config) <= set(training.CONFIG_KEYS), sorted(config))


class ARealRunEndToEndTest(unittest.TestCase):
    """The tool, the runner, the log, and the transcript, in one pass."""

    def setUp(self):
        self.root = support.sandbox(self)
        self.dataset = self.root / "data.jsonl"
        self.dataset.write_text('{"text": "hello"}\n', encoding="utf-8")

        self.started = REGISTRY.call(
            "start_training",
            {
                "recipe": "printer",
                "base_model": "acme/tiny",
                "dataset_path": str(self.dataset),
                "run_name": "a real fixture run",
            },
            approved=True,
        )
        self.assertTrue(self.started["ok"], self.started)
        self.assertTrue(
            training.wait_for_supervisors(timeout=120), "the job never finished"
        )

    def test_the_job_actually_ran_and_left_evidence(self):
        job = db.get_job(self.started["job_id"])

        self.assertEqual(job["status"], "done")
        self.assertEqual(job["exit_code"], 0)
        self.assertTrue(Path(job["log_path"]).is_file())
        self.assertIn("kind=train", Path(job["log_path"]).read_text(encoding="utf-8"))

    def test_starting_writes_a_started_event_with_the_cost_it_expects(self):
        rows = events.since(f"run:{self.started['run_id']}", 0)
        started = [r for r in rows if r["kind"] == "train.started"]

        self.assertEqual(len(started), 1)
        payload = started[0]["payload"]
        self.assertEqual(payload["recipe"], "printer")
        self.assertIn("cost_preview", payload)
        self.assertIn(
            payload["cost_preview"]["verdict"],
            ("FITS", "SPILLS", "WONT_FIT", "UNKNOWN"),
        )

    def test_the_log_becomes_events_and_asking_twice_does_not_repeat_them(self):
        first = training.training_status(job_id=self.started["job_id"])
        second = training.training_status(job_id=self.started["job_id"])

        self.assertGreater(first["events_appended"], 0)
        self.assertEqual(second["events_appended"], 0)

        rows = events.since(f"run:{self.started['run_id']}", 0)
        texts = [r["payload"].get("text") for r in rows if r["kind"] == "train.log"]
        self.assertEqual(len(texts), len(set(texts)), texts)

    def test_the_status_reports_a_measured_elapsed_and_a_real_outcome(self):
        status = training.training_status(job_id=self.started["job_id"])

        self.assertEqual(status["state"], "done")
        self.assertTrue(status["finished"])
        self.assertTrue(status["succeeded"])
        self.assertEqual(status["elapsed_provenance"], "measured")
        self.assertIsNotNone(status["elapsed_seconds"])
        self.assertGreaterEqual(status["elapsed_seconds"], 0)

    def test_a_job_that_does_not_exist_is_said_so_rather_than_crashing(self):
        result = training.training_status(job_id=9999)

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "no_such_job")


class LogParsingTest(unittest.TestCase):
    """The defect that ate every per-step metric of a real training run."""

    def test_a_marker_is_found_after_a_progress_bar_on_the_same_line(self):
        line = " 40%|####      | 4/10 [00:01<00:02,  2.9it/s]" + \
            training.EVENT_PREFIX + '{"kind": "progress", "step": 4, "loss": 1.5}'

        payload = training.structured(line)

        self.assertIsNotNone(payload, "stderr interleaving hid the whole event")
        self.assertEqual(payload["step"], 4)

    def test_an_ordinary_line_is_not_mistaken_for_an_event(self):
        self.assertIsNone(training.structured("loading the model"))

    def test_a_marker_with_broken_json_is_left_as_ordinary_output(self):
        self.assertIsNone(training.structured(training.EVENT_PREFIX + "{not json"))

    def test_the_last_progress_is_read_from_the_log_not_from_this_drain(self):
        """A finished run must not report `null` progress to the next caller."""
        lines = [
            "loading",
            training.EVENT_PREFIX + '{"kind": "progress", "step": 1}',
            training.EVENT_PREFIX + '{"kind": "progress", "step": 9}',
            "done",
        ]

        self.assertEqual(training.latest_progress(lines)["step"], 9)
        self.assertIsNone(training.latest_progress(["nothing here"]))

    def test_a_queued_row_with_output_is_reported_as_running(self):
        """`db.next_queued_job` never marks a job running. Say the true thing."""
        job = {"status": "queued"}

        self.assertEqual(training.latest_state(job, []), "queued")
        self.assertEqual(training.latest_state(job, ["first line"]), "running")
        self.assertEqual(training.latest_state({"status": "done"}, []), "done")


class ElapsedTest(unittest.TestCase):
    def test_both_ends_are_read_as_utc(self):
        """SQLite writes UTC with no zone marker; reading one end as local time
        makes a two-minute run look four hours long, plausibly."""
        started = datetime.now(timezone.utc) - timedelta(seconds=90)
        job = {
            "created_at": started.strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": (started + timedelta(seconds=30)).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        }

        self.assertAlmostEqual(training._elapsed_seconds(job), 30.0, delta=1.5)

    def test_an_unparseable_stamp_is_none_rather_than_a_wrong_number(self):
        self.assertIsNone(training._elapsed_seconds({"created_at": "never"}))
        self.assertIsNone(training._elapsed_seconds({}))


class TheShippedRecipeTest(unittest.TestCase):
    """`hf-peft-lora` is a real recipe with a pinned environment."""

    def test_it_declares_a_lockfile_and_the_two_kinds_it_implements(self):
        """`train` and `eval`, and the second one is not decoration.

        The recipe grew `eval` when `score_the_adapter` arrived: the only place
        in this product that can put an adapter in front of text is the pinned
        environment that trained it, and `jobspec.validate` refuses a kind the
        recipe does not declare. A recipe that declared the kind without
        implementing it would be worse than one that declared nothing - the job
        would be accepted and would train instead of scoring - so the entrypoint
        is checked for the branch here and end to end in
        `tests/test_an_adapter_is_scored_where_it_was_made.py`.
        """
        manifest = (SHIPPED_RECIPE / "recipe.toml").read_text(encoding="utf-8")
        entrypoint = (SHIPPED_RECIPE / "entrypoint.py").read_text(encoding="utf-8")

        self.assertIn('kinds = ["train", "eval"]', manifest)
        self.assertIn('args.kind == "eval"', entrypoint)
        self.assertIn("def evaluate(", entrypoint)
        self.assertTrue((SHIPPED_RECIPE / "requirements.lock").is_file())
        self.assertTrue((SHIPPED_RECIPE / "entrypoint.py").is_file())

    def test_the_lockfile_pins_the_cuda_wheel_and_not_the_cpu_one(self):
        lock = (SHIPPED_RECIPE / "requirements.lock").read_text(encoding="utf-8")

        self.assertIn("download.pytorch.org/whl/cu124", lock)
        self.assertIn("torch==2.6.0+cu124", lock)

    def test_it_refuses_to_train_outside_its_pinned_environment(self):
        """The half that has to work on a machine where nothing is built.

        A copy of the entrypoint with no `.venv` beside it must refuse and say
        how to build one - not fall back to whatever interpreter is running it,
        which is how an unreproducible run gets reported as a training result.
        """
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        elsewhere = Path(temp.name)
        shutil.copy(SHIPPED_RECIPE / "entrypoint.py", elsewhere / "entrypoint.py")
        (elsewhere / "job.json").write_text(
            json.dumps({"recipe": "hf-peft-lora", "kind": "train", "config": {}}),
            encoding="utf-8",
        )

        completed = subprocess.run(
            [
                sys.executable,
                str(elsewhere / "entrypoint.py"),
                "--kind", "train",
                "--job-json", str(elsewhere / "job.json"),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("REFUSED", completed.stderr)
        self.assertIn("uv venv", completed.stderr)
        self.assertIn("cu124", completed.stderr)
        self.assertIn(training.EVENT_PREFIX, completed.stdout)

    def test_list_recipes_measures_the_environment_rather_than_quoting_it(self):
        report = training.recipe_report("hf-peft-lora")

        self.assertEqual(report["kinds"], ["train", "eval"])
        self.assertTrue(report["pinned_environment"]["declared"])
        environment = report["pinned_environment"]
        if environment["built"]:
            self.assertEqual(environment["on_disk_provenance"], "measured")
            self.assertGreater(environment["on_disk_gb"], 0)
        else:
            self.assertIsNone(environment["on_disk_gb"])
            self.assertIn("has not been built", report["detail"])


class ListRecipesTest(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)

    def test_it_lists_what_is_on_disk_and_what_can_actually_run(self):
        result = training.list_recipes()

        self.assertTrue(result["ok"])
        names = {r["name"] for r in result["recipes"]}
        self.assertIn("printer", names)
        self.assertIn("printer", result["ready_to_train"])
        # `brokenentry` declares an entrypoint that is not on disk.
        broken = [r for r in result["recipes"] if r["name"] == "brokenentry"]
        self.assertTrue(broken)


if __name__ == "__main__":
    unittest.main()
