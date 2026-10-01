import { dict as theirUI } from "@opencode/ui/i18n/en"

/**
 * THEIR UI PACKAGE'S STRINGS, where the composer's words live.
 *
 * Their language context builds English as `{ ...en, ...uiDict }`
 * (runtime/i18n/language.tsx), so the UI package's copy wins over anything in
 * brand/strings.ts for the same key. These are therefore written onto their
 * UI dictionary object itself, at import. brand/strings.ts imports this
 * module, and strings.ts IS `@/runtime/i18n/en` (web/vite.config.ts
 * SUBSTITUTES), which language.tsx imports before it spreads the two - so the
 * spread reads these.
 *
 * THE COMPOSER'S "+" MENU, saying what each entry does in the harness
 * (composer/editor/editor.tsx ComposerEditorAddMenu). Its last entry, shell
 * mode, is hidden in brand/identity.css: the facade serves no shell route
 * (harness/session/unsupported.ts `prompt.mode.shell`).
 */
export const UI_STRINGS = {
  "ui.promptInput.add": "Attach a file, or mention one as context",
  "ui.promptInput.attachments": "Attach files or images to this message",
  "ui.promptInput.commands": "Run a command: /plan, /goal, /compact…",
  "ui.promptInput.context": "Mention a file or folder as context",
  // The agents ARE the harness's modes (app/facade/sessions.py AGENTS); the
  // mode hint in identity.css keys on this label.
  "ui.promptInput.chooseAgent": "Choose mode",
} as const satisfies Partial<Record<keyof typeof theirUI, string>>

Object.assign(theirUI, UI_STRINGS)
