"""Stop the turn that is running, at the next round boundary.

Max, 2026-09-19, watching a turn spend 49 seconds on `Thinking` with the
composer telling him his next message would be queued until it finished:
*"stopping a prompt, stopping a plan, mid-prompt, mid-workway, mid-pathway.
To kind of shut down that current prompt and work session to fix or edit the
prompt you sent."* There was no way to do it. `longrun.stop` ends a RUN - the
plan runner working steps down - and a person watching one turn burn nine
rounds on the wrong idea has no run to stop.

## Where it stops, and why not sooner

At a ROUND BOUNDARY, and never inside a tool. A round is: ask the model, run
what it asked for, append the results. Between two rounds the conversation is
a complete record and every tool that started has finished and been written to
`events`. Inside one, a half-run `start_training` or a `run_project_command`
that has spawned a process is a thing this flag must not be able to sever -
killing it would leave the sandbox, the database and the transcript disagreeing
about what happened, which is the one failure this product is built to prevent.

So the promise is exact: **no further round will be asked for**. A tool already
running finishes and is recorded. In practice that is the time of one tool
call, and the turn ends with `stopped_by_the_person` rather than `answered`.

## Why a module-level set and not a database column

The flag is about a generator running in this process right now. A column
would outlive the process and stop a turn nobody asked to stop - and would
have to be cleared by the same code that sets it, which is the bug this
avoids by construction. `clear` runs in the conductor's own `finally`, so a
turn that ends for any other reason leaves nothing behind.

A stop that arrives when no turn is running is not an error. It is recorded
and cleared by the next turn's start, which is the right answer for a person
who pressed the button as the turn was ending.

## A MODEL CALL IS NOT A ROUND BOUNDARY, and it is where the press landed

Max, 2026-09-23: *"the stop button doesn't seem to actually stop."* The
boundary above is right for a TOOL and was wrong for the MODEL: a round is one
model call, and a local Ollama generation on this machine is 60 to 90
seconds. The flag was set and the reply went on writing itself in front of
him, because nothing read the flag until the model decided it was done.

A model call is not a thing the conversation can be left half-way through in
a bad state - what reached the person is already written to `events`, and the
rest was never going to exist. So a model call IS severed, in two ways, and
each has a case in `tests/test_a_stop_ends_the_model_call.py` that only it
can pass:

- **Between two pieces of the reply** (`watched`): the conductor reads the
  flag before it takes the next piece from the provider, and leaves the
  stream the moment it is set. What was released is kept as the reply.
- **While the model says nothing** (`cancel_with` / `sever`): a prompt being
  evaluated sends no bytes for tens of seconds, so there is no next piece to
  check between. The provider registers a way to close its in-flight request
  for the turn it is reading for, and `ask_to_stop` calls it. The socket is
  shut down and its handle closed rather than `response.close()`d, and that
  was measured, not assumed: on this machine `response.close()` from the route
  thread blocked for 29.5 s on the reader's buffer lock, and `shutdown` alone
  did not wake the blocked read at all; closing the handle woke it at once.

Tools are untouched by both: `watched` wraps the provider's stream and
nothing else, and `cancel_with` is only reachable from provider code.
"""
from __future__ import annotations

import socket
import threading
from contextlib import contextmanager
from typing import Any, Callable, Iterable, Iterator

#: Thread ids whose current turn has been asked to stop. Guarded because the
#: HTTP route sets it on one thread and the turn generator reads it on another.
_ASKED: set[int] = set()
_LOCK = threading.Lock()

#: Per thread id, the ways to close the model requests in flight for its turn,
#: keyed by a token so each provider call removes only its own.
_CANCELS: dict[int, dict[int, Callable[[], None]]] = {}

#: Which turn's provider code is running on THIS OS thread right now. Set only
#: for the length of one `next()` on a provider stream (`watched`), because the
#: provider cannot be told its thread id without changing every adapter's
#: signature - and every fake in the suite with it.
_READING = threading.local()

#: What `stream.end` says when this is why the turn ended. Distinct from
#: `round_cap` and `answered`: a person deciding they have seen enough is not
#: the harness running out of budget, and a score row that conflated the two
#: would read a deliberate stop as a stall.
ENDING = "stopped_by_the_person"


def ask_to_stop(thread_id: int) -> None:
    with _LOCK:
        _ASKED.add(int(thread_id))
        hooks = list(_CANCELS.get(int(thread_id), {}).values())
    # Outside the lock: a hook closes a socket, and nothing that touches the
    # network runs while every other turn's flag is locked out.
    for close in hooks:
        _call(close)


def was_asked(thread_id: int | None) -> bool:
    if thread_id is None:
        return False
    with _LOCK:
        return int(thread_id) in _ASKED


def clear(thread_id: int | None) -> None:
    if thread_id is None:
        return
    with _LOCK:
        _ASKED.discard(int(thread_id))
        _CANCELS.pop(int(thread_id), None)


@contextmanager
def reading(thread_id: int | None) -> Iterator[None]:
    """Provider code running inside this block is reading for `thread_id`'s turn."""
    before = getattr(_READING, "thread_id", None)
    _READING.thread_id = None if thread_id is None else int(thread_id)
    try:
        yield
    finally:
        _READING.thread_id = before


def cancel_with(close: Callable[[], None]) -> Callable[[], None]:
    """Register `close` as the way to end the model request the caller just opened.

    For the turn this OS thread is reading for (`reading`); outside a turn -
    a capability probe, a compaction, memory extraction - there is no stop to
    answer and nothing is registered. A request opened after the press is
    closed at once. Returns the release the provider calls when its request
    ends by itself, so a finished request is never "cancelled" later.
    """
    thread_id = getattr(_READING, "thread_id", None)
    if thread_id is None:
        return lambda: None
    token = id(close)
    with _LOCK:
        _CANCELS.setdefault(thread_id, {})[token] = close
        asked = thread_id in _ASKED
    if asked:
        _call(close)

    def release() -> None:
        with _LOCK:
            hooks = _CANCELS.get(thread_id)
            if hooks is not None:
                hooks.pop(token, None)
                if not hooks:
                    _CANCELS.pop(thread_id, None)

    return release


def watched(thread_id: int | None, stream: Iterable[Any]) -> Iterator[Any]:
    """`stream`, ended the moment this turn is asked to stop.

    The flag is read before each piece is asked for and again after it
    arrives, so a piece that lands after the press - including the error a
    severed socket raises - is never handed up as part of the reply. An
    exception from a stream that was asked to stop is the stop, not a fault.
    """
    pieces = iter(stream)
    try:
        while not was_asked(thread_id):
            try:
                with reading(thread_id):
                    piece = next(pieces)
            except StopIteration:
                return
            except Exception:  # noqa: BLE001 - re-raised unless it is the stop
                if was_asked(thread_id):
                    return
                raise
            if was_asked(thread_id):
                return
            yield piece
    finally:
        close = getattr(pieces, "close", None)
        if close is not None:
            close()


def sever(response: Any) -> None:
    """Close a streaming HTTP response from ANOTHER thread, without waiting on it.

    Shut the socket down (the peer - Ollama - sees the client go and stops
    generating) and close its handle, which is what wakes a read blocked on
    it here; `response.close()` would wait on the reader's buffer lock until
    the next byte arrived. A response with no socket to find (a test double)
    is closed the ordinary way.
    """
    raw = getattr(getattr(response, "fp", None), "raw", None)
    sock = getattr(raw, "_sock", None)
    if isinstance(sock, socket.socket):
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            socket.close(sock.detach())
        except OSError:
            pass
        return
    close = getattr(response, "close", None)
    if close is not None:
        close()


def _call(close: Callable[[], None]) -> None:
    """A hook that fails has still been asked; the stop itself must not fail."""
    try:
        close()
    except Exception:  # noqa: BLE001
        pass


def a_turn_is_running(thread_id: int) -> bool:
    """Is this thread mid-turn right now, by its own event log?

    THE ROUTE ASKS THIS BEFORE IT SETS THE FLAG, and that is what keeps a stop
    from outliving its turn without a clear-on-start that would defeat the
    press landing in the moment before the turn begins. A flag set only while
    a turn is running is a flag that turn's own `finally` will clear.

    Read backwards to the newest of `turn.started` / `stream.end`: a start with
    no end after it is a turn in flight.
    """
    from app import events

    for row in reversed(events.since(f"thread:{int(thread_id)}", limit=2000)):
        kind = row.get("kind")
        if kind == "stream.end":
            return False
        if kind == "turn.started":
            return True
    return False


def waiting() -> set[int]:
    """Every thread with a stop outstanding. For a test, and for a status route."""
    with _LOCK:
        return set(_ASKED)
