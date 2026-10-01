"""The full gate, and it counts what it ran against what exists.

## The defect this exists for, measured 2026-09-04

Two full suites were started in this checkout minutes apart - one by this
session, one by another lane that gates in the same repository. The second
reported:

    Ran 3315 tests in 432.374s
    OK (expected failures=4)

Discovery in that same tree finds **3822**. So 507 tests never ran, nothing was
red, nothing was skipped in the report, and the run said OK. A commit was one
command away from being pushed on it.

`docs/how-to-verify.md`'s first law is that a gate you cannot make fail is not a
gate. A gate that silently covers 87% of the suite is the same failure wearing a
green tick, and no amount of remembering to run suites one at a time fixes it -
the next collision is a different lane on a different night. So the count is
asserted here, mechanically, and a mismatch is RED with both numbers printed.

## What it does not claim

It does not explain WHY a concurrent run loses tests. It does not need to: the
assertion is that a suite which reports OK must also report how many it ran
against how many exist, and any cause - a collision, a stray process, a partial
import, a killed worker - presents as red rather than as a pass.

## Usage

    python scripts/gate.py            # the gate; exit 0 only on a full green run

`python -m unittest discover -s tests -t tests` still works and is still what
`AGENTS.md` documents; this wraps it with the one check that run could not make
about itself.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest

NEWLINE = chr(10)
from pathlib import Path

#: Where every run of this gate records what it saw. The system temp directory,
#: beside the machine lock, for the same reason: it is a fact about this
#: MACHINE and its lanes, not about any one checkout, and a file inside a
#: worktree would count only that worktree's runs.
#:
#: WHY RECORD AT ALL. The claim "N concurrent runs, 0 lost tests" has been
#: carried by hand in `docs/walks.md` since the lock was built, and a hand-carried
#: number goes stale: it was written as 3, corrected to 5 an hour later, and was
#: 6 before that correction's own gate had finished. A number that moves faster
#: than the run that verifies it wants counting rather than typing.
HISTORY = Path(tempfile.gettempdir()) / "ml-harness-gate-history.jsonl"

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def how_many_tests_are_in(suite: unittest.TestSuite) -> int:
    """Count leaves. `suite.countTestCases()` would do it; this is explicit
    because the number is the whole point of the file and a reader should be
    able to see what is being counted rather than trust a method name."""
    total = 0
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            total += how_many_tests_are_in(item)
        else:
            total += 1
    return total


def _the_program(command: str) -> str:
    """The executable a command line runs, lowercased.

    The first token, and a quoted first token is read to its closing quote -
    `"C:/Program Files/Python/python.exe" -m unittest` is one path with a space
    in it, not two tokens. Splitting on a flag instead was the defect above.
    """
    command = command.strip()
    if command.startswith('"'):
        end = command.find('"', 1)
        return (command[1:end] if end > 0 else command[1:]).lower()
    return command.split(" ", 1)[0].lower()


def other_suites_running_now() -> list[str]:
    """Other full-suite runs on this machine, as `pid: command` lines.

    MEASURED 2026-09-05: two suites were running concurrently under two
    different interpreters while the gate lock was held by nobody. The lock in
    `scripts/one_gate_at_a_time.py` only protects lanes that remember to wrap
    their run in it, and a guard that depends on being remembered is not one.

    This does not refuse and does not wait - the count assertion below already
    turns a run that LOST tests red, which is the failure that matters. What it
    does is name the neighbours, so a green result carries the fact that it did
    not have the machine to itself, and a reader deciding whether to trust a
    timing or a flake knows to look. Best effort: on a machine where the
    process list cannot be read, this returns nothing rather than guessing.
    """
    if os.name != "nt":  # pragma: no cover - this suite's home is Windows
        return []
    import subprocess

    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "
             "'unittest discover|scripts.gate\.py' } | ForEach-Object "
             "{ '{0}|{1}' -f $_.ProcessId, $_.CommandLine }"],
            capture_output=True, text=True, timeout=25,
        ).stdout
    except Exception:  # noqa: BLE001 - a process list we cannot read is not a failure
        return []
    #: This process, and the one that started it. THE PARENT MATTERS: run through
    #: `one_gate_at_a_time.py`, the wrapper's own command line ends in
    #: `-- python scripts/gate.py`, so it matches this filter exactly as a real
    #: neighbour would and gets counted as company by the child it launched.
    #: Measured 2026-09-05 by reading what the filter excludes: only `getpid()`,
    #: so a single lane using the documented wrapper reports one neighbour that
    #: is its own parent. A number that counts you as your own company is worse
    #: than no number, because it is wrong in the direction of looking careful.
    mine = {str(os.getpid()), str(os.getppid())}
    #: Pids already reported. The process table should never list one twice, so
    #: this has never fired - but the count did not SAY distinct, and a number
    #: that only happens to be right teaches nothing about the instrument that
    #: produced it. Fed the same pid twice, this reported two neighbours.
    seen_pids: set[str] = set()
    seen = []
    for line in out.splitlines():
        pid, _, command = line.partition("|")
        pid, command = pid.strip(), command.strip()
        if not pid.isdigit() or pid in mine or pid in seen_pids:
            continue
        # ONLY ACTUAL PYTHON RUNS. A first version matched any process whose
        # command line contained the pattern, which caught the shell that
        # launched the query and the PowerShell running it - seven "suites"
        # where two were real. The shells carry the pattern because they carry
        # the query; the thing being looked for is a python interpreter with
        # the suite on its own command line.
        #
        # AND THE TIGHTENING HAD ITS OWN HOLE, found 2026-09-05 by watching this
        # report 0 neighbours while a gate was running three feet away. It read
        # the executable as `command.split(" -")[0]`, which only finds it when a
        # FLAG follows: `python -m unittest discover` splits at ` -m` and gives
        # `python.exe`, but `python scripts/gate.py` has no flag, so the "head"
        # was the whole line and ended in `gate.py`. The invocation it could not
        # see was the one this repository had just made standard everywhere.
        head = _the_program(command)
        if not head.endswith(("python.exe", "python", "python3.exe", "python3")):
            continue
        if "unittest discover" not in command and "gate.py" not in command:
            continue
        seen_pids.add(pid)
        seen.append(f"{pid}: {command[:90]}")
    return seen


def what_a_finished_run_looks_like() -> str:
    """The contract a run states before it starts, so silence can be read.

    A FUNCTION RATHER THAN AN INLINE LITERAL, for the reason the neighbour
    below gives: a test can call it.
    """
    return (
        "GATE VERDICT PENDING: this run ends with a line beginning 'GATE IS'. "
        "If the output stops before that line, the run did not finish and its "
        "result is unknown - not green."
    )


def why_the_count_is_red(discovered: int, ran: int) -> str:
    """The sentence a reader gets when tests went missing.

    A FUNCTION RATHER THAN AN INLINE LITERAL so a test can call it. The first
    version of that test asserted this text by grepping this file's source, and
    it broke on a line wrap inside the string - a test about formatting wearing
    the clothes of a test about behaviour. Caught by running it.

    It names the causes, because "counts differ" would send the next reader
    hunting a broken test when the cause is usually a second suite.
    """
    return (
        f"GATE IS RED: {discovered - ran} test(s) never ran "
        f"({ran} of {discovered}).\n"
        "A suite that reports OK must also report how many it ran against how "
        "many exist. Something took tests out of this run - a second suite in "
        "the same checkout, a stray process, a killed worker - and whatever it "
        "was, this run does not say what the tree does."
    )


def the_modules_that_did_not_import(suite: unittest.TestSuite) -> list[str]:
    """The module names unittest replaced with a placeholder, read off the
    suite rather than off `loader.errors`.

    `TestLoader.errors` is a list of formatted TRACEBACK STRINGS, not of
    (name, error) pairs - a first version of this file unpacked it as pairs,
    passed its own tuple fixture, and raised `too many values to unpack` the
    moment it met a real discovery. The placeholders themselves carry the name
    (`unittest.loader._FailedTest.test_broken`) and come from the same walk the
    count comes from, so they are the honest source.
    """
    names: list[str] = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            names.extend(the_modules_that_did_not_import(item))
        elif type(item).__name__ == "_FailedTest":
            names.append(item.id().rsplit(".", 1)[-1])
    return names


def why_the_import_errors_are_red(errors: list[str]) -> str:
    """The sentence a reader gets when a module did not import.

    MEASURED 2026-09-05 ON A CLEAN CLONE. Two test modules read a gitignored
    artifact at import time. On a checkout without it:

        with the guard      ran 3958 of 3958 discovered   GREEN
        without the guard   ran 3923 of 3923 discovered   errors=2

    Thirty-five real tests were replaced by two `_FailedTest` placeholders, and
    **the count check did not notice**, because a placeholder is discovered and
    run like anything else. `ran == discovered` cannot see this class of loss;
    only the errors can, and they are printed four thousand lines above where a
    reader looks. So it is said again at the end, with the modules named.

    It returns 2 rather than 1 for the same reason a count mismatch does: this
    run does not say what the tree does, which is a different fact from a test
    being red.
    """
    modules = ", ".join(sorted(errors))
    return (
        f"GATE IS RED: {len(errors)} test module(s) did not import: {modules}.\n"
        "Their tests are not in this run at all - unittest replaced each module "
        "with a single placeholder that errors, so the discovered count still "
        "matches and the count check cannot see the loss. A module that reads a "
        "gitignored artifact at import time fails exactly this way on a clean "
        "checkout; skip with a reason instead."
    )


def the_machine_lock():
    """`one_gate_at_a_time`, imported the way the tests import scripts.

    WHY THIS IS HERE AND WAS NOT. Two mechanisms were built for one collision
    and only one of them was on the path anybody uses. `one_gate_at_a_time.py`
    prevents two suites sharing a machine; THIS file detects the damage after
    the fact by counting. The wrapper's own docstring shows it in front of
    `python -m unittest discover` - but the gate this repository documents and
    that its lanes actually run is `python scripts/gate.py`, which took no lock
    at all. Every gate run on 2026-09-05 went without mutual exclusion; the
    count check would have caught the loss, having not prevented it.

    Returns None when the module cannot be loaded, because a gate that refuses
    to run without its lock is a gate nobody can run.
    """
    import importlib.util

    path = REPO / "scripts" / "one_gate_at_a_time.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("one_gate_at_a_time", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:  # noqa: BLE001 - a missing lock must not stop the gate
        return None
    return module


def the_wait_this_run_paid(lock) -> float:
    """Seconds this run spent queueing, from whichever process did the waiting.

    A gate run directly holds its own lock and knows. A gate run under
    `push_if_green` does NOT: the parent holds the lock and passes
    `--no-lock` down, so the process that queued and the process that
    records are different ones, and every such run recorded 0.0 while the
    parent's own stderr said it had waited 13.6 minutes. The parent hands
    the figure over in the environment rather than the number being lost.
    """
    if lock is not None:
        try:
            return float(lock.waited_seconds())
        except Exception:  # noqa: BLE001
            return 0.0
    try:
        return float(os.environ.get("MLH_WAITED_SECONDS") or 0.0)
    except ValueError:
        return 0.0


def remember(*, ran: int, discovered: int, beside: int, waited: float = 0.0,
             skipped: int = 0) -> None:
    """Append one line about this run, so the denominator can be counted.

    Best effort and silent on failure: a gate that went green must not go red
    because a log file could not be written. What it records is the whole claim
    - how many ran, how many existed, and how many other suites were live - so
    `--history` can produce the sentence that has been typed by hand until now.
    """
    try:
        with HISTORY.open("a", encoding="utf-8") as file:
            file.write(
                json.dumps(
                    {
                        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "ran": ran,
                        "discovered": discovered,
                        "beside": beside,
                        # HOW MUCH OF THE SUITE THIS CHECKOUT COULD ACTUALLY
                        # RUN. Measured 2026-09-07: the same commit on the
                        # same machine skipped 56 in one checkout and 0 in
                        # the other, because 55 of them need artefacts under
                        # `runs/`, which is gitignored and does not travel.
                        # The tests are not hollow; the checkout is
                        # unfurnished - a different defect with a different
                        # fix, and neither is visible from a count of 4,420.
                        "skipped": skipped,
                        # THE NUMBER THAT SAYS THE NARROWING WORKED. Queued
                        # minutes were counted by hand off log lines for two
                        # days - 194 of them - and a metric read out of a log by
                        # a person is a metric nobody will read next week.
                        "waited_seconds": round(waited, 1),
                        "cwd": str(Path.cwd()),
                    }
                )
                + chr(10)
            )
    except OSError:  # pragma: no cover - a log is not the gate
        pass


def the_history() -> int:
    """Print what the recorded runs actually say, and return 0."""
    try:
        rows = [json.loads(l) for l in HISTORY.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        rows = []
    if not rows:
        print("gate history: nothing recorded yet on this machine")
        return 0
    beside = [r for r in rows if r.get("beside", 0) > 0]
    lost = [r for r in rows if r.get("ran") != r.get("discovered")]
    lost_beside = [r for r in beside if r.get("ran") != r.get("discovered")]
    print(f"gate runs recorded on this machine: {len(rows)}")
    print(f"  runs with at least one concurrent suite: {len(beside)} of {len(rows)}")
    print(f"  of those, runs that lost tests:           {len(lost_beside)} of {len(beside)}")
    print(f"  runs that lost tests, in total:           {len(lost)} of {len(rows)}")
    if beside:
        print(f"  most neighbours seen at once:             {max(r['beside'] for r in beside)}")
    waited = [r.get("waited_seconds", 0) or 0 for r in rows]
    counted = [w for w in waited if w]
    print(f"  runs that queued for the lock:            {len(counted)} of {len(rows)}")
    print(f"  total queued:                             {sum(waited) / 60:.1f} minutes")
    if counted:
        print(f"  median wait when it queued:               {sorted(counted)[len(counted) // 2] / 60:.1f} min")
    #: COVERAGE VARIES BY CHECKOUT AND NOTHING ANNOUNCED IT. Fourth instance
    #: of the same shape in one evening, after the gitignored denylist, the
    #: gitignored artefacts and the shared git directory - and this one is
    #: inside the suite rather than around it. A fresh clone skips all 55.
    by_tree: dict[str, list[int]] = {}
    for row in rows:
        if "skipped" in row:
            by_tree.setdefault(str(row.get("cwd") or "unknown"), []).append(row["skipped"])
    if by_tree:
        print("  skipped, by checkout - a suite that skips more is not a suite "
              "that passed more:")
        for tree, counts in sorted(by_tree.items()):
            name = tree.rsplit(chr(92), 1)[-1].rsplit("/", 1)[-1] or tree
            low, high = min(counts), max(counts)
            span = f"{low}" if low == high else f"{low} to {high}"
            print(f"    {name:28s} {span:>10s}  over {len(counts)} run(s)")
    print(f"  file: {HISTORY}")
    return 0


def the_head_now(run=None) -> str | None:
    """This checkout's HEAD, or None when it cannot be read.

    None means "cannot decide", and the caller must not treat it as "unchanged":
    a tree with no git is a tree whose movement this cannot rule out.
    """
    import subprocess

    run = subprocess.run if run is None else run
    try:
        done = run(["git", "rev-parse", "HEAD"], cwd=str(REPO),
                   capture_output=True, text=True)
    except OSError:
        return None
    if getattr(done, "returncode", 1) != 0:
        return None
    return (done.stdout or "").strip() or None


def what_the_skips_were(skipped) -> list[str]:
    """Distinct skip reasons with counts, for the verdict line.

    A SKIP IS A PARTIAL RESULT WEARING A PASS. The other lane shipped a red
    commit because `test_no_shipped_file_names_a_person` skipped its identifier
    half - its denylist is gitignored, and gitignored files live in a WORKING
    TREE, so a worktree simply does not have one. The test said exactly the
    right thing:

        "no identifier list on this machine, so the personal-identifier rules
         did not run; 4 shape rules did ... This is NOT a clean bill."

    and said it four times. The summary line said `OK (skipped=1)`, and that is
    what got read. This repository already carries the law that nothing failed
    is not nothing was checked; the words were present and the place they were
    printed was not the place anybody looks.

    So the reasons come to the verdict. Distinct reasons rather than one line
    per skipped test, because 56 lines is noise and 5 is a sentence.
    """
    from collections import Counter

    counted = Counter((reason or "").strip().splitlines()[0].strip()
                      if (reason or "").strip() else "no reason given"
                      for _, reason in skipped)
    return [f"{count:4d}  {reason}" for reason, count in counted.most_common()]


def the_tracked_files_now(run=None) -> str | None:
    """A fingerprint of TRACKED files' state, or None when it cannot be read.

    NOTHING SERIALISES A PERSON EDITING A FILE AGAINST A SUITE READING IT. The
    machine lock stops two suites colliding; it has nothing to say about an edit
    landing in the middle of one. I did exactly that this evening - saved a docs
    file while a gate was running on that tree - which is the interference the
    lock exists to prevent, committed by the lane that spent the day narrowing
    it. Both lanes have now done it and both caught it only by re-gating out of
    habit.

    `--porcelain` untracked entries are excluded: the suite legitimately creates
    scratch files inside the checkout, and a detector that fires on those would
    be turned off within a day.

    None is "cannot decide", never "unchanged" - the same rule the HEAD check
    follows.
    """
    import subprocess

    run = subprocess.run if run is None else run
    try:
        done = run(["git", "status", "--porcelain", "--untracked-files=no"],
                   cwd=str(REPO), capture_output=True, text=True)
    except OSError:
        return None
    if getattr(done, "returncode", 1) != 0:
        return None
    return (done.stdout or "").strip()


def why_the_tree_moved_under_the_run(before: str | None, after: str | None) -> str:
    """Said BEFORE the verdict, and it refuses.

    THIS WAS DRAFTED REPORT-ONLY AND THE OTHER LANE TALKED ME OUT OF IT,
    which was the point of asking before it had a history. My argument was
    that a detector turning a green run red on an unmeasured signal is one
    somebody disables. Theirs: the signal is not unmeasured - both lanes
    did it today and both caught it only by re-gating out of habit - and a
    green run whose tree changed underneath it is not a weaker green, it is
    a category error. A verdict about a tree that no longer exists is the
    one thing a gate exists to prevent.

    And the decisive half: reporting it at the verdict while still exiting 0
    teaches a reader the line is advisory. That is exactly how "OK
    (skipped=1)" got read past a message that said NOT a clean bill, four
    times, the same evening. If it fires on runs nobody expected, that is a
    finding and it gets quieter with evidence - starting it advisory means
    the first person to see it learns to skip it.
    """
    lines = sorted(set(after.splitlines()) ^ set((before or '').splitlines()))
    #: BUILT FROM PARTS, NEVER TYPED. A literal escape in generated content is
    #: how this repository has lost ten fixtures, and it cost this very
    #: function one syntax error twenty minutes ago.
    indent = chr(10) + '  '
    shown = indent.join(lines[:10]) + (indent + '...' if len(lines) > 10 else '')
    return (
        "THE TRACKED FILES CHANGED WHILE THIS RAN, so some of the results above "
        "describe a tree that no longer exists. Nothing serialises an edit "
        "against a suite reading the same files, and this is that gap firing:"
        + indent + shown
    )


def the_run_is_not_about_one_tree(before: str | None, after: str | None) -> bool:
    """Did the tree change under the suite?

    A FUNCTION SO A TEST CAN ASK WITHOUT RUNNING A SUITE. The first version of
    its test called `the_gate` itself, which runs the whole tree in-process -
    thirty-eight seconds, a redirected stdout that the runner cannot take a
    `fileno` from, and a gate discovering the suite that is discovering it.

    Either sha being None is "cannot decide", and cannot decide is not moved.
    """
    return before is not None and after is not None and before != after


def why_the_moved_head_is_red(before: str, after: str) -> str:
    """The sentence when the tree changed under a running gate.

    MEASURED TWICE, 2026-09-05 AND AGAIN AN HOUR LATER, both times by me. A
    commit landed while the suite was running and
    `test_the_real_repository_answers_with_a_real_sha` went red - it reads
    `identity.git_head()` and `git rev-parse HEAD` and compares them, and HEAD
    moved between the two reads. The test was right both times.

    The machine lock serialises SUITES. It does not stop the agent that started
    one from moving HEAD underneath it, and after the first occurrence I wrote
    that I would rather build this than remember not to. Then I did it again,
    which is the argument for the check rather than against it.

    Exit 2, not 1: this repository's law is that a verdict is only about the
    tree it was computed on, and a run whose tree changed halfway describes
    neither.
    """
    return (
        "GATE IS RED: HEAD moved while the suite was running.\n"
        f"  started on {before}\n"
        f"  ended on   {after}\n"
        "This run describes neither tree. A verdict is only about the tree it "
        "was computed on, so it is not a pass and not a failure - it is a run "
        "that did not happen on one tree. Do not commit, rebase or checkout in "
        "this working copy while a gate is running; the machine lock serialises "
        "suites, not git."
    )


def the_gate(argv: list[str] | None = None) -> int:
    """Discover once, count that suite, run THAT suite, compare.

    ONE DISCOVERY, NOT TWO. Counting with one discovery and running with
    another would compare two different collections, and a difference between
    them would be a fact about discovery rather than about the run - which is
    the kind of number this repository refuses everywhere else.
    """
    argv = sys.argv[1:] if argv is None else argv
    if "--history" in argv:
        return the_history()
    verbosity = 2 if "-v" in argv else 1

    #: THE LOCK FIRST, so this gate is the protected one. A lane already
    #: gating is waited for by name rather than raced; the count check below
    #: stays as the detector for everything a lock cannot prevent.
    lock = None if "--no-lock" in argv else the_machine_lock()
    #: NO TIMEOUT, AND THAT IS THE RULING. A gate keys on the actor, never on a
    #: clock: this waits exactly as long as the holder is alive, and stops when
    #: the holder is gone - which the lock detects rather than guesses, because
    #: it records each process's start time and not just its number.
    #:
    #: The clock it replaces was 1,800 seconds, and measured against it two
    #: consecutive gates queued about 18 and about 19 minutes behind holders
    #: running about 28 and about 30. Neither expired. A third lane behind the
    #: second would have: thirty minutes spent to be told nothing, when one
    #: more minute would have told it whether the tree is green. False here now
    #: means only that a caller asked for a limit and hit it.
    if lock is not None and not lock.acquire(None, "scripts/gate.py"):
        print(
            "GATE IS RED: another full suite holds the machine lock and this run "
            "gave up waiting. This run did not start, so it says nothing about "
            "the tree - which is a different fact from a test being red.",
            file=sys.stderr,
        )
        return 2

    try:
        return _run_the_suite(argv, verbosity, lock)
    finally:
        if lock is not None:
            lock.release()


#: A skip that says its own absence matters. A test that cannot run for a reason
#: OUTSIDE the tree - a config file that lives in a working directory and is not
#: in this one - is not a test that passed, and the gate must not summarise the
#: run as one.
#:
#: MEASURED 2026-09-06. `test_no_shipped_file_names_a_person` skipped with
#: "...the personal-identifier rules did not run; 4 shape rules did ... This is
#: NOT a clean bill." and printed that warning four times. The summary line said
#: `OK (skipped=1)`. I read the summary, pushed, and the commit went red in the
#: other checkout on a rule that had never run here. THE CHECK SAID EXACTLY WHAT
#: IT HAD NOT DONE AND THE SUMMARY SAID OK.
A_SKIP_THAT_MATTERS = "not a clean bill"


def the_skips_that_matter(result) -> list[tuple[str, str]]:
    """`(test, reason)` for every skip declaring itself material.

    The marker is in the REASON rather than in a decorator, because the test
    knows whether its absence matters and the gate does not. A platform skip and
    a missing-ruleset skip are both skips; only one of them means the run cannot
    speak for the tree.
    """
    return [
        (str(case), reason)
        for case, reason in getattr(result, "skipped", [])
        if A_SKIP_THAT_MATTERS in str(reason).lower()
    ]


def why_a_material_skip_is_not_green(skips: list[tuple[str, str]]) -> str:
    """The sentence for a run that could not check what it claims to check."""
    lines = NEWLINE.join(f"  {case}{NEWLINE}    {reason}" for case, reason in skips)
    return (
        f"GATE IS NOT GREEN: {len(skips)} check(s) skipped for a reason outside "
        f"this tree, so this run does not speak for it:{NEWLINE}{lines}{NEWLINE}"
        "A skip is a partial result, and a partial result summarised as a pass "
        "is how a commit reaches main carrying something a rule would have "
        "caught - which is exactly what happened on 2026-09-06, from a skip "
        "that said `This is NOT a clean bill` four times above a summary line "
        "reading OK."
    )


#: Where this repository keeps libraries it has extracted and still ships.
THE_EXTRACTED = REPO / "packages"


def the_extracted_suites(loader) -> list:
    """The tests of every package under `packages/`, which this gate did not run.

    MEASURED 2026-09-07 and it is the reason this exists. `packages/four_asserts`
    holds **38 tests**. All 38 pass. NONE of them had ever run in this gate: the
    only discovery root was `tests/`, so a green line reading
    `4,483 of 4,483 discovered` was true of `tests/` and silent about a shipped
    library sitting beside it. The count was honest and its denominator was not
    the one a reader would assume - **a count without its denominator is a
    ceiling**, which is a law this repository already carries, written by this
    lane, about somebody else's number.

    Worse than not running: they could not be run. `packages/four_asserts/tests`
    has no `__init__.py`, so `discover` refuses it as a start directory unless it
    is also the top level, and the package is not on `sys.path` from the
    repository root - so the obvious invocation fails with `ImportError` and the
    plausible next one with `ModuleNotFoundError`. A suite nobody can start is a
    suite nobody is running, whatever its files say.

    Each package root goes on `sys.path` because these are STANDALONE
    libraries - `four_asserts` imports itself by name, exactly as a consumer
    would, and importing it any other way would test a thing nobody ships.
    """
    found = []
    if not THE_EXTRACTED.is_dir():
        return found
    for package in sorted(p for p in THE_EXTRACTED.iterdir() if p.is_dir()):
        tests = package / "tests"
        if not tests.is_dir():
            continue
        if str(package) not in sys.path:
            sys.path.insert(0, str(package))
        found.append(loader.discover(str(tests), top_level_dir=str(tests)))
    return found


def _run_the_suite(argv: list[str], verbosity: int, lock=None) -> int:
    """Discover, count, run, compare. Split out so the lock is released on
    every path out of it, including the early returns."""
    head_at_the_start = the_head_now()
    tracked_at_the_start = the_tracked_files_now()

    loader = unittest.defaultTestLoader
    suite = loader.discover(str(REPO / "tests"), top_level_dir=str(REPO / "tests"))
    #: STILL ONE DISCOVERY IN THE SENSE THAT MATTERS. The law above is that the
    #: collection counted is the collection run; it is not that there may only
    #: be one root. These are folded into `suite` BEFORE the count, so the
    #: number below and the run below are the same object.
    for extracted in the_extracted_suites(loader):
        #: MATERIALISED, AND NEVER ITSELF. `TestSuite.addTests` iterates its
        #: argument while appending to `self`, so handing it the suite it is
        #: appending to appends forever. That is not hypothetical: the gate's
        #: own self-tests stub `loader.discover` to return ONE suite object for
        #: every call, so the second discovery returned the first suite and this
        #: line grew a list until the interpreter raised `MemoryError`. Four
        #: tests caught it on the first full run after the change.
        if extracted is suite:
            continue
        suite.addTests(list(extracted))
    discovered = how_many_tests_are_in(suite)

    unimported = the_modules_that_did_not_import(suite)
    if unimported:
        # Discovery itself failed on a module. Those become `_FailedTest`
        # entries that run and error, so the count still holds - but say so,
        # because a reader seeing a smaller number deserves the reason here
        # rather than in a traceback four hundred lines down. It is said again
        # at the END, where a reader actually looks.
        print(f"discovery could not import: {', '.join(unimported)}", flush=True)

    print(f"discovered {discovered} tests", flush=True)
    # A GATE THAT IS KILLED MUST NOT READ AS A GATE THAT PASSED.
    #
    # Measured 2026-09-05: a run killed mid-suite left "discovered 3958 tests"
    # and a stream of dots. No RED, no GREEN, grep count zero for either - and
    # a reader grepping for failures finds none, which is one glance away from
    # "it was fine". The count assertion below cannot help, because the process
    # that would have made it is the one that went away.
    #
    # A signal handler would not close it either: on Windows the kill that did
    # this is TerminateProcess, which is not catchable. So the run states its
    # own contract up front, and the absence of the closing line becomes
    # evidence instead of silence.
    print(what_a_finished_run_looks_like(), flush=True)
    neighbours = other_suites_running_now()
    if neighbours:
        print(
            f"NOT ALONE ON THIS MACHINE: {len(neighbours)} other suite(s) are running "
            "while this one starts. The count check below still decides green or red; "
            "this is here so a green result is not read as a run that had the machine "
            "to itself.",
            flush=True,
        )
        for line in neighbours:
            print(f"  {line}", flush=True)
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    ran = result.testsRun

    print(f"\nran {ran} of {discovered} discovered")
    if ran != discovered:
        print(why_the_count_is_red(discovered, ran), file=sys.stderr)
        return 2
    if unimported:
        #: Checked AFTER the count and BEFORE the pass/fail, because a module
        #: that did not import is the same family as a count mismatch - the run
        #: does not say what the tree does - and it must not be reported as an
        #: ordinary red test.
        print(why_the_import_errors_are_red(unimported), file=sys.stderr)
        return 2
    head_at_the_end = the_head_now()
    if the_run_is_not_about_one_tree(head_at_the_start, head_at_the_end):
        #: Same family again, and the one that caught me twice in an hour.
        print(why_the_moved_head_is_red(head_at_the_start, head_at_the_end),
              file=sys.stderr)
        return 2
    tracked_at_the_end = the_tracked_files_now()
    moved = (tracked_at_the_start is not None
             and tracked_at_the_end is not None
             and tracked_at_the_start != tracked_at_the_end)
    if moved:
        #: ABOVE THE VERDICT, NOT BELOW IT. The first draft printed GATE IS
        #: GREEN and then said the tree had moved, which is the green-lie
        #: shape this repository lost twelve minutes to earlier today.
        print(why_the_tree_moved_under_the_run(tracked_at_the_start,
                                              tracked_at_the_end), file=sys.stderr)
        return 2
    material = the_skips_that_matter(result)
    if not result.wasSuccessful():
        return 1
    # ITEM 37. The neighbours are named at the START, and a reader scrolls to
    # the VERDICT - which is what a reader does. A qualification 4,000 dots
    # above the line it qualifies is a qualification nobody reads, so the
    # verdict carries it. Re-read here rather than passed down from the top:
    # a suite that started alone and finished beside three others ran beside
    # them, and the number at the start would have said it was alone.
    beside = other_suites_running_now()
    if material:
        #: NOT A BARE PASS AND NOT A REFUSAL. This exited 2 for about an hour,
        #: and a peer measured what that did: a FRESH CLONE COULD NEVER BE
        #: GREEN, because the skip is a gitignored file of personal identifiers
        #: that a visitor can never legitimately have. The suite became
        #: structurally un-passable for everyone except this machine, and the
        #: two checkouts that could have noticed had both just stopped being
        #: able to.
        #:
        #: The distinction that settles it: "the identifier rules did not run"
        #: means THIS RUN CANNOT CERTIFY A RELEASE. It does not mean the 4,435
        #: tests said nothing about the tree, and the second is the claim a gate
        #: makes. So the qualification goes in the verdict LINE rather than four
        #: thousand dots above it, the exit code stays 0 because the tests
        #: passed, and the refusal moves to the release path where it belongs -
        #: `push_if_green` will not push from a checkout that cannot run them.
        print(
            f"GATE IS GREEN FOR THIS TREE, NOT FOR RELEASE: {ran} of {discovered} "
            f"passed, and {len(material)} check(s) could not run here"
            + (f" (ran beside {len(beside)} other suite(s))" if beside else "")
        )
        for case, reason in material:
            print(f"  {case}{NEWLINE}    {reason}")
        print(
            "Nothing is wrong with the tree. This run cannot certify a release, "
            "and `push_if_green` refuses on that separately."
        )
    else:
        print(
            f"GATE IS GREEN: {ran} of {discovered}"
            + (f" (ran beside {len(beside)} other suite(s) on this machine)" if beside else "")
        )
    # THE QUALIFICATIONS GO WITH THE VERDICT, for item 37's reason: a
    # qualification 4,000 dots above the line it qualifies is one nobody
    # reads. A skip reason printed at the moment of the skip is exactly that.
    reasons = what_the_skips_were(result.skipped)
    if reasons:
        print(f"  and {len(result.skipped)} skipped, for {len(reasons)} "
              "distinct reason(s) - a skip is a partial result wearing a pass:")
        for line in reasons:
            print(f"  {line}")
    # THE BOOKKEEPING MUST NOT DECIDE THE VERDICT. This line crashed on its
    # first real run - `lock` was a name in the caller, not here - AFTER
    # printing GATE IS GREEN, and the gate exited 1 on a tree with 4,397 of
    # 4,397 passing. `push_if_green` read the exit code and refused, which is
    # the only reason this was a wasted run rather than a green lie. A record
    # that can turn a green gate red is worse than no record.
    try:
        remember(ran=ran, discovered=discovered, beside=len(beside),
                 waited=the_wait_this_run_paid(lock),
                 skipped=len(result.skipped))
    except Exception as why:  # noqa: BLE001 - the verdict outranks the ledger
        print(f"gate: the run was not recorded ({why!r}). The verdict above "
              "stands; only the history lost a row.", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(the_gate())
