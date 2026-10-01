"""Where a fact came from, decided by the engine and never by the speaker.

`app/diagnosis.py` now refuses to open a gate on a fact whose origin the ledger
does not admit. That is the wall. THIS FILE IS THE DOOR IN IT, and a wall with
a door anybody can stamp is a wall with a hole. So everything here exists to
make one sentence structurally true:

    A MEASURED stamp is written by the code that ran the instrument, next to
    the reading, and by nothing else. Nothing a model says, and nothing a model
    puts in a tool call's arguments, can produce one.

The spec says it too, in `fact_origins.the_origin_is_never_supplied_by_the_thing
_being_checked`: *"If a future tool schema ever grows an `origins` argument a
model can fill, this whole block becomes decoration on that day."* That is a
warning about a future defect. This module is what makes the warning enforceable
rather than a note.

## The walls

Each one alone would be worth having; the point is that a laundering attempt has
to get through all of them.

WALLS 1 TO 4 ARE ALL ABOUT ONE QUESTION - is this number one the engine watched
being produced - AND FOUR ANSWERS TO ONE QUESTION IS NOT COVERAGE. A number got
through all four and was still wrong, because they say a measurement is REAL and
none of them says what it is real ABOUT. Wall 5 is the other question, and it is
stated where the walls are counted so the next person does not add a fifth answer
to the first one instead. See WALL 5 further down.

AND THEN A NUMBER GOT THROUGH FIVE. Wall 7 is the third question, added for the
same reason and stated in the same place: a self-graded eval score is real, is
about the right thing, and is a model's opinion of its own homework.

1. **Only a registered tool that DECLARED the fact may stamp it.** `measures=`
   on the `ToolSpec` is checked at registration against the fact ledger: the
   name must be a declared fact, and the fact's own `source:` must admit
   MEASURED. A tool declaring `measures=("prompt_iterations",)` is refused at
   import, because `prompt_iterations` is `source: ask` - it is a fact about the
   user's own week and no instrument on this machine can read it. Half of the
   six facts the adversary asserted their way through are unmeasurable *by any
   tool that could ever be written*, and that is enforced by the ledger rather
   than by a list here.

2. **A tool cannot stamp a value it was handed.** Every tool's arguments reach
   its handler MARKED as the caller's, anything derived from one carries the
   mark forward, and `Instrument.measured()` also refuses a value that is
   strictly equal to a number the caller sent. See THE SECOND WALL below, which
   has been an equality test, then a mark, and is now both - for reasons that
   are worth reading before changing it a third time.

3. **A tool that can mint cannot read what anybody said.** Two records hold what
   was said: the claim ledger and the transcript. The ledger's guard is on the
   TABLE, in `_ledger_rows` - the one function in this module that reads it - so
   `rows_for`, `ledger_view`, `assemble_facts` and anything written next year
   inherit it rather than remembering it. `app/events.py` carries the same
   refusal, because `conductor._run_tool` writes every tool call's raw arguments
   into the event log and nothing was guarding that at all.
   AND THE REFUSAL IS NOT THE LOAD-BEARING HALF. It reads a `ContextVar`, and a
   handler that starts a `threading.Thread` and reads on it meets nothing. So
   every non-MEASURED value either record hands back is MARKED on its way out -
   see `mark_as_a_claim` - and a mark goes where a context does not.

4. **The origin of a supplied value comes from the actor, and the actor comes
   from the call site.** `REGISTRY.call(..., actor=...)` is set by the conductor
   (MODEL) or by the control route (USER). It is not a tool argument, it is not
   in any tool's schema, and `RESERVED_ARGUMENTS` refuses any schema that grows
   a slot for it. A model filling `facts` fills values; it does not get to say
   what they are worth.

5. **A row is bound to what it is about.** Every fact declares a `scope:` beside
   its `type:` and its `source:`, and `record` refuses a thread-scoped row that
   names no thread. This is the wall that was missing, it was missing on the
   WRITE side of a table whose READ side had the rule right, and the cost was a
   real measurement of somebody else's file opening the first gate in a
   conversation that had never seen one.

6. **(Not here.)** `bounds=` in `app/tools/registry.py`, which is how a tool says
   which of its arguments could never be the answer. Numbered in the same series
   because a laundering attempt meets them in one sequence; it lives there
   because it is a property of a tool's declaration rather than of a stamp.

7. **A model's opinion is not a reading.** Every fact may declare `opinion_of:`
   in the ledger, and a fact that does may never carry MEASURED through any door
   here. This is a THIRD question, and it is stated as one so nobody adds a
   ninth answer to the first: walls 1 to 4 ask *is this number real*, wall 5 asks
   *real about what*, and this one asks **is this the kind of fact a reading can
   produce at all**. A judge score answers yes to both of the others - a tool
   ran, the engine watched, it is about this thread's eval set - and is still an
   opinion. See WALL 7 further down for the run that made it necessary.

## THE SECOND WALL, which has now been wrong twice in opposite directions

The wall says *a tool may not hand a caller's number back with a measurement
badge on it*. That is a statement about where a value CAME FROM, and it has been
implemented twice as a statement about something else.

**First as equality.** `measured()` refused any value equal, at the same type,
to a scalar in the call's arguments. Wrong in both directions at once:

* **Too weak.** Any transformation escaped. `int(argument)` (`"100"` -> `100`),
  `argument + 1`, `argument * 2`, `int(str(a) + str(b))` (`1, 20` -> `120`) all
  laundered freely, because a transformed value equals nothing it was handed.

* **Too strong, and live and user-facing.** `profile_dataset` with
  `max_rows=120` on a 120-row eval file counted 120 honestly and was refused,
  because the count equalled an argument. "Count this file, and stop after 120
  rows" returned HTTP 500, and G0 - the gate the whole tree stands on - could
  not be opened that way for a whole commit.

**Then as a mark, at `a9245c3`, and the trade was invisible.** Caller numbers
arrived as `CallerInt`/`CallerFloat` and every operation carried the mark
forward, so the transformation family shut and the false refusal ended. What
nobody measured until an adversary did it by hand is that the IDENTITY-preserving
family re-opened: `operator.index(n)`, `n.numerator`, `n.real`, `n.conjugate()`,
`int(Decimal(n))`, `json.loads(json.dumps(n))`, `len([0] * n)`,
`int.from_bytes(n.to_bytes(...))`. Every one of those goes through C that is
required to return an exact type, so the mark is gone and the number is intact.
**Two of them are one token, and nobody writing `argument.numerator` is attacking
anything.** Measured across twenty routes: 8 of 20 laundered at `bb21645`, 11 of
20 at `a9245c3`. The wall got better and worse in the same commit and every test
in the repository stayed green.

`tests/test_laundering_routes.py` exists so that cannot happen silently again.

## THE MECHANISM NOW: THREE CHECKS, ONE PROPERTY, AND ONE DECLARATION

Marks and equality fail on DISJOINT families, so running both is the obvious
answer. It is also nearly the right one - but "run both" is a description of a
pile, and what follows is meant to be a shape. The property is *the engine
watched this measurement happen*, and each check is one route by which a value
reaches the stamp without that being true:

1. **Identity - the mark.** `Registry.call` hands every handler its arguments as
   `CallerValue`s, and every operation those support returns a marked result,
   `str()` included. This is what catches arithmetic, parsing, formatting and
   splicing, none of which equals anything.

2. **Conversion - the memory.** `int(x)` and `float(x)` are required to return
   exact types, so a conversion breaks the chain. Both are wrapped to REMEMBER
   what they produced (`_converting`), and `measured()` refuses that number.
   Identity conversions are not remembered - `int(x)` on a caller's `int` gives
   back the same number of the same kind and says nothing.

3. **Quantity - the quarantine.** `measured()` refuses a value strictly equal,
   by type, to any scalar the caller sent, and to any number a caller's string
   spells. THIS IS THE CHECK THAT WAS TRADED AWAY, and it is the only one that
   can catch a rebuild which touched no marked object at all - through JSON,
   through bytes, through a file on disk, through another thread, through
   anything that re-encodes a number and hands back a fresh one.

And the declaration that lets (3) exist without the HTTP 500: **`bounds=` on the
tool**, next to `measures=`, naming the arguments that bound the work rather than
answer the question. `profile_dataset` declares `bounds=("max_rows",)` and is the
only tool in the product that needs to. See WALL 6 in `app/tools/registry.py`.

## WHY NOT SOMETHING BIGGER, WHICH WAS THE FIRST THING CONSIDERED

Two larger shapes were argued out before this one was built, because filtering a
class is weaker than making it unreachable, and both are recorded here so the
next person does not have to re-derive why they were not taken.

**A capability split - a minting tool receives only a handle, never a number.**
This is right, and it is half-built: a tool that takes no numeric argument has
no arithmetic and no rebuild route, and three of the four minting tools in this
product are already that shape. It cannot be *enforced* at registration, because
enforcing it means refusing a tool whose schema has an undeclared number, and
`tests/test_laundering_routes.py` requires those tools to REGISTER AND RUN and
write no row - a registration error would make twenty-nine attacks into
twenty-nine crashes, which is a different and much weaker statement. `bounds=`
is the enforceable half of the same idea: not "you may not receive a number" but
"say which of your numbers could never be the answer", checked in the same place
and read by the same reviewer.

**The engine performs the measurement; the tool only names what to measure.**
This is the real endpoint. If no tool code ever produced the number that gets
stamped, "the engine watched it happen" stops being a claim about a value's
history and becomes a fact about who ran the code, and every check above becomes
unnecessary. It is not reachable from here: `measure_baseline` computes
`correct / asked` in its own handler from replies it collected itself, so an
allowlist of engine-side measurement primitives would refuse G1's own tool, and
`route 10` proves a primitive allowlist is not sufficient anyway - a tool that
writes `n` lines to a file and then honestly counts them has used the
filesystem, which is as real a primitive as there is. THE SHAPE THAT WOULD WORK
is `measured()` taking a reading the engine minted rather than a number the tool
computed, which is a change to every call site in `app/tools/measure.py`. Worth
doing; not doable in a change that may not touch that file.

## WHAT THIS DOES NOT CATCH, WHICH IS THE ONLY REASON THE LAST REGRESSION WAS SEEN

The previous version of this docstring named its own gap, and that sentence is
the only reason anybody thought to measure the trade. So, exactly:

* **A tool that invents a constant.** Nothing here can stop a handler that
  stamps `500` having read nothing. Wall 1 is the answer - a tool stamps only
  what it declared, checked at registration where a reviewer can see it - and
  `test_no_tool_that_ships_converts_an_argument_into_a_measurement` reads the
  source of every shipped tool. This is asserted as a live route
  (`positive control A` in any probe of this module) rather than assumed.

* **A tool that stamps its own declared bound.** `bounds=("max_rows",)` takes
  `max_rows` out of the quarantine; the mark still refuses `max_rows` itself and
  anything derived from it, but `int(max_rows)` rebuilt through JSON is not
  refused. That is the price of the declaration, it is confined to arguments a
  tool has said are not answers, and it is visible at registration.

* **A number parsed out of message TEXT.** `events.messages_for` returns what
  was typed, as strings. A number that a minting tool digs out of a sentence
  with a regex is an unmarked `int` that equals nothing it was handed. Marking
  it is not possible - a marked string breaks `pathlib` - and the guard on that
  reader is context-scoped, so a worker thread walks round it.

* **A second process.** Everything here is one interpreter's memory. A number
  that leaves this process and comes back has only check (3) standing in its
  way, and check (3) only knows about the current call's arguments.

* **A boolean fact, mostly.** There are two of them and one opens the gate, so no
  check on the value can work. What stands there instead is a rule about the
  call: a boolean is refused in a call that was handed values and has measured
  nothing else. `measure_baseline` passes because it stamps two real scores
  first. A future tool that measures ONLY a boolean will hit this and should
  stamp the reading behind the flag - which G1's own predicate already demands.

**Two types are quarantined instead of marked, and here is exactly why.**

*`bool`.* CPython will not let `bool` be subclassed, so a caller's `True` cannot
carry a mark. It is compared.

*`str`.* A path is a string, and `pathlib` interns path components - `sys.intern`
requires an exact `str` and raises `TypeError: can't intern CallerStr`. Marking a
caller's path would break `Path(path)` in every tool that opens a file, which is
a worse defect than the one being fixed. So a caller's strings are compared:
against the value, and against `int()` and `float()` of themselves, which is the
`int(str_argument)` attack answered where the string still is one.

## Three actors, and why the middle one is the whole point

`app/diagnosis.py` distinguishes STATED - the user, in their own person - from
ASSERTED - a model, or nobody. That distinction only means something if
something upstream can tell those two apart, and the only thing that can is the
call site: the conductor knows it is executing what a model asked for, and
`POST /api/tools/{name}` knows it is executing what a person clicked.

    USER    -> STATED     the person whose project this is, answering
    MODEL   -> ASSERTED   the model, answering on their behalf
    HARNESS -> ASSERTED   our own fixed script, which is not a witness either

HARNESS is ASSERTED rather than a fourth origin because the unassisted script
(`conductor.UNASSISTED_SCRIPT`) runs *tools*, and what a tool measures is
MEASURED by measurement, not by who pressed go. The only thing the harness could
"supply" is something it made up, and there is no honest origin for that.

An unknown actor resolves to ASSERTED. Failing closed is the default here in the
same way a bare value is an assertion in the engine: the safe reading is the one
you get by forgetting.

## The ledger is append-only, because the transcript is the artifact

Every row records the fact, the value, the origin, the actor, the tool that
produced it and one sentence of how. Nothing is ever updated in place, so "we
measured 12 rows at 14:02 and the model had claimed 500 at 13:58" survives, and
`ledger_view()` can show a user why the engine believes what it believes.

Resolution across rows is by origin strength first and recency second:

    MEASURED > STATED > ASSERTED

A model cannot overwrite what the harness measured, and it cannot overwrite what
the person said. A person can correct themselves, because STATED against STATED
is broken by recency. A measurement can replace an older measurement, because
pointing the harness at a different file is a real thing to do.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Iterable

from app import dataquality, db, diagnosis
from app.diagnosis import (
    ASSERTED,
    DEFAULTED,
    Fact,
    MEASURED,
    ORIGINS,
    STATED,
    Settled,
)


# ---------------------------------------------------------------------------
# Actors.

#: The person whose project this is, acting through a control.
USER = "user"
#: The connected model, acting through a tool call.
MODEL = "model"
#: Our own fixed script, when the connected model cannot call tools.
HARNESS = "harness"

ACTORS = (USER, MODEL, HARNESS)

#: What an actor's own word is worth when it SUPPLIES a value. Measurement is
#: not in this table on purpose: measurement is not something an actor is, it is
#: something an instrument did.
SUPPLIED_ORIGIN = {USER: STATED, MODEL: ASSERTED, HARNESS: ASSERTED}

#: An actor nobody named. The conductor and the control route both pass one
#: explicitly; this is what a caller that forgot gets, and it is the pessimistic
#: reading rather than the convenient one.
DEFAULT_ACTOR = MODEL

#: Origin strength, for resolving two rows about the same fact.
#:
#: DEFAULTED IS IN THE TABLE AT ZERO AND IT IS NOT DECORATION. Under permission
#: `full` the harness writes a DEFAULTED row for an ask-fact it settled by rule
#: (`app/full_defaults.py`), and the whole promise of that is that the person
#: can overrule it by simply saying so. A `.get(origin, 0)` would have given the
#: same answer today and would have said nothing about whether that was meant;
#: written down, "a person's STATED word beats the harness's rule" is a row in
#: a table rather than a fallback nobody chose.
ORIGIN_RANK = {MEASURED: 3, STATED: 2, ASSERTED: 1, DEFAULTED: 0}


class MeasurementError(RuntimeError):
    """An attempt to stamp MEASURED on something that was not measured."""


class ScopeError(MeasurementError):
    """A row about one conversation, written where every conversation can see it.

    A SUBCLASS, so everything that already catches `MeasurementError` - the
    control route, the conductor, every test - keeps catching this without
    knowing it exists. It is a distinct name because it is a distinct event and
    the two want different answers at a boundary: a `MeasurementError` proper
    says a TOOL tried to launder something and is a defect in the tool (HTTP
    500), while this says the CALL did not say which conversation it belongs to
    and is an incomplete request (HTTP 400). See wall 5.
    """


class GeneratedRowsError(MeasurementError):
    """A fact measured off a file this harness generated rows into.

    A SUBCLASS for the same reason `ScopeError` is one, and a distinct name for
    the same reason: everything that already catches `MeasurementError` keeps
    working, and the one boundary that has to tell them apart can.

    THE DIFFERENCE THAT MATTERS IS WHOSE PROBLEM IT IS. A `MeasurementError`
    proper says a TOOL tried to launder a number, which is a defect in the tool
    and a 500. This says the CALL pointed at a file whose rows this product
    wrote by sampling, which is neither a defect nor a laundering attempt - it
    is a person doing the reasonable thing with the file they just made, and the
    answer is a refusal with the remedy in it (HTTP 422), not a stack trace.

    `docs/VISION.md` states the rule it enforces: synthetic data can never open
    a gate. See `Instrument._refuse_generated_rows`, which is wall 8.
    """


def origin_for(actor: str | None) -> str:
    """What this actor's own word is worth. Unknown actors are assertions."""
    return SUPPLIED_ORIGIN.get(actor or "", ASSERTED)


# ---------------------------------------------------------------------------
# What may ever be measured, read off the fact ledger rather than listed here.


def spec(ledger: diagnosis.Spec | None = None) -> diagnosis.Spec:
    """The fact ledger this question is about.

    THE PARAMETER IS THE WHOLE POINT AND THE DEFAULT IS THE DEBT. Seventeen
    sites in eight modules reach a ledger through this function, `resolves()`
    and `declared_fact()` without the string `default_spec` appearing anywhere
    near them - which is how a grep for one function name undercounted the
    coupling by two thirds (`docs/CAPABILITY_BLOCKS.md` §1.4). Threading the
    handle through these three is what lets all seventeen answer about the
    ledger the thread is actually running.

    `None` still means the default ledger, and it means it for two honest
    callers: registration, which happens at import before any conversation
    exists, and the standing walk over nothing, which has no thread. Every
    caller that HAS a thread should be passing the ledger the registry injected,
    and `Registry.call` is where it comes from.
    """
    return ledger if ledger is not None else diagnosis.default_spec()


def ledger_for_thread(thread_id: Any) -> diagnosis.Spec:
    """Which ledger this conversation is running. The one resolver.

    `threads.ledger` since migration v011, holding a repository-relative path,
    and `diagnosis.spec_at` turns it into a validated `Spec` exactly once per
    file. A thread id that names nothing gets the default ledger rather than an
    error: `Registry.call` is reached with `thread_id=None` by callers that
    genuinely have no conversation, and refusing there would break the tools a
    person can run before a thread exists. What must NOT happen is a thread that
    named a ledger getting a different one, and that cannot: an unreadable path
    raises out of `spec_at` with the path in the message.
    """
    if isinstance(thread_id, bool) or not isinstance(thread_id, int) or thread_id <= 0:
        return diagnosis.default_spec()
    from app import events  # local: events reads this module back

    row = events.get_thread(int(thread_id))
    if row is None:
        return diagnosis.default_spec()
    return diagnosis.spec_at(row.get("ledger"))


def declared_fact(name: str, ledger: diagnosis.Spec | None = None) -> dict[str, Any] | None:
    return spec(ledger).facts.get(str(name))


def is_measurable(name: str, ledger: diagnosis.Spec | None = None) -> bool:
    """Could any instrument, ever, open a gate with this fact?

    True when the fact exists and its declared `source:` admits MEASURED. False
    for every `source: ask` fact, which is the ledger saying "there is nobody to
    ask but the user" - see `fact_origins.why_ask_admits_stated`.
    """
    current = spec(ledger)
    decl = current.facts.get(str(name))
    if decl is None:
        return False
    return MEASURED in current.admissible_for(str(name))


# ---------------------------------------------------------------------------
# WALL 7: A MODEL'S OPINION IS NOT A READING.
#
# `admissible_for_gates` asks WHO SUPPLIED a value. The evaluation bench gave
# that question the honest answer and was still wrong, and the honesty is the
# whole difficulty: `run_eval` with `metric=model_graded` really does run a
# tool, this module really does watch it, and MEASURED's own definition - "a
# tool ran and the engine watched it produce this value" - is satisfied word for
# word. What the engine watched was a model being asked "were you right?".
#
# REPRODUCED BEFORE IT WAS FIXED, through the registered tool, on a scratch
# database, thirty rows, one connection answering both prompts:
#
#     baseline_score        0.967   MEASURED
#     exact_match           0.400   the same rows, the same run, computed free
#     G1_BASELINE_MEASURED  PASSED
#     verdict               NO_TRAIN__SHIP_AS_IS
#
# The product told somebody to ship a system that gets four rows in ten right,
# because the system said it was fine. Pushed the other way - a harsh judge - the
# same lever opens G1 on a model's opinion and routes toward training with all
# five gates green.
#
# The mitigations that already existed are why this was visible rather than
# buried, and they are also exactly why they were not enough: the `how=` line
# says "judging its own answers" and the report carries a `self_graded` block
# with the deterministic scores beside the judge's. GATES READ THE ORIGIN TOKEN,
# NOT THE PROSE. A sentence next to a number is for the person; the number is
# what the tree walks on.
#
# SO THE FACT ITSELF CARRIES THE ANSWER, in the ledger, next to its type and its
# source and its scope, and this module reads that declaration rather than
# holding a list. A model's grade is `judge_score`, declared `opinion_of: model`,
# and three doors are shut on it at once:
#
#   * `may_be_declared_measurable` refuses it, so no tool can name it in
#     `measures=` and the refusal lands at import rather than at runtime;
#   * `record` refuses a MEASURED row for it whichever door reached the table,
#     which is where wall 5 learned to stand and for the same reason;
#   * `Instrument.measured` refuses it by name AND refuses any value the same
#     call already recorded as an opinion - because a bench that filed the
#     judge's 0.967 as `judge_score` and then stamped the same 0.967 as
#     `baseline_score` would have done the whole thing anyway. That is wall 2's
#     rule turned inward: a tool may not stamp what its caller handed it, and it
#     may not stamp what A MODEL handed it either.
#
# `Instrument.opinion` is the door that IS open, and it stamps ASSERTED whoever
# the actor is. This does not refuse the judge - a model-graded eval runs,
# records, displays and routes, and some tasks genuinely cannot be graded by a
# rule. It refuses to call the result a measurement. The whole argument, the
# decision about a judge that is a DIFFERENT model, and what G1 wants instead,
# are in `fact_origins.a_models_opinion_is_not_a_reading` in the ledger.
#
# NOTHING HERE NAMES A FACT. `opinion_facts()` asks the ledger, the refusals are
# composed from the declaration, and a fact declared an opinion next year is
# covered on the day it is written down. This module has been bitten twice by a
# list that answered a question the ledger already answers; see wall 3.

#: The ledger key that says a fact is somebody's judgement rather than a reading.
OPINION_DECLARATION = "opinion_of"


def opinion_of(fact: str, ledger: diagnosis.Spec | None = None) -> str | None:
    """Whose judgement this fact is, or `None` when it is a reading.

    `model` is the only value the ledger uses today. It is returned rather than
    reduced to a boolean because the refusals say it out loud, and "a model said
    so" and "a reviewer said so" would want different sentences on the day the
    second one exists.
    """
    declared = (declared_fact(fact, ledger) or {}).get(OPINION_DECLARATION)
    return str(declared) if declared else None


def is_an_opinion(fact: str, ledger: diagnosis.Spec | None = None) -> bool:
    """Does the ledger declare this fact somebody's judgement?"""
    return opinion_of(fact, ledger) is not None


def opinion_facts(ledger: diagnosis.Spec | None = None) -> tuple[str, ...]:
    """Every fact the ledger declares an opinion. Asked, never listed."""
    current = spec(ledger)
    return tuple(sorted(name for name in current.facts if is_an_opinion(name, current)))


def _opinion_refusal(
    fact: str, *, tool: str | None, doing: str, ledger: diagnosis.Spec | None = None
) -> str:
    """Why an opinion fact may not be measured, in the ledger's own terms."""
    name = str(fact)
    whose = opinion_of(name, ledger) or "somebody"
    who = tool or "a tool"
    return (
        f"{who!r} tried to {doing} for {name!r}, which the ledger declares "
        f"opinion_of: {whose}. That declaration means the value is a JUDGEMENT "
        f"made by {'a ' + whose if whose == 'model' else whose} rather than a "
        "reading taken by this harness, and a judgement can never be MEASURED - "
        "not because nothing ran, but because what ran produced an opinion. A "
        "self-graded 96.7% and a rule-graded 40.0% over the same thirty rows of "
        "the same run were the same fact until this wall existed, and G1 opened "
        "on the first one. Record it with Instrument.opinion, which stamps "
        "ASSERTED: it is carried, displayed and routed on, and it never opens a "
        "gate. See fact_origins.a_models_opinion_is_not_a_reading in "
        f"{_ledger_name(ledger)}."
    )


def may_be_declared_measurable(name: str, ledger: diagnosis.Spec | None = None) -> bool:
    """May a tool in THIS harness declare `measures=(name,)`?

    Stricter than `is_measurable`, and the gap is deliberate rather than a bug
    in one of them.

    AN OPINION FACT IS REFUSED HERE FIRST, at import, before any call is made.
    `is_measurable` reads `admissible_for_gates`, which answers a question about
    ORIGINS, and an opinion fact's problem is not its origin - see WALL 7 above.
    Refusing at registration is what makes the property cheap to hold: a tool
    that cannot name the fact cannot forget the rule.

    The ledger admits MEASURED for `source: ask` - `admissible_for_gates` says
    `ask: [MEASURED, STATED]` - and it is right to. If the harness itself drove
    the five prompt rewrites, it WATCHED them, and a measurement of the user's
    own week is a stronger thing than the user's memory of it, not a weaker one.

    Nothing in this harness drives that work today. So a tool declaring
    `measures=("prompt_iterations",)` right now would be claiming to have
    observed something no code here observes, and the honest answer is to refuse
    it at registration rather than to trust that whoever wrote it meant it. THIS
    IS THE ONE PLACE TO WIDEN when a tool genuinely runs the prompt loop: widen
    it there and then, with the tool in front of you, rather than leaving the
    door open in advance for a tool nobody has written.
    """
    current = spec(ledger)
    return (
        is_measurable(name, current)
        and not is_an_opinion(name, current)
        and (declared_fact(name, current) or {}).get("source") != "ask"
    )


# ---------------------------------------------------------------------------
# WALL 9: A FACT SAYS WHICH INSTRUMENT MAY MEASURE IT.
#
# `docs/PHASES.md` carried this as a debt for three days, in its own words:
#
#     "Any tool may claim any fact. `may_be_declared_measurable` is checked per
#      FACT and never per INSTRUMENT, so nothing structural stops a tabular tool
#      stamping a text-eval gate fact. Only care has prevented it so far. Fixing
#      this makes a whole class of defect unaskable."
#
# THE DEFECT IS NOT HYPOTHETICAL AND IT IS NOT ABOUT MALICE. Every wall above
# asks *where did this number come from* - the mark, the quarantine, the
# conversion, the file. None of them asks *is this the kind of tool that could
# have read this*. So `fit_a_tree_model`, which scores a decision tree on a
# table, could declare `measures=("baseline_score",)`, honestly compute an
# accuracy, honestly stamp it, and open G1 - the gate that says a text baseline
# has been measured - with a number about a CSV. Every provenance check passes
# because every provenance check is satisfied: a tool ran, this module watched
# it, the number is its own. It is the wrong instrument, and until now nothing
# in this product could say so.
#
# THE DECLARATION IS THE LEDGER'S AND IT NAMES A CAPABILITY, NOT A TOOL.
#
#     eval_size_n: {type: int, source: inspect, scope: thread, default: 0,
#                   measured_by: [data.eval_set.count, data.dataset.profile]}
#
# Capabilities rather than tool names for the reason `contract.capabilities.needs`
# already uses them one layer out: a ledger is domain knowledge and a tool name
# is an implementation detail, so a rename would silently unbind every fact in
# the file. `app/tools/blocks.py` publishes the closed vocabulary and validates
# every name in it, which is the same wall `provides=` gets.
#
# TWO CHECKS, AND THE FIRST ONE IS WHERE A PERSON READS IT. Registration refuses
# a tool whose `provides=` intersects nothing the fact admits, so the wrong
# instrument does not register; `measured()` refuses the same thing per call,
# because registration checks the union of every shipped ledger and only a call
# has a thread and therefore a domain. That is the same pair `measures=` itself
# already gets, for the same reason.
#
# AN UNDECLARED FACT IS NOT REFUSED, and that is a limit rather than a hole. A
# fact with no `measured_by:` is one the ledger has not spoken about, and
# reading silence as "nothing may measure this" would refuse every stamp in the
# product on the day this shipped. What closes the gap is a ratchet rather than
# a default: `tests/test_a_fact_names_its_instrument.py` sweeps both shipped
# ledgers and requires that every fact SOME REGISTERED TOOL MEASURES declares
# `measured_by:`, so a new instrument that forgets it reddens the run that adds
# it. Silence is legal exactly where nothing is claiming to measure.

#: The ledger key. One string or a list of them, each a published capability.
INSTRUMENT_DECLARATION = "measured_by"


def measured_by(fact: str, ledger: diagnosis.Spec | None = None) -> tuple[str, ...]:
    """The capabilities this ledger admits as instruments for this fact.

    Empty means the ledger HAS NOT SAID - never "nothing may measure it". See
    the wall above for why the difference is load-bearing and what closes it.
    """
    declared = (declared_fact(fact, ledger) or {}).get(INSTRUMENT_DECLARATION)
    if not declared:
        return ()
    if isinstance(declared, str):  # one capability, written without the brackets
        declared = [declared]
    return tuple(str(name) for name in declared if str(name).strip())


def facts_naming_an_instrument(ledger: diagnosis.Spec | None = None) -> tuple[str, ...]:
    """Every fact this ledger binds to an instrument. Asked, never listed."""
    current = spec(ledger)
    return tuple(sorted(name for name in current.facts if measured_by(name, current)))


def the_right_instrument(
    fact: str, provides: Iterable[str], ledger: diagnosis.Spec | None = None
) -> bool:
    """Is a tool declaring these capabilities one this fact admits?

    True when the ledger has not said, which is the permissive half stated in
    one place rather than repeated at both call sites.
    """
    admitted = set(measured_by(fact, ledger))
    return not admitted or bool(admitted & {str(name) for name in provides})


def wrong_instrument_reason(
    fact: str,
    *,
    tool: str | None,
    provides: Iterable[str],
    doing: str,
    ledger: diagnosis.Spec | None = None,
) -> str:
    """Why this tool is not an instrument for this fact, with both sets named."""
    name = str(fact)
    who = tool or "a tool"
    admitted = measured_by(name, ledger)
    declared = sorted(str(item) for item in provides)
    return (
        f"{who!r} tried to {doing} for {name!r}, and it is not an instrument for "
        f"it. {_ledger_name(ledger)} declares measured_by: {list(admitted)} on "
        f"that fact, and this tool provides {declared or 'nothing'}. THE NUMBER "
        "MAY BE PERFECTLY REAL AND THAT IS THE POINT: every other wall here asks "
        "where a value came from, and all of them pass for a tool that genuinely "
        "read something - of the wrong kind, about the wrong subject, and then "
        "opened a gate with it. A fact names the capability that can read it so "
        "that being the wrong instrument is a refusal rather than a matter of "
        "care. If this tool really can read it, add its capability to that fact's "
        "measured_by in the ledger, where a reviewer sees the claim."
    )


def declarable_in_any_ledger(name: str) -> bool:
    """May a tool in this harness declare `measures=(name,)` for ANY ledger it ships?

    THE REGISTRATION WALL'S QUESTION, AND IT IS A DIFFERENT ONE FROM THE CALL'S.
    A tool registers at import, before any conversation exists, so there is no
    thread and no ledger to ask - and asking the default one refused a plausible
    trace reader with a sentence that was correct at every step and consulted the
    wrong file at every step (`docs/CAPABILITY_BLOCKS.md` §1.3). `has_traces` is
    not a fact the ML ledger has ever heard of, and it is a declared inspect fact
    of `docs/ledgers/ai_engineering.yaml`, which ships in the same product.

    So registration asks whether SOME ledger declares it measurable, and the
    narrower question - may this instrument stamp it in THIS conversation - is
    asked per call, against the ledger that thread is running, by
    `Instrument.measured`. Widening the import-time check does not widen what may
    be stamped: it moves the refusal from the day a tool is written to the turn
    it is wrongly used, which is where the answer can name the domain.
    """
    return any(
        may_be_declared_measurable(name, diagnosis.spec_at(path))
        for path in diagnosis.known_ledgers()
    )


def ledgers_declaring(name: str) -> tuple[str, ...]:
    """Every ledger in this product whose facts include this name, as written.

    THE HALF THAT TURNS A WALL INTO A DOOR. A refusal that says only "this
    ledger has never heard of it" leaves the reader unable to tell a typo from a
    fact belonging to a domain they are not in, and those want opposite next
    moves. Derived from `known_ledgers()`, so a third ledger is covered on the
    day the file lands rather than on the day somebody remembers this function.
    """
    return tuple(
        diagnosis.spec_at(path).as_written
        for path in diagnosis.known_ledgers()
        if str(name) in diagnosis.spec_at(path).facts
    )


def _ledger_name(ledger: diagnosis.Spec | None) -> str:
    """How to refer to a ledger in a sentence a person reads. See `Spec.as_written`."""
    return spec(ledger).as_written


def unmeasurable_reason(name: str, ledger: diagnosis.Spec | None = None) -> str:
    """Why `measures=(name,)` was refused, in the ledger's own terms."""
    current = spec(ledger)
    decl = current.facts.get(str(name))
    if decl is None:
        elsewhere = ledgers_declaring(name)
        return (
            f"{name!r} is not a declared fact. Fact names come from the ledger in "
            f"{_ledger_name(current)}, and a tool cannot measure something that "
            "ledger has never heard of."
            + (
                ""
                if not elsewhere
                else (
                    f" It IS declared in {', '.join(elsewhere)}, which is a "
                    "different domain's knowledge - a thread running this ledger "
                    "is not asking that question."
                )
            )
        )
    if is_an_opinion(str(name), current):
        return _opinion_refusal(
            str(name), tool=None, doing="declare measures=", ledger=current
        )
    source = decl.get("source")
    if source == "ask":
        return (
            f"{name!r} is declared source: ask - it is a fact about the user's own "
            "history, and nothing in this harness watches that happen. A tool that "
            "stamped it would be reporting on somebody's week from the outside. "
            "See evidence.may_be_declared_measurable for the one case that would "
            f"change this. {current.substantiation(str(name)).strip()}"
        )
    admissible = sorted(current.admissible_for(str(name)))
    return (
        f"{name!r} is declared source: {source!r}, which admits {admissible}. "
        "No instrument can produce it, so no tool may claim to. "
        f"{current.substantiation(str(name)).strip()}"
    )


# ---------------------------------------------------------------------------
# WALL 5: A MEASUREMENT IS BOUND TO WHAT IT MEASURED.
#
# The four walls above are all about ORIGIN - is this number one the engine
# watched being produced. Every one of them held, and a number got through them
# all and was still wrong, because they answer "is this real" and nothing
# answered "real about WHAT".
#
# `fact_evidence.thread_id` is nullable, and `rows_for` reads a NULL as machine
# scope: the hardware in this box is the hardware in this box, so every
# conversation may see it. That read is right and it stays. The WRITE side had no
# rule at all - `record()` took `thread_id=None` for any fact, and
# `POST /api/tools/{name}` made the argument optional - so `measure_eval_set`
# called without one counted a real file honestly and filed the answer where
# every conversation on the machine could read it. Reproduced end to end: thread
# 4242, which had never been shown a file, saw `Fact(value=120, origin=
# 'MEASURED')` and G0_EVAL_SET - the first gate, the one the whole tree stands on
# - opened on it.
#
# AND `rows_for`'s OWN DOCSTRING NAMED THIS FAILURE, with the same fact and the
# same number, before it happened. Somebody saw it, wrote it down, guarded the
# read path and left the write path open. A rule enforced on one side of a table
# is a rule that is not enforced.
#
# So: A FACT HAS A SCOPE, the ledger declares it per fact the way it already
# declares a type and a source, and `record` refuses a thread-scoped row that
# names no thread. Two words, `machine` and `thread`, and the whole vocabulary
# with its argued-out third option is in `fact_scopes` in
# docs/diagnosis_engine.yaml rather than here.
#
# NOTHING BELOW IS A LIST OF FACTS. `scope_of` reads the declaration, the
# machine-scope set is derived by asking every fact its scope, and the gates a
# refusal names come out of the engine's own parsed gate rows. A list here would
# be a second answer to a question the ledger already answers, and this module
# has been bitten by exactly that twice - see wall 3.

#: A fact about this computer: same box, same answer, every conversation. A row
#: at this scope may be written with no thread and is then visible everywhere.
MACHINE = "machine"

#: A fact about one project in one conversation. A row at this scope must carry
#: the thread it belongs to.
THREAD = "thread"

SCOPES = (MACHINE, THREAD)

#: What a fact whose scope nobody declared counts as - and what a name the ledger
#: has never heard of counts as. The pessimistic reading, for the same reason
#: `DEFAULT_ACTOR` is MODEL and an unattributed value is ASSERTED: the safe
#: answer is the one you get by forgetting, and widening has to be typed.
DEFAULT_SCOPE = THREAD


def scope_policy(ledger: diagnosis.Spec | None = None) -> dict[str, Any]:
    """The `fact_scopes` block, verbatim. Empty if a spec predates it."""
    policy = spec(ledger).raw.get("fact_scopes")
    return policy if isinstance(policy, dict) else {}


def scope_of(fact: str, ledger: diagnosis.Spec | None = None) -> str:
    """Where a row about this fact belongs. Read off the ledger, never listed.

    THREAD for anything the ledger does not declare, anything it declares with no
    scope, and anything whose scope is not a word this module knows. All three are
    the same state of knowledge - nobody said this is true of the machine - and
    the one direction this must never fail in is open.
    """
    decl = declared_fact(fact, ledger)
    if decl is None:
        return DEFAULT_SCOPE
    declared = decl.get("scope")
    return declared if declared in SCOPES else DEFAULT_SCOPE


def is_machine_scoped(fact: str, ledger: diagnosis.Spec | None = None) -> bool:
    """May a row about this fact be written with no thread at all?"""
    return scope_of(fact, ledger) == MACHINE


def facts_at_scope(scope: str, ledger: diagnosis.Spec | None = None) -> tuple[str, ...]:
    """Every declared fact at one scope, sorted. Derived by asking each of them."""
    current = spec(ledger)
    return tuple(
        sorted(name for name in current.facts if scope_of(name, current) == str(scope))
    )


def gates_that_read(fact: str, ledger: diagnosis.Spec | None = None) -> tuple[str, ...]:
    """The gates whose `passes_when` rows read this fact, sorted.

    From `Spec.gate_row_facts`, which the engine parses out of each row's
    `requires:` expression at load time. This is what lets the refusal below say
    "G0_EVAL_SET reads it" about `eval_size_n` and stay silent about a fact no
    gate reads, without anybody maintaining the mapping.
    """
    name = str(fact)
    return tuple(sorted({
        gate_id for (gate_id, _row), names in spec(ledger).gate_row_facts.items()
        if name in names
    }))


def _scope_refusal(
    fact: str, *, tool: str | None, origin: str, ledger: diagnosis.Spec | None = None
) -> str:
    """Wall 5's refusal, and it names the door.

    The caller who hits this is precisely the caller who does not know the
    argument exists - the whole defect was that `thread_id` could be left off and
    nothing said so. `fact_name_help` set the standard for the other refusal in
    this module: say what would have worked, out of the ledger's own
    declarations. This says which argument is missing, where that argument
    arrives (not in the tool's schema, and deliberately not), what THIS fact
    would have done had it been let through, and the facts that genuinely may be
    written with no thread.
    """
    name = str(fact)
    who = f"{tool!r}" if tool else "something"
    decl = declared_fact(name, ledger)
    lines = [
        f"{who} tried to record {name!r} as {origin} with no thread_id, and "
        "nothing here can accept that."
    ]
    if decl is None:
        lines.append(
            f"{name!r} is not a declared fact, so this ledger cannot say it is "
            "true of the machine, and a fact nobody declared is read as belonging "
            "to one conversation - the safe answer is the one you get by "
            "forgetting."
        )
    else:
        lines.append(
            f"{name!r} is declared scope: {THREAD} in {_ledger_name(ledger)}. "
            "It is a fact about one project in one conversation, and a row "
            "written with no thread is MACHINE scope - evidence.rows_for shows "
            "those to every thread on this machine."
        )
    gates = gates_that_read(name, ledger)
    if gates:
        lines.append(
            "THIS IS NOT A SMALLER MISTAKE THAN AN INVENTED NUMBER. A value this "
            "row carries may well have been really measured; filed here it would "
            f"open {', '.join(gates)} in a conversation where nobody counted "
            "anything, and a gate opened on somebody else's file is the exact "
            "failure the five gates exist to prevent."
        )
    lines.append(
        "thread_id is the missing argument and it arrives ON the call rather "
        "than IN it: POST /api/tools/<name> takes it in the request body beside "
        "`arguments`, and app/conductor.py passes it to REGISTRY.call from the "
        "turn it is running. No tool schema may declare it - see RESERVED_ARGUMENTS "
        "- because which conversation a call belongs to is a property of the door, "
        "not of anything a model can type."
    )
    machine = facts_at_scope(MACHINE, ledger)
    lines.append(
        "The facts that may be written with no thread are the machine's own: "
        + (", ".join(machine) if machine else "none are declared")
        + ". They are the same in every conversation because the box is the same "
        "box. Nothing was recorded."
    )
    return " ".join(lines)


def thread_is_required_by(tool: str) -> str:
    """Why `POST /api/tools/{tool}` needs a thread, or "" if it does not.

    THE ROUTE'S HALF OF WALL 5, and the reason it is a separate answer from
    `record`'s: a call that forgot `thread_id` is an incomplete request, not a
    tool that laundered something, and the two deserve different status codes and
    different sentences. This one can be given BEFORE the tool runs, so it can
    say what to send instead; `record`'s is the wall, and it stands whichever
    door the call came through, including from Python where there is no door.

    Derived from the tool's own declarations and the ledger's scopes:

      * a tool that takes no instrument writes no fact and needs no thread -
        `record` is reachable only through `Instrument`;
      * a tool any of whose `measures=` facts is thread scope needs one, and the
        refusal names the fact, because that is the specific true answer;
      * a tool that declares `writes=("facts",)` needs one anyway, because it can
        reach `Instrument.supplied` with ANY name in the ledger - `measures=`
        bounds what may be STAMPED and bounds nothing about what may be SAID, and
        registration does not check the second.

    THE SPECIFIC CHECK RUNS FIRST so a tool that both measures and writes gets
    told which fact, rather than the general sentence about all of them.

    `inspect_hardware` is the one tool in the product that passes, and it is the
    reason `thread_id` is still optional at all: four facts, all of them the
    machine's, `writes=()`. A person looking at their own hardware page has no
    conversation open and should not have to invent one.
    """
    from app.tools.registry import REGISTRY  # local: registry imports this module

    candidate = REGISTRY.get(str(tool))
    if candidate is None or not candidate.wants_instrument:
        return ""
    leaking = sorted(f for f in candidate.measures if scope_of(f) != MACHINE)
    if leaking:
        return (
            f"{candidate.name} measures {', '.join(leaking)}, which the ledger "
            f"declares scope: {THREAD} - true of one project in one conversation "
            "and of no other - and this call did not say which conversation to "
            "file the reading under. A row written with no thread is machine "
            "scope, and every thread on this machine then reads it: that is how "
            "a count of somebody else's file opens the first gate in a "
            "conversation that has never seen one."
        )
    if "facts" in tuple(candidate.writes):
        return (
            f"{candidate.name} writes facts and this call did not say which "
            "conversation they belong to. Its `measures=` does not bound this: a "
            "tool that writes facts reaches Instrument.supplied, which takes any "
            f"name in the ledger, and all but {len(facts_at_scope(MACHINE))} of "
            f"those are declared scope: {THREAD}. A row written with no thread is "
            "machine scope and every thread on this machine reads it."
        )
    return ""


# ---------------------------------------------------------------------------
# WALL 5, THE SECOND HALF: A THREAD ID MUST IDENTIFY A REAL CONVERSATION.
#
# The first half made a thread-scoped row say WHICH conversation it belongs to.
# It checked that the argument was PRESENT and nothing checked that it NAMED
# anything, which is the same omission one notch in: `record(thread_id=1)` on a
# database with no conversations in it wrote a row against a conversation that
# did not exist, and SQLite hands out rowids from 1, so THE FIRST CONVERSATION
# THE USER EVER OPENS INHERITS IT. Reproduced end to end on an empty database:
# seed `eval_size_n=120` at thread 1, open the first thread, and it reads
# `Fact(value=120, origin='MEASURED')` having never been shown a file - the
# control answers BLOCKED__BUILD_EVAL_SET with G0 FAILED, the seeded thread
# answers TRAIN__LORA_SFT with all five gates PASSED. `0`, `-1` and `999999`
# were accepted too.
#
# THE PRODUCT ALREADY KNEW HOW TO SAY THIS. `storm.declare` refuses with "there
# is no thread {id}" and `events.add_message` returns `None` rather than write a
# message into nothing. Two siblings of this table check the parent row and the
# ledger did not, so this is not a new rule - it is the ledger learning what the
# rest of the product already does.
#
# THE MECHANISM IS BOTH A FOREIGN KEY AND THIS CHECK, and the argument for both
# rather than either is the argument this whole file keeps re-learning:
#
#   * A FOREIGN KEY IS THE PROPERTY. `fact_evidence.thread_id REFERENCES
#     threads(id)` is enforced by the store on every INSERT from every process,
#     through every route, forever, and cannot be forgotten by a caller written
#     next year - which is exactly what the last fix wanted and did not get. It
#     is also the only half that holds against the routes `record()` does not
#     cover, and this module has been bitten twice by guarding the function
#     somebody remembered instead of the table.
#
#   * A FOREIGN KEY CANNOT SAY ANYTHING. It fails with `FOREIGN KEY constraint
#     failed`, which names no argument, no fact, no gate and no door - and the
#     caller who trips this is precisely the caller who did not know the id had
#     to mean something. `_scope_refusal` set the standard for the sibling case
#     and `_no_such_thread_refusal` meets it.
#
#   * NEITHER OF THEM REFUSES `0` ON ITS OWN. A foreign key refuses `0` only
#     because no `threads` row has that id, which is true of every database this
#     product creates and is not a rule. The CHECK constraint beside the foreign
#     key, and the first clause below, say it as a rule: a conversation id is a
#     positive integer, because that is what SQLite hands out.
#
# WHAT THE FOREIGN KEY COSTS, stated rather than discovered later. It constrains
# the ORDER rows may be written in - a fact row cannot be committed before the
# conversation it belongs to - which is the true shape of the product and is why
# no shipped call site had to change, but it is a real constraint on any future
# bulk import that wants to write facts first. And it constrains the MIGRATION
# path: `PRAGMA foreign_keys` is a no-op inside a transaction and every migration
# here runs inside one, so the rebuild in migration 7 cannot switch enforcement
# off, and any row already pointing at a conversation that is not there aborts
# it. Migration 7 therefore quarantines those rows first, in migration 6's own
# style and for migration 6's own reason: they are somebody's real measurements
# and what is missing is where they belong, which is not something a migration
# can supply.


def names_a_conversation(thread_id: Any) -> bool:
    """Does this id identify a conversation that exists on this machine?

    Not "is it an integer" and not "is it not None" - both of those were already
    true of `1` on a database with no conversations in it. `events.get_thread`
    is the same reader `storm.declare` asks, so there is one answer to "is there
    a thread N" rather than a second one kept here.

    Only its truthiness is used and nothing it returns is passed on. A thread row
    carries a title somebody TYPED, and this function is reachable from inside
    `Instrument.measured` where wall 3 says a minting tool may not see what
    anybody said. Existence is not content.
    """
    if isinstance(thread_id, bool) or not isinstance(thread_id, int):
        return False
    if int(thread_id) <= 0:
        return False
    from app import events  # local: events reads this module back

    return events.get_thread(int(thread_id)) is not None


def _no_such_thread_refusal(
    thread_id: Any, *, fact: str, tool: str | None, origin: str
) -> str:
    """The refusal for an id that names nothing, and it names the door.

    Same standard as `_scope_refusal`: what was tried, why the id is not one,
    what this particular fact would have opened had it been let through, and
    where a real thread id comes from. The second paragraph is the headline -
    a row filed against a conversation that does not exist yet is a row the NEXT
    conversation inherits, because ids are handed out in order from 1.
    """
    name = str(fact)
    who = f"{tool!r}" if tool else "something"
    lines = [
        f"{who} tried to record {name!r} as {origin} against thread "
        f"{thread_id!r}, and there is no such conversation on this machine."
    ]
    if isinstance(thread_id, bool) or not isinstance(thread_id, int):
        lines.append(
            f"A conversation id is an integer and {type(thread_id).__name__} is "
            "not one."
        )
    elif int(thread_id) <= 0:
        lines.append(
            "A conversation id is a POSITIVE integer - SQLite hands them out in "
            f"order from 1 - so {thread_id} could never have named one, on this "
            "database or on any other."
        )
    else:
        lines.append(
            "THIS IS THE DANGEROUS DIRECTION AND NOT THE HARMLESS ONE. Ids are "
            "handed out in order from 1, so a row filed against a conversation "
            "that does not exist YET is a row the next conversation INHERITS: "
            f"write {name!r} against thread {thread_id} on an empty database and "
            "the first conversation the user ever opens reads it, having been "
            "shown nothing."
        )
    gates = gates_that_read(name)
    if gates:
        lines.append(
            f"{name!r} is read by {', '.join(gates)}, so what that conversation "
            "would inherit is an opened gate it did nothing to open."
        )
    lines.append(
        "A thread id comes from a conversation that was started: POST "
        "/api/threads mints one, POST /api/tools/<name> takes it in the request "
        "body beside `arguments`, and app/conductor.py passes the id of the turn "
        "it is running. app/storm.py and app/events.py already refuse an id that "
        "names nothing - this ledger is saying the same sentence they do."
    )
    lines.append("Nothing was recorded.")
    return " ".join(lines)


def thread_id_help(tool: str) -> dict[str, Any]:
    """What a thread-less call to this tool should have sent, for the route.

    Shaped like `fact_name_help`: the refusal, the argument that was missing,
    where it goes, and - because the honest next step is this product's voice -
    how to get one if the caller has none.
    """
    return {
        "missing": "thread_id",
        "detail": thread_is_required_by(tool),
        "send": {
            "thread_id": "the id of the conversation these facts belong to",
            "note": (
                "It goes in the request body beside `arguments`, never inside "
                "them. There is no tool argument for it and there is not meant "
                "to be one: which conversation a call belongs to is a property "
                "of the door it came through."
            ),
        },
        "if_you_have_no_thread": (
            "POST /api/threads to start one, or run a tool that only reads the "
            "machine. The facts that may be recorded with no conversation at all "
            "are " + ", ".join(facts_at_scope(MACHINE)) + " - this box's own "
            "hardware, which is the same in every conversation."
        ),
        "the_ledger": {
            "file": _ledger_name(None),
            "block": "fact_scopes",
            "machine_scoped_facts": list(facts_at_scope(MACHINE)),
            "counted": "read off the loaded ledger, not remembered",
        },
    }


# ---------------------------------------------------------------------------
# Wall 2: a caller's value is marked as the caller's, by construction.
#
# The mark is the type. `CallerInt(120)` is an `int` everywhere an int is
# wanted - it indexes, it compares, it serialises, it binds to a SQLite
# parameter - and it is not an ordinary int at the one place that matters,
# which is `Instrument.measured`. Every operation these types support returns a
# marked result, so a tool that adds one, doubles it, parses it, formats it or
# pulls it out of a nested argument is still holding the caller's value, and the
# stamp still refuses it. NO NUMBER IS COMPARED TO ANY NUMBER, which is what
# lets an honest count that happens to equal an argument go straight through.
#
# The two edges are below and both are stated where they are implemented: a
# caller's strings and booleans cannot be marked, so those two are compared
# (`COMPARED_TYPES`), and `int()`/`float()` will not carry a mark across, so
# those two are remembered (`_converting`).


class CallerValue:
    """Marker base: somebody SUPPLIED this value; nobody measured it.

    Not an ABC and not a wrapper. A `CallerValue` IS the value - the subclasses
    below inherit from `int`, `float` and `str` - so marking a caller's
    arguments changes nothing about how a handler uses them. The only code in
    the product that asks whether a value is marked is `Instrument.measured`.

    THE MARK RIDES ON THE VALUE, AND THAT IS THE POINT. A guard that lives in a
    `ContextVar` is exactly as wide as the context that set it, and route 12 and
    route 12b in `tests/test_laundering_routes.py` are both one `threading.Thread`
    stepping out of it. A guard that lives on the object goes wherever the object
    goes - onto a worker thread, into a module-level stash, through a second tool
    call - because it is not a fact about who is running, it is a fact about what
    the value is.

    `said_by` is the sentence `Instrument.measured` puts in its refusal, so the
    message names where the value actually came from rather than guessing.
    """

    __slots__ = ()

    #: Where a value of this kind entered the process, for the refusal message.
    said_by = "was handed to this tool rather than obtained by it"

    #: The instrument this value belongs to, when one is open. Set by
    #: `_inspect` and carried forward by every derivation, so `_note_conversion`
    #: can find the instrument from the VALUE and not from the context.
    _owner: Any = None


#: The dunders and methods that DERIVE a new value from an existing one. Every
#: one of them is wrapped so the derivation carries the mark. Listed rather than
#: discovered because `dir(int)` also contains comparisons (which return `bool`,
#: which cannot be marked and needs no mark) and `__index__` (which CPython
#: requires to return an exact `int`).
_DERIVING = (
    # numbers
    "__abs__", "__add__", "__and__", "__ceil__", "__divmod__",
    "__floor__", "__floordiv__", "__invert__", "__lshift__",
    "__mod__", "__mul__", "__neg__", "__or__", "__pos__", "__pow__",
    "__radd__", "__rand__", "__rdivmod__", "__rfloordiv__", "__rlshift__",
    "__rmod__", "__rmul__", "__ror__", "__round__", "__rpow__", "__rrshift__",
    "__rshift__", "__rsub__", "__rtruediv__", "__rxor__", "__sub__",
    "__truediv__", "__trunc__", "__xor__",
    # text
    "__format__", "__getitem__", "__str__",
    "capitalize", "casefold", "center", "expandtabs", "format", "format_map",
    "join", "ljust", "lower", "lstrip", "partition", "removeprefix",
    "removesuffix", "replace", "rjust", "rpartition", "rsplit", "rstrip",
    "split", "splitlines", "strip", "swapcase", "title", "translate", "upper",
    "zfill",
)

#: The two operations whose result CPython will not let carry a mark. See
#: `_converting`.
_CONVERTING = ("__int__", "__float__")


def _deriving(original: Any, name: str) -> Any:
    """Wrap one operation so its result is marked, and owned by the same call."""

    def method(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        if result is NotImplemented:
            return result
        return _own(_derived(result), self._owner)

    method.__name__ = name
    method.__qualname__ = name
    method.__doc__ = (
        "Derived from a caller-supplied value, and marked as one. See wall 2 in "
        "app/tools/evidence.py."
    )
    return method


def _converting(original: Any, name: str) -> Any:
    """Wrap `int()` and `float()`, whose results CANNOT carry the mark.

    `_PyLong_FromNbInt` normalises whatever `__int__` returns back to an exact
    `int` - it warns about a subclass and then copies it anyway - and `float()`
    does the same. So the mark cannot be threaded through a conversion, and
    returning a marked value would only buy a DeprecationWarning and an exact
    `int` at the end of it. These two wrappers therefore hand back the plain
    result and REMEMBER it on the open instrument, so `measured()` can refuse
    the number afterwards even though the number itself is no longer marked.

    Identity conversions are not remembered: `int(x)` where `x` is already the
    caller's `int` gives back the same number of the same kind, and that is the
    live defect in another costume - `_bounded(max_rows)` in `profile_dataset`
    does exactly this, and remembering `120` there would refuse the honest count
    of a 120-row file all over again. What is remembered is a conversion that
    CHANGED the kind of thing the value is, which is the family the adversary
    named: `int("100")`, `int(float(n))`, `float(n)`.
    """

    def method(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        _note_conversion(self, result)
        return result

    method.__name__ = name
    method.__qualname__ = name
    method.__doc__ = (
        "A caller-supplied value converted to a number. The result cannot carry "
        "the mark, so it is remembered instead. See wall 2 in "
        "app/tools/evidence.py."
    )
    return method


def _copying(self: Any, memo: Any = None) -> Any:
    """`copy` and `deepcopy` of a marked value keep the mark and the owner.

    Route 19 in `tests/test_laundering_routes.py` pins this: a defensive copy is
    the most ordinary thing a handler does, and it must not be a laundry. It
    used to be true by luck - `int.__reduce_ex__` happens to reconstruct the same
    class - and it stopped being reliable the moment these types grew a
    `__dict__` to hold the owner in, because `deepcopy` would then have deep-copied
    the INSTRUMENT along with the number. This says what a copy is instead of
    letting the pickle protocol guess.
    """
    clone = type(self)(self)
    clone._owner = self._owner
    return clone


def _marked_type(name: str, base: type, extra: dict[str, Any], said_by: str) -> type:
    namespace: dict[str, Any] = {
        # NO `__slots__`. These instances carry `_owner`, which is what lets a
        # conversion performed on a worker thread still be remembered - see
        # `CallerValue` and route 12. The cost is one dict per marked argument,
        # and a tool call's arguments are small.
        "__doc__": f"An ordinary {base.__name__} that {said_by}.",
        #: The ordinary type underneath the mark, for `_note_conversion`.
        "plain_type": base,
        "said_by": said_by,
        "__copy__": _copying,
        "__deepcopy__": _copying,
    }
    for attribute in _DERIVING:
        original = getattr(base, attribute, None)
        if original is not None:
            namespace[attribute] = _deriving(original, attribute)
    for attribute in _CONVERTING:
        original = extra.get(attribute) or getattr(base, attribute, None)
        if original is not None:
            namespace[attribute] = _converting(original, attribute)
    return type(name, (base, CallerValue), namespace)


def _text_to_int(self: Any) -> int:
    """`int("100")`. `str` has no `__int__` to wrap, so this is the original."""
    return int(str.__str__(self))


def _text_to_float(self: Any) -> float:
    """`float("1.5")`. `str` has no `__float__` to wrap."""
    return float(str.__str__(self))


_SAID_BY_CALLER = "was handed to this tool in a call's arguments"
_SAID_BY_LEDGER = "was handed back out of the claim ledger, where somebody put it"

CallerInt = _marked_type("CallerInt", int, {}, _SAID_BY_CALLER)
CallerFloat = _marked_type("CallerFloat", float, {}, _SAID_BY_CALLER)
CallerStr = _marked_type(
    "CallerStr", str, {"__int__": _text_to_int, "__float__": _text_to_float},
    _SAID_BY_CALLER,
)

#: The same mark, on the same value, at the other place a supplied value lives.
#: A row in the claim ledger whose origin is not MEASURED is something somebody
#: SAID - a model asserting, a user stating - and reading it back does not turn
#: it into a measurement. See `_row` and wall 3.
ClaimedInt = _marked_type("ClaimedInt", int, {}, _SAID_BY_LEDGER)
ClaimedFloat = _marked_type("ClaimedFloat", float, {}, _SAID_BY_LEDGER)

#: Which ordinary type becomes which marked one when a value is DERIVED from a
#: marked one. Keyed on the exact type, so a value that is already marked is
#: left alone and `True` - whose type is `bool`, not `int` - is not silently
#: turned into a `CallerInt`.
_DERIVED_MARKS: dict[type, type] = {int: CallerInt, float: CallerFloat, str: CallerStr}

#: Which types are marked when the CALLER supplies them. `str` is missing on
#: purpose and the reason is in the module docstring: a path is a string, and
#: `pathlib` interns path components, so a marked path raises `TypeError: can't
#: intern CallerStr` inside the standard library. A caller's strings are
#: compared by `Instrument.measured` instead; a string DERIVED from a caller's
#: number is marked, because nothing passes `str(120)` to `Path`.
_ARGUMENT_MARKS: dict[type, type] = {int: CallerInt, float: CallerFloat}

#: The same set, for a claim coming back out of the ledger, and for the same
#: reason: a fact whose value is a path must still be usable as a path.
_CLAIM_MARKS: dict[type, type] = {int: ClaimedInt, float: ClaimedFloat}

#: The types a caller can send that are QUARANTINED BY VALUE rather than marked.
#: `str` because a marked path breaks `pathlib`, `bool` because CPython will not
#: let `bool` be subclassed. Everything else a JSON call can carry is either
#: marked (`int`, `float`) or is a container the walk goes into. Written as one
#: list so the two exceptions can be checked against `_ARGUMENT_MARKS` by
#: reading rather than by hunting for a second rule somewhere else.
#:
#: A marked value is quarantined by value as well. The mark answers "is this the
#: caller's object"; the quarantine answers "is this the caller's number",
#: which is a different question once the value has been round-tripped through
#: JSON, a file, a socket or another thread and has come back as a new object.
COMPARED_TYPES = (str, bool)


def _own(value: Any, owner: Any) -> Any:
    """Point a freshly marked value at the instrument it belongs to.

    Containers are walked, because `divmod` and `str.partition` return tuples of
    marked values and a mark with no owner on it is only half the story. What is
    walked has just been built by `_inspect`, which refuses a cycle, so there is
    nothing here to guard against a second time.
    """
    if owner is None:
        return value
    if isinstance(value, CallerValue):
        value._owner = owner
    elif isinstance(value, dict):
        for key, item in value.items():
            _own(key, owner)
            _own(item, owner)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            _own(item, owner)
    return value


def _numeric_siblings(value: Any) -> Iterable[Any]:
    """A converted number, and the same number in the other numeric type.

    `int(float(n))` is two conversions and only the first one is on a marked
    value; without this, remembering `500.0` would not catch a tool that then
    stamps `500`. A conversion is remembered as the quantity it produced rather
    than as one Python object.
    """
    yield value
    if type(value) is float and value.is_integer():
        yield int(value)
    elif type(value) is int:
        yield float(value)


def _note_conversion(source: Any, result: Any) -> None:
    """Remember a conversion, on every instrument that has a claim on it.

    Two channels, because a conversion can happen somewhere the context cannot
    reach. `source._owner` is the instrument whose call this value arrived in,
    which is set on the value and therefore true on a worker thread as well as
    on the one that started it - that is route 12. `_MINTING.get()` is the call
    that is running right now, which catches a marked value that reached this
    call from somewhere else. Usually they are the same instrument and the note
    is written once.
    """
    holders = []
    owner = getattr(source, "_owner", None)
    if owner is not None:
        holders.append(owner)
    current = _MINTING.get()
    if current is not None and current is not owner:
        holders.append(current)
    if not holders:
        return
    plain = getattr(type(source), "plain_type", None)
    if type(result) is plain and result == source:
        return  # an identity conversion says nothing about where a value came from
    for holder in holders:
        holder.converted.extend(_numeric_siblings(result))


# ---------------------------------------------------------------------------
# One walk over a call's arguments: mark them, and write down what was in them.


#: How many values one walk will look at before it gives up. NOT A DEPTH BOUND,
#: and the difference is the whole of route 11.
#:
#: The old traversal stopped at eight levels, so a number nested ten dicts deep
#: was never marked, never compared, and never seen - it FAILED OPEN, silently,
#: on a structure a model can produce by typing more brackets. A bound is still
#: needed, because arguments arrive as JSON from a model and a huge or
#: self-referential structure is a denial of service rather than a fact. What was
#: wrong was the direction it failed in.
#:
#: So: no depth limit, a cycle guard that catches the case a depth limit was
#: standing in for, a budget on the TOTAL number of values, and `_Incomplete`
#: when the budget or Python's own recursion limit runs out. `instrument_for`
#: turns that into `inspected=False`, and `Instrument.measured` refuses to stamp
#: anything at all for the rest of the call. A call whose arguments cannot be
#: inspected does not get to measure; it still runs, and it still returns
#: whatever else it produces.
INSPECTION_BUDGET = 100_000


class _Incomplete(Exception):
    """The arguments could not be walked to the end. Fails the call closed."""


def _inspect(
    value: Any,
    marks: dict[type, type],
    *,
    quantities: list[Any] | None = None,
    collect: bool = False,
) -> Any:
    """Rebuild `value` with every markable scalar marked, collecting as it goes.

    One walk rather than three. `evidence._mark`, `_compared_scalars` and
    `is_caller_value` used to walk the same structure separately with the same
    depth bound, which is three chances to disagree about what is in an argument
    and, at `a9245c3`, three that agreed on being blind below level eight.
    """
    seen: set[int] = set()
    budget = [INSPECTION_BUDGET]

    def walk(node: Any, gather: bool) -> Any:
        budget[0] -= 1
        if budget[0] < 0:
            raise _Incomplete("more values than this module will look at")
        marked = marks.get(type(node))
        if marked is not None:
            if gather and quantities is not None:
                quantities.append(node)
            return marked(node)
        if type(node) in COMPARED_TYPES:
            if gather and quantities is not None:
                quantities.append(node)
            return node
        if isinstance(node, (dict, list, tuple, set)):
            token = id(node)
            if token in seen:
                raise _Incomplete("a value that contains itself")
            seen.add(token)
            try:
                if isinstance(node, dict):
                    return {
                        walk(key, gather): walk(item, gather)
                        for key, item in node.items()
                    }
                if isinstance(node, list):
                    return [walk(item, gather) for item in node]
                if isinstance(node, tuple):
                    return tuple(walk(item, gather) for item in node)
                return {walk(item, gather) for item in node}
            finally:
                seen.discard(token)
        return node

    try:
        return walk(value, collect)
    except RecursionError:  # deeper than CPython will go, which is deep enough
        raise _Incomplete("nested deeper than this module can walk") from None


def mark_caller_values(value: Any) -> Any:
    """Return `value` marked as having come from a tool call's arguments.

    Recurses through the containers a JSON tool call can carry, so the number
    inside `{"report": {"counts": [500, 12]}}` is marked too - one level of JSON
    is not a laundry, and nor is ten.

    Strings, booleans and `None` come back unchanged; see `_ARGUMENT_MARKS` for
    why, and `Instrument.measured` for what happens to them instead.

    A structure this cannot walk comes back UNCHANGED rather than half marked.
    Deciding what that means is `instrument_for`'s job, because it is the one
    that holds the instrument the refusal has to be recorded on; a half-marked
    copy handed back from here would look like a complete one.
    """
    try:
        return _inspect(value, _ARGUMENT_MARKS)
    except _Incomplete:
        return value


def mark_as_a_claim(value: Any) -> Any:
    """Return `value` marked as something somebody SAID rather than measured.

    The ledger uses this through `_row`; `app/events.py` uses it on the stored
    payload of every event it hands back. Both are records of what was said, and
    a number read back out of one is still what somebody said - on whichever
    thread, at whatever remove, however many times it has been re-encoded.

    This is the half of wall 3 that does not depend on being in the right
    context, and the probe that found it was needed is worth recording: the
    refusal in `refuse_a_minting_reader` closed the transcript to a minting tool
    on the thread that opened the instrument, and a `threading.Thread` started
    inside the handler read it anyway. A guard that a `Thread(...)` walks round
    is a guard for the honest.

    Strings are not marked, for the same reason a caller's path is not: see
    `_ARGUMENT_MARKS`.
    """
    try:
        return _inspect(value, _CLAIM_MARKS)
    except _Incomplete:
        return value


def _derived(value: Any) -> Any:
    """Mark a value produced BY an operation on a marked one. Strings included."""
    try:
        return _inspect(value, _DERIVED_MARKS)
    except _Incomplete:
        return value


def is_caller_value(value: Any) -> bool:
    """Is this value, or anything inside it, something somebody supplied?

    Cycle-guarded and budgeted like `_inspect`, and it FAILS CLOSED: a structure
    too large or too deep to search is reported as the caller's rather than as
    nobody's. A stamp is the one place in this product where "I could not tell"
    has to read as "no".
    """
    seen: set[int] = set()
    budget = [INSPECTION_BUDGET]

    def look(node: Any) -> bool:
        budget[0] -= 1
        if budget[0] < 0:
            return True
        if isinstance(node, CallerValue):
            return True
        if isinstance(node, dict):
            token = id(node)
            if token in seen:
                return True
            seen.add(token)
            try:
                return any(look(k) or look(v) for k, v in node.items())
            finally:
                seen.discard(token)
        if isinstance(node, (list, tuple, set)):
            token = id(node)
            if token in seen:
                return True
            seen.add(token)
            try:
                return any(look(item) for item in node)
            finally:
                seen.discard(token)
        return False

    try:
        return look(value)
    except RecursionError:
        return True


def _readings_of(text: str) -> Iterable[Any]:
    """The numbers a caller's string can be read as, if any.

    This is `int(str_argument)` answered while the string is still a string.
    Both readings are offered because `int("100")` and `float("100")` are
    different values of different types and a laundering tool may stamp either.
    """
    for reader in (int, float):
        try:
            yield reader(text)
        except (TypeError, ValueError):
            continue


# ---------------------------------------------------------------------------
# Wall 3: a tool that can mint cannot read the claim ledger.
#
# The guard is on the TABLE and not on the functions somebody remembered to
# guard. It used to sit at the top of `assemble_facts`, which was true of
# `assemble_facts` and false of `rows_for` - exported, unguarded, and enough on
# its own: a minting tool read a model's ASSERTED `eval_size_n = 999999` out of
# the ledger and re-stamped it MEASURED. `ledger_view` was the same hole again.
#
# A wall you have to remember is not a wall. `_ledger_rows` is the only function
# in this module that selects from `fact_evidence`, everything that reads the
# ledger goes through it, and a function written next year inherits the refusal
# by having no other way in.

_MINTING: ContextVar[Any] = ContextVar("ml_harness_minting_instrument", default=None)

#: Set only while `Instrument.measured` is writing its row, and read only by
#: `record`. Wall 2 lives on `measured()`, and `record()` is exported next to
#: it with an `origin` parameter - so without this a tool could write a MEASURED
#: row straight past every check by calling the wrong function, which is the
#: same mistake as guarding `assemble_facts` and not `rows_for` in the wall
#: below. The module docstring says a MEASURED stamp is written by the code that
#: ran the instrument AND BY NOTHING ELSE; this is what makes that sentence true
#: rather than a description of who happens to call what today.
_STAMPING: ContextVar[bool] = ContextVar("ml_harness_stamping", default=False)


def minting_instrument() -> Any:
    return _MINTING.get()


def refuse_a_minting_reader(reader: str, holds: str) -> None:
    """Wall 3's refusal, as a door other modules can knock on.

    `holds` names the record being asked for - the claim ledger here, the
    transcript in `app/events.py`. Both are lists of things somebody SAID, and
    the sentence is the same for both: a tool that can stamp MEASURED does not
    get to read them, because reading a claim and re-stamping it is the
    laundering this module exists to stop.

    It reads a `ContextVar`, so it is exactly as wide as the context that opened
    the instrument, and a handler that reads on a worker thread walks round it.
    That is why it is not the only thing standing here: `_row` marks every
    non-MEASURED value the claim ledger hands back, and a mark travels where a
    context does not. This is the loud, early half; the mark is the total half.
    """
    holder = _MINTING.get()
    if holder is None:
        return
    raise MeasurementError(
        f"{holder.tool!r} is holding a measuring instrument and asked to read "
        f"{holds} through {reader}(). A tool that can stamp MEASURED does not "
        "get to see what anyone claimed, because reading a claim and re-stamping "
        "it is the laundering this whole module exists to stop. Read facts in a "
        "tool that measures nothing, or measure in a tool that reads nothing."
    )


# ---------------------------------------------------------------------------
# The store.

#: The shape migration 7 leaves the table in, repeated here verbatim because
#: `ensure_table` still creates it on a database that has somehow lost it.
#: `tests/test_a_thread_id_names_a_conversation.py` asserts the two agree, so a
#: divergence is a failing test rather than a table whose constraints depend on
#: which code path happened to create it.
#:
#: `REFERENCES threads(id)` is the half of wall 5's second rule that the store
#: enforces and no caller can forget. `CHECK (thread_id IS NULL OR thread_id >
#: 0)` is the half the foreign key cannot state: a foreign key refuses `0` only
#: because no `threads` row happens to have that id, and "happens to" is not a
#: rule. NULL is still allowed by both, because a machine-scope row belongs to no
#: conversation and `scope_of` is what decides which facts may use that.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS fact_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER REFERENCES threads(id),
    fact TEXT NOT NULL,
    value TEXT NOT NULL,
    origin TEXT NOT NULL,
    actor TEXT NOT NULL,
    tool TEXT,
    how TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (thread_id IS NULL OR thread_id > 0)
);
"""


def ensure_table() -> None:
    """Self-healing, in the style of `db.ensure_datasets_table`.

    A database written before this table existed gets it the first time
    anything asks, so an install that predates fact provenance does not need a
    migration step somebody has to remember.

    THE MIGRATION RUNNER IS CALLED FIRST NOW, and that is not tidying. This
    table's `thread_id` references `threads`, which is migration 4's, and SQLite
    resolves a foreign key at INSERT time rather than at CREATE time - so a
    `CREATE TABLE` that ran before `threads` existed would succeed and then fail
    every write with "no such table: main.threads". A table that depends on
    another table cannot ensure only itself. This is the same call
    `events.ensure_tables` makes and costs the same: the runner takes no lock at
    all to discover a database is up to date, which it is on every call after the
    first.
    """
    from app import migrations  # local: migrations imports db, which imports us

    migrations.migrate()
    with db.session() as connection:
        connection.execute(_SCHEMA)


def _now() -> str:
    """What SQLite's `CURRENT_TIMESTAMP` would have written, written here.

    `record` composes the row it returns instead of selecting it back, so that
    the wall-3 property is absolute: NOTHING selects from `fact_evidence` while
    a minting instrument is open, including the tool's own read-back of the row
    it just wrote. A property with one exemption is a property nobody can test.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def record(
    *,
    fact: str,
    value: Any,
    origin: str,
    actor: str,
    how: str,
    tool: str | None = None,
    thread_id: int | None = None,
    ledger: diagnosis.Spec | None = None,
) -> dict[str, Any]:
    """Append one row. Nothing here ever updates or deletes one.

    WALL 5 IS THE FIRST CHECK AFTER THE ORIGIN ONES AND IT APPLIES TO EVERY
    ORIGIN, not only to MEASURED. `Instrument.supplied` comes through here too,
    and `state_facts` with no thread would spread a model's ASSERTED
    `prompt_iterations` across every conversation on the machine by the identical
    mechanism. The stamp is what makes the leak dangerous; the leak is not a
    property of the stamp.
    """
    if origin not in ORIGINS:
        raise MeasurementError(f"{origin!r} is not a fact origin")
    if origin == DEFAULTED and str(actor) != HARNESS:
        # THE OTHER HALF OF `diagnosis.ENGINE_ONLY_ORIGINS`, and it has to be
        # here rather than only there. `resolve_facts` refuses a caller that
        # CLAIMS DEFAULTED on the way in; without this, a tool could write the
        # claim into the ledger instead and `assemble_facts` would hand it back
        # to the engine as the engine's own word on the next walk. DEFAULTED is
        # not challengeable - `diagnosis._challenged_facts` skips it - so a
        # model that could mint one would be minting a value nobody may argue
        # with. Only the harness, settling by a written rule, writes this row.
        raise MeasurementError(
            f"the {actor!r} tried to write a {DEFAULTED} row for {str(fact)!r}. That "
            "origin means the engine applied its own default, and only the harness "
            "may say it. A model or a person says a value through state_facts, which "
            "records what they are worth."
        )
    if origin == MEASURED and is_an_opinion(fact, ledger):
        # WALL 7, AT THE TABLE, for the reason wall 5 is at the table: a rule
        # enforced on the function somebody remembered is a rule that is not
        # enforced. `Instrument.measured` refuses this too, earlier and with
        # more to say, and this is the one that holds for a door written next
        # year that never takes an instrument at all.
        raise MeasurementError(
            _opinion_refusal(
                fact, tool=tool, doing="write a MEASURED row", ledger=ledger
            )
        )
    if thread_id is None:
        if scope_of(fact, ledger) != MACHINE:
            raise ScopeError(
                _scope_refusal(fact, tool=tool, origin=origin, ledger=ledger)
            )
    elif not names_a_conversation(thread_id):
        # Wall 5's second half, and it applies to a MACHINE-scoped fact too: a
        # hardware reading filed against a conversation that does not exist is
        # still a row somebody else will inherit, and "the box is the same box"
        # is a reason to allow NO thread, never a reason to allow a wrong one.
        raise ScopeError(
            _no_such_thread_refusal(thread_id, fact=fact, tool=tool, origin=origin)
        )
    if origin == MEASURED and not _STAMPING.get():
        raise MeasurementError(
            f"a MEASURED row for {str(fact)!r} was written straight to the ledger. "
            "Every check that makes a measurement mean anything - the tool declared "
            "the fact, the value is not one the caller handed over, there is an "
            "account of how - lives in Instrument.measured, and a row that went "
            "round it carries a badge nobody earned. Take an instrument and stamp "
            "with it."
        )
    ensure_table()
    stored = json.dumps(value, default=str)
    created_at = _now()
    with db.session() as connection:
        cursor = connection.execute(
            "INSERT INTO fact_evidence"
            "(thread_id, fact, value, origin, actor, tool, how, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                thread_id,
                str(fact),
                stored,
                origin,
                str(actor),
                tool,
                str(how),
                created_at,
            ),
        )
        row_id = cursor.lastrowid
    return {
        "id": row_id,
        "thread_id": thread_id,
        "fact": str(fact),
        # Round-tripped rather than handed back, so the row a caller sees is the
        # row the table holds - and so a marked caller value cannot leave here
        # still marked.
        "value": json.loads(stored),
        "origin": origin,
        "actor": str(actor),
        "tool": tool,
        "how": str(how),
        "created_at": created_at,
    }


def _row(row: Any) -> dict[str, Any]:
    """One stored row, decoded - and a claim comes back marked as a claim.

    WALL 3, AS A PROPERTY OF THE VALUE RATHER THAN OF THE CALLER. The refusal in
    `_ledger_rows` reads a `ContextVar` and is therefore exactly as wide as the
    thread that set it: route 12b in `tests/test_laundering_routes.py` reads the
    ledger on a worker thread, where no minting instrument is in context, and
    hands the number back to the main one to be stamped.

    A row whose origin is not MEASURED is something somebody SAID. Marking it on
    the way out says so on the number itself, so it does not matter which thread
    read it, how many hands it passed through, or whether the guard above
    happened to be looking: `Instrument.measured` refuses a marked value.

    MEASURED rows are left alone. A measurement read back is still a
    measurement, and marking one would make the ledger's own history unusable to
    the code that has to display it.
    """
    out = dict(row)
    value = json.loads(out["value"])
    if out["origin"] != MEASURED:
        value = mark_as_a_claim(value)
    out["value"] = value
    return out


def _ledger_rows(where: str, parameters: tuple[Any, ...]) -> list[dict[str, Any]]:
    """THE ONE DOOR to the claim ledger, and the place wall 3 stands.

    `where` is composed from literals in this module and never from anything a
    caller sent; the values go through parameters. Any new reader belongs here,
    which is the point - a reader that goes around this function is a reader
    that reopens the hole, and
    `tests/test_the_wall_is_a_property_not_a_special_case.py` derives the
    module's surface and watches the database to catch one that does.
    """
    refuse_a_minting_reader(sys._getframe(1).f_code.co_name, "the fact ledger")
    ensure_table()
    with db.session() as connection:
        rows = connection.execute(
            f"SELECT * FROM fact_evidence {where} ORDER BY id", parameters
        ).fetchall()
    return [_row(row) for row in rows]


def rows_for(thread_id: int | None) -> list[dict[str, Any]]:
    """Every row this thread can see, oldest first.

    A row with no thread is machine scope - the hardware in this box is the
    hardware in this box, whichever thread asked - and is visible everywhere. A
    row with a thread belongs to that thread and to no other, because "the eval
    set has 120 rows" is a fact about one project and leaking it sideways would
    open a gate in a conversation where nobody counted anything.

    THAT SENTENCE WAS TRUE, WAS WRITTEN HERE, AND WAS NOT ENFORCED ANYWHERE. The
    reading is right and always was; what did not exist was any rule about the
    WRITING, so `measure_eval_set` with no `thread_id` produced exactly the row
    this docstring warns about, on exactly this fact, at exactly this number, in
    the owner's real database. `scope_of` and wall 5 are where the other half now
    lives, and `record` is where the refusal is - because a rule enforced on one
    side of a table is a rule that is not enforced.

    AND THEN THIS FUNCTION WAS STILL THE OTHER SIDE OF THAT SAME TABLE. "A row
    with no thread is machine scope" was a sentence about what the WRITER meant,
    used as a rule about what the READER serves, and the reader never asked the
    ledger what the fact's declared scope actually is. So every NULL row was
    served to every conversation whatever the ledger said, and any NULL row
    arriving by a route `record()` does not cover reopened the gate in silence:
    a restored pre-v006 backup, a hand-edited database, a bulk import, a future
    migration. Demonstrated with one INSERT: a thread that had counted nothing
    went from BLOCKED__BUILD_EVAL_SET to TRAIN__LORA_SFT with all five gates
    PASSED, and `record()` was never called.

    So the read asks the same question the write does, of the same declaration:

      * a NULL row for a MACHINE-scope fact is served to every conversation,
        because the box is the same box - unchanged, and the positive control;
      * a NULL row for a THREAD-scope fact is served TO NOBODY, including to
        `rows_for(None)`, whatever route wrote it and whatever it says;
      * a row that names a thread is that thread's, unchanged.

    The machine-scope names are read off the ledger through `facts_at_scope` and
    passed as parameters, so a fact re-declared `scope: machine` tomorrow becomes
    visible everywhere by being re-declared and not by anybody editing this
    function. A fact the ledger has never heard of is THREAD by `scope_of`'s
    default, so an unknown name in a NULL row is served to nobody either - which
    is the direction this must fail in.

    Nothing is deleted and nothing is hidden: `rows_no_thread_can_see` is the
    reader for exactly the rows this refuses to serve, and `GET /api/evidence`
    shows them beside the live ledger and the quarantine.
    """
    machine = facts_at_scope(MACHINE)
    clauses: list[str] = []
    parameters: list[Any] = []
    if machine:
        clauses.append(
            "(thread_id IS NULL AND fact IN (%s))"
            % ", ".join("?" for _ in machine)
        )
        parameters.extend(machine)
    if thread_id is not None:
        clauses.append("thread_id = ?")
        parameters.append(int(thread_id))
    if not clauses:
        # No fact in the ledger is declared machine scope and no thread was
        # named. There is nothing this caller may see, and an empty list is the
        # honest answer; composing `WHERE ` with nothing after it would serve
        # the whole table, which is the failure this function is a fix for.
        return []
    return _ledger_rows("WHERE " + " OR ".join(clauses), tuple(parameters))


def rows_no_thread_can_see() -> list[dict[str, Any]]:
    """The NULL rows `rows_for` refuses to serve, oldest first.

    THE POINT OF A RULE ON THE READ PATH IS THAT NOTHING NEEDS TO HAVE BEEN
    DELETED, and this is what makes that true rather than said. A row written
    with no thread for a fact the ledger declares `scope: thread` is still in
    `fact_evidence`, exactly as whoever wrote it wrote it, with its value, its
    origin, its tool and its `how`. It can open nothing, and a person can still
    see it and decide what it was.

    Migration 6's quarantine is the other half of the same answer and they are
    not the same thing: quarantine is what a MIGRATION did once, to rows that
    existed on the day it ran, and it MOVED them. This is what the READER does
    forever, to rows that arrive by any route afterwards, and it moves nothing.
    A restored backup puts the rows back; this is why putting them back does not
    put the gate back.
    """
    machine = facts_at_scope(MACHINE)
    if not machine:
        return _ledger_rows("WHERE thread_id IS NULL", ())
    return _ledger_rows(
        "WHERE thread_id IS NULL AND fact NOT IN (%s)"
        % ", ".join("?" for _ in machine),
        tuple(machine),
    )


def assemble_facts(
    thread_id: int | None,
    supplied: dict[str, Any] | None = None,
    actor: str = DEFAULT_ACTOR,
    ledger: diagnosis.Spec | None = None,
    *,
    persist: bool = False,
) -> tuple[dict[str, Fact], list[dict[str, Any]]]:
    """The fact sheet the engine is asked to reason over, with every origin on it.

    Returns `(facts, trail)`. `facts` maps name to `diagnosis.Fact`, ready to
    hand straight to `diagnose`; `trail` is one row per fact saying who supplied
    it, with what instrument, and what lost to it.

    `persist` IS FALSE UNLESS A CALLER THAT ALREADY WRITES SAYS OTHERWISE. The
    sheet is the same either way; what it decides is whether a correction the
    walk makes to the ledger (`_a_modality_the_file_contradicts`) is also
    WRITTEN. Only the `run_diagnosis` tool passes True - it is the walk the
    conductor's turn goes through, and the turn already writes. Every read
    route passes nothing: the Stage, `/ui/report`, `/report` and `/export`
    through `journey_report.build`, and `GET /api/next_step`, each promise
    that a GET writes nothing, and a reader that moved rows would be the second
    writer they say they are not. Off by default so a reader added next year
    keeps that promise by existing.

    WALL 3 IS NOT IN THIS FUNCTION ANY MORE, and that is the fix rather than a
    regression: it is in `_ledger_rows`, one layer down, where every reader of
    the claim ledger meets it whether or not its author knew the wall existed.
    The refusal a minting tool gets from calling this is raised on the line
    below, by the read.
    """
    current = spec(ledger)
    candidates: dict[str, list[dict[str, Any]]] = {}

    for order, row in enumerate(rows_for(thread_id)):
        if row["fact"] not in current.facts:
            # A row for a fact the ledger no longer declares. Dropped rather
            # than passed on, because `diagnose` would raise on the name and a
            # single stale row would then break every run in this thread. The
            # row stays in the table - nothing here deletes - so the history is
            # intact and `ledger_view` still shows it.
            continue
        candidates.setdefault(row["fact"], []).append(
            {
                "order": order,
                "rank": ORIGIN_RANK.get(row["origin"], 0),
                "value": row["value"],
                "origin": row["origin"],
                "actor": row["actor"],
                "tool": row["tool"],
                "how": row["how"],
                # Kept so a stored row can be MOVED to the quarantine whole;
                # see `_a_modality_the_file_contradicts`. Never on the trail.
                "stored": row,
            }
        )

    supplied_origin = origin_for(actor)
    # Supplied-with-this-call is the most recent thing anybody said, so it wins
    # every tie against a stored row of the same strength. It does not win
    # against a stronger one - which is what stops a model overwriting a
    # measurement or contradicting the user about the user's own week.
    base = 10_000
    for offset, (name, value) in enumerate(dict(supplied or {}).items()):
        candidates.setdefault(str(name), []).append(
            {
                "order": base + offset,
                "rank": ORIGIN_RANK.get(supplied_origin, 0),
                "value": value,
                "origin": supplied_origin,
                "actor": actor,
                "tool": None,
                "how": f"supplied with this call by the {actor}",
            }
        )

    _a_modality_the_file_contradicts(thread_id, candidates, current, persist=persist)

    facts: dict[str, Fact] = {}
    trail: list[dict[str, Any]] = []
    for name, rows in sorted(candidates.items()):
        winner = max(rows, key=lambda item: (item["rank"], item["order"]))
        # A DEFAULTED ROW IS THE ENGINE'S OWN DEFAULT COMING BACK, so it travels
        # as `Settled` and carries the `how` that was recorded with it. A plain
        # `Fact(value, DEFAULTED)` is refused by `resolve_facts` and should be:
        # this is the one door that row is allowed through, and it is the one
        # place that can know the row came out of the ledger rather than out of
        # a tool call. See `diagnosis.Settled`.
        facts[name] = (
            Settled(winner["value"], DEFAULTED, winner["how"])
            if winner["origin"] == DEFAULTED
            else Fact(winner["value"], winner["origin"])
        )
        trail.append(
            {
                "fact": name,
                "value": winner["value"],
                "origin": winner["origin"],
                "actor": winner["actor"],
                "tool": winner["tool"],
                "how": winner["how"],
                "declared_source": current.facts.get(name, {}).get("source"),
                "superseded": [
                    {
                        "value": other["value"],
                        "origin": other["origin"],
                        "actor": other["actor"],
                        "how": other["how"],
                    }
                    for other in rows
                    if other["order"] != winner["order"]
                ],
            }
        )
    return facts, trail


def _a_modality_the_file_contradicts(
    thread_id: int | None,
    candidates: dict[str, list[dict[str, Any]]],
    current: diagnosis.Spec,
    *,
    persist: bool = False,
) -> None:
    """A stated `modality` the file on record contradicts does not route the walk.

    THE OWNER'S THREAD 93. On 2026-09-22 the model, under Full, stated
    `modality` "tabular" (row 933) for `ml-principles-dataset/data/splits/
    eval.jsonl` - JSONL whose rows are `task_type`, `input`, `expected`: a prose
    question and a record of prose answers. STATED outranks the harness's
    DEFAULTED derivation, so the walk went down the tabular branch and stopped
    at S8_TABULAR_ROWS_UNKNOWN asking for the row count of a table that does not
    exist. On 2026-09-23 `state_facts` learnt to refuse such a statement
    (`measure.inspect_modality`, "G2"); a statement ALREADY ON RECORD still won
    every walk, and thread 93 stayed on the wrong branch for good.

    So the walk asks the same question the door does, of the same file, with
    the same rule: when `modality` would resolve from a claim (STATED or
    ASSERTED) that a file of prose rows is not consistent with
    (`measure.TEXT_ROWS_ADMIT`), and the eval file this thread has on record
    (`full_defaults._eval_file`, the file the door reads) can be opened and
    `inspect_modality` says `text`, then:

      * every stored claim row for `modality` the file contradicts is MOVED to
        the quarantine, whole, with a sentence naming the file and the prose
        fields - `quarantine_rows`, migration 6's shape;
      * `modality` resolves to `text`, as the harness's DEFAULTED row with the
        `how` naming the file and the fields, written once to the ledger and
        carried as `Settled` like every other DEFAULTED row.

    WHY DEFAULTED AND NOT MEASURED, although the inspection IS a reading of the
    file. A MEASURED row is minted only through `Instrument.measured`, by a tool
    that declared the fact in `measures=` and whose `provides` matches the
    fact's `measured_by` (walls 3 and 9). No instrument declares `modality`,
    and this is the claim ledger's READER: a reader that stamped MEASURED would
    be wall 3's laundering route with the file standing in for the argument.
    DEFAULTED - the harness settling by a written rule, rank zero, a value any
    person's `state_facts` overrules by being said - is the word
    `full_defaults` and the `state_facts` guard already file for this same
    fact derived from this same file. One fact, one derivation, one origin.

    ONCE. The move takes the claim out of `fact_evidence`, so the next walk
    finds only the DEFAULTED row, wins on it, and never inspects again; the
    DEFAULTED row is written only when the thread holds no DEFAULTED `text`
    already; and `quarantine_rows` inserts by the row's own id, so a second
    move of the same row adds nothing.

    THE MOVE AND THE ROW ARE WRITTEN ONLY WHEN `persist` IS TRUE, which is
    the `run_diagnosis` tool and nothing else (see `assemble_facts`). The first
    version wrote on every walk, and so on every GET of the Stage, the report
    and the export - read routes whose contract is that they write nothing.
    A read route still RESOLVES modality from the file, in memory, so the
    Stage on thread 93 shows the honest branch at once; the next
    `run_diagnosis` makes it durable.

    A DATABASE THAT CANNOT BE WRITTEN still gets the honest walk, for the same
    reason: the contradiction is a property of the file, re-derived on every
    walk until the move lands, so a read-only copy walks off the tabular branch
    all the same and a person reading it loses nothing but the durable record.

    NOTHING INSPECTABLE, NOTHING CHANGES: no file on record, a file that cannot
    be opened, rows with no prose field (a table of labels and numbers is what
    a tabular claim describes), or a claim the file agrees with, and the
    statement stands exactly as it did.
    """
    rows = candidates.get("modality")
    if thread_id is None or not rows or "modality" not in current.facts:
        return
    from app import full_defaults
    from app.tools import measure

    def said(item: dict[str, Any]) -> str:
        return str(item["value"]).strip().lower()

    winner = max(rows, key=lambda item: (item["rank"], item["order"]))
    if (
        winner.get("stored") is None
        or winner["origin"] not in (STATED, ASSERTED)
        or said(winner) in measure.TEXT_ROWS_ADMIT
    ):
        return
    found = full_defaults._eval_file(int(thread_id))
    seen = measure.inspect_modality(found[0]) if found else None
    if seen is None:
        return

    contradicted = [
        item for item in rows
        if item.get("stored") is not None
        and item["origin"] in (STATED, ASSERTED)
        and said(item) not in measure.TEXT_ROWS_ADMIT
    ]
    fields = ", ".join(seen["prose_fields"])
    because = (
        f"stated {said(winner)!r} for modality, and the file on record at {seen['path']} "
        f"is {seen['format'].upper()} whose rows are text: the fields {fields} carry prose "
        f"in the {seen['rows']} rows read, and none names an image, audio or video file. "
        "A claim the file contradicts cannot route the walk, so the walk resolves "
        "modality from the file. Moved rather than deleted: the statement was made; "
        "the file says otherwise. See evidence._a_modality_the_file_contradicts."
    )
    how = (
        f"Derived by inspection when the walk found modality stated {said(winner)!r}: read "
        f"{seen['rows']} rows of {seen['path']} ({seen['format']}); the fields {fields} are "
        "prose by the rule the fields grader uses, and no value names an image, audio "
        "or video file, so the modality is text. Say otherwise with state_facts and "
        "yours is inspected the same way."
    )
    already = any(
        item["origin"] == DEFAULTED and said(item) == "text" for item in rows
    )
    if persist:
        try:
            quarantine_rows([item["stored"] for item in contradicted], because)
            if not already:
                record(
                    fact="modality",
                    value="text",
                    origin=DEFAULTED,
                    actor=HARNESS,
                    how=how,
                    thread_id=int(thread_id),
                    ledger=current,
                )
        except sqlite3.Error:
            pass  # a database that cannot be written: see "CANNOT BE WRITTEN" above

    moved = {id(item) for item in contradicted}
    kept = [item for item in rows if id(item) not in moved]
    if not already:
        kept.append(
            {
                "order": max(item["order"] for item in rows) + 1,
                "rank": ORIGIN_RANK[DEFAULTED],
                "value": "text",
                "origin": DEFAULTED,
                "actor": HARNESS,
                "tool": None,
                "how": how,
            }
        )
    candidates["modality"] = kept


def ledger_view(thread_id: int | None) -> list[dict[str, Any]]:
    """Every row, for a person reading the transcript. Newest first."""
    return list(reversed(rows_for(thread_id)))


# ---------------------------------------------------------------------------
# The quarantine: rows that were written before wall 5 existed.


#: Where migration 6 put the rows that predate wall 5. A SEPARATE TABLE rather
#: than a flag on `fact_evidence`, for the reason the ledger is append-only:
#: `rows_for` composes its own WHERE clause and a flag is a condition somebody
#: has to remember to add. A row in another table cannot be forgotten into a
#: gate.
#:
#: NOT NAMED `fact_evidence_quarantine`, deliberately. The wall-3 property test
#: greps this module's source for a select against the claim ledger's table, and
#: a table whose name merely STARTS with that one would match the pattern - so a
#: reader of the quarantine would read as a second door into the claim ledger,
#: and the test that guards the one door would go red for a reason that is not
#: true. Two tables, two names, neither a prefix of the other.
QUARANTINE_TABLE = "quarantined_facts"


def quarantine_view(limit: int = 200) -> list[dict[str, Any]]:
    """The quarantined rows, newest first, for a person who wants to see them.

    Quarantine is not deletion and this is what makes that true rather than said:
    the rows are still here, with their original ids, their values, who wrote
    them, when, and one sentence saying why they were moved. Nothing in the
    product can open a gate on them - `rows_for` does not read this table and
    never will - and nobody has lost anything they had.

    EVERY VALUE COMES BACK MARKED AS A CLAIM, INCLUDING THE MEASURED ONES, and
    that is stricter than `_row` on the live ledger on purpose. A row is in here
    because the product decided its measurement is not attached to any
    conversation it can be trusted in; handing it back unmarked would let a
    minting tool read one and re-stamp it, which is wall 3's laundering with an
    extra hop. On the live ledger a MEASURED row is left alone because it is
    still a measurement of something. In here, that is exactly what is in doubt.
    """
    refuse_a_minting_reader("quarantine_view", "the fact quarantine")
    ensure_quarantine_table()
    with db.session() as connection:
        rows = connection.execute(
            f"SELECT * FROM {QUARANTINE_TABLE} ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["value"] = mark_as_a_claim(json.loads(item["value"]))
        out.append(item)
    return out


_QUARANTINE_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {QUARANTINE_TABLE} (
    id INTEGER PRIMARY KEY,
    thread_id INTEGER,
    fact TEXT NOT NULL,
    value TEXT NOT NULL,
    origin TEXT NOT NULL,
    actor TEXT NOT NULL,
    tool TEXT,
    how TEXT NOT NULL,
    created_at TEXT NOT NULL,
    quarantined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    quarantined_because TEXT NOT NULL
);
"""


def ensure_quarantine_table() -> None:
    """Self-healing, like `ensure_table`.

    Migration 6 creates this table and fills it. This exists so a reader on a
    database that has never had a row quarantined answers "none" instead of "no
    such table" - the `list_jobs` defect in `app/migrations/__init__.py`'s
    docstring, which is in this repository's git log and is not being repeated.
    """
    with db.session() as connection:
        connection.execute(_QUARANTINE_SCHEMA)


def quarantine_rows(rows: Iterable[dict[str, Any]], because: str) -> list[int]:
    """Move stored ledger rows into the quarantine, whole, and say why. Returns the ids moved.

    MIGRATION 6's MOVE, AS A FUNCTION, for a row the product finds wrong after
    the day a migration could have run: the row keeps its original id, value,
    origin, actor, tool, `how` and `created_at`, gains `quarantined_because`,
    and leaves `fact_evidence` in the same transaction - so `rows_for`, which
    never reads the quarantine, can never serve it to a walk again, and
    `quarantine_view` still shows it to a person. Nothing is edited and nothing
    is lost; "nothing here ever updates or deletes one" is `record`'s promise
    about the ledger's history, and the history is here.

    The rows are the ones `rows_for` handed back - this reads nothing itself,
    so the claim ledger still has exactly one door. `INSERT OR IGNORE` on the
    original id is what makes a second move of the same row add nothing.

    AND IT REFUSES A TOOL THAT CAN MINT, like every door to the ledger. It
    reads nothing, but a tool holding a measuring instrument that could MOVE
    rows could take a claim out from under the measurement it is about to
    stamp, and wall 3 is the rule that such a tool touches none of this.
    """
    refuse_a_minting_reader("quarantine_rows", "the fact ledger")
    moving = [row for row in rows if row.get("id") is not None]
    if not moving:
        return []
    ensure_quarantine_table()
    with db.session() as connection:
        for row in moving:
            connection.execute(
                f"INSERT OR IGNORE INTO {QUARANTINE_TABLE} "
                "(id, thread_id, fact, value, origin, actor, tool, how, created_at, "
                "quarantined_because) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    int(row["id"]),
                    row.get("thread_id"),
                    str(row["fact"]),
                    json.dumps(row["value"], default=str),
                    str(row["origin"]),
                    str(row["actor"]),
                    row.get("tool"),
                    str(row["how"]),
                    str(row.get("created_at") or _now()),
                    str(because),
                ),
            )
            connection.execute("DELETE FROM fact_evidence WHERE id = ?", (int(row["id"]),))
    return [int(row["id"]) for row in moving]


# ---------------------------------------------------------------------------
# The instrument.


def _same(left: Any, right: Any) -> bool:
    """Equality that does not confuse `True` with `1`.

    `True == 1` in Python, and a boolean fact stamped because an integer
    argument happened to be 1 would be a false refusal rather than a false
    stamp - annoying rather than dangerous - but the reverse case, a `1`
    argument laundering into a `True` measurement, is the dangerous one. Strict
    types answer both.
    """
    return type(left) is type(right) and left == right


@dataclass
class Instrument:
    """A tool's licence to stamp, for the duration of one call.

    Handed to the handler by `Registry.call` as the keyword argument
    `instrument`, which no schema may declare and therefore no model may fill.
    It carries no way to READ the fact ledger, on purpose: see wall 3.
    """

    tool: str
    actor: str = DEFAULT_ACTOR
    thread_id: int | None = None
    #: The facts this tool declared it measures. Checked at registration.
    measures: frozenset[str] = field(default_factory=frozenset)
    #: This call's arguments with every markable value marked as the caller's.
    #: Wall 2. `Registry.call` merges THESE over the raw ones before calling a
    #: minting handler, which is what makes the mark reach the code that could
    #: launder.
    caller_arguments: dict[str, Any] = field(default_factory=dict)
    #: EVERY scalar this call was handed, except the ones the tool declared as
    #: bounds. `measured` refuses a value strictly equal to one of these, which
    #: is what catches a rebuild that never touched a marked object at all - a
    #: number that went out through `json.dumps`, or onto a disk, or into another
    #: thread, and came back as a new one. See THE THIRD CHECK in the module
    #: docstring, and `ToolSpec.bounds` for the one thing that is left out of it.
    quarantined: tuple[Any, ...] = ()
    #: Could the walk over the arguments finish? False when a structure was too
    #: large, too deep or self-referential, and then this instrument stamps
    #: nothing at all. Route 11 is what a bounded search that failed OPEN did.
    inspected: bool = True
    #: The arguments this tool declared are a bound on the work rather than an
    #: answer to it. Kept for the refusal message, so a tool that stamps its own
    #: declared bound gets told which declaration let it try.
    bounds: frozenset[str] = field(default_factory=frozenset)
    #: WHAT THIS TOOL IS, IN THE ENGINE'S OWN VOCABULARY - its `provides=`, the
    #: same closed names `app/tools/blocks.py` publishes. Wall 9 asks whether
    #: any of them is one the fact admits. Carried here rather than looked up,
    #: because this module may not import the registry (the registry imports
    #: it), and because a licence should say what it licenses.
    provides: frozenset[str] = field(default_factory=frozenset)
    #: Numbers this call produced by CONVERTING a marked value to another kind
    #: of number, which is the one derivation the mark cannot survive. Filled by
    #: `_note_conversion`, read by `measured`, and empty for a call that never
    #: converted anything.
    converted: list[Any] = field(default_factory=list)
    #: What this call recorded as somebody's OPINION, through `opinion()`. Read
    #: by `measured`, which refuses a value that is already in here: filing the
    #: judge's 0.967 as `judge_score` and then stamping the same 0.967 as
    #: `baseline_score` is the whole defect with one extra row written. Wall 7.
    opinions: list[dict[str, Any]] = field(default_factory=list)
    #: What this call actually stamped, for the tool to report back.
    minted: list[dict[str, Any]] = field(default_factory=list)
    #: THE LEDGER THIS CALL IS BEING JUDGED AGAINST, resolved from the thread by
    #: `Registry.call`. It is a licence to stamp against ONE domain's knowledge,
    #: and it does not widen wall 3: nothing here reads the fact LEDGER of what
    #: anybody claimed - a `Spec` is the declarations, which is what `measures`
    #: was already checked against at registration and must now be checked
    #: against per call, because registration had no thread and so no domain.
    #: `None` is the default ledger, for a call made outside any conversation.
    ledger: "diagnosis.Spec | None" = None

    @property
    def supplied_origin(self) -> str:
        return origin_for(self.actor)

    @property
    def can_mint(self) -> bool:
        return bool(self.measures)

    # -- the stamp --------------------------------------------------------

    def measured(
        self,
        fact: str,
        value: Any,
        *,
        how: str,
        from_file: "str | Path | dict[str, Any] | None" = None,
    ) -> dict[str, Any]:
        """Record `value` for `fact` as MEASURED. Raises rather than laundering.

        `how` is not decoration. It is the sentence the interface shows next to
        the number - "counted 120 rows in eval.jsonl" - and invariant 3 says a
        number with no provenance does not get displayed. A stamp with no
        instrument reading behind it has nothing to say here, which is why the
        argument is required and why an empty one is refused.

        WALL 2 IS FOUR REFUSALS AND ONE QUESTION. The question is *did the
        engine watch this measurement happen*, and each refusal is one way a
        value can reach here without that being true:

        1. it IS the caller's object, or something derived from one (the mark);
        2. it is what this call CONVERTED one into, which is the one derivation
           CPython will not let a mark cross (`_note_conversion`);
        3. it is, strictly by type, a number or a string the caller SENT - which
           catches a rebuild that touched no marked object at all, because it
           went through JSON, a file, a socket or another thread;
        4. it is a bare `True` in a call that measured nothing else, which is a
           badge rather than a measurement.

        Only (3) can refuse an honest count, and only for an argument that
        really might be the answer. `ToolSpec.bounds` is where a tool says which
        of its arguments cannot be - `max_rows` bounds the work, it does not
        answer "how many rows are there" - and that declaration is the reason a
        120-row file counted with a cap of 120 is stamped instead of returning
        HTTP 500 the way it did for a whole commit.

        WALL 8 IS THE ONE ABOUT WHERE THE ROWS CAME FROM. `from_file` is how a
        tool that read a file on this machine says which file, and a fact
        measured off a file with generated rows in it is refused here.

        `docs/VISION.md` states the rule as *"synthetic data can never open a
        gate"*, and until 2026-08-27 it was enforced at the WRITER:
        `synthesize_rows` tags every row, declares `measures=()`, and says so in
        its manifest. The writer is the end that cannot enforce it. Nothing
        stopped the next turn pointing `measure_eval_set` at the file it had
        just written, and a thousand sampled rows would have counted as a
        thousand-row eval set - G0 open, a baseline scored against invented
        data, and every number after it a statement about a distribution this
        product made up. The check belongs where the stamp happens, which is
        here, beside the other seven.

        It is deliberately NOT "strip the synthetic rows and count the rest". A
        file that is 30 real rows and 970 generated ones is not a 30-row eval
        set: `measure_baseline` will score whatever the file holds, so a count
        of the clean subset would describe a file nobody is going to use. The
        refusal names both numbers and what to do instead.

        A file with no tagging at all passes, and that is not a hole - it is the
        limit, stated: this product can only know what is generated when
        something said so, and its own generator always says so.
        """
        name = str(fact)
        if not self.inspected:
            raise MeasurementError(
                f"{self.tool!r} tried to stamp {name!r} MEASURED, and this call's "
                "arguments could not be inspected to the end - they are too large, "
                "too deeply nested, or they contain themselves. Nothing can be "
                "stamped from a call whose arguments nobody could read, because "
                "the check that would say whether this number came from them did "
                "not finish. Send the same request with a smaller structure."
            )
        if from_file is not None:
            self._refuse_generated_rows(name, from_file)
        if is_an_opinion(name, self.ledger):
            # WALL 7, BEFORE THE `measures` CHECK ON PURPOSE. Registration
            # already makes this unreachable through a declared tool, so the
            # only caller who gets here is one holding an undeclared name - and
            # "you did not declare it" would be a true sentence that hides the
            # real one. The refusal a person reads should be the reason.
            raise MeasurementError(
                _opinion_refusal(
                    name, tool=self.tool, doing="stamp MEASURED", ledger=self.ledger
                )
            )
        if name not in spec(self.ledger).facts:
            # WHAT MAY BE DECLARED AND WHAT MAY BE STAMPED ARE DIFFERENT
            # QUESTIONS, AND THIS IS THE SECOND ONE. Registration checked the
            # union of every ledger this product ships, because it happens at
            # import with no thread and therefore no domain - which is what lets
            # an AI-engineering trace reader exist at all. Here there IS a
            # thread, so there is a ledger, and a fact that ledger has never
            # heard of cannot be stamped onto it however honestly it was read.
            raise MeasurementError(
                f"{self.tool!r} tried to stamp {name!r} MEASURED on a thread "
                f"running {_ledger_name(self.ledger)}, which declares no such "
                "fact. The measurement may be perfectly real; it is an answer in "
                "another domain's vocabulary, and a row filed here would be a "
                "number this conversation's gates cannot read and its diagnosis "
                "cannot use."
                + (
                    " Declared in: " + ", ".join(ledgers_declaring(name)) + "."
                    if ledgers_declaring(name)
                    else ""
                )
            )
        if name not in self.measures:
            raise MeasurementError(
                f"{self.tool!r} tried to stamp {name!r} MEASURED and did not declare "
                f"it. Declared: {sorted(self.measures) or 'nothing'}. A tool measures "
                "what it said it measures, decided at registration where it can be "
                "read, not at runtime where it cannot."
            )
        if not the_right_instrument(name, self.provides, self.ledger):
            # WALL 9, AND IT STANDS HERE AS WELL AS AT REGISTRATION FOR THE
            # REASON THE DOMAIN CHECK ABOVE DOES: registration sees the union of
            # every shipped ledger and has no thread, so a fact one ledger binds
            # loosely and another binds tightly passes there and must be asked
            # again where the thread's own ledger is known.
            raise MeasurementError(
                wrong_instrument_reason(
                    name,
                    tool=self.tool,
                    provides=self.provides,
                    doing="stamp MEASURED",
                    ledger=self.ledger,
                )
            )
        if not str(how).strip():
            raise MeasurementError(
                f"{self.tool!r} stamped {name!r} MEASURED with no account of how. "
                "Every displayed number carries its provenance, and 'measured' with "
                "no reading behind it is a badge rather than a provenance."
            )
        if value is None:
            raise MeasurementError(
                f"{self.tool!r} tried to stamp {name!r} MEASURED with no value. A "
                "tool that ran and found nothing has the same knowledge as a tool "
                "that did not run; both are the ledger's default."
            )
        if is_caller_value(value):
            said_by = getattr(value, "said_by", CallerValue.said_by)
            raise MeasurementError(
                f"{self.tool!r} tried to stamp {name!r} MEASURED with {value!r}, "
                f"which {said_by}, or was derived from something that did. A tool "
                "may only stamp what it obtained. Handing a supplied number back "
                "with a measurement badge on it - however many times it is added "
                "to, parsed or reformatted on the way - is the exact hole fact "
                "origins exist to close."
            )
        for candidate in self.converted:
            if _same(value, candidate):
                raise MeasurementError(
                    f"{self.tool!r} tried to stamp {name!r} MEASURED with {value!r}, "
                    "which this call produced by converting a value it was handed - "
                    "`int(argument)` on a string, `float()` on a number, or the two "
                    "in a row. CPython will not let a converted value carry the "
                    "caller mark, so the conversion was remembered instead. A tool "
                    "may only stamp what it obtained."
                )
        for said in self.opinions:
            if _same(value, said["value"]):
                raise MeasurementError(
                    f"{self.tool!r} tried to stamp {name!r} MEASURED with {value!r}, "
                    f"which this same call already recorded as {said['fact']!r} - a "
                    f"fact the ledger declares opinion_of: "
                    f"{opinion_of(said['fact'])}. Giving a model's judgement a "
                    "second name does not turn it into a reading, and the second "
                    "name is the one the gates read. THIS IS WALL 2 POINTED "
                    "INWARD: a tool may not stamp what its caller handed it, and "
                    "it may not stamp what a model handed it either. If a rule "
                    "graded these rows as well, stamp THAT number - it is a "
                    "different number, and where it is not, the judge told you "
                    "nothing the rule did not."
                )
        for candidate in self.quarantined:
            readings = [candidate]
            if type(candidate) is str:
                readings.extend(_readings_of(candidate))
            for reading in readings:
                if _same(value, reading):
                    raise MeasurementError(
                        f"{self.tool!r} tried to stamp {name!r} MEASURED with "
                        f"{value!r}, which is a value it was handed in this call's "
                        f"arguments, as {candidate!r}. THE MARK IS NOT ENOUGH ON ITS "
                        "OWN: a number written to a file and counted back, put "
                        "through json.dumps, decoded from bytes or rebuilt by any "
                        "of `.real`, `.numerator`, `operator.index` or `len()` is a "
                        "new object with no mark on it and the caller's answer "
                        "inside it. If this argument bounds the work rather than "
                        "answering it, say so: declare it in `bounds=` on the tool, "
                        "next to `measures=`, where a reviewer reads it. Declared "
                        f"bounds here: {sorted(self.bounds) or 'none'}."
                    )
        if (
            type(value) is bool
            and self.quarantined
            and not any(type(row["value"]) is not bool for row in self.minted)
        ):
            raise MeasurementError(
                f"{self.tool!r} tried to stamp the boolean fact {name!r} MEASURED "
                "in a call that was handed values and has measured nothing else. A "
                "boolean is the one thing this wall cannot check: it cannot carry "
                "the caller mark, there are only two of them, and `bool(anything "
                "non-zero)` is the one that opens the gate - so `bool(argument)` "
                "produces a True that no comparison has ever seen. What makes a "
                f"flag mean anything is the reading standing next to it, and the "
                "ledger already says so: G1 asks for `baseline_measured AND "
                "baseline_score is not null AND trivial_baseline_score is not "
                "null`, because a flag set true with nothing behind it is a badge. "
                "Stamp what was actually read first, then the flag that summarises "
                "it. A call handed nothing at all is exempt: with no supplied "
                "value in the room there is nothing to launder, and a tool that "
                "invents a constant is wall 1's problem rather than this one's."
            )
        token = _STAMPING.set(True)
        try:
            row = record(
                fact=name,
                value=value,
                origin=MEASURED,
                actor=self.actor,
                how=how,
                tool=self.tool,
                thread_id=self.thread_id,
                ledger=self.ledger,
            )
        finally:
            _STAMPING.reset(token)
        self.minted.append(
            {"fact": name, "value": row["value"], "origin": MEASURED, "how": how}
        )
        return row

    # -- wall 8: where the rows came from ---------------------------------

    def _refuse_generated_rows(
        self, fact: str, path: "str | Path | dict[str, Any]"
    ) -> None:
        """Refuse a stamp taken off a file that holds generated rows.

        Reads the census through `dataquality`, which reads the rows through the
        same `iter_records` every other part of this product reads them with -
        so "how many rows are in this file" and "how many of them are invented"
        can never disagree about what a row is.

        A CALLER MAY HAND IN THE CENSUS IT ALREADY TOOK, and one has to. The
        default read carries `count_rows`' time budget, and `measure_eval_set`
        exists precisely so that a user who has seen what the wait would be can
        say "finish it anyway" - so a wall that always used the bounded read
        would refuse the honest count on exactly the files that lever was built
        for. Found by `test_the_lever_finishes_the_count_and_the_stamp_follows`
        going red the day this wall landed, which is the test doing its job.
        A tool that already reads every row passes its own count for the same
        reason from the other end: a second pass over a five-million-row file to
        ask a question the first pass could have answered is a wait nobody
        needs.

        Three answers and each gets its own sentence, because "no" with no
        reason is the thing this product exists not to be:

        * the file could not be read -> the tool has a bigger problem than this
          wall, and saying so here would bury it. Nothing is refused; the tool's
          own reader will fail in its own words.
        * the scan did not finish -> `clean` is None, and a lower bound on "how
          many rows here are invented" cannot open a gate any more than a lower
          bound on the row count can.
        * generated rows were found -> both counts, and what to do.
        """
        census = path if isinstance(path, dict) else dataquality.synthetic_census(path)
        if not census.get("ok"):
            return
        if census.get("clean") is True:
            return

        where = census.get("path")
        if census.get("clean") is None:
            raise GeneratedRowsError(
                f"{self.tool!r} tried to stamp {fact!r} MEASURED from {where}, and "
                "the scan for generated rows did not reach the end of the file - "
                f"it stopped after {census.get('seconds')}s at "
                f"{census.get('rows')} rows. What came back is a lower bound on "
                "how much of this file was generated, and a gate cannot be opened "
                "on a lower bound. Split the real rows into their own file, or "
                "re-run this on a machine that can finish the read."
            )
        raise GeneratedRowsError(
            f"{self.tool!r} tried to stamp {fact!r} MEASURED from {where}, which "
            f"holds {census.get('synthetic')} generated rows out of "
            f"{census.get('rows')} - rows tagged "
            f"{dataquality.SYNTHETIC_FIELD!r} by this harness when it wrote them. "
            "Synthetic data can never open a gate. It cannot: every number "
            "downstream of it would be a statement about a distribution this "
            "product invented, wearing the badge of a measurement.\n\n"
            f"The {census.get('real')} real rows in there are still real. Put "
            "them in a file of their own and point this tool at that, and the "
            "gate opens on the same breath if the count clears. The generated "
            "rows are for training on, which is what they were amplified for."
        )

    # -- wall 7's open door: what a model judged ---------------------------

    def opinion(self, fact: str, value: Any, *, how: str) -> dict[str, Any]:
        """Record a judgement the harness obtained but did not take. ASSERTED.

        This is the door that stays OPEN, and it exists because the alternative
        to a labelled opinion is not a measurement, it is silence. Some tasks
        cannot be graded by a rule; that is why `model_graded` exists and why
        `metric_is_programmatic` is a fact the tree routes on. A bench that
        refused a judge outright would be less useful than one that says what
        the judge is. So the number is recorded, is displayed, and is routed on
        - and it arrives ASSERTED, which the ledger's own vocabulary already
        defines as *a model said so, nothing checked it, it may never open a
        gate*.

        THE ORIGIN IS NOT AN ARGUMENT AND IT DOES NOT COME FROM THE ACTOR
        EITHER, which is the one thing that makes this different from
        `supplied`. `supplied` asks who is speaking, because a user answering a
        question about their own week is worth more than a model guessing at it.
        Here the speaker is not in question: the judge is a model whoever
        clicked the button, so a USER actor must not upgrade its verdict to
        STATED. A person can vouch for their own history. Nobody can vouch for
        what a model thought.

        `how` is required for the reason it is required on `measured`: invariant
        3 says a displayed number carries its provenance, and this number needs
        it more than most. Name the judge, and say whether it graded its own
        answers.
        """
        name = str(fact)
        if not is_an_opinion(name):
            raise MeasurementError(
                f"{self.tool!r} recorded {name!r} as an opinion, and the ledger "
                "does not declare it one. This door is for facts carrying "
                "`opinion_of:` and for nothing else, so that the two records stay "
                "disjoint: what a judge said lives under a name no gate reads, "
                "and everything else keeps the origin its actor is worth. Use "
                "`supplied` for what the caller says, `measured` for what this "
                f"tool read. Declared opinions: {list(opinion_facts()) or 'none'}."
            )
        if not str(how).strip():
            raise MeasurementError(
                f"{self.tool!r} recorded an opinion for {name!r} with no account "
                "of whose it is. Name the judge and say whether it graded its own "
                "answers; a number with no provenance does not get displayed, and "
                "this one is somebody's opinion before it is anything else."
            )
        if value is None:
            raise MeasurementError(
                f"{self.tool!r} recorded an opinion for {name!r} with no value. A "
                "judge that returned nothing has the same knowledge as a judge "
                "that was never asked."
            )
        row = record(
            fact=name,
            value=value,
            origin=ASSERTED,
            actor=self.actor,
            how=how,
            tool=self.tool,
            thread_id=self.thread_id,
            ledger=self.ledger,
        )
        self.opinions.append(
            {"fact": name, "value": row["value"], "origin": ASSERTED, "how": how}
        )
        return row

    # -- the other half: what somebody said -------------------------------

    def supplied(self, fact: str, value: Any, *, how: str = "") -> dict[str, Any]:
        """Record what the caller says, at the origin their actor is worth.

        There is no argument for the origin. That is the point of the method: a
        model filling `facts` and a user answering a question go through the
        same door, and the door decides.
        """
        name = str(fact)
        origin = self.supplied_origin
        return record(
            fact=name,
            value=value,
            origin=origin,
            actor=self.actor,
            how=how or f"supplied by the {self.actor} through {self.tool}",
            tool=self.tool,
            thread_id=self.thread_id,
            ledger=self.ledger,
        )


def instrument_for(
    *,
    tool: str,
    measures: Iterable[str] = (),
    actor: str = DEFAULT_ACTOR,
    thread_id: int | None = None,
    arguments: dict[str, Any] | None = None,
    bounds: Iterable[str] = (),
    provides: Iterable[str] = (),
    ledger: diagnosis.Spec | None = None,
) -> Instrument:
    """Build the licence for one call. Called by the registry and by nobody else.

    ONE WALK over the arguments does both halves of wall 2: it marks every
    markable value, and it writes down every scalar that was in there. Two
    walkers with the same bound is how the mark and the comparison came to
    disagree about what "in the arguments" meant; one walk cannot.

    The argument names stay ordinary strings - they become keyword arguments to
    the handler - and every VALUE under them is marked. What a caller called a
    parameter is not a number anybody measures.

    `bounds` names the arguments left out of the quarantine, and only out of
    the quarantine: a declared bound is still marked, so stamping `max_rows`
    itself is still refused, and only a number that is EQUAL to it is let past.
    An instrument built without `bounds` quarantines everything, which is the
    strict reading and the right default - a relaxation has to be typed.
    """
    given = dict(arguments or {})
    named = frozenset(str(name) for name in bounds)
    quantities: list[Any] = []
    marked: dict[str, Any] = {}
    inspected = True
    try:
        for key, value in given.items():
            marked[str(key)] = _inspect(
                value,
                _ARGUMENT_MARKS,
                quantities=quantities,
                collect=str(key) not in named,
            )
    except _Incomplete:
        # FAIL CLOSED, AND STILL RUN. The handler gets its arguments exactly as
        # they arrived - refusing the call outright would turn a big request
        # into a crash - and `measured()` refuses to stamp anything, because the
        # check that decides whether a number came from these arguments did not
        # get to the end of them.
        marked, quantities, inspected = {}, [], False

    instrument = Instrument(
        tool=str(tool),
        actor=str(actor or DEFAULT_ACTOR),
        thread_id=thread_id,
        measures=frozenset(str(name) for name in measures),
        caller_arguments=marked,
        quarantined=tuple(quantities),
        inspected=inspected,
        bounds=named,
        provides=frozenset(str(name) for name in provides),
        ledger=ledger,
    )
    # The owner can only be set once the instrument exists, and it has to reach
    # the values the HANDLER will hold, so it is a second pass rather than an
    # argument to the walk above. See `CallerValue._owner` for what it buys:
    # a conversion performed on a worker thread is still remembered, because the
    # instrument is found from the value rather than from the context.
    _own(instrument.caller_arguments, instrument)
    return instrument


# ---------------------------------------------------------------------------
# The honest next step.


def tools_already_run(thread_id: int | None) -> set[str]:
    """Every tool that has returned `ok` in this conversation, by name.

    MEASURED 2026-09-13: the harness told the model to run `assess_the_data`
    for a fact that tool cannot settle, the model ran it, the verdict did not
    move, and the harness said the same thing again - ten turns of it. A
    remedy already spent is not a remedy, and this is how the next-move
    sentence knows. A read of the thread's own tool results; it decides
    nothing and stamps nothing.
    """
    if thread_id is None:
        return set()
    from app import events

    out: set[str] = set()
    for row in events.since(f"thread:{int(thread_id)}", limit=100_000):
        if row.get("kind") != "tool.result":
            continue
        payload = row.get("payload") or {}
        if payload.get("ok") and payload.get("name"):
            out.add(str(payload["name"]))
    return out


def _a_gate_reads(fact: str, spec: diagnosis.Spec) -> bool:
    """Is this fact in any gate row's `requires`?

    Read off `spec.gate_row_facts`, which is parsed from the rows themselves at
    load time, so a gate that starts reading a fact tomorrow is answered
    tomorrow with nothing here to update.
    """
    wanted = str(fact)
    for names in (getattr(spec, "gate_row_facts", None) or {}).values():
        if wanted in (names or ()):
            return True
    return False


def resolves(fact: str, ledger: diagnosis.Spec | None = None) -> dict[str, Any]:
    """Which tool would settle a challenge on this fact, derived not listed.

    THE LEDGER ARGUMENT IS THE FIX FOR A SENTENCE THAT WAS RIGHT BY ACCIDENT.
    Asked about `has_traces` - an AI-engineering fact - against the ML ledger,
    this used to return *"No tool in this harness measures this yet. That is a
    gap in the product rather than something you can answer"*, which is a true
    sentence with a false reason: the fact is not unmeasured, it is not this
    domain's fact at all, and the code could not tell the two apart. A harness
    whose honesty rests on saying exactly why it cannot answer must not have a
    branch that is correct by coincidence. The two states are now separate
    answers and the second one names the ledger it looked in.

    Derived from the registry's own `measures=` declarations, so a tool added
    next year that measures `corpus_tokens` becomes the answer to a challenge on
    `corpus_tokens` on the day it is registered, with nothing here to update.
    An `ask` fact has no such tool and never will; the answer is the user, in
    their own person, and `state_facts` is the door they say it through.

    WHERE TWO TOOLS MEASURE THE SAME FACT, the one that asks least of the user
    wins. `profile_dataset` and `measure_eval_set` both count an eval set;
    the second wants a path and nothing else, the first wants a path, a split
    and a row cap. Somebody who has just been told their claim is not good
    enough should be handed the shortest way to settle it, and the others are
    listed beside it rather than hidden.
    """
    from app.tools.registry import REGISTRY  # local: registry imports this module

    name = str(fact)
    current = spec(ledger)
    decl = current.facts.get(name)
    source = (decl or {}).get("source")
    line = current.substantiation(name) if decl is not None else ""

    if decl is None:
        # A NAME THIS LEDGER HAS NEVER HEARD OF. It may be a typo, or it may be
        # a real fact belonging to another domain's knowledge, and those are
        # different sentences. Neither is "no tool measures this yet", which is
        # a claim about the PRODUCT and would invite somebody to close a gap
        # that is not open.
        elsewhere = ledgers_declaring(name)
        return {
            "fact": name,
            "declared_source": None,
            "tool": None,
            "run_as": None,
            "verb": "",
            "substantiation": "",
            "note": (
                f"{name!r} is not a fact of {_ledger_name(current)}, which is the "
                "ledger this conversation is running. "
                + (
                    f"It is declared in {', '.join(elsewhere)}, so it is a real "
                    "question in another domain and not one this thread is asking."
                    if elsewhere
                    else "No ledger in this product declares it, so there is "
                    "nothing here that could settle it and nothing to ask the "
                    "user for either."
                )
            ),
            "declared_in": list(elsewhere),
        }

    if is_an_opinion(name, current):
        # WALL 7. Nothing settles a challenge on an opinion, because a challenge
        # on one is not a question about who ran the tool - it is a question
        # about whether a judgement is a reading, and the answer is no. Saying
        # "no tool measures this yet" here would read as a gap in the product
        # and invite somebody to close it.
        return {
            "fact": name,
            "declared_source": source,
            "opinion_of": opinion_of(name, current),
            "tool": None,
            "run_as": None,
            "verb": "",
            "substantiation": line.strip(),
            "note": (
                f"{name!r} is declared opinion_of: {opinion_of(name, current)}. No tool "
                "settles it, because settling it is not what it needs: a "
                "judgement is not a reading however carefully it was obtained, "
                "and no gate reads this fact. If a gate is waiting on a number, "
                "it is waiting on the one a rule produced."
            ),
        }

    candidates = sorted(
        (c for c in REGISTRY if name in c.measures),
        key=lambda c: (
            len(c.measures),
            len(c.schema.get("properties") or {}),
            c.control.order,
            c.name,
        ),
    )
    if candidates:
        first = candidates[0]
        return {
            "fact": name,
            "declared_source": source,
            "tool": first.name,
            "run_as": "harness",
            "verb": first.control.verb,
            "substantiation": line.strip(),
            "also": [c.name for c in candidates[1:]],
        }

    if source == "ask":
        return {
            "fact": name,
            "declared_source": source,
            "tool": "state_facts",
            "run_as": USER,
            "verb": "say this yourself, as the person whose project this is",
            "substantiation": line.strip(),
        }

    # A FACT NO INSTRUMENT MEASURES CAN STILL HAVE A ROUTE, and the answer used
    # to deny it. `task_family` has no `measures=` anywhere, so this branch said
    # "that is a gap in the product rather than something you can answer" -
    # while `full_defaults._from_the_eval_file` has been deriving it from the
    # eval file's own answers the whole time. Max, 2026-09-19: "This diagnosis
    # block never works... go stop just saying not work." His run of
    # 2026-09-19/20 called `state_facts` nineteen times on this fact, was told
    # each time that STATED "cannot, at this origin", and never learned that
    # counting the eval set was the move.
    #
    # THE ROUTE IS NOT `tool` AND MUST NOT BE. `tool` means "this instrument
    # measures this fact and can stamp it", and `app/asking.py` holds that to
    # its word: a card whose tool does not declare `measures=(fact,)` is a
    # harness defect, and naming `measure_eval_set` here refused 70 of them in
    # one gate run. A derivation is a different claim - run THAT tool, and the
    # harness works THIS fact out afterwards - so it gets a field of its own
    # that no invariant reads, and the sentence people actually act on.
    # Read off `full_defaults.PREREQUISITES` rather than written here, so a
    # rule added there is answered here on the day it lands.
    from app import full_defaults as _full

    route = _full.PREREQUISITES.get(name) or ()
    if route:
        needed, by_tool, why = route[0]
        return {
            "fact": name,
            "declared_source": source,
            "tool": None,
            "run_as": None,
            "verb": "",
            "substantiation": line.strip(),
            "derived_by": by_tool,
            "derived_from": needed,
            "note": (
                f"No instrument measures {name!r} and nothing you SAY will open "
                "the gate that reads it - `state_facts` records it and tells you "
                "it cannot, at that origin. The harness derives it instead, "
                f"once {needed} is measured: {why}. So the move is "
                f"{by_tool}, then run_diagnosis again."
            ),
        }

    return {
        "fact": name,
        "declared_source": source,
        "tool": None,
        "run_as": None,
        "verb": "",
        "substantiation": line.strip(),
        "held_shut_by_no_gate": not _a_gate_reads(name, current),
        "note": (
            f"No tool in this harness measures this yet. {name!r} IS a declared "
            f"fact of {_ledger_name(current)} - the ledger this conversation is "
            "running - and no registered instrument produces it, so that is a gap "
            "in the product rather than something you can answer, and saying so "
            "is the honest reply."
            # AND WHETHER IT IS STOPPING YOU, which is the half that was
            # missing. Max's run of 2026-09-21 spent turns on `data_quality`:
            # the model read "a gap in the product", concluded it was a blocked
            # gate, announced "no training or scoring can be run", and kept
            # calling state_facts at it. No gate in the ledger reads that fact.
            # A gap you cannot close and a gap that is holding you are
            # different sentences, and only one of them is worth a turn.
            + (
                " No gate in this ledger reads it, so it cannot hold anything "
                "shut - it can shape which route a walk takes, and nothing more. "
                "Do not spend turns on it: re-read the verdict you have and work "
                "the move it names."
                if not _a_gate_reads(name, current)
                else " A gate does read it, so the walk stops here until the "
                "product grows an instrument for it."
            )
        ),
    }


# ---------------------------------------------------------------------------
# THE DOOR IN THE WALL. A refusal that does not say what would have worked.
#
# The fact-origin system refusing an invented fact name is the system working:
# `answer_given`, `hardware_is_sufficient_for_training` and `you_have_an_eval_set`
# are three names a real local model sent to `state_facts` in one session, none
# of them is in the ledger, and every one of them was correctly refused. What
# the caller got back was "'answer_given' is not a declared fact; the ledger is
# in docs/diagnosis_engine.yaml" - true, unarguable, and useless to anything
# that cannot open that file. So the model guesses again, the user watches a
# second failed step go by in their transcript, and the round is spent.
#
# A REFUSAL THAT NAMES NOTHING IS A WALL WITH NO DOOR. What follows is the door,
# and it is built out of the ledger's own declarations rather than out of a list
# somebody maintains here:
#
#   * a fact's NAME, split into words - `you_have_an_eval_set` and `eval_size_n`
#     share `eval`, which is the whole of the match and is explainable to the
#     person reading the transcript;
#   * its declared ENUM or MULTI members - `privacy_ok` finds `privacy` through
#     `public_ok`;
#   * and THE NAMES OF THE TOOLS THAT MEASURE IT, read off `measures=` in the
#     registry. This is the one that answers the hardest of the three observed
#     names: nothing in the ledger contains the word "hardware", and
#     `inspect_hardware` declares `measures=("ram_gb", "vram_gb",
#     "disk_free_gb", "accelerator")`. So `hardware_is_sufficient_for_training`
#     comes back naming four legal facts AND the tool that produces them, which
#     is a better answer than a fact name on its own: those four are
#     `source: inspect` and stating them was never going to work anyway.
#
# NOTHING IS INVENTED AND NOTHING IS GUESSED AT. Every candidate is a fact the
# ledger declares, every match is a word the caller actually typed, and the word
# is returned in `matched_on` so a suggestion can be checked rather than
# trusted. A name that matches nothing gets no candidates at all - `answer_given`
# is not a fact this product has, and a plausible-looking wrong suggestion would
# cost the same round it was meant to save.


_WORD = re.compile(r"[a-z0-9]+")

#: Words dropped from a name before it is matched. English glue, and the whole
#: of it: `hardware_is_sufficient_for_training` must not find `goal_is_learning`
#: because both contain `is`. Deliberately not a domain vocabulary - `eval`,
#: `baseline`, `tried` and `budget` are exactly the words that carry the match,
#: and a stop list that grew to cover them would be this module deciding what a
#: caller meant instead of reading what they wrote.
UNINFORMATIVE_WORDS = frozenset(
    """
    a an and any are as at be been being but by can could did do does for from
    get had has have how i if in into is it its me my no not of on or our out
    so than that the their them then there these they this to up us was we were
    what when where which who will with would you your
    """.split()
)


def informative_words(text: Any) -> frozenset[str]:
    """The informative words in an identifier or a phrase."""
    return frozenset(_WORD.findall(str(text).lower())) - UNINFORMATIVE_WORDS


def _all_words(items: Iterable[Any]) -> frozenset[str]:
    """Every informative word across a collection. Empty for an empty one."""
    out: set[str] = set()
    for item in items:
        out |= informative_words(item)
    return frozenset(out)


def _measuring_tools() -> dict[str, list[str]]:
    """Fact -> the tools that declared they measure it. Read, never listed."""
    from app.tools.registry import REGISTRY  # local: registry imports this module

    out: dict[str, list[str]] = {}
    for candidate in REGISTRY:
        for name in candidate.measures:
            out.setdefault(str(name), []).append(candidate.name)
    return out


def declaration(fact: str, ledger: diagnosis.Spec | None = None) -> dict[str, Any]:
    """What the ledger says a fact IS, in the shape a caller needs to send one.

    `accepts` is the answer to "what may I put here" and it comes off the
    declaration rather than out of a sentence: a scalar type, or the exact
    members of an `enum` or `multi`. `opens_a_gate_when` is the other half and
    the one a model reliably gets wrong - a `source: inspect` fact stated by
    anybody is still not a measurement, and saying so at the point of refusal is
    cheaper than saying it after the gate fails to open.

    `default` IS WHAT THE VALUE BECOMES IF NOBODY ANSWERS, AND IT HAS TO BE SAID
    BEFORE IT IS TAKEN. A card that offers "I don't know" and cannot name what
    that costs is asking for a decision with the price hidden.

    THE CONSUMER IS THE TOOL REFUSAL, NOT THE QUESTION CARD, and this paragraph
    said otherwise until somebody checked. It claimed *"the surface drew an em
    dash instead of a number for exactly as long as this function did not send
    one"*, and that is FALSE: `app/asking.py::_declared` has computed both keys
    itself since before this function carried them, so the card has always had
    the number. Measured by removing `default` and `declares_a_default` from
    this function's output and re-deriving the card - `eval_size_n` still reads
    `default: 0, declares_a_default: True`, and `dont_know.takes` is still `0`.

    What this function feeds is `fact_name_help`'s `declared_facts_you_sent`,
    which is what a MODEL is handed when a tool refuses its arguments. That
    consumer genuinely had no default, and giving it one is worth doing on its
    own. It is simply not the thing the paragraph named, and a false account of
    why a change was needed is the failure this repository exists to end - see
    `CLAUDE.md`, rule 3.

    IT IS `diagnosis.unsupplied_value`, NOT `decl.get("default")`, and the
    difference is a wrong statement rather than a missing one. `need_type` is a
    `multi:` with no declared default and it resolves to `[]`, not to null - so
    `decl.get` would have this function announce a default the engine will not
    apply. One function answers "what happens when nobody supplies this" for the
    whole repository, and `app/asking.py::_declared` already reads that one; this
    now reads it too, so the tool refusal and the question card cannot disagree
    about the same fact.

    `declares_a_default` IS THE OTHER HALF AND IT IS NOT DECORATION. A fact with
    no default in the ledger takes null because there was nothing to take, and a
    fact declaring `default: 0` takes zero because somebody chose zero. Both send
    a `default` key; only one of them is a decision, and collapsing them is how a
    missing number becomes a confident one. `target_score` declares no default
    and must read as absent - never as 0.
    """
    name = str(fact)
    current = spec(ledger)
    decl = current.facts.get(name)
    if decl is None:
        return {"fact": name, "declared": False}
    out: dict[str, Any] = {"fact": name, "declared": True, "source": decl.get("source")}
    if "enum" in decl:
        out["accepts"] = {"one_of": list(decl["enum"])}
    elif "multi" in decl:
        out["accepts"] = {"any_of": list(decl["multi"])}
    else:
        out["accepts"] = {"type": decl.get("type")}
    out["default"] = diagnosis.unsupplied_value(decl)
    out["declares_a_default"] = "default" in decl
    out["opens_a_gate_when_the_origin_is"] = sorted(current.admissible_for(name))
    # THE LEDGER GOES WITH THE LOOKUP. `resolves(name)` alone asks the default
    # ledger who settles a challenge, so a door rendered for a second-ledger
    # fact said "no tool in this harness settles it" while the instrument that
    # settles it was registered one pack over. The declaration and its settler
    # come from the same ledger or the sentence is false by construction.
    settled = resolves(name, current)
    out["settled_by"] = {"tool": settled.get("tool"), "run_as": settled.get("run_as")}
    return out


def declaration_line(fact: str, ledger: diagnosis.Spec | None = None) -> str:
    """One declared fact on one line, for a list that would be heavy as JSON.

    `eval_size_n: int, source inspect, measured by measure_eval_set`. Same
    facts, same ledger, far less payload - which matters because the caller
    reading it is a model with a context window and the alternative is one
    nested object per fact.
    """
    decl = declaration(fact, ledger)
    if not decl.get("declared"):
        return f"{fact}: not declared"
    accepts = decl["accepts"]
    shape = (
        f"one of {accepts['one_of']}"
        if "one_of" in accepts
        else f"any of {accepts['any_of']}"
        if "any_of" in accepts
        else str(accepts.get("type"))
    )
    door = decl["settled_by"]["tool"]
    by = (
        f"measured by {door}"
        if decl["settled_by"]["run_as"] == "harness"
        else f"said by the user through {door}"
        if door
        else "no tool in this harness settles it"
    )
    return f"{fact}: {shape}, source {decl['source']}, {by}"


def nearest_facts(
    name: str, *, limit: int = 5, ledger: diagnosis.Spec | None = None
) -> list[dict[str, Any]]:
    """The declared facts a refused name is nearest to, best first.

    Empty when nothing in the ledger shares a word with what the caller typed.
    That is the honest answer and it is worth more than a filled list: a
    suggestion that is merely the least-bad of the whole ledger costs the caller
    the same round the refusal was trying to save them.
    """
    wanted = informative_words(name)
    if not wanted:
        return []
    current = spec(ledger)
    doors = _measuring_tools()
    scored: list[tuple[float, str, list[str]]] = []
    for fact, decl in current.facts.items():
        own = informative_words(fact)
        members = _all_words((decl.get("enum") or []) + (decl.get("multi") or []))
        instrument_words = _all_words(doors.get(fact, ()))

        by_name = wanted & own
        by_member = (wanted & members) - by_name
        by_tool = (wanted & instrument_words) - by_name - by_member
        score = 3.0 * len(by_name) + 2.0 * len(by_member) + 2.0 * len(by_tool)
        if not score:
            continue
        # A fact whose whole name was matched beats one that shares a word with
        # it: `eval_size_n` over `labels_are_closed_set` for `eval_set_size`.
        score += len(by_name) / max(len(own), 1)
        scored.append((score, fact, sorted(by_name | by_member | by_tool)))

    scored.sort(key=lambda row: (-row[0], row[1]))
    out = []
    for _, fact, matched in scored[:limit]:
        row = declaration(fact)
        row["matched_on"] = matched
        out.append(row)
    return out


def gate_facts(ledger: diagnosis.Spec | None = None) -> list[str]:
    """Every fact the five gates actually read, derived from their predicates.

    `Spec.gate_row_facts` is built by the engine from the `requires:` expression
    of each gate row, so this is the ledger's own answer to "which facts decide
    anything" rather than a list here that would rot the first time a predicate
    changed. It is a small fraction of the ledger, and it is what a caller who
    matched nothing should be shown instead of the whole of it.
    """
    names: set[str] = set()
    for row in spec(ledger).gate_row_facts.values():
        names |= {str(f) for f in row}
    return sorted(names)


def fact_name_help(
    names: Iterable[str], *, limit: int = 5, ledger: diagnosis.Spec | None = None
) -> dict[str, Any]:
    """What would have been accepted, for a call that named facts we refused.

    `names` is every key the caller sent, not only the bad ones: which of them
    the ledger declares is this function's to work out, and a caller that had
    one name right and one wrong should be told which was which.
    """
    current = spec(ledger)
    supplied = [str(name) for name in names]
    unknown = [name for name in supplied if name not in current.facts]
    accepted = [name for name in supplied if name in current.facts]

    did_you_mean: dict[str, list[dict[str, Any]]] = {}
    nothing_near: list[str] = []
    for name in unknown:
        candidates = nearest_facts(name, limit=limit, ledger=current)
        if candidates:
            did_you_mean[name] = candidates
        else:
            nothing_near.append(name)

    help_text = (
        "Fact names are ids declared in the harness fact ledger. They cannot be "
        "invented and a near miss is not accepted: send one of the ids named "
        "here, with a value of the type beside it. Nothing was recorded, "
        "including the names that were valid."
    )
    payload: dict[str, Any] = {
        "unknown_facts": unknown,
        "help": help_text,
        "the_ledger": {
            "declared_facts": len(current.facts),
            # THE FILE THIS ANSWER WAS READ OUT OF, not the file the product
            # shipped first. A refusal that names the wrong ledger sends the
            # reader to the wrong document to find out what IS legal.
            "file": _ledger_name(current),
            "counted": "read off the loaded ledger, not remembered",
        },
    }
    if accepted:
        payload["declared_facts_you_sent"] = [
            declaration(name, current) for name in accepted
        ]
    if did_you_mean:
        payload["did_you_mean"] = did_you_mean
    if nothing_near:
        payload["nothing_in_the_ledger_resembles"] = nothing_near
        payload["the_five_gates_read"] = [
            declaration_line(f, current) for f in gate_facts(current)
        ]
        payload["note"] = (
            "No declared fact shares a word with "
            + ", ".join(repr(n) for n in nothing_near)
            + ". Rather than guess at one, here is every fact the five gates "
            "actually read - if what you were reaching for is not among them, it "
            "is not a fact this product has, and saying so is the honest reply."
        )
    return payload


__all__ = [
    "ACTORS",
    "assemble_facts",
    "ASSERTED",
    "CallerFloat",
    "CallerInt",
    "CallerStr",
    "CallerValue",
    "ClaimedFloat",
    "ClaimedInt",
    "COMPARED_TYPES",
    "declaration",
    "declaration_line",
    "DEFAULT_ACTOR",
    "DEFAULT_SCOPE",
    "DEFAULTED",
    "ensure_quarantine_table",
    "ensure_table",
    "fact_name_help",
    "facts_at_scope",
    "gate_facts",
    "gates_that_read",
    "HARNESS",
    "informative_words",
    "INSPECTION_BUDGET",
    "Instrument",
    "instrument_for",
    "is_caller_value",
    "is_machine_scoped",
    "is_measurable",
    "ledger_view",
    "MACHINE",
    "mark_as_a_claim",
    "mark_caller_values",
    "may_be_declared_measurable",
    "MEASURED",
    "MeasurementError",
    "minting_instrument",
    "MODEL",
    "nearest_facts",
    "origin_for",
    "ORIGIN_RANK",
    "QUARANTINE_TABLE",
    "quarantine_rows",
    "quarantine_view",
    "record",
    "refuse_a_minting_reader",
    "resolves",
    "rows_for",
    "scope_of",
    "scope_policy",
    "ScopeError",
    "SCOPES",
    "Settled",
    "STATED",
    "SUPPLIED_ORIGIN",
    "THREAD",
    "thread_id_help",
    "thread_is_required_by",
    "UNINFORMATIVE_WORDS",
    "unmeasurable_reason",
    "USER",
]
