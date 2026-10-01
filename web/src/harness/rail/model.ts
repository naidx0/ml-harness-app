import { pathKey } from "@/workspaces/path-key"

/**
 * The session rail's shape, as pure functions over their session and project
 * records (docs/PARITY.md section 2).
 *
 * The outgoing app's rail (frontend/src/components/Rail.tsx) grouped threads
 * under project folders, nested a sub-agent's thread under the thread that
 * sent it, sorted pins above the rest INSIDE their folder, and filtered by
 * title. The same rules, over what OpenCode's own client already holds: a
 * `SessionInfo` carries `projectID`, `parentID` and `location.directory`,
 * which is everything the grouping needs. No harness route is read here.
 */

export type RailSessionLike = {
  id: string
  title?: string
  parentID?: string
  projectID: string
  location: { directory: string }
  time: { created: number; updated?: number; archived?: number }
}

export type RailProjectSource = {
  id?: string
  directory: string
  name?: string
}

export type RailRow<S extends RailSessionLike> = {
  session: S
  /** 0 for a thread a person started; 1+ for a sub-agent under its parent. */
  depth: number
  pinned: boolean
}

export type RailFolder<S extends RailSessionLike> = {
  key: string
  id?: string
  directory: string
  name: string
  rows: RailRow<S>[]
  /** Top-level threads left out by the per-folder limit. */
  hidden: number
  /** Every session grouped here, before filter and limit: busy and counts read this. */
  sessions: S[]
  collapsed: boolean
}

const updatedOf = (session: RailSessionLike) => session.time.updated ?? session.time.created

/** Newest first; id breaks ties so the order never flickers between renders. */
export function compareRecent(a: RailSessionLike, b: RailSessionLike) {
  return updatedOf(b) - updatedOf(a) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)
}

/**
 * The fetched index and what the client already knows, as one list.
 *
 * KNOWN WINS. Their data store is updated by events and by every rename this
 * window makes, so its copy is never older than the index; the index is what
 * finds sessions this window has never opened. Archived sessions are dropped
 * from both - the rail shows live conversations, as the outgoing one did.
 */
export function mergeSessions<S extends RailSessionLike>(fetched: readonly S[], known: readonly S[]): S[] {
  const byId = new Map<string, S>()
  for (const session of fetched) byId.set(session.id, session)
  for (const session of known) byId.set(session.id, session)
  return [...byId.values()].filter((session) => typeof session.time.archived !== "number").sort(compareRecent)
}

/**
 * The harness's projects and the folders their client has open, as one list.
 *
 * The server's list is the harness's projects (the facade's `/api/project`),
 * so it decides which folders exist and what they are called. A folder their
 * client opened that the server does not list - a directory added before its
 * project was made - is kept after them, matched by path, never twice.
 *
 * ONCE THE SERVER HAS ANSWERED, A FOLDER NO PROJECT OWNS IS NOT DRAWN (the
 * owner, 2026-09-23: a "project-1" folder with only "New chat" under it). A
 * folder their client opened carries a project id as soon as the facade has
 * resolved it (`location.get` makes the project); one with no id is a path
 * no server project ever claimed - here an old `workspaces/project-N` folder
 * (app/facade/sessions.py `legacy_workspace`) still in their saved list. Before
 * the server's list arrives, their folders are all the rail has, so all stay.
 */
export function mergeProjects(server: readonly RailProjectSource[], local: readonly RailProjectSource[]) {
  const seen = new Set(server.map((project) => pathKey(project.directory)))
  const ids = new Set(server.flatMap((project) => (project.id ? [project.id] : [])))
  const answered = server.length > 0
  const out = [...server]
  for (const project of local) {
    const key = pathKey(project.directory)
    if (seen.has(key) || (project.id && ids.has(project.id))) continue
    if (answered && !project.id) continue
    seen.add(key)
    out.push(project)
  }
  return out
}

const HARNESS_PROJECT_ID = /^prj_(\d+)$/

/**
 * The Default project: the one every conversation lands in when nothing else
 * is chosen. The engine's own definition, not a name match - `db.default_project`
 * is "the lowest-id live project", and the facade spells ids `prj_<n>`
 * (app/facade/sessions.py `project_id`), so a Default that was renamed is
 * still found. A folder called "Default" is the fallback for a list with no
 * harness ids in it: before the server's list has answered, the rail has only
 * their client's own folders, which carry a path and nothing else, so the
 * name it would draw (the folder's basename) is what is matched.
 */
export function defaultProject(projects: readonly RailProjectSource[]): RailProjectSource | undefined {
  let best: RailProjectSource | undefined
  let lowest = Number.POSITIVE_INFINITY
  for (const project of projects) {
    const match = project.id ? HARNESS_PROJECT_ID.exec(project.id) : null
    const n = match ? Number(match[1]) : Number.NaN
    if (Number.isFinite(n) && n < lowest) {
      lowest = n
      best = project
    }
  }
  return best ?? projects.find((project) => folderName(project).toLocaleLowerCase() === "default")
}

/** The name a folder is drawn with: the project's, or its directory's basename. */
export function folderName(project: RailProjectSource) {
  return project.name?.trim() || basename(project.directory)
}

export function folderKey(project: RailProjectSource) {
  return project.id ? `project:${project.id}` : `dir:${pathKey(project.directory)}`
}

export function basename(directory: string) {
  const parts = pathKey(directory).split("/").filter(Boolean)
  return parts[parts.length - 1] ?? directory
}

/**
 * Sessions grouped under the project that owns them, folders in project order.
 *
 * A session is placed by its `projectID` first and its directory second - the
 * same two keys their home list uses (home/sessions/records.ts). One whose
 * project neither list names goes under the Default project - where the
 * engine files a thread whose project it cannot find (app/facade/sessions.py
 * `session_info`) - and never into a folder invented from its directory's
 * basename (the owner, 2026-09-23: "project-1" beside the real projects).
 * Only when there is no Default to fall back to - no project known at all -
 * does it get a folder named for its directory: a thread the rail cannot
 * place is a conversation a person cannot reach.
 */
export function groupByProject<S extends RailSessionLike>(sessions: readonly S[], projects: readonly RailProjectSource[]) {
  const groups = new Map<string, { project: RailProjectSource; sessions: S[] }>()
  const byId = new Map<string, string>()
  const byPath = new Map<string, string>()
  for (const project of projects) {
    const key = folderKey(project)
    if (groups.has(key)) continue
    groups.set(key, { project, sessions: [] })
    if (project.id) byId.set(project.id, key)
    byPath.set(pathKey(project.directory), key)
  }
  const fallback = defaultProject(projects)
  const fallbackKey = fallback ? folderKey(fallback) : undefined
  for (const session of sessions) {
    const path = pathKey(session.location.directory)
    let key = byId.get(session.projectID) ?? byPath.get(path) ?? fallbackKey
    if (!key) {
      const project = { id: session.projectID || undefined, directory: session.location.directory }
      key = folderKey(project)
      if (!groups.has(key)) {
        groups.set(key, { project, sessions: [] })
        if (project.id) byId.set(project.id, key)
        byPath.set(path, key)
      }
    }
    groups.get(key)!.sessions.push(session)
  }
  return [...groups.entries()].map(([key, group]) => ({ key, ...group }))
}

/**
 * A folder's sessions as rows: people's threads newest first with pins above,
 * each followed by the sub-agents it sent, oldest first and indented.
 *
 * OLDEST FIRST UNDER A PARENT: the phases were handed out in order, and
 * reading them newest first tells the story backwards (Rail.tsx `nested`).
 * A child whose parent is not in this list - filtered away, archived, or in
 * another project - is shown at the top level rather than hidden.
 */
export function nestRows<S extends RailSessionLike>(sessions: readonly S[], pinned: ReadonlySet<string>): RailRow<S>[] {
  const here = new Map(sessions.map((session) => [session.id, session] as const))
  const children = new Map<string, S[]>()
  const roots: S[] = []
  for (const session of sessions) {
    const parent = session.parentID
    if (parent && parent !== session.id && here.has(parent)) {
      const kin = children.get(parent) ?? []
      kin.push(session)
      children.set(parent, kin)
    } else roots.push(session)
  }
  const ordered = [...roots].sort(compareRecent)
  const top = [...ordered.filter((s) => pinned.has(s.id)), ...ordered.filter((s) => !pinned.has(s.id))]
  const out: RailRow<S>[] = []
  const placed = new Set<string>()
  const visit = (session: S, depth: number) => {
    if (placed.has(session.id)) return
    placed.add(session.id)
    out.push({ session, depth, pinned: depth === 0 && pinned.has(session.id) })
    const kin = (children.get(session.id) ?? []).slice().sort((a, b) => a.time.created - b.time.created)
    for (const child of kin) visit(child, depth + 1)
  }
  for (const session of top) visit(session, 0)
  // A parent cycle has no root to hang from; show its members rather than lose them.
  for (const session of [...sessions].sort(compareRecent)) visit(session, 0)
  return out
}

/**
 * Sessions whose title contains `needle`, case-insensitively, and the
 * ancestors that sent them: a matching sub-agent keeps the thread it belongs
 * to above it, so the match reads in place rather than as an orphan.
 */
export function filterSessions<S extends RailSessionLike>(
  sessions: readonly S[],
  needle: string,
  titleOf: (session: S) => string = defaultTitle,
) {
  const query = needle.trim().toLocaleLowerCase()
  if (!query) return [...sessions]
  const byId = new Map(sessions.map((session) => [session.id, session] as const))
  const keep = new Set<string>()
  for (const session of sessions) {
    if (!titleOf(session).toLocaleLowerCase().includes(query)) continue
    let cursor: S | undefined = session
    while (cursor && !keep.has(cursor.id)) {
      keep.add(cursor.id)
      cursor = cursor.parentID ? byId.get(cursor.parentID) : undefined
    }
  }
  return sessions.filter((session) => keep.has(session.id))
}

function defaultTitle(session: RailSessionLike) {
  return session.title ?? ""
}

/**
 * Cut a folder's rows after `limit` top-level threads, keeping each kept
 * thread's sub-agents with it. Pinned threads are never cut.
 */
export function limitRows<S extends RailSessionLike>(rows: readonly RailRow<S>[], limit: number) {
  let roots = 0
  let hidden = 0
  const out: RailRow<S>[] = []
  let keeping = true
  for (const row of rows) {
    if (row.depth === 0) {
      keeping = row.pinned || roots < limit
      if (keeping) roots += row.pinned ? 0 : 1
      else hidden += 1
    }
    if (keeping) out.push(row)
  }
  return { rows: out, hidden }
}

export type BuildRailInput<S extends RailSessionLike> = {
  sessions: readonly S[]
  projects: readonly RailProjectSource[]
  pinned: ReadonlySet<string>
  collapsed: ReadonlySet<string>
  /** Folders whose "show more" was pressed. */
  expanded?: ReadonlySet<string>
  filter?: string
  limit?: number
  titleOf?: (session: S) => string
}

export const RAIL_FOLDER_LIMIT = 8

/**
 * The whole rail. While a filter is typed, folders with nothing matching are
 * left out, collapsed folders open, and nothing is cut: a filter is a search,
 * and a search that hides a match behind a chevron has not found it.
 *
 * THE DEFAULT PROJECT IS ALWAYS FIRST (the owner, 2026-09-22): the folder
 * every new conversation lands in is pinned above the rest whatever order the
 * project list arrives in. The others keep the list's order.
 */
export function buildRail<S extends RailSessionLike>(input: BuildRailInput<S>): RailFolder<S>[] {
  const folders = buildFolders(input)
  const first = defaultProject(input.projects)
  if (!first) return folders
  const key = folderKey(first)
  const at = folders.findIndex((folder) => folder.key === key)
  if (at <= 0) return folders
  return [folders[at]!, ...folders.slice(0, at), ...folders.slice(at + 1)]
}

function buildFolders<S extends RailSessionLike>(input: BuildRailInput<S>): RailFolder<S>[] {
  const filtering = !!input.filter?.trim()
  const limit = input.limit ?? RAIL_FOLDER_LIMIT
  const folders: RailFolder<S>[] = []
  for (const group of groupByProject(input.sessions, input.projects)) {
    const matched = filterSessions(group.sessions, input.filter ?? "", input.titleOf)
    if (filtering && matched.length === 0) continue
    const nested = nestRows(matched, input.pinned)
    const cut = filtering || input.expanded?.has(group.key) ? { rows: nested, hidden: 0 } : limitRows(nested, limit)
    folders.push({
      key: group.key,
      id: group.project.id,
      directory: group.project.directory,
      name: folderName(group.project),
      rows: cut.rows,
      hidden: cut.hidden,
      sessions: group.sessions,
      collapsed: !filtering && input.collapsed.has(group.key),
    })
  }
  return folders
}

type TabLike = { type: string; server?: string; sessionId?: string; routeSessionId?: string }

/**
 * "Close other tabs" from the rail (the owner, 2026-09-23: the open mark
 * meant nothing he could act on). Every session tab on this server except the
 * one showing `keep` - matched as their `findSessionTab` matches, by the tab's
 * session or the sub-agent it is showing. Draft tabs are left alone: closing
 * one throws away the unsent message it holds. Highest index first, so each
 * close leaves the indexes still to come where they were.
 */
export function otherSessionTabIndexes(tabs: readonly TabLike[], server: string, keep: string): number[] {
  const out: number[] = []
  tabs.forEach((tab, index) => {
    if (tab.type !== "session" || tab.server !== server) return
    if (tab.sessionId === keep || tab.routeSessionId === keep) return
    out.push(index)
  })
  return out.reverse()
}

/**
 * The rail's two queries, by key. The session index is the rail's own; the
 * project list is THEIR settings' query (`settings/workspaces/queries.ts`,
 * `[sdk.scope, "settings-workspace-project-metadata"]`), shared so the two
 * surfaces read one cache entry.
 */
export const RAIL_SESSIONS_QUERY = "harness-rail-sessions"
export const PROJECT_METADATA_QUERY = "settings-workspace-project-metadata"

export function isRailQuery(queryKey: readonly unknown[]): boolean {
  return queryKey[0] === RAIL_SESSIONS_QUERY || queryKey[1] === PROJECT_METADATA_QUERY
}

type Invalidates = {
  invalidateQueries(filters: { predicate: (query: { queryKey: readonly unknown[] }) => boolean }): Promise<unknown>
}

/**
 * Re-read what the rail draws, after something outside it changed a project
 * or a session (a palette command in session/actions.ts). Every server's
 * entries, because the command does not know which scope the rail is on.
 */
export function invalidateRail(client: Invalidates): Promise<unknown> {
  return client.invalidateQueries({ predicate: (query) => isRailQuery(query.queryKey) })
}

/** Pins and collapsed folders, kept in this browser. */
export type RailPrefs = { pinned: string[]; collapsed: string[] }

/** The one global key pins used to live under, whatever server was open. */
export const RAIL_PREFS_KEY = "mlh.rail.v1"

/**
 * Where one server's pins and folds are kept. Pins are session ids and folds
 * are project keys, and both belong to one engine's DATABASE: under one
 * global key, a second server (or a fresh database on the same address)
 * inherited the first one's pins. So the key names the server
 * (`ServerConnection.key`: "sidecar" in the desktop app, the origin in dev,
 * both stable across restarts) and the database's own instance id from
 * `/health` - not the engine id, which is new on every start and would drop
 * the pins each time.
 */
export function railPrefsKey(serverKey: string, databaseInstance: string | null | undefined): string {
  return `mlh.rail.v2|${serverKey}|${databaseInstance ?? ""}`
}

/**
 * One scope's prefs. The first scope to read, when it has none of its own,
 * takes over the legacy global entry and deletes it, so pins made before this
 * change survive once and never leak into a second scope.
 */
export function readScopedPrefs(
  storage: Pick<Storage, "getItem" | "setItem" | "removeItem"> | undefined,
  key: string,
): RailPrefs {
  try {
    if (storage && storage.getItem(key) === null && storage.getItem(RAIL_PREFS_KEY) !== null) {
      const legacy = readPrefs(storage, RAIL_PREFS_KEY)
      writePrefs(storage, legacy, key)
      storage.removeItem(RAIL_PREFS_KEY)
      return legacy
    }
  } catch {
    // Blocked storage: fall through to the plain read, which also refuses quietly.
  }
  return readPrefs(storage, key)
}

export function readPrefs(storage: Pick<Storage, "getItem"> | undefined, key: string = RAIL_PREFS_KEY): RailPrefs {
  try {
    const raw = storage?.getItem(key)
    const value = raw ? (JSON.parse(raw) as Partial<RailPrefs>) : {}
    const strings = (list: unknown) => (Array.isArray(list) ? list.filter((x): x is string => typeof x === "string") : [])
    return { pinned: strings(value.pinned), collapsed: strings(value.collapsed) }
  } catch {
    return { pinned: [], collapsed: [] }
  }
}

export function writePrefs(storage: Pick<Storage, "setItem"> | undefined, prefs: RailPrefs, key: string = RAIL_PREFS_KEY) {
  try {
    storage?.setItem(key, JSON.stringify(prefs))
  } catch {
    // Private windows and full quotas refuse; the rail still works for this visit.
  }
}

export function toggle(list: readonly string[], item: string) {
  return list.includes(item) ? list.filter((x) => x !== item) : [...list, item]
}
