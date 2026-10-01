import { describe, expect, it } from 'vitest';

import { parseMarkdown, parseSpans, type Block } from './markdown';

/**
 * WHAT A PLAN ACTUALLY CONTAINS.
 *
 * Max: *"make sure a markdown view is nice... our platform reads it and outputs
 * it in a very clean format as well... make sure we can interpret all the bold
 * writing and stuff."*
 *
 * Bold and code already worked. What did not, and what a phased plan is full
 * of, was italics, checkbox items, a rule between phases, and the `>` quote -
 * which `conductor._plan_note` uses to carry the plan into every build turn,
 * so the product was showing its own quoting marks back to the reader.
 *
 * These are ADDITIVE: everything here used to render as the literal characters
 * the model typed, so nothing that worked before can regress into them.
 */

const kinds = (blocks: Block[]) => blocks.map((block) => block.kind);

describe('the things a phased plan is made of', () => {
  it('reads a checkbox item as a task, not as a bullet saying "[ ]"', () => {
    const blocks = parseMarkdown('- [ ] carve an eval set\n- [x] measure the baseline');
    expect(kinds(blocks)).toEqual(['tasks']);
    const tasks = blocks[0] as Extract<Block, { kind: 'tasks' }>;
    expect(tasks.items.map((item) => item.done)).toEqual([false, true]);
    expect(tasks.items[0].spans[0]).toEqual({ kind: 'text', text: 'carve an eval set' });
  });

  it('takes an upper-case X as done too', () => {
    const blocks = parseMarkdown('- [X] done');
    expect((blocks[0] as Extract<Block, { kind: 'tasks' }>).items[0].done).toBe(true);
  });

  it('reads a rule between phases, and not as an empty bullet', () => {
    /* THE COLLISION THIS ORDERING EXISTS FOR: `---` matches the bullet rule
       too, and read that way it put a stray dot between every phase. */
    expect(kinds(parseMarkdown('a\n\n---\n\nb'))).toEqual(['p', 'hr', 'p']);
    for (const rule of ['---', '***', '___', '  ----  ']) {
      expect(kinds(parseMarkdown(rule))).toEqual(['hr']);
    }
  });

  it('reads a quote, which is how the engine carries a plan into a turn', () => {
    const blocks = parseMarkdown('> ## Phase 1\n> carve');
    expect(kinds(blocks)).toEqual(['quote', 'quote']);
  });

  it('keeps headings, lists and fences working', () => {
    const source = '## Phase 1\n\n- one\n- two\n\n1. first\n\n```py\nx = 1\n```';
    expect(kinds(parseMarkdown(source))).toEqual(['h', 'ul', 'ol', 'pre']);
  });
});

describe('a parked step', () => {
  it('is neither open nor done, and keeps its reason as text', () => {
    const blocks = parseMarkdown('- [!] measure the baseline ' + String.fromCharCode(0x2014) + ' parked: no eval set');
    const tasks = blocks[0] as Extract<Block, { kind: 'tasks' }>;
    expect(tasks.items[0].parked).toBe(true);
    expect(tasks.items[0].done).toBe(false);
    expect(tasks.items[0].spans[0]).toEqual({
      kind: 'text',
      text: 'measure the baseline ' + String.fromCharCode(0x2014) + ' parked: no eval set',
    });
  });
});

describe('emphasis', () => {
  it('reads *italics* and _italics_', () => {
    expect(parseSpans('a *soft* b')).toEqual([
      { kind: 'text', text: 'a ' },
      { kind: 'em', text: 'soft' },
      { kind: 'text', text: ' b' },
    ]);
    expect(parseSpans('_soft_')).toEqual([{ kind: 'em', text: 'soft' }]);
  });

  it('never lets italics eat a bold marker', () => {
    /* THE ORDERING RULE. `**bold**` is tried first at every position, so the
       two-star form cannot lose its second star to the one-star form. */
    expect(parseSpans('**hard**')).toEqual([{ kind: 'strong', text: 'hard' }]);
    expect(parseSpans('**a** and *b*')).toEqual([
      { kind: 'strong', text: 'a' },
      { kind: 'text', text: ' and ' },
      { kind: 'em', text: 'b' },
    ]);
  });

  it('leaves snake_case identifiers alone', () => {
    /* A plan is full of them - `eval_size_n`, `target_score`, `run_diagnosis` -
       and underscore italics would have eaten the middle of every one. */
    for (const name of ['eval_size_n', 'a_b_c_d', 'read_model_config']) {
      expect(parseSpans(name)).toEqual([{ kind: 'text', text: name }]);
    }
  });

  it('leaves an unmatched marker as the character that was typed', () => {
    expect(parseSpans('2 * 3 * 4')).toEqual([{ kind: 'text', text: '2 * 3 * 4' }]);
    expect(parseSpans('a * b')).toEqual([{ kind: 'text', text: 'a * b' }]);
  });

  it('does not read a bullet as italics', () => {
    /* `* item` is a list marker. It reaches parseSpans only as the item TEXT,
       never with its star, but the span rule requires a non-space after the
       marker so a stray one cannot open emphasis either. */
    expect(parseSpans('* item')).toEqual([{ kind: 'text', text: '* item' }]);
  });
});

describe('a real phased plan, end to end', () => {
  it('comes back as the blocks it looks like', () => {
    const plan = [
      '## Phase 1 - Data',
      '',
      'Carve an eval set from **the rows you already have**.',
      '',
      '- [x] count the rows',
      '- [ ] check for *leakage*',
      '',
      '---',
      '',
      '## Phase 2 - Train',
      '',
      '1. pick a recipe',
      '2. start the run',
    ].join('\n');
    expect(kinds(parseMarkdown(plan))).toEqual(['h', 'p', 'tasks', 'hr', 'h', 'ol']);
  });
});
