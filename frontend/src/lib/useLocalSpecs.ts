import { useEffect, useState } from 'react';
import { getLocalSpecs } from './engine/client';
import type { LocalSpecs } from './engine/types';

export type SpecsState =
  | { status: 'loading' }
  | { status: 'ok'; specs: LocalSpecs }
  | { status: 'error'; message: string };

/**
 * `GET /local_specs`, ONCE PER PAGE — not once per component that wants it.
 *
 * WHY THIS IS SHARED, AND WHY IT WAS A REAL DEFECT THAT IT WAS NOT.
 *
 * Four components read this: the Machine pane, the machine chip in the
 * composer, the first-run hardware card in the empty state, and the pane
 * stack's own header. Each used to run its own effect, so one page load was up
 * to four requests for the same fact sheet, and — the visible half — every
 * MOUNT started again at `{status:'loading'}`. The Machine pane therefore fell
 * back to skeleton rows under the line "source not read yet" whenever it
 * remounted, which is the pane saying it has not read something it read four
 * seconds ago. Photographed in both themes while driving the product end to
 * end; eight `/local_specs` responses were counted off the network log in
 * fourteen seconds on one screen.
 *
 * Four independent readings of one machine is also wrong on the product's own
 * terms. `components/Rail.tsx` already states the principle for the clock:
 * "one reading per render, shared by every row, so a column of forty
 * timestamps is forty readings of the same instant rather than forty instants
 * a millisecond apart." The hardware in this box is the hardware in this box,
 * `GET /api/evidence` calls facts with no thread MACHINE SCOPE for exactly that
 * reason, and the pane's own provenance line already promises what this now
 * delivers: read this session.
 *
 * The cache is a module-level promise, which is the pattern
 * `lib/engine/config.ts engineSession()` already uses in this codebase for the
 * same shape of problem. It is deliberately NOT a time-based cache: "this
 * session" is the claim the interface prints, and a five-minute expiry would
 * make that sentence false without telling anybody.
 *
 * On failure this returns the failure. It does NOT fall back to a default
 * profile: DESIGN_SYSTEM §9.13 — "It never substitutes a default silently, and
 * a failed detection never renders as a measurement." A failed read is cached
 * too, so four components report one failure rather than four; `forgetLocalSpecs`
 * is how a retry control would clear it.
 */

let cached: Promise<SpecsState> | null = null;
/** The resolved answer, so a component mounting after the read renders the
 *  values immediately instead of flashing the loading state at the reader. */
let settled: SpecsState | null = null;

function read(): Promise<SpecsState> {
  if (cached) return cached;
  cached = getLocalSpecs()
    .then((specs): SpecsState => ({ status: 'ok', specs }))
    .catch(
      (error: unknown): SpecsState => ({
        status: 'error',
        message: error instanceof Error ? error.message : String(error),
      }),
    )
    .then((state) => {
      settled = state;
      return state;
    });
  return cached;
}

export function useLocalSpecs(): SpecsState {
  const [state, setState] = useState<SpecsState>(() => settled ?? { status: 'loading' });

  useEffect(() => {
    if (settled) {
      setState(settled);
      return;
    }
    let live = true;
    void read().then((next) => {
      if (live) setState(next);
    });
    return () => {
      live = false;
    };
  }, []);

  return state;
}

/** Drop the reading, so the next mount asks the engine again. For a "recheck"
 *  control — Graphite page 13 draws one in the pane header — and for a
 *  reconnect, where the engine on the other end may be a different machine. */
export function forgetLocalSpecs(): void {
  cached = null;
  settled = null;
}
