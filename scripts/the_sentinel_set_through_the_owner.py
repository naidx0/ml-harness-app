"""The sentinel set through the card owner, with the direct run as its control.

## What this is, and what it is not

Every part of the card owner has been built and tested in isolation: the lock
and its recycling check, the window verdict, the record's four outcomes, the
lock log, the host field, the call guard. **Nothing has yet sent a single call
through all of them.** This does that, on the 72-row sentinel set, and reports
what the design asked to know.

The direct run already exists (`runs/judge-sentinel-n/results.jsonl`, 2026-09-05)
and is the control. This run is not repeated twice: the judge's self-agreement
is a separate measurement and its band is 44 to 58 of 72, which is what any
verdict difference here has to be read against.

## What the design asked, and what it can honestly answer

From `10-Signals/specs/design-the-card-owner.md`:

* `prompt_eval_count` on 72 of 72, within the client estimate x 1.3 on at
  least 68 - **answerable**, the runtime returns it on every chat response
* `reasoning_tokens > 0` on 72 of 72 with thinking on - **answerable only if
  the runtime exposes it**; if it does not, that is the answer and the design's
  first claim is dead, which the page already says
* the four durations on every row - **answerable**: total, load, prompt eval
  and eval durations all come back
* median owner overhead under 50 ms a call - **answerable**, measured as the
  wall the owner spends outside the call itself
* verdict agreement - **reported, not judged**. The bar of 65 of 72 was voided
  when the judge was measured agreeing with itself 52 of 72

## The window, verified rather than assumed

The defect this exists for is an HTTP 200 that silently kept 2,050 tokens of a
13,213-token prompt. So the owner does not trust that its own `num_ctx` was
applied: it reads the loaded model's `context_length` back from `/api/ps` and
hands THAT to the window verdict. A window it cannot read is `None`, and `None`
voids the call rather than passing it.

## Every call ends in exactly one of four outcomes

`answered`, `refused`, `void`, `aborted`, summing to 72 or the record is red.
A void costs zero tokens and an abort is written when it happens.
"""

from __future__ import annotations

import importlib.util
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "runs" / "sentinel-through-the-owner"
THE_DIRECT_RUN = REPO / "runs" / "judge-sentinel-n" / "results.jsonl"

#: Crude and stated rather than hidden: four characters to a token. The window
#: verdict multiplies by 1.3 for headroom, so the estimate only has to be in the
#: right order of magnitude to do its job.
CHARS_PER_TOKEN = 4.0

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


def get(url: str, timeout: float = 30.0):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def the_window_the_runtime_applied(model: str) -> int | None:
    """The loaded model's context length, read back rather than assumed.

    None when the model is not loaded or the runtime does not say - and None
    voids the call, which is the whole point.
    """
    try:
        for loaded in (get("http://127.0.0.1:11434/api/ps").get("models") or []):
            if loaded.get("model") == model or loaded.get("name") == model:
                window = loaded.get("context_length")
                return int(window) if isinstance(window, int) and window > 0 else None
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return None
    return None


def ask(model: str, system: str, user: str, deadline: float) -> dict:
    body = {
        "model": model, "stream": False,
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
    with urllib.request.urlopen(request, timeout=deadline) as response:
        return json.load(response)


def main() -> int:
    model = "granite42-hermes:latest"
    gate_lock = load("one_gate_at_a_time", REPO / "scripts" / "one_gate_at_a_time.py")
    the_lock = load("the_lock", REPO / "card_owner" / "the_lock.py")
    lock_log = load("the_lock_log", REPO / "card_owner" / "the_lock_log.py")
    host_of = load("the_host", REPO / "card_owner" / "the_host.py")
    window_of = load("the_window", REPO / "card_owner" / "the_window.py")
    record = load("the_record", REPO / "card_owner" / "the_record.py")
    guarding = load("the_call_guard", REPO / "card_owner" / "the_call_guard.py")
    driver = load("gen", REPO / "scripts" / "generate_the_preference_pairs.py")

    nightshift = the_lock.THE_LOCK.parent
    card = host_of.the_card_of()
    lock = nightshift / card.lock_name
    ledger = nightshift / "gpu.lock.log"

    rows_file = (
        nightshift.parent / "10-Signals" / "specs" / "evidence"
        / "sentinel-N-2026-09-05" / "sentinel-N.jsonl"
    )
    if not rows_file.exists():
        print(f"{rows_file} is not here; nothing was run.", file=sys.stderr)
        return 2
    rows = [json.loads(l) for l in rows_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    if len(rows) != 72:
        print(f"expected 72 sentinel rows, found {len(rows)}; nothing was run.", file=sys.stderr)
        return 2
    direct = {}
    if THE_DIRECT_RUN.exists():
        for line in THE_DIRECT_RUN.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                direct[r["id"]] = str(r.get("got", "")).upper()

    if lock.exists():
        print(f"the card is held: {lock.read_text(encoding='utf-8').strip()}", file=sys.stderr)
        return 2

    mine = os.getpid()
    took_at = datetime.now(timezone.utc)
    take = (
        f"lane=mlharness host={card.host} "
        f"since={took_at.strftime('%Y-%m-%dT%H:%M:%SZ')} pid={mine} "
        f"born={gate_lock.born_when(mine)} "
        "what=the sentinel set through the card owner, 72 calls, direct run as control"
    )
    lock.write_text(take + "\n", encoding="utf-8")
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(lock_log.the_take_line(take) + "\n")
    print("lock:", take, flush=True)

    started = time.monotonic()
    try:
        the_guard = guarding.TheGuard()
        results, outcomes, overheads = [], [], []
        stopped = None

        for number, row in enumerate(rows, 1):
            # `perf_counter`, not `monotonic`. MEASURED: monotonic's resolution
            # on this machine is 15.625 ms, so the owner's overhead - which is
            # well under a millisecond - reported as a median of 0.0 ms on the
            # first run. That is the clock, not the measurement, and "0.0 ms"
            # printed beside a 50 ms bar is a pass that measured nothing.
            owner_started = time.perf_counter()
            shown = driver.what_the_judge_is_shown(
                question=row["instruction"], chosen=row["real"],
                rejected=row["rewrite"], degradation=driver.DEGRADATIONS[0],
            )
            estimated = int((len(driver.JUDGE_SYSTEM) + len(shown)) / CHARS_PER_TOKEN)
            applied = the_window_the_runtime_applied(model)
            verdict = window_of.the_window_verdict(estimated, applied)

            base = {
                "id": row.get("id", number - 1),
                "estimated_tokens": estimated,
                "window_applied": applied,
                "window_void": verdict.void,
            }
            if verdict.void:
                overheads.append(time.perf_counter() - owner_started)
                results.append({**base, "outcome": record.VOID, "why": verdict.reason})
                outcomes.append({"outcome": record.VOID})
                print(f"    [{number}] VOID: {verdict.reason[:70]}", flush=True)
                continue

            overhead = time.perf_counter() - owner_started
            try:
                got = the_guard.call(lambda deadline: ask(model, driver.JUDGE_SYSTEM, shown, deadline))
            except guarding.TheRunMustStop as stop:
                stopped = str(stop)
                print(f"    [{number}] RUN STOPPED: {stop}", flush=True)
                break
            overheads.append(overhead)

            if not got.answered:
                results.append({**base, "outcome": record.ABORTED, "why": got.failed_because})
                outcomes.append(record.an_aborted_row(number - 1, got.failed_because))
                print(f"    [{number}] ABORTED: {got.failed_because}", flush=True)
                continue

            payload = got.answer
            reply = ((payload.get("message") or {}).get("content") or "").strip()
            read = driver.read_the_judges_verdict(reply)
            results.append({
                **base,
                "outcome": record.ANSWERED,
                "verdict": None if read is None else ("KEEP" if read else "DROP"),
                "direct_verdict": direct.get(row.get("id", number - 1)),
                "prompt_eval_count": payload.get("prompt_eval_count"),
                "eval_count": payload.get("eval_count"),
                "total_duration": payload.get("total_duration"),
                "load_duration": payload.get("load_duration"),
                "prompt_eval_duration": payload.get("prompt_eval_duration"),
                "eval_duration": payload.get("eval_duration"),
                "reasoning_tokens": payload.get("reasoning_tokens"),
                "attempts": got.attempts,
            })
            outcomes.append({"outcome": record.ANSWERED})
            if number % 12 == 0:
                print(f"    {number}/72", flush=True)

        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "results.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in results) + "\n",
            encoding="utf-8",
        )

        tally = record.the_tally(72, outcomes)
        answered = [r for r in results if r.get("outcome") == record.ANSWERED]
        print("\n" + "=" * 68)
        print(record.the_calls_line(tally))
        red = record.why_this_record_is_red(tally)
        if red:
            print(red)
        if stopped:
            print(f"THE RUN STOPPED EARLY: {stopped}")
        print(guarding.the_guard_line(the_guard))

        have_count = [r for r in answered if isinstance(r.get("prompt_eval_count"), int)]
        print(f"\nprompt_eval_count present : {len(have_count)} of {len(answered)} answered")
        within = [r for r in have_count if r["prompt_eval_count"] <= r["estimated_tokens"] * 1.3]
        print(f"  within the estimate x1.3: {len(within)} of {len(have_count)}  (design asked 68 of 72)")

        thinking = [r for r in answered if r.get("reasoning_tokens")]
        print(f"reasoning_tokens > 0      : {len(thinking)} of {len(answered)}")
        if not thinking:
            print("  THE RUNTIME DOES NOT EXPOSE IT on this route. The design's first")
            print("  claim rests on a field that is not there, and this is the answer.")

        four = [r for r in answered if all(
            isinstance(r.get(k), int)
            for k in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration")
        )]
        print(f"all four durations        : {len(four)} of {len(answered)}")

        if overheads:
            print(f"owner overhead            : median "
                  f"{statistics.median(overheads)*1000:.2f} ms, max "
                  f"{max(overheads)*1000:.2f} ms (design asked under 50 ms)")

        windows = {r.get("window_applied") for r in results}
        print(f"windows read back         : {sorted(w for w in windows if w)} "
              f"| unreadable on {sum(1 for r in results if r.get('window_applied') is None)} row(s)")

        comparable = [r for r in answered if r.get("verdict") and r.get("direct_verdict")]
        agreed = sum(1 for r in comparable if r["verdict"] == r["direct_verdict"])
        print(f"\nverdicts vs the direct run: {agreed} of {len(comparable)} comparable")
        print("  READ AGAINST THE JUDGE'S OWN BAND, 44 to 58 of 72. Inside it, the")
        print("  owner is indistinguishable from the instrument; the 65-of-72 bar was")
        print("  voided when the judge was measured agreeing with itself 52 of 72.")
        print(f"\nwall {(time.monotonic() - started)/60:.1f} min; written to {OUT}")
        return 0 if not red else 1
    finally:
        released_at = datetime.now(timezone.utc)
        held = (released_at - took_at).total_seconds()
        try:
            with ledger.open("a", encoding="utf-8") as fh:
                fh.write(lock_log.the_release_line("mlharness", released_at, held) + "\n")
            lock.unlink()
            print(f"LOCK RELEASED after {held/60:.1f} min", flush=True)
        except OSError as error:
            print(f"could not release cleanly: {error}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
