"""Write the GPU lock line in the form the card owner can rule on.

THE PROTOCOL, ruled 2026-09-05 20:50 and adopted from this lane's next lock:

    lane=<lane> since=<UTC Z> pid=<pid> born=<that process's start time, UTC Z> what=<line>

WHY THE TWO NEW FIELDS. The card owner has to decide two different things about
a lock nobody released - is the holder dead, or is it alive under a number that
was handed to somebody else - and until now the line carried neither fact. Every
lock written before tonight answers "cannot be decided", which is the honest
reading of a line with no pid and no birth: not "the holder is alive", not "the
holder is gone", but that the question was never askable.

WHY `born` IS A UTC STAMP AND NOT THE RAW VALUE. On Windows the process start
time is a FILETIME - 100-nanosecond intervals since 1601 - and on Linux it is
clock ticks since boot. Neither is comparable by a person reading a lock file,
and the second is not even comparable across a reboot. This converts on
Windows and verifies against an independent reader; where it cannot produce a
wall clock it writes nothing rather than writing a number that looks like one.

WHAT THIS DOES NOT CHANGE: when the card is taken or released. That is the
lane's business and stays exactly as it was.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import sys
from pathlib import Path

#: Seconds between 1601-01-01 and the Unix epoch. The Windows FILETIME origin.
FILETIME_EPOCH_OFFSET = 11_644_473_600

#: THE LEDGER, amended 2026-09-06 00:30. The lock line is the record only while
#: the file exists, and one run's line survived a night only inside a commit
#: body. So every writer APPENDS: the full lock line on take, and one release
#: line on release. Append-only, one line each, never rewritten - a log that can
#: be edited is a log a reader has to trust rather than read.
#:
#: `held=` IS WRITTEN BY THE WRITER BECAUSE THE WRITER KNOWS IT. A reader can
#: only infer the span from two whole-second stamps; the process that held the
#: card knows how long it held it. The protocol has the reader recompute and
#: report any disagreement past a second rather than correct either number,
#: which is why this writes the span it measured and not one it derived to
#: match.
LOG_NAME = "gpu.lock.log"


def _raw_start(pid: int) -> str:
    """The operating system's own start-time token for a pid, or ""."""
    if pid <= 0:
        return ""
    if os.name == "nt":
        import ctypes
        import ctypes.wintypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return ""
        try:
            created = ctypes.wintypes.FILETIME()
            spare = (ctypes.wintypes.FILETIME * 3)()
            ok = kernel32.GetProcessTimes(
                handle,
                ctypes.byref(created),
                ctypes.byref(spare[0]),
                ctypes.byref(spare[1]),
                ctypes.byref(spare[2]),
            )
        finally:
            kernel32.CloseHandle(handle)
        if not ok:
            return ""
        return str((created.dwHighDateTime << 32) | created.dwLowDateTime)
    try:
        stat = Path("/proc/{}/stat".format(pid)).read_text(encoding="utf-8", errors="replace")
        return stat[stat.rindex(")") + 1 :].split()[19]
    except (OSError, ValueError, IndexError):
        return ""


def born_utc(pid: int) -> str:
    """That process's start time as `YYYY-MM-DDTHH:MM:SSZ`, or "".

    Empty means the question could not be answered, and a reader must treat it
    as "cannot be decided" rather than as either answer. Verified against
    `Get-Process(...).StartTime` on this machine: the two agree to the second.
    """
    raw = _raw_start(pid)
    if not raw or os.name != "nt":
        return ""
    seconds = int(raw) / 10_000_000 - FILETIME_EPOCH_OFFSET
    return datetime.datetime.fromtimestamp(
        seconds, datetime.timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def the_log_beside(lock: Path) -> Path:
    """The ledger lives beside the lock it records."""
    return lock.parent / LOG_NAME


def append(log: Path, line: str) -> bool:
    """One line, appended. True if it landed.

    BEST EFFORT, AND LOUD WHEN IT IS NOT. A card owner refused the card because
    a log file could not be opened would be a worse outcome than a missing line,
    so this never raises - but it says so on stderr, because a ledger that is
    quietly not being written is the failure the ledger exists to prevent.
    """
    try:
        with log.open("a", encoding="utf-8") as file:
            file.write(line + chr(10))
        return True
    except OSError as problem:
        print(f"take_the_card: could not append to {log}: {problem}", file=sys.stderr)
        return False


def the_release_line(lane: str, held_seconds: int) -> str:
    return "released lane={lane} at={at} held={held}".format(
        lane=lane,
        at=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        held=int(held_seconds),
    )


def held_seconds(line: str, now: datetime.datetime | None = None) -> int | None:
    """How long that lock has been held, from its own `since`, or None.

    None when the line carries no readable `since`. A release line with no span
    is better than one carrying a zero that means "could not tell": the reader
    counts minutes, and a false zero is a silent subtraction from a total.
    """
    hit = re.search(r"since=(\S+)", line)
    if not hit:
        return None
    try:
        began = datetime.datetime.strptime(hit.group(1), "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    began = began.replace(tzinfo=datetime.timezone.utc)
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return max(0, int((now - began).total_seconds()))


def the_line(lane: str, what: str, pid: int | None = None) -> str:
    """The lock line, in the ruled order."""
    pid = os.getpid() if pid is None else int(pid)
    return "lane={lane} since={since} pid={pid} born={born} what={what}".format(
        lane=lane,
        since=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        pid=pid,
        born=born_utc(pid) or "unknown",
        what=what,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", default="practical")
    # NOT required at the parser, because a release does not need one and
    # making it required would force somebody to invent a purpose in order
    # to give the card back. Required for a take, checked below.
    parser.add_argument("--what", default=None, help="one line saying what the card is for")
    parser.add_argument("--pid", type=int, default=None, help="the process that holds the card")
    parser.add_argument("--lock", default=None, help="write it here instead of printing")
    parser.add_argument(
        "--release", action="store_true",
        help="remove the lock and append the release line, rather than taking it",
    )
    args = parser.parse_args(argv)

    if args.release:
        if not args.lock:
            parser.error("--release needs --lock")
        path = Path(args.lock)
        if not path.exists():
            print(f"take_the_card: nothing to release at {path}", file=sys.stderr)
            return 2
        line = path.read_text(encoding="utf-8").strip()
        held = held_seconds(line)
        lane = (re.search(r"lane=(\S+)", line) or [None, args.lane])[1]
        path.unlink()
        released = the_release_line(lane, held if held is not None else 0)
        if held is None:
            # Said rather than guessed: a span computed from a line with no
            # readable `since` is not a span.
            print("take_the_card: the lock carried no readable since=, so held= is 0 "
                  "and means unknown", file=sys.stderr)
        append(the_log_beside(path), released)
        print(released)
        return 0

    if not args.what:
        parser.error("a take needs --what: one line saying what the card is for")
    line = the_line(args.lane, args.what, args.pid)
    if args.lock:
        path = Path(args.lock)
        # EXCLUSIVE CREATE, not exists-then-write: two takers 23 s apart on 2026-09-24
        # both passed an exists() check window elsewhere and the second overwrote the
        # first. Mode "x" fails if the file appeared at any moment before the create.
        try:
            with open(path, "x", encoding="utf-8") as held:
                held.write(line + "\n")
        except FileExistsError:
            print(
                "take_the_card: a lock is already there and this will not overwrite it:\n  "
                + path.read_text(encoding="utf-8").strip(),
                file=sys.stderr,
            )
            return 2
        append(the_log_beside(path), line)
    print(line)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
