import { describe, expect, it } from 'vitest';

import {
  closeInspectorTab,
  focusInspectorTab,
  initialInspector,
  openInspectorTab,
  resolvePaneId,
  wantsHalfWidth,
} from './inspectorTabs';

describe('inspectorTabs', () => {
  it('starts open on Machine', () => {
    expect(initialInspector()).toEqual({
      open: true,
      tabs: ['machine'],
      active: 'machine',
    });
  });

  it('adds a second tab without dropping the first', () => {
    const next = openInspectorTab(initialInspector(), 'plan');
    expect(next.tabs).toEqual(['machine', 'plan']);
    expect(next.active).toBe('plan');
  });

  it('focuses an already-open tab instead of duplicating', () => {
    const withPlan = openInspectorTab(initialInspector(), 'plan');
    const again = openInspectorTab(withPlan, 'machine');
    expect(again.tabs).toEqual(['machine', 'plan']);
    expect(again.active).toBe('machine');
  });

  it('closing the last tab shuts the inspector', () => {
    const shut = closeInspectorTab(initialInspector(), 'machine');
    expect(shut.open).toBe(false);
  });

  it('closing a non-active tab keeps the active one', () => {
    let state = openInspectorTab(initialInspector(), 'files');
    state = openInspectorTab(state, 'plan');
    state = focusInspectorTab(state, 'plan');
    const next = closeInspectorTab(state, 'files');
    expect(next.tabs).toEqual(['machine', 'plan']);
    expect(next.active).toBe('plan');
  });

  it('redirects data to stage (Data∪Stage)', () => {
    expect(resolvePaneId('data')).toBe('stage');
    const next = openInspectorTab(initialInspector(), 'data');
    expect(next.active).toBe('stage');
    expect(next.tabs).toContain('stage');
  });

  it('work panes want half width', () => {
    expect(wantsHalfWidth(openInspectorTab(initialInspector(), 'files'))).toBe(
      true,
    );
    expect(wantsHalfWidth({ open: false, tabs: ['machine'], active: 'machine' })).toBe(
      false,
    );
  });
});
