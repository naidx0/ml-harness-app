"""Fetch the `uv` the shell ships, verified — so it is pinned without being committed.

`docs/THE_PLAN.md` V.4: *"ship `uv.exe` as the sidecar and bootstrap a real
interpreter on first run"*, and the argument for it is repo-internal and
decisive. `jobspec.interpreter` hands `sys.executable` to a training recipe, and
under a freezer that is the APPLICATION — so a frozen build would relaunch this
product instead of running somebody's training script, silently, with a
plausible process appearing. Freezing breaks the training executor. `uv` does
not, and it is already what `recipes/*/requirements.lock` is written for.

## Why a fetch and not a committed binary

`uv.exe` is about 35 MB. Committing it would put a third of a release into every
clone forever, and git stores each new version as another 35 MB — so pinning by
upgrade would mean the repository grows by a release every time the sidecar
moves. It would also make the binary something a reviewer cannot review: a blob
in the tree with no provenance beyond "somebody added it".

A pinned fetch is the same guarantee with none of that. The version is written
down here, the checksum is fetched from upstream's own `.sha256` beside the
archive, and the download is refused if it does not match. The result is
gitignored, which means a build that did not run this step has no sidecar rather
than a stale one.

## What "verified" is worth, said honestly

The checksum comes from the same host as the archive, so this defends against a
corrupted or truncated download and against a CDN serving the wrong object. **It
is not a defence against GitHub itself serving a bad release**, and pretending
otherwise would be the kind of claim this repository refuses. What would improve
it is upstream signing the release and this checking the signature; until then
the honest statement is the one in this paragraph.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import platform
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path


#: The version this shell ships. Bumping it is a deliberate edit here, and the
#: checksum is fetched for whatever this says rather than being pinned beside
#: it - a hash written by hand goes stale silently the first time somebody
#: changes the version and not the hash.
UV_VERSION = "0.12.0"

#: Where Tauri looks for an external binary. `bundle.externalBin` names
#: `binaries/uv`, and Tauri appends the target triple - so the file on disk must
#: be `uv-<triple>.exe` or the build fails with a message about a missing
#: sidecar rather than shipping without one.
BINARIES = Path(__file__).resolve().parents[1] / "src-tauri" / "binaries"

#: Rust's target triple for each host this can fetch for. Not a guess: these are
#: the names `rustc -vV` prints and the names uv's own release assets use, and
#: the two agreeing is what makes one string serve both.
TRIPLES = {
    ("Windows", "AMD64"): "x86_64-pc-windows-msvc",
    ("Windows", "ARM64"): "aarch64-pc-windows-msvc",
    ("Darwin", "arm64"): "aarch64-apple-darwin",
    ("Darwin", "x86_64"): "x86_64-apple-darwin",
    ("Linux", "x86_64"): "x86_64-unknown-linux-gnu",
    ("Linux", "aarch64"): "aarch64-unknown-linux-gnu",
}

RELEASE = "https://github.com/astral-sh/uv/releases/download/{version}/{asset}"


def host_triple() -> str:
    key = (platform.system(), platform.machine())
    triple = TRIPLES.get(key)
    if triple is None:
        raise SystemExit(
            f"no uv target triple known for {key}. The shell ships a sidecar for "
            f"the host it is built on; add the triple to TRIPLES if this host "
            "is one uv publishes for."
        )
    return triple


def _fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def fetch(triple: str, version: str = UV_VERSION) -> Path:
    """Download, verify, unpack. Returns the path Tauri will look for."""
    windows = "windows" in triple
    suffix = "zip" if windows else "tar.gz"
    asset = f"uv-{triple}.{suffix}"
    url = RELEASE.format(version=version, asset=asset)

    print(f"fetching {url}")
    archive = _fetch(url)

    # THE CHECKSUM IS FETCHED RATHER THAN WRITTEN DOWN, so bumping the version
    # above cannot leave a stale hash beside it that nobody notices.
    published = _fetch(url + ".sha256").decode("utf-8", "replace").split()[0].strip()
    actual = hashlib.sha256(archive).hexdigest()
    if actual != published:
        raise SystemExit(
            "REFUSED: the download does not match the checksum upstream "
            f"publishes for it.\n  expected {published}\n  got      {actual}\n"
            "Nothing was written. A sidecar this could not verify is a binary "
            "shipped to somebody on the strength of a URL."
        )
    print(f"verified sha256 {actual}")

    BINARIES.mkdir(parents=True, exist_ok=True)
    target = BINARIES / (f"uv-{triple}.exe" if windows else f"uv-{triple}")

    if windows:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            name = next(n for n in bundle.namelist() if n.endswith("uv.exe"))
            with bundle.open(name) as source, target.open("wb") as sink:
                shutil.copyfileobj(source, sink)
    else:
        import tarfile

        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
            member = next(m for m in bundle.getmembers() if m.name.endswith("/uv"))
            extracted = bundle.extractfile(member)
            if extracted is None:  # pragma: no cover - a malformed archive
                raise SystemExit(f"{asset} has no uv binary in it")
            with target.open("wb") as sink:
                shutil.copyfileobj(extracted, sink)
        target.chmod(0o755)

    size = target.stat().st_size
    print(f"wrote {target} ({size:,} bytes)")
    if size < 1_000_000:
        raise SystemExit(
            f"{target} is {size:,} bytes, which is not a uv binary. Refusing "
            "rather than letting a build ship something that is not what it says."
        )
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--triple",
        default=None,
        help="Target triple to fetch for. Defaults to this host's.",
    )
    parser.add_argument("--version", default=UV_VERSION)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report whether the sidecar is already there, and fetch nothing.",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    triple = args.triple or host_triple()
    windows = "windows" in triple
    target = BINARIES / (f"uv-{triple}.exe" if windows else f"uv-{triple}")

    if args.check:
        if target.is_file():
            print(f"present: {target} ({target.stat().st_size:,} bytes)")
            return 0
        print(f"absent: {target}\nRun `python scripts/fetch_sidecar.py` to fetch it.")
        return 1

    fetch(triple, args.version)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
