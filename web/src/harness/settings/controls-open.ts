import { useSettingsSurface, type SettingsRootTab } from "@/settings/surface"
import { focusTool } from "../panes/controls-focus"

/**
 * Controls lives in Settings > Harness > Controls, not in the side panel: it
 * is every tool run by hand, a place a person goes to on purpose rather than
 * a readout that follows the chat.
 *
 * The value of the settings tab the page is on (settings/slots.tsx).
 */
export const CONTROLS_SETTINGS_TAB = "harness:controls"

/**
 * Open Controls on one tool: the focus request first (controls-focus.ts - the
 * page opens that tool's pack and row when it next reads its tools), then
 * their settings route, whose source route is this chat, so a run there is
 * still filed under this conversation.
 *
 * Undefined where there is no settings surface to open - a pop-out window has
 * no router around it - so a caller shows no button rather than a dead one.
 */
export function useOpenToolControls(): ((tool: string) => void) | undefined {
  let surface: ReturnType<typeof useSettingsSurface>
  try {
    surface = useSettingsSurface()
  } catch {
    return undefined
  }
  return (tool: string) => {
    focusTool(tool)
    // Their tab check accepts the harness: prefix (patch P9).
    surface.open(CONTROLS_SETTINGS_TAB as SettingsRootTab)
  }
}
