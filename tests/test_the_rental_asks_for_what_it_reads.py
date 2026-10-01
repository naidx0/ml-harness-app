"""The rental asks for the rows its workload reads, and counts them from the file.

MEASURED 2026-09-07. `what_would_go` globbed `(REPO / "runs").rglob("*.jsonl")` -
every row file in the tree - so `--plan` printed **88 refused paths** and the fix
it demanded was a person approving all 88 by name.

**THAT IS NOT A DECISION A PERSON CAN MAKE.** An unreadable list is how a guard
gets waved through, and a guard that is waved through is no guard at all while
looking like more. The design was right - a person names the files, and the
script may not widen its own upload rule. The defect was asking for a tree when
the pinned workload reads ONE file.

Meanwhile the page said *"All seven are refused."* Seven, against a code path
that wanted 88. **The page had been wrong about the same number twice, in
opposite directions**, which is what a count carried in prose does.

AND FIXING IT CHANGED THE ANSWER. `CALLS = 60` was a round number nothing
derived. One call per recorded row is 72, and at 49 s/call that is 0.98 h -
about a minute inside the hour, where 60 left eleven. A round number had been
making a tight budget look comfortable, which is the reason to derive counts and
not the decoration on it.

This file has no predecessor: there were no tests for `rent_an_hour.py` at all.
"""

from __future__ import annotations

import unittest

import support

rental = support.import_file(
    "rent_an_hour", support.REPO_ROOT / "scripts" / "rent_an_hour.py"
)


class ItAsksForOneRowFileAndNotATreeTest(unittest.TestCase):
    """THE CASE."""

    def test_it_names_the_file_rather_than_globbing_runs(self):
        """THE FUNCTION, not the whole file. Two earlier versions of this test
        searched the entire source and matched the COMMENT that explains the
        glob was removed - a check that fails on its own record of the fix, and
        which dumped four hundred lines of source into the failure message on
        the way. `inspect.getsource` asks the narrow question."""
        import inspect

        body = inspect.getsource(rental.what_would_go)
        self.assertNotIn("rglob", body, "the tree glob came back in what_would_go")
        self.assertIn("THE_ROWS", body)

    def test_the_named_file_is_under_runs_and_is_a_single_path(self):
        self.assertIn("runs", rental.THE_ROWS.parts)
        self.assertTrue(str(rental.THE_ROWS).endswith(".jsonl"))

    def test_the_ask_is_short_enough_for_a_person_to_read(self):
        """The whole point. 88 paths is a list nobody reads; a handful is a list
        somebody can check line by line before approving it."""
        allowed, refused = rental.what_would_go()
        self.assertLessEqual(
            len(allowed) + len(refused),
            5,
            "the rental is asking for more paths than a person can actually approve",
        )

    def test_only_the_named_row_file_is_asked_for(self):
        allowed, refused = rental.what_would_go()
        rows = [p for p in allowed + refused if p.startswith("runs/")]
        self.assertLessEqual(len(rows), 1, f"more than one row file asked for: {rows}")


class ThePolicyStillDecidesTest(unittest.TestCase):
    """Narrowing what is ASKED FOR must not widen what is GRANTED.

    A rental script that can widen its own upload rule is not bounded by it, and
    that invariant is the reason the rest of this is safe.
    """

    def test_the_row_file_is_still_refused(self):
        allowed, refused = rental.what_would_go()
        if not rental.THE_ROWS.exists():
            self.skipTest("runs/ is gitignored; this checks the real artefact when it exists")
        wanted = rental.THE_ROWS.relative_to(support.REPO_ROOT).as_posix()
        self.assertIn(wanted, refused, "the row file became allowed without a person naming it")
        self.assertNotIn(wanted, allowed)

    def test_the_script_never_mutates_the_upload_rule(self):
        """PARSED, NOT GREPPED, and it took four tries to learn that here.

        `FORCE_INCLUDE` appears in this script twice: in a docstring, and in the
        sentence the plan PRINTS to tell a person what they must do. Both are
        mentions. A substring search cannot tell a mention from a mutation - the
        same lesson `test_a_script_imports_its_own_app` records, where a regex
        matched itself.

        What must not exist is an assignment to it, an `.append` on it, or a
        file write anywhere in this module. That is a question about syntax, so
        `ast` answers it and `in` does not.
        """
        import ast

        tree = ast.parse(
            (support.REPO_ROOT / "scripts" / "rent_an_hour.py").read_text(encoding="utf-8")
        )
        def names(node):
            """Every dotted name in an expression: `policy.FORCE_INCLUDE` gives
            both halves. THE FIRST VERSION ONLY LOOKED AT `ast.Name`, so it
            missed `policy.FORCE_INCLUDE.append(...)` - which is not an exotic
            spelling, it is THE way another module's list gets widened. A
            planted mutant doing exactly that came back green."""
            found = []
            while isinstance(node, ast.Attribute):
                found.append(node.attr)
                node = node.value
            if isinstance(node, ast.Name):
                found.append(node.id)
            return found

        MUTATES = {"append", "extend", "insert", "add", "update", "__setitem__"}
        offences = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if any("FORCE_INCLUDE" in n for n in names(target)):
                        offences.append("assigns FORCE_INCLUDE")
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute):
                    if func.attr in {"write_text", "write_bytes", "mkdir", "unlink"}:
                        offences.append(f"calls .{func.attr}()")
                    if func.attr in MUTATES and any(
                        "FORCE_INCLUDE" in n for n in names(func.value)
                    ):
                        offences.append(f"mutates FORCE_INCLUDE via .{func.attr}()")
                if isinstance(func, ast.Name) and func.id == "open":
                    mode = next((a for a in node.args[1:2]), None)
                    if isinstance(mode, ast.Constant) and any(
                        c in str(mode.value) for c in "wax+"
                    ):
                        offences.append(f"opens for writing: {mode.value!r}")
        self.assertEqual(
            offences, [], "the rental script writes where it should only report"
        )

    def test_it_does_still_tell_a_person_what_to_do(self):
        """The counterpart. Refusing to punch the hole is only useful if the
        refusal says who can and how - otherwise it is a dead end wearing a
        guard's clothes."""
        if not rental.THE_ROWS.exists():
            self.skipTest("runs/ is gitignored; this checks the real artefact when it exists")
        said = rental.the_plan()
        self.assertIn("FORCE_INCLUDE", said)
        self.assertIn("not a fix this script may make for itself", said)

    def test_it_still_asks_the_policy_rather_than_deciding_itself(self):
        source = (support.REPO_ROOT / "scripts" / "rent_an_hour.py").read_text(encoding="utf-8")
        self.assertIn("policy.decide(path)", source)


class TheCountComesFromTheFileTest(unittest.TestCase):
    """A number nothing derives is a number nothing checks."""

    def test_there_is_no_hardcoded_calls_constant(self):
        import re

        source = (support.REPO_ROOT / "scripts" / "rent_an_hour.py").read_text(encoding="utf-8")
        # THE ASSIGNMENT, not any mention of it. The first version of this test
        # searched the whole source for the string and matched the comment that
        # explains the constant was REMOVED - a check that fails on its own
        # documentation of the fix.
        self.assertIsNone(
            re.search(r"^CALLS\s*=", source, re.M), "the round number came back"
        )

    def test_the_call_count_equals_the_rows(self):
        if not rental.THE_ROWS.exists():
            self.skipTest("runs/ is gitignored; this checks the real artefact when it exists")
        self.assertEqual(rental.the_calls(), rental.how_many_rows())
        self.assertGreater(rental.the_calls(), 10)

    def test_a_missing_row_file_is_unknown_and_not_zero(self):
        """UNMEASURABLE RENDERS UNKNOWN. A clone has no `runs/`, and a plan
        reporting "0 calls" there would describe a workload nobody can run as
        though it were a cheap one."""
        from pathlib import Path

        real = rental.THE_ROWS
        try:
            rental.THE_ROWS = Path("no-such-file-anywhere.jsonl")
            self.assertIsNone(rental.how_many_rows())
            self.assertIsNone(rental.the_calls())
            self.assertIn("UNKNOWN", rental.the_plan())
            self.assertNotIn("0 calls", rental.the_plan())
        finally:
            rental.THE_ROWS = real

    def test_blank_lines_are_not_counted_as_rows(self):
        import tempfile
        from pathlib import Path

        real = rental.THE_ROWS
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "rows.jsonl"
                path.write_text('{"a":1}\n\n{"a":2}\n\n', encoding="utf-8")
                rental.THE_ROWS = path
                self.assertEqual(rental.how_many_rows(), 2)
        finally:
            rental.THE_ROWS = real


class ItCountsRecordsAndNotNewlinesTest(unittest.TestCase):
    """The pinned file has no trailing newline, so the two counts differ by one.

    MEASURED 2026-09-07 on the real artefact. `judge-sentinel-n/results.jsonl`
    ends `...se}`: **71 newline characters, 72 records**. Its neighbours all end
    with a newline and report 72 either way - so the ONE file this rental pins is
    the one where the counts diverge, and it diverges downward.

    DERIVING A COUNT PROTECTS IT FROM GOING STALE. IT DOES NOT PROTECT IT FROM
    COUNTING THE WRONG UNIT. A `wc -l` derivation would be just as derived, just
    as self-updating, and one short - and more convincing than a typed number,
    because it carries the authority of having been computed.
    """

    def the_file(self):
        if not rental.THE_ROWS.is_file():
            self.skipTest("runs/ is gitignored; this checks the real artefact when it exists")
        return rental.THE_ROWS.read_bytes()

    def test_the_two_counts_really_do_differ_on_this_file(self):
        """THE CASE THAT MAKES THE REST MEAN ANYTHING. On a file ending with a
        newline both methods agree and this test would pass while checking
        nothing - so it asserts the divergence exists before asserting which
        side is taken."""
        raw = self.the_file()
        newlines = raw.count(b"\n")
        records = sum(1 for line in raw.decode("utf-8").splitlines() if line.strip())
        self.assertNotEqual(
            newlines, records,
            "this file now ends with a newline, so the two counts agree and this "
            "test can no longer fail - pin a file where they differ, or delete it",
        )
        self.assertEqual(records, newlines + 1)

    def test_the_count_takes_the_record_side(self):
        raw = self.the_file()
        records = sum(1 for line in raw.decode("utf-8").splitlines() if line.strip())
        self.assertEqual(
            rental.how_many_rows(), records,
            "how_many_rows() is counting newlines, which is one short on this file",
        )

    def test_it_is_not_the_newline_count(self):
        raw = self.the_file()
        self.assertNotEqual(
            rental.how_many_rows(), raw.count(b"\n"),
            "the hour would be priced on 71 rows of a 72-row file",
        )

    def test_a_file_with_no_trailing_newline_still_counts_its_last_record(self):
        """The property, on a fixture, so it holds when `runs/` is absent."""
        import tempfile
        from pathlib import Path

        real = rental.THE_ROWS
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "rows.jsonl"
                path.write_bytes(b'{"a":1}\n{"a":2}\n{"a":3}')  # no trailing newline
                rental.THE_ROWS = path
                self.assertEqual(rental.how_many_rows(), 3)
        finally:
            rental.THE_ROWS = real

    def test_the_docstring_says_records_not_lines(self):
        """Anything else that later reads this file for a count - a report, a
        check, a shell one-liner in a commit message - gets 71 unless it makes
        the same choice. The reason has to be where the next reader looks."""
        said = rental.how_many_rows.__doc__
        self.assertIn("RECORDS, NOT LINES", said)
        self.assertIn("71", said)
        self.assertIn("STALE", said)


class ThePlanSaysWhatTheHourActuallyBuysTest(unittest.TestCase):
    """The margin is the finding, so the plan has to print it."""

    def test_it_prints_the_hours_the_calls_take(self):
        if not rental.THE_ROWS.exists():
            self.skipTest("runs/ is gitignored; this checks the real artefact when it exists")
        said = rental.the_plan()
        self.assertIn("h,", said)
        self.assertIn("CEILING", said.upper())

    def test_a_workload_that_overruns_the_hour_says_so(self):
        """The branch nobody would otherwise exercise: at 72 calls the margin is
        about a minute, so a slower call makes the hour insufficient - and the
        plan must say NOT ENOUGH rather than printing a negative spare."""
        real = rental.SECONDS_PER_CALL_HERE
        try:
            rental.SECONDS_PER_CALL_HERE = 600.0
            if rental.the_calls() is None:
                self.skipTest("runs/ is gitignored; this checks the real artefact when it exists")
            self.assertIn("NOT ENOUGH", rental.the_plan())
        finally:
            rental.SECONDS_PER_CALL_HERE = real

    def test_the_blocked_block_lists_the_file_it_is_blocked_on(self):
        if not rental.THE_ROWS.exists():
            self.skipTest("runs/ is gitignored; this checks the real artefact when it exists")
        said = rental.the_plan()
        self.assertIn("BLOCKED", said)
        self.assertIn(rental.THE_ROWS.name, said)

    def test_nothing_is_spent_without_a_ceiling(self):
        """`--plan` and a bare invocation both stop. A script that could spend
        money the moment it is run is a script that will, by accident, once.

        WITH A ROWS FILE THAT EXISTS, because the exit under test is PLAN_ONLY
        and the module correctly returns CANNOT_COUNT when it cannot count.
        THE_ROWS is `runs/judge-sentinel-n/results.jsonl`, `runs/` is
        gitignored, and a gitignored file lives in a working TREE - so this
        asserted 0 in the checkout that had run the judge pass and got 4 in
        every other one, green in one tree and red in another with no
        difference in the code.
        """
        import io
        import json
        import shutil
        import tempfile
        from contextlib import redirect_stdout
        from pathlib import Path

        where = Path(tempfile.mkdtemp(dir=support.REPO_ROOT, prefix="mlh-rental-rows-"))
        self.addCleanup(shutil.rmtree, where, True)
        rows = where / "results.jsonl"
        with rows.open("w", encoding="utf-8", newline=chr(10)) as handle:
            for n in range(88):
                handle.write(json.dumps({"row_index": n, "answer": "x"}) + chr(10))

        was = rental.THE_ROWS
        rental.THE_ROWS = rows
        self.addCleanup(lambda: setattr(rental, "THE_ROWS", was))

        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(rental.main(["--plan"]), 0)
        self.assertIn("PLAN ONLY", out.getvalue())


class ThePageAndTheCodeAgreeTest(unittest.TestCase):
    """The page said seven; the code wanted 88. Neither number was checked."""

    def page(self):
        return (support.REPO_ROOT / "docs" / "rented-card-plan.md").read_text(encoding="utf-8")

    def test_the_page_no_longer_claims_seven(self):
        """THE LIVE CLAIM, not the quoted history. The correction quotes the
        sentence it corrects, on purpose - a correction that hides what it
        corrected teaches nobody - so a bare substring search fails on the very
        text that fixes the problem. The live sentence is the one outside the
        quotation marks."""
        page = self.page()
        self.assertNotIn("**They do not.** All seven are refused", page)
        self.assertIn('*"All seven are refused."*', page,
                      "the correction stopped quoting what it corrected")

    def test_the_page_records_both_wrong_numbers(self):
        """A correction that hides what it corrected teaches nobody."""
        page = self.page()
        self.assertIn("88", page)
        self.assertIn("seven", page.lower())

    def test_the_page_names_the_file_the_code_names(self):
        wanted = rental.THE_ROWS.relative_to(support.REPO_ROOT).as_posix()
        self.assertIn(wanted, self.page())

    def test_the_page_carries_the_new_margin(self):
        page = self.page()
        self.assertIn("0.98", page)
        self.assertIn("72", page)


class ThePageStatesTheFailureModeTheCodeActuallyHasTest(unittest.TestCase):
    """The page's claim about failure is COUPLED to the code that would fail.

    This page has been wrong about a number twice already, in opposite
    directions, because prose and code were not tied together. So this ties
    them: if somebody makes the judge pass write incrementally, this test goes
    red and the page has to be updated - rather than the page quietly describing
    a failure mode the code no longer has.
    """

    def judge_source(self):
        return (support.REPO_ROOT / "scripts" / "the_second_judge_pass.py").read_text(
            encoding="utf-8"
        )

    def page(self):
        return (support.REPO_ROOT / "docs" / "rented-card-plan.md").read_text(encoding="utf-8")

    def test_a_failed_call_is_still_caught_and_recorded(self):
        """The survivable half. A void call must not end the run."""
        source = self.judge_source()
        self.assertIn("an_aborted_row", source)
        self.assertIn("except (urllib.error.URLError, OSError, TimeoutError, ValueError)", source)

    def test_the_record_is_now_written_per_row(self):
        """THE COUPLING, INVERTED BY ITS OWN SUCCESS. This used to assert the
        write-once shape so that making the run resumable would go RED and force
        the page to be corrected. It did exactly that, and the page was
        corrected - so the assertion now holds the NEW property, and reverting to
        a single write at the end turns it red the other way.

        Narrowed to `inspect`-style slicing rather than searching the whole file:
        the earlier form dumped four hundred lines of source into the failure
        message, which is a test that is hard to read when it matters most.
        """
        source = self.judge_source()
        loop = source.index("for number, row in enumerate(rows, 1):")
        opened = source.index('rolling = (OUT / "results.jsonl").open(')
        self.assertLess(opened, loop, "the handle is opened after the loop it protects")
        self.assertIn("rolling.flush()", source)
        self.assertNotIn('(OUT / "results.jsonl").write_text(', source)

    def test_the_page_says_the_loss_is_now_partial(self):
        page = self.page()
        self.assertIn("Total loss became partial loss", page)
        self.assertIn("70 usable rows", page)

    def test_the_page_keeps_what_it_used_to_say_as_well_as_the_fix(self):
        """A correction that hides what it corrected teaches nobody, and this
        one is the useful half: `survivable` was describing control flow while
        sounding like durability."""
        page = self.page()
        self.assertIn("WHAT IT SAID", page)
        self.assertIn("WHAT IS TRUE NOW", page)
        self.assertIn("constructed", page)

    def test_the_page_says_a_void_call_is_survivable(self):
        """Both halves, because saying only the frightening one is its own
        distortion - a reader who thinks any failure ends the run would decline
        a rental that is actually robust to the common case."""
        self.assertIn("SURVIVABLE", self.page().upper())

    def test_the_page_gives_the_void_rate_measured_here(self):
        """From this machine's own records - not a rate borrowed from a
        neighbouring lane's different experiment."""
        page = self.page()
        self.assertIn("332", page)
        self.assertIn("named here rather", page)

    def test_the_page_states_the_denominator_of_the_332(self):
        """THE CORRECTION. "332 of 332" alone reads as *every call*, and it is
        three of twelve run files. The other nine hold rows whose outcome
        nothing stored - not zero void, NOBODY COUNTED, and the two need
        different words."""
        page = self.page()
        self.assertIn("680", page, "the uncounted rows are not on the page")
        self.assertIn("rows that record an outcome", page)
        self.assertIn("unmeasured", page)

    def test_the_page_says_the_number_cannot_be_checked_elsewhere(self):
        """`runs/` is gitignored, so no reader can resolve this on the remote.
        Presenting it as though a push would settle it was the second error in
        the same paragraph."""
        page = self.page()
        self.assertIn("UNVERIFIABLE-ELSEWHERE", page)
        self.assertIn("gitignored", page)

    def test_the_uncounted_rows_are_really_there(self):
        """The 680, re-derived rather than quoted - a corrected number needs
        checking as much as the one it corrects."""
        import json

        counted = uncounted = 0
        found = 0
        for path in sorted((support.REPO_ROOT / "runs").rglob("results.jsonl")):
            found += 1
            rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
            if rows and "outcome" in rows[0]:
                counted += len(rows)
            else:
                uncounted += len(rows)
        if not found:
            self.skipTest("runs/ is gitignored; this checks the real artefact when it exists")
        self.assertEqual((counted, uncounted), (332, 680), "the page's split has moved")

    def test_the_failure_mode_is_stated_independently_of_any_rate(self):
        """It is a property of the design, not a probability. True at a measured
        zero, and true if nobody had ever counted one."""
        page = self.page()
        self.assertIn("DOES NOT DEPEND ON ANY RATE", page)

    def test_the_measured_total_is_the_one_on_the_record(self):
        """The number in the prose, re-derived from the files it describes."""
        import json

        total = answered = 0
        for name in ("second-judge-pass", "sentinel-thinking-on", "sentinel-through-the-owner"):
            path = support.REPO_ROOT / "runs" / name / "results.jsonl"
            if not path.is_file():
                self.skipTest("runs/ is gitignored; this checks the real artefact when it exists")
            rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
            total += len(rows)
            answered += sum(1 for r in rows if r.get("outcome") == "answered")
        self.assertEqual((total, answered), (332, 332), "the page's 332 of 332 has moved")


if __name__ == "__main__":
    unittest.main()
