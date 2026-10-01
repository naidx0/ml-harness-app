import { createEffect, createMemo, createSignal, For, lazy, on, Show, Suspense, type Component } from "solid-js"
import { Icon } from "@opencode/ui/icon"
import { IconButton } from "@opencode/ui/icon-button"
import { Keybind } from "@opencode/ui/keybind"
import { Menu } from "@opencode/ui/menu"
import { Tooltip } from "@opencode/ui/tooltip"
import { useData } from "@/runtime/server/current"
import { useLanguage } from "@/runtime/i18n/language"
import { useSessionLayout } from "@/session/session-layout"
import { useLayout } from "@/shell/state/layout"
import { CONTEXT_PANE, HARNESS_PANES, HARNESS_TAB_PREFIX, paneOf, tabOf, threadIdOf, windowPaneOf, type PaneProps, type PaneSpec } from "./panes"
import { PaneEmpty, PaneFrame } from "./frame"
import { addEntries } from "./add-menu"

/**
 * The three slots their side panel renders for a `harness:` tab (patches P5-P8
 * in scripts/vendor_opencode.py). Everything the panel does around them - the
 * tab strip, dragging, closing, resizing, the saved width - is theirs.
 */

const loaded = new Map<string, Component<PaneProps>>()
function componentOf(pane: PaneSpec) {
  let component = loaded.get(pane.id)
  if (!component) {
    component = lazy(pane.load)
    loaded.set(pane.id, component)
  }
  return component
}

/** The label inside their SortableTab - the same markup as their BTW tab. */
export function HarnessTabLabel(props: { tab: string }) {
  // windowPaneOf, not paneOf: an old saved Context tab still reads "Context".
  const pane = createMemo(() =>
    props.tab.startsWith(HARNESS_TAB_PREFIX) ? windowPaneOf(props.tab.slice(HARNESS_TAB_PREFIX.length)) : undefined,
  )
  return (
    <div class="flex items-center gap-1.5">
      <Show when={pane()}>{(pane) => <Icon name={pane().icon} size="small" />}</Show>
      <span>{pane()?.title ?? MOVED[props.tab]?.label ?? props.tab}</span>
    </div>
  )
}

function useThreadId() {
  const { params } = useSessionLayout()
  const data = useData()
  return createMemo(() => (params.id ? threadIdOf(data.session.get(params.id)) : undefined))
}

/** Panes that left the side panel, by their old tab id. */
const MOVED: Record<string, { label: string; title: string; where: string }> = {
  [tabOf(CONTEXT_PANE.id)]: {
    label: "Context",
    title: "Context moved",
    where: "It opens from the context ring in the session header. This tab can be closed.",
  },
  [tabOf("controls")]: {
    label: "Controls",
    title: "Controls moved",
    where: "Every tool, run by hand, is in Settings > Harness > Controls. This tab can be closed.",
  },
}

export function HarnessPanelContent(props: { tab: string }) {
  const pane = createMemo(() => paneOf(props.tab))
  const threadId = useThreadId()
  return (
    <Show
      when={pane()}
      fallback={
        // A chat saved with a tab from before its pane moved keeps the id;
        // the tab says where the pane went.
        <PaneEmpty title={MOVED[props.tab]?.title ?? "This panel is not part of this version"}>
          {MOVED[props.tab]?.where ?? "It can be closed."}
        </PaneEmpty>
      }
    >
      {(pane) => {
        const Pane = componentOf(pane())
        return (
          <PaneFrame pane={pane()} threadId={threadId()}>
            <Suspense fallback={<PaneEmpty title={`Opening ${pane().title}`} />}>
              <Pane threadId={threadId()} />
            </Suspense>
          </PaneFrame>
        )
      }}
    </Show>
  )
}

/**
 * Open a harness pane in this session's side panel, and show the panel. The
 * one way in, shared by the "+" menu and (later) commands and auto-focus.
 */
export function useOpenHarnessPane() {
  const { tabs, view } = useSessionLayout()
  return (id: string) => {
    tabs().open(tabOf(id))
    view().reviewPanel.open()
  }
}

/**
 * THE side panel's one "+" (patch P8 replaces their plus block with this):
 * their "Open file" - their own action and keybind, passed in - then the
 * harness panels, under one search. Their trigger's size, variant and
 * tooltip; their "Add tab" words.
 */
export function HarnessPanelAddButton(props: { onOpenFile: () => void; openFileKeybind: string[] }) {
  const open = useOpenHarnessPane()
  const { params } = useSessionLayout()
  const language = useLanguage()
  const [query, setQuery] = createSignal("")
  const layout = useLayout()
  // CONTROLLED, AND CLOSED WHEN ITS CHAT LEAVES THE SCREEN. Their app keeps a
  // switched-away chat's screen alive in the background, so this panel - and
  // its menu - never unmounts, and its own session id never changes: opened
  // in one chat, the menu was still floating over the next, seen in the
  // two-chat walk. The question is whether THIS chat is still the one on
  // screen, which is their current route, not this component's params.
  const [menuOpen, setMenuOpen] = createSignal(false)
  const onScreen = createMemo(() => {
    const route = layout.route()
    return route.type === "session" && route.sessionId === params.id
  })
  createEffect(
    on(onScreen, (visible) => {
      if (!visible) setMenuOpen(false)
    }),
  )
  const fileLabel = () => language.t("command.file.open")
  const entries = createMemo(() => addEntries(query(), fileLabel(), HARNESS_PANES))
  const hasFile = () => entries()[0]?.kind === "file"
  const panes = createMemo(() => entries().flatMap((entry) => (entry.kind === "pane" ? [entry.pane] : [])))
  return (
    <Tooltip value={language.t("session.tab.add")} placement="bottom" class="flex items-center">
      <Menu
        appearance="standard"
        modal={false}
        placement="bottom-start"
        gutter={4}
        open={menuOpen()}
        onOpenChange={(next: boolean) => {
          setMenuOpen(next)
          setQuery("")
        }}
      >
        <Menu.Trigger
          as={IconButton}
          icon={<Icon name="plus" />}
          variant="ghost-muted"
          size="large"
          aria-label={language.t("session.tab.add")}
          // Their note on the same trigger: the tablist redirects focus
          // entering it, which counts as focus-outside and closes the menu.
          onPointerDown={(event: PointerEvent) => event.preventDefault()}
        />
        <Menu.Portal>
          <Menu.Content>
            <div class="px-2 pb-1 pt-1">
              <input
                class="w-full rounded-md border border-transparent bg-v2-background-bg-layer-01 px-2 py-1 text-[13px] text-v2-text-text-base outline-none placeholder:text-v2-text-text-muted focus:border-v2-border-border-focus"
                placeholder="Find a file action or panel"
                aria-label="Find a file action or panel"
                value={query()}
                onInput={(event) => setQuery(event.currentTarget.value)}
                onKeyDown={(event) => event.stopPropagation()}
              />
            </div>
            <Show when={hasFile()}>
              {/* Their item, as their menu drew it: file-tree icon, their words, their keybind. */}
              <Menu.Item
                class="!gap-6"
                onSelect={() => props.onOpenFile()}
                shortcut={
                  <Show when={props.openFileKeybind.length > 0}>
                    <Keybind keys={props.openFileKeybind} variant="neutral" />
                  </Show>
                }
              >
                <div class="flex items-center gap-2">
                  <Icon name="file-tree" size="small" />
                  <span>{fileLabel()}</span>
                </div>
              </Menu.Item>
            </Show>
            <Show when={hasFile() && panes().length > 0}>
              <Menu.Separator />
            </Show>
            <For each={panes()}>
              {(pane) => (
                <Menu.Item class="!gap-6" onSelect={() => open(pane.id)}>
                  <div class="flex items-center gap-2">
                    <Icon name={pane.icon} size="small" />
                    <span>{pane.title}</span>
                    <span class="text-v2-text-text-muted">{pane.hint}</span>
                  </div>
                </Menu.Item>
              )}
            </For>
            <Show when={entries().length === 0}>
              <div class="px-3 py-1.5 text-[13px] text-v2-text-text-muted">Nothing matches "{query().trim()}".</div>
            </Show>
          </Menu.Content>
        </Menu.Portal>
      </Menu>
    </Tooltip>
  )
}
