"""Twenty-nine ways to get a model's number stamped MEASURED, run every build.

## Why this file exists

Between `bb21645` and `a9245c3` the anti-laundering wall was rewritten from an
equality check into a mark-based one. It closed two families it was asked to
close and it fixed wall 3 at the ledger, properly. It also traded away coverage
the old check had, and the trade was invisible: every test in the repository was
green on both sides of it. An adversary measured twenty routes by hand and found
the wall had gone from eight laundered to eleven - five identity-preserving
rebuilds that the old equality check caught now walk through, two of them
one-token expressions a careless author writes with no laundering intent at all.

THAT WAS CAUGHT BECAUSE SOMEBODY HAPPENED TO LOOK. This file is that somebody,
run on every build. It is not a proof that the wall is complete - it is a
ratchet, so that a future change cannot silently swap one laundering family for
another and stay green while doing it.

## What is being defended

A MEASURED stamp must mean THE ENGINE WATCHED THE MEASUREMENT HAPPEN. Not "the
number looks unfamiliar", not "the number is not equal to an argument". The
whole product is the sentence *do not train anything*; the five gates are that
sentence in mechanical form; a laundered MEASURED value opens a gate that should
be shut, and the person on the other end spends a month and a GPU bill on the
strength of a number nobody counted.

## What a route is

One route is one registered tool, declaring `measures=`, driven through the real
`Registry` with `actor=model` - because that is the only path by which a value
ever reaches a handler in this product, and a unit test that called
`Instrument.measured()` directly would not exercise the caller mark at all: the
mark is put on by the registry, on the way in.

Each route then asserts ONE THING about the ledger:

    NO MEASURED ROW CARRYING THAT ROUTE'S OWN PROBE NUMBER WAS WRITTEN.

Not "the call raised". A refusal that raises where the product swallows it has
stopped nothing, and a route that quietly writes no row has stopped everything
that matters. The ledger is the thing a gate reads, so the ledger is the thing
asserted.

## The two mistakes in the adversary's own detector, which this file must not repeat

Both were found in the adversary's own harness rather than in the product, and
both would have produced a confident, vacuous green:

1. **It filtered `origin == 'measured'` against a ledger that writes
   `'MEASURED'`,** and reported zero laundered routes out of twenty. The filter
   here uses `evidence.MEASURED`, the product's own constant, and
   `TheDetectorProvesItselfTest.test_the_detector_filters_on_the_case_the_ledger
   _writes` pins the case against a hand-spelled lower-case filter finding
   nothing.

2. **It asked "is 999999 anywhere in the ledger",** so the first route that
   succeeded made every route after it look successful too. Here every route has
   its OWN probe number (`PROBES`, asserted pairwise distinct), its OWN
   sandboxed database, and reads back its OWN row. A route cannot inherit
   another's success.

## The controls, because a detector that never fires certifies nothing

* `test_the_detector_sees_a_measured_row_carrying_the_probe` - a MEASURED row is
  stamped through a bare `Instrument`, with no wall involved at all, and the
  detector must find it. This control survives any change to the wall, which is
  the point: the seventeen open routes below are also live proof that the
  detector fires, and they will not be there once somebody closes them.
* `test_an_asserted_row_carrying_the_probe_is_not_a_laundered_measurement` - the
  same number, in the same ledger, at ASSERTED. The detector must NOT find it,
  or every route here is passing on a technicality.
* `TheHonestMeasurementStillGoesThroughTest` - the opposite failure. A wall that
  blocks everything is not a wall, it is a broken product that says "do not
  train" to the person who did all the work. Counting a 120-row file with a cap
  of 120 is the case that was live and user-facing for a whole commit, and it is
  asserted here through the real tools.
* `EveryOpenRouteFailsForTheRightReasonTest` - each expected failure is re-run
  and its traceback inspected, so a route that CRASHES instead of laundering
  cannot hide inside `expectedFailure`, which swallows every exception equally.

## The open routes, and how to close one

A route that currently launders is marked with `@open_route(...)`, which names
it individually and records it in `OPEN_ROUTES`. There is no blanket skip: grep
this file for `open_route(` and the whole list is on screen.

    grep -c "^    @open_route" tests/test_laundering_routes.py

When you close one, delete its `@open_route` line and lower
`OPEN_ROUTES_AT_A9245C3` in the same diff. You will not be able to forget:
`unittest` fails a build on an unexpected success, so a closed route with the
decorator still on it turns the suite red.

**THAT LIST IS EMPTY. All seventeen were closed in one change** - the rebuild of
wall 2 in `app/tools/evidence.py`, wall 6 (`bounds=`) in
`app/tools/registry.py`, and the claim mark on both records of what was said,
in `evidence._row` and `events._as_a_claim`.

EACH ROUTE'S OWN DOCSTRING BELOW DESCRIBES THE MECHANISM THAT USED TO LET IT
THROUGH, in the present tense it was written in, and those sentences are now
history rather than description. They are kept as written: the account of how a
family got in is the useful part of a route, and rewriting seventeen of them
into the past tense would lose the thing that made the trade visible. Where a
docstring says the wall does something, read `app/tools/evidence.py` for what it
does now - in particular THE MECHANISM NOW and WHAT THIS DOES NOT CATCH, which
names the gaps that are still real and would each make a good route here.
"""

from __future__ import annotations

import copy
import json
import math
import operator
import threading
import unittest
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from app import diagnosis, events
from app.tools import REGISTRY, evidence
from app.tools.evidence import (
    ASSERTED,
    Instrument,
    MEASURED,
    MODEL,
    MeasurementError,
    USER,
)
from app.tools.registry import Registry

import support


#: Every route runs in one conversation, in its own database. A fact is scoped
#: to a thread and each test method gets a fresh sandbox, so one number is all
#: that is needed - and the probe numbers are distinct anyway, so a leak between
#: routes would be visible rather than convenient.
THREAD = 1


# ---------------------------------------------------------------------------
# The roster of routes that are open right now.


#: Route id -> the mechanism that lets it through, in one line. Filled by the
#: decorator below rather than written twice.
OPEN_ROUTES: dict[str, str] = {}


#: How many routes launder. SEVENTEEN AT `a9245c3` - the commit this file was
#: written against, "the eval set can be counted again, and the wall got better
#: and worse at once" - and none now.
#:
#: All seventeen were closed in one change: the rebuild of wall 2 in
#: `app/tools/evidence.py` and wall 6 in `app/tools/registry.py`. Measured both
#: ways round, because seventeen going to zero means nothing unless the harness
#: was capable of reporting seventeen - this file reports 17 expected failures
#: against a pristine `a9245c3` in a git worktree, and 0 against the tree that
#: closed them.
#:
#: LOWER THIS IN THE SAME DIFF THAT DELETES AN `@open_route` LINE - the number
#: going down is the whole point of the file, and it should be legible in a diff
#: without running anything. RAISING IT IS THE REGRESSION THIS FILE EXISTS TO
#: CATCH, and it goes up only with a reason written next to it.
#:
#: Zero is not "the wall is complete". `app/tools/evidence.py` states what it
#: still cannot catch under WHAT THIS DOES NOT CATCH; each of those is a route
#: somebody could add here, and adding one is the right way to report it.
OPEN_ROUTES_AT_A9245C3 = 0


def open_route(route: str, mechanism: str) -> Callable[[Callable], Callable]:
    """Mark one route as CURRENTLY LAUNDERING, by name and with a reason.

    Deliberately not `skip`. A skipped test measures nothing and reads as a
    passing one at a glance; an expected failure runs the attack, watches it
    succeed, and is counted separately in the suite's last line. And when the
    route is closed, `unittest` reports an unexpected success and fails the
    build - so the decorator cannot be left behind.

    `unittest.expectedFailure` swallows every exception equally, including a
    crash in the route's own scaffolding, which would turn a broken test into a
    silent green. `EveryOpenRouteFailsForTheRightReasonTest` re-runs each of
    these and asserts the failure is the ledger assertion and names the route.
    """

    def decorate(method: Callable) -> Callable:
        if route in OPEN_ROUTES:
            raise AssertionError(f"{route} is declared open twice")
        OPEN_ROUTES[route] = mechanism
        method.open_route = route  # type: ignore[attr-defined]
        return unittest.expectedFailure(method)

    return decorate


# ---------------------------------------------------------------------------
# The probes.


#: One number per route, and no two the same. This is the answer to the second
#: defect in the adversary's own detector - it asked whether `999999` was
#: anywhere in the ledger, so the first route that laundered made every route
#: after it look laundered too. Here a route reads back only its own number,
#: from its own database.
#:
#: The four numbers that are not in the 900_000 family belong to routes that
#: MATERIALISE the value - a file with that many lines, a list with that many
#: items, a range iterated to the end. Nine hundred thousand of anything is a
#: slow test rather than a stronger one.
#:
#: `ROUTE_18A` and `ROUTE_18B` are absent on purpose: they probe a BOOLEAN fact,
#: `baseline_measured`, and a fact with two possible values has no room for a
#: unique one. They are told apart by their databases and asserted on the fact
#: itself - no MEASURED row for `baseline_measured` at all.
PROBES: dict[str, int] = {
    "ROUTE_01_EXACT_MATCH": 900_010,
    "ROUTE_02_INT_OF_A_STRING_ARGUMENT": 900_020,
    "ROUTE_03_ARGUMENT_PLUS_ONE": 900_030,
    "ROUTE_04_ROUND_OF_FLOAT_ARGUMENT": 900_040,
    "ROUTE_05_NESTED_IN_A_DICT_ARGUMENT": 900_050,
    "ROUTE_06_NESTED_IN_A_LIST_ARGUMENT": 900_060,
    "ROUTE_07_TWO_TOOLS_A_STASHES_B_STAMPS": 900_070,
    "ROUTE_08A_LEDGER_VIA_ROWS_FOR": 900_081,
    "ROUTE_08B_LEDGER_VIA_LEDGER_VIEW": 900_082,
    "ROUTE_08C_LEDGER_VIA_ASSEMBLE_FACTS": 900_083,
    "ROUTE_09_REPLAY_FROM_THE_EVENT_LOG": 900_090,
    "ROUTE_10_WRITE_A_FILE_THEN_COUNT_IT": 1_137,
    "ROUTE_11_DEEPER_THAN_THE_DEPTH_BOUND": 900_110,
    "ROUTE_12_CONVERT_INSIDE_A_THREAD": 900_120,
    "ROUTE_12B_READ_THE_LEDGER_IN_A_THREAD": 900_125,
    "ROUTE_13A_OPERATOR_INDEX": 900_131,
    "ROUTE_13B_INT_OF_DECIMAL": 900_132,
    "ROUTE_13C_JSON_ROUND_TRIP": 900_133,
    "ROUTE_13D_NUMERATOR": 900_134,
    "ROUTE_13E_LEN_OF_A_MULTIPLIED_LIST": 1_135,
    "ROUTE_14_DOT_REAL": 900_140,
    "ROUTE_15_DOT_CONJUGATE": 900_150,
    "ROUTE_16_SUM_OVER_A_RANGE": 1_160,
    "ROUTE_17_INT_FROM_BYTES": 900_170,
    "ROUTE_19_DEEPCOPY_OF_THE_ARGUMENTS": 900_190,
    "ROUTE_20_MATH_FLOOR": 900_200,
    "ROUTE_21_ROUND_TRIP_THROUGH_A_JSON_FILE": 900_210,
}

#: The two boolean routes, which have no number. Named so the roster tests can
#: account for every route rather than for every number.
BOOLEAN_ROUTES = (
    "ROUTE_18A_A_BOOLEAN_ARGUMENT_STAMPED",
    "ROUTE_18B_BOOL_OF_AN_INTEGER_ARGUMENT",
)

#: Every route in this file. `PROBES` plus the two boolean ones.
ALL_ROUTES = tuple(PROBES) + BOOLEAN_ROUTES

#: The twenty the adversary measured by hand against `bb21645` and `a9245c3`.
#: Kept as a set so `TheRosterIsCompleteTest` can prove none of them was quietly
#: dropped while the file was being extended.
ADVERSARY_TWENTY = (
    "ROUTE_01_EXACT_MATCH",
    "ROUTE_02_INT_OF_A_STRING_ARGUMENT",
    "ROUTE_03_ARGUMENT_PLUS_ONE",
    "ROUTE_04_ROUND_OF_FLOAT_ARGUMENT",
    "ROUTE_05_NESTED_IN_A_DICT_ARGUMENT",
    "ROUTE_06_NESTED_IN_A_LIST_ARGUMENT",
    "ROUTE_07_TWO_TOOLS_A_STASHES_B_STAMPS",
    "ROUTE_08A_LEDGER_VIA_ROWS_FOR",
    "ROUTE_08B_LEDGER_VIA_LEDGER_VIEW",
    "ROUTE_08C_LEDGER_VIA_ASSEMBLE_FACTS",
    "ROUTE_09_REPLAY_FROM_THE_EVENT_LOG",
    "ROUTE_10_WRITE_A_FILE_THEN_COUNT_IT",
    "ROUTE_11_DEEPER_THAN_THE_DEPTH_BOUND",
    "ROUTE_12_CONVERT_INSIDE_A_THREAD",
    "ROUTE_12B_READ_THE_LEDGER_IN_A_THREAD",
    "ROUTE_13A_OPERATOR_INDEX",
    "ROUTE_13B_INT_OF_DECIMAL",
    "ROUTE_13C_JSON_ROUND_TRIP",
    "ROUTE_13D_NUMERATOR",
    "ROUTE_13E_LEN_OF_A_MULTIPLIED_LIST",
)


# ---------------------------------------------------------------------------
# The harness one route runs in.


class RouteHarness(unittest.TestCase):
    """A sandboxed database, a tool factory, and the detector.

    Every route registers onto a FRESH `Registry` instance rather than onto the
    application's global one. Same class, same `call()`, same walls - the tools
    the product ships are simply not in the way, and nothing a route registers
    can leak into another test's registry.
    """

    def setUp(self) -> None:
        self.root = support.sandbox(self)
        support.a_conversation(THREAD)
        evidence.ensure_table()

    # -- building a route -------------------------------------------------

    def minting_tool(
        self,
        name: str,
        properties: dict[str, Any],
        body: Callable[..., Any],
        *,
        measures: tuple[str, ...] = ("eval_size_n",),
    ) -> Registry:
        """A registered tool that DECLARES it measures, and does as it is told.

        `body(instrument, **arguments)` is the laundering attempt. It is handed
        the arguments the registry decided to pass - which, for a minting tool,
        are the caller-marked ones - and the instrument it would stamp with.

        WALL 9 IS READ OFF THE LEDGER RATHER THAN TYPED, and the reason is that
        this file is about the OTHER walls. A route whose tool declared the
        wrong capability would be refused at registration, which is wall 9
        working and this file's route never running - so the fixture takes the
        capability the fact itself admits, and every route arrives at the wall
        it was written for. A hardcoded name here was exactly that: two routes
        measuring `baseline_measured` through a tool declaring the eval-set
        counter's capability.
        """
        admitted = evidence.measured_by(measures[0]) if measures else ()
        registry = Registry()

        @registry.tool(
            name,
            description=f"Laundering route {name}, for the test suite.",
            schema={
                "type": "object",
                "properties": properties,
                "required": sorted(properties),
            },
            measures=measures,
            provides=admitted or ("data.eval_set.count",),
            label="Route",
            group="Laundering routes",
            verb="run a laundering route",
        )
        def handler(*, instrument: Instrument, **arguments: Any) -> dict[str, Any]:
            body(instrument, **arguments)
            return {"ok": True}

        return registry

    def plain_tool(
        self, registry: Registry, name: str, properties: dict[str, Any], body
    ) -> Registry:
        """A tool that measures NOTHING, for the two-step routes.

        It matters that this one declares `measures=()`: it therefore never
        receives an instrument, its arguments are never marked, and it is
        exactly the shape of the ordinary helper tool a careless author writes
        without thinking about provenance at all.
        """

        @registry.tool(
            name,
            description=f"Helper {name}, for the test suite.",
            schema={
                "type": "object",
                "properties": properties,
                "required": sorted(properties),
            },
            provides=("data.eval_set.count",),
            label="Helper",
            group="Laundering routes",
            verb="help a laundering route",
        )
        def handler(**arguments: Any) -> dict[str, Any]:
            body(**arguments)
            return {"ok": True}

        return registry

    def drive(
        self, registry: Registry, name: str, arguments: dict[str, Any]
    ) -> Any:
        """Call the tool the way `conductor._run_tool` calls one: actor=model.

        A `MeasurementError` is an OUTCOME here rather than the answer. The wall
        firing is one way for a route to be closed; a tool that never got as far
        as stamping is another; and the assertion that decides is on the ledger,
        below. This is the lesson from the last adversary's own notes: an attack
        that raises somewhere the product swallows has not been stopped, so the
        raise is not what is measured.
        """
        try:
            return registry.call(
                name, dict(arguments), actor=MODEL, thread_id=THREAD
            )
        except MeasurementError as refusal:
            self.refusal = refusal
            return {"refused": str(refusal)}

    # -- the detector -----------------------------------------------------

    def laundered_rows(self, probe: Any, fact: str = "eval_size_n") -> list[dict]:
        """MEASURED rows in THIS route's thread carrying THIS route's number.

        Three filters, and each one answers a way this detector could lie:

        * `origin == MEASURED` - `evidence.MEASURED`, the product's own
          constant, not a string spelled here. The adversary's detector spelled
          it `'measured'` against a ledger that writes `'MEASURED'` and reported
          a vacuous zero over twenty routes.
        * `fact == fact` - a route that stamped something else stamped something
          else, and calling that a success would flatter this file.
        * `value` equal AND of the same type as this route's own probe. Strict
          on type because `True == 1` in Python, and a boolean fact opened by an
          integer argument is a different route from an integer fact opened by
          an integer argument.
        """
        return [
            row
            for row in evidence.rows_for(THREAD)
            if row["origin"] == MEASURED
            and row["fact"] == fact
            and type(row["value"]) is type(probe)
            and row["value"] == probe
        ]

    def assert_not_laundered(
        self, route: str, probe: Any, fact: str = "eval_size_n"
    ) -> None:
        """The one assertion every route makes.

        The route id is in the message on purpose:
        `EveryOpenRouteFailsForTheRightReasonTest` reads it back out of the
        traceback to prove the expected failure is THIS assertion failing and
        not the scaffolding falling over.
        """
        rows = self.laundered_rows(probe, fact)
        self.assertEqual(
            rows,
            [],
            f"{route} laundered {probe!r} into a MEASURED {fact}: {rows}. "
            "A MEASURED stamp means the engine watched the measurement happen. "
            "This number came from the caller.",
        )


def nest(value: Any, depth: int) -> Any:
    """`value` inside `depth` nested dicts. Route 11's payload."""
    for _ in range(depth):
        value = {"inside": value}
    return value


def dig(value: Any) -> Any:
    """Walk back down through `nest`. Route 11's handler."""
    while isinstance(value, dict):
        value = value["inside"]
    return value


# ---------------------------------------------------------------------------
# The routes.


class LaunderingRoutesTest(RouteHarness):
    """Twenty-nine routes from a tool call to a MEASURED stamp.

    Twenty are the adversary's, in the order they were reported. Nine are
    invented here, and the invented ones are deliberately not all attacks: the
    two that matter most (`.real`, `.conjugate()`) are one-token expressions
    that a tired author writes with no laundering intent whatsoever, and three
    more are pinned CLOSED so that a future rewrite cannot re-open them by
    accident the way this one re-opened five.
    """

    # -- 1 to 6: the caller's number, dressed up ---------------------------

    def test_route_01_exact_match_stamps_the_argument(self):
        """The naive attempt. Closed by both the old wall and the new one."""
        route, probe = "ROUTE_01_EXACT_MATCH", PROBES["ROUTE_01_EXACT_MATCH"]
        registry = self.minting_tool(
            "route_01",
            {"n": {"type": "integer"}},
            lambda instrument, n: instrument.measured(
                "eval_size_n", n, how="counted it, honestly, it says"
            ),
        )
        self.drive(registry, "route_01", {"n": probe})
        self.assert_not_laundered(route, probe)

    def test_route_02_int_of_a_string_argument(self):
        """`int(argument)` where the argument arrived as text.

        A caller's strings are COMPARED rather than marked - a marked string
        breaks `pathlib`, which interns path components - and compared as the
        numbers they spell as well as as themselves.
        """
        route = "ROUTE_02_INT_OF_A_STRING_ARGUMENT"
        probe = PROBES[route]
        registry = self.minting_tool(
            "route_02",
            {"n": {"type": "string"}},
            lambda instrument, n: instrument.measured(
                "eval_size_n", int(n), how="parsed the count"
            ),
        )
        self.drive(registry, "route_02", {"n": str(probe)})
        self.assert_not_laundered(route, probe)

    def test_route_03_argument_plus_one(self):
        """Arithmetic. The mark is carried by every operation `int` supports."""
        route = "ROUTE_03_ARGUMENT_PLUS_ONE"
        probe = PROBES[route]
        registry = self.minting_tool(
            "route_03",
            {"n": {"type": "integer"}},
            lambda instrument, n: instrument.measured(
                "eval_size_n", n + 1, how="counted the header row too"
            ),
        )
        self.drive(registry, "route_03", {"n": probe - 1})
        self.assert_not_laundered(route, probe)

    def test_route_04_round_of_float_argument(self):
        """`float()` cannot carry the mark, so the conversion is remembered."""
        route = "ROUTE_04_ROUND_OF_FLOAT_ARGUMENT"
        probe = PROBES[route]
        registry = self.minting_tool(
            "route_04",
            {"n": {"type": "integer"}},
            lambda instrument, n: instrument.measured(
                "eval_size_n", round(float(n)), how="rounded the count"
            ),
        )
        self.drive(registry, "route_04", {"n": probe})
        self.assert_not_laundered(route, probe)

    def test_route_05_nested_in_a_dict_argument(self):
        """One level of JSON is not a laundry. `mark_caller_values` recurses."""
        route = "ROUTE_05_NESTED_IN_A_DICT_ARGUMENT"
        probe = PROBES[route]
        registry = self.minting_tool(
            "route_05",
            {"report": {"type": "object"}},
            lambda instrument, report: instrument.measured(
                "eval_size_n", report["counts"]["rows"], how="read the report"
            ),
        )
        self.drive(
            registry, "route_05", {"report": {"counts": {"rows": probe}}}
        )
        self.assert_not_laundered(route, probe)

    def test_route_06_nested_in_a_list_argument(self):
        """The same, through the other container a JSON call can carry."""
        route = "ROUTE_06_NESTED_IN_A_LIST_ARGUMENT"
        probe = PROBES[route]
        registry = self.minting_tool(
            "route_06",
            {"counts": {"type": "array"}},
            lambda instrument, counts: instrument.measured(
                "eval_size_n", counts[0], how="took the first count"
            ),
        )
        self.drive(registry, "route_06", {"counts": [probe, 12]})
        self.assert_not_laundered(route, probe)

    # -- 7: two tools ------------------------------------------------------

    def test_route_07_two_tools_a_stashes_b_stamps(self):
        """The laundering is split across two calls, and neither one looks bad.

        Tool A declares `measures=()`. Its arguments are therefore never marked
        - deliberately, because marking every tool's arguments is a change to
        what every handler in the product holds - so the number it stashes is an
        ordinary `int`. Tool B takes no arguments at all, so there is nothing
        for the wall to compare or mark, and stamps what it finds in the stash.

        This is not a clever attack. It is the shape of any two-step tool pair:
        `prepare_dataset` writing to module state and `count_dataset` reading
        it. The mark is per-call and the model's turn is not.
        """
        route = "ROUTE_07_TWO_TOOLS_A_STASHES_B_STAMPS"
        probe = PROBES[route]
        stash: dict[str, Any] = {}

        registry = Registry()
        self.plain_tool(
            registry,
            "route_07_stash",
            {"n": {"type": "integer"}},
            lambda n: stash.__setitem__("n", n),
        )

        @registry.tool(
            "route_07_stamp",
            description="Stamps whatever the previous call left behind.",
            schema={"type": "object", "properties": {}},
            measures=("eval_size_n",),
            provides=("data.eval_set.count",),
            label="Route",
            group="Laundering routes",
            verb="run a laundering route",
        )
        def stamp(*, instrument: Instrument):
            instrument.measured(
                "eval_size_n", stash["n"], how="the number from the last step"
            )
            return {"ok": True}

        self.drive(registry, "route_07_stash", {"n": probe})
        self.drive(registry, "route_07_stamp", {})
        self.assert_not_laundered(route, probe)

    # -- 8: reading the claim ledger ---------------------------------------

    def seed_a_claim(self, probe: int) -> None:
        """The model asserts the number through the real `state_facts` tool.

        Through the application's own registry, because this half is not the
        attack - it is the ordinary, permitted thing a model does. It writes an
        ASSERTED row, which is what routes 8 and 12b then try to re-stamp.
        """
        REGISTRY.call(
            "state_facts",
            {"facts": {"eval_size_n": probe}},
            actor=MODEL,
            thread_id=THREAD,
        )

    def test_route_08a_minting_tool_reads_the_ledger_via_rows_for(self):
        """Wall 3, at the exported reader that used to have no guard."""
        route = "ROUTE_08A_LEDGER_VIA_ROWS_FOR"
        probe = PROBES[route]
        self.seed_a_claim(probe)

        def body(instrument: Instrument):
            for row in evidence.rows_for(instrument.thread_id):
                if row["fact"] == "eval_size_n":
                    instrument.measured(
                        "eval_size_n", row["value"], how="it was in the ledger"
                    )

        registry = self.minting_tool("route_08a", {}, body)
        self.drive(registry, "route_08a", {})
        self.assert_not_laundered(route, probe)

    def test_route_08b_minting_tool_reads_the_ledger_via_ledger_view(self):
        """The same hole a second time, through the transcript view."""
        route = "ROUTE_08B_LEDGER_VIA_LEDGER_VIEW"
        probe = PROBES[route]
        self.seed_a_claim(probe)

        def body(instrument: Instrument):
            for row in evidence.ledger_view(instrument.thread_id):
                if row["fact"] == "eval_size_n":
                    instrument.measured(
                        "eval_size_n", row["value"], how="it was in the view"
                    )

        registry = self.minting_tool("route_08b", {}, body)
        self.drive(registry, "route_08b", {})
        self.assert_not_laundered(route, probe)

    def test_route_08c_minting_tool_reads_the_ledger_via_assemble_facts(self):
        """And through the fact sheet the engine itself reasons over."""
        route = "ROUTE_08C_LEDGER_VIA_ASSEMBLE_FACTS"
        probe = PROBES[route]
        self.seed_a_claim(probe)

        def body(instrument: Instrument):
            sheet, _ = evidence.assemble_facts(instrument.thread_id)
            instrument.measured(
                "eval_size_n",
                diagnosis.bare(sheet["eval_size_n"]),
                how="it was on the fact sheet",
            )

        registry = self.minting_tool("route_08c", {}, body)
        self.drive(registry, "route_08c", {})
        self.assert_not_laundered(route, probe)

    # -- 9: the event log --------------------------------------------------

    def test_route_09_replay_the_number_from_the_event_log(self):
        """The claim ledger has one door. The transcript has none.

        `conductor._run_tool` appends a `tool.call` event carrying `call.name`
        and `call.arguments` verbatim, scoped to the thread, before it runs
        anything. So every number a model has ever put in a tool call is sitting
        in a second table, in the same database, at thread scope - and wall 3
        stands on `fact_evidence` alone.

        The event here is written exactly as the conductor writes it, so this is
        a replay of the product's own transcript and not a fixture invented to
        make a point.
        """
        route = "ROUTE_09_REPLAY_FROM_THE_EVENT_LOG"
        probe = PROBES[route]
        events.append(
            "tool.call",
            {
                "id": "call_1",
                "name": "state_facts",
                "arguments": {"facts": {"eval_size_n": probe}},
            },
            thread_id=THREAD,
        )

        def body(instrument: Instrument):
            for event in events.since(f"thread:{instrument.thread_id}"):
                facts = (event["payload"].get("arguments") or {}).get("facts") or {}
                if "eval_size_n" in facts:
                    instrument.measured(
                        "eval_size_n",
                        facts["eval_size_n"],
                        how="recovered from the transcript",
                    )

        registry = self.minting_tool("route_09", {}, body)
        self.drive(registry, "route_09", {})
        self.assert_not_laundered(route, probe)

    # -- 10: through the filesystem ----------------------------------------

    def test_route_10_write_the_number_into_a_file_then_measure_the_file(self):
        """The engine watched a measurement. It was a measurement of its own input.

        This is the route that shows why "did the engine watch it" is the right
        question and "is the number unfamiliar" is not. The line count is honest
        - the file really has that many lines - and the file has that many lines
        because the model said so. Nothing in `evidence.py` can see the
        difference, because by the time the count exists the provenance chain has
        gone through the operating system.
        """
        route = "ROUTE_10_WRITE_A_FILE_THEN_COUNT_IT"
        probe = PROBES[route]
        target = self.root / "generated_eval.jsonl"

        def body(instrument: Instrument, n, path):
            written = Path(path)
            written.write_text(
                "\n".join(json.dumps({"q": i}) for i in range(n)), encoding="utf-8"
            )
            counted = len(written.read_text(encoding="utf-8").splitlines())
            instrument.measured(
                "eval_size_n", counted, how=f"counted {counted} rows in {written}"
            )

        registry = self.minting_tool(
            "route_10",
            {"n": {"type": "integer"}, "path": {"type": "string"}},
            body,
        )
        self.drive(registry, "route_10", {"n": probe, "path": str(target)})
        self.assert_not_laundered(route, probe)

    # -- 11: below the traversal bound -------------------------------------

    def test_route_11_nested_deeper_than_the_traversal_bound(self):
        """The bound is there for a good reason and it is still a hole.

        A model's arguments arrive as JSON and a deep or self-referential
        structure is a denial of service rather than a fact, so the marker stops
        at eight levels. Everything below eight is therefore invisible to all
        three walkers at once - it is not marked going in, it is not compared,
        and `is_caller_value` would not find it even if it were.

        Ten levels, so the failure is not a boundary argument: nine is the last
        level that gets marked today.
        """
        route = "ROUTE_11_DEEPER_THAN_THE_DEPTH_BOUND"
        probe = PROBES[route]
        registry = self.minting_tool(
            "route_11",
            {"report": {"type": "object"}},
            lambda instrument, report: instrument.measured(
                "eval_size_n", dig(report), how="read it out of the report"
            ),
        )
        self.drive(registry, "route_11", {"report": nest(probe, 10)})
        self.assert_not_laundered(route, probe)

    # -- 12: another thread ------------------------------------------------

    def test_route_12_convert_the_value_inside_a_thread(self):
        """The mark is a type; the memory of a conversion is a context variable.

        `str(argument)` keeps the mark - `__str__` is wrapped - and `int()` of
        that string cannot, because CPython normalises whatever `__int__`
        returns back to an exact `int`. The wall's answer is to REMEMBER the
        conversion on the open instrument. `threading.Thread` does not inherit
        the calling context, so inside the thread `_MINTING.get()` is `None`,
        the wrapper returns early, and nothing is remembered.

        Nothing here is exotic. A tool that parses on a worker thread to keep an
        event loop free is an ordinary tool.
        """
        route = "ROUTE_12_CONVERT_INSIDE_A_THREAD"
        probe = PROBES[route]

        def body(instrument: Instrument, n):
            carried: dict[str, Any] = {}

            def convert():
                carried["value"] = int(str(n))

            worker = threading.Thread(target=convert)
            worker.start()
            worker.join()
            instrument.measured(
                "eval_size_n", carried["value"], how="parsed off the worker"
            )

        registry = self.minting_tool("route_12", {"n": {"type": "integer"}}, body)
        self.drive(registry, "route_12", {"n": probe})
        self.assert_not_laundered(route, probe)

    def test_route_12b_read_the_claim_ledger_from_inside_a_thread(self):
        """Wall 3 stands on the table, and the table is asked a per-thread question.

        Moving the guard from `assemble_facts` down to `_ledger_rows` was right
        and it closed three readers at once. It did not change what the guard
        reads: a `ContextVar`, which is exactly as wide as the thread that set
        it. The model's ASSERTED number comes back out of the ledger on a worker
        thread and is stamped MEASURED on the main one.
        """
        route = "ROUTE_12B_READ_THE_LEDGER_IN_A_THREAD"
        probe = PROBES[route]
        self.seed_a_claim(probe)

        def body(instrument: Instrument):
            carried: dict[str, Any] = {}

            def read():
                carried["rows"] = evidence.rows_for(instrument.thread_id)

            worker = threading.Thread(target=read)
            worker.start()
            worker.join()
            for row in carried.get("rows") or []:
                if row["fact"] == "eval_size_n":
                    instrument.measured(
                        "eval_size_n", row["value"], how="read on the worker"
                    )

        registry = self.minting_tool("route_12b", {}, body)
        self.drive(registry, "route_12b", {})
        self.assert_not_laundered(route, probe)

    # -- 13: the identity-preserving rebuilds ------------------------------
    #
    # THE REGRESSION. All five of these were caught by the equality check at
    # `bb21645` - it refused any value equal, at the same type, to a scalar in
    # the arguments, and every one of these produces exactly that. The
    # mark-based wall at `a9245c3` catches transformations the equality check
    # could not, and lets these through, because each one rebuilds the caller's
    # number through C code that is required to return an exact type.
    #
    # Two of them are one token. Nobody writing `argument.numerator` is
    # attacking anything.

    def test_route_13a_operator_index_of_the_argument(self):
        route = "ROUTE_13A_OPERATOR_INDEX"
        probe = PROBES[route]
        registry = self.minting_tool(
            "route_13a",
            {"n": {"type": "integer"}},
            lambda instrument, n: instrument.measured(
                "eval_size_n", operator.index(n), how="coerced to an index"
            ),
        )
        self.drive(registry, "route_13a", {"n": probe})
        self.assert_not_laundered(route, probe)

    def test_route_13b_int_of_decimal_of_the_argument(self):
        route = "ROUTE_13B_INT_OF_DECIMAL"
        probe = PROBES[route]
        registry = self.minting_tool(
            "route_13b",
            {"n": {"type": "integer"}},
            lambda instrument, n: instrument.measured(
                "eval_size_n", int(Decimal(n)), how="normalised the count"
            ),
        )
        self.drive(registry, "route_13b", {"n": probe})
        self.assert_not_laundered(route, probe)

    def test_route_13c_json_round_trip_of_the_argument(self):
        """Named in `app/tools/evidence.py` as a hole it cannot close.

        Kept here rather than left to that module's docstring, because a hole
        that is only described is a hole nobody counts. It is one of the five
        the equality check caught and this one does not.
        """
        route = "ROUTE_13C_JSON_ROUND_TRIP"
        probe = PROBES[route]
        registry = self.minting_tool(
            "route_13c",
            {"n": {"type": "integer"}},
            lambda instrument, n: instrument.measured(
                "eval_size_n", json.loads(json.dumps(n)), how="normalised the count"
            ),
        )
        self.drive(registry, "route_13c", {"n": probe})
        self.assert_not_laundered(route, probe)

    def test_route_13d_numerator_of_the_argument(self):
        """One token, and no intent. This is the case that should worry us most.

        `argument.numerator` is what somebody writes when they have a value that
        might be a `Fraction` and want the integer out of it. There is no attack
        in it, there is no cleverness in it, and it opens G0.
        """
        route = "ROUTE_13D_NUMERATOR"
        probe = PROBES[route]
        registry = self.minting_tool(
            "route_13d",
            {"n": {"type": "integer"}},
            lambda instrument, n: instrument.measured(
                "eval_size_n", n.numerator, how="took the whole part"
            ),
        )
        self.drive(registry, "route_13d", {"n": probe})
        self.assert_not_laundered(route, probe)

    def test_route_13e_len_of_a_list_built_from_the_argument(self):
        """A count of something real, which the caller decided the size of.

        The same shape as route 10 without the filesystem: build a thing with
        `n` items, count the items, and the count is a genuine `len()` of a
        genuine list.
        """
        route = "ROUTE_13E_LEN_OF_A_MULTIPLIED_LIST"
        probe = PROBES[route]
        registry = self.minting_tool(
            "route_13e",
            {"n": {"type": "integer"}},
            lambda instrument, n: instrument.measured(
                "eval_size_n", len([0] * n), how="counted the rows"
            ),
        )
        self.drive(registry, "route_13e", {"n": probe})
        self.assert_not_laundered(route, probe)

    # -- 14 to 21: invented here -------------------------------------------
    #
    # The brief for this file asked for five more, and asked that they be about
    # what a careless author does by accident rather than only what an attacker
    # does on purpose. Nine follow. Six are open; three are pinned CLOSED, which
    # is the other half of a ratchet - the regression this file exists to catch
    # was families going from closed to open while everything stayed green.

    def test_route_14_dot_real_of_the_argument(self):
        """`.real` on a number that might be complex. One token, no intent."""
        route = "ROUTE_14_DOT_REAL"
        probe = PROBES[route]
        registry = self.minting_tool(
            "route_14",
            {"n": {"type": "integer"}},
            lambda instrument, n: instrument.measured(
                "eval_size_n", n.real, how="took the real part"
            ),
        )
        self.drive(registry, "route_14", {"n": probe})
        self.assert_not_laundered(route, probe)

    def test_route_15_dot_conjugate_of_the_argument(self):
        """The third member of the numeric-tower family, and there may be more.

        `.real`, `.numerator` and `.conjugate()` are all `int`'s implementation
        of the `numbers.Integral` protocol, and all three return an exact `int`.
        A wall built by listing which operations carry the mark will keep meeting
        these; a wall built so the tool never holds the caller's number at all
        would not have any of them.
        """
        route = "ROUTE_15_DOT_CONJUGATE"
        probe = PROBES[route]
        registry = self.minting_tool(
            "route_15",
            {"n": {"type": "integer"}},
            lambda instrument, n: instrument.measured(
                "eval_size_n", n.conjugate(), how="normalised the count"
            ),
        )
        self.drive(registry, "route_15", {"n": probe})
        self.assert_not_laundered(route, probe)

    def test_route_16_sum_over_a_range_of_the_argument(self):
        """"I counted the rows" - over rows the caller asked to be generated.

        The careless version of route 10 with no file in it. An author who has
        been told "count it, do not take the caller's word" writes a loop, and
        the loop is over the caller's word.
        """
        route = "ROUTE_16_SUM_OVER_A_RANGE"
        probe = PROBES[route]
        registry = self.minting_tool(
            "route_16",
            {"n": {"type": "integer"}},
            lambda instrument, n: instrument.measured(
                "eval_size_n",
                sum(1 for _ in range(n)),
                how="counted the rows one at a time",
            ),
        )
        self.drive(registry, "route_16", {"n": probe})
        self.assert_not_laundered(route, probe)

    def test_route_17_int_from_bytes_of_the_argument(self):
        """The same family as the JSON round trip, through a different codec.

        Worth having as its own route rather than as a variant: it shows the
        JSON hole is not about JSON. Any serialisation this process performs and
        reverses drops the mark, and there is no list of codecs that can be
        completed.
        """
        route = "ROUTE_17_INT_FROM_BYTES"
        probe = PROBES[route]
        registry = self.minting_tool(
            "route_17",
            {"n": {"type": "integer"}},
            lambda instrument, n: instrument.measured(
                "eval_size_n",
                int.from_bytes(n.to_bytes(8, "big"), "big"),
                how="decoded the count",
            ),
        )
        self.drive(registry, "route_17", {"n": probe})
        self.assert_not_laundered(route, probe)

    def test_route_18a_a_boolean_argument_stamped_as_the_boolean_fact(self):
        """G1's own fact, handed over as a boolean and refused.

        `baseline_measured` is the fact `G1_BASELINE_MEASURED` reads, and it is
        a boolean, so it is the one fact where a caller's value and an honest
        measurement CANNOT be told apart by looking at the number. CPython will
        not let `bool` be subclassed, so it cannot carry the mark; the wall
        compares instead, and the comparison holds.
        """
        route = "ROUTE_18A_A_BOOLEAN_ARGUMENT_STAMPED"
        registry = self.minting_tool(
            "route_18a",
            {"scored": {"type": "boolean"}},
            lambda instrument, scored: instrument.measured(
                "baseline_measured", scored, how="the baseline was scored"
            ),
            measures=("baseline_measured",),
        )
        self.drive(registry, "route_18a", {"scored": True})
        self.assert_not_laundered(route, True, fact="baseline_measured")

    def test_route_18b_bool_of_an_integer_argument_opens_g1(self):
        """The boolean route that IS open, and it is the worst one in the file.

        Route 18a is refused because a caller's `True` is in the compared set. A
        caller's INTEGER is marked instead of compared, and `bool()` of it is a
        plain `True` that no check has ever seen. So `G1_BASELINE_MEASURED` -
        "somebody measured what the existing thing scores" - opens on
        `bool(1)`, and every TRAIN outcome behind it becomes reachable without a
        baseline having been scored at all.

        The number does not even have to be plausible. Any non-zero integer in
        any argument of a tool that declares `measures=("baseline_measured",)`
        does it.
        """
        route = "ROUTE_18B_BOOL_OF_AN_INTEGER_ARGUMENT"
        registry = self.minting_tool(
            "route_18b",
            {"correct": {"type": "integer"}},
            lambda instrument, correct: instrument.measured(
                "baseline_measured", bool(correct), how="the baseline was scored"
            ),
            measures=("baseline_measured",),
        )
        self.drive(registry, "route_18b", {"correct": 1})
        self.assert_not_laundered(route, True, fact="baseline_measured")

    def test_route_19_deepcopy_of_the_arguments(self):
        """PINNED CLOSED. A defensive copy is the most ordinary thing there is.

        `copy.deepcopy` rebuilds an `int` subclass through `__reduce_ex__`,
        which reconstructs the same class - so the mark survives. That is luck
        rather than design, and it is exactly the kind of thing that stops being
        true when somebody gives `CallerValue` a `__reduce__` or a `__slots__`
        layout it does not have today. Pinned here so that stops being silent.
        """
        route = "ROUTE_19_DEEPCOPY_OF_THE_ARGUMENTS"
        probe = PROBES[route]
        registry = self.minting_tool(
            "route_19",
            {"report": {"type": "object"}},
            lambda instrument, report: instrument.measured(
                "eval_size_n", copy.deepcopy(report)["rows"], how="read the report"
            ),
        )
        self.drive(registry, "route_19", {"report": {"rows": probe}})
        self.assert_not_laundered(route, probe)

    def test_route_20_math_floor_of_the_argument(self):
        """PINNED CLOSED. `__floor__` is in `_DERIVING`, and must stay there.

        The arithmetic family is the one the mark was built for and the one the
        equality check could not do. If a future rewrite trades it away for
        something that closes route 13, this goes red - which is the entire
        purpose of this file, stated as one test.
        """
        route = "ROUTE_20_MATH_FLOOR"
        probe = PROBES[route]
        registry = self.minting_tool(
            "route_20",
            {"n": {"type": "integer"}},
            lambda instrument, n: instrument.measured(
                "eval_size_n", math.floor(n), how="rounded down"
            ),
        )
        self.drive(registry, "route_20", {"n": probe})
        self.assert_not_laundered(route, probe)

    def test_route_21_round_trip_the_arguments_through_a_json_file(self):
        """Route 13c as an accident rather than an attack.

        A tool that writes its request to disk - a job spec, a cache entry, a
        manifest - and then reads the file back as its working copy has
        laundered every number in the call without anybody deciding to. There is
        no attacker in this one at all.
        """
        route = "ROUTE_21_ROUND_TRIP_THROUGH_A_JSON_FILE"
        probe = PROBES[route]
        manifest = self.root / "request.json"

        def body(instrument: Instrument, n, path):
            written = Path(path)
            written.write_text(json.dumps({"rows": n}), encoding="utf-8")
            recovered = json.loads(written.read_text(encoding="utf-8"))
            instrument.measured(
                "eval_size_n", recovered["rows"], how="read back from the manifest"
            )

        registry = self.minting_tool(
            "route_21",
            {"n": {"type": "integer"}, "path": {"type": "string"}},
            body,
        )
        self.drive(registry, "route_21", {"n": probe, "path": str(manifest)})
        self.assert_not_laundered(route, probe)


# ---------------------------------------------------------------------------
# The detector, proving itself.


class TheDetectorProvesItselfTest(RouteHarness):
    """A procedure that returns green against known-broken code certifies nothing.

    Every assertion in the class above is a NEGATIVE - no row was written - and
    a negative is what a detector that cannot see anything also reports. Two
    detectors on this project have already produced a confident zero that way.
    So this class makes the detector fire, makes it not fire, and pins the two
    specific mistakes the last one made.
    """

    def test_the_detector_sees_a_measured_row_carrying_the_probe(self):
        """THE POSITIVE CONTROL, and it does not depend on the wall at all.

        A MEASURED row is written through the real stamping path - a real
        `Instrument`, `measured()`, the real ledger - with nothing in the
        arguments, so no wall is involved and nothing here can be closed by the
        sibling change that closes the routes. If this ever fails, every "no row
        was written" in this file is worthless.
        """
        probe = 424_242
        instrument = evidence.instrument_for(
            tool="positive_control",
            measures=("eval_size_n",),
            provides=("data.eval_set.count",),
            actor=USER,
            thread_id=THREAD,
            arguments={},
        )
        instrument.measured("eval_size_n", probe, how="a row, on purpose")

        rows = self.laundered_rows(probe)
        self.assertEqual(len(rows), 1, "the detector cannot see a MEASURED row")
        self.assertEqual(rows[0]["value"], probe)
        self.assertEqual(rows[0]["origin"], MEASURED)

    def test_the_detector_filters_on_the_case_the_ledger_writes(self):
        """The adversary's first mistake, pinned so it cannot happen again.

        Their detector matched `origin == 'measured'` against a ledger that
        writes `'MEASURED'`, and reported zero laundered routes out of twenty -
        a completely vacuous green. The filter in `laundered_rows` uses the
        product's own constant; this asserts what that constant spells and that
        the lower-case spelling finds nothing, so a future edit that hard-codes
        a string has to disagree with a test rather than with a comment.
        """
        instrument = evidence.instrument_for(
            tool="case_control",
            measures=("eval_size_n",),
            provides=("data.eval_set.count",),
            thread_id=THREAD,
            arguments={},
        )
        instrument.measured("eval_size_n", 7, how="a row, on purpose")

        rows = evidence.rows_for(THREAD)
        self.assertEqual([row["origin"] for row in rows], ["MEASURED"])
        self.assertEqual(MEASURED, "MEASURED")
        self.assertEqual(
            [row for row in rows if row["origin"] == "measured"],
            [],
            "the ledger writes MEASURED in upper case and a lower-case filter "
            "finds nothing - which is the vacuous zero this file exists to "
            "avoid reporting",
        )

    def test_a_row_from_another_route_is_not_counted_as_this_route_s(self):
        """The adversary's second mistake: "is the number anywhere in the ledger".

        Their detector asked that, so every route after the first success
        inherited a false positive. Two rows are written here and each probe
        finds exactly its own.
        """
        instrument = evidence.instrument_for(
            tool="isolation_control",
            measures=("eval_size_n",),
            provides=("data.eval_set.count",),
            thread_id=THREAD,
            arguments={},
        )
        instrument.measured("eval_size_n", 111, how="the first route's row")
        instrument.measured("eval_size_n", 222, how="the second route's row")

        self.assertEqual([row["value"] for row in self.laundered_rows(111)], [111])
        self.assertEqual([row["value"] for row in self.laundered_rows(222)], [222])
        self.assertEqual(self.laundered_rows(333), [])

    def test_an_asserted_row_carrying_the_probe_is_not_a_laundered_measurement(self):
        """The other way the detector could lie: counting a claim as a stamp.

        The model's number is in the ledger, at ASSERTED, which is correct and
        harmless - `app/diagnosis.py` will not open a gate on it. A detector
        that flagged it would make every route in this file fail for the wrong
        reason and the file would be measuring the ledger's existence rather
        than the wall.
        """
        probe = 555_555
        REGISTRY.call(
            "state_facts",
            {"facts": {"eval_size_n": probe}},
            actor=MODEL,
            thread_id=THREAD,
        )
        self.assertEqual(
            [row["origin"] for row in evidence.rows_for(THREAD)], [ASSERTED]
        )
        self.assertEqual(self.laundered_rows(probe), [])

    def test_the_strict_type_check_tells_one_from_true(self):
        """`True == 1`, so a loose detector would confuse two different routes.

        Route 18b stamps `True` for a boolean fact from an integer argument.
        Without the type check its row would answer to a probe of `1`, and a
        route that had been closed would read as still open.
        """
        instrument = evidence.instrument_for(
            tool="type_control",
            measures=("baseline_measured",),
            provides=("measurement.baseline.score",),
            thread_id=THREAD,
            arguments={},
        )
        instrument.measured("baseline_measured", True, how="a boolean row")
        self.assertEqual(
            len(self.laundered_rows(True, fact="baseline_measured")), 1
        )
        self.assertEqual(self.laundered_rows(1, fact="baseline_measured"), [])


# ---------------------------------------------------------------------------
# The opposite failure.


class TheHonestMeasurementStillGoesThroughTest(RouteHarness):
    """A wall that blocks everything is not a wall, it is a broken product.

    This is the direction the equality check failed in, and it failed in front
    of a real user: `profile_dataset` counting a 120-row eval file with
    `max_rows=120` was refused as laundering and returned HTTP 500, so G0 - the
    gate the whole tree stands on - could not be opened the ordinary way for a
    whole commit. Every route above would still pass against a `measured()` that
    raised unconditionally. These three are why that is not what happened.
    """

    def eval_file(self, rows: int) -> Path:
        path = self.root / f"eval_{rows}.jsonl"
        path.write_text(
            "\n".join(json.dumps({"q": f"q{i}", "a": f"a{i % 5}"}) for i in range(rows)),
            encoding="utf-8",
        )
        return path

    def test_counting_a_120_row_file_with_a_cap_of_120_stamps_measured(self):
        """The reported reproduction, through the tool the user actually calls."""
        path = self.eval_file(120)
        result = REGISTRY.call(
            "profile_dataset",
            {"path": str(path), "split": "eval", "max_rows": 120},
            actor=MODEL,
            thread_id=THREAD,
        )
        self.assertEqual(result["rows"], 120)
        self.assertEqual(
            [(row["fact"], row["value"], row["origin"])
             for row in evidence.rows_for(THREAD)],
            [("eval_size_n", 120, MEASURED)],
        )

    def test_measure_eval_set_counts_a_file_and_stamps_measured(self):
        """The other counting tool, and the one `evidence.resolves` recommends."""
        path = self.eval_file(137)
        result = REGISTRY.call(
            "measure_eval_set", {"path": str(path)}, actor=USER, thread_id=THREAD
        )
        self.assertEqual(result["rows"], 137)
        self.assertEqual(
            [(row["fact"], row["value"], row["origin"])
             for row in evidence.rows_for(THREAD)],
            [("eval_size_n", 137, MEASURED)],
        )

    def test_the_same_number_is_refused_from_a_caller_and_stamped_from_a_disk(self):
        """The whole property in one test: provenance decides, not the value.

        A tool handed `120` and stamping it is refused. `profile_dataset`
        counting a 120-row file, in the same conversation, with `max_rows=120`
        so the number is in the arguments too, is stamped. One number, two
        origins, two answers - and if a future wall cannot tell them apart it
        will fail one half of this test whichever way it errs.
        """
        registry = self.minting_tool(
            "honest_control",
            {"n": {"type": "integer"}},
            lambda instrument, n: instrument.measured(
                "eval_size_n", n, how="the caller said so"
            ),
        )
        self.drive(registry, "honest_control", {"n": 120})
        self.assertEqual(evidence.rows_for(THREAD), [])

        path = self.eval_file(120)
        REGISTRY.call(
            "profile_dataset",
            {"path": str(path), "split": "eval", "max_rows": 120},
            actor=MODEL,
            thread_id=THREAD,
        )
        self.assertEqual(
            [(row["value"], row["origin"]) for row in evidence.rows_for(THREAD)],
            [(120, MEASURED)],
        )


# ---------------------------------------------------------------------------
# The roster, and the expected failures, checked rather than trusted.


class TheRosterIsCompleteTest(unittest.TestCase):
    """The bookkeeping this file's usefulness depends on.

    A route that is declared and never run, a probe shared by two routes, or an
    `@open_route` naming something that does not exist would each turn the
    ratchet into decoration.
    """

    def route_methods(self) -> dict[str, Any]:
        return {
            name: function
            for name, function in vars(LaunderingRoutesTest).items()
            if name.startswith("test_route_")
        }

    def test_no_two_routes_share_a_probe_number(self):
        """The answer to "is the number anywhere in the ledger", at the source."""
        self.assertEqual(
            len(set(PROBES.values())),
            len(PROBES),
            "two routes share a probe number, so one can inherit the other's row",
        )

    def test_every_declared_route_has_exactly_one_test(self):
        """Derived from the source rather than listed, so it cannot drift.

        Each route id must appear in the body of exactly one `test_route_*`
        method. A route added to `PROBES` and never exercised would otherwise
        look like coverage in a diff.
        """
        import inspect

        found: dict[str, list[str]] = {route: [] for route in ALL_ROUTES}
        for name, function in self.route_methods().items():
            source = inspect.getsource(function)
            for route in ALL_ROUTES:
                if route in source:
                    found[route].append(name)
        for route, methods in found.items():
            with self.subTest(route=route):
                self.assertEqual(
                    len(methods), 1, f"{route} is exercised by {methods}"
                )

    def test_every_route_the_adversary_measured_is_here(self):
        """The twenty from the run that produced this file, none quietly dropped."""
        self.assertEqual(len(ADVERSARY_TWENTY), 20)
        for route in ADVERSARY_TWENTY:
            with self.subTest(route=route):
                self.assertIn(route, ALL_ROUTES)

    def test_at_least_five_routes_were_invented_here(self):
        """The brief asked for five more than the adversary's twenty."""
        invented = [r for r in ALL_ROUTES if r not in ADVERSARY_TWENTY]
        self.assertGreaterEqual(len(invented), 5, invented)

    def test_every_open_route_is_a_real_route_with_a_reason(self):
        for route, mechanism in OPEN_ROUTES.items():
            with self.subTest(route=route):
                self.assertIn(route, ALL_ROUTES)
                self.assertGreater(len(mechanism), 40, mechanism)

    def test_the_number_of_open_routes_is_pinned(self):
        """The count going down has to be a line in a diff, not a lucky green.

        `unittest` already fails a build on an unexpected success, so a route
        that gets closed while its `@open_route` line stays cannot pass. This is
        the other half: the roster's SIZE is written down, so closing a route
        means editing a number a reviewer can see.
        """
        self.assertEqual(
            len(OPEN_ROUTES),
            OPEN_ROUTES_AT_A9245C3,
            "the set of laundering routes that are open has changed. If you "
            "closed one: delete its @open_route line and lower "
            "OPEN_ROUTES_AT_A9245C3 by one, in this diff. If you opened one: "
            "that is the regression this file exists to catch, and the number "
            "goes up only with a reason written next to it. Open now: "
            + ", ".join(sorted(OPEN_ROUTES)),
        )

    def test_the_adversarys_eleven_are_the_open_ones_among_their_twenty(self):
        """`8 of 20` at `bb21645`, `11 of 20` at `a9245c3`. This is the eleven.

        Pinned as a set rather than a count, because "eleven are open" and
        "these eleven are open" are different statements and only the second one
        catches a trade.
        """
        open_among_the_twenty = {r for r in ADVERSARY_TWENTY if r in OPEN_ROUTES}
        self.assertEqual(
            open_among_the_twenty,
            set(),
            "the adversary measured 8 of these 20 laundering at bb21645 and 11 at "
            "a9245c3, and the eleven were listed here by name. All eleven are "
            "shut. This set is empty and it stays empty: an entry appearing in it "
            "is a laundering family being re-opened, which is exactly the trade "
            "this file was written to make visible. If one does re-open, add its "
            "@open_route line and its name here together, with the reason.",
        )


class EveryOpenRouteFailsForTheRightReasonTest(unittest.TestCase):
    """`expectedFailure` swallows everything, including a broken test.

    A route whose scaffolding raises `TypeError` before it ever reaches the
    ledger is recorded as an expected failure exactly like a route that
    laundered - so seventeen expected failures could mean seventeen laundering
    holes or seventeen typing mistakes, and the last line of the suite cannot
    tell you which.

    This re-runs every open route through a fresh `TestResult` and reads the
    traceback: it must be the ledger assertion, and it must name the route. That
    makes each expected failure a POSITIVE CONTROL in its own right - proof that
    the detector fired on a real laundered row - for as long as the route is
    open.
    """

    def test_each_open_route_fails_on_its_ledger_assertion(self):
        methods = {
            name: function
            for name, function in vars(LaunderingRoutesTest).items()
            if getattr(function, "open_route", None)
        }
        self.assertEqual(
            sorted(getattr(f, "open_route") for f in methods.values()),
            sorted(OPEN_ROUTES),
            "an @open_route decoration did not land on a test method",
        )

        for name, function in sorted(methods.items()):
            route = getattr(function, "open_route")
            with self.subTest(route=route):
                result = unittest.TestResult()
                LaunderingRoutesTest(name).run(result)

                self.assertEqual(
                    len(result.expectedFailures),
                    1,
                    f"{route} did not fail at all - it is closed, so delete its "
                    "@open_route line and lower OPEN_ROUTES_AT_A9245C3",
                )
                _, trace = result.expectedFailures[0]
                self.assertIn(
                    "AssertionError",
                    trace,
                    f"{route} raised something other than the ledger assertion, "
                    f"so expectedFailure is hiding a broken test:\n{trace}",
                )
                self.assertIn(
                    route,
                    trace,
                    f"{route} failed somewhere other than assert_not_laundered:"
                    f"\n{trace}",
                )
                self.assertIn(
                    "laundered",
                    trace,
                    f"{route} failed on a different assertion:\n{trace}",
                )


if __name__ == "__main__":
    unittest.main()
