import { describe, expect, it, vi } from "vitest"
import { facadeFetch } from "./facade-fetch"

function capture() {
  const seen: string[] = []
  const base = vi.fn(async (input: RequestInfo | URL) => {
    seen.push(input instanceof Request ? input.url : String(input))
    return new Response("{}")
  }) as unknown as typeof fetch
  return { base, seen }
}

describe("their client's requests reach the facade", () => {
  it("puts /oc back on an engine /api request, which their client drops", async () => {
    const { base, seen } = capture()
    await facadeFetch(base, "http://127.0.0.1:8078")("http://127.0.0.1:8078/api/session?limit=2")
    expect(seen).toEqual(["http://127.0.0.1:8078/oc/api/session?limit=2"])
  })

  it("keeps the method, headers and body - and the body is buffered, not a stream", async () => {
    let init: RequestInit | undefined
    const base = (async (_input: RequestInfo | URL, given?: RequestInit) => {
      init = given
      return new Response("{}")
    }) as typeof fetch
    await facadeFetch(base, "http://127.0.0.1:8078")("http://127.0.0.1:8078/api/session", {
      method: "POST",
      headers: { Authorization: "Basic x" },
      body: '{"a":1}',
    })
    expect(init!.method).toBe("POST")
    expect(new Headers(init!.headers).get("authorization")).toBe("Basic x")
    // A ReadableStream body is what Chromium refuses over HTTP/1.1.
    expect(init!.body).toBeInstanceOf(ArrayBuffer)
    expect(new TextDecoder().decode(init!.body as ArrayBuffer)).toBe('{"a":1}')
  })

  it("leaves other origins and non-api paths alone", async () => {
    const { base, seen } = capture()
    const f = facadeFetch(base, "http://127.0.0.1:8078")
    await f("https://example.com/api/thing")
    await f("http://127.0.0.1:8078/health")
    expect(seen).toEqual(["https://example.com/api/thing", "http://127.0.0.1:8078/health"])
  })
})
