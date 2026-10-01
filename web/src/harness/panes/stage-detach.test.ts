import { afterEach, describe, expect, it, vi } from "vitest"
import { detachStage } from "./stage-detach"

type Host = { __TAURI_INTERNALS__?: { invoke?: (command: string, args?: Record<string, unknown>) => Promise<unknown> } }

afterEach(() => {
  delete (window as unknown as Host).__TAURI_INTERNALS__
  vi.restoreAllMocks()
})

describe("detachStage", () => {
  it("asks the shell for its Stage window by thread id", async () => {
    const invoke = vi.fn(async () => undefined)
    ;(window as unknown as Host).__TAURI_INTERNALS__ = { invoke }
    const opened = vi.spyOn(window, "open").mockImplementation(() => null)
    expect(await detachStage(33)).toBe("shell")
    expect(invoke).toHaveBeenCalledWith("open_stage", { threadId: 33 })
    expect(opened).not.toHaveBeenCalled()
  })

  it("opens the same page at ?stage=<id> outside the shell", async () => {
    const opened = vi.spyOn(window, "open").mockImplementation(() => null)
    expect(await detachStage(7)).toBe("browser")
    const url = new URL(String(opened.mock.calls[0][0]))
    expect(url.searchParams.get("stage")).toBe("7")
    expect(opened.mock.calls[0][1]).toBe("mlh-stage")
  })
})
