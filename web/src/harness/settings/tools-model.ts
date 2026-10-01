/**
 * The rules behind Settings > Tools, from the outgoing `ToolSettings.tsx`.
 *
 * `GET /api/projects/{id}/settings` answers the cap, the list of packs that
 * are off, and one row per pack with what it costs. `POST` answers the cap and
 * the list but NO rows - so whether a pack is off is read from `packs_off`,
 * never from the row's own `off`, or a switch appears to do nothing after the
 * first save. That bug happened in the outgoing app; this keeps the fix.
 */

export type Project = { id: number; name: string; root_path?: string | null; archived_at?: string | null }

export type PackSetting = { name: string; tools: number; tokens: number; core: boolean; off?: boolean }

export type ProjectSettings = {
  project_id: number | null
  subagents_max: number
  packs_off: string[]
  packs: PackSetting[]
  most_subagents: number
}

/**
 * The project Settings opens on: the default one, which the engine defines as
 * the lowest-id live project (`db.default_project`). The list arrives newest
 * first, so it is the smallest id, not the first row.
 */
export function defaultProject(projects: Project[] | undefined): Project | undefined {
  if (!projects || projects.length === 0) return undefined
  return projects.reduce((lowest, project) => (project.id < lowest.id ? project : lowest))
}

export function isOff(settings: Pick<ProjectSettings, "packs_off">, pack: Pick<PackSetting, "name" | "core">): boolean {
  // The core is on every turn whatever the list says - the engine keeps it on.
  if (pack.core) return false
  return settings.packs_off.includes(pack.name)
}

/** What the packs left on cost every turn: tools offered and tokens spent. */
export function onTheWire(settings: Pick<ProjectSettings, "packs_off" | "packs">): { tools: number; tokens: number } {
  return settings.packs
    .filter((pack) => !isOff(settings, pack))
    .reduce((sum, pack) => ({ tools: sum.tools + pack.tools, tokens: sum.tokens + pack.tokens }), { tools: 0, tokens: 0 })
}

/** The new `packs_off` after flipping one pack. The core never enters the list. */
export function toggledPacks(packsOff: string[], pack: Pick<PackSetting, "name" | "core">, on: boolean): string[] {
  if (pack.core) return packsOff.filter((name) => name !== pack.name)
  const rest = packsOff.filter((name) => name !== pack.name)
  return on ? rest : [...rest, pack.name].sort()
}

/** 0 through the engine's maximum. 0 is "None": delegation off, and the tool says so. */
export function subagentChoices(most: number): { value: number; label: string }[] {
  const top = Math.max(0, Math.floor(most))
  return Array.from({ length: top + 1 }, (_, value) => ({ value, label: value === 0 ? "None" : String(value) }))
}

/**
 * Merge a write's answer into what is on screen. The engine clamps the cap and
 * sorts the list, so its answer - not the optimistic guess - is what stays.
 */
export function merged(was: ProjectSettings, answer: Partial<ProjectSettings>): ProjectSettings {
  return {
    ...was,
    subagents_max: answer.subagents_max ?? was.subagents_max,
    packs_off: answer.packs_off ?? was.packs_off,
    packs: answer.packs ?? was.packs,
    most_subagents: answer.most_subagents ?? was.most_subagents,
  }
}
