import { useEffect, useState } from 'react';
import { listStudios } from './engine/client';
import type { Studios } from './engine/types';

export type StudiosState =
  | { status: 'loading' }
  | { status: 'ok'; studios: Studios }
  | { status: 'error'; message: string };

/**
 * `GET /api/studios`, once per page, cached the way `useLocalSpecs` caches the
 * machine — same argument, same shape, and for the same reason: the packs do
 * not change while the page is open. The registry is built at import time on
 * the engine, so a second reading would return the identical bytes and cost a
 * skeleton flash on every remount.
 *
 * Nothing here knows the name of a pack or of a tool. If this file carried a
 * list, the list would be the second manifest `app/tools/blocks.py` exists to
 * refuse — "a tool that declares `provides=` on a new capability is a pack on
 * the day it is added rather than on the day somebody remembers this endpoint."
 *
 * On failure this returns the failure rather than a plausible set of packs. A
 * studio list that renders when the engine is unreachable is a claim about
 * what this harness can do, made by the interface, with nothing behind it.
 */

let cached: Promise<StudiosState> | null = null;
let settled: StudiosState | null = null;

function read(): Promise<StudiosState> {
  if (cached) return cached;
  cached = listStudios()
    .then((studios): StudiosState => ({ status: 'ok', studios }))
    .catch(
      (error: unknown): StudiosState => ({
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

export function useStudios(): StudiosState {
  const [state, setState] = useState<StudiosState>(() => settled ?? { status: 'loading' });

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

/** Drop the reading, so the next mount asks the engine again — for a reconnect,
 *  where the engine on the other end may hold a different registry. */
export function forgetStudios(): void {
  cached = null;
  settled = null;
}
