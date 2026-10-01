import { describe, expect, it } from 'vitest';

import { nameForALocalModel } from './useProviders';

/**
 * NINE CONNECTIONS SHOULD HAVE NINE NAMES.
 *
 * Max's own database is the fixture here: seven saved local connections, six of
 * them named `Ollama`, because the one-click path named each row after the
 * endpoint - and every local model shares one endpoint. "Let me add a nickname
 * for each model just to make it very simple."
 *
 * Renaming was always possible; the default was what made it necessary.
 */
describe('what a local connection is called before anybody renames it', () => {
  it('is the model, for the models actually on his machine', () => {
    const his = [
      'granite4-hermes:latest',
      'deepseek-teach:latest',
      'granite42-hermes:latest',
      'minicpm5-hermes:latest',
      'hf.co/prism-ml/Bonsai-27B-gguf:Q1_0',
      'bonsai-tuned:latest',
      'bonsai-probe32:latest',
    ];
    expect(his.map(nameForALocalModel)).toEqual([
      'granite4-hermes',
      'deepseek-teach',
      'granite42-hermes',
      'minicpm5-hermes',
      'Bonsai-27B-gguf:Q1_0',
      'bonsai-tuned',
      'bonsai-probe32',
    ]);
  });

  it('gives every one of them a different name', () => {
    /* THE PROPERTY, not seven separate assertions: distinctness is a fact about
       the SET, and a per-item check cannot see a collision. */
    const his = [
      'granite4-hermes:latest',
      'deepseek-teach:latest',
      'granite42-hermes:latest',
      'minicpm5-hermes:latest',
      'hf.co/prism-ml/Bonsai-27B-gguf:Q1_0',
      'bonsai-tuned:latest',
      'bonsai-probe32:latest',
    ];
    const names = his.map(nameForALocalModel);
    expect(new Set(names).size).toBe(his.length);
  });

  it('drops :latest but keeps a tag that is telling two models apart', () => {
    expect(nameForALocalModel('llama3:latest')).toBe('llama3');
    expect(nameForALocalModel('llama3:70b')).toBe('llama3:70b');
    expect(nameForALocalModel('llama3:LATEST')).toBe('llama3');
  });

  it('keeps only the last segment of a namespaced id', () => {
    expect(nameForALocalModel('hf.co/org/thing:latest')).toBe('thing');
  });

  it('never returns an empty name', () => {
    /* A blank label is worse than a repeated one - it is a row you cannot
       click on with any confidence about what it is. */
    for (const odd of ['', ':latest', '/', '///', '   ']) {
      expect(nameForALocalModel(odd).length).toBeGreaterThan(0);
    }
  });
});
