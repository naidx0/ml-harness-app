"""One command that starts ML Harness and tells you the truth about it.

`./start.sh` is a wrapper around this file. Everything that decides anything
lives here, in Python, for two reasons: a bash script and a PowerShell script
that both implement this logic would diverge within a week, and a shell script
cannot be unit tested. `tests/test_the_launcher_refuses_to_guess.py` imports
this module and drives `decide()` directly.

## The question this answers

Max asked: *"when running the localhost and testing, what engine needs to be
running on the back side and how do we make sure it's ready and working, do we
need two separate gateways for our engine and our app, can they be consistent
together?"*

**Two processes in development, one in production.** Vite exists so a React
edit shows up without a rebuild; the engine serves the API. In production the
engine serves the built UI and it is one process on one port, which is where
`docs/ARCHITECTURE.md` already points, because Tauri later wraps the same React
app. The two-ness is a dev convenience and not a design, and this file's job is
to make it invisible: one command, one summary, one URL to open.

**Consistency is a handshake, not a convention.** The engine publishes what it
is (`app/identity.py`), the launcher verifies it before trusting it, and it
verifies it *over the socket* rather than out of a file, because the file is
exactly the thing that goes stale.

## The five failures this is built against

Every rule below is here because the absence of it produced a specific wrong
answer on one evening. None of them is defensive programming in the abstract.

1. **`engine.json` published pid 24636; 23220 held the port.** So `taskkill`
   on the published pid killed something that was not the server, and the
   launcher believed the port was clear. THE RULE: this launcher never
   terminates a pid it read from a file. It terminates only a pid that came
   back from a live `/health` response on the port in question, from a process
   that identified itself as `ml-harness-engine` - and then it waits for the
   port to actually close and fails loudly if it does not.

2. **The replacement engine died on `[Errno 10048]` into a log nobody read.**
   THE RULE: the child's output is captured, and if the child exits before it
   is ready, the log is printed TO THE TERMINAL and the launcher exits
   non-zero. A silent failure is not reachable from here.

3. **`GET /health` answered `ok` from the stale engine.** THE RULE: readiness
   is never "something answered". Every wait passes `expect_build` and a
   per-start `expect_launch` nonce, so the engine itself refuses to say `ok`
   to a caller that meant a different engine. See `app/main.py health()`, and
   `wait_for_engine` below for why it is a nonce and not a pid.

4. **The stale engine was older code, so the UI said "I couldn't find a
   graphics card" on a machine with an idle RTX 2060 SUPER.** THE RULE: an
   engine that is already listening is REUSED only when its `code_fingerprint`
   matches this working tree's. Otherwise it is replaced. "It answered" is not
   "it is the right one".

5. **The token rotates on every start, so an open browser tab starts 401ing.**
   THE RULE: the launcher pins `MLH_TOKEN`, carrying forward the token already
   published in `engine.json` unless `--rotate-token` is given. A restart the
   launcher performed does not invalidate a tab the user already had open. The
   trade-off is stated rather than hidden: a token that survives restarts also
   survives having been leaked, and `scripts/open_dashboard.py` puts it in a
   URL, so `--rotate-token` exists and the summary always says which happened.

## What it will not do

It will not kill a process it cannot identify. A foreign server on 8078 - some
other project's dev server, a leftover Docker publish - produces a refusal that
names what answered, and a non-zero exit. Guessing there is how you lose an
afternoon's work in another window.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app import identity  # noqa: E402  - after the sys.path insert, on purpose
from app.config import DEFAULT_PORT  # noqa: E402

#: Vite's port, pinned in `frontend/vite.config.ts` with `strictPort: true`.
#: Read from there rather than repeated here would be better; it is a TypeScript
#: literal, and `tests/test_the_launcher_refuses_to_guess.py` asserts the two
#: agree so the duplication cannot rot silently.
DEFAULT_UI_PORT = 5199

#: The dev-only route `frontend/vite.config.ts` mounts. Nothing else serves it,
#: which makes it an identity check for the UI process in the same way
#: `service: ml-harness-engine` is one for the engine. Hitting `/` would only
#: prove that *a* web server is there, which is failure 3 in another costume.
UI_IDENTITY_PATH = "/__engine/session"

#: `localhost`, not `127.0.0.1`, and the difference is not cosmetic. Vite binds
#: whatever `localhost` resolves to, and on this machine Node picks `::1` - so
#: the dev server listens on IPv6 loopback and IPv4 loopback is empty.
#:
#: THE REASON THIS IS THE RIGHT CHOICE AND NOT JUST A WORKING ONE: it is the
#: address a browser uses. The summary prints `http://localhost:<port>`, so the
#: thing the launcher verified and the thing the person opens have to be the
#: same server - and on this machine, at the moment this was written, they were
#: not the same server on port 5199. See `probe_ui`.
UI_HOST = "localhost"

LOG_ROOT = REPO_ROOT / "logs"
ENGINE_LOG = LOG_ROOT / "engine.log"
UI_LOG = LOG_ROOT / "ui.log"

#: How long to wait for the engine to answer a verified `/health`. A cold
#: import of fastapi plus nine migrations on a OneDrive-backed checkout is not
#: fast; 60 s is headroom, not a measurement, and the wait ends the moment the
#: engine is ready rather than sleeping the whole time.
ENGINE_READY_TIMEOUT = 60.0

#: Vite's first start compiles the TypeScript project. Slower than the engine.
UI_READY_TIMEOUT = 120.0

#: How long a terminated engine gets to release the port before this is
#: reported as a failure. See `_wait_for_port_to_close` for why the failure is
#: loud rather than a retry.
PORT_RELEASE_TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# Looking at a port without believing anything it does not prove.


# ---------------------------------------------------------------------------
# THE DECISIONS NOW LIVE IN THE PACKAGE. `docs/THE_PLAN.md` Phase V step A6:
# `scripts/` is not in a wheel, and the Tauri shell has to answer the same four
# questions this file answers - is there an engine on this port, is it OURS, is
# it running MY code, should it be replaced. A shell reimplementing `decide()`
# in Rust would be a second answer to each.
#
# EVERYTHING THAT LOOKS MOVED; EVERYTHING THAT ACTS STAYED. `start_engine`,
# `replace_engine`, `_terminate` and `start_ui` are below, unmoved, and that
# split is the boundary rather than a tidy-up. `app/` still imports nothing from
# `scripts/`; the dependency runs this way, as it always did.
#
# Re-exported by name rather than with a star, so this file's own surface is
# still readable and `tests/test_the_launcher_refuses_to_guess.py` keeps calling
# `launcher.decide(...)` exactly as it did.
from app.launcher import (  # noqa: E402 - after the sys.path insert, on purpose
    Decision,
    Probe,
    decide,
    port_is_open,
    portfile_path,
    probe_engine,
    published_token,
    read_portfile,
)

def probe_ui(port: int, timeout: float = 4.0) -> Probe:
    """Is OUR dev server on the address a browser will actually use?

    Two questions in one, and separating them is the whole value.

    *Is it ours* - `/__engine/session` is a route only `frontend/vite.config.ts`
    mounts, so a 200 with a JSON body identifies the process rather than merely
    finding one. Asking `/` would only prove that a web server is there, which
    is the stale-engine mistake in another costume.

    *On the address a browser will use* - `localhost`, not `127.0.0.1`. Those
    are not the same port. MEASURED ON THIS MACHINE WHILE THIS WAS BEING
    WRITTEN: `127.0.0.1:5199` was pid 19892 serving the identity route against
    an engine on 8079, and `[::1]:5199` was pid 6404 serving a different app's
    SPA - two processes, one port number, different address families, and
    `strictPort` prevented neither because neither collided. A browser opening
    `http://localhost:5199` gets the IPv6 one. That is precisely the failure
    `vite.config.ts` documents in its own comment - "a screenshot taken against
    it was reported as evidence for this one" - and pinning the port did not
    close it.

    So this refuses, and `_ui_disagreement` says why, rather than quietly
    reusing whichever half answers first. Picking one would mean the launcher
    printed a URL to a server it had not checked.
    """
    probe = _probe_ui_at(UI_HOST, port, timeout)
    if probe.state != "foreign":
        return probe
    other = _probe_ui_at("127.0.0.1", port, timeout)
    if other.state == "ours-current":
        probe.evidence = (
            f"{probe.evidence.rstrip('. ')}. AND THERE ARE TWO SERVERS ON PORT {port}: "
            f"http://127.0.0.1:{port}{UI_IDENTITY_PATH} IS ours while "
            f"http://{UI_HOST}:{port}{UI_IDENTITY_PATH} is not, which means "
            "one process holds IPv4 loopback and a different one holds IPv6. "
            "A browser opening localhost gets the second. Stop them both and "
            "run this again."
        )
    return probe


def _probe_ui_at(host: str, port: int, timeout: float) -> Probe:
    """One address family's answer. `probe_ui` is what callers want."""
    if not port_is_open(port, host=host, timeout=min(timeout, 1.0)):
        return Probe("free", port)
    url = f"http://{host}:{port}{UI_IDENTITY_PATH}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        return Probe(
            "foreign",
            port,
            evidence=(
                f"a web server on {port} answered HTTP {error.code} for "
                f"{UI_IDENTITY_PATH}, which our dev server always serves. It "
                "is not our dev server."
            ),
        )
    except (urllib.error.URLError, OSError) as error:
        return Probe(
            "foreign",
            port,
            evidence=f"something is on {url} but did not answer HTTP: {error}",
        )
    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
    except ValueError:
        preview = body[:80].decode("utf-8", errors="replace").strip()
        served_the_app = preview.lower().startswith(("<!doctype", "<html"))
        return Probe(
            "foreign",
            port,
            evidence=(
                f"HTTP {status} from {url} but the body is not JSON - "
                + (
                    "it is the app's index.html, so this dev server fell "
                    "through to its SPA route, which means its config does "
                    "not mount our identity route. It is a Vite from a "
                    "different checkout or a different project."
                    if served_the_app
                    else f"first bytes: {preview!r}"
                )
            ),
        )
    return Probe("ours-current", port, payload=payload)


# ---------------------------------------------------------------------------
# Deciding. Pure, so a test can drive every branch without a server.


# ---------------------------------------------------------------------------
# Acting.


class LaunchError(RuntimeError):
    """Something went wrong that the person at the terminal has to see."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _terminate(pid: int) -> None:
    """Ask one process, by pid, to stop. Nothing broader, ever.

    `os.kill` with `SIGTERM` maps to `TerminateProcess` on Windows and to a
    catchable signal on POSIX. There is no process-group kill and no name-based
    matching here on purpose: a `taskkill /IM python.exe` would have "worked"
    on the evening this file is a response to, and would also have killed the
    job runner, the test suite and every other agent lane on the machine.
    """
    os.kill(pid, signal.SIGTERM)


def _wait_for_port_to_close(port: int, timeout: float = PORT_RELEASE_TIMEOUT) -> bool:
    """Poll until nothing accepts a connection on `port`. `False` on timeout.

    THIS IS THE CHECK THAT MAKES TERMINATION HONEST. Killing a pid proves that
    a pid is gone; it does not prove the port is free, and the difference is
    the whole first failure. Under `uvicorn --reload` the socket belongs to a
    supervisor that will simply start another child, so the port stays open and
    this returns `False` - which is the correct answer and produces a message
    saying exactly that, rather than a second engine that cannot bind.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not port_is_open(port, timeout=0.5):
            return True
        time.sleep(0.2)
    return not port_is_open(port, timeout=0.5)


def replace_engine(probe: Probe, port: int) -> str:
    """Stop the engine we identified on `port`. Raises if the port stays open."""
    pid = probe.pid
    if pid is None:
        raise LaunchError(
            f"the engine on {port} did not report a pid in its /health "
            "response, so there is nothing this launcher is willing to "
            "terminate. Stop it by hand and run this again.",
            exit_code=2,
        )
    engine_id = (probe.payload or {}).get("engine", {}).get("engine_id")
    try:
        _terminate(pid)
    except ProcessLookupError:
        pass  # It died between the probe and now. Fine - we wanted it gone.
    except PermissionError as error:
        raise LaunchError(
            f"could not stop the engine on {port} (pid {pid}): {error}. It is "
            "running as another user, or under a supervisor this account "
            "cannot signal.",
            exit_code=2,
        ) from error

    if _wait_for_port_to_close(port):
        return f"stopped the engine on {port} (pid {pid}, engine {engine_id})"

    after = probe_engine(port)
    still = (after.payload or {}).get("engine", {}).get("engine_id")
    if after.is_ours and still == engine_id:
        detail = (
            f"the same engine ({engine_id}) is still answering, so pid {pid} "
            "was not the process holding the socket. This is the shape of "
            "failure that started all of this."
        )
    elif after.is_ours:
        detail = (
            f"a DIFFERENT engine ({still}) is now answering, so something is "
            "restarting it - `uvicorn --reload` keeps the socket in a "
            "supervisor and replaces the worker. Stop the supervisor."
        )
    else:
        detail = f"what is there now: {after.state}. {after.evidence}"
    raise LaunchError(
        f"terminated pid {pid} but port {port} is still occupied after "
        f"{PORT_RELEASE_TIMEOUT:.0f}s. {detail}",
        exit_code=2,
    )


def _detached(**kwargs: Any) -> dict[str, Any]:
    """Popen flags that let a child outlive this launcher.

    The default is to hand back the terminal, because "run it twice must not
    produce two engines" is much easier to believe when the first run has
    already exited. `--foreground` skips this.
    """
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
    else:
        kwargs["start_new_session"] = True
    return kwargs


def _tail(path: Path, limit: int = 4000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return f"<{path} could not be read>"
    return text[-limit:] if len(text) > limit else text or "<empty>"


def start_engine(
    port: int, token: str, nonce: str, foreground: bool
) -> subprocess.Popen:
    """Start uvicorn with the token pinned, output captured, nothing detached
    from the truth.

    **No `--reload`.** Reload is what puts a supervisor between the pid that
    answers requests and the pid that owns the socket, and that gap is failure
    one. A single process means `os.getpid()` inside the app IS the listener,
    which is what makes `expect_pid` on `/health` a real check rather than a
    hopeful one. Restarting on a Python edit is what running this command again
    is for; it takes about a second and it tells you what it did.
    """
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    handle = ENGINE_LOG.open("w", encoding="utf-8")
    child_env = dict(os.environ)
    child_env["MLH_PORT"] = str(port)
    child_env["MLH_TOKEN"] = token
    child_env["MLH_LAUNCH_NONCE"] = nonce
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "info",
    ]
    options: dict[str, Any] = {
        "cwd": str(REPO_ROOT),
        "env": child_env,
        "stdout": handle,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
    }
    if not foreground:
        options = _detached(**options)
    return subprocess.Popen(command, **options)


def wait_for_engine(
    child: subprocess.Popen,
    port: int,
    expect_build: str,
    nonce: str,
    timeout: float = ENGINE_READY_TIMEOUT,
) -> dict[str, Any]:
    """Wait until the engine is READY, which is four separate assertions.

    Not `sleep 3`. Not "the port is open". The loop ends only when `/health`
    returns 200 for a request that named this build AND the launch nonce this
    launcher invented for this child - so the thing that answered is provably
    the process we started, running the code in this working tree, with a
    schema its database agrees with, having just executed a real query.

    THE NONCE IS HERE BECAUSE THE PID DOES NOT WORK, and finding that out is
    worth the paragraph. The first version of this function asked "is the
    process answering the pid I started". It failed on its first run on the
    machine this is built on: `Popen.pid` was 12468 and the server logged
    `Started server process [25392]`, because the venv's `python.exe` re-execs
    and hands the real work to a different process. Every layer between a
    parent and the code it meant to run - a venv shim, a wrapper script, an
    antivirus interposer - breaks a pid comparison, and none of them break a
    value the child carries in its own environment and reads back out.

    Three ways it ends badly, and each one prints something a person can act on:

    - **The child exits.** `[Errno 10048] only one usage of each socket
      address` lands in the log, and the log is put in front of you. This is
      the failure that previously went to a file nobody read.
    - **Something else answers.** A 409 naming `launch_nonce` means an ML
      Harness engine we did not start has the port. We stop; killing at that
      point would be killing a stranger.
    - **It never answers.** The timeout reports the last thing we saw and the
      tail of the log.
    """
    deadline = time.monotonic() + timeout
    last = "no response yet"
    while time.monotonic() < deadline:
        code = child.poll()
        if code is not None:
            raise LaunchError(
                f"the engine exited with code {code} before it was ready.\n"
                f"--- {ENGINE_LOG} ---\n{_tail(ENGINE_LOG)}",
                exit_code=3,
            )
        probe = probe_engine(
            port, expect_build=expect_build, expect_launch=nonce, timeout=2.0
        )
        if probe.state == "ours-current":
            return probe.payload or {}
        if probe.state == "ours-stale":
            fields = sorted(str(item.get("field")) for item in probe.mismatch)
            raise LaunchError(
                f"an ML Harness engine is on {port} and it is NOT the one this "
                f"launcher just started - it disagrees on {fields}. Its "
                f"engine_id is "
                f"{(probe.payload or {}).get('engine', {}).get('engine_id')}, "
                f"its pid is {probe.pid}. Nothing has been terminated, because "
                "this launcher does not kill a process it did not start.\n"
                f"--- {ENGINE_LOG} ---\n{_tail(ENGINE_LOG)}",
                exit_code=3,
            )
        if probe.state == "ours-unready":
            failing = [
                f"{check['name']}: {check['detail']}"
                for check in (probe.payload or {}).get("checks", [])
                if not check.get("ok")
            ]
            last = "engine is up but not ready - " + "; ".join(failing)
        elif probe.state == "foreign":
            last = probe.evidence
        time.sleep(0.25)
    raise LaunchError(
        f"the engine did not become ready on {port} within {timeout:.0f}s. "
        f"Last seen: {last}.\n--- {ENGINE_LOG} ---\n{_tail(ENGINE_LOG)}",
        exit_code=3,
    )


# ---------------------------------------------------------------------------
# The portfile, verified from outside.


def reconcile_portfile(health: dict[str, Any], port: int, token: str) -> str | None:
    """Make `engine.json` describe the engine that is actually answering.

    THIS IS THE FIX FOR A BUG THE ENGINE CANNOT FIX ITSELF. Uvicorn runs ASGI
    lifespan startup BEFORE it binds the socket, so `write_portfile` is called
    by a process that does not yet know whether it will get the port - and
    `write_portfile` also, correctly, declines to overwrite a file owned by a
    live pid. Between those two facts there is a window in which the file on
    disk describes an engine that is not the one serving, and every client that
    reads it then authenticates against the wrong secret and gets a 401 with no
    explanation. From out here it is a two-line repair, because everything
    needed is either observed from the live `/health` response or was pinned by
    this launcher.

    Returns a sentence when it changed something, `None` when the file was
    already right.
    """
    published = read_portfile()
    live_id = health.get("engine", {}).get("engine_id")
    if published and published.get("engine", {}).get("engine_id") == live_id:
        if published.get("token") == token:
            return None
        note = "the token in engine.json was not the one this engine accepts"
    elif published is None:
        note = "engine.json was missing"
    else:
        note = (
            f"engine.json described engine "
            f"{published.get('engine', {}).get('engine_id')} (pid "
            f"{published.get('pid')}), not the one answering on {port}"
        )

    payload = {
        "host": "127.0.0.1",
        "port": port,
        "base_url": f"http://127.0.0.1:{port}",
        "token": token,
        "pid": health["engine"]["pid"],
        "service": health["service"],
        "portfile_version": health["portfile_version"],
        "engine": health["engine"],
        "build": health["build"],
        "schema": {"build_knows": health["schema"]["build_knows"]},
        "database": health.get("database", {}).get("path"),
    }
    path = portfile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return f"rewrote {path.name} from the live engine: {note}"


def discard_stale_portfile(port: int) -> str | None:
    """Delete a portfile only after proving nothing it describes is alive.

    Called when the port is FREE, which is the proof: whatever `engine.json`
    says, no engine is answering there. Left in place, `write_portfile`'s
    incumbent check can defer to a pid that has been recycled to an unrelated
    process, and the new engine then serves a token nobody has.
    """
    published = read_portfile()
    if not published:
        return None
    if int(published.get("port", port) or port) != port:
        # It describes some other engine on some other port. Not ours to touch.
        return None
    path = portfile_path()
    try:
        path.unlink()
    except OSError:
        return None
    return (
        f"removed a stale {path.name} describing pid {published.get('pid')} on "
        f"{port}, where nothing is listening"
    )


# ---------------------------------------------------------------------------
# The UI.


def node_executable() -> str | None:
    return shutil.which("node")


def start_ui(port: int, foreground: bool) -> subprocess.Popen:
    """Vite in `frontend/`, started through `node` directly.

    **`node node_modules/vite/bin/vite.js`, not `npm run dev`, and the reason
    is measured rather than stylistic.** `npm` on Windows is `npm.cmd`, which
    `CreateProcess` hands to the command interpreter, and a `.cmd` started with
    `DETACHED_PROCESS` - no console - WRITES NOTHING TO ITS REDIRECTED HANDLES.
    Measured here: the same Vite start produced 400 bytes of output attached
    and an empty `logs/ui.log` detached. An empty log at the moment something
    fails is failure 2 from the module docstring wearing a different hat, and
    it is not acceptable in a file whose whole argument is that a failure must
    be visible. `node` is a real executable and its output survives.

    It removes a shell from the path as a side effect, which is worth stating
    given invariant 1. That invariant is about the PRODUCT, and nothing under
    `app/` can reach this file - `tests/test_the_launcher_refuses_to_guess.py`
    asserts no module in `app/` imports it - but a developer launcher that
    needs no interpreter is still better than one that does.
    """
    frontend = REPO_ROOT / "frontend"
    if not (frontend / "node_modules").is_dir():
        raise LaunchError(
            f"{frontend / 'node_modules'} does not exist, so the UI cannot "
            "start. Run:\n\n    cd frontend && npm install\n\n"
            "or pass --no-ui to start the engine on its own.",
            exit_code=4,
        )
    node = node_executable()
    if node is None:
        raise LaunchError(
            "node is not on PATH, so the UI dev server cannot start. Install "
            "Node.js, or pass --no-ui to start the engine on its own.",
            exit_code=4,
        )
    vite = frontend / "node_modules" / "vite" / "bin" / "vite.js"
    if not vite.is_file():
        raise LaunchError(
            f"{vite} is missing, so Vite cannot start. Run:\n\n"
            "    cd frontend && npm install\n",
            exit_code=4,
        )
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    handle = UI_LOG.open("w", encoding="utf-8")
    options: dict[str, Any] = {
        "cwd": str(frontend),
        "stdout": handle,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
        "env": dict(os.environ),
    }
    if not foreground:
        options = _detached(**options)
    # `--port` and `--strictPort` on the command line rather than trusting the
    # config, and both of them together. `frontend/vite.config.ts` pins 5199
    # with `strictPort` for a reason it states: a stale process on Vite's
    # default port once served a DIFFERENT app and a screenshot taken against
    # it was reported as evidence for this one. Naming the port here keeps
    # `--ui-port` honest - the port this launcher PROBED and the port Vite
    # BOUND are the same number - and repeating `--strictPort` means a
    # collision is a loud failure rather than a silent move to 5200.
    return subprocess.Popen(
        [node, str(vite), "--port", str(port), "--strictPort"], **options
    )


def wait_for_ui(
    child: subprocess.Popen, port: int, timeout: float = UI_READY_TIMEOUT
) -> None:
    """Wait until our dev server answers its own identity route."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        code = child.poll()
        if code is not None:
            raise LaunchError(
                f"the UI dev server exited with code {code} before it was "
                f"ready.\n--- {UI_LOG} ---\n{_tail(UI_LOG)}",
                exit_code=4,
            )
        probe = probe_ui(port, timeout=2.0)
        if probe.state == "ours-current":
            return
        time.sleep(0.3)
    raise LaunchError(
        f"the UI dev server did not answer http://{UI_HOST}:{port}"
        f"{UI_IDENTITY_PATH} within {timeout:.0f}s.\n"
        f"--- {UI_LOG} ---\n{_tail(UI_LOG)}",
        exit_code=4,
    )


# ---------------------------------------------------------------------------
# Reporting.


def connected_model(port: int, token: str) -> str:
    """What model this engine is pointed at, asked through the real API.

    Through `/api/providers` with the bearer token rather than by opening the
    database, and that is deliberate: it exercises the token this launcher just
    pinned, so a summary line that reads "connected: granite4-hermes" is also
    proof that authentication works end to end. When it says
    `could not read (401)`, the handshake is broken and you find out here
    rather than in a browser tab twenty minutes later.
    """
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/providers",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            rows = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return f"could not read ({error.code})"
    except (urllib.error.URLError, OSError, ValueError) as error:
        return f"could not read ({error})"
    if not isinstance(rows, list) or not rows:
        return "none configured"
    active = [row for row in rows if row.get("is_active")]
    if not active:
        return f"{len(rows)} configured, none active"
    row = active[0]
    key = "key in keychain" if row.get("has_key") else "NO KEY"
    return f"{row.get('name')} -> {row.get('model')} ({key})"


def _describe_build(build: dict[str, Any]) -> str:
    sha = build.get("sha")
    short = sha[:12] if isinstance(sha, str) else f"unknown ({build.get('sha_source')})"
    dirty = build.get("dirty")
    if dirty is True:
        state = "dirty"
    elif dirty is False:
        state = "clean"
    else:
        state = f"dirty unknown ({build.get('dirty_source')})"
    fingerprint = str(build.get("code_fingerprint", ""))[:12]
    return f"{short} {state} - app/ fingerprint {fingerprint} over {build.get('code_files')} files"


def summarise(
    health: dict[str, Any],
    port: int,
    token: str,
    ui_port: int | None,
    notes: list[str],
) -> str:
    schema = health.get("schema", {})
    database = health.get("database", {})
    lines = [
        "",
        "  ML HARNESS IS RUNNING",
        "  " + "-" * 66,
        f"  engine     http://127.0.0.1:{port}   pid {health['engine']['pid']}"
        f"   engine_id {health['engine']['engine_id'][:12]}",
        f"  build      {_describe_build(health.get('build', {}))}",
        f"  schema     build knows {schema.get('build_knows')}, database at "
        f"{schema.get('database_at')}",
        f"  database   {database.get('path')}  ({database.get('runs')} runs)",
        f"  model      {connected_model(port, token)}",
    ]
    if ui_port is not None:
        lines.append(f"  ui         http://{UI_HOST}:{ui_port}   <- OPEN THIS")
    else:
        lines.append("  ui         not started (--no-ui)")
    lines.append(f"  logs       {ENGINE_LOG}")
    if ui_port is not None:
        lines.append(f"             {UI_LOG}")
    if notes:
        lines.append("  " + "-" * 66)
        for note in notes:
            lines.append(f"  note       {note}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The command.


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="start.sh",
        description=(
            "Start the ML Harness engine and UI, verify they are the ones you "
            "meant, and print what is running."
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MLH_PORT", DEFAULT_PORT)),
        help=f"engine port (default {DEFAULT_PORT}, or $MLH_PORT)",
    )
    parser.add_argument(
        "--ui-port",
        type=int,
        default=int(os.environ.get("MLH_UI_PORT", DEFAULT_UI_PORT)),
        help=f"Vite dev server port (default {DEFAULT_UI_PORT})",
    )
    parser.add_argument(
        "--no-ui", action="store_true", help="engine only; do not start Vite"
    )
    parser.add_argument(
        "--rotate-token",
        action="store_true",
        help=(
            "mint a fresh bearer token instead of carrying forward the one in "
            "engine.json. Open browser tabs will need reloading."
        ),
    )
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="do not detach the children; Ctrl-C in this terminal stops them",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="report what is running and change nothing",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="stop the engine this launcher started on --port, and nothing else",
    )
    return parser.parse_args(argv)


def report_status(port: int, ui_port: int, expect_build: str) -> int:
    probe = probe_engine(port, expect_build=expect_build)
    decision = decide(probe)
    print(f"engine on {port}: {probe.state} - {decision.reason}")
    ui = probe_ui(ui_port)
    print(f"ui on {ui_port}: {ui.state} {ui.evidence}".rstrip())
    return 0 if probe.state == "ours-current" else 1


def stop_engine(port: int, expect_build: str) -> int:
    """Stop the engine on `port`. Found by walking the product as a stranger.

    THE LOST MOMENT, 2026-09-05. A clean clone, `pip install -e .`, then
    `.\\start.ps1` per the README. The engine starts DETACHED and prints its
    pid - and nothing anywhere says how to stop it. The README's flag list has
    `--status`, `--no-ui`, `--rotate-token`, `--port`, `--ui-port` and
    `--foreground`; `mlh` offers only `doctor`. So the documented way out of a
    started product was to find the pid yourself and kill it, which is the kind
    of thing a person does once and then stops trusting the launcher about.

    It reuses `replace_engine` rather than reimplementing termination, because
    that function already carries the two lessons this file was written for:
    terminate ONE pid and never a name, and prove the PORT closed rather than
    trusting that a dead pid means a free socket. A `--stop` that killed by
    name would have been three lines shorter and would have killed the job
    runner, the suite and every other lane on this machine.

    It refuses in three states rather than pretending, and each says what is
    true: nothing there, something there that is not ours, and something ours
    that will not let go of the port.
    """
    probe = probe_engine(port, expect_build=expect_build)
    if probe.state == "free":
        # `free`, not `closed`. The first version of this guessed the name and
        # printed "something is listening on 8099 and it is not this product
        # (free)" at an empty port - a sentence that contradicts itself in its
        # own parentheses. Caught by running it against a port with nothing on
        # it, which took one command and would have shipped otherwise.
        print(f"nothing is listening on {port}. Nothing to stop.")
        return 0
    if not str(probe.state).startswith("ours"):
        print(
            f"something is listening on {port} and it is not this product "
            f"({probe.state}). Nothing has been terminated - this launcher "
            "stops engines it can identify, and stopping anything else is a "
            "decision for the person who started it.",
            file=sys.stderr,
        )
        return 2
    # `replace_engine` returns the whole sentence, pid and engine id included.
    # Printing it verbatim rather than composing a second one keeps the words a
    # person reads on a stop identical to the words they read on a restart.
    print(replace_engine(probe, port))
    return 0


def check_dependencies() -> None:
    """Fail before starting anything if the engine cannot possibly run.

    `start_engine` uses `sys.executable`, so the interpreter running this file
    is the interpreter that will run the engine - which makes this check exact
    rather than a guess about some other environment. Without it the failure is
    a child that exits with `No module named uvicorn` and a log to read; this
    turns the most common first-run problem into the command that fixes it.
    """
    import importlib.util

    missing = [
        name
        for name in ("uvicorn", "fastapi")
        if importlib.util.find_spec(name) is None
    ]
    if missing:
        raise LaunchError(
            f"{sys.executable}\ncannot import {', '.join(missing)}, so the "
            "engine cannot start. From this directory:\n\n"
            "    python -m pip install -e .\n",
            exit_code=127,
        )


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    fingerprint, _ = identity.code_fingerprint()
    notes: list[str] = []

    if args.status:
        return report_status(args.port, args.ui_port, fingerprint)

    if args.stop:
        return stop_engine(args.port, fingerprint)

    check_dependencies()

    probe = probe_engine(args.port, expect_build=fingerprint)
    decision = decide(probe)

    if decision.action == "reuse" and args.rotate_token:
        # An explicit --rotate-token must not be a silent no-op. The only way
        # an engine accepts a different token is to be a different engine, so
        # asking for one is asking for a restart, and saying so beats quietly
        # reusing the process that still holds the old secret.
        decision = Decision(
            "replace",
            f"--rotate-token was given and the engine on {probe.port} "
            f"(pid {probe.pid}) cannot change the token it accepts",
        )

    if decision.action == "refuse":
        raise LaunchError(
            f"REFUSING TO TOUCH PORT {args.port}.\n  {decision.reason}\n\n"
            "This launcher only ever stops a process that identified itself "
            "as an ML Harness engine over this socket. Stop whatever is on "
            f"{args.port} yourself, or run with --port <other>.",
            exit_code=2,
        )

    carried = None if args.rotate_token else published_token()
    token = carried or secrets.token_urlsafe(32)

    if decision.action == "reuse":
        health = probe.payload or {}
        notes.append(decision.reason)
        # The reused engine minted or was handed its own token; the file is the
        # only place we can learn it, and if the file is wrong we say so rather
        # than reporting a token that will 401.
        published = read_portfile()
        token = (published or {}).get("token", token)
        if (published or {}).get("engine", {}).get("engine_id") != health.get(
            "engine", {}
        ).get("engine_id"):
            notes.append(
                f"WARNING: {portfile_path().name} does not describe the engine "
                "that is answering. Clients reading it will get 401. Run with "
                "--rotate-token to restart cleanly."
            )
    else:
        if decision.action == "replace":
            notes.append(replace_engine(probe, args.port))
        removed = discard_stale_portfile(args.port)
        if removed:
            notes.append(removed)
        nonce = secrets.token_hex(8)
        child = start_engine(args.port, token, nonce, args.foreground)
        health = wait_for_engine(child, args.port, fingerprint, nonce)
        notes.append(
            f"started the engine (launcher child pid {child.pid}, serving "
            f"pid {health['engine']['pid']}) "
            + (
                "with the token the last engine published, so a browser tab "
                "left open still works"
                if carried
                else "with a freshly minted token; reload any open tab"
            )
        )
        repaired = reconcile_portfile(health, args.port, token)
        if repaired:
            notes.append(repaired)

    ui_port: int | None = None
    if not args.no_ui:
        ui_probe = probe_ui(args.ui_port)
        if ui_probe.state == "ours-current":
            notes.append(f"reused the UI dev server already on {args.ui_port}")
        elif ui_probe.state == "foreign":
            raise LaunchError(
                f"port {args.ui_port} is taken by something that is not our "
                f"dev server, and it will not be touched. {ui_probe.evidence}",
                exit_code=4,
            )
        else:
            ui_child = start_ui(args.ui_port, args.foreground)
            wait_for_ui(ui_child, args.ui_port)
            notes.append(f"started the UI dev server as pid {ui_child.pid}")
        ui_port = args.ui_port

    print(summarise(health, args.port, token, ui_port, notes))
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return run(argv)
    except LaunchError as error:
        print("\nML HARNESS DID NOT START\n", file=sys.stderr)
        print(str(error), file=sys.stderr)
        print("", file=sys.stderr)
        return error.exit_code
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
