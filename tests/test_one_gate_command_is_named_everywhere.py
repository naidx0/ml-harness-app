"""Every place that declares the gate declares the same gate.

ITEM 38, and it is item 29's defect made unrepeatable. Four entry points run
this suite and one of them stated what a finished run looks like: CI ran
`python -m unittest discover -s tests` while every lane locally ran
`python scripts/gate.py`, so the two checks that caught real green-looking
failures here - a run that lost tests still printing OK, and a module replaced
by an erroring placeholder that keeps the discovered count intact - ran only on
the machine of whoever remembered them.

The workflow's own comment had warned about exactly that: a CI running a
different command from the one a person runs before committing is two gates,
and the one nobody watches is the one that rots. It had happened to the comment
that warned about it, which is the whole reason this is a test now. A rule
stated in prose is enforced by whoever last read the prose.

WHAT THIS HOLDS. That `AGENTS.md`, the CI workflow and the lock wrapper's own
usage line all name `scripts/gate.py`. Not that the command strings match
character for character - `AGENTS.md` writes it as a sentence, the workflow as
a `run:` line, the wrapper inside an example after a `--` - so each is checked
for the thing that actually has to agree: which script is the gate.

WHAT IT DOES NOT HOLD. Whether that gate is any good. That is what everything
else in `tests/` is for.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: The one that has to agree. If the gate is ever renamed, this is the single
#: line to change, and every place below will then say where it disagrees.
THE_GATE = "scripts/gate.py"

#: THE LIVE IMPERATIVE, and not every mention of it. The first version matched
#: any line containing "Gate before commit:" and went red on its first full run
#: - against `docs/walks.md`, where the record of THIS finding quotes the phrase
#: in order to talk about it. A guard that cannot tell an instruction from a
#: description of one would force every account of the rule to be written around
#: the guard, which is the tail wagging the dog.
#:
#: The shape is what separates them: every real copy is a list item, `- Gate
#: before commit: ...` or `- **Gate before commit:** ...`. Prose about the rule
#: is not. This is the same distinction that was applied by hand to the nine
#: historical occurrences - "Ran 656 tests ... OK" names the old command because
#: that is what was run then - now written down instead of remembered.
THE_IMPERATIVE = re.compile(r"^\s*[-*]\s+\*{0,2}Gate before commit")

DECLARES_IT = {
    "AGENTS.md": "the instruction every lane reads before committing",
    ".github/workflows/gate.yml": "the gate nobody watches until it rots",
    "scripts/one_gate_at_a_time.py": "the wrapper's own usage line",
}


def files_git_tracks() -> set[str] | None:
    """Every path git tracks, or `None` when git cannot answer.

    THE RULE ML HARNESS WROTE, MATCHED TO THE REASON IT GAVE. This guard went
    red on main against three lines in `.claude/worktrees/epic-feynman-9788ce`,
    a scratch checkout of an older commit whose `AGENTS.md` carries the rule as
    it stood then. That lane's fix skipped that directory BY NAME, with the
    right argument beside it: the file is *"UNTRACKED by git - `git ls-files`
    returns nothing for it"*, and this guard is about the copies people READ.

    The argument is about tracking and the rule was about a path, and those come
    apart. Measured in this checkout on 2026-09-05: **92 markdown files, 2 of
    them untracked, and 0 of the 2 caught by the path rule** - generated adapter
    READMEs under `runs/`, the same class of thing in a different place. A
    second scratch checkout somewhere else would be missed the same way.

    So the skip asks git. `None` means git could not answer, and the caller then
    scans everything: a guard that over-scans goes red loudly and gets fixed,
    while one that under-scans passes silently, and only one of those two
    failures announces itself.
    """
    try:
        done = subprocess.run(
            ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover
        return None
    if done.returncode != 0:  # pragma: no cover - not a checkout
        return None
    return {line.strip() for line in done.stdout.splitlines() if line.strip()}


class OneGateCommandIsNamedEverywhereTest(unittest.TestCase):
    def test_every_declaring_file_names_the_same_gate(self):
        silent = []
        for name, why in DECLARES_IT.items():
            path = REPO / name
            if not path.exists():  # pragma: no cover - a moved file is its own failure
                silent.append(f"{name} is missing ({why})")
                continue
            if THE_GATE not in path.read_text(encoding="utf-8"):
                silent.append(f"{name} does not name {THE_GATE} ({why})")
        self.assertEqual(
            silent,
            [],
            "a file that tells somebody how to gate names a different gate from "
            "the others, which is how this repository ended up running two",
        )

    def test_the_ci_step_runs_it_rather_than_only_mentioning_it(self):
        """A comment naming the gate is not CI running the gate - which is
        precisely the state item 29 found."""
        workflow = (REPO / ".github" / "workflows" / "gate.yml").read_text(encoding="utf-8")
        runs = re.findall(r"^\s*run:\s*(.+)$", workflow, re.M)
        self.assertTrue(
            any(THE_GATE in line for line in runs),
            f"no CI step actually runs {THE_GATE}; it is only mentioned. "
            f"Steps found: {runs}",
        )

    def test_every_copy_of_the_rule_names_the_current_gate(self):
        """THE COPIES, FOUND 2026-09-05 BY LOOKING PAST THE LIST ABOVE.

        The rule is not stated once. `AGENTS.md`'s "Gate before commit:" line is
        copied verbatim into `BUILD_PLAN.md` and `docs/ROADMAP.md`, and
        `ROADMAP.md` says so in as many words - "It carries over verbatim". That
        is why item 29's change did not propagate: the contract is duplicated,
        so correcting one leaves the copies instructing a reader to run a gate
        this repository no longer runs.

        This DISCOVERS the copies rather than listing them, so a fourth is
        caught on the day it is written rather than on the day someone notices -
        and it matches the live imperative rather than the phrase, because on
        its first full run it went red against a record that merely QUOTED the
        phrase. See `THE_IMPERATIVE`.

        It deliberately does not touch historical records. `docs/ROADMAP.md`
        also says "Ran 656 tests ... OK" and `docs/HONEST_PATH.md` pins "Expect
        at a9245c3: Ran 816 tests" - those name the old command because that is
        what was run then, and rewriting them would falsify a record. Only the
        live imperative is checked, and it is recognised by its own words.
        """
        stale = []
        tracked = files_git_tracks()
        for path in sorted(REPO.rglob("*.md")):
            if any(part in path.parts for part in ("node_modules", ".git")):
                continue
            #: Untracked files are not copies anybody reads: a scratch
            #: worktree of an older commit, a generated adapter README. See
            #: `files_git_tracks` for why this asks git rather than matching a
            #: directory name.
            if tracked is not None and path.relative_to(REPO).as_posix() not in tracked:
                continue
            if "overnight" in path.parts or "judge_runs" in path.parts:
                continue  # dated records, true when written
            for number, text in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if THE_IMPERATIVE.match(text) and THE_GATE not in text:
                    stale.append(f"{path.relative_to(REPO).as_posix()}:{number}")
        self.assertEqual(
            stale,
            [],
            f"a live copy of the gate rule names a gate other than {THE_GATE}. The "
            "rule is copied verbatim between files, so changing one is never enough.",
        )

    def test_the_rule_is_found_where_it_is_known_to_be(self):
        """If the phrase is ever reworded, the check above passes by finding
        nothing. This fails instead."""
        tracked = files_git_tracks()
        carriers = [
            path
            for path in sorted(REPO.rglob("*.md"))
            if "node_modules" not in path.parts
            and (tracked is None or path.relative_to(REPO).as_posix() in tracked)
            and any(
                THE_IMPERATIVE.match(line)
                for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
            )
        ]
        self.assertGreaterEqual(
            len(carriers), 3, f"expected the rule in at least 3 files, found {carriers}"
        )

    def test_the_gate_it_names_exists_and_is_runnable(self):
        gate = REPO / THE_GATE
        self.assertTrue(gate.exists(), f"{THE_GATE} is named everywhere and is not there")
        self.assertIn("GATE IS GREEN", gate.read_text(encoding="utf-8"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
