import { children, createResource, createSignal, onCleanup, Show, type JSX } from "solid-js"
import { harness } from "./engine"

/**
 * Small pieces every harness pane shares, drawn in OpenCode's type scale and
 * tokens so a harness pane reads as part of their panel rather than a
 * different app pasted into it.
 */

/** Where a number came from - the harness's provenance vocabulary. */
export type Provenance = "measured" | "inferred" | "declared" | "defaulted" | "untested_on_this_platform"

const TAG: Record<Provenance, string> = {
  measured: "Measured",
  inferred: "Inferred",
  declared: "Declared",
  defaulted: "Default",
  untested_on_this_platform: "Untested",
}

export function ProvenanceTag(props: { value: Provenance | undefined; source?: string }) {
  return (
    <Show when={props.value}>
      {(value) => (
        <span
          class="rounded-sm px-1.5 py-px text-[11px] text-v2-text-text-muted bg-v2-background-bg-layer-02"
          title={props.source ? `From: ${props.source}` : undefined}
        >
          {TAG[value()]}
        </span>
      )}
    </Show>
  )
}

/**
 * The hover text for a row's value: the caller's `title` when given, else the
 * value itself when it is plain text. The value is truncated to one line, so
 * without this a long path or model name could not be read at all.
 */
export function rowTitle(title: string | undefined, value: unknown): string | undefined {
  if (title !== undefined) return title
  if (typeof value === "string" || typeof value === "number") return String(value)
  if (Array.isArray(value) && value.length > 0 && value.every((part) => typeof part === "string" || typeof part === "number")) {
    return value.join("")
  }
  return undefined
}

/** A label, a value, and an optional tag - one row of a readout. */
export function Row(props: { label: string; children: JSX.Element; tag?: JSX.Element; title?: string }) {
  // Resolved ONCE: reading `props.children` twice would build the value's
  // DOM twice, once for the body and once for the title.
  const value = children(() => props.children)
  return (
    <div class="flex min-h-8 items-center gap-3 px-4 py-1 text-[13px]">
      <span class="w-32 shrink-0 text-v2-text-text-muted">{props.label}</span>
      <span
        class="min-w-0 flex-1 truncate text-v2-text-text-base tabular-nums"
        title={rowTitle(props.title, value())}
      >
        {value()}
      </span>
      {props.tag}
    </div>
  )
}

/** A section heading inside a pane. */
export function Section(props: { title: string; action?: JSX.Element; children: JSX.Element }) {
  return (
    <section class="flex flex-col py-2">
      <div class="flex items-center gap-2 px-4 pb-1">
        <h3 class="flex-1 text-12-medium text-v2-text-text-muted">{props.title}</h3>
        {props.action}
      </div>
      {props.children}
    </section>
  )
}

/**
 * Read a harness route, with a refresh. `poll` re-reads on an interval for
 * the few readouts that change while a run is going and have no event yet.
 */
export function useHarnessRead<T>(path: () => string | undefined, options: { poll?: number } = {}) {
  // OUR OWN IN-FLIGHT FLAG. Solid's `resource.loading` stayed true after the
  // read had answered and its value was on screen - their app opens panel
  // tabs inside a transition, which holds resource states open - so a
  // "Checking" button never came back. This counts only our own requests.
  const [pending, setPending] = createSignal(0)
  // WHICH PATH LAST ANSWERED. `loading` is false both before the first read
  // goes out and after it answers, so a pane that asked "loading?" drew its
  // empty-state line ("No eval run yet") before the read had said anything.
  // `answered` is true only once a read of the CURRENT path has settled,
  // with a value or an error; a path that changes goes back to unanswered.
  const [settledFor, setSettledFor] = createSignal<string | undefined>(undefined, { equals: false })
  const [resource, { refetch, mutate }] = createResource(path, async (value) => {
    setPending((n) => n + 1)
    try {
      return await harness<T>(value)
    } finally {
      setPending((n) => n - 1)
      setSettledFor(value)
    }
  })
  if (options.poll) {
    const timer = setInterval(() => void refetch(), options.poll)
    onCleanup(() => clearInterval(timer))
  }
  // READ `latest`, NOT THE RESOURCE. Calling the resource inside the panel's
  // Suspense boundary suspends it on every re-read, so each refresh or poll
  // replaced the whole pane with "Opening…" for a moment. `latest` keeps
  // the last value on screen while the next one loads; `loading` still says
  // a read is in flight for anything that wants to show it.
  // REAL GETTERS. `Object.assign` copies a getter's VALUE once, at creation,
  // so an earlier version froze `loading` at true and `error` at undefined:
  // the "Checking" button never came back and no failed read ever showed its
  // error. `defineProperties` keeps them live.
  const read = () => resource.latest
  const data = Object.defineProperties(read, {
    latest: { get: () => resource.latest },
    state: { get: () => resource.state },
    loading: { get: () => pending() > 0 },
    answered: {
      get: () => {
        const current = path()
        return current !== undefined && settledFor() === current
      },
    },
    // Solid types a resource's error as `any`; kept, so callers that read
    // fields off it are not broken by the wrapper.
    error: { get: () => resource.error },
  }) as typeof read & {
    readonly latest: T | undefined
    readonly state: typeof resource.state
    readonly loading: boolean
    readonly answered: boolean
    readonly error: any
  }
  return { data, refetch, mutate }
}

/**
 * The session's word that the engine changed something for a thread
 * (session/refresh.ts sends it; the kinds are listed there). A pop-out has no
 * session, hears nothing, and keeps its polling.
 */
export const HARNESS_CHANGED_EVENT = "harness:changed"
export type HarnessChange = { threadId: number; kind: string }

function readChange(detail: unknown): HarnessChange | undefined {
  const record = detail as { threadId?: unknown; kind?: unknown } | null
  const threadId = record?.threadId
  const kind = record?.kind
  if (typeof threadId !== "number" || !Number.isInteger(threadId) || threadId <= 0) return undefined
  return typeof kind === "string" && kind ? { threadId, kind } : undefined
}

/** How long a burst of changes is gathered into one re-read. An eval that
 *  grades a row a moment says so every 25 rows; a turn ends a step, returns
 *  a tool result and records a fact within milliseconds - one read, not four. */
export const HARNESS_REFRESH_GATHER_MS = 250

/**
 * Re-read when the engine changed something for THIS thread. `kinds` narrows
 * it to the events that can change what the pane shows (every kind when
 * omitted). A burst is gathered into one call. Returns nothing; the listener
 * and any pending call go with the owner.
 */
export function useHarnessRefresh(
  threadId: number | (() => number | undefined),
  refetch: () => void,
  kinds?: (kind: string) => boolean,
  target: EventTarget = window,
) {
  let timer: ReturnType<typeof setTimeout> | undefined
  const listener = (event: Event) => {
    const change = readChange((event as CustomEvent).detail)
    const current = typeof threadId === "function" ? threadId() : threadId
    if (!change || current === undefined || change.threadId !== current) return
    if (kinds && !kinds(change.kind)) return
    if (timer !== undefined) return
    timer = setTimeout(() => {
      timer = undefined
      refetch()
    }, HARNESS_REFRESH_GATHER_MS)
  }
  target.addEventListener(HARNESS_CHANGED_EVENT, listener)
  onCleanup(() => {
    target.removeEventListener(HARNESS_CHANGED_EVENT, listener)
    if (timer !== undefined) clearTimeout(timer)
  })
}

/** A kind by its family: `kindIn("eval", "tool.result")` takes `eval.progress` and `tool.result`. */
export function kindIn(...families: string[]) {
  return (kind: string) => families.some((family) => kind === family || kind.startsWith(`${family}.`))
}

/**
 * What an empty list means, which is three different things: the read is
 * still out, the read FAILED, or the engine answered with nothing. Settings
 * said "Nothing is connected yet" and "No projects yet" when the read had
 * failed, which tells a person their setup is empty when it is only unread.
 */
export type ListPhase = "reading" | "failed" | "empty"
export function listPhase(read: { answered: boolean; error: unknown }): ListPhase {
  if (read.error) return "failed"
  if (!read.answered) return "reading"
  return "empty"
}

/** An engine error as a sentence, in their danger colour. */
export function ErrorLine(props: { error: unknown }) {
  return (
    <div class="px-4 py-2 text-[13px] text-v2-state-fg-danger">
      {props.error instanceof Error ? props.error.message : String(props.error)}
    </div>
  )
}
