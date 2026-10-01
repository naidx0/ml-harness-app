"""The vendored copy cannot change without the change being recorded.

## What was wrong, measured rather than feared

`packages/four_asserts` is a **copy** - no submodule, no subtree, no nested
`.git`, plain files whose `pyproject.toml` names another repository as their
source. Cloning that repository and diffing it against this tree at `18fc9dc`:
**11 files identical**, **README.md 84 lines apart**, and **`tools/run_readme.py`
absent from the copy entirely**.

The code agreed. The documentation and the tooling did not, and **nothing
compared them.**

**AND THE DRIFT RAN OPPOSITE TO THE RISK EVERYBODY NAMED.** The worry was that
editing the copy would diverge from the package. What had happened is that the
package moved AHEAD and the copy never followed - upstream had found two of its
four README usage lines did not work, **found by a person on a fresh machine
typing them in**, and had built a runner that executes every fenced block
verbatim on every push. The copy still documented three variables that do not
exist.

## Why a record and not a submodule

**Not a submodule**: we carry deliberate local modifications, so a pinned
upstream would leave our improvements as detached commits in a nested repository
and the gate would test code the harness does not import. **Not a dependency**:
it loses the 62 package tests the gate gained and our changes with them, and the
package is not on PyPI. **A subtree** is the right long-term shape and is history
surgery to adopt - and, by itself, *a subtree nobody pulls is today's situation
with extra ceremony*.

What stops silent drift is a comparison, and it splits on the network:

* **here, in the gate, with no network** - the tree matches the record, so our
  own edits cannot be quiet
* **`--upstream`, run by a person** - the record matches the published package.
  Deliberately NOT a gate test: a gate that fails when GitHub is slow is a gate
  people learn to ignore, and then it is not a gate at all.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import support

vendored = support.import_file(
    "the_vendored_copy", support.REPO_ROOT / "scripts" / "the_vendored_copy.py"
)


class TheCopyMatchesItsRecordTest(unittest.TestCase):
    """THE CASE, and it needs no network."""

    def test_nothing_has_changed_without_being_recorded(self):
        said = vendored.why_the_tree_does_not_match_the_record()
        self.assertEqual(
            said, [],
            "the vendored copy differs from its record - if the change is "
            "intended, run `python scripts/the_vendored_copy.py --record <sha>` "
            "and say why in the commit",
        )

    def test_the_record_exists_and_names_its_source(self):
        record = vendored.the_record()
        self.assertTrue(record, "there is no vendor record at all")
        self.assertIn("github.com", record.get("source", ""))
        self.assertRegex(record.get("upstream", ""), r"^[0-9a-f]{40}$")

    def test_the_record_covers_every_vendored_file(self):
        """A record of half the files is a check over half the files, and it
        would pass while the other half moved."""
        recorded = set(vendored.the_record().get("files") or {})
        here = set(vendored.ours())
        self.assertEqual(recorded, here)
        self.assertGreater(len(here), 10, "the scan found almost nothing to scan")


class ItCanActuallyFailTest(unittest.TestCase):
    """A gate you cannot make fail is not a gate."""

    def test_a_changed_file_is_caught(self):
        record = dict(vendored.the_record())
        files = dict(record.get("files") or {})
        name = next(iter(sorted(files)))
        files[name] = "0" * 64
        record["files"] = files
        real = vendored.the_record
        try:
            vendored.the_record = lambda: record
            said = vendored.why_the_tree_does_not_match_the_record()
        finally:
            vendored.the_record = real
        self.assertTrue(any(name in line and "changed" in line for line in said), said)

    def test_a_new_unrecorded_file_is_caught(self):
        record = dict(vendored.the_record())
        files = dict(record.get("files") or {})
        files.pop(next(iter(sorted(files))))
        record["files"] = files
        real = vendored.the_record
        try:
            vendored.the_record = lambda: record
            said = vendored.why_the_tree_does_not_match_the_record()
        finally:
            vendored.the_record = real
        self.assertTrue(any("without being recorded" in line for line in said), said)

    def test_a_missing_record_is_a_failure_and_not_a_pass(self):
        """The failure mode of every check that reads a file: absent must not
        read as clean. This repository has met that one twice."""
        real = vendored.the_record
        try:
            vendored.the_record = dict
            said = vendored.why_the_tree_does_not_match_the_record()
        finally:
            vendored.the_record = real
        self.assertTrue(said, "no record at all was reported as no drift")


class TheDeliberateDivergencesAreExplainedTest(unittest.TestCase):
    """A recorded fork is only useful if it says what was forked and why."""

    def test_every_diverged_file_carries_a_reason(self):
        for name, why in (vendored.the_record().get("diverged") or {}).items():
            with self.subTest(name=name):
                self.assertGreater(
                    len(why), 80,
                    f"{name} is recorded as diverged with no usable reason",
                )

    def test_the_diverged_files_are_files_we_actually_have(self):
        here = set(vendored.ours())
        for name in (vendored.the_record().get("diverged") or {}):
            with self.subTest(name=name):
                self.assertIn(name, here, "a divergence is recorded for a file that is gone")

    def test_the_record_is_readable_json_sorted_for_diffing(self):
        raw = (support.REPO_ROOT / "packages" / "four_asserts" / "VENDOR.json").read_text(
            encoding="utf-8"
        )
        self.assertEqual(json.loads(raw), vendored.the_record())
        self.assertIn('"files"', raw)


class TheNetworkHalfIsNotInTheGateTest(unittest.TestCase):
    """Deliberate, and worth asserting so nobody helpfully adds it."""

    def test_no_test_here_calls_the_network_function(self):
        """PARSED, NOT GREPPED, AND THE FIRST VERSION GREPPED.

        It asserted the string `--upstream` did not appear below the docstring.
        It does - in a help message, and in the assertion looking for it. **The
        check failed on its own text**, which is the ninth time today a
        substring stood in for a structure in this repository.

        The real property is that nothing here CALLS `upstream_now`, the one
        function that reaches the network. Stubbing it is an assignment and is
        fine; calling it is not. That is a question about syntax, so `ast`
        answers it.
        """
        import ast

        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        called = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "upstream_now"
        ]
        self.assertEqual(
            [ast.unparse(c) for c in called], [],
            "a gate test calls upstream_now, which clones a repository - a gate "
            "that fails when GitHub is slow is a gate people learn to ignore",
        )

    def test_the_stub_really_is_a_stub_and_not_a_call(self):
        """The counterpart: the one test that exercises the comparison must
        replace the network function, not invoke it. Without this, the check
        above passes on a file that never touched the comparison at all."""
        import ast

        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        stubbed = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Attribute) and t.attr == "upstream_now"
                    for t in node.targets)
        ]
        self.assertTrue(stubbed, "nothing stubs upstream_now, so nothing exercises the comparison")

    def test_the_comparison_says_unknown_when_it_cannot_reach_upstream(self):
        """UNREACHABLE IS NOT UNCHANGED. Reporting no drift because the network
        failed is the same error as a suite reporting OK over tests that never
        ran."""
        real = vendored.upstream_now
        try:
            vendored.upstream_now = lambda url: None
            import io
            from contextlib import redirect_stdout

            out = io.StringIO()
            with redirect_stdout(out):
                code = vendored.compare_with_upstream()
            self.assertEqual(code, 2, "an unreachable upstream did not return its own code")
            self.assertIn("UNKNOWN", out.getvalue())
        finally:
            vendored.upstream_now = real


if __name__ == "__main__":
    unittest.main()
