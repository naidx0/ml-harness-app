"""viewport_smoke: parse the runner verdict out of a Chromium --dump-dom body."""

from __future__ import annotations

import unittest
from pathlib import Path

from scripts.viewport_smoke import VIEWPORTS, find_browser, verdict_from_dom

REPO = Path(__file__).resolve().parents[1]


class ViewportSmokeVerdict(unittest.TestCase):
    def test_green_line_is_green(self):
        dom = (
            '<html><body><pre id="viewport-smoke-verdict">'
            "GREEN: no horizontal overflow at 820/1024/1280/1600\n"
            "  820px  OK"
            "</pre></body></html>"
        )
        status, detail = verdict_from_dom(dom)
        self.assertEqual(status, "GREEN")
        self.assertTrue(detail.startswith("GREEN"))

    def test_red_line_is_red(self):
        dom = (
            '<html><body><pre id="viewport-smoke-verdict">'
            "RED: overflow at 820px\n"
            "  820px  OVERFLOW"
            "</pre></body></html>"
        )
        status, detail = verdict_from_dom(dom)
        self.assertEqual(status, "RED")
        self.assertIn("820", detail)

    def test_missing_verdict_is_missing(self):
        status, _ = verdict_from_dom("<html><body>nothing</body></html>")
        self.assertEqual(status, "MISSING")

    def test_runner_and_specimen_exist(self):
        drafts = REPO / "docs" / "brand" / "drafts"
        self.assertTrue((drafts / "viewport-runner.html").is_file())
        self.assertTrue((drafts / "composer-three-paths.html").is_file())
        self.assertEqual(VIEWPORTS, (820, 1024, 1280, 1600))

    def test_find_browser_returns_path_or_none(self):
        found = find_browser()
        self.assertTrue(found is None or found.is_file())


if __name__ == "__main__":
    unittest.main()
