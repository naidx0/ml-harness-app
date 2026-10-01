/**
 * The transcript, folded out of the event log.
 *
 * THE EVENT LOG IS THE ONLY SOURCE. Not the `messages` table, not React state
 * that remembers what it sent. Everything on screen is built from rows that
 * `app/events.py append()` had already committed before they were streamed,
 * and that is what makes "the transcript is the artifact" and "the thread
 * survives a closed laptop" the same sentence.
 *
 * That the fold is *complete* is worth stating, because it is not obvious.
 * `app/conductor.py` writes the assistant's reply to the `messages` table as
 * `"".join(text_parts)` — the exact concatenation of the `chat.delta` payloads
 * it already committed. So replaying events from 0 reconstructs the assistant
 * turns character for character, and the client never has to reconcile two
 * sources that could disagree. Reading `GET /api/threads/{id}` as well would
 * introduce that disagreement for nothing.
 *
 * The fold is a pure function of an ordered event list, so re-running it after
 * a replay produces the same transcript. Duplicate ids are the caller's
 * problem to drop (see `useChat`), not this file's to tolerate.
 */

import type {
  ChatDeltaPayload,
  ChatErrorPayload,
  ConductorNoticePayload,
  ConductorVerdictNextStep,
  ConductorVerdictPayload,
  EngineEvent,
  SettledSentence,
  MessageCreatedPayload,
  StreamEndPayload,
  ToolCallPayload,
  ToolResultPayload,
  ToolCallingState,
  TurnStartedPayload,
} from './engine/types';

export type ToolState = 'running' | 'ok' | 'failed';

export interface UserItem {
  kind: 'user';
  key: string;
  id: number;
  text: string;
}

export interface AssistantItem {
  kind: 'assistant';
  key: string;
  id: number;
  text: string;
}

/** The last thing the model said, or `null` if it has not spoken yet.
 *
 *  This is what the Build control saves as the thread's plan, which is the
 *  honest reading of "click build plan": the plan is what was on screen when
 *  the person decided. It reads the RENDERED transcript rather than the
 *  database, for the same reason - what the person agreed to is what they
 *  were looking at. */
export function lastAssistantText(items: TranscriptItem[]): string | null {
  for (let i = items.length - 1; i >= 0; i -= 1) {
    const item = items[i];
    if (item.kind === 'assistant') {
      const text = (item as AssistantItem).text.trim();
      return text ? text : null;
    }
  }
  return null;
}

export interface TurnItem {
  kind: 'turn';
  key: string;
  id: number;
  provider: string;
  model: string;
  adapter: string;
  locality: string;
  toolCalling: ToolCallingState;
  /** Measured wall time for the turn, from `stream.end`. `null` until it
   *  arrives — never a guess and never a spinner pretending to be one. */
  seconds: number | null;
}

export interface ToolItem {
  kind: 'tool';
  key: string;
  id: number;
  callId: string;
  name: string;
  args: Record<string, unknown>;
  /** `"harness"` when the harness ran it because the model could not. */
  drivenBy: string | null;
  state: ToolState;
  result: unknown;
}

/** A line of a plan change, as `app/plandiff.py` writes it. `old` and `cur`
 *  are 1-based line numbers in the document that HAS the line - a deleted line
 *  has no `cur`, an added one has no `old`. */
export interface DiffRow {
  kind: 'ctx' | 'add' | 'del';
  old: number | null;
  cur: number | null;
  text: string;
}

export interface PlanChange {
  rows: DiffRow[];
  added: number;
  removed: number;
  /** Rows the engine cut to keep the event small. The plan file on disk is
   *  the whole truth; a capped diff that says it was capped is honest. */
  clipped: number;
}

export interface NoticeItem {
  kind: 'notice';
  key: string;
  id: number;
  text: string;
  reason: string;
  /** WHAT ACTUALLY CHANGED, when the notice is about a plan being written or a
   *  step moving. Max, 2026-09-14: "when the agent reads or writes anything and
   *  does any change, like adding to the plan, we should have that diff as an
   *  expandable feature." Absent on every other notice, which is why it is
   *  optional rather than an empty change. */
  diff?: PlanChange;
  /** AU2 — housekeeping (mode switch, blocks.changed, memory tick) draws as
   *  `.planline` rather than a blue info strip. Findings stay loud. */
  quiet?: boolean;
  /** ITEMS THAT ARE A LIST, DRAWN AS A LIST. `run.finished` joined seven
   *  parked steps - each one a full sentence with a tool call and its
   *  arguments in it - into one parenthesis, and Max photographed the result:
   *  "we're getting rid of this infinite kind of text thing". A count belongs
   *  in `reason`; the things counted belong here, one per line. */
  points?: string[];
}

/** The diff off an event payload, or undefined. Defensive because an event
 *  written by an older build has no `diff` at all, and a thread from before
 *  today is most of the event log. */
export function readPlanChange(payload: unknown): PlanChange | undefined {
  const diff = (payload as { diff?: unknown })?.diff as PlanChange | undefined;
  if (!diff || !Array.isArray(diff.rows) || diff.rows.length === 0) return undefined;
  return diff;
}

export interface ErrorItem {
  kind: 'error';
  key: string;
  id: number;
  detail: string;
}

/** CS5 — side effects of one turn, for the What-changed card. */
export interface EffectsItem {
  kind: 'effects';
  key: string;
  id: number;
  stepsDone: string[];
  stepsParked: { step: string; why: string }[];
  facts: { fact: string; origin: string; how: string; tool: string }[];
  files: string[];
  planWrites: number;
  canRevert: boolean;
}

/**
 * The engine's own verdict on the training decision, standing beside the reply
 * that settled it.
 *
 * BESIDE `NoticeItem` IN THE UNION AND NOT INSIDE IT. A notice is the harness
 * saying something happened to the reply — a sentence withheld, a preamble.
 * This is the harness's own answer, computed by `app/diagnosis.py` over this
 * thread's ledger, standing next to the model's. One row kind covering both
 * would be the transcript unable to say which of the two happened, and the
 * whole point of the event is that a reader can tell them apart.
 *
 * IT ARRIVES AFTER THE REPLY IT ANNOTATES. `run_turn` appends it once the
 * turn's sentences have all been read, so in the fold it sits below the
 * assistant row it is about — which is what "beside, not instead of" looks
 * like in a column.
 */
export interface VerdictItem {
  kind: 'verdict';
  key: string;
  id: number;
  /** The engine's half. */
  verdict: string | null;
  outcome: string | null;
  say: string | null;
  gates: string | null;
  nextSteps: ConductorVerdictNextStep[];
  computed: boolean;
  decidedBy: string;
  /** The reply's half, as the harness's reader read it. */
  asserted: string | null;
  agrees: boolean;
  sentences: SettledSentence[];
}

/**
 * Every `train.*` event for one job, collapsed to a single row.
 *
 * DESIGN_SYSTEM §9.1: "Heavy results never stream into the transcript…
 * Streaming raw training logs into the chat column is forbidden; it is the
 * single fastest way to destroy the calm the reference tools achieve." A
 * training run emits one `train.log` event per line, so this row counts them
 * and shows the last structured progress payload instead of printing any of
 * them.
 */
export interface TrainItem {
  kind: 'train';
  key: string;
  id: number;
  jobId: string;
  logLines: number;
  /** The most recent non-log `train.*` payload, e.g. `train.progress`. */
  latest: { kind: string; payload: Record<string, unknown> } | null;
}

/**
 * Every `storm.*` event for one storm, collapsed to a single row.
 *
 * The same rule the training row follows and for the same reason: a storm
 * emits `storm.declared`, `storm.started`, one `storm.step.started` and one
 * `storm.step.finished` per step, and `storm.finished` — a two-step build is
 * six rows of narration, and a ten-step one is twenty-two. DESIGN_SYSTEM §9.1:
 * "Heavy results never stream into the transcript."
 *
 * There is a second reason here that the training row does not have, and it is
 * the stronger one: **the proposal card is already showing every one of these
 * events, drawn as the plan.** The nodes carry the step states, the block under
 * them carries the storm's own state and its verification, and all of it comes
 * from the same log this row is folding. Printing the events beside the picture
 * would be the transcript arguing with the diagram about what happened.
 *
 * So the row is one line that says which storm and where it got to, and the
 * picture is where a person looks.
 */
export interface StormItem {
  kind: 'storm';
  key: string;
  id: number;
  stormId: number;
  /** How many of its own events have landed. Counted, never invented. */
  events: number;
  /** The last `storm.*` kind seen, without its namespace. */
  latest: string;
  /** `storm.finished`'s state when it has arrived, else null. */
  finishedAs: string | null;
}

/**
 * Every `eval.*` event for one run, collapsed to a single row.
 *
 * AN EVAL RUN IS A THING YOU WATCH AND THEN READ, and those are two different
 * surfaces. This is the watching half, and it is a run row (Graphite page 26)
 * rather than a card: it exists while the work is happening, it answers the
 * four questions page 26.1 says a run row answers — is it alive, is it
 * spending, is it going well, does it need me — and then the report card
 * arrives underneath it as the tool result and this row stops being the
 * interesting thing on screen.
 *
 * The same collapse rule as training and storms, and here the arithmetic is
 * worth writing down: `evals.py` emits one `eval.progress` every
 * `PROGRESS_STRIDE` = 25 rows, so the 200-row default sample is nine frames,
 * not two hundred. Nothing per-row is ever emitted — `evals.py` says so in its
 * own header, "the durable per-row record is `eval_results`" — so this row
 * cannot become a wall however long the run is.
 *
 * `graded` and `planned` are counted by the ENGINE and copied, never derived
 * from how many frames arrived. A progress bar that counts its own events
 * would read 100% the moment the stream hiccuped.
 */
export interface EvalItem {
  kind: 'eval';
  key: string;
  id: number;
  runId: number;
  /** From `eval.started`. Null until it lands — a reconnecting client can join
   *  a run mid-flight and sees progress before it sees the start. */
  evalPath: string | null;
  model: string | null;
  metric: string | null;
  /** True when this run is measuring the BASELINE — the thin default prompt.
   *  Null until `eval.started` says. */
  promptIsDefault: boolean | null;
  /** Rows graded and rows planned, both the engine's own counts. */
  graded: number;
  planned: number;
  /** Measured wall seconds from the last `eval.progress`. Never a guess. */
  seconds: number | null;
  /** `running` until a terminal frame arrives. `reused` means nothing was
   *  spent: the identical eval was already in this conversation. */
  state: 'running' | 'finished' | 'interrupted' | 'reused';
  /** `eval.finished`'s score. Null on every other state, including finished
   *  runs the engine scored as null. */
  score: number | null;
  /** `eval.interrupted`'s reason, verbatim. */
  why: string | null;
}

/** An event kind this client does not render specially. Named rather than
 *  dropped: a frame that vanishes is worse than one that looks plain. */
export interface UnknownItem {
  kind: 'unknown';
  key: string;
  id: number;
  eventKind: string;
}

/** A SUB-AGENT, IN THE CONVERSATION THAT SENT IT OUT.
 *
 * Max, 2026-09-19: *"throughout the actual chat, it shows sub agent open and
 * running, and you can see that instead of just the sub-agents on the
 * sidebar."* Four event kinds carried this and every one of them drew
 * nothing: `subagent.started`, `run.delegated`, `subagent.finished`,
 * `subagent.harvested`. The board above the composer knew; the transcript,
 * which is the thing with the times in it, did not - so a person reading back
 * could not tell WHEN a phase went out or what the conversation was doing
 * while it was gone.
 *
 * One row per event, in the order they happened, because the question this
 * answers is a question about time. The board stays the place for "what is
 * out right now"; this is "what happened, and when". */
export interface SubAgentItem {
  kind: 'subagent';
  key: string;
  id: number;
  /** `sent` | `back` | `folded` */
  event: 'sent' | 'back' | 'folded';
  phase: string;
  childThreadId: number | null;
  /** On `sent`: how many steps went with it. */
  steps: number | null;
  /** On `back`: done / stopped / failed, and why. */
  state: string;
  detail: string;
  /** On `back` and `folded`: what came home. */
  ticked: number | null;
  parked: number | null;
  unreached: number | null;
  /** On `sent`, from a run: the tools the phase names. */
  tools: string[];
}

export type TranscriptItem =
  | SubAgentItem
  | UserItem
  | AssistantItem
  | TurnItem
  | ToolItem
  | NoticeItem
  | VerdictItem
  | ErrorItem
  | EffectsItem
  | TrainItem
  | StormItem
  | EvalItem
  | UnknownItem;

/**
 * Kinds that carry no row of their own, and the reason each one is here.
 *
 * The `UnknownItem` fallback is deliberate - "a frame that vanishes is worse
 * than one that looks plain" - so silencing a kind is a decision that has to be
 * argued rather than a convenience. Two arguments cover this list.
 *
 * `stream.end` arrives once per turn and its only payload, the measured
 * duration, is already printed on the turn row it closes.
 *
 * The four `thread.*` kinds are facts about **where the thread lives**, not
 * about what the conversation did. Graphite page 20.4 enumerates what may enter
 * the transcript and none of them is on it; the rail is where a thread's home,
 * name and archive state are read. FOUND BY LOOKING: `thread.created` is
 * emitted for every thread and is scoped to that thread, so until this the
 * first row of every conversation in the product read "The engine sent a
 * thread.created event, which this surface has no row for yet."
 */
const SILENT: ReadonlySet<string> = new Set([
  'stream.end',
  'thread.created',
  'thread.renamed',
  'thread.archived',
  'thread.deleted',
  /* One reading per turn for the Context pane (app/contextwindow.py), and
     one row per turn of a run for the chip. Both are dashboards, not
     things that happened to the conversation. */
  'turn.context',
  'run.turn',
  'thread.plan',
  'thread.plan_adopted',
  'project.deleted',
  'thread.moved',
  /* The same argument as the four above: the goal is a fact about the
     thread, and it has a surface of its own — the line under the app bar,
     which is also where the person corrects it. A transcript row would be a
     second copy with no pencil on it. */
  'thread.goal_set',
  'turn.effects_reverted',
  /* The run's own word for the moment `subagent.started` already drew. Two
     rows for one hand-off is the noise, not the information. */
  'run.delegated',
  /* HOW A RESULT IS CARRIED IS NOT SOMETHING THAT HAPPENED. `observation
     .packed` says a large tool result now rides as a handle plus an excerpt -
     a fact about the context window, which is `turn.context`'s argument
     exactly, and the Context pane is where the window is read. It drew "The
     engine sent an observation.packed event, which this surface has no row
     for yet" eleven times in one of Max's runs, between rows that were about
     his data. The tool row above it already says what the tool answered. */
  'observation.packed',
]);

/** One step, short enough to read in a list.
 *
 *  A parked step carries its tool call and every argument - "Training itself,
 *  supervised, costed with `run_in_sandbox` - kind = train, config = lora_r=16,
 *  lora_alpha=32, lora_dropout=0.05, learning_rate=0.0002, max_seq_len=512,
 *  max_steps=20 (asks first)" is ONE of seven. The part before the first dash
 *  is the step; the rest is its arguments, which the plan itself still holds. */
function oneLine(step: string): string {
  const head = step.split(' - ')[0].trim() || step.trim();
  return head.length > 96 ? `${head.slice(0, 95)}…` : head;
}

export function foldEvents(events: readonly EngineEvent[]): TranscriptItem[] {
  const items: TranscriptItem[] = [];

  /** Index of the assistant row currently accepting deltas, or -1. */
  let openAssistant = -1;
  /** Index of the most recent turn row, so `stream.end` can time it. */
  let openTurn = -1;
  /** `${callId}\0${name}` -> index. Overwritten on every call, deleted when
   *  the result lands. Ollama numbers its calls `call_0`, `call_1` PER TURN,
   *  so ids repeat across a thread and a plain id map would attach turn 4's
   *  result to turn 1's call. */
  const pendingTools = new Map<string, number>();
  /** job_id -> index of its single collapsed row. */
  const trainRows = new Map<string, number>();
  /** storm id -> index of its single collapsed row. */
  const stormRows = new Map<number, number>();
  /** eval run id -> index of its single collapsed row. */
  const evalRows = new Map<number, number>();

  const closeAssistant = () => {
    openAssistant = -1;
  };

  for (const event of events) {
    const id = event.id;
    const kind = event.kind;

    if (kind === 'chat.delta') {
      const text = (event.payload as ChatDeltaPayload)?.text ?? '';
      if (!text) continue;
      if (openAssistant === -1) {
        items.push({ kind: 'assistant', key: `a${id}`, id, text });
        openAssistant = items.length - 1;
      } else {
        const row = items[openAssistant] as AssistantItem;
        row.text += text;
      }
      continue;
    }

    if (kind === 'stream.end') {
      closeAssistant();
      if (openTurn !== -1) {
        const turn = items[openTurn] as TurnItem;
        const seconds = (event.payload as StreamEndPayload)?.seconds;
        turn.seconds = typeof seconds === 'number' ? seconds : null;
      }
      continue;
    }

    closeAssistant();

    switch (kind) {
      case 'message.created': {
        const payload = event.payload as MessageCreatedPayload;
        if (payload?.role !== 'user') break;
        items.push({
          kind: 'user',
          key: `u${id}`,
          id,
          text: payload.content ?? '',
        });
        break;
      }

      case 'turn.started': {
        const payload = event.payload as TurnStartedPayload;
        items.push({
          kind: 'turn',
          key: `t${id}`,
          id,
          provider: payload?.provider ?? '',
          model: payload?.model ?? '',
          adapter: payload?.adapter ?? '',
          locality: payload?.locality ?? '',
          toolCalling: payload?.tool_calling ?? 'unknown',
          seconds: null,
        });
        openTurn = items.length - 1;
        break;
      }

      case 'turn.effects': {
        const payload = (event.payload ?? {}) as {
          steps_done?: string[];
          steps_parked?: { step?: string; why?: string }[];
          facts?: { fact?: string; origin?: string; how?: string; tool?: string }[];
          files?: string[];
          plan_writes?: number;
          can_revert?: boolean;
          empty?: boolean;
        };
        if (payload.empty) break;
        items.push({
          kind: 'effects',
          key: `fx${id}`,
          id,
          stepsDone: Array.isArray(payload.steps_done)
            ? payload.steps_done.filter((s): s is string => typeof s === 'string')
            : [],
          stepsParked: Array.isArray(payload.steps_parked)
            ? payload.steps_parked
                .filter((row) => row && typeof row.step === 'string')
                .map((row) => ({ step: String(row.step), why: String(row.why ?? '') }))
            : [],
          facts: Array.isArray(payload.facts)
            ? payload.facts
                .filter((row) => row && typeof row.fact === 'string')
                .map((row) => ({
                  fact: String(row.fact),
                  origin: String(row.origin ?? 'MEASURED'),
                  how: String(row.how ?? ''),
                  tool: String(row.tool ?? ''),
                }))
            : [],
          files: Array.isArray(payload.files)
            ? payload.files.filter((p): p is string => typeof p === 'string')
            : [],
          planWrites: Number(payload.plan_writes ?? 0),
          canRevert: Boolean(payload.can_revert),
        });
        break;
      }

      case 'conductor.notice': {
        const payload = event.payload as ConductorNoticePayload;
        items.push({
          kind: 'notice',
          key: `n${id}`,
          id,
          text: payload?.text ?? '',
          reason: payload?.reason ?? '',
        });
        break;
      }

      /* THE CAPABILITY BLOCKS THIS TURN RUNS UNDER, when and only when they
         move. `docs/PHASES.md`'s done-condition for Phase 1a is that the active
         block is visible "as a label rather than a choice", and this is the
         label: a strip that says what the harness loaded and why it loaded it,
         in the same register as every other number this product shows.

         NOT A CONTROL, DELIBERATELY. There is nothing here to click and there
         must not be - a person choosing their block is the tab bar this product
         exists to replace, asked politely. What a person does when the set is
         wrong is press the tool's own button, which is still on the screen
         because `REGISTRY.controls()` is not scoped.

         A `notice`, because that is exactly what it is and the row already
         exists: text plus the reason in dimmer type. A card of its own would be
         a bigger claim than the event makes. */
      /* THE PLAN LANDING. `write_plan` (or the prose capture) saved the
         thread's plan; the pane beside the chat has it. Max's transcript
         of 2026-09-12 printed "the engine sent a thread.plan_written event,
         which this surface has no row for yet" - so here is the row. */
      case 'thread.plan_written': {
        const payload = (event.payload ?? {}) as {
          phases?: number;
          characters?: number;
          source?: string;
          headings?: unknown[];
        };
        const phases = payload.phases ?? 0;
        const named = Array.isArray(payload.headings) ? payload.headings.filter((h) => typeof h === 'string') : [];
        items.push({
          kind: 'notice',
          key: `pw${id}`,
          id,
          quiet: true,
          diff: readPlanChange(event.payload),
          text: phases ? `Plan saved · ${phases} phase${phases === 1 ? '' : 's'}` : 'Plan saved',
          reason: [
            named.length ? named.join(' · ') : null,
            payload.characters
              ? `${payload.characters.toLocaleString()} characters${payload.source === 'prose' ? ' (from the reply)' : ''}`
              : null,
            'Open Plan in the side panel; switch to Build under the chat to run it.',
          ]
            .filter(Boolean)
            .join(' — '),
        });
        break;
      }
      case 'thread.step_done': {
        const payload = (event.payload ?? {}) as { step?: string; by?: string; open?: number; done?: number };
        items.push({
          kind: 'notice',
          key: `sd${id}`,
          id,
          diff: readPlanChange(event.payload),
          text: `Step ticked: ${payload.step ?? ''}`,
          reason: `${payload.done ?? 0} done, ${payload.open ?? 0} open${payload.by === 'harness' ? ' - ticked by the harness because the tool it names ran' : ''}.`,
        });
        break;
      }
      /* THE THREE MEMORY SYSTEMS, when they act. A compaction and a kept ask
         are things the harness did to the record; they are said in the same
         register as the tool list changing - a notice, not a card. */
      case 'thread.compacted': {
        const payload = (event.payload ?? {}) as {
          messages_summarised?: number;
          tokens_before?: number;
          tokens_after?: number;
          lines_dropped_by_the_sentry?: number;
          iteration?: number;
        };
        const dropped = payload.lines_dropped_by_the_sentry ?? 0;
        items.push({
          kind: 'notice',
          key: `c${id}`,
          id,
          quiet: true,
          text: `Earlier turns compacted into a checkpoint: ${payload.messages_summarised ?? 0} messages, ~${(
            payload.tokens_before ?? 0
          ).toLocaleString()} → ~${(payload.tokens_after ?? 0).toLocaleString()} tokens${
            (payload.iteration ?? 1) > 1 ? ` (update ${payload.iteration})` : ''
          }.`,
          reason: dropped
            ? `${dropped} line${dropped === 1 ? '' : 's'} the sentry read as an unmeasured figure were left out.`
            : 'Every message is still in the transcript and in recall; only what the model is sent is shorter.',
        });
        break;
      }
      case 'thread.compaction_failed': {
        const payload = (event.payload ?? {}) as { detail?: string };
        items.push({
          kind: 'notice',
          key: `cf${id}`,
          id,
          text: 'The transcript is over its share of the window and could not be compacted this turn.',
          reason: payload.detail ?? '',
        });
        break;
      }
      case 'thread.mode': {
        /* A mode is the person's choice, said once where they made it. */
        const payload = (event.payload ?? {}) as { mode?: string };
        const mode = payload.mode === 'plan' ? 'Plan' : 'Build';
        items.push({
          kind: 'notice',
          key: `md${id}`,
          id,
          quiet: true,
          text: `Switched to ${mode}.`,
          reason:
            mode === 'Plan'
              ? 'Lookups only; the reply is a plan. The saved plan stays where it is.'
              : 'Tools are offered as normal and the saved plan is worked down step by step.',
        });
        break;
      }
      case 'thread.permission': {
        /* THE AUTONOMY LADDER, and it is the person's choice in the same way
           the mode is. Until now this drew "The engine sent a
           thread.permission event, which this surface has no row for yet." on
           the FIRST line of every conversation started at anything but `ask` -
           Max, 2026-09-20, reading it at the top of his own run: "this is also
           very confusing i dont quite understand what this is runing for". */
        const payload = (event.payload ?? {}) as { permission?: string };
        const rung = String(payload.permission ?? '');
        const said =
          rung === 'full'
            ? 'Full'
            : rung === 'write'
              ? 'Write'
              : rung === 'measure'
                ? 'Measure'
                : 'Ask';
        items.push({
          kind: 'notice',
          key: `pm${id}`,
          id,
          quiet: true,
          text: `Approvals set to ${said}.`,
          reason:
            rung === 'full'
              ? 'Every gated tool runs without asking, except deleting a sandbox.'
              : rung === 'write'
                ? 'Tools that write into the workspace run without asking; the rest still ask.'
                : rung === 'measure'
                  ? 'Scoring and verification run without asking; the rest still ask.'
                  : 'Nothing gated runs without a click.',
        });
        break;
      }
      case 'run.started': {
        /* THE LONG RUN (app/longrun.py). Said once where it starts and once
           where it ends; every turn between is an ordinary turn and draws
           its own rows. */
        const payload = (event.payload ?? {}) as { open?: number; cap?: number };
        items.push({
          kind: 'notice',
          key: `rs${id}`,
          id,
          quiet: true,
          text: `Working the plan down: ${payload.open ?? 0} step${payload.open === 1 ? '' : 's'} to go.`,
          reason: `Up to ${payload.cap ?? 0} turns. It keeps going if you close this window, and stops on an approval, a failed connection, or the cap.`,
        });
        break;
      }
      case 'run.finished': {
        const payload = (event.payload ?? {}) as {
          reason?: string;
          detail?: string;
          turns?: number;
          done?: number;
          parked?: { step?: string; why?: string }[];
        };
        const parked = Array.isArray(payload.parked) ? payload.parked : [];
        items.push({
          kind: 'notice',
          key: `rf${id}`,
          id,
          text: `The run stopped: ${String(payload.detail || payload.reason || '').trim()}`,
          /* THE COUNT, AND ONLY THE COUNT. The seven step texts that used to
             be spliced in here are `points` now. */
          reason: `${payload.turns ?? 0} turn${payload.turns === 1 ? '' : 's'}, ${payload.done ?? 0} step${payload.done === 1 ? '' : 's'} ticked${
            parked.length ? `, ${parked.length} parked` : ''
          }.`,
          points: parked
            .map((one) => String(one?.step ?? '').trim())
            .filter((one) => one.length > 0)
            .map(oneLine),
        });
        break;
      }
      case 'thread.step_parked': {
        /* A step the run could not do, skipped rather than fatal - the
           "as far as it can" half of the loop. */
        const payload = (event.payload ?? {}) as { step?: string; why?: string };
        items.push({
          kind: 'notice',
          key: `sp${id}`,
          id,
          diff: readPlanChange(event.payload),
          text: `Parked: ${payload.step ?? 'a step'}`,
          reason: `${payload.why ?? ''} The run went on to the next step; the plan keeps the line as [!] so you can see what was skipped.`,
        });
        break;
      }
      case 'thread.plan_ready': {
        /* CS19 — quiet one-liner; details live in title / expand, not a blue Strip. */
        const payload = (event.payload ?? {}) as {
          phases?: number;
          headings?: unknown[];
          steps?: number;
          steps_open?: number;
          written_this_turn?: boolean;
        };
        const named = Array.isArray(payload.headings) ? payload.headings.filter((h) => typeof h === 'string') : [];
        const phases = payload.phases ?? named.length;
        const steps = payload.steps ?? 0;
        const open = payload.steps_open ?? 0;
        /* Prefer one notice when plan_written already landed this fold. */
        const already = items.some(
          (item) => item.kind === 'notice' && item.id < id && item.key.startsWith('pw'),
        );
        if (already && payload.written_this_turn) break;
        items.push({
          kind: 'notice',
          key: `pr${id}`,
          id,
          quiet: true,
          text: payload.written_this_turn
            ? phases
              ? `Plan saved · ${phases} phase${phases === 1 ? '' : 's'}`
              : 'Plan saved'
            : phases
              ? `Plan ready · ${phases} phase${phases === 1 ? '' : 's'}`
              : 'Plan ready',
          reason: [
            named.length ? named.join(' · ') : null,
            steps ? `${open} of ${steps} step${steps === 1 ? '' : 's'} open` : null,
            'Switch to Build under the chat to run it, or say what to change.',
          ]
            .filter(Boolean)
            .join(' — '),
        });
        break;
      }
      case 'memory.extracted': {
        /* What the harness kept after the turn (app/memory.extract_after_turn).
           A notice in the same register as the compaction row: something the
           harness did to the record, said once, with the entries. */
        const payload = (event.payload ?? {}) as { added?: unknown[]; skipped?: number; refused?: number };
        const added = Array.isArray(payload.added) ? payload.added : [];
        const facts = added
          .map((each) => {
            if (typeof each === 'string') return each;
            if (each && typeof each === 'object' && typeof (each as { fact?: unknown }).fact === 'string') {
              return (each as { fact: string }).fact;
            }
            return '';
          })
          .filter(Boolean);
        items.push({
          kind: 'notice',
          key: `me${id}`,
          id,
          quiet: true,
          text: `Kept ${facts.length} thing${facts.length === 1 ? '' : 's'} in memory from this turn.`,
          reason: facts.join(' § '),
        });
        break;
      }
      case 'memory.kept_by_the_harness': {
        const payload = (event.payload ?? {}) as { entry?: string };
        items.push({
          kind: 'notice',
          key: `mk${id}`,
          id,
          quiet: true,
          text: 'Kept in this project’s memory, in your words.',
          reason: payload.entry ?? '',
        });
        break;
      }
      /* THE FOUR SUB-AGENT EVENTS, as three rows. `run.delegated` and
         `subagent.started` are the same moment seen by the run and by the
         delegation machinery, so only one of them draws - the started one,
         which is the one that exists whether or not a run is driving. */
      case 'subagent.started': {
        const payload = (event.payload ?? {}) as {
          child_thread_id?: number;
          phase?: string;
          steps?: unknown;
        };
        items.push({
          kind: 'subagent',
          key: `sa${id}`,
          id,
          event: 'sent',
          phase: String(payload.phase ?? 'a phase'),
          childThreadId: payload.child_thread_id ?? null,
          steps: Array.isArray(payload.steps)
            ? payload.steps.length
            : typeof payload.steps === 'number'
              ? payload.steps
              : null,
          state: '',
          detail: '',
          ticked: null,
          parked: null,
          unreached: null,
          tools: [],
        });
        break;
      }
      case 'subagent.finished': {
        const payload = (event.payload ?? {}) as {
          child_thread_id?: number;
          phase?: string;
          state?: string;
          detail?: string;
          done?: number;
          parked?: number;
        };
        items.push({
          kind: 'subagent',
          key: `sa${id}`,
          id,
          event: 'back',
          phase: String(payload.phase ?? 'a phase'),
          childThreadId: payload.child_thread_id ?? null,
          steps: null,
          state: String(payload.state ?? ''),
          detail: String(payload.detail ?? ''),
          ticked: payload.done ?? null,
          parked: payload.parked ?? null,
          unreached: null,
          tools: [],
        });
        break;
      }
      case 'subagent.harvested': {
        const payload = (event.payload ?? {}) as {
          thread_id?: number;
          phase?: string;
          state?: string;
          detail?: string;
          ticked?: number;
          parked?: number;
          unreached?: number;
        };
        items.push({
          kind: 'subagent',
          key: `sa${id}`,
          id,
          event: 'folded',
          phase: String(payload.phase ?? 'a phase'),
          childThreadId: payload.thread_id ?? null,
          steps: null,
          state: String(payload.state ?? ''),
          detail: String(payload.detail ?? ''),
          ticked: payload.ticked ?? null,
          parked: payload.parked ?? null,
          unreached: payload.unreached ?? null,
          tools: [],
        });
        break;
      }
      case 'blocks.changed': {
        const payload = (event.payload ?? {}) as {
          added?: string[];
          removed?: string[];
          active?: string[];
          because?: Record<string, string>;
        };
        const added = payload.added ?? [];
        const removed = payload.removed ?? [];
        const moved = [
          added.length ? `loaded ${added.join(', ')}` : '',
          removed.length ? `unloaded ${removed.join(', ')}` : '',
        ]
          .filter(Boolean)
          .join('; ');
        /* The reason for ONE pack rather than all of them, and it is the one
           that just arrived. A strip listing five reasons is a paragraph, and
           the whole set with every reason is in `turn.started` for anybody
           reading the record rather than the conversation. */
        const first = added[0] ?? removed[0] ?? '';
        /* NOTHING MOVED, NOTHING SAID. The row used to print on every turn -
           "Tools for this thread: unchanged. Active: context, data, ledger,
           machine, measurement." - which is the pack machinery describing
           itself to a person who never asked for a pack. Max, 2026-09-19, of
           a thread that had done nothing yet: "this is also very confusing i
           dont quite understand what this is running for and whats
           happening?" When something DID move, that is a fact about the
           conversation and it says which way, in the product's words. The
           full set with every reason stays on `turn.started` for the
           Inspector. */
        if (!moved) break;
        items.push({
          kind: 'notice',
          key: `b${id}`,
          id,
          quiet: true,
          text: `Tools for this thread: ${moved}.`,
          reason: (payload.because ?? {})[first] ?? '',
        });
        break;
      }

      case 'conductor.verdict': {
        const payload = (event.payload ?? {}) as Partial<ConductorVerdictPayload>;
        /* Read field by field rather than spread, and every one of them
           defensively. The engine's shape is known, but a row folded out of a
           replayed log is data on disk from whatever version wrote it, and a
           card that renders `undefined` as a verdict is worse than one that
           renders nothing. */
        const text = (value: unknown): string | null =>
          typeof value === 'string' && value.trim() ? value : null;
        items.push({
          kind: 'verdict',
          key: `d${id}`,
          id,
          verdict: text(payload.verdict),
          outcome: text(payload.outcome),
          say: text(payload.say),
          gates: text(payload.gates),
          nextSteps: Array.isArray(payload.next_steps)
            ? payload.next_steps.flatMap((step) => {
                const tool = text((step as ConductorVerdictNextStep)?.tool);
                if (!tool) return [];
                return [
                  {
                    tool,
                    fact: text((step as ConductorVerdictNextStep)?.fact) ?? '',
                  },
                ];
              })
            : [],
          computed: payload.computed === true,
          decidedBy: text(payload.decided_by) ?? '',
          asserted: text(payload.asserted),
          agrees: payload.agrees === true,
          sentences: Array.isArray(payload.sentences)
            ? payload.sentences.flatMap((row) => {
                const sentence = text((row as SettledSentence)?.sentence);
                if (!sentence) return [];
                return [
                  {
                    verdict: text((row as SettledSentence)?.verdict) ?? '',
                    sentence,
                  },
                ];
              })
            : [],
        });
        break;
      }

      case 'chat.error': {
        const payload = event.payload as ChatErrorPayload;
        items.push({
          kind: 'error',
          key: `e${id}`,
          id,
          detail: payload?.detail ?? '',
        });
        break;
      }

      case 'tool.call': {
        const payload = event.payload as ToolCallPayload;
        items.push({
          kind: 'tool',
          key: `c${id}`,
          id,
          callId: String(payload?.id ?? ''),
          name: String(payload?.name ?? ''),
          args: (payload?.arguments as Record<string, unknown>) ?? {},
          drivenBy: payload?.driven_by ?? null,
          state: 'running',
          result: undefined,
        });
        pendingTools.set(
          `${payload?.id ?? ''}\0${payload?.name ?? ''}`,
          items.length - 1,
        );
        break;
      }

      case 'tool.result': {
        const payload = event.payload as ToolResultPayload;
        const slot = `${payload?.id ?? ''}\0${payload?.name ?? ''}`;
        const index = pendingTools.get(slot);
        if (index === undefined) break;
        pendingTools.delete(slot);
        const row = items[index] as ToolItem;
        row.state = payload?.ok ? 'ok' : 'failed';
        row.result = payload?.result;
        break;
      }

      default: {
        if (kind.startsWith('train.')) {
          const payload = (event.payload ?? {}) as Record<string, unknown>;
          const jobId = String(payload.job_id ?? 'unknown');
          let index = trainRows.get(jobId);
          if (index === undefined) {
            items.push({
              kind: 'train',
              key: `r${id}`,
              id,
              jobId,
              logLines: 0,
              latest: null,
            });
            index = items.length - 1;
            trainRows.set(jobId, index);
          }
          const row = items[index] as TrainItem;
          if (kind === 'train.log') row.logLines += 1;
          else row.latest = { kind: kind.slice('train.'.length), payload };
          break;
        }
        if (kind.startsWith('storm.')) {
          const payload = (event.payload ?? {}) as Record<string, unknown>;
          const stormId = Number(payload.storm ?? 0);
          let index = stormRows.get(stormId);
          if (index === undefined) {
            items.push({
              kind: 'storm',
              key: `s${id}`,
              id,
              stormId,
              events: 0,
              latest: '',
              finishedAs: null,
            });
            index = items.length - 1;
            stormRows.set(stormId, index);
          }
          const row = items[index] as StormItem;
          row.events += 1;
          row.latest = kind.slice('storm.'.length);
          if (kind === 'storm.finished') {
            row.finishedAs = String(payload.state ?? 'done');
          }
          break;
        }
        if (kind.startsWith('eval.')) {
          const payload = (event.payload ?? {}) as Record<string, unknown>;
          const runId = Number(payload.run_id ?? 0);
          let index = evalRows.get(runId);
          if (index === undefined) {
            items.push({
              kind: 'eval',
              key: `v${id}`,
              id,
              runId,
              evalPath: null,
              model: null,
              metric: null,
              promptIsDefault: null,
              graded: 0,
              planned: 0,
              seconds: null,
              state: 'running',
              score: null,
              why: null,
            });
            index = items.length - 1;
            evalRows.set(runId, index);
          }
          const row = items[index] as EvalItem;

          /* Every field is written only when the frame that owns it carries
             it. `eval.progress` has no `planned` on a resumed run and
             `eval.finished` has no `seconds`; a blanket spread would overwrite
             a real count with `undefined` and the row would lose the number it
             had already been told. */
          const number = (value: unknown): number | null =>
            typeof value === 'number' && Number.isFinite(value) ? value : null;

          if (kind === 'eval.started') {
            row.evalPath = typeof payload.eval_path === 'string' ? payload.eval_path : null;
            row.model = typeof payload.model === 'string' ? payload.model : null;
            row.metric = typeof payload.metric === 'string' ? payload.metric : null;
            row.promptIsDefault =
              typeof payload.prompt_is_default === 'boolean'
                ? payload.prompt_is_default
                : null;
            /* `already_graded` is what a RESUMED run starts from. Counting it
               is why a run continued after an interruption shows 120/200 when
               it restarts rather than 0/200 and a bar that appears to lose
               work the engine actually kept. */
            row.graded = number(payload.already_graded) ?? 0;
            row.planned = number(payload.planned) ?? 0;
          } else if (kind === 'eval.progress') {
            row.graded = number(payload.graded) ?? row.graded;
            row.planned = number(payload.planned) ?? row.planned;
            row.seconds = number(payload.seconds) ?? row.seconds;
          } else if (kind === 'eval.finished') {
            row.state = 'finished';
            row.graded = number(payload.graded) ?? row.graded;
            row.score = number(payload.score);
            row.metric = typeof payload.metric === 'string' ? payload.metric : row.metric;
            /* A finished run has graded everything it planned. Said by the
               engine's own count, not by setting graded = planned: a run that
               finished short is a fact worth being able to see. */
          } else if (kind === 'eval.interrupted') {
            row.state = 'interrupted';
            row.graded = number(payload.graded) ?? row.graded;
            row.why = typeof payload.why === 'string' ? payload.why : null;
          } else if (kind === 'eval.reused') {
            row.state = 'reused';
            const rows = number(payload.rows) ?? 0;
            row.graded = rows;
            /* A reused run spent nothing and graded nothing NOW. `planned`
               takes the same value so the row cannot draw a part-full bar over
               work that was already complete before this turn began. */
            row.planned = rows;
          }
          break;
        }
        if (SILENT.has(kind)) break;
        items.push({ kind: 'unknown', key: `x${id}`, id, eventKind: kind });
        break;
      }
    }
  }

  return items;
}
