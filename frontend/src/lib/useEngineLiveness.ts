/**
 * The engine-liveness store, as a hook.
 *
 * Thin on purpose: every decision lives in `lib/engine/liveness.ts`, which has
 * no React in it and can be reasoned about without a renderer. This file only
 * subscribes and starts the timer.
 *
 * `useSyncExternalStore` rather than `useState` + an effect, because the store
 * is written from outside React — `client.ts` and `events.ts` both publish into
 * it the moment a 401 comes back, which is mid-request and not mid-render.
 */

import { useEffect, useSyncExternalStore } from 'react';
import {
  dismissEngineNotice,
  engineLiveness,
  engineNoticeDismissed,
  startEngineWatch,
  subscribeToEngine,
  type EngineLiveness,
} from './engine/liveness';

export interface EngineLivenessView {
  state: EngineLiveness;
  /** The user has already read this exact state and closed it. */
  dismissed: boolean;
  dismiss: () => void;
}

export function useEngineLiveness(): EngineLivenessView {
  /* Two subscriptions to one store. The state snapshot is a module-level
     object that is replaced only when the meaning changes, and the dismissed
     snapshot is a boolean — both are stable between notifications, which is
     what this hook requires and what an object built per call would break. */
  const state = useSyncExternalStore(subscribeToEngine, engineLiveness);
  const dismissed = useSyncExternalStore(subscribeToEngine, engineNoticeDismissed);

  useEffect(() => startEngineWatch(), []);

  return { state, dismissed, dismiss: dismissEngineNotice };
}
