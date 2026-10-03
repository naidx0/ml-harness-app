import { For, lazy, type Component } from "solid-js"
import { Tabs } from "@opencode/ui/tabs"
import type { SettingsNavGroup } from "@/settings/navigation"
import { CONTROLS_SETTINGS_TAB } from "./controls-open"
import { harnessUnbackedSetting } from "./unbacked"

/**
 * The harness's own settings, as a group in their Settings screen (patches
 * P9-P12). Their Providers and Models pages are hidden (unbacked.ts):
 * Models here is the one place a model is added.
 *
 *   Models      - every model connection: on this computer, with an API key,
 *                 and where keys are kept (tab value harness:connections).
 *   Tools       - sub-agents at once, and tool packs with their token cost.
 *   Controls    - every tool, run by hand (moved out of the side panel).
 *   This machine- every hardware field, with where it came from.
 *   Engine      - which engine this window talks to and what it runs.
 *   About       - this product's name, version, build and database, in
 *                 place of their About (the owner, 2026-09-23; unbacked.ts).
 *
 * Tab values carry the `harness:` prefix their tab check was taught (P9).
 */

type Section = { value: string; label: string; icon: SettingsNavGroup["items"][number]["icon"]; component: Component }

const SECTIONS: Section[] = [
  { value: "harness:connections", label: "Models", icon: "cube", component: lazy(() => import("./connections")) },
  { value: "harness:tools", label: "Tools", icon: "outline-sliders", component: lazy(() => import("./tools")) },
  { value: CONTROLS_SETTINGS_TAB, label: "Controls", icon: "window-cursor", component: lazy(() => import("./controls")) },
  { value: "harness:machine", label: "This machine", icon: "monitor", component: lazy(() => import("./machine")) },
  { value: "harness:engine", label: "Engine", icon: "server", component: lazy(() => import("./engine")) },
  { value: "harness:about", label: "About", icon: "info", component: lazy(() => import("./about")) },
]

export function harnessSettingsGroups(): SettingsNavGroup[] {
  return [
    {
      label: "Harness",
      items: SECTIONS.map(({ value, label, icon }) => ({ value, label, icon })),
    },
  ]
}

/**
 * Their settings pages this product does not show (patch P19); which, and
 * why each, is in unbacked.ts. Hidden from navigation, not deleted.
 */
export function harnessFilterSettings(groups: SettingsNavGroup[]): SettingsNavGroup[] {
  return groups
    .map((group) => ({ ...group, items: group.items.filter((item) => !harnessUnbackedSetting(item.value)) }))
    .filter((group) => group.items.length > 0)
}

export function HarnessSettingsPanels() {
  return (
    <For each={SECTIONS}>
      {(section) => (
        <Tabs.Content value={section.value} class="settings-panel">
          <section.component />
        </Tabs.Content>
      )}
    </For>
  )
}
