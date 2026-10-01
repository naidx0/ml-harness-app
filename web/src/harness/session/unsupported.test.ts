import { readdirSync, readFileSync, statSync } from "node:fs"
import { join, resolve } from "node:path"
import { describe, expect, it } from "vitest"
import { SUPPORTED_COMMANDS, UNSUPPORTED_COMMANDS, unsupportedCommandOverrides } from "./unsupported"

/**
 * The subject set is DERIVED: every static command id their app registers,
 * read from the files that call `register(`. A command a vendored update adds
 * fails here until someone decides whether it works against the harness.
 */

// Vitest runs from web/.
const app = resolve(process.cwd(), "..", "vendor", "opencode", "packages", "app", "src")

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) {
      if (name !== "i18n") walk(path, out)
    } else if (/\.tsx?$/.test(name) && !/\.(test|spec|story|stories)\.tsx?$/.test(name)) out.push(path)
  }
  return out
}

const COMMAND_ID = /\bid: "([a-z][A-Za-z]*(?:\.[A-Za-z]+)+)"/g

function commandIds(source: string) {
  return [...source.matchAll(COMMAND_ID)].map((match) => match[1]!)
}

const registering = walk(app)
  .map((path) => readFileSync(path, "utf-8"))
  .filter((source) => source.includes("register("))
const theirs = [...new Set(registering.flatMap(commandIds))].sort()

describe("their commands, each classified", () => {
  it("the scan reads command ids and nothing else", () => {
    expect(commandIds('command.register("x", () => [{ id: "terminal.toggle", title: "T" }])')).toEqual([
      "terminal.toggle",
    ])
    expect(commandIds('{ id: "today" as const }')).toEqual([])
    // Known commands from three different files, so a zero means something.
    expect(theirs).toEqual(expect.arrayContaining(["terminal.toggle", "session.fork", "model.choose", "tab.new"]))
    expect(theirs.length).toBeGreaterThan(40)
  })

  it("every command id they register is either supported or overridden, never both", () => {
    const unsupported = Object.keys(UNSUPPORTED_COMMANDS)
    const both = unsupported.filter((id) => SUPPORTED_COMMANDS.includes(id))
    const unclassified = theirs.filter((id) => !SUPPORTED_COMMANDS.includes(id) && !unsupported.includes(id))
    expect(both).toEqual([])
    expect(unclassified).toEqual([])
  })

  it("names no command they do not register (a stale entry is a wrong claim)", () => {
    const stale = [...Object.keys(UNSUPPORTED_COMMANDS), ...SUPPORTED_COMMANDS].filter((id) => !theirs.includes(id))
    expect(stale).toEqual([])
  })

  it("each override is the same id, disabled, hidden, with no keybind and a reason on file", () => {
    for (const entry of unsupportedCommandOverrides()) {
      expect(entry).toEqual({ id: entry.id, title: expect.any(String), disabled: true, hidden: true })
      expect(UNSUPPORTED_COMMANDS[entry.id]!.why.length).toBeGreaterThan(5)
    }
    expect(unsupportedCommandOverrides().map((entry) => entry.id)).toEqual(Object.keys(UNSUPPORTED_COMMANDS))
  })

  it("the session mount and the new-chat card both register the overrides", () => {
    const here = resolve(process.cwd(), "src", "harness")
    for (const file of [join(here, "session", "mount.tsx"), join(here, "start", "start.tsx")]) {
      expect(readFileSync(file, "utf-8")).toContain("...unsupportedCommandOverrides()")
    }
  })
})
