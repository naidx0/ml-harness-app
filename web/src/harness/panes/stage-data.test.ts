import { describe, expect, it } from "vitest"
import { currentRun, latticeRow, readCarve, readRecall, runLabel, trainRuns, type StagePayload, type StageRun } from "./stage-data"

function run(runId: number, verdicts: (boolean | undefined)[], over: Partial<StageRun> = {}): StageRun {
  return {
    run_id: runId,
    complete: true,
    metric: "exact_match",
    prompt_is_default: false,
    model: "m",
    judge_model: null,
    planned: verdicts.length,
    graded: verdicts.filter((v) => v !== undefined).length,
    correct: verdicts.filter(Boolean).length,
    score: null,
    resolution: null,
    rows: verdicts.flatMap((correct, row_index) =>
      correct === undefined ? [] : [{ row_index, correct, failure_mode: null }],
    ),
    ...over,
  }
}

function payload(runs: StageRun[], baseline: number | null): StagePayload {
  return {
    thread_id: 1,
    baseline_run_id: baseline,
    runs,
    comparisons: {},
    sandboxes: [],
    gpu: { occupancy: null, guard: null, crowded_above_gb: 4 },
    diagnosis: null,
    reads: {},
  }
}

describe("latticeRow", () => {
  const baseline = run(1, [true, false, true, false, undefined])

  it("marks flips against the baseline and plain verdicts elsewhere", () => {
    const challenger = run(2, [true, true, false, false, true])
    expect(latticeRow(challenger, baseline, 6)).toEqual(["right", "up", "down", "wrong", "right", "held"])
  })

  it("never draws a flip on the baseline's own row", () => {
    expect(latticeRow(baseline, baseline, 5)).toEqual(["right", "wrong", "right", "wrong", "held"])
  })

  // The outgoing lattice read "baseline did not fail" as "baseline was
  // right", so a row the baseline never graded drew as flipped down.
  it("does not call a row flipped when the baseline never graded it", () => {
    const challenger = run(2, [undefined, undefined, undefined, undefined, false])
    expect(latticeRow(challenger, baseline, 5)[4]).toBe("wrong")
  })

  it("draws plain verdicts when there is no baseline", () => {
    expect(latticeRow(run(3, [true, false]), null, 2)).toEqual(["right", "wrong"])
  })
})

describe("currentRun", () => {
  const runs = [run(1, [true]), run(2, [true]), run(3, [false], { complete: false })]

  it("shows the pick, else the newest complete run, else the newest run", () => {
    expect(currentRun(payload(runs, 1), 1)?.run_id).toBe(1)
    expect(currentRun(payload(runs, 1), null)?.run_id).toBe(2)
    expect(currentRun(payload(runs, 1), 42)?.run_id).toBe(2)
    expect(currentRun(payload([runs[2]], null), null)?.run_id).toBe(3)
    expect(currentRun(payload([], null), null)).toBeNull()
  })
})

describe("runLabel", () => {
  it("names what changed", () => {
    expect(runLabel(run(1, []), 1)).toBe("baseline")
    expect(runLabel(run(2, [], { model: "qwen+adapter" }), 1)).toBe("adapter")
    // Checked before "adapter", which it also contains: the outgoing label
    // put it after, so a disabled adapter read as an adapter.
    expect(runLabel(run(3, [], { model: "qwen (adapter disabled)" }), 1)).toBe("bare base")
    expect(runLabel(run(4, [], { prompt_is_default: true }), 1)).toBe("default prompt")
    expect(runLabel(run(5, []), 1)).toBe("prompt")
  })
})

describe("trainRuns", () => {
  it("keeps training runs with a curve of at least two points", () => {
    const data = payload([], null)
    data.sandboxes = [
      {
        name: "box",
        runs: [
          { name: "a", kind: "train", base_model: null, max_steps: 10, steps: 10, elapsed_seconds: 5, peak_vram_gb: 1, final_loss: 1, curve: [{ step: 0, loss: 2 }, { step: 10, loss: 1 }] },
          { name: "b", kind: "train", base_model: null, max_steps: 10, steps: 1, elapsed_seconds: 1, peak_vram_gb: 1, final_loss: 2, curve: [{ step: 0, loss: 2 }] },
          { name: "c", kind: "eval", base_model: null, max_steps: null, steps: null, elapsed_seconds: 1, peak_vram_gb: null, final_loss: null, curve: [{ step: 0, loss: 2 }, { step: 1, loss: 1 }] },
        ],
      },
    ]
    expect(trainRuns(data).map((entry) => `${entry.box}/${entry.run.name}`)).toEqual(["box/a"])
  })
})

describe("readRecall and readCarve", () => {
  it("reads a recall report only when stampable, the curve and the count are all there", () => {
    const report = { stampable: true, recall_curve: [{ k: 1, hits: 3, of: 4, recall: 0.75 }], questions_scored: 4, index_id: 2 }
    expect(readRecall(report)?.curve).toEqual([{ k: 1, hits: 3, of: 4, recall: 0.75 }])
    expect(readRecall({ ...report, stampable: undefined })).toBeNull()
    expect(readRecall({ index_id: 2, k: 5 })).toBeNull()
  })

  it("reads a carve with its leak check, and refuses a refusal", () => {
    const carve = { eval_path: "e", train_path: "t", into: "d", rows_read: 10, eval_rows: 3, train_rows: 7, verification: { leaked_rows: 0 } }
    expect(readCarve(carve)).toEqual({ rowsRead: 10, evalRows: 3, trainRows: 7, leaked: 0, checked: true })
    expect(readCarve({ ...carve, verification: undefined })?.checked).toBe(false)
    expect(readCarve({ ...carve, nothing_was_written: true })).toBeNull()
    expect(readCarve({ eval_path: "e" })).toBeNull()
  })
})
