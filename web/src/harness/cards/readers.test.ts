import { describe, expect, it } from "vitest"
import {
  foldRepeats,
  readCarveCard,
  readChunkingSweep,
  readDiagnosisCard,
  readEffects,
  readEvalComparison,
  readPlanChange,
  readPlanTick,
  readProposal,
  readSandboxResult,
  readStorm,
  stormIdFor,
} from "./readers"
import { baseName, harnessOf, threadIdFor } from "./result"

describe("harnessOf - the facade's envelope", () => {
  it("reads the envelope translate.py writes", () => {
    const envelope = harnessOf({
      harness: { tool: "run_eval", callID: "c1", ok: true, result: { ok: true }, drivenBy: "user", via: "facade" },
    })
    expect(envelope).toMatchObject({ tool: "run_eval", callID: "c1", ok: true, result: { ok: true }, drivenBy: "user", via: "facade" })
    expect(envelope?.omitted).toBeNull()
  })

  it("says a result was over the bound rather than drawing nothing", () => {
    const envelope = harnessOf({ harness: { tool: "t", callID: "c", ok: true, resultOmitted: { chars: 300000, limit: 200000 } } })
    expect(envelope?.result).toBeUndefined()
    expect(envelope?.omitted).toEqual({ chars: 300000, limit: 200000 })
  })

  it("is null for a part the facade did not write", () => {
    expect(harnessOf({})).toBeNull()
    expect(harnessOf(undefined)).toBeNull()
    expect(harnessOf({ harness: "no" })).toBeNull()
  })
})

describe("threadIdFor", () => {
  const sessions = [
    { id: "ses_client_minted", metadata: { harness: { threadID: 42 } } },
    { id: "ses_7", metadata: { harness: { threadID: 9 } } },
    { id: "ses_8" },
  ]

  it("reads the thread off the session's own metadata", () => {
    expect(threadIdFor("ses_client_minted", sessions)).toBe(42)
  })

  it("asks the metadata before the id's digits", () => {
    // `ses_7` names thread 9 in its metadata; the digits must not win.
    expect(threadIdFor("ses_7", sessions)).toBe(9)
  })

  it("does not decode a listed session that carries no thread", () => {
    expect(threadIdFor("ses_8", sessions)).toBeUndefined()
  })

  it("falls back to the facade's own ses_<n> only for an unlisted session", () => {
    expect(threadIdFor("ses_12", sessions)).toBe(12)
    expect(threadIdFor("ses_abc", sessions)).toBeUndefined()
    expect(threadIdFor(undefined, sessions)).toBeUndefined()
  })
})

describe("baseName", () => {
  it("takes the last segment under either separator", () => {
    const back = String.fromCharCode(92)
    expect(baseName(["C:", "data", "eval.jsonl"].join(back))).toBe("eval.jsonl")
    expect(baseName("C:/data/train.jsonl")).toBe("train.jsonl")
    expect(baseName("plain")).toBe("plain")
  })
})

describe("readDiagnosisCard", () => {
  const payload = {
    ok: true,
    outcome: "BLOCKED__NO_EVAL_SET",
    verdict: "BLOCKED",
    say: "No eval set.",
    gate_ledger: {
      G0_EVAL_SET: { status: "FAILED", clause: "eval_size_n >= 50", unsubstantiated: ["eval_size_n"] },
      G1_BASELINE_MEASURED: { status: "NOT_REACHED" },
    },
    fact_origins: { eval_size_n: "ASSERTED" },
    facts_used: { eval_size_n: { value: 120, origin: "ASSERTED", how: "supplied with this call by the model" } },
    unsubstantiated: [
      {
        fact: "eval_size_n",
        gate: "G0_EVAL_SET",
        declared_source: "measure_eval_set",
        origin: "ASSERTED",
        substantiation: "You have told me there is an eval set. I have not seen it.",
        next_step: { fact: "eval_size_n", tool: "measure_eval_set", run_as: "harness", verb: "count the rows" },
      },
    ],
    alternatives: [{ move: "measure", text: "Measure the eval set", tool: "measure_eval_set", starts_now: true }, { text: "" }],
    revisit_if: ["an eval set is measured", ""],
    help: "Point me at the file.",
  }

  it("reads the verdict, the claims, the moves and the revisit conditions", () => {
    const d = readDiagnosisCard(payload)!
    expect(d.verdict).toBe("BLOCKED")
    expect(d.unsubstantiated[0].nextStep).toMatchObject({ tool: "measure_eval_set", runAs: "harness", verb: "count the rows" })
    expect(d.unsubstantiatedByGate.G0_EVAL_SET).toEqual(["eval_size_n"])
    // An alternative with no words is not a move, and a blank condition is not a condition.
    expect(d.alternatives.map((one) => one.text)).toEqual(["Measure the eval set"])
    expect(d.revisitIf).toEqual(["an eval set is measured"])
    expect(d.factsUsed.eval_size_n.value).toBe(120)
  })

  it("accepts exactly what the Evidence pane's reader accepts", () => {
    expect(readDiagnosisCard({ ...payload, ok: false })).toBeNull()
    expect(readDiagnosisCard({ ...payload, gate_ledger: { G0_EVAL_SET: { status: "MAYBE" } } })).toBeNull()
  })
})

describe("readProposal and the storms", () => {
  const build = {
    id: "b1",
    title: "Try a better prompt",
    for_outcome: "PROMPT",
    steps: [{ id: "s1", tool: "try_prompt", why: "the cheapest move", needs: [], exit_criterion: { stated: "a version beats v1" } }],
    cost: {
      model_tokens: { provenance: "INFERRED", value: 1200, unit: "tokens", how: "rows x prompt" },
      wall_clock: { provenance: "UNKNOWN", value: null, unit: "seconds", how: "not measured", find_out_by: "run one row" },
    },
    exit_criterion: { stated: "the score clears 80%" },
  }

  it("reads a proposal and keeps the raw build the approval compares against", () => {
    const proposal = readProposal({ ok: true, approve: "fp1", build })!
    expect(proposal.approve).toBe("fp1")
    expect(proposal.raw).toBe(build)
    expect(proposal.build.cost.wall_clock).toMatchObject({ provenance: "UNKNOWN", value: null, findOutBy: "run one row" })
    expect(proposal.build.exit).toBe("the score clears 80%")
  })

  it("refuses a plan with a step that names no tool", () => {
    expect(readProposal({ ok: true, approve: "fp1", build: { ...build, steps: [{ id: "s1" }] } })).toBeNull()
    expect(readProposal({ ok: true, approve: "", build })).toBeNull()
  })

  it("finds the storm by the fingerprint the engine keeps, never by position", () => {
    const list = { storms: [{ id: 3, fingerprint: "other" }, { id: 2, fingerprint: "fp1" }] }
    expect(stormIdFor(list, "fp1")).toBe(2)
    expect(stormIdFor(list, "missing")).toBeNull()
  })

  it("reads a storm and drops a step whose state is not one of the engine's", () => {
    const storm = readStorm({
      storm: 2,
      state: "running",
      live: true,
      manifest: { fingerprint: "fp1", approved_at: "2026-09-22T10:00:00" },
      steps: [
        { id: "s1", tool: "try_prompt", state: "done" },
        { id: "s2", tool: "run_eval", state: "exploded" },
      ],
    })!
    expect(storm.steps.map((step) => step.id)).toEqual(["s1"])
    expect(storm.fingerprint).toBe("fp1")
  })
})

describe("readEvalComparison", () => {
  const base = { ok: true, run_id: 5, against: 4, p_value: 0.03, verdict: "different", resolved: true, delta: 0.12 }

  it("reads a resolved comparison", () => {
    expect(readEvalComparison(base)).toMatchObject({ resolved: true, verdict: "different", delta: 0.12, sameRows: false })
  })

  it("refuses a payload whose verdict and resolved disagree, rather than picking the optimistic half", () => {
    expect(readEvalComparison({ ...base, resolved: false })).toBeNull()
    expect(readEvalComparison({ ...base, verdict: "better" })).toBeNull()
  })
})

describe("readChunkingSweep", () => {
  const base = { levers: {}, stamps_nothing: "stamps nothing" }
  it("tells a refusal, a plan, and a comparison apart", () => {
    expect(readChunkingSweep({ ...base, ok: false })?.state).toBe("refused")
    expect(readChunkingSweep({ ...base, ok: true, ran: false, settings: [{ passage_chars: 400, passage_overlap: 50, passages: 90 }] }))
      .toMatchObject({ state: "plan", planned: ["400/50 · 90 passages"] })
    expect(readChunkingSweep({ ...base, ok: true, ran: true, verdict: "nothing_was_compared" })?.state).toBe("nothing_compared")
    expect(readChunkingSweep({ ...base, ok: true, ran: true, verdict: "no_evidence" })?.state).toBe("compared")
  })
})

describe("readCarveCard", () => {
  it("reads what was written, and is disjoint from a refusal on nothing_was_written", () => {
    const carve = { ok: true, eval_path: "e", train_path: "t", into: "d", verification: { ran: true, leaked_rows: 0 }, rows_read: 10 }
    expect(readCarveCard(carve)?.leakage).toMatchObject({ ran: true, leaked: 0 })
    expect(readCarveCard({ ...carve, nothing_was_written: true })).toBeNull()
  })
})

describe("readSandboxResult", () => {
  it("keys on a sandbox name together with reach, adapter or run_dir", () => {
    expect(readSandboxResult({ sandbox: "s", run_dir: "r", exit_code: 1, ok: false })).toMatchObject({ ok: false, exitCode: 1 })
    expect(readSandboxResult({ sandbox: "s" })).toBeNull()
  })
})

describe("plan reads", () => {
  it("reads the diff plandiff.py writes, and nothing from an event without one", () => {
    const change = readPlanChange({
      diff: { rows: [{ kind: "del", old: 3, cur: null, text: "- [ ] a" }, { kind: "add", old: null, cur: 3, text: "- [x] a" }], added: 1, removed: 1, clipped: 0 },
    })
    expect(change?.rows).toHaveLength(2)
    expect(readPlanChange({ diff: { rows: [] } })).toBeNull()
    expect(readPlanChange({})).toBeNull()
  })

  it("reads a tick, an unpark and a save", () => {
    expect(readPlanTick({ ok: true, ticked: "a", open_steps: ["b"], done: 1, of: 2 })).toMatchObject({ ticked: "a", done: 1, of: 2 })
    expect(readPlanTick({ step: "b", open_steps: [] })?.step).toBe("b")
    expect(readPlanTick({ ok: true, saved: true })?.saved).toBe(true)
    expect(readPlanTick({ ok: true })).toBeNull()
  })
})

describe("readEffects and foldRepeats", () => {
  it("reads turn.effects and computes empty when the engine left it out", () => {
    expect(readEffects({ steps_done: ["a"], can_revert: true })).toMatchObject({ stepsDone: ["a"], canRevert: true, empty: false })
    expect(readEffects({}).empty).toBe(true)
    expect(readEffects({ empty: true, steps_done: ["a"] }).empty).toBe(true)
  })

  it("folds the same stamp repeated in one turn into one row with a count", () => {
    const fact = { fact: "eval_size_n = 120", origin: "MEASURED", tool: "measure_eval_set" }
    const folded = foldRepeats([fact, { ...fact }, { ...fact, origin: "STATED" }])
    expect(folded.map((row) => row.times)).toEqual([2, 1])
  })
})
