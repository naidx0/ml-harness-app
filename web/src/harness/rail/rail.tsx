import type { SessionInfo } from "@opencode/client/promise"
import { useDialog } from "@opencode/ui/context/dialog"
import { Button } from "@opencode/ui/button"
import { Dialog, DialogFooter, DialogHeader, DialogTitleGroup } from "@opencode/ui/dialog"
import { Icon } from "@opencode/ui/icon"
import { IconButton } from "@opencode/ui/icon-button"
import { InlineInput } from "@opencode/ui/inline-input"
import { Menu } from "@opencode/ui/menu"
import { Tooltip } from "@opencode/ui/tooltip"
import { SessionProgressIndicatorV2 } from "@opencode/session-ui/v2/session-progress-indicator-v2"
import { useNavigate } from "@solidjs/router"
import { skipToken, useQuery, useQueryClient } from "@tanstack/solid-query"
import { Key } from "@solid-primitives/keyed"
import { createEffect, createMemo, createResource, createSignal, on, Show, startTransition } from "solid-js"
import { createHomeController } from "@/home/model"
import { shouldOpenSessionInBackground } from "@/home/sessions/open"
import { useLanguage } from "@/runtime/i18n/language"
import { ServerConnection } from "@/runtime/server/registry"
import type { ServerCtx } from "@/runtime/server/runtime"
import { sessionHref } from "@/shell/routes/session"
import { useLayout } from "@/shell/state/layout"
import type { LocalProject } from "@/shell/state/layout"
import { ProjectIcon } from "@/shell/layout/project-icon"
import { errorMessage } from "@/shell/layout/helpers"
import { showToast } from "@/shell/notifications/toast"
import { notifySessionTabsRemoved } from "@/shell/titlebar/session-events"
import { findSessionTab, useTabs } from "@/shell/tabs/tabs"
import { removedSessionIDs } from "@/session/session-domain"
import { sessionLabel } from "@/session/title"
import { pathKey } from "@/workspaces/path-key"
import { harness } from "../engine"
import { threadIdOf } from "../panel/panes"
import {
  buildRail,
  mergeProjects,
  mergeSessions,
  otherSessionTabIndexes,
  PROJECT_METADATA_QUERY,
  RAIL_SESSIONS_QUERY,
  railPrefsKey,
  readScopedPrefs,
  toggle,
  writePrefs,
  type RailFolder,
  type RailPrefs,
  type RailRow,
} from "./model"

/**
 * THE SESSION RAIL, in OpenCode's vertical-tabs sidebar.
 *
 * The owner: "I like the UI layout looking like opencode, but I still want
 * some things like my session side rail." The outgoing rail
 * (frontend/src/components/Rail.tsx, docs/PARITY.md section 2) was projects
 * as folders with their threads, sub-agents nested under the thread that sent
 * them, a working indicator, pins, a title filter, and per-thread rename,
 * archive and delete. This is that rail drawn with their components and
 * tokens. It used to sit above their open-tab list; the owner, 2026-09-22:
 * "this bar where it cuts off and just shows sessions at the bottom - not
 * helpful; it should just be a side rail". So their list is hidden in this
 * sidebar (brand/identity.css, RAIL ONLY), the rail fills the height under
 * their Home and New-session buttons with its own scroll, and a row whose
 * session has a tab is marked open (`data-open`) with "Close tab" in its menu.
 *
 * WHERE IT MOUNTS AND WHY THERE. One declared patch to their titlebar
 * (scripts/vendor_opencode.py, P20-P21) renders <HarnessRail /> inside the
 * Portal their titlebar already mounts into `[data-slot="vertical-tabs-sidebar"]`,
 * between their "New session" button and their tab strip. The alternatives
 * were worse: no slot or context exposes that sidebar to our tree; a Portal
 * we aim at the element ourselves would have to chase it appearing and
 * disappearing whenever the layout toggles, which their own Portal already
 * does (`<Show when={vertical().mount} keyed>`); and a patch in shell.tsx
 * would land in the aside BEFORE their portal's children, above their home
 * and new-session buttons rather than between their buttons and their tabs.
 *
 * WHOSE DATA. Theirs, so it stays in step with their tabs: the per-server
 * context their home screen uses (`createHomeController`), their session
 * index (`sdk.api.session.list`, the same call home makes, without home's
 * root-only filter because sub-agents are the point), their live session
 * store for renames, new sessions and busy state (`data.session.status`, fed
 * by `session.active` on connect and by events after), their project list
 * query (shared cache with their settings), their navigation (`sessionHref`
 * into their router, which their titlebar turns into a tab) and their
 * `newDraft`. The one harness route is archive, because their client has no
 * archive call and the facade does not map one (app/facade/router.py
 * `session_update` takes a title and permissions only).
 */

const PAGE = 5_000
const MAX_PAGES = 20

async function loadAllSessions(ctx: ServerCtx, signal?: AbortSignal) {
  const out: SessionInfo[] = []
  let cursor: string | undefined
  for (let page = 0; page < MAX_PAGES; page++) {
    const response = await ctx.sdk.api.session.list(
      { limit: PAGE, order: "desc", ...(cursor ? { cursor } : {}) },
      { signal },
    )
    out.push(...response.data)
    if (response.data.length < PAGE || !response.cursor.next) break
    cursor = response.cursor.next
  }
  return out
}

type InstanceHealth = { database?: { instance_id?: string | null } } | undefined

const NO_PREFS: RailPrefs = { pinned: [], collapsed: [] }

function storage() {
  try {
    return typeof window === "undefined" ? undefined : window.localStorage
  } catch {
    return undefined
  }
}

const ROW =
  "group/row relative flex h-7 w-full min-w-0 shrink-0 items-center rounded-[6px] text-[13px] leading-4 [font-weight:530]"
const ROW_BUTTON =
  "flex h-full min-w-0 flex-1 items-center gap-1.5 rounded-[6px] pe-7 text-start outline-none focus-visible:bg-v2-overlay-simple-overlay-hover"

export function HarnessRail() {
  const home = createHomeController()
  const tabs = useTabs()
  const layout = useLayout()
  const dialog = useDialog()
  const language = useLanguage()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const conn = home.server.focused
  const ctx = home.server.focusedContext
  const serverKey = () => {
    const current = conn()
    return current ? ServerConnection.key(current) : undefined
  }
  const connected = () => ctx()?.sdk.connection.status() === "connected"

  // PINS AND FOLDS ARE PER SERVER AND PER DATABASE (model.ts `railPrefsKey`).
  // The database's instance id comes off `/health` (a 503 still carries it);
  // until it has answered for THIS server, nothing is read or written, so one
  // scope's pins are never filed under another's key.
  // A request that got no readout at all (the engine is down) stays an error
  // rather than settling on "no database", and is asked again on reconnect.
  const [database, { refetch: rereadDatabase }] = createResource(serverKey, () =>
    harness<InstanceHealth>("/health")
      .then((health) => health?.database?.instance_id ?? "")
      .catch((failure: unknown) => {
        const body = (failure as { body?: unknown } | null)?.body
        if (!body || typeof body !== "object") throw failure
        return (body as NonNullable<InstanceHealth>).database?.instance_id ?? ""
      }),
  )
  createEffect(on(connected, (up) => void (up && database.state === "errored" && rereadDatabase())))
  const prefsKey = createMemo(() => {
    const server = serverKey()
    // `ready` only: while refreshing for a new server the value is the OLD
    // database's, and a key built from it would be the wrong scope.
    if (!server || database.state !== "ready") return undefined
    return railPrefsKey(server, database())
  })
  const [prefs, setPrefsState] = createSignal<RailPrefs>(NO_PREFS)
  const setPrefs = (next: RailPrefs) => {
    setPrefsState(next)
    const key = prefsKey()
    if (key) writePrefs(storage(), next, key)
  }
  createEffect(on(prefsKey, (key) => setPrefsState(key ? readScopedPrefs(storage(), key) : NO_PREFS)))
  const pinned = createMemo(() => new Set(prefs().pinned))
  const collapsed = createMemo(() => new Set(prefs().collapsed))
  const [expanded, setExpanded] = createSignal<ReadonlySet<string>>(new Set())
  const [filter, setFilter] = createSignal("")
  const [gone, setGone] = createSignal<ReadonlySet<string>>(new Set())
  const [menuFor, setMenuFor] = createSignal<string>()
  const [editing, setEditing] = createSignal<{ id: string; draft: string; saving: boolean }>()
  // What this visit did on one server means nothing on another: the rows it
  // expanded, the sessions it just removed, an open menu or rename.
  createEffect(
    on(
      serverKey,
      () => {
        setExpanded(new Set<string>())
        setFilter("")
        setGone(new Set<string>())
        setMenuFor(undefined)
        setEditing(undefined)
      },
      { defer: true },
    ),
  )

  const sessionsKey = () => [RAIL_SESSIONS_QUERY, serverKey() ?? ""] as const
  const index = useQuery(() => {
    const current = ctx()
    return {
      queryKey: sessionsKey(),
      enabled: !!current && connected(),
      queryFn: current ? ({ signal }: { signal: AbortSignal }) => loadAllSessions(current, signal) : skipToken,
      retry: false,
      staleTime: 5_000,
      // Sub-agents are made by the engine, not this window, so their sessions
      // arrive with no event this client acts on; a light re-list finds them.
      refetchInterval: 15_000,
      refetchOnReconnect: true,
      // Opaque, as their home list does, so Query does not deep-unwrap every session.
      select: (sessions: SessionInfo[]) => () => sessions,
    }
  })

  // Their settings' own query for the same list, so the two share one cache entry.
  const projectsQuery = useQuery(() => {
    const current = ctx()
    return {
      queryKey: [current?.sdk.scope, PROJECT_METADATA_QUERY] as const,
      enabled: !!current && connected(),
      queryFn: current ? () => current.sdk.api.project.list() : skipToken,
      staleTime: 30_000,
    }
  })

  const sessions = createMemo(() => {
    const current = ctx()
    if (!current) return []
    const removed = gone()
    const merged = mergeSessions(
      index.data?.() ?? [],
      // `apply` hides sessions their store is deleting right now.
      current.data.session.apply(current.data.session.list()),
    )
    return removed.size ? merged.filter((session) => !removed.has(session.id)) : merged
  })

  const localProjects = createMemo(() => home.project.list())
  const projects = createMemo(() =>
    mergeProjects(
      (projectsQuery.data ?? []).map((project) => ({ id: project.id, directory: project.canonical, name: project.name })),
      localProjects().map((project) => ({ id: project.id, directory: project.worktree, name: project.name })),
    ),
  )

  const folders = createMemo(() =>
    buildRail({
      sessions: sessions(),
      projects: projects(),
      pinned: pinned(),
      collapsed: collapsed(),
      expanded: expanded(),
      filter: filter(),
      titleOf: (session) => sessionLabel(session),
    }),
  )

  const activeSessionID = () => {
    const route = layout.route()
    return route.type === "session" && route.server === serverKey() ? route.sessionId : undefined
  }
  const running = (sessionID: string) => ctx()?.data.session.status(sessionID) === "running"
  // OPEN, which their tab list used to be the only place to show: a session
  // with a tab, or a sub-agent shown inside its parent's tab. That list is
  // hidden in this sidebar (brand/identity.css, RAIL ONLY), so the rail marks
  // these rows (`data-open`) and offers to close them.
  const openTab = (sessionID: string) => {
    const server = serverKey()
    return server ? findSessionTab(tabs.store, server, sessionID) : undefined
  }
  function closeTab(sessionID: string) {
    const tab = openTab(sessionID)
    if (!tab) return
    const index = tabs.store.indexOf(tab)
    if (index !== -1) tabs.closeTab(index)
  }
  // THE OPEN MARK, SAID (the owner, 2026-09-23: "what do these little side
  // dashes mean?"). A tab is not invisible state: it is what the other layout
  // draws across the top, what Ctrl+W closes and Ctrl+Shift+T reopens, and
  // where a chat keeps its review pane and unsent text. So the mark stays,
  // says so on hover, and the menu can clear the tabs he never sees.
  const openHint = () => "Open as a tab in this window."
  const otherTabs = (sessionID: string) => {
    const server = serverKey()
    return server ? otherSessionTabIndexes(tabs.store, server, sessionID) : []
  }
  // Offered on the chat being shown only: closing a tab that is on screen
  // sends their tab list to its neighbour, and here that is never the case.
  function closeOtherTabs(sessionID: string) {
    for (const index of otherTabs(sessionID)) tabs.closeTab(index)
  }

  const iconProject = (folder: RailFolder<SessionInfo>): LocalProject => {
    const key = pathKey(folder.directory)
    const local = localProjects().find((project) => pathKey(project.worktree) === key)
    return { ...local, id: folder.id ?? local?.id, worktree: folder.directory, name: folder.name, expanded: false }
  }

  function refresh() {
    void queryClient.invalidateQueries({ queryKey: sessionsKey(), exact: true })
  }

  function failed(cause: unknown, title = language.t("common.requestFailed")) {
    showToast({ variant: "error", title, description: errorMessage(cause, title) })
  }

  function open(session: SessionInfo, background = false) {
    const current = ctx()
    const server = serverKey()
    if (!current || !server) return
    current.data.session.remember(session)
    if (!background) void current.data.session.message.sync(session.id).catch(() => undefined)
    current.projects.open(session.location.directory)
    if (background) {
      // A root opens its own tab; a sub-agent opens under its parent's, as their titlebar would.
      void startTransition(() => tabs.addSessionTab({ server, sessionId: session.parentID ?? session.id }))
      return
    }
    current.projects.touch(session.location.directory)
    // Their own navigation: the titlebar turns a session route into a tab (or
    // the parent's tab, for a child), exactly as a link inside a chat does.
    navigate(sessionHref(server, session.id))
  }

  function newThread(folder: RailFolder<SessionInfo>) {
    const current = conn()
    if (!current) return
    home.project.openProjectNewSession(current, folder.directory)
  }

  async function rename(session: SessionInfo, title: string) {
    const current = ctx()
    const next = title.trim()
    if (!current || !next || next === sessionLabel(session)) return true
    return current.sdk.api.session
      .update({ sessionID: session.id, title: next })
      .then(() => {
        current.data.session.remember({ ...(current.data.session.get(session.id) ?? session), title: next })
        current.data.session.invalidate(session.id)
        void current.data.session.sync(session.id).catch(() => {})
        refresh()
        return true
      })
      .catch((cause) => {
        failed(cause)
        return false
      })
  }

  async function saveEditor(session: SessionInfo) {
    const state = editing()
    if (!state || state.id !== session.id || state.saving) return
    setEditing({ ...state, saving: true })
    const ok = await rename(session, state.draft)
    setEditing((value) => (value?.id === session.id ? (ok ? undefined : { ...value, saving: false }) : value))
  }

  function togglePin(session: SessionInfo) {
    setPrefs({ ...prefs(), pinned: toggle(prefs().pinned, session.id) })
  }

  function toggleFolder(folder: RailFolder<SessionInfo>) {
    setPrefs({ ...prefs(), collapsed: toggle(prefs().collapsed, folder.key) })
  }

  async function archive(session: SessionInfo) {
    const server = serverKey()
    const current = ctx()
    const thread = threadIdOf(session)
    if (!server || !current) return
    if (thread === undefined) return failed(new Error("This conversation has no harness thread to archive."))
    await harness(`/api/threads/${thread}/archive`, { method: "POST" })
      .then(() => {
        setGone((value) => new Set([...value, session.id]))
        notifySessionTabsRemoved({ server, directory: session.location.directory, sessionIDs: [session.id] })
        current.data.session.invalidate(session.id)
        void current.data.session.sync(session.id).catch(() => {})
        refresh()
      })
      .catch((cause) => failed(cause))
  }

  async function remove(session: SessionInfo) {
    const server = serverKey()
    const current = ctx()
    if (!server || !current) return
    const ids = [...removedSessionIDs(sessions(), session.id)]
    await current.data.session
      .remove(session.id)
      .then(() => {
        setGone((value) => new Set([...value, ...ids]))
        notifySessionTabsRemoved({ server, directory: session.location.directory, sessionIDs: ids })
      })
      .catch((cause) => failed(cause, language.t("session.delete.failed.title")))
      .finally(refresh)
  }

  function confirm(input: { title: string; description: string; action: string; danger?: boolean; run: () => Promise<unknown> }) {
    void dialog.show(() => (
      <Dialog fit>
        <DialogHeader hideClose>
          <DialogTitleGroup title={input.title} description={input.description} />
        </DialogHeader>
        <DialogFooter>
          <Button variant="ghost" onClick={() => dialog.close()}>
            {language.t("common.cancel")}
          </Button>
          <Button
            variant={input.danger ? "danger" : "contrast"}
            onClick={async () => {
              await input.run()
              dialog.close()
            }}
          >
            {input.action}
          </Button>
        </DialogFooter>
      </Dialog>
    ))
  }

  const askArchive = (session: SessionInfo) =>
    confirm({
      title: language.t("common.archive"),
      description: `Archive "${sessionLabel(session)}"? It leaves the rail; nothing is deleted.`,
      action: language.t("common.archive"),
      run: () => archive(session),
    })

  const askDelete = (session: SessionInfo) =>
    confirm({
      title: language.t("session.delete.title"),
      description: language.t("session.delete.confirm", { name: sessionLabel(session) }),
      action: language.t("session.delete.button"),
      danger: true,
      run: () => remove(session),
    })

  function Row(props: { row: RailRow<SessionInfo>; divided: boolean }) {
    const session = () => props.row.session
    const active = () => activeSessionID() === session().id
    const busy = () => running(session().id)
    const opened = () => !!openTab(session().id)
    const edit = () => {
      const state = editing()
      return state?.id === session().id ? state : undefined
    }
    return (
      <div
        data-component="harness-rail-row"
        data-active={active()}
        data-open={opened()}
        data-working={busy()}
        data-depth={props.row.depth}
        class={ROW}
        classList={{
          "bg-v2-background-bg-layer-02 text-v2-text-text-base": active(),
          "text-v2-text-text-faint hover:bg-v2-overlay-simple-overlay-hover hover:text-v2-text-text-base": !active(),
          "mt-1 before:absolute before:-top-0.5 before:inset-x-1.5 before:h-px before:bg-v2-border-border-muted":
            props.divided,
        }}
        onContextMenu={(event) => {
          if (edit()) return
          event.preventDefault()
          setMenuFor(session().id)
        }}
      >
        <Show
          when={!edit()}
          fallback={
            <div class="flex h-full min-w-0 flex-1 items-center gap-1.5 pe-1.5" style={{ "padding-inline-start": `${6 + props.row.depth * 14}px` }}>
              <span class="size-4 shrink-0" aria-hidden="true" />
              <InlineInput
                data-component="harness-rail-rename"
                aria-label={language.t("common.rename")}
                dir="auto"
                ref={(element) =>
                  requestAnimationFrame(() => {
                    element.focus()
                    element.select()
                  })
                }
                value={edit()?.draft ?? ""}
                disabled={edit()?.saving ?? false}
                class="min-w-0 flex-1 text-v2-text-text-base outline-none"
                style={{ "--inline-input-shadow": "none", "text-align": "start" }}
                onInput={(event) => {
                  const draft = event.currentTarget.value
                  setEditing((value) => (value?.id === session().id ? { ...value, draft } : value))
                }}
                onKeyDown={(event) => {
                  event.stopPropagation()
                  if (event.isComposing || event.keyCode === 229) return
                  if (event.key === "Enter") {
                    event.preventDefault()
                    void saveEditor(session())
                  } else if (event.key === "Escape") {
                    event.preventDefault()
                    setEditing(undefined)
                  }
                }}
                onBlur={() => void saveEditor(session())}
              />
            </div>
          }
        >
          <button
            type="button"
            class={ROW_BUTTON}
            style={{ "padding-inline-start": `${6 + props.row.depth * 14}px` }}
            aria-current={active() ? "page" : undefined}
            onMouseDown={(event) => {
              if (event.button === 1) event.preventDefault()
            }}
            onClick={(event) => open(session(), isBackgroundOpen(event))}
            onAuxClick={(event) => {
              if (!isBackgroundOpen(event)) return
              event.preventDefault()
              open(session(), true)
            }}
            onDblClick={() => setEditing({ id: session().id, draft: sessionLabel(session()), saving: false })}
          >
            <span class="flex size-4 shrink-0 items-center justify-center">
              <Show
                when={busy()}
                fallback={
                  <Show when={props.row.depth > 0}>
                    <Icon name="subagent" size="small" class="text-v2-icon-icon-muted" />
                  </Show>
                }
              >
                <SessionProgressIndicatorV2 aria-label="Working" />
              </Show>
            </span>
            <span dir="auto" data-slot="harness-rail-title" class="min-w-0 flex-1 truncate">
              {sessionLabel(session())}
            </span>
          </button>
          {/* The open mark is drawn by brand/identity.css (`data-open`); this is
              its hover target, over the row's leading edge, saying what it is. */}
          <Show when={opened()}>
            <Tooltip placement="right" value={openHint()} class="absolute inset-y-0 start-0 w-1.5">
              <span
                data-slot="harness-rail-open-mark"
                aria-hidden="true"
                class="block size-full cursor-pointer"
                onClick={(event) => open(session(), isBackgroundOpen(event))}
              />
            </Tooltip>
          </Show>
          <div
            class="hover-reveal absolute inset-y-0 end-1 flex items-center group-hover/row:opacity-100 focus-within:opacity-100 data-[menu=true]:opacity-100"
            data-menu={menuFor() === session().id}
          >
            <Menu
              gutter={4}
              modal={false}
              placement="bottom-end"
              open={menuFor() === session().id}
              onOpenChange={(value) => setMenuFor(value ? session().id : undefined)}
            >
              <Menu.Trigger
                as={IconButton}
                variant="ghost-muted"
                size="small"
                icon={<Icon name="outline-dots" />}
                aria-label={language.t("common.moreOptions")}
              />
              <Menu.Portal>
                <Menu.Content>
                  <Menu.Item onSelect={() => setEditing({ id: session().id, draft: sessionLabel(session()), saving: false })}>
                    {language.t("common.rename")}
                  </Menu.Item>
                  <Show when={props.row.depth === 0}>
                    <Menu.Item onSelect={() => togglePin(session())}>{props.row.pinned ? "Unpin" : "Pin to top"}</Menu.Item>
                  </Show>
                  <Show when={opened()}>
                    <Menu.Item onSelect={() => closeTab(session().id)}>{language.t("command.tab.close")}</Menu.Item>
                  </Show>
                  <Show when={active() && otherTabs(session().id).length > 0}>
                    <Menu.Item onSelect={() => closeOtherTabs(session().id)}>Close other tabs</Menu.Item>
                  </Show>
                  <Menu.Separator />
                  <Menu.Item onSelect={() => askArchive(session())}>{language.t("common.archive")}…</Menu.Item>
                  <Menu.Item onSelect={() => askDelete(session())}>{language.t("common.delete")}…</Menu.Item>
                </Menu.Content>
              </Menu.Portal>
            </Menu>
          </div>
        </Show>
      </div>
    )
  }

  function Folder(props: { folder: RailFolder<SessionInfo> }) {
    const folder = () => props.folder
    const anyBusy = createMemo(() => folder().sessions.some((session) => running(session.id)))
    // A hairline between the pinned threads and the rest: pins sort to the top
    // of their folder, and the line is what says they were put there.
    const divideAt = createMemo(() => {
      const rows = folder().rows
      return rows[0]?.pinned ? rows.findIndex((row) => row.depth === 0 && !row.pinned) : -1
    })
    return (
      <div data-component="harness-rail-folder" data-collapsed={folder().collapsed} class="flex w-full min-w-0 flex-col">
        <div class={`${ROW} text-v2-text-text-muted hover:bg-v2-overlay-simple-overlay-hover`}>
          <button
            type="button"
            class={ROW_BUTTON}
            style={{ "padding-inline-start": "6px" }}
            aria-expanded={!folder().collapsed}
            onClick={() => toggleFolder(folder())}
          >
            <ProjectIcon project={iconProject(folder())} class="shrink-0" aria-hidden="true" />
            <span dir="auto" data-slot="harness-rail-folder-name" class="min-w-0 truncate text-v2-text-text-base">
              {folder().name}
            </span>
            <Icon
              name="chevron-down"
              size="small"
              class="shrink-0 text-v2-icon-icon-muted transition-transform duration-[120ms]"
              classList={{ "-rotate-90": folder().collapsed }}
            />
            <Show when={folder().collapsed && anyBusy()}>
              <SessionProgressIndicatorV2 class="ms-auto shrink-0" aria-label="Working" />
            </Show>
          </button>
          <div class="hover-reveal absolute inset-y-0 end-1 flex items-center group-hover/row:opacity-100 focus-within:opacity-100">
            <Tooltip placement="right" value={`${language.t("command.session.new")} in ${folder().name}`}>
              <IconButton
                type="button"
                variant="ghost-muted"
                size="small"
                icon={<Icon name="plus-small" />}
                aria-label={`${language.t("command.session.new")} in ${folder().name}`}
                onClick={() => newThread(folder())}
              />
            </Tooltip>
          </div>
        </div>
        <Show when={!folder().collapsed}>
          <div class="flex w-full min-w-0 flex-col gap-0.5 pt-0.5">
            <Key each={folder().rows} by={(row) => row.session.id}>
              {(row, index) => <Row row={row()} divided={index() === divideAt()} />}
            </Key>
            <Show when={folder().rows.length === 0}>
              <button
                type="button"
                class={`${ROW} ${ROW_BUTTON} text-v2-text-text-faint hover:bg-v2-overlay-simple-overlay-hover hover:text-v2-text-text-base`}
                style={{ "padding-inline-start": "6px" }}
                onClick={() => newThread(folder())}
              >
                <span class="flex size-4 shrink-0 items-center justify-center">
                  <Icon name="edit" size="small" />
                </span>
                <span class="min-w-0 truncate">{language.t("command.session.new")}</span>
              </button>
            </Show>
            <Show when={folder().hidden > 0}>
              <button
                type="button"
                class="flex h-6 w-full shrink-0 items-center rounded-[6px] ps-[28px] text-start text-[12px] text-v2-text-text-faint hover:text-v2-text-text-base"
                onClick={() => setExpanded((value) => new Set([...value, folder().key]))}
              >
                Show {folder().hidden} more
              </button>
            </Show>
          </div>
        </Show>
      </div>
    )
  }

  return (
    <Show when={conn()}>
      <section
        data-component="harness-rail"
        aria-label="Projects and threads"
        class="flex min-h-0 w-full flex-1 flex-col"
      >
        <div class="flex w-full shrink-0 items-center gap-1">
          <label class="flex h-7 min-w-0 flex-1 items-center gap-1.5 rounded-[6px] ps-1.5 pe-1 bg-v2-background-bg-layer-02/60 text-v2-icon-icon-muted transition-[background-color] duration-[120ms] hover:bg-v2-background-bg-layer-02 focus-within:bg-v2-background-bg-layer-02">
            <Icon name="magnifying-glass" size="small" />
            <input
              data-component="harness-rail-filter"
              class="min-w-0 flex-1 border-0 bg-transparent text-[13px] leading-4 text-v2-text-text-base outline-0 placeholder:text-v2-text-text-faint"
              placeholder="Filter threads"
              aria-label="Filter threads by title"
              value={filter()}
              onInput={(event) => setFilter(event.currentTarget.value)}
              onKeyDown={(event) => {
                if (event.key !== "Escape") return
                event.preventDefault()
                setFilter("")
                event.currentTarget.blur()
              }}
            />
            <Show when={filter()}>
              <IconButton
                type="button"
                variant="ghost-muted"
                size="small"
                icon={<Icon name="close-small" />}
                aria-label="Clear filter"
                onClick={() => setFilter("")}
              />
            </Show>
          </label>
        </div>
        <div class="mt-1 flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto overflow-x-hidden">
          {/* KEYED, NOT <For>. Every re-list builds new folder and row objects;
              <For> matches by identity and would rebuild each row's DOM, which
              drops an open menu and blurs - and so saves - a rename in progress. */}
          <Key each={folders()} by={(folder) => folder.key}>
            {(folder) => <Folder folder={folder()} />}
          </Key>
          <Show when={folders().length === 0 && !index.isPending}>
            <div data-slot="harness-rail-empty" class="px-1.5 py-1 text-[12px] text-v2-text-text-faint">
              {filter().trim() ? "No thread matches" : "No threads yet"}
            </div>
          </Show>
        </div>
      </section>
    </Show>
  )
}

// Middle-click, or Cmd+click on macOS (Ctrl+click elsewhere), opens a tab in
// the background - their home list's rule (home/sessions/open.ts).
function isBackgroundOpen(event: MouseEvent) {
  return shouldOpenSessionInBackground({
    button: event.button,
    mac: typeof navigator === "object" && /(Mac|iPod|iPhone|iPad)/.test(navigator.platform),
    meta: event.metaKey,
    ctrl: event.ctrlKey,
    shift: event.shiftKey,
    alt: event.altKey,
  })
}
