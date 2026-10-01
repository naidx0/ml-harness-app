import { readdirSync, readFileSync } from "node:fs"
import { join, resolve } from "node:path"
import { describe, expect, it } from "vitest"
import { dict as theirUI } from "@opencode/ui/i18n/en"
import { UI_STRINGS } from "./ui-strings"

// strings.ts itself is not imported: under vitest the `@/runtime/i18n/en`
// substitution resolves strings.ts's own import of their file back to
// strings.ts, so any test importing it fails before a line runs. Its one job
// here - importing ui-strings.ts - is checked from its source instead.

describe("the composer's words", () => {
  it("win the spread their language context builds, which puts their UI strings last", () => {
    // runtime/i18n/language.tsx: `flatten({ ...en, ...dict })`. A key only in
    // the app dictionary would lose to their UI copy; the write onto their UI
    // dictionary is what makes ours win.
    const appCopy = Object.fromEntries(Object.keys(UI_STRINGS).map((key) => [key, "their app copy"]))
    const english: Record<string, string> = { ...appCopy, ...theirUI }
    for (const [key, value] of Object.entries(UI_STRINGS)) expect(english[key]).toBe(value)
  })

  it("the + menu says what each entry does, and the agent picker is the mode picker", () => {
    expect(UI_STRINGS["ui.promptInput.attachments"]).toMatch(/^Attach/)
    expect(UI_STRINGS["ui.promptInput.context"]).toMatch(/file or folder/)
    expect(UI_STRINGS["ui.promptInput.chooseAgent"]).toBe("Choose mode")
  })

  it("strings.ts, which is their English, imports the rewrite", () => {
    const source = readFileSync(resolve(process.cwd(), "src", "brand", "strings.ts"), "utf-8")
    expect(source).toMatch(/^import "\.\/ui-strings"$/m)
    expect(source).toContain('"prompt.action.attachFile": "Attach files to this message"')
  })
})

/**
 * THEIR WORKTREE COPY, EVERY KEY OF IT CLASSIFIED. The subject set is derived:
 * every key in their English whose value says workspace or worktree. Each is
 * either reworded here (a key strings.ts sets), sits on a surface the harness
 * hides (a prefix below, with the reason), or is referenced by no file in
 * their app at all. An upstream key in none of the three fails this test.
 */
const HIDDEN: Record<string, string> = {
  "settings.workspaces.": "Settings > Worktrees is hidden (harness/settings/unbacked.ts); its General row by P27",
  "settings.tab.workspaces": "the same hidden page's tab",
  "workspace.": "worktree create/move/reset/delete: the picker is substituted, moves are off (P22), a saved default is not (P28)",
  "session.new.workspace.": "their worktree picker, substituted by panel/unbacked/workspace-selector.tsx",
  "session.new.worktree.": "the same picker",
  "session.location.worktree": "the location picker, whose menu P22 disables",
  "dialog.project.edit.worktree.": "the worktree startup script, hidden by P29",
  "project.settings.worktree.": "the same startup script block",
  "prompt.toast.worktreeCreateFailed.": "only after creating a worktree, which nothing here starts",
  "session.summary.mcp.": "MCP servers: the summary panel is substituted and the harness runs none",
  "provider.connect.console.": "their hosted Console sign-in, which the facade's provider catalogue does not offer",
}

describe("their worktree copy", () => {
  const VENDORED = resolve(process.cwd(), "..", "vendor", "opencode", "packages", "app", "src")
  const theirEnglish = readFileSync(resolve(VENDORED, "runtime", "i18n", "en.ts"), "utf-8")
  const ours = readFileSync(resolve(process.cwd(), "src", "brand", "strings.ts"), "utf-8")
  // "key": "value" or "key":<newline>    "value" - their file has both.
  const entries = [...theirEnglish.matchAll(/^\s+"([\w.]+)":\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')/gm)].map(
    (match) => ({ key: match[1], value: match[2] ?? match[3] ?? "" }),
  )
  const banned = entries.filter((entry) => /\b(workspaces?|worktrees?)\b/i.test(entry.value))
  const reworded = new Set([...ours.matchAll(/^\s+"([\w.]+)":/gm)].map((match) => match[1]))

  function appSources(directory: string): string[] {
    return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
      const path = join(directory, entry.name)
      if (entry.isDirectory()) return entry.name === "i18n" ? [] : appSources(path)
      return /\.tsx?$/.test(entry.name) ? [readFileSync(path, "utf-8")] : []
    })
  }
  const theirApp = appSources(VENDORED).join("\n")

  it("reads their whole dictionary (a parse of nothing would pass)", () => {
    expect(entries.length).toBeGreaterThan(1000)
    expect(banned.length).toBeGreaterThan(50)
    expect(banned.map((entry) => entry.key)).toContain("settings.tab.workspaces")
    expect(banned.map((entry) => entry.key)).toContain("command.category.workspace")
    // A key their app does reference is found by the reference check.
    expect(theirApp.includes('"command.category.workspace"')).toBe(true)
  })

  it("is reworded, hidden with a reason, or never referenced", () => {
    const unclassified = banned
      .map((entry) => entry.key)
      .filter((key) => !reworded.has(key))
      .filter((key) => !Object.keys(HIDDEN).some((prefix) => key.startsWith(prefix)))
      .filter((key) => theirApp.includes(`"${key}"`))
    expect(unclassified).toEqual([])
  })

  it("what is reworded says project or chat, never workspace", () => {
    const rewordedBanned = banned.filter((one) => reworded.has(one.key))
    expect(rewordedBanned.length).toBeGreaterThan(0)
    for (const entry of rewordedBanned) {
      const line = ours.split("\n").find((one) => one.includes(`"${entry.key}":`)) ?? ""
      const value = line.slice(line.indexOf(`"${entry.key}":`) + entry.key.length + 3)
      expect(value.trim().length).toBeGreaterThan(0)
      expect(value).not.toMatch(/\b(workspaces?|worktrees?)\b/i)
    }
  })

  it("the words a person reads as they move between chats and projects", () => {
    for (const [key, value] of [
      ["command.session.new", "New chat"],
      ["home.sessions.search.placeholder", "Search chats"],
      ["sidebar.nav.projectsAndSessions", "Projects and chats"],
      ["session.new.git.none", "Local folder"],
    ]) {
      expect(ours).toContain(`"${key}": "${value}"`)
    }
  })
})
