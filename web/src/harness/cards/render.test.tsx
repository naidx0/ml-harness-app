import { render } from "solid-js/web"
import { afterEach, describe, expect, it } from "vitest"
import { HarnessResultCard } from "./card"
import { SPECIMENS } from "./test-specimens"
import type { CardKind } from "./kinds"

/**
 * Every card mounts, in their chrome, from a specimen of its result - and a
 * result no reader knows mounts their own default. A smoke test: it proves
 * the bodies run (no throw, the words a person reads are there), not how
 * they look. No thread is open here, so nothing is fetched.
 */

const TOOL_FOR: Record<CardKind, string> = {
  diagnosis: "run_diagnosis",
  proposal: "propose_build",
  eval: "run_eval",
  compare: "read_eval_results",
  prompt: "try_prompt",
  sweep: "compare_chunkings",
  recall: "measure_retriever_recall",
  carve: "carve_eval_set",
  synthesis: "synthesize_rows",
  "verification-sample": "draw_verification_sample",
  verification: "record_verification",
  sandbox: "run_in_sandbox",
  plan: "mark_step_done",
}

/** A word each card must show, so a blank body cannot pass. */
const SAYS: Record<CardKind, string> = {
  diagnosis: "Gate ledger",
  proposal: "Allow once",
  eval: "What this many rows can resolve",
  compare: "No evidence",
  prompt: "Version 2 is the new one to beat",
  sweep: "NO EVIDENCE",
  recall: "recall at",
  carve: "Written",
  synthesis: "What was amplified",
  "verification-sample": "Your turn",
  verification: "What you recorded",
  sandbox: "lora-try",
  plan: "Ticked: Measure the baseline",
}

let dispose: (() => void) | undefined
afterEach(() => {
  dispose?.()
  dispose = undefined
  document.body.innerHTML = ""
})

function mount(tool: string, result: unknown) {
  const host = document.createElement("div")
  document.body.append(host)
  dispose = render(
    () => (
      <HarnessResultCard
        tool={tool}
        input={{}}
        status="completed"
        metadata={{ harness: { tool, callID: "c1", ok: true, result } }}
      />
    ),
    host,
  )
  return host
}

describe("each harness card mounts from its result", () => {
  for (const [kind, specimen] of Object.entries(SPECIMENS) as [CardKind, unknown][]) {
    it(`${kind}`, () => {
      const prompt = kind === "prompt" ? { ...(specimen as object), champion_changed: true } : specimen
      const host = mount(TOOL_FOR[kind], prompt)
      expect(host.querySelector('[data-component="harness-card"]')).not.toBeNull()
      expect(host.textContent).toContain(SAYS[kind])
    })
  }

  it("a result no reader recognises mounts their default, not an empty card", () => {
    const host = mount("run_eval", { ok: true, rows: 3 })
    expect(host.querySelector('[data-component="harness-card"]')).toBeNull()
    expect(host.querySelector('[data-component="tool-trigger"]')).not.toBeNull()
  })

  it("a call still running, with no envelope yet, mounts their default", () => {
    const host = document.createElement("div")
    document.body.append(host)
    dispose = render(() => <HarnessResultCard tool="run_eval" input={{}} status="running" metadata={{}} />, host)
    expect(host.querySelector('[data-component="harness-card"]')).toBeNull()
  })
})
