import re
import unittest
from pathlib import Path

from app.config import DEFAULT_PORT


class PortAlignmentTest(unittest.TestCase):
    def test_readme_uvicorn_port_matches_default(self):
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
        match = re.search(r"\buvicorn\s+app\.main:app\b[^\r\n]*?--port\s+(\d+)\b", readme)

        self.assertIsNotNone(match, "README must document the uvicorn --port value")
        self.assertEqual(int(match.group(1)), DEFAULT_PORT)


if __name__ == "__main__":
    unittest.main()
