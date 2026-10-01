/**
 * The two fixed lists the interface is specified to contain.
 *
 * WHAT USED TO BE HERE. A rail of invented runs, drawn because there was no
 * `/api/threads` and no `/api/runs` in the docs/ARCHITECTURE.md §5 shape. The
 * rail lists REAL threads now (`lib/useThreads.ts`) and the transcript is
 * folded out of the REAL event log (`lib/transcript.ts`), so the fixtures are
 * gone rather than left sitting next to live data where the difference is one
 * badge wide.
 *
 * What remains is not sample data. Both lists below are *specified content* —
 * the five gates are the product's promise in fixed words, and the four
 * starting prompts are quoted verbatim from PRODUCT_SPEC §3.1. Neither is a
 * claim about anything measurable.
 */

/**
 * The five gates, keyed by the engine's own gate ids.
 *
 * `id` comes from `app/diagnosis.py` `spec.required_gates` and is what the
 * `gate_ledger` on the wire is keyed by, so the ledger is joined on the
 * engine's identifier and never on position. A sixth gate, or a rename, shows
 * up as an unlabelled row carrying its raw id rather than as a wrong label
 * sitting confidently in the right place.
 *
 * `name` is Graphite page 23.3's wording and `asks` is `docs/diagnosis_engine.
 * yaml`'s own `asks:` string, both transcribed rather than composed. Page 23:
 * "Wording is the engine's own. The interface never paraphrases a gate: a
 * person who reads the card and then reads the diagnosis contract must find
 * the same sentence, or the card has become a translation of the guarantee
 * rather than a view of it."
 *
 * This list previously said "There is an eval set" for the first gate, which is
 * neither the book's sentence nor the engine's. Corrected here.
 *
 * All five render even when only one has been evaluated — §9.15, and page 23
 * rule 2: "A ledger that shows only the gates that ran cannot be read as a
 * guarantee, and the guarantee is the product."
 */
export interface GateSpec {
  id: string;
  name: string;
  asks: string;
}

export const FIVE_GATES: readonly GateSpec[] = [
  {
    id: 'G0_EVAL_SET',
    name: 'An eval set exists',
    asks:
      "Is there a set of examples we can score, so that 'better' is a " +
      'measurement and not a feeling?',
  },
  {
    id: 'G1_BASELINE_MEASURED',
    name: 'A baseline has been measured',
    asks: 'Do we know what the best thing that already exists scores on that eval set?',
  },
  {
    id: 'G2_PROMPT_EXHAUSTED',
    name: 'Prompting has been exhausted',
    asks: 'Has the no-training version of this approach been pushed as far as it goes?',
  },
  {
    id: 'G3_RETRIEVAL_CONSIDERED',
    name: 'Retrieval has been considered',
    asks: 'Was the missing information brought in from outside the weights, and did that fail?',
  },
  {
    id: 'G4_CHEAPER_MODEL_CONSIDERED',
    name: 'A cheaper model has been considered',
    asks: 'Did we check whether something cheaper that already exists solves this?',
  },
] as const;

/** PRODUCT_SPEC §3.1's four starting prompts, verbatim. The fourth exists
 *  because "the front door decides who exists". */
export const STARTER_PROMPTS = [
  'I have a folder of support tickets and I want the model to answer like our team does.',
  'I want a small model that runs on this machine and does one thing well.',
  'I have a spreadsheet and I want to predict a column in it.',
  "The model we're using works. It's too slow and it costs too much.",
] as const;
