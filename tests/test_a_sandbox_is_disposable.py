"""A delete that can escape its own directory is the worst defect this can have.

`docs/THE_PROPOSAL_LOOP.md` says an experiment that goes wrong is *deleted, not
untangled*. That promise is what makes a sandbox worth making, and it is also
what makes `app/tools/sandbox.py::destroy` the most dangerous function in this
product: it exists to remove a directory tree, and the difference between doing
that and doing something unforgivable is entirely in the guards.

So this file is written as attacks, not as coverage. Every test here tries to
make a delete reach outside the sandbox it names, and each one asserts a canary
outside is still there afterwards - the canary rather than the refusal, because
a refusal with the file already gone is a refusal that arrived late.

The junction tests assert the junction's OWN properties first. That is a
positive control: they are the reason the naive walk is wrong, and if a future
Python changes them the control fails loudly instead of the attack quietly
passing against an implementation that no longer needs the defence.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import jobspec  # noqa: E402
from app.tools import sandbox  # noqa: E402
from app.tools.registry import REGISTRY  # noqa: E402
from tests import support  # noqa: E402


def _link_a_directory(target: Path, link: Path) -> str:
    """Point `link` at `target`, however this machine will let us.

    A symlink where the account may make one, a junction otherwise. Returns
    which kind was made, so a test can say so when it fails.

    A machine where symlinks are permitted never reaches the junction branch,
    which is why `_junction` below exists as its own door: the junction is the
    harder case and it must not go untested on the machine where it works.
    """
    try:
        os.symlink(target, link, target_is_directory=True)
        return "symlink"
    except (OSError, NotImplementedError, AttributeError):
        pass
    return _junction(target, link)


def _junction(target: Path, link: Path) -> str:
    """A Windows directory junction, specifically, or a skip.

    Its own function because `_link_a_directory` prefers a symlink and would
    therefore never make one here - and the junction is the case the guard is
    really for: a symlink announces itself through `os.path.islink` and a
    junction does not. Junctions need no privilege, so this runs on an ordinary
    account where `os.symlink` would need developer mode.
    """
    if os.name != "nt":
        raise unittest.SkipTest("junctions are a Windows thing")
    import _winapi

    _winapi.CreateJunction(str(target), str(link))
    return "junction"


class ABoxOutsideTest(unittest.TestCase):
    """Shared setup: one sandbox, and a canary directory that is not in it."""

    def setUp(self):
        self.root = support.sandbox(self)
        self.outside = self.root / "not-a-sandbox"
        self.outside.mkdir()
        self.canary = self.outside / "canary.txt"
        self.canary.write_text("alive", encoding="utf-8")

    def a_sandbox(self, name="victim", **kwargs):
        made = sandbox.create(name, **kwargs)
        self.assertTrue(made["ok"], made)
        return Path(made["path"])

    def assertCanaryAlive(self, why=""):
        self.assertTrue(
            self.canary.is_file(),
            f"the canary outside the sandbox was destroyed. {why}",
        )
        self.assertEqual(self.canary.read_text(encoding="utf-8"), "alive")
        self.assertTrue(self.outside.is_dir())


class ADeleteCannotFollowALinkOutTest(ABoxOutsideTest):
    """The attack that needs no attacker: a link inside pointing outside."""

    def test_a_junction_inside_a_sandbox_is_not_followed(self):
        """The case the guard is really for, run as itself.

        `_link_a_directory` prefers a symlink and gets one on a machine with
        developer mode on, so without this the junction - the harder case -
        would never be exercised on the machine where it works.
        """
        directory = self.a_sandbox()
        link = directory / "work" / "my-data"
        _junction(self.outside, link)

        # THE POSITIVE CONTROL, and it is the whole reason this test is not
        # redundant with the symlink one. A junction is invisible to the two
        # checks anybody would reach for, so the obvious walk descends into it
        # and empties whatever it points at. Asserted rather than assumed: a
        # Python that changed these would make the attack stale, and a stale
        # attack passing quietly is worse than one that fails loudly.
        status = os.lstat(link)
        self.assertFalse(
            os.path.islink(link),
            "a junction used to be invisible to os.path.islink; if it is not "
            "any more, this attack is stale and the guard should be re-argued "
            "rather than trusted",
        )
        self.assertTrue(stat.S_ISDIR(status.st_mode))
        entry = next(e for e in os.scandir(link.parent) if e.name == link.name)
        self.assertTrue(entry.is_dir(follow_symlinks=False))
        self.assertFalse(entry.is_symlink())
        self.assertEqual(
            getattr(status, "st_reparse_tag", 0), stat.IO_REPARSE_TAG_MOUNT_POINT
        )
        self.assertTrue(
            sandbox._redirects_elsewhere(status),
            "a junction was not recognised as redirecting elsewhere, which is "
            "the whole basis of the delete guard",
        )

        result = sandbox.destroy("victim")

        self.assertTrue(result["deleted"], result)
        self.assertFalse(directory.exists())
        self.assertGreaterEqual(result["removed"]["links"], 1)
        self.assertCanaryAlive(
            "A junction inside the sandbox was followed and its target emptied."
        )

    def test_a_directory_symlink_inside_a_sandbox_is_not_followed(self):
        directory = self.a_sandbox()
        link = directory / "work" / "my-data"
        kind = _link_a_directory(self.outside, link)

        result = sandbox.destroy("victim")

        self.assertTrue(result["deleted"], result)
        self.assertGreaterEqual(result["removed"]["links"], 1)
        self.assertCanaryAlive(
            f"A {kind} inside the sandbox was followed and its target emptied."
        )

    def test_the_link_itself_is_gone_and_its_target_is_not(self):
        directory = self.a_sandbox()
        link = directory / "work" / "out"
        _link_a_directory(self.outside, link)

        sandbox.destroy("victim")

        self.assertFalse(link.exists(), "the link was left behind")
        self.assertCanaryAlive()

    def test_a_file_symlink_out_of_the_sandbox_is_not_followed(self):
        directory = self.a_sandbox()
        link = directory / "work" / "canary-link.txt"
        try:
            os.symlink(self.canary, link)
        except (OSError, NotImplementedError):
            self.skipTest("this machine does not make file symlinks")

        sandbox.destroy("victim")

        self.assertCanaryAlive("a file symlink was followed and its target unlinked.")


class ADeleteCannotBeSpelledAsAPathTest(ABoxOutsideTest):
    """Guard 1 and guard 2: a sandbox is named, never located."""

    def test_a_traversing_name_is_refused_and_nothing_moves(self):
        for attempt in (
            "..",
            "../..",
            r"..\..",
            "../not-a-sandbox",
            r"..\not-a-sandbox",
            "victim/../../not-a-sandbox",
            "/etc/passwd",
            "C:/Windows",
            str(self.outside),
            str(self.canary),
            "\x00victim",
        ):
            with self.subTest(name=attempt):
                with self.assertRaises(sandbox.SandboxRejected) as caught:
                    sandbox.destroy(attempt)
                self.assertCanaryAlive(f"delete_sandbox({attempt!r}) reached it.")
                # The refusal says what a name is, because the caller who got
                # here is exactly the caller who thought it was a path.
                self.assertTrue(
                    "name" in str(caught.exception).lower(),
                    str(caught.exception),
                )

    def test_the_tool_answers_a_traversing_name_rather_than_raising(self):
        """A model sending a path gets a sentence back, not a stack trace."""
        answered = REGISTRY.call(
            "delete_sandbox", {"name": "../not-a-sandbox"}, approved=True
        )
        self.assertFalse(answered["ok"])
        self.assertEqual(answered["error"], "sandbox_rejected")
        self.assertIn("path", answered["detail"])
        self.assertCanaryAlive()

    def test_a_name_that_is_shaped_on_the_way_in_is_not_shaped_on_the_way_out(self):
        """`make_sandbox` may tidy a name. Nothing that ACTS on one may.

        Shaping here would make `delete_sandbox("Victim Two")` remove
        `victim-two`, which is a delete the caller never spelled.
        """
        made = sandbox.create("Victim Two")
        self.assertEqual(made["name"], "victim-two")
        with self.assertRaises(sandbox.SandboxRejected):
            sandbox.destroy("Victim Two")
        self.assertTrue(Path(made["path"]).is_dir())


class ADeleteRemovesOnlyWhatThisHarnessMadeTest(ABoxOutsideTest):
    """Guard 3 and guard 4."""

    def test_a_directory_with_no_manifest_is_not_a_sandbox(self):
        stranger = sandbox.sandboxes_root()
        stranger.mkdir(parents=True, exist_ok=True)
        theirs = stranger / "someone-elses"
        theirs.mkdir()
        (theirs / "important.txt").write_text("mine", encoding="utf-8")

        with self.assertRaises(sandbox.SandboxRejected) as caught:
            sandbox.destroy("someone-elses")

        self.assertIn("no sandbox named", str(caught.exception))
        self.assertTrue((theirs / "important.txt").is_file())

    def test_a_manifest_naming_a_different_sandbox_is_refused(self):
        directory = self.a_sandbox()
        body = json.loads((directory / sandbox.MANIFEST).read_text(encoding="utf-8"))
        body["name"] = "somebody-else"
        (directory / sandbox.MANIFEST).write_text(json.dumps(body), encoding="utf-8")

        with self.assertRaises(sandbox.SandboxRejected):
            sandbox.destroy("victim")
        self.assertTrue(directory.is_dir())

    def test_a_link_standing_where_a_sandbox_should_be_is_refused(self):
        """Two guards answer this, and either one alone would be enough.

        Guard 2 usually gets there first: `sandbox_path` resolves the name, and
        `resolve()` folds a symlink to its target, so the target's parent is
        not the sandboxes root and the name refuses. Guard 3 is what answers a
        link `resolve()` does NOT fold. The assertion is therefore on the
        outcome - refused, canary alive - rather than on which sentence came
        back, because pinning the sentence would pin which guard fired.
        """
        root = sandbox.sandboxes_root()
        root.mkdir(parents=True, exist_ok=True)
        kind = _link_a_directory(self.outside, root / "impostor")

        with self.assertRaises(sandbox.SandboxRejected):
            sandbox.destroy("impostor")

        self.assertCanaryAlive(
            f"a {kind} standing in for a sandbox was deleted through."
        )
        self.assertTrue(
            sandbox._redirects_elsewhere(os.lstat(root / "impostor")),
            "guard 3 would not have recognised this link on its own",
        )


class ADeleteSaysWhatItRemovedTest(ABoxOutsideTest):
    """Disposable is a promise; a count is what makes it checkable."""

    def test_the_counts_are_of_what_was_really_there(self):
        directory = self.a_sandbox()
        (directory / "work" / "a.txt").write_text("aaa", encoding="utf-8")
        (directory / "work" / "deep").mkdir()
        (directory / "work" / "deep" / "b.txt").write_text("bb", encoding="utf-8")

        result = sandbox.destroy("victim")

        self.assertTrue(result["deleted"])
        # manifest + a.txt + b.txt at least; the sandbox also holds job files
        # for any run, and this one has had none.
        self.assertGreaterEqual(result["removed"]["files"], 3)
        self.assertGreaterEqual(result["removed"]["bytes"], 5)
        self.assertGreaterEqual(result["removed"]["directories"], 5)
        self.assertIn("counted while walking", result["removed_provenance"])

    def test_deleting_one_sandbox_leaves_the_others_alone(self):
        first = self.a_sandbox("keeper")
        second = self.a_sandbox("goner")

        sandbox.destroy("goner")

        self.assertFalse(second.exists())
        self.assertTrue(first.is_dir())
        self.assertEqual([row["name"] for row in sandbox.every()], ["keeper"])

    def test_a_deleted_sandbox_takes_its_record_with_it(self):
        """Why there is no table: the record cannot outlive the directory."""
        self.a_sandbox("temporary")
        self.assertEqual(len(sandbox.every()), 1)
        sandbox.destroy("temporary")
        self.assertEqual(sandbox.every(), [])
        with self.assertRaises(sandbox.SandboxRejected):
            sandbox.read_manifest("temporary")


class MakingOneCannotEscapeEitherTest(ABoxOutsideTest):
    """The same rule at the other end: a name is not a place to put something."""

    def test_a_traversing_name_cannot_make_a_directory_outside_the_root(self):
        for attempt in ("../evil", r"..\evil", "/tmp/evil", "C:/evil", "a/b"):
            with self.subTest(name=attempt):
                answered = REGISTRY.call("make_sandbox", {"name": attempt})
                self.assertFalse(answered["ok"], answered)
                self.assertIn("path", answered["detail"])

    def test_every_sandbox_made_lands_inside_the_root(self):
        root = sandbox.sandboxes_root().resolve()
        for name in ("one", "Two Words", "THREE"):
            made = sandbox.create(name)
            self.assertEqual(Path(made["path"]).resolve().parent, root)

    def test_a_sandbox_lives_under_this_database_s_own_artifact_root(self):
        """Reuse rather than a second identity scheme, asserted.

        `jobspec.runs_root_for` is what validates the instance identity that
        names the directory. A sandbox that keyed on something else would need
        its own answer to the collision `app/jobspec.py` already fixed.
        """
        made = sandbox.create("keyed")
        self.assertEqual(
            Path(made["path"]).parent.parent.resolve(),
            jobspec.runs_root_for().resolve(),
        )


if __name__ == "__main__":
    unittest.main()
