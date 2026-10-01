"""Thinking on, seeded, against the seed-only pair as control. One change.

## The one change

The seed-only pair sent `seed=20260906` and nothing else, twice, and got 72 of 72
self-agreement with **8 false keeps - the same 8 in both passes**. This run sends
the identical request plus `think`, one pass of 72. The control already
established what two passes of this configuration do, so a second pass here would
measure nothing new.

## The quantity, named before the threshold

`reasoning_tokens` present or absent per call, 0 to 72. That is the threshold
because it is what this run can settle. **The 8 is the thing worth knowing** -
whether thinking changes which rows the judge gets wrong - and it carries no
threshold, because eight false keeps in one pass is underpowered and saying so is
better than inventing a bar.

**No verdict-agreement number can be the threshold.** A seeded run agrees with
itself by construction, so an agreement bar would pass for a change that did
nothing and equally for one the judge is insensitive to. Ruled out deliberately.

## Repeatability or accuracy

Accuracy. The seed arm moved repeatability and in doing so hid the error set: a
seed removes the detector, not the defect. This is the first arm that tries to
move the thing that matters.

Registered at `docs/judge_runs/2026-09-06-registration-thinking-on.md`, with the
sequence-level kill written before any number existed.
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
OUT = REPO / "runs" / "sentinel-thinking-on"
THE_CONTROL = REPO / "runs" / "sentinel-n-pair-seed-only" / "results.jsonl"
THE_SEED = 20260906

#: Crude and stated rather than hidden: four characters to a token. The window
#: verdict multiplies by 1.3 for headroom, so the estimate only has to be in the
#: right order of magnitude to do its job.
CHARS_PER_TOKEN = 4.0
NEWLINE = chr(10)

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


def the_model_is_loaded(model: str) -> bool:
    """Is the model resident right now?

    THE DEADLOCK THIS EXISTS FOR, measured 2026-09-06. The window is read back
    from `/api/ps`, which lists only LOADED models; a model loads only when a
    call is made; and the owner refuses to call until it can read the window. So
    from cold, every one of 72 calls voided and the run sent nothing at all -
    "verify before sending" against "the window exists only once something was
    sent".

    The owner was right to refuse: an unverified window is exactly the defect it
    was built for. What it lacked was a way to get from cold to verifiable, which
    is one deliberate warm-up call, recorded as its own outcome rather than
    hidden inside the first measured one.
    """
    try:
        return any(
            loaded.get("model") == model or loaded.get("name") == model
            for loaded in (get("http://127.0.0.1:11434/api/ps").get("models") or [])
        )
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return False


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
        "options": {"num_ctx": 65536, "seed": THE_SEED},
        "think": True,
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
    # The control is the SEED-ONLY pair: same seed, no thinking, 8 false keeps,
    # the same 8 in both passes. Its run1 is the verdict this run is one change
    # away from.
    direct = {}
    if THE_CONTROL.exists():
        for line in THE_CONTROL.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                direct[r["id"]] = str(r.get("run1") or "").upper()

    if lock.exists():
        print(f"the card is held: {lock.read_text(encoding='utf-8').strip()}", file=sys.stderr)
        return 2

    mine = os.getpid()
    took_at = datetime.now(timezone.utc)
    take = (
        f"lane=mlharness host={card.host} "
        f"since={took_at.strftime('%Y-%m-%dT%H:%M:%SZ')} pid={mine} "
        f"born={gate_lock.born_when(mine)} "
f"what=THINKING ON, seed={THE_SEED}, 72 calls, the seed-only pair as control"
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

        # BREAK THE COLD-START DEADLOCK, deliberately and on the record. If the
        # model is not resident, /api/ps says nothing, the window cannot be
        # verified, and every call voids without sending - which is what
        # happened on the first attempt at this run: 72 of 72 void, zero tokens,
        # nothing measured. One warm-up call loads it. The warm-up is NOT one of
        # the 72: its verdict is discarded, it is announced, and the 72 that
        # follow are all verified against a window the runtime has stated.
        if not the_model_is_loaded(model):
            print("the model is not resident, so the window cannot be read and every "
                  "call would void. Sending ONE warm-up call, outside the 72, to load "
                  "it.", flush=True)
            try:
                the_guard.call(
                    lambda deadline: ask(model, "You are a test.", "Say OK.", deadline)
                )
            except Exception as error:  # noqa: BLE001 - reported, not swallowed
                print(f"  the warm-up failed: {error}", file=sys.stderr)
            if the_model_is_loaded(model):
                print("  loaded; the window is readable and the 72 can be verified.",
                      flush=True)
            else:
                print("  STILL NOT LOADED. The 72 will void and the run will report "
                      "that nothing was measured, which is the honest outcome.",
                      file=sys.stderr)

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

        # NOTHING MEASURED IS NOT A MEASUREMENT. The first version of this
        # report drew two confident conclusions from an empty run: with 0
        # answered calls it printed "ABSENT ON ALL ... KILL 1 fires" from 0 of 0,
        # and "FEWER FALSE KEEPS" from 0 keeps out of 0 calls against a control
        # of 8. Both are the failure this whole project is about - a zero
        # rendered as evidence - in a script whose subject is not confusing
        # absence for absence-of-evidence. The kill conditions written an hour
        # earlier to protect the sequence fired on a run that made no calls.
        if not answered:
            print(f"{NEWLINE}NOTHING WAS MEASURED: 0 of {len(results)} calls were "
                  "answered.")
            print("  No threshold is evaluated and no kill fires. A run that sent")
            print("  nothing cannot say a field is absent, cannot say the false")
            print("  keeps fell, and cannot end a sequence.")
            why = {r.get("why") for r in results if r.get("why")}
            for reason in list(why)[:2]:
                print(f"  every call: {str(reason)[:100]}")
            print(f"{NEWLINE}wall {(time.monotonic() - started)/60:.1f} min; "
                  f"written to {OUT}")
            return 2

        thinking = [r for r in answered if r.get("reasoning_tokens") is not None]
        nonzero = [r for r in thinking if r.get("reasoning_tokens")]
        print(f"{NEWLINE}THE THRESHOLD - reasoning_tokens present: "
              f"{len(thinking)} of {len(answered)} answered")
        if len(thinking) == 0:
            print("  ABSENT ON ALL. The field does not exist on this route with")
            print("  thinking on. The card owner's opening claim - that the owner")
            print("  would make the fabricating KEEPs visible as a reasoning-token")
            print("  column - is dead, and KILL 1 fires: the sequence stops here.")
        elif len(thinking) == len(answered):
            print(f"  PRESENT ON ALL ({len(nonzero)} of them non-zero).")
            if len(nonzero) == 0:
                print("  BUT EVERY VALUE IS ZERO - the registered refutation. A field")
                print("  that exists and is never populated is worse than absence,")
                print("  because a column of zeroes reads as a measurement.")
        else:
            print("  PARTIAL - present on some replies and not others. Registered in")
            print("  advance as a third finding: a field that depends on the reply is")
            print("  a different object from a field that exists.")

        control = {k: v for k, v in direct.items() if v}
        comparable = [r for r in answered if r.get("verdict") and control.get(r["id"])]
        moved = [r for r in comparable if r["verdict"] != control[r["id"]]]
        mine_keep = {r["id"] for r in answered if r.get("verdict") == "KEEP"}
        theirs_keep = {k for k, v in control.items() if v == "KEEP"}
        print(f"{NEWLINE}THE THING WORTH KNOWING - false keeps (every sentinel row "
              "should be DROP):")
        print(f"  control, seed only : {len(theirs_keep)}")
        print(f"  this run, thinking : {len(mine_keep)}")
        print(f"  same rows          : {mine_keep == theirs_keep}")
        print(f"  verdicts that moved: {len(moved)} of {len(comparable)} comparable")
        if mine_keep == theirs_keep:
            print("  KILL 2 fires: thinking changed what the runtime reports and not")
            print("  what the judge decides. This judge's errors are not attention")
            print("  errors, and a second arm asks the same question with more tokens.")
        elif len(mine_keep) >= len(theirs_keep):
            print("  KILL 3 fires: the false keeps moved to a different set rather")
            print("  than to fewer. That is variance by another door, not accuracy.")
        else:
            print("  FEWER FALSE KEEPS. The only outcome that earns a second arm, and")
            print("  that arm is a confirmation on CORPUS rows, not a third variation")
            print("  on sentinel rows.")
        print(f"{NEWLINE}No threshold is set on the false keeps: eight in one pass is")
        print("underpowered, and the sequence-level kill is what carries the decision.")

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
