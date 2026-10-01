/**
 * Every tool is also a control — VISION.md, and the reason this panel exists.
 *
 * "The harness works by calling the same operations a person could click. That
 * is what makes the product survive a user whose local model cannot do tool
 * calling — the buttons are all still there."
 *
 * So this panel has NO list of tools in it. It renders whatever
 * `GET /api/tools` returns, and every form field is built from the same JSON
 * Schema the model is handed. Adding a tool to the registry adds a button
 * here; changing a parameter changes this form. There is no second
 * declaration to keep in step, which is the only version of this promise that
 * survives contact with a year of changes.
 *
 * TWO HONEST EDGES, BOTH SAID ON SCREEN RATHER THAN IN A COMMENT
 *
 * - `POST /api/tools/{name}` **writes nothing to the event log**. The route
 *   calls the registry and returns; there is no `events.append`. So a result
 *   from this panel is not part of the durable transcript, and it is shown
 *   here, next to its button, with that stated — rather than dropped into the
 *   chat column where it would look like something the thread remembers.
 * - A tool marked `approval="always"` refuses without one and answers 428.
 *   The confirmation quotes the registry's own verb ("start a training run on
 *   this machine") instead of a sentence written here, because the verb is
 *   what the tool actually does.
 */

import { useEffect, useRef, useState } from 'react';
import type { ToolControl, ToolField } from '../lib/engine/types';
import type { ToolsState } from '../lib/useTools';
import { readDiagnosis } from '../lib/engine/facts';
import { readProposal, readProposalRefusal } from '../lib/engine/build';
import {
  readEvalComparison,
  readEvalReport,
  readEvalRefusal,
} from '../lib/engine/evals';
import { readPromptAttempt, readPromptRefusal } from '../lib/engine/prompts';
import type { DenialsState } from '../lib/useApprovals';
import type { ApproveOutcome, StormsState } from '../lib/useStorms';
import { Icon, groupIcon } from './Icon';
import { DiagnosisCard } from './DiagnosisCard';
import { ProposalCard, ProposalRefusalCard } from './ProposalCard';
import { EvalCard, EvalCompareCard, EvalRefusalCard } from './EvalCard';
import { PromptCard, PromptRefusalCard } from './PromptCard';
import type { RunTool } from './NextStep';
import { ResultView } from './ResultView';
import { Button, IconButton, Strip } from './primitives';

interface RunOutcome {
  ok: boolean;
  result: unknown;
  error: string | null;
  at: number;
}

export function Controls({
  tools,
  threadId,
  storms,
  denials,
  onApprove,
  onClose,
  focus = null,
  prefill = null,
}: {
  tools: ToolsState;
  /** The open conversation, or null on a new thread. Sent with every run: a
   *  fact measured with no thread is MACHINE scope and visible in every
   *  conversation, which is right for "this box has 8 GB of VRAM" and wrong for
   *  "the eval set has 120 rows". `app/main.py` says so at the route. */
  threadId: number | null;
  /** A proposal can arrive through this door as easily as through the model's,
   *  and an approval is an approval either way. Same state, same routes. */
  storms: StormsState;
  denials: DenialsState;
  onApprove: (
    fingerprint: string,
    proposalArgs: Record<string, unknown>,
    build: unknown,
  ) => Promise<ApproveOutcome>;
  onClose: () => void;
  /** One tool to open on arrival, by name. The journey overview sends the step
   *  a person is on, so "do this step" lands on the control that does it
   *  rather than in a list of sixty-seven. Null is the ordinary case: the
   *  dialog opened from the toolbar, about nothing in particular. */
  focus?: string | null;
  /** Values the journey overview read off the record for the focused tool,
   *  field name to `{value, from}`. Shown filled, with `from` under the field:
   *  a filled box with no account of where its value came from is
   *  indistinguishable from a guess, and this product's whole argument is that
   *  the difference is visible. */
  prefill?: Record<string, { value: unknown; from: string }> | null;
}) {
  const [openPacks, setOpenPacks] = useState<Set<string>>(() => new Set());
  useEffect(() => {
    if (!focus) return;
    const pack = tools.groups.find((group) => group.controls.some((control) => control.name === focus));
    if (!pack) return;
    setOpenPacks((current) => (current.has(pack.group) ? current : new Set([...current, pack.group])));
  }, [focus, tools.groups]);

  return (
    <div className="dialog__scrim" role="presentation" onClick={onClose}>
      <div
        className="dialog dialog--wide"
        role="dialog"
        aria-modal="true"
        aria-label="Controls"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="dialog__head">
          <Icon name="skill" size={16} />
          <h2 className="dialog__title">Controls</h2>
          <IconButton label="Close" icon="x" onClick={onClose} />
        </header>

        <div className="dialog__body scroll-y">
          <p className="dialog__lede">
            Everything the harness can do, as buttons. These are the same
            operations a connected model calls, declared once — so the product
            still works when the model you lent it cannot call tools.
          </p>

          {/* WHAT THIS USED TO SAY, AND WHY IT WAS FALSE BY THE TIME IT WAS
              READ. "A tool run from here is not written to the transcript...
              it appends no event, so the result appears below its button and
              nowhere else." That was true when it was written and stopped
              being true the day the owner asked "you sent 13 steps with 0
              output - where are you getting this information from?": the door
              now writes the same tool.call/tool.result pair the conductor
              writes, marked `driven_by: "user"`, whenever the run is filed
              under a conversation (app/main.py, run_tool_ep). The strip
              outlived the behaviour it described, which is the interface
              version of a stale docstring - and worse, because a person reads
              this one. */}
          <Strip tone="info">
            A tool run from here <strong>is written to the transcript</strong> when
            a conversation is open — the same <code>tool.call</code> and{' '}
            <code>tool.result</code> rows a model's call writes, marked{' '}
            <em>run by you</em>. With no conversation open, nothing is filed:
            a row belongs to a thread only when there is one to belong to, and
            the result appears below its button and nowhere else.
          </Strip>

          {tools.loading ? <p className="dialog__lede">Loading…</p> : null}
          {tools.error ? (
            <Strip tone="wont">
              <span className="mono">{tools.error}</span>
            </Strip>
          ) : null}

          {/* HIDDEN FIRST, THEN SHOWN. Max, 2026-09-12: "when you click on
              controls... I want to make sure it doesn't all come auto
              expanded... these categories should be expanded [on click], and
              the tools are expandables from the categorical main point...
              our go-to for tools and controls is just throw stuff in your
              face." A pack is one row with its count; its tools appear when
              the row is opened. The pack holding the tool the person was sent
              to (`focus`) opens on arrival so the row they came for is on
              screen. */}
          {tools.groups.map((group) => {
            const shown = openPacks.has(group.group);
            return (
              <section className="dialog__section" key={group.group} data-open={shown || undefined}>
                <button
                  type="button"
                  className="dialog__h3 packhead"
                  aria-expanded={shown}
                  onClick={() =>
                    setOpenPacks((current) => {
                      const next = new Set(current);
                      if (next.has(group.group)) next.delete(group.group);
                      else next.add(group.group);
                      return next;
                    })
                  }
                >
                  <Icon name="chevright" size={12} rotate={shown ? 90 : 0} />
                  <Icon name={groupIcon(group.group)} />
                  <span className="packhead__name">{group.group}</span>
                  <span className="packhead__count num">
                    {group.controls.length} tool{group.controls.length === 1 ? '' : 's'}
                  </span>
                </button>
                {shown
                  ? group.controls.map((control) => (
                      <ControlRow
                        key={control.name}
                        control={control}
                        focused={focus === control.name}
                        prefill={focus === control.name ? prefill : null}
                        tools={tools}
                        threadId={threadId}
                        storms={storms}
                        denials={denials}
                        onApprove={onApprove}
                      />
                    ))
                  : null}
              </section>
            );
          })}

          {tools.instructionSet ? (
            <p className="field__hint">
              Instruction set <span className="mono">{tools.instructionSet}</span>
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function ControlRow({
  control,
  tools,
  threadId,
  storms,
  denials,
  onApprove,
  focused = false,
  prefill = null,
}: {
  control: ToolControl;
  /** Opened and scrolled to on arrival — the journey overview's "do this
   *  step". It opens the row and fills nothing: what goes in the fields is the
   *  person's to say, and a pre-filled path would be this product guessing at
   *  the one thing it cannot measure. */
  focused?: boolean;
  prefill?: Record<string, { value: unknown; from: string }> | null;
  tools: ToolsState;
  threadId: number | null;
  storms: StormsState;
  denials: DenialsState;
  onApprove: (
    fingerprint: string,
    proposalArgs: Record<string, unknown>,
    build: unknown,
  ) => Promise<ApproveOutcome>;
}) {
  const [open, setOpen] = useState(focused);
  const row = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!focused || !row.current) return;
    setOpen(true);
    row.current.scrollIntoView({ block: 'center', behavior: 'auto' });
  }, [focused]);

  /* And put the caret in the first thing still to fill.

     The journey's button for this says "Fill in path"; opening the row and
     scrolling to it keeps three quarters of that promise and leaves the person
     to hunt for the field. Measured on the design-model walk: the row opened,
     all three fields were on screen, and focus stayed on the button in the
     other pane.

     Keyed on `open` rather than done alongside `setOpen(true)`, because the
     fields do not exist until that state change has been committed - a first
     attempt scheduled this in a `requestAnimationFrame` from the effect above
     and found nothing to focus, since the frame ran before React drew the row.

     The FIRST EMPTY field, never a filled one: a prefilled value is an answer
     already given, and moving past it to the next blank is what a person
     filling a form does anyway. */
  useEffect(() => {
    if (!focused || !open || !row.current) return;
    const fields = row.current.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>(
      'input, textarea',
    );
    [...fields].find((field) => !field.value)?.focus();
  }, [focused, open]);
  /* The offered values go in ONCE, when the row is focused with them. Not on
     every render: a person who clears a prefilled path meant to clear it, and
     a form that put the value back would be arguing with them. */
  const filled = useRef(false);
  useEffect(() => {
    if (!prefill || filled.current) return;
    filled.current = true;
    setValues((held) => {
      const next = { ...held };
      for (const [field, offered] of Object.entries(prefill)) {
        if (next[field]) continue;
        /* An object parameter is written as JSON, because that is the form the
           tool's own schema declares and the form's textarea parses — the
           training config arrives this way. `String({})` would put
           "[object Object]" in the box. */
        next[field] =
          offered.value !== null && typeof offered.value === 'object'
            ? JSON.stringify(offered.value, null, 2)
            : String(offered.value);
      }
      return next;
    });
  }, [prefill]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [approved, setApproved] = useState(false);
  const [running, setRunning] = useState(false);
  const [outcome, setOutcome] = useState<RunOutcome | null>(null);
  const [badField, setBadField] = useState<string | null>(null);
  /* The arguments the last run actually carried. Kept because approving a
     proposal sends the QUESTION back to the engine rather than the plan, and
     the question is these. */
  const [sent, setSent] = useState<Record<string, unknown> | null>(null);

  const run = async () => {
    setBadField(null);
    let args: Record<string, unknown>;
    try {
      args = coerce(control.fields, values);
    } catch (failure) {
      setBadField(failure instanceof Error ? failure.message : String(failure));
      return;
    }
    setRunning(true);
    setSent(args);
    const result = await tools.run(control.name, args, approved, threadId);
    setOutcome({ ...result, at: Date.now() });
    setRunning(false);
  };

  /**
   * A required field nobody has answered.
   *
   * AN EMPTY OBJECT OR ARRAY IS AN ANSWER, NOT A BLANK. This distinction was
   * found by driving the product end to end and being stopped by it: after the
   * harness had measured eight facts in a thread, the one control that turns
   * them into a verdict — `run_diagnosis`, whose `facts` parameter is a
   * required object — sat behind a disabled button reading "needs facts". Its
   * own description, printed three lines above the field, says the opposite:
   * "Anything already measured in this thread is merged in for you, so there is
   * nothing to be gained by repeating a number back." So the honest fact sheet
   * is `{}`, and the interface was demanding the user type those two characters
   * by hand before it would let them ask for the answer.
   *
   * JSON Schema `required` means the KEY must be present. It has never meant
   * the object must be non-empty. `coerce` sends `{}` for a blank object field
   * and `[]` for a blank array, so the key IS present and the schema is
   * satisfied exactly. Nothing is loosened for scalars: a required path or
   * number left blank is still missing, because for those there is no empty
   * value that means anything.
   */
  /* Parsed strictly: a payload without an outcome and a gate ledger is not a
     diagnosis and falls back to the ordinary result view, exactly as the
     transcript does. */
  const verdict =
    outcome && outcome.ok && !outcome.error ? readDiagnosis(outcome.result) : null;
  /* THE SAME ARGUMENT, ONE SURFACE FURTHER ON. A plan is even less readable as
     a JSON tree than a verdict is, and the person who presses this button is
     by definition the person whose model could not call the tool — so the door
     they can use must show them the picture, the costs and the approval, not a
     nest of braces with `provenance: "UNKNOWN"` buried in it. One design, both
     doors. */
  const proposal =
    outcome && outcome.ok && !outcome.error ? readProposal(outcome.result) : null;
  const refusal = outcome && !outcome.error ? readProposalRefusal(outcome.result) : null;

  /* AND THE SAME ARGUMENT A THIRD TIME, for the bench.

     `run_eval` and `read_eval_results` are the two tools most likely to be
     pressed rather than called: an eval is long, it is the thing a person
     re-runs after every prompt edit, and the person pressing buttons here is by
     definition the one whose model could not call it. What comes back is a
     score, a Wilson interval, a failure histogram and twenty failing rows —
     which as a JSON tree is the single worst payload in the registry to read,
     and the one where reading it wrong costs the most.

     The comparison is the case that decides whether this wiring is optional.
     `read_eval_results` with `against` can answer NO EVIDENCE, and through
     `ResultView` that answer is a `verdict: "no_evidence"` string sitting in
     grey among forty sibling keys, three rows under a `delta: -0.15` that reads
     like a result. The card exists to stop exactly that, and a door that skips
     it is a door where the product's most important refusal does not happen. */
  const evalReport =
    outcome && outcome.ok && !outcome.error ? readEvalReport(outcome.result) : null;
  const evalCompare =
    outcome && outcome.ok && !outcome.error ? readEvalComparison(outcome.result) : null;
  const evalRefusal = outcome && !outcome.error ? readEvalRefusal(outcome.result) : null;
  /* `try_prompt` marks the `incomplete` verdict `ok: false`, so this is read
     from either state — the run that ran out of clock is the one whose
     explanation matters most. */
  const attempt = outcome && !outcome.error ? readPromptAttempt(outcome.result) : null;
  const promptRefusal = outcome && !outcome.error ? readPromptRefusal(outcome.result) : null;

  /** The card's next-step chips run tools through the same door this panel
   *  does — `POST /api/tools/{name}`, `actor=USER`. */
  const runTool: RunTool = async (name, args, thread) => {
    const answer = await tools.run(name, args, false, thread);
    return { ok: answer.ok, result: answer.result, error: answer.error };
  };

  const missing = control.fields
    .filter(
      (field) =>
        field.required &&
        field.type !== 'object' &&
        field.type !== 'array' &&
        !values[field.name]?.trim(),
    )
    .map((field) => field.name);

  return (
    <div className="ctrl" data-open={open} ref={row}>
      <button
        type="button"
        className="ctrl__head"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <span className="ctrl__label">{control.label}</span>
        <span className="ctrl__verb">{control.verb}</span>
        {control.needs_approval ? (
          <span className="ctrl__approval">needs approval</span>
        ) : null}
        <span className="toolrow__chev">
          <Icon name="chevright" size={12} rotate={open ? 90 : 0} />
        </span>
      </button>

      {open ? (
        <div className="ctrl__body">
          <p className="ctrl__desc">{control.description}</p>

          {control.fields.map((field) => (
            <FieldInput
              key={field.name}
              field={field}
              value={values[field.name] ?? ''}
              offered={prefill?.[field.name] ?? null}
              onChange={(next) =>
                setValues((current) => ({ ...current, [field.name]: next }))
              }
            />
          ))}

          {control.needs_approval ? (
            <label className="ctrl__approve">
              <input
                type="checkbox"
                checked={approved}
                onChange={(event) => setApproved(event.target.checked)}
              />
              <span>
                I am approving this: <strong>{control.verb}</strong>.
              </span>
            </label>
          ) : null}

          <div className="dialog__actions">
            <Button
              kind="primary"
              onClick={() => void run()}
              disabled={
                running || missing.length > 0 || (control.needs_approval && !approved)
              }
            >
              {running ? 'Running…' : 'Run'}
            </Button>
            {missing.length > 0 ? (
              <span className="meta">needs {missing.join(', ')}</span>
            ) : null}
            <span className="meta">
              reads {control.reads.length ? control.reads.join(', ') : 'nothing'} ·
              writes {control.writes.length ? control.writes.join(', ') : 'nothing'}
            </span>
          </div>

          {badField ? (
            <Strip tone="wont">
              <span className="mono">{badField}</span>
            </Strip>
          ) : null}

          {outcome ? (
            <div className="ctrl__result" data-ok={outcome.ok}>
              <div className="toolrow__sectiontitle">
                {/* A REFUSAL IS NOT A FAILURE, and the header must not call it
                    one. `propose_build` answers `ok: false` when it knows what
                    should happen and cannot yet write a build that does it —
                    "a refusal to draw a plan that could not run, not a
                    failure" — and the call itself worked perfectly. Found by
                    looking: the block read FAILED above a card whose whole
                    argument is that declining to draw a plan is competence. */}
                {outcome.error
                  ? 'The engine refused'
                  : refusal
                    ? 'No plan, and why'
                    : /* THE SAME CORRECTION THE PROPOSAL REFUSAL EARNED, for
                         the same reason. `compare()` declining to subtract two
                         scores measured on two different eval sets is the bench
                         working exactly as designed; heading it "Failed" would
                         call the product's competence a fault. */
                      evalRefusal
                      ? 'Not compared, and why'
                      : /* Same correction again: the prompt bench recognising a
                           prompt it has already scored, and spending nothing,
                           is not a failure. Found by pressing this button. */
                        promptRefusal
                        ? 'Not run, and why'
                      : outcome.ok
                        ? 'Found'
                        : 'Failed'}
                <span className="ctrl__notinlog">not in the transcript</span>
              </div>
              {outcome.error ? (
                <p className="mono ctrl__desc">{outcome.error}</p>
              ) : verdict ? (
                /* A DIAGNOSIS IS NOT A KEY/VALUE TABLE, WHICHEVER DOOR IT CAME
                   THROUGH.

                   This panel exists so the product "still works when the model
                   you lent it cannot call tools" — and in the run this was
                   found in, that is exactly what happened: the model would not
                   call `run_diagnosis` with a clean fact sheet, so the person
                   pressed the button. What came back was a real BLOCKED verdict
                   with a five-gate ledger, and it rendered as a JSON tree with
                   seventy DEFAULTED rows in it, the verdict word set in the
                   same grey as every other value.

                   The transcript already renders this payload properly. There
                   was never a second design; there was one design and one path
                   that did not use it. Same component, same card, same gate
                   ledger and the same next-step controls. */
                <DiagnosisCard
                  result={verdict}
                  threadId={threadId}
                  tools={tools.byName}
                  runTool={runTool}
                />
              ) : proposal ? (
                <ProposalCard
                  proposal={proposal}
                  /* What this panel actually sent. The approval route
                     re-proposes from these, so a plan approved here is checked
                     against the same question that produced it. */
                  proposalArgs={sent ?? {}}
                  threadId={threadId}
                  tools={tools.byName}
                  storm={storms.forFingerprint(proposal.approve)}
                  denial={denials.forFingerprint(proposal.approve)}
                  onApprove={onApprove}
                  onDeny={denials.deny}
                  onForgetDenial={denials.forget}
                  onCancel={(id) => void storms.cancel(id)}
                />
              ) : refusal ? (
                <ProposalRefusalCard refusal={refusal} />
              ) : evalReport ? (
                <EvalCard report={evalReport} />
              ) : evalCompare ? (
                <EvalCompareCard comparison={evalCompare} />
              ) : evalRefusal ? (
                <EvalRefusalCard refusal={evalRefusal} />
              ) : attempt ? (
                <PromptCard attempt={attempt} />
              ) : promptRefusal ? (
                <PromptRefusalCard refusal={promptRefusal} />
              ) : (
                <ResultView value={outcome.result} />
              )}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function FieldInput({
  field,
  value,
  onChange,
  offered = null,
}: {
  field: ToolField;
  value: string;
  onChange: (next: string) => void;
  /** Where this field's value came from, when the journey overview offered
   *  it. Drawn under the input, because a filled box with no account of its
   *  value is indistinguishable from a guess - and the whole argument of this
   *  product is that the difference is visible. */
  offered?: { from: string } | null;
}) {
  const label = `${field.name}${field.required ? '' : ' (optional)'}`;
  const source =
    offered && value ? (
      <span className="field__from">from {offered.from}</span>
    ) : null;

  if (field.enum && field.enum.length > 0) {
    return (
      <label className="field">
        <span className="field__label mono">{label}</span>
        <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">— leave to the engine —</option>
          {field.enum.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        {field.description ? <span className="field__hint">{field.description}</span> : null}
        {source}
      </label>
    );
  }

  if (field.type === 'boolean') {
    return (
      <label className="field field--inline">
        <input
          type="checkbox"
          checked={value === 'true'}
          onChange={(event) => onChange(event.target.checked ? 'true' : '')}
        />
        <span className="field__label mono">{label}</span>
        {field.description ? <span className="field__hint">{field.description}</span> : null}
        {source}
      </label>
    );
  }

  if (field.type === 'object' || field.type === 'array') {
    return (
      <label className="field">
        <span className="field__label mono">{label}</span>
        <textarea
          className="input input--area mono"
          rows={3}
          value={value}
          spellCheck={false}
          placeholder={field.type === 'object' ? '{ }' : '[ ]'}
          onChange={(event) => onChange(event.target.value)}
        />
        <span className="field__hint">
          {field.description}
          {field.description ? ' ' : ''}
          Written as JSON, because this parameter is a {field.type} in the tool&rsquo;s
          own schema and there is no honest smaller form for it.
        </span>
        {source}
      </label>
    );
  }

  return (
    <label className="field">
      <span className="field__label mono">{label}</span>
      <input
        className="input mono"
        type={field.type === 'integer' || field.type === 'number' ? 'number' : 'text'}
        value={value}
        spellCheck={false}
        onChange={(event) => onChange(event.target.value)}
      />
      {field.description ? <span className="field__hint">{field.description}</span> : null}
      {source}
    </label>
  );
}

/**
 * Form strings to the types the schema declares.
 *
 * An empty optional field is **omitted** rather than sent as `""` or `0`, so
 * the engine's own default applies. Sending a zero where the user typed
 * nothing would be this layer inventing a value, which is the thing the
 * never-invent-a-number rule is about.
 */
function coerce(
  fields: ToolField[],
  values: Record<string, string>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const field of fields) {
    const raw = values[field.name];
    if (raw === undefined || raw.trim() === '') {
      /* A required object or array left blank is the empty one. See the note
         on `missing` in ControlRow: the key is what `required` asks for, and
         `{}` is a complete fact sheet, not an absent one. An OPTIONAL field
         left blank is still left to the engine's own default. */
      if (field.required && field.type === 'object') out[field.name] = {};
      if (field.required && field.type === 'array') out[field.name] = [];
      continue;
    }

    if (field.type === 'boolean') {
      out[field.name] = raw === 'true';
      continue;
    }
    if (field.type === 'integer' || field.type === 'number') {
      const parsed = Number(raw);
      if (!Number.isFinite(parsed)) {
        throw new Error(`${field.name}: "${raw}" is not a number`);
      }
      out[field.name] = field.type === 'integer' ? Math.trunc(parsed) : parsed;
      continue;
    }
    if (field.type === 'object' || field.type === 'array') {
      try {
        out[field.name] = JSON.parse(raw);
      } catch (failure) {
        throw new Error(
          `${field.name}: that is not valid JSON — ${
            failure instanceof Error ? failure.message : String(failure)
          }`,
        );
      }
      continue;
    }
    out[field.name] = raw;
  }
  return out;
}
