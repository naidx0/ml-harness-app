import { Show } from "solid-js"
import { usePlatform } from "@/runtime/platform/platform"
import { tauriInvoke } from "./tauri"

/**
 * Minimize, maximize and close, in the gap their titlebar leaves for them.
 *
 * Their Windows desktop app is Electron with a `titleBarOverlay`: Windows
 * draws the three caption buttons natively, and their titlebar reserves 138px
 * on the right for them (`windowsControlsBaseWidth`, three buttons at 46px).
 * Tauri has no overlay, and this shell is frameless, so the gap was empty -
 * a window with no way to close or minimize it, found by launching the built
 * app. The buttons are drawn here, fixed into that gap, at the same size, and
 * call the shell's existing window commands. Close is the same door as the
 * native close box: the window hides to the tray and the engine keeps running.
 *
 * Dragging needs nothing: their titlebar already carries
 * `data-tauri-drag-region`.
 */
const BUTTON = "flex h-9 w-[46px] items-center justify-center text-v2-icon-icon-muted hover:bg-v2-overlay-simple-overlay-hover hover:text-v2-icon-icon-base focus-visible:outline-none [app-region:no-drag]"

export function WindowControls() {
  const platform = usePlatform()
  const invoke = tauriInvoke()
  const call = (command: string) => () => void invoke?.(command)
  return (
    <Show when={invoke && platform.platform === "desktop" && platform.os === "windows"}>
      <div class="fixed end-0 top-0 z-50 flex h-9" style={{ direction: "ltr" }}>
        <button type="button" class={BUTTON} aria-label="Minimize" onClick={call("window_minimize")}>
          <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
            <path d="M0 5h10" stroke="currentColor" stroke-width="1" />
          </svg>
        </button>
        <button type="button" class={BUTTON} aria-label="Maximize" onClick={call("window_toggle_maximize")}>
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true">
            <rect x="0.5" y="0.5" width="9" height="9" stroke="currentColor" stroke-width="1" />
          </svg>
        </button>
        <button
          type="button"
          class={`${BUTTON} hover:!bg-[#c42b1c] hover:!text-white`}
          aria-label="Close"
          onClick={call("window_close")}
        >
          <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
            <path d="M0 0l10 10M10 0L0 10" stroke="currentColor" stroke-width="1" />
          </svg>
        </button>
      </div>
    </Show>
  )
}
