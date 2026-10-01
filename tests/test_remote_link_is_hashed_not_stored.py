"""CS2: remote Approve + Stop links store a hash, never the raw token."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import db, events, remote, security  # noqa: E402


class RemoteLinkTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)

    def test_raw_token_never_lands_in_sqlite(self) -> None:
        tid = events.create_thread("remote")["id"]
        minted = remote.create_link(tid, expires_in_hours=1)
        raw = minted["token"]
        self.assertTrue(raw)
        with db.session() as connection:
            blob = connection.execute(
                "SELECT token_hash FROM remote_links WHERE id = ?",
                (minted["link_id"],),
            ).fetchone()["token_hash"]
        self.assertNotEqual(blob, raw)
        self.assertEqual(blob, remote.hash_token(raw))
        data = Path(db.DB_PATH).read_bytes()
        self.assertNotIn(raw.encode("utf-8"), data)

    def test_resolve_rejects_revoked_and_unknown(self) -> None:
        tid = events.create_thread("remote revoke")["id"]
        minted = remote.create_link(tid)
        self.assertIsNotNone(remote.resolve(minted["token"]))
        remote.revoke(minted["link_id"])
        self.assertIsNone(remote.resolve(minted["token"]))
        self.assertIsNone(remote.resolve("not-a-real-token"))

    def test_engine_bearer_not_required_on_remote_paths(self) -> None:
        self.assertFalse(security.requires_token("GET", "/remote/abc"))
        self.assertFalse(security.requires_token("POST", "/remote/abc/stop"))
        self.assertTrue(security.requires_token("POST", "/api/threads/1/remote_link"))

    def test_deny_writes_declined_result(self) -> None:
        tid = events.create_thread("remote deny")["id"]
        events.append(
            "tool.result",
            {
                "name": "start_training",
                "ok": False,
                "result": {"error": "approval_required", "detail": "needs a yes"},
            },
            thread_id=tid,
        )
        pending = remote.pending_approval(tid)
        self.assertIsNotNone(pending)
        remote.deny(tid, pending or {})
        rows = list(events.since(f"thread:{tid}", limit=100))
        last = rows[-1]
        self.assertEqual(last["kind"], "tool.result")
        self.assertEqual((last["payload"] or {}).get("result", {}).get("error"), "declined")


if __name__ == "__main__":
    unittest.main()
