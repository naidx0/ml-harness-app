/**
 * WHO ELSE IS WORKING ON THIS PLAN.
 *
 * Max, 2026-09-13: *"Create a creative way to view sub agents - see how many
 * are active, see the ones that are running. I like the Cursor mobile app...
 * use our blue colouring, maybe use yellow or red for sub-agents."*
 *
 * So: the orchestrator keeps the accent blue it has everywhere else, and a
 * sub-agent is GOLD. That is not decoration - it is the one thing a person has
 * to be able to tell apart at a glance in a window where several things claim
 * to be working: this conversation's own turn, and a phase being worked
 * somewhere else by something it sent out.
 *
 * ONE ROW PER SUB-AGENT, and each row says the four things there are to say:
 * which phase it was given, how much of it is done, how long it has been at
 * it, and whether it is still going. A working row carries a gold dot that
 * breathes and a bar that fills; a finished one carries its ending in words.
 * The row is a button and the button opens the child conversation, because the
 * transcript a person wants is over there - this strip will never show it,
 * which is the same rule the orchestrator works under.
 *
 * WHY IT IS NOT A LIST OF EVERYTHING. Two is the cap (`app/subagents.py`), so
 * this is at most two working rows plus what has come back. A surface that
 * scrolled would be a surface built for a fleet, and there is no fleet: there
 * is one small model and two turns in flight on one card.
 */

import { Icon } from './Icon';
import type { SubAgent, SubAgentRead } from '../lib/engine/subagents';

/** `4m 12s`, and `48s` when a leading `0m` would be noise. Same shape as the
 *  goal card's, because they sit one above the other. */
function howLong(seconds: number | null): string {
  if (seconds === null || seconds < 0) return '';
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, '0')}s`;
}

/** What a finished sub-agent's ending is called, in words a person reads.
 *  The engine's reasons are `plan_worked_down`, `parked_more_than_it_did` and
 *  the rest; a person should never see an identifier. */
export function endingInWords(one: SubAgent): string {
  if (one.state === 'running') return '';
  if (one.state === 'failed') return 'it failed';
  if (one.state === 'stopped') return 'stopped';
  if (one.parked.length && one.done === 0) return 'nothing could be done';
  if (one.parked.length) return `${one.done} done, ${one.parked.length} parked`;
  return `all ${one.done} done`;
}

export function SubAgentStrip({
  read,
  onOpen,
  onStop,
}: {
  read: SubAgentRead;
  /** Open the child conversation - where its transcript is. */
  onOpen: (threadId: number) => void;
  onStop: (id: number) => void;
}) {
  if (!read.subagents.length) return null;
  const working = read.subagents.filter((one) => one.state === 'running');

  return (
    <div className="subagents" data-working={working.length ? 'yes' : undefined}>
      <div className="subagents__head">
        <span className="subagents__dots" aria-hidden="true">
          {/* One pip per slot the machine has, filled while it is in use.
              It says the cap and the load in the same three pixels. */}
          {Array.from({ length: read.at_most }, (_, index) => (
            <span key={index} className="subagents__pip" data-lit={index < working.length ? 'yes' : undefined} />
          ))}
        </span>
        <span className="subagents__title">
          {working.length
            ? `${working.length} sub-agent${working.length === 1 ? '' : 's'} working`
            : 'sub-agents'}
        </span>
        {read.running_anywhere > working.length ? (
          <span className="subagents__elsewhere" title="The cap is on the machine, not on this conversation.">
            {read.running_anywhere - working.length} more in another chat
          </span>
        ) : null}
      </div>

      <ol className="subagents__list">
        {read.subagents.map((one) => {
          const share = one.steps ? Math.round((one.done / one.steps) * 100) : 0;
          const when = one.state === 'running' ? howLong(one.seconds) : endingInWords(one);
          return (
            <li key={one.id} className="subagent" data-state={one.state}>
              <button
                type="button"
                className="subagent__open"
                onClick={() => onOpen(one.thread_id)}
                /* The phase is first, because it is the half that clips.
                   Max, 2026-09-13, of every line in this card: "when you
                   hover you can actually see the whole extent of the text."

                   The TIME rides along because the row hides
                   `.subagent__when` in a card under 360px wide (shell.css),
                   and a hover has to be able to get it back. Phase first. */
                title={`${one.phase} — ${when} — open this sub-agent's conversation and read what it did`}
              >
                <span className="subagent__dot" aria-hidden="true" />
                <span className="subagent__phase">{one.phase}</span>
                <span className="subagent__count num">
                  {one.done} of {one.steps}
                </span>
                <span className="subagent__bar" aria-hidden="true">
                  <span className="subagent__fill" style={{ width: `${share}%` }} />
                </span>
                <span className="subagent__when num">{when}</span>
              </button>
              {one.state === 'running' ? (
                <button
                  type="button"
                  className="subagent__stop"
                  onClick={() => onStop(one.id)}
                  title="Stop this sub-agent after the turn it is in"
                >
                  <Icon name="stop" size={11} />
                </button>
              ) : null}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
