import { showToast } from "@/shell/notifications/toast"
import { tauriInvoke } from "../../platform/tauri"
import { harness, HarnessError } from "../engine"
import type { Connection } from "../providers/local"

/**
 * What the harness can do from their command palette, for the open session.
 *
 * The outgoing app spread these across a rail menu, an amber chip under the
 * composer and a banner over it. In OpenCode's format they are commands: one
 * palette, searchable, with the result reported as their toast - the engine's
 * own sentence when it refuses, because that sentence was written for a person.
 */

function report(done: string) {
  return (result: unknown) => {
    showToast({ variant: "success", title: done })
    return result
  }
}

function refuse(error: unknown) {
  showToast({
    variant: "error",
    title: "The engine said no",
    description: error instanceof HarnessError || error instanceof Error ? error.message : String(error),
  })
}

/**
 * What to do after a project changed, so the surfaces listing it re-read -
 * the session mount passes the rail's invalidation (rail/model.ts
 * `invalidateRail`). Without it a duplicate or an archive only showed on the
 * rail's next poll, and a folder change not at all.
 */
export type Changed = () => unknown

function changed(after: Changed | undefined) {
  return (result: unknown) => {
    after?.()
    return result
  }
}

export async function setProjectFolder(projectId: number, after?: Changed) {
  const invoke = tauriInvoke()
  const chosen = invoke
    ? await invoke("pick_path", { kind: "directory" }).catch(() => null)
    : window.prompt("The folder this project works in")
  if (typeof chosen !== "string" || !chosen.trim()) return
  await harness(`/api/projects/${projectId}/root`, { body: { root_path: chosen.trim() } })
    .then(changed(after))
    .then(report(`This project now works in ${chosen.trim()}`))
    .catch(refuse)
}

export const duplicateProject = (projectId: number, after?: Changed) =>
  harness(`/api/projects/${projectId}/duplicate`, { method: "POST" })
    .then(changed(after))
    .then(report("Project duplicated, sharing the same folder"))
    .catch(refuse)

export function archiveProject(projectId: number, after?: Changed) {
  if (!window.confirm("Archive this project? Its chats stay on disk, but the interface cannot bring it back.")) return
  return harness(`/api/projects/${projectId}/archive`, { method: "POST" })
    .then(changed(after))
    .then(report("Project archived"))
    .catch(refuse)
}

/**
 * The route answers 200 either way: `{ok: true, ...}` when it compacted, and
 * `{ok: false, detail: "nothing to compact"}` when there was nothing to do
 * (app/main.py, `compact_thread_ep`). A 200 is not a "compacted".
 */
export const compactConversation = (threadId: number) =>
  harness<{ ok?: unknown; detail?: unknown } | undefined>(`/api/threads/${threadId}/compact`, { method: "POST" })
    .then((answer) => {
      if (answer?.ok === false) {
        const detail = typeof answer.detail === "string" && answer.detail ? answer.detail : "the engine did not say why"
        showToast({ title: "Nothing was compacted", description: `The engine said: ${detail}.` })
        return answer
      }
      return report("Conversation compacted")(answer)
    })
    .catch(refuse)

export async function recheckModel() {
  const active = (await harness<Connection[]>("/api/providers").catch(() => [])).find((row) => row.is_active)
  if (!active) return showToast({ title: "No model is connected", description: "Pick one on a new chat, or in Settings > Connections." })
  return harness<Connection>(`/api/providers/${active.id}/probe`, { method: "POST" })
    .then((row) => showToast({ variant: "success", title: `${row.name}: ${toolCallingLine(row)}` }))
    .catch(refuse)
}

export async function restartEngine() {
  const invoke = tauriInvoke()
  if (!invoke) return showToast({ title: "Only the desktop app can restart its engine" })
  if (!window.confirm("Restart the engine? Anything it is running stops.")) return
  await invoke("restart_engine").catch(refuse)
  window.location.reload()
}

export function toolCallingLine(row: Pick<Connection, "tool_calling">) {
  if (row.tool_calling === "yes") return "can call tools"
  if (row.tool_calling === "no") return "cannot call tools - you can still run them from Controls"
  return "tool calling not checked yet"
}

/**
 * The outgoing composer's banners, as one toast when a session opens: the
 * active model cannot call tools, or nobody has asked it yet. Silent when it
 * can, and when no model is connected (the new-chat card handles that).
 */
export async function warnAboutTheModel() {
  const active = (await harness<Connection[]>("/api/providers").catch(() => [])).find((row) => row.is_active)
  if (!active || active.tool_calling === "yes") return
  showToast({
    title: `${active.name}: ${toolCallingLine(active)}`,
    description:
      active.tool_calling === "no"
        ? "Connect a model that calls tools, or run tools yourself from the Controls panel."
        : "Asking takes a few seconds.",
    actions: active.tool_calling === "no" ? [] : [{ label: "Check now", onClick: () => void recheckModel() }],
  })
}
