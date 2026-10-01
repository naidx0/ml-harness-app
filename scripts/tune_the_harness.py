"""A bandit over the harness's own knobs. One arm at a time, one card.

Max: *"create a reinforcement learning environment for our harness to point it
towards the right tool definitions, the right instruction sets."*

## THIS IS NOT GRADIENT REINFORCEMENT LEARNING AND SAYING SO IS NOT PEDANTRY

Nothing in this harness has weights. There is no policy to differentiate, no
rollout buffer, no advantage estimate, and a file that used those words would
have somebody looking for a checkpoint that does not exist. What this is, said
exactly:

* An **arm** is a configuration of the harness - a set of environment variables
  the engine reads. Discrete, finite, enumerated by hand in a matrix file.
* The **environment** is one task, on one model, in a scratch data root: the
  same brief posted to the same engine build, so the only thing that differs
  between arms is the arm.
* The **reward** is the score row - the seven numbers `scripts/score_row.py`
  reads off the resulting database. Not a scalar. A scalar reward here would be
  a weighting somebody invented, and the weighting would then BE the finding.
* The **judge** is Fisher's exact test, the one already in this repository at
  `scripts/did_it_answer_the_question.py`. Nothing statistical is written here.

So it is a multi-armed bandit run in pure exploration, and the only thing it
learns is which arms are distinguishable at the number of turns you paid for -
which, at a dozen turns, is usually none of them. **That is the finding this
script exists to make cheap to reach**, because the alternative is shipping a
knob on a feeling.

## ARMS RUN SEQUENTIALLY. THERE IS ONE CARD

Not a performance note - a correctness one. Two engines against one Ollama
saturated it on this machine and turns stopped returning at all, which looks
exactly like a harness that hangs
(`scripts/did_it_answer_the_question.py`'s own account). Two arms sharing a
saturated provider are not two arms; they are one arm measured twice under
contention, and the slower one loses for a reason that is not the knob.

## THE PREREGISTRATION IS NOT PAPERWORK

The matrix will not run without a `prereg` string. `docs/judge_runs/` is full of
the reason: a rule written after the numbers is a rule fitted to the numbers,
and this repository has the receipts for both directions - a preregistration
that killed an expensive arm in ten calls, and an arm comparison that shipped
because its rule asked whether the new arm cleared a threshold and never asked
whether it beat the old one. Write down what you expect and what would refute
it, before the GPU is warm.

## WHAT IT REFUSES TO DO

* It does not pick a winner on the seven numbers as a whole. Each pair of arms
  gets Fisher on `steps_ticked` and on refusals, and a verdict of KEEP, NO
  DIFFERENCE or WORSE, with NO DIFFERENCE the default. The other five numbers
  are printed for a reader, not tested - five more tests on the same run is
  five more chances to find a p below 0.05 by asking again.
* It does not report a knob that did nothing as a knob that made no
  difference. `score_row.instruction_fingerprint` compares what each arm's
  FIRST turn was actually sent; arms that were sent the same laws and the same
  tools are named INERT in the report, and their p-values are not the news.
* It does not touch the owner's database, and it will not start on 8078.

Usage:
    python scripts/tune_the_harness.py docs/tuning/matrix-tools-vs-schemas.json
    python scripts/tune_the_harness.py the-matrix.json --dry-run \\
        --arm control=C:/scratch/control --arm on_demand=C:/scratch/on_demand
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
for _p in (REPO, REPO / "tests"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# `scripts/` is not a package, so the two modules this depends on are loaded by
# path in the idiom `scripts/drive_it_as_a_stranger.py` uses for
# `take_the_card.py`. Doing it by path rather than by name is what stops a
# `score_row` installed somewhere else on the path from being the one that
# scores an arm.
import importlib.util  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:  # pragma: no cover - a bad path
        raise ImportError(f"no module could be loaded from {path}")
    module = importlib.util.module_from_spec(spec)
    was = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = was
    return module


score_row = _load("tuning_score_row", REPO / "scripts" / "score_row.py")
_judge = _load("tuning_judge", REPO / "scripts" / "did_it_answer_the_question.py")

#: THE JUDGE, REUSED AND NOT REIMPLEMENTED. `fisher` is exact, dependency-free,
#: and was checked against `scipy.stats.fisher_exact` on 300 random tables
#: before it was believed. A second implementation of a statistical test in one
#: repository is two answers to one question.
fisher = _judge.fisher

#: The port the owner's own engine uses. An arm that took it would be measuring
#: his harness with his conversations in it, and would take the port away from
#: him while it did.
HIS_PORT = 8078

#: The product's own database filename. An arm's database is always `arm.db`,
#: so meeting this name anywhere near an arm means the arm is pointed at a real
#: installation.
THE_REAL_DATABASE = "ml_harness.db"

#: THE FOUR VARIABLES A MATRIX MAY NOT SET, and this is a fence rather than a
#: style rule. They are what puts an arm in its own scratch root; a matrix that
#: set `ML_HARNESS_DB` would run an arm against whatever database it named,
#: which on this machine is one keystroke from the owner's own.
#:
#: THIS IS NOT COVERED BY `tests/support.py`'s sqlite3 guard, and finding that
#: out is why the fence is here. That guard protects `<repo>/ml_harness.db`
#: resolved from the CHECKOUT THE CODE IS RUNNING FROM - so from an agent's git
#: worktree it protects the worktree's database and leaves the owner's real one
#: in the main checkout wide open. Measured, 2026-09-18: from this worktree the
#: guard let `sqlite3.connect` open the real file. A protection that names the
#: wrong file is not a protection.
RESERVED: tuple[str, ...] = (
    "ML_HARNESS_DB",
    "MLH_DATA_ROOT",
    "MLH_ENGINE_FILE",
    "MLH_PORT",
    "MLH_TOKEN",
)

#: How long an engine gets to answer /health before the arm is called failed.
#: The launcher allows 60s for a cold start with migrations; a scratch root has
#: no migrations to run but does have a first import of the whole product.
STARTUP_TIMEOUT = 60.0

#: How long one POST /turn may take. A build turn against a local model is tens
#: of seconds; `scripts/drive_it_as_a_stranger.py` allows 900 for the same call
#: and that number came from turns that really did take that long.
TURN_TIMEOUT = 900.0

#: The knobs this script knows how to describe. An arm may set any environment
#: variable it likes - they are opaque to this file, which is the point, since
#: two of them are being added by other lanes right now and this script must
#: not have to land after them. These are only for the report's prose.
KNOBS: dict[str, str] = {
    "MLH_FILL_BLANKS_FROM_THREAD": (
        "0 turns off the harness completing a required argument the model left "
        "blank from the thread's own first sentence (app/conductor.py). ON for "
        "a person, OFF for a trial: the fill moves the boundary between the "
        "model's work and the product's."
    ),
    "MLH_ALL_SCHEMAS": (
        "1 offers every registered tool's schema on every turn; 0 offers tools "
        "on demand. The cost is visible directly in tokens_before_first_word."
    ),
    "MLH_ALL_LAWS": (
        "1 sends every instruction fragment; 0 sends the conditional ones only "
        "when their condition holds."
    ),
    "MLH_FOOTER_VARIANT": (
        "A name, not a flag. Free-form on purpose, and the engine may not read "
        "it at all - in which case the arm still runs and the report says "
        "INERT rather than pretending the knob was tested."
    ),
}


# ---------------------------------------------------------------------------
# The matrix, and the refusal to run without one.


class MatrixError(Exception):
    """A matrix this script will not run, with the sentence saying why."""


def read_matrix(path: Path) -> dict[str, Any]:
    """Load and check the matrix. Every refusal names what is missing.

    THE PREREGISTRATION IS CHECKED FIRST and it is checked for CONTENT, not
    presence: `"prereg": "tbd"` is not a preregistration, and a key that can be
    satisfied by a placeholder is a key that will be. The floor is a sentence
    long enough to have said what would refute it.
    """
    try:
        matrix = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise MatrixError(f"no matrix at {path}") from None
    except ValueError as error:
        raise MatrixError(f"{path} is not JSON: {error}") from None
    if not isinstance(matrix, dict):
        raise MatrixError(f"{path} must hold one object, not a {type(matrix).__name__}")

    prereg = str(matrix.get("prereg") or "").strip()
    if len(prereg) < 80:
        raise MatrixError(
            "this matrix has no preregistration, so it will not run. Add a "
            '"prereg" string saying WHAT YOU EXPECT and WHAT WOULD REFUTE IT, '
            "before the run - docs/judge_runs/ is the convention and the reason. "
            f"Got {len(prereg)} characters; the floor is 80, which is about one "
            "sentence, and a sentence is the least that can carry a refutation."
        )

    arms = matrix.get("arms")
    if not isinstance(arms, list) or len(arms) < 2:
        raise MatrixError(
            "a matrix needs at least two arms: a control and something to "
            "compare against it. One arm is a run, not a comparison."
        )
    names = []
    for index, arm in enumerate(arms):
        if not isinstance(arm, dict) or not str(arm.get("name") or "").strip():
            raise MatrixError(f"arm {index} has no name")
        env = arm.get("env")
        if env is not None and not isinstance(env, dict):
            raise MatrixError(f"arm {arm.get('name')!r} has an env that is not an object")
        for key in sorted(env or {}):
            if str(key).strip().upper() in RESERVED:
                raise MatrixError(
                    f"arm {arm.get('name')!r} sets {key}, which this script sets "
                    "for itself. Those five variables are what put an arm in its "
                    "own scratch root, on its own port, with its own token; a "
                    "matrix that overrides one is a matrix that can point an arm "
                    "at the owner's real database. Tune a knob, not the fence."
                )
        names.append(str(arm["name"]).strip())
    if len(set(names)) != len(names):
        raise MatrixError(
            f"two arms share a name in {names} - the report is keyed on the "
            "name, so one of them would overwrite the other"
        )
    if names[0] != "control":
        raise MatrixError(
            f"the first arm must be named 'control' and this one is {names[0]!r}. "
            "Every pair in the report is arm-versus-control, and a comparison "
            "whose baseline is chosen after the numbers is not a comparison."
        )

    task = matrix.get("task")
    if not isinstance(task, dict):
        raise MatrixError('a matrix needs a "task" object')
    for key in ("brief_file", "model"):
        if not str(task.get(key) or "").strip():
            raise MatrixError(f'the task needs a "{key}"')
    return matrix


# ---------------------------------------------------------------------------
# One engine, on a port nobody is using, against a database nobody else has.


def free_port() -> int:
    """A loopback port nothing is listening on, and never his.

    Bind to 0, ask the OS what it picked, release it - `tests/support.py`'s own
    method. There is a window in which something else could take it; it is
    small, and the alternative is a hardcoded port, which is not a smaller risk
    but a certain collision.

    8078 is excluded rather than merely unlikely. The OS will not hand out a
    port something is listening on, so while his engine is up it cannot be
    picked - which means the one time it COULD be picked is the one time it
    must not be: when his engine is down and an arm would take the port he is
    about to come back to.
    """
    for _ in range(20):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = int(sock.getsockname()[1])
        if port != HIS_PORT:
            return port
    raise RuntimeError(  # pragma: no cover - twenty ephemeral ports in a row
        "the OS handed out 8078 twenty times running, which is not a port this "
        "script will take"
    )


def refuse_a_real_installation(root: Path, database: Path, port: int) -> None:
    """The fence, checked on every arm, before anything is started.

    Three ways an arm could end up measuring a real installation, and all three
    are cheap to rule out here and expensive to notice afterwards:

    1. **The port.** His engine is on 8078 and a run there would drive his
       conversations with a tuning brief.
    2. **The database's name.** An arm's database is always `arm.db`. Anything
       called `ml_harness.db` is a real installation's, wherever it sits.
    3. **A scratch root that is not scratch.** A directory already holding an
       `ml_harness.db`, or a database that already exists, is somebody's data -
       possibly a previous arm's, which is its own kind of wrong, because an
       arm scored on a database it did not fill is an arm scored on another
       run.
    """
    if port == HIS_PORT:
        raise RuntimeError(f"refusing port {HIS_PORT}: that is the owner's engine")
    if database.name == THE_REAL_DATABASE:
        raise RuntimeError(
            f"refusing {database}: {THE_REAL_DATABASE} is a real installation's "
            "database and an arm's is arm.db"
        )
    if database.exists():
        raise RuntimeError(
            f"refusing {database}: it already exists, so this arm would be "
            "scored on rows it did not write"
        )
    if (root / THE_REAL_DATABASE).exists():
        raise RuntimeError(
            f"refusing {root} as a scratch root: it holds a {THE_REAL_DATABASE}, "
            "so it is a real installation's data root"
        )


class Arm:
    """One engine process on its own port, its own data root and its own database.

    THE FOUR ENVIRONMENT VARIABLES ARE NOT INTERCHANGEABLE and all four are
    set. `MLH_DATA_ROOT` moves the root; `ML_HARNESS_DB` and `MLH_ENGINE_FILE`
    win over it (`app/paths.py`) and are set explicitly so a reader of this
    file can see where both land without resolving a precedence rule; and
    `MLH_PORT` is what the engine publishes to its own portfile. Leaving
    `MLH_ENGINE_FILE` to the default is the specific mistake that makes a
    scratch engine decline to write the owner's `engine.json`, print a warning
    on a stderr nobody is reading, and then be driven by a client holding the
    wrong token.
    """

    def __init__(self, name: str, root: Path, env: dict[str, str]) -> None:
        self.name = name
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = root / "arm.db"
        self.port = free_port()
        # THE FENCE, BEFORE THE LOG FILE IS EVEN OPENED. Checked here rather
        # than in `start()` so a refused arm has not yet written anything.
        refuse_a_real_installation(self.root, self.database, self.port)
        self.token = f"tuning-{name}-{os.getpid()}"
        self.log_path = root / "engine.log"
        self.handle = self.log_path.open("w", encoding="utf-8")
        self.process: subprocess.Popen | None = None
        self.knobs = dict(env)

    def environment(self) -> dict[str, str]:
        child = os.environ.copy()
        child["MLH_DATA_ROOT"] = str(self.root)
        child["ML_HARNESS_DB"] = str(self.database)
        child["MLH_ENGINE_FILE"] = str(self.root / "engine.json")
        child["MLH_PORT"] = str(self.port)
        child["MLH_TOKEN"] = self.token
        # THE ARM'S KNOBS GO ON FIRST AND THE FENCE LAST, which is the opposite
        # of the obvious order and is the point: the five lines above always
        # win. `read_matrix` already refuses a matrix that names one of them, so
        # this is the second of two locks on the same door - the first catches
        # it with a sentence a person can read, and this one holds even if some
        # future caller builds an `Arm` without going through a matrix at all.
        merged = {str(key): str(value) for key, value in self.knobs.items()}
        for key in RESERVED:
            merged.pop(key, None)
        return {**child, **merged, **{key: child[key] for key in RESERVED if key in child}}

    def start(self) -> None:
        """Spawn uvicorn and wait for /health. NO `--reload`.

        Reload puts a supervisor between the pid we hold and the socket that
        answers, so the process we later stop is not the process serving the
        arm (`scripts/launch.py` says the same thing at more length). Output
        goes to a FILE and not a pipe: a pipe nobody drains is a buffer that
        eventually blocks the process filling it, and that is a hang in the
        middle of a run that costs a GPU hour.
        """
        self.process = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn", "app.main:app",
                "--host", "127.0.0.1", "--port", str(self.port),
                "--log-level", "warning",
            ],
            cwd=str(REPO),
            env=self.environment(),
            stdout=self.handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + STARTUP_TIMEOUT
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"arm {self.name}: the engine exited {self.process.returncode} "
                    f"before answering. Its log is {self.log_path}"
                )
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/health", timeout=2
                ) as answer:
                    if answer.status == 200:
                        return
            except (urllib.error.URLError, OSError):
                time.sleep(0.2)
        raise RuntimeError(
            f"arm {self.name}: the engine on {self.port} never answered in "
            f"{STARTUP_TIMEOUT:.0f}s. Its log is {self.log_path}"
        )

    def call(
        self, method: str, path: str, body: dict | None = None, timeout: float = 60.0
    ) -> Any:
        """One API call. No `Origin` header - absent means 'not a browser'."""
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            method=method,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            return json.loads(answer.read().decode("utf-8") or "null")

    def stop(self) -> None:
        """Terminate, then kill the tree. Windows needs the second one.

        `taskkill /F /T` because uvicorn's child is not always reaped by a
        terminate on Windows, and an orphan holding the port is the next arm's
        startup failure - reported against the wrong arm.
        """
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(self.process.pid)],
                        capture_output=True,
                    )
                else:  # pragma: no cover - this script is run on Windows
                    self.process.kill()
                try:
                    self.process.wait(timeout=15)
                except subprocess.TimeoutExpired:  # pragma: no cover
                    pass
        try:
            self.handle.close()
        except OSError:  # pragma: no cover
            pass


# ---------------------------------------------------------------------------
# Driving one arm: connect, project, thread, full, post the brief, run.


def run_one_arm(
    name: str,
    env: dict[str, str],
    task: dict[str, Any],
    root: Path,
    turns_cap: int,
) -> dict[str, Any]:
    """Start an engine, take the task to it, stop the engine, return where it wrote.

    The order is the order a person does it in, and it is the order for a
    reason each time:

    1. **Provider, then activate.** A thread with no active provider takes no
       turn at all, and the failure reads as a model that would not answer.
    2. **Project with an absolute root**, or the engine 400s. The scratch root
       is the project root, so anything the arm writes lands in the arm's own
       directory rather than in the checkout.
    3. **Thread, then permission `full`.** Setting `full` also forces
       `mode='build'` and `autonomous=1` (`app/events.py`), which is what the
       run needs; setting mode first and permission second would be undone.
    4. **Goal, then message.** The goal is the thread's standing sentence; the
       message is the turn's. Both carry the brief because a run reads the
       goal and a turn reads the message, and an arm missing either is an arm
       measured on a different task.
    5. **`POST /run`, then poll, then stop at the cap.** The engine's own loop
       (`app/longrun.py`) and NOT a sequence of `POST /turn`, for two reasons:

       * A run is what the product does. It aims each turn at an open step,
         parks a step it cannot do with a reason, asks for a rewrite when
         nothing moves, and gives up after three barren turns. `steps_ticked`
         is a measurement OF that loop; posting bare turns would measure a
         thing no person uses, and the arms would be compared on it.
       * `run.turn` is written only by that loop, and it is the boundary
         `plan_written_on_turn_1` is defined against.

       The route takes no cap - `longrun.start` defaults to `TURN_CAP = 24` -
       so the cap is enforced from outside by `POST /run/stop`, which stops
       after the turn it is in. A matrix asking for 12 turns can therefore get
       13, and `turns_taken` in `rows.csv` says which, rather than the report
       claiming a bound it did not hold.
    """
    arm = Arm(name, root, env)
    try:
        arm.start()
        provider = arm.call(
            "POST",
            "/api/providers",
            {
                "name": f"tuning-{name}",
                "base_url": str(task.get("base_url") or "http://127.0.0.1:11434"),
                "model": str(task["model"]),
                "adapter": str(task.get("adapter") or "ollama"),
            },
        )
        provider_id = int(provider["id"])
        arm.call("POST", f"/api/providers/{provider_id}/activate", {})

        project = arm.call(
            "POST",
            "/api/projects",
            {"name": f"tuning-{name}", "root_path": str(root.resolve())},
        )
        thread = arm.call(
            "POST",
            "/api/threads",
            {"title": f"tuning arm {name}", "project_id": int(project["id"])},
        )
        thread_id = int(thread["id"])
        arm.call("POST", f"/api/threads/{thread_id}/permission", {"mode": "full"})

        brief = Path(task["brief_file"])
        if not brief.is_absolute():
            brief = REPO / brief
        text = brief.read_text(encoding="utf-8").strip()
        if not text:
            raise RuntimeError(f"the brief at {brief} is empty")
        arm.call("POST", f"/api/threads/{thread_id}/goal", {"goal": text[:8000]})
        arm.call("POST", f"/api/threads/{thread_id}/messages", {"content": text})

        arm.call("POST", f"/api/threads/{thread_id}/run", timeout=TURN_TIMEOUT)
        turns, ended, asked_to_stop = 0, "", False
        # THE WALL CLOCK IS A BOUND ON THE BOUND. A run that stops reporting
        # turns - a provider that hung, a worker thread that died without
        # writing its row - would otherwise poll for ever, and a tuning script
        # that never returns is worse than one that reports a failed arm.
        deadline = time.monotonic() + (int(turns_cap) + 2) * TURN_TIMEOUT
        while True:
            state_row = arm.call("GET", f"/api/threads/{thread_id}/run") or {}
            state = str(state_row.get("state") or "")
            turns = int(state_row.get("turns") or 0)
            if state and state != "running":
                ended = str(state_row.get("stop_reason") or state)
                break
            if turns >= int(turns_cap) and not asked_to_stop:
                # ASKED, not killed. `/run/stop` ends the run after the turn it
                # is in, so the cap can overshoot by one and `turns_taken`
                # records what actually happened.
                asked_to_stop = True
                arm.call("POST", f"/api/threads/{thread_id}/run/stop")
            if time.monotonic() > deadline:
                arm.call("POST", f"/api/threads/{thread_id}/run/stop")
                ended = "wall_clock"
                break
            time.sleep(2.0)
        return {
            "name": name,
            "root": str(root),
            "database": str(arm.database),
            "thread_id": thread_id,
            "turns_taken": turns,
            "ended": ended,
            "env": dict(env),
        }
    finally:
        arm.stop()


# ---------------------------------------------------------------------------
# The judging. Everything below here runs under --dry-run too, which is how it
# is tested without a GPU.


def _pairs(rows: list[dict[str, Any]]) -> list[tuple[str, str]]:
    names = []
    for row in rows:
        if row["name"] not in names:
            names.append(row["name"])
    return [(name, "control") for name in names if name != "control"]


def _pooled(rows: list[dict[str, Any]], name: str, hit: str, of: str) -> tuple[int, int]:
    """One arm's successes and attempts, summed over its repeats.

    POOLED AND NOT AVERAGED. A rate averaged over repeats loses the
    denominators, and Fisher's exact test is a statement about counts: two
    repeats of 5-of-6 is 10 of 12, which resolves more than one 83% does. A
    repeat that produced no attempts contributes nothing to either number,
    which is correct and is why this returns a pair rather than a fraction.
    """
    successes = sum(int(row[hit] or 0) for row in rows if row["name"] == name)
    attempts = sum(int(row[of] or 0) for row in rows if row["name"] == name)
    return successes, attempts


def _verdict(
    ticked_p: float | None,
    arm_ticked: tuple[int, int],
    control_ticked: tuple[int, int],
    refusal_p: float | None,
    arm_refusals: tuple[int, int],
    control_refusals: tuple[int, int],
    alpha: float,
) -> tuple[str, str]:
    """KEEP, WORSE or NO DIFFERENCE - and NO DIFFERENCE is the default.

    THE DIRECTION IS DECIDED BEFORE THE p. A p below alpha says the two arms
    are distinguishable; it does not say which way, and an arm that refused
    more often with a beautiful p is not an arm to keep. So the rate is
    compared first and the p only decides whether the comparison is allowed to
    be reported as a difference at all.

    An arm that ticks the same fraction but refuses significantly MORE is
    WORSE: it did the same work with more of the harness saying no, and the
    refusals are what a person feels.
    """

    def rate(pair: tuple[int, int]) -> float | None:
        hits, attempts = pair
        return (hits / attempts) if attempts else None

    arm_rate, control_rate = rate(arm_ticked), rate(control_ticked)
    arm_refused, control_refused = rate(arm_refusals), rate(control_refusals)

    ticked_says = ticked_p is not None and ticked_p < alpha
    refusal_says = refusal_p is not None and refusal_p < alpha

    if ticked_says and arm_rate is not None and control_rate is not None:
        if arm_rate > control_rate:
            return "KEEP", (
                f"ticked {arm_rate:.0%} against the control's {control_rate:.0%}, "
                f"p={ticked_p:.3f}"
            )
        if arm_rate < control_rate:
            return "WORSE", (
                f"ticked {arm_rate:.0%} against the control's {control_rate:.0%}, "
                f"p={ticked_p:.3f}"
            )
    if refusal_says and arm_refused is not None and control_refused is not None:
        if arm_refused > control_refused:
            return "WORSE", (
                f"same work, more refusals - {arm_refused:.0%} against the "
                f"control's {control_refused:.0%}, p={refusal_p:.3f}"
            )
        if arm_refused < control_refused:
            return "KEEP", (
                f"same work, fewer refusals - {arm_refused:.0%} against the "
                f"control's {control_refused:.0%}, p={refusal_p:.3f}"
            )
    return "NO DIFFERENCE", (
        "neither steps ticked nor refusals separated this arm from the control "
        "at this many turns"
    )


def resolution_sentence(turns: int, ticked: int) -> str:
    """The honest sentence about what this run could NOT have seen.

    Reuses `app/tools/evals.resolution_for`, which computes both figures from n
    rather than quoting `docs/PRODUCT_SPEC.md`'s rule of thumb, and falls back
    to saying the import failed rather than inventing a number - a resolution
    statement is exactly the sentence that must not be guessed at.
    """
    try:
        from app.tools import evals

        block = evals.resolution_for(int(ticked), int(turns))
    except Exception as error:  # noqa: BLE001 - a missing import is not a number
        return (
            f"the resolution could not be computed ({type(error).__name__}: "
            f"{error}), so this run does not say what it could not have seen"
        )
    if not block.get("n"):
        return (
            "nothing was attempted, so there is no resolution: this run cannot "
            "tell any two arms apart."
        )
    points = float(block["resolves_a_difference_of_at_least_points"])
    needed = int(block["rows_for_a_10_point_difference"])
    return (
        f"At {turns} attempts, two arms differ only above ~{points:.0f} points. "
        f"A 10-point difference would need {needed} attempts. "
        f"{block['says']}"
    )


def judge(rows: list[dict[str, Any]], alpha: float = 0.05) -> dict[str, Any]:
    """Every arm against the control, on two columns, with a verdict each."""
    control_ticked = _pooled(rows, "control", "steps_ticked", "steps_open_at_start")
    control_refusals = _pooled(rows, "control", "refusals", "tool_calls")
    out = []
    for name, _ in _pairs(rows):
        arm_ticked = _pooled(rows, name, "steps_ticked", "steps_open_at_start")
        arm_refusals = _pooled(rows, name, "refusals", "tool_calls")

        def p_for(arm: tuple[int, int], control: tuple[int, int]) -> float | None:
            # A 2x2 NEEDS FOUR CELLS. An arm or a control with no attempts has
            # no table at all, and `fisher` on a zero margin is a number with
            # nothing behind it.
            if not arm[1] or not control[1]:
                return None
            return fisher(
                arm[0], arm[1] - arm[0], control[0], control[1] - control[0]
            )

        ticked_p = p_for(arm_ticked, control_ticked)
        refusal_p = p_for(arm_refusals, control_refusals)
        verdict, because = _verdict(
            ticked_p, arm_ticked, control_ticked,
            refusal_p, arm_refusals, control_refusals,
            alpha,
        )
        out.append(
            {
                "arm": name,
                "steps_ticked": list(arm_ticked),
                "control_steps_ticked": list(control_ticked),
                "steps_ticked_p": ticked_p,
                "refusals": list(arm_refusals),
                "control_refusals": list(control_refusals),
                "refusals_p": refusal_p,
                "verdict": verdict,
                "because": because,
            }
        )
    return {
        "alpha": alpha,
        "control_steps_ticked": list(control_ticked),
        "control_refusals": list(control_refusals),
        "pairs": out,
    }


def inertness(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Which arms were sent the same prompt as the control, despite the knob.

    An arm with no fingerprint at all (it never took a turn) is UNKNOWN and not
    INERT: those are different failures and collapsing them would report a
    crashed arm as a knob the engine ignores.
    """
    control = next(
        (row.get("fingerprint") for row in rows if row["name"] == "control"), None
    )
    out = {}
    for name, _ in _pairs(rows):
        marks = {row.get("fingerprint") for row in rows if row["name"] == name}
        mark = next(iter(marks)) if len(marks) == 1 else None
        if mark is None or control is None:
            out[name] = "UNKNOWN"
        elif mark == control:
            out[name] = "INERT"
        else:
            out[name] = "LIVE"
    return out


# ---------------------------------------------------------------------------
# The two files.


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    """`rows.csv`, one row per arm per repeat. Newline handled for Windows.

    `newline=""` and not the default: `csv` writes its own line terminator and
    a text file in universal-newline mode turns it into two, which produces a
    file every spreadsheet reads as double-spaced.
    """
    columns = ["arm", "repeat", "thread_id", "turns_taken", "ended", "fingerprint"]
    columns += list(score_row.FIELDS) + ["env"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(
                [
                    row["name"],
                    row.get("repeat", 1),
                    row.get("thread_id", ""),
                    row.get("turns_taken", ""),
                    row.get("ended", ""),
                    row.get("fingerprint") or "",
                ]
                + ["" if row.get(field) is None else row.get(field) for field in score_row.FIELDS]
                + [json.dumps(row.get("env") or {}, sort_keys=True)]
            )


def _cell(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def write_report(
    path: Path,
    matrix: dict[str, Any],
    rows: list[dict[str, Any]],
    verdicts: dict[str, Any],
    inert: dict[str, str],
    dry_run: bool,
) -> None:
    """`report.md` - the table, the pairs, the resolution, the verdicts."""
    NL = chr(10)
    task = matrix.get("task") or {}
    lines: list[str] = []
    lines.append(f"# {matrix.get('name') or path.parent.name}")
    lines.append("")
    lines.append(
        f"**{date.today().isoformat()}.** "
        + (
            "Judged from existing scratch roots (`--dry-run`): no engine was "
            "started and no model was called, so this file says what those "
            "databases hold and nothing about the tree as it stands now."
            if dry_run
            else f"{len(rows)} runs, "
            f"{len({row['name'] for row in rows})} arms, "
            f"model `{task.get('model', '?')}`, "
            f"cap {matrix.get('turns_cap', '?')} turns, "
            f"{matrix.get('repeats', 1)} repeat(s) each, sequentially."
        )
    )
    lines.append("")

    lines.append("## What was preregistered, before the run")
    lines.append("")
    for para in str(matrix.get("prereg") or "").strip().split(NL + NL):
        lines.append("> " + para.strip().replace(NL, NL + "> "))
        lines.append("")

    lines.append("## The arms")
    lines.append("")
    lines.append("| arm | knobs | sent the same prompt as the control? |")
    lines.append("| --- | --- | --- |")
    for arm in matrix.get("arms") or []:
        name = str(arm.get("name"))
        env = arm.get("env") or {}
        knobs = ", ".join(f"`{k}={v}`" for k, v in sorted(env.items())) or "_(none)_"
        mark = "the control" if name == "control" else {
            "INERT": "**INERT - no, identical: the engine did not read this knob**",
            "LIVE": "no, the prompt differed - the knob was read",
            "UNKNOWN": "unknown - this arm took no turn to fingerprint",
        }.get(inert.get(name, "UNKNOWN"), "unknown")
        lines.append(f"| `{name}` | {knobs} | {mark} |")
    lines.append("")
    if "INERT" in inert.values():
        lines.append(
            "**An INERT arm is not a result.** Its numbers differ only by the "
            "model's own run-to-run variation, because it was sent the same "
            "laws and the same tool schemas as the control - compared on "
            "`turn.started.instruction_set` and the first `turn.context`'s "
            "system and tool token counts. Fix the matrix or the engine; do "
            "not read the p-value below as evidence about the knob."
        )
        lines.append("")

    lines.append("## The seven numbers")
    lines.append("")
    headline = list(score_row.HEADLINE)
    lines.append("| arm | repeat | " + " | ".join(headline) + " |")
    lines.append("| --- | --- | " + " | ".join("---" for _ in headline) + " |")
    for row in rows:
        cells = [_cell(row.get(field)) for field in headline]
        lines.append(
            f"| `{row['name']}` | {row.get('repeat', 1)} | " + " | ".join(cells) + " |"
        )
    lines.append("")
    lines.append(
        "`steps_ticked` and `steps_open_at_start` are counts; "
        "`refusals_per_call` and `empty_replies` are rates whose numerators and "
        "denominators are in `rows.csv` beside them, so every figure here can "
        "be recomputed rather than taken. `-` is a rate with an empty "
        "denominator, which is not zero."
    )
    lines.append("")

    lines.append("## Each arm against the control, Fisher's exact, two-sided")
    lines.append("")
    lines.append(
        "The test is `fisher` from `scripts/did_it_answer_the_question.py`, "
        "reused and not reimplemented. Repeats are POOLED, not averaged: the "
        "test is a statement about counts."
    )
    lines.append("")
    lines.append("| arm | steps ticked | vs control | p | refusals | vs control | p |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for pair in verdicts["pairs"]:
        arm_t, con_t = pair["steps_ticked"], pair["control_steps_ticked"]
        arm_r, con_r = pair["refusals"], pair["control_refusals"]
        lines.append(
            f"| `{pair['arm']}` "
            f"| {arm_t[0]} of {arm_t[1]} | {con_t[0]} of {con_t[1]} "
            f"| {_cell(pair['steps_ticked_p'])} "
            f"| {arm_r[0]} of {arm_r[1]} | {con_r[0]} of {con_r[1]} "
            f"| {_cell(pair['refusals_p'])} |"
        )
    lines.append("")

    lines.append("## What this run could not have seen")
    lines.append("")
    attempts = verdicts["control_steps_ticked"][1]
    hits = verdicts["control_steps_ticked"][0]
    lines.append(resolution_sentence(attempts, hits))
    lines.append("")

    lines.append("## The verdicts")
    lines.append("")
    lines.append(
        f"NO DIFFERENCE is the default and alpha is {verdicts['alpha']}. "
        "The direction is read off the rates before the p is consulted: an arm "
        "that refused more often with a small p is WORSE, not a finding to keep."
    )
    lines.append("")
    for pair in verdicts["pairs"]:
        note = ""
        if inert.get(pair["arm"]) == "INERT":
            note = " _(and this arm was INERT, so the verdict is about noise)_"
        lines.append(f"- **`{pair['arm']}`: {pair['verdict']}** - {pair['because']}.{note}")
    lines.append("")

    lines.append("## The knobs, as this script understands them")
    lines.append("")
    # A LOCAL `seen`, NOT `KNOBS.pop`. Popping would empty the module-level
    # dictionary, so the second report written in one process would describe no
    # knobs at all - and the test that writes two reports is the only thing
    # that would ever have noticed.
    seen: set[str] = set()
    for arm in matrix.get("arms") or []:
        for key in (arm.get("env") or {}):
            if key in KNOBS and key not in seen:
                seen.add(key)
                lines.append(f"- `{key}` - {KNOBS[key]}")
    if not seen:
        lines.append(
            "_No knob in this matrix is one this script carries a description "
            "for; they are opaque environment variables, which is deliberate._"
        )
    lines.append("")

    path.write_bytes((NL.join(lines).rstrip() + NL).encode("utf-8"))


# ---------------------------------------------------------------------------


def score(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn each finished run into its score row, keeping what identifies it."""
    rows = []
    for run in runs:
        row = dict(run)
        row.update(score_row.compute_row(run["database"], run["thread_id"]))
        row["fingerprint"] = score_row.instruction_fingerprint(
            run["database"], run["thread_id"]
        )
        rows.append(row)
    return rows


def _dry_run_runs(arms: list[str], given: dict[str, str]) -> list[dict[str, Any]]:
    """Find each named scratch root's database and its one thread.

    THE THREAD IS NOT GUESSED AT. A root with two threads in it is ambiguous -
    it could be a rerun, or two arms sharing a root - and picking the newest
    would quietly score the wrong one. It refuses and names both.
    """
    import sqlite3

    runs = []
    for name in arms:
        if name not in given:
            raise MatrixError(
                f"--dry-run needs a root for every arm and {name!r} has none. "
                f"Add --arm {name}=<path>"
            )
        root = Path(given[name])
        database = root if root.suffix == ".db" else root / "arm.db"
        if not database.exists():
            raise MatrixError(f"arm {name!r}: no database at {database}")
        connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
        try:
            ids = [int(r[0]) for r in connection.execute("SELECT id FROM threads ORDER BY id")]
        finally:
            connection.close()
        if len(ids) != 1:
            raise MatrixError(
                f"arm {name!r}: {database} holds {len(ids)} threads ({ids}), and "
                "an arm is one thread. Name the database of a single run."
            )
        runs.append(
            {
                "name": name,
                "root": str(root),
                "database": str(database),
                "thread_id": ids[0],
                "turns_taken": "",
                "ended": "read from disk",
                "repeat": 1,
                "env": {},
            }
        )
    return runs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a matrix of harness configurations and judge them.",
    )
    parser.add_argument("matrix", type=Path, help="the matrix JSON file")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="judge existing scratch roots instead of running anything",
    )
    parser.add_argument(
        "--arm",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="with --dry-run: where an arm already wrote (repeatable)",
    )
    parser.add_argument(
        "--out", type=Path, default=None, help="override the output directory"
    )
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument(
        "--scratch",
        type=Path,
        default=None,
        help="where the arms' data roots go; a temporary directory by default",
    )
    # THE ARMS' DATA ROOTS ARE KEPT BY DEFAULT, and the flag is the one that
    # throws them away. They hold the databases every number in the report was
    # read from, and they are the only thing that makes `--dry-run` able to
    # re-judge a run - so deleting them on the way out would leave a report
    # whose figures nobody can recheck and a GPU hour nobody can re-examine.
    # A repair that destroys the evidence it was needed for is not a tidy-up.
    parser.add_argument(
        "--discard-scratch",
        action="store_true",
        help="delete the arms' data roots afterwards - they hold the databases "
             "the report was computed from, so this throws away the evidence",
    )
    args = parser.parse_args(argv)

    try:
        matrix = read_matrix(args.matrix)
    except MatrixError as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 2

    arms = matrix["arms"]
    names = [str(arm["name"]).strip() for arm in arms]
    stem = str(matrix.get("name") or args.matrix.stem)
    out = args.out or (REPO / "docs" / "tuning" / f"{date.today().isoformat()}-{stem}")
    out.mkdir(parents=True, exist_ok=True)

    scratch: Path | None = None
    try:
        if args.dry_run:
            given = {}
            for pair in args.arm:
                key, _, value = str(pair).partition("=")
                if not value:
                    print(f"REFUSED: --arm wants NAME=PATH, got {pair!r}", file=sys.stderr)
                    return 2
                given[key.strip()] = value.strip()
            runs = _dry_run_runs(names, given)
        else:
            scratch = Path(args.scratch) if args.scratch else Path(
                tempfile.mkdtemp(prefix="mlh-tuning-")
            )
            turns_cap = int(matrix.get("turns_cap") or 12)
            repeats = int(matrix.get("repeats") or 1)
            runs = []
            # SEQUENTIAL. One card. See the module docstring.
            for repeat in range(1, repeats + 1):
                for arm in arms:
                    name = str(arm["name"]).strip()
                    root = scratch / f"{name}-{repeat}"
                    print(f"[{name} repeat {repeat}] starting", flush=True)
                    finished = run_one_arm(
                        name, dict(arm.get("env") or {}), matrix["task"], root, turns_cap
                    )
                    finished["repeat"] = repeat
                    runs.append(finished)
                    print(
                        f"[{name} repeat {repeat}] {finished['ended']} after "
                        f"{finished['turns_taken']} turns",
                        flush=True,
                    )

        rows = score(runs)
        verdicts = judge(rows, alpha=float(args.alpha))
        inert = inertness(rows)
        write_rows(out / "rows.csv", rows)
        write_report(out / "report.md", matrix, rows, verdicts, inert, args.dry_run)
    except MatrixError as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 2
    except Exception as error:  # noqa: BLE001 - the arm's failure is the news
        print(f"FAILED: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    finally:
        if scratch is not None and args.discard_scratch:
            shutil.rmtree(scratch, ignore_errors=True)

    print(f"wrote {out / 'rows.csv'}")
    print(f"wrote {out / 'report.md'}")
    if scratch is not None and not args.discard_scratch:
        # NAMED, not merely kept. A directory under the system temp folder that
        # nobody is told about is a directory nobody will find in a week, which
        # is the same as having deleted it.
        print(f"the arms' databases are in {scratch}")
        print(
            "  re-judge them without a card: "
            + " ".join(
                [f"--arm {row['name']}={row['root']}" for row in runs]
            )
        )
    for pair in verdicts["pairs"]:
        print(f"  {pair['arm']}: {pair['verdict']} - {pair['because']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
