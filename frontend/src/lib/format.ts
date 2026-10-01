/**
 * Number formatting — docs/DESIGN_SYSTEM.md §3.6, and the provenance mapping
 * of §9.3.
 *
 * Law 3: "Numbers are data. Do not animate, interpolate, round silently, or
 * reflow them." Nothing here rounds a number into meaninglessness, and
 * nothing here produces a number that was not given to it.
 */

import type { DisplayTag, WireProvenance } from './engine/types';

/**
 * Map the engine's provenance vocabulary onto DESIGN_SYSTEM §9.3's four tags.
 *
 * `untested_on_this_platform` is a real value returned by
 * `app/hwdetect.py` and DESIGN_SYSTEM §9.3 HAS NO TAG FOR IT. PRODUCT_SPEC
 * §3.1 does list it ("untested on this platform — this code path has never run
 * on hardware of this kind"). Rendered as `UNTESTED` and marked in the UI as a
 * placeholder awaiting a decision in DESIGN_SYSTEM. Reported as a gap.
 */
export function displayTag(provenance: WireProvenance | undefined): DisplayTag | null {
  switch (provenance) {
    case 'measured':
      return 'MEASURED';
    case 'inferred':
      return 'INFERRED';
    case 'declared':
      return 'DECLARED';
    case 'defaulted':
      return 'DEFAULT';
    case 'untested_on_this_platform':
      return 'UNTESTED';
    default:
      return null;
  }
}

/** §9.3: MEASURED is --fits, INFERRED --info, DECLARED --unknown,
 *  DEFAULT --spills. UNTESTED has no assigned colour; it borrows --unknown
 *  and is marked as a placeholder. */
export const TAG_TOKEN: Record<DisplayTag, string> = {
  MEASURED: 'var(--fits)',
  INFERRED: 'var(--info)',
  DECLARED: 'var(--unknown)',
  DEFAULT: 'var(--spills)',
  UNTESTED: 'var(--unknown)',
};

/**
 * A value plus its unit, per §3.6: "Units always attached, always --ink-3,
 * always one space." The unit is returned separately so the caller can colour
 * it — "the unit is never the same colour as the value."
 *
 * Returns null when the value is null. §3.1 of PRODUCT_SPEC: "A number that
 * cannot be computed is absent, not estimated."
 */
export function withUnit(
  value: number | null | undefined,
  unit: string,
): { value: string; unit: string } | null {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  return { value: significant(value), unit };
}

/**
 * §3.6: "Significant figures, not fixed decimals. `loss 1.8412` while it
 * matters, `loss 0.0031` not `0.00`. Never round a number into
 * meaninglessness to fit a column."
 *
 * The engine already rounds its GB figures to one decimal; this prints what it
 * was given rather than re-rounding it.
 */
export function significant(value: number): string {
  if (Number.isInteger(value)) return String(value);
  const abs = Math.abs(value);
  if (abs >= 100) return value.toFixed(1);
  if (abs >= 1) return String(value);
  /* Small magnitudes keep enough digits to still say something. */
  return value.toPrecision(2).replace(/0+$/, '').replace(/\.$/, '');
}

/**
 * Elapsed time for the cost-legibility rule (§2.5.4): "Spending rows show a
 * live elapsed timer in --ink-2, mono, tabular: `2h 14m elapsed`."
 */
export function elapsed(fromIso: string, nowMs: number = Date.now()): string {
  const started = Date.parse(fromIso);
  if (!Number.isFinite(started)) return '';
  const seconds = Math.max(0, Math.floor((nowMs - started) / 1000));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${m}m elapsed`;
  if (m > 0) return `${m}m ${s}s elapsed`;
  return `${s}s elapsed`;
}

/**
 * §3.6: "Deltas carry a sign and a direction glyph: `1.84 ▾0.31`. Down is not
 * automatically good — for loss it is, for accuracy it is not — so the glyph
 * states direction and the colour states goodness, resolved per metric."
 */
export function deltaGlyph(delta: number): '▾' | '▴' | '·' {
  if (delta < 0) return '▾';
  if (delta > 0) return '▴';
  return '·';
}

/** §9.6: "Colour: the arrow only... --fits if the direction is good for that
 *  metric, --wont if not, --ink-3 if flat. The number stays --ink-2." */
export function deltaColour(delta: number, downIsGood: boolean): string {
  if (delta === 0) return 'var(--ink-3)';
  const good = delta < 0 ? downIsGood : !downIsGood;
  return good ? 'var(--fits)' : 'var(--wont)';
}
