import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  hideGoalBar,
  isGoalBarHidden,
  showGoalBar,
  subscribeGoalBarVisibility,
} from './goalBarVisibility';

afterEach(() => {
  showGoalBar();
  try {
    sessionStorage.clear();
  } catch {
    /* node without storage */
  }
});

describe('goalBarVisibility', () => {
  it('starts visible', () => {
    expect(isGoalBarHidden()).toBe(false);
  });

  it('hide keeps a flag without touching a plan', () => {
    hideGoalBar();
    expect(isGoalBarHidden()).toBe(true);
    showGoalBar();
    expect(isGoalBarHidden()).toBe(false);
  });

  it('notifies subscribers when visibility changes', () => {
    const listen = vi.fn();
    const stop = subscribeGoalBarVisibility(listen);
    hideGoalBar();
    showGoalBar();
    expect(listen).toHaveBeenCalledTimes(2);
    stop();
    hideGoalBar();
    expect(listen).toHaveBeenCalledTimes(2);
  });
});
