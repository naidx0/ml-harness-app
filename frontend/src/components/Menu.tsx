/**
 * The dropdown menu, built to Graphite page 14.4, and nothing else.
 *
 * "A menu is a list of things you can do to one object. It is not a place to
 * put settings, it is not a place to put a verdict, and it never contains a
 * number that has not appeared elsewhere. Rows are the rail's own 30px
 * icon-and-label row, so a menu and the rail have the same rhythm — which is
 * correct, because the rail is a menu."
 *
 * WHY THIS FILE EXISTS. Two surfaces in this build now need one: the thread
 * row's hover actions, and the inspector's subject picker. Two hand-rolled
 * popovers would be two sets of dismiss rules, two focus behaviours and two
 * radii, and page 14.6 lists six behaviours that are shared by all four
 * transient surfaces precisely so they cannot drift apart. They are
 * implemented once, here.
 *
 * PAGE 14.6, ALL SIX, IMPLEMENTED RATHER THAN QUOTED:
 *   Escape closes and focus returns to the trigger — "a run is supervised with
 *     keys".
 *   Click outside closes WITHOUT acting — "a dismissal is not a choice".
 *   Arrow keys move, Enter chooses.
 *   Elevation is --e3, never --e4.
 *   No arrows, no tails — a 6px offset and an elevation locate the surface.
 *   Never the only home for a fact — which is a rule about CONTENT, and it is
 *     why nothing in this file will render a number or a verdict badge: the
 *     only things a row may carry are an icon, a label, an optional keycap and
 *     an optional reason.
 *
 * A DISABLED ROW STAYS IN PLACE AND SAYS WHY. Page 14.5's Do/Don't pair rules
 * that an unavailable action is shown disabled with its reason, never removed:
 * "the user learns that the option exists and why it is closed, which is the
 * only thing that lets them change it." That is not a nicety here — it is the
 * one honest way to draw Delete, which this product's engine deliberately does
 * not implement.
 */

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { Icon, type IconName } from './Icon';

export interface MenuRow {
  /** Stable identity. Also what `onChoose` is called with. */
  id: string;
  label: string;
  icon?: IconName;
  /** A keyboard shortcut, drawn as a keycap. Never a number. */
  keycap?: string;
  /** Page 14.5: one destructive row, LAST, after a divider, named with its
   *  object, and coloured on the ink only — never a red row fill. */
  destructive?: boolean;
  /** Rendered pressed. Used by the inspector's picker for the open subject. */
  current?: boolean;
  /** When set the row is disabled IN PLACE and prints this sentence beneath
   *  its label. Never a removed row. */
  disabledReason?: string;
}

/**
 * The menu surface. Anchored to `anchor`, below by default, flipping above at
 * the bottom of the window and shifting left at the right edge.
 *
 * `position: fixed` rather than an absolutely positioned child, because both
 * callers live inside a scrolling container with `overflow: hidden` on an
 * ancestor — the rail scroller and the inspector — and an absolutely
 * positioned menu is clipped by both.
 */
export function Menu({
  anchor,
  rows,
  onChoose,
  onClose,
  label,
  /** 14.1: a dropdown is --r-14 and sized to its content, with a floor so a
   *  three-word menu is not a sliver. */
  minWidth = 200,
  /** Which edge of the menu meets which edge of the trigger. `end` is for a
   *  trigger that sits at the right edge of a narrow column — a menu left-
   *  aligned to the rail's overflow button hangs over the transcript for no
   *  reason, and a menu is supposed to belong to the thing it acts on. */
  align = 'start',
}: {
  anchor: HTMLElement | null;
  rows: MenuRow[];
  onChoose: (id: string) => void;
  onClose: () => void;
  label: string;
  minWidth?: number;
  align?: 'start' | 'end';
}) {
  const surface = useRef<HTMLDivElement>(null);
  const [at, setAt] = useState<{ top: number; left: number } | null>(null);
  /* -1 means "nothing focused yet", which is the state a mouse user is in.
     The first arrow key moves to 0 rather than to 1. */
  const [active, setActive] = useState(-1);

  const choosable = rows.filter((row) => !row.disabledReason);

  useLayoutEffect(() => {
    if (!anchor || !surface.current) return;
    const trigger = anchor.getBoundingClientRect();
    const own = surface.current.getBoundingClientRect();
    /* 6px, the same offset a tooltip uses. Page 14.3: "anchored below their
       trigger with the same 6px offset a tooltip uses." */
    const GAP = 6;
    let top = trigger.bottom + GAP;
    if (top + own.height > window.innerHeight - 8) {
      const above = trigger.top - GAP - own.height;
      top = above >= 8 ? above : Math.max(8, window.innerHeight - 8 - own.height);
    }
    let left = align === 'end' ? trigger.right - own.width : trigger.left;
    if (left + own.width > window.innerWidth - 8) {
      left = Math.max(8, trigger.right - own.width);
    }
    left = Math.max(8, left);
    setAt({ top, left });
    /* The surface takes focus so Escape and the arrow keys reach it without
       the user first having to click a row. Focus goes back to the trigger on
       every exit — see `MenuButton`. */
    surface.current.focus();
  }, [anchor, rows.length, align]);

  useEffect(() => {
    /* "Click outside closes, without acting. A dismissal is not a choice."
       Pointerdown rather than click, so a drag that starts outside the menu
       closes it before it can land on a row underneath. */
    const away = (event: PointerEvent) => {
      const target = event.target as Node;
      if (surface.current?.contains(target)) return;
      if (anchor?.contains(target)) return;
      onClose();
    };
    /* A menu is not a viewport-tracking object. If the window moves under it,
       the honest response is to close rather than to chase. */
    const gone = () => onClose();
    window.addEventListener('pointerdown', away, true);
    window.addEventListener('resize', gone);
    window.addEventListener('blur', gone);
    return () => {
      window.removeEventListener('pointerdown', away, true);
      window.removeEventListener('resize', gone);
      window.removeEventListener('blur', gone);
    };
  }, [anchor, onClose]);

  const move = (delta: number) => {
    setActive((current) => {
      const next = current + delta;
      if (next < 0) return choosable.length - 1;
      if (next >= choosable.length) return 0;
      return next;
    });
  };

  return (
    <div
      ref={surface}
      className="menu"
      role="menu"
      aria-label={label}
      tabIndex={-1}
      style={{
        position: 'fixed',
        top: at?.top ?? -9999,
        left: at?.left ?? -9999,
        minWidth,
        /* Hidden until placed, so the surface is never seen at 0,0 for a frame
           on its way to where it belongs. */
        visibility: at ? 'visible' : 'hidden',
      }}
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          event.preventDefault();
          event.stopPropagation();
          onClose();
        } else if (event.key === 'ArrowDown') {
          event.preventDefault();
          move(1);
        } else if (event.key === 'ArrowUp') {
          event.preventDefault();
          move(-1);
        } else if (event.key === 'Enter' || event.key === ' ') {
          if (active >= 0 && choosable[active]) {
            event.preventDefault();
            onChoose(choosable[active].id);
          }
        }
      }}
    >
      {rows.map((row, index) => {
        const previous = rows[index - 1];
        /* The divider is drawn by the destructive row, not authored by the
           caller, so "after a divider" cannot be forgotten at a call site. */
        const divider = row.destructive && previous && !previous.destructive;
        const choosableIndex = choosable.indexOf(row);
        return (
          /* `role="none"` so the wrapper does not sit between `role="menu"` and
             `role="menuitem"` in the accessibility tree. It exists only to hold
             the divider and the reason line beside their row. */
          <div key={row.id} role="none">
            {divider ? <div className="menu__rule" role="separator" /> : null}
            <button
              type="button"
              role="menuitem"
              className="menu__row"
              data-destructive={row.destructive || undefined}
              data-active={choosableIndex >= 0 && choosableIndex === active ? 'true' : undefined}
              aria-checked={row.current}
              disabled={row.disabledReason != null}
              title={row.disabledReason}
              onMouseEnter={() => choosableIndex >= 0 && setActive(choosableIndex)}
              onClick={() => onChoose(row.id)}
            >
              {row.icon ? <Icon name={row.icon} /> : <span className="menu__nolead" />}
              <span className="menu__label">{row.label}</span>
              {row.current ? <Icon name="check" size={12} /> : null}
              {row.keycap ? <span className="menu__key">{row.keycap}</span> : null}
            </button>
            {/* The reason sits under the row it closes, in the row's own
                indent, so it reads as that row's caption and not as a note
                about the menu. */}
            {row.disabledReason ? (
              <p className="menu__why">{row.disabledReason}</p>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

/**
 * Trigger + menu, with the focus contract page 14.6 requires: the menu takes
 * focus when it opens and hands it back to the trigger when it closes, so a
 * keyboard never lands somewhere it cannot see.
 */
export function MenuButton({
  rows,
  onChoose,
  label,
  minWidth,
  align,
  open,
  setOpen,
  children,
  className,
  title,
}: {
  rows: MenuRow[];
  onChoose: (id: string) => void;
  label: string;
  minWidth?: number;
  align?: 'start' | 'end';
  open: boolean;
  setOpen: (next: boolean) => void;
  children: ReactNode;
  className: string;
  title?: string;
}) {
  const trigger = useRef<HTMLButtonElement>(null);

  return (
    <>
      <button
        ref={trigger}
        type="button"
        className={className}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label}
        title={title ?? label}
        onClick={(event) => {
          event.stopPropagation();
          setOpen(!open);
        }}
      >
        {children}
      </button>
      {open ? (
        <Menu
          anchor={trigger.current}
          rows={rows}
          label={label}
          minWidth={minWidth}
          align={align}
          onChoose={(id) => {
            setOpen(false);
            trigger.current?.focus();
            onChoose(id);
          }}
          onClose={() => {
            setOpen(false);
            trigger.current?.focus();
          }}
        />
      ) : null}
    </>
  );
}
