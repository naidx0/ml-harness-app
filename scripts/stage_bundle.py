"""Put the two things a packaged shell needs beside it, and refuse if it cannot.

`src-tauri/tauri.conf.json` runs this before every build. It is the ONE entry
point for "what does the bundle carry that is not Rust", and there are exactly
two answers:

1. **`uv`** — `bundle.externalBin`. `scripts/fetch_sidecar.py` fetches and
   verifies it, and argues there why a checksummed fetch beats a committed
   binary.
2. **the wheel** — `bundle.resources`. `src-tauri/src/engine.rs::payload` looks
   for `resources/ml_harness-*.whl` beside the binary and installs it into the
   interpreter uv makes on first run.

## Why the wheel and not the source tree

An installed copy has no checkout. uv can make an interpreter on a machine with
no Python at all, but an interpreter with nothing installed in it cannot
`import app` — so the bundle has to carry the product itself, and a wheel is the
form of it that `pip install` already knows how to place. It is also the exact
artefact `.github/workflows/gate.yml`'s wheel job builds and proves can load its
own ledgers, model geometries and recipes, so what ships is what CI checked.

## Why uv builds it rather than `python -m build`

Because the sidecar is already here and already pinned. Asking for `build` and
`setuptools` in whatever interpreter happens to be running the Tauri build would
add a second, unpinned toolchain to a step whose whole job is to be reproducible.

## Stale wheels are DELETED, not left

`payload()` picks the newest name when it finds several, which is the right
tie-break for a bundle that somehow carries two — but a build directory that
accumulates versions is a way to ship last month's product with this month's
shell. So the directory is emptied of wheels first, and what is in it after this
runs is what this run built.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetch_sidecar import BINARIES, fetch, host_triple  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "src-tauri" / "resources"


def sidecar() -> Path:
    """The verified uv, fetched if this build has not fetched one yet."""
    triple = host_triple()
    windows = "windows" in triple
    target = BINARIES / (f"uv-{triple}.exe" if windows else f"uv-{triple}")
    if target.is_file():
        print(f"sidecar present: {target} ({target.stat().st_size:,} bytes)")
        return target
    return fetch(triple)


def wheel(uv: Path) -> Path:
    RESOURCES.mkdir(parents=True, exist_ok=True)
    for stale in RESOURCES.glob("*.whl"):
        print(f"removing stale {stale.name}")
        stale.unlink()

    subprocess.run(
        [str(uv), "build", "--wheel", "--out-dir", str(RESOURCES), str(ROOT)],
        check=True,
    )

    built = sorted(RESOURCES.glob("ml_harness-*.whl"))
    if not built:
        raise SystemExit(
            f"uv build reported success and left no ml_harness wheel in {RESOURCES}. "
            "Refusing rather than letting a bundle ship without the product in it."
        )
    made = built[-1]
    print(f"staged {made.name} ({made.stat().st_size:,} bytes)")
    return made


def main() -> int:
    uv = sidecar()
    wheel(uv)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
