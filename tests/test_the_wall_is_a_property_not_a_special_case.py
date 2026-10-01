"""Two walls that were documented as properties and implemented as special cases.

`tests/test_no_tool_can_mint_a_measurement.py` attacks the four walls with the
attacks that were known when they were built. This file attacks the WALLS
THEMSELVES - not "does the guard fire", but "is the guard the thing the
docstring says it is" - because both defects this file closes were found by
walking one step off the path the original tests walked.

WALL 2 said *a tool cannot hand a caller's number back with a measurement badge
on it*, and refused any value equal, at the same type, to a scalar in the
arguments. Equality is not provenance, and it was wrong twice over:

    int("100")            -> 100        laundered: different type
    argument + 1          -> 100        laundered: different value
    argument * 2          -> 500        laundered: different value
    int(str(a) + str(b))  -> 120        laundered: assembled from two arguments
    int(" 100 ".strip())  -> 100        laundered: different type

and, in the other direction and in front of a real user, `profile_dataset`
counting a 120-row eval file with `max_rows=120` was refused as laundering and
returned HTTP 500, because an honest count equalled an argument. Both are one
mistake: a question about where a value CAME FROM answered by what it EQUALS.
`ElevenTransformationsTest` runs all of them, each through a registered tool
called the way a model calls one. It was eleven when this file was written and a
twelfth - `int(json round trip)` - was listed below as a hole that could not be
closed; it is closed, so it is in the loop, and the class keeps its name rather
than churning every reference to it.

WALL 3 said *a tool that can mint cannot read the claim ledger*, and was
enforced on `assemble_facts`. `rows_for` is exported in `__all__`, reads the
same table, and had no guard: a minting tool read a model's ASSERTED
`eval_size_n = 999999` straight out of the ledger and re-stamped it MEASURED.
`ledger_view` was the same hole a third time. A wall enforced on the functions
somebody remembered is not a wall, so it now stands on the TABLE - and
`TheLedgerHasOneDoorTest` derives this module's public surface from the module
itself and watches the database while it calls every part of it, so a function
written next year cannot escape by being new.

EVERY CLASS HERE HAS A POSITIVE CONTROL, in the same file and next to the
refusal it controls, because each of these tests would pass against code that
refuses everything:

    the transformation attacks   <- `test_the_same_tool_stamps_what_it_read`
    the ledger spy               <- `test_the_watch_sees_an_ordinary_read`
    the nine TRAIN fixtures      <- `TheProductStillMintsTest`, which reports
                                    how many real TRAIN verdicts this file
                                    produced rather than asserting a refusal
"""

from __future__ import annotations

import contextlib
import inspect
import json
import re
import tempfile
import unittest
from pathlib import Path

import diagnosis_fixtures as fixtures

from app import db, diagnosis
from app.providers import Delta, store as provider_store
from app.tools import REGISTRY, evidence, measure
from app.tools.evidence import (
    ASSERTED,
    CallerValue,
    Instrument,
    MEASURED,
    MODEL,
    MeasurementError,
    STATED,
    USER,
)
from app.tools.registry import Registry

import support


THREAD = 1


def eval_file(root: Path, rows: int, labels: int = 5) -> Path:
    """An eval set with a known row count and a known majority class."""
    path = root / f"eval_{rows}.jsonl"
    path.write_text(
        "\n".join(
            json.dumps({"q": f"q{i}", "a": f"label{i % labels}"}) for i in range(rows)
        ),
        encoding="utf-8",
    )
    return path


class ScriptedModel:
    """Right on the first `correct` rows, wrong after. Answers from the question."""

    def __init__(self, correct: int, labels: int = 5) -> None:
        self.correct = correct
        self.labels = labels

    def stream(self, conversation, offered, *, secret=None):
        question = conversation[-1]["content"]
        index = int(str(question).lstrip("q") or 0)
        if index < self.correct:
            yield Delta(kind="text", text=f"label{index % self.labels}")
        else:
            yield Delta(kind="text", text="something else entirely")


# ---------------------------------------------------------------------------
# Wall 2.


#: One laundering attempt each: a schema, the arguments a model would send, and
#: the transformation the tool applies before stamping. The first two are the
#: adversary's, verbatim; the rest were invented for this file. Every one of
#: them produces the same number the model wanted stamped, and none of them is
#: a measurement.
TRANSFORMATIONS: dict[str, tuple[dict, dict, object]] = {}


def _attack(label, properties, arguments, transform):
    TRANSFORMATIONS[label] = (
        {
            "type": "object",
            "properties": properties,
            "required": sorted(properties),
        },
        arguments,
        transform,
    )


_ONE_INT = {"n": {"type": "integer"}}
_ONE_STRING = {"n": {"type": "string"}}
_TWO_INTS = {"a": {"type": "integer"}, "b": {"type": "integer"}}
_ONE_OBJECT = {"report": {"type": "object"}}

# The naive attempt the old check did catch, kept so a fix cannot regress it.
_attack("the argument itself", _ONE_INT, {"n": 500}, lambda n: n)
# The adversary's two, in their own words: int(str_argument) and arg+1.
_attack("int(str_argument)", _ONE_STRING, {"n": "100"}, lambda n: int(n))
_attack("argument + 1", _ONE_INT, {"n": 99}, lambda n: n + 1)
# Five invented here.
_attack("argument * 2", _ONE_INT, {"n": 250}, lambda n: n * 2)
_attack(
    "two arguments spliced as text",
    _TWO_INTS,
    {"a": 1, "b": 20},
    lambda a, b: int(str(a) + str(b)),
)
_attack("int(argument.strip())", _ONE_STRING, {"n": " 100 "}, lambda n: int(n.strip()))
_attack("int(float(argument))", _ONE_INT, {"n": 500}, lambda n: int(float(n)))
_attack("abs(-argument)", _ONE_INT, {"n": 500}, lambda n: abs(-n))
# Three more shapes: summed, formatted, and buried inside a nested argument.
_attack("sum([argument])", _ONE_INT, {"n": 500}, lambda n: sum([n]))
_attack("int(f-string of argument)", _ONE_INT, {"n": 500}, lambda n: int(format(n)))
_attack(
    "buried in a nested object",
    _ONE_OBJECT,
    {"report": {"counts": [500, 12]}},
    lambda report: report["counts"][0],
)


class ElevenTransformationsTest(unittest.TestCase):
    """Wall 2 asks where a value came from. Eleven ways of dressing it up.

    Each attack is a registered tool called through `Registry.call`, because
    that is the only way a value ever reaches a handler in this product and a
    unit test that calls `measured()` directly would not exercise the mark at
    all - the mark is put on by the registry.
    """

    def setUp(self):
        self.root = support.sandbox(self)
        support.a_conversation(THREAD)
        evidence.ensure_table()

    def laundering_registry(self, schema, transform, bounds=()):
        registry = Registry()

        @registry.tool(
            "launder",
            description="Records an eval size the caller already knows.",
            schema=schema,
            measures=("eval_size_n",),
            bounds=bounds,
            provides=("data.eval_set.count",),
            label="Launder",
            group="Test",
            verb="launder a number",
        )
        def launder(*, instrument: Instrument, **arguments):
            instrument.measured(
                "eval_size_n",
                transform(**arguments),
                how="obtained by this tool, honestly, it says",
            )
            return {"ok": True}

        return registry

    def test_every_transformation_is_refused_and_nothing_is_recorded(self):
        for label, (schema, arguments, transform) in TRANSFORMATIONS.items():
            if label in KNOWN_TO_ESCAPE:
                continue
            with self.subTest(transformation=label):
                registry = self.laundering_registry(schema, transform)
                with self.assertRaises(MeasurementError) as caught:
                    registry.call(
                        "launder", dict(arguments), actor=MODEL, thread_id=THREAD
                    )
                self.assertIn("launder", str(caught.exception))
                self.assertEqual(
                    evidence.rows_for(THREAD),
                    [],
                    f"{label} wrote a row into the ledger",
                )

    def test_the_same_tool_stamps_what_it_read(self):
        """THE POSITIVE CONTROL. A wall that refuses everything is not a wall.

        The identical handler, with the identical schema and the identical
        arguments, stamping a number that came off a disk instead of out of the
        arguments. If this fails, every refusal above means nothing, because a
        `measured()` that raised unconditionally would pass all of them.

        ONE THING CHANGED HERE AND IT IS THE POINT OF THE WHOLE MECHANISM, so it
        is written out rather than slipped in. The tool now declares
        `bounds=("n",)`: *n is a bound on the work, it is not the answer*.
        Without that declaration this same honest count is refused, and
        `test_an_honest_count_needs_the_declaration_when_it_equals_an_argument`
        below asserts exactly that.

        That is not a weaker control, it is the true one. Route 10 in
        `tests/test_laundering_routes.py` is a tool that writes `n` lines to a
        file and counts them; this is a tool that counts a file the caller had
        nothing to do with. The values, the types, the schema and the arguments
        are identical in both, and the provenance chain in route 10 runs through
        the operating system, so NOTHING INSIDE THIS PROCESS CAN TELL THEM
        APART. A wall that stamps both is route 10 open; a wall that refuses
        both is the HTTP 500 that made G0 unopenable for a commit. The
        declaration is the third answer: the tool says which of its arguments
        could never be what it measures, at registration, where a reviewer reads
        it - and then the value check can do its job on everything else.
        """
        path = eval_file(self.root, rows=500)
        schema, arguments, _ = TRANSFORMATIONS["the argument itself"]
        counted = len(path.read_text(encoding="utf-8").splitlines())

        registry = self.laundering_registry(
            schema, lambda n: counted, bounds=("n",)
        )
        result = registry.call("launder", dict(arguments), actor=MODEL,
                               thread_id=THREAD)
        self.assertTrue(result["ok"])
        self.assertEqual(
            [(row["fact"], row["value"], row["origin"])
             for row in evidence.rows_for(THREAD)],
            [("eval_size_n", 500, MEASURED)],
        )
        # And the number it stamped is the same number the attack wanted
        # stamped. The wall told them apart on the declaration and nothing else,
        # because there is nothing else left to tell them apart by.
        self.assertEqual(counted, arguments["n"])

    def test_an_honest_count_needs_the_declaration_when_it_equals_an_argument(self):
        """The cost of closing route 10, stated rather than left to be found.

        The same handler and the same file as the control above, with the
        declaration taken away. The count is honest, and it is refused, because
        an undeclared integer argument equal to the count is indistinguishable
        from the laundered version of itself.

        This is the one false refusal the new wall can produce, it is confined
        to a tool that takes a number it does not declare, and the refusal says
        what to do about it. Every tool that ships is clear of it: only
        `profile_dataset` has a numeric argument at all, and it declares
        `bounds=("max_rows",)`.
        """
        path = eval_file(self.root, rows=500)
        schema, arguments, _ = TRANSFORMATIONS["the argument itself"]
        counted = len(path.read_text(encoding="utf-8").splitlines())

        registry = self.laundering_registry(schema, lambda n: counted)
        with self.assertRaises(MeasurementError) as caught:
            registry.call("launder", dict(arguments), actor=MODEL,
                          thread_id=THREAD)
        self.assertIn("bounds=", str(caught.exception))
        self.assertEqual(evidence.rows_for(THREAD), [])


#: The transformations that are NOT caught. EMPTY NOW, AND IT WAS NOT.
#:
#: `int(json round trip)` was in here, with a test below asserting the hole, on
#: the reasoning that an identity-preserving rebuild produces the same number of
#: the same type an honest reading would produce - so no check on the VALUE can
#: tell them apart, and the check that used to try is what returned HTTP 500 to
#: a user counting a 120-row file with a cap of 120.
#:
#: The reasoning was right and the conclusion was wrong. No check on the value
#: can tell them apart, so the thing that tells them apart is not a check on the
#: value: it is a DECLARATION on the tool. `bounds=` names the arguments that
#: cannot be the answer - `max_rows` bounds the work - and every other argument
#: is quarantined by value. That is wall 6 in `app/tools/registry.py`, and it is
#: what let the value check come back without the false refusal that killed it.
KNOWN_TO_ESCAPE: frozenset[str] = frozenset()

_attack(
    "int(json round trip)",
    _ONE_INT,
    {"n": 500},
    lambda n: json.loads(json.dumps(n)),
)


class TheHoleIsNamedRatherThanHiddenTest(unittest.TestCase):
    """What gets through, asserted, so nobody has to take the docstring's word.

    A test suite that only demonstrates its successes is how a partial guard
    comes to read as a complete one - which is the exact criticism that produced
    this whole change. This class named one hole and asserted it.

    THAT HOLE IS SHUT. `test_a_json_round_trip_still_gets_through` lived here
    and did what its own failure message told the next person to do: it went red
    when somebody closed it, and it has been deleted rather than weakened. The
    round trip is now one of twenty-nine routes in
    `tests/test_laundering_routes.py`, refused by the value quarantine in
    `Instrument.measured` - see `KNOWN_TO_ESCAPE` above for why the reasoning
    that said it could not be closed was half right.

    What is left here is the check that protects the product from the shape of
    tool that would reach any remaining hole: no tool that ships passes an
    argument into `measured()`. `app/tools/evidence.py` states what the wall
    still cannot catch under WHAT THIS DOES NOT CATCH, and the honest way to
    assert one of those is to add a route to the file that counts them.
    """

    def setUp(self):
        self.root = support.sandbox(self)
        support.a_conversation(THREAD)
        evidence.ensure_table()

    def test_no_tool_that_ships_converts_an_argument_into_a_measurement(self):
        """The hole above is only reachable by writing a tool that does it.

        So this asserts the thing that actually protects the product today: no
        registered tool passes a caller's argument into `measured()` at all. It
        reads the handlers' source, which is crude and is the point - the check
        is meant to notice a NEW tool written the careless way, and a new tool
        is exactly what source text catches and a runtime test does not.
        """
        for tool in REGISTRY:
            if not tool.measures:
                continue
            with self.subTest(tool=tool.name):
                source = inspect.getsource(tool.handler)
                stamps = re.findall(
                    r"measured\(\s*[\"'](\w+)[\"']\s*,\s*([^,]+),", source
                )
                self.assertTrue(
                    stamps,
                    f"{tool.name} declares measures={list(tool.measures)} and this "
                    "check could not find its stamps. If the call was reshaped, "
                    "reshape this pattern with it rather than deleting it.",
                )
                arguments = set(tool.schema.get("properties") or {})
                for fact, expression in stamps:
                    bare = expression.strip().strip("()")
                    self.assertNotIn(
                        bare,
                        arguments,
                        f"{tool.name} stamps {fact} straight from its argument "
                        f"{bare!r}",
                    )


class AnHonestCountThatEqualsAnArgumentIsStillACountTest(unittest.TestCase):
    """The other direction of the same defect, which was live and user-facing.

    `tests/test_an_honest_count_is_not_laundering.py` covers the reported
    reproduction and the route. This covers the property the new mechanism is
    supposed to have and the old one could not: equality with an argument is not
    evidence of anything, at any row count, through any of the tools that count.
    """

    def setUp(self):
        self.root = support.sandbox(self)
        support.a_conversation(THREAD)
        evidence.ensure_table()

    def test_the_cap_equal_to_the_count_records_the_count(self):
        for rows in (50, 120, 31):
            with self.subTest(rows=rows):
                support.db.DB_PATH  # the sandbox's database, one per test
                path = eval_file(self.root, rows=rows)
                result = REGISTRY.call(
                    "profile_dataset",
                    {"path": str(path), "split": "eval", "max_rows": rows},
                    actor=MODEL,
                    thread_id=THREAD,
                )
                self.assertEqual(result["rows"], rows)
                self.assertEqual(result["measured_facts"][0]["value"], rows)

    def test_a_count_equal_to_any_other_argument_is_also_still_a_count(self):
        """Not only the cap. Nothing in the arguments is compared to the count.

        A path with the row count in its name, a split spelled as the number,
        and a cap one higher - the count still gets stamped, because the wall no
        longer asks what the number equals.
        """
        path = eval_file(self.root, rows=64)
        renamed = self.root / "64.jsonl"
        path.replace(renamed)
        result = REGISTRY.call(
            "profile_dataset",
            {"path": str(renamed), "split": "eval", "max_rows": 64},
            actor=USER,
            thread_id=THREAD,
        )
        self.assertEqual(result["measured_facts"][0]["value"], 64)

    def test_measure_eval_set_counts_a_file_named_after_its_own_size(self):
        """The other counting tool, whose only argument is a path."""
        path = self.root / "120.jsonl"
        path.write_text(
            "\n".join(json.dumps({"a": i}) for i in range(120)), encoding="utf-8"
        )
        result = REGISTRY.call(
            "measure_eval_set", {"path": str(path)}, actor=USER, thread_id=THREAD
        )
        self.assertEqual(result["rows"], 120)
        self.assertEqual(result["measured_facts"][0]["value"], 120)


class TheMarkIsCarriedByConstructionTest(unittest.TestCase):
    """The mechanism itself, at the level a reviewer has to be able to check.

    The classes above prove the behaviour through the product. These prove the
    thing the behaviour rests on, so a failure points at the mechanism rather
    than at whichever tool happened to be in the test.
    """

    def setUp(self):
        self.root = support.sandbox(self)
        support.a_conversation(THREAD)
        evidence.ensure_table()

    def test_the_caller_s_numbers_are_marked_and_the_rest_are_not(self):
        marked = evidence.mark_caller_values(
            {"n": 5, "score": 0.5, "path": "/tmp/x", "flag": True, "nothing": None}
        )
        self.assertIsInstance(marked["n"], CallerValue)
        self.assertIsInstance(marked["score"], CallerValue)
        self.assertNotIsInstance(marked["path"], CallerValue)
        self.assertIs(marked["flag"], True)
        self.assertIsNone(marked["nothing"])

    def test_a_marked_number_is_still_the_number(self):
        n = evidence.mark_caller_values(120)
        self.assertEqual(n, 120)
        self.assertEqual([0, 1, 2][evidence.mark_caller_values(1)], 1)
        self.assertEqual(json.loads(json.dumps({"n": n})), {"n": 120})
        self.assertEqual(f"{n:,}", "120")

    def test_the_mark_survives_every_operation_a_launderer_would_reach_for(self):
        n = evidence.mark_caller_values(100)
        for label, derived in {
            "+": n + 1,
            "*": n * 2,
            "-": n - 1,
            "//": n // 2,
            "unary": -n,
            "abs": abs(n),
            "sum": sum([n]),
            "max": max(n, 3),
            "str": str(n),
            "format": format(n),
            "str then splice": str(n) + "0",
            "in a list": [n][0],
            "divmod": divmod(n, 3)[0],
        }.items():
            with self.subTest(operation=label):
                self.assertTrue(
                    evidence.is_caller_value(derived),
                    f"{label} produced an unmarked {derived!r}",
                )

    def test_a_marked_string_never_reaches_pathlib(self):
        """Why a caller's strings are compared instead of marked.

        `pathlib` interns path components and `sys.intern` refuses a `str`
        subclass, so marking a caller's path breaks every tool that opens a
        file. This asserts the decision that came out of that: the argument
        marker leaves strings alone, and `Path` still works on one.
        """
        marked = evidence.mark_caller_values(str(self.root))
        self.assertNotIsInstance(marked, CallerValue)
        self.assertTrue(Path(marked).exists())
        with self.assertRaises(TypeError):
            Path(evidence.CallerStr(str(self.root)))

    def test_a_conversion_is_remembered_because_it_cannot_be_marked(self):
        """CPython normalises `__int__`, so the mark cannot cross a conversion.

        The wrappers therefore hand back a plain number and remember it. This
        pins both halves: the conversion result is NOT marked, and the
        instrument knows about it anyway.
        """
        instrument = evidence.instrument_for(
            tool="probe", measures=("eval_size_n",), thread_id=THREAD,
            provides=("data.eval_set.count",),
            arguments={"n": "100"},
        )
        token = evidence._MINTING.set(instrument)
        try:
            converted = int(evidence.CallerStr("100"))
        finally:
            evidence._MINTING.reset(token)
        self.assertNotIsInstance(converted, CallerValue)
        self.assertIn(100, instrument.converted)

    def test_an_identity_conversion_is_not_remembered(self):
        """`int(x)` on a caller's int says nothing, and remembering it was the bug.

        `_bounded(max_rows)` in `profile_dataset` is this exact call. If an
        identity conversion were remembered, counting a 120-row file with a cap
        of 120 would be refused again, which is the defect this change exists
        to end.

        THE INSTRUMENT IS BUILT WITH `bounds=("max_rows",)` AND IT HAS TO BE.
        The identity-conversion rule alone stopped being enough to let this
        count through the day the value quarantine came back: `120` is in the
        arguments, and `Instrument.measured` refuses a value strictly equal to
        one unless the tool declared that argument cannot be the answer. This
        is what `Registry.call` passes for the real `profile_dataset`, which
        declares it. The property the old version of this test protected -
        counting a 120-row file with a cap of 120 records 120 - is asserted
        three times over through the real tools in
        `AnHonestCountThatEqualsAnArgumentIsStillACountTest`; what moved is the
        mechanism underneath it, so this moved with it.
        """
        instrument = evidence.instrument_for(
            tool="probe", measures=("eval_size_n",), thread_id=THREAD,
            provides=("data.eval_set.count",),
            arguments={"max_rows": 120}, bounds=("max_rows",),
        )
        token = evidence._MINTING.set(instrument)
        try:
            self.assertEqual(int(instrument.caller_arguments["max_rows"]), 120)
        finally:
            evidence._MINTING.reset(token)
        self.assertEqual(instrument.converted, [])
        instrument.measured("eval_size_n", 120, how="counted 120 rows")
        self.assertEqual(
            [row["value"] for row in evidence.rows_for(THREAD)], [120]
        )

    def test_a_declared_bound_is_still_marked_so_it_cannot_be_stamped_itself(self):
        """A bound is out of the quarantine and it is not out of the wall.

        `bounds=` exempts an argument from the comparison by VALUE and from
        nothing else. The argument still arrives marked, so a tool that hands
        its own cap back as a measurement is refused exactly as before - and so
        is anything derived from it. Without this, the declaration would be a
        way to turn wall 2 off one argument at a time.
        """
        instrument = evidence.instrument_for(
            tool="probe", measures=("eval_size_n",), thread_id=THREAD,
            provides=("data.eval_set.count",),
            arguments={"max_rows": 120}, bounds=("max_rows",),
        )
        cap = instrument.caller_arguments["max_rows"]
        self.assertIsInstance(cap, CallerValue)
        for label, value in {"the bound": cap, "derived from it": cap * 2}.items():
            with self.subTest(stamping=label):
                with self.assertRaises(MeasurementError):
                    instrument.measured("eval_size_n", value, how="counted it")
        self.assertEqual(evidence.rows_for(THREAD), [])

    def test_a_measured_row_cannot_be_written_round_the_instrument(self):
        """`record()` is exported and takes an origin. Wall 2 lives one door up.

        Without this, every check in `measured()` is optional for anyone who
        calls the other function - which is the same shape as the wall-3 defect
        below, where the guard was on one of two doors into the same table.
        """
        with self.assertRaises(MeasurementError) as caught:
            evidence.record(
                fact="eval_size_n",
                value=999_999,
                origin=MEASURED,
                actor=MODEL,
                how="straight into the table",
                thread_id=THREAD,
            )
        self.assertIn("Instrument.measured", str(caught.exception))
        self.assertEqual(evidence.rows_for(THREAD), [])
        # STATED and ASSERTED rows still go through it, because those are what
        # `supplied()` writes and they claim nothing.
        evidence.record(
            fact="eval_size_n", value=999_999, origin=ASSERTED, actor=MODEL,
            how="the model said so", thread_id=THREAD,
        )
        self.assertEqual(
            [row["origin"] for row in evidence.rows_for(THREAD)], [ASSERTED]
        )


# ---------------------------------------------------------------------------
# Wall 3.


class LedgerWatch:
    """Every statement this connection runs, and which of them read the ledger."""

    def __init__(self, connection):
        self._connection = connection
        self.statements: list[str] = []

    def execute(self, sql, *args, **kwargs):
        self.statements.append(str(sql))
        return self._connection.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._connection, name)

    @property
    def reads_of_the_ledger(self) -> list[str]:
        return [
            statement
            for statement in self.statements
            if re.search(r"SELECT.*FROM\s+fact_evidence", statement,
                         re.IGNORECASE | re.DOTALL)
        ]


@contextlib.contextmanager
def watching_the_ledger():
    """Wrap `db.session` so a test can see every statement `evidence` runs."""
    original = db.session
    watches: list[LedgerWatch] = []

    @contextlib.contextmanager
    def session():
        with original() as connection:
            watch = LedgerWatch(connection)
            watches.append(watch)
            yield watch

    db.session = session
    try:
        yield watches
    finally:
        db.session = original


def reads_of_the_ledger(watches) -> list[str]:
    return [statement for watch in watches for statement in watch.reads_of_the_ledger]


#: One plausible value per parameter name in this module's public surface. A
#: function whose parameter is not named here fails the derived-surface test
#: rather than being skipped, so tomorrow's function cannot escape by taking an
#: argument nobody thought of.
def _a_clean_file() -> str:
    """A two-row file with nothing generated in it, written once for this module.

    In a temporary directory rather than the sandbox, because SAMPLE_ARGUMENTS
    is built at import and the sandbox is per-test. Nothing writes to it.
    """
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".jsonl", delete=False, encoding="utf-8"
    )
    with handle:
        handle.write('{"input": "one", "expected": "yes"}\n')
        handle.write('{"input": "two", "expected": "no"}\n')
    return handle.name


SAMPLE_ARGUMENTS: dict[str, object] = {
    "actor": MODEL,
    "arguments": {"n": 1},
    "bounds": (),
    "collect": False,
    "depth": 0,
    "fact": "eval_size_n",
    # WALL 8's argument, and it is a REAL FILE rather than None on purpose. None
    # is the default and would skip the check entirely, so this test would say
    # nothing about the one code path added to `measured` since it was written.
    # A clean file exercises `_refuse_generated_rows` all the way through - it
    # reads rows off a disk, and the property being asserted here is that
    # nothing in this module touches the CLAIM ledger while a tool can mint.
    "from_file": _a_clean_file(),
    "holds": "the fact ledger",
    "how": "for this test",
    # `nearest_facts` and `fact_name_help` - the door in the refusal. Both read
    # the fact LEDGER in the `docs/diagnosis_engine.yaml` sense and neither may
    # read the claim ledger in the `fact_evidence` sense, which is exactly what
    # this test is here to establish about them.
    "limit": 3,
    "marks": {},
    "measures": ("eval_size_n",),
    "name": "eval_size_n",
    "names": ("eval_size_n", "answer_given"),
    "origin": ASSERTED,
    "owner": None,
    # WALL 9's argument. The capability whose tool may read `eval_size_n`, so
    # the sweep calls `the_right_instrument` and `wrong_instrument_reason` with
    # the honest shape rather than with something that trivially refuses - and
    # `instrument_for` builds the licence the registry would actually issue.
    "provides": ("data.eval_set.count",),
    # What a refusal says the caller was trying to do - "stamp MEASURED",
    # "declare measures=". Message-only, and both wall 7's and wall 9's
    # refusal composers take it.
    "doing": "stamp MEASURED",
    "quantities": None,
    "reader": "rows_for",
    # `quarantine_rows` - the move a walk makes when the file on record
    # contradicts a stated modality. A real-shaped row, so a mover that did not
    # refuse would act on it; it must refuse before it does.
    "rows": [{"id": 1, "thread_id": THREAD, "fact": "eval_size_n", "value": 1,
              "origin": ASSERTED, "actor": MODEL, "tool": None, "how": "for this test",
              "created_at": "2026-09-23 00:00:00"}],
    "because": "for this test",
    # `assemble_facts(persist=)`. True, the writing walk, because it is the
    # stricter case: a walk allowed to move rows must still refuse to read the
    # ledger while a tool can mint.
    "persist": True,
    # WHICH LEDGER THIS QUESTION IS ABOUT. Threaded through this module by the
    # per-thread ledger handle, and it is the fact LEDGER in the
    # `docs/diagnosis_engine.yaml` sense - the declarations - never the claim
    # ledger in the `fact_evidence` sense, which is the whole distinction wall 3
    # is about. Supplying the real spec rather than None is the stricter of the
    # two: a function handed a `Spec` and reaching for `fact_evidence` anyway is
    # exactly what this test exists to catch.
    "ledger": diagnosis.default_spec(),
    # Wall 5. `facts_at_scope` asks the ledger which facts are declared at one
    # scope; `machine` is the interesting one, because it is the answer to "what
    # may be written with no conversation at all".
    "scope": "machine",
    "supplied": None,
    "text": "100",
    "thread_id": THREAD,
    "tool": "probe",
    "value": 7,
}


def public_surface():
    """Every public callable this module offers, derived from the module.

    Not a list. `__all__` is a list, and the wall-3 defect was a function that
    was in `__all__` and had no guard - so this walks `vars(evidence)` instead,
    which is a superset, and it walks the public methods of the classes defined
    here as well. `CallerValue` subclasses are left out because they are numbers
    and strings: they hold no connection and cannot reach a database, and
    `TheLedgerHasOneDoorTest.test_only_one_statement_in_the_module_reads_the
    _ledger` covers them anyway by reading the source.
    """
    for name, value in sorted(vars(evidence).items()):
        if name.startswith("_"):
            continue
        if inspect.isfunction(value) and value.__module__ == evidence.__name__:
            yield name, value
        elif inspect.isclass(value) and value.__module__ == evidence.__name__:
            if issubclass(value, CallerValue):
                continue
            for attribute, member in sorted(vars(value).items()):
                if attribute.startswith("_") or not inspect.isfunction(member):
                    continue
                yield f"{name}.{attribute}", member


class TheLedgerHasOneDoorTest(unittest.TestCase):
    """Wall 3 stands on the table, so every reader meets it without being told.

    The old guard was at the top of `assemble_facts`. `rows_for` read the same
    rows, was exported, and had none - and a minting tool that called it got a
    model's ASSERTED 999999 back and re-stamped it MEASURED. `ledger_view` was
    the same hole again. Guarding those two by name would have been the same
    mistake a third time, so this asserts the property instead.
    """

    def setUp(self):
        self.root = support.sandbox(self)
        support.a_conversation(THREAD)
        evidence.ensure_table()
        REGISTRY.call(
            "state_facts",
            {"facts": {"eval_size_n": 999_999}},
            actor=MODEL,
            thread_id=THREAD,
        )

    def minting_tool(self, name, body):
        registry = Registry()

        @registry.tool(
            name,
            description="Reads the ledger and stamps what it finds there.",
            schema={"type": "object", "properties": {}},
            measures=("eval_size_n",),
            provides=("data.eval_set.count",),
            label="Restamp",
            group="Test",
            verb="restamp a claim",
        )
        def handler(*, instrument: Instrument):
            body(instrument)
            return {"ok": True}

        return registry

    def test_the_two_step_laundering_is_refused_at_every_reader(self):
        readers = {
            "rows_for": lambda i: evidence.rows_for(i.thread_id),
            "ledger_view": lambda i: evidence.ledger_view(i.thread_id),
            "assemble_facts": lambda i: evidence.assemble_facts(i.thread_id),
        }
        for label, read in readers.items():
            with self.subTest(reader=label):
                def body(instrument, read=read):
                    for row in read(instrument):
                        instrument.measured(
                            "eval_size_n", row, how="it was in the ledger"
                        )

                registry = self.minting_tool("restamp", body)
                with self.assertRaises(MeasurementError) as caught:
                    registry.call("restamp", {}, actor=MODEL, thread_id=THREAD)
                message = str(caught.exception)
                self.assertIn("laundering", message)
                # The message names the function that walked into the door.
                # `ledger_view` and `assemble_facts` both read through
                # `rows_for`, so the door names that rather than inventing a
                # chain: there is one door and it says who knocked.
                self.assertRegex(
                    message,
                    r"asked to read the fact ledger through "
                    r"(rows_for|ledger_view|assemble_facts)\(\)",
                )

        self.assertEqual(
            [row["origin"] for row in evidence.rows_for(THREAD)],
            [ASSERTED],
            "a measured row was written by a tool that only read one",
        )

    def test_the_claim_never_becomes_a_measurement_for_the_engine(self):
        """The consequence, one layer up, which is what a user would see."""
        sheet, _ = evidence.assemble_facts(THREAD)
        self.assertEqual(diagnosis.bare(sheet["eval_size_n"]), 999_999)
        self.assertEqual(sheet["eval_size_n"].origin, ASSERTED)

    def test_the_watch_sees_an_ordinary_read(self):
        """THE POSITIVE CONTROL for the spy the property test below depends on.

        A watch that saw nothing would make that test pass against a module
        that reads the ledger on every line.
        """
        with watching_the_ledger() as watches:
            evidence.rows_for(THREAD)
        self.assertTrue(
            reads_of_the_ledger(watches),
            "the watch did not see rows_for read the ledger",
        )

    def test_no_part_of_this_module_reads_the_ledger_while_a_tool_can_mint(self):
        """The property, over the whole public surface, derived from the module.

        Every public callable is invoked with a minting instrument open, and the
        database is watched. Each one must either refuse - the wall firing - or
        never touch the claim ledger at all. A function added next year is
        included by existing.
        """
        instrument = evidence.instrument_for(
            tool="attacker", measures=("eval_size_n",), thread_id=THREAD,
            provides=("data.eval_set.count",),
            arguments={"n": 1},
        )
        surface = dict(public_surface())
        self.assertGreaterEqual(len(surface), 10, surface)

        refused: set[str] = set()
        for label, function in surface.items():
            with self.subTest(callable=label):
                signature = inspect.signature(function)
                arguments = {}
                for parameter in signature.parameters.values():
                    if parameter.name == "self":
                        arguments["self"] = instrument
                        continue
                    if parameter.kind in (
                        parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD
                    ):
                        continue
                    self.assertIn(
                        parameter.name,
                        SAMPLE_ARGUMENTS,
                        f"{label} takes {parameter.name!r} and this test has no "
                        "sample value for it. Add one to SAMPLE_ARGUMENTS - a "
                        "callable nobody can call is a callable nobody checks.",
                    )
                    arguments[parameter.name] = SAMPLE_ARGUMENTS[parameter.name]

                token = evidence._MINTING.set(instrument)
                try:
                    with watching_the_ledger() as watches:
                        try:
                            outcome = function(**arguments)
                            if inspect.isgenerator(outcome):
                                list(outcome)
                        except MeasurementError:
                            refused.add(label)
                finally:
                    evidence._MINTING.reset(token)

                self.assertEqual(
                    reads_of_the_ledger(watches),
                    [],
                    f"{label} read the claim ledger while a tool could mint",
                )

        self.assertLessEqual(
            {"assemble_facts", "ledger_view", "rows_for"},
            refused,
            "the three known readers did not refuse, so this test proved "
            "nothing about the ones it does not know",
        )

    def test_only_one_statement_in_the_module_reads_the_ledger(self):
        """And it is the guarded one. This is what makes the walk above total.

        The runtime walk covers what it can call. A new function that writes its
        own SELECT and is never called by the walk would slip past it; this
        reads the source and refuses a second door outright.
        """
        source = inspect.getsource(evidence)
        statements = re.findall(
            r"SELECT[^\n]*FROM\s+fact_evidence", source, re.IGNORECASE
        )
        self.assertEqual(
            len(statements),
            1,
            f"there is more than one way into the claim ledger: {statements}",
        )
        self.assertIn(statements[0], inspect.getsource(evidence._ledger_rows))

    def test_reading_the_ledger_still_works_when_nothing_can_mint(self):
        """THE POSITIVE CONTROL for the wall: the ledger is not simply closed."""
        rows = evidence.rows_for(THREAD)
        self.assertEqual([row["value"] for row in rows], [999_999])
        self.assertEqual(len(evidence.ledger_view(THREAD)), 1)


# ---------------------------------------------------------------------------
# Non-vacuity for the whole change.


class TheProductStillMintsTest(unittest.TestCase):
    """Nine TRAIN fixtures, walked through the honest path, and counted.

    A change to the measurement wall that produced zero TRAIN verdicts would
    have measured nothing - it would only prove the harness can say no, which it
    could already do by being broken. So every `TRAIN__` fixture in
    `tests/diagnosis_fixtures.py` is run against a REAL counted eval set and a
    REAL scored baseline, and the count of TRAIN verdicts is asserted to be all
    nine of them.
    """

    def setUp(self):
        self.root = support.sandbox(self)
        support.a_conversation(THREAD)
        self.spec = diagnosis.default_spec()
        evidence.ensure_table()

        # 100 rows over five equal classes, so the trivial baseline is exactly
        # 0.20; the scripted model is right on 55 of them, so the baseline is
        # exactly 0.55. Both are the numbers every TRAIN fixture carries, and
        # both are arithmetic over a file this test wrote.
        self.path = eval_file(self.root, rows=100, labels=5)
        row = provider_store.create(
            "Scripted", "http://127.0.0.1:11434", "scripted", "ollama"
        )
        provider_store.set_active(row["id"])
        # Each fixture carries its own baseline, and the measured one has to
        # be that number or the engine is reasoning about a different story:
        # the distillation fixture is a model that already scores 0.91 and
        # costs too much, and measuring 0.55 for it would - correctly - route
        # to "work out why it is wrong" instead.
        self.correct = 55
        original = measure.build
        measure.build = lambda *a, **k: ScriptedModel(correct=self.correct)
        self.addCleanup(lambda: setattr(measure, "build", original))

    def measure_into(self, thread: int, baseline: float) -> None:
        """Count the eval set and score the baseline, in one conversation.

        One thread per fixture, because a fact is scoped to a conversation and
        nine fact sheets in one thread would let the fifth story's answers
        supersede the sixth's. That is the ledger working as designed and it
        would make this test measure the wrong thing.

        The cap is set to exactly the row count on purpose: this is the case
        that used to return HTTP 500, and every one of the nine verdicts below
        now stands on a count taken that way.
        """
        self.correct = round(baseline * 100)
        counted = REGISTRY.call(
            "profile_dataset",
            {"path": str(self.path), "split": "eval", "max_rows": 100},
            actor=USER,
            thread_id=thread,
        )
        self.assertEqual(counted["measured_facts"][0]["value"], 100)
        scored = REGISTRY.call(
            "measure_baseline",
            {
                "eval_path": str(self.path),
                "input_field": "q",
                "expected_field": "a",
                "sample": 100,
            },
            actor=USER,
            thread_id=thread,
        )
        self.assertTrue(scored["ok"], scored.get("summary"))
        # Arithmetic over a file this test wrote: `correct` of 100 rows right,
        # and five equal classes, so the trivial baseline is one in five.
        self.assertEqual(scored["baseline_score"], baseline)
        self.assertEqual(scored["trivial_baseline_score"], 0.20)

    def test_all_nine_train_fixtures_still_mint(self):
        minted = []
        for index, (outcome, facts) in enumerate(sorted(fixtures.MINTING.items())):
            thread = THREAD + index
            support.a_conversation(thread)
            with self.subTest(outcome=outcome):
                sheet = {
                    name: diagnosis.bare(value) for name, value in facts.items()
                }
                self.measure_into(thread, sheet["baseline_score"])
                asked = {
                    name: value
                    for name, value in sheet.items()
                    if self.spec.facts[name]["source"] == "ask"
                }
                REGISTRY.call(
                    "state_facts", {"facts": asked}, actor=USER, thread_id=thread
                )
                result = REGISTRY.call(
                    "run_diagnosis", {"facts": sheet}, actor=MODEL, thread_id=thread
                )
                self.assertEqual(
                    result["outcome"], outcome, result.get("say")
                )
                for gate, entry in result["gate_ledger"].items():
                    self.assertEqual(entry["status"], "PASSED", gate)
                self.assertEqual(result["fact_origins"]["eval_size_n"], MEASURED)
                self.assertEqual(
                    result["fact_origins"]["baseline_score"], MEASURED
                )
                for name in asked:
                    self.assertEqual(result["fact_origins"][name], STATED)
                minted.append(outcome)

        self.assertEqual(
            len(minted),
            9,
            f"this run produced {len(minted)} TRAIN verdicts: {minted}",
        )


if __name__ == "__main__":
    unittest.main()
