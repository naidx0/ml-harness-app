"""WHAT SHIPS IN A PUBLIC MIRROR OF THIS REPOSITORY — the decision, on its own.

This lives apart from `mirror.py` for one reason, and it is the reason Sequence's
`tools/release` splits the same way: the highest-consequence failure in the whole
release path is `decide()` quietly starting to say *keep* for something under
`docs/`. That publishes a private note permanently, and it looks exactly like a
successful release. A rule that important should not be reachable only by running
the tool.

DENY BY DEFAULT UNDER `docs/`, AND THE ASYMMETRY IS THE WHOLE ARGUMENT. An
exclusion list only protects you from the private files you thought of. This
tree's `docs/` currently holds judge runs, overnight reports, walk records and
an evidence directory, and it grows several files on an ordinary night. A doc
tree that grew a new owner plan tomorrow would ship it by default, silently and
permanently. The reverse mistake — a public doc missing for one release — is
fixable in a minute.

`runs/` IS NOT A DOC PROBLEM, IT IS ITS OWN. It holds sandboxes, adapters and
run artifacts named by identifier, and nothing in it was written to be read by a
stranger. It never ships, whatever it contains.
"""

from __future__ import annotations

#: Whole trees that never ship, whatever they contain.
EXCLUDE_DIRS = [
    ".claude/",       # agent workspace, including scratch worktrees
    ".agents/",
    ".cursor/",
    "docs/",          # deny-by-default - see DOC_ALLOW
    "runs/",          # sandboxes, adapters, run artifacts named by identifier
    # recipes/ and packages/ SHIP since 2026-10-01: 288 KB together, no private
    # string in either (checked), and 43 of the mirror's 140 red tests were tests
    # of the recipes the mirror had left out.
    # OPERATOR TOOLING, NOT PRODUCT, and it necessarily names a private path:
    # the card owner reads one specific lock file and its own comment says
    # that path is deliberately not configurable, because a card owner
    # reading a different lock from the lanes it protects is worse than no
    # lock at all. Scrubbing it would break the thing; excluding it is the
    # honest answer, and it is not part of what a visitor would install.
    "card_owner/",
    # The lab notebook folded in from ml-harness-lab: logs, handoffs, sealed
    # cases and drivers that name this machine's paths by design. Research
    # record, not product.
    "lab/",
]

#: Individual files that never ship.
EXCLUDE_FILES = {
    "CLAUDE.md",                       # agent instructions, and it points at every internal doc
    "AGENTS.md",                       # the same, for the other reader
    "scripts/release/identifiers.json",  # the denylist is itself the private data it protects
}

#: Exceptions punched back through EXCLUDE_DIRS, in order.
FORCE_INCLUDE = [
    # The three the README sends a visitor to. They are punched back through
    # the deny-by-default because they were CHOSEN, one by one, and read: the
    # rest of `docs/judge_runs/` stays private, which is the point of listing
    # three files rather than opening the directory.
    "docs/judge_runs/THE-JUDGE.md",
    "docs/judge_runs/2026-09-05-sentinel-n-result.md",
    "docs/judge_runs/2026-09-05-two-hundred-rows-prereg.md",
]

#: The docs that ship. Deny-by-default: anything under `docs/` not matched here
#: stays private, INCLUDING every file added after this list was written.
DOC_ALLOW = [
    "docs/VISION.md",
    "docs/how-to-verify.md",
    "docs/PHASES.md",
    "docs/COMPETITION.md",
    "docs/LEDGER_FORMAT.md",
    "docs/diagnosis_engine.yaml",
    "docs/ledgers/",
]

#: `docs/` files the README links to by name. Held separately from DOC_ALLOW so
#: that a README linking to something the policy denies is a LOUD failure rather
#: than a broken link in a published mirror - see `mirror.py`.
README_LINKED = [
    "docs/judge_runs/THE-JUDGE.md",
    "docs/judge_runs/2026-09-05-sentinel-n-result.md",
    "docs/judge_runs/2026-09-05-two-hundred-rows-prereg.md",
]


def decide(path: str) -> tuple[bool, str]:
    """`(keep, why)` for one repository-relative path, in `/` form."""
    for allowed in FORCE_INCLUDE:
        if path == allowed or (allowed.endswith("/") and path.startswith(allowed)):
            return True, "force-included"
    if path in EXCLUDE_FILES:
        return False, "internal file"
    for directory in EXCLUDE_DIRS:
        if not path.startswith(directory):
            continue
        if directory == "docs/":
            for allowed in DOC_ALLOW:
                if path == allowed or (allowed.endswith("/") and path.startswith(allowed)):
                    return True, "docs allow-list"
            return False, "docs deny-by-default"
        return False, f"excluded tree {directory}"
    return True, "source"
