"""Their review panel reads git, through the git CLI, in the project's folder.

Their review panel (`vendor/opencode/packages/app/src/session/review/model.ts`)
offers "git" for a project whose `vcs` is set and "branch" when `vcs.get`
names a current branch other than the default, reads `vcs.diff` in `working`
or `branch` mode, and re-reads on `filesystem.changed`. Every answer here is
validated against their OpenAPI document.

Each test builds its own repository in the sandbox - a test must own its
specimen - with its identity and signing set in that repository only.
"""

from __future__ import annotations

import shutil
import subprocess
import unittest

from app import events
from app.facade import sessions, translate

import openapi_contract as contract
from test_the_facade_speaks_their_protocol import FacadeTestCase

NEWLINE = chr(10)


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class TheReviewPanelReadsGitTest(FacadeTestCase):
    def setUp(self):
        super().setUp()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "symbolic-ref", "HEAD", "refs/heads/main")
        for key, value in (
            ("user.name", "Test"),
            ("user.email", "test@example.invalid"),
            ("commit.gpgsign", "false"),
            ("core.autocrlf", "false"),
        ):
            git(self.repo, "config", key, value)
        (self.repo / "keep.txt").write_bytes(b"one\ntwo\nthree\nfour\nfive\nsix\nseven\n")
        (self.repo / "gone.txt").write_bytes(b"bye\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "first")
        self.sid = self.create(location={"directory": str(self.repo)})["id"]
        self.where = {"location[directory]": str(self.repo)}

    def get(self, url, **params):
        return self.client.get(url, params={**self.where, **params})

    def change_the_work_tree(self):
        (self.repo / "keep.txt").write_bytes(b"one\ntwo\nthree\nFOUR\nfive\nsix\nseven\n")
        (self.repo / "gone.txt").unlink()
        (self.repo / "new.txt").write_bytes(b"a\nb\n")
        (self.repo / "blob.bin").write_bytes(b"\x00\x01\x02" * 100)

    def test_the_project_says_git_and_a_plain_folder_does_not(self):
        plain = self.root / "plain"
        plain.mkdir()
        self.create(location={"directory": str(plain)})
        projects = contract.assert_response(self, "project.list", self.client.get("/oc/api/project"))
        by_folder = {p["canonical"]: p for p in projects}
        self.assertEqual(by_folder[str(self.repo)]["vcs"], "git")
        self.assertNotIn("vcs", by_folder[str(plain)])

    def test_vcs_get_names_the_branch_and_the_default(self):
        body = contract.assert_response(self, "vcs.get", self.get("/oc/api/vcs"))
        self.assertEqual(body["data"], {"provider": "git", "branch": {"current": "main", "default": "main"}})

    def test_status_counts_every_change_untracked_too(self):
        self.change_the_work_tree()
        body = contract.assert_response(self, "vcs.status", self.get("/oc/api/vcs/status"))
        rows = {row["file"]: row for row in body["data"]}
        self.assertEqual(rows["keep.txt"], {"file": "keep.txt", "additions": 1, "deletions": 1, "status": "modified"})
        self.assertEqual(rows["gone.txt"]["status"], "deleted")
        self.assertEqual(rows["new.txt"], {"file": "new.txt", "additions": 2, "deletions": 0, "status": "added"})
        self.assertEqual(rows["blob.bin"]["status"], "added")

    def test_a_working_diff_has_patches_untracked_included_binaries_left_out(self):
        self.change_the_work_tree()
        body = contract.assert_response(self, "vcs.diff", self.get("/oc/api/vcs/diff", mode="working"))
        diffs = {d["file"]: d for d in body["data"]}
        self.assertEqual(sorted(diffs), ["gone.txt", "keep.txt", "new.txt"])
        self.assertIn("-four", diffs["keep.txt"]["patch"])
        self.assertIn("+FOUR", diffs["keep.txt"]["patch"])
        self.assertTrue(diffs["keep.txt"]["patch"].startswith("diff --git"))
        self.assertIn("+a", diffs["new.txt"]["patch"])
        self.assertEqual(diffs["new.txt"]["status"], "added")
        # Context is theirs to choose.
        tight = self.get("/oc/api/vcs/diff", mode="working", context="0").json()["data"]
        patch = next(d["patch"] for d in tight if d["file"] == "keep.txt")
        context_line = NEWLINE + " three" + NEWLINE
        self.assertNotIn(context_line, patch)
        self.assertIn(context_line, diffs["keep.txt"]["patch"])

    def test_a_branch_is_measured_from_where_it_was_created(self):
        git(self.repo, "checkout", "-q", "-b", "feature")
        (self.repo / "feature.txt").write_bytes(b"new work\n")
        git(self.repo, "add", "feature.txt")
        git(self.repo, "commit", "-q", "-m", "feature")
        (self.repo / "keep.txt").write_bytes(b"uncommitted\n")
        info = self.get("/oc/api/vcs").json()["data"]
        self.assertEqual(info["branch"], {"current": "feature", "default": "main"})
        base = contract.assert_response(self, "vcs.base", self.get("/oc/api/vcs/base"))["data"]
        self.assertEqual((base["name"], base["source"]), ("main", "reflog"))
        branch = contract.assert_response(self, "vcs.diff", self.get("/oc/api/vcs/diff", mode="branch"))
        self.assertEqual(sorted(d["file"] for d in branch["data"]), ["feature.txt", "keep.txt"])
        committed = contract.assert_response(
            self, "vcs.diff", self.get("/oc/api/vcs/diff", mode="committed")
        )
        self.assertEqual([d["file"] for d in committed["data"]], ["feature.txt"])
        branches = contract.assert_response(
            self, "vcs.branch.list", self.get("/oc/api/vcs/branch", search="FEAT")
        )
        self.assertEqual(branches["data"], ["feature"])
        # Made from a branch that is not the default, with a start point named:
        # the reflog's answer, which the default could not have given.
        git(self.repo, "checkout", "-q", "--", "keep.txt")
        git(self.repo, "branch", "topic", "feature")
        git(self.repo, "checkout", "-q", "topic")
        base = self.get("/oc/api/vcs/base").json()["data"]
        self.assertEqual((base["name"], base["source"]), ("feature", "reflog"))

    def test_on_the_default_branch_there_is_no_base(self):
        body = contract.assert_response(self, "vcs.base", self.get("/oc/api/vcs/base"))
        self.assertIsNone(body["data"])

    def test_a_folder_that_is_not_a_repository_answers_empty(self):
        plain = self.root / "plain"
        plain.mkdir()
        self.create(location={"directory": str(plain)})
        where = {"location[directory]": str(plain)}
        info = contract.assert_response(self, "vcs.get", self.client.get("/oc/api/vcs", params=where))
        self.assertEqual(info["data"], {"branch": {}})
        diff = self.client.get("/oc/api/vcs/diff", params={**where, "mode": "working"})
        self.assertEqual(contract.assert_response(self, "vcs.diff", diff)["data"], [])
        status = contract.assert_response(self, "vcs.status", self.client.get("/oc/api/vcs/status", params=where))
        self.assertEqual(status["data"], [])

    def test_a_folder_that_is_no_project_and_a_bad_mode_are_refused(self):
        stranger = self.root / "stranger"
        stranger.mkdir()
        refused = self.client.get("/oc/api/vcs/diff", params={"location[directory]": str(stranger), "mode": "working"})
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(contract.errors(refused.json(), contract.component("InvalidRequestErrorEncoded")), [])
        bad = self.get("/oc/api/vcs/diff", mode="sideways")
        self.assertEqual(bad.status_code, 400)

    def test_a_tool_that_writes_files_tells_their_panel_to_re_read(self):
        thread_id = sessions.thread_id_of(self.sid)
        written = self.repo / "results.md"
        written.write_bytes(b"# results\n")
        events.append("turn.started", {"provider": "Local", "model": "m"}, thread_id=thread_id)
        events.append("tool.call", {"id": "c-1", "name": "write_the_results", "arguments": {}}, thread_id=thread_id)
        events.append(
            "tool.result",
            {"id": "c-1", "name": "write_the_results", "ok": True, "result": {"ok": True, "path": str(written)}},
            thread_id=thread_id,
        )
        # A tool that writes no files says nothing about the filesystem.
        events.append("tool.call", {"id": "c-2", "name": "list_context", "arguments": {}}, thread_id=thread_id)
        events.append(
            "tool.result", {"id": "c-2", "name": "list_context", "ok": True, "result": {"ok": True}}, thread_id=thread_id
        )
        stream = translate.translate(events.since(f"thread:{thread_id}", 0, limit=1000))
        changed = [e for e in stream if e["type"] == "filesystem.changed"]
        self.assertEqual(len(changed), 1, changed)
        self.assertEqual(changed[0]["data"], {"file": "results.md", "event": "add"})
        self.assertEqual(changed[0]["location"], {"directory": str(self.repo)})
        self.assertNotIn("durable", changed[0])
        self.assertEqual(contract.event_problems(changed[0]), [])


if __name__ == "__main__":
    unittest.main()
