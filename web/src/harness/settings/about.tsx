import { createResource, Show, type JSX } from "solid-js"
import { SettingsList } from "@/settings/list"
import { SettingsRow } from "@/settings/row"
import { usePlatform } from "@/runtime/platform/platform"
import "@/settings/settings.css"
import { harness } from "../engine"
import { FACADE } from "../../platform/engine"
import { buildLine, notReadyHealth, runsLine, shortHex, versionLine, type Health } from "./engine-identity"
import { ErrorText, PageHeader, SettingsSection } from "./connections-parts"

/**
 * Settings > About, this product's own (the owner, 2026-09-23: "About says
 * OpenCode, anomaly, etc. - get rid of that About ... make sure it's all
 * mapped to our actual true systems").
 *
 * Their About page - wordmark animation, contributor list, trademark, their
 * website - is hidden (unbacked.ts). This one says what is running here, each
 * value read from the engine rather than written into the page:
 *
 *   Version  - this window's (`platform.version`, web/src/entry.tsx) and the
 *              engine's (`GET /oc/api/info`, the FastAPI app's version).
 *   Build    - the commit the engine runs (`/health` build.sha).
 *   Engine   - the process answering (`/health` engine.engine_id).
 *   Database - where threads and runs live, and how many runs it holds
 *              (`/health` database.path, database.runs).
 *
 * The interface's origin gets one line, as the licence asks; the notice itself
 * travels in THIRD-PARTY-NOTICES.txt.
 */
export const CREDIT = "Interface derived from OpenCode (MIT)"

export default function Section() {
  const platform = usePlatform()
  const [health] = createResource(async () => {
    try {
      return await harness<Health>("/health")
    } catch (failure) {
      // A 503 still carries the readout; the identity in it is what this page shows.
      const readout = notReadyHealth(failure)
      if (readout) return readout
      throw failure
    }
  })
  const [info] = createResource(() => harness<{ version?: string }>(`${FACADE}/api/info`))

  const reading = () => (health.error ? undefined : health.latest)
  const engineVersion = () => (info.error ? undefined : info.latest?.version)
  const missing = () => (health.error ? "engine not answering" : health.loading ? "…" : "not reported")

  return (
    <>
      <PageHeader title="About" description="ML Harness, a local workbench for building and measuring models." />
      <div class="settings-tab-body settings-tab-body--sectioned">
        <SettingsSection title="ML Harness">
          <Show when={health.error}>{(failure) => <ErrorText error={failure()} />}</Show>
          <SettingsList>
            <Fact
              title="Version"
              description="This window's release, and the engine's when it differs."
              value={versionLine(platform.version, engineVersion())}
              missing="not reported"
            />
            <Fact
              title="Build"
              description="The git commit the engine is running."
              value={buildLine(reading()?.build)}
              tip={reading()?.build?.sha ?? undefined}
              missing={missing()}
            />
            <Fact
              title="Engine"
              description="The id of the engine process answering this window. Settings > Engine has the rest."
              value={reading()?.engine?.engine_id ? shortHex(reading()?.engine?.engine_id, 16) : undefined}
              tip={reading()?.engine?.engine_id}
              missing={missing()}
            />
            <Fact
              title="Database"
              description="Threads, projects, runs and measured facts, in SQLite on this computer."
              value={reading()?.database?.path ?? undefined}
              mono
              missing={missing()}
            />
            <Fact
              title="Runs"
              description="Runs recorded in that database."
              value={runsLine(reading()?.database?.runs)}
              missing={missing()}
            />
          </SettingsList>
          <p data-slot="about-credit" class="pt-1 text-[12px] text-v2-text-text-faint">
            {CREDIT}
          </p>
        </SettingsSection>
      </div>
    </>
  )
}

function Fact(props: {
  title: string
  description: JSX.Element
  value: string | undefined
  missing: string
  tip?: string
  mono?: boolean
}) {
  return (
    <SettingsRow title={props.title} description={props.description}>
      <span
        class="max-w-[280px] truncate text-[13px] tabular-nums"
        classList={{
          "font-mono text-12-regular": !!props.mono,
          "text-v2-text-text-base": props.value !== undefined,
          "text-v2-text-text-faint": props.value === undefined,
        }}
        title={props.tip ?? props.value}
      >
        {props.value ?? props.missing}
      </span>
    </SettingsRow>
  )
}
