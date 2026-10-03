import { readdirSync, readFileSync } from "node:fs"
import { join, relative, resolve } from "node:path"
import ts from "typescript"
import { describe, expect, it } from "vitest"
import { UNBACKED_SETTINGS } from "./settings/unbacked"

/**
 * PROJECTS AND CHATS, NOTHING ELSE (the owner, 2026-09-22: "every chat is a
 * session; there are different projects where these chats take place - that's
 * the only difference. There shouldn't be infinite different workspaces").
 *
 * Every string this product's own code can put on screen - string literals,
 * template text and JSX text in web/src/harness and web/src/brand - is read
 * with the TypeScript parser, and none may say "workspace" or "worktree".
 * Code identifiers and comments are not strings, so they are free to; so are
 * module specifiers, object keys (their i18n keys are `settings.workspaces.*`),
 * key-shaped values with no space in them, and JSX attributes that are not
 * read by a person (class, data-*). The files are derived from the tree, not
 * listed, so a new surface is scanned the day it is added.
 */

const WEB = process.cwd()
const ROOTS = [resolve(WEB, "src", "harness"), resolve(WEB, "src", "brand")]
const BANNED = /\b(workspaces?|worktrees?)\b/i
/** JSX attributes a person reads (on hover, from a screen reader, in an empty field). */
const READ_ATTRIBUTES = new Set(["title", "aria-label", "placeholder", "alt", "label", "description"])
/**
 * Object properties whose values are written for the next engineer, never
 * rendered: session/unsupported.ts says WHY a command is switched off.
 */
const DEVELOPER_PROPERTIES = new Set(["why"])

function sources(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) return sources(path)
    if (!/\.tsx?$/.test(entry.name) || /\.test\.tsx?$/.test(entry.name)) return []
    return [path]
  })
}

function keyShaped(text: string) {
  return !/\s/.test(text) && (/[.:/_@-]/.test(text) || text === text.toLowerCase())
}

function propertyName(node: ts.Node): string | undefined {
  const parent = node.parent
  if (ts.isPropertyAssignment(parent) && parent.initializer === node) {
    const name = parent.name
    return ts.isIdentifier(name) || ts.isStringLiteral(name) ? name.text : undefined
  }
}

/** Whether a string literal node is code rather than copy. */
function isCode(node: ts.StringLiteral | ts.NoSubstitutionTemplateLiteral): boolean {
  const parent = node.parent
  if (ts.isImportDeclaration(parent) || ts.isExportDeclaration(parent) || ts.isExternalModuleReference(parent)) return true
  if (ts.isCallExpression(parent) && (parent.expression.kind === ts.SyntaxKind.ImportKeyword || /^vi\.(mock|doMock)$/.test(parent.expression.getText())))
    return true
  if (ts.isImportTypeNode(parent.parent)) return true
  if (ts.isLiteralTypeNode(parent)) return true
  if (ts.isPropertyAssignment(parent) && parent.name === node) return true
  if (ts.isElementAccessExpression(parent) && parent.argumentExpression === node) return true
  if (ts.isJsxAttribute(parent)) return !READ_ATTRIBUTES.has(parent.name.getText())
  if (DEVELOPER_PROPERTIES.has(propertyName(node) ?? "")) return true
  return keyShaped(node.text)
}

function userFacingStrings(file: string, text: string): { line: number; text: string }[] {
  const source = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, file.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS)
  const found: { line: number; text: string }[] = []
  const add = (node: ts.Node, value: string) =>
    found.push({ line: source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1, text: value.trim() })
  const visit = (node: ts.Node) => {
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
      if (!isCode(node)) add(node, node.text)
    } else if (ts.isTemplateHead(node) || ts.isTemplateMiddle(node) || ts.isTemplateTail(node)) {
      add(node, node.text)
    } else if (ts.isJsxText(node)) {
      if (node.text.trim()) add(node, node.text)
    }
    ts.forEachChild(node, visit)
  }
  visit(source)
  return found
}

describe("the harness speaks of projects and chats", () => {
  const files = ROOTS.flatMap(sources)

  it("scans a real tree (a scan of nothing would pass)", () => {
    expect(files.length).toBeGreaterThan(50)
    expect(files.some((file) => file.endsWith(join("rail", "rail.tsx")))).toBe(true)
    expect(files.some((file) => file.endsWith(join("brand", "strings.ts")))).toBe(true)
  })

  it("finds a planted user-facing workspace, and passes the code-shaped ones", () => {
    const planted = [
      'import { x } from "@/workspaces/location"',
      'const keys = { "settings.workspaces.title": "Projects" }',
      'const id = "new-session/workspace/selector.tsx"',
      'const rules = { why: "no worktrees here" }',
      'const a = <div class="workspace-row" title="Open the worktree">New workspace</div>',
      'const b = `Moving to ${"x"} worktree`',
      'const c = "Choose a Workspace"',
    ].join("\n")
    const hits = userFacingStrings("planted.tsx", planted).filter((one) => BANNED.test(one.text))
    expect(hits.map((one) => one.text)).toEqual(["Open the worktree", "New workspace", "worktree", "Choose a Workspace"])
  })

  it("no string on screen says workspace or worktree", () => {
    const offending = files.flatMap((file) =>
      userFacingStrings(file, readFileSync(file, "utf-8"))
        .filter((one) => BANNED.test(one.text))
        .map((one) => `${relative(WEB, file)}:${one.line}: ${one.text}`),
    )
    expect(offending).toEqual([])
  })
})

/**
 * THE SETTINGS SCREENS NAME THIS PRODUCT (the owner, 2026-09-23: "About says
 * OpenCode, anomaly, etc. ... make sure it's not using anything OpenCode").
 *
 * The subject set is derived, not listed: every i18n key their settings files
 * mention, plus every `command.*` key (Settings > Shortcuts lists command
 * titles), resolved the way the window resolves it - brand/strings.ts's value
 * if it sets one, else theirs with "OpenCode" renamed (strings.ts RENAMED). A
 * key only a hidden page mentions is not on screen; the hidden pages are the
 * ones unbacked.ts names, each mapped to its files below, and a page it adds
 * without a mapping fails the test. The harness's own settings pages are
 * scanned too; they may name OpenCode once, in About's credit line.
 */
const NOT_OURS = /opencode|anomaly/i
const HIDDEN_PAGE_FILES: Record<string, string[]> = {
  workspaces: ["settings/workspaces/workspaces.tsx", "settings/workspaces/queries.ts"],
  extensions: ["settings/providers/extensions.tsx", "settings/workspaces/project-extensions.tsx", "settings/workspaces/project-lsp.ts"],
  servers: ["settings/servers/"],
  pairing: ["settings/pairing/"],
  appearance: ["settings/appearance/"],
  about: ["settings/about/"],
  providers: ["settings/providers/providers.tsx"],
  models: ["settings/models/"],
}
/** Blocks drawn hidden inside a page that shows, by key prefix, with the patch that hides them. */
const HIDDEN_BLOCKS: Record<string, string> = {
  "project.settings.worktree.": "Settings > Projects > a project: the worktree startup script, display:none by P29",
}
const CREDIT_LINE = "Interface derived from OpenCode (MIT)"

describe("the settings screens name this product", () => {
  const VENDORED = resolve(WEB, "..", "vendor", "opencode", "packages", "app", "src")
  const entry = /^\s+"([\w.]+)":\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')/gm
  const theirs = new Map(
    [...readFileSync(resolve(VENDORED, "runtime", "i18n", "en.ts"), "utf-8").matchAll(entry)].map((match) => [
      match[1],
      match[2] ?? match[3] ?? "",
    ]),
  )
  const ours = new Map(
    [...readFileSync(resolve(WEB, "src", "brand", "strings.ts"), "utf-8").matchAll(entry)].map((match) => [
      match[1],
      match[2] ?? match[3] ?? "",
    ]),
  )
  const onScreen = (key: string) => ours.get(key) ?? (theirs.get(key) ?? "").replace(/OpenCode/g, "ML Harness")

  const settingsFiles = sources(resolve(VENDORED, "settings")).map((file) => relative(VENDORED, file).split("\\").join("/"))
  const hidden = (file: string) => Object.values(HIDDEN_PAGE_FILES).flat().some((prefix) => file.startsWith(prefix))
  const keysIn = (files: string[]) => {
    const found = new Set<string>()
    for (const file of files)
      for (const match of readFileSync(resolve(VENDORED, file), "utf-8").matchAll(/["'`]([\w.]+)["'`]/g))
        if (theirs.has(match[1])) found.add(match[1])
    return found
  }
  const visible = keysIn(settingsFiles.filter((file) => !hidden(file)))
  for (const key of theirs.keys()) if (key.startsWith("command.")) visible.add(key)

  it("reads their settings and their dictionary (a scan of nothing would pass)", () => {
    expect(theirs.size).toBeGreaterThan(1000)
    expect(settingsFiles).toContain("settings/general/general.tsx")
    expect(visible.has("settings.general.row.language.description")).toBe(true)
    expect(visible.has("command.permissions.autoaccept.enable")).toBe(true)
  })

  it("maps every hidden page to its files, and those files exist", () => {
    expect(Object.keys(HIDDEN_PAGE_FILES).sort()).toEqual([...UNBACKED_SETTINGS].sort())
    for (const prefix of Object.values(HIDDEN_PAGE_FILES).flat())
      expect(settingsFiles.some((file) => file.startsWith(prefix)), prefix).toBe(true)
  })

  it("catches their name where it would show, and lets a hidden page keep it", () => {
    // Their raw copy says it: the check has something to find.
    expect(theirs.get("settings.extensions.manageConfig")).toMatch(NOT_OURS)
    expect(theirs.get("settings.general.row.language.description")).toMatch(NOT_OURS)
    // The rename reaches a visible row...
    expect(onScreen("settings.general.row.language.description")).toBe("Change the display language for ML Harness")
    // ...and their About's colophon is mentioned only by the hidden About.
    const aboutOnly = [...keysIn(settingsFiles.filter((file) => file.startsWith("settings/about/")))].filter(
      (key) => NOT_OURS.test(theirs.get(key) ?? "") && !visible.has(key),
    )
    expect(aboutOnly).toContain("settings.about.copyright")
  })

  it("no visible settings string says OpenCode, opencode.json or Anomaly", () => {
    const offending = [...visible]
      .filter((key) => NOT_OURS.test(onScreen(key)))
      .filter((key) => !Object.keys(HIDDEN_BLOCKS).some((prefix) => key.startsWith(prefix)))
      .map((key) => `${key}: ${onScreen(key)}`)
    expect(offending).toEqual([])
    // Each hidden block is hidden where their page draws it, and is used.
    expect(readFileSync(resolve(VENDORED, "settings", "workspaces", "project.tsx"), "utf-8")).toContain(
      '<div class="project-settings-startup" style={{ display: "none" }}>',
    )
    for (const prefix of Object.keys(HIDDEN_BLOCKS)) expect([...visible].some((key) => key.startsWith(prefix)), prefix).toBe(true)
  })

  it("the harness's own settings pages name it once, in About's credit", () => {
    const pages = sources(resolve(WEB, "src", "harness", "settings"))
    expect(pages.some((file) => file.endsWith("about.tsx"))).toBe(true)
    const found = pages.flatMap((file) =>
      userFacingStrings(file, readFileSync(file, "utf-8"))
        .filter((one) => NOT_OURS.test(one.text))
        .map((one) => one.text),
    )
    expect(found).toEqual([CREDIT_LINE])
  })
})
