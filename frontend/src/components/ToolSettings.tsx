/**
 * WHAT THIS PROJECT HANDS THE MODEL, AND WHAT IT COSTS.
 *
 * Max, 2026-09-14: *"add some UI components which lets you configure the tools
 * - like how many sub-agents you want to be using, if any at all, often or not
 * often, and so on, with skills as well."* And, about the same problem in the
 * same breath: *"make sure the models aren't clouded with too many tools and
 * guidelines so that they can have free roam in the computer."*
 *
 * ## Why every row carries a number
 *
 * MEASURED on his database before this was built: one thread sent the model
 * 26,367 tokens of harness furniture against 3,562 tokens of conversation -
 * 88% of the prompt was this product talking, of which 12,735 was tool schemas
 * for 44 tools. A switch with no number beside it asks a person to guess; a
 * switch that says "13 tools, 4,020 tokens" is a decision they can make. The
 * engine counts those with the same budget that bills a real turn, so the
 * number is what actually leaves the window rather than a second estimate.
 *
 * ## What is deliberately not here
 *
 * No "how often" for sub-agents. He asked for it and there is nothing honest
 * to put behind it: the harness does not choose how often to delegate, a model
 * does, turn by turn, from the plan in front of it. A dial that pretended to
 * influence that would be a placebo with a number on it. The cap is real
 * because it is enforced at the door, and zero is the strongest "not often"
 * that can actually be kept.
 */

import { useEffect, useState } from 'react';

import { Icon } from './Icon';
import {
  readProjectSettings,
  writeProjectSettings,
  type PackSetting,
  type ProjectSettings,
} from '../lib/engine/client';

export function ToolSettings({ projectId }: { projectId: number | null }) {
  const [state, setState] = useState<ProjectSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (projectId === null) return;
    let alive = true;
    readProjectSettings(projectId)
      .then((next) => alive && setState(next))
      .catch((reason) => alive && setError(String(reason)));
    return () => {
      alive = false;
    };
  }, [projectId]);

  if (projectId === null) {
    return (
      <p className="set__note">
        Open a conversation first — these are a project&rsquo;s settings, not
        the app&rsquo;s, because a machine that runs one sub-agent at a time has
        decided that for the work rather than for one chat.
      </p>
    );
  }
  if (error) return <p className="set__note">{error}</p>;
  if (!state) return <p className="set__note">Reading this project&rsquo;s settings…</p>;

  const save = async (change: { subagents_max?: number; packs_off?: string[] }) => {
    setBusy(true);
    try {
      const next = await writeProjectSettings(projectId, change);
      /* The engine's answer, not the optimistic guess: it clamps the cap and
         sorts the packs, and a surface that kept its own version would drift
         from what the turn actually runs under. */
      setState((was) => (was ? { ...was, ...next } : was));
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  };

  /* ONE SOURCE FOR "IS THIS PACK OFF", AND IT IS `packs_off`. The rows carry
     an `off` of their own from the read, and the WRITE answers with the cap
     and the list but no rows - so merging the answer left every row's flag at
     whatever it was when the panel opened. The switch appeared to do nothing.
     Two fields that must agree is the drift machine at the smallest possible
     scale; the list is the fact and the row is a view of it. */
  const isOff = (pack: PackSetting) => state.packs_off.includes(pack.name);
  const on = state.packs.filter((one) => !isOff(one));
  const spent = on.reduce((sum, one) => sum + one.tokens, 0);
  const offered = on.reduce((sum, one) => sum + one.tools, 0);

  return (
    <div className="toolset">
      <section className="toolset__block">
        <h3 className="dialog__h3">Sub-agents</h3>
        <p className="set__note">
          How many phases this project may have worked in parallel. Each one is
          its own conversation with the whole toolset, in this project&rsquo;s
          folder. <b>None</b> turns delegation off: the tool refuses and says so
          rather than starting one quietly.
        </p>
        <div className="toolset__choices" role="group" aria-label="Sub-agents at once">
          {Array.from({ length: state.most_subagents + 1 }, (_, n) => (
            <button
              key={n}
              type="button"
              className="toolset__choice"
              aria-pressed={state.subagents_max === n}
              disabled={busy}
              onClick={() => void save({ subagents_max: n })}
            >
              {n === 0 ? 'None' : n}
            </button>
          ))}
        </div>
      </section>

      <section className="toolset__block">
        <h3 className="dialog__h3">Tools on the prompt</h3>
        <p className="set__note">
          Every pack you leave on is sent with <em>every</em> turn, as JSON, on
          top of the conversation. What it costs is measured with the same
          budget that bills a real turn.{' '}
          <b className="num">
            {offered} tools, {spent.toLocaleString()} tokens
          </b>{' '}
          at the moment.
        </p>
        <ul className="toolset__packs">
          {state.packs.map((pack) => (
            <li className="toolset__pack" key={pack.name} data-off={isOff(pack) || undefined}>
              <button
                type="button"
                className="toolset__switch"
                role="switch"
                aria-checked={!isOff(pack)}
                aria-label={`Offer the ${pack.name} pack`}
                disabled={busy || pack.core}
                title={
                  pack.core
                    ? 'The core is on every turn. Without it a turn cannot write a plan or tick a step, so switching it off would make the model mute rather than free.'
                    : isOff(pack)
                      ? `Offer ${pack.name} again`
                      : `Stop offering ${pack.name} — ${pack.tokens.toLocaleString()} tokens back`
                }
                onClick={() =>
                  void save({
                    packs_off: isOff(pack)
                      ? state.packs_off.filter((name) => name !== pack.name)
                      : [...state.packs_off, pack.name],
                  })
                }
              >
                <Icon name={isOff(pack) ? 'x' : 'check'} size={11} />
              </button>
              <span className="toolset__name">{pack.name}</span>
              {pack.core ? <span className="toolset__core">core</span> : null}
              <span className="toolset__cost num">
                {pack.tools} tools · {pack.tokens.toLocaleString()}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
