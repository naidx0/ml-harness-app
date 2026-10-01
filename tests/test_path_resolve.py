"""H-path-e: a missing read path that plainly means one workspace file is read from it."""
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from app import db, events
from app.tools import REGISTRY
from app.tools.path_resolve import resolve_missing

import support


class ResolveMissing(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for rel in (
            "ml-principles-dataset/data/splits/eval.jsonl",
            "ml-principles-dataset/data/schema.json",
            "ml-principles-dataset/taxonomy.md",
            "ml-principles-dataset/README.md",
            "ml-principles-dataset/programs/README.md",
            "clean/by_answer/eval.jsonl",
            ".cache/only-here.json",
            "node_modules/pkg/only-here.txt",
        ):
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x", encoding="utf-8")
        (self.root / "ml-principles-dataset" / "corpus").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def at(self, rel):
        return str(self.root / rel)

    def test_a_dropped_prefix_resolves_by_suffix(self):
        out = resolve_missing("data/splits/eval.jsonl", self.root)
        self.assertEqual(out, {"status": "resolved", "to": self.at("ml-principles-dataset/data/splits/eval.jsonl"), "by": "suffix"})

    def test_a_wrong_folder_resolves_by_the_one_file_with_that_name(self):
        out = resolve_missing("data/splits/schema.json", self.root)
        self.assertEqual(out["status"], "resolved")
        self.assertEqual(out["by"], "name")
        self.assertEqual(Path(out["to"]), self.root / "ml-principles-dataset/data/schema.json")

    def test_a_bare_name_resolves(self):
        self.assertEqual(Path(resolve_missing("taxonomy.md", self.root)["to"]), self.root / "ml-principles-dataset/taxonomy.md")

    def test_an_absolute_path_inside_the_root_resolves(self):
        out = resolve_missing(str(self.root / "data" / "schema.json"), self.root)
        self.assertEqual(Path(out["to"]), self.root / "ml-principles-dataset/data/schema.json")

    def test_two_files_with_the_name_are_ambiguous_and_named(self):
        out = resolve_missing("data/splits/README.md", self.root)
        self.assertEqual(out["status"], "ambiguous")
        self.assertEqual(sorted(out["candidates"]), ["ml-principles-dataset/README.md", "ml-principles-dataset/programs/README.md"])

    def test_two_suffix_matches_are_ambiguous(self):
        self.assertEqual(resolve_missing("eval.jsonl", self.root)["status"], "ambiguous")

    def test_folders_and_tool_names_are_never_resolved(self):
        for request in ("corpus/", "data/splits", "read_the_standing_constraints", "", "./"):
            self.assertEqual(resolve_missing(request, self.root)["status"], "none", request)

    def test_outside_the_root_and_missing_everywhere_are_none(self):
        self.assertEqual(resolve_missing("../HARNESS.md", self.root)["status"], "none")
        self.assertEqual(resolve_missing("HARNESS.md", self.root)["status"], "none")

    def test_hidden_and_bookkeeping_folders_are_not_searched(self):
        self.assertEqual(resolve_missing("only-here.json", self.root)["status"], "none")
        self.assertEqual(resolve_missing("only-here.txt", self.root)["status"], "none")


class TheRegistryReadsTheOneFileMeant(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self) / "workspace"
        target = self.root / "ml-principles-dataset" / "data" / "splits" / "eval.jsonl"
        target.parent.mkdir(parents=True)
        target.write_text('{"q": 1}' + chr(10), encoding="utf-8")
        for rel in ("ml-principles-dataset/README.md", "ml-principles-dataset/programs/README.md"):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text("readme", encoding="utf-8")
        flag = unittest.mock.patch.dict("os.environ", {"MLH_PATH_RESOLVE": "1"})
        flag.start()
        self.addCleanup(flag.stop)
        project = db.create_project("path-e", str(self.root))
        self.thread_id = events.create_thread("path-e", project_id=project["id"])["id"]

    def test_a_dropped_prefix_is_read_and_reported(self):
        result = REGISTRY.call("read_context_file", {"path": "data/splits/eval.jsonl"}, thread_id=self.thread_id)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["path_resolved"]["path"]["by"], "suffix")
        self.assertTrue(result["path_resolved"]["path"]["from"].replace(chr(92), "/").endswith("workspace/data/splits/eval.jsonl"))

    def test_several_candidates_are_named_and_nothing_is_read(self):
        result = REGISTRY.call("read_context_file", {"path": "data/splits/README.md"}, thread_id=self.thread_id)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "not_found")
        self.assertEqual(len(result["path_resolved"]["path"]["candidates"]), 2)

    def test_a_tool_that_writes_is_never_redirected(self):
        spec = REGISTRY._tools["attach_context"]
        self.assertTrue(spec.writes)
        from app.tools import registry
        accepted = {"path": str(self.root / "data" / "splits" / "eval.jsonl")}
        self.assertEqual(registry._resolve_missing_reads(spec, accepted, self.thread_id), {})
        self.assertEqual(accepted["path"], str(self.root / "data" / "splits" / "eval.jsonl"))


    def test_the_flag_off_leaves_a_missing_path_refused(self):
        with unittest.mock.patch.dict("os.environ", {"MLH_PATH_RESOLVE": "0"}):
            result = REGISTRY.call("read_context_file", {"path": "data/splits/eval.jsonl"}, thread_id=self.thread_id)
        self.assertFalse(result["ok"])
        self.assertNotIn("path_resolved", result)


if __name__ == "__main__":
    unittest.main()
