import { describe, expect, it } from "vitest"
import { allReadsOf, eventsPath, latestReadOf, liveWork, parseSse, toolResults, type ThreadEvent } from "./eval-events"

// The engine's own frame shape (app/events.py `frame`), built rather than
// typed so no literal escape has to survive a file write.
const NL = String.fromCharCode(10)
const CR = String.fromCharCode(13)
function frame(id: number, kind: string, payload: unknown) {
  return `id: ${id}${NL}event: ${kind}${NL}data: ${JSON.stringify(payload)}${NL}${NL}`
}

describe("parseSse", () => {
  it("reads the engine's frames in order, with ids, kinds and JSON payloads", () => {
    const body = frame(1, "message.created", { role: "user" }) + frame(2, "tool.result", { ok: true, result: { a: 1 } })
    expect(parseSse(body)).toEqual([
      { id: 1, kind: "message.created", payload: { role: "user" } },
      { id: 2, kind: "tool.result", payload: { ok: true, result: { a: 1 } } },
    ])
  })

  it("skips keep-alive comments and reads a body with no trailing blank line", () => {
    const body = `: keep-alive${NL}${NL}` + frame(5, "a", 1) + `id: 6${NL}event: b${NL}data: 2`
    expect(parseSse(body).map((event) => [event.id, event.kind, event.payload])).toEqual([
      [5, "a", 1],
      [6, "b", 2],
    ])
  })

  it("accepts CRLF and CR line endings", () => {
    const crlf = frame(1, "a", { x: 1 }).split(NL).join(CR + NL)
    const cr = frame(2, "b", { y: 2 }).split(NL).join(CR)
    expect(parseSse(crlf + cr).map((event) => event.payload)).toEqual([{ x: 1 }, { y: 2 }])
  })

  it("joins several data lines with a newline and keeps a non-JSON payload as text", () => {
    const body = `id: 3${NL}event: note${NL}data: first${NL}data: second${NL}${NL}`
    expect(parseSse(body)).toEqual([{ id: 3, kind: "note", payload: `first${NL}second` }])
  })

  it("returns nothing for an empty history", () => {
    expect(parseSse("")).toEqual([])
  })
})

describe("toolResults", () => {
  const events: ThreadEvent[] = [
    { id: 1, kind: "tool.call", payload: { id: "a", name: "run_eval" } },
    { id: 2, kind: "tool.result", payload: { id: "a", name: "run_eval", ok: true, result: { n: 1 } } },
    { id: 3, kind: "tool.result", payload: { id: "b", name: "run_diagnosis", ok: false, result: { n: 2 } } },
    { id: 4, kind: "tool.result", payload: { id: "c", name: "run_eval", ok: true, result: { n: 3 } } },
  ]

  it("keeps only successful results, oldest first", () => {
    expect(toolResults(events).map((result) => result.id)).toEqual([2, 4])
  })

  it("reads newest first, and the latest is the first of all reads", () => {
    const read = (value: unknown) => ((value as { n?: number }).n ?? null)
    const results = toolResults(events)
    expect(allReadsOf(results, read)).toEqual([3, 1])
    expect(latestReadOf(results, read)).toBe(allReadsOf(results, read)[0])
    expect(latestReadOf(results, () => null)).toBeNull()
  })
})

describe("liveWork", () => {
  it("counts an eval as spending from eval.started until it finishes, and carries its progress", () => {
    const started: ThreadEvent[] = [
      { id: 1, kind: "eval.started", payload: { run_id: 7, planned: 30, already_graded: 4 } },
      { id: 2, kind: "eval.progress", payload: { run_id: 7, graded: 12 } },
    ]
    expect(liveWork(started).evals).toEqual([{ runId: 7, graded: 12, planned: 30 }])
    for (const end of ["eval.finished", "eval.interrupted", "eval.reused"]) {
      expect(liveWork([...started, { id: 3, kind: end, payload: { run_id: 7 } }]).evals).toEqual([])
    }
  })

  it("counts a training job as spending until a terminal event, ignoring log lines", () => {
    const running: ThreadEvent[] = [
      { id: 1, kind: "train.started", payload: { job_id: "j1" } },
      { id: 2, kind: "train.log", payload: { job_id: "j1" } },
    ]
    expect(liveWork(running).trains).toEqual(["j1"])
    expect(liveWork([...running, { id: 3, kind: "train.finished", payload: { job_id: "j1" } }]).trains).toEqual([])
    // A job seen only through log lines has no terminal event, so it spends.
    expect(liveWork([{ id: 1, kind: "train.log", payload: { job_id: "j2" } }]).trains).toEqual(["j2"])
  })

  it("keeps two runs apart by run id", () => {
    const events: ThreadEvent[] = [
      { id: 1, kind: "eval.started", payload: { run_id: 1, planned: 10 } },
      { id: 2, kind: "eval.started", payload: { run_id: 2, planned: 20 } },
      { id: 3, kind: "eval.finished", payload: { run_id: 1 } },
    ]
    expect(liveWork(events).evals.map((run) => run.runId)).toEqual([2])
  })
})

describe("eventsPath", () => {
  it("asks for the whole history and no follow, so the response ends", () => {
    expect(eventsPath(33)).toBe("/api/events?scope=thread:33&since=0&follow=false")
  })
})
