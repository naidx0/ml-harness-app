import { tauriInvoke } from "../../platform/tauri"

/**
 * Open the Stage in its own large window.
 *
 * Inside the shell this is `open_stage` (src-tauri/src/lib.rs): one window
 * labelled `stage`, rebuilt rather than re-pointed when it already exists,
 * loading `index.html?stage=<id>`. Outside the shell a browser popup does the
 * same job at the same query string - one page, two hosts, as the outgoing
 * `openStageWindow` put it. This is not the frame's generic pop-out: that
 * opens `?pane=stage`, a pane-sized window; the Stage window is the size the
 * lattice and the loss curve were drawn for.
 */
export async function detachStage(threadId: number): Promise<"shell" | "browser"> {
  const invoke = tauriInvoke()
  if (invoke) {
    await invoke("open_stage", { threadId })
    return "shell"
  }
  const url = new URL(window.location.href)
  url.search = new URLSearchParams({ stage: String(threadId) }).toString()
  url.hash = ""
  window.open(url.href, "mlh-stage", "width=1280,height=800")
  return "browser"
}

/** True inside the detached Stage window, where "Detach" would reopen itself. */
export function isStageWindow(): boolean {
  return typeof window !== "undefined" && new URLSearchParams(window.location.search).has("stage")
}
