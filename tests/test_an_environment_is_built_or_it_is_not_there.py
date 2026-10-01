"""The environment program, attacked the way this repository attacks a claim.

Max, 2026-09-18: *"what elements and tools and built frameworks do we provide
for this training and working loop - create data framework program, sandbox
program, environment training program etc"*. `make_sandbox` makes a directory
and REPORTS what a recipe pinned; `build_environment` is the step that puts
something in it, and a step that builds is a step that can half-build.

Three claims, and each is measured rather than read back off a docstring.

**It answers about the card, and the answer is not a guess.** The manifest's
`gpu` section is written by running a probe, and `available` is a bool in every
one of the three cases - so the test that matters is not "is it True" (that
depends on the machine the suite runs on) but that the reading and the absence
of a reading are distinguishable: `checked`, `checked_by` and `why` are what
carry the difference, and an unchecked machine must say *no check possible*
rather than quietly reading as a box with no card in it.

**A package that will not install leaves nothing behind.** The sandbox is
removed, the name is free again, the refusal names the package, and the
installer's own last lines come back. A half-built environment that listed and
looked usable is the failure this is for - `app/tools/sandbox.py::create`
already makes the same move when a data snapshot fails, and its comment says
why.

**A version is what landed, not what was asked for.** `torch>=2.4` is a request.
The manifest has to hold the version that is on the disk, read out of the
environment itself, or it is a record of somebody's intention.

## THE OFFLINE WHEEL, AND WHY THE SUITE BUILDS ONE

A test that installs a package off PyPI is a test that fails on a train. So the
one case that needs a REAL successful install builds its own wheel first: a
`.dist-info` directory, a `METADATA` file and one line of Python, zipped. Both
installers take a wheel path as a requirement, and a wheel with no dependencies
needs no index at all. If the install still does not happen - a machine with
neither uv nor pip, a locked-down interpreter - the case SKIPS with the
installer's own words in the skip message, because a silent pass here would be
this file claiming to have measured the thing it exists to measure.
"""

from __future__ import annotations

import base64
import hashlib
import sys
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import autonomy  # noqa: E402
from app.tools import blocks, sandbox  # noqa: E402
from app.tools.registry import REGISTRY  # noqa: E402
from tests import support  # noqa: E402


#: The distribution the suite builds for itself. The name is deliberately one
#: no index has, so a test that accidentally reached an index would fail rather
#: than quietly install somebody else's package under this name.
OFFLINE_NAME = "mlh-offline-probe"
OFFLINE_VERSION = "0.1.0"
OFFLINE_DIST = OFFLINE_NAME.replace("-", "_")

#: A name no index can satisfy, for the refusal case. Same reasoning in reverse.
NO_SUCH_PACKAGE = "mlh-there-is-no-distribution-called-this-9x7"


def an_offline_wheel(into: Path) -> Path:
    """A real, installable, pure-python wheel with no dependencies.

    PEP 427 in thirty lines: the zip holds the module, a `.dist-info` directory
    with `METADATA` and `WHEEL`, and a `RECORD` listing every other member with
    its digest. `importlib.metadata` reads exactly that `METADATA`, which is
    what makes the version assertion downstream a reading of the installed
    environment and not of this file.
    """
    into.mkdir(parents=True, exist_ok=True)
    info = f"{OFFLINE_DIST}-{OFFLINE_VERSION}.dist-info"
    members = {
        f"{OFFLINE_DIST}.py": "VALUE = 1\n",
        f"{info}/METADATA": (
            "Metadata-Version: 2.1\n"
            f"Name: {OFFLINE_NAME}\n"
            f"Version: {OFFLINE_VERSION}\n"
            "Summary: a pure-python nothing, built by this suite so that one "
            "install can be measured with no index\n"
        ),
        f"{info}/WHEEL": (
            "Wheel-Version: 1.0\n"
            "Generator: ml-harness-tests\n"
            "Root-Is-Purelib: true\n"
            "Tag: py3-none-any\n"
        ),
    }
    path = into / f"{OFFLINE_DIST}-{OFFLINE_VERSION}-py3-none-any.whl"
    record: list[str] = []
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as bundle:
        for member, body in members.items():
            data = body.encode("utf-8")
            bundle.writestr(member, data)
            digest = (
                base64.urlsafe_b64encode(hashlib.sha256(data).digest())
                .rstrip(b"=")
                .decode("ascii")
            )
            record.append(f"{member},sha256={digest},{len(data)}")
        record.append(f"{info}/RECORD,,")
        bundle.writestr(f"{info}/RECORD", "\n".join(record) + "\n")
    return path


class TheEnvironmentIsBuiltOrItIsNotThereTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)

    # -- the card ----------------------------------------------------------

    def test_a_sandbox_with_no_packages_still_answers_about_the_card(self):
        """No packages is a real request, and it still gets a GPU section.

        `built` is false and there is no virtualenv, because building one to
        hold nothing would be twenty megabytes of nothing - but the question
        "can anything in here see the card" is still answered, against the
        interpreter a run in this sandbox would actually use.
        """
        made = sandbox.build_environment(name="empty-box")
        self.assertTrue(made["ok"], made)

        manifest = sandbox.read_manifest("empty-box")
        environment = manifest["environment"]
        self.assertFalse(environment["built"])
        self.assertFalse((Path(manifest["path"]) / sandbox.ENV).exists())

        gpu = environment["gpu"]
        self.assertIsInstance(
            gpu["available"],
            bool,
            "the GPU section's `available` has to be a bool: a caller branches "
            "on it, and a three-valued field is read as a bool by the first "
            "caller who forgets",
        )
        self.assertTrue(gpu["checked_by"])
        self.assertTrue(gpu["why"])
        # THE HALF `available` CANNOT CARRY. A machine nobody could check must
        # be distinguishable from a machine that was checked and has no card,
        # or the bool above is the collapse this product refuses everywhere.
        if not gpu["checked"]:
            self.assertEqual(gpu["checked_by"], "no check possible")
            self.assertFalse(gpu["available"])
            self.assertIn("nothing OBSERVED", gpu["why"])
        else:
            self.assertNotEqual(gpu["checked_by"], "no check possible")

    def test_the_check_can_be_declined_and_says_that_is_what_happened(self):
        """`gpu_check=false` is not a reading of a machine with no card."""
        made = sandbox.build_environment(name="unasked-box", gpu_check=False)
        gpu = made["environment"]["gpu"]
        self.assertFalse(gpu["available"])
        self.assertFalse(gpu["checked"])
        self.assertEqual(gpu["checked_by"], "not asked for")
        self.assertIn("nothing looked", gpu["why"])

    # -- the refusal -------------------------------------------------------

    def test_a_package_that_will_not_install_names_itself_and_leaves_nothing(self):
        """Nothing half-built is reported as built.

        The bound is shortened for this one call because the failure being
        provoked is a resolver failure, and a resolver that cannot reach an
        index retries: the fifteen-minute production bound is right for a real
        install and wrong for a test that is waiting for a refusal. Both routes
        out - the resolver saying no, and the bound killing the tree - return
        `install_failed` and name the requirement, which is what is asserted.
        """
        with mock.patch.object(sandbox, "INSTALL_TIMEOUT_SECONDS", 120):
            refused = sandbox.build_environment(
                name="doomed-box", packages=[NO_SUCH_PACKAGE], gpu_check=False
            )

        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "install_failed")
        self.assertIn(NO_SUCH_PACKAGE, refused["detail"])
        self.assertIn(NO_SUCH_PACKAGE, refused["packages"])
        self.assertLessEqual(
            len(refused["stderr_tail"]), sandbox.STDERR_TAIL_LINES
        )
        self.assertTrue(refused["sandbox_removed"])
        self.assertFalse(
            (sandbox.sandboxes_root() / "doomed-box").exists(),
            "the sandbox is still on disk after an install that failed, so it "
            "will list and look usable and be missing the one thing it was "
            "made for",
        )
        # AND THE NAME IS FREE AGAIN, which is the point of removing it rather
        # than keeping a broken one: the person retries with what they typed.
        again = sandbox.build_environment(name="doomed-box", gpu_check=False)
        self.assertTrue(again["ok"], again)

    # -- the versions ------------------------------------------------------

    def test_the_manifest_records_the_version_that_actually_landed(self):
        wheel = an_offline_wheel(Path(self.root) / "wheels")
        built = sandbox.build_environment(
            name="pinned-box", packages=[str(wheel)], gpu_check=False
        )
        if not built.get("ok"):
            self.skipTest(
                "no install could be made on this machine, so there is no "
                "version to read back. This case needs a working installer and "
                "not an index - the wheel is built by the test. The refusal "
                f"was: {built.get('detail')} {built.get('stderr_tail')}"
            )

        environment = sandbox.read_manifest("pinned-box")["environment"]
        self.assertTrue(environment["built"])
        self.assertIn(environment["built_by"], ("uv", "venv+pip"))
        self.assertTrue(Path(environment["interpreter"]).is_file())

        rows = environment["packages"]
        self.assertEqual(len(rows), 1, rows)
        row = rows[0]
        self.assertEqual(row["distribution"], OFFLINE_NAME)
        self.assertEqual(
            row["version"],
            OFFLINE_VERSION,
            "the manifest has to carry the version that is on the disk, read "
            "out of the environment itself - a requirement is a request and "
            "not a record",
        )
        self.assertIn("importlib.metadata", row["version_source"])
        self.assertTrue(environment["digest"])
        self.assertIn("does NOT cover", environment["fingerprint_note"])

    def test_a_requirement_that_names_no_distribution_says_so(self):
        """The version lookup refuses to guess, and the refusal is a sentence."""
        self.assertEqual(sandbox.distribution_name("peft==0.13.2"), "peft")
        self.assertEqual(sandbox.distribution_name("torch>=2.4"), "torch")
        self.assertEqual(sandbox.distribution_name("uvicorn[standard]"), "uvicorn")
        self.assertEqual(
            sandbox.distribution_name("mlh_offline_probe-0.1.0-py3-none-any.whl"),
            "mlh-offline-probe",
        )
        self.assertEqual(sandbox.distribution_name("something.tar.gz"), "")

    # -- the census --------------------------------------------------------

    def test_the_pack_census_moves_and_the_autonomy_is_named(self):
        """A capability, a pack membership and a classified approval.

        All three are derived rather than listed: the pack is the first segment
        of the capability, the membership is `provides=`, and the autonomy
        entry is checked against the registry's own approvals by
        `tests/test_autonomy_is_named_not_assumed.py`. This asserts the three
        agree for THIS tool, so the census moving is a fact about the product
        and not about a number somebody retyped.
        """
        self.assertIn("sandbox.environment.build", blocks.CAPABILITIES)
        self.assertEqual(blocks.pack_of("sandbox.environment.build"), "sandbox")
        self.assertIn("build_environment", blocks.tools_in({"sandbox"}))

        spec = REGISTRY.get("build_environment")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.approval, "always")
        self.assertEqual(spec.packs, frozenset({"sandbox"}))
        self.assertEqual(spec.measures, ())

        self.assertIn("build_environment", autonomy.UNATTENDED)
        self.assertTrue(autonomy.may_run("write", "build_environment"))
        self.assertTrue(autonomy.may_run("full", "build_environment"))
        self.assertFalse(autonomy.may_run("ask", "build_environment"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
