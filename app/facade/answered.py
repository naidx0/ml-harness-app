"""Their surfaces this engine does not have, answered honestly.

Their interface has panels for terminals, shells, MCP servers, web search,
git worktrees, OAuth sign-ins, plugins and forms. The harness has none of
these - it has tools, and its own folder and attachment model - so there is
nothing behind those panels to translate.

Some of their panels DID find a counterpart and moved out of this list on
purpose (2026-09-22): keyed integrations and credentials
(`app/facade/integrations.py`), the file tree (`files.py`), the review
panel's git reads (`vcs.py`), `/goal` and compaction (`router.py`).

What their interface needs from each is still an ANSWER: a request that 404s
or 500s is drawn as a broken server, while a request that returns the empty
shape its schema declares is drawn as the panel's own empty state - "no
terminals", "no MCP servers" - which is simply true here.

Two kinds of answer, and the line between them is whether the operation asks
for something to be listed or for something to be done:

* **Reads** return their schema's empty shape with 200: an empty list, an
  empty catalog, a `null` where the schema allows one.
* **Actions** - create a terminal, connect an integration, stage a revert -
  cannot be answered with an empty shape without claiming they happened. They
  return 400 with their own `InvalidRequestError` body, which every one of
  these operations declares, and a sentence saying this engine does not do it.

Each operation is listed by name in `OPERATIONS`, and
`tests/test_the_facade_speaks_their_protocol.py` walks the list, so a surface
cannot become half-implemented without someone moving it out of here on
purpose.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

#: How each read's empty answer is shaped. `located` is wrapped in their
#: `{location, data}` envelope; `data` is wrapped in `{data}`; `bare` is sent as
#: it is.
READ = "read"
ACTION = "action"


@dataclass(frozen=True)
class Operation:
    operation_id: str
    method: str
    path: str
    kind: str
    #: For a read: `(envelope, empty data)`.
    empty: tuple[str, Any] | None = None


def _read(operation_id: str, path: str, envelope: str, empty: Any) -> Operation:
    return Operation(operation_id, "GET", path, READ, (envelope, empty))


def _action(operation_id: str, method: str, path: str) -> Operation:
    return Operation(operation_id, method, path, ACTION)


#: The operations their interface calls that this engine answers without
#: implementing, found by reading their client calls (`api.*` and `api().*`
#: in `packages/app/src`, `packages/session-ui/src` and the `createData`
#: store) and matched against their OpenAPI document.
OPERATIONS: tuple[Operation, ...] = (
    # Terminals and shells.
    _read("pty.list", "/api/pty", "located", []),
    _action("pty.create", "POST", "/api/pty"),
    _action("pty.get", "GET", "/api/pty/{ptyID}"),
    _action("pty.update", "PUT", "/api/pty/{ptyID}"),
    _action("pty.remove", "DELETE", "/api/pty/{ptyID}"),
    _read("shell.list", "/api/shell", "located", []),
    _action("shell.create", "POST", "/api/shell"),
    _action("shell.output", "GET", "/api/shell/{id}/output"),
    _action("session.shell", "POST", "/api/session/{sessionID}/shell"),
    _read("config.shells", "/api/config/shell", "bare", []),
    # MCP.
    _read("mcp.list", "/api/mcp", "located", []),
    _read("mcp.resource.catalog", "/api/mcp/resource", "located", {"resources": [], "templates": []}),
    _action("experimental.mcp.connect", "POST", "/api/experimental/mcp/{server}/connect"),
    _action("experimental.mcp.disconnect", "POST", "/api/experimental/mcp/{server}/disconnect"),
    # OAuth. The keyed presets ARE implemented (`integration.list`, `.get`,
    # `.connect.key`, `credential.remove` in `app/facade/integrations.py`),
    # with the key in the OS keychain through the engine's own door; a browser
    # sign-in has no counterpart here, and no integration offers one.
    _action("integration.oauth.connect", "POST", "/api/integration/{integrationID}/connect/oauth"),
    _action("integration.oauth.status", "GET", "/api/integration/{integrationID}/connect/oauth/{attemptID}"),
    _action("integration.oauth.cancel", "DELETE", "/api/integration/{integrationID}/connect/oauth/{attemptID}"),
    _action(
        "integration.oauth.complete",
        "POST",
        "/api/integration/{integrationID}/connect/oauth/{attemptID}/complete",
    ),
    # Web search.
    _read("websearch.providers", "/api/websearch/provider", "located", []),
    # Worktrees. Git itself is implemented (`vcs.*` in `app/facade/vcs.py`);
    # making and removing worktrees is not something this engine does.
    _read("worktree.list", "/api/worktree", "bare", []),
    _action("worktree.create", "POST", "/api/worktree"),
    _action("worktree.refresh", "POST", "/api/worktree/refresh"),
    _action("worktree.remove", "DELETE", "/api/worktree"),
    # Plugins, skills, references. (`command.list` is implemented: `/goal`.)
    _read("plugin.list", "/api/plugin", "located", []),
    _read("skill.list", "/api/skill", "located", []),
    _read("reference.list", "/api/reference", "located", []),
    # Forms, saved permissions.
    _read("form.list", "/api/form", "located", []),
    _read("session.form.list", "/api/session/{sessionID}/form", "data", []),
    _action("session.form.reply", "POST", "/api/session/{sessionID}/form/{formID}/reply"),
    _action("session.form.cancel", "DELETE", "/api/session/{sessionID}/form/{formID}"),
    _read("permission.saved.list", "/api/permission/saved", "data", []),
    # Session actions with no engine counterpart.
    _action("session.background", "POST", "/api/session/{sessionID}/background"),
    _action("session.revert.stage", "POST", "/api/session/{sessionID}/revert/stage"),
    _action("session.revert.clear", "DELETE", "/api/session/{sessionID}/revert"),
    _action("session.move", "POST", "/api/session/{sessionID}/move"),
    # Forking a conversation, and the "by the way" side question, are the two
    # open questions `docs/PHASE-4-FACADE.md` defers; until they are decided
    # they are refused in words rather than half-built.
    _action("session.fork", "POST", "/api/session/{sessionID}/fork"),
    _action("session.generate", "POST", "/api/session/{sessionID}/generate"),
    # Nothing ever waits in the inbox here (see `session.inbox.list`), so there
    # is no queued item whose delivery could be changed.
    _action("session.inbox.update", "PATCH", "/api/session/{sessionID}/inbox/{inboxID}"),
    _action("project.update", "PATCH", "/api/project/{projectID}"),
    _action("experimental.config.update", "PATCH", "/api/experimental/config"),
)


def unsupported_message(operation_id: str) -> str:
    return (
        f"{operation_id} is not something this engine does. The ML Harness "
        "engine speaks OpenCode's protocol for conversations, models and "
        "approvals; this surface has no counterpart in it."
    )


def body_for(operation: Operation, location: Callable[[], dict[str, Any]]) -> Any:
    """The empty answer for a read, in its envelope."""
    assert operation.empty is not None
    envelope, empty = operation.empty
    data = list(empty) if isinstance(empty, list) else (dict(empty) if isinstance(empty, dict) else empty)
    if envelope == "located":
        return {"location": location(), "data": data}
    if envelope == "data":
        return {"data": data}
    return data
