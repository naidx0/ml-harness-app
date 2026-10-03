import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

const read = (path: string) => readFileSync(resolve(process.cwd(), path), "utf-8")

describe("Home is one column (Jaden, 2026-10-03)", () => {
  it("stands in for their Home", () => {
    expect(read("vite.config.ts")).toContain('"home/route.tsx": "./src/harness/home/route.tsx"')
  })

  it("has no projects column and no Settings or Help links: the sidebar has them", () => {
    const ours = read("src/harness/home/route.tsx")
    expect(ours).not.toContain("HomeProjects")
    expect(ours).not.toContain("HomeUtilityNav")
    expect(ours).not.toContain("grid-cols-[280px")
    // Theirs did, so the check has something to find.
    const theirs = read("../vendor/opencode/packages/app/src/home/route.tsx")
    expect(theirs).toContain("HomeProjects")
    expect(theirs).toContain("HomeUtilityNav")
  })

  it("shows one New chat button, never two", () => {
    const ours = read("src/harness/home/route.tsx")
    // Their floating one is hidden; the header's shows only when the empty state's does not.
    expect(ours).toContain('import "./home.css"')
    expect(read("src/harness/home/home.css")).toMatch(/\[data-component="harness-home"\] \[data-action="home-new-session"\] \{\s*display: none;/)
    expect(ours).toContain("sessions.data.groups().length > 0")
  })

  it("draws New chat as the one primary button, in the harness accent", () => {
    expect(read("src/harness/home/route.tsx")).toMatch(/data-action="harness-home-new-chat"\s+data-harness-primary/)
    expect(read("src/brand/identity.css")).toMatch(/\[data-harness-primary\] \{\s*background-color: var\(--harness-accent\)/)
  })
})
