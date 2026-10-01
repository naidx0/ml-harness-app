/**
 * The prompt bench, read off the wire. `app/tools/prompts.py`.
 *
 * ══ WHY THIS IS A THIN FILE AND NOT A SECOND COMPARISON READER ═════════════
 *
 * `try_prompt` returns its pairing under `comparison`, and that value IS an
 * `evals.compare()` payload — same keys, same `verdict`, same `resolved`,
 * because the bench calls `evals.compare` rather than reimplementing it. So
 * this file does NOT parse the comparison: it hands that key straight to
 * `readEvalComparison` and the same card draws it.
 *
 * That is worth being deliberate about. A second reader would be a second
 * chance to disagree with the first about when a difference is real, and the
 * whole product rests on there being exactly one answer to that question.
 * `prompts.py` makes the same argument from the other side — *"`attempt` never
 * decides significance itself. It reads `resolved` off"* `evals.compare` — and
 * this file is that sentence in TypeScript.
 *
 * ══ WHAT IS ACTUALLY NEW HERE ══════════════════════════════════════════════
 *
 * One fact: **whether the champion changed.** The eval bench can say two runs
 * differ; only the prompt bench decides whether that is enough to promote a
 * prompt, and `champion_changed: false` beside a measured fifteen-point gap is
 * the most product-defining thing either bench outputs. It is the refusal, made
 * durable — the prompt that "looked better" is not recorded as better.
 *
 * The verdict vocabulary is wider than the eval bench's two, and every one of
 * the six is a real state the card must be able to say out loud rather than
 * fall through on.
 */

import type { EvalComparison } from './evals';
import { readEvalComparison } from './evals';

/** `try_prompt`'s six verdicts, transcribed from `app/tools/prompts.py`. */
export type PromptVerdict =
  | 'first'
  | 'different'
  | 'no_evidence'
  | 'incomplete'
  | 'not_comparable'
  | 'different_models';

const VERDICTS: readonly string[] = [
  'first',
  'different',
  'no_evidence',
  'incomplete',
  'not_comparable',
  'different_models',
];

export interface PromptLine {
  id: number;
  name: string;
  evalPath: string;
  metric: string;
  sample: number;
}

export interface PromptVariant {
  id: number;
  version: number;
  parentId: number | null;
  text: string;
  changeNote: string | null;
  targets: string | null;
  exemplars: number;
  author: string | null;
}

/** The version this one was measured against. Absent on the first attempt. */
export interface PromptRival {
  variantId: number;
  version: number;
  runId: number;
  score: number | null;
  model: string | null;
}

/** What a targeted change did to the ONE bucket it was aimed at. */
export interface BucketEffect {
  mode: string;
  rows: number;
  fixed: number;
  resolved: boolean;
  says: string | null;
}

export interface PromptAttempt {
  line: PromptLine;
  variant: PromptVariant;
  verdict: PromptVerdict | (string & {});
  /** THE FACT THIS BENCH EXISTS TO PRODUCE. A prompt is promoted or it is not,
   *  and an unresolvable improvement is not. */
  championChanged: boolean;
  score: number | null;
  model: string | null;
  runId: number | null;
  complete: boolean;
  reused: boolean;
  against: PromptRival | null;
  /** The pairing, parsed by the EVAL bench's reader. Null when there was
   *  nothing to pair — the first version of a line, or two runs with no shared
   *  rows. */
  comparison: EvalComparison | null;
  targeted: BucketEffect | null;
  says: string | null;
  /** `try_prompt` declares `measures=()`; the sentence saying so is the
   *  engine's own and is rendered rather than paraphrased. */
  measuredNothing: string | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function num(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function int(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? Math.trunc(value) : fallback;
}

function str(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

/**
 * One `try_prompt` attempt, or null.
 *
 * `ok` IS NOT CHECKED, and that is deliberate rather than sloppy. `prompts.py`
 * sets `ok: false` for the `incomplete` verdict — a run that hit its deadline
 * with rows still to grade — while returning a complete, renderable attempt
 * with a line, a version and a reason. That is a state to draw, not an error to
 * fall through on, and requiring `ok` here would send the one case where the
 * user most needs an explanation to the key/value table.
 *
 * The discriminator is instead the shape only this tool produces: a `line` with
 * a name, a `variant` with a version, and a verdict from the declared six.
 */
export function readPromptAttempt(value: unknown): PromptAttempt | null {
  if (!isRecord(value)) return null;
  const line = value.line;
  const variant = value.variant;
  if (!isRecord(line) || !isRecord(variant)) return null;
  if (typeof line.name !== 'string') return null;
  if (typeof variant.version !== 'number') return null;
  const verdict = value.verdict;
  if (typeof verdict !== 'string' || !VERDICTS.includes(verdict)) return null;

  const rival = isRecord(value.against)
    ? {
        variantId: int(value.against.variant_id),
        version: int(value.against.version),
        runId: int(value.against.run_id),
        score: num(value.against.score),
        model: str(value.against.model),
      }
    : null;

  const targeted = isRecord(value.targeted)
    ? {
        mode: typeof value.targeted.mode === 'string' ? value.targeted.mode : '',
        rows: int(value.targeted.rows),
        fixed: int(value.targeted.fixed),
        resolved: value.targeted.resolved === true,
        says: str(value.targeted.says),
      }
    : null;

  return {
    line: {
      id: int(line.id),
      name: line.name,
      evalPath: typeof line.eval_path === 'string' ? line.eval_path : '',
      metric: typeof line.metric === 'string' ? line.metric : 'exact_match',
      sample: int(line.sample),
    },
    variant: {
      id: int(variant.id),
      version: variant.version,
      parentId: num(variant.parent_id),
      text: typeof variant.text === 'string' ? variant.text : '',
      changeNote: str(variant.change_note),
      targets: str(variant.targets),
      exemplars: Array.isArray(variant.exemplars) ? variant.exemplars.length : 0,
      author: str(variant.author),
    },
    verdict,
    championChanged: value.champion_changed === true,
    score: num(value.score),
    model: str(value.model),
    runId: num(value.run_id),
    complete: value.complete === true,
    reused: value.reused === true,
    against: rival,
    /* Straight to the eval bench's reader. One definition of "resolved" in the
       whole interface, for the same reason the engine has one. */
    comparison: readEvalComparison(value.comparison),
    targeted,
    says: str(value.says),
    measuredNothing: str(value.measured_nothing),
  };
}

/* ── The bench declining ──────────────────────────────────────────────────
   FOUND BY DRIVING THE PANEL, NOT BY READING THE CONTRACT. Re-running a prompt
   that was byte-for-byte a version already scored came back as `ok: false`,
   `error: "nothing_changed"` — and the control panel headed it **Failed** over
   a key/value table. Nothing failed. The bench recognised the prompt, spent
   nothing, and said so.

   That is the same defect `ProposalRefusalCard` exists to fix, and the reason
   this list is narrow: only the refusals where the bench WORKED and declined
   are here. A call with an unknown metric or a missing prompt really is a
   malformed call, and dressing those as considered refusals would be the
   opposite error. */

export type PromptRefusalKind =
  | 'nothing_changed'
  | 'different_instrument'
  | 'no_failures_to_learn_from';

const REFUSALS: readonly string[] = [
  'nothing_changed',
  'different_instrument',
  'no_failures_to_learn_from',
];

export interface PromptRefusal {
  error: PromptRefusalKind;
  detail: string;
  /** The version this prompt already is, when the bench recognised it. */
  variantId: number | null;
  lineId: number | null;
}

export function readPromptRefusal(value: unknown): PromptRefusal | null {
  if (!isRecord(value)) return null;
  if (value.ok !== false) return null;
  const error = value.error;
  if (typeof error !== 'string' || !REFUSALS.includes(error)) return null;
  return {
    error: error as PromptRefusalKind,
    detail: typeof value.detail === 'string' ? value.detail : '',
    variantId: num(value.variant_id),
    lineId: num(value.line_id),
  };
}
