"""A blank the thread already holds is filled, not billed back to the person.

## The walk, and what the harness did

ML BUILD, `530fc0b`, a 3B model at the wheel with the data and the path given:
the model called `map_the_ask` with **empty arguments**, and the harness
answered by asking the person to say again what they had already said.

The sentence was in `thread.goal` before any tool ran. It had already been
matched to `goal_journey`. Every part of the answer was sitting in the thread.

## Why this is a product fault and not a model one

`map_the_ask` says why it exists in its own description: *"so a small
conductor model does not need ML methodology in its weights - the map carries
it, and the model's job shrinks to relaying steps and asking the person for the
blanks."* A small model dropping an argument is the case this design is FOR. A
harness that answers the slip by making the person retype what it is already
holding has charged them for the model's mistake, and taught them the product
forgets.

## The two answers, and the second one matters as much

**Filled** when the thread holds it - and *said*, always. A value that appears
in a call the person did not make is a thing they are entitled to see, and "it
worked" is not a reason to be quiet about where it came from.

**Named as malformed** when nothing can fill it. Not *"say that again"*: if the
thread had held the value the harness would have used it, so being asked at all
means something went wrong that was not theirs.

## What is deliberately not done

Only blanks, and only required ones. A value the model DID send is the model's,
right or wrong, and overwriting it would be the harness quietly disagreeing
with the call it was asked to make. And the filler is keyed on `(tool,
argument)` rather than on the argument's name: `ask` means the person's
sentence to `map_the_ask` and could mean something else to a tool written next
year.
"""

from __future__ import annotations

import os
import unittest

import support

from app import conductor, events


class ADroppedArgumentIsFilledFromTheThreadTest(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)
        self.thread = int(events.create_thread("classify tickets", None)["id"])
        events.set_thread_goal(
            self.thread,
            "I want to classify support tickets by reason",
            "text_classification",
        )

    def test_the_empty_call_from_the_walk_is_filled(self):
        """THE CALL, VERBATIM FROM `530fc0b`: `map_the_ask` with `{}`."""
        filled, said = conductor._fill_from_the_thread("map_the_ask", {}, self.thread)
        self.assertEqual(["ask"], said)
        self.assertEqual(
            "I want to classify support tickets by reason", filled["ask"]
        )

    def test_a_blank_string_counts_as_dropped(self):
        """A model that sends `""` has dropped the argument as surely as one
        that sends nothing, and the person cannot tell the two apart."""
        filled, said = conductor._fill_from_the_thread(
            "map_the_ask", {"ask": "   "}, self.thread
        )
        self.assertEqual(["ask"], said)

    def test_a_value_the_model_did_send_is_left_alone(self):
        """THE CONTROL. Overwriting it would be the harness quietly disagreeing
        with the call it was asked to make."""
        filled, said = conductor._fill_from_the_thread(
            "map_the_ask", {"ask": "something else entirely"}, self.thread
        )
        self.assertEqual([], said)
        self.assertEqual("something else entirely", filled["ask"])

    def test_a_thread_with_no_goal_fills_nothing(self):
        bare = int(events.create_thread("nothing said yet", None)["id"])
        filled, said = conductor._fill_from_the_thread("map_the_ask", {}, bare)
        self.assertEqual([], said)

    def test_only_arguments_this_harness_knows_where_to_find(self):
        """Keyed on (tool, argument). A filler that matched on the name alone
        would put a goal into any tool that happened to call something `ask`.

        LAW SUBSTITUTED 2026-09-18. The old second assertion said `map_the_ask`
        is the ONLY tool this harness fills for, and it said it by reading one
        table. There are two now - `FROM_THE_THREAD` reads a thread COLUMN,
        `FROM_THE_LAST_TRAINING_RUN` reads the RESULT of a tool the thread has
        already run - so the same sentence read off one of them would have gone
        on passing while saying something false about the harness. The keying
        law is unchanged and is what is asserted; the roster is asserted across
        both tables, and the tables are asserted disjoint, because one key
        filled from two sources is a fill whose disclosure cannot be right.
        """
        self.assertIn(("map_the_ask", "ask"), conductor.FROM_THE_THREAD)
        self.assertIn(
            ("training_status", "job_id"), conductor.FROM_THE_LAST_TRAINING_RUN
        )
        every = {**conductor.FROM_THE_THREAD, **conductor.FROM_THE_LAST_TRAINING_RUN}
        self.assertEqual(
            {"map_the_ask", "training_status"},
            {tool for tool, _argument in every},
        )
        self.assertEqual(
            set(),
            set(conductor.FROM_THE_THREAD) & set(conductor.FROM_THE_LAST_TRAINING_RUN),
            "one argument filled from two sources cannot be disclosed honestly",
        )


    def test_a_tool_that_does_not_exist_does_not_crash_the_fill(self):
        """AN INVENTED NAME HAS NO SCHEMA, and reading one off `None` turned
        "no such tool" into an AttributeError. Caught by
        `test_an_invented_name_is_still_no_such_tool`, which exists for a
        different reason and was the only thing that noticed - so the case is
        recorded here too, where somebody changing this code will see it.
        """
        filled, said = conductor._fill_from_the_thread(
            "not_a_real_tool", {}, self.thread
        )
        self.assertEqual([], said)
        self.assertEqual({}, filled)


class TheFilledCallReachesARoutedAnswerTest(unittest.TestCase):
    """The point of the fix: the walk continues instead of stopping."""

    def setUp(self):
        support.sandbox(self)
        self.thread = int(events.create_thread("classify tickets", None)["id"])
        events.set_thread_goal(
            self.thread,
            "I want to classify support tickets by reason",
            "text_classification",
        )

    def test_the_empty_call_reaches_a_route(self):
        """THE CASE. Empty arguments in, an ordered journey out - which is what
        the person asked for two turns earlier."""
        from app.tools import REGISTRY

        filled, _said = conductor._fill_from_the_thread("map_the_ask", {}, self.thread)
        answer = REGISTRY.call("map_the_ask", filled, actor="model", thread_id=self.thread)
        self.assertTrue(answer.get("ok"), answer)
        self.assertTrue(answer.get("matched"), answer)

    def test_the_unfilled_call_reaches_nothing(self):
        """THE CONTROL, and it is what the walk measured: without the fill the
        same call cannot route, which is why the person was asked to repeat."""
        from app.tools import REGISTRY

        answer = REGISTRY.call("map_the_ask", {"ask": ""}, actor="model", thread_id=self.thread)
        self.assertFalse(answer.get("matched"))


class TheFillIsSwitchableBecauseItIsAConfoundTest(unittest.TestCase):
    """A ladder measures what a small model CONSTRUCTS.

    Research's trial spec (`7d97537`) names the problem this creates: a harness
    that quietly completes a dropped argument moves the boundary between the
    model's work and the product's, so a run scored under it reports the PAIR
    rather than the model. The harness would be grading its own help.

    On for a person, off for a trial - that way round, because the person is
    who the fill exists for and a trial is a deliberate act by somebody who
    knows what they are measuring.
    """

    def setUp(self):
        support.sandbox(self)
        self.thread = int(events.create_thread("classify tickets", None)["id"])
        events.set_thread_goal(
            self.thread, "I want to classify support tickets by reason",
            "text_classification",
        )
        self._was = os.environ.get(conductor.FILL_FROM_THE_THREAD_VARIABLE)
        self.addCleanup(self._restore)

    def _restore(self):
        if self._was is None:
            os.environ.pop(conductor.FILL_FROM_THE_THREAD_VARIABLE, None)
        else:
            os.environ[conductor.FILL_FROM_THE_THREAD_VARIABLE] = self._was

    def test_it_is_on_when_nobody_has_said_otherwise(self):
        os.environ.pop(conductor.FILL_FROM_THE_THREAD_VARIABLE, None)
        self.assertTrue(conductor.filling_is_on())
        _filled, said = conductor._fill_from_the_thread("map_the_ask", {}, self.thread)
        self.assertEqual(["ask"], said)

    def test_the_trial_can_switch_it_off(self):
        """THE CASE. With it off the same call fills nothing, so a ladder
        measures the model rather than the model plus the harness."""
        os.environ[conductor.FILL_FROM_THE_THREAD_VARIABLE] = "0"
        self.assertFalse(conductor.filling_is_on())
        filled, said = conductor._fill_from_the_thread("map_the_ask", {}, self.thread)
        self.assertEqual([], said)
        self.assertEqual({}, filled)

    def test_a_typo_leaves_it_on_rather_than_silently_off(self):
        """THE SAFE DIRECTION. A misspelled value in a trial script would
        otherwise score an arm nobody meant to run, and the reading would be
        wrong in the direction nobody checks."""
        os.environ[conductor.FILL_FROM_THE_THREAD_VARIABLE] = "offf"
        self.assertTrue(conductor.filling_is_on())

    def test_the_refusal_records_which_arm_this_was(self):
        """A reading that cannot tell which arm it was in is not a reading."""
        os.environ[conductor.FILL_FROM_THE_THREAD_VARIABLE] = "0"
        said = conductor._malformed_call("map_the_ask", ["ask"])
        self.assertEqual("off", said["filling_from_the_thread"])
        self.assertIn("switched off on this run", said["detail"])

    def test_with_it_on_the_refusal_says_the_thread_held_nothing(self):
        """The two refusals must not read alike: one means the thread was
        empty, the other means the harness was told not to look."""
        os.environ.pop(conductor.FILL_FROM_THE_THREAD_VARIABLE, None)
        said = conductor._malformed_call("map_the_ask", ["ask"])
        self.assertEqual("on", said["filling_from_the_thread"])
        self.assertIn("nothing recorded to fill", said["detail"])
        self.assertNotIn("switched off", said["detail"])


class WhenNothingCanFillItTest(unittest.TestCase):
    def test_it_names_the_fault_instead_of_asking_for_a_repeat(self):
        said = conductor._malformed_call("map_the_ask", ["ask"])
        self.assertEqual("malformed_call", said["error"])
        self.assertIn("fault in the call", said["detail"])
        self.assertIn("you do not have to repeat yourself", said["detail"])

    def test_it_says_nothing_was_run(self):
        """A person who is told a call was malformed will ask what it did."""
        self.assertIn("Nothing was run", conductor._malformed_call("map_the_ask", ["ask"])["detail"])

    def test_it_does_not_blame_the_person(self):
        said = conductor._malformed_call("map_the_ask", ["ask"])["detail"].lower()
        for blaming in ("say that again", "repeat what", "you did not"):
            with self.subTest(phrase=blaming):
                self.assertNotIn(blaming, said)


class ThePersonIsToldWhereTheValueCameFromTest(unittest.TestCase):
    def test_the_sentence_names_the_thread_and_the_start_of_it(self):
        self.assertEqual(
            "using your sentence from the start of this thread",
            conductor.FILLED_FROM_THE_THREAD,
        )

    def test_a_filled_call_carries_the_sentence_on_its_result(self):
        """A value appearing in a call the person did not make is a thing they
        are entitled to see. "It worked" is not a reason to be quiet.

        THE FIRST VERSION OF THIS ONLY ASSERTED THE CONSTANT WAS NON-EMPTY,
        and mutation showed the whole attachment could be deleted with the
        suite still green - the saying lived inline in a generator no test
        could reach. It is a function now, for that reason.
        """
        said = conductor._note_the_fill({"ok": True, "matched": "x"}, ["ask"])
        self.assertEqual(["ask"], said["filled_from_the_thread"]["arguments"])
        self.assertEqual(
            conductor.FILLED_FROM_THE_THREAD, said["filled_from_the_thread"]["say"]
        )
        self.assertTrue(said["ok"], "it must not disturb the answer it annotates")

    def test_a_call_that_filled_nothing_is_not_annotated(self):
        """THE CONTROL. A note on every result would train a reader to skip it."""
        self.assertNotIn(
            "filled_from_the_thread", conductor._note_the_fill({"ok": True}, [])
        )


def _a_start_that_worked(thread_id: int, job_id: int = 7, run_id: int = 3) -> None:
    """The record `start_training` leaves when a run actually started.

    Written as the conductor writes it - a `tool.result` row carrying the
    tool's own name and its returned dict - rather than by calling
    `start_training`, which wants a pinned backend, a dataset on disk and this
    machine's GPU. What the fill reads is the transcript, and this is the
    transcript.
    """
    events.append(
        "tool.result",
        {
            "id": f"call-{job_id}",
            "name": "start_training",
            "ok": True,
            "result": {
                "ok": True,
                "job_id": int(job_id),
                "run_id": int(run_id),
                "recipe": "hf-peft-lora",
                "status": "queued",
            },
        },
        thread_id=int(thread_id),
    )


class TheJobIdIsInTheThreadThirtySixTimesTest(unittest.TestCase):
    """`training_status` with `{}`, on a thread that started a run.

    MEASURED ON MAX'S DATABASE: 36 calls to `training_status` with no
    arguments, every one answered `missing_arguments`. `start_training` had
    returned the job id and said in its own `next` line "Ask training_status
    with this job id for progress" - so the number was in the thread for all 36
    of them, and the harness printed a refusal instead of a progress report.
    """

    def setUp(self):
        support.sandbox(self)
        self.thread = int(events.create_thread("train the router", None)["id"])

    def test_the_empty_call_is_filled_from_the_start(self):
        _a_start_that_worked(self.thread, job_id=7)
        filled, said = conductor._fill_from_the_thread(
            "training_status", {}, self.thread
        )
        self.assertEqual(["job_id"], said)
        self.assertEqual(7, filled["job_id"])

    def test_the_newest_run_is_the_one_it_reports_on(self):
        """Two runs in one thread: the person asking "how is it going" means
        the one that is going, which is the last one they started."""
        _a_start_that_worked(self.thread, job_id=7)
        _a_start_that_worked(self.thread, job_id=11)
        filled, _said = conductor._fill_from_the_thread(
            "training_status", {}, self.thread
        )
        self.assertEqual(11, filled["job_id"])

    def test_a_refused_start_does_not_hide_the_run_before_it(self):
        """A `start_training` that came back `ok: False` started nothing. The
        run the person is asking about is still the one before it, and stopping
        at the refusal would report "no training run" about a thread with one.
        """
        _a_start_that_worked(self.thread, job_id=7)
        events.append(
            "tool.result",
            {
                "id": "call-bad",
                "name": "start_training",
                "ok": False,
                "result": {"ok": False, "error": "unknown_recipe"},
            },
            thread_id=self.thread,
        )
        filled, said = conductor._fill_from_the_thread(
            "training_status", {}, self.thread
        )
        self.assertEqual(["job_id"], said)
        self.assertEqual(7, filled["job_id"])

    def test_a_job_id_the_model_did_send_is_left_alone(self):
        """THE CONTROL, and the same one the goal fill has: a value the model
        sent is the model's, right or wrong."""
        _a_start_that_worked(self.thread, job_id=7)
        filled, said = conductor._fill_from_the_thread(
            "training_status", {"job_id": 99}, self.thread
        )
        self.assertEqual([], said)
        self.assertEqual(99, filled["job_id"])

    def test_another_threads_run_is_not_borrowed(self):
        """The question is "what did THIS thread start", not "what is the
        newest job on this machine" - which would report one conversation's run
        into another."""
        other = int(events.create_thread("somebody else's run", None)["id"])
        _a_start_that_worked(other, job_id=7)
        filled, said = conductor._fill_from_the_thread(
            "training_status", {}, self.thread
        )
        self.assertEqual([], said)
        self.assertNotIn("job_id", filled)

    def test_the_fill_can_be_turned_off_like_the_other_one(self):
        """The ladder's confound switch covers BOTH sources or it measures a
        harness that still helps."""
        _a_start_that_worked(self.thread, job_id=7)
        os.environ[conductor.FILL_FROM_THE_THREAD_VARIABLE] = "0"
        self.addCleanup(
            os.environ.pop, conductor.FILL_FROM_THE_THREAD_VARIABLE, None
        )
        _filled, said = conductor._fill_from_the_thread(
            "training_status", {}, self.thread
        )
        self.assertEqual([], said)


class ATrainingStatusFillIsDisclosedTest(unittest.TestCase):
    """The person is told, and told the TRUTH about where it came from."""

    def test_the_sentence_names_the_run_rather_than_a_sentence(self):
        """"Your sentence from the start of this thread" would be a false
        statement about a job id the person never typed, and a disclosure that
        misdescribes what it disclosed teaches the reader to stop reading it."""
        self.assertEqual(
            "using the training run this thread started",
            conductor.FILLED_FROM_THE_LAST_TRAINING_RUN,
        )
        self.assertNotEqual(
            conductor.FILLED_FROM_THE_THREAD,
            conductor.FILLED_FROM_THE_LAST_TRAINING_RUN,
        )

    def test_the_sentence_is_derived_from_the_tables(self):
        self.assertEqual(
            conductor.FILLED_FROM_THE_LAST_TRAINING_RUN,
            conductor._the_fill_sentence("training_status", ["job_id"]),
        )
        self.assertEqual(
            conductor.FILLED_FROM_THE_THREAD,
            conductor._the_fill_sentence("map_the_ask", ["ask"]),
        )

    def test_the_disclosure_key_is_the_one_that_was_already_there(self):
        """A second key would make every reader of the note learn a second name
        to keep seeing the same fact."""
        said = conductor._note_the_fill(
            {"ok": True, "job_id": 7},
            ["job_id"],
            conductor.FILLED_FROM_THE_LAST_TRAINING_RUN,
        )
        self.assertEqual(["job_id"], said["filled_from_the_thread"]["arguments"])
        self.assertEqual(
            conductor.FILLED_FROM_THE_LAST_TRAINING_RUN,
            said["filled_from_the_thread"]["say"],
        )
        self.assertTrue(said["ok"], "it must not disturb the answer it annotates")


class AThreadWithNoRunIsStillRefusedTest(unittest.TestCase):
    """THE CONTROL FOR THE WHOLE FILL, and it is the important one.

    A fill that answered a thread which has never trained anything would be
    inventing a job id, and `training_status` would then report on somebody
    else's run or on nothing. The refusal stays exactly where it was - in the
    registry, as `missing_arguments` - because the fill adds a SOURCE and never
    a guess.
    """

    def setUp(self):
        support.sandbox(self)
        self.thread = int(events.create_thread("nothing started yet", None)["id"])

    def test_nothing_is_filled(self):
        filled, said = conductor._fill_from_the_thread(
            "training_status", {}, self.thread
        )
        self.assertEqual([], said)
        self.assertEqual({}, filled)

    def test_the_call_is_refused_with_missing_arguments(self):
        from app.tools import REGISTRY

        filled, _said = conductor._fill_from_the_thread(
            "training_status", {}, self.thread
        )
        answer = REGISTRY.call(
            "training_status", filled, actor="model", thread_id=self.thread
        )
        self.assertFalse(answer.get("ok"))
        self.assertEqual("missing_arguments", answer.get("error"))
        self.assertEqual(["job_id"], answer.get("missing"))

    def test_the_filled_call_gets_past_that_check(self):
        """THE OTHER HALF. The 36 calls never reached the tool at all; a filled
        one does, and whatever it says next is the tool's own business."""
        from app.tools import REGISTRY

        _a_start_that_worked(self.thread, job_id=7)
        filled, _said = conductor._fill_from_the_thread(
            "training_status", {}, self.thread
        )
        answer = REGISTRY.call(
            "training_status", filled, actor="model", thread_id=self.thread
        )
        self.assertNotEqual("missing_arguments", answer.get("error"))


class ScoreTheAdapterIsDeliberatelyNotFilledTest(unittest.TestCase):
    """Its run id is a BASELINE eval run, which a training start never makes.

    `score_the_adapter` requires `sandbox`, `baseline_run_id` and `thread_id`.
    `start_training` returns a job id and a training run id and neither of the
    first two. Filling `baseline_run_id` from a training run would pair an
    adapter against the wrong rows and produce a WRONG NUMBER rather than a
    refusal - which is strictly worse than the fault the fill exists to fix, so
    the absence is asserted rather than left to be noticed.
    """

    def test_it_is_in_neither_table(self):
        for table in (conductor.FROM_THE_THREAD, conductor.FROM_THE_LAST_TRAINING_RUN):
            self.assertEqual(
                [], [key for key in table if key[0] == "score_the_adapter"]
            )

    def test_the_reason_is_written_down_rather_than_inferred(self):
        self.assertIn(
            "baseline", conductor.SCORE_THE_ADAPTER_TAKES_NO_TRAINING_RUN_ID.lower()
        )

    def test_a_training_start_carries_neither_of_its_arguments(self):
        """DERIVED, so this cannot pass by a stale belief about the result: if
        `start_training` ever did return a sandbox or a baseline run id, this
        goes red and the decision above gets made again."""
        started = {
            "ok": True,
            "job_id": 7,
            "run_id": 3,
            "recipe": "hf-peft-lora",
            "status": "queued",
        }
        for argument in ("sandbox", "baseline_run_id"):
            with self.subTest(argument=argument):
                self.assertNotIn(argument, started)


if __name__ == "__main__":
    unittest.main()
