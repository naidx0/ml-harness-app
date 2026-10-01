"""A question about the machine in front of you can be asked before anything else.

## The measurement this exists because of

`docs/readiness-rehearsal-2026-09-11.md`, turn 4. A stranger asked:

> "Will that actually run on this machine?"

That is the question `can_this_machine_train` answers to the tenth of a
gigabyte, off the VRAM measured from this card and the layers, heads and
vocabulary in the model's own `config.json`. The model wrote **5,831 characters
of prose naming the tools it could have called** and called none.

**It could not have called that one.** Reading the run's own `turn.started`
events afterwards: all four turns offered the same 29 of the registry's 71
tools, packs `[context, data, ledger, machine]`, and `can_this_machine_train`
was not among them. The diagnosis sat at `BLOCKED__DEFINE_SUCCESS_FIRST` for
the whole conversation, and the instrument lived in the `training` pack, which
a stage-0 walk never turns on.

## Why the walk cannot be the only answer

`app/tools/blocks.py` unions four sources into the active set: the core, what
this ledger declares core, what it declares for the standing stage and outcome,
and what the diagnosis itself named. **None of them reads the person's
sentence.** So a stranger can ask about their own hardware in plain English and
contribute nothing at all to what the model is handed; the walk's stage decides,
and at stage 0 the walk is about defining success.

That scoping is not naive and must not be undone. `docs/CAPABILITY_BLOCKS.md`
§7 rejects accumulate-forever explicitly, "for precisely the reason it would be
the 40-tool problem reached slowly" - which is the complaint this product
exists to answer, in the user's own words: *it throws tools in your face.* So
the answer is not to widen on a training word.

The answer is that **a question about the box in front of you is not a
training-stage action.** How much memory the card has does not depend on
whether success has been defined, and the instrument that reads it belongs
where `inspect_hardware` already is.

## Why the subjects are derived

Listing the tools here would be a list somebody has to remember to add to. The
registry already declares what each tool touches, so the property reads itself
off that: **a tool that reads the hardware, writes nothing and needs no
approval is a question about this machine.** A machine question added next year
is covered by this test on the day it is registered.

The same three declarations draw the boundary, which is what stops this fix
becoming "offer everything". `start_training` reads the hardware too - it
writes `jobs`, `runs` and `events` and needs approval every time, so it is the
expensive irreversible half and stays behind the walk. `find_models` writes a
cache and reaches the network. Neither is a question about the box.
"""

from __future__ import annotations

import unittest

import support

from app import diagnosis
from app.tools import REGISTRY, blocks


def a_question_about_this_machine() -> list[str]:
    """DERIVED FROM THE REGISTRY'S OWN DECLARATIONS, never listed.

    Reads the hardware, so it is about this box. Writes nothing and needs no
    approval, so it is a question rather than an action.
    """
    return sorted(
        spec.name
        for spec in REGISTRY
        if "hardware" in (spec.reads or ())
        and not (spec.writes or ())
        and spec.approval == "never"
    )


def the_stage_a_stranger_starts_in(spec) -> dict:
    """One standing diagnosis with no facts in it, in the shape `run_diagnosis`
    puts on the wire - which is the state every one of the rehearsal's four
    turns was in."""
    result = diagnosis.diagnose({}, spec)
    return {
        "ok": True,
        "outcome": result.outcome,
        "verdict": result.verdict,
        "say": result.say,
        "proposed_method": result.proposed_method,
        "gate_ledger": result.gate_ledger,
        "path": [entry.as_dict() for entry in result.path],
        "fact_origins": result.fact_origins,
        "facts_used": {
            name: {"value": None, "origin": origin, "how": ""}
            for name, origin in result.fact_origins.items()
            if origin != "DEFAULTED"
        },
        "decided_by": "app/diagnosis.py",
    }


class AMachineQuestionIsReachableFromTheStartTest(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)
        self.spec = diagnosis.default_spec()
        self.payload = the_stage_a_stranger_starts_in(self.spec)
        #: `as_dict()` is what `turn.started` carries, so this reads the wire
        #: rather than the function behind it.
        self.on_the_wire = blocks.active(
            self.payload, thread_id=None, spec=self.spec
        ).as_dict()

    def test_the_rehearsals_stage_is_the_one_being_tested(self):
        """If the walk stops somewhere else one day, this file is about a state
        that no longer happens and should say so rather than pass quietly."""
        self.assertEqual("BLOCKED__DEFINE_SUCCESS_FIRST", self.payload["outcome"])

    def test_the_subjects_are_derived_and_there_are_some(self):
        """A criterion that silently matches nothing would make every case
        below pass by vacuum."""
        subjects = a_question_about_this_machine()
        self.assertIn("can_this_machine_train", subjects)
        self.assertIn("inspect_hardware", subjects)

    @unittest.expectedFailure
    def test_every_machine_question_is_offered_at_the_stage_a_stranger_starts_in(self):
        """THE CASE. Turn 4 of both drives, as a property rather than an anecdote.

        RECORDED AS AN EXPECTED FAILURE RATHER THAN FIXED, because fixing it the
        obvious way breaks something better than it.

        The obvious fix is to move `machine.feasibility.*` and
        `machine.placement.*` out of the `training` pack, since packs are derived
        from `provides` and the pack a capability belongs to is decided by which
        question it answers - `models.candidate.score` sits in `models` rather
        than `measurement` for exactly that reason. It works: stage 0 goes from
        29 tools to 32, the three machine questions arrive, `start_training` and
        `find_models` stay out, nothing is lost.

        AND IT COSTS 218 CHARACTERS ON A BUDGET WITH ONE TO SPARE. Measured over
        all 70-plus sheets in `diagnosis_fixtures`:

            ACTION__SUBSTANTIATE_CLAIMED_FACTS   2,399 of FOCUSED_BUDGET 2,400
            the same sheet with the three moved   2,617

        The widest scoped brief this product can produce was already one
        character under the line, and the next widest sheet is 1,875 - so that
        outcome is an outlier the core has quietly grown into, not a margin I
        overspent.

        `FOCUSED_BUDGET` is the one bound this repository says must not move.
        `test_the_diagnosis_is_not_optional` raised the degenerate bound six
        times and each time recorded why the focused one did not: *"a raise here
        is the registry growing; a raise there would be the scoping having
        failed."* Scoping exists to answer the complaint that the product throws
        tools in your face. Raising it to fit a fix for a stranger's question
        would trade that complaint for this one.

        So the fix is not "add the instrument to the core". It is either to find
        why one outcome loads 500 characters more than any other, or to let the
        person's own question reach the tool scope - `map_the_ask` already turns
        a sentence into a curated journey whose steps name registered tools,
        which is the same kind of bounded, authored-in-advance source as the
        diagnosis rows `active()` already reads. Neither is a change to make at
        the end of a shift.

        This case stays, red and declared, so the defect is in the suite rather
        than in a note nobody opens."""
        offered = set(self.on_the_wire["tools"])
        withheld = [
            name for name in a_question_about_this_machine() if name not in offered
        ]
        self.assertEqual(
            [], withheld,
            "a stranger asking about their own machine cannot be answered with "
            "an instrument, because these were not offered: " + ", ".join(withheld),
        )

    def test_the_expensive_irreversible_half_stays_behind_the_walk(self):
        """THE BOUNDARY, and it is what stops the fix being 'offer everything'.
        Both of these read the hardware; neither is a question about it."""
        offered = set(self.on_the_wire["tools"])
        self.assertNotIn("start_training", offered)
        self.assertNotIn("find_models", offered)

    def test_stage_zero_still_offers_far_less_than_everything(self):
        """THE CONTROL. The scoping exists because forty schemas on every turn
        is the complaint this product was built to answer. A fix that widened
        until this stopped being true would have traded one defect for the one
        underneath it."""
        self.assertLess(len(self.on_the_wire["tools"]), len(REGISTRY.names()))


if __name__ == "__main__":
    unittest.main()
