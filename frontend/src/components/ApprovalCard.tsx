/**
 * THE MODEL ASKED TO DO SOMETHING THAT NEEDS A YES, AND THIS IS THE YES.
 *
 * ── THE GAP THIS CLOSES, MEASURED ──────────────────────────────────────────
 *
 * Fourteen registered tools declare `approval="always"`, and SIX of the
 * seventeen steps in the `train_on_my_files` journey are among them - carving
 * rows, deduplicating, splitting an eval set, synthesizing, making a sandbox,
 * running in it. When the model reaches one, `app/tools/registry.py` raises
 * `ApprovalRequired`, `app/conductor.py` turns that into
 * `{"ok": false, "error": "approval_required"}`, and the transcript drew a
 * failed row.
 *
 * Then nothing. `grep -rn approval_required frontend/src` returned ZERO hits
 * before this file existed. There was no way to say yes from the chat at all:
 * a person had to open Controls, find that tool among sixty-seven, retype
 * every argument the model had already composed, and press Run. A journey that
 * needs six of those is a journey nobody finishes.
 *
 * ── WHY IT IS A CARD AND NOT A CONFIRM() ───────────────────────────────────
 *
 * A person approves a THING, not a word: the arguments the model proposed are
 * shown, in full, as data rather than prose, because the whole risk of an
 * approval surface is somebody clicking yes to a sentence while a different
 * set of arguments runs. What is rendered here is `item.args` off the
 * `tool.call` event - the arguments that were actually sent - and the same
 * object is what the button submits.
 *
 * ── WHAT PRESSING IT DOES, AND WHY THAT DOOR ───────────────────────────────
 *
 * It runs the tool through `POST /api/tools/{name}` with `approved: true` and
 * the thread id - THE USER'S DOOR, which hard-codes `actor=USER`. So the run
 * is the person's own act, lands STATED where a fact is stated, and writes its
 * own `tool.call`/`tool.result` pair into this thread marked
 * `driven_by: "user"`, which the transcript already draws as "run by you". The
 * approval is therefore not a special case in the record: it is an ordinary
 * user-driven run that happens to have been proposed by the model.
 *
 * Nothing here re-sends the turn. The model sees the result on its next turn
 * the way it sees every other tool row, and a person who approves and then
 * says nothing has still moved the work forward - which is the point.
 */

import { useState } from 'react';
import type { ToolControl } from '../lib/engine/types';
import { Button } from './primitives';
import { Icon } from './Icon';
import { ResultView } from './ResultView';

/** The engine's refusal, or null. Keyed on the error code `conductor.py`
 *  writes, so no other failure can be mistaken for a request to approve. */
export function readApprovalRequest(result: unknown): { detail: string } | null {
  if (typeof result !== 'object' || result === null) return null;
  const row = result as Record<string, unknown>;
  if (row.error !== 'approval_required') return null;
  return { detail: typeof row.detail === 'string' ? row.detail : '' };
}

export function ApprovalCard({
  name,
  args,
  control,
  detail,
  onApprove,
}: {
  /** The tool the model tried to run. */
  name: string;
  /** The arguments it proposed - shown whole, and submitted unchanged. */
  args: Record<string, unknown>;
  /** Its registered spec, when the catalogue has it: the label and verb are
   *  the tool's own words, never a sentence composed here. */
  control: ToolControl | null;
  /** The engine's own refusal sentence. */
  detail: string;
  onApprove: (
    name: string,
    args: Record<string, unknown>,
  ) => Promise<{ ok: boolean; result: unknown; error: string | null }>;
}) {
  const [phase, setPhase] = useState<'asking' | 'running' | 'ran' | 'declined'>(
    'asking',
  );
  const [outcome, setOutcome] = useState<{
    ok: boolean;
    result: unknown;
    error: string | null;
  } | null>(null);

  async function approve() {
    setPhase('running');
    const answered = await onApprove(name, args);
    setOutcome(answered);
    setPhase('ran');
  }

  const entries = Object.entries(args ?? {});
  const headline = control?.verb
    ? control.verb.charAt(0).toUpperCase() + control.verb.slice(1)
    : 'Run ' + name;

  return (
    <section
      className="card card--approval"
      aria-label="A tool is waiting for your approval"
    >
      <div className="card__head">
        <Icon name="alert" size={14} />
        <span className="card__kicker">Waiting for you</span>
        <span className="card__headright mono">{name}</span>
      </div>

      {/* THE SWAP IS AUDIBLE. This card replaces its own contents as the
          approval moves through asking, running, ran and declined - "It ran.
          The result is below" appears where the buttons were - and a screen
          reader was told none of it, because replacing a node silently is
          silent. `polite` rather than `assertive`: it is news, not an alarm,
          and it must not cut across what is being read. */}
      <div className="card__body" aria-live="polite">
        <h3 className="card__headline">{headline}</h3>

        {/* The engine's sentence, verbatim. It says which tool and why it
            stopped; paraphrasing it here would be this surface inventing a
            reason on the engine's behalf. */}
        {detail ? <p className="card__text approval__why">{detail}</p> : null}

        {/* What is true, in full. These are the exact arguments the button
            submits - not a summary of them. */}
        {entries.length > 0 ? (
          <dl className="approval__args">
            {entries.map(([key, value]) => (
              <div className="approval__arg" key={key}>
                <dt className="mono">{key}</dt>
                <dd className="mono">
                  {typeof value === 'string' ? value : JSON.stringify(value)}
                </dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="card__text approval__why">
            It proposed no arguments &mdash; this tool takes none.
          </p>
        )}

        {phase === 'asking' || phase === 'running' ? (
          <div className="approval__actions">
            <Button
              kind="primary"
              small
              icon="run"
              onClick={() => void approve()}
              disabled={phase === 'running'}
            >
              {phase === 'running' ? 'Running…' : 'Run it'}
            </Button>
            <Button
              small
              onClick={() => setPhase('declined')}
              disabled={phase === 'running'}
            >
              Not now
            </Button>
            <span className="approval__lands">
              runs as you, and is recorded in this thread
            </span>
          </div>
        ) : null}

        {phase === 'declined' ? (
          <div className="approval__landed">
            <p className="approval__state">
              <Icon name="info" size={12} />
              <span>
                Nothing ran. Say what you want changed, or approve it after all.
              </span>
            </p>
            <div className="approval__actions">
              <Button small onClick={() => setPhase('asking')}>
                Approve it after all
              </Button>
            </div>
          </div>
        ) : null}

        {phase === 'ran' && outcome ? (
          <div className="approval__landed">
            <p
              className={
                'approval__state' + (outcome.ok ? '' : ' approval__state--failed')
              }
            >
              <Icon name={outcome.ok ? 'check' : 'alert'} size={12} />
              <span>
                {outcome.error
                  ? outcome.error
                  : outcome.ok
                    ? 'It ran. The result is below, and is on this thread.'
                    : 'It ran and refused; what it said is below.'}
              </span>
            </p>
            {outcome.result !== null && outcome.result !== undefined ? (
              <ResultView value={outcome.result} />
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}
