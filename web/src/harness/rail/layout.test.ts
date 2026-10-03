import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"
import { keepVertical, type TabLayout } from "./layout"

// A settings double owned by this test: the one field the layout reads and writes.
function settings(start: TabLayout) {
  let value = start
  return {
    appearance: {
      tabLayout: () => value,
      setTabLayout: (next: TabLayout) => void (value = next),
    },
  }
}

describe("the layout is always the left sidebar (Jaden, 2026-10-03)", () => {
  it("puts a horizontal layout back to vertical", () => {
    const store = settings("horizontal")
    expect(keepVertical(store)).toBe(true)
    expect(store.appearance.tabLayout()).toBe("vertical")
  })

  it("leaves a vertical layout alone", () => {
    const store = settings("vertical")
    expect(keepVertical(store)).toBe(false)
    expect(store.appearance.tabLayout()).toBe("vertical")
  })

  it("offers no switch: no palette command, no shortcut, no rail button", () => {
    const here = (path: string) => readFileSync(resolve(process.cwd(), "src", "harness", path), "utf-8")
    for (const file of ["root.tsx", "rail/rail.tsx"]) {
      expect(here(file)).not.toContain("harness.layout")
      expect(here(file)).not.toContain("harness-rail-tab-layout")
      expect(here(file)).not.toContain('setTabLayout("horizontal")')
    }
  })
})
