import { QueryClient } from "@tanstack/solid-query"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { invalidateRail, PROJECT_METADATA_QUERY, RAIL_SESSIONS_QUERY } from "../rail/model"

const showToast = vi.fn()
vi.mock("@/shell/notifications/toast", () => ({ showToast: (input: unknown) => showToast(input) }))
vi.mock("../../platform/tauri", () => ({ tauriInvoke: () => undefined }))
const harness = vi.fn<(path: string, init?: unknown) => Promise<unknown>>()
vi.mock("../engine", () => ({
  harness: (path: string, init?: unknown) => harness(path, init),
  HarnessError: class HarnessError extends Error {},
}))

const { archiveProject, compactConversation, duplicateProject, setProjectFolder } = await import("./actions")

beforeEach(() => {
  showToast.mockReset()
  harness.mockReset()
})

describe("compacting a conversation", () => {
  it("says the engine's reason when there was nothing to compact, not 'compacted'", async () => {
    harness.mockResolvedValue({ ok: false, detail: "nothing to compact" })
    await compactConversation(4)
    expect(showToast).toHaveBeenCalledTimes(1)
    const toast = showToast.mock.calls[0]![0] as { title: string; description?: string; variant?: string }
    expect(toast.description).toContain("nothing to compact")
    expect(toast.title).not.toMatch(/^Conversation compacted/)
    expect(toast.variant).not.toBe("success")
  })

  it("reports success when the engine compacted", async () => {
    harness.mockResolvedValue({ ok: true, summary: "…" })
    await compactConversation(4)
    expect(showToast).toHaveBeenCalledWith(expect.objectContaining({ variant: "success", title: "Conversation compacted" }))
  })
})

describe("a project command", () => {
  it("re-reads the rail after duplicate, archive and set-folder succeed", async () => {
    harness.mockResolvedValue({})
    const after = vi.fn()
    await duplicateProject(2, after)
    window.confirm = () => true
    await archiveProject(2, after)
    window.prompt = () => "C:/work"
    await setProjectFolder(2, after)
    expect(after).toHaveBeenCalledTimes(3)
  })

  it("does not claim a change the engine refused", async () => {
    harness.mockRejectedValue(new Error("no such project"))
    const after = vi.fn()
    await duplicateProject(2, after)
    expect(after).not.toHaveBeenCalled()
  })
})

describe("the rail's invalidation", () => {
  it("marks the rail's session index and the shared project list stale, and nothing else", async () => {
    const client = new QueryClient()
    const sessions = [RAIL_SESSIONS_QUERY, "server-a"]
    const projects = ["scope-a", PROJECT_METADATA_QUERY]
    const other = ["scope-a", "something-else"]
    for (const key of [sessions, projects, other]) client.setQueryData(key, [])
    await invalidateRail(client)
    expect(client.getQueryState(sessions)?.isInvalidated).toBe(true)
    expect(client.getQueryState(projects)?.isInvalidated).toBe(true)
    expect(client.getQueryState(other)?.isInvalidated).toBe(false)
  })
})
