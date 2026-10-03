"""Re-vendor OpenCode's unpublished packages from a named upstream commit.

    python scripts/vendor_opencode.py                 # re-vendor the pinned ref
    python scripts/vendor_opencode.py <ref>           # move to a new ref
    python scripts/vendor_opencode.py --check         # is the tree what the pin says?

WHY THIS EXISTS RATHER THAN A SUBTREE. Most of OpenCode's UI is published to
npm under MIT - `@opencode/ui` alone has 467 versions - so it upgrades with a
version bump and needs no copy at all. Only two packages are unavailable that
way: `session-ui` is marked private, and `app` has never been published despite
not being marked private. Vendoring the whole 149 MB monorepo to obtain 12 MB
of those two would put their terminal UI, their website and their 49 MB console
into this repository for no reason.

So the split is: dependencies where a dependency is possible, copies where it
is not, and this script to make the copies reproducible. Upgrading is
`vendor_opencode.py <new ref>` followed by a diff, which is the same operation
a subtree pull would give and is legible in review.

THE PIN IS THE POINT. `PROVENANCE.json` records the commit, and the licence
test asserts that the notices file names the same one. An upstream diff is
impossible without knowing what we forked from, and the day that matters is the
day nobody remembers.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "opencode"
PROVENANCE = VENDOR / "PROVENANCE.json"

UPSTREAM = "https://github.com/anomalyco/opencode.git"
BRANCH = "v2"

#: Copied because npm cannot supply them. Everything else OpenCode's UI needs
#: is a published package; see the module docstring.
PACKAGES = ("packages/app", "packages/session-ui")

#: Never copied. `node_modules` would be someone else's install, and the build
#: outputs are regenerated here.
SKIP = {"node_modules", ".turbo", "dist", ".output"}

#: Their tests, stories and browser harnesses are not vendored at all.
#:
#: THIS IS A PRIVACY RULE BEFORE IT IS A SIZE ONE. Upstream's fixtures capture
#: real home-directory paths from real machines - a Windows profile path, two
#: macOS home directories, each carrying a contributor's own username. The
#: gate's identifier scan caught seven of them, and it was right to: other people's personal paths do not become
#: shippable because they belong to someone other than the owner.
#:
#: The two easy fixes both cost the gate its meaning. Excluding vendor/ from the
#: scan would let any future upstream leak straight through; editing the files
#: would break byte-identity with the pinned commit. Not copying them does
#: neither. None of these files is needed to build or run the interface, their
#: suite is theirs to run, and every source file that IS copied stays
#: byte-identical.
SKIP_DIRS = {"e2e", "component-tests", "test-browser", "test", "__tests__", "fixtures"}
SKIP_SUFFIXES = (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx", ".stories.tsx", ".stories.ts")


#: THE ONLY EDITS MADE TO UPSTREAM SOURCE, and they are here rather than in the
#: tree so that re-vendoring re-applies them and nobody can mistake one for a
#: local change.
#:
#: `session-ui` resolves by a Vite alias, which Tailwind's CSS resolver does not
#: honour - it uses enhanced-resolve and walks node_modules, and session-ui is
#: not installed as a package because its own manifest carries sixteen
#: `catalog:` entries npm cannot read. So one bare CSS import is rewritten to a
#: relative path. Everything else in the tree stays byte-identical to the pinned
#: commit.
PATCHES = (
    (
        "packages/app/src/index.css",
        '@import "@opencode/session-ui/styles";',
        '@import "../../session-ui/src/styles/index.css";',
    ),
    # TAILWIND WAS SCANNING NOTHING. Their @opencode/ui/styles/tailwind entry
    # declares @source globs relative to where that package sits in THEIR
    # monorepo ("../../../../app/src"). Installed from npm it sits in
    # node_modules, where those globs point at nothing - so none of the ~917
    # utility classes their app uses for layout were generated. The component
    # CSS still worked because it keys off data attributes, which is why every
    # other gate passed; only launching the real app showed every pane
    # collapsed. These globs are relative to THIS file, in this layout.
    # Joined with chr(10): an escaped newline typed into this file has been
    # eaten by the tooling three times.
    (
        "packages/app/src/index.css",
        '@import "tw-animate-css";',
        chr(10).join([
            '@import "tw-animate-css";',
            '@source "./";',
            '@source not "./runtime/i18n";',
            '@source "../../session-ui/src";',
            '@source "../../../../../web/index.html";',
            '@source "../../../../../web/src";',
        ]),
    ),
    # HARNESS SURFACES AS SIDE-PANEL TABS (docs/PHASE-5-SURFACES.md, P1-P8).
    # Their side panel keeps its tabs as plain strings per session, so a
    # `harness:<pane>` id gets their toggle, reordering, closing, resizing and
    # saved width for free. Only two places know the built-in ids, and both
    # would treat an unknown id as a FILE tab; these teach them one prefix.
    # P1: a harness tab is not a file tab.
    (
        "packages/app/src/session/helpers.ts",
        "        (tab) => tab !== SESSION_OPEN_FILE_TAB && tab !== SESSION_BTW_TAB && !isSessionBrowserTab(tab),",
        '        (tab) => tab !== SESSION_OPEN_FILE_TAB && tab !== SESSION_BTW_TAB && !isSessionBrowserTab(tab) && !tab.startsWith("harness:"),',
    ),
    # P2: an active harness tab stays active.
    (
        "packages/app/src/session/helpers.ts",
        '    if (active === "review" && review()) return active',
        chr(10).join([
            '    if (active?.startsWith("harness:")) return active',
            '    if (active === "review" && review()) return active',
        ]),
    ),
    # P3: with nothing else to show, fall back to a harness tab, not "empty".
    (
        "packages/app/src/session/helpers.ts",
        '    if (review() && hasReview()) return "review"',
        chr(10).join([
            '    if (review() && hasReview()) return "review"',
            '    const harness = panelTabs().find((tab) => tab.startsWith("harness:"))',
            "    if (harness) return harness",
        ]),
    ),
    # P4: a harness tab closes with their close-tab key.
    (
        "packages/app/src/session/helpers.ts",
        "  const closableTab = createMemo<string | undefined>(() => {",
        chr(10).join([
            "  const closableTab = createMemo<string | undefined>(() => {",
            '    if (activeTab().startsWith("harness:")) return activeTab()',
        ]),
    ),
    # P5: the three slots, from this product's tree.
    (
        "packages/app/src/session/files/session-side-panel.tsx",
        'import { SessionBrowserPane } from "@/session/browser/pane"',
        chr(10).join([
            'import { SessionBrowserPane } from "@/session/browser/pane"',
            'import { HarnessPanelAddButton, HarnessPanelContent, HarnessTabLabel } from "@harness/panel/slots"',
        ]),
    ),
    # P6: the tab trigger, in their SortableTab like the BTW and browser tabs.
    (
        "packages/app/src/session/files/session-side-panel.tsx",
        "                                <Match when={isSessionBrowserTab(tab)}>",
        chr(10).join([
            '                                <Match when={tab.startsWith("harness:")}>',
            "                                  <SortableTab tab={tab} index={tabs().all().indexOf(tab)} onTabClose={tabs().close}>",
            "                                    <HarnessTabLabel tab={tab} />",
            "                                  </SortableTab>",
            "                                </Match>",
            "                                <Match when={isSessionBrowserTab(tab)}>",
        ]),
    ),
    # P7: the tab content.
    (
        "packages/app/src/session/files/session-side-panel.tsx",
        "                      <Show when={props.browser.opened()}>",
        chr(10).join([
            '                      <Show when={activeTab().startsWith("harness:") ? activeTab() : undefined} keyed>',
            "                        {(tab) => (",
            '                          <Tabs.Content value={tab} class="flex h-full min-h-0 flex-col overflow-hidden">',
            "                            <HarnessPanelContent tab={tab} />",
            "                          </Tabs.Content>",
            "                        )}",
            "                      </Show>",
            "                      <Show when={props.browser.opened()}>",
        ]),
    ),
    # P8: ONE "+" for the side panel. Theirs was a one-click "Open file" or,
    # with a browser attached, a menu of Open file and Browser; the harness
    # had a second "+" beside it for its panels. The owner wanted one: their
    # whole block is replaced by the harness menu, which carries their Open
    # file action (their `openFileBrowser`, with its keybind) above the
    # panels, searchable. The Browser entry goes: the harness has no browser
    # pane. The anchor is their whole block, from their comment to the Show
    # that closes it, so it names one place and leaves nothing half-shown.
    (
        "packages/app/src/session/files/session-side-panel.tsx",
        chr(10).join([
            '                            {/* With only files to add, the plus stays a one-click "Open file" button. */}',
            "                            <Show",
            "                              when={props.browser.available()}",
            "                              fallback={",
            "                                <Tooltip",
            "                                  value={",
            "                                    <>",
            '                                      {language.t("command.file.open")}',
            "                                      <Show when={openFileKeybind().length > 0}>",
            '                                        <Keybind keys={openFileKeybind()} variant="neutral" />',
            "                                      </Show>",
            "                                    </>",
            "                                  }",
            '                                  placement="bottom"',
            '                                  class="flex items-center"',
            "                                >",
            "                                  <IconButton",
            '                                    icon={<Icon name="plus" />}',
            '                                    variant="ghost-muted"',
            '                                    size="large"',
            "                                    onClick={() => openFileBrowser()}",
            '                                    aria-label={language.t("command.file.open")}',
            "                                  />",
            "                                </Tooltip>",
            "                              }",
            "                            >",
            "                              <Tooltip",
            '                                value={language.t("session.tab.add")}',
            '                                placement="bottom"',
            '                                class="flex items-center"',
            "                              >",
            '                                <Menu appearance="standard" modal={false} placement="bottom-start" gutter={4}>',
            "                                  <Menu.Trigger",
            "                                    as={IconButton}",
            '                                    icon={<Icon name="plus" />}',
            '                                    variant="ghost-muted"',
            '                                    size="large"',
            '                                    aria-label={language.t("session.tab.add")}',
            "                                    // The tablist redirects focus entering it to the selected",
            "                                    // tab, which counts as focus-outside and closes the menu.",
            "                                    onPointerDown={(event: PointerEvent) => event.preventDefault()}",
            "                                  />",
            "                                  <Menu.Portal>",
            "                                    <Menu.Content>",
            "                                      <Menu.Item",
            '                                        class="!gap-6"',
            "                                        onSelect={openFileBrowser}",
            "                                        shortcut={",
            "                                          <Show when={openFileKeybind().length > 0}>",
            '                                            <Keybind keys={openFileKeybind()} variant="neutral" />',
            "                                          </Show>",
            "                                        }",
            "                                      >",
            '                                        <div class="flex items-center gap-2">',
            '                                          <Icon name="file-tree" size="small" />',
            '                                          <span>{language.t("command.file.open")}</span>',
            "                                        </div>",
            "                                      </Menu.Item>",
            "                                      <Menu.Item",
            '                                        class="!gap-6"',
            "                                        onSelect={props.browser.open}",
            "                                        shortcut={",
            "                                          <Show when={openBrowserKeybind().length > 0}>",
            '                                            <Keybind keys={openBrowserKeybind()} variant="neutral" />',
            "                                          </Show>",
            "                                        }",
            "                                      >",
            '                                        <div class="flex items-center gap-2">',
            '                                          <Icon name="globe" size="small" />',
            '                                          <span>{language.t("session.tab.browser")}</span>',
            "                                        </div>",
            "                                      </Menu.Item>",
            "                                    </Menu.Content>",
            "                                  </Menu.Portal>",
            "                                </Menu>",
            "                              </Tooltip>",
            "                            </Show>",
        ]),
        chr(10).join([
            "                            {/* Harness: one plus for files and the harness panels (scripts/vendor_opencode.py, P8). */}",
            "                            <HarnessPanelAddButton onOpenFile={openFileBrowser} openFileKeybind={openFileKeybind()} />",
        ]),
    ),
    # HARNESS SETTINGS SECTIONS (P9-P12). Their settings tabs are fixed lists
    # with no way to register a section from outside; these add one group whose
    # tab values carry the harness: prefix.
    (
        "packages/app/src/settings/surface.tsx",
        "  return value in rootTabs",
        '  return value in rootTabs || value.startsWith("harness:")',
    ),
    (
        "packages/app/src/settings/shell.tsx",
        'import { revealSettingsSearch } from "./search-reveal"',
        chr(10).join([
            'import { revealSettingsSearch } from "./search-reveal"',
            'import { harnessSettingsGroups, HarnessSettingsPanels } from "@harness/settings/slots"',
        ]),
    ),
    (
        "packages/app/src/settings/shell.tsx",
        "    ...trailingTabs.map((items) => ({ items: items.map((item) => ({ ...item, label: language.t(item.label) })) })),",
        chr(10).join([
            "    ...harnessSettingsGroups(),",
            "    ...trailingTabs.map((items) => ({ items: items.map((item) => ({ ...item, label: language.t(item.label) })) })),",
        ]),
    ),
    (
        "packages/app/src/settings/shell.tsx",
        '      <Tabs.Content value="about" class="settings-panel settings-about">',
        chr(10).join([
            "      <HarnessSettingsPanels />",
            '      <Tabs.Content value="about" class="settings-panel settings-about">',
        ]),
    ),
    # THEIR CUSTOM PROVIDER FORM, SAVED (P15-P16). Built upstream and disabled
    # until their server has a config API; the harness has one, so each model
    # the form lists becomes a harness connection.
    (
        "packages/app/src/providers/credentials/dialog.tsx",
        'import { type FormState, headerRow, modelRow, validateCustomProvider } from "./form"',
        chr(10).join([
            'import { type FormState, headerRow, modelRow, validateCustomProvider } from "./form"',
            'import { saveHarnessCustomProvider } from "@harness/providers/custom"',
        ]),
    ),
    (
        "packages/app/src/providers/credentials/dialog.tsx",
        '      throw new Error(language.t("provider.custom.unavailable"))',
        "      return saveHarnessCustomProvider(result)",
    ),
    # THEIR NEW-CHAT TIPS, REMOVED (P17). The provider tip is absolutely
    # positioned at the bottom and overlapped the harness start card, which
    # offers the same thing - a model, one click - better; the workspace tip
    # advertises worktrees, which the harness does not have. Seen only by
    # opening the rebuilt app. Anchored on the function, not the element: the
    # element's first line is where P14's anchor ends, and two patches must
    # never edit the same text.
    (
        "packages/app/src/new-session/view.tsx",
        "function NewSessionTips(props: { workspaceEligible: boolean; onWorkspace: () => void }) {",
        chr(10).join([
            "function NewSessionTips(props: { workspaceEligible: boolean; onWorkspace: () => void }) {",
            "  // Harness: no tips on the new-chat screen (scripts/vendor_opencode.py, P17).",
            "  const hiddenByHarness = true",
            "  if (hiddenByHarness) return null",
        ]),
    ),
    # THEIR ERROR SCREEN'S REPORT BUTTON, REMOVED (P18). It opened their
    # feedback page, so this product's crashes would have been reported to
    # another team. The line above it is reworded in web/src/brand/strings.ts.
    (
        "packages/app/src/shell/errors/error.tsx",
        chr(10).join([
            "            <button",
            '              type="button"',
            '              class="flex items-center text-text-interactive-base gap-1"',
            '              onClick={() => platform.openExternal("https://opencode.ai/desktop-feedback")}',
            "            >",
            '              <div>{language.t("error.page.report.discord")}</div>',
            '              <Icon name="discord" class="text-text-interactive-base" />',
            "            </button>",
        ]),
        "            {/* Harness: no report link to another product's team (P18). */}",
    ),
    # THEIR SETTINGS PAGES THAT DO NOT APPLY, HIDDEN (P19): Worktrees,
    # Extensions, Server. See harnessFilterSettings for why each. The group
    # list is wrapped, not edited, so P11's insertion inside it is untouched.
    # Its own import line, anchored on a line no other patch touches: editing
    # P10's inserted import would make P10 read as unapplied.
    (
        "packages/app/src/settings/shell.tsx",
        'import { pageIcons } from "./pages"',
        chr(10).join([
            'import { pageIcons } from "./pages"',
            'import { harnessFilterSettings } from "@harness/settings/slots"',
        ]),
    ),
    (
        "packages/app/src/settings/shell.tsx",
        chr(10).join([
            "  const groups = createMemo<SettingsNavGroup[]>(() => [",
            "    {",
            "      items: rootClientTabs",
        ]),
        chr(10).join([
            "  const groups = createMemo<SettingsNavGroup[]>(() => harnessFilterSettings([",
            "    {",
            "      items: rootClientTabs",
        ]),
    ),
    (
        "packages/app/src/settings/shell.tsx",
        chr(10).join([
            "    ...trailingTabs.map((items) => ({ items: items.map((item) => ({ ...item, label: language.t(item.label) })) })),",
            "  ])",
        ]),
        chr(10).join([
            "    ...trailingTabs.map((items) => ({ items: items.map((item) => ({ ...item, label: language.t(item.label) })) })),",
            "  ]))",
        ]),
    ),
    # THE TERMINAL PLACEMENT SETTING, REMOVED (P26). The harness has no
    # terminal surface; a setting for where one opens is a promise the app
    # cannot keep. Seen by the owner in Settings > Preferences.
    (
        "packages/app/src/settings/general/general.tsx",
        "        <TerminalPlacementSetting />",
        "        {/* Harness: no terminal here, so no placement for one (P26). */}",
    ),
    # PROJECTS AND CHATS, NOT WORKSPACES (P27-P29). The owner, 2026-09-22:
    # "every chat is a session; there are different projects where these chats
    # take place - that's the only difference." Their worktree controls that
    # were still reachable, each checked for what it does here first.
    # P27: "Default environment - choose where new sessions start". It picks
    # Local, New worktree or Last used; "New worktree" makes every new chat in
    # a git project try to create one (workspaces/paths.ts
    # workspaceDefaultSelection -> "create"), which the facade refuses. Search
    # stops listing it too (web/src/harness/settings/unbacked.ts).
    (
        "packages/app/src/settings/general/general.tsx",
        "        <WorkspaceDestinationSetting />",
        "        {/* Harness: no worktrees, so no choice of where a new chat starts (P27). */}",
    ),
    # P28: a "New worktree" already SAVED by that row before P27 hid it would
    # still route new chats to "create"; it now means the project's folder.
    (
        "packages/app/src/workspaces/paths.ts",
        '  if (setting === "new") return "create"',
        '  if (setting === "new") return "main" // Harness: no worktrees; a new chat starts in its project (P28).',
    ),
    # P29: Settings > Projects > a project: "Worktree startup script", run
    # after creating a worktree, which never happens here. Hidden inline so
    # their stylesheet's display rule cannot win over it.
    (
        "packages/app/src/settings/workspaces/project.tsx",
        '          <div class="project-settings-startup">',
        chr(10).join([
            "          {/* Harness: no worktrees, so no worktree startup script (P29). */}",
            '          <div class="project-settings-startup" style={{ display: "none" }}>',
        ]),
    ),
    # THE HARNESS START CONTENT (P13-P14): hardware, starter prompts, and a
    # one-click model when none is connected, under their new-chat composer and
    # its project selector. The anchor runs to <NewSessionTips because that is
    # what makes the closing tags above it name one place.
    (
        "packages/app/src/new-session/view.tsx",
        'import { NewSessionWordmark } from "./wordmark"',
        chr(10).join([
            'import { NewSessionWordmark } from "./wordmark"',
            'import { HarnessStart } from "@harness/start/start"',
        ]),
    ),
    (
        "packages/app/src/new-session/view.tsx",
        chr(10).join([
            "              </Show>",
            "            </div>",
            "          </div>",
            "        </div>",
            "        <NewSessionTips",
        ]),
        chr(10).join([
            "              </Show>",
            "              <HarnessStart composer={props.composer} />",
            "            </div>",
            "          </div>",
            "        </div>",
            "        <NewSessionTips",
        ]),
    ),
    # THE SESSION RAIL (P20-P21), in their vertical-tabs sidebar. The owner
    # kept OpenCode's layout but wanted his session rail back: projects as
    # folders, sub-agents nested, busy, pins, filter, rename/archive/delete
    # (docs/PARITY.md section 2; web/src/harness/rail/rail.tsx). It goes in
    # the Portal their titlebar already mounts into the sidebar, between their
    # "New session" button and their tab strip, so it rides their own handling
    # of the sidebar appearing and disappearing when the layout toggles. A
    # patch to shell.tsx would put it in the aside ahead of their portal's
    # children - above their home and new-session buttons. Import on its own
    # line; the mount anchored on the spacer AND the tab-strip wrapper so it
    # names one place and inserts between them.
    (
        "packages/app/src/shell/titlebar/titlebar.tsx",
        'import { SessionTabAvatar } from "@/shell/layout/session-tab-avatar"',
        chr(10).join([
            'import { SessionTabAvatar } from "@/shell/layout/session-tab-avatar"',
            'import { HarnessRail } from "@harness/rail/rail"',
        ]),
    ),
    (
        "packages/app/src/shell/titlebar/titlebar.tsx",
        chr(10).join([
            '                            <div class="h-4 w-full shrink-0" aria-hidden="true" />',
            '                            <div class="flex min-h-0 flex-1 flex-col gap-1">',
        ]),
        chr(10).join([
            '                            <div class="h-4 w-full shrink-0" aria-hidden="true" />',
            "                            <HarnessRail />",
            '                            <div class="flex min-h-0 flex-1 flex-col gap-1">',
        ]),
    ),
    # SURFACES WITH NO BACKING, HIDDEN (P22-P24). Found by grepping their
    # session and settings UI for worktrees, MCP, terminal and language
    # servers; the substitutions for the rest are in web/vite.config.ts.
    # P22: "Move to workspace". Their composer region calls every session
    # eligible to move into a worktree; the harness has none, so the move row
    # in the session summary and timeline never shows and the location row's
    # menu (Local / New workspace) is disabled.
    (
        "packages/app/src/session/composer/region.tsx",
        "    workspaceMoveEligible: () => true,",
        "    workspaceMoveEligible: () => false, // Harness: no worktrees to move a session to (P22).",
    ),
    # P23: their terminal and MCP palette commands. "New terminal"
    # (ctrl+alt+t) would mount a terminal the engine answers empty, and
    # "Toggle MCPs" (/mcp, mod+;) opens a dialog of servers that do not
    # exist. Their registration list simply stops including the two groups;
    # it also drops them from Settings > Shortcuts, which lists what is
    # registered. `terminal.toggle` is re-registered disabled by the harness
    # session mount (web/src/harness/session/mount.tsx).
    (
        "packages/app/src/session/commands/use-session-commands.tsx",
        "    ...terminalCmds(),",
        "    // Harness: no terminal here (P23).",
    ),
    (
        "packages/app/src/session/commands/use-session-commands.tsx",
        "    ...mcpCmds(),",
        "    // Harness: no MCP servers here (P23).",
    ),
    # P24: a project's own settings tabs. Worktrees and Extensions (MCP,
    # plugins, skills, language servers) per project, hidden for the reasons
    # in web/src/harness/settings/unbacked.ts; General stays. Its import on a
    # line no other patch touches.
    (
        "packages/app/src/settings/shell.tsx",
        'import { SettingsProjectGeneral } from "./workspaces/project"',
        chr(10).join([
            'import { SettingsProjectGeneral } from "./workspaces/project"',
            'import { harnessUnbackedSetting } from "@harness/settings/unbacked"',
        ]),
    ),
    (
        "packages/app/src/settings/shell.tsx",
        "      items: nestedProjectTabs.map((item) => ({",
        "      items: nestedProjectTabs.filter((item) => !harnessUnbackedSetting(item.value)).map((item) => ({",
    ),
    # P25: "!" IS TEXT. Their composer turns a lone "!" into shell mode, which
    # runs the line as a command in their shell; the harness has no shell
    # (app/facade/router.py has no shell route at all), so a person typing
    # "!" lost the character to a mode that could only fail. The branch stays,
    # switched off, so their machine is otherwise byte-for-byte theirs.
    (
        "packages/app/src/composer/suggestions/machine.ts",
        '  if (state.mode === "normal" && value === "!") {',
        chr(10).join([
            '  // Harness: no shell, so "!" is just text (scripts/vendor_opencode.py, P25).',
            '  if (false && state.mode === "normal" && value === "!") {',
        ]),
    ),
    # THE THINKING BLOCK (P30-P31). The owner, 2026-09-23, on the "Thinking"
    # block in a reply: "can you just click on any part of the thinking
    # process to minimise that thinking bar? Otherwise it keeps infinitely
    # scrolling up", and "add an icon for the thinking section ... a spinning
    # icon or a flashing sparkly icon". Their AssistantReasoningContent is what
    # the facade's session.reasoning.* stream renders as. The height cap while
    # it streams and the sparkle's motion are CSS (web/src/brand/identity.css).
    # P30: a click anywhere on the open body closes it, as the header does -
    # unless the click ended a drag that selected text, or landed on a link or
    # button inside the markdown. Same three calls as their onOpenChange.
    # A DOUBLE-CLICK SELECTS A WORD, and does not close it (the coordinator,
    # 2026-09-23). Its first click is an ordinary detail-1 click, so a guard on
    # `detail > 1` alone would already have closed the block; a single click
    # closes 300 ms later instead, and the second click (or a selection made
    # meanwhile) cancels it. The timer lives in the component, cleared with it.
    (
        "packages/session-ui/src/message/message-content.tsx",
        "  const [state, setState] = createStore<{ open?: boolean }>({})",
        chr(10).join([
            "  const [state, setState] = createStore<{ open?: boolean }>({})",
            "  // Harness: a single click on the open thinking closes it once no double-click follows (P30).",
            "  let harnessClose: ReturnType<typeof setTimeout> | undefined",
            "  onCleanup(() => clearTimeout(harnessClose))",
        ]),
    ),
    (
        "packages/session-ui/src/message/message-content.tsx",
        chr(10).join([
            "        <PacedMarkdown text={props.content.text} cacheKey={props.id} streaming={props.streaming} />",
            "      </BasicTool>",
        ]),
        chr(10).join([
            "        {/* Harness: a click on the open thinking closes it; a selection or a double-click does not (P30). */}",
            "        <div",
            '          data-slot="harness-reasoning-body"',
            "          onClick={(event) => {",
            "            clearTimeout(harnessClose)",
            "            if (event.detail > 1) return",
            "            if (window.getSelection()?.isCollapsed === false) return",
            '            if ((event.target as Element).closest?.("a, button, input, textarea")) return',
            "            harnessClose = setTimeout(() => {",
            "              if (window.getSelection()?.isCollapsed === false) return",
            '              setState("open", false)',
            "              props.onOpenChange?.(false)",
            "              props.onContentRendered?.()",
            "            }, 300)",
            "          }}",
            "        >",
            "          <PacedMarkdown text={props.content.text} cacheKey={props.id} streaming={props.streaming} />",
            "        </div>",
            "      </BasicTool>",
        ]),
    ),
    # P31: a sparkle before "Thinking" / "Thought" ("models" in their v2 set,
    # a four-point star - their set has no other; web/src/harness/panel/
    # panes.ts has the one-icon-set rule), and a mark while it streams, since
    # BasicTool puts its status on no element of its own.
    (
        "packages/session-ui/src/message/message-content.tsx",
        '    <div data-component="reasoning-part" data-timeline-part-id={props.id}>',
        chr(10).join([
            "    <div",
            '      data-component="reasoning-part"',
            "      data-timeline-part-id={props.id}",
            '      data-harness-streaming={props.streaming ? "true" : undefined} /* Harness: while it thinks (P31). */',
            "    >",
        ]),
    ),
    (
        "packages/session-ui/src/message/message-content.tsx",
        chr(10).join([
            '            <div data-slot="basic-tool-tool-info-main">',
            '              <span data-slot="basic-tool-tool-title">',
            "                <TextShimmer",
            '                  text={i18n.t(props.streaming ? "ui.sessionTurn.status.thinking" : "ui.message.thought")}',
        ]),
        chr(10).join([
            '            <div data-slot="basic-tool-tool-info-main">',
            '              <Icon name="models" size="small" data-harness-reasoning-icon="" /* Harness: the sparkle (P31). */ />',
            '              <span data-slot="basic-tool-tool-title">',
            "                <TextShimmer",
            '                  text={i18n.t(props.streaming ? "ui.sessionTurn.status.thinking" : "ui.message.thought")}',
        ]),
    ),
    # P32-P43: SETTINGS ROWS THAT DO NOTHING HERE (S1-S9, S11-S12 of
    # web/src/harness/settings/PENDING-PATCHES.md; S10 is NOT applied: the
    # owner asked for an easy rail/top-tabs switch, which the rail lane built). The owner, 2026-09-23:
    # "make sure all these things work if we actually need them". Each row
    # was checked against what reads it; the reasons are in
    # web/src/harness/settings/PENDING-PATCHES.md and unbacked.ts
    # (HIDDEN_SETTING_ROWS, which already keeps them out of search).
    # S1-S2: English only, and light or dark takes the Language row's slot -
    # their Appearance page is hidden and this is its one real row.
    (
        "packages/app/src/settings/general/general.tsx",
        'import { SettingsRow } from "@/settings/row"',
        chr(10).join([
            'import { SettingsRow } from "@/settings/row"',
            'import { HarnessColorSchemeSetting } from "@harness/settings/color-scheme"',
        ]),
    ),
    (
        "packages/app/src/settings/general/general.tsx",
        "        <LanguageSetting />",
        chr(10).join([
            "        {/* Harness: English only; every other locale is their translation (S2). */}",
            "        <HarnessColorSchemeSetting />",
        ]),
    ),
    # S3: "Show agent". The agents are the harness's modes; off hides Plan.
    (
        "packages/app/src/settings/general/general.tsx",
        chr(10).join([
            "        <SettingsRow",
            '          title={language.t("settings.general.row.showCustomAgents.title")}',
            '          description={language.t("settings.general.row.showCustomAgents.description")}',
            "        >",
            '          <div data-action="settings-show-custom-agents">',
            "            <Switch",
            "              checked={settings.general.showCustomAgents()}",
            "              onChange={(checked) => settings.general.setShowCustomAgents(checked)}",
            "            />",
            "          </div>",
            "        </SettingsRow>",
        ]),
        "        {/* Harness: the agents are the modes, always shown (S3). */}",
    ),
    # S4: queue and steer are one thing to this engine.
    (
        "packages/app/src/settings/general/general.tsx",
        "        <FollowUpBehaviorSetting />",
        "        {/* Harness: every follow-up runs after the running turn; no queue/steer choice (S4). */}",
    ),
    # S5: the shell has no pinch-zoom control.
    (
        "packages/app/src/settings/general/general.tsx",
        chr(10).join([
            "        <Show when={desktop()}>",
            "          <SettingsRow",
            '            title={language.t("settings.general.row.pinchZoom.title")}',
            '            description={language.t("settings.general.row.pinchZoom.description")}',
            "          >",
            '            <div data-action="settings-pinch-zoom">',
            "              <Switch checked={pinchZoom.latest} onChange={onPinchZoomChange} />",
            "            </div>",
            "          </SettingsRow>",
            "        </Show>",
        ]),
        "        {/* Harness: the shell has no pinch-zoom control (S5). */}",
    ),
    # S6: their updater and their release notes.
    (
        "packages/app/src/settings/general/general.tsx",
        chr(10).join([
            "        <Show when={desktop()}>",
            "          <UpdatesSection />",
            "        </Show>",
        ]),
        "        {/* Harness: no updater here, and their release notes are another product's (S6). */}",
    ),
    # S7: a notification setting nothing reads.
    (
        "packages/app/src/settings/notifications/notifications.tsx",
        chr(10).join([
            "            <SettingsRow",
            '              title={language.t("settings.general.notifications.permissions.title")}',
            '              description={language.t("settings.general.notifications.permissions.description")}',
            "            >",
            '              <div data-action="settings-notifications-permissions">',
            "                <Switch",
            "                  checked={settings.notifications.permissions()}",
            "                  onChange={(checked) => settings.notifications.setPermissions(checked)}",
            "                />",
            "              </div>",
            "            </SettingsRow>",
        ]),
        "            {/* Harness: nothing reads a permissions notification setting (S7). */}",
    ),
    # S8: their sound files are not vendored, so no sound plays.
    (
        "packages/app/src/settings/notifications/notifications.tsx",
        chr(10).join([
            '        <div class="settings-section">',
            '          <h3 class="settings-section-title">{language.t("settings.general.section.sounds")}</h3>',
            "          <SettingsList>",
            '            <SoundSetting kind="agent" channel={sounds.agent} />',
            '            <SoundSetting kind="permissions" channel={sounds.permissions} />',
            '            <SoundSetting kind="errors" channel={sounds.errors} />',
            "          </SettingsList>",
            "        </div>",
        ]),
        "        {/* Harness: their sound files are not vendored; no sound would play (S8). */}",
    ),
    # S9: never fetch opencode.ai's changelog as this product's release notes.
    (
        "packages/app/src/shell/updates/highlights.tsx",
        "      if (!settings.general.releaseNotes()) {",
        "      if (true || !settings.general.releaseNotes()) { // Harness: their changelog is another product's (S9).",
    ),
    # S11-S12: Settings > Shortcuts offers no key for a command switched off
    # here (web/src/harness/session/unsupported.ts). Their list reads the
    # command catalogue, which keeps the original entry an override hides.
    (
        "packages/app/src/settings/keybinds/keybinds.tsx",
        'import { SettingsList } from "@/settings/list"',
        chr(10).join([
            'import { SettingsList } from "@/settings/list"',
            'import { UNSUPPORTED_COMMANDS } from "@harness/session/unsupported"',
        ]),
    ),
    (
        "packages/app/src/settings/keybinds/keybinds.tsx",
        "  for (const opt of command.catalog) {",
        chr(10).join([
            "  for (const opt of command.catalog) {",
            "    if (opt.id in UNSUPPORTED_COMMANDS) continue // Harness: switched off here (S12).",
        ]),
    ),
    (
        "packages/app/src/settings/keybinds/keybinds.tsx",
        "  for (const opt of command.options) {",
        chr(10).join([
            "  for (const opt of command.options) {",
            "    if (opt.id in UNSUPPORTED_COMMANDS) continue // Harness: switched off here (S12).",
        ]),
    ),
    # P44: SETTINGS AT THE TOP LEFT (Jaden, 2026-10-03: "a settings bar top
    # left not on home"). Under their Home and New chat in the sidebar, in the
    # same row style, ahead of the spacer and the rail (P20-P21).
    (
        "packages/app/src/shell/titlebar/titlebar.tsx",
        'import { HarnessRail } from "@harness/rail/rail"',
        chr(10).join([
            'import { HarnessRail } from "@harness/rail/rail"',
            'import { HarnessSidebarSettings } from "@harness/rail/settings-link"',
        ]),
    ),
    (
        "packages/app/src/shell/titlebar/titlebar.tsx",
        chr(10).join([
            '                            <div class="h-4 w-full shrink-0" aria-hidden="true" />',
            "                            <HarnessRail />",
        ]),
        chr(10).join([
            "                            <HarnessSidebarSettings />",
            '                            <div class="h-4 w-full shrink-0" aria-hidden="true" />',
            "                            <HarnessRail />",
        ]),
    ),
)


def apply_patches() -> list[str]:
    """Apply PATCHES, failing loudly if a target no longer matches.

    A patch that silently does not apply is worse than no patch: the build
    would fail somewhere unrelated, or worse, succeed against stale content.
    """
    applied = []
    for relative, before, after in PATCHES:
        path = VENDOR / relative
        text = path.read_text(encoding="utf-8")
        # APPLIED CHECK FIRST. An insertion patch's `after` contains its
        # `before`, so testing `before` first finds it again in an already
        # patched file and inserts a second copy on every re-run.
        if after in text:
            continue
        if before not in text:
            sys.exit(
                f"patch target vanished in {relative}: upstream no longer "
                f"contains {before!r}. Re-read their file and update PATCHES "
                "rather than skipping it."
            )
        # ONE MATCH OR NONE. An anchor upstream starts using twice would patch
        # whichever came first, silently, and the build would still pass.
        if text.count(before) != 1:
            sys.exit(
                f"patch anchor in {relative} occurs {text.count(before)} times: "
                f"{before!r}. Lengthen it until it names one place."
            )
        path.write_text(text.replace(before, after, 1), encoding="utf-8", newline="")
        applied.append(relative)
    return applied


def patched_files() -> list[str]:
    return sorted({relative for relative, _, _ in PATCHES})


def read_pin() -> dict:
    return json.loads(PROVENANCE.read_text(encoding="utf-8"))


def fetch(ref: str, into: Path) -> str:
    """A shallow fetch of one commit. Returns the resolved sha."""
    subprocess.run(["git", "init", "-q", str(into)], check=True)
    # WITHOUT THIS THE COPY IS NOT UPSTREAM'S BYTES. On Windows a checkout
    # rewrites every line ending, so the vendored tree would differ from the
    # commit it claims to be - 8 stray carriage returns in a 240-byte file the
    # first time this ran - and every future upstream diff would be noise.
    subprocess.run(["git", "-C", str(into), "config", "core.autocrlf", "false"], check=True)
    subprocess.run(["git", "-C", str(into), "config", "core.eol", "lf"], check=True)
    subprocess.run(["git", "-C", str(into), "remote", "add", "origin", UPSTREAM], check=True)
    # `--depth 1` of a single ref: we want the tree, never the history. The
    # history is upstream's and stays there.
    subprocess.run(
        ["git", "-C", str(into), "fetch", "-q", "--depth", "1", "origin", ref],
        check=True,
    )
    subprocess.run(["git", "-C", str(into), "checkout", "-q", "FETCH_HEAD"], check=True)
    done = subprocess.run(
        ["git", "-C", str(into), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    )
    return done.stdout.strip()


def copy_package(source: Path, destination: Path) -> int:
    if destination.exists():
        shutil.rmtree(destination)
    copied = 0

    def skipped(directory, name) -> bool:
        path = Path(directory) / name
        if name in SKIP:
            return True
        if path.is_dir():
            return name in SKIP_DIRS
        return name.endswith(SKIP_SUFFIXES)

    def ignore(directory, names):
        nonlocal copied
        drop = [name for name in names if skipped(directory, name)]
        copied += sum(1 for name in names if name not in drop and (Path(directory) / name).is_file())
        return drop

    shutil.copytree(source, destination, ignore=ignore)
    return copied


def vendor(ref: str) -> None:
    with tempfile.TemporaryDirectory() as scratch:
        checkout = Path(scratch) / "upstream"
        print(f"fetching {ref} from {UPSTREAM}")
        resolved = fetch(ref, checkout)
        print(f"resolved to {resolved}")

        total = 0
        for relative in PACKAGES:
            source = checkout / relative
            if not source.is_dir():
                sys.exit(f"{relative} is not in {resolved} - has upstream moved it?")
            count = copy_package(source, VENDOR / relative)
            print(f"  {relative}: {count} files")
            total += count

        shutil.copy2(checkout / "LICENSE", VENDOR / "LICENSE")

        # THEIR VERSION CATALOG, CAPTURED AT THE SAME COMMIT. Their manifests
        # say `catalog:` instead of a version, which is a bun workspace feature
        # npm cannot resolve. Rather than hand-pin 69 versions that upstream
        # moves weekly, the catalog is copied out of their root manifest at the
        # pinned ref, so re-vendoring re-derives it and it can never drift from
        # the source it belongs to.
        root = json.loads((checkout / "package.json").read_text(encoding="utf-8"))
        catalog = root.get("workspaces", {}).get("catalog", {})
        if not catalog:
            sys.exit("upstream root manifest has no workspace catalog - has their layout changed?")
        (VENDOR / "CATALOG.json").write_text(
            json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline=chr(10)
        )
        print(f"  catalog: {len(catalog)} pinned versions")

    for relative in apply_patches():
        print(f"  patched: {relative}")

    # Outside the loop: the pin must be recorded even when every patch was
    # already present, and each patched file is named once.
    record = read_pin()
    record["commit"] = resolved
    record["vendored"] = list(PACKAGES)
    record["patched"] = patched_files()
    PROVENANCE.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline=chr(10))

    print(f"\nvendored {total} files at {resolved}")
    print("NEXT: update the commit in THIRD-PARTY-NOTICES.txt, then run the licence test.")


def check() -> int:
    """Is every recorded package actually on disk? The licence test asserts the
    same thing; this is the same check available without running the suite."""
    record = read_pin()
    missing = [r for r in record["vendored"] if not (VENDOR / r).is_dir()]
    if missing:
        print("MISSING: " + ", ".join(missing))
        return 1
    print(f"pinned at {record['commit'][:12]}, all {len(record['vendored'])} packages present")
    return 0


if __name__ == "__main__":
    argument = sys.argv[1] if len(sys.argv) > 1 else None
    if argument == "--check":
        raise SystemExit(check())
    vendor(argument or read_pin()["commit"])
