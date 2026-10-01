/**
 * The small components everything else is built from, drawn to Graphite.
 *
 * Each one carries the rule that shapes it. The rule they all share: every hue
 * on screen is a claim about the world, and there are never more hues than
 * there are claims. Nothing here is coloured because it looked nice.
 */

import type { CSSProperties, ReactNode } from 'react';
import type { DisplayTag, GateStatus, StateRole, Verdict } from '../lib/engine/types';
import type { FactOrigin } from '../lib/engine/facts';
import { ORIGIN_MEANS, ORIGIN_TAG, ORIGIN_WORD } from '../lib/engine/facts';
import type { DotShape } from '../lib/runState';
import { TAG_TOKEN } from '../lib/format';
import { Icon, type IconName } from './Icon';

/* ── Status dot ───────────────────────────────────────────────────────────
   6px. Status colour appears on the dot and the state word — never a row
   background, never a row border. */

export function StatusDot({ role, shape }: { role: StateRole; shape: DotShape }) {
  if (shape === 'none') return null;
  return (
    <span
      className="dot"
      data-shape={shape}
      style={{ '--st-colour': `var(--${role})` } as CSSProperties}
      aria-hidden="true"
    />
  );
}

/* ── Verdict badge ────────────────────────────────────────────────────────
   "The word is the badge. It is never an icon, never a bare dot, never a
   colour swatch."

   Verdict badges are the one place this design uses capitals. Everything else
   in the product is sentence case. A verdict is a terminal claim, it appears
   at most a few times per screen, and caps at 10px with +0.08em tracking and
   weight 700 is what makes it read as a stamp rather than a label. */

const VERDICT_WORD: Record<Verdict, string> = {
  FITS: 'FITS',
  SPILLS: 'SPILLS',
  /* "WON'T FIT sets on one line — do not abbreviate it to WON'T." */
  WONT_FIT: "WON'T FIT",
  UNKNOWN: 'UNKNOWN',
};

const VERDICT_TOKEN: Record<Verdict, string> = {
  FITS: 'fits',
  SPILLS: 'spills',
  WONT_FIT: 'wont',
  UNKNOWN: 'unknown',
};

function semanticStyle(token: string): CSSProperties {
  return {
    '--v-colour': `var(--${token})`,
    '--v-wash': `var(--${token}-wash)`,
    '--v-edge': `var(--${token}-edge)`,
  } as CSSProperties;
}

export function VerdictBadge({ verdict, detail }: { verdict: Verdict; detail?: string }) {
  return (
    <span>
      <span className="vpill" style={semanticStyle(VERDICT_TOKEN[verdict])}>
        {VERDICT_WORD[verdict]}
      </span>
      {/* Trailing detail sits OUTSIDE the pill so the pill's width depends only
          on the word and a rail of pills stays aligned. */}
      {detail ? <span className="vpill__detail">{detail}</span> : null}
    </span>
  );
}

/** Gate statuses — three, and no fourth. PASSED --fits, NOT MET --wont,
 *  NOT CHECKED --unknown. */
const GATE_TOKEN: Record<GateStatus, string> = {
  PASSED: 'fits',
  NOT_MET: 'wont',
  NOT_CHECKED: 'unknown',
};
const GATE_WORD: Record<GateStatus, string> = {
  PASSED: 'PASSED',
  NOT_MET: 'NOT MET',
  NOT_CHECKED: 'NOT CHECKED',
};
/** The ledger row's glyph, so a gate is readable with no colour perception at
 *  all: a tick passed, an alert blocked, a cross never reached. */
const GATE_ICON: Record<GateStatus, IconName> = {
  PASSED: 'check',
  NOT_MET: 'alert',
  NOT_CHECKED: 'x',
};

export function GateBadge({ status }: { status: GateStatus }) {
  return (
    <span className="vpill" style={semanticStyle(GATE_TOKEN[status])}>
      {GATE_WORD[status]}
    </span>
  );
}

export function GateIcon({ status }: { status: GateStatus }) {
  return (
    <span style={{ color: `var(--${GATE_TOKEN[status]})`, display: 'flex' }}>
      <Icon name={GATE_ICON[status]} />
    </span>
  );
}

/* ── Provenance tag ───────────────────────────────────────────────────────
   The tag on every number, and one of the most important things in this
   system. A pill with a wash, mono, 10px, uppercase.

   Estimates carry a tilde AND a tag, always together: a figure tagged
   INFERRED is a different claim from the same figure tagged MEASURED. */

/** The wash matching each tag's colour. Named rather than derived in CSS so
 *  the pairing is one decision in one place. */
const TAG_WASH: Record<DisplayTag, string> = {
  MEASURED: 'var(--fits-wash)',
  INFERRED: 'var(--info-wash)',
  DECLARED: 'var(--unknown-wash)',
  DEFAULT: 'var(--spills-wash)',
  UNTESTED: 'var(--unknown-wash)',
};

export function ProvenanceTag({ tag }: { tag: DisplayTag | null }) {
  if (!tag) return null;
  /* UNTESTED is a real wire value from app/hwdetect.py with no tag defined in
     the design system. Marked as a placeholder rather than given a quiet
     invented colour. */
  const placeholder = tag === 'UNTESTED';
  return (
    <span
      className="tag"
      data-placeholder={placeholder || undefined}
      style={
        {
          '--tag-colour': TAG_TOKEN[tag],
          '--tag-wash': TAG_WASH[tag],
        } as CSSProperties
      }
      title={
        placeholder
          ? 'PLACEHOLDER: the engine returns untested_on_this_platform; ' +
            'DESIGN_SYSTEM §9.3 defines no tag for it.'
          : undefined
      }
    >
      {tag}
    </span>
  );
}

/* ── Fact-origin tag ──────────────────────────────────────────────────────
   The same 16px pill as ProvenanceTag, carrying the ENGINE'S origin word.

   Why a second component rather than a fifth DisplayTag: the two vocabularies
   answer different questions and must not be allowed to blur. `ProvenanceTag`
   answers "how was this hardware number obtained" — measured, inferred,
   declared, defaulted. `OriginTag` answers "who is vouching for this fact" —
   measured, stated, asserted, defaulted. `lib/engine/types.ts` already records
   that three provenance vocabularies exist in this repository and do not
   agree; the answer to a fourth is not to merge them, it is to keep each one
   pointed at its own question and to map the STYLE rather than the word. See
   `lib/engine/facts.ts` for the mapping and the argument for it.

   The word is the load-bearing half. ASSERTED and STATED share Graphite's grey
   — both are unverified repetitions, which is the rank grey encodes — and are
   told apart by the word, exactly as page 05 requires of every colour-coded
   state. What must never happen is either of them rendering green. */

export function OriginTag({
  origin,
  by,
  compact,
}: {
  origin: FactOrigin;
  /** Who, when the interface knows: "the model", "you". Appended to the title
   *  so the tag answers "and by whom" on hover without growing a second pill. */
  by?: string | null;
  /** A DOT INSTEAD OF THE WORD, for the places where the word is the third
   *  label on one short line. Max, 2026-09-20, on `the bar you set · 70%
   *  STATED`: "the STATED is a status symbol, and instead the text can be Bar
   *  Set - 70% colors or underlind or put in a colored card to showcase that
   *  status". The colour is the same token the pill uses, so the two forms say
   *  the same thing; the word is still on the element, as its accessible name
   *  and its tooltip, because provenance a screen reader cannot reach is not
   *  provenance. Never use this where the origin is the point of the row - a
   *  fact table, a claims list - only where it qualifies a value beside it. */
  compact?: boolean;
}) {
  const tag = ORIGIN_TAG[origin];
  const means = ORIGIN_MEANS[origin];
  const word = ORIGIN_WORD[origin];
  return (
    <span
      className={compact ? 'tag tag--dot' : 'tag'}
      data-origin={origin}
      style={
        {
          '--tag-colour': TAG_TOKEN[tag],
          '--tag-wash': TAG_WASH[tag],
        } as CSSProperties
      }
      title={by ? `${word} — ${means} — ${by}` : `${word} — ${means}`}
      aria-label={compact ? word : undefined}
    >
      {compact ? null : word}
    </span>
  );
}

/* ── Buttons ──────────────────────────────────────────────────────────────
   Quiet borders, no fill until hover, and no fill at all except where the
   product asks for a commitment. Icons liberally: a button that can carry a
   glyph that helps it be recognised at a glance should carry one. */

type ButtonKind = 'primary' | 'ghost' | 'quiet';

export function Button({
  kind = 'ghost',
  followup,
  icon,
  chevron,
  small,
  pill,
  children,
  ...rest
}: {
  kind?: ButtonKind;
  followup?: boolean;
  /** Leading glyph. */
  icon?: IconName;
  /** Trailing chevron, for buttons that open something. */
  chevron?: boolean;
  small?: boolean;
  pill?: boolean;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const classes = [
    'btn',
    `btn--${kind}`,
    followup ? 'btn--followup' : '',
    small ? 'btn--sm' : '',
    pill ? 'btn--pill' : '',
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <button type="button" className={classes} {...rest}>
      {icon ? <Icon name={icon} /> : null}
      {children}
      {chevron ? <Icon name="chevdown" size={12} style={{ color: 'var(--ink-3)' }} /> : null}
    </button>
  );
}

export function IconButton({
  label,
  icon,
  size,
  bordered,
  children,
  ...rest
}: {
  label: string;
  /** Preferred: a Graphite symbol. `children` remains for the rare control
   *  that needs something else, but nothing in this build uses it. */
  icon?: IconName;
  size?: 'sm' | 'xs';
  bordered?: boolean;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const classes = [
    'iconbtn',
    bordered ? 'iconbtn--bordered' : '',
    size ? `iconbtn--${size}` : '',
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <button type="button" className={classes} aria-label={label} title={label} {...rest}>
      {icon ? <Icon name={icon} size={size === 'xs' ? 12 : 14} /> : children}
    </button>
  );
}

/* ── Context chip ─────────────────────────────────────────────────────────
   "A chip is a profile, not a filename." A filename tells an ML engineer
   nothing, so every attached thing carries its profile in the chip. The
   sensitivity flag renders as a glyph AND the word, never as colour alone. */

export function ContextChip({
  icon,
  label,
  profile,
  tag,
  sensitive,
  selected,
  onClick,
}: {
  icon: IconName;
  label: ReactNode;
  profile?: ReactNode;
  tag?: DisplayTag | null;
  sensitive?: boolean;
  selected?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      className="chip"
      data-lines={profile ? '2' : '1'}
      data-sensitive={sensitive || undefined}
      aria-pressed={selected}
      onClick={onClick}
    >
      <Icon name={sensitive ? 'sensitive' : icon} size={profile ? 14 : 12} />
      <span className="chip__stack">
        <span className="chip__label">{label}</span>
        {profile ? <span className="chip__profile">{profile}</span> : null}
      </span>
      {sensitive ? <span className="chip__sensitive">Sensitive</span> : null}
      {tag ? <ProvenanceTag tag={tag} /> : null}
    </button>
  );
}

/* ── Semantic strip ───────────────────────────────────────────────────────
   A finding, not an error: it names exactly what is missing and, where there
   is one, offers the thing that would fix it. Whatever it sits above stays
   fully usable underneath. */

export function Strip({
  tone,
  icon,
  children,
}: {
  tone: 'spills' | 'wont' | 'info' | 'fits';
  icon?: IconName;
  children: ReactNode;
}) {
  return (
    <div
      className="strip"
      style={
        {
          '--strip-colour': `var(--${tone})`,
          '--strip-wash': `var(--${tone}-wash)`,
          '--strip-edge': `var(--${tone}-edge)`,
          display: icon ? 'flex' : undefined,
          alignItems: icon ? 'flex-start' : undefined,
          gap: icon ? 'var(--sp-6)' : undefined,
        } as CSSProperties
      }
    >
      {icon ? (
        <span style={{ display: 'flex', paddingTop: 1 }}>
          <Icon name={icon} />
        </span>
      ) : null}
      <span>{children}</span>
    </div>
  );
}
