/**
 * The storm, read off the wire — `app/storm.py` `Storm.as_dict()` and the five
 * routes `app/main.py` mounts under `/api/storms`.
 *
 * ══ WHY THE DIAGRAM DOES NOT NEED A SECOND SOURCE ══════════════════════════
 *
 * A storm hands back `build` — the manifest's `blueprint`, which is
 * `Build.as_dict()` byte for byte as the person read it — and `steps`, keyed by
 * the same `Step.id`. So the picture drawn from a proposal and the picture
 * drawn from a running storm are the same picture with a state on each node,
 * and that is not a convention this file maintains: it is what
 * `docs/THE_PROPOSAL_LOOP.md` means by "it is the same node".
 *
 * `app/storm.py` is explicit about why the blueprint is kept rather than
 * re-derived: "after a restart the picture has to come from somewhere, and it
 * comes from here rather than from a re-proposal that might differ."
 *
 * ══ APPROVAL IS A CONTRACT, AND THE ROUTE IS SHAPED LIKE ONE ═══════════════
 *
 * `POST /api/storms` does NOT accept a plan to execute. It takes the arguments
 * the proposal was made from and the fingerprint the person approved; the
 * harness proposes again and refuses with `409 not_the_plan_you_approved` if
 * what it would run now is not what was said yes to. That is why
 * `approveStorm` sends `proposal` and `build` rather than the plan: the object
 * that runs is always one the engine built and validated in the same request.
 *
 * A 409 is therefore not an error to swallow — it is the deviation surface
 * firing. `StormDeviation` carries both fingerprints, the sentences naming what
 * changed, and the new build, so the interface can say *this is what you
 * approved, this is what changed, here is the choice.*
 */

import { readBuild, type Build, type StepState } from './build';
import { STEP_STATES } from './build';
import { engineJson, postJson } from './client';

/* ── What a storm looks like ─────────────────────────────────────────────── */

export interface StormStep {
  id: string;
  tool: string;
  why: string;
  /** One of `build.STEP_STATES`. The node's state IS this. */
  state: StepState;
  /** Whether the step's exit criterion was met. Null until it finishes. */
  ok: boolean | null;
  /** The engine's sentence about why it is in this state. Shown verbatim. */
  because: string;
  verification: { ok: boolean; stated: string; saw: unknown; because: string } | null;
  outputs: Record<string, unknown>;
  attempts: number;
}

export interface Storm {
  id: number;
  threadId: number;
  /** The storm's own state, from the same nine words. */
  state: StepState;
  /** True only while THIS engine process is running it. A `running` step with
   *  nothing live is reported as `stalled`, which is the engine refusing to
   *  guess whether a step that was in flight when it died did its work. */
  live: boolean;
  build: Build;
  fingerprint: string;
  approvedAt: string;
  steps: Map<string, StormStep>;
  stalled: string[];
  /** Non-empty when the contract stopped holding. Nothing decided these were
   *  harmless; every one is a change the person has to answer. */
  deviations: string[];
  verification: { ok: boolean; stated: string; saw: unknown; because: string } | null;
}

/** The 409 from `POST /api/storms`: the plan moved between showing and saying
 *  yes. Not a failure — the contract working. */
export interface StormDeviation {
  approved: string;
  now: string;
  changed: string[];
  build: Build | null;
  whatNow: string;
}

/* ── Reading ─────────────────────────────────────────────────────────────── */

export function readStorm(value: unknown): Storm | null {
  if (!isRecord(value)) return null;
  const id = value.storm;
  if (typeof id !== 'number') return null;
  const build = readBuild(value.build);
  /* Same refusal as everywhere else: a storm whose plan this surface cannot
     read is not drawn as a plan with a state on it. */
  if (!build) return null;
  const manifest = isRecord(value.manifest) ? value.manifest : {};

  const steps = new Map<string, StormStep>();
  if (Array.isArray(value.steps)) {
    for (const entry of value.steps) {
      const step = readStormStep(entry);
      if (step) steps.set(step.id, step);
    }
  }

  return {
    id,
    threadId: typeof value.thread_id === 'number' ? value.thread_id : 0,
    state: readStepState(value.state) ?? 'queued',
    live: value.live === true,
    build,
    fingerprint:
      typeof manifest.fingerprint === 'string' ? manifest.fingerprint : '',
    approvedAt: typeof manifest.approved_at === 'string' ? manifest.approved_at : '',
    steps,
    stalled: stringList(value.stalled),
    deviations: stringList(value.deviations),
    verification: readVerification(value.verification),
  };
}

function readStormStep(value: unknown): StormStep | null {
  if (!isRecord(value)) return null;
  if (typeof value.id !== 'string' || !value.id) return null;
  const state = readStepState(value.state);
  /* A state word this surface does not know is refused rather than shown as a
     colour it has not earned. `STEP_STATES` is the whole list and the engine
     ships it on every storm payload, so a mismatch is a real disagreement. */
  if (!state) return null;
  return {
    id: value.id,
    tool: typeof value.tool === 'string' ? value.tool : '',
    why: typeof value.why === 'string' ? value.why : '',
    state,
    ok: typeof value.ok === 'boolean' ? value.ok : null,
    because: typeof value.because === 'string' ? value.because : '',
    verification: readVerification(value.verification),
    outputs: isRecord(value.outputs) ? { ...value.outputs } : {},
    attempts: typeof value.attempts === 'number' ? value.attempts : 0,
  };
}

function readStepState(value: unknown): StepState | null {
  return typeof value === 'string' && (STEP_STATES as readonly string[]).includes(value)
    ? (value as StepState)
    : null;
}

function readVerification(value: unknown): Storm['verification'] {
  if (!isRecord(value)) return null;
  return {
    ok: value.ok === true,
    stated: typeof value.stated === 'string' ? value.stated : '',
    saw: value.saw ?? null,
    because: typeof value.because === 'string' ? value.because : '',
  };
}

export function readStormDeviation(detail: unknown): StormDeviation | null {
  if (!isRecord(detail)) return null;
  if (detail.error !== 'not_the_plan_you_approved') return null;
  return {
    approved: typeof detail.approved === 'string' ? detail.approved : '',
    now: typeof detail.now === 'string' ? detail.now : '',
    changed: stringList(detail.changed),
    build: readBuild(detail.build),
    whatNow: typeof detail.what_now === 'string' ? detail.what_now : '',
  };
}

/* ── The routes ──────────────────────────────────────────────────────────── */

/**
 * Every storm in one conversation, newest first, in FULL.
 *
 * `GET /api/storms` is a summary: `list_for_thread` selects eight columns off
 * the `storms` table and nothing else — no manifest, no blueprint, no step
 * states. Only `GET /api/storms/{id}` re-attaches and folds the state out of
 * the log. So the list names them and each one is then fetched.
 *
 * Found by looking rather than by reading: a storm was approved and run
 * successfully, and the card went on offering the approval buttons, because
 * `readStorm` was refusing every summary row for having no build in it — which
 * is the reader doing its job on a payload that was never the whole thing.
 */
export async function listStorms(threadId: number): Promise<Storm[]> {
  const payload = await engineJson(
    `/api/storms?thread_id=${encodeURIComponent(threadId)}`,
  );
  if (!isRecord(payload) || !Array.isArray(payload.storms)) return [];
  const ids: number[] = [];
  for (const entry of payload.storms) {
    if (isRecord(entry) && typeof entry.id === 'number') ids.push(entry.id);
  }
  const full = await Promise.all(
    ids.map((id) => getStorm(id).catch(() => null)),
  );
  return full.filter((storm): storm is Storm => storm !== null);
}

export async function getStorm(stormId: number): Promise<Storm | null> {
  return readStorm(await engineJson(`/api/storms/${encodeURIComponent(stormId)}`));
}

/**
 * Say yes to a specific plan, and to that plan only.
 *
 * `proposal` is the arguments `propose_build` was called with — not the plan.
 * The engine re-proposes from them and compares fingerprints, which is what
 * makes the contract survive the HTTP boundary. `build` is sent only so a
 * mismatch can be reported as what CHANGED rather than as a bare refusal.
 */
export function approveStorm(
  threadId: number,
  approve: string,
  proposal: Record<string, unknown>,
  build: unknown,
): Promise<unknown> {
  return postJson('/api/storms', {
    thread_id: threadId,
    approve,
    proposal,
    build,
  });
}

/** Start it. Returns immediately; the work reports itself into the thread. */
export function runStorm(stormId: number, restartStalled: string[] = []): Promise<unknown> {
  return postJson(`/api/storms/${encodeURIComponent(stormId)}/run`, {
    background: true,
    restart_stalled: restartStalled,
  });
}

export function cancelStorm(stormId: number): Promise<unknown> {
  return postJson(`/api/storms/${encodeURIComponent(stormId)}/cancel`, {});
}

/* ── small readers ───────────────────────────────────────────────────────── */

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((entry): entry is string => typeof entry === 'string');
}
