import { describe, expect, it } from "vitest"
import { classify, failingChecks, identityOf, readingOfFailure } from "./liveness"

const A = { engine: { pid: 10, engine_id: "a" }, build: { code_fingerprint: "f1" } }
const NOT_READY = {
  ...A,
  status: "not_ready",
  checks: [
    { name: "process", ok: true, detail: "pid 10" },
    { name: "schema_agrees", ok: false, detail: "code knows 41, database is at 40" },
  ],
}

describe("engine liveness", () => {
  it("says nothing while the same engine answers", () => {
    expect(classify(identityOf(A), A)).toBe("ok")
  })

  it("an engine that does not answer is gone", () => {
    expect(classify(identityOf(A), undefined)).toBe("gone")
  })

  it("a different engine answering is a restart, even on the same code", () => {
    expect(classify(identityOf(A), { ...A, engine: { pid: 11, engine_id: "b" } })).toBe("restarted")
  })

  it("the first reading is the baseline, not a verdict", () => {
    expect(classify(undefined, A)).toBe("ok")
  })

  it("a reading without identity fields is not taken for a restart", () => {
    expect(classify(identityOf(A), {})).toBe("ok")
  })
})

describe("an engine that answers 503", () => {
  it("is up but not ready - not gone", () => {
    expect(classify(identityOf(A), { status: 503, health: NOT_READY })).toBe("not-ready")
  })

  it("is not ready on the very first reading too", () => {
    expect(classify(undefined, { status: 503, health: NOT_READY })).toBe("not-ready")
  })

  it("is still a restart when it is a different engine", () => {
    expect(classify(identityOf(A), { status: 503, health: { ...NOT_READY, engine: { pid: 11, engine_id: "b" } } })).toBe(
      "restarted",
    )
  })

  it("is read out of the failed request, body and all", () => {
    const failure = Object.assign(new Error("503 from /health"), { status: 503, body: NOT_READY })
    const reading = readingOfFailure(failure)
    expect(reading?.status).toBe(503)
    expect(classify(identityOf(A), reading)).toBe("not-ready")
    expect(failingChecks(reading?.health)).toEqual([NOT_READY.checks[1]])
  })

  it("a failure with no body is no reading, which is gone", () => {
    expect(readingOfFailure(new TypeError("Failed to fetch"))).toBeUndefined()
    expect(readingOfFailure(Object.assign(new Error("x"), { status: 502, body: "<html>" }))).toBeUndefined()
    expect(classify(identityOf(A), readingOfFailure(new TypeError("Failed to fetch")))).toBe("gone")
  })
})
