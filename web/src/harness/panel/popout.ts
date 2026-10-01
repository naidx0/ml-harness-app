import { tauriInvoke } from "../../platform/tauri"

/**
 * Open a pane in its own window.
 *
 * The shell already has the command (`open_pane` in src-tauri/src/lib.rs): it
 * opens `index.html?pane=<id>&thread=<n>` in a window labelled
 * `pane-<id>-<n>`, and focuses that window instead of opening a second one.
 * Outside the shell a browser popup does the same job at the same URL.
 */
export async function popOut(pane: string, threadId: number) {
  const invoke = tauriInvoke()
  if (invoke) {
    await invoke("open_pane", { pane, threadId })
    return
  }
  const url = new URL(window.location.href)
  url.search = new URLSearchParams({ pane, thread: String(threadId) }).toString()
  url.hash = ""
  window.open(url.href, `pane-${pane}-${threadId}`, "width=920,height=760")
}
