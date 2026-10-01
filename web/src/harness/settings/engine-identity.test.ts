import { describe, expect, it } from "vitest"
import { failedChecks, healthFailure, notReadyHealth } from "./engine-identity"

const NOT_READY = {
  status: "not_ready",
  checks: [
    { name: "process", ok: true, detail: "pid 10" },
    { name: "database_opens", ok: false, detail: "no such file" },
  ],
}

describe("Settings > Engine on an engine that is up but not ready", () => {
  it("reads the 503's readout, so the failing checks can be listed", () => {
    const failure = Object.assign(new Error("503 from /health"), { status: 503, body: NOT_READY })
    const readout = notReadyHealth(failure)
    expect(readout?.status).toBe("not_ready")
    expect(failedChecks(readout)).toEqual([{ name: "database_opens", ok: false, detail: "no such file" }])
  })

  it("has no readout for anything but a 503 with a body", () => {
    expect(notReadyHealth(Object.assign(new Error("x"), { status: 409, body: NOT_READY }))).toBeUndefined()
    expect(notReadyHealth(Object.assign(new Error("x"), { status: 503, body: "Service Unavailable" }))).toBeUndefined()
    expect(notReadyHealth(new TypeError("Failed to fetch"))).toBeUndefined()
  })

  it("keeps the sentences for what cannot be read as a readout", () => {
    expect(healthFailure(409, "x")).toMatch(/not the engine this window expected/)
    expect(healthFailure(undefined, "Failed to fetch")).toBe("Failed to fetch")
  })
})
