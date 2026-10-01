"""The second judge pass over the 188, and the set that survives both.

## Why a second pass at all

The 200-row corpus was kept by ONE judge run. Measured 2026-09-05 on the
sentinel-N pair: the judge agrees with itself on 52 of 72, and **KEEP is the
unstable verdict** - 11 of 16 first-pass KEEPs flipped against 9 of 56 DROPs.
DROP is a refusal, so the noise sits on the decision that puts a row in the
training file. A corpus selected by one pass of an instrument that unstable is a
corpus whose membership is partly a coin.

So the showcase trains on rows kept by BOTH passes and passing both gates. This
run is the second pass.

## The 188, and why not the 164

The run judged 188: 164 it kept and 24 it dropped. Re-judging only the kept rows
would give "kept by both", but it cannot see the other direction - the pair
shows 9 of 56 DROPs flipping to KEEP (16%), so a kept-only pass would report
half the instrument's error and call it all of it. **The disagreement set is the
point of this run as much as the intersection is**, and half a disagreement set
is not a smaller version of one, it is a biased one.

## The stopping rule, fixed before the run

Set by the orchestrator as Max, before any call: **if the intersection is 100
rows or more the showcase trains on it; below 100 the showcase stops before
training and says why, and Max decides.** This script prints that verdict; it
does not train, and it does not adjust the threshold to whatever it found.

## What it is careful about

* the judge prompt is rebuilt from the same four inputs pass one used, and there
  is only one degradation in `DEGRADATIONS`, so the bytes are reproducible
* the tally is `card_owner.the_record`: 188 outcomes or the record is red. A
  call that dies is an `aborted` row written when it happens
* the lock line carries `lane`, `host`, `since`, `pid` and `born`, and take and
  release are appended to `gpu.lock.log` per the 00:30 amendment
* **it writes each row to disk as that row completes**, flushed, so a run killed
  part-way leaves the calls it paid for. Until 2026-09-07 it built the record in
  memory and wrote once after the loop, which guarded a crash in the ARITHMETIC
  and left the LOOP unprotected - killed on row 71 of 72 it left nothing at all,
  aborted rows included. That is the half that dies when a rented hour ends
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
#: THE LOCK'S DIRECTORY IS NOT WRITTEN HERE. `scripts/` is published by the
#: mirror and `card_owner/` is not, so a path spelled out in this file would
#: publish whose machine and which private notebook the card protocol lives in -
#: which `tests/test_no_shipped_file_names_a_person.py` caught in this very
#: file, on a rebase, after the run had already started.
#:
#: Importing it from `card_owner/the_lock.py` fixes more than the leak: that
#: module already defines the path and says it is deliberately not configurable,
#: because a runner writing a different lock from the lanes it shares the card
#: with is worse than no lock at all. Two definitions of one path can drift; one
#: cannot.
RUN = REPO / "runs" / "two-hundred"
OUT = REPO / "runs" / "second-judge-pass"

#: The stopping rule, written before the run and not adjusted to the result.
THE_SHOWCASE_NEEDS = 100

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


def rows_of(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def the_one_hundred_and_eighty_eight() -> list[dict]:
    """The rows that reached the judge: 164 it kept, 24 it dropped.

    The 12 the validator refused never reached it and are not re-judged: they
    were never the judge's to decide, and including them would change what the
    denominator means.
    """
    kept = rows_of(RUN / "train.synthetic.jsonl")
    dropped = [
        row
        for row in rows_of(RUN / "dropped.jsonl")
        if "judge" in str(row.get("dropped_by", "")).lower()
    ]
    rows = []
    for row in kept:
        rows.append({**row, "run1": "KEEP"})
    for row in dropped:
        rows.append({**row, "run1": "DROP"})
    return rows


def ask(system: str, user: str, timeout: int = 600) -> str:
    body = {
        "model": "granite42-hermes:latest",
        "stream": False,
        "options": {"num_ctx": 65536},
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
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    return ((payload.get("message") or {}).get("content") or "").strip()


def main() -> int:
    gate_lock = load("one_gate_at_a_time", REPO / "scripts" / "one_gate_at_a_time.py")
    driver = load("gen", REPO / "scripts" / "generate_the_preference_pairs.py")
    record = load("the_record", REPO / "card_owner" / "the_record.py")
    lock_log = load("the_lock_log", REPO / "card_owner" / "the_lock_log.py")
    host_of = load("the_host", REPO / "card_owner" / "the_host.py")

    the_lock = load("the_lock", REPO / "card_owner" / "the_lock.py")
    nightshift = the_lock.THE_LOCK.parent

    card = host_of.the_card_of()
    lock = nightshift / card.lock_name
    ledger = nightshift / "gpu.lock.log"

    if lock.exists():
        print(
            f"the card is held: {lock.read_text(encoding='utf-8').strip()}",
            file=sys.stderr,
        )
        return 2

    rows = the_one_hundred_and_eighty_eight()
    asked = len(rows)
    if asked != 188:
        print(
            f"expected 188 rows that reached the judge, found {asked}. The run "
            "record and this script disagree about the corpus; nothing was run.",
            file=sys.stderr,
        )
        return 2

    mine = os.getpid()
    took_at = datetime.now(timezone.utc)
    take = (
        f"lane=mlharness host={card.host} "
        f"since={took_at.strftime('%Y-%m-%dT%H:%M:%SZ')} pid={mine} "
        f"born={gate_lock.born_when(mine)} "
        f"what=the second judge pass over the {asked}, sequential, one call at a time"
    )
    lock.write_text(take + "\n", encoding="utf-8")
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(lock_log.the_take_line(take) + "\n")
    print("lock:", take, flush=True)

    started = time.monotonic()
    try:
        results: list[dict] = []
        #: EVERY ROW REACHES DISK AS IT COMPLETES, and until 2026-09-07 none did.
        #:
        #: The whole record used to be built in memory and written once after the
        #: loop, so a process that died on row 71 of 72 left NOTHING - not the 70
        #: answered calls, and not the aborted rows either. The per-row `except`
        #: below looked like durability and is not: it constructs an aborted row
        #: at the moment of failure (which is why it carries the real error
        #: rather than a reconstruction) and appends it to the same in-memory
        #: list as everything else. **Both failures left the same thing on disk:
        #: nothing.**
        #:
        #: This matters most where it is about to be spent. A rented hour is
        #: priced at 0.98 h against a 1 h ceiling, so the likely death is the
        #: hour ending - and with a single write at the end that costs $0.74 for
        #: zero rows. Writing per row turns total loss into partial loss: cut off
        #: on row 71, the run leaves 70 usable rows and a measurement. **The
        #: tight margin then costs the tail of the run rather than the run.**
        #:
        #: `flush()` per row on purpose. A buffered handle is the same failure
        #: one layer down - bytes that exist only in this process.
        OUT.mkdir(parents=True, exist_ok=True)
        rolling = (OUT / "results.jsonl").open("w", encoding="utf-8")

        def keep(entry: dict) -> None:
            """Record it in memory AND on disk, in that order, before moving on."""
            results.append(entry)
            rolling.write(json.dumps(entry, ensure_ascii=False) + "\n")
            rolling.flush()

        for number, row in enumerate(rows, 1):
            try:
                shown = driver.what_the_judge_is_shown(
                    question=row["prompt"],
                    chosen=row["chosen"],
                    rejected=row["rejected"],
                    degradation=driver.DEGRADATIONS[0],
                )
                reply = ask(driver.JUDGE_SYSTEM, shown)
                read = driver.read_the_judges_verdict(reply)
                keep(
                    {
                        "prompt": row["prompt"],
                        "chosen": row["chosen"],
                        "rejected": row["rejected"],
                        "source_row": row.get("synthetic_source_index"),
                        "run1": row["run1"],
                        "run2": None if read is None else ("KEEP" if read else "DROP"),
                        "run2_reply": reply,
                        "outcome": record.ANSWERED,
                    }
                )
            except (urllib.error.URLError, OSError, TimeoutError, ValueError) as error:
                # Written AT THE MOMENT OF FAILURE, not reconstructed from a gap.
                aborted = record.an_aborted_row(number - 1, f"{type(error).__name__}: {error}")
                aborted.update(
                    {
                        "prompt": row["prompt"],
                        "chosen": row["chosen"],
                        "rejected": row["rejected"],
                        "source_row": row.get("synthetic_source_index"),
                        "run1": row["run1"],
                        "run2": None,
                    }
                )
                keep(aborted)
                print(f"    [{number}/{asked}] ABORTED: {error}", flush=True)
            if number % 20 == 0:
                print(f"    {number}/{asked}", flush=True)

        # EVERY ROW IS ALREADY ON DISK. This closes the handle rather than
        # writing the record, because the record was written as it happened -
        # which is the whole change. The old comment here said the record went
        # to disk "before any arithmetic, so a run that dies in the summary
        # still leaves the calls it paid for": that guarded a crash in the
        # SUMMARY and left the LOOP unprotected, and the loop is the half that
        # dies when a rented hour ends.
        rolling.close()

        tally = record.the_tally(asked, results)
        print("\n" + "=" * 66)
        print(record.the_calls_line(tally))
        red = record.why_this_record_is_red(tally)
        if red:
            print(red)

        both = [r for r in results if r["run1"] == "KEEP" and r["run2"] == "KEEP"]
        only_one = [
            r
            for r in results
            if r["run2"] is not None and r["run1"] != r["run2"]
        ]
        agreed = sum(1 for r in results if r["run2"] is not None and r["run1"] == r["run2"])
        readable = sum(1 for r in results if r["run2"] is not None)

        from app.tools import evals

        low, high = evals.wilson(agreed, readable) if readable else (0.0, 0.0)
        print(
            f"\nagreement with pass 1: {agreed} of {readable} readable "
            f"(Wilson {low:.2f} - {high:.2f})"
        )
        print(f"  kept by BOTH passes            : {len(both)}")
        print(f"  kept by one and dropped by other: {len(only_one)}")

        (OUT / "the-instruments-own-error.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in only_one) + "\n",
            encoding="utf-8",
        )
        (OUT / "kept-by-both.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in both) + "\n",
            encoding="utf-8",
        )

        print(f"\nTHE STOPPING RULE, fixed before the run: {THE_SHOWCASE_NEEDS} rows")
        if len(both) >= THE_SHOWCASE_NEEDS:
            print(
                f"  {len(both)} >= {THE_SHOWCASE_NEEDS}: the showcase trains on "
                "the intersection."
            )
        else:
            print(
                f"  {len(both)} < {THE_SHOWCASE_NEEDS}: THE SHOWCASE STOPS BEFORE "
                "TRAINING. Max decides. Nothing here adjusts the threshold to "
                "what the run happened to find."
            )
        print(f"\nwall {(time.monotonic() - started) / 60:.1f} min for {asked} calls")
        print(f"written to {OUT}")
        return 0 if not red else 1
    finally:
        #: CLOSED ON EVERY PATH OUT, including the ones that raise. Nothing is
        #: LOST if this is missed - every row was flushed as it was written, so
        #: the bytes are on disk either way - but a handle left open by an
        #: exception is a file the operating system closes at its own
        #: convenience, and "it works because the process exited" is not a
        #: durability argument. Guarded with a name check because the exception
        #: may have been raised BEFORE the handle existed.
        rolling = locals().get("rolling")
        if rolling is not None and not rolling.closed:
            try:
                rolling.flush()
                rolling.close()
            except OSError as error:
                print(f"could not close the row record: {error}", file=sys.stderr)

        released_at = datetime.now(timezone.utc)
        held = (released_at - took_at).total_seconds()
        try:
            with ledger.open("a", encoding="utf-8") as fh:
                fh.write(
                    lock_log.the_release_line("mlharness", released_at, held) + "\n"
                )
            lock.unlink()
            print(f"LOCK RELEASED after {held / 60:.1f} min", flush=True)
        except OSError as error:
            print(f"could not release cleanly: {error}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
