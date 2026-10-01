/**
 * SNAP FRAMES FOR THE SIDE PANES.
 *
 * Max, on the section cards: "create snap frames at 25%, 33%, 50% so that when
 * we have the different sections open side by side they snap into frame
 * instead of working independently... it all condenses, some of the text
 * starts stacking and overlapping."
 *
 * The overlap half of that is CSS (container queries on the cards). This file
 * is the other half: the arithmetic that turns a raw dragged pixel width into
 * one of three frames, kept out of `App.tsx` so it can be tested without a
 * pointer, a viewport, or React.
 *
 * ── WHAT THE FRACTIONS ARE OF ─────────────────────────────────────────────
 *
 * The workspace, not the window. The rail is a column the person also resizes,
 * so `0.5` has to mean "half of what is left beside the rail" or the pane and
 * the chat stop being halves of anything the moment the rail moves.
 * `span = viewport - rail`, and every target is a fraction of that.
 *
 * ── WHY HYSTERESIS, AND WHY IT IS TWO BANDS ───────────────────────────────
 *
 * A single band is a trap: at exactly `band` from a target the pointer sits on
 * the boundary, and one pixel of hand-shake flips the pane between snapped and
 * free several times a second. So entering and leaving are different numbers -
 * `band` (24px) to be caught by a frame, `band * 2` (48px) to get back out of
 * one. Once held, the width does not move at all inside that dead zone, which
 * is the point of a frame: the pane stays where the frame is while the hand
 * wanders.
 *
 * The caller owns the held value (`snapWidth` is pure and stateless); it passes
 * back whatever `snap` it got last time, and `null` at the start of a drag.
 */

/** The three frames, as fractions of the workspace. */
export const PANE_SNAPS: readonly number[] = [0.25, 1 / 3, 0.5];

/** How close the drag must come before a frame catches it. */
export const SNAP_BAND = 24;

export interface SnapResult {
  /** The width to apply. Equal to `raw` when nothing caught it. */
  width: number;
  /** The frame it landed in, or `null` when it is free. */
  snap: number | null;
}

/**
 * The three frames in pixels, ascending, for a given viewport and rail.
 *
 * Rounded, because a fractional CSS pixel width and an integer one are two
 * different numbers in `localStorage`, and the one-shot widen has to agree with
 * the drag about what "50%" is.
 */
export function snapTargets(
  viewport: number,
  rail: number,
  snaps: readonly number[] = PANE_SNAPS,
): number[] {
  const span = Math.max(0, viewport - rail);
  const targets = snaps.map((fraction) => Math.round(fraction * span));
  return [...new Set(targets)].sort((a, b) => a - b);
}

/** One frame in pixels — the same arithmetic, for callers that want just one. */
export function snapTarget(viewport: number, rail: number, fraction: number): number {
  return Math.round(fraction * Math.max(0, viewport - rail));
}

/**
 * Quantise a dragged width to the nearest frame within `band`, else leave it
 * alone.
 *
 * @param raw      the width the pointer is asking for, already clamped by the
 *                 caller to whatever min/max that grabber allows
 * @param viewport window width
 * @param rail     the rail's current width
 * @param snaps    fractions of `viewport - rail`
 * @param band     how close to catch (and, doubled, how far to release)
 * @param held     the frame this drag is currently held by, or `null`
 */
export function snapWidth(
  raw: number,
  viewport: number,
  rail: number,
  snaps: readonly number[] = PANE_SNAPS,
  band: number = SNAP_BAND,
  held: number | null = null,
): SnapResult {
  const targets = snapTargets(viewport, rail, snaps);
  if (targets.length === 0 || band <= 0) return { width: raw, snap: null };

  /* Already in a frame: stay in it until the drag is a full band PAST the band
     it was caught by. See the note above on why this is not one number. */
  if (held !== null && targets.includes(held) && Math.abs(raw - held) <= band * 2) {
    return { width: held, snap: held };
  }

  let nearest = targets[0];
  for (const target of targets) {
    if (Math.abs(raw - target) < Math.abs(raw - nearest)) nearest = target;
  }
  if (Math.abs(raw - nearest) <= band) return { width: nearest, snap: nearest };
  return { width: raw, snap: null };
}

/**
 * The next frame along from where the pane is now — what Left and Right do
 * when the grabber has focus.
 *
 * It cycles rather than stopping at the ends: three frames and two keys, and a
 * key that does nothing at one end is a key the person presses twice before
 * they believe it.
 *
 * `direction` is in WIDTH, not in screen direction; the caller turns an arrow
 * key into a widen or a narrow using the grabber's own sign (the rail widens
 * to the right, the inspector narrows to the right).
 */
export function cycleSnap(
  current: number,
  targets: readonly number[],
  direction: 1 | -1,
): number {
  const sorted = [...targets].sort((a, b) => a - b);
  if (sorted.length === 0) return current;
  /* A pixel of tolerance: a width read back out of localStorage can be a hair
     off the frame it was stored from, and "next" must not mean "this one". */
  const EPS = 1;
  if (direction > 0) {
    return sorted.find((target) => target > current + EPS) ?? sorted[0];
  }
  return (
    [...sorted].reverse().find((target) => target < current - EPS) ??
    sorted[sorted.length - 1]
  );
}
