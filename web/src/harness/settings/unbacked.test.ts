import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"
import { clientSettings, projectSettings, serverSettings } from "./search-catalog"
import { harnessFilterSettings, harnessSettingsGroups } from "./slots"
import { HIDDEN_SETTING_ROWS, UNBACKED_SETTINGS } from "./unbacked"

const VENDORED = resolve(process.cwd(), "..", "vendor", "opencode", "packages", "app", "src")
const vendored = (path: string) => readFileSync(resolve(VENDORED, path), "utf-8")

/** PATCHES-format tuples from Python source: each value a quoted string or chr(10).join([...]). */
function pendingPatches(block: string): [string, string, string][] {
  return block
    .split(/^ {4}\(\n/m)
    .slice(1)
    .map((chunk) => {
      const body = chunk.slice(0, chunk.indexOf("\n    ),"))
      const values: string[] = []
      let joined: string[] | undefined
      for (const token of body.matchAll(/chr\(10\)\.join\(\[|\]\)|"([^"]*)"|'([^']*)'/g)) {
        if (token[0].startsWith("chr(")) joined = []
        else if (token[0] === "])") {
          values.push((joined ?? []).join("\n"))
          joined = undefined
        } else (joined ?? values).push(token[1] ?? token[2] ?? "")
      }
      return values as [string, string, string]
    })
}

describe("settings with no backing are hidden everywhere they are listed", () => {
  it("their catalogue does list them (a filter over nothing would pass)", () => {
    const catalogue = vendored("settings/search-catalog.ts")
    // Every one they list ("servers" has no search entry of its own).
    for (const tab of ["workspaces", "extensions", "pairing"]) expect(catalogue).toContain(`tab: "${tab}"`)
  })

  it("settings search offers none of them, and still offers the rest", () => {
    const tabs = [...clientSettings, ...serverSettings, ...projectSettings].map((entry) => entry.tab as string)
    expect(tabs.filter((tab) => UNBACKED_SETTINGS.has(tab))).toEqual([])
    // Their Providers and Models pages are gone too (2026-10-03): the harness's
    // Models page is the one place a model is added.
    expect(tabs).not.toContain("providers")
    expect(tabs).not.toContain("models")
    expect(tabs).toContain("general")
  })

  it("settings search offers no row the page no longer draws (P26, P27), and their catalogue did", () => {
    const catalogue = vendored("settings/search-catalog.ts")
    const targets = [...clientSettings, ...serverSettings, ...projectSettings].map((entry) => entry.target)
    for (const target of HIDDEN_SETTING_ROWS) {
      expect(catalogue).toContain(`target: "${target}"`)
      expect(targets).not.toContain(target)
    }
    // The rows that stay are still offered. (This named settings-language
    // until the owner's 2026-09-23 pass queued Language for hiding.)
    expect(targets).toContain("settings-auto-accept-permissions")
    expect(targets).toContain("settings-timeline-detail")
    expect(targets).toContain("settings-notifications-agent")
  })

  it("their Appearance and About pages are gone from navigation and search, and the harness has its own About", () => {
    // The owner, 2026-09-23: "we only have one appearance ... get rid of that About".
    const groups = harnessFilterSettings([
      { items: [{ value: "general", icon: "settings-gear", label: "Preferences" }, { value: "appearance", icon: "link", label: "Appearance" }] },
      ...harnessSettingsGroups(),
      { items: [{ value: "about", icon: "info", label: "About" }] },
    ])
    const values = groups.flatMap((group) => group.items.map((item) => item.value))
    expect(values).not.toContain("appearance")
    expect(values).not.toContain("about")
    expect(values).toContain("general")
    expect(values).toContain("harness:about")
    const tabs = [...clientSettings, ...serverSettings, ...projectSettings].map((entry) => entry.tab as string)
    expect(vendored("settings/search-catalog.ts")).toContain('tab: "about"')
    expect(tabs).not.toContain("about")
    expect(tabs).not.toContain("appearance")
  })

  it("the pending patches have landed in the vendored pages (PENDING-PATCHES.md is a record, not a queue)", () => {
    // 2026-09-23: the tuples were pasted into vendor_opencode.py (P32-P43) and
    // applied, so the md holds no code block any more, and each row it names
    // is gone from the page it named - except the tab-layout row, which stays
    // as the rail/top-tabs switch the owner asked for.
    const doc = readFileSync(resolve(process.cwd(), "src", "harness", "settings", "PENDING-PATCHES.md"), "utf-8")
    expect(doc.includes("```python")).toBe(false)
    expect(pendingPatches(doc.match(/```python\n([\s\S]*?)```/)?.[1] ?? "")).toEqual([])
    const general = vendored("settings/general/general.tsx")
    expect(general.includes("<LanguageSetting />")).toBe(false)
    expect(general.includes('from "@harness/settings/color-scheme"')).toBe(true)
    expect(general.includes('data-action="settings-show-custom-agents"')).toBe(false)
    expect(general.includes("<FollowUpBehaviorSetting />")).toBe(false)
    expect(general.includes('data-action="settings-pinch-zoom"')).toBe(false)
    expect(general.includes("<UpdatesSection />")).toBe(false)
    const notifications = vendored("settings/notifications/notifications.tsx")
    expect(notifications.includes('data-action="settings-notifications-permissions"')).toBe(false)
    expect(notifications.includes("<SoundSetting")).toBe(false)
    expect(vendored("shell/updates/highlights.tsx").includes("if (true || !settings.general.releaseNotes())")).toBe(true)
    expect(vendored("settings/experimental/experimental.tsx").includes('data-action="settings-tab-layout"')).toBe(true)
    expect(HIDDEN_SETTING_ROWS.has("settings-tab-layout")).toBe(false)
    // The colour-scheme row moved to General with the patch; search follows it.
    const scheme = clientSettings.filter((entry) => entry.target === "settings-color-scheme")
    expect(scheme.map((entry) => entry.tab)).toEqual(["general"])
    const keybinds = vendored("settings/keybinds/keybinds.tsx")
    expect(keybinds.split("if (opt.id in UNSUPPORTED_COMMANDS) continue").length - 1).toBe(2)
  })

  it("the navigation filter drops them and an emptied group", () => {
    const groups = harnessFilterSettings([
      { items: [{ value: "general", icon: "settings-gear", label: "General" }, { value: "pairing", icon: "link", label: "Pairing" }] },
      { items: [{ value: "workspaces", icon: "link", label: "Worktrees" }, { value: "extensions", icon: "link", label: "Extensions" }] },
    ])
    expect(groups.map((group) => group.items.map((item) => item.value))).toEqual([["general"]])
  })
})

describe("the vendored UI no longer reaches a surface with no backing", () => {
  it("no terminal or MCP commands are registered (P23)", () => {
    const commands = vendored("session/commands/use-session-commands.tsx")
    expect(commands).not.toContain("    ...terminalCmds(),")
    expect(commands).not.toContain("    ...mcpCmds(),")
    expect(commands).toContain("    ...permissionsCmds(),")
  })

  it("no session is eligible to move to a worktree (P22)", () => {
    expect(vendored("session/composer/region.tsx")).toContain("workspaceMoveEligible: () => false,")
  })

  it('"!" in the composer is text, not shell mode (P25)', async () => {
    // Their own state machine, driven: a lone "!" used to switch to shell
    // mode and clear the draft.
    const { createComposerInteractionState, transitionComposer } = await import("@/composer/suggestions/machine")
    const next = transitionComposer(
      createComposerInteractionState(),
      { type: "input.changed", value: "!" },
      { cursor: 1 } as Parameters<typeof transitionComposer>[2],
    )
    expect(next.state.mode).toBe("normal")
    expect(next.commands).not.toContainEqual({ type: "draft.setText", value: "" })
  })

  it("no worktree controls on the pages that show (P27-P29)", async () => {
    const general = vendored("settings/general/general.tsx")
    expect(general).not.toContain("        <WorkspaceDestinationSetting />")
    expect(vendored("settings/workspaces/project.tsx")).toContain(
      '<div class="project-settings-startup" style={{ display: "none" }}>',
    )
    // Their own function, driven: a saved "New worktree" means the project's folder.
    const { workspaceDefaultSelection } = await import("@/workspaces/paths")
    expect(workspaceDefaultSelection("new", undefined)).toBe("main")
    expect(workspaceDefaultSelection("local", undefined)).toBe("main")
    expect(workspaceDefaultSelection("last-used", "local")).toBe("main")
  })

  it("a project's settings tabs are filtered (P24)", () => {
    expect(vendored("settings/shell.tsx")).toContain("nestedProjectTabs.filter((item) => !harnessUnbackedSetting(item.value))")
  })
})
