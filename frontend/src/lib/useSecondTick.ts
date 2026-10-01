import { useEffect, useState } from 'react';

/**
 * One shared clock for every elapsed timer on screen.
 *
 * DESIGN_SYSTEM §2.5.4: the elapsed line is how a spending run is told from a
 * non-spending one, and §10's reduced-motion note makes it the signal that has
 * to survive when all motion is removed — "which conveys 'alive' through
 * changing content rather than motion". So it is content on a timer, not an
 * animation, and it keeps ticking under `prefers-reduced-motion`.
 *
 * Law 3 still holds: this replaces the number once a second. It never tweens
 * between two values.
 */
export function useSecondTick(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  return now;
}
