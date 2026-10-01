# Vendor patches for settings rows that do nothing here (landed)

**Landed 2026-09-23** as P32-P43 in `scripts/vendor_opencode.py`, which is now the
record; the tuples that used to sit at the end of this file are there. One exception:
**S10 (Experimental > Tab layout) was not applied.** Horizontal tabs do remove the
rail's sidebar, and that is the switch the owner asked for; the rail lane bound
Ctrl+Shift+H to it and the row stays. S11-S12 were re-anchored on the two loop
headers so the inserted text quotes none of their `startsWith` lines (the seams
test reads every patch for a foreign tab prefix).

The owner, 2026-09-23: "Fix the settings ... Preferences: make sure all these
things work if we actually need them ... make sure it's not using anything
OpenCode and it's all mapped to our actual true systems."

`scripts/vendor_opencode.py` belongs to another lane right now, so the patches
this pass needs are written out here for the orchestrator to paste into its
`PATCHES` tuple, in order, and number (the S-numbers are placeholders). Each
anchor was checked to occur exactly once in the vendored file at 2cd9438, and
the set was applied to a scratch copy and type-checked and built (see the
lane's report).

Search already stops offering every row below (`HIDDEN_SETTING_ROWS` in
`unbacked.ts`); the pages stop drawing them when these land. Nothing else in
this pass depends on them.

| Patch | File | Row | Why it goes |
|---|---|---|---|
| S1, S2 | `settings/general/general.tsx` | Language, replaced by Colour scheme | Every locale but English is their translation: German alone names "OpenCode" 44 times, and none of them carries `brand/strings.ts`'s words. Colour scheme is the one Appearance row with a real effect (`color-scheme.tsx`), so it takes the slot. |
| S3 | `settings/general/general.tsx` | Show agent | The agents are the modes. Off forces Build and hides Plan and three permission levels (`harness/root.tsx` v1 sets it on). |
| S4 | `settings/general/general.tsx` | Follow-up behaviour (queue / steer) | The facade runs every follow-up after the running turn whichever is sent (`app/facade/router.py` `session_prompt` echoes `delivery` and calls `turns.submit`). Steer does not steer. |
| S5 | `settings/general/general.tsx` | Pinch to zoom (desktop only) | `platform/tauri.ts` has no `getPinchZoomEnabled`/`setPinchZoomEnabled`; the switch flips and nothing changes. |
| S6 | `settings/general/general.tsx` | Updates: Release notes, Check for updates (desktop only) | No `platform.updater`, so the button is always disabled; release notes fetch `https://opencode.ai/changelog.json` (S9). |
| S7 | `settings/notifications/notifications.tsx` | Notifications > Permissions | Nothing in their app reads `settings.notifications.permissions()`. |
| S8 | `settings/notifications/notifications.tsx` | Sounds section (agent, permissions, errors) | `shell/notifications/sound.ts` globs `../../../../ui/src/assets/audio/*.aac`, i.e. `vendor/opencode/packages/ui`, which is not vendored: every sound resolves to nothing (checked in a running window: `soundSrc("alert-01")` is `undefined`). The permissions sound is also read by nothing. |
| S9 | `shell/updates/highlights.tsx` | (no row) their "What's New" dialog | With release notes on (their default), a version change fetches another product's changelog from opencode.ai and shows it. Off for good. |
| S10 | `settings/experimental/experimental.tsx` | Experimental > Tab layout | Horizontal tabs remove the vertical sidebar the session rail lives in (`harness/root.tsx` v2 sets vertical). |
| S11, S12 | `settings/keybinds/keybinds.tsx` | Shortcuts: rows for commands switched off here | The page works (a key bound to "Toggle debug bar" was recorded and then toggled the bar in a running window), but it lists every id in their command catalogue, so it offered keys for Undo, Redo, Fork, Terminal, Shell, Open browser, Move to background (on Ctrl+B, which Home also holds), Cycle session location, Add SSH server, Check for updates and Export logs - each switched off in `harness/session/unsupported.ts`. The list skips those ids. |

After S1/S2 land, `search-catalog.ts` can offer colour scheme again by
retargeting their `settings-color-scheme` entry from `appearance` to `general`
(it is filtered today because Appearance is hidden).

