import { dict as theirs } from "@/runtime/i18n/en"
// Their UI package's strings, rewritten at import (see the file for why).
import "./ui-strings"

/**
 * Their English strings, with this product's name and claims.
 *
 * Substituted for `runtime/i18n/en.ts` by resolved path (web/vite.config.ts),
 * so every import of it - including the other locales, which spread English
 * as their fallback - reads this. The import above reaches THEIR file, because
 * the substitution skips imports made from the replacement.
 *
 * Three kinds of change, and nothing else:
 *
 *   - THE PRODUCT NAME. Their copy says "OpenCode" 75 times. Most of those
 *     sit on surfaces this product never mounts (WSL, SSH, pairing), but the
 *     name is replaced everywhere so a newly reachable surface cannot leak it.
 *   - CLAIMS THIS PRODUCT DOES NOT MAKE. "Connect to 75+ providers" and the
 *     Claude/GPT/Gemini lists describe their catalogue, not the harness's.
 *   - THE COLOPHON. Their About page credits their authors and asserts their
 *     trademark. On this product it credits them as the interface it is built
 *     on - the MIT notice itself travels in THIRD-PARTY-NOTICES.txt.
 */

const RENAMED = Object.fromEntries(
  Object.entries(theirs).map(([key, value]) => [
    key,
    typeof value === "string" ? value.replace(/OpenCode/g, "ML Harness") : value,
  ]),
) as typeof theirs

export const dict = {
  ...RENAMED,
  "home.providerTip": "Pick a model on this computer, or connect one with an API key",
  "sidebar.gettingStarted.line2": "Pick a model on this computer, or connect one with an API key.",
  "settings.about.description": "ML Harness, a local workbench for building and measuring models",
  "settings.about.website": "Interface built on OpenCode (MIT)",
  "settings.about.trademark": "OpenCode is a trademark of Anomaly Innovations, Inc., named here only to credit the interface.",
  "settings.about.copyright": "Interface © Anomaly Innovations, Inc., under the MIT License",
  "settings.about.tagline": "Your machine, your models, measured",
  "settings.about.typeset": "Typeset in IBM Plex Sans and IBM Plex Mono",
  "error.page.report.prefix": "Copy the error above to include it in a report.",
  "error.page.report.discord": "",
  "prompt.action.attachFile": "Attach files to this message",
  // The slash menu's words: their agents are this product's modes, and its
  // connect dialog is the harness's presets, not their hosted service.
  "command.provider.connect.description": "Connect a model: one on this computer, or an API key",
  "command.agent.cycle": "Cycle mode",
  "command.agent.cycle.description": "Switch to the next mode",
  "command.agent.cycle.reverse": "Cycle mode backwards",
  "command.agent.cycle.reverse.description": "Switch to the previous mode",
  "command.context.addSelection": "Add the selected lines as context",
  // PROJECTS AND CHATS (the owner, 2026-09-22: "every chat is a session;
  // there are different projects where these chats take place - that's the
  // only difference"). Their words for the same things, where a person reads
  // them: the palette, the home list, the new-chat line under the composer.
  // Their worktree copy that is still reachable says "project"; the rest sits
  // on surfaces the harness hides (brand/strings.test.ts classifies each key).
  "command.category.session": "Chat",
  "command.category.workspace": "Project",
  "command.session.new": "New chat",
  "command.session.compact": "Compact chat",
  "command.session.compact.description": "Summarise the chat to reduce context size",
  "command.session.export": "Export chat",
  "command.session.export.description": "Export the full chat transcript as JSON",
  "command.session.copyID": "Copy chat ID",
  "command.session.location.cycle": "Cycle location",
  "home.sessions.search.placeholder": "Search chats",
  "home.sessions.search.placeholder.scoped": "Search chats in {{scope}}",
  "home.sessions.search.sessions": "Chats",
  "home.sessions.search.noResults": "No chats found for {{query}}",
  "home.sessions.empty.description": "Start a chat to get going",
  "home.workspaceTip": "Every chat belongs to a project",
  "sidebar.nav.projectsAndSessions": "Projects and chats",
  "sidebar.project.recentSessions": "Recent chats",
  "sidebar.project.viewAllSessions": "View all chats",
  // Under the new-chat composer, beside the project: a project folder that is
  // not a git repository. "No Git" read as something missing; it is not.
  "session.new.git.none": "Local folder",
  "session.new.workspace.trigger.tooltip": "Choose the project for this chat",
  "settings.workspaces.default.title": "New chats",
  "settings.workspaces.default.description": "Every new chat starts in its project's folder",
  "settings.projects.description": "Each project holds its own chats",
  // Settings > Preferences said "preferences and theme"; the theme went with
  // their Appearance page (the owner, 2026-09-23: "we only have one appearance").
  "settings.preferences.description": "How this window behaves",
  // Its sounds are queued for hiding (harness/settings/PENDING-PATCHES.md S8):
  // their audio files are not vendored, so none would play.
  "settings.notifications.description": "Choose when this window notifies you",
} as typeof theirs

export default dict
