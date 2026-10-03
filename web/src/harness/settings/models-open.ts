import { createSignal } from "solid-js"
import { useSettingsSurface, type SettingsRootTab } from "@/settings/surface"

/**
 * Settings > Models: the one page for every model connection. The tab value
 * keeps its old name, so links and tests that open it still do.
 */
export const MODELS_SETTINGS_TAB = "harness:connections"

/** Which part of the Models page a button was for: a model on this computer, or one with an API key. */
export type ModelsSection = "local" | "api"

const [wanted, setWanted] = createSignal<ModelsSection>()

/** The section the next Models page should bring into view, taken once. */
export function takeModelsSection(): ModelsSection | undefined {
  const section = wanted()
  setWanted(undefined)
  return section
}

/**
 * Open Settings > Models, at one of its sections. Undefined where there is no
 * settings surface to open (a pop-out window has no router around it), so a
 * caller shows no button rather than a dead one.
 */
export function useOpenModels(): ((section?: ModelsSection) => void) | undefined {
  let surface: ReturnType<typeof useSettingsSurface>
  try {
    surface = useSettingsSurface()
  } catch {
    return undefined
  }
  return (section?: ModelsSection) => {
    setWanted(section)
    // Their tab check accepts the harness: prefix (patch P9).
    surface.open(MODELS_SETTINGS_TAB as SettingsRootTab)
  }
}
