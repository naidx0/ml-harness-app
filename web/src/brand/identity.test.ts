import { readdirSync, readFileSync, statSync } from "node:fs"
import { join, resolve } from "node:path"
import { describe, expect, it } from "vitest"

/**
 * identity.css styles THEIR markup by its data attributes, so every rule in
 * it is a bet that the attribute still exists. A vendored update that renames
 * a slot turns the rule into a no-op with nothing red: the stylesheet builds,
 * the suite passes, and the rail grows its tab list back.
 *
 * The subject set is DERIVED from the stylesheet itself: every
 * `data-slot="x"` / `data-component="x"` / `data-action="x"` it names must be
 * spelled, as the string "x", in some source that renders markup - their app
 * and session UI, their UI package, or ours.
 */

// Vitest runs from web/.
const web = process.cwd()
const css = readFileSync(resolve(web, "src", "brand", "identity.css"), "utf-8")
const ROOTS = [
  resolve(web, "..", "vendor", "opencode", "packages"),
  resolve(web, "..", "node_modules", "@opencode", "ui", "src"),
  resolve(web, "src"),
]

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name.startsWith(".")) continue
    const path = join(dir, name)
    if (statSync(path).isDirectory()) walk(path, out)
    else if (/\.(tsx|ts)$/.test(name) && !/\.test\.tsx?$/.test(name)) out.push(path)
  }
  return out
}

const sources = ROOTS.flatMap((root) => walk(root))
const corpus = sources.map((path) => readFileSync(path, "utf-8")).join("\n")

const ATTRIBUTE = /\[data-(slot|component|action)="([^"]+)"\]/g

function named(stylesheet: string) {
  return [...new Set([...stylesheet.matchAll(ATTRIBUTE)].map((match) => match[2]!))]
}

function missing(stylesheet: string) {
  return named(stylesheet).filter((value) => !corpus.includes(`"${value}"`))
}

describe("identity.css names only attributes that something renders", () => {
  it("the scan finds a planted slot nobody renders, and passes a real one", () => {
    expect(sources.length).toBeGreaterThan(500)
    expect(missing('[data-slot="vertical-tabs"] {}')).toEqual([])
    expect(missing('[data-slot="no-such-slot-anywhere-7f3a"] {}')).toEqual(["no-such-slot-anywhere-7f3a"])
    expect(named(css).length).toBeGreaterThan(5)
  })

  it("every attribute in the stylesheet exists in a source", () => {
    expect(missing(css)).toEqual([])
  })
})

describe("the + menu's hidden shell entry rests on their menu's shape", () => {
  it("the menu's own class exists, and shell mode is its last item", () => {
    const editor = readFileSync(
      resolve(web, "..", "vendor", "opencode", "packages", "app", "src", "composer", "editor", "editor.tsx"),
      "utf-8",
    )
    const klass = "[data-slot=menu-v2-item-shortcut]]:w-5"
    expect(css).toContain(`[class*="${klass}"] > [role="menuitem"]:last-child`)
    const start = editor.indexOf("export function ComposerEditorAddMenu")
    const end = editor.indexOf("</Menu.Content>", start)
    const menu = editor.slice(start, end)
    // Exactly one menu carries the class, and this is it.
    expect(editor.split(klass).length - 1).toBe(1)
    expect(menu).toContain(klass)
    const items = [...menu.matchAll(/<Menu\.Item onSelect=\{props\.(\w+)\}/g)].map((match) => match[1])
    expect(items).toEqual(["onAttach", "onCommands", "onContext", "onShell"])
  })
})

describe("the display face is set only in cuts that are loaded", () => {
  // A rule asking for a weight or style entry.tsx does not load renders in a
  // synthesised face (faux bold, slanted roman), which reads as a different font.
  // The subject set is every place that asks for the display face: the rules
  // in identity.css, and the SVG text in the brand's marks (wordmark, logo).
  const PACKAGE = "sora"
  const entry = readFileSync(resolve(web, "src", "entry.tsx"), "utf-8")
  const brand = resolve(web, "src", "brand")
  const marks = readdirSync(brand)
    .filter((name) => name.endsWith(".tsx"))
    .map((name) => readFileSync(join(brand, name), "utf-8"))

  type Ask = { weight: string; italic: boolean }
  function asks(stylesheet: string, sources: string[]): Ask[] {
    const rules = [...stylesheet.matchAll(/\{([^{}]*var\(--font-family-display\)[^{}]*)\}/g)].map((match) => ({
      weight: /font-weight:\s*(\d+)/.exec(match[1]!)?.[1] ?? "400",
      italic: /font-style:\s*italic/.test(match[1]!),
    }))
    const texts = sources.flatMap((source) =>
      [...source.matchAll(/<text\b((?:[^>]|=>)*?--font-family-display(?:[^>]|=>)*?)>/g)].map((match) => ({
        weight: /font-weight="(\d+)"/.exec(match[1]!)?.[1] ?? "400",
        italic: /font-style="italic"/.test(match[1]!),
      })),
    )
    return [...rules, ...texts]
  }
  function unloaded(found: Ask[], imports: string) {
    return found
      .map((ask) => `@fontsource/${PACKAGE}/${ask.weight}${ask.italic ? "-italic" : ""}.css`)
      .filter((path) => !imports.includes(`import "${path}"`))
  }

  it("the scan finds a planted unloaded cut, and passes a loaded one", () => {
    const planted = asks("a { font-family: var(--font-family-display); font-weight: 700; }", [
      '<text style={{ "font-family": "var(--font-family-display)" }} font-weight="300">x</text>',
    ])
    expect(unloaded(planted, entry)).toEqual(["@fontsource/sora/700.css", "@fontsource/sora/300.css"])
    expect(unloaded(asks("a { font-family: var(--font-family-display); font-weight: 600; }", []), entry)).toEqual([])
  })

  it("finds the rules and the marks that set the face", () => {
    const found = asks(css, marks)
    expect(found.length).toBeGreaterThanOrEqual(6)
    // The title card's name and voice are two of them, at 600 and 400.
    expect(asks("", marks).map((ask) => ask.weight)).toEqual(expect.arrayContaining(["600", "400"]))
  })

  it("every weight and style asked for is imported", () => {
    expect(unloaded(asks(css, marks), entry)).toEqual([])
  })
})

describe("the display face is a clean grotesque, set plainly", () => {
  // The owner, 2026-09-22: "This kind of Roman old style, and a little too
  // spaced between the words; that needs a lot of fixing ... clean fonts like
  // Sora, or Neue Montreal, Aktiv Grotesk, Apfel Grotezk."
  const entry = readFileSync(resolve(web, "src", "entry.tsx"), "utf-8")
  const brand = resolve(web, "src", "brand")
  const marks = readdirSync(brand)
    .filter((name) => name.endsWith(".tsx"))
    .map((name) => readFileSync(join(brand, name), "utf-8"))
    .join("\n")

  it("the stack names his faces first and ships Sora behind them", () => {
    const stack = /--font-family-display:\s*([^;]+);/.exec(css)?.[1]?.replace(/\s+/g, " ")
    expect(stack).toBe(
      '"Neue Montreal", "Aktiv Grotesk", "Apfel Grotezk", "Sora", "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif',
    )
  })

  it("the retired faces are gone from the stylesheet, the marks and the imports", () => {
    for (const source of [css, marks, entry]) {
      expect(source).not.toMatch(/Marcellus|Cormorant|font-family-inscription|font-family-voice/)
    }
  })

  it("nothing is spaced out or set in capitals", () => {
    // Positive control: the scan sees the old inscription's treatment.
    const wide = /letter-spacing(?::\s*|=")0?\.(?:[1-9]|0[5-9])\d*em|text-transform:\s*uppercase/
    expect("a { letter-spacing: 0.18em; }").toMatch(wide)
    expect('<text letter-spacing="0.08em">').toMatch(wide)
    expect(css).not.toMatch(wide)
    expect(marks).not.toMatch(wide)
  })
})

describe("RAIL ONLY rests on the portal's order", () => {
  it("their vertical tab strip follows the harness rail inside the sidebar portal", () => {
    // The hiding rule is `harness-rail ~ div:has(vertical-tabs)`: a general
    // sibling combinator, so the rail must come BEFORE the strip's wrapper.
    const titlebar = readFileSync(
      resolve(web, "..", "vendor", "opencode", "packages", "app", "src", "shell", "titlebar", "titlebar.tsx"),
      "utf-8",
    )
    const rail = titlebar.indexOf("<HarnessRail />")
    const strip = titlebar.indexOf('orientation="vertical"', rail)
    expect(rail).toBeGreaterThan(-1)
    expect(strip).toBeGreaterThan(rail)
    expect(css).toContain('[data-component="harness-rail"] ~ div:has([data-slot="vertical-tabs"])')
  })
})
