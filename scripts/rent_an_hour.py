"""One hour of a rented card, pinned so it is one command and not an afternoon.

    python scripts/rent_an_hour.py --plan          # print what would run; spend nothing
    python scripts/rent_an_hour.py --ceiling 1.00  # run it, refusing to exceed the ceiling

**NOTHING RUNS WITHOUT `--ceiling`, AND THE CEILING IS A NUMBER MAX NAMES.** A
default ceiling would be this file deciding how much of somebody else's money to
spend, so there is not one: without the flag this prints the plan and exits.

THE ONE QUESTION IT ANSWERS. Seconds per call. On this machine it is 49, measured
over 49 calls in about 2,400 seconds, and every cost in `docs/rented-card-plan.md`
is that figure with a price attached. A rented hour replaces it with a
measurement or it ends the idea.

WHAT IS PINNED, so that renting is not also designing:

* **the card** - one RTX 4090, 24 GB, RunPod Community, $0.74/hr published
  2026-09-06;
* **the workload** - one call per row of the same pipeline this machine ran, on
  the same rows, at the same window. The count comes from the row file rather
  than from a constant: `CALLS = 60` was a round number nothing derived, and
  deriving it moved the answer to 72 and the hour from comfortable to tight;
* **the comparison** - seconds per call against 49, and the verdicts against the
  ones already recorded, because a faster card that changes the answers has
  changed the experiment rather than sped it up.

WHAT DOES NOT GO. The upload is filtered by the mirror's own policy - the same
`decide()` the release path uses - and the content scan runs first with every
rule. A file the policy would not publish is a file this will not send.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts" / "release"))

#: Published 2026-09-06 on the provider's own page, not an aggregator's.
CARD = "RTX 4090 24GB"
PROVIDER = "RunPod Community"
RATE_PER_HOUR = 0.74

#: The measurement this hour exists to replace.
SECONDS_PER_CALL_HERE = 49.0

#: THE EXITS, NAMED, so a caller can tell them apart and so each one can be
#: asked for by name in a test. Measured 2026-09-07: `CANNOT_COUNT` did not
#: exist, and the state it now reports was returning 0 or 3 - the codes for a
#: plan that counted and a ceiling that was accepted.
PLAN_ONLY = 0
CEILING_TOO_LOW = 2
CEILING_ACCEPTED = 3
CANNOT_COUNT = 4

#: THE ONE FILE THE WORKLOAD READS, named rather than globbed.
#:
#: MEASURED 2026-09-07 and this is the repair. `what_would_go` used to ask for
#: `(REPO / "runs").rglob("*.jsonl")` - every row file in the tree - so `--plan`
#: printed **88 refused paths**, and the fix it demanded was a person approving
#: all 88 by name. THAT IS NOT A DECISION A PERSON CAN MAKE. An unreadable list
#: is how a guard gets waved through, and a guard that gets waved through is the
#: same as no guard while looking like more.
#:
#: The pinned workload is 60-odd calls of ONE recorded pipeline on ONE set of
#: rows, compared against the verdicts already recorded for them. It reads one
#: run's rows, not every run's. This file carries both halves of that: the
#: instruction/real/rewrite the calls need, and the `got`/`expected`/`reply` the
#: comparison is against. Nothing else in `runs/` is read at all.
THE_ROWS = REPO / "runs" / "judge-sentinel-n" / "results.jsonl"

#: What the workload sends, plus the rows. Named one by one for the same reason.
THE_SCRIPTS = (
    REPO / "scripts" / "the_second_judge_pass.py",
    REPO / "scripts" / "what_actually_changed.py",
)


def _shown(path: Path) -> str:
    """The path as a reader should see it: repo-relative when it is in the repo.

    Falls back to the full path rather than raising. `relative_to` throws on
    anything outside the tree, and a plan that CRASHED because a path moved
    would be bookkeeping deciding a verdict.
    """
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


def how_many_rows() -> int | None:
    """Rows in `THE_ROWS`, or None when it is not in this checkout.

    RECORDS, NOT LINES, AND ON THIS FILE THE TWO DISAGREE.
    `runs/judge-sentinel-n/results.jsonl` ends `...se}` with **no trailing
    newline**: 71 newline characters, 72 records. Every neighbouring run file
    ends with one and reports 72 either way, so the single file this rental pins
    is the one where the counts diverge - and it diverges DOWNWARD BY ONE.

    `wc -l`, `len(f.readlines())` minus a guess, or any shell one-liner in a
    report would price the hour on **71 rows of a 72-row file**: plausible, one
    short, and invisible.

    THE DISTINCTION THIS COST ME. Deriving a count protects it from going STALE.
    It does not protect it from counting the WRONG UNIT - a derivation counting
    newlines is still derived, still self-updating, still wrong, and MORE
    convincing than a typed number because it carries the authority of having
    been computed. The 72 behind the 0.98 h is right because of *how* this
    counts, not because it is derived. Two different defences, and conflating
    them is how the second one gets skipped.

    NONE IS NOT ZERO. `runs/` is gitignored, so a fresh clone has no row file at
    all - and a plan that reported "0 calls" there would be describing a
    workload nobody could run as though it were a small one. Unmeasurable
    renders unknown.
    """
    try:
        with THE_ROWS.open(encoding="utf-8") as rows:
            return sum(1 for line in rows if line.strip())
    except OSError:
        return None


def the_calls() -> int | None:
    """How many calls the hour buys, FROM THE FILE rather than from a constant.

    The number used to be `CALLS = 60`, which nothing checked and nothing
    derived - a round number sitting beside a page that said seven where the
    code asked for 88. One call per recorded row is a count that cannot drift
    from the rows it counts.
    """
    return how_many_rows()


def what_would_go() -> tuple[list[str], list[str]]:
    """(files that may leave, files refused) - decided by the release policy.

    THE POLICY STILL DECIDES, and this still may not widen it. Naming the rows
    narrows what is ASKED FOR; whether the ask is granted is `decide()`'s, and
    `runs/` remains an excluded tree - so the row file appears here as refused,
    and putting it in `FORCE_INCLUDE` stays a person's act. A rental script that
    could widen its own upload rule is not bounded by it.
    """
    import policy

    wanted = sorted(
        str(p.relative_to(REPO).as_posix())
        for p in (THE_ROWS, *THE_SCRIPTS)
        if p.exists()
    )
    allowed, refused = [], []
    for path in wanted:
        (allowed if policy.decide(path)[0] else refused).append(path)
    return allowed, refused


def the_plan() -> str:
    allowed, refused = what_would_go()
    calls = the_calls()
    rows_line = (
        f"workload  {calls} calls of the recorded pipeline - one per row in"
        if calls is not None
        else "workload  UNKNOWN - the row file is not in this checkout, and"
    )
    lines = [
        f"card      {CARD} on {PROVIDER}, ${RATE_PER_HOUR:.2f}/hr published 2026-09-06",
        rows_line,
        f"          {_shown(THE_ROWS)}",
    ]
    if calls is None:
        #: NOT ZERO, AND NOT A GUESS. `runs/` is gitignored, so a clone has no
        #: rows - and a plan reporting "0 calls" there would describe a workload
        #: nobody can run as though it were a cheap one.
        lines += [
            "          `runs/` is gitignored, so this says UNKNOWN rather than 0.",
            "          Nothing here can price an hour it cannot count.",
        ]
    else:
        hours = (calls * SECONDS_PER_CALL_HERE) / 3600
        spare = (1.0 - hours) * 60
        lines += [
            f"budget    1 hour = ${RATE_PER_HOUR:.2f}. At this machine's rate those calls",
            f"          take {hours:.2f} h" + (
                f", leaving {spare:.0f} min of the hour. THE HOUR IS A CEILING"
                if spare >= 0 else
                f", which is {-spare:.0f} min OVER the hour. THE HOUR IS NOT ENOUGH"
            ),
            "          and, at this margin, very nearly the estimate too."
            if 0 <= spare < 5 else
            "          rather than an estimate.",
        ]
    lines += [
        "",
        f"decides   seconds per call against {SECONDS_PER_CALL_HERE:.0f} measured here,",
        "          and whether the verdicts match the ones already recorded.",
        "",
        f"uploads   {len(allowed)} file(s) the release policy allows:",
    ]
    lines += [f"            {p}" for p in allowed] or ["            (none found)"]
    if refused:
        lines.append(f"  REFUSED {len(refused)} file(s) the policy holds back:")
        lines += [f"            {p}" for p in refused]
    lines += [
        "",
        "not sent  anything docs/, runs/ artifacts, card_owner/, the denylist,",
        "          and the vault - which is not in this repository at all.",
    ]
    rows = [p for p in refused if p.startswith("runs/")]
    if rows:
        lines += [
            "",
            f"BLOCKED   the workload needs its rows and the policy refuses them:",
        ]
        lines += [f"            {p}" for p in rows]
        lines += [
            f"          {len(rows)} file(s), because runs/ is an excluded tree. So this",
            "          hour would send two scripts and no data, and measure nothing.",
            "          The fix is a person naming that file in FORCE_INCLUDE, the same",
            "          way the three judge-run docs were named one by one - a list this",
            "          short is a list somebody can actually read before approving it.",
            "          It is not a fix this script may make for itself: a rental script",
            "          that can widen its own upload rule is not bounded by it.",
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plan", action="store_true", help="print the plan; spend nothing")
    parser.add_argument(
        "--ceiling", type=float, default=None,
        help="the most this run may cost, in dollars. Named by the owner, never defaulted.",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    print(the_plan())

    #: CANNOT COUNT IS ITS OWN EXIT, AND UNTIL 2026-09-07 IT WAS NOT.
    #:
    #: MEASURED, by running each exit in isolation rather than reading the
    #: branches. With the row file absent, `the_plan()` printed **UNKNOWN** - and
    #: `main` returned **0** for `--plan` and **3** for `--ceiling 5.00`. Those
    #: are the same codes a fully-priced plan returns. So `unmeasurable renders
    #: unknown` was in the PROSE and not in the EXIT CODE, which is the thing a
    #: caller acts on.
    #:
    #: The money case is the second one: it accepted a ceiling against a workload
    #: it could not count, and said so only in a paragraph. A ceiling is named
    #: against a number; if there is no number there is nothing to name it
    #: against, and that has to be a refusal rather than a caveat.
    #:
    #: A DISTINCT CODE ON PURPOSE. Reusing 2 would fold "cannot count" into
    #: "ceiling too low", and a caller that cannot tell those apart is a caller
    #: that retries the wrong one.
    if the_calls() is None:
        print(f"\nREFUSED: the workload cannot be counted, so the hour cannot be "
              f"priced. {THE_ROWS.name} is not in this checkout ({_shown(THE_ROWS)}). "
              f"Nothing here can price an hour it cannot count.", file=sys.stderr)
        return CANNOT_COUNT

    if args.plan or args.ceiling is None:
        print()
        print("PLAN ONLY. Nothing was rented and nothing was sent. Pass --ceiling "
              "<dollars> to run it, and the number has to come from whoever is paying.")
        return PLAN_ONLY

    if args.ceiling < RATE_PER_HOUR:
        print(f"\nREFUSED: one hour costs ${RATE_PER_HOUR:.2f} and the ceiling is "
              f"${args.ceiling:.2f}.", file=sys.stderr)
        return CEILING_TOO_LOW

    # The provider call itself is deliberately absent until a ceiling exists to
    # authorise it: a script that could spend money the moment it is run is a
    # script that will, by accident, once.
    print(f"\nceiling ${args.ceiling:.2f} accepted, and the provisioning step is not "
          "written yet - by design. It is written when the ceiling is named, so that "
          "the first thing anybody runs has been read by somebody who knew the price.",
          file=sys.stderr)
    return CEILING_ACCEPTED


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
