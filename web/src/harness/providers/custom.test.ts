import { beforeEach, describe, expect, it, vi } from "vitest"

const harness = vi.fn<(path: string, init?: { body?: Record<string, unknown>; method?: string }) => Promise<unknown>>()
vi.mock("../engine", () => ({
  harness: (path: string, init?: never) => harness(path, init),
  HarnessError: class HarnessError extends Error {
    constructor(
      readonly status: number,
      message: string,
    ) {
      super(message)
    }
  },
}))

const { saveHarnessCustomProvider } = await import("./custom")
const { HarnessError } = await import("../engine")

const form = (key?: string) => ({
  name: "LM Studio",
  key,
  config: {
    options: { baseURL: "http://127.0.0.1:1234/v1" },
    models: { a: { name: "Model A" }, b: { name: "Model B" }, c: { name: "Model C" } },
  },
})

let calls: string[] = []
beforeEach(() => {
  calls = []
  harness.mockReset()
})

describe("saving their custom-provider form", () => {
  it("says which connections were saved without a key when the keychain is missing, and stops", async () => {
    let made = 0
    harness.mockImplementation(async (path, init) => {
      calls.push(path)
      if (path !== "/api/providers") return {}
      made += 1
      if (made === 2) throw new HarnessError(503, "the connection was saved but the key was not: no keyring backend")
      return { id: made, name: init?.body?.name }
    })
    const failure = (await saveHarnessCustomProvider(form("sk-test")).catch((error: unknown) => error)) as Error
    expect(failure).toBeInstanceOf(Error)
    expect(failure.message).toContain('"Model B" was saved WITHOUT its key')
    expect(failure.message).toContain("no keyring backend")
    expect(failure.message).toContain('"Model A"')
    expect(failure.message).toContain("1 more model was not saved")
    // Stopped cleanly: no third create, nothing activated or probed.
    expect(calls).toEqual(["/api/providers", "/api/providers"])
  })

  it("still activates and probes the first when every create succeeds", async () => {
    let made = 0
    harness.mockImplementation(async (path, init) => {
      calls.push(path)
      if (path !== "/api/providers") return {}
      made += 1
      return { id: made, name: init?.body?.name }
    })
    await saveHarnessCustomProvider(form("sk-test"))
    expect(calls).toEqual([
      "/api/providers",
      "/api/providers",
      "/api/providers",
      "/api/providers/1/activate",
      "/api/providers/1/probe",
    ])
  })

  it("names what was already saved when a later create fails for another reason", async () => {
    let made = 0
    harness.mockImplementation(async (path, init) => {
      if (path !== "/api/providers") return {}
      made += 1
      if (made === 3) throw new HarnessError(422, "base_url is not a URL")
      return { id: made, name: init?.body?.name }
    })
    const failure = (await saveHarnessCustomProvider(form()).catch((error: unknown) => error)) as Error
    expect(failure.message).toContain('Could not save "Model C": base_url is not a URL')
    expect(failure.message).toContain('Already saved: "Model A", "Model B"')
  })
})
