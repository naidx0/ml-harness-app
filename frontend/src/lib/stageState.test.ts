import { describe, expect, it } from 'vitest';

import { initialStage, stageReducer, stageShows } from './stageState';

describe('the Stage is one thing in three sizes', () => {
  it('the selection is one value shared by every size', () => {
    let state = stageReducer(initialStage(), { type: 'pick', runId: 45 });
    state = stageReducer(state, { type: 'open', size: 'window' });
    state = stageReducer(state, { type: 'open', size: 'row', anchor: 'tool-12' });
    state = stageReducer(state, { type: 'open', size: 'split' });
    expect(state.runId).toBe(45);
    expect(stageShows(state, 'window')).toBe(true);
    expect(stageShows(state, 'row')).toBe(true);
    expect(stageShows(state, 'split')).toBe(true);
  });

  it('a size change never changes the selection or the panel', () => {
    let state = stageReducer(initialStage(), { type: 'pick', runId: 47 });
    state = stageReducer(state, { type: 'panel', panel: 'progression' });
    state = stageReducer(state, { type: 'open', size: 'window' });
    state = stageReducer(state, { type: 'close', size: 'window' });
    state = stageReducer(state, { type: 'open', size: 'row', anchor: 'tool-3' });
    state = stageReducer(state, { type: 'close', size: 'row' });
    expect(state.runId).toBe(47);
    expect(state.panel).toBe('progression');
  });

  it('the inline row is open at exactly one anchor, or none', () => {
    let state = stageReducer(initialStage(), { type: 'open', size: 'row', anchor: 'a' });
    expect(state.anchor).toBe('a');
    state = stageReducer(state, { type: 'open', size: 'row', anchor: 'b' });
    expect(state.anchor).toBe('b');
    state = stageReducer(state, { type: 'close', size: 'row' });
    expect(state.anchor).toBeNull();
    expect(stageShows(state, 'row')).toBe(false);
  });

  it('closing the window leaves the row and the split where they were', () => {
    let state = stageReducer(initialStage(), { type: 'open', size: 'split' });
    state = stageReducer(state, { type: 'open', size: 'window' });
    state = stageReducer(state, { type: 'close', size: 'window' });
    expect(stageShows(state, 'split')).toBe(true);
    expect(stageShows(state, 'window')).toBe(false);
  });
});
