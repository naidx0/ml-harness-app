import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"
import { CONTEXT_PANE, HARNESS_PANES, POP_OUT_ICON } from "./panes"

/**
 * The panel icons are one set: their v2 icons (`additionalIcons`), the ones
 * their own side-panel tabs draw. `Icon` takes any string and draws "plus"
 * for a name it does not know, so a typo passes the type check; and a name
 * their older 16-unit set also defines wins the lookup and draws in that
 * set's weight. Both are read from the library's own source, not a copy.
 */

const ICONS = resolve(process.cwd(), "..", "node_modules", "@opencode", "ui", "src", "icons", "icon")

/** The keys of the object literal that starts at `start`, one per line at two spaces. */
function keysOf(source: string, start: string) {
  const body = source.slice(source.indexOf(start))
  const end = body.indexOf("\n}")
  return new Set([...body.slice(0, end).matchAll(/^ {2}"?([a-z0-9-]+)"?: /gm)].map((match) => match[1]))
}

const v2 = keysOf(readFileSync(resolve(ICONS, "additional-icons.ts"), "utf-8"), "export const additionalIcons = {")
const older = keysOf(readFileSync(resolve(ICONS, "icon.tsx"), "utf-8"), "const icons = {")

const panes = [...HARNESS_PANES, CONTEXT_PANE]
const used = [...panes.map((pane) => ({ where: pane.id, icon: pane.icon })), { where: "pop-out", icon: POP_OUT_ICON }]

describe("panel icons", () => {
  it("reads both sets (a parse that found nothing would pass everything below)", () => {
    expect(v2.has("bubble-5")).toBe(true)
    expect(v2.has("file-tree")).toBe(true)
    expect(older.has("grid-plus")).toBe(true)
    expect(older.has("bubble-5")).toBe(false)
  })

  // THE ONE NAMED EXCEPTION. "monitor" is the older-set icon their session
  // header draws beside every chat title, and the owner asked for exactly
  // that icon on Agents ("the same icon Alpha has on its actual thing - very
  // clean"). It draws in the older weight on purpose: it matches the title
  // it echoes. Any other older-set icon still fails here.
  const EXCEPTIONS: Record<string, string> = { agents: "monitor" }

  it("every panel icon is a v2 icon their older set does not shadow", () => {
    const wrong = used.filter(
      ({ where, icon }) => EXCEPTIONS[String(where)] !== String(icon) && (!v2.has(String(icon)) || older.has(String(icon))),
    )
    expect(wrong).toEqual([])
  })

  it("the exception is real: monitor is an older-set icon, so the rule would catch it", () => {
    expect(older.has("monitor")).toBe(true)
    expect(HARNESS_PANES.find((pane) => pane.id === "agents")?.icon).toBe("monitor")
  })

  it("Context has one way in, their ring: it is not a panel tab", () => {
    expect(HARNESS_PANES.map((pane) => pane.id)).not.toContain(CONTEXT_PANE.id)
  })

  it("no two panes share an icon", () => {
    const icons = panes.map((pane) => pane.icon)
    expect(new Set(icons).size).toBe(icons.length)
  })
})
