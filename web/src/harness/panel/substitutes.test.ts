import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

/**
 * A substituted module must export every name the module it stands in for
 * exports. Their code imports those names; a replacement that drops one
 * builds (Vite does not check named imports across a substitution the way
 * tsc would, and tsc never sees the substitution) and fails only when the
 * screen that imports it opens. The subject set is the SUBSTITUTES table
 * itself, so a new entry is checked without anyone adding it here.
 */

const WEB = process.cwd()
const VENDORED = resolve(WEB, "..", "vendor", "opencode", "packages", "app", "src")

function substitutes(): [string, string][] {
  const config = readFileSync(resolve(WEB, "vite.config.ts"), "utf-8")
  const block = /const SUBSTITUTES: Record<string, string> = \{([\s\S]*?)\n\}/.exec(config)?.[1] ?? ""
  return [...block.matchAll(/"([^"]+)":\s*"([^"]+)"/g)].map((match) => [match[1]!, match[2]!])
}

/** Runtime exports: `export function|const|class|let NAME` and `export { A, B }`. Types are left out. */
function exportsOf(source: string): Set<string> {
  const names = new Set<string>()
  for (const match of source.matchAll(/^export (?:async )?(?:function|const|class|let) (\w+)/gm)) names.add(match[1]!)
  for (const match of source.matchAll(/^export \{([^}]+)\}/gm)) {
    for (const part of match[1]!.split(",")) {
      const name = part.trim().split(/\s+as\s+/).pop()?.trim()
      if (name && !name.startsWith("type ")) names.add(name)
    }
  }
  return names
}

describe("every substitution keeps its original's exports", () => {
  const table = substitutes()

  it("reads the table (a regex that matched nothing would pass the rest)", () => {
    expect(table.map(([from]) => from)).toContain("session/header/session-header-actions.tsx")
    expect(exportsOf("export function A() {}\nexport const B = 1\nexport { C, D as E }\nexport type F = 1")).toEqual(
      new Set(["A", "B", "C", "E"]),
    )
  })

  for (const [from, to] of table) {
    it(from, () => {
      const theirs = exportsOf(readFileSync(resolve(VENDORED, from), "utf-8"))
      const source = readFileSync(resolve(WEB, to), "utf-8")
      expect(theirs.size).toBeGreaterThan(0)
      // A wrapper that re-exports the original wholesale keeps every name.
      if (/^export \* from "@\/[^"]+"/m.test(source)) return
      const ours = exportsOf(source)
      expect([...theirs].filter((name) => !ours.has(name))).toEqual([])
    })
  }
})
