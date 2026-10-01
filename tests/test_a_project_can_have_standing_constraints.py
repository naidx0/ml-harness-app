"""The things that are true for every run here, read instead of asked again.

## The column this makes live

`projects.harness_md_path` has existed since migration v003 and was read by
NOTHING - no Python, no TypeScript - and there was no `HARNESS.md` anywhere in
the tree. `projects.root_path` was the same shape: accepted at project creation,
stored, and never once opened. So a "project" was a folder in a sidebar, and
`docs/PRODUCT_SPEC.md` 4.3 described a file the product did not read:

    At the project root the harness maintains a plain markdown file called
    `HARNESS.md`. It records the things that are true for every run in this
    project and should never be asked twice: this data may not leave the
    machine; no run may exceed six hours; the target device is a Jetson with
    8 GB… Every run inherits it.

## What is built here, and what is deliberately not

The READ half. A project's standing constraints can be found and read, and the
three states a person can actually be in are each answered honestly rather than
collapsed into one error.

The WRITE half is not built and is not a leftover. The spec says the harness
writes to `HARNESS.md` when the person establishes a durable constraint in
conversation "and says so when it does" - and deciding that a sentence in a
conversation is DURABLE is a judgement, not a read. It belongs in its own step
with its own argument.

## Nothing in it is a measurement, and the tool says so

`measures=()`, permanently. What this file holds is prose somebody wrote about
their own project. "We deploy through Ollama" is a sentence, not a measurement,
and most of what belongs here is not a declared fact at all. A tool that stamped
from it would be laundering a document into the ledger - which is the one thing
every wall in this repository is about.
"""

import tempfile
import unittest
from pathlib import Path

from app import db
from app import events
from app.tools import REGISTRY
import support


TOOL = "read_the_standing_constraints"

A_REAL_ONE = """# Standing constraints

- This data may not leave the machine.
- No run may exceed six hours.
- The eval set is evals/tickets_v2.jsonl and it is the source of truth.
"""


class AProjectCanHaveStandingConstraintsTest(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)
        self.root = Path(tempfile.mkdtemp())
        self.project = db.create_project("tickets", str(self.root))
        self.thread = int(
            events.create_thread("route tickets", self.project["id"])["id"]
        )

    def _read(self, thread=None):
        return REGISTRY.call(
            TOOL, {}, actor="user", thread_id=thread if thread is not None else self.thread
        )

    def test_it_stamps_nothing_and_never_could(self):
        """The declaration that keeps a document out of the ledger."""
        spec = REGISTRY.get(TOOL)
        self.assertIsNotNone(spec)
        self.assertEqual(spec.measures, ())
        self.assertEqual(spec.provides, ("context.project.constraints",))

    def test_a_project_with_no_file_yet_is_not_an_error(self):
        """THE STATE ALMOST EVERY PROJECT IS IN, and collapsing it into a
        failure would teach the model to stop looking.

        "Nothing has been established as always-true here yet" is a real and
        common answer. It is `ok: True` with `found: False`, so a caller can
        tell it apart from a root that does not exist.
        """
        result = self._read()
        self.assertTrue(result.get("ok"), result)
        self.assertFalse(result["found"])
        self.assertEqual(result["constraints"], "")
        self.assertIn("HARNESS.md", result["looked_at"])

    def test_a_project_with_one_has_it_read_off_disk(self):
        (self.root / "HARNESS.md").write_text(A_REAL_ONE, encoding="utf-8")

        result = self._read()
        self.assertTrue(result.get("ok"), result)
        self.assertTrue(result["found"])
        self.assertIn("may not leave the machine", result["constraints"])
        self.assertEqual(result["lines"], 4)

    def test_it_is_read_off_disk_every_time_rather_than_cached(self):
        """The spec's own reason: it is a file so it can be edited without the
        app running. A copy in SQLite would be a second answer to a question the
        file already answers, and the person edits the file.
        """
        (self.root / "HARNESS.md").write_text(A_REAL_ONE, encoding="utf-8")
        self.assertIn("six hours", self._read()["constraints"])

        (self.root / "HARNESS.md").write_text(
            "- The target device is a Jetson with 8 GB.\n", encoding="utf-8"
        )
        second = self._read()
        self.assertIn("Jetson", second["constraints"])
        self.assertNotIn("six hours", second["constraints"])

    def test_the_reply_says_that_none_of_it_was_checked(self):
        """A verdict with no provenance beside it is the defect this product
        exists to refuse, and a document is the easiest place to forget that."""
        (self.root / "HARNESS.md").write_text(A_REAL_ONE, encoding="utf-8")
        result = self._read()
        self.assertIn("nothing_here_is_a_measurement", result)
        self.assertIn("stamps no facts", result["nothing_here_is_a_measurement"])

    def test_a_project_with_no_root_is_refused_and_told_what_would_fix_it(self):
        rootless = db.create_project("rootless")
        thread = int(events.create_thread("x", rootless["id"])["id"])

        result = self._read(thread=thread)
        self.assertFalse(result.get("ok"))
        self.assertEqual(result["error"], "no_root_path")
        self.assertIn("what_would_fix_it", result)

    def test_a_root_that_is_not_a_directory_is_said_so_plainly(self):
        """Distinct from "no file yet", because the remedies are different: one
        is somebody typing a path that was never a place."""
        elsewhere = db.create_project("gone", str(self.root / "not-here"))
        thread = int(events.create_thread("y", elsewhere["id"])["id"])

        result = self._read(thread=thread)
        self.assertFalse(result.get("ok"))
        self.assertEqual(result["error"], "root_is_not_a_directory")

    def test_the_scaffold_writes_only_what_was_measured(self):
        """PRODUCT_SPEC 4.3's "`/init` equivalent", and it decides nothing.

        Every line it writes is a fact already in the ledger with its origin
        beside it. This project's machine has been inspected, so the four
        machine facts are carried over - and each is tagged, because a number in
        a file outlives the conversation that produced it.
        """
        if not support.a_gpu_was_measured():
            # The scaffold carries every machine fact that WAS measured and
            # lists the rest in `left_blank_because_unmeasured` - which is the
            # behaviour under test. On a machine with no readable card that
            # list is correctly non-empty, so the assertion below is about
            # this machine rather than about the scaffold.
            self.skipTest(support.NO_GPU_HERE)
        REGISTRY.call("inspect_hardware", {}, actor="user", thread_id=self.thread)

        result = REGISTRY.call(
            "scaffold_the_standing_constraints",
            {},
            actor="user",
            thread_id=self.thread,
            approved=True,
        )
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result["left_blank_because_unmeasured"], [])

        written = (self.root / "HARNESS.md").read_text(encoding="utf-8")
        for fact in ("accelerator", "vram_gb", "ram_gb", "disk_free_gb"):
            with self.subTest(fact=fact):
                self.assertIn(fact, written)
        self.assertIn("MEASURED", written)

    def test_what_was_never_measured_is_left_blank_and_named(self):
        """An empty scaffold is a correct outcome, not a failure.

        A machine nobody has inspected has no VRAM figure, and inventing one is
        the defect invariant 5 forbids. The file says which are missing so the
        person can see what to do about it.
        """
        result = REGISTRY.call(
            "scaffold_the_standing_constraints",
            {},
            actor="user",
            thread_id=self.thread,
            approved=True,
        )
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result["facts_carried_over"], [])
        self.assertEqual(
            sorted(result["left_blank_because_unmeasured"]),
            ["accelerator", "disk_free_gb", "ram_gb", "vram_gb"],
        )
        self.assertIn("inspect_hardware", (self.root / "HARNESS.md").read_text(encoding="utf-8"))

    def test_it_will_not_overwrite_a_file_the_person_owns(self):
        """The spec's whole argument for a file is that a human can edit it
        without the app running. A tool that could silently replace one would
        take that back."""
        (self.root / "HARNESS.md").write_text("- mine" + chr(10), encoding="utf-8")

        result = REGISTRY.call(
            "scaffold_the_standing_constraints",
            {},
            actor="user",
            thread_id=self.thread,
            approved=True,
        )
        self.assertFalse(result.get("ok"))
        self.assertEqual(result["error"], "already_exists")
        self.assertEqual(
            (self.root / "HARNESS.md").read_text(encoding="utf-8"), "- mine" + chr(10)
        )

    def test_the_scaffold_stamps_nothing_either(self):
        """It writes a document OUT of facts. The direction that would need
        walls is reading a document IN, and neither tool does that."""
        self.assertEqual(REGISTRY.get("scaffold_the_standing_constraints").measures, ())

    def _record(self, text):
        return REGISTRY.call(
            "record_a_standing_constraint",
            {"constraint": text},
            actor="user",
            thread_id=self.thread,
            approved=True,
        )

    def test_recording_needs_a_file_and_names_what_makes_one(self):
        """A refusal that names nothing is a wall with no door."""
        result = self._record("This data may not leave the machine.")
        self.assertFalse(result.get("ok"))
        self.assertEqual(result["error"], "no_constraints_file")
        self.assertIn("scaffold_the_standing_constraints", result["detail"])

    def test_a_constraint_is_recorded_in_the_person_s_own_words(self):
        """VERBATIM IS A RULE, NOT A CONVENIENCE.

        "No run may exceed six hours" and "keep runs short" are not the same
        instruction, and this file is read back by somebody who was not in the
        conversation. So the words go in unchanged and the reply quotes what was
        written, so a wrong one can be seen at once.
        """
        (self.root / "HARNESS.md").write_text(A_REAL_ONE, encoding="utf-8")
        said = "The target device is a Jetson with 8 GB."

        result = self._record(said)
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result["constraint"], said)
        self.assertIn(said, result["said_so"])
        self.assertIn(said, (self.root / "HARNESS.md").read_text(encoding="utf-8"))

    def test_the_same_line_twice_is_recorded_once(self):
        """Somebody repeating themselves is not two rules."""
        (self.root / "HARNESS.md").write_text(A_REAL_ONE, encoding="utf-8")
        # NOT one of A_REAL_ONE's own lines. The first version of this test used
        # "No run may exceed six hours", which that fixture already contains -
        # so the duplicate check fired on the FIRST call and was right to. The
        # tool matches the whole file, not just what it wrote itself.
        said = "We deploy through Ollama."

        self.assertFalse(self._record(said)["already_recorded"])
        second = self._record(said)
        self.assertTrue(second["already_recorded"])
        self.assertIsNone(second["wrote"])

        body = (self.root / "HARNESS.md").read_text(encoding="utf-8")
        self.assertEqual(body.count("- " + said), 1)

    def test_it_appends_and_never_rewrites_what_is_already_there(self):
        """The spec's argument for a file is that a person can edit it. A tool
        that rewrote their lines would take that back."""
        (self.root / "HARNESS.md").write_text(A_REAL_ONE, encoding="utf-8")
        self._record("We deploy through Ollama.")

        body = (self.root / "HARNESS.md").read_text(encoding="utf-8")
        for original in A_REAL_ONE.splitlines():
            if original.strip():
                with self.subTest(line=original):
                    self.assertIn(original, body)

    def test_an_empty_constraint_is_refused(self):
        (self.root / "HARNESS.md").write_text(A_REAL_ONE, encoding="utf-8")
        result = self._record("   ")
        self.assertFalse(result.get("ok"))
        self.assertEqual(result["error"], "nothing_to_record")

    def test_recording_stamps_nothing_and_says_nothing_was_checked(self):
        """A constraint is an instruction, not a measurement. `state_facts` is
        the door for anything that IS a declared fact."""
        (self.root / "HARNESS.md").write_text(A_REAL_ONE, encoding="utf-8")
        self.assertEqual(REGISTRY.get("record_a_standing_constraint").measures, ())

        result = self._record("We deploy through Ollama.")
        self.assertIn("nothing_here_was_checked", result)

    def test_the_three_tools_are_read_scaffold_and_record(self):
        """The workspace triad, and the judgement each one does NOT make.

        Reading decides nothing. Scaffolding decides nothing - every line is a
        fact already measured. Recording decides nothing either: whether
        something is DURABLE is the person's call, and this writes what they
        said. What is still not built is DETECTING that a sentence in
        conversation was a standing constraint, and that one is a judgement.
        """
        for name in (
            "read_the_standing_constraints",
            "scaffold_the_standing_constraints",
            "record_a_standing_constraint",
        ):
            with self.subTest(tool=name):
                spec = REGISTRY.get(name)
                self.assertIsNotNone(spec)
                self.assertEqual(spec.measures, ())
                self.assertEqual(spec.provides, ("context.project.constraints",))

    def test_the_filename_is_written_down_once(self):
        """`HARNESS.md` is named in PRODUCT_SPEC 4.3 and in exactly one place in
        the code, so a project that has one and a reader looking for one cannot
        disagree about the spelling."""
        from app.tools import context

        self.assertEqual(context.STANDING_CONSTRAINTS, "HARNESS.md")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
