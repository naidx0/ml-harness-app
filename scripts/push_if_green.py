"""Push only when the gate exited zero, holding the lock across both.

WHY THIS EXISTS, and it is one commit's worth of evidence. On 2026-09-05 a push
went to main on a RED gate, from this command:

    grep -E "GATE IS|GATE EXIT" gate70.txt && git push origin main

The grep SUCCEEDED - it found the lines it was looking for - so the push ran.
The push was chained to grep's exit status, not to the gate's verdict, and the
verdict was `GATE EXIT=1`. Every earlier push that day happened to be green, so
the mistake had never shown itself. The gate did its job; the hand-typed step
around it did not, and a step retyped each time cannot be made reliable by care.

## Why the lock is held across the gate AND the push

The first version gated, then pushed, and its second real use was refused as a
non-fast-forward: **main had moved during the thirteen-minute gate.** Rebasing
and pushing anyway would push a tree the gate never saw, and a verdict is only
about the tree it was computed on. An unbounded retry spends the machine.

So the lock this repository already has for gating is held from the START of the
gate through the push. Every lane's gate takes the same lock, so no lane can
land between a green verdict and the push that follows it; a lane that arrives
waits, which is the queue-in-front-of-the-lock the scheduler design describes.

**That is why this passes `--no-lock` to the gate, and the first version of this
file said in bold that it never would.** It does now because THIS process is
already holding the lock the gate would take, and a subprocess waiting on a lock
its own parent holds is a deadlock. The words changed because the design did;
the guarantee is stronger, not weaker.

## Why the frontend is checked HERE and not in the gate

`scripts/gate.py` is unittest discovery and nothing else. It never opens a
`.ts` file, never runs `tsc`, and never runs vitest - so on 2026-09-17 a stray
brace in `whiteboard.css` passed 5,393 tests and failed in `vite build`, and
the record already carries the shorter sentence for it: THE GATE DOES NOT READ
CSS. A green gate is a statement about the Python; a push is an act of
publication, and what gets published is the whole product.

So both frontend commands run here, between the green gate and the push, each
judged by its EXIT CODE for the same reason everything else in this file is:

    npm --prefix frontend run test -- --run     (vitest, one pass)
    npm --prefix frontend run build             (tsc -b && vite build)

`npm ci` is NOT run for you. A step that installed a dependency tree in order
to certify a push would be changing the thing it is certifying, and on a clone
with no `frontend/node_modules` it would spend minutes before the first test.
When that directory is absent the checks are SKIPPED AND SAID SO, loudly, on
stdout - because a silent skip is how a check stops existing without anybody
deciding to remove it.

## What it will not do

* It will not read the gate's OUTPUT to decide. Output is what the grep was
  reading, and a line saying "GATE IS RED" matches a search for "GATE IS" just
  as well as a green one does.
* It will not push when the gate cannot run. A gate that failed to start says
  nothing about the tree.
* It will not retry forever. If origin moved anyway - a push from a worktree
  that never gated, which the record says has happened - it rebases and re-gates
  **once**, then refuses for a person, with the reason in the refusal.

## Usage

    python scripts/push_if_green.py origin main

Everything after the script name is handed to `git push` unchanged. `--dry-run`
gates and reports without pushing.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: `git push` exits 1 when the remote refuses the ref, which is the
#: non-fast-forward this file's retry exists for. Every other non-zero code is
#: the push failing for its own reasons and is not answered by a rebase.
A_REJECTED_REF = 1

#: What the gate means by each code, in its own words. Anything not here is
#: unknown, and unknown is a refusal.
WHAT_THE_GATE_MEANT = {
    0: "green",
    1: "a test failed",
    2: "the run does not say what the tree does - a count mismatch, a module "
       "that did not import, or another lane holding the machine lock",
}


#: Where an installed frontend lives. Its ABSENCE is the only thing that turns
#: the two checks below off, and it is the honest signal: nothing can run
#: without it, and every other reason to skip would be somebody's opinion.
FRONTEND = REPO / "frontend"
FRONTEND_MODULES = FRONTEND / "node_modules"

#: The two commands, in the order they run, as the arguments handed to npm.
#: The bare `--` is npm's separator: without it `--run` is eaten by npm and
#: vitest starts its WATCHER, which never exits and would hang the push behind
#: a file watcher for ever.
THE_FRONTEND_CHECKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("the frontend tests", ("--prefix", "frontend", "run", "test", "--", "--run")),
    ("the frontend build", ("--prefix", "frontend", "run", "build")),
)

#: Said out loud when there is nothing installed to check with. On stdout, in
#: the same block of lines as the gate's own verdict, because a person reading
#: a push that went through is entitled to know which of its checks did not
#: happen. A skip nobody prints is a check that has quietly stopped existing.
THE_FRONTEND_WAS_NOT_CHECKED = (
    "FRONTEND NOT CHECKED: " + str(FRONTEND_MODULES) + " is not there, so "
    "neither the frontend tests nor the typed build could run. The push is "
    "going ahead on the Python gate alone - run `npm ci` in frontend/ and "
    "gate again if this checkout is the one publishing a frontend change."
)


def the_npm_command() -> str:
    """`npm`, resolved. On Windows the thing on PATH is `npm.cmd`.

    `subprocess.run(["npm", ...])` without a shell raises `FileNotFoundError`
    on Windows, because `npm` there is a shell script beside the `.cmd` the
    loader would actually run. `shutil.which` applies PATHEXT and hands back
    the one that starts. It is resolved at call time rather than at import so
    that a machine which gains node between two runs is not told to restart
    anything, and the bare name is the fallback so the refusal a missing npm
    produces names npm rather than `None`.
    """
    import shutil

    return shutil.which("npm") or "npm"


def why_the_frontend_refuses_the_push(what: str, code: int) -> str:
    """The refusal when vitest or the typed build came back non-zero."""
    return (
        f"PUSH REFUSED: the Python gate was green and {what} exited {code}. "
        "Nothing was pushed. A green gate is a statement about the Python - "
        "`scripts/gate.py` is unittest discovery and never opens a .ts or .css "
        "file - and what a push publishes is the whole product. Fix it, and "
        "gate again."
    )


def why_the_frontend_could_not_run(what: str, detail: str) -> str:
    """The refusal when npm itself would not start. Not a skip.

    An installed `node_modules` with no npm to drive it is a broken machine,
    not a checkout without a frontend, and the two must not produce the same
    silence - that is the whole shape of the skip above.
    """
    return (
        f"PUSH REFUSED: {what} could not be run at all ({detail}). Nothing was "
        "pushed. A check that failed to START says nothing about the tree, "
        "which is the same rule this file already applies to a gate that could "
        "not run."
    )


def the_frontend_exit_code(run=subprocess.run) -> tuple[int, str]:
    """Run vitest then the typed build, stopping at the first non-zero.

    Returns `(0, "")` when both passed AND when there is nothing installed to
    run them with - the skip is printed, not returned, because a push that is
    allowed to go ahead is allowed to go ahead. Every other outcome is
    `(code, what)` and the caller refuses with it.
    """
    if not FRONTEND_MODULES.is_dir():
        print(THE_FRONTEND_WAS_NOT_CHECKED, flush=True)
        return 0, ""
    npm = the_npm_command()
    for what, arguments in THE_FRONTEND_CHECKS:
        print(f"gate green; now {what}: npm {' '.join(arguments)}", flush=True)
        try:
            done = run([npm, *arguments])
        except OSError as error:  # npm is gone, or the loader refused it
            print(why_the_frontend_could_not_run(what, str(error)), file=sys.stderr)
            return 2, what
        code = int(getattr(done, "returncode", 1))
        if code != 0:
            print(why_the_frontend_refuses_the_push(what, code), file=sys.stderr)
            return code, what
    return 0, ""


def what_is_uncommitted(run=None) -> list[str]:
    """Tracked paths that differ from HEAD. Untracked files are not dirt.

    Every lane leaves scratch files in a checkout and refusing on those would
    mean never pushing. A MODIFIED TRACKED FILE is different: it is in the tree
    the suite reads and not in the object the push publishes.
    """
    import subprocess

    run = subprocess.run if run is None else run
    try:
        done = run(
            ["git", "-C", str(REPO), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
        )
    except OSError:
        return []
    if getattr(done, "returncode", 1) != 0:
        return []
    return [line[3:] for line in (done.stdout or "").splitlines() if line.strip()]


def why_a_dirty_tree_cannot_certify(dirty: list[str]) -> str:
    """The refusal when the suite would read one tree and the push publish another.

    MEASURED ON THIS SCRIPT'S OWN AUTHOR, 2026-09-10. A `git commit --amend`
    with no pathspec kept the old content and replaced only the message, so
    HEAD described a feature it did not contain - while the WORKING TREE had
    it. The gate read the working tree, reported GREEN on 5,036 tests, and the
    object it was about to publish was missing the change the run had just
    certified. A non-fast-forward rejection is the only reason it did not land.
    IT WOULD HAVE PUSHED A GREEN LIE.

    `scripts/gate.py` cannot catch this and is not wrong not to: it fingerprints
    tracked files BEFORE and AFTER to see whether the tree MOVED under the run,
    which is a different question from whether the tree matched HEAD when the
    run started. Publishing an object is what makes that second question
    matter, so the check belongs here.
    """
    return (
        "PUSH REFUSED: this checkout has uncommitted changes to tracked files, "
        "so a gate would certify a tree that is not the object this would "
        "push. Nothing was gated and nothing was pushed - the suite reads the "
        "WORKING TREE and the push publishes HEAD, and they are not the same "
        "thing right now:" + chr(10) + "  "
        + (chr(10) + "  ").join(dirty[:10])
        + ((chr(10) + "  ...") if len(dirty) > 10 else "")
        + chr(10)
        + "Commit them or stash them. If they are another lane's, this is "
        "not the checkout to push from."
    )


def the_push_lock():
    """`one_push_at_a_time`, or None when it cannot be loaded."""
    path = REPO / "scripts" / "one_push_at_a_time.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("one_push_at_a_time", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:  # noqa: BLE001 - a missing lock must not stop a push
        return None
    return module


def why_the_push_lock_refused(remote: str, ref: str) -> str:
    return (
        f"PUSH REFUSED: another lane has held the push lock for {remote} {ref} "
        "longer than this step will wait. Nothing was gated and nothing was "
        "pushed - which is the point of taking that lock BEFORE the suite "
        "rather than after it. Run this again when the holder is done; its pid "
        "and start time were printed above."
    )


def the_machine_lock():
    """`one_gate_at_a_time`, or None when it cannot be loaded."""
    path = REPO / "scripts" / "one_gate_at_a_time.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("one_gate_at_a_time", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:  # noqa: BLE001 - a missing lock must not stop a push
        return None
    return module


def why_this_push_is_refused(code: int) -> str:
    """The sentence a reader gets when the push does not happen."""
    meaning = WHAT_THE_GATE_MEANT.get(code, "an exit code this script has no name for")
    return (
        f"PUSH REFUSED: the gate exited {code} ({meaning}).\n"
        "Nothing was pushed. Fix the tree and run this again - and note that "
        "reading the gate's output instead of its exit code is exactly how a "
        "red commit reached main on 2026-09-05."
    )


def why_the_second_attempt_is_refused() -> str:
    """The sentence when origin moved even though the lock was held."""
    return (
        "PUSH REFUSED: origin moved again while this lane held the machine "
        "lock, so a push arrived from something that did not gate - a worktree "
        "or a lane not using this step. Rebased and re-gated once already; a "
        "second automatic attempt would be a loop that spends the machine "
        "without converging. Rebase and run this again yourself, and if it "
        "keeps happening the lane that is not gating is the thing to fix."
    )


def the_object_that_was_gated(run) -> str | None:
    """The commit the suite just ran on, or None when git will not say.

    A GATE CERTIFIES A TREE AND `git push origin main` PUBLISHES A NAME. They
    are the same thing only while nothing moves the name, and on 2026-09-10
    three commits landed under one sixteen-minute run in a shared checkout. The
    fingerprint check in `scripts/gate.py` cannot see this: it watches the
    files in THIS working tree, and `refs/heads/main` is not one of them.

    Worse from a worktree, which is now the recommended place to gate: the
    branch checked out here is `intake/night`, so `main` is a name this run
    never touched at all and the rebase-and-retry below rebases the branch
    while the push publishes the ref. Two different objects, one of them
    certified.

    None is "cannot decide", never "unchanged" - the same rule the HEAD check
    and the tracked-files check both follow.
    """
    try:
        done = run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    except OSError:
        return None
    if getattr(done, "returncode", 1) != 0:
        return None
    said = (getattr(done, "stdout", "") or "").strip()
    if len(said) != 40 or any(c not in "0123456789abcdef" for c in said.lower()):
        return None
    return said


def why_the_object_cannot_be_named(push_args: list[str]) -> str:
    """The refusal when the arguments do not say what to publish where."""
    return (
        "PUSH REFUSED: this step publishes the OBJECT it gated, and it cannot "
        f"work out where {push_args!r} would put it. The form it understands is "
        "`<remote> <branch>` or `<remote> <src>:<dst>`. Nothing was pushed - "
        "the alternative would be pushing a REF, which is a name that can point "
        "somewhere else by the time the push runs, and that is the defect this "
        "function exists to remove."
    )


THE_GATED_OBJECT_IS_UNKNOWN = (
    "PUSH REFUSED: `git rev-parse HEAD` did not answer, so this step cannot say "
    "which commit the gate certified. The only thing left to push would be a "
    "ref, and a ref is a name - the certificate would be about one object and "
    "the publication about whatever the name happens to hold. Nothing was "
    "pushed."
)


def the_push_that_publishes(push_args: list[str], gated: str) -> list[str] | None:
    """`["origin", "main"]` and a sha -> `["origin", "<sha>:refs/heads/main"]`.

    THE SOURCE IS ALWAYS THE GATED OBJECT, whatever the caller wrote. A caller
    who names a source is naming the thing they believe was gated; this knows,
    because it asked git between the gate and the push. The DESTINATION is the
    caller's and is left alone.

    It is also what makes the retry correct. After `git rebase origin/main` the
    gated object is the rebased commit, and re-deriving the refspec each attempt
    publishes THAT - where pushing `main` would publish a ref the rebase never
    moved, which is a second attempt guaranteed to be refused for the same
    reason as the first.
    """
    if len(push_args) != 2:
        return None
    remote, refspec = push_args
    if remote.startswith("-") or not refspec:
        return None
    destination = refspec.split(":", 1)[1] if ":" in refspec else refspec
    if not destination or destination.startswith("-"):
        return None
    if not destination.startswith("refs/"):
        destination = f"refs/heads/{destination}"
    return [remote, f"{gated}:{destination}"]


#: The rules a release must be certified against, and the file they live in.
#: Gitignored, so it lives in a working tree and does not travel - which is why
#: the check belongs HERE and not in the gate. A visitor who clones this
#: repository can never legitimately hold this file, and a gate that refused
#: without it would make the suite un-passable for everyone but this machine.
#: A PUSH is different: it is the act that publishes, and publishing uncertified
#: is the thing that actually went wrong on 2026-09-06.
THE_RELEASE_RULES = Path(__file__).resolve().parents[1] / "scripts" / "release" / "identifiers.json"


def why_the_gated_tree_moved(dirty: list[str], gated: str, now: str | None) -> str:
    """The refusal when the tree the suite READ is not the tree being published.

    THE FIRST CHECK IS NOT ENOUGH, AND THIS LANE PROVED IT TWICE IN ONE NIGHT.
    `what_is_uncommitted` is asked once, before the gate. The gate then reads
    this working tree for eight to twenty minutes and nothing looks again. A
    tracked file written inside that window is read by the suite and is not in
    the object the push publishes, so a green verdict certifies a tree nobody
    committed.

    At 04:05 on 2026-09-11 this lane voided a live gate by committing under it,
    eleven minutes after arguing for the hook that exists to stop exactly that.
    At 02:22 it began writing a test file into a worktree whose gate was queued
    and stopped only because a person read the log first. A check that works
    when somebody remembers is not a check.

    REFUSING RATHER THAN RE-GATING. The verdict in hand describes a tree that no
    longer exists, so it cannot authorise anything. Re-running would spend
    another twenty minutes on a tree the same lane can dirty again while it
    runs. Naming what moved hands the decision to whoever moved it.
    """
    lines = [
        "PUSH REFUSED: the tree moved while the suite was reading it, so the "
        "green verdict is about a tree that is not what would be published.",
        f"  the suite began on: {gated}",
    ]
    if now is not None and now != gated:
        lines.append(f"  HEAD is now:        {now} - a commit landed under the suite")
    if dirty:
        lines.append("  tracked files that changed while the suite ran:")
        lines.extend("    " + path for path in dirty[:10])
        if len(dirty) > 10:
            lines.append("    ...")
    lines.append("  Commit or stash what moved and gate again. Nothing was pushed.")
    return chr(10).join(lines)


def why_this_checkout_cannot_certify_a_release() -> str | None:
    """The refusal when the identifier rules are not in this working tree."""
    if THE_RELEASE_RULES.exists():
        return None
    return (
        f"PUSH REFUSED: {THE_RELEASE_RULES.name} is not in this checkout, so the "
        "personal-identifier rules never ran and this tree cannot certify what "
        "it is about to publish. The gate is right to be green - the tests "
        "passed and the tree is fine - but a green gate is a statement about "
        "code and a push is an act of publication. On 2026-09-06 a commit "
        "reached main carrying a denylisted path because the rules were absent "
        "from the pushing checkout and the summary line said OK. Nothing was "
        "pushed."
    )


def the_gate_exit_code(argv: list[str], run=subprocess.run) -> int:
    """Run `scripts/gate.py` and return its exit code."""
    done = run([sys.executable, str(REPO / "scripts" / "gate.py"), *argv])
    return int(done.returncode)


def push_if_green(
    push_args: list[str],
    gate_args: list[str] | None = None,
    run=subprocess.run,
    dry_run: bool = False,
    lock=None,
    push_lock=None,
    rebase_and_retry_once: bool = True,
) -> int:
    """Gate and push under one lock. The whole decision, where a test can call it."""
    #: `None` asks for the real module; a FALSY lock means "there is none", and
    #: a test says so that way rather than passing None and blocking on the
    #: real machine lock for half an hour. A test that reaches for a real
    #: resource is how the earlier version of this file's suite nearly pushed
    #: to origin.
    lock = the_machine_lock() if lock is None else lock
    held = False
    if lock:
        held = bool(lock.acquire(lock.DEFAULT_TIMEOUT_SECONDS, "push_if_green"))
        if not held:
            print(
                "PUSH REFUSED: another lane holds the machine lock and did not "
                "finish in time. Nothing was gated and nothing was pushed.",
                file=sys.stderr,
            )
            return 2
    #: THE REMOTE REF, AFTER THE MACHINE LOCK AND BEFORE THE GATE.
    #:
    #: Six races on 2026-09-10, every one two lanes gating siblings of one
    #: commit in two checkouts: both green, the second refused non-fast-forward
    #: after a full suite, then another suite to rebase and re-gate. The
    #: machine lock cannot prevent that and is not wrong to - it is keyed by
    #: CHECKOUT, and what two worktrees contend for is `refs/heads/main` on the
    #: remote, which no per-checkout lock can name.
    #:
    #: BEFORE THE GATE, because a lock taken after a green gate serialises the
    #: pushes and nothing else: the loser has still spent a suite certifying a
    #: tree that no longer describes `main`. Taken first, the waiter's tree
    #: already contains the winner's object when its gate starts.
    #:
    #: AFTER THE MACHINE LOCK, and that order is not arbitrary. Two invocations
    #: in ONE checkout would otherwise deadlock - one holding the push lock and
    #: waiting for the machine lock, the other the reverse. Machine first makes
    #: the cycle impossible: a lane only ever waits for the push lock while
    #: holding a lock nobody outside its own checkout wants.
    push_lock = the_push_lock() if push_lock is None else push_lock
    push_held = False
    if push_lock and len(push_args) == 2:
        _remote, _refspec = push_args
        _target = _refspec.split(":", 1)[-1]
        if not _target.startswith("refs/"):
            _target = f"refs/heads/{_target}"
        push_held = bool(
            push_lock.acquire(
                _remote, _target, push_lock.DEFAULT_TIMEOUT_SECONDS, "push_if_green"
            )
        )
        if not push_held:
            #: RELEASED BEFORE RETURNING, or a lane that cannot push wedges its
            #: own checkout for nothing.
            if held:
                lock.release()
            print(why_the_push_lock_refused(_remote, _target), file=sys.stderr)
            return 2

    #: The gate would take the lock this process is already holding, and a
    #: subprocess waiting on its parent's lock never returns.
    gate_args = list(gate_args or [])
    if held and "--no-lock" not in gate_args:
        gate_args.append("--no-lock")
        # HAND THE WAIT DOWN. This process did the queueing; the gate
        # subprocess writes the history row. Measured: two runs queued 13.6
        # and 6.1 minutes behind the other lane and both were recorded as
        # 0.0, because the waiter and the recorder are different processes.
        # The one number this change is judged by was blind on exactly the
        # path every lane uses.
        try:
            os.environ["MLH_WAITED_SECONDS"] = repr(float(lock.waited_seconds()))
        except Exception:  # noqa: BLE001 - a lost figure must not stop a push
            pass

    #: BEFORE THE GATE, because a run that cannot authorise a push should not
    #: spend a suite. It is no longer before the LOCKS - they moved above this
    #: line when the push lock arrived and this sentence did not follow them.
    #: The queue is short and the suite is not, so the order that matters is
    #: this one: check, then spend.
    #:
    #: AND THIS LOOK IS NOT THE LAST ONE. See `why_the_gated_tree_moved` below,
    #: which is the only check that knows what the suite actually read.
    dirty = what_is_uncommitted(run=run)
    if dirty:
        print(why_a_dirty_tree_cannot_certify(dirty), file=sys.stderr)
        return 2

    uncertifiable = why_this_checkout_cannot_certify_a_release()
    if uncertifiable:
        #: BEFORE the gate, because spending eight minutes on a suite whose
        #: result cannot authorise a push is time nobody gets back.
        print(uncertifiable, file=sys.stderr)
        return 2

    try:
        for attempt in (1, 2):
            #: RE-DERIVED EVERY ATTEMPT, because a rebase between them changes
            #: which object is the one that was gated.
            gated = the_object_that_was_gated(run)
            if gated is None:
                print(THE_GATED_OBJECT_IS_UNKNOWN, file=sys.stderr)
                return 1
            publishing = the_push_that_publishes(push_args, gated)
            if publishing is None:
                print(why_the_object_cannot_be_named(push_args), file=sys.stderr)
                return 1

            code = the_gate_exit_code(gate_args, run=run)
            if code != 0:
                print(why_this_push_is_refused(code), file=sys.stderr)
                return code
            #: THE FRONTEND, AFTER A GREEN GATE AND BEFORE THE SECOND LOOK.
            #:
            #: After the gate, because there is no point spending minutes of
            #: vitest and vite on a tree whose Python is red. BEFORE the
            #: tree-moved check below, and that order is the whole reason it is
            #: here rather than three lines further down: the build takes
            #: roughly a minute, that minute is one more window in which
            #: another lane can write a tracked file, and `why_the_gated_tree_moved`
            #: is the only check that can see it. Everything the frontend
            #: build writes - `dist/`, `*.tsbuildinfo` - is gitignored, so it
            #: cannot dirty the tree on its own account and cannot make that
            #: check fire about itself.
            frontend, _which = the_frontend_exit_code(run=run)
            if frontend != 0:
                #: The refusal was printed by the check, which knows WHICH of
                #: the two failed. Returning its code rather than a code of
                #: this file's own keeps the rule the whole script is about:
                #: the decision is the exit code, never the output.
                return frontend
            #: THE SECOND LOOK, and the only one that knows what the suite
            #: actually read. Everything above was decided before it ran, and
            #: `gated` was resolved before it too, so both halves are asked
            #: again: what is in this tree, and which object HEAD names.
            #:
            #: UNTRACKED FILES ARE STILL NOT DIRT, by the same rule and the
            #: same function as the first check. Every lane leaves scratch
            #: files in a checkout, and a second check with a stricter
            #: definition would refuse pushes the first one allowed - a rule
            #: nobody could hold in their head.
            moved = what_is_uncommitted(run=run)
            still = the_object_that_was_gated(run)
            if moved or (still is not None and still != gated):
                print(why_the_gated_tree_moved(moved, gated, still), file=sys.stderr)
                return 2
            if dry_run:
                print(f"gate green; would run: git push {' '.join(publishing)}")
                return 0
            print(f"gate green; pushing: git push {' '.join(publishing)}", flush=True)
            pushed = int(run(["git", "push", *publishing]).returncode)
            if pushed == 0:
                return 0
            #: ONLY A REJECTION IS WORTH A REBASE. `git push` exits 1 when the
            #: remote refuses the ref - the non-fast-forward this retry exists
            #: for. Anything else is the push itself failing: no credentials,
            #: no network, a bad remote. Rebasing and re-gating for thirteen
            #: minutes would not fix any of those, and it would rewrite a
            #: branch in response to an unrelated error. Found by a test
            #: written before the retry existed, which fed 128 and expected it
            #: back.
            if pushed != A_REJECTED_REF:
                print(
                    f"PUSH FAILED: git push exited {pushed}, which is not a "
                    "rejected ref. Nothing was rebased - that would answer a "
                    "credential or network failure by rewriting a branch.",
                    file=sys.stderr,
                )
                return pushed
            if attempt == 2 or not rebase_and_retry_once:
                print(why_the_second_attempt_is_refused(), file=sys.stderr)
                return pushed
            print(
                "push rejected: origin moved even under the lock. Rebasing and "
                "re-gating once, because a verdict is only about the tree it "
                "was computed on.",
                flush=True,
            )
            if int(run(["git", "fetch", "origin"]).returncode) != 0 or int(
                run(["git", "rebase", "origin/main"]).returncode
            ) != 0:
                print(
                    "PUSH REFUSED: the rebase did not succeed, so there is no "
                    "tree to gate. Nothing was pushed.",
                    file=sys.stderr,
                )
                return 1
        return 1
    finally:
        if push_held and push_lock:
            push_lock.release()
        if held:
            lock.release()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in argv
    argv = [arg for arg in argv if arg != "--dry-run"]
    push_args = [arg for arg in argv if arg != "--no-lock"] or ["origin", "main"]
    return push_if_green(push_args, [], dry_run=dry_run)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
