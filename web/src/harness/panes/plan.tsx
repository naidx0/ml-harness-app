import { createEffect, createMemo, createSignal, onCleanup, Show, untrack } from "solid-js"
import { Button } from "@opencode/ui/button"
import { ProgressCircle } from "@opencode/ui/progress-circle"
import { SegmentedControl, SegmentedControlItem } from "@opencode/ui/segmented-control"
import { harness } from "../engine"
import { askAboutStep } from "../bridge/compose"
import { requestCompose, sessionBridgePresent } from "../bridge/events"
import { PaneEmpty } from "../panel/frame"
import type { PaneProps } from "../panel/panes"
import { ErrorLine, useHarnessRead } from "../ui"
import {
  countSteps,
  everyStepSettled,
  planTitle,
  splitIntoPhases,
  stepsOf,
  tickedLine,
  toggleStepAt,
  unparkAt,
  type Step,
} from "./plan-model"
import { lastRunLine, workingLine, type RunState } from "./plan-run"
import { PlanEdit, PlanRead } from "./plan-views"

/**
 * The plan beside the chat, and the one control that works it down.
 *
 * Three surfaces of the outgoing frontend in one pane: the phase editor
 * (`PlanPanel`), the read view with live tick boxes (`PlanDocument`), and the
 * goal bar's run controls and per-step actions (`GoalBar`,
 * `TheBuildWorksDown`). They were three because the old shell had three
 * places to put them; here the plan has one tab, and a person who opens it
 * to read the plan is the same person who wants to run it.
 *
 * WHAT IS READ. `GET /api/threads/{id}` for the plan, because that route runs
 * `planfile.sync` first - if the plan file in the project folder changed, the
 * file wins - and carries `plan_path` so the pane can name it. `GET .../run`
 * for the engine's long run. Both are polled every three seconds while a run
 * is live, because the run ticks steps without any event reaching this window;
 * otherwise the pane re-reads after its own writes and on "Refresh".
 *
 * WHAT IS WRITTEN. Every edit - a saved phase, a tick, an unpark - is the
 * whole document through `POST /api/threads/{id}/plan`, the one door the old
 * panel, the old checkboxes and the old goal bar all used.
 */

type Thread = {
  id: number
  mode?: string | null
  plan?: string | null
  plan_path?: string | null
}

/** Reads a resource without falling over or flashing. Reading one in its
 *  error state throws, and a pane that re-reads on a timer must survive one
 *  failed poll; and `resource()` suspends on every re-read, which inside the
 *  panel's Suspense would swap the whole pane for "Opening..." every three
 *  seconds. `latest` suspends only on the first read. */
function settled<T>(resource: { latest: T | undefined; error?: unknown }): T | undefined {
  return resource.error ? undefined : resource.latest
}

function say(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

/** Reports already written from this window, by thread, so reopening the pane
 *  on a finished plan does not write the files again. */
const REPORTED = new Map<number, string>()

const WHILE_RUNNING = 3000

export default function PlanPane(props: PaneProps) {
  return (
    <Show
      when={props.threadId}
      keyed
      fallback={
        <PaneEmpty title="No conversation open">Open a conversation and its plan shows here, one phase at a time.</PaneEmpty>
      }
    >
      {(threadId) => <PlanForThread threadId={threadId} />}
    </Show>
  )
}

function PlanForThread(props: { threadId: number }) {
  const id = props.threadId
  const thread = useHarnessRead<{ thread: Thread }>(() => `/api/threads/${id}`)
  const run = useHarnessRead<RunState>(() => `/api/threads/${id}/run`)

  const row = () => settled(thread.data)?.thread
  const plan = () => row()?.plan ?? ""
  const runState = () => settled(run.data)
  const live = () => runState()?.state === "running"
  const counts = createMemo(() => countSteps(plan()))
  const steps = createMemo(() => stepsOf(plan()))
  const title = () => planTitle(plan()) || "Plan"
  const phaseCount = () => splitIntoPhases(plan()).filter((phase) => phase.heading).length

  // Polled only while the run is live: that is the only time the plan and
  // the run row change with nobody in this window pressing anything.
  createEffect(() => {
    if (!live()) return
    const timer = setInterval(() => {
      void run.refetch()
      void thread.refetch()
    }, WHILE_RUNNING)
    onCleanup(() => clearInterval(timer))
  })

  const [view, setView] = createSignal<"read" | "edit">("read")
  const [phaseAt, setPhaseAt] = createSignal(0)
  const [busy, setBusy] = createSignal(false)
  const [working, setWorking] = createSignal<number>()
  const [error, setError] = createSignal<string>()
  const [note, setNote] = createSignal<string>()
  const [runBusy, setRunBusy] = createSignal(false)

  const refresh = () => {
    void thread.refetch()
    void run.refetch()
  }

  /** Write the whole plan. The row the engine answers with is shown at once,
   *  then re-read, because only the GET carries `plan_path`. */
  const writePlan = async (next: string) => {
    const current = settled(thread.data)
    const saved = await harness<Thread>(`/api/threads/${id}/plan`, { body: { plan: next } })
    if (current) thread.mutate({ ...current, thread: { ...current.thread, ...saved } })
    void thread.refetch()
  }

  const edit = async (change: (text: string) => string) => {
    if (busy()) return
    const next = change(plan())
    if (next === plan()) return
    setBusy(true)
    setError(undefined)
    try {
      await writePlan(next)
    } catch (failure) {
      // The box goes back to what the engine holds, with the reason beside it.
      setError(say(failure))
      void thread.refetch()
    } finally {
      setBusy(false)
    }
  }

  /**
   * Work this step now: a message in the conversation and a turn, the same two
   * calls the old goal bar made through the composer (`POST .../messages`, then
   * `POST .../turn`). The message is real and the person sent it, so it is in
   * the transcript in their name; the facade shows a message from this door as
   * `msg_<row id>`. The turn call answers only when the turn is over, so it is
   * not awaited - its tokens reach the conversation through the event log.
   *
   * Disabled while a run is live, because two loops sending turns into one
   * conversation is the one shape neither can be reasoned about. A turn the
   * person started from the composer is not visible to this pane, which is the
   * same exposure the old goal bar had.
   */
  const work = async (step: Step) => {
    if (working() !== undefined || live()) return
    setWorking(step.line)
    setError(undefined)
    setNote(undefined)
    try {
      await harness(`/api/threads/${id}/messages`, { body: { content: `Work this step now: ${step.text}` } })
      setNote(`Sent to the conversation: work "${step.text}".`)
      void harness(`/api/threads/${id}/turn`, { body: {} })
        .catch((failure) => setError(say(failure)))
        .finally(() => void thread.refetch())
    } catch (failure) {
      setError(say(failure))
    } finally {
      setWorking(undefined)
    }
  }

  /**
   * Ask about this step: a draft in the session's composer for the person to
   * finish and send (the session mount writes it, bridge/events.ts). A pop-out
   * has no composer, so the draft goes to the clipboard and the pane says so.
   */
  const ask = async (step: Step) => {
    const text = askAboutStep(step.text)
    setError(undefined)
    setNote(undefined)
    if (requestCompose(text)) return
    try {
      await navigator.clipboard.writeText(text)
      setNote(`Copied "${text.trim()}" - paste it into the conversation in the main window and finish the question.`)
    } catch {
      setNote(`No composer here. In the main window, ask: ${text.trim()}`)
    }
  }

  const startRun = async () => {
    if (runBusy()) return
    setRunBusy(true)
    setError(undefined)
    try {
      // A 409 carries the engine's own sentence - "switch to Build first",
      // "every step is ticked or parked" - and it is shown as written.
      await harness(`/api/threads/${id}/run`, { method: "POST" })
    } catch (failure) {
      setError(say(failure))
    } finally {
      setRunBusy(false)
      void run.refetch()
    }
  }

  const stopRun = async () => {
    if (runBusy()) return
    setRunBusy(true)
    try {
      // Ends after the turn in flight: a turn already running finishes and is
      // recorded, and the run takes no other.
      await harness(`/api/threads/${id}/run/stop`, { method: "POST" })
    } catch (failure) {
      setError(say(failure))
    } finally {
      setRunBusy(false)
      refresh()
    }
  }

  /* THE REPORT WRITES ITSELF. The owner, 2026-09-12: "save the journey report
     into this project's folder on disk - it should automatically save, you
     shouldn't have to even click that." When every step of a Build plan is
     ticked or parked, the report is written into the project folder once per
     thread from this window. A project with no folder answers 400 with the
     fix in the sentence, and that sentence is shown with a way to try again. */
  const [report, setReport] = createSignal<{ ok: boolean; detail: string }>()
  const saveReport = async () => {
    REPORTED.set(id, "Writing the journey report…")
    setReport({ ok: true, detail: REPORTED.get(id)! })
    try {
      const outcome = await harness<{ ok: boolean; detail: string }>(`/api/threads/${id}/report/save`, { body: {} })
      REPORTED.set(id, outcome.detail)
      setReport({ ok: true, detail: outcome.detail })
    } catch (failure) {
      REPORTED.delete(id)
      setReport({ ok: false, detail: say(failure) })
    }
  }
  createEffect(() => {
    const current = row()
    if (!current || (current.mode ?? "build") !== "build") return
    if (!everyStepSettled(counts())) return
    // Untracked: this effect answers to the plan, never to its own outcome,
    // or setting the outcome would run it again.
    untrack(() => {
      const already = REPORTED.get(id)
      if (already !== undefined) {
        if (report()?.detail !== already) setReport({ ok: true, detail: already })
        return
      }
      // A failed write waits for "Try again": the fix (attach a folder) is the
      // person's, and re-trying on every re-read would only repeat the refusal.
      if (report()?.ok === false) return
      void saveReport()
    })
  })

  const next = () => steps().find((step) => step.state === "open")?.line
  const percent = () => (counts().total ? Math.round((counts().done / counts().total) * 100) : 0)

  return (
    <Show
      when={!thread.data.error}
      fallback={
        <div class="flex flex-col py-2">
          <ErrorLine error={thread.data.error} />
          <div class="px-4">
            <Button size="small" variant="ghost" onClick={refresh}>
              Try again
            </Button>
          </div>
        </div>
      }
    >
      <Show
        when={plan().trim()}
        fallback={
          <PaneEmpty title={thread.data.loading ? "Reading the plan…" : "No plan yet"}>
            <Show when={!thread.data.loading}>
              Plan mode is a conversation with the harness. When the shape of the work is agreed it writes the plan out
              in phases, and leaving Plan mode saves it here.
            </Show>
          </PaneEmpty>
        }
      >
        <div class="flex flex-col">
          <header class="flex flex-col gap-1 px-4 pt-2 pb-1">
            <div class="flex items-center gap-2">
              <h2 class="min-w-0 flex-1 truncate text-14-medium leading-6! text-v2-text-text-base" title={title()}>
                {title()}
              </h2>
              <Button size="small" variant="ghost" onClick={refresh} disabled={thread.data.loading}>
                {thread.data.loading ? "Reading" : "Refresh"}
              </Button>
            </div>
            <div class="text-12-regular leading-5! text-v2-text-text-muted tabular-nums">
              {[`${phaseCount()} phase${phaseCount() === 1 ? "" : "s"}`, tickedLine(counts())].filter(Boolean).join(" · ")}
            </div>
            <Show when={row()?.plan_path}>
              {(path) => (
                <div
                  class="truncate font-mono text-[11px] leading-4 text-v2-text-text-faint"
                  title="Edit this file and the harness adopts it; the harness writes it on every change"
                >
                  {path()}
                </div>
              )}
            </Show>
          </header>

          {/* THE GOAL BAR: how far down the plan is, and the one control that
              can start or stop the engine's run of it. */}
          <div class="mx-4 my-2 flex flex-col gap-1 rounded-sm bg-v2-background-bg-layer-01 px-3 py-2">
            <div class="flex items-center gap-2">
              <Show when={counts().total}>
                <ProgressCircle percentage={percent()} size={16} />
              </Show>
              <span class="min-w-0 flex-1 truncate text-12-regular leading-5! text-v2-text-text-base tabular-nums">
                {live() ? workingLine(runState()) : counts().open ? `${counts().open} step${counts().open === 1 ? "" : "s"} open` : "Nothing open"}
              </span>
              <Show
                when={live()}
                fallback={
                  <Show when={counts().open > 0}>
                    <Button
                      size="small"
                      variant="neutral"
                      disabled={runBusy()}
                      onClick={() => void startRun()}
                      title="Work the whole plan down in the engine: one turn per step, until every step is ticked or parked. It keeps going if you close this window, and stops on an approval, a failed connection or the turn cap."
                    >
                      Run the plan
                    </Button>
                  </Show>
                }
              >
                <Button
                  size="small"
                  variant="ghost"
                  icon="stop"
                  disabled={runBusy()}
                  onClick={() => void stopRun()}
                  title="Stop after the turn that is running. A turn already in flight finishes and is recorded."
                >
                  Stop
                </Button>
              </Show>
            </div>
            <Show when={lastRunLine(runState())}>
              {(line) => (
                <div class="truncate text-12-regular leading-5! text-v2-text-text-muted" title={runState()?.detail || undefined}>
                  {line()}
                  {runState()?.detail ? ` — ${runState()!.detail}` : ""}
                </div>
              )}
            </Show>
            <Show when={run.data.error}>
              <div class="text-12-regular leading-5! text-v2-text-text-muted">The run's state could not be read.</div>
            </Show>
            <Show when={report()}>
              {(outcome) => (
                <div class="flex items-center gap-2 text-12-regular leading-5!">
                  <span class="min-w-0 flex-1" classList={{ "text-v2-text-text-muted": outcome().ok, "text-v2-state-fg-danger": !outcome().ok }}>
                    {outcome().detail}
                  </span>
                  <Show when={!outcome().ok}>
                    <Button size="small" variant="ghost" onClick={() => void saveReport()}>
                      Try again
                    </Button>
                  </Show>
                </div>
              )}
            </Show>
          </div>

          <Show when={error()}>{(message) => <ErrorLine error={message()} />}</Show>
          <Show when={note()}>
            {(message) => <div class="px-4 py-1 text-12-regular leading-5! text-v2-text-text-muted">{message()}</div>}
          </Show>

          <div class="flex items-center px-4 py-1">
            <SegmentedControl
              value={view()}
              onChange={(value) => {
                if (value === "read" || value === "edit") setView(value)
              }}
            >
              <SegmentedControlItem value="read">Read</SegmentedControlItem>
              <SegmentedControlItem value="edit">Edit</SegmentedControlItem>
            </SegmentedControl>
          </div>

          <Show
            when={view() === "edit"}
            fallback={
              <PlanRead
                plan={plan()}
                actions={{
                  get busy() {
                    return busy()
                  },
                  get next() {
                    return next()
                  },
                  get live() {
                    return live()
                  },
                  get working() {
                    return working()
                  },
                  onTick: (step) => void edit((text) => toggleStepAt(text, step.line)),
                  onUnpark: (step) => void edit((text) => unparkAt(text, step.line)),
                  onWork: (step) => void work(step),
                  onAsk: (step) => void ask(step),
                  get canCompose() {
                    return sessionBridgePresent()
                  },
                }}
                onEditPhase={(index) => {
                  setPhaseAt(index)
                  setView("edit")
                }}
              />
            }
          >
            <PlanEdit plan={plan()} at={phaseAt()} onAt={setPhaseAt} onSave={writePlan} />
          </Show>
        </div>
      </Show>
    </Show>
  )
}
