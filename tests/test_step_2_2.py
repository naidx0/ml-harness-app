import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app import db
from app.main import app
from app import client
from app import feasibility
from app import hwdetect
from app import plan

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

    def test_generated_step(self):
        """Updated: the three arithmetic cases now say where their VRAM came from.

        This test asserted that a bare `8.0` yields a confident verdict. That is
        the defect Ruling 6 exists to close - a bare float cannot say whether it
        was read off a GPU or made up, and the hardcoded-8.0 bug shipped exactly
        because nothing forced it to. The arithmetic is unchanged and still
        pinned here; the inputs now carry provenance.
        """
        vram = feasibility.measured(8.0, "nvidia-smi")

        self.assertEqual(feasibility.verdict(vram, 2.0, 2.0)['verdict'], 'FITS')
        self.assertEqual(feasibility.verdict(vram, 4.19, 3.5)['verdict'], 'SPILLS')
        self.assertEqual(feasibility.verdict(vram, 9.0, 3.0)['verdict'], 'WONT_FIT')

    def test_a_bare_number_nobody_vouched_for_is_UNKNOWN(self):
        """The type-level fix. Reverting it makes this go red."""
        for weights, kv in ((2.0, 2.0), (4.19, 3.5), (9.0, 3.0)):
            with self.subTest(weights=weights):
                result = feasibility.verdict(8.0, weights, kv)

                self.assertEqual(result['verdict'], 'UNKNOWN')
                self.assertEqual(result['vram_provenance'], 'defaulted')
                self.assertEqual(result['missing'], 'hardware')

    def test_a_defaulted_hardware_field_is_UNKNOWN_not_a_verdict(self):
        defaulted = feasibility.Field(8.0, "defaulted", "fallback constant")

        self.assertEqual(feasibility.verdict(defaulted, 2.0, 2.0)['verdict'], 'UNKNOWN')

    def test_an_untested_platform_reading_is_UNKNOWN(self):
        # Ruling 7: a reading from a code path never run on this platform is
        # best-effort, and best-effort is not a verdict.
        untested = feasibility.Field(8.0, "untested_on_this_platform", "sysctl")

        self.assertEqual(feasibility.verdict(untested, 2.0, 2.0)['verdict'], 'UNKNOWN')

    def test_an_unread_config_json_is_UNKNOWN_not_a_guess(self):
        result = feasibility.verdict(feasibility.measured(8.0), 2.0, None)

        self.assertEqual(result['verdict'], 'UNKNOWN')
        self.assertEqual(result['missing'], 'geometry')

    def test_WONT_FIT_survives_an_unread_config_json_when_the_weights_alone_blow_the_card(self):
        # We do not need the KV term to know that 9 GB of weights will not fit
        # on 8 GB, and refusing to say so would be its own dishonesty.
        result = feasibility.verdict(feasibility.measured(8.0), 9.0, None)

        self.assertEqual(result['verdict'], 'WONT_FIT')

    def test_the_declared_provenance_of_a_typed_in_profile_still_answers(self):
        declared = feasibility.declared(24.0, "POST /hardware")

        self.assertEqual(feasibility.verdict(declared, 2.0, 2.0)['verdict'], 'FITS')

    def test_there_are_exactly_four_verdicts(self):
        self.assertEqual(
            set(feasibility.VERDICTS), {"FITS", "SPILLS", "WONT_FIT", "UNKNOWN"}
        )
