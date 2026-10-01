/**
 * THE TWO WAYS TO SEE YOUR CHATS, one key apart (the owner, 2026-09-23: "you
 * can see better in horizontal than in vertical [the sessions you have
 * opened]; it should be easy to switch those modes").
 *
 * The two modes are their tab layout setting (settings/model.tsx
 * `appearance.tabLayout`), which their app kept under Settings > Experimental
 * as "Horizontal" and "Vertical":
 *   - horizontal: their tab strip across the titlebar, one tab per open chat,
 *     and no left sidebar;
 *   - vertical: their left sidebar, where the harness session rail lives
 *     (rail.tsx), and the open tabs shown only as the rail's open mark.
 * Nothing new is drawn: this is one palette command, with one shortcut,
 * that flips the setting their own shell already reads (shell/shell.tsx
 * `verticalTabs`). It is registered from the harness root, so it answers in
 * both modes; the rail's header button is its one-click form in the sidebar.
 */

export type TabLayout = "horizontal" | "vertical"

export const TAB_LAYOUT_COMMAND = "harness.layout.toggle"
/** Free in their catalogue and ours: nothing else binds shift+H. */
export const TAB_LAYOUT_KEYBIND = "mod+shift+h"

export function otherTabLayout(current: TabLayout): TabLayout {
  return current === "vertical" ? "horizontal" : "vertical"
}

/** What switching does, said from where the person is now. */
export function tabLayoutTitle(current: TabLayout) {
  return current === "vertical" ? "Show open chats as tabs across the top" : "Show the session rail"
}

type LayoutSettings = {
  appearance: { tabLayout(): TabLayout; setTabLayout(value: TabLayout): void }
}

export function tabLayoutCommand(settings: LayoutSettings, category: string) {
  const current = settings.appearance.tabLayout()
  return {
    id: TAB_LAYOUT_COMMAND,
    title: tabLayoutTitle(current),
    // Short: their palette gives the title what the description leaves, and
    // a long one cut the title to "Show the session ..." (looked at, 2026-09-23).
    description: "Tabs on top, or the rail",
    category,
    keybind: TAB_LAYOUT_KEYBIND,
    onSelect: () => settings.appearance.setTabLayout(otherTabLayout(settings.appearance.tabLayout())),
  }
}
