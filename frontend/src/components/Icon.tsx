/**
 * THE GRAPHITE ICON SET — transcribed from the sprite in
 * docs/brand/option-a-graphite.html, and extended from docs/brand/graphite.html
 * with five more of the book's own symbols (gear, sliders, cloud, file, trash)
 * when the settings surface needed them. TRANSCRIBED, NOT DRAWN: each path
 * below is character for character what the sprite holds, so "do not invent a
 * token" is satisfied by the fact that nothing here was invented.
 *
 * "Drawn for this product, not borrowed. One stroke weight throughout, round
 * caps and joins, optical alignment on a 24px grid so a 16px render lands on
 * whole pixels."
 *
 * DESIGN_DIRECTIVES §4 is "icons, liberally": rail rows, buttons, chips, tool
 * rows, pane headers, empty states. If a row can carry an icon that helps it be
 * recognised at a glance, it should. No emoji.
 *
 * These are the book's paths, character for character, not redrawings of them.
 * The stroke weight lives in `.i` in base.css — one declaration for the whole
 * product, so it cannot drift per glyph — and every path uses `currentColor`,
 * so an icon takes the colour of the row it sits in and can never introduce a
 * hue of its own. An icon is not a claim about the world.
 *
 * Inline rather than a sprite file or a library: a local-first product that
 * blocks first paint on a CDN is contradicting itself, and React tree-shakes
 * what a page does not render.
 */

import type { CSSProperties } from 'react';

export type IconName =
  | 'thread'
  | 'newthread'
  | 'clock'
  | 'skill'
  | 'folder'
  | 'folderplus'
  | 'filter'
  | 'search'
  | 'plus'
  | 'chevdown'
  | 'chevright'
  | 'check'
  | 'x'
  | 'alert'
  | 'info'
  | 'gpu'
  | 'dataset'
  | 'model'
  | 'run'
  | 'mark'
  | 'play'
  | 'stop'
  | 'terminal'
  | 'chart'
  | 'download'
  | 'sensitive'
  | 'send'
  | 'branch'
  | 'mic'
  | 'panel'
  | 'panelleft'
  | 'pin'
  | 'refresh'
  | 'copy'
  | 'more'
  | 'user'
  | 'key'
  | 'open'
  | 'commit'
  | 'gauge'
  | 'eye'
  | 'book'
  | 'sun'
  | 'moon'
  /* From the graphite.html sprite, added when the settings door was built. */
  | 'gear'
  | 'sliders'
  | 'cloud'
  | 'file'
  | 'trash'
  /* A SUB-AGENT. Max, 2026-09-14: "add icons for sub-agents, not just colours
     and circles - maybe colour icons, like robot icons or something." A dot
     says a thing exists and a colour says what state it is in; neither says
     WHAT it is, and a person opening this product for the first time has no
     reason to read gold as "something else is working on my plan". Drawn in
     this set's grammar - one stroke weight, round joins, 24px grid - rather
     than borrowed: a head with two eyes, an antenna, and shoulders, which is
     the least a robot can be and still read at 12px. */
  | 'robot'
  /* CS15/CS17/CS19 — star for GoalBar and `/goal`. */
  | 'goal'
  | 'star';

/** The single stroke weight. Named once so it cannot drift per icon. */
const STROKE = 1.5;

const PATHS: Record<IconName, React.ReactNode> = {
  thread: <path d="M4 6.2A2.2 2.2 0 0 1 6.2 4h11.6A2.2 2.2 0 0 1 20 6.2v8.1a2.2 2.2 0 0 1-2.2 2.2H9.3L4.9 20V16.5" />,
  newthread: (
    <>
      <path d="M12.5 4.5H6.6A2.6 2.6 0 0 0 4 7.1v10.3A2.6 2.6 0 0 0 6.6 20h10.3a2.6 2.6 0 0 0 2.6-2.6v-5.9" />
      <path d="M17.9 3.6a2 2 0 0 1 2.8 2.8l-7.4 7.4-3.5.7.7-3.5z" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 7.4v4.9l3.1 1.8" />
    </>
  ),
  skill: (
    <>
      <path d="M12 3.4 20 7.7v8.6L12 20.6 4 16.3V7.7z" />
      <path d="M4 7.7 12 12l8-4.3M12 12v8.6" />
    </>
  ),
  folder: <path d="M4 7.4A2.4 2.4 0 0 1 6.4 5h2.9l2.1 2.4h6.2A2.4 2.4 0 0 1 20 9.8v6.8A2.4 2.4 0 0 1 17.6 19H6.4A2.4 2.4 0 0 1 4 16.6z" />,
  folderplus: (
    <>
      <path d="M4 7.4A2.4 2.4 0 0 1 6.4 5h2.9l2.1 2.4h6.2A2.4 2.4 0 0 1 20 9.8v6.8A2.4 2.4 0 0 1 17.6 19H6.4A2.4 2.4 0 0 1 4 16.6z" />
      <path d="M12 11v4.6M9.7 13.3h4.6" />
    </>
  ),
  filter: <path d="M4.4 6.2h15.2l-5.9 6.9v5.2l-3.4 1.7v-6.9z" />,
  search: (
    <>
      <circle cx="11" cy="11" r="6.1" />
      <path d="M15.4 15.4 20 20" />
    </>
  ),
  plus: <path d="M12 5.2v13.6M5.2 12h13.6" />,
  chevdown: <path d="M6.8 9.6 12 14.8l5.2-5.2" />,
  chevright: <path d="M9.6 6.8 14.8 12l-5.2 5.2" />,
  check: <path d="M5 12.6 9.6 17.2 19 7.2" />,
  x: <path d="M6.6 6.6 17.4 17.4M17.4 6.6 6.6 17.4" />,
  alert: (
    <>
      <path d="M10.7 4.6a1.5 1.5 0 0 1 2.6 0l7.2 12.6a1.5 1.5 0 0 1-1.3 2.3H4.8a1.5 1.5 0 0 1-1.3-2.3z" />
      <path d="M12 9.6v4" />
      <path d="M12 16.4h.01" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 11.2v5" />
      <path d="M12 8.1h.01" />
    </>
  ),
  gpu: (
    <>
      <rect x="6" y="6" width="12" height="12" rx="2.4" />
      <rect x="9.6" y="9.6" width="4.8" height="4.8" rx="1.2" />
      <path d="M9.2 3.2V6M14.8 3.2V6M9.2 18v2.8M14.8 18v2.8M3.2 9.2H6M3.2 14.8H6M18 9.2h2.8M18 14.8h2.8" />
    </>
  ),
  dataset: (
    <>
      <rect x="3.6" y="5" width="16.8" height="14" rx="2.4" />
      <path d="M3.6 10h16.8M3.6 14.4h16.8M9.6 10v9" />
    </>
  ),
  model: (
    <>
      <path d="m12 3.4 8.4 4.2-8.4 4.2-8.4-4.2z" />
      <path d="m3.6 12.4 8.4 4.2 8.4-4.2" />
      <path d="m3.6 16.6 8.4 4.2 8.4-4.2" />
    </>
  ),
  run: <path d="M3.2 12h3.9l2.6-7.2 4.6 14.4 2.6-7.2h3.9" />,
  // THE ONE GLYPH IN THIS SET THAT USES FILL: it is a MARK, not an icon, and
  // the book draws it solid at every size. The paragraph that used to sit here
  // described the Basilica portal - two columns under a lintel - which has not
  // been the mark since the bolt replaced it, let alone since the gauge and
  // now the cleave. A comment describing a drawing the file no longer holds is
  // worse than none.
  mark: (
    // THE CLEAVE, and it replaces the gauge. Max, 2026-09-14: *"cleave, go
    // with the cleave, it's cool and new and creative."* He had kept the
    // gauge the day before, so this is a decision reversed on purpose rather
    // than a drift; the gauge's own generator went with it.
    //
    // ONE STONE, ONE STRAIGHT FAULT, and the top piece slid along it so the
    // two halves no longer line up. The step in the silhouette is the whole
    // mark - which is why the small surfaces get the outlines and nothing
    // else. A seven-facet gradient cannot survive a 14px rail, and
    // `currentColor` is the only way a glyph follows the ink around it.
    //
    // The points are PRINTED BY `scripts/make_icon.py --glyph`, off the same
    // geometry that draws the 1024 master and the favicon, so this cannot
    // drift from the taskbar. Do not nudge them by hand: re-run the script.
    <g strokeLinejoin="round">
      <polygon
        points="6.68,9.36 10.71,0.48 17.34,1.99 18.62,4.14"
        fill="currentColor"
        stroke="none"
      />
      <polygon
        points="5.28,11.21 17.23,5.99 19.73,10.15 18.78,17.47 14.05,23.52 7.11,21.50 4.27,13.43"
        fill="currentColor"
        stroke="none"
      />
    </g>
  ),
  play: <path d="M8.2 5.6a.6.6 0 0 1 .9-.5l9 6.4a.6.6 0 0 1 0 1l-9 6.4a.6.6 0 0 1-.9-.5z" />,
  stop: <rect x="6.6" y="6.6" width="10.8" height="10.8" rx="2.6" />,
  terminal: (
    <>
      <rect x="3.2" y="5" width="17.6" height="14" rx="2.6" />
      <path d="m7.6 9.6 2.8 2.4-2.8 2.4M12.8 14.8h4" />
    </>
  ),
  chart: (
    <>
      <path d="M4 4v15.2a.8.8 0 0 0 .8.8H20" />
      <path d="m7.6 15.4 3.4-4.4 3 2.4 4-5.8" />
    </>
  ),
  download: (
    <>
      <path d="M12 4v10.4" />
      <path d="m8 10.8 4 4 4-4" />
      <path d="M4.6 18.6h14.8" />
    </>
  ),
  sensitive: (
    <>
      <rect x="4.6" y="10.4" width="14.8" height="9.2" rx="2.6" />
      <path d="M8.1 10.4V7.9a3.9 3.9 0 0 1 7.8 0v2.5" />
    </>
  ),
  send: (
    <>
      <path d="M12 19V5.6" />
      <path d="m5.8 11.8 6.2-6.2 6.2 6.2" />
    </>
  ),
  branch: (
    <>
      <circle cx="6.4" cy="5.6" r="2.2" />
      <circle cx="6.4" cy="18.4" r="2.2" />
      <circle cx="17.2" cy="7.8" r="2.2" />
      <path d="M6.4 7.8v8.4" />
      <path d="M17.2 10v1a4 4 0 0 1-4 4H6.4" />
    </>
  ),
  mic: (
    <>
      <rect x="9.2" y="3.2" width="5.6" height="10.6" rx="2.8" />
      <path d="M5.8 11.6a6.2 6.2 0 0 0 12.4 0" />
      <path d="M12 17.8V20.8" />
    </>
  ),
  panel: (
    <>
      <rect x="3.2" y="5" width="17.6" height="14" rx="2.6" />
      <path d="M14.6 5v14" />
    </>
  ),
  panelleft: (
    <>
      <rect x="3.2" y="5" width="17.6" height="14" rx="2.6" />
      <path d="M9.4 5v14" />
    </>
  ),
  pin: (
    <>
      <path d="M9 3.6h6" />
      <path d="M10.4 3.6v6.2L8 13.6h8l-2.4-3.8V3.6" />
      <path d="M12 13.6v6.8" />
    </>
  ),
  refresh: (
    <>
      <path d="M19.6 12a7.6 7.6 0 1 1-2.3-5.4" />
      <path d="M19.9 4.6v4.2h-4.2" />
    </>
  ),
  copy: (
    <>
      <rect x="8.6" y="8.6" width="11.4" height="11.4" rx="2.6" />
      <path d="M15.6 8.6V6.4A2.4 2.4 0 0 0 13.2 4H6.4A2.4 2.4 0 0 0 4 6.4v6.8a2.4 2.4 0 0 0 2.4 2.4h2.2" />
    </>
  ),
  more: (
    <>
      <circle cx="5.6" cy="12" r=".9" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r=".9" fill="currentColor" stroke="none" />
      <circle cx="18.4" cy="12" r=".9" fill="currentColor" stroke="none" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8.6" r="3.8" />
      <path d="M4.8 19.8a7.4 7.4 0 0 1 14.4 0" />
    </>
  ),
  key: (
    <>
      <circle cx="7.8" cy="16.2" r="3.6" />
      <path d="m10.4 13.6 8.6-8.6" />
      <path d="m15.8 8.2 2.2 2.2M18.4 5.6l2.2 2.2" />
    </>
  ),
  open: (
    <>
      <path d="M14.2 4H20v5.8" />
      <path d="M20 4 11.4 12.6" />
      <path d="M17.6 14v4.4A1.6 1.6 0 0 1 16 20H5.6A1.6 1.6 0 0 1 4 18.4V8A1.6 1.6 0 0 1 5.6 6.4H10" />
    </>
  ),
  commit: (
    <>
      <circle cx="12" cy="12" r="3.4" />
      <path d="M2.8 12h5.8M15.4 12h5.8" />
    </>
  ),
  gauge: (
    <>
      <path d="M4.2 17.6a8.6 8.6 0 1 1 15.6 0" />
      <path d="m12 13.4 3.6-3.6" />
    </>
  ),
  eye: (
    <>
      <path d="M2.6 12S6.2 5.8 12 5.8 21.4 12 21.4 12 17.8 18.2 12 18.2 2.6 12 2.6 12Z" />
      <circle cx="12" cy="12" r="2.8" />
    </>
  ),
  /* AN OPEN BOOK, REDRAWN 2026-09-12 - the first cut's right page was a
     translated fragment of the left and rendered as a broken hook ("the icon
     is buggy and it looks bad. Redo the icon from scratch."). Two mirrored
     pages meeting at a spine, a line on each: the same grammar as the other
     glyphs, no transforms. */
  book: (
    <>
      <path d="M12 6.5C10.6 5.4 8.8 5 6.5 5H4v13h2.5c2.3 0 4.1.4 5.5 1.5" />
      <path d="M12 6.5C13.4 5.4 15.2 5 17.5 5H20v13h-2.5c-2.3 0-4.1.4-5.5 1.5" />
      <path d="M12 6.5v13" />
      <path d="M7 9.5h2.5M7 12.5h2.5M14.5 9.5H17M14.5 12.5H17" />
    </>
  ),
  sun: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2.6v2.2M12 19.2v2.2M4.4 4.4l1.6 1.6M18 18l1.6 1.6M2.6 12h2.2M19.2 12h2.2M4.4 19.6 6 18M18 6l1.6-1.6" />
    </>
  ),
  moon: <path d="M20 13.6A8.4 8.4 0 0 1 10.4 4a8.4 8.4 0 1 0 9.6 9.6Z" />,
  gear: (
    <>
      <circle cx="12" cy="12" r="2.9" />
      <circle cx="12" cy="12" r="7.2" />
      <path d="M12 3.4v1.5M12 19.1v1.5M20.6 12h-1.5M4.9 12H3.4M18.08 5.92l-1.06 1.06M6.98 17.02l-1.06 1.06M18.08 18.08l-1.06-1.06M6.98 6.98 5.92 5.92" />
    </>
  ),
  sliders: (
    <>
      <path d="M4 7.4h7.6M17.2 7.4H20M4 16.6h2.8M12.4 16.6H20" />
      <circle cx="14.4" cy="7.4" r="2.4" />
      <circle cx="9.6" cy="16.6" r="2.4" />
    </>
  ),
  cloud: (
    <path d="M7.6 18.4h9.2a3.8 3.8 0 0 0 .5-7.57 5.4 5.4 0 0 0-10.36-1.1A4.2 4.2 0 0 0 7.6 18.4Z" />
  ),
  file: (
    <>
      <path d="M13.6 3.6H7.6A2.4 2.4 0 0 0 5.2 6v12a2.4 2.4 0 0 0 2.4 2.4h8.8a2.4 2.4 0 0 0 2.4-2.4V8.4z" />
      <path d="M13.6 3.6v4.8h5.2" />
    </>
  ),
  robot: (
    <>
      <rect x="4.2" y="8.4" width="15.6" height="10.4" rx="2.6" />
      <path d="M12 4.2v4.2" />
      <circle cx="12" cy="3.4" r="1.2" />
      <path d="M8.9 12.4v1.8M15.1 12.4v1.8" />
      <path d="M2.6 12.6v2.6M21.4 12.6v2.6" />
    </>
  ),
  /* CS19 — star for goal / plan / todo (replaces the target in the GoalBar). */
  star: (
    <path d="M12 3.2l2.1 5.4 5.7.4-4.4 3.7 1.4 5.5L12 15.6 6.2 18.2l1.4-5.5L3.2 9l5.7-.4z" />
  ),
  /* A TARGET AGAIN, drawn for the size it is used at. Transcribed from
     Sequence's graphite book, where it was re-cut after "the goal icon still
     looks horrible - it renders very small and rough on the gold little
     toolbar": the ring is r 6.5 so its diameter lands on whole pixels at 12
     and 14; the ticks START ON the ring edge (5.5) instead of floating 0.8
     units off it, so the crosshair is one connected object; and the centre is
     a FILLED dot, because mass is the only thing that survives a downscale.
     A star is a favourite. A target is a goal. `star` keeps the star. */
  goal: (
    <>
      <circle cx="12" cy="12" r="6.5" />
      <circle cx="12" cy="12" r="2" fill="currentColor" stroke="none" />
      <path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3" />
    </>
  ),
  trash: (
    <>
      <path d="M4.8 6.6h14.4" />
      <path d="M9.6 6.6V5.2A1.6 1.6 0 0 1 11.2 3.6h1.6A1.6 1.6 0 0 1 14.4 5.2v1.4" />
      <path d="M6.8 6.6v11.6A2.2 2.2 0 0 0 9 20.4h6a2.2 2.2 0 0 0 2.2-2.2V6.6" />
      <path d="M10.4 10.4v6M13.6 10.4v6" />
    </>
  ),
};

export function Icon({
  name,
  size = 14,
  rotate = 0,
  style,
}: {
  name: IconName;
  size?: number;
  /** Degrees. The chevron is one glyph pointed four ways rather than four
   *  glyphs that can disagree about weight. */
  rotate?: number;
  style?: CSSProperties;
}) {
  return (
    <svg
      className="i"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={STROKE}
      strokeLinecap="round"
      strokeLinejoin="round"
      shapeRendering="geometricPrecision"
      aria-hidden="true"
      focusable="false"
      style={rotate ? { ...style, transform: `rotate(${rotate}deg)` } : style}
    >
      {PATHS[name]}
    </svg>
  );
}

/**
 * Which glyph belongs to a tool group. The groups are the registry's own
 * (`Look · Context · Data · Decide · Choose · Train`); an unknown group gets a
 * generic glyph rather than a guess that implies a meaning.
 *
 * Every one of these is a Graphite symbol drawn for exactly this job — the set
 * is not short of vocabulary here, so nothing new was drawn.
 */
export function groupIcon(group: string): IconName {
  switch (group) {
    case 'Look':
      return 'eye';
    case 'Context':
      return 'folder';
    case 'Data':
      return 'dataset';
    case 'Decide':
      return 'gauge';
    case 'Choose':
      return 'model';
    case 'Train':
      return 'play';
    default:
      return 'skill';
  }
}
