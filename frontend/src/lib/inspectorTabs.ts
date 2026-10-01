/**
 * CS11 — Chrome-style inspector tabs helpers.
 *
 * Opening a pane adds or focuses a tab; closing the last tab shuts the
 * inspector. Work subjects widen toward half the viewport (same path Stage
 * already used).
 */

import type { PaneId } from '../components/PaneStack';

/** Panes that open the inspector at ~half width (Cursor-style work panel). */
export const WORK_HALF_PANES: ReadonlySet<PaneId> = new Set([
  'files',
  'stage',
  'plan',
  'context',
  'agents',
  'memory',
  'machine',
]);

export interface InspectorState {
  open: boolean;
  /** Open tabs, left-to-right. */
  tabs: PaneId[];
  /** Focused tab — always a member of `tabs` when open. */
  active: PaneId;
}

/** CS11 — Data merges into Stage; old deep-links still resolve. */
export function resolvePaneId(pane: string): PaneId {
  if (pane === 'data') return 'stage';
  return pane as PaneId;
}

export function initialInspector(): InspectorState {
  return { open: true, tabs: ['machine'], active: 'machine' };
}

export function openInspectorTab(
  state: InspectorState,
  pane: string,
): InspectorState {
  const id = resolvePaneId(pane);
  const tabs = state.tabs.includes(id) ? state.tabs : [...state.tabs, id];
  return { open: true, tabs, active: id };
}

export function closeInspectorTab(
  state: InspectorState,
  pane: PaneId,
): InspectorState {
  const tabs = state.tabs.filter((each) => each !== pane);
  if (tabs.length === 0) {
    return { open: false, tabs: ['machine'], active: 'machine' };
  }
  const active =
    state.active === pane ? tabs[tabs.length - 1]! : state.active;
  return { ...state, tabs, active };
}

export function focusInspectorTab(
  state: InspectorState,
  pane: PaneId,
): InspectorState {
  if (!state.tabs.includes(pane)) return openInspectorTab(state, pane);
  return { ...state, open: true, active: pane };
}

export function wantsHalfWidth(state: InspectorState): boolean {
  return state.open && WORK_HALF_PANES.has(state.active);
}
