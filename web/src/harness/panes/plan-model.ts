/**
 * The plan as data: phases, steps, counts, and the three edits a person makes
 * to it from the Plan pane (save a phase, tick a step, unpark a step).
 *
 * Ported from the outgoing frontend's `lib/thePlanInPhases.ts`,
 * `PlanDocument.toggleStep`, `GoalBar.stepRows/unpark` and
 * `theBuildKeepsGoing.stepsIn`, and brought under one rule: every edit is
 * addressed by LINE NUMBER, not by "the n-th step". The old read view counted
 * rendered checkbox rows and the old goal bar matched steps by their text, so
 * two steps with the same words, or a parked step the checkbox list skipped,
 * could tick or unpark the wrong line. A line number is what both the reader
 * and the writer can agree on without re-deriving anything.
 *
 * Every function here is lossless on the lines it does not touch, including
 * a trailing carriage return, because the pane saves the whole document back
 * and a helper that quietly normalised line endings would rewrite a person's
 * plan file every time they ticked a box.
 */

export interface Phase {
  /** The `## ...` line, verbatim. Empty for anything before the first one. */
  heading: string
  /** Everything under the heading, as lines. What `joinPhases` reads. */
  bodyLines: string[]
  /** The same body as one string, which is what the editor shows. */
  body: string
  /** `Phase 1` gives 1, for the nav; null when the heading does not number itself. */
  number: number | null
  /** The heading without its `##` and without a `Phase N -` prefix. Display only. */
  label: string
}

export type StepState = "open" | "done" | "parked"

export interface Step {
  /** Index of the step's line in `plan.split(NL)`. The address every edit uses. */
  line: number
  state: StepState
  text: string
  /** The parked reason, when a run parked the step with ` — parked: why`. */
  why: string
}

const NL = "\n"
const CR = "\r"
const PARKED = " — parked: "

/* A `##` heading and nothing cleverer, because the engine's plan-mode note
   asks the model for exactly that shape (`app/conductor._mode_note`), so the
   reader and the instruction agree on one rule. */
const HEADING = /^##[^#].*$/
const FENCE = /^\s*(```|~~~)/
/* `- [ ] text`, `* [x] text`, `- [!] text` - open, done, parked. */
const STEP = /^(\s*[-*]\s+\[)([ xX!])(\]\s+)(\S.*)$/

/** A line with its carriage return set aside, so a pattern can end at `$`. */
function bare(line: string): { text: string; cr: string } {
  return line.endsWith(CR) ? { text: line.slice(0, -1), cr: CR } : { text: line, cr: "" }
}

/** Split a plan into its phases. `joinPhases(splitIntoPhases(t)) === t` for any t. */
export function splitIntoPhases(plan: string): Phase[] {
  const phases: Phase[] = []
  let heading = ""
  let lines: string[] = []
  let fenced = false
  const flush = () => {
    if (heading === "" && lines.length === 0) return
    phases.push(describe(heading, lines))
  }
  for (const line of plan.split(NL)) {
    const text = bare(line).text
    // A `##` inside a code fence is code, not a phase: a plan that explains how
    // to write a plan would otherwise cut itself in half.
    if (FENCE.test(text)) fenced = !fenced
    if (!fenced && HEADING.test(text)) {
      flush()
      heading = line
      lines = []
      continue
    }
    lines.push(line)
  }
  flush()
  return phases
}

/** Rebuild the document. The exact inverse of `splitIntoPhases`. */
export function joinPhases(phases: Phase[]): string {
  const out: string[] = []
  for (const phase of phases) {
    if (phase.heading !== "") out.push(phase.heading)
    out.push(...phase.bodyLines)
  }
  return out.join(NL)
}

/**
 * Replace one phase's body and return the whole document. The engine stores
 * one `plan` column, so the pane edits a section and saves the document; a
 * pane that saved sections would be inventing a second copy of where a phase
 * ends.
 */
export function withPhaseBody(plan: string, index: number, body: string): string {
  const phases = splitIntoPhases(plan)
  if (index < 0 || index >= phases.length) return plan
  return joinPhases(
    phases.map((phase, at) => (at === index ? { ...phase, body, bodyLines: body.split(NL) } : phase)),
  )
}

function describe(heading: string, bodyLines: string[]): Phase {
  const text = bare(heading).text.replace(/^##\s*/, "").trim()
  // An en or em dash counts as the separator too: a model writing
  // `## Phase 1 — Data` means what a hyphen means.
  const numbered = /^phase\s+(\d+)\s*[-–—:.]?\s*(.*)$/i.exec(text)
  return {
    heading,
    bodyLines,
    body: bodyLines.join(NL),
    number: numbered ? Number(numbered[1]) : null,
    label: numbered && numbered[2] ? numbered[2] : text || "Before the first phase",
  }
}

/** Every step line in the plan, in document order, with its state and reason. */
export function stepsOf(plan: string | null | undefined): Step[] {
  const out: Step[] = []
  let fenced = false
  ;(plan ?? "").split(NL).forEach((line, index) => {
    const text = bare(line).text
    if (FENCE.test(text)) fenced = !fenced
    if (fenced) return
    const match = STEP.exec(text)
    if (!match) return
    const glyph = match[2].toLowerCase()
    let words = match[4].trim()
    let why = ""
    const at = words.indexOf(PARKED)
    if (at >= 0) {
      why = words.slice(at + PARKED.length).trim()
      words = words.slice(0, at).trim()
    }
    out.push({ line: index, state: glyph === "x" ? "done" : glyph === "!" ? "parked" : "open", text: words, why })
  })
  return out
}

export interface StepCounts {
  open: number
  done: number
  parked: number
  total: number
}

export function countSteps(plan: string | null | undefined): StepCounts {
  const counts: StepCounts = { open: 0, done: 0, parked: 0, total: 0 }
  for (const step of stepsOf(plan)) {
    counts[step.state] += 1
    counts.total += 1
  }
  return counts
}

/**
 * "4 of 9 steps ticked", or an empty string for a plan with no steps. A parked
 * step is not ticked - the run gave up on it - so it counts against the total
 * exactly as the engine's own run summary does.
 */
export function tickedLine(counts: StepCounts): string {
  if (!counts.total) return ""
  const base = `${counts.done} of ${counts.total} steps ticked`
  if (counts.open === 0 && counts.parked === 0) return `${base} · every step done`
  if (counts.parked) return `${base} · ${counts.parked} parked`
  return base
}

/**
 * Every step is settled and at least one was done. This is when the report
 * writes itself (the owner, 2026-09-12: "it should automatically save, you
 * shouldn't have to even click that").
 */
export function everyStepSettled(counts: StepCounts): boolean {
  return counts.done > 0 && counts.open === 0
}

function editLine(plan: string, line: number, edit: (match: RegExpExecArray) => string | undefined): string {
  const lines = plan.split(NL)
  if (line < 0 || line >= lines.length) return plan
  const { text, cr } = bare(lines[line])
  const match = STEP.exec(text)
  if (!match) return plan
  const next = edit(match)
  if (next === undefined) return plan
  lines[line] = next + cr
  return lines.join(NL)
}

/**
 * Flip an open step to done or a done step back to open. Un-ticking is
 * deliberate: a step the model ticked and the person disagrees with goes back
 * on the list, and the next run picks it up. A parked step is left alone -
 * its way back is Unpark, which also drops the reason.
 */
export function toggleStepAt(plan: string, line: number): string {
  return editLine(plan, line, (match) => {
    const glyph = match[2].toLowerCase()
    if (glyph === "!") return undefined
    return `${match[1]}${glyph === "x" ? " " : "x"}${match[3]}${match[4]}`
  })
}

/** Put a parked step back to `- [ ]`, with its parked reason dropped. */
export function unparkAt(plan: string, line: number): string {
  return editLine(plan, line, (match) => {
    if (match[2] !== "!") return undefined
    const words = match[4]
    const at = words.indexOf(PARKED)
    return `${match[1]} ${match[3]}${(at >= 0 ? words.slice(0, at) : words).trim()}`
  })
}

/** The `# Title` line's text, or an empty string. */
export function planTitle(plan: string | null | undefined): string {
  for (const line of (plan ?? "").split(NL)) {
    const text = bare(line).text
    if (/^#\s+/.test(text)) return text.replace(/^#\s+/, "").trim()
  }
  return ""
}

/**
 * The plan as blocks for the read view. Deliberately not a markdown renderer:
 * the pane must work with no OpenCode session around it (pop-out windows), and
 * their markdown component needs that context. The plan is a narrow dialect -
 * a title, `##` phases, step lines, bullets and prose - and each of those gets
 * a block; anything else is shown as the line it is, never dropped.
 */
export type Block =
  | { kind: "title"; text: string }
  | { kind: "phase"; text: string; index: number }
  | { kind: "heading"; text: string }
  | { kind: "step"; step: Step }
  | { kind: "bullet"; text: string }
  | { kind: "code"; text: string }
  | { kind: "text"; text: string }
  | { kind: "gap" }

export function blocksOf(plan: string | null | undefined): Block[] {
  const steps = new Map(stepsOf(plan).map((step) => [step.line, step]))
  const blocks: Block[] = []
  let fence: string[] | undefined
  let phase = -1
  let titled = false
  const lines = (plan ?? "").split(NL)
  // The phase index must match `splitIntoPhases`, which gives text before the
  // first heading its own phase. So the first heading is phase 1 when there is
  // preamble and phase 0 when the document opens on a heading.
  let preamble = false
  lines.forEach((raw, index) => {
    const text = bare(raw).text
    if (FENCE.test(text)) {
      if (fence) {
        blocks.push({ kind: "code", text: fence.join(NL) })
        fence = undefined
      } else fence = []
      if (phase < 0) preamble = true
      return
    }
    if (fence) {
      fence.push(text)
      return
    }
    const step = steps.get(index)
    if (step) {
      if (phase < 0) preamble = true
      blocks.push({ kind: "step", step })
      return
    }
    if (HEADING.test(text)) {
      phase = phase < 0 ? (preamble ? 1 : 0) : phase + 1
      blocks.push({ kind: "phase", text: text.replace(/^##\s*/, "").trim(), index: phase })
      return
    }
    if (phase < 0) preamble = true
    if (/^#\s+/.test(text) && !titled) {
      titled = true
      blocks.push({ kind: "title", text: text.replace(/^#\s+/, "").trim() })
      return
    }
    if (/^#{1,6}\s+/.test(text)) {
      blocks.push({ kind: "heading", text: text.replace(/^#{1,6}\s+/, "").trim() })
      return
    }
    const bullet = /^\s*(?:[-*+]|\d+[.)])\s+(.*)$/.exec(text)
    if (bullet) {
      blocks.push({ kind: "bullet", text: bullet[1] })
      return
    }
    if (!text.trim()) {
      if (blocks.length && blocks[blocks.length - 1].kind !== "gap") blocks.push({ kind: "gap" })
      return
    }
    blocks.push({ kind: "text", text })
  })
  // An unclosed fence is still shown: dropping the tail of a plan because a
  // model forgot three backticks would hide exactly the part it was writing.
  if (fence) blocks.push({ kind: "code", text: fence.join(NL) })
  return blocks
}
