/**
 * The journey overview's one read: `GET /api/threads/{id}/journey` —
 * `app/journey.py::build`.
 *
 * A reader of what the thread already did, never a writer, which is the same
 * law the Stage is under and for the same reason: a surface that wrote would
 * file rows into the conversation it is showing you.
 *
 * Field names are the engine's own (snake_case), kept verbatim at the
 * boundary. Every state here is a claim about the record — `done` means a tool
 * left a result, `done_elsewhere` means the facts are on the ledger from
 * another tool — and a renamed field is one more place for the claim and the
 * evidence to drift apart.
 */

import { engineJson } from './client';

/** What answered for a step: the tool's own event, or the fact ledger. */
export type StepEvidence = 'event' | 'ledger' | null;

export type StepState = 'done' | 'done_elsewhere' | 'not_needed' | 'next' | 'ahead';

/** A value the harness already measured, offered into the step's form. `from`
 *  is shown beside the field: a filled box with no account of where it came
 *  from is indistinguishable from a guess. */
export interface Prefilled {
  /** A scalar for most fields; an OBJECT for a tool whose parameter is one —
   *  `run_in_sandbox.config` is the training config, and the form writes it as
   *  JSON because that is what the tool's own schema declares. */
  value: string | number | boolean | Record<string, unknown>;
  from: string;
}

/** The newest refused run of this step's tool, while the step is still not
 *  done. `detail` is the tool's OWN sentence, which in this product is written
 *  as a remedy rather than as a complaint. */
export interface Attempted {
  at: string | null;
  error: string | null;
  detail: string | null;
}

/** Whether this step can be a click. `needs` names what is still missing, so
 *  a control can ask for it by name instead of opening a form. */
export interface Readiness {
  mode: 'click' | 'approve' | 'needs';
  missing: string[];
}

export interface JourneyStep {
  ordinal: number;
  tool: string;
  why: string;
  args_hint: string;
  needs_approval: boolean;
  /** Field name to the value the record already holds for it. Only fields the
   *  tool's own schema declares; empty when the thread knows nothing yet. */
  prefill: Record<string, Prefilled>;
  readiness: Readiness;
  state: StepState;
  /** For `not_needed`: the later step whose success made this one moot. */
  unnecessary_because: string | null;
  attempted: Attempted | null;
  evidence: StepEvidence;
  ran_at: string | null;
  driven_by: string | null;
  /** The tool's own summary line, when it ran here. Never re-derived. */
  produced: string | null;
  /** Present only for `done_elsewhere`: which tool met this step's purpose,
   *  and which facts of the step's own `measures` it stamped. */
  satisfied_by: { tool: string | null; facts: string[] } | null;
}

export interface JourneyNext {
  ordinal: number;
  tool: string;
  why: string;
  args_hint: string;
  needs_approval: boolean;
  readiness: Readiness;
}

/** What came out the other end. Read off the thread's own runs with the same
 *  `evals.compare` the Stage uses — never recomputed here. Null until an
 *  adapter has been scored against the baseline. */
export interface JourneyOutcome {
  adapter_run_id: number;
  baseline_run_id: number;
  score: number | null;
  baseline_score: number | null;
  delta: number | null;
  improved: number | null;
  regressed: number | null;
  paired_rows: number | null;
  p_value: number | null;
  verdict: string | null;
  resolved: boolean | null;
  rows_that_would_resolve_this_delta: number | null;
  says: string | null;
}

/** The ledger's own answer for this thread, and the gates it stands on.
 *  `trains` is the engine's reading of the `TRAIN__` prefix, computed once
 *  there so no reader has to know that rule to tell the two answers apart. */
/** The rule that stopped the route, the values it read, and where they came
 *  from. `unmeasured` is the commonest case and the one a bare verdict hides:
 *  the rule is not false, it is unanswered. */
export interface BlockedBy {
  gate: string;
  /** Whether the engine actually evaluated this gate. False means the route
   *  stopped before it, so the rule shown is the one that comes first rather
   *  than one that failed - a distinction the screen must keep, because "not
   *  checked" and "checked and false" call for different next moves. */
  reached: boolean;
  /** How many of the five gates reached a verdict, and out of how many. The
   *  denominator travels with the number so "3 passed" can never be read as
   *  "3 of 3". */
  checked: number;
  of: number;
  /** Set when the applicable rule depends on a method class the run has not
   *  chosen (G2 and G3 have no `any` row). `clause` is empty in that case;
   *  the screen says the class is undecided rather than quoting one. */
  class_undecided: boolean;
  clause: string;
  reads: Array<{
    fact: string;
    value: unknown;
    origin: string | null;
    how: string | null;
    unmeasured: boolean;
  }>;
}

export interface JourneyVerdict {
  outcome: string;
  trains: boolean;
  blocked_by: BlockedBy | null;
  say: string;
  gates_passed: number;
  gates_total: number;
}

export interface JourneyPayload {
  thread_id: number;
  /** null when this conversation has no goal, and therefore no route. */
  journey: string | null;
  /** `recorded` when the thread carries it, `matched` when it was read out of
   *  the goal's own words by the playbook's keyword match. */
  journey_origin: 'recorded' | 'matched' | null;
  matched_on: string[];
  says: string | null;
  steps: JourneyStep[];
  total: number;
  done_n: number;
  next: JourneyNext | null;
  /** The first step that can actually be pressed, which is not always the
   *  first one nobody has done. See `app/journey.py`. */
  next_runnable: JourneyNext | null;
  outcome: JourneyOutcome | null;
  verdict: JourneyVerdict | null;
  journeys_available: string[];
  say: string;
}

export function getJourney(threadId: number): Promise<JourneyPayload> {
  return engineJson<JourneyPayload>(`/api/threads/${threadId}/journey`);
}

/** Put this thread on a named route. The goal is untouched: it is the
 *  person's own words and a menu pick is not those. */
export function chooseJourney(threadId: number, journey: string): Promise<unknown> {
  return engineJson(`/api/threads/${threadId}/journey`, {
    method: 'POST',
    body: JSON.stringify({ journey }),
  });
}
