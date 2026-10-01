"""Attaching the world, and finding the eval set that was already there.

Two things are being proved here.

**Attach records, it does not copy.** A user who points the harness at a folder
should get a row in a table, not a duplicate of their disk. The test for that is
not a comment: it writes a file into an attached folder *after* attaching and
checks the harness reads the new content, which it could not do from a copy.

**The flagship moment.** `docs/VISION.md` and `docs/PRODUCT_SPEC.md` both single
out the user who believes they have no evaluation set while their own git
history contains one. Gate G0 blocks every training recommendation until an eval
set exists, so this is the difference between "you cannot train yet" and "you
can, and here is the file". The test builds a real git repository, commits a
`qa_pairs.jsonl`, deletes it in a later commit, and asserts the harness finds it
in the history and reports it as no longer on disk.

That test needs git. When git is not on the machine it skips - and the product
code takes the same route, reporting the history search under `checks_not_run`
rather than concluding there is no eval set. A missing tool must never look like
a finished search.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from app import dataquality
from app.tools import REGISTRY
from app.tools import context as context_tools

import support


GIT = shutil.which("git")


def git(repo: Path, *arguments: str) -> subprocess.CompletedProcess:
    """Run git in `repo` with a fixed argv. Used to build fixtures, not product code."""
    return subprocess.run(
        [
            GIT,
            "-C",
            str(repo),
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "user.name=Fixture",
            "-c",
            "commit.gpgsign=false",
            *arguments,
        ],
        shell=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


class ContextToolTestCase(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        self.work = self.root / "work"
        self.work.mkdir(parents=True, exist_ok=True)


class AttachTest(ContextToolTestCase):
    def test_attaching_a_folder_records_the_path_and_says_what_it_is(self):
        folder = self.work / "project"
        folder.mkdir()

        result = REGISTRY.call("attach_context", {"path": str(folder), "role": "the app"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["what_it_is"]["kind"], "folder")
        self.assertEqual(result["attached"]["role"], "the app")
        self.assertIn("no file was copied", result["stored"])

    def test_attaching_a_file_reports_its_detected_format_not_its_extension(self):
        path = self.work / "rows.csv"
        path.write_text('{"a": 1}\n{"a": 2}\n', encoding="utf-8")

        result = REGISTRY.call("attach_context", {"path": str(path)})

        self.assertEqual(result["what_it_is"]["kind"], "file")
        self.assertEqual(result["what_it_is"]["format"]["name"], "jsonl")

    def test_attaching_a_missing_path_fails_rather_than_recording_a_fiction(self):
        result = REGISTRY.call("attach_context", {"path": str(self.work / "nope")})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "not_found")
        self.assertEqual(REGISTRY.call("list_context")["count"], 0)

    def test_attaching_the_same_path_twice_updates_rather_than_duplicates(self):
        folder = self.work / "project"
        folder.mkdir()

        REGISTRY.call("attach_context", {"path": str(folder), "role": "first"})
        second = REGISTRY.call("attach_context", {"path": str(folder), "role": "second"})

        self.assertTrue(second["already_attached"])
        listing = REGISTRY.call("list_context")
        self.assertEqual(listing["count"], 1)
        self.assertEqual(listing["contexts"][0]["role"], "second")

    def test_nothing_is_copied_so_later_changes_are_visible(self):
        """The proof that attach recorded a path rather than took a snapshot."""
        folder = self.work / "project"
        folder.mkdir()
        REGISTRY.call("attach_context", {"path": str(folder)})

        (folder / "added_afterwards.txt").write_text("later", encoding="utf-8")
        stored = REGISTRY.call("list_context")["contexts"][0]["path"]
        read = REGISTRY.call(
            "read_context_file", {"path": str(Path(stored) / "added_afterwards.txt")}
        )

        self.assertTrue(read["ok"])
        self.assertEqual(read["data"]["content"], "later")

    def test_list_context_carries_provenance_for_its_count(self):
        folder = self.work / "project"
        folder.mkdir()
        REGISTRY.call("attach_context", {"path": str(folder)})

        listing = REGISTRY.call("list_context")

        self.assertEqual(listing["provenance"]["count"], dataquality.MEASURED)


class ReadContextFileTest(ContextToolTestCase):
    def test_a_text_file_comes_back_wrapped_as_data(self):
        path = self.work / "notes.md"
        path.write_text("# Notes\nNothing unusual here.\n", encoding="utf-8")

        result = REGISTRY.call("read_context_file", {"path": str(path)})

        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["role"], "data")
        self.assertFalse(result["data"]["trusted"])
        self.assertIn("Nothing unusual", result["data"]["content"])

    def test_a_large_file_is_truncated_and_says_so(self):
        path = self.work / "big.txt"
        path.write_text("x" * 5000, encoding="utf-8")

        result = REGISTRY.call(
            "read_context_file", {"path": str(path), "max_characters": 100}
        )

        self.assertTrue(result["data"]["truncated"])
        self.assertEqual(result["data"]["characters"], 100)

    def test_a_hostile_character_limit_is_bounded_rather_than_obeyed(self):
        path = self.work / "big.txt"
        path.write_text("x" * 100, encoding="utf-8")

        for value in (-1, 0, "lots", 10**12):
            with self.subTest(max_characters=value):
                result = REGISTRY.call(
                    "read_context_file", {"path": str(path), "max_characters": value}
                )
                self.assertTrue(result["ok"])
                self.assertLessEqual(
                    result["characters_requested"], context_tools.MAX_READ_CHARACTERS
                )

    def test_a_binary_file_is_refused_rather_than_decoded_into_noise(self):
        path = self.work / "model.bin"
        path.write_bytes(b"\x00\x01\x02" * 100)

        result = REGISTRY.call("read_context_file", {"path": str(path)})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "not_text")
        self.assertNotIn("data", result)

    def test_a_folder_is_refused_with_a_useful_next_step(self):
        result = REGISTRY.call("read_context_file", {"path": str(self.work)})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "is_a_directory")

    def test_a_missing_file_returns_no_data_envelope_at_all(self):
        """An empty envelope would be a claim that the file said nothing."""
        result = REGISTRY.call("read_context_file", {"path": str(self.work / "nope.txt")})

        self.assertFalse(result["ok"])
        self.assertNotIn("data", result)


class EvalNameMatchingTest(unittest.TestCase):
    def test_data_files_with_evaluation_names_match(self):
        for name in (
            "qa_pairs.jsonl", "data/golden_answers.csv", "eval/benchmark.json",
            "validation.tsv", "held_out.parquet", "ground_truth.yaml",
        ):
            with self.subTest(name=name):
                self.assertTrue(context_tools.looks_like_eval(name))

    def test_source_code_test_files_do_not_match(self):
        """Otherwise every repository in the world reports an eval set."""
        for name in (
            "tests/test_parser.py", "src/evaluate.py", "eval.ts",
            "spec/validation_spec.rb", "benchmark.go",
        ):
            with self.subTest(name=name):
                self.assertFalse(context_tools.looks_like_eval(name))

    def test_ordinary_data_files_do_not_match(self):
        for name in ("data/customers.csv", "config.json", "README.md"):
            with self.subTest(name=name):
                self.assertFalse(context_tools.looks_like_eval(name))


class RepositoryProfileTest(ContextToolTestCase):
    def build_repo(self) -> Path:
        repo = self.work / "repo"
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
        (repo / "src" / "util.py").write_text("x = 1\n", encoding="utf-8")
        (repo / "index.ts").write_text("export const a = 1;\n", encoding="utf-8")
        (repo / "requirements.txt").write_text(
            "# a comment\nfastapi==0.110.0\npydantic>=2\n\n", encoding="utf-8"
        )
        (repo / "package.json").write_text(
            json.dumps({"dependencies": {"react": "^18"}, "devDependencies": {"vite": "^5"}}),
            encoding="utf-8",
        )
        (repo / "README.md").write_text(
            "# Support bot\nAnswers customer questions.\n", encoding="utf-8"
        )
        return repo

    def test_it_reports_the_primary_language_measured_by_file_count(self):
        repo = self.build_repo()

        report = context_tools.profile_repo(str(repo))

        self.assertEqual(report["languages"]["primary"], "Python")
        self.assertEqual(report["languages"]["counts"]["Python"], 2)
        self.assertEqual(report["languages"]["provenance"], dataquality.MEASURED)
        self.assertIn("not lines of code", report["languages"]["measured_as"])

    def test_it_reads_declared_dependencies_and_says_declared_not_installed(self):
        repo = self.build_repo()

        dependencies = context_tools.profile_repo(str(repo))["dependencies"]
        by_file = {entry["file"]: entry for entry in dependencies["files"]}

        self.assertIn("fastapi", by_file["requirements.txt"]["names"])
        self.assertIn("pydantic", by_file["requirements.txt"]["names"])
        self.assertNotIn("# a comment", by_file["requirements.txt"]["names"])
        self.assertIn("react", by_file["package.json"]["names"])
        self.assertIn("Nothing here says they are installed", dependencies["means"])

    def test_the_readme_comes_back_as_data_not_as_prose_to_believe(self):
        repo = self.build_repo()

        report = context_tools.profile_repo(str(repo))

        self.assertEqual(report["readme"]["role"], "data")
        self.assertFalse(report["readme"]["trusted"])

    def test_a_malformed_manifest_is_a_fact_and_not_a_crash(self):
        repo = self.build_repo()
        (repo / "pyproject.toml").write_text("this is not toml [[[", encoding="utf-8")

        dependencies = context_tools.profile_repo(str(repo))["dependencies"]
        entry = next(e for e in dependencies["files"] if e["file"] == "pyproject.toml")

        self.assertFalse(entry["parsed"])
        self.assertIn("could not be parsed", entry["note"])

    def test_a_path_that_is_not_a_directory_says_so_and_runs_no_checks(self):
        path = self.work / "a.txt"
        path.write_text("hello", encoding="utf-8")

        report = context_tools.profile_repo(str(path))

        self.assertTrue(report["checks_not_run"])
        self.assertFalse(report["is_git_repository"])

    def test_finding_nothing_is_not_the_same_as_there_being_nothing(self):
        repo = self.build_repo()

        candidates = context_tools.profile_repo(str(repo))["eval_candidates"]

        self.assertEqual(candidates["in_working_tree"], [])
        self.assertIn("not the same as", candidates["found_nothing_means"])

    def test_a_non_repository_reports_the_history_search_as_not_run(self):
        """A search that could not happen must never look like a finished one."""
        repo = self.build_repo()

        report = context_tools.profile_repo(str(repo))

        self.assertFalse(report["is_git_repository"])
        self.assertFalse(report["eval_candidates"]["history_searched"])
        self.assertIn(
            "eval_set_in_git_history",
            {entry["check"] for entry in report["checks_not_run"]},
        )


@unittest.skipIf(GIT is None, "git is not installed on this machine")
class TheEvalSetInTheGitHistoryTest(ContextToolTestCase):
    """The flagship moment, against a real repository with a real history."""

    def build_repo_with_a_deleted_eval_set(self) -> Path:
        repo = self.work / "repo"
        repo.mkdir(parents=True)
        self.assertEqual(git(repo, "init").returncode, 0)
        (repo / "app.py").write_text("print('hi')\n", encoding="utf-8")
        (repo / "qa_pairs.jsonl").write_text(
            "\n".join(
                json.dumps({"question": f"q{i}", "answer": f"a{i}"}) for i in range(50)
            )
            + "\n",
            encoding="utf-8",
        )
        git(repo, "add", "-A")
        self.assertEqual(git(repo, "commit", "-m", "first").returncode, 0)

        (repo / "qa_pairs.jsonl").unlink()
        git(repo, "add", "-A")
        self.assertEqual(
            git(repo, "commit", "-m", "tidy up before the demo").returncode, 0
        )
        return repo

    def test_the_deleted_eval_set_is_found_in_the_history(self):
        repo = self.build_repo_with_a_deleted_eval_set()

        candidates = context_tools.profile_repo(str(repo))["eval_candidates"]

        self.assertTrue(candidates["history_searched"])
        self.assertEqual(candidates["in_working_tree"], [])
        self.assertIn("qa_pairs.jsonl", candidates["in_history_only"])

    def test_the_tool_leads_with_it_in_plain_language(self):
        repo = self.build_repo_with_a_deleted_eval_set()

        result = REGISTRY.call("profile_repository", {"path": str(repo)})

        self.assertTrue(result["ok"])
        self.assertIn("qa_pairs.jsonl", result["summary"])
        self.assertIn("git history", result["summary"])
        self.assertIn("may already have the eval set", result["summary"])

    def test_a_file_still_on_disk_is_reported_in_the_working_tree_not_the_history(self):
        repo = self.work / "repo2"
        repo.mkdir(parents=True)
        git(repo, "init")
        (repo / "eval_set.csv").write_text("q,a\n1,2\n", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-m", "add eval")

        candidates = context_tools.profile_repo(str(repo))["eval_candidates"]

        self.assertEqual(candidates["in_working_tree"], ["eval_set.csv"])
        self.assertEqual(candidates["in_history_only"], [])

    def test_the_candidates_are_labelled_as_a_guess_from_a_filename(self):
        repo = self.build_repo_with_a_deleted_eval_set()

        candidates = context_tools.profile_repo(str(repo))["eval_candidates"]

        self.assertEqual(candidates["provenance"], dataquality.INFERRED)
        self.assertIn("guess from a name", candidates["how"])

    def test_the_git_directory_itself_is_not_profiled_as_source(self):
        repo = self.build_repo_with_a_deleted_eval_set()

        report = context_tools.profile_repo(str(repo))

        self.assertTrue(report["is_git_repository"])
        self.assertLess(report["file_count"], 50)


class GitFailuresAreReportedTest(ContextToolTestCase):
    def test_a_git_that_cannot_be_run_is_a_check_not_run(self):
        """Simulated by pointing at a directory that is not a repository.

        The same branch handles a machine with no git at all: `_git` returns
        `(False, "", "git is not installed on this machine")` and the reason
        reaches `checks_not_run` unchanged.
        """
        folder = self.work / "plain"
        folder.mkdir()

        report = context_tools.profile_repo(str(folder))

        reasons = {entry["check"]: entry["why"] for entry in report["checks_not_run"]}
        self.assertIn("eval_set_in_git_history", reasons)
        self.assertTrue(reasons["eval_set_in_git_history"].strip())

    def test_git_is_never_invoked_through_a_shell(self):
        """Invariant 1, asserted against the source rather than promised."""
        source = Path(context_tools.__file__).read_text(encoding="utf-8")

        self.assertIn("shell=False", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("os.system", source)


if __name__ == "__main__":
    unittest.main()
