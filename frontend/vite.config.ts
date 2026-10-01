import { readFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Plugin } from 'vite';
/* `vitest/config`'s defineConfig, not vite's, because this config carries a
   `test` block and vite's type does not know that key. Same function for
   everything else. */
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

/**
 * The engine publishes its host, port and bearer token to `engine.json` at the
 * repository root when it starts (app/security.py `write_portfile`). That file
 * is gitignored per-machine runtime state.
 *
 * `MLH_ENGINE_FILE` overrides it, and it is **the engine's own environment
 * variable** — `app/security.py` line 71 reads the same name for the same
 * purpose — so there is one name for one thing rather than a second convention
 * living in the dev server.
 *
 * WHY IT IS HERE, because a config knob with no reason is a config knob
 * somebody will misuse. Max's real `ml_harness.db` holds 1,119 runs and 33,500
 * metrics, and driving this interface writes to whatever database the engine
 * behind it opened: a thread, its messages, its events, and a fact_evidence row
 * for every measurement. Verifying a change against the shared engine on 8078
 * therefore means writing into that file. With this, a lane starts its own
 * engine on its own port with `ML_HARNESS_DB` pointed at a scratch file and
 * `MLH_ENGINE_FILE` pointed at a scratch portfile, runs a dev server against
 * it, and the shared portfile and the real database are both untouched:
 *
 *   MLH_ENGINE_FILE=<scratch>/engine.json ML_HARNESS_DB=<scratch>/verify.db \
 *     MLH_PORT=8079 python -m uvicorn app.main:app --port 8079
 *   MLH_ENGINE_FILE=<scratch>/engine.json npx vite --port 5200 --strictPort
 *
 * The default is unchanged, so `npm run dev` still means "the engine this
 * repository is running".
 */
const PORTFILE = process.env.MLH_ENGINE_FILE
  ? resolve(process.env.MLH_ENGINE_FILE)
  : resolve(import.meta.dirname, '..', 'engine.json');

/** app/config.py DEFAULT_PORT. Used only to have a target before the engine
 *  has ever run; the real value always comes from the portfile. */
const DEFAULT_ENGINE_ORIGIN = 'http://127.0.0.1:8078';

/**
 * `app/security.py write_portfile` writes exactly these five keys today.
 *
 * The index signature is the load-bearing part. A sibling lane is adding a
 * build identity to this file, and the page's job is to notice when the engine
 * changes underneath it — so this config forwards **every** key it finds rather
 * than a list it was taught, and a new field reaches the browser the day the
 * engine starts writing one, with no edit here. See `src/lib/engine/identity.ts`
 * for why the client is written the same way round.
 */
interface Portfile {
  host?: string;
  port?: number;
  base_url?: string;
  token?: string;
  pid?: number;
  [field: string]: unknown;
}

function readPortfile(): Portfile | null {
  try {
    return JSON.parse(readFileSync(PORTFILE, 'utf8')) as Portfile;
  } catch {
    return null;
  }
}

/**
 * Anything whose NAME suggests a secret is dropped before the payload above is
 * forwarded. Kept in step with `SECRET_FIELD_PATTERN` in
 * `src/lib/engine/identity.ts`; the client strips again on arrival, because two
 * cheap filters are the right price for "forward everything" not turning into
 * "publish the next secret somebody adds".
 */
const SECRET_FIELD = /token|secret|password|credential|\bkeys?\b/i;

function withoutSecrets(payload: Portfile): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(payload).filter(([key]) => !SECRET_FIELD.test(key)),
  );
}

/**
 * The revision this dev server is serving the page from, read out of `.git`.
 *
 * WHY THE PAGE NEEDS IT. The engine and the page are two processes started
 * separately, and on 2026-08-20 they were three commits apart for an hour: the
 * page was current, the engine was yesterday's, and the only symptom was
 * `gpu_name: null` on a machine with an idle RTX 2060 SUPER. "Are you running
 * my code" is the question that was never asked, and this is the half of the
 * answer the browser cannot get for itself.
 *
 * This is HEAD, not a hash of the working tree — uncommitted edits move neither
 * side, so a dirty checkout produces no false alarm and no false comfort. Read
 * with `readFileSync`, never a subprocess: the launcher may shell out, the
 * product may not, and a dev server that spawns `git` for every page load is a
 * habit this repository should not acquire.
 */
function readCheckout(): { revision: string; source: string } | null {
  const root = resolve(import.meta.dirname, '..');
  try {
    let gitDir = resolve(root, '.git');
    const stat = statSync(gitDir);
    if (stat.isFile()) {
      /* A worktree: `.git` is a file holding `gitdir: <path>`. */
      const pointer = readFileSync(gitDir, 'utf8').trim();
      const match = /^gitdir:\s*(.+)$/.exec(pointer);
      if (!match) return null;
      gitDir = resolve(root, match[1]);
    }

    const head = readFileSync(resolve(gitDir, 'HEAD'), 'utf8').trim();
    const ref = /^ref:\s*(.+)$/.exec(head);
    if (!ref) {
      /* Detached HEAD holds the sha directly. */
      return { revision: head, source: `${gitDir}/HEAD (detached)` };
    }

    /* A worktree's refs live in the common dir, not beside its HEAD. */
    const roots = [gitDir];
    try {
      const common = readFileSync(resolve(gitDir, 'commondir'), 'utf8').trim();
      roots.push(resolve(gitDir, common));
    } catch {
      /* Not a worktree. One root is all there is. */
    }

    for (const base of roots) {
      try {
        const sha = readFileSync(resolve(base, ref[1]), 'utf8').trim();
        if (sha) return { revision: sha, source: `${base}/${ref[1]}` };
      } catch {
        /* Try the next root, then packed-refs. */
      }
      try {
        const packed = readFileSync(resolve(base, 'packed-refs'), 'utf8');
        for (const line of packed.split('\n')) {
          const [sha, name] = line.trim().split(/\s+/);
          if (name === ref[1] && sha) {
            return { revision: sha, source: `${base}/packed-refs` };
          }
        }
      } catch {
        /* Fall through to null. Unverifiable is a real answer. */
      }
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Serves `engine.json` back to the page on a dev-only route.
 *
 * A browser cannot read a file off disk. `scripts/open_dashboard.py` solves
 * the same problem today by putting the token in the URL once and moving it to
 * sessionStorage; this is the dev-server equivalent and keeps the token out of
 * the URL bar and out of browser history entirely.
 *
 * ── IT IS ALSO WHERE A PAGE GOES TO ASK "AM I STILL TALKING TO THE SAME
 * ENGINE" ────────────────────────────────────────────────────────────────────
 *
 * The bearer token rotates on every engine start, so a tab left open starts
 * 401ing with no explanation — everything already loaded keeps working,
 * everything new fails, and the page has no story for it. This route is re-read
 * on a 401 (`src/lib/engine/client.ts`) and on a timer
 * (`src/lib/engine/liveness.ts`), which is why it is `no-store` and why it now
 * carries two things it did not:
 *
 *   `engine`   — the portfile minus anything secret, forwarded WHOLE. `pid`
 *                alone already answers "did it restart"; whatever the engine
 *                starts publishing about its build answers "did the code
 *                change", without this file being taught the name.
 *   `checkout` — the revision this dev server is serving the page from, so the
 *                two halves of a two-process dev setup can be compared at all.
 *
 * `base_url` and `token` are unchanged and still top-level: an older client
 * reads exactly what it read before.
 */
function enginePortfilePlugin(): Plugin {
  return {
    name: 'mlh-engine-portfile',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/__engine/session', (_req, res) => {
        const portfile = readPortfile();
        const checkout = readCheckout();
        res.setHeader('Content-Type', 'application/json');
        res.setHeader('Cache-Control', 'no-store');
        if (!portfile?.token) {
          res.statusCode = 200;
          res.end(
            JSON.stringify({
              error:
                'engine.json was not found where this dev server looked, so ' +
                'the engine is not running. Start it with: ' +
                'python -m uvicorn app.main:app --host 127.0.0.1 --port 8078',
              checkout,
            }),
          );
          return;
        }
        res.end(
          JSON.stringify({
            base_url: portfile.base_url ?? DEFAULT_ENGINE_ORIGIN,
            token: portfile.token,
            engine: withoutSecrets(portfile),
            checkout,
          }),
        );
      });
    },
  };
}

const engineOrigin = readPortfile()?.base_url ?? DEFAULT_ENGINE_ORIGIN;

export default defineConfig({
  plugins: [react(), enginePortfilePlugin()],
  /**
   * THE REVISION THIS BUNDLE WAS BUILT FROM, baked in.
   *
   * `readCheckout()` above answers "what is this dev server serving" and the
   * dev route publishes it. An INSTALLED app has no dev server and no checkout
   * beside the exe, so `engine_status` returns `checkout: null` and
   * `checkAgainstCheckout` can only answer `unverifiable` - which is how Max
   * ran for a day and a half, on 2026-09-19/20, against an engine started on
   * 2026-09-19 at 01:08 on commit c0cccd4 while three later commits sat on
   * main. Two whole cycles of fixes never reached him, the launcher's own
   * probe said "its build matches this working tree", and nothing on screen
   * disagreed.
   *
   * A built page knows one thing for certain: which commit it was built from.
   * Comparing THAT against the engine's `build.sha` is the question an
   * installed window can actually ask, so it is baked in here at build time.
   * `null` in a dev build with no readable `.git`, which stays `unverifiable`
   * and says so.
   */
  define: {
    __UI_REVISION__: JSON.stringify(readCheckout()?.revision ?? null),
  },
  /**
   * THE FRONTEND HAD NO TEST RUNNER AT ALL until 2026-08-27, and
   * `docs/PHASES.md` carried it as step 9 of the queue for exactly as long.
   * Every UI check in this repository's history was a person opening a browser
   * — which is why `AGENTS.md` requires one, and why three real defects were
   * caught by a screenshot after passing every assertion that existed.
   *
   * A browser check is still required and this does not replace it. What it
   * replaces is the class of thing a browser check is a wasteful way to find:
   * a component that renders the wrong count, a client that posts to the wrong
   * path, a formatter that drops a unit. `environment: 'jsdom'` because those
   * questions are about a DOM; `globals: false` because an import is cheaper to
   * read than a global nobody declared.
   */
  test: {
    environment: 'jsdom',
    globals: false,
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
    /* CSS IS STILL NOT PROCESSED - EXCEPT WHEN IT IS ASKED FOR AS TEXT.
     *
     * This was `css: false`, which is right: jsdom does no layout, so applying
     * a stylesheet buys nothing and costs a transform per test file. But
     * `false` is implemented by emptying every module whose id looks like CSS,
     * and `shell.css?raw` looks like CSS - so a test that imports a stylesheet
     * to READ it got an empty string and passed its assertions against
     * nothing.
     *
     * It matters because `src/lib/thePanesAreContainers.test.ts` guards a
     * property no render test can see: a `@container` query whose element has
     * no `container-type` ancestor does not error, does not warn, and silently
     * never matches. The only way to check the declaration is to read the file,
     * and `node:fs` is not available to `tsconfig.app.json` (`types` is
     * `["vite/client"]`).
     *
     * So: anything with a `?raw` query is processed - which for `?raw` means
     * vite's own "export this file as a string" and nothing else. A plain
     * `import './shell.css'` is still emptied exactly as before.
     */
    css: { include: [/\?raw/] },
  },
  server: {
    /**
     * PINNED, AND `strictPort` IS THE POINT.
     *
     * A stale process on Vite's default 5173 was serving a DIFFERENT app in
     * this project and a screenshot taken against it was reported as evidence
     * for this one. Vite's normal behaviour makes that easy: if the port is
     * taken it silently moves to the next free one, so "I ran the dev server"
     * and "I looked at the dev server I ran" stop being the same sentence.
     *
     * With `strictPort`, a second instance fails loudly instead of landing
     * somewhere nobody checked.
     */
    port: 5199,
    strictPort: true,
    proxy: {
      /**
       * Everything the page sends to the engine goes through here.
       *
       * WHY A PROXY AND NOT A DIRECT FETCH — verified by running the engine
       * and asking it:
       *
       *   curl -i -H "Origin: http://localhost:5173" \
       *        http://127.0.0.1:8078/local_specs
       *   → HTTP/1.1 403 Forbidden   {"detail":"cross-site request refused"}
       *
       * `app/security.py allowed_origins()` permits exactly two origins, both
       * on the ENGINE's own port. A dev server on :5173 is not one of them and
       * never will be. `origin_is_allowed()` documents that a MISSING Origin
       * means "the caller is not a browser — a curl, the launcher, a test",
       * and those are precisely the callers the bearer token checks. The proxy
       * is such a caller: it is a Node process, not a page. So it deletes
       * `Origin` and presents the token, which is exactly the contract that
       * function describes. The security boundary is satisfied, not bypassed:
       * authentication is still by token, and no browser page can reach the
       * engine without going through a server this user started.
       */
      '/engine': {
        target: engineOrigin,
        changeOrigin: false,
        rewrite: (path) => path.replace(/^\/engine/, ''),
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq) => {
            proxyReq.removeHeader('origin');
            proxyReq.removeHeader('referer');
            /* The client attaches its own Authorization (see
               src/lib/engine/client.ts) so the real code path is exercised.
               The one caller that CANNOT is EventSource, which has no API for
               request headers — so the token is filled in only when absent.
               Under Tauri this gap needs a real answer; see
               src/lib/engine/events.ts. */
            if (!proxyReq.getHeader('authorization')) {
              const token = readPortfile()?.token;
              if (token) proxyReq.setHeader('authorization', `Bearer ${token}`);
            }
          });
        },
      },
    },
  },
});
