import type { CardKind } from "./kinds"

/* Specimens, one per card, owned by this file: the fields each reader keys on
   and nothing borrowed from another lane's demonstration data. */

export const SPECIMENS: Record<CardKind, unknown> = {
  diagnosis: {
    ok: true,
    outcome: "BLOCKED__NO_EVAL_SET",
    verdict: "BLOCKED",
    say: "There is no eval set yet.",
    gate_ledger: { G0_EVAL_SET: { status: "FAILED", clause: "eval_size_n >= 50" } },
    fact_origins: { eval_size_n: "ASSERTED" },
  },
  proposal: {
    ok: true,
    approve: "abc123",
    outcome: "PROMPT",
    build: { id: "b1", title: "Try a better prompt", steps: [{ id: "s1", tool: "try_prompt" }] },
  },
  eval: { ok: true, run_id: 4, planned: 10, graded: 10, correct: 7, complete: true, score: 0.7 },
  compare: { ok: true, run_id: 5, against: 4, p_value: 0.5, verdict: "no_evidence", resolved: false },
  prompt: { ok: true, line: { name: "support" }, variant: { version: 2 }, verdict: "different" },
  sweep: { ok: true, ran: true, levers: {}, stamps_nothing: "A sweep stamps nothing.", verdict: "no_evidence" },
  recall: { stampable: true, recall_curve: [{ k: 1, hits: 3, of: 5, recall: 0.6 }], questions_scored: 5 },
  carve: { ok: true, eval_path: "C:/data/eval.jsonl", train_path: "C:/data/train.jsonl", into: "C:/data" },
  synthesis: { ok: true, synthetic_path: "C:/data/synthetic.jsonl", into: "C:/data" },
  "verification-sample": { ok: true, sample_path: "C:/data/sample.csv" },
  verification: { ok: true, dataset: "C:/data/synthetic.jsonl", verification_path: "C:/data/v.json", judged: 10, wrong: 0 },
  sandbox: { ok: true, sandbox: "lora-try", run_dir: "C:/runs/1", exit_code: 0 },
  plan: { ok: true, ticked: "Measure the baseline", open_steps: [], done: 3, of: 4 },
}
