"""An open handle is not a live process, and believing it was emptied the app.

## What happened, on the owner's machine, 2026-09-11

He restarted ML Harness and his conversations were gone from the rail. Nothing
was lost - the database was intact, the engine was healthy, `/health` answered
`status: ok` and named the right file with 1122 runs in it. What had happened
is that the engine declined to publish its token.

`write_portfile` refuses to overwrite a portfile owned by a process that is
still running, and that rule is right: two engines racing to own one token is
how a job authenticates against a secret nobody is listening for. The fault was
in how "still running" was answered.

Windows keeps a pid resolvable while ANY handle to it remains open, even after
the process has exited. `OpenProcess` therefore succeeds on a dead pid whose
handle somebody still holds - and the Tauri shell holds exactly that:
`src-tauri/src/engine.rs` keeps the spawned engine's `Child` in `OURS` for the
life of the window.

So after the first restart, every new engine saw the previous one as a live
incumbent, deferred, and left `engine.json` naming a token the listening engine
had never heard of. Every local client got 401. The app opened with an empty
rail. Deleting the file by hand and restarting brought all sixty-three threads
back, which is what proved the diagnosis.

## Why this test can actually fail

The condition is reproducible without mocking anything: start a child, wait for
it to exit, and keep the handle by keeping the `Popen`. That is the shell's
situation exactly. Before the fix this test's central assertion is False; after
it, True.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import security  # noqa: E402


class ADeadProcessReadsAsDeadTest(unittest.TestCase):
    def test_this_process_is_running(self):
        """The easy direction, which the old version also got right."""
        self.assertTrue(security._pid_is_running(os.getpid()))

    def test_a_pid_that_never_existed_is_not_running(self):
        self.assertFalse(security._pid_is_running(999_999_999))
        for nonsense in (None, "", "abc", -1, 0):
            self.assertFalse(security._pid_is_running(nonsense))

    def test_an_exited_child_whose_handle_is_still_held_reads_as_dead(self):
        """THE ONE. This is the shell's situation, reproduced.

        `subprocess.Popen` keeps a handle to the child on Windows until it is
        garbage collected, so the pid stays openable after the process exits -
        which is why the reference to `child` is kept alive deliberately below
        rather than being allowed to fall out of scope.
        """
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait()
        time.sleep(0.2)
        try:
            self.assertFalse(
                security._pid_is_running(child.pid),
                "an exited process read as alive, which is what made a new "
                "engine defer to a dead one and leave clients on a token "
                "nothing would accept",
            )
        finally:
            #: Held until after the assertion ON PURPOSE - releasing it first
            #: would close the handle and make the test pass for the wrong
            #: reason, which is the failure mode this whole file is about.
            self.assertIsNotNone(child.pid)

    def test_a_live_child_reads_as_alive(self):
        """The fix must not simply answer False to everything.

        A check that called every process dead would let two engines fight over
        one portfile, which is the fault `write_portfile`'s rule exists to
        prevent. Each direction needs a case that produces only it.
        """
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"]
        )
        try:
            time.sleep(0.3)
            self.assertTrue(security._pid_is_running(child.pid))
        finally:
            child.kill()
            child.wait()


if __name__ == "__main__":
    unittest.main()
