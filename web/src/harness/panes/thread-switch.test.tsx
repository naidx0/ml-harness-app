import { createSignal, type Component } from "solid-js"
import { render } from "solid-js/web"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { PaneProps } from "../panel/panes"

/**
 * Switching the open conversation must not leave the previous one's data on
 * screen. The per-thread panes wrapped their body in an UNKEYED Show, so the
 * body stayed mounted across a switch and `useHarnessRead` kept handing back
 * the previous thread's last value until the new read answered - a second
 * conversation showed the first one's score, gates or runs.
 *
 * Each case answers thread 1, switches to thread 2 with its read still out,
 * and asserts thread 1's words are gone and the pane says it is reading.
 */

// One pending request per path, so a test answers exactly the read it means.
const pending = new Map<string, { resolve: (value: unknown) => void; reject: (error: unknown) => void }>()
vi.mock("../engine", () => ({
  harness: (path: string) => new Promise((resolve, reject) => pending.set(path, { resolve, reject })),
}))

const tick = () => new Promise((done) => setTimeout(done, 0))
const NL = String.fromCharCode(10)
const frame = (id: number, kind: string, payload: unknown) =>
  `id: ${id}${NL}event: ${kind}${NL}data: ${JSON.stringify(payload)}${NL}${NL}`
const events = (id: number) => `/api/events?scope=thread:${id}&since=0&follow=false`

async function answer(path: string, value: unknown) {
  await tick()
  const request = pending.get(path)
  if (!request) throw new Error(`no read of ${path} is out; out: ${[...pending.keys()].join(", ")}`)
  pending.delete(path)
  request.resolve(value)
  await tick()
}

let dispose: (() => void) | undefined
afterEach(() => {
  dispose?.()
  dispose = undefined
  pending.clear()
  document.body.innerHTML = ""
})

function mount(Pane: Component<PaneProps>) {
  const [threadId, setThreadId] = createSignal<number | undefined>(1)
  const host = document.createElement("div")
  document.body.append(host)
  dispose = render(() => <Pane threadId={threadId()} />, host)
  return { host, setThreadId }
}

describe("a per-thread pane drops the previous thread on a switch", () => {
  it("Eval", async () => {
    const { default: EvalPane } = await import("./eval")
    const { host, setThreadId } = mount(EvalPane as Component<PaneProps>)
    await tick()
    // Before the log answers: reading, not "no eval run".
    expect(host.textContent).toContain("Reading…")
    expect(host.textContent).not.toContain("No eval run")
    const run = { ok: true, run_id: 4, planned: 10, graded: 10, correct: 7, complete: true, score: 0.7 }
    await answer(events(1), frame(1, "tool.result", { id: "a", name: "run_eval", ok: true, result: run }))
    expect(host.textContent).toContain("7 of 10 rows right")

    setThreadId(2)
    await tick()
    expect(host.textContent).not.toContain("7 of 10 rows right")
    expect(host.textContent).toContain("Reading…")
    await answer(events(2), "")
    expect(host.textContent).toContain("No eval run in this conversation yet")
  })

  it("Evidence", async () => {
    const { default: EvidencePane } = await import("./evidence")
    const { host, setThreadId } = mount(EvidencePane as Component<PaneProps>)
    await tick()
    expect(host.textContent).toContain("Reading…")
    expect(host.textContent).not.toContain("Nothing decided yet")
    const diagnosis = {
      ok: true,
      outcome: "BLOCKED__NO_EVAL_SET",
      verdict: "BLOCKED",
      say: "There is no eval set yet.",
      gate_ledger: { G0_EVAL_SET: { status: "FAILED", clause: "eval_size_n >= 50" } },
      fact_origins: { eval_size_n: "ASSERTED" },
    }
    await answer(events(1), frame(1, "tool.result", { id: "d", name: "run_diagnosis", ok: true, result: diagnosis }))
    await answer("/api/evidence?thread_id=1", { rows: [{ id: 1, fact: "eval_size_n", value: 12, origin: "MEASURED" }] })
    expect(host.textContent).toContain("There is no eval set yet.")
    expect(host.textContent).toContain("eval_size_n")

    setThreadId(2)
    await tick()
    expect(host.textContent).not.toContain("There is no eval set yet.")
    expect(host.textContent).not.toContain("eval_size_n")
    expect(host.textContent).toContain("Reading…")
  })

  it("Stage", async () => {
    const { default: StagePane } = await import("./stage")
    const { host, setThreadId } = mount(StagePane as Component<PaneProps>)
    await tick()
    expect(host.textContent).toContain("Reading…")
    const stage = {
      thread_id: 1,
      baseline_run_id: null,
      runs: [
        {
          run_id: 9,
          complete: true,
          metric: "exact_match",
          prompt_is_default: false,
          model: "alpha-model-one",
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
        },
      ],
      comparisons: {},
      sandboxes: [],
      gpu: { occupancy: null, guard: null, crowded_above_gb: 4 },
      diagnosis: null,
      reads: {},
    }
    await answer("/api/threads/1/stage", stage)
    await answer(events(1), "")
    expect(host.textContent).toContain("alpha-model-one")

    setThreadId(2)
    await tick()
    expect(host.textContent).not.toContain("alpha-model-one")
    expect(host.textContent).toContain("Reading…")
  })
})
