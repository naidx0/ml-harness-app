import { describe, expect, it } from "vitest"
import type { ServerConnection } from "@/runtime/server/registry"
import { harness, HarnessError, sentenceOf, setHarnessEngine } from "./engine"

describe("an engine refusal as a sentence", () => {
  it("a plain detail is the sentence", () => {
    expect(sentenceOf("No model is connected.")).toBe("No model is connected.")
  })

  it("FastAPI's validation list keeps every message", () => {
    expect(sentenceOf([{ msg: "field required" }, { msg: "not a path" }])).toBe("field required; not a path")
  })

  it("a structured detail yields its message", () => {
    expect(sentenceOf({ message: "This tool needs an open conversation." })).toBe(
      "This tool needs an open conversation.",
    )
    expect(sentenceOf({ reason: "refused", tool: "x" })).toBe("refused")
  })

  it("nothing readable is nothing, so the caller falls back to the status", () => {
    expect(sentenceOf({ code: 7 })).toBeUndefined()
    expect(sentenceOf(undefined)).toBeUndefined()
  })
})

const server = { http: { url: "http://engine.test/oc", password: "t" } } as unknown as ServerConnection.Any

describe("a refused request", () => {
  it("keeps the parsed body on the error, beside the engine's sentence", async () => {
    const body = { status: "not_ready", checks: [{ name: "schema_agrees", ok: false, detail: "behind" }] }
    setHarnessEngine(server, async () => new Response(JSON.stringify(body), { status: 503 }))
    const failure = await harness("/health").catch((error: unknown) => error)
    expect(failure).toBeInstanceOf(HarnessError)
    expect((failure as HarnessError).status).toBe(503)
    expect((failure as HarnessError).body).toEqual(body)
  })

  it("still leads with the engine's detail", async () => {
    setHarnessEngine(server, async () => new Response(JSON.stringify({ detail: "thread not found" }), { status: 404 }))
    const failure = (await harness("/api/threads/9").catch((error: unknown) => error)) as HarnessError
    expect(failure.message).toBe("thread not found")
    expect(failure.body).toEqual({ detail: "thread not found" })
  })
})
