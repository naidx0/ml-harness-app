import { readdirSync, readFileSync } from "node:fs"
import { join, resolve } from "node:path"
import { describe, expect, it } from "vitest"

/**
 * Two class names that pass every DOM test and draw nothing, because their
 * Tailwind theme resets the scale:
 *
 *   - bare `rounded` generates no CSS at all; `rounded-sm` is the step.
 *   - `text-12-regular` sets font-family, so beside `font-mono` it wins and
 *     the "monospace" text is sans; `text-12-mono` is the utility.
 *
 * The subject set is derived: every .tsx in panes/, plus the other harness
 * files this lane draws.
 */

const harness = resolve(process.cwd(), "src", "harness")
const panes = join(harness, "panes")
const subjects = [
  ...readdirSync(panes)
    .filter((name) => name.endsWith(".tsx") && !name.includes(".test."))
    .map((name) => join(panes, name)),
  ...["ui.tsx", "panel/slots.tsx", "cards/diagnosis.tsx", "cards/bench.tsx", "cards/eval.tsx"].map((path) =>
    join(harness, path),
  ),
  ...["machine.tsx", "tools.tsx", "connections.tsx"].map((name) => join(harness, "settings", name)),
]

// `rounded` as a whole class: preceded by a quote or a space, followed by a
// quote or a space. `rounded-sm`, `rounded-md` and `rounded-full` do not match.
const BARE_ROUNDED = /["'\s]rounded["'\s]/
const MONO_LOST = /font-mono[^"'`]*text-1[246]-(?:regular|medium)|text-1[246]-(?:regular|medium)[^"'`]*font-mono/

function offenders(pattern: RegExp) {
  return subjects.flatMap((path) =>
    readFileSync(path, "utf-8")
      .split("\n")
      .map((text, index) => ({ path, line: index + 1, text: text.trim() }))
      .filter((entry) => pattern.test(entry.text)),
  )
}

describe("class names that draw nothing", () => {
  it("the scans see a planted example", () => {
    expect(BARE_ROUNDED.test('class="rounded px-1"')).toBe(true)
    expect(BARE_ROUNDED.test('class="px-1 rounded"')).toBe(true)
    expect(BARE_ROUNDED.test('class="rounded-sm px-1"')).toBe(false)
    expect(MONO_LOST.test('class="font-mono text-12-regular"')).toBe(true)
    expect(MONO_LOST.test('class="text-12-mono"')).toBe(false)
    expect(subjects.length).toBeGreaterThan(20)
  })

  it("no bare rounded", () => {
    expect(offenders(BARE_ROUNDED)).toEqual([])
  })

  it("no font-mono beaten by a text-NN-regular", () => {
    expect(offenders(MONO_LOST)).toEqual([])
  })
})
