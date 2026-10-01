/**
 * THE CONTEXT WINDOW, BROKEN DOWN INTO THE PIECES THE PROMPT WAS BUILT FROM.
 *
 * Max, 2026-09-13: *"we need a context window showcase for ML Harness"*, and
 * then, with Claude Code's popup beside it: *"can we show the breakdown
 * behind token and context spend... it's an amazing and transparent
 * breakdown."*
 *
 * Every figure here was counted on a prompt that was sent. The conductor
 * names the pieces it assembles a prompt FROM - the instruction set, the six
 * notes, the standing brief, the tool schemas by pack, the conversation -
 * and counts each one with the same `providers/budget.py` both adapters use
 * to decide whether a turn fits (`app/contextwindow.py::parts`). A breakdown
 * of a string that has already been concatenated would be a guess; this is a
 * measurement of the parts themselves.
 *
 * WHAT IT IS FOR. This product's own instruction set and tool schemas cost
 * more than a small model's whole window - over 20,000 tokens on the owner's
 * machine, measured. That is not a thing to discover when a turn is refused.
 */

import { useEffect, useState } from 'react';

import {
  compactThread,
  readContextWindow,
  type ContextTurn,
  type ContextWindowRead,
} from '../lib/engine/client';
import { Icon } from './Icon';
import { Button } from './primitives';

/** Eight bands, assigned in the order the engine sorted the parts - biggest
 *  first - so the largest spend always carries the strongest colour. */
const BANDS = 8;

function thousands(n: number | null | undefined): string {
  return typeof n === 'number' ? n.toLocaleString() : '—';
}

/** "63.6%", or an em dash when there is no window to be a share of. */
function share(tokens: number, window: number | null): string {
  if (!window) return '—';
  const percent = (tokens / window) * 100;
  return `${percent >= 10 ? percent.toFixed(0) : percent.toFixed(1)}%`;
}

function Breakdown({ latest, window }: { latest: ContextTurn; window: number | null }) {
  const parts = latest.parts ?? [];
  const free = window ? Math.max(0, window - latest.total) : 0;
  const rows = parts.map((part, index) => ({ ...part, band: index % BANDS }));

  return (
    <>
      {/* One bar, a segment per part, free space last. Widths against the
          WINDOW when there is one, so the empty part of the bar is the room
          that is left rather than a rescaling of what was spent. */}
      <div
        className="ctxbar"
        role="img"
        aria-label={`${latest.total} tokens${window ? ` of ${window}` : ''}`}
      >
        {rows.map((part) => (
          <span
            key={part.key}
            className="ctxbar__part"
            data-band={part.band}
            style={{ width: `${((part.tokens / (window || latest.total)) * 100).toFixed(2)}%` }}
            title={`${part.label}: ${thousands(part.tokens)} tokens`}
          />
        ))}
      </div>

      <div className="ctxrows">
        {rows.map((part) => (
          <div className="ctxrow" key={part.key}>
            <span className="ctxrow__dot" data-band={part.band} aria-hidden="true" />
            <span className="ctxrow__label">{part.label}</span>
            <span className="ctxrow__why">{part.why}</span>
            <span className="ctxrow__n num">{thousands(part.tokens)}</span>
            <span className="ctxrow__pc num">{share(part.tokens, window)}</span>
          </div>
        ))}
        {window ? (
          <div className="ctxrow ctxrow--free">
            <span className="ctxrow__dot ctxrow__dot--free" aria-hidden="true" />
            <span className="ctxrow__label">Free space</span>
            <span className="ctxrow__why">room left in this model's window</span>
            <span className="ctxrow__n num">{thousands(free)}</span>
            <span className="ctxrow__pc num">{share(free, window)}</span>
          </div>
        ) : null}
      </div>
    </>
  );
}

export function ContextPane({ threadId, tick }: { threadId: number | null; tick: number }) {
  const [read, setRead] = useState<ContextWindowRead | null>(null);
  const [failed, setFailed] = useState(false);
  const [compacting, setCompacting] = useState(false);
  const [compactNote, setCompactNote] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    if (threadId === null) {
      setRead(null);
      return;
    }
    let live = true;
    readContextWindow(threadId)
      .then((got) => {
        if (live) {
          setRead(got);
          setFailed(false);
        }
      })
      .catch(() => {
        if (live) setFailed(true);
      });
    return () => {
      live = false;
    };
    /* Re-read when the thread moves, not on a timer: a reading is written
       once per turn, and `tick` is the thread's own last event id. */
  }, [threadId, tick, refresh]);

  async function onCompact() {
    if (threadId === null || compacting) return;
    setCompacting(true);
    setCompactNote(null);
    try {
      const result = await compactThread(threadId);
      if (!result.ok) {
        setCompactNote(result.detail || 'nothing to compact');
      } else {
        setCompactNote(
          `Compacted · ${thousands(result.messages_summarised)} messages · ${thousands(result.tokens_before)} → ${thousands(result.tokens_after)} tokens`,
        );
        setRefresh((n) => n + 1);
      }
    } catch (failure) {
      setCompactNote(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setCompacting(false);
    }
  }

  if (threadId === null) {
    return <p className="pane__empty">Open a conversation to see what its turns cost.</p>;
  }
  if (failed) {
    return (
      <p className="pane__empty">
        The engine did not answer when this pane asked what the last turn cost.
      </p>
    );
  }
  if (!read) return <p className="pane__empty">Reading…</p>;

  const latest = read.latest;
  if (!latest) {
    return (
      <p className="pane__empty">
        No turn has been sent in this conversation yet, so nothing has been counted. Every prompt is
        measured the moment it is assembled, and this pane is those measurements.
      </p>
    );
  }

  const window = read.window ?? null;
  const over = window !== null && latest.total > window;

  return (
    <div className="ctxpane">
      <div className="ctxpane__head">
        <span className="ctxpane__total num">{thousands(latest.total)}</span>
        <span className="ctxpane__of">
          tokens on the last prompt
          {window ? (
            <>
              {' '}
              of {thousands(window)} · <b>{share(latest.total, window)}</b> used
            </>
          ) : null}
        </span>
        <Button small onClick={() => void onCompact()} disabled={compacting}>
          {compacting ? 'Compacting…' : 'Compact'}
        </Button>
      </div>
      {compactNote ? <p className="ctxpane__line ctxpane__line--quiet">{compactNote}</p> : null}

      <Breakdown latest={latest} window={window} />

      {over ? (
        <p className="ctxpane__line">
          <Icon name="alert" size={12} /> Over the window by{' '}
          <b className="num">{thousands(latest.total - window!)}</b> tokens. A turn this size is
          refused before a byte is sent.
        </p>
      ) : null}

      {/* WHICH TOOLS THOSE SCHEMAS WERE. The line below counts them; without
          this one a person reading "9 tool schemas" on a harness with 88 tools
          would reasonably conclude the harness has nine. Every withheld tool is
          still named in the prompt and still callable - `blocks.on_the_wire`
          withholds the parameters, never the tool - so this says so. */}
      {latest.schemas_on_wire && latest.schemas_on_wire.withheld.length ? (
        <p className="ctxpane__line ctxpane__line--quiet">
          {latest.schemas_on_wire.withheld.length} more tool
          {latest.schemas_on_wire.withheld.length === 1 ? ' was' : 's were'} active and named in
          the prompt without {latest.schemas_on_wire.withheld.length === 1 ? 'its' : 'their'}{' '}
          parameters. The model can still call{' '}
          {latest.schemas_on_wire.withheld.length === 1 ? 'it' : 'them'}, and naming one puts its
          schema in the room next turn.
        </p>
      ) : null}

      <p className="ctxpane__line ctxpane__line--quiet">
        {latest.messages} message{latest.messages === 1 ? '' : 's'} · {latest.tool_count} tool
        {latest.tool_count === 1 ? ' schema' : ' schemas'} sent · {latest.mode} mode ·{' '}
        {read.model || 'no model'}
        {window ? (
          <>
            {' '}
            · the transcript is summarised past {thousands(read.compaction_at)} tokens
          </>
        ) : null}
      </p>

      {read.turns.length > 1 ? (
        <div className="ctxhistory">
          <h3 className="pane__h3">What each turn cost</h3>
          {/* Oldest at the left, against the WINDOW when the model has a
              measured one: a row of full-height bars would say "every turn is
              the same size" where the honest reading is "every turn is a
              sixth of what fits". Without a window there is nothing to be a
              share of, and the tallest turn sets the scale instead. */}
          <div className="ctxspark">
            {read.turns.map((turn) => {
              const against = window || Math.max(...read.turns.map((each) => each.total)) || 1;
              return (
                <span
                  key={turn.event_id}
                  className="ctxspark__bar"
                  data-over={window && turn.total > window ? 'yes' : undefined}
                  style={{ height: `${Math.min(100, Math.max(4, (turn.total / against) * 100)).toFixed(1)}%` }}
                  title={`${thousands(turn.total)} tokens${
                    window ? ` · ${share(turn.total, window)} of the window` : ''
                  }`}
                />
              );
            })}
          </div>
        </div>
      ) : null}

      {read.compactions.length ? (
        <div className="ctxhistory">
          <h3 className="pane__h3">Compactions</h3>
          {read.compactions.map((each) => (
            <p className="ctxpane__line" key={each.event_id}>
              <b className="num">{thousands(each.messages_summarised)}</b> messages summarised ·{' '}
              <span className="num">{thousands(each.tokens_before)}</span> →{' '}
              <span className="num">{thousands(each.tokens_after)}</span> tokens
            </p>
          ))}
        </div>
      ) : (
        <p className="ctxpane__line ctxpane__line--quiet">
          Nothing has been compacted in this conversation yet.
        </p>
      )}
    </div>
  );
}
