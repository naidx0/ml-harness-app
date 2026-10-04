from __future__ import annotations

import asyncio
import html
import json
import time
from contextlib import asynccontextmanager
from typing import Any, Literal
from uuid import uuid4

import markdown
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from fastapi.responses import PlainTextResponse, StreamingResponse
from app import activity, contextwindow, effects, longrun, planfile, remote, subagents, usage
from app import asking, interrupt, memory, modes
from app import autonomy
from app import feasibility
from app import plan
from pathlib import Path
from app import storm
from app import conductor
from app import journey_report
from app import stage
from app import diagnosis
from app import journey
from app import diagram
from app import events
from app import hwdetect
from app import identity
from app import instructions
from app import jobspec
from app import providers
from app import security
from app import theme
from app import tools
from app.config import PORT
from app.providers import secrets as provider_secrets
from app.providers import store as provider_store

from . import db


#: Context length the plan is budgeted against. Named once, not typed into three
#: call sites, and stated on the page rather than assumed silently.
PLAN_CONTEXT_TOKENS = 4096
PLAN_KV_QUANT = "q8_0"


def plan_inputs(answers: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Everything the three plan routes need, computed once from real inputs.

    This replaces `available_gb = 8.0`, `weights_gb = 4.19` and
    `activations_gb = 3.5`, which appeared literally at three call sites and
    made every plan for every user for every goal return the same verdict. The
    app could record that you own a 24 GB 4090 and still tell you your plan
    spilled on 8 GB.

    A hardware profile recorded through `POST /hardware` was typed by a person,
    so its provenance is `declared`, not `measured`. With no profile at all the
    VRAM figure is `defaulted` and the verdict is `UNKNOWN` - which is the
    honest answer, and the reason the fourth verdict exists.
    """
    profile = db.get_latest_hardware_profile()
    if profile is None or profile.get("vram_gb") is None:
        vram = feasibility.Field(
            None, "defaulted", "no hardware profile recorded"
        )
    else:
        vram = feasibility.Field(
            float(profile["vram_gb"]), "declared", "POST /hardware"
        )

    rec = feasibility.recommend(
        answers.get("goal", ""), vram, data_kind=answers.get("data_kind")
    )
    estimate = feasibility.estimate_vram(
        rec["params_b"],
        rec["quant"] if rec["quant"] in feasibility.BITS_PER_WEIGHT else "FP16",
        PLAN_CONTEXT_TOKENS,
        PLAN_KV_QUANT,
        geometry=rec["geometry"],
    )
    verdict_info = feasibility.verdict(
        vram,
        estimate["weights_gb"],
        estimate["kv_gb"],
        overhead_gb=estimate["overhead_gb"],
        geometry_provenance=estimate["geometry_provenance"],
    )
    return rec, estimate, verdict_info


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    # Publish where we are and how to talk to us. The launcher, the CLI client
    # and the tests all read this one file; there is no second source of truth
    # and no keychain in the path, which is what makes the suite able to
    # authenticate without one.
    security.write_portfile()
    # A run is a worker thread in this process, so any run still marked
    # `running` when this process starts is one whose engine died under it.
    # See `app/longrun.py::reap_orphans`.
    longrun.reap_orphans()
    # AFTER the runs, because a sub-agent's state is read from its child's run
    # and settling these against unsettled runs would record the wrong ending.
    subagents.reap_orphans()
    yield


app = FastAPI(title="ML Harness", version="0.1.1", lifespan=lifespan)


@app.middleware("http")
async def security_boundary(request: Request, call_next):
    """Every request passes the boundary before any route sees it.

    Middleware rather than a per-route dependency, deliberately. A dependency
    protects the routes somebody remembered to decorate, and the hole this
    replaces existed because `POST /jobs` was written without anyone thinking
    about authentication at all. A middleware cannot be forgotten by the next
    route, which is the property worth having.

    The policy itself lives in `app/security.py` as two pure functions so it can
    be read and tested without speaking HTTP.
    """
    try:
        security.check(request.method, request.url.path, request.headers)
    except security.Denied as denied:
        if request.url.path.startswith(security.FACADE_PREFIX + "/"):
            # Their client reads a declared status's body as their encoded
            # error; `{"detail": ...}` would reach it as a malformed response
            # rather than as "unauthorized".
            tag = "UnauthorizedError" if denied.status_code == 401 else "ForbiddenError"
            return JSONResponse(
                {"_tag": tag, "message": denied.detail}, status_code=denied.status_code
            )
        return JSONResponse(
            {"detail": denied.detail}, status_code=denied.status_code
        )
    return await call_next(request)


# Added last, so it wraps the boundary above and answers CORS preflight before
# the boundary runs. A preflight is not a state-changing request and has no
# `Authorization` header to check yet; this middleware refuses the ones from
# origins we do not allow, which is the half of the browser story that has to
# happen before the request is even sent. The other half - a *simple* cross-site
# POST, which needs no preflight and so never consults CORS at all - is what the
# `Origin` check in the boundary is for. Neither one alone is enough.
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(security.allowed_origins(PORT)),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    # Chromium's Private Network Access rule, measured on the desktop shell
    # 2026-08-31: `http://tauri.localhost` is not a name Chromium knows to be
    # loopback, so its fetches to 127.0.0.1 are public-to-private and the
    # preflight carries Access-Control-Request-Private-Network. Starlette
    # REFUSES those outright ("Disallowed CORS private-network") unless this
    # flag answers them. It widens nothing: the origin allowlist above still
    # decides who may ask at all, and every origin on it IS this machine.
    allow_private_network=True,
)



# The hardware router was written and never mounted, so GET /local_specs did not
# exist and nothing in the running product ever ran nvidia-smi. Every hardware
# number the app could show had to be typed in by hand.
app.include_router(hwdetect.router)

# OPENCODE'S PROTOCOL, UNDER `/oc`. The interface this product now draws is
# OpenCode's, and it speaks their server protocol; `app/facade` answers it with
# this engine's own threads, turns and tools, so their client runs unmodified.
# Mounted beside `/api` rather than in place of it: the outgoing interface
# keeps working until the cutover. `docs/PHASE-4-FACADE.md` is the design.
from app import facade  # noqa: E402 - the facade imports routes defined above lazily

app.include_router(facade.router)


class RunCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    params: dict[str, Any] = Field(default_factory=dict)


class MetricCreate(BaseModel):
    step: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=80)
    value: float

# Request bodies were typed as bare dicts and indexed directly, so a missing
# key was a KeyError and therefore a 500. Eight of nine ordinary bad payloads
# crashed. Declaring them as models hands validation to FastAPI, which answers
# 422 with the offending field named.
class IntakeCreate(BaseModel):
    session_id: str
    answers: dict[str, Any]


class JobCreate(BaseModel):
    """A job is a recipe, a verb and a config. It is never a command.

    `extra="forbid"` is load-bearing rather than tidy. The old contract took a
    free-text `cmd`; forbidding unknown fields means a caller still sending one
    gets a 422 naming `cmd` as unexpected, instead of having it silently
    ignored and being left to believe the command ran. A caller that is wrong
    should find out.
    """

    model_config = ConfigDict(extra="forbid")

    intake_id: str = Field(min_length=1)
    recipe: str = Field(min_length=1, max_length=64)
    kind: str = Field(min_length=1, max_length=16)
    config: dict[str, Any] = Field(default_factory=dict)


class HardwareCreate(BaseModel):
    gpu_name: str
    vram_gb: float
    ram_gb: float
    os: str
    disk_free_gb: float



#: What `/health` verifies before it will say `ok`, in the order it runs them.
#: Each entry is `(name, callable)` returning `(ok, detail, extra)`. A list
#: rather than a chain of `if`s so the response can report EVERY check rather
#: than the first one that failed - "the database is fine but the schema is
#: two versions behind" is a different afternoon from "the file is missing".
def _check_database_opens() -> tuple[bool, str, dict[str, Any]]:
    """Can this process open the database file it was pointed at?"""
    path = str(db.DB_PATH)
    try:
        connection = db.connect()
    except Exception as error:  # noqa: BLE001 - reported, never raised
        return False, f"cannot open {path}: {error}", {"path": path}
    connection.close()
    return True, f"opened {path}", {"path": path}


def _check_schema_agrees() -> tuple[bool, str, dict[str, Any]]:
    """Is the database at the version this build was written against?

    Not hypothetical, and not a nicety. An engine that knew schema 8 met a
    database at 9 and answered every request with a 500 - and `/health` said
    `ok` throughout, because nothing it looked at had anything to do with the
    database. This is the check that would have named it in one line.

    Read, not computed: the number comes from `schema_version`, the table the
    migration runner keeps its own state in.
    """
    known = identity.known_schema_version()
    try:
        with db.session() as connection:
            row = connection.execute(
                "SELECT MAX(version) FROM schema_version"
            ).fetchone()
        at = None if row is None or row[0] is None else int(row[0])
    except Exception as error:  # noqa: BLE001 - reported, never raised
        return (
            False,
            f"could not read schema_version: {error}",
            {"build_knows": known, "database_at": None},
        )
    extra = {"build_knows": known, "database_at": at, "agrees": at == known}
    if at is None:
        return False, "no schema_version row; the database is unmigrated", extra
    if at == known:
        return True, f"both at {known}", extra
    direction = "ahead of" if at > known else "behind"
    return (
        False,
        f"the database is at {at}, which is {direction} the {known} this "
        "build knows",
        extra,
    )


def _check_answers_a_real_query() -> tuple[bool, str, dict[str, Any]]:
    """Read two things the product actually depends on.

    `SELECT 1` would prove the connection and nothing else. These two prove the
    schema is really there: `runs` is migration 1's table and `harness_instance`
    carries the identity every artifact path is keyed on. Both reads and no
    writes - `db.get_instance()` would have been the natural call and it does
    an `INSERT OR IGNORE`, which is a write transaction on every poll of a
    route a launcher hits in a loop.
    """
    try:
        with db.session() as connection:
            runs = int(
                connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            )
            row = connection.execute(
                "SELECT instance_id FROM harness_instance WHERE id = 1"
            ).fetchone()
    except Exception as error:  # noqa: BLE001 - reported, never raised
        return False, f"query failed: {error}", {}
    instance = None if row is None else row[0]
    if instance is None:
        return False, f"{runs} runs, but this database has no identity row", {
            "runs": runs,
            "instance_id": None,
        }
    return (
        True,
        f"read {runs} runs and instance {instance}",
        {"runs": runs, "instance_id": instance},
    )


HEALTH_CHECKS = (
    ("database_opens", _check_database_opens),
    ("schema_agrees", _check_schema_agrees),
    ("answers_a_real_query", _check_answers_a_real_query),
)


def _run_health_checks() -> tuple[bool, list[dict[str, Any]], dict[str, Any]]:
    """Every check, in order. Returns `(ready, results, gathered_extras)`."""
    results: list[dict[str, Any]] = []
    gathered: dict[str, Any] = {}
    ready = True
    for name, check in HEALTH_CHECKS:
        try:
            ok, detail, extra = check()
        except Exception as error:  # noqa: BLE001 - a health route may not 500
            ok, detail, extra = False, f"{type(error).__name__}: {error}", {}
        ready = ready and ok
        results.append({"name": name, "ok": ok, "detail": detail})
        gathered[name] = extra
    return ready, results, gathered


@app.post("/api/engine/shutdown")
def shutdown_engine_ep() -> dict[str, Any]:
    """Exit this engine, so the app can start a fresh one in its place.

    THE APP IS ONE THING, AND RESTARTING IT IS A BUTTON. Max, 2026-09-21,
    looking at a banner that told him to run two shell commands: *"we seem to
    have lost the restart engine on the app button, the whole thing with the
    app should be one package, and the engine should be easy for people to
    restart, they shouldn't be running scripts on their own."* He is right,
    and the instruction was mine.

    The shell could already START an engine and could stop one IT had spawned
    (`engine::stop_if_ours`), which is deliberately narrow - a window must not
    kill a process a terminal owns. That left exactly the case that matters:
    an engine somebody else started, running older code, which the window can
    see is wrong and cannot replace.

    So the engine stops ITSELF, and the only caller that can ask is one
    holding its bearer token - which is published to `engine.json` with
    user-only permissions. That is a better identity check than a pid: a pid
    can be recycled, a token cannot be guessed, and nothing here kills a
    process it merely believes is ours. `scripts/launch.py --stop` keeps its
    own path and is unchanged; this is the same act, asked politely.

    The reply is sent BEFORE the exit: uvicorn is told to stop once this
    response has gone out, so the caller learns it worked rather than seeing a
    dropped connection and guessing.
    """
    import os
    import threading

    def _leave() -> None:
        # A beat for the response to reach the socket, then go. `os._exit`
        # rather than a signal: this process holds a port and a database
        # handle, and the next thing that happens is a fresh engine binding
        # the same port. An orderly shutdown that waits on a streaming
        # response would keep the port past the moment the caller starts
        # waiting for it to be free.
        time.sleep(0.25)
        os._exit(0)

    threading.Thread(target=_leave, daemon=True).start()
    return {
        "ok": True,
        "stopping": identity.ENGINE_ID,
        "pid": os.getpid(),
        "detail": (
            "This engine is exiting. Start a new one with the app's own "
            "control, or scripts/launch.py."
        ),
    }


@app.get("/health")
def health(
    expect_build: str | None = Query(
        None, description="code_fingerprint the caller is expecting"
    ),
    expect_schema: int | None = Query(
        None, description="schema version the caller is expecting"
    ),
    expect_pid: int | None = Query(
        None, description="pid the caller believes it started"
    ),
    expect_engine: str | None = Query(
        None, description="engine_id the caller read from engine.json"
    ),
    expect_launch: str | None = Query(
        None, description="MLH_LAUNCH_NONCE the caller gave the child it started"
    ),
) -> JSONResponse:
    """Readiness that means something: THIS process, THIS build, THIS schema,
    THIS database, and it can answer a real query.

    ## What was wrong with the old one

    It was `return {"status": "ok"}`. It proved that a FastAPI app was
    listening. That was never the question. On the evening this route was
    rewritten, a STALE engine holding port 8078 answered `ok` three times in a
    row while the engine somebody thought they had restarted was dead, and
    "restarted and confirmed" was reported to the user on that evidence. The
    old route could not have said anything else: nothing it read had any
    connection to the code it was running, the database it had opened, or the
    schema either of them expected.

    ## The design rule

    **A check written against this route must not be able to pass while the
    thing it is checking is wrong.** There are two halves to that, and only
    both together get there.

    *The engine says whether IT is consistent* - the `checks` list - and the
    status code follows. Not ready is `503`, so `curl -f` fails and a shell
    script cannot accidentally read a failure as a success. This half catches
    a schema mismatch, an unopenable database, a half-migrated file.

    *The CALLER says what it expects, and is told when it is wrong* - the four
    `expect_*` parameters, answered with `409`. This half is the one that
    catches the stale engine, and there is no way to get it without the
    caller's participation: an engine running last week's code is entirely
    consistent with itself and has no way to know it is not what you meant.
    So the question "is this the engine I meant" is only answerable by
    something that holds an opinion about the answer, and the route's job is to
    make holding one cost a query parameter. `scripts/launch.py` always passes
    `expect_build` and `expect_pid`, and every readiness wait in this
    repository goes through it.

    `expect_launch` deserves its own sentence, because it is what a launcher
    should actually verify and the obvious alternative does not work.
    `expect_pid` was written first: a launcher knows the pid of the child it
    started, so ask the socket whether that is who is answering. It failed on
    the first run on this machine. `subprocess.Popen(...).pid` was 12468 and
    the server logged `Started server process [25392]`, because the venv's
    `python.exe` re-execs and the pid the parent holds is not the pid that
    ends up running the code. A pid is a fact about a process table, and the
    two ends of a socket do not share one - which is the same lesson as the
    stale `engine.json` that started all this, arriving from the other side.
    So the launcher hands its child a nonce in `MLH_LAUNCH_NONCE`, this route
    echoes it, and "is this my child" becomes a question about a value the
    child carries rather than an inference about the operating system.
    `expect_pid` stays, because a caller that legitimately knows the real pid -
    one that read it from an earlier `/health` - can still use it.

    When either comes back `409`, something else is on the port, and killing
    anything at that moment would be killing a stranger.

    ## Not authenticated, on purpose

    A client that has not yet read `engine.json` still has to be able to ask
    whether the engine on this port is the one it wants - that is the whole
    bootstrap. So this route carries no secret: no token, no key reference,
    nothing from the keychain. It does publish the database path and the
    interpreter path, which are already within the read-only disclosure this
    file's security boundary documents and accepts on loopback.
    """
    ready, checks, gathered = _run_health_checks()
    payload: dict[str, Any] = dict(identity.identity())
    payload["schema"] = {
        **payload["schema"],
        **{
            key: value
            for key, value in gathered["schema_agrees"].items()
            if key != "build_knows"
        },
    }
    payload["database"] = {
        "path": gathered["database_opens"].get("path"),
        **gathered["answers_a_real_query"],
    }
    payload["checks"] = checks

    mismatch = _health_mismatches(
        payload,
        expect_build,
        expect_schema,
        expect_pid,
        expect_engine,
        expect_launch,
    )
    if mismatch:
        payload["status"] = "not_the_engine_you_meant"
        payload["mismatch"] = mismatch
        return JSONResponse(payload, status_code=409)
    if not ready:
        payload["status"] = "not_ready"
        return JSONResponse(payload, status_code=503)
    payload["status"] = "ok"
    return JSONResponse(payload, status_code=200)


def _health_mismatches(
    payload: dict[str, Any],
    expect_build: str | None,
    expect_schema: int | None,
    expect_pid: int | None,
    expect_engine: str | None,
    expect_launch: str | None,
) -> list[dict[str, Any]]:
    """Every expectation the caller stated that this engine does not meet.

    All of them, not the first. A caller that asked four questions and got one
    answer has to ask again to find out whether the rest were fine, and a
    launcher deciding whether to restart wants the whole disagreement in one
    reading.

    `expect_build` matches on a PREFIX so a person can paste the first twelve
    characters of a fingerprint into a curl by hand without it being a trap.
    A prefix of a sha256 is still an enormous amount of evidence and the
    alternative - a full 64-character paste or nothing - is the kind of
    ergonomics that gets a check dropped from a script.
    """
    stated = (
        (
            "build",
            expect_build,
            payload["build"]["code_fingerprint"],
            lambda want, got: got.startswith(want),
        ),
        (
            "schema",
            expect_schema,
            payload["schema"]["build_knows"],
            lambda want, got: want == got,
        ),
        (
            "pid",
            expect_pid,
            payload["engine"]["pid"],
            lambda want, got: want == got,
        ),
        (
            "engine_id",
            expect_engine,
            payload["engine"]["engine_id"],
            lambda want, got: want == got,
        ),
        (
            "launch_nonce",
            expect_launch,
            payload["engine"]["launch_nonce"],
            lambda want, got: want == got,
        ),
    )
    return [
        {"field": field, "expected": want, "actual": got}
        for field, want, got, matches in stated
        if want is not None and not matches(want, got)
    ]


@app.post("/api/runs", status_code=201)
def create_run(payload: RunCreate) -> dict[str, Any]:
    return db.create_run(payload.name, json.dumps(payload.params, sort_keys=True))


@app.get("/api/runs")
def list_runs() -> list[dict[str, Any]]:
    return db.list_runs()


@app.post("/api/runs/{run_id}/metrics", status_code=201)
def add_metric(run_id: int, payload: MetricCreate) -> dict[str, Any]:
    metric = db.add_metric(run_id, payload.step, payload.name, payload.value)
    if metric is None:
        raise HTTPException(status_code=404, detail="run not found")
    return metric


@app.get("/api/runs/{run_id}/metrics")
def list_metrics(
    run_id: int, name: str | None = Query(default=None, min_length=1, max_length=80)
) -> list[dict[str, Any]]:
    return db.metrics_for(run_id, name)


@app.post("/api/runs/{run_id}/complete")
def complete_run(run_id: int) -> dict[str, Any]:
    run = db.complete_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return theme.page("ML Harness", DASHBOARD)


DASHBOARD = r"""<style>
.dashboard-sub{margin-top:calc(-1 * var(--s4));color:var(--ink-3)}
main.glass{margin-top:var(--s5)}
.controls{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--s3);margin-bottom:var(--s4)}
.controls label{color:var(--ink-3);font-family:var(--mono);font-size:.78rem}
.controls select,.controls input{display:block;width:100%;margin-top:var(--s1);padding:var(--s2) var(--s3);border:1px solid var(--edge);border-radius:var(--r-sm);background:var(--veil-2);color:var(--ink);font-family:var(--mono)}
.chart-scroll{overflow-x:auto;}
#chart{min-width:620px}
#chart svg{display:block;width:100%;height:auto;border:1px solid var(--edge);border-radius:var(--r);background:var(--veil-3)}
.series-line{fill:none;stroke-width:2}.line-a{stroke:var(--accent)}.line-b{stroke:#6fb5e8}
.endpoint-a{fill:var(--accent)}.endpoint-b{fill:#6fb5e8}
.legend{display:flex;flex-wrap:wrap;gap:var(--s4);margin-top:var(--s3);font-size:.78rem}
.legend-item{display:inline-flex;align-items:center;gap:var(--s2)}
.swatch{width:18px;height:2px;border-radius:var(--r-pill)}.swatch-a{background:var(--accent)}.swatch-b{background:#6fb5e8}
.step-range{margin-top:var(--s2);font-size:.78rem}
.empty{min-width:0;padding:var(--s6) 0;color:var(--ink-3);text-align:center}
.empty p{margin:0}.empty .empty-title{color:var(--ink-2)}.empty code{display:inline-block;margin-top:var(--s3);color:var(--ink)}
@media(max-width:720px){.controls{grid-template-columns:1fr}}
</style><h1>ML Harness</h1><p class="dashboard-sub">Compare the shape of learning across stored runs, locally.</p>
<main class="glass"><div class="controls"><label>Run A<select id="run-a" aria-label="Run A"></select></label><label>Run B<select id="run-b" aria-label="Run B"></select></label><label>Metric<input id="metric-name" aria-label="Metric name" value="loss"></label></div><h2 id="title">Run comparison</h2><div class="chart-scroll"><div id="chart" class="empty"><p class="empty-title">No runs recorded yet.</p><p class="dim">Seed two so there is something to compare.</p><code>python scripts/demo_train.py</code></div></div></main>
<script>
let runs=[],selectedA=null,selectedB=null;const emptyState=document.querySelector('#chart').innerHTML;const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
/* The engine token, bootstrapped once and then kept out of the page.
   The token is NOT rendered into this HTML. GET / needs no credential - a
   browser cannot be made to send a header at a typed URL - so anything
   embedded here would be readable by any local process that fetches this page,
   which would hand POST /jobs to exactly the attacker the token exists to stop.
   Instead `python scripts/open_dashboard.py` opens this page once with the
   token in the query string; we move it into sessionStorage and strip it from
   the URL immediately, so a later unauthenticated GET of / discloses nothing.
   Cost, stated rather than hidden: the token passes through the URL bar and
   the browser's history for that one navigation. */
const TOKEN=(()=>{try{const u=new URL(location.href);const t=u.searchParams.get('token');if(t){sessionStorage.setItem('mlh-token',t);u.searchParams.delete('token');history.replaceState({},'',u.pathname+(u.search||'')+u.hash)}return sessionStorage.getItem('mlh-token')||''}catch(e){return ''}})();
const api=path=>fetch(path,{headers:TOKEN?{'Authorization':'Bearer '+TOKEN}:{}});
function runById(id){return runs.find(r=>String(r.id)===String(id))}
function option(r){return `<option value="${r.id}">${esc(r.name)} (${esc(r.status)})</option>`}
function showLocked(){const el=document.querySelector('#chart');el.className='empty';el.innerHTML='<p class="empty-title">This dashboard needs the engine token.</p><p class="dim">The API is authenticated so that no other page or process can reach it.</p><code>python scripts/open_dashboard.py</code>'}
async function loadRuns(){const resp=await api('/api/runs');if(resp.status===401){showLocked();return}const next=await resp.json();runs=next;const a=document.querySelector('#run-a'),b=document.querySelector('#run-b');const keepA=selectedA??a.value,keepB=selectedB??b.value;const options=runs.map(option).join('');a.innerHTML=options;b.innerHTML=options;if(runs.length){a.value=runById(keepA)?keepA:runs[0].id;b.value=runById(keepB)?keepB:(runs[1]??runs[0]).id;selectedA=a.value;selectedB=b.value}else{selectedA=selectedB=null}await compare()}
async function compare(){const metric=document.querySelector('#metric-name').value.trim();if(!selectedA||!selectedB||!metric){if(runs.length){showMessage('Enter a metric name.')}else{showEmptyState()}return}const query=encodeURIComponent(metric);const [a,b]=await Promise.all([api(`/api/runs/${selectedA}/metrics?name=${query}`).then(r=>r.json()),api(`/api/runs/${selectedB}/metrics?name=${query}`).then(r=>r.json())]);const runA=runById(selectedA),runB=runById(selectedB);document.querySelector('#title').textContent=`${runA.name} vs ${runB.name}: ${metric}`;if(!a.length){showMessage(`No ${metric} data for ${runA.name}.`);return}if(!b.length){showMessage(`No ${metric} data for ${runB.name}.`);return}draw(a,b,runA.name,runB.name,metric)}
function showEmptyState(){const el=document.querySelector('#chart');el.className='empty';el.innerHTML=emptyState}
function showMessage(message){const el=document.querySelector('#chart');el.className='empty';el.textContent=message}
function draw(a,b,nameA,nameB,metric){const el=document.querySelector('#chart');el.className='';const all=[...a,...b],steps=all.map(p=>Number(p.step)),vals=all.map(p=>Number(p.value)),minStep=Math.min(...steps),maxStep=Math.max(...steps),stepSpan=maxStep-minStep||1,min=Math.min(...vals),max=Math.max(...vals),span=max-min||1;const coords=pts=>pts.map(p=>[50+(Number(p.step)-minStep)/stepSpan*610,290-(Number(p.value)-min)/span*235]),points=cs=>cs.map(p=>`${p[0]},${p[1]}`).join(' '),ca=coords(a),cb=coords(b),lastA=ca[ca.length-1],lastB=cb[cb.length-1],areaA=`M ${ca[0][0]},290 L ${points(ca)} L ${lastA[0]},290 Z`,grid=[45,106.25,167.5,228.75,290].map(y=>`<line x1="50" y1="${y}" x2="660" y2="${y}" stroke="rgba(255,255,255,.06)"/>`).join('');el.innerHTML=`<svg viewBox="0 0 700 320" role="img" aria-label="${esc(metric)} comparison chart"><path d="${areaA}" fill="rgba(139,124,246,.10)"/>${grid}<polyline class="series-line line-a" points="${points(ca)}"/><polyline class="series-line line-b" points="${points(cb)}"/><circle class="endpoint-a" cx="${lastA[0]}" cy="${lastA[1]}" r="3.5"/><circle class="endpoint-b" cx="${lastB[0]}" cy="${lastB[1]}" r="3.5"/></svg><div class="legend mono dim"><span class="legend-item"><span class="swatch swatch-a"></span>${esc(nameA)} · ${Number(a[a.length-1].value).toFixed(3)}</span><span class="legend-item"><span class="swatch swatch-b"></span>${esc(nameB)} · ${Number(b[b.length-1].value).toFixed(3)}</span></div><div class="step-range mono dim">step ${minStep} -&gt; ${maxStep}</div>`}
document.querySelector('#run-a').addEventListener('change',e=>{selectedA=e.target.value;compare()});document.querySelector('#run-b').addEventListener('change',e=>{selectedB=e.target.value;compare()});document.querySelector('#metric-name').addEventListener('change',compare);
loadRuns();setInterval(loadRuns,2000);
</script>"""


@app.post("/hardware", status_code=201)
async def create_hardware(payload: HardwareCreate) -> dict[str, Any]:
    return db.create_hardware_profile(
        gpu_name=payload.gpu_name,
        vram_gb=payload.vram_gb,
        ram_gb=payload.ram_gb,
        os=payload.os,
        disk_free_gb=payload.disk_free_gb,
    )


@app.get("/hardware")
async def latest_hardware() -> dict[str, Any]:
    row = db.get_latest_hardware_profile()
    if row is None:
        raise HTTPException(status_code=404, detail="no hardware profile recorded")
    return row


@app.get("/intake/questions")
def intake_questions() -> list[dict[str, Any]]:
    return [
        {"id": 1, "field": "goal", "prompt": "What is your goal?", "type": "text", "options": ["Classifier", "Fine-tune", "RL", "Recommender"]},
        {"id": 2, "field": "dataset_size", "prompt": "What is the dataset size?", "type": "text", "options": ["Small", "Medium", "Large"]},
        {"id": 3, "field": "data_kind", "prompt": "What data kind?", "type": "text", "options": ["Text", "Image", "Tabular"]}
    ]


@app.post("/intake", status_code=201)
def create_intake(payload: IntakeCreate) -> dict[str, Any]:
    return db.create_intake(payload.session_id, payload.answers)


@app.get("/intake/{session_id}", status_code=200)
def get_intake(session_id: str) -> dict[str, Any]:
    intake = db.get_intake(session_id)
    if not intake:
        raise HTTPException(status_code=404, detail="Intake session not found")
    return intake


@app.get("/plan/{session_id}", response_class=PlainTextResponse)
def get_plan(session_id: str) -> PlainTextResponse:
    row = db.get_intake(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="Intake session not found")
    
    rec, _estimate, v = plan_inputs(row["answers"])

    markdown = plan.render_plan(row["answers"], rec, v)
    return PlainTextResponse(markdown)


@app.get("/plan/{session_id}/download", response_class=PlainTextResponse)
def download_plan(session_id: str) -> PlainTextResponse:
    row = db.get_intake(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="Intake session not found")
    
    rec, _estimate, v = plan_inputs(row["answers"])

    headers = {"Content-Disposition": "attachment; filename=plan.md"}
    markdown = plan.render_plan(row["answers"], rec, v)
    
    return PlainTextResponse(markdown, headers=headers)


@app.post("/jobs", status_code=201)
def enqueue_job(payload: JobCreate) -> dict[str, Any]:
    spec = jobspec.JobSpec(
        recipe=payload.recipe, kind=payload.kind, config=payload.config
    )
    # Validated at the door. A job that cannot run is refused now, with the
    # reason, rather than queued and discovered by the runner later - and the
    # refusal is what keeps an unknown recipe name from ever being stored.
    try:
        jobspec.validate(spec)
    except jobspec.JobRejected as rejected:
        raise HTTPException(status_code=422, detail=str(rejected))
    return db.create_job(payload.intake_id, spec)


@app.get("/api/recipes")
def list_recipes() -> dict[str, Any]:
    """The closed set of things a job may be. The allowlist, readable."""
    return {"recipes": jobspec.available_recipes(), "kinds": list(jobspec.KINDS)}


@app.get("/jobs/{job_id}/log", response_class=PlainTextResponse)
def job_log(job_id: int, tail: int = 200) -> PlainTextResponse:
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    
    # A queued job has the log_path KEY with a None VALUE, so the original
    # `"log_path" not in job` check never fired and Path(None) raised
    # TypeError. Asking for the log of a job that has not run yet is an
    # ordinary thing to do; it returns empty, not a 500.
    if not job["log_path"] or not Path(job["log_path"]).exists():
        return PlainTextResponse("")
    
    lines = Path(job["log_path"]).read_text(encoding="utf-8").splitlines()
    return PlainTextResponse("\n".join(lines[-tail:]))


# ---------------------------------------------------------------------------
# `GET /ui/intake` AND `POST /ui/intake` WERE HERE, and are gone deliberately.
# `docs/THE_PLAN.md` V.3 A9. The form was the last server-rendered thing that
# CHANGED state, and it was the only reason `security.BROWSER_FORM_ROUTES` had
# a member: a browser form cannot set an Authorization header, so that one POST
# was let through the bearer-token boundary and defended by SameSite instead.
# A real defence, and a DIFFERENT one from the rest of the product's, which is
# why it was named in a frozenset rather than assumed - and why removing the
# last thing that needed it is worth more than the twenty lines it cost.
#
# WHAT DID NOT GO: `/ui/plan/{session_id}` below, which is not orphaned - an
# intake is made by `POST /api/intake`, the JSON surface the React app and any
# script already use, and this page renders whatever session id it is handed.
# `/`, `/ui/jobs` and `/ui/report/{id}` never took a form and are untouched.
#
# It is one `git revert` away if the form is wanted back; nothing was migrated
# and no data was touched.

@app.get("/ui/plan/{session_id}", response_class=HTMLResponse)
def plan_page(session_id: str) -> HTMLResponse:
    row = db.get_intake(session_id)
    if None == row:
        raise HTTPException(status_code=404, detail="session not found")

    rec, estimate, v = plan_inputs(row["answers"])
    available_gb = v["vram_gb"]
    weights_gb = estimate["weights_gb"]
    kv_gb = estimate["kv_gb"]

    plan_markdown = plan.render_plan(row["answers"], rec, v)
    plan_lines = plan_markdown.splitlines()
    if (
        len(plan_lines) >= 3
        and plan_lines[0] == "# Training plan"
        and plan_lines[1]
        and plan_lines[2].startswith("verdict:")
    ):
        plan_markdown = "\n".join([plan_lines[0], *plan_lines[3:]])

    escaped_markdown = html.escape(plan_markdown)
    # nl2br: render_plan separates Goal / Method / Quantization with single
    # newlines, and markdown collapses those into one paragraph, so the browser
    # showed "Goal: ... Method: QLoRA Quantization: Q4" as one run-on line.
    # Only a screenshot caught it - the DOM assertions all passed.
    rendered_markdown = markdown.markdown(escaped_markdown, extensions=["nl2br"])
    # The diagram names the real model. An earlier version substituted
    # "recommended model" here only to satisfy a test that counted occurrences
    # of the model name - a guard that cost the reader information.
    escaped_mermaid = html.escape(diagram.render_diagram(rec, v))

    verdict_text = str(v["verdict"])
    verdict_class = {
        "FITS": "fits",
        "SPILLS": "spills",
        "WONT_FIT": "wont",
        "UNKNOWN": "unknown",
    }.get(verdict_text, "unknown")

    # Every one of these can legitimately be absent now, and an absent number
    # renders as an em dash rather than as a confident figure. The page used to
    # print 8.00 / 4.19 / 3.50 unconditionally because those were literals.
    def gb(value: float | None) -> str:
        return "&mdash;" if value is None else f"{value:.2f} GB"

    headroom_gb = v["headroom_gb"]
    if headroom_gb is not None:
        headroom_gb = max(float(headroom_gb), 0.0)

    def pct(value: float | None) -> float:
        if value is None or not available_gb:
            return 0.0
        return max(0.0, min(100.0, float(value) / float(available_gb) * 100))

    basis = (
        f'This plan is computed for {html.escape(str(rec["data_kind"]))} data '
        f'(data kind {html.escape(str(rec["data_kind_provenance"]))}). '
    )
    if verdict_text == "UNKNOWN":
        basis += html.escape(str(v.get("reason", "")))
    else:
        basis += (
            f'VRAM figure {html.escape(str(v["vram_provenance"]))}, budgeted at '
            f'{PLAN_CONTEXT_TOKENS} tokens of context.'
        )

    body = (
        f'<section class="glass plan-summary">'
        f'<p class="mono summary">{html.escape(str(rec["model"]))}<br>'
        f'{gb(v["needed_gb"])} needed - '
        f'{gb(v["vram_gb"])} available</p>'
        f'<span class="vpill {verdict_class}">{html.escape(verdict_text)}</span>'
        f'<div class="budget" role="img" aria-label="VRAM budget">'
        f'<span class="seg weights" style="width:{pct(weights_gb):.2f}%"></span>'
        f'<span class="seg activations" style="width:{pct(kv_gb):.2f}%"></span>'
        f'<span class="seg headroom" style="width:{pct(headroom_gb):.2f}%"></span>'
        f'</div><div class="budget-scale mono"><span>0 GB</span>'
        f'<span>headroom {gb(headroom_gb)}</span><span>{gb(available_gb)}</span></div>'
        f'<p class="dim basis">{basis}</p>'
        f'</section>{rendered_markdown}'
        f"<h2>Mermaid diagram</h2><pre><code>{escaped_mermaid}</code></pre>"
    )

    return HTMLResponse(theme.page("Training plan", body))


@app.get("/ui/jobs", response_class=HTMLResponse)
def jobs_page() -> HTMLResponse:
    jobs = db.list_jobs()
    rows = [f'<tr><td>{j["id"]}</td><td>{j["status"]}</td>'
            f'<td><a href="/jobs/{j["id"]}/log">log</a></td></tr>' for j in jobs]
    html = "<html><body><h1>Jobs</h1><table>" + "".join(rows) + "</table></body></html>"
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# The Conductor surface: threads, the event stream, providers, and the tools
# that are also controls.
#
# Everything here sits under `/api/`, which the security middleware at the top
# of this file already gates on the bearer token - read and write alike. There
# is deliberately no second `Depends(require_token)`: a dependency protects the
# routes somebody remembered to decorate, and the middleware cannot be
# forgotten by the next route. That is the property worth having, and it is why
# the boundary was written as middleware in the first place.


class ProjectCreate(BaseModel):
    """A project. `portal` is the only field the enterprise product changes.

    It is a `Literal` rather than a `str` so an unknown value is a 422 from the
    request model instead of a row in the database that belongs to neither
    product. `db.create_project` checks it a second time, because the database
    has callers that are not HTTP.
    """

    name: str = Field(min_length=1, max_length=120)
    root_path: str | None = Field(default=None, max_length=1000)
    portal: Literal["consumer", "enterprise"] = "consumer"


class ProjectRoot(BaseModel):
    """Where this project's files are. The person's directory, not ours.

    `max_length` matches `ProjectCreate.root_path` rather than being chosen
    again here: two limits on one column is two answers to "how long may a path
    be", and the shorter one wins by accident on whichever route somebody used.
    """

    root_path: str = Field(min_length=1, max_length=1000)


class ProjectRename(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ThreadCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    project_id: int | None = None


class ThreadRename(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ThreadMove(BaseModel):
    project_id: int


class MessageCreate(BaseModel):
    content: str = Field(min_length=1)


class ProviderCreate(BaseModel):
    """A model connection. `api_key` is accepted and never stored in SQLite.

    It goes straight to the OS keychain and is not echoed back in the response.
    See `app/providers/secrets.py` and the test that reads the database file as
    bytes and asserts the key is not in them.
    """

    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=200)
    adapter: str = Field(default="openai-compatible")
    api_key: str | None = None


class ProviderUpdate(BaseModel):
    """An edit to a saved connection. Every field is optional.

    ABSENT AND NULL ARE DIFFERENT for `api_key`, and the difference is the
    reason this model is not just `ProviderCreate` with optional fields. A
    settings page that redraws a connection has no key to redraw - the engine
    never gives one back - so a PATCH that carried the key as an ordinary field
    would wipe it every time somebody renamed a row. So:

      absent   leave whatever the keychain holds
      ""       delete the key from the keychain
      a string replace it

    `model_fields_set` is what tells the three apart, and it is the only place
    in this file that distinction is load-bearing.
    """

    name: str | None = Field(default=None, min_length=1, max_length=120)
    base_url: str | None = Field(default=None, min_length=1, max_length=500)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    adapter: str | None = None
    api_key: str | None = None
    #: One of `store.EFFORTS`. How hard the model thinks on this connection;
    #: the composer's effort chip writes it, the adapters read it.
    effort: str | None = None


class TurnRequest(BaseModel):
    """What a turn is started with.

    `portal` IS STILL ACCEPTED AND NO LONGER REACHES THE PROMPT. The
    consumer/enterprise split was dropped on 2026-08-19 (`docs/VISION.md`: *"a
    toggle that changes almost nothing is worse than none"*) and the two
    instruction fragments it selected are deleted. The field stays on the wire
    for one turn of the API's life so an existing client's POST does not become
    a 422 the day the fragments go; retiring it, and the `projects.portal`
    column with it, is a migration and belongs with one.
    """

    provider_id: int | None = None
    portal: str = Field(default="consumer")
    sensitive: bool = False
    #: CS9 — person checked "Agent may edit goal/todo this turn".
    invite_goal_edit: bool = False


class ToolRun(BaseModel):
    """Running a tool as a control rather than as a model tool call.

    There is no `actor` field and there must never be one. This route IS the
    user's door - a person pressed a button in their own application - and the
    route says so itself when it calls the registry. A field here would let a
    request claim to be the user, and the whole point of the distinction is that
    it is a property of the door rather than of the message.

    `thread_id` is which conversation the facts belong to. Facts measured
    without one are machine scope, which is right for hardware and wrong for
    anything about a project, so the interface sends it.

    "SO THE INTERFACE SENDS IT" WAS THE WHOLE ENFORCEMENT AND IT WAS NOT ONE.
    Every fact now declares a `scope:` in `docs/diagnosis_engine.yaml`,
    `evidence.record` refuses a thread-scoped row that names no thread, and
    `run_tool_ep` refuses the call before it runs when the tool could write one.
    The field stays optional because `inspect_hardware` genuinely does not need
    it; what has changed is that the route decides that per tool instead of
    trusting whoever built the request.
    """

    arguments: dict[str, Any] = Field(default_factory=dict)
    approved: bool = False
    thread_id: int | None = None


def _provider_public(row: dict[str, Any]) -> dict[str, Any]:
    """A provider row as the UI sees it. Never carries the key itself."""
    out = dict(row)
    out["has_key"] = provider_secrets.has_key(str(row["id"]))
    return out


# ---------------------------------------------------------------------------
# Projects. The rail's top level, and the reason it can be a tree rather than a
# flat list of every thread ever opened.
#
# Every route here is under `/api`, so the security middleware at the top of
# this file already gates it, and every one that changes something appends to
# the event log the same way `post_message_ep` does - one pattern, not two. A
# rail that redraws itself when a project is renamed in another tab is the
# whole reason the spine exists; a mutation that does not appear on it is
# invisible to every other window.


@app.get("/api/projects")
def list_projects_ep(include_archived: bool = False) -> list[dict[str, Any]]:
    return db.list_projects(include_archived=include_archived)


@app.post("/api/projects", status_code=201)
def create_project_ep(payload: ProjectCreate) -> dict[str, Any]:
    # Same shape rule as POST /root: a relative folder would follow the
    # engine's cwd around. Existence is still not checked here.
    if payload.root_path and not Path(payload.root_path).is_absolute():
        raise HTTPException(
            status_code=400,
            detail=(
                f"{payload.root_path!r} is a relative path. A project's folder "
                "is an absolute path on this machine - send that."
            ),
        )
    project = db.create_project(
        payload.name, payload.root_path, payload.portal
    )
    events.append(
        "project.created",
        {"id": project["id"], "name": project["name"], "portal": project["portal"]},
        project_id=project["id"],
    )
    return project


@app.post("/api/projects/{project_id}/duplicate", status_code=201)
def duplicate_project_ep(project_id: int) -> dict[str, Any]:
    """A new project with the same root, and nothing else.

    The owner asked for "copying projects" and this is the honest reading of
    what a copy IS here: a project is a name plus a root_path plus the threads
    that happened in it. The root is shared on purpose - both projects point at
    the same files, which is what a person duplicating a workspace wants. The
    THREADS are deliberately not copied: a thread is a record of measurements
    that happened once, and a copied MEASURED row would be a claim the copy
    never earned - the same reason `synthesize_rows` refuses to launder its
    output into an eval set. The copy starts with the facts of its own life.
    """
    source = db.get_project(project_id)
    if source is None:
        raise HTTPException(status_code=404, detail="project not found")
    project = db.create_project(
        f"{source['name']} copy", source.get("root_path"), source.get("portal")
    )
    events.append(
        "project.duplicated",
        {"id": project["id"], "from": project_id, "name": project["name"]},
        project_id=project["id"],
    )
    return project


@app.post("/api/projects/{project_id}/rename")
def rename_project_ep(project_id: int, payload: ProjectRename) -> dict[str, Any]:
    project = db.rename_project(project_id, payload.name)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    events.append(
        "project.renamed",
        {"id": project["id"], "name": project["name"]},
        project_id=project["id"],
    )
    return project


@app.post("/api/projects/{project_id}/root")
def set_project_root_ep(project_id: int, payload: ProjectRoot) -> dict[str, Any]:
    """Point a project at a directory, after the project exists.

    A POST rather than a PATCH because every other project mutation here is one
    (`/rename`, `/archive`) and a single-verb surface is one less thing for a
    client to get right; `app/security.py` treats all four the same way, so
    nothing about the token boundary turns on it.

    IT DOES NOT CHECK THE DIRECTORY EXISTS, deliberately and consistently with
    `POST /api/projects`, which stores whatever it is given. The check belongs
    where the path is USED - the standing-constraints tools already refuse
    `root_is_not_a_directory` with the path in the reply - and checking here as
    well would mean a root that was valid on Tuesday cannot be re-set on
    Wednesday from a machine where the drive is not mounted.
    """
    # DOES THIS PROJECT EXIST, BEFORE ANYTHING IS SAID ABOUT THE PATH. The
    # shape check below shipped above this line and answered 400 for a
    # project that was not there, so "no such project" arrived wearing
    # "your path is wrong" - and CI caught it on both operating systems
    # while this machine, whose fixtures all use real projects, never did.
    # A refusal has to name the thing that is actually wrong.
    if db.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")

    # A RELATIVE ROOT IS A ROOT THAT MOVES. `.` or `data` would bind the Files
    # pane, report/save and path rehoming to wherever the ENGINE happens to
    # be running from, which is never what a person meant by their folder.
    # Existence is deliberately not checked (see above); shape is.
    if not Path(payload.root_path).is_absolute():
        raise HTTPException(
            status_code=400,
            detail=(
                f"{payload.root_path!r} is a relative path. A project's folder "
                "is an absolute path on this machine, like C:\\Users\\you\\"
                "project - send that."
            ),
        )
    project = db.set_project_root(project_id, payload.root_path)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    events.append(
        "project.root_set",
        {"id": project["id"], "root_path": project["root_path"]},
        project_id=project["id"],
    )
    return project


@app.delete("/api/projects/{project_id}")
def delete_project_ep(project_id: int) -> dict[str, Any]:
    """Delete a project with its threads and memory. 409 when it is the last live one.

    Nothing on disk is touched: the project's folder is the person's and the
    engine never copied it in. One `project.deleted` event is written after,
    unscoped - the project it would name is gone - with the name and counts.
    """
    try:
        outcome = db.delete_project(project_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if outcome is None:
        raise HTTPException(status_code=404, detail="project not found")
    project = outcome["project"]
    events.append(
        "project.deleted",
        {"id": project["id"], "name": project["name"], "removed": outcome["removed"]},
    )
    return {"ok": True, "deleted": project["id"], "removed": outcome["removed"]}


@app.post("/api/projects/{project_id}/archive")
def archive_project_ep(project_id: int) -> dict[str, Any]:
    """Archive a project. 409 when it is the last live one.

    A refusal with a reason, not a silent success: archiving the last project
    would leave the rail empty and `db.default_project()` would mint a fresh
    `Default` behind it, so the next thread would land somewhere the user
    cannot see the old ones. `db.archive_project` raises and this turns that
    into the same 409 the Conductor uses for "you asked for something this
    state does not allow".
    """
    try:
        project = db.archive_project(project_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    events.append(
        "project.archived",
        {"id": project["id"], "archived_at": project["archived_at"]},
        project_id=project["id"],
    )
    return project


# ══ THE WORKSPACE'S OWN FILES ═══════════════════════════════════════════════
#
# The owner's direction, 2026-08-31: "If we ask people to pull up a file, we
# can actually open it on the sidebar somewhere, like where machine is...
# they can actually see it, let's say, a markdown file or a JSON file, and
# they can edit it as well. That's very important."
#
# Three routes, one wall: every path is RELATIVE and is resolved inside the
# project's own `root_path`, verified after resolution, so `..`, drive
# letters and absolute paths cannot reach a byte outside the folder the
# person attached. A project with no folder gets a 400 that names the fix,
# never a listing of somewhere it did not choose.

#: Folders nobody means when they ask what is in their project. The same junk
#: a carve skips: tool caches and checkouts-within-the-checkout, not data.
_SKIPPED_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".mypy_cache", ".ruff_cache", "target", "dist",
}

#: One file's ceiling for read and write, in bytes. A pane is a reading
#: surface; past this it is a download, and the sentence says so.
_FILE_BYTE_CAP = 512_000

#: The listing's ceiling. Past it the answer says how many were left unlisted
#: rather than pretending the folder ends where the list does.
_LISTING_CAP = 500


def _project_root_dir(project_id: int) -> tuple[dict[str, Any], Path]:
    project = db.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    root = project.get("root_path")
    if not root:
        raise HTTPException(
            status_code=400,
            detail=(
                "This project has no folder attached, so there are no files "
                "to show. Attach one — the chip under the chat box does it — "
                "then look again."
            ),
        )
    root_dir = Path(root)
    if not root_dir.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"The project's folder does not exist on disk: {root}",
        )
    return project, root_dir


def _inside_project_root(root_dir: Path, rel: str) -> Path:
    """The one wall. Resolve, then verify; refusal names what was refused."""
    try:
        candidate = Path(rel)
        # A NUL byte is not a path and used to escape as a 500. Refuse it in
        # the same sentence a traversal gets.
        bad = candidate.is_absolute() or rel.strip() == "" or "\x00" in rel
        resolved = None if bad else (root_dir / candidate).resolve()
    except (ValueError, OSError):
        bad, resolved = True, None
    if bad or resolved is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Paths here are relative to the project's folder. Send the "
                "path as the listing printed it."
            ),
        )
    if not resolved.is_relative_to(root_dir.resolve()):
        raise HTTPException(
            status_code=400,
            detail=(
                f"{rel} resolves outside the project's folder, and this "
                "surface reads and writes nothing outside it."
            ),
        )
    return resolved


def _file_stamp(target: Path) -> dict[str, Any]:
    stat = target.stat()
    return {"size": stat.st_size, "modified": stat.st_mtime}


@app.get("/api/projects/{project_id}/files")
def list_project_files_ep(project_id: int) -> dict[str, Any]:
    """Every file under the project's folder, relative paths, capped and dated."""
    import os as _os
    import time as _time

    project, root_dir = _project_root_dir(project_id)
    inside = root_dir.resolve()
    files: list[dict[str, Any]] = []
    left_unlisted = 0
    outside_root = 0
    unreadable = 0
    for dirpath, dirnames, filenames in _os.walk(root_dir):
        # A junction or symlinked directory inside the folder can point
        # anywhere on the disk. os.walk does not follow symlinks, but Windows
        # junctions walk like plain directories — so every directory is
        # resolved and one that lands outside the root is not entered. The
        # read route already refused those files; the listing must not name
        # them either.
        kept = []
        for d in sorted(dirnames):
            if d in _SKIPPED_DIRS:
                continue
            try:
                if (Path(dirpath) / d).resolve().is_relative_to(inside):
                    kept.append(d)
                else:
                    outside_root += 1
            except OSError:
                unreadable += 1
        dirnames[:] = kept
        for name in sorted(filenames):
            full = Path(dirpath) / name
            try:
                if not full.resolve().is_relative_to(inside):
                    outside_root += 1
                    continue
                stamp = _file_stamp(full)
            except OSError:
                unreadable += 1
                continue
            if len(files) >= _LISTING_CAP:
                left_unlisted += 1
                continue
            files.append(
                {"path": full.relative_to(root_dir).as_posix(), **stamp}
            )
    return {
        "project": {"id": project["id"], "name": project["name"]},
        "root": str(root_dir),
        "files": files,
        "count": len(files),
        # Honest about the cap: zero means the list IS the folder. The other
        # two counts say what the walk saw and would not, or could not, list.
        "left_unlisted": left_unlisted,
        "skipped_outside_root": outside_root,
        "unreadable": unreadable,
        "read_at": _time.time(),
        "source": "walked on this machine just now, skipping tool caches",
    }


@app.get("/api/projects/{project_id}/file")
def read_project_file_ep(project_id: int, path: str) -> dict[str, Any]:
    """One file's text, with the modification stamp an edit must echo back."""
    import time as _time

    _, root_dir = _project_root_dir(project_id)
    target = _inside_project_root(root_dir, path)
    if not target.is_file():
        raise HTTPException(
            status_code=404, detail=f"No file at {path} in the project's folder."
        )
    stamp = _file_stamp(target)
    if stamp["size"] > _FILE_BYTE_CAP:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{path} is {stamp['size']:,} bytes; this pane reads up to "
                f"{_FILE_BYTE_CAP:,}. Open it in an editor instead."
            ),
        )
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise HTTPException(
            status_code=400,
            detail=f"{path} is not UTF-8 text, so there is nothing to show as text.",
        ) from error
    except OSError as error:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{path} could not be read: {error.strerror or error}. "
                "Nothing was shown."
            ),
        ) from error
    return {
        "path": path,
        "content": content,
        **stamp,
        "read_at": _time.time(),
    }


class ProjectFileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=1000)
    content: str = Field(max_length=_FILE_BYTE_CAP)
    #: The `modified` the editor READ. Refused with a 409 when the file has
    #: changed since — a stale edit must never silently clobber a newer one.
    expect_modified: float | None = None


@app.put("/api/projects/{project_id}/file")
def write_project_file_ep(
    project_id: int, payload: ProjectFileWrite
) -> dict[str, Any]:
    """Save an edit to an existing file inside the project's folder.

    EDIT, NOT CREATE: the pane opens files the listing showed, so a path that
    does not exist is a typo or an escape attempt, and both get a sentence
    rather than a new file in a folder the person has to notice later.
    """
    _, root_dir = _project_root_dir(project_id)
    target = _inside_project_root(root_dir, payload.path)
    if not target.is_file():
        raise HTTPException(
            status_code=404,
            detail=(
                f"No file at {payload.path} in the project's folder. This "
                "surface edits files that exist; it does not create them."
            ),
        )
    current = _file_stamp(target)
    if (
        payload.expect_modified is not None
        and abs(current["modified"] - payload.expect_modified) > 1e-6
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                f"{payload.path} changed on disk after you opened it. "
                "Nothing was written — reopen it, then edit the newer copy."
            ),
        )
    # THE FILE'S OWN LINE ENDINGS SURVIVE THE EDIT. The read route hands the
    # editor universal-newline text and the browser sends '\n'; writing that
    # back with write_text() rewrote every CRLF file as LF on its first save
    # - a silent change to every line the person did not touch, which git
    # then shows as a whole-file diff. Review found it. The file's dominant
    # ending is read back off its bytes and re-applied.
    try:
        raw = target.read_bytes()
        crlf = raw.count(b"\r\n")
        lf_only = raw.count(b"\n") - crlf
        body = payload.content.replace("\r\n", "\n")
        if crlf > lf_only:
            body = body.replace("\n", "\r\n")
        with open(target, "w", encoding="utf-8", newline="") as handle:
            handle.write(body)
    except OSError as error:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{payload.path} could not be written: {error.strerror or error}. "
                "Nothing was changed."
            ),
        ) from error
    return {"ok": True, "path": payload.path, **_file_stamp(target)}


@app.get("/api/threads")
def list_threads_ep(project_id: int | None = None) -> list[dict[str, Any]]:
    return events.list_threads(project_id=project_id)


@app.post("/api/threads", status_code=201)
def create_thread_ep(payload: ThreadCreate) -> dict[str, Any]:
    if payload.project_id is not None and db.get_project(payload.project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    #: THE DOOR A PERSON OPENS A CONVERSATION THROUGH, so this is where the
    #: product's answer to "plan or build" is given. `events.create_thread`
    #: itself still opens threads in `build`; see `app/modes.py`.
    #: AND IT ADOPTS NOTHING. Max, 2026-09-19, of thread 81: *"i said hello in
    #: a brand new chat with nothing and its running for 2 minutes loading
    #: things i didnt need like a plan into a new chat right away, before me
    #: telling it literally anything."* He is right, and the event log agrees -
    #: thread 81 has one message, "hi", and a `thread.plan_adopted` beside it.
    #: A plan carried into a greeting is eighteen open steps the person did not
    #: ask for, and the brief then tells the model to work them. The plan is
    #: still on disk; `compile_the_plan` brings it in when there is work.
    thread = events.create_thread(
        payload.title,
        payload.project_id,
        mode=modes.WHEN_A_PERSON_OPENS_A_CONVERSATION,
        adopt_project_plan=False,
    )
    events.append(
        "thread.created",
        {"id": thread["id"], "title": thread["title"]},
        project_id=thread["project_id"],
        thread_id=thread["id"],
    )
    return thread


@app.post("/api/threads/{thread_id}/rename")
def rename_thread_ep(thread_id: int, payload: ThreadRename) -> dict[str, Any]:
    thread = events.rename_thread(thread_id, payload.title)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    events.append(
        "thread.renamed",
        {"id": thread["id"], "title": thread["title"]},
        project_id=thread["project_id"],
        thread_id=thread["id"],
    )
    return thread


class ThreadGoal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    #: Empty clears the goal — "no goal" is a real state, never faked as "".
    goal: str = Field(max_length=8000)


class ThreadJourney(BaseModel):
    journey: str = Field(min_length=1, max_length=120)


@app.post("/api/threads/{thread_id}/journey")
def set_thread_journey_ep(thread_id: int, payload: ThreadJourney) -> dict[str, Any]:
    """The person CHOOSES a route, rather than typing prose at a keyword matcher.

    Starting a journey was reachable one way: write a sentence and hope
    `match_journey` agreed with you. The overview has listed the five routes
    all along and none of them was choosable, so a person who could see the
    one they wanted still had to guess a sentence that would land on it.

    THE GOAL IS NOT TOUCHED, and `events.set_thread_goal`'s own docstring is
    the reason: the goal is "the person's own words, verbatim... never a
    model's paraphrase". A menu pick is not their words either. So the thread's
    existing goal is read and written back unchanged beside the new journey -
    empty if it was empty, theirs if they had written one.

    A name the playbook does not carry is REFUSED rather than stored. A thread
    holding a journey nothing can look up renders an empty route with no way
    back out of it.
    """
    from app.tools import knowledge

    wanted = payload.journey.strip()
    available = knowledge.journey_names()
    if wanted not in available:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{wanted!r} is not a route in the playbook. The routes that "
                f"exist: {', '.join(available)}."
            ),
        )
    thread = events.get_thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    updated = events.set_thread_goal(thread_id, thread.get("goal"), wanted)
    if updated is None:
        raise HTTPException(status_code=404, detail="thread not found")
    return updated


@app.post("/api/threads/{thread_id}/goal")
def set_thread_goal_ep(thread_id: int, payload: ThreadGoal) -> dict[str, Any]:
    """The person corrects (or clears) what this thread is for.

    THIS IS THE PERSON'S DOOR, like `POST /api/tools/{name}`: whatever
    arrives here is stored verbatim as their own words. The conductor's
    auto-adoption (`conductor._adopt_goal`) only ever fills an EMPTY goal, so
    a correction made here stands until the person changes it again. The
    journey beside it is re-matched from the new words — pure keyword code,
    carrying only the authority a keyword match has.
    """
    from app.tools import knowledge

    text = payload.goal.strip()
    journey = knowledge.match_journey(text) if text else None
    # An emptied goal is stored as "" — CLEARED BY THE PERSON — and not as
    # NULL, which means "nobody said anything yet" and would invite the
    # conductor to adopt the first message all over again on the next turn.
    thread = events.set_thread_goal(thread_id, text, journey)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    events.append(
        "thread.goal_set",
        {
            "goal": thread["goal"],
            "journey": thread["goal_journey"],
            "source": "the person, through their own door",
        },
        project_id=thread["project_id"],
        thread_id=thread["id"],
    )
    return thread


class ThreadAutonomy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    on: bool


class ThreadPermission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str


class ThreadMode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str


class ThreadPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: str | None = None


class ThreadTodo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    todo: str | None = None


class ThreadChecklistSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str


class MemoryText(BaseModel):
    """One memory block, wholesale, as the pane edits it - `§`-delimited."""

    model_config = ConfigDict(extra="forbid")
    target: str
    project_id: int | None = None
    text: str = ""


@app.get("/api/memory")
def get_memory_ep(project_id: int | None = None) -> dict[str, Any]:
    """Both memory blocks - this project's notes and the person's profile -
    with Hermes' limits, for the Memory pane. See `app/memory.py`."""
    return memory.summary(project_id)


@app.put("/api/memory")
def put_memory_ep(payload: MemoryText) -> dict[str, Any]:
    """The person's edit of one block. Refused whole - with the entry and the
    reason - when an entry carries a number with no origin word; the pane
    keeps their text either way."""
    if payload.target not in memory.TARGETS:
        raise HTTPException(status_code=400, detail=f"target is one of {memory.TARGETS}")
    if payload.target == "project" and payload.project_id is None:
        raise HTTPException(status_code=400, detail="a project memory needs a project_id")
    result = memory.set_text(payload.target, payload.text, payload.project_id)
    if result.get("ok"):
        events.append(
            "memory.edited",
            {"target": payload.target, "project_id": payload.project_id, "count": result["count"]},
            project_id=payload.project_id,
        )
    return result


@app.post("/api/threads/{thread_id}/run")
def start_run_ep(thread_id: int) -> dict[str, Any]:
    """Work the plan down, turn after turn, until it cannot go further.

    THE PERSON'S DOOR, like the mode. A run takes ordinary turns - the same
    prompt, the same tools, the same walls - and its whole contribution is
    that there is another one until every step is ticked or parked. It ends
    on an approval, a repeated connection failure, the turn cap, or the stop
    button; a step it cannot do is parked with its reason and the run goes on
    to the next one (`app/longrun.py`).
    """
    outcome = longrun.start(thread_id)
    if not outcome.get("ok"):
        if outcome.get("error") == "no_such_thread":
            raise HTTPException(status_code=404, detail="thread not found")
        raise HTTPException(
            status_code=409,
            detail=outcome.get("detail") or outcome.get("error") or "the run could not start",
        )
    return outcome


@app.post("/api/threads/{thread_id}/turn/stop")
def stop_turn_ep(thread_id: int) -> dict[str, Any]:
    """Stop the turn that is running, at the next round boundary.

    Stops the run too when there is one, because a person pressing stop on a
    turn a run started means the run. See `app/interrupt.py` for why this can
    never land inside a tool call.
    """
    if events.get_thread(thread_id) is None:
        raise HTTPException(status_code=404, detail="no such thread")
    running = interrupt.a_turn_is_running(thread_id)
    if running:
        interrupt.ask_to_stop(thread_id)
    run = longrun.stop(thread_id, reason="stopped by the person")
    events.append(
        "turn.stop_asked",
        {
            "thread_id": int(thread_id),
            "a_turn_was_running": running,
            "run_stopped": run is not None,
        },
        thread_id=thread_id,
    )
    return {
        "ok": True,
        "thread_id": int(thread_id),
        "a_turn_was_running": running,
        "run_stopped": run is not None,
    }


@app.post("/api/threads/{thread_id}/run/stop")
def stop_run_ep(thread_id: int) -> dict[str, Any]:
    """Ask the run to stop after the turn it is in. Never mid-turn."""
    run = longrun.stop(thread_id)
    if run is None:
        raise HTTPException(status_code=404, detail="this thread has no run")
    return run


class RemoteLinkCreate(BaseModel):
    label: str = ""
    expires_in_hours: float = 24.0


@app.post("/api/threads/{thread_id}/remote_link")
def create_remote_link_ep(
    thread_id: int,
    request: Request,
    payload: RemoteLinkCreate | None = None,
) -> dict[str, Any]:
    """Mint a short-lived remote Approve + Stop URL (CS2).

    The raw token is returned once. SQLite stores only its sha256 hash.
    """
    body = payload or RemoteLinkCreate()
    try:
        minted = remote.create_link(
            thread_id,
            label=body.label,
            expires_in_hours=body.expires_in_hours,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    base = str(request.base_url).rstrip("/")
    url = f"{base}/remote/{minted['token']}"
    return {**minted, "url": url, "token": minted["token"]}


@app.delete("/api/remote_links/{link_id}")
def revoke_remote_link_ep(link_id: int) -> dict[str, Any]:
    """Revoke a remote-control link. The token stops working immediately."""
    out = remote.revoke(link_id)
    if out is None:
        raise HTTPException(status_code=404, detail="link not found")
    return out


def _remote_or_404(token: str) -> dict[str, Any]:
    link = remote.resolve(token)
    if link is None:
        raise HTTPException(status_code=403, detail="link expired, revoked, or unknown")
    return link


@app.get("/remote/{token}", response_class=HTMLResponse)
def remote_page_ep(token: str) -> str:
    """Thin HTML surface: pending Approve/Deny and Stop run (CS2)."""
    link = _remote_or_404(token)
    return remote.page_html(token, link)


@app.post("/remote/{token}/approve")
def remote_approve_ep(token: str) -> HTMLResponse:
    link = _remote_or_404(token)
    pending = remote.pending_approval(int(link["thread_id"]))
    if pending is None:
        raise HTTPException(status_code=409, detail="nothing waiting for approval")
    try:
        remote.approve(int(link["thread_id"]), pending)
    except Exception as error:  # noqa: BLE001 — surface to the thin page
        raise HTTPException(status_code=400, detail=str(error)) from error
    return HTMLResponse(remote.page_html(token, link), status_code=200)


@app.post("/remote/{token}/deny")
def remote_deny_ep(token: str) -> HTMLResponse:
    link = _remote_or_404(token)
    pending = remote.pending_approval(int(link["thread_id"]))
    if pending is None:
        raise HTTPException(status_code=409, detail="nothing waiting for approval")
    remote.deny(int(link["thread_id"]), pending)
    return HTMLResponse(remote.page_html(token, link), status_code=200)


@app.post("/remote/{token}/stop")
def remote_stop_ep(token: str) -> HTMLResponse:
    link = _remote_or_404(token)
    longrun.stop(int(link["thread_id"]), reason="stopped from remote link")
    return HTMLResponse(remote.page_html(token, link), status_code=200)


@app.get("/api/threads/{thread_id}/run")
def read_run_ep(thread_id: int) -> dict[str, Any]:
    """What the run on this thread is doing, or has done. `state` is empty
    when it has never had one, which is not an error."""
    return longrun.status(thread_id) or {"thread_id": thread_id, "state": ""}


@app.get("/api/threads/{thread_id}/subagents")
def read_subagents_ep(thread_id: int) -> dict[str, Any]:
    """What this conversation has handed out, and what each sub-agent is doing.

    The strip above the chat box asks for this while a run is going. It settles
    any child that has finished as it reads, so the answer is never a stale
    "running" for a sub-agent that stopped ten minutes ago.
    """
    if events.get_thread(thread_id) is None:
        raise HTTPException(status_code=404, detail="thread not found")
    return subagents.read(thread_id)


@app.post("/api/subagents/{subagent_id}/stop")
def stop_subagent_ep(subagent_id: int) -> dict[str, Any]:
    """Ask one sub-agent to stop after the turn it is in."""
    row = subagents.stop(subagent_id)
    if row is None:
        raise HTTPException(status_code=404, detail="no such sub-agent")
    return row


class ProjectSettings(BaseModel):
    """What a person turned on for a project. Absent means unchanged."""

    subagents_max: int | None = None
    packs_off: list[str] | None = None


@app.get("/api/projects/{project_id}/settings")
def read_settings_ep(project_id: int) -> dict[str, Any]:
    """Sub-agents and tool packs for this project, with what each pack costs.

    The COST is the point. Max, 2026-09-14, measured on his own database: 88%
    of a prompt was this product talking, 12,735 tokens of it tool schemas for
    44 tools. A switch with no number beside it is a guess; a switch that says
    "5,746 tokens, 17 tools" is a decision.
    """
    from app import settings as project_settings
    from app.tools import blocks as tool_blocks

    from app.providers import budget as budget_mod
    from app.tools import REGISTRY as registry

    current = project_settings.read(project_id)
    packs = []
    for name in tool_blocks.packs():
        names = sorted(tool_blocks.tools_in([name]))
        schemas = registry.model_tools(only=names)
        #: The same counter the context pane bills a turn with, so the number
        #: beside a switch is the number that leaves the window when it is
        #: thrown - not a second estimate that can disagree with the first.
        weight = budget_mod.estimate(
            *budget_mod.billable([], schemas)
        ).tokens
        packs.append(
            {
                "name": name,
                "tools": len(names),
                "tokens": weight,
                "core": name in tool_blocks.CORE,
                "off": name in current["packs_off"],
            }
        )
    return {
        **current,
        "packs": packs,
        "most_subagents": project_settings.MOST_SUBAGENTS,
    }


@app.post("/api/projects/{project_id}/settings")
def write_settings_ep(project_id: int, payload: ProjectSettings) -> dict[str, Any]:
    """Change the sub-agent cap, the packs, or both."""
    from app import settings as project_settings

    return project_settings.write(
        project_id,
        subagents_max=payload.subagents_max,
        packs_off=payload.packs_off,
    )


@app.get("/api/activity")
def read_activity_ep() -> dict[str, Any]:
    """Which conversations are working, and what each is carrying.

    The rail asks for this every few seconds so a person can see that another
    chat is mid-turn, or that a run is taking turns in it, without opening it.
    Read off the event log (`app/activity.py`), so it is true across windows
    and across a reload rather than only in the tab that started the work.
    """
    return activity.read()


@app.get("/api/threads/{thread_id}/context")
def read_context_ep(thread_id: int) -> dict[str, Any]:
    """What this conversation spends of the model's context window.

    Read back from the `turn.context` rows the conductor writes at assembly
    time - measured on the prompt that was sent, never re-derived here.
    """
    if events.get_thread(thread_id) is None:
        raise HTTPException(status_code=404, detail="thread not found")
    return contextwindow.read(thread_id)


@app.post("/api/threads/{thread_id}/compact")
def compact_thread_ep(thread_id: int) -> dict[str, Any]:
    """Force a context compaction for this thread (CS19 — Context pane button).

    Same path the conductor uses before assembling a turn (`app/compaction.py`),
    with `force=True` so a person can compact before the auto budget fires.
    Needs an active connected model to summarise.
    """
    from app import compaction
    from app.providers import build

    if events.get_thread(thread_id) is None:
        raise HTTPException(status_code=404, detail="thread not found")
    row = provider_store.active()
    if row is None:
        raise HTTPException(status_code=400, detail="connect a model first")
    adapter = build(
        row["adapter"],
        row["base_url"],
        row["model"],
        effort=str(row.get("effort") or "default"),
    )
    key = provider_secrets.get_key(str(row["id"]))
    payload = compaction.compact(
        thread_id,
        adapter,
        secret=key,
        window=compaction.window_of(adapter, key),
        force=True,
    )
    if payload is None:
        return {"ok": False, "detail": "nothing to compact"}
    return {"ok": True, **payload}


@app.get("/api/threads/{thread_id}/usage")
def read_usage_ep(thread_id: int) -> dict[str, Any]:
    """Tokens, tool calls, and wall time for this thread — with provenance.

    CS3. Aggregated from `turn.context`, `tool.call`, and `stream.end` only.
    """
    if events.get_thread(thread_id) is None:
        raise HTTPException(status_code=404, detail="thread not found")
    return usage.read(thread_id)


@app.post("/api/threads/{thread_id}/mode")
def set_thread_mode_ep(thread_id: int, payload: ThreadMode) -> dict[str, Any]:
    """Put this thread in `plan` or `build`.

    THE PERSON'S DOOR, and the only way a mode is ever set. No model can
    reach it - it is not a tool - and nothing in the engine reads the
    question and picks one. `app/modes.py` says why that road is closed.

    The reply carries both modes and what each one means, because a person
    switching this is owed the sentence about what just changed.
    """
    if not modes.is_a_mode(payload.mode):
        raise HTTPException(
            status_code=422,
            detail="mode must be one of " + ", ".join(sorted(modes.MODES)),
        )
    thread = events.set_thread_mode(thread_id, payload.mode)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    events.append(
        "thread.mode",
        {"id": thread["id"], "mode": payload.mode},
        project_id=thread["project_id"],
        thread_id=thread["id"],
    )
    return {**thread, "modes": modes.MODES}


@app.post("/api/threads/{thread_id}/plan")
def set_thread_plan_ep(thread_id: int, payload: ThreadPlan) -> dict[str, Any]:
    """Write the plan this thread agreed, or clear it.

    Separate from the mode on purpose: accepting a plan and starting to
    build are two decisions, and a person may want the plan recorded while
    they think about it. The control does both in one press; the engine
    keeps them apart so that it can.
    """
    thread = events.set_thread_plan(thread_id, payload.plan)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    events.append(
        "thread.plan",
        {"id": thread["id"], "chars": len(payload.plan or "")},
        project_id=thread["project_id"],
        thread_id=thread["id"],
    )
    return thread


@app.post("/api/threads/{thread_id}/effects/{effects_id}/revert")
def revert_turn_effects_ep(thread_id: int, effects_id: int) -> dict[str, Any]:
    """CS5 — undo plan/todo ticks from one turn. Ledger facts stay put."""
    if events.get_thread(thread_id) is None:
        raise HTTPException(status_code=404, detail="thread not found")
    out = effects.revert(thread_id, effects_id)
    if not out.get("ok"):
        code = 404 if out.get("error") in ("no_such_effects", "no_such_thread") else 409
        raise HTTPException(status_code=code, detail=out.get("detail") or out.get("error"))
    return out


@app.post("/api/threads/{thread_id}/todo")
def set_thread_todo_ep(thread_id: int, payload: ThreadTodo) -> dict[str, Any]:
    """CS9 — secondary checklist, separate from the diagnosis plan."""
    thread = events.set_thread_todo(thread_id, payload.todo)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    return thread


@app.post("/api/threads/{thread_id}/checklist_source")
def set_checklist_source_ep(
    thread_id: int, payload: ThreadChecklistSource
) -> dict[str, Any]:
    """CS9 — GoalBar/longrun work `plan` or `todo`."""
    try:
        thread = events.set_thread_checklist_source(thread_id, payload.source)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    return thread


@app.post("/api/threads/{thread_id}/autonomous")
def set_thread_autonomous_ep(
    thread_id: int, payload: ThreadAutonomy
) -> dict[str, Any]:
    """Put this thread in autonomous mode, or take it out.

    THE PERSON'S DOOR, and the only way this flag is ever set: nothing in the
    engine turns it on, no model can reach it (it is not a tool), and there
    is no global default that could switch it on for a thread nobody opted
    in. `app/autonomy.py` decides what it then covers, and the answer is a
    whitelist - a gated tool nobody classified still stops and asks.

    The reply carries that whitelist and its reasons, because a person
    switching this on is owed the list of what they just pre-approved, in the
    words that say why each one is safe to run unwatched.
    """
    thread = events.set_thread_autonomous(thread_id, bool(payload.on))
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    events.append(
        "thread.autonomous",
        {"id": thread["id"], "autonomous": bool(payload.on)},
        project_id=thread["project_id"],
        thread_id=thread["id"],
    )
    mode = autonomy.normalise(str(thread.get("permission") or "ask"))
    return {
        **thread,
        "permission": mode,
        "covers": autonomy.covers_for(mode),
        "never_covers": autonomy.never_covers_for(mode),
    }


@app.post("/api/threads/{thread_id}/permission")
def set_thread_permission_ep(
    thread_id: int, payload: ThreadPermission
) -> dict[str, Any]:
    """Set this thread's permission ladder step (ask / measure / write / full)."""
    mode = autonomy.normalise(payload.mode)
    if mode not in autonomy.MODES:
        raise HTTPException(status_code=400, detail="unknown permission mode")
    thread = events.set_thread_permission(thread_id, mode)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    events.append(
        "thread.permission",
        {"id": thread["id"], "permission": mode},
        project_id=thread["project_id"],
        thread_id=thread["id"],
    )
    return {
        **thread,
        "permission": mode,
        "covers": autonomy.covers_for(mode),
        "never_covers": autonomy.never_covers_for(mode),
    }


class ThreadBaselineProvider(BaseModel):
    provider_id: int | None = None


@app.post("/api/threads/{thread_id}/baseline_provider")
def set_thread_baseline_provider_ep(
    thread_id: int, payload: ThreadBaselineProvider
) -> dict[str, Any]:
    """AU3 — bind measure_baseline to a specific local connection for this thread."""
    thread = events.set_thread_baseline_provider(thread_id, payload.provider_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    events.append(
        "thread.baseline_provider",
        {"id": thread["id"], "provider_id": payload.provider_id},
        project_id=thread["project_id"],
        thread_id=thread["id"],
    )
    return thread


@app.get("/api/threads/{thread_id}/contexts")
def thread_contexts_ep(thread_id: int) -> dict[str, Any]:
    """What is attached to this thread, as a read. The composer's line above
    the box names the attached file from this rather than from `list_context`
    through the user door, which files a transcript row per call."""
    from app.tools import context as _context

    if events.get_thread(thread_id) is None:
        raise HTTPException(status_code=404, detail="thread not found")
    _context.ensure_contexts_table()
    rows = _context.list_contexts(thread_id)
    return {"thread_id": thread_id, "count": len(rows), "contexts": rows}


@app.delete("/api/threads/{thread_id}")
def delete_thread_ep(thread_id: int) -> dict[str, Any]:
    """Delete a thread and everything in it. The ledger keeps one line.

    Archive is the reversible door and stays; this one is for the thread
    nobody will read again. The `thread.deleted` event lands on the PROJECT
    with no thread_id - the thread it would name is gone - carrying the title
    and what was removed, so the rail's owner can still see that it existed.
    """
    outcome = events.delete_thread(thread_id)
    if outcome is None:
        raise HTTPException(status_code=404, detail="thread not found")
    thread = outcome["thread"]
    events.append(
        "thread.deleted",
        {"id": thread["id"], "title": thread["title"], "removed": outcome["removed"]},
        project_id=thread["project_id"],
    )
    return {"ok": True, "deleted": thread["id"], "removed": outcome["removed"]}


@app.post("/api/threads/{thread_id}/archive")
def archive_thread_ep(thread_id: int) -> dict[str, Any]:
    thread = events.archive_thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    events.append(
        "thread.archived",
        {"id": thread["id"], "archived_at": thread["archived_at"]},
        project_id=thread["project_id"],
        thread_id=thread["id"],
    )
    return thread


@app.post("/api/threads/{thread_id}/move")
def move_thread_ep(thread_id: int, payload: ThreadMove) -> dict[str, Any]:
    """Move a thread between projects.

    Both rows are looked up before anything is written, so a bad project id is
    a 404 that names which of the two was missing rather than an
    `IntegrityError` surfacing as a 500. The event carries where it came from
    as well as where it went: a rail watching the old project needs to know the
    thread left, and `from_project_id` is the only place that fact exists.
    """
    thread = events.get_thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    if db.get_project(payload.project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    moved = events.move_thread(thread_id, payload.project_id)
    events.append(
        "thread.moved",
        {
            "id": moved["id"],
            "from_project_id": thread["project_id"],
            "to_project_id": moved["project_id"],
        },
        project_id=moved["project_id"],
        thread_id=moved["id"],
    )
    return moved


@app.get("/api/threads/{thread_id}/report")
def thread_report_ep(thread_id: int) -> dict[str, Any]:
    """The conversation as data: verdict, gates, every fact with its origin.

    Phase F's export surface starts here. Same rows the printable page reads,
    before they are rendered.
    """
    try:
        return journey_report.build(thread_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="thread not found")
    except ValueError as error:
        # See `thread_stage_ep`: a sentence, not a bare 500.
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/threads/{thread_id}/journey")
def thread_journey_ep(thread_id: int) -> dict[str, Any]:
    """Where this thread is on its journey, and the one thing next.

    A GET under `/api/`, for the Stage's reason: this is a reader of what the
    thread already did and never a second writer. See `app/journey.py` for why
    "did the step's tool run" and "is the step's purpose met" are two questions
    and both are answered.
    """
    try:
        return journey.build(thread_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="thread not found")


@app.get("/api/threads/{thread_id}/stage")
def thread_stage_ep(thread_id: int) -> dict[str, Any]:
    """Everything the Stage draws, in one read. See `app/stage.py`.

    A GET, under `/api/`, so it carries the bearer token and writes nothing:
    the Stage is a second reader of what the thread measured and never a second
    writer. It files no "run by you" row, because it ran nothing.
    """
    try:
        return stage.build(thread_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="thread not found")
    except ValueError as error:
        # A DIAGNOSIS THAT REFUSES IS A SENTENCE, NOT A BARE 500. 2026-09-23:
        # the owner's Stage pane read "500 from /api/threads/93/stage" and
        # nothing else, while the engine had a whole sentence saying which fact
        # and which origin (`diagnosis.FactError`, a ValueError). The pane
        # shows `detail`; a 500 gave it nothing to show. 422 because the
        # request was fine and the thread's evidence is what cannot be read.
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/ui/report/{thread_id}", response_class=HTMLResponse)
def ui_report_ep(thread_id: int) -> HTMLResponse:
    """The printable journey page. Read-only, like every /ui route.

    Print-to-PDF is the export path on purpose: a PDF library is a dependency
    and this is not (app/journey_report.py's own header says why)."""
    try:
        report = journey_report.build(thread_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="thread not found")
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return HTMLResponse(journey_report.render_html(report))


@app.get("/api/threads/{thread_id}/export")
def thread_export_ep(thread_id: int) -> Response:
    """The consent-share artifact: one file, self-describing, provenance intact.

    Phase F starts here rather than at a share server, because the thing being
    shared has to EXIST before anybody decides where it may go. The bundle
    names the engine build that produced it (`identity`), so a report somebody
    pastes into an issue is attributable to the code that measured it - and it
    carries no secrets by construction: it reads the same rows the printable
    page reads, which have never included a key.
    """
    try:
        report = journey_report.build(thread_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="thread not found")
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    bundle = {
        "kind": "ml-harness/journey-export",
        "version": 1,
        "engine": {
            "engine_id": identity.ENGINE_ID,
            "code_fingerprint": identity.code_fingerprint()[0],
        },
        "report": report,
    }
    payload = json.dumps(bundle, indent=2, default=str)
    return Response(
        content=payload,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="ml-harness-thread-{thread_id}-report.json"'
            )
        },
    )


@app.post("/api/threads/{thread_id}/report/save")
def save_thread_report_ep(thread_id: int) -> dict[str, Any]:
    """The journey report, written into the project's own folder on disk.

    The owner's direction, verbatim: "it should write all this journal stuff
    into this path workspace because people can actually reference that" —
    and the browser-download path was the glitch he was clicking around: a
    packaged webview does not run downloads, so the button did nothing he
    could find on disk. This writes where the project already lives, which is
    also the only place it will write: a project with no `root_path` gets a
    400 naming the fix, never a file in a folder nobody chose.

    Two files, one truth: the printable page as HTML and the same bundle
    `/export` serves as JSON, both under `harness-reports/` so a workspace
    folder stays legible — reports in one place, the person's data untouched.
    """
    thread = events.get_thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    project = (
        db.get_project(thread["project_id"]) if thread.get("project_id") else None
    )
    root = (project or {}).get("root_path")
    if not root:
        raise HTTPException(
            status_code=400,
            detail=(
                "This thread's project has no folder attached, so there is "
                "nowhere to write. Attach one — the chip under the chat box "
                "does it — then save again."
            ),
        )
    root_dir = Path(root)
    if not root_dir.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"The project's folder does not exist on disk: {root}",
        )
    try:
        report = journey_report.build(thread_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    out_dir = root_dir / "harness-reports"
    try:
        out_dir.mkdir(exist_ok=True)
    except OSError as error:
        # `harness-reports` already exists as a FILE, or the folder is not
        # writable: a sentence, not a 500.
        raise HTTPException(
            status_code=400,
            detail=(
                f"{out_dir} could not be used as the reports folder: "
                f"{error.strerror or error}. Nothing was written."
            ),
        ) from error
    html_path = out_dir / f"thread-{thread_id}-journey.html"
    json_path = out_dir / f"thread-{thread_id}-journey.json"
    html_path.write_text(journey_report.render_html(report), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "kind": "ml-harness/journey-export",
                "version": 1,
                "engine": {
                    "engine_id": identity.ENGINE_ID,
                    "code_fingerprint": identity.code_fingerprint()[0],
                },
                "report": report,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return {
        "ok": True,
        "wrote": [str(html_path), str(json_path)],
        "detail": f"Journey report written into {out_dir}.",
    }


@app.get("/api/threads/{thread_id}")
def get_thread_ep(thread_id: int) -> dict[str, Any]:
    thread = events.get_thread(thread_id)
    # THE FILE WINS. If the plan file in the project folder changed since the
    # harness wrote it, its text becomes the column before anyone reads it -
    # app/planfile.py. `plan_path` rides on the row so the panes can name it.
    thread = planfile.sync(thread)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    return {"thread": thread, "messages": events.messages_for(thread_id)}


@app.post("/api/threads/{thread_id}/messages", status_code=201)
def post_message_ep(thread_id: int, payload: MessageCreate) -> dict[str, Any]:
    """The role is always `user`. It is never taken from the request body.

    A client that could set the role to `system` could rewrite the model's
    instructions, which would make every law in `app/instructions/` advisory.
    """
    message = events.add_message(thread_id, "user", payload.content)
    if message is None:
        raise HTTPException(status_code=404, detail="thread not found")
    events.append(
        "message.created",
        {"id": message["id"], "role": "user", "content": payload.content},
        thread_id=thread_id,
    )
    return message


@app.post("/api/threads/{thread_id}/turn")
def run_turn_ep(thread_id: int, payload: TurnRequest | None = None) -> dict[str, Any]:
    """Run one turn. Returns the event ids it wrote; the tokens go to the stream.

    The turn is not the stream. Every delta is committed to `events` as it
    happens, and the client reads them from `GET /api/events`, which is what
    makes a disconnect mid-reply lose nothing: the writer never depended on the
    reader being attached.
    """
    request = payload or TurnRequest()
    try:
        written = [
            row["id"]
            for row in conductor.run_turn(
                thread_id,
                provider_id=request.provider_id,
                sensitive=request.sensitive,
                invite_goal_edit=request.invite_goal_edit,
            )
        ]
    except conductor.ConductorError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {
        "thread_id": thread_id,
        "events": written,
        "last_event_id": written[-1] if written else 0,
    }


# Rows per read of a `follow=false` history. A page, not a cap: the read goes
# on while a page comes back full.
_HISTORY_PAGE = 500


@app.get("/api/events")
async def event_stream(
    scope: str,
    since: int = 0,
    follow: bool = True,
    timeout: float = 25.0,
    request: Request = None,
) -> StreamingResponse:
    """Replayable server-sent events. Every frame carries its durable id.

    `Last-Event-ID` beats the `since` query parameter when both are present:
    the browser sets that header itself on reconnect and it describes what the
    client actually received, where `since` is what the client assembled from
    memory before it dropped.
    """
    try:
        events.parse_scope(scope)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    header = request.headers.get("last-event-id") if request is not None else None
    cursor = since
    if header:
        try:
            cursor = int(header)
        except (TypeError, ValueError):
            cursor = since

    async def history():
        # `follow=false` IS A HISTORY READ, AND HISTORY IS EVERY ROW. It read
        # one page of 500 and returned, and every token delta is a row, so a
        # thread with a few turns ran past the page and the client lost its
        # later turns (their effects, Revert, plan diffs, eval reports) without
        # a word. Every page is replay: folded, and a `stream.end` in it closes
        # nothing. A run of deltas cut by the page edge is held back and folded
        # into the next page, so one reply is still one row.
        after = cursor
        held: dict[str, Any] | None = None
        while True:
            page = events.since(scope, after, limit=_HISTORY_PAGE)
            if not page:
                break
            after = page[-1]["id"]
            rows = events.fold_replay(([held] if held else []) + page)
            held = rows.pop() if rows[-1]["kind"] == "chat.delta" else None
            for row in rows:
                yield events.frame(row)
            if len(page) < _HISTORY_PAGE:
                break
        if held:
            yield events.frame(held)

    async def frames():
        nonlocal cursor
        loop = asyncio.get_event_loop()
        deadline = loop.time() + max(0.0, timeout)
        first = True
        while True:
            rows = events.since(scope, cursor)
            # THE FIRST PASS IS HISTORY, and history is folded (see
            # `events.fold_replay`): a thread that took three thousand token
            # deltas to write is replayed in one row per reply rather than
            # three thousand. Every pass after this one is live, and a live
            # delta is never folded - arriving one at a time is what makes a
            # reply look like it is being written.
            replaying = first
            if first:
                rows = events.fold_replay(rows)
                first = False
            for row in rows:
                yield events.frame(row)
                cursor = row["id"]
                # A LIVE `stream.end` CLOSES THE RESPONSE - that is the signal
                # a turn finished, and the client reconnects from its own
                # Last-Event-ID. A REPLAYED one does not: a thread with nine
                # turns holds nine of them, and closing on the first made a
                # cold open nine HTTP round trips to read what had already
                # happened. Max, 2026-09-13: "when I launch the app and open a
                # chat it loads all the tokens and conversations from
                # scratch... if we can fix that and remove latency."
                if row["kind"] == events.END_KIND and not replaying:
                    return
            if request is not None and await request.is_disconnected():
                return
            if loop.time() >= deadline:
                return
            # A comment frame keeps the connection open through a proxy and
            # costs nothing. It carries no id because it is not an event.
            yield ": keep-alive\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(
        frames() if follow else history(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/provider_presets")
def provider_presets_ep() -> list[dict[str, Any]]:
    return providers.PRESETS


@app.get("/api/providers/discover")
def providers_discover_ep() -> dict[str, Any]:
    """First-run's opening question: what is already running on this machine?

    Reads only. Connecting stays the user's explicit click on one of these."""
    return {"candidates": providers.discover()}


@app.get("/api/studios")
def studios_ep() -> dict[str, Any]:
    """Phase C's studios frame: packs as named surfaces, read live off the registry.

    The vocabulary is the engine's (`app/tools/blocks.py::CAPABILITIES`), the
    pack is the namespace, and a ledger binds stages to packs - never to tool
    names. This surface makes that binding inspectable without opening a ledger
    file, the same honesty the tools list has.
    """
    from app.tools import blocks

    return {
        "packs": dict(blocks.PACKS),
        "core": list(blocks.CORE),
        "capabilities": dict(blocks.CAPABILITIES),
        "pack_index": {
            name: list(tools) for name, tools in blocks.pack_index().items()
        },
    }


@app.get("/api/providers")
def list_providers_ep() -> list[dict[str, Any]]:
    return [_provider_public(row) for row in provider_store.list_all()]


@app.post("/api/providers", status_code=201)
def create_provider_ep(payload: ProviderCreate) -> dict[str, Any]:
    try:
        row = provider_store.create(
            payload.name, payload.base_url, payload.model, payload.adapter
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if payload.api_key:
        try:
            provider_secrets.set_key(str(row["id"]), payload.api_key)
        except provider_secrets.KeychainUnavailable as error:
            # The row exists and the key does not. Said plainly rather than
            # written somewhere it would not be protected.
            raise HTTPException(
                status_code=503,
                detail=f"the connection was saved but the key was not: {error}",
            ) from error
    return _provider_public(row)


@app.post("/api/providers/{provider_id}/activate")
def activate_provider_ep(provider_id: int) -> dict[str, Any]:
    row = provider_store.set_active(provider_id)
    if row is None:
        raise HTTPException(status_code=404, detail="provider not found")
    return _provider_public(row)


@app.post("/api/providers/{provider_id}/probe")
def probe_provider_ep(provider_id: int) -> dict[str, Any]:
    """Ask the connection what it can do, once, and record the answer."""
    row = conductor.probe(provider_id)
    if row is None:
        raise HTTPException(status_code=404, detail="provider not found")
    return _provider_public(row)


@app.patch("/api/providers/{provider_id}")
def update_provider_ep(provider_id: int, payload: ProviderUpdate) -> dict[str, Any]:
    """Edit a saved connection, including its key.

    The key half is handled here rather than in the store because the store
    holds SQL and must never learn what a keychain is - see
    `app/providers/secrets.py`, which contains no SQL and never imports `db` so
    that a key has nowhere to land even by accident. This route is the one
    place that calls both, in that order: the row first, so a keychain that
    refuses cannot leave the row describing a model the user never asked for.
    """
    try:
        row = provider_store.update(
            provider_id,
            name=payload.name,
            base_url=payload.base_url,
            model=payload.model,
            adapter=payload.adapter,
            effort=payload.effort,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if row is None:
        raise HTTPException(status_code=404, detail="provider not found")

    if "api_key" in payload.model_fields_set:
        # "" and None both mean forget it. Anything else replaces it.
        if payload.api_key:
            try:
                provider_secrets.set_key(str(provider_id), payload.api_key)
            except provider_secrets.KeychainUnavailable as error:
                raise HTTPException(
                    status_code=503,
                    detail=f"the connection was saved but the key was not: {error}",
                ) from error
        else:
            provider_secrets.delete_key(str(provider_id))
    return _provider_public(row)


@app.delete("/api/providers/{provider_id}")
def delete_provider_ep(provider_id: int) -> dict[str, Any]:
    """Forget a connection, and its key with it.

    BOTH HALVES OR NEITHER IS THE POINT. Deleting the row alone would leave an
    API key sitting in the user's OS keychain with nothing in this product left
    pointing at it - a secret nobody can see and nobody will think to remove,
    which is a worse outcome than never having stored it. The keychain entry is
    filed under the row id, so it has to go while the id still means something.

    Returns the row as it was, so the interface can say what it removed.
    `has_key` on that answer describes the state BEFORE the deletion, which is
    the only interesting version of that fact at this point.
    """
    existing = provider_store.get(provider_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="provider not found")
    before = _provider_public(existing)
    provider_store.delete(provider_id)
    provider_secrets.delete_key(str(provider_id))
    return {**before, "deleted": True}


@app.get("/api/keychain")
def keychain_ep() -> dict[str, Any]:
    """Whether this machine has somewhere safe to put an API key.

    ASKED BEFORE A KEY IS TYPED, NOT AFTER IT FAILS. `POST /api/providers`
    answers 503 when there is no OS secret store, which is honest and arrives
    one step too late: the user has already typed the key into a field by then.
    With this, the connect surface can say up front that keys on this machine
    go to the Windows Credential Manager - or that there is no store here and
    the environment variable is the way in.

    It carries no secret and cannot: the only strings it returns are a backend
    name, the service label all our entries are filed under, and the
    environment-variable prefix. All three are constants in the source.
    """
    store = provider_secrets.backend()
    return {
        "available": store is not None,
        "backend": None if store is None else store.name,
        "service": provider_secrets.SERVICE,
        "env_prefix": provider_secrets.ENV_PREFIX,
        "detail": (
            f"Keys go to the {store.name.replace('-', ' ')} on this machine, "
            f"filed under {provider_secrets.SERVICE}."
            if store is not None
            else "There is no OS keychain this process can write to, so a key "
            "cannot be saved here. Set it in the environment instead, as "
            f"{provider_secrets.ENV_PREFIX}<the connection's id>."
        ),
    }


@app.get("/api/tools")
def list_tools_ep() -> dict[str, Any]:
    """Every tool, described as a control.

    This is the same declaration the model is given. A user whose model cannot
    call tools drives the product from this list, which is what "every tool is
    also a control" means in practice rather than in a slogan.
    """
    return {
        "controls": tools.REGISTRY.controls(),
        "instruction_set": instructions.version(),
    }


@app.post("/api/tools/{name}")
def run_tool_ep(name: str, payload: ToolRun | None = None) -> dict[str, Any]:
    """The user's door, and the route says so rather than being told so.

    `actor=evidence.USER` is hard-coded here for the same reason the role on
    `POST /api/threads/{id}/messages` is hard-coded to `user`: a value the
    request body could set is a value an attacker could set, and here the value
    decides whether a fact counts as the person's own word. A model reaches the
    registry through `app/conductor.py`, which passes `model`. Two doors, two
    words, neither of them reachable from the message.

    `thread_id` IS STILL OPTIONAL AND THIS ROUTE NOW SAYS WHAT OPTIONAL MEANS.
    It used to mean nothing at all: the value went straight to `REGISTRY.call`,
    a `None` reached `evidence.record`, and the row landed at machine scope -
    where `rows_for` shows it to every conversation on this box. That is how
    `measure_eval_set` through this door counted a real file and opened
    G0_EVAL_SET in a thread that had never been shown one, and two of the three
    bad rows in the owner's real database came through here.

    Optional stays, because it is right for `inspect_hardware`: every fact that
    tool declares is the machine's own, a person reading their own hardware page
    has no conversation open, and demanding one would be ceremony. It is wrong
    for anything that can write a thread-scoped fact, and `evidence.
    thread_is_required_by` answers which is which off the tool's own `measures=`
    and the scope declared on each fact in `docs/diagnosis_engine.yaml` - never
    off a list of tool names here, which would be stale on the day a tool is
    added.

    ANSWERED HERE AND NOT ONLY IN THE LEDGER, for two reasons. The status code:
    a call that forgot an argument is an incomplete request (400), and the
    ledger's refusal reaching this route as a `MeasurementError` would be a 500,
    which says "the harness is broken" about a request that is merely missing
    something. And the sentence: this check runs BEFORE the tool does, so it can
    say what to send instead and promise that nothing ran. The ledger's refusal
    is still the wall - it stands for the conductor, and for Python, where there
    is no route at all.
    """
    request = payload or ToolRun()
    # A run filed under a thread writes rows into that thread (see the end of
    # this route), so the thread has to exist BEFORE anything runs — review
    # found rows being filed under ids that named no conversation.
    if request.thread_id is not None and events.get_thread(request.thread_id) is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"thread {request.thread_id} does not exist, so there is no "
                "conversation to file this run under. Nothing was run."
            ),
        )
    if request.thread_id is None and tools.evidence.thread_is_required_by(name):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "missing_thread_id",
                **tools.evidence.thread_id_help(name),
                "help": (
                    "Nothing was run and nothing was recorded. Send the same "
                    "call again with `thread_id` beside `arguments`."
                ),
            },
        )
    try:
        result = tools.REGISTRY.call(
            name,
            request.arguments,
            approved=request.approved,
            actor=tools.evidence.USER,
            thread_id=request.thread_id,
        )
    except tools.ToolError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except tools.ApprovalRequired as error:
        raise HTTPException(status_code=428, detail=str(error)) from error
    except tools.evidence.ScopeError as error:
        # BEFORE the MeasurementError clause, because ScopeError is a subclass of
        # it and Python takes the first match. A row refused for having no thread
        # is the caller's incomplete request, not a tool that laundered
        # something, so it is a 400 with the argument named - the same answer the
        # pre-check above gives, for the paths the pre-check cannot see: a tool
        # whose declarations say it only measures the machine and whose handler
        # writes a thread-scoped fact anyway. The wall is in `evidence.record`
        # and this is only how it is reported.
        raise HTTPException(status_code=400, detail=str(error)) from error
    except tools.GeneratedRowsError as error:
        # ALSO BEFORE THE MeasurementError CLAUSE, and also a subclass. Wall 8:
        # the call pointed at a file this harness generated rows into, and a
        # gate may not open on those. Nothing here is a defect - it is somebody
        # doing the obvious thing with the file they just made - so it is the
        # request that is refused, with the remedy in the message, rather than
        # a 500 that reads as the product falling over.
        raise HTTPException(status_code=422, detail=str(error)) from error
    except tools.MeasurementError as error:
        # A tool tried to stamp something it did not measure. That is a defect
        # in the tool, not in the request, and it must be loud rather than a
        # 500 with a stack trace in a log nobody reads.
        raise HTTPException(status_code=500, detail=str(error)) from error
    except diagnosis.FactError as error:
        # A malformed fact is the caller's, and it has a message. 400 rather
        # than 500 because nothing here fell over: the harness read what was
        # sent, could not make a fact of it, and says which one and why.
        raise HTTPException(status_code=400, detail=str(error)) from error
    except HTTPException:
        raise
    except Exception as error:  # noqa: BLE001 - the boundary net; see below
        # NOTHING GETS OUT OF HERE AS A TRACEBACK.
        #
        # This route is the user's door. Every tool behind it is written to
        # answer rather than raise, and one of them did not: `run_diagnosis`
        # with `{"need_type": 5}` raised a raw `TypeError` out of
        # `app/diagnosis.py`, past every handler above, and out of the ASGI app.
        # The three `except` clauses above name the failures this route
        # UNDERSTANDS; this one is for the ones it does not, and it exists so
        # that "a tool raised something nobody predicted" is a 500 with a
        # sentence and a tool name instead of a stack trace on somebody's
        # screen. The failure is not hidden - it is still a 500, it is still in
        # the log - it is just no longer shaped like a crash.
        raise HTTPException(
            status_code=500,
            detail=(
                f"{name} failed with {type(error).__name__}: {error}. That is a "
                "defect in the harness, not in the request. Nothing was recorded."
            ),
        ) from error

    # ── A RUN A PERSON FILED UNDER A THREAD IS PART OF THAT THREAD ──────────
    # The owner, reading a thread whose whole journey was driven through this
    # door: "you sent 13 steps with 0 output... where are you getting this
    # information from?" Every run was real and every result was in the
    # ledger, the bench and the files - and the TRANSCRIPT showed none of it,
    # because only the conductor ever wrote tool rows. So the door now writes
    # the same `tool.call`/`tool.result` pair the conductor writes, marked
    # `driven_by: "user"`, whenever the caller filed the run under a thread.
    # A call with no `thread_id` stays silent: a row belongs to a
    # conversation only when the caller said which one, and the surfaces that
    # refresh themselves (the attach popover's listing) deliberately do not.
    # Both events are appended AFTER the run so a tool that refused above
    # leaves no dangling "running" row.
    if request.thread_id is not None:
        call_id = f"user-{uuid4().hex[:12]}"
        events.append(
            "tool.call",
            {
                "id": call_id,
                "name": name,
                "arguments": request.arguments,
                "driven_by": "user",
            },
            thread_id=request.thread_id,
        )
        ok = not (isinstance(result, dict) and result.get("ok") is False)
        events.append(
            "tool.result",
            {
                "id": call_id,
                "name": name,
                "ok": ok,
                "result": result,
                "driven_by": "user",
            },
            thread_id=request.thread_id,
        )
    return {"tool": name, "result": result}


@app.get("/api/evidence")
def evidence_ep(thread_id: int | None = None) -> dict[str, Any]:
    """Why the harness believes what it believes, newest first.

    Invariant 3 says every displayed number carries its provenance. This is
    where the interface gets it for the facts a diagnosis was computed from:
    one row per claim or measurement, with who said it and how.
    """
    return {
        "thread_id": thread_id,
        "rows": tools.evidence.ledger_view(thread_id),
        "origins": {
            "MEASURED": "a tool ran on this machine and the engine watched it",
            "STATED": "the person whose project this is said so",
            "ASSERTED": "a model said so, or nobody said where it came from",
        },
        # QUARANTINE IS NOT DELETION, and this is where that stops being a claim
        # about a migration and becomes something a person can look at. Migration
        # 6 moved every row written at machine scope for a fact the ledger
        # declares thread scope - three of them in the owner's database, all
        # `eval_size_n`, two of them written by a reviewer through this very
        # route. They can no longer open anything, and they are all still here.
        "quarantined": tools.evidence.quarantine_view(),
        "quarantine_note": (
            "Rows written before a fact declared its scope, moved somewhere they "
            "cannot open a gate and kept exactly as they were written. Nothing "
            "was deleted; each row says why it was moved."
        ),
        # THE READ PATH REFUSES ROWS TOO, AND A ROW NOTHING SHOWS IS A ROW THAT
        # HAS BEEN DELETED AS FAR AS ANYBODY LOOKING CAN TELL. `rows_for` used
        # to serve every NULL-thread row to every conversation whatever the
        # ledger declared, so any such row arriving by a route `record()` does
        # not cover - a restored backup, a hand edit, a bulk import, a future
        # migration - reopened the first gate in silence. It now serves a NULL
        # row only for a fact declared `scope: machine`. These are the rest:
        # still in `fact_evidence`, exactly as written, visible to a person and
        # to no gate. Invariant 3 says every displayed number carries its
        # provenance, and a number the product has stopped believing has to be
        # displayed saying so rather than vanishing.
        "unscoped": tools.evidence.rows_no_thread_can_see(),
        "unscoped_note": (
            "Rows written with no conversation for a fact the ledger declares "
            "scope: thread - true of one project in one conversation and of no "
            "other. No conversation can see them and no gate can open on them. "
            "Nothing was moved and nothing was deleted: unlike the quarantine, "
            "which is what a migration did once, this is what the reader does "
            "every time it reads, so a row put back by a restored backup does "
            "not put the gate back with it."
        ),
    }


# ---------------------------------------------------------------------------
# The question, on the wire.
#
# `app/asking.py` derives THE question that would move a stopped diagnosis and
# has been in the tree with nothing importing it. This is the import. It is one
# route and it is deliberately the smallest one that could work, because every
# field it grows is a field somebody could later mistake for an input.
#
# READ-ONLY, AND THAT IS A PROPERTY OF THE VERB RATHER THAN OF THE HANDLER.
# `GET` because the whole call is a derivation: `assemble_facts` reads rows,
# `diagnose` is pure, `next_step` is pure, and nothing between them writes. A
# person can refresh this a thousand times and the ledger will not have moved.
#
# ══ WHY THERE IS NO `POST /api/next_step/answer`, AND WHY THERE MUST NOT BE ══
#
# This is the whole reason the route is shaped like this. A card produced here
# says what kind of answer its fact takes and WHAT ORIGIN THAT ANSWER WOULD
# ARRIVE UNDER - `arrives_as`, STATED for a field, MEASURED for a pointer. It
# would be a very short walk from serving that string to accepting it back, and
# that walk is the laundering route this entire design exists to shut: a request
# that carried its own origin would let anybody stamp MEASURED on a number they
# typed, and every one of the five gates would open on it.
#
# So the answer does not come back here. It goes through `POST /api/tools/{name}`
# - `state_facts` for a field, the named measuring tool for a pointer - which
# hard-codes `actor=evidence.USER` and lets `evidence.SUPPLIED_ORIGIN` decide
# what that is worth. `state_facts` declares `measures=()`, so there is no code
# path from a typed field to a MEASURED stamp even if a caller asks for one.
# The card names that tool in `settled_by.tool`; it does not become it.
#
# `arrives_as` on the wire is therefore a PROMISE THE PRODUCT CAN KEEP rather
# than an instruction: `asking.Question.__post_init__` refuses to construct a
# card whose origin the ledger does not admit for that fact, so the string this
# route serves is the one the tool boundary will actually write.


@app.get("/api/next_step")
def next_step_ep(thread_id: int | None = None) -> dict[str, Any]:
    """One question, or the news that it is time to propose. Nothing is recorded.

    `thread_id` is which conversation's evidence to reason over. It is optional
    for the same reason it is optional on `GET /api/evidence`: a person with no
    conversation open still gets the first question the empty sheet produces,
    which is the honest answer to "what would you ask me first".

    NO FACTS ARE ACCEPTED FROM THE REQUEST. `assemble_facts(thread_id, {})` is
    called with an empty supplied dict on purpose - the sheet is what the ledger
    holds for this thread and nothing else. A `facts` parameter here would be a
    way to ask "what would you ask me if I had already told you X", which is a
    reasonable question and a terrible route: the answer is a card, the card
    names a tool, and a caller who can move the frontier by asserting things can
    choose which question the person is shown. `run_diagnosis` already takes
    facts, through the boundary that decides what a caller's word is worth.
    """
    # WHICH LEDGER THIS CONVERSATION IS RUNNING, ASKED BEFORE ANYTHING ELSE.
    # `asking.py` is written for one ledger and says so in `_spec`; `diagnose`
    # with no spec is the ML tree. Together, before 2026-08-27, they gave an
    # AI-engineering thread this, measured through this very route:
    #
    #     outcome  BLOCKED__DEFINE_SUCCESS_FIRST
    #     question classes_n, "say how much of this data is usable"
    #     because  S0_RULES_SUFFICE
    #
    # An outcome from another domain's tree, a fact that thread's ledger has
    # never heard of, and a card naming a tool that could not measure anything
    # in it. That is Phase 0's finding arriving exactly as it was predicted -
    # *"a second ledger will diagnose correctly and then hand its verdict to a
    # tool layer still reading the first ledger's file"* - on a route a person
    # can open.
    #
    # SO IT REFUSES RATHER THAN ANSWERING, and the refusal names the domain.
    # This is `evidence.resolves`' and `propose.propose`'s shape for the same
    # situation: the two states - "we cannot answer this" and "these tables
    # were never asked this domain's question" - are told apart and said out
    # loud. Making `asking.py` ledger-aware is the real fix and it is a
    # refactor of thirteen call sites and two dataclasses; it is written down
    # as a bounded debt in docs/PHASES.md. What may not wait for it is a
    # confident wrong answer.
    running = tools.evidence.ledger_for_thread(thread_id).as_written
    mine = diagnosis.default_spec().as_written
    if thread_id is not None and running != mine:
        raise HTTPException(
            status_code=409,
            detail=(
                f"This conversation is running {running}, and the next-question "
                f"machinery in this harness is written for {mine}. It would "
                "have answered - with an outcome from the other domain's tree, "
                "asking for a fact your ledger does not declare, and naming a "
                "tool that cannot measure anything in it. Nothing was recorded "
                "and no question is offered, because a confident question about "
                "the wrong domain is worse than none. Run the diagnosis for "
                "this thread instead: POST /api/tools/run_diagnosis, which reads "
                "the ledger this conversation is actually running."
            ),
        )

    try:
        sheet, _trail = tools.evidence.assemble_facts(thread_id, {}, tools.evidence.USER)
        result = diagnosis.diagnose(sheet)
        step = asking.next_step(result=result)
    except asking.AskingError as error:
        # The ledger and the registry disagree about a fact, which is a defect
        # in the harness rather than in the request. Loud, with a sentence, and
        # never a traceback on somebody's screen - the same rule `run_tool_ep`
        # follows one route up.
        raise HTTPException(
            status_code=500,
            detail=(
                f"the next question could not be derived: {error}. That is a "
                "defect in the harness, not in the request. Nothing was recorded."
            ),
        ) from error
    except diagnosis.EngineError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    return {
        "thread_id": thread_id,
        "step": step.as_dict(),
        # WHERE THE ANSWER GOES, said by the route that will not take it. A
        # client reading this payload should not have to infer from the absence
        # of a POST that there is another door; it is named, with the sentence
        # about what that door decides.
        "answer_through": {
            "route": "POST /api/tools/{name}",
            "tool": step.question.answered_by if step.question else None,
            "actor": tools.evidence.USER,
            "note": (
                "This route serves the question and takes no answer. The tool "
                "named above is called through the user's own door, which "
                "hard-codes the actor and lets the ledger decide the origin. "
                "Nothing sent to this route can change what an answer is worth."
            ),
        },
    }


# ---------------------------------------------------------------------------
# The storm: approving a build, running it, and watching it while it runs.
#
# `docs/THE_PROPOSAL_LOOP.md` step 5 is a contract rather than a button, and the
# shape of these routes is what makes that true rather than said:
#
# - **Nothing here accepts a plan to execute.** `POST /api/storms` takes the
#   inputs a proposal was made from and the fingerprint the person approved, and
#   the harness proposes again. The object that gets recorded and run is always
#   one the engine built and validated in the same request, so "the proposal is
#   the object the executor consumes" holds through the HTTP boundary too.
# - **A changed plan is a 409, never a run.** If the plan the harness would make
#   now is not the plan the person said yes to, this refuses and hands back both,
#   because the answer to "the world moved" is asking again rather than guessing
#   which of the two they meant.
# - **Starting a storm does not hold the request.** The run goes onto a daemon
#   thread and the events reach the transcript as they are committed, so the
#   turn endpoint stays free and the user can ask what is happening while it is
#   happening.
#
# There is deliberately no route that edits a storm. What was approved is a row
# that is written once; everything that happens to it is an event.


class StormApprove(BaseModel):
    """A person saying yes to a specific plan, and to that plan only.

    `approve` is the `Build.fingerprint()` the proposal came back with - the
    hash of exactly what was on screen. `proposal` is the arguments that
    proposal was made from, so the harness can make it again and check that it
    still comes out the same.

    `build` is optional and is never executed. It is what the person was shown,
    sent so that a mismatch can be reported as *what changed* instead of as a
    bare "that is not the same plan any more".
    """

    thread_id: int
    approve: str
    proposal: dict[str, Any] = Field(default_factory=dict)
    build: dict[str, Any] | None = None


class StormRun(BaseModel):
    """Start, or carry on.

    `restart_stalled` is the person's answer to a storm that was interrupted.
    A step that was running when the engine died is not restarted on anyone's
    assumption: naming it here is the decision, taken after being told what
    re-running it might repeat.
    """

    background: bool = True
    restart_stalled: list[str] = Field(default_factory=list)


@app.post("/api/storms", status_code=201)
def approve_storm_ep(payload: StormApprove) -> dict[str, Any]:
    """Approve a build and record the contract. Nothing runs here."""
    thread = events.get_thread(payload.thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")

    try:
        proposed = tools.REGISTRY.call(
            "propose_build",
            dict(payload.proposal),
            actor=tools.evidence.USER,
            thread_id=payload.thread_id,
        )
    except tools.ToolError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except HTTPException:
        raise
    except Exception as error:  # noqa: BLE001 - the boundary net, as run_tool_ep
        raise HTTPException(
            status_code=500,
            detail=(
                f"propose_build failed with {type(error).__name__}: {error}. "
                "Nothing was approved and nothing was recorded."
            ),
        ) from error

    if not isinstance(proposed, dict) or not proposed.get("ok"):
        raise HTTPException(
            status_code=409,
            detail=(
                "there is no plan to approve right now: "
                + str((proposed or {}).get("detail") or (proposed or {}).get("error"))
            ),
        )

    fresh = proposed.get("build") or {}
    if proposed.get("approve") != payload.approve:
        changed: list[str] = []
        if payload.build:
            try:
                changed = list(
                    storm.Manifest.of(
                        fresh, fingerprint=str(proposed.get("approve"))
                    ).deviations_from(payload.build)
                )
            except storm.StormRefused as error:
                changed = list(error.deviations) or [error.detail]
        raise HTTPException(
            status_code=409,
            detail={
                "error": "not_the_plan_you_approved",
                "approved": payload.approve,
                "now": proposed.get("approve"),
                "changed": changed,
                "build": fresh,
                "what_now": (
                    "The plan the harness would run now is not the one you said yes "
                    "to, so nothing was recorded. Read this one and approve it if it "
                    "is what you want."
                ),
            },
        )

    try:
        declared = storm.declare(
            fresh,
            approved=str(proposed.get("approve")),
            thread_id=payload.thread_id,
        )
    except storm.StormRefused as error:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "refused",
                "detail": error.detail,
                "changed": list(error.deviations),
            },
        ) from error
    except storm.StormError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    return storm.attach(declared["storm"]).as_dict()


@app.get("/api/storms")
def list_storms_ep(thread_id: int) -> dict[str, Any]:
    """Every storm in one conversation, newest first."""
    if events.get_thread(thread_id) is None:
        raise HTTPException(status_code=404, detail="thread not found")
    return {"thread_id": thread_id, "storms": storm.list_for_thread(thread_id)}


@app.get("/api/storms/{storm_id}")
def get_storm_ep(storm_id: int) -> dict[str, Any]:
    """The storm as it stands: the plan, and the state of every node in it.

    Re-attached on every call rather than cached, which is what makes an engine
    that has just restarted answer this identically to one that never stopped.
    """
    try:
        return storm.attach(storm_id).as_dict()
    except storm.StormError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/storms/{storm_id}/run")
def run_storm_ep(storm_id: int, payload: StormRun | None = None) -> dict[str, Any]:
    """Run it. Returns immediately; the work reports itself into the thread."""
    request = payload or StormRun()
    try:
        storm.load(storm_id)
    except storm.StormError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    if request.background:
        storm.start(storm_id, restart_stalled=tuple(request.restart_stalled))
        return storm.attach(storm_id).as_dict()

    try:
        written = [
            row["id"]
            for row in storm.run(
                storm_id, restart_stalled=tuple(request.restart_stalled)
            )
        ]
    except storm.StormRefused as error:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "refused",
                "detail": error.detail,
                "changed": list(error.deviations),
            },
        ) from error
    except storm.StormError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    answer = storm.attach(storm_id).as_dict()
    answer["events"] = written
    return answer


@app.post("/api/storms/{storm_id}/cancel")
def cancel_storm_ep(storm_id: int) -> dict[str, Any]:
    """Ask a storm to stop. A running one stops between steps."""
    try:
        storm.cancel(storm_id)
    except storm.StormError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return storm.attach(storm_id).as_dict()
