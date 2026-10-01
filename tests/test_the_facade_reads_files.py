"""Their file tree, previews, @-mentions and uploads, confined to the project.

Their interface reads files through `fs.list`, `fs.read` and `fs.find`
(`vendor/opencode/packages/app/src/workspaces/files/model.tsx`) and uploads an
attachment with `experimental.fs.write` into `server.info`'s `paths.tmp`
(`composer/attachments/destination.ts`). Every answer is validated against
their OpenAPI document; every refusal is one of their declared error bodies.

The confinement cases are the point: a path that climbs out with `..`, an
absolute path elsewhere, a location that is no project, and an upload aimed
anywhere but the temporary directory are each refused, and each is a case
that produces only that refusal.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from app.facade import files, sessions

import openapi_contract as contract
from test_the_facade_speaks_their_protocol import FacadeTestCase

HAVE_GIT = shutil.which("git") is not None


class FilesTestCase(FacadeTestCase):
    def setUp(self):
        super().setUp()
        self.project = self.root / "their-project"
        (self.project / "src" / "deep").mkdir(parents=True)
        # Bytes, not text: `write_text` on Windows writes CRLF, and the
        # preview test compares bytes.
        (self.project / "README.md").write_bytes(b"# hello\n")
        (self.project / "src" / "main.py").write_bytes(b"print('hi')\n")
        (self.project / "src" / "deep" / "model_config.json").write_text("{}", encoding="utf-8")
        (self.root / "outside.txt").write_text("not yours", encoding="utf-8")
        self.sid = self.create(location={"directory": str(self.project)})["id"]
        self.where = {"location[directory]": str(self.project)}

    def get(self, url, **params):
        return self.client.get(url, params={**self.where, **params})

    def refused(self, response, component="InvalidRequestErrorEncoded", status=400):
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(contract.errors(response.json(), contract.component(component)), [])
        return response.json()


class TheTreeListsTheProjectTest(FilesTestCase):
    def test_a_listing_is_relative_to_the_location_directories_first(self):
        body = contract.assert_response(self, "fs.list", self.get("/oc/api/fs/list"))
        self.assertEqual(
            body["data"],
            [{"path": "src", "type": "directory"}, {"path": "README.md", "type": "file"}],
        )
        inner = contract.assert_response(self, "fs.list", self.get("/oc/api/fs/list", path="src"))
        # Relative to the LOCATION, as their tree builds `${location}/${path}`.
        self.assertEqual(
            inner["data"],
            [{"path": "src/deep", "type": "directory"}, {"path": "src/main.py", "type": "file"}],
        )

    def test_climbing_out_is_refused_every_way(self):
        cases = {
            "dot-dot": {"path": ".."},
            "absolute elsewhere": {"path": str(self.root)},
        }
        for name, params in cases.items():
            with self.subTest(case=name):
                self.refused(self.get("/oc/api/fs/list", **params))
        stranger = self.root / "stranger"
        stranger.mkdir()
        response = self.client.get("/oc/api/fs/list", params={"location[directory]": str(stranger)})
        self.assertIn("not a project folder", self.refused(response)["message"])

    def test_a_symlink_out_of_the_project_is_outside_it(self):
        link = self.project / "escape"
        try:
            os.symlink(self.root, link, target_is_directory=True)
        except (OSError, NotImplementedError) as unavailable:
            self.skipTest(f"no symlinks here: {unavailable}")
        self.refused(self.get("/oc/api/fs/list", path="escape"))
        self.refused(self.get("/oc/api/fs/read/escape/outside.txt"))

    @unittest.skipUnless(HAVE_GIT, "git is not installed")
    def test_what_git_ignores_is_not_listed_or_found(self):
        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True)
        (self.project / ".gitignore").write_text("build/\n*.log\n", encoding="utf-8")
        (self.project / "build").mkdir()
        (self.project / "build" / "out.bin").write_bytes(b"x")
        (self.project / "run.log").write_text("noise", encoding="utf-8")
        listed = [e["path"] for e in contract.assert_response(self, "fs.list", self.get("/oc/api/fs/list"))["data"]]
        self.assertNotIn("build", listed)
        self.assertNotIn("run.log", listed)
        self.assertNotIn(".git", listed)
        self.assertIn(".gitignore", listed)
        found = contract.assert_response(self, "fs.find", self.get("/oc/api/fs/find", query="o"))
        paths = [e["path"] for e in found["data"]]
        self.assertFalse([p for p in paths if p.startswith("build") or p.endswith(".log")], paths)
        self.assertIn("src/deep/model_config.json", paths)


class APreviewReadsTheFileTest(FilesTestCase):
    def read(self, path):
        return self.get(f"/oc/api/fs/read/{path}")

    def test_a_text_file_is_its_bytes(self):
        response = self.read("src/main.py")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/octet-stream")
        self.assertEqual(response.content, b"print('hi')\n")
        # An absolute path inside the project, with its own folder as the
        # location, is how their viewer asks for a file it found elsewhere.
        absolute = self.client.get(
            "/oc/api/fs/read/main.py", params={"location[directory]": str(self.project / "src")}
        )
        self.assertEqual(absolute.content, b"print('hi')\n")

    def test_a_missing_file_is_their_not_found_and_outside_is_their_400(self):
        missing = self.refused(self.read("src/nowhere.py"), "FileNotFoundErrorEncoded", 404)
        self.assertEqual(missing["path"], "src/nowhere.py")
        # `..%2F` so the client does not collapse the dots before sending.
        self.refused(self.read("..%2Foutside.txt"))
        self.refused(self.read("src%2F..%2F..%2Foutside.txt"))

    def test_a_binary_is_sniffed_not_sent_and_an_image_is_sent_whole(self):
        blob = b"\x00\x01" * 50_000
        (self.project / "weights.bin").write_bytes(blob)
        (self.project / "shot.png").write_bytes(blob)
        self.assertEqual(self.read("weights.bin").content, blob[: files.SNIFF_BYTES])
        self.assertEqual(self.read("shot.png").content, blob)

    def test_a_file_over_the_bound_is_refused(self):
        with mock.patch.object(files, "MAX_READ_BYTES", 4):
            self.assertIn("previews stop", self.refused(self.read("README.md"))["message"])


class TheFinderFindsTest(FilesTestCase):
    def test_a_basename_match_comes_first_and_the_limit_holds(self):
        body = contract.assert_response(self, "fs.find", self.get("/oc/api/fs/find", query="main"))
        self.assertEqual(body["data"][0], {"path": "src/main.py", "type": "file"})
        dirs = contract.assert_response(
            self, "fs.find", self.get("/oc/api/fs/find", query="deep", type="directory")
        )
        self.assertEqual(dirs["data"], [{"path": "src/deep", "type": "directory"}])
        one = contract.assert_response(self, "fs.find", self.get("/oc/api/fs/find", query="", limit="1"))
        self.assertEqual(len(one["data"]), 1)
        self.refused(self.get("/oc/api/fs/find", query="x", limit="many"))


class AnUploadIsAnAttachmentTest(FilesTestCase):
    def test_server_info_names_a_temporary_directory_beside_the_database(self):
        body = contract.assert_response(self, "server.info", self.client.get("/oc/api/info"))
        tmp = Path(body["paths"]["tmp"])
        self.assertTrue(tmp.is_dir())
        self.assertIn(self.root, tmp.parents)

    def upload(self, path, data=b"id,text\n1,hello\n"):
        return self.client.post(
            "/oc/api/experimental/fs/write",
            params={**self.where, "path": path},
            content=data,
            headers={"content-type": "application/octet-stream"},
        )

    def test_an_upload_lands_in_tmp_and_the_prompt_attaches_it(self):
        from app.tools import context

        tmp = self.client.get("/oc/api/info").json()["paths"]["tmp"]
        response = self.upload(f"{tmp}/uploads/abc123/tickets.csv")
        body = contract.assert_response(self, "experimental.fs.write", response)
        written = Path(body["data"]["path"])
        self.assertEqual(written.read_bytes(), b"id,text\n1,hello\n")
        self.assertEqual(written.name, "tickets.csv")

        prompt = self.client.post(
            f"/oc/api/session/{self.sid}/prompt",
            json={
                "text": "count these",
                "metadata": {"attachments": [{"name": "tickets.csv", "mime": "text/csv", "path": str(written)}]},
                # The same file named twice is attached once.
                "files": [{"uri": written.as_uri(), "name": "tickets.csv"}],
            },
        )
        contract.assert_response(self, "session.prompt", prompt)
        thread_id = self.settle(self.sid)
        context.ensure_contexts_table()
        paths = [Path(row["path"]) for row in context.list_contexts(thread_id)]
        self.assertEqual(paths.count(written), 1, paths)

    def test_an_upload_anywhere_but_tmp_is_refused_and_writes_nothing(self):
        cases = {
            "into the project": str(self.project / "planted.txt"),
            "relative, so into the project": "planted.txt",
            "climbing out of tmp": f"{files.tmp_dir()}/../planted.txt",
        }
        for name, path in cases.items():
            with self.subTest(case=name):
                self.refused(self.upload(path))
        self.assertFalse((self.project / "planted.txt").exists())
        self.assertFalse((files.tmp_dir().parent / "planted.txt").exists())


class TheProjectFolderIsTheRootTest(FilesTestCase):
    def test_a_folderless_project_is_confined_to_its_workspace(self):
        workspace = Path(self.client.get("/oc/api/location").json()["directory"])
        (workspace / "notes.txt").write_text("mine", encoding="utf-8")
        listed = contract.assert_response(self, "fs.list", self.client.get("/oc/api/fs/list"))
        self.assertIn({"path": "notes.txt", "type": "file"}, listed["data"])
        self.assertEqual(Path(sessions.directory_of(__import__("app.db").db.default_project())), workspace)


if __name__ == "__main__":
    unittest.main()
