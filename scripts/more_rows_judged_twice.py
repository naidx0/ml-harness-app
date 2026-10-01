"""Generate rows through the full pipeline and judge every kept row twice.

## What this is for

The corpus stopped five rows short: 95 three-gate rows against a line of 100.
This produces more rows the same way the first 200 were produced, and judges
each survivor a second time, so the result is comparable with the 95 rather than
assembled from two runs on different days.

**All three gates now run at generation** (`344000b`), so a row that reaches the
second pass here has already passed the inverted-refusal check, the diff gate
and the added-fact rule. That is the difference between this run and the last
one: the 95 was the added-fact rule applied afterwards by a script, and this is
the pipeline refusing at generation time.

## How many rows, and why not twelve

Measured yield from the 200-row run and the second pass: **0.414 three-gate rows
per generated row**. Twelve rows therefore has an EXPECTED yield of 5.0, which is
exactly the five needed — so it clears the line about 60% of the time, which is
a coin flip with a good haircut.

    n=12  expected 5.0   P(clears) = 60%
    n=18  expected 7.5   P(clears) = 92%
    n=20  expected 8.3   P(clears) = 96%
    n=24  expected 9.9   P(clears) = 99%

The default is 20. Twenty minutes of extra card time buys the difference between
a coin flip and 96% on a run whose whole purpose is to settle a threshold, and
twelve is the worst number to pick if it fails: the card is spent and the
decision is where it was.

**The expected yield is printed beside the actual one**, because a prediction
that is never checked against its outcome is a decoration.

## What it does not do

Train anything. The ruling stands: nothing trains until Max chooses among the
three options, and this run only moves which of those options is on the table.
"""

from __future__ import annotations

import argparse
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
OUT = REPO / "runs" / "more-rows"

#: Measured over the 200-row run and the second pass. Printed beside the
#: outcome so the estimate is falsifiable rather than decorative.
THE_MEASURED_YIELD = 0.414

#: What the corpus already has, and the line it fell short of.
THE_CORPUS_HAS = 95
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


def ask(system: str, user: str, deadline: float) -> str:
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
    # The deadline is passed to urlopen rather than enforced by abandoning the
    # call: a call abandoned but still running is card still spent.
    with urllib.request.urlopen(request, timeout=deadline) as response:
        payload = json.load(response)
    return ((payload.get("message") or {}).get("content") or "").strip()


def main() -> int:
    parsed = argparse.ArgumentParser(description=__doc__)
    parsed.add_argument("--rows", type=int, default=20)
    parsed.add_argument("--seed", default="more-rows-2026-09-06")
    args = parsed.parse_args()

    gate_lock = load("one_gate_at_a_time", REPO / "scripts" / "one_gate_at_a_time.py")
    the_lock = load("the_lock", REPO / "card_owner" / "the_lock.py")
    lock_log = load("the_lock_log", REPO / "card_owner" / "the_lock_log.py")
    host_of = load("the_host", REPO / "card_owner" / "the_host.py")
    driver = load("gen", REPO / "scripts" / "generate_the_preference_pairs.py")
    record = load("the_record", REPO / "card_owner" / "the_record.py")
    guarding = load("the_call_guard", REPO / "card_owner" / "the_call_guard.py")

    nightshift = the_lock.THE_LOCK.parent
    card = host_of.the_card_of()
    lock = nightshift / card.lock_name
    ledger = nightshift / "gpu.lock.log"

    if lock.exists():
        print(f"the card is held: {lock.read_text(encoding='utf-8').strip()}", file=sys.stderr)
        return 2

    mine = os.getpid()
    took_at = datetime.now(timezone.utc)
    take = (
        f"lane=mlharness host={card.host} "
        f"since={took_at.strftime('%Y-%m-%dT%H:%M:%SZ')} pid={mine} "
        f"born={gate_lock.born_when(mine)} "
        f"what={args.rows} more rows through the full pipeline, each survivor judged twice"
    )
    lock.write_text(take + "\n", encoding="utf-8")
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(lock_log.the_take_line(take) + "\n")
    print("lock:", take, flush=True)

    started = time.monotonic()
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        source = REPO / "runs" / "honest-path" / "train.jsonl"
        if not source.exists():
            print(f"{source} is not here; nothing was run.", file=sys.stderr)
            return 2

        print(f"\n--- generating {args.rows} rows, all three gates on ---", flush=True)
        report = driver.generate(
            source=source,
            out_dir=OUT,
            how_many=args.rows,
            model="granite42-hermes:latest",
            base_url="http://127.0.0.1:11434",
            seed=args.seed,
            question_field="instruction",
            answer_field="response",
            degradation=driver.DEGRADATIONS[0],
            say=lambda line: print(line, flush=True),
        )
        kept = [
            json.loads(line)
            for line in (OUT / "train.synthetic.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        print(f"\ngenerated {report['generated']}, kept after all three gates "
              f"and judge pass 1: {len(kept)}", flush=True)

        print(f"\n--- judging those {len(kept)} a second time ---", flush=True)
        results, outcomes = [], []
        the_guard = guarding.TheGuard()
        stopped_early = None
        for number, row in enumerate(kept, 1):
            shown = driver.what_the_judge_is_shown(
                question=row["prompt"], chosen=row["chosen"],
                rejected=row["rejected"], degradation=driver.DEGRADATIONS[0],
            )
            try:
                outcome = the_guard.call(
                    lambda deadline: ask(driver.JUDGE_SYSTEM, shown, deadline)
                )
            except guarding.TheRunMustStop as stop:
                # The rows already made are written and counted against the
                # number requested. Stopping is not an excuse for a short record.
                stopped_early = str(stop)
                print(f"    [{number}] RUN STOPPED: {stop}", flush=True)
                break
            if outcome.answered:
                read = driver.read_the_judges_verdict(outcome.answer)
                results.append({**row, "run1": "KEEP",
                                "run2": None if read is None else ("KEEP" if read else "DROP"),
                                "run2_reply": outcome.answer})
                outcomes.append({"outcome": record.ANSWERED})
            else:
                results.append({**row, "run1": "KEEP", "run2": None})
                outcomes.append(record.an_aborted_row(number - 1, outcome.failed_because))
                print(f"    [{number}] ABORTED after {outcome.attempts} attempt(s): "
                      f"{outcome.failed_because}", flush=True)
            if number % 5 == 0:
                print(f"    {number}/{len(kept)}", flush=True)

        both = [r for r in results if r["run2"] == "KEEP"]
        (OUT / "kept-by-both.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in both) + "\n",
            encoding="utf-8",
        )
        (OUT / "second-pass.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in results) + "\n",
            encoding="utf-8",
        )

        tally = record.the_tally(len(kept), outcomes)
        print(guarding.the_guard_line(the_guard))
        if stopped_early:
            print(f"THE RUN STOPPED EARLY: {stopped_early}")
        expected = args.rows * THE_MEASURED_YIELD
        total = THE_CORPUS_HAS + len(both)

        print("\n" + "=" * 68)
        print(record.the_calls_line(tally))
        red = record.why_this_record_is_red(tally)
        if red:
            print(red)
        print(f"\ngenerated                    : {args.rows}")
        print(f"survived all three gates + p1: {len(kept)}")
        print(f"survived the second pass too : {len(both)}")
        print(f"\nyield this run  : {len(both) / args.rows:.3f} three-gate rows per generated row")
        print(f"yield predicted : {THE_MEASURED_YIELD:.3f}  (expected {expected:.1f} rows, got {len(both)})")
        if args.rows:
            drift = len(both) / args.rows - THE_MEASURED_YIELD
            print(f"  the estimate was {'high' if drift < 0 else 'low'} by "
                  f"{abs(drift):.3f} per row on this draw")
        print(f"\nTHE CORPUS: {THE_CORPUS_HAS} + {len(both)} = {total} three-gate rows")
        if total >= THE_SHOWCASE_NEEDS:
            print(f"  {total} >= {THE_SHOWCASE_NEEDS}: THE LINE IS CLEARED.")
            print("  Training still waits for Max - this run moved which options")
            print("  are on the table, not the decision.")
        else:
            print(f"  {total} < {THE_SHOWCASE_NEEDS}: still short by {THE_SHOWCASE_NEEDS - total}.")
            print("  The three options stand, with option 3 now costed from two draws")
            print("  rather than one.")
        print(f"\nwall {(time.monotonic() - started) / 60:.1f} min")
        print(f"written to {OUT}")
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
