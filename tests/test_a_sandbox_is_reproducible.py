"""The other two promises: reproducible, and honest about what it cannot reach.

`docs/THE_PROPOSAL_LOOP.md` asks a sandbox for three things. Disposability is
attacked in `tests/test_a_sandbox_is_disposable.py`. This file takes the other
two, and it takes them the way the product takes a number: by going and looking
rather than by reading the docstring back.

**Reproducible** is proved by running the same thing twice and comparing the
bytes, not by asserting that a field called `pinned` is true. Two sandboxes made
from the same recipe and the same data must carry the same fingerprint and must
produce the same output, and the fingerprint must not move because they were
made a minute apart - `app/build.py` records what happens when a timestamp gets
into a hash that approval compares.

**Cannot reach what it was not given** is proved by reading the environment the
run actually received, from inside the run. A no-egress sandbox that still
handed a job this harness's port and bearer token would be the exact shape of
overclaim `app/tools/sandbox.py` spends its second section refusing to make, and
a test that only read the docstring's list would not see it.

And one test here is about the docstring on purpose: every result this module
returns must carry the list of things no-egress does NOT enforce. The limit is
the claim's evidence, and a limit that lives only in a source file is one the
person deciding where to put their data never sees.
"""

from __future__ import annotations

import json
import sys
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import build, jobspec, runner  # noqa: E402
from app.tools import sandbox  # noqa: E402
from app.tools.registry import ApprovalRequired, REGISTRY  # noqa: E402
from tests import support  # noqa: E402


#: A recipe whose output depends on its config and on nothing else - no clock,
#: no random seed, no path that differs between two sandboxes. Running it twice
#: is the reproducibility measurement, so anything time-varying in here would
#: silently turn that measurement into a coin flip.
DETERMINISTIC = """
    import argparse, hashlib, json, os
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind")
    parser.add_argument("--job-json")
    args = parser.parse_args()
    job = json.loads(open(args.job_json, encoding="utf-8").read())
    body = json.dumps(job["config"], sort_keys=True)
    print("kind=" + args.kind)
    print("config=" + body)
    print("digest=" + hashlib.sha256(body.encode("utf-8")).hexdigest())
    print("cwd=" + os.path.basename(os.getcwd()))
    print("temp=" + os.path.basename(os.environ.get("TEMP", "")))
    print("has_port=" + str(bool(os.environ.get("MLH_PORT"))))
    print("has_token=" + str(bool(os.environ.get("MLH_TOKEN"))))
    print("hf_offline=" + str(os.environ.get("HF_HUB_OFFLINE")))
    print("keys=" + ",".join(sorted(os.environ)))
    open("wrote_here.txt", "w", encoding="utf-8").write("relative")
"""


def a_recipe(name, source=DETERMINISTIC, kinds=("train", "eval"), lock=None, venv=None):
    """Write a fixture recipe into the temporary recipes tree `support` bound.

    `lock` and `venv` are what make a recipe *pinned*: the lockfile is the
    record of what was installed and the venv is the interpreter that will be
    argv[0]. Both are written as files here rather than materialised with uv,
    because what is under test is whether this module reports what is on disk -
    not whether uv works.
    """
    directory = Path(jobspec.RECIPES_ROOT) / name
    directory.mkdir(parents=True, exist_ok=True)
    kind_list = ", ".join(f'"{k}"' for k in kinds)
    (directory / "recipe.toml").write_text(
        f'name = "{name}"\nkinds = [{kind_list}]\nentrypoint = "entrypoint.py"\n',
        encoding="utf-8",
    )
    (directory / "entrypoint.py").write_text(
        textwrap.dedent(source).strip() + "\n", encoding="utf-8"
    )
    if lock is not None:
        (directory / "requirements.lock").write_text(lock, encoding="utf-8")
    if venv is not None:
        env = directory / ".venv"
        (env / "Scripts").mkdir(parents=True, exist_ok=True)
        (env / "bin").mkdir(parents=True, exist_ok=True)
        (env / "Scripts" / "python.exe").write_text("", encoding="utf-8")
        (env / "bin" / "python").write_text("", encoding="utf-8")
        (env / "pyvenv.cfg").write_text(
            f"home = C:\\\\Python\nversion = {venv}\n", encoding="utf-8"
        )
    return directory


class SandboxTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        a_recipe("deterministic")

    def a_file(self, name="train.jsonl", body='{"text": "one"}\n'):
        path = self.root / name
        path.write_text(body, encoding="utf-8")
        return path


# ---------------------------------------------------------------------------
# What pins an environment on this machine.


class WhatPinsAnEnvironmentTest(SandboxTest):
    def test_a_recipe_with_a_lockfile_and_a_venv_is_reported_as_pinned(self):
        a_recipe(
            "pinned-one",
            lock="# a comment\n\ntorch==2.6.0\npeft==0.18.0\n",
            venv="3.11.9",
        )
        pin = sandbox.pin("pinned-one")

        self.assertTrue(pin["pinned"])
        self.assertEqual(pin["installs"], ("torch==2.6.0", "peft==0.18.0"))
        self.assertTrue(pin["lock_digest"])
        self.assertIn(".venv", pin["interpreter"])

    def test_the_python_version_comes_from_the_venv_and_not_from_this_process(self):
        """A real number measured off the wrong interpreter is still wrong.

        `sys.version` is the harness's Python. Reporting it as the pinned
        environment's would be the defect `app/build.py`'s second hard rule
        exists for: an impeccable provenance chain attached to the wrong thing.
        """
        a_recipe("pinned-two", lock="trl==1.0.0\n", venv="3.10.4")
        pin = sandbox.pin("pinned-two")

        self.assertEqual(pin["python"], "3.10.4")
        self.assertNotEqual(pin["python"], sys.version.split()[0])
        self.assertIn("pyvenv.cfg", pin["python_source"])

    def test_a_lockfile_with_no_built_venv_is_not_called_a_pin(self):
        """The state this machine is actually in, said rather than papered over."""
        a_recipe("declared-only", lock="torch==2.6.0\n")
        pin = sandbox.pin("declared-only")

        self.assertFalse(pin["pinned"])
        self.assertIn("has not been built", pin["why"])
        self.assertEqual(pin["interpreter"], sys.executable)
        self.assertIn("not built", pin["interpreter_is"])

    def test_a_sandbox_with_no_recipe_says_it_is_not_reproducible(self):
        pin = sandbox.pin(None)
        self.assertFalse(pin["pinned"])
        self.assertIn("not reproducible", pin["why"])

    def test_an_unknown_recipe_is_refused_by_name(self):
        answered = REGISTRY.call("make_sandbox", {"name": "x", "recipe": "nope"})
        self.assertFalse(answered["ok"])
        self.assertIn("unknown recipe", answered["detail"])

    def test_the_pin_reaches_the_manifest_and_the_environment(self):
        a_recipe("pinned-three", lock="torch==2.6.0\n", venv="3.11.9")
        made = sandbox.create("boxed", recipe="pinned-three")

        self.assertTrue(made["pinned"]["pinned"])
        environment = sandbox.environment_for("boxed")
        self.assertIsInstance(environment, build.Environment)
        self.assertEqual(environment.installs, ("torch==2.6.0",))
        self.assertEqual(environment.python, "3.11.9")
        self.assertFalse(environment.egress)


# ---------------------------------------------------------------------------
# The data as it was.


class TheDataAsItWasTest(SandboxTest):
    def test_a_file_is_copied_in_and_digested(self):
        source = self.a_file()
        made = sandbox.create("snap", data=[str(source)])

        row = made["snapshotted"][0]
        self.assertTrue(row["copied"])
        self.assertEqual(len(row["digest"]), 64)
        self.assertEqual(
            Path(row["copied_to"]).read_text(encoding="utf-8"),
            source.read_text(encoding="utf-8"),
        )
        self.assertEqual(row["provenance"]["bytes"], "measured")

    def test_the_copy_survives_a_change_to_the_original(self):
        """"The data as it was" has to mean *was*, or the word is decoration."""
        source = self.a_file()
        made = sandbox.create("snap", data=[str(source)])
        source.write_text("something else entirely\n", encoding="utf-8")

        held = Path(made["snapshotted"][0]["copied_to"]).read_text(encoding="utf-8")
        self.assertEqual(held, '{"text": "one"}\n')

    def test_two_sources_with_the_same_basename_do_not_land_on_each_other(self):
        first = self.root / "a"
        second = self.root / "b"
        first.mkdir()
        second.mkdir()
        (first / "train.jsonl").write_text("first\n", encoding="utf-8")
        (second / "train.jsonl").write_text("second\n", encoding="utf-8")

        made = sandbox.create(
            "two", data=[str(first / "train.jsonl"), str(second / "train.jsonl")]
        )
        held = [
            Path(row["copied_to"]).read_text(encoding="utf-8")
            for row in made["snapshotted"]
        ]
        self.assertEqual(held, ["first\n", "second\n"])

    def test_a_file_over_the_limit_is_recorded_where_it_is_and_says_so(self):
        source = self.a_file(body="x" * 4096)
        with mock.patch.object(sandbox, "SNAPSHOT_BYTE_LIMIT", 10):
            made = sandbox.create("big", data=[str(source)])

        row = made["snapshotted"][0]
        self.assertFalse(row["copied"])
        self.assertIn("over this sandbox's copy limit", row["why"])
        self.assertGreater(row["bytes"], 10)

    def test_a_folder_is_recorded_and_never_walked(self):
        folder = self.root / "corpus"
        folder.mkdir()
        (folder / "one.txt").write_text("x", encoding="utf-8")

        made = sandbox.create("folder", data=[str(folder)])
        row = made["snapshotted"][0]
        self.assertFalse(row["copied"])
        self.assertIn("says nothing about the files inside it", row["why"])

    def test_data_that_is_not_there_is_refused_and_leaves_nothing_behind(self):
        answered = REGISTRY.call(
            "make_sandbox", {"name": "ghost", "data": [str(self.root / "nope.jsonl")]}
        )
        self.assertFalse(answered["ok"])
        self.assertIn("cannot snapshot", answered["detail"])
        self.assertEqual(sandbox.every(), [])
        self.assertFalse((sandbox.sandboxes_root() / "ghost").exists())


# ---------------------------------------------------------------------------
# Reproducible: the same thing twice.


class TheSameThingTwiceTest(SandboxTest):
    def test_two_sandboxes_from_the_same_inputs_have_the_same_fingerprint(self):
        source = self.a_file()
        first = sandbox.create("one", recipe="deterministic", data=[str(source)])
        second = sandbox.create("two", recipe="deterministic", data=[str(source)])

        self.assertTrue(first["fingerprint"])
        self.assertEqual(first["fingerprint"], second["fingerprint"])

    def test_the_fingerprint_does_not_move_because_time_passed(self):
        """`app/build.py` paid for this lesson; it is not paid for twice.

        A timestamp inside a hash that approval compares made approval fail for
        every human who took longer than a second to read a plan. The same
        mistake here would mean two identical environments could never be shown
        to be identical.
        """
        source = self.a_file()
        first = sandbox.create("one", recipe="deterministic", data=[str(source)])
        time.sleep(1.05)
        second = sandbox.create("two", recipe="deterministic", data=[str(source)])

        self.assertNotEqual(first["created_at"], second["created_at"])
        self.assertEqual(first["fingerprint"], second["fingerprint"])

    def test_different_data_is_a_different_fingerprint(self):
        first = sandbox.create(
            "one", recipe="deterministic", data=[str(self.a_file("a.jsonl", "a\n"))]
        )
        second = sandbox.create(
            "two", recipe="deterministic", data=[str(self.a_file("b.jsonl", "b\n"))]
        )
        self.assertNotEqual(first["fingerprint"], second["fingerprint"])

    def test_running_the_same_thing_twice_gives_the_same_result(self):
        """The measurement, rather than the claim.

        Two separate sandboxes, the same recipe, the same config, compared byte
        for byte. If anything in the environment this module builds varied per
        sandbox - a path in the output, a temp directory that leaked through, a
        token present one time and not the other - this is where it shows up.
        """
        sandbox.create("first", recipe="deterministic")
        sandbox.create("second", recipe="deterministic")

        one = sandbox.run("first", kind="train", config={"steps": 3, "seed": 7})
        two = sandbox.run("second", kind="train", config={"steps": 3, "seed": 7})

        self.assertEqual(one["exit_code"], 0, one["output"])
        self.assertEqual(two["exit_code"], 0, two["output"])
        self.assertEqual(one["output"], two["output"])
        self.assertIn("digest=", one["output"])

    def test_running_it_twice_in_one_sandbox_gives_the_same_result(self):
        sandbox.create("again", recipe="deterministic")
        one = sandbox.run("again", config={"steps": 3})
        two = sandbox.run("again", config={"steps": 3})

        self.assertEqual(one["output"], two["output"])
        self.assertNotEqual(one["run_dir"], two["run_dir"])

    def test_a_different_config_is_a_different_result(self):
        """The positive control for the test above.

        Identical output from two runs proves reproducibility only if this
        recipe's output could have differed. Without this, a recipe that
        printed a constant would pass the test above and prove nothing.
        """
        sandbox.create("control", recipe="deterministic")
        one = sandbox.run("control", config={"steps": 3})
        two = sandbox.run("control", config={"steps": 4})
        self.assertNotEqual(one["output"], two["output"])

    def test_the_run_lands_in_the_sandbox_and_goes_with_it(self):
        sandbox.create("held", recipe="deterministic")
        result = sandbox.run("held", config={"steps": 1})

        run_dir = Path(result["run_dir"])
        directory = Path(sandbox.read_manifest("held")["path"])
        self.assertIn(directory, run_dir.parents)
        self.assertTrue((run_dir / "job.json").is_file())
        self.assertTrue((Path(result["cwd"]) / "wrote_here.txt").is_file())

        sandbox.destroy("held")
        self.assertFalse(run_dir.exists())


# ---------------------------------------------------------------------------
# What it can and cannot reach.


class WhatItCanReachTest(SandboxTest):
    def test_a_no_egress_run_is_given_no_address_and_no_token_for_this_harness(self):
        """The one egress control this module can actually enforce, measured.

        Read out of the environment the run itself received. A test that
        asserted on `reach()["enforced"]` would be reading the claim back.
        """
        sandbox.create("shut", recipe="deterministic")
        result = sandbox.run("shut", config={})

        self.assertIn("has_port=False", result["output"])
        self.assertIn("has_token=False", result["output"])
        self.assertIn("hf_offline=1", result["output"])

    def test_a_sandbox_that_declared_egress_is_given_the_address(self):
        sandbox.create(
            "open", recipe="deterministic", egress=True,
            egress_reason="it downloads a base model from the Hub",
        )
        result = sandbox.run("open", config={})

        self.assertIn("has_port=True", result["output"])
        self.assertIn("hf_offline=None", result["output"])
        self.assertIn("downloads a base model", result["reach"]["egress_reason"])

    def test_the_run_inherits_none_of_the_engine_s_environment(self):
        """A provider key exported into the engine's shell must not travel."""
        with mock.patch.dict(
            "os.environ", {"OPENAI_API_KEY": "sk-should-never-travel"}, clear=False
        ):
            sandbox.create("clean", recipe="deterministic")
            result = sandbox.run("clean", config={})

        self.assertNotIn("OPENAI_API_KEY", result["output"])
        self.assertNotIn("sk-should-never-travel", result["output"])

    def test_the_run_lands_in_the_working_directory_and_its_own_temp(self):
        sandbox.create("located", recipe="deterministic")
        result = sandbox.run("located", config={})

        self.assertIn(f"cwd={sandbox.WORK}", result["output"])
        self.assertIn(f"temp={sandbox.TMP}", result["output"])

    def test_egress_without_a_reason_is_refused(self):
        answered = REGISTRY.call("make_sandbox", {"name": "leaky", "egress": True})
        self.assertFalse(answered["ok"])
        self.assertIn("must say what for", answered["detail"])

    def test_a_reason_without_egress_is_refused(self):
        answered = REGISTRY.call(
            "make_sandbox", {"name": "confusing", "egress_reason": "the Hub"}
        )
        self.assertFalse(answered["ok"])
        self.assertIn("will read to the next person", answered["detail"])

    def test_every_result_carries_the_limit_of_the_claim(self):
        """The honest register, enforced.

        A sandbox that says "no egress" and does not say what that does not
        cover is worse than one that says nothing, because the claim is what a
        person relies on when deciding where to put sensitive data. So the
        limit travels with every result, from every door.
        """
        made = sandbox.create("honest", recipe="deterministic")
        listed = REGISTRY.call("list_sandboxes")
        ran = sandbox.run("honest", config={})

        for label, payload in (
            ("make_sandbox", made["reach"]["not_enforced"]),
            ("list_sandboxes", listed["reach_note"]),
            ("run_in_sandbox", ran["reach"]["not_enforced"]),
        ):
            with self.subTest(door=label):
                text = " ".join(payload)
                self.assertIn("operating system is not stopping a socket", text)
                self.assertIn("not a jail", text)

        self.assertIn("is not stopping it from opening a socket", made["say"])


# ---------------------------------------------------------------------------
# The bound, the interpreter, and the doors.


class TheRunIsBoundedAndPinnedTest(SandboxTest):
    def test_argv_zero_is_the_interpreter_the_sandbox_pinned(self):
        """The one-line substitution `app/jobspec.py` was shaped to accept.

        Captured at the runner's door rather than inferred from the report,
        because what matters is the argv a process is actually started with.
        """
        a_recipe("pinned-run", lock="torch==2.6.0\n", venv="3.11.9")
        sandbox.create("venved", recipe="pinned-run")
        seen = {}

        def capture(argv, timeout, log_path, cwd=None, env=None):
            seen["argv"] = list(argv)
            seen["cwd"] = str(cwd)
            Path(log_path).write_text("", encoding="utf-8")
            return 0

        with mock.patch.object(runner, "_run_streaming", capture):
            result = sandbox.run("venved", config={})

        self.assertIn(".venv", seen["argv"][0])
        self.assertEqual(seen["argv"][0], result["interpreter"])
        self.assertTrue(seen["argv"][1].endswith("entrypoint.py"))
        self.assertEqual(seen["argv"][2], "--kind")
        self.assertEqual(seen["cwd"], result["cwd"])

    def test_an_unpinned_sandbox_runs_on_this_harness_s_interpreter_and_says_so(self):
        sandbox.create("plain", recipe="deterministic")
        result = sandbox.run("plain", config={})
        self.assertEqual(result["interpreter"], sys.executable)
        self.assertFalse(result["pinned"])

    def test_the_timeout_actually_bounds_the_run(self):
        """Measured against the clock, the way `app/runner.py` insists on.

        `sleeper` sleeps for thirty seconds. A bound that is not a bound
        reports the right exit code and takes thirty seconds to do it, which is
        exactly the failure that runner's docstring records.
        """
        sandbox.create("slow", recipe="sleeper")
        started = time.monotonic()
        result = sandbox.run("slow", kind="train", config={}, timeout_seconds=1)
        elapsed = time.monotonic() - started

        self.assertTrue(result["timed_out"])
        self.assertEqual(result["exit_code"], -1)
        self.assertLess(elapsed, 15, "the timeout did not bound anything")
        self.assertIn("TIMEOUT", result["output"])

    def test_a_kind_the_recipe_does_not_support_is_refused_before_anything_runs(self):
        sandbox.create("narrow", recipe="deterministic")
        answered = REGISTRY.call(
            "run_in_sandbox",
            {"name": "narrow", "kind": "convert"},
            approved=True,
        )
        self.assertFalse(answered["ok"])
        self.assertIn("does not support kind", answered["detail"])

    def test_a_manifest_missing_a_directory_is_a_sentence_and_not_a_traceback(self):
        """`sandbox.json` is a file on the user's disk, so it can be damaged.

        Reading it with `[]` turns a truncated write or a hand edit into a
        `KeyError` out of a registered tool, and this product's boundary rule
        is that a person is never handed a stack trace. The recomposed path is
        not a guess: these are fixed children of the sandbox's own directory.
        """
        sandbox.create("damaged", recipe="deterministic")
        path = Path(sandbox.read_manifest("damaged")["path"])
        body = json.loads((path / sandbox.MANIFEST).read_text(encoding="utf-8"))
        for key in ("work_dir", "tmp_dir", "runs_dir"):
            body.pop(key)
        (path / sandbox.MANIFEST).write_text(json.dumps(body), encoding="utf-8")

        result = sandbox.run("damaged", config={})

        self.assertEqual(result["exit_code"], 0, result["output"])
        self.assertEqual(Path(result["cwd"]), path / sandbox.WORK)

    def test_a_sandbox_with_no_recipe_has_nothing_to_run(self):
        sandbox.create("empty")
        answered = REGISTRY.call("run_in_sandbox", {"name": "empty"}, approved=True)
        self.assertFalse(answered["ok"])
        self.assertIn("pins no recipe", answered["detail"])

    def test_running_and_deleting_both_need_an_approval(self):
        """A model may propose either; a person is what makes them happen."""
        sandbox.create("guarded", recipe="deterministic")
        for name in ("run_in_sandbox", "delete_sandbox"):
            with self.subTest(tool=name):
                with self.assertRaises(ApprovalRequired):
                    REGISTRY.call(name, {"name": "guarded"})
        self.assertTrue(Path(sandbox.read_manifest("guarded")["path"]).is_dir())


class ListingSaysWhatIsThereTest(SandboxTest):
    def test_a_new_sandbox_is_listed_with_what_it_pinned(self):
        sandbox.create("listed", purpose="try a LoRA", recipe="deterministic")
        answered = REGISTRY.call("list_sandboxes")

        self.assertEqual(answered["count"], 1)
        row = answered["sandboxes"][0]
        self.assertEqual(row["name"], "listed")
        self.assertEqual(row["purpose"], "try a LoRA")
        self.assertEqual(row["pinned"]["recipe"], "deterministic")
        self.assertIn("delete_sandbox('listed')", row["delete_with"])

    def test_a_name_is_chosen_when_none_is_given(self):
        """"Make me somewhere safe to try this" should produce one, not a question."""
        first = REGISTRY.call("make_sandbox", {})
        second = REGISTRY.call("make_sandbox", {})
        self.assertEqual(first["name"], "sandbox-1")
        self.assertEqual(second["name"], "sandbox-2")

    def test_a_folder_with_no_manifest_is_listed_as_unusable_rather_than_hidden(self):
        root = sandbox.sandboxes_root()
        root.mkdir(parents=True, exist_ok=True)
        (root / "orphan").mkdir()

        rows = {row["name"]: row for row in sandbox.every()}
        self.assertIn("orphan", rows)
        self.assertFalse(rows["orphan"]["ok"])

    def test_the_same_name_twice_is_refused_rather_than_overwriting(self):
        sandbox.create("once")
        answered = REGISTRY.call("make_sandbox", {"name": "once"})
        self.assertFalse(answered["ok"])
        self.assertIn("already", answered["detail"])


if __name__ == "__main__":
    unittest.main()
