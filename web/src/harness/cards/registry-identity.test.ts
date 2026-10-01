import { describe, expect, it } from "vitest"

/**
 * ONE REGISTRY, OR THE CARDS ARE INVISIBLE.
 *
 * Their renderer reads the registry through a RELATIVE import
 * (`../tools/tool-renderer` from message/current-message.tsx); the harness
 * registers through the `@session-ui-src` alias because the module is not in
 * session-ui's exports map. If Vite resolved those to two module ids there
 * would be two `state` records, and every harness card would be registered
 * into the one nobody reads - with no error anywhere. This asks the resolver
 * the question directly: import both spellings and check they are the same
 * object, then register through ours and read back through theirs.
 *
 * THE TIMEOUT IS THE IMPORT, NOT THE CHECK. The first import pulls their whole
 * renderer graph through Vite's transform; on a cold cache under a parallel
 * build it took just over vitest's 5 s default and failed with a timeout -
 * twice, both times passing alone. The gate runs vitest cold, so the budget
 * is sized for that rather than left as a flake.
 */
describe("the tool registry the harness fills is the one their renderer reads", { timeout: 30_000 }, () => {
  it("resolves the alias and the vendored relative path to one module", async () => {
    const ours = await import("@session-ui-src/tools/tool-renderer")
    const theirs = await import("../../../../vendor/opencode/packages/session-ui/src/tools/tool-renderer")
    expect(ours.ToolRegistry).toBe(theirs.ToolRegistry)
    expect(ours.getTool).toBe(theirs.getTool)
  })

  it("can see two copies when there are two (the positive control for the check above)", async () => {
    // A query string is a different module id to Vite: a deliberate second
    // instance. If `toBe` could not tell these apart, the identity check
    // above would pass whatever the resolver did.
    const ours = await import("@session-ui-src/tools/tool-renderer")
    // @ts-expect-error - a query-suffixed specifier has no declaration, on purpose.
    const copy = await import("@session-ui-src/tools/tool-renderer?second-instance")
    expect(copy.ToolRegistry).not.toBe(ours.ToolRegistry)
  })

  it("a card registered by register.ts is found through their spelling", async () => {
    const { registerHarnessCards } = await import("./register")
    const { HarnessResultCard } = await import("./card")
    const { HARNESS_CARD_TOOL_NAMES } = await import("./kinds")
    registerHarnessCards()
    const theirs = await import("../../../../vendor/opencode/packages/session-ui/src/tools/tool-renderer")
    for (const name of HARNESS_CARD_TOOL_NAMES) expect(theirs.ToolRegistry.render(name)).toBe(HarnessResultCard)
    // And a tool with no card keeps their default: nothing registered.
    expect(theirs.ToolRegistry.render("no_such_harness_tool")).toBeUndefined()
  })
})
