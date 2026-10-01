"""RC11. There is no path from a model's tool call to a MEASURED stamp.

`tests/test_tool_registry.py` proves no tool a model can call may DECIDE a gate.
`tests/test_fact_origins.py` proves the engine will not open a gate on a fact
whose origin the ledger does not admit. Between them they leave one question
unasked, and it is the one that decides whether either is worth anything:

    CAN A MODEL GET ITS OWN NUMBER STAMPED MEASURED?

If it can, the engine's refusal is decoration - the model launders an assertion
into a measurement, the gate opens on a measured fact, and every structural
check in the repository is green while the product recommends a fine-tune to
somebody who has counted nothing. That is the same defect as the one the last
adversary found, one layer further down, and it is reachable the moment a tool
is written carelessly.

So this file does not describe the wall. IT ATTACKS IT, with the three attacks
named in the brief, each in the shape the attacker would actually use:

  1. a tool call whose ARGUMENTS claim measured origin;
  2. a tool that returns a CALLER-SUPPLIED value and stamps it;
  3. a model that ASSERTS a fact and then calls a tool that would re-stamp it.

All three must fail closed, and "fail closed" is asserted as an outcome the user
would see - a gate that stays shut and a verdict that is not TRAIN - rather than
as an exception somewhere in the middle. An attack that raises in a place the
product swallows has not been stopped.

WHY THE LAST CLASS IS THE MOST IMPORTANT ONE. A wall this strict is only worth
having if the honest path still goes through, and a product where no gate can
ever open is not more honest, it is broken - it says "do not train" to everybody
including the person who did all the work, and nobody believes the sixth
refusal. `TheHonestPathStillGoesThroughTest` walks it end to end: the same fact
sheet that is refused when a model asserts it is minted when the harness counts
the eval set, scores the baseline, and the PERSON answers the questions that are
theirs to answer. One fixture, three doors, two answers.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import diagnosis_fixtures as fixtures

from app import db, diagnosis
from app import build
from app.providers import Delta, store as provider_store
from app.tools import REGISTRY, evidence, measure
from app.tools.evidence import (
    ASSERTED,
    HARNESS,
    Instrument,
    MEASURED,
    MODEL,
    MeasurementError,
    STATED,
    USER,
)
from app.tools.registry import (
    Control,
    INJECTED_ARGUMENTS,
    RESERVED_ARGUMENTS,
    Registry,
    ToolError,
    ToolSpec,
)

import support


THREAD = 1


def eval_file(root: Path, rows: int = 100, labels: int = 5) -> Path:
    """An eval set with a known row count and a known majority class.

    `labels` classes in equal proportion, so the trivial baseline is exactly
    `1 / labels` and the test can assert a measured number without inventing
    one: it is arithmetic over a file this function wrote.
    """
    path = root / "eval.jsonl"
    path.write_text(
        "\n".join(
            json.dumps({"q": f"q{i}", "a": f"label{i % labels}"}) for i in range(rows)
        ),
        encoding="utf-8",
    )
    return path


class ScriptedModel:
    """A stand-in for the user's connected model, right on the first `correct` rows.

    Not a mock of the adapter protocol in general - it implements the one method
    `measure_baseline` uses, and it answers from the question text, so the score
    it produces is a property of this file rather than of a network.
    """

    def __init__(self, correct: int, labels: int = 5) -> None:
        self.correct = correct
        self.labels = labels
        self.asked: list[str] = []

    def stream(self, conversation, offered, *, secret=None):
        question = conversation[-1]["content"]
        self.asked.append(question)
        index = int(str(question).lstrip("q") or 0)
        if index < self.correct:
            yield Delta(kind="text", text=f"label{index % self.labels}")
        else:
            yield Delta(kind="text", text="something else entirely")


def local_provider(name: str = "Scripted") -> dict:
    row = provider_store.create(name, "http://127.0.0.1:11434", "scripted", "ollama")
    provider_store.set_active(row["id"])
    return row


# ---------------------------------------------------------------------------


class TheMeasuringSurfaceIsSmallAndDeclaredTest(unittest.TestCase):
    """What may be stamped at all, decided at registration against the ledger.

    This runs first because everything below is only meaningful if the set of
    facts a tool may stamp is a closed, checked set rather than whatever a
    handler feels like passing to `measured()`.
    """

    def test_every_measured_fact_a_tool_declares_is_a_ledger_fact(self):
        # WIDENED 2026-08-25: "the fact ledger" was the default spec alone,
        # which refused the second ledger's facts the day the agent
        # instruments shipped. A measured fact must be declared by SOME ledger
        # this product ships - registration already enforces exactly that, so
        # this reads the same union rather than a private copy of it.
        declared: set[str] = set()
        for path in diagnosis.known_ledgers():
            declared |= set(diagnosis.spec_at(path).facts)
        for tool in REGISTRY:
            for fact in tool.measures:
                with self.subTest(tool=tool.name, fact=fact):
                    self.assertIn(
                        fact,
                        declared,
                        f"{tool.name} claims to measure {fact!r}, which is not in "
                        "any fact ledger",
                    )

    def test_no_tool_claims_to_measure_a_fact_only_the_user_can_answer(self):
        """The half of the adversary's six that nothing in this harness watches.

        `prompt_iterations`, `retrieval_tried` and `model_swap_tried` are
        `source: ask` - facts about the user's own week.

        AND THE LEDGER ADMITS MEASURED FOR THEM, which surprised this test into
        being written twice. `admissible_for_gates` says `ask: [MEASURED,
        STATED]`, and it is right: if the harness itself drove five prompt
        rewrites it WATCHED them, and that is stronger evidence than the user's
        memory, not weaker. So the refusal here is not the ledger's, it is this
        harness's own - `may_be_declared_measurable` - and it says the true
        thing: nothing in this product drives that work today, so a tool
        claiming to have observed it would be claiming something no code here
        does.
        """
        spec = diagnosis.default_spec()
        #: WIDENED 2026-08-25: the loop below read every measured fact out of
        # the DEFAULT ledger, which KeyError'd on the second ledger's facts the
        # day the agent instruments shipped. Each fact is now judged by a
        # ledger that declares it - registration already asks the union; the
        # per-fact checks here ask exactly what they asked before, of the
        # right file.
        def declaring_spec(fact):
            paths = evidence.ledgers_declaring(fact)
            if not paths:
                raise AssertionError(f"{fact!r} is measured but declared nowhere")
            return diagnosis.spec_at(paths[0])

        for tool in REGISTRY:
            for fact in tool.measures:
                with self.subTest(tool=tool.name, fact=fact):
                    ledger = declaring_spec(fact)
                    self.assertIn(
                        MEASURED,
                        ledger.admissible_for(fact),
                        f"{tool.name} measures {fact!r}, declared source "
                        f"{ledger.facts[fact].get('source')!r}, which MEASURED cannot "
                        "satisfy",
                    )
                    self.assertNotEqual(
                        ledger.facts[fact].get("source"),
                        "ask",
                        f"{tool.name} claims to measure {fact!r}, which is a fact "
                        "about the user's own history. If a tool now genuinely "
                        "drives that work, widen may_be_declared_measurable "
                        "deliberately and say so here",
                    )
        for fact in ("prompt_iterations", "retrieval_tried", "model_swap_tried"):
            with self.subTest(fact=fact):
                self.assertFalse(evidence.may_be_declared_measurable(fact))
                self.assertEqual(
                    [t.name for t in REGISTRY if fact in t.measures], []
                )

    def test_the_harness_rule_is_stricter_than_the_ledger_and_only_there(self):
        """Two predicates, TWO gaps, and each gap is a different sentence.

        Pinned so that a future edit which collapses them has to choose a
        direction rather than drift into one: collapsing towards the ledger
        lets a tool claim the user's week, collapsing towards the harness rule
        makes a real prompt-driving tool unregisterable.

        THE SECOND GAP ARRIVED WITH WALL 7 and it is not the same gap wearing a
        second name, which is why the assertion below names both rather than
        widening the first.

          * `source: ask` - the ledger WOULD admit a measurement and nothing in
            this harness takes one. A tool that drove the prompt loop could
            close it, and `may_be_declared_measurable`'s docstring says where.
          * `opinion_of:` - the ledger declares the fact a judgement, and no
            tool ever closes that one, because the problem is not who ran the
            instrument. `judge_score` is `source: derive`, which admits
            MEASURED, so `is_measurable` says yes and the harness rule still
            says no.
        """
        spec = diagnosis.default_spec()
        gaps = {"ask": 0, "opinion": 0}
        for name in sorted(spec.facts):
            with self.subTest(fact=name):
                ledger = MEASURED in spec.admissible_for(name)
                asked = spec.facts[name].get("source") == "ask"
                judged = bool(spec.facts[name].get("opinion_of"))
                self.assertEqual(evidence.is_measurable(name), ledger)
                self.assertEqual(
                    evidence.may_be_declared_measurable(name),
                    ledger and not asked and not judged,
                )
            if ledger and asked:
                gaps["ask"] += 1
            if ledger and judged:
                gaps["opinion"] += 1

        # Non-vacuity. A version of the two clauses above that never fired
        # would assert the two predicates are identical and pass.
        self.assertTrue(gaps["ask"], "no `source: ask` fact exercised the first gap")
        self.assertTrue(
            gaps["opinion"], "no `opinion_of:` fact exercised the second gap"
        )

    def test_registering_a_tool_that_measures_the_users_own_history_is_refused(self):
        registry = Registry()
        with self.assertRaises(ToolError) as caught:
            registry.add(
                ToolSpec(
                    name="liar_tool",
                    description="Claims to have watched the user's month.",
                    schema={"type": "object", "properties": {}},
                    reads=(),
                    writes=(),
                    approval="never",
                    provides=("data.eval_set.count",),
                    control=Control(label="Lie", group="Test", verb="lie"),
                    handler=lambda *, instrument: {"ok": True},
                    measures=("prompt_iterations",),
                )
            )
        self.assertIn("prompt_iterations", str(caught.exception))
        self.assertIn("ask", str(caught.exception))

    def test_registering_a_tool_that_measures_a_fact_that_does_not_exist_is_refused(self):
        registry = Registry()
        with self.assertRaises(ToolError) as caught:
            registry.add(
                ToolSpec(
                    name="ghost_tool",
                    description="Measures something the engine never heard of.",
                    schema={"type": "object", "properties": {}},
                    reads=(),
                    writes=(),
                    approval="never",
                    # DECLARED, so this test cannot pass on wall 7 instead of
                    # the wall it is about. A tool with no `provides=` is now
                    # refused too, and a refusal for the wrong reason is a test
                    # that has stopped testing what its name says.
                    provides=("data.eval_set.count",),
                    control=Control(label="Ghost", group="Test", verb="haunt"),
                    handler=lambda *, instrument: {"ok": True},
                    measures=("vibes",),
                )
            )
        self.assertIn("vibes", str(caught.exception))

    def test_a_tool_that_claims_to_measure_without_taking_an_instrument_is_refused(self):
        """Nothing to stamp with is not a smaller claim, it is an unchecked one."""
        registry = Registry()
        with self.assertRaises(ToolError):
            registry.add(
                ToolSpec(
                    name="empty_handed",
                    description="Says it measures and takes no instrument.",
                    schema={"type": "object", "properties": {}},
                    reads=(),
                    writes=(),
                    approval="never",
                    provides=("data.eval_set.count",),
                    control=Control(label="Empty", group="Test", verb="claim"),
                    handler=lambda: {"ok": True},
                    measures=("eval_size_n",),
                )
            )

    def test_no_tool_schema_offers_a_slot_for_a_provenance(self):
        """The spec's own warning, made unbreakable rather than written down.

        `fact_origins.the_origin_is_never_supplied_by_the_thing_being_checked`:
        "if a future tool schema ever grows an `origins` argument a model can
        fill, this whole block becomes decoration on that day".
        """
        for word in ("origin", "origins", "provenance", "measured", "actor"):
            self.assertIn(word, RESERVED_ARGUMENTS)
        for tool in REGISTRY:
            properties = tool.schema.get("properties") or {}
            with self.subTest(tool=tool.name):
                self.assertEqual(
                    {k for k in properties if str(k).lower() in RESERVED_ARGUMENTS},
                    set(),
                )
                self.assertEqual(
                    {k for k in properties if k in INJECTED_ARGUMENTS}, set()
                )


# ---------------------------------------------------------------------------


class NoPathFromAModelToAMeasurementTest(unittest.TestCase):
    """The three attacks, each run rather than described."""

    def setUp(self):
        self.root = support.sandbox(self)
        support.a_conversation(THREAD)
        self.spec = diagnosis.default_spec()

    # -- attack 1 ---------------------------------------------------------

    def test_a_tool_call_that_claims_a_measured_origin_gets_nowhere(self):
        """The arguments say MEASURED. Nothing about the answer changes.

        Every shape the claim could take goes in at once - a bare `origin`, a
        `provenance` map keyed by fact, a boolean `measured` flag, and an
        `actor` claiming to be the person. All four are refused by name, none
        of them reaches the handler, and the verdict is the one an unattributed
        fact sheet gets.
        """
        facts = {name: diagnosis.bare(v) for name, v in fixtures.MINTING["TRAIN__LORA_SFT"].items()}
        result = REGISTRY.call(
            "run_diagnosis",
            {
                "facts": facts,
                "origin": "MEASURED",
                "provenance": {"eval_size_n": "MEASURED"},
                "measured": True,
                "actor": USER,
            },
            actor=MODEL,
            thread_id=THREAD,
        )
        self.assertEqual(
            result["refused_arguments"], ["actor", "measured", "origin", "provenance"]
        )
        self.assertEqual(result["your_facts_were_recorded_as"], ASSERTED)
        self.assertFalse(result["outcome"].startswith("TRAIN__"))
        self.assertEqual(result["outcome"], self.spec.unsubstantiated_outcome)
        self.assertEqual(result["fact_origins"]["eval_size_n"], ASSERTED)

    def test_the_same_claim_on_the_tool_that_records_facts(self):
        """`state_facts` is the other door a claim could arrive through."""
        result = REGISTRY.call(
            "state_facts",
            {"facts": {"prompt_iterations": 9}, "origin": MEASURED},
            actor=MODEL,
            thread_id=THREAD,
        )
        self.assertEqual(result["refused_arguments"], ["origin"])
        self.assertEqual(result["origin"], ASSERTED)
        self.assertFalse(result["recorded"][0]["can_open_a_gate"])
        rows = evidence.rows_for(THREAD)
        self.assertEqual([r["origin"] for r in rows], [ASSERTED])

    # -- attack 2 ---------------------------------------------------------

    def test_a_tool_that_stamps_a_value_it_was_handed_raises(self):
        """The laundering move, written as a tool and run.

        This is the tool a well-meaning future agent writes: take the number
        the model already has, "record" it, return it measured. It is one line
        of code and it removes the entire guarantee. It raises.
        """
        registry = Registry()

        @registry.tool(
            "launder",
            description="Records the eval size the caller already knows.",
            schema={
                "type": "object",
                "properties": {"rows": {"type": "integer"}},
                "required": ["rows"],
            },
            measures=("eval_size_n",),
            provides=("data.eval_set.count",),
            label="Launder",
            group="Test",
            verb="launder a number",
        )
        def launder(rows: int, *, instrument: Instrument):
            instrument.measured("eval_size_n", rows, how="the caller told me")
            return {"ok": True}

        with self.assertRaises(MeasurementError) as caught:
            registry.call("launder", {"rows": 500}, actor=MODEL, thread_id=THREAD)
        self.assertIn("handed", str(caught.exception))
        self.assertEqual(evidence.rows_for(THREAD), [])

    def test_the_same_value_nested_inside_an_argument_is_still_a_handed_value(self):
        """One level of JSON is not a laundry. The taint walks the structure."""
        registry = Registry()

        @registry.tool(
            "nested_launder",
            description="Takes a report and records the number inside it.",
            schema={
                "type": "object",
                "properties": {"report": {"type": "object"}},
                "required": ["report"],
            },
            measures=("eval_size_n",),
            provides=("data.eval_set.count",),
            label="Nested",
            group="Test",
            verb="launder a nested number",
        )
        def nested(report: dict, *, instrument: Instrument):
            instrument.measured(
                "eval_size_n", report["counts"][0], how="read out of the report"
            )
            return {"ok": True}

        with self.assertRaises(MeasurementError):
            registry.call(
                "nested_launder",
                {"report": {"counts": [500, 12]}},
                actor=MODEL,
                thread_id=THREAD,
            )
        self.assertEqual(evidence.rows_for(THREAD), [])

    def test_a_tool_may_not_stamp_a_fact_it_did_not_declare(self):
        registry = Registry()

        @registry.tool(
            "overreach",
            description="Measures one thing and stamps another.",
            schema={"type": "object", "properties": {}},
            measures=("eval_size_n",),
            provides=("data.eval_set.count",),
            label="Overreach",
            group="Test",
            verb="overreach",
        )
        def overreach(*, instrument: Instrument):
            instrument.measured("baseline_score", 0.99, how="I felt it")
            return {"ok": True}

        with self.assertRaises(MeasurementError) as caught:
            registry.call("overreach", {}, actor=HARNESS, thread_id=THREAD)
        self.assertIn("did not declare", str(caught.exception))

    def test_a_stamp_with_no_account_of_how_is_refused(self):
        """Invariant 3, at the point the number is created rather than shown."""
        instrument = evidence.instrument_for(
            tool="probe", measures=("eval_size_n",), thread_id=THREAD,
            provides=("data.eval_set.count",)
        )
        with self.assertRaises(MeasurementError):
            instrument.measured("eval_size_n", 40, how="   ")
        with self.assertRaises(MeasurementError):
            instrument.measured("eval_size_n", None, how="the tool found nothing")
        self.assertEqual(evidence.rows_for(THREAD), [])

    # -- attack 3 ---------------------------------------------------------

    def test_a_tool_that_can_stamp_cannot_read_what_anybody_claimed(self):
        """The two-step laundering: read the assertion back, then stamp it.

        Argument taint cannot see this one - by the time the value is read out
        of the store it is not in the arguments any more - so it is closed by
        keeping the two capabilities apart. A tool holding a measuring
        instrument is refused the claim ledger outright.
        """
        REGISTRY.call(
            "state_facts",
            {"facts": {"eval_size_n": 500}},
            actor=MODEL,
            thread_id=THREAD,
        )

        registry = Registry()

        @registry.tool(
            "restamp",
            description="Reads the ledger and stamps what it finds.",
            schema={"type": "object", "properties": {}},
            measures=("eval_size_n",),
            provides=("data.eval_set.count",),
            label="Restamp",
            group="Test",
            verb="restamp a claim",
        )
        def restamp(*, instrument: Instrument):
            sheet, _ = evidence.assemble_facts(instrument.thread_id)
            instrument.measured(
                "eval_size_n",
                diagnosis.bare(sheet["eval_size_n"]),
                how="it was in the ledger",
            )
            return {"ok": True}

        with self.assertRaises(MeasurementError) as caught:
            registry.call("restamp", {}, actor=MODEL, thread_id=THREAD)
        self.assertIn("laundering", str(caught.exception))
        self.assertEqual(
            [r["origin"] for r in evidence.rows_for(THREAD)],
            [ASSERTED],
            "a measured row was written by a tool that only read one",
        )

    def test_a_model_asserting_a_number_does_not_survive_the_harness_counting(self):
        """The whole attack, end to end, through the real tools.

        The model claims a hundred-thousand-row eval set. The harness counts the
        file and finds twelve. The measurement wins - not because it is later,
        but because it is measured - the gate closes on twelve, and the claim
        survives only as a superseded row in the trail.
        """
        small = self.root / "tiny.jsonl"
        small.write_text(
            "\n".join(json.dumps({"q": f"q{i}", "a": "yes"}) for i in range(12)),
            encoding="utf-8",
        )

        claimed = REGISTRY.call(
            "run_diagnosis",
            {"facts": {"eval_size_n": 100_000}},
            actor=MODEL,
            thread_id=THREAD,
        )
        self.assertEqual(claimed["fact_origins"]["eval_size_n"], ASSERTED)

        counted = REGISTRY.call(
            "measure_eval_set", {"path": str(small)}, actor=MODEL, thread_id=THREAD
        )
        self.assertEqual(counted["rows"], 12)
        self.assertEqual(
            counted["measured_facts"], [
                {
                    "fact": "eval_size_n",
                    "value": 12,
                    "origin": MEASURED,
                    "how": build.counted_rows_how(12, small),
                }
            ]
        )

        after = REGISTRY.call(
            "run_diagnosis",
            {"facts": {"eval_size_n": 100_000}},
            actor=MODEL,
            thread_id=THREAD,
        )
        self.assertEqual(after["fact_origins"]["eval_size_n"], MEASURED)
        self.assertEqual(after["facts_used"]["eval_size_n"]["value"], 12)
        self.assertNotEqual(
            after["gate_ledger"]["G0_EVAL_SET"]["status"],
            "PASSED",
            "the gate opened on a number nobody counted",
        )
        self.assertFalse(after["outcome"].startswith("TRAIN__"))

    def test_profiling_a_file_nobody_called_the_eval_set_records_nothing_and_says_so(self):
        """Found live, on the real model. Silence read as agreement.

        granite4-hermes pointed `profile_dataset` at the user's eval file with
        no `split`. The count was real, nothing was recorded - correctly, since
        nothing on disk says which split a file is - and the tool said nothing
        about it, which in a transcript reads as the harness having taken the
        number. It now says what did not happen and how to make it happen.
        """
        path = eval_file(self.root, rows=40)
        result = REGISTRY.call(
            "profile_dataset", {"path": str(path)}, actor=MODEL, thread_id=THREAD
        )
        self.assertEqual(result["rows"], 40)
        self.assertNotIn("measured_facts", result)
        self.assertEqual(evidence.rows_for(THREAD), [])
        self.assertIn("split='eval'", result["eval_size_n_not_recorded"])
        self.assertIn("measure_eval_set", result["eval_size_n_not_recorded"])

        told = REGISTRY.call(
            "profile_dataset",
            {"path": str(path), "split": "eval"},
            actor=MODEL,
            thread_id=THREAD,
        )
        self.assertNotIn("eval_size_n_not_recorded", told)
        self.assertEqual(told["measured_facts"][0]["fact"], "eval_size_n")
        self.assertEqual(told["measured_facts"][0]["value"], 40)

    def test_a_truncated_scan_is_a_lower_bound_and_stamps_nothing(self):
        """"At least this many" is not a count, and G0 is not opened by one."""
        big = eval_file(self.root, rows=100)
        result = REGISTRY.call(
            "profile_dataset",
            {"path": str(big), "split": "eval", "max_rows": 10},
            actor=MODEL,
            thread_id=THREAD,
        )
        self.assertTrue(result["rows_are_truncated"])
        self.assertNotIn("measured_facts", result)
        self.assertEqual(evidence.rows_for(THREAD), [])


# ---------------------------------------------------------------------------


class WhoIsCallingDecidesWhatTheirWordIsWorthTest(unittest.TestCase):
    """The engine-side split between a person and a model, wired to a door."""

    def setUp(self):
        self.root = support.sandbox(self)
        support.a_conversation(THREAD)
        self.spec = diagnosis.default_spec()

    def test_the_actor_map_covers_every_actor_and_fails_closed(self):
        self.assertEqual(evidence.origin_for(USER), STATED)
        self.assertEqual(evidence.origin_for(MODEL), ASSERTED)
        self.assertEqual(evidence.origin_for(HARNESS), ASSERTED)
        self.assertEqual(evidence.origin_for(None), ASSERTED)
        self.assertEqual(evidence.origin_for("someone_new"), ASSERTED)
        self.assertEqual(evidence.origin_for(evidence.DEFAULT_ACTOR), ASSERTED)

    def test_the_same_call_through_two_doors_gives_two_answers(self):
        """One tool, identical arguments, and the difference is who called.

        This is the design decision made mechanical at the tool boundary. The
        person who did five prompt rewrites opens G2 by saying so. A model
        reporting on their week does not, and it is the same tool, the same
        fact, the same number.
        """
        arguments = {"facts": {"prompt_iterations": 5}}

        by_the_model = REGISTRY.call(
            "state_facts", dict(arguments), actor=MODEL, thread_id=THREAD
        )
        self.assertEqual(by_the_model["origin"], ASSERTED)
        self.assertFalse(by_the_model["recorded"][0]["can_open_a_gate"])
        self.assertIn("yourself", by_the_model["recorded"][0]["if_not"])

        by_the_person = REGISTRY.call(
            "state_facts", dict(arguments), actor=USER, thread_id=THREAD
        )
        self.assertEqual(by_the_person["origin"], STATED)
        self.assertTrue(by_the_person["recorded"][0]["can_open_a_gate"])

    def test_a_model_cannot_overwrite_what_the_person_said(self):
        """Precedence is by origin strength, so the weaker voice cannot win."""
        REGISTRY.call(
            "state_facts",
            {"facts": {"prompt_iterations": 5}},
            actor=USER,
            thread_id=THREAD,
        )
        REGISTRY.call(
            "state_facts",
            {"facts": {"prompt_iterations": 0}},
            actor=MODEL,
            thread_id=THREAD,
        )
        sheet, trail = evidence.assemble_facts(THREAD)
        self.assertEqual(diagnosis.bare(sheet["prompt_iterations"]), 5)
        self.assertEqual(sheet["prompt_iterations"].origin, STATED)
        row = next(r for r in trail if r["fact"] == "prompt_iterations")
        self.assertEqual([s["value"] for s in row["superseded"]], [0])

    def test_a_person_correcting_themselves_wins_on_recency(self):
        for value in (5, 2):
            REGISTRY.call(
                "state_facts",
                {"facts": {"prompt_iterations": value}},
                actor=USER,
                thread_id=THREAD,
            )
        sheet, _ = evidence.assemble_facts(THREAD)
        self.assertEqual(diagnosis.bare(sheet["prompt_iterations"]), 2)

    def test_the_person_saying_so_still_does_not_open_a_gate_the_harness_must_measure(self):
        """The strictest line in the policy, reached through the user's own door.

        `eval_size_n` is `source: inspect`. An honest, correct user typing the
        real number is still not the harness having counted it, and G0 stays
        shut. The tool says so to their face and names the tool that would
        settle it, which is the difference between a rule and a wall a user
        walks into in the dark.
        """
        result = REGISTRY.call(
            "state_facts",
            {"facts": {"eval_size_n": 100}},
            actor=USER,
            thread_id=THREAD,
        )
        row = result["recorded"][0]
        self.assertEqual(row["origin"], STATED)
        self.assertFalse(row["can_open_a_gate"])
        self.assertEqual(row["settled_by"]["tool"], "measure_eval_set")
        self.assertEqual(row["settled_by"]["run_as"], "harness")

    def test_the_harness_driving_a_tool_is_not_a_witness_either(self):
        """`actor="harness"` is worth a model's word, and its tools still measure."""
        instrument = evidence.instrument_for(tool="probe", actor=HARNESS)
        self.assertEqual(instrument.supplied_origin, ASSERTED)
        result = REGISTRY.call("inspect_hardware", {}, actor=HARNESS, thread_id=THREAD)
        measured = {row["fact"] for row in result.get("measured_facts", [])}
        for row in evidence.rows_for(THREAD):
            self.assertEqual(row["origin"], MEASURED)
            self.assertEqual(row["actor"], HARNESS)
            self.assertIn(row["fact"], measured)

    def test_a_tool_stamps_only_the_hardware_it_actually_read(self):
        """Only what came back `measured`, never what came back `defaulted`."""
        result = REGISTRY.call("inspect_hardware", {}, actor=USER, thread_id=THREAD)
        provenance = result["provenance"]
        stamped = {row["fact"] for row in result.get("measured_facts", [])}
        for field in ("ram_gb", "vram_gb", "disk_free_gb"):
            with self.subTest(field=field):
                if provenance.get(field) != "measured":
                    self.assertNotIn(field, stamped)
        self.assertTrue(
            all(row["how"].strip() for row in result.get("measured_facts", []))
        )


# ---------------------------------------------------------------------------


class TheRefusalIsAnInstructionAndNotAWallTest(unittest.TestCase):
    """Requirement 5: the product does something about it, not just says no."""

    def setUp(self):
        self.root = support.sandbox(self)
        support.a_conversation(THREAD)
        self.spec = diagnosis.default_spec()

    def test_a_refused_run_names_the_tool_that_would_settle_each_fact(self):
        facts = {
            name: diagnosis.bare(v)
            for name, v in fixtures.MINTING["TRAIN__LORA_SFT"].items()
        }
        result = REGISTRY.call(
            "run_diagnosis", {"facts": facts}, actor=MODEL, thread_id=THREAD
        )
        self.assertEqual(result["outcome"], self.spec.unsubstantiated_outcome)
        self.assertTrue(result["unsubstantiated"])
        for row in result["unsubstantiated"]:
            with self.subTest(fact=row["fact"]):
                step = row["next_step"]
                self.assertEqual(step["fact"], row["fact"])
                self.assertTrue(step["substantiation"].strip())
                self.assertIsNotNone(
                    step["tool"],
                    f"{row['fact']} was challenged and the product had nothing to "
                    "offer, which makes the refusal a dead end",
                )

    def test_every_fact_a_gate_reads_has_a_next_step_or_says_it_has_none(self):
        """Derived from the registry, so a tool added next year answers for itself."""
        for key, names in sorted(self.spec.gate_row_facts.items()):
            for name in sorted(names):
                with self.subTest(gate=key[0], fact=name):
                    step = evidence.resolves(name)
                    source = self.spec.facts[name]["source"]
                    if source == "ask":
                        self.assertEqual(step["tool"], "state_facts")
                        self.assertEqual(step["run_as"], USER)
                    elif step["tool"] is None:
                        self.assertIn("note", step)
                        self.assertTrue(step["note"].strip())
                    else:
                        self.assertIn(name, REGISTRY.get(step["tool"]).measures)

    def test_the_two_gates_everything_stands_on_have_a_tool_each(self):
        """G0 and G1 say what would settle them. Both sentences are executable."""
        self.assertEqual(evidence.resolves("eval_size_n")["tool"], "measure_eval_set")
        for fact in ("baseline_measured", "baseline_score", "trivial_baseline_score"):
            with self.subTest(fact=fact):
                self.assertEqual(evidence.resolves(fact)["tool"], "measure_baseline")

    def test_a_baseline_will_not_be_measured_off_this_machine_on_a_models_say_so(self):
        """The user may send their own data anywhere. A model may not send it for them."""
        row = provider_store.create(
            "Somewhere else", "https://api.example.com/v1", "gpt-x", "openai-compatible"
        )
        provider_store.set_active(row["id"])
        path = eval_file(self.root)

        refused = REGISTRY.call(
            "measure_baseline",
            {"eval_path": str(path), "input_field": "q", "expected_field": "a"},
            actor=MODEL,
            thread_id=THREAD,
        )
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "remote_needs_the_user")
        self.assertEqual(evidence.rows_for(THREAD), [])

    def test_a_baseline_run_that_falls_over_records_nothing(self):
        """All three of G1's facts from one run, or none of them."""
        local_provider()
        path = eval_file(self.root)

        class Broken:
            def stream(self, conversation, offered, *, secret=None):
                yield Delta(kind="error", detail="the endpoint went away")

        original = measure.build
        measure.build = lambda *args, **kwargs: Broken()
        self.addCleanup(lambda: setattr(measure, "build", original))

        result = REGISTRY.call(
            "measure_baseline",
            {"eval_path": str(path), "input_field": "q", "expected_field": "a"},
            actor=USER,
            thread_id=THREAD,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "model_failed")
        self.assertEqual(evidence.rows_for(THREAD), [])


# ---------------------------------------------------------------------------


class TheHonestPathStillGoesThroughTest(unittest.TestCase):
    """The other direction, and the reason a strict wall is allowed to be strict.

    A product where no gate can ever open is not more honest than one where they
    open on claims - it is useless, and a refusal nobody can act on is a refusal
    nobody believes. So the same fact sheet is run twice: once asserted by a
    model, where it is stopped, and once with the eval set COUNTED, the baseline
    SCORED, and the `source: ask` facts answered BY THE PERSON. The second one
    mints, and every number behind it came from somewhere.
    """

    def setUp(self):
        self.root = support.sandbox(self)
        support.a_conversation(THREAD)
        self.spec = diagnosis.default_spec()
        self.fixture = {
            name: diagnosis.bare(value)
            for name, value in fixtures.MINTING["TRAIN__LORA_SFT"].items()
        }
        # What the ledger says the user is the only witness to, plus the facts
        # the harness has a tool for. Split by the ledger's own `source:` column
        # rather than by a list, so a fact that changes source moves with it.
        self.asked = sorted(
            name
            for name in self.fixture
            if self.spec.facts[name]["source"] == "ask"
        )
        self.measurable = ("eval_size_n", "baseline_measured", "baseline_score",
                           "trivial_baseline_score")

    def test_the_lying_provider_is_stopped(self):
        result = REGISTRY.call(
            "run_diagnosis", {"facts": self.fixture}, actor=MODEL, thread_id=THREAD
        )
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertEqual(result["outcome"], self.spec.unsubstantiated_outcome)

    def test_the_same_sheet_mints_when_the_work_was_actually_done(self):
        path = eval_file(self.root, rows=100, labels=5)
        local_provider()
        scripted = ScriptedModel(correct=55)
        original = measure.build
        measure.build = lambda *args, **kwargs: scripted
        self.addCleanup(lambda: setattr(measure, "build", original))

        counted = REGISTRY.call(
            "measure_eval_set", {"path": str(path)}, actor=USER, thread_id=THREAD
        )
        self.assertEqual(counted["rows"], 100)

        scored = REGISTRY.call(
            "measure_baseline",
            {
                "eval_path": str(path),
                "input_field": "q",
                "expected_field": "a",
                "sample": 100,
            },
            actor=USER,
            thread_id=THREAD,
        )
        self.assertTrue(scored["ok"], scored.get("summary"))
        # 55 of 100 right, and five equal classes, so the trivial baseline is
        # one in five. Both are arithmetic over a file this test wrote.
        self.assertEqual(scored["baseline_score"], 0.55)
        self.assertEqual(scored["trivial_baseline_score"], 0.2)
        self.assertEqual(len(scripted.asked), 100)

        stated = REGISTRY.call(
            "state_facts",
            {"facts": {name: self.fixture[name] for name in self.asked}},
            actor=USER,
            thread_id=THREAD,
        )
        self.assertEqual(stated["origin"], STATED)

        # The model still supplies the routing facts - modality, task family,
        # the failure histogram. Those are not gate facts and an assertion may
        # route on them; `fact_origins.scope` says why in as many words.
        result = REGISTRY.call(
            "run_diagnosis", {"facts": self.fixture}, actor=MODEL, thread_id=THREAD
        )
        self.assertEqual(
            result["outcome"],
            "TRAIN__LORA_SFT",
            f"the honest path did not go through: {result.get('say')}",
        )
        for gate, entry in result["gate_ledger"].items():
            with self.subTest(gate=gate):
                self.assertEqual(entry["status"], "PASSED")
        for name in self.measurable:
            with self.subTest(fact=name):
                self.assertEqual(result["fact_origins"][name], MEASURED)
        for name in self.asked:
            with self.subTest(fact=name):
                self.assertEqual(result["fact_origins"][name], STATED)

    def test_the_measured_values_are_the_measured_ones_and_not_the_claimed_ones(self):
        """Non-vacuity for the class above: the fixture's numbers are not reused.

        The claim and the measurement must be able to disagree, or the previous
        test would pass on a sheet where nothing was ever checked. So the eval
        set on disk has a different size from the one the model claims, and the
        engine is asserted to be reasoning on the file.
        """
        path = eval_file(self.root, rows=64, labels=4)
        REGISTRY.call(
            "measure_eval_set", {"path": str(path)}, actor=USER, thread_id=THREAD
        )
        self.assertEqual(diagnosis.bare(self.fixture["eval_size_n"]), 100)
        result = REGISTRY.call(
            "run_diagnosis", {"facts": self.fixture}, actor=MODEL, thread_id=THREAD
        )
        self.assertEqual(result["facts_used"]["eval_size_n"]["value"], 64)
        self.assertEqual(result["fact_origins"]["eval_size_n"], MEASURED)


class AMalformedCallIsAFailedCallAndNotAnEmptyOneTest(unittest.TestCase):
    """A live defect, found against granite4-hermes on Ollama, written down.

    The model was asked to run the diagnosis and sent seventeen facts at the
    TOP LEVEL of the call instead of inside `facts`:

        run_diagnosis {"retrieval_tried": true, "eval_size_n": 100, ...}

    Every one of them was dropped as an unknown argument, `facts` defaulted to
    `None` in Python, and the tool answered `ok: true` with a verdict computed
    from an empty sheet. The user would have read a confident
    BLOCKED__DEFINE_SUCCESS_FIRST that was about nothing.

    `conductor.py` names this failure exactly - "a skipped step becomes a
    missing fact, and a missing fact becomes a diagnosis computed from
    defaults" - and it arrived anyway, through a door nobody had checked: the
    schema said `required: [facts]` and nothing read it.
    """

    def setUp(self):
        self.root = support.sandbox(self)
        support.a_conversation(THREAD)

    def test_a_required_argument_that_did_not_arrive_stops_the_call(self):
        """The specimen is derived; it used to be `run_diagnosis`.

        `facts` stopped being required on 2026-09-11 - it is the one
        argument that cannot open a gate, and requiring it had models
        inventing fact names to satisfy the schema. The property below is
        unchanged and is the one this class exists for; only the tool it is
        demonstrated on moved. `support.a_tool_that_requires_an_argument`
        says why that is derived now.
        """
        tool = support.a_tool_that_requires_an_argument()
        required = sorted(tool.schema["required"])
        result = REGISTRY.call(
            tool.name,
            {"eval_size_n": 100, "retrieval_tried": True},
            actor=MODEL,
            thread_id=THREAD,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "missing_arguments")
        self.assertEqual(sorted(result["missing"]), required)
        self.assertNotIn("outcome", result)
        self.assertEqual(result["ignored_arguments"], ["eval_size_n", "retrieval_tried"])

    def test_the_diagnosis_answers_a_call_that_sends_no_facts(self):
        """THE OTHER HALF OF THAT CHANGE, asserted where the old one lived.

        A model asked "which use case should I pick" spent all eight tool
        rounds inside this machinery and had a call rejected for inventing
        fact names, because the schema demanded an argument that cannot
        open a gate: only MEASURED facts do, and facts a caller sends are
        ASSERTED. Sending none is now a legal question - it asks where the
        thread stands - and this holds that door open so a later tidy of
        the schema cannot quietly shut it.
        """
        result = REGISTRY.call("run_diagnosis", {}, actor=MODEL, thread_id=THREAD)
        self.assertNotEqual(result.get("error"), "missing_arguments")

    def test_every_tool_with_a_required_argument_refuses_a_call_without_it(self):
        """Not one tool. The whole surface, because one was enough to do this."""
        for tool in REGISTRY:
            required = list(tool.schema.get("required") or ())
            if not required:
                continue
            with self.subTest(tool=tool.name):
                # `approved=True` because approval is checked first and is a
                # different refusal. This test is about the arguments.
                result = REGISTRY.call(
                    tool.name, {}, approved=True, actor=MODEL, thread_id=THREAD
                )
                self.assertEqual(result["error"], "missing_arguments")
                # A DECLARED `thread_id` IS FILLED FROM THE CALL SITE, not
                # reported missing: the prompt never tells a model which
                # conversation it is in, so a schema that asks for it asks for
                # something the model cannot know, and the registry supplies
                # the one this call arrived with (2026-09-11, for write_plan).
                # Everything else required is still a refusal.
                expected = sorted(r for r in required if r != "thread_id")
                self.assertEqual(result["missing"], expected)
                if "thread_id" in required:
                    self.assertNotIn("thread_id", result["missing"])
                    #: AND THE OTHER DIRECTION: with no thread at the call site
                    #: it is missing again, so the fill cannot become always-on.
                    without = REGISTRY.call(
                        tool.name, {}, approved=True, actor=MODEL, thread_id=None
                    )
                    self.assertIn("thread_id", without.get("missing", []))

    def test_nothing_runs_and_nothing_is_recorded_when_arguments_are_missing(self):
        REGISTRY.call("measure_eval_set", {}, actor=USER, thread_id=THREAD)
        REGISTRY.call("state_facts", {"fact": "retrieval_tried"}, actor=USER,
                      thread_id=THREAD)
        self.assertEqual(evidence.rows_for(THREAD), [])

    def test_a_tool_with_no_required_arguments_still_runs_on_an_empty_call(self):
        """The fix must not turn every optional argument into a demand."""
        result = REGISTRY.call("run_diagnosis", {"facts": {}}, actor=MODEL,
                               thread_id=THREAD)
        self.assertTrue(result["ok"])
        self.assertTrue(REGISTRY.call("inspect_hardware", {}, actor=USER)["provenance"])


class TheEvidenceLedgerIsTheStoryTest(unittest.TestCase):
    """Invariant 3, for the facts a verdict was computed from."""

    def setUp(self):
        self.root = support.sandbox(self)
        support.a_conversation(THREAD)

    def test_every_row_says_who_said_it_and_how(self):
        REGISTRY.call(
            "state_facts",
            {"facts": {"retrieval_tried": True}},
            actor=USER,
            thread_id=THREAD,
        )
        REGISTRY.call("inspect_hardware", {}, actor=HARNESS, thread_id=THREAD)
        rows = evidence.ledger_view(THREAD)
        self.assertTrue(rows)
        for row in rows:
            with self.subTest(fact=row["fact"]):
                self.assertIn(row["origin"], (MEASURED, STATED, ASSERTED))
                self.assertIn(row["actor"], (USER, MODEL, HARNESS))
                self.assertTrue(row["how"].strip())
                self.assertTrue(row["created_at"])

    def test_a_thread_does_not_see_another_threads_measurements(self):
        """A count is a fact about one project, and leaking it opens a gate."""
        first = self.root / "first.jsonl"
        first.write_text(
            "\n".join(json.dumps({"a": i}) for i in range(40)), encoding="utf-8"
        )
        REGISTRY.call(
            "measure_eval_set", {"path": str(first)}, actor=USER, thread_id=THREAD
        )
        sheet, _ = evidence.assemble_facts(THREAD)
        self.assertEqual(diagnosis.bare(sheet["eval_size_n"]), 40)

        other, _ = evidence.assemble_facts(THREAD + 1)
        self.assertNotIn("eval_size_n", other)

    def test_a_machine_scoped_measurement_is_visible_everywhere(self):
        """Hardware has no thread. The box is the box, whoever is asking."""
        REGISTRY.call("inspect_hardware", {}, actor=USER, thread_id=None)
        rows = evidence.rows_for(THREAD)
        self.assertTrue(rows)
        self.assertTrue(all(row["thread_id"] is None for row in rows))

    def test_nothing_is_ever_updated_in_place(self):
        for value in (1, 2, 3):
            REGISTRY.call(
                "state_facts",
                {"facts": {"prompt_iterations": value}},
                actor=USER,
                thread_id=THREAD,
            )
        rows = [r for r in evidence.rows_for(THREAD) if r["fact"] == "prompt_iterations"]
        self.assertEqual([r["value"] for r in rows], [1, 2, 3])

    def test_the_table_appears_on_a_database_that_never_had_one(self):
        """Self-healing, so an install that predates fact origins still works."""
        with db.session() as connection:
            connection.execute("DROP TABLE IF EXISTS fact_evidence")
        self.assertEqual(evidence.rows_for(THREAD), [])


if __name__ == "__main__":
    unittest.main()
