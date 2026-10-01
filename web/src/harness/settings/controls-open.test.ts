import { createRoot } from "solid-js"
import { afterEach, describe, expect, it, vi } from "vitest"

// Their settings surface, stood in for: present (a chat's window) or absent
// (a pop-out, where `use()` throws the way createSimpleContext does).
const surface = { open: vi.fn() }
let present = true
vi.mock("@/settings/surface", () => ({
  useSettingsSurface: () => {
    if (!present) throw new Error("SettingsSurface context must be used within a context provider")
    return surface
  },
}))

const { CONTROLS_SETTINGS_TAB, useOpenToolControls } = await import("./controls-open")
const { clearToolFocus, focusedTool } = await import("../panes/controls-focus")
const { HARNESS_PANES } = await import("../panel/panes")

afterEach(() => {
  present = true
  surface.open.mockReset()
  clearToolFocus()
})

describe("Controls, moved to Settings", () => {
  it("is not a side-panel pane any more", () => {
    expect(HARNESS_PANES.map((pane) => pane.id)).not.toContain("controls")
  })

  it("opening a tool asks for its row and opens the Controls settings page", () => {
    createRoot((dispose) => {
      const open = useOpenToolControls()
      expect(open).toBeTypeOf("function")
      open!("measure_baseline")
      expect(focusedTool()?.name).toBe("measure_baseline")
      expect(surface.open).toHaveBeenCalledWith(CONTROLS_SETTINGS_TAB)
      expect(CONTROLS_SETTINGS_TAB.startsWith("harness:")).toBe(true)
      dispose()
    })
  })

  it("offers nothing where there is no settings surface to open", () => {
    present = false
    createRoot((dispose) => {
      expect(useOpenToolControls()).toBeUndefined()
      expect(focusedTool()).toBeUndefined()
      dispose()
    })
  })
})
