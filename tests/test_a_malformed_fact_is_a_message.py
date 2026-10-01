"""A fact the ledger cannot read is a sentence, never a stack trace.

THE DEFECT, EXACTLY.

`app/diagnosis.py`, in `_coerce`, one line inside the `multi:` branch:

    items = [value] if isinstance(value, str) else list(value)

`diagnose({"need_type": 5})` raised `TypeError: 'int' object is not iterable`.
`TypeError` is not a `FactError`, so `run_diagnosis`'s handlers missed it, the
`/api/tools/{name}` route's handlers missed it, and it left the ASGI app as an
unhandled 500 with a traceback. A 200,000-draw fuzz found 763 crashes and every
single one of them was that one signature.

One line away, in the branch for a `map` fact, the same malformed input already
produced a proper `FactError` with a sentence in it. The two branches disagreed
about what a bad value IS, and the product promise - an honest answer, not a
stack trace - was decided by which kind of fact the caller happened to mistype.

WHAT THIS FILE IS FOR, IN THREE LAYERS, because fixing the one line would not
have been enough and this file is the argument that it was not.

  1. THE TWO SIGNATURES. The reported one, and the one the sweep found next to
     it: `failure_histogram` is declared `map[failure_mode,int]` and NOTHING WAS
     CHECKING THE VALUES, so `{"wrong_style": "lots"}` passed
     `isinstance(value, Mapping)` and raised
     `TypeError: unsupported operand type(s) for +: 'int' and 'str'` from inside
     `_fn_sum`, two stages later, in the arithmetic S1 routes on.

  2. THE CLASS, SWEPT. A type-hostile fuzz over the nine real TRAIN fixtures,
     asserting that the only exceptions the engine raises are its own. The
     existing fuzz in tests/test_diagnosis_no_crash.py draws every value from
     the fact's own declared shape - it is a test of the engine's LOGIC over
     well-typed facts, and it could never have found either of these, because it
     never sends a shape the ledger does not describe. This one only sends those.

  3. THE BOUNDARY. `run_diagnosis` and `POST /api/tools/{name}` must both be
     unable to leak an unhandled exception, whatever a tool does. The causes are
     fixed in `_coerce`, where they belong and where the message can name the
     fact; these are the nets, and they are here because the causes have been
     wrong twice in one release.

WHY THE FUZZ REPORTS ITS TRAIN COUNT. A fuzz that produces zero TRAIN verdicts
has measured nothing: it would be sweeping the shallow refusals at the top of
the tree and never reaching the arithmetic. This project has been bitten twice
by a vacuous pass, so the count is asserted and printed rather than assumed, and
so is the requirement that every one of the nine minting outcomes was reached.
"""

from __future__ import annotations

import random
import sys
import traceback
import unittest
from collections import Counter

from app import diagnosis
from app.diagnosis import EngineError, FactError, Fact, SpecError, default_spec, diagnose
from app.tools import REGISTRY
from app.tools.evidence import MODEL

from diagnosis_fixtures import MINTING
import support


# Fixed, so a failure is reproducible and a green run today is a green run
# tomorrow. Changing it is changing the test.
SEED = 20260819

#: Draws over the nine minting fixtures. Large enough that the two known
#: signatures appear thousands of times when the fix is reverted - 60,000 draws
#: produced 571 of the `multi` crash and 19 of the mapping one - and small
#: enough to run inside a suite somebody actually waits for.
DRAWS = 60_000

#: How many facts each draw corrupts. More than one, because the crash that was
#: reported needed only one and the one beside it was found by a draw that had
#: already knocked out something else.
MUTATIONS_PER_DRAW = (1, 3)

#: Values no fact in the ledger declares. Nothing here is a plausible answer to
#: anything - that is the point. They are the shapes a form, a model or a
#: careless caller actually sends: a bare number where a list was wanted, a
#: string where a number was wanted, an empty container, a nested one, a
#: mapping whose values are the wrong type.
HOSTILE: tuple[object, ...] = (
    5,
    -1,
    0,
    1.5,
    True,
    False,
    "",
    "x",
    "5",
    [],
    {},
    [1, 2],
    [None],
    [[]],
    [{}],
    {"a": 1},
    {"a": "b"},
    {"wrong_style": "many"},
    {"nope": 1},
    {None: 1},
    ["wrong_style"],
    set(),
    (1, 2),
    range(3),
    object(),
    b"bytes",
    10**30,
    -(10**30),
    float("nan"),
    float("inf"),
)


class TheTwoSignaturesTest(unittest.TestCase):
    """Each one named, reproduced as reported, and asserted as a `FactError`."""

    @classmethod
    def setUpClass(cls):
        cls.spec = default_spec()

    def test_a_non_iterable_multi_fact_is_a_fact_error_not_a_type_error(self):
        """The reported crash. `facts={'need_type': 5}` did it."""
        with self.assertRaises(FactError) as caught:
            diagnose({"need_type": 5}, self.spec)
        message = str(caught.exception)
        self.assertIn("need_type", message)
        # The message has to carry the answer, not only the complaint.
        for member in self.spec.facts["need_type"]["multi"]:
            self.assertIn(member, message)

    def test_the_sibling_map_fact_still_answers_the_same_way(self):
        """One line away, and it was already right. It stays right."""
        with self.assertRaises(FactError) as caught:
            diagnose({"failure_histogram": 5}, self.spec)
        self.assertIn("must be a mapping", str(caught.exception))

    def test_a_single_member_is_still_accepted_on_its_own(self):
        """The fix must not have narrowed the shapes that were always valid.

        A form with one box ticked sends `"style"`, not `["style"]`. Refusing
        that would trade a crash for a wrong refusal, which is not a fix.
        """
        member = self.spec.facts["need_type"]["multi"][0]
        values, _ = diagnosis.resolve_facts({"need_type": member}, self.spec)
        self.assertEqual(values["need_type"], [member])
        values, _ = diagnosis.resolve_facts({"need_type": [member]}, self.spec)
        self.assertEqual(values["need_type"], [member])

    def test_a_mapping_is_not_a_list_of_its_own_keys(self):
        """`list({"style": 1})` is `["style"]`, and that is not an answer.

        Accepting a mapping here would have read the keys as the value and
        thrown the numbers away without saying so, which is the silent half of
        the same defect.
        """
        with self.assertRaises(FactError):
            diagnose({"need_type": {"knowledge": 1}}, self.spec)

    def test_a_map_facts_values_are_checked_against_its_declared_type(self):
        """The signature the sweep found beside the reported one.

        `failure_histogram` is `map[failure_mode,int]`. A string in it used to
        reach `sum()` two stages later and raise from inside the arithmetic S1
        routes on, with nothing in the message about which fact was wrong.
        """
        with self.assertRaises(FactError) as caught:
            diagnose({"failure_histogram": {"wrong_style": "lots"}}, self.spec)
        message = str(caught.exception)
        self.assertIn("failure_histogram", message)
        self.assertIn("wrong_style", message)

    def test_a_map_facts_keys_have_to_be_names(self):
        with self.assertRaises(FactError):
            diagnose({"failure_histogram": {5: 5}}, self.spec)

    def test_the_failure_modes_themselves_are_still_open(self):
        """A key the router has no route for is NOT rejected, on purpose.

        `failure_mode` is not a declared enum and the spec records that as a
        known gap under `uninspectable_facts` rather than papering over it.
        Checking the keys against a closed set here would close a gap the file
        is honest about, so only the VALUES are typed.
        """
        result = diagnose(
            {"failure_histogram": {"a_mode_nobody_declared": 3}}, self.spec
        )
        self.assertTrue(result.outcome)


class NoIllTypedFactMakesTheEngineRaiseABuiltinTest(unittest.TestCase):
    """The class, swept: mutate the nine real TRAIN fixtures and see what escapes.

    THE FIXTURES ARE THE REAL ONES. `diagnosis_fixtures.MINTING` holds one fact
    set per `TRAIN__` outcome, each a consistent story about a real user, and
    each one reaching a five-gate TRAIN verdict on its own. Corrupting one to
    three of their facts walks the engine deep into the tree with a value the
    ledger does not describe in hand - past stage 0, through the gates, into the
    arithmetic - which is exactly where both known crashes were.

    A fuzz over random fact sets would not do: it would spend its draws being
    refused at the top of the tree. That is what the TRAIN count below is for.
    """

    @classmethod
    def setUpClass(cls):
        cls.spec = default_spec()
        cls.names = list(cls.spec.facts)
        cls.outcomes: Counter[str] = Counter()
        cls.crashes: list[str] = []
        cls._sweep()

    @classmethod
    def _sweep(cls):
        rng = random.Random(SEED)
        low, high = MUTATIONS_PER_DRAW
        for _ in range(DRAWS):
            base = dict(MINTING[rng.choice(list(MINTING))])
            mutated: dict[str, object] = {}
            for _ in range(rng.randint(low, high)):
                name = rng.choice(cls.names)
                value = rng.choice(HOSTILE)
                held = base.get(name)
                # Keep the fixture's own origin, so the corrupted fact is still
                # admissible for the gate that reads it. A value that lost its
                # origin would be refused for being ASSERTED long before its
                # type ever mattered, and the sweep would measure nothing.
                origin = held.origin if isinstance(held, Fact) else diagnosis.MEASURED
                base[name] = Fact(value, origin)
                mutated[name] = value
            try:
                cls.outcomes[diagnose(base, cls.spec).outcome] += 1
            except (FactError, EngineError, SpecError):
                # The three this module owns. All of them carry a message and
                # all of them are handled by every caller in the repository.
                pass
            except Exception as error:  # noqa: BLE001 - the whole subject
                frame = traceback.extract_tb(sys.exc_info()[2])[-1]
                cls.crashes.append(
                    f"{type(error).__name__}: {error}\n"
                    f"  at {frame.filename}:{frame.lineno}  {frame.line}\n"
                    f"  facts mutated: {mutated!r}"
                )

    def test_nothing_escapes_as_a_raw_builtin_exception(self):
        self.assertEqual(
            self.crashes,
            [],
            f"{len(self.crashes)} of {DRAWS} draws raised something that is not a "
            "FactError, an EngineError or a SpecError. Nothing above this in the "
            "stack is looking for those, so each one is an unhandled 500 with a "
            "traceback where the product promises an honest answer. The fix is "
            "the rejection where the value arrives - `_coerce`, with the fact's "
            "name in the message - never a catch at the top.\n\n"
            + "\n\n".join(self.crashes[:5]),
        )

    def test_the_sweep_reached_real_train_verdicts(self):
        """THE VACUITY GUARD, and it is not decoration.

        A sweep that produced no TRAIN verdicts would be a sweep that never got
        past the shallow refusals, and it would pass just as happily against an
        engine that rejected everything at the door. This asserts that the draws
        walked all the way to a minting outcome thousands of times, and that
        every one of the nine was reached.
        """
        train = {
            outcome: count
            for outcome, count in self.outcomes.items()
            if outcome.startswith("TRAIN__")
        }
        self.assertTrue(train, "no draw reached a TRAIN verdict; the sweep is vacuous")
        self.assertGreater(sum(train.values()), DRAWS // 100, sorted(train.items()))
        self.assertEqual(
            set(train), set(MINTING), f"minting outcomes never reached: {sorted(set(MINTING) - set(train))}"
        )

    def test_the_unmutated_fixtures_still_reach_their_own_outcome(self):
        """The positive control for the control. Nine in, nine out.

        Without this, a change that quietly broke every fixture would leave the
        sweep sweeping nothing and the guard above would be measuring a mistake.
        """
        for outcome, facts in MINTING.items():
            with self.subTest(outcome=outcome):
                self.assertEqual(diagnose(dict(facts), self.spec).outcome, outcome)


class TheBoundaryCannotLeakATracebackTest(unittest.TestCase):
    """`run_diagnosis` and the tool route, both nets, both exercised."""

    def setUp(self):
        self.root = support.sandbox(self)

    def test_run_diagnosis_answers_a_malformed_fact_rather_than_raising(self):
        result = REGISTRY.call(
            "run_diagnosis", {"facts": {"need_type": 5}}, actor=MODEL, thread_id=1
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "rejected_fact")
        self.assertIn("need_type", result["detail"])

    def test_the_tool_route_answers_a_malformed_fact_rather_than_raising(self):
        """The exact request that used to leave the ASGI app as a traceback."""
        from app.main import app

        client = support.api_client(app)
        response = client.post(
            "/api/tools/run_diagnosis",
            json={"arguments": {"facts": {"need_type": 5}}},
        )
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["result"]
        self.assertEqual(result["error"], "rejected_fact")

    def test_an_unpredicted_failure_inside_a_tool_is_a_500_with_a_sentence(self):
        """The net under the net.

        Everything above is a failure the route UNDERSTANDS. This is one it does
        not: a tool that raises something nobody predicted. It has to come back
        as a 500 that names the tool and says nothing was recorded, because the
        alternative - which is what happened - is a traceback on somebody's
        screen.
        """
        from app.main import app
        from app.tools.registry import Control, ToolSpec

        def explode():
            raise RuntimeError("the recipe file has a hole in it")

        spec = ToolSpec(
            name="explode_probe",
            description="A tool used only by this test.",
            schema={"type": "object", "properties": {}},
            reads=(),
            writes=(),
            approval="never",
            provides=("context.dataset.preview",),
            control=Control(label="Explode", group="Test", verb="explode"),
            handler=explode,
        )
        REGISTRY.add(spec)
        self.addCleanup(REGISTRY._tools.pop, "explode_probe", None)

        client = support.api_client(app)
        response = client.post("/api/tools/explode_probe", json={"arguments": {}})
        self.assertEqual(response.status_code, 500)
        detail = response.json()["detail"]
        self.assertIn("explode_probe", detail)
        self.assertIn("RuntimeError", detail)
        self.assertIn("Nothing was recorded", detail)

    def test_an_unknown_tool_is_still_a_404(self):
        """The nets must not have swallowed the answers that were already right."""
        from app.main import app

        client = support.api_client(app)
        response = client.post("/api/tools/nothing_like_this", json={"arguments": {}})
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
