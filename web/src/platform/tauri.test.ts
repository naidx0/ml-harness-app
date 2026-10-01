import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

/**
 * Tests for OUR half of the platform seam: how their `Platform` maps onto the
 * shell's existing commands.
 *
 * Their `createWebPlatform()` is mocked, deliberately. It opens IndexedDB at
 * construction for the draft store, which a test DOM does not have, and more to
 * the point it is their code and their tests' business. What is ours is the
 * mapping, and the one decision in it worth a test of its own: `restart()` must
 * not restart the engine.
 */

vi.mock("@/runtime/platform/web", () => ({
  createWebPlatform: (version: string) => ({
    platform: {
      platform: "web",
      version,
      openExternal: () => {},
      restart: async () => {},
      notify: async () => {},
      getDefaultServer: async () => null,
      setDefaultServer: () => {},
    },
    currentServerUrl: undefined,
    defaultServerUrl: undefined,
  }),
}))

import { createTauriPlatform, WINDOW_ID } from "./tauri"

type Invoke = (command: string, args?: unknown) => Promise<unknown>

function installShell(invoke: Invoke) {
  ;(window as unknown as { __TAURI_INTERNALS__: { invoke: Invoke } }).__TAURI_INTERNALS__ = { invoke }
}

afterEach(() => {
  delete (window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__
  vi.restoreAllMocks()
})

describe("outside the shell", () => {
  it("is their web platform, unchanged, so a browser tab keeps working", () => {
    const made = createTauriPlatform("0.1.0")
    expect(made.native).toBe(false)
    expect(made.platform.platform).toBe("web")
  })
})

describe("inside the shell", () => {
  let invoke: ReturnType<typeof vi.fn>

  beforeEach(() => {
    invoke = vi.fn(async () => null)
    installShell(invoke as unknown as Invoke)
  })

  it("declares itself a desktop platform with the one window it opens", () => {
    const made = createTauriPlatform("0.1.0")
    expect(made.native).toBe(true)
    expect(made.platform.platform).toBe("desktop")
    if (made.platform.platform !== "desktop") throw new Error("narrowing")
    expect(made.platform.windowID).toBe(WINDOW_ID)
  })

  it("opens the folder picker through the existing pick_path command", async () => {
    invoke.mockResolvedValueOnce("C:/work/project")
    const { platform } = createTauriPlatform("0.1.0")
    if (platform.platform !== "desktop") throw new Error("narrowing")
    await expect(platform.openDirectoryPickerDialog()).resolves.toBe("C:/work/project")
    expect(invoke).toHaveBeenCalledWith("pick_path", { kind: "directory" })
  })

  it("reports a cancelled picker as null, not as an empty path", async () => {
    invoke.mockResolvedValueOnce(null)
    const { platform } = createTauriPlatform("0.1.0")
    if (platform.platform !== "desktop") throw new Error("narrowing")
    await expect(platform.openDirectoryPickerDialog()).resolves.toBeNull()
  })

  it("reports a picker that threw as null rather than rejecting into the UI", async () => {
    invoke.mockRejectedValueOnce(new Error("dialog plugin missing"))
    const { platform } = createTauriPlatform("0.1.0")
    if (platform.platform !== "desktop") throw new Error("narrowing")
    await expect(platform.openDirectoryPickerDialog()).resolves.toBeNull()
  })

  it("RESTART RELOADS THE WINDOW AND NEVER TOUCHES THE ENGINE", async () => {
    // THE TEST THIS FILE EXISTS FOR. Their app calls restart() to apply a
    // setting or an update. The engine is a separate process so that it
    // outlives the webview, and what it is doing is often a twenty-minute
    // eval. Routing restart() to restart_engine would kill that eval every
    // time a setting changed.
    const reload = vi.fn()
    vi.spyOn(window, "location", "get").mockReturnValue({ ...window.location, reload } as Location)
    const { platform } = createTauriPlatform("0.1.0")
    await platform.restart()
    expect(reload).toHaveBeenCalledOnce()
    expect(invoke).not.toHaveBeenCalledWith("restart_engine", expect.anything())
    expect(invoke).not.toHaveBeenCalledWith("restart_engine")
  })

  it("refuses to open anything that is not a web or mail link", () => {
    // A model-authored link must not become a file: or javascript:
    // navigation just because somebody clicked it.
    const open = vi.spyOn(window, "open").mockImplementation(() => null)
    const { platform } = createTauriPlatform("0.1.0")
    platform.openExternal("javascript:alert(1)")
    platform.openExternal("file:///C:/Windows/System32")
    platform.openExternal("not a url")
    expect(open).not.toHaveBeenCalled()
    platform.openExternal("https://example.com/docs")
    expect(open).toHaveBeenCalledWith("https://example.com/docs", "_blank", "noopener,noreferrer")
  })
})
