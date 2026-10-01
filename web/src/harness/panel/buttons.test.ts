import { readdirSync, readFileSync } from "node:fs"
import { join, resolve } from "node:path"
import { describe, expect, it } from "vitest"

/**
 * The harness's panel chrome uses their header controls' button: every
 * header icon button beside it - their Add tab, Toggle review, Session
 * details - is `size="large"`, `variant="ghost-muted"`, measured 28x28 in the
 * running app. The pane header's pop-out was `small`, a visibly smaller
 * target beside them. Subjects are derived: every .tsx in panel/ and window/.
 */

const harness = resolve(process.cwd(), "src", "harness")
const subjects = ["panel", "window"].flatMap((dir) =>
  readdirSync(join(harness, dir))
    .filter((name) => name.endsWith(".tsx") && !name.includes(".test."))
    .map((name) => join(harness, dir, name)),
)

/**
 * Each `<IconButton` (or a Menu.Trigger rendered `as={IconButton}`) with its
 * attributes: to the `/>` that closes the tag on a line of its own, or to the
 * end of the line for a one-line tag. (A lazy match to the first `/>` stops
 * inside the `icon={<Icon ... />}` attribute.)
 */
function iconButtons(source: string) {
  return [...source.matchAll(/<(?:IconButton\b|Menu\.Trigger\s+as=\{IconButton\})([^\n]*\/>|[\s\S]*?\n\s*\/>)/g)].map(
    (match) => match[1]!,
  )
}

describe("panel chrome button sizes match theirs", () => {
  it("finds the buttons it checks (a scan that finds none proves nothing)", () => {
    const all = subjects.flatMap((path) => iconButtons(readFileSync(path, "utf-8")))
    expect(all.length).toBeGreaterThanOrEqual(3)
    expect(iconButtons('<IconButton icon={<Icon name="x" />} size="small" />')).toHaveLength(1)
  })

  it("every icon button is their large, ghost-muted", () => {
    const wrong = subjects.flatMap((path) =>
      iconButtons(readFileSync(path, "utf-8"))
        .filter((attrs) => !/size="large"/.test(attrs) || !/variant="ghost-muted"/.test(attrs))
        .map((attrs) => `${path}: ${attrs.replace(/\s+/g, " ").trim().slice(0, 80)}`),
    )
    expect(wrong).toEqual([])
  })
})
