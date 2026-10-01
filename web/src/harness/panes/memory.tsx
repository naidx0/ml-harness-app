import { createEffect, createMemo, createSignal, For, on, Show } from "solid-js"
import { Button } from "@opencode/ui/button"
import { Icon } from "@opencode/ui/icon"
import { Textarea } from "@opencode/ui/textarea"
import { harness } from "../engine"
import { ErrorLine, Section, useHarnessRead } from "../ui"
import type { PaneProps } from "../panel/panes"
import {
  DEFAULT_LIMITS,
  EMPTY,
  TARGETS,
  TITLE,
  memoryUse,
  type MemoryBlock,
  type MemoryRead,
  type MemorySaved,
  type MemoryTarget,
} from "./memory-text"

/**
 * Memory, editable. Two texts: what this project already knows, and who the
 * person is - the two stores Hermes keeps as MEMORY.md and USER.md, here as
 * rows the model writes through `remember` and the person edits here.
 *
 * This product's rule is that anything the model holds about the person is
 * something the person can read and change, so both blocks are here in the
 * form the model sees them: one entry per line, separated by `§` - Hermes'
 * own delimiter, kept so an export reads the same.
 *
 * Save refuses the whole text if any entry carries a number with no origin
 * word, or the text is over its limit, and says which - the engine's rule
 * (`app/memory.py::set_text`), not this pane's - and the edit stays in the
 * box either way. The count beside each box is the engine's count, not the
 * box's length (see memory-text.ts).
 *
 * The project comes from the open thread (`GET /api/threads/{id}` carries
 * its `project_id`). With no thread open there is no project, so its block
 * is read-only and says why, while "About you" - which belongs to no
 * project - stays editable.
 */

type ThreadRow = { thread: { id: number; project_id: number | null } }

export default function MemoryPane(props: PaneProps) {
  const thread = useHarnessRead<ThreadRow>(() =>
    props.threadId === undefined ? undefined : `/api/threads/${props.threadId}`,
  )

  // null: no project to speak of. undefined: still finding out, so nothing
  // is read yet - reading the user block alone and then both would draw the
  // pane twice with a project block that flickers from empty to full.
  const projectId = createMemo<number | null | undefined>(() => {
    if (props.threadId === undefined || thread.data.error) return null
    const value = thread.data.latest
    if (value?.thread.id !== props.threadId) return undefined
    return value.thread.project_id ?? null
  })

  // Re-read every so often so a `remember` the model made in the chat
  // appears without reopening the pane. A person's unsaved text is a draft
  // held apart from what was read, so a re-read never overwrites it.
  const memory = useHarnessRead<MemoryRead>(
    () => {
      const id = projectId()
      if (id === undefined) return undefined
      return id === null ? "/api/memory" : `/api/memory?project_id=${id}`
    },
    { poll: 15000 },
  )
  // LOADED means a read of THIS path answered with a value. Save is a
  // whole-text PUT, so a box a person could type into before the stored text
  // arrived - or while it still showed another project's text, or after the
  // read failed - would save their few words over everything stored.
  const loaded = () => memory.data.answered && !memory.data.error
  const read = () => (loaded() ? memory.data.latest : undefined)

  const [drafts, setDrafts] = createSignal<Partial<Record<MemoryTarget, string>>>({})
  // A draft of one project's memory is not a draft of another's - but a
  // thread switch passes through "still finding out" (undefined) on the way
  // to the next project, and a switch between two threads of the SAME
  // project threw the draft away on that blip. So the draft follows the last
  // project actually known, and only a different one drops it.
  const knownProject = createMemo<number | null | undefined>((was) => {
    const id = projectId()
    return id === undefined ? was : id
  })
  createEffect(
    on(
      knownProject,
      () => setDrafts((was) => (was.project === undefined ? was : { ...was, project: undefined })),
      { defer: true },
    ),
  )

  return (
    <div class="flex flex-col">
      <Show when={thread.data.error}>
        <ErrorLine error={thread.data.error} />
      </Show>
      <Show when={memory.data.error}>
        <ErrorLine error={memory.data.error} />
      </Show>
      <For each={TARGETS}>
        {(target) => (
          <MemoryBlockEditor
            target={target}
            block={read()?.[target]}
            projectId={projectId() ?? null}
            disabled={target === "project" && projectId() === null}
            loading={!loaded()}
            failed={Boolean(memory.data.error)}
            draft={drafts()[target]}
            setDraft={(text) => setDrafts((was) => ({ ...was, [target]: text }))}
            onSaved={() => void memory.refetch()}
          />
        )}
      </For>
    </div>
  )
}

function MemoryBlockEditor(props: {
  target: MemoryTarget
  block: MemoryBlock | undefined
  projectId: number | null
  disabled: boolean
  /** The stored text has not arrived (or could not be read): nothing may be typed or saved. */
  loading: boolean
  failed: boolean
  draft: string | undefined
  setDraft: (text: string | undefined) => void
  onSaved: () => void
}) {
  const [saving, setSaving] = createSignal(false)
  const [refused, setRefused] = createSignal<string>()

  const stored = () => props.block?.text ?? ""
  const shown = () => props.draft ?? stored()
  const limit = () => props.block?.limit ?? DEFAULT_LIMITS[props.target]
  const used = createMemo(() => memoryUse(shown()))
  const over = () => used() > limit()
  const dirty = () => props.draft !== undefined && props.draft !== stored()

  const save = async () => {
    const text = props.draft
    if (text === undefined || saving()) return
    setSaving(true)
    setRefused(undefined)
    try {
      const answer = await harness<MemorySaved>("/api/memory", {
        method: "PUT",
        body: { target: props.target, project_id: props.projectId, text },
      })
      if (!answer?.ok) {
        setRefused(answer?.detail ?? "Not saved.")
        return
      }
      props.setDraft(undefined)
      props.onSaved()
    } catch (failure) {
      setRefused(failure instanceof Error ? failure.message : String(failure))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Section
      title={TITLE[props.target]}
      action={
        <span
          class="text-12-regular tabular-nums"
          classList={{ "text-v2-text-text-faint": !over(), "text-v2-state-fg-danger": over() }}
          title="Characters as the engine counts them: entries plus separators"
        >
          {used().toLocaleString()} / {limit().toLocaleString()}
        </span>
      }
    >
      <div class="flex flex-col gap-2 px-4">
        <Textarea
          class="!w-full"
          rows={8}
          spellcheck={false}
          value={shown()}
          disabled={props.disabled || props.loading}
          invalid={over()}
          placeholder={
            props.disabled
              ? "Open a conversation in a project to see what the project knows."
              : props.loading
                ? props.failed
                  ? "Could not read what is stored, so nothing can be edited until it reads."
                  : "Reading…"
                : EMPTY[props.target]
          }
          aria-label={TITLE[props.target]}
          onInput={(event) => {
            setRefused(undefined)
            props.setDraft(event.currentTarget.value)
          }}
        />
        <div class="flex items-center gap-2">
          <span class="min-w-0 flex-1 text-12-regular">
            <Show
              when={refused()}
              fallback={<span class="text-v2-text-text-faint">One entry per line, separated by §</span>}
            >
              {(message) => (
                <span class="flex items-start gap-1 text-v2-state-fg-danger">
                  <Icon name="circle-exclamation" size="small" class="mt-px shrink-0" />
                  <span>{message()}</span>
                </span>
              )}
            </Show>
          </span>
          <Button
            size="small"
            variant="ghost"
            disabled={!dirty() || saving()}
            onClick={() => {
              setRefused(undefined)
              props.setDraft(undefined)
            }}
          >
            Revert
          </Button>
          <Button
            size="small"
            variant="contrast"
            disabled={!dirty() || saving() || props.disabled || props.loading || over()}
            onClick={() => void save()}
          >
            {saving() ? "Saving" : "Save"}
          </Button>
        </div>
      </div>
    </Section>
  )
}
