/**
 * The engine's question, read off the wire — `GET /api/next_step`.
 *
 * `app/asking.py` derives THE question that would move a stopped diagnosis and
 * sat in the tree with nothing importing it; `QuestionCard.tsx` drew a question
 * and had nothing rendering it. This file is one half of the join. It parses
 * what the route serves and maps it onto the `Question` interface the card
 * already accepts — the prop its author wrote for exactly this arrival:
 *
 *   "It is not on the wire yet, so `nextQuestion` below derives the question
 *    from what is. When it does arrive, a reader maps it onto `Question` and
 *    passes it here, and the derivation becomes the fallback rather than the
 *    path."
 *
 * ══ THIS FILE DERIVES NOTHING, AND THAT IS THE WHOLE POINT ═════════════════
 *
 * `QuestionCard.nextQuestion()` is a second implementation of PRODUCT_SPEC 9.8
 * in TypeScript: it picks a frontier, ranks facts, and decides whether a fact
 * may be typed into. It is a good implementation and it is still a SECOND
 * OPINION, computed from a payload that cannot see the ledger's `source:` for
 * an unchallenged fact or its declared default. Two implementations of "may
 * this fact be typed into?" is how the two drift, and the day they drift the
 * looser one is the one an adversary uses.
 *
 * So nothing here re-decides anything. Every field below is COPIED from the
 * engine's card:
 *
 *   shape   ← `typed`        the ledger's answer, not a guess from `source`
 *   lands   ← `arrives_as`   the origin `Question.__post_init__` admitted
 *   input   ← `answer`       the ledger's declared type
 *   choices ← `declared.accepts.one_of`
 *   step    ← `settled_by`   which tool, run as whom, in the registry's words
 *   gate    ← `because.gate`
 *   clause  ← `because.requires`   the ledger's own expression, verbatim
 *   fallback← `dont_know.takes` + `declared.declares_a_default`
 *
 * The last one closes a gap the card names in its own header — "`known` IS
 * FALSE FOR EVERY FACT ON TODAY'S WIRE… no route carries a fact's declared
 * default". This route carries it, so a card can now tell "the ledger's default
 * is false" apart from "the ledger has no default", which are different
 * sentences and were rendering as the same one.
 *
 * ══ THE ONE JUDGEMENT THIS FILE MAKES IS A REFUSAL ═════════════════════════
 *
 * `readCard` checks that `typed` and `arrives_as` AGREE — a field must land
 * STATED, a pointer must land MEASURED — and returns `null` when they do not.
 *
 * That is not a re-derivation of the wall in `app/asking.py`; it is the client
 * refusing to render a card that has already failed it. The wall is server-side
 * and it is where the guarantee lives. But this reader's output is passed
 * straight to a component that prints `lands` to the person as a promise about
 * what their answer will be worth, and a surface that would print "MEASURED"
 * beside a text field because a payload said so is a surface that can be lied
 * to by anything that can reach the port. Failing closed costs one card in a
 * case that should never happen; rendering it costs the person their reason to
 * believe the tag.
 *
 * NOTHING HERE SENDS AN ANSWER. The card answers through `POST /api/tools/{name}`,
 * which hard-codes `actor=user`; no origin travels in a request body, in either
 * direction, and there is no function in this file that posts anything.
 */

import { engineJson } from './client';
import type { DiagnosisPayload, FactUsed, NextStep } from './facts';
import { isFactOrigin } from './facts';

/* ── What the route serves ─────────────────────────────────────────────────
   Transcribed from `app/asking.py`'s `as_dict()` methods. Only the fields the
   card actually reads are typed; the rest of the payload is real and is left
   alone rather than half-described here. */

/** `asking.ANSWERS` — five typed, two pointing. */
export type AnswerKind =
  | 'number'
  | 'choice'
  | 'choices'
  | 'yes_no'
  | 'text'
  | 'pointer'
  | 'machine';

/** The origin a card's answer arrives under. `asking.Question.arrives_as`, and
 *  the ledger has already admitted it for this fact or the card would not have
 *  been constructible. */
export type Lands = 'STATED' | 'MEASURED';

/** `asking.Because` — why this is being asked, in the YAML's own words. */
export interface AskBecause {
  entry: string;
  kind: string;
  stage: string;
  gate: string;
  row: string;
  asks: string;
  action: string;
  note: string;
  requires: string;
  unblocks: string;
}

/** `asking.Question.as_dict()`. */
export interface EngineCard {
  fact: string;
  answer: AnswerKind;
  typed: boolean;
  arrives_as: Lands;
  accepts: Record<string, unknown>;
  declared: Record<string, unknown>;
  because: AskBecause;
  settled_by: Record<string, unknown>;
  answered_by: string;
  run_as: string;
  /** The gates this answer could open at the origin this card produces. */
  opens: string[];
  decides: number;
  /** What the number above counted, so it can be checked rather than believed. */
  decides_by: string;
  dont_know: { legal: boolean; takes: unknown; recorded_as: string; how: string };
}

/** `asking.NextStep.as_dict()` — ask this, or start proposing. Never both. */
export interface EngineStep {
  kind: 'question' | 'propose';
  outcome: string;
  verdict: string;
  question: EngineCard | null;
  proposal: {
    outcome: string;
    verdict: string;
    say: string;
    build_with: string;
    covered: boolean;
    how: string;
    why_not: string;
  } | null;
}

/** The whole response, including the route's own note about where an answer
 *  goes. Carried through rather than dropped: a client that shows a card should
 *  be able to show, from the same payload, that the card is not the door. */
export interface NextStepPayload {
  thread_id: number | null;
  step: EngineStep;
  answer_through: {
    route: string;
    tool: string | null;
    actor: string;
    note: string;
  };
}

/* ── Reading it ────────────────────────────────────────────────────────────── */

const TYPED: readonly AnswerKind[] = ['number', 'choice', 'choices', 'yes_no', 'text'];
const POINTING: readonly AnswerKind[] = ['pointer', 'machine'];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function str(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [];
}

function readBecause(value: unknown): AskBecause {
  const from = isRecord(value) ? value : {};
  return {
    entry: str(from.entry),
    kind: str(from.kind),
    stage: str(from.stage),
    gate: str(from.gate),
    row: str(from.row),
    asks: str(from.asks),
    action: str(from.action),
    note: str(from.note),
    requires: str(from.requires),
    unblocks: str(from.unblocks),
  };
}

/**
 * One card off the wire, or null.
 *
 * Strict about `fact`, `answer` and `arrives_as`, because those three are what
 * the card promises the person. A payload that is vague about any of them is
 * not rendered as a card with a hole in it — see the header.
 */
export function readCard(value: unknown): EngineCard | null {
  if (!isRecord(value)) return null;

  const fact = str(value.fact);
  if (!fact) return null;

  const answer = value.answer;
  const known = [...TYPED, ...POINTING] as readonly string[];
  if (typeof answer !== 'string' || !known.includes(answer)) return null;

  const arrives = value.arrives_as;
  if (arrives !== 'STATED' && arrives !== 'MEASURED') return null;

  const typed = value.typed === true;

  /* THE REFUSAL. `typed`, `answer` and `arrives_as` are three views of one
     decision the engine already made, and they cannot disagree about a card
     `asking.Question.__post_init__` built. If they disagree here, something
     between that constructor and this line is not the engine — so nothing is
     drawn, rather than a text field wearing a MEASURED tag. */
  if (typed !== (TYPED as readonly string[]).includes(answer)) return null;
  if (typed && arrives !== 'STATED') return null;
  if (!typed && arrives !== 'MEASURED') return null;

  const dont = isRecord(value.dont_know) ? value.dont_know : {};

  return {
    fact,
    answer: answer as AnswerKind,
    typed,
    arrives_as: arrives,
    accepts: isRecord(value.accepts) ? { ...value.accepts } : {},
    declared: isRecord(value.declared) ? { ...value.declared } : {},
    because: readBecause(value.because),
    settled_by: isRecord(value.settled_by) ? { ...value.settled_by } : {},
    answered_by: str(value.answered_by),
    run_as: str(value.run_as),
    opens: stringList(value.opens),
    decides: typeof value.decides === 'number' ? value.decides : 0,
    decides_by: str(value.decides_by),
    dont_know: {
      legal: dont.legal === true,
      takes: 'takes' in dont ? dont.takes : null,
      recorded_as: str(dont.recorded_as),
      how: str(dont.how),
    },
  };
}

/** The whole `GET /api/next_step` body, or null. */
export function readNextStep(value: unknown): NextStepPayload | null {
  if (!isRecord(value)) return null;
  const step = value.step;
  if (!isRecord(step)) return null;

  const kind = step.kind;
  if (kind !== 'question' && kind !== 'propose') return null;

  const card = kind === 'question' ? readCard(step.question) : null;
  /* A question step whose card would not read is not downgraded to a propose
     step. `asking.NextStep.__post_init__` refuses "a question step with no
     question", and inventing one here would be this file disagreeing with the
     engine about whether there is anything left to ask. */
  if (kind === 'question' && card === null) return null;

  const proposal = isRecord(step.proposal) ? step.proposal : null;
  const through = isRecord(value.answer_through) ? value.answer_through : {};

  return {
    thread_id: typeof value.thread_id === 'number' ? value.thread_id : null,
    step: {
      kind,
      outcome: str(step.outcome),
      verdict: str(step.verdict),
      question: card,
      proposal: proposal
        ? {
            outcome: str(proposal.outcome),
            verdict: str(proposal.verdict),
            say: str(proposal.say),
            build_with: str(proposal.build_with),
            covered: proposal.covered === true,
            how: str(proposal.how),
            why_not: str(proposal.why_not),
          }
        : null,
    },
    answer_through: {
      route: str(through.route),
      tool: typeof through.tool === 'string' ? through.tool : null,
      actor: str(through.actor),
      note: str(through.note),
    },
  };
}

/* ── Mapping it onto the card's own interface ──────────────────────────────── */

/** `QuestionCard.QuestionInput`, restated here so this module does not import
 *  the component it feeds. Kept in step by `toQuestion`'s return type, which is
 *  the component's `Question`. */
type Input = 'text' | 'number' | 'bool' | 'enum';

/**
 * How the answer is collected — the LEDGER's declared type, not a guess.
 *
 * `choices` (a set) collapses to `enum` because that is the only multi-valued
 * control the card draws today. It is the one lossy step in this file and it
 * loses nothing that decides anything: the fact, the tool and the origin are
 * all unchanged, and a card that offered one choice where the ledger allows
 * several is a card the engine will reject on submission, in the ledger's own
 * words, rather than one that quietly records the wrong thing.
 */
function inputFor(answer: AnswerKind): Input {
  switch (answer) {
    case 'number':
      return 'number';
    case 'yes_no':
      return 'bool';
    case 'choice':
    case 'choices':
      return 'enum';
    default:
      return 'text';
  }
}

/** Enum members, off the ledger's own `accepts`. Null when it declared none. */
function choicesFor(card: EngineCard): string[] | null {
  const accepts = isRecord(card.declared.accepts) ? card.declared.accepts : card.accepts;
  const oneOf = stringList(accepts.one_of);
  if (oneOf.length > 0) return oneOf;
  const anyOf = stringList(accepts.any_of);
  return anyOf.length > 0 ? anyOf : null;
}

/** `settled_by` as the `NextStep` the card and `NextStepControl` both read. */
function stepFor(card: EngineCard): NextStep {
  const settled = card.settled_by;
  const runAs = str(settled.run_as);
  return {
    fact: card.fact,
    declared_source: str(settled.declared_source),
    tool: card.answered_by || null,
    run_as: runAs === 'harness' || runAs === 'user' ? runAs : null,
    verb: str(settled.verb),
    substantiation: str(settled.substantiation),
    also: stringList(settled.also),
  };
}

/**
 * The engine's card, in the shape `QuestionCard` takes.
 *
 * `from` is optional and supplies exactly one field: `claimed`, which is what
 * somebody has already said about this fact. That is not on the card — the
 * engine's `Question` carries what the ledger DECLARES, not what a transcript
 * happens to hold — so it is read from the diagnosis's own `facts_used` row
 * when one is to hand. It is shown and never used; the card puts it beside the
 * field, not in it.
 */
export function toQuestion(
  card: EngineCard,
  from?: DiagnosisPayload | null,
): {
  fact: string;
  shape: 'field' | 'picker';
  input: Input;
  choices: string[] | null;
  step: NextStep;
  gate: string | null;
  clause: string | null;
  claimed: FactUsed | null;
  fallback: { value: unknown; known: boolean };
  lands: Lands;
} {
  const used = from?.facts_used?.[card.fact];
  const claimed: FactUsed | null =
    used && isFactOrigin(used.origin)
      ? { value: used.value, origin: used.origin, how: used.how }
      : (used ?? null);

  return {
    fact: card.fact,
    /* NOT re-derived from `source:`. The engine already decided, and it
       decided against a wall this side does not have. */
    shape: card.typed ? 'field' : 'picker',
    input: inputFor(card.answer),
    choices: card.typed ? choicesFor(card) : null,
    step: stepFor(card),
    /* A node entry has no gate, and `""` is how the engine says so. Null rather
       than an empty string, because the card renders "opens <gate>" on the
       strength of this being non-null. */
    gate: card.because.gate || null,
    clause: card.because.requires || null,
    claimed,
    /* THE LEDGER'S OWN DEFAULT, which is what "I don't know" takes. `known` is
       the ledger's `declares_a_default` and not `takes !== null`: a fact whose
       declared default IS null is a different thing from a fact with no
       declared default, and page 13.5 rule 2 says the second renders as an em
       dash rather than as a value. */
    fallback: {
      value: card.dont_know.takes,
      known: card.declared.declares_a_default === true,
    },
    lands: card.arrives_as,
  };
}

/* ── Asking the engine ─────────────────────────────────────────────────────── */

/**
 * `GET /api/next_step`. One question, or the news that it is time to propose.
 *
 * Read-only at both ends: this sends no facts, and the route accepts none.
 */
export function getNextStep(threadId: number | null): Promise<unknown> {
  const query = threadId === null ? '' : `?thread_id=${encodeURIComponent(String(threadId))}`;
  return engineJson(`/api/next_step${query}`);
}
