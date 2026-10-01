/**
 * A PLAN IS A LIST OF PHASES, and this is the only thing that decides where one
 * ends.
 *
 * Max, on what planning should produce: *"the goal is obviously just massive,
 * like, markdown... create it in terms of phases. So it has, like, data phase,
 * whatever phase, etcetera."* And on reading it back: *"have a harness to get
 * open the side by side and sectioned off."*
 *
 * Sectioning is a `##` heading and nothing cleverer. `app/conductor._mode_note`
 * asks the model for exactly that shape by name - "a `## Phase 1 - ...` heading
 * per phase" - so the reader and the instruction agree on one rule instead of
 * the reader guessing at prose the writer was never asked for.
 *
 * ## THE PROPERTY THAT MATTERS
 *
 * `joinPhases(splitIntoPhases(text)) === text`, for any text. The panel saves
 * the whole document back, so a splitter that loses a blank line or normalises
 * a heading quietly rewrites a person's plan every time they open it.
 *
 * The first draft held each body as a STRING and failed that property on the
 * smallest interesting case: `## A` followed immediately by `## B` came back
 * with a blank line between them. A phase with no body and a phase with one
 * empty line are different documents and a string cannot tell them apart.
 * Lines can.
 */

export interface Phase {
  /** The `## ...` line, verbatim. Empty for anything before the first one. */
  heading: string;
  /** Everything under the heading, as lines. What `joinPhases` reads. */
  bodyLines: string[];
  /** The same body as one string, which is what the editor shows. Display
   *  only - nothing rebuilds the document from it. */
  body: string;
  /** `Phase 1` -> 1, for the nav. `null` when the heading does not number
   *  itself, which is allowed: a person may write `## Notes`. */
  number: number | null;
  /** What the nav shows: the heading without its `##` and without a
   *  `Phase N -` prefix. Never used to rebuild the document. */
  label: string;
}

const HEADING = /^##[^#].*$/;
const FENCE = /^\s*(```|~~~)/;

/** Split a plan into its phases. Lossless: see the round-trip property above. */
export function splitIntoPhases(plan: string): Phase[] {
  const phases: Phase[] = [];
  let heading = '';
  let lines: string[] = [];
  let fenced = false;

  const flush = () => {
    if (heading === '' && lines.length === 0) return;
    phases.push(describe(heading, lines));
  };

  for (const line of plan.split('\n')) {
    /* A `##` inside a fence is code, not a phase. Markdown explaining how to
       write a plan would otherwise cut itself in half. */
    if (FENCE.test(line)) fenced = !fenced;
    if (!fenced && HEADING.test(line)) {
      flush();
      heading = line;
      lines = [];
      continue;
    }
    lines.push(line);
  }
  flush();
  return phases;
}

/** Rebuild the document. The exact inverse of `splitIntoPhases`. */
export function joinPhases(phases: Phase[]): string {
  const out: string[] = [];
  for (const phase of phases) {
    if (phase.heading !== '') out.push(phase.heading);
    out.push(...phase.bodyLines);
  }
  return out.join('\n');
}

/** Replace one phase's body, returning the whole document.
 *
 * The panel edits a section and saves the document, because the engine stores
 * one `plan` column and a panel that saved sections would be inventing a
 * second, disagreeing, copy of where a phase ends.
 */
export function withPhaseBody(plan: string, index: number, body: string): string {
  const phases = splitIntoPhases(plan);
  if (index < 0 || index >= phases.length) return plan;
  return joinPhases(
    phases.map((phase, at) =>
      at === index ? { ...phase, body, bodyLines: body.split('\n') } : phase,
    ),
  );
}

function describe(heading: string, bodyLines: string[]): Phase {
  const text = heading.replace(/^##\s*/, '').trim();
  /* An en or em dash counts as the separator too: a model writing
     `## Phase 1 \u2014 Data` means the same thing a hyphen means. */
  const numbered = /^phase\s+(\d+)\s*[\u002d\u2013\u2014:.]?\s*(.*)$/i.exec(text);
  return {
    heading,
    bodyLines,
    body: bodyLines.join('\n'),
    number: numbered ? Number(numbered[1]) : null,
    label: numbered && numbered[2] ? numbered[2] : text || 'Before the first phase',
  };
}
