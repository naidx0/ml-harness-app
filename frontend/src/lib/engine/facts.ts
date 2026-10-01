/**
 * Fact origins — where a number came from, and what the interface may say about it.
 *
 * Every type here is transcribed from `app/diagnosis.py` and
 * `app/tools/evidence.py`. Nothing is invented and nothing is widened: a
 * response that does not carry a field comes back as `null`, because the
 * alternative — a default that reads like data — is the exact defect this
 * whole layer exists to close.
 *
 * ══ WHY THIS FILE EXISTS ═══════════════════════════════════════════════════
 *
 * The engine used to track whether a fact was PRESENT. It now tracks where the
 * fact CAME FROM, because presence was being read as provenance and a model
 * that merely asserted `eval_size_n` and `baseline_measured` got all five gates
 * green. `app/diagnosis.py`:
 *
 *   "A model that cannot decide a gate can still SUPPLY the fact the gate
 *    reads… So a fact is no longer a bare value: it is a value and an ORIGIN."
 *
 * The interface is the other half of that wall, and it has exactly one job
 * here: **never render an asserted fact as a measured one.** It is the same law
 * the product already applies to hardware numbers (invariant 3), extended to
 * the facts that actually decide whether somebody trains a model.
 *
 * ══ THE VOCABULARY, AND THE ONE DECISION THIS FILE MAKES ═══════════════════
 *
 * The engine declares four origins. Graphite page 13 declares four provenance
 * TAGS. They are not the same four, and the mismatch is real rather than
 * something to smooth over:
 *
 *   engine origin   Graphite tag   why
 *   ─────────────   ────────────   ────────────────────────────────────────────
 *   MEASURED        Measured       "Read from this machine or this file, just
 *                                  now." Word for word the same promise.
 *   STATED          Declared       "You told us, and we have not checked it."
 *                                  Word for word the same promise.
 *   DEFAULTED       Defaulted      "Nothing was read and nothing was told to
 *                                  us; we picked it." The same promise again.
 *   ASSERTED        Declared       ← THE DECISION. See below.
 *
 * Graphite has no ASSERTED tag: page 13 predates fact origins, and grepping the
 * book for the word finds it only in prose. DESIGN_DIRECTIVES says Graphite is
 * the source of truth and this build was told not to invent a fourth tag style,
 * so ASSERTED does not get a fifth colour. It gets the fourth STYLE — grey,
 * `--unknown`, the Declared slot — and its own WORD.
 *
 * That is not a fudge, it is the ranking the book already draws: "Green is a
 * reading. Blue is arithmetic on a reading. Amber is an admission. Grey is a
 * repetition of something you said." STATED is a repetition of something the
 * user said; ASSERTED is a repetition of something the MODEL said. Same rank —
 * an unverified repetition — and Graphite's own law (page 05, "every
 * colour-coded state also carries a word") is what separates them, because the
 * word is load-bearing and the hue is only the rank.
 *
 * The two things that must not happen, and do not:
 *   - ASSERTED must never read as MEASURED. It is grey, never green.
 *   - ASSERTED must never be silently merged into STATED, because the
 *     difference between "the person whose project this is said so" and "a
 *     model said so on their behalf" is precisely what decides whether a gate
 *     opens. They render different words and different sentences.
 *
 * Recorded as outstanding work for the book rather than settled here: Graphite
 * page 13 owes a fifth row, and until it has one this mapping is where the
 * decision lives.
 */

import type { DisplayTag } from './types';

/* ── The engine's four origins — app/diagnosis.py ORIGINS ─────────────────── */

export type FactOrigin = 'MEASURED' | 'STATED' | 'ASSERTED' | 'DEFAULTED';

export const FACT_ORIGINS: readonly FactOrigin[] = [
  'MEASURED',
  'STATED',
  'ASSERTED',
  'DEFAULTED',
] as const;

export function isFactOrigin(value: unknown): value is FactOrigin {
  return typeof value === 'string' && (FACT_ORIGINS as readonly string[]).includes(value);
}

/** The Graphite tag each origin renders in. See the header for the argument. */
export const ORIGIN_TAG: Record<FactOrigin, DisplayTag> = {
  MEASURED: 'MEASURED',
  STATED: 'DECLARED',
  ASSERTED: 'DECLARED',
  DEFAULTED: 'DEFAULT',
};

/**
 * The word on the tag. It is the ENGINE'S word, not the book's, because the
 * word is what carries the distinction the colour cannot: a person reading
 * ASSERTED and a person reading the diagnosis contract have to find the same
 * term, or the tag has become a translation of the guarantee.
 */
export const ORIGIN_WORD: Record<FactOrigin, string> = {
  MEASURED: 'MEASURED',
  STATED: 'STATED',
  ASSERTED: 'ASSERTED',
  DEFAULTED: 'DEFAULTED',
};

/**
 * One sentence per origin, quoted from `GET /api/evidence`'s own `origins`
 * block where it has one. These are the tooltips; they are not paraphrased,
 * because a paraphrase of a provenance promise is a second promise.
 */
export const ORIGIN_MEANS: Record<FactOrigin, string> = {
  MEASURED: 'a tool ran on this machine and the engine watched it',
  STATED: 'the person whose project this is said so',
  ASSERTED: 'a model said so, or nobody said where it came from',
  DEFAULTED: "nobody supplied it, so the engine applied the fact ledger's own default",
};

/* ── Actors — app/tools/evidence.py ACTORS ────────────────────────────────── */

export type Actor = 'user' | 'model' | 'harness';

/** Who this was, in words a reader can use. `null` for an actor we have never
 *  heard of, which renders as the raw string rather than as a guess. */
export function actorName(actor: string | null | undefined): string | null {
  switch (actor) {
    case 'user':
      return 'you';
    case 'model':
      return 'the model';
    case 'harness':
      return 'the harness';
    default:
      return null;
  }
}

/* ── The diagnosis payload — app/tools/__init__.py run_diagnosis ──────────── */

/** Three statuses and no fourth. `app/diagnosis.py _finish`. */
export type LedgerStatus = 'PASSED' | 'FAILED' | 'NOT_REACHED';

export interface GateLedgerEntry {
  /** The spec node this gate hangs off, e.g. `S0_NO_EVAL_SET`. */
  node: string;
  status: LedgerStatus;
  /** Which method-class row was evaluated, `null` when the gate was never
   *  reached. */
  row: string | null;
  /** The row's `requires` expression, verbatim. This is the gate's evidence:
   *  page 23 — "the right-hand clause is what makes the ledger checkable by
   *  someone who does not trust it". */
  clause: string | null;
  /**
   * Present ONLY when the gate's predicate was true and the facts that made it
   * true are ones nobody can vouch for. `app/diagnosis.py` keeps the status at
   * FAILED on purpose — "a renderer that only knows PASSED/FAILED/NOT_REACHED
   * keeps working, and one that wants to say 'you told me, show me' has the
   * fact names".
   */
  unsubstantiated?: string[];
}

/** One row of `unsubstantiated` — the fact, the gate that refused it, and the
 *  tool that would settle it. `app/tools/evidence.py resolves()`. */
export interface UnsubstantiatedRow {
  fact: string;
  gate: string;
  /** The ledger's own `source:` tag: `inspect`, `ask`, `derive`. */
  declared_source: string;
  origin: FactOrigin | string;
  /** What would turn this claim into something that opens a gate, in the
   *  spec's own words. */
  substantiation: string;
  next_step: NextStep | null;
}

export interface NextStep {
  fact: string;
  declared_source: string;
  /** The registered tool that measures this fact, or `state_facts` for a fact
   *  only the user can answer, or `null` when nothing in the harness measures
   *  it yet — which is a gap in the product and says so. */
  tool: string | null;
  /** `harness` — the harness runs an instrument. `user` — the person answers in
   *  their own person, and only that door produces STATED. */
  run_as: 'harness' | 'user' | null;
  verb: string;
  substantiation: string;
  /** Other tools that measure the same fact, listed rather than hidden. */
  also?: string[];
  /** Present only when no tool measures this fact. */
  note?: string;
}

export interface FactUsed {
  value: unknown;
  origin: FactOrigin | string;
  /** The engine's own sentence: "counted 120 rows in eval.jsonl", "supplied
   *  with this call by the model". Shown verbatim. */
  how: string;
}

export interface DiagnosisPayload {
  ok: true;
  outcome: string;
  verdict: string;
  say: string | null;
  proposed_method: string;
  gate_ledger: Record<string, GateLedgerEntry>;
  path: { id: string; kind: string; row: string | null; clause: string | null }[];
  constraints: string[];
  struck_methods: string[];
  cost_provenance: string;
  fact_origins: Record<string, string>;
  facts_used: Record<string, FactUsed>;
  /** What the caller's own facts were worth. ASSERTED from a model, STATED
   *  from the control route. */
  your_facts_were_recorded_as: FactOrigin | string;
  unsubstantiated: UnsubstantiatedRow[];
  help: string | null;
  /** WHAT WOULD CHANGE THIS ANSWER, and WHAT TO DO INSTEAD. Both are built by
   *  `app/tools/next_moves.py` out of the ledger's own words and the registry's
   *  `measures=` declarations, and both have been on the wire since they were
   *  written - this reader simply never copied them, so the card drew a
   *  sentence saying the engine sends neither. Max read that sentence on every
   *  blocked verdict for weeks. */
  revisit_if: string[];
  alternatives: DiagnosisAlternative[];
}

/** One move the card can offer under a verdict. `tool` is what would run,
 *  `run_as` says whether it is the person's call or the model's. */
export interface DiagnosisAlternative {
  move: string;
  text: string;
  from: string;
  fact: string | null;
  tool: string | null;
  verb: string;
  run_as: string;
  arguments: Record<string, unknown>;
  starts_now: boolean;
  why: string;
}

/**
 * Read a `run_diagnosis` result, or return null.
 *
 * Deliberately strict about the two fields the card cannot be honest without —
 * `outcome` and `gate_ledger`. A payload missing either renders as an ordinary
 * tool result (the key/value table) rather than as a diagnosis with holes in
 * it, because a gate ledger with a missing row is a promise with a missing
 * piece and page 23 rule 2 forbids exactly that.
 */
export function readDiagnosis(value: unknown): DiagnosisPayload | null {
  if (!isRecord(value)) return null;
  if (value.ok !== true) return null;
  if (typeof value.outcome !== 'string') return null;
  if (typeof value.verdict !== 'string') return null;
  const ledger = value.gate_ledger;
  if (!isRecord(ledger)) return null;

  const gates: Record<string, GateLedgerEntry> = {};
  for (const [id, entry] of Object.entries(ledger)) {
    if (!isRecord(entry)) return null;
    const status = entry.status;
    if (status !== 'PASSED' && status !== 'FAILED' && status !== 'NOT_REACHED') return null;
    gates[id] = {
      node: typeof entry.node === 'string' ? entry.node : '',
      status,
      row: typeof entry.row === 'string' ? entry.row : null,
      clause: typeof entry.clause === 'string' ? entry.clause : null,
      unsubstantiated: Array.isArray(entry.unsubstantiated)
        ? entry.unsubstantiated.filter((name): name is string => typeof name === 'string')
        : undefined,
    };
  }

  return {
    ok: true,
    outcome: value.outcome,
    verdict: value.verdict,
    say: typeof value.say === 'string' && value.say.trim() ? value.say : null,
    proposed_method:
      typeof value.proposed_method === 'string' ? value.proposed_method : 'UNSET',
    gate_ledger: gates,
    path: readPath(value.path),
    constraints: stringList(value.constraints),
    struck_methods: stringList(value.struck_methods),
    cost_provenance:
      typeof value.cost_provenance === 'string' ? value.cost_provenance : 'UNKNOWN',
    fact_origins: stringMap(value.fact_origins),
    facts_used: readFactsUsed(value.facts_used),
    your_facts_were_recorded_as:
      typeof value.your_facts_were_recorded_as === 'string'
        ? value.your_facts_were_recorded_as
        : 'ASSERTED',
    unsubstantiated: readUnsubstantiated(value.unsubstantiated),
    help: typeof value.help === 'string' ? value.help : null,
    revisit_if: stringList(value.revisit_if),
    alternatives: readAlternatives(value.alternatives),
  };
}

function readAlternatives(value: unknown): DiagnosisAlternative[] {
  if (!Array.isArray(value)) return [];
  const out: DiagnosisAlternative[] = [];
  for (const row of value) {
    if (!row || typeof row !== 'object') continue;
    const one = row as Record<string, unknown>;
    const text = typeof one.text === 'string' ? one.text.trim() : '';
    if (!text) continue;
    out.push({
      move: typeof one.move === 'string' ? one.move : '',
      text,
      from: typeof one.from === 'string' ? one.from : '',
      fact: typeof one.fact === 'string' ? one.fact : null,
      tool: typeof one.tool === 'string' ? one.tool : null,
      verb: typeof one.verb === 'string' ? one.verb : '',
      run_as: typeof one.run_as === 'string' ? one.run_as : '',
      arguments:
        one.arguments && typeof one.arguments === 'object'
          ? (one.arguments as Record<string, unknown>)
          : {},
      starts_now: one.starts_now === true,
      why: typeof one.why === 'string' ? one.why : '',
    });
  }
  return out;
}

function readPath(value: unknown): DiagnosisPayload['path'] {
  if (!Array.isArray(value)) return [];
  const out: DiagnosisPayload['path'] = [];
  for (const entry of value) {
    if (!isRecord(entry) || typeof entry.id !== 'string') continue;
    out.push({
      id: entry.id,
      kind: typeof entry.kind === 'string' ? entry.kind : 'node',
      row: typeof entry.row === 'string' ? entry.row : null,
      clause: typeof entry.clause === 'string' ? entry.clause : null,
    });
  }
  return out;
}

function readFactsUsed(value: unknown): Record<string, FactUsed> {
  if (!isRecord(value)) return {};
  const out: Record<string, FactUsed> = {};
  for (const [name, entry] of Object.entries(value)) {
    if (!isRecord(entry)) continue;
    out[name] = {
      value: entry.value,
      origin: typeof entry.origin === 'string' ? entry.origin : 'ASSERTED',
      how: typeof entry.how === 'string' ? entry.how : '',
    };
  }
  return out;
}

function readUnsubstantiated(value: unknown): UnsubstantiatedRow[] {
  if (!Array.isArray(value)) return [];
  const out: UnsubstantiatedRow[] = [];
  for (const entry of value) {
    if (!isRecord(entry) || typeof entry.fact !== 'string') continue;
    out.push({
      fact: entry.fact,
      gate: typeof entry.gate === 'string' ? entry.gate : '',
      declared_source:
        typeof entry.declared_source === 'string' ? entry.declared_source : '',
      origin: typeof entry.origin === 'string' ? entry.origin : 'ASSERTED',
      substantiation:
        typeof entry.substantiation === 'string' ? entry.substantiation.trim() : '',
      next_step: readNextStep(entry.next_step),
    });
  }
  return out;
}

function readNextStep(value: unknown): NextStep | null {
  if (!isRecord(value)) return null;
  const runAs = value.run_as;
  return {
    fact: typeof value.fact === 'string' ? value.fact : '',
    declared_source:
      typeof value.declared_source === 'string' ? value.declared_source : '',
    tool: typeof value.tool === 'string' ? value.tool : null,
    run_as: runAs === 'harness' || runAs === 'user' ? runAs : null,
    verb: typeof value.verb === 'string' ? value.verb : '',
    substantiation:
      typeof value.substantiation === 'string' ? value.substantiation.trim() : '',
    also: Array.isArray(value.also)
      ? value.also.filter((name): name is string => typeof name === 'string')
      : undefined,
    note: typeof value.note === 'string' ? value.note : undefined,
  };
}

/* ── The evidence ledger — GET /api/evidence, app/tools/evidence.py ───────── */

export interface EvidenceRow {
  id: number;
  thread_id: number | null;
  fact: string;
  value: unknown;
  origin: FactOrigin | string;
  actor: string;
  /** The tool that produced it, `null` when it was supplied rather than run. */
  tool: string | null;
  /** One sentence of how. `Instrument.measured` refuses a stamp without one:
   *  "'measured' with no reading behind it is a badge rather than a
   *  provenance." */
  how: string;
  created_at: string;
}

export interface EvidenceLedger {
  thread_id: number | null;
  rows: EvidenceRow[];
  origins: Record<string, string>;
}

export function readEvidence(value: unknown): EvidenceLedger {
  if (!isRecord(value)) return { thread_id: null, rows: [], origins: {} };
  const rows: EvidenceRow[] = [];
  if (Array.isArray(value.rows)) {
    for (const entry of value.rows) {
      if (!isRecord(entry) || typeof entry.fact !== 'string') continue;
      rows.push({
        id: typeof entry.id === 'number' ? entry.id : 0,
        thread_id: typeof entry.thread_id === 'number' ? entry.thread_id : null,
        fact: entry.fact,
        value: entry.value,
        origin: typeof entry.origin === 'string' ? entry.origin : 'ASSERTED',
        actor: typeof entry.actor === 'string' ? entry.actor : '',
        tool: typeof entry.tool === 'string' ? entry.tool : null,
        how: typeof entry.how === 'string' ? entry.how : '',
        created_at: typeof entry.created_at === 'string' ? entry.created_at : '',
      });
    }
  }
  return {
    thread_id: typeof value.thread_id === 'number' ? value.thread_id : null,
    rows,
    origins: stringMap(value.origins),
  };
}

/* ── Joining a gate to the facts it read ──────────────────────────────────── */

/**
 * Which declared facts a gate's clause NAMES.
 *
 * The engine derives the same set server-side (`_facts_read_by`, parsed out of
 * the row's own `requires` string) and does not put it on the wire. So this
 * reads the clause the wire DOES carry and intersects the identifiers in it
 * with the fact ledger the wire also carries — the same join, done on the same
 * two pieces of real data.
 *
 * TWO THINGS IT DELIBERATELY DOES NOT DO. It does not carry a list of fact
 * names: a fact added to a gate row next year is covered on the day it is
 * added, which is the property `app/diagnosis.py` says in capitals must never
 * be given up. And it does not decide anything — it annotates the gate's own
 * clause with the gate's own origins, and every word on screen came from the
 * engine.
 *
 * The one thing it can get wrong is a false POSITIVE: the engine's compiler
 * knows that a bare word inside a set literal is an enum member rather than a
 * fact lookup, and a regular expression does not. That would name a fact the
 * gate does not really read. It fails in the direction of showing a reader one
 * provenance too many, never one too few, and the tag it shows is still that
 * fact's true origin.
 */
export function factsInClause(
  clause: string | null,
  declared: Record<string, string>,
): string[] {
  if (!clause) return [];
  const found = new Set<string>();
  for (const match of clause.matchAll(/[A-Za-z_][A-Za-z0-9_]*/g)) {
    const name = match[0];
    if (name in declared) found.add(name);
  }
  return [...found].sort();
}

/**
 * How a gate was satisfied, as one word, or null when the question does not
 * apply. The card's per-gate answer to "measurement or assertion?".
 *
 * The weakest origin among the facts the clause names wins, because a gate is
 * only as substantiated as its worst input — MEASURED beside ASSERTED is an
 * assertion with a green tag next to it, which is the shape this whole run
 * exists to make impossible.
 */
export function weakestOrigin(
  facts: string[],
  origins: Record<string, string>,
): FactOrigin | null {
  const rank: Record<FactOrigin, number> = {
    MEASURED: 3,
    STATED: 2,
    ASSERTED: 1,
    DEFAULTED: 0,
  };
  let worst: FactOrigin | null = null;
  for (const name of facts) {
    const origin = origins[name];
    if (!isFactOrigin(origin)) continue;
    /* DEFAULTED is skipped rather than counted as the floor. A clause reads
       facts the caller never supplied — `eval_train_overlap` defaults to false
       and the gate is happy — and letting an untouched default decide the
       word would report every gate as DEFAULTED. What is being answered here
       is "of the things somebody TOLD us, what is the weakest", and a default
       is not something anybody told us. */
    if (origin === 'DEFAULTED') continue;
    if (worst === null || rank[origin] < rank[worst]) worst = origin;
  }
  return worst;
}

/* ── helpers ──────────────────────────────────────────────────────────────── */

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((entry): entry is string => typeof entry === 'string')
    : [];
}

function stringMap(value: unknown): Record<string, string> {
  if (!isRecord(value)) return {};
  const out: Record<string, string> = {};
  for (const [key, entry] of Object.entries(value)) {
    if (typeof entry === 'string') out[key] = entry;
  }
  return out;
}
