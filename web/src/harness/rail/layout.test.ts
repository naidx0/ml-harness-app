import { describe, expect, it } from "vitest"
import { otherTabLayout, tabLayoutCommand, TAB_LAYOUT_COMMAND, TAB_LAYOUT_KEYBIND, type TabLayout } from "./layout"

// A settings double owned by this test: the one field the command reads and writes.
function settings(start: TabLayout) {
  let value = start
  return {
    appearance: {
      tabLayout: () => value,
      setTabLayout: (next: TabLayout) => void (value = next),
    },
  }
}

describe("the tab layout switch (the owner, 2026-09-23)", () => {
  it("flips between the two layouts and back", () => {
    expect(otherTabLayout("vertical")).toBe("horizontal")
    expect(otherTabLayout("horizontal")).toBe("vertical")
  })

  it("is one palette command with one shortcut, titled for where the person is", () => {
    const store = settings("vertical")
    const first = tabLayoutCommand(store, "View")
    expect(first).toMatchObject({ id: TAB_LAYOUT_COMMAND, keybind: TAB_LAYOUT_KEYBIND, category: "View" })
    expect(first.title).toBe("Show open chats as tabs across the top")
    first.onSelect()
    expect(store.appearance.tabLayout()).toBe("horizontal")
    const back = tabLayoutCommand(store, "View")
    expect(back.title).toBe("Show the session rail")
    // The same id and key from either side: one shortcut, both directions.
    expect([back.id, back.keybind]).toEqual([first.id, first.keybind])
    back.onSelect()
    expect(store.appearance.tabLayout()).toBe("vertical")
  })

  it("reads the setting when chosen, not when the palette was built", () => {
    const store = settings("vertical")
    const stale = tabLayoutCommand(store, "View")
    store.appearance.setTabLayout("horizontal")
    stale.onSelect()
    expect(store.appearance.tabLayout()).toBe("vertical")
  })
})
