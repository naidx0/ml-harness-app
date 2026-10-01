/**
 * One line, under the app bar, that appears only when the engine underneath
 * this page is not the engine this page loaded against.
 *
 * ── WHY IT EXISTS ──────────────────────────────────────────────────────────
 *
 * Two processes in development — Vite for hot reload, the engine for the API —
 * and until now the page could not tell which engine it was talking to. Both
 * failures that came out of that were silent by construction:
 *
 *   the bearer token rotates on every engine start, so a tab left open starts
 *   401ing and everything already rendered keeps looking fine;
 *
 *   and an engine three commits old answers `/health` with `ok`, serves
 *   `gpu_name: null` for an installed RTX 2060 SUPER, and nothing on screen
 *   suggests you are reading yesterday's answers.
 *
 * ── WHY IT IS THIS SMALL ───────────────────────────────────────────────────
 *
 * `docs/DESIGN_DIRECTIVES.md` §6: colour appears for state and for data, never
 * for ornament. A staleness notice IS a state, so it gets a hue — and it gets
 * one only while the state is true. `current` and `checking` render nothing, an
 * unanswerable question renders nothing, and the strip is dismissible, because
 * a bar that cannot be closed is a bar people learn to stop reading.
 *
 * It sits where the portal switch used to sit — between the app bar and the
 * transcript — and that space is empty again the moment the state clears.
 */

import { useState } from 'react';

import { Icon } from './Icon';
import { restartEngineNow, startEngineNow } from '../lib/engine/liveness';
import { hasNativeShell } from '../lib/engine/shell';
import { useEngineLiveness } from '../lib/useEngineLiveness';

export function EngineNotice() {
  const { state, dismissed, dismiss } = useEngineLiveness();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  /* Nothing to say, or nothing new to say. Renders no element at all rather
     than an empty one, so the layout is identical to before it existed. */
  if (state.kind === 'checking' || state.kind === 'current') return null;
  if (dismissed) return null;

  /**
   * A reload button appears only where reloading is the fix.
   *
   * `reload` (the engine refuses a token engine.json still publishes) and
   * `gone` are both states where a reload re-reads the same file and gets the
   * same answer. Offering the button there would be the fourth confident wrong
   * instruction in this incident's history; the sentence in `action` says what
   * actually has to happen instead.
   */
  const reloadWouldHelp = state.kind === 'restarted' || state.kind === 'rebuilt';

  /* AND WHERE RESTARTING IS THE FIX, A BUTTON THAT RESTARTS. `stale` is an
     engine on different code from this page and `published` is an engine that
     is not the one engine.json describes; in both the answer is the same act,
     and until now the sentence told the person to run it themselves. `gone`
     keeps `start`, because there is nothing to replace. */
  const restartWouldHelp = state.kind === 'stale' || state.kind === 'reload';

  async function restart() {
    if (busy) return;
    setBusy(true);
    setFailed(null);
    /* A successful restart reloads the window, so nothing after this runs. */
    const why = await restartEngineNow();
    if (why) {
      setFailed(why);
      setBusy(false);
    }
  }

  return (
    <div
      className="enginenotice"
      data-severity={state.severity}
      role="status"
      /* The whole evidence, for anyone who wants the fields and the pids. */
      title={`${state.detail}${state.action ? ` ${state.action}` : ''}`}
    >
      <Icon name={state.severity === 'notice' ? 'info' : 'alert'} size={13} />
      <span className="enginenotice__head">{state.headline}</span>
      <span className="enginenotice__detail">{state.detail}</span>
      {state.action ? (
        <span className="enginenotice__action">{state.action}</span>
      ) : null}
      {/* The owner's ask, verbatim: "a button inside the Harness app where I
          can just click and it starts the engine for me and restarts the app
          automatically." In the shell that is one invoke away, so a dead
          engine gets a real button, not an instruction. */}
      {state.kind === 'gone' && hasNativeShell() ? (
        <button
          type="button"
          className="enginenotice__btn"
          onClick={() => void startEngineNow()}
        >
          <Icon name="play" size={12} />
          Start the engine
        </button>
      ) : null}
      {restartWouldHelp && hasNativeShell() ? (
        <button
          type="button"
          className="enginenotice__btn"
          onClick={() => void restart()}
          disabled={busy}
          title="Stop the engine that is answering and start one on this build. Nothing else is touched."
        >
          <Icon name="refresh" size={12} />
          {busy ? 'Restarting…' : 'Restart the engine'}
        </button>
      ) : null}
      {failed ? (
        /* It did not start, and the reason is the only useful thing left to
           say. Never a reload: that would land on the same disagreement. */
        <span className="enginenotice__detail" role="alert">{failed}</span>
      ) : null}
      {reloadWouldHelp ? (
        <button
          type="button"
          className="enginenotice__btn"
          onClick={() => window.location.reload()}
        >
          <Icon name="refresh" size={12} />
          Reload
        </button>
      ) : null}
      <button
        type="button"
        className="enginenotice__close"
        onClick={dismiss}
        aria-label="Dismiss this notice"
        title="Dismiss. It comes back if the situation changes."
      >
        <Icon name="x" size={12} />
      </button>
    </div>
  );
}
