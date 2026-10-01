"""Hardware detection, with provenance on every field.

Two verified defects are fixed here.

* ``local_specs()`` reported free disk space in the ``ram_gb`` field. Both
  numbers came from the same ``shutil.disk_usage("/").free`` call, so this
  machine - which has 16 GB of RAM - reported 702.5 GB of it, and every
  downstream memory decision was computed from that figure.
* ``parse_nvidia_smi()`` was a correct regex with no caller anywhere in the
  product, and the router that would have exposed it was never mounted. Nothing
  in the running app ever learned what GPU was present, which is why no code
  path could produce a real VRAM number at all.

Every value returned carries a provenance tag. That is the mechanism, not a
decoration: the ``8.0``-hardcoded-VRAM class of bug is invisible until a number
has to say where it came from. ``app/feasibility.py`` refuses to render a
confident verdict from a value tagged ``defaulted``.

See docs/ROADMAP.md Milestone 0c and docs/ARCHITECTURE.md section 4.6.
"""

from __future__ import annotations

import ctypes
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal

#: IMPORTED LAZILY, SO DETECTION DOES NOT NEED A WEB FRAMEWORK.
#:
#: This module is what tells a person what their machine is, and on 2026-09-06 a
#: check built out of it could not run on a fresh Windows machine at all: the
#: first line of `parse_nvidia_smi` was never reached, because importing the
#: module imported FastAPI. A hardware detector that needs a web server to load
#: is a detector nobody can run before installing the product, which is the one
#: moment the answer is worth having.
#:
#: The route below still needs it and still gets it. When FastAPI is absent the
#: router is `None`, and `app/main.py` - the only caller - fails at
#: `include_router` rather than here, which is the right place for a web
#: application to notice it has no web framework.
try:
    from fastapi import APIRouter
except ModuleNotFoundError:  # pragma: no cover - the fresh-machine path
    APIRouter = None

# The four provenance tags docs/ROADMAP.md 0c enumerates. "declared" is the
# fifth, added by docs/DESIGN_SYSTEM.md section 9.3, and belongs to values a
# user typed rather than values this module read.
Provenance = Literal[
    "measured",
    "inferred",
    "declared",
    "defaulted",
    "untested_on_this_platform",
]

MEASURED: Provenance = "measured"
DEFAULTED: Provenance = "defaulted"
UNTESTED: Provenance = "untested_on_this_platform"

# Ruling 7: any result obtained by a code path that has never been executed on
# the platform it targets is best-effort, and says so in its provenance rather
# than in a footnote. Apple Silicon is the named case; the owner has no Mac.
UNTESTED_PLATFORMS = ("Darwin",)

# THREE MORE FIELDS FOR NO MORE COST. The Machine pane has printed "not
# detected yet" for the driver and the compute capability since it was drawn,
# and `docs/DESIGN_SYSTEM.md` §9.13 asks for both. Nothing in this repository
# computed them - not here, not in `app/feasibility.py` - so the rows were
# honest and permanently empty. They come off the SAME nvidia-smi call that
# already runs, so the machine is asked once and answers four questions.
NVIDIA_SMI_ARGV = [
    "nvidia-smi",
    "--query-gpu=name,memory.total,driver_version,compute_cap",
    "--format=csv,noheader",
]

GIB = 1024 ** 3


#: What an absent GPU looks like. Named once so every early return below is
#: the same shape, and so a field added here cannot be forgotten in one of them.
NO_GPU: dict[str, Any] = {
    "gpu_name": None,
    "vram_gb": None,
    "driver_version": None,
    "compute_capability": None,
}


def parse_nvidia_smi(text: str | None) -> dict[str, Any]:
    """Parse one ``name, NNNN MiB, driver, cap`` line of nvidia-smi CSV.

    THE LAST TWO FIELDS ARE OPTIONAL ON PURPOSE. A machine whose nvidia-smi
    predates `compute_cap` still answers the first two, and this product would
    rather report a GPU with an unknown capability than no GPU at all. So the
    name and the memory are required by the pattern and the rest is read if it
    is there - which is also what keeps an older recorded fixture parseable.
    """
    if not text:
        return dict(NO_GPU)

    match = re.search(r"^(.+?),\s+(\d+)\s+MiB(.*)$", text.strip(), re.MULTILINE)
    if not match:
        return dict(NO_GPU)

    rest = [part.strip() for part in match.group(3).split(",") if part.strip()]
    return {
        "gpu_name": match.group(1).strip(),
        "vram_gb": round(int(match.group(2)) / 1024.0, 1),
        "driver_version": rest[0] if len(rest) > 0 else None,
        "compute_capability": rest[1] if len(rest) > 1 else None,
    }


def _nvidia_smi_path() -> str:
    """The absolute path to ``nvidia-smi``, or the bare name if it is not found.

    A BARE NAME IS RESOLVED AGAINST THE CALLER'S ``PATH``, AND THE ENGINE'S IS
    NOT THE SHELL'S. Found by driving the running product: ``nvidia-smi`` answers
    instantly in a terminal and ``GET /local_specs`` returned
    ``gpu_name: null`` with ``"nvidia-smi unavailable"`` at the same moment, on
    the same machine, with the card idle and visible to ``shutil.which`` at
    ``C:\\WINDOWS\\system32\\nvidia-smi.EXE``. Max asked whether localhost was
    open to test and would have met an empty state saying his RTX 2060 SUPER was
    not there.

    Nothing about the honesty contract changes. ``which`` returning ``None`` is
    a machine with no NVIDIA driver, and the bare name then fails exactly as it
    did before: ``None`` from this function, ``defaulted`` provenance upstream,
    ``UNKNOWN`` rather than ``FITS``. Resolving the path can only turn a false
    negative into a reading; it can never turn a missing card into one.
    """
    return shutil.which(NVIDIA_SMI_ARGV[0]) or NVIDIA_SMI_ARGV[0]


def read_nvidia_smi(runner=subprocess.run) -> str | None:
    """Run ``nvidia-smi`` and return its stdout, or ``None`` if it is not there.

    This is the caller ``parse_nvidia_smi`` never had. It never raises and it
    never substitutes a default - a machine with no NVIDIA driver gets ``None``,
    which becomes a ``defaulted`` provenance upstream, which becomes an
    ``UNKNOWN`` verdict. A guess here would be indistinguishable from a reading.
    """
    try:
        completed = runner(
            [_nvidia_smi_path(), *NVIDIA_SMI_ARGV[1:]],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if getattr(completed, "returncode", 1) != 0:
        return None
    return completed.stdout or None


def _windows_physical_ram_bytes() -> int | None:
    class MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatusEx()
    status.dwLength = ctypes.sizeof(MemoryStatusEx)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return int(status.ullTotalPhys)


def _darwin_physical_ram_bytes() -> int | None:
    try:
        completed = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    try:
        return int(completed.stdout.strip())
    except ValueError:
        return None


def _posix_physical_ram_bytes() -> int | None:
    try:
        return int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, ValueError, OSError):
        return None


def physical_ram_bytes(system: str | None = None) -> tuple[int | None, str, str]:
    """Installed physical RAM, in bytes, with provenance and source.

    Free tier only - stdlib and one ``sysctl`` shell-out. Returns
    ``(None, "defaulted", ...)`` rather than a fallback constant when the
    platform will not say, because a fallback constant presented as a reading is
    the defect this module exists to stop repeating.
    """
    system = system or platform.system()
    reader, source = {
        "Windows": (_windows_physical_ram_bytes, "kernel32.GlobalMemoryStatusEx"),
        "Darwin": (_darwin_physical_ram_bytes, "sysctl -n hw.memsize"),
    }.get(system, (_posix_physical_ram_bytes, "os.sysconf(SC_PHYS_PAGES)"))

    try:
        total = reader()
    except Exception:  # noqa: BLE001 - a probe must never take the app down
        total = None

    if not total or total <= 0:
        return None, DEFAULTED, f"{source} unavailable"
    if system in UNTESTED_PLATFORMS:
        return total, UNTESTED, source
    return total, MEASURED, source


def model_cache_volume() -> Path:
    """The volume the models and the database actually live on.

    ``shutil.disk_usage("/")`` measures the root of the current drive, which on
    Windows is frequently not the drive this project sits on.
    """
    return Path(__file__).resolve().parents[1]


def local_specs(runner=subprocess.run) -> dict[str, Any]:
    """Describe this machine. Never returns ``None``; never invents a number.

    ``ram_gb`` and ``disk_free_gb`` are read from two different sources, which is
    the fix: they used to be the same call.
    """
    system = platform.system()
    provenance: dict[str, str] = {}
    sources: dict[str, str] = {}
    warnings: list[str] = []

    ram_bytes, ram_provenance, ram_source = physical_ram_bytes(system)
    ram_gb = round(ram_bytes / GIB, 1) if ram_bytes else None
    provenance["ram_gb"] = ram_provenance
    sources["ram_gb"] = ram_source
    if ram_gb is None:
        warnings.append(
            "Installed RAM could not be read on this platform; it is reported as "
            "unknown rather than guessed."
        )

    try:
        disk_free_gb = round(shutil.disk_usage(model_cache_volume()).free / GIB, 1)
        provenance["disk_free_gb"] = MEASURED
        sources["disk_free_gb"] = "shutil.disk_usage(model cache volume)"
    except OSError:
        disk_free_gb = None
        provenance["disk_free_gb"] = DEFAULTED
        sources["disk_free_gb"] = "shutil.disk_usage unavailable"

    os_name = system or None
    provenance["os"] = MEASURED if os_name else DEFAULTED
    sources["os"] = "platform.system()"

    gpu = parse_nvidia_smi(read_nvidia_smi(runner))
    gpu_measured = gpu["vram_gb"] is not None
    gpu_provenance = MEASURED if gpu_measured else DEFAULTED
    if gpu_measured and system in UNTESTED_PLATFORMS:
        gpu_provenance = UNTESTED
    provenance["gpu_name"] = gpu_provenance
    provenance["vram_gb"] = gpu_provenance
    gpu_source = "nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap"
    sources["gpu_name"] = gpu_source if gpu_measured else "nvidia-smi unavailable"
    sources["vram_gb"] = sources["gpu_name"]

    # THE DRIVER AND THE CAPABILITY ARE MEASURED SEPARATELY FROM THE MEMORY,
    # because an older nvidia-smi answers the first two columns and not these.
    # Each one carries its own provenance rather than borrowing the GPU's:
    # `MEASURED` when this call returned it, `DEFAULTED` when it did not, and
    # never a value this function chose.
    for field in ("driver_version", "compute_capability"):
        present = gpu[field] is not None
        provenance[field] = (
            (UNTESTED if system in UNTESTED_PLATFORMS else MEASURED)
            if present
            else DEFAULTED
        )
        sources[field] = (
            gpu_source
            if present
            else "nvidia-smi did not report it on this machine"
        )
    if not gpu_measured:
        warnings.append(
            "nvidia-smi did not answer, so no GPU was detected. Feasibility "
            "verdicts computed against this profile are UNKNOWN, not FITS."
        )
    if system in UNTESTED_PLATFORMS:
        warnings.append(
            f"{system} is untested on this platform; every reading above is "
            "best-effort."
        )

    return {
        "ram_gb": ram_gb,
        "disk_free_gb": disk_free_gb,
        "os": os_name,
        "gpu_name": gpu["gpu_name"],
        "vram_gb": gpu["vram_gb"],
        "driver_version": gpu["driver_version"],
        "compute_capability": gpu["compute_capability"],
        "provenance": provenance,
        "sources": sources,
        "warnings": warnings,
    }


router = APIRouter() if APIRouter is not None else None

REQUIRED_FIELDS = ("ram_gb", "disk_free_gb", "os", "gpu_name", "vram_gb")


def get_local_specs() -> dict[str, Any]:
    """The route that was written and never mounted.

    The bare ``assert`` statements this handler used to carry vanish under
    ``python -O``, which means the only validation in the module disappeared in
    exactly the configuration a user would run.
    """
    specs = local_specs()
    missing = [field for field in REQUIRED_FIELDS if field not in specs]
    if missing:
        raise RuntimeError(f"local_specs() omitted {', '.join(missing)}")
    if not isinstance(specs.get("provenance"), dict):
        raise RuntimeError("local_specs() returned no provenance map")
    unprovenanced = [f for f in REQUIRED_FIELDS if f not in specs["provenance"]]
    if unprovenanced:
        raise RuntimeError(
            f"local_specs() returned {', '.join(unprovenanced)} without provenance"
        )
    return specs


#: The route, mounted only when there is something to mount it on. Written this
#: way round so `get_local_specs` stays an ordinary function that a test - or a
#: check running on a machine with no web framework - can call directly.
if router is not None:  # pragma: no cover - exercised by the app's own startup
    router.get("/local_specs", response_model=dict[str, Any], status_code=200)(
        get_local_specs
    )
