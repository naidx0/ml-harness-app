import { createEffect, createMemo, onCleanup, type Accessor } from "solid-js"
import { useHarnessRead } from "../ui"

/**
 * A thread's event log, read once, as the panes need it.
 *
 * The outgoing app folded eval reports, diagnoses, recall reports and carves
 * out of the transcript it already held. A harness pane has no transcript: it
 * must also render in a pop-out window with no OpenCode session around it.
 * So it reads the same durable log the transcript was folded from,
 * `GET /api/events?scope=thread:{id}&since=0&follow=false` (app/main.py).
 *
 * `follow=false` is what makes this a plain request rather than a stream. The
 * engine's generator returns after its first pass, and the first pass is
 * history, folded by `events.fold_replay` so three thousand token deltas come
 * back as one row per reply. The response therefore ENDS, and the whole body
 * can be read as text and parsed here. `harness()` hands back an SSE body as
 * its raw text because the body is not JSON.
 */

export type ThreadEvent = { id: number; kind: string; payload: unknown }

/**
 * Parse a server-sent events body into frames.
 *
 * The engine writes `id:`, `event:` and one `data:` line per frame
 * (`events.frame`), and a bare `: keep-alive` comment between passes when it
 * follows. The parser still implements the general rules - several `data:`
 * lines join with a newline, one leading space after the colon is dropped,
 * CRLF and CR line endings count - because a proxy or a carrier that
 * re-chunks the body is allowed to, and a frame lost to a line ending is a
 * run missing from a picker with nothing on screen to say so.
 */
export function parseSse(body: string): ThreadEvent[] {
  const out: ThreadEvent[] = []
  const blocks = body.replace(/\r\n?/g, "\n").split(/\n\n+/)
  for (const block of blocks) {
    let id: number | undefined
    let kind = "message"
    const data: string[] = []
    for (const line of block.split("\n")) {
      if (!line || line.startsWith(":")) continue
      const colon = line.indexOf(":")
      const field = colon === -1 ? line : line.slice(0, colon)
      let value = colon === -1 ? "" : line.slice(colon + 1)
      if (value.startsWith(" ")) value = value.slice(1)
      if (field === "id") {
        const parsed = Number(value)
        if (Number.isFinite(parsed)) id = parsed
      } else if (field === "event") kind = value
      else if (field === "data") data.push(value)
    }
    // A block with no data is a comment or a stray id line, not an event.
    if (data.length === 0) continue
    const text = data.join("\n")
    let payload: unknown = text
    try {
      payload = JSON.parse(text)
    } catch {
      // Kept as text: an unparseable payload is still an event that happened.
    }
    out.push({ id: id ?? 0, kind, payload })
  }
  return out
}

/** One successful tool result, oldest first, with the event id it arrived on. */
export type ToolResult = { id: number; name: string; result: unknown }

type ToolResultPayload = { id?: unknown; name?: unknown; ok?: unknown; result?: unknown }

/**
 * Every tool result that succeeded, oldest first.
 *
 * `tool.result` carries its own `name`, `ok` and `result` (conductor), so it
 * is read on its own; the matching `tool.call` adds nothing a reader of
 * results needs. A failed result is skipped for the reason the outgoing
 * `latestDiagnosis` gave: a half-written verdict is not a verdict.
 */
export function toolResults(events: readonly ThreadEvent[]): ToolResult[] {
  const out: ToolResult[] = []
  for (const event of events) {
    if (event.kind !== "tool.result") continue
    const payload = event.payload as ToolResultPayload | null
    if (!payload || payload.ok !== true) continue
    out.push({ id: event.id, name: String(payload.name ?? ""), result: payload.result })
  }
  return out
}

/** Every result a reader accepts, newest first. */
export function allReadsOf<T>(results: readonly ToolResult[], read: (value: unknown) => T | null): T[] {
  const out: T[] = []
  for (let i = results.length - 1; i >= 0; i -= 1) {
    const found = read(results[i].result)
    if (found !== null) out.push(found)
  }
  return out
}

/** The newest result a reader accepts, or null. Always `allReadsOf(...)[0]`. */
export function latestReadOf<T>(results: readonly ToolResult[], read: (value: unknown) => T | null): T | null {
  for (let i = results.length - 1; i >= 0; i -= 1) {
    const found = read(results[i].result)
    if (found !== null) return found
  }
  return null
}

/**
 * A `train.*` kind that means the job is over - the outgoing
 * `stageTransition.ts` rule, kept word for word. Matched rather than listed
 * because recipes emit their own terminal names; a kind this misses leaves a
 * run counted as spending, which costs a few extra polls and nothing else.
 */
const TERMINAL = /finished|failed|done|complete|cancel|interrupt/i

export type LiveEval = { runId: number; graded: number; planned: number }

/**
 * What is still spending in this thread: eval runs started and not yet
 * finished, interrupted or reused, and training jobs whose latest event is
 * not terminal. `reused` is not spending - the bench answered from its own
 * tables and nothing was paid for.
 */
export function liveWork(events: readonly ThreadEvent[]): { evals: LiveEval[]; trains: string[] } {
  const evals = new Map<number, LiveEval & { running: boolean }>()
  const trains = new Map<string, string>()
  const number = (value: unknown) => (typeof value === "number" && Number.isFinite(value) ? value : null)
  for (const event of events) {
    const payload = (event.payload ?? {}) as Record<string, unknown>
    if (event.kind.startsWith("eval.")) {
      const runId = number(payload.run_id) ?? 0
      const row = evals.get(runId) ?? { runId, graded: 0, planned: 0, running: true }
      if (event.kind === "eval.started") {
        row.running = true
        row.graded = number(payload.already_graded) ?? 0
        row.planned = number(payload.planned) ?? 0
      } else if (event.kind === "eval.progress") {
        row.graded = number(payload.graded) ?? row.graded
        row.planned = number(payload.planned) ?? row.planned
      } else if (event.kind === "eval.finished" || event.kind === "eval.interrupted" || event.kind === "eval.reused") {
        row.running = false
      }
      evals.set(runId, row)
    } else if (event.kind.startsWith("train.")) {
      const job = String(payload.job_id ?? "unknown")
      const latest = trains.get(job) ?? ""
      trains.set(job, event.kind === "train.log" ? latest : event.kind.slice("train.".length))
    }
  }
  return {
    evals: [...evals.values()].filter((row) => row.running).map(({ running: _, ...row }) => row),
    trains: [...trains.entries()].filter(([, latest]) => !TERMINAL.test(latest)).map(([job]) => job),
  }
}

/** The events route for one thread, as a finite history read. */
export function eventsPath(threadId: number) {
  return `/api/events?scope=thread:${threadId}&since=0&follow=false`
}

/**
 * Read a thread's events, parsed. `useHarnessRead` hands back the last good
 * read while the next is in flight, so a poll never blanks the pane. The
 * error is checked first because a failed read has no last value to give.
 */
export function useThreadEvents(threadId: Accessor<number | undefined>) {
  const read = useHarnessRead<string | undefined>(() => {
    const id = threadId()
    return id === undefined ? undefined : eventsPath(id)
  })
  const events = createMemo<ThreadEvent[]>(() => {
    if (read.data.error) return []
    const body = read.data()
    return typeof body === "string" ? parseSse(body) : []
  })
  return { events, read }
}

/**
 * Re-run `tick` every `ms` while `live()` is true, and stop when it is not.
 *
 * `useHarnessRead`'s own `poll` is fixed when the pane mounts, and these
 * panes should only poll while a run is actually spending - the original
 * refreshed off the event stream, which is silent when nothing happens. So
 * this is the same interval, switched by the pane's own reading of the log.
 */
export function pollWhile(live: Accessor<boolean>, ms: number, tick: () => void) {
  createEffect(() => {
    if (!live()) return
    const timer = setInterval(tick, ms)
    onCleanup(() => clearInterval(timer))
  })
}
