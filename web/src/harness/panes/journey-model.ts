/**
 * The journey overview's one read, `GET /api/threads/{id}/journey`
 * (`app/journey.py::build`), and the pure rules the Journey pane applies to it.
 *
 * Field names are the engine's own (snake_case), kept verbatim at the
 * boundary. Every state is a claim about the record - `done` means a tool left
 * a result, `done_elsewhere` means another tool put the facts on the ledger -
 * and a renamed field is one more place for the claim and the evidence to
 * drift apart.
 */

export type StepState = "done" | "done_elsewhere" | "not_needed" | "next" | "ahead"

/** A value the harness already measured, offered into the step's call. */
export interface Prefilled {
  value: string | number | boolean | Record<string, unknown>
  from: string
}

export interface Readiness {
  /** `click` runs as is, `approve` runs after a yes, `needs` wants fields filled. */
  mode: "click" | "approve" | "needs"
  missing: string[]
}

export interface JourneyStep {
  ordinal: number
  tool: string
  why: string
  args_hint: string
  needs_approval: boolean
  prefill: Record<string, Prefilled>
  readiness: Readiness
  state: StepState
  unnecessary_because: string | null
  attempted: { at: string | null; error: string | null; detail: string | null } | null
  evidence: "event" | "ledger" | null
  ran_at: string | null
  driven_by: string | null
  produced: string | null
  satisfied_by: { tool: string | null; facts: string[] } | null
}

export interface JourneyNext {
  ordinal: number
  tool: string
}

export interface JourneyOutcome {
  adapter_run_id: number
  baseline_run_id: number
  score: number | null
  baseline_score: number | null
  delta: number | null
  paired_rows: number | null
  verdict: string | null
  resolved: boolean | null
  rows_that_would_resolve_this_delta: number | null
  says: string | null
}

export interface BlockedBy {
  gate: string
  reached: boolean
  checked: number
  of: number
  class_undecided: boolean
  clause: string
  reads: { fact: string; value: unknown; origin: string | null; how: string | null; unmeasured: boolean }[]
}

export interface JourneyVerdict {
  outcome: string
  trains: boolean
  blocked_by: BlockedBy | null
  say: string
  gates_passed: number
  gates_total: number
}

export interface JourneyPayload {
  thread_id: number
  journey: string | null
  journey_origin: "recorded" | "matched" | null
  matched_on: string[]
  says: string | null
  steps: JourneyStep[]
  total: number
  done_n: number
  next: JourneyNext | null
  /** The first step that can actually be pressed, which is not always the first undone one. */
  next_runnable: JourneyNext | null
  outcome: JourneyOutcome | null
  verdict: JourneyVerdict | null
  journeys_available: string[]
  say: string
}

/** One field of a tool, as `GET /api/tools` describes it (`as_control`). */
export interface ToolField {
  name: string
  type: string
  description: string
  required: boolean
  enum: unknown[] | null
}

/** A tool name as a person reads it: `carve_eval_set` becomes "Carve eval set". */
export function toolLabel(tool: string): string {
  const words = tool.replace(/_/g, " ").trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/**
 * The step's state as a sentence. `done_elsewhere` says MET BY and names the
 * tool, because collapsing it to "done" would claim a tool ran that never ran -
 * the distinction `app/journey.py` exists to keep.
 */
export function stateInWords(step: JourneyStep): string {
  if (step.state === "next") return "you are here"
  if (step.state === "done") return "done"
  if (step.state === "ahead") return "not started"
  if (step.state === "not_needed") {
    const by = step.unnecessary_because
    return by ? `not needed here, ${by} covered it` : "not needed here"
  }
  const by = step.satisfied_by?.tool
  return by ? `met by ${by}` : "met by another tool"
}

/** The engine's `CURRENT_TIMESTAMP` as the date it carries, never converted to an invented zone. */
export function stamp(value: string | null): string | null {
  if (!value) return null
  return value.replace("T", " ").slice(0, 16)
}

/** A score as a whole percent, or an em dash. The engine's number, rounded, never recomputed. */
export function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`
}

/**
 * What a tool's answer says about whether it ran. A tool refuses through
 * `detail`, `summary`, or `error` plus `help` - not one field - and reading only
 * one turned a refusal written as a remedy into "it did not run, and said
 * nothing about why", the one thing this product is built against.
 */
export function refusalOf(result: unknown): { ok: true } | { ok: false; detail?: string } {
  const body = result as { ok?: boolean; detail?: unknown; summary?: unknown; error?: unknown; help?: unknown } | null
  if (!body || typeof body !== "object" || body.ok !== false) return { ok: true }
  const said = [body.detail, body.summary, body.error].find(
    (part): part is string => typeof part === "string" && part.trim() !== "",
  )
  const help = typeof body.help === "string" ? body.help.trim() : ""
  return { ok: false, detail: said ? [said.trim(), help].filter(Boolean).join(" ") : undefined }
}

/**
 * The call's arguments: what the record already holds, then what the person
 * typed, each typed as the tool's own schema declares. Throws a sentence
 * naming the field when a value cannot be what the schema asks for, so the
 * mistake is caught before anything runs rather than refused after.
 */
export function argumentsFor(
  prefill: Record<string, Prefilled>,
  typed: Record<string, string>,
  fields: ToolField[],
): Record<string, unknown> {
  const args: Record<string, unknown> = {}
  for (const [field, offered] of Object.entries(prefill)) args[field] = offered.value
  const kinds = new Map(fields.map((field) => [field.name, field.type]))
  for (const [field, raw] of Object.entries(typed)) {
    const text = raw.trim()
    if (text === "") continue
    const kind = kinds.get(field) ?? "string"
    if (kind === "integer" || kind === "number") {
      const value = Number(text)
      if (!Number.isFinite(value) || (kind === "integer" && !Number.isInteger(value))) {
        throw new Error(`${field} needs ${kind === "integer" ? "a whole number" : "a number"}; "${text}" is not one.`)
      }
      args[field] = value
    } else if (kind === "boolean") {
      if (!/^(true|false)$/i.test(text)) throw new Error(`${field} needs true or false; "${text}" is neither.`)
      args[field] = text.toLowerCase() === "true"
    } else if (kind === "object" || kind === "array") {
      try {
        args[field] = JSON.parse(text)
      } catch {
        throw new Error(`${field} needs JSON (${kind === "object" ? "an object" : "a list"}); what is there does not parse.`)
      }
    } else args[field] = text
  }
  return args
}

/** The fields still empty after the person typed, of those the step said were missing. */
export function stillMissing(missing: string[], typed: Record<string, string>): string[] {
  return missing.filter((field) => !(typed[field] ?? "").trim())
}
