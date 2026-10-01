import { createSignal, For, Show, type JSX } from "solid-js"
import { BasicTool } from "@opencode/session-ui/basic-tool"
import { Button } from "@opencode/ui/button"
import { Icon } from "@opencode/ui/icon"
import type { ToolProps } from "@session-ui-src/tools/tool-renderer"
import { requestPane } from "../bridge/events"
import { detachStage } from "../panes/stage-detach"

/**
 * The chrome every harness card wears: THEIR tool chrome.
 *
 * `BasicTool` is what their own tools render in (their trigger row, their
 * collapsible, their pending shimmer), so a harness card in the transcript
 * reads as one of theirs with a richer body rather than a different app
 * pasted in. The open state follows their timeline's disclosure store exactly
 * as their tools do - `open` is theirs when they have one - but a harness card
 * starts OPEN: the outgoing transcript's rule was that a verdict, a plan to
 * approve or a score never waits behind a chevron.
 */
export function CardFrame(props: {
  tool: ToolProps
  title: string
  subtitle?: string
  action?: JSX.Element
  children: JSX.Element
}) {
  return (
    <BasicTool
      icon="mcp"
      status={props.tool.status}
      hideDetails={props.tool.hideDetails}
      defaultOpen={props.tool.defaultOpen ?? true}
      open={props.tool.open}
      forceOpen={props.tool.forceOpen}
      locked={props.tool.locked}
      onOpenChange={(open) => {
        props.tool.onOpenChange?.(open)
        props.tool.onContentRendered?.()
      }}
      hasContent
      trigger={{ title: props.title, subtitle: props.subtitle, action: props.action }}
    >
      <div data-component="harness-card" class="flex flex-col gap-3 pt-2 pb-1 text-[13px] text-v2-text-text-base">
        {props.children}
      </div>
    </BasicTool>
  )
}

export type Tone = "good" | "bad" | "warn" | "info" | "muted"

const TONE_CLASS: Record<Tone, string> = {
  good: "text-v2-state-fg-success",
  bad: "text-v2-state-fg-danger",
  warn: "text-v2-state-fg-warning",
  info: "text-v2-state-fg-info",
  muted: "text-v2-text-text-muted",
}

/** A verdict word in a quiet chip. The hue is the rank; the word carries the claim. */
export function Pill(props: { tone: Tone; title?: string; children: JSX.Element }) {
  return (
    <span
      class={`inline-flex shrink-0 items-center rounded-sm px-1.5 py-px text-12-medium bg-v2-background-bg-layer-02 ${TONE_CLASS[props.tone]}`}
      title={props.title}
    >
      {props.children}
    </span>
  )
}

/** A block inside a card, with the small muted heading their panes use. */
export function Block(props: { title: string; hint?: string; action?: JSX.Element; children: JSX.Element }) {
  return (
    <section class="flex flex-col gap-1">
      <div class="flex items-center gap-2">
        <h4 class="text-12-medium text-v2-text-text-muted">{props.title}</h4>
        <Show when={props.hint}>
          <span class="min-w-0 truncate text-12-regular text-v2-text-text-faint">{props.hint}</span>
        </Show>
        <span class="flex-1" />
        {props.action}
      </div>
      {props.children}
    </section>
  )
}

/** Key/value pairs, one per line, the value in mono. */
export function Facts(props: { rows: readonly (readonly [string, JSX.Element | string | number | null | undefined])[] }) {
  return (
    <div class="flex flex-col gap-0.5">
      <For each={props.rows.filter(([, value]) => value !== null && value !== undefined && value !== "")}>
        {([key, value]) => (
          <div class="flex min-w-0 gap-3 text-12-regular">
            <span class="w-32 shrink-0 text-v2-text-text-muted">{key}</span>
            <span class="min-w-0 flex-1 break-words text-12-mono text-v2-text-text-base">{value}</span>
          </div>
        )}
      </For>
    </div>
  )
}

/** A paragraph in the engine's own words, muted. */
export function Note(props: { children: JSX.Element; tone?: Tone }) {
  return <p class={`text-12-regular ${TONE_CLASS[props.tone ?? "muted"]}`}>{props.children}</p>
}

/**
 * A disclosure for a long body - the browser's own, for its keyboard
 * semantics. `list-none` removes the browser's marker, so the chevron is
 * drawn here: without one a folded body reads as a heading with nothing under it.
 */
export function Fold(props: { summary: string; hint?: string; children: JSX.Element; open?: boolean }) {
  return (
    <details class="group" open={props.open}>
      <summary class="flex cursor-pointer list-none items-center gap-1 text-12-medium text-v2-text-text-muted">
        <span data-slot="fold-chevron" class="inline-flex shrink-0 transition-transform group-open:rotate-90">
          <Icon name="chevron-right" size="small" />
        </span>
        {props.summary}
        <Show when={props.hint}>
          <span class="text-12-regular text-v2-text-text-faint">{` · ${props.hint}`}</span>
        </Show>
      </summary>
      <div class="pt-1">{props.children}</div>
    </details>
  )
}

/**
 * "Open in panel" and "Pop out" for a result the Stage draws (parity 5.12,
 * sizes D and S). The pop-out is the Stage's own large window
 * (`open_stage`, via `detachStage`), not a pane-sized one.
 *
 * "Open in panel" asks the session mount through the bridge
 * (bridge/events.ts) with THIS card's thread. A session showing another
 * thread declines - its Stage would show the wrong run - and so does a window
 * with no session (a pop-out); either way the card pops its own thread's
 * Stage out instead of doing nothing.
 */
export function StageActions(props: { threadId: number | undefined }) {
  const [error, setError] = createSignal<string>()
  const popOut = () => {
    setError(undefined)
    if (props.threadId === undefined) {
      setError("No conversation is open to show this in.")
      return
    }
    detachStage(props.threadId).catch((failure: unknown) =>
      setError(failure instanceof Error ? failure.message : String(failure)),
    )
  }
  return (
    <div class="flex flex-wrap items-center gap-2">
      <Button
        size="small"
        variant="ghost"
        icon="window-analytics"
        onClick={() => {
          setError(undefined)
          if (!requestPane("stage", props.threadId)) popOut()
        }}
      >
        Open in panel
      </Button>
      <Show when={props.threadId !== undefined}>
        <Button size="small" variant="ghost" icon="outline-square-arrow" onClick={popOut}>
          Pop out
        </Button>
      </Show>
      <Show when={error()}>
        <span class="text-12-regular text-v2-state-fg-danger">{error()}</span>
      </Show>
    </div>
  )
}
