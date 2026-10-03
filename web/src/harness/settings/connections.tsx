import { createSignal, For, onCleanup, onMount, Show } from "solid-js"
import { Badge } from "@opencode/ui/badge"
import { Button } from "@opencode/ui/button"
import { TextInput } from "@opencode/ui/text-input"
import { SettingsList } from "@/settings/list"
import "@/settings/settings.css"
import { harness } from "../engine"
import { listPhase, useHarnessRead } from "../ui"
import { connectionLabel, type Preset } from "../providers/local"
import {
  activeLabel,
  connectionSummary,
  contextTitle,
  draftFrom,
  dropsProbe,
  editPatch,
  isEmptyPatch,
  type ConnectionRow,
  type EditDraft,
  type Keychain,
} from "./connections-model"
import { BusyText, EmptyLine, ErrorText, Field, PageHeader, SettingsSection } from "./connections-parts"
import { LocalModels } from "./connections-local"
import { AddByHand } from "./connections-add"
import { Keys } from "./connections-keys"
import { takeModelsSection } from "./models-open"

/**
 * Settings > Models: every model connection the harness can think with.
 *
 * Laid out like the outgoing app's "Connect a model" (Jaden, 2026-10-03: "look
 * at the old format onboarding and implement it into this new kind of UI"):
 * the models you already have, then the two roads in - one on this computer,
 * or one with an API key - then where keys are kept. Their own Providers and
 * Models pages are hidden (unbacked.ts), so this is the one place for the job.
 *
 * Carried over from the outgoing Settings (Models, Keys) and the connect
 * dialog (PARITY 4.2-4.7, 8.1, 8.3). The harness ships no AI; the person lends
 * it one. Exactly one connection is active, and every turn goes through it.
 *
 * One `run` for every action, so there is one busy line and one error line and
 * the list is re-read after every change - succeeded or not, because a create
 * that saved the row and refused the key (a 503) still left a row behind.
 */

export type Run = (label: string, work: () => Promise<unknown>) => Promise<boolean>

export default function Section() {
  const connections = useHarnessRead<ConnectionRow[]>(() => "/api/providers")
  const presets = useHarnessRead<Preset[]>(() => "/api/provider_presets")
  const keychain = useHarnessRead<Keychain>(() => "/api/keychain")
  const [busy, setBusy] = createSignal<string>()
  const [error, setError] = createSignal<unknown>()

  const rows = () => (connections.data.error ? undefined : connections.data.latest)
  const keys = () => (keychain.data.error ? undefined : keychain.data.latest)
  const presetList = () => (presets.data.error ? [] : (presets.data.latest ?? []))

  const run: Run = async (label, work) => {
    setBusy(label)
    setError(undefined)
    try {
      await work()
      return true
    } catch (failure) {
      setError(failure)
      return false
    } finally {
      await connections.refetch()
      setBusy(undefined)
    }
  }

  // A button elsewhere (the new-chat card) asked for one road: bring it into view.
  let page: HTMLDivElement | undefined
  onMount(() => {
    const section = takeModelsSection()
    if (!section) return
    // Twice: once now, and once after the local list has answered and pushed
    // the sections below it down.
    const reveal = () => page?.querySelector(`[data-models-section="${section}"]`)?.scrollIntoView({ block: "start" })
    const timers = [setTimeout(reveal, 0), setTimeout(reveal, 600)]
    onCleanup(() => timers.forEach(clearTimeout))
  })

  return (
    <>
      <PageHeader
        title="Models"
        description="ML Harness ships no AI. It thinks with a model you lend it: one on this computer, or one you reach with an API key. One is in use at a time."
      />
      <div ref={page} class="settings-tab-body settings-tab-body--sectioned settings-providers">
        <SettingsSection
          title="Your models"
          action={
            <Button
              size="small"
              variant="ghost"
              icon="refresh"
              disabled={connections.data.loading}
              onClick={() => void connections.refetch()}
            >
              Refresh
            </Button>
          }
        >
          <BusyText text={busy()} />
          <ErrorText error={error()} />
          <SettingsList variant="catalog">
            <Show
              when={(rows() ?? []).length > 0}
              // A failed read is not an empty list: "Nothing is connected yet"
              // under a read that never answered told a person to set up again.
              fallback={
                <EmptyLine>
                  {(() => {
                    const phase = listPhase(connections.data)
                    if (phase === "failed")
                      return (
                        <span class="flex flex-col gap-1">
                          <span>Could not read your connections.</span>
                          <ErrorText error={connections.data.error} />
                        </span>
                      )
                    if (phase === "reading" || connections.data.loading) return "Reading your connections…"
                    return "Nothing is connected yet. Pick a model on this computer, or add one with an API key, below."
                  })()}
                </EmptyLine>
              }
            >
              <For each={rows()}>
                {(row) => <ConnectionItem row={row} keychain={keys()} busy={busy() !== undefined} run={run} />}
              </For>
            </Show>
          </SettingsList>
        </SettingsSection>

        <div data-models-section="local" class="scroll-mt-24">
          <LocalModels connections={rows()} busy={busy() !== undefined} run={run} />
        </div>

        <div data-models-section="api" class="scroll-mt-24">
          <AddByHand presets={presetList()} keychain={keys()} busy={busy() !== undefined} run={run} />
        </div>

        <Keys
          keychain={keys()}
          keychainError={keychain.data.error}
          connections={rows()}
          busy={busy() !== undefined}
          run={run}
        />
      </div>
    </>
  )
}

function ConnectionItem(props: { row: ConnectionRow; keychain: Keychain | undefined; busy: boolean; run: Run }) {
  const [renaming, setRenaming] = createSignal(false)
  const [newName, setNewName] = createSignal("")
  const [editing, setEditing] = createSignal(false)
  const [draft, setDraft] = createSignal<EditDraft>(draftFrom(props.row))
  const [confirming, setConfirming] = createSignal(false)

  const noKeychain = () => props.keychain?.available === false
  const patch = () => editPatch(props.row, draft())
  const set = (field: keyof EditDraft, value: string) => setDraft((was) => ({ ...was, [field]: value }))

  const startRename = () => {
    setNewName(props.row.name)
    setRenaming(true)
  }
  const commitRename = () => {
    if (!renaming()) return
    setRenaming(false)
    const name = newName().trim()
    if (!name || name === props.row.name) return
    void props.run("Renaming…", () =>
      harness(`/api/providers/${props.row.id}`, { method: "PATCH", body: { name } }),
    )
  }

  /* The fields are re-seeded from the row every time the editor opens, not
     once at mount: a re-check or another window may have changed the row, and
     an editor holding the old values would write them back. */
  const toggleEdit = () => {
    if (!editing()) setDraft(draftFrom(props.row))
    setEditing(!editing())
  }

  const save = async () => {
    const body = patch()
    // The key leaves this component's state the moment it is sent.
    set("api_key", "")
    if (isEmptyPatch(body)) {
      setEditing(false)
      return
    }
    const ok = await props.run("Saving…", () =>
      harness(`/api/providers/${props.row.id}`, { method: "PATCH", body }),
    )
    if (ok) setEditing(false)
  }

  return (
    <div class="settings-provider-row !flex-col !items-stretch !gap-4" data-active={props.row.is_active === 1}>
      <div class="flex flex-wrap items-center justify-between gap-4 sm:flex-nowrap">
        <div class="settings-provider-lead">
          <div class="settings-provider-copy">
            <div class="settings-provider-main">
              <Show
                when={renaming()}
                fallback={
                  <button
                    type="button"
                    class="settings-provider-name truncate text-left"
                    title={`${props.row.model} - rename this connection`}
                    onClick={startRename}
                  >
                    {connectionLabel(props.row)}
                  </button>
                }
              >
                <div class="w-full sm:w-[220px]">
                  <TextInput
                    type="text"
                    appearance="base"
                    aria-label="New name for this connection"
                    value={newName()}
                    spellcheck={false}
                    autocomplete="off"
                    ref={(element: HTMLInputElement) => setTimeout(() => element.focus?.(), 0)}
                    onInput={(event) => setNewName(event.currentTarget.value)}
                    onBlur={commitRename}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") commitRename()
                      if (event.key === "Escape") setRenaming(false)
                    }}
                  />
                </div>
              </Show>
              <Show when={activeLabel(props.row)}>
                {(label) => (
                  <Badge
                    variant="accent"
                    title={
                      props.row.tool_calling === "unknown"
                        ? "In use, and not yet checked - the first turn will tell"
                        : "In use, and it answered its check"
                    }
                  >
                    {label()}
                  </Badge>
                )}
              </Show>
              <Badge>{props.row.kind === "local" ? "Local" : "Remote"}</Badge>
            </div>
            <p
              class="settings-provider-description break-all"
              title={`${props.row.model} · ${contextTitle(props.row.ctx_len_provenance)}`}
            >
              {connectionSummary(props.row)}
            </p>
            <Show when={props.row.capability_detail}>
              {(detail) => <p class="text-12-regular text-v2-text-text-faint">{detail()}</p>}
            </Show>
          </div>
        </div>

        <div class="flex shrink-0 flex-wrap items-center gap-1">
          <Show when={props.row.is_active !== 1}>
            <Button
              size="small"
              variant="neutral"
              disabled={props.busy}
              onClick={() =>
                void props.run("Switching…", () =>
                  harness(`/api/providers/${props.row.id}/activate`, { method: "POST" }),
                )
              }
            >
              Use this one
            </Button>
          </Show>
          <Button
            size="small"
            variant="ghost"
            icon="refresh"
            disabled={props.busy}
            title="Ask the model again what it can do"
            onClick={() =>
              void props.run(`Asking ${connectionLabel(props.row)} what it can do…`, () =>
                harness(`/api/providers/${props.row.id}/probe`, { method: "POST" }),
              )
            }
          >
            Re-check
          </Button>
          <Button size="small" variant="ghost" icon="edit" onClick={toggleEdit}>
            {editing() ? "Close" : "Edit"}
          </Button>
          <Button size="small" variant="ghost" icon="trash" disabled={props.busy} onClick={() => setConfirming(true)}>
            Forget
          </Button>
        </div>
      </div>

      <Show when={editing()}>
        <div class="flex flex-col gap-3">
          <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="What to call it">
              <TextInput
                type="text"
                value={draft().name}
                spellcheck={false}
                autocomplete="off"
                onInput={(event) => set("name", event.currentTarget.value)}
              />
            </Field>
            <Field label="Model">
              <TextInput
                type="text"
                class="font-mono"
                value={draft().model}
                spellcheck={false}
                autocomplete="off"
                onInput={(event) => set("model", event.currentTarget.value)}
              />
            </Field>
            <Field label="Endpoint">
              <TextInput
                type="text"
                class="font-mono"
                value={draft().base_url}
                spellcheck={false}
                autocomplete="off"
                onInput={(event) => set("base_url", event.currentTarget.value)}
              />
            </Field>
            <Field
              label="Replace the API key"
              hint={
                noKeychain()
                  ? props.keychain?.detail
                  : props.row.has_key
                    ? "A key is stored. Leave this empty to keep it - the engine never gives a key back, so empty means unchanged, not delete."
                    : "No key is stored. Leave it empty for a server that does not want one."
              }
            >
              <TextInput
                type="password"
                class="font-mono"
                value={draft().api_key}
                autocomplete="off"
                disabled={noKeychain()}
                placeholder={noKeychain() ? "No keychain on this computer" : ""}
                onInput={(event) => set("api_key", event.currentTarget.value)}
              />
            </Field>
          </div>

          <Show when={dropsProbe(props.row, draft())}>
            <p class="text-[13px] text-v2-state-fg-warning">
              Saving this drops what the last check measured - whether it can call tools, and its context length.
              Those were measured on {props.row.model} at {props.row.base_url} and say nothing about a different one.
              Re-check afterwards to measure them again.
            </p>
          </Show>

          <div class="flex items-center gap-2">
            <Button size="small" variant="submit" disabled={props.busy} onClick={() => void save()}>
              Save
            </Button>
            <Button size="small" variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </div>
        </div>
      </Show>

      <Show when={confirming()}>
        <div class="flex flex-wrap items-center gap-3">
          <p class="min-w-0 flex-1 text-[13px] text-v2-text-text-base">
            Forget {connectionLabel(props.row)}?The connection goes, and{" "}
            {props.row.has_key ? "its key is removed from this computer's keychain with it" : "there is no key to remove"}.
            Nothing else is deleted.
          </p>
          <Button
            size="small"
            variant="danger"
            icon="trash"
            disabled={props.busy}
            onClick={() =>
              void props.run("Forgetting the connection…", () =>
                harness(`/api/providers/${props.row.id}`, { method: "DELETE" }),
              )
            }
          >
            Forget it
          </Button>
          <Button size="small" variant="ghost" onClick={() => setConfirming(false)}>
            Keep it
          </Button>
        </div>
      </Show>
    </div>
  )
}
