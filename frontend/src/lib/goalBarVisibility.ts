/**
 * CS12 — GoalBar X hides chrome; the plan stays in SQLite.
 *
 * sessionStorage so a refresh restores the bar (plan is still there) unless
 * the person hid it again this session. Plan tab / Goal affordance calls
 * showGoalBar so the bar can come back without rewriting the plan.
 */

const KEY = 'mlh.goalbarHidden';

const listeners = new Set<() => void>();

/** In-memory mirror — used when sessionStorage is missing (node tests). */
let memory = false;

function read(): boolean {
  try {
    if (typeof sessionStorage === 'undefined') return memory;
    return sessionStorage.getItem(KEY) === '1';
  } catch {
    return memory;
  }
}

function write(hidden: boolean): void {
  memory = hidden;
  try {
    if (typeof sessionStorage !== 'undefined') {
      if (hidden) sessionStorage.setItem(KEY, '1');
      else sessionStorage.removeItem(KEY);
    }
  } catch {
    /* private mode — memory still holds it */
  }
  for (const listen of listeners) listen();
}

export function isGoalBarHidden(): boolean {
  return read();
}

export function hideGoalBar(): void {
  write(true);
}

export function showGoalBar(): void {
  write(false);
}

export function subscribeGoalBarVisibility(listen: () => void): () => void {
  listeners.add(listen);
  return () => {
    listeners.delete(listen);
  };
}
