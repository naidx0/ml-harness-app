"""The `/api` surface for projects, and for a thread that can move between them.

`docs/ROADMAP.md` step 1.12 landed the thread and provider halves and left the
project half open, because it needs step 1.3. This is that half, plus the four
verbs the rail actually needs: list, create, rename, archive, and move a thread
from one project to another.

Three properties, none of which is "the route returns 200":

**Every mutation appends to the event log.** The spine is what makes a second
window redraw itself. A rename that changes the database and not the log is
invisible to every client except the one that asked for it, and the rail is
the surface where that shows up first.

**A missing row is a 404 that says which row.** `POST /api/threads/1/move`
against a project that does not exist must not surface as an `IntegrityError`
and a 500; the endpoint looks both rows up before it writes anything.

**Nothing here can be reached without the token.** Not asserted again in this
file - `tests/test_security_boundary.py` owns that, and it checks the policy
rather than a list of paths, so these routes are covered by it the moment they
exist. Said here so the absence is deliberate rather than forgotten.
"""

from __future__ import annotations

import unittest

from app import db, events

import support


class ProjectApiTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        from app.main import app

        self.client = support.api_client(app)
        self.addCleanup(self.client.close)

    def kinds(self) -> list[str]:
        with db.session() as connection:
            return [
                row[0] for row in connection.execute("SELECT kind FROM events ORDER BY id")
            ]

    def test_a_project_is_created_listed_renamed_and_archived(self):
        # An ABSOLUTE path on this machine: `/tmp/x` is relative on Windows
        # (no drive), and since dae6605 a project's root must be absolute -
        # which is what this test then relies on the engine to keep.
        created = self.client.post(
            "/api/projects",
            json={"name": "Support triage", "root_path": str(self.root / "x")},
        )
        self.assertEqual(created.status_code, 201)
        project_id = created.json()["id"]
        self.assertEqual(created.json()["portal"], "consumer")

        listed = self.client.get("/api/projects").json()
        self.assertEqual([p["id"] for p in listed], [project_id])

        renamed = self.client.post(
            f"/api/projects/{project_id}/rename", json={"name": "Renamed"}
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()["name"], "Renamed")

        second = self.client.post("/api/projects", json={"name": "Second"}).json()
        archived = self.client.post(f"/api/projects/{second['id']}/archive")
        self.assertEqual(archived.status_code, 200)
        self.assertIsNotNone(archived.json()["archived_at"])
        self.assertEqual(
            [p["id"] for p in self.client.get("/api/projects").json()], [project_id]
        )
        self.assertEqual(
            len(self.client.get("/api/projects?include_archived=true").json()), 2
        )

        self.assertEqual(
            self.kinds(),
            [
                "project.created",
                "project.renamed",
                "project.created",
                "project.archived",
            ],
            "every mutation belongs on the spine or no other window sees it",
        )

    def test_the_last_project_cannot_be_archived_and_says_so(self):
        project_id = self.client.post("/api/projects", json={"name": "only"}).json()["id"]
        refused = self.client.post(f"/api/projects/{project_id}/archive")
        self.assertEqual(refused.status_code, 409)
        self.assertIn("last project", refused.json()["detail"])

    def test_missing_projects_are_404_not_500(self):
        self.assertEqual(
            self.client.post("/api/projects/99999/rename", json={"name": "x"}).status_code,
            404,
        )
        self.assertEqual(
            self.client.post("/api/projects/99999/archive").status_code, 404
        )

    def test_a_portal_that_is_neither_product_is_refused(self):
        resp = self.client.post(
            "/api/projects", json={"name": "x", "portal": "freemium"}
        )
        self.assertEqual(resp.status_code, 422)

    def test_a_new_thread_lands_in_the_default_project(self):
        thread = self.client.post("/api/threads", json={"title": "t"}).json()
        self.assertEqual(thread["project_id"], db.default_project()["id"])

    def test_a_thread_can_be_created_in_a_named_project(self):
        project_id = self.client.post("/api/projects", json={"name": "p"}).json()["id"]
        thread = self.client.post(
            "/api/threads", json={"title": "t", "project_id": project_id}
        ).json()
        self.assertEqual(thread["project_id"], project_id)
        self.assertEqual(
            [t["id"] for t in self.client.get(f"/api/threads?project_id={project_id}").json()],
            [thread["id"]],
        )
        self.assertEqual(
            self.client.post(
                "/api/threads", json={"title": "t", "project_id": 99999}
            ).status_code,
            404,
        )

    def test_a_thread_moves_between_projects_and_the_move_is_on_the_spine(self):
        source = self.client.post("/api/threads", json={"title": "t"}).json()
        destination = self.client.post("/api/projects", json={"name": "dest"}).json()

        moved = self.client.post(
            f"/api/threads/{source['id']}/move", json={"project_id": destination["id"]}
        )
        self.assertEqual(moved.status_code, 200)
        self.assertEqual(moved.json()["project_id"], destination["id"])

        payloads = [
            row["payload"]
            for row in events.since(f"thread:{source['id']}")
            if row["kind"] == "thread.moved"
        ]
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["from_project_id"], source["project_id"])
        self.assertEqual(payloads[0]["to_project_id"], destination["id"])

    def test_moving_to_a_project_that_is_not_there_is_a_404(self):
        thread = self.client.post("/api/threads", json={"title": "t"}).json()
        resp = self.client.post(
            f"/api/threads/{thread['id']}/move", json={"project_id": 99999}
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["detail"], "project not found")

        resp = self.client.post(
            "/api/threads/99999/move", json={"project_id": db.default_project()["id"]}
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["detail"], "thread not found")

    def test_a_thread_is_renamed_and_archived_over_http(self):
        thread = self.client.post("/api/threads", json={"title": "t"}).json()
        renamed = self.client.post(
            f"/api/threads/{thread['id']}/rename", json={"title": "Renamed"}
        )
        self.assertEqual(renamed.json()["title"], "Renamed")

        archived = self.client.post(f"/api/threads/{thread['id']}/archive")
        self.assertIsNotNone(archived.json()["archived_at"])
        self.assertEqual(self.client.get("/api/threads").json(), [])
        self.assertEqual(
            self.client.get(f"/api/threads/{thread['id']}").status_code,
            200,
            "an archived thread is still readable - archiving is not deletion",
        )
        self.assertEqual(
            self.client.post("/api/threads/99999/rename", json={"title": "x"}).status_code,
            404,
        )
        self.assertEqual(
            self.client.post("/api/threads/99999/archive").status_code, 404
        )

    def test_an_empty_title_or_name_is_refused(self):
        self.assertEqual(
            self.client.post("/api/projects", json={"name": ""}).status_code, 422
        )
        thread = self.client.post("/api/threads", json={"title": "t"}).json()
        self.assertEqual(
            self.client.post(
                f"/api/threads/{thread['id']}/rename", json={"title": ""}
            ).status_code,
            422,
        )


if __name__ == "__main__":
    unittest.main()
