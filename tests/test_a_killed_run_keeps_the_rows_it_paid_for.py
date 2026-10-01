"""A run killed mid-loop leaves the rows it already paid for.

MEASURED 2026-09-07, and it is about to be spent. The rented hour is priced at
**0.98 h against a 1 h ceiling**, so the likely death is the hour ending - and
`the_second_judge_pass.py` used to build its whole record in memory and write it
once after the loop (`results.jsonl`, one `write_text`, line 229 of the old
file). Killed on row 71 of 72, that left **nothing**: $0.74 for zero rows and no
measurement.

THE PER-ROW `except` LOOKED LIKE DURABILITY AND WAS NOT. It builds an aborted row
*at the moment of failure* - which is why the row carries the real error rather
than a reconstruction - and then appends it to the same in-memory list as
everything else. **Both failures left the same thing on disk: nothing.** I had
read that comment's "written" as persistence and repeated it, and a neighbouring
lane read the line numbers instead.

WHY THIS FILE KILLS A PROCESS RATHER THAN CHECKING FOR `flush()`. A test that
greps for `.flush()` passes on code that flushes into a handle nobody opened, and
passes on code that opens the handle after the loop. **The claim is that bytes
survive a death**, so the only honest check is to kill something and read what is
left. This starts a real subprocess writing rows the same way, kills it partway,
and reads the file the dead process left behind.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

import support


#: The shape `the_second_judge_pass.py` now uses: open once, write and flush per
#: row, close at the end. Deliberately a copy of the SHAPE and not an import -
#: importing the real module would need an engine, a lock and a card, and a test
#: that needs a GPU is a test nobody runs.
A_RUN_THAT_WRITES_AS_IT_GOES = textwrap.dedent(
    """
    import json, sys, time
    from pathlib import Path

    out = Path(sys.argv[1])
    rolling = out.open("w", encoding="utf-8")
    results = []

    def keep(entry):
        results.append(entry)
        rolling.write(json.dumps(entry, ensure_ascii=False) + chr(10))
        rolling.flush()

    for number in range(1, 73):
        keep({"row": number, "outcome": "answered"})
        time.sleep(0.05)
    rolling.close()
    """
)

A_RUN_THAT_WRITES_AT_THE_END = textwrap.dedent(
    """
    import json, sys, time
    from pathlib import Path

    out = Path(sys.argv[1])
    results = []
    for number in range(1, 73):
        results.append({"row": number, "outcome": "answered"})
        time.sleep(0.3)
    out.write_text(chr(10).join(json.dumps(r) for r in results) + chr(10), encoding="utf-8")
    """
)


#: How long to keep looking before killing. Generous, because it is a CEILING
#: and not a wait: the rolling case stops the moment it sees a row.
THE_LONGEST_WE_LOOK = 20.0

#: The control writes nothing until it FINISHES, and it needs 72 x 0.3 s to do
#: that - so three seconds is ample to show it left nothing, and twenty would be
#: sixty seconds of the suite spent proving the same thing three times.
THE_CONTROL_CEILING = 3.0


def rows_on_disk(out: Path) -> int:
    """Rows currently readable, tolerating a half-written last line.

    A process killed mid-`write` can leave a partial line, and a counter that
    raised on it would turn a durability test into a JSON test.
    """
    if not out.is_file():
        return 0
    found = 0
    for line in out.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError:
            continue  # a torn final row is not a row, and not an error either
        found += 1
    return found


def rows_left_after_killing(program: str, want: int, ceiling: float | None = None) -> int:
    """Start it, kill it once `want` rows are on disk (or `ceiling` passes), count.

    THE CEILING DIFFERS BY CASE AND THAT IS THE POINT. The rolling run stops the
    instant it sees rows, so its ceiling is only a safety net. The control can
    never produce a row before it finishes - it needs 21.6 s of sleeps and gets
    far less - so a short ceiling is enough to show it wrote nothing, and a long
    one would spend twenty seconds proving it three times over. A slow suite is
    a suite people skip.

    POLLED, NOT SLEPT, AND THE FIRST VERSION SLEPT. It waited a fixed 0.9 s and
    then killed - which is a bet that the machine writes a row in 0.9 s. On a
    loaded machine it does not: this suite went red on a CLEAN tree while a full
    gate ran beside it, and the failure said "a killed run left no rows at all"
    about code that was working perfectly.

    A TEST THAT FAILS WHEN THE MACHINE IS BUSY IS A TEST PEOPLE RE-RUN, and a
    test people re-run is a test nobody believes. Waiting for the condition
    instead of for the clock makes the rolling case fast AND reliable; the
    write-at-the-end control still gets the full ceiling, because proving it
    wrote nothing means giving it every chance to.
    """
    #: `ignore_cleanup_errors` BECAUSE THIS KILLS PROCESSES ON WINDOWS.
    #:
    #: MEASURED: this suite passed six times in a row and then failed inside
    #: `push_if_green`'s gate with `PermissionError: [WinError 32] The process
    #: cannot access the file because it is being used by another process`, on
    #: `results.jsonl`, during `TemporaryDirectory.cleanup()`.
    #:
    #: `kill()` is asynchronous and `wait()` reaps the process, but Windows does
    #: not guarantee the child's file handle is released by the time the parent
    #: continues - so the directory is still in use when the context manager
    #: tries to remove it. **The count has already been taken by then**, so this
    #: is a tidying failure being reported as a test failure, and a durability
    #: test that goes red because a temp directory would not delete is telling
    #: the reader something false about the product.
    #:
    #: THIS IS THE SECOND FLAKE IN THIS FILE. The first was a fixed sleep; both
    #: come from spawning and killing real processes, which is also the reason
    #: the test is worth having - the honest response is to make the harness
    #: robust, not to stop killing things.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        script = Path(tmp) / "run.py"
        script.write_text(program, encoding="utf-8")
        out = Path(tmp) / "results.jsonl"
        process = subprocess.Popen(
            [sys.executable, str(script), str(out)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + (ceiling or THE_LONGEST_WE_LOOK)
            while time.monotonic() < deadline:
                if rows_on_disk(out) >= want:
                    break
                if process.poll() is not None:
                    break  # it finished on its own; count what it left
                time.sleep(0.02)
            process.kill()
            process.wait(timeout=30)
        finally:
            if process.poll() is None:  # pragma: no cover - belt and braces
                process.kill()
                process.wait(timeout=30)
        #: COUNTED BEFORE THE DIRECTORY GOES, so the answer never depends on
        #: whether the cleanup succeeds. Reading here rather than after the
        #: `with` is what makes `ignore_cleanup_errors` safe: the measurement is
        #: already taken by the time anything is deleted.
        left = rows_on_disk(out)
        #: A short settle so the common case still cleans up. Not correctness -
        #: `ignore_cleanup_errors` is the correctness - just tidiness, and
        #: bounded so a busy machine cannot make it slow.
        for _ in range(20):
            try:
                out.unlink(missing_ok=True)
                break
            except OSError:
                time.sleep(0.05)
        return left


class AKilledRunKeepsWhatItPaidForTest(unittest.TestCase):
    """THE CASE, and it is a kill rather than an assertion about source."""

    def test_writing_as_it_goes_survives_the_kill(self):
        left = rows_left_after_killing(A_RUN_THAT_WRITES_AS_IT_GOES, want=3)
        self.assertGreater(left, 0, "a killed run left no rows at all")

    def test_writing_at_the_end_loses_everything(self):
        """THE CONTROL, and without it the test above proves nothing. If the old
        shape also survived, the change would be decoration."""
        left = rows_left_after_killing(A_RUN_THAT_WRITES_AT_THE_END, want=3, ceiling=THE_CONTROL_CEILING)
        self.assertEqual(left, 0, "the write-at-the-end shape unexpectedly left rows")

    def test_the_difference_is_the_whole_point(self):
        rolling = rows_left_after_killing(A_RUN_THAT_WRITES_AS_IT_GOES, want=3)
        at_end = rows_left_after_killing(A_RUN_THAT_WRITES_AT_THE_END, want=3, ceiling=THE_CONTROL_CEILING)
        self.assertGreater(
            rolling, at_end,
            "per-row writing kept no more than writing once at the end",
        )


class TheJudgePassUsesThatShapeTest(unittest.TestCase):
    """The kill above proves the shape works. This proves the product uses it."""

    def source(self):
        return (support.REPO_ROOT / "scripts" / "the_second_judge_pass.py").read_text(
            encoding="utf-8"
        )

    def test_the_handle_is_opened_before_the_loop(self):
        source = self.source()
        opened = source.index('rolling = (OUT / "results.jsonl").open(')
        loop = source.index("for number, row in enumerate(rows, 1):")
        self.assertLess(opened, loop, "the handle is opened after the loop it protects")

    def test_every_row_is_flushed_INSIDE_THE_PER_ROW_HELPER(self):
        """PARSED, NOT GREPPED, AND THIS ONE SURVIVED A MUTANT FIRST.

        The earlier version asserted the string `rolling.flush()` appeared
        ANYWHERE in the file. It does - the `finally` block has one too. So
        deleting the per-row flush, the single line the whole durability claim
        rests on, left this test GREEN. The mutant was planted and passed, which
        is the only reason it is known.

        The question is structural - *is the flush inside the function that runs
        once per row* - so `ast` answers it and `in` cannot. Eighth time today
        that a substring stood in for a structure.
        """
        import ast

        tree = ast.parse(self.source())
        keep = next(
            (n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "keep"),
            None,
        )
        self.assertIsNotNone(keep, "the per-row helper `keep` is gone")
        calls = {
            f"{c.func.value.id}.{c.func.attr}"
            for c in ast.walk(keep)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
            and isinstance(c.func.value, ast.Name)
        }
        self.assertIn("rolling.write", calls, "keep() does not write the row")
        self.assertIn("rolling.flush", calls, "keep() writes the row and does not flush it")

    def the_row_loop(self):
        """The `for` that runs once per row - `for ... in enumerate(rows, 1)`.

        Found by its ITERATOR rather than by position, so renaming the loop
        variable or moving the loop does not silently select a different one.
        """
        import ast

        for node in ast.walk(ast.parse(self.source())):
            if not isinstance(node, ast.For):
                continue
            it = node.iter
            if (isinstance(it, ast.Call) and isinstance(it.func, ast.Name)
                    and it.func.id == "enumerate"
                    and any(isinstance(a, ast.Name) and a.id == "rows" for a in it.args)):
                return node
        self.fail("the per-row loop `for ... in enumerate(rows, 1)` is gone")

    def test_the_row_loop_ITSELF_calls_the_helper(self):
        """THE HOLE THIS TEST SHIPPED WITH, AND THE COMMIT MESSAGE WAS WORSE.

        The first version walked the WHOLE MODULE and asserted `keep` appeared
        among the called names - so *keep is called somewhere* passed, and a
        mutant hoisting the call OUT of the row loop satisfied it. The second
        assertion did not close it either: it looked for `results.append` inside
        any `For`, which a loop collecting into a differently-named list escapes.

        And the commit message said *"one asserting the loop calls that
        function"* when the assertion said *the module calls it somewhere*. THE
        MESSAGE CLAIMED MORE THAN THE TEST ASSERTED - the same fault as the
        write-once comment it was correcting in the same commit, where a
        protection was described more widely than it reached.

        So: unparse THAT LOOP ALONE and require the call inside it.
        """
        import ast

        inside = ast.unparse(self.the_row_loop())
        self.assertIn(
            "keep(", inside,
            "the row loop does not call keep(), so rows reach the list without "
            "reaching the disk - a hoisted call passes the old check and fails this",
        )

    def test_the_loop_does_not_collect_without_writing(self):
        """The other way round the same hole: appending inside the loop and
        writing afterwards. Any `.append(` in the row loop is a row that reached
        memory without reaching disk."""
        import ast

        inside = ast.unparse(self.the_row_loop())
        self.assertNotIn(
            ".append(", inside,
            "a row is appended inside the loop, bypassing the per-row write",
        )

    def test_both_the_answered_and_the_aborted_row_go_through_it(self):
        """The aborted row is the one that used to LOOK durable. Both paths must
        reach disk, or a run that fails is a run with no record of failing."""
        source = self.source()
        self.assertIn("keep(aborted)", source)
        self.assertIn("keep(\n", source)
        self.assertNotIn("results.append(aborted)", source)

    def test_nothing_writes_the_whole_record_at_the_end_any_more(self):
        source = self.source()
        self.assertNotIn('(OUT / "results.jsonl").write_text(', source)

    def test_the_handle_is_closed_on_every_path_out(self):
        """Nothing is lost if this is missed - the rows were flushed - but a
        handle left open by an exception is closed at the operating system's
        convenience, and "it works because the process exited" is not a
        durability argument."""
        source = self.source()
        finally_block = source[source.index("    finally:"):]
        self.assertIn("rolling", finally_block)
        self.assertIn("not rolling.closed", finally_block)

    def test_the_close_survives_an_exception_raised_before_the_handle_existed(self):
        """`rolling` is a local that may never have been bound. Bookkeeping must
        never raise into a verdict."""
        source = self.source()
        self.assertIn('locals().get("rolling")', source)


if __name__ == "__main__":
    unittest.main()
