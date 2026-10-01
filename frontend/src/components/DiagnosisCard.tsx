/**
 * The do-not-train card and the gate ledger — Graphite page 23.
 *
 * "The most valuable thing this product can say is *do not train anything*…
 * So this is the most important surface in the product, and its whole design
 * problem is one sentence: the answer 'no' has to read as expertise, not as
 * refusal."
 *
 * ══ WHAT THIS BUILD ADDS TO PAGE 23 ════════════════════════════════════════
 *
 * Page 23 was drawn before the engine tracked where a fact came from. The
 * ledger it draws shows, per gate, whether the gate PASSED. That is no longer
 * the whole question, because a gate can pass on a number nobody can vouch for:
 *
 *   "A provider that merely ASSERTS eval_size_n / baseline_measured /
 *    baseline_score / prompt_iterations / retrieval_tried / model_swap_tried
 *    gets TRAIN__LORA_SFT with all five gates green."
 *
 * The engine closed that. Every gate row here therefore carries a second fact
 * beside its status: **by what, and by whom.** A gate satisfied by a
 * measurement and a gate satisfied by a model's say-so are different claims,
 * and after this change they look different on screen. That is the same law
 * invariant 3 already applies to hardware numbers, pointed at the facts that
 * actually decide whether somebody trains a model.
 *
 * ══ THE THREE RULES THIS FILE IS BUILT TO ══════════════════════════════════
 *
 * 1. **Never render an asserted fact as a measured one.** `OriginTag` carries
 *    the engine's own word and the engine's own origin; nothing here upgrades,
 *    infers or summarises a provenance. Where the engine says nothing, nothing
 *    is shown — page 13: "a tag never renders without a number".
 *
 * 2. **A refusal comes with the thing that closes it.** A gate blocked because
 *    its fact is only asserted gets the tool that would measure it as a
 *    control, right there in the card. Page 23.4: "each of these starts now"
 *    is literal, and "a row of controls that each *begin* that work says the
 *    same thing and then does it".
 *
 * 3. **Neither alarmed nor credulous.** An assertion is not a lie and not an
 *    error. It is an unverified claim. So the block is `--unknown` grey, not
 *    `--wont` red: page 13.5 — "when the missing number blocks the whole
 *    answer, the card does not degrade, it changes verdict, and grey is
 *    deliberate. Not knowing is an absence, not a problem."
 *
 * ══ WHAT IS NOT HERE, AND WHY ══════════════════════════════════════════════
 *
 * Page 23.5 makes the revisit condition mandatory and page 23.4 wants three
 * alternative controls. `run_diagnosis` sends neither: there is no `revisit_if`
 * and no alternatives list on the wire — only `say`, and `help` on a blocked
 * run. Inventing either would be invariant 5 ("never invent a number… this
 * applies to our own documentation: an illustrative figure that reads as
 * measured is the same defect as a fabricated one in the product") applied to
 * sentences instead of figures, which is the same defect. So both render as
 * named absences saying which engine field would fill them. Reported, not
 * papered over.
 */

import { useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import {
  ORIGIN_MEANS,
  actorName,
  factsInClause,
  isFactOrigin,
  weakestOrigin,
  type DiagnosisPayload,
  type FactOrigin,
  type GateLedgerEntry,
  type UnsubstantiatedRow,
} from '../lib/engine/facts';
import type { ToolControl } from '../lib/engine/types';
import type { VerdictItem } from '../lib/transcript';
import { FIVE_GATES, type GateSpec } from '../data/sample';
import { OriginTag } from './primitives';
import { Icon, type IconName } from './Icon';
import { NextStepControl, type RunTool } from './NextStep';

/* ── The verdict badge ────────────────────────────────────────────────────
   Three verdicts reach a renderer — NO_TRAIN, BLOCKED and TRAIN — and each
   spends a different hue for a stated reason. */

interface VerdictLook {
  word: string;
  token: string;
  why: string;
}

const VERDICT: Record<string, VerdictLook> = {
  /* Page 23.1, in as many words: "--info is the token for 'a notice, not a
     verdict', and it is the only honest slot on the palette for a claim that
     is neither good news nor bad news but simply the finding." */
  NO_TRAIN: { word: 'Do not train', token: 'info', why: 'this is the answer, not a failure' },
  /* Page 13.5 §3, the UNKNOWN verdict: "When the missing number blocks the
     whole answer, the card does not degrade — it changes verdict, and grey is
     deliberate. Not knowing is an absence, not a problem." A blocked run is
     exactly that shape: the harness has not answered, because something it
     needs is missing or unvouched-for. Red would say the person did something
     wrong; they did not. */
  BLOCKED: { word: 'Blocked', token: 'unknown', why: 'nothing has been decided yet' },
  /* Under Full the harness settles open gates itself — "Blocked" reads as a
     person-facing stop. Same verdict on the wire; quieter word on the card. */
  BLOCKED_FULL: { word: 'Settling', token: 'unknown', why: 'Full mode is working the open gates' },
  /* Graphite has no train card. --fits is used because the five green rows
     directly beneath it are the claim, so the badge adds no colour the ledger
     is not already making — and grey would deny a verdict the engine did
     compute. Recorded as owed work for the book rather than settled here. */
  TRAIN: { word: 'Train', token: 'fits', why: 'all five gates passed' },
};

function VerdictPill({
  verdict,
  permission,
}: {
  verdict: string;
  permission?: 'ask' | 'measure' | 'write' | 'full';
}) {
  const key =
    verdict === 'BLOCKED' && permission === 'full' ? 'BLOCKED_FULL' : verdict;
  const look = VERDICT[key] ?? VERDICT[verdict];
  if (!look) {
    /* An unrecognised verdict prints itself. Better a raw word than a
       confident colour on a claim this file has never seen. */
    return (
      <span className="vpill vpill--plain" title="The engine sent a verdict this surface has no treatment for.">
        {verdict}
      </span>
    );
  }
  return (
    <span
      className="vpill"
      style={
        {
          '--v-colour': `var(--${look.token})`,
          '--v-wash': `var(--${look.token}-wash)`,
          '--v-edge': `var(--${look.token}-edge)`,
        } as CSSProperties
      }
      title={look.why}
    >
      {look.word}
    </span>
  );
}

/* ── The gate row's five states ───────────────────────────────────────────
   Page 23.3 draws four: passed, blocked, not reached, and waiting on you. The
   fourth "is the one that makes the ledger a control rather than a report".
   Here it is reached by a fifth engine fact rather than by a fifth status: a
   gate whose predicate held but whose facts were only claimed is FAILED on the
   wire and carries `unsubstantiated`. That is the row the person can close. */

export type RowState =
  | 'passed'
  | 'blocked'
  | 'not-started'
  | 'unsubstantiated'
  | 'not-reached';

/**
 * THE FIFTH STATE, and the owner is the reason it exists.
 *
 * Max, on a thread where he had measured nothing yet: *"it fails really
 * loud on this check and goes all in on it."* He was right about the
 * symptom. On a fresh thread every gate is BLOCKED, and blocked draws
 * `--wont` red with an alert icon - five red rows telling a person who has
 * not done anything yet that something is wrong.
 *
 * Nothing is wrong. Nothing has happened.
 *
 * The argument is already in this file, made for the other end of the
 * ledger: page 23.8 rule 3 says not-reached is never red "because red would
 * claim the harness tested it and found it wanting". A gate whose clause
 * names facts and where NOT ONE of them has been read or claimed is in the
 * same position. The harness did not test it. The person did not fail it.
 *
 * THE CONDITION IS PER-GATE, NOT PER-THREAD, and that distinction is the
 * whole honesty of it. "Has this thread measured anything" would grey out a
 * gate that really is blocked on a reading that exists and disagrees.
 * `factsInClause` returns only facts the payload has an origin for, so an
 * EMPTY result against a non-empty clause means precisely: this gate asks
 * about things nobody has looked at. That is a step not taken, and it is
 * drawn as one.
 */
function nothingIsKnownForThisGate(
  entry: GateLedgerEntry,
  origins: Record<string, string>,
): boolean {
  if (!entry.clause) return false;
  return factsInClause(entry.clause, origins).length === 0;
}

export function rowState(
  entry: GateLedgerEntry | undefined,
  origins: Record<string, string>,
): RowState {
  if (!entry) return 'not-reached';
  if (entry.status === 'PASSED') return 'passed';
  if (entry.status === 'NOT_REACHED') return 'not-reached';
  if (entry.unsubstantiated?.length) return 'unsubstantiated';
  return nothingIsKnownForThisGate(entry, origins) ? 'not-started' : 'blocked';
}

export const LOOK: Record<RowState, { token: string; icon: IconName; word: string }> = {
  passed: { token: 'fits', icon: 'check', word: 'passed' },
  /* STILL RED, and deliberately. A gate blocked on a reading that EXISTS and
     does not clear the bar is the harness having tested something and found
     it wanting, which is exactly what red is for. Only the untouched case
     moved. */
  blocked: { token: 'wont', icon: 'alert', word: 'blocked' },
  /* Grey, and the word is a step rather than a judgement. */
  'not-started': { token: 'unknown', icon: 'chevright', word: 'not started' },
  /* Grey, not red, and this is the whole point of the state existing. Page
     23.8 rule 3 says not-reached is never red "because red would claim the
     harness tested it and found it wanting". The same argument holds here from
     the other side: the harness did not test this, it declined to take
     somebody's word for it, and the person has not failed anything. The word
     is "unverified" rather than "refused" for the same reason. */
  unsubstantiated: { token: 'unknown', icon: 'eye', word: 'unverified' },
  'not-reached': { token: 'unknown', icon: 'x', word: 'not reached' },
};
/* ── The card ─────────────────────────────────────────────────────────────── */

export function DiagnosisCard({
  result,
  threadId,
  tools,
  runTool,
  defaultOpen = true,
  permission,
}: {
  result: DiagnosisPayload;
  /** Which conversation the facts belong to. Sent with every control run, so a
   *  measurement lands in this thread and not in machine scope. */
  threadId: number | null;
  tools: Map<string, ToolControl>;
  runTool: RunTool;
  /** AU2 — historical diagnoses start collapsed; the live one stays open. */
  defaultOpen?: boolean;
  /** AU1/CS17 — under `full`, softens BLOCKED → Settling (no person-facing stop). */
  permission?: 'ask' | 'measure' | 'write' | 'full';
}) {
  const [open, setOpen] = useState(defaultOpen);

  const passed = FIVE_GATES.filter(
    (gate) => result.gate_ledger[gate.id]?.status === 'PASSED',
  ).length;

  /* The header tag is a claim about the RUN, so it is computed from the gates
     that actually ran: the weakest origin among the facts their clauses name.
     A diagnosis is exactly as substantiated as its worst load-bearing input,
     and a header that reported the best one would be the "MEASURED beside
     ASSERTED" defect wearing a card header. Null when no gate ran, and then no
     tag renders at all — page 13: "a tag never renders without a number". */
  const evidenceOrigin = weakestOrigin(
    FIVE_GATES.flatMap((gate) => {
      const entry = result.gate_ledger[gate.id];
      if (!entry || entry.status === 'NOT_REACHED') return [];
      return factsInClause(entry.clause, result.fact_origins);
    }),
    result.fact_origins,
  );

  return (
    <div className="card card--diagnosis" data-open={open} data-full={permission === 'full' || undefined}>
      <div className="card__head">
        <Icon name="gauge" />
        <span className="card__kicker">Diagnosis</span>
        {open ? null : (
          <>
            <VerdictPill verdict={result.verdict} permission={permission} />
            <span className="card__clip">{firstClause(result.say) ?? result.outcome}</span>
          </>
        )}
        <span className="card__headright">
          {evidenceOrigin ? <OriginTag origin={evidenceOrigin} /> : null}
          <button
            type="button"
            className="iconbtn"
            aria-label={open ? 'Collapse the diagnosis' : 'Expand the diagnosis'}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            <Icon name="chevright" size={14} rotate={open ? 90 : 0} />
          </button>
        </span>
      </div>

      {open ? (
        <div className="card__body">
          <div className="card__headline">
            <VerdictPill verdict={result.verdict} permission={permission} />
            {/* The engine's own identifier for the finding, in mono. It is the
                word a reader will find in docs/diagnosis_engine.yaml, which is
                what makes the card checkable rather than a retelling. */}
            <span className="mono card__outcome" title={result.outcome}>
              {result.outcome}
            </span>
          </div>

          {permission === 'full' && result.verdict === 'BLOCKED' ? (
            <p className="card__text card__text--quiet">
              Full mode settles open gates itself — nothing here waits for your
              approval.
            </p>
          ) : null}

          {result.say ? (
            <p className="card__text">{result.say}</p>
          ) : (
            <p className="card__absent">
              The engine returned no note for this outcome. <span className="mono">say</span> was
              empty on the wire, and nothing here writes one.
            </p>
          )}

          <GateLedger result={result} passed={passed} />

          {result.unsubstantiated.length > 0 ? (
            <Unsubstantiated
              rows={result.unsubstantiated}
              result={result}
              threadId={threadId}
              tools={tools}
              runTool={runTool}
            />
          ) : null}

          <Alternatives result={result} />

          <Revisit result={result} />
        </div>
      ) : null}
    </div>
  );
}

/* ── The ledger ───────────────────────────────────────────────────────────── */

function GateLedger({ result, passed }: { result: DiagnosisPayload; passed: number }) {
  /* Every gate the engine returned that this surface has no row for. Appended
     rather than dropped: a sixth gate must be visible the day it exists, and
     "five of six" is not the promise. */
  const extra = Object.keys(result.gate_ledger).filter(
    (id) => !FIVE_GATES.some((gate) => gate.id === id),
  );

  return (
    <div className="gates gates--card">
      <div className="gates__head">
        <Icon name="check" size={12} />
        <span>Gate ledger</span>
        {/* "The counter in the header is n/5 and never a percentage. Three of
            five gates is not 60% of a guarantee." It is also derivable — five
            rows are drawn — so page 13.6 exempts it from carrying a tag. */}
        <span className="gates__count">
          {passed} of {FIVE_GATES.length} passed
        </span>
      </div>

      {FIVE_GATES.map((gate, index) => (
        <GateRow
          key={gate.id}
          gate={gate}
          index={index}
          entry={result.gate_ledger[gate.id]}
          result={result}
        />
      ))}

      {extra.map((id) => (
        <div className="gate gate--unlabelled" key={id}>
          <Icon name="info" size={14} />
          <span className="gate__name mono">{id}</span>
          <span className="gate__right">
            <span className="gate__evidence">
              a gate this surface has no wording for — {result.gate_ledger[id].status}
            </span>
          </span>
        </div>
      ))}
    </div>
  );
}

function GateRow({
  gate,
  index,
  entry,
  result,
}: {
  gate: GateSpec;
  index: number;
  entry: GateLedgerEntry | undefined;
  result: DiagnosisPayload;
}) {
  const [open, setOpen] = useState(false);
  const state = rowState(entry, result.fact_origins);
  const look = LOOK[state];

  const facts = factsInClause(entry?.clause ?? null, result.fact_origins);
  /* THE SECOND FACT ON EVERY ROW. Not "did this gate pass" but "on what". A
     gate that never ran read nothing, so it gets no tag — the alternative
     would be a provenance badge on a question nobody asked. */
  const origin = state === 'not-reached' ? null : weakestOrigin(facts, result.fact_origins);

  /* The claims this gate refused, joined back to the row that explains them. */
  const challenged = result.unsubstantiated.filter((row) => row.gate === gate.id);

  return (
    <div className="gate gate--wrap" data-state={state} data-open={open}>
      <button
        type="button"
        className="gate__head"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {/* The glyph carries the status as well as the colour does, so the
            ledger is readable with no colour perception at all. */}
        <span className="gate__glyph" style={{ color: `var(--${look.token})` }}>
          <Icon name={look.icon} size={14} />
        </span>
        <span className="gate__no">{index + 1}</span>
        <span className="gate__name">{gate.name}</span>
        <span className="gate__right">
          {origin ? (
            <OriginTag origin={origin} by={vouchedBy(facts, origin, result)} />
          ) : null}
          <span
            className="vpill vpill--sm"
            style={
              {
                '--v-colour': `var(--${look.token})`,
                '--v-wash': `var(--${look.token}-wash)`,
                '--v-edge': `var(--${look.token}-edge)`,
              } as CSSProperties
            }
          >
            {look.word}
          </span>
          <span className="gate__chev">
            <Icon name="chevright" size={12} rotate={open ? 90 : 0} />
          </span>
        </span>
      </button>

      {open ? (
        <div className="gate__body">
          {/* The engine's own question, verbatim. Page 23: "The interface never
              paraphrases a gate." */}
          <p className="gate__asks">{gate.asks}</p>

          {entry?.clause ? (
            <div className="gate__clause">
              <span className="gate__clauselabel">requires</span>
              <code className="mono">{entry.clause}</code>
              {entry.row ? <span className="gate__row">row {entry.row}</span> : null}
            </div>
          ) : (
            <p className="gate__absent">
              Nothing below the block was evaluated, so this gate has no clause and no result. It
              is not failed and it is not passed.
            </p>
          )}

          {facts.length > 0 ? (
            <div className="factlist">
              {facts.map((name) => (
                <FactRow key={name} name={name} result={result} />
              ))}
            </div>
          ) : null}

          {/* The claim and the control that settles it live in ONE place — the
              block below the ledger — and this row points at it rather than
              repeating it. The first cut printed the substantiation and the
              button here as well; looking at the screenshot, the card said the
              same paragraph and drew the same button twice, which is 90px of
              card spent on nothing and is the shape of thing page 23.7 says
              pushes the revisit condition below the fold. */}
          {challenged.length > 0 ? (
            <p className="gate__absent">
              {challenged.length === 1
                ? `${challenged[0].fact} was claimed rather than measured. What would settle it is below the ledger.`
                : 'These claims were not measured. What would settle them is below the ledger.'}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/**
 * One fact, its value, its origin, and the engine's own sentence about how it
 * got here. This is the row that makes the gate above it checkable.
 */
function FactRow({ name, result }: { name: string; result: DiagnosisPayload }) {
  const used = result.facts_used[name];
  const origin = result.fact_origins[name];

  if (!used) {
    /* Nobody supplied it: it resolved through the fact ledger's own default.
       The VALUE is deliberately not printed — the engine does not send it, and
       a default printed as a fact is the "0.82 Defaulted" row page 13.6 draws
       under Don't. */
    return (
      <div className="fact" data-defaulted="true">
        <span className="fact__name mono">{name}</span>
        <span className="fact__value fact__value--absent">&mdash;</span>
        <span className="fact__how">
          nobody supplied it; the fact ledger&rsquo;s own default was used
        </span>
        {isFactOrigin(origin) ? <OriginTag origin={origin} /> : null}
      </div>
    );
  }

  return (
    <div className="fact">
      <span className="fact__name mono">{name}</span>
      <span className="fact__value mono">{show(used.value)}</span>
      {/* The engine's sentence, not ours: "counted 120 rows in eval.jsonl",
          "supplied with this call by the model". */}
      <span className="fact__how">{used.how}</span>
      {isFactOrigin(used.origin) ? (
        <OriginTag origin={used.origin} />
      ) : (
        <span className="tag tag--raw">{String(used.origin)}</span>
      )}
    </div>
  );
}

/* ── The block that names what was only claimed ───────────────────────────── */

function Unsubstantiated({
  rows,
  result,
  threadId,
  tools,
  runTool,
}: {
  rows: UnsubstantiatedRow[];
  result: DiagnosisPayload;
  threadId: number | null;
  tools: Map<string, ToolControl>;
  runTool: RunTool;
}) {
  return (
    <div className="unsub">
      {/* The engine's own voice, which is first person and unalarmed: "You have
          told me there is an eval set. I have not seen it." The header is that
          sentence compressed, and it is deliberately not "REFUSED" or
          "REJECTED" — nothing here is either. */}
      <div className="unsub__head">
        <Icon name="eye" size={12} />
        <span>
          {rows.length === 1
            ? 'A claim I have not seen'
            : `${rows.length} claims I have not seen`}
        </span>
      </div>
      {rows.map((row) => (
        <div className="unsub__row" key={`${row.gate}:${row.fact}`}>
          <div className="unsub__title">
            <span className="mono unsub__fact">{row.fact}</span>
            {isFactOrigin(row.origin) ? <OriginTag origin={row.origin} /> : null}
            <span className="unsub__source">
              declared <span className="mono">source: {row.declared_source}</span>
            </span>
          </div>
          <p className="unsub__text">{row.substantiation}</p>
          {row.next_step ? (
            <NextStepControl
              step={row.next_step}
              claimed={result.facts_used[row.fact]}
              threadId={threadId}
              control={row.next_step.tool ? tools.get(row.next_step.tool) ?? null : null}
              runTool={runTool}
            />
          ) : null}
        </div>
      ))}
    </div>
  );
}

/* ── The two parts the engine DOES send ───────────────────────────────────── */

/* IT HAS BEEN SENDING BOTH ALL ALONG. `app/tools/next_moves.py` builds
   `alternatives` and `revisit_if` out of the ledger's own words and the
   registry's `measures=` declarations, and `run_diagnosis` attaches them to
   every verdict. `readDiagnosis` in lib/engine/facts.ts never copied them, so
   these two functions returned null and drew, in their place, a sentence
   saying the engine sends neither. Max read "The engine sends no alternatives
   with a verdict" and "revisit_if... is not on the wire yet" on every blocked
   verdict, while the wire carried both. Nothing here is invented: each row is
   a move the engine named, with the tool it named for it. */

function Alternatives({ result }: { result: DiagnosisPayload }) {
  const moves = result.alternatives.filter((one) => one.text);
  if (!moves.length) return null;
  return (
    <div className="alts">
      <div className="alts__lead">What would move this</div>
      <ol className="alts__list">
        {moves.map((one, index) => (
          <li key={`${one.move}-${index}`} className="alts__row" data-now={one.starts_now || undefined}>
            <span className="alts__text">{one.text}</span>
            {one.tool ? (
              <span className="alts__tool mono" title={one.why || undefined}>
                {one.verb ? `${one.verb} — ` : ''}
                {one.tool}
                {one.run_as === 'user' ? ' · your call' : ''}
              </span>
            ) : null}
          </li>
        ))}
      </ol>
    </div>
  );
}

function Revisit({ result }: { result: DiagnosisPayload }) {
  /* Page 23.5: the revisit condition is mandatory and "never dropped". The
     engine states it as a list of conditions, each one a fact changing. `help`
     is the other sentence it sends on a blocked run; both are the engine's own
     words and neither is given a lead-in that makes a claim they do not make. */
  const when = result.revisit_if.filter((one) => one.trim());
  if (!when.length && !result.help) return null;
  return (
    <div className="revisit">
      <Icon name="refresh" size={12} />
      <span>
        {when.length ? `Ask again when ${when.join(', or when ')}.` : null}
        {when.length && result.help ? ' ' : null}
        {result.help ?? null}
      </span>
    </div>
  );
}

/* ── helpers ──────────────────────────────────────────────────────────────── */

/**
 * Who is vouching for the weakest fact under this gate, in the engine's own
 * words, reduced to a person. Answers the "and by whom" half.
 */
function vouchedBy(
  facts: string[],
  origin: FactOrigin,
  result: DiagnosisPayload,
): string | null {
  const name = facts.find((fact) => result.fact_origins[fact] === origin);
  if (!name) return null;
  const how = result.facts_used[name]?.how;
  if (how) return how;
  return actorName(null) ?? ORIGIN_MEANS[origin];
}

/** The first clause of the engine's note, for the collapsed header. Cut at a
 *  sentence boundary and elided, never re-worded. */
function firstClause(say: string | null): string | null {
  if (!say) return null;
  const trimmed = say.trim();
  const stop = trimmed.search(/[.?!]\s/);
  if (stop === -1) return trimmed.length > 72 ? `${trimmed.slice(0, 71)}…` : trimmed;
  return `${trimmed.slice(0, stop + 1)}…`;
}

/** A fact's value, printed as the engine sent it. Nothing is rounded and
 *  nothing is unit-guessed: the fact names carry their own units. */
function show(value: unknown): ReactNode {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'number') return value.toLocaleString();
  if (typeof value === 'string') return value.length > 48 ? `${value.slice(0, 47)}…` : value;
  return JSON.stringify(value);
}

/* ══ THE SAME CARD, SMALL — the engine's verdict beside the model's prose ═══
 *
 * `conductor.verdict` arrives on every turn whose REPLY settled the training
 * decision, whether or not anybody ran `run_diagnosis`. It carries less than
 * the payload above it does — no `facts_used`, no per-gate origins, no five
 * rows — so this is page 23 in its small form: the badge, the engine's
 * sentence, the gate line as the engine summarised it, and the next step as a
 * control.
 *
 * ══ THE QUESTION THIS CARD HAD TO ANSWER FIRST ═════════════════════════════
 *
 * Max's standing note about this product is that the verdict card and the
 * paragraph under it say the same thing verbatim, and that defect is older
 * than this card. A card that only restates the prose in a box is noise, so
 * the case for drawing it has to be made out of what it carries that a
 * paragraph cannot. Three things, and none of them is `say`:
 *
 * 1. **Whose claim it is.** The prose is the model's. This is
 *    `app/diagnosis.py`'s, walked over this thread's own ledger, and the
 *    header prints that path rather than implying it. Two identical sentences
 *    from two different authorities are two facts, not one — and telling them
 *    apart is the entire reason the engine stopped deleting the model's half.
 * 2. **What the harness read the reply as saying.** The READING is not in the
 *    prose and cannot be: it is the harness's own parser naming what it
 *    concluded about the paragraph above. It is also the card's weakest claim
 *    — `app/conductor.py` records that reader being wrong in three of three
 *    live catches — so it is worded as a reading and, when it CONTRADICTS the
 *    reply, shown the sentence it was made on. `TheReplysHalf` carries that
 *    argument and the measurements behind it.
 * 3. **A control.** Page 23.4: "Prose that says 'you should probably try
 *    retrieval first' hands the work back to the person who came here because
 *    they did not know how to do it." Every tool is also a control, and a
 *    button is the one thing a paragraph is structurally incapable of being.
 *
 * `say` is the half that CAN be a repetition, because `standing_brief` hands
 * the engine's sentence to the model on every turn with a non-empty ledger —
 * *"the engine says: {say}"* — so the model has read it before it writes. When
 * a card in this thread has already printed those exact words, this card links
 * to that card instead of printing them a third time. What it never does is
 * touch the reply: this whole commit exists because deleting true sentences
 * from the transcript cost one turn in seven, and a frontend that deleted
 * paragraphs instead would be the same defect one layer down.
 *
 * ══ AND THE CASE WHERE THE WHOLE ENGINE HALF IS ALREADY DRAWN ══════════════
 *
 * When the model runs `run_diagnosis` and then settles the question, the card
 * that tool produced and this event are built from ONE payload — `_Standing`
 * is replaced by any result stamped `decided_by: app/diagnosis.py`. Found by
 * looking, on a real thread: the first cut drew the gate line, the claims
 * block and the `measure_baseline` control directly under a diagnosis card
 * that had just drawn all three, in a fuller form. That is precisely "the same
 * thing in a box", and the box was the smaller copy.
 *
 * So the whole engine half stands down, not just `say`, and what is left is
 * the badge, a line saying where the answer is, and the reply's half. Matched
 * on the engine's own OUTCOME ID rather than on the sentence: the id is the
 * string `docs/diagnosis_engine.yaml` declares, so "is this answer already on
 * screen?" is a lookup, and no renderer is asked whether two things mean the
 * same.
 *
 * ══ WHAT I DID NOT FIX, SAID HERE RATHER THAN LEFT TO BE FOUND ═════════════
 *
 * A quoted sentence prints the model's RAW text, so a bullet the reply set in
 * bold arrives here as `**Assess Data Needs**: Profile your dataset…`, marks
 * and all — visible in the live screenshots. That is deliberate rather than
 * missed: `reads_as_a_verdict` ran on that exact string, and a reader judging
 * whether the reading was fair should see what the parser saw. Rendering the
 * markdown would make the quote prettier and the evidence weaker. It is still
 * the ugliest thing on the card, and if it is ever changed the argument above
 * is the one to answer.
 *
 * It is also now confined to the case that needs it. The quote appears only
 * where the harness is CONTRADICTING the reply, which is the only place a
 * reader has to check the parser's work — so the raw marks are on screen
 * exactly when they are evidence, and never when they are decoration on a
 * sentence the reader has just read. `TheReplysHalf`, below.
 *
 * ══ AND `agrees` SETS THE TONE, NEVER THE PRESENCE ═════════════════════════
 *
 * The card is drawn on agreement too. `verdict_annotation`: "A card that only
 * ever appeared over a disagreement would BE the verdict: its presence would
 * read as an alarm, and a reader would learn to skip it when it says the
 * engine agrees." An absence would then be a claim we made silently and never
 * checked. So both are drawn, the word and the glyph carry the difference, and
 * neither spends a hue — page 23.8 rule 3's argument pointed at the model: the
 * harness did not test the model and find it wanting, it read a sentence and
 * formed a view, and red would claim more than that.
 */

export function EngineVerdictCard({
  item,
  engineIsOnACardAbove,
  sayIsOnACardAbove,
  threadId,
  tools,
  runTool,
}: {
  item: VerdictItem;
  /** True when a `run_diagnosis` card EARLIER in this thread is drawing THIS
   *  OUTCOME — the ordinary case on a turn where the model ran the diagnosis
   *  and then settled the question, because that card and this event are one
   *  payload. Everything the engine has to say is then already on screen, in a
   *  fuller form than this card can carry: five gate rows with their evidence,
   *  every fact's origin, and the same controls. So the engine half of this
   *  card stands down and the reply half — which is nowhere else — is what it
   *  draws. Matched on the engine's own outcome id in `Transcript`, never on
   *  whether two renderings look alike. */
  engineIsOnACardAbove: boolean;
  /** The weaker case: `say` alone is already on a card above, from an earlier
   *  turn that reached the same finding. The sentence is not printed again; the
   *  gate line and the controls are, because that card is showing a different
   *  walk. */
  sayIsOnACardAbove: boolean;
  threadId: number | null;
  tools: Map<string, ToolControl>;
  runTool: RunTool;
}) {
  /* ONE CONTROL PER TOOL, NOT ONE PER FACT. The engine sends up to two
     `unsubstantiated` rows and both can name the same instrument — the live
     case is `measure_baseline` answering `baseline_measured` AND
     `baseline_score`, which drew the same button twice. `GateRow` above
     already learned this lesson once and wrote it down: "the card said the
     same paragraph and drew the same button twice, which is 90px of card spent
     on nothing". One run settles both facts, so one button says so and names
     both. Order is the engine's own — first row first. */
  const steps: { tool: string; facts: string[] }[] = [];
  for (const step of item.nextSteps) {
    const already = steps.find((row) => row.tool === step.tool);
    if (already) {
      if (step.fact && !already.facts.includes(step.fact)) already.facts.push(step.fact);
    } else {
      steps.push({ tool: step.tool, facts: step.fact ? [step.fact] : [] });
    }
  }
  const facts = steps.reduce((total, row) => total + row.facts.length, 0);

  return (
    <div className="card card--verdict" data-agrees={item.agrees}>
      <div className="card__head">
        <Icon name="gauge" />
        <span className="card__kicker">Engine verdict</span>
        <span className="card__headright">
          {/* THE AUTHORITY, PRINTED. This is the half of the card a paragraph
              cannot carry: the same sentence from the engine and from the
              model are two different claims, and this is which one this is. */}
          <span
            className="vcard__by mono"
            title="Computed by the diagnosis engine walking this thread's fact ledger. Not written by the model."
          >
            {item.decidedBy || 'app/diagnosis.py'}
          </span>
        </span>
      </div>

      <div className="card__body">
        {item.verdict ? (
          <div className="card__headline">
            <VerdictPill verdict={item.verdict} />
            {item.outcome ? <span className="mono card__outcome">{item.outcome}</span> : null}
          </div>
        ) : null}

        {/* The engine's sentence. Verbatim or not at all — never trimmed to
            fit, never re-worded, and never printed twice in one thread. */}
        {engineIsOnACardAbove ? (
          <p className="vcard__same">
            <Icon name="info" size={12} />
            <span>
              The engine&rsquo;s answer for this turn is the diagnosis card above &mdash;
              that walk, its five gates and its next steps. Not drawn twice. What follows is
              how the reply read against it.
            </span>
          </p>
        ) : item.say && !sayIsOnACardAbove ? (
          <p className="card__text">{item.say}</p>
        ) : item.say ? (
          <p className="vcard__same">
            <Icon name="info" size={12} />
            <span>
              The engine&rsquo;s sentence is one a diagnosis card above already states, word
              for word. It is not printed a second time.
            </span>
          </p>
        ) : (
          <p className="card__absent">
            {item.computed
              ? 'The engine returned no note for this outcome. say was empty on the wire, and nothing here writes one.'
              : 'The diagnosis could not be computed for this thread, so there is no verdict to stand beside this reply — which is itself why a verdict in the reply cannot rest on this harness.'}
          </p>
        )}

        {/* The gate line, exactly as `_gate_line` wrote it. Nothing here counts
            gates: a ledger this surface assembled would be a second copy of the
            product's central guarantee, drifting from the first. The five rows
            are not on this event, and the line says which card draws them. */}
        {item.gates && !engineIsOnACardAbove ? (
          <div className="vcard__gates">
            <Icon name="check" size={12} />
            {/* THE LABEL IS LOAD-BEARING AND WAS MISSING. Found by looking: the
                check glyph alone in front of "no gate was reached" reads as
                "this passed", which is a status the engine did not compute —
                the exact confusion `_gate_line` exists to prevent, arriving
                through an icon instead of through a word. The big card's
                ledger header carries the same glyph under the same label. */}
            <span className="vcard__gatelabel">Gate ledger</span>
            <span className="vcard__gateline">{item.gates}</span>
            <span className="vcard__gatenote">
              per-gate rows are not on this event; <span className="mono">run_diagnosis</span>{' '}
              draws all five
            </span>
          </div>
        ) : null}

        <TheReplysHalf item={item} />

        {steps.length > 0 && !engineIsOnACardAbove ? (
          <div className="unsub unsub--small">
            {/* The big card's own header, word for word, because it is the same
                block: claims the engine would not take on trust. Counted over
                the FACTS rather than the rows, because one tool can settle two
                of them and the sentence is about the claims. */}
            <div className="unsub__head">
              <Icon name="eye" size={12} />
              <span>
                {facts === 1 ? 'A claim I have not seen' : `${facts} claims I have not seen`}
              </span>
            </div>
            {steps.map((step) => (
              <div className="unsub__row" key={step.tool}>
                <div className="unsub__title">
                  {step.facts.map((fact) => (
                    <span className="mono unsub__fact" key={fact}>
                      {fact}
                    </span>
                  ))}
                </div>
                <NextStepControl
                  step={{
                    /* The fact the CONTROL is keyed on. `NextStepControl` uses
                       it to key `state_facts`' object argument, so it must be
                       one name and not a list; the others this run settles are
                       named beside the button rather than inside it. */
                    fact: step.facts[0],
                    tool: step.tool,
                    /* NOT ON THE WIRE, SO NOT GUESSED. `run_as` decides the
                       glyph and the "in your own person" note; this event
                       carries the tool and the fact and nothing else, and a
                       door label a renderer invented would be a claim about
                       provenance made by the one layer that cannot know it.
                       `POST /api/tools/{name}` hard-codes `actor=USER` either
                       way, so the omission costs a label and never mislabels
                       one. */
                    run_as: null,
                    /* The registry's own imperative — the same string the tool
                       rows are labelled with. `NextStepControl` falls back to
                       "Run it" when the catalogue has not loaded, rather than
                       inventing a sentence for a tool. */
                    verb: tools.get(step.tool)?.verb ?? '',
                    declared_source: '',
                    substantiation: '',
                  }}
                  claimed={undefined}
                  threadId={threadId}
                  control={tools.get(step.tool) ?? null}
                  runTool={runTool}
                />
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

/**
 * What the REPLY said, and what the harness read it as — the half of this card
 * that is nowhere else on screen.
 *
 * THE READING IS QUOTED AGAINST ITS EVIDENCE — WHEN THE READING IS CONTESTED,
 * WHICH IS NOT EVERY TIME.
 *
 * `reads_as_a_verdict` is a parser over grammar, `app/conductor.py` puts its
 * live error rate in writing, and a card that asserted "this reply settles on
 * TRAIN" without showing the sentence it read that way would be asking to be
 * believed about the one thing on this card that is an inference rather than a
 * record. That is the case FOR the quote and it is a real one. Max's standing
 * complaint is the case against: *"the verdict card and the assistant prose
 * say the same thing verbatim"*, and this block is where a card can do that to
 * him worst — the model's own sentence, printed six lines under the paragraph
 * it came out of.
 *
 * Both are true, of two DIFFERENT situations, and the first cut of this card
 * treated them as one:
 *
 * - **The harness is contradicting the reply.** The card has just told the
 *   reader that a paragraph they read as helpful settles on something the
 *   engine did not reach. That claim picks one sentence out of a whole reply,
 *   and *which one* decides whether the reader believes it. The live catch in
 *   `.fleet-verify-shell/verdict-live-dark-card.png` is the whole argument in
 *   one screenshot: the card says TRAIN, and the quote under it is
 *   `**Assess Data Needs**: Profile your dataset…` — a bullet about profiling
 *   data. A reader who sees the quote can see the reading is a stretch. A
 *   reader who sees only "this reply reads as settling on TRAIN" has to take
 *   the harness's word for it, about a parser its own author says was wrong in
 *   three of three live catches.
 * - **The harness agrees with the reply.** Nothing is contested. The engine's
 *   answer is on this card, the model's is in the paragraph above it, and they
 *   are the same answer. The quote is then the shortest possible way to say
 *   what the reader has just finished reading — and unlike the diagnosis card,
 *   this card can never have deleted it. `conductor.verdict` arrives AFTER the
 *   reply and this surface never touches prose, so the evidence is a few lines
 *   up whatever happens: in the reply itself, or — in the one case
 *   `sentencesAlreadyOnCards` suppressed the reply's copy — printed word for
 *   word on the card that suppressed it, which is nearer still. Measured on
 *   the agreeing thread in `.fleet-verify-shell/vq-after-agree-dark.png`: the
 *   reply is 178 characters, one line, and its bottom edge is 8px above this
 *   card. Reprinting it is not what makes it checkable; proximity already did.
 *
 * SO THE QUOTE IS DRAWN ONLY WHERE IT IS EVIDENCE. This is `GateRow`'s and the
 * per-row token's own rule one level up: draw the thing when it distinguishes
 * something. The card draws less than it did, on the half of its turns where
 * what it was drawing was the paragraph above it.
 *
 * THE BOUNDARY IS `agrees` AND IT WAS CHECKED RATHER THAN ASSUMED, because a
 * rule that hid evidence in a case that needed it would be the worse defect.
 * `_Settled.agrees_with` is `all(row["verdict"] == engine)`, so:
 *
 * - A reply that said TRAIN and then NO_TRAIN cannot be an agreement — the
 *   `mixed` case, where the per-row tokens are the most important thing on the
 *   card, is inside the quoted half by construction.
 * - A turn where the engine computed NOTHING cannot be an agreement either,
 *   since no row's verdict equals `None`. A card that is ALL reading and no
 *   engine therefore keeps its evidence, which is the case that most needs it.
 *
 * THREE OTHER WAYS TO SPEND THIS SPACE, AND WHY NOT THEM. *Quote only the
 * fragment that triggered the reading*: `_settles_span` knows that span and the
 * event does not carry it, so this surface would have to re-find the words the
 * parser matched — a renderer inventing the evidence for a claim, which is the
 * one thing every rule in this file forbids. It is worth doing in the engine,
 * and it is reported rather than faked here. *Collapse it behind a disclosure*:
 * a chevron on every agreeing card is a control that promises something, and
 * what is behind it is a sentence the reader read a moment ago; they learn once
 * that it is never worth opening and then they skip the card. *Drop it
 * entirely*: that takes the evidence away from the disagreement too, and the
 * disagreement is the event this whole card exists to make visible.
 */
function TheReplysHalf({ item }: { item: VerdictItem }) {
  /* THE ENGINE'S OWN WORD, not a paraphrase of it. The first cut printed
     "settling on train", which reads as a typo mid-sentence and is a word this
     surface chose; `TRAIN` is the token `reads_as_a_verdict` returned and the
     token a reader will find in `app/conductor.py`. Page 23.3's rule about
     gates — "the interface never paraphrases" — for the same reason: a person
     who reads the card and then reads the code must find the same word. */
  const read = item.asserted;
  const mixed = new Set(item.sentences.map((row) => row.verdict)).size > 1;
  /* The evidence, drawn where it is evidence. `agrees` and nothing else: the
     long note above is why, and `_Settled.agrees_with` is why `mixed` and an
     uncomputed engine are both on this side of the test. */
  const quoted = item.agrees ? [] : item.sentences;
  /* THE CARD USED TO CONTRADICT ITS OWN BADGE HERE, and it was found by
     screenshotting the case rather than by reading the code. `agrees_with`
     requires EVERY sentence to match, so a reply that says TRAIN and then
     NO_TRAIN against an engine that said NO_TRAIN is `agrees: false` with
     `asserted: NO_TRAIN` — and the disagreement wording then printed *"This
     reply reads as settling on NO_TRAIN. The engine, walking this thread's own
     ledger, did not."* directly under a pill reading DO NOT TRAIN /
     NO_TRAIN__SHIP_AS_IS. The engine had; the reply had simply not held it
     throughout, which is a different and more interesting thing.

     `asserted` is where the reply LANDED and `agrees` is whether it stayed
     there, so the two disagree on exactly this shape and nowhere else: if
     every row matched `asserted` and `asserted` matched the engine, `agrees`
     would be true. The rows carry their own tokens underneath, which is where
     the reader sees the turn happen. */
  const landedTogether = !item.agrees && read !== null && read === item.verdict;
  return (
    <div className="vread">
      <p className="vread__head">
        <Icon name={item.agrees ? 'check' : 'eye'} size={12} />
        <span>
          {item.agrees ? (
            <>
              The reply above reached the same answer
              {read ? (
                <>
                  {' '}
                  &mdash; it <em>reads as</em> settling on{' '}
                  <span className="mono vread__verdict">{read}</span>, and so did the engine
                </>
              ) : null}
              .
            </>
          ) : landedTogether ? (
            <>
              This reply lands on <span className="mono vread__verdict">{read}</span>, where
              the engine landed &mdash; but it settles the question more than once, and not
              every sentence <em>reads as</em> the same answer.
            </>
          ) : (
            <>
              This reply <em>reads as</em> settling on{' '}
              <span className="mono vread__verdict">{read ?? 'nothing'}</span>. The engine,
              walking this thread&rsquo;s own ledger, did not.
            </>
          )}
        </span>
      </p>
      {quoted.length > 0 ? (
        <ul className="vread__list">
          {quoted.map((row, index) => (
            <li className="vread__row" key={`${index}:${row.sentence.slice(0, 24)}`}>
              <q className="vread__said">{row.sentence}</q>
              {/* THE PER-ROW TOKEN ONLY WHEN IT DISTINGUISHES SOMETHING. With
                  one sentence, or several the reader read the same way, the
                  line above has already named the verdict and a tag on every
                  row is the same word printed twice. When they DIFFER it is
                  the most important thing on the card: `agrees_with` requires
                  every sentence to match, so a reply that said TRAIN and then
                  NO_TRAIN disagreed whatever it ended on, and the rows are
                  where a reader sees that happen. */}
              {mixed && row.verdict ? (
                <span className="vread__as mono">{row.verdict}</span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
