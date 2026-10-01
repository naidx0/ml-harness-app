/**
 * Which card a harness tool result draws, and which tools get a card at all.
 *
 * TWO QUESTIONS, ANSWERED IN TWO PLACES ON PURPOSE.
 *
 * Their renderer looks a card up by TOOL NAME (`ToolRegistry.render(tool)`),
 * so something has to name the tools. But the outgoing transcript never
 * dispatched on names: it asked each reader whether it recognised the
 * RESULT, because `read_eval_results` answers with a report or a comparison
 * depending on its arguments, and `carve_rows` returns what `carve_eval_set`
 * does. Keying the drawing on the name would put the wrong card on one of
 * those the day an argument changes the shape.
 *
 * So `HARNESS_CARD_TOOLS` is only the list of doors - every tool the outgoing
 * transcript had a card for, with the card(s) each is known to produce, taken
 * from the `@tool(...)` declarations in app/tools/*.py and the readers the
 * outgoing `Transcript.tsx` ran - and `cardKindOf` decides the drawing from
 * the result, exactly as the old transcript did. A registered tool whose
 * result no reader recognises keeps the renderer it would have had anyway.
 */

import { readEvalReport } from "../panes/eval-report"
import { readRecall } from "../panes/stage-data"
import {
  readCarveCard,
  readChunkingSweep,
  readDiagnosisCard,
  readEvalComparison,
  readPlanTick,
  readPromptAttempt,
  readProposal,
  readSandboxResult,
  readSynthesis,
  readVerificationRecord,
  readVerificationSample,
} from "./readers"

export type CardKind =
  | "diagnosis"
  | "proposal"
  | "eval"
  | "compare"
  | "prompt"
  | "sweep"
  | "recall"
  | "carve"
  | "synthesis"
  | "verification-sample"
  | "verification"
  | "sandbox"
  | "plan"

/**
 * The readers in the order the outgoing transcript drew its cards. Each keys
 * on fields no other tool returns together, so the order only matters for a
 * payload two readers would both accept. A comparison carries `against`,
 * which `readEvalReport` refuses. A prompt attempt is tried BEFORE the eval
 * readers because it is the narrower shape (a `line` and a versioned
 * `variant`) and it may also carry a run's own fields; its comparison is
 * drawn inside its own card.
 */
const DETECTORS: readonly [CardKind, (value: unknown) => unknown][] = [
  ["diagnosis", readDiagnosisCard],
  ["proposal", readProposal],
  ["prompt", readPromptAttempt],
  ["compare", readEvalComparison],
  ["eval", readEvalReport],
  ["sweep", readChunkingSweep],
  ["recall", readRecall],
  ["carve", readCarveCard],
  ["synthesis", readSynthesis],
  ["verification-sample", readVerificationSample],
  ["verification", readVerificationRecord],
  ["sandbox", readSandboxResult],
  ["plan", readPlanTick],
]

/** The card a result draws, or null when no reader recognises it. */
export function cardKindOf(result: unknown): CardKind | null {
  for (const [kind, read] of DETECTORS) if (read(result) !== null) return kind
  return null
}

/** Every reader that accepts a result, in order - for the disjointness test. */
export function kindsAccepting(result: unknown): CardKind[] {
  return DETECTORS.filter(([, read]) => read(result) !== null).map(([kind]) => kind)
}

/**
 * The results the Stage draws, so the card offers to open it: the outgoing
 * transcript's `staged` set - a diagnosis, an eval, a comparison, a prompt
 * attempt, a recall, a carve, and a sandbox run - and nothing else.
 */
export const STAGED: ReadonlySet<CardKind> = new Set(["diagnosis", "eval", "compare", "prompt", "recall", "carve", "sandbox"])

/**
 * Every tool that gets a harness card, with the card(s) it is known to
 * produce. Parity rows (docs/PARITY.md): 5.11 eval, 5.12 stage inline,
 * 5.17 diagnosis/next step, 5.18 proposal and storm, 5.19 what changed
 * (drawn under whichever card is last in the turn), 5.20 the read-only cards
 * and the plan diff.
 */
export const HARNESS_CARD_TOOLS: Readonly<Record<string, readonly CardKind[]>> = {
  // 5.17 - the verdict and its next steps.
  run_diagnosis: ["diagnosis"],
  // 5.18 - the build proposal, its approval, and the storm it starts.
  propose_build: ["proposal"],
  // 5.11 / 5.20 - the bench. `read_eval_results` with `against` compares.
  run_eval: ["eval"],
  read_eval_results: ["eval", "compare"],
  // Not here, on purpose: `rebucket_failures` and `measure_baseline` answer
  // in shapes no outgoing reader drew (no `planned`/`graded`), so the old
  // transcript printed them as tables and they keep their default renderer.
  // 5.20 - the prompt bench.
  try_prompt: ["prompt"],
  // 5.20 - retrieval: the chunking sweep and the recall report.
  compare_chunkings: ["sweep"],
  measure_retriever_recall: ["recall"],
  // 5.20 - data work that writes files.
  carve_eval_set: ["carve"],
  carve_rows: ["carve"],
  synthesize_rows: ["synthesis"],
  draw_verification_sample: ["verification-sample"],
  record_verification: ["verification"],
  // 5.12 - the sandbox tools, drawn as the Stage's compact inline summary.
  make_sandbox: ["sandbox"],
  build_environment: ["sandbox"],
  run_in_sandbox: ["sandbox"],
  score_the_adapter: ["sandbox"],
  // 5.20 plan diff - the tools that rewrite the plan. The diff is on the
  // plan event the tool wrote, read from the thread's log.
  write_plan: ["plan"],
  mark_step_done: ["plan"],
  unpark_step: ["plan"],
}

export const HARNESS_CARD_TOOL_NAMES: readonly string[] = Object.keys(HARNESS_CARD_TOOLS)

/** A short title for a card, the kicker the outgoing cards printed. */
export const CARD_TITLE: Record<CardKind, string> = {
  diagnosis: "Diagnosis",
  proposal: "Proposal",
  eval: "Eval run",
  compare: "Compared",
  prompt: "Prompt",
  sweep: "Chunking sweep",
  recall: "Retriever recall",
  carve: "Carved an eval set",
  synthesis: "Synthesised rows",
  "verification-sample": "Verification sample",
  verification: "Verification recorded",
  sandbox: "Sandbox",
  plan: "Plan",
}
