/**
 * The Stage's one read, `GET /api/threads/{id}/stage` (app/stage.py `build`),
 * and the pure arithmetic its five panels do on it.
 *
 * Ported from the outgoing `frontend/src/lib/engine/stage.ts` and the helpers
 * inside `frontend/src/components/Stage.tsx`. Field names are the engine's
 * own snake_case, kept verbatim: every number on the Stage is quoted with its
 * run id, and a renamed field is one more place for the two to drift apart.
 * The Stage computes no statistic. Every p-value, delta and resolution here
 * is the engine's; what this file computes is layout - which cell flipped
 * against the baseline, which run is selected, what the reading band says.
 */

import { shortModelName } from "../providers/local"

export type StageRow ={ row_index: number; correct: boolean; failure_mode: string | null }

export type StageRun = {
  run_id: number
  complete: boolean
  metric: string
  prompt_is_default: boolean
  model: string | null
  judge_model: string | null
  planned: number
  graded: number
  correct: number
  score: number | null
  resolution: {
    n: number
    ci_95: [number, number]
    resolves_a_difference_of_at_least_points: number
    rows_for_a_10_point_difference: number
  } | null
  rows: StageRow[]
}

export type StageComparison = {
  run_id: number
  against: number
  delta: number
  improved: number
  regressed: number
  p_value: number
  verdict: "different" | "no_evidence" | string
  rows_that_would_resolve_this_delta: number | null
}

export type StageSandboxRun = {
  name: string
  kind: string | null
  base_model: string | null
  max_steps: number | null
  steps: number | null
  elapsed_seconds: number | null
  peak_vram_gb: number | null
  final_loss: number | null
  curve: { step: number; loss: number }[]
}

export type StageSandbox = {
  ok?: boolean
  name: string
  purpose?: string
  snapshotted?: { path: string; bytes: number; digest: string }[]
  pinned?: { recipe?: string; interpreter?: string; pinned?: boolean; on_disk_gb?: number }
  reach?: { egress: boolean }
  runs: StageSandboxRun[]
}

export type StageGpu = {
  occupancy: { used_gb: number; total_gb: number; resident: { name: string; size_gb: number }[]; source: string } | null
  guard: string | null
  crowded_above_gb: number
}

export type StageFact = { fact: string; value: unknown; origin: string; tool?: string | null; how?: string | null }

/** `journey_report.build`: the verdict, the gate ledger, and the facts with origins. */
export type StageDiagnosis = {
  verdict?: {
    outcome?: string | null
    say?: string | null
    gates?: Record<string, { status?: string; clause?: string | null }>
  }
  facts?: StageFact[]
}

export type StagePayload = {
  thread_id: number
  baseline_run_id: number | null
  runs: StageRun[]
  comparisons: Record<string, StageComparison>
  sandboxes: StageSandbox[]
  gpu: StageGpu
  diagnosis: StageDiagnosis | null
  reads: Record<string, string>
}

export type StagePanelId = "bench" | "sandbox" | "progression" | "gates" | "retrieval"

export const STAGE_PANELS: readonly { id: StagePanelId; title: string }[] = [
  { id: "bench", title: "Bench" },
  { id: "sandbox", title: "Sandbox" },
  { id: "progression", title: "Progression" },
  { id: "gates", title: "Gate map" },
  { id: "retrieval", title: "Retrieval & split" },
]

/* formatting */

export function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`
}

export function points(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? "—" : value.toFixed(digits)
}

export function secondsLabel(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—"
  if (seconds < 90) return `${Math.round(seconds)} s`
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(Math.round(seconds % 60)).padStart(2, "0")}`
}

/** A run's model as a person reads it (providers/local.ts `shortModelName`). */
export function shortModel(model: string | null | undefined): string {
  return shortModelName(model) || "—"
}

/**
 * A fact's value as the ledger would print it: whole numbers as they are,
 * fractions to three places, objects as `key value` pairs rather than JSON.
 */
export function factValue(value: unknown): string {
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3)
  if (value === null || value === undefined) return "—"
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, entry]) => `${key} ${String(entry)}`)
      .join(" · ")
  }
  return String(value)
}

/* runs */

/** A run's one-word label: what changed, not the prompt. */
export function runLabel(run: StageRun, baselineId: number | null): string {
  if (run.run_id === baselineId) return "baseline"
  const model = run.model ?? ""
  if (/adapter disabled|\(base\)|bare/i.test(model)) return "bare base"
  if (/adapter/i.test(model)) return "adapter"
  if (run.prompt_is_default) return "default prompt"
  return "prompt"
}

/** The run the Stage is showing: the picked one, or the newest complete one. */
export function currentRun(payload: StagePayload, runId: number | null): StageRun | null {
  if (runId !== null) {
    const picked = payload.runs.find((run) => run.run_id === runId)
    if (picked) return picked
  }
  for (let i = payload.runs.length - 1; i >= 0; i -= 1) if (payload.runs[i].complete) return payload.runs[i]
  return payload.runs[payload.runs.length - 1] ?? null
}

export function targetOf(payload: StagePayload): { value: number; origin: string } | null {
  const fact = (payload.diagnosis?.facts ?? []).find((entry) => entry.fact === "target_score")
  if (!fact || typeof fact.value !== "number") return null
  return { value: fact.value, origin: fact.origin ?? "DEFAULTED" }
}

export type Cell = "held" | "right" | "wrong" | "up" | "down"

/**
 * One run's row of the lattice. A cell is held (not graded), right, wrong,
 * or - against the baseline, for any run that is not the baseline - flipped
 * up (baseline wrong, this right) or flipped down (baseline right, this
 * wrong). The flips are the whole of a paired comparison; the percentages
 * are not.
 */
export function latticeRow(run: StageRun, baseline: StageRun | null, width: number): Cell[] {
  const graded = new Map(run.rows.map((row) => [row.row_index, row.correct]))
  const baseWrong = new Set((baseline?.rows ?? []).filter((row) => !row.correct).map((row) => row.row_index))
  const baseGraded = new Set((baseline?.rows ?? []).map((row) => row.row_index))
  const out: Cell[] = []
  for (let i = 0; i < width; i += 1) {
    const verdict = graded.get(i)
    if (verdict === undefined) {
      out.push("held")
      continue
    }
    if (baseline && run.run_id !== baseline.run_id && baseGraded.has(i)) {
      const wasWrong = baseWrong.has(i)
      if (wasWrong && verdict) {
        out.push("up")
        continue
      }
      if (!wasWrong && !verdict) {
        out.push("down")
        continue
      }
    }
    out.push(verdict ? "right" : "wrong")
  }
  return out
}

/** Training runs with a loss curve worth drawing, box by box. */
export function trainRuns(payload: StagePayload): { box: string; run: StageSandboxRun }[] {
  const out: { box: string; run: StageSandboxRun }[] = []
  for (const box of payload.sandboxes) {
    for (const run of box.runs) if (run.kind === "train" && run.curve.length > 1) out.push({ box: box.name, run })
  }
  return out
}

/* reading bands: what happened, why it matters, what to do */

export type Reading = { k: "what" | "why" | "do"; claim: string; body: string }

export const READING_LABEL: Record<Reading["k"], string> = {
  what: "What happened",
  why: "Why it matters",
  do: "What to do",
}

export function benchReading(
  payload: StagePayload,
  selected: StageRun | null,
  paired: StageComparison | null,
  target: number | null,
): Reading[] {
  const complete = payload.runs.filter((run) => run.complete)
  if (complete.length === 0) return []
  const best = [...complete].sort((a, b) => (b.score ?? 0) - (a.score ?? 0))[0]
  const out: Reading[] = [
    {
      k: "what",
      claim: `${complete.length} run${complete.length === 1 ? "" : "s"} graded the same ${best.planned} rows.`,
      body: `The best, run ${best.run_id}, got ${best.correct} right (${pct(best.score)}). Each green cell is one row the judge accepted.`,
    },
  ]
  if (paired && selected) {
    out.push({
      k: "why",
      claim: "Only rows that flipped count.",
      body: `Run ${selected.run_id} vs ${paired.against}: ${paired.improved} went right, ${paired.regressed} went wrong, p=${points(
        paired.p_value,
        3,
      )} - ${paired.verdict === "different" ? "a real difference" : "so these rows cannot tell the two apart"}.`,
    })
  }
  if (selected?.resolution) {
    out.push({
      k: "do",
      claim:
        target !== null && (best.score ?? 0) < target
          ? `No arm reaches your ${pct(target)} bar.`
          : "Grade more rows before believing a delta.",
      body: `${selected.resolution.rows_for_a_10_point_difference} rows resolve a 10-point difference; ${best.planned} resolve only about ${points(
        selected.resolution.resolves_a_difference_of_at_least_points,
        0,
      )} points.`,
    })
  }
  return out
}

export function sandboxReading(payload: StagePayload): Reading[] {
  const runs = trainRuns(payload)
  const out: Reading[] = []
  if (runs.length >= 2) {
    const [a, b] = [runs[0].run, runs[1].run]
    const rateA = a.elapsed_seconds && a.steps ? a.steps / a.elapsed_seconds : null
    const rateB = b.elapsed_seconds && b.steps ? b.steps / b.elapsed_seconds : null
    if (rateA && rateB) {
      const slow = rateA < rateB ? a : b
      const fast = rateA < rateB ? b : a
      const ratio = Math.max(rateA, rateB) / Math.min(rateA, rateB)
      out.push({
        k: "what",
        claim: `${slow.name} ran ${ratio.toFixed(0)}× slower per step than ${fast.name}.`,
        body: `${slow.name}: ${slow.steps} steps in ${secondsLabel(slow.elapsed_seconds)}; ${fast.name}: ${fast.steps} steps in ${secondsLabel(
          fast.elapsed_seconds,
        )}. Peak memory ${points(slow.peak_vram_gb, 2)} GB and ${points(fast.peak_vram_gb, 2)} GB, read off each run's own log.`,
      })
      if (ratio > 3) {
        out.push({
          k: "why",
          claim: "Paging looks exactly like training.",
          body: "A run that does not fit the card spills into system memory and still prints steps and falling loss. Only the rate says it is crawling.",
        })
      }
    }
  }
  const occupancy = payload.gpu.occupancy
  if (occupancy) {
    out.push({
      k: "do",
      claim: payload.gpu.guard ? "Unload what is resident before training." : "The guard reads the card before every run.",
      body: payload.gpu.guard
        ? `${occupancy.used_gb} of ${occupancy.total_gb} GB is held right now. The guard names the resident model and refuses; config.share_gpu runs anyway and accepts the paging.`
        : `${occupancy.used_gb} of ${occupancy.total_gb} GB in use, under the ${payload.gpu.crowded_above_gb} GB line, so a training run starts.`,
    })
  }
  return out
}

export function progressionReading(
  series: { box: string; run: StageSandboxRun }[],
  adapters: StageRun[],
  baseline: StageRun | null,
): Reading[] {
  const out: Reading[] = []
  if (series.length > 0) {
    const first = series[0].run
    out.push({
      k: "what",
      claim: `Loss fell from ${points(first.curve[0].loss, 2)} to ${points(first.curve[first.curve.length - 1].loss, 2)} over ${
        first.steps ?? first.max_steps ?? "?"
      } steps.`,
      body: "Loss is how surprised the model is by the next word of the true answer. Falling loss means the training sentences are being learned.",
    })
  }
  if (adapters.length > 0 && baseline) {
    const best = [...adapters].sort((a, b) => (b.score ?? 0) - (a.score ?? 0))[0]
    const behind = (best.score ?? 0) < (baseline.score ?? 0)
    out.push({
      k: "why",
      claim: behind ? "Reciting is not knowing." : "The adapter beat the baseline on held-out rows.",
      body: behind
        ? `The best adapter (run ${best.run_id}) scored ${pct(best.score)} on held-out rows against the baseline's ${pct(baseline.score)} (run ${baseline.run_id}). A falling loss with a flat held-out score is overfitting, drawn.`
        : `Run ${best.run_id} scored ${pct(best.score)} against ${pct(baseline.score)} on the same rows. Read the paired verdict on the Bench before calling it a win.`,
    })
  }
  out.push({
    k: "do",
    claim: "Read both charts together, always.",
    body: "A loss line alone will fool you. The held-out score is the one that costs something, and it is measured on rows the training never saw.",
  })
  return out
}

export function gatesReading(diagnosis: StageDiagnosis, passed: number): Reading[] {
  const outcome = diagnosis.verdict?.outcome ?? ""
  const facts = diagnosis.facts ?? []
  const measured = facts.filter((fact) => fact.origin === "MEASURED").length
  const stated = facts.filter((fact) => fact.origin === "STATED").length
  return [
    {
      k: "what",
      claim: `${passed} of 5 gates opened on ${measured} measured and ${stated} stated facts.`,
      body: "A gate is a question the ledger refuses to skip on the way to \"train\". Instruments or you answered the open ones; a model's claim opens nothing.",
    },
    {
      k: "why",
      claim: outcome.startsWith("NO_TRAIN")
        ? "The verdict is not to train, and it says why."
        : outcome.startsWith("TRAIN")
          ? "Every gate is open; training is on the table."
          : "The walk stopped before a verdict.",
      body: outcome.startsWith("NO_TRAIN")
        ? "The route ran through the cheaper levers first. Where it stopped is the sentence quoted above, verbatim from the ledger."
        : "What is still shut reads Not checked; the next action names the instrument that opens it.",
    },
  ]
}

/* retrieval and carve, read from the thread's tool results */

export type RecallPoint = { k: number; hits: number; of: number; recall: number | null }

export type RecallReport = {
  indexId: number | null
  indexName: string | null
  k: number
  hits: number | null
  recall: number | null
  curve: RecallPoint[]
  questionsScored: number
  questionsEligible: number
  unresolvedN: number
  unresolvedRows: string[]
  stampable: boolean
  notMeasured: string
}

export type Carve = { rowsRead: number; evalRows: number; trainRows: number; leaked: number | null; checked: boolean }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}
const num = (value: unknown) => (typeof value === "number" && Number.isFinite(value) ? value : null)
const int = (value: unknown) => (typeof value === "number" && Number.isFinite(value) ? Math.trunc(value) : 0)
const str = (value: unknown) => (typeof value === "string" && value.trim() ? value : null)

/**
 * A `measure_retriever_recall` result, or null. `stampable` plus
 * `recall_curve` plus `questions_scored` is the discriminator, as in the
 * outgoing reader: no other retrieval tool has ever carried `stampable`.
 */
export function readRecall(value: unknown): RecallReport | null {
  if (!isRecord(value)) return null
  if (typeof value.stampable !== "boolean") return null
  if (!Array.isArray(value.recall_curve)) return null
  if (typeof value.questions_scored !== "number") return null
  return {
    indexId: num(value.index_id),
    indexName: str(value.index_name),
    k: int(value.k),
    hits: num(value.hits),
    recall: num(value.recall_at_k),
    curve: value.recall_curve.filter(isRecord).map((row) => ({
      k: int(row.k),
      hits: int(row.hits),
      of: int(row.of),
      recall: num(row.recall),
    })),
    questionsScored: int(value.questions_scored),
    questionsEligible: int(value.questions_eligible),
    unresolvedN: int(value.unresolved_n),
    unresolvedRows: Array.isArray(value.unresolved_ground_truth)
      ? value.unresolved_ground_truth.filter((entry): entry is string => typeof entry === "string")
      : [],
    stampable: value.stampable,
    notMeasured: typeof value.not_measured === "string" ? value.not_measured : "",
  }
}

/**
 * A `carve_eval_set` result, or null. Keyed on the two paths plus `into`,
 * which no other tool returns together; a refusal says `nothing_was_written`.
 */
export function readCarve(value: unknown): Carve | null {
  if (!isRecord(value) || value.nothing_was_written === true) return null
  if (!str(value.eval_path) || !str(value.train_path) || !str(value.into)) return null
  const verification = isRecord(value.verification) ? value.verification : null
  return {
    rowsRead: int(value.rows_read),
    evalRows: int(value.eval_rows),
    trainRows: int(value.train_rows),
    leaked: verification ? num(verification.leaked_rows) : null,
    checked: verification !== null,
  }
}

export function retrievalReading(recall: RecallReport | null, carve: Carve | null, payload: StagePayload): Reading[] {
  const out: Reading[] = []
  if (recall && recall.curve.length > 0) {
    const first = recall.curve[0]
    const last = recall.curve[recall.curve.length - 1]
    out.push({
      k: "what",
      claim: `Recall rises from ${pct(first.recall)} at k=${first.k} to ${pct(last.recall)} at k=${last.k}.`,
      body: "Recall@k asks, for each question, whether the right document is in the retriever's top k. It scores the retriever alone, before any model answers.",
    })
    out.push(
      recall.unresolvedN > 0
        ? {
            k: "why",
            claim: `${recall.unresolvedN} question(s) name something this index does not hold.`,
            body: "Nothing indexed from this corpus can reach them, and nothing trained on it could either. The harness recorded no fact rather than a recall over the rows that happened to join.",
          }
        : {
            k: "why",
            claim: recall.stampable ? "The number is on the ledger as MEASURED." : "The number was not recorded.",
            body: recall.stampable
              ? `${recall.hits} of ${recall.questionsScored} questions had the right document in the top ${recall.k}. A retriever this good makes the generator the bottleneck.`
              : recall.notMeasured,
          },
    )
  }
  if (carve) {
    out.push({
      k: "do",
      claim:
        carve.leaked === 0 ? "The split does not leak. Watch what it isolates instead." : "Check the split before trusting any score.",
      body: `${carve.evalRows} eval and ${carve.trainRows} train rows from ${carve.rowsRead} read. A hash split can put a whole concept on one side; split by concept when the data has one.`,
    })
  } else if (payload.runs.length > 0) {
    out.push({
      k: "do",
      claim: "Index the whole knowledge base for retrieval.",
      body: "A deployed retriever sits on all of it, not on a training half. The held-out questions still never enter the index.",
    })
  }
  return out
}
