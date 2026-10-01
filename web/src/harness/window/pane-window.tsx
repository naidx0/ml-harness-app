import { createMemo, lazy, Show, Suspense } from "solid-js"
import { Icon } from "@opencode/ui/icon"
import { IconButton } from "@opencode/ui/icon-button"
import { tauriInvoke } from "../../platform/tauri"
import { windowPaneOf } from "../panel/panes"
import { PaneEmpty } from "../panel/frame"

/**
 * A harness pane in a window of its own.
 *
 * The shell opens these (`open_pane` -> `?pane=<id>&thread=<n>`, and
 * `open_stage` -> `?stage=<n>`) as frameless windows. There is no session and
 * no OpenCode layout here - which is why every pane is built from their UI
 * library and the harness client alone - so this draws the minimum a window
 * needs: a drag strip with a title and a close button, and the pane.
 */
export function HarnessPaneWindow(props: { pane: string; threadId: number | undefined }) {
  const spec = createMemo(() => windowPaneOf(props.pane))
  const close = () => {
    const invoke = tauriInvoke()
    if (invoke) void invoke("window_close")
    else window.close()
  }
  return (
    <div class="flex h-dvh flex-col bg-v2-background-bg-base text-v2-text-text-base">
      <div
        class="flex h-9 shrink-0 items-center gap-2 px-3 text-[13px] [font-weight:530] [app-region:drag]"
        data-tauri-drag-region
      >
        <Show when={spec()}>{(pane) => <Icon name={pane().icon} size="small" />}</Show>
        <span class="flex-1 truncate" data-tauri-drag-region>
          {spec()?.title ?? "Harness"}
          <Show when={props.threadId}>
            {(id) => <span class="text-v2-text-text-muted"> · thread {id()}</span>}
          </Show>
        </span>
        <IconButton
          icon={<Icon name="close" />}
          variant="ghost-muted"
          size="large"
          aria-label="Close this window"
          class="[app-region:no-drag]"
          onClick={close}
        />
      </div>
      <div class="min-h-0 flex-1 overflow-auto">
        <Show when={spec()} fallback={<PaneEmpty title="Unknown panel">{props.pane}</PaneEmpty>}>
          {(pane) => {
            const Pane = lazy(pane().load)
            return (
              <Suspense fallback={<PaneEmpty title={`Opening ${pane().title}`} />}>
                <Pane threadId={props.threadId} />
              </Suspense>
            )
          }}
        </Show>
      </div>
    </div>
  )
}

/** `?pane=plan&thread=7` or `?stage=7`, or nothing for the main window. */
export function paneWindowRequest(search: string): { pane: string; threadId: number | undefined } | undefined {
  const query = new URLSearchParams(search)
  const stage = query.get("stage")
  if (stage !== null) return { pane: "stage", threadId: toId(stage) }
  const pane = query.get("pane")
  if (pane) return { pane, threadId: toId(query.get("thread")) }
}

function toId(value: string | null) {
  const id = Number(value)
  return value !== null && Number.isInteger(id) && id > 0 ? id : undefined
}
