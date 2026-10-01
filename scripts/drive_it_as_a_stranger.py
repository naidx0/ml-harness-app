"""Drive the harness as a stranger would, through the engine API, and record it.

    python scripts/drive_it_as_a_stranger.py <transcript.json> <provider_id> [what]

Takes the card through `scripts/take_the_card.py` so the take and the release
both reach `gpu.lock.log`, records `ollama ps` and THE RUNNING ENGINE'S OWN
IDENTITY, runs the conversation, releases. Writes a JSON transcript for a report
to be built from by hand - the report is written from this, never generated.

## Why this is a script and not four curl commands

`docs/readiness-rehearsal-2026-09-11.md` was driven by a throwaway that lived in
a scratchpad, and everything it got wrong came from that:

* it hand-rolled the lock protocol and appended NOTHING to `gpu.lock.log`, which
  the 00:30 amendment requires of every writer, and the report then said "the
  lock protocol worked";
* it recorded the CHECKOUT's HEAD as the "engine build" and the process on 8078
  had been running twelve hours older code, which withdrew one of the report's
  four findings once somebody checked;
* and it was not in the repository, so the measurement could not be repeated by
  anybody but the person who still had the file.

A measurement nobody else can take is not a measurement. This is that script,
with those three faults fixed, in the tree.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app import security  # noqa: E402 - after the path is set


def _the_card() -> Path:
    """`gpu.lock`, wherever the card owner says it lives.

    ASKED FOR, NOT SPELLED OUT. The scratchpad version pasted a real home
    directory and the name of a private note vault, which is exactly what
    `test_no_shipped_file_names_a_person` exists to refuse. `card_owner/the_lock.py`
    already resolves that directory; two definitions of one directory is how
    they drift, and one of them being in a shipped file is how a private path
    escapes.

    `MLH_STRANGER_LOCK` overrides, for a machine arranged differently and for
    the tests.
    """
    named = os.environ.get("MLH_STRANGER_LOCK")
    if named:
        return Path(named)
    from card_owner.the_lock import THE_LOCK

    return THE_LOCK


def _the_engine_database() -> Path:
    """The database the ENGINE writes to, which is not this checkout's.

    MEASURED 2026-09-11 03:38, before it produced a false measurement. Run from
    the intake worktree, this script resolved `app.db.DB_PATH` to that
    worktree's own `ml_harness.db` - a file that does not exist - so
    `events.since` would have returned nothing for every turn and the transcript
    would have recorded four turns with empty event lists. Not a crash: a
    confident, silent nothing, in the file a report gets written from. The
    portfile had the same fault an hour earlier and I fixed that one without
    asking what else in here assumed this checkout was the engine's.

    `ML_HARNESS_DB` is `app.db`'s own override and stays the first word.
    Failing that the database sits beside the engine. If it is not there this
    REFUSES rather than opening an empty one, by the same rule as the portfile:
    a driver that cannot see the engine must not take the card.
    """
    named = os.environ.get("ML_HARNESS_DB")
    candidate = Path(named) if named else (ENGINE_CHECKOUT or REPO) / "ml_harness.db"
    if candidate.exists():
        return candidate
    raise SystemExit(
        "REFUSED before taking the card: no engine database at " + str(candidate)
        + ". A run recorded against a database the engine does not write to "
        "comes back empty and looks like a quiet conversation. Name it with "
        "ML_HARNESS_DB, or run this from the checkout the engine serves from."
    )


#: RESOLVED IN `main`, NOT AT IMPORT, and the tests are the reason but not the
#: only one. A module that reads `sys.argv` and opens a portfile while it is
#: being imported cannot be imported by a test, cannot be imported by a tool
#: that lists what this repository ships, and does its filesystem work during
#: collection of a five-thousand-test suite. The first version of this did all
#: three, and the test written to hold its honest-default behaviour could not
#: load it.
LOCK: Path | None = None
LEDGER: Path | None = None
OUT: Path | None = None
MODEL_PROVIDER_ID: int | None = None
WHAT = "driving the harness as a stranger"
PORT: dict | None = None


def settle(argv: list[str]) -> None:
    """Read the arguments and find the engine. Called by `main`, and by nothing
    else - every other function here takes what it needs from these globals
    once they are set."""
    global LOCK, LEDGER, OUT, MODEL_PROVIDER_ID, WHAT, PORT
    OUT = Path(argv[0])
    MODEL_PROVIDER_ID = int(argv[1])
    if len(argv) > 2:
        WHAT = argv[2]
    LOCK = _the_card()
    LEDGER = card.the_log_beside(LOCK)
    PORT = _the_running_engine()
    #: ASSIGNED, NOT SET IN THE ENVIRONMENT. `app.security` imports `app.db`,
    #: so by the time this runs `DB_PATH` has already been resolved from
    #: `ML_HARNESS_DB` and putting a value there now would be read by nobody.
    #: `db.connect()` reads the global on every call, so the global is the seam
    #: that still works this late.
    from app import db as engine_db

    engine_db.DB_PATH = _the_engine_database()

#: The checkout the engine actually serves from, set by `_the_running_engine`.
ENGINE_CHECKOUT: Path | None = None


def _the_running_engine() -> dict:
    """Where the engine is listening, or a refusal that says where it looked.

    `read_portfile()` resolves against THIS checkout, and this script is meant
    to be run from a worktree while the engine serves from the checkout the
    worktrees hang off. A worktree has no portfile, so the first version of this
    took the card, then died on `None["port"]` - holding the GPU and leaving a
    lock line behind for somebody else to clean up.

    So this is asked BEFORE the card is taken, and it refuses rather than
    guesses. `MLH_ENGINE_PORTFILE` names one explicitly.
    """
    global ENGINE_CHECKOUT
    named = os.environ.get("MLH_ENGINE_PORTFILE")
    if named:
        ENGINE_CHECKOUT = Path(named).resolve().parent
        return json.loads(Path(named).read_text(encoding="utf-8"))
    found = security.read_portfile()
    if found:
        ENGINE_CHECKOUT = REPO
        return found
    #: The checkout a worktree hangs off, which is where the engine serves from.
    common = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "--path-format=absolute",
         "--git-common-dir"],
        capture_output=True, text=True,
    )
    if common.returncode == 0 and common.stdout.strip():
        beside = Path(common.stdout.strip()).parent
        if beside != REPO:
            sys.path.insert(0, str(beside))
            for name in ("engine.json", ".engine.json", "engine-port.json"):
                candidate = beside / name
                if candidate.exists():
                    ENGINE_CHECKOUT = beside
                    return json.loads(candidate.read_text(encoding="utf-8"))
    raise SystemExit(
        "REFUSED before taking the card: no engine portfile in " + str(REPO)
        + ". This checkout is probably a worktree and the engine serves from "
        "the checkout it hangs off. Run it from there, or name the portfile "
        "with MLH_ENGINE_PORTFILE."
    )


def api(path: str, method: str = "GET", body: dict | None = None, timeout: float = 900.0):
    request = urllib.request.Request(
        f"http://127.0.0.1:{PORT['port']}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {PORT['token']}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout) as answer:
        return json.load(answer)


def ollama_ps() -> str:
    try:
        done = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=60)
        return (done.stdout or done.stderr or "").strip()
    except Exception as error:  # noqa: BLE001
        return f"could not run ollama ps: {error}"


#: THE LEDGER IS NOT OPTIONAL, and the first version of this driver proved it
#: by leaving no trace. It wrote `gpu.lock` and released it, and appended
#: NOTHING to `gpu.lock.log` - which the 00:30 amendment (`GPU LOCK.md` line
#: 114) requires of every writer. The rehearsal report then said "the lock
#: protocol worked". It did not: the take is not in the ledger and cannot be
#: put there now, because a back-filled line is a line a reader has to trust
#: rather than read.
#:
#: So this no longer hand-rolls the protocol. `scripts/take_the_card.py` is the
#: writer the protocol is defined by - `the_line` for the take, `the_log_beside`
#: for where the ledger lives, `held_seconds` measured by the process that did
#: the holding, `the_release_line` for the way out - and it is tested
#: (`tests/test_the_card_lock_writes_a_ledger.py`). A second implementation of a
#: protocol is a second thing that can drift from it.
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "take_the_card", REPO / "scripts" / "take_the_card.py"
)
card = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(card)

LANE = os.environ.get("MLH_LANE", "intake")


def take_the_lock() -> str:
    if LOCK.exists():
        held = LOCK.read_text(encoding="utf-8").strip()
        raise SystemExit(f"REFUSED: the card is held.\n  {held}")
    line = card.the_line(LANE, WHAT)
    LOCK.write_text(line + "\n", encoding="utf-8")
    if not card.append(LEDGER, line):
        # Loud, and then on with it: `append` has already said why on stderr,
        # and a rehearsal refused because a log file would not open is a worse
        # outcome than a missing line. The run records the failure in its own
        # transcript so the report cannot claim a ledger entry that is not there.
        print("LEDGER: the take line did NOT land", flush=True)
    return line


def release_the_lock(line: str | None) -> None:
    """Release, and say so in the ledger.

    The span is written by the process that held the card because that process
    knows it. A reader can only infer it from two whole-second stamps, and the
    protocol has the reader recompute and REPORT a disagreement rather than
    correct either number - which only works if the writer writes what it
    measured.
    """
    try:
        mine = LOCK.exists() and f"pid={os.getpid()} " in LOCK.read_text(encoding="utf-8")
    except OSError:
        mine = False
    if not mine:
        return
    try:
        LOCK.unlink()
    except OSError:
        return
    held = card.held_seconds(line) if line else None
    if held is None:
        # A release line carrying a zero that means "could not tell" is a silent
        # subtraction from the night's total. Say nothing rather than say zero.
        print("LEDGER: no readable since=, so no release line", flush=True)
        return
    card.append(LEDGER, card.the_release_line(LANE, held))


#: WHAT CODE IS ACTUALLY RUNNING, which is not the same question as what is
#: checked out and the first version of this driver confused them.
#:
#: `docs/readiness-rehearsal-2026-09-11.md` recorded "engine build b17f320
#: (clean)" and meant the CHECKOUT's HEAD. The engine process on 8078 started
#: 2026-09-10 02:43:02 with no --reload and has held that code ever since;
#: `a443add` landed `assess_the_data`'s no-path affordance at 15:21 the same
#: day. So the report's stall 3 - "the affordance exists and the route to it
#: does not" - was written about a tree, and the stranger drove a process where
#: `path` was still REQUIRED. The model could not have called the tool it was
#: blamed for not calling.
#:
#: A rehearsal against stale code produces findings about a product that does
#: not exist. This does not stop the run - restarting the engine is not this
#: driver's business and 8078 is guarded - but it measures the gap and puts it
#: in the transcript, so no report can claim a build it did not drive.
ENGINE_PORT_IN_THE_CHARTER = 8078


def what_the_engine_is_running() -> dict:
    """The running process's identity, and how far the checkout has moved past it."""
    found: dict = {"port": PORT["port"], "pid": None, "started": None,
                   "head": None, "commits_since_the_engine_started": None,
                   "behind_its_own_checkout": None, "behind_the_remote": None,
                   "checkout": None,
                   "behind": None}
    try:
        done = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             f"Where-Object {{ $_.CommandLine -like '*{PORT['port']}*' }} | "
             #: FORMATTED IN POWERSHELL, because `ConvertTo-Json` renders a
             #: CimInstance DateTime as `/Date(1789022582307)/` and the first
             #: version of this handed that string to `git log --since=` and
             #: got nothing, which reads exactly like "the engine is level".
             "Select-Object -First 1 ProcessId,"
             "@{n='Started';e={$_.CreationDate.ToString('yyyy-MM-dd HH:mm:ss')}} "
             "| ConvertTo-Json"],
            capture_output=True, text=True, timeout=60,
        )
        row = json.loads(done.stdout or "{}")
        found["pid"] = row.get("ProcessId")
        started = row.get("Started")
        if isinstance(started, str):
            found["started"] = started
    except Exception as error:  # noqa: BLE001
        found["started"] = f"could not read the process table: {error}"

    try:
        found["head"] = subprocess.run(
            ["git", "-C", str(ENGINE_CHECKOUT or REPO), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=60,
        ).stdout.strip() or None
    except Exception:  # noqa: BLE001
        pass

    #: THE NUMBER THAT MATTERS, AND IT IS MEASURED AGAINST `origin/main`
    #: RATHER THAN HEAD. The first version asked HEAD and answered 12; the true
    #: figure was 27. The checkout the engine runs from was itself 15 commits
    #: behind the remote, so `a443add` - the very commit that makes stall 3's
    #: diagnosis wrong - was invisible to the check written to find it. A
    #: staleness check that reads a stale reference reports the smaller of two
    #: gaps and calls it the gap.
    #:
    #: Both are reported, because they are different facts about different
    #: problems: `behind_the_checkout` is code somebody pulled and did not
    #: restart into, `behind_the_remote` is everything the product has become.
    stamp = found.get("started")
    if isinstance(stamp, str) and stamp[:4].isdigit():
        try:
            #: MEASURED AGAINST THE CHECKOUT THE ENGINE SERVES FROM, not
            #: against this one. A worktree's HEAD says nothing about what a
            #: restart would load, and reporting it would answer a question
            #: nobody asked with a number that looks like the answer.
            where = ENGINE_CHECKOUT or REPO
            for key, ref in (("behind_its_own_checkout", None), ("behind_the_remote", "origin/main")):
                done = subprocess.run(
                    ["git", "-C", str(where), "log", "--oneline", f"--since={stamp}"]
                    + ([ref] if ref else []) + ["--", "app/"],
                    capture_output=True, text=True, timeout=120,
                )
                if done.returncode != 0:
                    continue
                rows = [r for r in (done.stdout or "").splitlines() if r.strip()]
                found[key] = len(rows)
                if ref:
                    found["commits_since_the_engine_started"] = rows
        except Exception:  # noqa: BLE001
            pass
    #: The remote is the honest answer where both are known; where only one is,
    #: it is that one; where neither, None - which renders "unknown", never 0.
    found["checkout"] = str(ENGINE_CHECKOUT or REPO)
    found["behind"] = (
        found.get("behind_the_remote")
        if found.get("behind_the_remote") is not None
        else found.get("behind_its_own_checkout")
    )
    return found


def say_how_stale_the_engine_is(found: dict) -> None:
    behind = found.get("behind")
    if behind:
        here = found.get("behind_its_own_checkout")
        print(f"ENGINE IS BEHIND origin/main BY {behind} COMMIT(S) TO app/"
              + (f" ({here} of them already pulled into {found.get('checkout')} "
                 "and simply not restarted into)" if here is not None else "")
              + " - every product-caused finding below is about the code this "
              "process is running, not about the tree:", flush=True)
        for row in (found.get("commits_since_the_engine_started") or [])[:10]:
            print("   ", row, flush=True)
    elif behind == 0:
        print("engine is level with origin/main on app/", flush=True)
    else:
        #: UNKNOWN IS NOT ZERO, and the wording has to keep them apart at a
        #: glance. A reader skimming a run record for "is this current?" must
        #: not find a sentence that reads as a clean bill of health because the
        #: process table would not answer.
        print("could not tell how far behind the engine is - that is unknown, "
              "and a finding from this run cannot be said to be about current "
              "code", flush=True)


#: What a stranger types, in their own words. Four turns, following the
#: product's own route: what should I do -> the data -> which method -> will it
#: run here.
THE_CONVERSATION = [
    "I want a model that draws system-design JSON graphs from a description. "
    "Here is one example: {\"nodes\": [{\"id\": \"api\", \"kind\": \"service\"}, "
    "{\"id\": \"db\", \"kind\": \"store\"}], \"edges\": [[\"api\", \"db\"]]}. "
    "What should I do?",
    "I have about 400 examples like that. Where do I put them so you can see them?",
    "Should I fine-tune the whole model or use LoRA?",
    "Will that actually run on this machine?",
]


def events_since(thread_id: int, since: int) -> list[dict]:
    """Read the rows, not the stream.

    The events endpoint is an SSE StreamingResponse - the first version of this
    it for JSON and died on the first frame, after the turn had already run. The
    events table is the durable half the stream is a view of, and the whole
    point of that design is that a reader can take it directly.
    """
    from app import events as event_log

    return [
        row for row in event_log.since(f"thread:{thread_id}", after=since, limit=2000)
    ]


def main(argv: list[str] | None = None) -> int:
    settle(list(sys.argv[1:] if argv is None else argv))
    record: dict = {
        "started": datetime.now(timezone.utc).isoformat(),
        "provider_id": MODEL_PROVIDER_ID,
        "ollama_ps_at_take": None,
        "lock_line": None,
        "turns": [],
    }
    record["lock_line"] = take_the_lock()
    record["ledger"] = str(LEDGER)
    record["engine"] = what_the_engine_is_running()
    record["ollama_ps_at_take"] = ollama_ps()
    print("LOCK:", record["lock_line"], flush=True)
    print("OLLAMA PS AT TAKE:", record["ollama_ps_at_take"], flush=True)
    say_how_stale_the_engine_is(record["engine"])

    try:
        thread = api("/api/threads", "POST", {"title": "readiness rehearsal"})
        thread_id = int(thread["id"])
        record["thread_id"] = thread_id
        print("thread", thread_id, flush=True)

        last = 0
        for n, said in enumerate(THE_CONVERSATION, 1):
            print(f"--- turn {n} ---", flush=True)
            api(f"/api/threads/{thread_id}/messages", "POST",
                {"role": "user", "content": said})
            began = time.time()
            try:
                written = api(
                    f"/api/threads/{thread_id}/turn", "POST",
                    {"provider_id": MODEL_PROVIDER_ID},
                )
                error = None
            except Exception as problem:  # noqa: BLE001
                written, error = None, f"{type(problem).__name__}: {problem}"
            took = round(time.time() - began, 1)
            rows = events_since(thread_id, last)
            if rows:
                last = max(int(r.get("id") or 0) for r in rows)
            record["turns"].append(
                {
                    "n": n,
                    "user_said": said,
                    "seconds": took,
                    "error": error,
                    "events": rows,
                }
            )
            print(f"    {took}s, {len(rows)} events, error={error}", flush=True)
            OUT.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    finally:
        try:
            record["export"] = api(f"/api/threads/{record.get('thread_id')}/export")
        except Exception as problem:  # noqa: BLE001
            record["export_error"] = f"{type(problem).__name__}: {problem}"
        record["ollama_ps_at_release"] = ollama_ps()
        record["finished"] = datetime.now(timezone.utc).isoformat()
        OUT.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
        release_the_lock(record.get("lock_line"))
        print("lock released", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
