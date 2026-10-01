// @refresh reload

/**
 * The mount point, and the seam this product owns.
 *
 * Adapted from OpenCode's `packages/app/src/entry.tsx` (MIT, commit ad1a4a6).
 * See THIRD-PARTY-NOTICES.txt.
 *
 * WHY THIS FILE EXISTS RATHER THAN POINTING `index.html` AT THEIRS. Everything
 * else in the interface is theirs, vendored byte-for-byte and aliased to
 * source, so that an upstream diff stays possible. This is the one file that is
 * ours from the first line: it is where the platform, the server connection and
 * later the harness's own providers are decided. Keeping it here means those
 * decisions never become a local edit inside the vendored tree, which is the
 * thing that would quietly make re-vendoring lossy.
 *
 * Three things are deliberately dropped from theirs, each recorded rather than
 * silently absent:
 *
 *   - Sentry. A local-first product does not phone home.
 *   - The service worker. There is nothing to cache across a network we do not
 *     cross, and a stale worker is a debugging tax.
 *   - The PWA standalone/route-restore path. This runs in a desktop window.
 *
 * The platform is `createTauriPlatform()`: their `Platform` mapped onto the
 * shell's commands, falling back to their web platform in a browser.
 *
 * THE SERVER IS DECIDED HERE, BEFORE THEIR APP MOUNTS. Their app, given no
 * server, opens a "connect to a server" screen with a URL and a password. This
 * product is one package - the window and its engine ship together - so there
 * is nothing to connect to by hand. Inside the shell the engine is found or
 * started (`platform/engine.ts`) and handed over as their built-in `sidecar`
 * connection. In a browser under `npm run dev`, the dev server proxies `/oc`
 * to the running engine and publishes its token on `/__engine/session`.
 */

import "@/runtime/polyfills"
import { render } from "solid-js/web"
import { AppBaseProviders, AppInterface } from "@/app"
import { loadInitialLocale } from "@/runtime/i18n/language"
import { PlatformProvider } from "@/runtime/platform/platform"
import { createTauriPlatform, tauriInvoke } from "./platform/tauri"
import { engineServer, ensureEngine } from "./platform/engine"
import { facadeFetch } from "./platform/facade-fetch"
import { showStarting } from "./platform/starting"
import { OpenDefaultWorkspace } from "./platform/open-default-workspace"
import { setHarnessEngine } from "./harness/engine"
// Before render: their tool renderer looks cards up once per part, not reactively.
import "./harness/cards/register"
import { HarnessRoot } from "./harness/root"
import { EngineNotice } from "./harness/engine/notice"
import { WindowControls } from "./platform/window-controls"
import { HarnessPaneWindow, paneWindowRequest } from "./harness/window/pane-window"
import { KeyboardInsets } from "@/runtime/platform/keyboard"
import en from "@/runtime/i18n/en"
import { ServerConnection } from "@/runtime/server/registry"
import { ApplyHarnessTheme } from "./brand/apply-theme"
// After their stylesheets, so the typefaces and the first-paint ground win
// on source order. See the file for why one rule is !important.
// The product's one display face, bundled: Sora, in the three cuts
// identity.css asks for (brand/identity.test.ts holds the two together).
import "@fontsource/sora/400.css"
import "@fontsource/sora/500.css"
import "@fontsource/sora/600.css"
import "./brand/identity.css"

const VERSION = "0.1.0"

const root = document.getElementById("root")

if (!(root instanceof HTMLElement)) {
  // Their message, because the cause is the same one.
  throw new Error(en["error.dev.rootNotFound"] ?? "No #root element to mount into")
}

// The Tauri platform inside the shell, their web platform outside it -
// decided once, here, so nothing downstream has to ask which host it is in.
const web = createTauriPlatform(VERSION)

const MARK = new URL("./brand/mark-dev.png", import.meta.url).href

/**
 * The engine's connection, however this host provides it. Throws with a
 * sentence a person can act on.
 */
async function resolveServer(progress: (message: string) => void): Promise<ServerConnection.Any> {
  const invoke = tauriInvoke()
  if (invoke) {
    const call = (command: string, args?: Record<string, unknown>) => invoke(command, args)
    return engineServer(call, await ensureEngine(call, progress))
  }
  const session = (await fetch("/__engine/session", { cache: "no-store" })
    .then((response) => response.json())
    .catch(() => ({}))) as { token?: string; error?: string }
  if (!session.token) throw new Error(session.error ?? "No engine is running for this dev server.")
  return {
    type: "http",
    displayName: "This computer",
    http: { url: location.origin, password: session.token },
  }
}

// Their guard, kept verbatim in intent: a lazily-loaded chunk can import the
// entry back under a different URL, so the root is claimed before any async
// startup rather than after it.
if (root.dataset.opencodeMounted === undefined) {
  root.dataset.opencodeMounted = ""
  const screen = showStarting(root, MARK)

  const boot = async () => {
    const [locale, server] = await Promise.all([loadInitialLocale(), resolveServer(screen.progress)])
    // Two fetches over one wire: the harness's own surfaces get it as is, and
    // their client gets it with the facade prefix restored (facade-fetch.ts).
    const wire = web.platform.fetch ?? globalThis.fetch.bind(globalThis)
    setHarnessEngine(server, wire)
    web.platform.fetch = facadeFetch(wire, server.http.url)
    screen.remove()
    // A pop-out pane window (the shell's open_pane / open_stage) renders the
    // pane alone: no session, no layout, the same engine.
    const popout = paneWindowRequest(location.search)
    if (popout) {
      render(
        () => (
          <PlatformProvider value={web.platform}>
            <AppBaseProviders locale={locale}>
              <ApplyHarnessTheme />
              <HarnessPaneWindow pane={popout.pane} threadId={popout.threadId} />
            </AppBaseProviders>
          </PlatformProvider>
        ),
        root,
      )
      return
    }
    render(
      () => (
        <PlatformProvider value={web.platform}>
          <AppBaseProviders locale={locale}>
            <AppInterface
              servers={[server]}
              defaultServer={ServerConnection.key(server)}
              canonicalLocalServer={ServerConnection.key(server)}
            >
              <ApplyHarnessTheme />
              <KeyboardInsets />
              <OpenDefaultWorkspace server={server} />
              <HarnessRoot />
              <EngineNotice />
              <WindowControls />
            </AppInterface>
          </AppBaseProviders>
        </PlatformProvider>
      ),
      root,
    )
  }

  const attempt = () =>
    boot().catch((error: unknown) => {
      screen.failed(error instanceof Error ? error.message : String(error), attempt)
    })
  void attempt()
}
