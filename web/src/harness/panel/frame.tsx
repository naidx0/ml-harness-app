import { Show, type JSX } from "solid-js"
import { Icon } from "@opencode/ui/icon"
import { IconButton } from "@opencode/ui/icon-button"
import { Tooltip } from "@opencode/ui/tooltip"
import { POP_OUT_ICON, type PaneSpec } from "./panes"
import { popOut } from "./popout"

/**
 * The header every harness pane shares: its title, and a pop-out button
 * when there is a thread to follow. Their panels have no inner header, so
 * this one is kept to a single quiet line in their type scale.
 */
export function PaneFrame(props: { pane: PaneSpec; threadId: number | undefined; children: JSX.Element }) {
  return (
    <div class="flex h-full min-h-0 flex-col">
      <div class="flex h-10 shrink-0 items-center gap-2 px-4 text-[13px] [font-weight:530] text-v2-text-text-base">
        <Icon name={props.pane.icon} size="small" />
        <span class="flex-1 truncate">{props.pane.title}</span>
        <Show when={props.threadId}>
          {(threadId) => (
            <Tooltip value="Open in its own window" placement="bottom">
              <IconButton
                icon={<Icon name={POP_OUT_ICON} />}
                variant="ghost-muted"
                size="large"
                aria-label={`Open ${props.pane.title} in its own window`}
                onClick={() => void popOut(props.pane.id, threadId())}
              />
            </Tooltip>
          )}
        </Show>
      </div>
      <div class="min-h-0 flex-1 overflow-auto">{props.children}</div>
    </div>
  )
}

/** The empty state a pane shows when there is nothing for it yet. */
export function PaneEmpty(props: { title: string; children?: JSX.Element }) {
  return (
    <div class="flex h-full flex-col items-center justify-center gap-2 px-6 pb-16 text-center">
      <div class="text-14-medium text-v2-text-text-base">{props.title}</div>
      <Show when={props.children}>
        <div class="max-w-64 text-[13px] text-v2-text-text-muted">{props.children}</div>
      </Show>
    </div>
  )
}
