import { createEffect, createMemo, createSignal, For, Index, onCleanup, Show } from "solid-js"
import { Button } from "@opencode/ui/button"
import { Icon } from "@opencode/ui/icon"
import { Tooltip } from "@opencode/ui/tooltip"
import { requestOpenThread, sessionBridgePresent } from "../bridge/events"
import { harness } from "../engine"
import { PaneEmpty } from "../panel/frame"
import type { PaneProps } from "../panel/panes"
import { ErrorLine, kindIn, Section, useHarnessRead, useHarnessRefresh } from "../ui"
import { boardHeadline, clock, endingInWords, howLong, type SubAgent, type SubAgentRead } from "./agents-model"

/**
 * What the sub-agents this conversation handed out are doing.
 *
 * `GET /api/threads/{id}/subagents` (app/subagents.py). A sub-agent's own
 * progress writes events on its CHILD conversation, which nothing in this
 * window is reading, so the board polls every three seconds while any of them
 * is working - the only time the answer can change without anyone here
 * pressing anything - and stops polling when they are all back.
 *
 * The same read also folds finished work back into the parent's plan
 * (`subagents.read` harvests), so a poll here is what makes a child's result
 * reach the plan within one tick of it ending, whoever else is looking.
 *
 * Colour follows the outgoing board: success for a phase that came back whole,
 * warning for one that parked steps, danger for one that failed. A working one
 * is plain text with its clock running.
 */

const WHILE_WORKING = 3000

/** Reads a resource without falling over or flashing. Reading one in its
 *  error state throws, and a pane that re-reads on a timer must survive one
 *  failed poll; and `resource()` suspends on every re-read, which inside the
 *  panel's Suspense would swap the whole pane for "Opening..." every three
 *  seconds. `latest` suspends only on the first read. */
function settled<T>(resource: { latest: T | undefined; error?: unknown }): T | undefined {
  return resource.error ? undefined : resource.latest
}

export default function AgentsPane(props: PaneProps) {
  return (
    <Show
      when={props.threadId}
      keyed
      fallback={<PaneEmpty title="No conversation open">Open a conversation to see the sub-agents it sent out.</PaneEmpty>}
    >
      {(threadId) => <AgentsForThread threadId={threadId} />}
    </Show>
  )
}

function AgentsForThread(props: { threadId: number }) {
  const id = props.threadId
  const board = useHarnessRead<SubAgentRead>(() => `/api/threads/${id}/subagents`)
  /* The child's title. A child is created with its phase heading as its
     title, but a person can rename a conversation, and the name they gave it
     is how they will find it in the sidebar. Read once, not polled: titles do
     not change while work runs. Not read while loading, so the board never
     waits on a nicety. */
  const threads = useHarnessRead<{ id: number; title?: string | null }[]>(() => "/api/threads")
  const titles = createMemo(
    () => new Map(((threads.data.loading ? undefined : settled(threads.data)) ?? []).map((row) => [row.id, row.title ?? ""])),
  )

  const read = () => settled(board.data)
  const working = () => (read()?.running ?? 0) > 0

  // LIVE: the board re-reads on this chat's sub-agent and run events
  // (`subagent.started/finished/harvested`, `run.*`; session/refresh.ts). The
  // poll below stays as the fallback while one is working.
  useHarnessRefresh(id, () => void board.refetch(), kindIn("subagent", "run"))
  createEffect(() => {
    if (!working()) return
    const timer = setInterval(() => void board.refetch(), WHILE_WORKING)
    onCleanup(() => clearInterval(timer))
  })

  const [stopping, setStopping] = createSignal<number>()
  const [error, setError] = createSignal<unknown>()
  const stop = async (one: SubAgent) => {
    setStopping(one.id)
    setError(undefined)
    try {
      // Stops after the turn it is in; a tool already running finishes.
      await harness(`/api/subagents/${one.id}/stop`, { method: "POST" })
    } catch (failure) {
      setError(failure)
    } finally {
      setStopping(undefined)
      void board.refetch()
    }
  }

  const refresh = () => {
    void board.refetch()
    void threads.refetch()
  }

  return (
    <Show
      when={!board.data.error}
      fallback={
        <div class="flex flex-col py-2">
          <ErrorLine error={board.data.error} />
          <div class="px-4">
            <Button size="small" variant="ghost" onClick={refresh}>
              Try again
            </Button>
          </div>
        </div>
      }
    >
      <Show
        when={read()?.subagents.length}
        fallback={
          <PaneEmpty title={board.data.loading ? "Reading…" : "No sub-agents yet"}>
            <Show when={!board.data.loading}>
              When a Build turn hands a phase to a worker, it appears here with its status, its packs, and Stop.
            </Show>
          </PaneEmpty>
        }
      >
        <Section
          title={read() ? boardHeadline(read()!) : "Sub-agents"}
          action={
            <Button size="small" variant="ghost" onClick={refresh} disabled={board.data.loading}>
              {board.data.loading ? "Reading" : "Refresh"}
            </Button>
          }
        >
          <Show when={(read()?.running_anywhere ?? 0) > (read()?.running ?? 0)}>
            <div class="px-4 pb-1 text-12-regular text-v2-text-text-muted">
              {read()!.running_anywhere - read()!.running} more working in another conversation -{" "}
              {read()!.at_most} at a time is the whole machine, not this conversation.
            </div>
          </Show>
          <Show when={error()}>
            <ErrorLine error={error()} />
          </Show>
          <div class="flex flex-col gap-2 px-4 pb-4">
            {/* By position, not by object: every poll returns fresh objects, and
                a list keyed by reference would rebuild each card every three
                seconds and fold away the one a person had opened. */}
            <Index each={read()?.subagents ?? []}>
              {(one) => (
                <AgentCard
                  one={one()}
                  title={titles().get(one().thread_id)}
                  stopping={stopping() === one().id}
                  onStop={() => void stop(one())}
                />
              )}
            </Index>
          </div>
        </Section>
      </Show>
    </Show>
  )
}

/**
 * The sub-agent's own conversation, opened in this tab the way their timeline
 * opens a child session (the session mount resolves the thread to its session
 * and navigates; bridge/events.ts). A pop-out has no session to navigate, so
 * there the button is disabled and says where it works.
 */
function OpenConversation(props: { threadId: number }) {
  return (
    <Tooltip
      value={sessionBridgePresent() ? "Read what this sub-agent did, in its own conversation" : "Open from the main window"}
      placement="top"
    >
      <Button
        size="small"
        variant="ghost-muted"
        disabled={!sessionBridgePresent()}
        onClick={() => requestOpenThread(props.threadId)}
      >
        Open conversation
      </Button>
    </Tooltip>
  )
}

function AgentCard(props:{ one: SubAgent; title: string | undefined; stopping: boolean; onStop: () => void }) {
  const one = () => props.one
  const running = () => one().state === "running"
  const share = () => (one().steps ? Math.round((one().done / one().steps) * 100) : 0)
  const tone = () =>
    one().state === "failed"
      ? "text-v2-state-fg-danger"
      : one().parked.length
        ? "text-v2-state-fg-warning"
        : running()
          ? "text-v2-text-text-muted"
          : "text-v2-state-fg-success"
  const [open, setOpen] = createSignal(false)
  const renamed = () => (props.title && props.title.trim() && props.title.trim() !== one().phase ? props.title.trim() : "")

  return (
    <div class="flex flex-col gap-1.5 rounded-sm bg-v2-background-bg-layer-01 px-3 py-2">
      <div class="flex items-start gap-2">
        <Icon name={running() ? "subagent" : one().state === "failed" ? "circle-x" : "circle-check"} size="small" class={`mt-0.5 shrink-0 ${tone()}`} />
        <div class="min-w-0 flex-1">
          <div class="text-[13px] [font-weight:530] text-v2-text-text-base break-words">{one().phase}</div>
          <Show when={renamed()}>
            <div class="truncate text-12-regular text-v2-text-text-muted">Conversation: {renamed()}</div>
          </Show>
        </div>
        <span class={`shrink-0 text-12-regular tabular-nums ${tone()}`}>
          {running() ? howLong(one().seconds) || "working" : endingInWords(one())}
        </span>
        <Show when={running()}>
          <Button size="small" variant="ghost" icon="stop" disabled={props.stopping} onClick={props.onStop}>
            {props.stopping ? "Stopping" : "Stop"}
          </Button>
        </Show>
      </div>

      {/* The steps it was given: ticked, parked, and the rest still to do. */}
      <div class="flex flex-wrap gap-x-3 gap-y-0.5 text-12-regular text-v2-text-text-muted tabular-nums">
        <span>{one().done} done</span>
        <Show when={one().parked.length}>
          <span class="text-v2-state-fg-warning">{one().parked.length} parked</span>
        </Show>
        <Show when={one().open}>
          <span>{one().open} to go</span>
        </Show>
        <Show when={one().turns}>
          <span>
            {one().turns} turn{one().turns === 1 ? "" : "s"}
          </span>
        </Show>
        {/* What it spent to get there: steps say how far it got, this says the cost. */}
        <Show when={one().tools_run}>
          <span title={`${one().tools_distinct ?? 0} different tools${one().tools_failed ? `, ${one().tools_failed} refused` : ""}`}>
            {one().tools_run} tool{one().tools_run === 1 ? "" : "s"}
          </span>
        </Show>
        <Show when={one().context_peak_tokens}>
          <span title="The widest this worker's prompt ever got">{one().context_peak_tokens!.toLocaleString()} tok</span>
        </Show>
      </div>

      <div class="h-1 overflow-hidden rounded-sm bg-v2-background-bg-layer-03" aria-hidden="true">
        <div class="h-full bg-v2-icon-icon-muted" style={{ width: `${share()}%` }} />
      </div>

      {/* When it went out and when it came back, which the counts cannot say. */}
      <Show when={clock(one().started_at)}>
        <div class="flex flex-wrap gap-x-3 text-[11px] text-v2-text-text-faint tabular-nums">
          <span>sent {clock(one().started_at)}</span>
          <Show when={!running() && clock(one().updated_at)} fallback={<Show when={running()}><span>still out</span></Show>}>
            <span>back {clock(one().updated_at)}</span>
          </Show>
          <Show when={!running() && one().seconds != null}>
            <span>{howLong(one().seconds)}</span>
          </Show>
        </div>
      </Show>

      {/* Why a step was parked, in the sub-agent's own words. The orchestrator
          gets counts and one line; the person gets the reasons. */}
      <For each={one().parked.slice(0, 3)}>
        {(parked) => (
          <div class="text-12-regular text-v2-text-text-muted break-words" title={`${parked.step} - ${parked.why}`}>
            <span class="text-v2-text-text-base">{parked.step}</span> - {parked.why}
          </div>
        )}
      </For>
      <Show when={one().parked.length > 3}>
        <div class="text-12-regular text-v2-text-text-faint">and {one().parked.length - 3} more, in its own conversation</div>
      </Show>

      <Show when={one().state === "failed" && (one().detail || one().reason)}>
        <div class="text-12-regular text-v2-state-fg-danger break-words">{one().detail || one().reason}</div>
      </Show>

      <div class="flex items-center gap-1">
        <Show when={one().brief || one().tool_names?.length || one().last_digest || one().packs?.length}>
          <Button size="small" variant="ghost-muted" onClick={() => setOpen((was) => !was)}>
            {open() ? "Less" : "What it was told and ran"}
          </Button>
        </Show>
        {/* Every card, detail or not: the child conversation is where the
            whole of what it did can be read. */}
        <OpenConversation threadId={one().thread_id} />
      </div>

      <Show when={open()}>
        <div class="flex flex-col gap-2 pt-1">
          <Show when={one().packs?.length}>
            <div class="text-12-regular text-v2-text-text-muted" title="Packs this worker's turn loads">
              {one().packs!.join(" · ")}
            </div>
          </Show>
          <Show when={one().brief}>
            <div class="flex flex-col gap-0.5">
              <div class="text-[11px] text-v2-text-text-faint">Its instructions</div>
              <pre class="max-h-64 overflow-auto whitespace-pre-wrap rounded-sm bg-v2-background-bg-layer-02 px-2 py-1.5 font-mono text-[11px] text-v2-text-text-base">
                {one().brief}
              </pre>
            </div>
          </Show>
          <Show when={one().tool_names?.length}>
            <div class="flex flex-col gap-0.5">
              <div class="text-[11px] text-v2-text-text-faint">
                Tools it ran · {one().tools_run} call{one().tools_run === 1 ? "" : "s"} across {one().tools_distinct} tool
                {one().tools_distinct === 1 ? "" : "s"}
              </div>
              <div class="flex flex-wrap gap-1">
                <For each={one().tool_names ?? []}>
                  {(tool) => (
                    <span class="rounded-sm bg-v2-background-bg-layer-02 px-1.5 py-px font-mono text-[11px] text-v2-text-text-base">
                      {tool.name}
                      <Show when={tool.times > 1}>
                        <span class="text-v2-text-text-muted"> x{tool.times}</span>
                      </Show>
                    </span>
                  )}
                </For>
              </div>
            </div>
          </Show>
          <Show when={one().last_digest}>
            <div class="text-12-regular text-v2-text-text-base break-words">{one().last_digest}</div>
          </Show>
        </div>
      </Show>
    </div>
  )
}
