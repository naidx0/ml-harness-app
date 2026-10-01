/**
 * Their settings pages this product has no backing for, hidden wherever
 * their interface lists them: the root navigation (P19, `harnessFilterSettings`
 * in slots.tsx), a project's own settings tabs (P24), and settings search
 * (search-catalog.ts, substituted), which would otherwise still offer "MCP
 * servers" and jump to a page the navigation no longer shows.
 *
 *   workspaces - "Worktrees": the harness has no worktrees; every call on the
 *                page is answered with a refusal.
 *   extensions - MCP servers, plugins, skills and (per project) language
 *                servers, "managed in opencode.json": none of it exists here.
 *   servers    - connecting this window to other servers, the opposite of the
 *                one-package design.
 *   pairing    - pairing a phone with this machine; the shell has no pairing
 *                endpoint (their tab already hides without `platform.pair`,
 *                and search listed it regardless).
 *
 * The owner, 2026-09-23: "Appearance: we only have one appearance ... About
 * says OpenCode, anomaly, etc. - get rid of that About."
 *
 *   appearance - their theme picker (the harness registers one theme,
 *                brand/apply-theme.tsx, and brand/identity.css pins surfaces
 *                and ink over any other), a UI font the identity already sets
 *                (harness/root.tsx v2), a code font, and a terminal font for
 *                a terminal that does not exist. Its one row with a real
 *                effect, light or dark, is queued for General
 *                (PENDING-PATCHES.md, color-scheme.tsx).
 *   about      - their colophon: wordmark, contributors, trademark, website.
 *                Replaced by the harness's own About (about.tsx).
 *
 * Hidden, not deleted: their pages stay byte-identical.
 */
export const UNBACKED_SETTINGS: ReadonlySet<string> = new Set([
  "workspaces",
  "extensions",
  "servers",
  "pairing",
  "appearance",
  "about",
])

export function harnessUnbackedSetting(tab: string): boolean {
  return UNBACKED_SETTINGS.has(tab)
}

/**
 * Single rows removed from a page that otherwise shows, by the `data-action`
 * their search entry jumps to - so search does not offer a row the page no
 * longer draws (scripts/vendor_opencode.py):
 *
 *   settings-workspace-destination - "Default environment", worktree or not
 *                                    for a new chat (P27).
 *   settings-terminal-placement    - where a terminal opens; there is no
 *                                    terminal (P26).
 *
 * QUEUED (the owner, 2026-09-23: "make sure all these things work if we
 * actually need them"). Each row below was checked against what reads it and
 * does nothing here, or does harm; the patch that stops the page drawing it is
 * written out in PENDING-PATCHES.md (vendor_opencode.py belongs to another
 * lane). Search stops offering them now; the page stops drawing them when the
 * patches land.
 *
 *   settings-language              - every other locale is their
 *                                    translation: "OpenCode" by name and none
 *                                    of brand/strings.ts's words.
 *   settings-show-custom-agents    - the agents ARE the modes; off forces
 *                                    Build and hides Plan (harness/root.tsx v1).
 *   settings-follow-up-behavior    - queue and steer are one thing here: the
 *                                    facade runs every follow-up after the
 *                                    running turn (router.py session_prompt).
 *   settings-pinch-zoom            - the shell's platform has no pinch-zoom
 *                                    getter or setter; the switch moves alone.
 *   settings-release-notes         - their "What's New" reads opencode.ai's
 *                                    changelog, another product's releases.
 *   settings-check-updates         - no updater on this platform; the button
 *                                    is always disabled.
 *   settings-notifications-permissions,
 *   settings-sounds-permissions    - nothing in their app reads either value.
 *   settings-sounds-agent,
 *   settings-sounds-errors         - their sound files are in a package not
 *                                    vendored; every sound resolves to none.
 *
 * NOT hidden: settings-tab-layout. Horizontal tabs do remove the sidebar the
 * rail lives in, and that is the point - the owner asked for an easy way to
 * switch between the rail and tabs across the top (2026-09-23), so the rail
 * lane bound Ctrl+Shift+H to it and this row stays as the same switch.
 */
export const HIDDEN_SETTING_ROWS: ReadonlySet<string> = new Set([
  "settings-workspace-destination",
  "settings-terminal-placement",
  "settings-language",
  "settings-show-custom-agents",
  "settings-follow-up-behavior",
  "settings-pinch-zoom",
  "settings-release-notes",
  "settings-check-updates",
  "settings-notifications-permissions",
  "settings-sounds-permissions",
  "settings-sounds-agent",
  "settings-sounds-errors",
])
