import {
  clientSettings as theirClient,
  projectSettings as theirProject,
  serverSettings as theirServer,
} from "@/settings/search-catalog"
import { harnessUnbackedSetting, HIDDEN_SETTING_ROWS } from "./unbacked"

/**
 * Their settings search catalogue, less the pages this product hides
 * (unbacked.ts). Stands in for `settings/search-catalog.ts` (SUBSTITUTES in
 * web/vite.config.ts) and wraps it: their entries, filtered, so an upstream
 * entry added to a page that shows is searchable with no change here.
 *
 * Without it, searching "MCP" or "worktree" in Settings offered a result
 * that jumped to a page the navigation no longer lists.
 */
/**
 * Rows a patch moved to another page keep their search entry, retargeted:
 * colour scheme left the hidden Appearance page for General (P32-P33), so
 * its entry follows it rather than being filtered with the page.
 */
const MOVED_ROWS: Record<string, string> = { "settings-color-scheme": "general" }

const shown = <T extends { tab: string; target?: string }>(entries: T[]) =>
  entries
    .map((entry) => (entry.target && MOVED_ROWS[entry.target] ? { ...entry, tab: MOVED_ROWS[entry.target]! } : entry))
    .filter((entry) => !harnessUnbackedSetting(entry.tab) && !HIDDEN_SETTING_ROWS.has(entry.target ?? ""))

export const clientSettings = shown(theirClient)
export const serverSettings = shown(theirServer)
export const projectSettings = shown(theirProject)
