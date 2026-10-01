/**
 * `GET /api/threads/{id}/subagents` - the phases this conversation handed out -
 * and the words the Agents pane draws them with.
 *
 * Field names are the engine's own (`app/subagents.py`), kept verbatim at the
 * boundary. What reaches the pane is counts and endings, deliberately never a
 * child's transcript: a person who wants that opens the child, which is a real
 * conversation of its own.
 */

export interface SubAgent {
  id: number
  /** The child conversation. Opening it is how a person reads the work. */
  thread_id: number
  phase: string
  /** `running`, `done`, `failed` or `stopped`. */
  state: string
  reason: string
  detail: string
  harvested: boolean
  turns: number
  seconds: number | null
  steps: number
  done: number
  open: number
  parked: { step: string; why: string }[]
  packs?: string[]
  /** The plan the phase was handed out with - the child's own instructions. */
  brief?: string
  tools_run?: number
  tools_failed?: number
  tools_distinct?: number
  tool_names?: { name: string; times: number }[]
  context_peak_tokens?: number
  /** The last harvest paragraph; empty while running. */
  last_digest?: string
  started_at: string
  updated_at: string
}

export interface SubAgentRead {
  thread_id: number
  subagents: SubAgent[]
  /** Working for THIS conversation. */
  running: number
  /** Working anywhere - the cap is on the machine, not the conversation. */
  running_anywhere: number
  at_most: number
}

/** The one line a person wants first: is anything still out, and how much came back. */
export function boardHeadline(read: SubAgentRead): string {
  const working = read.subagents.filter((one) => one.state === "running").length
  const back = read.subagents.length - working
  if (working && back) return `${working} working, ${back} back`
  if (working) return `${working} of ${read.at_most} working`
  return back === 1 ? "1 phase came back" : `${back} phases came back`
}

/** How a finished sub-agent ended, in words; empty while it is still working. */
export function endingInWords(one: SubAgent): string {
  if (one.state === "running") return ""
  if (one.state === "failed") return "it failed"
  if (one.state === "stopped") return "stopped"
  if (one.parked.length && one.done === 0) return "nothing could be done"
  if (one.parked.length) return `${one.done} done, ${one.parked.length} parked`
  return `all ${one.done} done`
}

/** "4m 12s", and "48s" when a leading `0m` would be noise. */
export function howLong(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || seconds < 0) return ""
  if (seconds < 60) return `${seconds}s`
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`
}

/**
 * "18:04" from the engine's timestamp, local, or an empty string. SQLite hands
 * these back as `2026-09-19 18:04:33` with no zone, which `new Date()` reads as
 * local on some engines and UTC on others; the engine writes UTC, so a `Z` is
 * added when the stamp carries no zone. A time an hour out is worse than none.
 */
export function clock(stamp: string | null | undefined, locale?: string): string {
  if (!stamp) return ""
  const text = String(stamp).trim().replace(" ", "T")
  const iso = /[zZ]$|[+-]\d\d:?\d\d$/.test(text) ? text : `${text}Z`
  const when = new Date(iso)
  if (Number.isNaN(when.getTime())) return ""
  return when.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" })
}
