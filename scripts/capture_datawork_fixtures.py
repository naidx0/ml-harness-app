#!/usr/bin/env python3
"""Capture what `app/tools/datawork.py` actually returns, as fixtures.

## Why this exists

`carve_eval_set` is the first tool in this product that changes a user's disk,
and it had no surface. Measured before this script was written, by running it on
a real file and counting the reply with a transcription of `ResultView.tsx`'s own
recursion: 22 top-level keys, 83 rows for the generic table to draw, and - on
the reply where the split LEAKS - seven containers deep against that component's
`MAX_DEPTH` of 3, so 103 of 186 rows do not render. What does not render is
`leakage.examples`: the pairs of rows found on both sides of a file we wrote.

`docs/VISION.md`'s invariant is that no number is ever invented, "in code, in a
document OR IN A MOCKUP", so the card could not be demonstrated against numbers
somebody typed. This script is the other half of that rule: it produces the
payloads the card is built against, by running the real tool on real files and
writing down exactly what came back.

## What it will not do

It will not run against the owner's database. `ML_HARNESS_DB` names the scratch
file, `--work` names where the datasets are written, and `_guard` refuses to
start if `db.DB_PATH` resolves to the repository's own `ml_harness.db`. Every
situation runs in a conversation this script creates, because picking an
existing thread id is how 98,802 rows once landed in somebody's real
conversation.

It will not edit a payload. What the tool returned is re-serialised verbatim
under `payload`; the four keys beside it - `situation`, `dataset`, `produced_by`,
`shape` - are written here and are ABOUT the payload rather than part of it.

`measure()` is imported from `capture_retrieval_fixtures` rather than copied.
It is a transcription of `ResultView.tsx`'s recursion and a second copy of it
here would be a second answer to "what would the generic table draw".

## The four situations, and why these four

    01  a carve that WROTE, and whose own leak check found nothing
    02  a carve that WROTE AND LEAKS - ok: false, and the pairs to prove it
    03  a refusal: the answer column is not in the file
    04  a refusal: carving would leave too little to train on

Run it:

    ML_HARNESS_DB=/tmp/scratch.db python scripts/capture_datawork_fixtures.py

`--check` re-captures into a temporary directory and compares payloads with the
ones on disk instead of overwriting them, which is how the README's claim that
nothing in that folder was typed by hand stays checkable.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

DEFAULT_OUT = REPO / "frontend" / "src" / "fixtures" / "datawork"

THE_TOOL = "carve_eval_set"


# --------------------------------------------------------------------------
# THE DATASETS. Written to disk, then carved.
#
# Nothing in this section is a number that ends up in a fixture: what it decides
# is the SITUATION - a file whose rows are unlike each other, a file whose rows
# are near-duplicates of each other, a file too small to give up a held-out set.
# --------------------------------------------------------------------------

#: A vocabulary wide enough that two rows drawn from it are not near
#: neighbours. `carve_eval_set` runs a real near-duplicate check over what it
#: writes, and a dataset of "ticket 1", "ticket 11", "ticket 111" is a dataset
#: whose every row leaks - which is situation 02 and must not be situation 01.
WORDS = (
    "refund invoice delivery password upgrade cancel account shipping label "
    "return exchange warranty coupon discount receipt tracking courier parcel "
    "damaged missing duplicate charge subscription renewal downgrade transfer "
    "verify reset unlock suspend reopen escalate supervisor callback voucher "
    "credit debit statement threshold overdue reminder dispatch collection"
).split()

CLASSES = ("billing", "shipping", "refund", "account")

#: The seed is stated so this script gives the same datasets every run, which is
#: what makes `--check` a comparison rather than a coin toss.
SEED = 20260821


def distinct(path: Path, rows: int = 400) -> Path:
    draw = random.Random(SEED)
    path.write_text(
        "\n".join(
            json.dumps({"text": " ".join(draw.sample(WORDS, 12)), "answer": CLASSES[i % 4]})
            for i in range(rows)
        ),
        encoding="utf-8",
    )
    return path


def repetitive(path: Path, rows: int = 400) -> Path:
    path.write_text(
        "\n".join(
            json.dumps(
                {"text": f"ticket number {i} about something", "answer": CLASSES[i % 4]}
            )
            for i in range(rows)
        ),
        encoding="utf-8",
    )
    return path


def tiny(path: Path, rows: int = 60) -> Path:
    draw = random.Random(SEED + 1)
    path.write_text(
        "\n".join(
            json.dumps({"text": " ".join(draw.sample(WORDS, 12)), "answer": CLASSES[i % 4]})
            for i in range(rows)
        ),
        encoding="utf-8",
    )
    return path


# --------------------------------------------------------------------------
# The four situations, as calls.
# --------------------------------------------------------------------------

SITUATIONS: list[dict[str, Any]] = [
    {
        "slug": "01-carved-and-clean",
        "situation": (
            "A carve that WROTE and whose own leak check found nothing. ok: true, "
            "which in this tool is the conjunction of 'the two files account for "
            "every row read' and 'the leak check found nothing' rather than a "
            "mood. This is the payload where the card's green pill has to say NO "
            "LEAK and not anything that reads as a gate having opened."
        ),
        "dataset": (
            "400 rows of twelve words each drawn without replacement from a "
            "44-word vocabulary, so no two rows are near neighbours and the "
            "near-duplicate check has nothing to find."
        ),
        "make": distinct,
        "file": "tickets.jsonl",
        "arguments": {"answer_column": "answer"},
    },
    {
        "slug": "02-carved-and-leaking",
        "situation": (
            "A carve that WROTE AND LEAKS. ok: false - a split that leaks is a "
            "failed artifact, not a successful one with a note. This is the "
            "payload the card exists for: `leakage.examples` holds the pairs of "
            "rows found on both sides of a file this harness wrote, and it is "
            "four containers down, which is where ResultView's depth cap falls."
        ),
        "dataset": (
            "400 rows differing only by an integer - 'ticket number 1 about "
            "something' - so every row is a near-duplicate of every other and the "
            "leak check finds real pairs. Four answers rather than one, or the "
            "tool's imbalance refusal fires before its leak check."
        ),
        "make": repetitive,
        "file": "repetitive.jsonl",
        "arguments": {"answer_column": "answer"},
    },
    {
        "slug": "03-refused-no-such-column",
        "situation": (
            "A refusal: the column named as holding the answers is not in the "
            "file. Nothing was written, and `nothing_was_written` is literally "
            "true rather than reassuring - every check runs before the one call "
            "that creates anything."
        ),
        "dataset": "The same 400 distinct rows as 01, asked for a column it does not have.",
        "make": distinct,
        "file": "tickets.jsonl",
        "arguments": {"answer_column": "verdict"},
    },
    {
        "slug": "04-refused-would-starve-training",
        "situation": (
            "A refusal that carries arithmetic: holding out the rows G0 asks for "
            "would leave fewer than dataquality.MIN_ROWS_FOR_TRAINING to train "
            "on. It is the refusal whose extra fields a card cannot know in "
            "advance - would_hold_out, would_leave, minimum_to_train_on - and it "
            "is why the refusal card draws whatever the payload carried under the "
            "engine's own names rather than a closed table of twelve shapes."
        ),
        "dataset": "60 distinct rows, which is too few to give up an eval set from.",
        "make": tiny,
        "file": "small.jsonl",
        "arguments": {"answer_column": "answer"},
    },
]


# --------------------------------------------------------------------------


def _guard() -> None:
    from app import db

    if db.DB_PATH.resolve() == (REPO / "ml_harness.db").resolve():
        raise SystemExit(
            "Refusing to run against the repository's own ml_harness.db. Set "
            "ML_HARNESS_DB to a scratch file."
        )


def capture(work: Path) -> dict[str, dict[str, Any]]:
    """Run every situation and return the fixtures, keyed by slug."""
    work.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("ML_HARNESS_DB", str(work / "scratch.db"))

    from app import db, identity, jobspec

    db.DB_PATH = Path(os.environ["ML_HARNESS_DB"])
    jobspec.RUNS_ROOT = work / "runs"
    _guard()
    db.init_db()

    from app.tools import REGISTRY, evidence
    from capture_retrieval_fixtures import measure

    with db.connect() as connection:
        thread = connection.execute(
            "INSERT INTO threads (title, created_at) VALUES (?, datetime('now'))",
            ("capture_datawork_fixtures",),
        ).lastrowid

    captured: dict[str, dict[str, Any]] = {}
    for one in SITUATIONS:
        source = one["make"](work / one["file"])
        arguments = {
            "path": str(source),
            "into": str(work / f"{one['slug']}_out"),
            **one["arguments"],
        }
        payload = REGISTRY.call(
            THE_TOOL,
            dict(arguments),
            approved=True,
            actor=evidence.USER,
            thread_id=thread,
        )
        captured[one["slug"]] = {
            "situation": one["situation"],
            "dataset": one["dataset"],
            "produced_by": {
                "tool": THE_TOOL,
                "arguments": arguments,
                "thread_id": thread,
                "database": str(db.DB_PATH),
                "captured_at_utc": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                ),
                "engine": identity.build().get("code_fingerprint"),
            },
            "shape": measure(payload),
            "payload": payload,
        }
    return captured


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--work", type=Path, default=None)
    parser.add_argument(
        "--check",
        action="store_true",
        help="re-capture into a temp directory and compare, writing nothing",
    )
    args = parser.parse_args()

    work = args.work or Path(tempfile.mkdtemp(prefix="datawork_fixtures_"))
    fixtures = capture(work)

    if args.check:
        bad = 0
        for slug, fixture in fixtures.items():
            drawn = args.out / f"{slug}.json"
            if not drawn.exists():
                print(f"MISSING {slug}")
                bad += 1
                continue
            on_disk = json.loads(drawn.read_text(encoding="utf-8"))
            # The paths and the timestamps differ per run by construction; the
            # PAYLOAD's own numbers are what this compares.
            here = json.dumps(fixture["shape"], sort_keys=True)
            there = json.dumps(on_disk.get("shape"), sort_keys=True)
            if here != there:
                print(f"CHANGED {slug}\n  now: {here}\n  was: {there}")
                bad += 1
        print("checked", len(fixtures), "fixtures;", bad, "differ")
        return 1 if bad else 0

    args.out.mkdir(parents=True, exist_ok=True)
    for slug, fixture in fixtures.items():
        (args.out / f"{slug}.json").write_text(
            json.dumps(fixture, indent=2) + "\n", encoding="utf-8"
        )
    (args.out / "SHAPES.json").write_text(
        json.dumps(
            {slug: fixture["shape"] for slug, fixture in fixtures.items()}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    for slug, fixture in fixtures.items():
        shape = fixture["shape"]
        print(
            f"{slug:34} ok={str(fixture['payload'].get('ok')):5} "
            f"keys={shape['top_level_keys']:3} "
            f"rows={shape['rows_a_flat_table_would_draw']:4} "
            f"depth={shape['max_nesting_depth']} "
            f"hidden={shape['rows_hidden_behind_those_summaries']:4}"
        )
    print("\nwrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
