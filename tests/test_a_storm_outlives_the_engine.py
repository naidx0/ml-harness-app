"""A storm survives the engine being killed, the way a training run does.

`docs/THE_PROPOSAL_LOOP.md` promises long-running work that lives in the
conversation, and `app/events.py` explains why that is only true if every frame
a client ever sees is a committed row with an integer id. A storm is the same
promise one level up: hours of somebody's GPU and their model's tokens, spent
across a laptop lid closing.

So this file kills the engine. Not a mock, not a flag, not a simulated restart -
a real uvicorn process running a real storm, killed with its whole tree while a
step is in flight, and a second engine started against the same database that
has to say exactly what happened.

## What is asserted, and why each one could have gone wrong quietly

- **The storm is still there, and it is the same storm.** The manifest is a row
  that was written once, so the fingerprint the person approved is byte for byte
  what a new process reads.
- **The state comes out of the log rather than a guess.** A fresh engine folds
  `storm.step.finished` events into step states. Nothing is cached, so the two
  engines cannot disagree.
- **Nothing is silently restarted.** A step that finished before the kill has
  exactly ONE `storm.step.finished` event for the whole life of the storm, and
  its event id does not move when the storm is resumed. This is the assertion
  the whole file exists for: a resume that re-ran a completed step would repeat
  whatever it wrote, and the only evidence would be a second row in somebody's
  database.
- **A step that was interrupted is neither done nor queued.** It is `stalled`,
  and the storm refuses to carry on until the person says whether to run it
  again - because whether its work landed is not knowable from here, and
  guessing is how a dataset gets written twice.

The kill is made deterministic rather than left to a race: the test polls until
the first step has finished, which puts the engine inside the second one - the
count of a quarter of a million rows - and kills it there. The assertions do not
depend on that timing, but the coverage does, so it is arranged rather than
hoped for.

The in-process half of the same story is at the bottom of this file. A truncated
log - a `storm.step.started` with no finish - is what a killed engine leaves
behind, and `attach()` has to read it the same way whether the process died a
second ago or last week.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from app import events, storm
from app.tools import REGISTRY, evidence

import support


REPO_ROOT = Path(__file__).resolve().parents[1]

#: Pinned so the two engines and this test agree without any of them reading the
#: real `engine.json`. Same arrangement as `tests/test_demo_script_runs.py`.
TOKEN = "storm-survival-test-token"

STARTUP_TIMEOUT = 40.0

#: Big enough that counting it takes long enough to be killed in the middle of.
#: Measured on the machine this was written on: 200,000 rows is 0.40s and 13.5
#: MB, which is a window a 20 ms poll cannot miss and a file a temporary
#: directory does not mind.
EVAL_ROWS = 250_000


def kill_the_tree(process: subprocess.Popen) -> None:
    """Kill it the way the operating system kills things, not the way it asks.

    `terminate()` is a request, and a request is exactly what this test must not
    make: the engine would get the chance to finish what it was doing, and the
    thing being tested is what happens when it does not. The tree, because
    uvicorn is the parent of nothing here today and may not always be.
    """
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True
        )
    else:
        process.kill()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:  # pragma: no cover - the OS refused
        pass


class Engine:
    """One uvicorn process, and the small HTTP client this test drives it with."""

    def __init__(self, root: Path, database: Path, port: int) -> None:
        self.root = root
        self.database = database
        self.port = port
        self.log = root / f"engine-{port}.log"
        self.handle = self.log.open("w", encoding="utf-8")
        environment = os.environ.copy()
        environment["ML_HARNESS_DB"] = str(database)
        environment["MLH_PORT"] = str(port)
        environment["MLH_TOKEN"] = TOKEN
        environment["MLH_ENGINE_FILE"] = str(root / f"engine-{port}.json")
        self.process = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn", "app.main:app",
                "--host", "127.0.0.1", "--port", str(port),
                "--log-level", "warning",
            ],
            cwd=str(REPO_ROOT),
            env=environment,
            stdout=self.handle,
            stderr=subprocess.STDOUT,
        )
        self._wait_for_health()

    # -- lifecycle ---------------------------------------------------------

    def _wait_for_health(self) -> None:
        deadline = time.monotonic() + STARTUP_TIMEOUT
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise AssertionError(
                    f"engine exited {self.process.returncode} before answering:\n"
                    f"{self.output()}"
                )
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/health", timeout=1
                ) as response:
                    if response.status == 200:
                        return
            except (urllib.error.URLError, OSError):
                time.sleep(0.1)
        raise AssertionError(
            f"engine on {self.port} never answered:\n{self.output()}"
        )

    def output(self) -> str:
        try:
            return self.log.read_text(encoding="utf-8", errors="replace")
        except OSError:  # pragma: no cover
            return "<no engine log>"

    def stop(self) -> None:
        kill_the_tree(self.process)
        try:
            self.handle.close()
        except OSError:  # pragma: no cover
            pass

    # -- the client --------------------------------------------------------

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            method=method,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def get(self, path: str) -> dict:
        return self.call("GET", path)

    def post(self, path: str, body: dict | None = None) -> dict:
        return self.call("POST", path, body or {})


class AStormOutlivesTheEngineTest(unittest.TestCase):
    """One storm, one engine killed under it, one engine started over it.

    Class-level, because the thing being asserted is a single sequence of events
    and re-running it per assertion would be asserting about several different
    storms.
    """

    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._remove, temp)
        cls.root = Path(temp.name)
        cls.database = cls.root / "storm.db"

        cls.protected_before = {
            path: support.database_fingerprint(path)
            for path in support.PROTECTED_DATABASES
        }

        cls.evaluation = cls.root / "eval.jsonl"
        cls.evaluation.write_text(
            "\n".join(
                json.dumps({"q": f"support ticket number {i}", "a": "billing"})
                for i in range(EVAL_ROWS)
            ),
            encoding="utf-8",
        )

        first = Engine(cls.root, cls.database, support.free_port())
        cls.addClassCleanup(first.stop)
        cls._set_the_scene(first)
        cls.storm_id = cls._approve_and_start(first)
        cls.before_the_kill = cls._wait_until_a_step_has_finished(first)
        kill_the_tree(first.process)
        cls.engine_died_at = time.monotonic()

        # A SECOND ENGINE, ON THE SAME DATABASE, KNOWING NOTHING. It has never
        # heard of this storm except through the row and the log.
        second = Engine(cls.root, cls.database, support.free_port())
        cls.addClassCleanup(second.stop)
        cls.second = second
        cls.after_the_restart = second.get(f"/api/storms/{cls.storm_id}")
        cls.resumed = second.post(
            f"/api/storms/{cls.storm_id}/run",
            {
                "background": False,
                "restart_stalled": cls.after_the_restart["stalled"],
            },
        )
        cls.finally_ = second.get(f"/api/storms/{cls.storm_id}")
        cls.log = cls._storm_events(second, cls.storm_id)

        cls.protected_after = {
            path: support.database_fingerprint(path)
            for path in support.PROTECTED_DATABASES
        }

    # -- the sequence ------------------------------------------------------

    @classmethod
    def _set_the_scene(cls, engine: Engine) -> None:
        """A thread, and the facts a person would have stated to get this far."""
        thread = engine.post("/api/threads", {"title": "a storm that gets killed"})
        cls.thread_id = thread["id"]
        said = engine.post(
            "/api/tools/state_facts",
            {
                "arguments": {
                    "facts": {
                        "goal_text": "route support tickets",
                        "modality": "text",
                        "target_score": 0.9,
                    }
                },
                "thread_id": cls.thread_id,
            },
        )
        assert said["result"]["ok"], said

    @classmethod
    def _approve_and_start(cls, engine: Engine) -> int:
        proposal = {"facts": {}, "eval_path": str(cls.evaluation)}
        proposed = engine.post(
            "/api/tools/propose_build",
            {"arguments": proposal, "thread_id": cls.thread_id},
        )["result"]
        assert proposed["ok"], proposed
        cls.fingerprint = proposed["approve"]
        cls.build = proposed["build"]
        approved = engine.post(
            "/api/storms",
            {
                "thread_id": cls.thread_id,
                "approve": cls.fingerprint,
                "proposal": proposal,
            },
        )
        assert approved["state"] == "queued", approved
        engine.post(f"/api/storms/{approved['storm']}/run", {"background": True})
        return int(approved["storm"])

    @classmethod
    def _wait_until_a_step_has_finished(cls, engine: Engine) -> dict:
        """Poll until the first step is done, so the kill lands inside the second.

        The assertions below hold wherever the kill lands. This is here so that
        the interesting case - a step in flight, and a step already finished that
        must not be repeated - is the case that actually gets covered, rather
        than a case the test hopes a race produces.
        """
        deadline = time.monotonic() + 30.0
        seen = engine.get(f"/api/storms/{cls.storm_id}")
        while time.monotonic() < deadline:
            seen = engine.get(f"/api/storms/{cls.storm_id}")
            states = {node["id"]: node["state"] for node in seen["steps"]}
            if states.get("attach") == "done":
                return seen
            if seen["state"] in ("done", "failed", "cancelled"):
                return seen
            time.sleep(0.02)
        raise AssertionError(f"no step ever finished: {json.dumps(seen)[:2000]}")

    @classmethod
    def _storm_events(cls, engine: Engine, storm_id: int) -> list[dict]:
        """Every storm frame in the thread, read back off the replayable stream."""
        raw = urllib.request.Request(
            f"http://127.0.0.1:{engine.port}/api/events"
            f"?scope=thread:{cls.thread_id}&follow=false",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        with urllib.request.urlopen(raw, timeout=30) as response:
            text = response.read().decode("utf-8")
        frames = []
        for block in text.split("\n\n"):
            lines = [line for line in block.splitlines() if line.startswith(("id:", "event:", "data:"))]
            if len(lines) != 3:
                continue
            frames.append(
                {
                    "id": int(lines[0].split(":", 1)[1]),
                    "kind": lines[1].split(":", 1)[1].strip(),
                    "payload": json.loads(lines[2].split(":", 1)[1]),
                }
            )
        return [
            frame
            for frame in frames
            if frame["kind"] in storm.KINDS
            and int(frame["payload"].get("storm") or 0) == storm_id
        ]

    @classmethod
    def _remove(cls, temp):
        try:
            temp.cleanup()
        except (PermissionError, OSError):  # pragma: no cover - Windows handles
            pass

    # -- assertions --------------------------------------------------------

    def test_the_engine_really_did_die_with_the_storm_unfinished(self):
        """If this fails, nothing below is testing what it says it is."""
        self.assertNotIn(
            self.before_the_kill["state"], ("done", "failed", "cancelled")
        )
        self.assertIn(
            "done", [node["state"] for node in self.before_the_kill["steps"]]
        )

    def test_a_new_engine_reads_the_same_contract_off_the_same_row(self):
        self.assertEqual(
            self.after_the_restart["manifest"]["fingerprint"], self.fingerprint
        )
        self.assertEqual(
            self.after_the_restart["build"]["id"], self.build["id"]
        )
        self.assertEqual(
            [step["id"] for step in self.after_the_restart["build"]["steps"]],
            [step["id"] for step in self.build["steps"]],
        )

    def test_the_storm_is_neither_lost_nor_reported_as_running(self):
        """Nothing is live in this process, so nothing may claim to be."""
        self.assertFalse(self.after_the_restart["live"])
        self.assertNotIn(
            "running", [node["state"] for node in self.after_the_restart["steps"]]
        )
        self.assertIn(self.after_the_restart["state"], ("stalled", "waiting_input"))

    def test_a_step_that_was_in_flight_is_stalled_rather_than_guessed_at(self):
        interrupted = self.after_the_restart["stalled"]
        if not interrupted:
            self.skipTest("the kill landed between steps rather than inside one")
        for name in interrupted:
            node = next(
                item for item in self.after_the_restart["steps"] if item["id"] == name
            )
            self.assertEqual(node["state"], "stalled")
            self.assertIn("not knowable", node["because"])

    def test_a_finished_step_is_never_run_a_second_time(self):
        """THE ASSERTION THIS FILE EXISTS FOR.

        A step that finished before the engine died finished exactly once, for
        the whole life of the storm, and the id of the event that recorded it did
        not move when the storm was resumed. A resume that quietly re-ran a
        completed step would repeat whatever it had written, and this is the only
        place that would show.
        """
        finished_before = {
            node["id"]: node["finished_event"]
            for node in self.before_the_kill["steps"]
            if node["state"] == "done"
        }
        self.assertTrue(finished_before, self.before_the_kill)

        finished_after = {
            node["id"]: node["finished_event"] for node in self.finally_["steps"]
        }
        for name, event_id in finished_before.items():
            self.assertEqual(
                finished_after[name],
                event_id,
                f"step {name!r} was recorded as finishing again after the restart",
            )

        counted: dict[str, int] = {}
        for frame in self.log:
            if frame["kind"] == storm.STEP_FINISHED:
                name = frame["payload"]["step"]
                counted[name] = counted.get(name, 0) + 1
        for name in finished_before:
            self.assertEqual(
                counted.get(name),
                1,
                f"step {name!r} has {counted.get(name)} finish events",
            )

    def test_the_resumed_storm_carries_on_and_finishes_the_work(self):
        self.assertEqual(
            [node["state"] for node in self.finally_["steps"]],
            ["done", "done", "done"],
            json.dumps(self.finally_["steps"], indent=2)[:3000],
        )
        counted = next(
            node for node in self.finally_["steps"] if node["id"] == "count"
        )
        self.assertEqual(counted["outputs"]["rows"], EVAL_ROWS)
        self.assertTrue(counted["verification"]["ok"], counted)

    def test_the_whole_history_is_replayable_by_id(self):
        """A client that had seen up to N asks for N+1 onwards and gets it.

        The storm wrote through `app/events.py`, so its history is the same
        replayable stream a turn's tokens are - which is what makes re-attaching
        free rather than a second mechanism.
        """
        ids = [frame["id"] for frame in self.log]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(self.log[0]["kind"], storm.DECLARED)
        self.assertEqual(self.log[-1]["kind"], storm.FINISHED)

    def test_killing_an_engine_does_not_touch_the_real_database(self):
        for path, baseline in self.protected_before.items():
            self.assertEqual(
                self.protected_after[path],
                baseline,
                f"{path} changed while a storm was killed and restarted",
            )


class AnInterruptedStepIsReadTheSameWayForeverTest(unittest.TestCase):
    """The in-process half: what a killed engine leaves behind, read cold.

    A `storm.step.started` with no matching finish is exactly the shape a
    SIGKILL produces, and `attach()` must read it the same way whether the
    process died a second ago or last month. No engine is started here - the
    point is that the log alone decides.
    """

    def setUp(self):
        self.root = support.sandbox(self)
        self.thread = events.create_thread("an interrupted storm")
        path = self.root / "eval.jsonl"
        path.write_text(
            "\n".join(json.dumps({"q": f"q{i}", "a": "yes"}) for i in range(40)),
            encoding="utf-8",
        )
        stated = REGISTRY.call(
            "state_facts",
            {"facts": {"goal_text": "route tickets", "modality": "text",
                       "target_score": 0.9}},
            actor=evidence.USER,
            thread_id=self.thread["id"],
        )
        self.assertTrue(stated["ok"], stated)
        proposed = REGISTRY.call(
            "propose_build",
            {"facts": {}, "eval_path": str(path)},
            actor=evidence.USER,
            thread_id=self.thread["id"],
        )
        self.assertTrue(proposed["ok"], proposed)
        self.declared = storm.declare(
            proposed["build"],
            approved=proposed["approve"],
            thread_id=self.thread["id"],
        )
        self.storm_id = self.declared["storm"]

    def interrupt(self, step: str = "attach") -> None:
        """Write the wound a killed engine leaves: a start with no finish."""
        events.append(
            storm.STARTED,
            {"storm": self.storm_id, "state": "running", "resumed": False},
            thread_id=self.thread["id"],
        )
        events.append(
            storm.STEP_STARTED,
            {"storm": self.storm_id, "step": step, "tool": "attach_context",
             "state": "running"},
            thread_id=self.thread["id"],
        )

    def test_a_start_with_no_finish_is_stalled_and_says_why(self):
        self.interrupt()
        attached = storm.attach(self.storm_id)
        self.assertEqual(attached.steps["attach"].state, "stalled")
        self.assertEqual(attached.stalled, ("attach",))
        self.assertIn("not knowable", attached.steps["attach"].because)
        self.assertFalse(attached.live)

    def test_the_storm_stops_and_asks_rather_than_restarting_it(self):
        self.interrupt()
        rows = list(storm.run(self.storm_id))
        self.assertEqual([row["kind"] for row in rows], [storm.ASKED])
        payload = rows[0]["payload"]
        self.assertEqual(payload["stalled"], ["attach"])
        self.assertIn("not free", payload["what_now"])
        # And it started nothing while it was asking.
        self.assertEqual(
            storm.attach(self.storm_id).steps["count"].state, "queued"
        )

    def test_the_person_saying_so_is_what_restarts_it(self):
        self.interrupt()
        list(storm.run(self.storm_id))
        rows = list(storm.run(self.storm_id, restart_stalled=("attach",)))
        started = [row["payload"]["step"] for row in rows
                   if row["kind"] == storm.STEP_STARTED]
        self.assertEqual(started, ["attach", "count", "recheck"])
        self.assertEqual(
            {name: step.state
             for name, step in storm.attach(self.storm_id).steps.items()},
            {"attach": "done", "count": "done", "recheck": "done"},
        )

    def test_a_storm_nobody_has_run_is_queued_rather_than_stalled(self):
        attached = storm.attach(self.storm_id)
        self.assertEqual(attached.state, "queued")
        self.assertEqual(attached.stalled, ())


if __name__ == "__main__":
    unittest.main()
