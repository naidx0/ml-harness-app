import { createEffect, createSignal, For, Match, Show, Switch as Branch } from "solid-js"
import { Badge } from "@opencode/ui/badge"
import { SegmentedControl, SegmentedControlItem } from "@opencode/ui/segmented-control"
import { Select } from "@opencode/ui/select"
import { Switch } from "@opencode/ui/switch"
import { SettingsList } from "@/settings/list"
import { SettingsRow } from "@/settings/row"
import "@/settings/settings.css"
import { harness } from "../engine"
import { listPhase, useHarnessRead } from "../ui"
import { BusyText, EmptyLine, ErrorText, PageHeader, SettingsSection } from "./connections-parts"
import {
  defaultProject,
  isOff,
  merged,
  onTheWire,
  subagentChoices,
  toggledPacks,
  type PackSetting,
  type Project,
  type ProjectSettings,
} from "./tools-model"

/**
 * Settings > Tools: what a project hands the model, and what it costs
 * (PARITY 8.2). From the outgoing `ToolSettings.tsx`.
 *
 * Every pack left on is sent with every turn, as JSON, on top of the
 * conversation. Measured on the owner's database: 12,735 tokens of a 29,929-
 * token prompt were tool schemas. So every switch carries its number, counted
 * by the engine with the same budget that bills a real turn.
 *
 * The outgoing panel needed an open conversation to know the project. Here
 * the project is picked, defaulting to the engine's default project, so the
 * page works from Settings with nothing open.
 *
 * No "how often" for sub-agents, on purpose: the harness does not choose how
 * often to delegate, the model does, turn by turn. The cap is real because it
 * is enforced at the door, and None is the strongest "not often" that can be
 * kept.
 */
export default function Section() {
  const projects = useHarnessRead<Project[]>(() => "/api/projects")
  const projectList = () => (projects.data.error ? [] : (projects.data.latest ?? []))
  const [chosen, setChosen] = createSignal<number>()

  // Open on the default project once the list arrives; keep a person's pick.
  createEffect(() => {
    const list = projectList()
    if (chosen() !== undefined && list.some((project) => project.id === chosen())) return
    setChosen(defaultProject(list)?.id)
  })

  // useHarnessRead, not a raw createResource: a raw resource's `loading`
  // stays true inside their transitions, so "Reading this project's
  // settings" could stay on screen after the settings had arrived.
  const settingsRead = useHarnessRead<ProjectSettings>(() => {
    const id = chosen()
    return id === undefined ? undefined : `/api/projects/${id}/settings`
  })
  const settings = settingsRead.data
  const mutate = settingsRead.mutate
  const current = () => (settings.error ? undefined : settings.latest)
  const [busy, setBusy] = createSignal<string>()
  const [error, setError] = createSignal<unknown>()

  const save = async (label: string, change: { subagents_max?: number; packs_off?: string[] }) => {
    const id = chosen()
    if (id === undefined) return
    setBusy(label)
    setError(undefined)
    try {
      const answer = await harness<Partial<ProjectSettings>>(`/api/projects/${id}/settings`, { body: change })
      mutate((was) => (was ? merged(was, answer) : was))
    } catch (failure) {
      setError(failure)
    } finally {
      setBusy(undefined)
    }
  }

  const togglePack = (state: ProjectSettings, pack: PackSetting, on: boolean) =>
    void save(on ? `Offering ${pack.name} again…` : `Switching ${pack.name} off…`, {
      packs_off: toggledPacks(state.packs_off, pack, on),
    })

  return (
    <>
      <PageHeader
        title="Tools"
        description="How many sub-agents a project may run, and which tool packs are sent to the model with every turn."
      />
      <div class="settings-tab-body settings-tab-body--sectioned">
        <SettingsSection title="Project">
          <SettingsList>
            <SettingsRow
              title="Settings for"
              description="These belong to a project, not the app: a machine that runs one sub-agent at a time has decided that for the work, not for one chat."
            >
              <Show
                when={projectList().length > 0}
                // A failed read is not an empty list: "No projects yet" under a
                // read that never answered told a person they had none.
                fallback={
                  <Branch>
                    <Match when={listPhase(projects.data) === "failed"}>
                      <div class="flex flex-col items-end gap-1">
                        <span class="text-[13px] text-v2-text-text-muted">Could not read the projects</span>
                        <ErrorText error={projects.data.error} />
                      </div>
                    </Match>
                    <Match when={listPhase(projects.data) === "reading"}>
                      <span class="text-[13px] text-v2-text-text-muted">Reading projects…</span>
                    </Match>
                    <Match when={true}>
                      <span class="text-[13px] text-v2-text-text-muted">No projects yet</span>
                    </Match>
                  </Branch>
                }
              >
                <Select
                  options={projectList()}
                  current={projectList().find((project) => project.id === chosen())}
                  value={(project) => String(project.id)}
                  label={(project) => project.name}
                  placement="bottom-end"
                  gutter={6}
                  onSelect={(project) => project && setChosen(project.id)}
                />
              </Show>
            </SettingsRow>
          </SettingsList>
        </SettingsSection>

        <Show when={settings.error}>{(failure) => <ErrorText error={failure()} />}</Show>
        <ErrorText error={error()} />
        <BusyText text={busy()} />

        <Show
          when={current()}
          fallback={
            <Show when={chosen() !== undefined && !settings.answered}>
              <p class="text-[13px] text-v2-text-text-muted">Reading this project's settings…</p>
            </Show>
          }
        >
          {(state) => {
            const wire = () => onTheWire(state())
            return (
              <>
                <SettingsSection title="Sub-agents">
                  <SettingsList>
                    <SettingsRow
                      title="At once"
                      description="How many phases this project may have worked in parallel. Each is its own conversation with the whole toolset, in this project's folder. None turns delegation off: the tool refuses and says so rather than starting one quietly."
                    >
                      <SegmentedControl
                        aria-label="Sub-agents at once"
                        value={String(state().subagents_max)}
                        disabled={busy() !== undefined}
                        onChange={(value) => {
                          if (value === null) return
                          const next = Number(value)
                          if (next !== state().subagents_max)
                            void save("Saving the sub-agent limit…", { subagents_max: next })
                        }}
                      >
                        <For each={subagentChoices(state().most_subagents)}>
                          {(choice) => (
                            <SegmentedControlItem value={String(choice.value)}>{choice.label}</SegmentedControlItem>
                          )}
                        </For>
                      </SegmentedControl>
                    </SettingsRow>
                  </SettingsList>
                </SettingsSection>

                <SettingsSection
                  title="Tools on the prompt"
                  note={
                    <>
                      Every pack left on is sent with every turn. Right now:{" "}
                      <span class="tabular-nums text-v2-text-text-base">
                        {wire().tools} tools, {wire().tokens.toLocaleString()} tokens
                      </span>
                      .
                    </>
                  }
                >
                  <SettingsList>
                    <Show when={state().packs.length > 0} fallback={<EmptyLine>The engine reported no packs.</EmptyLine>}>
                      <For each={state().packs}>
                        {(pack) => (
                          <SettingsRow
                            title={
                              <span class="flex items-center gap-2">
                                {pack.name}
                                <Show when={pack.core}>
                                  <Badge>Core</Badge>
                                </Show>
                              </span>
                            }
                            description={
                              <span class="tabular-nums">
                                {pack.tools} tools · {pack.tokens.toLocaleString()} tokens
                                {pack.core
                                  ? " · always on: without it a turn cannot write a plan or tick a step"
                                  : isOff(state(), pack)
                                    ? " · not offered"
                                    : ""}
                              </span>
                            }
                          >
                            <div>
                              <Switch
                                checked={!isOff(state(), pack)}
                                disabled={pack.core || busy() !== undefined}
                                hideLabel
                                onChange={(on: boolean) => togglePack(state(), pack, on)}
                              >
                                {`Offer the ${pack.name} pack`}
                              </Switch>
                            </div>
                          </SettingsRow>
                        )}
                      </For>
                    </Show>
                  </SettingsList>
                </SettingsSection>
              </>
            )
          }}
        </Show>
      </div>
    </>
  )
}
