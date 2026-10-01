"""One certified push to a remote ref at a time, machine-wide.

    from scripts import one_push_at_a_time as push_lock
    push_lock.acquire("origin", "refs/heads/main", timeout, "push_if_green")
    ...gate, then push...
    push_lock.release()

## The measurement that justifies it

SIX RACES IN EIGHT HOURS on 2026-09-10, every one the same shape: two lanes
gate siblings of one commit in two checkouts, both go green, and the second to
reach the push is refused as a non-fast-forward. Each costs a full suite -
about sixteen minutes - and then costs another, because the loser rebases and
re-gates.

`one_gate_at_a_time` cannot prevent it and is not wrong to. It is keyed by
CHECKOUT, and two lanes in two worktrees are correctly not contending for one
tree. What they contend for is `refs/heads/main` on the remote, which is not a
thing any per-checkout lock can name.

## Why it is taken BEFORE the gate

A lock taken after a green gate would serialise the pushes and nothing else:
the loser would still have spent a suite on a tree that no longer describes
`main`, then rebased and spent another. Taken first, the second lane WAITS -
and when it starts, its tree already contains the winner's object, so its gate
certifies what it is about to publish. One wait replaces one wasted suite plus
one rebase.

The cost is honest and stated: a lane can now wait up to a full gate plus a
push behind the holder. That is the trade, and it is the cheaper side of it.

## What it does NOT do, said here rather than discovered

**It serialises the lanes on this machine that take it, and nothing else.** A
push from a clone we do not know about, from CI, or from a person's laptop
still moves the ref under a held lock, and this file would have no idea. It is
a courtesy between cooperating processes, exactly like the commit hook, and the
refusal says so in its own words. `push_if_green` still checks the fast-forward
and still rebases on a rejected ref; this removes the common case, not the
possibility.

## Stale holders

Wired from the start rather than added after somebody waits out a timeout
behind a dead process, because a push lock held across a whole gate is exactly
where a crash leaves a corpse. The liveness rules are `one_gate_at_a_time`'s,
imported rather than copied - including that an UNREADABLE lock file is read as
a live foreign holder, which is the fix that file took on 2026-09-10 after a
live gate was left holding nothing.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _gate_lock_module():
    """`one_gate_at_a_time`, loaded by path because `scripts/` is not a package.

    IMPORTED RATHER THAN COPIED. Its `_alive`, `born_when` and three-state
    holder reading are the parts that were got wrong and then fixed on
    2026-09-10; a second copy here would be a second thing to fix next time.
    """
    path = HERE / "one_gate_at_a_time.py"
    spec = importlib.util.spec_from_file_location("one_gate_at_a_time", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_gate = _gate_lock_module()

#: Exported when this process holds a push lock, so anything it spawns can tell
#: "somebody is pushing" from "I am the one pushing" - the same relation the
#: commit hook needed, and the same answer.
HOLDING_THIS_LOCK = "MLH_HOLDS_THE_PUSH_LOCK"

#: How long to wait for a holder. A gate plus a push is about twenty minutes,
#: so this allows for one ahead of us and then refuses rather than waiting
#: forever - an agent blocked with no message is worse than one that says it
#: cannot push yet.
DEFAULT_TIMEOUT_SECONDS = 2400

_POLL_SECONDS = 5
_SAY_EVERY = 60

_held: Path | None = None


def lock_path(remote: str, ref: str) -> Path:
    """One file per REMOTE REF, which is the thing actually contended.

    Keyed on the pair rather than on the word `main`: two remotes with a branch
    of the same name are two different refs and must not serialise, and a lane
    pushing `refs/heads/experiment` has no reason to wait for one pushing
    `refs/heads/main`.
    """
    key = hashlib.sha256(f"{remote}\n{ref}".encode()).hexdigest()[:8]
    return Path(tempfile.gettempdir()) / f"ml-harness-push.{key}.lock"


def _describe(holder: dict | None) -> str:
    if _gate.is_unreadable(holder):
        return "a push lock that is present and could not be read"
    if not holder:
        return "another process (no lock file to describe)"
    return (
        f"pid {holder.get('pid')} in {holder.get('cwd')} "
        f"pushing {holder.get('ref')} since {holder.get('started')}"
    )


def holder(remote: str, ref: str) -> dict | None:
    return _gate.read_holder(lock_path(remote, ref))


def _is_live(said: dict | None) -> bool:
    """Unreadable counts as live, for `one_gate_at_a_time`'s reason: a read
    that failed is not evidence that nobody is here."""
    if _gate.is_unreadable(said):
        return True
    if not said:
        return False
    return _gate._alive(int(said.get("pid") or 0), str(said.get("pid_born") or ""))


def acquire(remote: str, ref: str, timeout: float | None, command: str) -> bool:
    """Take the push lock for one remote ref, waiting while a live lane holds it."""
    global _held
    path = lock_path(remote, ref)
    payload = json.dumps(
        {
            "pid": os.getpid(),
            "pid_born": _gate.born_when(os.getpid()),
            "cwd": str(Path.cwd()),
            "command": command,
            "remote": remote,
            "ref": ref,
            "started": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    deadline = None if timeout is None else time.time() + timeout
    announced = False
    last_said = time.time()

    while True:
        said = holder(remote, ref)
        if not _is_live(said):
            #: A DEAD HOLDER'S LOCK IS STALE AND SAYS SO. Wired from the start:
            #: this lock is held across a whole gate, which is precisely where a
            #: crash leaves a corpse for the next lane to wait out.
            if said and not _gate.is_unreadable(said):
                print(
                    f"one_push_at_a_time: stale push lock - pid "
                    f"{said.get('pid')} is not running - taking it",
                    file=sys.stderr,
                )
            try:
                path.write_text(payload, encoding="utf-8")
            except OSError as problem:
                print(f"one_push_at_a_time: could not write {path}: {problem}",
                      file=sys.stderr)
                return False
            _held = path
            os.environ[HOLDING_THIS_LOCK] = str(os.getpid())
            return True

        if not announced:
            print(
                f"one_push_at_a_time: waiting to push {remote} {ref} - "
                f"{_describe(said)}. Waiting BEFORE the gate on purpose: a "
                "suite that runs now would certify a tree that will not be "
                "what `main` points at by the time it finishes.",
                file=sys.stderr,
            )
            announced = True
        if deadline is not None and time.time() >= deadline:
            print(
                f"one_push_at_a_time: gave up waiting for {_describe(said)}",
                file=sys.stderr,
            )
            return False
        if time.time() - last_said >= _SAY_EVERY:
            print(
                f"one_push_at_a_time: still waiting for {_describe(said)}",
                file=sys.stderr,
            )
            last_said = time.time()
        time.sleep(_POLL_SECONDS)


def release() -> None:
    """Drop the push lock, but only if it can be shown to be ours."""
    global _held
    path, _held = _held, None
    if path is None:
        return
    said = _gate.read_holder(path)
    if _gate.is_unreadable(said):
        print(
            "one_push_at_a_time: not releasing - the lock file is there and "
            "could not be read, so it cannot be shown to be ours.",
            file=sys.stderr,
        )
        return
    if said and int(said.get("pid") or 0) != os.getpid():
        print(
            "one_push_at_a_time: not releasing - the lock now belongs to "
            f"pid {said.get('pid')}",
            file=sys.stderr,
        )
        return
    path.unlink(missing_ok=True)
    os.environ.pop(HOLDING_THIS_LOCK, None)
