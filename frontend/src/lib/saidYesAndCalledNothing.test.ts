/** The three cases that must stay SILENT are the point of this file.
 *
 *  A banner that fires on a turn where nothing needed running is the product
 *  crying wolf on its own correct behaviour, and a warning that is usually
 *  wrong is one people learn to read past - worse than the silence it
 *  replaced. So case 1 (one turn is a conversation), case 6 (the harness's own
 *  script running a tool is not the model driving) and case 7 (a person's
 *  click is not either) matter as much as the cases that speak.
 *
 *  Case 6 in particular: `UNASSISTED_SCRIPT` runs `inspect_hardware` on the
 *  person's behalf, and reading that row as the model acting would silence the
 *  banner in exactly the state it exists for.
 *
 *  Finding and draft: ML BUILD, 2026-09-10, from the Windows Sandbox walk.
 */
import { describe, expect, it } from 'vitest';

import {
  ENOUGH_TURNS_TO_BE_A_PATTERN,
  saidYesAndCalledNothing,
} from './saidYesAndCalledNothing';
import type { ToolItem, TranscriptItem, TurnItem } from './transcript';

let next = 0;

function turn(
  toolCalling: TurnItem['toolCalling'],
  seconds: number | null = 1.5,
): TurnItem {
  next += 1;
  return {
    kind: 'turn',
    key: `turn-${next}`,
    id: next,
    provider: 'Ollama',
    model: 'qwen2.5:0.5b',
    adapter: 'ollama',
    locality: 'local',
    toolCalling,
    seconds,
  };
}

function tool(drivenBy: string | null): ToolItem {
  next += 1;
  return {
    kind: 'tool',
    key: `tool-${next}`,
    id: next,
    callId: `call_${next}`,
    name: 'inspect_hardware',
    args: {},
    drivenBy,
    state: 'ok',
    result: undefined,
  };
}

const read = (items: TranscriptItem[]) => saidYesAndCalledNothing(items);

describe('saidYesAndCalledNothing', () => {
  it('says nothing on the opening exchange', () => {
    expect(read([turn('yes')])).toBeNull();
  });

  it('speaks once the second tool-capable turn closes', () => {
    expect(read([turn('yes'), turn('yes')])).toEqual({ turns: 2, quiet: 2 });
  });

  it('carries the count so the sentence cannot invent one', () => {
    const said = read([turn('yes'), turn('yes'), turn('yes')]);
    expect(said?.turns).toBe(3);
  });

  it('reads the turn after a driven one on its own merits', () => {
    /* THIS CASE INVERTED, and it is the whole change. It used to assert null:
       one model-driven call anywhere bought silence for everything after it.
       The rehearsal showed what that costs - three driving turns and then
       prose on the decisive question, unremarked. Turn 1 drove a tool; turn 2
       did not, and turn 2 is the answer the person is reading. */
    expect(read([turn('yes'), tool(null), turn('yes')])).toEqual({
      turns: 2,
      quiet: 1,
    });
  });

  it('ignores a tool that belongs to no turn', () => {
    /* ALSO INVERTED. A `tool.call` arriving before any `turn.started` has no
       turn to be evidence about, and counting it against the three that follow
       is how the old reading silenced a whole thread on one row. */
    expect(read([tool(null), turn('yes'), turn('yes'), turn('yes')])).toEqual({
      turns: 3,
      quiet: 3,
    });
  });

  /* ── THE REHEARSAL, TURN BY TURN ────────────────────────────────────────
     `docs/readiness-rehearsal-2026-09-11.md`. A stranger drove four turns on
     `granite4-hermes` through the engine API. Turns 1, 2 and 3 each made a
     model-driven call - `map_the_ask`, then `profile_repository` and
     `profile_dataset`, then `map_the_ask` again. Turn 4 asked

         "Will that actually run on this machine?"

     which is the question `can_this_machine_train` answers to the tenth of a
     gigabyte, and got 5,831 characters of prose NAMING the tools it could
     have called, with zero calls.

     The banner stayed silent, because the model "had called a tool". That is
     the defect: the reading asked what the THREAD has ever done, and the
     thing worth saying is about THIS TURN. */
  it('speaks when the model drove three turns and then answered in prose', () => {
    const rehearsal: TranscriptItem[] = [
      turn('yes'), tool(null),
      turn('yes'), tool(null), tool(null),
      turn('yes'), tool(null),
      turn('yes'),
    ];
    expect(read(rehearsal)).toEqual({ turns: 4, quiet: 1 });
  });

  it('does not read the harness running its own script as the model', () => {
    // MUST STAY SILENT. `UNASSISTED_SCRIPT` runs `inspect_hardware` for the
    // person; reading it as the model acting would silence the banner in the
    // exact state it exists for.
    expect(read([turn('yes'), tool('harness'), turn('yes')])).toEqual({
      turns: 2,
      quiet: 2,
    });
  });

  it('does not read a person clicking a tool as the model', () => {
    expect(read([turn('yes'), tool('user'), turn('yes')])).toEqual({
      turns: 2,
      quiet: 2,
    });
  });

  it('stays out of the way when the probe said no', () => {
    // That banner already speaks, and two warnings about one thing is one
    // warning nobody finishes reading.
    expect(read([turn('no'), turn('no')])).toBeNull();
  });

  it('stays out of the way when the probe never answered', () => {
    expect(read([turn('unknown'), turn('unknown')])).toBeNull();
  });

  it('does not count a turn that is still streaming', () => {
    // `seconds` arrives with `stream.end`. Counting an open turn would make
    // the banner flicker into existence mid-reply and out of it again.
    expect(read([turn('yes'), turn('yes', null)])).toBeNull();
  });

  it('says nothing about an empty thread', () => {
    expect(read([])).toBeNull();
  });

  it('says nothing while the model is still calling tools', () => {
    /* THE SILENCE THAT MATTERS MOST now the reading is per-turn. The healthy
       thread is one whose last answer ran something, and a banner living there
       would be the product scolding itself for working. */
    expect(read([turn('yes'), tool(null), turn('yes'), tool(null)])).toBeNull();
  });

  it('stops speaking the moment the model calls something again', () => {
    /* The count is a RUN, not a tally. Two quiet answers followed by one that
       ran a tool is a model that started driving again, and the banner has to
       be able to leave as easily as it arrived - a warning that outlives the
       thing it warned about is one people learn to dismiss. */
    expect(read([turn('yes'), turn('yes'), turn('yes'), tool(null)])).toBeNull();
  });

  it('counts a turn once however many tools it called', () => {
    expect(
      read([turn('yes'), tool(null), tool(null), tool(null), turn('yes')]),
    ).toEqual({ turns: 2, quiet: 1 });
  });

  it('does not let the harness running a tool rescue a quiet turn', () => {
    /* The mirror of the silence above, and the reason `drivenBy` is read per
       turn rather than tallied per thread. `UNASSISTED_SCRIPT` running
       `inspect_hardware` on the person's behalf is the product working AROUND
       the model, not the model working - so the turn stays quiet and the
       banner still speaks. */
    expect(read([turn('yes'), tool(null), turn('yes'), tool('harness')])).toEqual({
      turns: 2,
      quiet: 1,
    });
  });

  it('states the floor once, so the sentence and the test read the same one', () => {
    expect(ENOUGH_TURNS_TO_BE_A_PATTERN).toBe(2);
  });
});
