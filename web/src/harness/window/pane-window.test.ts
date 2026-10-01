import { describe, expect, it } from "vitest"
import { paneWindowRequest } from "./pane-window"

describe("which window this is", () => {
  it("the main window has no pane in its query", () => {
    expect(paneWindowRequest("")).toBeUndefined()
  })

  it("open_pane's URL names a pane and a thread", () => {
    expect(paneWindowRequest("?pane=plan&thread=7")).toEqual({ pane: "plan", threadId: 7 })
  })

  it("open_stage's URL is the Stage for a thread", () => {
    expect(paneWindowRequest("?stage=12")).toEqual({ pane: "stage", threadId: 12 })
  })

  it("a thread that is not a positive integer is no thread", () => {
    expect(paneWindowRequest("?pane=machine&thread=abc")).toEqual({ pane: "machine", threadId: undefined })
    expect(paneWindowRequest("?pane=machine")).toEqual({ pane: "machine", threadId: undefined })
  })
})
