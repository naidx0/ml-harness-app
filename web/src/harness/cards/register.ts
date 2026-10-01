import { ToolRegistry } from "@session-ui-src/tools/tool-renderer"
import { HarnessResultCard } from "./card"
import { HARNESS_CARD_TOOL_NAMES } from "./kinds"

/**
 * Put the harness cards into THEIR tool registry, before anything renders.
 *
 * `ToolDisplay` asks `ToolRegistry.render(tool)` once, inside a memo that
 * reads nothing reactive from the registry (tool-renderer.tsx), so a card
 * registered after a tool part mounted would never be picked up by that part.
 * This module registers on import, and `entry.tsx` imports it before
 * `render()`.
 *
 * The registry is reached through `@session-ui-src`, because
 * `tools/tool-renderer` is the one module session-ui's exports map leaves
 * out. That alias and their own relative import (`../tools/tool-renderer`
 * in message/current-message.tsx) must land on ONE module, or this would
 * fill a second registry nobody reads; `registry-identity.test.ts` checks it.
 */

export function registerHarnessCards() {
  for (const name of HARNESS_CARD_TOOL_NAMES) ToolRegistry.register({ name, render: HarnessResultCard })
}

registerHarnessCards()
