import { describe, expect, it } from "vitest"
import { currentReport, distinctReports, dominantMode, readEvalReport, scoreIsAnOpinion } from "./eval-report"

const run = (over: Record<string, unknown> = {}) => ({
  ok: true,
  run_id: 4,
  planned: 30,
  graded: 30,
  correct: 21,
  complete: true,
  metric: "exact_match",
  score: 0.7,
  resolution: { n: 30, ci_95: [0.52, 0.83], half_width_points: 15.6, resolves_a_difference_of_at_least_points: 25 },
  failure_histogram: { wrong_format: 6, wrong_facts: 3 },
  failures: [{ row_index: 2, input: "q", expected: "a", answer: "b", verdicts: { exact_match: false } }],
  failures_total: 9,
  ...over,
})

describe("readEvalReport", () => {
  it("reads a run with its score and its interval together", () => {
    const report = readEvalReport(run())!
    expect(report.runId).toBe(4)
    expect(report.score).toBe(0.7)
    expect(report.resolution.ci95).toEqual([0.52, 0.83])
    expect(report.failures[0].verdicts).toEqual({ exact_match: false })
  })

  it("refuses a comparison, a failed result and anything without planned and graded", () => {
    expect(readEvalReport(run({ against: 3 }))).toBeNull()
    expect(readEvalReport(run({ ok: false }))).toBeNull()
    expect(readEvalReport(run({ planned: undefined }))).toBeNull()
    expect(readEvalReport({ ok: true, score: 1 })).toBeNull()
  })

  it("keeps a run with nothing graded as a real run with no interval", () => {
    const report = readEvalReport(run({ graded: 0, score: null, resolution: undefined, complete: false }))!
    expect(report.graded).toBe(0)
    expect(report.score).toBeNull()
    expect(report.resolution.n).toBe(0)
    expect(report.resolution.ci95).toBeNull()
  })
})

describe("the run picker", () => {
  const a = readEvalReport(run({ run_id: 4, failures_total: 9 }))!
  const b = readEvalReport(run({ run_id: 5 }))!
  const aAgain = readEvalReport(run({ run_id: 4, failures_total: 12 }))!

  it("keeps one report per run id, the newest sighting winning", () => {
    const distinct = distinctReports([aAgain, b, a])
    expect(distinct.map((report) => report.runId)).toEqual([4, 5])
    expect(distinct[0].failuresTotal).toBe(12)
  })

  it("shows the pick, or the newest when nothing is picked or the pick has gone", () => {
    const reports = distinctReports([b, a])
    expect(currentReport(reports, null)?.runId).toBe(5)
    expect(currentReport(reports, 4)?.runId).toBe(4)
    expect(currentReport(reports, 99)?.runId).toBe(5)
    expect(currentReport([], null)).toBeNull()
  })
})

describe("dominantMode", () => {
  it("routes on a bucket holding at least half the failures, and not below", () => {
    expect(dominantMode({ wrong_format: 5, wrong_facts: 5 })?.dominates).toBe(true)
    expect(dominantMode({ wrong_format: 4, wrong_facts: 3, refuses: 2 })).toMatchObject({
      mode: "wrong_format",
      dominates: false,
    })
    expect(dominantMode({})).toBeNull()
    expect(dominantMode({ wrong_format: 0 })).toBeNull()
  })
})

describe("scoreIsAnOpinion", () => {
  it("is true for a model-graded metric and for any run a model judged", () => {
    expect(scoreIsAnOpinion(readEvalReport(run())!)).toBe(false)
    expect(scoreIsAnOpinion(readEvalReport(run({ metric: "model_graded" }))!)).toBe(true)
    expect(scoreIsAnOpinion(readEvalReport(run({ self_graded: { judge_model: "m", rows_judged: 3 } }))!)).toBe(true)
  })
})
