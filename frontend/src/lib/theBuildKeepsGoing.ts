/**
 * WHEN A BUILDING THREAD RUNS ANOTHER TURN WITHOUT BEING ASKED.
 *
 * Max, describing what pressing Build should do: *"we create a goal tool, which
 * basically just sets an autonomous loop running to kinda keep the model
 * working through the goal in detail. And the goal is obviously just massive,
 * like, markdown."*
 *
 * The loop needs no new engine road. `POST /api/threads/{id}/turn` already runs
 * a turn with no new message, so working down a plan is that call again - and
 * nothing fabricates a user message to make it happen. A transcript that shows
 * "continue" typed by a person who did not type it is a transcript that lies
 * about who asked for the next nine minutes of work.
 *
 * ## THE RULE FOR STOPPING, AND WHY IT IS THIS ONE
 *
 * **The open steps are the work. Nothing open, nothing to run.**
 *
 * The first rule here was about the SHAPE of a turn - one that called a tool
 * earned another, one that only spoke handed back. It read a proxy: acting
 * looks like work in progress and speaking looks like the model addressing
 * you. Both readings were wrong often enough to be felt. It stopped mid-plan
 * on narration between steps, which Max watched: *"it starts working and then
 * it kind of builds a part of it and stops"*. And it RAN on a plan with no
 * steps in it at all, because a tool had been called - twelve turns of
 * "working" over nothing, which he photographed on 2026-09-13: *"it keeps
 * parking things and saying it's working but in reality it's working 0
 * items."*
 *
 * So the plan's own `- [ ]` lines decide. An open step is work outstanding
 * and the loop runs; none open is the end of it, whether they were ticked or
 * parked; no step lines at all is a plan that cannot be worked down and the
 * bar says exactly that rather than pretending. Narration ends the loop in
 * one case only - the model asked the person something.
 *
 * The alternative considered was a completion marker the model writes when the
 * plan is finished. It was rejected for the reason `app/modes.py` gives about
 * deriving a mode: a loop whose stop condition is a phrase stops when a 7B
 * forgets the phrase, which is to say it does not stop. A ticked checkbox is
 * not a phrase; it is a line the plan file either has or does not.
 *
 * ## THE THREE THAT STOP IT REGARDLESS
 *
 * A CAP, because a loop with no ceiling is a bill. An APPROVAL, because the
 * whole point of a gate is that a person answers it - and autonomy, if the
 * person turned it on, has already removed the gates it covers by name
 * (`app/autonomy.py`), so anything still asking is something autonomy said no
 * to. And an ERROR, because a loop that retries a broken turn is a loop that
 * breaks it twelve more times.
 */

/** The part of a transcript row this module reads. Structural, so a test does
 *  not have to build a whole `TranscriptItem`. */
export interface Seen {
  kind: string;
  /** A tool row's result, read only for the one field below. */
  result?: unknown;
  /** An assistant row's words, read only to see whether it asked something. */
  text?: unknown;
}

/** THE CEILING. Twelve turns is roughly an hour of a local 7B working, which is
 *  long enough for a phase and short enough that a person who walked away
 *  comes back to a stopped thread rather than a spent one. It is a ceiling on
 *  CONSECUTIVE unattended turns: the count resets the moment a person speaks. */
export const MOST_TURNS_WITHOUT_A_PERSON = 12;

export interface WorkingDown {
  /** The thread's own column. Only `build` loops. */
  mode: string;
  /** The accepted plan. No plan, no loop - there is nothing to work down. */
  plan: string | null;
  /** The transcript, oldest first. */
  items: Seen[];
  /** True while a turn is in flight. The loop never stacks turns. */
  running: boolean;
  /** An approval is on screen waiting for a person. */
  awaitingApproval: boolean;
  /** The last turn failed. */
  failed: boolean;
  /** Consecutive turns this loop has run since a person last spoke. */
  taken: number;
  /** The person pressed stop. */
  stopped: boolean;
}

export interface Verdict {
  go: boolean;
  /** Shown in the UI beside the step count, so a loop that will not start
   *  says why rather than looking broken. */
  why: string;
}

/** Is a tool sitting on screen asking the person for a yes?
 *
 * The engine answers a gated call with `{error: 'approval_required'}` and the
 * transcript draws that row as a card with a button - `readApprovalRequest`
 * in `components/ApprovalCard.tsx` keys on the same field, and this reads it
 * the same way rather than inventing a second opinion about what an approval
 * looks like. Approving re-runs the tool and writes a fresh row, so only the
 * LAST tool row since the person spoke can still be waiting.
 */
export function anApprovalIsWaiting(items: Seen[]): boolean {
  for (let i = items.length - 1; i >= 0; i -= 1) {
    const item = items[i];
    if (item.kind === 'user') return false;
    if (item.kind !== 'tool') continue;
    const result = item.result;
    if (typeof result !== 'object' || result === null) return false;
    return (result as Record<string, unknown>).error === 'approval_required';
  }
  return false;
}

/** The plan's step lines, open, ticked and PARKED - a step the run could not
 *  do, written `- [!] ... — parked: why`. Mirrors `planning.steps_in`. */
export function stepsIn(plan: string | null): { open: number; done: number; parked: number } {
  let open = 0;
  let done = 0;
  let parked = 0;
  for (const line of (plan ?? '').split(/\r?\n/)) {
    const match = /^\s*[-*]\s+\[([ xX!])\]\s+\S/.exec(line);
    if (!match) continue;
    const mark = match[1].toLowerCase();
    if (mark === 'x') done += 1;
    else if (mark === '!') parked += 1;
    else open += 1;
  }
  return { open, done, parked };
}

/** The last assistant text of the current turn, or '' - for the one thing
 *  narration is allowed to stop the loop on: a question to the person. */
export function theLastThingItSaid(items: Seen[]): string {
  for (let i = items.length - 1; i >= 0; i -= 1) {
    const item = items[i];
    if (item.kind === 'user') return '';
    if (item.kind === 'assistant') return String((item as { text?: unknown }).text ?? '');
  }
  return '';
}

/** "Would you like me to proceed with that?" is not a question the person
 *  has to answer - they answered it by pressing Build. MEASURED 2026-09-12:
 *  the owner's model worked three of four steps and then asked exactly
 *  that, which the plain '?' rule would have treated as the end of the work.
 *  A question that asks anything ELSE - which column, which model, may it
 *  delete - still stops the loop. */
export function askedOnlyWhetherToGoOn(said: string): boolean {
  const last = said.trim().split(/(?<=[.!?])\s+/).pop() ?? '';
  if (!last.endsWith('?')) return false;
  const asksToGoOn =
    /\b(proceed|continue|go on|carry on|move on|next step|shall i|should i (proceed|continue|go|start)|would you like me to (proceed|continue|go|run|do that)|want me to (proceed|continue|go on))\b/i.test(
      last,
    );
  const asksSomethingElse = /\b(which|what|where|who|how many|how much|delete|remove|overwrite|spend|pay|rent)\b/i.test(last);
  return asksToGoOn && !asksSomethingElse;
}

export function shouldRunAnotherTurn(state: WorkingDown): Verdict {
  if (state.stopped) return { go: false, why: 'stopped' };
  if (state.mode !== 'build') return { go: false, why: 'planning' };
  if (!state.plan || !state.plan.trim()) return { go: false, why: 'no plan to work down' };
  if (state.running) return { go: false, why: 'a turn is running' };
  if (state.failed) return { go: false, why: 'the last turn failed' };
  if (state.awaitingApproval) return { go: false, why: 'waiting on your approval' };
  if (state.taken >= MOST_TURNS_WITHOUT_A_PERSON) {
    return { go: false, why: `stopped after ${MOST_TURNS_WITHOUT_A_PERSON} turns` };
  }
  /* THE BROWSER LOOP NEVER AUTO-CHAINS. Max, 2026-09-14: goal/todo is a skill
     for long-running work, not something Build entry invents. The durable path
     is `app/longrun.py` via "Run the plan"; Continue still spends one turn by
     hand. Returning go:false here is what stops the surprise autonomous turns
     while leaving the bar able to say how many steps remain. */
  const steps = stepsIn(state.plan);
  if (steps.open + steps.done + steps.parked > 0) {
    if (steps.open === 0 && steps.parked > 0) {
      return {
        go: false,
        why: `nothing left to work · ${steps.done} done, ${steps.parked} parked`,
      };
    }
    if (steps.open === 0) return { go: false, why: `every step is ticked (${steps.done})` };
    const said = theLastThingItSaid(state.items).trim();
    if (said.endsWith('?') && !askedOnlyWhetherToGoOn(said)) {
      return { go: false, why: 'it asked you something' };
    }
    return {
      go: false,
      why: `${steps.open} open · press Run the plan to work them down`,
    };
  }
  return { go: false, why: 'the plan has no steps to work down' };
}
