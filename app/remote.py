"""Tokenized remote Approve + Stop for a live thread (CS2).

Raw tokens are shown once at mint time. SQLite stores only sha256(hex).
Revoke and expiry are first-class; the remote URL is the capability.
"""
from __future__ import annotations

import hashlib
import html
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from app import db, events, longrun, theme
from app.tools import evidence
from app.tools import registry as tools_registry

CAPABILITIES_DEFAULT = "approve,stop"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_link(
    thread_id: int,
    *,
    label: str = "",
    expires_in_hours: float = 24.0,
    capabilities: str = CAPABILITIES_DEFAULT,
) -> dict[str, Any]:
    """Mint a remote-control link. Returns raw token once."""
    if events.get_thread(thread_id) is None:
        raise LookupError("thread not found")
    raw = secrets.token_urlsafe(32)
    digest = hash_token(raw)
    expires_at = _iso(_now() + timedelta(hours=max(0.1, float(expires_in_hours))))
    with db.session() as connection:
        cursor = connection.execute(
            "INSERT INTO remote_links "
            "(thread_id, token_hash, capabilities, label, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (thread_id, digest, capabilities, label or "", expires_at),
        )
        link_id = int(cursor.lastrowid)
    return {
        "link_id": link_id,
        "thread_id": thread_id,
        "token": raw,
        "expires_at": expires_at,
        "capabilities": capabilities,
        "label": label or "",
    }


def revoke(link_id: int) -> dict[str, Any] | None:
    with db.session() as connection:
        row = connection.execute(
            "SELECT * FROM remote_links WHERE id = ?", (link_id,)
        ).fetchone()
        if row is None:
            return None
        connection.execute(
            "UPDATE remote_links SET revoked_at = ? WHERE id = ?",
            (_iso(_now()), link_id),
        )
    return {"link_id": link_id, "revoked": True}


def resolve(raw_token: str) -> dict[str, Any] | None:
    """Resolve a live link from the raw token, or None if dead."""
    digest = hash_token(raw_token)
    with db.session() as connection:
        row = connection.execute(
            "SELECT * FROM remote_links WHERE token_hash = ?", (digest,)
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        if data.get("revoked_at"):
            return None
        expires = _parse_iso(data.get("expires_at"))
        if expires is not None and expires <= _now():
            return None
        connection.execute(
            "UPDATE remote_links SET last_used_at = ? WHERE id = ?",
            (_iso(_now()), data["id"]),
        )
    return data


def pending_approval(thread_id: int) -> dict[str, Any] | None:
    """Last approval_required tool.result + matching tool.call args."""
    rows = list(events.since(f"thread:{thread_id}", limit=5_000))
    waiting_name = None
    detail = ""
    for row in reversed(rows):
        if row.get("kind") != "tool.result":
            continue
        payload = row.get("payload") or {}
        result = payload.get("result")
        if isinstance(result, dict) and result.get("error") == "approval_required":
            waiting_name = str(payload.get("name") or "")
            detail = str(result.get("detail") or "")
            break
        return None
    if not waiting_name:
        return None
    for row in reversed(rows):
        if row.get("kind") != "tool.call":
            continue
        payload = row.get("payload") or {}
        if str(payload.get("name") or "") == waiting_name:
            return {
                "name": waiting_name,
                "arguments": payload.get("arguments") or {},
                "detail": detail,
            }
    return {"name": waiting_name, "arguments": {}, "detail": detail}


def approve(thread_id: int, pending: dict[str, Any]) -> dict[str, Any]:
    name = str(pending.get("name") or "")
    arguments = pending.get("arguments") or {}
    if not name:
        raise ValueError("nothing waiting for approval")
    result = tools_registry.REGISTRY.call(
        name,
        arguments if isinstance(arguments, dict) else {},
        approved=True,
        actor=evidence.USER,
        thread_id=thread_id,
    )
    events.append(
        "tool.call",
        {
            "name": name,
            "arguments": arguments,
            "driven_by": "user",
            "via": "remote",
        },
        thread_id=thread_id,
    )
    events.append(
        "tool.result",
        {
            "name": name,
            "ok": True,
            "result": result,
            "driven_by": "user",
            "via": "remote",
        },
        thread_id=thread_id,
    )
    return {"ok": True, "name": name, "result": result}


def deny(thread_id: int, pending: dict[str, Any]) -> dict[str, Any]:
    name = str(pending.get("name") or "")
    events.append(
        "tool.result",
        {
            "name": name,
            "ok": False,
            "result": {
                "error": "declined",
                "detail": "declined from the remote control page",
            },
            "driven_by": "user",
            "via": "remote",
        },
        thread_id=thread_id,
    )
    return {"ok": True, "declined": True, "name": name}


def state(thread_id: int) -> dict[str, Any]:
    thread = events.get_thread(thread_id) or {}
    run = longrun.status(thread_id) or {}
    return {
        "thread_id": thread_id,
        "title": thread.get("title") or f"Thread {thread_id}",
        "run": run,
        "pending": pending_approval(thread_id),
    }


def page_html(raw_token: str, link: dict[str, Any]) -> str:
    snap = state(int(link["thread_id"]))
    pending = snap.get("pending")
    run = snap.get("run") or {}
    title = html.escape(str(snap.get("title") or "Remote control"))
    token_q = html.escape(raw_token)
    run_state = html.escape(str(run.get("state") or "idle"))
    detail = html.escape(str(run.get("detail") or run.get("stop_reason") or ""))
    body_parts = [
        f"<h1>Remote control</h1>",
        f"<p class='dim'>{title}</p>",
        f"<p>Run: <strong>{run_state}</strong>"
        + (f" — {detail}" if detail else "")
        + "</p>",
    ]
    if pending:
        name = html.escape(str(pending.get("name") or ""))
        why = html.escape(str(pending.get("detail") or ""))
        body_parts.append(
            f"<section class='glass'><h2>Approval needed</h2>"
            f"<p><code>{name}</code></p>"
            f"<p class='dim'>{why}</p>"
            f"<form method='post' action='/remote/{token_q}/approve'>"
            f"<button type='submit'>Approve</button></form> "
            f"<form method='post' action='/remote/{token_q}/deny' "
            f"style='display:inline'>"
            f"<button type='submit'>Deny</button></form></section>"
        )
    else:
        body_parts.append("<p class='dim'>Nothing is waiting for approval.</p>")
    body_parts.append(
        f"<form method='post' action='/remote/{token_q}/stop'>"
        f"<button type='submit'>Stop run</button></form>"
    )
    body_parts.append(
        "<p class='dim' style='margin-top:2rem'>This URL is a secret. "
        "Revoke it from the desktop app when finished.</p>"
    )
    return theme.page("Remote control — ML Harness", "\n".join(body_parts))


def is_remote_path(path: str) -> bool:
    return path.startswith("/remote/")
