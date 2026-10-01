import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';

import { WhatChangedCard } from './WhatChangedCard';

/**
 * THREE ROWS THAT LOOKED LIKE ONE ROW THREE TIMES.
 *
 * Max's screenshot, 2026-09-20: `+ FACT measure_eval_set measured` stacked
 * three deep under WHAT CHANGED. Two faults behind it.
 *
 * `shortFactLabel` returned `fact.tool` whenever there was one, so every fact
 * an instrument stamped was labelled with the INSTRUMENT. What changed was
 * `eval_size_n`; `measure_eval_set` is how.
 *
 * And they really were the same fact: a turn that calls `measure_eval_set`
 * three times stamps `eval_size_n` three times, `turn.effects` records all
 * three - correctly, it is a log - and the card drew all three, sharing one
 * React key, because the key is the fact plus the tool.
 */

const stamped = (fact: string, tool: string, times: number) =>
  Array.from({ length: times }, () => ({
    fact,
    origin: 'MEASURED',
    how: 'counted 40 rows',
    tool,
  }));

const effects = (facts: ReturnType<typeof stamped>) => ({
  effectsId: 1,
  stepsDone: [],
  stepsParked: [],
  facts,
  files: [],
  planWrites: 0,
  canRevert: false,
});

/** The summary line of each row - the card also prints the fact in the
 *  expandable detail below it, so an unscoped query finds every fact twice. */
const summaries = (root: HTMLElement) =>
  Array.from(root.querySelectorAll('.what-changed__sum')).map((one) =>
    (one.textContent ?? '').trim(),
  );

describe('what changed', () => {
  it('names the fact, not the instrument that stamped it', () => {
    const { container } = render(
      <WhatChangedCard threadId={1} effects={effects(stamped('eval_size_n', 'measure_eval_set', 1))} />,
    );
    const said = summaries(container);
    expect(said).toHaveLength(1);
    expect(said[0]).toContain('eval_size_n');
    expect(said[0]).not.toContain('measure_eval_set');
  });

  it('draws one row for a fact stamped three times, and says three', () => {
    const { container } = render(
      <WhatChangedCard threadId={1} effects={effects(stamped('eval_size_n', 'measure_eval_set', 3))} />,
    );
    const said = summaries(container);
    expect(said).toHaveLength(1);
    expect(said[0]).toContain('×3');
  });

  it('shows no count when it happened once', () => {
    const { container } = render(
      <WhatChangedCard threadId={1} effects={effects(stamped('ram_gb', 'inspect_hardware', 1))} />,
    );
    expect(summaries(container)[0]).not.toContain('×');
  });

  it('keeps two different facts from one tool as two rows', () => {
    const { container } = render(
      <WhatChangedCard
        threadId={1}
        effects={effects([
          ...stamped('ram_gb', 'inspect_hardware', 1),
          ...stamped('vram_gb', 'inspect_hardware', 1),
        ])}
      />,
    );
    const said = summaries(container);
    expect(said).toHaveLength(2);
    expect(said.join(' ')).toContain('ram_gb');
    expect(said.join(' ')).toContain('vram_gb');
  });
});
