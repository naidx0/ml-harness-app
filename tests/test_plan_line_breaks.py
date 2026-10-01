"""Guard: the plan's single-newline fields must not collapse into one line.

app/plan.py separates the model from its verdict, and Goal from Method from
Quantization, with single newlines. Markdown treats a single newline as a soft
break and joins those lines into one paragraph, so the rendered page read:

    Goal: Fine-tune a small image classifier on my RTX 2060 SUPER Method: QLoRA
    Quantization: Q4

Three separate facts run together. Every DOM assertion passed the whole time -
the strings were all present, just not separated. Only a screenshot caught it.
"""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.main import app

import support


class PlanLineBreaksTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp.name) / "breaks.db"
        db.init_db()
        self.client = support.api_client(app)
        # A hardware profile, so the page has real numbers to lay out. Without
        # one the VRAM figure is defaulted, the verdict is UNKNOWN and the
        # memory line renders em dashes - honest, but nothing to test spacing
        # against. The goal is text so the panel still names a language model,
        # which is what the "model above the memory line" assertion is about.
        db.create_hardware_profile(
            gpu_name="RTX 2060 SUPER", vram_gb=8.0, ram_gb=16.0,
            os="Windows 11", disk_free_gb=702.5,
        )
        db.create_intake(
            "breaks",
            {
                "goal": "Fine-tune a small text classifier",
                "dataset_size": "12000",
                "data_kind": "Text",
            },
        )
        self.body = self.client.get("/ui/plan/breaks").text

    def tearDown(self):
        self.client.close()
        try:
            self.temp.cleanup()
        except (PermissionError, OSError):
            pass

    def _between(self, first: str, second: str) -> str:
        """The markup sitting between two rendered fields."""
        start = self.body.index(first) + len(first)
        return self.body[start:self.body.index(second, start)]

    def test_goal_method_and_quantization_are_separated(self):
        self.assertIn("<br", self._between("Goal:", "Method:"))
        self.assertIn("<br", self._between("Method:", "Quantization:"))

    def test_the_panel_separates_model_from_the_memory_line(self):
        # The model and the memory summary share the panel's summary paragraph
        # and are separated the same way.
        self.assertIn("<br", self._between("Qwen3-4B", "GB needed"))

    def test_the_fields_are_all_still_present(self):
        # "verdict:" is deliberately no longer in the HTML view. The label was
        # dropped when the duplicate summary paragraph was removed and the pill
        # stopped restating its own context - the verdict VALUE is what has to
        # survive, and it does. The plaintext /plan route still carries the
        # "verdict:" label; tests/test_plan_hierarchy.py asserts that.
        #
        # Updated: the fourth field was "SPILLS", which every plan on every
        # machine for every goal returned, because the page computed it from the
        # literals 8.0 / 4.19 / 3.5. With those gone the verdict on this fixture
        # is UNKNOWN: the VRAM is real, but no config.json has been read for
        # Qwen3-4B, so the KV-cache term cannot be sized and the product says so
        # instead of inventing it.
        for field in ("Goal:", "Method:", "Quantization:", "UNKNOWN"):
            self.assertIn(field, self.body)


if __name__ == "__main__":
    unittest.main()
