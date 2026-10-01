/**
 * Result readers for the transcript's harness cards.
 *
 * Ported from the outgoing `frontend/src/lib/engine/{facts,build,storm,evals,
 * prompts,retrieval,datawork}.ts`, trimmed to what the cards draw. What the
 * panes already read is IMPORTED, not copied: the eval report
 * (`panes/eval-report.ts`), the recall report (`panes/stage-data.ts`) and the
 * diagnosis base (`panes/evidence-ledger.ts`). What is here is what no pane
 * reads yet.
 *
 * The outgoing files' rule is kept: a field the engine did not send is
 * `null`, never `0` and never a guess, and each reader keys on fields no other
 * tool returns together, so no reader has to know which tool produced the
 * result and one payload never renders as two cards.
 */

import { readResolution, type EvalResolution } from "../panes/eval-report"
import { readDiagnosis as readDiagnosisBase, type Diagnosis } from "../panes/evidence-ledger"
import { isRecord } from "./result"

const num = (value: unknown) => (typeof value === "number" && Number.isFinite(value) ? value : null)
const int = (value: unknown) => (typeof value === "number" && Number.isFinite(value) ? Math.trunc(value) : 0)
const str = (value: unknown) => (typeof value === "string" && value.trim() ? value : null)
const text = (value: unknown) => (typeof value === "string" ? value : "")
const strList = (value: unknown) =>
  Array.isArray(value) ? value.filter((entry): entry is string => typeof entry === "string") : []
const intList = (value: unknown) =>
  Array.isArray(value) ? value.filter((entry): entry is number => typeof entry === "number" && Number.isFinite(entry)) : []
const records = (value: unknown) => (Array.isArray(value) ? value.filter(isRecord) : [])

function stringMap(value: unknown): Record<string, string> {
  const out: Record<string, string> = {}
  if (!isRecord(value)) return out
  for (const [key, entry] of Object.entries(value)) if (typeof entry === "string") out[key] = entry
  return out
}

/* ── diagnosis ──────────────────────────────────────────────────────────── */

export type NextStep = {
  fact: string
  tool: string | null
  runAs: "harness" | "user" | null
  verb: string
  substantiation: string
  also: string[]
  note: string | null
}

export type Unsubstantiated = {
  fact: string
  gate: string
  declaredSource: string
  origin: string
  substantiation: string
  nextStep: NextStep | null
}

export type Alternative = {
  move: string
  text: string
  tool: string | null
  verb: string
  runAs: string
  startsNow: boolean
  why: string
}

export type FactUsed = { value: unknown; origin: string; how: string }

export type DiagnosisCardData = Diagnosis & {
  verdict: string
  help: string | null
  revisitIf: string[]
  alternatives: Alternative[]
  unsubstantiated: Unsubstantiated[]
  factsUsed: Record<string, FactUsed>
  /** Per gate, the facts the engine would not take on trust. */
  unsubstantiatedByGate: Record<string, string[]>
}

function readNextStep(value: unknown): NextStep | null {
  if (!isRecord(value)) return null
  const runAs = value.run_as
  return {
    fact: text(value.fact),
    tool: str(value.tool),
    runAs: runAs === "harness" || runAs === "user" ? runAs : null,
    verb: text(value.verb),
    substantiation: text(value.substantiation).trim(),
    also: strList(value.also),
    note: str(value.note),
  }
}

/**
 * A `run_diagnosis` result with everything the card draws, or null. The
 * base is the Evidence pane's reader, so the card and the pane accept exactly
 * the same payloads; this adds the verdict, the moves, the revisit
 * conditions and the claims the engine would not take on trust.
 */
export function readDiagnosisCard(value: unknown): DiagnosisCardData | null {
  const base = readDiagnosisBase(value)
  if (!base || !isRecord(value)) return null
  const factsUsed: Record<string, FactUsed> = {}
  if (isRecord(value.facts_used)) {
    for (const [name, entry] of Object.entries(value.facts_used)) {
      if (!isRecord(entry)) continue
      factsUsed[name] = { value: entry.value, origin: text(entry.origin) || "ASSERTED", how: text(entry.how) }
    }
  }
  const byGate: Record<string, string[]> = {}
  if (isRecord(value.gate_ledger)) {
    for (const [id, entry] of Object.entries(value.gate_ledger)) {
      if (isRecord(entry)) byGate[id] = strList(entry.unsubstantiated)
    }
  }
  return {
    ...base,
    verdict: text(value.verdict),
    help: str(value.help),
    revisitIf: strList(value.revisit_if).filter((one) => one.trim()),
    alternatives: records(value.alternatives)
      .map((one) => ({
        move: text(one.move),
        text: text(one.text).trim(),
        tool: str(one.tool),
        verb: text(one.verb),
        runAs: text(one.run_as),
        startsNow: one.starts_now === true,
        why: text(one.why),
      }))
      .filter((one) => one.text),
    unsubstantiated: records(value.unsubstantiated)
      .filter((one) => typeof one.fact === "string")
      .map((one) => ({
        fact: one.fact as string,
        gate: text(one.gate),
        declaredSource: text(one.declared_source),
        origin: text(one.origin) || "ASSERTED",
        substantiation: text(one.substantiation).trim(),
        nextStep: readNextStep(one.next_step),
      })),
    factsUsed,
    unsubstantiatedByGate: byGate,
  }
}

/* ── build proposal ─────────────────────────────────────────────────────── */

export const COST_DIMENSIONS = ["model_tokens", "model_requests", "wall_clock", "disk"] as const
export type CostDimension = (typeof COST_DIMENSIONS)[number]
export const DIMENSION_LABEL: Record<CostDimension, string> = {
  model_tokens: "Your model's tokens",
  model_requests: "Requests to your model",
  wall_clock: "Wall-clock time",
  disk: "Disk",
}

export type Estimate = {
  provenance: "MEASURED" | "INFERRED" | "UNKNOWN"
  value: number | null
  unit: string
  how: string
  findOutBy: string | null
}

export type BuildStep = { id: string; tool: string; why: string; needs: string[]; exit: string }

export type Build = {
  id: string
  title: string
  forOutcome: string
  because: string
  steps: BuildStep[]
  waves: string[][]
  cost: Partial<Record<CostDimension, Estimate>>
  exit: string
  risks: { what: string; whatWeDo: string }[]
  questions: { ask: string; why: string; fact: string; answeredBy: string }[]
  environment: { name: string; workingDir: string; egress: boolean; egressReason: string; installs: string[] } | null
}

export type Proposal = {
  outcome: string
  verdict: string
  approve: string
  build: Build
  /** The build as the engine sent it: what `POST /api/storms` compares against. */
  raw: unknown
  note: string
}

function readEstimate(value: unknown): Estimate | null {
  if (!isRecord(value)) return null
  const provenance = value.provenance
  if (provenance !== "MEASURED" && provenance !== "INFERRED" && provenance !== "UNKNOWN") return null
  return {
    provenance,
    value: provenance === "UNKNOWN" ? null : num(value.value),
    unit: text(value.unit),
    how: text(value.how).trim(),
    findOutBy: str(value.find_out_by),
  }
}

/**
 * A build, or null. Stricter than the rest on the fields a plan cannot be
 * honest without - an id, a title and at least one step, each with a tool -
 * because a plan drawn with a hole in it is a picture that lies about what
 * will run.
 */
export function readBuild(value: unknown): Build | null {
  if (!isRecord(value)) return null
  if (!str(value.id) || !str(value.title)) return null
  const steps: BuildStep[] = []
  for (const entry of records(value.steps)) {
    if (!str(entry.id) || !str(entry.tool)) return null
    steps.push({
      id: entry.id as string,
      tool: entry.tool as string,
      why: text(entry.why),
      needs: strList(entry.needs),
      exit: isRecord(entry.exit_criterion) ? text(entry.exit_criterion.stated) : "",
    })
  }
  if (steps.length === 0) return null
  const cost: Partial<Record<CostDimension, Estimate>> = {}
  if (isRecord(value.cost)) {
    for (const dimension of COST_DIMENSIONS) {
      const estimate = readEstimate(value.cost[dimension])
      if (estimate) cost[dimension] = estimate
    }
  }
  const env = isRecord(value.environment) ? value.environment : null
  return {
    id: value.id as string,
    title: value.title as string,
    forOutcome: text(value.for_outcome),
    because: text(value.because),
    steps,
    waves: Array.isArray(value.waves) ? value.waves.map(strList).filter((wave) => wave.length > 0) : [],
    cost,
    exit: isRecord(value.exit_criterion) ? text(value.exit_criterion.stated) : "",
    risks: records(value.risks).map((one) => ({ what: text(one.what), whatWeDo: text(one.what_we_do) })),
    questions: records(value.questions).map((one) => ({
      ask: text(one.ask),
      why: text(one.why),
      fact: text(one.fact),
      answeredBy: text(one.answered_by),
    })),
    environment: env
      ? {
          name: text(env.name),
          workingDir: text(env.working_dir),
          egress: env.egress === true,
          egressReason: text(env.egress_reason),
          installs: strList(env.installs),
        }
      : null,
  }
}

/** A `propose_build` proposal: `ok`, a fingerprint to approve, and a build. */
export function readProposal(value: unknown): Proposal | null {
  if (!isRecord(value) || value.ok !== true) return null
  if (!str(value.approve)) return null
  const build = readBuild(value.build)
  if (!build) return null
  return {
    outcome: text(value.outcome),
    verdict: text(value.verdict),
    approve: value.approve as string,
    build,
    raw: value.build,
    note: text(value.note),
  }
}

/* ── storms (an approved build, running) ────────────────────────────────── */

export const STEP_STATES = [
  "queued",
  "preflight",
  "running",
  "waiting_input",
  "waiting_approval",
  "stalled",
  "done",
  "failed",
  "cancelled",
] as const
export type StepState = (typeof STEP_STATES)[number]

export type StormStep = { id: string; tool: string; state: StepState; because: string }

export type Storm = {
  id: number
  state: StepState
  live: boolean
  fingerprint: string
  approvedAt: string
  steps: StormStep[]
  stalled: string[]
  deviations: string[]
  verification: { ok: boolean; stated: string; because: string } | null
}

const stepState = (value: unknown): StepState | null =>
  typeof value === "string" && (STEP_STATES as readonly string[]).includes(value) ? (value as StepState) : null

/** `GET /api/storms/{id}` (`storm.attach(...).as_dict()`), or null. */
export function readStorm(value: unknown): Storm | null {
  if (!isRecord(value) || typeof value.storm !== "number") return null
  const manifest = isRecord(value.manifest) ? value.manifest : {}
  const verification = isRecord(value.verification) ? value.verification : null
  return {
    id: value.storm,
    state: stepState(value.state) ?? "queued",
    live: value.live === true,
    fingerprint: text(manifest.fingerprint),
    approvedAt: text(manifest.approved_at),
    steps: records(value.steps).flatMap((one) => {
      const state = stepState(one.state)
      return typeof one.id === "string" && state
        ? [{ id: one.id, tool: text(one.tool), state, because: text(one.because) }]
        : []
    }),
    stalled: strList(value.stalled),
    deviations: strList(value.deviations),
    verification: verification
      ? { ok: verification.ok === true, stated: text(verification.stated), because: text(verification.because) }
      : null,
  }
}

/** Whether a storm in this state is still spending, and so worth polling and stopping. */
export const stormIsRunning = (state: StepState) => state === "queued" || state === "preflight" || state === "running"

/** The storm approved for a fingerprint, from `GET /api/storms?thread_id=`. */
export function stormIdFor(list: unknown, fingerprint: string): number | null {
  if (!isRecord(list)) return null
  for (const entry of records(list.storms)) {
    if (entry.fingerprint === fingerprint && typeof entry.id === "number") return entry.id
  }
  return null
}

/* ── eval comparison ────────────────────────────────────────────────────── */

export type EvalComparison = {
  runId: number
  against: number
  pairedRows: number
  sameRows: boolean
  score: number | null
  scoreAgainst: number | null
  delta: number
  improved: number
  regressed: number
  changed: number
  pValue: number
  test: string | null
  resolved: boolean
  verdict: "different" | "no_evidence"
  rowsThatWouldResolveThisDelta: number | null
  improvedRows: number[]
  regressedRows: number[]
  measuredOn: string | null
  resolution: EvalResolution
  says: string | null
}

/**
 * A paired comparison, or null. `verdict` is trusted only when it is one of
 * the engine's two words and agrees with `resolved`; anything else is a
 * payload this card would have to guess at, which is the surface that would
 * declare an unresolvable winner.
 */
export function readEvalComparison(value: unknown): EvalComparison | null {
  if (!isRecord(value) || value.ok !== true) return null
  if (typeof value.run_id !== "number" || typeof value.against !== "number") return null
  if (typeof value.p_value !== "number") return null
  const verdict = value.verdict
  if (verdict !== "different" && verdict !== "no_evidence") return null
  if ((verdict === "different") !== (value.resolved === true)) return null
  return {
    runId: value.run_id,
    against: value.against,
    pairedRows: int(value.paired_rows),
    // Defaults to false: an engine that did not send it cannot be asked.
    sameRows: value.same_rows === true,
    score: num(value.score),
    scoreAgainst: num(value.score_against),
    delta: num(value.delta) ?? 0,
    improved: int(value.improved),
    regressed: int(value.regressed),
    changed: int(value.changed),
    pValue: value.p_value,
    test: str(value.test),
    resolved: value.resolved === true,
    verdict,
    rowsThatWouldResolveThisDelta: num(value.rows_that_would_resolve_this_delta),
    improvedRows: intList(value.improved_rows),
    regressedRows: intList(value.regressed_rows),
    measuredOn: str(value.measured_on),
    resolution: readResolution(value.resolution),
    says: str(value.says),
  }
}

/* ── prompt bench ───────────────────────────────────────────────────────── */

const PROMPT_VERDICTS = ["first", "different", "no_evidence", "incomplete", "not_comparable", "different_models"]

export type PromptAttempt = {
  lineName: string
  evalPath: string
  version: number
  text: string
  changeNote: string | null
  author: string | null
  exemplars: number
  verdict: string
  championChanged: boolean
  score: number | null
  model: string | null
  runId: number | null
  reused: boolean
  againstVersion: number | null
  comparison: EvalComparison | null
  targeted: { mode: string; rows: number; fixed: number; resolved: boolean; says: string | null } | null
  measuredNothing: string | null
}

/** A `try_prompt` attempt: a line, a variant with a version, and a known verdict. */
export function readPromptAttempt(value: unknown): PromptAttempt | null {
  if (!isRecord(value)) return null
  const line = value.line
  const variant = value.variant
  if (!isRecord(line) || !isRecord(variant)) return null
  if (typeof line.name !== "string" || typeof variant.version !== "number") return null
  if (typeof value.verdict !== "string" || !PROMPT_VERDICTS.includes(value.verdict)) return null
  const targeted = isRecord(value.targeted) ? value.targeted : null
  return {
    lineName: line.name,
    evalPath: text(line.eval_path),
    version: variant.version,
    text: text(variant.text),
    changeNote: str(variant.change_note),
    author: str(variant.author),
    exemplars: Array.isArray(variant.exemplars) ? variant.exemplars.length : 0,
    verdict: value.verdict,
    championChanged: value.champion_changed === true,
    score: num(value.score),
    model: str(value.model),
    runId: num(value.run_id),
    reused: value.reused === true,
    againstVersion: isRecord(value.against) ? num(value.against.version) : null,
    comparison: readEvalComparison(value.comparison),
    targeted: targeted
      ? {
          mode: text(targeted.mode),
          rows: int(targeted.rows),
          fixed: int(targeted.fixed),
          resolved: targeted.resolved === true,
          says: str(targeted.says),
        }
      : null,
    measuredNothing: str(value.measured_nothing),
  }
}

/* ── chunking sweep ─────────────────────────────────────────────────────── */

export type SweepState = "refused" | "plan" | "nothing_compared" | "compared"

export type ChunkingSweep = {
  state: SweepState
  verdict: string | null
  corpusPath: string | null
  evalPath: string | null
  comparedQuestions: number
  perSetting: { setting: string; hits: number; of: number; recall: number | null; passages: number | null }[]
  planned: string[]
  comparisons: {
    a: string
    b: string
    aBetterOn: number
    bBetterOn: number
    changed: number
    p: number
    adjustedP: number | null
    separated: boolean
    better: string | null
  }[]
  familySize: number
  separatedN: number
  notBeatenByAnything: string[]
  whyNothingIsCrowned: string | null
  confirmation: { ok: boolean; why: string | null; says: string | null } | null
  stampsNothing: string
  says: string
}

/**
 * A `compare_chunkings` reply, or null. Keyed on `levers` plus
 * `stamps_nothing`, which no other tool returns together. Read in every
 * state, because a plan and a refusal are the bench working too.
 */
export function readChunkingSweep(value: unknown): ChunkingSweep | null {
  if (!isRecord(value) || !isRecord(value.levers)) return null
  if (typeof value.stamps_nothing !== "string") return null
  const verdict = str(value.verdict)
  const state: SweepState =
    value.ok !== true ? "refused" : value.ran !== true ? "plan" : verdict === "nothing_was_compared" ? "nothing_compared" : "compared"
  // A planned setting is a cut, named the way `per_setting` names one:
  // `<passage chars>/<overlap>`, with the passage count it would write.
  const planned = records(value.settings)
    .map((row) => {
      const chars = num(row.passage_chars)
      if (chars === null) return ""
      const overlap = num(row.passage_overlap)
      const passages = num(row.passages)
      return `${chars}/${overlap ?? 0}${passages !== null ? ` · ${passages} passages` : ""}${row.already_built === true ? " · already built" : ""}`
    })
    .filter(Boolean)
  const confirmation = isRecord(value.confirmation) ? value.confirmation : null
  return {
    state,
    verdict,
    corpusPath: str(value.corpus_path),
    evalPath: str(value.eval_path),
    comparedQuestions: int(value.compared_questions),
    perSetting: records(value.per_setting).map((row) => ({
      setting: text(row.setting),
      hits: int(row.hits),
      of: int(row.of),
      recall: num(row.recall),
      passages: num(row.passages),
    })),
    planned,
    comparisons: records(value.comparisons).map((row) => ({
      a: text(row.a),
      b: text(row.b),
      aBetterOn: int(row.a_better_on),
      bBetterOn: int(row.b_better_on),
      changed: int(row.changed),
      p: num(row.p) ?? 1,
      adjustedP: num(row.adjusted_p),
      separated: row.separated === true,
      better: str(row.better),
    })),
    familySize: int(value.family_size),
    separatedN: int(value.separated_n),
    notBeatenByAnything: strList(value.not_beaten_by_anything),
    whyNothingIsCrowned: str(value.why_nothing_is_crowned),
    confirmation: confirmation
      ? { ok: confirmation.ok === true, why: str(confirmation.why), says: str(confirmation.says) }
      : null,
    stampsNothing: value.stamps_nothing,
    says: text(value.says) || text(value.summary) || text(value.detail),
  }
}

/* ── data work: carve, synthesis, verification ──────────────────────────── */

export type WrittenFile = { file: string; path: string; rows: number; bytes: number | null; sha256: string | null }

function readWritten(value: unknown): WrittenFile | null {
  if (!isRecord(value) || !str(value.file)) return null
  return { file: value.file as string, path: text(value.path), rows: int(value.rows), bytes: num(value.bytes), sha256: str(value.sha256) }
}

export type CarveCardData = {
  ok: boolean
  summary: string
  into: string
  evalPath: string
  trainPath: string
  manifestPath: string | null
  rowsRead: number
  evalRows: number
  trainRows: number
  answerColumn: string | null
  wrote: WrittenFile[]
  method: { how: string; seed: string } | null
  leakage: {
    ran: boolean
    leaked: number | null
    exact: number | null
    near: number | null
    summary: string | null
    examples: { trainRow: number | null; evalRow: number | null; basis: string | null; similarity: number | null }[]
  } | null
  gradingIsStillYours: string
}

/**
 * A `carve_eval_set` (or `carve_rows`) reply that wrote files, or null.
 * Keyed on the two paths plus `into`; every refusal carries
 * `nothing_was_written`, so the two readers are disjoint on that field.
 */
export function readCarveCard(value: unknown): CarveCardData | null {
  if (!isRecord(value) || value.nothing_was_written === true) return null
  const evalPath = str(value.eval_path)
  const trainPath = str(value.train_path)
  const into = str(value.into)
  if (!evalPath || !trainPath || !into) return null
  const verification = isRecord(value.verification) ? value.verification : null
  const leakage = isRecord(value.leakage) ? value.leakage : null
  const method = isRecord(value.method) ? value.method : null
  return {
    ok: value.ok === true,
    summary: text(value.summary),
    into,
    evalPath,
    trainPath,
    manifestPath: str(value.manifest_path),
    rowsRead: int(value.rows_read),
    evalRows: int(value.eval_rows),
    trainRows: int(value.train_rows),
    answerColumn: str(value.answer_column),
    wrote: (Array.isArray(value.wrote) ? value.wrote : []).map(readWritten).filter((one): one is WrittenFile => one !== null),
    method: method ? { how: text(method.how), seed: text(method.seed) } : null,
    leakage: verification
      ? {
          ran: verification.ran === true,
          leaked: num(verification.leaked_rows),
          exact: num(verification.exact_matches),
          near: num(verification.near_matches),
          summary: str(verification.summary),
          examples: records(leakage?.examples).map((one) => ({
            trainRow: num(one.train_row),
            evalRow: num(one.eval_row),
            basis: str(one.similarity_basis),
            similarity: num(one.similarity),
          })),
        }
      : null,
    gradingIsStillYours: text(value.grading_is_still_yours),
  }
}

export type Synthesis = {
  summary: string
  syntheticPath: string
  manifestPath: string | null
  rowsRead: number
  answeredRows: number
  rowsWritten: number
  answerColumn: string | null
  seed: string
  wrote: WrittenFile[]
}

/** `synthesize_rows`: keyed on `synthetic_path` plus `into`. */
export function readSynthesis(value: unknown): Synthesis | null {
  if (!isRecord(value)) return null
  const syntheticPath = str(value.synthetic_path)
  if (!syntheticPath || !str(value.into)) return null
  return {
    summary: text(value.summary),
    syntheticPath,
    manifestPath: str(value.manifest_path),
    rowsRead: int(value.rows_read),
    answeredRows: int(value.answered_rows),
    rowsWritten: int(value.rows_written),
    answerColumn: str(value.answer_column),
    seed: text(value.seed),
    wrote: (Array.isArray(value.wrote) ? value.wrote : []).map(readWritten).filter((one): one is WrittenFile => one !== null),
  }
}

export type VerificationSample = { summary: string; samplePath: string; rowsTotal: number; rowsWritten: number; seed: string }

/** `draw_verification_sample`: keyed on `sample_path`. */
export function readVerificationSample(value: unknown): VerificationSample | null {
  if (!isRecord(value)) return null
  const samplePath = str(value.sample_path)
  if (!samplePath) return null
  return {
    summary: text(value.summary),
    samplePath,
    rowsTotal: int(value.rows_total),
    rowsWritten: int(value.rows_written),
    seed: text(value.seed),
  }
}

export type VerificationRecord = { summary: string; dataset: string; judged: number; wrong: number; verificationPath: string }

/** `record_verification`: keyed on `dataset` plus `verification_path` plus a numeric `judged`. */
export function readVerificationRecord(value: unknown): VerificationRecord | null {
  if (!isRecord(value)) return null
  const dataset = str(value.dataset)
  const path = str(value.verification_path)
  if (!dataset || !path || typeof value.judged !== "number") return null
  return { summary: text(value.summary), dataset, judged: int(value.judged), wrong: int(value.wrong), verificationPath: path }
}

/* ── sandbox results (the Stage's own subjects) ─────────────────────────── */

export type SandboxResult = {
  sandbox: string
  ok: boolean
  kind: string | null
  recipe: string | null
  exitCode: number | null
  timedOut: boolean
  runDir: string | null
  logPath: string | null
  adapter: string | null
  baseModel: string | null
  says: string | null
  egress: boolean | null
}

/**
 * A sandbox tool's reply, or null: a `sandbox` name together with one of
 * `reach`, `adapter` or `run_dir`, the pair the outgoing transcript keyed the
 * Stage chip on (`isSandboxResult`), because no other tool returns them
 * together.
 */
export function readSandboxResult(value: unknown): SandboxResult | null {
  if (!isRecord(value) || typeof value.sandbox !== "string") return null
  if (!("reach" in value || "adapter" in value || "run_dir" in value)) return null
  const reach = isRecord(value.reach) ? value.reach : null
  return {
    sandbox: value.sandbox,
    ok: value.ok !== false,
    kind: str(value.kind),
    recipe: str(value.recipe),
    exitCode: num(value.exit_code),
    timedOut: value.timed_out === true,
    runDir: str(value.run_dir),
    logPath: str(value.log_path),
    adapter: str(value.adapter),
    baseModel: str(value.base_model),
    says: str(value.says) ?? str(value.summary) ?? str(value.detail),
    egress: reach && typeof reach.egress === "boolean" ? reach.egress : null,
  }
}

/* ── plan changes (write_plan, mark_step_done, unpark_step) ─────────────── */

export type DiffRow = { kind: "ctx" | "add" | "del"; old: number | null; cur: number | null; text: string }
export type PlanChange = { rows: DiffRow[]; added: number; removed: number; clipped: number }

/** The diff `app/plandiff.py` writes onto a plan event, or null. */
export function readPlanChange(payload: unknown): PlanChange | null {
  if (!isRecord(payload) || !isRecord(payload.diff)) return null
  const diff = payload.diff
  const rows = records(diff.rows).flatMap((row): DiffRow[] => {
    const kind = row.kind
    if (kind !== "ctx" && kind !== "add" && kind !== "del") return []
    return [{ kind, old: num(row.old), cur: num(row.cur), text: text(row.text) }]
  })
  if (rows.length === 0) return null
  return { rows, added: int(diff.added), removed: int(diff.removed), clipped: int(diff.clipped) }
}

export type PlanTick = {
  ticked: string | null
  step: string | null
  saved: boolean
  openSteps: string[]
  done: number | null
  of: number | null
  next: string | null
}

/** What a plan tool answered: ticked/unparked/saved, and the open steps. */
export function readPlanTick(value: unknown): PlanTick | null {
  if (!isRecord(value)) return null
  const ticked = str(value.ticked)
  const step = str(value.step)
  const saved = value.saved === true
  if (!ticked && !step && !saved) return null
  return {
    ticked,
    step,
    saved,
    openSteps: strList(value.open_steps),
    done: num(value.done),
    of: num(value.of),
    next: str(value.next),
  }
}

/* ── what changed this turn (turn.effects) ──────────────────────────────── */

export type Effects = {
  stepsDone: string[]
  stepsParked: { step: string; why: string }[]
  facts: { fact: string; origin: string; how: string; tool: string }[]
  files: string[]
  planWrites: number
  canRevert: boolean
  empty: boolean
}

/** A `turn.effects` payload (`app/effects.py::gather`). */
export function readEffects(payload: unknown): Effects {
  const value = isRecord(payload) ? payload : {}
  const effects: Effects = {
    stepsDone: strList(value.steps_done),
    stepsParked: records(value.steps_parked)
      .filter((row) => typeof row.step === "string")
      .map((row) => ({ step: row.step as string, why: text(row.why) })),
    facts: records(value.facts)
      .filter((row) => typeof row.fact === "string")
      .map((row) => ({ fact: row.fact as string, origin: text(row.origin), how: text(row.how), tool: text(row.tool) })),
    files: strList(value.files),
    planWrites: int(value.plan_writes),
    canRevert: value.can_revert === true,
    empty: value.empty === true,
  }
  if (!effects.empty) {
    effects.empty =
      !effects.stepsDone.length && !effects.stepsParked.length && !effects.facts.length && !effects.files.length && !effects.planWrites
  }
  return effects
}

/**
 * The same fact stamped several times in one turn, folded into one row with
 * a count - the outgoing card's rule: a turn that ran a measurement four
 * times did not learn four things.
 */
export function foldRepeats<T extends { fact: string; origin: string; tool: string }>(facts: readonly T[]) {
  const order: string[] = []
  const seen = new Map<string, { fact: T; times: number }>()
  for (const one of facts) {
    const key = `${one.fact}|${one.origin}|${one.tool}`
    const had = seen.get(key)
    if (had) {
      had.times += 1
      continue
    }
    order.push(key)
    seen.set(key, { fact: one, times: 1 })
  }
  return order.map((key) => seen.get(key)!)
}
