import { Show } from "solid-js"
import { Icon } from "@opencode/ui/icon"
import { useSettingsSurface } from "@/settings/surface"

/**
 * Settings at the top left, under Home and New chat (Jaden, 2026-10-03: "a
 * settings bar top left not on home"). Mounted in their sidebar by patch P44
 * (scripts/vendor_opencode.py), in the same row style as their New chat.
 */
export function HarnessSidebarSettings() {
  let surface: ReturnType<typeof useSettingsSurface> | undefined
  try {
    surface = useSettingsSurface()
  } catch {
    // A pop-out window has no router around it: no button rather than a dead one.
  }
  return (
    <Show when={surface}>
      {(open) => (
        <button
          type="button"
          data-action="harness-sidebar-settings"
          data-active={open().active() ? "" : undefined}
          class="group flex h-7 w-full shrink-0 items-center gap-1.5 rounded-[6px] ps-1.5 pe-2 text-[13px] leading-4 text-v2-text-text-faint hover:text-v2-text-text-base data-[active]:bg-v2-background-bg-layer-02 data-[active]:text-v2-text-text-base"
          onClick={() => open().open()}
        >
          <Icon name="settings-gear" class="shrink-0" />
          <span class="min-w-0 truncate">Settings</span>
        </button>
      )}
    </Show>
  )
}
