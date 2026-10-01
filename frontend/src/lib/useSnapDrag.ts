import { useCallback, useMemo, useRef, useState } from 'react';
import type React from 'react';

import { PANE_SNAPS, SNAP_BAND, cycleSnap, snapTargets, snapWidth } from './snapWidth';

/**
 * THE PANE GRABBER, WITH FRAMES.
 *
 * `useDrag` in `App.tsx` is the free version and the rail still uses it - a
 * rail is a list of folders and there is nothing for it to line up with. The
 * panes are different: Max, of the section cards, "create snap frames at 25%,
 * 33%, 50% so that when we have the different sections open side by side they
 * snap into frame instead of working independently".
 *
 * IT LIVES IN `lib/` RATHER THAN BESIDE `useDrag` so that it can be tested.
 * Every other hook in this product is here for the same reason; importing
 * `App.tsx` to reach one would pull the whole shell into a unit test.
 *
 * Three things this adds and the free drag has not:
 *
 *  - the width quantises to `lib/snapWidth.ts`'s frames, with hysteresis, so a
 *    frame holds a wandering hand instead of flickering at its edge;
 *  - `snapped` says which frame has it, for the guide the grabber draws. It is
 *    reported only when the frame survives the clamp - a frame the clamp moved
 *    is not a frame the pane is in, and a guide that says otherwise is worse
 *    than no guide;
 *  - Left and Right step through the frames when the grabber has focus, which
 *    is the only way to reach them without a pointer.
 */
export function useSnapDrag(
  current: number,
  set: (next: number) => void,
  min: number,
  max: number,
  /* +1 when dragging right widens (the rail), -1 when it narrows (the stack) */
  sign: 1 | -1,
  viewport: number,
  rail: number,
  /* THE STOPS THIS GRABBER MAY OFFER, and a grabber whose floor is above a
     stop must not offer it. Measured 2026-09-19: the Stage grabber's floor is
     480, so at any window under 1720 the 25% and 33% frames were offered,
     clamped to 480, and reported `snapped: null` - an arrow key that appeared
     to do nothing and a drag that stopped following the pointer with no guide
     and no reason. A stop that cannot be reached is not a frame. */
  snaps: readonly number[] = PANE_SNAPS,
): { onPointerDown: (event: React.PointerEvent) => void;
     onKeyDown: (event: React.KeyboardEvent) => void;
     snapped: number | null } {
  /* Only the fractions whose pixel target this grabber can actually hold.
     Computed from the same `min`/`max` the drag clamps with, so the two can
     never disagree. */
  const reachable = useMemo(() => {
    const kept = snaps.filter((fraction) => {
      const target = Math.round(fraction * Math.max(0, viewport - rail));
      return target >= min && target <= max;
    });
    /* Never empty: a grabber with no reachable frame drags free, which is the
       honest behaviour, and `snapWidth` returns `raw` for an empty list. */
    return kept;
  }, [snaps, viewport, rail, min, max]);

  const start = useRef({ x: 0, width: 0 });
  /* The held frame is a ref, not state: it is read inside a pointermove
     listener that was closed over once, and a re-render must not restart the
     hysteresis half way through a drag. */
  const held = useRef<number | null>(null);
  const [snapped, setSnapped] = useState<number | null>(null);

  const onPointerDown = useCallback(
    (event: React.PointerEvent) => {
      event.preventDefault();
      start.current = { x: event.clientX, width: current };
      held.current = null;
      const move = (moveEvent: PointerEvent) => {
        const delta = (moveEvent.clientX - start.current.x) * sign;
        const raw = Math.min(max, Math.max(min, start.current.width + delta));
        const result = snapWidth(raw, viewport, rail, reachable, SNAP_BAND, held.current);
        const width = Math.min(max, Math.max(min, result.width));
        held.current = result.snap;
        setSnapped(result.snap !== null && width === result.snap ? result.snap : null);
        set(width);
      };
      const up = () => {
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', up);
        /* The guide belongs to the drag. The width stays where the frame put
           it; the line does not stay on screen after the hand lets go. */
        setSnapped(null);
        held.current = null;
      };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
    },
    [current, set, min, max, sign, viewport, rail, reachable],
  );

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      event.preventDefault();
      /* The arrow is a SCREEN direction; `sign` turns it into a width one, so
         Right on the inspector's grabber narrows the inspector exactly as
         dragging it right does. */
      const towards: 1 | -1 = event.key === 'ArrowRight' ? sign : ((-sign) as 1 | -1);
      const next = cycleSnap(current, snapTargets(viewport, rail, reachable), towards);
      set(Math.min(max, Math.max(min, next)));
    },
    [current, set, min, max, sign, viewport, rail, reachable],
  );

  return { onPointerDown, onKeyDown, snapped };
}
