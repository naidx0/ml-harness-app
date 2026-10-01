import { createMemo, createSignal, For, Match, Show, Switch } from "solid-js"
import { Button } from "@opencode/ui/button"
import { Icon } from "@opencode/ui/icon"
import { TextInput } from "@opencode/ui/text-input"
import { harness } from "../engine"
import { shortModelName } from "../providers/local"
import { ErrorLine, kindIn, ProvenanceTag, Section, useHarnessRead, useHarnessRefresh, type Provenance } from "../ui"
import { sessionBridgePresent } from "../bridge/events"
import { pollWhile } from "./eval-events"
import { PaneEmpty } from "../panel/frame"
import type { PaneProps } from "../panel/panes"
import { tauriInvoke } from "../../platform/tauri"
import {
  compactNote,
  segments,
  share,
  thousands,
  turnBars,
  withheldSentence,
  type CompactResult,
  type ContextWindowRead,
  type Segment,
  type ThreadContext,
} from "./context-read"

/**
 * The context window, broken down into the pieces the prompt was built from.
 *
 * Max, 2026-09-13: "can we show the breakdown behind token and context
 * spend... it's an amazing and transparent breakdown." Every figure here was
 * counted on a prompt that was sent: the conductor names the pieces it
 * assembles a prompt FROM - the instruction set, the notes, the standing
 * brief, the tool schemas by pack, the conversation - and counts each with
 * the same `providers/budget.py` both adapters use to decide whether a turn
 * fits (`app/contextwindow.py::parts`). A breakdown of a string already
 * concatenated would be a guess; this is a measurement of the parts.
 *
 * What it is for: this product's own instructions and tool schemas can cost
 * more than a small model's whole window, and that is not a thing to
 * discover when a turn is refused.
 *
 * Below the breakdown, what is attached to the conversation - the folders
 * and files the harness can refer to - with a way to attach another. The
 * attach goes through the same `attach_context` tool a model calls, filed
 * under this thread as run by you.
 *
 * `GET /api/threads/{id}/context` is re-read every few seconds: a reading is
 * written once per turn, and a pane that also lives in a pop-out window has
 * no session event stream to wait on.
 */

const PROVENANCE: readonly Provenance[] = ["measured", "inferred", "declared", "defaulted", "untested_on_this_platform"]

function provenanceOf(value: string | undefined): Provenance | undefined {
  const lower = (value ?? "").toLowerCase()
  return PROVENANCE.find((each) => each === lower)
}

export default function ContextPane(props: PaneProps) {
  return (
    <Show
      when={props.threadId}
      // KEYED, like every per-thread pane: a new thread mounts new bodies, so
      // a compaction note or an in-flight state never carries across.
      keyed
      fallback={<PaneEmpty title="No conversation open">Open a conversation to see what its turns cost.</PaneEmpty>}
    >
      {(threadId) => (
        <>
          <Spend threadId={threadId} />
          <Attached threadId={threadId} />
        </>
      )}
    </Show>
  )
}

function Spend(props: { threadId: number }) {
  const context = useHarnessRead<ContextWindowRead>(() => `/api/threads/${props.threadId}/context`)
  // LIVE: re-read when a step of this chat ends or a tool answers - the two
  // things that grow the window (session/refresh.ts). The four-second poll it
  // used to run for ever is kept only where no session says so: a pop-out.
  useHarnessRefresh(props.threadId, () => void context.refetch(), kindIn("step.ended", "tool.result"))
  pollWhile(() => !sessionBridgePresent(), 4000, () => void context.refetch())
  const [compacting, setCompacting] = createSignal(false)
  const [note, setNote] = createSignal<string>()

  // `.latest` so a re-read keeps the last reading on screen instead of
  // throwing the pane back to its loading state every four seconds. The
  // error is read first because `.latest` rethrows it, and a reading for
  // another thread (the moment after switching) is not shown as this one's.
  const read = createMemo(() => {
    if (context.data.error) return
    const value = context.data.latest
    return value?.thread_id === props.threadId ? value : undefined
  })
  const latest = () => read()?.latest ?? undefined
  const window = () => read()?.window ?? null

  const compact = async () => {
    if (compacting()) return
    setCompacting(true)
    setNote(undefined)
    try {
      const result = await harness<CompactResult>(`/api/threads/${props.threadId}/compact`, { method: "POST" })
      setNote(compactNote(result))
      if (result.ok) void context.refetch()
    } catch (failure) {
      setNote(failure instanceof Error ? failure.message : String(failure))
    } finally {
      setCompacting(false)
    }
  }

  return (
    <>
      <Section
        title="Last prompt"
        action={
          <Button size="small" variant="ghost" disabled={compacting()} onClick={() => void compact()}>
            {compacting() ? "Compacting" : "Compact"}
          </Button>
        }
      >
        <Show when={note()}>{(text) => <div class="px-4 pb-1 text-12-regular text-v2-text-text-muted">{text()}</div>}</Show>
        <Switch>
          <Match when={context.data.error}>
            <ErrorLine error={context.data.error} />
          </Match>
          <Match when={!read()}>
            <div class="px-4 py-1 text-[13px] text-v2-text-text-faint">Reading…</div>
          </Match>
          <Match when={!latest()}>
            <div class="px-4 py-1 text-[13px] text-v2-text-text-muted">
              No turn has been sent in this conversation yet, so nothing has been counted. Every prompt is measured the
              moment it is assembled, and this pane is those measurements.
            </div>
          </Match>
          <Match when={latest()}>{(turn) => <Breakdown read={read()!} turn={turn()} window={window()} />}</Match>
        </Switch>
      </Section>

      <Show when={(read()?.turns.length ?? 0) > 1}>
        <Section title="What each turn cost">
          <TurnChart read={read()!} />
        </Section>
      </Show>

      <Show when={read()}>
        {(value) => (
          <Section title="Compactions">
            <Show
              when={value().compactions.length > 0}
              fallback={
                <div class="px-4 py-1 text-[13px] text-v2-text-text-muted">
                  Nothing has been compacted in this conversation yet.
                </div>
              }
            >
              <For each={value().compactions}>
                {(each) => (
                  <div class="px-4 py-1 text-[13px] text-v2-text-text-base tabular-nums">
                    <span class="text-[13px] [font-weight:530]">{thousands(each.messages_summarised)}</span> messages summarised ·{" "}
                    {thousands(each.tokens_before)} → {thousands(each.tokens_after)} tokens
                  </div>
                )}
              </For>
            </Show>
          </Section>
        )}
      </Show>
    </>
  )
}

function Breakdown(props: { read: ContextWindowRead; turn: NonNullable<ContextWindowRead["latest"]>; window: number | null }) {
  const bar = createMemo(() => segments(props.turn, props.window))
  const over = () => props.window !== null && props.turn.total > props.window
  const withheld = () => withheldSentence(props.turn.schemas_on_wire?.withheld?.length ?? 0)

  return (
    <div class="flex flex-col gap-2">
      <div class="flex flex-wrap items-baseline gap-x-2 gap-y-1 px-4">
        <span class="text-16-medium text-v2-text-text-base tabular-nums">{thousands(props.turn.total)}</span>
        <span class="text-[13px] text-v2-text-text-muted">
          tokens on the last prompt
          <Show when={props.window}>
            {(window) => (
              <>
                {" "}
                of {thousands(window())} ·{" "}
                <span class="text-[13px] [font-weight:530] text-v2-text-text-base">{share(props.turn.total, window())}</span> used
              </>
            )}
          </Show>
        </span>
        <ProvenanceTag value={provenanceOf(props.read.window_provenance)} source="the active connection's window" />
      </div>

      {/* One bar, a segment per part, free space last. */}
      <div
        class="mx-4 flex h-2 overflow-hidden rounded-full"
        style={{ background: "var(--v2-background-bg-layer-02)" }}
        role="img"
        aria-label={`${props.turn.total} tokens${props.window ? ` of ${props.window}` : ""}`}
      >
        <For each={bar().parts}>
          {(part) => (
            <span
              class="h-full"
              style={{ width: `${part.width.toFixed(2)}%`, background: part.colour }}
              title={`${part.label}: ${thousands(part.tokens)} tokens`}
            />
          )}
        </For>
      </div>

      <div class="flex flex-col">
        <For each={bar().parts}>{(part) => <PartRow part={part} window={props.window} />}</For>
        <Show when={bar().free}>{(free) => <PartRow part={free()} window={props.window} />}</Show>
      </div>

      <Show when={over()}>
        <div class="flex items-start gap-1.5 px-4 text-[13px] text-v2-state-fg-danger">
          <Icon name="circle-exclamation" size="small" class="mt-0.5 shrink-0" />
          <span>
            Over the window by <span class="text-[13px] [font-weight:530] tabular-nums">{thousands(props.turn.total - props.window!)}</span>{" "}
            tokens. A turn this size is refused before a byte is sent.
          </span>
        </div>
      </Show>

      {/* Which tools those schemas were. Without this line, "9 tool schemas"
          on a harness with eighty tools reads as "the harness has nine".
          Every withheld tool is still named and still callable -
          `blocks.on_the_wire` withholds the parameters, never the tool. */}
      <Show when={withheld()}>{(line) => <div class="px-4 text-12-regular text-v2-text-text-muted">{line()}</div>}</Show>

      <div class="px-4 text-12-regular text-v2-text-text-faint">
        {props.turn.messages} message{props.turn.messages === 1 ? "" : "s"} · {props.turn.tool_count} tool
        {props.turn.tool_count === 1 ? " schema" : " schemas"} sent · {props.turn.mode || "no"} mode ·{" "}
        <span title={props.read.model || undefined}>{shortModelName(props.read.model) || "no model"}</span>
        <Show when={props.window}> · the transcript is summarised past {thousands(props.read.compaction_at)} tokens</Show>
      </div>
    </div>
  )
}

function PartRow(props: { part: Segment; window: number | null }) {
  return (
    <div class="flex min-h-7 items-center gap-2 px-4 text-[13px]" title={props.part.why}>
      <span class="size-2 shrink-0 rounded-full" style={{ background: props.part.colour }} aria-hidden="true" />
      <span class="shrink-0 text-v2-text-text-base">{props.part.label}</span>
      <span class="min-w-0 flex-1 truncate text-12-regular text-v2-text-text-faint">{props.part.why}</span>
      <span class="shrink-0 text-v2-text-text-base tabular-nums">{thousands(props.part.tokens)}</span>
      <span class="w-10 shrink-0 text-right text-v2-text-text-muted tabular-nums">{share(props.part.tokens, props.window)}</span>
    </div>
  )
}

/**
 * Oldest at the left, drawn against the window when the model has a
 * measured one (see `turnBars`). Inline SVG with its colours taken from
 * their CSS variables through `style`, since a `var()` in a presentation
 * attribute is not honoured everywhere, so both themes read.
 */
function TurnChart(props: { read: ContextWindowRead }) {
  const bars = createMemo(() => turnBars(props.read.turns, props.read.window))
  const HEIGHT = 56
  const STEP = 10
  return (
    <div class="flex flex-col gap-1 px-4">
      <svg
        class="block h-14 w-full"
        viewBox={`0 0 ${bars().length * STEP} ${HEIGHT}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`Tokens per turn for the last ${bars().length} turns`}
      >
        <For each={bars()}>
          {(bar, index) => {
            const h = () => (bar.height / 100) * HEIGHT
            const latest = () => index() === bars().length - 1
            return (
              <rect
                x={index() * STEP + 1.5}
                y={HEIGHT - h()}
                width={STEP - 3}
                height={h()}
                rx={1}
                style={{
                  fill: bar.over
                    ? "var(--v2-state-fg-danger)"
                    : latest()
                      ? "var(--v2-avatar-border-blue)"
                      : "var(--v2-icon-icon-faint)",
                }}
              >
                <title>
                  {`${thousands(bar.total)} tokens${props.read.window ? ` · ${share(bar.total, props.read.window)} of the window` : ""}`}
                </title>
              </rect>
            )
          }}
        </For>
      </svg>
      <div class="flex justify-between text-[11px] text-v2-text-text-faint">
        <span>{bars().length} turns, oldest first</span>
        <span>{props.read.window ? `top of the chart is the ${thousands(props.read.window)}-token window` : "scaled to the largest turn"}</span>
      </div>
    </div>
  )
}

/** What is attached to this conversation, and a way to attach another. */
function Attached(props: { threadId: number }) {
  const contexts = useHarnessRead<{ thread_id: number; contexts: ThreadContext[] }>(
    () => `/api/threads/${props.threadId}/contexts`,
  )
  // An attachment the model makes arrives as a tool result; one made here
  // re-reads after its own request. The poll stays only in a pop-out.
  useHarnessRefresh(props.threadId, () => void contexts.refetch(), kindIn("tool.result"))
  pollWhile(() => !sessionBridgePresent(), 10000, () => void contexts.refetch())
  const rows = createMemo(() => {
    if (contexts.data.error) return []
    const value = contexts.data.latest
    return value?.thread_id === props.threadId ? value.contexts : []
  })
  const [path, setPath] = createSignal("")
  const [role, setRole] = createSignal("")
  const [busy, setBusy] = createSignal(false)
  const [message, setMessage] = createSignal<{ tone: "quiet" | "danger"; text: string }>()
  // The shell's native picker when there is one; a browser (npm run dev)
  // has no way to hand a page a real path, so there the text field is all.
  const invoke = tauriInvoke()

  const browse = async (kind: "directory" | "file") => {
    if (!invoke) return
    const chosen = await invoke("pick_path", { kind }).catch(() => null)
    if (typeof chosen === "string" && chosen.length > 0) setPath(chosen)
  }

  const attach = async () => {
    const target = path().trim()
    if (!target || busy()) return
    setBusy(true)
    setMessage(undefined)
    try {
      const answer = await harness<{ result?: { ok?: boolean; detail?: string; already_attached?: boolean } }>(
        "/api/tools/attach_context",
        {
          body: {
            arguments: role().trim() ? { path: target, role: role().trim() } : { path: target },
            approved: false,
            thread_id: props.threadId,
          },
        },
      )
      const result = answer?.result
      if (result?.ok === false) {
        setMessage({ tone: "danger", text: result.detail ?? "Nothing was attached." })
        return
      }
      setMessage({ tone: "quiet", text: result?.already_attached ? "That was already attached." : "Attached." })
      setPath("")
      setRole("")
      void contexts.refetch()
    } catch (failure) {
      setMessage({ tone: "danger", text: failure instanceof Error ? failure.message : String(failure) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Section title="Attached to this conversation">
      <Switch>
        <Match when={contexts.data.error}>
          <ErrorLine error={contexts.data.error} />
        </Match>
        <Match when={rows().length === 0}>
          <div class="px-4 py-1 text-[13px] text-v2-text-text-muted">
            Nothing is attached yet. Attaching records the path only: no file is copied and no folder is read.
          </div>
        </Match>
        <Match when={true}>
          <For each={rows()}>
            {(row) => (
              <div class="flex min-h-8 items-center gap-2 px-4 py-1 text-[13px]" title={row.path}>
                <Icon name={row.kind === "file" ? "code-slash" : "folder"} size="small" class="shrink-0 text-v2-icon-icon-muted" />
                <span class="min-w-0 flex-1 truncate text-12-mono text-v2-text-text-base" dir="rtl">
                  {/* Right-to-left so a long path keeps its end - the part that names it - in view. */}
                  <bdi>{row.path}</bdi>
                </span>
                <span class="max-w-32 shrink-0 truncate text-12-regular text-v2-text-text-muted">
                  {row.role || row.kind}
                </span>
              </div>
            )}
          </For>
        </Match>
      </Switch>

      <form
        class="flex flex-col gap-2 px-4 pt-2"
        onSubmit={(event) => {
          event.preventDefault()
          void attach()
        }}
      >
        <TextInput
          class="!w-full"
          placeholder="A folder, file or repository on this machine"
          aria-label="Path to attach"
          spellcheck={false}
          value={path()}
          onInput={(event) => setPath(event.currentTarget.value)}
        />
        <TextInput
          class="!w-full"
          placeholder="What it is to the project (optional)"
          aria-label="What it is to the project"
          value={role()}
          onInput={(event) => setRole(event.currentTarget.value)}
        />
        <div class="flex flex-wrap items-center gap-2">
          <Show when={invoke}>
            <Button type="button" size="small" variant="neutral" icon="folder" onClick={() => void browse("directory")}>
              Folder
            </Button>
            <Button type="button" size="small" variant="neutral" icon="code-slash" onClick={() => void browse("file")}>
              File
            </Button>
          </Show>
          <span class="flex-1" />
          <Button type="submit" size="small" variant="contrast" disabled={busy() || !path().trim()}>
            {busy() ? "Attaching" : "Attach"}
          </Button>
        </div>
        <Show when={message()}>
          {(line) => (
            <div
              class="text-12-regular"
              classList={{
                "text-v2-text-text-muted": line().tone === "quiet",
                "text-v2-state-fg-danger": line().tone === "danger",
              }}
            >
              {line().text}
            </div>
          )}
        </Show>
      </form>
    </Section>
  )
}
