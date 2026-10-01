import { describe, expect, it } from "vitest"
import { factsInClause, FIVE_GATES, gateLedger, readDiagnosis, readEvidence, weakestOrigin } from "./evidence-ledger"

describe("gateLedger", () => {
  it("draws all five gates at Not checked before anything was diagnosed", () => {
    const ledger = gateLedger(null)
    expect(ledger.gates.map((gate) => gate.id)).toEqual(FIVE_GATES.map((gate) => gate.id))
    expect(ledger.gates.every((gate) => gate.status === "NOT_CHECKED")).toBe(true)
    expect([ledger.passed, ledger.of]).toEqual([0, 5])
  })

  it("counts passed gates, maps FAILED to Not met and NOT_REACHED to Not checked", () => {
    const ledger = gateLedger({
      G0_EVAL_SET: { status: "PASSED" },
      G1_BASELINE_MEASURED: { status: "PASSED" },
      G2_PROMPT_EXHAUSTED: { status: "FAILED" },
      G3_RETRIEVAL_CONSIDERED: { status: "NOT_REACHED" },
    })
    expect(ledger.passed).toBe(2)
    expect(ledger.gates.map((gate) => gate.status)).toEqual(["PASSED", "PASSED", "NOT_MET", "NOT_CHECKED", "NOT_CHECKED"])
  })

  it("does not count a gate id that is not one of the five", () => {
    const ledger = gateLedger({ G0_EVAL_SET: { status: "PASSED" }, G9_INVENTED: { status: "PASSED" } })
    expect(ledger.passed).toBe(1)
    expect(ledger.gates).toHaveLength(5)
  })

  // A derived check rather than a hand list: every gate id is distinct, so a
  // ledger keyed by id can never draw one gate's status on two rows.
  it("keys the five gates by distinct ids", () => {
    expect(new Set(FIVE_GATES.map((gate) => gate.id)).size).toBe(FIVE_GATES.length)
  })
})

describe("where a gate's facts came from", () => {
  const origins = { eval_size_n: "MEASURED", baseline_measured: "STATED", prompt_tries: "ASSERTED", overlap: "DEFAULTED" }

  it("names only declared facts that appear in the clause", () => {
    expect(factsInClause("eval_size_n >= 30 and baseline_measured", origins)).toEqual(["baseline_measured", "eval_size_n"])
    expect(factsInClause(null, origins)).toEqual([])
  })

  it("answers with the weakest origin, skipping untouched defaults", () => {
    expect(weakestOrigin(["eval_size_n", "baseline_measured"], origins)).toBe("STATED")
    expect(weakestOrigin(["eval_size_n", "prompt_tries"], origins)).toBe("ASSERTED")
    expect(weakestOrigin(["eval_size_n", "overlap"], origins)).toBe("MEASURED")
    expect(weakestOrigin(["overlap"], origins)).toBeNull()
  })
})

describe("readDiagnosis", () => {
  const good = {
    ok: true,
    outcome: "NO_TRAIN__FIX_THE_PROMPT",
    verdict: "no_train",
    say: "Rewrite the prompt.",
    gate_ledger: { G0_EVAL_SET: { status: "PASSED", clause: "eval_size_n >= 30" } },
    fact_origins: { eval_size_n: "MEASURED" },
  }

  it("reads a run_diagnosis result", () => {
    const diagnosis = readDiagnosis(good)!
    expect(diagnosis.outcome).toBe("NO_TRAIN__FIX_THE_PROMPT")
    expect(diagnosis.gateLedger.G0_EVAL_SET).toEqual({ status: "PASSED", clause: "eval_size_n >= 30" })
  })

  it("refuses a ledger with a status it does not know, or no outcome", () => {
    expect(readDiagnosis({ ...good, gate_ledger: { G0_EVAL_SET: { status: "MAYBE" } } })).toBeNull()
    expect(readDiagnosis({ ...good, outcome: undefined })).toBeNull()
    expect(readDiagnosis({ ...good, ok: false })).toBeNull()
  })
})

describe("readEvidence", () => {
  it("reads rows and counts the rows no gate can see", () => {
    const ledger = readEvidence({
      rows: [{ id: 1, fact: "eval_size_n", value: 30, origin: "MEASURED", actor: "harness", tool: "count_rows", how: "counted" }],
      quarantined: [{}, {}],
      unscoped: [{}],
    })
    expect(ledger.rows[0]).toMatchObject({ fact: "eval_size_n", origin: "MEASURED", tool: "count_rows" })
    expect([ledger.quarantined, ledger.unscoped]).toEqual([2, 1])
    expect(readEvidence(undefined)).toEqual({ rows: [], quarantined: 0, unscoped: 0 })
  })
})
