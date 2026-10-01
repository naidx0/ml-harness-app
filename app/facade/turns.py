"""Running a turn for their `session.prompt`, which does not wait for one.

The engine's own door (`POST /api/threads/{id}/turn`) runs the whole turn
inside the request and answers when it is over; the transcript reaches the
screen through the event log while it runs. Their protocol splits those two:
`session.prompt` admits the message and answers at once, and everything after
that arrives on the event stream. So the facade admits the message, answers,
and runs the SAME `conductor.run_turn` on a worker thread - no second turn
loop, no copy of any of its rules.

## One turn at a time per thread, and a queue of one

Their composer lets a person send while a reply is still being written. The
conductor reads the conversation when a turn starts, so a second message that
lands mid-turn is already in the transcript and simply needs another turn
after this one. Two messages that both land mid-turn need ONE more turn, not
two: the next turn reads both, and a second would answer nothing new. So a
thread holds at most one waiting turn; a prompt that arrives while one is
already waiting is folded into it.

## A turn that cannot start is still a record

`run_turn` raises `ConductorError` before it writes anything when no model is
connected. The old door turned that into a 409 for the page that asked; here
nobody is waiting on the request any more, so the refusal is written to the
thread's log as `turn.refused`, and the translator turns it into their failed
step - an error card that says "No model is connected", in the conversation,
where the person is looking. An exception from inside the turn that escapes
the conductor's own net is written the same way, as `turn.crashed`.
"""

from __future__ import annotations

import threading
from typing import Any

from app import events
from app.facade.translate import TURN_CRASHED, TURN_REFUSED

_GUARD = threading.Lock()
_LOCKS: dict[int, threading.Lock] = {}
_WAITING: set[int] = set()
_CANCELLED: set[int] = set()
_INVITED: set[int] = set()
_WORKERS: dict[int, list[threading.Thread]] = {}


def _lock_for(thread_id: int) -> threading.Lock:
    with _GUARD:
        return _LOCKS.setdefault(int(thread_id), threading.Lock())


def submit(thread_id: int, *, invite_goal_edit: bool = False) -> bool:
    """Run a turn on `thread_id` after any turn already running there.

    Returns `False` when a turn was already waiting and this prompt was folded
    into it, `True` when a new turn was queued.

    `invite_goal_edit` is the engine's own turn option (`TurnRequest`, CS9:
    the person invited the agent to edit the goal and todo this turn), which
    `/goal` sets. An invitation folded into a waiting turn is kept: that turn
    reads the message that carried it, so it carries the invitation too.
    """
    thread_id = int(thread_id)
    with _GUARD:
        if invite_goal_edit:
            _INVITED.add(thread_id)
        if thread_id in _WAITING:
            return False
        _WAITING.add(thread_id)
        worker = threading.Thread(
            target=_work, args=(thread_id,), name=f"facade-turn-{thread_id}", daemon=True
        )
        _WORKERS.setdefault(thread_id, []).append(worker)
    worker.start()
    return True


def _work(thread_id: int) -> None:
    from app import conductor

    with _lock_for(thread_id):
        # CLEARED AFTER THE LOCK, NOT BEFORE: until this turn has the thread,
        # a new prompt can still be folded into it, because the conductor has
        # not read the conversation yet.
        with _GUARD:
            _WAITING.discard(thread_id)
            cancelled = thread_id in _CANCELLED
            _CANCELLED.discard(thread_id)
            invited = thread_id in _INVITED
            _INVITED.discard(thread_id)
        try:
            if cancelled:
                return
            options = {"invite_goal_edit": True} if invited else {}
            for _row in conductor.run_turn(thread_id, **options):
                pass
        except conductor.ConductorError as error:
            events.append(TURN_REFUSED, {"detail": str(error)}, thread_id=thread_id)
        except Exception as error:  # noqa: BLE001 - the worker has no caller to raise to
            events.append(
                TURN_CRASHED,
                {"detail": f"{type(error).__name__}: {error}"},
                thread_id=thread_id,
            )
        finally:
            # NOTHING KEYED ON A THREAD ID OUTLIVES ITS LAST TURN. A thread id
            # is a counter that restarts at 1 in every database, so a lock left
            # behind here would be picked up by an unrelated thread 1 in the
            # next database this process opens. The lock goes only when no
            # other worker is registered for the thread, because a registered
            # worker may already hold a reference to it.
            with _GUARD:
                workers = _WORKERS.get(thread_id, [])
                current = threading.current_thread()
                if current in workers:
                    workers.remove(current)
                if not workers:
                    _WORKERS.pop(thread_id, None)
                    _LOCKS.pop(thread_id, None)


def cancel_waiting(thread_id: int) -> bool:
    """Drop the turn waiting behind the running one, if there is one.

    A person who presses stop while a reply is being written and a second
    message is queued behind it means stop: letting the queued turn start the
    moment the first one ends would answer a press of the stop button with a
    new reply. The queued message stays in the transcript; it is the turn that
    does not run.
    """
    with _GUARD:
        if int(thread_id) not in _WAITING:
            return False
        _CANCELLED.add(int(thread_id))
        return True


def busy(thread_id: int) -> bool:
    """Is a facade turn running or waiting on this thread?"""
    with _GUARD:
        return bool(_WORKERS.get(int(thread_id)))


def wait(thread_id: int, timeout: float = 30.0) -> bool:
    """Block until this thread's facade turns are done. For tests and shutdown.

    Returns `False` if any were still running when the timeout ran out.
    """
    with _GUARD:
        pending: list[Any] = list(_WORKERS.get(int(thread_id), []))
    for worker in pending:
        worker.join(timeout)
    return not any(worker.is_alive() for worker in pending)
