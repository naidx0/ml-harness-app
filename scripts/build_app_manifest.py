"""Generate `web/package.json` from OpenCode's vendored manifests.

    python scripts/build_app_manifest.py

The frontend lives in `web/`, NOT `app/` - `app/` is the Python engine
package (conductor, diagnosis, tools) and putting a node_modules in it is a
collision waiting to happen.

WHAT THIS SOLVES. OpenCode's manifests are written for their monorepo and do
not resolve anywhere else. Two protocols are in the way:

  "@opencode/ui":  "workspace:*"   - a sibling package in their repo
  "solid-js":      "catalog:"      - a bun workspace catalog entry

Neither means anything to npm. The naive fix is to hand-write 69 version pins,
which then rot every time upstream moves - and upstream moved 95 times in the
last seven days.

So instead both are RESOLVED FROM UPSTREAM ITSELF, at the commit
`PROVENANCE.json` pins:

  - `catalog:` is looked up in `vendor/opencode/CATALOG.json`, copied out of
    their root manifest by `vendor_opencode.py` at that same commit.
  - `workspace:*` splits two ways. A package published to npm becomes a real
    dependency at the pinned version, because it is maintained upstream and
    upgrades with a version bump. A package that is NOT published becomes a
    `file:` path into the vendored tree, because there is nothing to depend on.

Re-running this after a re-vendor regenerates every version, so nothing here is
maintained by hand and nothing can silently drift from the commit it claims.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "opencode"
WEB = REPO / "web"

#: Their packages that ARE on npm under MIT. These stay dependencies: upstream
#: publishes them, so an upgrade is a version bump rather than a re-copy.
#: Verified against the registry - @opencode/ui alone has 467 versions.
PUBLISHED = {
    "@opencode/ui",
    "@opencode/client",
    "@opencode/schema",
    "@opencode/util",
    "@opencode/sdk",
    "@opencode/protocol",
}

#: Their packages that are NOT on npm, so they are vendored and referenced by
#: path. `session-ui` is marked private; `app` has never been published.
VENDORED = {
    "@opencode/session-ui": "vendor/opencode/packages/session-ui",
    "@opencode/app": "vendor/opencode/packages/app",
}

#: Dropped deliberately. `plugin-browser` drives an Electron WebContentsView
#: that has no Tauri equivalent, and `ghostty-web` is a terminal emulator
#: pinned to a GitHub commit - neither belongs in a harness that shells out to
#: Python. Recorded here rather than silently absent.
DROPPED = {
    "@opencode/plugin-browser": "Electron browser pane; no Tauri equivalent",
    "ghostty-web": "terminal emulator; the harness has no terminal surface",
    "@sentry/solid": "no telemetry in a local-first product",
}


#: Build-time packages that are about being OpenCode rather than about
#: building a Solid app. Playwright and the PWA plugin are theirs to run; the
#: Sentry plugin uploads sourcemaps to a service this product does not use; the
#: bun types describe a runtime we do not have.
DEV_DROPPED = {
    "@playwright/test",
    "@sentry/vite-plugin",
    "@types/bun",
    "vite-plugin-pwa",
    "@typescript/native-preview",
}


def resolve(name: str, spec: str, catalog: dict[str, str], version: str) -> str | None:
    if name in DROPPED:
        return None
    # VERBATIM, NEVER WIDENED. This used to prepend "^", and the type checker
    # caught what that cost: upstream pins @pierre/diffs at exactly 1.2.10, the
    # caret let npm install 1.4.3, whose generic signatures changed - and
    # because @opencode/ui carries its own nested 1.2.10, the page ended up
    # with two copies of a library that registers a custom element. Upstream's
    # catalog says exactly what it was built against; a range here silently
    # overrides that on the next install.
    if spec.startswith("catalog"):
        pinned = catalog.get(name)
        if not pinned:
            sys.exit(f"{name} wants the catalog and the catalog has no entry for it")
        return pinned
    if spec.startswith("workspace:"):
        if name in PUBLISHED:
            # The published version their app declares, exactly - not "this or
            # anything newer", which is how the drift above happened.
            return version
        if name in VENDORED:
            return "file:" + VENDORED[name]
        sys.exit(f"{name} is a workspace dependency and is neither published nor vendored")
    return spec


def main() -> None:
    provenance = json.loads((VENDOR / "PROVENANCE.json").read_text(encoding="utf-8"))
    catalog = json.loads((VENDOR / "CATALOG.json").read_text(encoding="utf-8"))
    theirs = json.loads((VENDOR / "packages" / "app" / "package.json").read_text(encoding="utf-8"))
    version = theirs.get("version", "2.0.14")

    # SESSION-UI IS ALIASED, NOT INSTALLED. Installing it by `file:` would make
    # npm read its manifest, and that manifest has sixteen `catalog:` entries of
    # its own. Rewriting it in the vendored tree would break byte-identity with
    # the pinned commit, which is the one property that makes an upstream diff
    # possible. So it is resolved to source by a Vite alias - exactly how their
    # own monorepo resolves it - and its dependencies are merged into ours here,
    # because a source alias brings no dependencies with it.
    sessionui = json.loads(
        (VENDOR / "packages" / "session-ui" / "package.json").read_text(encoding="utf-8")
    )
    merged: dict[str, str] = {}
    merged.update(theirs.get("dependencies") or {})
    merged.update(sessionui.get("dependencies") or {})

    dependencies: dict[str, str] = {}
    dropped: list[str] = []
    for name, spec in sorted(merged.items()):
        if name in VENDORED:
            continue          # aliased to source, never a package
        resolved = resolve(name, str(spec), catalog, version)
        if resolved is None:
            dropped.append(name)
            continue
        dependencies[name] = resolved

    # THE BUILD TOOLCHAIN COMES FROM THEIRS TOO, for the same reason the runtime
    # dependencies do. Hand-pinning it put this on Vite 7 while their source is
    # written against Vite 8, which is the kind of mismatch that produces a
    # baffling error three layers down rather than an honest one here.
    dev: dict[str, str] = {}
    for name, spec in sorted((theirs.get("devDependencies") or {}).items()):
        if name in DEV_DROPPED:
            continue
        resolved = resolve(name, str(spec), catalog, version)
        if resolved is not None:
            dev[name] = resolved
    # Not in their manifest because their monorepo hoists it, and not optional:
    # @tailwindcss/vite is a plugin FOR tailwindcss, not a copy of it.
    dev.setdefault("tailwindcss", dev.get("@tailwindcss/vite", "^4.3.3"))
    dev.setdefault("typescript", "^5.9.3")
    # OURS, NOT THEIRS: their suite runs on bun's test runner, ours on vitest.
    # It lives here because this script OWNS web/package.json - vitest was
    # once added by hand with `npm install -w web`, and the next regeneration
    # silently dropped it, leaving a green build and a test runner that could
    # not load. Anything this product adds to the manifest is added here.
    dev["vitest"] = "^3.2.4"
    # OURS: the shell's own bridge. Their Electron desktop is not vendored, so
    # nothing of theirs needs it; the Tauri platform does, for the ordered
    # message channel the streaming carrier sends frames on. Exact, and the
    # same minor as the shell's tauri crate, so the IPC format cannot drift.
    dependencies["@tauri-apps/api"] = "2.11.1"
    # OURS: the product's one display face, Sora - a clean grotesque, and the
    # open face behind the owner's commercial ones (Neue Montreal, Aktiv
    # Grotesk, Apfel Grotezk) where those are installed. The owner, 2026-09-22,
    # retired the Roman inscription (Marcellus) and the italic voice
    # (Cormorant Garamond). OFL-licensed; bundled, never fetched.
    dependencies["@fontsource/sora"] = "5.3.0"
    # The shell's build CLI, so `npm --prefix web exec -- tauri build` works
    # the way `npm --prefix frontend exec` did. Same version the outgoing
    # frontend pinned, so the bundler does not change under the cutover.
    dev["@tauri-apps/cli"] = "2.11.4"

    manifest = {
        "name": "ml-harness-app",
        "private": True,
        "type": "module",
        "version": "0.1.0",
        "description": (
            "The ML Harness interface. Built on OpenCode (MIT); see "
            "THIRD-PARTY-NOTICES.txt. Generated by scripts/build_app_manifest.py "
            f"from upstream {provenance['commit'][:12]} - do not hand-edit the "
            "dependency versions, re-run the script."
        ),
        "scripts": {
            "dev": "vite",
            "build": "vite build",
            "preview": "vite preview",
            "typecheck": "tsc -b",
            "test": "vitest run",
        },
        "dependencies": dependencies,
        "devDependencies": dev,
    }

    WEB.mkdir(exist_ok=True)
    (WEB / "package.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline=chr(10))

    print(f"wrote web/package.json from upstream {provenance['commit'][:12]}")
    print(f"  {len(dependencies)} dependencies resolved")
    print(f"  {len(VENDORED)} aliased to vendored source, not installed")
    for name in dropped:
        print(f"  dropped {name}: {DROPPED[name]}")
    print(f"  tsconfig.paths.json: {write_tsconfig_paths()} paths from the exports map")


def write_tsconfig_paths() -> int:
    """Generate `web/tsconfig.paths.json` from session-ui's own exports map.

    The Vite resolver in web/vite.config.ts reads the same map at build time.
    The type checker cannot run a plugin, so it gets the map as `paths`,
    generated here from the same source - two resolvers fed from one file
    rather than a hand-kept copy that drifts from the other on the next
    re-vendor.
    """
    manifest = json.loads(
        (VENDOR / "packages" / "session-ui" / "package.json").read_text(encoding="utf-8")
    )
    base = "../vendor/opencode/packages/session-ui/"
    paths: dict[str, list[str]] = {
        "@/*": ["../vendor/opencode/packages/app/src/*"],
        # The two runtime shims, so the checker sees what Vite resolves.
        "ghostty-web": ["./src/shims/ghostty.ts"],
        "@sentry/solid": ["./src/shims/sentry.ts"],
        "@opencode/ui/wordmark": ["./src/brand/wordmark.tsx"],
        "@opencode/ui/logo": ["./src/brand/logo.tsx"],
        # This product's own surfaces, and a deep path into session-ui's
        # source for the one module its exports map leaves out (the tool-card
        # registry). Vite's aliases in web/vite.config.ts say the same.
        "@harness/*": ["./src/harness/*"],
        "@session-ui-src/*": [base + "src/*"],
    }
    for key, target in (manifest.get("exports") or {}).items():
        name = "@opencode/session-ui" + ("" if key == "." else key[1:])
        paths[name] = [base + str(target).removeprefix("./")]
    out = {
        "//": "GENERATED by scripts/build_app_manifest.py from session-ui's exports map. Do not edit.",
        "compilerOptions": {"paths": paths},
    }
    (WEB / "tsconfig.paths.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8", newline=chr(10))
    return len(paths)


if __name__ == "__main__":
    main()
