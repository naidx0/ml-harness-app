/* A SECOND dev server, for driving the empty-providers walk against a scratch
 * engine, without touching the one another lane is already running on 5199.
 *
 * Two things are isolated deliberately:
 *   - `port` 5233, because 5199 is pinned with `strictPort` and correctly
 *     refused a second instance rather than sliding to 5200 and letting a
 *     screenshot be taken of a different app. That refusal is the feature.
 *   - `cacheDir`, because two servers with different configs sharing
 *     `node_modules/.vite` re-optimise over each other, and the other server
 *     belongs to somebody else's session.
 *
 * KEPT, and the docstring that said otherwise was wrong the moment this was
 * committed. It read "untracked and temporary; delete it when the walk is
 * recorded" - written while it was scratch, and then committed, because it is
 * the instrument that made the empty-providers walk drivable at all without
 * disturbing another session's server. Deleting it means the next person
 * rebuilds it, and a file whose comment describes a state it is no longer in
 * is worse than no comment.
 */
import { defineConfig } from 'vite';
import base from './vite.config.ts';

export default defineConfig({
  ...base,
  cacheDir: 'node_modules/.vite-stranger',
  server: { ...(base as any).server, port: 5233, strictPort: true },
});
