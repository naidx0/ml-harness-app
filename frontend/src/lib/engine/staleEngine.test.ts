import { describe, expect, it } from 'vitest';

import { checkAgainstCheckout } from './identity';
import type { Checkout, EngineIdentity } from './identity';

/**
 * AN INSTALLED WINDOW HAS NO CHECKOUT BESIDE IT, and that used to end the
 * question.
 *
 * `liveness.ts` has always called `checkAgainstCheckout` and published a
 * "The engine is not running this checkout's code" banner on `differs`. It
 * never fired for Max, because `engine_status` only finds a checkout when the
 * exe sits in one - so an installed app got `checkout: null`, the verdict was
 * `unverifiable`, and nothing drew while he ran a day and a half against an
 * engine from 2026-09-19 01:08 on commit c0cccd4.
 *
 * `config.ts` now falls back to `__UI_REVISION__` - the commit the bundle was
 * built from, baked in by the vite config. These pin the comparison itself.
 */

const engineAt = (revision: string | null): EngineIdentity =>
  ({
    all: {},
    location: {},
    process: {},
    code: {},
    fingerprint: 'f',
    revision,
  }) as unknown as EngineIdentity;

const builtFrom = (revision: string): Checkout => ({
  revision,
  source: 'the commit this window was built from',
});

describe('an engine two commits behind the window', () => {
  it('is caught, and both revisions are in the verdict', () => {
    const verdict = checkAgainstCheckout(
      engineAt('c0cccd4abeacd235c309e22cee68ab3127ed49a4'),
      builtFrom('c40305136f22701ff5289d3cf76ae8ae58bf89d9'),
    );
    expect(verdict.kind).toBe('differs');
    if (verdict.kind !== 'differs') return;
    expect(verdict.engine).toMatch(/^c0cccd4/);
    expect(verdict.checkout).toMatch(/^c403051/);
  });

  it('matches across the short and long form of one commit', () => {
    /* engine.json carries 40 characters; a short sha is 7. Same commit. */
    const verdict = checkAgainstCheckout(
      engineAt('c40305136f22701ff5289d3cf76ae8ae58bf89d9'),
      builtFrom('c403051'),
    );
    expect(verdict.kind).toBe('matches');
  });

  it('says unverifiable rather than matches when the engine names nothing', () => {
    /* The honest branch. An engine old enough to BE the problem publishes no
       revision, and reporting that as a match is the whole defect again. */
    const verdict = checkAgainstCheckout(engineAt(null), builtFrom('c403051'));
    expect(verdict.kind).toBe('unverifiable');
  });

  it('says unverifiable rather than matches when the window names nothing', () => {
    const verdict = checkAgainstCheckout(engineAt('c403051'), null);
    expect(verdict.kind).toBe('unverifiable');
  });
});
