/**
 * An eval run's report, read off a tool result.
 *
 * Ported from the outgoing `frontend/src/lib/engine/evals.ts`, trimmed to the
 * fields the Eval pane draws. The rule it keeps is that file's rule: a field
 * the engine did not send is `null`, never `0` and never a guess, and a score
 * is only reachable together with its resolution, because `evals.py` never
 * returns one without the other and a renderer that drops the interval has
 * un-reported it.
 */

export type EvalResolution = {
  /** Rows graded. `0` means nothing was, and then every field below is null. */
  n: number
  /** Wilson 95%, as two fractions in [0,1]. */
  ci95: [number, number] | null
  halfWidthPoints: number | null
  /** Smallest difference two independent runs of this size could resolve. */
  resolvesDifferenceOfPoints: number | null
  rowsForTenPoints: number | null
  /** The engine's sentence. Rendered verbatim or not at all. */
  says: string | null
  method: string | null
}

export type SelfGraded = {
  judgeModel: string
  rowsJudged: number
  isTheModelThatAnswered: boolean
  /** Rule-computed scores on the SAME rows - the honest thing beside a judge. */
  deterministic: Record<string, number>
  warning: string | null
}

export type EvalFailure = {
  rowIndex: number
  input: string
  expected: string
  answer: string
  failureMode: string | null
  verdicts: Record<string, boolean>
  gradedBy: string | null
  bucketedBy: string | null
  seconds: number | null
}

export type EvalReport = {
  runId: number
  complete: boolean
  reused: boolean
  evalPath: string
  evalFingerprint: string | null
  inputField: string | null
  expectedField: string | null
  metric: string
  prompt: string | null
  promptIsDefault: boolean
  provider: string | null
  model: string | null
  locality: string | null
  judgeModel: string | null
  planned: number
  graded: number
  correct: number
  rowsAvailable: number | null
  /** Only on a complete run; a partial run reports `partialScore` instead. */
  score: number | null
  partialScore: number | null
  scores: Record<string, number>
  trivialBaselineScore: number | null
  trivialAnswer: string | null
  resolution: EvalResolution
  failureHistogram: Record<string, number>
  unclassified: number
  failures: EvalFailure[]
  failuresTotal: number
  selfGraded: SelfGraded | null
  bucketsDecidedBy: string | null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}
const num = (value: unknown) => (typeof value === "number" && Number.isFinite(value) ? value : null)
const int = (value: unknown) => (typeof value === "number" && Number.isFinite(value) ? Math.trunc(value) : 0)
const str = (value: unknown) => (typeof value === "string" && value.trim() ? value : null)
const text = (value: unknown) => (typeof value === "string" ? value : "")

function counts(value: unknown): Record<string, number> {
  const out: Record<string, number> = {}
  if (!isRecord(value)) return out
  for (const [key, entry] of Object.entries(value)) if (num(entry) !== null) out[key] = entry as number
  return out
}

function verdicts(value: unknown): Record<string, boolean> {
  const out: Record<string, boolean> = {}
  if (!isRecord(value)) return out
  for (const [key, entry] of Object.entries(value)) if (typeof entry === "boolean") out[key] = entry
  return out
}

export function readResolution(value: unknown): EvalResolution {
  if (!isRecord(value)) {
    return {
      n: 0,
      ci95: null,
      halfWidthPoints: null,
      resolvesDifferenceOfPoints: null,
      rowsForTenPoints: null,
      says: null,
      method: null,
    }
  }
  const raw = value.ci_95
  const ci =
    Array.isArray(raw) && raw.length === 2 && num(raw[0]) !== null && num(raw[1]) !== null
      ? ([raw[0], raw[1]] as [number, number])
      : null
  return {
    n: int(value.n),
    ci95: ci,
    halfWidthPoints: num(value.half_width_points),
    resolvesDifferenceOfPoints: num(value.resolves_a_difference_of_at_least_points),
    rowsForTenPoints: num(value.rows_for_a_10_point_difference),
    says: str(value.says),
    method: str(value.method),
  }
}

function readSelfGraded(value: unknown): SelfGraded | null {
  if (!isRecord(value)) return null
  const judge = str(value.judge_model)
  if (!judge) return null
  return {
    judgeModel: judge,
    rowsJudged: int(value.rows_judged),
    isTheModelThatAnswered: value.is_the_model_that_answered === true,
    deterministic: counts(value.deterministic_scores_on_the_same_rows),
    warning: str(value.warning),
  }
}

function readFailures(value: unknown): EvalFailure[] {
  if (!Array.isArray(value)) return []
  const out: EvalFailure[] = []
  for (const entry of value) {
    if (!isRecord(entry) || typeof entry.row_index !== "number") continue
    out.push({
      rowIndex: entry.row_index,
      input: text(entry.input),
      expected: text(entry.expected),
      answer: text(entry.answer),
      failureMode: str(entry.failure_mode),
      verdicts: verdicts(entry.verdicts),
      gradedBy: str(entry.graded_by),
      bucketedBy: str(entry.bucketed_by),
      seconds: num(entry.seconds),
    })
  }
  return out
}

/**
 * A stored eval run, or null. `run_id` plus `planned` plus `graded` is the
 * discriminator, type-checked rather than truth-checked (a run with
 * `graded: 0` is real). A comparison also carries `run_id`; it carries
 * `against` too, and is refused so one payload never renders as two cards.
 */
export function readEvalReport(value: unknown): EvalReport | null {
  if (!isRecord(value)) return null
  if (value.ok !== true) return null
  if (typeof value.run_id !== "number") return null
  if (typeof value.planned !== "number") return null
  if (typeof value.graded !== "number") return null
  if (value.against !== undefined) return null
  return {
    runId: value.run_id,
    complete: value.complete === true,
    reused: value.reused === true,
    evalPath: text(value.eval_path),
    evalFingerprint: str(value.eval_fingerprint),
    inputField: str(value.input_field),
    expectedField: str(value.expected_field),
    metric: text(value.metric) || "exact_match",
    prompt: str(value.prompt),
    promptIsDefault: value.prompt_is_default === true,
    provider: str(value.provider),
    model: str(value.model),
    locality: str(value.locality),
    judgeModel: str(value.judge_model),
    planned: int(value.planned),
    graded: int(value.graded),
    correct: int(value.correct),
    rowsAvailable: num(value.rows_available),
    score: num(value.score),
    partialScore: num(value.partial_score),
    scores: counts(value.scores),
    trivialBaselineScore: num(value.trivial_baseline_score),
    trivialAnswer: str(value.trivial_answer),
    resolution: readResolution(value.resolution),
    failureHistogram: counts(value.failure_histogram),
    unclassified: int(value.unclassified),
    failures: readFailures(value.failures),
    failuresTotal: int(value.failures_total),
    selfGraded: readSelfGraded(value.self_graded),
    bucketsDecidedBy: str(value.buckets_decided_by),
  }
}

/**
 * Every eval run the thread has read back, newest first, one per run id.
 *
 * `run_eval` returns the report when the run finishes and every later
 * `read_eval_results` returns it again with a different `failures` cut.
 * Without this the picker shows run 4 five times; the newest sighting of an
 * id is the freshest reading of it, and is the one kept.
 */
export function distinctReports(newestFirst: readonly EvalReport[]): EvalReport[] {
  const seen = new Set<number>()
  const out: EvalReport[] = []
  for (const report of newestFirst) {
    if (seen.has(report.runId)) continue
    seen.add(report.runId)
    out.push(report)
  }
  return out
}

/** The picked report, or the newest when nothing is picked or the pick is gone. */
export function currentReport(reports: readonly EvalReport[], picked: number | null): EvalReport | null {
  if (reports.length === 0) return null
  return (picked === null ? undefined : reports.find((report) => report.runId === picked)) ?? reports[0]
}

/**
 * Was this score a rule's reading or a model's opinion? A model's grade is
 * `judge_score` in docs/diagnosis_engine.yaml, which "may never carry the
 * MEASURED origin", so the pane draws it without the ink a reading gets.
 */
export function scoreIsAnOpinion(report: EvalReport): boolean {
  return report.metric === "model_graded" || report.selfGraded !== null
}

/**
 * The eight failure buckets and the diagnosis stage each routes to,
 * transcribed from `S1_ROUTE_BY_FAILURE_MODE` in docs/diagnosis_engine.yaml
 * (the outgoing file's list, which records six invented names it replaced).
 */
export const FAILURE_MODES: Record<string, { word: string; routesTo: string }> = {
  wrong_facts: { word: "Wrong facts", routesTo: "knowledge" },
  wrong_format: { word: "Wrong format", routesTo: "format" },
  wrong_style: { word: "Wrong style", routesTo: "behaviour" },
  inconsistent: { word: "Inconsistent", routesTo: "behaviour" },
  refuses: { word: "Refuses", routesTo: "behaviour" },
  wrong_reasoning: { word: "Wrong reasoning", routesTo: "capability" },
  too_slow: { word: "Too slow", routesTo: "efficiency" },
  too_expensive: { word: "Too expensive", routesTo: "efficiency" },
}

/** A bucket's word, or its raw id so a reader can grep the engine for it. */
export const failureModeWord = (mode: string) => FAILURE_MODES[mode]?.word ?? mode
export const failureModeRoute = (mode: string) => FAILURE_MODES[mode]?.routesTo ?? null

/**
 * The bucket that dominates, and whether it dominates enough to route on.
 * `S1_MIXED_FAILURES` fires below a half share - one fine-tune cannot fix
 * four different problems - so the pane says which side of it a run fell on.
 */
export function dominantMode(histogram: Record<string, number>) {
  const entries = Object.entries(histogram)
  const total = entries.reduce((sum, [, count]) => sum + count, 0)
  if (entries.length === 0 || total <= 0) return null
  let best = entries[0]
  for (const entry of entries) if (entry[1] > best[1]) best = entry
  const share = best[1] / total
  return { mode: best[0], count: best[1], share, dominates: share >= 0.5 }
}

/** A fraction as a percentage. The one rounding rule in the pane. */
export function pct(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`
}
