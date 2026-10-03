/// <reference types="vitest/config" />
import { readFileSync } from "node:fs"
import { createRequire } from "node:module"
import { fileURLToPath } from "node:url"
import { defineConfig, type Plugin } from "vite"
import solidPlugin from "vite-plugin-solid"
import tailwindcss from "@tailwindcss/vite"

/**
 * Derived from OpenCode's `packages/app/vite.js` and `vite.config.ts`
 * (MIT, commit ad1a4a6). See THIRD-PARTY-NOTICES.txt.
 *
 * Theirs is written for their monorepo and their Electron shell. This keeps
 * what makes their source compile and drops what is about being OpenCode:
 * Sentry, the PWA service worker, their icon channel plugin, the desktop
 * channel define.
 */

const here = (relative: string) => fileURLToPath(new URL(relative, import.meta.url))
const require = createRequire(import.meta.url)

const SESSION_UI = "../vendor/opencode/packages/session-ui"

/**
 * Resolve `@opencode/session-ui` and its subpaths through THEIR OWN exports
 * map rather than by guessing at the directory layout.
 *
 * A plain prefix alias is wrong here and fails in a way that looks like a
 * missing file: `@opencode/session-ui/file` is not `src/file`, it is
 * `src/components/file.tsx`, and there are forty such entries including two
 * wildcards. Hardcoding them would work today and rot on the next re-vendor.
 *
 * So the map is read from the vendored `package.json` at build time. Upstream
 * adds an export, it resolves; upstream moves one, it follows. The package is
 * not installed into node_modules because its manifest carries sixteen
 * `catalog:` entries npm cannot read, and rewriting that manifest would break
 * byte-identity with the pinned commit.
 */
function sessionUiExports(): Plugin {
  const root = here(SESSION_UI)
  const manifest = require(`${root}/package.json`) as {
    exports?: Record<string, string>
  }
  const map = manifest.exports ?? {}

  // Longest first, so "./pierre/*" is tried before "./*" would be.
  const wildcards = Object.entries(map)
    .filter(([key]) => key.includes("*"))
    .sort((a, b) => b[0].length - a[0].length)
  const exact = Object.entries(map).filter(([key]) => !key.includes("*"))

  const PACKAGE = "@opencode/session-ui"

  return {
    name: "harness:session-ui-exports",
    enforce: "pre",
    resolveId(id) {
      if (id !== PACKAGE && !id.startsWith(`${PACKAGE}/`)) return null
      const subpath = id === PACKAGE ? "." : `./${id.slice(PACKAGE.length + 1)}`

      for (const [key, target] of exact) {
        if (key === subpath) return `${root}/${target.replace(/^\.\//, "")}`
      }
      for (const [key, target] of wildcards) {
        const [before, after] = key.split("*")
        if (!subpath.startsWith(before!) || !subpath.endsWith(after ?? "")) continue
        const star = subpath.slice(before!.length, subpath.length - (after ?? "").length)
        return `${root}/${target.replace("*", star).replace(/^\.\//, "")}`
      }
      // Not in their map. Returning null lets Vite report it against the real
      // import site rather than this plugin inventing a path that does not
      // exist and failing three layers down.
      return null
    },
  }
}

/**
 * `npm run dev` in a browser, against the engine this checkout is running.
 *
 * Inside the desktop shell the window finds its engine through the shell. A
 * browser cannot read `engine.json` off disk, so this dev-only plugin does
 * the two things the shell does: it publishes the engine's token on
 * `/__engine/session`, and it proxies `/oc` to the engine so the page's
 * requests are same-origin. The proxy strips `Origin`, because the engine
 * refuses browser origins other than its own - a Node proxy is not a browser,
 * and the engine still checks the token on every request. The same arrangement,
 * and the same reasoning, as the outgoing frontend's `vite.config.ts`.
 */
const PORTFILE = process.env.MLH_ENGINE_FILE ?? here("../engine.json")

function readPortfile(): { base_url?: string; token?: string } | undefined {
  try {
    return JSON.parse(readFileSync(PORTFILE, "utf-8"))
  } catch {
    return undefined
  }
}

function engineSession(): Plugin {
  return {
    name: "harness:engine-session",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use("/__engine/session", (_request, response) => {
        const portfile = readPortfile()
        response.setHeader("Content-Type", "application/json")
        response.setHeader("Cache-Control", "no-store")
        response.end(
          JSON.stringify(
            portfile?.token
              ? { token: portfile.token }
              : { error: `No engine.json at ${PORTFILE}. Start the engine: python -m uvicorn app.main:app --port 8078` },
          ),
        )
      })
    },
  }
}

/**
 * Replace a vendored module with ours, matched by RESOLVED path.
 *
 * A string alias only catches the spelling it names. Their code reaches most
 * modules by relative imports (`./header/session-header-actions`), which no
 * alias sees. This resolves the import the normal way first and swaps the
 * result when it is one of the files listed here - whatever spelling reached
 * it. The replacement itself is exempt, so it can import the original and
 * wrap it rather than copy it: a copy of their code would drift, a wrapper
 * cannot.
 *
 * Keys are paths relative to the vendored app's `src`. Each entry is one
 * decision recorded in docs/PHASE-5-SURFACES.md.
 */
const SUBSTITUTES: Record<string, string> = {
  // The harness's foothold in the session tree; wraps theirs.
  "session/header/session-header-actions.tsx": "./src/harness/session/header-actions.tsx",
  // One Context view: their ring opens their context tab, which is this -
  // the harness view plus the readouts theirs showed.
  "session/files/session-context-tab.tsx": "./src/harness/panel/context-tab.tsx",
  // Surfaces with no backing here, drawn as nothing or as the part that
  // works (each file says which and why; web/src/harness/settings/unbacked.ts).
  "session/summary/server-panel.tsx": "./src/harness/panel/unbacked/server-panel.tsx",
  "new-session/workspace/selector.tsx": "./src/harness/panel/unbacked/workspace-selector.tsx",
  "settings/search-catalog.ts": "./src/harness/settings/search-catalog.ts",
  // Home as one column: the sidebar has projects, Settings and New chat
  // (docs/onboarding-ui-plan.md, slice 3).
  "home/route.tsx": "./src/harness/home/route.tsx",
  // Their English strings with this product's name and claims.
  "runtime/i18n/en.ts": "./src/brand/strings.ts",
}

function harnessSubstitutes(): Plugin {
  const vendored = here("../vendor/opencode/packages/app/src")
  const norm = (path: string) => path.split(String.fromCharCode(92)).join("/").toLowerCase()
  const table = new Map(
    Object.entries(SUBSTITUTES).map(([from, to]) => [norm(`${vendored}/${from}`), here(to)]),
  )
  const replacements = new Set([...table.values()].map(norm))
  const names = Object.keys(SUBSTITUTES).map((from) => from.replace(/\.[^./]+$/, "").split("/").pop()!)
  return {
    name: "harness:substitutes",
    enforce: "pre",
    async resolveId(id, importer, options) {
      // A cheap filter before the real resolve: the LAST path segment, minus
      // any extension, must name a substituted file. `includes` was enough
      // until a target was called `en`, which nearly every import contains.
      const last = id.split("/").pop()?.replace(/\.[^.]+$/, "")
      if (!importer || !last || !names.includes(last)) return null
      if (replacements.has(norm(importer))) return null
      // AN ID THAT IS ALREADY THE ORIGINAL'S ABSOLUTE PATH IS LEFT ALONE.
      // Vitest's module runner re-resolves a resolved id with the page as its
      // importer, so the original a wrapper imported came back as the wrapper
      // - a self-import whose names were undefined. Their source reaches these
      // files by relative or `@/` specifiers, never by absolute path.
      if (table.has(norm(id))) return null
      const resolved = await this.resolve(id, importer, { ...options, skipSelf: true })
      if (!resolved) return null
      return table.get(norm(resolved.id)) ?? null
    },
  }
}

export default defineConfig({
  plugins: [
    sessionUiExports(),
    engineSession(),
    harnessSubstitutes(),
    tailwindcss(),
    // After Tailwind: the Solid transform must run on JSX that Tailwind's
    // scanner has already read.
    solidPlugin(),
  ],

  resolve: {
    // ONE REACTIVE RUNTIME, OR CONTEXT SILENTLY DOES NOT MATCH. The vendored
    // source lives outside this root, so it resolves solid-js from the hoisted
    // node_modules while Vite's dep optimizer hands pre-bundled packages its
    // own copy. Two instances, two sets of context symbols, and every
    // `useContext` throws "must be used within a context provider" while the
    // provider is plainly right there in the tree. Deduping is the fix and it
    // has to name the subpaths too, because they are separate entry points.
    dedupe: ["solid-js", "solid-js/web", "solid-js/store", "@solidjs/router", "@solidjs/meta"],

    alias: {
      // `@` is theirs, and hundreds of their files import through it. Pointed
      // at the vendored app source, because that is the tree those imports
      // were written against.
      "@": here("../vendor/opencode/packages/app/src"),

      // TELEMETRY IS REMOVED, NOT DISABLED. Their app imports @sentry/solid in
      // three places. Installing it and leaving the DSN unset would ship a
      // telemetry client and trust a config value to keep it quiet; aliasing
      // it to a local no-op means the real module is not in the tree at all.
      "@sentry/solid": here("./src/shims/sentry.ts"),

      // THEIR APP ICONS ARE TRADEMARK, not copyright, and sit outside the MIT
      // grant - so packages/desktop/icons is deliberately not vendored and
      // their titlebar's two imports of it resolve to our own marks instead.
      // Phase 2 replaces these placeholders with the real identity.
      "../../../../desktop/icons/dev/64x64.png": here("./src/brand/mark-dev.png"),
      "../../../../desktop/icons/beta/64x64.png": here("./src/brand/mark-beta.png"),

      // Their terminal emulator, a multi-megabyte WebAssembly package pinned to
      // a GitHub commit. The harness has no terminal surface, so it resolves to
      // a stub that throws if anything ever mounts it - louder than a blank
      // pane with no explanation.
      "ghostty-web": here("./src/shims/ghostty.ts"),

      // THEIR WORDMARK IS TRADEMARK, and MIT grants copyright only. It is
      // substituted rather than restyled, so their lettering never ships under
      // this product's name. The replacement keeps their prop surface exactly,
      // because their call sites pass all four.
      "@opencode/ui/wordmark": here("./src/brand/wordmark.tsx"),
      // And their logo module: `Logo` is the "opencode" lettering itself.
      "@opencode/ui/logo": here("./src/brand/logo.tsx"),

      // This product's own surfaces. The deep path reaches the one session-ui
      // module their exports map leaves out: the tool-card registry.
      "@harness": here("./src/harness"),
      "@session-ui-src": here(`${SESSION_UI}/src`),
    },
  },

  // Their workers are ES modules and break if bundled as classic scripts.
  worker: { format: "es" },

  optimizeDeps: {
    // Pre-bundling Solid is what creates the second instance above.
    exclude: ["solid-js", "@opencode/ui", "@opencode/session-ui"],
  },

  server: {
    port: 3100,
    strictPort: true,
    // The facade for their client, and the harness's own routes for ours.
    proxy: Object.fromEntries(
      // Trailing slashes: a proxy key is a PREFIX, and a bare "/oc" also took
      // "/oc-theme-preload.js" from public/ and sent it to the engine.
      ["/oc/", "/api/", "/health", "/local_specs"].map((prefix) => [
        prefix,
        {
          // NO PORTFILE, NO ENGINE. This used to fall back to 8078, which is
          // the installed app's engine: a dev server started before its
          // scratch engine had written its portfile read the owner's live
          // database (2026-09-23). A port nothing listens on fails loudly.
          target: readPortfile()?.base_url ?? "http://127.0.0.1:1",
          configure: (proxy: { on: (event: "proxyReq", fn: (request: { removeHeader(name: string): void }) => void) => void }) => {
            proxy.on("proxyReq", (request) => {
              request.removeHeader("origin")
              request.removeHeader("referer")
            })
          },
        },
      ]),
    ),
  },

  // happy-dom rather than jsdom because it is what their own suite runs on,
  // and a platform that behaves differently under two DOMs is a platform whose
  // tests prove the DOM rather than the code.
  test: {
    environment: "happy-dom",
    // COLD IMPORTS, NOT SLOW TESTS. A test that imports a pane or their
    // renderer pulls a large vendored graph through Vite's transform on first
    // use; on a cold cache that crossed vitest's 5 s default in two files
    // (the Eval thread-switch case at exactly 5,000 ms, passing in 1.7 s
    // warm). The gate runs vitest cold, so the budget is set for that, once,
    // here - a per-file fix would leave the next file to find it again.
    testTimeout: 30_000,
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },

  build: {
    assetsDir: "_assets",
    target: "esnext",
    sourcemap: true,
  },
})
