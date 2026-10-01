import { describe, expect, it } from "vitest"
import type { Prompt } from "@/composer/state"
import { promptLength } from "@/composer/prompt-parts"
import { askAboutStep, draftInto } from "./compose"

const text = (content: string, start = 0): Prompt[number] => ({
  type: "text",
  content,
  start,
  end: start + content.length,
})
const joined = (prompt: Prompt) => prompt.map((part) => ("content" in part ? part.content : "")).join("")

describe("the Ask draft", () => {
  it("is the outgoing goal bar's wording, left open", () => {
    expect(askAboutStep("count the rows")).toBe('About the step "count the rows": ')
  })
})

describe("drafting into the composer", () => {
  const draft = askAboutStep("count the rows")

  it("fills an empty composer and puts the cursor at the end", () => {
    const next = draftInto([text("")], draft)
    expect(next.prompt).toEqual([text(draft)])
    expect(next.cursor).toBe(draft.length)
  })

  it("treats whitespace alone as empty", () => {
    expect(draftInto([text("  ")], draft).prompt).toEqual([text(draft)])
  })

  it("keeps what somebody typed and adds the draft after a blank line", () => {
    const next = draftInto([text("also check the eval split")], draft)
    expect(joined(next.prompt).startsWith("also check the eval split")).toBe(true)
    expect(joined(next.prompt).endsWith(draft)).toBe(true)
    expect(joined(next.prompt).length).toBe("also check the eval split".length + 2 + draft.length)
    expect(next.cursor).toBe(promptLength(next.prompt))
  })

  it("keeps offsets contiguous so their editor can place the cursor", () => {
    const next = draftInto([text("first")], draft)
    let at = 0
    for (const part of next.prompt) {
      if (!("start" in part)) throw new Error(`a ${part.type} part has no offsets`)
      expect(part.start).toBe(at)
      at = part.end
    }
    expect(at).toBe(next.cursor)
  })

  it("does not append the same draft twice", () => {
    const once = draftInto([text("")], draft)
    const twice = draftInto(once.prompt, draft)
    expect(twice.prompt).toEqual(once.prompt)
    expect(twice.cursor).toBe(draft.length)
  })
})
