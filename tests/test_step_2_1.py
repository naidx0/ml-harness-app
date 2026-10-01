import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app import db
from app.main import app
from app import client
from app import feasibility
from app import hwdetect

import support



class GeneratedStepTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp.name) / "test.db"
        db.init_db()
        self.client = support.api_client(app)

    def tearDown(self):
        self.client.close()
        # Windows refuses to unlink a sqlite file while any connection is still
        # open, and a lingering connection in product code should not fail an
        # otherwise-passing test. Leaking a temp dir is the lesser evil.
        try:
            self.temp.cleanup()
        except (PermissionError, OSError):
            pass

    # Llama-3-8B's geometry, which the old estimator hardcoded as
    # `2 * 32 * 8 * 128` and applied to every model from 270M to 27B.
    # docs/ROADMAP.md names those numbers as Llama-3-8B's; they are here as an
    # argument now, which is the whole point.
    LLAMA3_8B = feasibility.ModelGeometry(
        num_hidden_layers=32, num_key_value_heads=8, head_dim=128
    )
    # A model with a different shape. Nothing about it is claimed except that it
    # is not the geometry above.
    OTHER_SHAPE = feasibility.ModelGeometry(
        num_hidden_layers=16, num_key_value_heads=4, head_dim=64
    )

    def test_generated_step(self):
        """Updated: this test asserted two defects as if they were the spec.

        It asserted `weights_gb == 4.19` for a 9B model at Q4, which is 0.5
        bytes per parameter - 4.0 bits. Real Q4_K_M is 4.91 bits, 0.61 bytes
        (docs/ARCHITECTURE.md 4.7). The old constant understated the weights by
        about 21%, in the direction that tells a user something fits when it
        will OOM, so the old number is not one to preserve.

        It also asserted `kv_gb == 4.0` for a 9B model computed from Llama-3-8B's
        geometry, which was only true because the geometry was hardcoded. The
        geometry is now supplied, and the same call without it returns None.
        """
        estimate = feasibility.estimate_vram(
            9.0, "Q4", 65536, "q8_0", geometry=self.LLAMA3_8B
        )
        # 9e9 params x 4.91 bits / 8 / 2**30.
        self.assertAlmostEqual(estimate["weights_gb"], 5.14, delta=0.02)
        # The old hardcoded term, now reachable only by passing that geometry.
        self.assertAlmostEqual(estimate["kv_gb"], 4.0, delta=0.5)

    def test_a_different_architecture_gets_a_different_kv_figure(self):
        """The single-architecture assumption, stated as a test.

        A 0.5B and a 27B model used to get the same cache figure.
        """
        wide = feasibility.estimate_vram(
            9.0, "Q4", 65536, "q8_0", geometry=self.LLAMA3_8B
        )
        narrow = feasibility.estimate_vram(
            9.0, "Q4", 65536, "q8_0", geometry=self.OTHER_SHAPE
        )

        self.assertNotAlmostEqual(wide["kv_gb"], narrow["kv_gb"], delta=0.5)
        # 32*8*128 over 16*4*64 is a factor of eight.
        self.assertAlmostEqual(wide["kv_gb"] / narrow["kv_gb"], 8.0, delta=0.05)

    def test_without_geometry_the_kv_term_is_absent_rather_than_borrowed(self):
        estimate = feasibility.estimate_vram(9.0, "Q4", 65536, "q8_0")

        self.assertIsNone(estimate["kv_gb"])
        self.assertEqual(estimate["geometry_provenance"], "defaulted")
        self.assertIsNone(estimate["total_gb"])

    def test_the_overhead_terms_the_old_estimator_omitted_entirely(self):
        estimate = feasibility.estimate_vram(
            9.0, "Q4", 65536, "q8_0", geometry=self.LLAMA3_8B
        )

        # 0.75 GB of CUDA context plus 0.5 GB of desktop reserve.
        self.assertAlmostEqual(estimate["overhead_gb"], 1.25, delta=0.001)
        self.assertGreater(estimate["total_gb"], estimate["weights_gb"] + estimate["kv_gb"])
