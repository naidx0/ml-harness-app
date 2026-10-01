"""The launcher's decisions, in the package, so a shell can ask them too.

`docs/THE_PLAN.md` Phase V step A6. `scripts/` is not in a wheel, and the Tauri
shell has to answer the same four questions the developer launcher answers - is
there an engine on this port, is it OURS, is it running MY code, should it be
replaced. A shell reimplementing `decide()` in Rust would be a second answer to
each of them, which is the "second place that goes stale" this repository
refuses everywhere else.

## What is here and what is deliberately not

**Here: everything that LOOKS.** Opening a TCP connection, asking `/health`,
reading `engine.json`, and turning what came back into a decision. All of it is
read-only, and `decide()` in particular has no side effects and no network at
all - it is a pure function of a `Probe`, which is what lets the interesting
cases (a foreign listener, an engine running yesterday's code) be tested without
arranging a real one.

**Not here: everything that ACTS.** `start_engine`, `replace_engine`,
`_terminate`, `start_ui` and the whole two-process dev loop stay in
`scripts/launch.py`. That split is the point rather than a convenience.

## The boundary this does NOT cross, said plainly because it looks like it might

`tests/test_the_launcher_refuses_to_guess.py` forbids anything under `app/` from
importing the launcher, on the argument that "invariant 1 says the product
executes no shell. This file starts processes, so the boundary between it and
`app/` has to be a fact rather than a habit."

That boundary is intact. `app/` still imports nothing from `scripts/` - the
dependency runs the other way, as it always did - and nothing in this module
spawns or kills anything. The product already starts processes where it must
(`app/hwdetect.py` runs `nvidia-smi`, `app/tools/sandbox.py` runs recipes), so
what invariant 1 forbids is a shell and a free-text command, neither of which is
anywhere near here. `tests/test_the_launcher_refuses_to_guess.py` now asserts
both halves rather than the one that was easy to grep for.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app import identity


@dataclass
class Probe:
    """What is on a port, and how sure we are.

    `state` is one of:

    - `free` - nothing accepted a connection. Start here.
    - `ours-current` - an ML Harness engine whose build matches this tree.
    - `ours-stale` - an ML Harness engine running different code.
    - `ours-unready` - our engine, right code, failing its own checks
      (a schema mismatch, a database it cannot open).
    - `foreign` - something is listening and it is not ours. NEVER killed.

    `payload` is the `/health` body when we got one. `evidence` is whatever we
    can say about a foreign listener, which is deliberately raw: a refusal has
    to name what it found or the person reading it cannot act on it.
    """

    state: str
    port: int
    payload: dict[str, Any] | None = None
    evidence: str = ""
    mismatch: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_ours(self) -> bool:
        return self.state.startswith("ours-")

    @property
    def pid(self) -> int | None:
        """The pid THE LIVE ENGINE reported. Never one read from a file."""
        if not self.payload:
            return None
        value = self.payload.get("engine", {}).get("pid")
        return int(value) if isinstance(value, int) else None


def port_is_open(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    """Will anything accept a TCP connection here?

    The cheapest question that distinguishes "free" from "occupied", and the
    one `_wait_for_port_to_close` polls. It says nothing about *what* is there,
    which is why nothing decides to kill anything on the strength of it.

    **EVERY address `host` resolves to, not the first one.** This was written
    as a single `connect(("127.0.0.1", port))` and it was wrong about the UI
    within an hour of being written. Vite binds `localhost`, and Node resolves
    that to `::1` first, so the dev server was listening on IPv6 loopback and
    nothing at all was on IPv4 loopback. A launcher that asked 127.0.0.1
    concluded the port was free, started a second Vite, and watched
    `--strictPort` refuse it - having reported the first one as absent. Worse
    than the wrong answer was HOW it was wrong: connecting to 127.0.0.1 when
    something holds `::1` on this machine TIMES OUT rather than being refused,
    so the mistake also cost a full second on every poll.

    The engine binds `127.0.0.1` explicitly (`app/config.py` says why it is not
    configurable), so for the engine this loop finds exactly one address. It is
    the UI that needs it, and having one function that is right for both is
    better than two that differ by a subtlety nobody will remember.
    """
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    for family, socket_type, protocol, _, address in addresses:
        with socket.socket(family, socket_type, protocol) as sock:
            sock.settimeout(timeout)
            try:
                sock.connect(address)
            except OSError:
                continue
            return True
    return False


def probe_engine(
    port: int,
    expect_build: str | None = None,
    expect_launch: str | None = None,
    timeout: float = 4.0,
) -> Probe:
    """Ask the port what it is. Never assume, never kill on the answer alone.

    `expect_build` DEFAULTS TO THIS TREE, and that is the whole of a defect
    that cost Max a day and a half. Staleness is decided by the ENGINE: the
    caller sends `?expect_build=`, `/health` compares, and answers 409 when it
    disagrees. Send nothing and there is nothing to compare, so the engine
    answers 200 and this function reads 200 as `ours-current` - "I could not
    check" reported as "it matches", which is the same shape as a transform
    that removes nothing and returns success.

    `scripts/launch.py` always passed it, so the launcher was right. Nothing
    else did. On 2026-09-20 his app was answering from an engine started
    2026-09-19 at 01:08 on commit c0cccd4, three commits back, and
    `decide(probe_engine(8078))` said *"an ML Harness engine (pid 15876) is
    already on 8078 and its build matches this working tree"*. Two whole
    cycles of fixes had never run.

    Passing `expect_build=""` explicitly still skips the comparison, for a
    caller that genuinely only wants to know whether anybody is there.
    """
    if expect_build is None:
        # Not a default argument: `identity.code_fingerprint()` reads files,
        # and a default is evaluated once at import.
        expect_build = identity.code_fingerprint()[0]
    if not port_is_open(port, timeout=min(timeout, 1.0)):
        return Probe("free", port)

    url = f"http://127.0.0.1:{port}/health"
    expectations = {
        "expect_build": expect_build,
        "expect_launch": expect_launch,
    }
    stated = "&".join(
        f"{name}={value}" for name, value in expectations.items() if value
    )
    if stated:
        url += f"?{stated}"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        # 409 and 503 are OUR engine answering honestly, so the body matters
        # more than the status. `HTTPError` is a response, not a failure.
        status, body = error.code, error.read()
    except (urllib.error.URLError, OSError) as error:
        return Probe(
            "foreign",
            port,
            evidence=(
                f"something accepted a TCP connection on {port} but did not "
                f"answer an HTTP GET /health: {error}"
            ),
        )

    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
    except ValueError:
        preview = body[:200].decode("utf-8", errors="replace").strip()
        return Probe(
            "foreign",
            port,
            evidence=(
                f"HTTP {status} from {url}, but the body is not JSON. First "
                f"bytes: {preview!r}"
            ),
        )

    if not isinstance(payload, dict) or payload.get("service") != identity.SERVICE:
        return Probe("foreign", port, evidence=_unidentified(url, status, payload))

    if status == 409:
        return Probe(
            "ours-stale", port, payload=payload,
            mismatch=list(payload.get("mismatch", [])),
        )
    if status == 503:
        return Probe("ours-unready", port, payload=payload)
    if status == 200:
        return Probe("ours-current", port, payload=payload)
    return Probe(
        "ours-unready",
        port,
        payload=payload,
        evidence=f"unexpected HTTP {status} from our own engine",
    )


def _unidentified(url: str, status: int, payload: Any) -> str:
    """Why we are not going to touch whatever answered.

    One case gets its own sentence, because it is the one that will actually
    happen to somebody: an ML Harness engine started from code OLDER than
    `app/identity.py` answers `/health` with exactly `{"status": "ok"}` and no
    identity at all. It is ours, and there is no way for us to know that, which
    is precisely the hole this work closes. Refusing to kill it is still the
    right call - a launcher that killed anything answering `status: ok` would
    kill half the dev servers on the machine - but telling somebody "something
    else is on this port" when the honest answer is "a version of us from
    before we could tell" sends them hunting the wrong thing.
    """
    if isinstance(payload, dict) and "service" not in payload and "status" in payload:
        return (
            f"HTTP {status} from {url} answered {json.dumps(payload)[:120]} - a "
            "health route with no identity in it. That is what an ML Harness "
            "engine built before app/identity.py looks like, and there is no "
            "way from out here to tell it from any other server that has a "
            "/health. Stop it and run this again; the engine that replaces it "
            "will be identifiable."
        )
    return (
        f"HTTP {status} from {url} and the body is JSON, but it does not say "
        f"service={identity.SERVICE!r}. Something else is on this port: "
        f"{json.dumps(payload)[:200]}"
    )


@dataclass
class Decision:
    """`action` is `start`, `reuse`, `replace` or `refuse`, plus why."""

    action: str
    reason: str


def decide(probe: Probe) -> Decision:
    """What to do about what we found. No side effects, no network.

    Separated from everything that acts so the interesting cases - a foreign
    listener, an engine running yesterday's code - can be tested without
    arranging a real one. `tests/test_the_launcher_refuses_to_guess.py` covers
    all five branches.
    """
    if probe.state == "free":
        return Decision("start", f"nothing is listening on {probe.port}")
    if probe.state == "ours-current":
        return Decision(
            "reuse",
            f"an ML Harness engine (pid {probe.pid}) is already on "
            f"{probe.port} and its build matches this working tree",
        )
    if probe.state == "ours-stale":
        fields = ", ".join(item.get("field", "?") for item in probe.mismatch)
        return Decision(
            "replace",
            f"the engine on {probe.port} (pid {probe.pid}) is ML Harness but "
            f"not this build - it disagrees on: {fields or 'build'}",
        )
    if probe.state == "ours-unready":
        failing = ", ".join(
            check.get("name", "?")
            for check in (probe.payload or {}).get("checks", [])
            if not check.get("ok")
        )
        return Decision(
            "replace",
            f"the engine on {probe.port} (pid {probe.pid}) is ours but not "
            f"healthy - failing: {failing or 'unknown'}",
        )
    return Decision(
        "refuse",
        f"port {probe.port} is taken by a process this launcher cannot "
        f"identify, so it will not be touched. {probe.evidence}",
    )


def portfile_path() -> Path:
    from app import security

    return security.ENGINE_FILE


def read_portfile() -> dict[str, Any] | None:
    try:
        return json.loads(portfile_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def published_token() -> str | None:
    """The token already in `engine.json`, so a restart does not log out a tab.

    See failure 5 in the module docstring, and `--rotate-token` for the way
    out. Read before anything is deleted or started, because both of those can
    destroy it.
    """
    published = read_portfile()
    if published and isinstance(published.get("token"), str):
        return published["token"]
    return None


