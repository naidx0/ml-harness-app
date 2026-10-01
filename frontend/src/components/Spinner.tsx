/**
 * THE TWO SMALL ROUND THINGS IN THE RAIL, DRAWN AS VECTORS.
 *
 * Max, 2026-09-13: *"On the side rail some of the stuff looks low resolution
 * sometimes. I like the loading blue spinner and I like the blue context
 * wheel, it looks awesome, but it looks very low res. See if we should SVG
 * that."*
 *
 * He is describing two real artefacts, and both were CSS tricks rather than
 * drawings:
 *
 * THE SPINNER STAYED ASCII, and the first cut of this file got that wrong.
 * The rail's braille orbit was replaced with a drawn arc on 2026-09-13
 * because at 12px in a mono cell the glyph's 2x4 dot grid is whatever the
 * font's hinter snaps it to - chunky, uneven between glyphs, different again
 * at 125% Windows scaling. All true, and beside the point: Max, 2026-09-14,
 * *"for loading and working keep our thinking and reasoning spinner in ascii
 * as well."* The orbit is this product's word for "working" and the
 * transcript spins it while a turn runs; a rail that spun a DIFFERENT thing
 * for the same fact would be two answers to one question. The glyph is back,
 * at the transcript's own size and with precise rendering - which is what the
 * low-res complaint actually needed.
 *
 * THE CONTEXT WHEEL was `conic-gradient(...)` on an 11px circle. A conic
 * gradient's hard colour stop is a hard EDGE, and browsers do not antialias
 * that edge the way they antialias a path - at 11px the boundary between spent
 * and free is a visible staircase two pixels tall. An SVG arc is a stroked
 * path: antialiased by the same rasteriser that draws the text around it, and
 * sharp at any device pixel ratio.
 *
 * Both take a `size` and scale by it, so a caller asking for 11 or 24 gets the
 * same drawing rather than the same drawing plus artefacts.
 */

/** THE DIAL. These numbers were the gauge's, back when the gauge was the
 *  application mark: a 140-degree arc of radius 7.92 on a 24 grid, centred at
 *  the needle's hub rather than level with the arc's ends, which is why `cy`
 *  sits below them. They are kept as a proportion that reads, not as a claim
 *  about identity - see `ContextRing`. The gauge itself is saved at
 *  Documents/AI Workspace/app-icons/mlh-cleave/shipped-icon.svg, beside the
 *  mark that replaced it.
 */
const DIAL = { cx: 12, cy: 14.881, r: 7.92, stroke: 2.6, from: 200, sweep: 140 };

/** The dial's ink, so a tight viewBox can be cut around it: a 140-degree arc
 *  is wide and short, and a square box would sit it in a pool of nothing. */
const INK = { x: 3.26, y: 5.36, w: 17.48, h: 11.12 };

function onTheDial(degrees: number): [number, number] {
  const turn = (degrees * Math.PI) / 180;
  return [DIAL.cx + DIAL.r * Math.cos(turn), DIAL.cy + DIAL.r * Math.sin(turn)];
}

/** The path for `share` of the dial, 0 to 1. */
export function dialPath(share: number): string {
  const filled = Math.max(0, Math.min(1, Number.isFinite(share) ? share : 0));
  const [x0, y0] = onTheDial(DIAL.from);
  const [x1, y1] = onTheDial(DIAL.from + DIAL.sweep * filled);
  return `M${x0.toFixed(2)} ${y0.toFixed(2)} A ${DIAL.r} ${DIAL.r} 0 0 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
}

/** The share of the model's window one thread's last prompt took, drawn as a
 *  dial.
 *
 *  IT WAS THE APPLICATION MARK FOR ABOUT AN HOUR. It replaced a donut on
 *  2026-09-14 with the argument that a gauge reading should be drawn as the
 *  gauge the product puts on its own taskbar - and then the taskbar became the
 *  cleave, which is a stone with no dial in it. So the identity argument is
 *  gone and the geometry is kept, because it was MEASURED to read and the
 *  cleave changes nothing about that: at 60px across six fills the difference
 *  between a tenth and a whole is plain, once the track is a different hue
 *  from the reading rather than the same one faded.
 *
 *  `size` is the drawing's WIDTH; a 140-degree arc is wide and short, so the
 *  height follows from that aspect rather than from a square.
 */
export function ContextRing({
  share,
  size = 14,
  title,
}: {
  /** 0 to 1. Anything outside is clamped, never wrapped. */
  share: number;
  size?: number;
  title?: string;
}) {
  const filled = Math.max(0, Math.min(1, Number.isFinite(share) ? share : 0));
  return (
    <svg
      className="ctxring"
      width={size}
      height={Math.round((size * INK.h) / INK.w)}
      viewBox={`${INK.x} ${INK.y} ${INK.w} ${INK.h}`}
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
    >
      {title ? <title>{title}</title> : null}
      {/* THE MASTER'S OWN TRACK COLOUR, NOT THE ACCENT AT LOW OPACITY, and
          the difference is the whole readability of the thing. The first
          version drew the track as `currentColor` at 0.22 - which in the rail
          is the accent, so it was pale blue under solid blue, and MEASURED at
          60px across six fills, 10% and 100% were indistinguishable. #3F3E38
          is the warm grey the gauge used for exactly this reason - a different
          HUE from the reading rather than the same one faded - and against it
          every fill from a tenth to full is separable. */}
      <path
        className="ctxring__track"
        d={dialPath(1)}
        fill="none"
        stroke="#3F3E38"
        strokeWidth={DIAL.stroke}
        strokeLinecap="round"
      />
      {filled > 0 ? (
        <path
          className="ctxring__arc"
          d={dialPath(filled)}
          fill="none"
          stroke="currentColor"
          strokeWidth={DIAL.stroke}
          strokeLinecap="round"
        />
      ) : null}
    </svg>
  );
}
