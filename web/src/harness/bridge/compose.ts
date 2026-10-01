import { appendPrompt, promptLength } from "@/composer/prompt-parts"
import type { Prompt } from "@/composer/state"

/**
 * The words the plan's "Ask" drafts about a step - the outgoing app's exact
 * wording (frontend/src/components/GoalBar.tsx), left open for the person to
 * finish. It is a draft: nothing is sent.
 */
export function askAboutStep(step: string) {
  return `About the step "${step}": `
}

const textOnly = (prompt: Prompt) => prompt.every((part) => part.type === "text")
const textOf = (prompt: Prompt) => prompt.map((part) => ("content" in part ? part.content : "")).join("")

/**
 * The composer's prompt with `text` drafted into it, and where the cursor
 * goes (the end, so the person types straight on).
 *
 * An empty composer takes the text as its whole prompt. One that already
 * holds something keeps it and gets the text after a blank line - a draft
 * request must never throw away what somebody typed - through their own
 * `appendPrompt`, so file pills and attachments keep their offsets. A second
 * press on the same step changes nothing.
 */
export function draftInto(current: Prompt, text: string): { prompt: Prompt; cursor: number } {
  const own: Prompt = [{ type: "text", content: text, start: 0, end: text.length }]
  if (textOnly(current) && !textOf(current).trim()) return { prompt: own, cursor: text.length }
  if (textOf(current).trimEnd().endsWith(text.trimEnd())) return { prompt: current, cursor: promptLength(current) }
  const prompt = appendPrompt(current, own)
  return { prompt, cursor: promptLength(prompt) }
}
