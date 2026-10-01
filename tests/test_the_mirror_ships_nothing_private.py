"""What a public mirror would ship, decided here rather than by running it.

`scripts/release/policy.py` exists apart from `mirror.py` for one reason, and
this file is the other half of it: the highest-consequence failure in the whole
release path is `decide()` quietly starting to say *keep* for something under
`docs/`. That publishes a private note permanently and looks exactly like a
successful release. A rule that important must be reachable without running the
tool.

DENY BY DEFAULT, AND THE ASYMMETRY IS THE ARGUMENT. An exclusion list only
protects you from the private files you thought of. This tree's `docs/` grows
several files on an ordinary night - judge runs, overnight reports, walk
records - and a doc tree that grew an owner plan tomorrow would ship it by
default, silently and permanently. A public doc missing for one release is
fixable in a minute. The two mistakes are not the same size, so the default is
not in the middle.

THE MIRROR IS A DRY RUN AND HAS NO WAY TO PUSH. There is no public mirror of
this repository and nobody has asked for one; the flag that would create it is
a decision for whoever owns the repository, not a convenience in a script.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "release_policy", REPO / "scripts" / "release" / "policy.py"
)
policy = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(policy)


class TheMirrorShipsNothingPrivateTest(unittest.TestCase):
    def test_a_doc_nobody_listed_does_not_ship(self):
        """THE ONE THAT MATTERS. A file added under docs/ tomorrow is private
        until somebody decides otherwise, and this is what makes that true."""
        keep, why = policy.decide("docs/an-owner-plan-written-next-week.md")
        self.assertFalse(keep)
        self.assertEqual(why, "docs deny-by-default")

    def test_the_directories_that_never_ship(self):
        for path, expect in (
            ("runs/abc123/sandboxes/practical-ml/adapter/README.md", "excluded tree runs/"),
            (".claude/worktrees/anything/AGENTS.md", "excluded tree .claude/"),
            ("lab/handoff.md", "excluded tree lab/"),
            ("card_owner/the_lock.py", "excluded tree card_owner/"),
            ("docs/judge_runs/some-private-run.md", "docs deny-by-default"),
            ("docs/overnight/2026-09-02-overnight.md", "docs deny-by-default"),
        ):
            with self.subTest(path):
                keep, why = policy.decide(path)
                self.assertFalse(keep, f"{path} would ship")
                self.assertEqual(why, expect)

    def test_the_recipes_ship(self):
        """Changed 2026-10-01: recipes/ and packages/ ship (288 KB, no private
        string), because the mirror's own suite tests the recipes."""
        for path in ("recipes/hf-peft-lora/recipe.toml", "packages/four_asserts/README.md"):
            with self.subTest(path):
                self.assertEqual(policy.decide(path), (True, "source"))

    def test_the_agent_instructions_never_ship(self):
        """They point at every internal document in the tree, so shipping them
        publishes a map of what was held back."""
        for path in ("CLAUDE.md", "AGENTS.md"):
            with self.subTest(path):
                self.assertFalse(policy.decide(path)[0])

    def test_the_denylist_does_not_ship_itself(self):
        """It is a list of the private strings it exists to protect."""
        self.assertFalse(policy.decide("scripts/release/identifiers.json")[0])

    def test_source_ships(self):
        for path in ("app/main.py", "README.md", "scripts/gate.py", "pyproject.toml"):
            with self.subTest(path):
                keep, why = policy.decide(path)
                self.assertTrue(keep, f"{path} would be held back")
                self.assertEqual(why, "source")

    def test_every_doc_the_readme_links_survives_the_policy(self):
        """A README that links to a doc the policy denies publishes a broken
        link. The three are punched back one at a time, deliberately: the rest
        of docs/judge_runs/ stays private, which is the point of naming files
        instead of opening the directory."""
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        for linked in policy.README_LINKED:
            with self.subTest(linked):
                self.assertIn(linked, readme, "the policy allows a doc the README no longer links")
                keep, why = policy.decide(linked)
                self.assertTrue(keep, f"README links {linked} and the mirror would drop it ({why})")

    def test_opening_the_judge_directory_would_be_a_different_decision(self):
        """If FORCE_INCLUDE ever gains a trailing slash for judge_runs, every
        run in there ships, including ones written after that edit. That is a
        decision, and this test is where it has to be argued."""
        for allowed in policy.FORCE_INCLUDE:
            with self.subTest(allowed):
                self.assertFalse(
                    allowed.endswith("/") and "judge_runs" in allowed,
                    "docs/judge_runs/ is force-included as a whole tree",
                )

    def test_the_mirror_has_no_way_to_push(self):
        """A dry-run tool that grows a --push flag has changed what it is."""
        source = (REPO / "scripts" / "release" / "mirror.py").read_text(encoding="utf-8")
        self.assertNotIn('"--push"', source)
        self.assertNotIn("'--push'", source)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
