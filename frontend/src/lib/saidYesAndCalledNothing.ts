/** The fourth state: the probe said the model CAN call tools, and on the turns
 *  that matter it has not.
 *
 *  ## The measurement, by ML BUILD
 *
 *  2026-09-10, Windows Sandbox, `qwen2.5:0.5b` over Ollama, nothing on the
 *  machine but the installer. The daemon reported `tool_calling: "yes"`, the
 *  probe recorded it with its provenance sentence, and the model then wrote a
 *  confident numbered plan that NAMED the harness's own tools in prose and
 *  called none of them. `tool_calls_json: null`. No gate paid, no fact
 *  measured, no verdict reached.
 *
 *  Composer warns on `'no'` and says something on `'unknown'`, and said nothing
 *  at all on `'yes'` - correct for what the PROBE knows and wrong for what the
 *  THREAD knows. The honest-looking case is the misleading one: a person who
 *  reads `yes` and then reads fluent prose has no signal that nothing ran.
 *
 *  ## Why it is about the turn and not the thread's history
 *
 *  The first version of this went quiet for the whole thread the moment ANY
 *  tool call was model-driven: "a model that has called a tool once is
 *  driving, and a later prose turn is that model choosing not to call one."
 *
 *  THE READINESS REHEARSAL KILLED THAT ARGUMENT
 *  (`docs/readiness-rehearsal-2026-09-11.md`). A stranger drove four turns.
 *  Turns 1-3 each made a model-driven call. Turn 4 asked "Will that actually
 *  run on this machine?" - the question `can_this_machine_train` answers to a
 *  tenth of a gigabyte - and got 5,831 characters of prose describing the
 *  tools it could have called, with zero calls. The banner stayed silent,
 *  because the model had "called a tool once".
 *
 *  A model that drove three turns and then answered the consequential question
 *  in prose is exactly the case somebody needs told. So the reading is about
 *  the turns that just happened: `quiet` counts the CONSECUTIVE most recent
 *  tool-capable turns in which the model called nothing.
 *
 *  ## Why not simply "this turn called nothing"
 *
 *  A turn with no tool calls is not a defect. Someone asks what a stage means,
 *  the model answers, nothing needed running. A banner firing there would be
 *  the product crying wolf on its own correct behaviour - and a warning that is
 *  usually wrong is one people learn to read past, which is worse than the
 *  silence it replaced.
 *
 *  Hence the floor stayed: `turns` counts the thread's CLOSED tool-capable
 *  turns and must reach `ENOUGH_TURNS_TO_BE_A_PATTERN` before anything is
 *  said. One exchange is a conversation. Two is a thread.
 */
import type { TranscriptItem } from './transcript';

/** What the banner needs to say a true sentence, or `null` when there is
 *  nothing to say. Never a bare boolean: the counts are IN the sentence, and a
 *  caller that had to recompute them could compute different ones. */
export interface SaidYesAndCalledNothing {
  /** Closed turns whose probe said the model can call tools. Always >= 2. */
  turns: number;
  /** How many of the MOST RECENT of those called nothing. Always >= 1.
   *
   *  This is the number the sentence is about. `turns` is the context that
   *  makes it worth saying; `quiet` is what is happening now. */
  quiet: number;
}

/** Two closed turns is the floor. Below it, prose is a conversation. */
export const ENOUGH_TURNS_TO_BE_A_PATTERN = 2;

/** A tool call the MODEL drove.
 *
 *  THE ABSENCE IS THE SIGNAL, and it is the fragile part of this reading.
 *  `conductor.py` stamps `driven_by: "harness"` on the calls its own
 *  unassisted script makes; `main.py` stamps `"user"` when a person clicks one
 *  through `/api/tools`; the model's own calls carry no such key, and
 *  `transcript.ts` folds that to `null`.
 *
 *  Anything that starts stamping `driven_by` on a model call - for logging,
 *  for a badge, for symmetry - inverts this line and the banner goes quiet
 *  forever with nobody noticing.
 *  `tests/test_a_model_call_is_known_by_the_absence_of_a_driver.py` fails
 *  loudly the day that happens, against the conductor's own emission rather
 *  than a fixture. */
function theModelDroveIt(item: TranscriptItem): boolean {
  return item.kind === 'tool' && item.drivenBy === null;
}

/** `seconds` arrives from `stream.end`, so a turn that has it is a turn that
 *  CLOSED. A turn still streaming has not yet had its chance to call anything,
 *  and counting it would make the banner flicker into existence mid-reply and
 *  out of it again. */
function aClosedToolCapableTurn(item: TranscriptItem): boolean {
  return item.kind === 'turn' && item.toolCalling === 'yes' && item.seconds !== null;
}

export function saidYesAndCalledNothing(
  items: readonly TranscriptItem[],
): SaidYesAndCalledNothing | null {
  /* Tools belong to the turn they follow. The transcript is chronological, so
     walking it once and attaching each model-driven call to the turn most
     recently opened is the whole of the grouping - no ids to join on, and
     nothing that breaks when a turn carries several calls. */
  const calledSomething: boolean[] = [];
  for (const item of items) {
    if (aClosedToolCapableTurn(item)) {
      calledSomething.push(false);
    } else if (theModelDroveIt(item) && calledSomething.length > 0) {
      calledSomething[calledSomething.length - 1] = true;
    }
  }

  const turns = calledSomething.length;
  if (turns < ENOUGH_TURNS_TO_BE_A_PATTERN) return null;

  let quiet = 0;
  for (let at = calledSomething.length - 1; at >= 0 && !calledSomething[at]; at -= 1) {
    quiet += 1;
  }
  return quiet >= 1 ? { turns, quiet } : null;
}
