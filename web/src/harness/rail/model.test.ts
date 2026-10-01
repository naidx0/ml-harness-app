import { describe, expect, it } from "vitest"
import {
  buildRail,
  defaultProject,
  filterSessions,
  groupByProject,
  limitRows,
  mergeProjects,
  mergeSessions,
  nestRows,
  otherSessionTabIndexes,
  railPrefsKey,
  readPrefs,
  readScopedPrefs,
  toggle,
  writePrefs,
  RAIL_PREFS_KEY,
  type RailSessionLike,
} from "./model"

// Every specimen is built here; nothing is borrowed from another lane's data.
let clock = 1_000
function session(id: string, over: Partial<RailSessionLike> & { updated?: number } = {}): RailSessionLike {
  clock += 10
  const { updated, ...rest } = over
  return {
    id,
    title: id,
    projectID: "prj_a",
    location: { directory: "/work/a" },
    time: { created: clock, updated: updated ?? clock },
    ...rest,
  }
}

const ids = (rows: { session: { id: string } }[]) => rows.map((row) => row.session.id)

describe("mergeSessions", () => {
  it("prefers the known copy, drops archived, newest first", () => {
    const fetched = [session("s1", { title: "old", updated: 5 }), session("s2", { updated: 9 })]
    const known = [{ ...fetched[0]!, title: "renamed", time: { created: 1, updated: 20 } }]
    const archived = session("s3", { time: { created: 1, updated: 30, archived: 31 } })
    const out = mergeSessions([...fetched, archived], known)
    expect(out.map((s) => s.id)).toEqual(["s1", "s2"])
    expect(out[0]!.title).toBe("renamed")
  })
})

describe("mergeProjects", () => {
  it("keeps the server list and appends only unmatched local folders", () => {
    const server = [{ id: "prj_a", directory: "/work/a", name: "A" }]
    const local = [
      { directory: "/work/a/" }, // same path, trailing slash
      { id: "prj_a", directory: "/elsewhere" }, // same id
      // A folder the facade resolved to a project the server's list has not
      // caught up with yet (2026-09-23: an id is what "resolved" means).
      { id: "prj_b", directory: "/work/b" },
    ]
    expect(mergeProjects(server, local).map((p) => p.directory)).toEqual(["/work/a", "/work/b"])
  })

  it("once the server has answered, drops a saved folder no project owns (the owner, 2026-09-23)", () => {
    // Their client's saved folders: the Default's own path, and an old legacy
    // workspace (`.../workspaces/project-1`) no server project claims.
    const local = [{ directory: "/docs/ML Harness/Default" }, { directory: "/data/workspaces/project-1" }]
    const server = [{ id: "prj_1", directory: "/docs/ML Harness/Default", name: "Default" }]
    expect(mergeProjects(server, local).map((p) => p.directory)).toEqual(["/docs/ML Harness/Default"])
    // Before the server's list answers, their folders are all there is.
    expect(mergeProjects([], local).map((p) => p.directory)).toEqual(local.map((p) => p.directory))
  })
})

describe("groupByProject", () => {
  it("places by projectID, then by directory, then makes a folder for the rest", () => {
    const projects = [
      { id: "prj_a", directory: "/work/a", name: "A" },
      { directory: "/work/b", name: "B" },
      { id: "prj_empty", directory: "/work/empty" },
    ]
    const sessions = [
      session("byId", { projectID: "prj_a", location: { directory: "/somewhere/else" } }),
      session("byPath", { projectID: "prj_unknown_b", location: { directory: "/work/b" } }),
      session("orphan1", { projectID: "prj_z", location: { directory: "/work/z" } }),
      session("orphan2", { projectID: "prj_z", location: { directory: "/work/z" } }),
    ]
    const groups = groupByProject(sessions, projects)
    expect(groups.map((g) => [g.key, g.sessions.map((s) => s.id)])).toEqual([
      ["project:prj_a", ["byId"]],
      ["dir:/work/b", ["byPath"]],
      ["project:prj_empty", []],
      ["project:prj_z", ["orphan1", "orphan2"]],
    ])
  })

  it("puts a session no project claims under the Default, never a folder named for its path (the owner, 2026-09-23)", () => {
    const projects = [
      { id: "prj_17", directory: "/docs/ML Harness/Support bot", name: "Support bot" },
      { id: "prj_1", directory: "/docs/ML Harness/Default", name: "Default" },
    ]
    const sessions = [
      // A legacy workspace directory, and no project id to place it by.
      session("legacy", { projectID: "", location: { directory: "/data/workspaces/project-1" } }),
      // A project id neither list names.
      session("stale", { projectID: "prj_99", location: { directory: "/data/workspaces/project-99" } }),
      session("placed", { projectID: "prj_17", location: { directory: "/docs/ML Harness/Support bot" } }),
    ]
    const groups = groupByProject(sessions, projects)
    expect(groups.map((g) => [g.key, g.sessions.map((s) => s.id)])).toEqual([
      ["project:prj_17", ["placed"]],
      ["project:prj_1", ["legacy", "stale"]],
    ])
  })
})

describe("nestRows", () => {
  it("nests sub-agents under their parent, oldest child first, recursively", () => {
    const parent = session("parent", { updated: 100 })
    const childA = session("childA", { parentID: "parent", updated: 500 })
    const childB = session("childB", { parentID: "parent", updated: 400 })
    const grandchild = session("grand", { parentID: "childA" })
    const other = session("other", { updated: 50 })
    const rows = nestRows([other, childB, grandchild, parent, childA], new Set())
    expect(rows.map((r) => [r.session.id, r.depth])).toEqual([
      ["parent", 0],
      ["childA", 1],
      ["grand", 2],
      ["childB", 1],
      ["other", 0],
    ])
  })

  it("shows a child whose parent is absent at the top level", () => {
    const rows = nestRows([session("lost", { parentID: "gone" })], new Set())
    expect(rows.map((r) => [r.session.id, r.depth])).toEqual([["lost", 0]])
  })

  it("loses no member of a parent cycle", () => {
    const a = session("a", { parentID: "b" })
    const b = session("b", { parentID: "a" })
    expect(ids(nestRows([a, b], new Set())).sort()).toEqual(["a", "b"])
  })

  it("sorts pinned threads first inside the folder, keeping recency within each half", () => {
    const rows = nestRows(
      [session("new", { updated: 30 }), session("mid", { updated: 20 }), session("old", { updated: 10 })],
      new Set(["old", "mid"]),
    )
    expect(ids(rows)).toEqual(["mid", "old", "new"])
    expect(rows.map((r) => r.pinned)).toEqual([true, true, false])
  })
})

describe("filterSessions", () => {
  it("matches titles case-insensitively and keeps the ancestors of a match", () => {
    const parent = session("p", { title: "Train the model" })
    const child = session("c", { title: "Profile DATA loader", parentID: "p" })
    const other = session("o", { title: "unrelated" })
    expect(ids(filterSessions([parent, child, other], "data").map((s) => ({ session: s })))).toEqual(["p", "c"])
    expect(filterSessions([parent, child, other], "  ")).toHaveLength(3)
  })
})

describe("limitRows", () => {
  it("cuts after N top-level threads, keeping children and pins", () => {
    const rows = nestRows(
      [
        session("pin", { updated: 1 }),
        session("r1", { updated: 50 }),
        session("r1c", { parentID: "r1" }),
        session("r2", { updated: 40 }),
        session("r3", { updated: 30 }),
      ],
      new Set(["pin"]),
    )
    const out = limitRows(rows, 1)
    expect(ids(out.rows)).toEqual(["pin", "r1", "r1c"])
    expect(out.hidden).toBe(2)
  })
})

describe("buildRail", () => {
  const projects = [
    { id: "prj_a", directory: "/work/a", name: "Alpha" },
    { id: "prj_b", directory: "/work/b", name: "" },
  ]
  const sessions = [
    session("a1", { title: "tune lr" }),
    session("a2", { title: "eval run" }),
    session("b1", { title: "notes", projectID: "prj_b", location: { directory: "/work/b" } }),
  ]

  it("names a folder from its directory when the project has no name", () => {
    const rail = buildRail({ sessions, projects, pinned: new Set(), collapsed: new Set(["project:prj_a"]) })
    expect(rail.map((f) => [f.name, f.collapsed, ids(f.rows)])).toEqual([
      ["Alpha", true, ["a2", "a1"]],
      ["b", false, ["b1"]],
    ])
  })

  it("while filtering: hides empty folders, opens collapsed ones, cuts nothing", () => {
    const rail = buildRail({
      sessions,
      projects,
      pinned: new Set(),
      collapsed: new Set(["project:prj_a"]),
      filter: "EVAL",
      limit: 0,
    })
    expect(rail.map((f) => [f.key, f.collapsed, ids(f.rows), f.hidden])).toEqual([["project:prj_a", false, ["a2"], 0]])
  })

  it("applies the limit unless the folder was expanded", () => {
    const limited = buildRail({ sessions, projects, pinned: new Set(), collapsed: new Set(), limit: 1 })
    expect(limited[0]!.hidden).toBe(1)
    const open = buildRail({
      sessions,
      projects,
      pinned: new Set(),
      collapsed: new Set(),
      limit: 1,
      expanded: new Set(["project:prj_a"]),
    })
    expect(open[0]!.hidden).toBe(0)
    expect(open[0]!.rows).toHaveLength(2)
  })
})

describe("the Default project", () => {
  // The engine's Default is its lowest-id live project; here it arrives LAST
  // and renamed, which is the case a name match or the list order would miss.
  const projects = [
    { id: "prj_7", directory: "/work/seven", name: "Seven" },
    { id: "prj_12", directory: "/work/twelve", name: "Twelve" },
    { id: "prj_3", directory: "/work/home", name: "My workspace" },
  ]
  const sessions = [
    session("s7", { projectID: "prj_7", location: { directory: "/work/seven" }, updated: 900 }),
    session("s12", { projectID: "prj_12", location: { directory: "/work/twelve" }, updated: 800 }),
    session("s3", { projectID: "prj_3", location: { directory: "/work/home" }, updated: 1 }),
  ]

  it("is the lowest harness project id, whatever it is called", () => {
    expect(defaultProject(projects)?.id).toBe("prj_3")
    // Without harness ids, a folder named Default is the fallback.
    expect(defaultProject([{ directory: "/x", name: "x" }, { directory: "/d", name: " default " }])?.directory).toBe("/d")
    expect(defaultProject([{ directory: "/x", name: "x" }])).toBeUndefined()
  })

  it("before the server's list answers, is the client's folder whose path ends in Default", () => {
    // Their client's own folders: a path, no id, no name (as stored by their
    // server registry), in the order they were opened.
    const local = [{ directory: "D:/ML Harness/Support bot" }, { directory: "D:/ML Harness/Default" }]
    const early = [
      session("x1", { projectID: "", location: { directory: local[0]!.directory } }),
      session("x2", { projectID: "", location: { directory: local[1]!.directory } }),
    ]
    const rail = buildRail({ sessions: early, projects: local, pinned: new Set(), collapsed: new Set() })
    expect(rail.map((folder) => folder.name)).toEqual(["Default", "Support bot"])
  })

  it("is always the first folder, and the others keep the list's order", () => {
    const rail = buildRail({ sessions, projects, pinned: new Set(), collapsed: new Set() })
    expect(rail.map((folder) => folder.key)).toEqual(["project:prj_3", "project:prj_7", "project:prj_12"])
    // Collapsing or pinning inside other folders does not move it.
    const again = buildRail({ sessions, projects, pinned: new Set(["s7"]), collapsed: new Set(["project:prj_3"]) })
    expect(again[0]!.key).toBe("project:prj_3")
  })

  it("draws no invented project-N folder beside the real projects (the owner's screenshot 3, 2026-09-23)", () => {
    // The whole rail as it was built on his machine: the server's projects,
    // their client's saved folders (one a legacy workspace), and a session
    // whose directory is that workspace.
    const server = [
      { id: "prj_1", directory: "/docs/ML Harness/Default", name: "Default" },
      { id: "prj_17", directory: "/docs/ML Harness/Support bot", name: "Support bot" },
    ]
    const local = [{ directory: "/docs/ML Harness/Default" }, { directory: "/data/workspaces/project-1" }]
    const sessions = [
      session("mine", { projectID: "prj_17", location: { directory: "/docs/ML Harness/Support bot" } }),
      session("old", { projectID: "", location: { directory: "/data/workspaces/project-1" } }),
    ]
    const rail = buildRail({ sessions, projects: mergeProjects(server, local), pinned: new Set(), collapsed: new Set() })
    expect(rail.map((folder) => [folder.name, ids(folder.rows)])).toEqual([
      ["Default", ["old"]],
      ["Support bot", ["mine"]],
    ])
  })

  it("an order that already starts with it is left untouched", () => {
    const ordered = [projects[2]!, projects[0]!, projects[1]!]
    const rail = buildRail({ sessions, projects: ordered, pinned: new Set(), collapsed: new Set() })
    expect(rail.map((folder) => folder.key)).toEqual(["project:prj_3", "project:prj_7", "project:prj_12"])
  })
})

describe("otherSessionTabIndexes", () => {
  it("names this server's other session tabs, highest first, sparing drafts and the kept chat", () => {
    const tabs = [
      { type: "session", server: "here", sessionId: "ses_a" },
      { type: "draft", server: "here", draftID: "d1" },
      { type: "session", server: "here", sessionId: "ses_keep" },
      { type: "session", server: "elsewhere", sessionId: "ses_b" },
      // A parent's tab showing the kept chat's sub-agent is the kept tab too.
      { type: "session", server: "here", sessionId: "ses_parent", routeSessionId: "ses_child" },
      { type: "session", server: "here", sessionId: "ses_c" },
    ]
    expect(otherSessionTabIndexes(tabs, "here", "ses_keep")).toEqual([5, 4, 0])
    expect(otherSessionTabIndexes(tabs, "here", "ses_child")).toEqual([5, 2, 0])
    expect(otherSessionTabIndexes([], "here", "ses_keep")).toEqual([])
  })
})

describe("prefs", () => {
  it("round-trips, and survives garbage and a throwing storage", () => {
    const store = new Map<string, string>()
    const storage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) }
    writePrefs(storage, { pinned: ["s1"], collapsed: ["project:prj_a"] })
    expect(readPrefs(storage)).toEqual({ pinned: ["s1"], collapsed: ["project:prj_a"] })
    store.set(RAIL_PREFS_KEY, "{not json")
    expect(readPrefs(storage)).toEqual({ pinned: [], collapsed: [] })
    store.set(RAIL_PREFS_KEY, JSON.stringify({ pinned: [1, "ok"], collapsed: "no" }))
    expect(readPrefs(storage)).toEqual({ pinned: ["ok"], collapsed: [] })
    const hostile = {
      getItem: () => {
        throw new Error("denied")
      },
      setItem: () => {
        throw new Error("denied")
      },
    }
    expect(readPrefs(hostile)).toEqual({ pinned: [], collapsed: [] })
    expect(() => writePrefs(hostile, { pinned: [], collapsed: [] })).not.toThrow()
  })

  it("are kept per server and per database, so one scope's pins never show on another", () => {
    const store = new Map<string, string>()
    const storage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
    }
    const here = railPrefsKey("sidecar", "db-1")
    const otherServer = railPrefsKey("http://127.0.0.1:3100", "db-1")
    const otherDatabase = railPrefsKey("sidecar", "db-2")
    expect(new Set([here, otherServer, otherDatabase]).size).toBe(3)
    writePrefs(storage, { pinned: ["ses_1"], collapsed: [] }, here)
    expect(readScopedPrefs(storage, here)).toEqual({ pinned: ["ses_1"], collapsed: [] })
    expect(readScopedPrefs(storage, otherServer)).toEqual({ pinned: [], collapsed: [] })
    expect(readScopedPrefs(storage, otherDatabase)).toEqual({ pinned: [], collapsed: [] })
  })

  it("made under the old global key move to the first scope that reads them, once", () => {
    const store = new Map<string, string>([[RAIL_PREFS_KEY, JSON.stringify({ pinned: ["ses_old"], collapsed: [] })]])
    const storage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
    }
    const first = railPrefsKey("sidecar", "db-1")
    expect(readScopedPrefs(storage, first)).toEqual({ pinned: ["ses_old"], collapsed: [] })
    expect(store.has(RAIL_PREFS_KEY)).toBe(false)
    expect(readScopedPrefs(storage, railPrefsKey("sidecar", "db-2"))).toEqual({ pinned: [], collapsed: [] })
    expect(readScopedPrefs(storage, first)).toEqual({ pinned: ["ses_old"], collapsed: [] })
  })

  it("toggle adds and removes", () => {
    expect(toggle(["a"], "b")).toEqual(["a", "b"])
    expect(toggle(["a", "b"], "a")).toEqual(["b"])
  })
})
