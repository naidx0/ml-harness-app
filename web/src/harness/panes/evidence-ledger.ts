/**
 * The five gates, the diagnosis that walked them, and the evidence rows.
 *
 * Ported from the outgoing `frontend/src/data/sample.ts` (FIVE_GATES) and
 * `frontend/src/lib/engine/facts.ts`, trimmed to what the Evidence pane and
 * the Stage's gate map draw. Every type is transcribed from app/diagnosis.py
 * and app/tools/evidence.py; nothing is widened, and a missing field comes
 * back null rather than as a default that reads like data.
 */

/**
 * The five gates, keyed by the engine's own gate ids (`spec.required_gates`
 * in app/diagnosis.py), so the ledger is joined on the engine's identifier
 * and never on position. `name` is the Graphite wording and `asks` is
 * docs/diagnosis_engine.yaml's own `asks:` string, both transcribed.
 *
 * All five render even before anything has been diagnosed: a ledger that
 * shows only the gates that ran cannot be read as a guarantee, and the
 * guarantee is the product.
 */
export const FIVE_GATES = [
  {
    id: "G0_EVAL_SET",
    name: "An eval set exists",
    asks: "Is there a set of examples we can score, so that 'better' is a measurement and not a feeling?",
  },
  {
    id: "G1_BASELINE_MEASURED",
    name: "A baseline has been measured",
    asks: "Do we know what the best thing that already exists scores on that eval set?",
  },
  {
    id: "G2_PROMPT_EXHAUSTED",
    name: "Prompting has been exhausted",
    asks: "Has the no-training version of this approach been pushed as far as it goes?",
  },
  {
    id: "G3_RETRIEVAL_CONSIDERED",
    name: "Retrieval has been considered",
    asks: "Was the missing information brought in from outside the weights, and did that fail?",
  },
  {
    id: "G4_CHEAPER_MODEL_CONSIDERED",
    name: "A cheaper model has been considered",
    asks: "Did we check whether something cheaper that already exists solves this?",
  },
] as const

/** The engine's four origins - app/diagnosis.py ORIGINS. */
export type FactOrigin = "MEASURED" | "STATED" | "ASSERTED" | "DEFAULTED"
const ORIGINS: readonly string[] = ["MEASURED", "STATED", "ASSERTED", "DEFAULTED"]
export const isFactOrigin = (value: unknown): value is FactOrigin =>
  typeof value === "string" && ORIGINS.includes(value)

/** One sentence per origin, quoted from `GET /api/evidence`'s own `origins`. */
export const ORIGIN_MEANS: Record<FactOrigin, string> = {
  MEASURED: "a tool ran on this machine and the engine watched it",
  STATED: "the person whose project this is said so",
  ASSERTED: "a model said so, or nobody said where it came from",
  DEFAULTED: "nobody supplied it, so the engine applied the fact ledger's own default",
}

/** What a gate shows. NOT_CHECKED is not a softer NOT_MET: it was never asked. */
export type GateStatus = "PASSED" | "NOT_MET" | "NOT_CHECKED"

export type GateLedgerEntry = { status: "PASSED" | "FAILED" | "NOT_REACHED"; clause: string | null }

export type Diagnosis = {
  outcome: string
  say: string | null
  gateLedger: Record<string, GateLedgerEntry>
  factOrigins: Record<string, string>
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function stringMap(value: unknown): Record<string, string> {
  const out: Record<string, string> = {}
  if (!isRecord(value)) return out
  for (const [key, entry] of Object.entries(value)) if (typeof entry === "string") out[key] = entry
  return out
}

/**
 * A `run_diagnosis` result, or null. Strict about the two fields a ledger
 * cannot be honest without - `outcome` and `gate_ledger` - so a payload
 * missing either is not drawn as a diagnosis with a hole in it.
 */
export function readDiagnosis(value: unknown): Diagnosis | null {
  if (!isRecord(value) || value.ok !== true) return null
  if (typeof value.outcome !== "string" || typeof value.verdict !== "string") return null
  if (!isRecord(value.gate_ledger)) return null
  const gateLedger: Record<string, GateLedgerEntry> = {}
  for (const [id, entry] of Object.entries(value.gate_ledger)) {
    if (!isRecord(entry)) return null
    const status = entry.status
    if (status !== "PASSED" && status !== "FAILED" && status !== "NOT_REACHED") return null
    gateLedger[id] = { status, clause: typeof entry.clause === "string" ? entry.clause : null }
  }
  return {
    outcome: value.outcome,
    say: typeof value.say === "string" && value.say.trim() ? value.say : null,
    gateLedger,
    factOrigins: stringMap(value.fact_origins),
  }
}

/** A ledger entry's status as the ledger draws it. */
export function gateStatus(raw: string | undefined): GateStatus {
  if (raw === "PASSED") return "PASSED"
  if (raw === "FAILED" || raw === "NOT_MET") return "NOT_MET"
  return "NOT_CHECKED"
}

/**
 * Each of the five gates with its status, and how many passed. The counter
 * is "n of 5" and never a percentage: three of five gates is not 60% of a
 * guarantee. A gate id the engine sends that is not one of the five is not
 * counted - it would be a sixth row this list has no name for.
 */
export function gateLedger(ledger: Record<string, { status?: string } | undefined> | null | undefined) {
  const gates = FIVE_GATES.map((gate) => ({ ...gate, status: gateStatus(ledger?.[gate.id]?.status) }))
  return { gates, passed: gates.filter((gate) => gate.status === "PASSED").length, of: FIVE_GATES.length }
}

/**
 * Which declared facts a gate's clause names: the identifiers in the clause
 * the wire carries, intersected with the fact origins the wire also carries.
 * It can err only towards naming one fact too many (a bare enum member in a
 * set literal), never one too few.
 */
export function factsInClause(clause: string | null, declared: Record<string, string>): string[] {
  if (!clause) return []
  const found = new Set<string>()
  for (const match of clause.matchAll(/[A-Za-z_][A-Za-z0-9_]*/g)) if (match[0] in declared) found.add(match[0])
  return [...found].sort()
}

/**
 * How a gate was satisfied, as one word: the weakest origin among the facts
 * its clause names, because a gate is only as substantiated as its worst
 * input. DEFAULTED is skipped rather than counted as the floor - an untouched
 * default is not something anybody told the harness.
 */
export function weakestOrigin(facts: string[], origins: Record<string, string>): FactOrigin | null {
  const rank: Record<FactOrigin, number> = { MEASURED: 3, STATED: 2, ASSERTED: 1, DEFAULTED: 0 }
  let worst: FactOrigin | null = null
  for (const name of facts) {
    const origin = origins[name]
    if (!isFactOrigin(origin) || origin === "DEFAULTED") continue
    if (worst === null || rank[origin] < rank[worst]) worst = origin
  }
  return worst
}

/** One row of `GET /api/evidence` - app/tools/evidence.py `ledger_view`. */
export type EvidenceRow = {
  id: number
  fact: string
  value: unknown
  origin: string
  actor: string
  tool: string | null
  how: string
  createdAt: string
}

export type EvidenceLedger = { rows: EvidenceRow[]; quarantined: number; unscoped: number }

export function readEvidence(value: unknown): EvidenceLedger {
  if (!isRecord(value)) return { rows: [], quarantined: 0, unscoped: 0 }
  const rows: EvidenceRow[] = []
  for (const entry of Array.isArray(value.rows) ? value.rows : []) {
    if (!isRecord(entry) || typeof entry.fact !== "string") continue
    rows.push({
      id: typeof entry.id === "number" ? entry.id : 0,
      fact: entry.fact,
      value: entry.value,
      origin: typeof entry.origin === "string" ? entry.origin : "ASSERTED",
      actor: typeof entry.actor === "string" ? entry.actor : "",
      tool: typeof entry.tool === "string" ? entry.tool : null,
      how: typeof entry.how === "string" ? entry.how : "",
      createdAt: typeof entry.created_at === "string" ? entry.created_at : "",
    })
  }
  return {
    rows,
    quarantined: Array.isArray(value.quarantined) ? value.quarantined.length : 0,
    unscoped: Array.isArray(value.unscoped) ? value.unscoped.length : 0,
  }
}

/** Who this was, in words; null for an actor never heard of, shown raw. */
export function actorName(actor: string | null | undefined): string | null {
  if (actor === "user") return "you"
  if (actor === "model") return "the model"
  if (actor === "harness") return "the harness"
  return null
}

/** A ledger value, printed as the engine stored it. */
export function showValue(value: unknown): string {
  if (value === null || value === undefined) return "—"
  if (typeof value === "boolean") return value ? "true" : "false"
  if (typeof value === "number") return value.toLocaleString()
  if (typeof value === "string") return value.length > 40 ? `${value.slice(0, 39)}…` : value
  return JSON.stringify(value)
}
