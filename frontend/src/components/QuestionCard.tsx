/**
 * ONE QUESTION, AS A CARD WITH A FIELD — because the prose round-trip is where
 * the provenance is lost.
 *
 * Max, 2026-08-20: *"When the bot asks these questions they should pop up the
 * same [way] Claude asks questions and they pop up. This pop-up collects each
 * bit of information that they need in order to build the user what they need.
 * Simple, straightforward."*
 *
 * ══ THIS IS NOT A COSMETIC REQUEST ═════════════════════════════════════════
 *
 * The harness needs a fact. It asks for it in prose. The user answers in prose.
 * The model writes the answer down with `state_facts` — and because a model is
 * not a witness to the user's own week, the fact arrives ASSERTED. A fact the
 * ledger declares `source: inspect` cannot open a gate when it is ASSERTED
 * (`fact_origins.admissible_for_gates`), so the gate does not move and the
 * conversation goes round again.
 *
 * Max's own transcript, the morning this was written: he wrote *"I have
 * something like 1000 tickets with full information within them tracked to
 * clients, reasons and so on"* and the harness recorded **1 fact ASSERTED**. It
 * never offered to go and count them. He had the data. He would have pointed at
 * it if asked.
 *
 * A TYPED CARD CHANGES THE KIND OF THING AN ANSWER IS:
 *
 *   - a number typed into a field, by the person whose project this is, through
 *     `POST /api/tools/{name}` — which hard-codes `actor=USER` — arrives
 *     **STATED**, and STATED is admissible for every `source: ask` fact;
 *   - a path chosen in a picker is not a value at all. It is a location, and a
 *     tool then goes and **MEASURES** the fact, which is the only origin a
 *     `source: inspect` fact will ever accept.
 *
 * Neither of those is reachable through a paragraph. That is the whole argument
 * for this component.
 *
 * ══ THE WALL, STATED BEFORE ANYTHING ELSE ══════════════════════════════════
 *
 * **A card that let a user type a value into a `source: inspect` fact and open
 * a gate with it would be the whole product defeated by a form.** An adversary
 * will try it, and so will an ordinary bug.
 *
 * `mayBeTyped()` below is the wall. A typed field is drawn only when the
 * engine's own `resolves()` answer says `run_as: "user"` **and** the ledger's
 * own `source:` for that fact is `ask`. Both, always. Either one alone is a
 * single point of failure: `resolves()` could change its tie-break next year,
 * and a `declared_source` could arrive from a stale catalogue. When they
 * disagree the card draws nothing rather than a field, because failing closed
 * is the only direction this may fail in.
 *
 * The server-side walls are still there and are still the ones that count —
 * `state_facts` records at the caller's own worth, `evidence.record` refuses an
 * inadmissible stamp, and the gate rule masks an inadmissibly-originated fact
 * back to its unsupplied reading before it will pass a row. This card adds a
 * fourth wall in the surface a person actually touches; it does not replace
 * any of the three.
 *
 * ══ THE QUESTION IS DERIVED, NEVER WRITTEN BY HAND ═════════════════════════
 *
 * There is no list of questions in this file and there must never be one. A
 * hand-written list would drift from `docs/diagnosis_engine.yaml` the first time
 * a fact changed, which is exactly how "the only scoring tool", the stale
 * roadmap and the capability undersell all happened in this repository.
 *
 * Every part of the question already exists as data on the wire:
 *
 *   what          where it comes from
 *   ────────────  ────────────────────────────────────────────────────────────
 *   which fact    `gate_ledger[g].clause` — the gate row's `requires`
 *                 expression, verbatim — intersected with `fact_origins`,
 *                 which `resolve_facts` guarantees holds **every declared
 *                 fact**. So the legal fact names come from the engine, not
 *                 from a constant here.
 *   which gate    the first entry of `gate_ledger` the walk actually REACHED
 *                 and did not pass. A NOT_REACHED gate is not the frontier —
 *                 `conductor._gate_line` learned that one the expensive way and
 *                 the reasoning is quoted at `frontierGate` below.
 *   which tool    `unsubstantiated[].next_step`, which is `evidence.resolves()`
 *                 — derived from the registry's own `measures=` declarations.
 *                 Where the engine sent no such row, the same derivation runs
 *                 here over `GET /api/tools`, which carries `measures` for
 *                 every tool. Same declarations, same tie-break, no list.
 *   the wording   the tool's own `verb` and `label`, and the ledger's own
 *                 `substantiation` sentence. Nothing on this card is a
 *                 sentence this file composed about a fact.
 *   the default   NOT ON THE WIRE, and the card says the em dash rather than a
 *                 number because of it. Measured rather than assumed:
 *                 `facts_used` is built from the evidence TRAIL, a defaulted
 *                 fact was never recorded in the ledger, so it is never in the
 *                 trail — and `evidence.declaration()` returns `accepts`,
 *                 `settled_by` and the admissible origins but not `default`.
 *                 One field on that function turns "eval_size_n stays —" into
 *                 "eval_size_n stays 0 DEFAULT". Until it exists this card
 *                 refuses to print a zero it does not hold, which is Graphite
 *                 13.5 rule 2 and invariant 5 agreeing with each other.
 *
 * ══ WHICH QUESTION, AND WHY THAT ORDER ═════════════════════════════════════
 *
 * `docs/PRODUCT_SPEC.md` §9.8 gives the algorithm and this implements that one
 * rather than inventing a second:
 *
 *   1. Find the frontier — the first node whose condition you cannot evaluate.
 *   2. Collect the facts that node's condition references.
 *   3. Drop every one you could inspect instead, and go inspect them.
 *   4. Of what remains, rank by how many branches the answer eliminates.
 *   5. Ask the top one. Just that one.
 *
 * Step 3 is the one that shapes this component. "Drop and go inspect" is not a
 * question at all — it is the harness doing the work — so an inspectable fact
 * outranks every askable one, and what it needs from the person is the one
 * thing no tool can see: *where to look*. That is the PICKER, and it is what
 * Max meant by "upload data, read data". Only when nothing at the frontier is
 * inspectable does the card ask a question in the ordinary sense.
 *
 * Step 4 is honest about its own limit. The true branch count needs the parsed
 * conditions, which the engine holds and does not send. What the wire supports
 * is **how many gate rows in this run's own ledger name the fact** — two gates
 * reading a fact is more branches eliminated than one — and that is what
 * `gatesReading` counts. It orders questions; it is never displayed, and it is
 * not a measurement of anything.
 *
 * ══ THE THREE SHAPES ═══════════════════════════════════════════════════════
 *
 * - **A FIELD**, when the person's own word is the evidence. A number, a choice
 *   from an enum, a yes/no. It lands STATED.
 * - **A PICKER**, when the harness must go and measure. The answer is a path,
 *   not a value. It lands MEASURED, and it is the tool that measures, not the
 *   person who typed.
 * - **"I DON'T KNOW"**, always available, never buried, and it does not look
 *   like failure. §9.8: "take the conservative default, record it in the ledger
 *   as an assumption, and surface it in the assumptions list on the next
 *   verdict card. Never let an assumption disappear into the reasoning
 *   silently."
 *
 *   Mechanically, taking the default means **sending nothing**. `resolve_facts`
 *   refuses a caller who supplies the DEFAULTED origin — "only the engine may
 *   say that. Leave the fact out to get the default." So this card leaves it
 *   out, and says on screen what leaving it out will do, using the engine's own
 *   defaulted value. A default the user cannot see is a number we invented on
 *   their behalf.
 *
 * ══ WHY IT IS A CARD AND NOT A ROW IN THE VERDICT CARD ═════════════════════
 *
 * `DiagnosisCard`'s `Unsubstantiated` block already lists **every** claim the
 * engine could not vouch for, each with a `NextStepControl` folded behind a
 * phase toggle. That is the right shape for a ledger and the wrong shape for a
 * question: §9.8 says *ask one*, and "a form asks six; you are not a form".
 * This is the one-question surface. It draws exactly one, it draws it open, and
 * it goes away when there is nothing to ask.
 *
 * ══ GRAPHITE ══════════════════════════════════════════════════════════════
 *
 * Page 11.9 says "a field is an override, not a question — the harness knows
 * the process and proposes the next action. It does not interview you." This
 * card is the exception to that sentence and it earns it by obeying the rest of
 * the rule: **every field is presented beside the value it would replace and
 * beside where that value came from.** Here the value it would replace is the
 * ledger's own default, shown with its DEFAULT tag before the person chooses
 * it, and the claim it would correct is shown wearing ASSERTED. A blank box
 * with a grey label in it is a control panel; this is not that.
 *
 * The card's body is page 16.5's mandatory three parts, in order, because an
 * empty-ish surface is where a person decides whether this thing knows what it
 * is doing:
 *   1. **what is true and measured, with its provenance** — the claim somebody
 *      already made, or the default currently in force;
 *   2. **what that means, in one sentence** — the ledger's own `substantiation`
 *      line, verbatim, never paraphrased;
 *   3. **one to three concrete actions as buttons** — answer it, or say you do
 *      not know. No illustration, no encouragement, no exclamation mark.
 *
 * No filled accent button. Page 10: "no fill at all except in the two places
 * the product is asking for a commitment — send, and the primary action of an
 * approval." Answering a question is neither, so both buttons are the ordinary
 * 28px bordered chassis and "I don't know" is exactly as prominent as the other
 * one. That is the design saying it is a legal answer.
 *
 * ══ WHAT THIS CARD NEVER DOES ═════════════════════════════════════════════
 *
 * **It never pre-fills a value a model asserted.** `NextStep.tsx` states the
 * rule and it is the same rule here: pre-filling would take the model's claim,
 * push it through the user's door and hand it back stamped STATED — a one-click
 * laundering of the exact origin the engine spent a wall refusing. The claim is
 * shown BESIDE the field, wearing its tag, as something to disagree with.
 *
 * **It never asks a second question off a stale ledger.** Once an answer is
 * recorded, the verdict this question was derived from is out of date, so the
 * card shows what happened and stops. The next question comes from the next
 * diagnosis, which is the only thing entitled to name it.
 */

import { useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import type {
  DiagnosisPayload,
  FactOrigin,
  FactUsed,
  GateLedgerEntry,
  NextStep,
} from '../lib/engine/facts';
import { ORIGIN_TAG, ORIGIN_WORD, isFactOrigin } from '../lib/engine/facts';
import type { ToolControl, ToolField } from '../lib/engine/types';
import { TAG_TOKEN } from '../lib/format';
import { hasNativeShell, nativePickPath } from '../lib/engine/shell';
import { Button, OriginTag, ProvenanceTag } from './primitives';
import { Icon } from './Icon';
import type { RunTool } from './NextStep';
import './QuestionCard.css';

/* ── What a question is ───────────────────────────────────────────────────── */

/** A field is the person's own word. A picker is a place for a tool to look. */
export type QuestionShape = 'field' | 'picker';

/** How the answer is collected. Derived from the ledger's declaration where the
 *  shell has one, and from the value already in play where it does not. */
export type QuestionInput = 'text' | 'number' | 'bool' | 'enum';

/**
 * One fact's declaration, exactly as `evidence.declaration()` returns it.
 *
 * OPTIONAL, AND THE CARD IS USEFUL WITHOUT IT. Nothing on the wire today
 * carries the ledger's `source:` for a fact the engine did not challenge, so
 * `GET /api/tools` (which carries `measures`) is what covers the inspect side,
 * and `unsubstantiated[].declared_source` is what covers the ask side. A fact
 * that neither of those describes is not asked about at all — see `shapeOf`.
 *
 * When a route grows that serves `evidence.declaration()` for every declared
 * fact, passing it here closes that gap and also upgrades a bare number field
 * to a real enum select. The type is written now so the wiring is a prop.
 */
export interface FactDeclaration {
  fact: string;
  declared: boolean;
  source?: string | null;
  accepts?: { type?: string | null; one_of?: string[]; any_of?: string[] };
  opens_a_gate_when_the_origin_is?: string[];
  settled_by?: { tool?: string | null; run_as?: string | null };
}

/** What the card was told to ask, all of it derived. */
export interface Question {
  fact: string;
  shape: QuestionShape;
  input: QuestionInput;
  /** Enum members, when the ledger declared some and the shell passed them. */
  choices: string[] | null;
  /** The engine's own answer to "what settles this", or the same derivation run
   *  over the registry when the engine sent no row for this fact. */
  step: NextStep;
  /** The frontier gate this answer unblocks, and its `requires` expression
   *  verbatim — page 23: "the right-hand clause is what makes the ledger
   *  checkable by someone who does not trust it". */
  gate: string | null;
  clause: string | null;
  /** What somebody already claimed for this fact. Shown, never used. */
  claimed: FactUsed | null;
  /** The ledger's own default, as the engine reported it, and whether the
   *  engine reported one at all. A default we do not hold is an em dash and no
   *  tag — page 13.5 rule 2 — never a zero.
   *
   *  `known` IS FALSE FOR EVERY FACT ON TODAY'S WIRE. See the header: no route
   *  carries a fact's declared default. The branch is here because the fix is
   *  one field on `evidence.declaration()` and not a redesign, and because a
   *  card that had nowhere to put the default would quietly stop asking for it.
   */
  fallback: { value: unknown; known: boolean };
  /** The origin this answer will carry once it lands. STATED for a field,
   *  MEASURED for a picker, and nothing else is reachable. */
  lands: Extract<FactOrigin, 'STATED' | 'MEASURED'>;
}

/** What the shell is told when somebody takes the default. */
export interface Assumption {
  fact: string;
  value: unknown;
  known: boolean;
  gate: string | null;
}

/* ── Picking the question — PRODUCT_SPEC §9.8, step by step ──────────────── */

/**
 * The one question to ask, or null when nothing at the frontier can be asked.
 *
 * Pure, exported and tested from the outside: which question the harness asks
 * is the load-bearing half of this component and it should be checkable without
 * rendering anything.
 */
export function nextQuestion(
  from: DiagnosisPayload,
  tools: Map<string, ToolControl>,
  catalogue?: Record<string, FactDeclaration>,
): Question | null {
  const frontier = frontierGate(from);
  const names = factsAtFrontier(from, frontier);

  const asked: { question: Question; position: number; branches: number }[] = [];
  names.forEach((fact, position) => {
    const question = shapeOf(fact, from, frontier, tools, catalogue);
    if (question) {
      asked.push({ question, position, branches: gatesReading(from, fact) });
    }
  });
  if (asked.length === 0) return null;

  /* §9.8 STEP 3. "Drop every one you could inspect instead, and go inspect
     them." An inspectable fact is not a question the person has to think about
     — it is work the harness does — so it comes first whenever there is one,
     and the ranking in step 4 applies to what is left over only when there is
     nothing to inspect. */
  const inspectable = asked.filter((row) => row.question.shape === 'picker');
  const pool = inspectable.length > 0 ? inspectable : asked;

  /* §9.8 STEP 4, and see the header for what this count is and is not. Ties
     break on the engine's own order — its challenge list first, then the order
     the facts appear in the gate's own clause — and then on the name, so the
     same ledger always produces the same question. */
  pool.sort(
    (a, b) =>
      b.branches - a.branches ||
      a.position - b.position ||
      a.question.fact.localeCompare(b.question.fact),
  );

  /* §9.8 STEP 5. Just that one. */
  return pool[0].question;
}

/**
 * §9.8 STEP 1 — the frontier.
 *
 * The first gate the walk REACHED and did not pass. A `NOT_REACHED` gate is not
 * the frontier and treating it as one is a defect this repository has already
 * paid for: `app/conductor.py` shipped a brief that "counted all five as unmet
 * and named the first as 'first unmet'" on an empty sheet, and the model quoted
 * `G0_EVAL_SET NOT_REACHED` at Max instead of answering him. `_gate_line` now
 * "reports only gates the walk reached and never invents a status for one it did
 * not", and `clause === null` is precisely how the engine says it never got
 * there.
 *
 * `Object.entries` reads the ledger in the engine's own key order, which is the
 * tree's order, so "first" here is the engine's first and not this file's.
 */
function frontierGate(
  from: DiagnosisPayload,
): { id: string; entry: GateLedgerEntry } | null {
  for (const [id, entry] of Object.entries(from.gate_ledger)) {
    if (entry.status === 'PASSED') continue;
    if (entry.clause === null) continue;
    return { id, entry };
  }
  return null;
}

/**
 * §9.8 STEP 2 — the facts that node's condition references.
 *
 * Two sources, both the engine's:
 *
 *   1. the challenge list. `unsubstantiated[]` is the engine naming the facts
 *      whose origin was not good enough for the row that read them, in its own
 *      order, each already carrying `declared_source` and a `next_step`. This is
 *      Max's case, and it goes first.
 *   2. the gate's own `requires` expression, verbatim. Identifiers are pulled
 *      out of it and kept only when `fact_origins` declares them — and
 *      `resolve_facts` guarantees "every declared fact appears in both", so
 *      that map is the ledger's own list of legal names. `and`, `is`, `null`
 *      and every other word in the expression fall out for free.
 *
 * A fact is dropped when somebody has already answered it admissibly. That is
 * not the same as "the gate passes": a user who admits to one prompt iteration
 * has ANSWERED `prompt_iterations`, the condition evaluates and it evaluates
 * false, and the engine's own rule is that they are "told to go and iterate —
 * never told to substantiate their claim". A task is not a question.
 */
function factsAtFrontier(
  from: DiagnosisPayload,
  frontier: { id: string; entry: GateLedgerEntry } | null,
): string[] {
  const out: string[] = [];
  const add = (name: string) => {
    if (!name || out.includes(name)) return;
    if (!(name in from.fact_origins)) return;
    const challenged = challenges(from).some((row) => row.fact === name);
    if (!challenged && from.fact_origins[name] !== 'DEFAULTED') return;
    out.push(name);
  };

  for (const row of challenges(from)) {
    if (!frontier || row.gate === frontier.id) add(row.fact);
  }
  if (frontier?.entry.clause) {
    for (const word of identifiers(frontier.entry.clause)) add(word);
  }
  return out;
}

/**
 * How many gate rows in THIS run's ledger name the fact.
 *
 * The wire's answer to §9.8's "how many branches the answer eliminates". It is
 * a proxy for that count and it is documented as one in the header: the real
 * number needs the parsed conditions the engine keeps. Used to order questions,
 * never rendered, and never described to anybody as a measurement.
 */
function gatesReading(from: DiagnosisPayload, fact: string): number {
  let n = 0;
  for (const entry of Object.values(from.gate_ledger)) {
    if (entry.clause && identifiers(entry.clause).includes(fact)) n += 1;
  }
  return n;
}

/** Every identifier in an expression. Filtered against `fact_origins` by the
 *  caller, so this deliberately knows nothing about what a fact name is. */
function identifiers(clause: string): string[] {
  return clause.match(/[A-Za-z_][A-Za-z0-9_]*/g) ?? [];
}

/**
 * The engine's challenge list, or none.
 *
 * `run_diagnosis` ONLY ADDS THE KEY WHEN THERE ARE ROWS — `if
 * result.unsubstantiated:` — so a clean payload has no `unsubstantiated` at
 * all. `readDiagnosis` fills it with `[]`, which is why the transcript never
 * saw this; `nextQuestion` is exported and pure and somebody will hand it a raw
 * payload, which is exactly what happened the first time this card was pointed
 * at one. It threw `from.unsubstantiated is not iterable` and the page went
 * blank. Found by looking, not by a type: the type says the field is required
 * and the wire disagrees.
 */
function challenges(from: DiagnosisPayload): DiagnosisPayload['unsubstantiated'] {
  return Array.isArray(from.unsubstantiated) ? from.unsubstantiated : [];
}

/**
 * What shape this fact's question takes — or null, which means do not ask it.
 *
 * Null is the common and correct answer. A fact nothing in the harness settles
 * is a gap in the product and `resolves()` says so in those words; a fact whose
 * declared source this surface cannot see is one it must not guess at. Drawing
 * nothing costs a card. Drawing a field on an `inspect` fact costs the product.
 */
function shapeOf(
  fact: string,
  from: DiagnosisPayload,
  frontier: { id: string; entry: GateLedgerEntry } | null,
  tools: Map<string, ToolControl>,
  catalogue?: Record<string, FactDeclaration>,
): Question | null {
  const challenged = challenges(from).find((row) => row.fact === fact) ?? null;
  const declared = catalogue?.[fact];
  const source = challenged?.declared_source ?? declared?.source ?? null;

  const step = challenged?.next_step ?? resolvesHere(fact, source, tools, declared);
  if (!step || !step.tool) return null;

  const shape: QuestionShape | null =
    step.run_as === 'harness' ? 'picker' : mayBeTyped(step, source) ? 'field' : null;
  if (shape === null) return null;

  const used = from.facts_used[fact] ?? null;
  const defaulted = from.fact_origins[fact] === 'DEFAULTED' && used !== null;

  return {
    fact,
    shape,
    input: inputFor(shape, declared, used),
    choices: choicesFor(declared),
    step,
    gate: challenged?.gate ?? frontier?.id ?? null,
    clause: frontier?.entry.clause ?? null,
    claimed: used && !defaulted ? used : null,
    fallback: { value: defaulted ? used?.value : undefined, known: defaulted },
    lands: shape === 'picker' ? 'MEASURED' : 'STATED',
  };
}

/**
 * THE WALL. Whether this fact may be answered by typing.
 *
 * Two independent readings have to agree: the engine's own `resolves()` answer
 * has to say the door is the user's, AND the ledger's own `source:` for the
 * fact has to be `ask`. `fact_origins.admissible_for_gates` is the reason —
 * `ask` admits STATED, `inspect` and `derive` admit MEASURED and nothing else —
 * so a typed field on anything but an `ask` fact is at best a wasted round and
 * at worst the five-gate test defeated by a form.
 *
 * When the two disagree, or when the source is simply not known here, this
 * returns false and the card draws nothing. Failing closed is the only
 * direction a check like this may fail in, and it is the same reading
 * `evidence.origin_for` takes of an unknown actor.
 */
function mayBeTyped(step: NextStep, source: string | null): boolean {
  return step.run_as === 'user' && source === 'ask' && step.declared_source === 'ask';
}

/**
 * `evidence.resolves()`, run here, for a fact the engine sent no row for.
 *
 * SAME DECLARATIONS, SAME TIE-BREAK, NO LIST. The Python sorts the tools that
 * declare `measures=` containing this fact by "the one that asks least of the
 * user wins" — fewest facts measured, then fewest schema properties, then the
 * control's own order, then the name — and `GET /api/tools` carries all four.
 * A tool registered next year measuring `corpus_tokens` becomes the answer to a
 * question about `corpus_tokens` on the day it is registered, here as much as
 * there, with nothing in this file to update.
 *
 * The `ask` branch is NOT reconstructed here. `resolves()` answers `state_facts`
 * for a fact no tool measures, and knowing that requires the ledger's `source:`
 * — so it is taken from the catalogue's own `settled_by`, which is that same
 * function's answer computed on the server, or it is not taken at all. There is
 * no tool name written in this file.
 */
function resolvesHere(
  fact: string,
  source: string | null,
  tools: Map<string, ToolControl>,
  declared?: FactDeclaration,
): NextStep | null {
  const settled = declared?.settled_by;
  if (settled?.tool) {
    const control = tools.get(settled.tool);
    return {
      fact,
      declared_source: source ?? '',
      tool: settled.tool,
      run_as: settled.run_as === 'user' ? 'user' : 'harness',
      verb: control?.verb ?? '',
      substantiation: '',
    };
  }

  const candidates = [...tools.values()].filter((control) =>
    control.measures.includes(fact),
  );
  if (candidates.length === 0) return null;
  candidates.sort(
    (a, b) =>
      a.measures.length - b.measures.length ||
      a.fields.length - b.fields.length ||
      a.order - b.order ||
      a.name.localeCompare(b.name),
  );
  const first = candidates[0];
  return {
    fact,
    declared_source: source ?? '',
    tool: first.name,
    run_as: 'harness',
    verb: first.verb,
    substantiation: '',
    also: candidates.slice(1).map((control) => control.name),
  };
}

/**
 * Which control collects the answer.
 *
 * The ledger's declaration wins when the shell has it. Otherwise the shape is
 * read off the value ALREADY IN PLAY — which for an unanswered fact is the
 * ledger's own default, applied by the engine and reported back — because the
 * type of the default is the type of the fact. Where there is neither, it is a
 * text field and `app/diagnosis.py`'s own coercion error is what the person
 * reads, exactly as `NextStep.tsx` decided for the same reason: better the
 * engine's message than a value this file guessed at.
 */
function inputFor(
  shape: QuestionShape,
  declared: FactDeclaration | undefined,
  used: FactUsed | null,
): QuestionInput {
  if (shape === 'picker') return 'text';
  const accepts = declared?.accepts;
  if (accepts?.one_of?.length || accepts?.any_of?.length) return 'enum';
  const type = accepts?.type;
  if (type === 'bool') return 'bool';
  if (type === 'int' || type === 'float') return 'number';
  if (type) return 'text';
  if (typeof used?.value === 'boolean') return 'bool';
  if (typeof used?.value === 'number') return 'number';
  return 'text';
}

function choicesFor(declared: FactDeclaration | undefined): string[] | null {
  const accepts = declared?.accepts;
  const members = accepts?.one_of ?? accepts?.any_of;
  return members && members.length > 0 ? [...members] : null;
}

/* ── The card ─────────────────────────────────────────────────────────────── */

export function QuestionCard({
  from,
  question: given,
  frontierExhausted,
  threadId,
  tools,
  runTool,
  catalogue,
  workspaceRoot,
  onAnswered,
  onAssumed,
}: {
  /** The verdict this question is derived from. Everything the card asks comes
   *  out of this payload and the tool catalogue; nothing is composed here. */
  from: DiagnosisPayload;
  /**
   * A question the ENGINE picked, when the engine is picking them.
   *
   * `app/asking.py` landed in a sibling lane while this was being built, and it
   * is the same algorithm on the other side of the wire — `next_question`,
   * `frontier`, a `Question` whose `__post_init__` refuses to construct a card
   * whose answer would arrive under an origin the ledger does not admit. It
   * holds the two things this side cannot see: the ledger's own DEFAULT for a
   * fact (`DontKnow.takes`), and the frontier NODE's condition rather than only
   * the frontier GATE's.
   *
   * IT IS ON THE WIRE NOW — `frontend/src/lib/engine/asking.ts` reads the
   * payload and `App.tsx` maps it onto `Question`. `nextQuestion` below is the
   * FALLBACK, for when the engine has not answered; see `frontierExhausted` for
   * the case where it has answered and has nothing to ask.
   */
  question?: Question | null;
  /**
   * THE ENGINE ANSWERED AND HAD NOTHING TO ASK.
   *
   * `kind: 'propose'` on `GET /api/next_step` — the frontier is exhausted
   * because the facts it wanted are in the ledger. It is NOT the same as the
   * engine being silent, and reading the two as one null is what put a card
   * on screen saying a measured fact "has not been answered in this thread".
   * When this is true the fallback derivation is suppressed and the card
   * renders nothing.
   */
  frontierExhausted?: boolean;
  /** The open conversation. A fact measured with no thread is MACHINE scope and
   *  visible in every conversation, which is right for "this box has 8 GB of
   *  VRAM" and wrong for "the eval set has 120 rows". */
  threadId: number | null;
  tools: Map<string, ToolControl>;
  /** `POST /api/tools/{name}`, which hard-codes `actor=USER`. That is the whole
   *  reason a value collected here is STATED and the same value from a model is
   *  ASSERTED. */
  runTool: RunTool;
  catalogue?: Record<string, FactDeclaration>;
  /** The open project's folder on disk, when it has one. Offered — never
   *  auto-filled — on a picker's path fields. A path the USER attached to the
   *  project is the user's own word, so a click that copies it into the field
   *  launders nothing; the wall in the header is about MODEL claims. */
  workspaceRoot?: string | null;
  /** An answer landed. The shell asks the engine again; this card does not,
   *  because a card is not entitled to spend the user's tokens. */
  onAnswered?: (fact: string) => void;
  /** The person said they do not know. §9.8: the assumption is recorded and
   *  surfaced on the next verdict, never allowed to disappear silently. */
  onAssumed?: (assumption: Assumption) => void;
}) {
  const derived = useMemo(
    () => nextQuestion(from, tools, catalogue),
    [from, tools, catalogue],
  );
  /* THE FALLBACK IS FOR SILENCE, NOT FOR "NOTHING TO ASK".
     `given` is null in two unrelated situations and this read them as one:
     the engine has not answered (no payload, a failed fetch, a payload the
     reader refused), and the engine HAS answered with `kind: 'propose'` —
     the frontier is exhausted because the facts it wanted are in the ledger.
     In the first, deriving a card here is the honest fallback it has always
     been. In the second it is a FALSEHOOD: `nextQuestion` reads the FROZEN
     diagnosis snapshot this card was rendered beside, so on a thread where
     `eval_size_n` had been measured at 150 the card said "eval_size_n — has
     not been answered in this thread", about a fact the ledger held, and it
     survived a reload. A product whose whole subject is where a number came
     from cannot tell somebody a fact is unanswered while its own ledger
     holds it. */
  const question = given ?? (frontierExhausted ? null : derived);
  if (!question) return null;
  return (
    <Ask
      /* A new fact is a new question, so the typed value, the phase and the
         error all reset. Without this the answer to one question would be
         sitting in the field of the next one. */
      key={question.fact}
      question={question}
      control={question.step.tool ? tools.get(question.step.tool) ?? null : null}
      threadId={threadId}
      runTool={runTool}
      workspaceRoot={workspaceRoot ?? null}
      onAnswered={onAnswered}
      onAssumed={onAssumed}
    />
  );
}

type Phase = 'asking' | 'running' | 'answered' | 'assumed';

function Ask({
  question,
  control,
  threadId,
  runTool,
  workspaceRoot,
  onAnswered,
  onAssumed,
}: {
  question: Question;
  control: ToolControl | null;
  threadId: number | null;
  runTool: RunTool;
  workspaceRoot: string | null;
  onAnswered?: (fact: string) => void;
  onAssumed?: (assumption: Assumption) => void;
}) {
  const [phase, setPhase] = useState<Phase>('asking');
  const [values, setValues] = useState<Record<string, string>>({});
  const [problem, setProblem] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<{
    ok: boolean;
    error: string | null;
    result: unknown;
  } | null>(null);

  /* WHAT THE ANSWER IS PUT INTO. For a picker it is the measuring tool's own
     required arguments, straight off the schema the model is handed, so the
     control and the tool call cannot disagree about what an argument is. For a
     field it is the single slot the fact goes in. */
  const slots: ToolField[] =
    question.shape === 'picker'
      ? (control?.fields ?? []).filter((field) => field.required)
      : [];

  const answer = (values[ANSWER] ?? '').trim();
  const filled =
    question.shape === 'picker'
      ? slots.length > 0 && slots.every((field) => (values[field.name] ?? '').trim() !== '')
      : answer !== '';

  async function send() {
    setProblem(null);
    let args: Record<string, unknown>;
    try {
      args = argumentsFor(question, control, values);
    } catch (failure) {
      setProblem(failure instanceof Error ? failure.message : String(failure));
      return;
    }
    setPhase('running');
    const result = await runTool(question.step.tool as string, args, threadId);
    setOutcome(result);
    setPhase('answered');
    if (result.ok && !result.error) onAnswered?.(question.fact);
  }

  function dontKnow() {
    /* NOTHING IS SENT. `resolve_facts` refuses a caller who supplies DEFAULTED:
       that origin means the engine applied the ledger's own default and only
       the engine may say so. Leaving the fact out IS taking the default, and it
       is the only way to take it honestly. */
    setPhase('assumed');
    onAssumed?.({
      fact: question.fact,
      value: question.fallback.value,
      known: question.fallback.known,
      gate: question.gate,
    });
  }

  return (
    <section className="card card--question" aria-label="One question" aria-live="polite">
      <div className="card__head">
        <Icon name={question.shape === 'picker' ? 'folder' : 'user'} size={14} />
        <span className="card__kicker">Question</span>
        {question.gate ? (
          <span className="card__headright qcard__opens">
            opens <span className="mono">{question.gate}</span>
          </span>
        ) : null}
      </div>

      <div className="card__body">
        {/* ONE GROUP. The headline and the state of play are the same thought —
            what is being asked, and what is standing in for the answer right
            now — so they close up to the WITHIN-group distance. `DiagnosisCard`
            paid for this lesson: "five bordered blocks of the same visual
            weight at one repeating distance is a wall, and it is a wall whether
            or not any single gap is small." */}
        <div className="qcard__lede">
          <h3 className="card__headline qcard__headline">
            {sentence(question.step.verb) || `Answer ${question.fact}`}
          </h3>

          {/* PAGE 16.5, PART ONE — what is true right now, carrying its
              provenance. Either somebody has already claimed this fact, or the
              ledger's own default is in force. Both are shown; neither is ever
              put in the field. */}
          <StateOfPlay question={question} />
        </div>

        {/* PAGE 16.5, PART TWO — what that means, in one sentence, and it is
            the ledger's sentence rather than one composed here. Absent when the
            question came from the registry rather than from a challenge, in
            which case there is nothing to quote and nothing is invented. */}
        {question.step.substantiation ? (
          <p className="card__text qcard__why">{question.step.substantiation}</p>
        ) : null}

        {phase === 'asking' || phase === 'running' ? (
          /* THE SECOND GROUP — the control, the two buttons and what happens if
             neither is used. One thing to do, so one block. */
          <div className="qcard__collect">
            <div className="qcard__ask">
              {question.shape === 'picker' ? (
                <Picker
                  slots={slots}
                  control={control}
                  values={values}
                  workspaceRoot={workspaceRoot}
                  onChange={(name, next) =>
                    setValues((current) => ({ ...current, [name]: next }))
                  }
                  disabled={phase === 'running'}
                />
              ) : (
                <Field
                  question={question}
                  value={answer}
                  onChange={(next) =>
                    setValues((current) => ({ ...current, [ANSWER]: next }))
                  }
                  disabled={phase === 'running'}
                />
              )}

              {/* PAGE 11.3 — one line, under the field, in --wont, naming what
                  is wrong and what would clear it. Border only; the value
                  itself stays readable. */}
              {problem ? (
                <p className="qcard__problem">
                  <Icon name="alert" size={12} />
                  <span>{problem}</span>
                </p>
              ) : null}
            </div>

            {/* PAGE 16.5, PART THREE — the actions. Two, both on the ordinary
                bordered chassis: page 10 spends the accent fill on send and on
                an approval's primary action, and this is neither. Equal weight
                is the design saying "I don't know" is a legal answer. */}
            <div className="qcard__actions">
              <Button
                icon={question.shape === 'picker' ? 'run' : 'check'}
                onClick={() => void send()}
                disabled={!filled || phase === 'running'}
                aria-busy={phase === 'running' || undefined}
              >
                {/* THE SMALLEST IMPERATIVE FOR THE ACT, and not the tool's own
                    label. The label was tried and read as a stutter: the
                    headline is already the engine's verb, so "Count the eval
                    set myself" sat two rows above a button reading "Count the
                    eval set". The tool is named on the line beside the button
                    instead, where it is provenance rather than a repetition. */}
                {phase === 'running'
                  ? 'Working…'
                  : question.shape === 'picker'
                    ? 'Run it'
                    : 'Record it'}
              </Button>
              <Button onClick={dontKnow} disabled={phase === 'running'}>
                I don&rsquo;t know
              </Button>
              <Lands question={question} />
            </div>

            {/* THE DEFAULT, BEFORE IT IS CHOSEN. A default the user cannot see
                is a number we invented on their behalf. Page 11.3's "two errors
                that are not errors" is the exact construction: a hint line with
                the value and its DEFAULT tag, amber for "I picked this for
                you", and nothing red anywhere near it. */}
            <Fallback question={question} />
          </div>
        ) : null}

        {phase === 'answered' && outcome ? (
          <Landed
            outcome={outcome}
            /* A RUN THAT FAILED MUST NOT BE A DEAD END. Found by reading the
               state machine rather than the screen: an errored tool call left
               the card showing the error with no control on it and no way back
               to the field, and the only escape was another whole diagnosis.
               The typed values are kept, because the path was probably right
               and the disk was probably busy. */
            onRetry={
              outcome.ok && !outcome.error ? undefined : () => setPhase('asking')
            }
          />
        ) : null}

        {phase === 'assumed' ? (
          <Assumed question={question} onReturn={() => setPhase('asking')} />
        ) : null}

        <Footnote question={question} />
      </div>
    </section>
  );
}

/** The single slot a field's answer goes in. Not a fact name and not a schema
 *  property — this is local state, and the fact it belongs to is on the
 *  question.
 *
 *  THE PREFIX IS A COLON BECAUSE IT USED TO BE A LITERAL NUL. A 0x00 in the
 *  source makes the whole file BINARY to grep and ripgrep, so every repo-wide
 *  content search silently skipped this component. The prefix still has to be
 *  a character no tool field name can contain - these keys share one record
 *  with the control's own fields - and `:` is that without making the file
 *  unsearchable. */
const ANSWER = ':answer';

/* ── The parts ────────────────────────────────────────────────────────────── */

/**
 * What somebody already said, or what the ledger is currently using.
 *
 * This is the credulity test and it is the same one `NextStep.tsx` passes: the
 * claim is real — a model did say it — so it is not hidden, and it is not an
 * error, so nothing here is red. It wears its origin, and the origin is the
 * engine's own word.
 */
function StateOfPlay({ question }: { question: Question }) {
  if (question.claimed) {
    const origin = question.claimed.origin;
    return (
      <p className="qcard__now">
        <span className="mono qcard__fact">{question.fact}</span>
        <span className="qcard__nowsaid">was given as</span>
        <span className="mono qcard__nowvalue">{show(question.claimed.value)}</span>
        {isFactOrigin(origin) ? <OriginTag origin={origin} /> : null}
        {question.claimed.how ? (
          <span className="qcard__how">{question.claimed.how}</span>
        ) : null}
      </p>
    );
  }
  return (
    <p className="qcard__now">
      <span className="mono qcard__fact">{question.fact}</span>
      <span className="qcard__nowsaid">has not been answered in this thread</span>
    </p>
  );
}

/** Where the answer lands, in the provenance vocabulary of page 13, and which
 *  tool puts it there.
 *
 *  NOT A `.tag`. A tag is attached at the point a number is rendered, and page
 *  13.5 is explicit that "a tag without a number is meaningless" — there is no
 *  number here yet, only a promise about the one that is coming. So the word
 *  carries the origin's own colour and none of the pill, which keeps the four
 *  tags meaning exactly what they mean everywhere else in the product. */
function Lands({ question }: { question: Question }) {
  const colour = TAG_TOKEN[ORIGIN_TAG[question.lands]];
  return (
    <span className="qcard__lands">
      {question.lands === 'MEASURED' ? (
        <>
          <span className="mono">{question.step.tool}</span> counts it &mdash;{' '}
        </>
      ) : (
        'in your own person — '
      )}
      <span
        className="mono qcard__landsword"
        style={{ '--lands': colour } as CSSProperties}
      >
        {ORIGIN_WORD[question.lands]}
      </span>
    </span>
  );
}

/**
 * The consequence of not knowing, said before it is chosen.
 *
 * TWO DIFFERENT SENTENCES, because there are two different states and saying
 * one of them for both was wrong on screen. Found by reading the rendered card:
 * over Max's own fixture — where a model asserted 1000 — it read "eval_size_n
 * stays —", which is not what happens. Nothing is deleted. The claim stays on
 * the card, wearing ASSERTED, and what changes is that the gate goes on reading
 * the fact as if nobody had answered it, which is `fact_origins.rule` step 3
 * word for word: "evaluate the row a second time with every challenged fact
 * reset to its unsupplied reading".
 *
 * So the DEFAULTED case names the value and tags it, and the challenged case
 * names the masking instead of pretending there is a value to show. Neither
 * invents a number: the ledger's own default is not on the wire for a fact
 * somebody supplied, and a zero here would be this file guessing at it.
 */
function Fallback({ question }: { question: Question }) {
  return (
    <p className="qcard__fallback">
      <span>I don&rsquo;t know &mdash; </span>
      {question.fallback.known ? (
        <>
          <span className="mono qcard__fact">{question.fact}</span>
          <span> stays </span>
          <span className="mono qcard__nowvalue">{show(question.fallback.value)}</span>
          <ProvenanceTag tag="DEFAULT" />
          <span>, carried as an assumption you will see on the next verdict.</span>
        </>
      ) : question.claimed ? (
        <>
          <span>the claim stays exactly where it is, and the gate goes on reading </span>
          <span className="mono qcard__fact">{question.fact}</span>
          <span> as if nobody had answered it.</span>
        </>
      ) : (
        /* PAGE 13.5 RULE 2 — the em dash, and NO provenance tag beside it. A
           tag with no number is meaningless, and a zero would be invented. */
        <>
          <span className="mono qcard__fact">{question.fact}</span>
          <span> stays </span>
          <span className="qcard__dash">&mdash;</span>
          <span>, carried as an assumption you will see on the next verdict.</span>
        </>
      )}
    </p>
  );
}

/** The picker: the measuring tool's own required arguments, from its own
 *  schema. The answer is a location, not a value — what lands in the ledger is
 *  whatever the tool counts when it looks there. */
/** Whether a slot holds a location on disk — the fields the owner should never
 *  have to type by hand: "why do I have to type the path, like an attached
 *  folder, by searching my files... that's outrageous." Matched on the field's
 *  own name, never on the tool's. */
function isPathField(field: ToolField): boolean {
  return field.type === 'string' && /(^|_)(path|root|folder|dir|file)s?$/i.test(field.name);
}

function Picker({
  slots,
  control,
  values,
  workspaceRoot,
  onChange,
  disabled,
}: {
  slots: ToolField[];
  control: ToolControl | null;
  values: Record<string, string>;
  workspaceRoot: string | null;
  onChange: (name: string, next: string) => void;
  disabled: boolean;
}) {
  if (slots.length === 0) {
    return (
      <p className="qcard__noargs">
        <Icon name="info" size={12} />
        <span>
          {control
            ? `${control.name} needs nothing from you — it reads this machine.`
            : 'This runs with no arguments.'}
        </span>
      </p>
    );
  }
  return (
    <>
      {slots.map((field) => (
        <label className="qcard__field" key={field.name}>
          <span className="qcard__label mono">{field.name}</span>
          <div className="field--inline">
            <input
              className="input mono"
              type={field.type === 'integer' || field.type === 'number' ? 'number' : 'text'}
              value={values[field.name] ?? ''}
              spellCheck={false}
              disabled={disabled}
              onChange={(event) => onChange(field.name, event.target.value)}
            />
            {/* The same Browse the attach popover has, for the same reason it
                is shell-only there: a browser never learns a real path. The
                dataset answer is usually a file, so the file picker opens. */}
            {isPathField(field) && hasNativeShell() ? (
              <button
                type="button"
                className="btn"
                disabled={disabled}
                onClick={() => {
                  void nativePickPath('file').then((picked) => {
                    if (picked) onChange(field.name, picked);
                  });
                }}
              >
                Browse…
              </button>
            ) : null}
          </div>
          {/* PAGE 11.2: "the placeholder names the value, never instructs", so
              the tool's own sentence goes under the field rather than inside
              it. There is no invented example path in this component: an
              example path is a path on somebody else's machine. */}
          {field.description ? (
            <span className="field__hint">{field.description}</span>
          ) : null}
          {/* THE PROJECT'S OWN FOLDER, ONE CLICK AWAY. Offered, not filled:
              the person clicking IS the person choosing, and the path is one
              they attached to the project themselves — their own word, not a
              model's claim, which is what the header's wall is about. */}
          {isPathField(field) && workspaceRoot && (values[field.name] ?? '') === '' ? (
            <button
              type="button"
              className="qcard__usews"
              disabled={disabled}
              onClick={() => onChange(field.name, workspaceRoot)}
            >
              <Icon name="folder" size={11} /> use the project folder —{' '}
              <span className="mono">{workspaceRoot}</span>
            </button>
          ) : null}
        </label>
      ))}
    </>
  );
}

/** The field: one answer, in the person's own person. */
function Field({
  question,
  value,
  onChange,
  disabled,
}: {
  question: Question;
  value: string;
  onChange: (next: string) => void;
  disabled: boolean;
}) {
  if (question.input === 'bool') {
    /* PAGE 11.5 — a closed set of two, where seeing the alternatives is part of
       the decision. Built from the button chassis, as the book requires:
       "the selected segment lifts to --surface-3 with --e1 — it is raised, not
       coloured, because the accent belongs to the send button". */
    return (
      <div className="qcard__field">
        <span className="qcard__label mono">{question.fact}</span>
        <div className="qcard__seg" role="group" aria-label={question.fact}>
          {[
            ['true', 'Yes'],
            ['false', 'No'],
          ].map(([raw, label]) => (
            <button
              key={raw}
              type="button"
              className="qcard__segbtn"
              aria-pressed={value === raw}
              disabled={disabled}
              onClick={() => onChange(raw)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    );
  }

  if (question.input === 'enum' && question.choices) {
    return (
      <label className="qcard__field">
        <span className="qcard__label mono">{question.fact}</span>
        <select
          className="input"
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
        >
          {/* No pre-selected member. A select that opens on a value nobody
              chose is this surface answering for the person, which is the
              defect the whole card exists to close. */}
          <option value="">&mdash;</option>
          {question.choices.map((member) => (
            <option key={member} value={member}>
              {member}
            </option>
          ))}
        </select>
      </label>
    );
  }

  return (
    <label className="qcard__field">
      <span className="qcard__label mono">{question.fact}</span>
      <input
        className="input mono"
        type={question.input === 'number' ? 'number' : 'text'}
        value={value}
        spellCheck={false}
        disabled={disabled}
        /* NEVER PRE-FILLED with what a model asserted. See the header: that
           would push the model's claim through the user's door and hand it
           back stamped STATED. */
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

/**
 * What actually happened, in the engine's words rather than this card's.
 *
 * `state_facts` returns one `recorded` row per fact, each carrying the origin
 * the CALLER was worth and, when that origin still cannot open the gate, the
 * ledger's own sentence saying why. Hard-coding MEASURED here would be the very
 * defect this card exists to prevent, arriving through the back of it.
 */
function Landed({
  outcome,
  onRetry,
}: {
  outcome: { ok: boolean; error: string | null; result: unknown };
  /** Present only when the run did not succeed. */
  onRetry?: () => void;
}) {
  if (outcome.error) {
    return (
      <div className="qcard__landed">
        <p className="qcard__state qcard__state--failed">
          <Icon name="alert" size={12} />
          <span>{outcome.error}</span>
        </p>
        {onRetry ? (
          <div className="qcard__actions">
            <Button small onClick={onRetry}>
              Try again
            </Button>
          </div>
        ) : null}
      </div>
    );
  }
  const detail = readDetail(outcome.result);
  /* EVERY ROW THE TOOL WROTE, not only the one this card asked about. One run
     can settle two facts — `measure_baseline` answers `baseline_measured` AND
     `baseline_score` — and hiding the second would be this card deciding which
     of the engine's own results the person is allowed to see. */
  const recorded = readRecorded(outcome.result);

  return (
    <div className="qcard__landed">
      <p className={`qcard__state${outcome.ok ? '' : ' qcard__state--failed'}`}>
        <Icon name={outcome.ok ? 'check' : 'alert'} size={12} />
        <span>
          {detail ??
            (outcome.ok
              ? 'It ran and reported nothing to record.'
              : 'It refused, and sent no reason this surface can read.')}
        </span>
      </p>
      {recorded.map((row) => (
        <p className="qcard__state" key={row.fact}>
          <span className="mono qcard__fact">{row.fact}</span>
          <span className="mono qcard__nowvalue">{show(row.value)}</span>
          {isFactOrigin(row.origin) ? <OriginTag origin={row.origin} /> : null}
          {row.note ? <span className="qcard__how">{row.note}</span> : null}
        </p>
      ))}
    </div>
  );
}

/** The assumption, kept on screen rather than folded away.
 *
 *  §9.8: "Never let an assumption disappear into the reasoning silently." The
 *  shell carries it onto the next verdict through `onAssumed`; this line is
 *  what stops it vanishing in the meantime, and the way back is a control
 *  rather than a reload. */
function Assumed({
  question,
  onReturn,
}: {
  question: Question;
  onReturn: () => void;
}) {
  return (
    <div className="qcard__landed">
      <p className="qcard__state">
        <Icon name="info" size={12} />
        <span>
          Nothing was recorded. <span className="mono qcard__fact">{question.fact}</span>{' '}
          {question.fallback.known ? (
            <>
              stays <span className="mono qcard__nowvalue">{show(question.fallback.value)}</span>{' '}
              <ProvenanceTag tag="DEFAULT" />
            </>
          ) : (
            <>
              stays <span className="qcard__dash">&mdash;</span>
            </>
          )}
        </span>
      </p>
      <div className="qcard__actions">
        <Button small onClick={onReturn}>
          Answer it after all
        </Button>
      </div>
    </div>
  );
}

/** The hairline: which gate this opens and the clause that decides it.
 *
 *  Page 23: "the right-hand clause is what makes the ledger checkable by
 *  someone who does not trust it". It is the quietest thing on the card and it
 *  is the reason the card is not asking somebody to take its word. */
function Footnote({ question }: { question: Question }) {
  const also = question.step.also ?? [];
  if (!question.clause && also.length === 0) return null;
  return (
    <p className="qcard__foot">
      <Icon name="info" size={12} />
      <span>
        {question.clause ? (
          <>
            {question.gate ? <span className="mono">{question.gate}</span> : null} passes when{' '}
            <span className="mono">{question.clause}</span>
          </>
        ) : null}
        {also.length > 0 ? (
          <>
            {question.clause ? ' · ' : ''}also measured by{' '}
            <span className="mono">{also.join(', ')}</span>
          </>
        ) : null}
      </span>
    </p>
  );
}

/* ── Sending it ───────────────────────────────────────────────────────────── */

/**
 * The arguments for the call, built from the tool's own schema.
 *
 * A PICKER fills the tool's required properties, coerced by the type the schema
 * declares. A FIELD fills the one object property the fact goes in — the step
 * already says which fact, so the person answers one question instead of
 * writing JSON — and the property is found by its TYPE, not by the tool's name.
 * Nothing in this file knows what any particular tool does, which is the
 * property that stops the control face and the model face drifting apart.
 */
function argumentsFor(
  question: Question,
  control: ToolControl | null,
  values: Record<string, string>,
): Record<string, unknown> {
  const fields = (control?.fields ?? []).filter((field) => field.required);
  const out: Record<string, unknown> = {};

  if (question.shape === 'picker') {
    for (const field of fields) {
      const raw = (values[field.name] ?? '').trim();
      if (field.type === 'integer' || field.type === 'number') {
        const parsed = Number(raw);
        if (!Number.isFinite(parsed)) {
          throw new Error(
            `${field.name}: "${raw}" is not a number. Type the figure on its own, with no units.`,
          );
        }
        out[field.name] = field.type === 'integer' ? Math.trunc(parsed) : parsed;
        continue;
      }
      if (field.type === 'boolean') {
        out[field.name] = raw.toLowerCase() === 'true' || raw === '1';
        continue;
      }
      out[field.name] = raw;
    }
    return out;
  }

  const slot = fields.find((field) => field.type === 'object');
  if (!slot) {
    throw new Error(
      `${question.step.tool} takes no object argument this answer could go in, so nothing was sent.`,
    );
  }
  const raw = (values[ANSWER] ?? '').trim();
  if (question.input === 'number') {
    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) {
      throw new Error(
        `${question.fact} is a number. "${raw}" is not one — type the figure on its own, with no units or commas.`,
      );
    }
  }
  out[slot.name] = { [question.fact]: scalar(question, raw) };
  return out;
}

/**
 * One value the person typed, read as what they wrote.
 *
 * The fact ledger lives in the engine; this surface has no copy of it and must
 * not grow one. A boolean and a plain number are read as themselves; anything
 * else goes through as the string, so `app/diagnosis.py`'s own coercion error
 * is what the person reads rather than a value this file guessed at.
 */
function scalar(question: Question, raw: string): unknown {
  if (question.input === 'bool') return raw === 'true';
  if (question.input === 'number') {
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : raw;
  }
  if (/^(true|yes)$/i.test(raw)) return true;
  if (/^(false|no)$/i.test(raw)) return false;
  if (raw !== '' && Number.isFinite(Number(raw))) return Number(raw);
  return raw;
}

/* ── Reading a tool result, narrowly ──────────────────────────────────────── */

interface Recorded {
  fact: string;
  value: unknown;
  origin: string;
  note: string;
}

/**
 * The fact rows a tool says it wrote, each carrying its own origin.
 *
 * The same narrow read `NextStep.tsx` does, repeated here rather than shared
 * because that file belongs to another lane in this build and a shared helper
 * would have had to land in it. Worth saying out loud: this is duplication, it
 * is two dozen lines, and the honest fix is one exported reader in
 * `lib/engine/facts.ts` that both cards use.
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
    const value = record[key];
    if (typeof value === 'string' && value) return value;
  }
  return null;
}

/* ── Small helpers ────────────────────────────────────────────────────────── */

/** A value as the ledger holds it. `null` and `undefined` are absences and are
 *  drawn as the em dash, never as a zero or an empty string. */
function show(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'number') return String(value);
  if (typeof value === 'string') return value;
  return JSON.stringify(value);
}

/** The registry's verbs are imperative and lower case; a headline starts with a
 *  capital. */
function sentence(verb: string): string {
  if (!verb) return '';
  return verb.charAt(0).toUpperCase() + verb.slice(1);
}
