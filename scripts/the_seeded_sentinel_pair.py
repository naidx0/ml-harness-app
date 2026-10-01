"""The sentinel pair again, with a seed and temperature 0.

## The one question it answers

The unseeded pair measured the judge against itself at **52 of 72**, Wilson 0.61
to 0.81 - a band 15 rows wide. Every later comparison has to be read against
that band, and a band that wide can only detect gross change: an owner run
inside 44 to 58 is indistinguishable from the instrument, so *no* agreement
number separates the card owner from the wire while the wire moves this much.

**Is that the model, or is it the call?** The pipeline sends no seed and no
temperature, so the runtime's defaults decide. If a fixed seed and temperature 0
make the judge repeat itself, the instability is the WIRE and the fix is one
line in every caller. If it does not, the instability is the MODEL at this size
and the band is a permanent property that every future claim must live with.

Those two answers lead to different work, which is what makes this worth 144
calls before anything else is measured through the owner.

## What is held constant

The same 72 rows, the same order, the same prompt bytes, the same model, the
same `num_ctx`. **Only `seed` and `temperature` are added**, because a run that
changed two things could not say which one mattered. The unseeded pair is the
control and it already exists; this does not re-run it.

## What would refute what

* **72 of 72 agreement**: seeding makes this judge deterministic on this wire.
  The unseeded band is a property of the call, not the model, and every caller
  should send a seed. This is the outcome that would make the owner's agreement
  number meaningful again.
* **agreement inside 44 to 58**: the seed changed nothing measurable. The
  instability is the model, the band stands as a permanent floor, and agreement
  is not a usable acceptance test for the owner at any threshold.
* **anything between**: seeding helps and does not settle it, and the honest
  report is the number with its interval rather than a verdict either way.

A single pair cannot separate "the seed did nothing" from "the seed helped a
little", and this script does not pretend otherwise: it prints the count, the
interval, and the unseeded number beside it.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: The unseeded pair, for the report to stand beside. Measured 2026-09-05,
#: `runs/sentinel-n-pair/results.jsonl`.
THE_UNSEEDED_AGREEMENT = 52
THE_ROWS = 72
THE_UNSEEDED_BAND = (44, 58)

#: Fixed and written down rather than chosen at the prompt, so a rerun of this
#: script is the same run.
THE_SEED = 20260906

sys.path.insert(0, str(REPO))
sys.dont_write_bytecode = True
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ask(system: str, user: str) -> str:
    """One judge call, with the seed and temperature this run is about."""
    body = {
        "model": "granite42-hermes:latest",
        "stream": False,
        "options": {"num_ctx": 65536, "seed": THE_SEED, "temperature": 0},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        payload = json.load(response)
    return ((payload.get("message") or {}).get("content") or "").strip()


def main() -> int:
    gate_lock = load("one_gate_at_a_time", REPO / "scripts" / "one_gate_at_a_time.py")
    the_lock = load("the_lock", REPO / "card_owner" / "the_lock.py")
    lock_log = load("the_lock_log", REPO / "card_owner" / "the_lock_log.py")
    host_of = load("the_host", REPO / "card_owner" / "the_host.py")
    driver = load("gen", REPO / "scripts" / "generate_the_preference_pairs.py")
    record = load("the_record", REPO / "card_owner" / "the_record.py")

    # The path is imported, never spelled here: `scripts/` is published by the
    # mirror and `card_owner/` is not. Learned when this lane's own runner was
    # caught naming a home directory and a private notebook.
    nightshift = the_lock.THE_LOCK.parent
    card = host_of.the_card_of()
    lock = nightshift / card.lock_name
    ledger = nightshift / "gpu.lock.log"

    rows_file = (
        nightshift.parent
        / "10-Signals" / "specs" / "evidence" / "sentinel-N-2026-09-05"
        / "sentinel-N.jsonl"
    )
    if not rows_file.exists():
        print(f"{rows_file} is not here; nothing was run.", file=sys.stderr)
        return 2
    rows = [
        json.loads(line)
        for line in rows_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) != THE_ROWS:
        print(
            f"expected {THE_ROWS} sentinel rows, found {len(rows)} - this would "
            "not be the same set the unseeded pair measured, so the comparison "
            "would be meaningless. Nothing was run.",
            file=sys.stderr,
        )
        return 2

    if lock.exists():
        print(f"the card is held: {lock.read_text(encoding='utf-8').strip()}", file=sys.stderr)
        return 2

    mine = os.getpid()
    took_at = datetime.now(timezone.utc)
    take = (
        f"lane=mlharness host={card.host} "
        f"since={took_at.strftime('%Y-%m-%dT%H:%M:%SZ')} pid={mine} "
        f"born={gate_lock.born_when(mine)} "
        f"what=the SEEDED sentinel pair, seed={THE_SEED} temperature=0, 144 calls"
    )
    lock.write_text(take + "\n", encoding="utf-8")
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(lock_log.the_take_line(take) + "\n")
    print("lock:", take, flush=True)

    started = time.monotonic()
    try:
        runs: list[list[str | None]] = []
        outcomes: list[dict] = []
        for attempt in (1, 2):
            print(f"\n--- seeded run {attempt} of 2, same {THE_ROWS} rows ---", flush=True)
            verdicts: list[str | None] = []
            for number, row in enumerate(rows, 1):
                try:
                    shown = driver.what_the_judge_is_shown(
                        question=row["instruction"],
                        chosen=row["real"],
                        rejected=row["rewrite"],
                        degradation=driver.DEGRADATIONS[0],
                    )
                    reply = ask(driver.JUDGE_SYSTEM, shown)
                    read = driver.read_the_judges_verdict(reply)
                    verdicts.append(None if read is None else ("KEEP" if read else "DROP"))
                    outcomes.append({"outcome": record.ANSWERED})
                except (urllib.error.URLError, OSError, TimeoutError, ValueError) as error:
                    verdicts.append(None)
                    outcomes.append(record.an_aborted_row(number - 1, str(error)))
                    print(f"    [{attempt}:{number}] ABORTED: {error}", flush=True)
                if number % 12 == 0:
                    print(f"    {number}/{THE_ROWS}", flush=True)
            runs.append(verdicts)

        first, second = runs
        out = REPO / "runs" / "sentinel-n-pair-seeded"
        out.mkdir(parents=True, exist_ok=True)
        (out / "results.jsonl").write_text(
            "\n".join(
                json.dumps(
                    {
                        "id": rows[i].get("id", i),
                        "edit": rows[i].get("edit", ""),
                        "edit_kind": rows[i].get("edit_kind"),
                        "run1": first[i],
                        "run2": second[i],
                        "agreed": first[i] == second[i],
                    },
                    ensure_ascii=False,
                )
                for i in range(THE_ROWS)
            )
            + "\n",
            encoding="utf-8",
        )

        tally = record.the_tally(THE_ROWS * 2, outcomes)
        #: COMPARABLE ROWS ONLY. `None` is an unreadable or aborted call, and
        #: `None == None` is True in Python - so counting agreement over every
        #: row would score a row where BOTH calls failed as a row where the
        #: judge agreed with itself. That inflates the single number this run
        #: exists to produce, and inflates it in the direction that makes
        #: seeding look like it worked. The unseeded pair had 0 unreadable of
        #: 144, so this never bit; a defect that has not bitten yet is still a
        #: defect, and this one would have been invisible in the result.
        comparable = [(a, b) for a, b in zip(first, second)
                      if a is not None and b is not None]
        agreed = sum(1 for a, b in comparable if a == b)
        from app.tools import evals

        low, high = evals.wilson(agreed, len(comparable)) if comparable else (0.0, 0.0)

        print("\n" + "=" * 66)
        print(record.the_calls_line(tally))
        red = record.why_this_record_is_red(tally)
        if red:
            print(red)
        print(
            f"\nSEEDED (seed={THE_SEED}, temperature=0): {agreed} of "
            f"{len(comparable)} comparable rows agree   Wilson {low:.2f} - {high:.2f}"
        )
        if len(comparable) < THE_ROWS:
            print(
                f"  {THE_ROWS - len(comparable)} of {THE_ROWS} rows are NOT "
                "comparable - a call failed on one side or both. They are "
                "excluded from the count rather than scored as agreement."
            )
        print(
            f"UNSEEDED, measured 2026-09-05          : {THE_UNSEEDED_AGREEMENT} of "
            f"{THE_ROWS}, band {THE_UNSEEDED_BAND[0]} to {THE_UNSEEDED_BAND[1]}"
        )
        print(f"  seeded run 1: {dict(Counter(first))}")
        print(f"  seeded run 2: {dict(Counter(second))}")
        print(f"  unreadable  : {sum(1 for v in first + second if v is None)} of {THE_ROWS * 2}")

        print("\nAGAINST WHAT WAS REGISTERED BEFORE THE RUN:")
        # Determinism is a claim about EVERY row, so it needs all 72 comparable
        # as well as all 72 agreeing. With a call missing, the strongest honest
        # statement is "every row we could compare agreed", which is not the
        # same claim and must not print the same sentence.
        if agreed == THE_ROWS and len(comparable) == THE_ROWS:
            print(
                "  72 of 72. Seeding makes this judge deterministic on this wire.\n"
                "  The unseeded band is a property of the CALL, not the model, and\n"
                "  every caller should send a seed. The owner's agreement number\n"
                "  becomes meaningful again."
            )
        elif comparable and agreed == len(comparable):
            # No escapes in this block on purpose: three separate strings
            # rather than one carrying newline escapes, because a heredoc
            # collapsed those escapes three times tonight and produced an
            # unterminated literal each time.
            print(
                f"  {agreed} of {len(comparable)} comparable rows agreed, "
                f"and {THE_ROWS - len(comparable)} row(s) could not be compared."
            )
            print("  Every row this run could read agreed, which is NOT the")
            print("  same as determinism over the set: the missing rows are")
            print("  missing, not agreeing. Re-run those rows before the")
            print("  stronger claim is made.")
        elif THE_UNSEEDED_BAND[0] <= agreed <= THE_UNSEEDED_BAND[1]:
            print(
                "  Inside the unseeded band. The seed changed nothing this run can\n"
                "  measure: the instability is the MODEL at this size, the band is a\n"
                "  permanent floor, and agreement is not a usable acceptance test\n"
                "  for the owner at any threshold."
            )
        else:
            print(
                "  Above the unseeded band but short of determinism. Seeding helps\n"
                "  and does not settle it. One pair cannot separate 'a little' from\n"
                "  'a lot' - the number and its interval are the report, and a\n"
                "  verdict either way would be more than this run measured."
            )
        print(f"\nwall {(time.monotonic() - started) / 60:.1f} min")
        print(f"written to {out}")
        return 0 if not red else 1
    finally:
        released_at = datetime.now(timezone.utc)
        held = (released_at - took_at).total_seconds()
        try:
            with ledger.open("a", encoding="utf-8") as fh:
                fh.write(lock_log.the_release_line("mlharness", released_at, held) + "\n")
            lock.unlink()
            print(f"LOCK RELEASED after {held / 60:.1f} min", flush=True)
        except OSError as error:
            print(f"could not release cleanly: {error}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
