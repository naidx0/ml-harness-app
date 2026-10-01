import { describe, expect, it } from 'vitest';

import {
  PANE_SNAPS,
  SNAP_BAND,
  cycleSnap,
  snapTarget,
  snapTargets,
  snapWidth,
} from './snapWidth';

/* One viewport for the whole file so every number below can be recomputed by
   hand: 1680 wide, a 280px rail, so the workspace is 1400 and the three frames
   are 350, 467 and 700. */
const VIEWPORT = 1680;
const RAIL = 280;
const QUARTER = 350;
const THIRD = 467;
const HALF = 700;

describe('snapTargets', () => {
  it('is the three fractions of the workspace, not of the window', () => {
    expect(snapTargets(VIEWPORT, RAIL)).toEqual([QUARTER, THIRD, HALF]);
    /* The same window with a wider rail gives smaller frames: the fractions
       are of what is left beside the rail. */
    expect(snapTargets(VIEWPORT, 400)).toEqual([320, 427, 640]);
  });

  it('never goes negative when the rail is wider than the window', () => {
    expect(snapTargets(300, 500)).toEqual([0]);
  });

  it('agrees with snapTarget, which is what the one-shot widen reads', () => {
    expect(snapTarget(VIEWPORT, RAIL, 0.5)).toBe(HALF);
    expect(snapTargets(VIEWPORT, RAIL)).toContain(snapTarget(VIEWPORT, RAIL, 0.5));
  });
});

describe('snapWidth catches a drag inside the band', () => {
  it('snaps to each of the three fractions', () => {
    for (const target of [QUARTER, THIRD, HALF]) {
      expect(snapWidth(target + 5, VIEWPORT, RAIL).width).toBe(target);
      expect(snapWidth(target - 5, VIEWPORT, RAIL).width).toBe(target);
    }
  });

  it('reports which frame caught it, so the grabber can show the snap', () => {
    expect(snapWidth(HALF - 3, VIEWPORT, RAIL).snap).toBe(HALF);
    expect(snapWidth(QUARTER + 1, VIEWPORT, RAIL).snap).toBe(QUARTER);
  });

  it('catches exactly at the edge of the band', () => {
    expect(snapWidth(HALF + SNAP_BAND, VIEWPORT, RAIL).width).toBe(HALF);
    expect(snapWidth(HALF - SNAP_BAND, VIEWPORT, RAIL).width).toBe(HALF);
  });

  it('takes the nearest frame when two are close together', () => {
    /* 350 and 467 are 117 apart, so the line between them is 408.5. With a
       wide enough band both are in reach and only the distance decides. */
    expect(snapWidth(410, VIEWPORT, RAIL, PANE_SNAPS, 80).width).toBe(THIRD);
    expect(snapWidth(405, VIEWPORT, RAIL, PANE_SNAPS, 80).width).toBe(QUARTER);
  });
});

describe('snapWidth leaves a drag alone outside the band', () => {
  it('is free between the frames', () => {
    const raw = 560; /* 93 from the third, 140 from the half */
    const result = snapWidth(raw, VIEWPORT, RAIL);
    expect(result.width).toBe(raw);
    expect(result.snap).toBeNull();
  });

  it('is free one pixel past the band', () => {
    expect(snapWidth(HALF + SNAP_BAND + 1, VIEWPORT, RAIL).snap).toBeNull();
    expect(snapWidth(HALF + SNAP_BAND + 1, VIEWPORT, RAIL).width).toBe(
      HALF + SNAP_BAND + 1,
    );
  });

  it('snaps nothing when the band is zero', () => {
    expect(snapWidth(HALF, VIEWPORT, RAIL, PANE_SNAPS, 0).snap).toBeNull();
  });

  it('snaps nothing when there are no frames', () => {
    const result = snapWidth(HALF, VIEWPORT, RAIL, []);
    expect(result).toEqual({ width: HALF, snap: null });
  });
});

describe('snapWidth hysteresis', () => {
  it('holds the frame past the band it was caught by', () => {
    /* 30px out is beyond the 24px catch band, so a fresh drag would be free -
       but a drag already held by the half stays pinned to it. */
    expect(snapWidth(HALF + 30, VIEWPORT, RAIL).snap).toBeNull();
    const held = snapWidth(HALF + 30, VIEWPORT, RAIL, PANE_SNAPS, SNAP_BAND, HALF);
    expect(held.width).toBe(HALF);
    expect(held.snap).toBe(HALF);
  });

  it('lets go one pixel past twice the band', () => {
    const still = snapWidth(
      HALF + SNAP_BAND * 2, VIEWPORT, RAIL, PANE_SNAPS, SNAP_BAND, HALF,
    );
    expect(still.snap).toBe(HALF);

    const free = snapWidth(
      HALF + SNAP_BAND * 2 + 1, VIEWPORT, RAIL, PANE_SNAPS, SNAP_BAND, HALF,
    );
    expect(free.snap).toBeNull();
    expect(free.width).toBe(HALF + SNAP_BAND * 2 + 1);
  });

  it('is symmetric — the same hold on the narrowing side', () => {
    const held = snapWidth(HALF - 40, VIEWPORT, RAIL, PANE_SNAPS, SNAP_BAND, HALF);
    expect(held.width).toBe(HALF);
  });

  it('ignores a held value that is not one of this viewport frames', () => {
    /* The window was resized mid-drag: yesterday's frame is not a frame now,
       and holding onto it would pin the pane to a number nothing else knows. */
    const result = snapWidth(900, VIEWPORT, RAIL, PANE_SNAPS, SNAP_BAND, 912);
    expect(result.snap).toBeNull();
    expect(result.width).toBe(900);
  });

  it('hands the next frame over when the drag reaches one', () => {
    const result = snapWidth(THIRD, VIEWPORT, RAIL, PANE_SNAPS, SNAP_BAND, HALF);
    expect(result.snap).toBe(THIRD);
  });
});

describe('cycleSnap', () => {
  const targets = [QUARTER, THIRD, HALF];

  it('steps up and down through the three frames', () => {
    expect(cycleSnap(QUARTER, targets, +1)).toBe(THIRD);
    expect(cycleSnap(THIRD, targets, +1)).toBe(HALF);
    expect(cycleSnap(HALF, targets, -1)).toBe(THIRD);
    expect(cycleSnap(THIRD, targets, -1)).toBe(QUARTER);
  });

  it('wraps rather than dead-ending', () => {
    expect(cycleSnap(HALF, targets, +1)).toBe(QUARTER);
    expect(cycleSnap(QUARTER, targets, -1)).toBe(HALF);
  });

  it('starts from a free width at the next frame in that direction', () => {
    expect(cycleSnap(560, targets, +1)).toBe(HALF);
    expect(cycleSnap(560, targets, -1)).toBe(THIRD);
  });

  it('returns the width unchanged when there are no frames', () => {
    expect(cycleSnap(560, [], +1)).toBe(560);
  });
});
