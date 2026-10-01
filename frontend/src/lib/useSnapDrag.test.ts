/**
 * THE WIRING, NOT THE ARITHMETIC.
 *
 * `snapWidth.test.ts` proves the frames are where they should be. This file
 * proves the grabber actually reaches them: that a pointer drag runs the raw
 * delta through the snap table, that the clamps still win, that the guide only
 * claims a frame the pane is really in, and that the arrow keys move between
 * the three without a pointer at all.
 *
 * The listeners are on `window`, not on the element, because a drag that
 * leaves the 16px grabber must keep working — so the test dispatches on
 * `window` too, which is the same contract the shell uses.
 */
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { snapTargets } from './snapWidth';
import { useSnapDrag } from './useSnapDrag';

const VIEWPORT = 1680;
const RAIL = 280;
const [QUARTER, THIRD, HALF] = snapTargets(VIEWPORT, RAIL); /* 350, 467, 700 */

/** The inspector's grabber: min 320, max 900, and dragging RIGHT narrows it. */
function stack(width: number, set: (next: number) => void) {
  return renderHook(() => useSnapDrag(width, set, 320, 900, -1, VIEWPORT, RAIL));
}

function press(hook: ReturnType<typeof stack>, clientX: number) {
  act(() => {
    hook.result.current.onPointerDown({
      clientX,
      preventDefault() {},
    } as unknown as React.PointerEvent);
  });
}

function dragTo(clientX: number) {
  act(() => {
    window.dispatchEvent(new PointerEvent('pointermove', { clientX }));
  });
}

function release() {
  act(() => {
    window.dispatchEvent(new PointerEvent('pointerup'));
  });
}

describe('the pane grabber snaps while it is dragged', () => {
  it('lands on the frame when the pointer passes near it', () => {
    const set = vi.fn();
    const hook = stack(500, set);
    press(hook, 1000);
    /* 190px to the LEFT, and this grabber's sign is -1, so the pane widens by
       190 to 690 — eleven pixels short of the half, which is inside the band. */
    dragTo(810);
    expect(set).toHaveBeenLastCalledWith(HALF);
    expect(hook.result.current.snapped).toBe(HALF);
    release();
  });

  it('stays free between the frames and says so', () => {
    const set = vi.fn();
    const hook = stack(500, set);
    press(hook, 1000);
    dragTo(940); /* 500 + 60 = 560, between the third and the half */
    expect(set).toHaveBeenLastCalledWith(560);
    expect(hook.result.current.snapped).toBeNull();
    release();
  });

  it('holds a frame across a wobble, then lets go', () => {
    const set = vi.fn();
    const hook = stack(500, set);
    press(hook, 1000);
    dragTo(810); /* caught by the half at 700 */
    expect(set).toHaveBeenLastCalledWith(HALF);
    dragTo(780); /* wants 720 — outside the catch band, inside the hold */
    expect(set).toHaveBeenLastCalledWith(HALF);
    dragTo(740); /* wants 760 — past twice the band, so it is free again */
    expect(set).toHaveBeenLastCalledWith(760);
    expect(hook.result.current.snapped).toBeNull();
    release();
  });

  it('the clamp beats the frame, and the guide does not lie about it', () => {
    const set = vi.fn();
    /* A grabber whose ceiling is below the half: the frame is unreachable, so
       the pane stops at 600 and nothing may claim it is in a frame. */
    const hook = renderHook(() => useSnapDrag(500, set, 320, 600, -1, VIEWPORT, RAIL));
    act(() => {
      hook.result.current.onPointerDown({
        clientX: 1000,
        preventDefault() {},
      } as unknown as React.PointerEvent);
    });
    dragTo(800);
    expect(set).toHaveBeenLastCalledWith(600);
    expect(hook.result.current.snapped).toBeNull();
    release();
  });

  it('drops the guide when the hand lets go, and keeps the width', () => {
    const set = vi.fn();
    const hook = stack(500, set);
    press(hook, 1000);
    dragTo(810);
    expect(hook.result.current.snapped).toBe(HALF);
    release();
    expect(hook.result.current.snapped).toBeNull();
    expect(set).toHaveBeenLastCalledWith(HALF);
  });

  it('stops listening after the drag ends', () => {
    const set = vi.fn();
    const hook = stack(500, set);
    press(hook, 1000);
    dragTo(810);
    release();
    set.mockClear();
    dragTo(600);
    expect(set).not.toHaveBeenCalled();
  });
});

describe('the pane grabber snaps from the keyboard', () => {
  function key(hook: ReturnType<typeof stack>, name: string) {
    const preventDefault = vi.fn();
    act(() => {
      hook.result.current.onKeyDown({
        key: name,
        preventDefault,
      } as unknown as React.KeyboardEvent);
    });
    return preventDefault;
  }

  it('Left widens the inspector, because its grabber is on its left edge', () => {
    const set = vi.fn();
    key(stack(QUARTER, set), 'ArrowLeft');
    expect(set).toHaveBeenCalledWith(THIRD);
  });

  it('Right narrows it', () => {
    const set = vi.fn();
    key(stack(HALF, set), 'ArrowRight');
    expect(set).toHaveBeenCalledWith(THIRD);
  });

  it('cycles round rather than dead-ending at the widest', () => {
    const set = vi.fn();
    key(stack(HALF, set), 'ArrowLeft');
    expect(set).toHaveBeenCalledWith(QUARTER);
  });

  it('takes the arrow key, so the page does not also scroll', () => {
    expect(key(stack(THIRD, vi.fn()), 'ArrowLeft')).toHaveBeenCalled();
  });

  it('leaves every other key alone', () => {
    const set = vi.fn();
    const prevented = key(stack(THIRD, set), 'ArrowUp');
    expect(set).not.toHaveBeenCalled();
    expect(prevented).not.toHaveBeenCalled();
  });

  /* IT USED TO CLAMP, AND CLAMPING IS WHAT WAS WRONG. A grabber whose ceiling
     is 600 was still offered the 700px half frame; the arrow key "moved" to it
     and the clamp flattened it to 600, which is not a frame, reported
     `snapped: null`, so the guide did not draw either. From the outside that is
     an arrow key that does nothing. Max, 2026-09-19: the machine pane "only
     getting snapped to at most 40 or 33%". A stop the grabber cannot hold is
     not offered at all, and the cycle moves to one it can. */
  it('does not offer a frame the grabber cannot hold, and moves to one it can', () => {
    const set = vi.fn();
    const hook = renderHook(() => useSnapDrag(THIRD, set, 320, 600, -1, VIEWPORT, RAIL));
    act(() => {
      hook.result.current.onKeyDown({
        key: 'ArrowLeft',
        preventDefault() {},
      } as unknown as React.KeyboardEvent);
    });
    expect(set).toHaveBeenCalledWith(QUARTER);
    expect(set).not.toHaveBeenCalledWith(600);
  });

  it('drags free when its bounds hold no frame at all', () => {
    const set = vi.fn();
    const hook = renderHook(() => useSnapDrag(360, set, 355, 365, -1, VIEWPORT, RAIL));
    act(() => {
      hook.result.current.onKeyDown({
        key: 'ArrowLeft',
        preventDefault() {},
      } as unknown as React.KeyboardEvent);
    });
    expect(set).toHaveBeenCalledWith(360);
  });
});
