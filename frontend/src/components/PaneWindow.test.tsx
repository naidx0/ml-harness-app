/**
 * Which panes can be a window: every one the inspector has.
 *
 * Max, 2026-09-12: *"this means everything should be able to come into a pop
 * out. Literally every single thing."* The list is the inspector's own
 * `PANE_ORDER`, so a pane added to the inspector is a pane that pops out, and
 * a name that is not a pane is refused rather than opening an empty frame -
 * the same refusal `open_pane` in src-tauri/src/lib.rs makes for junk.
 */

import { describe, expect, it } from 'vitest';

import { PANE_ORDER, PANE_TITLE } from './PaneStack';
import { PANES_THAT_POP_OUT, canPopOut } from './PaneWindow';

describe('which panes can be a window', () => {
  it('every pane the inspector has, in its order', () => {
    expect([...PANES_THAT_POP_OUT]).toEqual([...PANE_ORDER]);
  });

  it('every pane on the list is a real pane with a title', () => {
    for (const pane of PANES_THAT_POP_OUT) {
      expect(canPopOut(pane)).toBe(true);
      expect(typeof PANE_TITLE[pane]).toBe('string');
    }
  });

  it('the stage and the plan are on it - the two he named first', () => {
    expect(canPopOut('stage')).toBe(true);
    expect(canPopOut('plan')).toBe(true);
    expect(canPopOut('journey')).toBe(true);
  });

  it('says no to junk, which is what the Rust side also refuses', () => {
    for (const junk of ['', 'bogus', 'plan; rm -rf', '../plan', 'PLAN']) {
      expect(canPopOut(junk)).toBe(false);
    }
  });
});
