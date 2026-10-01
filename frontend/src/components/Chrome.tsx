/**
 * Chrome controls: the theme toggle and the segmented control.
 *
 * TWO OF THE THREE CORRECTIONS DESIGN_DIRECTIVES NAMES LIVE IN THIS FILE.
 *
 * §2 — COMPACT IS THE ONLY DENSITY. `useRowSize` is gone, with the
 * comfortable / compact segmented control and the `data-rows` attribute it
 * set. "The interface ships compact and stays compact. Airy is a defect, not a
 * preference." Graphite draws every row at its literal compact height rather
 * than deriving it from a looser one, because a scale that is only ever used
 * at one setting should be drawn at that setting. Two modes means every
 * component has two sets of true values and only one of them is ever tested.
 *
 * The `mlh.rows` key is left alone rather than migrated: a stale localStorage
 * value now selects nothing, because nothing reads it.
 *
 * §3 — THERE IS ONE PRODUCT. Superseded by Max on 2026-08-19 and rewritten in
 * DESIGN_DIRECTIVES: "If there are no consumer versus enterprise specs, then
 * really don't worry about that… The scaffolding toggle in the shell should
 * go." So `Portal` and `Scaffold` are gone from this file rather than
 * relabelled. The fence went with the thing it was fencing: a `Scaffold`
 * wrapper with nothing left to put in it is an invitation to put something in
 * it, and the next thing somebody smuggles past a design review is the thing
 * the fence was built to make acceptable.
 *
 * The `mlh.portal` key was never written, so there is nothing stale to leave
 * alone this time.
 *
 * §1 of the design system still governs theme: three states — explicit dark,
 * explicit light, and system default. Both themes ship at equal quality; light
 * is a separately tuned instrument, not an inversion.
 */

import { useEffect, useState } from 'react';
import { Icon } from './Icon';

export type Theme = 'dark' | 'light' | 'system';

const THEME_KEY = 'mlh.theme';

/**
 * What "system" resolves to right now.
 *
 * Dark when the browser will not say, because dark is what this product ships
 * on first run and an unanswered media query should not flip the app to the
 * theme the user did not choose. `matchMedia` is guarded because jsdom and
 * older webviews do not always provide it.
 */
export function theSystemTheme(): 'dark' | 'light' {
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

export function useTheme(): [Theme, (next: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    const stored = localStorage.getItem(THEME_KEY);
    /* Ships dark on first run. */
    return stored === 'light' || stored === 'system' || stored === 'dark'
      ? stored
      : 'dark';
  });

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'system') {
      /* THE THIRD STATE, WHICH DID NOT WORK UNTIL 2026-09-05.
         This branch used to remove the attribute and leave a comment saying
         "the media query decides". There is no media query: `prefers-color-scheme`
         appears nowhere in this frontend, and bare `:root` in tokens.css is the
         DARK palette. So "system" silently meant "dark" on every machine, while
         the toggle's own tooltip said "Follow the system theme".

         Resolving the preference here rather than adding the missing media
         query keeps ONE copy of the light palette. The alternative was a
         second `@media (prefers-color-scheme: light)` block repeating forty
         token assignments, and two lists of the same colours drift. */
      root.setAttribute('data-theme', theSystemTheme());
    } else {
      root.setAttribute('data-theme', theme);
    }
    /* The old build could leave `data-rows="compact"` on the root from a
       previous session. Nothing reads it any more; it is cleared so a reader
       inspecting the DOM does not think a density mode still exists. */
    root.removeAttribute('data-rows');
    localStorage.setItem(THEME_KEY, theme);

    /* And it has to keep following. A user who flips their OS to light at
       dusk with this app open is still on "system", so the attribute has to
       move with them - otherwise the third state works once, at mount, which
       is a slower version of not working. */
    if (theme !== 'system') return;
    const watch = window.matchMedia?.('(prefers-color-scheme: light)');
    if (!watch) return;
    const follow = () => root.setAttribute('data-theme', theSystemTheme());
    watch.addEventListener('change', follow);
    return () => watch.removeEventListener('change', follow);
  }, [theme]);

  return [theme, setTheme];
}

/**
 * The theme control, as the brand book's own toggle: one icon button, and the
 * glyph shows where the click takes you rather than where you are. Sun means
 * "go light", moon means "go dark", and the cycle glyph means "hand it back to
 * the system". All three states are reachable, because the third one is real
 * and a two-way switch would leave it unreachable from the UI.
 */
export function ThemeToggle({
  theme,
  onChange,
}: {
  theme: Theme;
  onChange: (next: Theme) => void;
}) {
  const next: Theme = theme === 'dark' ? 'light' : theme === 'light' ? 'system' : 'dark';
  const label =
    next === 'light' ? 'Switch to light' : next === 'system' ? 'Follow the system theme' : 'Switch to dark';
  return (
    <button
      type="button"
      className="iconbtn iconbtn--bordered"
      onClick={() => onChange(next)}
      aria-label={label}
      title={`${label} · currently ${theme}`}
    >
      <Icon name={next === 'light' ? 'sun' : next === 'system' ? 'refresh' : 'moon'} />
    </button>
  );
}

export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: readonly { value: T; label: string }[];
  value: T;
  onChange: (next: T) => void;
}) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className="seg__btn"
          aria-pressed={option.value === value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
