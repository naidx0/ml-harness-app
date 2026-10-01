/**
 * APPROVAL IS A CONTRACT, NOT A BUTTON — Graphite page 15, and
 * `docs/THE_PROPOSAL_LOOP.md` §5.
 *
 * "What they approved is what runs. Any deviation stops and asks. This is not
 * ceremony. The whole product is trust: we are the tool that tells people not
 * to train, and we are about to spend hours of their GPU and their model's
 * tokens. If the storm can quietly do something that was not in the picture
 * they said yes to, every claim this product makes about honesty is
 * decoration."
 *
 * ══ WHY THIS IS A CARD IN THE THREAD AND NOT A DIALOG ══════════════════════
 *
 * Page 15.1 rules on it: "If the decision can be a message in the thread, it
 * must be a message in the thread. That is not a preference about modality —
 * it is the product's central claim, which is that the conversation *is* the
 * lab notebook." A dialog produces no record; it interrupts, it is answered,
 * and it is gone. An approval card "blocks the run rather than the app, and is
 * still there tomorrow saying what you decided". So it never disappears when
 * answered — it collapses into the record of the answer.
 *
 * ══ THE THREE RULES TAKEN VERBATIM FROM PAGE 15.2 AND 15.3 ═════════════════
 *
 * 1. **"Allow once" is the solid button and the default focus.** Solid marks
 *    the commitment being offered, and the commitment on offer is one call.
 *    "Always allow is never the solid button and never the default focus" — a
 *    standing grant is a far larger commitment and the interface must not make
 *    the larger commitment the easier click.
 * 2. **Deny is neutral, never destructive.** Refusing a proposal destroys
 *    nothing, so Deny is an ordinary button and is not red.
 * 3. **A timeout resolves to Deny, never to Allow.** "Nothing in this product
 *    ever happens because nobody was watching." The countdown is a 2px line on
 *    the header's top edge in --st-attention, which is the accent — the product
 *    asking for something — and never a verdict colour, "because a running
 *    clock is not a claim about the world".
 *
 * ══ WHAT A BUILD APPROVAL DOES NOT OFFER, AND WHY ══════════════════════════
 *
 * **No "Always allow", and no window.** Both omissions are page 15's own rules
 * applied to this subject rather than gaps:
 *
 * - A standing grant has to be a grant of SOMETHING repeatable — page 15.2's
 *   specimen grants `write_file`, a tool. A build is a specific plan against a
 *   specific data snapshot with a specific fingerprint; "always allow this
 *   build" could only mean "always allow builds", which is a grant nobody
 *   asked for and the opposite of a contract. Tool-level standing grants
 *   belong on the tool approval, which is where `approval: always` already
 *   lives in the registry.
 * - The window exists because "training runs for hours and the person who
 *   started it goes to lunch… an approval that could sit unanswered forever
 *   stalls a run that is burning a GPU". A proposal stalls nothing: nothing is
 *   running. A countdown here would be manufacturing urgency, which is the
 *   prose form of inventing a number. The window belongs on the deviation stop
 *   — a storm that paused mid-run IS burning something — and `countdown` below
 *   is the seam for it, unused until there is a storm to pause.
 *
 * ══ THE HONEST GAP, STATED ON SCREEN RATHER THAN HIDDEN ════════════════════
 *
 * There is no executor yet. At the time this was built `app/storm.py` does not
 * exist and `app/main.py` has no build or approval route, so an approval
 * recorded here binds a contract and starts nothing. The card says that in
 * those words. A surface that took the click, went quiet, and let the person
 * believe something had started would be a worse lie than any missing feature.
 */

import { useEffect, useRef } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { useSecondTick } from '../lib/useSecondTick';
import { Icon } from './Icon';
import { Button } from './primitives';

export type ApprovalAnswer = 'allow_once' | 'always_allow' | 'deny';

/* ── The card ─────────────────────────────────────────────────────────────── */

export function ApprovalCard({
  /** One sentence: what would happen if this is allowed. */
  asks,
  /** The facts of the call, shown verbatim. Page 15.2's kv block. */
  facts,
  /** Anything larger than a kv row — a deviation table, a diff. */
  children,
  /** Offered only where a standing grant means something. See the header. */
  alwaysAllowLabel,
  /** The window, when there is one. BOTH ends, because the countdown line is
   *  a fraction and a fraction needs a denominator that somebody set — reading
   *  it off the moment this component happened to mount would make the line's
   *  length depend on when the page was opened. Present only where something
   *  is actually waiting on the answer; absent everywhere else, because a
   *  clock is a claim too. */
  countdown,
  /** What happens if the window closes. Rendered beside the buttons so the
   *  rule is on screen and not only in a document. */
  timeoutNote,
  footnote,
  /** True while the engine is being asked, or when this surface cannot ask it
   *  at all. A button that looks live and does nothing is the worst of both. */
  disabled,
  onAnswer,
}: {
  asks: ReactNode;
  facts?: { key: string; value: ReactNode; tone?: 'plain' | 'warn' }[];
  children?: ReactNode;
  alwaysAllowLabel?: string;
  countdown?: { startedAt: string; expiresAt: string } | null;
  timeoutNote?: ReactNode;
  footnote?: ReactNode;
  disabled?: boolean;
  onAnswer: (answer: ApprovalAnswer, reason: 'clicked' | 'timeout') => void;
}) {
  const now = useSecondTick();
  const actions = useRef<HTMLDivElement>(null);
  const deadline = countdown ? Date.parse(countdown.expiresAt) : Number.NaN;
  const opened = countdown ? Date.parse(countdown.startedAt) : Number.NaN;
  const windowed = Number.isFinite(deadline) && Number.isFinite(opened);
  const span = windowed ? Math.max(1, deadline - opened) : 1;
  const left = windowed ? Math.max(0, deadline - now) : 0;
  const expired = windowed && left <= 0;

  /* "Default focus: Allow once." The commitment on offer is one call, and the
     keyboard has to land on the same button the eye does. `preventScroll`
     because this card sits in a transcript that is already following its own
     tail — the focus ring is the point, not a jump. */
  useEffect(() => {
    const first = actions.current?.querySelector('button');
    if (first instanceof HTMLElement) first.focus({ preventScroll: true });
  }, []);

  /* A TIMEOUT RESOLVES TO DENY. In an effect rather than during render,
     because it is a decision that leaves this component — and it fires once,
     on the tick that crosses the deadline. */
  const fired = useRef(false);
  useEffect(() => {
    if (!expired || fired.current) return;
    fired.current = true;
    onAnswer('deny', 'timeout');
  }, [expired, onAnswer]);

  return (
    <div className="card card--approval">
      <div className="card__head approval__head">
        {windowed ? (
          /* The 2px line on the header's top edge. It shrinks as the window
             closes; it is content on a timer, not an animation, so it survives
             prefers-reduced-motion intact. */
          <span
            className="approval__clockline"
            style={
              {
                width: `${Math.max(0, Math.min(100, (left / span) * 100))}%`,
              } as CSSProperties
            }
            aria-hidden="true"
          />
        ) : null}
        <Icon name={windowed ? 'clock' : 'alert'} size={14} />
        <span className="card__kicker">Approval</span>
        <span className="card__headright">
          {windowed ? (
            <span className="approval__left mono">{remaining(left)} left</span>
          ) : (
            <span className="approval__needs">
              <span
                className="dot"
                data-shape="filled-ring"
                style={{ '--st-colour': 'var(--st-attention)' } as CSSProperties}
                aria-hidden="true"
              />
              Needs you
            </span>
          )}
        </span>
      </div>

      <div className="card__body">
        <div className="approval__asks">{asks}</div>

        {facts && facts.length > 0 ? (
          <div className="approval__facts">
            {facts.map((fact) => (
              <div className="approval__fact" key={fact.key} data-tone={fact.tone}>
                <span className="approval__k">{fact.key}</span>
                <span className="approval__v">{fact.value}</span>
              </div>
            ))}
          </div>
        ) : null}

        {children}

        <div className="approval__actions" ref={actions}>
          <Button
            kind="primary"
            disabled={disabled}
            onClick={() => onAnswer('allow_once', 'clicked')}
          >
            Allow once
          </Button>
          {alwaysAllowLabel ? (
            <Button disabled={disabled} onClick={() => onAnswer('always_allow', 'clicked')}>
              Always allow <span className="approval__grant mono">{alwaysAllowLabel}</span>
            </Button>
          ) : null}
          {/* Deny is never disabled while the approval is being asked: saying no
              takes nothing from the engine, and a person who has changed their
              mind must not have to wait for a request they no longer want. */}
          <Button onClick={() => onAnswer('deny', 'clicked')}>Deny</Button>
          {timeoutNote ? <span className="approval__note">{timeoutNote}</span> : null}
        </div>

        {footnote ? <p className="approval__foot">{footnote}</p> : null}
      </div>
    </div>
  );
}

/* ── The record it becomes ────────────────────────────────────────────────── */

/**
 * Page 15.3: "The card collapses to one line and keeps the arguments one click
 * away. The transcript is the record of what was permitted, not just of what
 * happened." And on the expired case: "The row is permanent and says why, so a
 * reader six months later does not think the tool failed."
 */
export function ApprovalRecord({
  answer,
  reason,
  at,
  /** The fingerprint of what was approved. This is the contract; showing it is
   *  what makes "what was approved is what runs" checkable rather than said. */
  fingerprint,
  note,
  onAskAgain,
}: {
  answer: ApprovalAnswer;
  reason: 'clicked' | 'timeout';
  at: string;
  fingerprint: string;
  note?: ReactNode;
  onAskAgain?: () => void;
}) {
  const allowed = answer !== 'deny';
  return (
    <div className="approvalrec" data-answer={allowed ? 'allowed' : 'denied'}>
      <span className="approvalrec__glyph">
        <Icon name={allowed ? 'check' : 'x'} size={14} />
      </span>
      <span className="approvalrec__word">
        {answer === 'allow_once'
          ? 'Allowed once by you'
          : answer === 'always_allow'
            ? 'Always allowed by you'
            : reason === 'timeout'
              ? 'Denied — no answer before the window closed'
              : 'Denied by you'}
      </span>
      <span className="approvalrec__fp mono" title={fingerprint}>
        {fingerprint.slice(0, 12)}
      </span>
      <span className="approvalrec__when">{when(at)}</span>
      {onAskAgain ? (
        <button type="button" className="approvalrec__again" onClick={onAskAgain}>
          <Icon name="refresh" size={12} />
          Ask me again
        </button>
      ) : null}
      {note ? <span className="approvalrec__note">{note}</span> : null}
    </div>
  );
}

/* ── The deviation ────────────────────────────────────────────────────────── */

/**
 * "This is what you approved, this is what changed, here is the choice."
 *
 * The sentences mirror `Build.deviations_from` in `app/build.py`, which is the
 * mechanical half of the contract: it compares each step's
 * `contract_fingerprint()` — the tool, the arguments, the dependencies, the
 * outputs and the exit criterion, and deliberately NOT the cost, because "a
 * cost estimate that improved between proposal and execution is not a
 * deviation from the contract, and treating it as one would train people to
 * click through the check that matters".
 *
 * Nothing here decides on its own that a change is harmless. Every line is a
 * change, and the choice is the person's.
 */
export function DeviationBlock({ notes }: { notes: string[] }) {
  if (notes.length === 0) return null;
  return (
    <div className="deviation">
      <div className="deviation__head">
        <Icon name="alert" size={12} />
        <span>
          {notes.length === 1
            ? 'One thing changed since you approved this'
            : `${notes.length} things changed since you approved this`}
        </span>
      </div>
      <ul className="deviation__list">
        {notes.map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>
    </div>
  );
}

/* ── helpers ──────────────────────────────────────────────────────────────── */

function remaining(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m > 0) return `${m}m ${String(s).padStart(2, '0')}s`;
  return `${s}s`;
}

function when(iso: string): string {
  const parsed = Date.parse(iso);
  if (!Number.isFinite(parsed)) return iso;
  return new Date(parsed).toLocaleString();
}
