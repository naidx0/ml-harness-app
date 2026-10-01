/**
 * CS19 — `paneProvenance` still names the source for title/aria use, but the
 * UI no longer shows a standing “from GET …” strip in people’s faces (Max over
 * DESIGN_SYSTEM §9.12).
 */

import { describe, expect, it } from 'vitest';

import { paneProvenance } from './PaneStack';

describe('a derived pane still knows its source', () => {
  it('the Stage names the request and the thread it read', () => {
    const line = paneProvenance('stage', null, { threadId: 33 });
    expect(line).toContain('GET /api/threads/33/stage');
  });

  it('says nothing when there is no thread to have read', () => {
    expect(paneProvenance('stage', null, { threadId: null })).toBeNull();
  });

  it('leaves the machine pane line alone', () => {
    expect(paneProvenance('machine', null)).toBe('source not read yet');
  });

  it('claims no source for a pane that derives nothing', () => {
    expect(paneProvenance('terminal', null)).toBeNull();
  });
});
