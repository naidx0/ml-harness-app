import { describe, expect, it } from 'vitest';

import {
  joinPhases,
  splitIntoPhases,
  withPhaseBody,
} from './thePlanInPhases';

/** Every document below goes through the round trip, so a case added here is a
 *  case the property is checked on. */
const DOCUMENTS: Record<string, string> = {
  empty: '',
  'no headings at all': 'just some notes\nover two lines',
  'a heading on the first line': '## Phase 1 - Data\ncarve an eval set',
  'two headings with nothing between them': '## Phase 1 - Data\n## Phase 2 - Train',
  'a preamble before the first phase': 'The plan\n\n## Phase 1 - Data\nrows',
  'trailing blank lines': '## Phase 1 - Data\nrows\n\n',
  'a deeper heading underneath': '## Phase 1 - Data\n### Sources\nthe csv',
  'windows line endings inside': '## Phase 1 - Data\r\nrows\r\n',
  'a fenced block containing a heading': [
    '## Phase 1 - Data',
    'write it like this:',
    '```md',
    '## Phase 2 - Train',
    '```',
    'and then stop',
  ].join('\n'),
};

describe('the round trip is exact', () => {
  for (const [name, text] of Object.entries(DOCUMENTS)) {
    it(name, () => {
      expect(joinPhases(splitIntoPhases(text))).toBe(text);
    });
  }
});

describe('where a phase ends', () => {
  it('a `##` heading starts one', () => {
    const phases = splitIntoPhases(DOCUMENTS['a preamble before the first phase']);
    expect(phases).toHaveLength(2);
    expect(phases[0].heading).toBe('');
    expect(phases[1].heading).toBe('## Phase 1 - Data');
  });

  it('a `###` under it does not', () => {
    /* Sub-headings are how a phase says what is inside it. Cutting there would
       turn one phase into three sections the loop works down separately. */
    expect(splitIntoPhases(DOCUMENTS['a deeper heading underneath'])).toHaveLength(1);
  });

  it('a `##` inside a fence does not', () => {
    /* A plan that explains how to write a plan would otherwise cut itself in
       half at the example. */
    const phases = splitIntoPhases(DOCUMENTS['a fenced block containing a heading']);
    expect(phases).toHaveLength(1);
    expect(phases[0].bodyLines).toContain('## Phase 2 - Train');
  });

  it('a document with no headings is one unnamed phase', () => {
    const phases = splitIntoPhases(DOCUMENTS['no headings at all']);
    expect(phases).toHaveLength(1);
    expect(phases[0].label).toBe('Before the first phase');
  });

  it('two headings in a row are two phases, one of them empty', () => {
    const phases = splitIntoPhases(DOCUMENTS['two headings with nothing between them']);
    expect(phases).toHaveLength(2);
    expect(phases[0].bodyLines).toEqual([]);
  });
});

describe('what the nav shows', () => {
  it('reads the number and drops it from the label', () => {
    const [phase] = splitIntoPhases('## Phase 3 - Evaluate\n');
    expect(phase.number).toBe(3);
    expect(phase.label).toBe('Evaluate');
  });

  it('takes an en or em dash as the same separator', () => {
    for (const dash of ['\u2013', '\u2014']) {
      const [phase] = splitIntoPhases(`## Phase 2 ${dash} Train\n`);
      expect(phase.number).toBe(2);
      expect(phase.label).toBe('Train');
    }
  });

  it('an unnumbered heading is still a phase', () => {
    /* `_mode_note` asks for `## Phase N - ...`, and a person editing the plan
       afterwards is not bound by it. */
    const [phase] = splitIntoPhases('## Notes\nsomething');
    expect(phase.number).toBeNull();
    expect(phase.label).toBe('Notes');
  });
});

describe('editing one phase saves the whole document', () => {
  const plan = '## Phase 1 - Data\nrows\n## Phase 2 - Train\nlora';

  it('changes the phase it was given', () => {
    expect(withPhaseBody(plan, 1, 'full finetune')).toBe(
      '## Phase 1 - Data\nrows\n## Phase 2 - Train\nfull finetune',
    );
  });

  it('leaves every other phase byte for byte', () => {
    const edited = splitIntoPhases(withPhaseBody(plan, 1, 'x'));
    expect(edited[0].bodyLines).toEqual(['rows']);
    expect(edited[0].heading).toBe('## Phase 1 - Data');
  });

  it('a multi-line edit stays multi-line', () => {
    const out = withPhaseBody(plan, 0, 'one\ntwo');
    expect(splitIntoPhases(out)[0].bodyLines).toEqual(['one', 'two']);
  });

  it('an index that is not a phase changes nothing', () => {
    for (const index of [-1, 2, 99]) {
      expect(withPhaseBody(plan, index, 'nope')).toBe(plan);
    }
  });
});
