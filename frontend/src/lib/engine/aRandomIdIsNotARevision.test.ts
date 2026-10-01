import { describe, expect, it } from 'vitest';

import { readIdentity, revisionIn, checkAgainstCheckout } from './identity';

/**
 * A PER-PROCESS ID IS NOT A COMMIT, AND MUST NEVER BE READ AS ONE.
 *
 * `engine.json` carries both: `build.sha`, the git commit, and
 * `engine.engine_id`, 32 hex characters from `secrets.token_hex(16)` that are
 * new on every start. `revisionIn` looks the first up by name and used to fall
 * through to scanning every value for anything revision-shaped.
 *
 * In the packaged build the shell forwarded only the nested `engine` block, so
 * `build` never arrived, the named lookups all missed, and the scan found
 * `engine_id`. The page then compared a random id against a git commit,
 * reported the engine stale, and every restart minted a different random id.
 * Max, 2026-09-21, after ten presses: *"why is it still doing this?"* - the
 * revision in the banner had gone from c467f06b to ba572ca and the sentence
 * had not moved.
 */

const portfile = {
  host: '127.0.0.1',
  port: 8078,
  base_url: 'http://127.0.0.1:8078',
  pid: 8596,
  service: 'ml-harness-engine',
  engine: {
    engine_id: 'ba572ca9b2b8bf9e0f9faceec87b9b66',
    pid: 8596,
    started_at: '2026-09-21T16:27:21+00:00',
  },
  build: {
    sha: 'f2e331298f1cffb97d0b767584b3dac52f989286',
    sha_source: 'git-ref',
    dirty: false,
    code_fingerprint: 'bdb13f441b814664bffd32a1a65c98175c220e4a15f11043fff945244dd4910a',
  },
};

describe('what the page calls the engine’s revision', () => {
  it('reads build.sha when the whole portfile arrives', () => {
    const identity = readIdentity(portfile);
    expect(identity?.revision).toBe('f2e331298f1cffb97d0b767584b3dac52f989286');
  });

  it('says it cannot tell, rather than naming a per-process id', () => {
    /* Exactly what the packaged shell used to send: the nested block alone. */
    const identity = readIdentity(portfile.engine);
    expect(identity?.revision).toBeNull();
  });

  it('never returns a 32-hex engine id from a loose scan', () => {
    expect(revisionIn({ engine_id: 'ba572ca9b2b8bf9e0f9faceec87b9b66' })).toBeNull();
    expect(revisionIn({ anything: 'c467f06b150b4d2e8a1f9c3b7e5d0a2f4b6c8d90' })).toBeNull();
  });

  it('still reads a revision published under a name it knows', () => {
    expect(revisionIn({ build: { sha: 'abc1234' } })).toBe('abc1234');
    expect(revisionIn({ revision: 'abc1234' })).toBe('abc1234');
  });

  it('turns a missing revision into unverifiable, never into an accusation', () => {
    const identity = readIdentity(portfile.engine);
    const verdict = checkAgainstCheckout(identity, {
      revision: 'f2e331298f1cffb97d0b767584b3dac52f989286',
      source: 'the commit this window was built from',
    });
    expect(verdict.kind).toBe('unverifiable');
  });

  it('agrees when the engine really is on this build', () => {
    const verdict = checkAgainstCheckout(readIdentity(portfile), {
      revision: 'f2e331298f1cffb97d0b767584b3dac52f989286',
      source: 'the commit this window was built from',
    });
    expect(verdict.kind).toBe('matches');
  });
});
