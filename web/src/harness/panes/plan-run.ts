/**
 * The engine's long run (`app/longrun.py`), as the Plan pane words it.
 *
 * A run is started by a person and by nothing else, takes ordinary turns until
 * every step is ticked or parked, and survives this window closing - which is
 * why its state is read from `GET /api/threads/{id}/run` rather than kept here.
 * These helpers only turn that row into sentences, so the wording has one home
 * and a test.
 */

export interface RunState {
  thread_id: number
  /** Empty when the thread has never had a run, which is not an error. */
  state: "" | "running" | "done" | "stopped" | "failed"
  turns?: number
  cap?: number
  stop_reason?: string
  detail?: string
  steps?: number
  open?: number
  done?: number
  parked?: { step: string; why: string }[]
  /** How long the run has been going, or took - from the engine's own timestamps. */
  seconds?: number | null
  started_at?: string
}

/** "14m 07s", and "48s" when that is all it took, because a leading `0m` is noise. */
export function minutes(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`
}

/** The live line: "Working the plan · 3 done, 5 left · 1 parked". */
export function workingLine(run: RunState | undefined): string {
  let line = "Working the plan"
  if (run && typeof run.open === "number") line += ` · ${run.done ?? 0} done, ${run.open} left`
  if (run?.parked?.length) line += ` · ${run.parked.length} parked`
  return line
}

/**
 * How the last run ended, in the engine's words: its `stop_reason` with the
 * underscores read as spaces, then its own detail. Empty while one is running
 * or when there has never been one.
 */
export function lastRunLine(run: RunState | undefined): string {
  if (!run || !run.state || run.state === "running") return ""
  let line = `Last run: ${String(run.stop_reason || run.state).replace(/_/g, " ")}`
  if (run.parked?.length) line += ` · ${run.parked.length} parked`
  if (typeof run.seconds === "number" && run.seconds >= 0) line += ` · ${minutes(run.seconds)}`
  return line
}
