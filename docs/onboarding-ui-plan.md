# Simpler first screens: plan

**End state.** A new user opens ML Harness, sees one plain way to get a model, reaches a single
Models page that offers a model on this computer or one reached with an API key, and starts a
chat. Home, the sidebar and Settings read as this product rather than as OpenCode with new
colours.

Asked by Jaden, 2026-10-03, after walking through a fresh install in Windows Sandbox.

## Slices, in order

Each slice ships alone and is gated by the web tests (`npm test` in `web/`), the seam tests
(`tests/test_the_harness_seams_hold.py`) and a screenshot of the screen it changes.

1. **One Models page, and a start card that routes to it.**
   - Settings shows one model page, *Models* (today's harness Connections page, renamed). Their
     *Providers* and *Models* pages are hidden, so there are not three places for one job.
   - The page follows the old app's "Connect a model": *On this computer* first (one click per
     Ollama model, and when Ollama or a model is missing, the one install line), then *With an
     API key*, then the saved connections and where keys are kept.
   - The new-chat card, when no model is connected, shows two buttons and nothing else:
     *Use a model on this computer* and *Use an API key*. Both open Settings > Models.
   - Gate: start-card tests rewritten to the new contract; a settings test that the page order is
     local, API, saved; screenshots of the card and the page.
2. **Sidebar: Settings at the top left, vertical only.** Home, New chat and Settings sit together
   at the top of the left sidebar. The horizontal tab layout and its shortcut are removed, so
   projects are always the vertical list on the left. Gate: rail tests; screenshot.
3. **Home is ours.** The projects column and the Settings and Help links leave Home (the sidebar
   has them). Home becomes the recent chats with search and one New chat button, in the
   harness's own card, button and spacing styles. Gate: a Home test that pins the new layout;
   screenshot in light and dark.
4. **Visual pass.** Buttons, cards and section headers on Home, New chat and Settings use the
   harness tokens (`web/src/brand/identity.css`) rather than OpenCode's defaults. Gate:
   screenshots before and after, side by side.

## Out of scope

- Signing in with a subscription (ChatGPT, Claude, Copilot). The engine has no sign-in flow
  today; only local models and API keys connect. It is named as open, not faked.
- Changes to chat, tools or the engine.
- A release. v0.1.1 waits for Jaden's yes after he has seen the install steps.

## Measure

Clicks from first launch to a connected model, counted on the scratch engine with Ollama
running: before (today) and after slice 1.
