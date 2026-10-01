import { render } from "solid-js/web"
import { afterEach, describe, expect, it, vi } from "vitest"
import { Lattice } from "./stage-lattice"
import type { StagePayload, StageRun } from "./stage-data"

/**
 * A run can be picked from the lattice by keyboard, not only by mouse, and
 * the picked run wears gold (selection), never the accent (send and focus).
 */

function run(run_id: number): StageRun {
  return {
    run_id,
    complete: true,
    metric: "exact_match",
    prompt_is_default: false,
    model: "m",
    judge_model: null,
    planned: 2,
    graded: 2,
    correct: 1,
    score: 0.5,
    resolution: null,
    rows: [
      { row_index: 0, correct: true, failure_mode: null },
      { row_index: 1, correct: false, failure_mode: null },
    ],
  }
}

const payload: StagePayload = {
  thread_id: 1,
  baseline_run_id: null,
  runs: [run(3), run(4)],
  comparisons: {},
  sandboxes: [],
  gpu: { occupancy: null, guard: null, crowded_above_gb: 4 },
  diagnosis: null,
  reads: {},
}

let dispose: (() => void) | undefined
afterEach(() => {
  dispose?.()
  dispose = undefined
  document.body.innerHTML = ""
})

function mount(selected: StageRun | null) {
  const onPick = vi.fn()
  const host = document.createElement("div")
  document.body.append(host)
  dispose = render(() => <Lattice payload={payload} selected={selected} onPick={onPick} />, host)
  const labels = [...host.querySelectorAll('[role="button"]')] as SVGTextElement[]
  return { host, onPick, labels }
}

describe("the lattice's run labels", () => {
  it("are focusable buttons that Enter and Space pick", () => {
    const { onPick, labels } = mount(null)
    expect(labels.length).toBe(2)
    expect(labels.every((label) => label.getAttribute("tabindex") === "0")).toBe(true)
    labels[1].dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }))
    labels[0].dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true }))
    labels[0].dispatchEvent(new KeyboardEvent("keydown", { key: "a", bubbles: true }))
    expect(onPick.mock.calls).toEqual([[4], [3]])
  })

  it("sit in a group, not an image that would hide them", () => {
    const { host } = mount(null)
    expect(host.querySelector("svg")!.getAttribute("role")).toBe("group")
  })

  it("mark the selected run in gold, not the accent", () => {
    const { labels } = mount(payload.runs[1])
    expect(labels[1].getAttribute("fill")).toBe("var(--harness-gold)")
    expect(labels[1].getAttribute("aria-pressed")).toBe("true")
    expect(labels[0].getAttribute("fill")).not.toContain("accent")
  })
})
