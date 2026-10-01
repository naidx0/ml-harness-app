/**
 * The run-state vocabulary — docs/DESIGN_SYSTEM.md §2.5, which is the single
 * statement of it. ARCHITECTURE §5.1 and PRODUCT_SPEC §2.1 both defer here.
 *
 * §2.5.2: "A label is a pure function of (status, kind)... Nothing is stored
 * twice." So this is a function, and the UI never stores a display string.
 */

import type { RunKind, RunStatus, StateRole } from './engine/types';

/** How the status dot renders — §2.5.2 "Dot" column, drawn per §9.6. */
export type DotShape = 'filled' | 'filled-pulse' | 'filled-ring' | 'hollow' | 'none';

export interface RunStateView {
  /** Sentence case, from §2.5.2 and from nowhere else. */
  label: string;
  role: StateRole;
  dot: DotShape;
  /** §2.5.4: a spending row shows a live elapsed timer; a non-spending row
   *  shows no timer at all. This is the carrier, not colour. */
  spending: boolean;
  /** §9.6: Waiting rows sort to the top of their day group. */
  sortsFirst: boolean;
}

/**
 * Derive the row's display state. `archivedAt` is a nullable timestamp and is
 * NOT a status (§2.5.1) — it is a modifier applied on top of the terminal
 * state the row actually reached.
 */
export function runStateView(
  status: RunStatus,
  kind: RunKind,
): RunStateView {
  switch (status) {
    case 'queued':
      return { label: 'Queued', role: 'st-neutral', dot: 'hollow', spending: false, sortsFirst: false };
    case 'preflight':
      /* §10 rule 4: Checking does NOT pulse — preflight is short and a pulse
         that appears for two seconds is noise. */
      return { label: 'Checking', role: 'st-active', dot: 'filled', spending: false, sortsFirst: false };
    case 'running':
      return {
        label: RUNNING_LABELS[kind],
        role: 'st-active',
        dot: 'filled-pulse',
        /* PRODUCT_SPEC §2.1: preflight is not spending, and Diagnosing costs
           nothing. Preparing costs nothing. Train/eval/convert do. */
        spending: kind === 'train' || kind === 'eval' || kind === 'convert',
        sortsFirst: false,
      };
    case 'waiting_input':
      return { label: 'Waiting on you', role: 'st-attention', dot: 'filled-ring', spending: false, sortsFirst: true };
    case 'waiting_approval':
      return { label: 'Waiting for approval', role: 'st-attention', dot: 'filled-ring', spending: false, sortsFirst: true };
    case 'stalled':
      /* §2.5.2: Stalled is spending. PRODUCT_SPEC §2.1: "the process is alive
         and burning your GPU, which is worse" than Failed. */
      return { label: 'Stalled', role: 'st-stalled', dot: 'filled', spending: true, sortsFirst: false };
    case 'done':
      return { label: 'Done', role: 'st-done', dot: 'filled', spending: false, sortsFirst: false };
    case 'failed':
      return { label: 'Failed', role: 'st-failed', dot: 'filled', spending: false, sortsFirst: false };
    case 'cancelled':
      return { label: 'Cancelled', role: 'st-neutral', dot: 'hollow', spending: false, sortsFirst: false };
  }
}

/**
 * The same vocabulary, for a node in a storm.
 *
 * A STORM REPORTS A STATUS AND NOT A KIND. `app/storm.py` folds each step's
 * state out of the event log as one of `build.STEP_STATES` — the nine words
 * §2.5.1 declares — and there is no `runs.kind` on a storm step, because a step
 * is a tool call rather than a run row.
 *
 * Eight of the nine labels do not need one: Queued, Checking, Waiting on you,
 * Waiting for approval, Stalled, Done, Failed and Cancelled are the same words
 * whatever the work is. Only `running` splits five ways in §2.5.2 — Diagnosing,
 * Preparing, Training, Evaluating, Converting — and choosing between those from
 * a tool name would be this file deciding that `measure_baseline` is
 * "Evaluating", which is a guess dressed as a label. So a running node says
 * **Running**, which is the engine's own word for the state it reported.
 *
 * That is a gap in what the storm reports, not a second vocabulary: the day
 * `storm.step.started` carries a kind, this delegates the running case to
 * `runStateView` and the five verbs appear with nothing else to change. The
 * role, the dot and the spending flag are already pure functions of the status
 * and are taken from the one switch above rather than restated here.
 */
export function stepStateView(state: RunStatus): RunStateView {
  const view = runStateView(state, 'diagnose');
  if (state !== 'running') return view;
  return { ...view, label: 'Running' };
}

const RUNNING_LABELS: Record<RunKind, string> = {
  diagnose: 'Diagnosing',
  prepare: 'Preparing',
  train: 'Training',
  eval: 'Evaluating',
  convert: 'Converting',
};

/**
 * The thirteen display labels of §2.5.2, in the document's own order. Used by
 * the rail's state filter, so the filter cannot drift from the labels.
 */
export const ALL_RUN_STATE_LABELS: readonly {
  status: RunStatus;
  kind: RunKind;
}[] = [
  { status: 'queued', kind: 'diagnose' },
  { status: 'preflight', kind: 'diagnose' },
  { status: 'running', kind: 'diagnose' },
  { status: 'running', kind: 'prepare' },
  { status: 'running', kind: 'train' },
  { status: 'running', kind: 'eval' },
  { status: 'running', kind: 'convert' },
  { status: 'waiting_input', kind: 'diagnose' },
  { status: 'waiting_approval', kind: 'train' },
  { status: 'stalled', kind: 'train' },
  { status: 'done', kind: 'train' },
  { status: 'failed', kind: 'train' },
  { status: 'cancelled', kind: 'train' },
] as const;
