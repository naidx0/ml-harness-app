"""`engine.json` has to say what the engine IS, not only where it is.

The file used to carry `base_url`, `host`, `pid`, `port` and `token`. Every one
of those is an address. On the evening this work comes from, five failures
chained off that gap - a `taskkill` on a pid that was not the server, a
replacement engine that died on `[Errno 10048]` into an unread log, a `/health`
that answered `ok` from the stale engine still holding the port, an interface
that reported no graphics card on a machine with an idle RTX 2060 SUPER, and a
browser tab that started 401ing because the token had rotated underneath it.

These tests are about the first half of the fix: the engine publishes an
identity, that identity is checkable, and the one thing the identity must never
carry is a secret.

`tests/test_health_means_the_right_engine.py` covers the second half - the
route that hands the same identity back over the socket and refuses to say `ok`
to a caller that meant a different engine.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import support

from app import identity, migrations, security


class TheIdentityIsOneThing(unittest.TestCase):
    """The portfile and the route must not be able to disagree."""

    def setUp(self):
        support.sandbox(self)

    def test_the_portfile_carries_the_identity_the_module_computes(self):
        """One source. Two writers of "what this engine is" would drift."""
        path = Path(tempfile.mkdtemp()) / "engine.json"
        security.write_portfile(port=8078, path=path)
        published = json.loads(path.read_text(encoding="utf-8"))

        expected = identity.identity()
        self.assertEqual(published["service"], expected["service"])
        self.assertEqual(published["portfile_version"], expected["portfile_version"])
        self.assertEqual(
            published["engine"]["engine_id"], expected["engine"]["engine_id"]
        )
        self.assertEqual(
            published["build"]["code_fingerprint"],
            expected["build"]["code_fingerprint"],
        )
        self.assertEqual(
            published["schema"]["build_knows"], expected["schema"]["build_knows"]
        )

    def test_the_old_five_fields_are_still_there(self):
        """Additive, not a rewrite.

        `frontend/vite.config.ts` reads `base_url` and `token` out of this file
        to proxy to the engine, `scripts/open_dashboard.py` reads the token,
        and `security.client_token` reads it for every local client. Adding
        identity must not cost any of them their field.
        """
        path = Path(tempfile.mkdtemp()) / "engine.json"
        security.write_portfile(port=8078, path=path)
        published = json.loads(path.read_text(encoding="utf-8"))
        for field in ("host", "port", "base_url", "token", "pid"):
            self.assertIn(field, published, f"{field} disappeared from the portfile")
        self.assertEqual(published["token"], security.current_token())
        self.assertEqual(published["pid"], os.getpid())

    def test_the_portfile_names_the_database_this_process_actually_opened(self):
        """Read at call time, not imported.

        `sandbox()` rebinds `db.DB_PATH`. A portfile written from inside a
        sandbox that named the user's real `ml_harness.db` would be a lie of
        precisely the kind this file exists to stop telling - and it would be
        one that a launcher then PRINTS to somebody as fact.
        """
        from app import db

        path = Path(tempfile.mkdtemp()) / "engine.json"
        security.write_portfile(port=8078, path=path)
        published = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(published["database"], str(db.DB_PATH))
        self.assertNotIn("ml_harness.db", published["database"])

    def test_the_engine_id_is_the_same_value_every_time_it_is_asked(self):
        """It is a name, not a reading. A name that changes names nothing."""
        self.assertEqual(
            identity.identity()["engine"]["engine_id"],
            identity.identity()["engine"]["engine_id"],
        )
        self.assertEqual(identity.ENGINE_ID, identity.identity()["engine"]["engine_id"])
        self.assertEqual(len(identity.ENGINE_ID), 32)


class NothingSecretTravelsWithTheIdentity(unittest.TestCase):
    """`/health` needs no token, so everything here is public to the machine."""

    def setUp(self):
        support.sandbox(self)

    def test_the_identity_payload_contains_no_token_anywhere(self):
        """Recursively, because a nested dict is how one gets in by accident."""
        blob = json.dumps(identity.identity())
        self.assertNotIn(security.current_token(), blob)
        for word in ("token", "secret", "api_key", "password"):
            self.assertNotIn(word, blob.lower(), f"{word!r} appears in the identity")

    def test_the_launch_nonce_is_not_treated_as_a_credential(self):
        """It is an identifier that anyone can read out of an open `/health`.

        Asserted here so that a later change which starts authorising anything
        on it has to delete a test that says not to.
        """
        self.assertFalse(security.token_matches(f"Bearer {identity.ENGINE_ID}"))
        nonce = identity.LAUNCH_NONCE or "whatever-a-launcher-chose"
        self.assertFalse(security.token_matches(f"Bearer {nonce}"))


class TheCodeFingerprintAnswersAmIRunningYourCode(unittest.TestCase):
    """The field a git sha cannot replace, and the reason it exists."""

    def _tree(self) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "sub").mkdir()
        (root / "a.py").write_text("print(1)\n", encoding="utf-8")
        (root / "sub" / "b.py").write_text("print(2)\n", encoding="utf-8")
        (root / "sub" / "prompt.md").write_text("be honest\n", encoding="utf-8")
        return root

    def test_an_edit_to_any_file_changes_it(self):
        root = self._tree()
        before, files = identity.code_fingerprint(root)
        (root / "sub" / "b.py").write_text("print(3)\n", encoding="utf-8")
        after, _ = identity.code_fingerprint(root)
        self.assertEqual(files, 3)
        self.assertNotEqual(before, after)

    def test_an_edit_to_a_non_python_file_changes_it_too(self):
        """The system prompt is `app/instructions/*.md`, and the model geometry
        every VRAM estimate uses is `app/model_configs/*.json`. A fingerprint
        over `*.py` only would report "same code" across a rewritten prime
        directive, which is the silent staleness this is here to catch.
        """
        root = self._tree()
        before, _ = identity.code_fingerprint(root)
        (root / "sub" / "prompt.md").write_text("be honest, twice\n", encoding="utf-8")
        self.assertNotEqual(before, identity.code_fingerprint(root)[0])

    def test_renaming_a_file_changes_it(self):
        """The path is hashed with the content. Two files that swap names have
        the same bytes and are not the same tree.
        """
        root = self._tree()
        before, _ = identity.code_fingerprint(root)
        (root / "a.py").rename(root / "z.py")
        self.assertNotEqual(before, identity.code_fingerprint(root)[0])

    def test_running_the_code_does_not_change_it(self):
        """`__pycache__` is derived from the very files being hashed. Counting
        it would make the fingerprint depend on whether the engine had been
        started yet, so two identical checkouts would disagree.
        """
        root = self._tree()
        before, files = identity.code_fingerprint(root)
        cache = root / "sub" / "__pycache__"
        cache.mkdir()
        (cache / "b.cpython-311.pyc").write_bytes(b"\x00compiled")
        (root / "a.pyc").write_bytes(b"\x00compiled")
        after, files_after = identity.code_fingerprint(root)
        self.assertEqual(before, after)
        self.assertEqual(files, files_after)

    def test_the_real_one_covers_the_whole_app_package(self):
        fingerprint, files = identity.code_fingerprint()
        self.assertEqual(len(fingerprint), 64)
        self.assertGreater(files, 40, "app/ has more files than this")
        self.assertEqual(fingerprint, identity.code_fingerprint()[0], "not cached")


class TheGitReadingSaysWhereItCameFrom(unittest.TestCase):
    """A sha with no `source` invites the reader to invent a reason for a null."""

    def _repo(self, head: str, refs: dict[str, str] | None = None) -> Path:
        root = Path(tempfile.mkdtemp())
        git = root / ".git"
        (git / "refs" / "heads").mkdir(parents=True)
        (git / "HEAD").write_text(head, encoding="utf-8")
        for ref, sha in (refs or {}).items():
            target = git / ref
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(sha + "\n", encoding="utf-8")
        return root

    def test_a_loose_ref(self):
        root = self._repo("ref: refs/heads/main\n", {"refs/heads/main": "a" * 40})
        self.assertEqual(identity.git_head(root), ("a" * 40, "git-ref"))

    def test_a_packed_ref(self):
        """A fresh clone keeps almost every ref packed. Checking only the loose
        file is how a sha reader works on the author's machine and comes back
        empty on somebody else's.
        """
        root = self._repo("ref: refs/heads/main\n")
        (root / ".git" / "packed-refs").write_text(
            "# pack-refs with: peeled fully-peeled sorted\n"
            f"{'b' * 40} refs/heads/main\n"
            f"^{'c' * 40}\n",
            encoding="utf-8",
        )
        self.assertEqual(identity.git_head(root), ("b" * 40, "git-ref"))

    def test_a_detached_head(self):
        """An agent lane checked out at a commit is in this state, so it is not
        an edge case in this repository.
        """
        root = self._repo("d" * 40 + "\n")
        self.assertEqual(identity.git_head(root), ("d" * 40, "git-head-detached"))

    def test_a_worktree_follows_its_pointer_file(self):
        """`.claude/worktrees/` exists in this repository, so an agent working
        in one must not get a null sha.
        """
        main = self._repo("ref: refs/heads/main\n", {"refs/heads/main": "e" * 40})
        worktree_git = main / ".git" / "worktrees" / "lane"
        worktree_git.mkdir(parents=True)
        (worktree_git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (worktree_git / "commondir").write_text("../..\n", encoding="utf-8")
        lane = Path(tempfile.mkdtemp())
        (lane / ".git").write_text(f"gitdir: {worktree_git}\n", encoding="utf-8")
        self.assertEqual(identity.git_head(lane), ("e" * 40, "git-ref"))

    def test_no_repository_says_so_rather_than_returning_nothing(self):
        root = Path(tempfile.mkdtemp())
        self.assertEqual(identity.git_head(root), (None, "not-a-git-checkout"))
        self.assertEqual(identity.git_dirty(root), (None, "not-a-git-checkout"))

    def test_dirty_is_never_false_when_it_was_not_checked(self):
        """`False` is a claim that the tree is clean. `None` is the truth when
        nothing looked.
        """
        dirty, source = identity.git_dirty(Path(tempfile.mkdtemp()))
        self.assertIsNone(dirty)
        self.assertNotEqual(source, "git-status")

    def test_asking_git_does_not_write_to_the_users_repository(self):
        """`--no-optional-locks` is load-bearing, not tidy.

        A plain `git status` REFRESHES THE INDEX, which is a write into the
        user's repository performed by a process that was only asked a
        question. The engine calls this at startup.
        """
        source = Path(identity.__file__).read_text(encoding="utf-8")
        self.assertIn("--no-optional-locks", source)
        self.assertIn("--untracked-files=no", source)

    def test_the_real_repository_answers_with_a_real_sha(self):
        sha, source = identity.git_head()
        if source == "not-a-git-checkout":
            self.skipTest("this checkout has no .git")
        self.assertIsNotNone(sha)
        self.assertEqual(len(sha), 40)
        confirmed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(identity.REPO_ROOT),
            capture_output=True,
            text=True,
        )
        if confirmed.returncode == 0:
            self.assertEqual(sha, confirmed.stdout.strip())


class TheSchemaVersionIsAPropertyOfTheBuild(unittest.TestCase):
    """An engine that knew 8 met a database at 9 and 500'd every request."""

    def test_it_is_the_highest_migration_this_build_ships(self):
        self.assertEqual(
            identity.known_schema_version(), migrations.MIGRATIONS[-1][0]
        )

    def test_it_does_not_read_the_database(self):
        """Deliberately. It cannot change while this process is alive, which is
        what makes it part of an identity rather than a reading - and it has to
        be answerable by an engine whose database will not open, which is
        exactly the case worth reporting.
        """
        from app import db

        previous = db.DB_PATH
        db.DB_PATH = Path(tempfile.mkdtemp()) / "does-not-exist" / "no.db"
        try:
            self.assertEqual(
                identity.known_schema_version(), migrations.MIGRATIONS[-1][0]
            )
        finally:
            db.DB_PATH = previous


class TheLaunchNonceComesFromWhoeverStartedUs(unittest.TestCase):
    """A pid does not survive the trip between a parent and its child.

    Measured on the machine this product is built on: `Popen(...).pid` was
    12468 while the server it started logged `Started server process [25392]`,
    because the venv's `python.exe` re-execs. A nonce the child carries in its
    own environment is not vulnerable to that, or to pid recycling, or to any
    other layer between a parent and the code it meant to run.
    """

    def test_it_is_read_from_the_environment(self):
        source = Path(identity.__file__).read_text(encoding="utf-8")
        self.assertIn('os.environ.get("MLH_LAUNCH_NONCE")', source)

    def test_it_is_none_when_nobody_set_one(self):
        """`None`, not `""`. An empty string would match an empty expectation
        and let a caller that stated nothing be told it was right.
        """
        self.assertIsNone(identity.LAUNCH_NONCE or None)
        self.assertIn("launch_nonce", identity.engine())

    def test_a_child_reports_the_nonce_it_was_given(self):
        """End to end through a real subprocess, because the whole point is
        that the value survives process creation.
        """
        environment = dict(os.environ)
        environment["MLH_LAUNCH_NONCE"] = "a-value-the-parent-chose"
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from app import identity; print(identity.engine()['launch_nonce'])",
            ],
            cwd=str(identity.REPO_ROOT),
            env=environment,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "a-value-the-parent-chose")


class WhenThePortfileIsNotPublishedSomebodyIsTold(unittest.TestCase):
    """Silence was half of the 401 mystery.

    `write_portfile` correctly declines to overwrite a file that belongs to a
    live process. It used to do that without saying anything, so a second
    engine could start, serve on a token no client had, and leave nothing
    anywhere to explain the 401s that followed.
    """

    def setUp(self):
        support.sandbox(self)

    def _incumbent(self, path: Path, **fields) -> dict:
        """Plant a portfile for a live pid whose engine really answers.

        Since 2026-09-23 a live pid alone does not make the guard defer (see
        test_a_live_pid_is_not_a_live_engine.py): the engine the file names
        has to answer `/health` with the file's `engine_id`. So the incumbent
        here is a tiny HTTP server this test owns, answering with the id the
        real `write_portfile` minted, and the file's `base_url` points at it.
        """
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        security.write_portfile(port=8078, path=path)
        live = json.loads(path.read_text(encoding="utf-8"))
        engine_id = live["engine"]["engine_id"]

        class Health(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - the stdlib's spelling
                body = json.dumps({"engine": {"engine_id": engine_id}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass

        server = HTTPServer(("127.0.0.1", 0), Health)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        planted = {
            **live,
            "pid": os.getppid(),
            "base_url": f"http://127.0.0.1:{server.server_address[1]}",
            **fields,
        }
        path.write_text(json.dumps(planted), encoding="utf-8")
        return planted

    def test_a_deferral_with_a_different_token_is_announced(self):
        import io
        import contextlib

        path = Path(tempfile.mkdtemp()) / "engine.json"
        self._incumbent(path, token="somebody-elses")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            security.write_portfile(port=8078, path=path)
        said = stderr.getvalue()
        self.assertIn("did NOT publish its token", said)
        self.assertIn(str(os.getppid()), said)
        self.assertNotIn(
            security.current_token(), said, "the warning must not leak the token"
        )
        self.assertEqual(
            json.loads(path.read_text(encoding="utf-8"))["token"], "somebody-elses"
        )

    def test_a_deferral_to_the_same_token_is_silent(self):
        """A launcher that pinned `MLH_TOKEN` for both processes produces this,
        and it is the arrangement working rather than a collision.
        """
        import io
        import contextlib

        path = Path(tempfile.mkdtemp()) / "engine.json"
        planted = self._incumbent(path)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            security.write_portfile(port=8078, path=path)
        self.assertEqual(stderr.getvalue(), "")
        # Silent because it deferred, not because it overwrote: the planted
        # file, with the parent's pid, is still the one on disk.
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["pid"], planted["pid"])


if __name__ == "__main__":
    unittest.main()
