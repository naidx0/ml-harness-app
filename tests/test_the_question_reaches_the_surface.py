"""The question gets to the person, and it cannot stamp its own answer.

Two halves sat in this repository with nothing between them. `app/asking.py`
derives THE question that would move a stopped diagnosis, as typed data, with
`next_step()` and `as_dict()` written for a wire - and NOTHING IMPORTED IT.
`frontend/src/components/QuestionCard.tsx` draws that card, verified by
screenshot in both themes - and NOTHING RENDERED IT. `GET /api/next_step` is
the join, and this file is what makes the join safe to have made.

══ WHY A ROUTE THAT ONLY SERVES A CARD NEEDS AN ADVERSARIAL TEST ═════════════

Because of what is written on the card. `asking.Question.arrives_as` is the
ORIGIN the answer will carry - STATED for a field the person types into,
MEASURED for a pointer at something an instrument reads. Putting that string on
the wire is safe. Accepting it back would not be, and the distance between the
two is one handler somebody adds in a hurry six months from now:

    a card that could stamp its own answer is the laundering route this
    entire design exists to shut.

There are about thirty such routes already closed in this repository. Every one
of them was a place where a value arrived carrying its own claim about how good
it was. So this file does not check that the route happens to be read-only
today. IT TRIES TO LAUNDER A MEASUREMENT THROUGH IT, four ways:

  * by POSTing an answer to it (`TheRouteTakesNoAnswerTest`);
  * by telling it what the facts are, so a caller can choose which question the
    person is shown (`TheRouteReadsTheLedgerNotTheRequestTest`);
  * by typing a value into the fact a POINTER card asks about, through the card's
    own named door, and checking what the ledger actually wrote
    (`ATypedAnswerToAPointerCardTest`);
  * by checking that the origin the card PROMISES is the origin the tool
    boundary WRITES, for every card the route can serve
    (`ThePromiseIsKeptTest`).

══ AND ONE TEST THAT THE CONNECTION IS REAL ═════════════════════════════════

`TheRouteServesTheEnginesOwnCardTest` compares the route's payload against
`asking.next_step().as_dict()` computed in-process. That is deliberately a
strict equality rather than a spot-check of three fields: the failure it exists
to catch is a route that RE-DERIVES the question instead of importing the module
that derives it, which would pass any test that only looked at a fact name and
would drift from the ledger the first time either side was edited.
"""

from __future__ import annotations

import unittest

from app import asking, diagnosis
from app.diagnosis import MEASURED, STATED
from app.main import app as fastapi_app
from app.tools import REGISTRY, evidence

from support import api_client, sandbox


SPEC = diagnosis.default_spec()


def a_value_for(fact: str):
    """A value of the fact's own declared type. Derived, never tabulated."""
    decl = SPEC.facts[fact]
    if "enum" in decl:
        return decl["enum"][0]
    if "multi" in decl:
        return [decl["multi"][0]]
    declared = str(decl.get("type") or "")
    if declared == "bool":
        return True
    if declared == "int":
        return 999
    if declared == "float":
        return 0.99
    return "something the person typed"


class RouteCase(unittest.TestCase):
    """A sandboxed database and a client that presents the real token."""

    def setUp(self) -> None:
        sandbox(self)
        self.client = api_client(fastapi_app)

    def open_thread(self) -> int:
        created = self.client.post("/api/threads", json={"title": "asking"})
        self.assertEqual(created.status_code, 201, created.text)
        return int(created.json()["id"])

    def card(self, thread_id: int | None = None) -> dict:
        query = "" if thread_id is None else f"?thread_id={thread_id}"
        response = self.client.get(f"/api/next_step{query}")
        self.assertEqual(response.status_code, 200, response.text)
        step = response.json()["step"]
        self.assertEqual(
            step["kind"],
            "question",
            "an empty sheet has questions left; a propose step here means the "
            "frontier was computed against something other than this thread",
        )
        return step["question"]


class TheRouteServesTheEnginesOwnCardTest(RouteCase):
    """The connection is an import, not a second implementation."""

    def test_the_payload_is_next_step_as_dict_verbatim(self) -> None:
        thread = self.open_thread()

        response = self.client.get(f"/api/next_step?thread_id={thread}")
        self.assertEqual(response.status_code, 200, response.text)

        sheet, _trail = evidence.assemble_facts(thread, {}, evidence.USER)
        expected = asking.next_step(result=diagnosis.diagnose(sheet)).as_dict()

        self.assertEqual(
            response.json()["step"],
            expected,
            "the route must serve app/asking.py's own object. A payload that "
            "differs anywhere is a route deriving the question for itself, "
            "which is a second opinion about which fact to ask for and a second "
            "place for the origin wall to be got wrong.",
        )

    def test_the_module_that_had_no_importer_now_has_one(self) -> None:
        """The literal defect in the brief: `NOTHING IN THE REPO IMPORTS IT`."""
        import app.main as main

        self.assertIs(
            main.asking,
            asking,
            "app/main.py must import app/asking.py itself rather than copying "
            "what it returns",
        )

    def test_the_card_names_the_door_it_is_not(self) -> None:
        thread = self.open_thread()
        body = self.client.get(f"/api/next_step?thread_id={thread}").json()

        through = body["answer_through"]
        self.assertEqual(through["route"], "POST /api/tools/{name}")
        self.assertEqual(through["actor"], evidence.USER)
        self.assertEqual(
            through["tool"],
            body["step"]["question"]["answered_by"],
            "the route must point at the same tool the card names, or a client "
            "following the payload answers through a door the engine did not "
            "pick",
        )


class TheRouteTakesNoAnswerTest(RouteCase):
    """There is no `POST /api/next_step`, and there must never be one."""

    def test_the_route_refuses_every_method_that_could_carry_an_answer(self) -> None:
        thread = self.open_thread()
        card = self.card(thread)

        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                # `request` rather than `client.delete(...)`: httpx's DELETE
                # helper takes no `json=`, and a body is the whole point here.
                sent = self.client.request(
                    method.upper(),
                    "/api/next_step",
                    json={
                        "thread_id": thread,
                        "fact": card["fact"],
                        "value": 4,
                        # The whole attack in one field.
                        "arrives_as": MEASURED,
                        "origin": MEASURED,
                    },
                )
                self.assertNotIn(
                    sent.status_code,
                    (200, 201),
                    f"{method.upper()} /api/next_step answered. A card that can "
                    "be answered where it was served is a card that stamps its "
                    "own origin; the answer goes through POST /api/tools/{name}, "
                    "where the actor is a property of the door.",
                )

    def test_nothing_was_recorded_by_trying(self) -> None:
        thread = self.open_thread()
        card = self.card(thread)

        self.client.post(
            "/api/next_step",
            json={"fact": card["fact"], "value": 4, "origin": MEASURED},
        )

        rows = evidence.ledger_view(thread)
        self.assertEqual(
            [row for row in rows if row["fact"] == card["fact"]],
            [],
            "a refused request wrote a row",
        )


class TheRouteReadsTheLedgerNotTheRequestTest(RouteCase):
    """A caller may not choose which question the person is shown."""

    def test_facts_sent_as_query_parameters_change_nothing(self) -> None:
        thread = self.open_thread()
        honest = self.card(thread)

        loaded = self.client.get(
            f"/api/next_step?thread_id={thread}"
            f"&facts=%7B%22{honest['fact']}%22%3A%204%7D"
            f"&{honest['fact']}=4"
            f"&origin={MEASURED}"
            f"&actor=harness"
        )
        self.assertEqual(loaded.status_code, 200, loaded.text)
        self.assertEqual(
            loaded.json()["step"]["question"],
            honest,
            "the route answered a different question because the request said "
            "so. Every extra parameter here is ignored on purpose: a caller who "
            "can move the frontier by asserting things can choose what the "
            "person is asked next.",
        )

    def test_the_question_moves_when_the_LEDGER_moves(self) -> None:
        """The other half: it is not simply frozen.

        Without this, `test_facts_sent_as_query_parameters_change_nothing` would
        pass against a route that returned a constant.
        """
        thread = self.open_thread()
        before = self.card(thread)

        # Record the fact the card asks about, through the user's own door. It
        # arrives STATED, which is not what an `inspect` fact admits - so the
        # gate does not move - but the ROW is real and the engine now has an
        # opinion about the fact.
        wrote = self.client.post(
            "/api/tools/state_facts",
            json={
                "arguments": {"facts": {before["fact"]: a_value_for(before["fact"])}},
                "thread_id": thread,
            },
        )
        self.assertEqual(wrote.status_code, 200, wrote.text)

        rows = [row for row in evidence.ledger_view(thread) if row["fact"] == before["fact"]]
        self.assertTrue(rows, "the write did not land, so this test proves nothing")
        self.assertEqual(rows[0]["origin"], STATED)


class ATypedAnswerToAPointerCardTest(RouteCase):
    """THE LAUNDERING ATTEMPT. Type a value into a fact that must be measured.

    The route serves a POINTER card for an `inspect` fact - "point me at the
    folder and `assess_the_data` will count it" - and says the answer will
    arrive MEASURED. The attack is to skip the instrument: take the fact name
    off the card and send a number for it through the user's own door, which is
    the highest-trust door in the product.

    It must arrive STATED, it must open nothing, and the ledger must say so.
    """

    def test_the_number_arrives_stated_and_opens_nothing(self) -> None:
        """Every pointer card in the ledger, not just the one served today.

        WHICH card the route serves is the ledger's call and it moves - the
        whole design is that a fact becomes a pointer on the day a tool
        declaring `measures=` for it is registered. Pinning "the first question
        is `classes_n`" here would make this test a hostage to
        `docs/diagnosis_engine.yaml`, and the day it broke somebody would
        "fix" it by relaxing it. So the attack is run against EVERY fact the
        module will build a pointer card for.
        """
        thread = self.open_thread()

        pointers = [
            card
            for card in (asking.question_for(fact) for fact in sorted(SPEC.facts))
            if isinstance(card, asking.Question) and card.points
        ]
        self.assertTrue(
            pointers,
            "the ledger declares no pointer cards at all, so this test proves "
            "nothing - that is a finding, not a pass",
        )

        #: Facts where a typed value actually became a STATED row. See the
        #: `rejected_fact` branch below for why this is counted.
        landed: list[str] = []

        for card in pointers:
            with self.subTest(fact=card.fact):
                self.assertEqual(card.arrives_as, MEASURED)
                # NOT `source == "inspect"`. `failure_histogram` is declared
                # `source: derive` and still gets a pointer card, because
                # `run_eval` declares `measures=("failure_histogram",)` and the
                # door is derived from `evidence.resolves` rather than from a
                # list of sources somebody typed. That is the derivation working.
                # What has to hold for every one of them is the property the
                # attack is against: the person's own word is not good enough.
                self.assertNotIn(
                    STATED,
                    SPEC.admissible_for(card.fact),
                    f"{card.fact} gets a pointer card promising MEASURED while "
                    "its ledger entry would also admit STATED, so the same fact "
                    "has a typed door and a measured one",
                )

                answered = self.client.post(
                    "/api/tools/state_facts",
                    json={
                        "arguments": {"facts": {card.fact: a_value_for(card.fact)}},
                        "thread_id": thread,
                    },
                )
                self.assertEqual(answered.status_code, 200, answered.text)
                result = answered.json()["result"]

                if result.get("ok") is False:
                    # The stronger outcome: the value never became a row at all.
                    # `failure_histogram` takes `map[failure_mode,int]` and a
                    # scalar is refused by the ledger's own coercion. Counted as
                    # a pass, but NOT counted towards `landed` below - a suite
                    # where every fact took this branch would be proving that
                    # the test sends bad values, not that the wall holds.
                    self.assertEqual(result.get("error"), "rejected_fact", result)
                    continue

                self.assertEqual(
                    result["origin"],
                    STATED,
                    "a value typed into a pointer card's fact was recorded as "
                    "something other than the person's own word",
                )
                recorded = [row for row in result["recorded"] if row["fact"] == card.fact]
                self.assertEqual(len(recorded), 1, result)
                self.assertEqual(recorded[0]["origin"], STATED)
                self.assertFalse(
                    recorded[0]["can_open_a_gate"],
                    f"a typed answer to {card.fact}, which the ledger says must "
                    "be measured, opened a gate. This is the five-gate honesty "
                    "test defeated by a form field.",
                )

                stored = [
                    row for row in evidence.ledger_view(thread) if row["fact"] == card.fact
                ]
                self.assertEqual(
                    {row["origin"] for row in stored},
                    {STATED},
                    "the row in the ledger does not say STATED",
                )
                landed.append(card.fact)

        self.assertTrue(
            landed,
            "every pointer fact refused the typed value on its TYPE before the "
            "origin was ever considered, so this test never exercised the wall "
            "it exists to check. That is a vacuous pass and it must fail.",
        )

    def test_every_card_in_the_payload_is_internally_coherent(self) -> None:
        """`typed`, `answer` and `arrives_as` are three views of one decision.

        This is the invariant the browser's reader (`engine/asking.ts`
        `readCard`) fails closed on, asserted here against the real route so the
        two cannot disagree about what a coherent card is.

        OVER THE WHOLE PAYLOAD, NOT THE HEADLINE CARD, and that distinction was
        found by mutation rather than by reading. Forcing `arrives_as` to
        MEASURED on `step.question` alone changed nothing detectable, because
        the question an empty sheet produces is a POINTER and already says
        MEASURED - so the test that was supposed to catch origin-laundering
        passed against a laundering route. The typed cards in this payload are
        all in `frontier.entries[].questions[]`, so that is where a rewrite
        would show and that is what has to be walked.
        """
        def cards_for(thread_id: int) -> list[dict]:
            response = self.client.get(f"/api/next_step?thread_id={thread_id}")
            self.assertEqual(response.status_code, 200, response.text)
            step = response.json()["step"]
            out = []
            if step["question"]:
                out.append(step["question"])
            for entry in step["frontier"]["entries"]:
                out.extend(entry["questions"])
            return out

        # TWO THREADS, BECAUSE ONE NO LONGER CARRIES BOTH SHAPES, and the
        # reason is a fix rather than a loss. An empty sheet used to be asked
        # for `classes_n` - a POINTER card - by `S0_RULES_SUFFICE`, on a
        # thread that had not said what kind of task it was. That node reads
        # `task_family in {extraction, classification} and ... classes_n <= 5`
        # and answers False at the first operand, so the class count was never
        # looked at; the asker was reading a PARSE of the condition rather
        # than what the evaluation reached (2026-09-19). The empty sheet now
        # carries only the typed `target_score`.
        #
        # The invariant this test exists for is unchanged and so is its
        # mutation coverage: both shapes are still walked, and a rewrite of
        # either would still show. The pointer comes from the thread that has
        # answered the bar, which is where the walk reaches the eval count.
        empty = self.open_thread()
        cards = cards_for(empty)

        answered = self.open_thread()
        told = self.client.post(
            "/api/tools/state_facts",
            json={"arguments": {"facts": {"target_score": 0.8}}, "thread_id": answered},
        )
        self.assertEqual(told.status_code, 200, told.text)
        pointer_cards = cards_for(answered)
        cards = cards + pointer_cards

        self.assertTrue(cards, "the payload carried no cards at all")
        kinds = {card["typed"] for card in cards}
        self.assertEqual(
            kinds,
            {True, False},
            "only one shape of card was walked, so a mutation that relabelled "
            "the other would not be caught here. Cards seen: "
            + repr([(c["fact"], c["answer"], c["arrives_as"]) for c in cards]),
        )

        for card in cards:
            with self.subTest(fact=card["fact"]):
                typed = card["typed"]
                self.assertEqual(typed, card["answer"] in asking.TYPED_ANSWERS)
                self.assertEqual(card["arrives_as"], STATED if typed else MEASURED)
                self.assertIn(card["arrives_as"], SPEC.admissible_for(card["fact"]))

    def test_state_facts_could_not_stamp_it_even_if_it_wanted_to(self) -> None:
        """The structural half. `state_facts` declares `measures=()`."""
        spec = next(tool for tool in REGISTRY if tool.name == "state_facts")
        self.assertEqual(
            tuple(spec.measures),
            (),
            "state_facts declares that it measures something. It is the tool "
            "every FIELD card answers through, so a `measures=` on it is a "
            "direct path from a typed value to a MEASURED stamp.",
        )

    def test_the_card_never_names_state_facts_for_a_fact_it_must_measure(self) -> None:
        """Belt and braces, over every card the route could ever serve."""
        for fact in sorted(SPEC.facts):
            built = asking.question_for(fact)
            if not isinstance(built, asking.Question):
                continue
            with self.subTest(fact=fact):
                if built.arrives_as == MEASURED:
                    self.assertNotEqual(
                        built.answered_by,
                        "state_facts",
                        f"the card for {fact} promises MEASURED and sends the "
                        "answer to the tool that measures nothing",
                    )
                    self.assertIn(
                        fact,
                        next(
                            tool.measures
                            for tool in REGISTRY
                            if tool.name == built.answered_by
                        ),
                        f"{built.answered_by} does not declare measures=({fact!r},)",
                    )


class ThePromiseIsKeptTest(RouteCase):
    """`arrives_as` is a promise, and the boundary is what keeps it.

    A card saying STATED that produced ASSERTED would be worse than a card
    saying nothing: the person would have been told their answer counted.
    """

    def test_a_field_cards_promise_matches_what_the_door_writes(self) -> None:
        thread = self.open_thread()

        typed = [
            card
            for card in (asking.question_for(fact) for fact in sorted(SPEC.facts))
            if isinstance(card, asking.Question) and card.typed
        ]
        self.assertTrue(typed, "no field cards exist, so this test proves nothing")

        for card in typed[:8]:
            with self.subTest(fact=card.fact):
                self.assertEqual(card.arrives_as, STATED)
                answered = self.client.post(
                    "/api/tools/state_facts",
                    json={
                        "arguments": {"facts": {card.fact: a_value_for(card.fact)}},
                        "thread_id": thread,
                    },
                )
                self.assertEqual(answered.status_code, 200, answered.text)
                row = next(
                    entry
                    for entry in answered.json()["result"]["recorded"]
                    if entry["fact"] == card.fact
                )
                self.assertEqual(
                    row["origin"],
                    card.arrives_as,
                    f"the card for {card.fact} promised {card.arrives_as} and "
                    f"the boundary wrote {row['origin']}",
                )

    def test_every_servable_card_promises_an_origin_the_ledger_admits(self) -> None:
        for fact in sorted(SPEC.facts):
            built = asking.question_for(fact)
            if not isinstance(built, asking.Question):
                continue
            with self.subTest(fact=fact):
                self.assertIn(
                    built.arrives_as,
                    SPEC.admissible_for(fact),
                    f"the card for {fact} promises an origin its own ledger "
                    "entry does not admit",
                )


class TheRouteIsReadOnlyTest(RouteCase):
    """Serving a question must not move the ledger."""

    def test_asking_twice_writes_nothing(self) -> None:
        thread = self.open_thread()

        before = evidence.ledger_view(thread)
        for _ in range(3):
            self.assertEqual(self.client.get(f"/api/next_step?thread_id={thread}").status_code, 200)
        after = evidence.ledger_view(thread)

        self.assertEqual(
            before,
            after,
            "deriving a question changed the evidence it was derived from",
        )

    def test_a_thread_that_does_not_exist_is_still_answered_without_writing(self) -> None:
        """No 404. An unknown thread has no evidence, which is a fact sheet.

        Pinned because the alternative is a route that must be kept in step with
        the threads table, and because the empty sheet's question - "what would
        you ask me first" - is a real and useful answer.
        """
        response = self.client.get("/api/next_step?thread_id=999999")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["step"]["kind"], "question")


class APropseStepCarriesNoQuestionTest(unittest.TestCase):
    """The contract the SURFACE now depends on, pinned on this side of the wire.

    `frontend/src/components/QuestionCard.tsx` used to read a null `question` as
    permission to derive one of its own, from the frozen diagnosis snapshot it
    was rendered beside. That is right when the engine has said nothing and
    WRONG when the engine has said `kind: 'propose'` - the frontier is exhausted
    because the facts it wanted are in the ledger, and a derivation from the
    stale snapshot then draws a card saying a MEASURED fact "has not been
    answered in this thread".

    The surface can only tell those two apart if a propose step reliably carries
    no question. It does, by construction - `next_step` sets `question` on the
    question branch only - and this is the test that says so out loud, because
    the frontend is now written against it and nothing else asserts it.
    """

    def walk_to_exhaustion(self):
        """Answer whatever the frontier asks until it stops asking.

        Every value is read off the fact's OWN declaration - the first enum
        member, the declared type's obvious filler - rather than chosen here,
        so this walks the real ledger and invents no readings.
        """
        spec = asking._spec()
        facts: dict = {}
        for _ in range(60):
            result = diagnosis.diagnose(facts)
            card = asking.next_question(result)
            if card is None:
                return facts, result
            decl = spec.facts[card.fact]
            if "enum" in decl:
                value = decl["enum"][0]
            elif "multi" in decl:
                value = [decl["multi"][0]]
            elif decl.get("type") == "bool":
                value = True
            elif decl.get("type") == "int":
                value = 1000
            elif decl.get("type") == "float":
                value = 0.9
            else:
                value = "text"
            facts[card.fact] = (
                diagnosis.measured(value) if decl.get("source") == "inspect" else value
            )
        self.fail("the frontier never emptied in 60 answers")

    def test_the_frontier_can_be_emptied_at_all(self):
        """The anti-vacuity guard. If nothing below ever reaches a propose step,
        every assertion in this class is about a branch that never runs."""
        facts, _ = self.walk_to_exhaustion()
        self.assertTrue(facts, "the frontier was empty before anything was answered")

    def test_it_is_a_propose_step_and_it_carries_no_question(self):
        _, result = self.walk_to_exhaustion()
        payload = asking.next_step(result=result).as_dict()
        self.assertEqual(payload["kind"], "propose")
        self.assertIsNone(
            payload["question"],
            "a propose step carrying a question would make the surface's two "
            "cases indistinguishable",
        )
        self.assertIsNotNone(payload["proposal"])

    def test_and_the_question_branch_still_carries_one(self):
        """The control, so the test above cannot pass by the payload always
        being empty."""
        payload = asking.next_step(result=diagnosis.diagnose({})).as_dict()
        self.assertEqual(payload["kind"], "question")
        self.assertIsNotNone(payload["question"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
