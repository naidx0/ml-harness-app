"""Who holds this resource, and is that holder still alive?

THE FAILURE THIS IS FOR. Two runs shared one machine and one of them lost 507
of its cases while printing OK. The agreed rule beforehand was "check for
another run and wait if one is going", and that rule is a check-then-act race:
both look, both see a clear machine, both start. It failed twice in twenty
minutes, the second time within minutes of being agreed. Looking cannot fix a
race; only mutual exclusion can.

WHAT MAKES THIS DIFFERENT FROM A LOCK FILE. Three things, each of which was a
defect first.

**A pid is not an identity.** Every operating system reuses process ids. A lock
left behind by a run whose number was later handed to a long-lived program
reads as HELD for as long as that program runs - measured: a liveness check
answered "alive" for pid 8932, and 8932 was the desktop shell. So the holder's
process start time is recorded beside its number, and "still held" means that
process rather than that number.

**The wait keys on the holder, not on a clock.** A fixed timeout decides an
honest question on a quantity unrelated to it. Measured against a 30-minute
one: two runs queued about 18 and 19 minutes behind holders that ran about 28
and 30 - neither expired, but a third arriving behind the second would have
waited half an hour to be told nothing at all. This waits while the holder is
alive and stops when it is gone.

**A lock protects only the runs that take it.** Measured: two suites running
concurrently under two interpreters while nobody held the lock. So a green run
also NAMES the neighbours it can see, because a guard that depends on being
remembered is not one, and a green result should carry the fact that it did not
have the machine to itself.

WHAT THIS IS NOT. It is not a distributed lock and does not try to be. It is
one file, created with O_EXCL, which is atomic on Windows and POSIX alike:
exactly one process can create it and the loser learns who holds it rather than
guessing.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable

#: How long between "are you still there?" checks while waiting.
BEAT_SECONDS = 5

#: How often a wait says out loud that it is still a wait. An unbounded wait
#: with no output is indistinguishable from a wedged process, and telling those
#: two apart is most of what this module is for.
SAY_EVERY_SECONDS = 60


def started_at(pid: int) -> str:
    """When that pid's process started, as a string, or "" if unreadable.

    Two processes can share a number over a machine's life, but not a number
    AND a creation instant. Empty means "could not tell", which callers must
    treat as no evidence rather than as a mismatch - see `still_running`.
    """
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
        # Field 22 of the proc stat line is start time in clock ticks since
        # boot. The command name can contain spaces and brackets, so read after
        # the last close-paren rather than splitting the whole line.
        stat = Path("/proc/{}/stat".format(pid)).read_text(encoding="utf-8", errors="replace")
        return stat[stat.rindex(")") + 1 :].split()[19]
    except (OSError, ValueError, IndexError):
        return ""


def still_running(pid: int, born: str = "") -> bool:
    """Is THAT process still running - not merely something with that number?

    `born` is the start time recorded when the lock was written. Present and
    disagreeing means the number was reused and the holder is gone however
    alive it looks. Absent means no evidence, and the check falls back to the
    number alone.

    THE DIRECTION OF THE DOUBT IS THE DESIGN. Treating "cannot tell" as "gone"
    would start a second run beside a live one, which is the collision being
    prevented. Treating it as "alive" costs a wait.
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
    else:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            # Cannot query it, so cannot compare start times either.
            return True
    now = started_at(pid)
    if born and now and now != born:
        return False
    return True


class Hold:
    """A named claim on a resource, with a holder that can be checked."""

    def __init__(self, path: str | Path, *, holder: str, purpose: str):
        self.path = Path(path)
        self.holder = str(holder)
        self.purpose = str(purpose)
        self._waited = 0.0

    # -- reading -----------------------------------------------------------

    def whose(self) -> dict | None:
        """What the lock file says, or None if there is nothing readable."""
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def describe(self, held: dict | None = None) -> str:
        held = self.whose() if held is None else held
        if not held:
            return "another process (its lock file is unreadable)"
        return (
            "{holder} (pid {pid}) doing {purpose!r} since {since}".format(
                holder=held.get("holder"),
                pid=held.get("pid"),
                purpose=held.get("purpose"),
                since=held.get("since"),
            )
        )

    def is_free(self) -> bool:
        held = self.whose()
        if held is None:
            return not self.path.exists()
        return not still_running(
            int(held.get("pid") or 0), str(held.get("pid_started_at") or "")
        )

    # -- taking and letting go ---------------------------------------------

    def take(self, *, timeout: float | None = None, say: Callable[[str], None] | None = None) -> bool:
        """Take the hold, waiting while a live holder has it.

        `timeout=None` - the default, and the one to use - waits for exactly as
        long as the holder is alive. A number is a CALLER saying how long it
        will wait, which is a different statement from this file having an
        opinion about how long the work takes.
        """
        say = say or (lambda line: None)
        payload = json.dumps(
            {
                "holder": self.holder,
                "purpose": self.purpose,
                "pid": os.getpid(),
                "pid_started_at": started_at(os.getpid()),
                "since": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        )
        began = time.time()
        deadline = None if timeout is None else began + timeout
        last_said = began
        announced = False
        while True:
            try:
                handle = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                held = self.whose()
                pid = int((held or {}).get("pid") or 0)
                born = str((held or {}).get("pid_started_at") or "")
                if not still_running(pid, born):
                    reused = born and still_running(pid) and started_at(pid) != born
                    why = (
                        "pid {} is a different process than the one that took this "
                        "hold".format(pid)
                        if reused
                        else "pid {} is not running".format(pid)
                    )
                    say("hold: stale - {} - taking it".format(why))
                    try:
                        self.path.unlink()
                    except OSError:  # pragma: no cover - somebody else got there
                        pass
                    continue
                if not announced:
                    say("hold: waiting for {}".format(self.describe(held)))
                    announced = True
                if deadline is not None and time.time() >= deadline:
                    say("hold: gave up after {:.0f}s".format(timeout or 0))
                    return False
                now = time.time()
                if now - last_said >= SAY_EVERY_SECONDS:
                    say(
                        "hold: still waiting after {:.0f} minute(s) for {}".format(
                            (now - began) / 60, self.describe(held)
                        )
                    )
                    last_said = now
                time.sleep(BEAT_SECONDS)
                continue
            with os.fdopen(handle, "w") as file:
                file.write(payload)
            self._waited = time.time() - began
            if self._waited >= 10:
                say("hold: took it after waiting {:.1f} minutes".format(self._waited / 60))
            return True

    def waited_seconds(self) -> float:
        """How long the last successful `take` waited. Recorded rather than
        estimated, because a wait nobody totals is a wait nobody can price."""
        return self._waited

    def let_go(self, *, say: Callable[[str], None] | None = None) -> None:
        """Drop the hold, but only if it is still ours.

        If we were declared dead and somebody took it, removing the file now
        would take the hold out from under its legitimate owner.
        """
        say = say or (lambda line: None)
        held = self.whose()
        if held and int(held.get("pid") or 0) != os.getpid():
            say("hold: not releasing - it now belongs to pid {}".format(held.get("pid")))
            return
        try:
            self.path.unlink()
        except OSError:
            pass

    def __enter__(self) -> "Hold":
        if not self.take():
            raise RuntimeError("could not take the hold at {}".format(self.path))
        return self

    def __exit__(self, *exc) -> None:
        self.let_go()
        return None
