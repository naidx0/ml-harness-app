import { describe, expect, it, vi } from "vitest"
import { createCarriedFetch, isCarried, type Frame } from "./carrier"

/**
 * A fake shell: `engine_stream` hands its frames to the channel the page
 * passed, in order, on later ticks - the way Tauri delivers channel messages.
 */
function shell(frames: Frame[], opts: { hold?: boolean } = {}) {
  let deliver: ((frame: Frame) => void) | undefined
  const calls: { command: string; args?: Record<string, unknown> }[] = []
  const invoke = vi.fn(async (command: string, args?: Record<string, unknown>) => {
    calls.push({ command, args })
    if (command !== "engine_stream") return null
    if (!opts.hold) for (const frame of frames) await Promise.resolve().then(() => deliver?.(frame))
    return null
  })
  const makeChannel = (onFrame: (frame: Frame) => void) => {
    deliver = onFrame
    return "__CHANNEL__:1"
  }
  const fallback = vi.fn(async () => new Response("from the browser"))
  return {
    fetch: createCarriedFetch(invoke, makeChannel, fallback),
    invoke,
    calls,
    fallback,
    push: (frame: Frame) => deliver?.(frame),
  }
}

describe("which requests the shell carries", () => {
  it("carries this machine over plain http and nothing else", () => {
    expect(isCarried("http://127.0.0.1:8078/oc/api/info")).toBe(true)
    expect(isCarried("http://localhost:8078/oc/api/info")).toBe(true)
    expect(isCarried("https://127.0.0.1/")).toBe(false)
    expect(isCarried("http://example.com/")).toBe(false)
    expect(isCarried("http://127.0.0.1.example.com/")).toBe(false)
  })

  it("leaves everything else to the browser", async () => {
    const s = shell([])
    const response = await s.fetch("https://example.com/image.png")
    expect(await response.text()).toBe("from the browser")
    expect(s.invoke).not.toHaveBeenCalled()
  })
})

describe("a carried response", () => {
  it("is a real Response with the engine's status, headers and body", async () => {
    const s = shell([
      { kind: "head", status: 201, headers: [["content-type", "application/json"]] },
      { kind: "chunk", data: '{"ok":' },
      { kind: "chunk", data: "true}" },
      { kind: "end" },
    ])
    const response = await s.fetch("http://127.0.0.1:8078/oc/api/session", {
      method: "POST",
      headers: { Authorization: "Basic abc" },
      body: '{"title":"x"}',
    })
    expect(response.status).toBe(201)
    expect(response.headers.get("content-type")).toBe("application/json")
    expect(await response.json()).toEqual({ ok: true })

    const sent = s.calls.find((call) => call.command === "engine_stream")!.args!
    expect(sent.method).toBe("POST")
    expect(sent.body).toBe('{"title":"x"}')
    // Header names are case-insensitive; browsers lower-case them and
    // happy-dom does not, so compare the way HTTP does.
    const headers = (sent.headers as [string, string][]).map(([name, value]) => [name.toLowerCase(), value])
    expect(headers).toContainEqual(["authorization", "Basic abc"])
  })

  it("streams: the body is readable before the engine has finished", async () => {
    const s = shell([], { hold: true })
    const pending = s.fetch("http://127.0.0.1:8078/oc/api/event")
    await Promise.resolve()
    s.push({ kind: "head", status: 200, headers: [["content-type", "text/event-stream"]] })
    const response = await pending
    const reader = response.body!.getReader()
    s.push({ kind: "chunk", data: "data: one\n\n" })
    const first = await reader.read()
    // Read while the stream is still open - no end frame has been sent.
    expect(new TextDecoder().decode(first.value)).toBe("data: one\n\n")
    s.push({ kind: "end" })
    expect((await reader.read()).done).toBe(true)
  })

  it("a failure before the head rejects like a network error", async () => {
    const s = shell([{ kind: "error", message: "connection refused" }])
    await expect(s.fetch("http://127.0.0.1:8078/oc/api/info")).rejects.toBeInstanceOf(TypeError)
  })

  it("aborting cancels the stream in the shell", async () => {
    const s = shell([], { hold: true })
    const controller = new AbortController()
    const pending = s.fetch("http://127.0.0.1:8078/oc/api/event", { signal: controller.signal })
    await Promise.resolve()
    controller.abort()
    await expect(pending).rejects.toBeDefined()
    expect(s.invoke).toHaveBeenCalledWith("engine_stream_cancel", expect.objectContaining({ id: expect.any(Number) }))
  })
})
