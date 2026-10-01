import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"
import { addEntries } from "./add-menu"
import { HARNESS_PANES } from "./panes"

const kinds = (query: string) =>
  addEntries(query, "Open file", HARNESS_PANES).map((entry) => (entry.kind === "file" ? "file" : entry.pane.id))

describe("the one side-panel plus", () => {
  it("offers Open file first, then every harness panel, with no query", () => {
    expect(kinds("")).toEqual(["file", ...HARNESS_PANES.map((pane) => pane.id)])
  })

  it("one search filters both kinds", () => {
    expect(kinds("file")).toEqual(["file"])
    expect(kinds("PLAN")).toContain("plan")
    expect(kinds("plan")).not.toContain("file")
    expect(kinds("sub-agents")).toEqual(["agents"])
  })

  it("a query nothing matches offers nothing", () => {
    expect(kinds("zzz-no-such-thing")).toEqual([])
  })

  it("the side panel draws one plus, the harness one, and no browser entry", () => {
    // The patched vendored file (P8 in scripts/vendor_opencode.py): their
    // plus block, both of its variants, is replaced by ours.
    const panel = readFileSync(
      resolve(process.cwd(), "..", "vendor", "opencode", "packages", "app", "src", "session", "files", "session-side-panel.tsx"),
      "utf-8",
    )
    expect(panel.match(/<HarnessPanelAddButton\b/g)?.length).toBe(1)
    expect(panel).toContain("<HarnessPanelAddButton onOpenFile={openFileBrowser}")
    expect(panel).not.toContain('icon={<Icon name="plus" />}')
    expect(panel).not.toContain("onSelect={props.browser.open}")
  })
})
