/**
 * The arithmetic behind the Context pane, kept apart from the drawing so it
 * can be tested without a DOM.
 *
 * Every figure the pane shows was counted by the engine on a prompt that was
 * sent (`app/contextwindow.py`). Nothing here re-counts anything: it only
 * turns those counts into widths, heights and sentences, and the rules for
 * doing that are the ones the outgoing pane settled on.
 */

/** One reading of what a prompt cost, as `app/contextwindow.py` returns it. */
export type ContextTurn = {
  event_id: number
  system: number
  tools: number
  history: number
  total: number
  messages: number
  tool_count: number
  window: number | null
  mode: string
  /** Every named piece of that prompt, biggest first. */
  parts?: { key: string; label: string; why: string; tokens: number; count: number }[]
  /**
   * Which tools spent a full schema on that turn. `withheld` are still named
   * in the prompt and still callable, just without their parameters. `{}` on
   * a turn taken before the record existed, hence every field optional.
   */
  schemas_on_wire?: {
    tools?: string[]
    because?: Record<string, string>
    considered?: string[]
    withheld?: string[]
    all_schemas?: boolean
    switch?: string
  }
}

export type ContextWindowRead = {
  thread_id: number
  model: string
  window: number | null
  window_provenance: string
  latest: ContextTurn | null
  headroom: number | null
  share: number | null
  turns: ContextTurn[]
  compactions: {
    event_id: number
    messages_summarised: number | null
    tokens_before: number | null
    tokens_after: number | null
  }[]
  compaction_at: number
  counted_by: string
}

/** `POST /api/threads/{id}/compact`. `ok: false` with a detail is "nothing to compact", not a failure. */
export type CompactResult = {
  ok: boolean
  detail?: string
  messages_summarised?: number
  tokens_before?: number
  tokens_after?: number
}

/** One attachment, as `GET /api/threads/{id}/contexts` lists it. */
export type ThreadContext = { id: number; path: string; kind: string; role: string; note?: string }

/**
 * Eight colour bands, assigned in the order the engine sorted the parts -
 * biggest first - so the largest spend always carries the first colour.
 *
 * Their avatar border colours are the one eight-hue set in the token file
 * that is redefined for dark mode (`tokens/theme.css`), so both themes read
 * without this pane carrying a palette of its own.
 */
export const BANDS = [
  "var(--v2-avatar-border-blue)",
  "var(--v2-avatar-border-orange)",
  "var(--v2-avatar-border-green)",
  "var(--v2-avatar-border-purple)",
  "var(--v2-avatar-border-cyan)",
  "var(--v2-avatar-border-pink)",
  "var(--v2-avatar-border-yellow)",
  "var(--v2-avatar-border-red)",
] as const

/** Free space is the room that is left, so it is drawn as the panel's own raised surface rather than as a colour. */
export const FREE_COLOUR = "var(--v2-background-bg-layer-03)"

export function thousands(n: number | null | undefined): string {
  return typeof n === "number" && Number.isFinite(n) ? n.toLocaleString() : "—"
}

/** "63.6%" or "12%", or an em dash when there is no window to be a share of. */
export function share(tokens: number, window: number | null | undefined): string {
  if (!window) return "—"
  const percent = (tokens / window) * 100
  return `${percent >= 10 ? percent.toFixed(0) : percent.toFixed(1)}%`
}

export type Segment = {
  key: string
  label: string
  why: string
  tokens: number
  colour: string
  /** Width in percent of the bar. */
  width: number
}

/**
 * The bar, one segment per part, free space last.
 *
 * Widths are taken against the WINDOW when there is one, so the empty part
 * of the bar is the room that is left rather than a rescaling of what was
 * spent. Without a window the parts fill the bar between them, and there is
 * no free segment because there is nothing to be free of.
 */
export function segments(latest: ContextTurn, window: number | null): { parts: Segment[]; free: Segment | undefined } {
  const against = window || latest.total || 1
  const parts = (latest.parts ?? []).map((part, index) => ({
    key: part.key,
    label: part.label,
    why: part.why,
    tokens: part.tokens,
    colour: BANDS[index % BANDS.length],
    width: Math.max(0, Math.min(100, (part.tokens / against) * 100)),
  }))
  if (!window) return { parts, free: undefined }
  const tokens = Math.max(0, window - latest.total)
  return {
    parts,
    free: {
      key: "free",
      label: "Free space",
      why: "room left in this model's window",
      tokens,
      colour: FREE_COLOUR,
      width: (tokens / window) * 100,
    },
  }
}

/**
 * Bar heights for the per-turn chart, in percent, oldest first.
 *
 * Against the window when the model has one: a row of full-height bars would
 * say "every turn is the same size" where the honest reading is "every turn
 * is a sixth of what fits". Without a window the tallest turn sets the scale.
 * A floor of 4% keeps a tiny turn visible as a turn rather than as nothing.
 */
export function turnBars(turns: ContextTurn[], window: number | null) {
  const against = window || Math.max(0, ...turns.map((turn) => turn.total)) || 1
  return turns.map((turn) => ({
    id: turn.event_id,
    total: turn.total,
    height: Math.min(100, Math.max(4, (turn.total / against) * 100)),
    over: !!window && turn.total > window,
  }))
}

/**
 * The line that stops "9 tool schemas" being read as "the harness has nine
 * tools": every withheld tool is still named and callable, only its
 * parameters stayed out of the room.
 */
export function withheldSentence(count: number): string | undefined {
  if (count <= 0) return
  const one = count === 1
  return (
    `${count} more tool${one ? " was" : "s were"} active and named in the prompt without ` +
    `${one ? "its" : "their"} parameters. The model can still call ${one ? "it" : "them"}, ` +
    "and naming one puts its schema in the room next turn."
  )
}

/** The receipt a Compact press leaves under the header. */
export function compactNote(result: CompactResult): string {
  if (!result.ok) return result.detail || "Nothing to compact."
  return (
    `Compacted ${thousands(result.messages_summarised)} messages, ` +
    `${thousands(result.tokens_before)} to ${thousands(result.tokens_after)} tokens.`
  )
}
