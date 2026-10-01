"""Restart the engine, but only when restarting it costs nobody anything.

    python scripts/restart_engine_when_idle.py            # guards, then act
    python scripts/restart_engine_when_idle.py --dry-run  # guards only

## Why a script and not a command somebody types

A long-lived engine serves the build it started with. Measured 2026-09-10: the
engine on 8078 reported `build.sha da203bb` and `dirty: true` while main had
moved many commits past it, so a walk recorded through it described a tree that
had not existed for hours - `and_these_change_the_answer`, added at `887f598`,
came back `None` on every question. A transcript taken through that engine is a
transcript of yesterday.

Restarting is easy. Restarting **safely** is three questions nobody was in a
position to ask by hand, because each has an owner in a different lane:

1. **Is the card busy?** A lane holding `gpu.lock` may be mid-measurement, and
   stopping the engine underneath it destroys a run somebody is paying for in
   wall-clock time.
2. **Is anybody mid-conversation?** A thread with activity in the last five
   minutes is a person or an agent in the middle of something.
3. **Is the tree the new engine would launch from clean?** A restart onto a
   dirty tree swaps one unreproducible build for another, which is the fault it
   is meant to fix.

Each refusal names the thing that refused it - the lock line, the thread id, the
paths - because "not now" without a subject is a message nobody can act on.

## The verification is not optional

`--dry-run` aside, this reads `/health` after relaunching and requires that
`build.sha` CHANGED and `dirty` is false. A restart that does not read the sha
it produced is the health-check fault in a new costume: a process that started
is not a build that is serving, and the only evidence of the second is the sha
coming back different from the one written down before.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app import security  # noqa: E402 - after the path is set

#: WHERE THE CARD'S LOCK LIVES, AND THIS FILE MUST NOT KNOW.
#:
#: It used to be built from literal segments - `Path.home()` joined to a
#: personal folder name and a vault name - which put one machine's directory
#: layout into a shipped script. `tests/test_the_mirror_ships_nothing_private.py`
#: flags private path segments, and it does so against `identifiers.json`, which
#: is gitignored and per-checkout: a tree whose denylist happens not to name
#: those segments reads green while a tree whose denylist does reads red. Main
#: was red for two other lanes on this file while it was green here, which is
#: the per-checkout denylist story and is exactly why the test is written that
#: way.
#:
#: So the path is configuration, not a constant. Unset is a refusal naming the
#: variable - never a guess at somebody's folders, because a guess that happens
#: to be right on one machine is the thing that shipped in the first place.
THE_CARD_LOCK_VARIABLE = "MLH_CARD_LOCK"


def the_card_lock_path() -> Path | None:
    """Where this machine keeps the card lock, or `None` if nobody has said."""
    said = os.environ.get(THE_CARD_LOCK_VARIABLE, "").strip()
    return Path(said) if said else None


#: A thread touched inside this window is somebody's live conversation.
QUIET_FOR = timedelta(minutes=5)

#: Every table that carries a thread id and a timestamp. Asking all of them
#: rather than one is the difference between "nobody is talking" and "nobody is
#: talking in the table I happened to check".
WHERE_ACTIVITY_SHOWS = (
    "messages",
    "fact_evidence",
    "eval_runs",
    "agent_runs",
    "storms",
)

RESTARTED = 0
THE_CARD_IS_BUSY = 1
#: Nobody has said where the lock is. Not a refusal ABOUT the card - a refusal
#: to guess, which is a different exit because it names a different fix.
NO_LOCK_CONFIGURED = 5
A_THREAD_IS_LIVE = 2
THE_TREE_IS_DIRTY = 3
THE_RESTART_DID_NOT_TAKE = 4


def the_card_holder(lock: Path) -> str | None:
    """The lock line, or `None` if the card is free."""
    try:
        said = lock.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return said or None


def a_live_thread(database: Path, now: datetime | None = None) -> tuple[int, str] | None:
    """The most recent thread touched inside the window, or `None`.

    READ, NOT ASSUMED. Opened immutable so asking the question cannot itself
    write a journal beside a database another process is using.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = (now - QUIET_FOR).strftime("%Y-%m-%d %H:%M:%S")
    try:
        db = sqlite3.connect(f"file:{database}?mode=ro&immutable=1", uri=True)
    except sqlite3.Error:
        return None
    try:
        for table in WHERE_ACTIVITY_SHOWS:
            try:
                row = db.execute(
                    f"SELECT thread_id, created_at FROM {table} "  # noqa: S608 - names are ours
                    "WHERE created_at > ? ORDER BY created_at DESC LIMIT 1",
                    (cutoff,),
                ).fetchone()
            except sqlite3.Error:
                continue
            if row and row[0] is not None:
                return int(row[0]), f"{table} at {row[1]}"
    finally:
        db.close()
    return None


def what_is_dirty(repo: Path = REPO) -> list[str]:
    """Tracked paths that differ from HEAD. Untracked files are not dirt.

    A NEW FILE NOBODY HAS ADDED IS NOT A MODIFIED BUILD. Every lane leaves
    scratch files in this tree, and refusing a restart because one exists would
    mean never restarting.
    """
    done = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if done.returncode != 0:
        return ["git could not read this tree: " + done.stderr.strip()[:120]]
    return [line[3:] for line in done.stdout.splitlines() if line.strip()]


def health(timeout: float = 20.0) -> dict:
    """What the engine says about itself, or `{}` if it says nothing."""
    try:
        port = security.read_portfile()
        request = urllib.request.Request(
            f"http://127.0.0.1:{port['port']}/health",
            headers={"Authorization": f"Bearer {port['token']}"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            return json.load(answer)
    except Exception:  # noqa: BLE001 - an engine that cannot be asked is not an error here
        return {}


def _launcher(*arguments: str, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO / "scripts" / "launch.py"), *arguments],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="check the guards and stop")
    parser.add_argument(
        "--lock",
        default=None,
        help=f"the card lock file; defaults to ${THE_CARD_LOCK_VARIABLE}",
    )
    parser.add_argument("--database", default=str(REPO / "ml_harness.db"))
    arguments = parser.parse_args(sys.argv[1:] if argv is None else argv)

    lock = Path(arguments.lock) if arguments.lock else the_card_lock_path()
    if lock is None:
        print(
            f"NOT NOW: nobody has said where the card lock is. Set "
            f"{THE_CARD_LOCK_VARIABLE} to its path, or pass --lock. This script "
            "will not guess at a directory layout - a guess that happens to be "
            "right on one machine is how a personal path ends up in a shipped "
            "file."
        )
        return NO_LOCK_CONFIGURED

    holder = the_card_holder(lock)
    if holder:
        print("NOT NOW: the card is held, and stopping the engine under a lane "
              "mid-measurement destroys a run somebody is waiting on.")
        print(f"  {holder}")
        return THE_CARD_IS_BUSY

    live = a_live_thread(Path(arguments.database))
    if live:
        thread_id, where = live
        print(f"NOT NOW: thread {thread_id} was touched inside the last "
              f"{int(QUIET_FOR.total_seconds() // 60)} minutes ({where}). "
              "Somebody is mid-conversation.")
        return A_THREAD_IS_LIVE

    dirt = what_is_dirty()
    if dirt:
        print("NOT NOW: the tree this would launch from is dirty, so the new "
              "engine would serve a build nobody can reproduce - which is the "
              "fault this script exists to fix.")
        for path in dirt[:10]:
            print(f"  {path}")
        return THE_TREE_IS_DIRTY

    before = (health().get("build") or {}).get("sha")
    print(f"the engine is serving {before or '(nothing answered)'}")
    if arguments.dry_run:
        print("--dry-run: every guard passed and nothing was restarted.")
        return RESTARTED

    port = security.read_portfile().get("port")
    stopped = _launcher("--stop", "--port", str(port))
    print((stopped.stdout or stopped.stderr).strip()[:200])
    started = _launcher("--port", str(port))
    print((started.stdout or started.stderr).strip()[:200])

    #: A PROCESS THAT STARTED IS NOT A BUILD THAT IS SERVING. The sha is read
    #: back, and read again while it settles, because the only evidence the
    #: restart took is the number coming back different.
    after = None
    for _ in range(15):
        build = health(timeout=5.0).get("build") or {}
        after = build.get("sha")
        if after and after != before:
            if build.get("dirty"):
                print(f"REFUSED THE RESULT: now serving {after} but dirty is "
                      "true, so this build is not reproducible either.")
                return THE_RESTART_DID_NOT_TAKE
            print(f"restarted: {before} -> {after}, dirty false")
            return RESTARTED
        time.sleep(2)

    print(f"REFUSED THE RESULT: the engine still reports {after or '(nothing)'}, "
          f"which is what it reported before. A restart that does not change the "
          "sha did not happen, whatever the launcher said.")
    return THE_RESTART_DID_NOT_TAKE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
