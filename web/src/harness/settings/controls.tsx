import { createMemo } from "solid-js"
import { useSettingsSurface } from "@/settings/surface"
import "@/settings/settings.css"
import { FACADE } from "../../platform/engine"
import ControlsPane from "../panes/controls"
import { threadIdOf } from "../panel/panes"
import { useHarnessRead } from "../ui"
import { PageHeader } from "./connections-parts"

/**
 * Settings > Harness > Controls: every tool, run by hand (panes/controls.tsx,
 * moved here from the side panel).
 *
 * Settings is a route their surface remembers the way back from, and that
 * source route is the chat Settings was opened over. A run here is filed
 * under THAT conversation, as run by you - the same thing the side-panel
 * pane did. Opened from anywhere else, nothing is filed and the page says so.
 *
 * THE SESSION IS READ THROUGH THE HARNESS CLIENT, not their session store:
 * their root settings pages sit outside their server context, and `useData()`
 * here threw "Server context must be used within a context provider", taking
 * the whole app to its error screen - found by opening the page.
 */
export default function ControlsSection() {
  const surface = useSettingsSurface()
  const sessionID = () => {
    const route = surface.route()
    return route.type === "session" ? route.sessionId : undefined
  }
  const session = useHarnessRead<{ data?: unknown }>(() => {
    const id = sessionID()
    return id ? `${FACADE}/api/session/${encodeURIComponent(id)}` : undefined
  })
  const threadId = createMemo(() => (sessionID() && !session.data.error ? threadIdOf(session.data.latest?.data) : undefined))
  return (
    <>
      <PageHeader
        title="Controls"
        description="Every tool the model can call, as a form you can run yourself - the same operations, the same approvals."
      />
      <div class="settings-tab-body">
        <ControlsPane threadId={threadId()} />
      </div>
    </>
  )
}
