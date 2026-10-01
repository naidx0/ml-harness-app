/**
 * What the product shows while it is thinking.
 *
 * Found on a stranger walk: after sending, the transcript's whole account of a
 * running turn was a blinking caret. Measured against a local granite4 on a
 * 2060 Super, 80 seconds passed with nothing else on screen. The caret was put
 * there so "the interface is never silent while the engine is working" - the
 * intent was right and a blinking cursor does not carry it. Nothing separated
 * working from hung, which is the only question a person has while waiting.
 */

import { describe, expect, it } from 'vitest';

import { duration, elapsed } from './Transcript';

describe('how long a wait is read back', () => {
  it('counts whole seconds under a minute', () => {
    expect(elapsed(0)).toBe('0s');
    expect(elapsed(9)).toBe('9s');
    expect(elapsed(59)).toBe('59s');
  });

  it('turns over into minutes, zero-padded so the number does not jump', () => {
    /* Tabular figures and a padded seconds field: the count updates in place
       once a second, and a width that changes on every tick is a flicker. */
    expect(elapsed(60)).toBe('1m 00s');
    expect(elapsed(80)).toBe('1m 20s');
    expect(elapsed(605)).toBe('10m 05s');
  });

  it('never shows a fraction', () => {
    /* A clock read to the tenth implies a precision that means nothing to
       somebody waiting, and this surface does not show numbers it cannot
       justify. */
    for (const n of [1, 42, 90, 3599]) {
      expect(elapsed(n)).not.toMatch(/\./);
    }
  });
});

describe('how a finished turn reports what it cost', () => {
  it('keeps sub-second resolution only where it means something', () => {
    /* 0.8s against 4s is a real difference and worth seeing. */
    expect(duration(0.84)).toBe('0.8s');
    expect(duration(4.21)).toBe('4.2s');
  });

  it('drops the decimals once a turn is long enough not to need them', () => {
    expect(duration(12.7)).toBe('13s');
    expect(duration(59.4)).toBe('59s');
  });

  it('reads a long turn the same way the waiting row counted it', () => {
    /* The live row counted this turn up in minutes and seconds; the record it
       leaves behind must not switch units. 337.219s was what shipped - three
       decimals of invented precision on a wall clock, and the reader still had
       to divide by sixty to learn it meant five and a half minutes. */
    expect(duration(337.219)).toBe('5m 37s');
    expect(duration(60)).toBe('1m 00s');
  });

  it('never prints the millisecond noise it was given', () => {
    for (const n of [337.219, 88.0041, 1200.5]) {
      expect(duration(n)).not.toMatch(/\.\d\d/);
    }
  });
});
