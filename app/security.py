"""The security boundary: bind localhost, require a token, refuse cross-site.

Before this file existed, `POST /jobs` accepted a free-text command, stored it,
and `app/runner.py` handed it to the system shell. There was no authentication,
no CORS policy and no `Origin` check anywhere in the app. Two different
attackers could use that:

1. **Any web page open in the user's browser.** A cross-site form POST to
   `http://127.0.0.1:8078/jobs` needs no preflight, so the browser sends it
   before any CORS rule is consulted. The page never reads the response and
   does not care - the side effect is the payload.
2. **Any other process on the machine**, including one running as a different
   local user, which can open a socket to `127.0.0.1` without a browser at all.

They need different answers, which is why there are two mechanisms here and not
one. The `Origin` check stops (1): a browser always tells us where a request
came from, and it cannot be talked out of it by the page. The bearer token
stops (2): a stranger cannot guess 256 bits, and the file holding it is written
user-only.

Neither is sufficient alone. The token alone leaves the browser case open,
because a same-origin page would carry the token and a CSRF is a request the
browser makes *for* the page. The `Origin` check alone leaves the local-process
case open, because a process that is not a browser simply omits the header.

## What is protected, exactly

`requires_token()` is the whole policy and it is deliberately short:

- **Every `/api/*` path**, read or write. This is the programmatic surface. A
  client that talks to it can attach a header.
- **Every `/oc/*` path**, read or write: OpenCode's protocol, spoken by
  `app/facade` over the same threads and tools. Their client authenticates
  with `Basic base64("opencode:<token>")`, which `token_matches` accepts as a
  second spelling of the same token - see there.
- **Every state-changing method** - `POST`, `PUT`, `PATCH`, `DELETE` - on every
  path. This is the rule that closes the hole: `POST /jobs` is covered by it
  whether or not anyone remembers to move the route under `/api/`.

with one exemption, listed by name in `BROWSER_FORM_ROUTES` so it cannot be
acquired by accident:

- **`POST /ui/intake`**, the one server-rendered HTML form. A browser form
  submit cannot attach an `Authorization` header, and the alternative -
  embedding the token in the page - would publish the token to any local reader
  of an unauthenticated `GET`, which trades a real defence for a cosmetic one.
  It is protected by the `Origin` check instead, it performs no execution (it
  writes an intake row), and it disappears with the server-rendered surface
  when React replaces it. See `docs/ARCHITECTURE.md` section 8.

**Known and accepted gap, stated rather than hidden:** read-only browser-
navigable routes (`GET /`, `GET /ui/*`, `GET /jobs/{id}/log`) do not require a
token, because the user reaches them by typing a URL and a browser cannot be
made to send a header. A local process can therefore read job logs. That is a
disclosure gap, not an execution gap, and it closes when the React surface
replaces those routes and every read moves under `/api/*`.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any

from app import db
from app import identity
from app.config import HOST, PORT


from app import paths

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Where the token is published for local clients to read. The launcher, the
#: CLI client and the tests all read the same file; nothing has a second source
#: of truth and no keychain is required to run the suite.
#:
#: AND `sys.path` DECIDES WHICH ENGINE A CLIENT TRUSTS, which is not obvious
#: from this line and was not drawn end to end until 2026-09-06. This is
#: `data_root()/engine.json`; `data_root()` prefers the checkout of
#: whichever `app` was imported; and which `app` is imported is decided by
#: `sys.path`. So one missing path entry moves the package, the data root,
#: this file and the token together - and on a machine where two checkouts
#: share a virtualenv with an editable install, a process that does not put
#: its own checkout first authenticates against the OTHER checkout's
#: engine. Measured, with the launcher-pinning explanation ruled out: see
#: `docs/judge_runs/2026-09-06-two-suites-two-checkouts-result.md`.
ENGINE_FILE = Path(
    os.environ.get("MLH_ENGINE_FILE") or paths.in_data_root("engine.json")
)

#: Methods that change state. Everything here needs a token on every path.
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: The one exemption, named so it is reviewable. See the module docstring.
#: EMPTY SINCE 2026-08-28, AND THE EMPTY SET IS THE POINT.
#:
#: This held `/ui/intake` - the one server-rendered form that changed state.
#: A browser form cannot set an Authorization header, so that POST was let
#: through the bearer-token boundary and defended by SameSite instead: a real
#: defence, and a DIFFERENT one from every other route's, which is why it was
#: named here rather than assumed anywhere.
#:
#: `docs/THE_PLAN.md` V.3 A9 retired the form, so there is nothing left that
#: needs the exemption. THE SET STAYS RATHER THAN THE BRANCH BEING DELETED,
#: because the branch is what a future form would have to be added to on
#: purpose - and a mechanism that has to be rebuilt to be used again is a
#: mechanism somebody rebuilds in a hurry, differently, somewhere else.
BROWSER_FORM_ROUTES: frozenset[str] = frozenset()

#: Where `app/facade` mounts OpenCode's protocol. Named here because the
#: boundary has to know it, and a prefix spelled twice is a prefix that one day
#: differs between the router and the rule protecting it.
FACADE_PREFIX = "/oc"

#: The only username a `Basic` credential may carry. Their client sends it
#: unconditionally; see `token_matches`.
BASIC_USERNAME = "opencode"

_TOKEN: str | None = None


class Denied(Exception):
    """A request that the boundary refuses, carrying the status to return."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def current_token() -> str:
    """The token this engine process accepts.

    Generated once per process and cached. `MLH_TOKEN` overrides it so a
    launcher can pin the value it is about to hand to a child, and so a test can
    run against a known token - but the default path invents 256 bits of
    `secrets` entropy and never falls back to a constant. A default token is
    worse than no token, because it reads as protection.
    """
    global _TOKEN
    if _TOKEN is not None:
        return _TOKEN
    from_env = os.environ.get("MLH_TOKEN")
    _TOKEN = from_env if from_env else secrets.token_urlsafe(32)
    return _TOKEN


def reset_token_for_tests() -> None:
    """Drop the cached token so a test can exercise generation."""
    global _TOKEN
    _TOKEN = None


#: THE DESKTOP SHELL'S OWN ORIGIN, MEASURED RATHER THAN LOOKED UP.
#:
#: `docs/THE_PLAN.md` Phase V A7 called this "the single highest-risk unknown"
#: of the installer milestone and refused to guess at it, because widening a
#: security boundary on the strength of a blog post is the boundary loosened by
#: an assumption. So it was measured: `scripts/origin_spike.py` served a page to
#: a real Tauri v2 window on this machine, 2026-08-28, WebView2 runtime
#: 151.0.4129.107, and recorded what it sent.
#:
#:     packaged (frontendDist)  Origin: http://tauri.localhost
#:                              Sec-Fetch-Site: cross-site
#:     dev (devUrl)             Origin: http://localhost:5199
#:                              Sec-Fetch-Site: same-origin
#:
#: **Only the packaged one is admitted, and the difference is the whole of the
#: argument.** `tauri.localhost` is WebView2's internal custom-protocol host: no
#: page a browser can navigate to has that origin, so admitting it widens
#: nothing a website can reach. `http://localhost:5199` is an ordinary origin
#: any page served on that port can have - and the dev path does not need it,
#: because Vite's proxy strips `Origin` and `origin_is_allowed` already treats
#: a missing one as "not a browser".
#:
#: The bearer token still does the authenticating either way. This check is CSRF
#: defence, and CSRF is a browser attack: a non-browser client that forged this
#: header gains nothing it did not already have by sending no header at all.
SHELL_ORIGIN = "http://tauri.localhost"


def allowed_origins(port: int | None = None) -> set[str]:
    """The only origins a browser may name.

    Both spellings of loopback, because a user who types `localhost` and a user
    who types `127.0.0.1` are the same user - plus the desktop shell's own
    custom-protocol origin, which is not a spelling of anything a browser can
    navigate to. Nothing else: no LAN address, no hostname, no `file://`.
    """
    port = PORT if port is None else port
    return {
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
        SHELL_ORIGIN,
    }


def origin_is_allowed(origin: str | None, port: int | None = None) -> bool:
    """Is this `Origin` header acceptable?

    A missing `Origin` is allowed. That is not a loophole: browsers attach
    `Origin` to every request that could be a CSRF, so *absent* means the caller
    is not a browser - a curl, the launcher, a test - and those are exactly the
    callers the bearer token is there to check. Rejecting a missing `Origin`
    would break every non-browser client while stopping no attack.
    """
    if origin is None or origin == "":
        return True
    if origin == "null":
        # A sandboxed iframe or a `file://` page. Never ours.
        return False
    return origin in allowed_origins(port)


def requires_token(method: str, path: str) -> bool:
    """Does this request need `Authorization: Bearer <token>`?

    The whole policy, in one function, so a reviewer can read it in ten seconds
    and a test can assert on it without speaking HTTP.
    """
    method = method.upper()
    path = path.rstrip("/") or "/"
    # CS2: the remote-control URL is its own capability (hashed token in the
    # path). Engine bearer would force the phone to know the desktop token.
    if path.startswith("/remote/"):
        return False
    if path.startswith("/api/"):
        return True
    # THE OPENCODE FACADE IS THE SAME SURFACE UNDER ANOTHER NAME. `app/facade`
    # mounts their protocol at `/oc`, and everything it answers - transcripts,
    # the approval dock, the button that runs a gated tool - is what `/api/*`
    # answers. A read there is a read of the person's conversations, so reads
    # need the token too, exactly as they do under `/api/`.
    if path == FACADE_PREFIX or path.startswith(FACADE_PREFIX + "/"):
        return True
    if method in UNSAFE_METHODS:
        return path not in BROWSER_FORM_ROUTES
    return False


def token_matches(header_value: str | None) -> bool:
    """Constant-time check of an `Authorization` header against our token.

    TWO SPELLINGS OF ONE SECRET. `Bearer <token>` is what every client of this
    engine has always sent. `Basic base64("opencode:<token>")` is what
    OpenCode's client sends - `authTokenFromCredentials` in their
    `runtime/server/api.ts` hard-codes the username `opencode` and puts the
    server's password after it - and the desktop app hands their client this
    engine's token as that password. Accepting it is not a second credential:
    it is the same 256 bits, and a Basic header carrying anything else fails
    exactly as a wrong Bearer token does.

    The username is checked as well as the password, and a wrong one is a
    refusal. Nothing depends on the username, but a header that names a user we
    do not have is not a header this engine issued, and accepting it would make
    the check wider than the sentence above says it is.
    """
    if not header_value:
        return False
    scheme, _, presented = header_value.partition(" ")
    presented = presented.strip()
    if not presented:
        return False
    if scheme.lower() == "bearer":
        return secrets.compare_digest(presented, current_token())
    if scheme.lower() == "basic":
        try:
            decoded = base64.b64decode(presented, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return False
        username, separator, password = decoded.partition(":")
        if not separator:
            return False
        # Both comparisons run whatever the first one says, so the time taken
        # does not reveal which half was wrong.
        user_ok = secrets.compare_digest(username, BASIC_USERNAME)
        password_ok = secrets.compare_digest(password, current_token())
        return user_ok and password_ok
    return False


def check(method: str, path: str, headers: Any) -> None:
    """Raise `Denied` if this request must not proceed.

    Order matters. The `Origin` check runs first and answers 403, because a
    cross-site request is refused on the grounds of where it came from - saying
    401 there would invite the page to go looking for a token.
    """
    origin = headers.get("origin")
    if not origin_is_allowed(origin):
        raise Denied(403, "cross-site request refused")
    if requires_token(method, path) and not token_matches(
        headers.get("authorization")
    ):
        raise Denied(401, "missing or invalid bearer token")


def _pid_is_running(pid: Any) -> bool:
    """Is this process still alive? Used to avoid stealing a live portfile."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        # SYNCHRONIZE only: enough to WAIT on the process, and not enough to
        # do anything to it. No shelling out to tasklist.
        handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)
        if not handle:
            return False
        try:
            # AN OPEN HANDLE IS NOT A LIVE PROCESS, and believing it was
            # broke the product on every restart after the first.
            #
            # Windows keeps a pid resolvable while ANY handle to it is still
            # open, even after the process has exited. The Tauri shell holds
            # exactly such a handle - `OURS.lock() = Some(child)` in
            # src-tauri/src/engine.rs keeps the spawned engine's `Child` for
            # the life of the window - so a dead engine's pid went on
            # answering `OpenProcess` forever.
            #
            # What that did, measured on the owner's machine 2026-09-11:
            # `write_portfile` saw the previous engine as the live incumbent,
            # declined to publish, and left `engine.json` naming a token the
            # listening engine had never heard of. Every local client got 401
            # and the app opened with no threads in it. Deleting the file by
            # hand and restarting brought all sixty-three back.
            #
            # `WaitForSingleObject(h, 0)` asks the question that was meant:
            # a process handle is SIGNALLED when the process has exited, so
            # WAIT_OBJECT_0 means gone and WAIT_TIMEOUT means running. It
            # costs one more call and no extra access right.
            signalled = ctypes.windll.kernel32.WaitForSingleObject(handle, 0)
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
        WAIT_OBJECT_0 = 0x00000000
        return signalled != WAIT_OBJECT_0
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def portfile_payload(port: int | None = None) -> dict[str, Any]:
    """Exactly what gets written, built separately so a test can read it.

    WHERE TO SEND A REQUEST, and WHAT WILL ANSWER IT. The first five fields are
    the original file and they are all address; every field after them is
    identity, and they are here because the address alone let five failures
    happen in one evening (see `app/identity.py` for the list).

    `pid` is kept, and what it means is narrower than it looks. It is
    `os.getpid()` - THE PROCESS THAT WROTE THIS FILE AND WILL ANSWER REQUESTS.
    It is *not*, and cannot be made to be, "the process that owns the listening
    socket": under `uvicorn --reload` the socket is created by the supervisor
    and the app is imported in a child, so the pid a reader most wants is one
    this process does not have. That is the exact shape of the first failure -
    `taskkill` on a published pid that killed something which was not the
    server - so the fix is not a better guess at the pid, it is
    **`engine_id`**: a value this process invented, which cannot be wrong,
    which travels in this file AND comes back from `/health`. Anything that
    wants to know "is the thing on this port the thing this file describes"
    asks the socket and compares that, and `scripts/launch.py` will not
    terminate a process on any weaker evidence.

    `database` is published because "which database did this engine open" is
    the other question a stale engine answers wrongly and silently, and because
    a launcher cannot print it otherwise. It is read from `db.DB_PATH` at call
    time rather than imported, since the test sandbox rebinds that global and a
    portfile naming the real database from inside a sandbox would be a lie of
    exactly the kind this function is being extended to stop telling.
    """
    port = PORT if port is None else port
    return {
        "host": HOST,
        "port": port,
        "base_url": f"http://{HOST}:{port}",
        "token": current_token(),
        "pid": os.getpid(),
        **identity.identity(),
        "database": str(db.DB_PATH),
    }


def write_portfile(
    port: int | None = None, path: Path | None = None
) -> Path:
    """Publish where this engine is, and what it is, for local clients.

    Written user-only. `os.chmod(0o600)` is honest on POSIX and close to
    decorative on Windows, where the file's protection actually comes from the
    ACL it inherits - so this is a belt on POSIX and a label on Windows, and
    saying so here is better than implying a guarantee we do not have.

    **It will not overwrite a portfile that belongs to a process still running.**
    Found the hard way: an engine was serving on 8078, a second process started
    the same app, and its startup rewrote `engine.json` with a token the
    listening engine had never heard of. Every local client then authenticated
    against the wrong secret and got 401 - including a job that had already
    started. Anything that runs the app writes this file, so "the last process
    to start owns the token" is not a rule that can hold. The process holding
    the port owns the portfile; everyone else leaves it alone.

    **When it declines, it now SAYS SO, on stderr.** Silence was the second
    half of the 401 mystery: a process could start, find the file taken, serve
    on a token no client had, and give no indication anywhere that the file on
    disk described somebody else. One line to stderr costs nothing and turns a
    confusing 401 into a sentence naming both pids.

    **The gap this function still has, stated rather than hidden.** Uvicorn
    runs ASGI lifespan startup BEFORE it binds the socket, so this file is
    written by a process that does not yet know whether it will get the port.
    An engine that then dies on `[Errno 10048]` has already published. The
    incumbent check above catches the common case - the process holding the
    port is alive, so its portfile is left alone - and it cannot catch the case
    where the incumbent's own portfile entry is stale. Closing it properly
    needs a hook that runs after the bind, which the ASGI lifespan protocol
    does not have. `scripts/launch.py` closes it from outside instead: it waits
    for `/health` to answer, checks that the answering `engine_id` is the one
    in this file, and repairs the file from the live engine when they differ.
    A bare `python -m uvicorn app.main:app` does not get that, which is one of
    the reasons `./start.sh` exists.
    """
    port = PORT if port is None else port
    path = ENGINE_FILE if path is None else Path(path)

    existing = read_portfile(path)
    if existing:
        owner = existing.get("pid")
        if (
            owner != os.getpid()
            and _pid_is_running(owner)
            and _incumbent_answers(existing)
        ):
            _announce_deferral(path, existing)
            return path
    payload = portfile_payload(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def _incumbent_answers(existing: dict[str, Any]) -> bool:
    """Is the engine the portfile describes actually the one answering?

    A LIVE PID IS NOT A LIVE ENGINE. Windows hands a dead process's pid to the
    next process that asks: on 2026-09-23 a scratch engine's pid was reused by
    a browser renderer, `_pid_is_running` read it as alive, the next engine
    deferred to it, and every local client authenticated against a token
    nobody was serving - 401 on every request, with the engine's own log the
    only witness. So the guard now asks the incumbent itself, the way
    `scripts/launch.py` repairs the file from outside: one local GET of
    `/health` at the portfile's own address, and the answer counts only when
    its `engine_id` is the one in the file. Nothing answering, or a different
    engine answering, means the file is stale and this process may publish.
    The probe is unauthenticated and bounded; `/health` needs no token.
    """
    base = str(existing.get("base_url") or "").rstrip("/")
    expected = str((existing.get("engine") or {}).get("engine_id") or "")
    if not base or not expected:
        return False
    import urllib.request

    try:
        with urllib.request.urlopen(base + "/health", timeout=1.5) as answer:
            body = json.loads(answer.read() or b"{}")
    except Exception:  # noqa: BLE001 - any failure to answer is "not there"
        return False
    return str((body.get("engine") or {}).get("engine_id") or "") == expected


def _announce_deferral(path: Path, existing: dict[str, Any]) -> None:
    """Say out loud that this process did not publish its token.

    Only when the incumbent's token differs from ours, because a matching token
    means a launcher pinned `MLH_TOKEN` for both and no client is going to be
    surprised - that is the arrangement working, not a collision.
    """
    if existing.get("token") == current_token():
        return
    print(
        f"ML HARNESS: {path} already belongs to pid {existing.get('pid')}, "
        f"which is still running, so this process (pid {os.getpid()}, engine "
        f"{identity.ENGINE_ID}) did NOT publish its token. Local clients will "
        "authenticate against the other engine and get 401 from this one.",
        file=sys.stderr,
        flush=True,
    )


def read_portfile(path: Path | None = None) -> dict[str, Any] | None:
    """What a local client reads to find the engine. `None` if not running."""
    path = ENGINE_FILE if path is None else Path(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def client_token(path: Path | None = None) -> str | None:
    """The token a *client* should present, without generating a new one.

    Deliberately not `current_token()`. A client that cannot find a token must
    send none and get a 401 it can report, rather than mint a fresh secret the
    engine has never heard of and fail with a confusing mismatch.
    """
    from_env = os.environ.get("MLH_TOKEN")
    if from_env:
        return from_env
    published = read_portfile(path)
    if published and isinstance(published.get("token"), str):
        return published["token"]
    return None


def auth_header(path: Path | None = None) -> dict[str, str]:
    """`Authorization` header for a local client, or `{}` if we have no token."""
    token = client_token(path)
    return {"Authorization": f"Bearer {token}"} if token else {}
