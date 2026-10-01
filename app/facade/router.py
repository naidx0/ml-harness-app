"""The routes: OpenCode's operations, answered by this engine's own functions.

Every route here is a thin door onto something the engine already does. A
session is created by the same `events.create_thread` call `POST /api/threads`
makes, renamed by `rename_thread_ep`, stopped by `stop_turn_ep`, switched
between plan and build by `set_thread_mode_ep` - the route functions in
`app/main.py` are called directly, imported late because `app.main` mounts
this router. Calling the route functions rather than the storage beneath them
is deliberate: each one also appends the event every other window listens
for, and a facade that wrote the row without the event would change a thread
behind the back of the engine's own interface.

## Response shapes

Every body is built to their OpenAPI document (`app/facade/openapi.json`), and
`tests/test_the_facade_speaks_their_protocol.py` validates each one against the
operation's declared schema. Errors use their encoded error bodies
(`{"_tag": "SessionNotFoundError", "message": ...}`) with the status the
operation declares, because their client parses a declared status's body and
treats an undeclared one as a transport failure.
"""

from __future__ import annotations

import functools
import os
import secrets
import time
import urllib.parse
import urllib.request
from typing import Any, Callable
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from app import activity, autonomy, db, events, security
from app.config import HOST, PORT
from app.facade import answered, catalog, files, integrations, sessions, stream, translate, turns, vcs

router = APIRouter(prefix=security.FACADE_PREFIX)

#: What a new conversation is called until someone names it - the same words
#: the harness's own "new chat" button used.
NEW_TITLE = "New chat"


class Refused(Exception):
    """A request answered with one of their declared error bodies.

    `fields` are the error's own required keys - `SessionNotFoundError` names
    the `sessionID`, `PermissionNotFoundError` the `requestID` - because their
    encoded errors forbid a missing one as firmly as an extra one.
    """

    def __init__(self, status: int, tag: str, message: str, **fields: str) -> None:
        super().__init__(message)
        self.status = status
        self.tag = tag
        self.message = message
        self.fields = fields


def error(status: int, tag: str, message: str, **fields: str) -> JSONResponse:
    return JSONResponse({"_tag": tag, "message": message, **fields}, status_code=status)


def answers(handler: Callable[..., Any]) -> Callable[..., Any]:
    """Turn a refusal from anywhere below into their error body.

    A route function in `app/main.py` refuses with `HTTPException`. Every one
    this facade calls is reached for a session that has already been found, so
    its 404 means the thread went away in between and is their
    `SessionNotFoundError`; a 409 is their `ConflictError`; anything else is
    the request's fault as far as their client can act on it, and every
    operation declares 400 for that.
    """

    @functools.wraps(handler)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return handler(*args, **kwargs)
        except Refused as refusal:
            return error(refusal.status, refusal.tag, refusal.message, **refusal.fields)
        except HTTPException as refusal:
            detail = refusal.detail if isinstance(refusal.detail, str) else str(refusal.detail)
            if refusal.status_code == 404:
                return error(
                    404, "SessionNotFoundError", detail, sessionID=str(kwargs.get("sessionID", ""))
                )
            if refusal.status_code == 409:
                return error(409, "ConflictError", detail)
            return error(400, "InvalidRequestError", detail)

    return wrapper


def _engine():
    from app import main

    return main


def _directory(request: Request) -> str | None:
    """The directory their `location` query names, if any.

    Their client flattens an object query as `location[directory]=...`
    (`appendQuery` in their generated client); a bare `directory` is accepted
    too, because `session.list` sends it that way.
    """
    value = request.query_params.get("location[directory]") or request.query_params.get("directory")
    return value or None


def _located(request: Request) -> dict[str, Any]:
    directory = _directory(request)
    if directory:
        return {"directory": directory}
    return {"directory": sessions.directory_of(db.default_project())}


def _thread(sid: str) -> dict[str, Any]:
    thread_id = sessions.thread_id_of(sid)
    thread = events.get_thread(thread_id) if thread_id is not None else None
    if thread is None:
        raise Refused(404, "SessionNotFoundError", f"no session {sid}", sessionID=str(sid))
    return thread


def _invalid(message: str) -> Refused:
    return Refused(400, "InvalidRequestError", message)


# ---------------------------------------------------------------------------
# The server, its location and its catalogs


@router.get("/api/info")
@answers
def server_info(request: Request) -> dict[str, Any]:
    """Who is answering. Their health check reads only that this succeeds.

    The URL is the one the request arrived on rather than the configured port,
    because an engine started on another port (a second checkout, a test) is
    still the engine this client is talking to.
    """
    base = str(request.base_url).rstrip("/") or f"http://{HOST}:{PORT}"
    return {
        "version": _engine().app.version,
        "pid": os.getpid(),
        "urls": [f"{base}{security.FACADE_PREFIX}"],
        # Their attachment upload writes under this (`experimental.fs.write`),
        # and it is the one place that write is allowed (`files.write_target`).
        "paths": {"tmp": str(files.tmp_dir())},
    }


@router.get("/api/location")
@answers
def location_get(request: Request) -> dict[str, Any]:
    return sessions.location_info(sessions.project_for_directory(_directory(request)))


@router.get("/api/project")
@answers
def project_list() -> list[dict[str, Any]]:
    return [sessions.project_info(project) for project in db.list_projects()]


@router.get("/api/config")
@answers
def config_get() -> list[dict[str, Any]]:
    return catalog.config_entries()


@router.get("/api/agent")
@answers
def agent_list(request: Request) -> dict[str, Any]:
    return {"location": _located(request), "data": catalog.agents()}


@router.get("/api/model")
@answers
def model_list(request: Request) -> dict[str, Any]:
    return {"location": _located(request), "data": catalog.models()}


@router.get("/api/model/default")
@answers
def model_default(request: Request) -> dict[str, Any]:
    return {"location": _located(request), "data": catalog.default_model()}


@router.get("/api/provider")
@answers
def provider_list(request: Request) -> dict[str, Any]:
    return {"location": _located(request), "data": catalog.providers()}


# ---------------------------------------------------------------------------
# Integrations: their connect dialog over the harness's keyed presets
# (`app/facade/integrations.py`).


def _integration_missing(iid: str) -> Refused:
    return Refused(
        404,
        "IntegrationNotFoundError",
        f"no integration {iid!r}; this engine connects "
        f"{', '.join(p['name'] for p in integrations.keyed_presets().values())} with a key",
        integrationID=str(iid),
    )


@router.get("/api/integration")
@answers
def integration_list(request: Request) -> dict[str, Any]:
    return {"location": _located(request), "data": integrations.listed()}


@router.get("/api/integration/{integrationID}")
@answers
def integration_get(integrationID: str, request: Request) -> dict[str, Any]:
    found = integrations.find(integrationID)
    if found is None:
        raise _integration_missing(integrationID)
    return {"location": _located(request), "data": found}


@router.post("/api/integration/{integrationID}/connect/key")
@answers
def integration_connect_key(
    integrationID: str, payload: dict[str, Any] = Body(default_factory=dict)
) -> Response:
    """Connect a keyed preset: make the connection, keep the key, use it.

    THE CONNECTION IS MADE BY `create_provider_ep`, the engine's own door, so
    the key goes to the OS keychain by the same code and a machine with no
    keychain gets the same sentence (its 503 becomes their declared 400
    through `answers`). The row stays in that case, because the sentence tells
    the person how to supply the key another way (`MLH_KEY_<id>`), and that
    way needs the row. Only a connection whose key was kept is made active;
    it is probed on a thread (`catalog.probe_later`), and their catalogs are
    re-read when the stream sees the row change.
    """
    presets = integrations.keyed_presets()
    preset = presets.get(integrationID)
    if preset is None:
        raise _integration_missing(integrationID)
    key = payload.get("key")
    if not isinstance(key, str) or not key.strip():
        raise _invalid("an API key is required")
    try:
        model = integrations.chosen_model(preset, payload.get("answer"))
    except ValueError as refusal:
        raise _invalid(str(refusal)) from refusal
    label = payload.get("label")
    name = str(label).strip()[:120] if isinstance(label, str) and label.strip() else str(preset["name"])
    main = _engine()
    row = main.create_provider_ep(
        main.ProviderCreate(
            name=name,
            base_url=str(preset["base_url"]),
            model=model,
            adapter=str(preset["adapter"]),
            api_key=key.strip(),
        )
    )
    main.activate_provider_ep(int(row["id"]))
    catalog.probe_later(int(row["id"]))
    return Response(status_code=204)


@router.delete("/api/credential/{credentialID}")
@answers
def credential_remove(credentialID: str) -> Response:
    """Forget one connection and its key, through `delete_provider_ep`."""
    connection = integrations.connection_of_credential(credentialID)
    if connection is None:
        raise _invalid(f"{credentialID!r} is not a credential this engine issued")
    try:
        _engine().delete_provider_ep(connection)
    except HTTPException as refusal:
        raise _invalid(f"no credential {credentialID}: {refusal.detail}") from refusal
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Sessions


def _page(items: list[Any], request: Request, *, default_order: str) -> tuple[list[Any], dict[str, Any]]:
    """A page of `items` (oldest first) under their `limit`/`order`/`cursor`.

    The cursor carries its own order - `desc:<index>` means "the items before
    this index" - because their `loadMore` passes the cursor alone and expects
    the page to continue in the order the first page was read.
    """
    order = request.query_params.get("order") or default_order
    cursor = request.query_params.get("cursor")
    raw_limit = request.query_params.get("limit")
    try:
        limit = max(1, int(raw_limit)) if raw_limit else None
    except ValueError as bad:
        raise _invalid(f"limit must be a whole number, got {raw_limit!r}") from bad
    if cursor:
        kind, _, number = cursor.partition(":")
        if kind not in ("asc", "desc") or not number.isdigit():
            raise Refused(400, "InvalidCursorError", f"not a cursor this server issued: {cursor!r}")
        order, position = kind, int(number)
    else:
        position = len(items) if order == "desc" else 0
    if order == "desc":
        start = 0 if limit is None else max(0, position - limit)
        page = list(reversed(items[start:position]))
        after = f"desc:{start}" if start > 0 else None
    else:
        end = len(items) if limit is None else min(len(items), position + limit)
        page = items[position:end]
        after = f"asc:{end}" if end < len(items) else None
    return page, {"previous": None, "next": after}


@router.get("/api/session")
@answers
def session_list(request: Request) -> dict[str, Any]:
    threads = list(reversed(events.list_threads()))  # oldest first, for paging
    # A CHAT LEAVES THE LIST WITH ITS PROJECT. `/api/project` hides archived
    # projects, but their threads are not themselves archived, so the unscoped
    # list still carried them: their client then drew each one in a folder it
    # invented from the thread's directory, beside projects that exist - two
    # strays on the owner's own rail (2026-09-22). Every chat is a chat in a
    # project the list shows; a project-less thread stays, it reads as Default.
    shown = {int(project["id"]) for project in db.list_projects()}
    threads = [t for t in threads if t.get("project_id") is None or int(t["project_id"]) in shown]
    directory = request.query_params.get("directory")
    # A FILTER THAT NAMES NOTHING MATCHES NOTHING. An unresolved directory or
    # parent came back `None`, and `== None` matched every project-less thread,
    # or every top-level chat as the "children" of a session their client had
    # minted but not yet created.
    if directory:
        project = sessions.find_project(directory)
        wanted = project["id"] if project else None
        threads = [t for t in threads if wanted is not None and t.get("project_id") == wanted]
    project_filter = request.query_params.get("project")
    if project_filter:
        wanted_project = sessions.project_of(project_filter)
        threads = [
            t for t in threads if wanted_project is not None and t.get("project_id") == wanted_project
        ]
    parent = request.query_params.get("parentID")
    if parent == "null":
        threads = [t for t in threads if not t.get("subagent_of")]
    elif parent:
        parent_thread = sessions.thread_id_of(parent)
        threads = [
            t for t in threads if parent_thread is not None and t.get("subagent_of") == parent_thread
        ]
    search = (request.query_params.get("search") or "").casefold()
    if search:
        threads = [t for t in threads if search in str(t.get("title") or "").casefold()]
    page, cursor = _page(threads, request, default_order="desc")
    return {"data": [sessions.session_info(thread) for thread in page], "cursor": cursor}


@router.get("/api/session/active")
@answers
def session_active() -> dict[str, Any]:
    working: set[int] = set()
    for entry in activity.read()["threads"]:
        working.add(int(entry["thread_id"]))
    for thread in events.list_threads():
        if turns.busy(int(thread["id"])):
            working.add(int(thread["id"]))
    return {"data": {sessions.session_id(tid): {"type": "running"} for tid in sorted(working)}}


def _apply_agent(thread: dict[str, Any], agent: str) -> None:
    """Put the thread in the preset `agent` names, through the engine's doors."""
    preset = sessions.AGENTS.get(agent)
    if preset is None:
        raise _invalid(f"unknown agent {agent!r}; this engine offers {', '.join(sessions.AGENTS)}")
    main = _engine()
    if thread.get("mode") != preset["mode"]:
        main.set_thread_mode_ep(int(thread["id"]), main.ThreadMode(mode=preset["mode"]))
    if autonomy.normalise(str(thread.get("permission") or "")) != preset["permission"]:
        main.set_thread_permission_ep(
            int(thread["id"]), main.ThreadPermission(mode=preset["permission"])
        )


def _apply_permissions(thread: dict[str, Any], rules: Any) -> None:
    if rules is None:
        return
    if not isinstance(rules, list):
        raise _invalid("permissions must be a list of rules")
    step = sessions.permission_from_ruleset(rules)
    if autonomy.normalise(str(thread.get("permission") or "")) != step:
        main = _engine()
        main.set_thread_permission_ep(int(thread["id"]), main.ThreadPermission(mode=step))


def _select_model(ref: Any) -> None:
    if ref is None:
        return
    if not isinstance(ref, dict):
        raise _invalid("model must be an object with id and providerID")
    try:
        catalog.select_model(ref)
    except (LookupError, ValueError) as refusal:
        raise _invalid(str(refusal)) from refusal


@router.post("/api/session")
@answers
def session_create(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    """A new conversation, under the id their client already minted.

    THE THREAD IS MADE HERE RATHER THAN THROUGH `create_thread_ep`, and the
    difference is one line: the client's id is recorded against the thread
    BEFORE `thread.created` is appended. The event stream names a thread's
    session the first time it sees it, so an event read before the id was
    recorded would announce the session under `ses_<n>`, and every later event
    for it would go to a session their client has never heard of. The rest is
    the route's own sequence: the same mode for a person's new conversation,
    no plan adopted into an empty chat, the same `thread.created` event.
    """
    from app import modes

    oc_id = payload.get("id")
    if oc_id is not None and not (isinstance(oc_id, str) and oc_id.startswith("ses")):
        raise _invalid("a session id starts with 'ses'")
    if oc_id:
        existing = sessions.thread_id_of(oc_id)
        thread = events.get_thread(existing) if existing is not None else None
        if thread is not None:
            # Their client retries a create it did not hear back from.
            return {"data": sessions.session_info(thread)}

    location = payload.get("location") or {}
    directory = location.get("directory") if isinstance(location, dict) else None
    project = sessions.project_for_directory(directory)
    title = str(payload.get("title") or NEW_TITLE)[:200]
    agent = payload.get("agent")
    preset = sessions.AGENTS.get(str(agent)) if agent else None
    if agent and preset is None:
        raise _invalid(f"unknown agent {agent!r}; this engine offers {', '.join(sessions.AGENTS)}")
    mode = preset["mode"] if preset else modes.WHEN_A_PERSON_OPENS_A_CONVERSATION
    if payload.get("permissions") is not None and not isinstance(payload["permissions"], list):
        raise _invalid("permissions must be a list of rules")
    # The model is chosen BEFORE the thread exists, so a refused model leaves
    # no conversation behind it that nobody asked for.
    _select_model(payload.get("model"))

    thread = events.create_thread(title, project["id"], mode=mode, adopt_project_plan=False)
    if oc_id:
        sessions.remember(oc_id, thread["id"])
    events.append(
        "thread.created",
        {"id": thread["id"], "title": thread["title"]},
        project_id=thread["project_id"],
        thread_id=thread["id"],
    )
    if preset and preset["permission"] != "ask":
        _apply_agent(thread, str(agent))
    _apply_permissions(events.get_thread(thread["id"]) or thread, payload.get("permissions"))
    return {"data": sessions.session_info(events.get_thread(thread["id"]) or thread)}


@router.get("/api/session/{sessionID}")
@answers
def session_get(sessionID: str) -> dict[str, Any]:
    return {"data": sessions.session_info(_thread(sessionID))}


@router.patch("/api/session/{sessionID}")
@answers
def session_update(sessionID: str, payload: dict[str, Any] = Body(default_factory=dict)) -> Response:
    thread = _thread(sessionID)
    title = payload.get("title")
    if title is not None:
        if not isinstance(title, str) or not title.strip():
            raise _invalid("title must be a non-empty string")
        main = _engine()
        main.rename_thread_ep(int(thread["id"]), main.ThreadRename(title=title.strip()[:200]))
    _apply_permissions(thread, payload.get("permissions"))
    return Response(status_code=204)


@router.delete("/api/session/{sessionID}")
@answers
def session_remove(sessionID: str) -> Response:
    thread = _thread(sessionID)
    _engine().delete_thread_ep(int(thread["id"]))
    return Response(status_code=204)


@router.post("/api/session/{sessionID}/agent")
@answers
def session_switch_agent(sessionID: str, payload: dict[str, Any] = Body(default_factory=dict)) -> Response:
    thread = _thread(sessionID)
    agent = payload.get("agent")
    if not isinstance(agent, str):
        raise _invalid("agent is required")
    _apply_agent(thread, agent)
    return Response(status_code=204)


@router.post("/api/session/{sessionID}/model")
@answers
def session_switch_model(sessionID: str, payload: dict[str, Any] = Body(default_factory=dict)) -> Response:
    _thread(sessionID)
    if "model" not in payload:
        raise _invalid("model is required")
    _select_model(payload.get("model"))
    return Response(status_code=204)


def _mint_message_id() -> str:
    """A message id in their shape: `msg_`, twelve hex of time, fourteen more."""
    stamp = int(time.time() * 1000) * 0x1000 + secrets.randbelow(0x1000)
    return "msg_" + format(stamp, "012x")[-12:] + secrets.token_hex(7)


def _attach(thread_id: int, files: Any, attachments: Any = None, directory: str | None = None) -> list[str]:
    """Attach the prompt's local files through the harness's own door.

    Their composer sends two kinds of local file. Files and @-mentions arrive
    as URIs in `files`; a `file:` URI names a path on this machine. A dropped
    or uploaded file arrives as a PATH part, which their composer puts in the
    text as a reference and in `metadata.attachments[].path` - an upload's path
    is the one `experimental.fs.write` answered, in the engine's temporary
    directory. Both are exactly what `attach_context` records, and both go
    through `run_tool_ep`, the user's door, so the attachment lands in the
    transcript as the person's own action. A path is attached once however
    many times it is named. Anything else (an inline image, a remote URL) has
    no counterpart in the engine and is named in the message instead of being
    silently dropped.
    """
    notes: list[str] = []
    wanted: list[tuple[str, str]] = []
    for item in files if isinstance(files, list) else []:
        uri = str((item or {}).get("uri") or "") if isinstance(item, dict) else ""
        name = str((item or {}).get("name") or uri) if isinstance(item, dict) else ""
        parsed = urllib.parse.urlparse(uri)
        if parsed.scheme != "file":
            notes.append(f"(not attached: {name or 'an item'} is not a file on this machine)")
            continue
        path = urllib.request.url2pathname(urllib.parse.unquote(parsed.path))
        if parsed.netloc and parsed.netloc != "localhost":
            path = f"//{parsed.netloc}{path}"
        wanted.append((path, name))
    for item in attachments if isinstance(attachments, list) else []:
        raw = str((item or {}).get("path") or "") if isinstance(item, dict) else ""
        if not raw:
            continue
        if raw.startswith("file:"):
            raw = urllib.request.url2pathname(urllib.parse.unquote(urllib.parse.urlparse(raw).path))
        path = raw if os.path.isabs(raw) or not directory else os.path.join(directory, raw)
        wanted.append((path, str(item.get("name") or raw)))
    main = _engine()
    seen: set[str] = set()
    for path, name in wanted:
        key = os.path.normcase(os.path.normpath(path))
        if key in seen:
            continue
        seen.add(key)
        try:
            main.run_tool_ep(
                "attach_context", main.ToolRun(arguments={"path": path}, thread_id=thread_id)
            )
        except HTTPException as refusal:
            notes.append(f"(not attached: {name}: {refusal.detail})")
    return notes


def _admit(thread: dict[str, Any], payload: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """Write a person's message into the thread: `(their id, content, row)`.

    The message is written with the engine's own `add_message` and the same
    `message.created` event `post_message_ep` appends - plus `oc_id`, the id
    their client minted and already shows, so the stream can tell it which of
    its pending messages this was. Attachments go first, and a note for any
    that could not be attached joins the text.
    """
    text = payload.get("text")
    if not isinstance(text, str):
        raise _invalid("text is required")
    oc_id = payload.get("id") or _mint_message_id()
    if not (isinstance(oc_id, str) and oc_id.startswith("msg_")):
        raise _invalid("a message id starts with 'msg_'")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    notes = _attach(
        int(thread["id"]),
        payload.get("files"),
        metadata.get("attachments"),
        sessions.session_info(thread)["location"]["directory"],
    )
    content = "\n".join(part for part in [text, *notes] if part.strip())
    if not content.strip():
        raise _invalid("the message is empty")
    sid = sessions.session_id(int(thread["id"]))
    message = events.add_message(int(thread["id"]), "user", content)
    if message is None:
        raise Refused(404, "SessionNotFoundError", f"no session {sid}", sessionID=sid)
    events.append(
        "message.created",
        {"id": message["id"], "role": "user", "content": content, "oc_id": oc_id},
        thread_id=int(thread["id"]),
    )
    return oc_id, content, message


@router.post("/api/session/{sessionID}/prompt")
@answers
def session_prompt(sessionID: str, payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    """Admit the message (`_admit`), answer, and run the turn behind the answer."""
    thread = _thread(sessionID)
    oc_id, content, message = _admit(thread, payload)
    turns.submit(int(thread["id"]))
    delivery = payload.get("delivery") if payload.get("delivery") in ("steer", "queue") else "steer"
    body: dict[str, Any] = {"text": content}
    if isinstance(payload.get("metadata"), dict):
        body["metadata"] = payload["metadata"]
    return {
        "data": {
            "id": oc_id,
            "sessionID": sessions.session_id(int(thread["id"])),
            "time": {"created": sessions.ms(message.get("created_at")) or int(time.time() * 1000)},
            "type": "user",
            "payload": body,
            "delivery": delivery,
        }
    }


@router.post("/api/session/{sessionID}/interrupt")
@answers
def session_interrupt(sessionID: str) -> dict[str, Any]:
    """Stop - the engine's stop, which is an interruption and never a pause.

    `stop_turn_ep` stops the turn and a run with it; a turn queued behind it
    is dropped too, because a stop that let the next reply start would not be
    one. Since 2026-09-23 a press while the model is writing ends that model
    call within the second - the in-flight request is closed and the words
    already written stay - where it used to wait for a round boundary 60-90 s
    away; a TOOL that is running still finishes (`app/interrupt.py`). Their
    Stop sends `resume=true`, which asks for queued steering to resume; there
    is no steering queue here, so it changes nothing.
    """
    thread = _thread(sessionID)
    outcome = _engine().stop_turn_ep(int(thread["id"]))
    dropped = turns.cancel_waiting(int(thread["id"]))
    return {
        "interrupted": bool(
            outcome.get("a_turn_was_running") or outcome.get("run_stopped") or dropped
        )
    }


@router.post("/api/session/{sessionID}/compact")
@answers
def session_compact(sessionID: str, payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    """Compact now: the engine's `compact_thread_ep`, the Context pane's button.

    It summarises with the active model, so it needs one (their 400 with the
    engine's sentence), and it is refused while a reply is being written
    (their 409), because a compaction that rewrote the context under a running
    turn would change what that turn had read. What the engine answers -
    including "nothing to compact" - is the payload of their compaction item.
    """
    thread = _thread(sessionID)
    oc_id = payload.get("id") or _mint_message_id()
    if not (isinstance(oc_id, str) and oc_id.startswith("msg_")):
        raise _invalid("a message id starts with 'msg_'")
    if turns.busy(int(thread["id"])):
        raise Refused(409, "ConflictError", "a reply is being written; compact once it has finished")
    outcome = _engine().compact_thread_ep(int(thread["id"]))
    delivery = payload.get("delivery") if payload.get("delivery") in ("steer", "queue") else "steer"
    return {
        "data": {
            "id": oc_id,
            "sessionID": sessions.session_id(int(thread["id"])),
            "time": {"created": int(time.time() * 1000)},
            "type": "compaction",
            "payload": dict(outcome) if isinstance(outcome, dict) else {"result": outcome},
            "delivery": delivery,
        }
    }


#: The slash commands the engine runs. Every other one their composer offers
#: stays on their side (`/plan`, `/doc` and their own are client commands).
COMMANDS = {
    "goal": (
        "Set or change the goal: this turn may edit the plan's goal and todo, "
        "and the Plan pane opens."
    ),
}


@router.get("/api/command")
@answers
def command_list(request: Request) -> dict[str, Any]:
    return {
        "location": _located(request),
        "data": [{"name": name, "description": text} for name, text in COMMANDS.items()],
    }


@router.post("/api/session/{sessionID}/command")
@answers
def session_command(sessionID: str, payload: dict[str, Any] = Body(default_factory=dict)) -> Response:
    """`/goal`: the turn the old composer's "may edit goal/todo" box ran.

    With text, the text is admitted as the person's message and a turn runs
    with `invite_goal_edit` - the engine's own turn option (`TurnRequest`),
    the same one `POST /api/threads/{id}/turn` takes. With or without text,
    `harness.ui.open` asks the interface to open the Plan pane, where the goal
    is. An unknown command is their `CommandNotFoundError`.
    """
    thread = _thread(sessionID)
    name = str(payload.get("name") or "").lstrip("/")
    if name not in COMMANDS:
        raise Refused(
            404,
            "CommandNotFoundError",
            f"no command {name!r}; this engine runs {', '.join('/' + c for c in COMMANDS)}",
            command=name,
        )
    text = payload.get("text")
    if not isinstance(text, str):
        raise _invalid("text is required")
    if text.strip() or payload.get("files"):
        _admit(thread, {**payload, "text": text})
        turns.submit(int(thread["id"]), invite_goal_edit=True)
    events.append(translate.UI_OPEN, {"tab": "plan"}, thread_id=int(thread["id"]))
    return Response(status_code=204)


@router.get("/api/session/{sessionID}/message")
@answers
def session_message_list(sessionID: str, request: Request) -> dict[str, Any]:
    thread = _thread(sessionID)
    messages = translate.transcript(int(thread["id"]))
    wanted = request.query_params.get("type")
    if wanted:
        messages = [message for message in messages if message["type"] == wanted]
    page, cursor = _page(messages, request, default_order="asc")
    return {"data": page, "cursor": cursor}


@router.get("/api/session/{sessionID}/message/{messageID}")
@answers
def session_message_get(sessionID: str, messageID: str) -> dict[str, Any]:
    thread = _thread(sessionID)
    for message in translate.transcript(int(thread["id"])):
        if message["id"] == messageID:
            return {"data": message}
    raise Refused(
        404,
        "MessageNotFoundError",
        f"no message {messageID} in {sessionID}",
        sessionID=sessionID,
        messageID=messageID,
    )


@router.get("/api/session/{sessionID}/inbox")
@answers
def session_inbox_list(sessionID: str) -> dict[str, Any]:
    """Always empty, and truthfully so.

    Their inbox holds messages admitted but not yet delivered to the model.
    This engine delivers on admission: a prompt is in the transcript the moment
    `session.prompt` answers, and a turn queued behind a running one reads it
    from there.
    """
    _thread(sessionID)
    return {"data": []}


@router.delete("/api/session/{sessionID}/inbox/{inboxID}")
@answers
def session_inbox_cancel(sessionID: str, inboxID: str) -> Response:
    """Idempotent, as their protocol makes it: nothing is ever waiting here."""
    _thread(sessionID)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Approvals


@router.get("/api/session/{sessionID}/permission")
@answers
def session_permission_list(sessionID: str) -> dict[str, Any]:
    thread = _thread(sessionID)
    pending = translate.pending_approval(int(thread["id"]))
    return {"data": [pending] if pending else []}


@router.get("/api/permission/request")
@answers
def permission_request_list(request: Request) -> dict[str, Any]:
    """Every approval waiting in one location's conversations.

    Their auto-approve sweep asks this per directory. A directory is a project
    here, so the answer is the pending request, if any, of each of that
    project's live threads - read by the same rule `session.permission.list`
    uses.
    """
    directory = _directory(request)
    project = sessions.find_project(directory) if directory else db.default_project()
    pending = []
    if project is not None:
        for thread in events.list_threads(project_id=int(project["id"])):
            asked = translate.pending_approval(int(thread["id"]))
            if asked is not None:
                pending.append(asked)
    return {"location": _located(request), "data": pending}


def _raise_for_always(thread: dict[str, Any], tool: str) -> None:
    """`always`: move the ladder to the lowest step that covers this tool.

    Their "always allow" saves a rule; this engine's equivalent is the
    permission ladder, whose steps each pre-approve a named list. So the thread
    moves up to the first step that covers the tool - and never down, and never
    past what the tool needs. A tool no step covers (the sandbox wipe) stays a
    one-time approval.
    """
    current = autonomy.normalise(str(thread.get("permission") or ""))
    ladder = list(autonomy.MODES)
    for step in ladder[ladder.index(current) + 1:]:
        if tool in autonomy.covers_for(step):
            main = _engine()
            main.set_thread_permission_ep(int(thread["id"]), main.ThreadPermission(mode=step))
            return


@router.post("/api/session/{sessionID}/permission/{requestID}/reply")
@answers
def session_permission_reply(
    sessionID: str, requestID: str, payload: dict[str, Any] = Body(default_factory=dict)
) -> Response:
    """Answer the approval dock: run the held tool as the person, or decline it.

    APPROVING RUNS THE TOOL THROUGH THE REGISTRY WITH `actor=USER` AND
    `approved=True` - what `app/remote.py::approve` does for the phone page,
    and the only way an approval ever reaches the registry: a person pressed a
    button. The call and result are appended AFTER the run, as `run_tool_ep`
    does, so a tool that raises leaves no dangling running row; both carry
    `answers`, which is how the stream knows to take the request off the dock.
    """
    from app.tools import REGISTRY, ApprovalRequired, ToolError, evidence

    thread = _thread(sessionID)
    decision = payload.get("decision")
    if decision not in ("once", "always", "reject"):
        raise _invalid("decision must be once, always or reject")
    pending = translate.pending_approval(int(thread["id"]))
    if pending is None or pending["id"] != requestID:
        raise Refused(
            404, "PermissionNotFoundError", f"no pending request {requestID}", requestID=requestID
        )
    tool = str(pending["action"])
    arguments = (pending.get("metadata") or {}).get("arguments") or {}
    thread_id = int(thread["id"])
    if decision == "reject":
        note = payload.get("message")
        events.append(
            "tool.result",
            {
                "id": pending["source"]["id"],
                "name": tool,
                "ok": False,
                "result": {
                    "ok": False,
                    "error": "declined",
                    "detail": str(note) if note else "declined in the approval dock",
                },
                "driven_by": "user",
                "via": "facade",
                "answers": requestID,
                "decision": "reject",
            },
            thread_id=thread_id,
        )
        return Response(status_code=204)

    if decision == "always":
        _raise_for_always(thread, tool)
    try:
        result = REGISTRY.call(
            tool, dict(arguments), approved=True, actor=evidence.USER, thread_id=thread_id
        )
    except (ApprovalRequired, ToolError) as refusal:
        result = {"ok": False, "error": "tool_failed", "detail": str(refusal)}
    except Exception as refusal:  # noqa: BLE001 - the dock gets a sentence, not a traceback
        result = {"ok": False, "error": "tool_failed", "detail": f"{type(refusal).__name__}: {refusal}"}
    call_id = f"user-{uuid4().hex[:12]}"
    events.append(
        "tool.call",
        {"id": call_id, "name": tool, "arguments": arguments, "driven_by": "user", "via": "facade"},
        thread_id=thread_id,
    )
    ok = not (isinstance(result, dict) and result.get("ok") is False)
    events.append(
        "tool.result",
        {
            "id": call_id,
            "name": tool,
            "ok": ok,
            "result": result,
            "driven_by": "user",
            "via": "facade",
            "answers": requestID,
            "decision": decision,
        },
        thread_id=thread_id,
    )
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Files: their tree, previews, @-mentions and attachment uploads, confined to
# the project's folder and the engine's temporary directory (`files.py`).


def _outside(refusal: Exception) -> Refused:
    return Refused(400, "InvalidRequestError", str(refusal))


@router.get("/api/fs/list")
@answers
def fs_list(request: Request) -> dict[str, Any]:
    try:
        entries = files.list_entries(_directory(request), request.query_params.get("path"))
    except (files.Outside, files.Missing) as refusal:
        raise _outside(refusal) from refusal
    return {"location": _located(request), "data": entries}


@router.get("/api/fs/find")
@answers
def fs_find(request: Request) -> dict[str, Any]:
    query = request.query_params.get("query")
    if query is None:
        raise _invalid("query is required")
    kind = request.query_params.get("type")
    if kind not in (None, "", "file", "directory"):
        raise _invalid("type must be file or directory")
    try:
        found = files.find(_directory(request), query, kind, request.query_params.get("limit"))
    except (files.Outside, ValueError) as refusal:
        raise _outside(refusal) from refusal
    return {"location": _located(request), "data": found}


@router.get("/api/fs/read/{path:path}")
@answers
def fs_read(path: str, request: Request) -> Response:
    try:
        data = files.read(_directory(request), path)
    except files.Missing as refusal:
        raise Refused(404, "FileNotFoundError", str(refusal), path=path) from refusal
    except (files.Outside, ValueError, OSError) as refusal:
        raise _outside(refusal) from refusal
    return Response(content=data, media_type="application/octet-stream")


@router.post("/api/experimental/fs/write")
async def fs_write(request: Request) -> Any:
    """Their attachment upload: the body, streamed into the temporary directory.

    Async because the body is streamed to disk as it arrives rather than held
    in memory - their composer uploads whatever file a person drops, and a
    video would otherwise be read whole into the engine first.
    """
    path = request.query_params.get("path") or ""
    try:
        destination = files.write_target(_directory(request), path)
    except (files.Outside, ValueError) as refusal:
        return error(400, "InvalidRequestError", str(refusal))
    destination.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    partial = destination.with_name(destination.name + ".part")
    try:
        with partial.open("wb") as sink:
            async for chunk in request.stream():
                written += len(chunk)
                if written > files.MAX_WRITE_BYTES:
                    raise ValueError(
                        f"the upload is over {files.MAX_WRITE_BYTES // (1024 * 1024)} MB, "
                        "which is more than an attachment here may be"
                    )
                sink.write(chunk)
        os.replace(partial, destination)
    except (ValueError, OSError) as refusal:
        partial.unlink(missing_ok=True)
        return error(400, "InvalidRequestError", str(refusal))
    return {"location": _located(request), "data": {"path": str(destination)}}


# ---------------------------------------------------------------------------
# Git, through their review panel (`vcs.py`), in the same confined folder.


def _repo_folder(request: Request) -> Any:
    try:
        return files.base_for(_directory(request))[1]
    except files.Outside as refusal:
        raise _outside(refusal) from refusal


def _unavailable(refusal: Exception) -> Refused:
    return Refused(503, "ServiceUnavailableError", str(refusal))


@router.get("/api/vcs")
@answers
def vcs_get(request: Request) -> dict[str, Any]:
    return {"location": _located(request), "data": vcs.info(_repo_folder(request))}


@router.get("/api/vcs/status")
@answers
def vcs_status(request: Request) -> dict[str, Any]:
    return {"location": _located(request), "data": vcs.status(_repo_folder(request))}


@router.get("/api/vcs/diff")
@answers
def vcs_diff(request: Request) -> dict[str, Any]:
    folder = _repo_folder(request)
    try:
        data = vcs.diff(
            folder,
            request.query_params.get("mode") or "",
            request.query_params.get("base") or None,
            request.query_params.get("context"),
        )
    except ValueError as refusal:
        raise _invalid(str(refusal)) from refusal
    except vcs.Unavailable as refusal:
        raise _unavailable(refusal) from refusal
    return {"location": _located(request), "data": data}


@router.get("/api/vcs/base")
@answers
def vcs_base(request: Request) -> dict[str, Any]:
    folder = _repo_folder(request)
    try:
        data = vcs.base(folder)
    except vcs.Unavailable as refusal:
        raise _unavailable(refusal) from refusal
    return {"location": _located(request), "data": data}


@router.get("/api/vcs/branch")
@answers
def vcs_branch_list(request: Request) -> dict[str, Any]:
    folder = _repo_folder(request)
    try:
        data = vcs.branches(folder, request.query_params.get("search"), request.query_params.get("limit"))
    except ValueError as refusal:
        raise _invalid(str(refusal)) from refusal
    return {"location": _located(request), "data": data}


# ---------------------------------------------------------------------------
# The event stream


@router.get("/api/event")
async def event_subscribe(request: Request) -> StreamingResponse:
    return StreamingResponse(
        stream.frames(request, request.headers.get("last-event-id")),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# The surfaces answered without being implemented


def _answer(operation: answered.Operation) -> Callable[[Request], Any]:
    def endpoint(request: Request) -> Any:
        if operation.kind == answered.ACTION:
            return error(400, "InvalidRequestError", answered.unsupported_message(operation.operation_id))
        return answered.body_for(operation, lambda: _located(request))

    endpoint.__name__ = "answered_" + operation.operation_id.replace(".", "_")
    return endpoint


for _operation in answered.OPERATIONS:
    router.add_api_route(
        _operation.path,
        _answer(_operation),
        methods=[_operation.method],
        name=_operation.operation_id,
        include_in_schema=False,
    )
del _operation
