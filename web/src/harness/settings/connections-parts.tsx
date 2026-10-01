import { Show, type JSX } from "solid-js"

/**
 * Small pieces the four harness settings pages share, drawn in their settings
 * markup (settings-tab-header, settings-section) so a harness page reads as
 * one of theirs. Only classes their own settings pages use appear here.
 */

export function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

/** Their page header: a title and a muted line under it. */
export function PageHeader(props: { title: string; description: string }) {
  return (
    <div class="settings-tab-header">
      <div class="settings-tab-header-row">
        <div class="flex flex-col gap-1">
          <h2 class="settings-tab-title">{props.title}</h2>
          <span class="text-[11px] text-v2-text-text-muted">{props.description}</span>
        </div>
      </div>
    </div>
  )
}

/** Their section, with an optional control beside the title (a rescan, a refresh). */
export function SettingsSection(props: { title: string; action?: JSX.Element; note?: JSX.Element; children: JSX.Element }) {
  return (
    <section class="settings-section" aria-label={props.title}>
      <div class="flex min-h-7 items-center justify-between gap-3">
        <h3 class="settings-section-title">{props.title}</h3>
        {props.action}
      </div>
      <Show when={props.note}>
        <p class="-mt-2 text-[13px] text-v2-text-text-muted">{props.note}</p>
      </Show>
      {props.children}
    </section>
  )
}

/** An engine error, in the engine's own words, in their danger colour. */
export function ErrorText(props: { error: unknown }) {
  return (
    <Show when={props.error}>
      <p role="alert" class="text-[13px] text-v2-state-fg-danger">
        {message(props.error)}
      </p>
    </Show>
  )
}

/** What is happening right now, while a request is out. */
export function BusyText(props: { text: string | undefined }) {
  return (
    <Show when={props.text}>
      <p role="status" class="text-[13px] text-v2-text-text-muted">
        {props.text}
      </p>
    </Show>
  )
}

/** A labelled field for forms that sit inside a list row. */
export function Field(props: { label: string; hint?: JSX.Element; children: JSX.Element }) {
  return (
    <label class="flex min-w-0 flex-col gap-1.5">
      <span class="text-12-medium text-v2-text-text-muted">{props.label}</span>
      {props.children}
      <Show when={props.hint}>
        <span class="text-12-regular text-v2-text-text-faint">{props.hint}</span>
      </Show>
    </label>
  )
}

/** The empty line of a list, in their provider-list style. */
export function EmptyLine(props: { children: JSX.Element }) {
  return <div class="settings-provider-empty">{props.children}</div>
}
