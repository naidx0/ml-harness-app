import { describe, expect, it } from "vitest"
import { defaultProject, isOff, merged, onTheWire, subagentChoices, toggledPacks, type ProjectSettings } from "./tools-model"
import { formatReading, machineRows, provenanceOf } from "./machine-fields"
import {
  buildLine,
  checkoutVerdict,
  formatUptime,
  healthFailure,
  portfileVerdict,
  restartOutcome,
  runsLine,
  schemaLine,
  shortHex,
  versionLine,
} from "./engine-identity"

describe("tools: which project", () => {
  it("opens on the engine's default project - the lowest id, not the first row", () => {
    // /api/projects answers newest first.
    expect(defaultProject([{ id: 9, name: "new" }, { id: 4, name: "old" }, { id: 6, name: "mid" }])?.id).toBe(4)
    expect(defaultProject([])).toBeUndefined()
    expect(defaultProject(undefined)).toBeUndefined()
  })
})

describe("tools: packs", () => {
  const state: ProjectSettings = {
    project_id: 1,
    subagents_max: 2,
    packs_off: ["eval"],
    most_subagents: 4,
    packs: [
      { name: "ledger", tools: 9, tokens: 3000, core: true, off: false },
      { name: "eval", tools: 5, tokens: 1500, core: false, off: false },
      { name: "train", tools: 4, tokens: 1000, core: false, off: true },
    ],
  }

  it("reads off-ness from packs_off, never from the row's stale flag", () => {
    expect(isOff(state, state.packs[1]!)).toBe(true)
    expect(isOff(state, state.packs[2]!)).toBe(false)
  })

  it("the core is on whatever the list says", () => {
    expect(isOff({ packs_off: ["ledger"] }, state.packs[0]!)).toBe(false)
    expect(toggledPacks(["ledger"], state.packs[0]!, false)).toEqual([])
  })

  it("counts only what is left on", () => {
    expect(onTheWire(state)).toEqual({ tools: 13, tokens: 4000 })
  })

  it("flips one pack without duplicating or losing others", () => {
    expect(toggledPacks(["eval"], state.packs[2]!, false)).toEqual(["eval", "train"])
    expect(toggledPacks(["eval", "train"], state.packs[1]!, true)).toEqual(["train"])
    expect(toggledPacks(["eval"], state.packs[1]!, false)).toEqual(["eval"])
  })

  it("keeps the engine's answer, and the rows the write did not send", () => {
    const next = merged(state, { subagents_max: 0, packs_off: [] })
    expect(next.subagents_max).toBe(0)
    expect(next.packs_off).toEqual([])
    expect(next.packs).toBe(state.packs)
  })

  it("offers None through the engine's maximum", () => {
    expect(subagentChoices(4).map((c) => c.label)).toEqual(["None", "1", "2", "3", "4"])
    expect(subagentChoices(0)).toEqual([{ value: 0, label: "None" }])
  })
})

describe("machine: every field", () => {
  const specs = {
    gpu_name: "RTX 2060 SUPER",
    vram_gb: 8,
    ram_gb: 31.9,
    disk_free_gb: null,
    os: "Windows",
    driver_version: "560.1",
    compute_capability: "7.5",
    npu_tops: 40,
    provenance: { gpu_name: "measured", disk_free_gb: "defaulted", ram_gb: "MEASURED" },
    sources: { gpu_name: "nvidia-smi --query-gpu=name" },
    warnings: ["x"],
  }

  it("never renders a failed detection as a value", () => {
    const rows = machineRows(specs)
    expect(rows.find((r) => r.field === "disk_free_gb")?.value).toBeUndefined()
    expect(rows.find((r) => r.field === "vram_gb")?.value).toBe("8 GB")
    expect(rows.find((r) => r.field === "ram_gb")?.value).toBe("31.9 GB")
  })

  it("carries provenance and source per field", () => {
    const gpu = machineRows(specs).find((r) => r.field === "gpu_name")
    expect(gpu?.provenance).toBe("measured")
    expect(gpu?.source).toBe("nvidia-smi --query-gpu=name")
    expect(machineRows(specs).find((r) => r.field === "ram_gb")?.provenance).toBe("measured")
  })

  it("shows a field this page has no label for, and not the metadata", () => {
    const fields = machineRows(specs).map((r) => r.field)
    expect(fields).toContain("npu_tops")
    expect(fields).not.toContain("provenance")
    expect(fields).not.toContain("warnings")
  })

  it("formats readings and rejects unknown provenance words", () => {
    expect(formatReading(undefined)).toBeUndefined()
    expect(formatReading("")).toBeUndefined()
    expect(formatReading(Number.NaN)).toBeUndefined()
    expect(formatReading(true)).toBe("yes")
    expect(provenanceOf("guessed")).toBeUndefined()
    expect(machineRows(undefined)).toEqual([])
  })
})

describe("engine: identity", () => {
  it("matches a checkout by prefix either way, and never claims a match it did not check", () => {
    expect(checkoutVerdict("3966702f4c1a", { revision: "3966702" }).kind).toBe("matches")
    expect(checkoutVerdict("3966702", { revision: "3966702f4c1a" }).kind).toBe("matches")
    expect(checkoutVerdict("aaaaaaa", { revision: "bbbbbbb" }).kind).toBe("differs")
    expect(checkoutVerdict("aaaaaaa", null).kind).toBe("unknown")
    expect(checkoutVerdict(null, { revision: "bbbbbbb" }).kind).toBe("unknown")
    expect(checkoutVerdict("aaaaaaa", { revision: 12 }).kind).toBe("unknown")
  })

  it("compares the portfile's engine id with the one answering", () => {
    const health = { engine: { engine_id: "abc" } }
    expect(portfileVerdict({ engine: { engine: { engine_id: "abc" } } }, health)?.kind).toBe("matches")
    expect(portfileVerdict({ engine: { engine: { engine_id: "def" } } }, health)?.kind).toBe("differs")
    expect(portfileVerdict(undefined, health)).toBeUndefined()
    expect(portfileVerdict({ engine: { engine: { engine_id: "abc" } } }, undefined)).toBeUndefined()
  })

  it("reads build, schema and uptime as sentences", () => {
    expect(buildLine({ sha: "0123456789abcdef", dirty: true })).toBe("0123456789ab (uncommitted changes)")
    expect(buildLine({ sha: null })).toBeUndefined()
    expect(schemaLine({ build_knows: 12, database_at: 12, agrees: true })).toBe("version 12")
    expect(schemaLine({ build_knows: 12, database_at: 11, agrees: false })).toBe("code knows 12, database is at 11")
    expect(schemaLine(undefined)).toBeUndefined()
    expect(formatUptime(42)).toBe("42s")
    expect(formatUptime(3 * 3600 + 5 * 60)).toBe("3h 5m")
    expect(formatUptime(-1)).toBeUndefined()
    expect(shortHex("abcdef", 4)).toBe("abcd")
  })

  it("names a 503 from /health instead of printing the status code", () => {
    expect(healthFailure(503, "503 from /health")).toContain("not ready")
    expect(healthFailure(undefined, "network down")).toBe("network down")
  })

  it("treats either flag from restart_engine as success, as the outgoing app learned", () => {
    expect(restartOutcome({ started: true })).toEqual({ ok: true })
    expect(restartOutcome({ already_running: true })).toEqual({ ok: true })
    expect(restartOutcome({ started: false, already_running: false, detail: "port busy" })).toEqual({ ok: false, why: "port busy" })
    expect(restartOutcome(null).ok).toBe(false)
  })
})

describe("about: what is running", () => {
  it("one version when window and engine agree, both when they do not, none invented", () => {
    expect(versionLine("0.1.0", "0.1.0")).toBe("0.1.0")
    expect(versionLine("0.1.0", "0.2.0")).toBe("0.1.0 (engine 0.2.0)")
    expect(versionLine(undefined, "0.2.0")).toBe("0.2.0")
    expect(versionLine("0.1.0", undefined)).toBe("0.1.0")
    expect(versionLine(undefined, undefined)).toBeUndefined()
    expect(versionLine("", "")).toBeUndefined()
  })

  it("counts runs, and says nothing for a count it was not given", () => {
    expect(runsLine(0)).toBe("0 runs")
    expect(runsLine(1)).toBe("1 run")
    expect(runsLine(42)).toBe("42 runs")
    expect(runsLine(undefined)).toBeUndefined()
    expect(runsLine(-1)).toBeUndefined()
    expect(runsLine(Number.NaN)).toBeUndefined()
  })
})
