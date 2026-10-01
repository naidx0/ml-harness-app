/**
 * The third theme state, which did not work.
 *
 * §1 of the design system promises three states: explicit dark, explicit
 * light, and system default. The third was implemented by REMOVING
 * `data-theme` from the root and a comment saying "the media query decides".
 * `prefers-color-scheme` appears nowhere in this frontend, and bare `:root` in
 * tokens.css is the dark palette - so "system" rendered dark on every machine
 * while the toggle's tooltip said "Follow the system theme".
 *
 * These tests fail against that implementation: it never set the attribute at
 * all, so both of the first two assertions would read `null`.
 */

import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useTheme, theSystemTheme } from './Chrome';

type Listener = () => void;

function pretendTheSystemIs(scheme: 'light' | 'dark') {
  const listeners: Listener[] = [];
  const query = {
    matches: scheme === 'light',
    addEventListener: (_: string, fn: Listener) => listeners.push(fn),
    removeEventListener: (_: string, fn: Listener) => {
      const at = listeners.indexOf(fn);
      if (at >= 0) listeners.splice(at, 1);
    },
  };
  vi.stubGlobal('matchMedia', () => query);
  return {
    flipTo(next: 'light' | 'dark') {
      query.matches = next === 'light';
      listeners.forEach((fn) => fn());
    },
    listenerCount: () => listeners.length,
  };
}

describe('the system theme state', () => {
  beforeEach(() => localStorage.setItem('mlh.theme', 'system'));
  afterEach(() => {
    vi.unstubAllGlobals();
    document.documentElement.removeAttribute('data-theme');
    localStorage.clear();
  });

  it('renders light when the system is light', () => {
    pretendTheSystemIs('light');
    renderHook(() => useTheme());
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  });

  it('renders dark when the system is dark', () => {
    pretendTheSystemIs('dark');
    renderHook(() => useTheme());
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('keeps following when the system changes with the app open', () => {
    /* The third state working once, at mount, is a slower way of not
       working - a user who flips their OS at dusk is still on "system". */
    const system = pretendTheSystemIs('dark');
    renderHook(() => useTheme());
    act(() => system.flipTo('light'));
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  });

  it('stops following once the user makes an explicit choice', () => {
    const system = pretendTheSystemIs('dark');
    const { result } = renderHook(() => useTheme());
    act(() => result.current[1]('light'));
    act(() => system.flipTo('dark'));
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    expect(system.listenerCount()).toBe(0);
  });

  it('falls back to dark where the browser will not answer', () => {
    /* jsdom and older webviews do not always provide matchMedia. An
       unanswered query must not flip the app to a theme nobody chose, and
       dark is what it ships on first run. */
    vi.stubGlobal('matchMedia', undefined);
    expect(theSystemTheme()).toBe('dark');
  });
});
