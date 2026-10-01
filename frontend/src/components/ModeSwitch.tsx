/**
 * ONE CHIP: Plan · Build · Full.
 *
 * Max, 2026-09-15 (A+C hybrid): permission is not a second dropdown. Autonomy
 * is built into the working mode —
 *
 *   Plan  — read-only consultation (mode=plan, permission=ask)
 *   Build — execute the plan, still ask on gates (mode=build, permission=ask)
 *   Full  — execute and decide (mode=build, permission=full)
 *
 * Switching to Build / Full with a plan already saved just flips. No "Build
 * it?" confirm. No auto-Run. The person prompts; the mode does not get horny.
 */

import { useState } from 'react';

import {
  setThreadMode,
  setThreadPermission,
  setThreadPlan,
} from '../lib/engine/client';
import type { PermissionMode } from './PermissionLadder';
import { Icon } from './Icon';
import { MenuButton, type MenuRow } from './Menu';

export type WorkingMode = 'plan' | 'build' | 'full';

export function workingModeOf(
  mode: string,
  permission: PermissionMode,
): WorkingMode {
  if (mode !== 'build') return 'plan';
  if (permission === 'full') return 'full';
  return 'build';
}

const LABELS: Record<WorkingMode, string> = {
  plan: 'Plan',
  build: 'Build',
  full: 'Full',
};

const TITLES: Record<WorkingMode, string> = {
  plan:
    'Plan — read-only. Lookups and writing the checklist. It does not measure, train, or grind.',
  build:
    'Build — execute the saved plan. Gated steps still ask. It does not start a run by itself — you prompt or press Run.',
  full:
    'Full — build and decide. Zero ask except delete_sandbox. Gold means risk.',
};

export function ModeSwitch({
  threadId,
  mode,
  permission,
  plan,
  planDraft,
  onChanged,
}: {
  threadId: number;
  mode: string;
  permission: PermissionMode;
  plan: string | null;
  planDraft: string | null;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const current = workingModeOf(mode, permission);
  const hasPlan = Boolean(plan && plan.trim());
  const draftIsAPlan = Boolean(planDraft && /^##\s+/m.test(planDraft));

  async function choose(next: WorkingMode) {
    if (busy || next === current) return;
    setBusy(true);
    try {
      if (next === 'plan') {
        await setThreadMode(threadId, 'plan');
        await setThreadPermission(threadId, 'ask');
      } else {
        /* Save a draft only when there is no plan yet and the draft looks like
           one. Never re-prompt; never start the durable run. */
        if (!hasPlan && draftIsAPlan) {
          await setThreadPlan(threadId, planDraft as string);
        }
        await setThreadMode(threadId, 'build');
        await setThreadPermission(threadId, next === 'full' ? 'full' : 'ask');
      }
      onChanged();
    } catch {
      /* Stay put — a chip that moved without the engine would lie. */
    } finally {
      setBusy(false);
    }
  }

  const rows: MenuRow[] = (['plan', 'build', 'full'] as WorkingMode[]).map(
    (id) => ({
      id,
      label: LABELS[id],
      icon: id === 'plan' ? 'eye' : id === 'build' ? 'play' : 'run',
      current: current === id,
      disabledReason: busy ? 'Switching…' : undefined,
    }),
  );

  return (
    <span className="modeswitch" data-mode={current}>
      <MenuButton
        className="modechip"
        label="Mode"
        title={TITLES[current]}
        rows={rows}
        open={open}
        setOpen={setOpen}
        minWidth={168}
        onChoose={(id) => void choose(id as WorkingMode)}
      >
        <span className="modechip__dot" aria-hidden="true" />
        <span className="modechip__word">{LABELS[current]}</span>
        <Icon name="chevdown" size={11} />
      </MenuButton>
    </span>
  );
}
