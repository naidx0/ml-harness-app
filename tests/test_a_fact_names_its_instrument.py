"""Wall 9: a real number, honestly read, by the wrong kind of tool.

## The debt this pays, in the words it was written down in

`docs/PHASES.md` carried it under Debts from the day capability blocks shipped:

> **Any tool may claim any fact.** `may_be_declared_measurable` is checked per
> *fact* and never per *instrument*, so nothing structural stops a tabular tool
> stamping a text-eval gate fact. Only care has prevented it so far. Fixing this
> makes a whole class of defect unaskable.

## Why the eight walls already there do not catch it

Every one of them asks the same question in a different way: **where did this
number come from?** The mark says it is not the caller's object; the quarantine
says it is not a value the caller sent; `_note_conversion` says it is not a
caller's value rebuilt through `int()`; wall 8 says it was not read off a file
of generated rows; wall 7 says it is not a model's judgement.

A tool of the wrong KIND passes all eight, honestly. `fit_a_tree_model` really
does score a decision tree; the accuracy it computes really is its own; nothing
in the call was the caller's. Declare `measures=("baseline_score",)` and every
provenance check is satisfied - and G1, the gate that says *a text baseline has
been measured against a trivial one*, opens on a number about a CSV.

**The question nobody was asking is not about the value. It is about the
reader.** That is what a fact declaring `measured_by:` asks.

## Why the ledger declares it, and why in capabilities rather than tool names

`contract.capabilities.needs` already binds a stage's work to PACKS rather than
to tools, for the reason a fact needs too: a ledger is domain knowledge and a
tool name is an implementation detail, so a rename would silently unbind every
fact in the file. `app/tools/blocks.py` publishes the closed vocabulary and
`check_name` refuses anything outside it, which is the same wall `provides=`
gets on the tool's own side.

## Why silence is legal, and what stops that from being the hole again

A fact with no `measured_by:` is one the ledger has not spoken about. Reading
silence as "nothing may measure this" would have refused every stamp in the
product on the day this shipped, so the permissive reading is deliberate - and
it would be exactly the debt again if nothing closed it.

`TheRatchetTest` is what closes it: **every fact some registered tool declares
`measures=` on must declare `measured_by:`**, swept over both shipped ledgers.
A new instrument that forgets the declaration reddens the run that adds it.
Silence is legal precisely where nothing is claiming to measure.

## What is driven rather than asserted

Registration is driven through `_validate`, the same code path every `@tool`
decorator runs at import. The stamp is driven through a real `Instrument`
against the real ML ledger, with the number honestly computed inside the test,
so what is refused is a measurement that is true.
"""

from __future__ import annotations

import unittest

from app import diagnosis
from app.tools import REGISTRY, blocks, evidence

#: Every ledger this product ships, DERIVED rather than listed. Read as paths
#: rather than through `default_spec()` because the whole question is whether
#: the second ledger is held to the first one's standard, and it was not.
#:
#: A LITERAL TUPLE STOOD HERE UNTIL 2026-08-28 and it was a trap with a date on
#: it. `diagnosis.known_ledgers()` is a directory glob, deliberately - "a second
#: place naming which ledgers ship is a second place that goes stale" - so a
#: third ledger dropped into `docs/ledgers/` would have been picked up by the
#: engine, by the router and by the journey test, and silently skipped by THIS
#: file. The rule it holds would have applied to two domains out of three, and
#: nothing would have said so.
def _shipped_ledgers() -> tuple[str, ...]:
    return tuple(
        diagnosis.spec_at(path).as_written for path in diagnosis.known_ledgers()
    )


SHIPPED_LEDGERS = _shipped_ledgers()

#: Loaded once. `diagnosis.load_spec` re-parses and re-validates a 3,500-line
#: YAML file on every call, and the sweeps below are nested loops over facts and
#: tools - the first version of this file spent 58 seconds re-reading two
#: documents it had already read. `spec_at` is the cached door and this is the
#: same idea held locally, so what the sweeps read is unambiguously one parse.
_LOADED: dict[str, diagnosis.Spec] = {}


def ledger(path: str) -> diagnosis.Spec:
    if path not in _LOADED:
        _LOADED[path] = diagnosis.load_spec(path)
    return _LOADED[path]


def _measured_facts() -> dict[str, list[str]]:
    """Every fact some registered tool declares `measures=` on, and by whom."""
    found: dict[str, list[str]] = {}
    for spec in REGISTRY:
        for fact in spec.measures:
            found.setdefault(str(fact), []).append(spec.name)
    return found


class TheRatchetTest(unittest.TestCase):
    """The half that keeps 'the ledger has not said' from becoming the debt."""

    def test_there_are_measured_facts_to_check(self):
        """A sweep over an empty map passes forever."""
        self.assertGreaterEqual(len(_measured_facts()), 20)

    def test_every_fact_a_tool_measures_names_its_instrument(self):
        silent = []
        for fact, tools in sorted(_measured_facts().items()):
            for path in SHIPPED_LEDGERS:
                spec = ledger(path)
                if fact not in spec.facts:
                    continue
                if not evidence.measured_by(fact, spec):
                    silent.append(f"{path}: {fact} (measured by {sorted(tools)})")
        self.assertEqual(
            [],
            silent,
            "these facts have an instrument and the ledger does not say which "
            "kind of instrument may read them, so any tool that registers may "
            "stamp them. Add `measured_by: [<capability>]` to the fact, beside "
            "`source:`, where a reviewer reads the claim.",
        )

    def test_every_instrument_is_admitted_by_the_facts_it_measures(self):
        """The other direction, and it is the one a rename breaks. A tool whose
        capability is not in its fact's `measured_by` cannot stamp - so if this
        ever failed, a shipped instrument would be silently unable to measure
        the thing it exists for."""
        for spec in REGISTRY:
            for fact in spec.measures:
                for path in SHIPPED_LEDGERS:
                    current = ledger(path)
                    if fact not in current.facts:
                        continue
                    with self.subTest(tool=spec.name, fact=fact, ledger=path):
                        self.assertTrue(
                            evidence.the_right_instrument(
                                fact, spec.provides, current
                            ),
                            f"{spec.name} provides {sorted(spec.provides)} and "
                            f"{fact} admits {list(evidence.measured_by(fact, current))}",
                        )

    def test_every_declared_capability_is_one_the_engine_publishes(self):
        """A misspelling here is the worst failure this declaration has: it
        names a capability no tool provides, so wall 9 refuses EVERY instrument
        for that fact and the gate can never open."""
        for path in SHIPPED_LEDGERS:
            spec = ledger(path)
            bound = blocks.check_fact_instruments(spec)
            self.assertGreater(len(bound), 0, path)
            for fact, wanted in bound.items():
                for name in wanted:
                    self.assertIn(name, blocks.CAPABILITIES, f"{path}: {fact}")

    def test_every_declared_capability_has_a_tool_that_provides_it(self):
        """A capability nothing provides is a fact nothing can measure, said in
        a way that reads as though something could."""
        for path in SHIPPED_LEDGERS:
            spec = ledger(path)
            for fact, wanted in blocks.check_fact_instruments(spec).items():
                for name in wanted:
                    self.assertTrue(
                        blocks.providers(name),
                        f"{path}: {fact} admits {name!r} and no registered tool "
                        "provides it",
                    )


class RegistrationRefusesTheWrongInstrumentTest(unittest.TestCase):
    """Driven through `_validate`, the path every `@tool` decorator runs."""

    def _spec(self, **overrides):
        from app.tools.registry import Control, ToolSpec

        base = dict(
            name="a_tool_for_this_test",
            description="fits a tree on a table and scores it",
            schema={"type": "object", "properties": {"path": {"type": "string"}}},
            reads=("filesystem",),
            writes=("facts",),
            approval="never",
            control=Control(label="X", group="Look", verb="look", order=1),
            handler=lambda path, *, instrument: {"ok": True},
            provides=("tabular.tree.fit",),
        )
        base.update(overrides)
        return ToolSpec(**base)

    def test_a_tabular_tool_may_not_declare_a_text_baseline_fact(self):
        """THE DEFECT THE DEBT NAMED, run. `baseline_score` opens G1, and G1 is
        about a text baseline scored against a trivial one."""
        from app.tools.registry import ToolError, _validate

        with self.assertRaises(ToolError) as caught:
            _validate(self._spec(measures=("baseline_score",)))
        message = str(caught.exception)
        self.assertIn("baseline_score", message)
        self.assertIn("tabular.tree.fit", message)
        self.assertIn("measurement.baseline.score", message)

    def test_the_right_instrument_registers(self):
        """The negative beside it. A wall that refuses everything is a wall
        nobody leaves standing."""
        from app.tools.registry import _validate

        _validate(
            self._spec(
                measures=("baseline_score",),
                provides=("measurement.baseline.score",),
            )
        )

    def test_a_fact_the_ledger_has_not_bound_is_not_refused(self):
        """Silence is permissive, on purpose, and the ratchet above is what
        keeps that from being a hole. `prompt_iterations` is refused for a
        different reason entirely - source: ask - so the fact used here is one
        the ML ledger declares inspect and does not bind."""
        from app.tools.registry import _validate

        unbound = [
            name
            for name in ledger(SHIPPED_LEDGERS[0]).facts
            if evidence.may_be_declared_measurable(
                name, ledger(SHIPPED_LEDGERS[0])
            )
            and not evidence.measured_by(
                name, ledger(SHIPPED_LEDGERS[0])
            )
        ]
        if not unbound:  # every measurable fact is bound; nothing to show
            self.skipTest("every measurable ML fact names an instrument")
        _validate(self._spec(measures=(unbound[0],)))

    def test_the_refusal_says_what_would_work(self):
        """A wall with no door sends the author back to the YAML to guess."""
        from app.tools.registry import ToolError, _validate

        with self.assertRaises(ToolError) as caught:
            _validate(self._spec(measures=("eval_size_n",)))
        message = str(caught.exception)
        self.assertIn("data.eval_set.count", message)
        self.assertIn("measured_by", message)


class TheStampIsRefusedPerCallTest(unittest.TestCase):
    """And at the stamp, because registration has no thread and so no domain."""

    def setUp(self):
        import support

        from app import events

        support.sandbox(self)
        self.ml = ledger(SHIPPED_LEDGERS[0])
        # A REAL CONVERSATION, because `baseline_score` is scope: thread and a
        # row written without one is machine-scoped - visible to every thread on
        # this box. The stamp has to succeed for the control below to mean
        # anything, so the fixture has to be one a stamp can succeed on.
        self.thread = int(events.create_thread(title="wall 9")["id"])

    def _instrument(self, *, provides, measures=("baseline_score",)):
        return evidence.instrument_for(
            tool="a_tool_for_this_test",
            measures=measures,
            actor="user",
            thread_id=self.thread,
            arguments={},
            provides=provides,
            ledger=self.ml,
        )

    def test_an_honest_number_from_the_wrong_instrument_is_refused(self):
        """The number is computed here, in this test, off nothing the caller
        sent - so every other wall passes and this is the only one that can
        refuse it."""
        instrument = self._instrument(provides=("tabular.tree.fit",))
        correct = sum(1 for row in range(1000) if row % 3 == 0)
        score = correct / 1000
        with self.assertRaises(evidence.MeasurementError) as caught:
            instrument.measured(
                "baseline_score", score, how="scored a decision tree on held-out rows"
            )
        message = str(caught.exception)
        self.assertIn("not an instrument for it", message)
        self.assertIn("tabular.tree.fit", message)

    def test_the_same_number_from_the_right_instrument_is_stamped(self):
        """THE CONTROL, AND IT IS THE HALF THAT MAKES THE TEST ABOVE MEAN
        ANYTHING. Same value, same `how`, same everything but the capability -
        and it goes through. A wall that refused this too would be a wall
        against measurement rather than against the wrong measurer."""
        instrument = self._instrument(provides=("measurement.baseline.score",))
        correct = sum(1 for row in range(1000) if row % 3 == 0)
        score = correct / 1000
        stamped = instrument.measured(
            "baseline_score", score, how="scored the model over the eval set"
        )
        self.assertEqual(diagnosis.MEASURED, stamped["origin"])
        self.assertEqual(score, stamped["value"])

    def test_a_tool_declaring_nothing_is_refused_for_a_bound_fact(self):
        """`provides=` is required at registration, so an empty one can only
        reach here through a hand-built instrument - and it must not be the way
        through."""
        instrument = self._instrument(provides=())
        with self.assertRaises(evidence.MeasurementError):
            instrument.measured("baseline_score", 0.42, how="read it off a run")

    def test_an_unbound_fact_still_stamps(self):
        """The permissive half, driven rather than reasoned about."""
        unbound = [
            name
            for name in self.ml.facts
            if evidence.may_be_declared_measurable(name, self.ml)
            and not evidence.measured_by(name, self.ml)
        ]
        if not unbound:
            self.skipTest("every measurable ML fact names an instrument")
        instrument = self._instrument(
            provides=("tabular.tree.fit",), measures=(unbound[0],)
        )
        stamped = instrument.measured(unbound[0], 7, how="counted them")
        self.assertEqual(diagnosis.MEASURED, stamped["origin"])


class TheDeclarationSurvivesTheRoundTripTest(unittest.TestCase):
    """One string or a list; both are the same declaration."""

    def test_a_single_capability_may_be_written_without_brackets(self):
        spec = ledger(SHIPPED_LEDGERS[1])
        self.assertEqual(("agent.tools.read",), evidence.measured_by("tool_count", spec))

    def test_an_absent_declaration_reads_as_empty_and_not_as_none(self):
        spec = ledger(SHIPPED_LEDGERS[0])
        self.assertEqual((), evidence.measured_by("target_score", spec))

    def test_a_fact_nobody_declared_reads_as_empty(self):
        spec = ledger(SHIPPED_LEDGERS[0])
        self.assertEqual((), evidence.measured_by("no_such_fact_anywhere", spec))



class TheRosterIsDerivedNotListedTest(unittest.TestCase):
    """The guard on the guard.

    `SHIPPED_LEDGERS` used to be a literal tuple, and a third ledger would have
    been silently exempt from everything this file holds. It is now the glob -
    and this asserts that it IS the glob, with a floor under it so an empty or
    unreadable `docs/ledgers/` cannot make the sweeps above pass by having
    nothing to sweep.
    """

    def test_the_roster_is_exactly_what_the_engine_loads(self):
        self.assertEqual(
            sorted(SHIPPED_LEDGERS),
            sorted(
                diagnosis.spec_at(path).as_written
                for path in diagnosis.known_ledgers()
            ),
        )

    def test_there_is_more_than_one_of_them(self):
        """Two is the number that makes every sweep here mean something: one
        ledger cannot show that a rule is domain-general."""
        self.assertGreaterEqual(len(SHIPPED_LEDGERS), 2)

if __name__ == "__main__":  # pragma: no cover
    unittest.main()
