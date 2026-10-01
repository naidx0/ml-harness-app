/**
 * Stands in for their `session/summary/server-panel.tsx` (SUBSTITUTES in
 * web/vite.config.ts): the MCP, Plugins, Skills and LSP rows their session
 * summary and new-chat summary draw under the project card. The harness has
 * none of the four - the engine answers their MCP and plugin calls empty, and
 * there is no language server - so every row could only say "none" or offer
 * a config link to an opencode.json that does not exist here.
 *
 * Same export, same props, draws nothing.
 */
export function SessionServerPanel(_props: { directory: string; shown: boolean; mobile?: boolean; mcp?: unknown }) {
  return null
}
