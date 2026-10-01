/**
 * The honest next step — a control that closes the gate, not a paragraph.
 *
 * "A gate blocked because its fact is only asserted gets the honest next step
 * as a chip that runs the tool that would measure it, not a paragraph telling
 * the user to go away."
 *
 * Graphite page 23.4 is the same instruction from the design side: "Prose that
 * says 'you should probably try retrieval first' hands the work back to the
 * person who came here because they did not know how to do it. A row of
 * controls that each *begin* that work says the same thing and then does it."
 * And page 23.3's fourth ledger state — "a gate the person could close in five
 * minutes… carries the attention dot and a button that starts it, right there
 * in the row".
 *
 * ══ WHERE THE TOOL COMES FROM ══════════════════════════════════════════════
 *
 * Nowhere in this file. `app/tools/evidence.py resolves()` derives it from the
 * registry's own `measures=` declarations and says why in as many words: "a
 * tool added next year that measures `corpus_tokens` becomes the answer to a
 * challenge on `corpus_tokens` on the day it is registered, with nothing here
 * to update". The engine sends the answer on `unsubstantiated[].next_step`;
 * this renders it. There is no list of tools here and there must never be one.
 *
 * ══ THE TWO DOORS, AND WHY THIS ONE IS THE USER'S ══════════════════════════
 *
 * `POST /api/tools/{name}` hard-codes `actor=USER`. A person pressed a button
 * in their own application, so what they supply is STATED — their own word,
 * which is what opens a `source: ask` gate. The conductor's door passes
 * `model`, and the same facts through it are ASSERTED. `app/main.py`: "Two
 * doors, two words, neither of them reachable from the message."
 *
 * THAT MAKES ONE THING FORBIDDEN HERE, and it is the reason the form below is
 * empty rather than convenient: **a value a model asserted is never pre-filled
 * into a control the user submits.** Doing that would take the model's claim,
 * push it through the user's door, and hand it back stamped STATED — a
 * one-click laundering of exactly the origin the engine just spent a wall
 * refusing. The claim is shown BESIDE the field, wearing its ASSERTED tag, as
 * context the person can disagree with. They type their own answer or they do
 * not answer.
 *
 * The same rule is why `run_diagnosis` is re-run with an empty fact sheet. The
 * facts already measured in this thread are merged in by the engine; nothing
 * the model said is resubmitted through the user's door.
 */

import { useState } from 'react';
import type { FactUsed, NextStep } from '../lib/engine/facts';
import { isFactOrigin } from '../lib/engine/facts';
import type { ToolControl, ToolField } from '../lib/engine/types';
import { Button, OriginTag } from './primitives';
import { Icon } from './Icon';

/** What the shell hands down: run one tool through the user's door. */
export type RunTool = (
  name: string,
  args: Record<string, unknown>,
  threadId: number | null,
) => Promise<{ ok: boolean; result: unknown; error: string | null }>;

type Phase = 'closed' | 'form' | 'running' | 'done';

export function NextStepControl({
  step,
  claimed,
  control,
  threadId,
  runTool,
}: {
  step: NextStep;
  /** What somebody claimed for this fact, if anything. Shown, never used. */
  claimed: FactUsed | undefined;
  /** The tool's own declaration from `GET /api/tools`, when the catalogue has
   *  loaded. Its `fields` are the SAME JSON Schema the model is given, so the
   *  form cannot drift from the tool. */
  control: ToolControl | null;
  threadId: number | null;
  runTool: RunTool;
}) {
  const [phase, setPhase] = useState<Phase>('closed');
  const [values, setValues] = useState<Record<string, string>>({});
  const [outcome, setOutcome] = useState<{
    ok: boolean;
    error: string | null;
    result: unknown;
  } | null>(null);

  /* No tool measures this fact yet. The engine says so itself and calls it a
     gap in the product; that sentence is the whole answer and there is no
     button to draw. */
  if (!step.tool) {
    return (
      <p className="nextstep__none">
        <Icon name="info" size={12} />
        <span>{step.note ?? 'Nothing in this harness measures this yet.'}</span>
      </p>
    );
  }

  const required = (control?.fields ?? []).filter((field) => field.required);
  const label = sentence(step.verb);

  async function run() {
    setPhase('running');
    const args: Record<string, unknown> = {};
    for (const field of required) {
      const typed = coerce(field, values[field.name] ?? '');
      /* An OBJECT argument on a step that names a fact is keyed by that fact.
         `state_facts` takes `facts: {name: value}` and the step already says
         which name, so the person answers one question instead of writing
         JSON. Derived from the step and the schema, not from the tool's name —
         nothing in this file knows what any particular tool does, which is the
         property that stops the control face and the model face drifting. */
      args[field.name] =
        field.type === 'object' && step.fact
          ? { [step.fact]: scalar(values[field.name] ?? '') }
          : typed;
    }
    const answer = await runTool(step.tool as string, args, threadId);
    setOutcome(answer);
    setPhase('done');
  }

  return (
    <div className="nextstep" data-phase={phase}>
      <div className="nextstep__row">
        <Button
          icon={step.run_as === 'user' ? 'user' : 'run'}
          small
          onClick={() => {
            /* A tool with no required argument runs on the click. One with
               required arguments opens the smallest form that can fill them —
               still a control that starts the work, never a page of advice. */
            if (required.length === 0) void run();
            else setPhase(phase === 'form' ? 'closed' : 'form');
          }}
          disabled={phase === 'running'}
        >
          {label}
        </Button>
        <span className="nextstep__tool mono">{step.tool}</span>
        {step.run_as === 'user' ? (
          <span className="nextstep__door" title="Facts you record here count as STATED — your own word. The same facts from a model count as ASSERTED and open nothing.">
            in your own person
          </span>
        ) : null}
      </div>

      {step.also?.length ? (
        <p className="nextstep__also">
          also measured by <span className="mono">{step.also.join(', ')}</span>
        </p>
      ) : null}

      {phase === 'form' ? (
        <div className="nextstep__form">
          {claimed ? <Claimed fact={step.fact} claimed={claimed} /> : null}
          {required.map((field) => (
            <label className="nextstep__field" key={field.name}>
              <span className="nextstep__label mono">{field.name}</span>
              <input
                className="input"
                value={values[field.name] ?? ''}
                placeholder={field.description}
                onChange={(event) =>
                  setValues((current) => ({ ...current, [field.name]: event.target.value }))
                }
              />
            </label>
          ))}
          <div className="nextstep__actions">
            <Button
              kind="primary"
              small
              onClick={() => void run()}
              disabled={required.some((field) => !(values[field.name] ?? '').trim())}
            >
              Run it
            </Button>
            <Button kind="quiet" small onClick={() => setPhase('closed')}>
              Cancel
            </Button>
          </div>
        </div>
      ) : null}

      {phase === 'running' ? (
        <p className="nextstep__state">
          <span
            className="dot"
            data-shape="filled-pulse"
            style={{ ['--st-colour' as string]: 'var(--st-active)' }}
          />
          Running <span className="mono">{step.tool}</span> on this machine.
        </p>
      ) : null}

      {phase === 'done' && outcome ? <Outcome outcome={outcome} /> : null}
    </div>
  );
}

/**
 * What was claimed, shown beside the empty field rather than inside it.
 *
 * This is the credulity test. The number is real — a model did say it — so it
 * is not hidden, and it is not an error, so nothing here is red. It wears its
 * origin and sits in --ink-3, which is what "neither alarmed nor credulous"
 * looks like at 11px.
 */
function Claimed({ fact, claimed }: { fact: string; claimed: FactUsed }) {
  return (
    <p className="nextstep__claimed">
      <span className="mono">{fact}</span> was given as{' '}
      <span className="mono nextstep__claimedvalue">{String(claimed.value)}</span>
      {isFactOrigin(claimed.origin) ? <OriginTag origin={claimed.origin} /> : null}
      <span className="nextstep__how">{claimed.how}</span>
    </p>
  );
}

function Outcome({
  outcome,
}: {
  outcome: { ok: boolean; error: string | null; result: unknown };
}) {
  if (outcome.error) {
    return (
      <p className="nextstep__state nextstep__state--failed">
        <Icon name="alert" size={12} />
        <span>{outcome.error}</span>
      </p>
    );
  }

  /* The tool's OWN sentence, first and always. `measure_eval_set` writes
     "Counted 1,204 rows in eval.jsonl. eval_size_n is now measured rather than
     claimed; run the diagnosis again and G0 will be asked on the count." No
     summary this surface could compose would be better, and one it composed
     would be a second claim about a measurement it did not take. */
  const detail = readDetail(outcome.result);
  const recorded = readRecorded(outcome.result);

  return (
    <div className="nextstep__minted">
      <p className={`nextstep__state${outcome.ok ? '' : ' nextstep__state--failed'}`}>
        <Icon name={outcome.ok ? 'check' : 'alert'} size={12} />
        <span>
          {detail ??
            (outcome.ok
              ? 'The tool ran and reported nothing to record.'
              : 'The tool refused, and sent no reason this surface can read.')}
        </span>
      </p>

      {/* Every row wears the origin the ENGINE gave it. `state_facts` records
          at the caller's own worth, so a row that came back STATED renders
          STATED — hard-coding MEASURED here would have been the very defect
          this card exists to prevent, arriving through the back of the same
          component. */}
      {recorded.map((row) => (
        <p className="nextstep__state" key={row.fact}>
          <span className="mono">{row.fact}</span>
          <span className="mono">{String(row.value)}</span>
          {isFactOrigin(row.origin) ? <OriginTag origin={row.origin} /> : null}
          {row.note ? <span className="nextstep__how">{row.note}</span> : null}
        </p>
      ))}
    </div>
  );
}

/* ── reading a tool result, narrowly ──────────────────────────────────────── */

interface Recorded {
  fact: string;
  value: unknown;
  origin: string;
  note: string;
}

/**
 * The fact rows a tool says it wrote, each carrying its own origin.
 *
 * `state_facts` returns `recorded`, and the origin on each row is what the
 * CALLER was worth — STATED through the user's door, ASSERTED through the
 * model's. Nothing here assumes which; the row says.
 *
 * The measuring tools return no such list. Their `summary` sentence is the
 * whole answer and is rendered above, so this returning empty is the normal
 * case rather than a failure to find something.
 */
function readRecorded(result: unknown): Recorded[] {
  if (typeof result !== 'object' || result === null) return [];
  const list = (result as Record<string, unknown>).recorded;
  if (!Array.isArray(list)) return [];
  const out: Recorded[] = [];
  for (const entry of list) {
    if (typeof entry !== 'object' || entry === null) continue;
    const row = entry as Record<string, unknown>;
    if (typeof row.fact !== 'string') continue;
    out.push({
      fact: row.fact,
      value: row.value,
      origin: typeof row.origin === 'string' ? row.origin : '',
      /* `if_not` is the engine's sentence for a fact that was recorded and
         still cannot open its gate. Shown, because a row that says STATED and
         nothing else would read as success. */
      note: typeof row.if_not === 'string' ? row.if_not : '',
    });
  }
  return out;
}

function readDetail(result: unknown): string | null {
  if (typeof result !== 'object' || result === null) return null;
  const record = result as Record<string, unknown>;
  for (const key of ['summary', 'detail', 'help', 'error']) {
    if (typeof record[key] === 'string' && record[key]) return record[key] as string;
  }
  return null;
}

/* ── small helpers ────────────────────────────────────────────────────────── */

/**
 * A schema field's value, coerced by the type the SCHEMA declares — the same
 * schema the model is handed, so a control and a tool call cannot disagree
 * about what an argument is. An unparseable number goes through as the string
 * the person typed, so the engine's own validation error is what they read
 * rather than a silent zero.
 */
function coerce(field: ToolField, raw: string): unknown {
  const text = raw.trim();
  if (field.type === 'integer' || field.type === 'number') {
    const parsed = Number(text);
    return Number.isFinite(parsed) ? parsed : text;
  }
  if (field.type === 'boolean') return text.toLowerCase() === 'true' || text === '1';
  return text;
}

/**
 * One value the person typed, read as what they wrote.
 *
 * Used only for the object-keyed case, where the type belongs to the FACT and
 * the fact ledger lives in the engine — this surface has no copy of it and must
 * not grow one. `true`/`false` and a plain number are read as themselves;
 * anything else goes through as the string, so `app/diagnosis.py`'s own
 * coercion error is what the person reads rather than a value this file
 * guessed at.
 */
function scalar(raw: string): unknown {
  const text = raw.trim();
  if (/^(true|yes)$/i.test(text)) return true;
  if (/^(false|no)$/i.test(text)) return false;
  if (text !== '' && Number.isFinite(Number(text))) return Number(text);
  return text;
}

/** The registry's verbs are imperative and lower case; a control starts with a
 *  capital. */
function sentence(verb: string): string {
  if (!verb) return 'Run it';
  return verb.charAt(0).toUpperCase() + verb.slice(1);
}
