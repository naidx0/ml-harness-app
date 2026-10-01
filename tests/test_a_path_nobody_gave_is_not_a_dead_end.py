"""A path the person never gave is a dead end, and it should be a door.

## Measured, twice, on two different builds

`docs/readiness-rehearsal-2026-09-11.md` turn 2, and again in the re-drive on
the restarted engine at `f87b7f4`. The person typed:

> "I have about 400 examples like that. Where do I put them so you can see them?"

The model INVENTED a path and called `profile_repository({"path": "./examples"})`,
then called it twice more on the same absolute path. Each answer said, correctly
and uselessly:

    "There is nothing at that path."

and carried no next move at all. So the model did the only thing left and asked
the person where their data is - which is the complaint this product exists to
answer, in the user's own words: *"a tool has to run and asks for a path where
the data is sitting. I have no idea."*

## Both halves are the product's, and neither is the model's

`assess_the_data` has run without a path since `a443add`: it lists the datasets
it can already see, each row carrying `run_this` so picking one runs the tool
with the path filled in. **The model never called it on either build.** Its
description still says only *"Point it at the file or folder the user named"*,
so nothing the model was handed said that calling it empty does anything at all.
An affordance nobody is told about is not an affordance.

And the dead end is the other half. `profile_repository` answering "there is
nothing at that path" is honest and complete about the question it was asked,
and it leaves a model with nowhere to go but the person. The harness knows
something useful here - what data it CAN see - and the answer is the place to
say so.

## Why a redirect rather than a refusal

`profile_repository` did nothing wrong and must keep answering. This adds a
next move to an answer that had none; it does not change the answer. The
control below holds that: a path that EXISTS gets no redirect, because the
question it was asked was answered.
"""

from __future__ import annotations

import unittest

import support

from app.tools import REGISTRY


class APathThatIsNotThereNamesWhatIsTest(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)

    def test_a_path_that_does_not_exist_carries_the_next_move(self):
        """THE CASE. Turn 2 of both drives, as a property."""
        answer = REGISTRY.get("profile_repository").handler(path="nowhere-at-all")
        move = (answer.get("repository") or {}).get("run_this") or answer.get("run_this")
        self.assertIsNotNone(
            move,
            "a path that is not there is a dead end: the answer names no tool "
            "that could see what actually is here",
        )
        self.assertEqual("assess_the_data", move.get("tool"))
        self.assertFalse(
            move.get("arguments", {}).get("path"),
            "the redirect must NOT carry a path - the whole point is that the "
            "person has not given one, and inventing a second one is the "
            "defect wearing a different tool's name",
        )

    def test_the_tool_it_names_really_runs_without_a_path(self):
        """The advice has to be TRUE. If `path` ever goes back to being
        required, this redirect starts telling the model to make a call that
        cannot be made, and that is worse than the dead end it replaced."""
        schema = REGISTRY.get("assess_the_data").schema
        self.assertNotIn("path", schema.get("required") or [])

    def test_the_description_says_what_an_empty_call_does(self):
        """THE ROUTE, and it is the half that was never built. The affordance
        has existed since `a443add`; nothing the model is handed mentions it,
        and on two drives across two builds the model never chose it."""
        said = (REGISTRY.get("assess_the_data").description or "").lower()
        self.assertTrue(
            any(
                phrase in said
                for phrase in (
                    "with no path",
                    "without a path",
                    "call it with no arguments",
                    "no arguments",
                )
            ),
            "the description never tells the model that calling it empty lists "
            "the datasets already here",
        )

    def test_a_path_that_is_there_is_not_redirected(self):
        """THE CONTROL. `profile_repository` answered the question it was asked;
        a next move stapled to a good answer is noise, and noise is how a
        genuinely useful next move stops being read."""
        answer = REGISTRY.get("profile_repository").handler(path=".")
        move = (answer.get("repository") or {}).get("run_this") or answer.get("run_this")
        self.assertIsNone(move)


if __name__ == "__main__":
    unittest.main()
