/**
 * THEIR COMMANDS THAT DO NOTHING HERE, and why - so the palette and the slash
 * menu offer only what works.
 *
 * Their app registers commands for surfaces the harness does not have. Each
 * one below is overridden with a disabled, hidden entry of the same id from
 * the session mount and the new-chat card: registrations made later win on a
 * shared id (shell/commands/command.tsx `addCommandRegistration` puts the
 * newest first and `registered` keeps the first of each id), a disabled
 * command is left out of the keymap, and their slash menu lists only enabled
 * commands (composer/model.ts `slashCommands`). An entry with no keybind also
 * frees the key it used to hold.
 *
 * "Not served" means the facade (app/facade/router.py) has no route for the
 * call the command makes, so the command could only fail.
 *
 * Every static command id in their app is in exactly one of the two lists
 * here; unsupported.test.ts derives the ids from their source and fails on one
 * nobody classified, so a vendored update cannot add a dead command silently.
 */
export const UNSUPPORTED_COMMANDS: Readonly<Record<string, { title: string; why: string }>> = {
  // The harness has no terminal surface: the engine answers `pty.*` empty and
  // the emulator is a stub that throws.
  "terminal.toggle": { title: "Terminal", why: "no terminal surface (/terminal, ctrl+`)" },
  "terminal.new": { title: "New terminal", why: "no terminal surface" },
  "terminal.close": { title: "Close terminal", why: "no terminal surface" },
  // Revert: `/api/session/{id}/revert`, `/revert/stage` are not served.
  "session.undo": { title: "Undo", why: "revert is not served (/undo)" },
  "session.redo": { title: "Redo", why: "revert is not served (/redo)" },
  "session.fork": { title: "Fork", why: "`/api/session/{id}/fork` is not served (/fork)" },
  "session.btw": { title: "Side question", why: "`/api/session/{id}/generate` is not served (/btw)" },
  "session.background": { title: "Move to background", why: "`/api/session/{id}/background` is not served" },
  "prompt.mode.shell": { title: "Shell mode", why: "`/api/session/{id}/shell` is not served; a shell turn could only fail" },
  "mcp.toggle": { title: "MCP servers", why: "the harness runs no MCP servers (/mcp)" },
  "browser.open": { title: "Open browser", why: "no browser pane" },
  "browser.reload": { title: "Reload browser", why: "no browser pane" },
  "session.location.cycle": { title: "Cycle location", why: "no worktrees: the facade lists no sandboxes (project_info `sandboxes: []`)" },
  "server.ssh.add": { title: "Add SSH server", why: "no SSH servers; the window talks to its own engine" },
  "server.pair": { title: "Pair a device", why: "no device pairing" },
  "app.checkForUpdates": { title: "Check for updates", why: "their updater; the harness ships through its own shell" },
  "logs.export": { title: "Export logs", why: "their debug-log export; the harness shell has none" },
}

/** Their commands that work against the harness, kept as they are. */
export const SUPPORTED_COMMANDS: readonly string[] = [
  "agent.cycle",
  "agent.cycle.reverse",
  "command.palette",
  "common.goBack",
  "common.goForward",
  "context.addSelection",
  "debugBar.toggle",
  "file.attach",
  "file.close",
  "file.open",
  "fileTree.toggle",
  "home.sessions.search.focus",
  "home.toggle",
  "input.focus",
  "message.next",
  "message.previous",
  "model.choose",
  "model.variant.cycle",
  "permissions.autoaccept",
  "project.copyID",
  "project.select",
  "prompt.mode.normal",
  "provider.connect",
  "review.toggle",
  "session.compact",
  "session.copyID",
  "session.export",
  "session.new",
  "session.search",
  "session.summary.toggle",
  "settings.open",
  "settings.search.focus",
  "tab.close",
  "tab.new",
  "tab.reopenClosed",
]

/** The overriding entries: same id, disabled, hidden, no keybind. */
export function unsupportedCommandOverrides() {
  return Object.entries(UNSUPPORTED_COMMANDS).map(([id, { title }]) => ({
    id,
    title,
    disabled: true,
    hidden: true,
  }))
}
