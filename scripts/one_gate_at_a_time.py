"""Hold a machine-wide lock while a full-suite gate runs.

WHY A LOCK AND NOT A LOOK. Two lanes work this repository from two worktrees on
one machine. The agreed rule was "before a full-suite gate, check for another
test process and wait if one is running", and that rule is a check-then-act
race: both lanes look, both see a clear machine, both start. It failed twice in
twenty minutes on 2026-09-04, the second time within minutes of being agreed.
Looking cannot fix a race. Only mutual exclusion can.

WHAT THE COLLISION COSTS. It does not present as a crash. On 2026-09-04 the ML
Harness lane's gate discovered 3,822 tests, ran 3,315, and reported OK - a gate
that cannot fail, which is the first law in `docs/how-to-verify.md`, produced
by two suites running AT ONCE IN THIS CHECKOUT - one tree, two lanes, which is
what the record says and is worth being exact about, because it decides how
wide this lock has to be.

**THE MECHANISM IS UNKNOWN, AND THIS DOCSTRING USED TO CLAIM OTHERWISE.** It
said the suites contend for the same temp portfile and quoted the engine.json
deferral line as its evidence. `docs/how-to-verify.md` had already withdrawn
that: "the mechanism of the 3,315-of-3,822 collision is still unknown. It was
not the portfile." Two files in this repository disagreed about the cause of
one incident, and the one asserting a cause was the one justifying the scope of
a lock. Corrected here 2026-09-05; the laws page was right.

**WHICH LEAVES THE SCOPE RESTING ON SOMETHING WEAKER THAN IT LOOKED, AND IT
STAYS MACHINE-WIDE ANYWAY.** Nothing recorded WHICH 507 tests went missing -
the count assertion detects a loss and cannot name it - so the shared resource
has never been identified, and a scope narrowed to a tree would be narrowed on
a guess. What is measured points at a tree rather than the machine: the
collision was two suites in ONE checkout, and FIVE gates on 2026-09-05 ran
beside one to four concurrent suites in a DIFFERENT tree and reported
`ran == discovered` every time - 4,054, 4,068, 4,075, 4,086 and 4,101, each
against itself. That is 0 losses in 5 cross-tree runs against 1
loss in 1 same-tree run - evidence, not a resource, and a resource is what a
scope change needs. Note also that a per-tree lock would NOT have prevented the
incident this file was built for, since both suites were in the same tree.

The cost of being wider than necessary is a queue, and that is measured too:
two consecutive gates waited about 18 and about 19 minutes for a neighbour in
the other tree. If the resource is ever named and turns out to be per-tree,
that queue is what narrowing the scope buys back.

HOW IT WORKS. One file in the system temp directory, created with O_EXCL, which
is atomic on Windows and POSIX alike: exactly one process can create it, and
the loser learns who holds it rather than guessing. The holder writes its pid,
its worktree and what it is running, so a wait says who it is waiting for
instead of just hanging.

A holder that dies without releasing leaves the file behind. That is handled by
checking whether the recorded pid is still alive and stealing the lock if it is
not - a stale lock that blocks every future gate would be worse than the
collision it prevents.

A PID IS NOT AN IDENTITY, so the lock records when each process started as well
as its number. Operating systems reuse pids: measured 2026-09-05, this file's
own liveness check called pid 8932 alive, and pid 8932 was `explorer.exe`. A
lock left behind by a run whose number was later handed to a desktop shell
would have read as HELD for as long as the machine stayed up - every gate
waiting out the full timeout for a process that never took the lock. Two
processes can share a number over a machine's life; the same number with the
same creation instant is the same process.

    python scripts/one_gate_at_a_time.py -- python scripts/gate.py

It wraps any command and exits with that command's status, so it goes in front
of whatever the gate already is rather than replacing it.

THE DOCUMENTED GATE NOW TAKES THIS LOCK ITSELF (`1828b7f`), so the line above is
no longer the usual way in - `python scripts/gate.py` acquires and releases it
without being asked, and `--no-lock` opts out. This wrapper stays for the case
it was written for: putting the lock in front of something that is not the
gate, on a machine where the gate is not the only thing that contends.

The line above used to read `-- python -m unittest discover -s tests`, and that
was the third place naming a gate this repository had stopped running.
`tests/test_one_gate_command_is_named_everywhere.py` found it here, on its
first run, after the same divergence had already been found in CI.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

#: The system temp directory, because that is the resource actually being
#: contended: both suites put their scratch engines and portfiles there. A lock
#: inside one worktree would not have prevented either collision.
#: The name every lane used until 2026-09-06. Still WAITED FOR, never written -
#: see below.
LEGACY_LOCK = Path(tempfile.gettempdir()) / "ml-harness-gate.lock"


def _this_checkout() -> str:
    """Eight hex characters naming this working tree.

    THE REPOSITORY, NOT THE WORKING DIRECTORY, and the difference is not
    cosmetic. Keyed on `Path.cwd()` this lock names wherever the caller
    happened to be standing: two lanes in two trees that both run the gate
    from a common directory get the SAME lock and serialise for no reason,
    and one lane running it from a subdirectory of its own tree gets a
    DIFFERENT lock than from the root and loses the mutual exclusion this
    file exists for - inside its own checkout, which is the one collision it
    was built to prevent.

    Found by the designed collision run: both arms reported the same key,
    549c5cae, because the second arm was launched from the first arm's
    working directory with only the repository overridden. That was an
    instrument artefact and a real defect wearing the same face.
    """
    import hashlib

    #: This file lives in `<repo>/scripts/`, so its own location names the
    #: tree whatever directory the caller is standing in.
    tree = Path(__file__).resolve().parents[1]
    return hashlib.sha256(str(tree).lower().encode()).hexdigest()[:8]


#: ONE LOCK PER CHECKOUT, NOT ONE PER MACHINE, and the measurement is what
#: allows it.
#:
#: The collision this file was built for was **two full suites in ONE
#: checkout** - the laws page says so in those words. Cross-checkout is a
#: different question, and it now has a counted answer: **26 of 64 recorded gate
#: runs had at least one concurrent suite, and 0 of the 26 lost a test.**
#:
#: What is actually shared between two checkouts on this machine was measured
#: rather than assumed: the suite asks the OS for a port (`bind(("127.0.0.1",
#: 0))`) instead of taking 8078, the portfile is bound to a per-test root, and
#: the data root resolves to the checkout. What is left machine-wide is this
#: lock and an append-only history file.
#:
#: The cost of the old scope was 39% of every gate: 22 queued runs over two
#: days, 194 minutes, median 8.3, against a suite that takes 13.7 and needs no
#: GPU at all.
LOCK = Path(tempfile.gettempdir()) / f"ml-harness-gate.{_this_checkout()}.lock"

#: How long to wait for a holder before giving up. A full suite is about ten
#: minutes, so this allows for one ahead of us plus room, and then refuses
#: rather than waiting forever - an agent blocked with no message is worse than
#: one that reports it cannot gate yet.
DEFAULT_TIMEOUT_SECONDS = 1800


def note_the_child(pid: int) -> None:
    """Record the pid of the run this lock is holding the card for.

    FOUND BY KILLING THE WRAPPER. `Stop-Process -Force` on this process does not
    touch the suite it started: measured 2026-09-05, the wrapper died, the
    child kept running, and `--status` then said the lock was STALE because it
    only knew the wrapper's pid. A second lane reading that would have taken
    the lock and started a second suite beside a run that was still going -
    which is the exact collision this file exists to prevent, arriving through
    the file itself.

    So the lock records both, and a holder is gone only when BOTH are gone.
    """
    holder = _holder()
    if not holder:
        return
    holder["child"] = int(pid)
    holder["child_born"] = born_when(pid)
    try:
        LOCK.write_text(json.dumps(holder), encoding="utf-8")
    except OSError:  # pragma: no cover - the lock vanished under us
        pass


def born_when(pid: int) -> str:
    """When that pid's process started, as a string, or "" if unreadable.

    A PID IS NOT AN IDENTITY. Windows recycles process ids, and so does every
    other operating system; a pid on its own answers "is something running
    under this number", which is not the question the lock asks. Measured
    2026-09-05: `_alive(8932)` returned True for a live `explorer.exe`, so a
    lock recording pid 8932 would have read as HELD - by a desktop shell, for
    as long as the machine stayed up, wedging every gate until the timeout.

    A start time is what separates the two. Two processes can share a pid over
    a machine's life; the same pid with the same creation instant is the same
    process. Empty means "could not tell", which callers must treat as no
    evidence rather than as a mismatch.
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
        # Field 22 of /proc/<pid>/stat is start time in clock ticks since boot.
        # The command name can contain spaces and brackets, so read after the
        # last ')' rather than splitting the whole line.
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
        return stat[stat.rindex(")") + 1 :].split()[19]
    except (OSError, ValueError, IndexError):
        return ""


def _alive(pid: int, born: str = "") -> bool:
    """Is THAT process still running? A dead holder's lock is stale.

    `born` is the start time recorded when the lock was written. When it is
    present and disagrees with the live process's, the pid has been reused and
    the holder is gone however alive the number looks. When it is absent - an
    older lock, or a machine whose process times cannot be read - this falls
    back to the pid alone, which is the behaviour it has always had.

    IT IS COMPARED AS TEXT, BOTH SIDES COERCED. MEASURED 2026-09-05: this
    answered False - "the holder is gone" - for a live, correct, mid-run holder
    whose start time arrived as `134331322491779160` rather than
    `"134331322491779160"`. `born_when` returns a string and the lock file
    yields strings, so the two natural sources agree; a caller that parses the
    field to an int, or writes the literal unquoted, does not, and a string
    never equals an int in Python however identical the digits read.

    That slip is worse than the recycling it looks like. A wrong "recycled"
    CLEARS a live lock and starts a second run beside the first, which is the
    collision this module exists to prevent - and it is the direction this
    file's own law forbids: a start time that cannot be compared is no evidence,
    not evidence of absence.
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        # PROCESS_QUERY_LIMITED_INFORMATION. A live pid we may not query still
        # returns a handle, and treating "cannot tell" as alive is the safe
        # direction.
        #
        # BUT "OpenProcess returns NULL for a pid that no longer exists" - what
        # this comment said until 2026-09-11 - IS NOT TRUE, and the sentence is
        # what made an unsafe shape look safe. On Windows the process object
        # outlives the process while ANY handle to it is open, so an exited
        # process whose parent still holds its `Popen` answers this call with a
        # handle and reads as alive. Measured six trials each way: handle held,
        # alive 6 of 6; handle released, 0 of 6.
        #
        # It is mostly harmless HERE, because a holder this module meets is a
        # detached gate whose parent is gone. It is not harmless for anything
        # that asks about a child it spawned itself, and it cost a red gate on
        # an unrelated commit before it was written down.
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
            # Cannot query it, so cannot compare start times either. Alive is
            # the safe direction: a wrong "gone" starts a second suite.
            return True

    now = born_when(pid)
    if born and now and str(now).strip() != str(born).strip():
        # Same number, different process. Reporting this one alive would hold
        # the lock against a process that never took it.
        return False
    return True


#: What `_holder()` returns when the file is THERE and cannot be understood.
#:
#: MEASURED 2026-09-10, one window hit twice six minutes apart in the shared
#: checkout. 05:23:43 the lock named pid 23932 with a live child running the
#: suite. 05:25:38 the SAME file named pid 6268 - a second process had taken a
#: lock whose holder was alive. 05:29:58 the file was gone, and at 05:30:54
#: 23932 was still running its suite: a live gate with no lock at all, which is
#: the one state every reader here is built on never happening.
#:
#: Neither liveness check failed. NEITHER RAN. `_holder()` answered None for
#: "no lock file" and for "could not read the lock file", and both callers took
#: the second to mean the first:
#:
#:   acquire:  pid = int((holder or {}).get("pid") or 0)  ->  0
#:             _alive(0, ...) is False by its own first line
#:             -> "the holder died without releasing" -> steals a live lock
#:
#:   release:  if holder and int(...) != os.getpid(): return
#:             None walks straight past the guard into unlink(missing_ok=True)
#:             -> deletes a lock it could not read, so cannot know is its own
#:
#: A partial write, or a Windows sharing violation while another process
#: rewrites the file, produces exactly this. THE FILE'S OWN LAW, written three
#: functions down, is that None means "cannot decide" and never "unchanged" -
#: and its two most important callers were the two that broke it.
#:
#: So unreadable gets its own answer, and it is read as A LIVE FOREIGN HOLDER:
#: wait, do not take; refuse, do not delete. That is the safe direction for the
#: same reason `_alive` treats "cannot tell" as alive - the cost of waiting for
#: a lock nobody holds is a wait, and the cost of taking one somebody holds is
#: the collision this module exists to prevent.
UNREADABLE: dict = {"unreadable": True}


def read_holder(path: Path) -> dict | None:
    """The lock's contents; None when there is NO lock; `UNREADABLE` when there
    is one and it cannot be parsed. Three answers, because there are three
    states and collapsing two of them is what let a live lock be stolen.

    TAKES A PATH so `one_push_at_a_time` can import this rather than copy it.
    These three states and their two callers are the part of this file that was
    got wrong and fixed on 2026-09-10; a second copy would be a second thing to
    fix the next time.
    """
    try:
        said = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        #: THE FILE IS THERE AND WE COULD NOT OPEN IT. On Windows that is
        #: routinely another process mid-write, which is a holder, not an
        #: absence.
        return UNREADABLE
    try:
        parsed = json.loads(said)
    except ValueError:
        return UNREADABLE
    return parsed if isinstance(parsed, dict) else UNREADABLE


def _holder() -> dict | None:
    """This checkout's lock, through the shared reading above."""
    return read_holder(LOCK)


def is_unreadable(holder: dict | None) -> bool:
    """Is this the "there is a lock and it makes no sense" answer?"""
    return holder is UNREADABLE or bool(holder) and holder.get("unreadable") is True


def _describe(holder: dict | None) -> str:
    if is_unreadable(holder):
        #: SAID EXACTLY, because this used to be the sentence for BOTH "no
        #: lock" and "a lock we could not read", and the two are the states
        #: whose conflation let a live lock be stolen.
        return "a lock file that is present and could not be read"
    if not holder:
        return "another process (no lock file to describe)"
    return (
        f"pid {holder.get('pid')} in {holder.get('cwd')} "
        f"running {holder.get('command')!r} since {holder.get('started')}"
    )


def _still_waiting(holder: dict | None, began: float, last_said: float) -> float:
    """Say, once a minute, that this is a wait and not a hang.

    An unbounded wait with no output is indistinguishable from a wedged
    process, and the reason the clock could be removed at all is that the
    holder is checkable - so the check gets said out loud.
    """
    now = time.time()
    if now - last_said < 60:
        return last_said
    print(
        f"one_gate_at_a_time: still waiting after {(now - began) / 60:.0f} "
        f"minute(s) for {_describe(holder)}",
        file=sys.stderr,
    )
    return now


#: The two real paths, captured before any caller redirects them. A test
#: that points LOCK at a temp file is asking about ITS lock, not this
#: machine's - and until this existed, every such test silently waited on
#: whatever the OTHER checkout happened to be doing. Nine of them failed at
#: once the first time the neighbouring lane ran a gate, and the failure was
#: the harness reaching outside itself, not the code under test.
THE_REAL_LOCK = LOCK
THE_REAL_LEGACY_LOCK = LEGACY_LOCK


def _the_legacy_wait_is_ours_to_make() -> bool:
    """Whether waiting out a legacy holder is this caller's business.

    True in production, where LOCK is the real per-checkout path. True for a
    test that redirected the legacy lock too, which is a test deliberately
    exercising the transition against its own fixture. False for a test that
    redirected only LOCK - that test is about locking, and the neighbouring
    lane's real lock is not part of its subject.
    """
    return LOCK == THE_REAL_LOCK or LEGACY_LOCK != THE_REAL_LEGACY_LOCK


def _wait_out_a_legacy_holder(deadline: float | None) -> bool:
    """Wait for a lane that has not taken the per-checkout change yet.

    THE TRANSITION IS THE DANGEROUS PART, not the new scope. A lane still on the
    machine-wide name writes `LEGACY_LOCK` and cannot see a per-checkout one, so
    for as long as one lane is upgraded and the other is not, the un-upgraded
    lane could start beside us. Waiting for its lock closes that in the
    direction we control, and leaves open only the cross-checkout case that 26
    of 26 recorded runs came through clean.

    This never WRITES the legacy lock. Writing it would re-impose the
    machine-wide scope on every other lane, which is the thing being removed.

    IT HONOURS THE CALLER'S DEADLINE, and the first version did not. A wait
    placed before the timeout loop turned every bounded `acquire` into an
    unbounded one the moment a lane on the old name was live - which was
    found by the lock's own suite hanging for eight minutes while the other
    checkout ran its gate. A caller that asked for one second must get an
    answer in about one second, and "I could not get in" is an answer.

    Returns True if the way is clear, False if the deadline passed first.
    """
    if not _the_legacy_wait_is_ours_to_make() or not LEGACY_LOCK.exists():
        return True
    announced = False
    while True:
        try:
            held = json.loads(LEGACY_LOCK.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return True
        pid = int(held.get("pid") or 0)
        if not _alive(pid, str(held.get("pid_born") or "")):
            return True
        if deadline is not None and time.time() >= deadline:
            return False
        if not announced:
            print(
                "one_gate_at_a_time: a lane is still on the machine-wide lock "
                f"({_describe(held)}) - waiting for it. This wait disappears once "
                "every lane takes the per-checkout change.",
                file=sys.stderr,
            )
            announced = True
        # Sleep no further than the deadline: a five-second step is fine for
        # a gate that waits forever and absurd for a caller that asked for
        # one second and got five.
        left = 5.0 if deadline is None else max(0.05, min(5.0, deadline - time.time()))
        time.sleep(left)


#: EXPORTED WHEN THIS PROCESS TAKES THE LOCK, so its own children can tell
#: "somebody is gating here" from "I am the one gating here".
#:
#: MEASURED 2026-09-10: `push_if_green` held this lock, its push was rejected,
#: it ran `git rebase origin/main` to recover - and the `pre-rebase` hook read
#: the lock, saw a live holder, and refused. The holder was the rebasing
#: process itself. The guard blocked its own recovery and the retry died with
#: "the rebase did not succeed, so there is no tree to gate".
#:
#: An environment variable rather than a process-tree walk because inheritance
#: is exactly the relation being asked about: a hook git spawns under the
#: holder is a descendant of the holder and nothing else is.
HOLDING_THIS_LOCK = "MLH_HOLDS_THE_GATE_LOCK"


def this_process_holds_the_lock(holder: dict | None) -> bool:
    """Is the live holder this process, or an ancestor of it?

    The pid is COMPARED, never just the variable's presence: a lane holding one
    checkout's lock and committing in another would otherwise wave itself
    through a lock it does not hold.
    """
    if not holder:
        return False
    said = os.environ.get(HOLDING_THIS_LOCK, "").strip()
    return bool(said) and said == str(holder.get("pid") or "")


def acquire(timeout: float | None, command: str) -> bool:
    """Take the lock, waiting while a live holder holds it.

    **THE WAIT KEYS ON THE ACTOR, NEVER ON A CLOCK**, which is the standing law
    here and was the one place this file still broke it. `timeout=None` - what
    the gate passes - waits for exactly as long as the holder is alive, and
    stops waiting when the holder is gone, which is the orphan and stale
    handling below rather than a separate exit.

    WHY A CLOCK WAS WRONG HERE, MEASURED. With a fixed 1,800 seconds, two gates
    in a row queued about 18 and about 19 minutes behind holders that ran about
    28 and about 30. Neither expired, so nothing failed - but the second holder
    took essentially the whole timeout, and a third lane arriving behind it
    would have waited half an hour and then been told nothing at all. A gate
    that spends thirty minutes to learn NOTHING is worse than one that waits
    thirty-one and learns whether the tree is green: the clock was deciding an
    honest question on a quantity unrelated to it, and the holder's liveness is
    the quantity the question is actually about.

    THAT ONLY BECAME SAFE WHEN LIVENESS BECAME REAL. Waiting forever on "is
    there a process with that number" would wedge this machine the first time a
    pid was recycled - which was measured happening (`ceede9d`). The lock
    records each process's start time, so "the holder is alive" now means that
    process and not that number, and an unbounded wait rests on a check that
    can actually tell.

    A number may still be passed, and the tests do: it is a caller saying "I
    will not wait longer than this", which is a different statement from the
    file having an opinion about how long a suite takes.
    """
    payload = json.dumps(
        {
            "pid": os.getpid(),
            "pid_born": born_when(os.getpid()),
            "cwd": str(Path.cwd()),
            "command": command,
            "started": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )

    deadline = None if timeout is None else time.time() + timeout
    began = time.time()
    if not _wait_out_a_legacy_holder(deadline):
        _remember_the_wait(time.time() - began)
        return False
    announced = False
    #: The last time the wait said it was still waiting. A silent wait and a
    #: hung one look identical, and this file's whole subject is telling apart
    #: two states that look identical.
    last_said = began
    while True:
        try:
            handle = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            holder = _holder()
            if is_unreadable(holder):
                #: THERE IS A LOCK. It is unparseable, which is what a holder
                #: mid-write looks like, so this waits rather than deciding
                #: from a failed read that nobody is here. Announced once, so
                #: a wait on a corrupt file is not a silent hang.
                if not announced:
                    print(
                        "one_gate_at_a_time: waiting - a lock file is present "
                        "and could not be read. Treating it as held: a read "
                        "that failed is not evidence that nobody is gating.",
                        file=sys.stderr,
                    )
                    announced = True
                if deadline is not None and time.time() >= deadline:
                    return False
                last_said = _still_waiting(holder, began, last_said)
                time.sleep(5)
                continue
            pid = int((holder or {}).get("pid") or 0)
            child = int((holder or {}).get("child") or 0)
            pid_born = str((holder or {}).get("pid_born") or "")
            child_born = str((holder or {}).get("child_born") or "")
            if _alive(child, child_born) and not _alive(pid, pid_born):
                # Orphaned, not stale: the wrapper is gone and its run is not.
                if not announced:
                    print(
                        f"one_gate_at_a_time: pid {pid} is gone but the run it started "
                        f"(pid {child}) is still going - waiting for that, not taking "
                        "the lock. A suite started beside it is the collision this "
                        "file exists to prevent.",
                        file=sys.stderr,
                    )
                    announced = True
                if deadline is not None and time.time() >= deadline:
                    return False
                last_said = _still_waiting(holder, began, last_said)
                time.sleep(5)
                continue
            if not _alive(pid, pid_born) and not _alive(child, child_born):
                # The holder died without releasing. Better to steal a stale
                # lock than to block every gate on this machine forever.
                # Say WHICH kind of gone. "not running" about a pid that is
                # running, under a process that simply is not ours, is the
                # instrument lying in the direction that is hardest to check.
                recycled = pid_born and _alive(pid) and born_when(pid) != pid_born
                why = (
                    f"pid {pid} is now a different process than the one that took "
                    f"this lock (started {born_when(pid)}, the lock recorded {pid_born})"
                    if recycled
                    else f"pid {pid} is not running"
                )
                print(
                    f"one_gate_at_a_time: stale lock - {why} - taking it",
                    file=sys.stderr,
                )
                LOCK.unlink(missing_ok=True)
                continue
            if not announced:
                print(
                    f"one_gate_at_a_time: waiting for {_describe(holder)}",
                    file=sys.stderr,
                )
                announced = True
            if deadline is not None and time.time() >= deadline:
                print(
                    f"one_gate_at_a_time: gave up after {timeout:.0f}s waiting for "
                    f"{_describe(holder)}",
                    file=sys.stderr,
                )
                return False
            last_said = _still_waiting(holder, began, last_said)
            time.sleep(5)
            continue
        with os.fdopen(handle, "w") as file:
            file.write(payload)
        waited = time.time() - began
        _remember_the_wait(waited)
        if waited >= 10:
            # RECORD THE WAIT. The law written on 2026-09-05 says the number in
            # it is one observation rather than a rate, because the wait was
            # announced while it happened and never totalled when it ended.
            print(
                f"one_gate_at_a_time: took the lock after waiting {waited / 60:.1f} "
                f"minutes for the previous holder",
                file=sys.stderr,
            )
        os.environ[HOLDING_THIS_LOCK] = str(os.getpid())
        return True


#: How long the last successful `acquire` spent queueing, in seconds. The
#: wait was ANNOUNCED while it happened and never TOTALLED when it ended, so
#: "194 minutes over two days" had to be reconstructed by hand from scattered
#: lines. A caller that records this puts the number in the history instead.
_LAST_WAIT = 0.0


def _remember_the_wait(seconds: float) -> None:
    global _LAST_WAIT
    _LAST_WAIT = seconds


def waited_seconds() -> float:
    """Seconds the last successful acquire queued. Zero when it did not."""
    return _LAST_WAIT


def release() -> None:
    """Drop the lock, but only if it is still ours."""
    holder = _holder()
    if is_unreadable(holder):
        #: A LOCK WE CANNOT READ IS A LOCK WE CANNOT KNOW IS OURS. Deleting it
        #: is how a live gate ended up with no lock at 05:29:58.
        print(
            "one_gate_at_a_time: not releasing - the lock file is there and "
            "could not be read, so it cannot be shown to be ours. It will be "
            "reclaimed as stale if its holder is gone.",
            file=sys.stderr,
        )
        return
    if holder and int(holder.get("pid") or 0) != os.getpid():
        # Somebody stole it after deciding we were dead. Removing it now would
        # take the lock out from under whoever is legitimately holding it.
        print(
            "one_gate_at_a_time: not releasing - the lock now belongs to "
            f"pid {holder.get('pid')}",
            file=sys.stderr,
        )
        return
    LOCK.unlink(missing_ok=True)
    os.environ.pop(HOLDING_THIS_LOCK, None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="seconds to wait for a live holder before refusing",
    )
    parser.add_argument("--status", action="store_true", help="say who holds the lock")
    parser.add_argument("rest", nargs=argparse.REMAINDER, help="-- then the command")
    args = parser.parse_args()

    if args.status:
        holder = _holder()
        if holder is None:
            print("one_gate_at_a_time: nobody holds the gate lock")
            return 0
        alive = _alive(int(holder.get("pid") or 0), str(holder.get("pid_born") or ""))
        child_alive = _alive(int(holder.get("child") or 0), str(holder.get("child_born") or ""))
        print(f"one_gate_at_a_time: held by {_describe(holder)}")
        if not alive and child_alive:
            print(
                f"one_gate_at_a_time: that wrapper is gone but the run it started "
                f"(pid {holder.get('child')}) is STILL RUNNING - the lock is orphaned, "
                "not stale, and taking it would put a second suite beside a live one"
            )
        elif not alive:
            print("one_gate_at_a_time: that process is gone - the lock is stale")
        if alive and not holder.get("pid_born"):
            print(
                "one_gate_at_a_time: this lock records no start time, so ALIVE here "
                "means only that some process holds that number - it may be a "
                "different one that inherited the pid"
            )
        return 0

    command = [part for part in args.rest if part != "--"]
    if not command:
        parser.error("nothing to run: put the command after --")

    if not acquire(args.timeout, " ".join(command)):
        return 2
    child = None
    try:
        child = subprocess.Popen(command)
        note_the_child(child.pid)
        return child.wait()
    finally:
        release()


if __name__ == "__main__":
    raise SystemExit(main())
