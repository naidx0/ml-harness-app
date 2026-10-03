import { Button } from "@opencode/ui/button"
import { ScrollView } from "@opencode/ui/scroll-view"
import { Show } from "solid-js"
import { createHomeController } from "@/home/model"
import { createHomeScrollController } from "@/home/scroll"
import { createHomeSessionSearchController } from "@/home/sessions/search"
import { createHomeSessionsController } from "@/home/sessions/controller"
import { HomeSessions } from "@/home/sessions/region"
import "./home.css"

/**
 * Home, this product's way (stands in for their `home/route.tsx`, SUBSTITUTES
 * in web/vite.config.ts).
 *
 * Jaden, 2026-10-03: their Home was a copy with our colours. Theirs is two
 * columns: projects with Settings and Help on the left, chats on the right.
 * Here the left sidebar already has Home, New chat, Settings and every
 * project (slice 2, docs/onboarding-ui-plan.md), so Home is one column: a
 * title, one New chat button, and your chats with search. Their chats list
 * (controllers, search, rows, rename, archive) is reused as it is; only its
 * own floating New chat is hidden, because the header has the one button.
 */
export function Home() {
  const home = createHomeController()
  const sessions = createHomeSessionsController(home)
  const search = createHomeSessionSearchController(home, sessions)
  const scroll = createHomeScrollController(sessions.data.groups)
  return (
    <div
      data-component="harness-home"
      class="mx-2 mb-[var(--shell-bottom-inset,8px)] mt-[var(--shell-top-inset,8px)] flex min-h-0 flex-1 flex-col self-stretch overflow-hidden rounded-[10px] bg-v2-background-bg-base shadow-[var(--v2-elevation-raised)]"
    >
      <ScrollView
        class="min-h-0 flex-1 [container-type:size]"
        thumbContainer={scroll.viewport.thumbTrack()}
        thumbHoverTarget={scroll.viewport.hoverTarget()}
        viewportRef={scroll.viewport.setViewport}
        onScroll={(event) => scroll.viewport.update(event.currentTarget.scrollTop)}
        onWheel={scroll.viewport.containOuterWheel}
      >
        <div class="mx-auto flex min-h-full w-full max-w-[720px] flex-col px-4 lg:px-6">
          <header data-slot="harness-home-header" class="flex items-end justify-between gap-3 pt-8 lg:pt-12">
            <div class="flex min-w-0 flex-col gap-1">
              <h1 class="[font-family:var(--font-family-display)] text-[22px] leading-7 [font-weight:600] text-v2-text-text-base">
                Your chats
              </h1>
              <p class="text-[13px] text-v2-text-text-muted">Every chat, newest first. Projects are in the sidebar.</p>
            </div>
            {/* With no chats yet, the empty state below has the one New chat. */}
            <Show when={sessions.session.canCreate() && sessions.data.groups().length > 0}>
              <Button
                data-action="harness-home-new-chat"
                variant="contrast"
                size="normal"
                icon="edit"
                class="shrink-0"
                onClick={sessions.session.create}
              >
                New chat
              </Button>
            </Show>
          </header>
          <HomeSessions sessions={sessions} search={search} scroll={scroll} />
        </div>
      </ScrollView>
    </div>
  )
}
