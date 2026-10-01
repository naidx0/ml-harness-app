/**
 * The typed client for the engine API.
 *
 * ARCHITECTURE §4.1: the frontend "never contains a business rule. Never
 * parses a model config, computes a VRAM figure, ranks a model, or decides
 * anything about ML." Nothing in this file computes; it transports.
 *
 * Every function below was checked against the running engine, not against a
 * document. Where a route does not exist it throws `NotImplementedError` and
 * names where it was specified, because a stub that returns a plausible object
 * is indistinguishable from a working feature until it ships.
 */

import { engineSession, type EngineSession } from './config';
import { nativeEngineFetch } from './shell';
import { recoverFromUnauthorized } from './liveness';
import type {
  Keychain,
  LocalSpecs,
  Project,
  Provider,
  ProviderCreate,
  ProviderPreset,
  ProviderUpdate,
  Studios,
  Thread,
  ThreadDetail,
  ToolCatalogue,
  ToolRunResult,
  TurnReceipt,
} from './types';

/** A request the engine refused, carrying the status so callers can tell
 *  "not authenticated" from "not running", and the detail so the interface can
 *  print what the engine actually said rather than a paraphrase. */
export class EngineError extends Error {
  readonly status: number;
  readonly path: string;
  readonly detail: string;
  /**
   * `detail` as the engine sent it, when it sent a STRUCTURE rather than a
   * sentence.
   *
   * Added for one case that is not an error at all: `POST /api/storms` answers
   * 409 with `{error, approved, now, changed, build, what_now}` when the plan
   * moved between being shown and being approved. That is the contract working
   * — "any deviation stops and asks" — and flattening it to a line would throw
   * away the very thing the person needs to see, which is WHAT changed. The
   * string form is still filled in for every ordinary refusal, so nothing that
   * reads `detail` has to know this exists.
   */
  readonly body: unknown;

  constructor(
    status: number,
    path: string,
    message: string,
    detail = '',
    body: unknown = null,
  ) {
    super(message);
    this.status = status;
    this.path = path;
    this.detail = detail;
    this.body = body;
    this.name = 'EngineError';
  }
}

/** The engine could not be reached at all — usually it is not running. */
export class EngineUnavailableError extends Error {
  readonly reason: string;

  constructor(reason: string) {
    super(reason);
    this.reason = reason;
    this.name = 'EngineUnavailableError';
  }
}

/** Thrown by every endpoint the engine has not been written yet. */
export class NotImplementedError extends Error {
  readonly path: string;
  readonly specifiedIn: string;

  constructor(path: string, specifiedIn: string) {
    super(
      `${path} does not exist in the engine yet. Specified in ${specifiedIn}. ` +
        `This client types it; it does not fake it.`,
    );
    this.path = path;
    this.specifiedIn = specifiedIn;
    this.name = 'NotImplementedError';
  }
}

/**
 * The fetch wrapper. Attaches the bearer token, refuses to cache, and turns a
 * non-2xx into a typed error carrying the engine's own `detail` string.
 *
 * The detail matters. `POST /api/threads/{id}/turn` answers 409 with "No model
 * is connected. Connect one, or use the controls directly — every tool in this
 * app is also a button", and that sentence is better than anything this layer
 * could write in its place.
 *
 * ── A 401 IS NOT A DEAD END ──────────────────────────────────────────────────
 *
 * `app/security.py` mints a new bearer token every time the engine starts. A
 * tab left open across a restart is holding a secret the engine has never heard
 * of, and the way that used to present was the worst possible way: everything
 * already on screen kept working, everything new returned 401, and nothing said
 * why. Max has had that happen to him once.
 *
 * So on 401 this re-reads `/__engine/session` ONCE (`recoverFromUnauthorized`),
 * and either retries with the fresher token or throws an error whose `detail`
 * is the sentence explaining why retrying cannot help. Once, not in a loop:
 * a second 401 after a fresh token is a different fault and deserves to be
 * reported rather than hammered at.
 */
export async function engineFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const session = await engineSession();
  if (!session.available) {
    throw new EngineUnavailableError(
      session.reason ?? 'The engine is not running.',
    );
  }

  const response = await send(path, init, session);
  if (response.status !== 401 || !canBeSentTwice(init)) {
    return await checked(path, init, response);
  }

  const recovery = await recoverFromUnauthorized(session.token);
  if (recovery.kind === 'stuck') {
    throw new EngineError(401, path, recovery.why, recovery.why, null);
  }
  return await checked(path, init, await send(path, init, recovery.session));
}

async function send(
  path: string,
  init: RequestInit,
  session: EngineSession,
): Promise<Response> {
  const headers = new Headers(init.headers);
  if (session.token) {
    headers.set('Authorization', `Bearer ${session.token}`);
  }
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  /* IN THE SHELL, THE SHELL CARRIES IT. Two measured reasons, one day apart:
     the WebView refused loopback via evolving browser policy, and this
     function - the comment in config.ts notwithstanding - never actually used
     `engineBaseUrl`, so packaged requests always went relative into
     tauri.localhost and came back as HTML. The carrier takes the absolute
     engine URL and no browser rule applies to it. */
  if (session.engineBaseUrl) {
    const carried = await nativeEngineFetch(
      `${session.engineBaseUrl}${path}`,
      {
        method: init.method ?? 'GET',
        body: typeof init.body === 'string' ? init.body : null,
        token: session.token,
      },
    );
    if (carried) return carried;
  }
  return await fetch(`${session.baseUrl}${path}`, {
    ...init,
    headers,
    cache: 'no-store',
  });
}

/**
 * A retry has to re-send the body, and a body that has already been read cannot
 * be re-sent.
 *
 * Every caller in this file passes a `JSON.stringify` string, so this is true
 * today for all of them — but a stream body would be silently truncated on the
 * retry rather than failing, and a silently wrong request is the family of bug
 * this whole file is about. Streams do not get retried; they get their 401
 * reported.
 */
function canBeSentTwice(init: RequestInit): boolean {
  const body = init.body;
  return (
    body === undefined ||
    body === null ||
    typeof body === 'string' ||
    body instanceof URLSearchParams ||
    body instanceof Blob ||
    body instanceof ArrayBuffer ||
    ArrayBuffer.isView(body)
  );
}

async function checked(
  path: string,
  init: RequestInit,
  response: Response,
): Promise<Response> {
  if (response.ok) return response;
  const { text, body } = await readDetail(response);
  throw new EngineError(
    response.status,
    path,
    text ||
      `${init.method ?? 'GET'} ${path} → ${response.status} ${response.statusText}`,
    text,
    body,
  );
}

/** FastAPI answers errors as `{"detail": …}`; 422 makes `detail` a list of
 *  field errors. Both are turned into one readable line. */
async function readDetail(
  response: Response,
): Promise<{ text: string; body: unknown }> {
  try {
    const payload = (await response.clone().json()) as { detail?: unknown };
    const detail = payload?.detail;
    if (typeof detail === 'string') return { text: detail, body: null };
    if (Array.isArray(detail)) {
      return {
        text: detail
          .map((item) => {
            const entry = item as { loc?: unknown[]; msg?: string };
            const where = Array.isArray(entry.loc) ? entry.loc.join('.') : '';
            return where ? `${where}: ${entry.msg ?? ''}` : String(entry.msg ?? '');
          })
          .join('; '),
        body: null,
      };
    }
    /* A structured refusal. Kept whole; see EngineError.body. */
    if (detail && typeof detail === 'object') {
      const named = detail as { detail?: unknown; error?: unknown };
      const text =
        typeof named.detail === 'string'
          ? named.detail
          : typeof named.error === 'string'
            ? named.error
            : '';
      return { text, body: detail };
    }
  } catch {
    /* Not JSON. The status line is all we have. */
  }
  return { text: '', body: null };
}

export async function engineJson<T = unknown>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await engineFetch(path, init);
  return (await response.json()) as T;
}

export function postJson<T = unknown>(path: string, body?: unknown): Promise<T> {
  return engineJson<T>(path, {
    method: 'POST',
    body: JSON.stringify(body ?? {}),
  });
}

const getJson = engineJson;

/* ══════════════════════════════════════════════════════════════════════════
   Machine
   ══════════════════════════════════════════════════════════════════════════ */

/** `GET /health` → `{"status": "ok"}`. No token required. */
export function getHealth(): Promise<{ status: string }> {
  return getJson('/health');
}

/**
 * `GET /local_specs` — app/hwdetect.py, mounted in app/main.py at the app
 * root, NOT at `/api/local_specs` as docs/ROADMAP.md step 1.22 says.
 *
 * The only source of hardware facts in the product. Every field carries a
 * provenance entry; a field the engine could not read comes back `null` with
 * provenance `defaulted`, never as a number.
 */
export function getLocalSpecs(): Promise<LocalSpecs> {
  return getJson('/local_specs');
}

/** `GET /api/recipes` — app/main.py. Requires the bearer token. */
export function listRecipes(): Promise<unknown> {
  return getJson('/api/recipes');
}

/* ══════════════════════════════════════════════════════════════════════════
   The transcript — app/events.py, app/main.py
   ══════════════════════════════════════════════════════════════════════════ */

/* ── Projects ───────────────────────────────────────────────────────────────
   THESE ROUTES EXIST NOW. `client.ts` and `Rail.tsx` both used to carry a note
   that `GET /api/projects` did not exist and that the rail was a flat list of
   threads until it did. It does — `app/main.py` serves all four — and the note
   is deleted rather than left to rot beside working code.

   Checked against the running engine on 127.0.0.1:8078, not against
   docs/ROADMAP.md step 1.3, which still says the rail is threads-only. */

/** `GET /api/projects`. Newest first (id DESC); live only unless asked. */
export function listProjects(includeArchived = false): Promise<Project[]> {
  return getJson(
    `/api/projects${includeArchived ? '?include_archived=true' : ''}`,
  );
}

/** `POST /api/projects` → 201. `portal` defaults to `consumer` on the engine
 *  and is validated there against `db.PORTALS`, so a typo is a 500 rather than
 *  a project belonging to neither product. */
export function duplicateProject(projectId: number): Promise<Project> {
  /* Same root, fresh history - the engine's own reading of what a copy is;
     see the route's docstring for why threads deliberately stay behind. */
  return postJson(`/api/projects/${projectId}/duplicate`, {});
}

export function createProject(
  name: string,
  options: { root_path?: string; portal?: 'consumer' | 'enterprise' } = {},
): Promise<Project> {
  return postJson('/api/projects', { name, ...options });
}

/** `POST /api/projects/{id}/rename`. */
export function renameProject(projectId: number, name: string): Promise<Project> {
  return postJson(`/api/projects/${projectId}/rename`, { name });
}

/** `POST /api/projects/{id}/root` — attach the folder a project works in. */
export function setProjectRoot(
  projectId: number,
  rootPath: string,
): Promise<{ id: number; root_path: string }> {
  return postJson(`/api/projects/${projectId}/root`, { root_path: rootPath });
}

/**
 * `POST /api/projects/{id}/archive`.
 *
 * **409 when it is the last live project**, with the engine's own sentence:
 * "cannot archive the last project; create another one first". That is a
 * refusal with a reason, not a failure — `db.default_project()` would mint a
 * fresh `Default` behind an empty rail and the next thread would land somewhere
 * the user cannot see the old ones. Surface the detail; do not retry.
 */
export function archiveProject(projectId: number): Promise<Project> {
  return postJson(`/api/projects/${projectId}/archive`);
}

/** What a delete removed, by table. The engine counts; the rail repeats it. */
export interface Deleted {
  ok: true;
  deleted: number;
  removed: Record<string, number>;
}

/** `DELETE /api/projects/{id}`. The other door: the project, every thread in
 *  it, its memory and its ledger rows are removed. Nothing on disk is touched.
 *  409 for the last live project, for `archiveProject`'s reason. */
export function deleteProject(projectId: number): Promise<Deleted> {
  return getJson(`/api/projects/${projectId}`, { method: 'DELETE' });
}

/** One reading of what a prompt cost, as `app/contextwindow.py` returns it. */
export interface ContextTurn {
  event_id: number;
  system: number;
  tools: number;
  history: number;
  total: number;
  messages: number;
  tool_count: number;
  window: number | null;
  mode: string;
  /** Every named piece of that prompt, biggest first - the instruction set,
   *  the notes, the standing brief, the tool schemas by pack, the
   *  conversation. `app/contextwindow.py::parts`. */
  parts?: { key: string; label: string; why: string; tokens: number; count: number }[];
  /** Which tools spent a full schema on that turn, and why each one did.
   *  `app/tools/blocks.py::on_the_wire` chooses them from the tools the packs
   *  made active: `considered` is that pool, `tools` is what rode, `withheld`
   *  is the rest - still callable, still named in the capability list, just
   *  without their parameters in the room. `{}` on a turn taken before the
   *  record existed. */
  schemas_on_wire?: {
    tools: string[];
    because: Record<string, string>;
    considered: string[];
    withheld: string[];
    all_schemas: boolean;
    switch: string;
  };
}

export interface ContextWindowRead {
  thread_id: number;
  model: string;
  window: number | null;
  window_provenance: string;
  latest: ContextTurn | null;
  headroom: number | null;
  share: number | null;
  turns: ContextTurn[];
  compactions: {
    event_id: number;
    messages_summarised: number | null;
    tokens_before: number | null;
    tokens_after: number | null;
  }[];
  compaction_at: number;
  counted_by: string;
}

/** `GET /api/threads/{id}/context`. Counted when the prompt was assembled. */
export function readContextWindow(threadId: number): Promise<ContextWindowRead> {
  return getJson(`/api/threads/${threadId}/context`);
}

/** CS19 — force a context compaction for this thread. */
export function compactThread(threadId: number): Promise<{
  ok: boolean;
  detail?: string;
  messages_summarised?: number;
  tokens_before?: number;
  tokens_after?: number;
}> {
  return postJson(`/api/threads/${threadId}/compact`);
}

/** CS3 — glanceable tokens / tool calls / wall time with provenance. */
export interface ThreadUsageRead {
  thread_id: number;
  turns: {
    started_id: number;
    at: string;
    tokens: number | null;
    tool_calls: number;
    seconds: number | null;
    window: number | null;
    mode: string;
  }[];
  thread: {
    latest_tokens: number | null;
    /** Sum of per-turn prompt totals that reported tokens (measured). */
    total_tokens?: number | null;
    total_tool_calls: number;
    total_seconds: number | null;
    window: number | null;
    window_provenance: string;
    turn_count: number;
  };
  provenance: {
    tokens: string;
    tool_calls: string;
    seconds: string;
    window: string;
  };
  counted_by: Record<string, string>;
}

export function readThreadUsage(threadId: number): Promise<ThreadUsageRead> {
  return getJson(`/api/threads/${threadId}/usage`);
}

/** The long run on a thread (`app/longrun.py`). `state` is empty when this
 *  thread has never had one, which is not an error. */
export interface RunState {
  thread_id: number;
  state: '' | 'running' | 'done' | 'stopped' | 'failed';
  turns?: number;
  cap?: number;
  stop_reason?: string;
  detail?: string;
  steps?: number;
  open?: number;
  done?: number;
  parked?: { step: string; why: string }[];
  /** How long the run has been going, or took. Seconds, from the engine's own
   *  two timestamps rather than a clock in the page. */
  seconds?: number | null;
  started_at?: string;
}

/** `POST /api/threads/{id}/run`. Takes turns until the plan is worked down.
 *  409 carries the engine's own sentence - plan mode, or nothing open. */
export function startRun(threadId: number): Promise<{ ok: boolean; run: RunState }> {
  return postJson(`/api/threads/${threadId}/run`);
}

/** `POST /api/threads/{id}/run/stop`. Ends after the turn in flight. */
export function stopRun(threadId: number): Promise<RunState> {
  return postJson(`/api/threads/${threadId}/run/stop`);
}

/** `POST /api/threads/{id}/turn/stop`. Ends the TURN at its next round
 *  boundary, and the run with it when there is one. Never lands inside a tool
 *  call - see `app/interrupt.py`. */
export function stopTurn(
  threadId: number,
): Promise<{ ok: boolean; a_turn_was_running: boolean; run_stopped: boolean }> {
  return postJson(`/api/threads/${threadId}/turn/stop`);
}

/** CS2 — mint a remote Approve + Stop URL. Raw token returned once. */
export function createRemoteLink(
  threadId: number,
  body: { label?: string; expires_in_hours?: number } = {},
): Promise<{
  link_id: number;
  thread_id: number;
  token: string;
  url: string;
  expires_at: string;
}> {
  return postJson(`/api/threads/${threadId}/remote_link`, body);
}

export function revokeRemoteLink(linkId: number): Promise<{ link_id: number; revoked: boolean }> {
  return getJson(`/api/remote_links/${linkId}`, { method: 'DELETE' });
}

export function readRun(threadId: number): Promise<RunState> {
  return getJson(`/api/threads/${threadId}/run`);
}

/* ── Threads ───────────────────────────────────────────────────────────── */

/** `GET /api/threads`. Newest first; the engine orders them. Unfiltered it is
 *  every live thread across every project, which is what the rail's tree needs
 *  — one request, grouped in the browser, rather than one request per folder. */
export function listThreads(projectId?: number): Promise<Thread[]> {
  return getJson(
    `/api/threads${projectId === undefined ? '' : `?project_id=${projectId}`}`,
  );
}

/** `POST /api/threads`. Omitting `project_id` puts the thread in
 *  `db.default_project()`, which is what the engine does, not what we guess. */
export function createThread(
  title: string,
  projectId?: number | null,
): Promise<Thread> {
  return postJson('/api/threads', {
    title,
    ...(projectId === null || projectId === undefined
      ? {}
      : { project_id: projectId }),
  });
}

/** `POST /api/threads/{id}/rename`. */
export function renameThread(threadId: number, title: string): Promise<Thread> {
  return postJson(`/api/threads/${threadId}/rename`, { title });
}

/** `POST /api/threads/{id}/archive`. Not deletion — the transcript is the
 *  artifact, so this writes a timestamp and every message stays where it is. */
export function archiveThread(threadId: number): Promise<Thread> {
  return postJson(`/api/threads/${threadId}/archive`);
}

/** One attachment, as `list_context` reports it. */
export interface ThreadContext {
  id: number;
  path: string;
  kind: string;
  role: string;
}

/** `GET /api/threads/{id}/contexts`. A read, so the line above the composer
 *  can name the attached file without filing a transcript row per open. */
export function listThreadContexts(threadId: number): Promise<{ contexts: ThreadContext[] }> {
  return getJson(`/api/threads/${threadId}/contexts`);
}

/** `DELETE /api/threads/{id}`. Removes the thread and every row keyed to it;
 *  one `thread.deleted` event stays on the project. Nothing on disk. */
export function deleteThread(threadId: number): Promise<Deleted> {
  return getJson(`/api/threads/${threadId}`, { method: 'DELETE' });
}

/** `POST /api/threads/{id}/move`. 404 names which of the two rows was missing. */
export function moveThread(threadId: number, projectId: number): Promise<Thread> {
  return postJson(`/api/threads/${threadId}/move`, { project_id: projectId });
}

/** `GET /api/threads/{id}` → the thread row and every message on it. */
export function getThread(threadId: number): Promise<ThreadDetail> {
  return getJson(`/api/threads/${threadId}`);
}

/** `GET /ui/report/{id}` — printable journey page. Read-only on the engine. */
export async function threadReportUrl(threadId: number): Promise<string> {
  const session = await engineSession();
  if (!session.available) {
    throw new EngineUnavailableError(
      session.reason ?? 'The engine is not running.',
    );
  }
  return `${session.baseUrl}/ui/report/${threadId}`;
}

/** `POST /api/threads/{id}/permission` — ladder step ask|measure|write|full. */
export function setThreadPermission(
  threadId: number,
  mode: string,
): Promise<
  Thread & {
    permission?: string;
    covers?: Record<string, string>;
    never_covers?: Record<string, string>;
  }
> {
  return postJson(`/api/threads/${threadId}/permission`, { mode });
}

/** `POST /api/threads/{id}/autonomous` — legacy boolean; maps to write/ask. */
export function setThreadAutonomous(
  threadId: number,
  on: boolean,
): Promise<
  Thread & {
    permission?: string;
    covers?: Record<string, string>;
    never_covers?: Record<string, string>;
  }
> {
  return postJson(`/api/threads/${threadId}/autonomous`, { on });
}

/** `POST /api/threads/{id}/mode` - the person puts this thread in `plan` or
 *  `build`. THE PERSON'S DOOR: no model can reach it, and nothing in the
 *  engine reads the question and picks. See `app/modes.py`. */
export function setThreadMode(
  threadId: number,
  mode: 'plan' | 'build',
): Promise<Thread & { modes?: Record<string, string> }> {
  return postJson(`/api/threads/${threadId}/mode`, { mode });
}

/** `POST /api/threads/{id}/plan` - the agreed steps, as markdown. Separate
 *  from the mode because accepting a plan and starting to build are two
 *  decisions; the control does both in one press and the engine keeps them
 *  apart so that it can. */
export function setThreadPlan(
  threadId: number,
  plan: string | null,
): Promise<Thread> {
  return postJson(`/api/threads/${threadId}/plan`, { plan });
}

/** CS5 — restore plan/todo ticks from a `turn.effects` snapshot. Facts stay. */
export function revertTurnEffects(
  threadId: number,
  effectsId: number,
): Promise<{ ok: boolean; facts_untouched: boolean }> {
  return postJson(`/api/threads/${threadId}/effects/${effectsId}/revert`, {});
}

export function setThreadTodo(
  threadId: number,
  todo: string | null,
): Promise<Thread> {
  return postJson(`/api/threads/${threadId}/todo`, { todo });
}

export function setChecklistSource(
  threadId: number,
  source: 'plan' | 'todo',
): Promise<Thread> {
  return postJson(`/api/threads/${threadId}/checklist_source`, { source });
}

/** `POST /api/threads/{id}/goal` — the person corrects (or, with an empty
 *  string, clears) what the thread is for. Stored verbatim: this is their
 *  door, and their words are the goal. */
export function setThreadGoal(threadId: number, goal: string): Promise<Thread> {
  return postJson(`/api/threads/${threadId}/goal`, { goal });
}

/* ── Curated memory — this project's notes and who the person is ─────────── */

export type MemoryTarget = 'project' | 'user';

export interface MemoryBlock {
  entries: { id: number; content: string; created_at: string; updated_at: string }[];
  /** The block as one `§`-delimited text - the pane's edit form. */
  text: string;
  used: number;
  limit: number;
}

/** `GET /api/memory?project_id=` — both blocks, Hermes' limits included. */
export function getMemory(projectId: number | null): Promise<Record<MemoryTarget, MemoryBlock>> {
  const query = projectId === null ? '' : `?project_id=${projectId}`;
  return engineJson(`/api/memory${query}`);
}

/** `PUT /api/memory` — the person's edit of one block, wholesale. Refused
 *  with `detail` when an entry carries a number with no origin word. */
export function saveMemory(
  target: MemoryTarget,
  projectId: number | null,
  text: string,
): Promise<{ ok: boolean; detail?: string; count?: number; used?: number; limit?: number }> {
  return engineJson('/api/memory', {
    method: 'PUT',
    body: JSON.stringify({ target, project_id: projectId, text }),
    headers: { 'Content-Type': 'application/json' },
  });
}

/* ── The workspace's own files — the Files pane's three doors ────────────── */

export interface WorkspaceFileRow {
  path: string;
  size: number;
  modified: number;
}

export interface WorkspaceListing {
  project: { id: number; name: string };
  root: string;
  files: WorkspaceFileRow[];
  count: number;
  left_unlisted: number;
  /** Files the walk saw and would not, or could not, list. Zero when the
   *  list IS the folder; anything else is said on screen, not swallowed. */
  skipped_outside_root?: number;
  unreadable?: number;
  read_at: number;
  source: string;
}

export interface WorkspaceFile {
  path: string;
  content: string;
  size: number;
  /** The stamp an edit must echo back — see `saveWorkspaceFile`. */
  modified: number;
  read_at: number;
}

/** `GET /api/projects/{id}/files` — relative paths, capped, dated. */
export function listWorkspaceFiles(projectId: number): Promise<WorkspaceListing> {
  return getJson(`/api/projects/${projectId}/files`);
}

/** `GET /api/projects/{id}/file?path=` — one file's text and its stamp. */
export function readWorkspaceFile(
  projectId: number,
  path: string,
): Promise<WorkspaceFile> {
  return getJson(
    `/api/projects/${projectId}/file?path=${encodeURIComponent(path)}`,
  );
}

/** `PUT /api/projects/{id}/file` — an edit to an existing file. Sends the
 *  `modified` the editor read, so a file that moved on since comes back as a
 *  409 instead of being silently clobbered. */
export function saveWorkspaceFile(
  projectId: number,
  path: string,
  content: string,
  expectModified: number,
): Promise<{ ok: boolean; path: string; size: number; modified: number }> {
  return engineJson(`/api/projects/${projectId}/file`, {
    method: 'PUT',
    body: JSON.stringify({ path, content, expect_modified: expectModified }),
  });
}

/** `POST /api/threads/{id}/report/save` — the journey report written into the
 *  project's own folder. 400, with the fix in the sentence, when the project
 *  has no folder attached. */
export function saveThreadReport(
  threadId: number,
): Promise<{ ok: boolean; wrote: string[]; detail: string }> {
  return postJson(`/api/threads/${threadId}/report/save`, {});
}

/** `GET /api/threads/{id}/export` — self-describing journey bundle. */
export async function downloadThreadExport(threadId: number): Promise<void> {
  const response = await engineFetch(`/api/threads/${threadId}/export`);
  const blob = await response.blob();
  const disposition = response.headers.get('Content-Disposition') ?? '';
  const match = disposition.match(/filename="([^"]+)"/);
  const filename = match?.[1] ?? `ml-harness-thread-${threadId}-report.json`;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

/**
 * `POST /api/threads/{id}/messages`.
 *
 * The role is always `user`; the engine will not take it from the body. The
 * write also appends a `message.created` event, so a client watching the
 * stream sees its own message arrive the same way it sees everything else.
 */
export function postMessage(threadId: number, content: string): Promise<unknown> {
  return postJson(`/api/threads/${threadId}/messages`, { content });
}

/**
 * `POST /api/threads/{id}/turn`. Runs one whole turn and returns only when it
 * is finished — the tokens go to the event stream, not to this response.
 *
 * So the caller opens the stream first and does not await this for anything it
 * wants to render. A 409 here means no model is connected.
 */
export function runTurn(
  threadId: number,
  options: {
    provider_id?: number;
    portal?: string;
    sensitive?: boolean;
    invite_goal_edit?: boolean;
  } = {},
): Promise<TurnReceipt> {
  return postJson(`/api/threads/${threadId}/turn`, options);
}

/* ══════════════════════════════════════════════════════════════════════════
   The connection — app/providers/
   ══════════════════════════════════════════════════════════════════════════ */

/** `GET /api/provider_presets` — endpoints a user can pick without typing a
 *  URL. The three local ones are first; that ordering is the engine's. */
export function listProviderPresets(): Promise<ProviderPreset[]> {
  return getJson('/api/provider_presets');
}

/** `GET /api/providers`. Never carries a key — see `has_key`. */
export function listProviders(): Promise<Provider[]> {
  return getJson('/api/providers');
}

/**
 * `POST /api/providers`.
 *
 * `api_key` is accepted here and goes straight to the OS keychain. It is never
 * written to SQLite and never echoed back. A 503 means the row was saved and
 * the key was NOT — the engine says so explicitly rather than pretending.
 */
export function createProvider(payload: ProviderCreate): Promise<Provider> {
  return postJson('/api/providers', payload);
}

/** `POST /api/providers/{id}/activate`. Exactly one provider is active. */
export function activateProvider(providerId: number): Promise<Provider> {
  return postJson(`/api/providers/${providerId}/activate`);
}

/**
 * `POST /api/providers/{id}/probe`. Asks the connection what it can do and
 * writes the answer on the row.
 *
 * This is a real network call to the model's server and can take a while: for
 * Ollama it reads `/api/show`, and on an older server that does not report
 * capabilities it falls back to spending one short turn asking the model to
 * call a trivial tool.
 */
export function probeProvider(providerId: number): Promise<Provider> {
  return postJson(`/api/providers/${providerId}/probe`);
}

/**
 * `PATCH /api/providers/{id}`.
 *
 * Leave `api_key` OFF the payload to keep whatever the keychain holds; send
 * `''` to delete it. Sending a key here goes to the keychain exactly as
 * `createProvider` does, and comes back only as `has_key`.
 */
export function updateProvider(
  providerId: number,
  patch: ProviderUpdate,
): Promise<Provider> {
  return getJson(`/api/providers/${providerId}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  });
}

/**
 * `DELETE /api/providers/{id}` — forget a connection AND its key.
 *
 * Both halves happen at the engine. Deleting the row alone would leave an API
 * key in the user's OS keychain with nothing left pointing at it, which is a
 * worse outcome than never having stored one.
 */
export function deleteProvider(providerId: number): Promise<Provider> {
  return getJson(`/api/providers/${providerId}`, { method: 'DELETE' });
}

/** `GET /api/keychain` — where a key would go on this machine, before one is
 *  typed. Carries no secret; every string on it is a source constant. */
export function getKeychain(): Promise<Keychain> {
  return getJson('/api/keychain');
}

export interface DiscoveryCandidate {
  name: string;
  base_url: string;
  adapter: string;
  reachable: boolean;
  models: string[];
  suggested_model?: string;
}

/** `GET /api/providers/discover` — what is already running on this machine.
 *  Probed live with sub-second timeouts; creates nothing. */
export function discoverProviders(): Promise<{ candidates: DiscoveryCandidate[] }> {
  return getJson('/api/providers/discover');
}

/* ══════════════════════════════════════════════════════════════════════════
   Every tool is also a control — app/tools/registry.py
   ══════════════════════════════════════════════════════════════════════════ */

/** `GET /api/tools` — the same declaration the model is given, described for
 *  a person. */
export function listTools(): Promise<ToolCatalogue> {
  return getJson('/api/tools');
}

/**
 * `GET /api/studios` — the capability packs, and what is inside each one.
 *
 * Read-only, and derived: `app/main.py::studios_ep` builds `pack_index` from
 * `blocks.pack_index()`, which reads the registry. So this is the same answer
 * `blocks.active()` scopes a turn with, shown to a person instead of to a
 * model, and there is no way for the two to disagree.
 */
export function listStudios(): Promise<Studios> {
  return getJson('/api/studios');
}

/**
 * `POST /api/tools/{name}` — run a tool as a button rather than as a model
 * tool call.
 *
 * 428 means the tool is marked `approval="always"` and was called without one;
 * 404 means there is no such tool.
 *
 * **This route writes nothing to the event log.** `run_tool_ep` calls the
 * registry and returns the result; it does not `events.append`. So a tool the
 * user runs from the controls is NOT in the durable transcript, and the
 * interface has to say so rather than let it look like one. See
 * `components/Controls.tsx`.
 */
export function runTool(
  name: string,
  args: Record<string, unknown> = {},
  approved = false,
  threadId: number | null = null,
): Promise<ToolRunResult> {
  return postJson(`/api/tools/${encodeURIComponent(name)}`, {
    arguments: args,
    approved,
    /* Which conversation the facts belong to. `app/main.py`: "Facts measured
       without one are machine scope, which is right for hardware and wrong for
       anything about a project, so the interface sends it." An eval set counted
       in one thread must not open a gate in another. */
    thread_id: threadId,
  });
}

/**
 * `GET /api/evidence` — why the harness believes what it believes.
 *
 * One row per claim or measurement, newest first, with who said it and how.
 * `app/main.py`: "Invariant 3 says every displayed number carries its
 * provenance. This is where the interface gets it for the facts a diagnosis was
 * computed from."
 *
 * Rows with no thread are machine scope — the hardware in this box is the
 * hardware in this box — and come back for every thread. Rows with a thread
 * belong to that thread and to no other.
 */
export function getEvidence(threadId: number | null): Promise<unknown> {
  const query = threadId === null ? '' : `?thread_id=${encodeURIComponent(threadId)}`;
  return getJson(`/api/evidence${query}`);
}

/* ══════════════════════════════════════════════════════════════════════════
   STILL NOT IN THE ENGINE.
   ══════════════════════════════════════════════════════════════════════════ */

/**
 * @unimplemented There is no feasibility endpoint. `app/feasibility.py` has
 * `estimate_vram`, `estimate_training_vram` and `verdict`, and nothing serves
 * them over HTTP.
 *
 * This is why the empty state prints the machine's facts and NO capability
 * sentence: DESIGN_SYSTEM §9.11 — "If the engine cannot produce the sentence,
 * the card shows the facts and no interpretation, which is still a
 * demonstration that we looked." The frontend must not compute it
 * (ARCHITECTURE §4.1, "never computes a VRAM figure").
 */
export function getFeasibility(): Promise<never> {
  throw new NotImplementedError(
    'GET /api/feasibility',
    'docs/ARCHITECTURE.md §4.8 (module exists, route does not)',
  );
}

/* `GET /api/runs` exists but returns the legacy run-tracker shape — no `kind`,
   no `status` from the nine-value set, no `archived_at`. The rail needs the
   docs/ARCHITECTURE.md §5 shape, so nothing here calls it; the rail lists
   PROJECTS and THREADS, which are real, instead of runs, which would be half
   real. That is also why no thread row carries a run-state dot: Graphite page
   17 draws six of them, and every one would be a colour we invented. */

/** What a person turned on for a project: the sub-agent cap and which tool
 *  packs are offered, with what each pack costs on the wire.
 *
 *  The COST is the reason this returns packs rather than the UI listing them:
 *  it is counted by the engine with the same budget that bills a real turn, so
 *  a switch says "4,020 tokens" rather than asking somebody to guess. */
export interface PackSetting {
  name: string;
  tools: number;
  tokens: number;
  /** The core is offered on every turn and cannot be switched off. */
  core: boolean;
  off: boolean;
}

export interface ProjectSettings {
  project_id: number | null;
  subagents_max: number;
  packs_off: string[];
  packs: PackSetting[];
  most_subagents: number;
}

export function readProjectSettings(projectId: number): Promise<ProjectSettings> {
  return getJson(`/api/projects/${projectId}/settings`);
}

export function writeProjectSettings(
  projectId: number,
  change: { subagents_max?: number; packs_off?: string[] },
): Promise<ProjectSettings> {
  return postJson(`/api/projects/${projectId}/settings`, change);
}
