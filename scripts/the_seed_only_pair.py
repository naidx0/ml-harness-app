"""The sentinel pair with a seed and NO temperature. The last one-change run.

## The one thing it decides

Temperature 0 was shown to hang this runtime: 4 hangs in 30 calls with no seed,
against 0 in 834 with neither parameter. What no run has done is send a SEED
without a temperature. Equal rates in the two arms that hung are consistent with
temperature being the whole cause, and equally consistent with a seed that does
nothing while temperature is already doing it.

    default (no seed, no temperature)   834 calls,  0 hangs
    seed + temperature 0                 64 calls,  9 hangs
    temperature 0, no seed               30 calls,  4 hangs
    a seed, no temperature                    THIS RUN

**Registered predictions**, before any call: hangs in the default band, 0 to 1
in 144. If a seed alone hangs at anything near 0.13, it is a second independent
cause and both parameters are unusable. Self-agreement between 44 and 58 of 72 -
and if a seed alone RAISES agreement above 58, that is the repeatability the
seeded pair was looking for, obtainable without the parameter that hangs.

**Refuted if** hangs exceed 1 in 144, or agreement exceeds 58.

## The stop rule, learned the hard way

**Stop if hangs reach 1 in 20 over the first 40 calls.** The temperature-only
pair's agreement half was unobtainable the moment its hang rate held: every hung
row is excluded from the comparable count, so a pair losing one call in seven
can never produce a number against the 44-to-58 band however long it runs. That
registration predicted a condition under which its own second prediction could
not be tested, and did not notice. This one stops instead of spending two hours
proving it again.

Registered in `docs/judge_runs/2026-09-06-two-registrations-one-change-each.md`
and `2026-09-06-temperature-is-what-hangs-the-runtime.md`.
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
NEWLINE = chr(10)
THE_UNSEEDED_BAND = (44, 58)

#: A SEED AND NO TEMPERATURE. The one combination never sent, and the only one
#: that can say whether a seed alone is harmless.
THE_SEED = 20260906

#: Registered before the run: stop if hangs reach 1 in 20 once this many
#: calls have been made.
THE_STOP_RULE_AFTER = 40

#: The control, measured over two days of this lane's calls.
THE_UNSEEDED_HANGS, THE_UNSEEDED_CALLS = 0, 834
THE_SEEDED_HANGS, THE_SEEDED_CALLS = 9, 64
#: Where 144 calls would land under each explanation. Non-overlapping on purpose.
IF_TEMPERATURE_IS_RESPONSIBLE = (11, 35)
IF_THE_SEED_IS_RESPONSIBLE = (0, 1)

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
    """One judge call, with the seed and temperature this run is about."""
    body = {
        "model": "granite42-hermes:latest",
        "stream": False,
        "options": {"num_ctx": 65536, "seed": THE_SEED},
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
    with urllib.request.urlopen(request, timeout=deadline) as response:
        payload = json.load(response)
    return ((payload.get("message") or {}).get("content") or "").strip()


def main() -> int:
    gate_lock = load("one_gate_at_a_time", REPO / "scripts" / "one_gate_at_a_time.py")
    the_lock = load("the_lock", REPO / "card_owner" / "the_lock.py")
    lock_log = load("the_lock_log", REPO / "card_owner" / "the_lock_log.py")
    host_of = load("the_host", REPO / "card_owner" / "the_host.py")
    driver = load("gen", REPO / "scripts" / "generate_the_preference_pairs.py")
    record = load("the_record", REPO / "card_owner" / "the_record.py")
    guarding = load("the_call_guard", REPO / "card_owner" / "the_call_guard.py")

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
        f"what=the SEED-ONLY sentinel pair, seed={THE_SEED} and no temperature, 144 calls"
    )
    lock.write_text(take + "\n", encoding="utf-8")
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(lock_log.the_take_line(take) + "\n")
    print("lock:", take, flush=True)

    started = time.monotonic()
    try:
        the_guard = guarding.TheGuard()
        stopped = None
        runs: list[list[str | None]] = []
        outcomes: list[dict] = []
        for attempt in (1, 2):
            if stopped:
                # THE LINE THAT WENT MISSING. A patch used `replace` without
                # asserting the anchor matched, so this guard - and the
                # progress label below - were silently dropped. Run 1 would
                # stop on two consecutive failures and run 2 would start
                # anyway, spending 72 more calls on a run already declared
                # over. Caught by auditing the patch, not by the run.
                break
            print(f"{NEWLINE}--- seed-only run {attempt} of 2, same "
                  f"{THE_ROWS} rows, a seed and no temperature ---", flush=True)
            verdicts: list[str | None] = []
            for number, row in enumerate(rows, 1):
                shown = driver.what_the_judge_is_shown(
                    question=row["instruction"],
                    chosen=row["real"],
                    rejected=row["rewrite"],
                    degradation=driver.DEGRADATIONS[0],
                )
                try:
                    got = the_guard.call(
                        lambda deadline: ask(driver.JUDGE_SYSTEM, shown, deadline)
                    )
                except guarding.TheRunMustStop as stop:
                    print(f"    [{attempt}:{number}] RUN STOPPED: {stop}", flush=True)
                    stopped = str(stop)
                    break
                if got.answered:
                    read = driver.read_the_judges_verdict(got.answer)
                    verdicts.append(None if read is None else ("KEEP" if read else "DROP"))
                    outcomes.append({"outcome": record.ANSWERED})
                else:
                    verdicts.append(None)
                    outcomes.append(record.an_aborted_row(number - 1, got.failed_because))
                    print(f"    [{attempt}:{number}] ABORTED after {got.attempts} "
                          f"attempt(s): {got.failed_because}", flush=True)
                # THE REGISTERED STOP RULE: 1 hang in 20 over the first 40
                # calls. Past that rate the agreement half is already
                # unobtainable - every hung row leaves the comparable count -
                # so the remaining calls buy nothing. The temperature-only pair
                # learned this by spending 30 calls proving it.
                made = len(outcomes)
                if made >= THE_STOP_RULE_AFTER and the_guard.hangs * 20 >= made:
                    stopped = (
                        f"the registered stop rule: {the_guard.hangs} hang(s) in "
                        f"{made} calls is at or past 1 in 20, so the agreement "
                        "number is already unobtainable and the rest of the run "
                        "buys nothing"
                    )
                    print(f"    [{attempt}:{number}] STOPPING: {stopped}", flush=True)
                    break

                if number % 12 == 0:
                    print(f"    {number}/{THE_ROWS}", flush=True)
            runs.append(verdicts)

        first, second = runs
        out = REPO / "runs" / "sentinel-n-pair-seed-only"
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

        low_w, high_w = evals.wilson(agreed, len(comparable)) if comparable else (0.0, 0.0)

        hangs = the_guard.hangs
        print(NEWLINE + "=" * 68)
        print(f"HANGS: {hangs} in {len(outcomes)} calls"
              f"   |   unseeded control: {THE_UNSEEDED_HANGS} in {THE_UNSEEDED_CALLS}"
              f"   |   seeded: {THE_SEEDED_HANGS} in {THE_SEEDED_CALLS}")
        rate = hangs / len(outcomes) if outcomes else 0.0
        per144 = rate * 144
        if hangs <= 1 and len(outcomes) >= 100:
            print("  IN THE DEFAULT BAND: a seed alone is harmless. Temperature is")
            print("  the whole cause, and a caller may send a seed without it.")
        elif rate >= 0.05:
            print("  A SEED ALONE HANGS TOO: a second independent cause, and BOTH")
            print("  parameters are unusable on this wire. The registered refutation.")
        else:
            print("  Between the bands, or too few calls to say. The number and its")
            print("  interval are the report; no verdict is claimed.")
        print(f"  rate {rate:.3f} = {per144:.1f} per 144; registered: 0-1 per 144 if")
        print(f"  the seed is harmless, refuted above 1")
        print(f"  {guarding.the_guard_line(the_guard)}")
        if stopped:
            print(f"  THE RUN STOPPED EARLY: {stopped}")

        print()
        print(record.the_calls_line(tally))
        red = record.why_this_record_is_red(tally)
        if red:
            print(red)
        print(
            f"{NEWLINE}A SEED, NO TEMPERATURE: {agreed} of {len(comparable)} "
            f"comparable rows agree   Wilson {low_w:.2f} - {high_w:.2f}"
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
        if THE_UNSEEDED_BAND[0] <= agreed <= THE_UNSEEDED_BAND[1]:
            print("  Inside the band: temperature 0 does not move the verdict, as")
            print("  registered.")
        elif agreed > THE_UNSEEDED_BAND[1]:
            # INHERITED TEXT, CORRECTED. This branch was copied from the
            # temperature-only runner, where agreement above the band would have
            # meant temperature was moving the verdict. In THIS arm it means the
            # opposite and better thing, which the registration named in advance.
            print("  ABOVE the band. A SEED ALONE MAKES THE JUDGE REPEATABLE -")
            print("  the registration's named better-than-expected outcome, and it")
            print("  needs its own confirmation before anything relies on it. The")
            print("  44-to-58 band describes UNSEEDED calls and nothing else.")
        else:
            print("  BELOW the band, which nothing predicted. The number and its")
            print("  interval are the report; no verdict is claimed.")
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
