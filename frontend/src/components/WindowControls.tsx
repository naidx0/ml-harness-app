/**
 * Minimize / maximize / close for the frameless shell.
 *
 * The native title bar is gone (the owner: the window icon and the rail mark
 * were "the whole double nonsense" - one app, one identity, the app owns its
 * frame the way Claude's desktop does). These three buttons are the native
 * box's replacement, rendered only when a shell is actually hosting the page:
 * in a browser tab the browser owns the frame and drawing fake controls in it
 * would be exactly the confusion this removes.
 *
 * Close goes through the SAME CloseRequested path as the native box did, so
 * it hides to tray and a training run keeps living - see lib.rs.
 */

import { hasNativeShell, nativeWindow } from '../lib/engine/shell';
import { Icon } from './Icon';

export function WindowControls() {
  if (!hasNativeShell()) return null;
  return (
    <span className="winctl" aria-label="Window controls">
      <button
        type="button"
        className="winctl__btn"
        aria-label="Minimize"
        onClick={() => nativeWindow('minimize')}
      >
        <svg viewBox="0 0 10 10" width="10" height="10" aria-hidden="true">
          <line x1="1" y1="5" x2="9" y2="5" stroke="currentColor" strokeWidth="1.2" />
        </svg>
      </button>
      <button
        type="button"
        className="winctl__btn"
        aria-label="Maximize or restore"
        onClick={() => nativeWindow('toggle_maximize')}
      >
        <svg viewBox="0 0 10 10" width="10" height="10" aria-hidden="true">
          <rect x="1.5" y="1.5" width="7" height="7" fill="none" stroke="currentColor" strokeWidth="1.2" />
        </svg>
      </button>
      <button
        type="button"
        className="winctl__btn winctl__btn--close"
        aria-label="Close - the engine keeps running"
        title="Close. The engine keeps running; reopen from the tray."
        onClick={() => nativeWindow('close')}
      >
        <Icon name="x" size={11} />
      </button>
    </span>
  );
}
