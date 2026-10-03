/**
 * ONE LAYOUT: the left sidebar, always (Jaden, 2026-10-03: "you can see all
 * the projects from the left side ... always vertical not horizontal
 * sidebars").
 *
 * Their app has two (settings/model.tsx `appearance.tabLayout`): tabs across
 * the titlebar with no sidebar, or the left sidebar where the harness rail
 * lives (rail.tsx). The switch between them that 2026-09-23 added - a palette
 * command, Ctrl+Shift+H and a button in the rail - is gone, and a layout set
 * to horizontal anywhere (an older install, their Experimental page) is put
 * back to vertical.
 */

export type TabLayout = "horizontal" | "vertical"

type LayoutSettings = {
  appearance: { tabLayout(): TabLayout; setTabLayout(value: TabLayout): void }
}

/** Put the layout back to the sidebar if anything set it otherwise. True when it changed it. */
export function keepVertical(settings: LayoutSettings): boolean {
  if (settings.appearance.tabLayout() === "vertical") return false
  settings.appearance.setTabLayout("vertical")
  return true
}
