/**
 * What the facade hands a harness result card, read off their tool part.
 *
 * `app/facade/translate.py::harness_metadata` puts the engine's structured
 * result on the tool part's `metadata.harness`, on the live
 * `session.tool.success` event and on parts `message.list` returns alike:
 *
 *     { tool, callID, ok, result | resultOmitted, repeatOf?, rerun?,
 *       drivenBy?, via?, answers?, decision? }
 *
 * Their card draws `content`, which is text; these cards draw `result`, the
 * dict the engine wrote. This file is the one reader of that envelope, so a
 * card never reaches into `metadata` itself and two cards cannot disagree
 * about what the facade sent.
 */

export type HarnessEnvelope = {
  tool: string
  callID: string
  /** The CALL worked and the tool did not answer `ok: false`. */
  ok: boolean
  /** The engine's own result, or undefined when it was over the size bound. */
  result: unknown
  /** Set instead of `result` when the result was too large to carry. */
  omitted: { chars: number; limit: number } | null
  repeatOf: unknown
  rerun: unknown
  drivenBy: string | null
  via: string | null
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

/**
 * The envelope, or null when the part carries none - a tool part written by
 * something other than the facade, or one still streaming its input.
 */
export function harnessOf(metadata: Record<string, unknown> | undefined): HarnessEnvelope | null {
  const raw = metadata?.harness
  if (!isRecord(raw)) return null
  const omitted = isRecord(raw.resultOmitted)
    ? {
        chars: typeof raw.resultOmitted.chars === "number" ? raw.resultOmitted.chars : 0,
        limit: typeof raw.resultOmitted.limit === "number" ? raw.resultOmitted.limit : 0,
      }
    : null
  return {
    tool: typeof raw.tool === "string" ? raw.tool : "tool",
    callID: typeof raw.callID === "string" ? raw.callID : "",
    ok: raw.ok !== false,
    result: raw.result,
    omitted,
    repeatOf: raw.repeatOf,
    rerun: raw.rerun,
    drivenBy: typeof raw.drivenBy === "string" && raw.drivenBy ? raw.drivenBy : null,
    via: typeof raw.via === "string" && raw.via ? raw.via : null,
  }
}

/**
 * The harness thread behind an OpenCode session id.
 *
 * The facade records the thread on the session's own metadata
 * (`sessions.py`, `metadata.harness.threadID`) because a session id their
 * client minted is opaque. Only when no session in the list names it does
 * the `ses_<n>` form the facade itself mints get read, and never before: an
 * id that merely happens to be digits must not resolve to somebody else's
 * thread (the same order `sessions.thread_id_of` asks in).
 */
export function threadIdFor(sessionID: string | undefined, sessions: readonly unknown[] | undefined): number | undefined {
  if (!sessionID) return undefined
  const session = (sessions ?? []).find((entry) => isRecord(entry) && entry.id === sessionID)
  const value = (session as { metadata?: { harness?: { threadID?: unknown } } } | undefined)?.metadata?.harness?.threadID
  const id = typeof value === "string" ? Number(value) : value
  if (typeof id === "number" && Number.isFinite(id)) return id
  if (session) return undefined
  const minted = /^ses_(\d+)$/.exec(sessionID)
  return minted ? Number(minted[1]) : undefined
}

const BACKSLASH = String.fromCharCode(92)

/** A path's last segment, whichever separator wrote it. */
export function baseName(path: string): string {
  const parts = path.split("/").join(BACKSLASH).split(BACKSLASH).filter(Boolean)
  return parts[parts.length - 1] ?? path
}

const COUNT = new Intl.NumberFormat("en")
export const count = (value: number) => COUNT.format(value)

/** A fraction as a percentage. */
export function pct(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`
}

/** A byte count for a person; `null` says it was not reported rather than zero. */
export function bytes(value: number | null): string {
  if (value === null) return "not reported"
  const units = ["B", "kB", "MB", "GB"]
  let size = value
  let unit = 0
  while (size >= 1000 && unit < units.length - 1) {
    size /= 1000
    unit += 1
  }
  return `${size >= 100 || unit === 0 ? Math.round(size) : size.toPrecision(3)} ${units[unit]}`
}

/** The first sentence of a note, for a collapsed card's one line. */
export function firstClause(say: string | null | undefined, max = 96): string | null {
  if (!say) return null
  const trimmed = say.trim()
  const stop = trimmed.search(/[.?!]\s/)
  const head = stop === -1 ? trimmed : trimmed.slice(0, stop + 1)
  return head.length > max ? `${head.slice(0, max - 1)}…` : head
}

/** A value from the wire, short enough for one cell. */
export function show(value: unknown, max = 48): string {
  if (value === null || value === undefined) return "—"
  if (typeof value === "boolean") return value ? "true" : "false"
  if (typeof value === "number") return value.toLocaleString("en")
  if (typeof value === "string") return value.length > max ? `${value.slice(0, max - 1)}…` : value
  try {
    const text = JSON.stringify(value)
    return text.length > max ? `${text.slice(0, max - 1)}…` : text
  } catch {
    return String(value)
  }
}
