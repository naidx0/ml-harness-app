import { createMemo, onCleanup, onMount } from "solid-js"
import { useNavigate } from "@solidjs/router"
import { useQueryClient } from "@tanstack/solid-query"
import { useData as useSessionUIData } from "@opencode/session-ui/context"
import { useComposerState } from "@/composer/persistence"
import { setCursorPosition } from "@/composer/editor/dom"
import { useCommand } from "@/shell/commands/command"
import { showToast } from "@/shell/notifications/toast"
import { requireServerKey, sessionHref } from "@/shell/routes/session"
import { useServerSDK } from "@/runtime/server/client"
import { useData } from "@/runtime/server/current"
import { useSessionLayout } from "@/session/session-layout"
import { useLocal } from "@/providers/models/selection"
import { HarnessSurfaceMarks } from "./marks"
import { unsupportedCommandOverrides } from "./unsupported"
import { rebroadcastHarnessChange } from "./refresh"
import { threadIdOf } from "../panel/panes"
import { draftInto } from "../bridge/compose"
import {
  claimSessionBridge,
  COMPOSE_EVENT,
  onBridge,
  OPEN_PANE_EVENT,
  OPEN_THREAD_EVENT,
  paneRequestIsOurs,
  uiOpenTab,
} from "../bridge/events"
import { resolveThreadSession } from "../bridge/thread-session"
import {
  archiveProject,
  compactConversation,
  duplicateProject,
  recheckModel,
  restartEngine,
  setProjectFolder,
  warnAboutTheModel,
} from "./actions"
import { HARNESS_PANES } from "../panel/panes"
import { useOpenHarnessPane } from "../panel/slots"
import { invalidateRail } from "../rail/model"

/**
 * The harness's foothold inside a session. Draws nothing visible: one hidden
 * marker, from which the chat's mode and working state are written onto its
 * panel for the colour hints (marks.tsx).
 *
 * - One palette command per harness panel, and `/plan` and `/doc` as the
 *   composer slash commands they were in the outgoing app.
 * - Their commands for surfaces the harness does not have, replaced by
 *   disabled, hidden entries (unsupported.ts has each id and why) - the
 *   terminal first among them: the engine answers `pty.*` empty and the
 *   emulator is a stub that throws, so `ctrl+backquote` would open a panel
 *   that can only fail. Registrations made later win on a shared id, and
 *   this one is made after theirs.
 * - The pane the engine asks for (`harness.ui.open`), for THIS session only.
 * - The project and model actions the outgoing rail and composer carried,
 *   as palette commands (see actions.ts), and its model banner as a toast.
 */
export function HarnessSessionMount() {
  const command = useCommand()
  const open = useOpenHarnessPane()
  const sdk = useServerSDK()
  const { params } = useSessionLayout()
  const data = useData()
  const harnessIds = createMemo(() => {
    const info = params.id ? data.session.get(params.id) : undefined
    const meta = (info as { metadata?: { harness?: { projectID?: unknown } } } | undefined)?.metadata?.harness
    const project = Number(meta?.projectID)
    return { thread: threadIdOf(info), project: Number.isFinite(project) && project > 0 ? project : undefined }
  })
  onMount(() => void warnAboutTheModel())
  // A project command changes what the rail lists; it re-reads at once.
  const queryClient = useQueryClient()
  const railChanged = () => invalidateRail(queryClient)

  command.register("harness.session", () => [
    ...HARNESS_PANES.map((pane) => ({
      id: `harness.open.${pane.id}`,
      title: `Open ${pane.title}`,
      description: pane.hint,
      category: "Harness",
      onSelect: () => open(pane.id),
    })),
    {
      id: "harness.slash.plan",
      title: "Open the plan",
      description: "Open the Plan pane: the goal, the todo and the steps",
      category: "Harness",
      slash: "plan",
      hidden: true,
      onSelect: () => open("plan"),
    },
    {
      id: "harness.slash.doc",
      title: "Open the plan document",
      description: "Open the Plan pane on the written plan",
      category: "Harness",
      slash: "doc",
      hidden: true,
      onSelect: () => open("plan"),
    },
    {
      id: "harness.project.folder",
      title: "Set this project's folder",
      category: "Harness",
      disabled: !harnessIds().project,
      onSelect: () => void setProjectFolder(harnessIds().project!, railChanged),
    },
    {
      id: "harness.project.duplicate",
      title: "Duplicate this project",
      category: "Harness",
      disabled: !harnessIds().project,
      onSelect: () => void duplicateProject(harnessIds().project!, railChanged),
    },
    {
      id: "harness.project.archive",
      title: "Archive this project",
      category: "Harness",
      disabled: !harnessIds().project,
      onSelect: () => void archiveProject(harnessIds().project!, railChanged),
    },
    {
      id: "harness.thread.compact",
      title: "Compact this conversation",
      category: "Harness",
      disabled: !harnessIds().thread,
      onSelect: () => void compactConversation(harnessIds().thread!),
    },
    { id: "harness.model.recheck", title: "Check what the model can do", category: "Harness", onSelect: () => void recheckModel() },
    { id: "harness.engine.restart", title: "Restart the engine", category: "Harness", onSelect: () => void restartEngine() },
    // Their commands for surfaces the harness does not have (terminal, MCP,
    // revert, fork, shell, browser, worktrees, SSH, pairing): each id and the
    // reason it is off are listed in unsupported.ts.
    ...unsupportedCommandOverrides(),
  ])

  // Their event stream passes unknown event types through untouched, which
  // is what lets the engine's own events ride it (docs/PHASE-5-SURFACES.md).
  // It carries EVERY thread's events to every window, so an instruction is
  // acted on only when it names this session or its thread (`uiOpenTab`).
  //
  // NO `harness.stage.started` LISTENER. This mount used to open the Stage on
  // it, but nothing in the engine emits that kind. An emitter belongs where a
  // run starts spending (an `events.append("stage.started", ...)` beside the
  // run's start in app/), and it MUST pass `thread_id=` so the facade's
  // pass-through (app/facade/translate.py `_pass_through`) puts `threadID` on
  // it; a listener here would then filter on that as `uiOpenTab` does.
  //
  // The same stream tells this session's panes when to re-read: an engine
  // event for this chat is said again on `window` as `harness:changed`
  // (refresh.ts has which events and why), and a pane re-reads on it rather
  // than polling while nothing happens.
  onCleanup(
    sdk.event.listen((event) => {
      const here = { sessionID: params.id, threadID: harnessIds().thread }
      rebroadcastHarnessChange(event, here)
      const tab = uiOpenTab(event, here)
      if (tab && HARNESS_PANES.some((pane) => pane.id === tab)) open(tab)
    }),
  )

  // Result cards in the transcript and the panes cannot reach the session, so
  // they ask with a window event and the session answers it here
  // (bridge/events.ts). A pop-out has no mount, so its requests go unanswered
  // and the pane falls back on its own.
  onCleanup(claimSessionBridge())
  onCleanup(
    onBridge(OPEN_PANE_EVENT, (detail) => {
      if (!HARNESS_PANES.some((spec) => spec.id === detail.pane)) return false
      // A card from another thread would open this chat's pane on this
      // chat's data. Declined, so the card pops its own thread out instead.
      if (!paneRequestIsOurs(detail, harnessIds().thread)) return false
      open(detail.pane)
    }),
  )

  // The plan's "Ask": a draft in THIS tab's composer, through their persisted
  // composer state - the store the editor renders from and the tab remembers
  // - so it survives a tab switch like anything typed. Then focus, with the
  // cursor at the end. Their `input.focus` command is what ctrl+L runs; it
  // focuses the editor but leaves the caret where the browser puts it.
  const composer = useComposerState()
  const compose = (text: string) => {
    const target = composer.capture()
    const next = draftInto(target.current(), text)
    target.set(next.prompt, next.cursor)
    requestAnimationFrame(() => {
      command.trigger("input.focus")
      const editor = document.activeElement
      if (editor instanceof HTMLElement && editor.isContentEditable) setCursorPosition(editor, next.cursor)
    })
  }
  onCleanup(
    onBridge(COMPOSE_EVENT, ({ text }) => {
      // A draft written before the tab's saved prompt has loaded would be
      // overwritten by it, so it waits for the load rather than racing it.
      if (composer.ready()) return compose(text)
      void Promise.resolve(composer.ready.promise).then(() => compose(text))
    }),
  )

  // The Agents pane's "Open conversation": a sub-agent's child thread, opened
  // the way their timeline opens a child session (their DataProvider's
  // `navigateToSession`: remember the route on this tab, sync, navigate), so
  // Escape and the header's parent link lead back here.
  const ui = useSessionUIData()
  const navigate = useNavigate()
  const openThread = async (threadId: number) => {
    const found = await resolveThreadSession(threadId, {
      known: () => data.session.list(),
      children: params.id
        ? () => sdk.api.session.list({ parentID: params.id }).then((page) => page.data)
        : undefined,
      get: (sessionID) => sdk.api.session.get({ sessionID }),
    })
    if (!found) {
      showToast({
        title: "Could not open that chat",
        description: `The engine lists no chat for thread ${threadId}.`,
      })
      return
    }
    if (ui.navigateToSession) return ui.navigateToSession(found.id)
    navigate(sessionHref(requireServerKey(params.serverKey), found.id))
  }
  onCleanup(onBridge(OPEN_THREAD_EVENT, ({ threadId }) => void openThread(threadId)))

  // COLOUR HINTS (marks.tsx): the chat's mode and whether it is working, on
  // the panel that holds this session's header, transcript and composer. The
  // mount lives in their review-toggle slot, whose parent is that panel.
  const local = useLocal()
  return (
    <HarnessSurfaceMarks
      find={(marker) => marker.closest<HTMLElement>('[data-slot="session-review-toggle"]')?.parentElement}
      mode={() => local.agent.current()?.name}
      working={() => !!params.id && data.session.status(params.id) === "running"}
    />
  )
}
