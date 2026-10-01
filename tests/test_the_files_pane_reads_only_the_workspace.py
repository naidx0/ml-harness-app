"""The Files pane's routes read and write only inside the project's folder.

The owner's direction, 2026-08-31: "If we ask people to pull up a file, we can
actually open it on the sidebar somewhere... a markdown file or a JSON file,
and they can edit it as well." Three routes serve that pane, and this file is
their wall:

  GET  /api/projects/{id}/files   the folder, relative paths, capped and dated
  GET  /api/projects/{id}/file    one file's text plus the stamp an edit echoes
  PUT  /api/projects/{id}/file    an edit to an EXISTING file, stale-guarded

Every path is resolved inside `root_path` and verified after resolution, so
`..`, absolute paths and drive letters cannot reach a byte outside the folder
the person attached. A stale edit is a 409, never a silent clobber. A project
with no folder is a 400 that names the fix.
"""

import unittest
from pathlib import Path

from app import db, main
import support


class TheFilesPaneReadsOnlyTheWorkspaceTest(unittest.TestCase):
    def setUp(self):
        sandbox = support.sandbox(self)
        self.client = support.api_client(main.app)
        self.root = sandbox / "workspace"
        self.root.mkdir()
        (self.root / "notes.md").write_text("# hello\n", encoding="utf-8")
        (self.root / "harness-reports").mkdir()
        (self.root / "harness-reports" / "thread-1-journey.json").write_text(
            "{}\n", encoding="utf-8"
        )
        self.pid = db.create_project("files-wall", str(self.root))["id"]

    def test_the_listing_is_relative_dated_and_honest_about_its_cap(self):
        answer = self.client.get(f"/api/projects/{self.pid}/files").json()
        paths = [row["path"] for row in answer["files"]]
        self.assertIn("notes.md", paths)
        self.assertIn("harness-reports/thread-1-journey.json", paths)
        self.assertEqual(answer["left_unlisted"], 0)
        self.assertIn("read_at", answer)
        for row in answer["files"]:
            self.assertFalse(Path(row["path"]).is_absolute())

    def test_a_file_reads_back_with_the_stamp_an_edit_must_echo(self):
        answer = self.client.get(
            f"/api/projects/{self.pid}/file", params={"path": "notes.md"}
        ).json()
        self.assertEqual(answer["content"], "# hello\n")
        self.assertIn("modified", answer)

    def test_an_edit_lands_and_a_stale_edit_is_refused(self):
        read = self.client.get(
            f"/api/projects/{self.pid}/file", params={"path": "notes.md"}
        ).json()
        wrote = self.client.put(
            f"/api/projects/{self.pid}/file",
            json={
                "path": "notes.md",
                "content": "# hello\nedited\n",
                "expect_modified": read["modified"],
            },
        )
        self.assertEqual(wrote.status_code, 200)
        self.assertEqual(
            (self.root / "notes.md").read_text(encoding="utf-8"),
            "# hello\nedited\n",
        )
        # The same stamp again is now stale: the write above moved the file on.
        stale = self.client.put(
            f"/api/projects/{self.pid}/file",
            json={
                "path": "notes.md",
                "content": "clobber",
                "expect_modified": read["modified"],
            },
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(
            (self.root / "notes.md").read_text(encoding="utf-8"),
            "# hello\nedited\n",
            "a stale edit must never silently clobber the newer copy",
        )

    def test_traversal_and_absolute_paths_are_refused_after_resolution(self):
        for rel in ("../somewhere.txt", "harness-reports/../../escape.txt"):
            with self.subTest(path=rel):
                answer = self.client.get(
                    f"/api/projects/{self.pid}/file", params={"path": rel}
                )
                self.assertEqual(answer.status_code, 400)
        absolute = self.client.get(
            f"/api/projects/{self.pid}/file",
            params={"path": str(self.root / "notes.md")},
        )
        self.assertEqual(absolute.status_code, 400)

    def test_the_pane_edits_files_it_can_see_and_creates_nothing(self):
        answer = self.client.put(
            f"/api/projects/{self.pid}/file",
            json={"path": "invented.md", "content": "x"},
        )
        self.assertEqual(answer.status_code, 404)
        self.assertFalse((self.root / "invented.md").exists())

    def test_a_project_without_a_folder_names_the_fix(self):
        bare = db.create_project("files-wall-bare")["id"]
        answer = self.client.get(f"/api/projects/{bare}/files")
        self.assertEqual(answer.status_code, 400)
        self.assertIn("no folder attached", str(answer.json()["detail"]))

    def test_a_crlf_file_keeps_its_line_endings_through_an_edit(self):
        target = self.root / "windows.md"
        target.write_bytes(b"# one\r\ntwo\r\n")
        read = self.client.get(
            f"/api/projects/{self.pid}/file", params={"path": "windows.md"}
        ).json()
        wrote = self.client.put(
            f"/api/projects/{self.pid}/file",
            json={
                "path": "windows.md",
                "content": "# one\ntwo\nthree\n",
                "expect_modified": read["modified"],
            },
        )
        self.assertEqual(wrote.status_code, 200)
        self.assertEqual(
            target.read_bytes(),
            b"# one\r\ntwo\r\nthree\r\n",
            "a save must not rewrite every untouched line's ending",
        )

    def test_a_nul_byte_in_the_path_is_a_refusal_not_a_crash(self):
        answer = self.client.get(
            f"/api/projects/{self.pid}/file", params={"path": "notes\x00.md"}
        )
        self.assertEqual(answer.status_code, 400)

    def test_a_junction_pointing_outside_the_root_is_not_listed(self):
        try:
            import _winapi
        except ImportError:  # pragma: no cover - not Windows
            self.skipTest("junctions are a Windows construct")
        outside = Path(self.root).parent / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("not yours\n", encoding="utf-8")
        _winapi.CreateJunction(str(outside), str(self.root / "escape"))
        answer = self.client.get(f"/api/projects/{self.pid}/files").json()
        paths = [row["path"] for row in answer["files"]]
        self.assertNotIn("escape/secret.txt", paths)
        self.assertGreaterEqual(answer["skipped_outside_root"], 1)

    def test_a_relative_root_is_refused_on_both_doors(self):
        """A relative folder would follow the engine's cwd around, binding the
        pane, report/save and path rehoming to wherever it happens to run."""
        for body, path in (
            ({"root_path": "data"}, f"/api/projects/{self.pid}/root"),
            ({"name": "rel", "root_path": "."}, "/api/projects"),
        ):
            with self.subTest(path=path):
                answer = self.client.post(path, json=body)
                self.assertEqual(answer.status_code, 400)
                self.assertIn("relative", str(answer.json()["detail"]))

    def test_a_binary_file_is_named_as_one_rather_than_mangled(self):
        (self.root / "blob.bin").write_bytes(b"\xff\xfe\x00\x01")
        answer = self.client.get(
            f"/api/projects/{self.pid}/file", params={"path": "blob.bin"}
        )
        self.assertEqual(answer.status_code, 400)
        self.assertIn("not UTF-8", str(answer.json()["detail"]))


if __name__ == "__main__":
    unittest.main()
