"""A push happens on the gate's exit code and on nothing else.

MEASURED BY A COMMIT THAT SHOULD NOT EXIST. On 2026-09-05, `39d36e5` reached
main on a red gate from this command:

    grep -E "GATE IS|GATE EXIT" gate70.txt && git push origin main

The grep succeeded — it found the lines — so the push ran. It was chained to
grep's exit status rather than to the gate's verdict, which was `GATE EXIT=1`.

These tests hold the decision, not the wording: a non-zero code refuses, zero
pushes, and reading output instead of the code cannot creep back in because
nothing here looks at output at all.
"""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

import support

pusher = support.import_file(
    "push_if_green", support.REPO_ROOT / "scripts" / "push_if_green.py"
)


#: A commit that looks like one. `push_if_green` checks the shape before it
#: will publish anything, so a fixture that hands back "abc" is a fixture that
#: cannot exercise the push at all.
A_GATED_SHA = "d5326599ee8662465acfce4cb4c51a0d323d8b0a"


def _is_npm(command) -> bool:
    """Is this the frontend check? Asked on the BASENAME, on both platforms.

    `push_if_green.the_npm_command` resolves npm through `shutil.which`, so on
    Windows the recorded argv[0] is `C:\\Program Files\\nodejs\\npm.cmd` and on
    a POSIX machine it is `/usr/bin/npm`. Splitting on one separator would make
    this fake correct on one of the two and silently wrong on the other, which
    is the shape of a test that passes for the wrong reason.
    """
    head = str(command[0]).replace(chr(92), "/").rsplit("/", 1)[-1].lower()
    return head.startswith("npm")


class AFakeRun:
    """Records the commands and returns the codes it was given, in order.

    `git rev-parse HEAD` IS ANSWERED, NOT COUNTED. The step asks git which
    object it is about to publish, and that question is not one of the outcomes
    a test is setting up - consuming a code for it would mean every existing
    case had to be rewritten to pad for a call it does not care about, and the
    padding would be the thing that broke next time.

    LAW SUBSTITUTED 2026-09-18: `npm` IS ANSWERED THE SAME WAY, for the same
    reason and by a stronger argument. The frontend checks arrived between the
    green gate and the push, so on any checkout with `frontend/node_modules`
    installed - which is every developer machine - two npm calls now land in
    the middle of every case here and would have eaten the codes meant for
    `git push`. They answer `frontend` (green by default) and stay out of
    `decisions`, and a case that is ABOUT them passes a code for them or lives
    in `tests/test_the_push_checks_the_frontend_too.py`, which is where that
    law is held.
    """

    def __init__(self, *codes, head=A_GATED_SHA, frontend=0):
        self.codes = list(codes)
        self.commands = []
        self.head = head
        self.frontend = int(frontend)

    def __call__(self, command, *args, **kwargs):
        self.commands.append(list(command))
        if _is_npm(command):
            class Checked:
                returncode = self.frontend

            return Checked()
        if "status" in command and command[0] == "git":
            #: ANSWERED, NOT COUNTED, for the reason `rev-parse` is below: the
            #: step asks git whether this tree matches HEAD before it will
            #: spend a suite, and that question is not one of the outcomes a
            #: case is setting up. A clean tree is the default because every
            #: case here is about what happens AFTER that check passes; the
            #: dirty arm has its own fake.
            class Clean:
                returncode = 0
                stdout = ""

            return Clean()
        if list(command[:2]) == ["git", "rev-parse"]:
            class Resolved:
                returncode = 0 if self.head else 128
                stdout = self.head + chr(10) if self.head else ""

            return Resolved()

        class Done:
            returncode = self.codes.pop(0) if self.codes else 0

        return Done()

    @property
    def decisions(self):
        """Every command but the question the step asks git about its own HEAD.

         stays complete - a recorder that hides a call it really made
        is a recorder that can be believed about the wrong thing. These tests
        are about what the step DECIDES: gate, push, fetch, rebase. Asking git
        which object it is holding is not a decision, and counting it would
        make every case here read as one call further along than it is.
        """
        return [
            c for c in self.commands
            if c[:2] != ['git', 'rev-parse']
            and not (c[0] == 'git' and 'status' in c)
            and not _is_npm(c)
        ]


class AFakeLock:
    """The machine lock, taken and released without touching the real file.

    EVERY TEST HERE PASSES ONE. Without it these would take the lock a real
    gate uses, from inside a suite that a real gate is running - which is the
    collision the lock exists to prevent, caused by its own tests.

    AND EVERY TEST HERE NOW PASSES `push_lock=False` FOR THE SAME REASON,
    which was learned the expensive way on 2026-09-10. `one_push_at_a_time`
    arrived keyed on the remote ref and taken BEFORE the gate - so these cases,
    which passed a fake machine lock and said nothing about the new one,
    reached for the REAL push lock from inside a suite whose own runner was
    holding it. The gate did not fail; it WAITED, for an hour, printing "still
    waiting for pid 21908" - its own parent - until the run was killed and
    origin had moved twice.

    The warning above was already written, about the other lock, in this
    docstring. Adding a second lock without extending it is how a hazard
    somebody already documented gets committed again.
    """

    DEFAULT_TIMEOUT_SECONDS = 1

    def __init__(self, grant=True):
        self.grant = grant
        self.taken = 0
        self.released = 0

    def acquire(self, timeout, command):
        self.taken += 1
        return self.grant

    def release(self):
        self.released += 1


class ANonZeroGateRefusesTest(unittest.TestCase):
    def test_a_failing_test_refuses_the_push(self):
        run = AFakeRun(1)
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = pusher.push_if_green(["origin", "main"], run=run, lock=AFakeLock(), push_lock=False)
        self.assertEqual(code, 1)
        self.assertEqual(len(run.decisions), 1, "it pushed anyway")
        self.assertNotIn("git", run.decisions[0][0].lower().rsplit("\\", 1)[-1][:3])
        self.assertIn("PUSH REFUSED", err.getvalue())

    def test_an_incomplete_run_refuses_the_push(self):
        """Exit 2 is the gate saying the run does not describe the tree — a
        count mismatch, an unimported module, or another lane holding the
        lock. That is not 'nearly green'."""
        run = AFakeRun(2)
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = pusher.push_if_green(["origin", "main"], run=run, lock=AFakeLock(), push_lock=False)
        self.assertEqual(code, 2)
        self.assertEqual(len(run.decisions), 1)
        self.assertIn("does not say what the tree does", err.getvalue())

    def test_an_exit_code_with_no_name_still_refuses(self):
        """A gate that grew a new code must not fall through to a push."""
        run = AFakeRun(97)
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = pusher.push_if_green(["origin", "main"], run=run, lock=AFakeLock(), push_lock=False)
        self.assertEqual(code, 97)
        self.assertEqual(len(run.decisions), 1)
        self.assertIn("no name for", err.getvalue())


class AGreenGatePushesTest(unittest.TestCase):
    def test_it_pushes_the_object_it_gated_and_not_the_name_it_was_given(self):
        """THIS ASSERTED `["git", "push", "origin", "main"]` UNTIL 2026-09-10.

        A gate certifies a tree; `origin main` publishes a NAME. They are the
        same thing only while nothing moves the name, and that night three
        commits landed under one sixteen-minute run in a shared checkout. From
        a worktree it is worse: the branch here is not `main`, so `main` is a
        name the run never touched.

        The destination stays the caller's. Only the source is replaced, by the
        object git named between the gate and the push.
        """
        run = AFakeRun(0, 0)
        with redirect_stdout(io.StringIO()):
            code = pusher.push_if_green(["origin", "main"], run=run, lock=AFakeLock(), push_lock=False)
        self.assertEqual(code, 0)
        pushes = [c for c in run.decisions if c[:2] == ["git", "push"]]
        self.assertEqual(
            pushes, [["git", "push", "origin", f"{A_GATED_SHA}:refs/heads/main"]]
        )

    def test_it_refuses_rather_than_push_a_ref_when_git_will_not_name_head(self):
        """CANNOT DECIDE IS NOT UNCHANGED. With no object to publish the only
        thing left is the name, and publishing the name is the defect."""
        run = AFakeRun(0, 0, head="")
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = pusher.push_if_green(["origin", "main"], run=run, lock=AFakeLock(), push_lock=False)
        self.assertEqual(code, 1)
        self.assertEqual([c for c in run.decisions if c[:2] == ["git", "push"]], [])
        self.assertIn("rev-parse", err.getvalue())

    def test_a_push_that_failed_for_its_own_reasons_is_not_rebased_over(self):
        """WRITTEN BEFORE THE RETRY EXISTED, AND IT CAUGHT THE RETRY. Exit 128
        is no credentials, no network, a bad remote - none of which a
        thirteen-minute rebase and re-gate would fix, and answering one by
        rewriting a branch is worse than reporting it. Only exit 1, a rejected
        ref, is worth the retry."""
        run = AFakeRun(0, 128)
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = pusher.push_if_green(["origin", "main"], run=run, lock=AFakeLock(), push_lock=False)
        self.assertEqual(code, 128)
        self.assertEqual(len(run.decisions), 2, "it rebased over an unrelated failure")
        self.assertIn("not a rejected ref", err.getvalue())

    def test_dry_run_gates_and_does_not_push(self):
        run = AFakeRun(0)
        out = io.StringIO()
        with redirect_stdout(out):
            code = pusher.push_if_green(["origin", "main"], run=run, dry_run=True, lock=AFakeLock(), push_lock=False)
        self.assertEqual(code, 0)
        self.assertEqual(len(run.decisions), 1)
        self.assertIn("would run", out.getvalue())


class ADirtyTreeCannotCertifyTest(unittest.TestCase):
    """The suite reads the WORKING TREE; the push publishes HEAD.

    MEASURED ON THIS SCRIPT'S OWN AUTHOR, 2026-09-10. A `git commit --amend`
    with no pathspec kept the old content and replaced only the message, so
    HEAD described a feature it did not contain while the working tree had it.
    The gate read the working tree, reported GREEN on 5,036 tests, and the
    object about to be published was missing the very change that run had
    certified. Only a non-fast-forward rejection stopped it landing: it would
    have pushed a green lie.

    `ThePublishedObjectIsTheCertifiedObjectTest` above closes the other half -
    that what is pushed is the object that was gated. This closes the half
    underneath it: that the object gated is the one that was TESTED.

    `scripts/gate.py` cannot catch this and is right not to. It fingerprints
    tracked files before and after to see whether the tree MOVED under the run,
    which is a different question from whether it matched HEAD when the run
    began. Publishing an object is what makes the second question matter.
    """

    class ARunWithADirtyTree(AFakeRun):
        def __call__(self, command, *args, **kwargs):
            if list(command[:2]) == ["git", "-C"] and "status" in command:
                self.commands.append(list(command))

                class Said:
                    returncode = 0
                    stdout = " M app/conductor.py" + chr(10) + " M tests/x.py" + chr(10)

                return Said()
            return super().__call__(command, *args, **kwargs)

    def test_it_refuses_before_spending_a_suite(self):
        run = self.ARunWithADirtyTree(0, 0)
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = pusher.push_if_green(
                ["origin", "main"], run=run, lock=AFakeLock(), push_lock=False
            )
        self.assertEqual(2, code)
        self.assertNotIn("gate", [c[0] for c in run.decisions], repr(run.decisions))
        self.assertIn("not the same thing right now", err.getvalue())

    def test_it_names_the_files(self):
        run = self.ARunWithADirtyTree(0, 0)
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            pusher.push_if_green(
                ["origin", "main"], run=run, lock=AFakeLock(), push_lock=False
            )
        self.assertIn("app/conductor.py", err.getvalue())

    def test_untracked_files_are_not_dirt(self):
        """Every lane leaves scratch files in a checkout, and refusing on those
        would mean never pushing. `--untracked-files=no` is asked for."""
        run = self.ARunWithADirtyTree(0, 0)
        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            pusher.push_if_green(
                ["origin", "main"], run=run, lock=AFakeLock(), push_lock=False
            )
        asked = [c for c in run.commands if "status" in c][0]
        self.assertIn("--untracked-files=no", asked)

    def test_a_clean_tree_gates_as_before(self):
        """THE CONTROL. If this went red the check would have stopped every
        push on the machine rather than the wrong ones."""
        run = AFakeRun(0, 0)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = pusher.push_if_green(
                ["origin", "main"], run=run, lock=AFakeLock(), push_lock=False
            )
        self.assertEqual(0, code)


class ThePublishedObjectIsTheCertifiedObjectTest(unittest.TestCase):
    """A gate certifies a TREE; `git push origin main` publishes a NAME.

    MEASURED 2026-09-10 in the shared checkout: three commits landed under one
    sixteen-minute run - `b7cc2af` 03:52:00, `fbe337e` 03:57:35, `38e6e63`
    03:57:52 - while the certificate was being written for `2531252`. Neither
    guard in `scripts/gate.py` can see it: the tracked-files fingerprint watches
    the files in THIS working tree and `refs/heads/main` is not one of them, and
    the HEAD check watches THIS checkout's HEAD, which a push to `main` from a
    worktree does not touch either.
    """

    A_LATER_COMMIT = "1111111111111111111111111111111111111111"

    def test_main_moving_between_gate_and_push_does_not_change_what_is_published(self):
        """THE CASE, and it is stated as a property rather than a refusal.

        The instruction was "`main` moves between gate and push and the push
        does not happen". This does something stronger and simpler: the push
        never names `main` as its SOURCE, so a `main` that moved is not a thing
        the push can publish. There is nothing to detect and nothing to refuse -
        the race is gone rather than caught, and a check that is not there
        cannot later be widened by somebody who finds it inconvenient.

        If the remote's `main` has moved on, this push is rejected as a
        non-fast-forward, which is the correct outcome and the one the retry
        below already knows how to answer.
        """
        run = AFakeRun(0, 0)
        with redirect_stdout(io.StringIO()):
            pusher.push_if_green(["origin", "main"], run=run, lock=AFakeLock(), push_lock=False)
        pushed = [c for c in run.decisions if c[:2] == ["git", "push"]][0]
        self.assertEqual(pushed[-1], f"{A_GATED_SHA}:refs/heads/main")
        self.assertNotIn("main", pushed[-1].split(":")[0],
                         "the source is a name, so it can point elsewhere")

    def test_the_destination_is_the_callers_and_only_the_source_is_replaced(self):
        """A caller naming `branch:main` is naming a destination. Taking that
        away would break the very route this lane pushed by tonight."""
        run = AFakeRun(0, 0)
        with redirect_stdout(io.StringIO()):
            pusher.push_if_green(["origin", "intake/night:main"], run=run, lock=AFakeLock(), push_lock=False)
        pushed = [c for c in run.decisions if c[:2] == ["git", "push"]][0]
        self.assertEqual(pushed[-1], f"{A_GATED_SHA}:refs/heads/main")

    def test_a_retry_from_a_branch_that_is_not_main_publishes_what_it_rebased(self):
        """THE SECOND INSTANCE, in the recovery rather than the push.

        `push_if_green` rebases whatever the process's cwd has checked out -
        line 234, no `-C`. From a worktree on `intake/night` that rebases
        `intake/night`, and the old code then pushed the ref `main`, which the
        rebase never moved. So the second attempt was refused for exactly the
        same reason as the first, after spending another full suite finding out.

        Now the object is re-derived each attempt, so the retry publishes the
        commit the rebase produced.
        """

        class ARunWhereTheRebaseMovesHead(AFakeRun):
            def __call__(self, command, *args, **kwargs):
                done = super().__call__(command, *args, **kwargs)
                if list(command[:2]) == ["git", "rebase"]:
                    self.head = ThePublishedObjectIsTheCertifiedObjectTest.A_LATER_COMMIT
                return done

        #: gate green, push rejected, fetch, rebase, gate green, push green.
        run = ARunWhereTheRebaseMovesHead(0, pusher.A_REJECTED_REF, 0, 0, 0, 0)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            pusher.push_if_green(["origin", "main"], run=run, lock=AFakeLock(), push_lock=False)
        pushes = [c for c in run.decisions if c[:2] == ["git", "push"]]
        self.assertEqual(len(pushes), 2, "it did not retry")
        self.assertEqual(pushes[0][-1], f"{A_GATED_SHA}:refs/heads/main")
        self.assertEqual(
            pushes[1][-1], f"{self.A_LATER_COMMIT}:refs/heads/main",
            "the retry published something the rebase did not produce",
        )

    def test_arguments_it_cannot_place_are_refused_rather_than_passed_through(self):
        """Passing them through would mean pushing a ref again, which is the
        one outcome this class exists to make impossible."""
        run = AFakeRun(0, 0)
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = pusher.push_if_green(["origin", "main", "--force"], run=run, lock=AFakeLock(), push_lock=False)
        self.assertEqual(code, 1)
        self.assertEqual([c for c in run.decisions if c[:2] == ["git", "push"]], [])
        self.assertIn("OBJECT it gated", err.getvalue())


class ItNeverDecidesOnOutputTest(unittest.TestCase):
    """THE FAILURE THIS FILE EXISTS FOR. The old step searched the gate's
    output for a phrase, and 'GATE IS RED' matches a search for 'GATE IS' as
    well as a green line does."""

    def test_a_red_gate_that_prints_the_word_green_still_refuses(self):
        #: IT MUST STILL ANSWER `rev-parse`. The first version of this returned
        #: 1 for every command, including the question about HEAD - so the step
        #: refused before the gate ever ran, and this case passed on code 1 for
        #: a reason that had nothing to do with believing output.
        class ARunThatPrintsGreenAndFails(AFakeRun):
            def __call__(self, command, *args, **kwargs):
                done = super().__call__(command, *args, **kwargs)
                if list(command[:2]) != ["git", "rev-parse"]:
                    print("GATE IS GREEN: 4106 of 4106")  # a lie in the output
                return done

        run = ARunThatPrintsGreenAndFails(1)
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = pusher.push_if_green(["origin", "main"], run=run, lock=AFakeLock(), push_lock=False)
        self.assertEqual(code, 1)
        self.assertEqual(len(run.decisions), 1, "it believed the output")


class TheLockIsHeldAcrossTheGateAndThePushTest(unittest.TestCase):
    """CHANGED 2026-09-05, and the earlier version of this class said the
    opposite in its name: `TheLockIsNeverSkippedForYou`.

    It asserted that `--no-lock` was never passed to the gate. That was right
    when the pusher took no lock of its own. It is wrong now: the pusher holds
    the machine lock from the START of the gate through the push, so the gate
    would be waiting on a lock its own parent holds, which never returns.

    The guarantee is stronger, not weaker. Main cannot move between a green
    verdict and the push that follows it, because every lane's gate takes the
    same lock and a lane that arrives waits.
    """

    def test_the_lock_is_taken_before_the_gate_and_released_after(self):
        lock, run = AFakeLock(), AFakeRun(0, 0)
        with redirect_stdout(io.StringIO()):
            pusher.push_if_green(["origin", "main"], run=run, lock=lock, push_lock=False)
        self.assertEqual((lock.taken, lock.released), (1, 1))

    def test_the_gate_is_told_not_to_take_the_lock_this_process_holds(self):
        lock, run = AFakeLock(), AFakeRun(0, 0)
        with redirect_stdout(io.StringIO()):
            pusher.push_if_green(["origin", "main"], run=run, lock=lock, push_lock=False)
        self.assertIn("--no-lock", run.decisions[0])
        self.assertNotIn("--no-lock", run.decisions[1], "it reached git")

    def test_without_a_lock_module_the_gate_takes_its_own(self):
        """The fallback must not silently gate unlocked: with no lock here, the
        gate keeps the one it always had.

        THIS TEST HUNG THE SUITE ONCE. Its first version passed `lock=None`,
        which asks the script to load the REAL module and wait up to half an
        hour on the actual machine lock - from inside a suite a real gate was
        running. A falsy lock says "there is none" without touching it.
        """
        run = AFakeRun(0, 0)
        with redirect_stdout(io.StringIO()):
            pusher.push_if_green(["origin", "main"], run=run, lock=False, push_lock=False)
        self.assertNotIn("--no-lock", run.decisions[0], "it gated unlocked")

    def test_a_lock_it_cannot_take_refuses_before_gating(self):
        lock, run = AFakeLock(grant=False), AFakeRun(0, 0)
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = pusher.push_if_green(["origin", "main"], run=run, lock=lock, push_lock=False)
        self.assertEqual(code, 2)
        self.assertEqual(run.decisions, [], "it gated anyway")
        self.assertIn("Nothing was gated", err.getvalue())

    def test_the_lock_is_released_even_when_the_gate_is_red(self):
        lock, run = AFakeLock(), AFakeRun(1)
        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            pusher.push_if_green(["origin", "main"], run=run, lock=lock, push_lock=False)
        self.assertEqual(lock.released, 1, "the lock was left held")


class ItRebasesAndRegatesExactlyOnceTest(unittest.TestCase):
    """If origin moves even under the lock, something pushed without gating -
    a worktree, or a lane not using this step. One automatic recovery, then a
    person, because a loop spends the machine without converging."""

    def test_a_rejected_push_rebases_regates_and_pushes_once(self):
        # gate green, push rejected, fetch ok, rebase ok, gate green, push ok
        lock, run = AFakeLock(), AFakeRun(0, 1, 0, 0, 0, 0)
        with redirect_stdout(io.StringIO()):
            code = pusher.push_if_green(["origin", "main"], run=run, lock=lock, push_lock=False)
        self.assertEqual(code, 0)
        kinds = [c[0] if c[0] in ("git",) else "gate" for c in run.decisions]
        self.assertEqual(kinds, ["gate", "git", "git", "git", "gate", "git"])
        self.assertEqual(run.decisions[2][:2], ["git", "fetch"])
        self.assertEqual(run.decisions[3][:2], ["git", "rebase"])

    def test_a_second_rejection_refuses_for_a_person(self):
        lock, run = AFakeRun, None
        lock, run = AFakeLock(), AFakeRun(0, 1, 0, 0, 0, 1)
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = pusher.push_if_green(["origin", "main"], run=run, lock=lock, push_lock=False)
        self.assertEqual(code, 1)
        self.assertIn("did not gate", err.getvalue())
        self.assertIn("spends the machine", err.getvalue())

    def test_a_failed_rebase_refuses_rather_than_gating_nothing(self):
        lock, run = AFakeLock(), AFakeRun(0, 1, 0, 1)
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = pusher.push_if_green(["origin", "main"], run=run, lock=lock, push_lock=False)
        self.assertEqual(code, 1)
        self.assertIn("no tree to gate", err.getvalue().replace("there is ", ""))

    def test_the_retry_can_be_turned_off(self):
        lock, run = AFakeLock(), AFakeRun(0, 1)
        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            code = pusher.push_if_green(
                ["origin", "main"], run=run, lock=lock, push_lock=False,
                rebase_and_retry_once=False
            )
        self.assertEqual(code, 1)
        self.assertEqual(len(run.decisions), 2, "it retried anyway")

#: A second commit that looks like one, for the case where HEAD moves out from
#: under a running suite.
ANOTHER_SHA = "0f4c1b2e7a9d8c6f5e3b1a0d9c8b7a6f5e4d3c2b"


class ATreeThatMovedUnderTheSuiteTest(unittest.TestCase):
    """The tree the suite READ must be the tree the push PUBLISHES.

    ## The hole

    `what_is_uncommitted` is asked once, before the gate. The gate then reads
    this working tree for eight to twenty minutes and NOTHING LOOKS AGAIN. A
    tracked file written inside that window is read by the suite and is not in
    the object the push publishes, so a green verdict certifies a tree nobody
    committed. `gated` is resolved before the gate too, so a commit landing in
    this checkout while the suite runs leaves the push publishing an object the
    suite only partly ran on.

    ## Measured, twice, by this lane, in one night

    At 04:05 on 2026-09-11 this lane voided a live gate by committing under it,
    eleven minutes after arguing for the hook that exists to stop exactly that.
    At 02:22 it began writing a test file into a worktree whose gate was queued
    and stopped only because a person read the log first. Both times the thing
    that caught it was somebody remembering. A check that works when somebody
    remembers is not a check, and the second one nearly went the other way.

    ## Why refusing, and not re-gating

    The verdict in hand describes a tree that no longer exists, so it cannot
    authorise anything. Re-running would spend another twenty minutes on a tree
    the same lane can dirty again while it runs. Naming what moved hands the
    decision to whoever moved it.
    """

    class ARunDirtiedByItsOwnSuite(AFakeRun):
        """Clean when the step looks, dirty while the suite reads.

        This is the shape of the accident rather than a contrivance: nobody
        dirties a tree before a gate they are about to start. They dirty it
        while it is running, because from outside nothing says it is.
        """

        def __init__(self, *codes, dirt=" M app/asking.py", **kwargs):
            super().__init__(*codes, **kwargs)
            self.dirt = dirt
            self.the_suite_has_run = False

        def __call__(self, command, *args, **kwargs):
            if any("gate.py" in str(part) for part in command):
                answer = super().__call__(command, *args, **kwargs)
                self.the_suite_has_run = True
                return answer
            if command[0] == "git" and "status" in command and self.the_suite_has_run:
                self.commands.append(list(command))
                dirt = self.dirt

                class Dirty:
                    returncode = 0
                    stdout = dirt + chr(10)

                return Dirty()
            return super().__call__(command, *args, **kwargs)

    class ARunWhoseHeadMovesUnderTheSuite(AFakeRun):
        """A commit lands in this checkout while the suite is reading it."""

        def __call__(self, command, *args, **kwargs):
            answer = super().__call__(command, *args, **kwargs)
            if any("gate.py" in str(part) for part in command):
                self.head = ANOTHER_SHA
            return answer

    def _drive(self, run):
        said = io.StringIO()
        with redirect_stderr(said), redirect_stdout(io.StringIO()):
            code = pusher.push_if_green(
                ["origin", "main"], run=run, lock=AFakeLock(), push_lock=False
            )
        return code, said.getvalue()

    def test_a_file_written_during_the_suite_refuses_the_push(self):
        run = self.ARunDirtiedByItsOwnSuite(0, 0)
        code, _ = self._drive(run)
        self.assertEqual(2, code)
        self.assertEqual(
            [], [c for c in run.decisions if c[:2] == ["git", "push"]],
            "a tree that moved under the suite was published anyway",
        )

    def test_the_refusal_names_what_moved(self):
        """A refusal that will not say which file is a refusal somebody has to
        go and hunt the reason for, at the end of a twenty-minute wait."""
        _, said = self._drive(self.ARunDirtiedByItsOwnSuite(0, 0))
        self.assertIn("app/asking.py", said)

    def test_head_moving_during_the_suite_refuses_the_push(self):
        """The other half, and it is not covered by the tree check: a commit
        leaves the tree clean. The suite still read files that are not the
        object `gated` names."""
        run = self.ARunWhoseHeadMovesUnderTheSuite(0, 0)
        code, said = self._drive(run)
        self.assertEqual(2, code)
        self.assertIn(ANOTHER_SHA, said)
        self.assertEqual([], [c for c in run.decisions if c[:2] == ["git", "push"]])

    def test_an_untracked_file_appearing_is_still_not_dirt(self):
        """THE SAME RULE AS THE FIRST CHECK, and it has to be the same one.
        Every lane leaves scratch files in a checkout; a second check with a
        stricter definition would refuse pushes the first one allowed, which is
        a rule nobody could hold in their head.

        WHAT THIS CASE DOES NOT COVER, said here rather than assumed. The fake
        answers whatever it was told and never reads git's arguments, so
        deleting `--untracked-files=no` from `what_is_uncommitted` does not
        fail this test - it fails `test_untracked_files_are_not_dirt` above,
        which is the case that pins the FLAG. This one pins the RULE: when
        nothing tracked has changed, the second look lets the push through.
        Measured by mutation, both ways, 2026-09-11."""
        code, _ = self._drive(self.ARunDirtiedByItsOwnSuite(0, 0, dirt=""))
        self.assertEqual(0, code)

    def test_a_tree_that_stays_still_pushes_as_before(self):
        """THE CONTROL. A second look that refused the ordinary case would be
        worse than no second look at all."""
        run = AFakeRun(0, 0)
        code, _ = self._drive(run)
        self.assertEqual(0, code)
        self.assertIn(
            ["git", "push", "origin", f"{A_GATED_SHA}:refs/heads/main"],
            run.decisions,
        )

if __name__ == "__main__":
    unittest.main()
