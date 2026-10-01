import { createWebPlatform } from "@/runtime/platform/web"
import type { Platform } from "@/runtime/platform/platform"
import { createCarriedFetch } from "./carrier"

/**
 * OpenCode's `Platform`, implemented for this product's Tauri shell.
 *
 * Their app is shell-agnostic by construction: `grep -rl electron
 * packages/app/src` returns nothing, and everything a host provides comes
 * through this one interface, supplied by `PlatformProvider`. They ship two
 * implementations - `createWebPlatform()` for a browser and an Electron one in
 * `packages/desktop`, which is not vendored. This is the third.
 *
 * Every member maps onto a shell command (see `src-tauri/src/lib.rs`), reached
 * through the same `__TAURI_INTERNALS__` detection the outgoing React app uses.
 *
 *   openDirectoryPickerDialog -> `pick_path { kind: "directory" }`
 *   openExternal              -> `window.open`, as the React app already does
 *   notify                    -> the webview's own Notification API
 *   restart                   -> a UI reload, and deliberately NOTHING MORE
 *   fetch                     -> `engine_stream`, for requests to this machine
 *
 * The one addition to the shell is `engine_stream`: their client reads its
 * event stream as a live response body, and the old `engine_fetch` could only
 * hand a body back once it had ended. See `carrier.ts`.
 *
 * Outside the shell it returns their web platform unchanged, so `npm run dev`
 * in a browser keeps working and nothing has to know which host it is in.
 */

type Invoke = (command: string, args?: Record<string, unknown>) => Promise<unknown>

interface TauriWindow {
  __TAURI_INTERNALS__?: { invoke?: Invoke }
  __TAURI__?: { core?: { invoke?: Invoke } }
}

/**
 * Both globals are checked because which one exists depends on
 * `withGlobalTauri` in tauri.conf.json - the same reasoning, and the same two
 * names, as `frontend/src/lib/engine/shell.ts`.
 */
export function tauriInvoke(): Invoke | null {
  if (typeof window === "undefined") return null
  const host = window as unknown as TauriWindow
  return host.__TAURI_INTERNALS__?.invoke ?? host.__TAURI__?.core?.invoke ?? null
}

function detectOS(): "macos" | "windows" | "linux" {
  const agent = typeof navigator === "object" ? navigator.userAgent.toLowerCase() : ""
  if (agent.includes("windows")) return "windows"
  if (agent.includes("mac os") || agent.includes("macintosh")) return "macos"
  return "linux"
}

/** The one window this shell opens. Their persistence scopes some state by it. */
export const WINDOW_ID = "main"

/**
 * Their web implementation fetches its notification icon from opencode.ai,
 * which is a network request and their brand. This product's mark, bundled.
 */
const NOTIFICATION_ICON = new URL("../brand/mark-dev.png", import.meta.url).href

export function createTauriPlatform(version: string) {
  const web = createWebPlatform(version)
  const invoke = tauriInvoke()
  if (!invoke) return { ...web, native: false as const }

  const platform: Platform = {
    // Keep what the web one does well and has no native equivalent to beat:
    // the draft store, and the default-server memory.
    ...web.platform,

    platform: "desktop",
    os: detectOS(),
    windowID: WINDOW_ID,

    // Every request their client makes - the event stream included - goes
    // through here, so this is what keeps the window's traffic to its own
    // engine out of the browser's networking rules.
    fetch: createCarriedFetch((command, args) => invoke(command, args)),

    openExternal(value) {
      // Their validation, kept: a model-authored link must not become a
      // `file:` or `javascript:` navigation just because it was clicked.
      if (!URL.canParse(value)) return
      const url = new URL(value)
      if (url.protocol !== "http:" && url.protocol !== "https:" && url.protocol !== "mailto:") return
      window.open(url.href, "_blank", "noopener,noreferrer")
    },

    /**
     * A UI restart, NOT an engine restart - and that difference is the reason
     * this comment is long.
     *
     * The shell has a `restart_engine` command and it is tempting to call it
     * here. Their app calls `restart()` to apply a setting or an update, i.e.
     * "relaunch the window". Mapping that onto the engine would kill whatever
     * the engine is doing, and what the engine is doing is often a twenty-
     * minute eval. The engine is a separate process precisely so it outlives
     * the webview. Restarting the engine stays an explicit act, behind its own
     * button.
     */
    restart: async () => {
      window.location.reload()
    },

    async notify(title, description, onClick) {
      if (!("Notification" in window)) return
      const permission =
        Notification.permission === "default"
          ? await Notification.requestPermission().catch(() => "denied" as const)
          : Notification.permission
      if (permission !== "granted") return
      // Their rule, kept: do not notify someone who is already looking.
      if (document.visibilityState === "visible" && document.hasFocus()) return
      const notification = new Notification(title, { body: description ?? "", icon: NOTIFICATION_ICON })
      notification.onclick = () => {
        window.focus()
        onClick?.()
        notification.close()
      }
    },

    async openDirectoryPickerDialog() {
      // `pick_path` is single-selection. Their `multiple` option is therefore
      // not honoured, and returning one path where several were asked for is
      // the honest degradation - their callers already accept a string.
      const chosen = await invoke("pick_path", { kind: "directory" }).catch(() => null)
      return typeof chosen === "string" && chosen.length > 0 ? chosen : null
    },
  }

  return { ...web, platform, native: true as const }
}
