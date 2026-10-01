import { createEffect, on } from "solid-js"
import { useLocation } from "@solidjs/router"
import { createApiForServer } from "@/runtime/server/api"
import { usePlatform } from "@/runtime/platform/platform"
import { ServerConnection, useServers } from "@/runtime/server/registry"
import { useTabs } from "@/shell/tabs/tabs"

/**
 * Land in a chat, in the default workspace, on a launch with nothing open.
 *
 * Their app opens on Home: a list of projects to pick from, which is right for
 * a tool pointed at many repositories and one step too many for this product.
 * The harness already has a default workspace - the engine answers
 * `location.get()` without a directory with it - so a launch with no open tab
 * opens that workspace and a new chat in it, and the first thing on screen is
 * the composer.
 *
 * Only when nothing is open. A person who left three chats open finds three
 * chats open; their tab restore is not second-guessed. And only on "/", so a
 * deep link or the settings screen is never pulled away from.
 */
export function OpenDefaultWorkspace(props: { server: ServerConnection.Any }) {
  const tabs = useTabs()
  const servers = useServers()
  const route = useLocation()
  const platform = usePlatform()
  let decided = false

  createEffect(
    on(tabs.ready, (ready) => {
      if (!ready || decided) return
      decided = true
      if (route.pathname !== "/" || tabs.store.length > 0) return

      const key = ServerConnection.key(props.server)
      const api = createApiForServer({ server: props.server.http, fetch: platform.fetch })
      void api.location
        .get()
        .then((location) => {
          // Still on Home and still empty: the person may have clicked
          // somewhere while the engine answered.
          if (route.pathname !== "/" || tabs.store.length > 0) return
          servers.projects.forServer(key).open(location.directory)
          return tabs.newDraft({ server: key, directory: location.directory })
        })
        // Home is a working fallback: it lists the workspace too. Nothing to
        // report, because nothing is broken.
        .catch(() => undefined)
    }),
  )

  return null
}
