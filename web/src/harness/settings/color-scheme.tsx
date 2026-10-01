import type { Component } from "solid-js"
import { Select } from "@opencode/ui/select"
import { useTheme, type ColorScheme } from "@opencode/ui/theme/context"
import { useLanguage } from "@/runtime/i18n/language"
import { SettingsRow } from "@/settings/row"

/**
 * Light or dark, the one appearance choice with a real effect here (the
 * owner, 2026-09-23: "Appearance: we only have one appearance").
 *
 * Their Appearance page is hidden (unbacked.ts): its theme picker, UI font
 * and terminal font have nothing to change in this product. Colour scheme is
 * different - brand/theme.json carries a light and a dark palette, and
 * brand/identity.css pins both the charcoal surfaces and the cream ones the
 * owner chose on 2026-09-03 - so switching it re-skins every token. Checked
 * by switching it in a running window, not assumed.
 *
 * Their own row, their words and their control, drawn on General by the
 * pending patch in PENDING-PATCHES.md.
 */
const SCHEMES: ColorScheme[] = ["system", "light", "dark"]

export const HarnessColorSchemeSetting: Component = () => {
  const language = useLanguage()
  const theme = useTheme()
  return (
    <SettingsRow
      title={language.t("settings.general.row.colorScheme.title")}
      description={language.t("settings.general.row.colorScheme.description")}
    >
      <Select
        data-action="settings-color-scheme"
        options={SCHEMES}
        current={SCHEMES.find((option) => option === theme.colorScheme())}
        placement="bottom-end"
        gutter={6}
        label={(option) => {
          if (option === "system") return language.t("theme.scheme.system")
          if (option === "light") return language.t("theme.scheme.light")
          return language.t("theme.scheme.dark")
        }}
        onSelect={(option) => option && theme.setColorScheme(option)}
      />
    </SettingsRow>
  )
}
