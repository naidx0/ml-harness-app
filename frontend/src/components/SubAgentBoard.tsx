/**
 * WHAT THE SUB-AGENTS ARE DOING, IN THE CHAT, AT FULL SIZE.
 *
 * Max, 2026-09-14: *"have sub-agents show up in the chat in a big section (not
 * a separate section) but just have it shown in a large way, to not pollute the
 * main screen around the chatbox - hence the small expandable goal tool."*
 *
 * The strip that used to live inside the goal card is gone. That card sits
 * directly above the chat box and everything in it is paid for twice: once in
 * the pixels and once in the attention of somebody who is trying to type. Two
 * sub-agent rows in there crowded the one thing that surface is for. So the
 * card keeps the counts and the controls, small and expandable, and the work
 * itself is drawn HERE - in the column, at the width of the conversation,
 * where there is room to say what each one is doing.
 *
 * IN THE CHAT AND NOT A SEPARATE SECTION. It is rendered as part of the
 * transcript's flow rather than as a pane or a drawer, so it scrolls with the
 * conversation it belongs to and moves up out of the way as the talk goes on.
 * When it has scrolled away the rail still carries the same fact, indented
 * under this conversation and in the same gold - which is the other half of
 * what he asked for and why neither surface needs to shout.
 *
 * COLOUR IS THE SAME EVERYWHERE. Gold is a sub-agent, here and in the rail and
 * on the card. Green finished, amber parked its way to the end, red failed.
 */

import { Icon } from './Icon';
import { endingInWords } from './SubAgentStrip';
import type { SubAgent, SubAgentRead } from '../lib/engine/subagents';

/** `18:04` from the engine's timestamp, local, or '' when it cannot be read.
 *
 *  Max, 2026-09-19: *"see like what time they returned, when they were
 *  prompted."* Both have been in the payload since the table was written -
 *  `started_at` and `updated_at` - and neither surface drew them, so the only
 *  answer to "when did this go out" was where the card sat in a list.
 *
 *  SQLite hands these back as `2026-09-19 18:04:33` with no zone, which `new
 *  Date()` reads as local on some engines and UTC on others. The engine writes
 *  them in UTC, so the `Z` is added when the string does not carry one - a
 *  time an hour out is worse than no time. */
function clock(stamp: string | null | undefined): string {
  if (!stamp) return '';
  const text = String(stamp).trim();
  const iso = /[zZ]|[+-]\d\d:?\d\d$/.test(text)
    ? text.replace(' ', 'T')
    : `${text.replace(' ', 'T')}Z`;
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return '';
  return when.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

/** `4m 12s`, and `48s` when a leading `0m` would be noise. */
function howLong(seconds: number | null): string {
  if (seconds === null || seconds < 0) return '';
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, '0')}s`;
}

/** The one line a person wants first: is anything still out, and how much of
 *  the work has come back. */
export function boardHeadline(read: SubAgentRead): string {
  const working = read.subagents.filter((one) => one.state === 'running').length;
  const back = read.subagents.length - working;
  if (working && back) {
    return `${working} working, ${back} back`;
  }
  if (working) return `${working} of ${read.at_most} working`;
  return back === 1 ? '1 phase came back' : `${back} phases came back`;
}

function Card({ one, onOpen, onStop, detailed }: {
  one: SubAgent;
  onOpen: (threadId: number) => void;
  onStop: (id: number) => void;
  detailed?: boolean;
}) {
  const share = one.steps ? Math.round((one.done / one.steps) * 100) : 0;
  const working = one.state === 'running';
  return (
    <li className="subcard" data-state={one.state}>
      <button
        type="button"
        className="subcard__open"
        onClick={() => onOpen(one.thread_id)}
        title={`${one.phase} — open this sub-agent's conversation and read what it did`}
      >
        <span className="subcard__head">
          <span className="subcard__dot" aria-hidden="true" />
          <span className="subcard__phase">{one.phase}</span>
          <span className="subcard__when num">
            {working ? howLong(one.seconds) : endingInWords(one)}
          </span>
        </span>

        {/* The steps it was given, which is the thing there was no room for in
            the strip. Ticked, parked, and the rest still to do. */}
        <span className="subcard__counts num">
          <span className="subcard__count" data-kind="done">
            {one.done} done
          </span>
          {one.parked.length ? (
            <span className="subcard__count" data-kind="parked">
              {one.parked.length} parked
            </span>
          ) : null}
          {one.open ? (
            <span className="subcard__count" data-kind="open">
              {one.open} to go
            </span>
          ) : null}
          {one.turns ? (
            <span className="subcard__count" data-kind="turns">
              {one.turns} turn{one.turns === 1 ? '' : 's'}
            </span>
          ) : null}
          {/* WHAT IT SPENT TO GET THERE. Steps ticked says how far it got;
              this says what it cost. A phase that burned nine turns on one
              lookup and a phase that ran twelve tools drew the same card. */}
          {one.tools_run ? (
            <span
              className="subcard__count"
              data-kind="tools"
              title={`${one.tools_distinct ?? 0} different tools${
                one.tools_failed ? `, ${one.tools_failed} refused` : ''
              }`}
            >
              {one.tools_run} tool{one.tools_run === 1 ? '' : 's'}
            </span>
          ) : null}
          {one.context_peak_tokens ? (
            <span
              className="subcard__count"
              data-kind="context"
              title="The widest this worker's prompt ever got"
            >
              {one.context_peak_tokens.toLocaleString()} tok
            </span>
          ) : null}
        </span>

        {/* WHEN IT WENT OUT AND WHEN IT CAME BACK, which the counts cannot
            say. A phase that took nine minutes at 02:00 and one that took
            nine minutes an hour ago are different facts about a run. */}
        {clock(one.started_at) ? (
          <span className="subcard__when-line num">
            <span>sent {clock(one.started_at)}</span>
            {working ? (
              <span className="subcard__still">still out</span>
            ) : clock(one.updated_at) ? (
              <span>back {clock(one.updated_at)}</span>
            ) : null}
            {one.seconds != null ? <span>{howLong(one.seconds)}</span> : null}
          </span>
        ) : null}

        <span className="subcard__bar" aria-hidden="true">
          <span className="subcard__fill" style={{ width: `${share}%` }} />
        </span>

        {detailed && one.packs && one.packs.length ? (
          <span className="subcard__packs" title="Packs this worker's turn loads">
            {one.packs.join(' · ')}
          </span>
        ) : null}

        {/* WHY A STEP WAS PARKED, in the sub-agent's own words. This is the
            only thing in the product that reads a child's reasons to the
            person, and it is the person's surface rather than the
            orchestrator's - the orchestrator gets counts and one line, which
            is the whole economy of delegation (app/subagents.py). */}
        {one.parked.length ? (
          <span className="subcard__parked">
            {one.parked.slice(0, 3).map((parked) => (
              <span key={parked.step} className="subcard__why" title={`${parked.step} — ${parked.why}`}>
                <Icon name="alert" size={11} />
                <b>{parked.step}</b>
                {parked.why}
              </span>
            ))}
            {one.parked.length > 3 ? (
              <span className="subcard__why subcard__why--more">
                and {one.parked.length - 3} more, in its own conversation
              </span>
            ) : null}
          </span>
        ) : null}

        {/* EXPANDED: what it was told, and every tool it ran. Max,
            2026-09-19: "the prompt the instructions that you gave them...
            what tools they ran collectively. Is it 85 tools used? And if you
            click expand, you can really view them all." */}
        {detailed && one.brief ? (
          <span className="subcard__brief">
            <span className="subcard__brieflabel">Its instructions</span>
            <span className="subcard__brieftext">{one.brief}</span>
          </span>
        ) : null}

        {detailed && one.tool_names && one.tool_names.length ? (
          <span className="subcard__tools">
            <span className="subcard__brieflabel">
              Tools it ran · {one.tools_run} call
              {one.tools_run === 1 ? '' : 's'} across {one.tools_distinct} tool
              {one.tools_distinct === 1 ? '' : 's'}
            </span>
            <span className="subcard__toollist">
              {one.tool_names.map((tool) => (
                <span key={tool.name} className="subcard__tool">
                  {tool.name}
                  {tool.times > 1 ? <b> ×{tool.times}</b> : null}
                </span>
              ))}
            </span>
          </span>
        ) : null}

        {detailed && one.last_digest ? (
          <span className="subcard__digest">{one.last_digest}</span>
        ) : null}
      </button>

      {working ? (
        <button
          type="button"
          className="subcard__stop"
          onClick={() => onStop(one.id)}
          title="Stop this sub-agent after the turn it is in"
        >
          <Icon name="stop" size={11} />
          Stop
        </button>
      ) : null}
    </li>
  );
}

export function SubAgentBoard({
  read,
  onOpen,
  onStop,
  detailed = false,
}: {
  read: SubAgentRead;
  onOpen: (threadId: number) => void;
  onStop: (id: number) => void;
  /** CS4 inspector: packs + last digest under each card. */
  detailed?: boolean;
}) {
  if (!read.subagents.length) return null;
  const working = read.subagents.filter((one) => one.state === 'running').length;

  return (
    <section
      className="subboard"
      data-working={working ? 'yes' : undefined}
      data-detailed={detailed || undefined}
      aria-label="Sub-agents working on this plan"
    >
      <header className="subboard__head">
        <span className="subboard__pips" aria-hidden="true">
          {Array.from({ length: read.at_most }, (_, index) => (
            <span
              key={index}
              className="subboard__pip"
              data-lit={index < working ? 'yes' : undefined}
            />
          ))}
        </span>
        <h2 className="subboard__title">Sub-agents</h2>
        <span className="subboard__count">{boardHeadline(read)}</span>
        {read.running_anywhere > working ? (
          <span className="subboard__elsewhere" title="Two at a time is the whole machine, not this conversation.">
            {read.running_anywhere - working} more in another chat
          </span>
        ) : null}
      </header>

      <ol className="subboard__list">
        {read.subagents.map((one) => (
          <Card
            key={one.id}
            one={one}
            onOpen={onOpen}
            onStop={onStop}
            detailed={detailed}
          />
        ))}
      </ol>
    </section>
  );
}
