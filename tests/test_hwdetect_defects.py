"""Regression tests for the two verified defects in app/hwdetect.py.

1. `local_specs()` reported free disk space in the `ram_gb` field. Both numbers
   came from one `shutil.disk_usage("/").free` call, so a machine with 16 GB of
   RAM reported 702.5 GB of it.
2. `parse_nvidia_smi()` had no caller and its router was never mounted, so the
   running product never learned what GPU was present.

The RAM test mocks both sources so it fails on any machine if the fix is
reverted, rather than only on one where the two numbers happen to differ.
"""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import db, hwdetect
from app.main import app

import support

GIB = 1024 ** 3

SMI_LINE = "NVIDIA GeForce RTX 2060 SUPER, 8192 MiB\n"


def fake_smi(*_args, **_kwargs):
    return SimpleNamespace(returncode=0, stdout=SMI_LINE, stderr="")


def absent_smi(*_args, **_kwargs):
    raise FileNotFoundError("nvidia-smi")


class RamIsNotFreeDiskTest(unittest.TestCase):
    def test_ram_is_read_from_memory_not_from_the_disk(self):
        with patch.object(
            hwdetect, "physical_ram_bytes",
            return_value=(16 * GIB, "measured", "kernel32.GlobalMemoryStatusEx"),
        ), patch.object(
            hwdetect.shutil, "disk_usage",
            return_value=SimpleNamespace(total=1000 * GIB, used=298 * GIB, free=702 * GIB),
        ):
            specs = hwdetect.local_specs(runner=absent_smi)

        # The exact shape of the defect: this used to be 702.0.
        self.assertAlmostEqual(specs["ram_gb"], 16.0, delta=0.05)
        self.assertAlmostEqual(specs["disk_free_gb"], 702.0, delta=0.05)
        self.assertNotEqual(specs["ram_gb"], specs["disk_free_gb"])

    def test_the_two_fields_name_two_different_sources(self):
        specs = hwdetect.local_specs(runner=absent_smi)

        self.assertNotEqual(specs["sources"]["ram_gb"], specs["sources"]["disk_free_gb"])

    def test_unreadable_ram_is_reported_as_unknown_not_as_a_constant(self):
        with patch.object(hwdetect, "_windows_physical_ram_bytes", return_value=None), \
             patch.object(hwdetect, "_posix_physical_ram_bytes", return_value=None), \
             patch.object(hwdetect, "_darwin_physical_ram_bytes", return_value=None):
            specs = hwdetect.local_specs(runner=absent_smi)

        self.assertIsNone(specs["ram_gb"])
        self.assertEqual(specs["provenance"]["ram_gb"], "defaulted")

    def test_an_untested_platform_says_so_in_the_provenance(self):
        # Ruling 7: no blocking claim about hardware the owner cannot test on.
        with patch.object(hwdetect, "_darwin_physical_ram_bytes", return_value=32 * GIB):
            total, provenance, _source = hwdetect.physical_ram_bytes("Darwin")

        self.assertEqual(total, 32 * GIB)
        self.assertEqual(provenance, "untested_on_this_platform")


class NvidiaSmiHasACallerTest(unittest.TestCase):
    def test_local_specs_actually_runs_nvidia_smi(self):
        calls = []

        def recording(argv, **kwargs):
            calls.append(argv)
            return fake_smi()

        specs = hwdetect.local_specs(runner=recording)

        self.assertEqual(len(calls), 1)
        # argv[0] is the RESOLVED nvidia-smi, not the bare name. Pinned to the
        # module's own resolver, so this stays as strict as the bare-name
        # assertion it replaces: a resolver that started returning something
        # else fails here, and the stem check fails if it returns another
        # program entirely.
        self.assertEqual(calls[0][0], hwdetect._nvidia_smi_path())
        self.assertEqual(Path(calls[0][0]).stem.lower(), "nvidia-smi")
        self.assertEqual(list(calls[0][1:]), hwdetect.NVIDIA_SMI_ARGV[1:])
        self.assertEqual(specs["gpu_name"], "NVIDIA GeForce RTX 2060 SUPER")
        self.assertAlmostEqual(specs["vram_gb"], 8.0)
        self.assertEqual(specs["provenance"]["vram_gb"], "measured")

    def test_the_binary_is_resolved_because_the_engine_path_is_not_the_shell_path(self):
        """The defect this replaced the bare name to fix.

        ``nvidia-smi`` answered instantly in a terminal while ``GET
        /local_specs`` returned ``gpu_name: null`` on the same machine, at the
        same moment, with the card idle. A bare name is resolved against the
        CALLER's PATH, and the engine's is not the shell's.
        """
        with patch.object(hwdetect.shutil, "which", return_value="/opt/bin/nvidia-smi"):
            self.assertEqual(hwdetect._nvidia_smi_path(), "/opt/bin/nvidia-smi")

    def test_a_machine_with_no_driver_falls_back_to_the_bare_name_not_a_guess(self):
        """Resolution can turn a false negative into a reading. It can never
        turn a missing card into one: ``which`` returning ``None`` leaves the
        bare name, which fails exactly as it did before."""
        with patch.object(hwdetect.shutil, "which", return_value=None):
            self.assertEqual(hwdetect._nvidia_smi_path(), "nvidia-smi")

    def test_a_machine_with_no_nvidia_driver_gets_none_not_a_default(self):
        specs = hwdetect.local_specs(runner=absent_smi)

        self.assertIsNone(specs["gpu_name"])
        self.assertIsNone(specs["vram_gb"])
        self.assertEqual(specs["provenance"]["vram_gb"], "defaulted")
        self.assertTrue(any("nvidia-smi" in w for w in specs["warnings"]))

    def test_a_failing_nvidia_smi_is_not_parsed_as_a_reading(self):
        def failing(*_args, **_kwargs):
            return SimpleNamespace(returncode=9, stdout="garbage", stderr="boom")

        self.assertIsNone(hwdetect.read_nvidia_smi(failing))


class LocalSpecsRouteIsMountedTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp.name) / "specs.db"
        db.init_db()
        self.client = support.api_client(app)

    def tearDown(self):
        self.client.close()
        try:
            self.temp.cleanup()
        except (PermissionError, OSError):
            pass

    def test_the_orphaned_router_is_mounted(self):
        response = self.client.get("/local_specs")

        self.assertEqual(response.status_code, 200)

    def test_the_route_returns_a_provenance_tag_for_every_field(self):
        payload = self.client.get("/local_specs").json()

        for name in hwdetect.REQUIRED_FIELDS:
            with self.subTest(field=name):
                self.assertIn(name, payload)
                self.assertIn(name, payload["provenance"])
                self.assertIn(
                    payload["provenance"][name],
                    ("measured", "inferred", "declared", "defaulted",
                     "untested_on_this_platform"),
                )

    def test_validation_does_not_vanish_under_python_O(self):
        """The handler used bare `assert`, which -O strips out entirely.

        Reverting to `assert` makes this go red because nothing raises.
        """
        import inspect

        source = inspect.getsource(hwdetect.get_local_specs)

        self.assertNotIn("assert ", source)
        self.assertIn("raise", source)


if __name__ == "__main__":
    unittest.main()


class TheDriverAndTheCapabilityAreReadTest(unittest.TestCase):
    """Two rows the Machine pane printed "not detected yet" from the day it
    was drawn.

    `docs/DESIGN_SYSTEM.md` §9.13 asks for the driver and the compute
    capability. Nothing in this repository computed either - not here, not in
    `app/feasibility.py`, whose `can_train` is about VRAM arithmetic and has
    never had an opinion about a driver version. So the rows were honest and
    permanently empty, and the pane's own note said so.

    They come off the SAME `nvidia-smi` call that already ran, so the machine
    is asked once and answers four questions instead of two.
    """

    def test_the_query_asks_for_all_four_in_one_call(self):
        joined = " ".join(hwdetect.NVIDIA_SMI_ARGV)
        for field in ("name", "memory.total", "driver_version", "compute_cap"):
            self.assertIn(field, joined)
        self.assertEqual(
            len([a for a in hwdetect.NVIDIA_SMI_ARGV if a.startswith("--query-gpu")]),
            1,
            "one query, one subprocess: asking twice would be two readings of "
            "a machine that can change between them",
        )

    def test_a_full_line_yields_the_driver_and_the_capability(self):
        parsed = hwdetect.parse_nvidia_smi(
            "NVIDIA GeForce RTX 2060 SUPER, 8192 MiB, 591.86, 7.5"
        )
        self.assertEqual(parsed["gpu_name"], "NVIDIA GeForce RTX 2060 SUPER")
        self.assertEqual(parsed["vram_gb"], 8.0)
        self.assertEqual(parsed["driver_version"], "591.86")
        self.assertEqual(parsed["compute_capability"], "7.5")

    def test_an_older_smi_that_answers_two_columns_still_gives_a_gpu(self):
        """A machine whose nvidia-smi predates compute_cap must not lose its
        GPU. Reporting a card with an unknown capability beats reporting no
        card at all."""
        parsed = hwdetect.parse_nvidia_smi("NVIDIA GeForce GTX 1080, 8192 MiB")
        self.assertEqual(parsed["gpu_name"], "NVIDIA GeForce GTX 1080")
        self.assertEqual(parsed["vram_gb"], 8.0)
        self.assertIsNone(parsed["driver_version"])
        self.assertIsNone(parsed["compute_capability"])

    def test_no_gpu_answers_every_field_with_none(self):
        for text in (None, "", "garbage that is not csv"):
            with self.subTest(text=text):
                parsed = hwdetect.parse_nvidia_smi(text)
                self.assertEqual(parsed, dict(hwdetect.NO_GPU))

    def test_each_new_field_carries_its_own_provenance(self):
        """Not the GPU's. An older smi reports the card and not the driver, so
        borrowing `gpu_name`'s MEASURED would stamp a field nobody read."""
        def two_columns(*args, **kwargs):
            class Result:
                returncode = 0
                stdout = "NVIDIA GeForce GTX 1080, 8192 MiB"
                stderr = ""
            return Result()

        specs = hwdetect.local_specs(runner=two_columns)
        self.assertEqual(specs["provenance"]["gpu_name"], hwdetect.MEASURED)
        self.assertEqual(specs["provenance"]["driver_version"], hwdetect.DEFAULTED)
        self.assertEqual(
            specs["provenance"]["compute_capability"], hwdetect.DEFAULTED
        )
        self.assertIsNone(specs["driver_version"])
        self.assertIn("did not report it", specs["sources"]["driver_version"])

    def test_a_full_answer_stamps_them_measured_with_the_command(self):
        def four_columns(*args, **kwargs):
            class Result:
                returncode = 0
                stdout = "NVIDIA GeForce RTX 2060 SUPER, 8192 MiB, 591.86, 7.5"
                stderr = ""
            return Result()

        specs = hwdetect.local_specs(runner=four_columns)
        self.assertEqual(specs["driver_version"], "591.86")
        self.assertEqual(specs["compute_capability"], "7.5")
        for field in ("driver_version", "compute_capability"):
            self.assertEqual(specs["provenance"][field], hwdetect.MEASURED)
            self.assertIn("nvidia-smi", specs["sources"][field])
