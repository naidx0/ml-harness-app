import unittest

from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.theme import GLASS_CSS, page

import support


class ThemeTest(unittest.TestCase):
    def test_glass_has_inset_highlight(self):
        self.assertIn("0 1px 0 var(--edge-2) inset", GLASS_CSS)

    def test_theme_has_no_external_urls(self):
        self.assertNotIn("http://", GLASS_CSS)
        self.assertNotIn("https://", GLASS_CSS)

    def test_page_is_complete_and_escapes_title(self):
        rendered = page("A & B", "<p>x</p>")

        self.assertTrue(rendered.lower().startswith("<!doctype html"))
        self.assertIn("<title>A &amp; B</title>", rendered)
        self.assertIn("<p>x</p>", rendered)

    def test_plan_page_has_verdict_pill_and_budget(self):
        """`with TestClient(app)` runs the app's LIFESPAN, and that writes.

        `app.main.lifespan` calls `security.write_portfile()` with no path, so
        entering the client republishes the repository's real `engine.json` -
        the file the launcher, the CLI client and every local tool read the
        engine's port and BEARER TOKEN from. This was the only test in the
        suite that entered a lifespan, so it was the only one that did it, and
        nothing in 1057 tests reported it: the database guard watches SQLite,
        and this is a JSON file.

        `support.sandbox()` binds `security.ENGINE_FILE` along with the
        database, so the portfile the lifespan publishes lands in this test's
        temporary directory. Nothing else about the test changes.
        """
        support.sandbox(self)
        db.create_intake("glass-plan", {"goal": "fine-tune"})

        with TestClient(app) as client:
            response = client.get("/ui/plan/glass-plan")

        self.assertEqual(response.status_code, 200)
        self.assertIn('class="vpill', response.text)
        self.assertIn('class="budget"', response.text)


if __name__ == "__main__":
    unittest.main()
